# -*- coding: utf-8 -*-
"""
StarDebate - 撤销/重做命令类
============================================================================
所有 QUndoCommand 子类，用于封装可撤销的操作。

命令类型：
  - TextEditCommand   文本编辑（带 500ms 定时器合并）
  - NodeAddCommand    添加节点（辩论框架/结构树）
  - NodeDeleteCommand 删除节点
  - NodeModifyCommand 修改节点文本
============================================================================
"""
from PyQt5.QtWidgets import QUndoCommand, QUndoStack
from PyQt5.QtCore import QObject, QTimer
from PyQt5.QtGui import QTextCursor


# ============================================================================
# TextEditCommand - 文本编辑命令（带定时器合并）
# ============================================================================

class TextEditCommand(QUndoCommand):
    """封装文本编辑操作，支持 undo/redo。

    保存编辑前的旧文本和编辑后的新文本，
    撤销时恢复旧文本，重做时设置新文本。
    """

    def __init__(self, editor, old_text, new_text, description="输入文字"):
        super().__init__(description)
        self._editor = editor
        self._old_text = old_text
        self._new_text = new_text

    def undo(self):
        """撤销：恢复旧文本。"""
        if self._editor is None:
            return
        self._editor.setPlainText(self._old_text)
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._editor.setTextCursor(cursor)

    def redo(self):
        """重做：设置新文本。"""
        if self._editor is None:
            return
        self._editor.setPlainText(self._new_text)
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._editor.setTextCursor(cursor)


class TextEditCommandMerger(QObject):
    """文本编辑命令合并器。

    监听 QPlainTextEdit 的 textChanged 信号，
    用 500ms 定时器合并连续输入，超时后向指定 QUndoStack 推入一条命令。

    支持 suspend() 上下文管理器：批量加载 / 程序化 setPlainText 时
    临时停止监听，避免：
    1) 500ms 后 push 一次 redo 触发 setPlainText 清空已应用的高亮
    2) 重新记录 _old_text 锚点污染后续撤销行为
    """

    def __init__(self, editor, undo_stack, parent=None):
        super().__init__(parent)
        self._editor = editor
        self._undo_stack = undo_stack
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._push_command)
        self._old_text = ""
        self._active = False
        self._suspend_count = 0

    def start(self):
        """开始监听文本变化。"""
        if self._active:
            return
        self._active = True
        self._old_text = self._editor.toPlainText()
        self._editor.textChanged.connect(self._on_text_changed)

    def stop(self):
        """停止监听文本变化，并推送最后一次未提交的更改。"""
        if not self._active:
            return
        self._active = False
        self._timer.stop()
        try:
            self._editor.textChanged.disconnect(self._on_text_changed)
        except Exception:
            pass
        current = self._editor.toPlainText()
        if current != self._old_text:
            cmd = TextEditCommand(self._editor, self._old_text, current)
            self._undo_stack.push(cmd)

    def suspend(self):
        """返回上下文管理器：进入时停止 timer + 阻止 textChanged 重启；退出时自动清理

        用法::

            with merger.suspend():
                edit.setPlainText(content)
                # 大量后续操作...
            # 退出后恢复正常监听
        """
        return _MergerSuspend(self)

    def _is_suspended(self) -> bool:
        return self._suspend_count > 0

    def _on_text_changed(self):
        """文本发生变化，重置 500ms 定时器。"""
        if not self._active or self._is_suspended():
            return
        self._timer.stop()
        self._timer.start(500)

    def _push_command(self):
        """定时器超时，推送命令到撤销栈。"""
        if not self._active or self._is_suspended():
            return
        new_text = self._editor.toPlainText()
        if new_text != self._old_text:
            cmd = TextEditCommand(self._editor, self._old_text, new_text)
            self._undo_stack.push(cmd)
            self._old_text = new_text

    def __del__(self):
        self.stop()


class _MergerSuspend:
    """TextEditCommandMerger 的 suspend 上下文管理器

    进入时：
    - suspend_count += 1
    - 停止可能已经启动的 timer
    退出时：
    - suspend_count -= 1
    - 重新同步 _old_text 为当前文本（避免程序化 setPlainText 造成的旧文本差异污染）
    """

    def __init__(self, merger: "TextEditCommandMerger"):
        self._merger = merger

    def __enter__(self):
        self._merger._suspend_count += 1
        self._merger._timer.stop()
        return self._merger

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._merger._suspend_count = max(0, self._merger._suspend_count - 1)
        # 重新同步锚点：suspend 期间的 setPlainText 不应进入 undo 栈
        if self._merger._active and self._merger._suspend_count == 0:
            self._merger._old_text = self._merger._editor.toPlainText()
        return False


