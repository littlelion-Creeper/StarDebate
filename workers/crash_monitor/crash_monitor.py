"""奔溃弹窗 — 独立进程监控 + stderr 重定向 + 崩溃弹窗

CrashMonitor 进程职责：
  - 接收主进程 PID 和日志文件路径
  - 每 1 秒检测主进程是否存活
  - 主进程异常退出时弹出 CrashPopup 弹窗
  - 主进程正常退出（通过 Event 通知）时静默退出

StderrToLogRedirector：
  - 替换 sys.stderr，将 Python 错误输出同步写入日志文件
  - 直接写文件路径（无中间层），确保崩溃时数据可靠落盘
"""

import os
import re
import sys
import io
import time
import ctypes
import multiprocessing
from typing import Optional, Tuple

from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QFontDatabase
from PyQt5.QtSvg import QSvgRenderer


# ════════════════════════════════════════════════════════════
#  stderr → 日志文件 重定向器（直接写文件，不依赖 LogManager）
# ════════════════════════════════════════════════════════════

class StderrToLogRedirector(io.TextIOBase):
    """将 sys.stderr 的输出直接写入日志文件。

    Python 异常 traceback 默认输出到 stderr。
    安装后所有错误信息会同时：
      1. 写入原始 stderr（终端可见）
      2. 直接追加写入日志文件路径（绕过中间层，崩溃时可靠）
    """

    def __init__(self, log_file_path: str):
        super().__init__()
        self._log_path = log_file_path
        self._original_stderr = sys.stderr
        self._buffer = ""

    def install(self):
        """安装重定向：替换 sys.stderr。"""
        sys.stderr = self

    def uninstall(self):
        """卸载重定向：恢复原始 stderr 并冲刷缓冲区。"""
        self.flush()
        sys.stderr = self._original_stderr

    def write(self, s: str) -> int:
        # 写入原始 stderr（终端保留输出）
        if self._original_stderr is not None:
            written = self._original_stderr.write(s)
            self._original_stderr.flush()
        else:
            written = len(s)

        # 累积行，每遇到完整行就写入日志文件
        self._buffer += s
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip("\r")
            if line.strip():  # 跳过纯空行
                self._write_to_log(line)

        return written

    def flush(self):
        if self._original_stderr is not None:
            self._original_stderr.flush()
        # 冲刷缓冲区中的残留内容
        if self._buffer.strip():
            self._write_to_log(self._buffer.rstrip("\r\n"))
            self._buffer = ""

    # 匹配已格式化的日志行：[HH:MM:SS.mmm] [LEVEL] ...
    _MONITOR_LINE_RE = re.compile(
        r'^\[\d{2}:\d{2}:\d{2}\.\d{3}\]\s'
        r'\[(INFO|WARN|ERROR|DEBUG|VAR|FUNC|API|AI|PLUGIN|MON|ATH|CFG|SYS|CRON)\b'
    )

    def _write_to_log(self, line: str):
        """直接写文件（open → write → close，确保即时落盘）。

        对已含时间戳+级别的格式化监视行，直接写入不再附加 [ERROR]。
        """
        if not self._log_path:
            return
        try:
            if self._MONITOR_LINE_RE.match(line):
                # 来自 _monitor() 的预格式化行，直接写入
                entry = f"{line}\n"
            else:
                now = time.strftime("%H:%M:%S")
                timestamp = f"{now}.{int(time.time() * 1000) % 1000:03d}"
                entry = f"[{timestamp}] [ERROR] {line}\n"
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass

    def fileno(self):
        if self._original_stderr is not None:
            return self._original_stderr.fileno()
        raise OSError("原始 stderr 不可用")

    def readable(self):
        return False

    def seekable(self):
        return False


# ════════════════════════════════════════════════════════════
#  监控进程入口
# ════════════════════════════════════════════════════════════

