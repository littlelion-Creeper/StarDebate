from components.theme_colors import tc, refresh
"""
STP 安装预览对话框

在安装 .stp 插件包之前，向用户展示：
  - 插件基本信息（名称 / 作者 / 版本 / 描述 / plugin_id）
  - 所需权限列表（危险权限标红）
  - 依赖检查结果
  - 版本兼容性
  - 冲突检测（是否覆盖/并列安装）
  - 校验和状态

用户确认后才执行安装。
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget, QRadioButton, QButtonGroup,
    QSizePolicy,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from workers.plugin_manager.plugin_api import PERMISSION_DEFS, PERMISSION_LEVEL_ORDER


class STPInstallPreview(QDialog):
    """.stp 插件安装预览对话框"""

    # 返回结果常量
    INSTALL = "install"
    CANCEL = "cancel"

    def __init__(self, parent, manifest: dict, missing_deps: list,
                 conflict: dict, compat_ok: bool, compat_msg: str):
        """
        Args:
            parent: 父窗口
            manifest: plugin.json 完整内容
            missing_deps: check_dependencies 返回的缺失依赖列表
            conflict: check_conflict 返回的冲突信息
            compat_ok: 版本是否兼容
            compat_msg: 不兼容时的提示文字
        """
        super().__init__(parent)
        self._manifest = manifest
        self._missing_deps = missing_deps
        self._conflict = conflict
        self._compat_ok = compat_ok
        self._compat_msg = compat_msg

        self._conflict_mode = "overwrite"  # 用户选择的冲突处理方式
        self._result = self.CANCEL

        self.setWindowTitle("📦 安装插件")
        self.setObjectName("stpInstallPreview")
        self.setMinimumSize(520, 500)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ── 标题 ──
        title_lbl = QLabel(f"📦 安装插件")
        title_lbl.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title_lbl.setObjectName("stpPreviewTitle")
        layout.addWidget(title_lbl)

        # ── 滚动内容区 ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(8)

        # 基本信息卡片
        self._add_info_card(scroll_layout)

        # 权限列表卡片
        self._add_permissions_card(scroll_layout)

        # 依赖检查卡片
        self._add_deps_card(scroll_layout)

        # 版本兼容性卡片
        self._add_version_card(scroll_layout)

        # 冲突检测卡片
        self._add_conflict_card(scroll_layout)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, stretch=1)

        # ── 分隔线 ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("stpPreviewSep")
        layout.addWidget(sep)

        # ── 按钮区 ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("stpPreviewCancelBtn")
        btn_cancel.setFixedSize(100, 36)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setFont(QFont("Microsoft YaHei", 11))
        btn_cancel.clicked.connect(self._on_cancel)

        btn_install = QPushButton("确认安装")
        btn_install.setObjectName("stpPreviewInstallBtn")
        btn_install.setFixedSize(120, 36)
        btn_install.setCursor(Qt.PointingHandCursor)
        btn_install.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))

        # 如果版本不兼容或必要的依赖缺失，禁用安装按钮
        can_install = self._compat_ok and not missing_deps_mandatory(self._missing_deps)
        disabled_reason = ""
        if not self._compat_ok:
            disabled_reason = "版本不兼容"
        elif self._missing_deps and not self._compat_ok:
            disabled_reason = "依赖不满足 + 版本不兼容"
        elif self._missing_deps:
            disabled_reason = "依赖不满足"

        if not can_install:
            btn_install.setEnabled(False)
            btn_install.setToolTip(disabled_reason)

        btn_install.clicked.connect(self._on_install)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_install)
        layout.addLayout(btn_layout)

    # ── 卡片构建 ────────────────────────────────────────────────

    def _make_card(self, title: str, icon: str = "") -> tuple[QVBoxLayout, QFrame]:
        """创建一张信息卡片，返回 (layout, frame)"""
        card = QFrame()
        card.setObjectName("stpPreviewCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        title_widget = QLabel(f"{icon} {title}" if icon else title)
        title_widget.setObjectName("stpPreviewCardTitle")
        title_widget.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        header.addWidget(title_widget)
        header.addStretch()
        card_layout.addLayout(header)

        return card_layout, card

    def _add_label_row(self, parent_layout, label: str, value: str,
                       value_color: str = "", value_bold: bool = False):
        """添加一行 label: value"""
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel(label)
        lbl.setObjectName("stpPreviewLabel")
        lbl.setFont(QFont("Microsoft YaHei", 10))
        lbl.setFixedWidth(90)
        val = QLabel(value)
        val.setObjectName("stpPreviewValue")
        val.setFont(QFont("Microsoft YaHei", 10, QFont.Bold if value_bold else QFont.Normal))
        val.setWordWrap(True)
        if value_color:
            val.setStyleSheet(f"color: {value_color};")
        row.addWidget(lbl)
        row.addWidget(val, stretch=1)
        parent_layout.addLayout(row)

    def _add_info_card(self, parent_layout):
        """插件信息卡片"""
        m = self._manifest
        card_layout, card = self._make_card("插件信息", "📋")
        self._add_label_row(card_layout, "名称", m.get("name", "未知"), value_bold=True)
        self._add_label_row(card_layout, "ID", m.get("plugin_id", ""))
        self._add_label_row(card_layout, "作者", m.get("author", "未知"))
        self._add_label_row(card_layout, "版本", f"v{m.get('version', '0.0.0')}")
        desc = m.get("description", "")
        if desc:
            self._add_label_row(card_layout, "描述", desc)
        parent_layout.addWidget(card)

    def _add_permissions_card(self, parent_layout):
        """权限列表卡片"""
        perms = self._manifest.get("permissions", [])
        if not perms:
            card_layout, card = self._make_card("权限请求", "🔒")
            hint = QLabel("该插件未声明权限")
            hint.setObjectName("stpPreviewHint")
            hint.setFont(QFont("Microsoft YaHei", 10))
            card_layout.addWidget(hint)
            parent_layout.addWidget(card)
            return

        card_layout, card = self._make_card("权限请求", "🔒")
        for perm in perms:
            pinfo = PERMISSION_DEFS.get(perm, {})
            level = pinfo.get("level", "safe")
            desc = pinfo.get("description", perm)
            icon = "🟢" if level == "safe" else ("🟡" if level == "medium" else "🔴")
            color = "" if level == "safe" else ("#f9e2af" if level == "medium" else "#f38ba8")
            row = QHBoxLayout()
            row.setSpacing(6)
            icon_lbl = QLabel(icon)
            icon_lbl.setFont(QFont("Microsoft YaHei", 10))
            text = QLabel(f"{perm} — {desc}")
            text.setFont(QFont("Microsoft YaHei", 10))
            if color:
                text.setStyleSheet(f"color: {color};")
            row.addWidget(icon_lbl)
            row.addWidget(text, stretch=1)
            card_layout.addLayout(row)
        parent_layout.addWidget(card)

    def _add_deps_card(self, parent_layout):
        """依赖检查卡片"""
        deps = self._missing_deps
        card_layout, card = self._make_card("依赖检查", "📦")
        if not deps:
            ok_lbl = QLabel("✅ 所有依赖已满足")
            ok_lbl.setObjectName("stpPreviewCheckPass")
            ok_lbl.setFont(QFont("Microsoft YaHei", 10))
            card_layout.addWidget(ok_lbl)
        else:
            for dep in deps:
                status = "❌ 未安装" if dep["status"] == "missing" else "❌ 版本不匹配"
                detail = f"{dep['id']} ({dep['required']})"
                if dep.get("installed"):
                    detail += f" 已安装: {dep['installed']}"
                dep_lbl = QLabel(f"{status}  {detail}")
                dep_lbl.setFont(QFont("Microsoft YaHei", 10))
                dep_lbl.setStyleSheet(f"color: {tc("accent_red")};")
                dep_lbl.setWordWrap(True)
                card_layout.addWidget(dep_lbl)
        parent_layout.addWidget(card)

    def _add_version_card(self, parent_layout):
        """版本兼容性卡片"""
        card_layout, card = self._make_card("版本兼容", "⚙️")
        if self._compat_ok:
            ok_lbl = QLabel("✅ StarDebate 版本满足要求")
            ok_lbl.setObjectName("stpPreviewCheckPass")
            ok_lbl.setFont(QFont("Microsoft YaHei", 10))
            card_layout.addWidget(ok_lbl)
        else:
            fail_lbl = QLabel(f"❌ {self._compat_msg}")
            fail_lbl.setFont(QFont("Microsoft YaHei", 10))
            fail_lbl.setStyleSheet(f"color: {tc("accent_red")};")
            fail_lbl.setWordWrap(True)
            card_layout.addWidget(fail_lbl)
        parent_layout.addWidget(card)

    def _add_conflict_card(self, parent_layout):
        """冲突检测卡片"""
        if not self._conflict.get("has_conflict"):
            card_layout, card = self._make_card("冲突检测", "🔍")
            ok_lbl = QLabel("✅ 无冲突，可直接安装")
            ok_lbl.setObjectName("stpPreviewCheckPass")
            ok_lbl.setFont(QFont("Microsoft YaHei", 10))
            card_layout.addWidget(ok_lbl)
            parent_layout.addWidget(card)
            return

        c = self._conflict
        card_layout, card = self._make_card("冲突检测", "🔍")
        warn = QLabel(
            f"⚠ 插件 \"{c['name']}\" 已安装\n"
            f"当前版本: v{c['current_version']}\n"
            f"新版本: v{c['new_version']}"
        )
        warn.setFont(QFont("Microsoft YaHei", 10))
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color: {tc("accent_yellow")};")
        card_layout.addWidget(warn)

        # 冲突处理选项
        group = QButtonGroup(self)
        rb_overwrite = QRadioButton("🔁 覆盖升级（推荐）")
        rb_overwrite.setObjectName("stpConflictRadio")
        rb_overwrite.setFont(QFont("Microsoft YaHei", 10))
        rb_overwrite.setChecked(True)
        rb_overwrite.toggled.connect(
            lambda checked: checked and setattr(self, "_conflict_mode", "overwrite")
        )
        rb_cancel = QRadioButton("❌ 取消安装")
        rb_cancel.setObjectName("stpConflictRadio")
        rb_cancel.setFont(QFont("Microsoft YaHei", 10))
        rb_cancel.toggled.connect(
            lambda checked: checked and setattr(self, "_conflict_mode", "cancel")
        )
        rb_parallel = QRadioButton("📂 并列安装（自动修改 ID）")
        rb_parallel.setObjectName("stpConflictRadio")
        rb_parallel.setFont(QFont("Microsoft YaHei", 10))
        rb_parallel.toggled.connect(
            lambda checked: checked and setattr(self, "_conflict_mode", "parallel")
        )

        group.addButton(rb_overwrite)
        group.addButton(rb_cancel)
        group.addButton(rb_parallel)

        card_layout.addWidget(rb_overwrite)
        card_layout.addWidget(rb_cancel)
        card_layout.addWidget(rb_parallel)
        parent_layout.addWidget(card)

    # ── 回调 ────────────────────────────────────────────────────

    def _on_cancel(self):
        self._result = self.CANCEL
        self.reject()

    def _on_install(self):
        self._result = self.INSTALL
        self.accept()

    def get_result(self) -> str:
        """返回用户选择：INSTALL / CANCEL"""
        return self._result

    def get_conflict_mode(self) -> str:
        """返回用户选择的冲突处理模式：overwrite / parallel / cancel"""
        return self._conflict_mode


def missing_deps_mandatory(missing: list) -> bool:
    """判断缺失依赖列表是否阻止安装（有缺失即阻止）"""
    return len(missing) > 0
