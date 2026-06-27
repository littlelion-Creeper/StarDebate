"""底层事件设置 UI — 使用 PyQt-SiliconUI 重构版组件

由 log_settings_page.py 的 build_page() 导入并调用。
"""

import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout,
)

# PyQt-SiliconUI 组件
from siui.components.widgets import SiLabel
from siui.components.button import SiSwitchRefactor
from siui.components.editbox import SiSpinBox
from siui.components.container import SiPanelCard
from siui.core import SiColor, SiGlobal
from siui.gui.font import SiFont

from components.theme_colors import tc
from workers.settings.pages._page_utils import (
    safe_set_style_data,
    add_silabel,
    make_transparent_row,
)

_logger = logging.getLogger("StarDebate.settings.native_log")


# ═══════════════════════════════════════
#  标签映射
# ═══════════════════════════════════════

NATIVE_HOOK_LABELS = {
    "qt_handler": ("Qt 内部错误 [L1]", "拦截 qWarning/qCritical/qFatal → SQLite"),
    "excepthook": ("未捕获异常 [L2]", "sys.excepthook 增强，含完整 traceback"),
    "unraisablehook": ("不可抛出异常 [L2]", "__del__/生成器/__exit__ 异常 (excepthook 盲区)"),
    "audithook": ("审计事件 [L2]", "import/open/socket/ctypes 审计事件记录"),
    "gc_callbacks": ("GC 回调 [L3]", "检测不可回收对象 + 可疑循环引用"),
    "c_exception_profile": ("C 异常 Profile [L2]", "C 函数异常跟踪 (⚠ 有性能开销，默认关闭)"),
}

NATIVE_THREAD_LABELS = {
    "stuck_threshold": ("线程卡死阈值", "秒", 5, 300, 5, 30.0),
    "deadlock_threshold": ("死锁嫌疑阈值", "秒", 10, 600, 10, 60.0),
}

NATIVE_RESOURCE_LABELS = {
    "fd_threshold": ("文件句柄阈值", "", 100, 10000, 100, 1000),
}

NATIVE_ADV_LABELS = {
    "max_per_second": ("同源节流", "条/秒", 1, 500, 10, 50),
}


# ═══════════════════════════════════════
#  辅助
# ═══════════════════════════════════════

def _add_switch_row(card, label_text: str, checked: bool,
                    description: str = "",
                    accent_color: str = None):
    """在卡片中构建一行: 左标签 + 右开关 + 可选描述。

    accent_color 为开启态背景色，默认取主题 accent_blue。
    """
    if accent_color is None:
        accent_color = tc("accent_blue")

    row = make_transparent_row(card)
    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(0, 4, 0, 0)
    row_layout.setSpacing(8)

    lbl = SiLabel(row)
    lbl.setText(label_text)
    lbl.setTextColor(lbl.getColor(SiColor.TEXT_B))
    lbl.setFont(SiFont.getFont(size=14))
    lbl.setStyleSheet("background: transparent;")
    lbl.setFixedHeight(28)
    row_layout.addWidget(lbl, stretch=1)

    sw = SiSwitchRefactor(row)
    sw.setChecked(checked)
    # SiSwitchRefactor 的视觉由 _progress 控制，setChecked 仅改内部状态不触发 clicked/动画
    sw._progress = 1.0 if checked else 0.0
    safe_set_style_data(sw, "background_color_starting", accent_color)
    safe_set_style_data(sw, "background_color_ending", accent_color)
    safe_set_style_data(sw, "frame_color", tc("border"))
    safe_set_style_data(sw, "thumb_color_checked", "white")
    safe_set_style_data(sw, "thumb_color_unchecked", tc("muted"))
    row_layout.addWidget(sw)

    card.addWidget(row)

    if description:
        desc = SiLabel(card)
        desc.setText(description)
        desc.setTextColor(desc.getColor(SiColor.TEXT_C))
        desc.setFont(SiFont.getFont(size=12))
        desc.setStyleSheet("background: transparent;")
        desc.setWordWrap(True)
        desc.setFixedHeight(20)
        card.addWidget(desc)

    return sw


