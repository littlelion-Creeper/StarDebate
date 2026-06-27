"""StarDebate ★ 辩之星 — 启动器
============================================================================
职责：
  1. 启动 LogService 独立进程（日志写入与系统健康监视）
  2. 创建 QApplication + 全局 QSS
  3. 创建 StarDebateApp 主窗口并注入日志队列
  4. 编排两个进程的生命周期（启动 → 运行 → 正常退出 → 清理）

软重启（更新器 v2.0）：
  QApplication 和 LogService 在 main_loop() 中一次性创建。
  更新完成后 `app.quit()` → 关闭旧窗口 → 循环内重新 _start_window()，
  不重新创建 QApp / LogService。

架构：
  StarDebate.py (启动器 - 主进程)
  ├── LogService 子进程 (star_debate_log.py)
  │   ├── LogManager → 文件写入
  │   └── SystemHealthMonitor → 主进程存活检测
  └── StarDebateApp (主窗口 - 主进程同一线程)
      ├── LogClient → 轻量队列投递
      ├── StderrToLogRedirector → 崩溃直写文件
      └── DebugMonitorManager → 监视钩子（队列投递+降级）

主窗口崩溃 ≠ 日志丢失：LogService 独立进程持续写入，并记录崩溃快照。
主窗口正常退出 → 根据「保留正常退出日志」设置决定是否删除日志文件。
============================================================================="""
import sys
import os
import json
import multiprocessing

# ── ★ Windows: 防止 multiprocessing 子进程弹出控制台白窗 ─────────
if sys.platform == "win32":
    _no_console_patched = False
    try:
        import _winapi as _wa
        _orig_wa_CP = _wa.CreateProcess
        _CREATE_NO_WINDOW = 0x08000000

        def _patched_CreateProcess(*args, **kwargs):
            if "creationflags" in kwargs:
                kwargs["creationflags"] = (kwargs["creationflags"] or 0) | _CREATE_NO_WINDOW
            elif len(args) >= 6:
                args = list(args)
                args[5] = (args[5] or 0) | _CREATE_NO_WINDOW
            return _orig_wa_CP(*args, **kwargs)

        _wa.CreateProcess = _patched_CreateProcess
        _no_console_patched = True
    except Exception:
        pass

    if not _no_console_patched:
        try:
            import subprocess as _sp
            _orig_exec = _sp.Popen._execute_child

            def _patched_execute_child(self, args, executable, preexec_fn,
                                        close_fds, pass_fds, cwd, env,
                                        startupinfo, creationflags, shell,
                                        p2cread, p2cwrite, c2pread, c2pwrite,
                                        errread, errwrite, restore_sigmask,
                                        gid, gids, uid, umask, start_new_session):
                creationflags = (creationflags or 0) | 0x08000000
                return _orig_exec(self, args, executable, preexec_fn,
                                   close_fds, pass_fds, cwd, env,
                                   startupinfo, creationflags, shell,
                                   p2cread, p2cwrite, c2pread, c2pwrite,
                                   errread, errwrite, restore_sigmask,
                                   gid, gids, uid, umask, start_new_session)

            _sp.Popen._execute_child = _patched_execute_child
        except Exception:
            pass

    # ★ 隐藏当前进程的控制台窗口
    try:
        import ctypes
        _hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if _hwnd:
            ctypes.windll.user32.ShowWindow(_hwnd, 0)
    except Exception:
        pass

# ── PyQt-SiliconUI 组件（迁入 components/siui/）───────────────────
from components.res_path import get_resource_root
_SIUI_COMPONENTS_DIR = os.path.join(get_resource_root(), "components")
if os.path.isdir(_SIUI_COMPONENTS_DIR) and _SIUI_COMPONENTS_DIR not in sys.path:
    sys.path.insert(0, _SIUI_COMPONENTS_DIR)

# ── 日志服务 ─────────────────────────────────────────────────────────
# ── 配置路径统一解析 ──────────────────────────────────────────────
from workers.app_config import ensure_config_dir, get_config_path
from components.res_path import get_resource_root, get_resource_path

from star_debate_log import LogService

