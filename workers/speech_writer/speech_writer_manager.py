from components.theme_colors import tc, refresh
# -*- coding: utf-8 -*-
"""AI写稿管理器 — UI 构建 + 业务逻辑 + 卡片管理

负责：
  - AI写稿面板的 UI 构建（标题栏 + 正方/反方按钮 + 结果卡片网格）
  - 导航栏切换按钮创建
  - AI 写稿触发、Worker 调度、结果解析与展示
  - 稿本结果卡片构建、展开/收起、网格重排
  - 面板互斥切换逻辑（与 AI扩写/便签/训练/插件互斥）
  - 事件过滤（scroll resize → 卡片网格重排）
  - 复制文本到剪切板

面板位于 splitter 索引 4，通过右侧导航栏「✍️ 写稿」按钮切换显示。
"""

import json as _json

from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QWidget, QGridLayout, QApplication,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from components.popup_dialog import CustomDialog
from components.star_button import StarButton
from .speech_writer_worker import AISpeechWriterWorker
from workers.nav_bar.nav_bar_manager import NavBarManager


class SpeechWriterManager:
    """AI写稿面板全生命周期管理器"""

    _FlowLayout = None  # 类级 FlowLayout 引用，由主窗口在实例化后注入

    def __init__(self, mw):
        """初始化管理器

        Args:
            mw: StarDebateWindow 主窗口引用
        """
        self._mw = mw

        # ---- 面板状态 ----
        self._visible: bool = False

        # ---- AI写稿数据 ----
        self._drafts: list[dict] = []
        self._cards: list[QFrame] = []
        self._worker: AISpeechWriterWorker | None = None
        self._dialog = None  # 进度弹窗（保留兼容，当前未使用）
        self._expanded_index: int = -1  # 当前展开的卡片索引，-1 表示无
        self._current_side: str = "pro"  # 当前生成的稿本立场

        # ---- UI 控件引用 ----
        self._panel: QFrame | None = None
        self._result_label: QLabel | None = None
        self._cards_scroll: QScrollArea | None = None
        self._cards_grid: QGridLayout | None = None
        self._empty_hint: QLabel | None = None

        # ---- 导航按钮 ----
        self._btn_toggle: QPushButton | None = None
        self._lbl_toggle: QLabel | None = None

        # ---- 正方/反方生成按钮 ----
        self.btn_pro: QPushButton | None = None
        self.btn_con: QPushButton | None = None

        # ---- 重排定时器 ----
        self._reflow_timer: QTimer | None = None

    # ========== 属性 ==========

    @property
    def visible(self) -> bool:
        return self._visible

    @property
    def panel(self) -> QFrame | None:
        return self._panel

    @property
    def cards_scroll(self) -> QScrollArea | None:
        return self._cards_scroll

    @property
    def cards(self) -> list[QFrame]:
        return self._cards

    @property
    def btn_toggle(self) -> QPushButton | None:
        return self._btn_toggle

    # ========== UI 构建 ==========

    def build_panel(self) -> QFrame:
        """构建 AI写稿面板，返回 QFrame（由主窗口添加到 splitter）"""
        panel = QFrame()
        panel.setObjectName("speechWriterPanel")
        panel.setMinimumWidth(480)
        panel.setMaximumWidth(2400)
        sw_layout = QVBoxLayout(panel)
        sw_layout.setContentsMargins(0, 0, 0, 0)
        sw_layout.setSpacing(0)

        # ---- 标题栏 ----
        sw_header = QFrame()
        sw_header.setObjectName("aiExpandHeader")
        sw_header.setFixedHeight(54)
        sw_header_layout = QHBoxLayout(sw_header)
        sw_header_layout.setContentsMargins(12, 6, 12, 6)
        sw_header_layout.setSpacing(8)

        lbl_sw_title = QLabel("AI写稿")
        lbl_sw_title.setObjectName("swPanelTitle")
        lbl_sw_title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))

        # 正方写稿按钮
        self.btn_pro = QPushButton("🟢 正方")
        self.btn_pro.setObjectName("smallBtn")
        self.btn_pro.setFixedHeight(36)
        self.btn_pro.setToolTip("基于框架稿为正方生成一辩稿")
        self.btn_pro.setCursor(Qt.PointingHandCursor)
        self.btn_pro.clicked.connect(lambda: self.generate("pro"))

        # 反方写稿按钮
        self.btn_con = QPushButton("🔴 反方")
        self.btn_con.setObjectName("smallBtn")
        self.btn_con.setFixedHeight(36)
        self.btn_con.setToolTip("基于框架稿为反方生成一辩稿")
        self.btn_con.setCursor(Qt.PointingHandCursor)
        self.btn_con.clicked.connect(lambda: self.generate("con"))

        btn_close = QPushButton("−")
        btn_close.setObjectName("smallBtn")
        btn_close.setFixedSize(42, 42)
        btn_close.setToolTip("关闭AI写稿面板")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.toggle_visibility)

        sw_header_layout.addWidget(lbl_sw_title)
        sw_header_layout.addStretch()
        sw_header_layout.addWidget(self.btn_pro)
        sw_header_layout.addWidget(self.btn_con)
        sw_header_layout.addWidget(btn_close)

        # ---- 结果区域 ----
        sw_cards_section = QFrame()
        sw_cards_section.setObjectName("aiExpandCardsSection")
        sw_cards_layout = QVBoxLayout(sw_cards_section)
        sw_cards_layout.setContentsMargins(8, 6, 8, 6)
        sw_cards_layout.setSpacing(6)

        lbl_sw_result = QLabel("生成结果")
        lbl_sw_result.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        lbl_sw_result.setStyleSheet(f"color: {tc("accent_green")};")

        self._result_label = QLabel("")
        self._result_label.setObjectName("swCurrentLabel")
        self._result_label.setFont(QFont("Microsoft YaHei", 9))
        self._result_label.setWordWrap(True)

        self._cards_scroll = QScrollArea()
        self._cards_scroll.setObjectName("aiExpandCardsScroll")
        self._cards_scroll.setWidgetResizable(True)
        self._cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._cards_scroll.installEventFilter(self._mw)

        sw_cards_container = QWidget()
        sw_cards_container.setObjectName("aiCardsContainer")
        self._cards_grid = QGridLayout(sw_cards_container)
        self._cards_grid.setContentsMargins(4, 4, 4, 4)
        self._cards_grid.setSpacing(8)
        self._cards_scroll.setWidget(sw_cards_container)

        # 空状态提示
        self._empty_hint = QLabel(
            "点击上方「正方」或「反方」按钮\n基于框架稿自动生成一辩稿\n结果将在此展示"
        )
        self._empty_hint.setObjectName("swEmptyHint")
        self._empty_hint.setFont(QFont("Microsoft YaHei", 11))
        self._empty_hint.setAlignment(Qt.AlignCenter)
        self._empty_hint.setWordWrap(True)

        sw_cards_layout.addWidget(lbl_sw_result)
        sw_cards_layout.addWidget(self._result_label)
        sw_cards_layout.addWidget(self._empty_hint, stretch=1)
        sw_cards_layout.addWidget(self._cards_scroll, stretch=1)

        sw_layout.addWidget(sw_header)
        sw_layout.addWidget(sw_cards_section, stretch=1)

        self._panel = panel
        self._panel.setVisible(False)
        return panel

    def build_nav_button(self) -> tuple[QPushButton, QLabel]:
        """构建右侧导航栏的 AI写稿切换按钮 + 标签（支持图标文件）

        Returns:
            (toggle_button, label)
        """
        self._btn_toggle = QPushButton()
        self._btn_toggle.setObjectName("navToggleBtn")
        self._btn_toggle.setCheckable(True)
        self._btn_toggle.setChecked(False)
        self._btn_toggle.setToolTip("开关 AI写稿")
        self._btn_toggle.setCursor(Qt.PointingHandCursor)
        self._btn_toggle.setFixedSize(50, 50)
        self._btn_toggle.clicked.connect(self.toggle_visibility)

        # ── 尝试加载图标文件 ──
        item = self._mw._nav_registry.get_item("speech_writer")
        icon = NavBarManager.load_nav_icon(item.icon) if item else None
        if icon is not None:
            NavBarManager._apply_icon_to_button(self._btn_toggle, icon)
        else:
            self._btn_toggle.setText("✍️")

        self._lbl_toggle = QLabel("写稿")
        self._lbl_toggle.setObjectName("swNavLabel")
        self._lbl_toggle.setFont(QFont("Microsoft YaHei", 8))
        self._lbl_toggle.setAlignment(Qt.AlignCenter)

        return self._btn_toggle, self._lbl_toggle

    # ========== 面板互斥切换 ==========

    def toggle_visibility(self):
        """切换 AI写稿面板的显示/隐藏（与其他面板互斥）"""
        self._visible = not self._visible
        self._panel.setVisible(self._visible)
        if self._btn_toggle:
            self._btn_toggle.setChecked(self._visible)
        # 互斥：打开 AI写稿时关闭 AI扩写、便签、模拟训练和插件
        if self._visible:
            self._close_other_panels()
            self._mw._update_status("AI写稿面板已打开")
        else:
            self._mw._update_status("AI写稿面板已关闭")

    def _close_other_panels(self):
        """关闭所有与 AI写稿互斥的面板"""
        mw = self._mw
        if mw._ai_expand_visible:
            mw._ai_expand_visible = False
            mw._ai_expand_panel.setVisible(False)
            mw._btn_toggle_ai_expand.setChecked(False)
        if mw._notes_visible:
            mw._notes_visible = False
            mw._notes_panel.setVisible(False)
            mw._btn_toggle_notes.setChecked(False)
        if mw._training_visible:
            mw._training_visible = False
            mw._training_panel.setVisible(False)
            mw._btn_toggle_training.setChecked(False)
        if mw._plugins_visible:
            mw._plugins_visible = False
            mw._plugin_panel.setVisible(False)
            mw._btn_toggle_plugins.setChecked(False)
        mw._close_all_plugin_registered_panels()

    def close_if_open(self):
        """如果 AI写稿面板打开则关闭（供其他面板互斥时调用）"""
        if self._visible:
            self._visible = False
            self._panel.setVisible(False)
            if self._btn_toggle:
                self._btn_toggle.setChecked(False)

    # ========== AI 写稿触发 ==========

    def generate(self, side: str):
        """触发 AI 写稿"""
        self._current_side = side
        mw = self._mw

        # 检查框架数据
        if not mw._framework_mgr.data:
            CustomDialog.warning(mw, "提示", "请先在框架画布中编辑辩论框架，再使用 AI写稿功能。")
            return

        # 检查 API 配置
        api_config = mw._load_api_config()
        if not api_config.get("api_key"):
            CustomDialog.warning(
                mw, "缺少 API Key",
                "请在 api_config.json 中填写您的 DeepSeek API Key 后再使用 AI写稿功能。"
            )
            return

        # 格式化框架数据为文本
        framework_text = mw._format_framework_for_ai()

        # 获取辩论标题
        debate_title = ""
        if mw.current_debate_data:
            pro = mw.current_debate_data.get("pro", "")
            con = mw.current_debate_data.get("con", "")
            debate_title = "{} vs {}".format(pro, con)

        side_label = "正方" if side == "pro" else "反方"

        # 确认弹窗
        result = CustomDialog.question(
            mw, "确认 AI 写稿",
            "将为【{}】基于当前框架稿生成 5 个一辩稿版本。\n\n"
            "框架内容预览：\n{}\n\n"
            "是否开始？".format(side_label, framework_text[:300]),
            buttons=[("否", "no"), ("是", "yes")])
        if result != "yes":
            return

        # 显示加载条
        mw._ai_loading_bar.show_loading("AI正在撰写一辩稿…")

        # 启动异步线程
        self._worker = AISpeechWriterWorker(
            api_config, framework_text, side, debate_title
        )
        self._worker.finished.connect(self._on_generate_finished)
        self._worker.start()
        mw._update_status("AI写稿进行中: {}…".format(side_label))

    def _on_generate_finished(self, success: bool, error_msg: str, result_text: str):
        """AI写稿完成回调"""
        mw = self._mw
        mw._ai_loading_bar.hide_loading()

        if not success:
            self._result_label.setText("写稿失败: {}".format(error_msg))
            mw._update_status("AI写稿失败: {}".format(error_msg))
            CustomDialog.warning(mw, "AI写稿失败", error_msg)
            return

        # 解析 JSON 结果
        try:
            json_text = result_text.strip()
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0].strip()
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0].strip()

            data, parse_err = mw._robust_json_parse(json_text)

            if data is None:
                raise ValueError(parse_err or "无法解析 AI 返回的 JSON 格式")

            drafts = data.get("drafts", [])
            if not drafts:
                raise ValueError("AI返回的稿本列表为空")

            self._drafts = drafts
            self._build_cards(drafts)

            self._result_label.setText(
                "✅ 共生成 {} 个一辩稿版本".format(len(drafts))
            )
            mw._update_status("AI写稿完成，共生成 {} 个版本".format(len(drafts)))
        except (_json.JSONDecodeError, ValueError, KeyError) as e:
            self._result_label.setText("❌ 解析结果失败: {}".format(str(e)))
            mw._update_status("解析AI写稿结果失败")
            raw_preview = result_text[:500] + ("…" if len(result_text) > 500 else "")
            CustomDialog.warning(
                mw, "JSON解析失败",
                "AI返回的内容无法解析为JSON。\n错误：{}\n\n"
                "返回内容预览（前500字）：\n{}".format(e, raw_preview)
            )

    # ========== 结果卡片构建 ==========

    def _clear_cards(self):
        """清空稿本结果卡片"""
        grid = self._cards_grid
        while grid.count():
            item = grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._mw._clean_layout_recursive(item.layout())
        self._cards = []

    def _build_cards(self, drafts: list):
        """构建稿本结果卡片"""
        self._clear_cards()
        self._expanded_index = -1
        cards = []

        for i, draft in enumerate(drafts):
            card = self._create_card(draft, i)
            cards.append(card)
            self._cards_grid.addWidget(card, i, 0)

        self._cards = cards

        # 显示卡片区域，隐藏空提示
        self._cards_scroll.setVisible(True)
        self._empty_hint.setVisible(False)

        # 首次按面板宽度排布
        self._relayout_grid()

    def _relayout_grid(self):
        """重新排布卡片网格：展开的卡片独占整行，其余保持1或2列（按面板宽度自适应）"""
        grid = self._cards_grid
        cards = self._cards
        if not cards:
            return
        exp_i = self._expanded_index

        # 根据面板宽度动态计算列数：<660px 单列，>=660px 双列
        panel_w = self._cards_scroll.viewport().width() if self._cards_scroll else 600
        COL_COUNT = 2 if panel_w >= 660 else 1

        # 从网格中移除所有控件（不删除）
        for _ in range(grid.count()):
            grid.takeAt(0)

        if exp_i < 0:
            # 无展开：按 COL_COUNT 列排布
            for i, card in enumerate(cards):
                grid.addWidget(card, i // COL_COUNT, i % COL_COUNT)
        else:
            # 展开卡片独占第一行（跨满所有列）
            grid.addWidget(cards[exp_i], 0, 0, 1, COL_COUNT)

            # 其余卡片从第1行开始按 COL_COUNT 列排布
            remaining = [c for i, c in enumerate(cards) if i != exp_i]
            for j, card in enumerate(remaining):
                grid.addWidget(card, j // COL_COUNT + 1, j % COL_COUNT)

    def _expand_card(self, idx: int, lbl_text: QLabel, full_text: str, btn_expand: QPushButton):
        """展开指定卡片：先收起其他已展开的卡片"""
        old = self._expanded_index
        if old >= 0 and old != idx:
            self._collapse_old_card(old)
        self._expanded_index = idx
        lbl_text.setText(full_text)
        lbl_text.setMaximumHeight(16777215)
        btn_expand.setText("▲ 收起")
        self._relayout_grid()

    def _collapse_card(self, idx: int, lbl_text: QLabel, preview_text: str, btn_expand: QPushButton):
        """收起指定卡片"""
        self._expanded_index = -1
        lbl_text.setText(preview_text)
        lbl_text.setMaximumHeight(120)
        btn_expand.setText("▼ 展开全文")
        self._relayout_grid()

    def _collapse_old_card(self, idx: int):
        """收起旧展开卡片（通过存储的属性直接操作控件）"""
        if idx < 0 or idx >= len(self._cards):
            return
        card = self._cards[idx]
        lbl = getattr(card, '_sw_lbl_text', None)
        prev = getattr(card, '_sw_preview_text', None)
        btn = getattr(card, '_sw_btn_expand', None)
        if lbl and prev:
            lbl.setText(prev)
            lbl.setMaximumHeight(120)
        if btn:
            btn.setText("▼ 展开全文")

    def _create_card(self, draft: dict, card_index: int = 0) -> QFrame:
        """创建单个稿本结果卡片"""
        draft_id = draft.get("id", "?")
        title = draft.get("title", "")
        summary = draft.get("summary", "")
        text = draft.get("text", "")
        highlights = draft.get("highlights", [])

        card = QFrame()
        card.setObjectName("aiExpandResultCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # 顶部行：编号 + 标题
        top_row = QHBoxLayout()
        top_row.setSpacing(4)

        title_text = "稿本 #{}".format(draft_id)
        if title:
            title_text += " · {}".format(title)
        lbl_title = QLabel(title_text)
        lbl_title.setObjectName("swCardTitle")
        lbl_title.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        lbl_title.setWordWrap(True)

        top_row.addWidget(lbl_title)
        top_row.addStretch()

        # 复制按钮
        btn_copy = QPushButton("")
        btn_copy.setObjectName("smallBtn")
        btn_copy.setFixedSize(32, 32)
        btn_copy.setToolTip("复制到剪切板")
        btn_copy.setCursor(Qt.PointingHandCursor)
        btn_copy.clicked.connect(lambda checked, t=text, b=btn_copy: self._copy_text(t, b))

        top_row.addWidget(btn_copy)

        # 摘要
        lbl_summary = None
        if summary:
            lbl_summary = QLabel(summary)
            lbl_summary.setFont(QFont("Microsoft YaHei", 9))
            lbl_summary.setStyleSheet(f"color: {tc("subtext")}; font-style: italic;")
            lbl_summary.setWordWrap(True)

        # 分隔线
        sep = QFrame()
        sep.setObjectName("swCardSep")
        sep.setFrameShape(QFrame.HLine)

        # 文本内容（折叠显示前200字）
        preview_text = text[:200] + ("…" if len(text) > 200 else "")
        lbl_text = QLabel(preview_text)
        lbl_text.setObjectName("swCardText")
        lbl_text.setFont(QFont("Microsoft YaHei", 10))
        lbl_text.setWordWrap(True)
        lbl_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl_text.setMinimumHeight(60)
        lbl_text.setMaximumHeight(120)

        # "展开/收起" 按钮
        btn_expand = QPushButton("▼ 展开全文")
        btn_expand.setObjectName("smallBtn")
        btn_expand.setCursor(Qt.PointingHandCursor)
        btn_expand.setFixedHeight(24)

        def toggle_expand():
            if self._expanded_index == card_index:
                self._collapse_card(card_index, lbl_text, preview_text, btn_expand)
            else:
                self._expand_card(card_index, lbl_text, text, btn_expand)

        btn_expand.clicked.connect(toggle_expand)

        # 亮点标签
        highlight_widget = None
        if highlights:
            FlowLayout = SpeechWriterManager._FlowLayout
            hl_layout = FlowLayout()
            hl_layout.setContentsMargins(0, 0, 0, 0)
            hl_layout.setSpacing(4)
            lbl_hl_title = QLabel("💡")
            lbl_hl_title.setFont(QFont("Microsoft YaHei", 9))
            lbl_hl_title.setStyleSheet(f"color: {tc("accent_yellow")};")
            lbl_hl_title.setFixedSize(18, 18)
            hl_layout.addWidget(lbl_hl_title)

            tag_font = QFont("Microsoft YaHei", 8)
            for h in highlights:
                hl_tag = QLabel(h)
                hl_tag.setObjectName("swHLTag")
                hl_tag.setFont(tag_font)
                hl_tag.setWordWrap(True)
                hl_tag.setMaximumWidth(180)
                hl_layout.addWidget(hl_tag)
            highlight_widget = QWidget()
            highlight_widget.setLayout(hl_layout)

        # 底部按钮（单个「导入」按钮，自动写入当前稿本对应的立场）
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)

        side_of_card = getattr(self, "_current_side", "pro")
        btn_import = StarButton("导入", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_import.setFixedHeight(28)
        btn_import._text_label.setStyleSheet("font-size: 11px; background: transparent; border: none;")

        # 捕获当前 side 到闭包
        _card_side = side_of_card
        btn_import.clicked.connect(lambda checked, t=text, s=_card_side: self._mw._import_speech_writer_text(t, s))

        bottom_row.addWidget(btn_import)
        bottom_row.addStretch()

        # 组装
        layout.addLayout(top_row)
        if lbl_summary:
            layout.addWidget(lbl_summary)
        layout.addWidget(sep)
        layout.addWidget(lbl_text)
        layout.addWidget(btn_expand)
        if highlight_widget:
            layout.addWidget(highlight_widget)
        layout.addLayout(bottom_row)

        # 存储内部控件引用，方便跨卡片收起时操作 UI
        card._sw_lbl_text = lbl_text
        card._sw_preview_text = preview_text
        card._sw_full_text = text
        card._sw_btn_expand = btn_expand

        return card

    # ========== 复制功能 ==========

    def _copy_text(self, text: str, btn: QPushButton):
        """复制文本到剪切板"""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        btn.setText("")
        btn.setStyleSheet(f"color: {tc("accent_green")};")
        QTimer.singleShot(1500, lambda: self._reset_copy_button(btn))

    def _reset_copy_button(self, btn: QPushButton):
        """恢复复制按钮"""
        btn.setText("")
        btn.setStyleSheet("")

    # ========== 事件过滤（由主窗口 eventFilter 调用） ==========

    def handle_scroll_resize(self) -> bool:
        """处理卡片滚动区域的 resize 事件
        
        Returns:
            True 表示已处理（触发了重排定时器）
        """
        if self._cards and self._panel and self._panel.isVisible():
            if self._reflow_timer is None:
                self._reflow_timer = QTimer(self._mw)
                self._reflow_timer.setSingleShot(True)
                self._reflow_timer.timeout.connect(self._relayout_grid)
            self._reflow_timer.start(80)
            return True
        return False