def _monitor_main(pid: int, log_path: str, project_root: str, stop_event: multiprocessing.Event):
    """监控进程的主函数（在子进程中运行）。

    Args:
        pid: 主进程 PID
        log_path: 本次运行的日志文件完整路径
        project_root: 项目根目录
        stop_event: 正常退出的停止信号
    """
    try:
        # 等待主进程完全启动（避免启动期间误判）
        time.sleep(2)

        poll_interval = 1.0  # 每秒检查一次
        max_consecutive_misses = 3  # 连续3次检测不到才判定崩溃

        consecutive_miss = 0
        crashed = False

        while not stop_event.is_set():
            alive = _is_process_alive(pid)

            if not alive:
                consecutive_miss += 1
                if consecutive_miss >= max_consecutive_misses:
                    crashed = True
                    break
            else:
                consecutive_miss = 0

            # 带超时的 wait，避免永久阻塞
            stop_event.wait(timeout=poll_interval)

        # 如果崩溃且不是正常退出信号触发的
        if crashed and not stop_event.is_set():
            _show_crash_popup(log_path, project_root)
    except Exception as e:
        # 子进程异常时写入 stderr 方便调试
        sys.stderr.write(f"[CrashMonitor] 监控进程异常: {e}\n")
        sys.stderr.flush()


def _is_process_alive(pid: int) -> bool:
    """检查指定 PID 的进程是否存活。

    Windows: 使用 kernel32 OpenProcess + GetExitCodeProcess
    Linux/macOS: os.kill(pid, 0)
    """
    if sys.platform != 'win32':
        try:
            os.kill(pid, 0)
            return True
        except (OSError, PermissionError):
            return False

    # ── Windows: kernel32 API ──────────────────────────
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259

    try:
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if handle == 0 or handle is None:
            return False

        exit_code = ctypes.c_ulong()
        result = ctypes.windll.kernel32.GetExitCodeProcess(
            handle, ctypes.byref(exit_code)
        )
        ctypes.windll.kernel32.CloseHandle(handle)

        if result == 0:
            return False
        return exit_code.value == STILL_ACTIVE
    except Exception:
        return False


# ════════════════════════════════════════════════════════════
#  崩溃弹窗（独立进程中的 PyQt 窗口）
# ════════════════════════════════════════════════════════════

def _show_crash_popup(log_path: str, project_root: str):
    """在独立进程中显示崩溃弹窗。

    Args:
        log_path: 日志文件路径
        project_root: 项目根目录
    """
    # ★ 仅设 OS 级 DPI 感知（不设 AA_EnableHighDpiScaling）
    # 让 setFixedSize(530, 380) 按物理像素精确渲染，取消 Windows 位图缩放
    if sys.platform == "win32":
        try:
            for _aware in (2, 1):
                try:
                    ctypes.windll.shcore.SetProcessDpiAwareness(_aware)
                    break
                except Exception:
                    continue
            else:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("StarDebate Crash Monitor")

    # 加载 HarmonyOS Sans SC 字体
    font_dir = os.path.join(project_root, "style", "font", "HarmonyOS_SansSC")
    font_path = os.path.join(font_dir, "HarmonyOS_SansSC_Regular.ttf")
    if os.path.isfile(font_path):
        fid = QFontDatabase.addApplicationFont(font_path)
        if fid >= 0:
            app.setFont(QFont("HarmonyOS Sans SC", 10))

    # 加载 QSS 样式
    qss = _load_crash_monitor_qss(project_root)
    if qss:
        app.setStyleSheet(qss)

    popup = CrashPopup(log_path, project_root)
    popup.show()
    popup.raise_()
    popup.activateWindow()

    sys.exit(app.exec_())


def show_startup_failure_dialog(log_path: str, project_root: str,
                                 failures: list[tuple[str, str]]):
    """在主进程中显示启动失败弹窗（不创建新进程）。

    当核心功能初始化失败、主界面无法显示时调用。
    显示后用户关闭退出进程。

    Args:
        log_path: 日志文件路径
        project_root: 项目根目录
        failures: [(模块名, 错误描述), ...]
    """
    # 加载 QSS 样式
    qss = _load_crash_monitor_qss(project_root)
    app = QApplication.instance()
    if app and qss:
        app.setStyleSheet(qss)

    popup = CrashPopup(log_path, project_root, startup_failures=failures)
    popup.exec_()


