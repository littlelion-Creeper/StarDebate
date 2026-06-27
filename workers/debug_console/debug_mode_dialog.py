from components.theme_colors import tc, refresh
"""调试模式设置弹窗 — DebugModeDialog

独立弹出窗口，用于配置 5 项监视开关。
包含自定义 TitleBar、总开关、5 项监视复选框、恢复默认/保存按钮。
"""

import sys
import ctypes
import os
import json
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QCheckBox, QFrame, QSizePolicy,
)
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QFont

from components.title_bar import TitleBar
from components.star_button import StarButton
from .debug_monitor_manager import (
    DebugMonitorManager, MONITOR_TYPES, MONITOR_LABELS,
)

# ── 监视项描述 ──────────────────────────────────────

MONITOR_DESCRIPTIONS = {
    "variable_watch": "记录所有变量赋值操作，捕获变量名和新值。\n输出格式: [VAR] 文件:行号 → name = value",
    "function_watch": "记录所有def函数的调用、返回值和异常信息。\n输出格式: [FUNC] 模块:函数名 → 结果/异常",
    "plugin_watch": "记录插件和功能模块的加载成功/失败状态。\n输出格式: [PLUGIN] ✅/❌ 插件名 → 状态",
    "api_watch": "记录所有HTTP API请求的端点、参数、响应状态码、\n耗时和网络错误信息。输出格式: [API] ▶请求/✓成功/✗错误",
    "ai_watch": "记录AI功能的业务逻辑调用、返回内容和错误信息。\n输出格式: [AI] 功能名 → 耗时 | 结果/错误",
}

MONITOR_WARNINGS = {
    "variable_watch": "⚠ 高频变量变化可能产生大量日志，谨慎开启。",
    "function_watch": "⚠ 大量函数调用可能影响运行性能。",
    "plugin_watch": "",
    "api_watch": "",
    "ai_watch": "",
}

MONITOR_ORDER = list(MONITOR_TYPES)


