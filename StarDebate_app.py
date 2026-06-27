"""StarDebate ★ 辩之星 — 主应用程序窗口
============================================================================
StarDebateApp 通过多重继承组合三个职责：
  1. 管理器实例化与生命周期管理（本文件 __init__）
  2. UI 面板组装（UIAssemblyMixin → workers/star_debate/ui_assembly.py）
  3. 跨模块胶水代码（GlueCodeMixin → workers/star_debate/glue.py）

所有功能逻辑和 UI 构建已模块化至 workers/ 目录。

日志系统已完全剥离至 star_debate_log.py（独立进程）。
本文件通过 LogClient（轻量队列客户端）发送日志指令。
============================================================================
"""
import sys
import os
import json
import time
import multiprocessing

# ── PyQt5 ──────────────────────────────────────────────────────────────
from PyQt5.QtWidgets import QApplication, QMainWindow, QSplitter
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon

# ── 配置路径统一解析（持久化配置 vs 打包资源）───────────────────
from workers.app_config import get_config_path, get_packaged_path

# ── 主窗口拆分的两个 Mixin ────────────────────────────────────────────
from workers.star_debate.ui_assembly import UIAssemblyMixin
from workers.star_debate.glue import GlueCodeMixin

# ── 插件系统 ──────────────────────────────────────────────────────────
from workers.plugin_manager import get_manager as _get_plugin_manager
from workers.plugin_manager.plugin_api import PluginSafeAPI

# ── 功能模块管理器（在 _setup_ui 之前创建）──────────────────────────
from workers.app_config import AppConfigManager
from workers.ai_analysis import AIAnalysisManager
from workers.cross_examination import CrossExaminationManager, AcceptExaminationManager
from workers.speech_writer import SpeechWriterManager
from workers.ai_expand import AIExpandManager
from workers.framework import FrameworkManager
from workers.notes import NotesManager
from workers.training import TrainingManager
from workers.tournament import TournamentManager
from workers.material_pool import MaterialPoolManager
from workers.nav_bar import NavBarManager, NavRegistry
from workers.top_nav import TopNavManager, TopNavRegistry
from workers.project_explorer import ProjectExplorerManager
from workers.plugin_panel import PluginPanelManager
from workers.common import FlowLayout

# ── 扩展包管理器 ────────────────────────────────────────────────────
from workers.extension_manager import get_manager as _get_ext_manager
from workers.extension_manager.extension_api import ExtensionAPI

# ── 日志客户端（轻量，通过队列发送到独立 LogService 进程）───────────
from star_debate_log import LogClient

# ── 崩溃监控 + stderr 重定向（stderr 直写文件，崩溃安全）──────────
from workers.crash_monitor import start_crash_monitor, StderrToLogRedirector
from workers.crash_monitor import show_startup_failure_dialog as _show_startup_failure_dialog

# ── 错误卡片组件 ────────────────────────────────────────────────────
from components.error_card import ErrorCardWidget
import traceback as _tb_module

# ── 调试监视管理器（钩子投递到日志队列）───────────────────────────
try:
    from workers.debug_console.debug_monitor_manager import DebugMonitorManager
except ImportError:
    DebugMonitorManager = None  # debug_console 未打包时跳过

# ── .stardebate 编辑器管理器 ────────────────────────────────────────
from workers.stardebate_format import StardebateEditorManager, StardebateModulePanel

# ── 快捷键管理器（v3.0.0 新增）─────────────────────────────────
from workers.shortcuts import ShortcutManager

# ── 撤销/重做协调器 ────────────────────────────────────────
from components.undo_coordinator import UndoCoordinator

# ── 更新器管理器 ───────────────────────────────────────────
from workers.updater import UpdateManager

# ── 介绍与引导页管理器 ─────────────────────────────────────
from workers.welcome_guide import WelcomeGuideManager


