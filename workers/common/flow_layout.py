"""FlowLayout：自适应换行布局"""
from PyQt5.QtWidgets import QLayout, QLayoutItem
from PyQt5.QtCore import Qt, QSize, QRect


class FlowLayout(QLayout):
    """自适应换行布局，根据容器宽度自动排列子控件。
    使用 contentsMargins() 控制外边距，spacing() 控制间距。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._item_list: list = []
        self.setSpacing(8)

    def __del__(self):
        while self._item_list:
            item = self._item_list.pop()
            w = item.widget()
            if w:
                self.removeWidget(w)

    def addItem(self, item: QLayoutItem):
        self._item_list.append(item)

    def count(self) -> int:
        return len(self._item_list)

    def itemAt(self, index: int):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        margins = self.contentsMargins()
        s = QSize()
        for item in self._item_list:
            s = s.expandedTo(item.minimumSize())
        return QSize(s.width() + margins.left() + margins.right(),
                     s.height() + margins.top() + margins.bottom())

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        """实际布局计算，返回所需高度"""
        margins = self.contentsMargins()
        spacing = self.spacing()
        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        line_height = 0
        max_width = rect.width() - margins.left() - margins.right()

        for item in self._item_list:
            widget = item.widget()
            if not widget or widget.isHidden():
                continue

            w = widget.sizeHint().width()
            h = widget.sizeHint().height()

            # 换行
            if x > rect.x() + margins.left() and x + w > rect.x() + max_width + margins.left():
                x = rect.x() + margins.left()
                y += line_height + spacing
                line_height = 0

            if not test_only:
                widget.setGeometry(QRect(x, y, w, h))

            x += w + spacing
            line_height = max(line_height, h)

        return y + line_height + margins.bottom() - rect.y()
