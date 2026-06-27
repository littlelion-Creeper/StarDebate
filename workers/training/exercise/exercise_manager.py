"""立论驳论管理器 — UI 构建 + 答题流程 + 历史记录"""
import json
import os
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from components.theme_colors import tc, refresh
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QScrollArea, QWidget,
    QApplication, QSplitter,
)
from components.popup_dialog import CustomDialog

from workers.training.exercise.exercise_topic_worker import DebateExerciseTopicWorker
from workers.training.exercise.exercise_opponent_worker import DebateExerciseOpponentWorker
from workers.training.exercise.exercise_eval_worker import DebateExerciseEvalWorker


class ExerciseManager:
    """立论驳论管理器：UI 构建 + 答题流程 + 历史记录"""

    def __init__(self, train_mgr):
        """train_mgr: TrainingManager 实例"""
        self._tm = train_mgr
        self._mw = train_mgr._mw

        # ---- 数据 ----
        self._ex_active: bool = False
        self._ex_phase: str = ""
        self._ex_topic_data: dict = {}
        self._ex_position_speech: str = ""
        self._ex_ai_speech: str = ""
        self._ex_rebuttal_speech: str = ""
        self._ex_eval_data: dict = {}
        self._ex_timer = None
        self._ex_remaining_seconds: int = 0
        self._ex_opponent_ready: bool = False
        self._ex_position_submitted: bool = False
        self._ex_opponent_pending_speech: str = ""
        self._ex_topic_worker = None
        self._ex_opponent_worker = None
        self._ex_eval_worker = None
        self._ex_sessions: list = []
        self._current_history_session: dict = {}

    # ==================== UI 构建 ====================

    def build_pages(self, parent_stack: QStackedWidget) -> int:
        """构建立论驳论的所有子页面，返回起始页索引"""
        self._stack = parent_stack
        start_idx = parent_stack.count()

        self._build_exercise_rules_page()
        self._build_exercise_position_page()
        self._build_exercise_rebuttal_page()
        self._build_exercise_result_page()
        self._build_exercise_history_page()

        return start_idx

    def _build_exercise_rules_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        btn_back = QPushButton("← 返回训练首页")
        btn_back.setObjectName("smallBtn")
        btn_back.setCursor(Qt.PointingHandCursor)
        btn_back.setFixedSize(180, 28)
        btn_back.clicked.connect(lambda: self._tm._train_stack.setCurrentIndex(0))
        layout.addWidget(btn_back)

        lbl_title = QLabel("立论与驳论 — 规则说明")
        lbl_title.setObjectName("exRulesTitle")
        lbl_title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        layout.addWidget(lbl_title)

        rules_scroll = QScrollArea()
        rules_scroll.setObjectName("exRulesScroll")
        rules_scroll.setWidgetResizable(True)
        rules_content_w = QWidget()
        rules_content_w.setObjectName("exRulesContent")
        rules_content_layout = QVBoxLayout(rules_content_w)
        rules_content_layout.setContentsMargins(0, 0, 0, 0)
        rules_content_layout.setSpacing(8)

        rule_items = [
            ("①", "AI随机出题", "AI将随机生成一个有深度的辩题，并为你指定<b>正方</b>或<b>反方</b>立场"),
            ("②", "第一阶段：立论（30分钟）",
             "你需要在中央编辑器中撰写一辩立论稿，可以提前提交<br>"
             "<span style='color:#a6adc8;'>要求：字数不少于800字，包含定义、标准、论点、论据</span>"),
            ("③", "AI生成对手稿",
             "提交立论稿后，AI将自动生成一篇与你立场<b>相反</b>的一辩稿，展示在右侧功能区"),
            ("④", "第二阶段：驳论（15分钟）",
             "你需要对AI生成的一辩稿进行驳论，可以提前提交<br>"
             "<span style='color:#a6adc8;'>要求：逐点反驳核心论点，指出逻辑漏洞</span>"),
            ("⑤", "AI综合评分",
             "完成立论与驳论后，AI将从论点清晰度、逻辑严密性、论据充分度、表达文采等维度<b>综合评定分数</b>"),
        ]

        for num, title, desc in rule_items:
            rule_card = QFrame()
            rule_card.setObjectName("exerciseScoreBlock")
            card_layout = QHBoxLayout(rule_card)
            card_layout.setContentsMargins(10, 10, 10, 10)
            card_layout.setSpacing(12)

            lbl_num = QLabel(num)
            lbl_num.setObjectName("exNumLabel")
            lbl_num.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
            lbl_num.setFixedWidth(36)
            lbl_num.setAlignment(Qt.AlignTop | Qt.AlignCenter)
            card_layout.addWidget(lbl_num, alignment=Qt.AlignTop)

            text_widget = QWidget()
            text_widget.setObjectName("exCardContainer")
            text_layout = QVBoxLayout(text_widget)
            text_layout.setContentsMargins(0, 2, 0, 0)
            text_layout.setSpacing(4)

            lbl_title_card = QLabel(title)
            lbl_title_card.setObjectName("exCardTitle")
            lbl_title_card.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
            lbl_title_card.setWordWrap(True)
            text_layout.addWidget(lbl_title_card)

            lbl_desc = QLabel(desc)
            lbl_desc.setObjectName("exCardDesc")
            lbl_desc.setFont(QFont("Microsoft YaHei", 9))
            lbl_desc.setWordWrap(True)
            lbl_desc.setTextFormat(Qt.RichText)
            text_layout.addWidget(lbl_desc)

            card_layout.addWidget(text_widget, stretch=1)
            rules_content_layout.addWidget(rule_card)

        rule_sep = QFrame()
        rule_sep.setObjectName("exScoreHLine")
        rule_sep.setFrameShape(QFrame.HLine)
        rules_content_layout.addWidget(rule_sep)

        lbl_extra = QLabel(
            "<span style='color:#f9e2af;'>💡 提示：</span>"
            "<span style='color:#a6adc8;'>建议先在记事本中打好草稿，再粘贴到编辑器中。时间到后系统将自动提交。</span>"
        )
        lbl_extra.setObjectName("exExtraLabel")
        lbl_extra.setFont(QFont("Microsoft YaHei", 9))
        lbl_extra.setWordWrap(True)
        lbl_extra.setTextFormat(Qt.RichText)
        rules_content_layout.addWidget(lbl_extra)

        rules_content_layout.addStretch()
        rules_scroll.setWidget(rules_content_w)
        layout.addWidget(rules_scroll, stretch=1)

        btn_start = QPushButton("▶ 开始答题")
        btn_start.setObjectName("primaryBtn")
        btn_start.setCursor(Qt.PointingHandCursor)
        btn_start.setFixedHeight(36)
        btn_start.clicked.connect(self._on_exercise_start)
        layout.addWidget(btn_start)

        self._stack.addWidget(page)  # rules page

    def _build_exercise_position_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        mw = self._mw
        self._ex_pos_top_row = QHBoxLayout()
        self._btn_ex_pos_abandon = QPushButton("← 放弃本轮")
        self._btn_ex_pos_abandon.setObjectName("smallBtn")
        self._btn_ex_pos_abandon.setCursor(Qt.PointingHandCursor)
        self._tm._auto_size_button(self._btn_ex_pos_abandon, "← 放弃本轮", 28)
        self._btn_ex_pos_abandon.clicked.connect(self._on_exercise_abandon)
        self._ex_pos_top_row.addWidget(self._btn_ex_pos_abandon)
        self._ex_pos_top_row.addStretch()
        layout.addLayout(self._ex_pos_top_row)

        self._lbl_ex_topic = QLabel("")
        self._lbl_ex_topic.setObjectName("exPositionTopic")
        self._lbl_ex_topic.setFont(QFont("Microsoft YaHei", 11))
        self._lbl_ex_topic.setWordWrap(True)
        layout.addWidget(self._lbl_ex_topic)

        self._lbl_ex_stance = QLabel("")
        self._lbl_ex_stance.setObjectName("exPositionStance")
        self._lbl_ex_stance.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        self._lbl_ex_stance.setWordWrap(True)
        layout.addWidget(self._lbl_ex_stance)

        self._ex_timer_frame = QFrame()
        self._ex_timer_frame.setObjectName("exerciseTimerFrame")
        timer_frame_layout = QVBoxLayout(self._ex_timer_frame)
        timer_frame_layout.setContentsMargins(12, 16, 12, 16)
        timer_frame_layout.setSpacing(4)
        self._lbl_ex_timer_icon = QLabel("⏱")
        self._lbl_ex_timer_icon.setObjectName("exTimerIcon")
        self._lbl_ex_timer_icon.setFont(QFont("Microsoft YaHei", 14))
        self._lbl_ex_timer_icon.setAlignment(Qt.AlignCenter)
        timer_frame_layout.addWidget(self._lbl_ex_timer_icon)
        self._lbl_ex_timer = QLabel("30:00")
        self._lbl_ex_timer.setObjectName("exTimerDisplay")
        self._lbl_ex_timer.setFont(QFont("Consolas", 28, QFont.Bold))
        self._lbl_ex_timer.setAlignment(Qt.AlignCenter)
        timer_frame_layout.addWidget(self._lbl_ex_timer)
        self._lbl_ex_timer_hint = QLabel("剩余时间")
        self._lbl_ex_timer_hint.setObjectName("exTimerHint")
        self._lbl_ex_timer_hint.setFont(QFont("Microsoft YaHei", 9))
        self._lbl_ex_timer_hint.setAlignment(Qt.AlignCenter)
        timer_frame_layout.addWidget(self._lbl_ex_timer_hint)
        layout.addWidget(self._ex_timer_frame)

        self._ex_hints_frame = QFrame()
        self._ex_hints_frame.setObjectName("exerciseHintsFrame")
        hints_layout = QVBoxLayout(self._ex_hints_frame)
        hints_layout.setContentsMargins(8, 8, 8, 8)
        hints_layout.setSpacing(4)
        self._lbl_ex_hints = QLabel("")
        self._lbl_ex_hints.setObjectName("exHintsText")
        self._lbl_ex_hints.setFont(QFont("Microsoft YaHei", 9))
        self._lbl_ex_hints.setWordWrap(True)
        hints_layout.addWidget(self._lbl_ex_hints)
        layout.addWidget(self._ex_hints_frame)

        self._lbl_ex_word_count = QLabel("字数: 0")
        self._lbl_ex_word_count.setObjectName("exWordCount")
        self._lbl_ex_word_count.setFont(QFont("Microsoft YaHei", 10))
        layout.addWidget(self._lbl_ex_word_count)

        layout.addStretch()

        self._btn_ex_submit = QPushButton("交立论稿")
        self._btn_ex_submit.setObjectName("primaryBtn")
        self._btn_ex_submit.setCursor(Qt.PointingHandCursor)
        self._btn_ex_submit.setFixedHeight(36)
        self._btn_ex_submit.clicked.connect(self._on_exercise_submit_position)
        layout.addWidget(self._btn_ex_submit)

        self._stack.addWidget(page)  # position page

    def _build_exercise_rebuttal_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self._btn_ex_reb_abandon = QPushButton("← 放弃本轮")
        self._btn_ex_reb_abandon.setObjectName("smallBtn")
        self._btn_ex_reb_abandon.setCursor(Qt.PointingHandCursor)
        self._tm._auto_size_button(self._btn_ex_reb_abandon, "← 放弃本轮", 28)
        self._btn_ex_reb_abandon.clicked.connect(self._on_exercise_abandon)
        layout.addWidget(self._btn_ex_reb_abandon)

        lbl_info = QLabel("AI已生成对立立场一辩稿\n→ 请在右侧中间的面板查看")
        lbl_info.setObjectName("exRebuttalInfo")
        lbl_info.setFont(QFont("Microsoft YaHei", 10))
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)

        self._ex_reb_timer_frame = QFrame()
        self._ex_reb_timer_frame.setObjectName("exerciseTimerFrame")
        reb_timer_layout = QVBoxLayout(self._ex_reb_timer_frame)
        reb_timer_layout.setContentsMargins(12, 16, 12, 16)
        reb_timer_layout.setSpacing(4)
        self._lbl_ex_reb_timer_icon = QLabel("⏱")
        self._lbl_ex_reb_timer_icon.setObjectName("exTimerIcon")
        self._lbl_ex_reb_timer_icon.setFont(QFont("Microsoft YaHei", 14))
        self._lbl_ex_reb_timer_icon.setAlignment(Qt.AlignCenter)
        reb_timer_layout.addWidget(self._lbl_ex_reb_timer_icon)
        self._lbl_ex_reb_timer = QLabel("15:00")
        self._lbl_ex_reb_timer.setObjectName("exTimerDisplay")
        self._lbl_ex_reb_timer.setFont(QFont("Consolas", 28, QFont.Bold))
        self._lbl_ex_reb_timer.setAlignment(Qt.AlignCenter)
        reb_timer_layout.addWidget(self._lbl_ex_reb_timer)
        self._lbl_ex_reb_timer_hint = QLabel("剩余时间")
        self._lbl_ex_reb_timer_hint.setObjectName("exTimerHint")
        self._lbl_ex_reb_timer_hint.setFont(QFont("Microsoft YaHei", 9))
        self._lbl_ex_reb_timer_hint.setAlignment(Qt.AlignCenter)
        reb_timer_layout.addWidget(self._lbl_ex_reb_timer_hint)
        layout.addWidget(self._ex_reb_timer_frame)

        lbl_hints = QLabel("驳论要求：逐点反驳AI稿核心论点 · 指出逻辑漏洞 · 字数不少于500字")
        lbl_hints.setObjectName("exRebuttalHint")
        lbl_hints.setFont(QFont("Microsoft YaHei", 9))
        lbl_hints.setWordWrap(True)
        layout.addWidget(lbl_hints)

        self._lbl_ex_reb_word_count = QLabel("驳论字数: 0")
        self._lbl_ex_reb_word_count.setObjectName("exRebWordCount")
        self._lbl_ex_reb_word_count.setFont(QFont("Microsoft YaHei", 10))
        layout.addWidget(self._lbl_ex_reb_word_count)

        layout.addStretch()

        self._btn_ex_reb_submit = QPushButton("提交驳论稿")
        self._btn_ex_reb_submit.setObjectName("primaryBtn")
        self._btn_ex_reb_submit.setCursor(Qt.PointingHandCursor)
        self._btn_ex_reb_submit.setFixedHeight(36)
        self._btn_ex_reb_submit.clicked.connect(self._on_exercise_submit_rebuttal)
        layout.addWidget(self._btn_ex_reb_submit)

        self._stack.addWidget(page)  # rebuttal page

    def _build_exercise_result_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        btn_back = QPushButton("← 返回训练首页")
        btn_back.setObjectName("smallBtn")
        btn_back.setCursor(Qt.PointingHandCursor)
        btn_back.setFixedSize(120, 28)
        btn_back.clicked.connect(self._on_exercise_back_to_entry)
        layout.addWidget(btn_back)

        self._lbl_ex_result_title = QLabel("评分结果")
        self._lbl_ex_result_title.setObjectName("exResultTitle")
        self._lbl_ex_result_title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        layout.addWidget(self._lbl_ex_result_title)

        self._ex_result_scroll = QScrollArea()
        self._ex_result_scroll.setObjectName("exResultScroll")
        self._ex_result_scroll.setWidgetResizable(True)
        self._ex_result_content = QWidget()
        self._ex_result_content.setObjectName("exResultContent")
        self._ex_result_layout = QVBoxLayout(self._ex_result_content)
        self._ex_result_layout.setSpacing(6)
        self._ex_result_scroll.setWidget(self._ex_result_content)
        layout.addWidget(self._ex_result_scroll, stretch=1)

        res_btn_row = QHBoxLayout()
        res_btn_row.setSpacing(8)
        btn_save = QPushButton("保存记录")
        btn_save.setObjectName("smallBtn")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.setFixedHeight(32)
        btn_save.clicked.connect(self._on_exercise_save_session)
        res_btn_row.addWidget(btn_save)
        btn_again = QPushButton("再来一次")
        btn_again.setObjectName("primaryBtn")
        btn_again.setCursor(Qt.PointingHandCursor)
        btn_again.setFixedHeight(32)
        btn_again.clicked.connect(self._on_exercise_restart)
        res_btn_row.addWidget(btn_again)
        layout.addLayout(res_btn_row)

        self._stack.addWidget(page)  # result page

    def _build_exercise_history_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        lbl_title = QLabel("立论驳论记录")
        lbl_title.setObjectName("exHistoryTitle")
        lbl_title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        layout.addWidget(lbl_title)

        self._ex_hist_scroll = QScrollArea()
        self._ex_hist_scroll.setObjectName("exHistoryScroll")
        self._ex_hist_scroll.setWidgetResizable(True)
        self._ex_hist_container = QWidget()
        self._ex_hist_container.setObjectName("exHistoryContainer")
        self._ex_hist_layout = QVBoxLayout(self._ex_hist_container)
        self._ex_hist_layout.setSpacing(4)
        self._ex_hist_layout.addStretch()
        self._ex_hist_scroll.setWidget(self._ex_hist_container)
        layout.addWidget(self._ex_hist_scroll)

        btn_back = QPushButton("← 返回训练首页")
        btn_back.setCursor(Qt.PointingHandCursor)
        btn_back.setFixedHeight(32)
        btn_back.clicked.connect(lambda: self._tm._train_stack.setCurrentIndex(0))
        layout.addWidget(btn_back)

        self._stack.addWidget(page)  # history page

    # ---- Page index properties (set after build) ----
    @property
    def rules_idx(self) -> int:
        return self._rules_idx

    @property
    def position_idx(self) -> int:
        return self._rules_idx + 1

    @property
    def rebuttal_idx(self) -> int:
        return self._rules_idx + 2

    @property
    def result_idx(self) -> int:
        return self._rules_idx + 3

    @property
    def history_idx(self) -> int:
        return self._rules_idx + 4

    # ==================== 答题流程 ====================

    def show_rules(self):
        self._tm._train_stack.setCurrentIndex(self.rules_idx)

    def _on_exercise_start(self):
        mw = self._mw
        api_config = mw._load_api_config()
        if not api_config.get("api_key"):
            ptype = api_config.get("provider_type", "auto")
            if ptype not in ("auto", "web"):
                CustomDialog.warning(mw, "缺少 API Key",
                                    "请在 api_config.json 中填写您的 DeepSeek API Key 后再使用此功能。")
                return
            # auto/web 无 key 时静默跳过，由 _resolve_provider_type 回退到 Web

        mw._ai_loading_bar.show_loading("AI生成辩题中...")
        worker = DebateExerciseTopicWorker(api_config)
        worker.finished.connect(self._on_exercise_topic_ready)
        worker.start()
        self._ex_topic_worker = worker

    def _on_exercise_topic_ready(self, success: bool, error_msg: str, topic_data: dict):
        mw = self._mw
        mw._ai_loading_bar.hide_loading()
        if not success:
            CustomDialog.warning(mw, "出题失败", f"AI出题失败: {error_msg}")
            return

        self._ex_topic_data = topic_data
        self._ex_active = True
        self._ex_phase = "position"
        self._ex_position_speech = ""
        self._ex_ai_speech = ""
        self._ex_rebuttal_speech = ""
        self._ex_eval_data = {}

        mw._ex_ai_speech_panel.setVisible(False)

        topic = topic_data.get("topic", "")
        stance = topic_data.get("assigned_stance", "")
        pro_stance = topic_data.get("pro_stance", "")
        con_stance = topic_data.get("con_stance", "")
        self._lbl_ex_topic.setText(f"辩题：{topic}")

        pro_color = "#a6e3a1"
        con_color = "#f38ba8"
        stance_parts = []
        if pro_stance:
            stance_parts.append(f'<span style="color:{pro_color}; font-weight:bold;">正方</span>'
                                f'<span style="color:#cdd6f4;">：{pro_stance}</span>')
        if con_stance:
            stance_parts.append(f'<span style="color:{con_color}; font-weight:bold;">反方</span>'
                                f'<span style="color:#cdd6f4;">：{con_stance}</span>')
        stance_info = "<br>".join(stance_parts) if stance_parts else f"🎯 你的立场：{stance}"
        your_mark = f'<span style="color:#f9e2af; font-weight:bold;">🎯 你的立场：{stance}</span>'
        self._lbl_ex_stance.setText(f"{stance_info}<br>{your_mark}")
        self._lbl_ex_stance.setStyleSheet(f"color: {tc("text")}; padding: 4px 0; line-height: 1.8;")
        self._lbl_ex_stance.setTextFormat(Qt.RichText)

        hints = topic_data.get("writing_hints", [])
        hints_text = "💡 写作提示：\n• 字数不少于800字\n• 需包含定义、标准、论点、论据"
        if hints:
            hints_text += "\n" + "\n".join(f"• {h}" for h in hints[:3])
        self._lbl_ex_hints.setText(hints_text)

        mw._exercise_editor.setPlainText("")
        mw._lbl_ex_edit_title.setText("立论稿编辑")
        self._btn_ex_submit.setText("提交立论稿")
        self._lbl_ex_word_count.setText("字数: 0")
        self._btn_ex_submit.setStyleSheet("")

        self._tm._train_stack.setCurrentIndex(self.position_idx)
        mw.centre_stack.setCurrentIndex(9)

        self._ex_opponent_ready = False
        self._ex_position_submitted = False
        self._ex_opponent_pending_speech = ""

        api_config = mw._load_api_config()
        worker = DebateExerciseOpponentWorker(api_config, topic, stance, "")
        worker.finished.connect(self._on_opponent_speech_ready)
        worker.start()
        self._ex_opponent_worker = worker
        mw._update_status(f"立论与驳论开始！辩题: {topic[:30]}...  立场: {stance}  |  AI正在后台生成对手稿...")

        self._start_exercise_timer(30 * 60)

    def _start_exercise_timer(self, total_seconds: int):
        self._ex_remaining_seconds = total_seconds
        self._update_exercise_timer_display()
        if self._ex_timer:
            self._ex_timer.stop()
        self._ex_timer = QTimer(self._mw)
        self._ex_timer.timeout.connect(self._on_exercise_timer_tick)
        self._ex_timer.start(1000)

    def _stop_exercise_timer(self):
        if self._ex_timer:
            self._ex_timer.stop()
            self._ex_timer = None

    def _on_exercise_timer_tick(self):
        self._ex_remaining_seconds -= 1
        self._update_exercise_timer_display()
        if self._ex_remaining_seconds <= 0:
            self._stop_exercise_timer()
            if self._ex_phase == "position":
                self._on_exercise_submit_position()
            elif self._ex_phase == "rebuttal":
                self._on_exercise_submit_rebuttal()

    def _update_exercise_timer_display(self):
        m, s = divmod(max(0, self._ex_remaining_seconds), 60)
        time_str = f"{m:02d}:{s:02d}"

        if self._ex_phase == "position":
            timer_label = self._lbl_ex_timer
            icon_label = self._lbl_ex_timer_icon
            hint_label = self._lbl_ex_timer_hint
        else:
            timer_label = self._lbl_ex_reb_timer
            icon_label = self._lbl_ex_reb_timer_icon
            hint_label = self._lbl_ex_reb_timer_hint

        timer_label.setText(time_str)

        remaining = self._ex_remaining_seconds
        if remaining <= 180:
            color = "#f38ba8"
            icon = "🔴"
            hint = "请尽快提交！"
        elif remaining <= 600:
            color = "#f9e2af"
            icon = "⚠"
            hint = "时间不多了！"
        else:
            color = "#89b4fa"
            icon = "⏱"
            hint = "剩余时间"

        timer_label.setStyleSheet(f"color: {color}; background: transparent;")
        icon_label.setText(icon)
        icon_label.setStyleSheet(f"color: {color}; background: transparent;")
        hint_label.setText(hint)
        hint_label.setStyleSheet(f"color: {color}; background: transparent;")

    def on_exercise_editor_changed(self):
        """编辑器内容变化，更新字数统计"""
        mw = self._mw
        text = mw._exercise_editor.toPlainText()
        word_count = len(text.replace("\n", "").replace(" ", ""))
        if self._ex_phase == "position":
            self._lbl_ex_word_count.setText(f"字数: {word_count}")
            if word_count < 800:
                self._lbl_ex_word_count.setStyleSheet(f"color: {tc("accent_red")}; padding: 4px 0;")
            else:
                self._lbl_ex_word_count.setStyleSheet(f"color: {tc("accent_green")}; padding: 4px 0;")
        elif self._ex_phase == "rebuttal":
            self._lbl_ex_reb_word_count.setText(f"驳论字数: {word_count}")
            if word_count < 500:
                self._lbl_ex_reb_word_count.setStyleSheet(f"color: {tc("accent_red")}; padding: 4px 0;")
            else:
                self._lbl_ex_reb_word_count.setStyleSheet(f"color: {tc("accent_green")}; padding: 4px 0;")
        block_count = mw._exercise_editor.blockCount()
        mw._lbl_ex_editor_status.setText(f"字数: {word_count}  |  行: {block_count}")

    def _on_exercise_submit_position(self):
        mw = self._mw
        text = mw._exercise_editor.toPlainText().strip()
        word_count = len(text.replace("\n", "").replace(" ", ""))
        if word_count < 800:
            result = CustomDialog.question(
                mw, "字数不足",
                f"当前字数为 {word_count} 字，建议不少于800字。\n确定要提交吗？",
                buttons=[("否", "no"), ("是", "yes")])
            if result != "yes":
                return

        self._stop_exercise_timer()
        self._ex_position_speech = text
        self._ex_position_submitted = True

        if self._ex_opponent_ready:
            self._transition_to_rebuttal(self._ex_opponent_pending_speech)
        else:
            mw._ai_loading_bar.show_loading("等待AI对手稿生成完成...")
            mw._update_status("立论稿已提交，等待后台AI对手稿生成完成...")

    def _on_opponent_speech_ready(self, success: bool, error_msg: str, speech_text: str):
        mw = self._mw
        mw._ai_loading_bar.hide_loading()
        if not self._ex_active:
            return
        if not success:
            CustomDialog.warning(mw, "生成失败", f"AI对手稿生成失败: {error_msg}")
            self._on_exercise_abandon()
            return

        self._ex_opponent_pending_speech = speech_text
        self._ex_opponent_ready = True

        if self._ex_position_submitted:
            self._transition_to_rebuttal(speech_text)
        else:
            mw._update_status("AI对手稿已在后台生成完毕，请完成立论稿后提交")

    def _transition_to_rebuttal(self, speech_text: str):
        mw = self._mw
        mw._ai_loading_bar.hide_loading()
        self._ex_ai_speech = speech_text
        self._ex_phase = "rebuttal"

        mw._ex_ai_speech_editor.setPlainText(speech_text)
        mw._ex_ai_speech_panel.setVisible(True)

        opponent_stance = "反方" if self._ex_topic_data.get("assigned_stance", "") == "正方" else "正方"
        mw._lbl_ex_ai_title.setText(f"📄 {opponent_stance}一辩稿")

        mw._exercise_editor.setPlainText("")
        mw._lbl_ex_edit_title.setText("驳论稿编辑")
        self._btn_ex_reb_submit.setStyleSheet("")

        self._tm._train_stack.setCurrentIndex(self.rebuttal_idx)
        mw.centre_stack.setCurrentIndex(9)

        self._start_exercise_timer(15 * 60)
        self._adjust_exercise_splitter()
        mw._update_status(f"驳论阶段开始！请阅读{opponent_stance}一辩稿后在中央编辑器进行驳论")

    def _adjust_exercise_splitter(self):
        mw = self._mw
        splitter = mw.findChild(QSplitter)
        if not splitter:
            return
        total_w = splitter.width()
        avail = total_w - splitter.widget(0).width() - splitter.handleWidth() * 6
        center_w = int(avail * 0.35)
        side_each = int(avail * 0.12)
        splitter.setSizes([splitter.widget(0).width(), side_each, center_w, 0, 0, 0, side_each])

    def _on_exercise_submit_rebuttal(self):
        mw = self._mw
        text = mw._exercise_editor.toPlainText().strip()
        word_count = len(text.replace("\n", "").replace(" ", ""))
        if word_count < 500:
            result = CustomDialog.question(
                mw, "字数不足",
                f"当前驳论字数为 {word_count} 字，建议不少于500字。\n确定要提交吗？",
                buttons=[("否", "no"), ("是", "yes")])
            if result != "yes":
                return

        self._stop_exercise_timer()
        self._ex_rebuttal_speech = text
        mw._update_status("驳论稿已提交，正在AI评分...")

        mw._ai_loading_bar.show_loading("AI评分中...")
        api_config = mw._load_api_config()
        topic = self._ex_topic_data.get("topic", "")
        stance = self._ex_topic_data.get("assigned_stance", "")

        worker = DebateExerciseEvalWorker(
            api_config, topic, stance,
            self._ex_position_speech, self._ex_ai_speech, self._ex_rebuttal_speech)
        worker.finished.connect(self._on_exercise_eval_ready)
        worker.start()
        self._ex_eval_worker = worker

        mw._ex_ai_speech_panel.setVisible(False)

        self._tm._train_stack.setCurrentIndex(self.result_idx)
        self._on_exercise_save_session()

    def _on_exercise_eval_ready(self, success: bool, error_msg: str, eval_data: dict):
        self._mw._ai_loading_bar.hide_loading()
        if success:
            self._ex_eval_data = eval_data
        else:
            self._ex_eval_data = {"error": error_msg}
        self._render_exercise_result()

    def _render_exercise_result(self):
        while self._ex_result_layout.count():
            item = self._ex_result_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        eval_data = self._ex_eval_data
        if not eval_data or "error" in eval_data:
            lbl_err = QLabel(f"评分生成失败: {eval_data.get('error', '未知错误')}")
            lbl_err.setFont(QFont("Microsoft YaHei", 10))
            lbl_err.setStyleSheet(f"color: {tc("accent_red")};")
            lbl_err.setWordWrap(True)
            self._ex_result_layout.addWidget(lbl_err)
            self._ex_result_layout.addStretch()
            return

        pos = eval_data.get("position_score", {})
        reb = eval_data.get("rebuttal_score", {})

        self._add_score_block("📝 立论评分", {
            "clarity": "论点清晰度", "logic": "逻辑严密性",
            "evidence": "论据充分度", "expression": "表达文采"
        }, "#a6e3a1", pos)

        self._add_score_block("🎯 驳论评分", {
            "targeting": "驳论针对性", "deconstruction": "逻辑拆解",
            "refutation": "论据反驳", "force": "表达力度"
        }, "#f38ba8", reb)

        total = eval_data.get("total_score", 0)
        total_block = QFrame()
        total_block.setObjectName("exerciseScoreBlock")
        tb_layout = QVBoxLayout(total_block)
        tb_layout.setContentsMargins(8, 8, 8, 8)
        lbl_total = QLabel(f"🏆 总分: {total}/100")
        lbl_total.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        lbl_total.setStyleSheet(f"color: {tc("accent_yellow")};")
        lbl_total.setAlignment(Qt.AlignCenter)
        tb_layout.addWidget(lbl_total)
        self._ex_result_layout.addWidget(total_block)

        e_block = QFrame()
        e_block.setObjectName("exerciseScoreBlock")
        eb_layout = QVBoxLayout(e_block)
        eb_layout.setContentsMargins(8, 8, 8, 8)
        lbl_e_title = QLabel("📋 AI综合评价")
        lbl_e_title.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        lbl_e_title.setStyleSheet(f"color: {tc("accent_blue")};")
        eb_layout.addWidget(lbl_e_title)

        summary = eval_data.get("summary", "")
        if summary:
            lbl_summary = QLabel(summary)
            lbl_summary.setFont(QFont("Microsoft YaHei", 10))
            lbl_summary.setStyleSheet(f"color: {tc("text")}; padding: 4px 0; line-height: 1.6;")
            lbl_summary.setWordWrap(True)
            eb_layout.addWidget(lbl_summary)

        strengths = eval_data.get("strengths", [])
        if strengths:
            lbl_s = QLabel("✅ 优点：" + " | ".join(strengths))
            lbl_s.setFont(QFont("Microsoft YaHei", 9))
            lbl_s.setStyleSheet(f"color: {tc("accent_green")}; padding: 2px 0;")
            lbl_s.setWordWrap(True)
            eb_layout.addWidget(lbl_s)

        weaknesses = eval_data.get("weaknesses", [])
        if weaknesses:
            lbl_w = QLabel("⚠ 不足：" + " | ".join(weaknesses))
            lbl_w.setFont(QFont("Microsoft YaHei", 9))
            lbl_w.setStyleSheet(f"color: {tc("accent_yellow")}; padding: 2px 0;")
            lbl_w.setWordWrap(True)
            eb_layout.addWidget(lbl_w)

        suggestions = eval_data.get("suggestions", [])
        if suggestions:
            lbl_sug = QLabel("💡 建议：" + " | ".join(suggestions))
            lbl_sug.setFont(QFont("Microsoft YaHei", 9))
            lbl_sug.setStyleSheet(f"color: {tc("accent_blue")}; padding: 2px 0;")
            lbl_sug.setWordWrap(True)
            eb_layout.addWidget(lbl_sug)

        self._ex_result_layout.addWidget(e_block)
        self._ex_result_layout.addStretch()

    def _add_score_block(self, title: str, scores: dict, accent: str, data: dict):
        block = QFrame()
        block.setObjectName("exerciseScoreBlock")
        b_layout = QVBoxLayout(block)
        b_layout.setContentsMargins(8, 6, 8, 6)
        b_layout.setSpacing(3)
        lbl_title = QLabel(title)
        lbl_title.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        lbl_title.setStyleSheet(f"color: {accent};")
        b_layout.addWidget(lbl_title)
        for key, label in scores.items():
            if key == "total":
                continue
            score = data.get(key, 0)
            bar_len = int(score / 25 * 10)
            bar = "█" * bar_len + "░" * (10 - bar_len)
            row = QLabel(f"  {label}  {bar}  {score}/25")
            row.setObjectName("exScoreRow")
            row.setFont(QFont("Microsoft YaHei", 9))
            b_layout.addWidget(row)
        sep = QFrame()
        sep.setObjectName("exScoreHLine")
        sep.setFrameShape(QFrame.HLine)
        b_layout.addWidget(sep)
        total_score = data.get("total", 0)
        stars = "★" * (int(total_score / 20) + 1)
        total_label = QLabel(f"  综合分  {stars}  {total_score}/100")
        total_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        total_label.setStyleSheet(f"color: {accent};")
        b_layout.addWidget(total_label)
        self._ex_result_layout.addWidget(block)

    def _on_exercise_save_session(self):
        from components.res_path import get_resource_root
        save_dir = os.path.join(get_resource_root(), "exercise_sessions")
        os.makedirs(save_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(save_dir, f"debate_exercise_{timestamp}.json")

        session_data = {
            "session_id": f"debate_exercise_{timestamp}",
            "date": datetime.now().isoformat(),
            "type": "debate_exercise",
            "topic": self._ex_topic_data.get("topic", ""),
            "topic_description": self._ex_topic_data.get("topic_description", ""),
            "topic_category": self._ex_topic_data.get("topic_category", ""),
            "user_stance": self._ex_topic_data.get("assigned_stance", ""),
            "position_speech": self._ex_position_speech,
            "ai_speech": self._ex_ai_speech,
            "rebuttal_speech": self._ex_rebuttal_speech,
            "position_score": self._ex_eval_data.get("position_score", {}),
            "rebuttal_score": self._ex_eval_data.get("rebuttal_score", {}),
            "total_score": self._ex_eval_data.get("total_score", 0),
            "ai_evaluation": self._ex_eval_data,
        }

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            self._mw._update_status(f"立论驳论记录已保存: debate_exercise_{timestamp}.json")
        except Exception as e:
            self._mw._update_status(f"保存失败: {str(e)}")

    def _on_exercise_abandon(self):
        mw = self._mw
        self._stop_exercise_timer()
        self._ex_active = False
        self._ex_phase = ""
        self._ex_opponent_ready = False
        self._ex_position_submitted = False
        self._ex_opponent_pending_speech = ""
        mw._ex_ai_speech_panel.setVisible(False)
        self._tm._train_stack.setCurrentIndex(0)
        mw._update_status("已放弃本轮立论与驳论训练")

    def _on_exercise_restart(self):
        mw = self._mw
        self._ex_active = False
        self._ex_phase = ""
        self._ex_position_speech = ""
        self._ex_ai_speech = ""
        self._ex_rebuttal_speech = ""
        self._ex_eval_data = {}
        self._ex_topic_data = {}
        self._ex_opponent_ready = False
        self._ex_position_submitted = False
        self._ex_opponent_pending_speech = ""
        mw._ex_ai_speech_panel.setVisible(False)
        mw._ex_ai_speech_editor.setPlainText("")
        mw._exercise_editor.setPlainText("")
        self._tm._train_stack.setCurrentIndex(self.rules_idx)
        self._on_exercise_start()

    def _on_exercise_back_to_entry(self):
        mw = self._mw
        self._ex_active = False
        self._ex_phase = ""
        self._ex_opponent_ready = False
        self._ex_position_submitted = False
        self._ex_opponent_pending_speech = ""
        mw._ex_ai_speech_panel.setVisible(False)
        self._stop_exercise_timer()
        self._tm._train_stack.setCurrentIndex(0)

    def on_ex_ai_speech_copy(self):
        text = self._mw._ex_ai_speech_editor.toPlainText()
        if text.strip():
            QApplication.clipboard().setText(text)
            self._mw._update_status("AI一辩稿已复制到剪贴板")

    # ==================== 历史记录 ====================

    def show_history(self):
        self._tm._train_stack.setCurrentIndex(self.history_idx)
        self._refresh_exercise_sessions()

    def _refresh_exercise_sessions(self):
        from components.res_path import get_resource_root
        save_dir = os.path.join(get_resource_root(), "exercise_sessions")
        sessions = []
        if os.path.isdir(save_dir):
            for fname in sorted(os.listdir(save_dir), reverse=True):
                if fname.endswith(".json") and fname.startswith("debate_exercise_"):
                    fpath = os.path.join(save_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        data["_filepath"] = fpath
                        sessions.append(data)
                    except Exception:
                        pass
        self._ex_sessions = sessions

        while self._ex_hist_layout.count() > 1:
            item = self._ex_hist_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not sessions:
            lbl = QLabel("暂无立论驳论记录")
            lbl.setObjectName("exEmptyLabel")
            lbl.setFont(QFont("Microsoft YaHei", 10))
            lbl.setAlignment(Qt.AlignCenter)
            self._ex_hist_layout.insertWidget(0, lbl)
            return

        for sess in sessions:
            date_str = sess.get("date", "")[:16].replace("T", " ")
            topic = sess.get("topic", "")[:40]
            stance = sess.get("user_stance", "")
            stance_icon = "🟢" if stance == "正方" else "🔴"
            pos_score = sess.get("position_score", {}).get("total", "-")
            reb_score = sess.get("rebuttal_score", {}).get("total", "-")
            total = sess.get("total_score", "-")

            btn = QPushButton(
                f"{date_str}   {stance_icon}{stance}\n"
                f"📋 {topic}\n"
                f"📝 立论:{pos_score}  🎯 驳论:{reb_score}  🏆 总分:{total}"
            )
            btn.setFont(QFont("Microsoft YaHei", 9))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(56)
            btn.setObjectName("exHistoryBtn")
            btn.clicked.connect(lambda checked, s=sess: self._on_exercise_view_session(s))
            self._ex_hist_layout.insertWidget(self._ex_hist_layout.count() - 1, btn)

    def _on_exercise_view_session(self, session: dict):
        topic = session.get("topic", "")
        stance = session.get("user_stance", "")
        stance_color = "#a6e3a1" if stance == "正方" else "#f38ba8"
        opponent_stance = "反方" if stance == "正方" else "正方"
        pos_score = session.get("position_score", {})
        reb_score = session.get("rebuttal_score", {})
        total = session.get("total_score", 0)
        evaluation = session.get("ai_evaluation", {})

        content = f"""<html><body style='font-family: Microsoft YaHei; font-size: 13px; color: #cdd6f4;'>
        <h3 style='color: #89b4fa;'>📋 辩题: {topic}</h3>
        <p style='color: {stance_color};'><b>🎯 你的立场: {stance}  |  🏆 总分: {total}/100</b></p>
        <hr style='border-color: #45475a;'>

        <h4 style='color: #a6e3a1;'>📝 你的立论稿</h4>
        <p>{session.get('position_speech', '')[:300].replace(chr(10), '<br>')}...</p>
        <p style='color: #6c7086;'>【立论评分】论点清晰度:{pos_score.get('clarity','-')}/25 
        逻辑严密性:{pos_score.get('logic','-')}/25 
        论据充分度:{pos_score.get('evidence','-')}/25 
        表达文采:{pos_score.get('expression','-')}/25 
        综合:{pos_score.get('total','-')}/100</p>
        <hr style='border-color: #45475a;'>

        <h4 style='color: #f38ba8;'>📄 {opponent_stance}AI一辩稿</h4>
        <p>{session.get('ai_speech', '')[:300].replace(chr(10), '<br>')}...</p>
        <hr style='border-color: #45475a;'>

        <h4 style='color: #f9e2af;'>⚔️ 你的驳论稿</h4>
        <p>{session.get('rebuttal_speech', '')[:300].replace(chr(10), '<br>')}...</p>
        <p style='color: #6c7086;'>【驳论评分】驳论针对性:{reb_score.get('targeting','-')}/25 
        逻辑拆解:{reb_score.get('deconstruction','-')}/25 
        论据反驳:{reb_score.get('refutation','-')}/25 
        表达力度:{reb_score.get('force','-')}/25 
        综合:{reb_score.get('total','-')}/100</p>
        <hr style='border-color: #45475a;'>

        <h4 style='color: #89b4fa;'>📋 AI总评</h4>
        <p>{evaluation.get('summary', '')}</p>
        </body></html>"""

        msg = CustomDialog(self._mw, dialog_type="info", title="立论驳论记录查看",
                          message=content, buttons=[("确定", "ok")])
        msg.exec_()
