from components.theme_colors import tc, refresh
from components.star_button import StarButton
"""
MaterialPoolManager — 资料池面板管理器 v1.0
完整功能：文件列表/内容查看/搜索卡片/详细展示/导入导出/索引管理
监视钩子 + 起居注全覆盖
"""
import os, time, shutil, datetime, copy
try:
    import markdown as _md
    _MARKDOWN_AVAILABLE = True
except Exception:
    _MARKDOWN_AVAILABLE = False
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QWidget, QLineEdit, QTextBrowser,
    QTreeWidget, QTreeWidgetItem, QFileDialog, QStackedWidget,
    QMenu, QApplication, QProgressBar,
)
from PyQt5.QtCore import Qt, QTimer, QThreadPool, QRunnable, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QFontMetrics
from components.popup_dialog import CustomDialog
from workers.nav_bar.nav_bar_manager import NavBarManager
from .file_parser import FileParser
from .index_manager import IndexManager
from .local_search import LocalSearcher
from .ai_search import AISearcher
from .file_parser import FileParser
from .detail_page import DetailPage
from .ai_export_worker import AIExportWorker


def _get_mgr():
    try:
        from workers.debug_console.debug_monitor_manager import DebugMonitorManager
        return DebugMonitorManager.instance()
    except: return None
def _log_f(mod, fn, ok, res="", ms=0):
    try:
        m = _get_mgr()
        if m and m.is_monitor_enabled("function_watch"): m.log_function_call(mod, fn, ok, str(res)[:120], duration_ms=ms)
    except: pass
def _log_v(name, old, new):
    try:
        m = _get_mgr()
        if m and m.is_monitor_enabled("variable_watch"): m.log_variable_change(__file__, 0, name, f"{old} → {new}")
    except: pass

class _SWSignals(QObject):
    results_ready = pyqtSignal(list); ai_progress = pyqtSignal(int, int, dict)

class _SearchWorker(QRunnable):
    def __init__(self, query, pool_path, idx, api_cfg, enable_ai):
        super().__init__(); self.q = query; self.p = pool_path; self.idx = idx; self.cfg = api_cfg; self.ai = enable_ai
        self.signals = _SWSignals()
    def run(self):
        try:
            r = LocalSearcher.search(self.q, self.idx, self.p); self.signals.results_ready.emit(r)
            if self.ai and self.cfg and r:
                def cb(c, t, i): self.signals.ai_progress.emit(c, t, i)
                AISearcher.rerank_results(self.q, r, self.cfg, self.p, callback=cb)
                self.signals.results_ready.emit(r)
        except: pass

