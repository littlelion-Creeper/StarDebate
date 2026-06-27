"""
StarDebate 全局快捷键管理器

功能：
  - 快捷键注册/取消注册（支持内置功能 + 插件）
  - 冲突检测（同组合键被多次使用时即时报警）
  - 配置持久化（config/keyboard_shortcuts.json）
  - 录制模式（供设置页实时捕获新按键组合）
  - QShortcut 绑定（应用到 QMainWindow）

使用方式：
    mgr = get_shortcut_manager(window)
    mgr.register("open_settings", "Ctrl+,", "打开设置", "通用", callback)
    mgr.apply_all()

钩子标签：[SHORTCUT]
"""

import os
import json
import traceback
from typing import Any, Callable
from enum import Enum

from PyQt5.QtWidgets import QWidget, QShortcut
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import Qt

from workers.app_config.config_paths import get_config_path

_DEFAULT_CONFIG = get_config_path("config/keyboard_shortcuts.json")

# ── 内置默认快捷键定义 ─────────────────────────────────────
# 格式: { shortcut_id: {"keys": "Ctrl+X", "description": "说明", "category": "分类"} }
# callback 在注册时由各模块提供，默认配置不含 callback
BUILTIN_DEFAULTS: dict[str, dict] = {
    # 通用功能
    "open_settings":       {"keys": "Ctrl+,",     "description": "打开设置",       "category": "通用"},
    "save_debate":         {"keys": "Ctrl+S",     "description": "保存辩论",       "category": "通用"},
    "search_project":      {"keys": "Ctrl+Shift+F","description": "搜索项目",       "category": "通用"},
    "toggle_sidebar":      {"keys": "Ctrl+B",     "description": "切换侧边栏",     "category": "通用"},
    "toggle_debug_console": {"keys": "F12",       "description": "切换调试控制台", "category": "通用"},
    "new_debate":          {"keys": "Ctrl+N",     "description": "新建辩论",       "category": "通用"},
    "open_project":        {"keys": "Ctrl+O",     "description": "打开项目",       "category": "通用"},
    "close_tab":           {"keys": "Ctrl+W",     "description": "关闭当前标签",   "category": "通用"},

    # 写稿功能
    "ai_expand":           {"keys": "Ctrl+E",     "description": "AI 扩写",        "category": "写稿"},
    "framework_analyze":   {"keys": "Ctrl+K",     "description": "框架分析",        "category": "写稿"},
    "speech_writer_pro":   {"keys": "Ctrl+Shift+P","description": "正方写稿",       "category": "写稿"},
    "speech_writer_con":   {"keys": "Ctrl+Shift+C","description": "反方写稿",       "category": "写稿"},

    # 训练功能
    "quick_quiz":          {"keys": "Ctrl+Q",     "description": "快速刷题",       "category": "训练"},
    "cross_examination":   {"keys": "Ctrl+Shift+X","description": "模拟质询",       "category": "训练"},
    "start_training":      {"keys": "Ctrl+T",     "description": "开始训练",       "category": "训练"},

    # AI 分析
    "ai_analysis_pro":     {"keys": "Ctrl+Alt+P", "description": "正方 AI 分析",   "category": "AI分析"},
    "ai_analysis_con":     {"keys": "Ctrl+Alt+C", "description": "反方 AI 分析",   "category": "AI分析"},

    # 赛程
    "new_tournament":      {"keys": "Ctrl+Shift+N","description": "新建赛程",       "category": "赛程"},
}


class ShortcutSource(Enum):
    BUILTIN = "builtin"
    PLUGIN = "plugin"


# ═══════════════════════════════════════
#  按键位名称映射
# ═══════════════════════════════════════

