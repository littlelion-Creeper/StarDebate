"""
顶部导航栏管理器 — 将菜单按钮注入 TitleBar 标题栏

TopNavManager 读取 TopNavRegistry，根据注册表中的分区配置，
将按钮注入到 TitleBar 的对应注入区（menu_section / right_section / plugin_section），
实现标题栏与菜单栏的融合。

使用方式：
    from workers.top_nav import TopNavManager, TopNavRegistry

    registry = TopNavRegistry("config/menu_main_window.json")
    registry.load()
    top_nav_mgr = TopNavManager(mw, registry)
    top_nav_mgr.inject_into_titlebar(title_bar)   # ★ 注入到 TitleBar
"""
from __future__ import annotations

from components.theme_colors import tc, refresh
from typing import Optional, Callable, Any
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QPushButton, QMenu, QAction, QWidget,
)

from .top_nav_registry import TopNavRegistry, TopNavItem, TopNavSubItem


# 前向引用 TitleBar 类型（避免循环导入）
from PyQt5.QtWidgets import QHBoxLayout as _LayoutRef


class TopNavManager:
    """顶部导航栏管理器 — 将注册表按钮注入 TitleBar"""

    def __init__(self, mw: QWidget, registry: TopNavRegistry):
        self._mw = mw
        self._registry = registry

        # 控件引用表
        self._buttons: dict[str, QPushButton] = {}       # id → QPushButton
        self._menus: dict[str, QMenu] = {}                # id → QMenu
        self._actions: dict[str, QAction] = {}            # "parent_id/sub_id" → QAction

        # 插件区布局引用
        self._plugin_area_layouts: dict[str, QHBoxLayout] = {}  # plugin_area_id → QHBoxLayout

        # 插件子菜单项动态引用（用于删除清理）
        self._plugin_sub_actions: dict[str, list[tuple[QAction, str]]] = {}

        # TitleBar 引用
        self._titlebar: Optional[Any] = None

    # ==================== ★ 注入到 TitleBar ====================

    def inject_into_titlebar(self, titlebar) -> None:
        """将注册表中的控件注入到 TitleBar 的对应注入区。

        - menu_area 的条目 → titlebar.get_menu_section()
        - right_area 的 plugin_area → titlebar.get_plugin_section()
        - right_area 的 button/separator → titlebar.get_right_section()
        - stretch 忽略（TitleBar 的 drag_area 已提供弹性空间）

        调用前请确保 registry.load() 已成功。
        """
        from components.title_bar import TitleBar

        self._titlebar = titlebar

        # 清除旧的注入控件
        self._clear_injected_widgets()

        # 清除引用
        self._buttons.clear()
        self._menus.clear()
        self._actions.clear()
        self._plugin_area_layouts.clear()

        btn_w = self._registry.button_min_width
        btn_h = self._registry.button_height

        items = self._registry.get_items()

        for item in items:
            if not item.enabled:
                continue

            section = item.section  # "menu_area" | "right_area"

            if item.item_type == "separator":
                sep = QFrame()
                sep.setFrameShape(QFrame.VLine)
                sep.setStyleSheet(f"QFrame {{ color: {tc('divider')}; max-width: 1px; margin: 5px 2px; }}")
                if section == "right_area":
                    titlebar.get_right_section().addWidget(sep)
                else:
                    titlebar.get_menu_section().addWidget(sep)

            elif item.item_type == "stretch":
                # TitleBar 的 drag_area 已提供弹性空间，忽略
                pass

            elif item.item_type == "plugin_area":
                # 插件区注入到 plugin_section
                target_layout: QHBoxLayout = titlebar.get_plugin_section()
                self._plugin_area_layouts[item.id] = target_layout
                self._build_plugin_area_buttons(item.id, item.plugin_buttons)

            elif item.item_type == "menu_button":
                btn, menu = self._build_menu_button(item, btn_w, btn_h)
                self._buttons[item.id] = btn
                self._menus[item.id] = menu
                if section == "right_area":
                    titlebar.get_right_section().addWidget(btn)
                else:
                    titlebar.get_menu_section().addWidget(btn)

            elif item.item_type == "button":
                btn = self._build_standard_button(item, btn_w, btn_h)
                self._buttons[item.id] = btn
                if section == "right_area":
                    titlebar.get_right_section().addWidget(btn)
                else:
                    titlebar.get_menu_section().addWidget(btn)

    def _clear_injected_widgets(self):
        """清除 TitleBar 注入区中由本管理器创建的所有控件。"""
        if self._titlebar is None:
            return
        for layout in [
            self._titlebar.get_menu_section(),
            self._titlebar.get_right_section(),
            self._titlebar.get_plugin_section(),
        ]:
            self._clear_layout_widgets(layout)

    # ==================== 构建方法 ====================

    def _get_disabled_features(self) -> set:
        """获取主窗口设置的禁用功能ID集合。"""
        try:
            raw = getattr(self._mw, "_disabled_features", [])
            if isinstance(raw, (list, tuple)):
                return set(raw)
        except Exception:
            pass
        return set()

    def _build_menu_button(self, item: TopNavItem, btn_w: int, btn_h: int) -> tuple[QPushButton, QMenu]:
        """创建带下拉菜单的按钮，返回 (btn, menu)。

        如果初始无菜单项，则创建为普通按钮（菜单为空时不 setMenu），
        后续通过 register_plugin_sub_menu 可动态添加菜单。

        对设置了 dev_feature_id 的子菜单项，如果该功能在禁用列表中则跳过。
        """
        btn = QPushButton(f" {item.text}")
        btn.setObjectName("topNavBtn")
        btn.setToolTip(item.tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(btn_h)
        btn.setMinimumWidth(btn_w)

        disabled_features = self._get_disabled_features()
        menu = QMenu(self._mw)
        menu.setObjectName("topNavMenu")

        has_items = False
        for si in sorted(item.menu_items, key=lambda x: x.position):
            # ── 开发者模式过滤 ────────────────────────────
            if si.dev_feature_id and si.dev_feature_id in disabled_features:
                continue

            if si.item_type == "separator":
                menu.addSeparator()
                has_items = True
            else:
                action = menu.addAction(si.text)
                self._actions[f"{item.id}/{si.id}"] = action
                has_items = True

                if si.plugin_id:
                    pass  # 插件子菜单项，回调在 rebuild_plugin_buttons 中连接
                elif si.callback:
                    callback_method = getattr(self._mw, si.callback, None)
                    if callback_method:
                        action.triggered.connect(callback_method)

        if has_items:
            btn.setMenu(menu)

        return btn, menu

    def _build_standard_button(self, item: TopNavItem, btn_w: int, btn_h: int) -> QPushButton:
        """创建独立按钮（无下拉菜单）。"""
        btn = QPushButton(f" {item.text}")
        btn.setObjectName("topNavBtn")
        btn.setToolTip(item.tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(btn_h)
        btn.setMinimumWidth(btn_w)

        if item.callback:
            callback_method = getattr(self._mw, item.callback, None)
            if callback_method:
                btn.clicked.connect(callback_method)

        return btn

    def _build_plugin_area_buttons(self, area_id: str, plugin_buttons: list[dict]):
        """在 plugin_area 布局中构建插件按钮。"""
        layout = self._plugin_area_layouts.get(area_id)
        if layout is None:
            return

        self._clear_layout_widgets(layout)

        for btn_data in plugin_buttons:
            btn = QPushButton(f" {btn_data.get('text', '')}")
            btn.setObjectName("topNavBtn")
            btn.setToolTip(btn_data.get("tooltip", ""))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(self._registry.button_height)
            btn.setMinimumWidth(self._registry.button_min_width)

            callback = btn_data.get("callback")
            if callable(callback):
                btn.clicked.connect(callback)

            layout.addWidget(btn)

            btn_id = btn_data.get("id", "")
            if btn_id:
                self._buttons[btn_id] = btn

    def _clear_layout_widgets(self, layout: QHBoxLayout):
        """清除布局中所有子控件（保留布局本身）。"""
        while layout.count():
            layout_item = layout.takeAt(0)
            if layout_item.widget():
                layout_item.widget().deleteLater()
            elif layout_item.layout():
                self._clear_layout_widgets(layout_item.layout())

    # ==================== 插件注册 ====================

    def register_plugin_top_button(self, plugin_area_id: str, btn_data: dict):
        """向 plugin_area 注册一个插件顶部按钮。"""
        self._registry.add_plugin_button(plugin_area_id, btn_data)
        item = self._registry.get_item(plugin_area_id)
        if item:
            self._build_plugin_area_buttons(plugin_area_id, item.plugin_buttons)

    def register_plugin_sub_menu(self, parent_menu_id: str, sub_data: dict):
        """向指定菜单按钮注册一个插件子菜单项。

        如果目标按钮尚无菜单（如初始为空的 menu_button），则动态创建菜单并绑定。
        """
        self._registry.add_plugin_sub_menu(parent_menu_id, sub_data)
        menu = self._menus.get(parent_menu_id)
        if menu is None:
            menu = QMenu(self._mw)
            menu.setObjectName("topNavMenu")
            self._menus[parent_menu_id] = menu
            btn = self._buttons.get(parent_menu_id)
            if btn:
                btn.setMenu(menu)

        sub_id = sub_data.get("id", "")
        text = sub_data.get("text", "")
        callback = sub_data.get("callback")
        plugin_id = sub_data.get("plugin_id", "")

        action = menu.addAction(text)
        self._actions[f"{parent_menu_id}/{sub_id}"] = action

        if callable(callback):
            action.triggered.connect(callback)

        if parent_menu_id not in self._plugin_sub_actions:
            self._plugin_sub_actions[parent_menu_id] = []
        self._plugin_sub_actions[parent_menu_id].append((action, plugin_id))

    def remove_plugin_items(self, plugin_id: str):
        """移除指定插件的所有动态注入项。"""
        self._registry.remove_plugin_items(plugin_id)

        for area_id, layout in self._plugin_area_layouts.items():
            item = self._registry.get_item(area_id)
            if item:
                self._build_plugin_area_buttons(area_id, item.plugin_buttons)

        for parent_menu_id, entries in list(self._plugin_sub_actions.items()):
            remaining = []
            for action, pid in entries:
                if pid == plugin_id:
                    action.deleteLater()
                else:
                    remaining.append((action, pid))
            if remaining:
                self._plugin_sub_actions[parent_menu_id] = remaining
            else:
                self._plugin_sub_actions.pop(parent_menu_id, None)

    def rebuild_plugin_buttons(self, plugin_manager):
        """根据已启用的插件刷新顶部导航栏中的插件按钮和子菜单项。

        由主窗口在插件加载/启用/禁用/导入/删除时调用。
        """
        self._registry.remove_all_plugin_items()

        for area_id in self._plugin_area_layouts:
            item = self._registry.get_item(area_id)
            if item:
                item.plugin_buttons.clear()

        for parent_menu_id in list(self._plugin_sub_actions.keys()):
            for action, _ in self._plugin_sub_actions[parent_menu_id]:
                action.deleteLater()
            self._plugin_sub_actions.pop(parent_menu_id, None)

        # 获取所有已启用插件的顶部导航按钮
        top_nav_buttons = plugin_manager.get_enabled_top_nav_buttons()
        for btn_data in top_nav_buttons:
            area_id = btn_data.get("area", "plugin_area_top")
            self._registry.add_plugin_button(area_id, {
                "id": btn_data["id"],
                "text": btn_data["text"],
                "tooltip": btn_data.get("tooltip", ""),
                "callback": btn_data.get("callback"),
                "plugin_id": btn_data.get("plugin_id", ""),
            })

        # 获取所有已启用插件的顶部子菜单项
        top_nav_sub_items = plugin_manager.get_enabled_top_nav_sub_menus()
        for sub_data in top_nav_sub_items:
            parent_menu_id = sub_data.get("parent_menu_id", "file_menu")
            self._registry.add_plugin_sub_menu(parent_menu_id, {
                "id": sub_data["id"],
                "text": sub_data["text"],
                "callback": sub_data.get("callback"),
                "plugin_id": sub_data.get("plugin_id", ""),
            })

        # 重建所有 plugin_area
        for area_id, layout in self._plugin_area_layouts.items():
            item = self._registry.get_item(area_id)
            if item:
                self._build_plugin_area_buttons(area_id, item.plugin_buttons)

        # 重建所有菜单中的插件子项
        for parent_menu_id, menu in self._menus.items():
            item = self._registry.get_item(parent_menu_id)
            if item and item.item_type == "menu_button":
                if parent_menu_id in self._plugin_sub_actions:
                    for action, _ in self._plugin_sub_actions[parent_menu_id]:
                        menu.removeAction(action)
                        action.deleteLater()
                    self._plugin_sub_actions.pop(parent_menu_id, None)

                for si in item.menu_items:
                    if si.plugin_id:
                        action = menu.addAction(si.text)
                        self._actions[f"{parent_menu_id}/{si.id}"] = action
                        callback = self._find_sub_menu_callback(plugin_manager, si.plugin_id, si.id)
                        if callable(callback):
                            action.triggered.connect(callback)
                        if parent_menu_id not in self._plugin_sub_actions:
                            self._plugin_sub_actions[parent_menu_id] = []
                        self._plugin_sub_actions[parent_menu_id].append((action, si.plugin_id))

    def _find_sub_menu_callback(self, plugin_manager, plugin_id: str, sub_id: str) -> Optional[Callable]:
        """从插件管理器中查找子菜单项的回调函数。"""
        sub_items = plugin_manager.get_enabled_top_nav_sub_menus()
        for sd in sub_items:
            if sd.get("plugin_id") == plugin_id and sd.get("id") == sub_id:
                cb = sd.get("callback")
                if callable(cb):
                    return cb
        return None

    # ==================== 查询 ====================

    def get_button(self, button_id: str) -> Optional[QPushButton]:
        """按注册表 ID 获取按钮控件。"""
        return self._buttons.get(button_id)

    def get_menu(self, menu_id: str) -> Optional[QMenu]:
        """按注册表 ID 获取菜单。"""
        return self._menus.get(menu_id)

    def get_action(self, parent_id: str, sub_id: str) -> Optional[QAction]:
        """获取菜单动作。"""
        return self._actions.get(f"{parent_id}/{sub_id}")

    # ==================== 批量操作 ====================

    def set_all_disabled(self, disabled: bool):
        """设置所有顶部导航按钮的禁用状态。"""
        disabled_qss = (
            "QPushButton { background-color: #1e1e2e; border: 1px solid #313244; "
            "border-radius: 6px; font-size: 12px; color: #45475a; }"
        )
        for btn in self._buttons.values():
            btn.setEnabled(not disabled)
            if disabled:
                btn.setStyleSheet(disabled_qss)
            else:
                btn.setStyleSheet("")
                self._mw.style().unpolish(btn)
                self._mw.style().polish(btn)

    def set_buttons_disabled(self, button_ids: list[str], disabled: bool):
        """批量设置指定按钮的禁用状态。"""
        disabled_qss = (
            "QPushButton { background-color: #1e1e2e; border: 1px solid #313244; "
            "border-radius: 6px; font-size: 12px; color: #45475a; }"
        )
        for bid in button_ids:
            btn = self._buttons.get(bid)
            if btn is None:
                continue
            btn.setEnabled(not disabled)
            if disabled:
                btn.setStyleSheet(disabled_qss)
            else:
                btn.setStyleSheet("")
                self._mw.style().unpolish(btn)
                self._mw.style().polish(btn)

    # ==================== 属性 ====================

    @property
    def panel(self):
        """兼容旧版 panel 属性 — 返回标题栏引用"""
        return self._titlebar

    @property
    def registry(self) -> TopNavRegistry:
        return self._registry
