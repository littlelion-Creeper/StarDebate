"""
导航栏管理器 — 根据注册表构建/管理左右两侧导航栏

NavBarManager 读取 NavRegistry，为每个注册项创建对应的控件，
并暴露按钮引用、插件区布局和批量操作接口。

使用方式：
    from workers.nav_bar import NavBarManager, NavRegistry

    registry = NavRegistry()
    registry.load()
    nav_mgr = NavBarManager(mw, registry)
    nav_mgr.register_module_builder("speech_writer", lambda: sw_mgr.build_nav_button())
    nav_mgr.register_module_builder("ai_expand", lambda: ae_mgr.build_nav_button())
    ...
    nav_mgr.build("left")   # → QFrame
    nav_mgr.build("right")  # → QFrame
"""
from __future__ import annotations

import os
import json
from components.theme_colors import tc, refresh
from typing import Optional, Callable, Any
from PyQt5.QtCore import Qt, QSize, QRectF
from PyQt5.QtGui import QFont, QIcon, QPixmap, QPainter, QColor
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QPushButton, QLabel, QWidget,
)
from PyQt5.QtSvg import QSvgRenderer

from .nav_registry import NavRegistry, NavItem
from components.res_path import get_resource_root

# 模块按钮构建器签名：返回 (QPushButton, QLabel)
ModuleBuilder = Callable[[], tuple[QPushButton, QLabel]]


