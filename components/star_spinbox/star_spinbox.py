"""自定义数字输入框 — StarSpinBox / StarDoubleSpinBox 通用组件。

替代 Qt 原生 QSpinBox / QDoubleSpinBox，提供：
    - SVG 图标渲染 + 动态着色（同 StarCheckBox v3.0 着色管线）
    - 三种布局模式："right"(右竖) / "split"(左右分) / "embedded"(内嵌)
    - 长按按钮自动重复（400ms 延迟 + 80ms 间隔）
    - 鼠标滚轮步进 / 键盘上下键步进
    - 前缀/后缀文本显示
    - HiDPI 图标缓存 + 主题热切换

使用示例:
    from components.star_spinbox import StarSpinBox, StarDoubleSpinBox

    # 基本用法（模式 A 默认）
    spin = StarSpinBox(value=42, max_value=100, suffix=" 人")

    # 模式 B 左右分离按钮
    spin = StarSpinBox(value=50, step=5, button_layout="split")

    # 模式 C 紧凑嵌入
    spin = StarSpinBox(value=10, max_value=99, button_layout="embedded")

    # 双精度浮点
    spin = StarDoubleSpinBox(value=0.7, min_value=0.0, max_value=2.0, step=0.1)

    # 动态切换布局
    spin.setButtonLayout("split")
"""

import os
import json
from PyQt5.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton, QApplication,
)
from PyQt5.QtCore import (
    Qt, QSize, QRectF, pyqtSignal, QTimer, QEvent, QRegExp,
)
from PyQt5.QtGui import (
    QPixmap, QPainter, QFont, QColor, QIcon, QRegExpValidator, QIntValidator,
    QDoubleValidator, QKeyEvent,
)
from PyQt5.QtSvg import QSvgRenderer

# ═══════════════════════════════════════════════════════════════════════
#  模块级常量 & 工具函数
# ═══════════════════════════════════════════════════════════════════════

from workers.app_config.config_paths import get_config_path
from components.res_path import get_resource_root

_SPINBOX_ICON_DIR = os.path.join(get_resource_root(), "icon", "spinbox")

# 图标文件名（白色模板 — 用于动态着色）
_UP_TEMPLATE = "arrowtriangle_up_fill_white.svg"
_DOWN_TEMPLATE = "arrowtriangle_down_fill_white.svg"
# 黑色后备（浅色主题直接使用，无需着色）
_UP_BLACK = "arrowtriangle_up_fill_black.svg"
_DOWN_BLACK = "arrowtriangle_down_fill_black.svg"

# ★ 模块级主题缓存
_THEME_CACHE: dict = {"loaded": False}


