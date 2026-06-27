"""自定义提示弹窗 — CustomDialog 类。

通用可复用弹窗控件，替代 Qt 的 QMessageBox。
支持五种类型（info/warning/error/question/custom）、
SVG 图标渲染（通过 SvgRenderer 动态着色）、主/辅按钮、可选复选框、主题跟随。

位于 components/popup_dialog/，与 TitleBar 同级，属通用组件。
"""

import os
import json
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QFrame, QApplication, QPushButton,
)

from components.star_button import StarButton
from components.theme_colors import tc
from workers.app_config.config_paths import get_config_path
from PyQt5.QtCore import Qt, QSize, QRect, QTimer, pyqtProperty
from PyQt5.QtGui import QPixmap, QFont, QPainter, QPen, QColor, QBrush, QPainterPath

# ── SVG 渲染器（动态着色 + 主题跟随 + 缓存）──
from components.svg_renderer import SvgRenderer

# ── 图标文件映射 ─────────────────────────────────────────────────────
_ICON_MAP = {
    "info": "info_circle.svg",
    "warning": "exclamationmark_circle.svg",
    "error": "xmark_circle.svg",
    "question": "questionmark_circle.svg",
}

# ── 各类型 SVG 着色映射（主题色键，由 SvgRenderer 解析为实际颜色）──
_TYPE_COLOR = {
    "info": "accent_blue",
    "warning": "accent_yellow",
    "error": "accent_red",
    "question": "accent_blue",
}

# ── 项目根目录（通过统一资源路径解析）───────────────────────────────
from components.res_path import get_resource_root
_ICON_DIR = os.path.join(get_resource_root(), "icon", "message_box")


def _render_svg(svg_path: str, size: QSize, color_key: str = "text") -> QPixmap:
    """通过 SvgRenderer 渲染 SVG 图标为 QPixmap。

    自动跟随当前主题颜色；若 SvgRenderer 尚未初始化，则使用项目根目录懒加载。

    Args:
        svg_path: SVG 文件的完整路径
        size: 目标尺寸
        color_key: 主题色键名（如 "accent_blue", "text" 等）

    Returns:
        渲染后的 QPixmap
    """
    if not os.path.exists(svg_path):
        return QPixmap(size)

    # 确保 SvgRenderer 已初始化
    if not getattr(SvgRenderer, "_initialized", False):
        SvgRenderer.init(get_resource_root())

    w = size.width() if isinstance(size, QSize) else size
    return SvgRenderer.icon(svg_path, w, color=color_key)


# ═══════════════════════════════════════════════════════════════════════
#  绘制型关闭按钮
# ═══════════════════════════════════════════════════════════════════════

