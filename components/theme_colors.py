"""
全局主题色板工具模块。

所有 worker / 组件若需要在 Python 代码中获取当前主题颜色，
请使用本模块提供的函数，而不是硬编码 Catppuccin 色值。

用法示例::

    from components.theme_colors import tc  # tc = theme color

    label.setStyleSheet(f"color: {tc('text')};")
    label.setStyleSheet(f"color: {tc('accent_blue')}; background: transparent; border: none;")

--- 设计说明 ---
- 本模块读取 style/themes/<theme_name>/theme.json 中的 colors 字段
- 使用进程级缓存，主题切换时调用 refresh() 清除缓存
- tc() 返回 hex 字符串（如 "#E0E0E0"），可以直接拼接进 QSS 字符串
"""

from __future__ import annotations

import json
import os

from workers.app_config.config_paths import get_config_path
from components.res_path import get_resource_root

# ── Catppuccin Mocha 色板（兜底默认值）───────────────────────────────────
_FALLBACK_COLORS: dict[str, str] = {
    # 基础
    "base": "#1e1e2e", "surface": "#181825", "overlay": "#313244",
    "mantle": "#181825", "crust": "#11111b",
    # 文字
    "text": "#cdd6f4", "subtext": "#a6adc8", "muted": "#6c7086",
    # 强调色
    "accent_blue": "#89b4fa", "accent_green": "#a6e3a1",
    "accent_red": "#f38ba8", "accent_yellow": "#f9e2af",
    "accent_purple": "#2E6DDE", "accent_pink": "#f5c2e7",
    "accent_teal": "#94e2d5", "accent_orange": "#fab387",
    "accent_mauve": "#2E6DDE", "accent_peach": "#fab387",
    "accent_lavender": "#b4befe",
    # 边框 / 分割
    "border": "#313244", "divider": "#45475a",
    # 交互
    "hover": "#313244", "pressed": "#585b70",
    "selected_bg": "#45475a",
    # 语义别名
    "accent": "#2E6DDE", "title": "#2E6DDE", "keyword": "#f9e2af",
    "error": "#f38ba8", "success": "#a6e3a1",
    "warning": "#f9e2af", "info": "#89b4fa",
    # 组件专用
    "toggle_off": "#585b70",
}

# ── 缓存 ──────────────────────────────────────────────────────────────────
_cache: dict = {"loaded": False, "colors": {}, "theme_name": ""}


def refresh() -> None:
    """主题切换后调用，清除缓存使下次读取时重新加载。"""
    _cache["loaded"] = False
    _cache["colors"] = {}
    _cache["theme_name"] = ""


def _load() -> None:
    """从 theme.json 加载当前主题颜色到缓存。"""
    if _cache["loaded"]:
        return

    colors = dict(_FALLBACK_COLORS)
    theme_name = "notion_dark"

    try:
        config_path = get_config_path("config/config.json")
        if os.path.isfile(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            theme_name = cfg.get("theme", "notion_dark")

        theme_path = os.path.join(
            get_resource_root(), "style", "themes", theme_name, "theme.json"
        )
        if os.path.isfile(theme_path):
            with open(theme_path, "r", encoding="utf-8") as f:
                theme = json.load(f)
            tc = theme.get("colors", {})
            if isinstance(tc, dict):
                colors.update(tc)
    except Exception:
        pass

    _cache.update({"loaded": True, "colors": colors, "theme_name": theme_name})


def tc(key: str, fallback: str | None = None) -> str:
    """获取当前主题中 key 对应的 hex 颜色字符串。

    Args:
        key:      颜色键名，如 "text"、"accent_blue"、"surface"
        fallback: 可选，找不到时的兜底值；默认使用 Catppuccin Mocha 色板

    Returns:
        hex 字符串，如 "#E0E0E0"
    """
    _load()
    fb = fallback if fallback is not None else _FALLBACK_COLORS.get(key, "#FFFFFF")
    return _cache["colors"].get(key, fb)


def tc_qcolor(key: str, fallback: str | None = None) -> str:
    """同 tc()，但返回值带 fallback 保证（兼容旧调用方式）。"""
    return tc(key, fallback)
