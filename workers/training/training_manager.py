"""模拟训练管理器 — 面板框架 + 子功能注册发现 + 入口页自动排版"""
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont, QFontMetrics
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QWidget, QScrollArea,
)
from workers.nav_bar.nav_bar_manager import NavBarManager


class TrainingManager:
    """模拟训练管理器：面板框架 + 入口页自动排版 + 子功能委托"""

    def __init__(self, mw):
        """mw: StarDebateWindow 主窗口实例"""
        self._mw = mw

        # ---- 面板状态 ----
        self._visible: bool = False

        # ---- 子功能管理器实例（延迟创建）----
        self._sub_managers: dict = {}  # {feature_id: manager_instance}
        self._sub_page_map: dict = {}  # {feature_id: (start_idx, count)}

        # ---- 向后兼容的训练数据（委托至子管理器）----
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
        self._current_history_session: dict = {}

        # ---- 向后兼容的立论驳论数据（委托至 ExerciseManager）----
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

    # ==================== UI 构建 ====================

    def build_panel(self) -> QFrame:
        """构建模拟训练面板，返回 QFrame"""
        training_panel = QFrame()
        training_panel.setObjectName("trainingPanel")
        training_panel.setMinimumWidth(480)
        training_panel.setMaximumWidth(2400)
        train_layout = QVBoxLayout(training_panel)
        train_layout.setContentsMargins(0, 0, 0, 0)
        train_layout.setSpacing(0)

        # 标题栏
        train_header = QFrame()
        train_header.setObjectName("notesHeader")
        train_header.setFixedHeight(46)
        th_layout = QHBoxLayout(train_header)
        th_layout.setContentsMargins(12, 4, 12, 4)
        th_layout.setSpacing(8)

        self._lbl_train_title = QLabel("模拟训练")
        self._lbl_train_title.setObjectName("trainPanelTitle")
        self._lbl_train_title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        th_layout.addWidget(self._lbl_train_title)
        th_layout.addStretch()

        self._lbl_train_status = QLabel("")
        self._lbl_train_status.setObjectName("trainPanelStatus")
        self._lbl_train_status.setFont(QFont("Microsoft YaHei", 9))
        th_layout.addWidget(self._lbl_train_status)
        th_layout.addStretch()

        # 动态历史按钮容器（由子功能自动注册）
        self._history_btn_layout = QHBoxLayout()
        self._history_btn_layout.setSpacing(6)
        th_layout.addLayout(self._history_btn_layout)

        btn_train_close = QPushButton("−")
        btn_train_close.setObjectName("smallBtn")
        btn_train_close.setFixedSize(28, 28)
        btn_train_close.setToolTip("关闭模拟训练")
        btn_train_close.setCursor(Qt.PointingHandCursor)
        btn_train_close.clicked.connect(self.toggle_visibility)
        th_layout.addWidget(btn_train_close)

        train_layout.addWidget(train_header)

        # 训练内容区 (QStackedWidget)
        self._train_stack = QStackedWidget()
        self._train_stack.setObjectName("trainContentStack")

        # 构建入口页（自动发现子功能）
        self._build_entry_page()

        # 自动发现并构建所有子功能页面
        from workers.training import discover_sub_features
        features = discover_sub_features()
        for feature_id, feature_data in features.items():
            info = feature_data["info"]
            get_mgr_class = feature_data["get_manager"]
            try:
                MgrClass = get_mgr_class()
                mgr = MgrClass(self)  # 传入 TrainingManager 自身
                start_idx = mgr.build_pages(self._train_stack)
                count = self._train_stack.count() - start_idx
                self._sub_managers[feature_id] = mgr
                self._sub_page_map[feature_id] = (start_idx, count)

                # 设置子管理器的页面起始索引（直接赋值，不检查 hasattr）
                mgr._config_idx = start_idx
                mgr._rules_idx = start_idx
            except Exception as e:
                print(f"[TrainingManager] 加载子功能 {feature_id} 失败: {e}")

        # 创建动态历史按钮
        self._build_dynamic_history_buttons()

        train_layout.addWidget(self._train_stack, stretch=1)
        self._train_stack.currentChanged.connect(self._on_page_changed)
        training_panel.setVisible(False)
        self._panel = training_panel

        return training_panel

    def build_nav_button(self):
        """构建右侧导航栏按钮（支持图标文件）"""
        btn = QPushButton()
        btn.setObjectName("navToggleBtn")
        btn.setCheckable(True)
        btn.setChecked(False)
        btn.setToolTip("开关 模拟训练")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(50, 50)
        btn.clicked.connect(self.toggle_visibility)

        item = self._mw._nav_registry.get_item("training")
        icon = NavBarManager.load_nav_icon(item.icon) if item else None
        if icon is not None:
            NavBarManager._apply_icon_to_button(btn, icon)
        else:
            btn.setText("🎯")
        self._btn_toggle = btn

        lbl = QLabel("训练")
        lbl.setObjectName("trainNavLabel")
        lbl.setFont(QFont("Microsoft YaHei", 7))
        lbl.setAlignment(Qt.AlignCenter)
        return btn, lbl

    # ==================== 入口页（自动发现+自动排版）====================

    def _build_entry_page(self, insert_at: int | None = None):
        """构建入口页 — 自动发现子功能并生成卡片（可滚动）

        Args:
            insert_at: 插入位置索引。None 表示追加到末尾，0 表示插入首位。
        """
        page = QWidget()
        page.setObjectName("trainEntryPage")
        outer_layout = QVBoxLayout(page)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # 滚动区域（子功能增多时自动可滚动）
        scroll = QScrollArea()
        scroll.setObjectName("trainEntryScroll")
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_widget.setObjectName("qqScrollContainer")
        layout = QVBoxLayout(scroll_widget)
        layout.setContentsMargins(20, 30, 20, 30)
        layout.setSpacing(16)

        from workers.training import get_sub_features
        sub_features = get_sub_features()

        for info in sub_features:
            fid = info["id"]
            icon = info.get("icon", "📌")
            name = info.get("name", fid)
            accent = info.get("accent_color", "#f9e2af")
            desc = info.get("description", "")
            tags = info.get("tags", [])

            btn = QPushButton()
            btn.setObjectName("trainEntryBtn")
            btn.setCursor(Qt.PointingHandCursor)
            # 不设固定最小高度，由内部文字内容自动撑开

            # 内部布局
            btn_inner = QHBoxLayout()
            btn_inner.setContentsMargins(16, 12, 16, 12)
            btn_inner.setSpacing(12)

            # 图标（顶部对齐，避免多行文字时图标垂直居中偏移）
            lbl_icon = QLabel(icon)
            lbl_icon.setObjectName("trainEntryIcon")
            lbl_icon.setFont(QFont("Segoe UI Emoji", 16))
            lbl_icon.setFixedWidth(40)
            lbl_icon.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
            btn_inner.addWidget(lbl_icon, alignment=Qt.AlignTop)

            # 文字区域
            text_layout = QVBoxLayout()
            text_layout.setSpacing(5)

            lbl_title = QLabel(name)
            lbl_title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
            lbl_title.setStyleSheet(f"color: {accent}; background: transparent; border: none;")
            lbl_title.setWordWrap(True)
            text_layout.addWidget(lbl_title)

            if desc:
                lbl_desc = QLabel(desc)
                lbl_desc.setObjectName("trainEntryDesc")
                lbl_desc.setFont(QFont("Microsoft YaHei", 10))
                lbl_desc.setWordWrap(True)
                text_layout.addWidget(lbl_desc)

            # 标签行（自动换行）
            if tags:
                tags_layout = QHBoxLayout()
                tags_layout.setSpacing(6)
                for tag in tags:
                    tag_lbl = QLabel(tag)
                    tag_lbl.setFont(QFont("Microsoft YaHei", 8))
                    tag_lbl.setStyleSheet(
                        f"color: {accent}; background: transparent; "
                        f"border: 1px solid {accent}44; border-radius: 4px; padding: 2px 6px;"
                    )
                    tags_layout.addWidget(tag_lbl)
                tags_layout.addStretch()
                text_layout.addLayout(tags_layout)

            btn_inner.addLayout(text_layout, stretch=1)

            # 箭头（顶部对齐）
            lbl_arrow = QLabel("→")
            lbl_arrow.setObjectName("trainEntryArrow")
            lbl_arrow.setFont(QFont("Microsoft YaHei", 13))
            lbl_arrow.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
            lbl_arrow.setFixedWidth(20)
            btn_inner.addWidget(lbl_arrow, alignment=Qt.AlignTop)

            btn.setLayout(btn_inner)

            # 点击跳转到子功能首页
            btn.clicked.connect(lambda checked, fid=fid: self._on_entry_clicked(fid))
            layout.addWidget(btn, alignment=Qt.AlignTop)

        layout.addStretch()
        scroll.setWidget(scroll_widget)
        outer_layout.addWidget(scroll)
        if insert_at is not None:
            self._train_stack.insertWidget(insert_at, page)
        else:
            self._train_stack.addWidget(page)

    def _build_dynamic_history_buttons(self):
        """清空并重建标题栏中的动态历史按钮"""
        # 清空现有按钮
        while self._history_btn_layout.count():
            item = self._history_btn_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        from workers.training import get_sub_features
        for info in get_sub_features():
            label = info.get("history_label", "")
            if not label:
                continue
            fid = info["id"]

            btn = QPushButton(label)
            btn.setObjectName("smallBtn")
            self._auto_size_button(btn, label, 28)
            btn.setToolTip(f"查看{info['name']}历史记录")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, fid=fid: self._on_history_clicked(fid))
            self._history_btn_layout.addWidget(btn)

    def refresh_sub_features_ui(self):
        """插件开关后调用：刷新训练面板的入口页卡片 + 历史按钮 + 子页面。

        当插件被启用/禁用时，主窗口应调用此方法以同步 UI。
        """
        from workers.training import reset_discovery_cache, discover_sub_features

        # 1. 清除缓存，重新发现子功能
        reset_discovery_cache()
        new_features = discover_sub_features()
        new_ids = set(new_features.keys())

        # 2. 清理已移除的子管理器
        old_ids = set(self._sub_managers.keys())
        removed_ids = old_ids - new_ids
        for fid in removed_ids:
            # 移除子功能在 stack 中的页面
            if fid in self._sub_page_map:
                start_idx, count = self._sub_page_map.pop(fid)
                # 从后往前移除页面（避免索引偏移）
                for _ in range(count):
                    idx = start_idx + count - 1
                    if idx < self._train_stack.count():
                        widget = self._train_stack.widget(idx)
                        self._train_stack.removeWidget(widget)
                        if widget:
                            widget.deleteLater()
                # 更新其他子功能的页面索引
                for other_fid, (other_start, other_count) in list(self._sub_page_map.items()):
                    if other_start > start_idx:
                        self._sub_page_map[other_fid] = (
                            other_start - count, other_count
                        )
            # 清理管理器实例
            if fid in self._sub_managers:
                del self._sub_managers[fid]

        # 3. 重建入口页（插入到索引 0 位）
        old_entry = self._train_stack.widget(0)
        self._train_stack.removeWidget(old_entry)
        if old_entry:
            old_entry.deleteLater()
        self._build_entry_page(insert_at=0)

        # 4. 重建动态历史按钮
        self._build_dynamic_history_buttons()

        # 5. 确保当前显示入口页
        if self._train_stack.currentIndex() != 0:
            self._train_stack.setCurrentIndex(0)

    def _on_entry_clicked(self, feature_id: str):
        """入口卡片点击 → 跳转到子功能首页"""
        mgr = self._sub_managers.get(feature_id)
        if mgr is None:
            return

        if feature_id == "quick_quiz":
            self._train_stack.setCurrentIndex(mgr.config_idx)
        elif feature_id == "exercise":
            mgr.show_rules()
        else:
            # 通用：跳转到子功能第一个页面
            start_idx, _ = self._sub_page_map.get(feature_id, (0, 0))
            if start_idx > 0:
                self._train_stack.setCurrentIndex(start_idx)

    def _on_history_clicked(self, feature_id: str):
        """历史按钮点击 → 跳转到子功能历史页"""
        mgr = self._sub_managers.get(feature_id)
        if mgr is None:
            return
        if hasattr(mgr, 'show_history'):
            mgr.show_history()

    def _on_page_changed(self, index: int):
        """Stack 页面切换 → 更新标题"""
        if index == 0:
            self._lbl_train_title.setText("模拟训练")
            return
        # 检查属于哪个子功能
        for fid, (start, count) in self._sub_page_map.items():
            if start <= index < start + count:
                mgr = self._sub_managers.get(fid)
                from workers.training import get_sub_feature
                feature = get_sub_feature(fid)
                if feature:
                    icon = feature["info"].get("icon", "")
                    name = feature["info"].get("name", fid)
                    self._lbl_train_title.setText(f"{icon} {name}")
                return
        self._lbl_train_title.setText("模拟训练")

    # ==================== 面板控制 ====================

    def toggle_visibility(self):
        """切换模拟训练面板的显示/隐藏（与其他面板互斥）"""
        mw = self._mw

        mw._speech_writer_mgr.close_if_open()

        self._visible = not self._visible
        self._panel.setVisible(self._visible)
        self._btn_toggle.setChecked(self._visible)

        if self._visible:
            mw._ai_expand_mgr.close_if_open()
            mw._notes_mgr.close_if_open()
            if mw._plugins_visible:
                mw._plugins_visible = False
                mw._plugin_panel.setVisible(False)
                mw._btn_toggle_plugins.setChecked(False)
            self._train_stack.setCurrentIndex(0)
            # 刷新快速刷题历史
            qq_mgr = self._sub_managers.get("quick_quiz")
            if qq_mgr:
                qq_mgr._refresh_sessions()
            mw._close_all_plugin_registered_panels()
            mw._update_status("模拟训练面板已打开")
        else:
            mw._update_status("模拟训练面板已关闭")

    def close_if_open(self):
        """供其他面板互斥调用：如果训练面板打开则关闭"""
        if self._visible:
            self._visible = False
            self._panel.setVisible(False)
            self._btn_toggle.setChecked(False)

    # ==================== 工具方法 ====================

    def _auto_size_button(self, btn, text, height, padding_h=24, min_width=40):
        fm = QFontMetrics(btn.font())
        text_width = fm.horizontalAdvance(text)
        btn.setFixedHeight(height)
        btn.setMinimumWidth(max(min_width, text_width + padding_h))

    # ==================== 向后兼容的委托方法 ====================

    def _on_exercise_editor_changed(self):
        """委托至 ExerciseManager"""
        mgr = self._sub_managers.get("exercise")
        if mgr and mgr._ex_active:
            mgr.on_exercise_editor_changed()

    def _on_ex_ai_speech_copy(self):
        """委托至 ExerciseManager"""
        mgr = self._sub_managers.get("exercise")
        if mgr:
            mgr.on_ex_ai_speech_copy()

    def refresh_format_combo(self):
        """委托至 QuickQuizManager"""
        mgr = self._sub_managers.get("quick_quiz")
        if mgr and hasattr(mgr, 'refresh_format_combo'):
            mgr.refresh_format_combo()

    def _on_train_show_history(self):
        mgr = self._sub_managers.get("quick_quiz")
        if mgr:
            mgr.show_history()

    def _on_exercise_show_history(self):
        mgr = self._sub_managers.get("exercise")
        if mgr:
            mgr.show_history()

    def _on_view_session(self, session: dict):
        """查看快速刷题历史会话"""
        mgr = self._sub_managers.get("quick_quiz")
        if mgr:
            mgr._on_view_session(session)

    def _refresh_sessions(self):
        mgr = self._sub_managers.get("quick_quiz")
        if mgr:
            mgr._refresh_sessions()

    # ==================== 属性访问器 ====================

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, value: bool):
        self._visible = value

    @property
    def panel(self):
        return self._panel

    @property
    def btn_toggle(self):
        return self._btn_toggle

    # ---- 训练数据向后兼容（委托至 QuickQuizManager）----
    @property
    def training_visible(self):
        return self._visible

    @property
    def training_active(self):
        mgr = self._sub_managers.get("quick_quiz")
        return mgr._active if mgr else False

    @property
    def training_mode(self):
        mgr = self._sub_managers.get("quick_quiz")
        return mgr._mode if mgr else ""

    @property
    def training_difficulty(self):
        mgr = self._sub_managers.get("quick_quiz")
        return mgr._difficulty if mgr else "medium"

    @property
    def training_format(self):
        mgr = self._sub_managers.get("quick_quiz")
        return mgr._format if mgr else ""

    @property
    def training_position(self):
        mgr = self._sub_managers.get("quick_quiz")
        return mgr._position if mgr else ""

    @property
    def training_questions(self):
        mgr = self._sub_managers.get("quick_quiz")
        return mgr._questions if mgr else []

    @property
    def training_current_index(self):
        mgr = self._sub_managers.get("quick_quiz")
        return mgr._current_index if mgr else -1

    @property
    def training_score(self):
        mgr = self._sub_managers.get("quick_quiz")
        return mgr._score if mgr else 0

    @property
    def training_correct(self):
        mgr = self._sub_managers.get("quick_quiz")
        return mgr._correct if mgr else 0

    @property
    def training_answered(self):
        mgr = self._sub_managers.get("quick_quiz")
        return mgr._answered if mgr else False

    @property
    def train_stack(self):
        return self._train_stack

    # ---- 立论驳论数据向后兼容（委托至 ExerciseManager）----
    def _get_ex_mgr(self):
        return self._sub_managers.get("exercise")

    @property
    def exercise_active(self):
        mgr = self._get_ex_mgr()
        return mgr._ex_active if mgr else False

    @property
    def exercise_phase(self):
        mgr = self._get_ex_mgr()
        return mgr._ex_phase if mgr else ""

    @property
    def exercise_topic_data(self):
        mgr = self._get_ex_mgr()
        return mgr._ex_topic_data if mgr else {}

    @property
    def exercise_position_speech(self):
        mgr = self._get_ex_mgr()
        return mgr._ex_position_speech if mgr else ""

    @property
    def exercise_ai_speech(self):
        mgr = self._get_ex_mgr()
        return mgr._ex_ai_speech if mgr else ""

    @property
    def exercise_rebuttal_speech(self):
        mgr = self._get_ex_mgr()
        return mgr._ex_rebuttal_speech if mgr else ""

    @property
    def exercise_eval_data(self):
        mgr = self._get_ex_mgr()
        return mgr._ex_eval_data if mgr else {}

    @property
    def exercise_remaining_seconds(self):
        mgr = self._get_ex_mgr()
        return mgr._ex_remaining_seconds if mgr else 0

    @property
    def exercise_opponent_ready(self):
        mgr = self._get_ex_mgr()
        return mgr._ex_opponent_ready if mgr else False

    @property
    def exercise_position_submitted(self):
        mgr = self._get_ex_mgr()
        return mgr._ex_position_submitted if mgr else False
