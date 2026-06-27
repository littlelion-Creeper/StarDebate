# -*- coding: utf-8 -*-
"""辩论框架模块 - 思维导图式辩论框架编辑器

目录结构：
    workers/framework/
        __init__.py              # 本文件：常量 + 模块导出
        framework_worker.py      # AIFrameworkWorker：AI 异步生成辩论框架
        framework_widgets.py     # FrameworkNodeWidget + FrameworkCanvas：节点控件与画布
        framework_manager.py     # FrameworkManager：UI 构建 + 数据管理 + AI 调度
    style/themes/*/
        framework.qss            # 框架画布 QSS 样式（各主题一份）
"""

from components.theme_colors import tc

# ---- 框架节点类型定义 ----
FRAMEWORK_NODE_TYPES = {
    "position": ("🧭 立场", "#f38ba8"),
    "definition": ("📖 定义", "#89b4fa"),
    "criterion": ("⚖️ 判准", "#f9e2af"),
    "argument": ("💡 论点", "#a6e3a1"),
    "evidence": ("📊 论据", "#fab387"),
    "value": ("💎 价值", "#2E6DDE"),
}

# 节点类型 → 主题颜色键名映射
NODE_TYPE_COLOR_KEYS = {
    "position": "accent_red",
    "definition": "accent_blue",
    "criterion": "accent_yellow",
    "argument": "accent_green",
    "evidence": "accent_orange",
    "value": "accent_purple",
}


def get_node_type_color(node_type: str) -> str:
    """获取节点类型的主题感知颜色（跟随当前主题切换）。"""
    key = NODE_TYPE_COLOR_KEYS.get(node_type, "accent_blue")
    return tc(key, "#888")


from .framework_worker import AIFrameworkWorker
from .framework_widgets import FrameworkNodeWidget, FrameworkCanvas
from .framework_manager import FrameworkManager

__all__ = [
    "FRAMEWORK_NODE_TYPES",
    "NODE_TYPE_COLOR_KEYS",
    "get_node_type_color",
    "AIFrameworkWorker",
    "FrameworkNodeWidget",
    "FrameworkCanvas",
    "FrameworkManager",
]