# ── PyQt5 ────────────────────────────────────────────────────────────
from PyQt5.QtWidgets import QApplication, QShortcut
from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.QtGui import QKeySequence, QFontDatabase, QIcon

# ── 更新器软重启检测 ────────────────────────────────────────────────
from workers.updater.update_utils import needs_restart, write_update_state, read_update_state
from workers.updater.update_utils import _MAX_RESTART_LOOP


def _load_harmonyos_font():
    """加载 HarmonyOS Sans SC 字体（注册到 QFontDatabase）。

    与 QSS 中 font-family: "HarmonyOS Sans SC" 保持一致。
    """
    font_dir = os.path.join(get_resource_root(),
                            "style", "font", "HarmonyOS_SansSC")
    font_files = [
        "HarmonyOS_SansSC_Regular.ttf",
    ]
    loaded = 0
    for fn in font_files:
        path = os.path.join(font_dir, fn)
        if os.path.exists(path):
            fid = QFontDatabase.addApplicationFont(path)
            if fid >= 0:
                loaded += 1
    if loaded > 0:
        print(f"[StarDebate] HarmonyOS Sans SC 字体已加载 ({loaded}/{len(font_files)})")


def _apply_global_qss(app: QApplication):
    """应用全局 QSS 样式（ToolTip 等）。"""
    app.setStyleSheet("""
        QMainWindow, QWidget {
            background-color: #1e1e2e;
        }
        QToolTip {
            max-width: 390px;
            padding: 10px 14px;
            border: 1px solid #585b70;
            border-radius: 8px;
            background-color: #313244;
            color: #cdd6f4;
            font-size: 18px;
            font-family: "HarmonyOS Sans SC", "Microsoft YaHei", sans-serif;
        }
    """)


def _emergency_force_quit(app: QApplication):
    """紧急强制退出：先尝试正常退出，3 秒后仍不退出则 os._exit()。"""
    print("[StarDebate] ⚠ 紧急退出触发 (Alt+F4)...")
    try:
        app.quit()
    except Exception:
        pass
    from PyQt5.QtCore import QTimer
    def _force_kill():
        os._exit(1)
    QTimer.singleShot(3000, _force_kill)


