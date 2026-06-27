"""自定义多选框 — StarCheckBox 通用组件。

替代 Qt 原生 QCheckBox，提供 SVG 图标渲染、动态着色、可调大小、主题自适应。
图标来源：icon/checkbox/ 目录下 2 个模板 SVG，通过 QSvgRenderer 渲染 + QPainter.CompositionMode 着色。

着色机制（v3.0）：
    - 模板 SVG 统一为白色（square.svg / checkmark_square.svg）
    - 渲染后通过 CompositionMode_SourceIn + fillRect 将白色像素替换为目标色
    - icon_scheme 支持："auto"（主题自适应）/ "white" / "black" / "#hex" / "accent_xxx"

API 兼容 Qt QCheckBox 的核心方法/信号：
    - isChecked() / setChecked(bool) / toggle()
    - toggled(bool) / stateChanged(int) / clicked()
    - setText(str) / text()

使用示例:
    from components.star_checkbox import StarCheckBox

    # 基本用法
    cb = StarCheckBox("同意用户协议", parent=self)
    cb.toggled.connect(lambda checked: print(f"选中: {checked}"))

    # 自定义大小
    cb = StarCheckBox("我是会员", parent=self, checkbox_size=28)

    # 初始选中
    cb = StarCheckBox("记住密码", parent=self, checked=True)

    # 配合 objectName 使用 QSS
    cb = StarCheckBox("选项", object_name="myCheckBox")
"""

import os
import json
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QApplication
from PyQt5.QtCore import Qt, QSize, QRectF, pyqtSignal, QEvent
from PyQt5.QtGui import QPixmap, QPainter, QFont, QColor
from PyQt5.QtSvg import QSvgRenderer


from workers.app_config.config_paths import get_config_path
from components.res_path import get_resource_root

# ── 图标路径 ─────────────────────────────────────────────────────────
_ICON_DIR = os.path.join(get_resource_root(), "icon", "checkbox")

# 图标模板文件名（v3.0：统一为白色模板，着色由代码动态完成）
_UNCHECKED_TEMPLATE = "square.svg"
_CHECKED_TEMPLATE = "checkmark_square.svg"


# ── 工具函数：获取模板路径 ──────────────────────
def _get_icon_path(filename: str) -> str:
    """获取图标文件完整路径。"""
    return os.path.join(_ICON_DIR, filename)


# ★ 模块级主题缓存：避免每个 StarCheckBox 实例重复读取文件
#   _THEME_CACHE = {"scheme": "white", "theme_type": "dark", "colors": {...}, "loaded": True}
_THEME_CACHE: dict = {"loaded": False}


