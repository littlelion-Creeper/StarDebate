"""StarDebate ★ 辩之星 — UI 面板组装 Mixin
============================================================================
将 StarDebateWindow 的 _setup_ui 及所有子页面构建 / 信号连接方法抽离至此。
与 GlueCodeMixin 通过多重继承组合。
============================================================================
"""
from components.theme_colors import tc, refresh
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QSplitter, QTreeWidget,
    QStackedWidget,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

# ── 共享工具 ──────────────────────────────────────────────────────────
from workers.common import FlowLayout, AILoadingBar

# ── UI 构建所需的组件类 ───────────────────────────────────────────────
from components.title_bar import TitleBar
from workers.structure import StructureTreeManager
from workers.speech_editor import SpeechEditorManager, SpeechEditor
from workers.ref_doc import RefDocManager
from workers.stardebate_format import StardebateModulePanel


class UIAssemblyMixin:
    """UI 面板组装 — 将所有管理器构建的面板组装到主布局。

    此类仅包含 _setup_ui 及子页面构建方法，不包含任何业务逻辑或面板切换。
    """

    # =====================================================================
    # _setup_ui — 核心 UI 组装（仅组装，不含业务逻辑）
    # =====================================================================
    def _setup_ui(self):
        """构建界面布局 — 将所有管理器构建的面板组装到一起"""
        from components.shadow_container import ShadowContainer

        container = ShadowContainer(self)
        self._shadow_container = container
        self.setCentralWidget(container)
        content = container.get_content()

        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ── 自定义标题栏（替代原生标题栏，融合顶部菜单栏）─────────
        self._title_bar = TitleBar(self, "StarDebate", "★",
                                   icon_path="icon/common/main.png")
        main_layout.addWidget(self._title_bar)

        # ★ 将菜单栏注入标题栏（TopNavManager → TitleBar 注入区）
        self._top_nav_mgr.inject_into_titlebar(self._title_bar)
        self.btn_file = self._top_nav_mgr.get_button("file_menu")
        self.btn_edit = self._top_nav_mgr.get_button("edit_menu")
        self.btn_view = self._top_nav_mgr.get_button("view_menu")
        self.btn_help = self._top_nav_mgr.get_button("help_btn")

        # ── 中间内容区域：QSplitter ──────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)

        # ── 左侧面板：项目树 ──────────────────────────────────────────
        tree_panel = QFrame()
        tree_panel.setMinimumWidth(550)
        tree_panel.setObjectName("treePanel")
        self._tree_panel = tree_panel
        tree_layout = QVBoxLayout(tree_panel)
        tree_layout.setContentsMargins(10, 10, 10, 10)
        tree_layout.setSpacing(6)

        tree_title = QLabel("项目浏览器")
        tree_title.setObjectName("treeTitle")

        self.project_tree = QTreeWidget()
        self.project_tree.setObjectName("projectTree")
        self.project_tree.setHeaderHidden(True)
        self.project_tree.setIndentation(16)
        self.project_tree.setAnimated(True)
        self.project_tree.setCursor(Qt.PointingHandCursor)
        self.project_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.project_tree.customContextMenuRequested.connect(self._project_explorer.on_context_menu)
        self._project_explorer.populate_tree()

        tree_layout.addWidget(tree_title)
        tree_layout.addWidget(self.project_tree)

        # ── 结构树面板（StructureTreeManager）────────────────────────
        self._structure_mgr = StructureTreeManager(self)
        self._structure_mgr.build_ui()
        self._structure_panel = self._structure_mgr
        self.structure_tree = self._structure_mgr.structure_tree

        # ── 赛程面板（TournamentManager 可能为None）──────────────────
        if self._tournament_mgr is not None:
            format_panel = self._tournament_mgr.build_panel()
            format_panel.setVisible(False)
        else:
            format_panel = QFrame()
        self._format_panel = format_panel

        # ── 左侧垂直分栏 ─────────────────────────────────────────────
        left_vsplit = QSplitter(Qt.Vertical)
        left_vsplit.setHandleWidth(2)
        left_vsplit.setObjectName("leftVerticalSplitter")
        left_vsplit.addWidget(tree_panel)                # 0: 项目树
        left_vsplit.addWidget(self._structure_mgr)       # 1: 结构树
        left_vsplit.addWidget(format_panel)              # 2: 赛程面板
        left_vsplit.setStretchFactor(0, 1)
        left_vsplit.setStretchFactor(1, 1)
        left_vsplit.setStretchFactor(2, 1)

        # ── 中央功能区：QStackedWidget ───────────────────────────────
        center_panel = QFrame()
        center_panel.setObjectName("centerPanel")
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(16, 16, 16, 16)

        self.centre_stack = QStackedWidget()

        # 资料稿管理器（需提前创建，供详情页按钮连接）
        self._ref_doc_mgr = RefDocManager()

        # 第 0 页 - 空状态欢迎页
        self._build_page_empty()

        # 第 1 页 - 辩论详情展示
        self._build_page_detail()

        # 第 2 页 - 一辩稿编辑（SpeechEditorManager）
        self._speech_mgr = SpeechEditorManager(self, self.centre_stack)
        self._speech_mgr.build_ui()
        self._nav_mgr.register_module_builder("speech_editor", lambda: self._speech_mgr.build_right_nav_button())

        # 向后兼容别名
        self._setup_speech_compat_aliases()

        # 第 3 页 - AI 分析结果展示
        if self._analysis_mgr is not None:
            self._analysis_mgr.build_ui()
        else:
            self.centre_stack.addWidget(QWidget())

        # 第 4、5 页 - 资料稿管理器
        self._ref_doc_mgr.build_ui(self, self.centre_stack)

        # 第 6 页 - 模拟质询
        if self._cross_mgr is not None:
            self._cross_mgr.build_ui()
        else:
            self.centre_stack.addWidget(QWidget())

        # 第 7 页 - 模拟接质
        if self._accept_mgr is not None:
            self._accept_mgr.build_ui()
        else:
            self.centre_stack.addWidget(QWidget())

        # 第 8 页 - 辩论框架（思维导图）
        if self._framework_mgr is not None:
            self._framework_mgr.build_ui()
        else:
            self.centre_stack.addWidget(QWidget())

        # 第 9 页 - 立论驳论编辑器
        self._build_page_exercise_editor()

        # 介绍与引导页（注入 centre_stack 末尾，不干扰既有索引）
        welcome_mgr = getattr(self, '_welcome_guide_mgr', None)
        if welcome_mgr is not None:
            welcome_mgr.inject_into_centre_stack(self.centre_stack)

        center_layout.addWidget(self.centre_stack)

        # ── 左侧导航栏（NavBarManager 注册表驱动）────────────────────
        nav_panel = self._nav_mgr.build("left")
        self._setup_left_nav_refs()

        # ── 右侧功能面板 ─────────────────────────────────────────────
        # AI写稿面板（可能为None）
        if self._speech_writer_mgr is not None:
            speech_writer_panel = self._speech_writer_mgr.build_panel()
        else:
            speech_writer_panel = QFrame()
        self._speech_writer_panel = speech_writer_panel

        # AI扩写面板（可能为None）
        if self._ai_expand_mgr is not None:
            ai_expand_panel = self._ai_expand_mgr.build_panel()
            self._ai_expand_panel = self._ai_expand_mgr.panel
            self._ai_expand_cards_scroll = self._ai_expand_mgr.cards_scroll
            self._ai_expand_cards_scroll.installEventFilter(self)
        else:
            ai_expand_panel = QFrame()
            self._ai_expand_panel = ai_expand_panel
            self._ai_expand_cards_scroll = None

        # 便签面板（可能为None）
        if self._notes_mgr is not None:
            notes_panel = self._notes_mgr.build_panel()
        else:
            notes_panel = QFrame()
        self._notes_panel = notes_panel

        # AI一辩稿展示面板（立论驳论专用）
        self._build_ex_ai_speech_panel()

        # 模拟训练面板（可能为None）
        if self._train_mgr is not None:
            training_panel = self._train_mgr.build_panel()
        else:
            training_panel = QFrame()
        self._training_panel = training_panel

        # ── 资料池：页面注入中心功能区（可能为None）─────────────────
        if self._material_pool_mgr is not None:
            self._material_pool_mgr.set_centre_stack(self.centre_stack)

        # ── 资料池左侧文件列表面板（可能为None）────────────────────
        if self._material_pool_mgr is not None:
            file_panel = self._material_pool_mgr.build_file_list_panel()
            search_bar = self._material_pool_mgr.build_search_bar()
            self._title_bar.get_right_section().addWidget(search_bar)
        else:
            file_panel = QFrame()
            file_panel.setVisible(False)
        self._material_pool_file_panel = file_panel
        left_vsplit.addWidget(file_panel)
        left_vsplit.setStretchFactor(left_vsplit.count() - 1, 1)

        # ── 右侧导航栏 ──────────────────────────────────────────────
        right_nav_panel = self._nav_mgr.build("right")
        self._setup_right_nav_refs()

        # ── 插件管理面板（可能为None）─────────────────────────────
        if self._plugin_panel_mgr is not None:
            plugin_panel = self._plugin_panel_mgr.build_panel()
            plugin_panel.setVisible(False)
        else:
            plugin_panel = QFrame()
            plugin_panel.setVisible(False)
        self._plugin_panel = plugin_panel

        # ── 插件注册面板容器 ─────────────────────────────────────────
        self._plugin_left_stack = QStackedWidget()
        self._plugin_left_stack.setObjectName("pluginLeftStack")
        self._plugin_left_stack.setMinimumWidth(0)
        self._plugin_left_stack.setVisible(False)
        empty_left = QWidget()
        empty_left.setMinimumWidth(0)
        empty_left.setMaximumWidth(0)
        self._plugin_left_stack.addWidget(empty_left)
        self._plugin_left_panel_map: dict[str, int] = {}

        self._plugin_right_stack = QStackedWidget()
        self._plugin_right_stack.setObjectName("pluginRightStack")
        self._plugin_right_stack.setMinimumWidth(0)
        self._plugin_right_stack.setVisible(False)
        empty_right = QWidget()
        empty_right.setMinimumWidth(0)
        empty_right.setMaximumWidth(0)
        self._plugin_right_stack.addWidget(empty_right)
        self._plugin_right_panel_map: dict[str, int] = {}

        # ── .stardebate 模块浏览面板 ─────────────────────────────────
        self._stdb_module_panel = None  # 由 StarDebate_app 在 _setup_ui 之后创建并插入 left_vsplit

        # ── Splitter 组装 ────────────────────────────────────────────
        splitter.addWidget(left_vsplit)                      # 0
        splitter.addWidget(self._ex_ai_speech_panel)         # 1
        splitter.addWidget(self._plugin_left_stack)           # 2
        splitter.addWidget(center_panel)                      # 3
        splitter.addWidget(speech_writer_panel)               # 4
        splitter.addWidget(ai_expand_panel)                   # 5
        splitter.addWidget(notes_panel)                       # 6
        splitter.addWidget(training_panel)                    # 7
        splitter.addWidget(plugin_panel)                      # 8
        splitter.addWidget(self._plugin_right_stack)          # 9
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setStretchFactor(3, 3)
        splitter.setStretchFactor(4, 1)
        splitter.setStretchFactor(5, 1)
        splitter.setStretchFactor(6, 1)
        splitter.setStretchFactor(7, 1)
        splitter.setStretchFactor(8, 1)
        splitter.setStretchFactor(9, 0)

        # ── 中间容器：左导航 + splitter + 右导航 ────────────────────
        content_wrapper = QWidget()
        content_wrapper_layout = QHBoxLayout(content_wrapper)
        content_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        content_wrapper_layout.setSpacing(0)
        content_wrapper_layout.addWidget(self._nav_mgr.left_panel)
        content_wrapper_layout.addWidget(splitter, 1)
        content_wrapper_layout.addWidget(self._nav_mgr.right_panel)

        # ── 底部状态栏 ──────────────────────────────────────────────
        status_bar = QFrame()
        status_bar.setObjectName("statusBar")
        status_bar.setFixedHeight(36)
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(16, 0, 16, 0)

        self.status_label = QLabel("就绪")
        self.status_label.setFont(QFont("Microsoft YaHei", 9))
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        self._ai_loading_bar = AILoadingBar(self)

        app_version = self._app_cfg.load_full_config().get("version", "1.0.0")
        self.version_label = QLabel(f"v{app_version}")
        self.version_label.setFont(QFont("Microsoft YaHei", 9))
        status_layout.addWidget(self._ai_loading_bar)
        status_layout.addStretch()
        status_layout.addWidget(self.version_label)

        # ── 顶层组装 ─────────────────────────────────────────────────
        main_layout.addWidget(content_wrapper)
        main_layout.addWidget(status_bar)

        # ── 信号连接 ─────────────────────────────────────────────────
        self._connect_signals()

    # =====================================================================
    # UI 子页面构建（私有）
    # =====================================================================

    def _build_page_empty(self):
        """第 0 页 - 空状态欢迎页 (含错误卡片)"""
        page_empty = QWidget()
        empty_layout = QVBoxLayout(page_empty)
        empty_layout.setAlignment(Qt.AlignCenter)

        # ── 欢迎文字 ────────────────────────────────────────
        self.debate_area = QLabel("StarDebate ★ 辩之星\n与你一起专业备赛「AI专业备赛助手」")
        self.debate_area.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        self.debate_area.setStyleSheet(f"color: {tc("border")};")
        self.debate_area.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.debate_area)

        # ── 错误卡片（内嵌在欢迎语下方，默认隐藏）──────────────
        self._error_card = self._build_error_card()
        empty_layout.addWidget(self._error_card)
        empty_layout.setAlignment(self._error_card, Qt.AlignCenter)

        self.centre_stack.addWidget(page_empty)

    def _build_error_card(self):
        """构建错误卡片组件（默认隐藏，有错误时通过外部调用显示）。"""
        from components.error_card import ErrorCardWidget
        card = ErrorCardWidget(self)
        card.setVisible(False)
        return card

    def _build_page_detail(self):
        """第 1 页 - 辩论详情展示页"""
        page_detail = QWidget()
        page_detail.setObjectName("detailPage")
        detail_layout = QVBoxLayout(page_detail)
        detail_layout.setSpacing(12)

        self.lbl_debate_file = QLabel("")
        self.lbl_debate_file.setObjectName("label")
        self.lbl_debate_file.setFont(QFont("Microsoft YaHei", 9))

        self.lbl_format_info = QLabel("")
        self.lbl_format_info.setObjectName("label")
        self.lbl_format_info.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))

        # 正方区域
        pro_frame = QFrame()
        pro_frame.setObjectName("proFrame")
        pro_layout = QVBoxLayout(pro_frame)
        pro_layout.setContentsMargins(14, 14, 14, 14)
        lbl_pro_hdr = QLabel("🟢 正方")
        lbl_pro_hdr.setObjectName("detailProHeader")
        lbl_pro_hdr.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        self.lbl_pro = QLabel("—")
        self.lbl_pro.setObjectName("label")
        self.lbl_pro.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        self.lbl_pro.setWordWrap(True)
        self.lbl_pro_args = QLabel("—")
        self.lbl_pro_args.setObjectName("label")
        self.lbl_pro_args.setFont(QFont("Microsoft YaHei", 11))
        self.lbl_pro_args.setWordWrap(True)
        pro_layout.addWidget(lbl_pro_hdr)
        pro_layout.addWidget(self.lbl_pro)
        pro_layout.addWidget(self.lbl_pro_args)

        # 反方区域
        con_frame = QFrame()
        con_frame.setObjectName("conFrame")
        con_layout = QVBoxLayout(con_frame)
        con_layout.setContentsMargins(14, 14, 14, 14)
        lbl_con_hdr = QLabel("🔴 反方")
        lbl_con_hdr.setObjectName("label")
        lbl_con_hdr.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        self.lbl_con = QLabel("—")
        self.lbl_con.setObjectName("detailConName")
        self.lbl_con.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        self.lbl_con.setWordWrap(True)
        self.lbl_con_args = QLabel("—")
        self.lbl_con_args.setObjectName("label")
        self.lbl_con_args.setFont(QFont("Microsoft YaHei", 11))
        self.lbl_con_args.setWordWrap(True)
        con_layout.addWidget(lbl_con_hdr)
        con_layout.addWidget(self.lbl_con)
        con_layout.addWidget(self.lbl_con_args)

        detail_layout.addWidget(self.lbl_debate_file)
        detail_layout.addWidget(self.lbl_format_info)
        detail_layout.addWidget(pro_frame)
        detail_layout.addWidget(con_frame)

        # 详情页入口按钮（一辩稿按钮连接在 _setup_speech_compat_aliases 中重写）
        btn_detail_speech = QPushButton("创建 / 编辑一辩稿")
        btn_detail_speech.setObjectName("primaryBtn")
        btn_detail_speech.setCursor(Qt.PointingHandCursor)
        btn_detail_speech.setFixedHeight(36)
        btn_detail_speech.clicked.connect(lambda: None)  # 稍后重连
        detail_layout.addWidget(btn_detail_speech)

        btn_detail_ref = QPushButton("创建 / 编辑资料稿")
        btn_detail_ref.setObjectName("primaryBtn")
        btn_detail_ref.setCursor(Qt.PointingHandCursor)
        btn_detail_ref.setFixedHeight(36)
        btn_detail_ref.clicked.connect(self._ref_doc_mgr._on_open_ref_doc)
        detail_layout.addWidget(btn_detail_ref)

        btn_detail_cross = QPushButton("模拟质询")
        btn_detail_cross.setObjectName("primaryBtn")
        btn_detail_cross.setCursor(Qt.PointingHandCursor)
        btn_detail_cross.setFixedHeight(36)
        btn_detail_cross.clicked.connect(self._cross_mgr.start_cross_exam)
        detail_layout.addWidget(btn_detail_cross)

        btn_detail_accept = QPushButton("模拟接质")
        btn_detail_accept.setObjectName("primaryBtn")
        btn_detail_accept.setCursor(Qt.PointingHandCursor)
        btn_detail_accept.setFixedHeight(36)
        btn_detail_accept.clicked.connect(self._accept_mgr.open_page)
        detail_layout.addWidget(btn_detail_accept)

        # 指定赛制按钮（特殊引用保存）
        self.btn_assign_format = QPushButton("指定赛制")
        self.btn_assign_format.setObjectName("primaryBtn")
        self.btn_assign_format.setCursor(Qt.PointingHandCursor)
        self.btn_assign_format.setFixedHeight(36)
        self.btn_assign_format.clicked.connect(self._on_assign_format_from_detail)
        detail_layout.addWidget(self.btn_assign_format)

        detail_layout.addStretch()
        self.centre_stack.addWidget(page_detail)

    def _build_page_exercise_editor(self):
        """第 9 页 - 立论驳论编辑器"""
        page_exercise_editor = QWidget()
        page_exercise_editor.setObjectName("exerciseEditorPage")
        ex_edit_layout = QVBoxLayout(page_exercise_editor)
        ex_edit_layout.setSpacing(4)
        ex_edit_layout.setContentsMargins(8, 8, 8, 8)

        ex_edit_header = QHBoxLayout()
        self._lbl_ex_edit_title = QLabel("立论稿编辑")
        self._lbl_ex_edit_title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        self._lbl_ex_edit_title.setStyleSheet(f"color: {tc("accent_blue")};")
        ex_edit_header.addWidget(self._lbl_ex_edit_title)
        ex_edit_header.addStretch()

        for label, text in [("+定义", "定义："), ("+标准", "标准："), ("+论点", "论点：")]:
            btn = QPushButton(label)
            btn.setObjectName("smallBtn")
            btn.setCursor(Qt.PointingHandCursor)
            self._auto_size_button(btn, label, 24, padding_h=16, min_width=30)
            insert_text = text
            btn.clicked.connect(lambda checked, t=insert_text: self._exercise_editor.insertPlainText(t))
            ex_edit_header.addWidget(btn)

        self._btn_ex_insert_def = ex_edit_header.itemAt(1).widget() if ex_edit_header.count() > 1 else None
        self._btn_ex_insert_std = ex_edit_header.itemAt(2).widget() if ex_edit_header.count() > 2 else None
        self._btn_ex_insert_arg = ex_edit_header.itemAt(3).widget() if ex_edit_header.count() > 3 else None

        ex_edit_layout.addLayout(ex_edit_header)

        self._exercise_editor = SpeechEditor()
        self._exercise_editor.setPlaceholderText("在此撰写你的辩稿...")
        self._exercise_editor.textChanged.connect(self._train_mgr._on_exercise_editor_changed)
        ex_edit_layout.addWidget(self._exercise_editor, stretch=1)

        ex_status_bar = QHBoxLayout()
        self._lbl_ex_editor_status = QLabel("字数: 0  |  行: 0")
        self._lbl_ex_editor_status.setFont(QFont("Microsoft YaHei", 9))
        self._lbl_ex_editor_status.setStyleSheet(f"color: {tc("muted")};")
        ex_status_bar.addWidget(self._lbl_ex_editor_status)
        ex_status_bar.addStretch()
        ex_edit_layout.addLayout(ex_status_bar)

        self.centre_stack.addWidget(page_exercise_editor)

    def _build_ex_ai_speech_panel(self):
        """AI一辩稿展示面板（立论驳论专用，默认隐藏）"""
        panel = QFrame()
        panel.setObjectName("exAISpeechPanel")
        panel.setMinimumWidth(480)
        panel.setVisible(False)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QFrame()
        header.setObjectName("notesHeader")
        header.setFixedHeight(46)
        hd = QHBoxLayout(header)
        hd.setContentsMargins(12, 4, 12, 4)
        self._lbl_ex_ai_title = QLabel("AI一辩稿")
        self._lbl_ex_ai_title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        self._lbl_ex_ai_title.setStyleSheet(f"color: {tc("accent_red")};")
        hd.addWidget(self._lbl_ex_ai_title)
        hd.addStretch()

        self._btn_ex_ai_copy = QPushButton("复制全文")
        self._btn_ex_ai_copy.setObjectName("smallBtn")
        self._btn_ex_ai_copy.setCursor(Qt.PointingHandCursor)
        self._auto_size_button(self._btn_ex_ai_copy, "复制全文", 28)
        self._btn_ex_ai_copy.clicked.connect(self._train_mgr._on_ex_ai_speech_copy)
        hd.addWidget(self._btn_ex_ai_copy)
        lay.addWidget(header)

        self._ex_ai_speech_editor = SpeechEditor()
        self._ex_ai_speech_editor.setReadOnly(True)
        self._ex_ai_speech_editor.setPlaceholderText("AI生成的对手一辩稿将在此展示...")
        lay.addWidget(self._ex_ai_speech_editor, stretch=1)
        self._ex_ai_speech_panel = panel

    def _setup_speech_compat_aliases(self):
        """设置一辩稿编辑器的向后兼容别名"""
        self.edit_pro_speech = self._speech_mgr.edit_pro_speech
        self.edit_con_speech = self._speech_mgr.edit_con_speech
        self.speech_tabs = None  # Tab 已移除
        self.btn_back_to_detail = self._speech_mgr.btn_back_to_detail

        self._speech_mgr.init_keyword_flows()

        self._keyword_bar_pro = None
        self._keyword_bar_con = None
        self._lbl_word_pro = self._speech_mgr._lbl_word
        self._lbl_word_con = self._speech_mgr._lbl_word

        self._custom_glossary_pro = self._speech_mgr.custom_glossary_pro
        self._custom_glossary_con = self._speech_mgr.custom_glossary_con
        self._keywords_pro = self._speech_mgr.keywords_pro
        self._keywords_con = self._speech_mgr.keywords_con

        self._on_create_speech = self._speech_mgr._on_create_speech
        self._load_speech_data = self._speech_mgr._load_speech_data
        self._on_speech_count_update = self._speech_mgr._on_speech_count_update
        self._on_save_speech = self._speech_mgr._on_save_speech
        self._import_speech_writer_text = self._speech_mgr.import_speech_writer_text
        self._refresh_keyword_bar = lambda s: None  # 已移除

        # 一辩稿详情页按钮连接（需要在 speech_mgr 创建后）
        detail_page = self.centre_stack.widget(1)
        if detail_page:
            for btn in detail_page.findChildren(QPushButton):
                if btn.text() == "创建 / 编辑一辩稿":
                    btn.clicked.disconnect()
                    btn.clicked.connect(self._speech_mgr._on_create_speech)

    def _setup_left_nav_refs(self):
        """设置左侧导航按钮的向后兼容引用"""
        self.btn_toggle_project_tree = self._nav_mgr.get_button("project_tree")
        self.btn_toggle_structure_tree = self._nav_mgr.get_button("structure_tree")
        self.btn_toggle_match_schedule = self._nav_mgr.get_button("match_schedule")
        self.btn_toggle_stdb_browser = self._nav_mgr.get_button("stardebate_browser")
        self.btn_new_debate = self._nav_mgr.get_button("new_debate")
        self.btn_framework = self._nav_mgr.get_button("framework")
        self.btn_create_speech = self._nav_mgr.get_button("create_speech")
        self.btn_ref_doc = self._nav_mgr.get_button("ref_doc")
        self.btn_ref_cards = self._nav_mgr.get_button("ref_cards")
        self.btn_settings = self._nav_mgr.get_button("settings")
        self._left_plugin_btns_layout = self._nav_mgr.plugin_left_layout

    def _setup_right_nav_refs(self):
        """设置右侧导航按钮的向后兼容引用"""
        self._btn_toggle_speech_writer = self._nav_mgr.get_button("speech_writer")
        self._btn_toggle_ai_expand = self._nav_mgr.get_button("ai_expand")
        self._btn_toggle_notes = self._nav_mgr.get_button("notes")
        self._btn_toggle_training = self._nav_mgr.get_button("training")
        self.btn_ai_framework = self._nav_mgr.get_button("ai_framework")
        self.btn_cross_exam = self._nav_mgr.get_button("cross_exam")
        self.btn_accept_exam = self._nav_mgr.get_button("accept_exam")
        self._btn_toggle_plugins = self._nav_mgr.get_button("plugin_manager")
        self._right_plugin_btns_layout = self._nav_mgr.plugin_right_layout

    def _connect_signals(self):
        """连接全部信号"""
        # 左侧导航
        self.btn_toggle_project_tree.clicked.connect(self._toggle_project_tree)
        self.btn_toggle_structure_tree.clicked.connect(self._toggle_structure_tree)
        self.btn_toggle_match_schedule.clicked.connect(self._toggle_match_schedule)
        self.btn_toggle_stdb_browser.clicked.connect(self._toggle_stdb_browser)
        self.btn_new_debate.clicked.connect(self._on_new_debate)
        self.btn_ref_doc.clicked.connect(self._ref_doc_mgr._on_open_ref_doc)
        self.btn_ref_cards.clicked.connect(self._ref_doc_mgr._on_show_ref_cards)
        self.btn_framework.clicked.connect(self._on_framework)
        self.btn_settings.clicked.connect(self._on_open_settings)

        # 右侧导航
        self.btn_ai_framework.clicked.connect(self._framework_mgr.start_ai_framework)
        self._btn_toggle_plugins.clicked.connect(self._toggle_plugins_panel)

        # 树控件
        self.project_tree.itemClicked.connect(self._project_explorer.on_item_clicked)

        # 词汇索引信号（委托 speech_mgr）
        self._speech_mgr.setup_signal_connections()

        # 资料稿表格列宽比
        QTimer.singleShot(0, self._ref_doc_mgr.apply_column_ratio)

        # 插件导航按钮初始化
        self._left_nav_btns = self._nav_mgr.plugin_left_btns
        self._right_nav_btns = self._nav_mgr.plugin_right_btns
        for delay in (200, 800):
            QTimer.singleShot(delay, lambda: (
                self._nav_mgr.rebuild_plugin_buttons(self._plugin_manager),
                self._top_nav_mgr.rebuild_plugin_buttons(self._plugin_manager)
            ))
