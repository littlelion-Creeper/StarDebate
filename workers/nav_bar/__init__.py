"""
导航栏模块 — 注册机制驱动的导航栏管理

NavRegistry:  加载/保存 config/nav_registry.json，提供查询和修改接口
NavBarManager: 根据注册表构建左右导航栏，统一管理按钮和插件区
NavItem:       描述单个导航元素的 dataclass
"""
from .nav_registry import NavRegistry, NavItem
from .nav_bar_manager import NavBarManager

__all__ = ["NavRegistry", "NavItem", "NavBarManager"]