class NavBarManager:
    """导航栏管理器 — 构建和统一管理左右两侧导航栏"""

    def __init__(self, mw: QWidget, registry: NavRegistry):
        self._mw = mw
        self._registry = registry
        self._left_panel: Optional[QFrame] = None
        self._right_panel: Optional[QFrame] = None

        # 模块按钮构建器注册表
        self._module_builders: dict[str, ModuleBuilder] = {}

        # 按钮/标签引用表
        self._buttons: dict[str, QPushButton] = {}
        self._labels: dict[str, QLabel] = {}

        # 插件按钮区布局
        self._plugin_left_layout: Optional[QVBoxLayout] = None
        self._plugin_right_layout: Optional[QVBoxLayout] = None

        # 插件按钮列表（用于批量管理）
        self._plugin_left_btns: list[QPushButton] = []
        self._plugin_right_btns: list[QPushButton] = []
        # 插件面板按钮元数据（btn → (plugin_id, icon_name, size)）
        self._plugin_btn_meta: dict[QPushButton, tuple] = {}

        # 标签可见性状态标志（供重建后的插件按钮标签跟随）
        self._labels_visible: bool = True

    # ==================== 图标加载 ====================

    @staticmethod
    def _render_svg_themed(svg_path: str, size: int = 28) -> QIcon:
        """用当前主题颜色渲染 SVG → QIcon。
        使用 QSvgRenderer + SourceIn 着色，兼容任意 SVG（无 fill 属性亦可）。
        """
        # 从 SvgRenderer 获取 mono 色键名（如 "accent_blue"）
        color_key = "text"
        try:
            from components.svg_renderer import SvgRenderer
            cm = SvgRenderer.get_color_map()
            key = cm.mono_color_key
            if key:
                color_key = key
        except Exception:
            pass
        # 用 theme_colors.tc() 解析 hex（保证跟随主题切换）
        from components.theme_colors import tc
        icon_color = QColor(tc(color_key, "#cdd6f4"))

        # 渲染原始 SVG
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)

        renderer = QSvgRenderer(svg_path)
        if not renderer.isValid():
            return QIcon()

        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        try:
            if painter.isActive():
                renderer.render(painter, QRectF(0, 0, size, size))
        finally:
            if painter.isActive():
                painter.end()

        # SourceIn 着色：将非透明像素全部替换为主题色
        tinted = QPixmap(size, size)
        tinted.fill(Qt.transparent)
        p = QPainter(tinted)
        p.setRenderHint(QPainter.Antialiasing)
        try:
            if p.isActive():
                p.drawPixmap(0, 0, pix)
                p.setCompositionMode(QPainter.CompositionMode_SourceIn)
                p.fillRect(QRectF(0, 0, size, size), icon_color)
        finally:
            if p.isActive():
                p.end()

        return QIcon(tinted)

    @staticmethod
    def load_nav_icon(icon_name: str) -> Optional[QIcon]:
        """从 icon/nav_bar/ 目录加载图标文件（.svg/.png）。
        .svg → SourceIn 着色，自动适配当前主题。
        .png → 直接加载（原色显示）。
        返回 QIcon（成功）或 None。
        """
        if not icon_name:
            return None
        icon_path = os.path.join(get_resource_root(), "icon", "nav_bar", icon_name)
        if not os.path.exists(icon_path):
            return None
        ext = os.path.splitext(icon_path)[1].lower()
        if ext == '.svg':
            return NavBarManager._render_svg_themed(icon_path, size=28)
        elif ext == '.png':
            icon = QIcon(icon_path)
            if icon.isNull():
                return None
            return icon
        return None

    @staticmethod
    def load_plugin_icon(plugin_id: str, icon_name: str) -> Optional[QIcon]:
        """从插件 icon 目录加载图标文件（plugins/<plugin_id>/icon/<icon_name>）。
        .svg → SourceIn 着色，自动适配当前主题。
        .png → 直接加载（原色显示）。
        返回 QIcon（成功）或 None。
        """
        if not icon_name or not plugin_id:
            return None
        icon_path = os.path.join(_PROJECT_ROOT, "plugins", plugin_id, "icon", icon_name)
        if not os.path.exists(icon_path):
            return None
        ext = os.path.splitext(icon_path)[1].lower()
        if ext == '.svg':
            return NavBarManager._render_svg_themed(icon_path, size=28)
        elif ext == '.png':
            icon = QIcon(icon_path)
            if icon.isNull():
                return None
            return icon
        return None

    @staticmethod
    def _apply_icon_to_button(btn: QPushButton, icon: QIcon,
                               icon_size: int = 28):
        """将 QIcon 应用到按钮，清除文字。"""
        btn.setIcon(icon)
        btn.setIconSize(QSize(icon_size, icon_size))
        btn.setText("")

    @staticmethod
    def _get_icon_color(color_key: str) -> QColor:
        """将颜色键名解析为 QColor。

        "white" → #FFFFFF 直接
        其他    → tc(key) 从当前主题 colors 解析
        """
        if color_key == "white":
            return QColor("#FFFFFF")
        from components.theme_colors import tc
        return QColor(tc(color_key, "#cdd6f4"))

    @staticmethod
    def _get_theme_icon_color() -> QColor:
        """获取当前主题的 SVG 不选中颜色（自动侦测）。

        深色主题 → mono 文字色（灰）
        浅色主题 → accent 主色（蓝），避免灰色在浅背景上难以辨认
        """
        color_key = "text"
        try:
            from components.svg_renderer import SvgRenderer
            cm = SvgRenderer.get_color_map()
            tname = cm.theme_name
            if tname:
                tpath = os.path.join(
                    get_resource_root(), "style", "themes", tname, "theme.json",
                )
                if os.path.isfile(tpath):
                    with open(tpath, "r", encoding="utf-8") as _f:
                        _td = json.load(_f)
                    if _td.get("type") == "light":
                        color_key = cm.dual_primary_key or "accent_blue"
                    else:
                        color_key = cm.mono_color_key or "text"
                else:
                    color_key = cm.mono_color_key or "text"
            else:
                color_key = cm.mono_color_key or "text"
        except Exception:
            pass
        from components.theme_colors import tc
        return QColor(tc(color_key, "#cdd6f4"))

    def _get_initial_color(self, item: NavItem) -> QColor:
        """获取按钮的初始图标颜色（遵循注册表颜色系统）。"""
        if not item.checkable:
            from components.theme_colors import tc
            return QColor(tc("subtext", "#cdd6f4"))
        if item.default_checked:
            key = (item.icon_checked_color
                    or self._registry.default_icon_checked_color
                    or "white")
        else:
            key = (item.icon_unchecked_color
                    or self._registry.default_icon_unchecked_color
                    or "")
        if key:
            return self._get_icon_color(key)
        return self._get_theme_icon_color()

    @staticmethod
    def _render_svg_colored(svg_path: str, color: QColor, size: int = 28) -> QIcon:
        """用指定颜色渲染 SVG → QIcon。"""
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        renderer = QSvgRenderer(svg_path)
        if not renderer.isValid():
            return QIcon()
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        try:
            if painter.isActive():
                renderer.render(painter, QRectF(0, 0, size, size))
        finally:
            if painter.isActive():
                painter.end()
        tinted = QPixmap(size, size)
        tinted.fill(Qt.transparent)
        p = QPainter(tinted)
        p.setRenderHint(QPainter.Antialiasing)
        try:
            if p.isActive():
                p.drawPixmap(0, 0, pix)
                p.setCompositionMode(QPainter.CompositionMode_SourceIn)
                p.fillRect(QRectF(0, 0, size, size), color)
        finally:
            if p.isActive():
                p.end()
        return QIcon(tinted)

    def _get_item_color(self, item_id: str, checked: bool) -> QColor:
        """从注册表和 settings 解析按钮当前状态的颜色。

        Args:
            item_id: 按钮的注册表 ID
            checked: True=选中，False=不选中

        Returns:
            QColor 颜色值
        """
        nav_item = self._registry.get_item(item_id)
        if checked:
            key = (nav_item.icon_checked_color
                    if nav_item and nav_item.icon_checked_color
                    else self._registry.default_icon_checked_color)
            return self._get_icon_color(key) if key else QColor("#FFFFFF")
        else:
            key = (nav_item.icon_unchecked_color
                    if nav_item and nav_item.icon_unchecked_color
                    else self._registry.default_icon_unchecked_color)
            if key:
                return self._get_icon_color(key)
            return self._get_theme_icon_color()  # 空=自动侦测

    def _on_nav_toggle_icon(self, btn: QPushButton, icon_name: str,
                             icon_size: int, item_id: str = None):
        """按钮选中/取消时切换 SVG 图标颜色。"""
        icon_path = os.path.join(get_resource_root(), "icon", "nav_bar", icon_name)
        if not os.path.isfile(icon_path):
            return
        color = (self._get_item_color(item_id, True) if btn.isChecked()
                 else self._get_item_color(item_id, False))
        icon = self._render_svg_colored(icon_path, color, icon_size)
        if icon is not None and not icon.isNull():
            self._apply_icon_to_button(btn, icon, icon_size)
            btn.update()

    def _on_plugin_toggle_icon(self, btn: QPushButton, plugin_id: str, icon_name: str):
        """插件按钮选中/取消时切换 SVG 图标颜色。"""
        icon_path = os.path.join(get_resource_root(), "plugins", plugin_id, "icon", icon_name)
        if not os.path.isfile(icon_path):
            return
        size = 28
        color = (self._get_icon_color("white") if btn.isChecked()
                 else self._get_theme_icon_color())
        icon = self._render_svg_colored(icon_path, color, size)
        if icon is not None and not icon.isNull():
            self._apply_icon_to_button(btn, icon, size)
            btn.update()

    # ==================== 按钮创建 ====================

    def _create_button(self, item: NavItem) -> tuple[QPushButton, QLabel]:
        """根据 NavItem 创建按钮（支持文字/图标自由选择）。"""
        bw, bh = self._registry.button_size
        label_fs = self._registry.label_font_size

        btn = QPushButton()
        btn.setObjectName("navToggleBtn")
        btn.setToolTip(item.tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(bw, bh)

        # ── 尝试加载图标 ──
        if item.icon:
            icon_size = item.icon_size if item.icon_size > 0 else 28
            icon_path = os.path.join(get_resource_root(), "icon", "nav_bar", item.icon)
            if os.path.isfile(icon_path) and item.checkable:
                # checkable 按钮：用注册表颜色系统
                color = self._get_initial_color(item)
                icon = self._render_svg_colored(icon_path, color, icon_size)
            else:
                # 非 checkable 或无图标文件：沿用旧方式
                icon = self.load_nav_icon(item.icon)
            if icon is not None and not icon.isNull():
                self._apply_icon_to_button(btn, icon, icon_size)
            else:
                btn.setText(item.text)
        else:
            btn.setText(item.text)

        if item.checkable:
            btn.setCheckable(True)
            # 选中时渲染为白色图标（先连接信号，再 setChecked 触发）
            if item.icon:
                icon_size = item.icon_size if item.icon_size > 0 else 28
                btn.toggled.connect(
                    lambda checked, b=btn, n=item.icon, s=icon_size, iid=item.id:
                    self._on_nav_toggle_icon(b, n, s, iid)
                )
            btn.setChecked(item.default_checked)

        lbl = QLabel(item.label)
        lbl.setObjectName("navBtnLabel")
        lbl.setFont(QFont("Microsoft YaHei", label_fs))
        lbl.setAlignment(Qt.AlignCenter)

        return btn, lbl

    def register_module_builder(self, module_id: str, builder: ModuleBuilder):
        """注册一个模块的导航按钮构建器。

        module_id 需与注册表中对应按钮的 'module' 字段匹配。
        builder 是一个无参回调，返回 (QPushButton, QLabel) 元组。
        """
        self._module_builders[module_id] = builder

    def unregister_module_builder(self, module_id: str):
        """取消注册模块构建器。"""
        self._module_builders.pop(module_id, None)

    # ==================== 构建 ====================

    def build(self, side: str) -> QFrame:
        """构建并返回指定侧的导航面板 QFrame。"""
        panel = QFrame()
        panel.setObjectName("navPanel")
        panel.setFixedWidth(self._registry.panel_width)
        panel.setSizePolicy(
            panel.sizePolicy().horizontalPolicy(),
            panel.sizePolicy().verticalPolicy(),
        )
        # 设置 expanding 垂直策略以确保填充全部高度
        from PyQt5.QtWidgets import QSizePolicy
        panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        layout = QVBoxLayout(panel)
        m = self._registry.margins
        layout.setContentsMargins(m[0], m[1], m[2], m[3])
        layout.setSpacing(self._registry.spacing)

        items = self._registry.get_items(side)

        for item in items:
            if not item.enabled:
                continue

            if item.item_type == "separator":
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setStyleSheet(f"QFrame {{ color: {tc('divider')}; max-height: 1px; }}")
                layout.addWidget(sep)

            elif item.item_type == "stretch":
                layout.addStretch()

            elif item.item_type == "plugin_area":
                sub_layout = QVBoxLayout()
                sub_layout.setSpacing(4)
                layout.addLayout(sub_layout)
                if side == "left":
                    self._plugin_left_layout = sub_layout
                else:
                    self._plugin_right_layout = sub_layout

            elif item.item_type == "button":
                if item.module and item.module in self._module_builders:
                    # 由外部模块提供按钮
                    try:
                        btn, lbl = self._module_builders[item.module]()
                    except Exception:
                        continue
                    self._buttons[item.id] = btn
                    self._labels[item.id] = lbl
                    # ★ 统一为模块按钮连接图标颜色切换
                    if btn.isCheckable() and item.icon:
                        _icon_size = item.icon_size if item.icon_size > 0 else 28
                        btn.toggled.connect(
                            lambda checked, b=btn, n=item.icon, s=_icon_size, iid=item.id:
                            self._on_nav_toggle_icon(b, n, s, iid)
                        )
                else:
                    # 创建标准按钮（支持文字/图标自由选择）
                    btn, lbl = self._create_button(item)
                    self._buttons[item.id] = btn
                    self._labels[item.id] = lbl

                layout.addWidget(self._buttons[item.id])
                layout.addWidget(self._labels[item.id])

        # 保存面板引用
        if side == "left":
            self._left_panel = panel
        else:
            self._right_panel = panel

        return panel

    def refresh_nav_icons(self):
        """主题切换后刷新所有导航按钮 + 插件面板按钮的 SVG 图标颜色。"""
        # ── 标准 / 模块按钮 ──────────────────────────────────────
        for item_id, btn in self._buttons.items():
            nav_item = self._registry.get_item(item_id)
            if not nav_item or not nav_item.icon:
                continue
            icon_name = nav_item.icon
            icon_size = nav_item.icon_size if nav_item.icon_size > 0 else 28
            icon_path = os.path.join(get_resource_root(), "icon", "nav_bar", icon_name)
            if not os.path.isfile(icon_path):
                continue
            if btn.isCheckable():
                color = self._get_item_color(item_id, btn.isChecked())
            else:
                # 非 checkable 按钮（如新建辩论/设置）：始终用主题 mono 色
                color = self._get_theme_icon_color()
            icon = self._render_svg_colored(icon_path, color, icon_size)
            if icon is not None and not icon.isNull():
                self._apply_icon_to_button(btn, icon, icon_size)
                btn.update()

        # ── 插件按钮（含导航按钮 + 面板按钮）─────────────────────
        for btn, (pid, iname, isize) in self._plugin_btn_meta.items():
            icon_path = os.path.join(get_resource_root(), "plugins", pid, "icon", iname)
            if not os.path.isfile(icon_path):
                continue
            if btn.isCheckable():
                color = (self._get_icon_color("white") if btn.isChecked()
                         else self._get_theme_icon_color())
            else:
                # 非 checkable 插件导航按钮：始终用主题 mono 色
                from components.theme_colors import tc as _tc
                color = QColor(_tc("subtext", "#cdd6f4"))
            icon = self._render_svg_colored(icon_path, color, isize)
            if icon is not None and not icon.isNull():
                self._apply_icon_to_button(btn, icon, isize)
                btn.update()

    def rebuild_plugin_buttons(self, plugin_manager):
        """根据已启用的插件刷新导航栏中的插件按钮区域。

        由主窗口在插件加载/启用/禁用/导入/删除时调用。
        """
        # 获取插件导航按钮和面板按钮数据
        left_nav_data = plugin_manager.get_enabled_nav_buttons("left")
        right_nav_data = plugin_manager.get_enabled_nav_buttons("right")
        left_panel_data = plugin_manager.get_enabled_panels("left")
        right_panel_data = plugin_manager.get_enabled_panels("right")
        center_panel_data = plugin_manager.get_enabled_panels("center")

        # 清除面板按钮引用和元数据
        if hasattr(self._mw, '_plugin_panel_btns'):
            self._mw._plugin_panel_btns.clear()
        self._plugin_btn_meta.clear()

        # 重建左侧插件区
        if self._plugin_left_layout is not None:
            self._clear_layout(self._plugin_left_layout)
            self._plugin_left_btns.clear()
            for btn_data in left_nav_data:
                self._add_plugin_button(self._plugin_left_layout, self._plugin_left_btns, btn_data)

        # 重建右侧插件区
        if self._plugin_right_layout is not None:
            self._clear_layout(self._plugin_right_layout)
            self._plugin_right_btns.clear()
            for btn_data in right_nav_data:
                self._add_plugin_button(self._plugin_right_layout, self._plugin_right_btns, btn_data)
            # 面板按钮也放在右侧
            for panel_data in left_panel_data + right_panel_data + center_panel_data:
                self._add_panel_button(self._plugin_right_layout, self._plugin_right_btns, panel_data)

        # 强制刷新布局
        if self._right_panel:
            self._right_panel.updateGeometry()
            self._right_panel.update()
        if self._left_panel:
            self._left_panel.updateGeometry()
            self._left_panel.update()

    # ==================== 插件按钮创建 ====================

    def _add_plugin_button(self, layout: QVBoxLayout, btn_list: list, btn_data: dict):
        """在布局中添加一个插件导航按钮（支持图标文件）。"""
        btn = QPushButton()
        btn.setObjectName("navToggleBtn")
        btn.setCheckable(False)
        btn.setToolTip(btn_data["tooltip"])
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(*self._registry.button_size)

        # ── 尝试加载插件图标（存放在插件自身目录下）──
        icon_name = btn_data.get("icon", "")
        plugin_id = btn_data.get("plugin_id", "")
        icon = self.load_plugin_icon(plugin_id, icon_name)
        if icon is not None:
            self._apply_icon_to_button(btn, icon)
            # 存储元数据供 refresh_nav_icons 刷新
            self._plugin_btn_meta[btn] = (plugin_id, icon_name, 28)
        else:
            btn.setText(btn_data["emoji"])

        try:
            cb = btn_data["callback"]
            btn.clicked.connect(lambda checked, cb=cb: cb())
        except Exception:
            pass

        lbl = QLabel(btn_data["label"])
        lbl.setObjectName("navPluginLabel")
        lbl.setFont(QFont("Microsoft YaHei", self._registry.label_font_size))
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setVisible(self._labels_visible)

        layout.addWidget(btn)
        layout.addWidget(lbl)
        btn.show()
        if self._labels_visible:
            lbl.show()
        btn_list.append(btn)

    def _add_panel_button(self, layout: QVBoxLayout, btn_list: list, panel_data: dict):
        """在布局中添加一个插件面板切换按钮（支持图标文件）。"""
        plugin_id = panel_data["plugin_id"]
        side = panel_data["side"]
        title = panel_data["title"]
        emoji = panel_data["emoji"]
        tooltip = panel_data["tooltip"]

        btn = QPushButton()
        btn.setObjectName("navToggleBtn")
        btn.setCheckable(True)
        btn.setChecked(False)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(*self._registry.button_size)

        # ── 尝试加载插件面板图标（存放在插件自身目录下）──
        icon_name = panel_data.get("icon", "")
        icon = self.load_plugin_icon(plugin_id, icon_name)
        if icon is not None:
            self._apply_icon_to_button(btn, icon)
            # 存储元数据供 refresh_nav_icons 使用
            self._plugin_btn_meta[btn] = (plugin_id, icon_name, 28)
            # 选中时渲染为白色图标
            btn.toggled.connect(
                lambda checked, b=btn, pid=plugin_id, n=icon_name:
                self._on_plugin_toggle_icon(b, pid, n)
            )
        else:
            btn.setText(emoji)

        # 回调延迟绑定（由主窗口提供_toggle_plugin_registered_panel）
        if hasattr(self._mw, '_toggle_plugin_registered_panel'):
            btn.clicked.connect(
                lambda checked, pid=plugin_id, s=side: self._mw._toggle_plugin_registered_panel(pid, s)
            )

        lbl = QLabel(title)
        lbl.setObjectName("navPanelLabel")
        lbl.setFont(QFont("Microsoft YaHei", self._registry.label_font_size))
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setVisible(self._labels_visible)

        layout.addWidget(btn)
        layout.addWidget(lbl)
        btn.show()
        if self._labels_visible:
            lbl.show()
        btn_list.append(btn)

        # 保存面板按钮引用
        if not hasattr(self._mw, '_plugin_panel_btns'):
            self._mw._plugin_panel_btns = {}
        self._mw._plugin_panel_btns[f"{plugin_id}_{side}"] = btn

    @staticmethod
    def _clear_layout(layout: QVBoxLayout):
        """清除布局中所有子控件。"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                NavBarManager._clear_layout(item.layout())

    # ==================== 按钮查询 ====================

    def get_button(self, button_id: str) -> Optional[QPushButton]:
        """按注册表 ID 获取按钮控件。"""
        return self._buttons.get(button_id)

    def get_label(self, button_id: str) -> Optional[QLabel]:
        """按注册表 ID 获取标签控件。"""
        return self._labels.get(button_id)

    def get_all_buttons(self, side: Optional[str] = None) -> dict[str, QPushButton]:
        """获取所有按钮。side=None 返回全部，否则过滤 'left'/'right'。"""
        if side is None:
            return dict(self._buttons)
        items = self._registry.get_items(side)
        return {
            item.id: self._buttons[item.id]
            for item in items
            if item.item_type == "button" and item.id in self._buttons
        }

    # ==================== 标签显示控制 ====================

    def set_labels_visible(self, visible: bool):
        """显示/隐藏所有导航按钮下方的文字标签（左右两侧 + 插件按钮）。

        Args:
            visible: True=显示名称, False=隐藏名称
        """
        self._labels_visible = visible
        # 1. 标准按钮 + 模块构建器返回的标签（_labels 字典覆盖所有注册按钮）
        for lbl in self._labels.values():
            lbl.setVisible(visible)
        # 2. 插件按钮 + 面板按钮标签（通过 objectName 筛选 findChildren）
        for panel in (self._left_panel, self._right_panel):
            if panel is None:
                continue
            for label in panel.findChildren(QLabel):
                obj_name = label.objectName()
                if obj_name in ("navPluginLabel", "navPanelLabel"):
                    label.setVisible(visible)

    # ==================== 批量操作 ====================

    def set_buttons_disabled(self, button_ids: list[str], disabled: bool,
                             disabled_qss: Optional[str] = None,
                             tooltip_overrides: Optional[dict[str, str]] = None):
        """批量设置按钮禁用状态。

        Args:
            button_ids: 按钮 ID 列表
            disabled: True=禁用, False=启用
            disabled_qss: 禁用时的内联样式（为 None 则使用默认灰色样式）
            tooltip_overrides: {button_id: tooltip_text} 恢复时还原的 tooltip
        """
        if disabled_qss is None:
            disabled_qss = (
                "QPushButton { background-color: #1e1e2e; border: 1px solid #313244; "
                "border-radius: 8px; font-size: 16px; color: #45475a; }"
            )

        for bid in button_ids:
            btn = self._buttons.get(bid)
            if btn is None:
                continue
            btn.setEnabled(not disabled)
            if disabled:
                btn.setStyleSheet(disabled_qss)
                if tooltip_overrides and bid in tooltip_overrides:
                    btn.setToolTip(tooltip_overrides[bid])
            else:
                btn.setStyleSheet("")
                self._mw.style().unpolish(btn)
                self._mw.style().polish(btn)
                # 恢复 tooltip
                if tooltip_overrides:
                    item = self._registry.get_item(bid)
                    if item:
                        btn.setToolTip(item.tooltip)

    def set_all_disabled(self, disabled: bool):
        """设置所有导航按钮的禁用状态（立论驳论答题期间调用）。"""
        # 右侧功能按钮（需改 tooltip）
        function_ids = [
            "speech_writer", "ai_expand", "notes", "training",
            "ai_framework", "cross_exam", "accept_exam",
        ]
        func_tooltips = {
            bid: "(答题中，暂不可用)" if disabled else self._registry.get_item(bid).tooltip
            for bid in function_ids
            if self._registry.get_item(bid)
        }

        # 左侧导航按钮（只需禁用，不改 tooltip）
        nav_ids = [
            "project_tree", "structure_tree", "match_schedule",
            "new_debate", "framework", "create_speech",
            "ref_doc", "ref_cards", "settings",
        ]

        all_ids = function_ids + nav_ids
        disabled_qss = (
            "QPushButton { background-color: #1e1e2e; border: 1px solid #313244; "
            "border-radius: 8px; font-size: 16px; color: #45475a; }"
        )

        for bid in all_ids:
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

        # 恢复功能按钮 tooltip
        for bid in function_ids:
            btn = self._buttons.get(bid)
            if btn is None:
                continue
            if disabled:
                btn.setToolTip("(答题中，暂不可用)")
            else:
                item = self._registry.get_item(bid)
                if item:
                    btn.setToolTip(item.tooltip)

    # ==================== 属性 ====================

    @property
    def left_panel(self) -> Optional[QFrame]:
        return self._left_panel

    @property
    def right_panel(self) -> Optional[QFrame]:
        return self._right_panel

    @property
    def plugin_left_layout(self) -> Optional[QVBoxLayout]:
        return self._plugin_left_layout

    @property
    def plugin_right_layout(self) -> Optional[QVBoxLayout]:
        return self._plugin_right_layout

    @property
    def plugin_left_btns(self) -> list[QPushButton]:
        return self._plugin_left_btns

    @property
    def plugin_right_btns(self) -> list[QPushButton]:
        return self._plugin_right_btns

    @property
    def registry(self) -> NavRegistry:
        return self._registry
