from components.theme_colors import tc, refresh
# -*- coding: utf-8 -*-
"""AI扩写管理器 — UI 构建 + 业务逻辑 + 卡片管理 + JSON 容错解析

负责:
  - AI扩写面板的 UI 构建（标题栏 + 历史记录区 + 结果卡片区）
  - 导航栏切换按钮创建
  - AI 扩写触发、Worker 调度、结果 JSON 解析与展示
  - 扩写结果卡片构建、网格重排
  - 历史任务卡片管理（查看/重试/删除）
  - 文件保存/加载/删除（ai_expand_results/）
  - 面板互斥切换逻辑（与 AI写稿/便签/训练/插件互斥）
  - 事件过滤（scroll resize → 卡片网格重排）
  - JSON 容错解析（处理 AI 常见格式错误）

面板位于 splitter 索引 5，通过右侧导航栏「🤖 扩写」按钮切换显示。
"""

import json as _json
import os
import re
import datetime

from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QWidget, QGridLayout, QApplication,
    QListWidget, QListWidgetItem, QMenu, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QFontMetrics

from components.popup_dialog import CustomDialog

from .ai_expand_worker import AIExpandWorker
from workers.nav_bar.nav_bar_manager import NavBarManager


class AIExpandManager:
    """AI扩写面板全生命周期管理器"""

    _FlowLayout = None  # 类级 FlowLayout 引用，由主窗口在实例化后注入

    def __init__(self, mw):
        """初始化管理器

        Args:
            mw: StarDebateWindow 主窗口引用
        """
        self._mw = mw

        # ---- 面板状态 ----
        self._visible: bool = False
        self._history_visible: bool = True

        # ---- AI扩写数据 ----
        self._tasks: list[dict] = []
        self._current_task_index: int = -1
        self._cards: list[QFrame] = []
        self._worker: AIExpandWorker | None = None
        self._dialog = None

        # ---- UI 控件引用 ----
        self._panel: QFrame | None = None
        self._history_section: QFrame | None = None
        self._history_scroll: QScrollArea | None = None
        self._history_list: QVBoxLayout | None = None
        self._saved_files_list: QListWidget | None = None
        self._current_label: QLabel | None = None
        self._cards_scroll: QScrollArea | None = None
        self._cards_grid: QGridLayout | None = None
        self._empty_hint: QLabel | None = None

        # ---- 标题栏按钮 ----
        self._btn_history: QPushButton | None = None
        self._btn_close: QPushButton | None = None
        self._btn_view_saved: QPushButton | None = None

        # ---- 导航按钮 ----
        self._btn_toggle: QPushButton | None = None
        self._lbl_toggle: QLabel | None = None

        # ---- 重排定时器 ----
        self._reflow_timer: QTimer | None = None

    # ============================================================
    #  属性 (向后兼容)
    # ============================================================

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, value: bool):
        self._visible = value
        if self._panel:
            self._panel.setVisible(value)

    @property
    def panel(self) -> QFrame | None:
        return self._panel

    @property
    def cards_scroll(self) -> QScrollArea | None:
        return self._cards_scroll

    @property
    def cards(self) -> list:
        return self._cards

    @property
    def btn_toggle(self) -> QPushButton | None:
        return self._btn_toggle

    # ============================================================
    #  UI 构建
    # ============================================================

    def build_panel(self) -> QFrame:
        """构建 AI扩写面板，返回 QFrame"""
        panel = QFrame()
        panel.setObjectName("aiExpandPanel")
        panel.setMinimumWidth(480)
        panel.setMaximumWidth(2400)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # --- 标题栏 ---
        header = QFrame()
        header.setObjectName("aiExpandHeader")
        header.setFixedHeight(54)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 12, 6)
        header_layout.setSpacing(8)

        title_lbl = QLabel("AI扩写")
        title_lbl.setObjectName("aiExpandPanelTitle")
        title_lbl.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))

        # 历史记录开关按钮
        self._btn_history = QPushButton("📋")
        self._btn_history.setObjectName("smallBtn")
        self._btn_history.setFixedSize(42, 42)
        self._btn_history.setCheckable(True)
        self._btn_history.setChecked(True)
        self._btn_history.setToolTip("显示/隐藏 历史记录")
        self._btn_history.setCursor(Qt.PointingHandCursor)
        self._btn_history.clicked.connect(self._toggle_history)

        # 关闭按钮
        self._btn_close = QPushButton("−")
        self._btn_close.setObjectName("smallBtn")
        self._btn_close.setFixedSize(42, 42)
        self._btn_close.setToolTip("关闭AI扩写面板")
        self._btn_close.setCursor(Qt.PointingHandCursor)
        self._btn_close.clicked.connect(self.toggle_visibility)

        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        header_layout.addWidget(self._btn_history)
        header_layout.addWidget(self._btn_close)

        # --- 历史记录区域 ---
        history_section = QFrame()
        history_section.setObjectName("aiExpandHistorySection")
        self._history_section = history_section
        history_layout = QVBoxLayout(history_section)
        history_layout.setContentsMargins(8, 6, 8, 6)
        history_layout.setSpacing(4)

        history_title_row = QHBoxLayout()
        history_title_row.setSpacing(8)

        hist_title = QLabel("历史记录")
        hist_title.setObjectName("aiExpandHistTitle")
        hist_title.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        history_title_row.addWidget(hist_title)
        history_title_row.addStretch()

        self._btn_view_saved = QPushButton("已保存")
        self._btn_view_saved.setObjectName("smallBtn")
        self._btn_view_saved.setFixedSize(90, 32)
        self._btn_view_saved.setCheckable(True)
        self._btn_view_saved.setChecked(False)
        self._btn_view_saved.setToolTip("显示/隐藏 已保存的扩写文件列表")
        self._btn_view_saved.setCursor(Qt.PointingHandCursor)
        self._btn_view_saved.clicked.connect(self._toggle_saved_files_list)
        history_title_row.addWidget(self._btn_view_saved)

        # 已保存文件列表（默认隐藏）
        self._saved_files_list = QListWidget()
        self._saved_files_list.setObjectName("savedFilesList")
        self._saved_files_list.setMaximumHeight(180)
        self._saved_files_list.setVisible(False)
        self._saved_files_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._saved_files_list.itemClicked.connect(self._on_saved_file_clicked)
        self._saved_files_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._saved_files_list.customContextMenuRequested.connect(self._on_saved_file_context_menu)

        self._history_scroll = QScrollArea()
        self._history_scroll.setObjectName("aiExpandHistoryScroll")
        self._history_scroll.setWidgetResizable(True)
        self._history_scroll.setMinimumHeight(280)
        self._history_scroll.setMaximumHeight(400)
        self._history_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        history_container = QWidget()
        history_container.setObjectName("aiHistoryContainer")
        self._history_list = QVBoxLayout(history_container)
        self._history_list.setContentsMargins(0, 0, 0, 0)
        self._history_list.setSpacing(4)
        self._history_list.addStretch()
        self._history_scroll.setWidget(history_container)

        history_layout.addLayout(history_title_row)
        history_layout.addWidget(self._history_scroll)
        history_layout.addWidget(self._saved_files_list)

        # --- 结果卡片区域 ---
        cards_section = QFrame()
        cards_section.setObjectName("aiExpandCardsSection")
        cards_layout = QVBoxLayout(cards_section)
        cards_layout.setContentsMargins(8, 6, 8, 6)
        cards_layout.setSpacing(4)

        result_title = QLabel("扩写结果")
        result_title.setObjectName("aiExpandResultTitle")
        result_title.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))

        self._current_label = QLabel("")
        self._current_label.setObjectName("aiExpandCurrentLabel")
        self._current_label.setFont(QFont("Microsoft YaHei", 9))
        self._current_label.setWordWrap(True)

        self._cards_scroll = QScrollArea()
        self._cards_scroll.setObjectName("aiExpandCardsScroll")
        self._cards_scroll.setWidgetResizable(True)
        self._cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._cards_scroll.installEventFilter(self._mw)

        cards_container = QWidget()
        cards_container.setObjectName("aiCardsContainer")
        self._cards_grid = QGridLayout(cards_container)
        self._cards_grid.setContentsMargins(4, 4, 4, 4)
        self._cards_grid.setSpacing(8)
        self._cards_scroll.setWidget(cards_container)

        # 空状态提示
        self._empty_hint = QLabel(
            "在一辩稿中选中关键词\n右键点击「AI扩写」\n结果将在此展示"
        )
        self._empty_hint.setObjectName("aiExpandEmptyHint")
        self._empty_hint.setFont(QFont("Microsoft YaHei", 11))
        self._empty_hint.setAlignment(Qt.AlignCenter)
        self._empty_hint.setWordWrap(True)

        cards_layout.addWidget(result_title)
        cards_layout.addWidget(self._current_label)
        cards_layout.addWidget(self._empty_hint, stretch=1)
        cards_layout.addWidget(self._cards_scroll, stretch=1)

        panel_layout.addWidget(header)
        panel_layout.addWidget(history_section)
        panel_layout.addWidget(cards_section, stretch=1)

        # 初始不可见
        panel.setVisible(False)
        self._cards_scroll.setVisible(False)
        self._panel = panel

        return panel

    def build_nav_button(self) -> tuple[QPushButton, QLabel]:
        """构建导航栏切换按钮，返回 (按钮, 标签)（支持图标文件）"""
        btn = QPushButton()
        btn.setObjectName("navToggleBtn")
        btn.setCheckable(True)
        btn.setChecked(False)
        btn.setToolTip("开关 AI扩写")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(50, 50)
        btn.clicked.connect(self.toggle_visibility)

        item = self._mw._nav_registry.get_item("ai_expand")
        icon = NavBarManager.load_nav_icon(item.icon) if item else None
        if icon is not None:
            NavBarManager._apply_icon_to_button(btn, icon)
        else:
            btn.setText("🤖")
        self._btn_toggle = btn

        lbl = QLabel("扩写")
        lbl.setObjectName("aiExpandNavLabel")
        lbl.setFont(QFont("Microsoft YaHei", 7))
        lbl.setAlignment(Qt.AlignCenter)
        self._lbl_toggle = lbl

        return btn, lbl

    # ============================================================
    #  面板切换 & 互斥
    # ============================================================

    def toggle_visibility(self):
        """切换 AI 扩写面板的显示/隐藏（与其他面板互斥）"""
        mw = self._mw

        # 互斥：打开 AI扩写时关闭 AI写稿
        mw._speech_writer_mgr.close_if_open()

        self._visible = not self._visible
        self._panel.setVisible(self._visible)
        self._btn_toggle.setChecked(self._visible)

        if self._visible:
            # 互斥：关闭便签、模拟训练和插件
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
            mw._update_status("AI扩写面板已打开")
        else:
            mw._update_status("AI扩写面板已关闭")

    def close_if_open(self):
        """如果 AI扩写面板已打开，关闭它（供其他面板互斥调用）"""
        if self._visible:
            self._visible = False
            self._panel.setVisible(False)
            self._btn_toggle.setChecked(False)

    # ============================================================
    #  AI 扩写请求入口
    # ============================================================

    def request_expand(self, edit, side: str, selected_text: str):
        """用户请求 AI 扩写（由一辩稿右键菜单调用）"""
        mw = self._mw

        # 获取完整一辩稿正文
        full_text = edit.toPlainText().strip()
        if not full_text:
            CustomDialog.warning(mw, "提示", "一辩稿内容为空，请先输入内容")
            return

        keyword = selected_text[:50].strip()
        if not keyword:
            CustomDialog.warning(mw, "提示", "请先选中需要扩写的关键词")
            return

        # 检查 API 配置
        api_config = mw._load_api_config()
        if not api_config.get("api_key"):
            CustomDialog.warning(
                mw, "缺少 API Key",
                "请在 api_config.json 中填写您的 DeepSeek API Key 后再使用 AI扩写功能。"
            )
            return

        # 获取辩论标题
        debate_title = ""
        if mw.current_debate_data:
            pro = mw.current_debate_data.get("pro", "")
            con = mw.current_debate_data.get("con", "")
            debate_title = f"{pro} vs {con}"

        # 创建扩写任务
        task = {
            "keyword": keyword,
            "side": side,
            "full_text": full_text,
            "debate_title": debate_title,
            "status": "processing",
            "results": [],
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            "error_msg": ""
        }
        self._tasks.append(task)
        task_index = len(self._tasks) - 1
        self._current_task_index = task_index

        # 自动打开面板
        if not self._visible:
            self.toggle_visibility()

        # 刷新历史列表
        self._refresh_history()

        # 更新当前任务标签
        side_label = "正方" if side == "pro" else "反方"
        self._current_label.setText(
            f"⏳ 正在为 {side_label} 关键词「{keyword}」生成扩写方案..."
        )
        self._empty_hint.setVisible(False)
        self._cards_scroll.setVisible(False)

        # 清空旧卡片
        self._clear_cards()

        # 启动 AI 线程
        self._worker = AIExpandWorker(
            api_config=api_config,
            full_text=full_text,
            keyword=keyword,
            side=side,
            debate_title=debate_title
        )
        self._worker.finished.connect(
            lambda success, err, result: self._on_expand_finished(success, err, result, task_index)
        )
        self._worker.start()

        # 显示加载条
        mw._ai_loading_bar.show_loading(f"AI正在扩写「{keyword}」...")
        mw._update_status(f"正在对「{keyword}」进行AI扩写...")

    # ============================================================
    #  AI 扩写完成回调
    # ============================================================

    def _on_expand_finished(self, success: bool, error_msg: str, result_text: str, task_index: int):
        """AI扩写完成回调"""
        mw = self._mw
        mw._ai_loading_bar.hide_loading()

        if task_index >= len(self._tasks):
            return

        task = self._tasks[task_index]

        if not success:
            task["status"] = "failed"
            task["error_msg"] = error_msg
            self._refresh_history()
            self._current_label.setText(f"❌ 扩写失败: {error_msg}")
            mw._update_status(f"AI扩写失败: {error_msg}")
            CustomDialog.warning(mw, "AI扩写失败", error_msg)
            return

        # 解析 JSON 结果
        try:
            json_text = result_text.strip()
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0].strip()
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0].strip()

            data, parse_err = self._robust_json_parse(json_text)

            if data is None:
                raise ValueError(parse_err or "无法解析 AI 返回的 JSON 格式")

            schemes = data.get("schemes", [])
            if not schemes:
                raise ValueError("AI返回的方案列表为空")

            task["results"] = schemes
            task["status"] = "completed"
            self._refresh_history()

            self._save_to_json(task_index)

            side_label = "正方" if task["side"] == "pro" else "反方"
            self._current_label.setText(
                f"{side_label}「{task['keyword']}」— 共 {len(schemes)} 个扩写方案"
            )
            self._empty_hint.setVisible(False)
            self._build_cards(schemes)

            mw._update_status(f"AI扩写完成：「{task['keyword']}」共生成 {len(schemes)} 个方案")
        except (_json.JSONDecodeError, ValueError, KeyError) as e:
            task["status"] = "failed"
            task["error_msg"] = f"解析AI返回结果失败: {str(e)}"
            try:
                self._save_raw_response_for_debug(task_index, result_text)
            except Exception:
                pass
            self._refresh_history()
            self._current_label.setText(f"❌ 解析结果失败: {str(e)}")
            mw._update_status("解析AI扩写结果失败")
            raw_preview = result_text[:500] + ("…" if len(result_text) > 500 else "")
            CustomDialog.warning(
                mw, "JSON解析失败",
                f"AI返回的内容无法解析为JSON。\n错误：{e}\n\n"
                f"原始返回已保存至 ai_expand_results/debug_*.json，可手动查看。\n\n"
                f"返回内容预览（前500字）：\n{raw_preview}"
            )

    # ============================================================
    #  文件操作
    # ============================================================

    def _get_save_dir(self) -> str | None:
        """获取 AI 扩写结果保存目录"""
        mw = self._mw
        project_path = mw._get_current_project_path()
        if not project_path:
            return None
        save_dir = os.path.join(project_path, "ai_expand_results")
        os.makedirs(save_dir, exist_ok=True)
        return save_dir

    def _save_to_json(self, task_index: int) -> str | None:
        """将完成的扩写任务保存为 JSON 文件，返回文件路径"""
        if task_index >= len(self._tasks):
            return None
        task = self._tasks[task_index]
        if task["status"] != "completed":
            return None

        save_dir = self._get_save_dir()
        if not save_dir:
            return None

        safe_keyword = re.sub(r'[\\/:*?"<>|\s]', '_', task["keyword"])[:20]
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"expand_{safe_keyword}_{timestamp}.json"
        filepath = os.path.join(save_dir, filename)

        save_data = {
            "keyword": task["keyword"],
            "side": task["side"],
            "side_label": "正方" if task["side"] == "pro" else "反方",
            "debate_title": task.get("debate_title", ""),
            "timestamp": task.get("timestamp", ""),
            "save_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "results": task.get("results", [])
        }

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                _json.dump(save_data, f, ensure_ascii=False, indent=2)
            task["saved_file"] = filepath
            self._mw._update_status(f"已保存扩写结果: {filename}")
            self._refresh_saved_files_list()
            return filepath
        except Exception as e:
            self._mw._update_status(f"保存扩写结果失败: {str(e)}")
            return None

    def _delete_json_file(self, task: dict):
        """删除扩写任务对应的 JSON 文件"""
        saved_file = task.get("saved_file", "")
        if saved_file and os.path.isfile(saved_file):
            try:
                os.remove(saved_file)
                self._mw._update_status(f"已删除保存文件: {os.path.basename(saved_file)}")
                self._refresh_saved_files_list()
            except Exception as e:
                self._mw._update_status(f"删除保存文件失败: {str(e)}")

    def _save_raw_response_for_debug(self, task_index: int, raw_text: str):
        """解析失败时保存 AI 原始返回内容到 debug 文件"""
        save_dir = self._get_save_dir()
        if not save_dir or task_index >= len(self._tasks):
            return
        task = self._tasks[task_index]
        safe_keyword = re.sub(r'[\\/:*?"<>|\s]', '_', task["keyword"])[:20]
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"debug_{safe_keyword}_{timestamp}.json"
        filepath = os.path.join(save_dir, filename)
        debug_data = {
            "keyword": task["keyword"],
            "side": task["side"],
            "side_label": "正方" if task["side"] == "pro" else "反方",
            "debug_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "parse_error": task.get("error_msg", ""),
            "raw_response": raw_text,
            "response_length": len(raw_text)
        }
        with open(filepath, "w", encoding="utf-8") as f:
            _json.dump(debug_data, f, ensure_ascii=False, indent=2)
        self._mw._update_status(f"原始返回已保存到 debug 文件: {filename}")

    def _open_file_location(self, task_index: int):
        """在文件管理器中打开保存的 JSON 文件所在目录"""
        mw = self._mw
        if task_index >= len(self._tasks):
            return
        task = self._tasks[task_index]
        saved_file = task.get("saved_file", "")
        if saved_file and os.path.isfile(saved_file):
            folder = os.path.dirname(saved_file)
            try:
                os.startfile(folder)
                mw._update_status("已打开保存目录")
            except Exception as e:
                CustomDialog.warning(mw, "打开失败", f"无法打开目录: {str(e)}")
        else:
            save_dir = self._get_save_dir()
            if save_dir:
                try:
                    os.startfile(save_dir)
                    mw._update_status("已打开保存目录（文件可能已被移动）")
                except Exception:
                    CustomDialog.warning(mw, "提示", "尚未保存或文件已不存在。请先完成一次AI扩写。")
            else:
                CustomDialog.warning(mw, "提示", "未检测到有效的项目路径，请先创建或打开一个项目。")

    # ============================================================
    #  已保存文件列表
    # ============================================================

    def _toggle_saved_files_list(self):
        """切换已保存文件列表的显示/隐藏"""
        visible = not self._saved_files_list.isVisible()
        self._saved_files_list.setVisible(visible)
        self._btn_view_saved.setChecked(visible)
        if visible:
            self._refresh_saved_files_list()
            self._mw._update_status("已保存文件列表已展开")
        else:
            self._mw._update_status("已保存文件列表已收起")

    def _refresh_saved_files_list(self):
        """刷新已保存文件列表"""
        self._saved_files_list.clear()
        save_dir = self._get_save_dir()
        if not save_dir:
            self._saved_files_list.addItem("(无有效项目路径)")
            return
        try:
            json_files = sorted(
                [f for f in os.listdir(save_dir) if f.endswith(".json") and not f.startswith("debug_")],
                reverse=True
            )
        except Exception:
            self._saved_files_list.addItem("(无法读取保存目录)")
            return
        if not json_files:
            self._saved_files_list.addItem("(暂无保存的扩写文件)")
            return
        for jf in json_files:
            item = QListWidgetItem(f"📄 {jf}")
            item.setData(Qt.UserRole, os.path.join(save_dir, jf))
            self._saved_files_list.addItem(item)

    def _on_saved_file_clicked(self, item: QListWidgetItem):
        """点击已保存文件 → 加载并在卡片区域展示方案"""
        filepath = item.data(Qt.UserRole)
        if not filepath or not os.path.isfile(filepath):
            return
        self._load_saved_file_schemes(filepath)

    def _on_saved_file_context_menu(self, pos):
        """右键菜单：加载 / 删除"""
        item = self._saved_files_list.itemAt(pos)
        if not item:
            return
        filepath = item.data(Qt.UserRole)
        if not filepath:
            return
        menu = QMenu(self._mw)
        menu.setStyleSheet(f"""
            QMenu { background-color: {tc("base")}; color: {tc("text")}; border: 1px solid {tc("overlay")}; }
            QMenu::item { padding: 6px 24px; }
            QMenu::item:selected { background-color: {tc("overlay")}; }
        """)
        action_load = menu.addAction("📋 加载方案")
        action_delete = menu.addAction("🗑 删除文件")
        chosen = menu.exec_(self._saved_files_list.mapToGlobal(pos))
        if chosen == action_load:
            self._load_saved_file_schemes(filepath)
        elif chosen == action_delete:
            self._delete_saved_file(filepath)

    def _load_saved_file_schemes(self, filepath: str):
        """读取 JSON 文件并在结果卡片区展示其方案"""
        mw = self._mw
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = _json.load(f)
        except Exception as e:
            CustomDialog.warning(mw, "读取失败", f"无法读取文件: {str(e)}")
            return

        keyword = data.get("keyword", os.path.basename(filepath))
        side_label = data.get("side_label", "")
        schemes = data.get("results", [])
        if not schemes:
            CustomDialog.information(mw, "空文件", "该文件中没有有效的扩写方案。")
            return

        label_text = f"{side_label}「{keyword}」— 共 {len(schemes)} 个扩写方案"
        if data.get("save_time"):
            label_text += f" (保存于 {data['save_time']})"
        self._current_label.setText(label_text)
        self._empty_hint.setVisible(False)
        self._cards_scroll.setVisible(True)
        self._build_cards(schemes)
        mw._update_status(f"已加载保存文件: {os.path.basename(filepath)}")

    def _delete_saved_file(self, filepath: str):
        """删除已保存的 JSON 文件"""
        filename = os.path.basename(filepath)
        result = CustomDialog.question(
            self._mw, "确认删除",
            f"确定要删除「{filename}」吗？\n此操作不可恢复。",
            buttons=[("否", "no"), ("是", "yes")])
        if result != "yes":
            return
        try:
            os.remove(filepath)
            for task in self._tasks:
                if task.get("saved_file") == filepath:
                    task["saved_file"] = ""
                    break
            self._refresh_saved_files_list()
            self._mw._update_status(f"已删除保存文件: {filename}")
        except Exception as e:
            CustomDialog.warning(self._mw, "删除失败", f"无法删除文件: {str(e)}")

    # ============================================================
    #  历史记录
    # ============================================================

    def _toggle_history(self):
        """切换历史记录区域的显示/隐藏"""
        self._history_visible = not self._history_visible
        self._history_section.setVisible(self._history_visible)
        self._btn_history.setChecked(self._history_visible)
        if self._history_visible:
            self._mw._update_status("历史记录已打开")
        else:
            self._mw._update_status("历史记录已关闭")

    def _refresh_history(self):
        """刷新历史任务列表"""
        history_layout = self._history_list
        while history_layout.count() > 1:
            item = history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._mw._clean_layout_recursive(item.layout())

        for idx, task in enumerate(self._tasks):
            card = self._create_history_card(idx, task)
            history_layout.insertWidget(history_layout.count() - 1, card)

    def _create_history_card(self, task_index: int, task: dict) -> QFrame:
        """创建历史任务卡片"""
        card = QFrame()
        card.setObjectName("aiHistoryCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # 关键词 + 时间
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        keyword_label = QLabel(f"▸ {task['keyword']}")
        keyword_label.setObjectName("aiHistoryKeyword")
        keyword_label.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        keyword_label.setWordWrap(True)

        time_label = QLabel(task.get("timestamp", ""))
        time_label.setObjectName("aiHistoryTime")
        time_label.setFont(QFont("Microsoft YaHei", 8))

        top_row.addWidget(keyword_label)
        top_row.addStretch()
        top_row.addWidget(time_label)

        # 状态 + 持方
        mid_row = QHBoxLayout()
        mid_row.setSpacing(6)

        side_label_text = "正方" if task["side"] == "pro" else "反方"
        side_lbl = QLabel(f"{side_label_text}一辩稿")
        side_lbl.setFont(QFont("Microsoft YaHei", 9))
        side_lbl.setStyleSheet(
            f"color: {'#a6e3a1' if task['side'] == 'pro' else '#f38ba8'};"
        )

        if task["status"] == "processing":
            status_text = "⏳ 扩写中..."
            status_color = "#f9e2af"
        elif task["status"] == "completed":
            n = len(task.get("results", []))
            status_text = f"✅ 已完成 ({n}个方案)"
            status_color = "#a6e3a1"
        else:
            status_text = "❌ 失败"
            status_color = "#f38ba8"

        status_lbl = QLabel(status_text)
        status_lbl.setFont(QFont("Microsoft YaHei", 9))
        status_lbl.setStyleSheet(f"color: {status_color};")

        mid_row.addWidget(side_lbl)
        mid_row.addStretch()
        mid_row.addWidget(status_lbl)

        # 操作按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        if task["status"] == "completed":
            btn_view = QPushButton("查看")
            btn_view.setObjectName("smallBtn")
            btn_view.setFixedSize(64, 32)
            btn_view.setCursor(Qt.PointingHandCursor)
            btn_view.clicked.connect(lambda checked, ti=task_index: self._view_task(ti))

            btn_file = QPushButton("📂")
            btn_file.setObjectName("smallBtn")
            btn_file.setFixedSize(34, 34)
            btn_file.setToolTip("查看保存的 JSON 文件")
            btn_file.setCursor(Qt.PointingHandCursor)
            btn_file.clicked.connect(lambda checked, ti=task_index: self._open_file_location(ti))

            btn_retry = QPushButton("")
            btn_retry.setObjectName("smallBtn")
            btn_retry.setFixedSize(34, 34)
            btn_retry.setToolTip("重新扩写")
            btn_retry.setCursor(Qt.PointingHandCursor)
            btn_retry.clicked.connect(lambda checked, ti=task_index: self._retry_expand(ti))

            btn_delete = QPushButton("")
            btn_delete.setObjectName("smallBtn")
            btn_delete.setFixedSize(34, 34)
            btn_delete.setToolTip("删除")
            btn_delete.setCursor(Qt.PointingHandCursor)
            btn_delete.clicked.connect(lambda checked, ti=task_index: self._delete_task(ti))

            btn_row.addStretch()
            btn_row.addWidget(btn_view)
            btn_row.addWidget(btn_file)
            btn_row.addWidget(btn_retry)
            btn_row.addWidget(btn_delete)
        elif task["status"] == "failed":
            btn_retry = QPushButton("重试")
            btn_retry.setObjectName("smallBtn")
            btn_retry.setFixedSize(64, 32)
            btn_retry.setCursor(Qt.PointingHandCursor)
            btn_retry.clicked.connect(lambda checked, ti=task_index: self._retry_expand(ti))

            btn_delete = QPushButton("")
            btn_delete.setObjectName("smallBtn")
            btn_delete.setFixedSize(34, 34)
            btn_delete.setToolTip("删除")
            btn_delete.setCursor(Qt.PointingHandCursor)
            btn_delete.clicked.connect(lambda checked, ti=task_index: self._delete_task(ti))

            btn_row.addStretch()
            btn_row.addWidget(btn_retry)
            btn_row.addWidget(btn_delete)
        else:
            btn_row.addStretch()

        layout.addLayout(top_row)
        layout.addLayout(mid_row)
        layout.addLayout(btn_row)

        return card

    def _view_task(self, task_index: int):
        """查看历史扩写任务的结果"""
        if task_index >= len(self._tasks):
            return
        task = self._tasks[task_index]
        self._current_task_index = task_index

        if task["status"] == "completed":
            side_label = "正方" if task["side"] == "pro" else "反方"
            self._current_label.setText(
                f"{side_label}「{task['keyword']}」— 共 {len(task['results'])} 个扩写方案"
            )
            self._empty_hint.setVisible(False)
            self._build_cards(task["results"])
        elif task["status"] == "failed":
            self._current_label.setText(f"❌ 扩写失败: {task.get('error_msg', '未知错误')}")
            self._empty_hint.setVisible(True)
            self._cards_scroll.setVisible(False)

        if not self._visible:
            self.toggle_visibility()

    def _retry_expand(self, task_index: int):
        """重新扩写历史任务"""
        if task_index >= len(self._tasks):
            return
        task = self._tasks[task_index]
        mw = self._mw

        edit = mw.edit_pro_speech if task["side"] == "pro" else mw.edit_con_speech
        full_text = task.get("full_text", edit.toPlainText().strip())

        keyword = task["keyword"]
        side = task["side"]
        debate_title = task.get("debate_title", "")

        task["status"] = "processing"
        task["error_msg"] = ""
        task["results"] = []

        self._delete_json_file(task)
        task.pop("saved_file", None)
        self._current_task_index = task_index
        self._refresh_history()

        side_label = "正方" if side == "pro" else "反方"
        self._current_label.setText(
            f"⏳ 正在为 {side_label} 关键词「{keyword}」重新扩写..."
        )
        self._empty_hint.setVisible(False)
        self._cards_scroll.setVisible(False)
        self._clear_cards()

        api_config = mw._load_api_config()
        self._worker = AIExpandWorker(
            api_config=api_config,
            full_text=full_text,
            keyword=keyword,
            side=side,
            debate_title=debate_title
        )
        self._worker.finished.connect(
            lambda s, e, r: self._on_expand_finished(s, e, r, task_index)
        )
        self._worker.start()

        mw._ai_loading_bar.show_loading(f"AI正在重新扩写「{keyword}」...")
        mw._update_status(f"正在重新扩写「{keyword}」...")

    def _delete_task(self, task_index: int):
        """删除历史扩写任务"""
        if task_index >= len(self._tasks):
            return

        result = CustomDialog.question(
            self._mw, "确认删除",
            f"确定要删除对「{self._tasks[task_index]['keyword']}」的扩写记录吗？",
            buttons=[("否", "no"), ("是", "yes")])
        if result != "yes":
            return

        task = self._tasks[task_index]
        self._delete_json_file(task)

        del self._tasks[task_index]

        if self._current_task_index == task_index:
            self._current_task_index = -1
            self._clear_cards()
            self._current_label.setText("")
            self._empty_hint.setVisible(True)
            self._cards_scroll.setVisible(False)
        elif self._current_task_index > task_index:
            self._current_task_index -= 1

        self._refresh_history()
        self._mw._update_status("已删除扩写记录")

    # ============================================================
    #  结果卡片
    # ============================================================

    def _clear_cards(self):
        """清空结果卡片"""
        grid = self._cards_grid
        while grid.count():
            item = grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._mw._clean_layout_recursive(item.layout())
        self._cards = []

    def _build_cards(self, schemes: list):
        """构建扩写结果卡片"""
        self._clear_cards()
        cards = []
        for scheme in schemes:
            card = self._create_result_card(scheme)
            cards.append(card)
        self._cards = cards

        self._cards_scroll.setVisible(True)
        self._empty_hint.setVisible(False)

        QTimer.singleShot(50, self._arrange_cards)
        QTimer.singleShot(250, self._arrange_cards)

    def _create_result_card(self, scheme: dict) -> QFrame:
        """创建单个扩写结果卡片"""
        scheme_id = scheme.get("id", "?")
        angle = scheme.get("angle", "")
        text = scheme.get("text", "")
        highlights = scheme.get("highlights", [])

        card = QFrame()
        card.setObjectName("aiExpandResultCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # 顶部行：标题 + 按钮
        top_row = QHBoxLayout()
        top_row.setSpacing(4)

        title_text = f"方案 #{scheme_id}"
        if angle:
            title_text += f" · {angle}"
        lbl_title = QLabel(title_text)
        lbl_title.setObjectName("aiExpandCardTitle")
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

        # 分隔线
        sep = QFrame()
        sep.setObjectName("aiExpandCardSep")
        sep.setFrameShape(QFrame.HLine)

        # 文本内容
        lbl_text = QLabel(text)
        lbl_text.setObjectName("aiExpandCardText")
        lbl_text.setFont(QFont("Microsoft YaHei", 10))
        lbl_text.setWordWrap(True)
        lbl_text.setTextInteractionFlags(Qt.TextSelectableByMouse)

        # 亮点标签
        highlight_widget = None
        if highlights:
            FlowLayout = self._FlowLayout
            if FlowLayout:
                hl_layout = FlowLayout()
                hl_layout.setContentsMargins(0, 0, 0, 0)
                hl_layout.setSpacing(4)
                lbl_hl_title = QLabel("💡")
                lbl_hl_title.setObjectName("aiExpandHLTitle")
                lbl_hl_title.setFont(QFont("Microsoft YaHei", 9))
                lbl_hl_title.setFixedSize(18, 18)
                hl_layout.addWidget(lbl_hl_title)

                tag_font = QFont("Microsoft YaHei", 8)
                fm = QFontMetrics(tag_font)
                max_tag_w = 300

                for h in highlights:
                    text_w = fm.horizontalAdvance(h) + 16
                    tag_w = min(max_tag_w, max(text_w, 30))
                    hl_tag = QLabel(h)
                    hl_tag.setObjectName("aiExpandHLTag")
                    hl_tag.setFont(tag_font)
                    hl_tag.setWordWrap(True if text_w > max_tag_w else False)
                    hl_tag.setFixedWidth(tag_w)
                    hl_tag.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
                    hl_layout.addWidget(hl_tag)
                highlight_widget = QWidget()
                highlight_widget.setLayout(hl_layout)

        # 底部按钮
        btn_insert = QPushButton("插入编辑器")
        btn_insert.setObjectName("smallBtn")
        btn_insert.setCursor(Qt.PointingHandCursor)
        btn_insert.setFixedHeight(28)
        btn_insert.clicked.connect(lambda checked, t=text: self._insert_text(t))

        layout.addLayout(top_row)
        layout.addWidget(sep)
        layout.addWidget(lbl_text, stretch=1)
        if highlight_widget:
            layout.addWidget(highlight_widget)
        layout.addWidget(btn_insert)

        return card

    def _arrange_cards(self):
        """智能排布扩写结果卡片 — 根据面板宽度自适应列数"""
        cards = self._cards
        grid = self._cards_grid

        for card in cards:
            grid.removeWidget(card)

        if not cards:
            return

        self._cards_scroll.updateGeometry()
        QApplication.processEvents()

        container_width = self._cards_scroll.viewport().width()
        if container_width <= 0:
            container_width = self._cards_scroll.width() - (
                self._cards_scroll.frameWidth() * 2)
        if container_width <= 0:
            container_width = self._panel.width() - 30
        if container_width <= 0:
            container_width = 280

        margins = grid.contentsMargins()
        avail_w = container_width - margins.left() - margins.right()
        spacing = grid.spacing()

        if avail_w >= 700:
            cols = 2
            actual_card_w = (avail_w - spacing * (cols - 1)) // cols
        else:
            cols = 1
            actual_card_w = max(260, avail_w)

        for i, card in enumerate(cards):
            row = i // cols
            col = i % cols
            card.setFixedWidth(actual_card_w)
            card.adjustSize()
            grid.addWidget(card, row, col)

        total = len(cards)
        last_row = (total - 1) // cols if total > 0 else 0
        grid.setRowStretch(last_row + 1, 1)

    def handle_scroll_resize(self):
        """eventFilter 委托：卡片滚动区域尺寸变化时重排"""
        if self._cards and self._panel and self._panel.isVisible():
            if not self._reflow_timer:
                self._reflow_timer = QTimer(self._mw)
                self._reflow_timer.setSingleShot(True)
                self._reflow_timer.timeout.connect(self._arrange_cards)
            self._reflow_timer.start(100)

    # ============================================================
    #  文本操作
    # ============================================================

    def _copy_text(self, text: str, btn: QPushButton):
        """复制扩写文本到剪切板"""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        btn.setText("✅")
        btn.setStyleSheet(f"color: {tc("accent_green")};")
        QTimer.singleShot(1500, lambda: self._reset_copy_btn(btn))

    def _reset_copy_btn(self, btn: QPushButton):
        """恢复复制按钮"""
        btn.setText("")
        btn.setStyleSheet("")

    def _insert_text(self, text: str):
        """将扩写文本插入到编辑器光标位置"""
        mw = self._mw
        edit = mw.edit_pro_speech  # 单编辑器，正反方指向同一实例

        cursor = edit.textCursor()
        cursor.insertText(text)
        edit.setTextCursor(cursor)
        edit.setFocus()
        mw._update_status("已将扩写文本插入编辑器")

    # ============================================================
    #  JSON 容错解析（处理 AI 常见格式错误）
    # ============================================================

    def _find_matching_bracket(self, text: str, start: int, open_ch: str, close_ch: str) -> int:
        """括号计数：从 start 位置（指向 open_ch）开始，找到匹配的 close_ch 位置。
        返回匹配位置索引，若未找到返回 -1。正确处理字符串和转义。"""
        depth = 0
        pos = start
        in_string = False
        escape_next = False
        while pos < len(text):
            ch = text[pos]
            if escape_next:
                escape_next = False
            elif ch == '\\':
                escape_next = True
            elif ch == '"':
                in_string = not in_string
            elif not in_string:
                if ch == open_ch:
                    depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        return pos
            pos += 1
        return -1

    def _extract_balanced_objects(self, array_text: str) -> list:
        """用括号计数从数组文本中提取每个 {…} 对象，支持嵌套花括号。"""
        objects = []
        if not array_text.startswith('['):
            return objects
        inner = array_text[1:]
        if inner.endswith(']'):
            inner = inner[:-1]
        inner = inner.strip()
        if not inner:
            return objects

        pos = 0
        while pos < len(inner):
            if inner[pos] == '{':
                end = self._find_matching_bracket(inner, pos, '{', '}')
                if end >= 0:
                    objects.append(inner[pos:end + 1])
                    pos = end + 1
                else:
                    pos += 1
            else:
                pos += 1
        return objects

    def _repair_single_object(self, obj_str: str) -> dict | None:
        """尝试修复单个对象 JSON 字符串并解析。"""
        # 1. 标准解析
        try:
            return _json.loads(obj_str)
        except _json.JSONDecodeError:
            pass

        # 2. 去除尾部多余逗号
        fixed = re.sub(r',\s*}', '}', obj_str)
        try:
            return _json.loads(fixed)
        except _json.JSONDecodeError:
            pass

        # 3. 补全不配对的引号
        if fixed.count('"') % 2 != 0:
            fixed += '"'
        try:
            return _json.loads(fixed)
        except _json.JSONDecodeError:
            pass

        # 4. 尝试用括号计数找到 text 字段，将其值替换为占位符后解析
        text_match = re.search(r'"text"\s*:\s*"', fixed)
        if text_match:
            text_val_start = text_match.end()
            text_val_end = self._find_matching_quote(fixed, text_val_start)
            if text_val_end >= 0:
                replacement = fixed[:text_val_start] + '…' + fixed[text_val_end + 1:]
                try:
                    return _json.loads(replacement)
                except _json.JSONDecodeError:
                    pass

        return None

    @staticmethod
    def _find_matching_quote(text: str, start: int) -> int:
        """从 start 位置（已越过起始引号）查找匹配的闭合引号，正确处理转义。"""
        pos = start
        escape_next = False
        while pos < len(text):
            ch = text[pos]
            if escape_next:
                escape_next = False
            elif ch == '\\':
                escape_next = True
            elif ch == '"':
                return pos
            pos += 1
        return -1

    def _extract_schemes_array_by_counting(self, text: str) -> list | None:
        """用括号计数提取 'schemes': [...] 中的数组，处理嵌套的 []（如 highlights）。"""
        match = re.search(r'"schemes"\s*:\s*\[', text)
        if not match:
            return None
        start = match.end() - 1  # 指向 [
        end = self._find_matching_bracket(text, start, '[', ']')
        if end < 0:
            return None
        array_text = text[start:end + 1]
        try:
            return _json.loads(array_text)
        except _json.JSONDecodeError:
            pass

        # 用括号计数逐个提取对象
        objects = self._extract_balanced_objects(array_text)
        if not objects:
            return None

        repaired = []
        for obj_str in objects:
            parsed = self._repair_single_object(obj_str)
            if parsed is not None:
                repaired.append(parsed)
        return repaired if repaired else None

    def _try_complete_json(self, json_text: str, cut_pos: int) -> str | None:
        """尝试在 cut_pos 处截断并补全缺失的括号，返回补全后的合法 JSON 字符串或 None。"""
        truncated = json_text[:cut_pos + 1]
        depth_brace = 0  # { }
        depth_bracket = 0  # [ ]
        in_string = False
        escape_next = False
        for i, ch in enumerate(truncated):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\':
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth_brace += 1
            elif ch == '}':
                depth_brace -= 1
            elif ch == '[':
                depth_bracket += 1
            elif ch == ']':
                depth_bracket -= 1

        if in_string:
            return None

        suffix = ']' * depth_bracket + '}' * depth_brace
        if not suffix:
            return None
        completed = truncated + suffix
        try:
            _json.loads(completed)
            return completed
        except _json.JSONDecodeError:
            return None

    def _robust_json_parse(self, json_text: str) -> tuple:
        """容错 JSON 解析：处理 AI 常见的 JSON 格式错误。返回 (dict | None, error_msg | None)"""
        # 1. 标准解析
        try:
            return _json.loads(json_text), None
        except _json.JSONDecodeError:
            pass

        # 2. 截断到最后一个完整结构
        trunc_bounds = [json_text.rfind("}"), json_text.rfind("]")]
        last_pos = max(trunc_bounds)
        if last_pos >= 0:
            completed = self._try_complete_json(json_text, last_pos)
            if completed:
                try:
                    return _json.loads(completed), None
                except _json.JSONDecodeError:
                    pass

            all_positions = sorted(
                [i for i, ch in enumerate(json_text) if ch in ('}', ']')],
                reverse=True
            )
            for pos in all_positions[:20]:
                if pos == last_pos:
                    continue
                completed = self._try_complete_json(json_text, pos)
                if completed:
                    try:
                        return _json.loads(completed), None
                    except _json.JSONDecodeError:
                        pass

        # 3. 逐字符回退（最多回退 2000 字符）
        for i in range(len(json_text) - 1, max(0, len(json_text) - 2000), -1):
            if json_text[i] in ('"', '}', ']', '\n'):
                try:
                    return _json.loads(json_text[:i + 1]), None
                except _json.JSONDecodeError:
                    continue

        # 4. 括号计数提取 schemes 数组
        schemes = self._extract_schemes_array_by_counting(json_text)
        if schemes is not None:
            return {"schemes": schemes}, None

        return None, "无法解析 AI 返回的 JSON 格式"
