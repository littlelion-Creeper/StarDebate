"""一辩稿编辑器组件：SpeechEditor（行号+当前行高亮+等宽字体）、
_LineNumberArea（行号区域）、KeywordCard（关键词卡片）、AddKeywordButton（添加按钮）"""

import os

from PyQt5.QtWidgets import (
    QWidget, QPlainTextEdit, QLabel, QHBoxLayout, QFrame,
    QToolTip, QTextEdit,
)
from components.star_button import StarButton
from PyQt5.QtCore import Qt, QRect, QEvent, QSize, pyqtSignal, QTimer, QPoint
from PyQt5.QtGui import (
    QFont, QFontInfo, QColor, QPainter, QTextCharFormat,
    QTextFormat, QTextCursor, QPixmap, QFontMetrics,
)
from PyQt5.QtSvg import QSvgRenderer
from components.theme_colors import tc
from components.svg_renderer import SvgRenderer

# ── 图标缓存 ──
_ICON_PIXMAP_CACHE: dict[str, QPixmap] = {}
_ICON_SIZE = 14  # 图标像素大小


def _load_icon_svg(svg_path: str) -> QPixmap | None:
    """加载 SVG 文件并渲染为 QPixmap（带缓存，主题色跟随）"""
    if svg_path in _ICON_PIXMAP_CACHE:
        return _ICON_PIXMAP_CACHE[svg_path]
    if not os.path.isfile(svg_path):
        return None
    try:
        pixmap = SvgRenderer.render(svg_path, _ICON_SIZE, mode="mono",
                                    color=tc("accent"))
        if pixmap and not pixmap.isNull():
            _ICON_PIXMAP_CACHE[svg_path] = pixmap
            return pixmap
    except Exception:
        pass
    # 兜底
    try:
        renderer = QSvgRenderer(svg_path)
        pixmap = QPixmap(_ICON_SIZE, _ICON_SIZE)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        renderer.render(painter)
        painter.end()
        _ICON_PIXMAP_CACHE[svg_path] = pixmap
        return pixmap
    except Exception:
        return None


def _wrap_tooltip_text(text: str, chars_per_line: int = 20) -> str:
    """将纯文本按固定字数强制换行，保留已有的 \\n 换行"""
    if not text:
        return text
    if text.strip().startswith("<html") or text.strip().startswith("<!DOCTYPE"):
        return text
    lines = text.split("\n")
    wrapped_lines = []
    for line in lines:
        if len(line) <= chars_per_line:
            wrapped_lines.append(line)
        else:
            for i in range(0, len(line), chars_per_line):
                wrapped_lines.append(line[i:i + chars_per_line])
    return "\n".join(wrapped_lines)


class _LineNumberArea(QWidget):
    """行号区域"""

    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return QSize(self._editor._line_number_area_width(), 0)

    def paintEvent(self, event):
        self._editor._line_number_area_paint_event(event)


