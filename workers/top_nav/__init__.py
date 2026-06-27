"""
顶部导航栏模块 — 注册机制驱动的顶部菜单栏管理

v2.0 — 与 TitleBar 融合：菜单按钮直接注入标题栏，不再生成独立 QFrame。

TopNavRegistry:  加载/保存菜单配置 JSON（如 config/menu_main_window.json），提供查询和修改接口
TopNavManager:    将注册表按钮注入 TitleBar 注入区，统一管理按钮/菜单/插件区
TopNavItem:       描述单个顶部导航元素的 dataclass（含 section 分区字段）
TopNavSubItem:    描述菜单子项的 dataclass
"""
from .top_nav_registry import TopNavRegistry, TopNavItem, TopNavSubItem
from .top_nav_manager import TopNavManager

__all__ = ["TopNavRegistry", "TopNavItem", "TopNavSubItem", "TopNavManager"]