# ============================================================================
# NodeAddCommand - 添加节点命令
# ============================================================================

class NodeAddCommand(QUndoCommand):
    """封装添加树节点操作。"""

    def __init__(self, tree_widget, node_data, description="添加节点"):
        super().__init__(description)
        self._tree_widget = tree_widget
        self._node_data = dict(node_data)

    def undo(self):
        """撤销：从树中移除该节点。"""
        if self._tree_widget is None:
            return
        target_id = self._node_data.get("id", "")
        if hasattr(self._tree_widget, "_find_node_by_id"):
            item = self._tree_widget._find_node_by_id(target_id)
            if item:
                parent = item.parent()
                if parent:
                    parent.removeChild(item)
                else:
                    idx = self._tree_widget.indexOfTopLevelItem(item)
                    if idx >= 0:
                        self._tree_widget.takeTopLevelItem(idx)

    def redo(self):
        """重做：重新添加节点。"""
        if self._tree_widget is None:
            return
        if hasattr(self._tree_widget, "_add_node_from_data"):
            self._tree_widget._add_node_from_data(self._node_data)
        elif hasattr(self._tree_widget, "add_node"):
            self._tree_widget.add_node(self._node_data)


# ============================================================================
# NodeDeleteCommand - 删除节点命令
# ============================================================================

class NodeDeleteCommand(QUndoCommand):
    """封装删除树节点操作。记录父节点和位置，以便撤销时恢复。"""

    def __init__(self, tree_widget, node_item, parent_item, index,
                 description="删除节点"):
        super().__init__(description)
        self._tree_widget = tree_widget
        self._node_data = self._extract_node_data(node_item)
        self._parent_is_none = (parent_item is None)
        self._parent_data = self._extract_node_data(parent_item) if parent_item else None
        self._index = index

    def undo(self):
        """撤销：在原始位置重新插入节点。"""
        if self._tree_widget is None:
            return
        if hasattr(self._tree_widget, "_add_node_from_data"):
            self._tree_widget._add_node_from_data(self._node_data)
        elif hasattr(self._tree_widget, "add_node"):
            self._tree_widget.add_node(self._node_data)

    def redo(self):
        """重做：再次删除该节点。"""
        if self._tree_widget is None:
            return
        target_id = self._node_data.get("id", "")
        if hasattr(self._tree_widget, "_find_node_by_id"):
            item = self._tree_widget._find_node_by_id(target_id)
            if item:
                parent = item.parent()
                if parent:
                    parent.removeChild(item)
                else:
                    idx = self._tree_widget.indexOfTopLevelItem(item)
                    if idx >= 0:
                        self._tree_widget.takeTopLevelItem(idx)

    @staticmethod
    def _extract_node_data(item):
        """从 QTreeWidgetItem 提取节点数据。"""
        if item is None:
            return {}
        data = item.data(0, 0x0100)
        if isinstance(data, dict):
            return dict(data)
        return {"text": item.text(0), "id": getattr(item, "_node_id", "")}


# ============================================================================
# NodeModifyCommand - 修改节点文本命令
# ============================================================================

class NodeModifyCommand(QUndoCommand):
    """封装修改节点文本操作。"""

    def __init__(self, tree_widget, node_id, old_text, new_text,
                 description="修改节点"):
        super().__init__(description)
        self._tree_widget = tree_widget
        self._node_id = node_id
        self._old_text = old_text
        self._new_text = new_text

    def undo(self):
        """撤销：恢复旧文本。"""
        self._set_node_text(self._node_id, self._old_text)

    def redo(self):
        """重做：设置新文本。"""
        self._set_node_text(self._node_id, self._new_text)

    def _set_node_text(self, node_id, text):
        """根据 node_id 查找节点并设置文本。"""
        if self._tree_widget is None:
            return
        if hasattr(self._tree_widget, "_find_node_by_id"):
            item = self._tree_widget._find_node_by_id(node_id)
            if item:
                item.setText(0, text)
                data = item.data(0, 0x0100)
                if isinstance(data, dict):
                    data["text"] = text
                    item.setData(0, 0x0100, data)
