"""icon_loader — 通用 SVG 图标加载工具。

提供加载 icon/common/ 目录下 SVG 图标的方法，
以及模块 ID → SVG 图标的映射。

用法:
    from components.icon_loader import load_common_icon, get_module_svg_icon

    icon = load_common_icon("STDB.svg")
    module_icon = get_module_svg_icon("speech_pro")
"""

import os
from PyQt5.QtGui import QIcon
from workers.nav_bar.nav_bar_manager import NavBarManager
from components.res_path import get_resource_root

# ── SVG 图标目录 ──
_COMMON_ICON_DIR = os.path.join(get_resource_root(), "icon", "common")


def load_common_icon(svg_name: str) -> QIcon:
    """加载 icon/common/ 下的 SVG 图标文件，返回主题色适配的 QIcon。"""
    icon_path = os.path.join(_COMMON_ICON_DIR, svg_name)
    if not os.path.isfile(icon_path):
        return None
    return NavBarManager._render_svg_themed(icon_path, size=16)


# ── 模块 ID → SVG 文件名映射 ──
_MODULE_SVG_MAP: dict[str, str] = {
    "basic":            "debate.svg",
    "speech_pro":       "speech.svg",
    "speech_con":       "speech.svg",
    "ref_doc_pro":      "form.svg",
    "ref_doc_con":      "form.svg",
    "analysis_pro":     "analysis.svg",
    "analysis_con":     "analysis.svg",
    "framework":        "framework.svg",
    "cross_exam":       "cross.svg",
    "accept_exam_pro":  "accept.svg",
    "accept_exam_con":  "accept.svg",
    "notes":            "note.svg",
    "structure":        "structure.svg",
    "training":         "train.svg",
    "export":           "export.svg",
}


def get_module_svg_icon(module_id: str) -> QIcon:
    """根据模块 ID 返回对应的主题色 SVG QIcon。"""
    svg_name = _MODULE_SVG_MAP.get(module_id)
    if not svg_name:
        return None
    return load_common_icon(svg_name)
