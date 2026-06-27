"""StardebateImportDialog — .stardebate 文件导入独立窗口

使用 TitleBar 通用控件 + 多文件规则 UI 拆分:
  - _build_title_bar()         标题栏 (TitleBar 通用组件)
  - _build_content()            主内容区
  - _build_file_select_card()   文件选择卡片
  - _build_verify_card()        验证状态卡片
  - _build_password_card()      密码输入卡片
  - _build_preview_card()       辩论预览卡片
  - _build_import_options_card()导入目标选择卡片
  - _build_modules_card()       模块选择卡片
  - _build_bottom_buttons()     底部按钮
"""

import os, sys, json, time, ctypes
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QLineEdit, QFileDialog, QApplication,
    QRadioButton, QScrollArea,
)
from PyQt5.QtCore import Qt, QEvent, QRectF
from PyQt5.QtGui import QFont, QPainterPath, QRegion

from components.title_bar import TitleBar
from components.star_button import StarButton
from components.popup_dialog import CustomDialog
from components.star_checkbox import StarCheckBox
from .stardebate_compiler import StardebateCompiler, restore_debate_data


class StardebateImportDialog(QWidget):
    """导入 .stardebate 文件 — 独立窗口 (TitleBar 通用控件)"""

    obj_name = "stdebImportDialog"

    def __init__(self, parent=None):
        super().__init__(None)
        self._mw = parent
        self._compiler: StardebateCompiler | None = None
        self._file_data: bytes | None = None
        self._decrypted_modules: dict | None = None
        self._decrypted_meta: dict = {}
        self._password_attempts: int = 0
        self._max_attempts: int = 5
        self._module_checkboxes: dict[str, StarCheckBox] = {}
        self._importing: bool = False

        self.setWindowTitle("导入 .stardebate 辩论文件")
        self.resize(580, 200)
        self.setMinimumSize(480, 180)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setObjectName(self.obj_name)
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._setup_ui()
        self._apply_style()
        self._auto_adjust_size()

        if parent:
            pg = parent.geometry()
            self.move(pg.x() + (pg.width() - self.width()) // 2,
                      pg.y() + (pg.height() - self.height()) // 2)

    # ══════════════════════════════════════════════════════════════════
    #  窗口事件
    # ══════════════════════════════════════════════════════════════════

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange and self._title_bar:
            self._title_bar.update_max_btn()
        super().changeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_rounded_mask()

    def _update_rounded_mask(self):
        """应用 12px 圆角遮罩"""
        if self.isMaximized():
            self.clearMask()
            return
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 12, 12)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def nativeEvent(self, event_type, message):
        if sys.platform != 'win32':
            return False, 0
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:
                x, y = msg.lParam & 0xFFFF, (msg.lParam >> 16) & 0xFFFF
                g = self.geometry()
                b = 6
                l, r, t, bt = x < g.left() + b, x > g.right() - b, y < g.top() + b, y > g.bottom() - b
                if t and l:       return True, 13
                if t and r:       return True, 14
                if bt and l:      return True, 16
                if bt and r:      return True, 17
                if l:             return True, 10
                if r:             return True, 11
                if t:             return True, 12
                if bt:            return True, 15
            return False, 0
        except Exception:
            return False, 0

    # ══════════════════════════════════════════════════════════════════
    #  UI 构建
    # ══════════════════════════════════════════════════════════════════

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._build_title_bar()

        scroll = QScrollArea()
        scroll.setObjectName("stdebContentScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._content_widget = self._build_content()
        scroll.setWidget(self._content_widget)
        layout.addWidget(scroll, stretch=1)

    def _build_title_bar(self):
        self._title_bar = TitleBar(parent=self, title="导入 .stardebate 辩论文件", icon="")
        self._title_bar.setObjectName("stdebTitleBar")
        self.layout().insertWidget(0, self._title_bar)
        self._set_title_bar_icon()

    def _set_title_bar_icon(self):
        """将标题栏图标替换为蓝色 STDB.svg（22px）。"""
        import os
        from components.svg_renderer import SvgRenderer
        from components.theme_colors import tc
        from components.res_path import get_resource_root
        svg_path = os.path.join(
            get_resource_root(),
            "icon", "common", "STDB.svg"
        )
        if os.path.isfile(svg_path):
            pixmap = SvgRenderer.render(svg_path, 22, mode="mono", color=tc("accent_blue"))
            self._title_bar._icon_label.setPixmap(pixmap)
            self._title_bar._icon_label.setFixedWidth(30)

    def _build_content(self) -> QWidget:
        w = QWidget()
        w.setObjectName("stdebContent")
        lo = QVBoxLayout(w)
        lo.setContentsMargins(20, 12, 20, 16)
        lo.setSpacing(12)

        lo.addWidget(self._build_file_select_card())

        self._verify_card = QFrame()
        self._verify_card.setObjectName("stdebVerifyCard")
        self._verify_card.setVisible(False)
        self._verify_layout = QVBoxLayout(self._verify_card)
        self._verify_layout.setContentsMargins(14, 12, 14, 12)
        self._verify_layout.setSpacing(4)
        self._verify_labels: list[QLabel] = []
        lo.addWidget(self._verify_card)

        self._pwd_card = self._build_password_card()
        self._pwd_card.setVisible(False)
        lo.addWidget(self._pwd_card)

        self._preview_card = self._build_preview_card()
        self._preview_card.setVisible(False)
        lo.addWidget(self._preview_card)

        self._options_card = self._build_import_options_card()
        self._options_card.setVisible(False)
        lo.addWidget(self._options_card)

        self._modules_card = QFrame()
        self._modules_card.setObjectName("stdebModulesCard")
        self._modules_card.setVisible(False)
        self._modules_layout = QVBoxLayout(self._modules_card)
        self._modules_layout.setContentsMargins(14, 12, 14, 12)
        self._modules_layout.setSpacing(4)
        lo.addWidget(self._modules_card)

        lo.addLayout(self._build_bottom_buttons())
        lo.addStretch()
        return w

    # ── 文件选择卡片 ─────────────────────────────────────────────────

    def _build_file_select_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("stdebFileSelectCard")
        lo = QHBoxLayout(card)
        lo.setContentsMargins(14, 12, 14, 12)
        lo.setSpacing(8)

        self._input_file_path = QLineEdit()
        self._input_file_path.setObjectName("stdebFileInput")
        self._input_file_path.setFont(QFont("Microsoft YaHei", 11))
        self._input_file_path.setFixedHeight(34)
        self._input_file_path.setReadOnly(True)
        self._input_file_path.setPlaceholderText("请选择 .stardebate 文件...")

        btn = StarButton("📂 选择文件", None, layout_mode="text_only", ratio_h=0.7)
        btn.setObjectName("stdebBrowseBtn")
        btn.setFixedHeight(34)
        btn.clicked.connect(self._browse_file)

        lo.addWidget(self._input_file_path, stretch=1)
        lo.addWidget(btn)
        return card

    # ── 密码输入卡片 ─────────────────────────────────────────────────

    def _build_password_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("stdebPasswordCard")
        lo = QVBoxLayout(card)
        lo.setContentsMargins(14, 12, 14, 12)
        lo.setSpacing(8)

        title = QLabel("🔐 此文件受到密码保护")
        title.setObjectName("stdebCardTitle")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        lo.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._input_password = QLineEdit()
        self._input_password.setObjectName("lineEdit")
        self._input_password.setFont(QFont("Microsoft YaHei", 11))
        self._input_password.setEchoMode(QLineEdit.Password)
        self._input_password.setFixedHeight(34)
        self._input_password.setPlaceholderText("请输入导出时设置的密码")
        self._input_password.returnPressed.connect(self._on_try_decrypt)
        btn_eye = StarButton("", None, layout_mode="text_only", ratio_h=0.7)
        btn_eye.setObjectName("stdebPwdEyeBtn")
        btn_eye.setFixedSize(34, 34)
        btn_eye.clicked.connect(self._toggle_pwd_visible)
        self._btn_pwd_eye = btn_eye
        row.addWidget(self._input_password, stretch=1)
        row.addWidget(btn_eye)
        lo.addLayout(row)

        self._lbl_retry = QLabel("")
        self._lbl_retry.setObjectName("stdebPwdRetryCount")
        self._lbl_retry.setFont(QFont("Microsoft YaHei", 10))
        lo.addWidget(self._lbl_retry)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_decrypt = StarButton("🔓 解密预览", None, layout_mode="text_only", ratio_h=0.7)
        self._btn_decrypt.setObjectName("stdebDecryptBtn")
        self._btn_decrypt.setFixedHeight(38)
        self._btn_decrypt.clicked.connect(self._on_try_decrypt)
        btn_row.addWidget(self._btn_decrypt)
        lo.addLayout(btn_row)
        return card

    # ── 预览卡片 ─────────────────────────────────────────────────────

    def _build_preview_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("stdebPreviewCard")
        lo = QVBoxLayout(card)
        lo.setContentsMargins(14, 12, 14, 12)
        lo.setSpacing(4)

        title = QLabel("辩论预览")
        title.setObjectName("stdebCardTitle")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        lo.addWidget(title)

        for attr in ['_lbl_preview_pro', '_lbl_preview_con', '_lbl_preview_info', '_lbl_preview_badge']:
            lbl = QLabel("—")
            if attr == '_lbl_preview_badge':
                lbl.setObjectName("stdebEncryptBadge")
            lbl.setFont(QFont("Microsoft YaHei", 11))
            lbl.setWordWrap(True)
            lo.addWidget(lbl)
            setattr(self, attr, lbl)
        self._lbl_preview_pro.setText("正方: —")
        self._lbl_preview_con.setText("反方: —")
        self._lbl_preview_info.setText("信息: —")
        return card

    # ── 导入选项卡片 ─────────────────────────────────────────────────

    def _build_import_options_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("stdebImportOptionsCard")
        lo = QVBoxLayout(card)
        lo.setContentsMargins(14, 12, 14, 12)
        lo.setSpacing(8)

        title = QLabel("导入目标")
        title.setObjectName("stdebCardTitle")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        lo.addWidget(title)

        self._radio_new = QRadioButton("新建项目 (在选定目录创建新项目文件夹)")
        self._radio_existing = QRadioButton("追加到当前项目")
        self._radio_new.setChecked(True)
        for rb in [self._radio_new, self._radio_existing]:
            rb.setFont(QFont("Microsoft YaHei", 11))
            lo.addWidget(rb)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._input_target = QLineEdit()
        self._input_target.setObjectName("lineEdit")
        self._input_target.setFont(QFont("Microsoft YaHei", 11))
        self._input_target.setFixedHeight(34)
        self._input_target.setPlaceholderText("目标路径 — 点击右侧浏览选择...")
        btn = StarButton("📂", None, layout_mode="text_only", ratio_h=0.7)
        btn.setFixedSize(34, 34)
        btn.clicked.connect(self._browse_target)
        row.addWidget(self._input_target, stretch=1)
        row.addWidget(btn)
        lo.addLayout(row)
        return card

    # ── 底部按钮 ─────────────────────────────────────────────────────

    def _build_bottom_buttons(self):
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addStretch()

        btn_cancel = StarButton("取消", None, layout_mode="text_only", ratio_h=0.7)
        btn_cancel.setObjectName("stdebCancelBtn")
        btn_cancel.setFixedHeight(38)
        btn_cancel.clicked.connect(self.close)
        row.addWidget(btn_cancel)

        self._btn_import = StarButton("开始导入", None, layout_mode="text_only", ratio_h=0.7)
        self._btn_import.setObjectName("stdebImportBtn")
        self._btn_import.setFixedHeight(38)
        self._btn_import.setVisible(False)
        self._btn_import.clicked.connect(self._on_import)
        row.addWidget(self._btn_import)
        return row

    # ══════════════════════════════════════════════════════════════════
    #  事件处理
    # ══════════════════════════════════════════════════════════════════

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 .stardebate 文件", "",
                                               "StarDebate 文件 (*.stardebate);;所有文件 (*)")
        if path:
            self._input_file_path.setText(path)
            self._on_file_selected(path)

    def _on_file_selected(self, path):
        try:
            with open(path, 'rb') as f:
                self._file_data = f.read()
        except Exception as e:
            CustomDialog.error(self, "读取失败", f"无法读取文件:\n{str(e)}")
            return

        if self._compiler is None:
            try:
                self._compiler = StardebateCompiler()
            except ImportError as e:
                CustomDialog.error(self, "缺少依赖", str(e))
                return

        is_valid = self._compiler.verify_magic(self._file_data)
        info = self._compiler.get_file_info(self._file_data)
        self._show_verify_status(is_valid, info)

        if not is_valid:
            self._hide_decrypted_ui()
            return

        if info.get("has_password", False):
            self._show_password_ui()
        else:
            self._hide_password_ui()
            self._auto_decrypt()

    def _show_verify_status(self, valid, info):
        self._verify_card.setVisible(True)
        for lbl in self._verify_labels:
            lbl.deleteLater()
        self._verify_labels.clear()

        if valid:
            lines = [
                f"✅ 文件格式验证通过 (StarDebate .stardebate v{info.get('version','?')})",
                f"📦 文件大小: {info.get('file_size',0)/1024:.1f} KB",
                f"{'🔐 密码保护: 是' if info.get('has_password') else '🔓 密码保护: 否'}",
            ]
        else:
            lines = ["❌ 文件格式不正确: 不是有效的 .stardebate 文件"]
        for line in lines:
            lbl = QLabel(line)
            lbl.setFont(QFont("Microsoft YaHei", 11))
            lbl.setWordWrap(True)
            self._verify_layout.addWidget(lbl)
            self._verify_labels.append(lbl)
        self._schedule_resize()

    def _show_password_ui(self):
        self._pwd_card.setVisible(True)
        self._password_attempts = 0
        self._lbl_retry.setText("")
        self._input_password.clear()
        self._input_password.setFocus()
        self._hide_decrypted_ui()
        self._schedule_resize()

    def _hide_password_ui(self):
        self._pwd_card.setVisible(False)

    def _show_decrypted_ui(self):
        for w in [self._preview_card, self._options_card, self._modules_card]:
            w.setVisible(True)
        self._btn_import.setVisible(True)
        self._hide_password_ui()
        self._schedule_resize()

    def _hide_decrypted_ui(self):
        for w in [self._preview_card, self._options_card, self._modules_card]:
            w.setVisible(False)
        self._btn_import.setVisible(False)
        self._schedule_resize()

    def _auto_decrypt(self):
        if not self._file_data or not self._compiler:
            return
        result = self._compiler.unpack(self._file_data)
        if result["success"]:
            self._on_decrypt_success(result)
        else:
            CustomDialog.error(self, "解密失败", result.get("error", "未知错误"))

    def _on_try_decrypt(self):
        password = self._input_password.text()
        if not password:
            CustomDialog.warning(self, "提示", "请输入密码。"); return
        self._password_attempts += 1
        remaining = self._max_attempts - self._password_attempts
        if not self._file_data or not self._compiler:
            return
        result = self._compiler.unpack(self._file_data, password=password)
        if result["success"]:
            self._on_decrypt_success(result)
        else:
            if remaining > 0:
                self._lbl_retry.setText(f"❌ 密码不正确，剩余尝试次数: {remaining}/{self._max_attempts}")
                self._input_password.clear()
                self._input_password.setFocus()
            else:
                CustomDialog.error(self, "密码错误", f"密码验证失败 {self._max_attempts} 次\n导入已取消")
                self.close()

    def _on_decrypt_success(self, result):
        self._decrypted_modules = result.get("modules", {})
        self._decrypted_meta = result.get("meta", {})
        self._show_decrypted_ui()

        basic = self._decrypted_modules.get("basic", {})
        self._lbl_preview_pro.setText(f"正方: {basic.get('pro', '—')}")
        self._lbl_preview_con.setText(f"反方: {basic.get('con', '—')}")
        fmt = basic.get('format', {})
        fmt_info = ""
        if fmt and isinstance(fmt, dict):
            pc = len(fmt.get('positions', []))
            ts = fmt.get('team_size', 0)
            fmt_info = f"赛制: {fmt.get('name','未知')}（{pc}辩位，{ts}人/方）"
        created_ts = self._decrypted_meta.get("created", 0)
        created_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(created_ts)) if created_ts else "未知"
        app_ver = self._decrypted_meta.get("app_version", "未知")
        has_pwd = self._decrypted_meta.get("has_password", False)
        self._lbl_preview_info.setText(
            f"📅 创建时间: {created_str}\n🏷 创建版本: StarDebate v{app_ver}\n"
            f"📦 包含模块: {len(self._decrypted_modules)} 个\n{fmt_info}")
        self._lbl_preview_badge.setText(
            "🔐 密码保护: 是 (双层加密)" if has_pwd else "🔓 密码保护: 否 (单层加密)")

        self._build_module_checkboxes()

    def _build_module_checkboxes(self):
        for cb in self._module_checkboxes.values():
            cb.deleteLater()
        self._module_checkboxes.clear()

        while self._modules_layout.count():
            item = self._modules_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        title = QLabel("导入模块选择")
        title.setObjectName("stdebCardTitle")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        self._modules_layout.addWidget(title)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(12)
        self._chk_all = StarCheckBox("全部选中", icon_scheme="auto")
        self._chk_all.setFont(QFont("Microsoft YaHei", 11))
        self._chk_all.setCursor(Qt.PointingHandCursor)
        self._chk_all.setChecked(True)
        self._chk_all.toggled.connect(self._on_toggle_all)
        toggle_row.addWidget(self._chk_all)
        toggle_row.addStretch()
        self._modules_layout.addLayout(toggle_row)

        grid = QVBoxLayout()
        grid.setSpacing(2)
        row_layout = None
        for i, mod_id in enumerate(sorted(self._decrypted_modules.keys())):
            if i % 2 == 0:
                row_layout = QHBoxLayout()
                row_layout.setSpacing(16)
                grid.addLayout(row_layout)
            cb = StarCheckBox(mod_id, icon_scheme="auto")
            cb.setFont(QFont("Microsoft YaHei", 11))
            cb.setCursor(Qt.PointingHandCursor)
            cb.setChecked(True)
            self._module_checkboxes[mod_id] = cb
            if row_layout is not None:
                row_layout.addWidget(cb, stretch=1)
        self._modules_layout.addLayout(grid)
        self._schedule_resize()

    def _on_toggle_all(self, checked):
        for cb in self._module_checkboxes.values():
            cb.setChecked(checked)

    def _toggle_pwd_visible(self):
        mode = QLineEdit.Normal if self._input_password.echoMode() == QLineEdit.Password else QLineEdit.Password
        self._input_password.setEchoMode(mode)
        self._btn_pwd_eye.setText("" if mode == QLineEdit.Normal else "")

    def _browse_target(self):
        is_new = self._radio_new.isChecked()
        if is_new:
            folder = QFileDialog.getExistingDirectory(self, "选择父目录")
            if folder:
                basic = self._decrypted_modules.get("basic", {}) if self._decrypted_modules else {}
                pro = basic.get("pro", "正方")
                name = f"{pro}_导入_{time.strftime('%Y%m%d')}"
                self._input_target.setText(os.path.join(folder, name))
        else:
            folder = QFileDialog.getExistingDirectory(self, "选择项目目录")
            if folder:
                self._input_target.setText(folder)

    def _on_import(self):
        if self._importing:
            return
        target = self._input_target.text().strip()
        if not target:
            CustomDialog.warning(self, "提示", "请选择导入目标路径。"); return
        is_new = self._radio_new.isChecked()
        selected = {mid for mid, cb in self._module_checkboxes.items() if cb.isChecked()}
        if not selected:
            CustomDialog.warning(self, "提示", "请选择至少一个数据模块。"); return
        mw = self._mw
        if not mw:
            return

        if is_new:
            if os.path.exists(target):
                r = CustomDialog.question(self, "确认", f"目标路径已存在:\n{target}\n\n是否覆盖？",
                                          buttons=[("否","no"),("是","yes")])
                if r != "yes":
                    return
            else:
                try:
                    os.makedirs(target)
                except OSError as e:
                    CustomDialog.error(self, "创建失败", f"无法创建目录:\n{str(e)}"); return
            project_dir = target
        else:
            if not os.path.isdir(target):
                CustomDialog.warning(self, "提示", "目标路径不存在。"); return
            project_dir = target

        self._importing = True
        self._btn_import.setText("⏳ 导入中...")
        self._btn_import.setEnabled(False)
        QApplication.processEvents()

        try:
            success = restore_debate_data(mw, self._decrypted_modules, selected, project_dir)
            fname = os.path.basename(self._input_file_path.text())
            CustomDialog.information(self, "导入完成",
                f"辩论文件已成功导入\n━━━━━━━━━━━━━━━\n"
                f"源文件: {fname}\n目标: {project_dir}\n"
                f"模块: {len(selected)} 个\n{'✅ 全部成功' if success else '⚠ 部分模块失败'}")
            self.close()
        except Exception as e:
            CustomDialog.error(self, "导入失败", f"导入过程中发生错误:\n{str(e)}")
            self._btn_import.setText("开始导入")
            self._btn_import.setEnabled(True)
            self._importing = False

    # ══════════════════════════════════════════════════════════════════
    #  样式
    # ══════════════════════════════════════════════════════════════════

    def _get_project_root(self) -> str:
        from components.res_path import get_resource_root
        return get_resource_root()

    def _schedule_resize(self):
        """延迟触发尺寸调整，确保布局更新完成"""
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(20, self._auto_adjust_size)

    def _auto_adjust_size(self):
        """根据可见控件动态调整窗口高度，无多余空白"""
        if not hasattr(self, '_content_widget') or not self._content_widget:
            return
        self._content_widget.adjustSize()
        QApplication.processEvents()

        # 累加可见控件高度
        lo = self._content_widget.layout()
        if not lo:
            return
        visible_h = 0
        for i in range(lo.count()):
            item = lo.itemAt(i)
            w = item.widget()
            if w and w.isVisible():
                visible_h += w.height()
            elif item.layout():
                # 检查布局所属父控件是否可见
                parent = item.layout().parentWidget()
                if parent and parent.isVisible():
                    # 布局本身的高度需要单独计算
                    lh = 0
                    for j in range(item.layout().count()):
                        sub = item.layout().itemAt(j)
                        sw = sub.widget()
                        if sw and sw.isVisible():
                            lh += sw.height()
                    visible_h += lh if lh > 0 else 20  # 至少给行高

        margins = lo.contentsMargins()
        total_h = visible_h + margins.top() + margins.bottom() + lo.spacing() * max(lo.count() - 1, 0)
        total_h += 42  # 标题栏
        total_h += 4   # 容差

        screen_h = QApplication.primaryScreen().geometry().height()
        max_h = int(screen_h * 0.85)
        target_h = min(total_h, max_h)
        target_w = self.width()
        self.resize(target_w, target_h)
        if self._mw:
            pg = self._mw.geometry()
            self.move(pg.x() + (pg.width() - target_w) // 2,
                      pg.y() + (pg.height() - target_h) // 2)

    def _apply_style(self):
        try:
            from components.theme_colors import tc
            from workers.app_config.config_paths import get_config_path
            cfg_path = get_config_path("config/config.json")
            theme_name = "catppuccin_mocha"
            if os.path.isfile(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    theme_name = json.load(f).get("theme", theme_name)
            theme_dir = os.path.join(self._get_project_root(), "style", "themes", theme_name)

            # ── 加载 TitleBar + StarCheckBox QSS（如有）──
            combined = ""
            for fname in ("title_bar.qss", "star_checkbox.qss"):
                fp = os.path.join(theme_dir, fname)
                if os.path.isfile(fp):
                    with open(fp, 'r', encoding='utf-8') as f:
                        combined += f.read() + "\n"

            # ── 全部 QSS 用 tc() 动态生成，确保始终跟随当前主题 ──
            B = tc("base")          # 背景
            S = tc("surface")       # 卡片背景
            T = tc("text")          # 文字颜色
            M = tc("muted")         # 次要文字
            H = tc("hover")         # 悬停背景
            A = tc("accent_blue")   # 强调色
            BD = tc("border")       # 边框
            PR = tc("pressed")      # 次要文字

            combined += f"""
#{self.obj_name} {{
    background-color: {B};
}}

/* -- 滚动区 -- */
#stdebContentScroll {{
    background-color: transparent;
}}

/* -- 内容容器 -- */
#stdebContent {{
    background-color: transparent;
}}

/* -- 所有卡片（QFrame）共享 -- */
#stdebContent QFrame {{
    background-color: {S};
    border: none;
    border-radius: 6px;
}}

/* -- 标签 -- */
#stdebContent QLabel {{
    color: {T};
    background-color: transparent;
    padding: 0px;
}}
#stdebCardTitle {{
    color: {T};
    font-size: 12pt;
    font-weight: bold;
}}
#stdebEncryptBadge {{
    color: {A};
    font-weight: bold;
}}
#stdebPwdRetryCount, #stdebPwdStrengthLabel {{
    color: {M};
    font-size: 10pt;
}}
#stdebSizeEstimate {{
    color: {M};
    font-size: 10pt;
}}
#stdebInfoLabel {{
    color: {T};
    font-size: 11pt;
}}

/* -- 输入框 -- */
#stdebContent QLineEdit {{
    background-color: transparent;
    color: {T};
    border: none;
    border-bottom: 1px solid {BD};
    border-radius: 0px;
    padding: 6px 4px;
    font-size: 11pt;
}}
#stdebContent QLineEdit:focus {{
    border-bottom: 2px solid {A};
}}

/* -- 单选按钮 -- */
#stdebContent QRadioButton {{
    color: {T};
    font-size: 11pt;
    background-color: transparent;
}}
#stdebContent QRadioButton::indicator {{
    width: 16px;
    height: 16px;
}}

/* -- 密码强度条 -- */
#stdebPwdStrengthBar {{
    border: none;
    border-radius: 3px;
    background-color: {H};
    text-align: center;
    font-size: 9pt;
}}
#stdebPwdStrengthBar::chunk {{
    border-radius: 3px;
    background-color: {A};
}}

"""
            self.setStyleSheet(combined)
        except Exception:
            pass
