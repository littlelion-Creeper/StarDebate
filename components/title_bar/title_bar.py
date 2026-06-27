"""自定义标题栏 — 通用组件（含菜单栏注入能力）

TitleBar(QWidget) 提供：
  - 窗口拖拽移动（仅中间空白 drag_area 区域响应拖拽）
  - 双击最大化/还原
  - 最小化 / 最大化 / 关闭 按钮（SVG 图标渲染）
  - 自动监听顶层窗口状态变化，刷新最大化按钮图标
  - ★ 菜单注入区：get_menu_section() / get_right_section() / get_plugin_section()
    供 TopNavManager 注入菜单按钮和插件按钮，实现标题栏+菜单栏融合

使用示例:
    from components.title_bar import TitleBar
    from workers.top_nav import TopNavManager, TopNavRegistry

    class MyWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowFlags(Qt.FramelessWindowHint)
            self._title_bar = TitleBar(self, icon="★")
            main_layout.insertWidget(0, self._title_bar)

            # 注入菜单按钮到标题栏
            registry = TopNavRegistry("config/menu_my_window.json")
            registry.load()
            top_nav_mgr = TopNavManager(self, registry)
            top_nav_mgr.inject_into_titlebar(self._title_bar)

        def changeEvent(self, event):
            if event.type() == QEvent.WindowStateChange:
                self._title_bar.update_max_btn()
            super().changeEvent(event)
"""
import os

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, QPoint, QEvent, pyqtProperty
from PyQt5.QtGui import (
    QFont, QPainter, QPen, QColor, QMouseEvent, QPainterPath,
    QPixmap,
)

from components.theme_colors import tc
from components.svg_renderer import SvgRenderer
from components.res_path import get_resource_root

# SVG 图标目录
_ICON_DIR = os.path.join(
    get_resource_root(),
    'icon', 'top_nav_bar',
)


# ═══════════════════════════════════════════════════════════════════════
# 绘制型按钮子类
# ═══════════════════════════════════════════════════════════════════════

