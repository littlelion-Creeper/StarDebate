"""
编辑器设置页 — 项目树文件名简化 + 自动保存设置
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame,
)
from PyQt5.QtCore import Qt

from components.star_checkbox import StarCheckBox

# ═══════════════════════════════════════
#  页面元信息
# ═══════════════════════════════════════

PAGE_INFO = {
    "id": "editor",
    "name": "编辑器",
    "icon": "✏️",
    "order": 60,
    "author": "StarDebate",
    "version": "1.1.0",
}

PAGE_CONFIG = {
    "save_path": "",
    "auto_save": False,
}


def get_default_config() -> dict:
    return {"font_size": 14, "tab_size": 4, "simplify_tree_names": True, "auto_save_on_switch": True}


def build_page(parent_dialog, current_config: dict) -> QWidget:
    """构建编辑器页面"""
    page = QWidget()
    page.setObjectName("settingsPage")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)

    title = QLabel("编辑器")
    title.setObjectName("settingsSectionTitle")
    layout.addWidget(title)

    desc = QLabel("调整一辩稿编辑器的显示选项与行为设置")
    desc.setObjectName("settingsSectionDesc")
    desc.setWordWrap(True)
    layout.addWidget(desc)

    mw = parent_dialog.parent()
    full_cfg = mw._app_cfg.load_full_config()

    # ── 项目树文件名简化 ──
    card1 = QFrame()
    card1.setObjectName("settingsCard")
    card1_layout = QVBoxLayout(card1)
    card1_layout.setContentsMargins(24, 20, 24, 20)
    card1_layout.setSpacing(8)

    cb_simplify = StarCheckBox("简化项目树文件名显示", parent=page)
    cb_simplify.setObjectName("settingsCheckbox")

    hint1 = QLabel(
        "开启后项目树只显示简化后的文件名。\n"
        "例如：辩论_一辩稿.json → 一辩稿，赛题_资料稿.json → 资料稿"
    )
    hint1.setObjectName("settingsHint")
    hint1.setWordWrap(True)

    card1_layout.addWidget(cb_simplify)
    card1_layout.addWidget(hint1)
    layout.addWidget(card1)

    # ── 切换文件时自动保存 ──
    card2 = QFrame()
    card2.setObjectName("settingsCard")
    card2_layout = QVBoxLayout(card2)
    card2_layout.setContentsMargins(24, 20, 24, 20)
    card2_layout.setSpacing(8)

    cb_auto_save = StarCheckBox("切换文件时自动保存", parent=page)
    cb_auto_save.setObjectName("settingsCheckbox")

    hint2 = QLabel(
        "开启后，切换正方/反方一辩稿时自动保存当前编辑内容。\n"
        "关闭后，切换时将弹窗询问是否保存。"
    )
    hint2.setObjectName("settingsHint")
    hint2.setWordWrap(True)

    card2_layout.addWidget(cb_auto_save)
    card2_layout.addWidget(hint2)
    layout.addWidget(card2)

    # ── 加载当前状态 ──
    cb_simplify.setChecked(full_cfg.get("simplify_tree_names", True))
    cb_auto_save.setChecked(full_cfg.get("auto_save_on_switch", True))

    # ── 即时保存 + 刷新 ──
    def _on_simplify_toggle(checked: bool):
        mw._app_cfg.save_config(simplify_tree_names=checked)
        current_path = mw._project_explorer.get_current_project_path()
        if current_path:
            mw._build_tree_from_path(current_path)

    def _on_auto_save_toggle(checked: bool):
        mw._app_cfg.save_config(auto_save_on_switch=checked)

    cb_simplify.toggled.connect(_on_simplify_toggle)
    cb_auto_save.toggled.connect(_on_auto_save_toggle)

    layout.addStretch()
    return page


def collect_config(page_widget: QWidget) -> dict:
    """收集配置"""
    return {"font_size": 14, "tab_size": 4, "simplify_tree_names": True, "auto_save_on_switch": True}
