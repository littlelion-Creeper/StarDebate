"""StardebateExportDialog — .stardebate 文件导出独立窗口

使用 TitleBar 通用控件 + 多文件规则 UI 拆分:
  - _build_title_bar()      标题栏 (TitleBar 通用组件)
  - _build_content()         主内容区
  - _build_debate_info_card()   辩论信息卡片
  - _build_export_scope_card()  导出范围卡片
  - _build_security_card()      安全设置卡片
  - _build_save_path_card()     保存位置卡片
  - _build_bottom_buttons()     底部按钮
"""

import os, sys, json, re, time, ctypes
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QLineEdit, QProgressBar, QFileDialog,
    QApplication, QScrollArea,
)
from PyQt5.QtCore import Qt, QEvent, QRectF
from PyQt5.QtGui import QFont, QPainterPath, QRegion

from components.title_bar import TitleBar
from components.star_button import StarButton
from components.popup_dialog import CustomDialog
from components.star_checkbox import StarCheckBox
from .stardebate_compiler import StardebateCompiler, collect_debate_data
from workers.app_config.config_paths import get_config_path


# ── 模块定义 ────────────────────────────────────────────────────────────
ALL_MODULES: list[tuple] = [
    ("basic",           "辩论信息",   "正方/反方/论点/赛制",   True),
    ("speech_pro",     "正方一辩稿", "正方立场阐述稿",       True),
    ("speech_con",     "反方一辩稿", "反方立场阐述稿",       True),
    ("ref_doc_pro",    "正方资料稿", "正方论证表格数据",     False),
    ("ref_doc_con",    "反方资料稿", "反方论证表格数据",     False),
    ("analysis_pro",   "正方AI分析", "AI 分析报告",          False),
    ("analysis_con",   "反方AI分析", "AI 分析报告",          False),
    ("framework",      "辩论框架",   "思维导图节点",         False),
    ("cross_exam",     "模拟质询",   "质询模拟记录",         False),
    ("accept_exam_pro","正方接质",   "正方接质模拟",         False),
    ("accept_exam_con","反方接质",   "反方接质模拟",         False),
    ("notes",          "便签数据",   "便签内容",             False),
    ("structure",      "结构树",     "一辩稿结构分析",       False),
    ("training",       "训练记录",   "模拟训练历史",         False),
]


