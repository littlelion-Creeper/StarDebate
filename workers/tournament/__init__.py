# -*- coding: utf-8 -*-
"""赛程管理模块 - 赛制选择、编辑、导入/导出

目录结构：
    workers/tournament/
        __init__.py             # 本文件：常量 + 模块导出
        tournament_manager.py   # TournamentManager 类
    style/themes/catppuccin_mocha/
        tournament.qss          # 赛程面板 QSS 样式
    config/
        competition_formats.json # 集中式备份文件
    custom_formats/              # 独立赛制文件目录
"""

import os

# ---- 赛制预设 ---- 
COMPETITION_PRESETS = {
    "华语辩论赛制": {
        "type": "preset",
        "team_size": 4,
        "positions": [
            {"name": "一辩", "phases": [{"name": "立论", "duration": 180}, {"name": "接质询", "duration": 120}]},
            {"name": "二辩", "phases": [{"name": "驳论", "duration": 180}, {"name": "接质询", "duration": 120}]},
            {"name": "三辩", "phases": [{"name": "盘问", "duration": 120}, {"name": "小结", "duration": 180}]},
            {"name": "四辩", "phases": [{"name": "总结陈词", "duration": 240}]},
        ],
        "free_debate": {"name": "自由辩论", "duration": 480, "description": "双方交替发言"},
    },
    "世界大学生辩论赛制": {
        "type": "preset",
        "team_size": 3,
        "positions": [
            {"name": "一辩", "phases": [{"name": "立论", "duration": 240}, {"name": "接质询", "duration": 120}]},
            {"name": "二辩", "phases": [{"name": "驳论", "duration": 180}, {"name": "接质询", "duration": 120}]},
            {"name": "三辩", "phases": [{"name": "盘问", "duration": 120}, {"name": "总结陈词", "duration": 240}]},
        ],
        "free_debate": {"name": "自由辩论", "duration": 360, "description": "双方交替发言"},
    },
    "英国议会制辩论": {
        "type": "preset",
        "team_size": 2,
        "positions": [
            {"name": "首相(PM)", "phases": [{"name": "立论", "duration": 420}]},
            {"name": "反对党领袖(LO)", "phases": [{"name": "驳论", "duration": 420}]},
            {"name": "副首相(DPM)", "phases": [{"name": "论证展开", "duration": 420}]},
            {"name": "反对党副领袖(DLO)", "phases": [{"name": "论证展开", "duration": 420}]},
            {"name": "执政党议员(MP)", "phases": [{"name": "延伸论证", "duration": 420}]},
            {"name": "反对党议员(MO)", "phases": [{"name": "延伸论证", "duration": 420}]},
            {"name": "执政党党鞭(PW)", "phases": [{"name": "总结陈词", "duration": 420}]},
            {"name": "反对党党鞭(OW)", "phases": [{"name": "总结陈词", "duration": 420}]},
        ],
        "free_debate": None,
    },
    "政策辩论赛制": {
        "type": "preset",
        "team_size": 2,
        "positions": [
            {"name": "正方一辩", "phases": [{"name": "立论", "duration": 480}]},
            {"name": "反方一辩", "phases": [{"name": "驳论", "duration": 480}]},
            {"name": "正方二辩", "phases": [{"name": "盘问", "duration": 180}, {"name": "小结", "duration": 300}]},
            {"name": "反方二辩", "phases": [{"name": "盘问", "duration": 180}, {"name": "小结", "duration": 300}]},
            {"name": "正方一辩", "phases": [{"name": "总结驳辩", "duration": 300}]},
            {"name": "反方一辩", "phases": [{"name": "总结驳辩", "duration": 300}]},
            {"name": "正方二辩", "phases": [{"name": "总结陈词", "duration": 300}]},
            {"name": "反方二辩", "phases": [{"name": "总结陈词", "duration": 300}]},
        ],
        "free_debate": None,
    },
    "腾讯辩论赛制": {
        "type": "preset",
        "team_size": 3,
        "positions": [
            {"name": "一辩", "phases": [{"name": "破题", "duration": 120}, {"name": "立论", "duration": 180}]},
            {"name": "二辩", "phases": [{"name": "驳论", "duration": 180}, {"name": "对辩", "duration": 120}]},
            {"name": "三辩", "phases": [{"name": "盘问", "duration": 120}, {"name": "小结", "duration": 180}]},
        ],
        "free_debate": {"name": "自由辩论", "duration": 360, "description": "双方交替发言"},
    },
}

# 可选环节列表
AVAILABLE_PHASES = [
    "立论", "驳论", "盘问", "接质询", "对辩", "小结", "总结陈词",
    "破题", "提问", "申论", "反驳", "论证展开", "延伸论证", "总结驳辩",
    "自由辩论",
]

# 可选时长（秒）
AVAILABLE_DURATIONS = [60, 90, 120, 150, 180, 210, 240, 300, 360, 420, 480, 600, 900]

# 环节对位选项
COUNTERPART_OPTIONS = [
    "无（独立环节）", "立论", "驳论", "盘问", "接质询", "对辩", "小结", "总结陈词",
    "申论", "反驳", "质询", "论证展开", "全体",
]

from .tournament_manager import TournamentManager

__all__ = [
    "TournamentManager",
    "COMPETITION_PRESETS", "AVAILABLE_PHASES", "AVAILABLE_DURATIONS", "COUNTERPART_OPTIONS",
]
