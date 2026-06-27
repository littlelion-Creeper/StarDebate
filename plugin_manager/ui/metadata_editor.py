"""
右侧面板：plugin.json 元数据编辑器 + 打包按钮

以表单形式编辑 plugin.json 字段，支持：
  - 文本字段（名称/ID/版本/作者/描述/最低版本）
  - 权限复选框（选中/取消 + 全选/清空）
  - 依赖键值对（增删行：plugin_id + 版本约束）
  - 标签输入（逗号分隔）
  - 实时验证
  - 一键打包为 .stp
"""

import os
import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QPlainTextEdit, QPushButton, QLabel, QCheckBox, QFrame,
    QScrollArea, QMessageBox, QSizePolicy, QFileDialog,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


# 可用权限定义（与 plugin_api.py 保持一致）
ALL_PERMISSIONS = {
    "file_read": {"level": "safe", "label": "🔵 读取文件"},
    "file_write": {"level": "dangerous", "label": "🔴 写入文件"},
    "network": {"level": "dangerous", "label": "🔴 网络请求"},
    "ai_api": {"level": "safe", "label": "🔵 AI 接口"},
    "settings_read": {"level": "safe", "label": "🔵 读取配置"},
    "settings_write": {"level": "medium", "label": "🟡 修改配置"},
}


