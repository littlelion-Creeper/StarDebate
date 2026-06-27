from components.theme_colors import tc, refresh
# -*- coding: utf-8 -*-
"""模拟接质管理器 — UI 构建 + 业务逻辑 + 聊天界面 + 数据管理

负责:
  - 模拟接质聊天页面的 UI 构建（centre_stack 第7页）
  - 持方选择、AI 初始化（生成一辩稿 + 首问）
  - 用户回答 → AI 评分 → 下一问 的完整交互流程
  - 聊天气泡管理（speech/ai/question/score/system）
  - 接质结果持久化（JSON 文件）
  - 历史接质记录的加载与回看
  - 右侧导航按钮创建
"""

import json
import os

from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QWidget, QTextEdit,
)

from components.star_button import StarButton
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from components.popup_dialog import CustomDialog

from .accept_exam_worker import AcceptExaminationWorker
from workers.nav_bar.nav_bar_manager import NavBarManager


class AcceptExaminationManager:
    """模拟接质完整功能管理器"""

    def __init__(self, mw):
        """mw: StarDebateWindow 主窗口引用"""
        self._mw = mw

        # 页面 UI 引用
        self._page: QWidget | None = None
        self._chat_scroll: QScrollArea | None = None
        self._chat_container: QWidget | None = None
        self._chat_layout: QVBoxLayout | None = None
        self._input_frame: QFrame | None = None
        self._input_edit: QTextEdit | None = None
        self._score_bar: QFrame | None = None
        self._score_label: QLabel | None = None

        # 按钮引用
        self._btn_nav: QPushButton | None = None
        self._lbl_nav: QLabel | None = None
        self._btn_start: StarButton | None = None
        self._btn_send: StarButton | None = None
        self._btn_end: StarButton | None = None
        self._btn_side_pro: StarButton | None = None
        self._btn_side_con: StarButton | None = None

        # 状态
        self._state: str = "idle"
        self._user_side: str = ""
        self._messages: list[dict] = []
        self._scores: list[int] = []
        self._round: int = 0

        # Worker
        self._worker: AcceptExaminationWorker | None = None

    # ==================== 属性 ====================

    @property
    def state(self) -> str:
        return self._state

    @property
    def user_side(self) -> str:
        return self._user_side

    @property
    def page_index(self) -> int:
        return 7

    # ==================== UI 构建 ====================

    def build_ui(self) -> int:
        """构建模拟接质页面并添加到 centre_stack，返回页面索引"""
        mw = self._mw

        page = QWidget()
        page.setObjectName("acceptExamPage")
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        btn_back = StarButton("← 返回辩论详情")
        # btn_back.setFixedSize(130, 32)
        btn_back.clicked.connect(lambda: mw.centre_stack.setCurrentIndex(1))

        # 持方切换
        self._btn_side_pro = StarButton("🟢 我是正方", checkable=True, checked=True)
        self._btn_side_pro.setObjectName("sideToggleBtn")
        # self._btn_side_pro.setFixedSize(110, 32)
        self._btn_side_pro.clicked.connect(lambda: self._on_side_toggle("pro"))

        self._btn_side_con = StarButton("🔴 我是反方", checkable=True)
        self._btn_side_con.setObjectName("sideToggleBtn")
        # self._btn_side_con.setFixedSize(110, 32)
        self._btn_side_con.clicked.connect(lambda: self._on_side_toggle("con"))

        # 开始按钮
        self._btn_start = StarButton("开始接质训练")
        self._btn_start.setObjectName("primaryBtn")
        # self._btn_start.setFixedSize(130, 32)
        self._btn_start.clicked.connect(self._on_start)

        toolbar.addWidget(btn_back)
        toolbar.addStretch()
        toolbar.addWidget(self._btn_side_pro)
        toolbar.addWidget(self._btn_side_con)
        toolbar.addStretch()
        toolbar.addWidget(self._btn_start)
        toolbar.addStretch()

        # 聊天消息滚动区域
        self._chat_scroll = QScrollArea()
        self._chat_scroll.setObjectName("acceptChatScroll")
        self._chat_scroll.setWidgetResizable(True)
        self._chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._chat_container = QWidget()
        self._chat_container.setObjectName("acceptChatContainer")
        self._chat_layout = QVBoxLayout(self._chat_container)
        self._chat_layout.setContentsMargins(10, 10, 10, 10)
        self._chat_layout.setSpacing(12)
        self._chat_layout.addStretch()
        self._chat_scroll.setWidget(self._chat_container)

        # 分数摘要栏
        self._score_bar = QFrame()
        self._score_bar.setObjectName("acceptScoreBar")
        self._score_bar.setFixedHeight(44)
        self._score_bar.setVisible(False)
        score_bar_layout = QHBoxLayout(self._score_bar)
        score_bar_layout.setContentsMargins(16, 4, 16, 4)
        self._score_label = QLabel("接质成绩")
        self._score_label.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        self._score_label.setStyleSheet(f"color: {tc("accent_yellow")};")
        score_bar_layout.addWidget(self._score_label)
        score_bar_layout.addStretch()

        # 底部输入区域
        self._input_frame = QFrame()
        self._input_frame.setObjectName("acceptInputFrame")
        self._input_frame.setFixedHeight(120)
        input_layout = QVBoxLayout(self._input_frame)
        input_layout.setContentsMargins(12, 8, 12, 8)
        input_layout.setSpacing(6)

        self._input_edit = QTextEdit()
        self._input_edit.setObjectName("textEdit")
        self._input_edit.setPlaceholderText("在此输入你的接质回答...")
        self._input_edit.setMinimumHeight(60)
        self._input_edit.setFont(QFont("Microsoft YaHei", 11))
        self._input_edit.setEnabled(False)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self._btn_send = StarButton("发送回答", ratio_mode="h_only", ratio_h=0.7)
        self._btn_send.setObjectName("primaryBtn")
        self._btn_send.setFixedHeight(32)
        self._btn_send.setMinimumWidth(120)
        self._btn_send.clicked.connect(self._on_send)
        self._btn_send.setEnabled(False)

        self._btn_end = StarButton("结束接质", ratio_mode="h_only", ratio_h=0.7)
        self._btn_end.setFixedHeight(32)
        self._btn_end.setMinimumWidth(110)
        self._btn_end.clicked.connect(self._on_end)
        self._btn_end.setEnabled(False)

        btn_row.addWidget(self._btn_send)
        btn_row.addWidget(self._btn_end)

        input_layout.addWidget(self._input_edit)
        input_layout.addLayout(btn_row)

        layout.addLayout(toolbar)
        layout.addWidget(self._chat_scroll)
        layout.addWidget(self._score_bar)
        layout.addWidget(self._input_frame)

        self._page = page
        mw.centre_stack.addWidget(page)
        return self.page_index

    def build_nav_button(self):
        """创建右侧导航栏按钮，返回 (btn, label)（支持图标文件）"""
        mw = self._mw
        btn = QPushButton()
        btn.setObjectName("navToggleBtn")
        btn.setToolTip("模拟接质")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(50, 50)
        btn.clicked.connect(self._on_nav_click)

        item = mw._nav_registry.get_item("accept_exam")
        icon = NavBarManager.load_nav_icon(item.icon) if item else None
        if icon is not None:
            NavBarManager._apply_icon_to_button(btn, icon)
        else:
            btn.setText("🛡️")

        lbl = QLabel("接质")
        lbl.setObjectName("acceptExamNavLabel")
        lbl.setFont(QFont("Microsoft YaHei", 7))
        lbl.setAlignment(Qt.AlignCenter)

        self._btn_nav = btn
        self._lbl_nav = lbl
        return btn, lbl

    def _on_nav_click(self):
        """右侧导航按钮点击"""
        self.open_page()

    def open_page(self):
        """打开接质页面并初始化状态"""
        mw = self._mw
        if not mw.current_debate_path:
            CustomDialog.warning(mw, "提示", "请先在左侧树控件中选择一个辩论文件")
            return

        self._state = "idle"
        self._messages = []
        self._scores = []
        self._round = 0
        self._user_side = "pro"

        self._input_frame.setVisible(True)
        self._btn_side_pro.setChecked(True)
        self._btn_side_con.setChecked(False)
        self._btn_start.setEnabled(True)
        self._btn_start.setVisible(True)
        self._btn_send.setEnabled(False)
        self._btn_end.setEnabled(False)
        self._input_edit.setEnabled(False)
        self._input_edit.clear()
        self._score_bar.setVisible(False)
        self._clear_chat()
        self._add_empty_hint()

        mw.centre_stack.setCurrentIndex(self.page_index)
        mw._update_status("模拟接质 - 请选择持方并开始训练")

    # ==================== 持方切换 ====================

    def _on_side_toggle(self, side: str):
        mw = self._mw
        if self._state != "idle":
            CustomDialog.information(mw, "提示",
                                    "接质训练已开始，无法切换持方。请结束当前训练后重试。")
            self._btn_side_pro.setChecked(self._user_side == "pro")
            self._btn_side_con.setChecked(self._user_side == "con")
            return
        self._user_side = side
        self._btn_side_pro.setChecked(side == "pro")
        self._btn_side_con.setChecked(side == "con")
        label = "正方" if side == "pro" else "反方"
        mw._update_status(f"模拟接质 - 已选择{label}持方")

    # ==================== 训练启动 ====================

    def _on_start(self):
        """开始接质训练：AI 生成一辩稿 + 首问"""
        mw = self._mw
        if not mw.current_debate_path:
            return

        pro_speech = mw._speech_mgr.edit_pro_speech.toPlainText().strip()
        con_speech = mw._speech_mgr.edit_con_speech.toPlainText().strip()
        if not pro_speech and not con_speech:
            mw._speech_mgr._load_speech_from_file("pro")
            mw._speech_mgr._load_speech_from_file("con")
            pro_speech = mw._speech_mgr.edit_pro_speech.toPlainText().strip()
            con_speech = mw._speech_mgr.edit_con_speech.toPlainText().strip()

        api_config = mw._load_api_config()
        if not api_config.get("api_key"):
            CustomDialog.warning(mw, "缺少 API Key",
                                "请在 api_config.json 中填写您的 DeepSeek API Key 再使用此功能。")
            return

        debate_title = ""
        if mw.current_debate_data:
            pro = mw.current_debate_data.get("pro", "")
            con = mw.current_debate_data.get("con", "")
            debate_title = f"{pro} vs {con}"

        self._input_frame.setVisible(True)
        self._btn_start.setEnabled(False)
        self._btn_start.setVisible(False)
        self._btn_side_pro.setEnabled(False)
        self._btn_side_con.setEnabled(False)

        self._clear_chat()
        self._state = "initializing"
        self._messages = []
        self._scores = []
        self._round = 0

        mw._ai_loading_bar.show_loading("AI正在初始化接质训练…")

        side_label = "正方" if self._user_side == "pro" else "反方"
        self._add_chat_bubble("system", f"🛡️ 模拟接质训练开始\n持方：{side_label}\n辩题：{debate_title}")

        self._worker = AcceptExaminationWorker(
            api_config, "init", self._user_side,
            debate_title, pro_speech, con_speech
        )
        self._worker.finished.connect(self._on_init_finished)
        self._worker.start()
        mw._update_status("模拟接质 - AI 正在初始化...")

    def _on_init_finished(self, success: bool, side: str, result: dict):
        """初始化完成回调"""
        mw = self._mw
        mw._ai_loading_bar.hide_loading()

        if not success:
            err = result.get("error", "未知错误")
            CustomDialog.error(mw, "初始化失败", f"模拟接质初始化失败:\n{err}")
            self._state = "idle"
            self._btn_start.setEnabled(True)
            self._btn_start.setVisible(True)
            self._btn_side_pro.setEnabled(True)
            self._btn_side_con.setEnabled(True)
            mw._update_status("模拟接质初始化失败")
            return

        speech_content = result.get("speech_content", "")
        if speech_content:
            speech_text = f"📜 {result.get('speech_title', '一辩稿大纲')}\n\n{speech_content}"
            self._add_chat_bubble("speech", speech_text)
            self._messages.append({"role": "speech", "content": speech_content})

        question = result.get("question", "")
        question_tip = result.get("question_tip", "")
        if question:
            q_text = f"❓ {question}"
            if question_tip:
                q_text += f"\n\n💡 质询方向：{question_tip}"
            self._add_chat_bubble("ai", q_text)
            self._messages.append({
                "role": "ai_question", "content": question,
                "question_tip": question_tip
            })

        self._state = "waiting_answer"
        self._round = 1
        self._input_edit.setEnabled(True)
        self._input_edit.setPlaceholderText("在此输入你的接质回答...")
        self._btn_send.setEnabled(True)
        self._btn_end.setEnabled(True)
        self._btn_start.setVisible(False)
        self._score_bar.setVisible(False)
        self._score_label.setText("接质成绩")
        mw._update_status("模拟接质 - 等待回答（第1轮）")

    # ==================== 发送回答 ====================

    def _on_send(self):
        """用户发送接质回答"""
        mw = self._mw
        if self._state != "waiting_answer":
            return

        answer = self._input_edit.toPlainText().strip()
        if not answer:
            CustomDialog.warning(mw, "提示", "请输入你的接质回答")
            return

        round_label = f"📍 第 {self._round} 轮回答"
        self._add_chat_bubble("user", f"{round_label}\n\n{answer}")
        self._messages.append({
            "role": "user_answer", "content": answer,
            "round": self._round
        })

        self._input_edit.clear()
        self._input_edit.setEnabled(False)
        self._btn_send.setEnabled(False)
        self._btn_end.setEnabled(False)

        self._state = "scoring"

        api_config = mw._load_api_config()
        pro_speech = mw._speech_mgr.edit_pro_speech.toPlainText().strip()
        con_speech = mw._speech_mgr.edit_con_speech.toPlainText().strip()
        debate_title = ""
        if mw.current_debate_data:
            pro = mw.current_debate_data.get("pro", "")
            con = mw.current_debate_data.get("con", "")
            debate_title = f"{pro} vs {con}"

        self._worker = AcceptExaminationWorker(
            api_config, "respond", self._user_side,
            debate_title, pro_speech, con_speech,
            messages=self._messages,
            user_answer=answer,
            round_num=self._round
        )
        self._worker.finished.connect(self._on_respond_finished)
        self._worker.start()
        self._add_chat_bubble("system", "⏳ AI 正在评分...")
        mw._update_status(f"模拟接质 - AI 正在评分（第{self._round}轮）")

    def _on_respond_finished(self, success: bool, side: str, result: dict):
        """评分完成回调"""
        mw = self._mw
        if not success:
            err = result.get("error", "未知错误")
            self._add_chat_bubble("system", f"❌ 评分失败: {err}")
            self._state = "waiting_answer"
            self._input_edit.setEnabled(True)
            self._btn_send.setEnabled(True)
            self._btn_end.setEnabled(True)
            mw._update_status("模拟接质 - 评分失败，请重试")
            return

        self._remove_last_temp_bubble()

        score = result.get("score", -1)
        feedback = result.get("feedback", "")
        next_question = result.get("next_question", "")
        question_tip = result.get("question_tip", "")
        is_end = result.get("is_end", False)

        if score >= 0:
            self._scores.append(score)
            score_text = f"⭐ AI评分：{score}/10分\n\n📝 点评：{feedback}"
            self._add_chat_bubble("score", score_text)
            self._messages.append({
                "role": "ai_score", "content": f"{score}/10",
                "round": self._round
            })
            self._messages.append({
                "role": "feedback", "content": feedback,
                "round": self._round
            })

        if self._scores:
            avg = sum(self._scores) / len(self._scores)
            self._score_label.setText(
                f"接质成绩 | 第{self._round}轮: {score}分 | 平均: {avg:.1f}分"
            )
            self._score_bar.setVisible(True)

        if is_end:
            if self._scores:
                avg = sum(self._scores) / len(self._scores)
                self._add_chat_bubble("system",
                    f"🏁 第{self._round}轮评分完成。AI 建议结束接质。\n"
                    f"当前成绩：共{len(self._scores)}轮，平均 {avg:.1f} 分\n"
                    f"请点击「结束接质」查看综合总结。"
                )
            self._state = "ended"
            self._input_edit.setEnabled(False)
            self._btn_send.setEnabled(False)
            self._btn_end.setEnabled(True)
            mw._update_status("模拟接质 - AI 建议结束")
        else:
            if next_question:
                q_text = f"❓ {next_question}"
                if question_tip:
                    q_text += f"\n\n💡 质询方向：{question_tip}"
                self._add_chat_bubble("ai", q_text)
                self._messages.append({
                    "role": "ai_question", "content": next_question,
                    "question_tip": question_tip,
                    "round": self._round + 1
                })

            self._state = "waiting_answer"
            self._round += 1
            self._input_edit.setEnabled(True)
            self._input_edit.setPlaceholderText(f"在此输入你第 {self._round} 轮的接质回答...")
            self._btn_send.setEnabled(True)
            self._btn_end.setEnabled(True)
            mw._update_status(f"模拟接质 - 等待回答（第{self._round}轮）")

    # ==================== 结束接质 ====================

    def _on_end(self):
        """用户主动结束接质"""
        mw = self._mw
        if self._state not in ("waiting_answer", "ended"):
            return

        self._input_edit.setEnabled(False)
        self._btn_send.setEnabled(False)
        self._btn_end.setEnabled(False)
        self._state = "finalizing"

        self._add_chat_bubble("system", "🏁 正在生成综合总结...")

        api_config = mw._load_api_config()
        pro_speech = mw._speech_mgr.edit_pro_speech.toPlainText().strip()
        con_speech = mw._speech_mgr.edit_con_speech.toPlainText().strip()
        debate_title = ""
        if mw.current_debate_data:
            pro = mw.current_debate_data.get("pro", "")
            con = mw.current_debate_data.get("con", "")
            debate_title = f"{pro} vs {con}"

        self._worker = AcceptExaminationWorker(
            api_config, "end", self._user_side,
            debate_title, pro_speech, con_speech,
            messages=self._messages,
            round_num=self._round
        )
        self._worker.finished.connect(self._on_end_finished)
        self._worker.start()
        mw._update_status("模拟接质 - 正在生成总结...")

    def _on_end_finished(self, success: bool, side: str, result: dict):
        """结束总结完成回调"""
        mw = self._mw
        if not success:
            self._add_chat_bubble("system", "❌ 生成总结失败，请重试")
            self._state = "waiting_answer"
            self._input_edit.setEnabled(True)
            self._btn_send.setEnabled(True)
            self._btn_end.setEnabled(True)
            return

        total_score = result.get("total_score", -1)
        summary = result.get("summary", "")
        highlights = result.get("highlights", "")
        improvements = result.get("improvements", "")
        advice = result.get("advice", "")

        summary_lines = ["🎓 接质训练综合总结", "", f"📊 综合评分：{total_score}/100分"]
        if self._scores:
            avg = sum(self._scores) / len(self._scores)
            summary_lines.append(f"📈 总计{len(self._scores)}轮，单轮均分：{avg:.1f}/10")
        summary_lines.extend(["", f"📝 总体评价：{summary}"])
        if highlights:
            summary_lines.append(f"\n✨ 接质亮点：{highlights}")
        if improvements:
            summary_lines.append(f"\n🔧 改进方向：{improvements}")
        if advice:
            summary_lines.append(f"\n💡 训练建议：{advice}")

        summary_text = "\n".join(summary_lines)
        self._add_chat_bubble("score", summary_text)
        self._messages.append({
            "role": "end_summary", "content": summary_text,
            "total_score": total_score
        })

        if self._scores:
            avg = sum(self._scores) / len(self._scores)
            self._score_label.setText(
                f"接质成绩 | 综合: {total_score}分 | {len(self._scores)}轮均分: {avg:.1f}"
            )
            self._score_bar.setVisible(True)

        self._save_result()
        self._state = "ended"
        self._input_frame.setVisible(False)
        self._btn_start.setVisible(True)
        self._btn_start.setEnabled(False)
        self._btn_start.setText("🔄 重新开始")
        self._btn_side_pro.setEnabled(True)
        self._btn_side_con.setEnabled(True)
        mw._update_status(f"模拟接质 - 完成（综合评分: {total_score}）")

        CustomDialog.information(mw, "接质训练完成",
            f"接质训练已结束！\n\n综合评分：{total_score}/100分\n"
            f"总轮次：{len(self._scores)}轮\n\n训练记录已保存到JSON文件。")

    # ==================== Worker 清理 ====================

    def _cleanup_worker(self):
        """取消/清理接质线程"""
        if self._worker:
            self._worker.terminate()
            self._worker = None

    # ==================== 聊天 UI 方法 ====================

    def _clear_chat(self):
        """清空聊天区域"""
        layout = self._chat_layout
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clean_layout_recursive(item.layout())

    def _add_chat_bubble(self, role: str, text: str):
        """添加聊天气泡"""
        bubble = QFrame()
        content = QLabel(text)
        content.setFont(QFont("Microsoft YaHei", 11))
        content.setWordWrap(True)

        v_layout = QVBoxLayout(bubble)
        v_layout.setContentsMargins(14, 10, 14, 10)
        v_layout.addWidget(content)

        h_wrap = QHBoxLayout()
        if role == "user":
            bubble.setObjectName("acceptMsgUser")
            content.setStyleSheet(f"color: {tc("text")};")
            h_wrap.addStretch()
            h_wrap.addWidget(bubble, 3)
        elif role == "ai":
            bubble.setObjectName("acceptMsgAI")
            content.setStyleSheet(f"color: {tc("text")};")
            h_wrap.addWidget(bubble, 3)
            h_wrap.addStretch()
        elif role == "score":
            bubble.setObjectName("acceptMsgScore")
            content.setStyleSheet(f"color: {tc("text")};")
            h_wrap.addWidget(bubble, 3)
            h_wrap.addStretch()
        elif role == "speech":
            bubble.setObjectName("acceptMsgSpeech")
            content.setStyleSheet(f"color: {tc("text")};")
            h_wrap.addWidget(bubble, 3)
            h_wrap.addStretch()
        else:  # system
            bubble.setObjectName("acceptMsgSystem")
            content.setStyleSheet(f"color: {tc("subtext")};")
            h_wrap.addWidget(bubble, 2)
            h_wrap.addStretch()

        layout = self._chat_layout
        layout.insertLayout(layout.count() - 1, h_wrap)

        QTimer.singleShot(50, lambda: self._chat_scroll.verticalScrollBar().setValue(
            self._chat_scroll.verticalScrollBar().maximum()
        ))

    def _add_empty_hint(self):
        """添加空状态提示"""
        hint = QLabel("尚未开始接质训练\n请选择持方后点击「开始接质训练」按钮")
        hint.setObjectName("acceptChatEmpty")
        hint.setFont(QFont("Microsoft YaHei", 13))
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        hint.setFixedHeight(80)
        layout = self._chat_layout
        layout.insertWidget(layout.count() - 1, hint)

    def _remove_last_temp_bubble(self):
        """移除最后一个临时消息气泡"""
        layout = self._chat_layout
        if layout.count() >= 2:
            idx = layout.count() - 2
            item = layout.itemAt(idx)
            if item:
                if item.layout():
                    sub = item.layout()
                    while sub.count():
                        si = sub.takeAt(0)
                        if si.widget():
                            si.widget().deleteLater()
                    self._clean_layout_recursive(sub)
                    layout.removeItem(item)
                elif item.widget():
                    item.widget().deleteLater()
                    layout.removeItem(item)

    @staticmethod
    def _clean_layout_recursive(layout):
        """递归清理布局"""
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                AcceptExaminationManager._clean_layout_recursive(item.layout())

    # ==================== 持久化 ====================

    def _get_filename(self) -> str | None:
        """生成接质模拟文件路径"""
        mw = self._mw
        if not mw.current_debate_path:
            return None
        dir_name = os.path.dirname(mw.current_debate_path)
        base = os.path.splitext(os.path.basename(mw.current_debate_path))[0]
        side_label = "正方" if self._user_side == "pro" else "反方"
        return os.path.join(dir_name, f"{base}_接质模拟_{side_label}.json")

    def _save_result(self):
        """保存接质结果到 JSON 文件"""
        mw = self._mw
        save_file = self._get_filename()
        if not save_file:
            return
        data = {
            "user_side": "正方" if self._user_side == "pro" else "反方",
            "debate_title": (
                f"{mw.current_debate_data.get('pro', '')} vs {mw.current_debate_data.get('con', '')}"
                if mw.current_debate_data else ""
            ),
            "total_rounds": len(self._scores),
            "scores": self._scores,
            "average_score": (
                round(sum(self._scores) / len(self._scores), 1)
                if self._scores else 0
            ),
            "messages": self._messages,
        }
        try:
            os.makedirs(os.path.dirname(save_file), exist_ok=True)
            with open(save_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            project_path = mw._get_current_project_path()
            if project_path:
                mw._build_tree_from_path(project_path)
            mw._update_status(f"接质结果已保存: {os.path.basename(save_file)}")
        except OSError as e:
            CustomDialog.error(mw, "保存失败", f"无法保存接质结果:\n{str(e)}")

    # ==================== 树控件点击处理 ====================

    def handle_tree_click(self, file_path: str) -> bool:
        """从树控件点击加载接质结果，返回是否成功加载"""
        mw = self._mw
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._messages = data.get("messages", [])
            self._scores = data.get("scores", [])
            user_side_text = data.get("user_side", "正方")
            self._user_side = "pro" if user_side_text == "正方" else "con"

            self._btn_start.setEnabled(False)
            self._btn_start.setVisible(True)
            self._btn_start.setText("🔄 重新开始")
            self._btn_side_pro.setEnabled(True)
            self._btn_side_con.setEnabled(True)
            self._btn_side_pro.setChecked(self._user_side == "pro")
            self._btn_side_con.setChecked(self._user_side == "con")
            self._btn_send.setEnabled(False)
            self._btn_end.setEnabled(False)
            self._input_edit.setEnabled(False)
            self._input_edit.clear()

            self._input_frame.setVisible(False)
            self._clear_chat()

            for msg in self._messages:
                role = msg.get("role", "")
                if role == "speech":
                    self._add_chat_bubble("speech", f"📜 一辩稿大纲\n\n{msg.get('content', '')}")
                elif role == "ai_question":
                    q_text = f"❓ {msg.get('content', '')}"
                    tip = msg.get("question_tip", "")
                    if tip:
                        q_text += f"\n\n💡 质询方向：{tip}"
                    self._add_chat_bubble("ai", q_text)
                elif role == "user_answer":
                    rnd = msg.get("round", "?")
                    self._add_chat_bubble("user", f"📍 第 {rnd} 轮回答\n\n{msg.get('content', '')}")
                elif role == "ai_score":
                    pass
                elif role == "feedback":
                    rnd = msg.get("round", "?")
                    score_val = ""
                    for s_msg in self._messages:
                        if s_msg.get("role") == "ai_score" and s_msg.get("round") == rnd:
                            score_val = s_msg.get("content", "")
                            break
                    self._add_chat_bubble("score", f"⭐ AI评分：{score_val}\n\n📝 点评：{msg.get('content', '')}")
                elif role == "end_summary":
                    self._add_chat_bubble("score", msg.get("content", ""))

            if self._scores:
                avg = sum(self._scores) / len(self._scores)
                self._score_label.setText(f"接质成绩 | {len(self._scores)}轮均分: {avg:.1f}")
                self._score_bar.setVisible(True)

            self._state = "ended"
            mw.centre_stack.setCurrentIndex(self.page_index)
            mw._update_status(f"已加载接质记录: {os.path.basename(file_path)}")
            return True
        except (json.JSONDecodeError, OSError) as e:
            mw._update_status(f"加载接质记录失败: {str(e)}")
            return False

    def load_stardebate_data(self, data: dict):
        """从 .stardebate 加载接质数据。

        Args:
            data: {"messages": [...], "scores": [...], "user_side": "正方"}
        """
        mw = self._mw
        self._messages = data.get("messages", [])
        self._scores = data.get("scores", [])
        user_side_text = data.get("user_side", "正方")
        self._user_side = "pro" if user_side_text == "正方" else "con"

        self._btn_start.setEnabled(False)
        self._btn_start.setVisible(True)
        self._btn_start.setText("🔄 重新开始")
        self._btn_side_pro.setEnabled(True)
        self._btn_side_con.setEnabled(True)
        self._input_edit.setEnabled(False)
        self._input_edit.clear()
        self._input_frame.setVisible(False)
        self._clear_chat()

        for msg in self._messages:
            role = msg.get("role", "")
            if role == "speech":
                self._add_chat_bubble("speech", f"📜 一辩稿大纲\n\n{msg.get('content', '')}")
            elif role == "ai_question":
                q_text = f"❓ {msg.get('content', '')}"
                tip = msg.get("question_tip", "")
                if tip:
                    q_text += f"\n\n💡 质询方向：{tip}"
                self._add_chat_bubble("ai", q_text)
            elif role == "user_answer":
                rnd = msg.get("round", "?")
                self._add_chat_bubble("user", f"📍 第 {rnd} 轮回答\n\n{msg.get('content', '')}")
            elif role == "ai_score":
                score_val = ""
                for s_msg in self._messages:
                    if s_msg.get("role") == "ai_score" and s_msg.get("round") == msg.get("round"):
                        score_val = s_msg.get("content", "")
                        break
                self._add_chat_bubble("score", f"⭐ AI评分：{score_val}\n\n📝 点评：{msg.get('content', '')}")
            elif role == "end_summary":
                self._add_chat_bubble("score", msg.get("content", ""))

        if self._scores:
            avg = sum(self._scores) / len(self._scores)
            self._score_label.setText(f"接质成绩 | {len(self._scores)}轮均分: {avg:.1f}")
            self._score_bar.setVisible(True)

        self._state = "ended"
        mw.centre_stack.setCurrentIndex(self.page_index)
        mw._update_status("已加载接质记录 [.stardebate]")
