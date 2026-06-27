"""StarDebate ★ 辩之星 — 启动横幅

功能：
  - 黑色圆角卡片，在 LogService 等待期间显示
  - 7 阶段精确进度文字（左下）+ 版本号（右下）
  - 3px 全宽渐变呼吸光晕进度条（左→右填充 + 亮度呼吸）
  - 脉冲呼吸点（绿色 6×6 圆点，与进度文字并行）
  - 淡入淡出动画
  - ★ 自动读取当前主题的 theme.json 颜色生成 QSS

架构：
  由 StarDebate.py 在 QApplication 创建后立即实例化，
  通过 set_progress() 驱动阶段进度。
  主窗口初始化完成后调用 fade_out_and_close() 关闭。
============================================================================
"""
import math
import time
import os
import json

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QApplication
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QColor, QLinearGradient, QBrush, QPainterPath, QPixmap
from PyQt5.QtSvg import QSvgRenderer

from workers.app_config.config_paths import get_config_path
from components.res_path import get_resource_root


# ══════════════════════════════════════════════════════════════════════
#  主题颜色 -> 横幅颜色的映射规则
# ══════════════════════════════════════════════════════════════════════
# (theme.json 的 colors key, 可指定多个作为 fallback)
_BANNER_COLOR_MAP = {
    "card_bg":         ["base"],
    "card_border":     ["border"],
    "title_color":     ["accent_purple", "accent", "accent_blue"],
    "subtitle_color":  ["text"],
    "tagline_color":   ["muted"],
    "status_color":    ["muted"],
    "version_color":   ["pressed", "muted"],
    "pulse_color":     ["accent_green"],
    "bar_bg":          ["overlay"],
    "bar_start":       ["accent_purple", "accent", "accent_blue"],
    "bar_end":         ["accent_blue", "accent"],
}


def _resolve_color(theme_colors: dict, keys: list[str], fallback="#585b70"):
    """按优先级从 theme_colors 中取第一个存在的颜色值。"""
    for k in keys:
        v = theme_colors.get(k)
        if v and isinstance(v, str) and v.startswith("#"):
            return v
    return fallback


def _load_banner_colors() -> dict:
    """从 config.json -> theme.json 读取颜色配置。

    Returns:
        dict: {color_name: "#hex", ...} 供 QSS 和 BreathingBar 使用。
              失败时返回 Catppuccin Mocha 硬编码备选。
    """
    # ── 默认备选（Catppuccin Mocha）─────────────────────────────
    fallback = {
        "card_bg":        "#1e1e2e",
        "card_border":    "#45475a",
        "title_color":    "#cba6f7",
        "subtitle_color": "#a6adc8",
        "tagline_color":  "#6c7086",
        "status_color":   "#6c7086",
        "version_color":  "#585b70",
        "pulse_color":    "#a6e3a1",
        "bar_bg":         "#313244",
        "bar_start":      "#cba6f7",
        "bar_end":        "#89b4fa",
    }

    # ── 读取 config.json ────────────────────────────────────────
    config_path = get_config_path("config/config.json")
    theme_name = None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            theme_name = cfg.get("theme")
    except Exception:
        return fallback

    if not theme_name:
        return fallback

    # ── 读取 theme.json ─────────────────────────────────────────
    theme_path = os.path.join(
        get_resource_root(), "style", "themes", theme_name, "theme.json"
    )
    try:
        with open(theme_path, "r", encoding="utf-8") as f:
            theme_data = json.load(f)
    except Exception:
        return fallback

    theme_colors = theme_data.get("colors", {})
    if not theme_colors:
        return fallback

    # ── 根据映射规则取颜色 ──────────────────────────────────────
    result = {}
    for banner_key, source_keys in _BANNER_COLOR_MAP.items():
        result[banner_key] = _resolve_color(
            theme_colors, source_keys, fallback.get(banner_key, "#585b70")
        )
    result["_theme_type"] = theme_data.get("type", "dark")

    return result


def _generate_card_qss(colors: dict) -> str:
    """生成卡片的 QSS（背景+圆角），无边框。"""
    return (
        f"background-color: {colors['card_bg']}; "
        f"border-radius: 16px;"
    )


# ══════════════════════════════════════════════════════════════════════
#  BreathingBar — 呼吸光晕进度条
# ══════════════════════════════════════════════════════════════════════