class DebugModeDialog(QDialog):
    """调试模式设置弹窗"""

    def __init__(self, parent=None, monitor_mgr: DebugMonitorManager = None):
        super().__init__(parent)
        self.setWindowTitle("调试模式设置")
        self.resize(540, 620)
        self.setMinimumSize(460, 480)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)

        self._monitor_mgr = monitor_mgr or DebugMonitorManager.instance()
        self._checkboxes: dict[str, QCheckBox] = {}
        self._status_label: QLabel = None

        # 居中
        if parent:
            pg = parent.geometry()
            self.move(
                pg.x() + (pg.width() - self.width()) // 2,
                pg.y() + (pg.height() - self.height()) // 2,
            )

        self._setup_ui()
        self._load_style()
        self._load_current_config()

    # ═══════════════════════════════════════════════════
    #  UI 构建
    # ═══════════════════════════════════════════════════

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 标题栏 ──
        self._title_bar = TitleBar(self, "调试模式设置", "🔧")
        main_layout.addWidget(self._title_bar)

        # ── 内容区 ──
        content = QVBoxLayout()
        content.setContentsMargins(20, 16, 20, 16)
        content.setSpacing(10)

        # ★ 总开关卡片
        master_card = self._create_card(content)
        master_card.setObjectName("monitorMasterCard")
        master_layout = QVBoxLayout(master_card)
        master_layout.setContentsMargins(14, 12, 14, 12)
        master_layout.setSpacing(10)

        master_title = QLabel("调试模式总开关")
        master_title.setObjectName("monitorCardTitle")
        master_title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        master_layout.addWidget(master_title)

        # 总开关按钮
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(12)

        lbl_off = QLabel("⬤ 已关闭")
        lbl_off.setObjectName("monitorToggleOff")
        lbl_off.setFont(QFont("Microsoft YaHei", 11))
        toggle_row.addWidget(lbl_off)

        self._btn_master = StarButton("○", self, layout_mode="text_only", ratio_h=0.7, checkable=True, auto_size=False)
        self._btn_master.setObjectName("monitorMasterToggle")
        self._btn_master.setFixedSize(56, 28)
        self._btn_master.clicked.connect(self._on_master_toggled)
        toggle_row.addWidget(self._btn_master)

        lbl_on = QLabel("已开启 ⬤")
        lbl_on.setObjectName("monitorToggleOn")
        lbl_on.setFont(QFont("Microsoft YaHei", 11))
        toggle_row.addWidget(lbl_on)

        toggle_row.addStretch()
        master_layout.addLayout(toggle_row)

        # 状态文字
        self._status_label = QLabel("状态: ● 调试模式未开启 | 已选中 0/5 项监视")
        self._status_label.setObjectName("monitorStatus")
        self._status_label.setFont(QFont("Microsoft YaHei", 10))
        master_layout.addWidget(self._status_label)

        # ★ 分隔线
        sep = QFrame()
        sep.setObjectName("monitorSep")
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        content.addWidget(sep)

        # ★ 5 项监视复选框
        for i, mtype in enumerate(MONITOR_ORDER):
            card = self._create_monitor_card(mtype, i + 1)
            content.addWidget(card)

        content.addStretch()

        # ── 底部按钮栏 ──
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(20, 8, 20, 12)
        btn_layout.setSpacing(10)

        btn_layout.addStretch()

        btn_default = StarButton("恢复默认", self, layout_mode="text_only", ratio_h=0.7)
        btn_default.setObjectName("monitorBtnReset")
        btn_default.clicked.connect(self._on_reset_default)
        btn_layout.addWidget(btn_default)

        btn_cancel = StarButton("取消", self, layout_mode="text_only", ratio_h=0.7)
        btn_cancel.setObjectName("monitorBtnCancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = StarButton("保存并应用", self, layout_mode="text_only", ratio_h=0.7, accent="#89b4fa")
        btn_save.setObjectName("monitorBtnSave")
        btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(btn_save)

        content_widget = QWidget()
        content_widget.setObjectName("monitorContent")
        content_widget.setLayout(content)
        main_layout.addWidget(content_widget, 1)

        btn_widget = QWidget()
        btn_widget.setObjectName("monitorBtnBar")
        btn_widget.setLayout(btn_layout)
        main_layout.addWidget(btn_widget)

    def _create_card(self, parent_layout) -> QFrame:
        """创建统一样式的卡片容器。"""
        card = QFrame()
        card.setObjectName("monitorCard")
        return card

    def _create_monitor_card(self, mtype: str, num: int) -> QFrame:
        """创建单个监视项卡片。"""
        card = QFrame()
        card.setObjectName("monitorItemCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        # 复选框 + 标题
        cb = QCheckBox(f"{num}. 监视{MONITOR_LABELS.get(mtype, mtype)}变化" if mtype == "variable_watch" else
                       f"{num}. 监视{MONITOR_LABELS.get(mtype, mtype)}{'运行结果' if mtype in ('function_watch', 'ai_watch', 'api_watch') else '加载'}")
        cb.setObjectName("monitorCheckbox")
        cb.setFont(QFont("Microsoft YaHei", 11))
        cb.setCursor(Qt.PointingHandCursor)
        cb.toggled.connect(lambda checked, mt=mtype: self._on_monitor_toggled(mt, checked))
        self._checkboxes[mtype] = cb
        layout.addWidget(cb)

        # 描述
        desc = MONITOR_DESCRIPTIONS.get(mtype, "")
        if desc:
            desc_label = QLabel(desc)
            desc_label.setObjectName("monitorDesc")
            desc_label.setFont(QFont("Microsoft YaHei", 9))
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)

        # 警告
        warn = MONITOR_WARNINGS.get(mtype, "")
        if warn:
            warn_label = QLabel(warn)
            warn_label.setObjectName("monitorWarn")
            warn_label.setFont(QFont("Microsoft YaHei", 9))
            warn_label.setWordWrap(True)
            layout.addWidget(warn_label)

        return card

    # ═══════════════════════════════════════════════════
    #  样式加载
    # ═══════════════════════════════════════════════════

    def _load_style(self):
        """加载当前主题样式。"""
        from components.res_path import get_resource_root
        from workers.app_config.config_paths import get_config_path
        project_root = get_resource_root()
        config_path = get_config_path("config/config.json")
        theme_name = "catppuccin_mocha"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            theme_name = config.get("theme", "catppuccin_mocha")
        except Exception:
            pass

        theme_dir = os.path.join(project_root, "style", "themes", theme_name)

        # 加载 debug_console.qss（包含监视弹窗样式）
        qss_path = os.path.join(theme_dir, "debug_console.qss")
        if os.path.exists(qss_path):
            try:
                with open(qss_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
            except Exception:
                pass

        # 合并标题栏样式
        titlebar_qss = os.path.join(theme_dir, "title_bar.qss")
        if os.path.exists(titlebar_qss):
            try:
                with open(titlebar_qss, "r", encoding="utf-8") as f:
                    current = self.styleSheet()
                    self.setStyleSheet(current + "\n" + f.read())
            except Exception:
                pass

    # ═══════════════════════════════════════════════════
    #  数据加载/保存
    # ═══════════════════════════════════════════════════

    def _load_current_config(self):
        """从 manager 加载当前配置到 UI。"""
        config = self._monitor_mgr.config
        self._btn_master.setChecked(config.get("debug_mode_enabled", False))
        monitors = config.get("monitors", {})
        for mtype in MONITOR_TYPES:
            cb = self._checkboxes.get(mtype)
            if cb:
                cb.setChecked(monitors.get(mtype, False))
        self._update_status_label()

    def _on_master_toggled(self, checked: bool):
        """总开关切换。"""
        # 总开关联动所有子项
        for cb in self._checkboxes.values():
            cb.setChecked(checked)
        self._update_status_label()

    def _on_monitor_toggled(self, mtype: str, checked: bool):
        """单项监视切换。"""
        # 如果所有子项都关了，总开关也关
        if not checked:
            all_off = all(not cb.isChecked() for cb in self._checkboxes.values())
            if all_off:
                self._btn_master.setChecked(False)
        else:
            # 如果开了任一项，总开关也开
            self._btn_master.setChecked(True)
        self._update_status_label()

    def _update_status_label(self):
        """更新状态文字。"""
        enabled = self._btn_master.isChecked()
        active_count = sum(1 for cb in self._checkboxes.values() if cb.isChecked())
        total = len(self._checkboxes)

        if enabled:
            self._status_label.setText(
                f"状态: ● 调试模式已开启 | 已选中 {active_count}/{total} 项监视"
            )
            self._status_label.setStyleSheet(f"color: {tc("accent_green")}; font-size: 10px;")
        else:
            self._status_label.setText(
                f"状态: ● 调试模式未开启 | 已选中 {active_count}/{total} 项监视"
            )
            self._status_label.setStyleSheet(f"color: {tc("subtext")}; font-size: 10px;")

    def _on_save(self):
        """保存配置到 manager。"""
        self._monitor_mgr.enabled = self._btn_master.isChecked()
        for mtype in MONITOR_TYPES:
            cb = self._checkboxes.get(mtype)
            if cb:
                self._monitor_mgr.set_monitor(mtype, cb.isChecked())
        self.accept()

    def _on_reset_default(self):
        """恢复默认配置。"""
        self._monitor_mgr.reset_to_default()
        self._load_current_config()

    # ═══════════════════════════════════════════════════
    #  窗口事件
    # ═══════════════════════════════════════════════════

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
            if msg.message == 0x0084:
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
        super().closeEvent(event)
