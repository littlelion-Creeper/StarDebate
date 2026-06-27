"""
SVG 渲染器设置页

管理 SVG 渲染模式、缓存，以及查看各主题的颜色配置。
颜色配置嵌入在 style/themes/<name>/theme.json 的 svg_renderer 字段中，
此页面只读展示，支持预览效果。
"""
import os
import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QSizePolicy, QRadioButton,
    QButtonGroup, QCheckBox,
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont, QColor, QPixmap, QPainter

# ── 项目模块导入 ──
from components.svg_renderer import SvgRenderer
from components.star_spinbox import StarSpinBox


# ═══════════════════════════════════════
#  页面元信息（由 PageRegistry 自动扫描）
# ═══════════════════════════════════════

PAGE_INFO = {
    "id": "svg_renderer",
    "name": "SVG",
    "icon": "🖼",
    "order": 55,
    "author": "StarDebate",
    "version": "1.0.0",
}

PAGE_CONFIG = {
    "save_path": "config/svg_renderer.json",
    "auto_save": True,
}


def get_default_config() -> dict:
    return {"mode": "mono", "cache_enabled": True, "cache_max": 256}


# ── 常量 ─────────────────────────────

_COLOR_NAMES: dict[str, str] = {
    "base": "背景", "surface": "面板", "overlay": "叠加层",
    "text": "正文", "subtext": "副文", "muted": "弱化",
    "accent_green": "绿色强调", "accent_purple": "紫色强调",
    "accent_blue": "蓝色强调", "accent_pink": "粉色强调",
    "accent_yellow": "黄色强调", "accent_red": "红色强调",
}


# ═══════════════════════════════════════
#  主构建函数
# ═══════════════════════════════════════