class _PopupCloseButton(QPushButton):
    """弹窗关闭按钮 — paintEvent 绘制 ✕ 交叉线。

    hover 时变为红色，颜色通过 pyqtProperty 暴露，可由 QSS 的 qproperty-* 覆盖。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 28)
        self.setCursor(Qt.PointingHandCursor)
        self._clr_norm = QColor("#a6adc8")
        self._clr_hover = QColor("#ffffff")
        self._bg_hover = QColor("#f38ba8")

    # ── QSS 可覆盖的 pyqtProperty ──────────────────────────────

    def _get_icon_normal(self) -> QColor:
        return self._clr_norm

    def _set_icon_normal(self, color: QColor):
        self._clr_norm = QColor(color)
        self.update()

    iconNormal = pyqtProperty(QColor, fget=_get_icon_normal, fset=_set_icon_normal)

    def _get_icon_hover(self) -> QColor:
        return self._clr_hover

    def _set_icon_hover(self, color: QColor):
        self._clr_hover = QColor(color)
        self.update()

    iconHover = pyqtProperty(QColor, fget=_get_icon_hover, fset=_set_icon_hover)

    def _get_bg_hover(self) -> QColor:
        return self._bg_hover

    def _set_bg_hover(self, color: QColor):
        self._bg_hover = QColor(color)
        self.update()

    bgHover = pyqtProperty(QColor, fget=_get_bg_hover, fset=_set_bg_hover)

    # ── 绘制 ──────────────────────────────────────────────────

    _RADIUS = 6  # 圆角半径

    def paintEvent(self, event):
        p = QPainter(self)
        if not p.isActive():
            return

        p.setRenderHint(QPainter.Antialiasing)

        under = self.underMouse()
        if under:
            # 绘制圆角背景（fillPath 需要 QBrush，不能直接传 QColor）
            path = QPainterPath()
            r = self.rect()
            path.addRoundedRect(r.x(), r.y(), r.width(), r.height(),
                                self._RADIUS, self._RADIUS)
            p.fillPath(path, QBrush(self._bg_hover))
            p.setPen(QPen(self._clr_hover, 1.5))
        else:
            p.setPen(QPen(self._clr_norm, 1.5))

        # 绘制 ✕ 交叉线
        s = 10
        cx, cy = self.rect().center().x(), self.rect().center().y()
        p.drawLine(cx - s // 2, cy - s // 2, cx + s // 2, cy + s // 2)
        p.drawLine(cx - s // 2, cy + s // 2, cx + s // 2, cy - s // 2)
        p.end()


# ═══════════════════════════════════════════════════════════════════════
#  CustomDialog
# ═══════════════════════════════════════════════════════════════════════

class CustomDialog(QDialog):
    """自定义提示弹窗。

    Attributes:
        clicked_button: 用户点击的按钮标识符（仅在 exec_() 后有效）。
        checkbox_checked: 复选框是否被勾选。

    静态便捷方法:
        information(parent, title, message, ...)  — 信息提示
        warning(parent, title, message, ...)      — 警告提示
        error(parent, title, message, ...)         — 错误提示
        question(parent, title, message, ...)      — 询问确认
        confirm(parent, title, message, ...)       — 确认操作（直接返回 bool）
    """

    # ── 静态便捷方法 ──────────────────────────────────────────────

    @staticmethod
    def information(parent=None, title: str = "提示", message: str = "",
                    buttons=None, checkbox: str = ""):
        """信息提示弹窗。返回用户点击的按钮标识符。"""
        dlg = CustomDialog(parent, "info", title, message, buttons, checkbox)
        dlg.exec_()
        return dlg.clicked_button

    @staticmethod
    def warning(parent=None, title: str = "警告", message: str = "",
                buttons=None, checkbox: str = ""):
        """警告提示弹窗。返回用户点击的按钮标识符。"""
        dlg = CustomDialog(parent, "warning", title, message, buttons, checkbox)
        dlg.exec_()
        return dlg.clicked_button

    @staticmethod
    def error(parent=None, title: str = "错误", message: str = "",
              buttons=None, checkbox: str = ""):
        """错误提示弹窗。返回用户点击的按钮标识符。"""
        dlg = CustomDialog(parent, "error", title, message, buttons, checkbox)
        dlg.exec_()
        return dlg.clicked_button

    @staticmethod
    def question(parent=None, title: str = "确认", message: str = "",
                 buttons=None, checkbox: str = ""):
        """询问确认弹窗。默认按钮为 [("取消","cancel"), ("确定","ok")]。"""
        if buttons is None:
            buttons = [("取消", "cancel"), ("确定", "ok")]
        dlg = CustomDialog(parent, "question", title, message, buttons, checkbox)
        dlg.exec_()
        return dlg.clicked_button

    @staticmethod
    def confirm(parent=None, title: str = "确认", message: str = "",
                ok_text: str = "确定", cancel_text: str = "取消",
                checkbox: str = "") -> bool:
        """确认操作弹窗，直接返回 True/False。"""
        result = CustomDialog.question(
            parent, title, message,
            buttons=[(cancel_text, "cancel"), (ok_text, "ok")],
            checkbox=checkbox,
        )
        return result == "ok"

    # ── 实例化 ────────────────────────────────────────────────────

    def __init__(self, parent=None, dialog_type: str = "info",
                 title: str = "", message: str = "",
                 buttons=None, checkbox: str = ""):
        """创建弹窗。

        Args:
            parent: 父窗口
            dialog_type: 弹窗类型（"info"/"warning"/"error"/"question"/"custom"）
            title: 标题栏文字
            message: 消息内容文本
            buttons: 按钮列表 [(文字, 标识符), ...]。默认 [("确定","ok")]。
            checkbox: 可选的复选框文字，空字符串表示不显示。
        """
        super().__init__(parent)
        self._dialog_type = dialog_type if dialog_type in _ICON_MAP else "info"
        self._title = title or "提示"
        self._message = message
        self._buttons = buttons or [("确定", "ok")]
        self._checkbox_text = checkbox
        self.clicked_button: str = ""
        self.checkbox_checked: bool = False

        self.setObjectName("popupDialog")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowModality(Qt.ApplicationModal)
        self._setup_ui()
        self._load_theme_qss()
        # 延迟到下一个事件循环，确保 setStyleSheet() 的字体/样式已生效
        QTimer.singleShot(0, self._deferred_init)

    def _deferred_init(self):
        """延迟初始化：在 QSS 生效后计算尺寸并居中（避免双渲染）。"""
        self._adjust_size()
        self._center_on_parent()
        # 应用圆角遮罩
        self._apply_rounded_mask()

    # ── 圆角遮罩 ────────────────────────────────────────────────────

    ROUNDED_RADIUS = 12

    def _apply_rounded_mask(self):
        """为弹窗应用圆角遮罩，使 border-radius 在 Windows 上生效。"""
        from PyQt5.QtGui import QPainterPath, QRegion
        try:
            path = QPainterPath()
            path.addRoundedRect(
                0, 0, self.width(), self.height(),
                self.ROUNDED_RADIUS, self.ROUNDED_RADIUS,
            )
            polygon = path.toFillPolygon()
            region = QRegion(polygon.toPolygon())
            self.setMask(region)
        except Exception:
            pass

    def resizeEvent(self, event):
        """尺寸变化时重新应用圆角遮罩。"""
        super().resizeEvent(event)
        self._apply_rounded_mask()

    # ── UI 构建 ────────────────────────────────────────────────────

    def _setup_ui(self):
        """构建弹窗整体布局（含圆角容器）。"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 圆角容器（WA_TranslucentBackground 下承载背景和圆角）──
        self._container = QFrame()
        self._container.setObjectName("popupContainer")
        self._container.setStyleSheet(
            f"#popupContainer {{"
            f"  background-color: {tc('base')};"
            f"  border: 1px solid {tc('overlay')};"
            f"  border-radius: {self.ROUNDED_RADIUS}px;"
            f"}}"
            f"#popupTitleBar {{"
            f"  background-color: {tc('surface')};"
            f"  border-top-left-radius: {self.ROUNDED_RADIUS}px;"
            f"  border-top-right-radius: {self.ROUNDED_RADIUS}px;"
            f"}}"
        )
        container_layout = QVBoxLayout(self._container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # ── 标题栏 ──────────────────────────────────────────────
        self._build_title_bar(container_layout)

        # ── 内容区域 ────────────────────────────────────────────
        self._build_content(container_layout)

        main_layout.addWidget(self._container)

    def _build_title_bar(self, main_layout):
        """构建自定义标题栏（42px）。"""
        title_bar = QFrame()
        title_bar.setObjectName("popupTitleBar")
        title_bar.setFixedHeight(42)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(12, 0, 8, 0)
        title_layout.setSpacing(6)

        # 标题栏图标（26×26 SVG）
        title_icon = QLabel()
        title_icon.setObjectName("popupTitleIcon")
        title_icon.setFixedSize(26, 26)
        title_icon.setAlignment(Qt.AlignCenter)
        icon_path = self._icon_path()
        color_key = _TYPE_COLOR.get(self._dialog_type, "text")
        pix = _render_svg(icon_path, QSize(26, 26), color_key)
        if not pix.isNull():
            title_icon.setPixmap(pix)
        title_layout.addWidget(title_icon)

        # 标题文字
        title_label = QLabel(self._title)
        title_label.setObjectName("popupTitleLabel")
        title_layout.addWidget(title_label)

        title_layout.addStretch()

        # 关闭按钮（paintEvent 绘制 ✕ 交叉线）
        close_btn = _PopupCloseButton()
        close_btn.setObjectName("popupCloseBtn")
        close_btn.clicked.connect(self.reject)
        title_layout.addWidget(close_btn)

        main_layout.addWidget(title_bar)

    def _build_content(self, main_layout):
        """构建内容区域（图标 + 消息 + 复选框 + 按钮）。"""
        content = QFrame()
        content.setObjectName("popupContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(0)

        # ── 图标 + 消息行 ──────────────────────────────────────
        msg_row = QHBoxLayout()
        msg_row.setSpacing(16)
        msg_row.setContentsMargins(0, 0, 0, 0)

        # 消息图标（64×64 SVG）
        msg_icon = QLabel()
        msg_icon.setObjectName("popupMsgIcon")
        msg_icon.setFixedSize(64, 64)
        msg_icon.setAlignment(Qt.AlignCenter)
        icon_path = self._icon_path()
        color_key = _TYPE_COLOR.get(self._dialog_type, "text")
        pix = _render_svg(icon_path, QSize(64, 64), color_key)
        if not pix.isNull():
            msg_icon.setPixmap(pix)
        msg_row.addWidget(msg_icon)

        # 消息文本
        msg_label = QLabel(self._message)
        msg_label.setObjectName("popupMsgLabel")
        msg_label.setWordWrap(True)
        msg_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        msg_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        msg_row.addWidget(msg_label, 1)

        content_layout.addLayout(msg_row)

        # ── 复选框（可选）──────────────────────────────────────
        if self._checkbox_text:
            content_layout.addSpacing(14)
            self._checkbox = QCheckBox(self._checkbox_text)
            self._checkbox.setObjectName("popupCheckbox")
            self._checkbox.setCursor(Qt.PointingHandCursor)
            content_layout.addWidget(self._checkbox)
        else:
            self._checkbox = None

        # ── 按钮行 ──────────────────────────────────────────────
        content_layout.addSpacing(20)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addStretch()

        for i, (text, btn_id) in enumerate(self._buttons):
            btn = StarButton(text, None, layout_mode="text_only", ratio_h=0.7,
                             accent=tc("accent"))
            btn.setFixedHeight(34)
            btn.setObjectName("popupDialogBtn")
            btn.clicked.connect(lambda bid=btn_id: self._on_btn_click(bid))
            btn_row.addWidget(btn)

        content_layout.addLayout(btn_row)
        main_layout.addWidget(content, 1)

    # ── 按钮回调 ──────────────────────────────────────────────────

    def _on_btn_click(self, btn_id: str):
        """按钮点击：记录标识符并关闭弹窗。"""
        self.clicked_button = btn_id
        if self._checkbox:
            self.checkbox_checked = self._checkbox.isChecked()
        self.accept()

    # ── 图标工具 ──────────────────────────────────────────────────

    def _icon_path(self) -> str:
        """获取当前类型对应的 SVG 图标完整路径。"""
        filename = _ICON_MAP.get(self._dialog_type, _ICON_MAP["info"])
        return os.path.join(_ICON_DIR, filename)

    # ── 主题 QSS ──────────────────────────────────────────────────

    def _load_theme_qss(self):
        """根据 config.json 的 theme 字段加载对应 popup_dialog.qss。"""
        try:
            config_path = get_config_path("config/config.json")
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            theme_name = config.get("theme", "catppuccin_mocha")
            qss_path = os.path.join(
                get_resource_root(), "style", "themes", theme_name, "popup_dialog.qss"
            )
            if os.path.exists(qss_path):
                with open(qss_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
        except Exception:
            pass

    # ── 尺寸自适应 ────────────────────────────────────────────────

    def _adjust_size(self):
        """根据消息文本和按钮宽度自适应弹窗的宽度和高度。

        宽度策略（clamp [420, 630]）：
            1. 取文本最长行像素宽度
            2. 取所有按钮总宽度（含 padding 和间距）
            3. 取两者较大者 + 图标区(64) + 间距(16) + 边距(48)
        高度策略：
            用 QFontMetrics.boundingRect 精确计算文本换行后实际高度，
            保证至少能容纳 64px 图标。
        """
        msg_label = self.findChild(QLabel, "popupMsgLabel")
        if not msg_label:
            self.setFixedWidth(420)
            self.setFixedHeight(200)
            return

        fm = msg_label.fontMetrics()
        text = self._message or ""

        # ── 宽度自适应 ──────────────────────────────────────────
        # 1) 文本最长行像素宽度
        lines = text.split("\n") if text else [""]
        max_line_w = max(fm.horizontalAdvance(line) for line in lines)

        # 2) 按钮总宽度（文字 + 左右 padding 40px + 间距 10px）
        btn_total = 0
        for btn_text, _ in self._buttons:
            btn_total += fm.horizontalAdvance(btn_text) + 40
        if len(self._buttons) > 1:
            btn_total += (len(self._buttons) - 1) * 10

        # 3) 理想内容宽度 → 弹窗总宽，clamp 到 [420, 630]
        ideal_content = max(max_line_w, btn_total)
        ideal_total = ideal_content + 64 + 16 + 48  # +图标+间距+左右边距
        dialog_w = max(420, min(630, ideal_total))
        self.setFixedWidth(dialog_w)

        # ── 高度自适应 ──────────────────────────────────────────
        avail_text_w = dialog_w - 24 * 2 - 64 - 16  # 文本可用宽度
        text_rect = fm.boundingRect(
            QRect(0, 0, max(avail_text_w, 1), 10000),
            int(Qt.TextWordWrap | Qt.AlignLeft),
            text,
        )
        text_h = text_rect.height()

        content_h = max(text_h, 64)  # 至少容纳图标高度
        # 标题栏42 + 内容上边距20 + 内容行 + 按钮前间距20 + 按钮行34 + 内容下边距20
        total_h = 42 + 20 + content_h + 20 + 34 + 20

        if self._checkbox_text:
            total_h += 14 + 22  # 复选框前间距 + 复选框估计高度

        self.setFixedHeight(max(total_h, 180))

    # ── 居中 ──────────────────────────────────────────────────────

    def _center_on_parent(self):
        """将弹窗居中于父窗口。"""
        if self.parent() and self.parent().isVisible():
            pg = self.parent().geometry()
            self.move(
                pg.x() + (pg.width() - self.width()) // 2,
                pg.y() + (pg.height() - self.height()) // 2,
            )
        else:
            screen = QApplication.primaryScreen().geometry()
            self.move(
                (screen.width() - self.width()) // 2,
                (screen.height() - self.height()) // 2,
            )

    # ── 窗口拖拽 ──────────────────────────────────────────────────

    def mousePressEvent(self, event):
        """标题栏区域拖拽移动窗口。"""
        if event.y() < 42 and event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if hasattr(self, '_drag_pos') and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if hasattr(self, '_drag_pos'):
            del self._drag_pos
        super().mouseReleaseEvent(event)