class MaterialPoolManager:
    def __init__(self, mw):
        self._mw = mw; self._visible = False; self._panel = None
        self._file_list_panel = None; self._search_status = "idle"
        self._search_history = []; self._current_results = []
        self._current_page = 0; self._page_size = 10
        self._index_ready = False; self._index_data = {"files": {}, "inverted": {}}
        self._file_list = []; self._ai_searching = False; self._ai_analysis_progress = 0
        self._ai_completed = 0
        self._content_text = None; self._content_title = None
        self._file_tree = None; self._search_scroll = None
        self._search_container_w = None; self._search_layout = None
        self._detail_page = None; self._result_count_label = None
        self._search_input = None; self._btn_toggle = None
        self._btn_prev = None; self._btn_next = None; self._lbl_page = None
        # AI 总结导出进度面板
        self._export_progress_panel = None
        self._export_progress_bar = None
        self._export_progress_label = None
        self._export_progress_info = None
        self._ai_export_busy = False
        self._thread_pool = QThreadPool(); self._thread_pool.setMaxThreadCount(3)
        # 中心页面索引（在主 centre_stack 中）
        self.IDX_WELCOME = -1; self.IDX_CONTENT = -1
        self.IDX_SEARCH = -1; self.IDX_DETAIL = -1
        _log_f("material_pool", "__init__", True)
    @property
    def visible(self): return self._visible
    @property
    def panel(self): return self._panel
    @property
    def btn_toggle(self): return self._btn_toggle

    # ── UI: 将页面注入主 centre_stack ──
    def set_centre_stack(self, centre_stack):
        """将资料池的 4 个页面添加到主 QStackedWidget 中，记录索引"""
        self.IDX_WELCOME = centre_stack.addWidget(self._build_welcome())
        self.IDX_CONTENT = centre_stack.addWidget(self._build_content())
        self.IDX_SEARCH = centre_stack.addWidget(self._build_search_results())
        self.IDX_DETAIL = centre_stack.addWidget(self._build_detail())

    def build_file_list_panel(self) -> QFrame:
        """构建左侧文件列表面板（插入 left_vsplit）"""
        _log_f("material_pool", "build_panel", True)
        p = self._build_file_list()
        p.setVisible(False)
        self._file_list_panel = p
        self._panel = p  # 兼容旧引用
        return p

    def _mk_btn(self, txt, w, cb):
        b = QPushButton(txt); b.setObjectName("smallBtn"); b.setFixedSize(w, 30); b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(cb); return b

    def _build_file_list(self):
        p = QFrame(); p.setMinimumWidth(550); ly = QVBoxLayout(p); ly.setContentsMargins(8, 8, 8, 8); ly.setSpacing(6)
        self._file_tree = QTreeWidget(); self._file_tree.setHeaderHidden(True); self._file_tree.setIndentation(12)
        self._file_tree.setFont(QFont("Microsoft YaHei", 10)); self._file_tree.setCursor(Qt.PointingHandCursor)
        self._file_tree.itemClicked.connect(self._on_file_clicked)
        self._file_tree.setContextMenuPolicy(Qt.CustomContextMenu); self._file_tree.customContextMenuRequested.connect(self._on_file_menu)
        ly.addWidget(self._file_tree, 1)
        # AI 总结导出进度面板（默认隐藏）
        ly.addWidget(self._build_export_progress_panel())
        br = QHBoxLayout(); br.setSpacing(6)
        btn_import = StarButton("导入", None, layout_mode="text_only", ratio_h=0.7)
        btn_import.clicked.connect(self._on_import)
        br.addWidget(btn_import)
        btn_ai_export = StarButton("AI总结导出", None, layout_mode="text_only", ratio_h=0.7)
        btn_ai_export.clicked.connect(self._on_ai_export_summary)
        br.addWidget(btn_ai_export)
        br.addStretch(); ly.addLayout(br); return p

    def _build_welcome(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setAlignment(Qt.AlignCenter)
        i = QLabel("📚"); i.setObjectName("poolWelcomeIcon"); i.setFont(QFont("Microsoft YaHei", 48)); i.setAlignment(Qt.AlignCenter)
        h = QLabel("资料池 — 统筹与AI智能搜索"); h.setObjectName("poolWelcomeTitle"); h.setFont(QFont("Microsoft YaHei", 16, QFont.Bold)); h.setAlignment(Qt.AlignCenter)
        s = QLabel("导入素材  |  关键词搜索  |  AI语义分析\n支持 MD · PDF · DOCX · XLSX · CSV · TXT")
        s.setObjectName("poolWelcomeSub"); s.setFont(QFont("Microsoft YaHei", 12)); s.setAlignment(Qt.AlignCenter)
        ly.addStretch(); ly.addWidget(i); ly.addSpacing(12); ly.addWidget(h); ly.addSpacing(8); ly.addWidget(s); ly.addStretch(); return w

    def _build_content(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(8, 8, 8, 8); ly.setSpacing(4)
        tr = QHBoxLayout(); self._content_title = QLabel("文件内容")
        self._content_title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold)); self._content_title.setStyleSheet(f"color:{tc("accent_blue")};border:none;")
        tr.addWidget(self._content_title); tr.addStretch()
        self._btn_content_back = StarButton("← 返回", None, layout_mode="text_only", ratio_h=0.7)
        self._btn_content_back.setObjectName("smallBtn")
        self._btn_content_back.clicked.connect(lambda: self._mw.centre_stack.setCurrentIndex(self.IDX_WELCOME))
        tr.addWidget(self._btn_content_back)
        ly.addLayout(tr)
        self._content_text = QTextBrowser(); self._content_text.setObjectName("textEdit"); self._content_text.setOpenExternalLinks(True)
        self._content_text.setFont(QFont("Microsoft YaHei", 13))
        self._content_view = QStackedWidget()
        self._content_view.addWidget(self._content_text)        # 0: 文本
        self._content_view.addWidget(QWidget())                  # 1: 表格(动态替换)
        self._content_view.setCurrentIndex(0)
        ly.addWidget(self._content_view, 1); return w

    def _build_search_results(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(8, 8, 8, 8); ly.setSpacing(6)
        tr = QHBoxLayout(); self._result_count_label = QLabel(""); self._result_count_label.setFont(QFont("Microsoft YaHei", 13))
        self._result_count_label.setObjectName("poolResultCount"); tr.addWidget(self._result_count_label); tr.addStretch()
        self._btn_search_back = StarButton("← 返回", None, layout_mode="text_only", ratio_h=0.7)
        self._btn_search_back.setObjectName("smallBtn")
        self._btn_search_back.clicked.connect(lambda: self._mw.centre_stack.setCurrentIndex(self.IDX_WELCOME))
        tr.addWidget(self._btn_search_back); ly.addLayout(tr)
        sep = QFrame(); sep.setObjectName("searchHLine"); sep.setFrameShape(QFrame.HLine); ly.addWidget(sep)
        self._search_scroll = QScrollArea(); self._search_scroll.setWidgetResizable(True); self._search_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._search_container_w = QWidget()
        self._search_layout = QVBoxLayout(self._search_container_w); self._search_layout.setContentsMargins(4, 4, 4, 4); self._search_layout.setSpacing(8); self._search_layout.addStretch(1)
        self._search_scroll.setWidget(self._search_container_w); ly.addWidget(self._search_scroll, 1)
        pr = QHBoxLayout(); pr.addStretch()
        self._btn_prev = StarButton("< 上一页", None, layout_mode="text_only", ratio_h=0.7)
        self._btn_prev.setObjectName("smallBtn")
        self._btn_prev.clicked.connect(self._prev_page)
        pr.addWidget(self._btn_prev)
        self._lbl_page = QLabel("1/1"); self._lbl_page.setObjectName("searchPageLabel"); self._lbl_page.setFont(QFont("Microsoft YaHei", 10)); pr.addWidget(self._lbl_page)
        self._btn_next = StarButton("下一页 >", None, layout_mode="text_only", ratio_h=0.7)
        self._btn_next.setObjectName("smallBtn")
        self._btn_next.clicked.connect(self._next_page)
        pr.addWidget(self._btn_next); pr.addStretch(); ly.addLayout(pr); return w

    def _build_detail(self):
        self._detail_page = DetailPage()
        return self._detail_page

    # ── UI: SearchBar / NavButton ──
    def build_search_bar(self) -> QWidget:
        c = QWidget(); c.setFixedHeight(32); ly = QHBoxLayout(c); ly.setContentsMargins(4, 0, 4, 0); ly.setSpacing(4)
        self._search_input = QLineEdit(); self._search_input.setObjectName("lineEdit"); self._search_input.setPlaceholderText("搜索资料池..."); self._search_input.setFont(QFont("Microsoft YaHei", 10))
        self._search_input.setFixedSize(400, 32)
        self._search_input.returnPressed.connect(self._on_search); ly.addWidget(self._search_input); ly.addWidget(self._mk_btn("搜索", 80, self._on_search)); return c

    def build_nav_button(self):
        self._btn_toggle = QPushButton(); self._btn_toggle.setObjectName("navToggleBtn"); self._btn_toggle.setCheckable(True)
        self._btn_toggle.setChecked(False); self._btn_toggle.setToolTip("资料池 — 统筹与AI智能搜索"); self._btn_toggle.setCursor(Qt.PointingHandCursor)
        self._btn_toggle.setFixedSize(50, 50); self._btn_toggle.clicked.connect(self.toggle_visibility)
        item = self._mw._nav_registry.get_item("material_pool")
        if item and item.icon:
            icon = NavBarManager.load_nav_icon(item.icon)
            if icon: NavBarManager._apply_icon_to_button(self._btn_toggle, icon)
            else: self._btn_toggle.setText("")
        else: self._btn_toggle.setText("")
        l = QLabel("册府"); l.setObjectName("poolNavLabel"); l.setAlignment(Qt.AlignCenter); return self._btn_toggle, l

    # ── Visibility ──
    def toggle_visibility(self):
        _log_v("_visible", self._visible, not self._visible); self._visible = not self._visible
        if self._file_list_panel: self._file_list_panel.setVisible(self._visible)
        if self._btn_toggle: self._btn_toggle.setChecked(self._visible)
        if self._visible:
            self._refresh_files()
            if not self._index_ready: QTimer.singleShot(100, self._rebuild_index)
            # 切换到中心功能区
            if self.IDX_WELCOME >= 0: self._mw.centre_stack.setCurrentIndex(self.IDX_WELCOME)
            self._mw._update_status("资料池已打开")
        else:
            self._mw.centre_stack.setCurrentIndex(0)
            self._mw._update_status("资料池已关闭")

    def close_if_open(self):
        if self._visible: self._visible = False
        if self._file_list_panel: self._file_list_panel.setVisible(False)
        if self._btn_toggle: self._btn_toggle.setChecked(False)

    # ── File Management ──
    def _get_pool_path(self):
        pp = self._mw._get_current_project_path()
        if not pp: return ""
        dp = os.path.join(pp, "data_pool"); os.makedirs(dp, exist_ok=True); return dp

    def _refresh_files(self):
        pp = self._get_pool_path()
        if not pp or not self._file_tree: return
        self._file_tree.clear(); self._file_list = []
        if not os.path.isdir(pp): return
        for fn in sorted(os.listdir(pp)):
            if fn.startswith("."): continue
            fp = os.path.join(pp, fn)
            if os.path.isfile(fp):
                ext = os.path.splitext(fn)[1].lower()
                icons = {".md": "📝", ".pdf": "📕", ".xlsx": "📊", ".csv": "📊", ".docx": "📘", ".json": "📋"}
                icon = icons.get(ext, "📄")
                item = QTreeWidgetItem([f"{icon} {fn}"]); item.setData(0, Qt.UserRole, fp); item.setToolTip(0, fp)
                self._file_tree.addTopLevelItem(item); self._file_list.append(fp)

    def _clear_md_stylesheet(self):
        """清除 QTextBrowser 的 MD 样式表残留，避免影响后续纯文本显示"""
        self._content_text.document().setDefaultStyleSheet("")

    def _on_file_clicked(self, item, col):
        fp = item.data(0, Qt.UserRole)
        if not fp or not os.path.isfile(fp): return
        _log_f("material_pool", "_on_file_clicked", True, fp)
        r = FileParser.parse(fp)
        if r["success"]:
            self._content_title.setText(f"📄 {os.path.basename(fp)}")
            ext = os.path.splitext(fp)[1].lower()
            if ext in (".xlsx", ".csv"):
                table_widget = self._build_table_view(fp)
                self._content_view.removeWidget(self._content_view.widget(1))
                self._content_view.insertWidget(1, table_widget)
                self._content_view.setCurrentIndex(1)
            elif ext in (".md", ".markdown"):
                self._content_view.setCurrentIndex(0)
                if not self._render_md(r["text"]):
                    self._clear_md_stylesheet()
                    self._content_text.setPlainText(r["text"])
            else:
                self._content_view.setCurrentIndex(0)
                self._clear_md_stylesheet()
                self._content_text.setPlainText(r["text"])
            self._mw.centre_stack.setCurrentIndex(self.IDX_CONTENT)
        else:
            _log_f("material_pool", "_on_file_clicked", False, r.get("error",""))
            CustomDialog.warning(self._mw, "打开失败", r.get("error", "未知错误"))

    @staticmethod
    def _make_md_stylesheet() -> str:
        """生成当前主题下的 Markdown CSS 样式表字符串（供 setDefaultStyleSheet 使用）"""
        T = tc("text")
        A = tc("accent_blue")
        S = tc("surface")
        O = tc("overlay")
        BD = tc("border")
        return (
            f"body{{font-family:'HarmonyOS Sans SC','Microsoft YaHei',sans-serif;"
            f"font-size:11pt;color:{T};background:transparent;line-height:1.6;"
            f"margin:0;padding:8px;}}"
            f"h1,h2,h3,h4,h5,h6{{color:{A};font-weight:bold;margin:14px 0 6px 0;}}"
            f"h1{{font-size:18pt;}}h2{{font-size:15pt;}}h3{{font-size:13pt;}}"
            f"p{{margin:6px 0;}}"
            f"code{{background:{O};color:{T};padding:1px 4px;border-radius:3px;"
            f"font-family:'Consolas','Courier New',monospace;font-size:10pt;}}"
            f"pre{{background:{S};border:1px solid {BD};border-radius:6px;padding:10px;}}"
            f"pre code{{background:transparent;padding:0;border-radius:0;}}"
            f"blockquote{{border-left:3px solid {A};background:{S};"
            f"margin:8px 0;padding:6px 12px;border-radius:0 4px 4px 0;}}"
            f"a{{color:{A};text-decoration:none;}}"
            f"ul,ol{{margin:6px 0;padding-left:24px;}}"
            f"li{{margin:2px 0;}}"
            f"hr{{border:none;border-top:1px solid {BD};margin:12px 0;}}"
            f"table{{border-collapse:collapse;width:100%;margin:8px 0;}}"
            f"th,td{{border:1px solid {BD};padding:6px 10px;text-align:left;}}"
            f"th{{background:{O};}}"
        )

    def _render_md(self, md_text: str) -> bool:
        """将 Markdown 文本渲染到 _content_text，成功返回 True，失败返回 False"""
        _log_f("material_pool", "_render_md", True, f"text_len={len(md_text)}")
        if not _MARKDOWN_AVAILABLE:
            return False
        try:
            body = _md.markdown(md_text, extensions=["fenced_code", "tables"])
        except Exception as e:
            _log_f("material_pool", "_render_md/convert", False, str(e))
            return False
        css = self._make_md_stylesheet()
        try:
            self._content_text.document().setDefaultStyleSheet(css)
            self._content_text.setHtml(body)
        except Exception as e:
            _log_f("material_pool", "_render_md/setHtml", False, str(e))
            return False
        return True

    def _build_table_view(self, file_path: str, max_rows: int = 200) -> QWidget:
        """将 XLSX/CSV 文件渲染为 QTableWidget（仿资料稿表格样式）"""
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        data = FileParser.parse_table(file_path, max_rows)
        if not data["success"] or not data["rows"]:
            lbl = QLabel(f"无法解析表格: {data.get('error','')}")
            lbl.setObjectName("poolErrorLabel")
            return lbl

        rows = data["rows"]
        headers = data.get("headers", [])
        offset = 1 if headers and headers == rows[0] else 0
        ncols = max(len(r) for r in rows) if rows else 1
        nrows = len(rows) - offset

        table = QTableWidget(nrows, ncols)
        table.setObjectName("poolTableView")
        table.setFont(QFont("Microsoft YaHei", 11))
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(48)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

        if offset == 1 and headers:
            table.setHorizontalHeaderLabels(headers[:ncols])

        for i, row in enumerate(rows[offset:]):
            for j, cell in enumerate(row[:ncols]):
                item = QTableWidgetItem(str(cell) if cell else "")
                if not cell:
                    item.setForeground(Qt.gray)
                table.setItem(i, j, item)

        self._trim_empty_tail(table)
        self._auto_adjust_table(table, table.rowCount(), table.columnCount())

        # 列宽拖动时重新计算行高
        table.horizontalHeader().sectionResized.connect(
            lambda idx, old, new: self._readjust_rows(table))
        return table

    @staticmethod
    def _readjust_rows(table):
        """列宽变化时仅重新计算行高"""
        min_row_h = table.verticalHeader().defaultSectionSize()
        from PyQt5.QtGui import QTextDocument
        def _h(text: str, w: int) -> int:
            if not text: return min_row_h
            doc = QTextDocument(); doc.setPlainText(str(text))
            doc.setTextWidth(w - 10)
            return max(min_row_h, int(doc.size().height()) + 16)
        for i in range(table.rowCount()):
            best = min_row_h
            for j in range(table.columnCount()):
                item = table.item(i, j)
                if item and item.text():
                    h = _h(item.text(), table.columnWidth(j))
                    if h > best: best = h
            table.setRowHeight(i, best)

    @staticmethod
    def _trim_empty_tail(table):
        """移除尾部全空行和全空列"""
        # 从下往上找最后有内容的行
        last_row = -1
        for i in range(table.rowCount() - 1, -1, -1):
            for j in range(table.columnCount()):
                item = table.item(i, j)
                if item and item.text().strip():
                    last_row = i
                    break
            if last_row >= 0:
                break
        if last_row < 0:
            table.setRowCount(0)
            table.setColumnCount(0)
            return
        if last_row < table.rowCount() - 1:
            table.setRowCount(last_row + 1)

        # 从右往左找最后有内容的列
        last_col = -1
        for j in range(table.columnCount() - 1, -1, -1):
            for i in range(table.rowCount()):
                item = table.item(i, j)
                if item and item.text().strip():
                    last_col = j
                    break
            if last_col >= 0:
                break
        if last_col < table.columnCount() - 1:
            table.setColumnCount(last_col + 1)

    @staticmethod
    def _auto_adjust_table(table, nrows: int, ncols: int):
        """移植资料稿排布算法：
           1. QTextDocument 精确测量文字高度
           2. 二分查找每列「舒适宽度」→ 最长文字行高 ≤ 3×最小行高
           3. 按舒适宽度优选分配，保证文字完整显示 + 尽可能多行
        """
        if ncols == 0 or nrows == 0:
            return
        from PyQt5.QtGui import QTextDocument

        label_fm = QFontMetrics(table.font())
        ABS_MIN_W = 80
        COMFORT_FACTOR = 3
        min_row_h = table.verticalHeader().defaultSectionSize()
        comfort_target = min_row_h * COMFORT_FACTOR

        available_w = table.viewport().width() - table.verticalHeader().width() - 4
        if available_w < 200:
            available_w = max(table.parent().width() if table.parent() else 800, 600)

        def _text_height(text: str, width: int) -> int:
            if not text: return min_row_h
            doc = QTextDocument()
            doc.setPlainText(str(text))
            doc.setTextWidth(width - 10)
            return max(min_row_h, int(doc.size().height()) + 16)

        # ---- 1. 收集每列最长文本 ----
        col_longest = [""] * ncols
        for j in range(ncols):
            for i in range(min(nrows, 200)):
                item = table.item(i, j)
                if item and item.text() and len(item.text()) > len(col_longest[j]):
                    col_longest[j] = item.text()

        # ---- 2. 二分查找每列舒适宽度 ----
        def _comfort_width(text: str, max_w: int) -> int:
            if not text: return ABS_MIN_W
            target_h = comfort_target
            if _text_height(text, max_w) <= target_h:
                lo, hi = ABS_MIN_W, max_w
                while lo < hi:
                    mid = (lo + hi) // 2
                    if _text_height(text, mid) <= target_h:
                        hi = mid
                    else:
                        lo = mid + 1
                return lo
            return max_w

        comfort_w = [_comfort_width(col_longest[j], available_w) for j in range(ncols)]

        # ---- 3. 按舒适宽度分配 ----
        total_comfort = sum(comfort_w)
        if total_comfort <= available_w:
            extra = available_w - total_comfort
            text_lens = [max(1, len(t)) for t in col_longest]
            tl_total = sum(text_lens)
            for j in range(ncols):
                w = comfort_w[j] + int(extra * text_lens[j] / tl_total) if tl_total else comfort_w[j]
                table.setColumnWidth(j, w)
        else:
            for j in range(ncols):
                table.setColumnWidth(j, max(ABS_MIN_W, int(available_w * comfort_w[j] / total_comfort)))

        # ---- 4. 行高：取最小必要高度 ----
        for i in range(nrows):
            best_h = min_row_h
            for j in range(ncols):
                item = table.item(i, j)
                if item and item.text():
                    h = _text_height(item.text(), table.columnWidth(j))
                    if h > best_h:
                        best_h = h
            table.setRowHeight(i, best_h)
    def _on_file_menu(self, pos):
        item = self._file_tree.currentItem()
        if not item: return
        fp = item.data(0, Qt.UserRole)
        menu = QMenu(self._mw); menu.setStyleSheet(f"QMenu{{background:{tc('base')};color:{tc('text')};border:1px solid {tc('overlay')};border-radius:8px;}}QMenu::item{{padding:6px 24px;}}QMenu::item:selected{{background:{tc('overlay')};}}")
        a1 = menu.addAction("👁 查看"); a2 = menu.addAction("🗑 删除")
        chosen = menu.exec_(self._file_tree.mapToGlobal(pos))
        if chosen == a1: self._on_file_clicked(item, 0)
        elif chosen == a2:
            if CustomDialog.question(self._mw, "确认删除", f"删除 {os.path.basename(fp)}？", buttons=[("否","no"),("是","yes")]) == "yes":
                try: os.remove(fp); self._refresh_files(); self._index_ready = False
                except Exception as e: CustomDialog.warning(self._mw, "删除失败", str(e))

    # ── AI 总结导出进度面板 ──
    def _build_export_progress_panel(self):
        """构建进度显示面板（默认隐藏）"""
        p = QFrame(); p.setObjectName("exportProgressPanel"); p.setVisible(False)
        ly = QVBoxLayout(p); ly.setContentsMargins(8, 6, 8, 6); ly.setSpacing(4)
        # 标题行
        tr = QHBoxLayout(); tl = QLabel("🤖 AI 总结导出中...")
        tl.setObjectName("exportProgressTitle")
        tl.setFont(QFont("Microsoft YaHei", 10, QFont.Bold)); tr.addWidget(tl, 1)
        self._export_progress_label = QLabel("0/0")
        self._export_progress_label.setObjectName("exportProgressCount")
        self._export_progress_label.setFont(QFont("Microsoft YaHei", 10)); tr.addWidget(self._export_progress_label)
        ly.addLayout(tr)
        # 进度条
        self._export_progress_bar = QProgressBar(); self._export_progress_bar.setRange(0, 100)
        self._export_progress_bar.setValue(0); self._export_progress_bar.setTextVisible(True)
        self._export_progress_bar.setFixedHeight(16)
        self._export_progress_bar.setStyleSheet(
            "QProgressBar{background:#313244;border:none;border-radius:6px;text-align:center;"
            "color:#cdd6f4;font-size:9px;}"
            "QProgressBar::chunk{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #89b4fa,stop:1 #2E6DDE);border-radius:6px;}"
        )
        ly.addWidget(self._export_progress_bar)
        # 当前处理文件名
        self._export_progress_info = QLabel("")
        self._export_progress_info.setObjectName("exportProgressInfo")
        self._export_progress_info.setFont(QFont("Microsoft YaHei", 9))
        self._export_progress_info.setWordWrap(True)
        ly.addWidget(self._export_progress_info)
        self._export_progress_panel = p
        return p

    def _show_export_progress(self, show: bool):
        """显示/隐藏进度面板"""
        if self._export_progress_panel:
            self._export_progress_panel.setVisible(show)
            if show:
                self._export_progress_bar.setValue(0)
                self._export_progress_label.setText("0/0")
                self._export_progress_info.setText("正在准备...")

    def _on_ai_export_summary(self):
        """🤖 AI 总结导出 — 将资料池中所有文件投入 AI 生成综合总结 MD"""
        if self._ai_export_busy:
            CustomDialog.information(self._mw, "提示", "AI 总结导出正在进行中，请稍候...")
            return
        # 1. 检查项目路径
        pp = self._get_pool_path()
        if not pp:
            CustomDialog.warning(self._mw, "提示", "请先打开一个项目")
            return
        # 2. 刷新文件列表
        self._refresh_files()
        files = self._file_list[:]
        if not files:
            CustomDialog.information(self._mw, "提示", "资料池中暂无文件，请先导入")
            return
        # 3. 检查 API 配置
        api_cfg = self._mw._load_api_config() if hasattr(self._mw, '_load_api_config') else {}
        if not api_cfg.get("api_key"):
            ptype = api_cfg.get("provider_type", "auto")
            if ptype not in ("auto", "web"):
                CustomDialog.warning(self._mw, "缺少 API Key",
                    "请在设置中配置 API Key 后再使用 AI 总结导出功能。")
                return
            # auto/web 无 key 时静默跳过，由 _resolve_provider_type 回退到 Web
        # 4. 确认对话框
        fcount = len(files)
        resp = CustomDialog.question(self._mw, "🤖 AI 总结导出",
            f"将调用 AI 对资料池中 **{fcount} 个文件** 逐个生成详细总结，\n"
            f"合并输出为一份完整的 Markdown 文件。\n\n"
            f"⚠ 注意：此操作将消耗较多 API Token，请确保 API 余额充足。\n"
            f"单个文件处理约需 3-10 秒不等。\n\n"
            f"预计处理 **{fcount} 个文件**，是否继续？",
            buttons=[("取消", "no"), ("确认", "yes")]
        )
        if resp != "yes":
            return
        # 5. 构建文件信息列表
        ext_map = {".md": "markdown", ".txt": "text", ".pdf": "pdf",
                    ".docx": "docx", ".xlsx": "xlsx", ".csv": "csv",
                    ".json": "json", ".html": "html"}
        file_list = []
        for fp in files:
            if not os.path.isfile(fp): continue
            fn = os.path.basename(fp)
            ext = os.path.splitext(fn)[1].lower()
            file_list.append({
                "name": fn,
                "path": fp,
                "size": os.path.getsize(fp),
                "type": ext,
            })
        # 6. 显示进度面板
        self._show_export_progress(True)
        self._export_progress_label.setText(f"0/{len(file_list)}")
        # 7. 启动后台工作线程
        self._ai_export_busy = True
        w = AIExportWorker(file_list, api_cfg)
        w.signals.progress_updated.connect(self._on_ai_export_progress)
        w.signals.finished.connect(self._on_ai_export_complete)
        self._thread_pool.start(w)
        _log_f("material_pool", "ai_export", True, f"Started AI export for {len(file_list)} files")

    def _on_ai_export_progress(self, completed: int, total: int, file_name: str, result: dict):
        """AI 导出进度更新"""
        if not self._export_progress_panel:
            return
        pct = int(completed / max(total, 1) * 100)
        self._export_progress_bar.setValue(pct)
        self._export_progress_label.setText(f"{completed}/{total}")
        status = "✅" if result.get("success") else "❌"
        err = result.get("error", "")
        info = f"正在处理: {file_name}  ({status})"
        if err:
            info += f"\n⚠ {err}"
        self._export_progress_info.setText(info)

    def _on_ai_export_complete(self, all_results: list):
        """AI 导出完成 — 生成 MD 文件并保存"""
        self._ai_export_busy = False
        self._show_export_progress(False)
        if not all_results:
            CustomDialog.warning(self._mw, "导出失败", "AI 处理未返回任何结果")
            return
        success = sum(1 for r in all_results if r.get("success"))
        fail = len(all_results) - success
        # 组装 Markdown
        pp = self._get_pool_path()
        fname = f"pool_ai_summary_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        md_content = AIExportWorker.build_markdown(all_results, project_name=pp or "")
        # 弹出保存对话框
        fp, _ = QFileDialog.getSaveFileName(
            self._mw, "保存 AI 综合总结", fname, "Markdown(*.md)"
        )
        if not fp:
            return
        try:
            with open(fp, "w", encoding="utf-8") as f:
                f.write(md_content)
            _log_f("material_pool", "ai_export_complete", True, f"Saved to {fp}")
            # 完成对话框
            summary = f"✅ 处理文件: {success}/{len(all_results)} 成功"
            if fail:
                summary += f"\n⚠ 失败: {fail} 个（详见报告）"
            summary += f"\n📄 已保存至:\n{fp}"
            CustomDialog.information(self._mw, "✅ AI 总结完成！", summary)
        except Exception as e:
            CustomDialog.warning(self._mw, "保存失败", str(e))

    def _on_import(self):
        fps, _ = QFileDialog.getOpenFileNames(self._mw, "选择要导入的文件", "",
            "所有支持的文件(*.md *.txt *.pdf *.docx *.xlsx *.csv *.json *.html);;所有文件(*.*)")
        if not fps: return
        pp = self._get_pool_path()
        if not pp: CustomDialog.warning(self._mw, "提示", "请先打开一个项目"); return
        n = 0
        for src in fps:
            if not FileParser.is_supported(src): continue
            fn = os.path.basename(src); dst = os.path.join(pp, fn)
            if os.path.exists(dst):
                if CustomDialog.question(self._mw, "文件已存在", f"{fn} 已存在，覆盖？", buttons=[("跳过","no"),("覆盖","yes")]) != "yes": continue
            try: shutil.copy2(src, dst); n += 1
            except Exception as e: CustomDialog.warning(self._mw, "导入失败", str(e))
        _log_f("material_pool", "import", True, f"Imported {n}"); self._refresh_files(); self._index_ready = False

    def _on_export(self):
        if not self._current_results: CustomDialog.information(self._mw, "提示", "请先执行搜索后再导出"); return
        fp, _ = QFileDialog.getSaveFileName(self._mw, "导出汇总", f"pool_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.md", "Markdown(*.md);;Text(*.txt)")
        if not fp: return
        try:
            lines = [f"# 资料池搜索汇总\n导出时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n共 {len(self._current_results)} 条结果\n---\n"]
            for i, r in enumerate(self._current_results, 1):
                lines.append(f"## {i}. {r.get('title','未知')}\n- 文件: {r.get('file','')}\n- BM25={r.get('score',0)} AI={r.get('ai_score','N/A')}\n- {r.get('summary','')}\n")
            with open(fp, "w", encoding="utf-8") as f: f.write("\n".join(lines))
            _log_f("material_pool", "export", True, f"Exported"); CustomDialog.information(self._mw, "导出成功", f"已导出至:\n{fp}")
        except Exception as e: CustomDialog.warning(self._mw, "导出失败", str(e))

    # ── Search ──
    def _on_search(self):
        q = self._search_input.text().strip() if self._search_input else ""
        if not q: return
        pp = self._get_pool_path()
        if not pp: return
        if not self._index_ready: self._rebuild_index()
        _log_f("material_pool", "search", True, f"Query:{q[:50]}")
        self._mw.centre_stack.setCurrentIndex(self.IDX_SEARCH); self._clear_cards(); QApplication.processEvents()
        results = LocalSearcher.search(q, self._index_data, pp, 50)
        self._current_results = results; self._current_page = 0; self._render_cards()
        self._search_history.append({"query": q, "time": time.time(), "count": len(results)})
        api_cfg = self._mw._load_api_config() if hasattr(self._mw, '_load_api_config') else None
        if api_cfg and api_cfg.get("api_key"):
            self._ai_searching = True; w = _SearchWorker(q, pp, self._index_data, api_cfg, True)
            w.signals.results_ready.connect(self._on_ai_ready); w.signals.ai_progress.connect(self._on_ai_progress)
            self._thread_pool.start(w)
        self._mw._update_status(f"搜索'{q}': {len(results)} 条结果")

    def _rebuild_index(self):
        pp = self._get_pool_path()
        if not pp: return
        self._refresh_files()
        data = IndexManager.rebuild_all(pp, self._file_list, FileParser)
        self._index_data = {"files": data.get("files", {}), "inverted": data.get("inverted", {})}
        self._index_ready = True

    # ── 公开方法：供一辩稿绑定弹窗调用 ──

    def search_material_files(self, query: str) -> list[dict]:
        """搜索资料池文件，返回匹配的文件列表（供一辩稿绑定弹窗使用）

        Args:
            query: 搜索关键词

        Returns:
            [{file_path, rel_path, file_name, title, snippet, summary}, ...]
        """
        if not query or not query.strip():
            return self._list_all_material_files()
        pp = self._get_pool_path()
        if not pp:
            return []
        if not self._index_ready:
            self._rebuild_index()
        results = LocalSearcher.search(query, self._index_data, pp)
        return [
            {
                "file_path": r["file_path"],
                "rel_path": r.get("rel_path", ""),
                "file_name": r.get("file", ""),
                "title": r.get("title", ""),
                "snippet": (r.get("snippet") or r.get("summary") or "")[:200],
            }
            for r in results
        ]

    def _list_all_material_files(self) -> list[dict]:
        """列出资料池所有文件（无搜索关键词时的兜底）"""
        pp = self._get_pool_path()
        if not pp:
            return []
        self._refresh_files()
        results = []
        for fp in self._file_list:
            fname = os.path.basename(fp)
            rel = os.path.relpath(fp, pp)
            # 取前 100 字作为预览
            text = FileParser.get_text(fp)
            snippet = text[:100].replace("\n", " ") if text else ""
            results.append({
                "file_path": fp,
                "rel_path": rel,
                "file_name": fname,
                "title": fname,
                "snippet": snippet,
            })
        return results

    def _on_ai_ready(self, results):
        self._current_results = results; self._current_page = 0; self._render_cards()
        self._ai_searching = False; self._ai_analysis_progress = 100

    def _on_ai_progress(self, completed, total, item):
        self._ai_completed = completed; self._ai_analysis_progress = int(completed / max(total, 1) * 100)
        fid = item.get("file", "")
        for i in range(self._search_layout.count()):
            w = self._search_layout.itemAt(i).widget()
            if w and w.property("result_id") == fid:
                nc = self._build_card(item); self._search_layout.replaceWidget(w, nc); w.deleteLater(); return

    def _clear_cards(self):
        if self._search_layout:
            while self._search_layout.count():
                w = self._search_layout.takeAt(0)
                if w and w.widget(): w.widget().deleteLater()

    def _render_cards(self):
        self._clear_cards()
        total = len(self._current_results); pages = max(1, (total + self._page_size - 1) // self._page_size)
        st = self._current_page * self._page_size; en = min(st + self._page_size, total)
        self._result_count_label.setText(f"🔍 共 {total} 条结果  (第 {self._current_page+1}/{pages} 页)")
        for r in self._current_results[st:en]: self._search_layout.addWidget(self._build_card(r))
        self._search_layout.addStretch(1); self._lbl_page.setText(f"{self._current_page+1}/{pages}")
        self._btn_prev.setEnabled(self._current_page > 0); self._btn_next.setEnabled(en < total)

    def _build_card(self, r: dict) -> QFrame:
        c = QFrame(); c.setObjectName("searchResultCard"); c.setProperty("result_id", r.get("file", ""))
        c.setCursor(Qt.PointingHandCursor); c.mousePressEvent = lambda ev: self._on_card_click(r)
        ly = QVBoxLayout(c); ly.setContentsMargins(12, 10, 12, 8); ly.setSpacing(4)
        tr = QHBoxLayout(); icons = {"data_pool": "📄", "project": "🏛", "stardebate": "📦"}
        tl = QLabel(f"{icons.get(r.get('source','data_pool'),'📄')} {r.get('title','未知')}")
        tl.setObjectName("searchCardTitle")
        tl.setFont(QFont("Microsoft YaHei", 13, QFont.Bold)); tr.addWidget(tl, 1)
        ai = r.get("ai_score")
        sl = QLabel(f"AI:{ai:.2f}" if ai is not None else f"BM25:{r.get('score',0)}")
        sl.setObjectName("searchCardScore")
        sl.setFont(QFont("Microsoft YaHei", 10)); sl.setStyleSheet(f"color:{'#a6e3a1' if ai else '#6c7086'};border:none;"); tr.addWidget(sl)
        ly.addLayout(tr)
        ml = QLabel(f"📁 {r.get('file','')}  |  📎 ×{r.get('match_count',0)}")
        ml.setObjectName("searchCardMeta")
        ml.setFont(QFont("Microsoft YaHei", 10)); ly.addWidget(ml)
        s = QFrame(); s.setObjectName("searchHLine"); s.setFrameShape(QFrame.HLine); ly.addWidget(s)
        sm = r.get("ai_summary") or r.get("summary", "")
        if sm:
            sl2 = QLabel(sm[:150]); sl2.setObjectName("searchCardSummary"); sl2.setFont(QFont("Microsoft YaHei", 11)); sl2.setWordWrap(True); ly.addWidget(sl2)
        return c

    def _on_card_click(self, r: dict):
        """点击搜索卡片 → 展示纯 Qt 详情页"""
        self._current_detail_result = r
        fp = r.get("file_path", ""); ft = ""
        if fp and os.path.isfile(fp):
            pr = FileParser.parse(fp); ft = pr.get("text", "") if pr["success"] else ""
        self._detail_page.populate(r, ft, manager=self)
        self._mw.centre_stack.setCurrentIndex(self.IDX_DETAIL)

    # ── 详情页操作按钮回调 ──
    def _detail_copy(self):
        """复制全文到剪贴板"""
        try:
            fp = self._current_detail_result.get("file_path", "")
            if fp and os.path.isfile(fp):
                pr = FileParser.parse(fp)
                if pr["success"]:
                    from PyQt5.QtWidgets import QApplication
                    QApplication.clipboard().setText(pr["text"])
                    CustomDialog.information(self._mw, "复制成功", "全文已复制到剪贴板")
        except Exception: pass

    def _detail_export(self):
        """导出当前详情为 MD 文件"""
        r = self._current_detail_result
        if not r: return
        fp, _ = QFileDialog.getSaveFileName(self._mw, "导出详情",
            f"{r.get('file','detail')}_detail.md", "Markdown(*.md)")
        if not fp: return
        try:
            lines = [f"# {r.get('title','')}", "", f"- 文件: {r.get('file','')}", f"- BM25: {r.get('score',0)}"]
            if r.get("ai_summary"): lines += ["", "## AI 摘要", "", r["ai_summary"]]
            if r.get("ai_key_points"): lines += ["", "## 关键要点", ""] + [f"- {k}" for k in r["ai_key_points"]]
            if r.get("matched_paragraphs"): lines += ["", "## 匹配段落", ""] + [f"> {m.get('text','')}" for m in r["matched_paragraphs"]]
            with open(fp, "w", encoding="utf-8") as f: f.write("\n".join(lines))
            CustomDialog.information(self._mw, "导出成功", f"已导出至:\n{fp}")
        except Exception as e: CustomDialog.warning(self._mw, "导出失败", str(e))

    def _detail_to_stdb(self):
        """将当前结果加入 .stardebate 文件"""
        from PyQt5.QtWidgets import QInputDialog
        fp, ok = QInputDialog.getText(self._mw, "加入 .stardebate", "输入 .stardebate 文件路径:")
        if not ok or not fp: return
        if not os.path.isfile(fp):
            CustomDialog.warning(self._mw, "错误", "文件不存在")
            return
        try:
            from workers.stardebate_format import StardebateEditorManager
            mgr = getattr(self._mw, '_stdb_editor_mgr', None)
            if not mgr: mgr = StardebateEditorManager(self._mw)
            r = self._current_detail_result
            mgr.update_module_data(fp, "notes",
                {"text": f"## {r.get('title','')}\nBM25={r.get('score',0)} AI={r.get('ai_score','N/A')}\n\n{r.get('summary','')}"})
            CustomDialog.information(self._mw, "成功", "已加入 .stardebate 文件")
        except Exception as e: CustomDialog.warning(self._mw, "失败", str(e))

    def _detail_open_file(self):
        """在操作系统中打开源文件"""
        fp = self._current_detail_result.get("file_path", "")
        if fp and os.path.isfile(fp):
            import subprocess
            subprocess.Popen(['explorer', '/select,', os.path.normpath(fp)])

    def _prev_page(self):
        if self._current_page > 0: self._current_page -= 1; self._render_cards()
    def _next_page(self):
        total = len(self._current_results)
        if self._current_page < (total + self._page_size - 1) // self._page_size - 1: self._current_page += 1; self._render_cards()

    # ── Public API (for plugin_api) ──
    def search(self, kw, sources=None, limit=20):
        pp = self._get_pool_path()
        if not pp or not self._index_ready: self._rebuild_index()
        if not pp: return []
        return LocalSearcher.search(kw, self._index_data, pp, limit)
    search_local = search
    def list_files(self, rec=True):
        pp = self._get_pool_path()
        if not pp: return []
        return [{"name": fn, "path": os.path.join(pp, fn), "size": os.path.getsize(os.path.join(pp, fn)),
                 "type": os.path.splitext(fn)[1]} for fn in sorted(os.listdir(pp))
                if not fn.startswith(".") and os.path.isfile(os.path.join(pp, fn))]
    def get_file_text(self, rp):
        pp = self._get_pool_path(); fp = os.path.join(pp, rp) if pp and ".." not in rp else ""; return FileParser.get_text(fp) if fp else ""
    def get_stats(self):
        f = self.list_files(); tc = {}; ts = 0
        for x in f: tc[x["type"]] = tc.get(x["type"], 0) + 1; ts += x["size"]
        return {"file_count": len(f), "total_size": ts, "type_counts": tc, "indexed": self._index_ready}
    def notify_file_added(self, fp): self._refresh_files(); self._index_ready = False
    def notify_file_removed(self, rp): self._refresh_files(); self._index_ready = False
    def summarize_file(self, rp):
        pp = self._get_pool_path(); fp = os.path.join(pp, rp) if pp and ".." not in rp else ""
        if not fp or not os.path.isfile(fp): return {"success": False, "summary": None, "key_points": [], "keywords": [], "error": "文件不存在"}
        api_cfg = self._mw._load_api_config() if hasattr(self._mw, '_load_api_config') else {}
        if not api_cfg.get("api_key"): return {"success": False, "summary": None, "key_points": [], "keywords": [], "error": "未配置API密钥"}
        return AISearcher.summarize_document(fp, api_cfg)
    def ai_rerank(self, results):
        api_cfg = self._mw._load_api_config() if hasattr(self._mw, '_load_api_config') else {}
        pp = self._get_pool_path()
        if not api_cfg.get("api_key") or not pp: return results
        return AISearcher.rerank_results(results[0].get("summary","") if results else "", results, api_cfg, pp, max_to_rerank=5)
    def export_results(self, results=None, fmt="md"):
        rs = results or self._current_results
        if not rs: return None
        fp = os.path.join(self._get_pool_path(), f"export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}")
        lines = [f"# 资料池搜索汇总\n\n导出时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n共 {len(rs)} 条\n---\n"]
        for i, r in enumerate(rs, 1):
            lines.append(f"## {i}. {r.get('title','未知')}\n- 文件: {r.get('file','')}\n- BM25={r.get('score',0)}\n- {r.get('summary','')}\n")
        with open(fp, "w", encoding="utf-8") as f: f.write("\n".join(lines)); return fp
    def export_to_stdb(self, fp, results=None): return True