class BreathingBar(QWidget):
    """3px 全宽呼吸光晕进度条，颜色跟随主题。"""

    BAR_HEIGHT = 4
    WIDGET_HEIGHT = 10

    def __init__(self, colors: dict, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.WIDGET_HEIGHT)
        self.setObjectName("startupBannerBar")
        self._progress = 0.0
        self._breath_phase = 0.0

        # ── 主题颜色 ────────────────────────────────────────────
        self._bar_bg = QColor(colors["bar_bg"])
        self._grad_start = QColor(colors["bar_start"])
        self._grad_end = QColor(colors["bar_end"])
        # 浅色主题用黑色呼吸光晕，深色用白色
        is_light = colors.get("_theme_type") == "light"
        self._overlay_base = QColor(0, 0, 0) if is_light else QColor(255, 255, 255)
        self._overlay_max_alpha = 20 if is_light else 35

        # QTimer 驱动
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._timer_tick)
        self._timer.start(33)

    def set_progress(self, value: float):
        self._progress = max(0.0, min(1.0, value))
        self._breath_phase += 0.18
        self.update()

    def _timer_tick(self):
        self._breath_phase += 0.08
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        bar_y = (self.WIDGET_HEIGHT - self.BAR_HEIGHT) // 2
        bar_h = self.BAR_HEIGHT
        r = 2

        # ── 背景（未填充区域）────────────────────────────────────
        bg_path = QPainterPath()
        bg_path.addRoundedRect(0, bar_y, w, bar_h, r, r)
        p.fillPath(bg_path, self._bar_bg)

        if self._progress <= 0.0:
            p.end()
            return

        fill_w = int(w * self._progress)
        if fill_w < 1:
            p.end()
            return

        # ── 渐变填充 ──────────────────────────────────────────
        grad = QLinearGradient(0, 0, fill_w, 0)
        grad.setColorAt(0.0, self._grad_start)
        grad.setColorAt(1.0, self._grad_end)

        fill_path = QPainterPath()
        fill_path.addRoundedRect(0, bar_y, fill_w, bar_h, r, r)
        p.fillPath(fill_path, QBrush(grad))

        # ── 呼吸光晕 ──────────────────────────────────────────
        breath = 0.5 + 0.5 * math.sin(self._breath_phase)
        overlay = QColor(
            self._overlay_base.red(),
            self._overlay_base.green(),
            self._overlay_base.blue(),
            int(self._overlay_max_alpha * breath),
        )
        p.fillPath(fill_path, overlay)

        p.end()


# ══════════════════════════════════════════════════════════════════════
#  StartupBanner — 启动横幅窗口
# ══════════════════════════════════════════════════════════════════════

