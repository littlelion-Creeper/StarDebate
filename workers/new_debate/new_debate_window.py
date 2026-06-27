"""NewDebateWindow：新建辩论窗口"""
import os
import re
import json
import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QLineEdit, QComboBox,
)
from PyQt5.QtCore import Qt, QEvent, QRectF
from PyQt5.QtGui import QFont, QPainterPath, QRegion

from components.popup_dialog import CustomDialog
from components.theme_colors import tc
from components.star_button import StarButton
from components.title_bar import TitleBar
from components.svg_renderer import SvgRenderer
from workers.app_config.config_paths import get_config_path


class NewDebateWindow(QWidget):
    """新建辩论窗口 — 风格与父窗口一致"""

    def __init__(self, parent=None, project_path="", competition_formats=None, competition_presets=None):
        super().__init__()
        self.project_path = project_path
        self.main_window = parent  # 保留父窗口引用用于刷新树
        self._competition_formats = competition_formats or []
        self._competition_presets = competition_presets or {}
        self._selected_format_name: str = ""  # 选中的赛制名称
        self._selected_format_data: dict | None = None  # 选中的赛制数据

        self.setObjectName("newDebatePanel")
        self.setWindowTitle("新建辩论 - Star Debate")
        self.resize(680, 650)
        self.setMinimumSize(500, 450)
        self.setWindowFlags(
            (self.windowFlags() & ~Qt.WindowContextHelpButtonHint) | Qt.FramelessWindowHint
        )
        self.setAttribute(Qt.WA_StyledBackground, True)

        # 相对父窗口居中
        if parent:
            pg = parent.geometry()
            self.move(pg.x() + (pg.width() - self.width()) // 2,
                      pg.y() + (pg.height() - self.height()) // 2)

        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        # ── 顶层布局（无间距，TitleBar 占满横向）──
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 标题栏 (TitleBar 通用控件) ──
        self._build_title_bar()
        main_layout.addWidget(self._title_bar)

        # ── 内容区 ──
        content_widget = QWidget()
        content_widget.setObjectName("newDebateContent")
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 标题
        header = QLabel("新建辩论")
        header.setFont(QFont("Microsoft YaHei", 20, QFont.Bold))
        header.setObjectName("dialogTitle")
        layout.addWidget(header)

        # 辩论名称（可选项）
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        lbl_name = QLabel("辩论名称")
        lbl_name.setObjectName("debateNameLabel")
        lbl_name.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        self.edit_debate_name = QLineEdit()
        self.edit_debate_name.setObjectName("lineEdit")
        self.edit_debate_name.setPlaceholderText("为本次辩论起个名字（留空则自动以时间命名）")
        self.edit_debate_name.setFont(QFont("Microsoft YaHei", 11))
        self.edit_debate_name.setFixedHeight(50)
        self.edit_debate_name.setMaxLength(50)
        self.edit_debate_name.textChanged.connect(self._on_debate_name_changed)
        name_row.addWidget(lbl_name)
        name_row.addWidget(self.edit_debate_name, stretch=1)
        layout.addLayout(name_row)

        # 表单容器
        form_frame = QFrame()
        form_frame.setObjectName("formFrame")
        form_layout = QVBoxLayout(form_frame)
        form_layout.setContentsMargins(20, 20, 20, 20)
        form_layout.setSpacing(14)

        # 赛制选择
        format_row = QHBoxLayout()
        format_row.setSpacing(8)
        lbl_format = QLabel("赛制选择")
        lbl_format.setObjectName("formatLabel")
        lbl_format.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        self._format_combo = QComboBox()
        self._format_combo.setObjectName("formatCombo")
        self._format_combo.setFont(QFont("Microsoft YaHei", 11))
        self._format_combo.setFixedHeight(32)
        self._format_combo.setCursor(Qt.PointingHandCursor)
        # 填充选项：预设 + 自定义
        self._format_combo.addItem("（不指定赛制）", None)
        for name in self._competition_presets:
            self._format_combo.addItem(f"📌 {name}（预设）", {"name": name, "data": self._competition_presets[name], "type": "preset"})
        for fmt in self._competition_formats:
            fmt_name = fmt.get("name", "未命名")
            self._format_combo.addItem(f"✏️ {fmt_name}（自定义）", {"name": fmt_name, "data": fmt, "type": "custom"})
        self._format_combo.currentIndexChanged.connect(self._on_format_selected)
        format_row.addWidget(lbl_format)
        format_row.addWidget(self._format_combo, stretch=1)
        form_layout.addLayout(format_row)

        # 正方 / 反方 并排
        sides_row = QHBoxLayout()
        sides_row.setSpacing(12)

        left_side = QVBoxLayout()
        left_side.setSpacing(6)
        lbl_pro = QLabel("正方")
        lbl_pro.setObjectName("proHdrLabel")
        lbl_pro.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        self.edit_pro = QLineEdit()
        self.edit_pro.setObjectName("lineEdit")
        self.edit_pro.setPlaceholderText("正方")
        self.edit_pro.setFont(QFont("Microsoft YaHei", 11))
        self.edit_pro.setFixedHeight(50)
        left_side.addWidget(lbl_pro)
        left_side.addWidget(self.edit_pro)

        right_side = QVBoxLayout()
        right_side.setSpacing(6)
        lbl_con = QLabel("反方")
        lbl_con.setObjectName("conHdrLabel")
        lbl_con.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        self.edit_con = QLineEdit()
        self.edit_con.setObjectName("lineEdit")
        self.edit_con.setPlaceholderText("反方")
        self.edit_con.setFont(QFont("Microsoft YaHei", 11))
        self.edit_con.setFixedHeight(50)
        right_side.addWidget(lbl_con)
        right_side.addWidget(self.edit_con)

        sides_row.addLayout(left_side)
        sides_row.addLayout(right_side)

        # 正方论点
        lbl_pro_args = QLabel("正方论点")
        lbl_pro_args.setObjectName("proArgsLabel")
        lbl_pro_args.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        self.edit_pro_args = QLineEdit()
        self.edit_pro_args.setObjectName("lineEdit")
        self.edit_pro_args.setPlaceholderText("请输入正方立场")
        self.edit_pro_args.setFont(QFont("Microsoft YaHei", 11))
        self.edit_pro_args.setFixedHeight(50)

        # 反方论点
        lbl_con_args = QLabel("反方论点")
        lbl_con_args.setObjectName("conArgsLabel")
        lbl_con_args.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        self.edit_con_args = QLineEdit()
        self.edit_con_args.setObjectName("lineEdit")
        self.edit_con_args.setPlaceholderText("请输入反方立场")
        self.edit_con_args.setFont(QFont("Microsoft YaHei", 11))
        self.edit_con_args.setFixedHeight(50)

        form_layout.addLayout(sides_row)
        form_layout.addWidget(lbl_pro_args)
        form_layout.addWidget(self.edit_pro_args)
        form_layout.addWidget(lbl_con_args)
        form_layout.addWidget(self.edit_con_args)
        form_layout.addStretch()

        layout.addWidget(form_frame)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()

        btn_cancel = StarButton("取消", parent=content_widget)
        btn_cancel.setFixedSize(100, 38)
        btn_cancel.clicked.connect(self.close)

        btn_confirm = StarButton("创建辩论", accent=tc("accent_blue"), parent=content_widget)
        btn_confirm.setFixedSize(120, 38)
        btn_confirm.clicked.connect(self._on_confirm)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_confirm)

        layout.addLayout(btn_row)

        main_layout.addWidget(content_widget, stretch=1)

    def _build_title_bar(self):
        """构建标题栏 — 使用 TitleBar 通用控件"""
        self._title_bar = TitleBar(parent=self, title="新建辩论", icon="")
        self._title_bar.setObjectName("ndTitleBar")
        self._set_title_bar_icon()

    def _set_title_bar_icon(self):
        """将标题栏图标替换为 new_program.svg（22px）"""
        from components.res_path import get_resource_root
        svg_path = os.path.join(
            get_resource_root(),
            "icon", "windows_icon", "new_program.svg"
        )
        if os.path.isfile(svg_path):
            pixmap = SvgRenderer.render(svg_path, 22, mode="mono", color=tc("accent_blue"))
            self._title_bar._icon_label.setPixmap(pixmap)
            self._title_bar._icon_label.setFixedWidth(30)

    def _on_debate_name_changed(self, text: str):
        """实时过滤文件名非法字符"""
        invalid = set(r'\/:*?"<>|')
        if any(ch in invalid for ch in text):
            clean = ''.join(ch for ch in text if ch not in invalid)
            cursor = self.edit_debate_name.cursorPosition()
            self.edit_debate_name.setText(clean)
            # 光标位置修正：移除的字符数可能在光标前，将光标置于末尾更稳定
            self.edit_debate_name.setCursorPosition(
                max(0, min(cursor, len(clean)))
            )

    # ── 窗口事件 ─────────────────────────────────────────────────
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

    def _on_format_selected(self, index: int):
        """赛制下拉框选择变化"""
        data = self._format_combo.itemData(index)
        if data:
            self._selected_format_name = data["name"]
            self._selected_format_data = data["data"]
        else:
            self._selected_format_name = ""
            self._selected_format_data = None

    def _on_confirm(self):
        """确认创建辩论"""
        pro = self.edit_pro.text().strip()
        con = self.edit_con.text().strip()
        pro_args = self.edit_pro_args.text().strip()
        con_args = self.edit_con_args.text().strip()
        debate_name = self.edit_debate_name.text().strip()

        if not pro or not con:
            CustomDialog.warning(self, "提示", "请填写正方和反方名称")
            return
        if not pro_args or not con_args:
            CustomDialog.warning(self, "提示", "请填写正方和反方的论点")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # 确定文件名：自定义名称 or 时间戳
        if debate_name:
            # 二次 sanitize（防御性）
            clean_name = re.sub(r'[\\/:*?"<>|]', '', debate_name).strip()
            if not clean_name:
                # 全为非法字符时回退时间戳
                safe_name = f"debate_{timestamp}.json"
            else:
                safe_name = f"{clean_name}.json"
        else:
            safe_name = f"debate_{timestamp}.json"

        save_path = os.path.join(self.project_path, safe_name)

        # 文件已存在时弹窗
        if os.path.exists(save_path):
            reply = CustomDialog.question(
                self, "文件已存在",
                f"文件“{safe_name}”已存在，是否覆盖？",
                buttons=[("覆盖", "覆盖"), ("取消", "取消")]
            )
            if reply != "覆盖":
                return

        debate_data = {
            "pro": pro,
            "con": con,
            "pro_args": pro_args,
            "con_args": con_args,
            "created": timestamp
        }

        # 保存辩论名称
        if debate_name:
            clean_name = re.sub(r'[\\/:*?"<>|]', '', debate_name).strip()
            debate_data["debate_name"] = clean_name

        # 保存赛制信息
        if self._selected_format_name and self._selected_format_data:
            debate_data["format"] = {
                "name": self._selected_format_name,
                "team_size": self._selected_format_data.get("team_size", 0),
                "positions": self._selected_format_data.get("positions", []),
                "free_debate": self._selected_format_data.get("free_debate")
            }

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(debate_data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            CustomDialog.error(self, "保存失败", f"无法保存文件:\n{str(e)}")
            return

        format_info = f"\n赛制: {self._selected_format_name}" if self._selected_format_name else ""
        name_info = f"\n辩论名称: {debate_name}" if debate_name else ""
        CustomDialog.information(
            self, "创建成功",
            f"辩论已创建\n━━━━━━━━━━\n"
            f"正方: {pro}\n论点: {pro_args}\n\n"
            f"反方: {con}\n论点: {con_args}{name_info}{format_info}\n\n"
            f"已保存至: {safe_name}"
        )

        # 刷新主窗口树控件
        if self.main_window:
            self.main_window._build_tree_from_path(self.project_path)

        self.close()

    @staticmethod
    def _get_project_root() -> str:
        from components.res_path import get_resource_root
        return get_resource_root()

    def _apply_style(self):
        """加载主题 QSS + 用 tc() 动态生成内容区 QSS"""
        # ── 加载 title_bar.qss（主题目录）──
        combined = ""
        theme_name = "catppuccin_mocha"
        config_path = get_config_path("config/config.json")
        if os.path.isfile(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                theme_name = cfg.get("theme", theme_name)
            except (json.JSONDecodeError, OSError):
                pass
        theme_dir = os.path.join(self._get_project_root(), "style", "themes", theme_name)
        for fname in ("title_bar.qss",):
            fp = os.path.join(theme_dir, fname)
            if os.path.isfile(fp):
                with open(fp, "r", encoding="utf-8") as f:
                    combined += f.read() + "\n"

        # ── 内容区 QSS 用 tc() 动态生成 ──
        B = tc("base")
        S = tc("surface")
        T = tc("text")
        BD = tc("border")
        H = tc("hover")
        A = tc("accent_blue")
        SEL = tc("selected_bg")

        combined += f"""
#newDebatePanel {{
    background-color: {B};
}}

#ndTitleBar {{
    background-color: {B};
}}

#newDebateContent {{
    background-color: {B};
}}

#dialogTitle {{
    color: {T};
    background: transparent;
    padding: 0px;
}}

#formFrame {{
    background-color: {S};
    border: 1px solid {BD};
    border-radius: 6px;
}}

QLabel {{
    color: {T};
    background: transparent;
}}

QLineEdit {{
    background-color: transparent;
    border: none;
    border-bottom: 1px solid {BD};
    border-radius: 0px;
    padding: 6px 4px;
    color: {T};
}}
QLineEdit:focus {{
    border-bottom: 2px solid {A};
}}

QComboBox {{
    background-color: transparent;
    border: none;
    border-bottom: 1px solid {BD};
    border-radius: 0px;
    padding: 5px 8px;
    color: {T};
    font-size: 11pt;
}}
QComboBox:hover {{
    background-color: {H};
}}
QComboBox QAbstractItemView {{
    background-color: {S};
    color: {T};
    border: 1px solid {BD};
    border-radius: 4px;
    selection-background-color: {SEL};
}}
"""
        self.setStyleSheet(combined)
