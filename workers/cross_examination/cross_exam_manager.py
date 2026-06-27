# -*- coding: utf-8 -*-
"""模拟质询管理器 — UI 构建 + 业务逻辑 + 卡片渲染 + 数据管理

负责:
  - 模拟质询展示页面的 UI 构建（centre_stack 第6页）
  - AI 质询触发、Worker 调度、结果解析与展示
  - 质询卡片构建与网格自适应排列
  - 质询结果持久化（JSON 文件）
  - 历史质询记录的加载与查看
  - 右侧导航按钮创建
"""

import json
import os
import re

from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QScrollArea, QWidget,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from components.popup_dialog import CustomDialog
from components.star_button import StarButton

from .cross_exam_worker import CrossExaminationWorker
from workers.nav_bar.nav_bar_manager import NavBarManager


class CrossExaminationManager:
    """模拟质询完整功能管理器"""

    def __init__(self, mw):
        """mw: StarDebateWindow 主窗口引用"""
        self._mw = mw

        # 页面 UI 引用
        self._page: QWidget | None = None
        self._scroll: QScrollArea | None = None
        self._container: QWidget | None = None
        self._grid: QGridLayout | None = None

        # 导航按钮
        self._btn_nav: QPushButton | None = None
        self._lbl_nav: QLabel | None = None

        # 数据
        self._rounds: list[dict] = []
        self._cards: list[QFrame] = []

        # Worker
        self._worker: CrossExaminationWorker | None = None

        # 重排防抖
        self._reflow_timer: QTimer | None = None
        self._reflow_guard: bool = False

    # ==================== 属性 ====================

    @property
    def rounds(self) -> list[dict]:
        return self._rounds

    @rounds.setter
    def rounds(self, value: list):
        self._rounds = value

    @property
    def cards_scroll(self) -> QScrollArea | None:
        return self._scroll

    @property
    def page_index(self) -> int:
        """返回页面在 centre_stack 中的索引"""
        return 6

    # ==================== UI 构建 ====================

    def build_ui(self) -> int:
        """构建模拟质询页面并添加到 centre_stack，返回页面索引"""
        mw = self._mw

        page = QWidget()
        page.setObjectName("crossExamPage")
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        btn_back = StarButton("← 返回辩论详情", layout_mode="text_only", ratio_h=0.7)
        btn_back.setObjectName("crossExamBackBtn")
        btn_back.clicked.connect(lambda: mw.centre_stack.setCurrentIndex(1))

        btn_refresh = StarButton("刷新页面", layout_mode="text_only", ratio_h=0.7)
        btn_refresh.setObjectName("crossExamRefreshBtn")
        btn_refresh.clicked.connect(self._refresh_page)

        toolbar.addWidget(btn_back)
        toolbar.addStretch()
        toolbar.addWidget(btn_refresh)

        # 质询对话滚动区域
        self._scroll = QScrollArea()
        self._scroll.setObjectName("crossExamScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._container.setObjectName("crossExamContainer")
        self._grid = QGridLayout(self._container)
        self._grid.setContentsMargins(16, 16, 16, 16)
        self._grid.setSpacing(16)
        self._scroll.setWidget(self._container)

        layout.addLayout(toolbar)
        layout.addWidget(self._scroll)

        self._page = page
        mw.centre_stack.addWidget(page)
        # 构建完成后立即刷新以显示初始空状态提示
        self._refresh_page()
        return self.page_index

    def build_nav_button(self):
        """创建右侧导航栏按钮，返回 (btn, label)（支持图标文件）"""
        mw = self._mw
        btn = QPushButton()
        btn.setObjectName("navToggleBtn")
        btn.setToolTip("模拟质询")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(50, 50)
        btn.clicked.connect(self._on_nav_click)

        item = mw._nav_registry.get_item("cross_exam")
        icon = NavBarManager.load_nav_icon(item.icon) if item else None
        if icon is not None:
            NavBarManager._apply_icon_to_button(btn, icon)
        else:
            btn.setText("⚡")

        lbl = QLabel("质询")
        lbl.setObjectName("crossExamNavLabel")
        lbl.setFont(QFont("Microsoft YaHei", 7))
        lbl.setAlignment(Qt.AlignCenter)

        self._btn_nav = btn
        self._lbl_nav = lbl
        return btn, lbl

    # ==================== 导航按钮入口 ====================

    def _on_nav_click(self):
        """右侧导航按钮点击：有历史数据则展示，无数据则自动发起 AI 质询"""
        mw = self._mw
        if not mw.current_debate_path:
            CustomDialog.warning(mw, "提示", "请先在左侧树控件中选择一个辩论文件")
            return
        # 已有质询结果 → 直接展示
        if self._rounds:
            self._refresh_page()
            mw.centre_stack.setCurrentIndex(self.page_index)
            mw._update_status("已切换到模拟质询页面")
            return
        # 无数据 → 自动发起 AI 质询
        self.start_cross_exam()

    def centre_stack(self):
        return self._mw.centre_stack

    # ==================== AI 质询调度 ====================

    def start_cross_exam(self):
        """发起模拟质询（从详情页按钮调用）"""
        mw = self._mw
        if not mw.current_debate_path:
            CustomDialog.warning(mw, "提示", "请先在左侧树控件中选择一个辩论文件")
            return

        # 获取双方一辩稿
        pro_speech = mw._speech_mgr.edit_pro_speech.toPlainText().strip()
        con_speech = mw._speech_mgr.edit_con_speech.toPlainText().strip()
        if not pro_speech and not con_speech:
            mw._speech_mgr._load_speech_from_file("pro")
            mw._speech_mgr._load_speech_from_file("con")
            pro_speech = mw._speech_mgr.edit_pro_speech.toPlainText().strip()
            con_speech = mw._speech_mgr.edit_con_speech.toPlainText().strip()

        if not pro_speech or not con_speech:
            CustomDialog.warning(mw, "缺少一辩稿",
                                "请先为正方和反方创建并保存一辩稿，再发起模拟质询。")
            return

        # 加载资料稿
        mw._ref_doc_mgr.load_data_from_file()

        api_config = mw._load_api_config()
        if not api_config.get("api_key"):
            ptype = api_config.get("provider_type", "auto")
            if ptype not in ("auto", "web"):
                CustomDialog.warning(mw, "缺少 API Key",
                                    "请在 api_config.json 中填写您的 DeepSeek API Key 再使用此功能。")
                return
            # auto/web 无 key 时静默跳过，由 _resolve_provider_type 回退到 Web

        debate_title = ""
        if mw.current_debate_data:
            pro = mw.current_debate_data.get("pro", "")
            con = mw.current_debate_data.get("con", "")
            debate_title = f"{pro} vs {con}"

        mw._ai_loading_bar.show_loading("AI正在模拟质询…")

        self._worker = CrossExaminationWorker(
            api_config, pro_speech, con_speech,
            mw._ref_doc_mgr.ref_doc_rows, mw._ref_doc_mgr.ref_doc_rows, debate_title
        )
        self._worker.finished.connect(self._on_finished)
        self._worker.start()
        mw._update_status("模拟质询已启动，AI 正在分析...")

    def _cleanup_worker(self):
        """取消/清理质询线程"""
        if self._worker:
            self._worker.terminate()
            self._worker = None

    def _on_finished(self, success: bool, _side: str, result_text: str):
        """质询完成回调"""
        mw = self._mw
        mw._ai_loading_bar.hide_loading()

        if not success:
            CustomDialog.error(mw, "质询模拟失败",
                                 f"AI 模拟质询失败:\n{result_text}")
            mw._update_status("模拟质询失败")
            return

        rounds = self._parse_result(result_text)
        if not rounds:
            CustomDialog.error(mw, "解析失败",
                                 "AI 返回的内容格式异常，无法解析为质询数据。\n请稍后重试。")
            mw._update_status("模拟质询解析失败")
            return

        self._rounds = rounds
        self._save_result(rounds)
        self._refresh_page()
        mw.centre_stack.setCurrentIndex(self.page_index)
        mw._update_status(f"模拟质询完成（{len(rounds)} 轮）")

    # ==================== 结果解析与持久化 ====================

    @staticmethod
    def _parse_result(text: str) -> list:
        """解析 AI 返回的 JSON，提取 rounds 列表"""
        text = text.strip()
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            text = m.group(1)
        try:
            data = json.loads(text)
            rounds = data.get("rounds", [])
            return rounds if isinstance(rounds, list) else []
        except json.JSONDecodeError:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start:end + 1])
                rounds = data.get("rounds", [])
                return rounds if isinstance(rounds, list) else []
            except json.JSONDecodeError:
                pass
        return []

    def _get_filename(self) -> str | None:
        """生成质询模拟文件路径"""
        mw = self._mw
        if not mw.current_debate_path:
            return None
        dir_name = os.path.dirname(mw.current_debate_path)
        base = os.path.splitext(os.path.basename(mw.current_debate_path))[0]
        return os.path.join(dir_name, f"{base}_质询模拟.json")

    def _save_result(self, rounds: list):
        """保存质询结果到 JSON 文件"""
        mw = self._mw
        save_file = self._get_filename()
        if not save_file:
            return
        data = {
            "rounds": rounds,
            "debate_title": (
                f"{mw.current_debate_data.get('pro', '')} vs {mw.current_debate_data.get('con', '')}"
                if mw.current_debate_data else ""
            ),
        }
        try:
            os.makedirs(os.path.dirname(save_file), exist_ok=True)
            with open(save_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            project_path = mw._get_current_project_path()
            if project_path:
                mw._build_tree_from_path(project_path)
            mw._update_status(f"质询结果已保存: {os.path.basename(save_file)}")
        except OSError as e:
            CustomDialog.error(mw, "保存失败", f"无法保存质询结果:\n{str(e)}")

    # ==================== 页面刷新与卡片 ====================

    def _refresh_page(self):
        """刷新质询展示页面"""
        self._clear_grid()

        if not self._rounds:
            empty_label = QLabel("暂无质询数据\n请点击右侧「⚡」按钮或辩论详情页的「模拟质询」发起 AI 质询")
            empty_label.setObjectName("crossExamEmpty")
            empty_label.setFont(QFont("Microsoft YaHei", 13))
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setWordWrap(True)
            empty_label.setFixedHeight(80)
            self._grid.addWidget(empty_label, 0, 0)
            return

        self._build_cards()
        QTimer.singleShot(0, self._arrange_cards)

    def _clear_grid(self):
        """清空质询网格中所有 widget"""
        grid = self._grid
        while grid.count():
            item = grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _build_cards(self):
        """创建质询卡片列表，存入 self._cards"""
        cards = []
        for round_data in self._rounds:
            if not isinstance(round_data, dict):
                continue
            round_num = round_data.get("round", "?")
            side = round_data.get("side", "正方")
            question = round_data.get("question", "")
            answer = round_data.get("answer", "")
            thinking = round_data.get("thinking", "")

            round_frame = QFrame()
            round_frame.setObjectName("crossExamRound")
            round_frame.setMinimumWidth(360)
            round_layout = QVBoxLayout(round_frame)
            round_layout.setSpacing(8)
            round_layout.setContentsMargins(12, 10, 12, 10)

            # 轮次信息条
            hdr_layout = QHBoxLayout()
            lbl_round = QLabel(f"第 {round_num} 轮 — 质询{side}")
            lbl_round.setObjectName("crossExamRoundLabel")
            lbl_round.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
            hdr_layout.addWidget(lbl_round)
            hdr_layout.addStretch()

            # 问题气泡
            q_frame = QFrame()
            q_frame.setObjectName("crossExamQuestion")
            q_layout = QVBoxLayout(q_frame)
            q_layout.setContentsMargins(14, 10, 14, 10)
            q_label = QLabel("❓ 质询问题")
            q_label.setObjectName("crossExamQLabel")
            q_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
            q_content = QLabel(question)
            q_content.setObjectName("crossExamQContent")
            q_content.setFont(QFont("Microsoft YaHei", 12))
            q_content.setWordWrap(True)
            q_layout.addWidget(q_label)
            q_layout.addWidget(q_content)

            # 回答气泡
            a_frame = QFrame()
            a_frame.setObjectName("crossExamAnswer")
            a_layout = QVBoxLayout(a_frame)
            a_layout.setContentsMargins(14, 10, 14, 10)
            a_label = QLabel("💬 辩手回答")
            a_label.setObjectName("crossExamALabel")
            a_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
            a_content = QLabel(answer)
            a_content.setObjectName("crossExamAContent")
            a_content.setFont(QFont("Microsoft YaHei", 12))
            a_content.setWordWrap(True)
            a_layout.addWidget(a_label)
            a_layout.addWidget(a_content)

            # 思路解析
            t_frame = QFrame()
            t_frame.setObjectName("crossExamThinking")
            t_layout = QVBoxLayout(t_frame)
            t_layout.setContentsMargins(14, 10, 14, 10)
            t_label = QLabel("🧠 思路解析")
            t_label.setObjectName("crossExamTLabel")
            t_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
            t_content = QLabel(thinking)
            t_content.setObjectName("crossExamTContent")
            t_content.setFont(QFont("Microsoft YaHei", 11))
            t_content.setWordWrap(True)
            t_layout.addWidget(t_label)
            t_layout.addWidget(t_content)

            round_layout.addLayout(hdr_layout)
            round_layout.addWidget(q_frame)
            round_layout.addWidget(a_frame)
            round_layout.addWidget(t_frame)

            cards.append(round_frame)
        self._cards = cards

    def _arrange_cards(self):
        """根据容器宽度智能选择 1 或 2 列排布卡片"""
        if self._reflow_guard:
            return
        self._reflow_guard = True
        try:
            cards = self._cards
            grid = self._grid

            container_width = self._scroll.viewport().width()
            if container_width <= 0:
                container_width = self._scroll.width()
            margins = grid.contentsMargins()
            avail_w = container_width - margins.left() - margins.right()
            spacing = grid.spacing()

            MIN_TWO_COL = 700
            cols = 2 if avail_w >= MIN_TWO_COL else 1

            self._clear_grid()
            if not cards:
                return

            if cols == 1:
                actual_card_w = max(360, avail_w)
            else:
                actual_card_w = max(300, (avail_w - (cols - 1) * spacing) // cols)

            for col in range(cols):
                grid.setColumnStretch(col, 1)

            for i, card in enumerate(cards):
                row = i // cols
                col = i % cols
                card.setFixedWidth(actual_card_w)
                card.adjustSize()
                grid.addWidget(card, row, col)

            total = len(cards)
            last_row = (total - 1) // cols if total > 0 else 0
            grid.setRowStretch(last_row + 1, 1)

            QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
                self._scroll.verticalScrollBar().maximum()
            ))
        finally:
            self._reflow_guard = False

    # ==================== 树控件点击处理 ====================

    def handle_tree_click(self, file_path: str, data: dict):
        """从树控件点击加载质询结果"""
        mw = self._mw
        mw._derive_debate_path(file_path, "_质询模拟")
        rounds = data.get("rounds", [])
        self._rounds = rounds if isinstance(rounds, list) else []
        self._refresh_page()
        mw.centre_stack.setCurrentIndex(self.page_index)
        mw._update_status(f"已加载质询模拟: {os.path.basename(file_path)}")

    def load_stardebate_data(self, data: dict):
        """从 .stardebate 加载质询数据。

        Args:
            data: {"rounds": [...]}
        """
        rounds = data.get("rounds", [])
        self._rounds = rounds if isinstance(rounds, list) else []
        self._refresh_page()
        self._mw.centre_stack.setCurrentIndex(self.page_index)
        self._mw._update_status("已加载质询模拟 [.stardebate]")

    # ====================事件过滤委托 ====================

    def handle_event_filter(self, obj, event) -> bool:
        """处理与质询卡片区域相关的 resize 事件"""
        if event.type() == event.Resize:
            if obj is self._scroll:
                if self._mw.centre_stack.currentIndex() == self.page_index and self._cards:
                    if self._reflow_timer is None:
                        self._reflow_timer = QTimer(self._mw)
                        self._reflow_timer.setSingleShot(True)
                        self._reflow_timer.timeout.connect(self._arrange_cards)
                    self._reflow_timer.start(80)
        return False
