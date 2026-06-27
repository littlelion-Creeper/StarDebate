from components.theme_colors import tc, refresh
# -*- coding: utf-8 -*-
"""赛程管理 — TournamentManager 类

负责：
- 赛制选择面板 UI（浏览视图 + 多 Tab 编辑视图）
- 赛制数据 CRUD（预设 + 自定义）
- 赛制导入/导出
- 辩位 + 环节编辑（卡片布局 + 对位 + 实时预览）
- 自由辩论编辑区
- 实时预览刷新
- 数据持久化（独立 JSON + 集中式备份）

面板位于 left_vsplit 索引 2，通过导航栏 🏆赛程 按钮切换显示。
"""

import os
import re
import json
import copy

from workers.app_config.config_paths import get_config_path, get_config_base_dir

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QTabWidget, QScrollArea, QWidget, QLineEdit,
    QComboBox, QFileDialog, QMenu, QLayout,
)
from PyQt5.QtGui import QFont

from . import COMPETITION_PRESETS, AVAILABLE_PHASES, AVAILABLE_DURATIONS, COUNTERPART_OPTIONS


class TournamentManager:
    """赛程/赛制管理器"""

    def __init__(self, mw):
        """初始化管理器

        Args:
            mw: StarDebateWindow 主窗口引用
        """
        self._mw = mw

        # ---- 数据成员 ----
        self._competition_formats_file = get_config_path("config/competition_formats.json")
        self._competition_formats_dir = os.path.join(get_config_base_dir(), "custom_formats")
        self._competition_formats: list[dict] = []
        self._current_format: dict | None = None
        self._match_schedule_visible: bool = False

        # ---- 编辑视图状态 ----
        self._format_tabs_data: dict[int, dict] = {}
        self._format_tab_counter: int = 0

        # ---- UI 控件引用（由 build_panel 赋值） ----
        self._panel: QFrame | None = None
        self._format_view_stack: QStackedWidget | None = None
        self._format_browse_tab: QTabWidget | None = None
        self._preset_format_list: QListWidget | None = None
        self._custom_format_list: QListWidget | None = None
        self._format_detail_scroll: QScrollArea | None = None
        self._format_detail: QWidget | None = None
        self._format_detail_layout: QVBoxLayout | None = None
        self._format_tab_widget: QTabWidget | None = None
        self._btn_save_format: QPushButton | None = None

        # ---- 指定赛制页 UI 引用 ----
        self._assign_debate_lbl: QLabel | None = None
        self._assign_format_combo: QComboBox | None = None
        self._assign_name_lbl: QLabel | None = None
        self._assign_team_lbl: QLabel | None = None
        self._assign_positions_lbl: QLabel | None = None
        self._assign_phases_lbl: QLabel | None = None
        self._assign_free_lbl: QLabel | None = None
        self._assign_empty_hint: QLabel | None = None
        self._assign_detail_container: QWidget | None = None
        self._assign_save_btn: QPushButton | None = None
        self._assign_no_debate_hint: QLabel | None = None
        self._assign_debate_section: QFrame | None = None

        # ---- 页面导航按钮 ----
        self._btn_nav_assign: QPushButton | None = None
        self._btn_nav_browse: QPushButton | None = None
        self._btn_nav_edit: QPushButton | None = None

        # ---- 内部信号引用 ----
        self._btn_toggle: QPushButton | None = None

    # ============================================================
    # 公共属性
    # ============================================================

    @property
    def competition_formats(self) -> list[dict]:
        return self._competition_formats

    @property
    def current_format(self) -> dict | None:
        return self._current_format

    @property
    def match_schedule_visible(self) -> bool:
        return self._match_schedule_visible

    @property
    def panel(self) -> QFrame | None:
        return self._panel

    @property
    def custom_format_list(self) -> QListWidget | None:
        return self._custom_format_list

    @property
    def browse_tab(self) -> QTabWidget | None:
        return self._format_browse_tab

    # ============================================================
    # 面板构建
    # ============================================================

    def build_panel(self) -> QFrame:
        """创建赛制管理面板（左侧面板栈索引 2）

        顶部三按钮导航 + QStackedWidget 三页：
          0: 指定赛制（默认）
          1: 浏览赛制
          2: 编辑赛制
        """
        panel = QFrame()
        panel.setObjectName("structurePanel")
        panel.setMinimumWidth(550)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(0)

        # ── 页面导航按钮 ──
        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(10, 0, 10, 4)
        nav_row.setSpacing(6)


        self._btn_nav_assign = QPushButton("指定赛制")
        self._btn_nav_assign.setObjectName("assignNavBtn")
        self._btn_nav_assign.setCheckable(True)
        self._btn_nav_assign.setChecked(True)
        self._btn_nav_assign.setCursor(Qt.PointingHandCursor)
        self._btn_nav_assign.setMinimumWidth(80)
        self._btn_nav_assign.setFixedHeight(30)
        self._btn_nav_assign.clicked.connect(lambda: self._switch_page(0))
        nav_row.addWidget(self._btn_nav_assign)

        self._btn_nav_browse = QPushButton("浏览赛制")
        self._btn_nav_browse.setObjectName("assignNavBtn")
        self._btn_nav_browse.setCheckable(True)
        self._btn_nav_browse.setCursor(Qt.PointingHandCursor)
        self._btn_nav_browse.setMinimumWidth(80)
        self._btn_nav_browse.setFixedHeight(30)
        self._btn_nav_browse.clicked.connect(lambda: self._switch_page(1))
        nav_row.addWidget(self._btn_nav_browse)

        self._btn_nav_edit = QPushButton("编辑赛制")
        self._btn_nav_edit.setObjectName("assignNavBtn")
        self._btn_nav_edit.setCheckable(True)
        self._btn_nav_edit.setCursor(Qt.PointingHandCursor)
        self._btn_nav_edit.setMinimumWidth(80)
        self._btn_nav_edit.setFixedHeight(30)
        self._btn_nav_edit.clicked.connect(lambda: self._switch_page(2))
        nav_row.addWidget(self._btn_nav_edit)

        nav_row.addStretch()
        layout.addLayout(nav_row)

        self._format_view_stack = QStackedWidget()
        self._format_view_stack.addWidget(self._create_assign_page())  # 0: 指定赛制
        self._format_view_stack.addWidget(self._create_browse_page())  # 1: 浏览赛制
        self._format_view_stack.addWidget(self._create_edit_page())    # 2: 编辑赛制
        self._format_view_stack.setCurrentIndex(0)  # 默认显示指定赛制
        layout.addWidget(self._format_view_stack)

        self._panel = panel
        return panel

    def _switch_page(self, index: int):
        """切换 QStackedWidget 页面"""
        self._format_view_stack.setCurrentIndex(index)
        # 更新按钮 checked 状态——样式由 QSS :checked 伪状态自动切换
        if self._btn_nav_assign:
            self._btn_nav_assign.setChecked(index == 0)
        if self._btn_nav_browse:
            self._btn_nav_browse.setChecked(index == 1)
        if self._btn_nav_edit:
            self._btn_nav_edit.setChecked(index == 2)
        # 切换到指定页时刷新
        if index == 0:
            self.refresh_assign_section()

    def switch_to_assign_page(self):
        """切换到指定赛制页面（供外部调用）"""
        self._switch_page(0)

    def refresh_assign_section(self):
        """刷新指定赛制区块，同步当前辩论的赛制信息"""
        if self._assign_format_combo is None:
            return

        mw = self._mw
        if not mw.current_debate_path or not mw.current_debate_data:
            if self._assign_no_debate_hint:
                self._assign_no_debate_hint.setVisible(True)
            if self._assign_debate_lbl:
                self._assign_debate_lbl.setText("（未打开辩论）")
            self._show_assign_empty()
            self._populate_assign_combo(None)
            self._enable_assign_controls(False)
            return

        if self._assign_no_debate_hint:
            self._assign_no_debate_hint.setVisible(False)
        self._enable_assign_controls(True)

        data = mw.current_debate_data
        pro = data.get("pro", "—")
        con = data.get("con", "—")
        fname = os.path.basename(mw.current_debate_path)
        if self._assign_debate_lbl:
            self._assign_debate_lbl.setText(f"{pro} vs {con}\n{fname}")

        fmt = data.get("format")
        if fmt and isinstance(fmt, dict):
            self._show_assign_detail(fmt)
        else:
            self._show_assign_empty()

        self._populate_assign_combo(fmt)

    def _populate_assign_combo(self, current_fmt: dict | None):
        """填充指定赛制下拉框"""
        if self._assign_format_combo is None:
            return
        self._assign_format_combo.blockSignals(True)
        self._assign_format_combo.clear()
        self._assign_format_combo.addItem("（不指定赛制）", None)

        preselected_idx = -1
        idx = 1
        for name in COMPETITION_PRESETS:
            fmt_data = COMPETITION_PRESETS[name]
            self._assign_format_combo.addItem(
                f"📌 {name}（预设）",
                {"name": name, "data": fmt_data, "type": "preset"})
            if current_fmt and current_fmt.get("name") == name:
                preselected_idx = idx
            idx += 1

        for fmt in self._competition_formats:
            f_name = fmt.get("name", "未命名")
            self._assign_format_combo.addItem(
                f"✏️ {f_name}（自定义）",
                {"name": f_name, "data": fmt, "type": "custom"})
            if current_fmt and current_fmt.get("name") == f_name:
                preselected_idx = idx
            idx += 1

        self._assign_format_combo.blockSignals(False)
        if preselected_idx >= 0:
            self._assign_format_combo.setCurrentIndex(preselected_idx)

    def _show_assign_detail(self, fmt: dict):
        """展示指定赛制详情"""
        name = fmt.get("name", "未知")
        fmt_type = fmt.get("type", "")
        type_label = "自定义" if fmt_type == "custom" else "预设"
        team_size = fmt.get("team_size", 0)
        positions = fmt.get("positions", [])
        free_debate = fmt.get("free_debate")

        if self._assign_name_lbl:
            self._assign_name_lbl.setText(f"{name} ({type_label})")
        if self._assign_team_lbl:
            self._assign_team_lbl.setText(f"队伍人数: {team_size}人/方")

        pos_names = [p.get("name", "?") for p in positions]
        if self._assign_positions_lbl:
            self._assign_positions_lbl.setText(
                f"辩位: {' → '.join(pos_names) if pos_names else '无'}")

        phase_lines = []
        for p in positions:
            p_name = p.get("name", "?")
            phases = p.get("phases", [])
            for ph in phases:
                ph_name = ph.get("name", "")
                ph_dur = ph.get("duration", 0)
                ph_cp = ph.get("counterpart", "")
                dur_s = f"{ph_dur // 60}分{ph_dur % 60}秒" if ph_dur >= 60 else f"{ph_dur}秒"
                cp_s = f"→{ph_cp}" if ph_cp else ""
                phase_lines.append(f"  {p_name}: {ph_name}({dur_s}){cp_s}")

        if self._assign_phases_lbl:
            self._assign_phases_lbl.setText(
                "环节:\n" + "\n".join(phase_lines[:12]) +
                ("\n  ..." if len(phase_lines) > 12 else ""))

        if free_debate and isinstance(free_debate, dict):
            fd_name = free_debate.get("name", "自由辩论")
            fd_dur = free_debate.get("duration", 0)
            fd_cp = free_debate.get("counterpart", "")
            dur_s = f"{fd_dur // 60}分{fd_dur % 60}秒" if fd_dur >= 60 else f"{fd_dur}秒"
            if self._assign_free_lbl:
                self._assign_free_lbl.setText(
                    f"自由辩论: {fd_name}({dur_s}) {'→ ' + fd_cp if fd_cp else ''}")
                self._assign_free_lbl.setVisible(True)
        else:
            if self._assign_free_lbl:
                self._assign_free_lbl.setVisible(False)

        if self._assign_empty_hint:
            self._assign_empty_hint.setVisible(False)
        if self._assign_detail_container:
            self._assign_detail_container.setVisible(True)

    def _show_assign_empty(self):
        """显示未指定状态"""
        if self._assign_empty_hint:
            self._assign_empty_hint.setVisible(True)
        if self._assign_detail_container:
            self._assign_detail_container.setVisible(False)

    def _enable_assign_controls(self, enabled: bool):
        """启用/禁用指定赛制控件"""
        if self._assign_format_combo:
            self._assign_format_combo.setEnabled(enabled)
        if self._assign_save_btn:
            self._assign_save_btn.setEnabled(enabled)

    def _on_assign_combo_changed(self, index: int):
        """下拉框选择变更 → 预览"""
        if self._assign_format_combo is None:
            return
        data = self._assign_format_combo.itemData(index)
        if data and isinstance(data, dict):
            self._show_assign_detail(data["data"])
        else:
            self._show_assign_empty()

    def _on_save_assign_format(self):
        """保存赛制到辩论 JSON 文件"""
        mw = self._mw
        if not mw.current_debate_path or not mw.current_debate_data:
            from components.popup_dialog import CustomDialog
            CustomDialog.warning(self._panel, "无辩论", "请先在项目树中打开一个辩论文件。")
            return
        if self._assign_format_combo is None:
            return

        sel_data = self._assign_format_combo.currentData()
        file_path = mw.current_debate_path

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                debate_data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            from components.popup_dialog import CustomDialog
            CustomDialog.error(self._panel, "读取失败", f"无法读取辩论文件:\n{str(e)}")
            return

        if sel_data and isinstance(sel_data, dict):
            fmt = sel_data["data"]
            debate_data["format"] = {
                "name": fmt.get("name", ""),
                "type": sel_data.get("type", "custom"),
                "team_size": fmt.get("team_size", 0),
                "positions": fmt.get("positions", []),
                "free_debate": fmt.get("free_debate")
            }
        else:
            debate_data.pop("format", None)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(debate_data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            from components.popup_dialog import CustomDialog
            CustomDialog.error(self._panel, "保存失败", f"无法保存辩论文件:\n{str(e)}")
            return

        mw.current_debate_data = debate_data
        mw._display_debate(file_path, debate_data)
        self.refresh_assign_section()
        fmt_name = sel_data["data"]["name"] if sel_data else "不指定"
        if hasattr(mw, '_update_status'):
            mw._update_status(f"已保存赛制: {fmt_name}")

    def _on_edit_assign_format(self):
        """编辑当前选中的赛制 — 切换到编辑视图"""
        if self._assign_format_combo is None:
            return
        sel_data = self._assign_format_combo.currentData()
        if not sel_data or not isinstance(sel_data, dict):
            from components.popup_dialog import CustomDialog
            CustomDialog.information(self._panel, "提示", "请先选择一个赛制。")
            return

        fmt_name = sel_data["name"]
        fmt_copy = json.loads(json.dumps(sel_data["data"], ensure_ascii=False))
        self._switch_page(2)
        self._on_new_format_tab(fmt_copy, fmt_name)

    def _create_browse_page(self) -> QWidget:
        """创建赛制浏览视图"""
        page = QWidget()
        page.setObjectName("tournBrowsePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 0, 10, 10)
        layout.setSpacing(8)

        # 新建按钮 + 导入
        title_row = QHBoxLayout()
        title_row.addStretch()
        btn_new = QPushButton("+ 新建赛制")
        btn_new.setObjectName("aiStructBtn")
        btn_new.setCursor(Qt.PointingHandCursor)
        btn_new.clicked.connect(self._on_new_custom_format)
        title_row.addWidget(btn_new)
        btn_import = QPushButton("📥 导入赛制")
        btn_import.setObjectName("smallBtn")
        btn_import.setCursor(Qt.PointingHandCursor)
        btn_import.clicked.connect(self._on_import_format)
        title_row.addWidget(btn_import)
        layout.addLayout(title_row)

        # 浏览 Tab：预设赛制 + 已保存赛制
        self._format_browse_tab = QTabWidget()
        self._format_browse_tab.setObjectName("formatBrowseTab")
        self._format_browse_tab.setMaximumHeight(260)

        self._preset_format_list = QListWidget()
        self._preset_format_list.setObjectName("formatList")
        self._preset_format_list.setCursor(Qt.PointingHandCursor)
        for name, fmt in COMPETITION_PRESETS.items():
            pos_count = len(fmt["positions"])
            item = QListWidgetItem(f"  {name}  （{pos_count}辩位）")
            item.setData(Qt.UserRole, {"name": name, "data": fmt})
            self._preset_format_list.addItem(item)
        self._preset_format_list.currentRowChanged.connect(self._on_select_preset_format)
        self._format_browse_tab.addTab(self._preset_format_list, "预设赛制")

        self._custom_format_list = QListWidget()
        self._custom_format_list.setObjectName("formatList")
        self._custom_format_list.setCursor(Qt.PointingHandCursor)
        self._custom_format_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._custom_format_list.customContextMenuRequested.connect(self._on_custom_format_context_menu)
        self._custom_format_list.currentRowChanged.connect(self._on_select_custom_format)
        self._custom_format_list.installEventFilter(self._mw)
        self._format_browse_tab.addTab(self._custom_format_list, "已保存赛制")

        layout.addWidget(self._format_browse_tab)

        # 赛制详情预览
        detail_label = QLabel("赛制详情")
        detail_label.setObjectName("tournDetailLabel")
        detail_label.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        layout.addWidget(detail_label)


        self._format_detail_scroll = QScrollArea()
        self._format_detail_scroll.setObjectName("formatDetailScroll")
        self._format_detail_scroll.setWidgetResizable(True)
        self._format_detail = QWidget()
        self._format_detail_layout = QVBoxLayout(self._format_detail)
        self._format_detail_layout.setContentsMargins(12, 10, 12, 10)
        self._format_detail_layout.setSpacing(6)
        self._format_detail_scroll.setWidget(self._format_detail)
        layout.addWidget(self._format_detail_scroll, stretch=1)


        return page

    def _create_assign_page(self) -> QWidget:
        """创建指定赛制页面（QStackedWidget 第 0 页）"""
        page = QWidget()
        page.setObjectName("tournAssignedPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 0, 10, 10)
        layout.setSpacing(8)

        # ── 当前辩论信息 ──
        debate_section = QFrame()
        debate_section.setObjectName("assignFormatSection")
        debate_layout = QVBoxLayout(debate_section)
        debate_layout.setContentsMargins(12, 10, 12, 10)
        debate_layout.setSpacing(6)
        lbl_s1 = QLabel("当前辩论")
        lbl_s1.setObjectName("tournSectionTitle")
        lbl_s1.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        debate_layout.addWidget(lbl_s1)
        self._assign_debate_lbl = QLabel("（未打开辩论）")
        self._assign_debate_lbl.setObjectName("tournSectionSub")
        self._assign_debate_lbl.setFont(QFont("Microsoft YaHei", 10))
        self._assign_debate_lbl.setWordWrap(True)
        debate_layout.addWidget(self._assign_debate_lbl)
        self._assign_debate_section = debate_section
        layout.addWidget(debate_section)

        # ── 已指定赛制详情 ──
        detail_section = QFrame()
        detail_section.setObjectName("assignFormatSection")
        ds_layout = QVBoxLayout(detail_section)
        ds_layout.setContentsMargins(12, 10, 12, 10)
        ds_layout.setSpacing(6)
        lbl_s2 = QLabel("📌 已指定赛制")
        lbl_s2.setObjectName("tournSectionTitle")
        lbl_s2.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        ds_layout.addWidget(lbl_s2)

        self._assign_empty_hint = QLabel("尚无赛制（未指定）")
        self._assign_empty_hint.setObjectName("tournEmptyHint")
        self._assign_empty_hint.setFont(QFont("Microsoft YaHei", 10))
        ds_layout.addWidget(self._assign_empty_hint)

        self._assign_detail_container = QWidget()
        self._assign_detail_container.setVisible(False)
        card_layout = QVBoxLayout(self._assign_detail_container)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(4)

        self._assign_name_lbl = QLabel("")
        self._assign_name_lbl.setObjectName("tournAssignName")
        self._assign_name_lbl.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        card_layout.addWidget(self._assign_name_lbl)

        self._assign_team_lbl = QLabel("")
        self._assign_team_lbl.setObjectName("tournSectionSub")
        self._assign_team_lbl.setFont(QFont("Microsoft YaHei", 10))
        card_layout.addWidget(self._assign_team_lbl)

        self._assign_positions_lbl = QLabel("")
        self._assign_positions_lbl.setObjectName("tournSectionSub")
        self._assign_positions_lbl.setFont(QFont("Microsoft YaHei", 10))
        self._assign_positions_lbl.setWordWrap(True)
        card_layout.addWidget(self._assign_positions_lbl)

        self._assign_phases_lbl = QLabel("")
        self._assign_phases_lbl = QLabel("")
        self._assign_phases_lbl.setObjectName("tournAssignPhases")
        self._assign_phases_lbl.setFont(QFont("Microsoft YaHei", 9))
        self._assign_phases_lbl.setWordWrap(True)
        card_layout.addWidget(self._assign_phases_lbl)

        self._assign_free_lbl = QLabel("")
        self._assign_free_lbl.setObjectName("tournAssignFree")
        self._assign_free_lbl.setFont(QFont("Microsoft YaHei", 10))
        self._assign_free_lbl.setWordWrap(True)
        card_layout.addWidget(self._assign_free_lbl)

        ds_layout.addWidget(self._assign_detail_container)
        layout.addWidget(detail_section)

        # ── 选择赛制 ──
        select_section = QFrame()
        select_section.setObjectName("assignFormatSection")
        ss_layout = QVBoxLayout(select_section)
        ss_layout.setContentsMargins(12, 10, 12, 10)
        ss_layout.setSpacing(8)
        lbl_s3 = QLabel("选择赛制")
        lbl_s3.setObjectName("tournSectionTitle")
        lbl_s3.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        ss_layout.addWidget(lbl_s3)

        self._assign_format_combo = QComboBox()
        self._assign_format_combo.setObjectName("assignFormatCombo")
        self._assign_format_combo.setFont(QFont("Microsoft YaHei", 11))
        self._assign_format_combo.setFixedHeight(34)
        self._assign_format_combo.setCursor(Qt.PointingHandCursor)
        self._assign_format_combo.currentIndexChanged.connect(self._on_assign_combo_changed)
        ss_layout.addWidget(self._assign_format_combo)
        layout.addWidget(select_section)

        # ── 编辑/管理按钮 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        edit_btn = QPushButton("✏️ 编辑此赛制")
        edit_btn.setObjectName("assignFormatBtn")
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setMinimumWidth(120)
        edit_btn.setFixedHeight(34)
        edit_btn.clicked.connect(self._on_edit_assign_format)
        btn_row.addWidget(edit_btn)

        layout.addLayout(btn_row)

        # ── 保存按钮 ──
        self._assign_save_btn = QPushButton("💾 保存赛制到辩论文件")
        self._assign_save_btn.setObjectName("assignFormatSaveBtn")
        self._assign_save_btn.setCursor(Qt.PointingHandCursor)
        self._assign_save_btn.setMinimumWidth(210)
        self._assign_save_btn.setFixedHeight(38)
        self._assign_save_btn.clicked.connect(self._on_save_assign_format)
        layout.addWidget(self._assign_save_btn)

        # ── 提示 ──
        hint = QLabel("💡 一个辩论只能指定一个赛制。修改后需点击保存按钮写入辩论文件。")
        hint.setObjectName("tournMutedHint")
        hint.setFont(QFont("Microsoft YaHei", 9))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ── 无辩论提示 ──
        self._assign_no_debate_hint = QLabel("⚠ 请先在左侧项目树中打开一个辩论文件")
        self._assign_no_debate_hint = QLabel("请先打开一个辩论项目")
        self._assign_no_debate_hint.setObjectName("tournNoDebate")
        self._assign_no_debate_hint.setFont(QFont("Microsoft YaHei", 11))
        self._assign_no_debate_hint.setAlignment(Qt.AlignCenter)
        self._assign_no_debate_hint.setVisible(False)

        layout.insertWidget(1, self._assign_no_debate_hint)
        layout.addStretch()

        return page

    def _create_edit_page(self) -> QWidget:
        """创建赛制编辑视图（滚动单页布局）"""
        page = QWidget()
        page.setObjectName("tournEditPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 0, 10, 10)
        layout.setSpacing(6)

        # 顶部栏
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        back_btn = QPushButton("← 返回浏览")
        back_btn.setObjectName("smallBtn")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self._on_format_edit_back)
        top_bar.addWidget(back_btn)
        top_bar.addStretch()
        self._btn_save_format = QPushButton("保存赛制")
        self._btn_save_format.setObjectName("aiStructBtn")
        self._btn_save_format.setCursor(Qt.PointingHandCursor)
        self._btn_save_format.clicked.connect(self._on_save_current_tab)
        top_bar.addWidget(self._btn_save_format)
        layout.addLayout(top_bar)

        # 编辑滚动区
        edit_scroll = QScrollArea()
        edit_scroll.setObjectName("formatEditScroll")
        edit_scroll.setWidgetResizable(True)

        self._format_tab_widget = QTabWidget()
        self._format_tab_widget.setObjectName("formatTabWidget")
        self._format_tab_widget.setTabsClosable(True)
        self._format_tab_widget.setMovable(True)
        self._format_tab_widget.setMinimumHeight(200)
        self._format_tab_widget.tabCloseRequested.connect(self._on_format_tab_close_index)
        self._format_tab_widget.currentChanged.connect(self._on_format_tab_changed)
        add_btn = QPushButton("+")
        add_btn.setObjectName("cardBtn")
        add_btn.setFixedSize(30, 30)
        add_btn.setToolTip("新建赛制")
        add_btn.clicked.connect(lambda: self._on_new_format_tab())
        self._format_tab_widget.setCornerWidget(add_btn, Qt.TopRightCorner)
        edit_scroll.setWidget(self._format_tab_widget)
        layout.addWidget(edit_scroll, stretch=1)

        return page

    # ============================================================
    # 面板可见性
    # ============================================================

    def toggle_visibility(self) -> bool:
        """切换赛程面板显示/隐藏，返回新状态"""
        self._match_schedule_visible = not self._match_schedule_visible
        if self._panel:
            self._panel.setVisible(self._match_schedule_visible)
        return self._match_schedule_visible

    def set_visible(self, visible: bool):
        """直接设置面板可见性"""
        self._match_schedule_visible = visible
        if self._panel:
            self._panel.setVisible(visible)

    # ============================================================
    # 按键事件处理（供主窗口 eventFilter 委托）
    # ============================================================

    def handle_key_press(self, obj, key: int) -> bool:
        """处理 Delete 键删除已保存赛制"""
        if (obj is self._custom_format_list
                and key == Qt.Key_Delete
                and self._format_browse_tab.currentIndex() == 1):
            self._on_delete_custom_format()
            return True
        return False

    # ============================================================
    # 编辑 Tab 管理
    # ============================================================

    def _on_new_format_tab(self, fmt: dict | None = None, label: str = ""):
        """在编辑视图中新建一个赛制 Tab"""
        self._format_tab_counter += 1
        tab_idx = self._format_tab_counter
        if fmt is None:
            fmt = {"name": "", "positions": [], "free_debate": None, "team_size": 4}
        self._format_tabs_data[tab_idx] = fmt

        tab_widget = QWidget()
        tab_widget.setObjectName("tournTabContent")
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setContentsMargins(0, 6, 0, 0)
        tab_layout.setSpacing(8)

        # ── 赛制名称 + 队伍人数 ──
        basic_card = QFrame()
        basic_card.setObjectName("formatSectionCard")
        basic_layout = QVBoxLayout(basic_card)
        basic_layout.setContentsMargins(14, 12, 14, 12)
        basic_layout.setSpacing(8)
        basic_title = QLabel("基本设置")
        basic_title.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        basic_title.setStyleSheet(f"color: {tc("accent_yellow")};")
        basic_layout.addWidget(basic_title)

        name_row = QHBoxLayout()
        name_lbl = QLabel("赛制名称")
        name_lbl.setObjectName("tournFieldLabel")
        name_input = QLineEdit(fmt.get("name", ""))
        name_input.setObjectName("lineEdit")
        name_input.setPlaceholderText("输入赛制名称...")
        name_input.setFont(QFont("Microsoft YaHei", 12))
        name_input.textChanged.connect(lambda t, idx=tab_idx: self._on_tab_name_changed(idx, t))
        name_row.addWidget(name_lbl)
        name_row.addWidget(name_input, stretch=1)
        basic_layout.addLayout(name_row)
        tab_widget._name_input = name_input

        team_row = QHBoxLayout()
        team_lbl = QLabel("队伍人数")
        team_lbl.setObjectName("tournFieldLabel")
        team_size_combo = QComboBox()
        team_size_combo.setObjectName("formatCombo")
        for ts in range(1, 9):
            team_size_combo.addItem(f"{ts} 人", ts)
        team_size_combo.setCurrentText(f"{fmt.get('team_size', 4)} 人")
        team_size_combo.currentIndexChanged.connect(
            lambda _, idx=tab_idx, cb=team_size_combo: self._update_tab_team_size(idx, cb))
        tab_widget._team_size_combo = team_size_combo
        team_row.addWidget(team_lbl)
        team_row.addWidget(team_size_combo)
        team_row.addStretch()
        basic_layout.addLayout(team_row)
        tab_layout.addWidget(basic_card)
        tab_widget._basic_card = basic_card

        # ── 辩论环节编排 ──
        phases_card = QFrame()
        phases_card.setObjectName("formatSectionCard")
        phases_layout = QVBoxLayout(phases_card)
        phases_layout.setContentsMargins(14, 12, 14, 12)
        phases_layout.setSpacing(8)
        phases_title = QLabel("辩论环节编排")
        phases_title.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        phases_title.setStyleSheet(f"color: {tc("accent_blue")};")
        phases_layout.addWidget(phases_title)

        pos_container = QVBoxLayout()
        pos_container.setSpacing(6)
        tab_widget._pos_container = pos_container
        tab_widget._pos_widgets = {}
        tab_widget._phase_widgets = {}
        phases_layout.addLayout(pos_container)

        add_pos_btn = QPushButton("＋ 添加辩位")
        add_pos_btn.setObjectName("formatAddBtn")
        add_pos_btn.setCursor(Qt.PointingHandCursor)
        add_pos_btn.clicked.connect(lambda _, idx=tab_idx: self._on_add_position(idx))
        phases_layout.addWidget(add_pos_btn)

        # 自由辩论
        free_sep = QFrame()
        free_sep.setFrameShape(QFrame.HLine)
        free_sep.setStyleSheet(f"background-color: {tc("divider")}; max-height: 1px;")
        phases_layout.addWidget(free_sep)
        self._build_free_debate_section(fmt, tab_idx, tab_widget, phases_layout)

        tab_layout.addWidget(phases_card)
        tab_widget._phases_card = phases_card

        # ── 实时预览 ──
        preview_card = QFrame()
        preview_card.setObjectName("formatSectionCard")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(14, 12, 14, 12)
        preview_layout.setSpacing(4)
        preview_title = QLabel("👁 实时预览")
        preview_title.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        preview_title.setStyleSheet(f"color: {tc("accent_green")};")
        preview_layout.addWidget(preview_title)
        preview_content = QWidget()
        preview_content.setObjectName("tournPreviewContent")
        preview_inner = QVBoxLayout(preview_content)
        preview_inner.setContentsMargins(0, 0, 0, 0)
        preview_inner.setSpacing(2)
        preview_layout.addWidget(preview_content)
        tab_layout.addWidget(preview_card)
        tab_widget._preview_card = preview_card
        tab_widget._preview_content = preview_content
        tab_widget._preview_layout = preview_inner

        tab_layout.addStretch()

        # 添加 Tab
        tab_name = label or fmt.get("name") or f"新建赛制{tab_idx}"
        tab_count = self._format_tab_widget.addTab(tab_widget, tab_name)
        self._set_tab_id(tab_count, tab_idx)
        self._format_tab_widget.setCurrentWidget(tab_widget)

        # 初始化辩位编辑行
        for i, pos in enumerate(fmt.get("positions", [])):
            self._add_position_edit_row(tab_idx, i, pos)

        self._refresh_format_preview(tab_idx)

    # ---- Tab ID 管理 ----

    def _get_tab_id_for_widget(self, widget: QWidget) -> int:
        for i in range(self._format_tab_widget.count()):
            if self._format_tab_widget.widget(i) is widget:
                tip = self._format_tab_widget.tabToolTip(i)
                if tip.startswith("tab_"):
                    return int(tip[4:])
        return -1

    def _get_tab_index_widget(self, tab_id: int) -> int:
        for i in range(self._format_tab_widget.count()):
            if self._format_tab_widget.tabToolTip(i) == f"tab_{tab_id}":
                return i
        return -1

    def _set_tab_id(self, tab_widget_idx: int, tab_id: int):
        self._format_tab_widget.setTabToolTip(tab_widget_idx, f"tab_{tab_id}")

    # ---- Tab 回调 ----

    def _on_tab_name_changed(self, tab_idx: int, text: str):
        self._format_tabs_data.setdefault(tab_idx, {})["name"] = text
        tab_widget_idx = self._get_tab_index_widget(tab_idx)
        if tab_widget_idx >= 0:
            self._format_tab_widget.setTabText(
                tab_widget_idx, text if text.strip() else f"新建赛制{tab_idx}")

    def _on_format_tab_close_index(self, tab_widget_idx: int):
        """关闭一个编辑 Tab（由 tabCloseRequested 触发）"""
        if tab_widget_idx < 0 or tab_widget_idx >= self._format_tab_widget.count():
            return
        widget = self._format_tab_widget.widget(tab_widget_idx)
        tab_id = self._get_tab_id_for_widget(widget)
        fmt = self._format_tabs_data.get(tab_id, {})
        name = fmt.get("name") or f"新建赛制{tab_id}"
        if fmt.get("name") or fmt.get("positions"):
            from components.popup_dialog import CustomDialog
            result = CustomDialog.question(
                self._mw, "关闭 Tab", f"关闭「{name}」前是否保存？\n（选择 No 将丢弃未保存内容）",
                buttons=[("取消", "cancel"), ("否", "no"), ("是", "yes")])
            if result == "cancel":
                return
            if result == "yes":
                self._do_save_tab(tab_id)

        if tab_id in self._format_tabs_data:
            del self._format_tabs_data[tab_id]
        self._format_tab_widget.removeTab(tab_widget_idx)

        if self._format_tab_widget.count() == 0:
            self._switch_page(1)  # 返回浏览页

    def _on_format_tab_changed(self, tab_widget_idx: int):
        pass

    def _on_format_edit_back(self):
        has_unsaved = any(
            fmt.get("name") or fmt.get("positions")
            for fmt in self._format_tabs_data.values()
        )
        if has_unsaved:
            from components.popup_dialog import CustomDialog
            result = CustomDialog.question(
                self._mw, "返回浏览", "编辑视图中有未保存的赛制，\n返回后仍可切换回编辑视图。\n确定返回？",
                buttons=[("否", "no"), ("是", "yes")])
            if result == "yes":
                self._switch_page(1)  # 返回浏览页
                self._refresh_format_lists()
        else:
            self._switch_page(1)  # 返回浏览页

    # ============================================================
    # 浏览视图交互
    # ============================================================

    def _on_new_custom_format(self):
        self._switch_page(2)  # 切换到编辑页并更新按钮状态
        self._on_new_format_tab()

    def _on_edit_custom_format(self, list_index: int):
        if list_index < 0 or list_index >= len(self._competition_formats):
            return
        fmt_copy = json.loads(json.dumps(self._competition_formats[list_index], ensure_ascii=False))
        name = fmt_copy.get("name", "自定义赛制")
        self._switch_page(2)  # 切换到编辑页并更新按钮状态
        self._on_new_format_tab(fmt_copy, name)

    def _on_select_preset_format(self, row: int):
        if row < 0:
            return
        item = self._preset_format_list.item(row)
        data = item.data(Qt.UserRole)
        self._current_format = data["data"]
        self._custom_format_list.clearSelection()
        self._render_format_detail(self._current_format, data["name"], "preset")

    def _on_select_custom_format(self, row: int):
        if row < 0:
            return
        self._preset_format_list.clearSelection()
        fmt = self._competition_formats[row]
        self._current_format = fmt
        self._render_format_detail(fmt, fmt.get("name", "自定义赛制"), "custom")

    def _render_format_detail(self, fmt: dict, name: str, fmt_type: str):
        """渲染赛制详情预览"""
        self._clear_layout(self._format_detail_layout)

        type_tag = "预设" if fmt_type == "preset" else "自定义"
        header = QLabel(f"📌 {name}  <span style='color:#6c7086;font-size:12px;'>({type_tag})</span>")
        header.setObjectName("tournSectionTitle")
        header.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        self._format_detail_layout.addWidget(header)

        team_info = QLabel(f"队伍人数: {fmt.get('team_size', '未知')} 人/方")
        team_info.setObjectName("tournSectionSub")
        team_info.setFont(QFont("Microsoft YaHei", 12))
        self._format_detail_layout.addWidget(team_info)

        self._format_detail_layout.addSpacing(4)
        positions = fmt.get("positions", [])
        for pos in positions:
            pos_name = pos.get("name", "?")
            phases = pos.get("phases", [])
            phase_strs = []
            for ph in phases:
                pname = ph.get("name", "?")
                dur = ph.get("duration", 0)
                cp = ph.get("counterpart", "")
                dur_str = f"{int(dur / 60)}分{dur % 60}秒" if dur % 60 else f"{int(dur / 60)}分钟"
                cp_str = f" →对位[{cp}]" if cp and cp != "无（独立环节）" else ""
                phase_strs.append(f"{pname}({dur_str}{cp_str})")
            phases_text = "  →  ".join(phase_strs) if phase_strs else "（无环节）"
            pos_label = QLabel(f"<b style='color:#2E6DDE;'>{pos_name}</b>: {phases_text}")
            pos_label.setFont(QFont("Microsoft YaHei", 12))
            pos_label.setWordWrap(True)
            self._format_detail_layout.addWidget(pos_label)

        free = fmt.get("free_debate")
        if free:
            self._format_detail_layout.addSpacing(4)
            dur = free.get("duration", 0)
            cp = free.get("counterpart", "双方互辩")
            dur_str = f"{int(dur / 60)}分钟" if dur % 60 == 0 else f"{int(dur / 60)}分{dur % 60}秒"
            free_label = QLabel(
                f"<b style='color:#f9e2af;'>自由辩论</b>（公共）: "
                f"{free.get('name', '自由辩论')} ({dur_str}, 对位: {cp})")
            free_label.setFont(QFont("Microsoft YaHei", 12))
            free_label.setWordWrap(True)
            self._format_detail_layout.addWidget(free_label)
        else:
            self._format_detail_layout.addSpacing(4)
            no_free = QLabel("<span style='color:#6c7086;'>（无自由辩论环节）</span>")
            self._format_detail_layout.addWidget(no_free)

        self._format_detail_layout.addStretch()

        if fmt_type == "custom":
            try:
                idx = self._competition_formats.index(fmt)
            except ValueError:
                idx = self._custom_format_list.currentRow()
            btn_row = QHBoxLayout()
            btn_row.setSpacing(8)
            edit_btn = QPushButton("✏️ 编辑此赛制")
            edit_btn.setObjectName("smallBtn")
            edit_btn.setCursor(Qt.PointingHandCursor)
            edit_btn.clicked.connect(lambda _, i=idx: self._on_edit_custom_format(i))
            btn_row.addWidget(edit_btn)
            export_btn = QPushButton("📤 导出赛制")
            export_btn.setObjectName("smallBtn")
            export_btn.setCursor(Qt.PointingHandCursor)
            export_btn.clicked.connect(lambda _, i=idx: self._on_export_format(i))
            btn_row.addWidget(export_btn)
            delete_btn = QPushButton("🗑 删除赛制")
            delete_btn.setObjectName("smallBtn")
            delete_btn.setCursor(Qt.PointingHandCursor)
            delete_btn.setStyleSheet(f"#smallBtn {{ color: {tc('accent_red')}; }} #smallBtn:hover {{ color: {tc('accent_red')}; }}")
            delete_btn.clicked.connect(lambda _, i=idx: self._on_delete_custom_format(i))
            btn_row.addWidget(delete_btn)
            btn_row.addStretch()
            self._format_detail_layout.addLayout(btn_row)

    # ============================================================
    # 保存 / 删除 / 导入 / 导出
    # ============================================================

    def _on_save_current_tab(self):
        current_idx = self._format_tab_widget.currentIndex()
        if current_idx < 0:
            return
        widget = self._format_tab_widget.widget(current_idx)
        tab_id = self._get_tab_id_for_widget(widget)
        self._do_save_tab(tab_id)

    def _do_save_tab(self, tab_id: int):
        fmt = self._format_tabs_data.get(tab_id)
        if not fmt:
            return
        name = fmt.get("name", "").strip()
        if not name:
            from components.popup_dialog import CustomDialog
            CustomDialog.warning(self._mw, "保存失败", "请输入赛制名称。")
            return

        fmt["type"] = "custom"
        if "team_size" not in fmt:
            fmt["team_size"] = len(fmt.get("positions", []))

        existing_idx = -1
        for i, existing in enumerate(self._competition_formats):
            if existing.get("name") == name:
                existing_idx = i
                break

        if existing_idx >= 0:
            self._competition_formats[existing_idx] = fmt
        else:
            self._competition_formats.append(fmt)

        self._save_competition_formats()
        self._refresh_format_lists()
        self._mw._refresh_train_format_combo()
        tab_widget_idx = self._get_tab_index_widget(tab_id)
        if tab_widget_idx >= 0:
            self._format_tab_widget.setTabText(tab_widget_idx, name)
        if hasattr(self._mw, '_update_status'):
            self._mw._update_status(f"赛制「{name}」已保存")

    def _on_custom_format_context_menu(self, pos):
        item = self._custom_format_list.itemAt(pos)
        if not item:
            return
        self._custom_format_list.setCurrentItem(item)
        menu = QMenu(self._mw)
        menu.setObjectName("treeContextMenu")
        action_delete = menu.addAction("🗑 删除此赛制")
        action_delete.triggered.connect(lambda: self._on_delete_custom_format())
        action_export = menu.addAction("📤 导出此赛制")
        action_export.triggered.connect(
            lambda: self._on_export_format(self._custom_format_list.currentRow()))
        menu.exec_(self._custom_format_list.mapToGlobal(pos))

    def _on_delete_custom_format(self, list_index: int = -1):
        if list_index < 0:
            list_index = self._custom_format_list.currentRow()
        if list_index < 0 or list_index >= len(self._competition_formats):
            from components.popup_dialog import CustomDialog
            CustomDialog.information(self._mw, "提示", "请先在列表中选择要删除的赛制。")
            return
        name = self._competition_formats[list_index].get("name", "未知")
        result = CustomDialog.question(
            self._mw, "确认删除", f"确定要删除赛制「{name}」吗？",
            buttons=[("否", "no"), ("是", "yes")])
        if result != "yes":
            return
        del self._competition_formats[list_index]
        self._save_competition_formats()
        self._refresh_format_lists()
        self._mw._refresh_train_format_combo()
        self._clear_layout(self._format_detail_layout)
        if hasattr(self._mw, '_update_status'):
            self._mw._update_status(f"赛制「{name}」已删除")

    def _on_import_format(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self._mw, "导入赛制", "",
            "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                fmt = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            from components.popup_dialog import CustomDialog
            CustomDialog.warning(self._mw, "导入失败", f"无法读取文件:\n{str(e)}")
            return

        if not isinstance(fmt, dict) or "name" not in fmt or "positions" not in fmt:
            CustomDialog.warning(self._mw, "导入失败", "文件格式不正确，缺少必要的赛制字段（name, positions）。")
            return

        name = fmt.get("name", "导入赛制")
        existing_names = [f.get("name", "") for f in self._competition_formats]
        if name in existing_names:
            from components.popup_dialog import CustomDialog
            result = CustomDialog.question(
                self._mw, "名称冲突",
                f"已存在同名赛制「{name}」，是否覆盖？",
                buttons=[("否", "no"), ("是", "yes")])
            if result == "yes":
                for i, f in enumerate(self._competition_formats):
                    if f.get("name", "") == name:
                        self._competition_formats[i] = fmt
                        break
            else:
                return
        else:
            self._competition_formats.append(fmt)

        self._save_competition_formats()
        self._refresh_format_lists()
        self._mw._refresh_train_format_combo()
        self._format_browse_tab.setCurrentIndex(1)
        if hasattr(self._mw, '_update_status'):
            self._mw._update_status(f"赛制「{name}」已导入")

    def _on_export_format(self, list_index: int):
        if list_index < 0 or list_index >= len(self._competition_formats):
            return
        fmt = self._competition_formats[list_index]
        name = fmt.get("name", "未命名")
        safe_name = "".join(c for c in name if c.isalnum() or c in "() -_").strip()
        if not safe_name:
            safe_name = "competition_format"

        filepath, _ = QFileDialog.getSaveFileName(
            self._mw, "导出赛制", f"{safe_name}.json",
            "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not filepath:
            return
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(fmt, f, ensure_ascii=False, indent=2)
        except OSError as e:
            from components.popup_dialog import CustomDialog
            CustomDialog.warning(self._mw, "导出失败", f"无法写入文件:\n{str(e)}")
            return
        if hasattr(self._mw, '_update_status'):
            self._mw._update_status(f"赛制「{name}」已导出至 {os.path.basename(filepath)}")

    # ============================================================
    # 辩位 / 环节编辑
    # ============================================================

    def _add_position_edit_row(self, tab_id: int, pos_idx: int, pos_data: dict | None = None):
        tab_widget_idx = self._get_tab_index_widget(tab_id)
        if tab_widget_idx < 0:
            return
        tab_w = self._format_tab_widget.widget(tab_widget_idx)
        if not hasattr(tab_w, '_pos_container'):
            return

        fmt = self._format_tabs_data.setdefault(
            tab_id, {"name": "", "positions": [], "free_debate": None, "team_size": 4})
        while len(fmt.setdefault("positions", [])) <= pos_idx:
            fmt["positions"].append({"name": "", "phases": []})

        if pos_data is None:
            pos_data = fmt["positions"][pos_idx] if pos_idx < len(fmt["positions"]) else {
                "name": f"辩位{pos_idx + 1}", "phases": []}
        if pos_idx < len(fmt["positions"]):
            fmt["positions"][pos_idx] = pos_data
        else:
            fmt["positions"].append(pos_data)

        # 辩位卡片
        pos_card = QFrame()
        pos_card.setObjectName("positionCard")
        pc_layout = QVBoxLayout(pos_card)
        pc_layout.setContentsMargins(12, 8, 12, 8)
        pc_layout.setSpacing(6)

        # 顶部：辩位名称 + 删除按钮
        top_row = QHBoxLayout()
        pos_label_inner = QLabel(f"辩位{pos_idx + 1} ·")
        pos_label_inner.setObjectName("tournSectionSub")
        top_row.addWidget(pos_label_inner)

        pos_name = QLineEdit(pos_data.get("name", ""))
        pos_name.setObjectName("lineEdit")
        pos_name.setPlaceholderText("辩位名称")
        pos_name.setFixedWidth(100)
        pos_name.textChanged.connect(
            lambda t, tid=tab_id, pi=pos_idx: self._update_tab_pos_name(tid, pi, t))
        top_row.addWidget(pos_name)
        top_row.addStretch()

        del_pos_btn = QPushButton("删除")
        del_pos_btn.setObjectName("tournDelBtn")
        del_pos_btn.setCursor(Qt.PointingHandCursor)
        del_pos_btn.clicked.connect(lambda _, tid=tab_id, pi=pos_idx: self._on_remove_position(tid, pi))
        top_row.addWidget(del_pos_btn)
        pc_layout.addLayout(top_row)

        # 环节卡片行
        phases_flow = QHBoxLayout()
        phases_flow.setSpacing(8)
        phase_frames = []
        for pi, phase in enumerate(pos_data.get("phases", [])):
            pf = self._create_phase_card(tab_id, pos_idx, pi, phase)
            phase_frames.append(pf)

        self._populate_phase_cards(phases_flow, phase_frames)
        pc_layout.addLayout(phases_flow)
        pos_card._phases_flow = phases_flow

        add_phase_btn = QPushButton("＋ 添加环节")
        add_phase_btn.setCursor(Qt.PointingHandCursor)
        add_phase_btn.setObjectName("tournAddPhaseBtn")
        add_phase_btn.clicked.connect(lambda _, tid=tab_id, pi=pos_idx: self._on_add_phase(tid, pi))
        pc_layout.addWidget(add_phase_btn)

        pos_card._phase_frames = phase_frames
        pos_card._pos_name_input = pos_name

        pos_container = tab_w._pos_container
        pos_container.addWidget(pos_card)
        tab_w._pos_widgets[pos_idx] = pos_card
        tab_w._phase_widgets[pos_idx] = phase_frames

    def _create_phase_card(self, tab_id: int, pos_idx: int, phase_idx: int,
                            phase_data: dict) -> QFrame:
        card = QFrame()
        card.setFixedWidth(170)
        card.setObjectName("tournPhaseCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(8, 6, 8, 6)
        cl.setSpacing(4)

        phase_combo = QComboBox()
        phase_combo.setObjectName("formatCombo")
        phase_combo.setEditable(True)
        phase_combo.setMinimumWidth(100)
        for p in AVAILABLE_PHASES:
            phase_combo.addItem(p)
        phase_combo.setCurrentText(phase_data.get("name", ""))
        phase_combo.currentTextChanged.connect(
            lambda t, tid=tab_id, pi=pos_idx, phi=phase_idx:
            self._update_tab_phase_name(tid, pi, phi, t))
        cl.addWidget(phase_combo)

        mid_row = QHBoxLayout()
        mid_row.setSpacing(4)
        dur_combo = QComboBox()
        dur_combo.setObjectName("formatCombo")
        dur_combo.setEditable(True)
        for d in AVAILABLE_DURATIONS:
            d_min, d_sec = d // 60, d % 60
            dur_combo.addItem(f"{d_min}分{d_sec}秒" if d_sec else f"{d_min}分钟", d)
        dur_val = phase_data.get("duration", 120)
        fd_idx = dur_combo.findData(dur_val)
        if fd_idx >= 0:
            dur_combo.setCurrentIndex(fd_idx)
        else:
            d_min, d_sec = divmod(dur_val, 60)
            dur_combo.setCurrentText(f"{d_min}分{d_sec}秒" if d_sec else f"{d_min}分钟")
        dur_combo.currentTextChanged.connect(
            lambda t, tid=tab_id, pi=pos_idx, phi=phase_idx:
            self._update_tab_phase_duration(tid, pi, phi, t))
        mid_row.addWidget(dur_combo)

        cp_combo = QComboBox()
        cp_combo.setObjectName("formatCombo")
        cp_combo.setEditable(True)
        cp_combo.setMinimumWidth(60)
        cp_combo.setToolTip("对位")
        for cp in COUNTERPART_OPTIONS:
            cp_combo.addItem(cp)
        cp_combo.setCurrentText(phase_data.get("counterpart", "无（独立环节）"))
        cp_combo.currentTextChanged.connect(
            lambda t, tid=tab_id, pi=pos_idx, phi=phase_idx:
            self._update_tab_phase_counterpart(tid, pi, phi, t))
        mid_row.addWidget(cp_combo)
        cl.addLayout(mid_row)

        del_btn = QPushButton("✕ 移除")
        del_btn.setObjectName("tournPhaseDelBtn")
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(
            lambda _, tid=tab_id, pi=pos_idx, phi=phase_idx:
            self._on_remove_phase(tid, pi, phi))
        cl.addWidget(del_btn)

        card._phase_combo = phase_combo
        card._dur_combo = dur_combo
        card._cp_combo = cp_combo
        return card

    @staticmethod
    def _populate_phase_cards(flow_layout: QHBoxLayout, phase_frames: list):
        while flow_layout.count():
            item = flow_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        for pf in phase_frames:
            flow_layout.addWidget(pf)
        flow_layout.addStretch()

    # ---- Tab 数据更新 ----

    def _update_tab_pos_name(self, tab_id: int, pos_idx: int, text: str):
        fmt = self._format_tabs_data.get(tab_id, {})
        positions = fmt.get("positions", [])
        if pos_idx < len(positions):
            positions[pos_idx]["name"] = text
        self._refresh_format_preview(tab_id)

    def _update_tab_team_size(self, tab_id: int, combo: QComboBox):
        fmt = self._format_tabs_data.get(tab_id, {})
        fmt["team_size"] = combo.currentData()
        self._refresh_format_preview(tab_id)

    def _update_tab_phase_name(self, tab_id: int, pos_idx: int, phase_idx: int, text: str):
        fmt = self._format_tabs_data.get(tab_id, {})
        positions = fmt.get("positions", [])
        if pos_idx < len(positions) and phase_idx < len(positions[pos_idx].get("phases", [])):
            positions[pos_idx]["phases"][phase_idx]["name"] = text
        self._refresh_format_preview(tab_id)

    def _update_tab_phase_duration(self, tab_id: int, pos_idx: int, phase_idx: int, text: str):
        dur = self._parse_duration(text)
        fmt = self._format_tabs_data.get(tab_id, {})
        positions = fmt.get("positions", [])
        if pos_idx < len(positions) and phase_idx < len(positions[pos_idx].get("phases", [])):
            positions[pos_idx]["phases"][phase_idx]["duration"] = dur
        self._refresh_format_preview(tab_id)

    def _update_tab_phase_counterpart(self, tab_id: int, pos_idx: int, phase_idx: int, text: str):
        fmt = self._format_tabs_data.get(tab_id, {})
        positions = fmt.get("positions", [])
        if pos_idx < len(positions) and phase_idx < len(positions[pos_idx].get("phases", [])):
            positions[pos_idx]["phases"][phase_idx]["counterpart"] = text
        self._refresh_format_preview(tab_id)

    # ---- 添加/移除 ----

    def _on_add_phase(self, tab_id: int, pos_idx: int):
        fmt = self._format_tabs_data.get(tab_id, {})
        positions = fmt.get("positions", [])
        if pos_idx < len(positions):
            positions[pos_idx].setdefault("phases", []).append(
                {"name": "", "duration": 120, "counterpart": "无（独立环节）"})
            self._rebuild_format_tab_ui(tab_id)
            self._refresh_format_preview(tab_id)

    def _on_remove_phase(self, tab_id: int, pos_idx: int, phase_idx: int):
        fmt = self._format_tabs_data.get(tab_id, {})
        positions = fmt.get("positions", [])
        if pos_idx < len(positions) and phase_idx < len(positions[pos_idx].get("phases", [])):
            del positions[pos_idx]["phases"][phase_idx]
            self._rebuild_format_tab_ui(tab_id)
            self._refresh_format_preview(tab_id)

    def _on_add_position(self, tab_id: int):
        fmt = self._format_tabs_data.setdefault(
            tab_id, {"name": "", "positions": [], "free_debate": None, "team_size": 4})
        idx = len(fmt.setdefault("positions", []))
        fmt["positions"].append({"name": f"辩位{idx + 1}", "phases": []})
        self._add_position_edit_row(tab_id, idx, fmt["positions"][idx])
        self._refresh_format_preview(tab_id)

    def _on_remove_position(self, tab_id: int, pos_idx: int):
        fmt = self._format_tabs_data.get(tab_id, {})
        positions = fmt.get("positions", [])
        if pos_idx >= len(positions):
            return
        name = positions[pos_idx].get("name", "该辩位")
        from components.popup_dialog import CustomDialog
        result = CustomDialog.question(
            self._mw, "确认删除", f"确定要删除「{name}」吗？",
            buttons=[("否", "no"), ("是", "yes")])
        if result != "yes":
            return
        del positions[pos_idx]
        self._rebuild_format_tab_ui(tab_id)
        self._refresh_format_preview(tab_id)

    def _rebuild_format_tab_ui(self, tab_id: int):
        tab_widget_idx = self._get_tab_index_widget(tab_id)
        if tab_widget_idx < 0:
            return
        fmt = self._format_tabs_data.get(tab_id)
        if not fmt:
            return
        tab_w = self._format_tab_widget.widget(tab_widget_idx)
        pos_container = getattr(tab_w, '_pos_container', None)
        if pos_container:
            self._clear_layout(pos_container)
        for i, pos in enumerate(fmt.get("positions", [])):
            self._add_position_edit_row(tab_id, i, pos)

    # ============================================================
    # 自由辩论编辑
    # ============================================================

    def _build_free_debate_section(self, fmt: dict, tab_idx: int, tab_widget: QWidget,
                                    parent_layout: QVBoxLayout):
        fd_card = QFrame()
        fd_card.setObjectName("freeDebateCard")
        fd_layout = QVBoxLayout(fd_card)
        fd_layout.setContentsMargins(12, 10, 12, 10)
        fd_layout.setSpacing(6)

        fd_title_row = QHBoxLayout()
        fd_title = QLabel("⭐ 自由辩论（双方交替发言 · 公共环节）")
        fd_title.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        fd_title.setStyleSheet(f"color: {tc("accent_yellow")};")
        fd_title_row.addWidget(fd_title)
        fd_title_row.addStretch()

        free_enable = QPushButton()
        free_enable.setCheckable(True)
        free_enable.setChecked(fmt.get("free_debate") is not None)
        free_enable.setFixedSize(56, 24)
        free_enable.setObjectName("freeToggleBtn")
        free_enable.setCursor(Qt.PointingHandCursor)
        free_enable.setText("OFF" if not free_enable.isChecked() else "ON")
        free_enable.toggled.connect(lambda checked: free_enable.setText("ON" if checked else "OFF"))
        fd_title_row.addWidget(free_enable)
        fd_layout.addLayout(fd_title_row)
        tab_widget._free_debate_enable = free_enable

        fd_ctrl = QHBoxLayout()
        fd_ctrl.setSpacing(10)

        fd_phase_lbl = QLabel("环节")
        fd_phase_lbl.setStyleSheet(f"color: {tc("subtext")}; font-size: 12px;")
        fd_ctrl.addWidget(fd_phase_lbl)
        free_phase = QComboBox()
        free_phase.setObjectName("formatCombo")
        free_phase.setEditable(True)
        free_phase.setFixedWidth(110)
        for p in AVAILABLE_PHASES:
            free_phase.addItem(p)
        free_phase.setCurrentText((fmt.get("free_debate") or {}).get("name", "自由辩论"))
        fd_ctrl.addWidget(free_phase)
        tab_widget._free_debate_phase = free_phase

        fd_dur_lbl = QLabel("时长")
        fd_dur_lbl.setObjectName("tournFieldLabel")
        fd_ctrl.addWidget(fd_dur_lbl)
        free_dur = QComboBox()
        free_dur.setObjectName("formatCombo")
        free_dur.setEditable(True)
        free_dur.setFixedWidth(90)
        for d in AVAILABLE_DURATIONS:
            d_min, d_sec = d // 60, d % 60
            free_dur.addItem(f"{d_min}分{d_sec}秒" if d_sec else f"{d_min}分钟", d)
        if fmt.get("free_debate"):
            dur = fmt["free_debate"].get("duration", 480)
            fd_idx = free_dur.findData(dur)
            if fd_idx >= 0:
                free_dur.setCurrentIndex(fd_idx)
            else:
                free_dur.setCurrentText(f"{dur // 60}分{dur % 60}秒")
        fd_ctrl.addWidget(free_dur)
        tab_widget._free_debate_duration = free_dur
        fd_ctrl.addStretch()
        fd_layout.addLayout(fd_ctrl)

        # 自由辩论对位
        fd_cp_row = QHBoxLayout()
        fd_cp_lbl = QLabel("对位")
        fd_cp_lbl.setObjectName("tournFieldLabel")
        fd_cp_row.addWidget(fd_cp_lbl)
        free_cp = QComboBox()
        free_cp.setObjectName("formatCombo")
        free_cp.setEditable(True)
        free_cp.setFixedWidth(110)
        for cp in COUNTERPART_OPTIONS:
            free_cp.addItem(cp)
        free_cp.setCurrentText((fmt.get("free_debate") or {}).get("counterpart", "双方互辩"))
        fd_cp_row.addWidget(free_cp)
        tab_widget._free_debate_counterpart = free_cp
        fd_cp_row.addStretch()
        fd_layout.addLayout(fd_cp_row)

        # 信号绑定
        def _on_free_toggle(checked, idx=tab_idx):
            self._sync_free_debate_full(idx)
            self._refresh_format_preview(idx)

        def _on_free_param_changed(text, idx=tab_idx):
            self._sync_free_debate_full(idx)
            self._refresh_format_preview(idx)

        free_enable.toggled.connect(_on_free_toggle)
        free_phase.currentTextChanged.connect(_on_free_param_changed)
        free_dur.currentTextChanged.connect(_on_free_param_changed)
        free_cp.currentTextChanged.connect(_on_free_param_changed)

        parent_layout.addWidget(fd_card)
        tab_widget._free_debate_card = fd_card

    # ============================================================
    # 实时预览
    # ============================================================

    def _refresh_format_preview(self, tab_id: int):
        tab_widget_idx = self._get_tab_index_widget(tab_id)
        if tab_widget_idx < 0:
            return
        tab_w = self._format_tab_widget.widget(tab_widget_idx)
        preview_layout = getattr(tab_w, '_preview_layout', None)
        if not preview_layout:
            return
        fmt = self._format_tabs_data.get(tab_id, {})
        self._clear_layout(preview_layout)

        pos_colors = ["#89b4fa", "#a6e3a1", "#2E6DDE", "#f9e2af", "#f38ba8", "#94e2d5", "#fab387", "#b4befe"]
        total_phases = 0
        total_seconds = 0

        for i, pos in enumerate(fmt.get("positions", [])):
            color = pos_colors[i % len(pos_colors)]
            pos_name = pos.get("name", f"辩位{i + 1}")
            phases = pos.get("phases", [])
            phase_strs = []
            for ph in phases:
                pname = ph.get("name", "?")
                dur = ph.get("duration", 0)
                cp = ph.get("counterpart", "")
                dur_str = f"{dur // 60}分{dur % 60}秒" if dur % 60 else f"{dur // 60}分钟"
                cp_str = f" → {cp}" if cp and cp != "无（独立环节）" else ""
                phase_strs.append(f"{pname}({dur_str}{cp_str})")
                total_phases += 1
                total_seconds += dur

            line = QLabel(
                f"<span style='color:{color};'>▓</span> "
                f"<b style='color:{color};'>{pos_name}</b>  "
                f"<span style='color:#a6adc8;'>{'  →  '.join(phase_strs) if phase_strs else '（无环节）'}</span>"
            )
            line.setFont(QFont("Microsoft YaHei", 10))
            line.setWordWrap(True)
            preview_layout.addWidget(line)

        free = fmt.get("free_debate")
        if free:
            fd_name = free.get("name", "自由辩论")
            fd_dur = free.get("duration", 0)
            fd_cp = free.get("counterpart", "双方互辩")
            fd_dur_str = f"{fd_dur // 60}分{fd_dur % 60}秒" if fd_dur % 60 else f"{fd_dur // 60}分钟"
            fd_line = QLabel(
                f"<span style='color:#f9e2af;'>⭐</span> "
                f"<b style='color:#f9e2af;'>{fd_name}</b>"
                f"<span style='color:#a6adc8;'>（{fd_cp}, {fd_dur_str}）</span>"
            )
            fd_line.setFont(QFont("Microsoft YaHei", 10))
            fd_line.setWordWrap(True)
            preview_layout.addWidget(fd_line)
            total_phases += 1
            total_seconds += fd_dur

        preview_layout.addSpacing(4)
        total_min = total_seconds // 60
        total_sec = total_seconds % 60
        ts_str = f"{total_min}分{total_sec}秒" if total_sec else f"{total_min}分钟"
        summary = QLabel(
            f"<span style='color:#6c7086;'>📊 共计 {len(fmt.get('positions', []))} 辩位"
            f" · {total_phases} 个环节 · 约 {ts_str}</span>"
        )
        summary.setFont(QFont("Microsoft YaHei", 10))
        preview_layout.addWidget(summary)
        preview_layout.addStretch()

    # ============================================================
    # 同步自由辩论
    # ============================================================

    def _sync_free_debate_full(self, tab_id: int):
        tab_widget_idx = self._get_tab_index_widget(tab_id)
        if tab_widget_idx < 0:
            return
        tab_w = self._format_tab_widget.widget(tab_widget_idx)
        fmt = self._format_tabs_data.setdefault(
            tab_id, {"name": "", "positions": [], "free_debate": None, "team_size": 4})
        if hasattr(tab_w, '_free_debate_enable') and tab_w._free_debate_enable.isChecked():
            fmt["free_debate"] = {
                "name": tab_w._free_debate_phase.currentText(),
                "duration": self._parse_duration(tab_w._free_debate_duration.currentText()),
                "counterpart": (tab_w._free_debate_counterpart.currentText()
                                if hasattr(tab_w, '_free_debate_counterpart') else "双方互辩"),
            }
        else:
            fmt["free_debate"] = None

    # ============================================================
    # 工具方法
    # ============================================================


    @staticmethod
    def _parse_duration(text: str) -> int:
        """解析时长字符串为秒数"""
        text = text.strip()
        if not text:
            return 120
        if "分" in text:
            try:
                clean = text.replace("钟", "").strip()
                if "秒" in clean:
                    parts = clean.replace("秒", "").split("分")
                    minutes = int(float(parts[0].strip())) if parts[0].strip() else 0
                    seconds = int(float(parts[1].strip())) if len(parts) > 1 and parts[1].strip() else 0
                    return minutes * 60 + seconds
                return int(float(clean.replace("分", "").strip()) * 60)
            except ValueError:
                pass
        if text.lower().endswith("min"):
            try:
                return int(float(text[:-3].strip()) * 60)
            except ValueError:
                pass
        m = re.search(r'(\d+)', text)
        if m:
            return int(m.group(1))
        return 120

    @staticmethod
    def _clear_layout(layout: QLayout):
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                TournamentManager._clear_layout(item.layout())

    # ============================================================
    # 列表刷新
    # ============================================================

    def _refresh_format_lists(self):
        """刷新自定义赛制列表（安全：面板未构建时跳过）"""
        if self._custom_format_list is None or self._format_browse_tab is None:
            return
        self._custom_format_list.clear()
        for fmt in self._competition_formats:
            name = fmt.get("name", "未命名")
            pos_count = len(fmt.get("positions", []))
            item = QListWidgetItem(f"  {name}  （{pos_count}辩位）")
            item.setData(Qt.UserRole, fmt)
            self._custom_format_list.addItem(item)
        count = len(self._competition_formats)
        self._format_browse_tab.setTabText(1, f"已保存赛制 ({count})")

    # ============================================================
    # 外部查询 API
    # ============================================================

    def get_positions_for_format(self, format_name: str) -> list[str]:
        """根据赛制名称返回该赛制的辩位列表（供训练面板调用）"""
        if not format_name:
            return ["一辩", "二辩", "三辩", "四辩", "混合"]
        if format_name in COMPETITION_PRESETS:
            preset = COMPETITION_PRESETS[format_name]
            positions = []
            seen = set()
            for p in preset["positions"]:
                name = p["name"]
                if name not in seen:
                    positions.append(name)
                    seen.add(name)
            positions.append("混合")
            return positions
        for fmt in self._competition_formats:
            if fmt.get("name", "") == format_name:
                positions = []
                seen = set()
                for p in fmt.get("positions", []):
                    name = p.get("name", "")
                    if name and name not in seen:
                        positions.append(name)
                        seen.add(name)
                positions.append("混合")
                return positions
        return ["一辩", "二辩", "三辩", "四辩", "混合"]

    def refresh_train_combo(self, combo: QComboBox):
        """刷新训练面板的赛制下拉框（供主窗口调用）"""
        prev_text = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("不限制（混合出题）", "")
        for name in COMPETITION_PRESETS.keys():
            combo.addItem(name, name)
        for fmt in self._competition_formats:
            combo.addItem(fmt.get("name", ""), fmt.get("name", ""))
        found_idx = combo.findText(prev_text)
        if found_idx >= 0:
            combo.setCurrentIndex(found_idx)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    # ============================================================
    # 数据持久化
    # ============================================================

    @staticmethod
    def _sanitize_format_filename(name: str) -> str:
        safe = "".join(c for c in name if c.isalnum() or c in "() -_").strip()
        return safe if safe else "unnamed_format"

    def load_competition_formats(self):
        """加载已保存的自定义赛制（优先从 custom_formats/ 目录加载独立文件）"""
        if os.path.isdir(self._competition_formats_dir):
            formats = []
            try:
                for fname in sorted(os.listdir(self._competition_formats_dir)):
                    if not fname.endswith(".json"):
                        continue
                    fpath = os.path.join(self._competition_formats_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            fmt = json.load(f)
                        if isinstance(fmt, dict) and "name" in fmt and "positions" in fmt:
                            formats.append(fmt)
                    except (json.JSONDecodeError, OSError):
                        continue
            except OSError:
                pass
            if formats:
                self._competition_formats = formats
                self._refresh_format_lists()  # 加载后刷新 UI 列表
                return

        if not os.path.isfile(self._competition_formats_file):
            self._competition_formats = []
            self._refresh_format_lists()
            return
        try:
            with open(self._competition_formats_file, "r", encoding="utf-8") as f:
                self._competition_formats = json.load(f)
        except (json.JSONDecodeError, OSError):
            self._competition_formats = []

        if self._competition_formats:
            self._save_competition_formats()

        self._refresh_format_lists()  # 加载后刷新 UI 列表

    def _save_competition_formats(self):
        os.makedirs(self._competition_formats_dir, exist_ok=True)

        saved_names = set()
        for fmt in self._competition_formats:
            name = fmt.get("name", "未命名")
            safe = self._sanitize_format_filename(name)
            base_name = safe
            counter = 2
            while safe in saved_names:
                safe = f"{base_name}_{counter}"
                counter += 1
            saved_names.add(safe)
            fpath = os.path.join(self._competition_formats_dir, f"{safe}.json")
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(fmt, f, ensure_ascii=False, indent=2)
            except OSError:
                pass

        try:
            for fname in os.listdir(self._competition_formats_dir):
                if fname.endswith(".json"):
                    stem = fname[:-5]
                    if stem not in saved_names:
                        try:
                            os.remove(os.path.join(self._competition_formats_dir, fname))
                        except OSError:
                            pass
        except OSError:
            pass

        try:
            with open(self._competition_formats_file, "w", encoding="utf-8") as f:
                json.dump(self._competition_formats, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
