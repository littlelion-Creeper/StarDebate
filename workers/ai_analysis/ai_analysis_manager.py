# -*- coding: utf-8 -*-
"""AI 分析管理器 — UI 构建 + 业务逻辑 + 卡片渲染

负责:
  - AI 分析报告页面的 UI 构建（正方/反方分 Tab）
  - AI 分析触发、Worker 调度、结果接收
  - 分析结果持久化（JSON 文件）
  - 已保存分析的查看与加载
  - Markdown → 彩色卡片渲染
  - Worker 清理

页面位于 centre_stack 索引 3，由一辩稿编辑页的「🧠 AI分析」按钮触发。
"""

import json as _json
import os
import re
from datetime import datetime

from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QWidget, QTabWidget,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from components.popup_dialog import CustomDialog
from components.star_button import StarButton

from .ai_analysis_worker import AnalysisWorker


class AIAnalysisManager:
    """AI 分析面板全生命周期管理器"""

    def __init__(self, mw):
        """初始化管理器

        Args:
            mw: StarDebateWindow 主窗口引用
        """
        self._mw = mw

        # ---- AI 分析状态 ----
        self._worker: AnalysisWorker | None = None

        # ---- UI 控件引用 ----
        self._analysis_page: QWidget | None = None
        self._analysis_tabs: QTabWidget | None = None
        self._pro_scroll: QScrollArea | None = None
        self._pro_widget: QWidget | None = None
        self._pro_layout: QVBoxLayout | None = None
        self._con_scroll: QScrollArea | None = None
        self._con_widget: QWidget | None = None
        self._con_layout: QVBoxLayout | None = None

    # =================================================================
    # 公开属性（向后兼容主文件直接访问）
    # =================================================================
    @property
    def analysis_page(self) -> QWidget | None:
        return self._analysis_page

    @property
    def analysis_tabs(self) -> QTabWidget | None:
        return self._analysis_tabs

    @property
    def pro_scroll(self) -> QScrollArea | None:
        return self._pro_scroll

    @property
    def con_scroll(self) -> QScrollArea | None:
        return self._con_scroll

    # =================================================================
    # UI 构建
    # =================================================================
    def build_ui(self) -> int:
        """构建 AI 分析报告页面，添加到 centre_stack，返回页面索引

        Returns:
            int: 在 centre_stack 中的页面索引
        """
        mw = self._mw

        page_analysis = QWidget()
        page_analysis.setObjectName("analysisPage")
        analysis_layout = QVBoxLayout(page_analysis)
        analysis_layout.setSpacing(10)
        analysis_layout.setContentsMargins(10, 10, 10, 10)

        # ---- 工具栏 ----
        analysis_toolbar = QHBoxLayout()
        analysis_toolbar.setSpacing(8)

        btn_back_to_detail = StarButton("← 返回辩论详情", None, layout_mode="text_only", ratio_h=0.7)
        btn_back_to_detail.clicked.connect(lambda: mw.centre_stack.setCurrentIndex(1))

        btn_back_to_speech = StarButton("← 返回一辩稿编辑", None, layout_mode="text_only", ratio_h=0.7)
        btn_back_to_speech.clicked.connect(lambda: mw.centre_stack.setCurrentIndex(2))

        analysis_toolbar.addWidget(btn_back_to_detail)
        analysis_toolbar.addWidget(btn_back_to_speech)
        analysis_toolbar.addStretch()

        # ---- 分析 Tab — 正方 / 反方 ----
        self._analysis_tabs = QTabWidget()
        self._analysis_tabs.setObjectName("analysisTabs")
        self._analysis_tabs.setFont(QFont("Microsoft YaHei", 11))

        # 正方分析容器
        self._pro_scroll = QScrollArea()
        self._pro_scroll.setObjectName("analysisProScroll")
        self._pro_scroll.setWidgetResizable(True)
        self._pro_scroll.setFrameShape(QFrame.NoFrame)
        self._pro_widget = QWidget()
        self._pro_widget.setObjectName("analysisProWidget")
        self._pro_layout = QVBoxLayout(self._pro_widget)
        self._pro_layout.setSpacing(10)
        self._pro_layout.setContentsMargins(8, 8, 8, 8)
        self._pro_scroll.setWidget(self._pro_widget)
        self._analysis_tabs.addTab(self._pro_scroll, "🟢 正方分析")

        # 反方分析容器
        self._con_scroll = QScrollArea()
        self._con_scroll.setObjectName("analysisConScroll")
        self._con_scroll.setWidgetResizable(True)
        self._con_scroll.setFrameShape(QFrame.NoFrame)
        self._con_widget = QWidget()
        self._con_widget.setObjectName("analysisConWidget")
        self._con_layout = QVBoxLayout(self._con_widget)
        self._con_layout.setSpacing(10)
        self._con_layout.setContentsMargins(8, 8, 8, 8)
        self._con_scroll.setWidget(self._con_widget)
        self._analysis_tabs.addTab(self._con_scroll, "🔴 反方分析")

        analysis_layout.addLayout(analysis_toolbar)
        analysis_layout.addWidget(self._analysis_tabs)

        self._analysis_page = page_analysis
        index = mw.centre_stack.addWidget(page_analysis)
        return index

    # =================================================================
    # AI 分析流程
    # =================================================================
    def start_analysis(self, side: str):
        """发起 AI 分析

        Args:
            side: "pro" 或 "con"
        """
        mw = self._mw
        label = mw._side_label(side)
        edit = mw.edit_pro_speech if side == "pro" else mw.edit_con_speech
        speech_text = edit.toPlainText().strip()

        if not speech_text:
            CustomDialog.warning(mw, "提示", f"{label}一辩稿内容为空，请先输入内容")
            return

        api_config = mw._load_api_config()
        if not api_config.get("api_key"):
            CustomDialog.warning(
                mw, "缺少 API Key",
                "请在 api_config.json 中填写您的 DeepSeek API Key 后再使用分析功能。"
            )
            return

        debate_title = ""
        if mw.current_debate_data:
            pro = mw.current_debate_data.get("pro", "")
            con = mw.current_debate_data.get("con", "")
            debate_title = f"{pro} vs {con}"

        # 显示加载条
        mw._ai_loading_bar.show_loading(f"AI正在分析{label}一辩稿…")

        # 启动后台线程
        self._worker = AnalysisWorker(api_config, speech_text, debate_title, side)
        self._worker.finished.connect(self._on_analysis_finished)
        self._worker.start()

    def cleanup_worker(self):
        """取消/清理分析线程"""
        if self._worker:
            self._worker.terminate()
            self._worker = None

    def _on_analysis_finished(self, success: bool, side: str, result_text: str):
        """分析完成回调 — 保存结果 + 展示到分析页"""
        mw = self._mw
        mw._ai_loading_bar.hide_loading()
        label = mw._side_label(side)

        # ★ 调试监视：记录 AI 结果
        self._log_ai_monitor("ai_analysis", success, result_text)

        if not success:
            CustomDialog.error(
                mw, "分析失败",
                f"{label}一辩稿分析失败:\n{result_text}"
            )
            mw._update_status(f"{label}一辩稿 AI 分析失败")
            return

        # 保存分析结果到文件
        self._on_save_analysis(side, result_text)

        # 切换到分析展示页并渲染
        self._show_analysis_page(side, label, result_text)
        mw._update_status(f"{label}一辩稿 AI 分析完成")

    @staticmethod
    def _log_ai_monitor(feature: str, success: bool, result_text: str):
        """记录 AI 功能结果到调试监视管理器。"""
        try:
            from workers.debug_console.debug_monitor_manager import DebugMonitorManager
            mgr = DebugMonitorManager.instance()
            if mgr.is_monitor_enabled("ai_watch"):
                summary = f"响应:{len(result_text)}字符" if success else ""
                mgr.log_ai_result(
                    feature, success, duration_ms=0,
                    result_summary=summary,
                    error=result_text[:200] if not success else "",
                )
        except Exception:
            pass

    # =================================================================
    # 持久化
    # =================================================================
    def _get_analysis_filename(self, side: str) -> str | None:
        """生成分析结果文件路径"""
        mw = self._mw
        if not mw.current_debate_path:
            return None
        dir_name = os.path.dirname(mw.current_debate_path)
        base = os.path.splitext(os.path.basename(mw.current_debate_path))[0]
        label = mw._side_label(side)
        return os.path.join(dir_name, f"{base}_{label}一辩稿_分析.json")

    def _on_save_analysis(self, side: str, result_text: str):
        """持久化分析结果到 JSON 文件"""
        mw = self._mw
        analysis_file = self._get_analysis_filename(side)
        if not analysis_file:
            return

        label = mw._side_label(side)
        edit = mw.edit_pro_speech if side == "pro" else mw.edit_con_speech
        debate_title = ""
        if mw.current_debate_data:
            pro = mw.current_debate_data.get("pro", "")
            con = mw.current_debate_data.get("con", "")
            debate_title = f"{pro} vs {con}"

        data = {
            "side": label,
            "debate_title": debate_title,
            "speech_snapshot": edit.toPlainText().strip()[:500],
            "analysis": result_text,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            with open(analysis_file, "w", encoding="utf-8") as f:
                _json.dump(data, f, ensure_ascii=False, indent=2)
            # 刷新树控件
            project_path = mw._get_current_project_path()
            if project_path:
                mw._build_tree_from_path(project_path)
        except OSError as e:
            print(f"[Warning] 分析结果保存失败: {e}")

    # =================================================================
    # 查看分析
    # =================================================================
    def view_analysis(self, side: str):
        """查看已保存的分析结果

        Args:
            side: "pro" 或 "con"
        """
        mw = self._mw
        analysis_file = self._get_analysis_filename(side)
        label = mw._side_label(side)

        if not analysis_file or not os.path.isfile(analysis_file):
            CustomDialog.information(
                mw, "提示",
                f"尚未对{label}一辩稿进行 AI 分析。\n请先输入内容后点击「🧠 AI分析」。"
            )
            return

        try:
            with open(analysis_file, "r", encoding="utf-8") as f:
                data = _json.load(f)
            result_text = data.get("analysis", "")
            if not result_text:
                CustomDialog.warning(mw, "提示", f"{label}分析结果为空")
                return
            self._show_analysis_page(side, label, result_text)
        except (_json.JSONDecodeError, OSError) as e:
            CustomDialog.error(mw, "加载失败", f"无法读取分析文件:\n{str(e)}")

    def _show_analysis_page(self, side: str, label: str, text: str):
        """加载分析文本并在 page 3 以卡片形式渲染"""
        mw = self._mw
        self._render_analysis_cards(side, text)
        # 切换到对应 Tab
        tab_idx = 0 if side == "pro" else 1
        self._analysis_tabs.setCurrentIndex(tab_idx)
        mw.centre_stack.setCurrentIndex(3)

    # =================================================================
    # 卡片渲染
    # =================================================================
    def _render_analysis_cards(self, side: str, text: str):
        """将 Markdown 分析文本解析为彩色卡片并填充到对应容器"""
        layout = self._pro_layout if side == "pro" else self._con_layout

        # 彻底清空旧卡片
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # ---- 第一步：将各种标题格式统一规范化为 ## ----
        normalized = text.strip()

        # 1. 将 ### 标题转为 ##（去掉多余 #）
        normalized = re.sub(r'^#{3,}\s*', '## ', normalized, flags=re.MULTILINE)

        # 2. 将 **数字. 标题** 或 **标题** 折行转为 ## 标题
        normalized = re.sub(
            r'^\*\*\s*(?:\d+[\.\、\s]+)?(.+?)\s*\*\*\s*$',
            r'## \1',
            normalized,
            flags=re.MULTILINE
        )

        # 3. 将纯数字列表行转为 ## 标题
        normalized = re.sub(
            r'^\d+[\.\、\s]+(核心论点|论证结构|论据强度|优势|改进建议)(.*?)$',
            r'## \1\2',
            normalized,
            flags=re.MULTILINE
        )

        # ---- 第二步：按 ## 标题切分 ----
        sections = re.split(r"\n(?=##\s)", normalized)

        # 收集纯 ## 标题段落之前的"元信息"（并过滤掉 AI 常见问候语）
        meta_lines = []
        sec_start = 0
        boilerplate_patterns = [
            "好的", "好的，", "您好", "你好", "以下是", "以下是对",
            "作为", "作为您的", "辩论教练", "分析如下", "为您分析",
        ]
        for i, s in enumerate(sections):
            if s.startswith("## "):
                sec_start = i
                break
            line = s.strip()
            if line:
                if any(line.startswith(p) for p in boilerplate_patterns):
                    continue
                if len(line) < 8 and ("分析" in line or "辩论" in line):
                    continue
                meta_lines.append(line)

        # 元信息卡片
        if meta_lines:
            meta_text = "\n".join(meta_lines).strip()
            if meta_text:
                card = QFrame()
                card.setObjectName("analysisMetaCard")
                c_layout = QVBoxLayout(card)
                c_layout.setSpacing(4)
                c_layout.setContentsMargins(14, 12, 14, 12)
                meta_lbl = QLabel(meta_text)
                meta_lbl.setObjectName("analysisMetaLabel")
                meta_lbl.setWordWrap(True)
                meta_lbl.setFont(QFont("Microsoft YaHei", 10))
                c_layout.addWidget(meta_lbl)
                layout.addWidget(card)

        # 卡片配色方案（按分析维度索引）
        card_colors = [
            ("#f9e2af", "#df8e1d"),  # 核心论点 - 金色
            ("#89b4fa", "#1e66f5"),  # 论证结构 - 蓝色
            ("#a6e3a1", "#40a02b"),  # 论据强度 - 绿色
            ("#f38ba8", "#d20f39"),  # 优势与漏洞 - 红色
            ("#2E6DDE", "#8839ef"),  # 改进建议 - 紫色
        ]

        # ---- 第三步：生成维度卡片 ----
        for sec in sections[sec_start:]:
            if not sec.startswith("## "):
                continue
            parts = sec.split("\n", 1)
            raw_title = parts[0].replace("##", "").strip()
            # 去掉标题中可能残留的编号
            title = re.sub(r'^\d+[\.\、\s]+', '', raw_title).strip()
            body = parts[1].strip() if len(parts) > 1 else ""

            # 按维度关键词匹配颜色
            color_idx = -1
            kw_list = ["论点", "论证", "论据", "优势", "建议"]
            for i, kw in enumerate(kw_list):
                if kw in title:
                    color_idx = i
                    break
            if color_idx < 0 or color_idx >= len(card_colors):
                color_idx = len(card_colors) - 1
            title_color, accent = card_colors[color_idx]

            # ---- 卡片主体 ----
            card = QFrame()
            card.setObjectName("analysisCard")
            card.setStyleSheet(
                f"QFrame#analysisCard {{ background-color: transparent; "
                f"border: none; border-radius: 10px; "
                f"border-left: 4px solid {accent}; }}"
            )
            c_layout = QVBoxLayout(card)
            c_layout.setSpacing(8)
            c_layout.setContentsMargins(16, 12, 16, 14)

            # 标题
            header = QLabel(title)
            header.setObjectName("analysisCardTitle")
            header.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
            header.setStyleSheet(
                f"color: {title_color}; background: transparent;")
            c_layout.addWidget(header)

            # 分隔线
            sep = QFrame()
            sep.setObjectName("analysisCardSep")
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet(
                f"QFrame#analysisCardSep {{ color: {accent}44; max-height: 1px; }}")
            c_layout.addWidget(sep)

            # 正文
            body_lbl = QLabel()
            body_lbl.setObjectName("analysisCardBody")
            body_lbl.setFont(QFont("Microsoft YaHei", 10))
            body_lbl.setWordWrap(True)
            body_lbl.setTextInteractionFlags(
                Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse
            )
            try:
                body_lbl.setTextFormat(Qt.MarkdownText)
                body_lbl.setText(body)
            except AttributeError:
                body_lbl.setText(body)
            c_layout.addWidget(body_lbl)

            layout.addWidget(card)

        # 底部弹性空间
        layout.addStretch()
