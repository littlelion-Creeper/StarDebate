"""ShadowContainer — 窗口阴影容器组件

为无边框 (FramelessWindowHint) + 透明背景 (WA_TranslucentBackground)
窗口提供 QGraphicsDropShadowEffect 阴影和圆角效果。

- 内部 content widget 承载实际 UI
- QSS 控制 content 的背景色和 border-radius
- 最大化时自动禁用阴影和圆角
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
from PyQt5.QtGui import QColor


class ShadowContainer(QWidget):
    """包裹实际内容，提供阴影 + 圆角效果。

    Attributes:
        SHADOW_MARGIN: 阴影边距（像素），为阴影在透明背景上的渲染留出空间。
    """

    SHADOW_MARGIN = 15

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("shadowContainer")

        # ── 布局：边距为阴影留空间 ──────────────────────────────────
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(
            self.SHADOW_MARGIN, self.SHADOW_MARGIN,
            self.SHADOW_MARGIN, self.SHADOW_MARGIN,
        )
        self._layout.setSpacing(0)

        # ── 内容容器（实心背景 + 圆角，由 QSS 控制）────────────────
        self._content = QWidget()
        self._content.setObjectName("shadowContainerContent")
        self._layout.addWidget(self._content)

        # ── 阴影效果（施加在内容容器上，阴影渲染到边距区域）───────
        self._shadow = QGraphicsDropShadowEffect(self._content)
        self._shadow.setBlurRadius(30)
        self._shadow.setOffset(0, 6)
        self._shadow.setColor(QColor(0, 0, 0, 100))
        self._content.setGraphicsEffect(self._shadow)

    # ── 公开接口 ─────────────────────────────────────────────────────

    def get_content(self) -> QWidget:
        """返回内容容器，调用方应将所有 UI 构建在此 widget 上。"""
        return self._content

    def set_maximized(self, maximized: bool):
        """最大化/恢复时调整阴影和圆角。"""
        if maximized:
            # 最大化 → 禁用阴影、清除圆角、移除边距
            self._shadow.setEnabled(False)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._content.setStyleSheet("#shadowContainerContent { border-radius: 0px; }")
        else:
            # 恢复 → 启用阴影、恢复圆角、恢复边距
            self._shadow.setEnabled(True)
            self._layout.setContentsMargins(
                self.SHADOW_MARGIN, self.SHADOW_MARGIN,
                self.SHADOW_MARGIN, self.SHADOW_MARGIN,
            )
            self._content.setStyleSheet("")
