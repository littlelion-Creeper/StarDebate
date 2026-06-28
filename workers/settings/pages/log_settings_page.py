"""
日志系统设置页 — 使用 PyQt-SiliconUI 重构版组件
========================================================================
提供日志系统的集中可视化配置，整合以下子系统：

  - DebugMonitorManager (5 项监视开关)
  - ActivityChronicle   (4 类别起居注开关)
  - NativeEventLogging  (6 钩子 + 线程/资源/节流)
  - LogService          (清理/保留策略)

配置持久化: config/log_settings.json
========================================================================
"""

import json
import os
import logging

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
)

# PyQt-SiliconUI 组件
from siui.components.widgets import SiLabel
from siui.components.button import SiSwitchRefactor
from siui.components.editbox import SiSpinBox, SiDoubleSpinBox
from siui.core import SiColor, SiGlobal
from siui.gui.font import SiFont

from components.theme_colors import tc

# 共享设置页工具函数
from workers.settings.pages._page_utils import (
    safe_set_style_data,
    safe_create_card,
    add_silabel,
    make_transparent_row,
)

_logger = logging.getLogger("StarDebate.settings.log_settings")


# ═══════════════════════════════════════
#  页面元信息（由 SettingsDialog 自动扫描读取）
# ═══════════════════════════════════════

PAGE_INFO = {
    "id": "log_settings",
    "name": "日志",
    "icon": "log",
    "order": 50,
    "author": "StarDebate",
    "version": "3.0.0",
}

PAGE_CONFIG = {
    "save_path": "config/log_settings.json",
    "auto_save": True,
}


# ═══════════════════════════════════════
#  默认配置
# ═══════════════════════════════════════

def get_default_config() -> dict:
    return {
        "version": 1,
        "master_enabled": True,

        "debug_monitor": {
            "enabled": False,
            "monitors": {
                "variable_watch": False,
                "function_watch": False,
                "plugin_watch": False,
                "api_watch": False,
                "ai_watch": False,
            },
            "function_min_duration_ms": 0,
        },

        "chronicle": {
            "enabled": True,
            "categories_active": {
                "feature": True,
                "plugin": True,
                "api": True,
                "ai": True,
            },
            "min_duration_ms": 0,
            "max_duration_ms": {
                "feature": 0,
                "api": 0,
                "ai": 0,
                "plugin": 0,
            },
            "capture_traceback": True,
            "snapshot_interval_s": 2.0,
        },

        "log_service": {
            "auto_clean": True,
            "keep_normal_exit_log": False,
        },

        "native_event": {
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
        },
    }


# ═══════════════════════════════════════
#  数据常量
# ═══════════════════════════════════════

MONITOR_LABELS_CN = {
    "variable_watch": "变量监视 [VAR]",
    "function_watch": "函数监视 [FUNC]",
    "plugin_watch": "插件监视 [PLUGIN]",
    "api_watch": "API 监视 [API]",
    "ai_watch": "AI 监视 [AI]",
}

MONITOR_DESCRIPTIONS = {
    "variable_watch": "记录全局变量/属性值的变化",
    "function_watch": "记录函数调用的结果与耗时",
    "plugin_watch": "记录插件加载/启用/禁用状态",
    "api_watch": "记录 HTTP API 请求详情",
    "ai_watch": "记录 AI 功能业务结果",
}

CHRONICLE_CATEGORIES_CN = {
    "feature": "功能运行追踪",
    "plugin": "插件加载追踪",
    "api": "API 调用追踪",
    "ai": "AI 调用追踪",
}

CHRONICLE_CATEGORY_EXAMPLES = {
    "feature": "✅ feature·xxx → ok (ms)",
    "plugin": "▶  plugin·xxx → ok",
    "api": "✓  api·xxx → ok (ms)",
    "ai": "✅ ai·call_ai → ok (ms)",
}


# ═══════════════════════════════════════
#  辅助函数 — 构建 SiSwitchRefactor 行
# ═══════════════════════════════════════

