from components.theme_colors import tc, refresh
"""
快捷键设置页：浏览、搜索、录制修改所有快捷键

功能：
  - 按分类分组展示所有快捷键
  - 搜索框实时过滤
  - 🎬 录制模式：点击按钮后按下新组合键
  - ↺ 重置单个快捷键为默认值
  - 冲突检测与红色高亮
  - 插件快捷键自动展示
"""

import os
import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QLineEdit,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeyEvent


# ═══════════════════════════════════════
#  页面元信息
# ═══════════════════════════════════════

PAGE_INFO = {
    "id": "keyboard_shortcuts",
    "name": "快捷键",
    "icon": "⌨️",
    "order": 45,
    "author": "StarDebate",
    "version": "1.0.0",
}

PAGE_CONFIG = {
    "save_path": "",
    "auto_save": False,  # 快捷键配置由 ShortcutManager 自行管理
}


def get_default_config() -> dict:
    return {}


# ═══════════════════════════════════════
#  按键录制按钮
# ═══════════════════════════════════════

class KeyRecorderButton(QPushButton):
    """可进入录制模式的按钮，按下后捕获键盘组合键。

    Signals:
        key_recorded(str): 录制完成，发射组合键字符串
    """
    key_recorded = pyqtSignal(str)

    def __init__(self, current_keys: str, parent=None):
        super().__init__(parent)
        self._current_keys = current_keys
        self._recording = False
        self._default_text = current_keys if current_keys else "点击录制"
        self.setText(self._default_text)
        self.setObjectName("settingsKeyRecorder")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(30)
        self.setMinimumWidth(120)
        self.clicked.connect(self._toggle_recording)

    def _toggle_recording(self):
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self._recording = True
        self.setText("按下组合键...")
        self.setStyleSheet(self._recording_style())
        self.grabKeyboard()
        self.setFocus()

    def _stop_recording(self):
        self._recording = False
        self.releaseKeyboard()
        self.setText(self._current_keys if self._current_keys else "点击录制")
        self.setStyleSheet("")

    def keyPressEvent(self, event: QKeyEvent):
        if not self._recording:
            super().keyPressEvent(event)
            return

        from workers.shortcuts.shortcut_manager import key_event_to_sequence
        seq = key_event_to_sequence(event)
        if seq is None:
            return

        self._current_keys = seq
        self._stop_recording()
        self.setText(seq)
        self.key_recorded.emit(seq)

    def set_current_keys(self, keys: str):
        self._current_keys = keys
        if not self._recording:
            self.setText(keys if keys else "点击录制")

    def _recording_style(self) -> str:
        return (
            "QPushButton {"
            "  background-color: #a6e3a1;"
            "  color: #1e1e2e;"
            "  border: 2px solid #a6e3a1;"
            "  border-radius: 6px;"
            "  font-size: 12px;"
            "  font-weight: bold;"
            "  padding: 4px 10px;"
            "}"
        )


# ═══════════════════════════════════════
#  快捷键行 widget
# ═══════════════════════════════════════

