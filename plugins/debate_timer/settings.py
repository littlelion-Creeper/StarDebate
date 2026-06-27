"""
辩论计时器 - 插件设置页
在 ⚙️ 设置对话框的「插件页面」分区中自动展示
"""

import json
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QCheckBox, QFrame, QPushButton,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

# ═══════════════════════════════════════
#  页面元信息（必需）
# ═══════════════════════════════════════
PAGE_INFO = {
    "name": "辩论计时器",
    "icon": "⏱",
    "order": 110,
    "author": "StarDebate",
    "version": "1.0.0",
}

# ═══════════════════════════════════════
#  页面参数配置（可选）
# ═══════════════════════════════════════
PAGE_CONFIG = {
    "save_path": "plugins/debate_timer/settings_config.json",
    "auto_save": True,
}

# ═══════════════════════════════════════
#  插件配置保存路径
# ═══════════════════════════════════════
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_JSON = os.path.join(PLUGIN_DIR, "plugin.json")

# 默认各阶段时长（秒）
DEFAULT_PHASES = [
    ("立论", 180, 30),
    ("驳论", 120, 20),
    ("质询", 90, 15),
    ("自由辩论", 240, 30),
    ("总结陈词", 180, 30),
]


def get_default_config() -> dict:
    """默认配置"""
    return {
        "phases": [
            {"name": name, "duration": dur, "warn_time": warn}
            for name, dur, warn in DEFAULT_PHASES
        ],
        "sound_enabled": False,
        "always_on_top": True,
    }


def build_page(parent_dialog, current_config: dict) -> QWidget:
    """构建设置页内容"""
    page = QWidget()
    page.setObjectName("settingsPage")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)

    # 标题
    title = QLabel("⏱ 辩论计时器设置")
    title.setObjectName("settingsSectionTitle")
    layout.addWidget(title)

    desc = QLabel("配置各辩论环节的计时参数和提醒设置")
    desc.setObjectName("settingsSectionDesc")
    desc.setWordWrap(True)
    layout.addWidget(desc)

    # 阶段时长卡片
    phases_card = QFrame()
    phases_card.setObjectName("settingsCard")
    phases_layout = QVBoxLayout(phases_card)
    phases_layout.setContentsMargins(20, 18, 20, 18)
    phases_layout.setSpacing(10)

    lbl_phases = QLabel("环节时长设置（秒）")
    lbl_phases.setObjectName("settingsLabel")
    phases_layout.addWidget(lbl_phases)

    # 获取当前阶段配置
    phases = current_config.get("phases", [])
    phase_widgets = {}

    for i, phase in enumerate(phases):
        name = phase.get("name", f"环节{i+1}")
        duration = phase.get("duration", 180)
        warn_time = phase.get("warn_time", 30)

        row = QHBoxLayout()
        row.setSpacing(8)

        name_lbl = QLabel(name)
        name_lbl.setFixedWidth(70)
        name_lbl.setStyleSheet("color: #cdd6f4; font-size: 12px; font-weight: bold;")
        row.addWidget(name_lbl)

        dur_spin = QSpinBox()
        dur_spin.setObjectName("settingsSpin")
        dur_spin.setRange(10, 3600)
        dur_spin.setValue(duration)
        dur_spin.setMinimumHeight(30)
        dur_spin.setToolTip(f"{name}时长")
        row.addWidget(dur_spin)

        dur_unit = QLabel("秒")
        dur_unit.setStyleSheet("color: #6c7086; font-size: 11px;")
        row.addWidget(dur_unit)

        warn_lbl = QLabel("提醒:")
        warn_lbl.setStyleSheet("color: #a6adc8; font-size: 11px;")
        row.addWidget(warn_lbl)

        warn_spin = QSpinBox()
        warn_spin.setObjectName("settingsSpin")
        warn_spin.setRange(5, 600)
        warn_spin.setValue(warn_time)
        warn_spin.setMinimumHeight(30)
        warn_spin.setToolTip(f"{name}结束前提醒")
        row.addWidget(warn_spin)

        warn_unit = QLabel("秒前")
        warn_unit.setStyleSheet("color: #6c7086; font-size: 11px;")
        row.addWidget(warn_unit)

        row.addStretch()
        phases_layout.addLayout(row)
        phase_widgets[i] = {"name": name, "dur_spin": dur_spin, "warn_spin": warn_spin}

    layout.addWidget(phases_card)

    # 通用设置卡片
    general_card = QFrame()
    general_card.setObjectName("settingsCard")
    general_layout = QVBoxLayout(general_card)
    general_layout.setContentsMargins(20, 18, 20, 18)
    general_layout.setSpacing(10)

    lbl_general = QLabel("通用设置")
    lbl_general.setObjectName("settingsLabel")
    general_layout.addWidget(lbl_general)

    cb_sound = QCheckBox("启用提示音")
    cb_sound.setObjectName("settingsCheck")
    cb_sound.setChecked(current_config.get("sound_enabled", False))
    general_layout.addWidget(cb_sound)

    cb_top = QCheckBox("窗口置顶显示")
    cb_top.setObjectName("settingsCheck")
    cb_top.setChecked(current_config.get("always_on_top", True))
    general_layout.addWidget(cb_top)

    layout.addWidget(general_card)

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
        phase_widgets, cb_sound, cb_top
    ))

    layout.addStretch()

    # 保存控件引用
    page._phase_widgets = phase_widgets
    page._cb_sound = cb_sound
    page._cb_top = cb_top
    return page


def _reset_to_default(phase_widgets, cb_sound, cb_top):
    """恢复默认值"""
    for i, (name, dur, warn) in enumerate(DEFAULT_PHASES):
        if i in phase_widgets:
            phase_widgets[i]["dur_spin"].setValue(dur)
            phase_widgets[i]["warn_spin"].setValue(warn)
    cb_sound.setChecked(False)
    cb_top.setChecked(True)


def collect_config(page_widget: QWidget) -> dict:
    """从页面控件收集当前配置"""
    phase_widgets = getattr(page_widget, "_phase_widgets", {})
    phases = []
    for i in sorted(phase_widgets.keys()):
        w = phase_widgets[i]
        phases.append({
            "name": w["name"],
            "duration": w["dur_spin"].value(),
            "warn_time": w["warn_spin"].value(),
        })

    config = {
        "phases": phases,
        "sound_enabled": page_widget._cb_sound.isChecked(),
        "always_on_top": page_widget._cb_top.isChecked(),
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
        print(f"[debate_timer] 保存配置失败: {e}")