def _add_switch_row(card, label_text: str, checked: bool,
                    description: str = "",
                    accent_color: str = None):
    """在卡片中构建一行: 左标签 + 右开关 + 可选描述。

    accent_color 为开启态背景色，默认取主题 accent_blue。
    Returns:
        SiSwitchRefactor: 创建的开关控件
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
    """对 SiSpinBox/SiDoubleSpinBox 应用主题色。"""
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
#  构建页面
# ═══════════════════════════════════════

def build_page(parent_dialog, current_config: dict) -> QWidget:
    """构建日志设置页。

    Args:
        parent_dialog: SettingsDialog 实例
        current_config: 当前配置 dict (来自 log_settings.json 或默认值)

    Returns:
        QWidget: 页面内容
    """
    # 安全兜底：SystemError 是 BaseException，不继承 Exception，需要额外保护
    try:
        return _build_page_impl(parent_dialog, current_config)
    except BaseException:
        _logger.exception("日志设置页 build_page 崩溃")
        # 返回一个极简占位页面，防止 SettingsDialog 切换页面时崩溃
        fallback = QWidget()
        fallback.setObjectName("settingsPage")
        _logger.info("已返回日志设置页占位组件")
        return fallback


def _build_page_impl(parent_dialog, current_config: dict) -> QWidget:
    """日志设置页实现（内层，被 build_page 兜底保护）。"""
    page = QWidget()
    page.setObjectName("settingsPage")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)

    cfg = current_config or get_default_config()

    # ── 页标题 (H1: 20px) ──
    add_silabel(page, "日志设置", SiColor.TEXT_A, font_size=20)
    add_silabel(page, "统一管理调试监视、起居注、日志服务、底层事件开关",
                SiColor.TEXT_C, word_wrap=True, font_size=13)

    # ═══════════════════════════════════════
    #  ① 日志系统总开关
    # ═══════════════════════════════════════
    master_card = safe_create_card(page)
    add_silabel(master_card, "日志系统总开关", SiColor.TEXT_B, font_size=16)
    add_silabel(master_card,
                "关闭后将禁用所有日志监视与起居注（LogService 进程不受影响）",
                SiColor.TEXT_C, word_wrap=True, font_size=12)

    cb_master = _add_switch_row(
        master_card, "启用日志系统",
        cfg.get("master_enabled", True),
    )
    layout.addWidget(master_card)

    # ═══════════════════════════════════════
    #  ② 调试监视
    # ═══════════════════════════════════════
    monitor_cfg = cfg.get("debug_monitor", {})
    monitors = monitor_cfg.get("monitors", {})

    monitor_card = safe_create_card(page)
    add_silabel(monitor_card, "调试监视 (DebugMonitor)", SiColor.TEXT_B, font_size=16)
    add_silabel(monitor_card,
                "标签: [VAR] [FUNC] [PLUGIN] [API] [AI]",
                SiColor.TEXT_C, word_wrap=True, font_size=12)

    cb_monitor_enabled = _add_switch_row(
        monitor_card, "启用调试监视",
        monitor_cfg.get("enabled", False),
    )

    # 5 项监视独立开关
    monitor_checkboxes = {}
    for mtype in ["variable_watch", "function_watch", "plugin_watch",
                  "api_watch", "ai_watch"]:
        cb = _add_switch_row(
            monitor_card,
            MONITOR_LABELS_CN.get(mtype, mtype),
            monitors.get(mtype, False),
            description=MONITOR_DESCRIPTIONS.get(mtype, ""),
        )
        monitor_checkboxes[mtype] = cb

    # 函数最低耗时阈值
    spin_min_dur = SiSpinBox(monitor_card, title="函数最低耗时阈值 (ms)")
    spin_min_dur.setMinimum(0)
    spin_min_dur.setMaximum(10000)
    spin_min_dur.setSingleStep(100)
    spin_min_dur.setValue(monitor_cfg.get("function_min_duration_ms", 0))
    _set_spin_style(spin_min_dur)
    monitor_card.addWidget(spin_min_dur)

    layout.addWidget(monitor_card)

    # ═══════════════════════════════════════
    #  ③ 起居注
    # ═══════════════════════════════════════
    chronicle_cfg = cfg.get("chronicle", {})
    categories = chronicle_cfg.get("categories_active", {})

    chronicle_card = safe_create_card(page)
    add_silabel(chronicle_card, "起居注 (ActivityChronicle)", SiColor.TEXT_B, font_size=16)
    add_silabel(chronicle_card,
                "标签: [CRON] — 自动记录操作成功/失败，无需修改代码",
                SiColor.TEXT_C, word_wrap=True, font_size=12)

    cb_chronicle_enabled = _add_switch_row(
        chronicle_card, "启用起居注 [CRON]",
        chronicle_cfg.get("enabled", True),
    )

    # 4 类别独立开关
    chronicle_checkboxes = {}
    for cat in ["feature", "plugin", "api", "ai"]:
        cb = _add_switch_row(
            chronicle_card,
            CHRONICLE_CATEGORIES_CN.get(cat, cat),
            categories.get(cat, True),
            description=CHRONICLE_CATEGORY_EXAMPLES.get(cat, ""),
        )
        chronicle_checkboxes[cat] = cb

    # 最低记录耗时
    spin_chron_dur = SiSpinBox(chronicle_card, title="最低记录耗时 (ms)")
    spin_chron_dur.setMinimum(0)
    spin_chron_dur.setMaximum(60000)
    spin_chron_dur.setSingleStep(100)
    spin_chron_dur.setValue(chronicle_cfg.get("min_duration_ms", 0))
    _set_spin_style(spin_chron_dur)
    chronicle_card.addWidget(spin_chron_dur)

    # 崩溃定位增强 (H3: 14px)
    crash_title = SiLabel(chronicle_card)
    crash_title.setText("崩溃定位增强 (v2.7.0)")
    crash_title.setTextColor(crash_title.getColor(SiColor.TEXT_B))
    crash_title.setFont(SiFont.getFont(size=14))
    crash_title.setStyleSheet("background: transparent;")
    crash_title.setFixedHeight(24)
    chronicle_card.addWidget(crash_title)

    # 完整 traceback 开关
    cb_capture_tb = _add_switch_row(
        chronicle_card, "捕获完整异常堆栈",
        chronicle_cfg.get("capture_traceback", True),
        description="记录未处理异常的完整 traceback 到起居注日志",
    )

    # 快照间隔
    spin_snap = SiDoubleSpinBox(chronicle_card, title="操作路径快照间隔 (秒)")
    spin_snap.setMinimum(0)
    spin_snap.setMaximum(30)
    spin_snap.setSingleStep(1)
    spin_snap.setValue(chronicle_cfg.get("snapshot_interval_s", 2.0))
    _set_spin_style(spin_snap)
    chronicle_card.addWidget(spin_snap)

    layout.addWidget(chronicle_card)

    # ═══════════════════════════════════════
    #  ④ 日志服务
    # ═══════════════════════════════════════
    service_cfg = cfg.get("log_service", {})

    service_card = safe_create_card(page)
    add_silabel(service_card, "日志服务 (LogService)", SiColor.TEXT_B, font_size=16)
    add_silabel(service_card,
                "日志文件的存储与清理策略",
                SiColor.TEXT_C, word_wrap=True, font_size=12)

    cb_auto_clean = _add_switch_row(
        service_card, "自动清理过期日志",
        service_cfg.get("auto_clean", True),
        description="启动时自动删除 docs/log/ 下超过 7 天的 debug_*.log 文件",
    )

    cb_keep_normal = _add_switch_row(
        service_card, "保留正常退出日志",
        service_cfg.get("keep_normal_exit_log", False),
        description="程序正常退出时保留日志文件（关闭时正常退出将自动删除日志）",
    )

    layout.addWidget(service_card)

    # ═══════════════════════════════════════
    #  ⑤ 底层事件记录
    # ═══════════════════════════════════════
    from workers.settings.pages.native_log_settings_ui import (
        build_native_event_card, collect_native_config
    )

    native_card, native_controls = build_native_event_card(cfg)
    layout.addWidget(native_card)

    # 弹性空间
    layout.addStretch()

    # ═══════════════════════════════════════
    #  存储控件引用到 page (供 collect_config 使用)
    # ═══════════════════════════════════════
    page._cb_master = cb_master

    page._cb_monitor_enabled = cb_monitor_enabled
    page._monitor_checkboxes = monitor_checkboxes
    page._spin_min_dur = spin_min_dur

    page._cb_chronicle_enabled = cb_chronicle_enabled
    page._chronicle_checkboxes = chronicle_checkboxes
    page._spin_chron_dur = spin_chron_dur
    page._cb_capture_tb = cb_capture_tb
    page._spin_snap = spin_snap

    page._cb_auto_clean = cb_auto_clean
    page._cb_keep_normal = cb_keep_normal

    page._native_controls = native_controls
    page._collect_native_config = collect_native_config

    # ── 安全刷新 SiUI 样式 ──
    try:
        if SiGlobal.siui is not None and hasattr(SiGlobal.siui, "reloadStyleSheetRecursively"):
            SiGlobal.siui.reloadStyleSheetRecursively(page)
    except Exception:
        pass

    return page


# ═══════════════════════════════════════
#  收集配置
# ═══════════════════════════════════════

def collect_config(page_widget: QWidget) -> dict:
    """从页面控件收集当前配置并返回 dict。"""
    monitors_enabled = {}
    for mtype, sw in page_widget._monitor_checkboxes.items():
        monitors_enabled[mtype] = sw.isChecked()

    categories_enabled = {}
    for cat, sw in page_widget._chronicle_checkboxes.items():
        categories_enabled[cat] = sw.isChecked()

    config = {
        "version": 1,
        "master_enabled": page_widget._cb_master.isChecked(),

        "debug_monitor": {
            "enabled": page_widget._cb_monitor_enabled.isChecked(),
            "monitors": monitors_enabled,
            "function_min_duration_ms": page_widget._spin_min_dur.value(),
        },

        "chronicle": {
            "enabled": page_widget._cb_chronicle_enabled.isChecked(),
            "categories_active": categories_enabled,
            "min_duration_ms": page_widget._spin_chron_dur.value(),
            "max_duration_ms": {
                "feature": 0,
                "api": 0,
                "ai": 0,
                "plugin": 0,
            },
            "capture_traceback": page_widget._cb_capture_tb.isChecked(),
            "snapshot_interval_s": page_widget._spin_snap.value(),
        },

        "log_service": {
            "auto_clean": page_widget._cb_auto_clean.isChecked(),
            "keep_normal_exit_log": page_widget._cb_keep_normal.isChecked(),
        },

        "native_event": page_widget._collect_native_config(
            page_widget._native_controls
        ),
    }

    _apply_to_runtime(page_widget, config)

    return config


# ═══════════════════════════════════════
#  运行时同步
# ═══════════════════════════════════════

def _apply_to_runtime(page_widget: QWidget, config: dict):
    """将配置变更同步到各运行时组件。"""
    try:
        mw = _get_main_window(page_widget)
        if mw is None:
            return

        # ── ① 同步 DebugMonitorManager ──
        from workers.debug_console.debug_monitor_manager import DebugMonitorManager
        mgr = DebugMonitorManager.instance()

        master_enabled = config.get("master_enabled", True)
        monitor_cfg = config.get("debug_monitor", {})

        mgr.enabled = master_enabled and monitor_cfg.get("enabled", False)
        for mtype, enabled in monitor_cfg.get("monitors", {}).items():
            mgr.set_monitor(mtype, enabled)

        mgr._config.setdefault("options", {})
        mgr._config["options"]["function_min_duration_ms"] = (
            monitor_cfg.get("function_min_duration_ms", 0)
        )
        mgr._save_config()

        # ── ② 同步 ActivityChronicle ──
        if hasattr(mw, '_log_client') and mw._log_client:
            chronicle_cfg = config.get("chronicle", {})
            chronicle_enabled = master_enabled and chronicle_cfg.get("enabled", True)
            mw._log_client.chronicle_enabled = chronicle_enabled

            from components.res_path import get_resource_root
            chronicle_config_path = os.path.join(
                get_resource_root(),
                "config", "chronicle_config.json"
            )
            try:
                chronicle_config = {
                    "enabled": chronicle_enabled,
                    "categories": chronicle_cfg.get("categories_active", {}),
                    "min_duration_ms": chronicle_cfg.get("min_duration_ms", 0),
                    "max_duration_ms": chronicle_cfg.get("max_duration_ms", {
                        "feature": 0, "api": 0, "ai": 0, "plugin": 0
                    }),
                    "log_level": "INFO",
                    "snapshot_interval_s": chronicle_cfg.get("snapshot_interval_s", 2.0),
                    "capture_traceback": chronicle_cfg.get("capture_traceback", True),
                    "keep_ring_log_lines": 200,
                }
                os.makedirs(os.path.dirname(chronicle_config_path), exist_ok=True)
                with open(chronicle_config_path, "w", encoding="utf-8") as f:
                    json.dump(chronicle_config, f, indent=4, ensure_ascii=False)
            except Exception:
                pass

    except Exception:
        pass


def _get_main_window(page_widget: QWidget):
    """向上遍历获取主窗口引用。"""
    try:
        parent = page_widget.parent()
        while parent:
            if hasattr(parent, '_log_client'):
                return parent
            parent = parent.parent()
    except Exception:
        pass
    return None
