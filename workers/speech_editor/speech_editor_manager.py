from components.theme_colors import tc, refresh
"""一辩稿编辑管理器：UI构建 + 全部业务逻辑

管理 StarDebate 的一辩稿编辑功能：
- 单编辑器页面，通过结构树节点切换正反方（centre_stack 第2页）
- 自定义词汇索引（正/反方独立）
- 字数实时统计
- 文件持久化（读写 JSON，pro.json / con.json 分开放）

使用方式：
    mgr = SpeechEditorManager(mw, centre_stack)
    mgr.build_ui()           # 构建 UI 页面（添加到 centre_stack 索引2）
    btn, lbl = mgr.build_right_nav_button()  # 构建右侧导航按钮
"""

import os
import json

from PyQt5.QtWidgets import (
    QUndoStack,
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QTabWidget, QMenu,
    QDialog, QLineEdit, QTextEdit, QDialogButtonBox,
    QListWidget, QListWidgetItem, QTextBrowser, QFrame,
)
from PyQt5.QtCore import Qt, QTimer, QPoint, QRect
from PyQt5.QtGui import QFont, QFontInfo, QTextCharFormat, QColor, QTextCursor

from components.popup_dialog import CustomDialog
from components.star_button import StarButton
from components.svg_renderer import SvgRenderer
from components.title_bar import TitleBar
from components.undo_commands import TextEditCommandMerger
from components.icon_loader import get_module_svg_icon

from .speech_editor_widget import SpeechEditor, KeywordCard, AddKeywordButton
from .hover_card import HoverCard
from .bind_source_dialog import BindSourceDialog
from .paragraph_manager import (
    split_content_to_paragraphs,
    rebuild_content_from_paragraphs,
    get_paragraph_context,
    find_paragraph_by_id,
    update_paragraph_text,
)
from .export_preview_dialog import ExportPreviewDialog


_INDEX_ICON_PATH = os.path.join(
    __import__("components.res_path", fromlist=["get_resource_root"]).get_resource_root(),
    "icon", "index", "index.svg",
)


