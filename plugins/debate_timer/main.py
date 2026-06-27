# -*- coding: utf-8 -*-
"""
辩论计时器插件
==============
带完整 PyQt5 UI 的多阶段辩论计时器。
- 预设 5 个辩论阶段（立论/驳论/质询/自由辩论/总结陈词）
- 每个阶段独立时长和预警时间
- 倒计时显示，30 秒内变黄，10 秒内变红闪烁
- 进度条可视化
- 阶段切换自动重置
- 置顶窗口选项

使用方法：
  - 导入插件后，调用 show_timer() 打开计时器窗口
  - 或在 StarDebate 控制台中运行:
      from plugins.debate_timer.main import show_timer
      show_timer()
"""

import json
import os
import sys

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QProgressBar, QFrame, QCheckBox, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer, QTime
from PyQt5.QtGui import QFont

from workers.plugin_manager import get_api

# ── 元信息 ──
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ID = "debate_timer"

# ── 深色主题 QSS ──
TIMER_QSS = """
QDialog {
    background-color: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 12px;
}
QLabel {
    color: #cdd6f4;
    font-family: "Microsoft YaHei";
}
QComboBox {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    min-height: 28px;
}
QComboBox:hover { border: 1px solid #585b70; }
QComboBox:focus { border: 1px solid #2E6DDE; }
QComboBox QAbstractItemView {
    background-color: #181825;
    color: #cdd6f4;
    selection-background-color: #313244;
    border: 1px solid #45475a;
}
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 8px;
    padding: 8px 18px;
    font-size: 13px;
    font-family: "Microsoft YaHei";
}
QPushButton:hover { background-color: #45475a; border: 1px solid #585b70; }
QPushButton:pressed { background-color: #585b70; }
#btnStart {
    background-color: #a6e3a1;
    color: #1e1e2e;
    font-weight: bold;
    font-size: 15px;
    border: none;
}
#btnStart:hover { background-color: #94e2d5; }
#btnPause {
    background-color: #f9e2af;
    color: #1e1e2e;
    font-weight: bold;
    border: none;
}
#btnPause:hover { background-color: #fab387; }
#btnStop {
    background-color: #f38ba8;
    color: #1e1e2e;
    font-weight: bold;
    border: none;
}
#btnStop:hover { background-color: #eba0ac; }
#phaseCard {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 10px;
}
#timeLabel {
    font-size: 72px;
    font-weight: bold;
    font-family: "Consolas", "Microsoft YaHei";
    color: #cdd6f4;
}
#timeLabel[warning="true"] {
    color: #f9e2af;
}
#timeLabel[crisis="true"] {
    color: #f38ba8;
}
#phaseNameLabel {
    font-size: 18px;
    font-weight: bold;
    color: #2E6DDE;
}
#infoLabel {
    color: #6c7086;
    font-size: 11px;
}
QProgressBar {
    background-color: #313244;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #2E6DDE;
    border-radius: 4px;
}
QProgressBar[warning="true"]::chunk { background-color: #f9e2af; }
QProgressBar[crisis="true"]::chunk { background-color: #f38ba8; }
QCheckBox {
    color: #a6adc8;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #45475a;
    border-radius: 4px;
    background-color: #181825;
}
QCheckBox::indicator:checked {
    background-color: #2E6DDE;
    border-color: #2E6DDE;
}
"""


