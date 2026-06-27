# -*- coding: utf-8 -*-
"""辩论框架节点控件与画布

FrameworkNodeWidget — 框架画布上的单个节点（拖拽/缩放/内联编辑/右键菜单）
FrameworkCanvas      — 框架画布（节点 CRUD、连接管理、自动布局、绘制连接线）
"""
import copy
from PyQt5.QtWidgets import (
    QUndoCommand,
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QMenu, QSizePolicy,
)
from PyQt5.QtCore import Qt, QSize, QTimer, QPointF
from PyQt5.QtGui import (
    QFont, QColor, QPainter, QPen, QPainterPath, QBrush, QPixmap,
)

from . import FRAMEWORK_NODE_TYPES, get_node_type_color


# ── 撤销快照命令 ──────────────────────────────────────────
class FrameworkSnapshotCommand(QUndoCommand):
    """保存/恢复整个框架数据的快照命令。"""
    def __init__(self, canvas, old_data, old_next_id, new_data, new_next_id, description):
        super().__init__(description)
        self._canvas = canvas
        self._old_state = (copy.deepcopy(old_data), old_next_id)
        self._new_state = (copy.deepcopy(new_data), new_next_id)
    def undo(self):
        self._canvas._restore_state(*self._old_state)
    def redo(self):
        self._canvas._restore_state(*self._new_state)


class FrameworkNodeTextCommand(QUndoCommand):
    """保存/恢复单个节点文本的命令。"""
    def __init__(self, canvas, node_id: int, old_text: str, new_text: str, description="编辑节点"):
        super().__init__(description)
        self._canvas = canvas
        self._node_id = node_id
        self._old_text = old_text
        self._new_text = new_text
    def _apply(self, text: str):
        for nd in self._canvas._data:
            if nd["id"] == self._node_id:
                nd["text"] = text
                w = self._canvas._node_map.get(self._node_id)
                if w:
                    w._node_data = nd  # 更新引用
                    w._update_label_text()
                break
        self._canvas._auto_save()
        self._canvas.update()
    def undo(self):
        self._apply(self._old_text)
    def redo(self):
        self._apply(self._new_text)