class MetadataEditor(QWidget):
    """右侧插件元数据编辑器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_dir = ""
        self._manifest: dict = {}
        self._dirty = False
        self._build_ui()
        self.setEnabled(False)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 标题
        title_row = QHBoxLayout()
        title = QLabel("🔧 插件元数据")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        title_row.addWidget(title)
        title_row.addStretch()

        self._save_btn = QPushButton("💾 保存")
        self._save_btn.setObjectName("pmActionBtn")
        self._save_btn.setFixedSize(90, 30)
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setFont(QFont("Microsoft YaHei", 10))
        self._save_btn.clicked.connect(self._on_save)
        self._save_btn.setEnabled(False)
        title_row.addWidget(self._save_btn)

        layout.addLayout(title_row)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        # 滚动编辑区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setContentsMargins(0, 4, 0, 4)
        form_layout.setSpacing(8)
        form_layout.setLabelAlignment(Qt.AlignRight)

        # 基本字段
        self._inp_name = QLineEdit()
        self._inp_name.setObjectName("lineEdit")
        self._inp_name.setFont(QFont("Microsoft YaHei", 10))
        self._inp_name.textChanged.connect(self._mark_dirty)
        form_layout.addRow("名称:", self._inp_name)

        self._inp_plugin_id = QLineEdit()
        self._inp_plugin_id.setObjectName("lineEdit")
        self._inp_plugin_id.setFont(QFont("Microsoft YaHei", 10))
        self._inp_plugin_id.textChanged.connect(self._mark_dirty)
        form_layout.addRow("插件 ID:", self._inp_plugin_id)

        self._inp_version = QLineEdit()
        self._inp_version.setObjectName("pmInput")
        self._inp_version.setFont(QFont("Microsoft YaHei", 10))
        self._inp_version.setPlaceholderText("1.0.0")
        self._inp_version.textChanged.connect(self._mark_dirty)
        form_layout.addRow("版本:", self._inp_version)

        self._inp_author = QLineEdit()
        self._inp_author.setObjectName("lineEdit")
        self._inp_author.setFont(QFont("Microsoft YaHei", 10))
        self._inp_author.textChanged.connect(self._mark_dirty)
        form_layout.addRow("作者:", self._inp_author)

        self._inp_min_version = QLineEdit()
        self._inp_min_version.setObjectName("lineEdit")
        self._inp_min_version.setFont(QFont("Microsoft YaHei", 10))
        self._inp_min_version.setPlaceholderText("1.0.0")
        self._inp_min_version.textChanged.connect(self._mark_dirty)
        form_layout.addRow("最低 StarDebate:", self._inp_min_version)

        self._inp_description = QPlainTextEdit()
        self._inp_description.setObjectName("textEdit")
        self._inp_description.setFont(QFont("Microsoft YaHei", 10))
        self._inp_description.setFixedHeight(60)
        self._inp_description.textChanged.connect(self._mark_dirty)
        form_layout.addRow("描述:", self._inp_description)

        # 分隔
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        form_layout.addRow(sep2)

        # 权限（全选/取消）
        perm_header = QHBoxLayout()
        perm_title = QLabel("权限声明:")
        perm_title.setFont(QFont("Microsoft YaHei", 10))
        perm_header.addWidget(perm_title)

        btn_perm_all = QPushButton("全选")
        btn_perm_all.setObjectName("pmSmallBtn")
        btn_perm_all.setFixedSize(55, 24)
        btn_perm_all.setCursor(Qt.PointingHandCursor)
        btn_perm_all.setFont(QFont("Microsoft YaHei", 9))
        btn_perm_all.clicked.connect(lambda: self._set_all_perms(True))
        perm_header.addWidget(btn_perm_all)

        btn_perm_none = QPushButton("清空")
        btn_perm_none.setObjectName("pmSmallBtn")
        btn_perm_none.setFixedSize(55, 24)
        btn_perm_none.setCursor(Qt.PointingHandCursor)
        btn_perm_none.setFont(QFont("Microsoft YaHei", 9))
        btn_perm_none.clicked.connect(lambda: self._set_all_perms(False))
        perm_header.addWidget(btn_perm_none)

        perm_header.addStretch()
        form_layout.addRow(perm_header)

        self._perm_checkboxes: dict[str, QCheckBox] = {}
        for perm_key, perm_info in ALL_PERMISSIONS.items():
            cb = QCheckBox(perm_info["label"])
            cb.setObjectName("pmPermCheck")
            cb.setFont(QFont("Microsoft YaHei", 10))
            cb.toggled.connect(self._mark_dirty)
            self._perm_checkboxes[perm_key] = cb
            form_layout.addRow("", cb)

        # 分割
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.HLine)
        form_layout.addRow(sep3)

        # ── 依赖 ──
        dep_header = QHBoxLayout()
        dep_title = QLabel("依赖:")
        dep_title.setFont(QFont("Microsoft YaHei", 10))
        dep_header.addWidget(dep_title)

        btn_add_dep = QPushButton("+ 添加")
        btn_add_dep.setObjectName("pmSmallBtn")
        btn_add_dep.setFixedSize(75, 24)
        btn_add_dep.setCursor(Qt.PointingHandCursor)
        btn_add_dep.setFont(QFont("Microsoft YaHei", 9))
        btn_add_dep.clicked.connect(self._add_dep_row)
        dep_header.addWidget(btn_add_dep)

        dep_header.addStretch()
        form_layout.addRow(dep_header)

        self._dep_rows: list[tuple[QLineEdit, QLineEdit]] = []
        self._dep_container = QWidget()
        self._dep_container_layout = QVBoxLayout(self._dep_container)
        self._dep_container_layout.setContentsMargins(0, 0, 0, 0)
        self._dep_container_layout.setSpacing(4)

        form_layout.addRow("", self._dep_container)

        # 依赖空提示（独立于容器，避免被 _clear_dep_rows 意外删除）
        self._dep_hint = QLabel("（无依赖，点击「+ 添加」增加依赖项）")
        self._dep_hint.setFont(QFont("Microsoft YaHei", 9))
        self._dep_hint.setStyleSheet("color: #6c7086;")
        form_layout.addRow("", self._dep_hint)

        # 分割
        sep4 = QFrame()
        sep4.setFrameShape(QFrame.HLine)
        form_layout.addRow(sep4)

        # 标签
        self._inp_tags = QLineEdit()
        self._inp_tags.setObjectName("lineEdit")
        self._inp_tags.setFont(QFont("Microsoft YaHei", 10))
        self._inp_tags.setPlaceholderText("标签1, 标签2, 标签3")
        self._inp_tags.textChanged.connect(self._mark_dirty)
        form_layout.addRow("标签:", self._inp_tags)

        scroll.setWidget(form_widget)
        layout.addWidget(scroll, stretch=1)

        # ── 底部操作栏 ──
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self._validate_label = QLabel("")
        self._validate_label.setFont(QFont("Microsoft YaHei", 9))
        bottom.addWidget(self._validate_label, stretch=1)

        btn_package = QPushButton("打包为 .stp")
        btn_package.setObjectName("pmPrimaryBtn")
        btn_package.setFixedSize(180, 36)
        btn_package.setCursor(Qt.PointingHandCursor)
        btn_package.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        btn_package.clicked.connect(self._on_package)
        bottom.addWidget(btn_package)

        layout.addLayout(bottom)

    # ── 加载项目 ────────────────────────────────────────────────

    def load_project(self, dir_path: str):
        """加载插件项目的 plugin.json"""
        self._current_dir = dir_path
        if not dir_path:
            self.setEnabled(False)
            self._dirty = False
            return

        mf = os.path.join(dir_path, "plugin.json")
        if not os.path.isfile(mf):
            self.setEnabled(False)
            return

        try:
            with open(mf, "r", encoding="utf-8") as f:
                self._manifest = json.load(f)
        except Exception:
            self.setEnabled(False)
            return

        self._dirty = False
        self.setEnabled(True)
        self._load_fields()

    def _load_fields(self):
        """将 manifest 数据填入表单"""
        m = self._manifest
        self._inp_name.setText(m.get("name", ""))
        self._inp_plugin_id.setText(m.get("plugin_id", ""))
        self._inp_version.setText(m.get("version", ""))
        self._inp_author.setText(m.get("author", ""))
        self._inp_min_version.setText(m.get("min_app_version", ""))
        self._inp_description.setPlainText(m.get("description", ""))

        # 权限
        perms = set(m.get("permissions", []))
        for key, cb in self._perm_checkboxes.items():
            cb.setChecked(key in perms)

        # 标签
        tags = m.get("tags", [])
        self._inp_tags.setText(", ".join(tags) if tags else "")

        # 依赖
        self._clear_dep_rows()
        deps = m.get("dependencies", {})
        if deps:
            for dep_id, dep_ver in deps.items():
                self._add_dep_row(dep_id, dep_ver)
        else:
            self._dep_hint.setVisible(True)

        self._dirty = False
        self._save_btn.setEnabled(False)
        self._validate()

    # ── 保存 ────────────────────────────────────────────────────

    def _on_save(self):
        """保存表单数据到 plugin.json"""
        if not self._current_dir:
            return
        self._collect_fields()
        mf = os.path.join(self._current_dir, "plugin.json")
        try:
            with open(mf, "w", encoding="utf-8") as f:
                json.dump(self._manifest, f, ensure_ascii=False, indent=2)
                f.write("\n")
            self._dirty = False
            self._save_btn.setEnabled(False)
            self._validate_label.setText("✅ 已保存")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    # ── 打包 ────────────────────────────────────────────────────

    def _on_package(self):
        """打包为 .stp 文件"""
        if not self._current_dir:
            return

        # 先保存
        if self._dirty:
            self._on_save()

        from plugin_manager.core.stp_packager import validate_package, package

        errors = validate_package(self._current_dir)
        if errors:
            QMessageBox.warning(self, "打包验证失败",
                              "请修正以下问题后再打包：\n" + "\n".join(f"• {e}" for e in errors))
            return

        # 选择输出位置
        manifest = self._manifest
        default_name = f"{manifest.get('name', 'plugin')}.stp"
        output_path, _ = QFileDialog.getSaveFileName(
            self, "保存 .stp 文件", default_name,
            "StarPlugin 包 (*.stp);;所有文件 (*)",
        )
        if not output_path:
            return

        try:
            result = package(self._current_dir, output_path)
            QMessageBox.information(self, "打包成功",
                f"✅ 插件包已生成：\n{result}\n\n"
                f"插件名：{manifest.get('name', '')}\n"
                f"版本：v{manifest.get('version', '')}\n"
                f"文件大小：{os.path.getsize(result) / 1024:.1f} KB")
            # 打包后重新加载（checksum 已更新）
            self.load_project(self._current_dir)
        except Exception as e:
            QMessageBox.critical(self, "打包失败", str(e))

    # ── 表单数据收集 ────────────────────────────────────────────

    def _collect_fields(self):
        """从表单收集数据到 self._manifest"""
        # 防止空值覆盖
        name = self._inp_name.text().strip()
        if name:
            self._manifest["name"] = name

        pid = self._inp_plugin_id.text().strip()
        if pid:
            self._manifest["plugin_id"] = pid

        ver = self._inp_version.text().strip() or "1.0.0"
        self._manifest["version"] = ver

        author = self._inp_author.text().strip()
        if author:
            self._manifest["author"] = author

        min_ver = self._inp_min_version.text().strip()
        if min_ver:
            self._manifest["min_app_version"] = min_ver

        self._manifest["description"] = self._inp_description.toPlainText().strip()

        # 权限
        perms = [k for k, cb in self._perm_checkboxes.items() if cb.isChecked()]
        self._manifest["permissions"] = perms

        # 标签
        tags_text = self._inp_tags.text().strip()
        if tags_text:
            tags = [t.strip() for t in tags_text.split(",") if t.strip()]
            self._manifest["tags"] = tags
        else:
            self._manifest["tags"] = []

        # 依赖
        deps = {}
        for dep_id_input, dep_ver_input in self._dep_rows:
            did = dep_id_input.text().strip()
            dver = dep_ver_input.text().strip()
            if did and dver:
                deps[did] = dver
        if deps:
            self._manifest["dependencies"] = deps
        else:
            self._manifest.pop("dependencies", None)

    # ── 验证 ────────────────────────────────────────────────────

    def _validate(self):
        """实时验证并更新状态"""
        errors = []

        if not self._inp_name.text().strip():
            errors.append("名称不能为空")

        if not self._inp_plugin_id.text().strip():
            errors.append("插件 ID 不能为空")

        if errors:
            self._validate_label.setText("⚠ " + "; ".join(errors))
        else:
            self._validate_label.setText("")

    def _mark_dirty(self):
        """标记为已修改"""
        if not self._current_dir:
            return
        self._dirty = True
        self._save_btn.setEnabled(True)
        self._validate()

    def _set_all_perms(self, checked: bool):
        """全选/清空权限"""
        for cb in self._perm_checkboxes.values():
            cb.setChecked(checked)

    # ── 依赖行管理 ─────────────────────────────────────────────

    def _add_dep_row(self, dep_id: str = "", dep_ver: str = ""):
        """添加一行依赖输入"""
        self._dep_hint.setVisible(False)

        row = QHBoxLayout()
        row.setSpacing(4)

        inp_id = QLineEdit(dep_id)
        inp_id.setObjectName("pmDepInput")
        inp_id.setFont(QFont("Microsoft YaHei", 10))
        inp_id.setPlaceholderText("author.plugin_id")
        inp_id.textChanged.connect(self._mark_dirty)
        row.addWidget(inp_id, stretch=3)

        ver_lbl = QLabel("≥")
        ver_lbl.setFont(QFont("Microsoft YaHei", 10))
        row.addWidget(ver_lbl)

        inp_ver = QLineEdit(dep_ver)
        inp_ver.setObjectName("pmDepInput")
        inp_ver.setFont(QFont("Microsoft YaHei", 10))
        inp_ver.setPlaceholderText("1.0.0")
        inp_ver.textChanged.connect(self._mark_dirty)
        row.addWidget(inp_ver, stretch=2)

        btn_remove = QPushButton("✕")
        btn_remove.setObjectName("pmSmallBtn")
        btn_remove.setFixedSize(28, 24)
        btn_remove.setCursor(Qt.PointingHandCursor)
        btn_remove.setFont(QFont("Microsoft YaHei", 9))
        btn_remove.clicked.connect(
            lambda checked=False, r=row, i=inp_id, v=inp_ver:
                self._remove_dep_row(r, i, v)
        )
        row.addWidget(btn_remove)

        row_widget = QWidget()
        row_widget.setLayout(row)
        self._dep_container_layout.addWidget(row_widget)
        self._dep_rows.append((inp_id, inp_ver))

        self._mark_dirty()

    def _remove_dep_row(self, row_layout: QHBoxLayout,
                        inp_id: QLineEdit, inp_ver: QLineEdit):
        """移除一行依赖"""
        for i, (oid, over) in enumerate(self._dep_rows):
            if oid is inp_id and over is inp_ver:
                self._dep_rows.pop(i)
                break
        # 找到并删除对应的 QWidget
        for i in range(self._dep_container_layout.count()):
            w = self._dep_container_layout.itemAt(i).widget()
            if w and w.layout() is row_layout:
                self._dep_container_layout.removeWidget(w)
                w.deleteLater()
                break
        if not self._dep_rows:
            self._dep_hint.setVisible(True)
        self._mark_dirty()

    def _clear_dep_rows(self):
        """清空所有依赖行（不含 hint，hint 独立于容器）"""
        while self._dep_container_layout.count() > 0:
            item = self._dep_container_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._dep_rows.clear()
        self._dep_hint.setVisible(True)
