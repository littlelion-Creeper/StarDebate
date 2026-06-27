"""命令自动补全悬浮框 — SuggestPopup

顶层工具窗口，独立 QSS 样式文件（suggest_popup.qss），跟随当前主题。
基于命令树结构，支持逐级补全：命令集 → 子命令集 → 后缀。
使用 HintDelegate 实现命令名+灰色提示同排双色显示。
"""

import os
import json

from PyQt5.QtWidgets import (
    QFrame, QListWidget, QListWidgetItem, QVBoxLayout,
    QStyledItemDelegate, QStyle,
)
from PyQt5.QtCore import Qt, QEvent, QPoint, QSize
from PyQt5.QtGui import QFont, QFontMetrics, QColor, QPainter

from .command_handler import (
    get_command_tree, walk_tree, get_node_completions, get_node_meta
)


# 自定义数据角色
DESC_ROLE = Qt.UserRole + 1
ITEM_TYPE_ROLE = Qt.UserRole + 2


class HintDelegate(QStyledItemDelegate):
    """带双色提示文字的列表项绘制器。
    
    命令名用主色（#cdd6f4），说明文字用灰色（#6c7086），
    选中时命令名变为蓝色（#89b4fa）。
    所有提示文字首字对齐于同一竖线。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.max_label_width = 0  # 由 SuggestPopup 更新

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        rect = option.rect
        text = index.data(Qt.DisplayRole) or ""
        desc = index.data(DESC_ROLE) or ""
        itype = index.data(ITEM_TYPE_ROLE) or ""

        # 背景
        is_selected = bool(option.state & QStyle.State_Selected)
        is_hover = bool(option.state & QStyle.State_MouseOver)
        if is_selected:
            painter.fillRect(rect, QColor("#585b70"))
        elif is_hover:
            painter.fillRect(rect, QColor("#45475a"))

        if desc:
            # 命令名
            painter.setPen(QColor("#89b4fa" if is_selected else "#cdd6f4"))
            painter.drawText(rect.adjusted(10, 0, 0, 0), Qt.AlignVCenter, text)
            # 提示文字从 max_label_width 右侧 28px 处开始（白色）
            desc_x = 28 + self.max_label_width
            painter.setPen(QColor("#cdd6f4"))
            desc_rect = rect.adjusted(desc_x, 0, -8, 0)
            painter.drawText(desc_rect, Qt.AlignVCenter | Qt.AlignLeft, desc)
        elif itype == "placeholder":
            # 占位符：灰色斜体
            painter.setPen(QColor("#6c7086"))
            font = painter.font()
            font.setItalic(True)
            painter.setFont(font)
            painter.drawText(rect.adjusted(10, 0, 0, 0), Qt.AlignVCenter, text)
        else:
            painter.setPen(QColor("#89b4fa" if is_selected else "#cdd6f4"))
            painter.drawText(rect.adjusted(10, 0, 0, 0), Qt.AlignVCenter, text)

        painter.restore()

    def sizeHint(self, option, index):
        desc = index.data(DESC_ROLE) or ""
        w = 400 if desc else 200
        return QSize(w, 26)


class SuggestPopup(QFrame):
    """命令自动补全悬浮提示框 — 基于命令树的逐级补全"""

    MAX_VISIBLE = 10  # 基础值，_resize_to_content 中会根据匹配数动态提升

    QSS_PATH = "style/themes/{theme}/suggest_popup.qss"

    def __init__(self, dialog_parent, cmd_input):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint |
                         Qt.WindowStaysOnTopHint)
        self.setObjectName("suggestPopup")
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._cmd_input = cmd_input
        self._dialog_parent = dialog_parent
        from components.res_path import get_resource_root
        self._project_root = get_resource_root()
        self._main_window = None  # 由 DebugConsoleWindow 注入

        # 命令树
        self._tree = get_command_tree()

        # ── 当前补全上下文 ──
        self._current_path: list[str] = []       # 已确认的路径 token
        self._is_root_mode: bool = True          # True=根级匹配; False=节点子级
        self._current_completions: list[dict] = []  # 当前显示的补全项

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self._list = QListWidget()
        self._list.setObjectName("suggestList")
        self._list.setFont(QFont("Consolas", 10))
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setFocusPolicy(Qt.NoFocus)
        self._list.setItemDelegate(HintDelegate(self._list))
        self._list.installEventFilter(self)
        layout.addWidget(self._list)

        self._load_qss()
        self.hide()

    def _get_theme_name(self) -> str:
        config_path = os.path.join(self._project_root, "config", "config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f).get("theme", "catppuccin_mocha")
        except Exception:
            return "catppuccin_mocha"

    def _load_qss(self):
        theme = self._get_theme_name()
        qss_path = os.path.join(
            self._project_root, self.QSS_PATH.format(theme=theme)
        )
        if os.path.exists(qss_path):
            try:
                with open(qss_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
            except Exception:
                pass

    @staticmethod
    def _get_plugin_accent_color(theme: str) -> str:
        colors = {
            "catppuccin_mocha": "#2E6DDE",
            "catppuccin_macchiato": "#c6a0f6",
            "catppuccin_latte": "#8839ef",
        }
        return colors.get(theme, "#2E6DDE")

    def refresh_tree(self):
        """重新加载命令树（插件变动时调用）。"""
        self._tree = get_command_tree()

    # ── 动态补全解析 ────────────────────────────────────────

    def _resolve_dynamic(self, key: str) -> list[str]:
        """解析动态列表。"""
        mw = self._main_window
        if key == "plugin_list":
            if mw and hasattr(mw, "_plugin_manager"):
                try:
                    return [p.plugin_id
                            for p in mw._plugin_manager.get_all_plugins()]
                except Exception:
                    pass
        elif key == "theme_list":
            if mw and hasattr(mw, "_app_cfg"):
                try:
                    themes_dir = mw._app_cfg.get_themes_dir()
                    return [
                        d for d in os.listdir(themes_dir)
                        if os.path.isdir(os.path.join(themes_dir, d))
                        and os.path.exists(
                            os.path.join(themes_dir, d, "theme.json")
                        )
                    ]
                except Exception:
                    pass
        elif key == "command_completions":
            try:
                from .command_handler import get_flat_help_list
                flat = get_flat_help_list(self._tree)
                return [entry["cmd"] for entry in flat]
            except Exception:
                pass
        elif key == "alias_list":
            try:
                dlg = self._dialog_parent
                if dlg and hasattr(dlg, "_cmd_handler"):
                    return list(dlg._cmd_handler.get_aliases().keys())
            except Exception:
                pass
        return []

    # ── 补全构建 ────────────────────────────────────────────

    def _build_completions_from_node(self, node: dict) -> list[dict]:
        """从树节点构建补全列表。
        
        Returns:
            每项 dict: {"label": str, "path": str, "type": str, "desc": str}
            type = "child" | "dynamic" | "placeholder"
        """
        results = []
        completions = get_node_completions(node)
        children_dict = node.get("children", node) if isinstance(node, dict) else {}

        for comp in completions:
            name = comp["name"]
            is_placeholder = comp.get("is_placeholder", False)
            dynamic_key = comp.get("dynamic")

            # 从子节点提取描述
            child_node = children_dict.get(name, {}) if isinstance(children_dict, dict) else {}
            child_meta = get_node_meta(child_node) if isinstance(child_node, dict) else {}
            desc = child_meta.get("desc", "")

            if dynamic_key is not None:
                dynamic_items = self._resolve_dynamic(dynamic_key)
                if dynamic_items:
                    for item in dynamic_items:
                        full_path = " ".join(self._current_path + [item])
                        results.append({
                            "label": item, "path": full_path,
                            "type": "dynamic", "desc": desc,
                        })
                elif is_placeholder:
                    full_path = " ".join(self._current_path + [name])
                    results.append({
                        "label": name, "path": full_path,
                        "type": "placeholder", "desc": "",
                    })
            elif is_placeholder:
                full_path = " ".join(self._current_path + [name])
                results.append({
                    "label": name, "path": full_path,
                    "type": "placeholder", "desc": "",
                })
            else:
                full_path = " ".join(self._current_path + [name])
                results.append({
                    "label": name, "path": full_path,
                    "type": "child", "desc": desc,
                })

        return results

    def _build_root_completions(self, partial: str) -> list[dict]:
        """从根节点构建根级补全列表（含别名）。"""
        results = []
        partial_lower = partial.lower()

        for key, val in self._tree.items():
            if key.startswith("_"):
                continue
            if key.lower().startswith(partial_lower):
                meta = get_node_meta(val) if isinstance(val, dict) else {}
                has_children = False
                if isinstance(val, dict):
                    children = val.get("children", {})
                    real_children = {k: v for k, v in children.items()
                                     if not k.startswith("_")}
                    has_children = bool(real_children)

                results.append({
                    "label": key,
                    "path": key,
                    "type": "root",
                    "meta": meta,
                    "has_children": has_children,
                    "desc": meta.get("desc", ""),
                })

        # 追加别名（匹配前缀时显示）
        try:
            dlg = self._dialog_parent
            if dlg and hasattr(dlg, "_cmd_handler"):
                aliases = dlg._cmd_handler.get_aliases()
                for alias_name, alias_cmd in aliases.items():
                    if alias_name.lower().startswith(partial_lower):
                        results.append({
                            "label": alias_name,
                            "path": alias_name,
                            "type": "alias",
                            "meta": {},
                            "has_children": False,
                            "desc": f"→ {alias_cmd}",
                        })
        except Exception:
            pass

        return results

    # ── 别名展开 ──────────────────────────────────────────

    def _resolve_alias(self, name: str):
        """查别名：返回展开后的 token 列表，非别名返回 None。"""
        dlg = self._dialog_parent
        if not dlg:
            return None
        if not hasattr(dlg, "_cmd_handler"):
            return None
        aliases = dlg._cmd_handler.get_aliases()
        if name in aliases:
            return aliases[name].split()
        return None

    def _walk_with_alias(self, tokens):
        """先用原路径走树，失败后检查首个 token 是否为别名并展开重试。
        
        Returns:
            (最终用于 _current_path 的路径, 树节点 or None)
        """
        node = walk_tree(self._tree, tokens)
        if node is not None:
            return tokens, node

        # 原路径失败 → 尝试别名展开
        if tokens:
            expanded = self._resolve_alias(tokens[0])
            if expanded is not None:
                expanded_tokens = expanded + tokens[1:]
                node = walk_tree(self._tree, expanded_tokens)
                if node is not None:
                    return tokens, node  # _current_path 仍用原路径

        return tokens, None

    # ── 显示 ────────────────────────────────────────────────

    def show_suggestions(self, partial: str):
        """根据输入显示补全（原路径优先，失败后别名展开兜底）。"""
        text = partial.strip()
        if not text:
            self.hide()
            return

        has_trailing_space = partial.endswith(" ") and len(partial.strip()) > 0

        if has_trailing_space:
            tokens = text.split()
            path, node = self._walk_with_alias(tokens)
            if node is None:
                self.hide()
                return
            self._current_path = path
            self._is_root_mode = False
            self._current_completions = self._build_completions_from_node(node)
            self._display_completions(self._current_completions, "")

        elif " " in text:
            tokens = text.split()
            path_tokens = tokens[:-1]
            partial_last = tokens[-1]

            path, node = self._walk_with_alias(path_tokens)
            if node is None:
                self.hide()
                return

            self._current_path = path
            self._is_root_mode = False
            all_comps = self._build_completions_from_node(node)
            self._current_completions = all_comps

            filtered = [
                c for c in all_comps
                if c["label"].lower().startswith(partial_last.lower())
            ]
            self._display_completions(filtered, partial_last)

        else:
            self._is_root_mode = True
            self._current_path = []
            comps = self._build_root_completions(text)
            self._current_completions = comps
            self._display_completions(comps, text)

    def _display_completions(self, completions: list[dict], partial: str):
        """在列表中显示补全项（使用 HintDelegate 双色绘制）。"""
        self._list.clear()

        if not completions:
            self.hide()
            return

        # 预计算最大标签宽度（含前导空格），用于对齐提示词
        fm = QFontMetrics(self._list.font())
        max_lw = 0
        for comp in completions:
            lw = fm.boundingRect(f"  {comp['label']}").width()
            if lw > max_lw:
                max_lw = lw
        # 更新 delegate 对齐位置
        delegate = self._list.itemDelegate()
        if isinstance(delegate, HintDelegate):
            delegate.max_label_width = max_lw

        for comp in completions:
            label = comp["label"]
            ctype = comp.get("type", "")
            desc = comp.get("desc", "")

            item = QListWidgetItem(f"  {label}")
            item.setData(Qt.UserRole, comp["path"])
            item.setData(DESC_ROLE, desc)
            item.setData(ITEM_TYPE_ROLE, ctype)

            if ctype == "placeholder":
                item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            elif ctype == "dynamic":
                accent = self._get_plugin_accent_color(self._get_theme_name())
                item.setForeground(QColor(accent))

            self._list.addItem(item)

        self._list.setCurrentRow(0)
        self._show_popup()

    def _is_dynamic_empty(self, comp: dict) -> bool:
        """判断动态补全是否为空（降级为占位符显示）。"""
        return False  # 动态项已在 _build... 中过滤

    def _show_popup(self):
        """调整尺寸、定位并显示。"""
        self._resize_to_content()
        self._position_below_cursor()
        if self.isVisible():
            self.hide()
        self.show()
        self.raise_()
        if self._dialog_parent:
            self._dialog_parent.installEventFilter(self)

    def _resize_to_content(self):
        fm = QFontMetrics(self._list.font())
        item_h = fm.height() + 6
        count = self._list.count()
        # 匹配项数与可见项数相同，上限 14 项
        n_visible = min(count, 14)
        n_visible = max(1, n_visible)
        list_h = n_visible * item_h + 6

        max_px = 0
        for i in range(self._list.count()):
            item = self._list.item(i)
            label_w = fm.boundingRect(item.text()).width()
            desc = item.data(DESC_ROLE) or ""
            total_w = label_w
            if desc:
                # 包含 [desc] 的完整宽度 + 28px 间距
                desc_full = f"[{desc}]"
                desc_w = fm.boundingRect(desc_full).width()
                total_w = label_w + 28 + desc_w
            if total_w > max_px:
                max_px = total_w
        # 一次函数冗余：内容越长冗余越大，最小 20px
        redundancy = max(20, int(max_px * 0.1))
        lw = max_px + redundancy
        lw = min(max(180, lw), 520)

        self.setFixedSize(lw + 4, list_h + 4)
        self._list.setFixedSize(lw, list_h)
        self.updateGeometry()

    def _position_below_cursor(self):
        input_global = self._cmd_input.mapToGlobal(QPoint(0, 0))
        cursor_rect = self._cmd_input.cursorRect()
        cursor_bottom_y = input_global.y() + cursor_rect.bottom() + 2
        cursor_right_x = input_global.x() + cursor_rect.right()
        popup_x = cursor_right_x - self.width()
        popup_y = cursor_bottom_y
        if popup_x < input_global.x():
            popup_x = input_global.x()
        self.move(popup_x, popup_y)

    # ── 选择操作 ────────────────────────────────────────────

    def select_next(self):
        scroll_pos = self._list.verticalScrollBar().value()
        row = self._list.currentRow()
        nxt = row + 1 if row < self._list.count() - 1 else 0
        self._list.setCurrentRow(nxt)
        self._list.verticalScrollBar().setValue(scroll_pos)

    def select_prev(self):
        scroll_pos = self._list.verticalScrollBar().value()
        row = self._list.currentRow()
        prv = row - 1 if row > 0 else self._list.count() - 1
        self._list.setCurrentRow(prv)
        self._list.verticalScrollBar().setValue(scroll_pos)

    def get_selected_cmd(self) -> str:
        item = self._list.currentItem()
        return item.data(Qt.UserRole) if item else ""

    def apply_to_input(self, execute: bool = False):
        path = self.get_selected_cmd()
        if not path:
            return
        self._cmd_input.setText(path)
        self._cmd_input.setFocus()
        self.hide()
        if execute:
            self._cmd_input.returnPressed.emit()

    # ── 键盘事件 ────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if (obj is self._dialog_parent
                and event.type() == QEvent.WindowDeactivate):
            if self.isVisible():
                self.hide()
            self._dialog_parent.removeEventFilter(self)
            return False

        if obj is self._list and event.type() == event.KeyPress:
            key = event.key()
            if key == Qt.Key_Up:
                self.select_prev()
                return True
            if key == Qt.Key_Down:
                self.select_next()
                return True
            if key in (Qt.Key_Tab, Qt.Key_Right):
                self.apply_to_input(execute=False)
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self.apply_to_input(execute=True)
                return True
            if key == Qt.Key_Escape:
                self.hide()
                self._cmd_input.setFocus()
                return True
            if key == Qt.Key_Backspace:
                self.hide()
                self._cmd_input.setFocus()
                self._cmd_input.event(event)
                return True
        return super().eventFilter(obj, event)
