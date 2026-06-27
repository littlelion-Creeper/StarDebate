"""
导航栏注册表 — NavItem 数据类 + NavRegistry 管理类

NavItem 描述导航栏中每个元素（按钮/分隔符/stretch/插件区）的属性。
NavRegistry 负责加载/保存注册表 JSON，提供查询和修改接口。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional, Callable, Any


@dataclass
class NavItem:
    """导航栏中的一个元素"""
    id: str                              # 唯一标识符
    item_type: str                       # "button" | "separator" | "stretch" | "plugin_area"
    label: str = ""                      # 按钮下方标签文字
    text: str = ""                       # 按钮文字（emoji，无 icon 时显示）
    icon: str = ""                       # ★ 图标文件名（如 "settings.svg"），存放于 icon/nav_bar/
    tooltip: str = ""                    # 按钮 tooltip
    section: str = "middle"              # "top" | "middle" | "bottom"
    position: int = 0                    # 排序位置（越小越靠前）
    enabled: bool = True                 # 是否启用
    checkable: bool = False              # 是否可切换状态
    default_checked: bool = False        # 默认是否选中
    module: str = ""                     # 关联的外部模块 ID（如 "speech_writer"）
    icon_size: int = 0                   # 图标边长（px），0=使用默认 28
    icon_checked_color: str = ""         # 选中时的 SVG 颜色键名（空=使用 settings 默认）
    icon_unchecked_color: str = ""       # 不选中时的 SVG 颜色键名（空=使用 settings 默认）


class NavRegistry:
    """导航栏注册表 — 管理左右两侧导航栏的按钮配置"""

    DEFAULT_PATH = "config/nav_registry.json"

    def __init__(self, registry_path: Optional[str] = None):
        self._path = registry_path or self.DEFAULT_PATH
        self._left_items: list[NavItem] = []
        self._right_items: list[NavItem] = []
        self._settings: dict = {}
        self._loaded = False

    # ---------- 加载 / 保存 ----------

    def load(self) -> bool:
        """从 JSON 文件加载注册表。返回是否加载成功。"""
        if not os.path.exists(self._path):
            return False
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return False

        self._settings = data.get("settings", {})
        self._left_items = self._parse_items(data.get("left_nav", []))
        self._right_items = self._parse_items(data.get("right_nav", []))
        self._loaded = True
        return True

    def save(self) -> bool:
        """将当前注册表保存回 JSON 文件。"""
        data = {
            "version": "1.0.0",
            "description": "导航栏按钮注册表",
            "settings": self._settings,
            "left_nav": self._serialize_items(self._left_items),
            "right_nav": self._serialize_items(self._right_items),
        }
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return True
        except OSError:
            return False

    # ---------- 解析 ----------

    @staticmethod
    def _parse_items(raw: list[dict]) -> list[NavItem]:
        items: list[NavItem] = []
        for entry in raw:
            item = NavItem(
                id=entry.get("id", ""),
                item_type=entry.get("type", "button"),
                label=entry.get("label", ""),
                text=entry.get("text", ""),
                icon=entry.get("icon", ""),
                tooltip=entry.get("tooltip", ""),
                section=entry.get("section", "middle"),
                position=entry.get("position", 0),
                enabled=entry.get("enabled", True),
                checkable=entry.get("checkable", False),
                default_checked=entry.get("default_checked", False),
                module=entry.get("module", ""),
                icon_size=entry.get("icon_size", 0),
                icon_checked_color=entry.get("icon_checked_color", ""),
                icon_unchecked_color=entry.get("icon_unchecked_color", ""),
            )
            items.append(item)
        return items

    @staticmethod
    def _serialize_items(items: list[NavItem]) -> list[dict]:
        result: list[dict] = []
        for item in items:
            d: dict = {"type": item.item_type, "id": item.id, "section": item.section, "position": item.position}
            if item.item_type == "button":
                d["text"] = item.text
                d["label"] = item.label
                d["tooltip"] = item.tooltip
                d["enabled"] = item.enabled
                if item.icon:
                    d["icon"] = item.icon
                if item.checkable:
                    d["checkable"] = True
                    d["default_checked"] = item.default_checked
                if item.module:
                    d["module"] = item.module
                if item.icon_size:
                    d["icon_size"] = item.icon_size
                if item.icon_checked_color:
                    d["icon_checked_color"] = item.icon_checked_color
                if item.icon_unchecked_color:
                    d["icon_unchecked_color"] = item.icon_unchecked_color
            result.append(d)
        return result

    # ---------- 查询 ----------

    def get_items(self, side: str) -> list[NavItem]:
        """按 position 排序返回指定侧的所有注册项。"""
        items = self._left_items if side == "left" else self._right_items
        return sorted(items, key=lambda x: x.position)

    def get_item(self, item_id: str) -> Optional[NavItem]:
        """按 ID 查找注册项。"""
        for items in (self._left_items, self._right_items):
            for item in items:
                if item.id == item_id:
                    return item
        return None

    def get_buttons(self, side: str) -> list[NavItem]:
        """返回指定侧所有 type==button 的注册项（按 position 排序）。"""
        return [it for it in self.get_items(side) if it.item_type == "button"]

    # ---------- 修改 ----------

    def set_enabled(self, item_id: str, enabled: bool):
        """启用/禁用某个注册项。"""
        item = self.get_item(item_id)
        if item:
            item.enabled = enabled

    def set_checked(self, item_id: str, checked: bool):
        """设置某个按钮的默认选中状态。"""
        item = self.get_item(item_id)
        if item and item.item_type == "button" and item.checkable:
            item.default_checked = checked

    def add_item(self, side: str, item: NavItem):
        """向指定侧添加一个注册项。"""
        target = self._left_items if side == "left" else self._right_items
        # 移除同 ID 旧项
        target[:] = [it for it in target if it.id != item.id]
        target.append(item)

    def remove_item(self, item_id: str) -> bool:
        """按 ID 移除注册项。返回是否找到并移除。"""
        for lst in (self._left_items, self._right_items):
            for i, item in enumerate(lst):
                if item.id == item_id:
                    lst.pop(i)
                    return True
        return False

    # ---------- 属性 ----------

    @property
    def settings(self) -> dict:
        return self._settings

    @property
    def panel_width(self) -> int:
        return self._settings.get("panel_width", 62)

    @property
    def button_size(self) -> tuple[int, int]:
        sz = self._settings.get("button_size", [50, 50])
        return (sz[0], sz[1])

    @property
    def label_font_size(self) -> int:
        return self._settings.get("label_font_size", 7)

    @property
    def spacing(self) -> int:
        return self._settings.get("spacing", 8)

    @property
    def margins(self) -> tuple[int, int, int, int]:
        m = self._settings.get("margins", [6, 12, 6, 12])
        return (m[0], m[1], m[2], m[3])

    @property
    def default_icon_checked_color(self) -> str:
        """所有按钮的默认选中色键名。"""
        return self._settings.get("icon_checked_color", "white")

    @property
    def default_icon_unchecked_color(self) -> str:
        """所有按钮的默认不选中色键名。"""
        return self._settings.get("icon_unchecked_color", "subtext")
