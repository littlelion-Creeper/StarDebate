"""HoverCard — 自定义悬浮卡片（类似 IDE 的文档悬浮提示）

显示一辩稿中已绑定索引词的来源信息：
- 手动补充的解释
- 关联的资料摘要（可点击打开）
- 关联的便签内容（可点击打开）

使用方式：由 SpeechEditorManager 创建并管理显示/隐藏。
"""

import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QPoint, QRect
from PyQt5.QtGui import QFont, QColor, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer

from components.theme_colors import tc
from components.star_button import StarButton
from components.svg_renderer import SvgRenderer


MAX_CARD_WIDTH = 400
MAX_CARD_HEIGHT = 900
SECTION_MAX_HEIGHT = 300
HIDE_DELAY_MS = 500
_ICON_SIZE = 14

# ── SVG 图标缓存 ──
from components.res_path import get_resource_root
_ICON_DIR = os.path.join(get_resource_root(), "icon", "index")
_ICON_CACHE: dict[str, QPixmap] = {}


def _load_svg_icon(name: str) -> QPixmap | None:
    """加载 SVG 图标并渲染为 QPixmap（带缓存，主题色跟随）"""
    if name in _ICON_CACHE:
        return _ICON_CACHE[name]
    path = os.path.join(_ICON_DIR, name)
    if not os.path.isfile(path):
        return None
    try:
        pixmap = SvgRenderer.render(path, _ICON_SIZE, mode="mono",
                                    color=tc("accent_blue"))
        if pixmap and not pixmap.isNull():
            _ICON_CACHE[name] = pixmap
            return pixmap
    except Exception:
        pass
    # 兜底
    try:
        renderer = QSvgRenderer(path)
        pixmap = QPixmap(_ICON_SIZE, _ICON_SIZE)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        renderer.render(painter)
        painter.end()
        _ICON_CACHE[name] = pixmap
        return pixmap
    except Exception:
        return None


def _icon_label(name: str) -> QLabel:
    """创建固定大小的 SVG 图标签"""
    pixmap = _load_svg_icon(name)
    lbl = QLabel()
    if pixmap:
        lbl.setPixmap(pixmap)
    lbl.setFixedSize(_ICON_SIZE + 4, _ICON_SIZE + 4)
    lbl.setStyleSheet("border: none; background: transparent;")
    return lbl


def _short_text(text: str, max_len: int = 80) -> str:
    """截取文本前 max_len 字，超出加 ..."""
    if not text:
        return ""
    text_flat = text.replace("\n", " ").replace("\r", " ").strip()
    if len(text_flat) <= max_len:
        return text_flat
    return text_flat[:max_len] + "..."


def _wrap_tooltip_text(text: str, chars_per_line: int = 20) -> str:
    """将纯文本按固定字数强制换行，保留已有的 \n 换行"""
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


