# StarDebate 设置模块
# 提供设置对话框、页面注册、自动扫描功能

from .settings_dialog import SettingsDialog
from .settings_page_base import SettingsPageInfo, PageRegistry, register_builtin_page

__all__ = [
    "SettingsDialog",
    "SettingsPageInfo",
    "PageRegistry",
    "register_builtin_page",
]