def build_page(parent_dialog, current_config: dict) -> QWidget:
    page = QWidget()
    page.setObjectName("settingsPage")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(24, 20, 24, 24)
    layout.setSpacing(16)

    # 存储引用
    page._dialog = parent_dialog
    page._mode_buttons = {}
    page._preview_widgets = []
    page._theme_cards = []

    # ── 标题 ──
    title = QLabel("SVG 渲染器设置")
    title.setObjectName("settingsSectionTitle")
    layout.addWidget(title)

    desc = QLabel("管理 SVG 图标的渲染模式与主题颜色映射。颜色配置嵌入在各主题的 theme.json 中。")
    desc.setObjectName("settingsSectionDesc")
    desc.setWordWrap(True)
    layout.addWidget(desc)

    # ── 滚动区域 ──
    scroll = QScrollArea()
    scroll.setObjectName("settingsContentScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    scroll_content = QWidget()
    scroll_content.setObjectName("settingsPage")
    scroll_layout = QVBoxLayout(scroll_content)
    scroll_layout.setContentsMargins(0, 0, 0, 0)
    scroll_layout.setSpacing(14)

    # ── 1. 全局渲染模式 ──
    scroll_layout.addWidget(_build_mode_section(page, current_config))

    # ── 2. 当前主题颜色配置 ──
    scroll_layout.addWidget(_build_current_theme_section(page))

    # ── 3. 所有主题一览 ──
    scroll_layout.addWidget(_build_all_themes_section(page))

    # ── 4. 预览区域 ──
    scroll_layout.addWidget(_build_preview_section(page))

    # ── 5. 缓存管理 ──
    scroll_layout.addWidget(_build_cache_section(page, current_config))

    scroll_layout.addStretch()
    scroll.setWidget(scroll_content)
    layout.addWidget(scroll, 1)

    # ── 底部按钮 ──
    footer = QHBoxLayout()
    footer.setSpacing(10)
    footer.addStretch()

    reset_btn = QPushButton("恢复默认")
    reset_btn.setObjectName("settingsSmallBtn")
    reset_btn.setFixedHeight(34)
    reset_btn.clicked.connect(lambda: _on_reset(page))
    footer.addWidget(reset_btn)

    save_btn = QPushButton("保存设置")
    save_btn.setObjectName("settingsPrimaryBtn")
    save_btn.setFixedHeight(34)
    footer.addWidget(save_btn)

    layout.addLayout(footer)

    # 初始刷新预览
    QTimer = __import__("PyQt5.QtCore", fromlist=["QTimer"]).QTimer
    QTimer.singleShot(100, lambda: _refresh_preview(page))

    return page


# ═══════════════════════════════════════
#  配置收集
# ═══════════════════════════════════════

def collect_config(page_widget: QWidget) -> dict:
    config = {}
    # 渲染模式
    if hasattr(page_widget, "_mode_buttons"):
        for mode, btn in page_widget._mode_buttons.items():
            if btn.isChecked():
                config["mode"] = mode
                break
    # 缓存
    if hasattr(page_widget, "_cache_cb"):
        config["cache_enabled"] = page_widget._cache_cb.isChecked()
    if hasattr(page_widget, "_cache_max_spin"):
        config["cache_max"] = page_widget._cache_max_spin.value()
    return config


# ═══════════════════════════════════════
#  各区域构建
# ═══════════════════════════════════════

def _build_mode_section(page: QWidget, config: dict) -> QWidget:
    card = QFrame()
    card.setObjectName("settingsCard")
    ly = QVBoxLayout(card)
    ly.setContentsMargins(18, 14, 18, 14)
    ly.setSpacing(10)

    header = QLabel("渲染模式")
    header.setObjectName("settingsLabel")
    ly.addWidget(header)

    mode_group = QButtonGroup(page)
    row = QHBoxLayout()
    row.setSpacing(18)

    modes = [
        ("mono", "单色 (Mono) — 全 SVG 使用一种颜色"),
        ("dual", "双色 (Dual) — 按 data-color 区分主/辅色"),
        ("native", "原生 (Native) — 保留 SVG 原始颜色"),
    ]
    current_mode = config.get("mode", "mono")

    for mode_key, label_text in modes:
        rb = QRadioButton(label_text)
        rb.setObjectName("svgRendererMode")
        rb.setChecked(mode_key == current_mode)
        mode_group.addButton(rb)
        page._mode_buttons[mode_key] = rb
        row.addWidget(rb)

    row.addStretch()
    ly.addLayout(row)

    return card


def _build_current_theme_section(page: QWidget) -> QWidget:
    card = QFrame()
    card.setObjectName("settingsCard")
    ly = QVBoxLayout(card)
    ly.setContentsMargins(18, 14, 18, 14)
    ly.setSpacing(8)

    theme_name = SvgRenderer.get_theme_name()
    cm = SvgRenderer.get_color_map()

    header_lbl = QLabel(f"当前主题: {theme_name} — 颜色来源: theme.json")
    header_lbl.setObjectName("settingsLabel")
    ly.addWidget(header_lbl)

    # 单色
    mono_key = cm.mono_color_key
    mono_hex = cm.colors.get(mono_key, "N/A")
    mono_label = QLabel(f"单色 → color: ▓ {mono_key} ({mono_hex})")
    mono_label.setObjectName("settingsValueLabel")
    ly.addWidget(mono_label)

    # 双色
    p_key = cm.dual_primary_key
    p_hex = cm.colors.get(p_key, "N/A")
    a_key = cm.dual_accent_key
    a_hex = cm.colors.get(a_key, "N/A")
    dual_label = QLabel(f"双色 → primary: ▓ {p_key} ({p_hex})  |  accent: ▓ {a_key} ({a_hex})")
    dual_label.setObjectName("settingsValueLabel")
    ly.addWidget(dual_label)

    # 可用颜色列表
    colors_text = "  ".join(
        f"<span style='color:{h}'>{k}</span>"
        for k, h in sorted(cm.colors.items())[:12]
    )
    hint = QLabel(f"<span style='color:#6c7086;font-size:12px;'>可用的主题色键:</span> {colors_text}")
    hint.setObjectName("settingsHint")
    hint.setWordWrap(True)
    hint.setTextFormat(Qt.RichText)
    ly.addWidget(hint)

    return card


def _build_all_themes_section(page: QWidget) -> QWidget:
    card = QFrame()
    card.setObjectName("settingsCard")
    ly = QVBoxLayout(card)
    ly.setContentsMargins(18, 14, 18, 14)
    ly.setSpacing(10)

    header = QLabel("各主题 SVG 渲染配置一览 (只读)")
    header.setObjectName("settingsLabel")
    ly.addWidget(header)

    hint = QLabel("颜色配置嵌入在各主题的 theme.json 中，修改请直接编辑该文件。")
    hint.setObjectName("settingsHint")
    hint.setWordWrap(True)
    ly.addWidget(hint)

    # 扫描所有主题
    project_root = _get_project_root()
    themes_dir = os.path.join(project_root, "style", "themes")
    if os.path.isdir(themes_dir):
        for theme_dir_name in sorted(os.listdir(themes_dir)):
            theme_path = os.path.join(themes_dir, theme_dir_name, "theme.json")
            if not os.path.isfile(theme_path):
                continue
            try:
                with open(theme_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            name = data.get("name", theme_dir_name)
            colors_data = data.get("colors", {})
            svg_cfg = data.get("svg_renderer", {})

            mono = svg_cfg.get("mono", {}).get("color", "无")
            dual_p = svg_cfg.get("dual", {}).get("primary", "无")
            dual_a = svg_cfg.get("dual", {}).get("accent", "无")

            mono_hex = colors_data.get(mono, "")
            dual_p_hex = colors_data.get(dual_p, "")
            dual_a_hex = colors_data.get(dual_a, "")

            sub_card = QFrame()
            sub_card.setObjectName("svgThemeSubCard")
            sub_card.setStyleSheet(
                "#svgThemeSubCard { background-color: transparent; border-radius: 8px; padding: 10px; }"
            )
            sub_ly = QVBoxLayout(sub_card)
            sub_ly.setContentsMargins(12, 8, 12, 8)
            sub_ly.setSpacing(3)

            name_lbl = QLabel(name)
            name_lbl.setObjectName("settingsLabel")
            sub_ly.addWidget(name_lbl)

            mono_txt = f"单色: {mono} ({mono_hex})" if mono_hex else f"单色: {mono}"
            sub_ly.addWidget(QLabel(mono_txt))

            dual_txt = f"双色: {dual_p} ({dual_p_hex}) + {dual_a} ({dual_a_hex})" \
                if dual_p_hex else f"双色: {dual_p} + {dual_a}"
            sub_ly.addWidget(QLabel(dual_txt))

            ly.addWidget(sub_card)

    return card


def _build_preview_section(page: QWidget) -> QWidget:
    card = QFrame()
    card.setObjectName("settingsCard")
    ly = QVBoxLayout(card)
    ly.setContentsMargins(18, 14, 18, 14)
    ly.setSpacing(10)

    header = QLabel("渲染预览")
    header.setObjectName("settingsLabel")
    ly.addWidget(header)

    # 预览图标行 — 三种尺寸
    preview_row = QHBoxLayout()
    preview_row.setSpacing(18)

    for sz in [16, 24, 32]:
        lbl = QLabel()
        lbl.setFixedSize(sz + 12, sz + 12)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setObjectName("svgPreviewLabel")
        preview_row.addWidget(lbl)
        page._preview_widgets.append((lbl, sz))

    preview_row.addStretch()
    ly.addLayout(preview_row)

    # 按钮预览
    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)

    for txt in ["快速刷题", "添加稿件", "设置"]:
        btn = QPushButton(txt)
        btn.setObjectName("svgPreviewBtn")
        btn.setFixedHeight(32)
        btn_row.addWidget(btn)

    btn_row.addStretch()
    ly.addLayout(btn_row)

    return card


def _build_cache_section(page: QWidget, config: dict) -> QWidget:
    card = QFrame()
    card.setObjectName("settingsCard")
    ly = QVBoxLayout(card)
    ly.setContentsMargins(18, 14, 18, 14)
    ly.setSpacing(10)

    header = QLabel("缓存管理")
    header.setObjectName("settingsLabel")
    ly.addWidget(header)

    cache_row = QHBoxLayout()
    cache_row.setSpacing(12)

    cb = QCheckBox("启用缓存")
    cb.setObjectName("svgCacheCheck")
    cb.setChecked(config.get("cache_enabled", True))
    page._cache_cb = cb
    cache_row.addWidget(cb)

    cache_row.addWidget(QLabel("上限:"))
    spin = StarSpinBox(
        value=config.get("cache_max", 256),
        min_value=16, max_value=2048, step=16,
        button_layout="embedded", spin_height=30,
        object_name="settingsSpin",
    )
    spin.setFixedWidth(90)
    page._cache_max_spin = spin
    cache_row.addWidget(spin)

    cur_label = QLabel(f"当前缓存: {SvgRenderer.get_cache_size()}")
    cur_label.setObjectName("settingsHint")
    page._cache_cur_label = cur_label
    cache_row.addWidget(cur_label)

    cache_row.addStretch()

    clear_btn = QPushButton("清空缓存")
    clear_btn.setObjectName("settingsSmallBtn")
    clear_btn.setFixedHeight(32)
    clear_btn.clicked.connect(lambda: _on_clear_cache(page))
    cache_row.addWidget(clear_btn)

    ly.addLayout(cache_row)

    return card


# ═══════════════════════════════════════
#  回调与辅助函数
# ═══════════════════════════════════════

def _refresh_preview(page: QWidget):
    """刷新预览区域 — 用当前主题颜色渲染图标"""
    try:
        icon_path = os.path.join(_get_project_root(), "icon", "message_box", "info_circle.svg")
        if not os.path.isfile(icon_path):
            return

        for lbl, sz in page._preview_widgets:
            try:
                pix = SvgRenderer.icon(icon_path, sz)
                lbl.setPixmap(pix.scaled(sz, sz, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except Exception:
                pass
    except Exception:
        pass


def _on_clear_cache(page: QWidget):
    SvgRenderer.clear_cache()
    if hasattr(page, "_cache_cur_label"):
        page._cache_cur_label.setText(f"当前缓存: {SvgRenderer.get_cache_size()}")


def _on_reset(page: QWidget):
    """恢复默认设置"""
    if hasattr(page, "_mode_buttons") and "mono" in page._mode_buttons:
        page._mode_buttons["mono"].setChecked(True)
    if hasattr(page, "_cache_cb"):
        page._cache_cb.setChecked(True)
    if hasattr(page, "_cache_max_spin"):
        page._cache_max_spin.setValue(256)


def _get_project_root() -> str:
    from components.res_path import get_resource_root
    return get_resource_root()
