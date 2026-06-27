"""一辩稿导出预览弹窗 — TitleBar + Ribbon 格式控制 + QWebEngineView 预览

组件使用规范（优先通用组件）:
    - TitleBar: components.title_bar.TitleBar
    - StarButton: components.star_button.StarButton
    - QSS 模板 + tc() 动态颜色
"""

from __future__ import annotations

import os

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QComboBox, QFrame, QSizePolicy, QFileDialog, QMessageBox,
)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QFont

from components.theme_colors import tc
from components.title_bar import TitleBar
from components.star_button import StarButton
from components.res_path import get_resource_path
from components.icon_loader import get_module_svg_icon

from .export_worker import (
    generate_preview_html,
    export_to_docx,
    export_to_pdf,
)

# ── QWebEngine ─────────────────────────────────────────────────────────────
_HAVE_WEBENGINE = False
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    _HAVE_WEBENGINE = True
except ImportError:
    pass


# ═══════════════════════════════════════════════════════════════════════════
#  常量
# ═══════════════════════════════════════════════════════════════════════════

FONT_SIZES = [str(i) for i in (10, 11, 12, 14, 16, 18, 20, 22, 24)]
FONT_NAMES = ["宋体", "黑体", "楷体", "仿宋", "微软雅黑"]
ALIGN_OPTIONS = ["左对齐", "居中对齐", "右对齐", "两端对齐"]
INDENT_OPTIONS = ["0字符", "1字符", "2字符", "3字符", "4字符"]
LINE_SPACING_OPTIONS = ["1.0", "1.25", "1.5", "1.75", "2.0"]
PAGE_SIZE_OPTIONS = ["A4", "A5", "B5", "Letter"]
ORIENTATION_OPTIONS = ["纵向", "横向"]


# ═══════════════════════════════════════════════════════════════════════════
#  Ribbon 控件工厂
# ═══════════════════════════════════════════════════════════════════════════

def _ribbon_group(label: str, widget: QWidget) -> QWidget:
    """创建一个 Ribbon 分组：上标签 + 下控件。"""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(4, 2, 4, 2)
    layout.setSpacing(3)

    lbl = QLabel(label)
    lbl.setObjectName("ribbonLabel")
    lbl.setFont(QFont("Microsoft YaHei", 9))
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setFixedHeight(16)

    layout.addWidget(lbl, alignment=Qt.AlignCenter)
    layout.addWidget(widget)
    return container


def _combo(items: list[str], default: str = "", min_w: int = 72) -> QComboBox:
    cb = QComboBox()
    cb.setObjectName("ribbonCombo")
    cb.addItems(items)
    if default:
        idx = cb.findText(default)
        if idx >= 0:
            cb.setCurrentIndex(idx)
    cb.setMinimumWidth(min_w)
    cb.setMaximumHeight(26)
    return cb


# ═══════════════════════════════════════════════════════════════════════════
#  主弹窗
# ═══════════════════════════════════════════════════════════════════════════

