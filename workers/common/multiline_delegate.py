"""MultilineDelegate：通用多行文本编辑代理（支持多行表格单元格）"""
from PyQt5.QtWidgets import (
    QStyle, QStyledItemDelegate, QStyleOptionViewItem,
    QAbstractItemDelegate, QTextEdit,
)
from PyQt5.QtCore import Qt, QSize, QRect, QEvent
from PyQt5.QtGui import QFont, QColor


class MultilineDelegate(QStyledItemDelegate):
    """自定义代理：支持多行文本编辑和智能行高"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._default_row_height = 48
        self._min_row_height = 36

    def createEditor(self, parent, option, index):
        """创建多行文本编辑器"""
        editor = QTextEdit(parent)
        editor.setAcceptRichText(False)
        editor.setFont(QFont("Microsoft YaHei", 11))
        editor.setStyleSheet(
            "QTextEdit { background-color: #1e1e2e; color: #cdd6f4; "
            "border: 2px solid #89b4fa; border-radius: 4px; padding: 4px 6px; "
            "selection-background-color: #45475a; }"
        )
        # Ctrl+Enter 提交编辑，Tab/Shift+Tab 导航到相邻单元格
        editor.installEventFilter(self)
        return editor

    def eventFilter(self, obj, event):
        """事件过滤：QTextEdit 编辑器中 Tab 导航单元格，Ctrl+Enter 提交"""
        if event.type() == QEvent.KeyPress and isinstance(obj, QTextEdit):
            if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
                # Ctrl+Enter：提交编辑器内容
                self.commitData.emit(obj)
                self.closeEditor.emit(obj)
                return True
            if event.key() == Qt.Key_Tab and not event.modifiers():
                # Tab：提交并移动到下一列（或下一行第一列）
                self.commitData.emit(obj)
                self.closeEditor.emit(obj, QAbstractItemDelegate.EditNextItem)
                return True
            if event.key() == Qt.Key_Backtab:
                # Shift+Tab：提交并移动到上一列
                self.commitData.emit(obj)
                self.closeEditor.emit(obj, QAbstractItemDelegate.EditPreviousItem)
                return True
        return super().eventFilter(obj, event)

    def setEditorData(self, editor, index):
        """从模型加载数据到编辑器"""
        text = index.model().data(index, Qt.EditRole)
        if text is None:
            text = ""
        editor.setPlainText(str(text))

    def setModelData(self, editor, model, index):
        """将编辑器内容保存回模型"""
        text = editor.toPlainText().strip()
        model.setData(index, text, Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        """调整编辑器位置和大小"""
        editor.setGeometry(option.rect)

    def paint(self, painter, option, index):
        """绘制多行文本"""
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#45475a"))

        text = index.model().data(index, Qt.DisplayRole)
        if text is None:
            text = ""
        text = str(text)

        painter.save()
        painter.setFont(QFont("Microsoft YaHei", 11))
        painter.setPen(QColor("#cdd6f4"))

        # 带内边距的绘制区域
        margin = 6
        rect = option.rect.adjusted(margin, margin, -margin, -margin)

        # 多行文本绘制（支持 \n 和自动换行）
        painter.drawText(rect, Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap, text)
        painter.restore()

    def sizeHint(self, option, index):
        """计算单元格所需高度"""
        text = index.model().data(index, Qt.DisplayRole)
        if text is None:
            text = ""
        text = str(text)
        if not text:
            return QSize(100, self._min_row_height)

        # 使用 QFontMetrics 计算文本实际需要的高度
        fm = QFontMetrics(QFont("Microsoft YaHei", 11))
        margin = 6 * 2  # 上下各 6px 内边距

        col_width = option.rect.width()
        if col_width <= 0:
            col_width = 200

        text_width = col_width - margin
        if text_width < 40:
            text_width = 40

        # 计算文本需要的矩形大小
        bounding = fm.boundingRect(
            QRect(0, 0, text_width, 10000),
            Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap,
            text
        )
        h = bounding.height() + margin + 6  # 额外 6px 余量
        return QSize(100, max(h, self._min_row_height))

    def get_row_height(self, text: str, col_width: int) -> int:
        """供外部使用的行高计算"""
        if not text:
            return self._min_row_height
        fm = QFontMetrics(QFont("Microsoft YaHei", 11))
        margin = 6 * 2
        text_width = col_width - margin
        if text_width < 40:
            text_width = 40
        bounding = fm.boundingRect(
            QRect(0, 0, text_width, 10000),
            Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap,
            text
        )
        return max(bounding.height() + margin + 6, self._min_row_height)
