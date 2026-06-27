"""
辩论智能助手 - 插件设置页
在 ⚙️ 设置对话框的「插件页面」分区中自动展示
"""

import json
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QSpinBox, QCheckBox, QFrame, QPushButton,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

# ═══════════════════════════════════════
#  页面元信息（必需）
# ═══════════════════════════════════════
PAGE_INFO = {
    "name": "辩论智能助手",
    "icon": "🤖",
    "order": 105,
    "author": "StarDebate",
    "version": "1.0.0",
}

# ═══════════════════════════════════════
#  页面参数配置（可选）
# ═══════════════════════════════════════
PAGE_CONFIG = {
    "save_path": "plugins/debate_assistant/settings_config.json",
    "auto_save": True,
}

# ═══════════════════════════════════════
#  插件配置保存路径
# ═══════════════════════════════════════
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_JSON = os.path.join(PLUGIN_DIR, "plugin.json")


def get_default_config() -> dict:
    """默认配置"""
    return {
        "auto_analyze_on_save": True,
        "report_format": "markdown",
        "analysis_depth": "detailed",
        "max_output_tokens": 2048,
    }


def build_page(parent_dialog, current_config: dict) -> QWidget:
    """构建设置页内容"""
    page = QWidget()
    page.setObjectName("settingsPage")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)

    # 标题
    title = QLabel("🤖 辩论智能助手设置")
    title.setObjectName("settingsSectionTitle")
    layout.addWidget(title)

    desc = QLabel("AI驱动的辩论分析助手，自动分析辩稿质量、生成改进建议、导出分析报告")
    desc.setObjectName("settingsSectionDesc")
    desc.setWordWrap(True)
    layout.addWidget(desc)

    # 设定卡片
    card = QFrame()
    card.setObjectName("settingsCard")
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(20, 18, 20, 18)
    card_layout.setSpacing(12)

    # 自动分析开关
    cb_auto = QCheckBox("保存辩稿时自动触发 AI 分析")
    cb_auto.setObjectName("settingsCheck")
    cb_auto.setChecked(current_config.get("auto_analyze_on_save", True))
    card_layout.addWidget(cb_auto)

    # 报告格式
    lbl_format = QLabel("报告导出格式")
    lbl_format.setObjectName("settingsLabel")
    combo_format = QComboBox()
    combo_format.setObjectName("settingsCombo")
    combo_format.addItems(["markdown", "html", "plain_text"])
    combo_format.setMinimumHeight(34)
    fmt = current_config.get("report_format", "markdown")
    idx = combo_format.findText(fmt)
    if idx >= 0:
        combo_format.setCurrentIndex(idx)
    card_layout.addWidget(lbl_format)
    card_layout.addWidget(combo_format)

    # 分析深度
    lbl_depth = QLabel("分析深度")
    lbl_depth.setObjectName("settingsLabel")
    combo_depth = QComboBox()
    combo_depth.setObjectName("settingsCombo")
    combo_depth.addItems(["brief", "standard", "detailed"])
    combo_depth.setMinimumHeight(34)
    depth = current_config.get("analysis_depth", "detailed")
    idx = combo_depth.findText(depth)
    if idx >= 0:
        combo_depth.setCurrentIndex(idx)
    card_layout.addWidget(lbl_depth)
    card_layout.addWidget(combo_depth)

    # 最大输出 Token
    lbl_tokens = QLabel("最大输出 Token")
    lbl_tokens.setObjectName("settingsLabel")
    spin_tokens = QSpinBox()
    spin_tokens.setObjectName("settingsSpin")
    spin_tokens.setRange(256, 16384)
    spin_tokens.setSingleStep(256)
    spin_tokens.setValue(current_config.get("max_output_tokens", 2048))
    spin_tokens.setMinimumHeight(34)
    card_layout.addWidget(lbl_tokens)
    card_layout.addWidget(spin_tokens)

    layout.addWidget(card)

    # 恢复默认按钮
    btn_reset = QPushButton("恢复默认")
    btn_reset.setObjectName("settingsSmallBtn")
    btn_reset.setCursor(Qt.PointingHandCursor)
    btn_reset.setFixedWidth(120)
    reset_row = QHBoxLayout()
    reset_row.addStretch()
    reset_row.addWidget(btn_reset)
    layout.addLayout(reset_row)

    btn_reset.clicked.connect(lambda: _reset_to_default(
        cb_auto, combo_format, combo_depth, spin_tokens
    ))

    layout.addStretch()

    # 保存控件引用
    page._cb_auto = cb_auto
    page._combo_format = combo_format
    page._combo_depth = combo_depth
    page._spin_tokens = spin_tokens
    return page


def _reset_to_default(cb_auto, combo_format, combo_depth, spin_tokens):
    """恢复默认值"""
    cb_auto.setChecked(True)
    combo_format.setCurrentIndex(0)  # markdown
    combo_depth.setCurrentIndex(2)   # detailed
    spin_tokens.setValue(2048)


def collect_config(page_widget: QWidget) -> dict:
    """从页面控件收集当前配置"""
    config = {
        "auto_analyze_on_save": page_widget._cb_auto.isChecked(),
        "report_format": page_widget._combo_format.currentText(),
        "analysis_depth": page_widget._combo_depth.currentText(),
        "max_output_tokens": page_widget._spin_tokens.value(),
    }
    # 同步写入 plugin.json 的 config 字段
    _save_to_plugin_json(config)
    return config


def _save_to_plugin_json(config: dict):
    """将配置写入 plugin.json"""
    try:
        if os.path.exists(PLUGIN_JSON):
            with open(PLUGIN_JSON, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            manifest["config"] = config
            with open(PLUGIN_JSON, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[debate_assistant] 保存配置失败: {e}")