class ShortcutRow(QWidget):
    """单行快捷键条目：功能名 + 快捷键显示 + 录制按钮 + 重置按钮"""

    shortcut_changed = pyqtSignal(str, str)   # (shortcut_id, new_keys)
    shortcut_reset = pyqtSignal(str)          # shortcut_id

    ROW_HEIGHT = 44
    COL_DESC = 0
    COL_KEYS = 1
    COL_ACTIONS = 2

    def __init__(self, shortcut_data: dict, parent=None):
        super().__init__(parent)
        self._data = shortcut_data
        self.setFixedHeight(self.ROW_HEIGHT)
        self.setObjectName("shortcutRow")
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(12)

        # ── 描述文字 ──
        desc = self._data.get("description", "")
        source = self._data.get("source", "builtin")
        if source.startswith("plugin:"):
            plugin_name = source.split(":", 1)[1]
            desc = f"[{plugin_name}] {desc}"

        desc_label = QLabel(desc)
        desc_label.setObjectName("shortcutDescLabel")
        desc_label.setFixedWidth(180)
        layout.addWidget(desc_label)

        # ── 快捷键显示标签 ──
        keys = self._data.get("keys", "")
        is_conflict = self._data.get("has_conflict", False)

        self._keys_label = QLabel(keys if keys else "(未设置)")
        self._keys_label.setObjectName("shortcutKeysLabel")
        self._keys_label.setAlignment(Qt.AlignCenter)
        self._keys_label.setFixedWidth(160)
        self._keys_label.setFixedHeight(30)

        if is_conflict:
            self._keys_label.setStyleSheet(
                "background-color: #f38ba8; color: #1e1e2e; "
                "border-radius: 6px; font-size: 12px; font-weight: bold;"
            )
        elif keys:
            self._keys_label.setStyleSheet(
                "background-color: #313244; color: #cdd6f4; "
                "border: 1px solid #45475a; border-radius: 6px; "
                "font-size: 12px; padding: 4px 8px;"
            )
        else:
            self._keys_label.setStyleSheet(
                "background-color: #181825; color: #6c7086; "
                "border: 1px solid #313244; border-radius: 6px; "
                "font-size: 12px; padding: 4px 8px;"
            )
        layout.addWidget(self._keys_label)

        # ── 录制按钮 ──
        self._recorder = KeyRecorderButton(keys, self)
        self._recorder.key_recorded.connect(self._on_key_recorded)
        layout.addWidget(self._recorder)

        # ── 重置按钮 ──
        reset_btn = QPushButton("重置")
        reset_btn.setObjectName("shortcutResetBtn")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setFixedSize(60, 30)
        reset_btn.setToolTip("重置为默认值")
        reset_btn.clicked.connect(lambda: self.shortcut_reset.emit(self._data["id"]))
        layout.addWidget(reset_btn)

        layout.addStretch()

    def _on_key_recorded(self, keys: str):
        """录制按钮触发"""
        self._keys_label.setText(keys)
        self._keys_label.setStyleSheet(
            "background-color: #a6e3a1; color: #1e1e2e; "
            "border-radius: 6px; font-size: 12px; font-weight: bold;"
        )
        self.shortcut_changed.emit(self._data["id"], keys)

    def update_display(self, keys: str, has_conflict: bool = False):
        """更新显示的快捷键文本和冲突状态"""
        self._data["keys"] = keys
        self._data["has_conflict"] = has_conflict
        text = keys if keys else "(未设置)"
        self._keys_label.setText(text)
        self._recorder.set_current_keys(keys)

        if has_conflict:
            self._keys_label.setStyleSheet(
                "background-color: #f38ba8; color: #1e1e2e; "
                "border-radius: 6px; font-size: 12px; font-weight: bold;"
            )
        elif keys:
            self._keys_label.setStyleSheet(
                "background-color: #313244; color: #cdd6f4; "
                "border: 1px solid #45475a; border-radius: 6px; "
                "font-size: 12px; padding: 4px 8px;"
            )
        else:
            self._keys_label.setStyleSheet(
                "background-color: #181825; color: #6c7086; "
                "border: 1px solid #313244; border-radius: 6px; "
                "font-size: 12px; padding: 4px 8px;"
            )

    @property
    def shortcut_id(self) -> str:
        return self._data["id"]


# ═══════════════════════════════════════
#  主设置页
# ═══════════════════════════════════════