class _TitleBarButton(QPushButton):
    """标题栏按钮基类：SVG 图标渲染。

    按钮尺寸 52×42（宽=高×1.25），与标题栏等高。
    hover/pressed 状态全部由 paintEvent 控制。
    支持按边角设置圆角裁剪（round_left / round_right）。

    ★ 颜色通过 pyqtProperty 暴露，可由 QSS 的 qproperty-* 覆盖：
       iconsNormal / iconHover / bgHover / bgPressed

    ★ SVG 图标：通过 svg_path 传入，运行时 fill 颜色自动替换为当前状态色
    """
    CORNER_RADIUS = 12  # 与窗口圆角一致

    def __init__(self, icon_normal="", icon_hover="", bg_hover="", bg_pressed="",
                 tooltip="", parent=None, round_left=False, round_right=False,
                 svg_path=""):
        """
        图标 / 背景 四项颜色可传 hex 或留空。
        留空 → 自动从 tc() 读取当前主题色：
           icon_normal = subtext, icon_hover = text
           bg_hover = hover, bg_pressed = pressed
        传入 hex → 优先使用（可被 QSS qproperty-* 覆盖）
        """
        super().__init__(parent)
        self.setFixedSize(52, 42)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        # 空字符串 ↴ 动态主题色（可刷新）；非空 ↴ 显式 hex（QSS 可覆盖）
        self._auto_clr_norm = not bool(icon_normal)
        self._auto_clr_hover = not bool(icon_hover)
        self._auto_bg_hover = not bool(bg_hover)
        self._auto_bg_press = not bool(bg_pressed)
        self._clr_norm = QColor(icon_normal) if icon_normal else QColor(tc("subtext"))
        self._clr_hover = QColor(icon_hover) if icon_hover else QColor(tc("text"))
        self._bg_hover = QColor(bg_hover) if bg_hover else QColor(tc("hover"))
        self._bg_press = QColor(bg_pressed) if bg_pressed else QColor(tc("pressed"))
        self._round_left = round_left
        self._round_right = round_right
        # SVG 文件路径映射（key='default' 或自定义名称，渲染由 SvgRenderer 缓存）
        self._svg_file_paths: dict[str, str] = {}
        if svg_path:
            self._svg_file_paths['default'] = svg_path

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

    def _get_bg_pressed(self) -> QColor:
        return self._bg_press

    def _set_bg_pressed(self, color: QColor):
        self._bg_press = QColor(color)
        self.update()

    bgPressed = pyqtProperty(QColor, fget=_get_bg_pressed, fset=_set_bg_pressed)

    # ── 主题刷新 ────────────────────────────────────────────────
    def refresh_theme_colors(self):
        """主题切换后重新读取自动获取的主题色。"""
        if self._auto_clr_norm:
            self._clr_norm = QColor(tc("subtext"))
        if self._auto_clr_hover:
            self._clr_hover = QColor(tc("text"))
        if self._auto_bg_hover:
            self._bg_hover = QColor(tc("hover"))
        if self._auto_bg_press:
            self._bg_press = QColor(tc("pressed"))
        self.update()

    # ── SVG 图标渲染 — 由 SvgRenderer 统一处理（颜色替换 + LRU 缓存）─
    def _render_colored_icon(self, painter: QPainter, svg_key: str,
                             color: QColor, target_size: int = 18):
        """用 SvgRenderer 渲染指定颜色的图标，绘制到按钮中心"""
        path = self._svg_file_paths.get(svg_key, '')
        if not path:
            return
        pixmap = SvgRenderer.render(path, target_size, mode="mono",
                                    color=color.name())
        if pixmap.isNull():
            return
        x = (self.width() - target_size) // 2
        y = (self.height() - target_size) // 2
        painter.drawPixmap(x, y, pixmap)

    def _clip_path(self) -> QPainterPath:
        """构建带边角圆角的裁剪路径"""
        r = self.CORNER_RADIUS
        w, h = self.width(), self.height()
        path = QPainterPath()
        if self._round_left:
            path.moveTo(r, 0)
        else:
            path.moveTo(0, 0)
        if self._round_right:
            path.lineTo(w - r, 0)
            path.arcTo(w - r * 2, 0, r * 2, r * 2, 90, -90)
        else:
            path.lineTo(w, 0)
        if self._round_right:
            path.lineTo(w, h - r)
            path.arcTo(w - r * 2, h - r * 2, r * 2, r * 2, 0, -90)
        else:
            path.lineTo(w, h)
        if self._round_left:
            path.lineTo(r, h)
            path.arcTo(0, h - r * 2, r * 2, r * 2, 270, -90)
        else:
            path.lineTo(0, h)
        if self._round_left:
            path.lineTo(0, r)
            path.arcTo(0, 0, r * 2, r * 2, 180, -90)
        else:
            path.lineTo(0, 0)
        path.closeSubpath()
        return path

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # 圆角裁剪
        if self._round_left or self._round_right:
            p.setClipPath(self._clip_path())

        under = self.underMouse()
        if under and self.isDown():
            p.fillRect(self.rect(), self._bg_press)
        elif under:
            p.fillRect(self.rect(), self._bg_hover)

        p.setPen(QPen(self._clr_hover if under else self._clr_norm, 1.5))
        self._draw_icon(p, self.rect())
        p.end()

    def _draw_icon(self, painter: QPainter, rect):
        """子类可重写，默认渲染 SVG 图标"""
        if 'default' not in self._svg_file_paths:
            return
        under = self.underMouse()
        color = self._clr_hover if under else self._clr_norm
        self._render_colored_icon(painter, 'default', color)


class MinimizeButton(_TitleBarButton):
    """最小化按钮：minimise.svg 图标，左上 + 左下圆角"""

    def __init__(self, parent=None):
        super().__init__(
            tooltip="最小化", parent=parent,
            round_left=True,
            svg_path=os.path.join(_ICON_DIR, 'minimise.svg'),
        )


class MaximizeButton(_TitleBarButton):
    """最大化/还原按钮：full_screen.svg / windowed.svg"""

    def __init__(self, parent=None):
        super().__init__(
            tooltip="最大化", parent=parent,
            svg_path=os.path.join(_ICON_DIR, 'full_screen.svg'),
        )
        self._svg_file_paths['restore'] = os.path.join(_ICON_DIR, 'windowed.svg')
        self._restore = False

    def set_restore(self, value: bool):
        """True → 还原图标 / False → 最大化图标"""
        if self._restore != value:
            self._restore = value
            self.update()

    def _draw_icon(self, p: QPainter, rect):
        key = 'restore' if self._restore else 'default'
        if key not in self._svg_file_paths:
            return
        under = self.underMouse()
        color = self._clr_hover if under else self._clr_norm
        self._render_colored_icon(p, key, color)


