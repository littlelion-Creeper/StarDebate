"""StardebateModulePanel — .stardebate 模块浏览面板（右侧卡片视图）。

显示为一个可滚动的卡片列表，每个卡片展示一个模块的预览信息和操作按钮。

监视钩子:
  - function_watch: show_file / _on_module_clicked / _on_change_password
  - variable_watch: refresh_file_list / 卡片构建
  - api_watch: 密码修改 API 调用
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QComboBox, QSizePolicy, QToolButton,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QFontMetrics

from components.star_button import StarButton
from components.theme_colors import tc
from .stardebate_editor_manager import (
    MODULE_REGISTRY, get_module_label,
)
from components.icon_loader import get_module_svg_icon

# ── 监视钩子 ──────────────────────────────────────────────────────
_MONITOR_TAGS = {
    'variable_watch': 'VAR',
    'function_watch': 'FUNC',
    'api_watch': 'API',
}

def _monitor(mtype: str, message: str):
    import sys as _sys
    from datetime import datetime
    tag = _MONITOR_TAGS.get(mtype, 'MON')
    now = datetime.now()
    ts = now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"
    try:
        _sys.stderr.write(f"[{ts}] [INFO] [{tag}] {message}\n")
        _sys.stderr.flush()
    except Exception:
        pass


class ModuleCard(QFrame):
    """单个模块卡片。"""

    clicked = pyqtSignal(str)  # 发射 module_id
    MAX_PREVIEW_LEN = 30

    @staticmethod
    def _truncate(text: str, max_len: int = MAX_PREVIEW_LEN) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."

    def __init__(self, module_id: str, module_data, is_dirty: bool = False, parent=None):
        super().__init__(parent)
        self._module_id = module_id
        self.setObjectName("stdbModuleCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(84)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._build_ui(module_data, is_dirty)

    def _build_ui(self, module_data, is_dirty: bool):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # 顶部：图标 + 标签 + 修改标记
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        label = get_module_label(self._module_id)
        dirty_mark = " ⚠" if is_dirty else ""

        icon_btn = QToolButton()
        module_icon = get_module_svg_icon(self._module_id)
        if module_icon:
            icon_btn.setIcon(module_icon)
        icon_btn.setIconSize(QSize(16, 16))
        icon_btn.setFixedSize(20, 20)
        icon_btn.setAutoRaise(True)
        icon_btn.setEnabled(False)
        top_row.addWidget(icon_btn)

        title = QLabel(f"{label}{dirty_mark}")
        title.setObjectName("stdbModuleTitle")
        title.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        top_row.addWidget(title)

        top_row.addStretch()

        # 按钮
        btn_text = "查看 ▸" if self._is_view_only() else "编辑 ▸"
        btn = QPushButton(btn_text)
        btn.setFixedSize(100, 42)
        btn.setFont(QFont("Microsoft YaHei", 10))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setObjectName("stdbCardBtn")
        btn.clicked.connect(self._on_click)
        top_row.addWidget(btn)

        layout.addLayout(top_row)

        # 底部：预览信息
        preview = self._generate_preview(module_data)
        preview_label = QLabel(preview)
        preview_label.setObjectName("stdbModuleSubtitle")
        preview_label.setFont(QFont("Microsoft YaHei", 9))
        preview_label.setWordWrap(False)
        layout.addWidget(preview_label)

    def _is_view_only(self) -> bool:
        """判断模块是否只能查看（不可编辑）。"""
        view_only_ids = {
            "analysis_pro", "analysis_con", "accept_exam_pro",
            "accept_exam_con", "notes", "training",
        }
        return self._module_id in view_only_ids

    def _generate_preview(self, data) -> str:
        """生成模块预览文本（统一截断至 MAX_PREVIEW_LEN 字符）。"""
        if data is None:
            return self._truncate("(空)")

        mid = self._module_id

        if mid == "basic":
            pro = data.get("pro", "—")
            con = data.get("con", "—")
            return self._truncate(f"正方: {pro}  |  反方: {con}")

        elif mid in ("speech_pro", "speech_con"):
            content = data.get("content", "")
            if not content:
                return self._truncate("(尚未编辑)")
            text = content.replace("\n", " ")
            return self._truncate(f"{text}（{len(content)}字）")

        elif mid in ("ref_doc_pro", "ref_doc_con"):
            rows = data.get("rows", [])
            count = len(rows) if isinstance(rows, list) else 0
            return self._truncate(f"共 {count} 条资料条目")

        elif mid in ("analysis_pro", "analysis_con"):
            has_text = bool(data.get("analysis_text", ""))
            return self._truncate("分析已完成" if has_text else "(未分析)")

        elif mid == "framework":
            count = len(data) if isinstance(data, list) else 0
            return self._truncate(f"共 {count} 个节点")

        elif mid == "cross_exam":
            rounds = data.get("rounds", [])
            count = len(rounds) if isinstance(rounds, list) else 0
            return self._truncate(f"共 {count} 轮质询")

        elif mid in ("accept_exam_pro", "accept_exam_con"):
            messages = data.get("messages", [])
            count = len(messages) if isinstance(messages, list) else 0
            return self._truncate(f"共 {count} 条消息")

        elif mid == "notes":
            count = len(data) if isinstance(data, list) else 0
            return self._truncate(f"共 {count} 个便签")

        elif mid == "structure":
            pro_count = len(data.get("pro", [])) if isinstance(data, dict) else 0
            con_count = len(data.get("con", [])) if isinstance(data, dict) else 0
            return self._truncate(f"正方 {pro_count} 节点 | 反方 {con_count} 节点")

        elif mid == "training":
            count = len(data) if isinstance(data, list) else 0
            return self._truncate(f"共 {count} 条训练记录")

        return self._truncate(f"数据大小: {len(str(data))} 字符")

    def _on_click(self):
        self.clicked.emit(self._module_id)

    def mousePressEvent(self, event):
        """点击卡片。"""
        if event.button() == Qt.LeftButton:
            self._on_click()
        super().mousePressEvent(event)


class StardebateModulePanel(QFrame):
    """.stardebate 模块浏览面板 — 可滚动卡片列表。

    用法:
        panel = StardebateModulePanel(editor_mgr)
        panel.show_file("C:/.../辩论.stardebate")
    """

    module_selected = pyqtSignal(str, str)  # (file_path, module_id)

    def __init__(self, editor_manager, parent=None):
        super().__init__(parent)
        self._mgr = editor_manager
        self._current_file: str | None = None
        self.setObjectName("stdbModulePanel")
        self.setMinimumWidth(550)

        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 头部 ──
        header = QFrame()
        header.setObjectName("stdbPanelHeader")
        header.setFixedHeight(50)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 12, 6)
        header_layout.setSpacing(2)

        # 文件选择器（支持多个 .stardebate 文件切换）
        self._file_combo = QComboBox()
        self._file_combo.setFont(QFont("Microsoft YaHei", 10))
        self._file_combo.setObjectName("stdbFileCombo")
        self._file_combo.currentIndexChanged.connect(self._on_file_changed)
        self._file_combo.setStyleSheet(f"""
            #stdbFileCombo {{
                background-color: {tc("overlay")};
                border: none;
                border-radius: 6px;
                padding: 4px 8px;
                color: {tc("text")};
                font-size: 11pt;
                min-height: 28px;
            }}
            #stdbFileCombo::drop-down {{
                border: none;
                width: 28px;
            }}
            #stdbFileCombo QAbstractItemView {{
                background-color: {tc("surface")};
                color: {tc("text")};
                border: none;
                border-radius: 4px;
                padding: 4px;
                outline: none;
            }}
            #stdbFileCombo QAbstractItemView::item {{
                padding: 5px 10px;
                border-radius: 3px;
                min-height: 22px;
            }}
            #stdbFileCombo QAbstractItemView::item:hover,
            #stdbFileCombo QAbstractItemView::item:selected {{
                background-color: {tc("hover")};
            }}
        """)
        header_layout.addWidget(self._file_combo)

        main_layout.addWidget(header)

        # ── 滚动区域 ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("stdbScrollArea")

        self._cards_container = QWidget()
        self._cards_container.setObjectName("stdbCardsContainer")
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(8, 8, 8, 8)
        self._cards_layout.setSpacing(6)

        scroll.setWidget(self._cards_container)
        main_layout.addWidget(scroll)

        # ── 底部状态栏 ──
        footer = QFrame()
        footer.setObjectName("stdbPanelFooter")
        footer.setFixedHeight(82)
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(12, 4, 12, 4)
        footer_layout.setSpacing(2)

        self._info_label = QLabel("")
        self._info_label.setObjectName("stdbPanelInfoLabel")
        self._info_label.setFont(QFont("Microsoft YaHei", 9))
        footer_layout.addWidget(self._info_label)

        self._dirty_label = QLabel("")
        self._dirty_label.setObjectName("stdbPanelDirtyLabel")
        self._dirty_label.setFont(QFont("Microsoft YaHei", 9))
        footer_layout.addWidget(self._dirty_label)

        # 修改密码按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._chg_pwd_btn = StarButton("修改密码", None, layout_mode="text_only", ratio_h=0.7)
        self._chg_pwd_btn.setFixedHeight(30)
        self._chg_pwd_btn.setObjectName("stdbChgPwdBtn")
        self._chg_pwd_btn.clicked.connect(self._on_change_password)
        btn_row.addWidget(self._chg_pwd_btn)
        footer_layout.addLayout(btn_row)

        main_layout.addWidget(footer)

    # ── 文件切换 ─────────────────────────────────────────────────

    def refresh_file_list(self):
        """刷新文件选择下拉列表。"""
        _monitor('variable_watch', f'stdb_panel: refresh_file_list → {len(self._mgr.open_files)} open files')
        self._file_combo.blockSignals(True)
        self._file_combo.clear()

        files = self._mgr.open_files
        for file_path in files:
            self._file_combo.addItem(f"📦 {os.path.basename(file_path)}", file_path)

        if self._current_file and self._file_combo.count() > 0:
            idx = self._file_combo.findData(self._current_file)
            if idx >= 0:
                self._file_combo.setCurrentIndex(idx)

        self._file_combo.blockSignals(False)

    def _on_file_changed(self, index: int):
        if index < 0:
            return
        file_path = self._file_combo.itemData(index)
        if file_path and file_path != self._current_file:
            _monitor('function_watch', f'stdb_panel: file switched → {os.path.basename(file_path)}')
            self.show_file(file_path)

    # ── 显示文件 ─────────────────────────────────────────────────

    def show_file(self, file_path: str):
        """显示指定 .stardebate 文件的模块卡片列表。"""
        _monitor('function_watch', f'stdb_panel: show_file → {os.path.basename(file_path)}')
        self._current_file = file_path

        # 更新下拉列表
        self.refresh_file_list()

        # 清空卡片
        self._clear_cards()

        data = self._mgr.open_files.get(file_path)
        if not data:
            return

        modules = data.get("modules", {})
        meta = data.get("meta", {})
        dirty_modules = data.get("dirty_modules", set())

        # 按注册表顺序遍历模块
        for module_id in MODULE_REGISTRY:
            if module_id in modules:
                module_data = modules[module_id]
                is_dirty = module_id in dirty_modules
                card = ModuleCard(module_id, module_data, is_dirty)
                card.clicked.connect(
                    lambda mid=module_id: self._on_module_clicked(mid)
                )
                self._cards_layout.addWidget(card)

        # 底部弹簧
        self._cards_layout.addStretch()

        # 更新信息栏
        module_count = len([m for m in MODULE_REGISTRY if m in modules])
        has_password = meta.get("has_password", False)
        version = meta.get("version", "1")
        total_size = sum(len(str(v)) for v in modules.values())

        _monitor('variable_watch',
                 f'stdb_panel: show_file → {module_count} module cards, '
                 f'dirty={len(dirty_modules)}')
        self._info_label.setText(
            f"📋 {module_count} 模块 | {self._format_size(total_size)} | v{version} | "
            f"{'🔒有密码' if has_password else '🔓无密码'}"
        )

        if dirty_modules:
            dirty_names = [get_module_label(m) for m in dirty_modules if m in MODULE_REGISTRY]
            self._dirty_label.setText(f"⚠ 已修改: {', '.join(dirty_names[:3])}")
            self._dirty_label.setVisible(True)
        else:
            self._dirty_label.setVisible(False)

    def _clear_cards(self):
        """清空所有卡片。"""
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_module_clicked(self, module_id: str):
        """点击模块卡片。"""
        _monitor('function_watch', f'stdb_panel: card clicked → {module_id}')
        if self._current_file:
            self.module_selected.emit(self._current_file, module_id)
            self._mgr.open_module_editor(self._current_file, module_id)

    def _on_change_password(self):
        """修改密码按钮点击。"""
        _monitor('function_watch', f'stdb_panel: change_password dialog → {os.path.basename(self._current_file)}')
        if not self._current_file:
            return
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QCheckBox
        from components.popup_dialog import CustomDialog

        data = self._mgr.open_files.get(self._current_file)
        has_pwd = data.get("password") is not None if data else False

        dialog = QDialog(self)
        dialog.setWindowTitle("修改文件密码")
        dialog.setFixedSize(400, 280)
        dialog.setObjectName("stdbPwdDialog")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # 状态提示
        status_label = QLabel(f"当前状态: {'已设置密码' if has_pwd else '无密码保护'}")
        status_label.setFont(QFont("Microsoft YaHei", 11))
        layout.addWidget(status_label)

        # 旧密码
        old_pwd = QLineEdit()
        old_pwd.setObjectName("lineEdit")
        old_pwd.setEchoMode(QLineEdit.Password)
        old_pwd.setPlaceholderText("旧密码" if has_pwd else "（无密码则留空）")
        old_pwd.setFont(QFont("Microsoft YaHei", 11))
        old_pwd.setMinimumHeight(32)
        layout.addWidget(old_pwd)

        # 新密码
        new_pwd = QLineEdit()
        new_pwd.setEchoMode(QLineEdit.Password)
        new_pwd.setPlaceholderText("新密码（留空则移除密码保护）")
        new_pwd.setFont(QFont("Microsoft YaHei", 11))
        new_pwd.setMinimumHeight(32)
        layout.addWidget(new_pwd)

        # 确认密码
        confirm_pwd = QLineEdit()
        confirm_pwd.setObjectName("lineEdit")
        confirm_pwd.setEchoMode(QLineEdit.Password)
        confirm_pwd.setPlaceholderText("确认新密码")
        confirm_pwd.setFont(QFont("Microsoft YaHei", 11))
        confirm_pwd.setMinimumHeight(32)
        layout.addWidget(confirm_pwd)

        # 移除密码复选框
        remove_cb = QCheckBox("移除密码保护（不再使用密码）")
        remove_cb.setFont(QFont("Microsoft YaHei", 10))
        remove_cb.toggled.connect(
            lambda checked: [new_pwd.setDisabled(checked), confirm_pwd.setDisabled(checked)]
        )
        layout.addWidget(remove_cb)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(80, 30)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton("确认修改")
        confirm_btn.setFixedSize(100, 30)
        confirm_btn.setObjectName("stdbConfirmBtn")

        def do_change():
            old = old_pwd.text()
            new = new_pwd.text() if not remove_cb.isChecked() else None
            confirm = confirm_pwd.text() if not remove_cb.isChecked() else ""

            if new is not None and new != confirm:
                CustomDialog.warning(dialog, "密码不匹配", "新密码两次输入不一致。")
                return

            if has_pwd and old != (data.get("password") or ""):
                CustomDialog.warning(dialog, "密码错误", "旧密码不正确。")
                return

            result = self._mgr.change_password(self._current_file, old, new)
            if result["success"]:
                _monitor('api_watch',
                         f'stdb_panel: change_password → '
                         f'{"removed" if new is None else "updated"}')
                self._mgr.mark_dirty(self._current_file, "__password__")
                dialog.accept()
                self.show_file(self._current_file)
                CustomDialog.info(self, "成功",
                    f"密码已{'移除' if new is None else '修改'}。\n退出时将自动用新密码加密保存。")
            else:
                _monitor('api_watch', f'stdb_panel: change_password → FAILED: {result["error"]}')
                CustomDialog.warning(dialog, "修改失败", result["error"])

        confirm_btn.clicked.connect(do_change)
        btn_layout.addWidget(confirm_btn)
        layout.addLayout(btn_layout)

        dialog.exec_()

    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小。"""
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f}KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f}MB"

    def refresh_current(self):
        """刷新当前显示。"""
        _monitor('function_watch', 'stdb_panel: refresh_current')
        if self._current_file:
            self.show_file(self._current_file)