class _KeyboardShortcutsPage(QWidget):
    """快捷键设置页"""

    def __init__(self, parent_dialog, current_config: dict):
        super().__init__()
        self._parent_dialog = parent_dialog
        self._current_config = current_config
        self._rows: dict[str, ShortcutRow] = {}
        self.setObjectName("settingsPage")
        self._build_ui()
        self._load_shortcuts()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # ── 标题 ──
        title = QLabel("快捷键")
        title.setObjectName("settingsSectionTitle")
        layout.addWidget(title)

        desc = QLabel("自定义所有功能的快捷键参数。点击 🎬 录制按钮后按下新组合键。")
        desc.setObjectName("settingsSectionDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # ── 搜索框 ──
        search_card = QFrame()
        search_card.setObjectName("settingsCard")
        search_layout = QHBoxLayout(search_card)
        search_layout.setContentsMargins(16, 12, 16, 12)
        search_layout.setSpacing(8)

        search_icon = QLabel("🔍")
        search_icon.setObjectName("shortcutSearchIcon")
        search_icon.setFixedWidth(24)
        search_layout.addWidget(search_icon)

        self._search_input = QLineEdit()
        self._search_input.setObjectName("lineEdit")
        self._search_input.setPlaceholderText("搜索快捷键...")
        self._search_input.setFixedHeight(34)
        self._search_input.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self._search_input)

        # 全部重置按钮
        reset_all_btn = QPushButton("全部重置")
        reset_all_btn.setObjectName("settingsSmallBtn")
        reset_all_btn.setCursor(Qt.PointingHandCursor)
        reset_all_btn.setFixedSize(90, 34)
        reset_all_btn.clicked.connect(self._on_reset_all)
        search_layout.addWidget(reset_all_btn)

        layout.addWidget(search_card)

        # ── 卡片容器（直接排列，依赖设置对话框自身的滚动区域）──
        self._cards_layout = QVBoxLayout()
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(12)
        layout.addLayout(self._cards_layout)

        layout.addStretch()

        # ── 提示 ──
        hint = QLabel("ℹ 点击「保存」后快捷键立即生效。冲突的快捷键以红色高亮显示。")
        hint.setObjectName("settingsHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def _load_shortcuts(self):
        """从 ShortcutManager 加载所有快捷键并构建行"""
        try:
            from workers.shortcuts import get_shortcut_manager
            mgr = get_shortcut_manager()
            all_shortcuts = mgr.get_all_shortcuts()

            # 检测冲突
            conflicts = {s[0] for s in mgr.get_conflicts()}
            conflicts.update({s[1] for s in mgr.get_conflicts()})

            # 按分类分组
            groups: dict[str, list[dict]] = {}
            for sc in all_shortcuts:
                cat = sc.get("category", "其他")
                if cat not in groups:
                    groups[cat] = []
                sc["has_conflict"] = sc["id"] in conflicts
                groups[cat].append(sc)

            # 清除旧内容
            for row in self._rows.values():
                row.deleteLater()
            self._rows.clear()

            # 清除旧卡片
            while self._cards_layout.count():
                item = self._cards_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            # 按分类构建卡片
            for cat_name in sorted(groups.keys()):
                group = groups[cat_name]
                self._build_category_card(cat_name, group)

        except Exception:
            import traceback
            traceback.print_exc()

    def _build_category_card(self, category: str, shortcuts: list[dict]):
        """构建一个分类卡片"""
        card = QFrame()
        card.setObjectName("settingsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(6)

        # 分类标题
        cat_label = QLabel(category)
        cat_label.setObjectName("settingsLabel")
        card_layout.addWidget(cat_label)

        # 表头
        header = QWidget()
        header.setFixedHeight(24)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        header_layout.setSpacing(12)

        hdr_func = QLabel("功能")
        hdr_func.setStyleSheet(f"color: {tc("muted")}; font-size: 11px; background: transparent; border: none;")
        hdr_func.setFixedWidth(180)
        header_layout.addWidget(hdr_func)

        hdr_key = QLabel("快捷键")
        hdr_key.setStyleSheet(f"color: {tc("muted")}; font-size: 11px; background: transparent; border: none;")
        hdr_key.setFixedWidth(160)
        hdr_key.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(hdr_key)

        hdr_act = QLabel("操作")
        hdr_act.setStyleSheet(f"color: {tc("muted")}; font-size: 11px; background: transparent; border: none;")
        header_layout.addWidget(hdr_act)
        header_layout.addStretch()
        card_layout.addWidget(header)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setObjectName("settingsSep")
        card_layout.addWidget(sep)

        # 快捷键行
        for sc in shortcuts:
            row = ShortcutRow(sc, self)
            row.shortcut_changed.connect(self._on_shortcut_changed)
            row.shortcut_reset.connect(self._on_shortcut_reset)
            self._rows[sc["id"]] = row
            card_layout.addWidget(row)

        # 添加到卡片容器
        self._cards_layout.addWidget(card)

    def _on_search_changed(self, text: str):
        """搜索过滤"""
        text = text.strip().lower()
        for sid, row in self._rows.items():
            desc = row._data.get("description", "").lower()
            keys = row._data.get("keys", "").lower()
            cat = row._data.get("category", "").lower()
            if not text or text in desc or text in keys or text in cat:
                row.setVisible(True)
            else:
                row.setVisible(False)

    def _on_shortcut_changed(self, shortcut_id: str, new_keys: str):
        """快捷键录制完成"""
        try:
            from workers.shortcuts import get_shortcut_manager
            mgr = get_shortcut_manager()

            # 更新管理器
            mgr.update_shortcut_keys(shortcut_id, new_keys)

            # 重新检测并更新冲突状态
            self._refresh_conflict_states()
        except Exception:
            import traceback
            traceback.print_exc()

    def _on_shortcut_reset(self, shortcut_id: str):
        """重置单个快捷键"""
        try:
            from workers.shortcuts import get_shortcut_manager
            mgr = get_shortcut_manager()
            mgr.reset_to_default(shortcut_id)

            # 更新显示
            if shortcut_id in self._rows:
                effective = mgr.get_effective_keys(shortcut_id)
                default_keys = mgr._shortcuts.get(shortcut_id, {}).get("keys", "")
                self._rows[shortcut_id]._data["keys"] = effective
                self._rows[shortcut_id]._data["default_keys"] = default_keys
                self._rows[shortcut_id].update_display(effective)

            self._refresh_conflict_states()
        except Exception:
            import traceback
            traceback.print_exc()

    def _on_reset_all(self):
        """全部重置为默认值"""
        try:
            from workers.shortcuts import get_shortcut_manager
            mgr = get_shortcut_manager()
            mgr.reset_all_defaults()

            for sid, row in self._rows.items():
                effective = mgr.get_effective_keys(sid)
                row.update_display(effective)

            self._refresh_conflict_states()
        except Exception:
            import traceback
            traceback.print_exc()

    def _refresh_conflict_states(self):
        """刷新所有行的冲突高亮"""
        try:
            from workers.shortcuts import get_shortcut_manager
            mgr = get_shortcut_manager()
            conflicts = mgr.get_conflicts()
            conflict_ids = set()
            for c in conflicts:
                conflict_ids.add(c[0])
                conflict_ids.add(c[1])

            for sid, row in self._rows.items():
                keys = mgr.get_effective_keys(sid)
                row.update_display(keys, has_conflict=(sid in conflict_ids))
        except Exception:
            import traceback
            traceback.print_exc()

    def collect_config(self) -> dict:
        """收集当前配置：触发保存"""
        try:
            from workers.shortcuts import get_shortcut_manager
            mgr = get_shortcut_manager()
            mgr.save_config()
        except Exception:
            pass
        return {}


# ═══════════════════════════════════════
#  页面构建函数
# ═══════════════════════════════════════

def build_page(parent_dialog, current_config: dict) -> QWidget:
    """构建设置页面"""
    page = _KeyboardShortcutsPage(parent_dialog, current_config)
    return page


def collect_config(page_widget: QWidget) -> dict:
    """收集快捷键配置"""
    if isinstance(page_widget, _KeyboardShortcutsPage):
        return page_widget.collect_config()
    return {}
