"""
设置页通用工具函数

提供多个设置页共用的辅助函数，消除约 page 与 api_config 等页面间的重复代码。
"""

import logging

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QBoxLayout, QFrame, QLabel, QWidget

from siui.components.widgets import SiLabel
from siui.core import SiColor
from siui.components.container import SiPanelCard
from siui.gui.font import SiFont

from components.theme_colors import tc

_logger = logging.getLogger("StarDebate.settings.page_utils")


def safe_set_style_data(target, attr, color_str: str):
    """安全设置 SiUI style_data 属性，失败时静默跳过。"""
    try:
        setattr(target.style_data, attr, QColor(color_str))
    except Exception:
        _logger.warning("无法设置 style_data.%s", attr, exc_info=True)


def safe_create_card(page) -> QWidget | None:
    """尝试创建 SiPanelCard，失败时返回 None。"""
    try:
        card = SiPanelCard(page, direction=QBoxLayout.TopToBottom)
        safe_set_style_data(card, "background_fore_color", tc("surface"))
        safe_set_style_data(card, "background_back_color", tc("surface"))
        cl = card.layout()
        if cl is not None and hasattr(cl, "setSpacing"):
            cl.setSpacing(0)
        if hasattr(card, "muteStretchWidget"):
            card.muteStretchWidget()
        card.setContentsMargins(20, 18, 20, 18)
        return card
    except Exception:
        _logger.exception("创建 SiPanelCard 失败")
        return None


def add_silabel(parent, text: str, color_key=SiColor.TEXT_B,
                word_wrap: bool = False, min_height: int | None = None,
                font_size: int | None = None) -> SiLabel | None:
    """添加带 fallback 的 SiLabel，支持自定义字号。"""
    try:
        lbl = SiLabel(parent)
        lbl.setText(text)
        lbl.setTextColor(lbl.getColor(color_key))
        lbl.setStyleSheet("background: transparent;")
        if font_size is not None:
            lbl.setFont(SiFont.getFont(size=font_size))
        if word_wrap:
            lbl.setWordWrap(True)
        if min_height is not None:
            lbl.setMinimumHeight(min_height)
        # SiPanelCard.addWidget() 或父容器的 layout().addWidget()
        if hasattr(parent, "addWidget"):
            parent.addWidget(lbl)
        elif parent.layout() is not None:
            parent.layout().addWidget(lbl)
        return lbl
    except Exception:
        _logger.warning("SiLabel(%s) 创建失败", text[:20], exc_info=True)
        return None


def make_transparent_row(parent) -> QWidget:
    """创建透明背景的行容器。"""
    row = QWidget(parent)
    row.setAttribute(Qt.WA_StyledBackground, True)
    row.setStyleSheet("background: transparent;")
    return row


def make_sep() -> QFrame:
    """创建水平分隔线。"""
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setStyleSheet(f"color: {tc('border')};")
    sep.setFixedHeight(2)
    return sep
