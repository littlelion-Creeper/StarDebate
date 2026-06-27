"""
顶部导航栏注册表 — TopNavItem / TopNavSubItem 数据类 + TopNavRegistry 管理类

TopNavItem 描述顶部导航栏中的每个元素（菜单按钮/独立按钮/分隔符/stretch/插件区）。
TopNavSubItem 描述菜单按钮下的子项（菜单项/分隔符）。
TopNavRegistry 负责加载/保存注册表 JSON，提供查询和修改接口。

v2.0 — 支持分区配置：menu_area / right_area 分别对应标题栏左右的注入区。
      注册表文件路径由构造函数传入（每个窗口一份独立 JSON）。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TopNavSubItem:
    """菜单按钮下的一个子项"""
    id: str                              # 唯一标识符
    item_type: str = "sub_menu"          # "sub_menu" | "separator"
    text: str = ""                        # 显示文本（emoji + 文字）
    position: int = 0                     # 排序位置
    callback: str = ""                    # 回调方法名（主窗口方法）
    plugin_id: str = ""                   # 所属插件ID（插件动态注入时设置，空=内置）
    dev_feature_id: str = ""              # 开发者模式功能ID（空=始终可见，非空=按开发者模式过滤）


@dataclass
class TopNavItem:
    """顶部导航栏中的一个元素"""
    id: str                              # 唯一标识符
    item_type: str = "button"            # "menu_button" | "button" | "separator" | "stretch" | "plugin_area"
    text: str = ""                        # 显示文本
    tooltip: str = ""                     # 按钮 tooltip
    position: int = 0                     # 排序位置（越小越靠前）
    enabled: bool = True                  # 是否启用
    callback: str = ""                    # 回调方法名（仅 button 类型，主窗口方法）
    section: str = "menu_area"            # ★ v2.0: 分区标识 "menu_area" | "right_area"
    menu_items: list[TopNavSubItem] = field(default_factory=list)  # 子菜单项（仅 menu_button 类型）
    # 插件动态注入按钮
    plugin_buttons: list[dict] = field(default_factory=list)  # [{id, text, tooltip, callback(可调用)}]


class TopNavRegistry:
    """顶部导航栏注册表 — 管理顶部菜单栏的按钮配置

    v2.0 变更：
    - 支持分区配置（menu_area / right_area），每个条目增加 section 字段
    - 注册表文件路径由构造函数传入，每个窗口独立配置
    - 向后兼容旧的扁平 items 格式
    """

    MENU_CONFIG_PATH = "config/menu_main_window.json"  # 默认主窗口菜单

    def __init__(self, registry_path: Optional[str] = None):
        self._path = registry_path or self.MENU_CONFIG_PATH
        self._items: list[TopNavItem] = []
        self._settings: dict = {}
        self._loaded = False

    # ---------- 加载 / 保存 ----------

    def load(self) -> bool:
        """从 JSON 文件加载注册表。返回是否加载成功。

        支持两种格式：
        1. 新格式（v2.0）：含 menu_area + right_area 分区键
        2. 旧格式：含 items 扁平列表，所有条目 section 默认 "menu_area"
        """
        if not os.path.exists(self._path):
            return False
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return False

        self._settings = data.get("settings", {})

        # 判断格式：有 menu_area/right_area 键为新格式
        if "menu_area" in data or "right_area" in data:
            items = []
            # menu_area 中的条目
            for entry in data.get("menu_area", []):
                entry = dict(entry)  # shallow copy
                entry.setdefault("section", "menu_area")
                items.append(entry)
            # right_area 中的条目
            for entry in data.get("right_area", []):
                entry = dict(entry)
                entry.setdefault("section", "right_area")
                items.append(entry)
            self._items = self._parse_items(items)
        else:
            # 旧格式（扁平 items 列表），所有条目默认 menu_area
            raw = data.get("items", [])
            for entry in raw:
                entry.setdefault("section", "menu_area")
            self._items = self._parse_items(raw)

        self._loaded = True
        return True

    def save(self) -> bool:
        """将当前注册表保存回 JSON 文件（v2.0 分区格式）。"""
        menu_items = [it for it in self._items if it.section == "menu_area"]
        right_items = [it for it in self._items if it.section == "right_area"]

        data = {
            "version": "1.0.0",
            "window": "main_window",
            "description": "顶部导航栏按钮注册表",
            "settings": self._settings,
            "menu_area": self._serialize_items(menu_items),
            "right_area": self._serialize_items(right_items),
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
    def _parse_items(raw: list[dict]) -> list[TopNavItem]:
        items: list[TopNavItem] = []
        for entry in raw:
            menu_items: list[TopNavSubItem] = []
            for sub in entry.get("items", []):
                menu_items.append(TopNavSubItem(
                    id=sub.get("id", ""),
                    item_type=sub.get("type", "sub_menu"),
                    text=sub.get("text", ""),
                    position=sub.get("position", 0),
                    callback=sub.get("callback", ""),
                    plugin_id=sub.get("plugin_id", ""),
                    dev_feature_id=sub.get("dev_feature_id", ""),
                ))

            item = TopNavItem(
                id=entry.get("id", ""),
                item_type=entry.get("type", "button"),
                text=entry.get("text", ""),
                tooltip=entry.get("tooltip", ""),
                position=entry.get("position", 0),
                enabled=entry.get("enabled", True),
                callback=entry.get("callback", ""),
                section=entry.get("section", "menu_area"),
                menu_items=menu_items,
                plugin_buttons=[],  # 运行时动态填充
            )
            items.append(item)
        return items

    @staticmethod
    def _serialize_items(items: list[TopNavItem]) -> list[dict]:
        result: list[dict] = []
        for item in items:
            d: dict = {
                "id": item.id,
                "type": item.item_type,
                "position": item.position,
            }
            if item.item_type in ("menu_button", "button"):
                d["text"] = item.text
                d["tooltip"] = item.tooltip
                d["enabled"] = item.enabled
            if item.item_type == "button" and item.callback:
                d["callback"] = item.callback
            if item.item_type == "menu_button":
                d["items"] = [
                    {
                        "id": si.id,
                        "type": si.item_type,
                        "text": si.text,
                        "position": si.position,
                    } | ({"callback": si.callback} if si.callback else {})
                    for si in sorted(item.menu_items, key=lambda x: x.position)
                ]
            result.append(d)
        return result

    # ---------- 查询 ----------

    def get_items(self) -> list[TopNavItem]:
        """按 position 排序返回所有注册项。"""
        return sorted(self._items, key=lambda x: x.position)

    def get_items_by_section(self, section: str) -> list[TopNavItem]:
        """按分区返回注册项（menu_area | right_area）。"""
        return sorted(
            [it for it in self._items if it.section == section],
            key=lambda x: x.position,
        )

    def get_item(self, item_id: str) -> Optional[TopNavItem]:
        """按 ID 查找注册项。"""
        for item in self._items:
            if item.id == item_id:
                return item
        return None

    def get_menu_item(self, parent_id: str, sub_id: str) -> Optional[TopNavSubItem]:
        """查找指定菜单按钮下的子项。"""
        parent = self.get_item(parent_id)
        if parent and parent.item_type == "menu_button":
            for si in parent.menu_items:
                if si.id == sub_id:
                    return si
        return None

    def add_plugin_button(self, plugin_area_id: str, btn_data: dict):
        """向指定 plugin_area 的动态按钮列表添加插件按钮。

        btn_data 格式: {"id": str, "text": str, "tooltip": str, "callback": callable, "plugin_id": str}
        """
        item = self.get_item(plugin_area_id)
        if item and item.item_type == "plugin_area":
            # 去重
            item.plugin_buttons = [
                b for b in item.plugin_buttons if b.get("id") != btn_data.get("id")
            ]
            item.plugin_buttons.append(btn_data)

    def add_plugin_sub_menu(self, parent_menu_id: str, sub_data: dict):
        """向指定菜单按钮添加插件子菜单项。

        sub_data 格式: {"id": str, "text": str, "callback": callable, "plugin_id": str}
        """
        item = self.get_item(parent_menu_id)
        if item and item.item_type == "menu_button":
            # 去重
            item.menu_items = [
                si for si in item.menu_items if si.id != sub_data.get("id")
            ]
            item.menu_items.append(TopNavSubItem(
                id=sub_data["id"],
                item_type="sub_menu",
                text=sub_data["text"],
                position=999,  # 插件项排最后
                callback="",
                plugin_id=sub_data.get("plugin_id", ""),
            ))
            item.menu_items.sort(key=lambda x: x.position)

    def remove_plugin_items(self, plugin_id: str):
        """移除指定插件的所有动态注入项（plugin_area 按钮 + 子菜单项）。"""
        for item in self._items:
            if item.item_type == "plugin_area":
                item.plugin_buttons = [
                    b for b in item.plugin_buttons
                    if b.get("plugin_id") != plugin_id
                ]
        for item in self._items:
            if item.item_type == "menu_button":
                item.menu_items = [
                    si for si in item.menu_items
                    if si.plugin_id != plugin_id
                ]

    def remove_all_plugin_items(self):
        """移除所有插件动态注入项（用于全局刷新）。"""
        for item in self._items:
            if item.item_type == "plugin_area":
                item.plugin_buttons.clear()
            if item.item_type == "menu_button":
                item.menu_items = [
                    si for si in item.menu_items if not si.plugin_id
                ]

    # ---------- 属性 ----------

    @property
    def settings(self) -> dict:
        return self._settings

    @property
    def bar_height(self) -> int:
        return self._settings.get("bar_height", 42)

    @property
    def button_min_width(self) -> int:
        return self._settings.get("button_min_width", 70)

    @property
    def button_height(self) -> int:
        return self._settings.get("button_height", 30)

    @property
    def font_size(self) -> int:
        return self._settings.get("font_size", 12)

    @property
    def spacing(self) -> int:
        return self._settings.get("spacing", 3)

    @property
    def margins(self) -> tuple[int, int, int, int]:
        m = self._settings.get("margins", [8, 4, 8, 4])
        return (m[0], m[1], m[2], m[3])

    @property
    def is_loaded(self) -> bool:
        return self._loaded