class SpeechEditorManager:
    """一辩稿编辑管理器：构建 UI 页面 + 管理正/反方一辩稿的编辑、保存、词汇索引"""

    # ========== 常量 ==========
    CENTRE_STACK_INDEX = 2  # centre_stack 中的页面索引

    def __init__(self, mw, centre_stack):
        """初始化管理器

        Args:
            mw: StarDebateWindow 主窗口实例
            centre_stack: QStackedWidget 中央页面栈
        """
        self._mw = mw
        self._centre_stack = centre_stack

        # ---- 当前编辑状态 ----
        self._current_side: str = "pro"  # "pro" 或 "con"
        self._has_content: bool = False  # 是否有任何一辩稿数据

        # ---- 编辑器控件（延迟构建）----
        self._editor: SpeechEditor | None = None  # 单编辑器
        self._merger: TextEditCommandMerger | None = None
        self._lbl_side: QLabel | None = None  # 顶部立场标签
        self._btn_save: StarButton | None = None
        self._btn_glossary: StarButton | None = None
        self._btn_view: StarButton | None = None
        self._btn_ai: StarButton | None = None
        self._btn_export: StarButton | None = None
        self._lbl_word: QLabel | None = None  # 字数统计
        self._empty_placeholder: QWidget | None = None  # 空状态占位

        # ---- 向后兼容别名（指向单编辑器）----
        self.edit_pro_speech: SpeechEditor | None = None
        self.edit_con_speech: SpeechEditor | None = None
        self.speech_tabs = None
        self._keyword_bar_pro = None
        self._keyword_bar_con = None
        self._keyword_flow_pro = None
        self._keyword_flow_con = None
        self._lbl_word_pro: QLabel | None = None
        self._lbl_word_con: QLabel | None = None

        # ---- 导航按钮 ----
        self.btn_create_speech: StarButton | None = None
        self.btn_back_to_detail: StarButton | None = None

        # ---- 关键词卡片数据（按 side 分开）----
        self.keywords_pro: list[dict] = []
        self.keywords_con: list[dict] = []

        # ---- 自定义词汇索引（按 side 分开）----
        self.custom_glossary_pro: dict[str, str] = {}
        self.custom_glossary_con: dict[str, str] = {}

        # ---- 段落数据（按 side 分开）----
        self.paragraphs_pro: list[dict] = []
        self.paragraphs_con: list[dict] = []

        # ---- 词汇索引开关 ----
        self._glossary_enabled: bool = True
        self._glossary_scan_timer: QTimer | None = None
        self._last_clicked_speech_data: dict | None = None  # 树控件点击时暂存

        # ── 悬浮卡片 ──────────────────────────────────────
        self._hover_card: HoverCard | None = None

        # ── 撤销栈 ──────────────────────────────────────
        self._undo_stack = QUndoStack()
        from components.undo_coordinator import UndoCoordinator
        UndoCoordinator.instance().register_stack("speech_editor", self._undo_stack)

    # ========== 辅助方法 ==========

    @staticmethod
    def _side_label(side: str) -> str:
        """返回 side 的中文标签"""
        return "正方" if side == "pro" else "反方"

    @staticmethod
    def _side_emoji(side: str) -> str:
        """返回 side 的 emoji"""
        return "🟢" if side == "pro" else "🔴"

    def _get_merger(self, side: str) -> "TextEditCommandMerger":
        """返回 TextEditCommandMerger 实例"""
        return self._merger

    @property
    def current_side(self) -> str:
        """获取当前编辑的 side"""
        return self._current_side

    @staticmethod
    def _wrap_tooltip_text(text: str, chars_per_line: int = 20) -> str:
        """将纯文本按固定字数强制换行"""
        if not text:
            return text
        if text.strip().startswith("<html"):
            return text
        lines = text.split("\n")
        wrapped_lines = []
        for line in lines:
            if len(line) <= chars_per_line:
                wrapped_lines.append(line)
            else:
                for i in range(0, len(line), chars_per_line):
                    wrapped_lines.append(line[i:i + chars_per_line])
        return "\n".join(wrapped_lines)

    # ========== 旧数据迁移 ==========

    def _maybe_migrate_glossary(self, side: str):
        """检测并提示迁移旧格式自定义索引（value 为 str → dict）"""
        custom_glossary = (
            self.custom_glossary_pro if side == "pro" else self.custom_glossary_con
        )
        needs_migration = any(
            isinstance(v, str) for v in custom_glossary.values()
        )
        if not needs_migration:
            return

        label = self._side_label(side)
        old_count = sum(1 for v in custom_glossary.values() if isinstance(v, str))
        result = CustomDialog.question(
            self._mw,
            "检测到旧版索引",
            f"{label}一辩稿中检测到 {old_count} 条旧版格式的索引。\n\n"
            f"是否升级为新格式以支持资料和便签绑定？\n"
            f"（升级后原有索引仍可正常使用）",
            buttons=[("稍后", "later"), ("现在升级", "upgrade")],
        )
        if result != "upgrade":
            return

        # 执行迁移
        migrated = 0
        for term, value in list(custom_glossary.items()):
            if isinstance(value, str):
                custom_glossary[term] = {
                    "explanation": value,
                    "sources": [],
                }
                migrated += 1

        self._apply_glossary_highlights(self._editor)
        self._mw._update_status(f"已迁移 {label} {migrated} 条索引为新格式")
        CustomDialog.information(
            self._mw, "升级完成",
            f"已成功升级 {label} {migrated} 条索引。\n"
            f"现在悬浮索引词可显示更多来源信息。"
        )

    # ── 来源绑定 ────────────────────────────────────────

    def _bind_source_for_term(self, word: str, side: str):
        """弹出绑定弹窗，将资料/便签绑定到指定词汇"""
        custom_glossary = (
            self.custom_glossary_pro if side == "pro" else self.custom_glossary_con
        )
        # 确保当前词已存在
        if word not in custom_glossary:
            custom_glossary[word] = {"explanation": "", "sources": []}
        entry = custom_glossary[word]
        if isinstance(entry, str):
            entry = {"explanation": entry, "sources": []}
            custom_glossary[word] = entry

        dlg = BindSourceDialog(word, self._mw, self._mw)
        if dlg.exec_() == QDialog.Accepted:
            result = dlg.get_result()
            # 合并解释
            if result.get("explanation"):
                if entry.get("explanation"):
                    entry["explanation"] = result["explanation"]
                else:
                    entry["explanation"] = result["explanation"]
            # 合并来源（去重）
            existing_sources = entry.get("sources", [])
            existing_keys = set()
            for s in existing_sources:
                if s["type"] == "material":
                    existing_keys.add(("material", s.get("file_path", "")))
                elif s["type"] == "note":
                    existing_keys.add(("note", str(s.get("note_id", ""))))
                elif s["type"] == "speech":
                    existing_keys.add(("speech", s.get("file_path", "")))
            for new_src in result.get("sources", []):
                if new_src["type"] == "material":
                    key = ("material", new_src.get("file_path", ""))
                elif new_src["type"] == "note":
                    key = ("note", str(new_src.get("note_id", "")))
                elif new_src["type"] == "speech":
                    key = ("speech", new_src.get("file_path", ""))
                else:
                    continue
                if key not in existing_keys:
                    existing_sources.append(new_src)
                    existing_keys.add(key)
            entry["sources"] = existing_sources

            self._apply_glossary_highlights(self._editor)
            self._mw._update_status(
                f"已为「{word}」绑定 {len(existing_sources)} 个来源"
            )

    def _open_source_preview(self, source: dict):
        """弹出独立浮动窗口显示来源内容

        Args:
            source: {"type": "material"/"note"/"speech", "title": str, ...}
        """
        import json as _json

        src_type = source.get("type", "")
        title = source.get("title", "来源内容")
        excerpt = source.get("excerpt", "")

        dlg = QDialog(self._mw)
        dlg.setWindowTitle(f"来源预览 — {title}")
        dlg.resize(500, 400)
        dlg.setWindowFlags(
            dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # 标题
        if src_type == "material":
            icon_text = "\U0001F4C4"
        elif src_type == "speech":
            icon_text = "\U0001F4DD"
        else:
            icon_text = "\U0001F4CB"
        lbl_hdr = QLabel(f"{icon_text} {title}")
        lbl_hdr.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        lbl_hdr.setStyleSheet(f"color: {tc('accent_blue')}; background: transparent; border: none;")
        layout.addWidget(lbl_hdr)

        # 内容
        browser = QTextBrowser()
        browser.setObjectName("sourcePreview")
        browser.setFont(QFont("Microsoft YaHei", 10))

        # 根据类型加载完整内容
        if src_type == "speech":
            file_path = source.get("file_path", "")
            if os.path.isfile(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = _json.load(f)
                    browser.setPlainText(data.get("content", "") or "（内容为空）")
                except (_json.JSONDecodeError, OSError):
                    browser.setPlainText("（无法读取文件内容）")
            else:
                browser.setPlainText("（文件不存在）")
        else:
            browser.setPlainText(excerpt if excerpt else "（无内容）")

        browser.setStyleSheet(f"""
            QTextBrowser#sourcePreview {{
                background-color: {tc("surface")};
                color: {tc("text")};
                border: 1px solid {tc("overlay")};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        layout.addWidget(browser, 1)

        # 关闭按钮
        btn_close = StarButton("关闭", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_close.setObjectName("primaryBtn")
        btn_close.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        pg = self._mw.geometry()
        dlg.move(
            pg.x() + (pg.width() - 500) // 2,
            pg.y() + (pg.height() - 400) // 2,
        )
        dlg.exec_()

    # ── 悬浮卡片管理 ────────────────────────────────────

    def _get_or_create_hover_card(self) -> HoverCard:
        """获取或创建 HoverCard 实例"""
        if self._hover_card is None:
            self._hover_card = HoverCard(self._mw)
            self._hover_card.open_source_requested.connect(
                self._on_hover_card_open_source
            )
        return self._hover_card

    def refresh_hover_card_theme(self):
        """主题切换时刷新 HoverCard 的颜色（由 AppConfigManager 调用）"""
        if self._hover_card is not None:
            self._hover_card.refresh_theme_colors()

    def _on_hover_requested(self, term: str, start_pos: int,
                            end_pos: int):
        """悬浮卡片请求显示（由 SpeechEditor.hover_requested 信号触发）"""
        side = self._current_side

        custom_glossary = (
            self.custom_glossary_pro if side == "pro" else self.custom_glossary_con
        )

        entry = custom_glossary.get(term)
        if not entry:
            self._on_hide_hover_requested()
            return

        # 兼容旧格式
        if isinstance(entry, str):
            explanation = entry
            sources = []
        else:
            explanation = entry.get("explanation", "")
            sources_raw = entry.get("sources", [])

            # 检查来源是否仍有效
            sources = []
            for s in sources_raw:
                src_type = s.get("type", "")
                deleted = False
                if src_type == "material":
                    fp = s.get("file_path", "")
                    if not os.path.isfile(fp):
                        deleted = True
                elif src_type == "note":
                    note_id = s.get("note_id", -1)
                    try:
                        notes = self._mw._notes_mgr.notes_data
                        exists = any(n.get("id") == note_id for n in notes)
                        if not exists:
                            deleted = True
                    except Exception:
                        pass
                elif src_type == "speech":
                    fp = s.get("file_path", "")
                    if not os.path.isfile(fp):
                        deleted = True
                info = dict(s)
                if deleted:
                    info["deleted"] = True
                sources.append(info)

        word_screen_rect = self._calc_word_screen_rect(self._editor, start_pos, end_pos)

        card = self._get_or_create_hover_card()
        card.load_data(term, explanation, sources)
        card.show_at(word_screen_rect)

    def _on_hide_hover_requested(self):
        """隐藏悬浮卡片"""
        if self._hover_card:
            self._hover_card.schedule_hide()

    @staticmethod
    def _calc_word_screen_rect(editor, start_pos: int, end_pos: int) -> QRect:
        """计算高亮词在屏幕上的矩形区域

        通过 QTextCursor 定位到词的起止位置，获取 viewport 坐标，
        再通过 mapToGlobal 转换为全局屏幕坐标。
        """
        cursor = QTextCursor(editor.document())
        cursor.setPosition(start_pos)
        start_rect = editor.cursorRect(cursor)
        cursor.setPosition(end_pos)
        end_rect = editor.cursorRect(cursor)

        # 词的矩形：从 start 左上角 到 end 右下角
        vp_rect = QRect(
            start_rect.left(),
            start_rect.top(),
            end_rect.right() - start_rect.left(),
            max(start_rect.height(), end_rect.height())
        )

        # viewport 坐标 → 全局屏幕坐标
        global_tl = editor.viewport().mapToGlobal(vp_rect.topLeft())
        return QRect(global_tl, vp_rect.size())

    def _on_hover_card_open_source(self, source: dict):
        """悬浮卡片上点击"打开"按钮"""
        self._open_source_preview(source)

    # ── 索引缓存构建 ────────────────────────────────────

    def _build_bound_terms_cache(self, side: str) -> list[tuple]:
        """构建索引词位置缓存，供 SpeechEditor.paintEvent 使用

        Returns:
            [(term, start, end, has_sources), ...]
        """
        custom_glossary = (
            self.custom_glossary_pro if side == "pro" else self.custom_glossary_con
        )
        text = self._editor.toPlainText() if self._editor else ""

        if not custom_glossary or not text:
            return []

        cache = []
        for term, value in custom_glossary.items():
            if not term:
                continue
            has_sources = False
            if isinstance(value, dict):
                sources = value.get("sources", [])
                has_sources = len(sources) > 0

            term_len = len(term)
            idx = 0
            while True:
                idx = text.find(term, idx)
                if idx == -1:
                    break
                cache.append((term, idx, idx + term_len, has_sources))
                idx += term_len

        return cache

    # ========== 路径相关 ==========

    def get_speech_filename(self, side: str) -> str | None:
        """根据当前辩论文件路径，生成正方/反方独立的一辩稿文件名"""
        if not self._mw.current_debate_path:
            return None
        dir_name = os.path.dirname(self._mw.current_debate_path)
        base = os.path.splitext(os.path.basename(self._mw.current_debate_path))[0]
        label = self._side_label(side)
        return os.path.join(dir_name, f"{base}_{label}一辩稿.json")

    def derive_debate_path(self, speech_file: str, suffix: str):
        """从一辩稿文件路径推导对应的辩论文件路径并缓存到 mw"""
        dir_name = os.path.dirname(speech_file)
        speech_fname = os.path.basename(speech_file)
        debate_fname = speech_fname.replace(f"{suffix}.json", ".json")
        candidate = os.path.join(dir_name, debate_fname)
        if os.path.isfile(candidate):
            self._mw.current_debate_path = candidate
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    self._mw.current_debate_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._mw.current_debate_data = None

    # ========== UI 构建 ==========

    def build_ui(self) -> QWidget:
        """构建一辩稿编辑页面（centre_stack 第2页），返回 page_speech

        页面结构：
        ┌──────────────────────────────────────────┐
        │ ← 返回辩论详情                           │  toolbar
        ├──────────────────────────────────────────┤
        │ 🟢 正方一辩稿              [字数]        │  立场标签
        ├──────────────────────────────────────────┤
        │                                          │
        │          SpeechEditor 编辑区              │
        │          （含空状态占位）                  │
        │                                          │
        ├──────────────────────────────────────────┤
        │ [■保存■] [索引] [查看分析] [AI分析]      │  工具栏按钮
        └──────────────────────────────────────────┘
        """
        from PyQt5.QtWidgets import QWidget as _QW

        page_speech = QWidget()
        page_speech.setObjectName("speechPage")
        speech_layout = QVBoxLayout(page_speech)
        speech_layout.setSpacing(10)
        speech_layout.setContentsMargins(10, 10, 10, 10)

        # ---- 顶部工具栏 ----
        speech_toolbar = QHBoxLayout()
        speech_toolbar.setSpacing(8)

        self.btn_back_to_detail = StarButton("← 返回辩论详情", ratio_h=0.75, text_align=Qt.AlignLeft)
        self.btn_back_to_detail.clicked.connect(
            lambda: self._centre_stack.setCurrentIndex(1)
        )

        speech_toolbar.addWidget(self.btn_back_to_detail)
        speech_toolbar.addStretch()

        # ---- 立场标签行 ----
        label_row = QHBoxLayout()
        label_row.setSpacing(8)
        self._lbl_side = QLabel("🟢 正方一辩稿")
        self._lbl_side.setObjectName("speechSideLabel")
        self._lbl_side.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        label_row.addWidget(self._lbl_side)
        label_row.addStretch()

        edit_font = QFont("Cascadia Code", 11)
        if QFontInfo(edit_font).family() != "Cascadia Code":
            edit_font = QFont("Consolas", 11)
        self._lbl_word = QLabel("0 字")
        self._lbl_word.setObjectName("speechEditorWordCount")
        self._lbl_word.setFont(edit_font)
        label_row.addWidget(self._lbl_word)

        # ---- 向后兼容别名 ----
        self._lbl_word_pro = self._lbl_word
        self._lbl_word_con = self._lbl_word

        # ---- 编辑器 ----
        self._editor = SpeechEditor()
        self._merger = TextEditCommandMerger(self._editor, self._undo_stack, self._editor)
        self._merger.start()
        self._editor.setObjectName("speechEditor")
        self._editor.setPlaceholderText("请先创建一辩稿...")
        self._editor.setContextMenuPolicy(Qt.CustomContextMenu)
        self._editor.customContextMenuRequested.connect(
            lambda pos: self._on_speech_context_menu(pos, self._current_side)
        )
        self._editor.textChanged.connect(
            lambda: self._on_speech_count_update(self._current_side)
        )

        # ---- 向后兼容别名 ----
        self.edit_pro_speech = self._editor
        self.edit_con_speech = self._editor

        # ---- 空状态占位 ----
        self._build_empty_placeholder()

        # ---- 按钮行 ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_save = StarButton("保存", checkable=False, ratio_h=0.75, text_align=Qt.AlignLeft, accent=tc("accent_blue"))
        self._btn_save.clicked.connect(lambda: self._on_save_speech(self._current_side))

        btn_glossary = StarButton("索引", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_glossary.setToolTip("切换辩论词汇索引高亮\n开启后，鼠标悬停术语将显示解释")
        btn_glossary.clicked.connect(self._toggle_glossary)
        self._btn_glossary = btn_glossary

        btn_view = StarButton("查看分析", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_view.clicked.connect(lambda: self._mw._analysis_mgr.view_analysis(self._current_side))
        self._btn_view = btn_view

        btn_ai = StarButton("AI分析", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_ai.clicked.connect(lambda: self._mw._analysis_mgr.start_analysis(self._current_side))
        self._btn_ai = btn_ai

        btn_export = StarButton(
            "预览导出",
            ratio_h=0.75,
            text_align=Qt.AlignLeft,
            icon=get_module_svg_icon("export"),
        )
        btn_export.clicked.connect(self._on_open_export_preview)
        btn_export.setToolTip("预览一辩稿导出效果并导出为 .docx / .pdf")
        self._btn_export = btn_export

        btn_row.addWidget(self._btn_save)
        btn_row.addStretch()
        btn_row.addWidget(btn_glossary)
        btn_row.addWidget(btn_view)
        btn_row.addWidget(btn_ai)
        btn_row.addWidget(btn_export)

        # ---- 组装 ----
        speech_layout.addLayout(speech_toolbar)
        speech_layout.addLayout(label_row)
        speech_layout.addWidget(self._editor, stretch=1)
        speech_layout.addLayout(btn_row)

        self._centre_stack.addWidget(page_speech)
        return page_speech

    def _build_empty_placeholder(self):
        """构建空状态占位提示（当无一辩稿文件时显示）"""
        from PyQt5.QtWidgets import QLabel as _QL, QVBoxLayout as _VBL
        placeholder = QWidget()
        placeholder.setObjectName("speechEmptyPlaceholder")
        pl_layout = QVBoxLayout(placeholder)
        pl_layout.setAlignment(Qt.AlignCenter)
        lbl_empty = QLabel("请先创建一辩稿")
        lbl_empty.setObjectName("speechEmptyLabel")
        lbl_empty.setFont(QFont("Microsoft YaHei", 16))
        lbl_empty.setAlignment(Qt.AlignCenter)
        lbl_empty.setStyleSheet(f"color: {tc('subtext')};")
        pl_layout.addWidget(lbl_empty)
        self._empty_placeholder = placeholder

    def build_right_nav_button(self) -> tuple:
        """构建右侧导航栏的「一辩稿」按钮，返回 (btn, label)"""
        from PyQt5.QtWidgets import QPushButton
        from workers.nav_bar.nav_bar_manager import NavBarManager

        self.btn_create_speech = QPushButton()
        self.btn_create_speech.setObjectName("navToggleBtn")
        self.btn_create_speech.setToolTip("创建/编辑一辩稿")
        self.btn_create_speech.setCursor(Qt.PointingHandCursor)
        self.btn_create_speech.setFixedSize(50, 50)

        item = self._mw._nav_registry.get_item("create_speech")
        icon = NavBarManager.load_nav_icon(item.icon) if item else None
        if icon is not None:
            NavBarManager._apply_icon_to_button(self.btn_create_speech, icon)
        else:
            self.btn_create_speech.setText("📝")

        self.btn_create_speech.clicked.connect(self._on_create_speech)

        lbl_speech = QLabel("辩稿")
        lbl_speech.setFont(QFont("Microsoft YaHei", 7))
        lbl_speech.setAlignment(Qt.AlignCenter)
        lbl_speech.setObjectName("speechEditorSpeechLabel")

        return self.btn_create_speech, lbl_speech

    def _show_create_speech_dialog(self) -> str | None:
        """弹出立场选择弹窗，返回 "pro" 或 "con"，点取消返回 None"""
        from PyQt5.QtWidgets import QDialog as _QD, QVBoxLayout as _VBL, QHBoxLayout as _HBL, QFrame as _QF, QLabel as _QL
        from components.title_bar import TitleBar

        dialog = _QD(self._mw)
        dialog.setWindowTitle("创建一辩稿")
        dialog.setFixedSize(420, 320)
        dialog.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        dialog.setAttribute(Qt.WA_TranslucentBackground)
        dialog.setWindowModality(Qt.ApplicationModal)

        # 外层容器
        container = _QF(dialog)
        container.setObjectName("createSpeechDialog")
        container.setStyleSheet(f"""
            #createSpeechDialog {{
                background-color: {tc("base")};
                border: 1px solid {tc("border")};
                border-radius: 10px;
            }}
        """)

        main_layout = _VBL(dialog)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)

        layout = _VBL(container)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── TitleBar (compact) ──
        title_bar = TitleBar(dialog, title="创建一辩稿", icon="📝", compact=True)
        title_bar.setStyleSheet(f"""
            TitleBar {{
                background-color: {tc("surface")};
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }}
        """)
        title_bar._close_btn.clicked.disconnect()
        title_bar._close_btn.clicked.connect(dialog.reject)
        layout.addWidget(title_bar)

        # ── 提示文字 ──
        content_widget = _QF()
        content_widget.setObjectName("createSpeechContent")
        content_widget.setStyleSheet("border: none; background: transparent;")
        content_layout = _VBL(content_widget)
        content_layout.setSpacing(12)
        content_layout.setContentsMargins(24, 16, 24, 20)

        lbl_prompt = _QL("请选择要创建的一辩稿立场：")
        lbl_prompt.setFont(QFont("Microsoft YaHei", 12))
        lbl_prompt.setStyleSheet(f"color: {tc('text')}; border: none;")

        content_layout.addWidget(lbl_prompt)

        # ── 正方卡片 ──
        card_pro = StarButton("🟢  从正面阐述观点，论证立场合理性\n    构建完整的论证体系",
                              ratio_h=0.85, text_align=Qt.AlignLeft, auto_size=False)
        card_pro.setFixedHeight(72)
        card_pro.setStyleSheet(f"""
            StarButton {{
                background-color: {tc("surface")};
                border: 1px solid {tc("border")};
                border-radius: 8px;
            }}
            StarButton:hover {{
                background-color: {tc("hover")};
            }}
        """)
        card_pro.clicked.connect(lambda: dialog.accept())

        # ── 反方卡片 ──
        card_con = StarButton("🔴  从反面质疑观点，指出逻辑漏洞\n    提出有力的对立论据",
                              ratio_h=0.85, text_align=Qt.AlignLeft, auto_size=False)
        card_con.setFixedHeight(72)
        card_con.setStyleSheet(f"""
            StarButton {{
                background-color: {tc("surface")};
                border: 1px solid {tc("border")};
                border-radius: 8px;
            }}
            StarButton:hover {{
                background-color: {tc("hover")};
            }}
        """)
        card_con.clicked.connect(lambda: dialog.done(2))

        content_layout.addWidget(card_pro)
        content_layout.addWidget(card_con)

        # ── 取消按钮 ──
        btn_cancel = StarButton("取消", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_cancel.clicked.connect(dialog.reject)
        btn_row = _HBL()
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        content_layout.addLayout(btn_row)
        content_layout.addStretch()

        layout.addWidget(content_widget, 1)

        pg = self._mw.geometry()
        dialog.move(
            pg.x() + (pg.width() - 420) // 2,
            pg.y() + (pg.height() - 320) // 2,
        )

        result = dialog.exec_()
        if result == _QD.Accepted:
            return "pro"
        elif result == 2:
            return "con"
        return None

    # ========== 初始化后回调 ==========

    def init_keyword_flows(self, flow_pro=None, flow_con=None):
        """关键词卡片栏已从编辑器移除，此方法保留为向后兼容空操作"""

    def setup_signal_connections(self):
        """连接信号（词汇索引高亮刷新 + 悬浮卡片）"""
        if self._editor is None:
            return
        # 编辑时实时刷新词汇高亮
        self._editor.textChanged.connect(
            lambda: self._schedule_glossary_refresh(self._editor)
        )
        # 悬浮卡片请求
        self._editor.hover_requested.connect(self._on_hover_requested)
        self._editor.hide_hover_requested.connect(self._on_hide_hover_requested)

    # ========== 核心操作 ==========

    def _on_create_speech(self):
        """打开/切换到一辩稿编辑页，两方都不存在时弹出立场选择"""
        if not self._mw.current_debate_path:
            CustomDialog.warning(self._mw, "提示", "请先在左侧树控件中选择一个辩论文件")
            return

        # 检测两方文件是否都存在
        pro_file = self.get_speech_filename("pro")
        con_file = self.get_speech_filename("con")
        pro_exists = pro_file and os.path.isfile(pro_file)
        con_exists = con_file and os.path.isfile(con_file)

        if not pro_exists and not con_exists:
            # 两方都不存在 → 弹立场选择窗
            side = self._show_create_speech_dialog()
            if side is None:
                return  # 用户点取消
            self._load_speech_data(side)
            self._switch_side(side)
        elif pro_exists and not con_exists:
            self._load_speech_data("pro")
            self._switch_side("pro")
        elif con_exists and not pro_exists:
            self._load_speech_data("con")
            self._switch_side("con")
        else:
            # 两方都存在，默认加载正方
            self._load_speech_data("pro")
            self._switch_side("pro")

        self._centre_stack.setCurrentIndex(self.CENTRE_STACK_INDEX)
        self._mw._update_status("一辩稿编辑页已打开")

    def _switch_side(self, new_side: str):
        """切换到指定立场，更新编辑器数据和所有UI"""
        self._current_side = new_side

        # 更新立场标签
        emoji = self._side_emoji(new_side)
        label_text = self._side_label(new_side)
        if self._lbl_side:
            self._lbl_side.setText(f"{emoji} {label_text}一辩稿")

        # 更新按钮连接的 side
        if self._btn_save:
            self._btn_save.clicked.disconnect()
            self._btn_save.clicked.connect(lambda: self._on_save_speech(new_side))
        if self._btn_view:
            self._btn_view.clicked.disconnect()
            self._btn_view.clicked.connect(lambda: self._mw._analysis_mgr.view_analysis(new_side))
        if self._btn_ai:
            self._btn_ai.clicked.disconnect()
            self._btn_ai.clicked.connect(lambda: self._mw._analysis_mgr.start_analysis(new_side))

        # 更新词汇索引
        self._apply_glossary_highlights(self._editor)
        self._on_speech_count_update(new_side)

    def _save_current_and_switch(self, new_side: str):
        """根据设置决定自动保存或弹窗询问，然后切换立场"""
        # 判断是否有改动
        full_cfg = getattr(self._mw, '_app_cfg', None)
        auto_save = True
        if full_cfg:
            try:
                cfg = full_cfg.load_full_config()
                auto_save = cfg.get("auto_save_on_switch", True)
            except Exception:
                auto_save = True

        if auto_save:
            self._on_save_speech(self._current_side)
            self._load_speech_data(new_side)
            self._switch_side(new_side)
        else:
            result = CustomDialog.question(
                self._mw,
                "保存更改",
                f"当前{self._side_label(self._current_side)}一辩稿尚未保存，是否保存？",
                buttons=[("不保存", "no"), ("取消", "cancel"), ("保存", "yes")],
            )
            if result == "cancel":
                return
            if result == "yes":
                self._on_save_speech(self._current_side)
            self._load_speech_data(new_side)
            self._switch_side(new_side)

    # ========== 数据加载与保存 ==========

    def _load_speech_data(self, side: str):
        """从对应侧独立文件加载一辩稿数据到编辑框，同时加载自定义词汇索引和结构树"""
        speech_file = self.get_speech_filename(side)

        # 清空当前侧数据
        if side == "pro":
            self.custom_glossary_pro.clear()
            self.keywords_pro.clear()
            self.paragraphs_pro.clear()
        else:
            self.custom_glossary_con.clear()
            self.keywords_con.clear()
            self.paragraphs_con.clear()

        # 加载结构树数据
        self._mw._structure_mgr.load_data(side)
        if self._mw._structure_mgr.current_side == side:
            self._mw._structure_mgr._refresh_tree(side)

        if speech_file and os.path.isfile(speech_file):
            try:
                with open(speech_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 阻止 textChanged 触发
                self._editor.blockSignals(True)
                with self._get_merger(side).suspend():
                    self._editor.setPlainText(data.get("content", ""))
                self._editor.blockSignals(False)

                # 加载自定义词汇索引
                custom_glossary = data.get("custom_glossary", {})
                if isinstance(custom_glossary, dict):
                    if side == "pro":
                        self.custom_glossary_pro = custom_glossary
                    else:
                        self.custom_glossary_con = custom_glossary

                # 加载关键词卡片数据（仅供存储，UI已移除）
                kws = data.get("keywords", [])
                if isinstance(kws, list):
                    if side == "pro":
                        self.keywords_pro = kws
                    else:
                        self.keywords_con = kws

                # 加载段落数据
                loaded_paras = data.get("paragraphs", [])
                if isinstance(loaded_paras, list) and loaded_paras:
                    if side == "pro":
                        self.paragraphs_pro = loaded_paras
                    else:
                        self.paragraphs_con = loaded_paras
                else:
                    content = self._editor.toPlainText().strip()
                    leaf_slugs = self._mw._structure_mgr.get_leaf_slugs(side)
                    auto_paras = split_content_to_paragraphs(content, leaf_slugs)
                    if side == "pro":
                        self.paragraphs_pro = auto_paras
                    else:
                        self.paragraphs_con = auto_paras

                self._apply_glossary_highlights(self._editor)
                # 补回被 blockSignals 跳过的字数统计
                self._on_speech_count_update(side)
                # 旧数据迁移检测
                QTimer.singleShot(100, lambda s=side: self._maybe_migrate_glossary(s))
                return
            except (json.JSONDecodeError, OSError) as e:
                label = self._side_label(side)
                self._mw._update_status(f"{label}一辩稿加载失败: {str(e)}")
        self._editor.clear()

    def _on_speech_count_update(self, side: str):
        """实时更新标题行右侧的字数统计"""
        if self._lbl_word and self._editor:
            count = len(self._editor.toPlainText())
            self._lbl_word.setText(f"{count} 字")

    def _on_save_speech(self, side: str):
        """保存指定侧一辩稿（含自定义词汇索引和结构树）"""
        if not self._mw.current_debate_path:
            CustomDialog.warning(self._mw, "提示", "当前没有关联的辩论文件")
            return

        speech_file = self.get_speech_filename(side)
        if not speech_file:
            return

        label = self._side_label(side)
        custom_glossary = (
            self.custom_glossary_pro if side == "pro" else self.custom_glossary_con
        )
        structure_data = self._mw._structure_mgr._get_data(side)
        keywords = self.keywords_pro if side == "pro" else self.keywords_con

        # ── 自动生成/更新 paragraphs ──
        content = self._editor.toPlainText().strip() if self._editor else ""
        leaf_slugs = self._mw._structure_mgr.get_leaf_slugs(side)
        paragraphs = split_content_to_paragraphs(content, leaf_slugs)
        if side == "pro":
            self.paragraphs_pro = paragraphs
        else:
            self.paragraphs_con = paragraphs

        speech_data = {
            "content": content,
            "paragraphs": paragraphs,
            "custom_glossary": custom_glossary,
            "structure_tree": structure_data,
            "keywords": keywords,
        }

        try:
            with open(speech_file, "w", encoding="utf-8") as f:
                json.dump(speech_data, f, ensure_ascii=False, indent=2)
            # 刷新树控件
            project_path = self._mw._get_current_project_path()
            if project_path:
                self._mw._build_tree_from_path(project_path)
            glossary_count = len(custom_glossary)
            struct_count = len(structure_data)
            kw_count = len(keywords)
            para_count = len(paragraphs)
            self._mw._update_status(
                f"{label}一辩稿已保存（{glossary_count} 条索引, "
                f"{struct_count} 个章节, {kw_count} 个关键词, "
                f"{para_count} 个段落）: "
                f"{os.path.basename(speech_file)}"
            )
            CustomDialog.information(
                self._mw, "保存成功",
                f"{label}一辩稿已保存\n"
                f"自定义索引：{glossary_count} 条\n"
                f"结构树章节：{struct_count} 个\n"
                f"关键词卡片：{kw_count} 个\n"
                f"结构化段落：{para_count} 段"
            )
        except OSError as e:
            CustomDialog.error(
                self._mw, "保存失败",
                f"无法保存{label}一辩稿:\n{str(e)}"
            )

    # ========== 预览导出 ==========

    def _on_open_export_preview(self):
        """打开导出预览弹窗。"""
        if not self._editor:
            CustomDialog.warning(self._mw, "提示", "编辑器尚未初始化")
            return
        content = self._editor.toPlainText().strip()
        if not content:
            CustomDialog.warning(self._mw, "提示", "当前一辩稿为空，无法预览导出")
            return
        # 从辩论数据中获取当前立场文本，兜底使用"正方"/"反方"
        side_label = self._side_label(self._current_side)
        data = getattr(self._mw, "current_debate_data", None)
        if data:
            key = "pro_args" if self._current_side == "pro" else "con_args"
            stance = data.get(key, "").strip()
            if stance:
                side_label = stance
        dlg = ExportPreviewDialog(content, side_label=side_label, parent=self._mw)
        dlg.exec_()

    def load_speech_from_file(self, side: str):
        """从文件加载一辩稿（供质询/接质等场景使用）"""
        if not self._mw.current_debate_path or not self._editor:
            return
        dir_name = os.path.dirname(self._mw.current_debate_path)
        base = os.path.splitext(os.path.basename(self._mw.current_debate_path))[0]
        label = self._side_label(side)
        speech_file = os.path.join(dir_name, f"{base}_{label}一辩稿.json")
        if os.path.isfile(speech_file):
            try:
                with open(speech_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                content = data.get("content", "")
                self._editor.setPlainText(content)
            except (json.JSONDecodeError, OSError):
                pass

    def import_speech_writer_text(self, text: str, side: str):
        """将 AI 写稿文本导入到对应立场的一辩稿编辑器"""
        if not self._editor:
            CustomDialog.warning(self._mw, "提示", "编辑器尚未初始化")
            return

        current = self._editor.toPlainText().strip()
        label = "正方" if side == "pro" else "反方"

        if current:
            result = CustomDialog.question(
                self._mw, "确认导入",
                f"{label}一辩稿已有内容，是否替换？\n选择「否」将在末尾追加。",
                buttons=[("取消", "cancel"), ("否", "no"), ("是", "yes")])
            if result == "cancel":
                return
            elif result == "yes":
                self._editor.setPlainText(text)
            else:
                self._editor.setPlainText(current + "\n\n" + text)
        else:
            self._editor.setPlainText(text)

        # 自动切到该立场
        self._switch_side(side)
        self._centre_stack.setCurrentIndex(self.CENTRE_STACK_INDEX)
        self._mw._update_status(f"已将AI写稿内容导入{label}一辩稿")

    # ========== 树控件点击处理 ==========

    def handle_tree_click(self, file_path: str, fname: str) -> bool:
        """处理项目树中一辩稿文件的点击事件，返回 True 表示已处理

        点击时自动检测立场，切换编辑器内容。
        """
        import json as _json

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = _json.load(f)
        except (_json.JSONDecodeError, OSError):
            return False

        # ── 分析文件（独立处理，不涉及编辑器切换）──
        if "_正方一辩稿_分析" in fname:
            self.derive_debate_path(file_path, "_正方一辩稿_分析")
            analysis_text = data.get("analysis", "")
            self._mw._analysis_mgr._show_analysis_page("pro", "正方", analysis_text)
            self._centre_stack.setCurrentIndex(3)
            self._mw._update_status(f"已加载正方分析: {fname}")
            return True

        elif "_反方一辩稿_分析" in fname:
            self.derive_debate_path(file_path, "_反方一辩稿_分析")
            analysis_text = data.get("analysis", "")
            self._mw._analysis_mgr._show_analysis_page("con", "反方", analysis_text)
            self._centre_stack.setCurrentIndex(3)
            self._mw._update_status(f"已加载反方分析: {fname}")
            return True

        # ── 自动检测新旧格式，切换到对应立场 ──
        side = None
        if "_正方一辩稿" in fname:
            side = "pro"
        elif "_反方一辩稿" in fname:
            side = "con"

        if side:
            # 如果当前已有不同立场的未保存内容，先处理切换
            if self._current_side != side:
                # 如果有内容且有未保存变化，按设置处理
                current_text = self._editor.toPlainText().strip()
                # 记录当前文字用于后续比对
                pass

            self.derive_debate_path(file_path, f"__{side}一辩稿")

            # 加载到对应数据侧
            if side == "pro":
                self.custom_glossary_pro = (
                    data.get("custom_glossary", {})
                    if isinstance(data.get("custom_glossary"), dict)
                    else {}
                )
                kws = data.get("keywords", [])
                self.keywords_pro = kws if isinstance(kws, list) else []
            else:
                self.custom_glossary_con = (
                    data.get("custom_glossary", {})
                    if isinstance(data.get("custom_glossary"), dict)
                    else {}
                )
                kws = data.get("keywords", [])
                self.keywords_con = kws if isinstance(kws, list) else []

            # 加载编辑器内容
            self._editor.blockSignals(True)
            self._editor.setPlainText(data.get("content", ""))
            self._editor.blockSignals(False)

            self._apply_glossary_highlights(self._editor)
            self._mw._structure_mgr.load_data(side)
            if self._mw._structure_mgr.current_side == side:
                self._mw._structure_mgr._refresh_tree(side)
            self._switch_side(side)
            self._on_speech_count_update(side)
            self._centre_stack.setCurrentIndex(self.CENTRE_STACK_INDEX)
            self._mw._update_status(
                f"已加载{self._side_label(side)}一辩稿: {fname}"
            )
            return True

        elif "_一辩稿" in fname:
            # 兼容旧版合并的 _一辩稿.json（无正反方区分）
            self.derive_debate_path(file_path, "_一辩稿")
            cg = data.get("custom_glossary", {})
            if isinstance(cg, dict):
                self.custom_glossary_pro = (
                    cg.get("pro", {}) if isinstance(cg.get("pro", {}), dict) else {}
                )
                self.custom_glossary_con = (
                    cg.get("con", {}) if isinstance(cg.get("con", {}), dict) else {}
                )
            self._editor.setPlainText(data.get("pro_speech", ""))
            self._apply_glossary_highlights(self._editor)
            self._mw._structure_mgr.load_legacy_data(data)
            kws = data.get("keywords", {})
            if isinstance(kws, dict):
                self.keywords_pro = (
                    kws.get("pro", []) if isinstance(kws.get("pro"), list) else []
                )
                self.keywords_con = (
                    kws.get("con", []) if isinstance(kws.get("con"), list) else []
                )
            self._switch_side("pro")
            self._centre_stack.setCurrentIndex(self.CENTRE_STACK_INDEX)
            self._mw._update_status(f"已加载一辩稿(旧格式): {fname}")
            return True

        return False

    # ========== 词汇索引管理 ==========

    def _toggle_glossary(self):
        """切换词汇索引开关"""
        self._glossary_enabled = not self._glossary_enabled
        edit = self._editor
        if self._glossary_enabled:
            self._apply_glossary_highlights(edit)
        else:
            text = edit.toPlainText()
            saved_pos = edit.textCursor().position()
            edit._begin_batch_update()
            edit.blockSignals(True)
            edit.setPlainText(text)
            edit.blockSignals(False)
            cursor = edit.textCursor()
            cursor.setPosition(min(saved_pos, len(text)))
            edit.setTextCursor(cursor)
            edit._end_batch_update()
            edit.set_bound_terms_cache([])
        self._mw._update_status(
            f"词汇索引: {'开启' if self._glossary_enabled else '关闭'}"
        )

    def _on_speech_context_menu(self, pos, side: str):
        """编辑一辩稿时的右键菜单，支持添加/编辑/删除自定义词汇索引和来源绑定"""
        edit = self._editor
        custom_glossary = (
            self.custom_glossary_pro if side == "pro" else self.custom_glossary_con
        )

        menu = QMenu(self._mw)
        menu.setObjectName("speechContextMenu")

        selected_text = edit.textCursor().selectedText().strip()
        if selected_text:
            word = selected_text[:20].strip()
        else:
            cursor = edit.cursorForPosition(pos)
            text_pos = cursor.position()
            word, _, _ = self._mw._get_word_under_cursor(edit, text_pos)
            word = word.strip()

        if word and 1 <= len(word) <= 20:
            if word in custom_glossary:
                act_label = menu.addAction(f"「{word}」已有索引")
                act_label.setEnabled(False)

                # 来源绑定（新增）
                entry = custom_glossary[word]
                source_count = 0
                if isinstance(entry, dict):
                    source_count = len(entry.get("sources", []))
                action_bind = menu.addAction(
                    f"绑定资料/便签" +
                    (f"（{source_count} 个来源）" if source_count else "")
                )
                action_bind.triggered.connect(
                    lambda: self._bind_source_for_term(word, side)
                )

                # action_edit = menu.addAction(f"✏️ 编辑索引")
                # action_edit.triggered.connect(
                #     lambda: self._edit_custom_glossary(word, side)
                # )

                action_del = menu.addAction(f"删除索引")
                action_del.triggered.connect(
                    lambda: self._delete_custom_glossary(word, side)
                )
            # else:
                # action_add = menu.addAction(f"为「{word}」添加索引(暂时关闭)")
                # action_add.triggered.connect(
                #     lambda: self._add_custom_glossary(word, side)
                # )

        menu.addSeparator()

        if word and 1 <= len(word) <= 20:
            # 即使不是已有的索引词也允许绑定来源（自动创建索引）
            action_bind_new = menu.addAction(f"为「{word}」绑定资料/便签作为来源")
            action_bind_new.triggered.connect(
                lambda: self._bind_source_for_term(word, side)
            )

        if selected_text and len(selected_text) > 20:
            # action_add_sel = menu.addAction(f"为选中文本添加自定义索引")
            # action_add_sel.triggered.connect(
            #     lambda: self._add_custom_glossary(selected_text[:30], side)
            # )
            # 对长选中文本也允许绑定
            sel_word = selected_text[:30].strip()
            action_bind_sel = menu.addAction(f"为选中文本绑定来源")
            action_bind_sel.triggered.connect(
                lambda: self._bind_source_for_term(sel_word, side)
            )

        total = len(custom_glossary)
        action_manage = menu.addAction(f"管理自定义索引（共 {total} 条）")
        action_manage.triggered.connect(lambda: self._manage_custom_glossary(side))

        # AI扩写
        menu.addSeparator()
        if selected_text:
            expand_keyword = selected_text[:50].strip()
            action_expand = menu.addAction(f"AI扩写「{expand_keyword}」")
            action_expand.triggered.connect(
                lambda: self._mw._on_ai_expand_request(edit, side, selected_text)
            )
        else:
            action_expand = menu.addAction("AI扩写")
            action_expand.setEnabled(False)

        menu.exec_(edit.viewport().mapToGlobal(pos))

    @staticmethod
    def _get_word_under_cursor(edit, pos: int) -> tuple:
        """获取光标/指定位置处的完整中文词语及其范围"""
        if pos < 0 or pos >= len(edit.toPlainText()):
            return "", -1, -1
        text = edit.toPlainText()
        start, end = pos, pos
        while (
            start > 0
            and text[start - 1].strip()
            and text[start - 1] not in "，。；：！？、\n\r\t "
        ):
            start -= 1
        while (
            end < len(text)
            and text[end].strip()
            and text[end] not in "，。；：！？、\n\r\t "
        ):
            end += 1
        return text[start:end], start, end

    def _apply_glossary_highlights(self, edit):
        """扫描文本框，为自定义词汇索引添加高亮（accent 色 + 加粗）"""
        if not self._glossary_enabled:
            edit.setToolTip("")
            return

        if edit is self.edit_con_speech:
            custom_glossary = self.custom_glossary_con
        else:
            custom_glossary = self.custom_glossary_pro
        # 单编辑器模式：根据当前 side 获取对应词汇表
        if edit is self._editor:
            custom_glossary = (
                self.custom_glossary_pro if self._current_side == "pro"
                else self.custom_glossary_con
            )

        if not custom_glossary:
            edit.set_bound_terms_cache([])
            return

        text = edit.toPlainText()

        # 新格式：accent 色 + 加粗（去掉下划线）
        accent_color = QColor(tc("accent"))
        fmt_base = QTextCharFormat()
        fmt_base.setFontWeight(QFont.Bold)
        fmt_base.setForeground(accent_color)

        edit._begin_batch_update()
        saved_cursor_pos = edit.textCursor().position()

        # 重置格式
        edit.blockSignals(True)
        edit.setPlainText(text)

        # 重新应用格式（全程 blockSignals，防止 mergeCharFormat 误触 textChanged）
        for term, entry in custom_glossary.items():
            if not term:
                continue

            # 获取解释文字（兼容新旧格式）
            if isinstance(entry, str):
                explanation = entry
            else:
                explanation = entry.get("explanation", "")

            term_len = len(term)
            idx = 0
            while True:
                idx = text.find(term, idx)
                if idx == -1:
                    break
                fmt = QTextCharFormat(fmt_base)
                if explanation:
                    fmt.setToolTip(
                        self._wrap_tooltip_text(f"{term}: {explanation}")
                    )
                cursor = QTextCursor(edit.document())
                cursor.setPosition(idx)
                cursor.movePosition(
                    QTextCursor.Right, QTextCursor.KeepAnchor, term_len
                )
                cursor.mergeCharFormat(fmt)
                idx += term_len

        edit.blockSignals(False)

        cursor = edit.textCursor()
        cursor.setPosition(min(saved_cursor_pos, len(text)))
        edit.setTextCursor(cursor)
        edit._end_batch_update()

        # 更新索引缓存（供 paintEvent 绘制图标）
        cache = self._build_bound_terms_cache(self._current_side)
        edit.set_bound_terms_cache(cache)

    def _schedule_glossary_refresh(self, edit):
        """防抖：延迟 800ms 后刷新词汇高亮"""
        if self._glossary_scan_timer:
            self._glossary_scan_timer.stop()
        self._glossary_scan_timer = QTimer(self._mw)
        self._glossary_scan_timer.setSingleShot(True)
        self._glossary_scan_timer.timeout.connect(
            lambda e=edit: self._apply_glossary_highlights(e)
        )
        self._glossary_scan_timer.start(800)

    # ========== 自定义词汇索引对话框 ==========

    def _add_custom_glossary(self, word: str, side: str):
        """弹出对话框添加自定义词汇解释"""
        custom_glossary = (
            self.custom_glossary_pro if side == "pro" else self.custom_glossary_con
        )

        dialog = QDialog(self._mw)
        dialog.setWindowTitle(f"添加自定义索引 - 「{word}」")
        dialog.setFixedSize(440, 330)
        dialog.setWindowFlags(
            Qt.FramelessWindowHint |
            (dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        )
        dialog.setAttribute(Qt.WA_TranslucentBackground)
        pg = self._mw.geometry()
        dialog.move(
            pg.x() + (pg.width() - 440) // 2,
            pg.y() + (pg.height() - 300) // 2,
        )

        # 外层圆角容器
        container = QFrame(dialog)
        container.setObjectName("addGlossaryContainer")
        container.setStyleSheet(f"""
            #addGlossaryContainer {{
                background-color: {tc("base")};
                border: 1px solid {tc("border")};
                border-radius: 10px;
            }}
        """)

        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── 使用 components.title_bar.TitleBar ──
        title_bar = TitleBar(dialog, title="添加自定义索引", icon="")
        title_bar._min_btn.setVisible(False)
        title_bar._max_btn.setVisible(False)
        _icon_pix = SvgRenderer.render(_INDEX_ICON_PATH, 18, mode="mono",
                                        color=tc("accent_blue"))
        if _icon_pix and not _icon_pix.isNull():
            title_bar._icon_label.setPixmap(_icon_pix)
            title_bar._icon_label.setFixedSize(24, 24)
        title_bar.setStyleSheet(f"""
            TitleBar {{
                background-color: {tc("surface")};
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }}
        """)
        # 关闭 → reject
        title_bar._close_btn.clicked.disconnect()
        title_bar._close_btn.clicked.connect(dialog.reject)
        layout.addWidget(title_bar)

        # 内容区域
        content_widget = QWidget()
        content_widget.setObjectName("addGlossaryContent")
        content_widget.setStyleSheet("border: none; background: transparent;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(12)
        content_layout.setContentsMargins(20, 8, 20, 16)

        lbl_word = QLabel(f"词语：{word}")
        lbl_word.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))

        lbl_hint = QLabel("请输入该词语在辩论语境中的解释：")
        lbl_hint.setFont(QFont("Microsoft YaHei", 10))

        text_edit = QTextEdit()
        text_edit.setObjectName("textEdit")
        text_edit.setPlaceholderText("在此输入自定义解释（将作为悬浮提示显示）...")
        text_edit.setFont(QFont("Microsoft YaHei", 11))
        text_edit.setMinimumHeight(100)

        btn_row = QHBoxLayout()
        btn_cancel = StarButton("取消", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_cancel.clicked.connect(dialog.reject)
        btn_ok = StarButton("确认添加", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_ok.setObjectName("primaryBtn")
        btn_ok.clicked.connect(dialog.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)

        content_layout.addWidget(lbl_word)
        content_layout.addWidget(lbl_hint)
        content_layout.addWidget(text_edit)
        content_layout.addLayout(btn_row)
        layout.addWidget(content_widget, 1)

        if dialog.exec_() == QDialog.Accepted:
            explanation = text_edit.toPlainText().strip()
            if explanation:
                # 新格式：使用 dict 结构
                if word in custom_glossary and isinstance(custom_glossary[word], dict):
                    custom_glossary[word]["explanation"] = explanation
                else:
                    custom_glossary[word] = {"explanation": explanation, "sources": []}
                self._apply_glossary_highlights(edit)
                self._mw._update_status(f"已为「{word}」添加自定义索引")

    def _edit_custom_glossary(self, word: str, side: str):
        """编辑已有的自定义词汇解释"""
        custom_glossary = (
            self.custom_glossary_pro if side == "pro" else self.custom_glossary_con
        )
        edit = self.edit_pro_speech if side == "pro" else self.edit_con_speech
        old_data = custom_glossary.get(word, "")
        old_explanation = (old_data.get("explanation", "")
                          if isinstance(old_data, dict) else old_data)

        dialog = QDialog(self._mw)
        dialog.setWindowTitle(f"编辑自定义索引 - 「{word}」")
        dialog.setFixedSize(440, 330)
        dialog.setWindowFlags(
            Qt.FramelessWindowHint |
            (dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        )
        dialog.setAttribute(Qt.WA_TranslucentBackground)
        pg = self._mw.geometry()
        dialog.move(
            pg.x() + (pg.width() - 440) // 2,
            pg.y() + (pg.height() - 300) // 2,
        )

        # 外层圆角容器
        container = QFrame(dialog)
        container.setObjectName("editGlossaryContainer")
        container.setStyleSheet(f"""
            #editGlossaryContainer {{
                background-color: {tc("base")};
                border: 1px solid {tc("border")};
                border-radius: 10px;
            }}
        """)

        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── 使用 components.title_bar.TitleBar ──
        title_bar = TitleBar(dialog, title="编辑自定义索引", icon="")
        title_bar._min_btn.setVisible(False)
        title_bar._max_btn.setVisible(False)
        _icon_pix = SvgRenderer.render(_INDEX_ICON_PATH, 18, mode="mono",
                                        color=tc("accent_blue"))
        if _icon_pix and not _icon_pix.isNull():
            title_bar._icon_label.setPixmap(_icon_pix)
            title_bar._icon_label.setFixedSize(24, 24)
        title_bar.setStyleSheet(f"""
            TitleBar {{
                background-color: {tc("surface")};
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }}
        """)
        # 关闭 → reject
        title_bar._close_btn.clicked.disconnect()
        title_bar._close_btn.clicked.connect(dialog.reject)
        layout.addWidget(title_bar)

        # 内容区域
        content_widget = QWidget()
        content_widget.setObjectName("editGlossaryContent")
        content_widget.setStyleSheet("border: none; background: transparent;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(12)
        content_layout.setContentsMargins(20, 8, 20, 16)

        lbl_word = QLabel(f"词语：{word}")
        lbl_word.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))

        lbl_hint = QLabel("修改该词语在辩论语境中的解释：")
        lbl_hint.setFont(QFont("Microsoft YaHei", 10))

        text_edit = QTextEdit()
        text_edit.setObjectName("textEdit")
        text_edit.setPlainText(old_explanation)
        text_edit.setFont(QFont("Microsoft YaHei", 11))
        text_edit.setMinimumHeight(100)

        btn_row = QHBoxLayout()
        btn_cancel = StarButton("取消", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_cancel.clicked.connect(dialog.reject)
        btn_ok = StarButton("保存修改", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_ok.setObjectName("primaryBtn")
        btn_ok.clicked.connect(dialog.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)

        layout.addWidget(lbl_word)
        layout.addWidget(lbl_hint)
        layout.addWidget(text_edit)
        layout.addLayout(btn_row)

        if dialog.exec_() == QDialog.Accepted:
            explanation = text_edit.toPlainText().strip()
            if explanation:
                # 保持已有 sources 数据
                if word in custom_glossary and isinstance(custom_glossary[word], dict):
                    custom_glossary[word]["explanation"] = explanation
                else:
                    custom_glossary[word] = {"explanation": explanation, "sources": []}
            else:
                if word in custom_glossary and isinstance(custom_glossary[word], dict):
                    custom_glossary[word]["explanation"] = ""
                else:
                    custom_glossary.pop(word, None)
            self._apply_glossary_highlights(edit)
            self._mw._update_status(f"已更新「{word}」的自定义索引")

    def _delete_custom_glossary(self, word: str, side: str):
        """删除自定义词汇解释"""
        custom_glossary = (
            self.custom_glossary_pro if side == "pro" else self.custom_glossary_con
        )
        edit = self.edit_pro_speech if side == "pro" else self.edit_con_speech

        result = CustomDialog.question(
            self._mw,
            "确认删除",
            f"确定要删除「{word}」的自定义索引吗？",
            buttons=[("否", "no"), ("是", "yes")])
        if result != "yes":
            return

        custom_glossary.pop(word, None)
        self._apply_glossary_highlights(edit)
        self._mw._update_status(f"已删除「{word}」的自定义索引")

    def _manage_custom_glossary(self, side: str):
        """管理所有自定义索引（查看、编辑、删除）"""
        custom_glossary = (
            self.custom_glossary_pro if side == "pro" else self.custom_glossary_con
        )
        edit = self.edit_pro_speech if side == "pro" else self.edit_con_speech

        dialog = QDialog(self._mw)
        label = self._side_label(side)
        dialog.setWindowTitle(f"管理自定义索引 - {label}一辩稿")
        dialog.setFixedSize(520, 420)
        dialog.setWindowFlags(
            Qt.FramelessWindowHint |
            (dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        )
        dialog.setAttribute(Qt.WA_TranslucentBackground)
        pg = self._mw.geometry()
        dialog.move(
            pg.x() + (pg.width() - 520) // 2,
            pg.y() + (pg.height() - 420) // 2,
        )

        # 外层圆角容器
        container = QFrame(dialog)
        container.setObjectName("manageGlossaryContainer")
        container.setStyleSheet(f"""
            #manageGlossaryContainer {{
                background-color: {tc("base")};
                border: 1px solid {tc("border")};
                border-radius: 10px;
            }}
        """)

        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── 使用 components.title_bar.TitleBar ──
        title_bar = TitleBar(dialog, title=f"管理自定义索引 - {label}一辩稿", icon="")
        title_bar._min_btn.setVisible(False)
        title_bar._max_btn.setVisible(False)
        # 设置图标
        from components.res_path import get_resource_root
        _index_icon_path = os.path.join(
            get_resource_root(),
            "icon", "index", "index.svg",
        )
        _icon_pix = SvgRenderer.render(_index_icon_path, 18, mode="mono",
                                        color=tc("accent_blue"))
        if _icon_pix and not _icon_pix.isNull():
            title_bar._icon_label.setPixmap(_icon_pix)
            title_bar._icon_label.setFixedSize(24, 24)
        title_bar.setStyleSheet(f"""
            TitleBar {{
                background-color: {tc("surface")};
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }}
        """)
        # 关闭 → reject
        title_bar._close_btn.clicked.disconnect()
        title_bar._close_btn.clicked.connect(dialog.reject)
        layout.addWidget(title_bar)

        # 内容区域
        content_widget = QWidget()
        content_widget.setObjectName("manageGlossaryContent")
        content_widget.setStyleSheet("border: none; background: transparent;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(16, 8, 16, 14)

        lbl_title = QLabel(
            f"{label}一辩稿 · 自定义索引（共 {len(custom_glossary)} 条）"
        )
        lbl_title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))

        list_widget = QListWidget()
        list_widget.setFont(QFont("Microsoft YaHei", 10))
        list_widget.setSpacing(4)

        if custom_glossary:
            for term, entry in custom_glossary.items():
                # 兼容新旧格式
                if isinstance(entry, dict):
                    expl = entry.get("explanation", "")
                    sc = len(entry.get("sources", []))
                    tip = expl if expl else f"暂无解释 · 已绑定 {sc} 个来源"
                else:
                    expl = str(entry)
                    tip = expl
                    sc = 0
                suffix = f" [{sc}个来源]" if sc else ""
                item = QListWidgetItem(f"📌 {term}{suffix}")
                item.setData(Qt.UserRole, term)
                item.setToolTip(self._wrap_tooltip_text(tip))
                list_widget.addItem(item)
        else:
            item = QListWidgetItem("（暂无自定义索引，可在编辑框右键添加）")
            item.setFlags(Qt.NoItemFlags)
            list_widget.addItem(item)

        btn_row = QHBoxLayout()
        btn_edit = StarButton("编辑选中", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_edit.clicked.connect(
            lambda: self._manage_edit_selected(list_widget, side, dialog)
        )
        btn_del = StarButton("删除选中", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_del.clicked.connect(
            lambda: self._manage_delete_selected(list_widget, side, dialog)
        )
        btn_clear = StarButton("清空全部", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_clear.clicked.connect(lambda: self._manage_clear_all(side, dialog))
        btn_close = StarButton("关闭", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_close.setObjectName("primaryBtn")
        btn_close.clicked.connect(dialog.accept)

        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        btn_row.addWidget(btn_clear)
        btn_row.addWidget(btn_close)

        content_layout.addWidget(lbl_title)
        content_layout.addWidget(list_widget)
        content_layout.addLayout(btn_row)
        layout.addWidget(content_widget, 1)

        dialog.exec_()
        self._apply_glossary_highlights(edit)

    def _manage_edit_selected(self, list_widget, side: str, parent_dialog: QDialog):
        selected = list_widget.currentItem()
        if not selected or not selected.data(Qt.UserRole):
            return
        word = selected.data(Qt.UserRole)
        parent_dialog.accept()
        self._edit_custom_glossary(word, side)

    def _manage_delete_selected(self, list_widget, side: str, parent_dialog: QDialog):
        selected = list_widget.currentItem()
        if not selected or not selected.data(Qt.UserRole):
            return
        word = selected.data(Qt.UserRole)
        parent_dialog.accept()
        self._delete_custom_glossary(word, side)

    def _manage_clear_all(self, side: str, parent_dialog: QDialog):
        label = self._side_label(side)
        result = CustomDialog.question(
            self._mw,
            "确认清空",
            f"确定要清空{label}一辩稿的全部自定义索引吗？",
            buttons=[("否", "no"), ("是", "yes")])
        if result != "yes":
            return
        if side == "pro":
            self.custom_glossary_pro.clear()
        else:
            self.custom_glossary_con.clear()
        parent_dialog.accept()
        edit = self.edit_pro_speech if side == "pro" else self.edit_con_speech
        self._apply_glossary_highlights(edit)
        self._mw._update_status(f"已清空{label}全部自定义索引")

    # ========== 关键词卡片管理 ==========

    def _refresh_keyword_bar(self, side: str):
        """重建关键词卡片栏"""
        flow = self._keyword_flow_pro if side == "pro" else self._keyword_flow_con
        keywords = self.keywords_pro if side == "pro" else self.keywords_con

        # 清空旧卡片
        while flow.count():
            item = flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 重建卡片
        for idx, kw in enumerate(keywords):
            card = KeywordCard(kw["word"], kw.get("note", ""), side)
            card.clicked.connect(
                lambda i=idx, s=side: self._edit_keyword_dialog(s, i)
            )
            card.edit_requested.connect(
                lambda i=idx, s=side: self._edit_keyword_dialog(s, i)
            )
            card.delete_requested.connect(
                lambda i=idx, s=side: self._delete_keyword(s, i)
            )
            flow.addWidget(card)

        # 添加按钮
        btn_add = AddKeywordButton()
        btn_add.clicked.connect(lambda s=side: self._add_keyword_dialog(s))
        flow.addWidget(btn_add)

        # 更新滚动区高度
        bar = self._keyword_bar_pro if side == "pro" else self._keyword_bar_con
        container = bar.widget()
        if container:
            flow.invalidate()
            container.updateGeometry()
            viewport_w = bar.viewport().width()
            if viewport_w > 0:
                needed_h = (
                    flow.heightForWidth(viewport_w)
                    + flow.contentsMargins().top()
                    + flow.contentsMargins().bottom()
                    + 8
                )
            else:
                hint = container.sizeHint()
                needed_h = hint.height() + 8
            max_h = bar.maximumHeight()
            bar.setFixedHeight(min(max(needed_h, bar.minimumHeight()), max_h))

    def _add_keyword_dialog(self, side: str):
        """弹出添加关键词对话框"""
        label = self._side_label(side)
        dlg = QDialog(self._mw)
        dlg.setWindowTitle(f"添加关键词 - {label}一辩稿")
        dlg.setFixedSize(420, 320)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)

        lbl_word = QLabel("关键词名称 *")
        lbl_word.setFont(QFont("Microsoft YaHei", 10))
        edit_word = QLineEdit()
        edit_word.setObjectName("lineEdit")
        edit_word.setPlaceholderText("输入关键词，如：定义权、因果链...")
        edit_word.setFont(QFont("Microsoft YaHei", 11))

        lbl_note = QLabel("注释说明")
        lbl_note.setFont(QFont("Microsoft YaHei", 10))
        edit_note = QTextEdit()
        edit_note.setObjectName("textEdit")
        edit_note.setPlaceholderText("对该关键词的补充说明...")
        edit_note.setFont(QFont("Microsoft YaHei", 11))
        edit_note.setFixedHeight(80)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).clicked.connect(dlg.accept)
        btns.button(QDialogButtonBox.Cancel).clicked.connect(dlg.reject)

        layout.addWidget(lbl_word)
        layout.addWidget(edit_word)
        layout.addWidget(lbl_note)
        layout.addWidget(edit_note)
        layout.addWidget(btns)

        pg = self._mw.geometry()
        dlg.move(
            pg.x() + (pg.width() - 420) // 2,
            pg.y() + (pg.height() - 280) // 2,
        )

        if dlg.exec_() == QDialog.Accepted:
            word = edit_word.text().strip()
            if not word:
                CustomDialog.warning(self._mw, "提示", "关键词名称不能为空")
                return
            note = edit_note.toPlainText().strip()
            keywords = self.keywords_pro if side == "pro" else self.keywords_con
            keywords.insert(0, {"word": word, "note": note, "reference": ""})
            self._refresh_keyword_bar(side)
            self._save_keywords_to_file(side)
            self._mw._update_status(f"{label} 已添加关键词: {word}")

    def _edit_keyword_dialog(self, side: str, idx: int):
        """弹出编辑关键词对话框"""
        keywords = self.keywords_pro if side == "pro" else self.keywords_con
        if idx < 0 or idx >= len(keywords):
            return
        kw = keywords[idx]
        label = self._side_label(side)

        dlg = QDialog(self._mw)
        dlg.setWindowTitle(f"编辑关键词 - {label}一辩稿")
        dlg.setFixedSize(420, 480)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)

        lbl_word = QLabel("关键词名称 *")
        lbl_word.setFont(QFont("Microsoft YaHei", 10))
        edit_word = QLineEdit(kw["word"])
        edit_word.setObjectName("lineEdit")
        edit_word.setFont(QFont("Microsoft YaHei", 11))

        lbl_note = QLabel("注释说明")
        lbl_note.setFont(QFont("Microsoft YaHei", 10))
        edit_note = QTextEdit()
        edit_note.setObjectName("textEdit")
        edit_note.setPlaceholderText("对该关键词的补充说明...")
        edit_note.setPlainText(kw.get("note", ""))
        edit_note.setFont(QFont("Microsoft YaHei", 11))
        edit_note.setFixedHeight(80)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).clicked.connect(dlg.accept)
        btns.button(QDialogButtonBox.Cancel).clicked.connect(dlg.reject)

        layout.addWidget(lbl_word)
        layout.addWidget(edit_word)
        layout.addWidget(lbl_note)
        layout.addWidget(edit_note)
        layout.addWidget(btns)

        pg = self._mw.geometry()
        dlg.move(
            pg.x() + (pg.width() - 420) // 2,
            pg.y() + (pg.height() - 280) // 2,
        )

        if dlg.exec_() == QDialog.Accepted:
            word = edit_word.text().strip()
            if not word:
                CustomDialog.warning(self._mw, "提示", "关键词名称不能为空")
                return
            kw["word"] = word
            kw["note"] = edit_note.toPlainText().strip()
            self._refresh_keyword_bar(side)
            self._save_keywords_to_file(side)
            self._mw._update_status(f"{label} 已更新关键词: {word}")

    def _delete_keyword(self, side: str, idx: int):
        """删除关键词"""
        keywords = self.keywords_pro if side == "pro" else self.keywords_con
        if idx < 0 or idx >= len(keywords):
            return
        word = keywords[idx]["word"]
        label = self._side_label(side)
        result = CustomDialog.question(
            self._mw,
            "确认删除",
            f"确定要删除关键词「{word}」吗？",
            buttons=[("否", "no"), ("是", "yes")])
        if result == "yes":
            del keywords[idx]
            self._refresh_keyword_bar(side)
            self._save_keywords_to_file(side)
            self._mw._update_status(f"{label} 已删除关键词: {word}")

    def _save_keywords_to_file(self, side: str):
        """将关键词数据写入一辩稿 JSON 文件（仅更新 keywords 字段）"""
        if not self._mw.current_debate_path:
            self._mw._update_status("保存关键词失败：未关联辩论文件")
            return
        speech_file = self.get_speech_filename(side)
        if not speech_file:
            self._mw._update_status("保存关键词失败：无法生成文件路径")
            return
        data = {}
        if os.path.isfile(speech_file):
            try:
                with open(speech_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                label = self._side_label(side)
                self._mw._update_status(f"{label}一辩稿加载失败: {str(e)}")
        keywords = self.keywords_pro if side == "pro" else self.keywords_con
        data["keywords"] = keywords
        try:
            os.makedirs(os.path.dirname(speech_file), exist_ok=True)
            with open(speech_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            self._mw._update_status(f"保存关键词失败: {str(e)}")

    # ── .stardebate 编辑器集成 ────────────────────────────────────

    def load_stardebate_data(self, side: str, data: dict):
        """从 .stardebate 文件加载一辩稿数据到编辑器。

        Args:
            side: "pro" 或 "con"
            data: {"content": "", "keywords": [...], "custom_glossary": {...}
        """
        if side == "pro":
            self.keywords_pro = data.get("keywords", []) if isinstance(data.get("keywords"), list) else []
            self.custom_glossary_pro = (
                data.get("custom_glossary", {})
                if isinstance(data.get("custom_glossary"), dict)
                else {}
            )
            if self.edit_pro_speech:
                self.edit_pro_speech.setPlainText(data.get("content", ""))
                self._apply_glossary_highlights(self.edit_pro_speech)
            self._refresh_keyword_bar("pro")
            if self.speech_tabs:
                self.speech_tabs.setCurrentIndex(0)
        else:
            self.keywords_con = data.get("keywords", []) if isinstance(data.get("keywords"), list) else []
            self.custom_glossary_con = (
                data.get("custom_glossary", {})
                if isinstance(data.get("custom_glossary"), dict)
                else {}
            )
            if self.edit_con_speech:
                self.edit_con_speech.setPlainText(data.get("content", ""))
                self._apply_glossary_highlights(self.edit_con_speech)
            self._refresh_keyword_bar("con")
            if self.speech_tabs:
                self.speech_tabs.setCurrentIndex(1)

        self._current_side = side
        self._centre_stack.setCurrentIndex(self.CENTRE_STACK_INDEX)
        self._mw._update_status(f"已加载{self._side_label(side)}一辩稿 [.stardebate]")

    def get_current_data(self) -> dict | None:
        """获取当前活跃侧的编辑器数据，用于保存到 .stardebate。

        Returns:
            dict or None: {"content": str, "keywords": list, "custom_glossary": dict}
        """
        if not hasattr(self, '_current_side'):
            return None

        side = self._current_side
        if side == "pro":
            if not self.edit_pro_speech:
                return None
            return {
                "content": self.edit_pro_speech.toPlainText(),
                "keywords": self.keywords_pro,
                "custom_glossary": self.custom_glossary_pro,
            }
        else:
            if not self.edit_con_speech:
                return None
            return {
                "content": self.edit_con_speech.toPlainText(),
                "keywords": self.keywords_con,
                "custom_glossary": self.custom_glossary_con,
            }

    def get_current_side(self) -> str:
        """获取当前活跃的 side ("pro" 或 "con")。"""
        return getattr(self, '_current_side', 'pro')

    # ── 段落公共 API（供 debate_claw 插件等外部模块使用）──

    def get_paragraphs(self, side: str) -> list:
        """获取指定侧的段落数据。

        Args:
            side: "pro" 或 "con"

        Returns:
            list[dict]: paragraphs 数组，格式见 paragraph_manager.py
        """
        return self.paragraphs_pro if side == "pro" else self.paragraphs_con

    def get_paragraph_context_text(self, side: str) -> str:
        """获取段落结构的 AI 上下文摘要文本。"""
        paras = self.get_paragraphs(side)
        return get_paragraph_context(paras)

    def apply_paragraph_diff(
        self, side: str, paragraph_id: str, new_texts: list,
    ) -> str:
        """接受 AI diff 后更新指定段落并重建 content 文本。

        Args:
            side: "pro" 或 "con"
            paragraph_id: 目标段落 id/slug
            new_texts: 替换后的子段落数组 (list[str])

        Returns:
            str: 重建后的完整 content 文本
        """
        if side == "pro":
            paragraphs = self.paragraphs_pro
        else:
            paragraphs = self.paragraphs_con

        updated = update_paragraph_text(paragraphs, paragraph_id, new_texts)
        if side == "pro":
            self.paragraphs_pro = updated
        else:
            self.paragraphs_con = updated

        # 重建 content
        content = rebuild_content_from_paragraphs(updated)

        # 同步到编辑器
        edit = self.edit_pro_speech if side == "pro" else self.edit_con_speech
        edit.setPlainText(content)
        self._apply_glossary_highlights(edit)

        label = self._side_label(side)
        self._mw._update_status(f"已更新{label}一辩稿段落 [{paragraph_id}]")

        return content
