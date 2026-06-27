"""
主题颜色映射模块

颜色配置嵌入各主题 theme.json 的 svg_renderer 字段。

第三方主题只需在 theme.json 中添加:
  "svg_renderer": {
    "mono": {"color": "text"},
    "dual": {"primary": "accent_blue", "accent": "text"}
  }

若 theme.json 缺少 svg_renderer 字段，自动回退到默认值。
"""
import os
import json
from PyQt5.QtGui import QColor

from workers.app_config.config_paths import get_config_path

# 默认颜色映射（主题未定义时回退）
_DEFAULT_MONO_DARK = {"color": "subtext"}   # 深色主题：柔和图标色
_DEFAULT_MONO_LIGHT = {"color": "text"}      # 浅色主题：高对比图标色
_DEFAULT_DUAL = {"primary": "accent_blue", "accent": "text"}

# 浅色主题名称集合（用于自动推断）
_LIGHT_THEMES = {"catppuccin_latte", "notion_light"}


class ColorMap:
    """管理当前主题的颜色映射"""

    def __init__(self):
        self._project_root = ""
        self._theme_name = ""
        self._theme_type = "dark"  # "dark" | "light"
        self._colors: dict[str, str] = {}
        self._mono: dict[str, str] = dict(_DEFAULT_MONO_DARK)
        self._dual: dict[str, str] = dict(_DEFAULT_DUAL)

    # ── 初始化和重载 ────────────────────────────────────────

    def init(self, project_root: str):
        """设置项目根目录"""
        self._project_root = project_root
        self._detect_and_load()

    def set_theme(self, theme_name: str):
        """切换主题并重载颜色"""
        if self._theme_name != theme_name:
            self._theme_name = theme_name
            self._theme_type = "light" if theme_name in _LIGHT_THEMES else "dark"
            self._load_theme()

    def _detect_and_load(self):
        """从持久化 config.json 读取当前主题名并加载"""
        config_path = get_config_path("config/config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            theme = data.get("theme", "notion_dark")
        except (json.JSONDecodeError, OSError):
            theme = "notion_dark"
        self._theme_name = theme
        self._theme_type = "light" if theme in _LIGHT_THEMES else "dark"
        self._load_theme()

    def _load_theme(self):
        """加载当前主题的 theme.json，提取 colors 和 svg_renderer"""
        theme_path = os.path.join(
            self._project_root, "style", "themes",
            self._theme_name, "theme.json"
        )
        self._colors = {}
        # 根据主题类型选择默认 mono 色
        default_mono = (_DEFAULT_MONO_LIGHT if self._theme_type == "light"
                        else _DEFAULT_MONO_DARK)
        self._mono = dict(default_mono)
        self._dual = dict(_DEFAULT_DUAL)

        if not os.path.isfile(theme_path):
            return

        try:
            with open(theme_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        # 加载颜色词典
        self._colors = data.get("colors", {})

        # 加载 svg_renderer 配置
        svg_cfg = data.get("svg_renderer", {})
        if isinstance(svg_cfg, dict):
            mono = svg_cfg.get("mono", {})
            if isinstance(mono, dict) and "color" in mono:
                self._mono = {"color": mono["color"]}
            dual = svg_cfg.get("dual", {})
            if isinstance(dual, dict):
                if "primary" in dual:
                    self._dual["primary"] = dual["primary"]
                if "accent" in dual:
                    self._dual["accent"] = dual["accent"]

    # ── 颜色解析 ─────────────────────────────────────────────

    def resolve(self, color_key: str) -> QColor | None:
        """根据颜色键名解析为 QColor。支持主题色键名（如 "text"）和直接 hex（如 "#2E6DDE"）。"""
        if not color_key or not isinstance(color_key, str):
            return None

        # 直接 hex 颜色
        if color_key.startswith("#"):
            try:
                return QColor(color_key)
            except Exception:
                return None

        # 在主题 colors 字典中查找
        hex_val = self._colors.get(color_key, "")
        if hex_val:
            try:
                return QColor(hex_val)
            except Exception:
                return None

        return None

    # ── 获取当前渲染颜色 ─────────────────────────────────────

    @property
    def mono_color_key(self) -> str:
        """单色模式使用的颜色键名"""
        return self._mono.get("color", "subtext")

    @property
    def mono_color(self) -> QColor | None:
        """单色模式使用的 QColor"""
        return self.resolve(self.mono_color_key)

    @property
    def dual_primary_key(self) -> str:
        """双色模式主色键名"""
        return self._dual.get("primary", _DEFAULT_DUAL["primary"])

    @property
    def dual_primary(self) -> QColor | None:
        """双色模式主色 QColor"""
        return self.resolve(self.dual_primary_key)

    @property
    def dual_accent_key(self) -> str:
        """双色模式辅色键名"""
        return self._dual.get("accent", _DEFAULT_DUAL["accent"])

    @property
    def dual_accent(self) -> QColor | None:
        """双色模式辅色 QColor"""
        return self.resolve(self.dual_accent_key)

    @property
    def theme_name(self) -> str:
        return self._theme_name

    @property
    def colors(self) -> dict:
        return dict(self._colors)

    @property
    def mono_config(self) -> dict:
        return dict(self._mono)

    @property
    def dual_config(self) -> dict:
        return dict(self._dual)
