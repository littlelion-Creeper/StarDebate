from components.theme_colors import tc, refresh
from components.star_button import StarButton
"""
NotesManager — 便签面板管理器
==============================
负责便签面板的全部 UI 构建与业务逻辑，遵循多文件模块化规则。

功能覆盖：
- 便签面板 UI 构建（标题栏 + 搜索 + 卡片区 + 可折叠输入区）
- 右侧导航按钮创建
- 面板互斥切换
- 便签 CRUD：添加/删除/清空/置顶/改色
- 搜索过滤（防抖 300ms，按命中次数排序，关键词高亮）
- 卡片动态布局（展开/折叠、宽度自适应）
- 贴纸模式（独立置顶窗口）
- 拖放排序（跨区限制：置顶/普通不能互相拖入）
- 一键导出 Markdown/TXT
- 事件过滤委托（scroll resize + Ctrl+Enter 快捷添加）

对外 API（主窗口调用）：
| 属性/方法 | 说明 |
|----------|------|
| build_panel() | 构建面板 UI，返回 QFrame |
| build_nav_button(parent_layout) | 创建右导航按钮 + 标签 |
| toggle_visibility() | 切换面板显示/隐藏 |
| close_if_open() | 关闭面板（互斥调用） |
| visible | @property 面板可见状态 |
| panel | @property QFrame 面板引用 |
| handle_event_filter(obj, event) | eventFilter 委托 |
| handle_scroll_resize() | scroll resize 防抖处理 |
"""

import os
import json
import datetime
import re
import ctypes

from PyQt5.QtCore import (
    Qt, QRect, QPoint, QSize, QMimeData, QTimer
)
from PyQt5.QtGui import (
    QFont, QFontMetrics, QColor, QIcon, QPixmap, QDrag
)
from PyQt5.QtWidgets import (
    QUndoStack,
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QLineEdit, QPlainTextEdit,
    QMenu, QApplication, QFileDialog,
    QSizePolicy
)

from components.popup_dialog import CustomDialog
from components.undo_commands import TextEditCommandMerger
from workers.nav_bar.nav_bar_manager import NavBarManager


# ============================================================
#  颜色映射（便签卡片的五种预设色）
# ============================================================
NOTE_COLOR_MAP: dict[str, str] = {
    "green": "#a6e3a1",
    "yellow": "#f9e2af",
    "orange": "#fab387",
    "red": "#f38ba8",
    "purple": "#2E6DDE",
}