class ExportPreviewDialog(QDialog):
    """一辩稿导出预览弹窗"""

    def __init__(self, content: str, side_label: str = "", parent=None):
        super().__init__(parent)
        self._content = content
        self._side_label = side_label  # 辩论立场文本，如"支持人工智能发展"

        self.setWindowTitle("一辩稿导出预览")
        self.resize(900, 680)
        self.setMinimumSize(700, 500)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)

        if parent:
            pg = parent.geometry()
            self.move(
                pg.x() + (pg.width() - self.width()) // 2,
                pg.y() + (pg.height() - self.height()) // 2,
            )

        # ── 格式控制状态 ──
        self._font_name = "宋体"
        self._font_size = 12
        self._align = "两端对齐"
        self._indent = 2
        self._line_spacing = 1.5
        self._page_size = "A4"
        self._orientation = "纵向"

        self._build_ui()
        self._apply_style()
        self._refresh_preview()

    # ══════════════════════════════════════════════════════════════════
    #  UI 构建
    # ══════════════════════════════════════════════════════════════════

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── TitleBar ──
        self._title_bar = TitleBar(self, "一辩稿导出预览", "📄", compact=True)
        main_layout.addWidget(self._title_bar)

        # ── Ribbon 工具栏 ──
        ribbon = self._build_ribbon()
        main_layout.addWidget(ribbon)

        # ── 分隔线 ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("exportPreviewSep")
        sep.setFixedHeight(1)
        main_layout.addWidget(sep)

        # ── 预览区域 ──
        if _HAVE_WEBENGINE:
            self._web_view = QWebEngineView()
            self._web_view.setObjectName("exportPreviewWeb")
            self._web_view.setStyleSheet("background: transparent; border: none;")
        else:
            self._web_view = QLabel("需要安装 PyQtWebEngine 才能预览\n\npip install PyQtWebEngine")
            self._web_view.setAlignment(Qt.AlignCenter)
            self._web_view.setFont(QFont("Microsoft YaHei", 12))
            self._web_view.setObjectName("exportPreviewFallback")
        main_layout.addWidget(self._web_view, stretch=1)

        # ── 底部操作栏 ──
        footer = self._build_footer()
        main_layout.addWidget(footer)

    def _build_ribbon(self) -> QWidget:
        """构建 Ribbon 样式格式控制栏。"""
        ribbon = QWidget()
        ribbon.setObjectName("exportPreviewRibbon")
        ribbon.setFixedHeight(56)
        layout = QHBoxLayout(ribbon)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(2)

        # 字号
        self._cb_font_size = _combo(FONT_SIZES, "12", 64)
        self._cb_font_size.currentTextChanged.connect(self._on_format_changed)
        layout.addWidget(_ribbon_group("字号", self._cb_font_size))

        # 字体
        self._cb_font_name = _combo(FONT_NAMES, "宋体", 80)
        self._cb_font_name.currentTextChanged.connect(self._on_format_changed)
        layout.addWidget(_ribbon_group("字体", self._cb_font_name))

        # 对齐
        self._cb_align = _combo(ALIGN_OPTIONS, "两端对齐", 80)
        self._cb_align.currentTextChanged.connect(self._on_format_changed)
        layout.addWidget(_ribbon_group("对齐", self._cb_align))

        # 首行缩进
        self._cb_indent = _combo(INDENT_OPTIONS, "2字符", 72)
        self._cb_indent.currentTextChanged.connect(self._on_format_changed)
        layout.addWidget(_ribbon_group("缩进", self._cb_indent))

        # 行距
        self._cb_line_spacing = _combo(LINE_SPACING_OPTIONS, "1.5", 64)
        self._cb_line_spacing.currentTextChanged.connect(self._on_format_changed)
        layout.addWidget(_ribbon_group("行距", self._cb_line_spacing))

        # 纸张
        self._cb_page_size = _combo(PAGE_SIZE_OPTIONS, "A4", 64)
        self._cb_page_size.currentTextChanged.connect(self._on_format_changed)
        layout.addWidget(_ribbon_group("纸张", self._cb_page_size))

        # 方向
        self._cb_orientation = _combo(ORIENTATION_OPTIONS, "纵向", 56)
        self._cb_orientation.currentTextChanged.connect(self._on_format_changed)
        layout.addWidget(_ribbon_group("方向", self._cb_orientation))

        layout.addStretch()

        return ribbon

    def _build_footer(self) -> QWidget:
        """构建底部操作栏。"""
        footer = QWidget()
        footer.setObjectName("exportPreviewFooter")
        footer.setFixedHeight(48)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        layout.addStretch()

        btn_export_docx = StarButton("导出 .docx", ratio_h=0.75)
        btn_export_docx.clicked.connect(self._on_export_docx)

        btn_export_pdf = StarButton("导出 .pdf", ratio_h=0.75)
        btn_export_pdf.clicked.connect(self._on_export_pdf)

        btn_cancel = StarButton("取消", ratio_h=0.75)
        btn_cancel.clicked.connect(self.reject)

        layout.addWidget(btn_export_docx)
        layout.addWidget(btn_export_pdf)
        layout.addSpacing(8)
        layout.addWidget(btn_cancel)

        return footer

    # ══════════════════════════════════════════════════════════════════
    #  格式响应
    # ══════════════════════════════════════════════════════════════════

    def _on_format_changed(self):
        """Ribbon 控件变更时刷新状态并重新渲染预览。"""
        self._font_size = int(self._cb_font_size.currentText())
        self._font_name = self._cb_font_name.currentText()
        self._align = self._cb_align.currentText()
        indent_text = self._cb_indent.currentText()
        self._indent = int(indent_text.replace("字符", "")) if "字符" in indent_text else 0
        self._line_spacing = float(self._cb_line_spacing.currentText())
        self._page_size = self._cb_page_size.currentText()
        self._orientation = self._cb_orientation.currentText()
        self._refresh_preview()

    def _refresh_preview(self):
        """重新生成 HTML 并加载到 QWebEngineView。"""
        if not _HAVE_WEBENGINE:
            return
        html = generate_preview_html(
            self._content, side_label=self._side_label,
            font_name=self._font_name,
            font_size=self._font_size,
            align=self._align,
            indent_chars=self._indent,
            line_spacing=self._line_spacing,
            page_size=self._page_size,
            orientation=self._orientation,
        )
        self._web_view.setHtml(html, QUrl("about:blank"))

    # ══════════════════════════════════════════════════════════════════
    #  导出
    # ══════════════════════════════════════════════════════════════════

    def _on_export_docx(self):
        default_name = f"{self._side_label}_一辩稿.docx" if self._side_label else "一辩稿.docx"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出为 .docx", default_name,
            "Word 文档 (*.docx)",
        )
        if not filepath:
            return
        try:
            export_to_docx(
                self._content, filepath, side_label=self._side_label,
                font_name=self._font_name,
                font_size=self._font_size,
                align=self._align,
                indent_chars=self._indent,
                line_spacing=self._line_spacing,
                page_size=self._page_size,
                orientation=self._orientation,
            )
            QMessageBox.information(self, "导出成功", f"已导出至:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出 .docx 时出错:\n{e}")

    def _on_export_pdf(self):
        default_name = f"{self._side_label}_一辩稿.pdf" if self._side_label else "一辩稿.pdf"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出为 .pdf", default_name,
            "PDF 文档 (*.pdf)",
        )
        if not filepath:
            return
        try:
            export_to_pdf(
                self._content, filepath, side_label=self._side_label,
                font_name=self._font_name,
                font_size=self._font_size,
                align=self._align,
                indent_chars=self._indent,
                line_spacing=self._line_spacing,
                page_size=self._page_size,
                orientation=self._orientation,
            )
            QMessageBox.information(self, "导出成功", f"已导出至:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出 .pdf 时出错:\n{e}")

    # ══════════════════════════════════════════════════════════════════
    #  主题
    # ══════════════════════════════════════════════════════════════════

    def _apply_style(self):
        """加载 QSS 模板样式。"""
        qss_path = get_resource_path(
            "style/qss_templates/export_preview.qss"
        )
        if os.path.isfile(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                qss = f.read()
            # 替换 @key@ 占位符
            import re as _re
            def _replace(m):
                key = m.group(1)
                val = tc(key)
                return val if val else "#FFFFFF"
            qss = _re.sub(r'@(\w+)@', _replace, qss)
            self.setStyleSheet(qss)