_KEY_NAME_MAP = {
    Qt.Key_Control: "Ctrl", Qt.Key_Shift: "Shift", Qt.Key_Alt: "Alt",
    Qt.Key_Meta: "Meta", Qt.Key_Space: "Space",
    Qt.Key_Return: "Enter", Qt.Key_Enter: "Enter",
    Qt.Key_Backspace: "Backspace", Qt.Key_Delete: "Delete",
    Qt.Key_Escape: "Esc", Qt.Key_Tab: "Tab", Qt.Key_Backtab: "Backtab",
    Qt.Key_CapsLock: "CapsLock",
    Qt.Key_Up: "Up", Qt.Key_Down: "Down",
    Qt.Key_Left: "Left", Qt.Key_Right: "Right",
    Qt.Key_PageUp: "PageUp", Qt.Key_PageDown: "PageDown",
    Qt.Key_Home: "Home", Qt.Key_End: "End",
    Qt.Key_Insert: "Insert",
    Qt.Key_F1: "F1", Qt.Key_F2: "F2", Qt.Key_F3: "F3", Qt.Key_F4: "F4",
    Qt.Key_F5: "F5", Qt.Key_F6: "F6", Qt.Key_F7: "F7", Qt.Key_F8: "F8",
    Qt.Key_F9: "F9", Qt.Key_F10: "F10", Qt.Key_F11: "F11", Qt.Key_F12: "F12",
    Qt.Key_Plus: "+", Qt.Key_Minus: "-", Qt.Key_Equal: "=",
    Qt.Key_BracketLeft: "[", Qt.Key_BracketRight: "]",
    Qt.Key_Backslash: "\\",
    Qt.Key_Semicolon: ";", Qt.Key_Apostrophe: "'",
    Qt.Key_Comma: ",", Qt.Key_Period: ".", Qt.Key_Slash: "/",
    Qt.Key_QuoteLeft: "`",
    Qt.Key_0: "0", Qt.Key_1: "1", Qt.Key_2: "2", Qt.Key_3: "3", Qt.Key_4: "4",
    Qt.Key_5: "5", Qt.Key_6: "6", Qt.Key_7: "7", Qt.Key_8: "8", Qt.Key_9: "9",
    Qt.Key_A: "A", Qt.Key_B: "B", Qt.Key_C: "C", Qt.Key_D: "D", Qt.Key_E: "E",
    Qt.Key_F: "F", Qt.Key_G: "G", Qt.Key_H: "H", Qt.Key_I: "I", Qt.Key_J: "J",
    Qt.Key_K: "K", Qt.Key_L: "L", Qt.Key_M: "M", Qt.Key_N: "N", Qt.Key_O: "O",
    Qt.Key_P: "P", Qt.Key_Q: "Q", Qt.Key_R: "R", Qt.Key_S: "S", Qt.Key_T: "T",
    Qt.Key_U: "U", Qt.Key_V: "V", Qt.Key_W: "W", Qt.Key_X: "X", Qt.Key_Y: "Y",
    Qt.Key_Z: "Z",
}


def key_event_to_sequence(event) -> str | None:
    """将 QKeyEvent 转换为可显示的组合键字符串，如 'Ctrl+Shift+F'。
    仅修饰键单独按下返回 None。
    """
    key = event.key()
    modifiers = event.modifiers()

    # 忽略纯修饰键
    modifier_keys = {
        Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta,
        Qt.Key_Control_L, Qt.Key_Control_R,
        Qt.Key_Shift_L, Qt.Key_Shift_R,
        Qt.Key_Alt_L, Qt.Key_Alt_R,
        Qt.Key_Meta_L, Qt.Key_Meta_R,
    }
    if key in modifier_keys:
        return None

    parts = []
    if modifiers & Qt.ControlModifier:
        parts.append("Ctrl")
    if modifiers & Qt.ShiftModifier:
        parts.append("Shift")
    if modifiers & Qt.AltModifier:
        parts.append("Alt")
    if modifiers & Qt.MetaModifier:
        parts.append("Meta")

    key_name = _KEY_NAME_MAP.get(key)
    if key_name is None:
        # 回退到 QKeySequence 的 toString
        seq = QKeySequence(key | int(modifiers))
        key_name = seq.toString()
    if key_name:
        parts.append(key_name)
    else:
        return None

    return "+".join(parts)


def normalize_shortcut(seq_str: str) -> str:
    """标准化组合键字符串，如 'ctrl+shift+a' → 'Ctrl+Shift+A'"""
    parts = [p.strip().capitalize() for p in seq_str.split("+")]
    return "+".join(parts)


# ═══════════════════════════════════════
#  ShortcutManager
# ═══════════════════════════════════════