def _set_spin_style(spin):
    """对 SiSpinBox 应用主题色。"""
    safe_set_style_data(spin, "title_background_color", tc("surface"))
    safe_set_style_data(spin, "title_color_idle", tc("muted"))
    safe_set_style_data(spin, "title_color_focused", tc("text"))
    safe_set_style_data(spin, "text_color", tc("text"))
    safe_set_style_data(spin, "text_background_color", tc("base"))
    safe_set_style_data(spin, "text_indicator_color_idle", tc("surface"))
    safe_set_style_data(spin, "text_indicator_color_editing", tc("accent_blue"))
    # 刷新内联 QSS（_initStyleSheet 将 text_color 写入 QLineEdit { color: ... }，
    # 但只在 __init__ 调用一次，后续修改 style_data 需要手动重建样式表）
    try:
        spin._initStyleSheet()
    except Exception:
        pass


# ═══════════════════════════════════════
#  构建卡片
# ═══════════════════════════════════════

def build_native_event_card(current_config: dict) -> tuple:
    """构建底层事件配置卡片。

    Returns:
        (card, dict_of_controls): SiPanelCard 容器和控件引用 dict
    """
    native_cfg = current_config.get("native_event", get_default_native_config())
    controls = {}

    # 创建 SiPanelCard
    card = SiPanelCard(None, direction=QBoxLayout.TopToBottom)
    safe_set_style_data(card, "background_fore_color", tc("surface"))
    safe_set_style_data(card, "background_back_color", tc("surface"))
    cl = card.layout()
    if cl is not None and hasattr(cl, "setSpacing"):
        cl.setSpacing(0)
    if hasattr(card, "muteStretchWidget"):
        card.muteStretchWidget()
    card.setContentsMargins(20, 18, 20, 18)

    # ── 标题 (H2: 16px / Caption: 12px) ──
    add_silabel(card, "底层事件记录 (Native Event Logging)", SiColor.TEXT_B, font_size=16)
    add_silabel(card,
                "标签: [NATIVE] [THREAD] [RES] [EXT] — 捕获比起居注更底层的信号源",
                SiColor.TEXT_C, word_wrap=True, font_size=12)

    # ── 总开关 ──
    sw_master = _add_switch_row(
        card, "启用底层事件记录",
        native_cfg.get("enabled", True),
        description="关闭后所有钩子和监视器静默跳过",
    )
    controls["sw_native_enabled"] = sw_master

    # ── 钩子开关分组 (H3: 14px) ──
    hooks_title = SiLabel(card)
    hooks_title.setText("── 钩子开关 (Hooks) ──")
    hooks_title.setTextColor(hooks_title.getColor(SiColor.TEXT_B))
    hooks_title.setFont(SiFont.getFont(size=14))
    hooks_title.setStyleSheet("background: transparent;")
    hooks_title.setFixedHeight(24)
    card.addWidget(hooks_title)

    hooks_cfg = native_cfg.get("hooks", {})
    hook_switches = {}
    for hook_key, (label, desc) in NATIVE_HOOK_LABELS.items():
        sw = _add_switch_row(
            card, label,
            hooks_cfg.get(hook_key, True),
            description=desc,
        )
        hook_switches[hook_key] = sw
    controls["hook_switches"] = hook_switches

    # ── 线程监视分组 (H3: 14px) ──
    thread_title = SiLabel(card)
    thread_title.setText("── 线程监视 ──")
    thread_title.setTextColor(thread_title.getColor(SiColor.TEXT_B))
    thread_title.setFont(SiFont.getFont(size=14))
    thread_title.setStyleSheet("background: transparent;")
    thread_title.setFixedHeight(24)
    card.addWidget(thread_title)

    thread_cfg = native_cfg.get("thread_monitor", {})
    for key, (label, suffix, min_v, max_v, step, default) in NATIVE_THREAD_LABELS.items():
        full_title = f"{label} ({suffix})" if suffix else label
        spin = SiSpinBox(card, title=full_title)
        spin.setMinimum(int(min_v))
        spin.setMaximum(int(max_v))
        spin.setSingleStep(int(step))
        spin.setValue(int(thread_cfg.get(key, default)))
        _set_spin_style(spin)
        card.addWidget(spin)
        controls[f"spin_{key}"] = spin

    # ── 资源监视分组 (H3: 14px) ──
    res_title = SiLabel(card)
    res_title.setText("── 资源监视 ──")
    res_title.setTextColor(res_title.getColor(SiColor.TEXT_B))
    res_title.setFont(SiFont.getFont(size=14))
    res_title.setStyleSheet("background: transparent;")
    res_title.setFixedHeight(24)
    card.addWidget(res_title)

    res_cfg = native_cfg.get("resource_monitor", {})
    for key, (label, suffix, min_v, max_v, step, default) in NATIVE_RESOURCE_LABELS.items():
        full_title = f"{label} ({suffix})" if suffix else label
        spin = SiSpinBox(card, title=full_title)
        spin.setMinimum(int(min_v))
        spin.setMaximum(int(max_v))
        spin.setSingleStep(int(step))
        spin.setValue(int(res_cfg.get(key, default)))
        _set_spin_style(spin)
        card.addWidget(spin)
        controls[f"spin_{key}"] = spin

    # ── 高级分组 (H3: 14px) ──
    adv_title = SiLabel(card)
    adv_title.setText("── 高级 ──")
    adv_title.setTextColor(adv_title.getColor(SiColor.TEXT_B))
    adv_title.setFont(SiFont.getFont(size=14))
    adv_title.setStyleSheet("background: transparent;")
    adv_title.setFixedHeight(24)
    card.addWidget(adv_title)

    throttle_cfg = native_cfg.get("throttle", {})
    for key, (label, suffix, min_v, max_v, step, default) in NATIVE_ADV_LABELS.items():
        full_title = f"{label} ({suffix})" if suffix else label
        spin = SiSpinBox(card, title=full_title)
        spin.setMinimum(int(min_v))
        spin.setMaximum(int(max_v))
        spin.setSingleStep(int(step))
        spin.setValue(int(throttle_cfg.get(key, default)))
        _set_spin_style(spin)
        card.addWidget(spin)
        controls[f"spin_{key}"] = spin

    # ── 性能提示 (Caption: 12px) ──
    perf_hint = SiLabel(card)
    perf_hint.setText(
        "⚠ 性能提示: c_exception Profile 启用 sys.setprofile，有显著开销。"
        " 建议仅在调试 CPU 不敏感的场景开启。"
    )
    perf_hint.setTextColor(perf_hint.getColor(SiColor.TEXT_C))
    perf_hint.setFont(SiFont.getFont(size=12))
    perf_hint.setStyleSheet("background: transparent;")
    perf_hint.setWordWrap(True)
    perf_hint.setFixedHeight(40)
    card.addWidget(perf_hint)

    # ── SQLite 路径 (Caption: 12px) ──
    path_hint = SiLabel(card)
    path_hint.setText(
        "🔗 数据文件: docs/log/native.db (自动保留最近 7 天 / 50000 条)"
    )
    path_hint.setTextColor(path_hint.getColor(SiColor.TEXT_C))
    path_hint.setFont(SiFont.getFont(size=12))
    path_hint.setStyleSheet("background: transparent;")
    path_hint.setWordWrap(True)
    path_hint.setFixedHeight(20)
    card.addWidget(path_hint)

    # ── 安全刷新 SiUI 样式 ──
    try:
        if SiGlobal.siui is not None and hasattr(SiGlobal.siui, "reloadStyleSheetRecursively"):
            SiGlobal.siui.reloadStyleSheetRecursively(card)
    except Exception:
        pass

    return card, controls


