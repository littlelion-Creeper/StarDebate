"""AILoadingBar：底部 AI 加载指示条 — 带旋转动画 + 文字提示"""
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QPixmap, QPainter, QPen
from components.theme_colors import tc, refresh


class AILoadingBar(QWidget):
    """底部 AI 加载指示条 — 带旋转动画 + 文字提示"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._ref_count = 0  # 引用计数，支持多个 AI 任务并行
        self.setFixedHeight(32)
        self.setVisible(False)
        self._build_ui()

    def _build_ui(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        self._spinner = QLabel()
        self._spinner.setFixedSize(18, 18)
        self._lbl = QLabel("AI运行中")
        self._lbl.setFont(QFont("Microsoft YaHei", 9))
        self._lbl.setStyleSheet(f"color: {tc("text")}; border: none; background: transparent;")
        lay.addStretch()
        lay.addWidget(self._spinner)
        lay.addSpacing(8)
        lay.addWidget(self._lbl)
        lay.addStretch()

    def _tick(self):
        self._angle = (self._angle + 30) % 360
        pixmap = QPixmap(18, 18)
        pixmap.fill(Qt.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(9, 9)
        p.rotate(self._angle)
        pen = QPen(QColor("#2E6DDE"), 2, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(-7, -7, 14, 14, 0, 270 * 16)
        p.end()
        self._spinner.setPixmap(pixmap)

    def show_loading(self, text="AI运行中"):
        """显示加载条（引用计数 +1）"""
        self._ref_count += 1
        self._lbl.setText(text)
        if not self._timer.isActive():
            self._timer.start(80)
        self.setVisible(True)

    def hide_loading(self):
        """隐藏加载条（引用计数 -1，归零时才真正隐藏）"""
        self._ref_count = max(0, self._ref_count - 1)
        if self._ref_count == 0:
            self._timer.stop()
            self.setVisible(False)
