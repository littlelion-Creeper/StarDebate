from components.theme_colors import tc, refresh
"""调试台主窗口 — DebugConsoleWindow

提供运行时日志查看、命令输入执行、日志导出/清理、调试模式监视等功能。
独立弹出窗口，带自定义 TitleBar，支持边缘拖拽缩放。
标题栏「调试 ▼」菜单可进入调试模式设置。
"""

import sys
import os
import json
import ctypes
from typing import Optional
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QTextEdit, QLineEdit, QComboBox, QFrame,
    QCheckBox, QSizePolicy, QMenu, QAction, QApplication,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QEvent, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QTextCursor, QColor, QKeyEvent, QTextCharFormat, QTextDocument

from components.title_bar import TitleBar
from components.star_button import StarButton
from .log_manager import LogManager
from .command_handler import CommandHandler
from .suggest_popup import SuggestPopup
from .debug_monitor_manager import DebugMonitorManager, MONITOR_TYPES, MONITOR_LABELS
from .debug_mode_dialog import DebugModeDialog


class DebugConsoleWindow(QDialog):
    """调试台独立窗口"""

    # 窗口关闭信号
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔧 调试台 - StarDebate")
        self.resize(820, 560)
        self.setMinimumSize(500, 380)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)

        # 居中于父窗口
        if parent:
            pg = parent.geometry()
            self.move(
                pg.x() + (pg.width() - self.width()) // 2,
                pg.y() + (pg.height() - self.height()) // 2,
            )

        # ── 日志管理器（复用主窗口后台日志实例）─────────────────
        from components.res_path import get_resource_root
        project_root = get_resource_root()
        self._reused_logger = False

        if parent and hasattr(parent, "_bg_log_mgr") and parent._bg_log_mgr is not None:
            # ★ 复用启动时创建的 LogManager，只挂载 UI 回调
            self._log_mgr = parent._bg_log_mgr
            self._reused_logger = True
        else:
            # 回退：独立创建（如 parent 不是 StarDebateWindow）
            self._log_mgr = LogManager(project_root)

        self._log_mgr.set_log_callback(self._on_log_entry)

        # 存储到主窗口引用中（供命令执行访问）
        if parent:
            parent._debug_log_mgr = self._log_mgr

        # ── 调试监视管理器（单例，复用已有）──────────────
        self._monitor_mgr = DebugMonitorManager.instance(project_root)
        # 确保绑定当前日志管理器（可能是复用的）
        self._monitor_mgr.set_log_manager(self._log_mgr)
        self._monitor_mgr.config_changed.connect(self._on_monitor_config_changed)

        # ── 命令处理器 ──────────────────────────────────────
        self._cmd_handler = CommandHandler()
        self._refresh_plugin_commands()  # 加载插件注册的命令

        # ── 状态 ───────────────────────────────────────────
        self._paused: bool = False
        self._auto_scroll: bool = True
        self._log_level_index: int = 0  # 0=DEBUG, 1=INFO, 2=WARN, 3=ERROR
        self._pending_entries: list[str] = []
        self._timer_seconds: int = 0
        self._timer: Optional[QTimer] = None
        self._main_window = parent

        # ── 构建 UI ─────────────────────────────────────────
        self._setup_ui()
        self._load_style()

        # ── 启动日志 ────────────────────────────────────────
        self._log_mgr.info("═══ StarDebate 调试台界面已打开 ═══")

        # 仅在新建日志时输出系统信息（复用时不重复）
        if not self._reused_logger:
            if parent and hasattr(parent, "_app_cfg"):
                try:
                    ver = parent._app_cfg.get_app_version()
                    self._log_mgr.info(f"StarDebate 版本: {ver}")
                except Exception:
                    self._log_mgr.info("StarDebate 版本: 未知")
                try:
                    theme = parent._app_cfg.get_theme_name()
                    self._log_mgr.info(f"当前主题: {theme}")
                except Exception:
                    pass

            self._log_mgr.info(f"日志文件: {self._log_mgr.log_path}")

            # 自动清理旧日志
            cleaned = self._log_mgr.auto_clean()
            if cleaned > 0:
                self._log_mgr.info(f"自动清理: 已删除 {cleaned} 个过期日志文件（>7天）")
            else:
                self._log_mgr.info("自动清理: 无过期日志文件")

        # ── 聚焦命令输入 ────────────────────────────────────
        QTimer.singleShot(100, lambda: self._cmd_input.setFocus())

    # ═══════════════════════════════════════════════════
    #  UI 构建
    # ═══════════════════════════════════════════════════

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 自定义标题栏 ──
        self._title_bar = TitleBar(self, "调试台", "🔧")
        main_layout.addWidget(self._title_bar)

        # ★ 标题栏注入「调试 ▼」菜单按钮
        self._btn_debug_menu = StarButton("调试 ▼", self, layout_mode="text_only", ratio_h=0.7)
        self._btn_debug_menu.setObjectName("debugTitleMenuBtn")
        self._debug_menu = QMenu(self)
        self._debug_menu.setObjectName("debugMonitorMenu")
        self._setup_debug_menu()
        self._btn_debug_menu.clicked.connect(self._on_show_debug_menu)
        self._title_bar.get_menu_section().addWidget(self._btn_debug_menu)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(10, 6, 10, 6)
        toolbar.setSpacing(8)

        self._btn_clear = StarButton("清空", self, layout_mode="text_only", ratio_h=0.7)
        self._btn_clear.setObjectName("debugToolBtn")
        self._btn_clear.setToolTip("清空当前日志显示区")
        self._btn_clear.clicked.connect(self._on_clear)
        toolbar.addWidget(self._btn_clear)

        self._btn_pause = StarButton("⏸ 暂停", self, layout_mode="text_only", ratio_h=0.7, checkable=True)
        self._btn_pause.setObjectName("debugToolBtn")
        self._btn_pause.setToolTip("暂停/恢复日志刷新")
        self._btn_pause.clicked.connect(self._on_toggle_pause)
        toolbar.addWidget(self._btn_pause)

        toolbar.addSpacing(12)

        # 自动滚动
        self._chk_auto_scroll = QCheckBox("自动滚动")
        self._chk_auto_scroll.setObjectName("debugCheckBox")
        self._chk_auto_scroll.setChecked(True)
        self._chk_auto_scroll.setCursor(Qt.PointingHandCursor)
        self._chk_auto_scroll.toggled.connect(self._on_toggle_auto_scroll)
        toolbar.addWidget(self._chk_auto_scroll)

        # 日志级别
        lbl_level = QLabel("级别:")
        lbl_level.setObjectName("debugLbl")
        toolbar.addWidget(lbl_level)

        self._cmb_level = QComboBox()
        self._cmb_level.setObjectName("debugCombo")
        self._cmb_level.addItems(["DEBUG", "INFO", "WARN", "ERROR"])
        self._cmb_level.setCurrentIndex(1)  # 默认 INFO
        self._cmb_level.setCursor(Qt.PointingHandCursor)
        self._cmb_level.currentIndexChanged.connect(self._on_level_changed)
        toolbar.addWidget(self._cmb_level)

        toolbar.addStretch()

        # 导出日志
        self._btn_export = StarButton("导出日志", self, layout_mode="text_only", ratio_h=0.7)
        self._btn_export.setObjectName("debugToolBtn")
        self._btn_export.setToolTip("导出当前会话日志到文件")
        self._btn_export.clicked.connect(self._on_export_log)
        toolbar.addWidget(self._btn_export)

        # 清理旧日志
        self._btn_clean = StarButton("清理旧日志", self, layout_mode="text_only", ratio_h=0.7)
        self._btn_clean.setObjectName("debugToolBtn")
        self._btn_clean.setToolTip("手动删除超过7天的旧日志文件")
        self._btn_clean.clicked.connect(self._on_clean_logs)
        toolbar.addWidget(self._btn_clean)

        toolbar_widget = QWidget()
        toolbar_widget.setObjectName("debugToolbar")
        toolbar_widget.setLayout(toolbar)
        main_layout.addWidget(toolbar_widget)

        # ── 监视状态指示条 ──
        self._monitor_bar = QWidget()
        self._monitor_bar.setObjectName("debugMonitorBar")
        monitor_bar_layout = QHBoxLayout(self._monitor_bar)
        monitor_bar_layout.setContentsMargins(10, 3, 10, 3)
        monitor_bar_layout.setSpacing(8)

        self._monitor_icon_label = QLabel("🔍")
        self._monitor_icon_label.setObjectName("monitorBarIcon")
        self._monitor_icon_label.setFont(QFont("Microsoft YaHei", 10))
        monitor_bar_layout.addWidget(self._monitor_icon_label)

        self._monitor_text_label = QLabel("监视: 未开启")
        self._monitor_text_label.setObjectName("monitorBarText")
        self._monitor_text_label.setFont(QFont("Microsoft YaHei", 9))
        monitor_bar_layout.addWidget(self._monitor_text_label, 1)

        self._btn_stop_all_monitors = StarButton("停止全部监视", self, layout_mode="text_only", ratio_h=0.7)
        self._btn_stop_all_monitors.setObjectName("debugToolBtn")
        self._btn_stop_all_monitors.clicked.connect(self._on_disable_all_monitors)
        self._btn_stop_all_monitors.setVisible(False)
        monitor_bar_layout.addWidget(self._btn_stop_all_monitors)

        self._monitor_bar.setVisible(False)
        main_layout.addWidget(self._monitor_bar)

        # ── 日志输出区（右键菜单） ──
        self._log_output = QTextEdit()
        self._log_output.setObjectName("textEdit")
        self._log_output.setReadOnly(True)
        self._log_output.setFont(QFont("Consolas", 10))
        self._log_output.setLineWrapMode(QTextEdit.WidgetWidth)
        self._log_output.setContextMenuPolicy(Qt.CustomContextMenu)
        self._log_output.customContextMenuRequested.connect(self._on_output_context_menu)
        main_layout.addWidget(self._log_output, 1)

        # ── 搜索栏（默认隐藏，Ctrl+F 切换） ──
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(10, 2, 10, 2)
        search_layout.setSpacing(4)
        self._search_edit = QLineEdit()
        self._search_edit.setObjectName("lineEdit")
        self._search_edit.setPlaceholderText("搜索输出... (Enter 下一个, Esc 关闭)")
        self._search_edit.setFont(QFont("Consolas", 10))
        self._search_edit.setVisible(False)
        self._search_edit.returnPressed.connect(self._on_search_next)
        self._search_edit.installEventFilter(self)
        search_layout.addWidget(self._search_edit, 1)
        self._search_btn_close = StarButton("✕", self, layout_mode="text_only", ratio_h=0.7, auto_size=False)
        self._search_btn_close.setObjectName("debugSearchBtn")
        self._search_btn_close.setFixedSize(24, 24)
        self._search_btn_close.setVisible(False)
        self._search_btn_close.clicked.connect(self._toggle_search_bar)
        search_layout.addWidget(self._search_btn_close)
        self._search_bar_widget = QWidget()
        self._search_bar_widget.setObjectName("debugSearchBar")
        self._search_bar_widget.setLayout(search_layout)
        self._search_bar_widget.setVisible(False)
        main_layout.addWidget(self._search_bar_widget)

        # ── 命令输入区 ──
        cmd_layout = QHBoxLayout()
        cmd_layout.setContentsMargins(10, 6, 10, 8)
        cmd_layout.setSpacing(6)

        cmd_prompt = QLabel(">")
        cmd_prompt.setObjectName("debugPrompt")
        cmd_prompt.setFont(QFont("Consolas", 11, QFont.Bold))
        cmd_layout.addWidget(cmd_prompt)

        self._cmd_input = QLineEdit()
        self._cmd_input.setObjectName("lineEdit")
        self._cmd_input.setPlaceholderText("输入命令，输入 help 查看帮助...")
        self._cmd_input.setFont(QFont("Consolas", 11))
        self._cmd_input.returnPressed.connect(self._on_execute_command)
        self._cmd_input.textChanged.connect(self._on_input_text_changed)
        self._cmd_input.installEventFilter(self)
        cmd_layout.addWidget(self._cmd_input, 1)

        # ── 命令自动补全悬浮框（基于命令树）──
        self._suggest_popup = SuggestPopup(self, self._cmd_input)
        self._suggest_popup._main_window = self._main_window

        self._btn_execute = StarButton("执行", self, layout_mode="text_only", ratio_h=0.7)
        self._btn_execute.setObjectName("debugExecuteBtn")
        self._btn_execute.setToolTip("执行命令 (Enter)")
        self._btn_execute.clicked.connect(self._on_execute_command)
        cmd_layout.addWidget(self._btn_execute)

        cmd_widget = QWidget()
        cmd_widget.setObjectName("debugCmdBar")
        cmd_widget.setLayout(cmd_layout)
        main_layout.addWidget(cmd_widget)

        # ── 状态栏 ──
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(10, 3, 10, 3)
        status_layout.setSpacing(12)

        self._status_count = QLabel("共 0 条")
        self._status_count.setObjectName("debugStatusLbl")
        status_layout.addWidget(self._status_count)

        # 监视状态
        self._status_monitor = QLabel("")
        self._status_monitor.setObjectName("debugStatusLbl")
        status_layout.addWidget(self._status_monitor)

        self._status_path = QLabel("")
        self._status_path.setObjectName("debugStatusLbl")
        status_layout.addWidget(self._status_path, 1)

        status_bar = QWidget()
        status_bar.setObjectName("debugStatusBar")
        status_bar.setLayout(status_layout)
        main_layout.addWidget(status_bar)

        # 更新状态栏
        self._update_statusbar()
        self._update_monitor_bar()

    # ═══════════════════════════════════════════════════
    #  样式加载
    # ═══════════════════════════════════════════════════

    def _get_theme_dir(self) -> str:
        """获取当前主题目录路径。"""
        from components.res_path import get_resource_root
        project_root = get_resource_root()
        config_path = os.path.join(project_root, "config", "config.json")
        theme_name = "catppuccin_mocha"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            theme_name = config.get("theme", "catppuccin_mocha")
        except Exception:
            pass
        return os.path.join(project_root, "style", "themes", theme_name)

    def _load_style(self):
        """加载调试台 QSS 样式（跟随当前主题）。"""
        theme_dir = self._get_theme_dir()

        qss_path = os.path.join(theme_dir, "debug_console.qss")
        if os.path.exists(qss_path):
            try:
                with open(qss_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
            except Exception:
                pass

        # 也加载标题栏样式
        titlebar_qss = os.path.join(theme_dir, "title_bar.qss")
        if os.path.exists(titlebar_qss):
            try:
                with open(titlebar_qss, "r", encoding="utf-8") as f:
                    current = self.styleSheet()
                    self.setStyleSheet(current + "\n" + f.read())
            except Exception:
                pass

    # ═══════════════════════════════════════════════════
    #  日志回调
    # ═══════════════════════════════════════════════════

    def _on_log_entry(self, entry: str):
        """日志条目回调（由 LogManager 调用）。"""
        if self._paused:
            self._pending_entries.append(entry)
        else:
            self._append_log(entry)

    def _append_log(self, entry: str, is_html: bool = False):
        """将日志条目追加到显示区（带颜色）。

        Args:
            entry: 日志文本
            is_html: True 表示 entry 已是 HTML 格式，跳过转义和着色
        """
        if is_html:
            html = f"{entry}<br>"
        else:
            if "[ERROR]" in entry:
                color = "#f38ba8"
            elif "[WARN]" in entry:
                color = "#f9e2af"
            elif "[DEBUG]" in entry:
                color = "#6c7086"
            else:
                color = "#cdd6f4"
            html = f'<span style="color:{color};">{self._escape_html(entry)}</span><br>'

        self._log_output.moveCursor(QTextCursor.End)
        self._log_output.insertHtml(html)

        if self._auto_scroll:
            scrollbar = self._log_output.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        # 更新状态栏
        self._update_statusbar()

    def _flush_pending(self):
        """刷新暂停期间缓存的日志条目。"""
        if self._pending_entries:
            self._log_output.insertHtml(
                '<span style="color:#6c7086;">── 以下为暂停期间日志 ──</span><br>'
            )
            for entry in self._pending_entries:
                self._append_log(entry)
            self._pending_entries.clear()

    @staticmethod
    def _escape_html(text: str) -> str:
        """转义 HTML 特殊字符。"""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _on_output_context_menu(self, pos):
        """输出区右键菜单：复制选中文本/保存全部输出。"""
        menu = QMenu(self)
        act_copy = QAction("📋 复制选中", self)
        act_copy.triggered.connect(self._on_copy_selected)
        menu.addAction(act_copy)

        act_copy_all = QAction("📋 复制全部", self)
        act_copy_all.triggered.connect(self._on_copy_all)
        menu.addAction(act_copy_all)

        menu.addSeparator()

        act_save = QAction("💾 保存到文件...", self)
        act_save.triggered.connect(self._on_save_output)
        menu.addAction(act_save)

        menu.exec_(self._log_output.mapToGlobal(pos))

    def _on_copy_selected(self):
        """复制选中文本到剪贴板。"""
        cursor = self._log_output.textCursor()
        if cursor.hasSelection():
            QApplication.clipboard().setText(cursor.selectedText())
        else:
            # 无选中时复制全部可见文本
            QApplication.clipboard().setText(self._log_output.toPlainText())

    def _on_copy_all(self):
        """复制输出区全部内容到剪贴板。"""
        QApplication.clipboard().setText(self._log_output.toPlainText())

    def _on_save_output(self):
        """将输出区内容保存到文件。"""
        from components.popup_dialog import CustomDialog
        from components.res_path import get_resource_root
        import os
        project_root = get_resource_root()
        logs_dir = os.path.join(project_root, "docs", "log")
        os.makedirs(logs_dir, exist_ok=True)
        fpath = os.path.join(logs_dir, "debug_output_saved.txt")
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(self._log_output.toPlainText())
            CustomDialog.information(self, "保存成功", f"已保存至:\n{fpath}")
        except Exception as e:
            CustomDialog.warning(self, "保存失败", str(e))

    # ═══════════════════════════════════════════════════
    #  搜索功能
    # ═══════════════════════════════════════════════════

    def _toggle_search_bar(self):
        """切换搜索栏显隐。"""
        visible = not self._search_bar_widget.isVisible()
        self._search_bar_widget.setVisible(visible)
        self._search_edit.setVisible(visible)
        self._search_btn_close.setVisible(visible)
        if visible:
            self._search_edit.setFocus()
            self._search_edit.selectAll()
        else:
            self._clear_search_highlight()
            self._cmd_input.setFocus()

    def _on_search_next(self):
        """搜索下一个匹配项。"""
        keyword = self._search_edit.text().strip()
        if not keyword:
            return
        self._highlight_search(keyword)

    def _highlight_search(self, keyword: str):
        """在输出区高亮并定位所有匹配项。"""
        doc = self._log_output.document()
        # 清除旧高亮
        self._clear_search_highlight()

        # 查找并高亮
        cursor = doc.find(keyword, 0)
        found = 0
        first_pos = None
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#f9e2af"))
        fmt.setForeground(QColor("#1e1e2e"))

        while not cursor.isNull():
            if first_pos is None:
                first_pos = cursor.position()
            cursor.mergeCharFormat(fmt)
            found += 1
            # 继续查找
            cursor = doc.find(keyword, cursor.position())

        if found == 0:
            return

        # 定位到第一个匹配项
        if first_pos is not None:
            c = self._log_output.textCursor()
            c.setPosition(first_pos)
            self._log_output.setTextCursor(c)
            self._log_output.ensureCursorVisible()

    def _clear_search_highlight(self):
        """清除搜索高亮。"""
        doc = self._log_output.document()
        # 将全文背景恢复
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.Document)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("transparent"))
        cursor.mergeCharFormat(fmt)

    # ═══════════════════════════════════════════════════
    #  工具栏按钮回调
    # ═══════════════════════════════════════════════════

    def _on_clear(self):
        """清空日志显示区。"""
        self._log_output.clear()
        self._log_mgr.info("日志显示区已清空")

    def _on_toggle_pause(self):
        """暂停/恢复日志刷新。"""
        self._paused = self._btn_pause.isChecked()
        if self._paused:
            self._btn_pause.setText("▶ 继续")
            self._log_mgr.info("⏸ 日志刷新已暂停")
        else:
            self._btn_pause.setText("⏸ 暂停")
            self._log_mgr.info("▶ 日志刷新已恢复")
            self._flush_pending()

    def _on_toggle_auto_scroll(self, checked: bool):
        """自动滚动开关。"""
        self._auto_scroll = checked

    def _on_level_changed(self, index: int):
        """日志级别切换。"""
        self._log_level_index = index
        levels = ["DEBUG", "INFO", "WARN", "ERROR"]
        self._log_mgr.info(f"日志显示级别已切换为: {levels[index]}")

        # 按级别过滤已有的日志显示
        self._log_output.clear()
        level_order = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3}
        min_order = index
        for entry in self._log_mgr.entries:
            for lvl_name in ["DEBUG", "INFO", "WARN", "ERROR"]:
                if f"[{lvl_name}]" in entry:
                    if level_order[lvl_name] >= min_order:
                        self._append_log(entry)
                    break

    def _on_export_log(self):
        """导出日志到文件。"""
        from components.popup_dialog import CustomDialog
        path = self._log_mgr.export_log()
        if path:
            self._log_mgr.info(f"日志已导出至: {path}")
            CustomDialog.information(self, "导出成功", f"日志已保存至:\n{path}")
        else:
            self._log_mgr.error("日志导出失败")
            CustomDialog.warning(self, "导出失败", "无法写入日志文件，请检查磁盘空间或权限。")

    def _on_clean_logs(self):
        """手动清理旧日志。"""
        n = self._log_mgr.manual_clean()
        self._log_mgr.info(f"手动清理: 已删除 {n} 个过期日志文件")

    # ═══════════════════════════════════════════════════
    #  命令执行
    # ═══════════════════════════════════════════════════

    def _on_execute_command(self):
        """执行命令输入框中的命令（含耗时统计）。"""
        self._suggest_popup.hide()
        cmd_line = self._cmd_input.text().strip()
        if not cmd_line:
            return

        self._cmd_input.clear()

        # 添加到历史记录
        self._cmd_handler.add_history(cmd_line)

        # 显示命令回显
        self._append_log(
            f"<span style='color:#89b4fa;'>&gt; {self._escape_html(cmd_line)}</span>",
            is_html=True,
        )

        # 执行命令并计时
        import time
        t0 = time.perf_counter()
        success = self._cmd_handler.execute(
            cmd_line,
            log_fn=self._cmd_log_fn,
            mw=self._main_window,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        elapsed_str = f"{elapsed:.0f}ms" if elapsed >= 1 else f"{elapsed:.1f}ms"
        status = "✅" if success else "❌"
        self._append_log(
            f"<span style='color:#6c7086;font-size:9px;'>  {status} {elapsed_str}</span>",
            is_html=True,
        )

    def _refresh_plugin_commands(self):
        """从插件管理器加载已启用插件的自定义控制台命令。"""
        try:
            mw = self._main_window
            if mw and hasattr(mw, "_plugin_manager"):
                pm = mw._plugin_manager
                cmds = pm.get_enabled_console_commands()
                self._cmd_handler.set_plugin_commands(cmds)
                # 同步更新悬浮窗的命令树
                self._suggest_popup.refresh_tree()
        except Exception:
            pass

    def _on_input_text_changed(self, text: str):
        """输入框文本变化时触发自动补全（基于命令树）。"""
        if self._suggest_popup.isVisible():
            self._suggest_popup.show_suggestions(text)
        elif text.strip() and len(text.strip()) >= 1:
            self._suggest_popup.show_suggestions(text)

    def _cmd_log_fn(self, level: str, message: str):
        """命令处理器的日志回调。"""
        if level == "__CLEAR__":
            self._log_output.clear()
        elif level == "__LEVEL__":
            # 同步更新下拉框并重新过滤日志
            new_level = message.upper()
            lvl_map = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3}
            idx = lvl_map.get(new_level, 1)
            self._cmb_level.blockSignals(True)
            self._cmb_level.setCurrentIndex(idx)
            self._cmb_level.blockSignals(False)
            self._log_level_index = idx
            # 重新过滤显示
            self._log_output.clear()
            for entry in self._log_mgr.entries:
                for lvl_name in ["DEBUG", "INFO", "WARN", "ERROR"]:
                    if f"[{lvl_name}]" in entry:
                        if lvl_map[lvl_name] >= idx:
                            self._append_log(entry)
                        break
        elif level == "__DIALOG_INFO__":
            from components.popup_dialog import CustomDialog
            CustomDialog.information(self, "提示", message)
        elif level == "__TIMER_START__":
            self._start_timer(int(message))
        elif level == "__TIMER_STOP__":
            self._stop_timer()
        else:
            # 按当前级别过滤
            lvl_order = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3}
            if lvl_order.get(level, 0) >= self._log_level_index:
                # 直接追加到显示区（不写入文件，避免重复）
                if "[ERROR]" in f"[{level}]":
                    color = "#f38ba8"
                elif "[WARN]" in f"[{level}]":
                    color = "#f9e2af"
                else:
                    color = "#cdd6f4"
                html = f'<span style="color:{color};">[{datetime.now().strftime("%H:%M:%S.%f")[:12]}] [{level}] {self._escape_html(message)}</span><br>'
                self._log_output.moveCursor(QTextCursor.End)
                self._log_output.insertHtml(html)
                if self._auto_scroll:
                    scrollbar = self._log_output.verticalScrollBar()
                    scrollbar.setValue(scrollbar.maximum())
                self._update_statusbar()

    # ═══════════════════════════════════════════════════
    #  计时器
    # ═══════════════════════════════════════════════════

    def _start_timer(self, seconds: int):
        """启动倒计时器。"""
        self._stop_timer()
        self._timer_seconds = seconds
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._timer_tick)
        self._timer.start(1000)
        mins, secs = divmod(self._timer_seconds, 60)
        self._log_mgr.info(f"⏱  倒计时开始: {mins:02d}:{secs:02d}")

    def _stop_timer(self):
        """停止计时器。"""
        if self._timer:
            self._timer.stop()
            self._timer = None
        self._timer_seconds = 0

    def _timer_tick(self):
        """计时器每秒回调。"""
        self._timer_seconds -= 1
        if self._timer_seconds <= 0:
            self._log_mgr.info("⏱  时间到！")
            self._stop_timer()
            return
        mins, secs = divmod(self._timer_seconds, 60)
        if self._timer_seconds % 10 == 0 or self._timer_seconds <= 5:
            self._log_mgr.info(f"⏱  剩余: {mins:02d}:{secs:02d}")

    # ═══════════════════════════════════════════════════
    #  键盘事件
    # ═══════════════════════════════════════════════════

    def keyPressEvent(self, event: QKeyEvent):
        """处理快捷键，路由键盘事件。"""
        # Ctrl+F 搜索
        if event.key() == Qt.Key_F and event.modifiers() == Qt.ControlModifier:
            self._toggle_search_bar()
            return

        # Ctrl+L 清屏
        if event.key() == Qt.Key_L and event.modifiers() == Qt.ControlModifier:
            self._on_clear()
            return

        # 悬浮框可见时的键盘导航
        if self._suggest_popup.isVisible():
            if event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Tab,
                               Qt.Key_Enter, Qt.Key_Return, Qt.Key_Escape):
                # 将事件转发给悬浮框的列表控件
                self._suggest_popup.eventFilter(
                    self._suggest_popup._list,
                    event
                )
                return

        # 阻止 Enter/Return 键触发 QDialog.accept() 关闭对话框
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            widget = self.focusWidget()
            if widget is self._cmd_input:
                if self._suggest_popup.isVisible():
                    # 悬浮框可见→先补全再执行
                    self._suggest_popup.apply_to_input(execute=True)
                else:
                    self._on_execute_command()
            return

        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        """拦截输入事件：↑↓ 历史，Tab 补全，Shift+Enter 反向搜索。"""
        if not hasattr(self, '_cmd_input') or obj is not self._cmd_input or event.type() != event.KeyPress:
            return super().eventFilter(obj, event)

        key = event.key()
        mod = event.modifiers()

        # 搜索框激活时 Shift+Enter 反向搜索
        if obj is self._search_edit and key in (Qt.Key_Return, Qt.Key_Enter):
            if mod == Qt.ShiftModifier:
                # 反向搜索（可选实现）
                pass
            return False

        # 搜索框 Escape → 关闭搜索栏
        if obj is self._search_edit and key == Qt.Key_Escape:
            self._toggle_search_bar()
            return True

        # 悬浮框可见时：↑↓ Tab 由补全框处理
        if self._suggest_popup.isVisible():
            if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Tab,
                       Qt.Key_Escape, Qt.Key_Right):
                self._suggest_popup.eventFilter(
                    self._suggest_popup._list, event
                )
                return True
            elif key in (Qt.Key_Return, Qt.Key_Enter):
                return False
        else:
            # 悬浮框隐藏时：↑↓ 浏览历史命令
            if key == Qt.Key_Up:
                cmd = self._cmd_handler.history_up()
                if cmd is not None:
                    self._cmd_input.setText(cmd)
                return True
            elif key == Qt.Key_Down:
                cmd = self._cmd_handler.history_down()
                if cmd is not None:
                    self._cmd_input.setText(cmd)
                return True
        return super().eventFilter(obj, event)

    # ═══════════════════════════════════════════════════
    #  调试模式菜单
    # ═══════════════════════════════════════════════════

    def _setup_debug_menu(self):
        """构建标题栏「调试 ▼」下拉菜单。"""
        self._debug_menu.clear()
        self._debug_menu.setFont(QFont("Microsoft YaHei", 10))

        # 设置入口
        act_settings = QAction("⚙ 调试模式设置...", self._debug_menu)
        act_settings.triggered.connect(self._on_open_debug_mode_dialog)
        self._debug_menu.addAction(act_settings)

        self._debug_menu.addSeparator()

        # 全部启用/禁用
        act_enable_all = QAction("🟢 全部启用", self._debug_menu)
        act_enable_all.triggered.connect(self._on_enable_all_monitors)
        self._debug_menu.addAction(act_enable_all)

        act_disable_all = QAction("🔴 全部禁用", self._debug_menu)
        act_disable_all.triggered.connect(self._on_disable_all_monitors)
        self._debug_menu.addAction(act_disable_all)

        self._debug_menu.addSeparator()

        # 5 项监视快捷切换
        self._monitor_actions: dict[str, QAction] = {}
        for mtype in MONITOR_TYPES:
            label = MONITOR_LABELS.get(mtype, mtype)
            action = QAction(f"☐ 监视{label}", self._debug_menu)
            action.setCheckable(True)
            action.setData(mtype)
            action.toggled.connect(lambda checked, mt=mtype: self._on_toggle_monitor_from_menu(mt, checked))
            self._debug_menu.addAction(action)
            self._monitor_actions[mtype] = action

        self._debug_menu.addSeparator()

        # 查看监视日志
        act_view = QAction("📋 查看监视日志", self._debug_menu)
        act_view.triggered.connect(self._on_view_monitor_logs)
        self._debug_menu.addAction(act_view)

    def _on_show_debug_menu(self):
        """显示调试菜单（定位在按钮下方）。"""
        # 刷新菜单项勾选状态
        for mtype, action in self._monitor_actions.items():
            action.blockSignals(True)
            action.setChecked(self._monitor_mgr.is_monitor_enabled(mtype))
            # 更新显示文字
            label = MONITOR_LABELS.get(mtype, mtype)
            state = "☑" if self._monitor_mgr.is_monitor_enabled(mtype) else "☐"
            action.setText(f"{state} 监视{label}")
            action.blockSignals(False)

        # 菜单弹出
        pos = self._btn_debug_menu.mapToGlobal(
            self._btn_debug_menu.rect().bottomLeft()
        )
        self._debug_menu.exec_(pos)

    def _on_open_debug_mode_dialog(self):
        """打开调试模式设置弹窗。"""
        dialog = DebugModeDialog(self, self._monitor_mgr)
        dialog.exec_()

    def _on_enable_all_monitors(self):
        """启用全部监视。"""
        self._monitor_mgr.enable_all()
        self._log_mgr.info("[DEBUG] 调试模式: 已启用全部监视")

    def _on_disable_all_monitors(self):
        """禁用全部监视。"""
        self._monitor_mgr.disable_all()
        self._log_mgr.info("[DEBUG] 调试模式: 已禁用全部监视")

    def _on_toggle_monitor_from_menu(self, mtype: str, checked: bool):
        """从菜单快速切换单项监视。"""
        self._monitor_mgr.set_monitor(mtype, checked)
        label = MONITOR_LABELS.get(mtype, mtype)
        state = "已开启" if checked else "已关闭"
        self._log_mgr.info(f"[DEBUG] 监视{label}: {state}")

    def _on_view_monitor_logs(self):
        """查看监视日志（过滤显示监视相关条目）。"""
        monitor_tags = ["[VAR]", "[FUNC]", "[PLUGIN]", "[API]", "[AI]"]
        self._log_output.clear()
        found = 0
        for entry in self._log_mgr.entries:
            if any(tag in entry for tag in monitor_tags):
                self._append_log(entry)
                found += 1
        if found == 0:
            self._log_mgr.info("没有监视日志条目")

    # ═══════════════════════════════════════════════════
    #  监视状态回调
    # ═══════════════════════════════════════════════════

    def _on_monitor_config_changed(self, config: dict):
        """监视配置变更时更新 UI。"""
        self._update_monitor_bar()
        self._update_statusbar()

    def _update_monitor_bar(self):
        """更新监视状态指示条。"""
        active = self._monitor_mgr.get_active_monitors()
        if not active:
            self._monitor_bar.setVisible(False)
            self._btn_stop_all_monitors.setVisible(False)
            return

        self._monitor_bar.setVisible(True)
        self._btn_stop_all_monitors.setVisible(True)

        # 构建监视项文字：监视中: ■变量 □函数 ■插件 ...
        parts = []
        for mtype in MONITOR_TYPES:
            label = MONITOR_LABELS.get(mtype, mtype)
            enabled = self._monitor_mgr.is_monitor_enabled(mtype)
            symbol = "■" if enabled else "□"
            parts.append(f"{symbol}{label}")

        self._monitor_text_label.setText("监视中: " + " ".join(parts))

    def _update_statusbar(self):
        """更新状态栏信息。"""
        count = self._log_mgr.get_entry_count()
        self._status_count.setText(f"共 {count} 条")

        # 监视状态
        if self._monitor_mgr.enabled:
            active = self._monitor_mgr.get_active_monitors()
            if active:
                self._status_monitor.setText(f"调试: ⬤开启 | 监视: {','.join(active)}")
                self._status_monitor.setStyleSheet(f"color: {tc("accent_green")}; font-size: 10px;")
            else:
                self._status_monitor.setText("调试: ⬤开启 | 监视: 无")
                self._status_monitor.setStyleSheet(f"color: {tc("accent_yellow")}; font-size: 10px;")
        else:
            self._status_monitor.setText("")
            self._status_monitor.setStyleSheet("")

        log_path = self._log_mgr.log_path
        # 显示相对于项目根目录的路径
        from components.res_path import get_resource_root
        project_root = get_resource_root()
        rel_path = os.path.relpath(log_path, project_root) if log_path else ""
        self._status_path.setText(f"日志: {rel_path}")

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            self._title_bar.update_max_btn()
        super().changeEvent(event)

    def nativeEvent(self, event_type, message):
        """Windows: 无边框窗口边缘拖拽缩放。"""
        if sys.platform != 'win32':
            return False, 0
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST
                x = msg.lParam & 0xFFFF
                y = (msg.lParam >> 16) & 0xFFFF
                g = self.geometry()
                border = 6
                left = x < g.left() + border
                right = x > g.right() - border
                top = y < g.top() + border
                bottom = y > g.bottom() - border
                if top and left:
                    return True, 13
                if top and right:
                    return True, 14
                if bottom and left:
                    return True, 16
                if bottom and right:
                    return True, 17
                if left:
                    return True, 10
                if right:
                    return True, 11
                if top:
                    return True, 12
                if bottom:
                    return True, 15
            return False, 0
        except Exception:
            return False, 0

    def closeEvent(self, event):
        """关闭窗口时清理计时器。"""
        self._stop_timer()
        self._log_mgr.info("═══ 调试台界面已关闭（后台日志继续运行）═══")
        self.closed.emit()
        super().closeEvent(event)
