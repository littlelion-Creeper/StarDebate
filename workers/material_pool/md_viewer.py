"""
md_viewer.py — 通用 Markdown 文件查看器组件（纯 Qt 控件版）
============================================================
自包含的 Markdown 渲染 / 文本查看器，使用纯 Qt Widgets 构建，
不依赖任何 HTML 元素。

支持 Markdown 语法：标题（#/##/###）、代码块（```）、引用（>）、
无序列表（-/*/+）、水平线（---）、粗体（**）、斜体（*）。

可使用于资料池、便签、插件等场景。
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
import re


class _MDSegment:
    """单个 Markdown 片段的数据结构"""
    TYPE_PARAGRAPH = "paragraph"
    TYPE_H1 = "h1"
    TYPE_H2 = "h2"
    TYPE_H3 = "h3"
    TYPE_CODE = "code"
    TYPE_QUOTE = "quote"
    TYPE_LIST = "list"
    TYPE_HR = "hr"
    TYPE_EMPTY = "empty"


class MDViewer(QWidget):
    """通用 Markdown 查看器组件（纯 Qt 控件）

    Signals:
        closed: 用户点击关闭按钮
    """
    closed = pyqtSignal()

    def __init__(self, parent=None, title: str = "文档查看器",
                 show_close: bool = True):
        super().__init__(parent)
        self._title = title
        self._show_close = show_close
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 标题栏 ──
        header = QFrame()
        header.setObjectName("mdViewerHeader")
        header.setFixedHeight(42)
        hd_layout = QHBoxLayout(header)
        hd_layout.setContentsMargins(12, 4, 12, 4)

        self._lbl_title = QLabel(self._title)
        self._lbl_title.setObjectName("mdViewerTitle")
        self._lbl_title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        hd_layout.addWidget(self._lbl_title)
        hd_layout.addStretch()

        if self._show_close:
            btn_close = QPushButton("×")
            btn_close.setObjectName("mdViewerCloseBtn")
            btn_close.setFixedSize(28, 28)
            btn_close.setFont(QFont("Microsoft YaHei", 14))
            btn_close.setCursor(Qt.PointingHandCursor)
            btn_close.clicked.connect(self.closed.emit)
            hd_layout.addWidget(btn_close)

        layout.addWidget(header)

        # ── 内容区域（QScrollArea + 容器，纯控件） ──
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setObjectName("mdViewerContent")

        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(16, 12, 16, 12)
        self._container_layout.setSpacing(2)
        self._container_layout.addStretch(1)

        self._scroll_area.setWidget(self._container)
        layout.addWidget(self._scroll_area, stretch=1)

    # ── 公开 API ────────────────────────────────────────────

    def set_title(self, title: str):
        """设置标题"""
        self._title = title
        if hasattr(self, '_lbl_title'):
            self._lbl_title.setText(title)

    def set_text(self, text: str):
        """设置纯文本内容（自动识别 Markdown）"""
        self.set_markdown(text)

    def set_html(self, html: str):
        """设置为纯文本（忽略 HTML 标签）"""
        # 去掉 HTML 标签，当作纯文本显示
        plain = re.sub(r"<[^>]+>", "", html)
        plain = plain.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        self.set_markdown(plain)

    def set_markdown(self, md_text: str):
        """解析 Markdown 并用纯 Qt 控件渲染"""
        self._clear_content()
        segments = self._parse_markdown(md_text)
        for seg in segments:
            widget = self._build_segment_widget(seg)
            if widget:
                self._container_layout.insertWidget(
                    self._container_layout.count() - 1, widget
                )

    def get_text(self) -> str:
        """获取当前显示的纯文本"""
        parts = []
        for i in range(self._container_layout.count()):
            w = self._container_layout.itemAt(i).widget()
            if isinstance(w, QLabel):
                txt = w.text()
                # 去除样式前缀标记
                txt = re.sub(r"^[#\->*\s]+", "", txt).strip()
                if txt:
                    parts.append(txt)
            elif isinstance(w, QFrame) and w.property("_md_type") == "code":
                code_label = w.findChild(QLabel)
                if code_label:
                    parts.append(code_label.text())
        return "\n".join(parts)

    def set_readonly(self, readonly: bool):
        """设置只读（无操作，纯查看器始终只读）"""
        pass

    def text_edit(self):
        """返回自身上层 QScrollArea（供高级操作）"""
        return self._scroll_area

    # ── 内部清理 ────────────────────────────────────────────

    def _clear_content(self):
        """清除所有已渲染的片段控件，保留末尾的 stretch"""
        layout = self._container_layout
        i = 0
        while i < layout.count():
            item = layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                # 跳过 stretch
                if isinstance(widget, QWidget):
                    layout.takeAt(i)
                    widget.deleteLater()
                else:
                    i += 1
            else:
                i += 1

    # ── Markdown 解析 ──────────────────────────────────────

    @staticmethod
    def _parse_markdown(md: str) -> list:
        """将 Markdown 文本解析为片段列表"""
        segments = []
        lines = md.split("\n")
        in_code = False
        code_buf = []

        for raw_line in lines:
            line = raw_line

            # 代码块开始/结束
            if line.strip().startswith("```"):
                if in_code:
                    # 结束代码块
                    segments.append({
                        "type": _MDSegment.TYPE_CODE,
                        "content": "\n".join(code_buf),
                    })
                    code_buf = []
                    in_code = False
                else:
                    in_code = True
                continue

            if in_code:
                code_buf.append(line)
                continue

            # 空行
            if not line.strip():
                segments.append({"type": _MDSegment.TYPE_EMPTY})
                continue

            # 水平线
            if line.strip() in ("---", "***", "___"):
                segments.append({"type": _MDSegment.TYPE_HR})
                continue

            # 标题
            if line.startswith("### "):
                segments.append({"type": _MDSegment.TYPE_H3, "content": line[4:]})
                continue
            if line.startswith("## "):
                segments.append({"type": _MDSegment.TYPE_H2, "content": line[3:]})
                continue
            if line.startswith("# "):
                segments.append({"type": _MDSegment.TYPE_H1, "content": line[2:]})
                continue

            # 引用
            if re.match(r"^>\s?", line):
                content = re.sub(r"^>\s?", "", line)
                segments.append({"type": _MDSegment.TYPE_QUOTE, "content": content})
                continue

            # 无序列表
            if re.match(r"^\s*[\-\*\+]\s+", line):
                content = re.sub(r"^\s*[\-\*\+]\s+", "", line)
                segments.append({"type": _MDSegment.TYPE_LIST, "content": content})
                continue

            # 普通段落（处理粗体/斜体后直接显示）
            segments.append({"type": _MDSegment.TYPE_PARAGRAPH, "content": line})

        # 未关闭的代码块
        if in_code and code_buf:
            segments.append({
                "type": _MDSegment.TYPE_CODE,
                "content": "\n".join(code_buf),
            })

        return segments

    # ── 构建纯 Qt 控件片段 ─────────────────────────────────

    @staticmethod
    def _render_inline(text: str) -> str:
        """处理行内粗体/斜体，返回纯文本（移除标记）"""
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        return text

    def _build_segment_widget(self, seg: dict):
        """根据片段类型构建对应的纯 Qt 控件"""
        seg_type = seg.get("type")

        if seg_type == _MDSegment.TYPE_EMPTY:
            spacer = QFrame()
            spacer.setObjectName("mdSpacer")
            spacer.setFixedHeight(6)
            return spacer

        if seg_type == _MDSegment.TYPE_HR:
            line = QFrame()
            line.setObjectName("mdHr")
            line.setFrameShape(QFrame.HLine)
            line.setFixedHeight(1)
            return line

        if seg_type == _MDSegment.TYPE_H1:
            label = QLabel(seg.get("content", ""))
            label.setObjectName("mdH1")
            label.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
            label.setWordWrap(True)
            return label

        if seg_type == _MDSegment.TYPE_H2:
            label = QLabel(seg.get("content", ""))
            label.setObjectName("mdH2")
            label.setFont(QFont("Microsoft YaHei", 15, QFont.Bold))
            label.setWordWrap(True)
            return label

        if seg_type == _MDSegment.TYPE_H3:
            label = QLabel(seg.get("content", ""))
            label.setObjectName("mdH3")
            label.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
            label.setWordWrap(True)
            return label

        if seg_type == _MDSegment.TYPE_CODE:
            content = seg.get("content", "")
            frame = QFrame()
            frame.setProperty("_md_type", "code")
            frame.setObjectName("mdCodeBlock")
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(12, 10, 12, 10)
            frame_layout.setSpacing(0)

            code_label = QLabel(content)
            code_label.setObjectName("mdCodeLabel")
            code_label.setFont(QFont("Consolas", 12))
            code_label.setWordWrap(True)
            code_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            frame_layout.addWidget(code_label)
            return frame

        if seg_type == _MDSegment.TYPE_QUOTE:
            content = self._render_inline(seg.get("content", ""))
            frame = QFrame()
            frame.setObjectName("mdQuoteBlock")
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(16, 4, 0, 4)
            frame_layout.setSpacing(0)

            quote_label = QLabel(content)
            quote_label.setObjectName("mdQuoteLabel")
            quote_label.setFont(QFont("Microsoft YaHei", 13))
            quote_label.setWordWrap(True)
            frame_layout.addWidget(quote_label)
            return frame

        if seg_type == _MDSegment.TYPE_LIST:
            content = self._render_inline(seg.get("content", ""))
            frame = QFrame()
            frame.setObjectName("mdLiFrame")
            frame_layout = QHBoxLayout(frame)
            frame_layout.setContentsMargins(12, 1, 0, 1)
            frame_layout.setSpacing(8)

            bullet = QLabel("•")
            bullet.setObjectName("mdLiBullet")
            bullet.setFont(QFont("Microsoft YaHei", 14))
            bullet.setFixedWidth(12)
            frame_layout.addWidget(bullet)

            text = QLabel(content)
            text.setObjectName("mdLiText")
            text.setFont(QFont("Microsoft YaHei", 13))
            text.setWordWrap(True)
            frame_layout.addWidget(text, 1)
            return frame

        if seg_type == _MDSegment.TYPE_PARAGRAPH:
            content = self._render_inline(seg.get("content", ""))
            label = QLabel(content)
            label.setObjectName("mdParagraph")
            label.setFont(QFont("Microsoft YaHei", 13))
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            return label

        return None