class FrameworkNodeWidget(QFrame):
    """框架画布上的单个节点

    支持：
      - 拖拽移动（左键拖拽非右下角区域）
      - 拖拽右下角调节宽高（左键拖拽右下角 16x16 手柄）
      - 双击内联编辑文本
      - 多行文本智能截断（最大 5 行，每行约 20 字）
    """
    MIN_W, MIN_H = 100, 40
    MAX_W, MAX_H = 400, 200
    HANDLE_SIZE = 16      # 右下角 resize 手柄大小

    def __init__(self, node_data: dict, canvas):
        super().__init__(canvas)
        self._canvas = canvas
        self._node_data = node_data
        self._drag_start = None
        self._resizing = False          # 是否正在 resize
        self._resize_origin = None      # resize 起始鼠标位置
        self._resize_orig_size = None   # resize 起始尺寸
        w = node_data.get("width", 140)
        h = node_data.get("height", 52)
        w = max(self.MIN_W, min(self.MAX_W, w))
        h = max(self.MIN_H, min(self.MAX_H, h))
        self.resize(w, h)
        self.setMinimumSize(self.MIN_W, self.MIN_H)
        self.setMaximumSize(self.MAX_W, self.MAX_H)
        self.setCursor(Qt.OpenHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self._build_ui()
        self._apply_pos()
        self._update_label_text()  # 应用智能截断

    # ---------- 智能文本截断 ----------

    def _truncate_text(self, text: str) -> str:
        """按节点宽度智能截断文本：最大 5 行，按实际显示行截断，多余用 …"""
        if not text:
            return "双击编辑"

        node_w = self.width()
        # 可用文本宽度 ≈ 节点宽 - 内边距 - 边框，9pt 中文字符约 10px
        chars_per_line = max(10, (node_w - 20) // 10)
        max_lines = 5

        # 按显式换行符拆分为段落
        paragraphs = text.split('\n')
        display_lines = []  # 实际显示行
        total_display = 0

        for para in paragraphs:
            if not para:
                # 空行
                display_lines.append('')
                total_display += 1
                if total_display >= max_lines:
                    break
                continue

            # 该段落按 chars_per_line 拆分为多个显示行
            para_lines = []
            remaining = para
            while remaining:
                para_lines.append(remaining[:chars_per_line])
                remaining = remaining[chars_per_line:]
            para_display = len(para_lines)

            if total_display + para_display <= max_lines:
                # 完整容纳
                display_lines.extend(para_lines)
                total_display += para_display
            elif total_display >= max_lines:
                # 已达上限，停止
                break
            else:
                # 部分容纳：能放几行放几行
                fit_lines = max_lines - total_display
                if fit_lines > 0:
                    display_lines.extend(para_lines[:fit_lines])
                    # 最后一行末尾追加省略号
                    last = display_lines[-1]
                    if len(last) > chars_per_line - 1:
                        last = last[:chars_per_line - 1]
                    display_lines[-1] = last + '…'
                total_display = max_lines
                break

        return '\n'.join(display_lines)

    def _update_label_text(self):
        """更新 QLabel 显示文本（应用截断）"""
        raw = self._node_data.get("text", "")
        display = self._truncate_text(raw)
        self._text_label.setText(display)
        # 设置 tooltip 显示完整文本
        if len(raw) > len(display) or "\n" in raw:
            self._text_label.setToolTip(raw)
        else:
            self._text_label.setToolTip("")

    def _build_ui(self):
        """初始化节点 UI（仅在 __init__ 中调用一次）"""
        ntype = self._node_data.get("node_type", "position")
        color = get_node_type_color(ntype)
        type_label_text = FRAMEWORK_NODE_TYPES.get(ntype, ("节点", "#888"))[0]
        self.setStyleSheet(f"#fwNode {{ border: 2px solid {color}; }}")
        self.setObjectName("fwNode")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(1)
        layout.setAlignment(Qt.AlignTop)  # 靠顶部排布
        lbl_type = QLabel(type_label_text)
        lbl_type.setObjectName("nodeTypeLabel")
        lbl_type.setFont(QFont("Microsoft YaHei", 7, QFont.Bold))
        lbl_type.setStyleSheet(f"color: {color};")
        layout.addWidget(lbl_type)
        lbl_text = QLabel(self._node_data.get("text", "双击编辑"))
        lbl_text.setObjectName("nodeContentLabel")
        lbl_text.setFont(QFont("Microsoft YaHei", 9))
        lbl_text.setStyleSheet("border: none; background: transparent;")
        lbl_text.setWordWrap(True)
        lbl_text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lbl_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(lbl_text)
        layout.addStretch()
        self._text_label = lbl_text
        self._text_edit = None  # 内联编辑控件，按需创建

    def _reset_style_internal(self):
        """仅重置节点样式表（不重建 layout，安全用于 _cancel_connect / _finish_connect）"""
        ntype = self._node_data.get("node_type", "position")
        color = get_node_type_color(ntype)
        self.setStyleSheet(f"#fwNode {{ border: 2px solid {color}; }}")

    def _apply_pos(self):
        self.move(self._node_data.get("x", 50), self._node_data.get("y", 50))

    def _is_in_handle(self, pos) -> bool:
        """判断鼠标是否在右下角 resize 手柄区域内"""
        return (self.width() - self.HANDLE_SIZE <= pos.x() <= self.width()
                and self.height() - self.HANDLE_SIZE <= pos.y() <= self.height())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            local_pos = event.pos()
            if self._is_in_handle(local_pos):
                # 右下角手柄 → resize 模式
                self._resizing = True
                self._resize_origin = event.globalPos()
                self._resize_orig_size = QSize(self.width(), self.height())
                self.setCursor(Qt.SizeFDiagCursor)
            else:
                # 拖拽移动模式
                self._drag_start = event.globalPos() - self.pos()
                self._drag_old_x = self.x()
                self._drag_old_y = self.y()
                self.setCursor(Qt.ClosedHandCursor)
            self._canvas._last_clicked_node = self
            self.raise_()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing and event.buttons() == Qt.LeftButton:
            # ── Resize 模式 ──
            delta = event.globalPos() - self._resize_origin
            nw = max(self.MIN_W, min(self.MAX_W, self._resize_orig_size.width() + delta.x()))
            nh = max(self.MIN_H, min(self.MAX_H, self._resize_orig_size.height() + delta.y()))
            self.resize(nw, nh)
            self._node_data["width"] = self.width()
            self._node_data["height"] = self.height()
            self._update_label_text()  # 宽度变化后重新截断
            self._canvas.update()
        elif self._drag_start is not None and event.buttons() == Qt.LeftButton:
            # ── 拖拽移动模式 ──
            new_pos = event.globalPos() - self._drag_start
            cw, ch = self._canvas.width(), self._canvas.height()
            nx = max(0, min(cw - self.width(), new_pos.x()))
            ny = max(0, min(ch - self.height(), new_pos.y()))
            dx = nx - self._drag_old_x
            dy = ny - self._drag_old_y
            self.move(nx, ny)
            self._node_data["x"] = self.x()
            self._node_data["y"] = self.y()
            self._drag_old_x = nx
            self._drag_old_y = ny
            self._canvas._move_descendants(self, dx, dy)
            self._canvas.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        was_resizing = self._resizing
        self._drag_start = None
        self._resizing = False
        self._resize_origin = None
        self._resize_orig_size = None
        self.setCursor(Qt.OpenHandCursor)
        if was_resizing:
            self._canvas._compute_and_store_offsets()
        self._canvas._auto_save()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._edit_text()
        event.accept()

    def _edit_text(self):
        """内联编辑节点文本（替换 QLabel 为 QTextEdit，支持多行输入）"""
        if self._text_edit:
            return  # 已在编辑中

        self._edit_old_text = self._node_data.get("text", "")
        text = self._edit_old_text
        ntype = self._node_data.get("node_type", "position")
        color = get_node_type_color(ntype)
        edit = QTextEdit(text, self)
        edit.setFont(QFont("Microsoft YaHei", 9))
        edit.setStyleSheet(
            "QTextEdit { border: 1px solid %s; selection-background-color: %s; }" % (color, color)
        )
        edit.setPlaceholderText("输入文本...")
        edit.setAcceptRichText(False)
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 替换 label 为 edit
        layout = self.layout()
        idx = layout.indexOf(self._text_label)
        if idx >= 0:
            self._text_label.hide()
            layout.insertWidget(idx, edit)
            edit.setFocus()

        # Ctrl+Enter 或 Escape 提交并保存
        def on_key(event):
            if event.key() == Qt.Key_Escape:
                self._commit_edit()
                return
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() == Qt.ControlModifier:
                self._commit_edit()
                return
            QTextEdit.keyPressEvent(edit, event)

        edit.keyPressEvent = on_key
        self._text_edit = edit

    def _commit_edit(self):
        """提交内联编辑，保存并恢复 QLabel"""
        edit = self._text_edit
        if not edit:
            return
        self._text_edit = None  # 提前置空，防止重复触发
        new_text = edit.toPlainText().strip()
        if not new_text:
            new_text = "双击编辑"
        old_text = getattr(self, '_edit_old_text', "")
        self._node_data["text"] = new_text
        self._update_label_text()
        edit.deleteLater()
        self._text_label.show()
        self._canvas._auto_save()
        # 推入撤销命令
        if new_text != old_text:
            cmd = FrameworkNodeTextCommand(self._canvas, self._node_data["id"], old_text, new_text)
            mgr = self._canvas._mgr
            if hasattr(mgr, '_undo_stack') and mgr._undo_stack:
                mgr._undo_stack.push(cmd)

    def _cancel_edit(self):
        """取消内联编辑，恢复 QLabel（不保存）"""
        edit = self._text_edit
        if not edit:
            return
        self._text_edit = None
        edit.deleteLater()
        self._text_label.show()

    def _on_context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("编辑文本").triggered.connect(self._edit_text)
        menu.addAction("删除节点").triggered.connect(
            lambda: self._canvas._delete_node(self)
        )
        child_menu = menu.addMenu("添加子节点")
        for ntype, (label, _) in FRAMEWORK_NODE_TYPES.items():
            act = child_menu.addAction(label)
            act.triggered.connect(lambda checked, t=ntype: self._canvas._add_child_node(self, t))
        menu.addSeparator()
        pending = self._canvas._pending_source
        if pending and pending is not self:
            menu.addAction("完成连接到此").triggered.connect(
                lambda: self._canvas._finish_connect(self)
            )
        elif not pending:
            menu.addAction("连接到...").triggered.connect(
                lambda: self._canvas._start_connect(self)
            )
        if pending:
            menu.addAction("取消连接").triggered.connect(
                lambda: self._canvas._cancel_connect()
            )
        menu.exec_(self.mapToGlobal(pos))


class FrameworkCanvas(QFrame):
    """框架画布 — 思维导图编辑区

    数据流：
      - 每个节点在 _data 中以 dict 存储，包含 id/node_type/text/x/y/children/offset_x/offset_y
      - _node_map 提供 O(1) 的 id→widget 查找
      - 保存时自动计算子节点相对于父节点的 offset
      - 加载时分两阶段：先创建控件，后触发重绘
    """

    # 标记是否正在绘制，防止重入 paintEvent 导致崩溃
    _painting_guard = False

    def __init__(self, mgr):
        """mgr: FrameworkManager 实例，用于保存数据和状态更新"""
        super().__init__()
        self._mgr = mgr
        self._nodes: list[FrameworkNodeWidget] = []
        self._node_map: dict[int, FrameworkNodeWidget] = {}  # id -> widget 快速索引
        self._data: list[dict] = []
        self._next_id: int = 1
        self._pending_source: FrameworkNodeWidget | None = None
        self._last_clicked_node: FrameworkNodeWidget | None = None
        self.setObjectName("frameworkCanvas")
        self.setMinimumSize(800, 600)

    # ---------- 数据存取 ----------

    def _auto_save(self):
        """触发管理器保存数据"""
        try:
            self._mgr.save_data()
        except RuntimeError:
            pass  # 管理器已销毁时静默忽略

    def mousePressEvent(self, event):
        """单击 canvas 空白区域时自动保存并提交当前编辑"""
        self._commit_all_edits()
        super().mousePressEvent(event)

    def _commit_all_edits(self):
        """遍历所有节点，提交正在编辑中的内容"""
        for w in self._nodes:
            try:
                if w._text_edit is not None:
                    w._commit_edit()
            except RuntimeError:
                pass

    def _build_node_map(self):
        """重建 id→widget 快速查找表"""
        self._node_map = {}
        for w in self._nodes:
            try:
                nid = w._node_data["id"]
                self._node_map[nid] = w
            except RuntimeError:
                pass

    def _compute_and_store_offsets(self):
        """计算每个子节点相对父节点的偏移量，写入 _data（保存前调用）"""
        for nd in self._data:
            parent_w = self._node_map.get(nd["id"])
            if not parent_w:
                continue
            px, py = parent_w.x(), parent_w.y()
            for child_id in nd.get("children", []):
                child_w = self._node_map.get(child_id)
                if child_w:
                    child_nd = child_w._node_data
                    child_nd["offset_x"] = child_w.x() - px
                    child_nd["offset_y"] = child_w.y() - py

    def _collect_descendant_ids(self, root_id: int, visited: set[int] | None = None) -> set[int]:
        """收集 root_id 的所有后代节点 ID（不含自身）"""
        if visited is None:
            visited = set()
        node = next((n for n in self._data if n["id"] == root_id), None)
        if node:
            for child_id in node.get("children", []):
                if child_id not in visited:
                    visited.add(child_id)
                    self._collect_descendant_ids(child_id, visited)
        return visited

    # ---------- 载入：两阶段 ----------

    def set_data(self, nodes_data: list, next_id: int = 1):
        """安全载入：清除旧控件→创建新控件→显示并重绘"""
        # ── 清除旧数据 ──
        for w in self._nodes:
            try:
                w.setParent(None)
            except RuntimeError:
                pass
            w.deleteLater()
        self._nodes.clear()
        self._node_map.clear()
        self._pending_source = None
        self._last_clicked_node = None

        self._data = list(nodes_data) if nodes_data else []
        self._next_id = next_id

        # ── 创建所有节点控件并显示 ──
        for nd in self._data:
            w = FrameworkNodeWidget(nd, self)
            self._nodes.append(w)
            self._node_map[nd["id"]] = w
            w.show()

        # ── 强制重绘 ──
        self.update()

        # 状态日志
        try:
            edge_count = sum(len(nd.get("children", [])) for nd in self._data)
            self._mgr.update_status(
                f"框架已载入：{len(self._nodes)} 个节点，{edge_count} 条连接线"
            )
        except RuntimeError:
            pass

    def _restore_state(self, data: list, next_id: int):
        """恢复框架状态（撤销/重做用）。"""
        for w in self._nodes:
            try:
                w.setParent(None)
                w.deleteLater()
            except RuntimeError:
                pass
        self._nodes.clear()
        self._node_map.clear()
        self._pending_source = None
        self._last_clicked_node = None
        self._data = list(data) if data else []
        self._next_id = next_id
        for nd in self._data:
            w = FrameworkNodeWidget(nd, self)
            self._nodes.append(w)
            self._node_map[nd["id"]] = w
            w.show()
        self._auto_save()
        self.update()

    # ---------- 节点 CRUD ----------

    def _add_root_node(self, node_type: str = "position"):
        old_data = copy.deepcopy(self._data)
        old_next_id = self._next_id
        nd = {
            "id": self._next_id, "node_type": node_type,
            "text": "", "x": 50, "y": 50,
            "width": 140, "height": 52,
            "children": [],
        }
        self._next_id += 1
        self._data.append(nd)
        w = FrameworkNodeWidget(nd, self)
        w.show()
        self._nodes.append(w)
        self._node_map[nd["id"]] = w
        self._auto_save()
        self.update()
        # 推入撤销命令
        cmd = FrameworkSnapshotCommand(
            self, old_data, old_next_id,
            copy.deepcopy(self._data), self._next_id,
            f"添加{node_type}节点"
        )
        if hasattr(self._mgr, '_undo_stack') and self._mgr._undo_stack:
            self._mgr._undo_stack.push(cmd)

    def _add_child_node(self, parent: FrameworkNodeWidget, node_type: str):
        old_data = copy.deepcopy(self._data)
        old_next_id = self._next_id
        px, py = parent.x(), parent.y()
        child_count = len(parent._node_data.get("children", []))
        nd = {
            "id": self._next_id, "node_type": node_type,
            "text": "",
            "x": px + 160, "y": py + child_count * 62,
            "width": 140, "height": 52,
            "children": [],
            "offset_x": 160,
            "offset_y": child_count * 62,
        }
        self._next_id += 1
        self._data.append(nd)
        parent._node_data.setdefault("children", []).append(nd["id"])
        w = FrameworkNodeWidget(nd, self)
        w.show()
        self._nodes.append(w)
        self._node_map[nd["id"]] = w
        self._auto_save()
        self.update()
        QTimer.singleShot(150, self.update)
        # 推入撤销命令
        cmd = FrameworkSnapshotCommand(
            self, old_data, old_next_id,
            copy.deepcopy(self._data), self._next_id,
            "添加子节点"
        )
        if hasattr(self._mgr, '_undo_stack') and self._mgr._undo_stack:
            self._mgr._undo_stack.push(cmd)

    def _delete_node(self, target: FrameworkNodeWidget):
        old_data = copy.deepcopy(self._data)
        def _collect_ids(nd_id, visited=None):
            if visited is None:
                visited = set()
            if nd_id in visited:
                return []
            visited.add(nd_id)
            ids = [nd_id]
            for n in self._data:
                if n["id"] == nd_id:
                    for c in n.get("children", []):
                        ids.extend(_collect_ids(c, visited))
                    break
            return ids
        del_ids = _collect_ids(target._node_data["id"])
        for n in self._data:
            if target._node_data["id"] in n.get("children", []):
                n["children"].remove(target._node_data["id"])
        self._data = [nd for nd in self._data if nd["id"] not in del_ids]
        for nid in del_ids:
            w = self._node_map.pop(nid, None)
            if w:
                try:
                    w.setParent(None)
                except RuntimeError:
                    pass
        self._nodes = [w for w in self._nodes if w._node_data["id"] not in del_ids]
        self._auto_save()
        QTimer.singleShot(150, self.update)
        # 推入撤销命令
        cmd = FrameworkSnapshotCommand(
            self, old_data, self._next_id,
            copy.deepcopy(self._data), self._next_id,
            "删除节点"
        )
        if hasattr(self._mgr, '_undo_stack') and self._mgr._undo_stack:
            self._mgr._undo_stack.push(cmd)

    # ---------- 自动调整布局 ----------

    def _calc_optimal_node_size(self, text: str) -> tuple:
        """根据文字内容计算最优节点大小，确保文字尽可能全部显示"""
        if not text:
            return 140, 52

        MAX_LINES = 5
        _font = QFont("Microsoft YaHei", 9)
        from PyQt5.QtGui import QFontMetrics
        _fm = QFontMetrics(_font)
        char_w = max(10, _fm.boundingRect("测").width())
        line_h = _fm.height() + 4
        MARGIN_W = max(24, int(char_w) + 14)
        TYPE_H = 24
        PAD_BOT = 12

        chars = len(text)
        min_cpl = max(10, -(-chars // MAX_LINES))  # ceil

        best_w, best_h = 100, 40
        best_score = float('inf')

        for cpl in range(min_cpl, min(min_cpl + 30, 42)):
            w = max(100, min(400, int(cpl * char_w) + MARGIN_W))
            lines = min(max(1, -(-chars // cpl)), MAX_LINES)
            h = max(40, min(200, TYPE_H + int(lines * line_h) + PAD_BOT))

            t_cpl = max(10, (w - 20) // 10)
            can_show_all = (t_cpl * MAX_LINES >= chars)

            if can_show_all:
                score = abs(w - h)
            else:
                score = 100000 + abs(w - h)

            if score < best_score:
                best_score = score
                best_w, best_h = w, h

        return best_w, best_h

    def auto_adjust_layout(self):
        """根据文字内容自动调整节点大小，并智能排列节点位置避免遮挡"""
        if not self._data:
            return

        # ── 1. 计算每个节点的最优大小 ──
        node_map = {nd["id"]: nd for nd in self._data}
        for nd in self._data:
            text = nd.get("text", "") or ""
            w, h = self._calc_optimal_node_size(text)
            nd["width"] = w
            nd["height"] = h

        # ── 2. 找根节点 ──
        child_ids = set()
        for nd in self._data:
            for cid in nd.get("children", []):
                child_ids.add(cid)
        roots = [nd["id"] for nd in self._data if nd["id"] not in child_ids]

        # ── 3. 迭代后序遍历计算子树高度 ──
        heights = {}
        stack = [(rid, False) for rid in roots]
        while stack:
            node_id, processed = stack.pop()
            if node_id not in node_map:
                heights[node_id] = 0
                continue
            if processed:
                nd = node_map[node_id]
                children = [c for c in nd.get("children", []) if c in node_map]
                if not children:
                    heights[node_id] = nd["height"]
                else:
                    ch_h = sum(heights.get(c, 0) for c in children)
                    gap = (len(children) - 1) * 24
                    heights[node_id] = max(nd["height"], ch_h + gap)
            else:
                if node_id in heights:
                    continue
                stack.append((node_id, True))
                nd = node_map[node_id]
                for cid in reversed(nd.get("children", [])):
                    if cid not in heights:
                        stack.append((cid, False))

        # ── 4. 迭代 BFS 布局 ──
        GAP_X = 70
        MARGIN = 40
        GAP_TREE = 50
        CHILD_GAP = 24

        current_y = MARGIN
        layout_queue = []
        for rid in roots:
            sub_h = heights.get(rid, 0)
            layout_queue.append((rid, MARGIN, current_y + sub_h / 2))
            current_y += sub_h + GAP_TREE

        visited = set()
        while layout_queue:
            node_id, x, y_center = layout_queue.pop(0)
            if node_id in visited or node_id not in node_map:
                continue
            visited.add(node_id)

            nd = node_map[node_id]
            nd["x"] = x
            nd["y"] = int(y_center - nd["height"] / 2)

            children = [c for c in nd.get("children", []) if c in node_map]
            if not children:
                continue

            child_x = x + nd["width"] + GAP_X
            total_h = sum(heights.get(c, 0) for c in children) + (len(children) - 1) * CHILD_GAP
            cur = y_center - total_h / 2
            for cid in children:
                sh = heights.get(cid, 0)
                layout_queue.append((cid, child_x, cur + sh / 2))
                cur += sh + CHILD_GAP

        # ── 5. 批量更新 widget ──
        for nd in self._data:
            widget = self._node_map.get(nd["id"])
            if widget:
                try:
                    widget.resize(nd["width"], nd["height"])
                    widget._update_label_text()
                    widget.move(nd["x"], nd["y"])
                except RuntimeError:
                    pass

        self._compute_and_store_offsets()
        self._auto_save()
        self.update()

    # ---------- 拖拽时同步移动所有后代 ----------

    def _move_descendants(self, node: FrameworkNodeWidget, dx: int, dy: int):
        """移动后代节点（纯视觉更新，不触发保存）"""
        descendant_ids = self._collect_descendant_ids(node._node_data["id"])
        if not descendant_ids:
            return
        for nid in descendant_ids:
            child_w = self._node_map.get(nid)
            if child_w:
                child_w.move(child_w.x() + dx, child_w.y() + dy)
                child_w._node_data["x"] = child_w.x()
                child_w._node_data["y"] = child_w.y()

    def _on_node_dragged(self, node: FrameworkNodeWidget, dx: int, dy: int):
        """节点被拖拽后，同步移动其所有后代节点（保持相对位置）"""
        self._move_descendants(node, dx, dy)
        self.update()
        self._compute_and_store_offsets()
        self._auto_save()

    def _start_connect(self, source: FrameworkNodeWidget):
        self._pending_source = source
        try:
            source.setStyleSheet("#fwNode { border: 3px solid #ffffff; }")
        except RuntimeError:
            self._pending_source = None
            return
        try:
            self._mgr.update_status("🔗 已选择源节点，请右键目标节点→「完成连接到此」完成连接")
        except RuntimeError:
            pass

    def _cancel_connect(self):
        """取消连接"""
        if self._pending_source:
            source = self._pending_source
            self._pending_source = None
            QTimer.singleShot(150, lambda: self._safe_reset_style(source))
        try:
            self._mgr.update_status("连接已取消")
        except RuntimeError:
            pass

    def _safe_reset_style(self, source: FrameworkNodeWidget):
        """在事件循环空闲时安全复位节点样式"""
        try:
            source._reset_style_internal()
        except RuntimeError:
            pass
        self.update()

    def _finish_connect(self, target: FrameworkNodeWidget):
        """完成连接"""
        if not self._pending_source or self._pending_source == target:
            self._cancel_connect()
            return

        sid = self._pending_source._node_data["id"]
        tid = target._node_data["id"]

        def _in_subtree(anc, desc, visited=None):
            if visited is None:
                visited = set()
            if anc in visited:
                return False
            visited.add(anc)
            for n in self._data:
                if n["id"] == anc:
                    if desc in n.get("children", []):
                        return True
                    for c in n.get("children", []):
                        if _in_subtree(c, desc, visited):
                            return True
            return False

        # 防止循环
        if sid == tid or _in_subtree(tid, sid) or _in_subtree(sid, tid):
            self._cancel_connect()
            try:
                self._mgr.update_status("❌ 不能连接到自己或后代节点")
            except RuntimeError:
                pass
            return

        # 数据修改
        self._pending_source._node_data.setdefault("children", [])
        if tid not in self._pending_source._node_data["children"]:
            self._pending_source._node_data["children"].append(tid)

        target_nd = target._node_data
        target_nd["offset_x"] = target.x() - self._pending_source.x()
        target_nd["offset_y"] = target.y() - self._pending_source.y()

        self._auto_save()
        try:
            self._mgr.update_status("✅ 连接完成")
        except RuntimeError:
            pass

        source = self._pending_source
        self._pending_source = None
        QTimer.singleShot(150, lambda: self._safe_reset_style(source))

    def paintEvent(self, event):
        super().paintEvent(event)
        if FrameworkCanvas._painting_guard:
            return
        FrameworkCanvas._painting_guard = True
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            for nd in self._data:
                src_w = self._node_map.get(nd["id"])
                if not src_w:
                    continue
                for child_id in nd.get("children", []):
                    child_w = self._node_map.get(child_id)
                    if not child_w:
                        continue

                    src_rect = src_w.geometry()
                    ch_rect = child_w.geometry()
                    line_color = QColor(get_node_type_color(nd.get("node_type", "argument")))

                    # 确定连接端点
                    src_cx = src_rect.center().x()
                    ch_cx = ch_rect.center().x()

                    if ch_cx >= src_cx:
                        start_pt = QPointF(src_rect.right() + 2, src_rect.center().y())
                        end_pt = QPointF(ch_rect.left() - 2, ch_rect.center().y())
                    else:
                        start_pt = QPointF(src_rect.left() - 2, src_rect.center().y())
                        end_pt = QPointF(ch_rect.right() + 2, ch_rect.center().y())

                    # 贝塞尔曲线控制点
                    cp_dist = max(abs(end_pt.x() - start_pt.x()) * 0.45, 50)
                    if ch_cx >= src_cx:
                        cp1 = QPointF(start_pt.x() + cp_dist, start_pt.y())
                        cp2 = QPointF(end_pt.x() - cp_dist, end_pt.y())
                    else:
                        cp1 = QPointF(start_pt.x() - cp_dist, start_pt.y())
                        cp2 = QPointF(end_pt.x() + cp_dist, end_pt.y())

                    # 发光阴影层
                    glow_pen = QPen(QColor(255, 255, 255, 40))
                    glow_pen.setWidth(6)
                    glow_pen.setCapStyle(Qt.RoundCap)
                    painter.setPen(glow_pen)
                    glow_path = QPainterPath()
                    glow_path.moveTo(start_pt)
                    glow_path.cubicTo(cp1, cp2, end_pt)
                    painter.drawPath(glow_path)

                    # 主连接线
                    main_pen = QPen(line_color)
                    main_pen.setWidth(2)
                    main_pen.setCapStyle(Qt.RoundCap)
                    painter.setPen(main_pen)
                    main_path = QPainterPath()
                    main_path.moveTo(start_pt)
                    main_path.cubicTo(cp1, cp2, end_pt)
                    painter.drawPath(main_path)

                    # 箭头
                    self._draw_arrowhead(painter, end_pt, cp2, line_color)

            # 绘制 resize 手柄
            for nd in self._data:
                w = self._node_map.get(nd["id"])
                if not w:
                    continue
                r = w.geometry()
                hx, hy = r.right() - FrameworkNodeWidget.HANDLE_SIZE, r.bottom() - FrameworkNodeWidget.HANDLE_SIZE
                color = QColor(get_node_type_color(nd.get("node_type", "argument")))
                color.setAlpha(100)
                painter.setPen(QPen(color, 1))
                painter.drawLine(hx, r.bottom() - 2, r.right() - 2, hy)
                painter.drawLine(hx + 8, r.bottom() - 2, r.right() - 2, hy + 8)
                painter.drawLine(hx + 14, r.bottom() - 2, r.right() - 2, hy + 14)

            painter.end()
        except Exception:
            pass
        finally:
            FrameworkCanvas._painting_guard = False

    @staticmethod
    def _draw_arrowhead(painter: QPainter, tip: QPointF, control: QPointF, color: QColor):
        """在连接线末端绘制三角形箭头"""
        arrow_size = 7
        dx = tip.x() - control.x()
        dy = tip.y() - control.y()
        length = (dx * dx + dy * dy) ** 0.5
        if length < 1:
            return
        dx /= length
        dy /= length

        px = -dy * arrow_size
        py = dx * arrow_size

        tip_pt = tip
        left_pt = QPointF(tip.x() - dx * arrow_size * 1.5 + px * 0.5,
                          tip.y() - dy * arrow_size * 1.5 + py * 0.5)
        right_pt = QPointF(tip.x() - dx * arrow_size * 1.5 - px * 0.5,
                           tip.y() - dy * arrow_size * 1.5 - py * 0.5)

        arrow_path = QPainterPath()
        arrow_path.moveTo(tip_pt)
        arrow_path.lineTo(left_pt)
        arrow_path.lineTo(right_pt)
        arrow_path.closeSubpath()

        painter.save()
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawPath(arrow_path)
        painter.restore()