class SpeechEditor(QPlainTextEdit):
    """IDE 风格的一辩稿编辑器：行号、当前行高亮、等宽字体、索引图标绘制+自定义悬浮"""

    # ── 信号 ────────────────────────────────────────────
    hover_requested = pyqtSignal(str, int, int)   # term, start_pos, end_pos
    hide_hover_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._line_number_area = _LineNumberArea(self)
        self._suppress_line_highlight = False

        # ── 索引词缓存 ──
        # [(term, start_pos, end_pos, has_sources), ...] 每次 setPlainText 后重建
        self._bound_terms_cache: list[tuple[str, int, int, bool]] = []

        # ── 图标 pixmap ──
        from components.res_path import get_resource_root
        self._icon_pixmap: QPixmap | None = _load_icon_svg(
            os.path.join(get_resource_root(), "icon", "index", "has_material.svg")
        )

        # ── 鼠标悬停 ──
        self._hover_timer: QTimer | None = None
        self._hover_term_pos: tuple[str, int, int] | None = None  # (term, start, end)
        self._last_mouse_viewport_pos: QPoint | None = None
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)

        self._update_line_number_area_width(0)
        self._highlight_current_line()

        # IDE 等宽字体
        font = QFont("Cascadia Code", 11)
        resolved = QFontInfo(font).family()
        if resolved != "Cascadia Code":
            font = QFont("Consolas", 11)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)

    # ── 索引词缓存接口（由 Manager 调用）──

    def set_bound_terms_cache(self, terms: list[tuple[str, int, int, bool]]):
        """设置索引词位置缓存

        Args:
            terms: [(term, start_pos, end_pos, has_sources), ...]
        """
        self._bound_terms_cache = terms
        # 触发重绘
        self.viewport().update()

    # ── 行号区域 ──

    def _line_number_area_width(self):
        digits = len(str(max(1, self.blockCount())))
        space = 8 + self.fontMetrics().horizontalAdvance('9') * (digits + 1)
        return max(space, 32)

    def _update_line_number_area_width(self, _=None):
        self.setViewportMargins(self._line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy):
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(
                0, rect.y(), self._line_number_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self._line_number_area_width(), cr.height())
        )

    def _line_number_area_paint_event(self, event):
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor(tc("surface")))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        offset = self.contentOffset()
        top = round(self.blockBoundingGeometry(block).translated(offset).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        current_block = self.textCursor().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                if block_number == current_block:
                    painter.setPen(QColor(tc("accent_yellow")))
                else:
                    painter.setPen(QColor(tc("pressed")))
                painter.setFont(self.font())
                painter.drawText(
                    0, top, self._line_number_area.width() - 6,
                    self.fontMetrics().height(),
                    Qt.AlignRight, number
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def _highlight_current_line(self):
        if self._suppress_line_highlight:
            return
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor(tc("base")))
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)

    # ── 事件处理 ──

    def event(self, event):
        """拦截 ToolTip 事件，由自定义 hover 替代"""
        if event.type() == QEvent.ToolTip:
            # 由 viewportEvent 的 mouse move + timer 处理
            return True
        return super().event(event)

    def viewportEvent(self, event):
        """拦截 Viewport 鼠标事件实现自定义 hover"""
        if event.type() == QEvent.MouseMove:
            self._last_mouse_viewport_pos = event.pos()
            self._on_mouse_move(event.pos(), event.globalPos())
        elif event.type() == QEvent.Leave:
            self._on_mouse_leave()
        return super().viewportEvent(event)

    def paintEvent(self, event):
        """重写 paintEvent：先绘制文本，再在索引词前绘制图标"""
        # 1. 先绘制文本
        super().paintEvent(event)

        # 2. 在可见的已绑定词前绘制图标
        if not self._bound_terms_cache or not self._icon_pixmap:
            return

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setOpacity(0.55)  # 透明度

        icon_w = _ICON_SIZE
        icon_h = _ICON_SIZE
        icon_offset = 2  # 词与图标之间的间距

        text = self.toPlainText()

        for term, start_pos, end_pos, has_sources in self._bound_terms_cache:
            if not has_sources:
                continue  # 没有来源的不画图标
            if start_pos < 0 or start_pos > len(text):
                continue

            # 用 cursor 获取词开始位置在 viewport 中的坐标
            cursor = QTextCursor(self.document())
            cursor.setPosition(start_pos)
            rect = self.cursorRect(cursor)

            # 只绘制可见区域
            if rect.bottom() < event.rect().top() or rect.top() > event.rect().bottom():
                continue
            if rect.right() < event.rect().left():
                continue

            # 图标位置：在词的左前方
            icon_x = rect.left() - icon_w - icon_offset
            # 垂直居中
            icon_y = rect.top() + (rect.height() - icon_h) // 2

            painter.drawPixmap(icon_x, icon_y, self._icon_pixmap)

        painter.end()

    # ── 自定义 hover 逻辑 ──

    def _on_mouse_move(self, viewport_pos: QPoint, global_pos: QPoint):
        """鼠标在 viewport 上移动时检测是否在索引词上"""
        cursor = self.cursorForPosition(viewport_pos)
        pos_in_text = cursor.position()

        term, start, end, has_sources = self._find_term_at_pos(pos_in_text)
        if term and has_sources:
            if self._hover_term_pos != (term, start, end):
                # 新词 → 取消旧定时器，启动新的（位置由 Manager 端根据文本位置计算）
                self._cancel_hover_timer()
                self._hover_term_pos = (term, start, end)
                self._hover_timer = QTimer(self)
                self._hover_timer.setSingleShot(True)
                self._hover_timer.timeout.connect(
                    lambda t=term, s=start, e=end:
                    self.hover_requested.emit(t, s, e)
                )
                self._hover_timer.start(300)
        else:
            # 不在索引词上
            if self._hover_term_pos is not None:
                self._cancel_hover_timer()
                self._hover_term_pos = None
                self.hide_hover_requested.emit()

    def _on_mouse_leave(self):
        """鼠标离开 viewport → 取消 hover"""
        self._cancel_hover_timer()
        self._hover_term_pos = None
        self.hide_hover_requested.emit()

    def _cancel_hover_timer(self):
        if self._hover_timer:
            self._hover_timer.stop()
            self._hover_timer = None

    def _find_term_at_pos(self, pos: int) -> tuple:
        """查找位置 pos 是否在某索引词范围内

        Returns:
            (term, start, end, has_sources) 或 ("", -1, -1, False)
        """
        for term, start, end, has_sources in self._bound_terms_cache:
            if start <= pos <= end:
                return (term, start, end, has_sources)
        return ("", -1, -1, False)

    # ── 批量更新 ──

    def _begin_batch_update(self):
        """暂停行号高亮更新（在批量文本操作前调用）"""
        self._suppress_line_highlight = True

    def _end_batch_update(self):
        """恢复行号高亮更新"""
        self._suppress_line_highlight = False
        self._highlight_current_line()


class KeywordCard(QFrame):
    """单个关键词卡片，支持编辑和删除"""

    clicked = pyqtSignal()
    edit_requested = pyqtSignal()
    delete_requested = pyqtSignal()

    def __init__(self, word: str, note: str = "", side: str = "pro", parent=None):
        super().__init__(parent)
        self.setObjectName("keywordCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(
            _wrap_tooltip_text(f"点击编辑\n{note}") if note else "点击编辑"
        )
        self._word = word
        self._side = side

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 6, 4)
        layout.setSpacing(4)

        lbl = QLabel(word)
        lbl.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        accent = "#a6e3a1" if side == "pro" else "#f38ba8"
        lbl.setStyleSheet(f"color: {accent}; background: transparent;")
        layout.addWidget(lbl)

        layout.addSpacing(6)

        btn_edit = StarButton("✎", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_edit.setObjectName("cardBtn")
        btn_edit.setCursor(Qt.PointingHandCursor)
        btn_edit.setToolTip("编辑关键词")
        btn_edit.clicked.connect(self.edit_requested.emit)
        layout.addWidget(btn_edit)

        btn_del = StarButton("✕", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_del.setObjectName("cardBtn")
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.setToolTip("删除关键词")
        btn_del.clicked.connect(self.delete_requested.emit)
        layout.addWidget(btn_del)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class AddKeywordButton(StarButton):
    """流式布局中新增关键词的入口按钮"""

    def __init__(self, parent=None):
        super().__init__("+ 添加关键词", parent)
        self.setObjectName("addKeywordBtn")
        self.setCursor(Qt.PointingHandCursor)