# ═══════════════════════════════════════
#  默认配置
# ═══════════════════════════════════════

def get_default_native_config() -> dict:
    """返回底层事件默认配置结构。"""
    return {
        "enabled": True,
        "hooks": {
            "qt_handler": True,
            "excepthook": True,
            "unraisablehook": True,
            "audithook": True,
            "gc_callbacks": True,
            "c_exception_profile": False,
        },
        "thread_monitor": {
            "stuck_threshold": 30,
            "deadlock_threshold": 60,
        },
        "resource_monitor": {
            "fd_threshold": 1000,
        },
        "throttle": {
            "max_per_second": 50,
        },
    }


# ═══════════════════════════════════════
#  收集配置
# ═══════════════════════════════════════

def collect_native_config(controls: dict) -> dict:
    """从控件收集底层事件配置。"""
    hooks = {}
    for key, sw in controls.get("hook_switches", {}).items():
        hooks[key] = sw.isChecked()

    config = {
        "enabled": controls["sw_native_enabled"].isChecked(),
        "hooks": hooks,
        "thread_monitor": {
            "stuck_threshold": controls["spin_stuck_threshold"].value(),
            "deadlock_threshold": controls["spin_deadlock_threshold"].value(),
        },
        "resource_monitor": {
            "fd_threshold": controls["spin_fd_threshold"].value(),
        },
        "throttle": {
            "max_per_second": controls["spin_max_per_second"].value(),
        },
    }
    return config