class StartupBanner(QWidget):
    """启动横幅窗口。"""

    CARD_WIDTH = 560
    CARD_HEIGHT = 380

    def __init__(self, version="1.0.0"):
        super().__init__()
        self._version = version

        # ★ 读取主题颜色（在 UI 构建之前）
        self._theme_colors = _load_banner_colors()

        self._build_ui()
        self._center_on_screen()
        self._apply_qss()

        # 脉冲点呼吸定时器
        self._pulse_phase = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._update_pulse_dot)
        self._pulse_timer.start(250)

        self.setWindowOpacity(0.0)

    # ── 公开 API ─────────────────────────────────────────────────────
    def set_progress(self, stage: int, total: int, text: str = None):
        progress = stage / total
        self._progress_bar.set_progress(progress)
        if text:
            self._status_label.setText(text)
        try:
            QApplication.processEvents()
        except Exception:
            pass

    def show_with_fade(self, steps: int = 20, interval_ms: int = 15):
        self.show()
        self.raise_()
        self.activateWindow()
        for i in range(1, steps + 1):
            self.setWindowOpacity(i / steps)
            try:
                QApplication.processEvents()
                time.sleep(interval_ms / 1000)
            except Exception:
                pass

    def fade_out_and_close(self, callback=None):
        steps = 20
        for i in range(steps, -1, -1):
            self.setWindowOpacity(i / steps)
            try:
                QApplication.processEvents()
                time.sleep(0.015)
            except Exception:
                pass
        self.close()
        if callback:
            callback()

    # ── 内部：卡片 QSS ───────────────────────────────────────────────
    def _apply_qss(self):
        """卡片背景/边框由 QSS 控制。"""
        qss = _generate_card_qss(self._theme_colors)
        self._card.setStyleSheet(qss)

    # ── 内部：脉冲点动画 ─────────────────────────────────────────────
    def _update_pulse_dot(self):
        pulse_color = self._theme_colors.get("pulse_color", "#a6e3a1")
        self._pulse_phase += 0.3
        breath = 0.3 + 0.7 * abs(math.sin(self._pulse_phase))
        alpha = int(200 * breath)
        self._pulse_dot.setStyleSheet(
            f"background-color: rgba({self._hex_to_rgb(pulse_color)}, {alpha}); "
            f"border-radius: 3px;"
        )

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> str:
        """#aabbcc → "170,187,204" """
        h = hex_color.lstrip("#")
        if len(h) == 6:
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return f"{r},{g},{b}"
        return "166,227,161"

    # ── UI 构建 ──────────────────────────────────────────────────────
    def _build_ui(self):
        c = self._theme_colors
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.CARD_WIDTH, self.CARD_HEIGHT)
        self.setObjectName("startupBanner")

        # ── 卡片容器 ──────────────────────────────────────────────
        self._card = QWidget(self)
        self._card.setGeometry(0, 0, self.CARD_WIDTH, self.CARD_HEIGHT)
        self._card.setObjectName("startupBannerCard")

        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(40, 36, 40, 24)
        layout.setSpacing(0)

        # ── 顶部弹性空间 ─────────────────────────────────────────
        layout.addStretch(1)

        # ── 图标 ────────────────────────────────────────────────
        self._icon_label = QLabel()
        self._icon_label.setObjectName("startupBannerIcon")
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setFixedSize(96, 96)
        # 加载主Logo SVG
        icon_path = os.path.join(get_resource_root(), "icon", "common", "main.svg")
        renderer = QSvgRenderer(icon_path)
        if renderer.isValid():
            pixmap = QPixmap(96, 96)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            self._icon_label.setPixmap(pixmap)
        self._icon_label.setStyleSheet("background-color: transparent; padding: 0px;")

        icon_wrapper = QWidget()
        iw_layout = QHBoxLayout(icon_wrapper)
        iw_layout.setContentsMargins(0, 0, 0, 0)
        iw_layout.addStretch()
        iw_layout.addWidget(self._icon_label)
        iw_layout.addStretch()
        layout.addWidget(icon_wrapper)

        layout.addSpacing(8)

        # ── 副标题 ──────────────────────────────────────────────
        self._subtitle_label = QLabel("辩之星")
        self._subtitle_label.setObjectName("startupBannerSubtitle")
        self._subtitle_label.setAlignment(Qt.AlignCenter)
        self._subtitle_label.setStyleSheet(
            f"background-color: transparent; color: {c['subtitle_color']}; "
            f"font-family: \"HarmonyOS Sans SC\"; "
            f"font-size: 19px; font-weight: bold; padding: 0px;"
        )
        layout.addWidget(self._subtitle_label)

        # ── 标语 ────────────────────────────────────────────────
        self._tagline_label = QLabel("AI专业备赛助手")
        self._tagline_label.setObjectName("startupBannerTagline")
        self._tagline_label.setAlignment(Qt.AlignCenter)
        self._tagline_label.setStyleSheet(
            f"background-color: transparent; color: {c['tagline_color']}; "
            f"font-family: \"HarmonyOS Sans SC\"; "
            f"font-size: 15px; padding: 0px;"
        )
        layout.addWidget(self._tagline_label)

        layout.addStretch(1)

        # ── 呼吸光晕进度条 ──────────────────────────────────────
        self._progress_bar = BreathingBar(self._theme_colors)
        layout.addWidget(self._progress_bar)

        layout.addSpacing(8)

        # ── 底部行 ──────────────────────────────────────────────
        bottom = QWidget()
        bottom.setObjectName("startupBannerBottomRow")
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(6)

        # 脉冲点 + 文字容器
        status_container = QWidget()
        status_container.setObjectName("startupBannerStatusContainer")
        sc = QHBoxLayout(status_container)
        sc.setContentsMargins(0, 0, 0, 0)
        sc.setSpacing(6)

        self._pulse_dot = QLabel()
        self._pulse_dot.setObjectName("startupBannerPulseDot")
        self._pulse_dot.setFixedSize(6, 6)
        sc.addWidget(self._pulse_dot)

        self._status_label = QLabel("正在初始化应用环境...")
        self._status_label.setObjectName("startupBannerStatus")
        self._status_label.setStyleSheet(
            f"background-color: transparent; color: {c['status_color']}; "
            f"font-family: \"HarmonyOS Sans SC\"; "
            f"font-size: 13px; padding: 0px;"
        )
        sc.addWidget(self._status_label)

        sc.addStretch()
        bl.addWidget(status_container)
        bl.addStretch()

        self._version_label = QLabel(f"v{self._version}")
        self._version_label.setObjectName("startupBannerVersion")
        self._version_label.setStyleSheet(
            f"background-color: transparent; color: {c['version_color']}; "
            f"font-family: \"HarmonyOS Sans SC\"; "
            f"font-size: 11px; padding: 0px;"
        )
        bl.addWidget(self._version_label)

        layout.addWidget(bottom)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2,
        )