def _load_crash_monitor_qss(project_root: str) -> str:
    """加载奔溃弹窗 QSS 样式（跟随当前主题）。"""
    try:
        import json
        from workers.app_config.config_paths import get_config_path
        config_path = get_config_path("config/config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        theme_name = config.get("theme", "catppuccin_mocha")
        qss_dir = os.path.join(project_root, "style", "themes", theme_name)
        qss_path = os.path.join(qss_dir, "crash_monitor.qss")

        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        pass
    return ""


class CrashPopup(QDialog):
    """程序崩溃弹窗。

    显示崩溃信息、日志文件路径，提供打开文件夹和复制日志功能。
    """

    def __init__(self, log_path: str, project_root: str, parent=None,
                 startup_failures: list[tuple[str, str]] = None):
        """初始化崩溃弹窗。

        Args:
            log_path: 日志文件路径
            project_root: 项目根目录
            parent: 父窗口
            startup_failures: 启动失败列表 [(模块名, 错误描述), ...]
                             传入此参数时弹窗为"启动失败"模式而非"崩溃"模式。
        """
        super().__init__(parent)
        self._log_path = log_path
        self._project_root = project_root
        self._startup_failures = startup_failures or []

        is_startup_fail = bool(self._startup_failures)
        title = "StarDebate - 启动失败" if is_startup_fail else "StarDebate - 程序崩溃检测"

        self.setWindowTitle(title)
        self.setFixedSize(530, 440 if is_startup_fail else 380)
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Dialog
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setObjectName("crashPopup")

        # 设置对话框 QSS（border-radius 替代 setMask，避免 Windows DPI 下遮罩冲突）
        self.setStyleSheet("""
            #crashPopup {
                background-color: #1e1e2e;
                border: 1px solid #45475a;
                border-radius: 10px;
            }
            #crashTitleBar {
                background-color: #181825;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            #crashCloseBtn {
                background: transparent;
                border: none;
                color: #cdd6f4;
                font-size: 16px;
                border-radius: 4px;
            }
            #crashCloseBtn:hover {
                background: #f38ba8;
                color: #1e1e2e;
            }
            #crashContent {
                background-color: #1e1e2e;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
            }
            #crashLogCard {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 8px;
            }
            #crashPopup QLabel {
                color: #cdd6f4;
            }
            #crashOpenFolderBtn, #crashCopyBtn {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 6px;
                color: #cdd6f4;
                font-size: 12px;
                padding: 6px 14px;
            }
            #crashOpenFolderBtn:hover, #crashCopyBtn:hover {
                background-color: #45475a;
            }
        """)

        # 居中显示
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )

        self._setup_ui()

        # 延迟应用窗口圆角（等 show() 后 winId 有效）
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self._apply_window_rounded_corners)

    # ── 工具方法 ──────────────────────────────────────────

    def _load_svg_pixmap(self, svg_name: str, size: int = 24,
                         color: str = None) -> QPixmap:
        """加载 icon/common/ 下 SVG 文件，渲染为指定大小并可选着色。

        Args:
            svg_name: SVG 文件名（含后缀）
            size: 目标像素大小
            color: 着色 hex 色值（如 "#f38ba8"），为 None 时保留原色
        """
        icon_dir = os.path.join(self._project_root, "icon", "common")
        svg_path = os.path.join(icon_dir, svg_name)
        if not os.path.isfile(svg_path):
            return QPixmap()
        renderer = QSvgRenderer(svg_path)
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        if painter.isActive():
            renderer.render(painter)
            painter.end()

        if color:
            # 使用 SourceIn 合成模式将透明度遮罩保留，填充为目标色
            colored = QPixmap(size, size)
            colored.fill(Qt.transparent)
            painter = QPainter(colored)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setCompositionMode(QPainter.CompositionMode_Source)
            painter.drawPixmap(0, 0, pix)
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(colored.rect(), QColor(color))
            painter.end()
            pix = colored

        return pix

    # ── UI 构建 ──────────────────────────────────────────

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 自定义标题栏 ──────────────────────────────
        title_bar = QFrame()
        title_bar.setObjectName("crashTitleBar")
        title_bar.setFixedHeight(42)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 12, 0)
        title_layout.setSpacing(0)

        # 标题左侧 StarDebate 星标 SVG
        title_icon = QLabel()
        title_icon.setObjectName("crashTitleIcon")
        title_icon.setFixedWidth(30)
        title_pix = self._load_svg_pixmap("main.svg", 20)
        if not title_pix.isNull():
            title_icon.setPixmap(title_pix)
            title_icon.setFixedWidth(24)
        else:
            title_icon.setText("★")
        title_layout.addWidget(title_icon)

        title_label = QLabel("StarDebate - 程序崩溃检测")
        title_label.setObjectName("crashTitleLabel")
        title_layout.addWidget(title_label)

        title_layout.addStretch()

        # 关闭按钮 ×（保留文字形式，hover 变色效果更清晰）
        close_btn = QPushButton("✕")
        close_btn.setObjectName("crashCloseBtn")
        close_btn.setFixedSize(36, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        title_layout.addWidget(close_btn)

        main_layout.addWidget(title_bar)

        # ── 内容区域 ──────────────────────────────────
        content = QFrame()
        content.setObjectName("crashContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 24, 28, 24)
        content_layout.setSpacing(16)

        # ── 警告图标 + 标题 ──────────────────────────────
        warn_row = QHBoxLayout()
        warn_row.setSpacing(12)
        warn_icon = QLabel()
        warn_icon.setObjectName("crashWarnIcon")
        warn_icon.setFixedWidth(40)
        warn_icon.setAlignment(Qt.AlignCenter)
        warn_pix = self._load_svg_pixmap("warning.svg", 28, color="#f38ba8")
        if not warn_pix.isNull():
            warn_icon.setPixmap(warn_pix)
        else:
            warn_icon.setText("⚠")
        warn_row.addWidget(warn_icon)

        if self._startup_failures:
            warn_text = QLabel("核心功能初始化失败，无法继续运行")
            warn_text.setObjectName("crashWarnText")
            warn_text.setWordWrap(True)
            warn_row.addWidget(warn_text, 1)
            content_layout.addLayout(warn_row)

            # 失败模块列表
            fail_list = QFrame()
            fail_list.setObjectName("crashLogCard")
            fail_layout = QVBoxLayout(fail_list)
            fail_layout.setContentsMargins(12, 10, 12, 10)
            fail_layout.setSpacing(4)
            for mod_name, err_desc in self._startup_failures:
                line = QLabel(f"• {mod_name}: {err_desc}")
                line.setObjectName("crashDesc")
                line.setWordWrap(True)
                fail_layout.addWidget(line)
            content_layout.addWidget(fail_list)

            # 说明
            desc = QLabel(
                "以下是本次运行的日志文件，可帮助诊断问题："
            )
            desc.setObjectName("crashDesc")
            desc.setWordWrap(True)
            content_layout.addWidget(desc)
        else:
            warn_text = QLabel("检测到主程序异常退出")
            warn_text.setObjectName("crashWarnText")
            warn_text.setWordWrap(True)
            warn_row.addWidget(warn_text, 1)
            content_layout.addLayout(warn_row)

            # 说明文字
            desc = QLabel(
                "程序似乎意外崩溃了。以下是本次运行的日志文件，"
                "可帮助诊断问题："
            )
            desc.setObjectName("crashDesc")
            desc.setWordWrap(True)
            content_layout.addWidget(desc)

        # 日志文件信息卡片
        log_card = QFrame()
        log_card.setObjectName("crashLogCard")
        log_card_layout = QVBoxLayout(log_card)
        log_card_layout.setContentsMargins(16, 14, 16, 14)
        log_card_layout.setSpacing(6)

        # 文件名行
        log_name_row = QHBoxLayout()
        log_name_row.setSpacing(8)
        log_icon = QLabel()
        log_icon.setObjectName("crashLogIcon")
        log_icon.setFixedWidth(24)
        log_icon.setText("📄")
        log_name_row.addWidget(log_icon)

        log_name = QLabel(os.path.basename(self._log_path) if self._log_path else "（无日志文件）")
        log_name.setObjectName("crashLogName")
        log_name.setWordWrap(True)
        log_name_row.addWidget(log_name, 1)
        log_card_layout.addLayout(log_name_row)

        # 完整路径
        log_path_label = QLabel(self._log_path if self._log_path else "日志文件路径不可用")
        log_path_label.setObjectName("crashLogPath")
        log_path_label.setWordWrap(True)
        log_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        log_card_layout.addWidget(log_path_label)

        content_layout.addWidget(log_card)

        # ── 操作按钮 ──────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        open_folder_btn = QPushButton("  打开日志文件夹")
        open_folder_btn.setObjectName("crashOpenFolderBtn")
        open_folder_btn.setCursor(Qt.PointingHandCursor)
        folder_pix = self._load_svg_pixmap("folder.svg", 16, color="#cdd6f4")
        if not folder_pix.isNull():
            open_folder_btn.setIcon(QIcon(folder_pix))
            open_folder_btn.setIconSize(folder_pix.size())
        open_folder_btn.clicked.connect(self._on_open_log_folder)
        open_folder_btn.setMinimumHeight(36)
        btn_row.addWidget(open_folder_btn)

        copy_btn = QPushButton("复制日志到剪贴板")
        copy_btn.setObjectName("crashCopyBtn")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.clicked.connect(self._on_copy_log)
        copy_btn.setMinimumHeight(36)
        btn_row.addWidget(copy_btn)

        content_layout.addLayout(btn_row)

        content_layout.addStretch()

        main_layout.addWidget(content, 1)

    # ── 操作回调 ──────────────────────────────────────────

    def _on_open_log_folder(self):
        """打开日志文件夹。"""
        log_dir = os.path.dirname(self._log_path) if self._log_path else ""
        if log_dir and os.path.isdir(log_dir):
            try:
                os.startfile(log_dir)
            except Exception:
                pass
        elif self._project_root:
            # 回退：打开项目 docs/log 目录
            fallback = os.path.join(self._project_root, "docs", "log")
            if os.path.isdir(fallback):
                try:
                    os.startfile(fallback)
                except Exception:
                    pass

    def _on_copy_log(self):
        """复制日志内容到剪贴板。"""
        if self._log_path and os.path.exists(self._log_path):
            try:
                with open(self._log_path, "r", encoding="utf-8") as f:
                    content = f.read()
                QApplication.clipboard().setText(content)
            except Exception:
                QApplication.clipboard().setText(
                    f"无法读取日志文件: {self._log_path}"
                )
        else:
            QApplication.clipboard().setText("日志文件不可用")

    # ── 窗口圆角 ──────────────────────────────────────────

    def _apply_window_rounded_corners(self):
        """使用 Windows 11 DWM 原生圆角（不依赖 setMask，无 DPI 缩放问题）。"""
        if sys.platform != "win32":
            return
        try:
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = 2
            hwnd = int(self.winId())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(ctypes.c_int(DWMWCP_ROUND)),
                ctypes.sizeof(ctypes.c_int),
            )
        except Exception:
            pass

    # ── 窗口事件 ──────────────────────────────────────────

    def mousePressEvent(self, event):
        """标题栏拖拽移动。"""
        if event.y() < 42 and event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if hasattr(self, '_drag_pos') and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if hasattr(self, '_drag_pos'):
            del self._drag_pos
        super().mouseReleaseEvent(event)


# ════════════════════════════════════════════════════════════
#  公共 API
# ════════════════════════════════════════════════════════════

def start_crash_monitor(pid: int, log_path: str, project_root: str) -> Tuple[multiprocessing.Event, multiprocessing.Process]:
    """启动崩溃监控进程。

    Args:
        pid: 主进程 PID
        log_path: 本次运行的日志文件完整路径
        project_root: 项目根目录

    Returns:
        (stop_event, monitor_process):
          - stop_event: 用于通知监控进程正常退出的 Event
          - monitor_process: 监控进程对象
    """
    # 验证参数
    if not log_path:
        log_path = ""

    stop_event = multiprocessing.Event()

    process = multiprocessing.Process(
        target=_monitor_main,
        args=(pid, log_path, project_root, stop_event),
        name="StarDebate-CrashMonitor",
        daemon=False,  # 非守护进程：主进程崩溃时仍存活，才能弹出崩溃窗口
    )

    process.start()

    return stop_event, process