class CloseButton(_TitleBarButton):
    """关闭按钮：close.svg 图标，右上 + 右下圆角

    正常色 → 由 tc("subtext") 自动主题适配。
    hover 白图标 + 红色背景是设计常数。
    """

    def __init__(self, parent=None):
        super().__init__(
            icon_hover="#ffffff",
            bg_hover="#f38ba8", bg_pressed="#e0567a",
            tooltip="关闭", parent=parent,
            round_right=True,
            svg_path=os.path.join(_ICON_DIR, 'close.svg'),
        )


# ═══════════════════════════════════════════════════════════════════════
# TitleBar 主体
# ═══════════════════════════════════════════════════════════════════════

class TitleBar(QWidget):
    """通用自定义标题栏 — 内置菜单栏注入能力。

    位于窗口顶部，替代原生标题栏。通过 get_menu_section() / get_right_section() /
    get_plugin_section() 将外部按钮（菜单按钮/插件按钮/独立按钮）注入标题栏，
    实现标题栏 + 菜单栏的融合。

    布局结构：
      [icon] [menu_section(菜单注入)] [drag_area(弹性拖拽)] [plugin_section(插件)] [right_section(右侧)] [ctrl_btns]
    """

    def __init__(self, parent=None, title: str = "StarDebate",
                 icon: str = "★", icon_path: str = "",
                 compact: bool = False):
        """初始化标题栏。

        Args:
            parent: 父控件
            title: 标题文字
            icon: 图标文字（无图片路径时生效）
            icon_path: 可选图片路径，优先于文字图标
            compact: 紧凑模式，仅显示图标+标题+关闭按钮，适用于弹窗
        """
        super().__init__(parent)
        self._compact = compact
        self._drag_pos: QPoint | None = None
        self._title = title
        self._icon = icon
        self._icon_path = icon_path  # 可选图片路径，优先于文字图标
        self._setup_ui()
        self._connect_signals()

        if compact:
            # compact 模式：隐藏最小化/最大化，保留拖拽功能（弹窗仍需拖动）
            self._min_btn.setVisible(False)
            self._max_btn.setVisible(False)
            self._close_btn.setVisible(True)

        # 监听顶层窗口状态变化，自动刷新最大化按钮图标
        if parent is not None and not compact:
            top = parent.window()
            top.installEventFilter(self)

    # ── UI 构建 ────────────────────────────────────────────────────
    def _setup_ui(self):
        self.setObjectName("titleBar")
        self.setFixedHeight(42)
        self.setCursor(Qt.ArrowCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 4, 0)
        layout.setSpacing(0)

        # ★ 图标（优先加载图片，回退到文字）
        self._icon_label = QLabel()
        self._icon_label.setObjectName("titleIcon")
        self._icon_label.setFixedWidth(26)
        self._icon_label.setAlignment(Qt.AlignCenter)
        if self._icon_path and os.path.exists(self._icon_path):
            pix = QPixmap(self._icon_path).scaled(
                22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._icon_label.setPixmap(pix)
        else:
            self._icon_label.setText(self._icon)
            self._icon_label.setFont(QFont("Microsoft YaHei", 18))

        # ★ 菜单注入区（menu_area：菜单按钮组，如文件/编辑/视图）
        self._menu_section = QHBoxLayout()
        self._menu_section.setSpacing(3)

        # ★ 拖拽区域（弹性空间，仅此处响应拖拽 + 双击最大化）
        self._drag_area = QWidget()
        self._drag_area.setObjectName("titleDragArea")
        self._drag_area.setCursor(Qt.ArrowCursor)

        # ★ 插件注入区（right_area 内的 plugin_area：动态插件按钮）
        self._plugin_section = QHBoxLayout()
        self._plugin_section.setSpacing(3)

        # ★ 右侧按钮注入区（right_area 内的 button：如帮助）
        self._right_section = QHBoxLayout()
        self._right_section.setSpacing(3)

        # ★ 窗口控制按钮（固定最右侧，SVG 图标渲染）
        self._min_btn = MinimizeButton(self)
        self._min_btn.setObjectName("minBtn")

        self._max_btn = MaximizeButton(self)
        self._max_btn.setObjectName("maxBtn")

        self._close_btn = CloseButton(self)
        self._close_btn.setObjectName("closeBtn")

        # ── 组装布局 ──
        layout.addWidget(self._icon_label)
        layout.addSpacing(6)
        layout.addLayout(self._menu_section)
        layout.addWidget(self._drag_area, 1)          # stretch=1，占据全部剩余空间
        layout.addLayout(self._plugin_section)
        layout.addLayout(self._right_section)
        layout.addWidget(self._min_btn)
        layout.addWidget(self._max_btn)
        layout.addWidget(self._close_btn)

    def _connect_signals(self):
        self._min_btn.clicked.connect(self._on_minimize)
        self._max_btn.clicked.connect(self._on_maximize)
        self._close_btn.clicked.connect(self._on_close)

    # ── 拖拽支持（仅 drag_area 区域）────────────────────────────
    def mousePressEvent(self, event: 'QMouseEvent'):
        if event.button() == Qt.LeftButton:
            if self._drag_area.geometry().contains(event.pos()):
                self._drag_pos = event.globalPos()
                self._drag_area.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: 'QMouseEvent'):
        if self._drag_pos is not None:
            delta = event.globalPos() - self._drag_pos
            top = self.window()
            if top.isMaximized():
                top.showNormal()
                ratio = event.globalPos().x() / top.screen().geometry().width()
                new_x = int(event.globalPos().x() - top.width() * ratio)
                top.move(new_x, 0)
                self._drag_pos = event.globalPos()
            else:
                top.move(top.pos() + delta)
                self._drag_pos = event.globalPos()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: 'QMouseEvent'):
        if event.button() == Qt.LeftButton and self._drag_pos is not None:
            self._drag_pos = None
            self._drag_area.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: 'QMouseEvent'):
        if event.button() == Qt.LeftButton:
            if self._drag_area.geometry().contains(event.pos()):
                self._on_maximize()
        super().mouseDoubleClickEvent(event)

    # ── 窗口控制 ─────────────────────────────────────────────────
    def _on_minimize(self):
        self.window().showMinimized()

    def _on_maximize(self):
        top = self.window()
        if top.isMaximized():
            top.showNormal()
        else:
            top.showMaximized()

    def _on_close(self):
        self.window().close()

    # ── 公开 API ──────────────────────────────────────────────────
    def set_title(self, text: str):
        """更新标题文字（当前版本无标题标签，保留接口兼容）"""
        self._title = text

    def set_icon(self, text: str):
        """更新图标文字（当无图片路径时生效）"""
        self._icon = text
        if not self._icon_path:
            self._icon_label.setText(text)

    def refresh_theme_colors(self):
        """主题切换后刷新三个窗口按钮的颜色。"""
        for btn in (self._min_btn, self._max_btn, self._close_btn):
            btn.refresh_theme_colors()

    def update_max_btn(self):
        """根据顶层窗口状态刷新最大化按钮图标"""
        top = self.window()
        if top.isMaximized():
            self._max_btn.set_restore(True)
            self._max_btn.setToolTip("还原")
        else:
            self._max_btn.set_restore(False)
            self._max_btn.setToolTip("最大化")

    # ── ★ 菜单注入 API ──────────────────────────────────────────
    def get_menu_section(self) -> QHBoxLayout:
        """返回菜单按钮注入区布局（图标右侧，drag_area 左侧）。

        TopNavManager 将 menu_area 中的 menu_button/button/separator
        类型的控件添加到此布局。
        """
        return self._menu_section

    def get_right_section(self) -> QHBoxLayout:
        """返回右侧按钮注入区布局（drag_area 右侧，窗口控制按钮左侧）。

        TopNavManager 将 right_area 中 button 类型的独立按钮（如帮助）添加到此布局。
        """
        return self._right_section

    def get_plugin_section(self) -> QHBoxLayout:
        """返回插件按钮注入区布局（drag_area 右侧，right_section 左侧）。

        TopNavManager 将 right_area 中 plugin_area 类型的动态插件按钮添加到此布局。
        """
        return self._plugin_section

    # ── 事件过滤：监听顶层窗口 WindowStateChange ───────────────
    def eventFilter(self, obj, event):
        if event.type() == QEvent.WindowStateChange:
            self.update_max_btn()
        return super().eventFilter(obj, event)
