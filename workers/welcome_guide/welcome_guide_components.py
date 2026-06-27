"""WelcomeGuideComponents — 引导页可复用的卡片和 SVG 渲染组件。"""

import os
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal, QRectF
from PyQt5.QtGui import QPainter, QColor, QFont, QPixmap
from PyQt5.QtSvg import QSvgRenderer
from components.theme_colors import tc
from components.res_path import get_resource_root


def render_svg_themed(svg_path, size=28, color_key="accent_blue"):
    """渲染 SVG 到 QPixmap，主题色着色。"""
    from components.theme_colors import tc as get_tc
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    r = QSvgRenderer(svg_path)
    if not r.isValid():
        return pix
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    if p.isActive():
        r.render(p, QRectF(0, 0, size, size))
    p.end()
    tinted = QPixmap(size, size)
    tinted.fill(Qt.transparent)
    p = QPainter(tinted)
    p.setRenderHint(QPainter.Antialiasing)
    if p.isActive():
        p.drawPixmap(0, 0, pix)
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(0, 0, size, size, QColor(get_tc(color_key, "#89b4fa")))
    p.end()
    return tinted


class ClickableCard(QFrame):
    """可点击的功能卡片。"""
    clicked = pyqtSignal(str)

    def __init__(self, svg_name, title, desc, action):
        super().__init__()
        self._action = action
        self.setObjectName("welcomeCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(194, 92)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(3)
        lay.setAlignment(Qt.AlignCenter)
        # SVG 图标
        svg_path = os.path.join(get_resource_root(), "icon", "common", svg_name)
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(28, 28)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("background:transparent;")
        if os.path.isfile(svg_path):
            icon_lbl.setPixmap(render_svg_themed(svg_path, 26))
        else:
            icon_lbl.setText("?")
        lay.addWidget(icon_lbl, 0, Qt.AlignCenter)
        # 标题
        t = QLabel(title)
        t.setObjectName("welcomeCardTitle")
        t.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet(f"color:{tc('text')};background:transparent;")
        lay.addWidget(t, 0, Qt.AlignCenter)
        # 描述
        d = QLabel(desc)
        d.setObjectName("welcomeCardDesc")
        d.setFont(QFont("Microsoft YaHei", 8))
        d.setAlignment(Qt.AlignCenter)
        d.setStyleSheet(f"color:{tc('muted')};background:transparent;")
        lay.addWidget(d, 0, Qt.AlignCenter)

    def mousePressEvent(self, event):
        self.clicked.emit(self._action)
        super().mousePressEvent(event)