def _load_theme_cache():
    """加载并缓存主题配置（config.json + theme.json）。
    仅首次调用时读文件，后续直接复用缓存。
    """
    global _THEME_CACHE
    if _THEME_CACHE.get("loaded"):
        return

    scheme = "white"
    theme_type = "dark"
    colors = {
        "text": "#cdd6f4", "subtext": "#a6adc8",
        "muted": "#6c7086", "overlay": "#313244",
    }
    try:
        config_path = get_config_path("config/config.json")
        if os.path.isfile(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            theme_name = config.get("theme", "catppuccin_mocha")
            theme_path = os.path.join(
                get_resource_root(), "style", "themes", theme_name, "theme.json"
            )
            if os.path.isfile(theme_path):
                with open(theme_path, "r", encoding="utf-8") as f:
                    theme = json.load(f)
                theme_type = theme.get("type", "dark")
                scheme = theme.get("icon_scheme", "white")
                theme_colors = theme.get("colors", {})
                if isinstance(theme_colors, dict):
                    colors.update(theme_colors)
    except Exception:
        pass

    _THEME_CACHE = {
        "scheme": scheme, "theme_type": theme_type,
        "colors": colors, "loaded": True,
    }


def _refresh_theme_cache():
    """主题切换后调用，强制重新加载缓存。"""
    global _THEME_CACHE
    _THEME_CACHE = {"loaded": False}


def _get_cached_color(key: str, fallback: str) -> str:
    """从缓存读取主题颜色。"""
    _load_theme_cache()
    return _THEME_CACHE.get("colors", {}).get(key, fallback)


# ── 颜色解析工具 ────────────────────────────────────────────────────

def _resolve_tint_color(scheme: str) -> QColor:
    """将 icon_scheme 字符串解析为 QColor 着色值。

    支持的值类型：
        "auto"            — 根据主题 type 自动选择（dark→white, light→black）
        "white" / "black" — 固定白/黑色
        "#rrggbb"         — 直接 hex 颜色（如 "#2E6DDE"）
        "accent_xxx"      — 主题配色中的对应键（如 "accent_blue" → colors["accent_blue"]）
        裸颜色键           — 直接查主题 colors 表（如 "text", "subtext"）

    返回: QColor 对象；解析失败返回白色。
    """
    _load_theme_cache()
    theme_type = _THEME_CACHE.get("theme_type", "dark")
    colors = _THEME_CACHE.get("colors", {})

    if scheme == "auto":
        # 深色主题用白色图标，浅色主题用黑色图标
        return QColor(0, 0, 0) if theme_type == "light" else QColor(255, 255, 255)

    if scheme == "white":
        return QColor(255, 255, 255)
    if scheme == "black":
        return QColor(0, 0, 0)

    # "accent_xxx" → 去掉前缀后查主题配色表
    if scheme.startswith("accent_") and scheme[7:] in colors:
        return QColor(colors[scheme[7:]])

    # "#xxxxxx" hex 颜色
    if scheme.startswith("#"):
        try:
            return QColor(scheme)
        except Exception:
            return QColor(255, 255, 255)

    # 裸键 → 查主题配色表
    if scheme in colors:
        return QColor(colors[scheme])

    # 末次回退
    return QColor(255, 255, 255)


# ── SVG 渲染工具 ────────────────────────────────────────────────────

def _render_svg(svg_path: str, size: QSize, tint_color: QColor | None = None) -> QPixmap:
    """将 SVG 模板渲染为指定尺寸的 QPixmap，动态着色，支持 HiDPI。

    Args:
        svg_path: SVG 文件路径
        size: 目标逻辑尺寸
        tint_color: 着色目标色（None=不渲染）；始终应用（白色也是安全恒等变换）

    着色原理：CompositionMode_SourceIn 用 tint_color 填充，
              白色区域→目标色，透明区域→保持透明，半透明→目标色×alpha
    """
    if not svg_path or not os.path.isfile(svg_path):
        pix = QPixmap(size)
        pix.fill(Qt.transparent)
        return pix

    painter = None
    try:
        app = QApplication.instance()
        pixel_ratio = app.devicePixelRatio() if app else 1.0
        real_size = QSize(int(size.width() * pixel_ratio), int(size.height() * pixel_ratio))

        pix = QPixmap(real_size)
        pix.setDevicePixelRatio(pixel_ratio)
        pix.fill(Qt.transparent)

        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        renderer = QSvgRenderer(svg_path)
        if renderer.isValid():
            renderer.render(painter, QRectF(0, 0, real_size.width(), real_size.height()))

        # ★ v3.0.1：始终执行着色（消除 QColor 相等性比较的不确定性）
        # 白色模板 + 白色着色 = 无变化（SourceIn 恒等变换），安全无副作用
        if tint_color is not None:
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(
                QRectF(0, 0, real_size.width(), real_size.height()), tint_color
            )

        return pix
    except Exception:
        pix = QPixmap(size)
        pix.fill(Qt.transparent)
        return pix
    finally:
        if painter is not None:
            try:
                painter.end()
            except Exception:
                pass


def _apply_opacity(pixmap: QPixmap, opacity: float) -> QPixmap:
    """对 QPixmap 应用全局透明度。"""
    result = QPixmap(pixmap.size())
    result.setDevicePixelRatio(pixmap.devicePixelRatio())
    result.fill(Qt.transparent)
    p = QPainter(result)
    p.setOpacity(opacity)
    p.drawPixmap(0, 0, pixmap)
    p.end()
    return result


# ═══════════════════════════════════════════════════════════════════════
#  StarCheckBox 主体
# ═══════════════════════════════════════════════════════════════════════

class StarCheckBox(QWidget):
    """自定义多选框组件 — 替代 Qt QCheckBox。

    特性:
        - SVG 模板渲染 + 动态着色（v3.0）：无需多套色系文件
        - 可调图标大小（setCheckboxSize），文字字号自动跟随
        - 四态交互：Normal / Hover / Checked / Disabled
        - 主题跟随：根据 theme.json icon_scheme 动态计算图标色
        - API 兼容 QCheckBox 核心方法/信号

    Attributes:
        checked: 选中状态（可通过 property 读写）
        text: 标签文本（可通过 property 读写）
        checkbox_size: 图标像素大小（可通过 property 读写）

    Signals:
        toggled(bool): 状态翻转时发射，参数为新状态
        stateChanged(int): 状态改变时发射，0=未选中 2=选中（兼容 QCheckBox）
        clicked(): 点击时发射
    """

    # ── 信号 ──────────────────────────────────────────────────
    toggled = pyqtSignal(bool)
    stateChanged = pyqtSignal(int)
    clicked = pyqtSignal()

    def __init__(self, text: str = "", parent=None,
                 checked: bool = False, checkbox_size: int = 20,
                 object_name: str = "", icon_scheme: str = "auto"):
        """创建多选框。

        Args:
            text: 标签文字
            parent: 父控件
            checked: 初始选中状态
            checkbox_size: 图标像素大小（最小 12px）
            object_name: QSS objectName（可选）
            icon_scheme: 图标色系。支持以下值：
                "auto"          — 根据主题 type 自动选择（dark→white, light→black）
                "white"         — 强制白色
                "black"         — 强制黑色
                "#hex"          — 直接 hex 颜色（如 "#2E6DDE"）
                "accent_xxx"    — 使用主题配色（如 "accent_blue"）
                裸颜色键         — 从主题 colors 查表（如 "text"）
        """
        super().__init__(parent)
        self._checked = bool(checked)
        self._checkbox_size = max(12, checkbox_size)
        self._hovered = False
        self._enabled = True
        self._handling_style_change = False  # ★ 重入 guard，防止 changeEvent 无限递归
        self._cached_pix = {}  # {(checked, size, tint_hex): QPixmap}
        self._external_font: QFont | None = None
        self._theme_type: str = "dark"
        self._tint_color: QColor = QColor(255, 255, 255)
        self._icon_scheme: str = icon_scheme  # ★ v3.0：存储原始 scheme 字符串用于重新解析

        # 图标模板路径（统一引用）
        self._icon_unchecked = _get_icon_path(_UNCHECKED_TEMPLATE)
        self._icon_checked = _get_icon_path(_CHECKED_TEMPLATE)

        if object_name:
            self.setObjectName(object_name)
        else:
            self.setObjectName("starCheckBox")

        self.setAttribute(Qt.WA_StyledBackground, True)

        self._resolve_icon_color()  # ★ v3.0：解析 icon_scheme → tint_color
        self._setup_ui(text)
        self._apply_text_color()
        self._update_icon()

    # ── UI 构建 ──────────────────────────────────────────────

    def _setup_ui(self, text: str):
        """构建水平布局：[图标] [文字]"""
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # 图标标签
        icon_size = self._checkbox_size + 4
        self._icon_label = QLabel()
        self._icon_label.setObjectName("starCheckIcon")
        self._icon_label.setFixedSize(icon_size, icon_size)
        self._icon_label.setAlignment(Qt.AlignCenter)

        # 文字标签
        self._text_label = QLabel(text)
        self._text_label.setObjectName("starCheckText")
        self._text_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._text_label.setWordWrap(False)
        self._apply_font_size()

        layout.addWidget(self._icon_label)
        layout.addWidget(self._text_label, 1)

    # ── 字号计算 ────────────────────────────────────────────

    def _apply_font_size(self):
        """根据图标大小自动计算文字字号（下限 10px）。"""
        if self._external_font is not None:
            self._text_label.setFont(self._external_font)
        else:
            font_size = max(10, int(self._checkbox_size * 0.7))
            font = QFont("Microsoft YaHei", font_size)
            self._text_label.setFont(font)

    def setFont(self, font: QFont):
        """覆盖 QWidget.setFont，同步设置文字标签字体。"""
        self._external_font = QFont(font)
        self._text_label.setFont(self._external_font)
        super().setFont(font)

    def font(self) -> QFont:
        """返回文字标签当前使用的字体。"""
        return self._text_label.font()

    def resetFont(self):
        """恢复文字字号由 checkbox_size 自动计算。"""
        self._external_font = None
        self._apply_font_size()

    # ── 图标更新 ────────────────────────────────────────────

    def _resolve_icon_color(self):
        """★ v3.0：将 icon_scheme 解析为 QColor 着色值。

        支持"auto"/"white"/"black"/"#hex"/"accent_xxx"/裸颜色键。
        同时从缓存更新 _theme_type。
        """
        scheme = self._icon_scheme
        self._tint_color = _resolve_tint_color(scheme)

        # 补充更新 theme_type（_resolve_tint_color 内部已加载缓存）
        _load_theme_cache()
        self._theme_type = _THEME_CACHE.get("theme_type", "dark")

    def _update_icon(self):
        """刷新图标显示（含 HiDPI 缓存 + 着色）。
        未选中显示方框（subtext 色），选中显示勾选方框（text 色）。
        """
        size = QSize(self._checkbox_size, self._checkbox_size)
        if not self._checked:
            # 未选中：方框 + subtext 色
            sub_hex = self._get_theme_color("subtext", "#a6adc8")
            cache_key = (False, self._checkbox_size, sub_hex)
            if cache_key not in self._cached_pix:
                sub_color = QColor(sub_hex)
                raw = _render_svg(self._icon_unchecked, size, sub_color)
                self._cached_pix[cache_key] = raw
            pix = self._cached_pix[cache_key]
        else:
            # 选中：勾选框 + text 色
            tint_hex = self._tint_color.name(QColor.HexArgb)
            cache_key = (True, self._checkbox_size, tint_hex)
            if cache_key not in self._cached_pix:
                raw = _render_svg(self._icon_checked, size, self._tint_color)
                self._cached_pix[cache_key] = raw
            pix = self._cached_pix[cache_key]

        if not self._enabled:
            pix = _apply_opacity(pix, 0.4)

        self._icon_label.setPixmap(pix)

    def _invalidate_cache(self):
        """清空图标缓存（主题切换/tint 变更时调用）。"""
        self._cached_pix.clear()

    # ── 文字颜色 ────────────────────────────────────────────

    def _apply_text_color(self):
        """根据 checked / enabled 状态设置文字颜色。"""
        if not self._checked:
            color = self._get_theme_color("subtext", "#a6adc8")
        else:
            color = self._get_theme_color("text", "#cdd6f4")

        if not self._enabled:
            color = self._get_theme_color("muted", "#6c7086")

        self._text_label.setStyleSheet(
            f"QLabel {{ color: {color}; }}"
        )

    def _get_theme_color(self, key: str, fallback: str) -> str:
        """从模块级主题缓存读取配色。"""
        return _get_cached_color(key, fallback)

    # ── 鼠标事件 ────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._enabled:
            self.toggle()
            self.clicked.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        if self._enabled:
            self._hovered = True
            self._apply_background("hover")
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._hovered:
            self._hovered = False
            self._apply_background("normal")
        super().leaveEvent(event)

    def _apply_background(self, state: str):
        """设置 hover/normal 背景色（内联 stylesheet）。
        normal 状态显式设为透明，防止父控件 QSS 透传产生色块。
        """
        obj_name = self.objectName()
        if state == "hover" and self._enabled:
            bg = self._get_theme_color("overlay", "#313244")
            self.setStyleSheet(
                f"#{obj_name} {{ background-color: {bg}; border-radius: 4px; }}"
                f" QLabel {{ background: transparent; }}"
            )
        else:
            self.setStyleSheet(
                f"#{obj_name} {{ background-color: transparent; }}"
                f" QLabel {{ background: transparent; }}"
            )

    # ── 公开 API ────────────────────────────────────────────

    def isChecked(self) -> bool:
        """返回当前选中状态。"""
        return self._checked

    def setChecked(self, checked: bool):
        """设置选中状态，若状态变化则发射 toggled / stateChanged 信号。"""
        checked = bool(checked)
        if self._checked != checked:
            self._checked = checked
            self._update_icon()
            self._apply_text_color()
            self.toggled.emit(self._checked)
            self.stateChanged.emit(2 if self._checked else 0)

    def toggle(self):
        """翻转选中状态。"""
        self.setChecked(not self._checked)

    def setText(self, text: str):
        """设置标签文字。"""
        self._text_label.setText(text)

    def text(self) -> str:
        """获取标签文字。"""
        return self._text_label.text()

    def setCheckboxSize(self, size: int):
        """设置图标像素大小（≥12px），文字字号自动跟随。"""
        size = max(12, size)
        if self._checkbox_size != size:
            self._checkbox_size = size
            icon_size = size + 4
            self._icon_label.setFixedSize(icon_size, icon_size)
            self._apply_font_size()
            self._invalidate_cache()
            self._update_icon()

    def checkboxSize(self) -> int:
        """获取当前图标像素大小。"""
        return self._checkbox_size

    def setEnabled(self, enabled: bool):
        """启用/禁用控件。"""
        self._enabled = enabled
        if not enabled:
            self._hovered = False
            self._apply_background("normal")
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ForbiddenCursor)
        self._update_icon()
        self._apply_text_color()
        super().setEnabled(enabled)

    # ★ v3.0：公开 icon_scheme 读写
    def iconScheme(self) -> str:
        """获取当前 icon_scheme 值。"""
        return self._icon_scheme

    def setIconScheme(self, scheme: str):
        """动态修改 icon_scheme 并立即刷新图标。

        Args:
            scheme: 与构造参数 icon_scheme 相同格式
        """
        if self._icon_scheme != scheme:
            self._icon_scheme = scheme
            self._resolve_icon_color()
            self._invalidate_cache()
            self._update_icon()

    # ── 主题热切换 ──────────────────────────────────────────

    def changeEvent(self, event):
        """监听全局样式变化（主题切换时 app.setStyleSheet 触发）。"""
        if event.type() == QEvent.StyleChange:
            if self._handling_style_change:
                return
            self._handling_style_change = True
            try:
                _refresh_theme_cache()
                self._resolve_icon_color()
                self._invalidate_cache()
                self._update_icon()
                self._apply_text_color()
                if self._hovered:
                    self._apply_background("hover")
                else:
                    self._apply_background("normal")
            finally:
                self._handling_style_change = False
        super().changeEvent(event)

    def refresh_theme(self):
        """主题切换后调用：刷新缓存、重新解析颜色、清空图标缓存、刷新 UI。"""
        _refresh_theme_cache()
        self._resolve_icon_color()
        self._invalidate_cache()
        self._update_icon()
        self._apply_text_color()
        self._apply_background("normal")

    # ── property 快捷访问 ────────────────────────────────────

    def _get_checked(self) -> bool:
        return self._checked

    def _set_checked(self, value: bool):
        self.setChecked(value)

    checked = property(_get_checked, _set_checked,
                       doc="选中状态（可读写 property）")

    def _get_text(self) -> str:
        return self.text()

    def _set_text(self, value: str):
        self.setText(value)

    text_prop = property(_get_text, _set_text,
                         doc="标签文本（可读写 property）")

    def _get_cb_size(self) -> int:
        return self._checkbox_size

    def _set_cb_size(self, value: int):
        self.setCheckboxSize(value)

    checkbox_size = property(_get_cb_size, _set_cb_size,
                             doc="图标像素大小（可读写 property）")

    # ── Qt 信号兼容方法 ─────────────────────────────────────

    def setChecked_(self, checked: bool):
        """setChecked 的别名。"""
        self.setChecked(checked)

    def isChecked_(self) -> bool:
        """isChecked 的别名。"""
        return self.isChecked()