def _load_theme_cache():
    """加载并缓存主题配置（config.json + theme.json）。"""
    global _THEME_CACHE
    if _THEME_CACHE.get("loaded"):
        return

    scheme = "white"
    theme_type = "dark"
    colors = {
        "text": "#cdd6f4", "subtext": "#a6adc8",
        "muted": "#6c7086", "overlay": "#313244",
        "surface": "#181825", "base": "#1e1e2e",
        "accent_purple": "#2E6DDE",
    }
    try:
        config_path = get_config_path("config/config.json")
        if os.path.isfile(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            theme_name = config.get("theme", "catppuccin_mocha")
            theme_path = os.path.join(get_resource_root(), "style", "themes", theme_name, "theme.json")
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


def _resolve_tint_color(scheme: str) -> QColor:
    """将 icon_scheme 解析为 QColor 着色值（同 StarCheckBox 逻辑）。

    支持："auto" / "white" / "black" / "#hex" / "accent_xxx" / 裸颜色键
    """
    _load_theme_cache()
    theme_type = _THEME_CACHE.get("theme_type", "dark")
    colors = _THEME_CACHE.get("colors", {})

    if scheme == "auto":
        return QColor(0, 0, 0) if theme_type == "light" else QColor(255, 255, 255)
    if scheme == "white":
        return QColor(255, 255, 255)
    if scheme == "black":
        return QColor(0, 0, 0)
    if scheme.startswith("accent_") and scheme[7:] in colors:
        return QColor(colors[scheme[7:]])
    if scheme.startswith("#"):
        try:
            return QColor(scheme)
        except Exception:
            return QColor(255, 255, 255)
    if scheme in colors:
        return QColor(colors[scheme])

    return QColor(255, 255, 255)


def _get_icon_path(is_up: bool, use_black: bool = False) -> str:
    """获取图标文件完整路径。

    Args:
        is_up: True=上箭头, False=下箭头
        use_black: True=黑色模板 (浅色主题), False=白色模板 (深色主题+着色)

    Returns: SVG 文件绝对路径
    """
    subdir = "black" if use_black else "white"
    filename = _UP_BLACK if (use_black and is_up) else (
        _DOWN_BLACK if (use_black and not is_up) else (
            _UP_TEMPLATE if is_up else _DOWN_TEMPLATE
        )
    )
    return os.path.join(_SPINBOX_ICON_DIR, subdir, filename)


# ── SVG 渲染工具 ────────────────────────────────────────────────────

def _render_svg_icon(svg_path: str, size: int, tint_color: QColor | None = None) -> QPixmap:
    """将 SVG 模板渲染为指定尺寸的 QPixmap，动态着色，支持 HiDPI。

    Args:
        svg_path: SVG 文件路径
        size: 目标逻辑尺寸（像素）
        tint_color: 着色目标色（None=不渲染）；始终应用

    Returns: QPixmap
    """
    if not svg_path or not os.path.isfile(svg_path):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        return pix

    painter = None
    try:
        app = QApplication.instance()
        pixel_ratio = app.devicePixelRatio() if app else 1.0
        real_size = int(size * pixel_ratio)

        pix = QPixmap(real_size, real_size)
        pix.setDevicePixelRatio(pixel_ratio)
        pix.fill(Qt.transparent)

        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        renderer = QSvgRenderer(svg_path)
        if renderer.isValid():
            renderer.render(painter, QRectF(0, 0, real_size, real_size))

        if tint_color is not None:
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(QRectF(0, 0, real_size, real_size), tint_color)

        return pix
    except Exception:
        pix = QPixmap(size, size)
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
#  StarSpinBox 基类
# ═══════════════════════════════════════════════════════════════════════

class _BaseSpinBox(QWidget):
    """自定义数字输入框基类 — 三种布局模式 + SVG 图标 + 主题自适应。

    ★ 不直接使用，请用 StarSpinBox (int) 或 StarDoubleSpinBox (double)。

    Signals:
        valueChanged: 值变化时发射（int/float 超载）
        editingFinished: 编辑完成时发射
    """

    valueChanged = pyqtSignal(object)  # int 或 float
    editingFinished = pyqtSignal()

    VALID_LAYOUTS = ("right", "split", "embedded")

    def __init__(self, parent=None, value=None, min_value=0, max_value=99, step=1,
                 prefix="", suffix="", button_layout="right",
                 spin_height=32, button_width=22, editable=True,
                 icon_scheme="auto", object_name="",
                 text_align="left", font_size=None):
        super().__init__(parent)

        # 参数校验
        if button_layout not in self.VALID_LAYOUTS:
            button_layout = "right"
        spin_height = max(24, spin_height)
        button_width = max(16, button_width)
        if text_align not in ("left", "center", "right"):
            text_align = "left"

        # 状态存储
        self._value = value if value is not None else min_value
        self._min_value = min_value
        self._max_value = max_value
        self._step = step
        self._prefix = prefix
        self._suffix = suffix
        self._button_layout = button_layout
        self._spin_height = spin_height
        self._button_width = button_width
        self._editable = editable
        self._icon_scheme = icon_scheme
        self._object_name = object_name if object_name else "starSpinBox"
        self._text_align = text_align
        self._font_size = font_size  # None=自动, int=固定
        self._enabled = True
        self._hovered = False
        self._focused = False

        # 长按自动重复
        self._repeat_timer = QTimer(self)
        self._repeat_timer.setInterval(80)
        self._repeat_timer.timeout.connect(self._on_repeat_step)
        self._repeat_direction = 0  # 1=up, -1=down
        self._repeat_initial_delay = None  # QTimer.singleShot 引用

        # 图标缓存 & 着色
        self._tint_color: QColor = QColor(255, 255, 255)
        self._theme_type: str = "dark"
        self._cached_icons: dict = {}  # {(is_up, size, tint_hex): QPixmap}

        self._setup_theme()
        self._setup_ui()
        self._update_display()

        # 监视钩子 — 模块加载
        self._hook_log("function_watch", "StarSpinBox.__init__",
                        f"layout={button_layout} min={min_value} max={max_value}")

    # ── 监视钩子 ──────────────────────────────────────────────────

    def _hook_log(self, hook_type: str, func_name: str, detail: str = ""):
        """向日志系统投递监视钩子 (静默失败)。"""
        try:
            parent = self.window()
            if hasattr(parent, "_log_client") and parent._log_client:
                parent._log_client.monitor(
                    category=hook_type,
                    source=f"StarSpinBox.{func_name}",
                    detail=detail,
                )
        except Exception:
            pass

    # ── 主题解析 ──────────────────────────────────────────────────

    def _setup_theme(self):
        """解析主题配置，确定图标着色方案。"""
        _load_theme_cache()
        self._theme_type = _THEME_CACHE.get("theme_type", "dark")
        self._tint_color = _resolve_tint_color(self._icon_scheme)

    def _is_black_icon(self) -> bool:
        """浅色主题且 icon_scheme 为 auto 时，直接使用黑色模板（无需着色）。"""
        # ★ 统一使用白色模板 + 动态着色，保证一致性
        return False

    # ── UI 构建 ──────────────────────────────────────────────────

    def _setup_ui(self):
        """构建 SpinBox 主体 UI。"""
        self.setObjectName("starSpinBoxWrapper")

        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # 外框 (QSS 圆角/边框在此)
        self._spin_outer = QFrame()
        self._spin_outer.setObjectName(self._object_name)
        self._spin_outer.setFixedHeight(self._spin_height)

        self._rebuild_inner_layout()

        outer_layout.addWidget(self._spin_outer)

    def _rebuild_inner_layout(self):
        """根据 button_layout 重建内部布局。"""
        # 销毁旧布局
        old_layout = self._spin_outer.layout()
        if old_layout is not None:
            while old_layout.count():
                item = old_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.setParent(None)
            QWidget().setLayout(old_layout)  # 释放旧布局

        # 创建控件
        self._line_edit = QLineEdit()
        self._line_edit.setObjectName("starSpinEdit")
        self._apply_text_alignment()
        self._line_edit.setReadOnly(not self._editable)
        self._line_edit.installEventFilter(self)
        self._line_edit.editingFinished.connect(self._on_editing_finished)

        # 设置验证器
        self._setup_validator()

        # 字体大小
        self._apply_font_size()

        # 图标大小
        icon_size = max(8, int(self._spin_height * 0.5))

        # 上按钮
        self._up_btn = self._create_spin_button(is_up=True, icon_size=icon_size)
        # 下按钮
        self._down_btn = self._create_spin_button(is_up=False, icon_size=icon_size)

        # ★ 根据布局模式排列
        layout = QHBoxLayout(self._spin_outer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if self._button_layout == "right":
            # 模式A: [编辑区 | ▲▼竖直]
            layout.addWidget(self._line_edit, 1)
            btn_container = QWidget()
            btn_container.setFixedWidth(self._button_width)
            btn_vbox = QVBoxLayout(btn_container)
            btn_vbox.setContentsMargins(0, 0, 0, 0)
            btn_vbox.setSpacing(0)
            self._up_btn.setFixedSize(self._button_width, self._spin_height // 2)
            self._down_btn.setFixedSize(self._button_width, self._spin_height - self._spin_height // 2)
            btn_vbox.addWidget(self._up_btn)
            btn_vbox.addWidget(self._down_btn)
            layout.addWidget(btn_container)

        elif self._button_layout == "split":
            # 模式B: [▼ | 编辑区 | ▲]
            self._down_btn.setFixedSize(self._button_width, self._spin_height)
            self._up_btn.setFixedSize(self._button_width, self._spin_height)
            layout.addWidget(self._down_btn)
            layout.addWidget(self._line_edit, 1)
            layout.addWidget(self._up_btn)

        elif self._button_layout == "embedded":
            # 模式C: [编辑区 | ▲▼内嵌]
            layout.addWidget(self._line_edit, 1)
            btn_container = QWidget()
            btn_container.setFixedWidth(self._button_width)
            btn_container.setStyleSheet("background: transparent;")
            btn_vbox = QVBoxLayout(btn_container)
            btn_vbox.setContentsMargins(0, 1, 1, 1)  # 微内边距
            btn_vbox.setSpacing(0)
            up_h = self._spin_height // 2
            down_h = self._spin_height - up_h
            self._up_btn.setFixedSize(self._button_width, up_h)
            self._down_btn.setFixedSize(self._button_width, down_h)
            btn_vbox.addWidget(self._up_btn)
            btn_vbox.addWidget(self._down_btn)
            layout.addWidget(btn_container)

        self._update_icons()
        self._apply_button_state()

    def _create_spin_button(self, is_up: bool, icon_size: int) -> QPushButton:
        """创建一个箭头按钮。"""
        btn = QPushButton()
        btn.setObjectName("starSpinUpBtn" if is_up else "starSpinDownBtn")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setIconSize(QSize(icon_size, icon_size))

        # 鼠标事件
        btn.pressed.connect(lambda: self._on_btn_pressed(1 if is_up else -1))
        btn.released.connect(self._on_btn_released)

        return btn

    def _setup_validator(self):
        """子类重写以设置数值验证器。"""
        pass

    # ── 图标更新 ──────────────────────────────────────────────────

    def _update_icons(self):
        """刷新上下按钮的 SVG 图标。"""
        icon_size = max(8, int(self._spin_height * 0.5))
        self._up_btn.setIconSize(QSize(icon_size, icon_size))
        self._down_btn.setIconSize(QSize(icon_size, icon_size))

        tint_hex = self._tint_color.name(QColor.HexArgb)

        for is_up, btn in [(True, self._up_btn), (False, self._down_btn)]:
            cache_key = (is_up, icon_size, tint_hex)
            if cache_key not in self._cached_icons:
                svg_path = _get_icon_path(is_up=is_up, use_black=self._is_black_icon())
                pix = _render_svg_icon(svg_path, icon_size, self._tint_color)
                if not self._enabled:
                    pix = _apply_opacity(pix, 0.4)
                self._cached_icons[cache_key] = pix

            btn.setIcon(QIcon(self._cached_icons[cache_key]))

    def _invalidate_icon_cache(self):
        """清空图标缓存。"""
        self._cached_icons.clear()

    # ── 按钮事件 ──────────────────────────────────────────────────

    def _on_btn_pressed(self, direction: int):
        """按钮按下：立即执行一步，启动长按计时。"""
        if not self._enabled:
            return
        self._step_value(direction)
        self._repeat_direction = direction
        # 400ms 后开始重复
        if self._repeat_initial_delay is not None:
            self._repeat_initial_delay.stop()
        self._repeat_initial_delay = QTimer.singleShot(400, self._start_repeat)

    def _on_btn_released(self):
        """按钮释放：停止重复。"""
        self._repeat_direction = 0
        self._repeat_timer.stop()
        if self._repeat_initial_delay is not None:
            self._repeat_initial_delay.stop()
            self._repeat_initial_delay = None

    def _start_repeat(self):
        """启动连续重复。"""
        if self._repeat_direction != 0:
            self._repeat_timer.start()

    def _on_repeat_step(self):
        """重复步进。"""
        if self._repeat_direction != 0 and self._enabled:
            self._step_value(self._repeat_direction)

    def _step_value(self, direction: int):
        """执行一次步进 (direction: 1=增, -1=减)。"""
        new_val = self._clamp_value(self._value + direction * self._step)
        if new_val != self._value:
            self._value = new_val
            self._update_display()
            self._emit_value_changed()
            self._hook_log("variable_watch", "step_value",
                           f"direction={direction} new_value={self._value}")

    # ── 值操作 ──────────────────────────────────────────────────

    def _clamp_value(self, val):
        """将值限制在 [min, max] 范围内。子类重写以处理精度。"""
        return max(self._min_value, min(self._max_value, val))

    def _update_display(self):
        """更新编辑框显示（含前后缀）。"""
        text = f"{self._prefix}{self._format_value()}{self._suffix}"
        self._line_edit.setText(text)

    def _format_value(self):
        """格式化值用于显示。子类重写。"""
        return str(self._value)

    def _parse_display_text(self, text: str):
        """从显示文本解析数值。子类重写。"""
        # 去除前后缀
        t = text
        if self._prefix and t.startswith(self._prefix):
            t = t[len(self._prefix):]
        if self._suffix and t.endswith(self._suffix):
            t = t[:-len(self._suffix)]
        return t.strip()

    def _on_editing_finished(self):
        """编辑完成（回车/失焦），解析并校验值。"""
        raw = self._line_edit.text()
        parsed = self._parse_display_text(raw)
        try:
            val = self._convert_text(parsed)
            clamped = self._clamp_value(val)
            if clamped != self._value:
                self._value = clamped
                self._emit_value_changed()
                self._hook_log("variable_watch", "editing_finished",
                               f"new_value={self._value}")
        except (ValueError, TypeError):
            pass
        self._update_display()
        self.editingFinished.emit()

    def _convert_text(self, text: str):
        """将文本转换为数值。子类重写。"""
        return int(text)

    def _emit_value_changed(self):
        """发射 valueChanged 信号（含超载）。"""
        self.valueChanged.emit(self._value)

    # ── 键盘事件 ──────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        """过滤 line_edit 的键盘/滚轮事件。"""
        if obj is self._line_edit:
            if event.type() == QEvent.KeyPress:
                return self._handle_key_press(event)
            elif event.type() == QEvent.Wheel:
                return self._handle_wheel(event)
            elif event.type() == QEvent.FocusIn:
                self._focused = True
                self._apply_outer_style()
            elif event.type() == QEvent.FocusOut:
                self._focused = False
                self._apply_outer_style()
        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        """顶层滚轮事件（兜底）。"""
        if self._enabled and self._line_edit.underMouse():
            delta = event.angleDelta().y()
            if delta > 0:
                self._step_value(1)
            elif delta < 0:
                self._step_value(-1)
            event.accept()
            return
        super().wheelEvent(event)

    def _handle_key_press(self, event: QKeyEvent) -> bool:
        """处理键盘按键。"""
        key = event.key()
        if key == Qt.Key_Up:
            self._step_value(1)
            return True
        elif key == Qt.Key_Down:
            self._step_value(-1)
            return True
        elif key == Qt.Key_PageUp:
            self._step_value(10)
            return True
        elif key == Qt.Key_PageDown:
            self._step_value(-10)
            return True
        elif key == Qt.Key_Escape:
            self._update_display()
            self._line_edit.clearFocus()
            return True
        return False

    def _handle_wheel(self, event) -> bool:
        """处理鼠标滚轮。"""
        if not self._enabled:
            return False
        delta = event.angleDelta().y()
        if delta > 0:
            self._step_value(1)
        elif delta < 0:
            self._step_value(-1)
        event.accept()
        return True

    # ── 鼠标事件 (hover 效果) ────────────────────────────────────

    def enterEvent(self, event):
        if self._enabled:
            self._hovered = True
            self._apply_outer_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._hovered:
            self._hovered = False
            self._apply_outer_style()
            # 确保按钮释放
            if self._repeat_direction != 0:
                self._on_btn_released()
        super().leaveEvent(event)

    def _apply_outer_style(self):
        """根据 hover/focus/disabled 状态设置外框内联样式。"""
        if not self._enabled:
            return
        obj_name = self._spin_outer.objectName()
        if self._focused or self._hovered:
            accent = _get_cached_color("accent_purple", "#2E6DDE")
            self._spin_outer.setStyleSheet(
                f"#{obj_name} {{ border: 1px solid {accent}; }}"
            )
        else:
            self._spin_outer.setStyleSheet("")
            try:
                self._spin_outer.style().unpolish(self._spin_outer)
                self._spin_outer.style().polish(self._spin_outer)
            except Exception:
                pass

    def _apply_button_state(self):
        """更新按钮启用/禁用状态。"""
        self._up_btn.setEnabled(self._enabled)
        self._down_btn.setEnabled(self._enabled)

    # ── 公开 API ──────────────────────────────────────────────────

    def value(self):
        """获取当前值。"""
        return self._value

    def setValue(self, val):
        """设置值 (自动 clamp)。"""
        clamped = self._clamp_value(val)
        if clamped != self._value:
            self._value = clamped
            self._update_display()
            self._emit_value_changed()
            self._hook_log("variable_watch", "setValue", f"value={self._value}")

    def setRange(self, min_val, max_val):
        """设置数值范围。"""
        self._min_value = min_val
        self._max_value = max_val
        old = self._value
        self._value = self._clamp_value(self._value)
        if old != self._value:
            self._update_display()
            self._emit_value_changed()
        self._setup_validator()
        self._hook_log("function_watch", "setRange", f"min={min_val} max={max_val}")

    def setStep(self, step):
        """设置步长。"""
        self._step = step
        self._hook_log("function_watch", "setStep", f"step={step}")

    def setPrefix(self, text: str):
        """设置前缀。"""
        self._prefix = text
        self._update_display()

    def setSuffix(self, text: str):
        """设置后缀。"""
        self._suffix = text
        self._update_display()

    def setButtonLayout(self, mode: str):
        """动态切换布局模式 ("right"/"split"/"embedded")。"""
        if mode not in self.VALID_LAYOUTS:
            return
        if mode == self._button_layout:
            return
        self._button_layout = mode
        self._rebuild_inner_layout()
        self._hook_log("variable_watch", "setButtonLayout", f"mode={mode}")

    def buttonLayout(self) -> str:
        """获取当前布局模式。"""
        return self._button_layout

    def setSpinHeight(self, h: int):
        """调整整体高度。"""
        h = max(24, h)
        if h == self._spin_height:
            return
        self._spin_height = h
        self._spin_outer.setFixedHeight(h)
        if self._font_size is None:
            self._apply_font_size()
        self._invalidate_icon_cache()
        self._rebuild_inner_layout()

    def setButtonWidth(self, w: int):
        """调整按钮宽度。"""
        w = max(16, w)
        if w == self._button_width:
            return
        self._button_width = w
        self._rebuild_inner_layout()

    def setEditable(self, editable: bool):
        """切换可编辑/只读。"""
        self._editable = editable
        self._line_edit.setReadOnly(not editable)

    def setIconScheme(self, scheme: str):
        """动态修改图标色系。"""
        if self._icon_scheme != scheme:
            self._icon_scheme = scheme
            self._tint_color = _resolve_tint_color(scheme)
            self._invalidate_icon_cache()
            self._update_icons()

    def setEnabled(self, enabled: bool):
        """启用/禁用控件。"""
        self._enabled = enabled
        self._apply_button_state()
        self._line_edit.setReadOnly(not enabled if not self._editable else not self._editable)
        if not enabled:
            self._hovered = False
            self._focused = False
            self._apply_outer_style()
        self._invalidate_icon_cache()
        self._update_icons()
        super().setEnabled(enabled)

    # ── 字体大小 ──────────────────────────────────────────────

    def _apply_font_size(self):
        """应用字体大小到 line_edit（自动计算或使用固定值）。"""
        if self._font_size is not None:
            size = max(10, self._font_size)
        else:
            size = max(10, int(self._spin_height * 0.33))
        self._line_edit.setFont(QFont("Microsoft YaHei", size))

    def setFontSize(self, size: int | None):
        """设置文字大小（None=自动，int=固定 ≥10px）。"""
        if size is not None:
            size = max(10, size)
        self._font_size = size
        self._apply_font_size()

    def fontSize(self) -> int | None:
        """获取文字大小（None=自动）。"""
        return self._font_size

    # ── 文字对齐 ──────────────────────────────────────────────

    _ALIGN_MAP = {
        "left": Qt.AlignLeft | Qt.AlignVCenter,
        "center": Qt.AlignCenter,
        "right": Qt.AlignRight | Qt.AlignVCenter,
    }

    def _apply_text_alignment(self):
        """应用文字对齐到 line_edit。"""
        flag = self._ALIGN_MAP.get(self._text_align, Qt.AlignRight | Qt.AlignVCenter)
        self._line_edit.setAlignment(flag)

    def setTextAlign(self, align: str):
        """设置文字对齐方式（"left"/"center"/"right"）。"""
        if align not in ("left", "center", "right"):
            return
        if align == self._text_align:
            return
        self._text_align = align
        self._apply_text_alignment()

    def textAlign(self) -> str:
        """获取当前文字对齐方式。"""
        return self._text_align

    # ── 主题热切换 ──────────────────────────────────────────────

    def changeEvent(self, event):
        """监听全局样式变化（主题切换）。"""
        if event.type() == QEvent.StyleChange:
            _refresh_theme_cache()
            self._setup_theme()
            self._invalidate_icon_cache()
            self._update_icons()
            self._apply_outer_style()
        super().changeEvent(event)

    def refresh_theme(self):
        """主动刷新主题。"""
        _refresh_theme_cache()
        self._setup_theme()
        self._invalidate_icon_cache()
        self._update_icons()
        self._apply_outer_style()
        self._hook_log("function_watch", "refresh_theme",
                       f"theme={_THEME_CACHE.get('theme_type', '?')}")


# ═══════════════════════════════════════════════════════════════════════
#  StarSpinBox — 整数版本
# ═══════════════════════════════════════════════════════════════════════

class StarSpinBox(_BaseSpinBox):
    """自定义整数输入框 — 替代 Qt QSpinBox。

    使用示例:
        spin = StarSpinBox(value=42, max_value=100, suffix=" 人")
        spin.valueChanged.connect(lambda v: print(f"新值: {v}"))
    """

    def __init__(self, parent=None, value=0, min_value=0, max_value=99, step=1,
                 prefix="", suffix="", button_layout="right",
                 spin_height=32, button_width=22, editable=True,
                 icon_scheme="auto", object_name="",
                 text_align="left", font_size=None):
        super().__init__(
            parent=parent, value=int(value), min_value=int(min_value),
            max_value=int(max_value), step=int(step),
            prefix=prefix, suffix=suffix, button_layout=button_layout,
            spin_height=spin_height, button_width=button_width,
            editable=editable, icon_scheme=icon_scheme,
            object_name=object_name,
            text_align=text_align, font_size=font_size,
        )

    def _setup_validator(self):
        """设置整数验证器。"""
        validator = QIntValidator(self._min_value, self._max_value)
        self._line_edit.setValidator(validator)

    def _clamp_value(self, val):
        return max(self._min_value, min(self._max_value, int(val)))

    def _format_value(self):
        return str(self._value)

    def _convert_text(self, text: str):
        return int(text)


# ═══════════════════════════════════════════════════════════════════════
#  StarDoubleSpinBox — 双精度浮点版本
# ═══════════════════════════════════════════════════════════════════════

class StarDoubleSpinBox(_BaseSpinBox):
    """自定义双精度浮点输入框 — 替代 Qt QDoubleSpinBox。

    使用示例:
        spin = StarDoubleSpinBox(value=0.7, min_value=0.0, max_value=2.0,
                                 step=0.1, decimals=2, prefix="温度: ")
    """

    def __init__(self, parent=None, value=0.0, min_value=0.0, max_value=99.0,
                 step=1.0, decimals=2, prefix="", suffix="", button_layout="right",
                 spin_height=32, button_width=22, editable=True,
                 icon_scheme="auto", object_name="",
                 text_align="left", font_size=None):
        self._decimals = max(0, decimals)
        super().__init__(
            parent=parent, value=float(value), min_value=float(min_value),
            max_value=float(max_value), step=float(step),
            prefix=prefix, suffix=suffix, button_layout=button_layout,
            spin_height=spin_height, button_width=button_width,
            editable=editable, icon_scheme=icon_scheme,
            object_name=object_name,
            text_align=text_align, font_size=font_size,
        )

    def _setup_validator(self):
        """设置双精度验证器。"""
        validator = QDoubleValidator(self._min_value, self._max_value, self._decimals)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self._line_edit.setValidator(validator)

    def _clamp_value(self, val):
        return max(self._min_value, min(self._max_value, round(float(val), self._decimals)))

    def _format_value(self):
        return f"{self._value:.{self._decimals}f}"

    def _convert_text(self, text: str):
        return round(float(text), self._decimals)

    def setDecimals(self, decimals: int):
        """设置小数位数。"""
        self._decimals = max(0, decimals)
        self._setup_validator()
        self._value = round(self._value, self._decimals)
        self._update_display()

    def decimals(self) -> int:
        """获取小数位数。"""
        return self._decimals
