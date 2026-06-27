"""自定义按钮 — StarButton 通用组件，替代 Qt QPushButton。

特性: 6 种排布 / 5 种占比模式 / 自动尺寸 / 竖排 / 可勾选 / QSS 样式兼容。
"""

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
)
from PyQt5.QtCore import Qt, QSize, QRectF, pyqtSignal
from PyQt5.QtGui import (
    QFont, QFontMetrics, QIcon, QPixmap, QPainter, QColor, QPainterPath,
)
from components.theme_colors import tc


class StarButton(QWidget):
    """自定义按钮组件 — 替代 Qt QPushButton。"""

    clicked = pyqtSignal()
    pressed = pyqtSignal()
    released = pyqtSignal()
    toggled = pyqtSignal(bool)

    def __init__(
        self, text: str = "", parent=None,
        *,
        icon=None, icon_size: int = 24,
        layout_mode: str = "h_left",
        text_vertical: bool = False,
        text_align=Qt.AlignCenter,
        accent=None,
        ratio_mode: str = "sync",
        ratio_h: float = 0.8, ratio_v: float = 0.8,
        checkable: bool = False, checked: bool = False,
        cursor=None, auto_size: bool = True,
        text_color: str | None = None,
    ):
        super().__init__(parent)
        if cursor is None:
            cursor = Qt.PointingHandCursor

        self._text = text
        self._icon = None
        self._icon_pixmap = None
        self._icon_size = icon_size
        self._layout_mode = layout_mode
        self._text_vertical = text_vertical
        self._text_align = text_align
        self._accent = accent
        self._text_color = text_color
        self._ratio_mode = ratio_mode
        self._ratio_h = max(0.3, min(0.9, ratio_h))
        self._ratio_v = max(0.3, min(0.9, ratio_v))
        self._checkable = bool(checkable)
        self._checked = bool(checked)
        self._auto_size = bool(auto_size)
        self._hovered = False
        self._pressed = False
        self._enabled = True
        self._external_font = None
        self._user_fixed_size = None

        self.setCursor(cursor)

        # 构建 UI（必须在 setIcon 前调用，确保 _icon_label 已创建）
        self._build_layout()

        # 处理图标
        if icon is not None:
            self.setIcon(icon)

        # 非透明底色按钮 → 文字颜色
        if self._accent:
            color = self._text_color if self._text_color else "#ffffff"
            self._text_label.setStyleSheet(
                f"QLabel {{ background: transparent; border: none; color: {color}; }}"
            )

        # 初始选中
        if self._checkable and self._checked:
            self.update()

    # ══════════════════════════════════════════════════════════════════
    #  UI 构建
    # ══════════════════════════════════════════════════════════════════

    def _build_layout(self):
        """重建内部布局。"""
        old = self.layout()
        if old:
            QWidget().setLayout(old)

        is_v = self._layout_mode in ("v_top", "v_bottom")

        layout = QVBoxLayout(self) if is_v else QHBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 0)

        # 图标标签
        self._icon_label = QLabel()
        self._icon_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._icon_label.setObjectName("starBtnIcon")
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setStyleSheet("QLabel { background: transparent; border: none; }")

        # 文字标签
        self._text_label = QLabel()
        self._text_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._text_label.setObjectName("starBtnText")
        self._text_label.setStyleSheet("QLabel { background: transparent; border: none; }")
        self._text_label.setAlignment(self._text_align)
        self._sync_label_font()
        self._update_text_display()

        ac = Qt.AlignCenter
        if self._layout_mode == "text_only":
            layout.addWidget(self._text_label, 0, ac)
        elif self._layout_mode == "icon_only":
            layout.addWidget(self._icon_label, 0, ac)
        elif self._layout_mode in ("h_left", "v_top"):
            layout.addWidget(self._icon_label, 0, ac)
            layout.addWidget(self._text_label, 0, ac)
        else:  # h_right / v_bottom
            layout.addWidget(self._text_label, 0, ac)
            layout.addWidget(self._icon_label, 0, ac)

        self._update_icon_display()
        self._refresh_size()

    def _sync_label_font(self):
        font = self._external_font if self._external_font else QFont("Microsoft YaHei", 12)
        self._text_label.setFont(font)
        self._text_label.setWordWrap(self._text_vertical)

    def _update_text_display(self):
        if self._text_vertical:
            self._text_label.setText("\n".join(self._text))
        else:
            self._text_label.setText(self._text)

    def _update_icon_display(self):
        if self._icon_pixmap is not None:
            s = self._icon_size
            self._icon_label.setPixmap(
                self._icon_pixmap.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            self._icon_label.setFixedSize(s, s)
            self._icon_label.show()
        else:
            self._icon_label.clear()
            self._icon_label.hide()

    # ══════════════════════════════════════════════════════════════════
    #  尺寸计算
    # ══════════════════════════════════════════════════════════════════

    def _content_size(self) -> QSize:
        """计算文字+图标内容的最小尺寸（不含 padding）。"""
        fm = QFontMetrics(self._text_label.font())
        if self._text_vertical:
            tw = max((fm.horizontalAdvance(c) for c in self._text), default=0)
            th = fm.height() * max(len(self._text), 1)
        else:
            tw = fm.horizontalAdvance(self._text) if self._text else 0
            th = fm.height() if self._text else 0

        iw = self._icon_size if self._icon_pixmap else 0
        ih = self._icon_size if self._icon_pixmap else 0
        sp = 4 if (self._text and self._icon_pixmap) else 0

        if self._layout_mode == "text_only":
            return QSize(tw, th)
        if self._layout_mode == "icon_only":
            return QSize(iw, ih)
        if self._layout_mode in ("h_left", "h_right"):
            return QSize(tw + sp + iw, max(th, ih))
        return QSize(max(tw, iw), th + sp + ih)

    def _button_size(self) -> QSize:
        """根据内容 + 占比反推按钮的理想尺寸。"""
        c = self._content_size()
        w, h = c.width(), c.height()

        rh = self._ratio_h
        rv = self._ratio_v

        if self._ratio_mode in ("sync", "auto"):
            w = w / rh if rh > 0 else w
            h = h / rh if rh > 0 else h
        elif self._ratio_mode == "hv":
            w = w / rh if rh > 0 else w
            h = h / rv if rv > 0 else h
        elif self._ratio_mode == "h_only":
            w = w / rh if rh > 0 else w
        elif self._ratio_mode == "v_only":
            h = h / rv if rv > 0 else h

        return QSize(max(int(w), 20), max(int(h), 16))

    def _calc_margins(self, w: int, h: int):
        """根据当前实际尺寸计算 layout contentsMargins。"""
        rh = self._ratio_h
        rv = self._ratio_v
        mode = self._ratio_mode

        if mode in ("sync", "auto"):
            lr = int(w * (1 - rh) / 2)
            tb = int(h * (1 - rh) / 2)
            return (lr, tb, lr, tb)
        if mode == "hv":
            lr = int(w * (1 - rh) / 2)
            tb = int(h * (1 - rv) / 2)
            return (lr, tb, lr, tb)
        if mode == "h_only":
            lr = int(w * (1 - rh) / 2)
            return (lr, 0, lr, 0)
        if mode == "v_only":
            tb = int(h * (1 - rv) / 2)
            return (0, tb, 0, tb)
        return (0, 0, 0, 0)

    def _refresh_size(self):
        """重新计算尺寸并实际调整按钮高宽。

        策略(B1):
            - setMinimumSize(1,1) 不给布局硬性下限（允许布局压缩）
            - resize(s) 明确设尺寸（不在布局中时直接生效）
            - updateGeometry() 通知父布局重新布局
            - sizeHint() 返回理想尺寸，布局尽量尊重但不强制
        """
        if not self._auto_size or self._user_fixed_size:
            return
        s = self._button_size()
        self.setMinimumSize(1, 1)
        self.resize(s)
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        if self._auto_size and not self._user_fixed_size:
            return self._button_size()
        return super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        if self._auto_size and not self._user_fixed_size:
            return self._button_size()
        return super().minimumSizeHint()

    # ══════════════════════════════════════════════════════════════════
    #  绘制
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _is_dark_theme() -> bool:
        """检测当前主题是深色还是浅色。"""
        return QColor(tc("surface")).lightness() < 160

    def _hover_variant(self, color: QColor) -> QColor:
        """深色主题 → 加亮；浅色主题 → 加深。"""
        if self._is_dark_theme():
            return color.lighter(120)
        return color.darker(100)

    def _resolve_bg_color(self) -> QColor:
        """根据当前四态返回背景色（Normal 透明/ Accent 实色）。"""
        if not self._enabled:
            c = QColor(tc("overlay"))
            c.setAlpha(80)
            return c
        if self._accent:
            if self._hovered:
                return self._hover_variant(QColor(self._accent))
            return QColor(self._accent)
        if self._checkable and self._checked:
            try:
                checked_color = getattr(self, '_checked_accent', None) or tc("accent")
                c = QColor(checked_color)
                return self._hover_variant(c) if self._hovered else c
            except Exception:
                return QColor(tc("surface")).lighter(120)
        if self._hovered:
            return self._hover_variant(QColor(tc("surface")))
        return QColor(0, 0, 0, 0)  # Normal → 透明

    def paintEvent(self, event):
        """绘制深色主题扁平按钮背景（圆角 6px, 纯色, 四态颜色）。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        bg = self._resolve_bg_color()

        path = QPainterPath()
        path.addRoundedRect(rect, 6.0, 6.0)
        painter.fillPath(path, bg)

    def resizeEvent(self, event):
        """重新计算占比 margins。"""
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        layout = self.layout()
        if layout:
            layout.setContentsMargins(*self._calc_margins(w, h))

    # ══════════════════════════════════════════════════════════════════
    #  鼠标事件
    # ══════════════════════════════════════════════════════════════════

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._enabled:
            self._pressed = True
            self.pressed.emit()
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._enabled:
            wp = self._pressed
            self._pressed = False
            self.released.emit()
            if wp and self.rect().contains(event.pos()):
                if self._checkable:
                    self._checked = not self._checked
                    self.toggled.emit(self._checked)
                self.clicked.emit()
            self.update()
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        if self._enabled:
            self._hovered = True
            self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._pressed = False
        self.update()
        super().leaveEvent(event)

    # ══════════════════════════════════════════════════════════════════
    #  QPushButton 兼容 API
    # ══════════════════════════════════════════════════════════════════

    # ── 文字 ──

    def setText(self, text: str):
        self._text = text
        self._update_text_display()
        self._refresh_size()

    def text(self) -> str:
        return self._text

    # ── 图标 ──

    def setIcon(self, icon):
        """接受 QIcon、QPixmap、文件路径。"""
        if isinstance(icon, str):
            pix = QPixmap(icon)
            if not pix.isNull():
                self._icon = QIcon(icon)
                self._icon_pixmap = pix
        elif isinstance(icon, QIcon):
            self._icon = icon
            self._icon_pixmap = icon.pixmap(QSize(self._icon_size, self._icon_size))
        elif isinstance(icon, QPixmap):
            self._icon = QIcon(icon)
            self._icon_pixmap = icon
        if self._icon_pixmap is not None and not self._icon_pixmap.isNull():
            self._update_icon_display()
            self._refresh_size()

    def icon(self) -> QIcon:
        return self._icon

    def setIconSize(self, size):
        if isinstance(size, QSize):
            self._icon_size = min(size.width(), size.height())
        else:
            self._icon_size = int(size)
        self._update_icon_display()
        self._refresh_size()

    def iconSize(self) -> QSize:
        return QSize(self._icon_size, self._icon_size)

    # ── 可勾选 ──

    def setCheckable(self, checkable: bool):
        self._checkable = bool(checkable)

    def isCheckable(self) -> bool:
        return self._checkable

    def setChecked(self, checked: bool):
        checked = bool(checked)
        if self._checkable and self._checked != checked:
            self._checked = checked
            self.update()
            self.toggled.emit(self._checked)

    def isChecked(self) -> bool:
        return self._checked

    def toggle(self):
        if self._checkable:
            self.setChecked(not self._checked)

    # ── 启用/禁用 ──

    def setEnabled(self, enabled: bool):
        self._enabled = bool(enabled)
        self.setCursor(Qt.PointingHandCursor if self._enabled else Qt.ForbiddenCursor)
        self.update()
        super().setEnabled(self._enabled)

    def isEnabled(self) -> bool:
        return self._enabled

    # ── 字体 ──

    def setFont(self, font):
        self._external_font = QFont(font) if isinstance(font, QFont) else font
        self._sync_label_font()
        self._refresh_size()
        super().setFont(font)

    def font(self):
        return self._external_font or super().font()

    # ── 固定尺寸（覆盖以记录用户设置，关闭自动尺寸） ──

    def setFixedSize(self, *args):
        super().setFixedSize(*args)
        if len(args) == 1 and isinstance(args[0], QSize):
            self._user_fixed_size = args[0]
        elif len(args) >= 2:
            self._user_fixed_size = QSize(args[0], args[1])
        else:
            self._user_fixed_size = QSize(args[0].width(), args[0].height())

    def setFixedWidth(self, w):
        super().setFixedWidth(w)
        if self._user_fixed_size:
            self._user_fixed_size.setWidth(w)
        else:
            s = self.size()
            self._user_fixed_size = QSize(w, s.height())

    def setFixedHeight(self, h):
        super().setFixedHeight(h)
        if self._user_fixed_size:
            self._user_fixed_size.setHeight(h)
        else:
            s = self.size()
            self._user_fixed_size = QSize(s.width(), h)

    # ── 最小/最大尺寸 ──

    def setMinimumSize(self, *args):
        super().setMinimumSize(*args)

    def setMaximumSize(self, *args):
        super().setMaximumSize(*args)

    # ── QSS ──

    def setObjectName(self, name: str):
        super().setObjectName(name)
        self._icon_label.setObjectName(f"{name}Icon")
        self._text_label.setObjectName(f"{name}Text")

    # ── 属性读写 ──

    @property
    def layout_mode(self) -> str:
        return self._layout_mode

    @layout_mode.setter
    def layout_mode(self, mode: str):
        if mode != self._layout_mode:
            self._layout_mode = mode
            self._build_layout()

    @property
    def ratio_h(self) -> float:
        return self._ratio_h

    @ratio_h.setter
    def ratio_h(self, val: float):
        self._ratio_h = max(0.3, min(0.9, val))
        if self.layout() and self.isVisible():
            w, h = self.width(), self.height()
            self.layout().setContentsMargins(*self._calc_margins(w, h))
        self._refresh_size()

    @property
    def ratio_v(self) -> float:
        return self._ratio_v

    @ratio_v.setter
    def ratio_v(self, val: float):
        self._ratio_v = max(0.3, min(0.9, val))
        if self.layout() and self.isVisible():
            w, h = self.width(), self.height()
            self.layout().setContentsMargins(*self._calc_margins(w, h))
        self._refresh_size()

    @property
    def ratio_mode(self) -> str:
        return self._ratio_mode

    @ratio_mode.setter
    def ratio_mode(self, mode: str):
        if mode in ("sync", "hv", "h_only", "v_only", "auto"):
            self._ratio_mode = mode
            if self.layout() and self.isVisible():
                w, h = self.width(), self.height()
                self.layout().setContentsMargins(*self._calc_margins(w, h))
            self._refresh_size()

    @property
    def text_vertical(self) -> bool:
        return self._text_vertical

    @text_vertical.setter
    def text_vertical(self, val: bool):
        if val != self._text_vertical:
            self._text_vertical = bool(val)
            self._update_text_display()
            self._sync_label_font()
            self._refresh_size()

    @property
    def auto_size(self) -> bool:
        return self._auto_size

    @auto_size.setter
    def auto_size(self, val: bool):
        self._auto_size = bool(val)
        if self._auto_size:
            self._user_fixed_size = None
            self._refresh_size()