class StardebateExportDialog(QWidget):
    """导出 .stardebate 文件 — 独立窗口 (TitleBar 通用控件)"""

    obj_name = "stdebExportDialog"

    def __init__(self, parent=None):
        super().__init__(None)
        self._mw = parent
        self._compiler: StardebateCompiler | None = None
        self._module_checkboxes: dict[str, StarCheckBox] = {}
        self._module_sizes: dict[str, int] = {}
        self._module_names: dict[str, str] = {}
        self._password_visible: bool = False
        self._exporting: bool = False
        self._config = self._load_config()

        self.setWindowTitle("导出 .stardebate 辩论文件")
        self.resize(560, 640)
        self.setMinimumSize(480, 560)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setObjectName(self.obj_name)
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._setup_ui()
        self._apply_style()
        self._auto_adjust_size()
        self._refresh_debate_info()
        self._refresh_size_estimate()

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
        if self.isMaximized():
            self.clearMask()
            return
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 12, 12)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def nativeEvent(self, event_type, message):
        """Windows: 无边框窗口边缘拖拽缩放 (6px)"""
        if sys.platform != 'win32':
            return False, 0
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST
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
    #  UI 构建 (多文件规则拆分为独立方法)
    # ══════════════════════════════════════════════════════════════════

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 标题栏 (TitleBar 通用控件) ──
        self._build_title_bar()

        # ── 主内容 (ScrollArea) ──
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
        """构建标题栏 — 使用 TitleBar 通用控件"""
        self._title_bar = TitleBar(
            parent=self, title="导出 .stardebate 辩论文件", icon=""
        )
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
        """构建主内容区"""
        w = QWidget()
        w.setObjectName("stdebContent")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 12, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(self._build_debate_info_card())
        layout.addWidget(self._build_export_scope_card())
        layout.addWidget(self._build_security_card())
        layout.addWidget(self._build_save_path_card())
        layout.addLayout(self._build_bottom_buttons())
        layout.addStretch()

        return w

    # ── 辩论信息卡片 ─────────────────────────────────────────────────

    def _build_debate_info_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("stdebDebateInfoCard")
        lo = QVBoxLayout(card)
        lo.setContentsMargins(14, 12, 14, 12)
        lo.setSpacing(4)
        for attr in ['_lbl_pro', '_lbl_con', '_lbl_args', '_lbl_format']:
            lbl = QLabel("—")
            lbl.setObjectName("stdebInfoLabel")
            lbl.setFont(QFont("Microsoft YaHei", 11))
            lbl.setWordWrap(True)
            lo.addWidget(lbl)
            setattr(self, attr, lbl)
        self._lbl_pro.setText("正方: —")
        self._lbl_con.setText("反方: —")
        self._lbl_args.setText("论点: —")
        self._lbl_format.setText("赛制: —")
        return card

    # ── 导出范围卡片 ─────────────────────────────────────────────────

    def _build_export_scope_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("stdebExportScopeCard")
        lo = QVBoxLayout(card)
        lo.setContentsMargins(14, 12, 14, 12)
        lo.setSpacing(4)

        title = QLabel("导出范围")
        title.setObjectName("stdebCardTitle")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        lo.addWidget(title)

        grid = QVBoxLayout()
        grid.setSpacing(2)
        row_layout = None
        for i, (mod_id, mod_name, _desc, is_main) in enumerate(ALL_MODULES):
            if i % 2 == 0:
                row_layout = QHBoxLayout()
                row_layout.setSpacing(16)
                grid.addLayout(row_layout)
            cb = StarCheckBox(mod_name, icon_scheme="auto")
            cb.setObjectName(f"stdebModule_{mod_id}")
            cb.setFont(QFont("Microsoft YaHei", 11))
            cb.setCursor(Qt.PointingHandCursor)
            cb.setChecked(is_main or mod_id in self._config.get("default_selected_modules", []))
            cb.toggled.connect(lambda checked, mid=mod_id, cb=cb:
                               self._on_module_toggled(mid, checked, cb))
            self._module_checkboxes[mod_id] = cb
            self._module_sizes[mod_id] = 0
            self._module_names[mod_id] = mod_name
            if row_layout is not None:
                row_layout.addWidget(cb, stretch=1)
        lo.addLayout(grid)

        self._lbl_size_est = QLabel("已选: 0/0 模块 | 预计总大小: —")
        self._lbl_size_est.setObjectName("stdebSizeEstimate")
        self._lbl_size_est.setFont(QFont("Microsoft YaHei", 10))
        lo.addWidget(self._lbl_size_est)
        return card

    # ── 安全设置卡片 ─────────────────────────────────────────────────

    def _build_security_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("stdebSecurityCard")
        lo = QVBoxLayout(card)
        lo.setContentsMargins(14, 12, 14, 12)
        lo.setSpacing(8)

        title = QLabel("安全设置")
        title.setObjectName("stdebCardTitle")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        lo.addWidget(title)

        self._chk_password = StarCheckBox("启用密码保护 (推荐)", icon_scheme="auto")
        self._chk_password.setObjectName("stdebPasswordToggle")
        self._chk_password.setFont(QFont("Microsoft YaHei", 11))
        self._chk_password.setCursor(Qt.PointingHandCursor)
        self._chk_password.toggled.connect(self._on_password_toggled)
        lo.addWidget(self._chk_password)

        self._pwd_area = QFrame()
        self._pwd_area.setObjectName("stdebPwdArea")
        self._pwd_area.setVisible(False)
        self._build_password_inputs()
        lo.addWidget(self._pwd_area)

        notice = QLabel(
            "🔒 第1层: StarDebate 内置密钥加密 (自动)\n"
            "🔒 第2层: 密码加密 (可选，启用后更强)\n"
            "⚠  密码无法找回，请务必牢记！\n"
            "📌 无密码: 仅 StarDebate 可读\n"
            "🔐 有密码: 需密码 + StarDebate 双重认证"
        )
        notice.setObjectName("stdebSecurityNotice")
        notice.setFont(QFont("Microsoft YaHei", 10))
        notice.setWordWrap(True)
        lo.addWidget(notice)
        return card

    def _build_password_inputs(self):
        """构建密码输入区域"""
        pwd_layout = self._pwd_area.layout() or QVBoxLayout(self._pwd_area)
        if not self._pwd_area.layout():
            pwd_layout.setContentsMargins(0, 0, 0, 0)
            pwd_layout.setSpacing(6)
        else:
            # 清空已有控件
            while pwd_layout.count():
                item = pwd_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
                elif item.layout():
                    # 递归清理子布局
                    while item.layout().count():
                        sub = item.layout().takeAt(0)
                        if sub.widget():
                            sub.widget().deleteLater()

        for placeholder, obj_name in [("请输入密码", "lineEdit"),
                                      ("请确认密码", "lineEdit")]:
            row = QHBoxLayout()
            row.setSpacing(8)
            inp = QLineEdit()
            inp.setObjectName(obj_name)
            inp.setFont(QFont("Microsoft YaHei", 11))
            inp.setEchoMode(QLineEdit.Password)
            inp.setPlaceholderText(placeholder)
            inp.setFixedHeight(34)
            row.addWidget(inp, stretch=1)
            if "Input" in obj_name:
                btn_eye = StarButton("👁", None, layout_mode="text_only", ratio_h=0.7)
                btn_eye.setObjectName("stdebPwdEyeBtn")
                btn_eye.setFixedSize(34, 34)
                btn_eye.setToolTip("显示/隐藏密码")
                btn_eye.clicked.connect(self._toggle_password_visible)
                row.addWidget(btn_eye)
                self._btn_eye = btn_eye
            pwd_layout.addLayout(row)
            setattr(self, f"_input_{obj_name}", inp)

        self._strength_bar = QProgressBar()
        self._strength_bar.setObjectName("stdebPwdStrengthBar")
        self._strength_bar.setFixedHeight(6)
        self._strength_bar.setRange(0, 100)
        self._strength_bar.setValue(0)
        self._strength_bar.setTextVisible(False)
        pwd_layout.addWidget(self._strength_bar)

        self._lbl_strength = QLabel("")
        self._lbl_strength.setObjectName("stdebPwdStrengthLabel")
        self._lbl_strength.setFont(QFont("Microsoft YaHei", 10))
        pwd_layout.addWidget(self._lbl_strength)

        # 连接密码变更信号
        inp_pwd = getattr(self, '_input_stdebPasswordInput', None)
        if inp_pwd:
            inp_pwd.textChanged.connect(self._on_password_changed)

    # ── 保存位置卡片 ─────────────────────────────────────────────────

    def _build_save_path_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("stdebSavePathCard")
        lo = QHBoxLayout(card)
        lo.setContentsMargins(14, 12, 14, 12)
        lo.setSpacing(8)

        self._input_save_path = QLineEdit()
        self._input_save_path.setObjectName("lineEdit")
        self._input_save_path.setFont(QFont("Microsoft YaHei", 11))
        self._input_save_path.setFixedHeight(34)
        self._input_save_path.setPlaceholderText("保存位置 — 点击右侧浏览选择...")

        btn = StarButton("📂 浏览", None, layout_mode="text_only", ratio_h=0.7)
        btn.setObjectName("stdebBrowseSaveBtn")
        btn.setFixedHeight(34)
        btn.clicked.connect(self._browse_save_path)

        lo.addWidget(self._input_save_path, stretch=1)
        lo.addWidget(btn)
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

        self._btn_export = StarButton("加密导出", None, layout_mode="text_only", ratio_h=0.7)
        self._btn_export.setObjectName("stdebExportBtn")
        self._btn_export.setFixedHeight(38)
        self._btn_export.clicked.connect(self._on_export)
        row.addWidget(self._btn_export)
        return row

    # ══════════════════════════════════════════════════════════════════
    #  事件处理
    # ══════════════════════════════════════════════════════════════════

    def _refresh_debate_info(self):
        mw = self._mw
        if mw and mw.current_debate_data:
            d = mw.current_debate_data
            self._lbl_pro.setText(f"正方: {d.get('pro', '—')}")
            self._lbl_con.setText(f"反方: {d.get('con', '—')}")
            self._lbl_args.setText(f"论点: {d.get('pro_args', '—')} / {d.get('con_args', '—')}")
            fmt = d.get('format', {})
            if fmt and isinstance(fmt, dict):
                pc = len(fmt.get('positions', []))
                ts = fmt.get('team_size', 0)
                self._lbl_format.setText(f"赛制: {fmt.get('name', '未知')}（{pc}辩位，{ts}人/方）")
            else:
                self._lbl_format.setText("赛制: 未指定")
        else:
            for lbl in [self._lbl_pro, self._lbl_con, self._lbl_args, self._lbl_format]:
                lbl.setText("—")
            self._lbl_pro.setText("正方: — (请先打开一个辩论文件)")

    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes <= 0:
            return "—"
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes / (1024 * 1024):.2f} MB"

    def _estimate_module_size(self, mod_id: str) -> int:
        """估算单个模块的 JSON 序列化大小"""
        mw = self._mw
        if not mw:
            return 0
        try:
            data = None
            dp = mw.current_debate_path
            pd = os.path.dirname(dp) if dp else None

            if mod_id == 'basic':
                data = mw.current_debate_data
            elif mod_id in ('speech_pro', 'speech_con'):
                side = 'pro' if 'pro' in mod_id else 'con'
                if pd:
                    for sfx in [f'speech_{side}.json', f'{side}_一辩稿.json']:
                        fp = os.path.join(pd, sfx)
                        if os.path.isfile(fp):
                            with open(fp, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                            break
            elif mod_id in ('ref_doc_pro', 'ref_doc_con'):
                if pd:
                    side = '正方' if 'pro' in mod_id else '反方'
                    for sfx in [f'ref_doc_{side}.json', 'ref_doc.json']:
                        fp = os.path.join(pd, sfx)
                        if os.path.isfile(fp):
                            with open(fp, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                            break
            elif mod_id in ('analysis_pro', 'analysis_con'):
                if pd:
                    side = 'pro' if 'pro' in mod_id else 'con'
                    for sfx in [f'analysis_{side}.json']:
                        fp = os.path.join(pd, sfx)
                        if os.path.isfile(fp):
                            with open(fp, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                            break
            elif mod_id == 'framework':
                try:
                    data = mw._framework_mgr.data
                except Exception:
                    pass
            elif mod_id == 'cross_exam':
                if pd:
                    fp = os.path.join(pd, 'cross_exam.json')
                    if os.path.isfile(fp):
                        with open(fp, 'r', encoding='utf-8') as f:
                            data = json.load(f)
            elif mod_id in ('accept_exam_pro', 'accept_exam_con'):
                if pd:
                    side = '正方' if 'pro' in mod_id else '反方'
                    fp = os.path.join(pd, f'accept_exam_{side}.json')
                    if os.path.isfile(fp):
                        with open(fp, 'r', encoding='utf-8') as f:
                            data = json.load(f)
            elif mod_id == 'notes':
                if pd:
                    fp = os.path.join(pd, 'sticky_notes.json')
                    if os.path.isfile(fp):
                        with open(fp, 'r', encoding='utf-8') as f:
                            data = json.load(f)
            elif mod_id == 'structure':
                try:
                    sp = mw._structure_mgr._get_data('pro')
                    sc = mw._structure_mgr._get_data('con')
                    if sp or sc:
                        data = {'pro': sp, 'con': sc}
                except Exception:
                    pass

            if data is not None:
                return len(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        except Exception:
            pass
        return 0

    def _on_module_toggled(self, mod_id: str, checked: bool, cb: StarCheckBox):
        """单个模块复选框切换 → 更新名称后缀 + 总计"""
        name = self._module_names.get(mod_id, mod_id)
        if checked:
            size = self._estimate_module_size(mod_id)
            self._module_sizes[mod_id] = size
            cb.setText(f"{name}  {self._format_size(size)}")
        else:
            self._module_sizes[mod_id] = 0
            cb.setText(name)
        self._update_size_label()

    def _refresh_size_estimate(self):
        """刷新所有选中模块的大小估算"""
        for mod_id, cb in self._module_checkboxes.items():
            if cb.isChecked():
                size = self._estimate_module_size(mod_id)
                self._module_sizes[mod_id] = size
                name = self._module_names.get(mod_id, mod_id)
                cb.setText(f"{name}  {self._format_size(size)}")
        self._update_size_label()

    def _update_size_label(self):
        """更新底部统计标签"""
        total = sum(s for s in self._module_sizes.values() if s > 0)
        checked = sum(1 for cb in self._module_checkboxes.values() if cb.isChecked())
        total_count = len(self._module_checkboxes)
        self._lbl_size_est.setText(
            f"已选: {checked}/{total_count} 模块 | 预计总大小: {self._format_size(total)}"
        )

    def _on_password_toggled(self, checked):
        self._pwd_area.setVisible(checked)
        if not checked:
            for attr in ['_input_stdebPasswordInput', '_input_stdebPasswordConfirm']:
                inp = getattr(self, attr, None)
                if inp:
                    inp.clear()
            self._strength_bar.setValue(0)
            self._lbl_strength.setText("")

    def _on_password_changed(self, text):
        if not text:
            self._strength_bar.setValue(0)
            self._lbl_strength.setText("")
            return
        score = 0
        if len(text) >= 6:  score += 20
        if len(text) >= 10: score += 15
        if re.search(r'[A-Z]', text): score += 15
        if re.search(r'[a-z]', text): score += 15
        if re.search(r'[0-9]', text): score += 15
        if re.search(r'[!@#$%^&*(),.?":{}|<>]', text): score += 20
        score = min(score, 100)
        self._strength_bar.setValue(score)
        levels = [(30, "弱"), (60, "中等"), (80, "强"), (100, "非常强")]
        for threshold, label in levels:
            if score < threshold:
                self._lbl_strength.setText(f"密码强度: {label}")
                break
        else:
            self._lbl_strength.setText("密码强度: 非常强")

    def _toggle_password_visible(self):
        self._password_visible = not self._password_visible
        mode = QLineEdit.Normal if self._password_visible else QLineEdit.Password
        for attr in ['_input_stdebPasswordInput', '_input_stdebPasswordConfirm']:
            inp = getattr(self, attr, None)
            if inp:
                inp.setEchoMode(mode)
        if hasattr(self, '_btn_eye'):
            self._btn_eye.setText("🙈" if self._password_visible else "👁")

    def _browse_save_path(self):
        mw = self._mw
        default_name = "辩论导出.stardebate"
        if mw and mw.current_debate_data:
            pro = mw.current_debate_data.get('pro', '')
            con = mw.current_debate_data.get('con', '')
            if pro and con:
                default_name = f"{pro}vs{con}_{time.strftime('%Y%m%d')}.stardebate"
        last_path = self._config.get("last_export_path", "")
        initial = os.path.join(last_path, default_name) if last_path else default_name
        path, _ = QFileDialog.getSaveFileName(self, "保存 .stardebate 文件", initial,
                                               "StarDebate 文件 (*.stardebate);;所有文件 (*)")
        if path:
            self._input_save_path.setText(path)
            self._config["last_export_path"] = os.path.dirname(path)
            self._save_config()

    def _on_export(self):
        if self._exporting:
            return
        mw = self._mw
        if not mw or not mw.current_debate_data:
            CustomDialog.warning(self, "提示", "请先在项目树中打开一个辩论文件。")
            return

        save_path = self._input_save_path.text().strip()
        if not save_path:
            CustomDialog.warning(self, "提示", "请选择保存位置。")
            return
        if not save_path.lower().endswith('.stardebate'):
            save_path += '.stardebate'

        selected = {mid for mid, cb in self._module_checkboxes.items() if cb.isChecked()}
        if not selected:
            CustomDialog.warning(self, "提示", "请选择至少一个数据模块。")
            return

        password = None
        if self._chk_password.isChecked():
            p1 = getattr(self, '_input_stdebPasswordInput', None)
            p2 = getattr(self, '_input_stdebPasswordConfirm', None)
            pw1 = p1.text() if p1 else ""
            pw2 = p2.text() if p2 else ""
            if not pw1:
                CustomDialog.warning(self, "提示", "请输入密码。"); return
            if len(pw1) < 6:
                CustomDialog.warning(self, "提示", "密码长度至少6位。"); return
            if pw1 != pw2:
                CustomDialog.warning(self, "提示", "两次输入的密码不一致。"); return
            password = pw1

        self._exporting = True
        self._btn_export.setText("⏳ 导出中...")
        self._btn_export.setEnabled(False)
        QApplication.processEvents()

        try:
            modules = collect_debate_data(mw, selected)
            if not modules:
                CustomDialog.warning(self, "导出失败", "没有可导出的数据。")
                self._reset_export_btn()
                return
            if self._compiler is None:
                self._compiler = StardebateCompiler()
            app_ver = mw._app_cfg.get_app_version() if hasattr(mw, '_app_cfg') else "1.0.0"
            file_bytes = self._compiler.pack(modules, password=password, app_version=app_ver)
            with open(save_path, 'wb') as f:
                f.write(file_bytes)
            size_kb = len(file_bytes) / 1024
            pwd_info = "🔐 密码保护已启用" if password else "🔓 无密码保护"
            CustomDialog.information(self, "导出成功",
                f"辩论文件已加密导出\n━━━━━━━━━━━━━━━\n"
                f"文件: {os.path.basename(save_path)}\n大小: {size_kb:.1f} KB\n"
                f"模块: {len(modules)} 个\n加密: {pwd_info}")
            self._config["default_selected_modules"] = sorted(selected)
            self._save_config()
            self.close()
        except ImportError as e:
            CustomDialog.error(self, "缺少依赖", str(e))
            self._reset_export_btn()
        except Exception as e:
            CustomDialog.error(self, "导出失败", f"导出过程中发生错误:\n{str(e)}")
            self._reset_export_btn()

    def _reset_export_btn(self):
        self._exporting = False
        self._btn_export.setText("加密导出")
        self._btn_export.setEnabled(True)

    # ══════════════════════════════════════════════════════════════════
    #  配置持久化
    # ══════════════════════════════════════════════════════════════════

    def _get_project_root(self) -> str:
        from components.res_path import get_resource_root
        return get_resource_root()

    def _load_config(self) -> dict:
        path = os.path.join(self._get_project_root(), "config", "stardebate_format_config.json")
        defaults = {"default_selected_modules": [m[0] for m in ALL_MODULES if m[3]],
                     "last_export_path": "", "remember_password_option": False}
        if os.path.isfile(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    defaults.update(json.load(f))
            except Exception:
                pass
        return defaults

    def _save_config(self):
        path = get_config_path("config/stardebate_format_config.json")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    def _auto_adjust_size(self):
        """智能调整窗口尺寸，确保所有控件完全显示且无滚动条"""
        if not hasattr(self, '_content_widget') or not self._content_widget:
            return
        # 计算内容实际所需高度
        self._content_widget.adjustSize()
        content_h = self._content_widget.sizeHint().height()
        # 标题栏 42px + 上下布局边距已在 content margins 中
        total_h = content_h + 42 + 2  # 2px 边距容差
        # 屏幕高度 85% 上限
        screen_h = QApplication.primaryScreen().geometry().height()
        max_h = int(screen_h * 0.85)
        target_h = min(total_h, max_h)
        # 宽度保持当前设定
        target_w = self.width()
        self.resize(target_w, target_h)
        # 重新居中
        if self._mw:
            pg = self._mw.geometry()
            self.move(pg.x() + (pg.width() - target_w) // 2,
                      pg.y() + (pg.height() - target_h) // 2)

    def _apply_style(self):
        try:
            from components.theme_colors import tc
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
#stdebSecurityNotice {{
    color: {M};
    font-size: 10pt;
    line-height: 1.4;
}}
#stdebSizeEstimate {{
    color: {M};
    font-size: 10pt;
}}
#stdebInfoLabel {{
    color: {T};
    font-size: 11pt;
}}
#stdebPwdStrengthLabel {{
    color: {M};
    font-size: 10pt;
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