class NotesManager:
    """便签面板管理器：UI + 业务逻辑 + 事件处理"""

    # ── 初始化 ────────────────────────────────────────────

    def __init__(self, mw):
        """mw: StarDebateWindow 主窗口实例"""
        self._mw = mw

        # 面板可见性
        self._visible: bool = False

        # 便签数据
        self._notes_data: list[dict] = []
        self._next_note_id: int = 1
        self._notes_selected_color: str = "green"

        # 输入区状态
        self._notes_input_expanded: bool = False

        # 搜索
        self._notes_search_text: str = ""
        self._notes_search_timer: QTimer | None = None

        # 卡片组件列表
        self._notes_cards: list[QFrame] = []

        # 拖放
        self._notes_drag_source: QFrame | None = None

        # 贴纸模式
        self._sticker_windows: dict[int, QWidget] = {}

        # 卡片列表重排防抖
        self._reflow_timer: QTimer | None = None

        # ── UI 控件引用（在 build_panel 中赋值）──
        self._panel: QFrame | None = None
        self._search_input: QLineEdit | None = None
        self._scroll: QScrollArea | None = None
        self._container: QWidget | None = None
        self._list_layout: QVBoxLayout | None = None
        self._input_area: QWidget | None = None
        self._notes_input: QPlainTextEdit | None = None
        self._lbl_status: QLabel | None = None
        self._btn_toggle_input: QPushButton | None = None
        self._color_buttons: dict[str, QPushButton] = {}

        # 导航按钮（外部持有引用）
        self._btn_toggle: QPushButton | None = None


        # ── 撤销栈 ──────────────────────────────────────
        self._undo_stack = QUndoStack()
        from components.undo_coordinator import UndoCoordinator
        UndoCoordinator.instance().register_stack("notes", self._undo_stack)

    # ── 对外属性 ──────────────────────────────────────────

    @property
    def visible(self) -> bool:
        return self._visible

    @property
    def panel(self) -> QFrame | None:
        return self._panel

    @property
    def cards_scroll(self) -> QScrollArea | None:
        return self._scroll

    @property
    def cards(self) -> list[QFrame]:
        return self._notes_cards

    @property
    def btn_toggle(self) -> QPushButton | None:
        return self._btn_toggle

    @property
    def notes_data(self) -> list[dict]:
        """获取全部便签数据（供一辩稿绑定弹窗使用）"""
        return list(self._notes_data)

    # ============================================================
    #  UI 构建
    # ============================================================

    def build_panel(self) -> QFrame:
        """构建便签面板 UI，返回 QFrame"""
        panel = QFrame()
        panel.setObjectName("notesPanel")
        panel.setMinimumWidth(480)
        panel.setMaximumWidth(2400)
        notes_layout = QVBoxLayout(panel)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        notes_layout.setSpacing(0)

        # ── 标题栏 ──
        notes_header = QFrame()
        notes_header.setObjectName("notesHeader")
        notes_header.setFixedHeight(88)
        notes_header_layout = QVBoxLayout(notes_header)
        notes_header_layout.setContentsMargins(12, 6, 12, 6)
        notes_header_layout.setSpacing(4)

        # 标题行
        notes_title_row = QHBoxLayout()
        notes_title_row.setSpacing(8)

        lbl_notes_title = QLabel("便签")
        lbl_notes_title.setObjectName("notesPanelTitle")
        lbl_notes_title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))

        btn_notes_export = StarButton("一键导出", None, layout_mode="text_only", ratio_h=0.7)
        btn_notes_export.setObjectName("smallBtn")
        btn_notes_export.setFixedHeight(28)
        btn_notes_export.setToolTip("将所有便签导出为文本")
        btn_notes_export.clicked.connect(self._export_notes)

        btn_notes_clear = StarButton("清空", None, layout_mode="text_only", ratio_h=0.7)
        btn_notes_clear.setObjectName("smallBtn")
        btn_notes_clear.setFixedHeight(28)
        btn_notes_clear.setToolTip("清空全部便签（不可恢复）")
        btn_notes_clear.clicked.connect(self._clear_all_notes)

        btn_notes_close = StarButton("\u2212", None, layout_mode="text_only", ratio_h=0.7)
        btn_notes_close.setObjectName("smallBtn")
        btn_notes_close.setFixedSize(28, 28)
        btn_notes_close.setToolTip("关闭便签面板")
        btn_notes_close.clicked.connect(self.toggle_visibility)

        notes_title_row.addWidget(lbl_notes_title)
        notes_title_row.addStretch()
        notes_title_row.addWidget(btn_notes_export)
        notes_title_row.addWidget(btn_notes_clear)
        notes_title_row.addWidget(btn_notes_close)

        # 搜索行
        notes_search_row = QHBoxLayout()
        notes_search_row.setSpacing(4)

        self._search_input = QLineEdit()
        self._search_input.setObjectName("lineEdit")
        self._search_input.setPlaceholderText("搜索便签...")
        self._search_input.setFont(QFont("Microsoft YaHei", 10))
        self._search_input.setFixedHeight(38)
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_search_text_changed)

        notes_search_row.addWidget(self._search_input)

        notes_header_layout.addLayout(notes_title_row)
        notes_header_layout.addLayout(notes_search_row)

        # ── 卡片滚动区 ──
        self._scroll = QScrollArea()
        self._scroll.setObjectName("notesScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.installEventFilter(self._mw)

        self._container = QWidget()
        self._container.setObjectName("notesContainer")
        self._container.setContextMenuPolicy(Qt.CustomContextMenu)
        self._container.customContextMenuRequested.connect(self._on_container_context_menu)
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(8, 8, 8, 8)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch(1)
        self._scroll.setWidget(self._container)

        # ── 分隔线 ──
        notes_separator = QFrame()
        notes_separator.setObjectName("notesHLine")
        notes_separator.setFrameShape(QFrame.HLine)

        # ── 底部状态栏 / 输入区 ──
        self._notes_bottom = QFrame()
        self._notes_bottom.setObjectName("notesBottom")
        notes_bottom_layout = QVBoxLayout(self._notes_bottom)
        notes_bottom_layout.setContentsMargins(8, 4, 8, 8)
        notes_bottom_layout.setSpacing(6)

        # 状态栏行
        notes_status_row = QHBoxLayout()
        self._lbl_status = QLabel("共 0 条便签  |  已置顶 0 条")
        self._lbl_status.setObjectName("notesStatusLabel")
        self._lbl_status.setFont(QFont("Microsoft YaHei", 8))

        self._btn_toggle_input = QPushButton("\u2795 新建便签 \u25b2")
        self._btn_toggle_input.setObjectName("smallBtn")
        self._btn_toggle_input.setFixedWidth(120)
        self._btn_toggle_input.setCursor(Qt.PointingHandCursor)
        self._btn_toggle_input.clicked.connect(self._toggle_input_area)

        notes_status_row.addWidget(self._lbl_status)
        notes_status_row.addStretch()
        notes_status_row.addWidget(self._btn_toggle_input)
        notes_bottom_layout.addLayout(notes_status_row)

        # ── 可折叠输入区 ──
        self._input_area = QWidget()
        self._input_area.setObjectName("notesInputArea")
        self._input_area.setVisible(False)
        input_area_layout = QVBoxLayout(self._input_area)
        input_area_layout.setContentsMargins(0, 4, 0, 4)
        input_area_layout.setSpacing(6)

        # 颜色选择行
        color_row = QHBoxLayout()
        color_row.setSpacing(6)
        lbl_color_hint = QLabel("颜色:")
        lbl_color_hint.setObjectName("notesHintLabel")
        lbl_color_hint.setFont(QFont("Microsoft YaHei", 9))
        color_row.addWidget(lbl_color_hint)

        self._color_buttons = {}
        for color_key, color_hex in NOTE_COLOR_MAP.items():
            btn = QPushButton()
            btn.setFixedSize(22, 22)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(color_key)
            border = "2px solid #ffffff" if color_key == self._notes_selected_color else "2px solid transparent"
            btn.setStyleSheet(
                f"background-color: {color_hex}; border-radius: 11px; border: {border};"
            )
            btn.clicked.connect(lambda checked, c=color_key: self._select_notes_color(c))
            self._color_buttons[color_key] = btn
            color_row.addWidget(btn)
        color_row.addStretch()
        input_area_layout.addLayout(color_row)

        # 文本输入框
        self._notes_input = QPlainTextEdit()
        self._notes_merger = TextEditCommandMerger(self._notes_input, self._undo_stack, self._notes_input)
        self._notes_merger.start()
        self._notes_input.setObjectName("textEdit")
        self._notes_input.setPlaceholderText("输入关键论点或金句... 支持多行, Ctrl+Enter 快速添加")
        self._notes_input.setMinimumHeight(80)
        self._notes_input.setMaximumHeight(200)
        self._notes_input.setFont(QFont("Microsoft YaHei", 10))
        self._notes_input.installEventFilter(self._mw)
        input_area_layout.addWidget(self._notes_input)

        # 添加按钮
        btn_add_note = QPushButton("+ 添加便签")
        btn_add_note.setObjectName("noteAddBtn")
        btn_add_note.setCursor(Qt.PointingHandCursor)
        btn_add_note.setFixedHeight(42)
        btn_add_note.clicked.connect(self._add_note_from_input)
        input_area_layout.addWidget(btn_add_note)

        notes_bottom_layout.addWidget(self._input_area)

        # ── 组装 ──
        notes_layout.addWidget(notes_header)
        notes_layout.addWidget(self._scroll, stretch=1)
        notes_layout.addWidget(notes_separator)
        notes_layout.addWidget(self._notes_bottom)

        # 初始不可见
        panel.setVisible(False)
        self._panel = panel
        return panel

    def build_nav_button(self) -> tuple:
        """构建导航栏切换按钮，返回 (按钮, 标签)（支持图标文件）"""
        self._btn_toggle = QPushButton()
        self._btn_toggle.setObjectName("navToggleBtn")
        self._btn_toggle.setCheckable(True)
        self._btn_toggle.setChecked(False)
        self._btn_toggle.setToolTip("开关 便签")
        self._btn_toggle.setCursor(Qt.PointingHandCursor)
        self._btn_toggle.setFixedSize(50, 50)
        self._btn_toggle.clicked.connect(self.toggle_visibility)

        item = self._mw._nav_registry.get_item("notes")
        icon = NavBarManager.load_nav_icon(item.icon) if item else None
        if icon is not None:
            NavBarManager._apply_icon_to_button(self._btn_toggle, icon)
        else:
            self._btn_toggle.setText("")

        lbl_notes_nav = QLabel("便签")
        lbl_notes_nav.setObjectName("notesNavLabel")
        lbl_notes_nav.setFont(QFont("Microsoft YaHei", 7))
        lbl_notes_nav.setAlignment(Qt.AlignCenter)

        return self._btn_toggle, lbl_notes_nav

    # ============================================================
    #  面板切换
    # ============================================================

    def toggle_visibility(self):
        """切换便签面板的显示/隐藏（与其他面板互斥）"""
        mw = self._mw

        # 互斥：打开便签时关闭 AI写稿
        mw._speech_writer_mgr.close_if_open()

        self._visible = not self._visible
        self._panel.setVisible(self._visible)
        if self._btn_toggle:
            self._btn_toggle.setChecked(self._visible)

        if self._visible:
            # 互斥：关闭 AI扩写、模拟训练、插件
            mw._ai_expand_mgr.close_if_open()
            if mw._training_visible:
                mw._training_visible = False
                mw._training_panel.setVisible(False)
                mw._btn_toggle_training.setChecked(False)
            if mw._plugins_visible:
                mw._plugins_visible = False
                mw._plugin_panel.setVisible(False)
                mw._btn_toggle_plugins.setChecked(False)
            mw._close_all_plugin_registered_panels()
            mw._update_status("便签面板已打开")
            # 加载便签数据
            if not self._notes_data:
                self._load_notes()
            self._rebuild_notes_cards()
        else:
            mw._update_status("便签面板已关闭")

    def close_if_open(self):
        """关闭便签面板（供其他面板互斥调用）"""
        if self._visible:
            self._visible = False
            self._panel.setVisible(False)
            if self._btn_toggle:
                self._btn_toggle.setChecked(False)

    # ============================================================
    #  事件过滤委托
    # ============================================================

    def handle_event_filter(self, obj, event) -> bool:
        """
        由主窗口 eventFilter 调用。
        返回 True 表示事件已被处理。
        """
        from PyQt5.QtCore import QEvent

        # scroll 区域 resize → 防抖重排卡片
        if obj is self._scroll and event.type() == QEvent.Resize:
            if self._notes_cards and self._panel.isVisible():
                if not self._reflow_timer:
                    self._reflow_timer = QTimer(self._mw)
                    self._reflow_timer.setSingleShot(True)
                    self._reflow_timer.timeout.connect(self._reflow_notes_cards)
                self._reflow_timer.start(100)
            return False  # 不阻止事件，只是触发重排

        # Ctrl+Enter 在便签输入框中快捷提交
        if event.type() == QEvent.KeyPress and obj is self._notes_input:
            if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
                self._add_note_from_input()
                return True

        return False

    def handle_scroll_resize(self):
        """外部 resize 事件处理委托（保持向后兼容）"""
        if self._notes_cards and self._panel and self._panel.isVisible():
            if not self._reflow_timer:
                self._reflow_timer = QTimer(self._mw)
                self._reflow_timer.setSingleShot(True)
                self._reflow_timer.timeout.connect(self._reflow_notes_cards)
            self._reflow_timer.start(100)

    # ============================================================
    #  文件持久化
    # ============================================================

    def _get_save_path(self) -> str:
        """获取便签 JSON 保存路径（位于当前项目目录下）"""
        project_dir = self._mw._get_current_project_path()
        if not project_dir:
            return ""
        return os.path.join(project_dir, "sticky_notes.json")

    def _load_notes(self):
        """从文件加载便签数据"""
        filepath = self._get_save_path()
        if not filepath or not os.path.isfile(filepath):
            self._notes_data = []
            self._next_note_id = 1
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._notes_data = data.get("notes", [])
            self._next_note_id = data.get("next_id", 1)
            if not self._notes_data:
                self._next_note_id = 1
            else:
                self._next_note_id = max(n["id"] for n in self._notes_data) + 1
        except Exception:
            self._notes_data = []
            self._next_note_id = 1

    def _save_notes(self):
        """保存便签数据到文件"""
        filepath = self._get_save_path()
        if not filepath:
            return
        try:
            data = {"version": 1, "notes": self._notes_data, "next_id": self._next_note_id}
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ============================================================
    #  输入区操作
    # ============================================================

    def _select_notes_color(self, color_key: str):
        """选择便签添加颜色"""
        self._notes_selected_color = color_key
        for ck, btn in self._color_buttons.items():
            hex_color = NOTE_COLOR_MAP[ck]
            border = "2px solid #ffffff" if ck == color_key else "2px solid transparent"
            btn.setStyleSheet(
                f"background-color: {hex_color}; border-radius: 11px; border: {border};"
            )

    def _toggle_input_area(self):
        """展开/折叠输入区"""
        self._notes_input_expanded = not self._notes_input_expanded
        self._input_area.setVisible(self._notes_input_expanded)
        if self._notes_input_expanded:
            self._btn_toggle_input.setText("\u2795 新建便签 \u25bc")
            self._notes_input.setFocus()
        else:
            self._btn_toggle_input.setText("\u2795 新建便签 \u25b2")

    def _add_note_from_input(self):
        """从输入框添加便签"""
        text = self._notes_input.toPlainText().strip()
        if not text:
            return
        note = {
            "id": self._next_note_id,
            "text": text,
            "color": self._notes_selected_color,
            "pinned": False,
            "expanded": False,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._next_note_id += 1
        # 插入到非置顶区最前面
        pinned_count = sum(1 for n in self._notes_data if n["pinned"])
        self._notes_data.insert(pinned_count, note)
        self._notes_input.clear()
        self._save_notes()
        self._rebuild_notes_cards()
        self._update_status_bar()
        self._mw._update_status(f"已添加便签 #{note['id']}")

    # ============================================================
    #  状态栏更新
    # ============================================================

    def _update_status_bar(self):
        """更新便签面板底部状态栏"""
        total = len(self._notes_data)
        pinned_count = sum(1 for n in self._notes_data if n["pinned"])
        status = f"共 {total} 条便签  |  已置顶 {pinned_count} 条"
        if self._notes_search_text:
            visible = len(self._notes_cards)
            status += f"  |  搜索「{self._notes_search_text[:10]}」: {visible} 条结果"
        self._lbl_status.setText(status)

    # ============================================================
    #  搜索功能
    # ============================================================

    def _on_search_text_changed(self, text: str):
        """搜索防抖：延迟 300ms 后执行搜索"""
        if self._notes_search_timer:
            self._notes_search_timer.stop()
        self._notes_search_timer = QTimer(self._mw)
        self._notes_search_timer.setSingleShot(True)
        self._notes_search_timer.timeout.connect(lambda: self._do_notes_search(text))
        self._notes_search_timer.start(300)

    def _do_notes_search(self, text: str):
        """执行便签搜索，按出现次数降序"""
        self._notes_search_text = text.strip().lower()
        self._rebuild_notes_cards()

    def _highlight_search_text(self, raw_text: str, search: str) -> str:
        """将搜索词在文本中高亮加粗（HTML格式）"""
        escaped = raw_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        pattern = re.compile(re.escape(search), re.IGNORECASE)
        highlighted = pattern.sub(
            lambda m: f'<b style="color:#f9e2af;">{m.group(0)}</b>',
            escaped,
        )
        return '<p style="margin:0; line-height:1.4;">' + highlighted + '</p>'

    # ============================================================
    #  卡片构建
    # ============================================================

    def _rebuild_notes_cards(self):
        """重建全部便签卡片"""
        # 清除现有卡片
        for card in self._notes_cards:
            self._list_layout.removeWidget(card)
            card.deleteLater()
        self._notes_cards.clear()

        # 清空 layout
        while self._list_layout.count() > 0:
            item = self._list_layout.takeAt(0)
            pass

        # 构建展示列表
        display_notes = list(self._notes_data)
        search_text = self._notes_search_text

        # 搜索过滤与排序
        if search_text:
            scored = []
            for n in display_notes:
                n_text = n["text"].lower()
                count = n_text.count(search_text)
                if count > 0:
                    scored.append((count, n))
            scored.sort(key=lambda x: x[0], reverse=True)
            display_notes = [n for _, n in scored]

        # 按 pinned + id 排序
        sorted_notes = sorted(display_notes, key=lambda n: (0 if n["pinned"] else 1, n.get("id", 0)))
        for note in sorted_notes:
            if note["id"] in self._sticker_windows:
                continue  # 贴纸模式：不在面板中显示
            card = self._create_note_card(note)
            self._notes_cards.append(card)
            self._list_layout.addWidget(card)

        self._list_layout.addStretch(1)
        self._update_status_bar()

    def _create_note_card(self, note: dict) -> QFrame:
        """创建单张便签卡片"""
        card = QFrame()
        card.setObjectName("noteCard")
        card.setProperty("note_id", note["id"])
        card.setProperty("note_color", note["color"])
        card.setAcceptDrops(True)
        card.setCursor(Qt.OpenHandCursor)
        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(lambda pos, c=card, n=note: self._on_note_context_menu(pos, c, n))

        card.mousePressEvent = lambda ev, c=card: self._on_note_mouse_press(ev, c)
        card.mouseMoveEvent = lambda ev, c=card: self._on_note_mouse_move(ev, c)
        card.dragEnterEvent = lambda ev, c=card: self._on_note_drag_enter(ev, c)
        card.dragLeaveEvent = lambda ev, c=card: self._on_note_drag_leave(ev, c)
        card.dropEvent = lambda ev, c=card: self._on_note_drop(ev, c)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 4)
        card_layout.setSpacing(2)

        # 上部：颜色条 + 文字 + 按钮
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        # 颜色指示条
        color_bar = QFrame()
        color_bar.setFixedWidth(6)
        color_hex = NOTE_COLOR_MAP.get(note["color"], "#a6e3a1")
        color_bar.setStyleSheet(f"background-color: {color_hex}; border-radius: 3px; border: none;")
        color_bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        # 文字区域
        raw_text = note["text"]
        search_text = self._notes_search_text
        if search_text:
            highlight_text = self._highlight_search_text(raw_text, search_text)
            note_text = QLabel(highlight_text)
            note_text.setTextFormat(Qt.RichText)
        else:
            note_text = QLabel(raw_text)
        note_text.setObjectName("noteCardText")
        note_text.setFont(QFont("Microsoft YaHei", 9))
        note_text.setWordWrap(True)
        note_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card.setProperty("text_label", note_text)

        # 右侧按钮栏
        btn_row = QVBoxLayout()
        btn_row.setSpacing(2)

        pin_text = "" if note["pinned"] else ""
        btn_pin = QPushButton(pin_text)
        btn_pin.setObjectName("noteCardBtn")
        btn_pin.setFixedSize(28, 28)
        btn_pin.setToolTip("取消置顶" if note["pinned"] else "置顶")
        btn_pin.setCursor(Qt.PointingHandCursor)
        btn_pin.clicked.connect(lambda: self._toggle_note_pin(note))

        btn_color = QPushButton("")
        btn_color.setObjectName("noteCardBtn")
        btn_color.setFixedSize(28, 28)
        btn_color.setToolTip("更改颜色")
        btn_color.setCursor(Qt.PointingHandCursor)
        btn_color.clicked.connect(lambda: self._show_note_color_menu(btn_color, note))

        btn_delete = QPushButton("\u2715")
        btn_delete.setObjectName("noteCardBtn")
        btn_delete.setFixedSize(28, 28)
        btn_delete.setToolTip("删除")
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.clicked.connect(lambda: self._delete_note(note))

        btn_row.addWidget(btn_pin)
        btn_row.addWidget(btn_color)
        btn_row.addWidget(btn_delete)
        btn_row.addStretch()

        card._note_btns = (btn_pin, btn_color, btn_delete)

        top_row.addWidget(color_bar)
        top_row.addWidget(note_text, stretch=1)
        top_row.addLayout(btn_row)

        card_layout.addLayout(top_row)

        # 展开/折叠按钮
        btn_toggle = QPushButton("\u25bc 展开全部")
        btn_toggle.setObjectName("noteToggleBtn")
        btn_toggle.setFont(QFont("Microsoft YaHei", 8))
        btn_toggle.setFlat(True)
        btn_toggle.setCursor(Qt.PointingHandCursor)
        btn_toggle.setStyleSheet(f"color: {tc("muted")}; text-align: center; border: none; background: transparent;")
        btn_toggle.clicked.connect(lambda: self._toggle_note_expand(note, card))
        card.setProperty("toggle_btn", btn_toggle)
        card_layout.addWidget(btn_toggle)

        # 初始化布局计算
        self._update_note_card_layout(card, note, note_text)

        return card

    def _update_note_card_layout(self, card: QFrame, note: dict, text_label: QLabel):
        """根据可用宽度动态计算卡片高度与展开/折叠状态"""
        try:
            scroll_w = self._scroll.viewport().width()
        except Exception:
            scroll_w = 0
        if scroll_w <= 0:
            scroll_w = self._panel.width() - 30
        if scroll_w <= 0:
            scroll_w = 400

        margins = 16
        color_bar_w = 6
        btn_area_w = 34
        text_w = max(100, scroll_w - margins - color_bar_w - btn_area_w - 24)

        font = QFont("Microsoft YaHei", 9)
        fm = QFontMetrics(font)
        br = fm.boundingRect(QRect(0, 0, text_w, 99999), Qt.TextWordWrap | Qt.AlignLeft, note["text"])
        line_h = fm.lineSpacing()
        total_lines = max(1, (br.height() + line_h - 1) // line_h)

        toggle_btn = card.property("toggle_btn")
        collapsed = not note.get("expanded", False)
        show_toggle = total_lines > 3

        if show_toggle:
            toggle_btn.setVisible(True)
            if collapsed:
                text_h = 3 * line_h
                toggle_btn.setText("\u25bc 展开全部")
            else:
                text_h = max(total_lines * line_h, 3 * line_h)
                toggle_btn.setText("\u25b2 收起")
        else:
            toggle_btn.setVisible(False)
            text_h = total_lines * line_h
            note["expanded"] = False

        text_label.setFixedHeight(text_h)

        # 折叠态显示省略号；展开态显示全文
        search_text = self._notes_search_text
        if collapsed and show_toggle:
            elided_text = fm.elidedText(note["text"], Qt.ElideRight, text_w * 3)
            if search_text:
                text_label.setText(self._highlight_search_text(elided_text, search_text))
                text_label.setTextFormat(Qt.RichText)
            else:
                text_label.setText(elided_text)
        else:
            raw_text = note["text"]
            if search_text:
                text_label.setText(self._highlight_search_text(raw_text, search_text))
                text_label.setTextFormat(Qt.RichText)
            else:
                text_label.setText(raw_text)

        # 更新卡片边框样式（置顶 vs 普通）
        color_hex = NOTE_COLOR_MAP.get(note["color"], "#a6e3a1")
        if note["pinned"]:
            card.setStyleSheet(
                f"#noteCard {{ background-color: #1e1e30; border: 2px solid {color_hex}; "
                f"border-radius: 8px; }}"
            )
        else:
            card.setStyleSheet(
                f"#noteCard {{ background-color: #181825; border: 1px solid #313244; "
                f"border-radius: 8px; }}"
                f"#noteCard:hover {{ border: 1px solid #45475a; }}"
            )

    def _reflow_notes_cards(self):
        """窗口缩放后重新计算所有卡片布局（由 scroll resize 事件触发）"""
        for card in self._notes_cards:
            note_id = card.property("note_id")
            note = next((n for n in self._notes_data if n["id"] == note_id), None)
            if note is None:
                continue
            text_label = card.property("text_label")
            if text_label:
                self._update_note_card_layout(card, note, text_label)
                card.adjustSize()
        self._container.updateGeometry()
        QApplication.processEvents()

    # ============================================================
    #  卡片操作
    # ============================================================

    def _toggle_note_expand(self, note: dict, card: QFrame):
        """切换单张卡片的展开/折叠状态"""
        note["expanded"] = not note.get("expanded", False)
        text_label = card.property("text_label")
        if text_label:
            self._update_note_card_layout(card, note, text_label)
            card.adjustSize()
        self._save_notes()

    def _toggle_note_pin(self, note: dict):
        """切换置顶状态"""
        note["pinned"] = not note.get("pinned", False)
        note["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._notes_data.sort(key=lambda n: (0 if n["pinned"] else 1, n.get("id", 0)))
        self._save_notes()
        self._rebuild_notes_cards()

    def _show_note_color_menu(self, anchor_btn: QPushButton, note: dict):
        """弹出改色菜单"""
        menu = QMenu(self._mw)
        menu.setStyleSheet(f"""
            QMenu { background-color: {tc("base")}; color: {tc("text")}; border: 1px solid {tc("overlay")}; border-radius: 8px; }
            QMenu::item { padding: 6px 24px; }
            QMenu::item:selected { background-color: {tc("overlay")}; }
        """)
        for ck, chex in NOTE_COLOR_MAP.items():
            color_icon = QPixmap(16, 16)
            color_icon.fill(QColor(chex))
            action = menu.addAction(QIcon(color_icon), ck)
            action.setData(ck)
        chosen = menu.exec_(anchor_btn.mapToGlobal(QPoint(0, anchor_btn.height())))
        if chosen:
            new_color = chosen.data()
            note["color"] = new_color
            note["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save_notes()
            self._rebuild_notes_cards()

    def _delete_note(self, note: dict):
        """删除便签"""
        result = CustomDialog.question(
            self._mw, "确认删除", "确定要删除这条便签吗？",
            buttons=[("否", "no"), ("是", "yes")])
        if result != "yes":
            return
        self._notes_data = [n for n in self._notes_data if n["id"] != note["id"]]
        self._save_notes()
        self._rebuild_notes_cards()
        self._mw._update_status("便签已删除")

    def _clear_all_notes(self):
        """清空全部便签"""
        if not self._notes_data:
            return
        result = CustomDialog.question(
            self._mw, "确认清空",
            f"确定要清空全部 {len(self._notes_data)} 条便签吗？此操作不可恢复。",
            buttons=[("否", "no"), ("是", "yes")])
        if result != "yes":
            return
        self._notes_data = []
        self._next_note_id = 1
        self._save_notes()
        self._rebuild_notes_cards()
        self._mw._update_status("已清空全部便签")

    # ============================================================
    #  贴纸模式
    # ============================================================

    def _enter_sticker_mode(self, note: dict, card: QFrame):
        """将便签切换为贴纸模式：独立窗口、始终置顶"""
        sticker_win = QWidget(None, Qt.WindowStaysOnTopHint | Qt.Tool)
        sticker_win.setWindowTitle(note["text"][:30] or "贴纸")

        # 智能计算窗口大小
        text = note["text"]
        fm = QFontMetrics(QFont("Microsoft YaHei", 10))
        fixed_h = 60
        best_w, best_score = 300, float('inf')

        for w in range(260, 1200, 20):
            content_w = w - 34
            if content_w < 50:
                continue
            br = fm.boundingRect(QRect(0, 0, content_w, 99999), Qt.TextWordWrap | Qt.AlignLeft, text)
            text_h = br.height() + 12
            total_h = fixed_h + text_h
            score = abs(w - total_h)
            if 300 <= w <= 800:
                score *= 0.9
            if total_h <= 900 and score < best_score:
                best_w, best_score = w, score

        best_h = min(fixed_h + fm.boundingRect(
            QRect(0, 0, best_w - 34, 99999), Qt.TextWordWrap | Qt.AlignLeft, text,
        ).height() + 12, 900)
        sticker_win.resize(max(260, best_w), max(150, best_h))

        color_hex = NOTE_COLOR_MAP.get(note["color"], "#a6e3a1")
        sticker_win.setStyleSheet(
            f"background-color: #181825; border: 2px solid {color_hex}; border-radius: 10px;"
            "QWidget { color: #cdd6f4; font-family: 'Microsoft YaHei'; }"
            "#smallBtn {"
            "  background-color: #313244; border: 1px solid #45475a;"
            "  border-radius: 6px; padding: 2px 10px;"
            "  color: #cdd6f4; font-size: 11px; font-weight: bold;"
            "}"
            "#smallBtn:hover {"
            "  background-color: #45475a; border: 1px solid #585b70;"
            "}"
        )

        win_layout = QVBoxLayout(sticker_win)
        win_layout.setContentsMargins(10, 8, 10, 8)
        win_layout.setSpacing(6)

        # 标题/颜色条行
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        color_bar = QFrame()
        color_bar.setFixedWidth(6)
        color_bar.setFixedHeight(20)
        color_bar.setStyleSheet(f"background-color: {color_hex}; border-radius: 3px; border: none;")
        top_row.addWidget(color_bar)

        lbl_title = QLabel(f"便签 #{note['id']}")
        lbl_title.setObjectName("notesStickerTitle")
        lbl_title.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        top_row.addWidget(lbl_title)
        top_row.addStretch()
        win_layout.addLayout(top_row)

        # 文本内容
        text_label = QLabel(note["text"])
        text_label.setFont(QFont("Microsoft YaHei", 10))
        text_label.setWordWrap(True)
        text_label.setObjectName("notesStickerContent")
        text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        text_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        win_layout.addWidget(text_label, stretch=1)

        # 底部留空
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        win_layout.addLayout(btn_row)

        # 记录关联
        self._sticker_windows[note["id"]] = sticker_win
        sticker_win.setProperty("note_id", note["id"])
        sticker_win.setAttribute(Qt.WA_DeleteOnClose)

        # 窗口关闭时自动退出贴纸模式
        sticker_win.destroyed.connect(
            lambda obj=None, nid=note["id"]: self._on_sticker_window_closed(nid)
        )

        sticker_win.show()

        # 深色标题栏（Windows 10/11）
        try:
            hwnd = int(sticker_win.winId())
            for dwmwa in (20, 19):
                try:
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, dwmwa,
                        ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int(1)),
                    )
                    break
                except Exception:
                    continue
        except Exception:
            pass

        # 隐藏面板中的卡片
        card.setVisible(False)
        self._list_layout.removeWidget(card)

        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        self._mw._update_status(f"便签 #{note['id']} 已切换为贴纸模式 ({stamp})")

    def _exit_sticker_mode(self, note_id: int):
        """退出贴纸模式，恢复面板中的卡片"""
        if note_id not in self._sticker_windows:
            return
        sticker_win = self._sticker_windows.pop(note_id)
        try:
            sticker_win.destroyed.disconnect()
        except (TypeError, RuntimeError):
            pass
        sticker_win.hide()
        sticker_win.deleteLater()
        self._rebuild_notes_cards()
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        self._mw._update_status(f"便签 #{note_id} 已恢复为卡片模式 ({stamp})")

    def _on_sticker_window_closed(self, note_id: int):
        """贴纸窗口被用户关闭（点击 X 或系统销毁），自动恢复卡片"""
        if note_id not in self._sticker_windows:
            return
        try:
            self._sticker_windows.pop(note_id)
            self._rebuild_notes_cards()
        except Exception:
            pass

    def _toggle_sticker_pin(self, note_id: int):
        """贴纸窗口中切换置顶状态"""
        note = next((n for n in self._notes_data if n["id"] == note_id), None)
        if not note:
            return
        self._toggle_note_pin(note)

    # ============================================================
    #  导出
    # ============================================================

    def _export_notes(self):
        """导出全部便签为 Markdown / TXT 文件"""
        if not self._notes_data:
            CustomDialog.information(self._mw, "提示", "当前没有便签可导出。")
            return

        lines = []
        lines.append(f"# StarDebate 便签导出 ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M')})")
        lines.append("")
        pinned = [n for n in self._notes_data if n["pinned"]]
        normal = [n for n in self._notes_data if not n["pinned"]]
        if pinned:
            lines.append("## 已置顶")
            for n in pinned:
                lines.append(f"- [{n['color']}] {n['text']}")
            lines.append("")
        if normal:
            lines.append("## 普通")
            for n in normal:
                lines.append(f"- [{n['color']}] {n['text']}")
        text = "\n".join(lines)

        filepath, _ = QFileDialog.getSaveFileName(
            self._mw, "导出便签",
            f"notes_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.md",
            "Markdown (*.md);;Text (*.txt)",
        )
        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(text)
                self._mw._update_status(f"便签已导出至: {os.path.basename(filepath)}")
            except Exception as e:
                CustomDialog.warning(self._mw, "导出失败", f"无法保存文件: {str(e)}")

    # ============================================================
    #  右键菜单
    # ============================================================

    def _on_container_context_menu(self, pos):
        """便签空白区域右键菜单"""
        menu = QMenu(self._mw)
        menu.setStyleSheet(f"""
            QMenu { background-color: {tc("base")}; color: {tc("text")}; border: 1px solid {tc("overlay")}; }
            QMenu::item { padding: 6px 24px; }
            QMenu::item:selected { background-color: {tc("overlay")}; }
        """)
        action_add = menu.addAction("\u2795 新建便签")
        action_expand = menu.addAction("全部展开")
        action_collapse = menu.addAction("全部折叠")
        action_export = menu.addAction("导出")
        chosen = menu.exec_(self._container.mapToGlobal(pos))
        if chosen == action_add:
            self._toggle_input_area()
            if not self._notes_input_expanded:
                self._toggle_input_area()
        elif chosen == action_expand:
            for n in self._notes_data:
                n["expanded"] = True
            self._save_notes()
            self._rebuild_notes_cards()
        elif chosen == action_collapse:
            for n in self._notes_data:
                n["expanded"] = False
            self._save_notes()
            self._rebuild_notes_cards()
        elif chosen == action_export:
            self._export_notes()

    def _on_note_context_menu(self, pos, card: QFrame, note: dict):
        """单张卡片右键菜单"""
        menu = QMenu(self._mw)
        menu.setStyleSheet(f"""
            QMenu { background-color: {tc("base")}; color: {tc("text")}; border: 1px solid {tc("overlay")}; border-radius: 8px; }
            QMenu::item { padding: 6px 24px; }
            QMenu::item:selected { background-color: {tc("overlay")}; }
        """)
        action_pin = menu.addAction("取消置顶" if note["pinned"] else "置顶")

        color_menu = menu.addMenu("更改颜色")
        for ck, chex in NOTE_COLOR_MAP.items():
            pix = QPixmap(14, 14)
            pix.fill(QColor(chex))
            ca = color_menu.addAction(QIcon(pix), ck)
            ca.setData(ck)

        action_copy = menu.addAction("复制文本")
        action_sticker = menu.addAction(
            "贴纸模式" if note["id"] not in self._sticker_windows
            else "退出贴纸模式"
        )
        action_delete = menu.addAction("\u2715 删除")

        chosen = menu.exec_(card.mapToGlobal(pos))
        if chosen == action_pin:
            self._toggle_note_pin(note)
        elif chosen == action_copy:
            QApplication.clipboard().setText(note["text"])
            self._mw._update_status("已复制到剪贴板")
        elif chosen == action_sticker:
            if note["id"] in self._sticker_windows:
                self._exit_sticker_mode(note["id"])
            else:
                self._enter_sticker_mode(note, card)
        elif chosen == action_delete:
            self._delete_note(note)
        elif chosen and chosen.data():
            note["color"] = chosen.data()
            note["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save_notes()
            self._rebuild_notes_cards()

    # ============================================================
    #  拖放排序
    # ============================================================

    def _on_note_mouse_press(self, event, card: QFrame):
        """卡片鼠标按下 → 准备拖拽"""
        if event.button() == Qt.LeftButton:
            self._notes_drag_source = card
            card._notes_drag_start_pos = event.pos()
            card.setCursor(Qt.ClosedHandCursor)

    def _on_note_mouse_move(self, event, card: QFrame):
        """卡片鼠标移动 → 触发拖拽"""
        if self._notes_drag_source != card:
            return
        if not hasattr(card, '_notes_drag_start_pos'):
            return
        if (event.pos() - card._notes_drag_start_pos).manhattanLength() < 10:
            return

        note_id = card.property("note_id")
        note = next((n for n in self._notes_data if n["id"] == note_id), None)
        if not note:
            return

        drag = QDrag(card)
        mime = QMimeData()
        mime.setData("application/x-starnote", str(note_id).encode())
        drag.setMimeData(mime)

        pixmap = card.grab()
        drag.setPixmap(pixmap.scaled(pixmap.width() // 2, pixmap.height() // 2,
                                      Qt.KeepAspectRatio, Qt.SmoothTransformation))
        drag.setHotSpot(QPoint(pixmap.width() // 4, pixmap.height() // 4))

        card.setCursor(Qt.ClosedHandCursor)
        drag.exec_(Qt.MoveAction)
        self._notes_drag_source = None
        card.setCursor(Qt.OpenHandCursor)

    def _on_note_drag_enter(self, event, target_card: QFrame):
        """拖拽进入目标卡片"""
        event.acceptProposedAction()
        s = target_card.styleSheet()
        s = s.replace("border: 1px solid #313244", "border: 2px solid #89b4fa")
        s = s.replace("border: 2px solid", "border: 2px solid #89b4fa")
        target_card.setStyleSheet(s)

    def _on_note_drag_leave(self, event, target_card: QFrame):
        """拖拽离开目标卡片"""
        note_id = target_card.property("note_id")
        note = next((n for n in self._notes_data if n["id"] == note_id), None)
        if note:
            color_hex = NOTE_COLOR_MAP.get(note["color"], "#a6e3a1")
            if note["pinned"]:
                target_card.setStyleSheet(
                    f"#noteCard {{ background-color: #1e1e30; border: 2px solid {color_hex}; border-radius: 8px; }}"
                )
            else:
                target_card.setStyleSheet(
                    f"#noteCard {{ background-color: #181825; border: 1px solid #313244; border-radius: 8px; }}"
                    f"#noteCard:hover {{ border: 1px solid #45475a; }}"
                )

    def _on_note_drop(self, event, target_card: QFrame):
        """拖拽释放到目标卡片"""
        event.acceptProposedAction()
        if not event.mimeData().hasFormat("application/x-starnote"):
            return

        source_id = int(event.mimeData().data("application/x-starnote").data().decode())
        target_id = target_card.property("note_id")
        if source_id == target_id:
            return

        source_note = next((n for n in self._notes_data if n["id"] == source_id), None)
        target_note = next((n for n in self._notes_data if n["id"] == target_id), None)
        if not source_note or not target_note:
            return

        # 跨区限制：pinned 与 normal 不能互相拖入
        if source_note["pinned"] != target_note["pinned"]:
            return

        self._notes_data.remove(source_note)
        target_idx = self._notes_data.index(target_note)
        self._notes_data.insert(target_idx, source_note)
        source_note["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save_notes()
        self._rebuild_notes_cards()