def load_config() -> dict:
    try:
        with open(os.path.join(PLUGIN_DIR, "plugin.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("config", {})
    except Exception:
        return {"phases": [], "sound_enabled": False, "always_on_top": True}


def save_config(config: dict):
    try:
        config_path = os.path.join(PLUGIN_DIR, "plugin.json")
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["config"] = config
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def format_time(seconds: int) -> str:
    """将秒数格式化为 MM:SS"""
    m, s = divmod(max(0, seconds), 60)
    return f"{m:02d}:{s:02d}"


class DebateTimerWindow(QDialog):
    """辩论计时器主窗口"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config = load_config()
        self._phases = self._config.get("phases", [])
        self._current_phase_idx = 0
        self._remaining = 0
        self._total = 0
        self._warn_time = 30
        self._running = False
        self._paused = False
        self._blink_on = True
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._toggle_blink)

        self._build_ui()
        self._apply_phase(0)

    def _build_ui(self):
        self.setWindowTitle("⏱ 辩论计时器")
        self.setMinimumSize(420, 380)
        self.setMaximumSize(520, 520)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # ── 标题栏 ──
        title = QLabel("⏱ 辩论计时器")
        title.setFont(QFont("Microsoft YaHei", 15, QFont.Bold))
        title.setStyleSheet("color: #2E6DDE;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # ── 阶段信息卡片 ──
        card = QFrame()
        card.setObjectName("phaseCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(10)

        # 阶段选择 + 时长
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self._phase_combo = QComboBox()
        self._phase_combo.setCursor(Qt.PointingHandCursor)
        self._phase_combo.currentIndexChanged.connect(self._on_phase_changed)
        top_row.addWidget(self._phase_combo, stretch=1)

        self._phase_name = QLabel("立论")
        self._phase_name.setObjectName("phaseNameLabel")
        top_row.addWidget(self._phase_name)

        card_layout.addLayout(top_row)

        # 进度条
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(100)
        self._progress.setTextVisible(False)
        card_layout.addWidget(self._progress)

        # 时间显示
        self._time_label = QLabel("03:00")
        self._time_label.setObjectName("timeLabel")
        self._time_label.setAlignment(Qt.AlignCenter)
        self._time_label.setFont(QFont("Consolas", 72, QFont.Bold))
        card_layout.addWidget(self._time_label)

        # 信息标签
        self._info_label = QLabel("准备开始")
        self._info_label.setObjectName("infoLabel")
        self._info_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self._info_label)

        layout.addWidget(card)

        # ── 控制按钮 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._btn_start = QPushButton("▶ 开始")
        self._btn_start.setObjectName("btnStart")
        self._btn_start.setCursor(Qt.PointingHandCursor)
        self._btn_start.setMinimumHeight(40)
        self._btn_start.clicked.connect(self._on_start)

        self._btn_pause = QPushButton("⏸ 暂停")
        self._btn_pause.setObjectName("btnPause")
        self._btn_pause.setCursor(Qt.PointingHandCursor)
        self._btn_pause.setMinimumHeight(40)
        self._btn_pause.setEnabled(False)
        self._btn_pause.clicked.connect(self._on_pause)

        self._btn_reset = QPushButton("↺ 重置")
        self._btn_reset.setObjectName("btnStop")
        self._btn_reset.setCursor(Qt.PointingHandCursor)
        self._btn_reset.setMinimumHeight(40)
        self._btn_reset.clicked.connect(self._on_reset)

        btn_row.addWidget(self._btn_start)
        btn_row.addWidget(self._btn_pause)
        btn_row.addWidget(self._btn_reset)
        layout.addLayout(btn_row)

        # ── 快捷切换 ──
        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)

        self._btn_prev = QPushButton("◀ 上一阶段")
        self._btn_prev.setCursor(Qt.PointingHandCursor)
        self._btn_prev.clicked.connect(self._prev_phase)

        self._btn_next = QPushButton("下一阶段 ▶")
        self._btn_next.setCursor(Qt.PointingHandCursor)
        self._btn_next.clicked.connect(self._next_phase)

        nav_row.addWidget(self._btn_prev)
        nav_row.addWidget(self._btn_next)
        layout.addLayout(nav_row)

        # ── 选项 ──
        opt_row = QHBoxLayout()
        opt_row.setSpacing(16)

        self._chk_ontop = QCheckBox("窗口置顶")
        self._chk_ontop.setChecked(self._config.get("always_on_top", True))
        self._chk_ontop.toggled.connect(self._on_top_toggled)

        self._lbl_total = QLabel("")
        self._lbl_total.setStyleSheet("color: #6c7086; font-size: 11px;")

        opt_row.addWidget(self._chk_ontop)
        opt_row.addStretch()
        opt_row.addWidget(self._lbl_total)
        layout.addLayout(opt_row)

        # ── 定时器 ──
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        self.setStyleSheet(TIMER_QSS)

    # ── 阶段管理 ──

    def _populate_phases(self):
        self._phase_combo.blockSignals(True)
        self._phase_combo.clear()
        for i, p in enumerate(self._phases):
            name = p.get("name", f"阶段{i+1}")
            dur = p.get("duration", 180)
            d_min, d_sec = dur // 60, dur % 60
            label = f"{name} ({d_min}:{d_sec:02d})"
            self._phase_combo.addItem(label)
        self._phase_combo.blockSignals(False)

    def _apply_phase(self, idx: int):
        if not self._phases:
            return
        idx = max(0, min(idx, len(self._phases) - 1))
        self._current_phase_idx = idx

        phase = self._phases[idx]
        name = phase.get("name", "阶段")
        dur = phase.get("duration", 180)
        warn = phase.get("warn_time", 30)

        self._phase_combo.setCurrentIndex(idx)
        self._phase_name.setText(name)
        self._total = dur
        self._remaining = dur
        self._warn_time = max(5, warn)
        self._running = False
        self._paused = False

        self._update_display()
        self._update_warning_state()
        self._update_button_state()
        self._lbl_total.setText(f"阶段 {idx+1}/{len(self._phases)}")

    def _prev_phase(self):
        if self._running:
            self._stop_timer()
        idx = self._current_phase_idx - 1
        if idx < 0:
            idx = len(self._phases) - 1
        self._apply_phase(idx)

    def _next_phase(self):
        if self._running:
            self._stop_timer()
        idx = self._current_phase_idx + 1
        if idx >= len(self._phases):
            idx = 0
        self._apply_phase(idx)

    def _on_phase_changed(self, idx: int):
        if idx >= 0:
            self._apply_phase(idx)

    # ── 计时控制 ──

    def _on_start(self):
        if self._paused:
            self._paused = False
            self._running = True
        else:
            self._remaining = self._total
            self._running = True
            self._paused = False

        self._timer.start(1000)
        self._update_button_state()
        self._update_warning_state()

        phase_name = self._phases[self._current_phase_idx].get("name", "")
        api = get_api()
        if api:
            api.update_status(f"计时开始: {phase_name} {format_time(self._total)}")

    def _on_pause(self):
        self._paused = not self._paused
        if self._paused:
            self._timer.stop()
        else:
            self._timer.start(1000)
        self._update_button_state()

    def _on_reset(self):
        self._stop_timer()
        self._remaining = self._total
        self._update_display()
        self._update_warning_state()
        self._update_button_state()

    def _stop_timer(self):
        self._timer.stop()
        self._running = False
        self._paused = False
        self._blink_timer.stop()
        self._blink_on = True

    def _tick(self):
        if not self._running:
            return
        self._remaining -= 1
        self._update_display()
        self._update_warning_state()

        if self._remaining <= 0:
            self._on_time_up()

    def _on_time_up(self):
        self._stop_timer()
        self._time_label.setText("00:00")
        self._info_label.setText("⏰ 时间到！")
        phase_name = self._phases[self._current_phase_idx].get("name", "")
        api = get_api()
        if api:
            api.update_status(f"⏰ {phase_name} 时间到！")
            api.show_notification("⏰ 时间到", f"「{phase_name}」环节计时结束。")

        # 闪烁效果 3 秒
        self._blink_remaining = 6  # 闪烁 3 秒（6 次 toggle）
        self._blink_timer.start(500)

    def _toggle_blink(self):
        self._blink_on = not self._blink_on
        self._update_display()
        self._blink_remaining -= 1
        if self._blink_remaining <= 0:
            self._blink_timer.stop()
            self._blink_on = True
            self._update_display()

    # ── UI 更新 ──

    def _update_display(self):
        if self._remaining <= 0 and not self._blink_on:
            self._time_label.setText("")  # 闪烁：隐藏
            self._progress.setValue(0)
        else:
            self._time_label.setText(format_time(self._remaining))
            pct = int(self._remaining / max(self._total, 1) * 100)
            self._progress.setValue(pct)

    def _update_warning_state(self):
        """根据剩余时间更新颜色状态"""
        self._time_label.setProperty("warning", False)
        self._time_label.setProperty("crisis", False)
        self._progress.setProperty("warning", False)
        self._progress.setProperty("crisis", False)

        if self._remaining <= 10:
            self._time_label.setProperty("crisis", True)
            self._progress.setProperty("crisis", True)
            if self._running:
                self._info_label.setText("⚠ 时间紧迫！")
        elif self._remaining <= self._warn_time:
            self._time_label.setProperty("warning", True)
            self._progress.setProperty("warning", True)
            if self._running:
                self._info_label.setText(f"⏳ 剩余 {self._remaining} 秒")
        else:
            self._info_label.setText(
                "运行中..." if self._running else "准备开始"
            )

        # 强制刷新样式
        self._time_label.style().unpolish(self._time_label)
        self._time_label.style().polish(self._time_label)
        self._progress.style().unpolish(self._progress)
        self._progress.style().polish(self._progress)

    def _update_button_state(self):
        self._btn_start.setEnabled(not self._running or self._paused)
        self._btn_pause.setEnabled(self._running)
        self._btn_reset.setEnabled(True)

        if self._paused:
            self._btn_start.setText("▶ 继续")
        else:
            self._btn_start.setText("▶ 开始")

        if self._running and not self._paused:
            self._btn_pause.setText("⏸ 暂停")
        elif self._paused:
            self._btn_pause.setText("▶ 继续")
        else:
            self._btn_pause.setText("⏸ 暂停")

        # 非运行时禁用阶段切换
        self._phase_combo.setEnabled(not self._running)
        self._btn_prev.setEnabled(not self._running)
        self._btn_next.setEnabled(not self._running)

    def _on_top_toggled(self, checked: bool):
        if checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()  # 需要重新 show 才能使 flags 生效
        self._config["always_on_top"] = checked
        save_config(self._config)

    def refresh_phases(self):
        """从配置文件重新加载阶段列表"""
        config = load_config()
        self._phases = config.get("phases", [])
        self._config = config
        self._populate_phases()
        if self._current_phase_idx >= len(self._phases):
            self._current_phase_idx = 0
        self._apply_phase(self._current_phase_idx)

    def showEvent(self, event):
        super().showEvent(event)
        self._populate_phases()
        self._apply_phase(self._current_phase_idx)


# ============================================================
#  全局实例管理
# ============================================================

_timer_window: DebateTimerWindow | None = None


def show_timer():
    """打开辩论计时器窗口（全局单例）"""
    global _timer_window
    api = get_api()

    if _timer_window is not None:
        try:
            _timer_window.refresh_phases()
            _timer_window.raise_()
            _timer_window.activateWindow()
            _timer_window.show()
        except RuntimeError:
            _timer_window = None

    if _timer_window is None:
        parent = api.mw if api else None
        _timer_window = DebateTimerWindow(parent)
        _timer_window.setAttribute(Qt.WA_DeleteOnClose, False)
        _timer_window.finished.connect(lambda: _on_timer_closed())

    _timer_window.show()
    if api:
        api.update_status("辩论计时器已打开")


def _on_timer_closed():
    global _timer_window
    api = get_api()
    if api:
        api.update_status("辩论计时器已关闭")
    _timer_window = None


# ============================================================
#  生命周期
# ============================================================

def on_enable():
    api = get_api()
    # 注册右侧导航栏按钮：点击直接打开计时器
    api.register_nav_button(
        side="right",
        emoji="⏱",
        label="计时",
        tooltip="打开辩论计时器",
        callback=show_timer,
    )
    api.update_status("辩论计时器已就绪！")


def on_disable():
    global _timer_window
    if _timer_window:
        _timer_window.close()
        _timer_window = None
    api = get_api()
    api.update_status("辩论计时器已停止")