def _load_log_settings() -> dict:
    config_path = get_config_path("config/log_settings.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_log_settings(cfg: dict) -> bool:
    config_path = get_config_path("config/log_settings.json")
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════════════
#  _start_window — 创建主窗口并进入事件循环（每轮软重启调用一次）
# ════════════════════════════════════════════════════════════════════════

def _start_window(app: QApplication, log_queue, log_path: str,
                  log_settings: dict, restart_count: int = 0) -> int:
    """创建 StarDebateApp → 显示 → 事件循环 → 返回退出码。

    每轮软重启调用一次，QApp 和 LogService 由外部创建。
    """
    project_root = get_resource_root()

    # ── ★ 确保持久化配置目录存在（首次自动复制默认配置）─────────
    ensure_config_dir()

    # ── 获取版本号（横幅需要）────────────────────────────────────
    _banner_version = "1.0.0"
    try:
        _cfg_path = get_config_path("config/config.json")
        with open(_cfg_path, "r", encoding="utf-8") as _f:
            _banner_version = json.load(_f).get("version", "1.0.0")
    except Exception:
        pass

    # ── 首次运行时初始化全局资源（字体、QSS、SvgRenderer）───────
    if restart_count == 0:
        from workers.startup_banner import StartupBanner
        _banner = StartupBanner(version=_banner_version)
        _banner.show_with_fade()

        _banner.set_progress(1, 7, "正在初始化应用环境...")
        _banner.set_progress(2, 7, "正在加载字体与样式...")
        _load_harmonyos_font()
        _apply_global_qss(app)

        _banner.set_progress(3, 7, "正在初始化渲染器...")
        from components.svg_renderer import SvgRenderer
        SvgRenderer.init(project_root)

        _banner.set_progress(4, 7, "正在启动日志服务...")
    else:
        from workers.startup_banner import StartupBanner
        _banner = StartupBanner(version=_banner_version)
        _banner.show_with_fade()
        _banner.set_progress(1, 7, "正在重新加载...")
        _banner.set_progress(2, 7, "正在配置环境...")
        _banner.set_progress(3, 7, "正在初始化渲染器...")
        _banner.set_progress(4, 7, "日志服务已就绪")

    # ── 阶段 5/7：创建主窗口 ──────────────────────────────────────
    _banner.set_progress(5, 7, "正在加载功能模块...")
    from StarDebate_app import StarDebateApp
    window = StarDebateApp(log_queue, log_path, log_settings,
                           startup_banner=_banner)

    # ── 全局紧急退出快捷键（Alt+F4）───────────────────────────────
    _emergency_quit = QShortcut(QKeySequence(QKeySequence.Quit), window,
                                context=Qt.ApplicationShortcut)
    _emergency_quit.activated.connect(lambda: _emergency_force_quit(app))

    # ── 关闭横幅 → 显示主窗口 ────────────────────────────────────
    _banner.fade_out_and_close()
    window.show()

    # ── 进入事件循环 ──────────────────────────────────────────────
    exit_code = app.exec_()
    return exit_code


# ════════════════════════════════════════════════════════════════════════
#  _cleanup_log — 正常退出时清理日志
# ════════════════════════════════════════════════════════════════════════

def _cleanup_log(log_path: str):
    """正常退出时根据设置决定是否删除日志文件。"""
    keep_normal_exit_log = False
    try:
        exit_cfg = _load_log_settings()
        keep_normal_exit_log = exit_cfg.get("log_service", {}).get(
            "keep_normal_exit_log", False)
    except Exception:
        pass

    if log_path and os.path.isfile(log_path) and not keep_normal_exit_log:
        try:
            os.remove(log_path)
            print(f"[StarDebate] 正常退出，已删除日志: {os.path.basename(log_path)}")
        except OSError as e:
            print(f"[StarDebate] 删除日志失败: {e}")
    elif log_path and os.path.isfile(log_path) and keep_normal_exit_log:
        print(f"[StarDebate] 已保留日志: {os.path.basename(log_path)}")
        reset_cfg = _load_log_settings()
        reset_cfg.setdefault("log_service", {})["keep_normal_exit_log"] = False
        _save_log_settings(reset_cfg)


def _safe_close_all_windows(app: QApplication):
    """安全关闭所有顶级窗口（软重启专用）。

    解决的问题：
    1. app.quit() 只终止事件循环（exec_() 返回），不会关闭/隐藏 QWidget
    2. 模态对话框（如 SettingsDialog.exec_()）在 quit 后状态不一致，
       close() 可能被阻塞或无效
    3. 父窗口可能因子窗口存在而拒绝关闭
    4. 单次 processEvents() 无法处理完整的异步关闭链

    策略：
    ① 先 hide() 所有非 QApplication 顶级窗口 → 立即隐藏视觉
    ② 按从子到父的顺序 close() → 避免父等子的问题
    ③ 多轮 processEvents() + deleteLater() → 彻底清理 Qt 对象树
    """
    from PyQt5.QtWidgets import QDialog

    # ── 第 1 步：立即隐藏所有窗口（防止视觉双窗）───────────────────
    all_widgets = [w for w in app.topLevelWidgets()
                   if not isinstance(w, QApplication)]
    for w in all_widgets:
        try:
            if w.isVisible():
                w.hide()
        except Exception:
            pass

    # ── 第 2 步：按正确顺序关闭（子窗口/对话框先于主窗口）───────────
    # QDialog / 弹窗类优先关闭
    dialogs = [w for w in all_widgets if isinstance(w, QDialog)]
    others = [w for w in all_widgets if not isinstance(w, QDialog)]

    for w in dialogs + others:
        try:
            # 对模态对话框：先 reject 再 close（确保内部状态一致）
            if isinstance(w, QDialog) and hasattr(w, 'reject'):
                try:
                    w.reject()
                except Exception:
                    pass
            w.close()
        except Exception:
            pass

    # ── 第 3 步：多轮事件处理 + 强制清理 ────────────────────────────
    # 关闭事件链是异步的，需要多次处理才能完成
    for _ in range(5):
        app.processEvents()

    # 对仍存活的 widget 发送 deleteLater（标记为待删除）
    remaining = [w for w in app.topLevelWidgets()
                 if not isinstance(w, QApplication)]
    for w in remaining:
        try:
            w.deleteLater()
        except Exception:
            pass

    # 最终一轮事件处理，确保 deleteLater 被执行
    for _ in range(3):
        app.processEvents()

    closed_count = len(all_widgets)
    print(f"[StarDebate] 已关闭 {closed_count} 个旧窗口 ("
          f"{len(dialogs)} 对话框, {len(others)} 其他)")


def _reset_global_singletons():
    """重置所有全局单例（软重启专用）。

    问题：旧窗口关闭后，以下全局单例仍持有旧窗口引用：
    - UndoCoordinator._instance → 旧的 _mw / _edit_menu / _stacks
    - ShortcutManager._instance → 旧的 _window + 旧 QShortcut 绑定
    - PluginManager._manager → 插件持有旧上下文
    - _safe_api (plugin_manager 模块) → 旧 API 实例

    新窗口创建时这些单例不会重建（instance() 返回旧实例），
    导致功能异常。
    """
    # ── 1. 重置撤销协调器 ────────────────────────────────────────
    try:
        from components.undo_coordinator import UndoCoordinator
        if UndoCoordinator._instance is not None:
            old = UndoCoordinator._instance
            old._mw = None
            old._edit_menu = None
            old._current_undo_action = None
            old._current_redo_action = None
            old._stacks.clear()
            old._active_panel_id = None
            print("[StarDebate] 已重置 UndoCoordinator")
    except Exception as e:
        print(f"[StarDebate] ⚠ 重置 UndoCoordinator 失败: {e}")

    # ── 2. 重置快捷键管理器 ──────────────────────────────────────
    try:
        from workers.shortcuts import ShortcutManager
        if ShortcutManager._instance is not None:
            # 清除所有旧快捷键绑定
            for sid, shortcut in list(ShortcutManager._instance._active_shortcuts.items()):
                try:
                    shortcut.disconnect()
                    shortcut.deleteLater()
                except Exception:
                    pass
            ShortcutManager._instance._active_shortcuts.clear()
            ShortcutManager._instance._window = None
            ShortcutManager._instance._shortcuts.clear()
            # ★ 关键：重置单例标志，让新窗口重新初始化
            ShortcutManager._instance = None
            print("[StarDebate] 已重置 ShortcutManager")
    except Exception as e:
        print(f"[StarDebate] ⚠ 重置 ShortcutManager 失败: {e}")

    # ── 3. 清理插件系统全局状态 ─────────────────────────────────
    try:
        from workers.plugin_manager import get_manager, set_api, _safe_api
        mgr = get_manager()
        if mgr is not None:
            # 确保所有插件已禁用（closeEvent 中已处理，此处保险）
            for plugin in list(mgr.get_plugins().values()):
                try:
                    if hasattr(plugin, 'enabled') and plugin.enabled:
                        plugin.disable()
                except Exception:
                    pass
            # 不销毁 PluginManager 本身（它是模块级单例，
            # 新窗口的 __init__ 会重新 enable_all_default）
        # 清除全局 API 引用（新窗口会重新 set_api）
        import workers.plugin_manager as _pm
        _pm._safe_api = None
        print("[StarDebate] 已清理插件系统全局状态")
    except Exception as e:
        print(f"[StarDebate] ⚠ 清理插件系统失败: {e}")

    # ── 4. 清理 SVG 渲染器缓存（图标可能因主题变更而失效）──────
    try:
        from components.svg_renderer import SvgRenderer
        SvgRenderer.clear_cache()
        print("[StarDebate] 已清理 SVG 渲染器缓存")
    except Exception as e:
        print(f"[StarDebate] ⚠ 清理 SVG 缓存失败: {e}")


# ════════════════════════════════════════════════════════════════════════
#  main_loop — 外层循环：单次创建 QApp + LogService，内层重建窗口
# ════════════════════════════════════════════════════════════════════════

def main_loop():
    """主循环：管理软重启生命周期。

    QApplication 和 LogService 在此一次性创建，跨软重启保持运行。
    _start_window() 在循环内每次重启时调用，创建新的 StarDebateApp。

    更新流程：
      1. 用户确认更新后，update manager 覆盖文件
      2. QApplication.quit() 退出事件循环
      3. 此处检测到 needs_restart() → 关闭旧窗口 → 重新 _start_window()
      4. 新 StarDebateApp 检测到 "restarting" 状态 → 显示成功通知
    """
    project_root = get_resource_root()
    log_settings = _load_log_settings()
    service_cfg = log_settings.get("log_service", {})
    auto_clean_enabled = service_cfg.get("auto_clean", True)

    # ── ① 创建进程间通信队列（仅一次）─────────────────────────────
    log_queue = multiprocessing.Queue()
    result_queue = multiprocessing.Queue()

    # ── ② 创建 QApplication（仅一次）──────────────────────────────
    # QWebEngine 要求：在 Q(Gui)Application 构造前设置共享 OpenGL 上下文
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    app.setApplicationName("StarDebate")
    app.setWindowIcon(QIcon("icon/common/main.png"))
    app.setQuitOnLastWindowClosed(True)
    _apply_global_qss(app)
    _load_harmonyos_font()

    # ── ③ 初始化 SVG 渲染器（仅一次）─────────────────────────────
    from components.svg_renderer import SvgRenderer
    SvgRenderer.init(project_root)

    # ── ④ 启动 LogService 独立进程（仅一次）───────────────────────
    log_service = LogService(project_root, log_queue, result_queue,
                             auto_clean_enabled=auto_clean_enabled)
    log_service.start()

    # ── 等待 LogService 初始化 ─────────────────────────────────────
    log_path = ""
    try:
        result = result_queue.get(timeout=15)
        log_path = result.get("log_path", "")
        status = result.get("status", "error")
        if status == "error":
            print(f"[StarDebate] LogService 初始化失败: {result.get('error', '未知错误')}")
            log_path = ""
        else:
            print(f"[StarDebate] LogService 就绪 → {log_path}")
    except Exception as e:
        print(f"[StarDebate] LogService 初始化超时: {e}")
        log_path = ""

    # ── 软重启循环 ─────────────────────────────────────────────────
    restart_count = 0
    exit_code = 0

    while restart_count < _MAX_RESTART_LOOP:
        # 首次运行 / 软重启后重新创建主窗口
        exit_code = _start_window(app, log_queue, log_path, log_settings,
                                  restart_count=restart_count)

        # 检测是否需要软重启
        if needs_restart():
            restart_count += 1
            print(f"[StarDebate] 软重启 #{restart_count}/{_MAX_RESTART_LOOP}")

            # 将状态改为 restarting（供新窗口检测）
            state = read_update_state()
            state["status"] = "restarting"
            state["restart_count"] = restart_count
            write_update_state(state)

            # ★ 关闭旧窗口（避免双窗口问题）
            # app.quit() 只让 exec_() 返回，不会销毁/隐藏 QWidget
            _safe_close_all_windows(app)

            # ★ 重置全局单例（旧窗口引用必须清除）
            _reset_global_singletons()
            continue

        # 正常退出
        break

    if restart_count >= _MAX_RESTART_LOOP:
        print(f"[StarDebate] ⚠ 已达到最大重启次数 ({_MAX_RESTART_LOOP})，停止尝试")

    # ── LogService 退出清理（仅一次）───────────────────────────────
    print("[StarDebate] 正在关闭...")
    log_service.join(timeout=8)
    if log_service.is_alive():
        print("[StarDebate] LogService 未及时退出，强制终止")
        log_service.terminate()
        log_service.join(timeout=3)

    _cleanup_log(log_path)
    print(f"[StarDebate] 退出码: {exit_code}")
    sys.exit(exit_code)


# ============================================================================
# 程序入口
# ============================================================================
if __name__ == "__main__":
    multiprocessing.freeze_support()  # Windows spawn 模式必需
    main_loop()