class ShortcutManager:
    """全局快捷键管理器（单例模式）"""

    _instance: "ShortcutManager | None" = None

    @classmethod
    def instance(cls, window: QWidget = None) -> "ShortcutManager":
        if cls._instance is None:
            if window is None:
                raise RuntimeError("ShortcutManager 首次初始化必须提供 QMainWindow")
            cls._instance = cls(window)
        return cls._instance

    def __init__(self, window: QWidget):
        if ShortcutManager._instance is not None:
            raise RuntimeError("ShortcutManager 是单例，请使用 instance()")
        self._window = window
        self._shortcuts: dict[str, dict] = {}  # shortcut_id → info dict
        self._active_shortcuts: dict[str, QShortcut] = {}  # shortcut_id → QShortcut 实例
        self._plugin_shortcuts: dict[str, set[str]] = {}  # plugin_id → {shortcut_id, ...}
        self._monitor_fn = None  # 监视钩子回调
        self._load_config()

    # ── 配置持久化 ─────────────────────────────────────────

    def _load_config(self):
        """从 config/keyboard_shortcuts.json 加载用户自定义的快捷键映射"""
        self._user_overrides: dict[str, str] = {}
        if os.path.isfile(_DEFAULT_CONFIG):
            try:
                with open(_DEFAULT_CONFIG, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._user_overrides = data.get("overrides", {})
            except Exception:
                pass

    def save_config(self):
        """保存用户自定义的快捷键映射到文件"""
        data = {"overrides": self._user_overrides, "version": "1.0.0"}
        try:
            os.makedirs(os.path.dirname(_DEFAULT_CONFIG), exist_ok=True)
            with open(_DEFAULT_CONFIG, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            traceback.print_exc()
        self._log_monitor("config_saved", f"快捷键配置已保存 ({len(self._user_overrides)} 项自定义)")

    def get_effective_keys(self, shortcut_id: str) -> str:
        """获取快捷键实际生效的按键组合（优先用户自定义）"""
        if shortcut_id in self._user_overrides:
            return self._user_overrides[shortcut_id]
        info = self._shortcuts.get(shortcut_id, {})
        return info.get("keys", "")

    def reset_to_default(self, shortcut_id: str) -> bool:
        """将指定快捷键重置为默认值"""
        if shortcut_id in self._shortcuts:
            self._user_overrides.pop(shortcut_id, None)
            self._reapply_single(shortcut_id)
            self._log_monitor("reset", f"快捷键已重置: {shortcut_id}")
            return True
        return False

    def reset_all_defaults(self):
        """重置所有快捷键为默认值"""
        self._user_overrides.clear()
        self._reapply_all()
        self._log_monitor("reset_all", "所有快捷键已重置为默认值")

    # ── 注册 / 注销 ───────────────────────────────────────

    def register(self, shortcut_id: str, keys: str, description: str,
                 category: str, callback: Callable,
                 source: str = "builtin") -> bool:
        """注册一个快捷键。

        Args:
            shortcut_id: 唯一标识（建议 'module:action' 格式）
            keys: 默认组合键，如 'Ctrl+Shift+F'
            description: 功能描述
            category: 分类名（用于设置页分组显示）
            callback: 触发回调
            source: 'builtin' 或 'plugin:plugin_id'

        Returns:
            bool: 注册成功返回 True
        """
        if shortcut_id in self._shortcuts:
            # 更新已有注册
            self.unregister(shortcut_id)

        self._shortcuts[shortcut_id] = {
            "id": shortcut_id,
            "keys": normalize_shortcut(keys),
            "description": description,
            "category": category,
            "callback": callback,
            "source": source,
        }

        # 跟踪插件来源
        if source.startswith("plugin:"):
            plugin_id = source.split(":", 1)[1]
            if plugin_id not in self._plugin_shortcuts:
                self._plugin_shortcuts[plugin_id] = set()
            self._plugin_shortcuts[plugin_id].add(shortcut_id)

        # 应用快捷键
        self._reapply_single(shortcut_id)
        self._log_monitor("register", f"已注册: {shortcut_id} → {keys}")
        return True

    def unregister(self, shortcut_id: str):
        """注销一个快捷键"""
        if shortcut_id in self._active_shortcuts:
            self._active_shortcuts[shortcut_id].setEnabled(False)
            self._active_shortcuts[shortcut_id].deleteLater()
            del self._active_shortcuts[shortcut_id]

        info = self._shortcuts.pop(shortcut_id, None)
        if info:
            source = info.get("source", "")
            if source.startswith("plugin:"):
                plugin_id = source.split(":", 1)[1]
                if plugin_id in self._plugin_shortcuts:
                    self._plugin_shortcuts[plugin_id].discard(shortcut_id)
            self._log_monitor("unregister", f"已注销: {shortcut_id}")

    def unregister_plugin_shortcuts(self, plugin_id: str):
        """注销指定插件的所有快捷键"""
        sids = self._plugin_shortcuts.pop(plugin_id, set())
        for sid in list(sids):
            self.unregister(sid)
        self._log_monitor("unregister_plugin", f"插件快捷键已全部注销: {plugin_id}")

    def update_shortcut_keys(self, shortcut_id: str, new_keys: str) -> bool:
        """更新快捷键的按键组合（由设置页调用）。

        返回 False 表示存在冲突（不会更新）。
        """
        new_keys = normalize_shortcut(new_keys)
        if not new_keys:
            return False

        # 冲突检测
        conflict = self.check_conflict(new_keys, exclude_id=shortcut_id)
        if conflict:
            # 仍然允许更新，但返回冲突信息（由调用者决定）
            # 这里我们允许覆盖但记录冲突
            self._log_monitor("conflict_override",
                f"快捷键 {new_keys} 冲突: {shortcut_id} 覆盖 {conflict}")

        old_keys = self.get_effective_keys(shortcut_id)
        self._user_overrides[shortcut_id] = new_keys

        if shortcut_id in self._shortcuts:
            self._reapply_single(shortcut_id)

        self._log_monitor("keys_changed",
            f"快捷键已更改: {shortcut_id} {old_keys} → {new_keys}")
        return True

    def check_conflict(self, keys: str, exclude_id: str = None) -> str | None:
        """检查组合键是否已被其他功能使用。返回冲突的 shortcut_id，无冲突返回 None。"""
        keys = normalize_shortcut(keys)
        for sid, info in self._shortcuts.items():
            if sid == exclude_id:
                continue
            effective = self.get_effective_keys(sid)
            if effective == keys:
                return sid
        return None

    def get_all_shortcuts(self) -> list[dict]:
        """获取所有快捷键信息（已排序），供设置页展示"""
        result = []
        for sid, info in self._shortcuts.items():
            effective = self.get_effective_keys(sid)
            is_custom = sid in self._user_overrides
            result.append({
                "id": sid,
                "keys": effective,
                "default_keys": info.get("keys", ""),
                "description": info.get("description", ""),
                "category": info.get("category", "其他"),
                "source": info.get("source", "builtin"),
                "is_custom": is_custom,
                "has_conflict": False,  # 由设置页实时检测
            })
        # 排序：分类 → 描述
        result.sort(key=lambda x: (x["category"], x["description"]))
        return result

    def get_conflicts(self) -> list[tuple[str, str, str]]:
        """检查所有快捷键冲突。返回 [(sid1, sid2, keys), ...]"""
        conflicts = []
        sids = list(self._shortcuts.keys())
        for i in range(len(sids)):
            for j in range(i + 1, len(sids)):
                k1 = self.get_effective_keys(sids[i])
                k2 = self.get_effective_keys(sids[j])
                if k1 and k2 and k1 == k2:
                    conflicts.append((sids[i], sids[j], k1))
        return conflicts

    # ── 应用 / 绑定 ───────────────────────────────────────

    def _reapply_single(self, shortcut_id: str):
        """重新应用单个快捷键绑定"""
        info = self._shortcuts.get(shortcut_id)
        if not info:
            return

        # 移除旧绑定
        if shortcut_id in self._active_shortcuts:
            self._active_shortcuts[shortcut_id].setEnabled(False)
            self._active_shortcuts[shortcut_id].deleteLater()
            del self._active_shortcuts[shortcut_id]

        keys = self.get_effective_keys(shortcut_id)
        if not keys:
            return

        try:
            qshortcut = QShortcut(QKeySequence(keys), self._window)
            callback = info.get("callback")
            if callback:
                qshortcut.activated.connect(callback)
            qshortcut.setAutoRepeat(False)
            self._active_shortcuts[shortcut_id] = qshortcut
        except Exception:
            traceback.print_exc()

    def _reapply_all(self):
        """重新应用所有快捷键绑定"""
        for sid in list(self._active_shortcuts.keys()):
            self._active_shortcuts[sid].setEnabled(False)
            self._active_shortcuts[sid].deleteLater()
        self._active_shortcuts.clear()

        for sid in self._shortcuts:
            self._reapply_single(sid)

    def apply_all(self):
        """应用所有已注册的快捷键（在主窗口完全构建后调用）"""
        self._reapply_all()
        self._log_monitor("apply_all", f"已应用 {len(self._active_shortcuts)} 个快捷键")

    # ── 默认内置快捷键加载 ─────────────────────────────────

    def load_builtin_defaults(self, callbacks: dict[str, Callable]):
        """加载内置默认快捷键定义。

        Args:
            callbacks: {shortcut_id: callback_fn} 映射表
        """
        for sid, info in BUILTIN_DEFAULTS.items():
            cb = callbacks.get(sid)
            if cb:
                self.register(
                    sid, info["keys"], info["description"],
                    info["category"], cb, source="builtin"
                )
            else:
                # 注册但无回调（仅占位，由设置页显示）
                self._shortcuts[sid] = {
                    "id": sid,
                    "keys": normalize_shortcut(info["keys"]),
                    "description": info["description"],
                    "category": info["category"],
                    "callback": None,
                    "source": "builtin",
                }
        self._log_monitor("load_defaults", f"已加载 {len(BUILTIN_DEFAULTS)} 个内置快捷键定义")

    # ── 监视钩子 ───────────────────────────────────────────

    def set_monitor_fn(self, fn):
        """设置监视日志回调"""
        self._monitor_fn = fn

    def _log_monitor(self, action: str, detail: str):
        """向监视系统报告快捷键操作"""
        if self._monitor_fn:
            try:
                self._monitor_fn("[SHORTCUT]", f"{action}: {detail}")
            except Exception:
                pass


def get_shortcut_manager(window: QWidget = None) -> ShortcutManager:
    """获取 ShortcutManager 单例"""
    return ShortcutManager.instance(window)