# ============================================================================
# StarDebateApp — 主窗口（管理器实例化 + Mixin 组合）
# ============================================================================
class StarDebateApp(UIAssemblyMixin, GlueCodeMixin, QMainWindow):
    """星辩论 - 主窗口。

    通过多重继承组合：
      - UIAssemblyMixin  → _setup_ui / _build_page_* / _connect_signals
      - GlueCodeMixin    → 面板切换 / 事件处理 / 桥接方法 / 兼容属性

    本文件 __init__ 仅负责管理器实例化与生命周期管理。
    日志系统通过 LogClient 投递到独立 LogService 进程。
    """

    CONFIG_FILE = get_config_path("config/config.json")
    API_CONFIG_FILE = get_config_path("config/api_config.json")

    def __init__(self, log_queue: multiprocessing.Queue, log_path: str,
                 log_settings: dict = None,
                 startup_banner=None):
        super().__init__()
        self._startup_banner = startup_banner
        self.setWindowTitle("StarDebate - 辩之星")
        self.setWindowIcon(QIcon("icon/common/main.png"))
        self.resize(2000, 1200)
        self.setMinimumSize(900, 600)
        self.setWindowFlags(Qt.FramelessWindowHint)  # 隐藏原生标题栏，使用自定义 TitleBar
        self.setAttribute(Qt.WA_TranslucentBackground)  # 透明背景，让阴影在边距区域可见

        # 居中显示
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )

        # ── 基础状态 ─────────────────────────────────────────────────
        self._pinned_items = set()  # 被置顶的项目路径
        self.current_debate_path: str | None = None
        self.current_debate_data: dict | None = None

        # ── ★ 日志客户端（轻量队列发送）─────────────────────────────
        self._log_path = log_path
        self._log_client = LogClient(log_queue, log_path)

        # ── ★ stderr 重定向（崩溃 traceback 直写文件，不经过队列）───
        if log_path:
            self._stderr_redirector = StderrToLogRedirector(log_path)
            self._stderr_redirector.install()
        else:
            self._stderr_redirector = None

        # ── ★ 错误追踪（启动时收集加载失败的功能模块）──────────────
        self._failed_core: list[tuple[str, str, str]] = []     # [(name, desc, traceback)]
        self._failed_non_core: list[tuple[str, str, str]] = [] # [(name, desc, traceback)]
        self._session_has_error = False  # 标记本次运行是否出现过错误（用于日志保留）

        # ── 应用配置管理器（核心功能）────────────────────────────────
        self._app_cfg = self._safe_init("应用配置", AppConfigManager, self,
                                         self.CONFIG_FILE, self.API_CONFIG_FILE,
                                         category="core")

        # ── 开发者模式配置（从 config.json 读取）────────────────────
        self._disabled_features: list[str] = []
        self._load_dev_mode_config()

        # ── AI 分析管理器 ────────────────────────────────────────────
        self._analysis_mgr = self._safe_init("AI分析", AIAnalysisManager, self, category="non_core")

        # ── 模拟质询 + 接质管理器 ────────────────────────────────────
        self._cross_mgr = self._safe_init("模拟质询", CrossExaminationManager, self, category="non_core")
        self._accept_mgr = self._safe_init("模拟接质", AcceptExaminationManager, self, category="non_core")

        # ── 向后兼容：质询/接质数据 ──────────────────────────────────
        self._cross_exam_rounds: list[dict] = []
        self._accept_exam_state: str = "idle"
        self._accept_exam_user_side: str = ""
        self._accept_exam_messages: list[dict] = []
        self._accept_exam_scores: list[int] = []
        self._accept_exam_round: int = 0

        # ── 面板可见性状态 ───────────────────────────────────────────
        self._project_tree_visible: bool = True
        self._stdb_browser_visible: bool = False

        # ── AI写稿管理器 ─────────────────────────────────────────────
        self._speech_writer_mgr = self._safe_init("AI写稿", SpeechWriterManager, self, category="non_core")
        SpeechWriterManager._FlowLayout = FlowLayout

        # ── AI扩写管理器 ─────────────────────────────────────────────
        self._ai_expand_mgr = self._safe_init("AI扩写", AIExpandManager, self, category="non_core")
        AIExpandManager._FlowLayout = FlowLayout

        # ── 辩论框架管理器 ───────────────────────────────────────────
        self._framework_mgr = self._safe_init("辩论框架", FrameworkManager, self, category="non_core")

        # ── 便签管理器 ───────────────────────────────────────────────
        self._notes_mgr = self._safe_init("便签", NotesManager, self, category="non_core")

        # ── 模拟训练管理器 ───────────────────────────────────────────
        self._train_mgr = self._safe_init("模拟训练", TrainingManager, self, category="non_core")

        # ── 扩展包管理器 ───────────────────────────────────────────────
        self._ext_mgr = _get_ext_manager()
        self._ext_api = ExtensionAPI()
        from workers.extension_manager import set_api as _set_ext_api
        _set_ext_api(self._ext_api)
        self._ext_api.set_context(self, "__main__")
        self._ext_panel_mgr = None  # 延迟创建
        self._ext_page_idx = -1

        # ── 素材池管理器 ───────────────────────────────────────────────
        self._material_pool_mgr = self._safe_init("素材池", MaterialPoolManager, self, category="non_core")

        # ── 赛程管理器 ────────────────────────────────────────────────
        self._tournament_mgr = self._safe_init("赛程", TournamentManager, self, category="non_core")

        # ── 导航栏注册系统 ───────────────────────────────────────────
        self._nav_registry = NavRegistry()
        self._nav_registry.load()
        self._nav_mgr = self._safe_init("导航栏", NavBarManager, self, self._nav_registry, category="core")

        # ── 顶部导航栏注册系统（使用菜单配置文件）─────────────────
        self._top_nav_registry = TopNavRegistry("config/menu_main_window.json")
        self._top_nav_registry.load()
        self._top_nav_mgr = self._safe_init("顶部导航栏", TopNavManager, self, self._top_nav_registry, category="core")

        # ── 注册模块按钮构建器（管理器可能为None，用try保护）───────
        _module_builders = [
            ("speech_writer", "_speech_writer_mgr"),
            ("ai_expand", "_ai_expand_mgr"),
            ("notes", "_notes_mgr"),
            ("training", "_train_mgr"),
            ("cross_examination", "_cross_mgr"),
            ("accept_examination", "_accept_mgr"),
            ("material_pool", "_material_pool_mgr"),
        ]
        for name, attr in _module_builders:
            mgr = getattr(self, attr, None)
            if mgr is not None:
                self._nav_mgr.register_module_builder(name, lambda m=mgr: m.build_nav_button())
            else:
                self._nav_mgr.register_module_builder(name, lambda: QWidget())

        # ── 插件系统（核心功能）──────────────────────────────────────
        self._plugins_visible: bool = False
        self._plugin_manager = _get_plugin_manager()
        self._plugin_api = PluginSafeAPI()
        from workers.plugin_manager import set_api as _set_plugin_api
        _set_plugin_api(self._plugin_api)
        self._plugin_api.set_context(self, "__main__")
        try:
            self._plugin_manager.enable_all_default()
        except Exception as e:
            tb_str = _tb_module.format_exc()
            self._failed_core.append(("插件系统", str(e)[:200], tb_str))
            self._log_client.error(f"[INIT] 插件系统启用失败: {e}")

        # ── 插件注册面板容器 ─────────────────────────────────────────
        self._plugin_left_stack = None
        self._plugin_right_stack = None
        self._plugin_panels_data: dict = {}
        self._plugin_active_panel: dict = {"left": None, "right": None}
        self._plugin_center_pages: list[dict] = []
        self._plugin_panel_btns: dict = {}

        # ── 项目树管理器 ─────────────────────────────────────────────
        self._project_explorer = self._safe_init("项目树", ProjectExplorerManager, self, category="core")

        # ── 插件面板管理器 ───────────────────────────────────────────
        self._plugin_panel_mgr = self._safe_init("插件面板", PluginPanelManager, self, category="non_core")

        # ── 扩展包管理器引用（供 GlueCodeMixin 使用）─────────────────
        self._ext_panel_visible = False

        # ── ★ 启动日志记录 ──────────────────────────────────────────
        self._init_logging_startup()

        # ── ★ 启动起居注自动追踪钩子 ──────────────────────────────
        self._init_chronicle()

        # ── ★ 启动底层事件记录系统 (Native Event Logging) ─────────
        self._init_native_events()

        # ── ★ 初始化调试监视管理器（绑定日志队列）───────────────────
        self._init_monitor_manager(log_queue, log_path)

        # ── ★ 应用统一日志配置（log_settings.json → 各子系统）──────
        self._apply_log_settings(log_settings)

        # ── ★ 启动崩溃监控进程 ──────────────────────────────────────
        self._init_crash_monitor()

        # ── ★ 快捷键管理器（v3.0.0 新增）─────────────────────────
        self._shortcut_mgr = ShortcutManager.instance(self)

        # ── ★ 加载已启用的扩展包（阶段 D 后、阶段 E 前）────────────
        #     在所有管理器就绪后、UI 构建前加载，允许扩展现有 UI
        try:
            self._ext_mgr.enable_all_default()
            enabled_count = sum(1 for e in self._ext_mgr.get_all() if e.enabled)
            if enabled_count > 0:
                self._log_client.info(f"[EXT] 已加载 {enabled_count} 个扩展包")
        except Exception as e:
            self._log_client.error(f"[EXT] 扩展包加载失败: {e}")

        # ── ★ 检查核心功能是否全部加载成功 ─────────────────────
        #     如果有核心功能失败，致命退出（不显示主窗口）
        if self._failed_core:
            self._session_has_error = True
            self._auto_keep_log()
            # 关闭崩溃监控（避免触发崩溃弹出独立弹窗）
            self._shutdown_crash_monitor_quiet()
            # 记录日志
            self._log_client.error(
                "核心功能加载失败，无法启动: "
                + "; ".join(f"{n}: {d}" for n, d, _ in self._failed_core)
            )
            # 显示启动失败弹窗
            failures = [(n, d) for n, d, _ in self._failed_core]
            _show_startup_failure_dialog(
                self._log_path or "",
                __import__("components.res_path", fromlist=["get_resource_root"]).get_resource_root(),
                failures,
            )
            # 退出进程
            QApplication.quit()
            sys.exit(1)

        # ── ★ 阶段 5/7 → 实际映射至阶段 6/7：构建 UI ────────────
        #   (阶段 5 已在 StarDebate.py 中声明为 "正在加载功能模块...")
        if self._startup_banner:
            self._startup_banner.set_progress(6, 7, "正在构建用户界面...")

        # ── ★ 介绍与引导页管理器（必须在 _setup_ui 之前创建）───────
        self._welcome_guide_mgr = self._safe_init(
            "介绍与引导页", WelcomeGuideManager, self, self._app_cfg,
            category="non_core"
        )

        # ── 构建 UI（UIAssemblyMixin._setup_ui）───────────────────────
        self._setup_ui()

        # ── ★ 启动后检测是否显示引导页 ──────────────────────────
        if self._welcome_guide_mgr is not None:
            QTimer.singleShot(800, self._welcome_guide_mgr.check_and_show)

        # ── .stardebate 编辑器管理器初始化 ────────────────────────────
        self._stdb_editor_mgr = self._safe_init(
            ".stardebate编辑器", StardebateEditorManager, self, category="non_core"
        )

        if self._stdb_editor_mgr is not None:
            # 创建模块浏览面板
            self._stdb_module_panel = StardebateModulePanel(self._stdb_editor_mgr)
            self._stdb_module_panel.setVisible(False)
            self._stdb_editor_mgr.set_module_panel(self._stdb_module_panel)

            # 将面板插入左侧垂直分栏（与项目树/结构树/赛程同列）
            hsplitter = self.findChildren(QSplitter)[0]
            left_vsplit = hsplitter.widget(0)  # left_vsplit 在 splitter 索引 0
            if left_vsplit:
                left_vsplit.addWidget(self._stdb_module_panel)
                left_vsplit.setStretchFactor(left_vsplit.count() - 1, 1)

            # ── 连接模块选择信号
            self._stdb_module_panel.module_selected.connect(
                lambda fp, mid: self._stdb_editor_mgr.open_module_editor(fp, mid)
            )
        else:
            self._stdb_module_panel = None

        # ── 样式和配置文件加载 ───────────────────────────────────────
        if self._startup_banner:
            self._startup_banner.set_progress(7, 7, "正在应用主题配置...")
        if self._app_cfg is not None:
            self._app_cfg.apply_style()
            self._app_cfg.auto_load_last_project()
        if self._tournament_mgr is not None:
            self._tournament_mgr.load_competition_formats()
        if self._train_mgr is not None:
            self._train_mgr.refresh_format_combo()

        # ── ★ 快捷键注册与应用（v3.0.0 新增）───────────────────
        self._init_shortcuts()

        # ── ★ 自动加载已保存的 .stardebate 文件 ─────────────────────────
        #     必须在 auto_load_last_project 之后执行，
        #     否则项目树会被 tree.clear() 清空已添加的 .stardebate 节点。
        #     STDB 面板默认关闭，点击项目树文件时自动展开。
        try:
            self._stdb_editor_mgr.auto_load_saved_files()
            if self._stdb_editor_mgr.open_files:
                self._log_client.info(
                    f"自动加载 .stardebate: {len(self._stdb_editor_mgr.open_files)} 个文件"
                )
        except Exception as e:
            self._log_client.warn(f".stardebate 自动加载失败: {e}")

        # ── ★ 窗口可见性自动恢复 ──────────────────────────────────
        #     定时检测：若窗口意外隐藏超过 8 秒，尝试恢复显示
        self._last_visible_time = time.time()
        self._visibility_timer = QTimer(self)
        self._visibility_timer.setInterval(4000)  # 每 4 秒检测一次
        self._visibility_timer.timeout.connect(self._check_window_visibility)
        self._visibility_timer.start()
        # ── ★ 撤销/重做协调器初始化 ──────────────────────────────
        coordinator = UndoCoordinator.instance()
        coordinator.initialize(self)
        self._undo_coordinator = coordinator

        # ── ★ 更新器管理器初始化（非核心功能）─────────────────────
        self._updater_mgr = self._safe_init("更新器", UpdateManager, self, category="non_core")
        if self._updater_mgr is not None:
            self._updater_mgr.inject_log_client(self._log_client)

        # ── centre_stack 页面切换 → 激活对应面板的撤销栈 ─────
        self.centre_stack.currentChanged.connect(self._on_center_page_changed)

        # ── ★ 非核心功能加载失败检查 ────────────────────────────
        #     如果有非核心功能失败 → 显示错误卡片 + 警告对话框
        if self._failed_non_core:
            self._session_has_error = True
            self._auto_keep_log()
            self._log_client.warn(
                "部分功能加载失败: "
                + "; ".join(f"{n}: {d}" for n, d, _ in self._failed_non_core)
            )
            # 填充错误卡片
            self._populate_error_card()
            # 弹出警告对话框（在主窗口显示后立即弹出）
            QTimer.singleShot(500, self._show_non_fatal_warning_dialog)

        # ── ★ 启用 .stp 拖拽安装 ──────────────────────────────────
        self.setAcceptDrops(True)

        # ── ★ 启动时自动检测更新补丁 ─────────────────────────────
        if self._updater_mgr is not None:
            QTimer.singleShot(1000, self._updater_mgr.check_on_startup)

        # ── ★ 从 config 恢复导航栏标签显示状态 ────────────────
        QTimer.singleShot(0, self._apply_nav_labels_from_config)

    # ═══════════════════════════════════════════════════════════════
    #  开发者模式配置
    # ═══════════════════════════════════════════════════════════════

    def _apply_nav_labels_from_config(self):
        """启动时从 config.json 读取 show_nav_labels 并应用到导航栏。"""
        if not hasattr(self, '_nav_mgr') or self._nav_mgr is None:
            return
        try:
            from workers.app_config.config_paths import get_config_path
            cfg_path = get_config_path("config/config.json")
            if not os.path.isfile(cfg_path):
                return
            with open(cfg_path, "r", encoding="utf-8") as f:
                import json
                data = json.load(f)
            visible = data.get("show_nav_labels", True)
            self._nav_mgr.set_labels_visible(visible)
        except Exception:
            pass

    def _load_dev_mode_config(self):
        """从 config.json 读取开发者模式配置，存入 self._disabled_features。"""
        try:
            import json
            from workers.app_config.config_paths import get_config_path
            cfg_path = get_config_path("config/config.json")
            if os.path.isfile(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                dev_mode = cfg.get("developer_mode", False)
                self._disabled_features = (
                    [] if dev_mode else cfg.get("disabled_features", [])
                )
            self._log_client.info(
                f"开发者模式: {'开启' if not self._disabled_features else '关闭'} "
                f"(禁用: {self._disabled_features or '无'})"
            )
        except Exception as e:
            self._log_client.warn(f"读取开发者模式配置失败: {e}")
            self._disabled_features = []

    # ═══════════════════════════════════════════════════════════════
    #  安全初始化 + 错误追踪 (v4.0.0)
    # ═══════════════════════════════════════════════════════════════

    def _safe_init(self, display_name: str, manager_class, *args,
                   category: str = "non_core", **kwargs) -> object:
        """安全初始化管理器，捕获异常并分类收集。

        Args:
            display_name: 显示名称（用于错误提示）
            manager_class: 管理器类
            *args: 管理器构造参数
            category: "core" 或 "non_core"
            **kwargs: 管理器构造关键字参数

        Returns:
            初始化成功返回管理器实例，失败返回 None
        """
        try:
            return manager_class(*args, **kwargs)
        except Exception as e:
            tb_str = _tb_module.format_exc()
            short_desc = f"{e}"[:200]
            entry = (display_name, short_desc, tb_str)
            if category == "core":
                self._failed_core.append(entry)
            else:
                self._failed_non_core.append(entry)
            self._log_client.error(f"[INIT] {display_name} 初始化失败: {short_desc}")
            return None

    def _populate_error_card(self):
        """将非核心功能加载失败的条目填充到错误卡片。"""
        error_card = getattr(self, '_error_card', None)
        if error_card is None:
            return
        for name, desc, tb_str in self._failed_non_core:
            error_card.add_error(name, desc, tb_str)

    def _show_non_fatal_warning_dialog(self):
        """显示非致命错误警告对话框（可恢复）。"""
        from components.popup_dialog import CustomDialog

        count = len(self._failed_non_core)
        msg = (
            f"有 {count} 个功能模块加载失败。\n\n"
            + "\n".join(f"• {n}: {d}" for n, d, _ in self._failed_non_core[:6])
            + ("\n…" if count > 6 else "")
            + "\n\n您可以继续使用其他功能，或重启应用修复。"
        )

        result = CustomDialog(
            self, "部分功能加载失败",
            msg,
            buttons=[("立即重启", "restart"), ("继续使用", "continue")],
            icon_path=None,  # 显示默认警告图标
        )
        result_text = getattr(result, "_result", "continue")
        if result_text == "restart":
            self._restart_application()

    def _restart_application(self):
        """重新启动应用（兼容 EXE 与源码两种环境）。"""
        self._log_client.info("[INIT] 用户选择重启应用")
        try:
            self._close_logging_and_monitor()
        except Exception:
            pass
        try:
            if getattr(sys, 'frozen', False):
                # EXE 版：直接重新执行自身（boot.py 已设置好 sys.path + cwd）
                os.execl(sys.executable, sys.executable)
            else:
                # 源码版：用 Python 解释器运行当前脚本
                os.execl(sys.executable, sys.executable, os.path.abspath(__file__))
        except Exception:
            QApplication.quit()
            sys.exit(0)

    def _auto_keep_log(self):
        """自动设置本次运行的日志保留标记（复用 log keep 命令逻辑）。"""
        log_cfg_path = get_config_path("config/log_settings.json")
        try:
            with open(log_cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if not cfg.get("log_service", {}).get("keep_normal_exit_log", False):
                cfg.setdefault("log_service", {})["keep_normal_exit_log"] = True
                with open(log_cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                self._log_client.info("[INIT] 已自动标记日志保留（检测到加载错误）")
        except Exception:
            pass

    def _shutdown_crash_monitor_quiet(self):
        """安静关闭崩溃监控（致命错误退出前调用）。"""
        try:
            if hasattr(self, '_crash_monitor_event') and self._crash_monitor_event:
                self._crash_monitor_event.set()
            if hasattr(self, '_crash_monitor_process') and self._crash_monitor_process:
                self._crash_monitor_process.join(timeout=2)
                if self._crash_monitor_process.is_alive():
                    self._crash_monitor_process.terminate()
        except Exception:
            pass

    def _close_logging_and_monitor(self):
        """清理日志和监控（在重启/退出前统一调用）。"""
        # 关闭崩溃监控
        self._shutdown_crash_monitor_quiet()
        # 关闭日志
        try:
            if hasattr(self, '_log_client') and self._log_client:
                self._log_client.shutdown()
        except Exception:
            pass
        # 卸载 stderr 重定向
        try:
            if hasattr(self, '_stderr_redirector') and self._stderr_redirector:
                self._stderr_redirector.uninstall()
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════
    #  重试初始化方法（供 ErrorCard 重试时调用）
    # ═══════════════════════════════════════════════════════════════

    def _reinit_ai_analysis(self):
        """重新初始化 AI分析 管理器（重试用）。"""
        try:
            self._analysis_mgr = AIAnalysisManager(self)
            self._analysis_mgr.build_ui()
            self._log_client.info("[RETRY] AI分析 重试成功")
        except Exception as e:
            self._log_client.error(f"[RETRY] AI分析 重试失败: {e}")
            raise

    def _reinit_cross_exam(self):
        try:
            self._cross_mgr = CrossExaminationManager(self)
            self._cross_mgr.build_ui()
            self._log_client.info("[RETRY] 模拟质询 重试成功")
        except Exception as e:
            self._log_client.error(f"[RETRY] 模拟质询 重试失败: {e}")
            raise

    def _reinit_accept_exam(self):
        try:
            self._accept_mgr = AcceptExaminationManager(self)
            self._accept_mgr.build_ui()
            self._log_client.info("[RETRY] 模拟接质 重试成功")
        except Exception as e:
            self._log_client.error(f"[RETRY] 模拟接质 重试失败: {e}")
            raise

    def _reinit_speech_writer(self):
        try:
            self._speech_writer_mgr = SpeechWriterManager(self)
            SpeechWriterManager._FlowLayout = FlowLayout
            self._log_client.info("[RETRY] AI写稿 重试成功")
        except Exception as e:
            self._log_client.error(f"[RETRY] AI写稿 重试失败: {e}")
            raise

    def _reinit_ai_expand(self):
        try:
            self._ai_expand_mgr = AIExpandManager(self)
            AIExpandManager._FlowLayout = FlowLayout
            self._log_client.info("[RETRY] AI扩写 重试成功")
        except Exception as e:
            self._log_client.error(f"[RETRY] AI扩写 重试失败: {e}")
            raise

    def _reinit_framework(self):
        try:
            from workers.framework import FrameworkManager
            self._framework_mgr = FrameworkManager(self)
            self._framework_mgr.build_ui()
            self._log_client.info("[RETRY] 辩论框架 重试成功")
        except Exception as e:
            self._log_client.error(f"[RETRY] 辩论框架 重试失败: {e}")
            raise

    def _reinit_notes(self):
        try:
            self._notes_mgr = NotesManager(self)
            self._log_client.info("[RETRY] 便签 重试成功")
        except Exception as e:
            self._log_client.error(f"[RETRY] 便签 重试失败: {e}")
            raise

    def _reinit_training(self):
        try:
            self._train_mgr = TrainingManager(self)
            self._log_client.info("[RETRY] 模拟训练 重试成功")
        except Exception as e:
            self._log_client.error(f"[RETRY] 模拟训练 重试失败: {e}")
            raise

    def _reinit_material_pool(self):
        try:
            self._material_pool_mgr = MaterialPoolManager(self)
            self._material_pool_mgr.set_centre_stack(self.centre_stack)
            self._log_client.info("[RETRY] 素材池 重试成功")
        except Exception as e:
            self._log_client.error(f"[RETRY] 素材池 重试失败: {e}")
            raise

    def _reinit_tournament(self):
        try:
            self._tournament_mgr = TournamentManager(self)
            self._tournament_mgr.load_competition_formats()
            self._log_client.info("[RETRY] 赛程 重试成功")
        except Exception as e:
            self._log_client.error(f"[RETRY] 赛程 重试失败: {e}")
            raise

    def dragEnterEvent(self, event):
        """拖拽进入：识别 .stp 文件"""
        from PyQt5.QtGui import QDragEnterEvent
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".stp"):
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event):
        """放下文件：安装 .stp"""
        if not event.mimeData().hasUrls():
            return
        from workers.stp_installer.stp_installer import STPInstaller
        installer = STPInstaller(self)
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if not filepath.lower().endswith(".stp"):
                continue
            if not installer.is_stp_file(filepath):
                from components.popup_dialog import CustomDialog
                CustomDialog.warning(self, "拖拽安装失败", "不是有效的 .stp 文件")
                continue
            # 读取 manifest
            manifest = installer.get_manifest_from_stp(filepath)
            if not manifest:
                from components.popup_dialog import CustomDialog
                CustomDialog.warning(self, "拖拽安装失败", "无法读取插件包信息")
                continue
            # 显示预览对话框
            from workers.stp_installer.install_preview import STPInstallPreview
            missing_deps = installer.check_dependencies(manifest)
            conflict = installer.check_conflict(manifest)
            compat_ok, compat_msg = installer.check_version_compatibility(manifest)
            preview = STPInstallPreview(
                self, manifest, missing_deps,
                conflict, compat_ok, compat_msg,
            )
            if preview.exec_() != STPInstallPreview.Accepted:
                continue
            conflict_mode = preview.get_conflict_mode()
            if conflict_mode == "cancel":
                continue
            result = installer.install(filepath, conflict_mode=conflict_mode)
            if result["success"]:
                self._update_status(
                    f"✅ 插件 \"{manifest.get('name', '')}\" 安装完成。"
                )
                # 刷新插件面板
                if hasattr(self, '_plugin_panel_mgr'):
                    self._plugin_panel_mgr.refresh_list()
                    self._plugin_panel_mgr._refresh_nav_buttons()
                    if hasattr(self, '_train_mgr'):
                        self._train_mgr.refresh_sub_features_ui()
            else:
                from components.popup_dialog import CustomDialog
                CustomDialog.warning(self, "拖拽安装失败",
                                    result.get("error", "未知错误"))

    def _check_window_visibility(self):
        """检测窗口可见性，意外隐藏时自动恢复。

        场景：某些 Qt 内部错误或 excepthook 副作用可能使窗口变为不可见
        但进程仍在运行。此时自动调用 show() 恢复。
        
        注意：最小化 (isMinimized=True) 是正常状态，不触发恢复。
        """
        try:
            # 最小化 = 正常操作，不干扰
            if self.isMinimized():
                self._last_visible_time = time.time()
                return

            if self.isVisible():
                self._last_visible_time = time.time()
                return

            # 窗口不可见且未最小化 → 可能是异常隐藏
            hidden_duration = time.time() - self._last_visible_time
            if hidden_duration >= 8:
                self._log_client.warn(
                    "[RECOVERY] 窗口异常隐藏 {:0.0f}s，尝试恢复显示...".format(hidden_duration)
                )
                try:
                    self.show()
                    self.raise_()
                    self.activateWindow()
                    self._last_visible_time = time.time()
                    self._log_client.info("[RECOVERY] 窗口已恢复显示")
                except Exception as e:
                    self._log_client.error(f"[RECOVERY] 恢复失败: {e}")
        except Exception:
            pass  # 安静失败，不干扰 UI 线程



    # ═══════════════════════════════════════════════════
    #  快捷键初始化（v3.0.0 新增）
    # ═══════════════════════════════════════════════════

    def _init_shortcuts(self):
        """注册内置快捷键回调并应用全局快捷键。
        已为所有可能为None的管理器添加Null保护。
        """
        callbacks = {
            # 通用
            "open_settings":       self._open_settings_dialog,
            "new_debate":          self._on_new_debate_trigger,
            "save_debate":         self._on_save_debate_trigger,
            "toggle_sidebar":      self._toggle_project_tree,
            "close_tab":           self._on_close_tab_trigger,
            "search_project":      self._on_search_project_trigger,
            "open_project":        self._on_open_project,
            # 写稿（管理器可能为None）
            "ai_expand":           lambda: self._ai_expand_mgr.trigger_expand() if self._ai_expand_mgr else None,
            "framework_analyze":   lambda: self._framework_mgr.trigger_analyze() if self._framework_mgr else None,
            "speech_writer_pro":   lambda: self._speech_writer_mgr.switch_side("pro") if self._speech_writer_mgr else None,
            "speech_writer_con":   lambda: self._speech_writer_mgr.switch_side("con") if self._speech_writer_mgr else None,
            # 训练（管理器可能为None）
            "quick_quiz":          lambda: self._train_mgr.switch_to_quiz() if self._train_mgr else None,
            "cross_examination":   self._open_cross_examination,
            "start_training":      lambda: self._train_mgr.start_current() if self._train_mgr else None,
            # AI分析（管理器可能为None）
            "ai_analysis_pro":     lambda: self._analysis_mgr.analyze("pro") if self._analysis_mgr else None,
            "ai_analysis_con":     lambda: self._analysis_mgr.analyze("con") if self._analysis_mgr else None,
            # 赛程（管理器可能为None）
            "new_tournament":      self._on_new_tournament_trigger,
        }

        # 开发者模式过滤：禁用功能不注册快捷键
        if "debug_console" not in self._disabled_features:
            callbacks["toggle_debug_console"] = self._toggle_debug_console

        # 扩展包管理快捷键
        callbacks["open_extension_manager"] = self._toggle_extension_panel

        self._shortcut_mgr.load_builtin_defaults(callbacks)
        self._shortcut_mgr.apply_all()
        self._shortcut_mgr.set_monitor_fn(self._log_client.info)
        self._log_client.info("[SHORTCUT] 快捷键系统已初始化")

    def _open_settings_dialog(self):
        """打开设置对话框"""
        try:
            from workers.settings import SettingsDialog
            ver = self._app_cfg.get_app_version()
            dlg = SettingsDialog(self, app_version=ver, theme_change_callback=self._app_cfg.switch_theme)
            dlg.exec_()
        except Exception:
            pass

    def _toggle_debug_console(self):
        """切换调试控制台（开发者模式保护）"""
        if "debug_console" in self._disabled_features:
            return
        try:
            self._top_nav_mgr._toggle_debug_console()
        except Exception:
            pass

    def _on_new_debate_trigger(self):
        """新建辩论"""
        try:
            self._top_nav_mgr._on_new_debate()
        except Exception:
            pass

    def _on_save_debate_trigger(self):
        """保存当前辩论"""
        try:
            if hasattr(self, '_framework_mgr') and hasattr(self._framework_mgr, 'save_current'):
                self._framework_mgr.save_current()
        except Exception:
            pass

    def _on_close_tab_trigger(self):
        """关闭当前标签"""
        try:
            centre = getattr(self, "centre_stack", None)
            if centre:
                idx = centre.currentIndex()
                if idx >= 0:
                    w = centre.widget(idx)
                    if w:
                        centre.removeWidget(w)
                        w.deleteLater()
        except Exception:
            pass

    def _on_search_project_trigger(self):
        """搜索项目"""
        try:
            if hasattr(self, '_project_explorer'):
                self._project_explorer.focus_search()
        except Exception:
            pass




    def _open_cross_examination(self):
        """打开模拟质询（管理器可能为None）"""
        try:
            if self._cross_mgr is not None:
                self._cross_mgr.start_examination()
        except Exception:
            pass

    def _on_new_tournament_trigger(self):
        """新建赛程（管理器可能为None）"""
        try:
            if self._tournament_mgr is not None:
                self._tournament_mgr.open_new_tournament()
        except Exception:
            pass

    # ═══════════════════════════════════════════════════
    #  启动日志记录
    # ═══════════════════════════════════════════════════

    def _init_logging_startup(self):
        """记录启动信息到日志服务。"""
        from components.res_path import get_resource_root
        project_root = get_resource_root()

        self._log_client.info("═══ StarDebate 启动 ═══")

        # 记录版本和主题（_app_cfg可能为None）
        try:
            if self._app_cfg is not None:
                ver = self._app_cfg.get_app_version()
                self._log_client.info(f"版本: {ver}")
        except Exception:
            pass
        try:
            if self._app_cfg is not None:
                theme = self._app_cfg.get_theme_name()
                self._log_client.info(f"主题: {theme}")
        except Exception:
            pass

        if self._log_path:
            self._log_client.info(f"日志文件: {self._log_path}")
            self._log_client.info(f"日志服务: 独立进程 (LogService)")

    # ═══════════════════════════════════════════════════
    #  起居注自动追踪 (ActivityChronicle)
    # ═══════════════════════════════════════════════════

    def _init_chronicle(self):
        """注入起居注自动追踪钩子 (v2.0.0 增强)。

        通过 monkey-patch 自动记录:
          - 插件加载/卸载 (PluginInfo.enable/disable)
          - API 调用 (monitored_api_post)
          - AI 调用 (PluginSafeAPI.call_ai)
          - ★ Qt 内部消息 (qInstallMessageHandler)
          - ★ Worker 线程异常 (QThread Worker)

        所有钩子不修改源文件，关闭时可完全恢复。
        标签: [CRON]
        """
        try:
            from workers.debug_console.chronicle import install_chronicle
            self._chronicle_refs = install_chronicle(self._log_client)
        except ImportError:
            self._chronicle_refs = {}

        # ★ v2.0.0: Qt message handler 已在 QApplication 创建后安装
        # （通过 chronicle_patcher._install_qt_handler + LogClient.install_qt_handler 双重保障）

        self._log_client.info("[CRON] 起居注自动追踪已启用 (v2.0.0)")
        self._log_client.info(
            "[CRON] 追踪范围: 插件/API/AI/Qt错误/Worker线程  "
            "+ traceback + 守护日志环 + 崩溃分析"
        )

    # ═══════════════════════════════════════════════════
    #  底层事件记录系统 (Native Event Logging)
    # ═══════════════════════════════════════════════════

    def _init_native_events(self):
        """启动底层事件记录系统 (Native Event Logging) — M3 完整版。

        在起居注初始化之后调用，安装全部钩子 + 监视器 + 桥接器:

        [钩子] M1: Qt handler / excepthook
        [钩子] M2: unraisablehook / audithook / gc.callbacks / c_exception
        [监视] M3: NativeThreadMonitor (4 类线程检测)
        [监视] M3: NativeResourceMonitor (fd/Qt 孤儿/atexit)
        [桥接] M3: NativeChronicleBridge (重大事件 → CRON context)
        """
        try:
            from workers.debug_console.native import (
                NativeEventManager, install_native_hooks,
                NativeThreadMonitor, NativeResourceMonitor,
                NativeChronicleBridge,
            )
        except ImportError:
            self._native_event_mgr = None
            self._native_hook_refs = None
            self._native_thread_monitor = None
            self._native_resource_monitor = None
            self._native_chronicle_bridge = None
            self._log_client.info("[NATIVE] 底层事件系统: debug_console 未打包，跳过")
            return

        try:
            from components.res_path import get_resource_root
            project_root = get_resource_root()
            self._native_event_mgr = NativeEventManager(
                project_root,
                log_client=self._log_client,
            )
            self._native_hook_refs = install_native_hooks(self._native_event_mgr)

            # ── M3: 线程健康监视器 ────────────────────────────
            self._native_thread_monitor = NativeThreadMonitor(
                self._native_event_mgr
            )
            self._native_thread_monitor.start()

            # ── M3: 资源跟踪监视器 ────────────────────────────
            self._native_resource_monitor = NativeResourceMonitor(
                self._native_event_mgr
            )
            self._native_resource_monitor.install()

            # ── M3: 起居注桥接器 ──────────────────────────────
            self._native_chronicle_bridge = NativeChronicleBridge(
                self._native_event_mgr, self._log_client
            )
            self._native_chronicle_bridge.install()

            # ── M3: Qt 主循环心跳（线程监视器驱动）───────────
            try:
                from PyQt5.QtCore import QTimer
                self._native_qt_heartbeat_timer = QTimer(self)
                self._native_qt_heartbeat_timer.timeout.connect(
                    self._native_thread_monitor.set_qt_heartbeat
                )
                self._native_qt_heartbeat_timer.start(1000)
            except Exception:
                pass

            # ── 延迟健康检查（30 秒后）───────────────────────
            try:
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(30000, self._native_event_mgr.health_check)
            except Exception:
                pass

            self._log_client.info(
                "[NATIVE] 底层事件记录系统已启用 (v1.2.0 M3)"
            )
            self._log_client.info(
                "[NATIVE] 钩子: Qt/excepthook/unraisable/audit/gc/c_exception"
            )
            self._log_client.info(
                "[NATIVE] 监视: 线程健康/资源跟踪/起居注桥接"
            )
            self._log_client.info(
                f"[NATIVE] SQLite: {self._native_event_mgr.db_path}"
            )

        except Exception as e:
            self._log_client.error(
                f"[NATIVE] 底层事件系统初始化失败: {e}"
            )
            self._native_event_mgr = None
            self._native_hook_refs = None
            self._native_thread_monitor = None
            self._native_resource_monitor = None
            self._native_chronicle_bridge = None

    # ═══════════════════════════════════════════════════
    #  调试监视管理器初始化
    # ═══════════════════════════════════════════════════

    def _init_monitor_manager(self, log_queue, log_path):
        """初始化调试监视管理器，绑定日志队列。

        监视钩子通过队列投递到 LogService，队列满/断时自动降级
        为文件直写（由 LogClient 内部的 _emergency_write 处理）。
        """
        from components.res_path import get_resource_root
        project_root = get_resource_root()
        if DebugMonitorManager is not None:
            self._monitor_mgr = DebugMonitorManager.instance(project_root)
            # 绑定日志队列（替代原来的 LogManager 引用）
            self._monitor_mgr.set_log_queue(log_queue, log_path)
        else:
            self._monitor_mgr = None

        # 记录当前配置状态
        if self._monitor_mgr is not None and self._monitor_mgr.enabled:
            active = self._monitor_mgr.get_active_monitors()
            self._log_client.info(f"调试监视已开启: {', '.join(active) if active else '无'}")
        else:
            self._log_client.info("调试监视: 已关闭（可在调试台中开启）")

    # ═══════════════════════════════════════════════════
    #  应用统一日志配置到各子系统
    # ═══════════════════════════════════════════════════

    def _apply_log_settings(self, log_settings: dict):
        """将 log_settings.json 统一配置应用到运行时子系统。

        启动时调用一次，确保 DebugMonitorManager、ActivityChronicle
        等子系统与 log_settings.json 保持一致。
        """
        if not log_settings:
            self._log_client.info("[CFG] 未加载 log_settings.json，使用各子系统默认配置")
            return

        self._log_client.info("[CFG] 已加载 log_settings.json，开始同步运行时配置")

        # ── ① 总开关 ─────────────────────────────────
        master_enabled = log_settings.get("master_enabled", True)

        # ── ② 同步 DebugMonitorManager ────────────────
        monitor_cfg = log_settings.get("debug_monitor", {})
        monitor_enabled = master_enabled and monitor_cfg.get("enabled", False)

        if hasattr(self, '_monitor_mgr') and self._monitor_mgr:
            self._monitor_mgr.enabled = monitor_enabled
            for mtype, enabled in monitor_cfg.get("monitors", {}).items():
                self._monitor_mgr.set_monitor(mtype, enabled)

            # 同步高级选项
            self._monitor_mgr._config.setdefault("options", {})
            self._monitor_mgr._config["options"]["function_min_duration_ms"] = (
                monitor_cfg.get("function_min_duration_ms", 0)
            )
            self._monitor_mgr._save_config()

            if monitor_enabled:
                active = self._monitor_mgr.get_active_monitors()
                self._log_client.info(f"[CFG] 调试监视: 已开启 → {', '.join(active) if active else '无'}")
            else:
                self._log_client.info("[CFG] 调试监视: 已关闭")

        # ── ③ 同步 ActivityChronicle ──────────────────
        chronicle_cfg = log_settings.get("chronicle", {})
        chronicle_enabled = master_enabled and chronicle_cfg.get("enabled", True)

        if hasattr(self, '_log_client') and self._log_client:
            self._log_client.chronicle_enabled = chronicle_enabled
            # 同步 chronicle_config.json
            try:
                chronicle_config_path = get_config_path("config/chronicle_config.json")
                chronicle_config = {
                    "enabled": chronicle_enabled,
                    "categories": chronicle_cfg.get("categories_active", {}),
                    "min_duration_ms": chronicle_cfg.get("min_duration_ms", 0),
                    "log_level": "INFO",
                }
                os.makedirs(os.path.dirname(chronicle_config_path), exist_ok=True)
                with open(chronicle_config_path, "w", encoding="utf-8") as f:
                    json.dump(chronicle_config, f, indent=4, ensure_ascii=False)
            except Exception:
                pass

            if chronicle_enabled:
                self._log_client.info("[CFG] 起居注: 已开启")
            else:
                self._log_client.info("[CFG] 起居注: 已关闭")

        self._log_client.info("[CFG] log_settings.json 同步完成")

    # ═══════════════════════════════════════════════════
    #  崩溃监控进程
    # ═══════════════════════════════════════════════════

    def _init_crash_monitor(self):
        """启动崩溃监控独立进程。"""
        self._crash_monitor_event = None
        self._crash_monitor_process = None
        try:
            current_pid = os.getpid()
            log_path = self._log_path or ""
            from components.res_path import get_resource_root
            project_root = get_resource_root()
            self._crash_monitor_event, self._crash_monitor_process = start_crash_monitor(
                current_pid, log_path, project_root
            )
            self._log_client.info(f"崩溃监控已启动 (PID: {current_pid})")
        except Exception as e:
            self._log_client.warn(f"崩溃监控启动失败: {e}")

    # ═══════════════════════════════════════════════════
    #  生命周期
    # ═══════════════════════════════════════════════════

    def closeEvent(self, event):
        """窗口关闭前清理资源，最后通过 super() 通知 GlueCodeMixin 保存文件与关闭插件。

        清理顺序（从表层到依赖底层，再委托上层）：
        1. 停止定时器 / 断开信号
        2. 记录会话错误状态
        3. 禁用单插件 → 清理撤销栈
        4. 卸载调试钩子 / 监视器
        5. 关闭日志客户端
        → super() → GlueCodeMixin 保存 .stardebate / 关闭插件管理器 / 恢复 stderr / 停止崩溃监控
        """
        # ── 1. 停止定时器 + 断开信号 ──────────────────────────
        try:
            if hasattr(self, '_visibility_timer') and self._visibility_timer:
                self._visibility_timer.stop()
                self._visibility_timer = None
        except Exception:
            pass

        try:
            if hasattr(self, 'centre_stack') and self.centre_stack:
                try:
                    self.centre_stack.currentChanged.disconnect(self._on_center_page_changed)
                except Exception:
                    pass
        except Exception:
            pass

        # ── 2. 日志：本次会话是否有加载错误 ───────────────────
        if getattr(self, '_session_has_error', False):
            try:
                if hasattr(self, '_log_client') and self._log_client:
                    self._log_client.info(
                        "[EXIT] 本次运行存在功能加载错误，日志已保留"
                    )
            except Exception:
                pass

        # ── 3. 禁用所有插件（释放对旧窗口的引用）──────────────
        try:
            if hasattr(self, '_plugin_manager') and self._plugin_manager:
                for plugin in list(self._plugin_manager.get_plugins().values()):
                    try:
                        plugin.disable()
                    except Exception:
                        pass
        except Exception:
            pass

        # ── 4. 清理撤销协调器 ────────────────────────────────
        try:
            if hasattr(self, '_undo_coordinator') and self._undo_coordinator:
                coord = self._undo_coordinator
                stacks_to_remove = [
                    k for k, v in coord._stacks.items()
                    if v is not None
                ]
                for key in stacks_to_remove:
                    try:
                        del coord._stacks[key]
                    except Exception:
                        pass
                coord._active_panel_id = None
                coord._mw = None
        except Exception:
            pass

        # ── 5. 卸载起居注钩子 ────────────────────────────────
        try:
            if hasattr(self, '_chronicle_refs') and self._chronicle_refs:
                from workers.debug_console.chronicle import uninstall_chronicle
                uninstall_chronicle(self._chronicle_refs)
        except Exception:
            pass

        # ── 6. 卸载全局异常钩子 ───────────────────────────────
        try:
            if hasattr(self, '_log_client') and self._log_client:
                self._log_client.uninstall_global_hooks()
        except Exception:
            pass

        # ── 7. 停止 Qt 主循环心跳计时器 ───────────────────────
        try:
            if hasattr(self, '_native_qt_heartbeat_timer'):
                self._native_qt_heartbeat_timer.stop()
        except Exception:
            pass

        # ── 8. 卸载起居注桥接器 ───────────────────────────────
        try:
            if hasattr(self, '_native_chronicle_bridge'):
                self._native_chronicle_bridge.uninstall()
        except Exception:
            pass

        # ── 9. 停止资源监视器 ────────────────────────────────
        try:
            if hasattr(self, '_native_resource_monitor'):
                self._native_resource_monitor.uninstall()
        except Exception:
            pass

        # ── 10. 停止线程监视器 ───────────────────────────────
        try:
            if hasattr(self, '_native_thread_monitor'):
                self._native_thread_monitor.stop()
        except Exception:
            pass

        # ── 11. 卸载底层事件钩子 ──────────────────────────────
        try:
            if hasattr(self, '_native_hook_refs') and self._native_hook_refs:
                from workers.debug_console.native import uninstall_native_hooks
                uninstall_native_hooks(self._native_hook_refs)
        except Exception:
            pass

        # ── 12. 关闭 SQLite 管理器 ────────────────────────────
        try:
            if hasattr(self, '_native_event_mgr') and self._native_event_mgr:
                self._native_event_mgr.close()
                self._log_client.info("[NATIVE] 底层事件系统已关闭")
        except Exception:
            pass

        # ── 13. 通知 LogService 正常退出 ──────────────────────
        try:
            if hasattr(self, '_log_client') and self._log_client:
                chronicle_snap = {}
                ring_data = []
                try:
                    chronicle_snap = self._log_client.chronicle.get_crash_snapshot()
                    ring_data = self._log_client.dump_ring_buffer()
                except Exception:
                    pass

                self._log_client.set_emergency_info(
                    self._log_client.emergency_count,
                    self._log_client.last_heartbeat,
                    chronicle_snapshot=chronicle_snap if chronicle_snap else None,
                    ring_buffer_data=ring_data if ring_data else None,
                )
                self._log_client.info("═══ StarDebate 正常关闭 ═══")
                self._log_client.shutdown()
        except Exception:
            pass

        # ══════════════════════════════════════════════════════
        # ★ super() → GlueCodeMixin.closeEvent:
        #   保存 .stardebate / 关闭插件管理器 / 恢复 stderr / 停止崩溃监控
        # ══════════════════════════════════════════════════════
        super().closeEvent(event)

