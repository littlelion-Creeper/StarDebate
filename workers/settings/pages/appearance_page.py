"""
外观设置页：主题切换（卡片式预览）
"""
import os
import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QSizePolicy, QScrollBar,
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QEvent
from PyQt5.QtGui import QFont, QWheelEvent
from workers.common import FlowLayout
from components.star_checkbox import StarCheckBox


# ═══════════════════════════════════════
#  页面元信息
# ═══════════════════════════════════════

PAGE_INFO = {
    "id": "appearance",
    "name": "外观",
    "icon": "🎨",
    "order": 40,
    "author": "StarDebate",
    "version": "2.0.0",
}

PAGE_CONFIG = {
    "save_path": "",
    "auto_save": False,
}


def get_default_config() -> dict:
    """从 config.json 读取当前主题，未设置时回退默认"""
    from workers.app_config.config_paths import get_config_path
    from components.res_path import get_resource_root
    try:
        config_path = get_config_path("config/config.json")
        if os.path.isfile(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            theme = data.get("theme", "notion_dark")
            show_nav_labels = data.get("show_nav_labels", True)
            # 验证主题目录存在
            theme_dir = os.path.join(get_resource_root(), "style", "themes", theme)
            if os.path.isdir(theme_dir):
                return {"theme": theme, "show_nav_labels": show_nav_labels}
    except (json.JSONDecodeError, OSError):
        pass
    return {"theme": "notion_dark"}


# ============================================================
#  主题预览卡片
# ============================================================

class ThemeCard(QFrame):
    """单个主题预览卡片，点击选中"""
    clicked = pyqtSignal(str)  # theme_id

    CARD_SIZE_W = 195
    CARD_SIZE_H = 232
    PREVIEW_H = 120
    PREVIEW_W = 163

    def __init__(self, theme_id: str, theme_data: dict, is_current: bool, parent=None):
        super().__init__(parent)
        self._theme_id = theme_id
        self._theme_data = theme_data
        self._is_current = is_current
        self._selected = is_current
        self.setObjectName("themeCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.CARD_SIZE_W, self.CARD_SIZE_H)
        self._build()

    def _build(self):
        colors = self._theme_data.get("colors", {})
        base = colors.get("base", "#1e1e2e")
        surface = colors.get("surface", "#181825")
        overlay = colors.get("overlay", "#313244")
        text_c = colors.get("text", "#cdd6f4")
        subtext = colors.get("subtext", "#a6adc8")
        purple = colors.get("accent_purple", "#2E6DDE")
        green = colors.get("accent_green", "#a6e3a1")
        blue = colors.get("accent_blue", "#89b4fa")
        yellow = colors.get("accent_yellow", "#f9e2af")
        red = colors.get("accent_red", "#f38ba8")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 10)
        main_layout.setSpacing(8)

        # ── 预览窗 ──
        preview_frame = QFrame()
        preview_frame.setObjectName("themePreviewFrame")
        preview_frame.setFixedSize(self.PREVIEW_W, self.PREVIEW_H)
        preview_frame.setStyleSheet(
            f"#themePreviewFrame {{"
            f"background-color: {base};"
            f"border: 1px solid {overlay};"
            f"border-radius: 8px;"
            f"}}"
        )
        pv_layout = QVBoxLayout(preview_frame)
        pv_layout.setContentsMargins(0, 0, 0, 0)
        pv_layout.setSpacing(0)

        # 模拟标题栏
        title_bar = QLabel()
        title_bar.setFixedHeight(18)
        title_bar.setStyleSheet(
            f"background-color: {surface};"
            f"border-top-left-radius: 7px;"
            f"border-top-right-radius: 7px;"
            f"padding: 2px 8px;"
            f"color: {subtext};"
            f"font-size: 9px;"
        )
        title_bar.setText("  ★ StarDebate")
        pv_layout.addWidget(title_bar)

        # 模拟导航 / 侧边
        body_area = QWidget()
        body_area.setStyleSheet(f"background: transparent;")
        body_layout = QHBoxLayout(body_area)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # 侧边迷你导航
        sidebar = QLabel()
        sidebar.setFixedWidth(22)
        sidebar.setStyleSheet(
            f"background-color: {surface};"
            f"padding: 2px;"
        )
        naive_lines = "\n".join(["─"] * 8)
        sidebar.setText(naive_lines)
        sidebar.setStyleSheet(
            f"background-color: {surface};"
            f"color: {subtext}; font-size: 5px; padding: 2px 0px; border: none;"
        )
        body_layout.addWidget(sidebar)

        # 内容区
        content_area = QLabel()
        content_area.setStyleSheet(
            f"background-color: {base};"
            f"color: {text_c};"
            f"font-size: 9px; padding: 6px; border: none;"
        )
        content_area.setText("辩论论点\n论据支撑\n反驳推演")
        body_layout.addWidget(content_area, stretch=1)

        pv_layout.addWidget(body_area, stretch=1)

        # 底部色条
        swatch_bar = QWidget()
        swatch_bar.setFixedHeight(10)
        swatch_bar.setStyleSheet(f"background: transparent;")
        swatch_layout = QHBoxLayout(swatch_bar)
        swatch_layout.setContentsMargins(6, 2, 6, 2)
        swatch_layout.setSpacing(3)

        for accent_c in [green, purple, blue, yellow, red]:
            dot = QLabel()
            dot.setFixedSize(6, 6)
            dot.setStyleSheet(
                f"background-color: {accent_c}; border-radius: 3px; border: none;"
            )
            swatch_layout.addWidget(dot)
        swatch_layout.addWidget(dot)
        swatch_layout.addStretch()

        pv_layout.addWidget(swatch_bar)

        main_layout.addWidget(preview_frame, alignment=Qt.AlignCenter)

        # ── 主题名称 ──
        name_label = QLabel(self._theme_data.get("name", self._theme_id))
        name_label.setObjectName("themeCardName")
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet(
            f"color: {text_c}; font-size: 13px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        main_layout.addWidget(name_label)

        # ── 类型 + 状态 ──
        theme_type = self._theme_data.get("type", "dark")
        type_text = "浅色" if theme_type == "light" else "深色"
        status_text = f"{type_text}"
        if self._is_current:
            status_text += " · ✓ 当前使用"

        status_label = QLabel(status_text)
        status_label.setObjectName("themeCardStatus")
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setStyleSheet(
            f"color: {subtext}; font-size: 11px; background: transparent; border: none;"
        )
        main_layout.addWidget(status_label)

        self._update_border(base, overlay, purple)

        # 子控件穿透鼠标事件，确保点击落在 ThemeCard 上
        for child in self.findChildren(QWidget):
            child.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def _update_border(self, base, overlay, purple):
        if self._selected:
            self.setStyleSheet(
                f"#themeCard {{"
                f"background-color: {base};"
                f"border: 2px solid {purple};"
                f"border-radius: 12px;"
                f"}}"
            )
        else:
            self.setStyleSheet(
                f"#themeCard {{"
                f"background-color: {overlay};"
                f"border: 1px solid {overlay};"
                f"border-radius: 12px;"
                f"}}"
                f"#themeCard:hover {{"
                f"border: 1px solid {purple};"
                f"}}"
            )

    def set_current(self, is_current: bool):
        """设置是否为当前使用的主题"""
        self._is_current = is_current

    def set_selected(self, selected: bool):
        """设置卡片选中状态"""
        self._selected = selected
        colors = self._theme_data.get("colors", {})
        self._update_border(
            colors.get("base", "#1e1e2e"),
            colors.get("overlay", "#313244"),
            colors.get("accent_purple", "#2E6DDE"),
        )

    def mousePressEvent(self, event):
        self.clicked.emit(self._theme_id)
        super().mousePressEvent(event)

    @property
    def theme_id(self) -> str:
        return self._theme_id


# ============================================================
#  页面构建函数
# ============================================================

def _discover_themes() -> list[dict]:
    """扫描 style/themes/ 下所有主题文件夹，返回 [{id, data}, ...]"""
    import os
    from components.res_path import get_resource_root
    themes_root = os.path.join(get_resource_root(), "style", "themes")

    themes = []
    if not os.path.isdir(themes_root):
        return themes

    for entry in sorted(os.listdir(themes_root)):
        theme_dir = os.path.join(themes_root, entry)
        if not os.path.isdir(theme_dir):
            continue
        theme_json = os.path.join(theme_dir, "theme.json")
        if not os.path.isfile(theme_json):
            continue
        try:
            with open(theme_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            themes.append({"id": entry, "data": data})
        except (json.JSONDecodeError, OSError):
            continue

    return themes


class _AppearancePage(QWidget):
    """外观设置页内部类，管理卡片布局和选择状态
    窗口模式：横向滚动，卡片单行排列
    全屏模式：FlowLayout 换行，纵向滚动
    """

    CARD_W = ThemeCard.CARD_SIZE_W  # 195
    CARD_SPACING = 16
    MARGIN = 4

    def __init__(self, parent_dialog, current_config: dict):
        super().__init__()
        self._parent_dialog = parent_dialog
        self._current_theme = current_config.get("theme", "notion_dark")
        self._selected_theme = self._current_theme
        self._show_nav_labels = current_config.get("show_nav_labels", True)
        self._cards: dict[str, ThemeCard] = {}
        self._themes_data: list[dict] = []
        self._is_fullscreen = False
        self.setObjectName("settingsPage")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # 标题
        title = QLabel("外观")
        title.setObjectName("settingsSectionTitle")
        layout.addWidget(title)

        desc = QLabel("选择您喜欢的界面主题，点击卡片即可预览")
        desc.setObjectName("settingsSectionDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # ── 主题卡片区 ──
        theme_card = QFrame()
        theme_card.setObjectName("settingsCard")
        theme_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._tc_layout = QVBoxLayout(theme_card)
        self._tc_layout.setContentsMargins(16, 16, 16, 16)
        self._tc_layout.setSpacing(12)

        section_label = QLabel("主题切换")
        section_label.setObjectName("settingsLabel")
        self._tc_layout.addWidget(section_label)

        # QScrollArea（动态切换布局）
        self._scroll = QScrollArea()
        self._scroll.setObjectName("themeCardScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setAlignment(Qt.AlignTop)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._scroll.viewport().installEventFilter(self)

        self._cards_inner = QWidget()
        self._cards_inner.setObjectName("themeCardsContainer")
        self._cards_inner.setStyleSheet("background: transparent;")

        # 预加载主题数据
        self._themes_data = _discover_themes()

        # 初始化布局
        self._rebuild_cards()

        self._scroll.setWidget(self._cards_inner)
        self._tc_layout.addWidget(self._scroll)
        layout.addWidget(theme_card)

        # ── 提示 ──
        hint = QLabel("ℹ 切换主题后点击「保存」即可生效，界面配色将立即更新。")
        hint.setObjectName("settingsHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ── 导航栏按钮名称显示开关 ──
        nav_label_card = QFrame()
        nav_label_card.setObjectName("settingsCard")
        nav_label_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        nl_layout = QVBoxLayout(nav_label_card)
        nl_layout.setContentsMargins(16, 16, 16, 16)
        nl_layout.setSpacing(8)

        section_label2 = QLabel("导航栏")
        section_label2.setObjectName("settingsLabel")
        nl_layout.addWidget(section_label2)

        cb_show_labels = StarCheckBox(
            "显示导航栏按钮名称",
            parent=nav_label_card,
            checked=self._show_nav_labels,
            checkbox_size=18,
            icon_scheme="auto",
            object_name="settingsCheckbox",
        )
        nl_layout.addWidget(cb_show_labels)

        nl_hint = QLabel("控制左侧和右侧导航栏中按钮下方的文字标签是否可见")
        nl_hint.setObjectName("settingsHint")
        nl_hint.setWordWrap(True)
        nl_layout.addWidget(nl_hint)

        layout.addWidget(nav_label_card)

        # 延迟连接 toggle（避免 __init__ 阶段访问 parent 链的时序问题）
        QTimer.singleShot(0, lambda: self._connect_nav_label_toggle(cb_show_labels))

        layout.addStretch()

        # 延迟检测全屏状态
        QTimer.singleShot(100, self._check_fullscreen_mode)

    # ── 导航栏标签开关连接 ──────────────────────────────

    def _connect_nav_label_toggle(self, cb: StarCheckBox):
        """连接导航栏标签开关：即时生效 + 持久化配置"""
        try:
            mw = self._parent_dialog.parent()
            if mw is None:
                return
            if hasattr(mw, '_nav_mgr') and mw._nav_mgr is not None:
                cb.toggled.connect(
                    lambda checked, mgr=mw._nav_mgr: mgr.set_labels_visible(checked)
                )
            if hasattr(mw, '_app_cfg') and mw._app_cfg is not None:
                cb.toggled.connect(
                    lambda checked, cfg=mw._app_cfg: cfg.save_config(show_nav_labels=checked)
                )
        except Exception:
            import traceback
            traceback.print_exc()

    def showEvent(self, event):
        """页面重新可见时强制重设滚动区域高度，防止 QStackedWidget 切换导致膨胀"""
        super().showEvent(event)
        if not self._is_fullscreen and hasattr(self, '_scroll'):
            card_row_h = ThemeCard.CARD_SIZE_H + 2 * self.MARGIN
            self._cards_inner.setFixedHeight(card_row_h)
            self._scroll.setMinimumHeight(0)
            self._scroll.setMaximumHeight(card_row_h + 4)
            self._scroll.setWidgetResizable(False)

    # ═══════════════════════════════════════
    #  模式切换
    # ═══════════════════════════════════════

    def _check_fullscreen_mode(self):
        """检测父对话框是否最大化，切换布局"""
        dialog = self._parent_dialog
        if dialog:
            new_state = dialog.isMaximized()
            if new_state != self._is_fullscreen:
                self._is_fullscreen = new_state
                self._rebuild_cards()

    def eventFilter(self, obj, event):
        """监听滚动区域尺寸变化 + 鼠标滚轮转向"""
        if obj == self._scroll.viewport():
            if event.type() == QEvent.Resize:
                self._check_fullscreen_mode()
            elif event.type() == QEvent.Wheel:
                wheel_event = event  # type: QWheelEvent
                if not self._is_fullscreen:
                    # 窗口模式：滚轮驱动横向滚动（滚动条已隐藏，直接操作 value）
                    delta = wheel_event.angleDelta().y()
                    hbar = self._scroll.horizontalScrollBar()
                    if hbar:
                        step = self.CARD_W // 2
                        new_val = hbar.value() - delta // 30 * step
                        new_val = max(hbar.minimum(), min(hbar.maximum(), new_val))
                        hbar.setValue(new_val)
                        return True
        return super().eventFilter(obj, event)

    def _rebuild_cards(self):
        """根据全屏/窗口模式重建卡片布局"""
        # 清空旧布局
        if self._cards_inner.layout():
            QWidget().setLayout(self._cards_inner.layout())  # 移走旧 layout

        self._cards.clear()

        if self._is_fullscreen:
            # ── 全屏模式：FlowLayout 换行 + 纵向滚动 ──
            self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._scroll.setWidgetResizable(True)
            self._scroll.setMinimumHeight(0)
            self._scroll.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX, 取消窗口模式限制

            new_layout = FlowLayout(self._cards_inner)
            new_layout.setContentsMargins(
                self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN)
            new_layout.setSpacing(self.CARD_SPACING)
        else:
            # ── 窗口模式：单行横向滚动，卡片行高紧凑排列 ──
            # 固定 cards_inner 高度 = 卡片高 + 上下 margin，防止纵向膨胀
            card_row_h = ThemeCard.CARD_SIZE_H + 2 * self.MARGIN
            self._cards_inner.setFixedHeight(card_row_h)
            self._scroll.setWidgetResizable(False)
            self._scroll.setMinimumHeight(0)
            self._scroll.setMaximumHeight(card_row_h + 4)  # scroll 略高于内容
            self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            outer = QVBoxLayout(self._cards_inner)
            outer.setContentsMargins(self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN)
            outer.setSpacing(0)

            cards_row = QHBoxLayout()
            cards_row.setContentsMargins(0, 0, 0, 0)
            cards_row.setSpacing(self.CARD_SPACING)

            for t in self._themes_data:
                card = self._create_card(t, self._cards_inner)
                cards_row.addWidget(card)

            cards_row.addStretch()
            outer.addLayout(cards_row)
            # 不再添加 outer.addStretch()，避免内容上方留空
            return  # 窗口模式卡片已添加，不需要再走下面的通用循环

        # 全屏模式 FlowLayout：逐个添加卡片
        for t in self._themes_data:
            card = self._create_card(t, self._cards_inner)
            new_layout.addWidget(card)

    def _create_card(self, theme_entry: dict, parent: QWidget) -> ThemeCard:
        """创建单张主题卡片并注册"""
        tid = theme_entry["id"]
        tdata = theme_entry["data"]
        is_current = (tid == self._current_theme)
        card = ThemeCard(tid, tdata, is_current, parent)
        card.clicked.connect(self._on_card_clicked)
        self._cards[tid] = card
        if is_current:
            card.set_selected(True)
        return card

    def _on_card_clicked(self, theme_id: str):
        """主题卡片点击：更新选中态"""
        if theme_id == self._selected_theme:
            return
        if self._selected_theme in self._cards:
            self._cards[self._selected_theme].set_selected(False)
        self._selected_theme = theme_id
        if theme_id in self._cards:
            self._cards[theme_id].set_selected(True)

    def collect_config(self) -> dict:
        return {"theme": self._selected_theme}


def build_page(parent_dialog, current_config: dict) -> QWidget:
    """构建设置页面"""
    page = _AppearancePage(parent_dialog, current_config)
    return page


def collect_config(page_widget: QWidget) -> dict:
    """收集外观配置"""
    if isinstance(page_widget, _AppearancePage):
        return page_widget.collect_config()
    return get_default_config()