class _SectionTitle(QLabel):
    """带色条的 Section 标题"""

    def __init__(self, text: str, color: str, parent=None):
        super().__init__(text, parent)
        self._accent_color = color
        self.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        self.setStyleSheet(f"""
            color: {color};
            padding: 4px 0 2px 0;
            border: none;
            background: transparent;
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self._accent_color))
        painter.drawRoundedRect(0, 4, 3, self.height() - 8, 1, 1)
        painter.end()


class _SourceItem(QFrame):
    """单个来源条目（资料 or 便签）"""

    open_requested = pyqtSignal(dict)

    def __init__(self, source: dict, parent=None):
        """source: {type, title, excerpt, ...}"""
        super().__init__(parent)
        self._source = source
        self.setObjectName("hoverSourceItem")
        self.setStyleSheet(f"""
            #hoverSourceItem {{
                background-color: {tc("surface")};
                border: 1px solid {tc("overlay")};
                border-radius: 6px;
                padding: 6px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # 标题行：SVG 图标 + 文字 + 打开按钮
        hdr = QHBoxLayout()
        hdr.setSpacing(6)

        src_type = source.get("type", "")
        if src_type == "material":
            icon_name = "material_pool.svg"
            label_text = "资料"
        elif src_type == "speech":
            icon_name = "form.svg"
            label_text = "资料稿"
        else:
            icon_name = "note.svg"
            label_text = "便签"
        icon_lbl = _icon_label(icon_name)
        hdr.addWidget(icon_lbl)
        if source.get("deleted"):
            deleted_color = tc("error")
            lbl_type = QLabel(f"[{label_text}] {source.get('title', '')}  (已删除)")
            lbl_type.setStyleSheet(f"color: {deleted_color}; border: none; background: transparent;")
        else:
            lbl_type = QLabel(f"[{label_text}] {source.get('title', '')}")
            lbl_type.setStyleSheet(f"color: {tc('text')}; border: none; background: transparent;")
        lbl_type.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        hdr.addWidget(lbl_type, 1)

        if not source.get("deleted"):
            btn_open = QPushButton("打开")
            btn_open.setFixedSize(50, 22)
            btn_open.setObjectName("smallBtn")
            btn_open.setCursor(Qt.PointingHandCursor)
            btn_open.setStyleSheet(f"""
                QPushButton#smallBtn {{
                    background-color: {tc("overlay")};
                    color: {tc("accent_blue")};
                    border: 1px solid {tc("border")};
                    border-radius: 4px;
                    font-size: 10px;
                }}
                QPushButton#smallBtn:hover {{
                    background-color: {tc("hover")};
                }}
            """)
            btn_open.clicked.connect(lambda: self.open_requested.emit(self._source))
            hdr.addWidget(btn_open)

        layout.addLayout(hdr)

        # 摘要文字
        excerpt = source.get("excerpt", "")
        if excerpt:
            lbl_excerpt = QLabel(_short_text(excerpt, 200))
            lbl_excerpt.setWordWrap(True)
            lbl_excerpt.setFont(QFont("Microsoft YaHei", 9))
            lbl_excerpt.setStyleSheet(f"color: {tc('muted')}; border: none; background: transparent;")
            layout.addWidget(lbl_excerpt)


class HoverCard(QWidget):
    """自定义悬浮卡片，显示索引词的来源信息

    信号:
        open_source_requested(dict): 用户点击"打开"按钮，携带 source 信息
    """

    open_source_requested = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(MAX_CARD_WIDTH)
        self.setMaximumHeight(MAX_CARD_HEIGHT)

        self._data: dict | None = None
        self._hide_timer: QTimer | None = None

        # 主容器
        self._container = QFrame(self)
        self._container.setObjectName("hoverCardContainer")
        self._container.setStyleSheet(f"""
            #hoverCardContainer {{
                background-color: {tc("base")};
                border: 1px solid {tc("border")};
                border-radius: 10px;
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._container)

        card_layout = QVBoxLayout(self._container)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(6)

        # 标题行：SVG 图标 + 词语
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_icon = _icon_label("index.svg")
        title_row.addWidget(title_icon)

        self._title_label = QLabel()
        self._title_label.setObjectName("hoverCardTitle")
        self._title_label.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        self._title_label.setStyleSheet(f"color: {tc('accent_yellow')}; border: none; background: transparent;")
        title_row.addWidget(self._title_label, 1)
        card_layout.addLayout(title_row)

        # 手动解释区
        self._explanation_section = QWidget()
        self._explanation_section.setObjectName("hoverExplanationSection")
        self._explanation_section.setStyleSheet(f"border: none; background: transparent;")
        expl_layout = QVBoxLayout(self._explanation_section)
        expl_layout.setContentsMargins(0, 0, 0, 0)
        expl_layout.setSpacing(4)

        self._expl_title = _SectionTitle("手动解释", tc("accent_green"))
        expl_layout.addWidget(self._expl_title)

        self._expl_label = QLabel()
        self._expl_label.setObjectName("hoverExplText")
        self._expl_label.setWordWrap(True)
        self._expl_label.setFont(QFont("Microsoft YaHei", 10))
        self._expl_label.setStyleSheet(f"color: {tc('text')}; border: none; background: transparent;")
        expl_layout.addWidget(self._expl_label)

        card_layout.addWidget(self._explanation_section)

        # 分隔线
        self._sep1 = QFrame()
        self._sep1.setFrameShape(QFrame.HLine)
        self._sep1.setStyleSheet(f"border: none; border-top: 1px solid {tc('overlay')};")
        self._sep1.setVisible(False)
        card_layout.addWidget(self._sep1)

        # 来源区（滚动）
        self._scroll = QScrollArea()
        self._scroll.setObjectName("hoverCardScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setMaximumHeight(SECTION_MAX_HEIGHT)
        self._scroll.setStyleSheet(f"""
            #hoverCardScroll {{
                background: transparent;
                border: none;
            }}
            #hoverCardScroll QScrollBar:vertical {{
                width: 4px;
                background: transparent;
            }}
            #hoverCardScroll QScrollBar::handle:vertical {{
                background: {tc('muted')};
                border-radius: 2px;
            }}
        """)

        self._source_container = QWidget()
        self._source_container.setObjectName("hoverCardSources")
        self._source_container.setStyleSheet(f"border: none; background: transparent;")
        self._source_layout = QVBoxLayout(self._source_container)
        self._source_layout.setContentsMargins(0, 0, 0, 0)
        self._source_layout.setSpacing(6)
        self._source_layout.addStretch(1)
        self._scroll.setWidget(self._source_container)

        card_layout.addWidget(self._scroll, stretch=1)

        # 隐式拥有：卡片本身也是"可停留的"，鼠标在上面时不隐藏
        self.setMouseTracking(True)

    def load_data(self, term: str, explanation: str,
                  sources: list[dict]):
        """加载数据并重新构建卡片内容

        Args:
            term: 索引词
            explanation: 手动解释（可能为空）
            sources: [{type, title, excerpt, file_path/note_id, deleted}, ...]
        """
        self._data = {"term": term, "explanation": explanation, "sources": sources}
        self._rebuild_content()

    def _rebuild_content(self):
        """根据 self._data 重建卡片内容"""
        if not self._data:
            self.hide()
            return

        data = self._data
        term = data.get("term", "")
        explanation = data.get("explanation", "")
        sources = data.get("sources", [])

        # 标题
        self._title_label.setText(term)

        # 手动解释区
        has_explanation = bool(explanation and explanation.strip())
        if has_explanation:
            self._expl_label.setText(explanation)
            self._explanation_section.setVisible(True)
        else:
            self._expl_label.setText("暂无手动解释，点击编辑")
            self._expl_label.setStyleSheet(f"color: {tc('muted')}; font-style: italic; border: none; background: transparent;")
            self._explanation_section.setVisible(True)

        # 清空来源区
        self._clear_sources()

        # 来源区
        active_sources = [s for s in sources]
        if active_sources:
            self._sep1.setVisible(True)
            self._scroll.setVisible(True)

            mat_sources = [s for s in active_sources if s.get("type") == "material"]
            note_sources = [s for s in active_sources if s.get("type") == "note"]
            speech_sources = [s for s in active_sources if s.get("type") == "speech"]

            if mat_sources:
                mat_title = _SectionTitle(
                    f"资料来源（{len(mat_sources)}）", tc("accent_blue")
                )
                self._source_layout.insertWidget(
                    self._source_layout.count() - 1, mat_title
                )
                for src in mat_sources:
                    item = _SourceItem(src)
                    item.open_requested.connect(self._on_source_open)
                    self._source_layout.insertWidget(
                        self._source_layout.count() - 1, item
                    )

            if speech_sources:
                speech_title = _SectionTitle(
                    f"资料稿来源（{len(speech_sources)}）", tc("accent_purple")
                )
                self._source_layout.insertWidget(
                    self._source_layout.count() - 1, speech_title
                )
                for src in speech_sources:
                    item = _SourceItem(src)
                    item.open_requested.connect(self._on_source_open)
                    self._source_layout.insertWidget(
                        self._source_layout.count() - 1, item
                    )

            if note_sources:
                note_title = _SectionTitle(
                    f"便签来源（{len(note_sources)}）", tc("accent_green")
                )
                self._source_layout.insertWidget(
                    self._source_layout.count() - 1, note_title
                )
                for src in note_sources:
                    item = _SourceItem(src)
                    item.open_requested.connect(self._on_source_open)
                    self._source_layout.insertWidget(
                        self._source_layout.count() - 1, item
                    )
        else:
            self._sep1.setVisible(False)
            self._scroll.setVisible(False)

        self.adjustSize()
        if self.height() > MAX_CARD_HEIGHT:
            self.setFixedHeight(MAX_CARD_HEIGHT)
        else:
            self.setMinimumHeight(self.sizeHint().height())

    def _clear_sources(self):
        """清空来源区所有子控件"""
        while self._source_layout.count():
            item = self._source_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_source_open(self, source: dict):
        """用户点击"打开"按钮"""
        self.open_source_requested.emit(source)

    def refresh_theme_colors(self):
        """主题切换后刷新所有颜色：清空图标缓存 + 重设容器样式 + 重建内容"""
        global _ICON_CACHE
        _ICON_CACHE.clear()

        # 重设容器样式
        self._container.setStyleSheet(f"""
            #hoverCardContainer {{
                background-color: {tc("base")};
                border: 1px solid {tc("border")};
                border-radius: 10px;
            }}
        """)
        # 重设标题颜色
        self._title_label.setStyleSheet(
            f"color: {tc('accent_yellow')}; border: none; background: transparent;"
        )
        # 重设解释标签（恢复主色，_rebuild_content 会按需改掉）
        self._expl_label.setStyleSheet(
            f"color: {tc('text')}; border: none; background: transparent;"
        )
        # 重设分隔线颜色
        self._sep1.setStyleSheet(
            f"border: none; border-top: 1px solid {tc('overlay')};"
        )
        # 重设滚动条颜色
        self._scroll.setStyleSheet(f"""
            #hoverCardScroll {{
                background: transparent;
                border: none;
            }}
            #hoverCardScroll QScrollBar:vertical {{
                width: 4px;
                background: transparent;
            }}
            #hoverCardScroll QScrollBar::handle:vertical {{
                background: {tc('muted')};
                border-radius: 2px;
            }}
        """)

        # 完全重建内容（会重建所有 _SectionTitle 和 _SourceItem）
        if self._data:
            self._rebuild_content()

    # -- 显示/隐藏管理 --

    def schedule_hide(self):
        """启动延迟隐藏定时器（500ms 后隐藏）"""
        self._stop_hide_timer()
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self._hide_timer.start(HIDE_DELAY_MS)

    def cancel_hide(self):
        """取消延迟隐藏"""
        self._stop_hide_timer()

    def _stop_hide_timer(self):
        if self._hide_timer:
            self._hide_timer.stop()
            self._hide_timer = None

    def show_at(self, word_screen_rect: QRect):
        """根据高亮词的屏幕位置显示卡片"""
        card_h = self.height() if self.height() > 0 else MAX_CARD_HEIGHT
        x, y = self._calc_position(word_screen_rect, card_h)
        self.move(x, y)
        self.raise_()
        self.show()

    def move_to(self, word_screen_rect: QRect):
        """跟随移动时重新定位（仅移动，不弹窗）"""
        card_h = self.height() if self.height() > 0 else MAX_CARD_HEIGHT
        x, y = self._calc_position(word_screen_rect, card_h)
        self.move(x, y)

    @staticmethod
    def _calc_position(word_rect: QRect, card_height: int = MAX_CARD_HEIGHT) -> tuple[int, int]:
        """根据词的屏幕矩形计算卡片的最佳显示位置

        策略：优先在词下方弹出，空间不足时在上方弹出。
        水平方向以词左侧为基准，超出屏幕时右对齐到词右侧。

        Args:
            word_rect: 高亮词在屏幕上的矩形区域
            card_height: 卡片实际高度（用于精确计算可用空间）
        """
        from PyQt5.QtWidgets import QApplication
        desk = QApplication.primaryScreen().availableGeometry()
        gap = 8  # 卡片与词之间的间距

        # 垂直方向：优先在词下方
        above_y = word_rect.top() - card_height - gap
        below_y = word_rect.bottom() + gap

        if below_y + card_height <= desk.bottom():
            y = below_y
        elif above_y >= desk.top():
            y = above_y
        else:
            # 两边都不够，取可用空间的更近一侧
            space_above = word_rect.top() - desk.top()
            space_below = desk.bottom() - word_rect.bottom()
            if space_above > space_below:
                y = max(desk.top(), word_rect.top() - card_height - gap)
            else:
                y = min(desk.bottom() - card_height, below_y)

        # 水平方向：以词左侧为基准，超出则右对齐
        x = word_rect.left()
        if x + MAX_CARD_WIDTH > desk.right():
            x = word_rect.right() - MAX_CARD_WIDTH
        if x < desk.left():
            x = desk.left()

        return x, y

    def mousePressEvent(self, event):
        """点击卡片不隐藏"""
        super().mousePressEvent(event)

    def enterEvent(self, event):
        """鼠标进入卡片 -> 取消隐藏定时器"""
        self.cancel_hide()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开卡片 -> 启动隐藏定时器"""
        self.schedule_hide()
        super().leaveEvent(event)
