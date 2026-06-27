"""快速刷题管理器 — UI 构建 + 答题流程 + 历史记录"""
import json
import os
import random
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QFontMetrics
from components.theme_colors import tc, refresh
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QStackedWidget, QScrollArea, QWidget, QComboBox,
    QSizePolicy,
)
from components.star_button import StarButton
from components.popup_dialog import CustomDialog

from workers.training.train_question_worker import TrainingQuestionWorker
from workers.training.train_eval_worker import TrainingEvalWorker


class QuickQuizManager:
    """快速刷题管理器：UI 构建 + 答题流程 + 历史记录"""

    def __init__(self, train_mgr):
        """train_mgr: TrainingManager 实例"""
        self._tm = train_mgr
        self._mw = train_mgr._mw

        # ---- 数据 ----
        self._mode: str = ""
        self._difficulty: str = "medium"
        self._format: str = ""
        self._position: str = ""
        self._active: bool = False
        self._questions: list = []
        self._current_index: int = -1
        self._score: int = 0
        self._correct: int = 0
        self._answered: bool = False
        self._sessions: list = []
        self._history_view: str = "sessions"
        self._detail_index: int = 0
        self._result_cards: list = []
        self._question_worker = None
        self._prefetch_worker = None
        self._pending_question = None
        self._eval_worker = None
        self._dialog = None
        self._current_history_session: dict = {}

    # ==================== UI 构建 ====================

    def build_pages(self, parent_stack: QStackedWidget) -> int:
        """构建快速刷题的所有子页面，返回起始页索引"""
        self._stack = parent_stack
        start_idx = parent_stack.count()

        self._build_config_page()
        self._build_quiz_page()
        self._build_sessions_page()
        self._build_cards_page()
        self._build_detail_page()
        self._build_summary_page()

        self._update_mode_selection()
        return start_idx

    def _build_config_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        btn_back = StarButton("← 返回", None, layout_mode="text_only", ratio_h=0.7)
        btn_back.setObjectName("smallBtn")
        btn_back.setFixedHeight(28)
        btn_back.clicked.connect(lambda: self._tm._train_stack.setCurrentIndex(0))
        layout.addWidget(btn_back)

        lbl_mode = QLabel("选择训练模式")
        lbl_mode.setObjectName("qqSectionTitle")
        lbl_mode.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        layout.addWidget(lbl_mode)

        mode_btns = QHBoxLayout()
        mode_btns.setSpacing(8)

        self._btn_mode_technique = StarButton("辩论技巧", None, layout_mode="text_only", ratio_h=0.85, checkable=True)
        self._btn_mode_technique.setObjectName("trainModeBtn")
        self._btn_mode_technique.setFont(QFont("Microsoft YaHei", 10))
        self._btn_mode_technique._checked_accent = tc("accent_blue")
        self._btn_mode_technique.setFixedSize(100, 72)
        self._btn_mode_technique.setToolTip("选择题+判断题，考察辩论理论知识点")
        self._btn_mode_technique.clicked.connect(lambda: self._on_mode_select("technique"))

        self._btn_mode_scenario = StarButton("辩论场景", None, layout_mode="text_only", ratio_h=0.85, checkable=True)
        self._btn_mode_scenario.setObjectName("trainModeBtn")
        self._btn_mode_scenario.setFont(QFont("Microsoft YaHei", 10))
        self._btn_mode_scenario._checked_accent = tc("accent_blue")
        self._btn_mode_scenario.setFixedSize(100, 72)
        self._btn_mode_scenario.setToolTip("场景模拟题，考察实战应变能力")
        self._btn_mode_scenario.clicked.connect(lambda: self._on_mode_select("scenario"))

        self._btn_mode_mixed = StarButton("混合训练", None, layout_mode="text_only", ratio_h=0.85, checkable=True)
        self._btn_mode_mixed.setObjectName("trainModeBtn")
        self._btn_mode_mixed.setFont(QFont("Microsoft YaHei", 10))
        self._btn_mode_mixed._checked_accent = tc("accent_blue")
        self._btn_mode_mixed.setFixedSize(100, 72)
        self._btn_mode_mixed.setToolTip("随机交替技巧题和场景题")
        self._btn_mode_mixed.clicked.connect(lambda: self._on_mode_select("mixed"))

        mode_btns.addWidget(self._btn_mode_technique)
        mode_btns.addWidget(self._btn_mode_scenario)
        mode_btns.addWidget(self._btn_mode_mixed)
        mode_btns.addStretch()
        layout.addLayout(mode_btns)

        lbl_diff = QLabel("选择难度")
        lbl_diff.setObjectName("qqSectionTitle")
        lbl_diff.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        layout.addWidget(lbl_diff)

        diff_btns = QHBoxLayout()
        diff_btns.setSpacing(8)

        self._btn_diff_easy = StarButton("🟢 简单", None, layout_mode="text_only", ratio_h=0.85, checkable=True)
        self._btn_diff_easy.setObjectName("trainDiffBtn")
        self._btn_diff_easy.setFont(QFont("Microsoft YaHei", 10))
        self._btn_diff_easy._checked_accent = tc("accent_blue")
        self._btn_diff_easy.setFixedSize(90, 56)
        self._btn_diff_easy.setToolTip("基础概念·入门练习·每题+10分")
        self._btn_diff_easy.clicked.connect(lambda: self._on_diff_select("easy"))

        self._btn_diff_medium = StarButton("🟡 中等", None, layout_mode="text_only", ratio_h=0.85, checkable=True)
        self._btn_diff_medium.setObjectName("trainDiffBtn")
        self._btn_diff_medium.setFont(QFont("Microsoft YaHei", 10))
        self._btn_diff_medium._checked_accent = tc("accent_blue")
        self._btn_diff_medium.setChecked(True)
        self._btn_diff_medium.setFixedSize(90, 56)
        self._btn_diff_medium.setToolTip("理论应用·常规训练·每题+15分")
        self._btn_diff_medium.clicked.connect(lambda: self._on_diff_select("medium"))

        self._btn_diff_hard = StarButton("🔴 困难", None, layout_mode="text_only", ratio_h=0.85, checkable=True)
        self._btn_diff_hard.setObjectName("trainDiffBtn")
        self._btn_diff_hard.setFont(QFont("Microsoft YaHei", 10))
        self._btn_diff_hard._checked_accent = tc("accent_blue")
        self._btn_diff_hard.setFixedSize(90, 56)
        self._btn_diff_hard.setToolTip("深度辨析·高阶挑战·每题+20分")
        self._btn_diff_hard.clicked.connect(lambda: self._on_diff_select("hard"))

        diff_btns.addWidget(self._btn_diff_easy)
        diff_btns.addWidget(self._btn_diff_medium)
        diff_btns.addWidget(self._btn_diff_hard)
        diff_btns.addStretch()
        layout.addLayout(diff_btns)

        self._lbl_selection = QLabel("")
        self._lbl_selection.setObjectName("qqSelectionInfo")
        self._lbl_selection.setFont(QFont("Microsoft YaHei", 9))
        layout.addWidget(self._lbl_selection)

        train_sep = QFrame()
        train_sep.setObjectName("trainHLine")
        train_sep.setFrameShape(QFrame.HLine)
        layout.addWidget(train_sep)

        lbl_position_title = QLabel("专精辩位 (可选)")
        lbl_position_title.setObjectName("qqSectionTitle")
        lbl_position_title.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        layout.addWidget(lbl_position_title)

        lbl_format_label = QLabel("赛制选择")
        lbl_format_label.setObjectName("qqSubLabel")
        lbl_format_label.setFont(QFont("Microsoft YaHei", 9))
        layout.addWidget(lbl_format_label)

        self._format_combo = QComboBox()
        self._format_combo.setObjectName("trainFormatCombo")
        self._format_combo.setFont(QFont("Microsoft YaHei", 10))
        self._format_combo.setMinimumHeight(30)
        self._format_combo.setCursor(Qt.PointingHandCursor)
        self._format_combo.currentTextChanged.connect(self._on_format_changed)
        layout.addWidget(self._format_combo)

        lbl_role_title = QLabel("辩位选择")
        lbl_role_title.setObjectName("qqSubLabel")
        lbl_role_title.setFont(QFont("Microsoft YaHei", 9))
        layout.addWidget(lbl_role_title)

        self._position_layout = QHBoxLayout()
        self._position_layout.setSpacing(6)
        self._position_btns: dict = {}
        self._position_layout.addStretch()
        layout.addLayout(self._position_layout)

        mw = self._mw
        mw._tournament_mgr.refresh_train_combo(self._format_combo)
        self._refresh_position_buttons(self._format_combo.currentText())

        layout.addStretch()
        btn_start = StarButton("▶ 开始刷题", None, layout_mode="text_only", ratio_h=0.7)
        btn_start.setObjectName("primaryBtn")
        btn_start.setFixedHeight(36)
        btn_start.clicked.connect(self._on_training_start)
        layout.addWidget(btn_start)

        self._stack.addWidget(page)  # config page

    def _build_quiz_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self._lbl_quiz_progress = QLabel("")
        self._lbl_quiz_progress.setObjectName("qqQuizProgress")
        self._lbl_quiz_progress.setFont(QFont("Microsoft YaHei", 9))
        layout.addWidget(self._lbl_quiz_progress)

        self._question_label = QLabel("")
        self._question_label.setObjectName("qqQuestionLabel")
        self._question_label.setFont(QFont("Microsoft YaHei", 11))
        self._question_label.setWordWrap(True)
        self._question_label.setMinimumHeight(60)
        layout.addWidget(self._question_label)

        self._scenario_frame = QFrame()
        self._scenario_frame.setObjectName("scenarioFrame")
        self._scenario_frame.setVisible(False)
        scenario_frame_layout = QVBoxLayout(self._scenario_frame)
        scenario_frame_layout.setContentsMargins(8, 6, 8, 6)
        self._lbl_scenario_info = QLabel("")
        self._lbl_scenario_info.setObjectName("qqScenarioInfo")
        self._lbl_scenario_info.setFont(QFont("Microsoft YaHei", 10))
        self._lbl_scenario_info.setWordWrap(True)
        scenario_frame_layout.addWidget(self._lbl_scenario_info)
        layout.addWidget(self._scenario_frame)

        self._option_btns: list = []
        self._option_labels: list = []
        self._option_selected: int = -1
        self._options_layout = QVBoxLayout()
        self._options_layout.setSpacing(4)
        for i in range(4):
            frame = QFrame()
            frame.setObjectName("trainOptionBtn")
            frame.setCursor(Qt.PointingHandCursor)
            frame.setMinimumHeight(0)
            frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            frame_layout = QHBoxLayout(frame)
            frame_layout.setContentsMargins(10, 8, 10, 8)
            frame_layout.setSpacing(0)
            lbl = QLabel("")
            lbl.setObjectName("trainOptionLabel")
            lbl.setFont(QFont("Microsoft YaHei", 11))
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            lbl.setTextInteractionFlags(Qt.NoTextInteraction)
            frame_layout.addWidget(lbl, stretch=1)
            frame._option_index = i
            frame._label = lbl
            frame._selected = False
            frame._enabled = True
            frame.mousePressEvent = lambda event, idx=i: self._on_option_click(idx)
            frame.setVisible(False)
            self._option_btns.append(frame)
            self._option_labels.append(lbl)
            self._options_layout.addWidget(frame)
        layout.addLayout(self._options_layout)

        for i in range(2, 4):
            self._option_btns[i].setVisible(False)

        self._result_frame = QFrame()
        self._result_frame.setObjectName("trainResultFrame")
        self._result_frame.setVisible(False)
        result_layout = QVBoxLayout(self._result_frame)
        result_layout.setContentsMargins(8, 6, 8, 6)
        result_layout.setSpacing(4)

        self._lbl_result = QLabel("")
        self._lbl_result.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        self._lbl_result.setWordWrap(True)
        result_layout.addWidget(self._lbl_result)

        self._lbl_explanation = QLabel("")
        self._lbl_explanation.setObjectName("qqExplanation")
        self._lbl_explanation.setFont(QFont("Microsoft YaHei", 9))
        self._lbl_explanation.setWordWrap(True)
        result_layout.addWidget(self._lbl_explanation)

        self._lbl_improvement = QLabel("")
        self._lbl_improvement.setObjectName("qqImprovement")
        self._lbl_improvement.setFont(QFont("Microsoft YaHei", 9))
        self._lbl_improvement.setWordWrap(True)
        result_layout.addWidget(self._lbl_improvement)

        layout.addWidget(self._result_frame)
        layout.addStretch()

        quiz_btn_row = QHBoxLayout()
        self._btn_next = StarButton("🔄 下一题", None, layout_mode="text_only", ratio_h=0.7)
        self._btn_next.setObjectName("primaryBtn")
        self._btn_next.setFixedHeight(34)
        self._btn_next.clicked.connect(self._on_training_next)
        self._btn_next.setVisible(False)

        self._btn_end = StarButton("🏁 结束答题", None, layout_mode="text_only", ratio_h=0.7)
        self._btn_end.setFixedHeight(34)
        self._btn_end.clicked.connect(self._on_training_end)

        quiz_btn_row.addStretch()
        quiz_btn_row.addWidget(self._btn_next)
        quiz_btn_row.addWidget(self._btn_end)
        layout.addLayout(quiz_btn_row)

        self._stack.addWidget(page)  # quiz page

    def _build_sessions_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        lbl_title = QLabel("📂 往期训练记录")
        lbl_title.setObjectName("qqSectionTitle")
        lbl_title.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        layout.addWidget(lbl_title)

        self._sessions_scroll = QScrollArea()
        self._sessions_scroll.setObjectName("qqScrollArea")
        self._sessions_scroll.setWidgetResizable(True)
        self._sessions_container = QWidget()
        self._sessions_container.setObjectName("qqScrollContainer")
        self._sessions_list_layout = QVBoxLayout(self._sessions_container)
        self._sessions_list_layout.setSpacing(4)
        self._sessions_list_layout.addStretch()
        self._sessions_scroll.setWidget(self._sessions_container)
        layout.addWidget(self._sessions_scroll)

        btn_back = StarButton("← 返回训练", None, layout_mode="text_only", ratio_h=0.7)
        btn_back.setFixedHeight(32)
        btn_back.clicked.connect(lambda: self._tm._train_stack.setCurrentIndex(0))
        layout.addWidget(btn_back)

        self._stack.addWidget(page)  # sessions page

    def _build_cards_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        self._lbl_cards_session_info = QLabel("")
        self._lbl_cards_session_info.setObjectName("qqCardsSessionInfo")
        self._lbl_cards_session_info.setFont(QFont("Microsoft YaHei", 9))
        layout.addWidget(self._lbl_cards_session_info)

        self._cards_scroll = QScrollArea()
        self._cards_scroll.setObjectName("qqScrollArea")
        self._cards_scroll.setWidgetResizable(True)
        self._cards_container = QWidget()
        self._cards_container.setObjectName("qqScrollContainer")
        self._cards_list_layout = QVBoxLayout(self._cards_container)
        self._cards_list_layout.setSpacing(4)
        self._cards_list_layout.addStretch()
        self._cards_scroll.setWidget(self._cards_container)
        layout.addWidget(self._cards_scroll)

        cards_btn_row = QHBoxLayout()
        btn_back_cards = StarButton("← 返回会话列表", None, layout_mode="text_only", ratio_h=0.7)
        btn_back_cards.setFixedHeight(32)
        btn_back_cards.clicked.connect(self._on_back_to_sessions)
        cards_btn_row.addWidget(btn_back_cards)
        cards_btn_row.addStretch()
        self._btn_del_session = StarButton("删除此记录", None, layout_mode="text_only", ratio_h=0.7)
        self._btn_del_session.setFixedHeight(32)
        self._btn_del_session.clicked.connect(self._on_delete_session)
        self._btn_del_session.setVisible(False)
        cards_btn_row.addWidget(self._btn_del_session)
        layout.addLayout(cards_btn_row)

        self._stack.addWidget(page)  # cards page

    def _build_detail_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        self._lbl_detail_nav = QLabel("")
        self._lbl_detail_nav.setObjectName("qqDetailNav")
        self._lbl_detail_nav.setFont(QFont("Microsoft YaHei", 9))
        layout.addWidget(self._lbl_detail_nav)

        self._detail_question_label = QLabel("")
        self._detail_question_label.setObjectName("qqDetailQuestion")
        self._detail_question_label.setFont(QFont("Microsoft YaHei", 11))
        self._detail_question_label.setWordWrap(True)
        layout.addWidget(self._detail_question_label)

        self._detail_scenario_label = QLabel("")
        self._detail_scenario_label.setObjectName("qqScenarioInfo")
        self._detail_scenario_label.setFont(QFont("Microsoft YaHei", 10))
        self._detail_scenario_label.setWordWrap(True)
        self._detail_scenario_label.setVisible(False)
        layout.addWidget(self._detail_scenario_label)

        self._detail_options_layout = QVBoxLayout()
        self._detail_options_layout.setSpacing(2)
        self._detail_option_labels: list = []
        for _ in range(4):
            lbl = QLabel("")
            lbl.setFont(QFont("Microsoft YaHei", 9))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {tc("subtext")}; padding: 2px 6px;")
            self._detail_option_labels.append(lbl)
            self._detail_options_layout.addWidget(lbl)
            lbl.setVisible(False)
        layout.addLayout(self._detail_options_layout)

        self._detail_explanation_label = QLabel("")
        self._detail_explanation_label.setObjectName("qqExplanation")
        self._detail_explanation_label.setFont(QFont("Microsoft YaHei", 9))
        self._detail_explanation_label.setWordWrap(True)
        layout.addWidget(self._detail_explanation_label)

        self._detail_improvement_label = QLabel("")
        self._detail_improvement_label.setObjectName("qqImprovement")
        self._detail_improvement_label.setFont(QFont("Microsoft YaHei", 9))
        self._detail_improvement_label.setWordWrap(True)
        layout.addWidget(self._detail_improvement_label)

        layout.addStretch()
        detail_nav_row = QHBoxLayout()
        btn_back_detail = StarButton("← 返回题目列表", None, layout_mode="text_only", ratio_h=0.7)
        btn_back_detail.setFixedHeight(32)
        btn_back_detail.clicked.connect(self._on_detail_back)
        detail_nav_row.addWidget(btn_back_detail)
        detail_nav_row.addStretch()
        self._btn_detail_prev = StarButton("← 上一题", None, layout_mode="text_only", ratio_h=0.7)
        self._btn_detail_prev.setFixedHeight(32)
        self._btn_detail_prev.clicked.connect(self._on_detail_prev)
        detail_nav_row.addWidget(self._btn_detail_prev)
        self._btn_detail_next = StarButton("下一题 →", None, layout_mode="text_only", ratio_h=0.7)
        self._btn_detail_next.setFixedHeight(32)
        self._btn_detail_next.clicked.connect(self._on_detail_next)
        detail_nav_row.addWidget(self._btn_detail_next)
        layout.addLayout(detail_nav_row)

        self._stack.addWidget(page)  # detail page

    def _build_summary_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        summary_header_row = QHBoxLayout()
        self._lbl_summary_title = QLabel("训练总结")
        self._lbl_summary_title.setObjectName("trainPanelTitle")
        self._lbl_summary_title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        summary_header_row.addWidget(self._lbl_summary_title)
        summary_header_row.addStretch()
        layout.addLayout(summary_header_row)

        self._lbl_summary_stats = QLabel("")
        self._lbl_summary_stats.setObjectName("qqSummaryStats")
        self._lbl_summary_stats.setFont(QFont("Microsoft YaHei", 10))
        self._lbl_summary_stats.setWordWrap(True)
        layout.addWidget(self._lbl_summary_stats)

        self._lbl_diff_stats = QLabel("")
        self._lbl_diff_stats.setObjectName("qqSummaryStats")
        self._lbl_diff_stats.setFont(QFont("Microsoft YaHei", 9))
        self._lbl_diff_stats.setWordWrap(True)
        layout.addWidget(self._lbl_diff_stats)

        self._lbl_summary_eval = QLabel("")
        self._lbl_summary_eval.setObjectName("qqSummaryEval")
        self._lbl_summary_eval.setFont(QFont("Microsoft YaHei", 9))
        self._lbl_summary_eval.setWordWrap(True)
        layout.addWidget(self._lbl_summary_eval)

        layout.addStretch()

        btn_new_train = StarButton("开始新训练", None, layout_mode="text_only", ratio_h=0.7)
        btn_new_train.setObjectName("primaryBtn")
        btn_new_train.setFixedHeight(34)
        btn_new_train.clicked.connect(self._on_training_new)
        layout.addWidget(btn_new_train)

        self._stack.addWidget(page)  # summary page

    # ---- Page index properties ----
    @property
    def config_idx(self) -> int:
        return self._config_idx

    @property
    def quiz_idx(self) -> int:
        return self._config_idx + 1

    @property
    def sessions_idx(self) -> int:
        return self._config_idx + 2

    @property
    def cards_idx(self) -> int:
        return self._config_idx + 3

    @property
    def detail_idx(self) -> int:
        return self._config_idx + 4

    @property
    def summary_idx(self) -> int:
        return self._config_idx + 5

    # ==================== 配置选择 ====================

    def _auto_size_button(self, btn, text, height, padding_h=24, min_width=40):
        fm = QFontMetrics(btn.font())
        text_width = fm.horizontalAdvance(text)
        btn.setFixedHeight(height)
        btn.setMinimumWidth(max(min_width, text_width + padding_h))

    @staticmethod
    def _diff_score(diff: str) -> int:
        return {"easy": 10, "medium": 15, "hard": 20}.get(diff, 15)

    def _update_mode_selection(self):
        sel_parts = []
        if self._mode:
            sel_parts.append("📚辩论技巧" if self._mode == "technique" else
                             "🎬辩论场景" if self._mode == "scenario" else "🔀混合训练")
        diff_map = {"easy": "🟢简单", "medium": "🟡中等", "hard": "🔴困难"}
        sel_parts.append(diff_map.get(self._difficulty, "🟡中等"))
        if self._format:
            if self._position:
                sel_parts.append(f"🎯{self._format}·{self._position}")
            else:
                sel_parts.append(f"🎯{self._format}")
        self._lbl_selection.setText(f"已选: {' · '.join(sel_parts)}")

    def _on_mode_select(self, mode: str):
        self._mode = mode
        for btn in [self._btn_mode_technique, self._btn_mode_scenario, self._btn_mode_mixed]:
            btn.setChecked(False)
        {"technique": self._btn_mode_technique, "scenario": self._btn_mode_scenario,
         "mixed": self._btn_mode_mixed}[mode].setChecked(True)
        self._update_mode_selection()

    def _on_diff_select(self, diff: str):
        self._difficulty = diff
        for btn in [self._btn_diff_easy, self._btn_diff_medium, self._btn_diff_hard]:
            btn.setChecked(False)
        {"easy": self._btn_diff_easy, "medium": self._btn_diff_medium,
         "hard": self._btn_diff_hard}[diff].setChecked(True)
        self._update_mode_selection()

    def refresh_format_combo(self):
        """刷新专精辩位赛制下拉框（委托 TournamentManager）"""
        if hasattr(self, '_format_combo'):
            self._mw._tournament_mgr.refresh_train_combo(self._format_combo)

    def _get_positions_for_format(self, format_name: str) -> list:
        return self._mw._tournament_mgr.get_positions_for_format(format_name)

    def _refresh_position_buttons(self, format_name: str):
        for btn in list(self._position_btns.values()):
            if self._position_layout.indexOf(btn) >= 0:
                self._position_layout.removeWidget(btn)
            btn.deleteLater()
        self._position_btns.clear()

        item = self._position_layout.takeAt(self._position_layout.count() - 1)
        if item:
            del item

        positions = self._get_positions_for_format(format_name)
        for pos in positions:
            btn = StarButton(pos, None, layout_mode="text_only", ratio_h=0.7, checkable=True)
            btn.setObjectName("trainPositionBtn")
            btn._checked_accent = tc("accent_blue")
            btn.setFixedHeight(34)
            btn.setToolTip(f"专精训练 {pos}" if pos != "混合" else "不限定辩位，随机出题")
            btn.clicked.connect(lambda p=pos: self._on_position_select(p))
            self._position_btns[pos] = btn
            self._position_layout.addWidget(btn)

        self._position_layout.addStretch()

        if self._position in self._position_btns:
            self._position_btns[self._position].setChecked(True)
        else:
            self._position = ""
            if "混合" in self._position_btns:
                self._position_btns["混合"].setChecked(True)

    def _on_format_changed(self, format_name: str):
        self._format = format_name if format_name and format_name != "不限制（混合出题）" else ""
        self._position = ""
        self._refresh_position_buttons(format_name)
        self._update_mode_selection()

    def _on_position_select(self, position: str):
        self._position = position if position != "混合" else ""
        for btn in self._position_btns.values():
            btn.setChecked(False)
        key = position
        if key in self._position_btns:
            self._position_btns[key].setChecked(True)
        self._update_mode_selection()

    # ==================== 答题流程 ====================

    def _on_training_start(self):
        mw = self._mw
        if not self._mode:
            CustomDialog.warning(mw, "提示", "请先选择训练模式")
            return
        api_config = mw._load_api_config()
        if not api_config.get("api_key"):
            ptype = api_config.get("provider_type", "auto")
            if ptype not in ("auto", "web"):
                CustomDialog.warning(mw, "缺少 API Key",
                                    "请在 api_config.json 中填写您的 DeepSeek API Key 后再使用模拟训练功能。")
                return
            # auto/web 无 key 时静默跳过，由 _resolve_provider_type 回退到 Web

        self._questions = []
        self._current_index = -1
        self._score = 0
        self._correct = 0
        self._active = True
        self._answered = False
        self._pending_question = None
        self._tm._train_stack.setCurrentIndex(self.quiz_idx)
        self._update_quiz_status()
        self._reset_quiz_ui()
        self._request_next_question()

    def _reset_quiz_ui(self):
        self._result_frame.setVisible(False)
        self._scenario_frame.setVisible(False)
        self._btn_next.setVisible(False)
        self._option_selected = -1
        for frame in self._option_btns:
            frame._selected = False
            frame._enabled = True
            frame.setStyleSheet("")
        for lbl in self._option_labels:
            lbl.setStyleSheet(f"color: {tc("text")}; padding: 0; background: transparent;")


    def _update_quiz_status(self):
        if self._active and self._current_index >= 0:
            diff_map = {"easy": "🟢简单", "medium": "🟡中等", "hard": "🔴困难"}
            q = self._questions[self._current_index]
            q_diff = q.get("difficulty", self._difficulty)
            q_diff_label = diff_map.get(q_diff, "🟡中等")
            qtype = q.get("type", "choice")
            type_label = "选择题" if qtype == "choice" else "判断题" if qtype == "truefalse" else "场景题"
            self._lbl_quiz_progress.setText(
                f"第 {self._current_index + 1} 题 · {type_label} · {q_diff_label}")
            self._tm._lbl_train_status.setText(
                f"正确率: {self._correct}/{self._current_index + 1}  得分: {self._score}分")
        else:
            self._lbl_quiz_progress.setText("")
            self._tm._lbl_train_status.setText("")

    def _request_next_question(self):
        self._reset_quiz_ui()
        self._mw._ai_loading_bar.show_loading("AI出题中...")
        self._answered = False
        self._start_question_worker(self._on_question_ready)

    def _prefetch_next_question(self):
        if not self._active:
            return
        self._pending_question = None
        self._start_question_worker(self._on_prefetch_ready)

    def _start_question_worker(self, callback):
        mw = self._mw
        api_config = mw._load_api_config()
        debate_title = ""
        try:
            debate_title = mw.current_debate_path or "辩论技巧训练"
        except Exception:
            debate_title = "辩论技巧训练"

        actual_mode = self._mode
        if actual_mode == "mixed":
            actual_mode = random.choice(["technique", "scenario"])

        worker = TrainingQuestionWorker(
            api_config, actual_mode, self._difficulty, debate_title,
            self._format, self._position)
        worker.finished.connect(callback)
        worker.start()

        if callback == self._on_question_ready:
            self._question_worker = worker
        else:
            self._prefetch_worker = worker

    def _on_prefetch_ready(self, success: bool, error_msg: str, question_data: dict):
        if not self._active:
            return
        if success and self._pending_question is None:
            q = question_data
            q["user_answer"] = ""
            q["is_correct"] = False
            q["index"] = -1
            self._pending_question = q

    def _on_question_ready(self, success: bool, error_msg: str, question_data: dict):
        self._mw._ai_loading_bar.hide_loading()
        if not self._active:
            return
        if not success:
            CustomDialog.warning(self._mw, "出题失败", error_msg)
            self._tm._train_stack.setCurrentIndex(self.config_idx)
            self._active = False
            return

        self._reset_quiz_ui()
        self._answered = False
        q = question_data
        q["user_answer"] = ""
        q["is_correct"] = False
        q["index"] = len(self._questions) + 1
        self._questions.append(q)
        self._current_index = len(self._questions) - 1
        self._display_current_question()
        self._update_quiz_status()
        self._prefetch_next_question()

    def _display_current_question(self):
        q = self._questions[self._current_index]
        self._question_label.setText(f"Q: {q.get('question', '')}")

        if q.get("category") == "scenario" and "scenario" in q:
            sc = q["scenario"]
            info_text = f"📍 辩题: {sc.get('debate_title', '')}\n"
            info_text += f"🎭 你的角色: {sc.get('your_role', '')}\n"
            info_text += f"⚔️ 局面: {sc.get('situation', '')}\n"
            info_text += f"🎯 任务: {sc.get('task', '')}"
            self._lbl_scenario_info.setText(info_text)
            self._scenario_frame.setVisible(True)
        else:
            self._scenario_frame.setVisible(False)

        qtype = q.get("type", "choice")
        options = q.get("options", [])
        if qtype == "truefalse":
            options = ["✓ 正确", "✗ 错误"]
        labels = ["A", "B", "C", "D"]
        for i in range(4):
            frame = self._option_btns[i]
            if i < len(options):
                prefix = f"[{labels[i]}] " if qtype == "choice" else ""
                self._option_labels[i].setText(f"{prefix}{options[i]}")
                frame.setVisible(True)
                frame._enabled = True
                frame._selected = False
                frame.setStyleSheet("")
            else:
                frame.setVisible(False)

    def _on_option_click(self, idx: int):
        if self._answered:
            return
        frame = self._option_btns[idx]
        if not frame._enabled:
            return
        self._answered = True
        self._option_selected = idx
        q = self._questions[self._current_index]
        labels = ["A", "B", "C", "D"]
        q["user_answer"] = labels[idx]

        correct = q.get("correct", "")
        is_correct = (labels[idx] == correct)
        q["is_correct"] = is_correct

        diff = q.get("difficulty", self._difficulty)
        score = self._diff_score(diff)
        if is_correct:
            self._score += score
            self._correct += 1

        self._display_result(q, idx, is_correct)
        self._update_quiz_status()
        self._btn_next.setVisible(True)

        correct_color = "#a6e3a1"
        wrong_color = "#f38ba8"
        for i, frm in enumerate(self._option_btns):
            frm._enabled = False
            if i == idx:
                bg = correct_color if is_correct else wrong_color
                self._option_labels[i].setStyleSheet(f"color: {tc("base")}; padding: 0; background: transparent;")
                frm.setStyleSheet(f"#trainOptionBtn {{ background-color: {bg}; border-radius: 8px; }}")
            elif labels[i] == correct:
                self._option_labels[i].setStyleSheet(f"color: {tc("base")}; padding: 0; background: transparent;")
                frm.setStyleSheet(f"#trainOptionBtn {{ background-color: {correct_color}; border-radius: 8px; }}")

    def _display_result(self, q: dict, user_idx: int, is_correct: bool):
        labels = ["A", "B", "C", "D"]
        correct = q.get("correct", "")
        diff = q.get("difficulty", self._difficulty)
        score = self._diff_score(diff)

        result_text = f"✅ 回答正确！ +{score}分" if is_correct else f"❌ 回答错误！ (正确答案: {correct}) +0分"
        self._lbl_result.setText(result_text)
        self._lbl_result.setStyleSheet(f"color: {tc('accent_green')};" if is_correct else f"color: {tc('accent_red')};")

        explanation_text = "📖 解析:\n"
        if q.get("category") == "scenario":
            analysis = q.get("strategy_analysis", {})
            for i, label in enumerate(labels):
                expl = analysis.get(label, "")
                if expl:
                    mark = "✓" if label == correct else "✗"
                    explanation_text += f"\n{label} {mark} {expl}"
        else:
            explanations = q.get("explanation", {})
            for i, label in enumerate(labels):
                expl = explanations.get(label, "")
                if expl:
                    mark = "✓" if label == correct else "✗"
                    explanation_text += f"\n{label} {mark} {expl}"

        self._lbl_explanation.setText(explanation_text)

        user_label = labels[user_idx]
        tips = q.get("improvement_tips", {})
        tip = tips.get(user_label, q.get("improvement_tip", ""))
        if tip:
            self._lbl_improvement.setText(f"💡 提升建议: {tip}")

        self._result_frame.setVisible(True)

    def _on_training_next(self):
        pending = self._pending_question
        if pending is not None:
            self._reset_quiz_ui()
            self._answered = False
            self._pending_question = None
            q = pending
            q["index"] = len(self._questions) + 1
            self._questions.append(q)
            self._current_index = len(self._questions) - 1
            self._display_current_question()
            self._update_quiz_status()
            self._prefetch_next_question()
        else:
            self._mw._ai_loading_bar.show_loading("AI出题中...")
            self._start_question_worker(self._on_question_ready)

    def _on_training_end(self):
        self._pending_question = None
        if not self._questions:
            self._tm._train_stack.setCurrentIndex(self.config_idx)
            self._active = False
            return
        self._active = False
        self._tm._train_stack.setCurrentIndex(self.summary_idx)
        self._show_summary_content()

    def _on_training_new(self):
        self._questions = []
        self._current_index = -1
        self._score = 0
        self._correct = 0
        self._active = False
        self._pending_question = None
        self._tm._train_stack.setCurrentIndex(self.config_idx)

    def _show_summary_content(self):
        total = len(self._questions)
        correct = self._correct
        rate = f"{(correct / total * 100):.0f}%" if total > 0 else "0%"

        self._lbl_summary_title.setText("🎯 训练总结")

        mode_label = {"technique": "辩论技巧", "scenario": "辩论场景", "mixed": "混合训练"}.get(self._mode, "")
        diff_label = {"easy": "简单", "medium": "中等", "hard": "困难"}.get(self._difficulty, "中等")
        stats_text = (f"训练模式: {mode_label} · 难度: {diff_label}\n"
                      f"总题数: {total} · 正确: {correct} · 错误: {total - correct}\n"
                      f"正确率: {rate} · 总分: {self._score}")
        if self._format:
            if self._position:
                stats_text += f"\n专精赛制: {self._format} · 辩位: {self._position}"
            else:
                stats_text += f"\n专精赛制: {self._format}（混合辩位）"
        self._lbl_summary_stats.setText(stats_text)

        diff_stats = {"easy": {"total": 0, "correct": 0}, "medium": {"total": 0, "correct": 0},
                      "hard": {"total": 0, "correct": 0}}
        for q in self._questions:
            d = q.get("difficulty", self._difficulty)
            if d in diff_stats:
                diff_stats[d]["total"] += 1
                if q.get("is_correct"):
                    diff_stats[d]["correct"] += 1

        diff_text = "按难度分段:\n"
        diff_colors = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}
        for d in ["easy", "medium", "hard"]:
            s = diff_stats[d]
            if s["total"] > 0:
                dr = f"{(s['correct'] / s['total'] * 100):.0f}%"
                bar = "█" * (s["correct"] * 10 // s["total"]) if s["total"] > 0 else ""
                diff_text += f"  {diff_colors[d]} {d}: {s['correct']}/{s['total']} ({dr}) {bar}\n"
        self._lbl_diff_stats.setText(diff_text)

        eval_text = "正在生成 AI 综合评价..."
        self._lbl_summary_eval.setText(eval_text)
        self._on_save_session()
        self._request_ai_evaluation()

    def _on_save_session(self):
        """保存训练会话到文件"""
        mw = self._mw
        project_dir = mw._get_current_project_path()
        if not project_dir:
            from components.res_path import get_resource_root
            project_dir = os.path.join(get_resource_root(), "training_sessions")
            os.makedirs(project_dir, exist_ok=True)

        train_dir = os.path.join(project_dir, "training_sessions")
        os.makedirs(train_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"train_{timestamp}.json"
        filepath = os.path.join(train_dir, filename)

        session_data = {
            "session_id": f"train_{timestamp}",
            "date": datetime.now().isoformat(),
            "mode": self._mode,
            "difficulty": self._difficulty,
            "format": self._format,
            "position": self._position,
            "total_questions": len(self._questions),
            "correct_count": self._correct,
            "score": self._score,
            "difficulty_stats": {},
            "questions": self._questions,
            "ai_evaluation": {}
        }

        diff_count = {}
        for q in self._questions:
            d = q.get("difficulty", self._difficulty)
            if d not in diff_count:
                diff_count[d] = {"total": 0, "correct": 0, "score": 0, "rate": 0}
            diff_count[d]["total"] += 1
            if q.get("is_correct"):
                diff_count[d]["correct"] += 1
                diff_count[d]["score"] += self._diff_score(d)
        for d, v in diff_count.items():
            v["rate"] = v["correct"] / v["total"] if v["total"] > 0 else 0
        session_data["difficulty_stats"] = diff_count

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            mw._update_status(f"训练记录已保存: {filename}")
        except Exception as e:
            mw._update_status(f"保存失败: {str(e)}")

    def _request_ai_evaluation(self):
        mw = self._mw
        api_config = mw._load_api_config()
        if not api_config.get("api_key"):
            self._lbl_summary_eval.setText("(需要配置 API Key 才能生成AI评价)")
            return

        mw._ai_loading_bar.show_loading("AI评估中...")
        self._eval_worker = TrainingEvalWorker(
            api_config, self._questions, self._mode, self._difficulty,
            self._format, self._position)
        self._eval_worker.finished.connect(self._on_eval_ready)
        self._eval_worker.start()

    def _on_eval_ready(self, success: bool, error_msg: str, eval_text: str):
        self._mw._ai_loading_bar.hide_loading()
        if success:
            self._lbl_summary_eval.setText(eval_text)
        else:
            self._lbl_summary_eval.setText(f"(AI评价生成失败: {error_msg})")

    # ==================== 历史记录 ====================

    def _get_training_sessions_dir(self) -> str:
        mw = self._mw
        project_dir = mw._get_current_project_path()
        if not project_dir:
            from components.res_path import get_resource_root
            project_dir = os.path.join(get_resource_root(), "training_sessions")
        train_dir = os.path.join(project_dir, "training_sessions")
        os.makedirs(train_dir, exist_ok=True)
        return train_dir

    def show_history(self):
        self._tm._train_stack.setCurrentIndex(self.sessions_idx)
        self._refresh_sessions()

    def _refresh_sessions(self):
        train_dir = self._get_training_sessions_dir()
        sessions = []
        if os.path.isdir(train_dir):
            for fname in sorted(os.listdir(train_dir), reverse=True):
                if fname.endswith(".json") and fname.startswith("train_"):
                    fpath = os.path.join(train_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        data["_filepath"] = fpath
                        sessions.append(data)
                    except Exception:
                        pass
        self._sessions = sessions

        while self._sessions_list_layout.count() > 1:
            item = self._sessions_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not sessions:
            lbl = QLabel("暂无训练记录")
            lbl.setObjectName("qqEmptyLabel")
            lbl.setFont(QFont("Microsoft YaHei", 10))
            lbl.setAlignment(Qt.AlignCenter)
            self._sessions_list_layout.insertWidget(0, lbl)
            return

        for sess in sessions:
            date_str = sess.get("date", "")[:16].replace("T", " ")
            mode = {"technique": "📚技巧", "scenario": "🎬场景", "mixed": "🔀混合"}.get(sess.get("mode", ""), "")
            diff = {"easy": "🟢简单", "medium": "🟡中等", "hard": "🔴困难"}.get(
                sess.get("difficulty", "medium"), "🟡中等")
            total = sess.get("total_questions", 0)
            correct = sess.get("correct_count", 0)
            score = sess.get("score", 0)

            btn = StarButton(
                f"{mode} · {diff}    {date_str}\n"
                f"总{total}题 · 正确{correct} · {score}分",
                None, layout_mode="text_only", ratio_h=0.7)
            btn.setMinimumHeight(48)
            btn.setObjectName("qqSessionBtn")
            btn.clicked.connect(lambda s=sess: self._on_view_session(s))
            self._sessions_list_layout.insertWidget(self._sessions_list_layout.count() - 1, btn)

    def _on_view_session(self, session: dict):
        self._history_view = "cards"
        self._sessions = [session]
        self._current_history_session = session
        self._tm._train_stack.setCurrentIndex(self.cards_idx)

        total = session.get("total_questions", 0)
        correct = session.get("correct_count", 0)
        score = session.get("score", 0)
        mode = {"technique": "📚辩论技巧", "scenario": "🎬辩论场景", "mixed": "🔀混合训练"}.get(
            session.get("mode", ""), "")
        diff = {"easy": "🟢简单", "medium": "🟡中等", "hard": "🔴困难"}.get(
            session.get("difficulty", "medium"), "")
        self._lbl_cards_session_info.setText(
            f"{mode} · {diff}   总{total}题 · 正确{correct} · {score}分")
        self._btn_del_session.setVisible(True)
        self._btn_del_session._session_data = session

        while self._cards_list_layout.count() > 1:
            item = self._cards_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        questions = session.get("questions", [])
        for q in questions:
            self._add_training_card(q)

    def _add_training_card(self, q: dict):
        idx = q.get("index", 0)
        qtype = q.get("type", "choice")
        type_icon = "🟦选择题" if qtype == "choice" else "🟧判断题" if qtype == "truefalse" else "🎬场景题"
        diff = q.get("difficulty", "medium")
        diff_icon = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(diff, "🟡")
        is_correct = q.get("is_correct", False)
        score_icon = "✅" if is_correct else "❌"
        question_text = q.get("question", "")

        diff_score = self._diff_score(diff)
        score_text = f"+{diff_score}" if is_correct else "+0"

        card = QFrame()
        card.setObjectName("trainingCard")
        card.setCursor(Qt.PointingHandCursor)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(8)

        lbl_idx = QLabel(f"#{idx}")
        lbl_idx.setObjectName("trainCardIndex")
        lbl_idx.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        lbl_idx.setFixedWidth(28)
        card_layout.addWidget(lbl_idx)

        lbl_type = QLabel(f"{type_icon}\n{diff_icon}")
        lbl_type.setObjectName("trainCardType")
        lbl_type.setFont(QFont("Microsoft YaHei", 8))
        lbl_type.setAlignment(Qt.AlignCenter)
        lbl_type.setMinimumWidth(56)
        card_layout.addWidget(lbl_type)

        lbl_q = QLabel(question_text)
        lbl_q.setObjectName("trainCardQuestion")
        lbl_q.setFont(QFont("Microsoft YaHei", 9))
        lbl_q.setWordWrap(True)
        lbl_q.setMinimumHeight(0)
        lbl_q.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card_layout.addWidget(lbl_q, stretch=1)

        lbl_score = QLabel(f"{score_icon}\n{score_text}")
        lbl_score.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        lbl_score.setAlignment(Qt.AlignCenter)
        lbl_score.setStyleSheet(
            "color: #a6e3a1; padding: 0;" if is_correct else "color: #f38ba8; padding: 0;")
        lbl_score.setFixedWidth(36)
        card_layout.addWidget(lbl_score)

        card.mouseDoubleClickEvent = lambda event, qdata=q: self._on_view_detail(qdata)
        card_layout.setObjectName("cardLayout")

        self._cards_list_layout.insertWidget(self._cards_list_layout.count() - 1, card)

    def _on_view_detail(self, q: dict):
        questions = self._current_history_session.get("questions", [])
        q_idx = q.get("index", 0) - 1
        if 0 <= q_idx < len(questions):
            self._detail_index = q_idx
            self._history_view = "detail"
            self._tm._train_stack.setCurrentIndex(self.detail_idx)
            self._render_detail_view()

    def _render_detail_view(self):
        questions = self._current_history_session.get("questions", [])
        total = len(questions)
        idx = self._detail_index
        if idx < 0 or idx >= len(questions):
            return

        q = questions[idx]
        self._lbl_detail_nav.setText(f"第 {idx + 1} 题 / 共 {total} 题")
        self._btn_detail_prev.setEnabled(idx > 0)
        self._btn_detail_next.setEnabled(idx < total - 1)

        self._detail_question_label.setText(f"Q: {q.get('question', '')}")

        if q.get("category") == "scenario" and "scenario" in q:
            sc = q["scenario"]
            self._detail_scenario_label.setText(
                f"📍 辩题: {sc.get('debate_title', '')}\n"
                f"🎭 角色: {sc.get('your_role', '')}\n"
                f"⚔️ 局面: {sc.get('situation', '')}\n"
                f"🎯 任务: {sc.get('task', '')}")
            self._detail_scenario_label.setVisible(True)
        else:
            self._detail_scenario_label.setVisible(False)

        labels = ["A", "B", "C", "D"]
        correct = q.get("correct", "")
        user_answer = q.get("user_answer", "")
        options = q.get("options", [])
        qtype = q.get("type", "choice")
        is_correct = q.get("is_correct", False)

        if qtype == "truefalse":
            options = ["✓ 正确", "✗ 错误"]

        for i in range(4):
            lbl = self._detail_option_labels[i]
            if i < len(options):
                label = labels[i]
                opt_text = f"[{label}] {options[i]}"
                if label == user_answer and label == correct:
                    opt_text += "  ✅ 你的选择 (正确)"
                elif label == user_answer:
                    opt_text += "  ❌ 你的选择"
                elif label == correct:
                    opt_text += "  ✓ 正确答案"

                if label == user_answer:
                    lbl.setStyleSheet(
                        "color: #a6e3a1; padding: 3px 6px; background-color: rgba(166,227,161,0.08); border-radius: 4px;"
                        if is_correct else
                        "color: #f38ba8; padding: 3px 6px; background-color: rgba(243,139,168,0.08); border-radius: 4px;")
                elif label == correct:
                    lbl.setStyleSheet(
                        "color: #a6e3a1; padding: 3px 6px; background-color: rgba(166,227,161,0.05); border-radius: 4px;")
                else:
                    lbl.setStyleSheet("color: #9399b2; padding: 3px 6px;")
                lbl.setText(opt_text)
                lbl.setVisible(True)
            else:
                lbl.setVisible(False)

        expl_text = "📖 解析:\n"
        if q.get("category") == "scenario":
            analysis = q.get("strategy_analysis", {})
            for label in labels:
                expl = analysis.get(label, "")
                if expl:
                    mark = "✓" if label == correct else "✗"
                    expl_text += f"\n{label} {mark} {expl}"
        else:
            explanations = q.get("explanation", {})
            for label in labels:
                expl = explanations.get(label, "")
                if expl:
                    mark = "✓" if label == correct else "✗"
                    expl_text += f"\n{label} {mark} {expl}"
        self._detail_explanation_label.setText(expl_text)

        if user_answer:
            tips = q.get("improvement_tips", {})
            tip = tips.get(user_answer, q.get("improvement_tip", ""))
            if tip:
                self._detail_improvement_label.setText(f"💡 当时建议: {tip}")
            else:
                self._detail_improvement_label.setText("")
        else:
            self._detail_improvement_label.setText("")

    def _on_detail_back(self):
        self._history_view = "cards"
        self._tm._train_stack.setCurrentIndex(self.cards_idx)

    def _on_detail_prev(self):
        if self._detail_index > 0:
            self._detail_index -= 1
            self._render_detail_view()

    def _on_detail_next(self):
        questions = self._current_history_session.get("questions", [])
        if self._detail_index < len(questions) - 1:
            self._detail_index += 1
            self._render_detail_view()

    def _on_back_to_sessions(self):
        self._history_view = "sessions"
        self._tm._train_stack.setCurrentIndex(self.sessions_idx)
        self._refresh_sessions()

    def _on_delete_session(self):
        session = getattr(self, "_current_history_session", None)
        if not session:
            return
        filepath = session.get("_filepath", "")
        if not filepath or not os.path.isfile(filepath):
            return
        result = CustomDialog.question(
            self._mw, "确认删除", "确定要删除这条训练记录吗？此操作不可恢复。",
            buttons=[("否", "no"), ("是", "yes")])
        if result == "yes":
            try:
                os.remove(filepath)
                self._mw._update_status("训练记录已删除")
                self._tm._train_stack.setCurrentIndex(self.sessions_idx)
                self._refresh_sessions()
            except Exception as e:
                CustomDialog.warning(self._mw, "删除失败", str(e))
