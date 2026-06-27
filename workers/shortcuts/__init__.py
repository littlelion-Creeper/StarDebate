# StarDebate 快捷键模块
# 提供全局快捷键管理器，支持注册、冲突检测、配置持久化
# 插件可通过 api.register_shortcut() 注册快捷键

from .shortcut_manager import ShortcutManager, get_shortcut_manager

__all__ = [
    "ShortcutManager",
    "get_shortcut_manager",
]
