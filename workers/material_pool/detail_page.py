"""
detail_page.py — 纯 Qt 结果详细展示页
======================================
所有 UI 由 Qt 控件渲染，不使用 HTML。
文本框根据内容自动调整高度，始终在功能区宽度内。
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QLabel, QPushButton, QTextEdit, QScrollArea, QSizePolicy,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QFontMetrics


class _AutoTextEdit(QTextEdit):
    """自适应高度文本框 — 根据内容自动撑开，最外层 QScrollArea 统一滚动"""
    def __init__(self, parent=None, min_lines=1):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        fm = QFontMetrics(self.font())
        self._min_h = fm.lineSpacing() * min_lines + 18
        self.setFixedHeight(self._min_h)
        self.document().documentLayout().documentSizeChanged.connect(
            self._on_doc_resize)

    def _on_doc_resize(self, sz):
        h = int(sz.height() + 18)
        h = max(self._min_h, h)
        self.setFixedHeight(h)


class DetailPage(QWidget):
    """纯 Qt 结果详细展示页 — 可滚动"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("detailPageContainer")
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── 滚动区 ──
        scroll = QScrollArea()
        scroll.setObjectName("detailPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._content = QWidget()
        self._content.setObjectName("detailContent")
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(14, 10, 14, 14)
        self._layout.setSpacing(6)

        scroll.setWidget(self._content)
        outer.addWidget(scroll, 1)

    # ═══════ 填充数据入口 ═══════

    def populate(self, r: dict, full_text: str = "", manager=None):
        """根据搜索结果填充所有控件"""
        # 清空旧内容
        while self._layout.count():
            w = self._layout.takeAt(0)
            if w and w.widget():
                w.widget().deleteLater()

        ft = r.get("file_type", "").lower()
        is_table = ft in (".xlsx", ".csv")
        fp = r.get("file_path", "")

        self._build_top_bar(r, manager)
        self._build_title(r)
        self._build_info_card(r)
        self._build_ai_section(r)
        self._build_match_section(r)
        if is_table and fp:
            self._build_table_preview(fp)
        else:
            self._build_preview(full_text)
        self._build_footer(manager)
        self._layout.addStretch(1)

    # ═══════ 构建函数 ═══════

    def _build_top_bar(self, r: dict, manager):
        bar = QFrame()
        bar.setObjectName("detailTopBar")
        bar.setFixedHeight(42)
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 4, 10, 4)
        h.setSpacing(8)

        # 返回按钮
        back = QPushButton("← 返回")
        back.setObjectName("smallBtn")
        back.setFixedHeight(28)
        back.setMinimumWidth(62)
        back.setCursor(Qt.PointingHandCursor)
        if manager:
            back.clicked.connect(lambda: manager._mw.centre_stack.setCurrentIndex(
                manager.IDX_SEARCH if manager.IDX_SEARCH >= 0 else 0))
        h.addWidget(back)

        # 标题
        title = QLabel(r.get("title", "")[:40])
        title.setObjectName("detailTopTitle")
        title.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        h.addWidget(title, 1)

        # 操作按钮
        for label, action in [("📋 复制", "copy"), ("📤 导出", "export"), ("📦 STDB", "stdb")]:
            btn = self._mk_small_btn(label)
            if manager:
                btn.clicked.connect(lambda checked, a=action: self._handle_action(a, manager))
            h.addWidget(btn)

        self._layout.addWidget(bar)

    def _build_title(self, r: dict):
        lbl = QLabel(f"🌐 {r.get('title', '未知')}")
        lbl.setObjectName("detailTitle")
        lbl.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        lbl.setWordWrap(True)
        self._layout.addWidget(lbl)

        sep = QFrame()
        sep.setObjectName("detailSepLine")
        sep.setFrameShape(QFrame.HLine)
        self._layout.addWidget(sep)

    def _mk_label(self, text: str, size: int = 12, bold: bool = False,
                  color: str = "#cdd6f4", wrap: bool = True) -> QLabel:
        """创建自适应换行 QLabel——颜色动态传入，保留内联样式"""
        lbl = QLabel(text)
        lbl.setFont(QFont("Microsoft YaHei", size, QFont.Bold if bold else QFont.Normal))
        lbl.setStyleSheet(f"color:{color};border:none;background:transparent;")
        if wrap:
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return lbl

    def _build_info_card(self, r: dict):
        card = QFrame()
        card.setObjectName("detailInfoCard")
        ly = QVBoxLayout(card)
        ly.setContentsMargins(12, 10, 12, 10)
        ly.setSpacing(4)

        # 表格行
        grid = QGridLayout()
        grid.setSpacing(2)
        fname = r.get("file", "")
        ftype = (r.get("file_type", "") or "").upper()
        meta = r.get("meta", {})
        sz = self._fmt_size(meta.get("size", 0))
        mtime = str(meta.get("mtime", ""))
        mc = r.get("match_count", 0)

        rows = [
            (f"📂 {fname}", f"🏷 {ftype}"),
            ("📁 data_pool/", f"📏 {sz}"),
            (f"🕒 {mtime}", f"📎 匹配 {mc} 处"),
        ]
        for i, (left, right) in enumerate(rows):
            l = QLabel(left)
            l.setObjectName("detailInfoRow")
            l.setFont(QFont("Microsoft YaHei", 12))
            rlb = QLabel(right)
            rlb.setObjectName("detailInfoRow")
            rlb.setFont(QFont("Microsoft YaHei", 12))
            rlb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(l, i, 0)
            grid.addWidget(rlb, i, 1)
        ly.addLayout(grid)

        # 分隔线
        div = QFrame()
        div.setObjectName("detailSepLine")
        div.setFrameShape(QFrame.HLine)
        ly.addWidget(div)

        # 徽章行
        badge_row = QHBoxLayout()
        badge_row.setSpacing(6)
        bm25 = r.get("score", 0)
        badge_row.addWidget(self._mk_badge(f"⭐ BM25 {bm25:.2f}", "#89b4fa", "#1a2a3a"))
        ai_s = r.get("ai_score")
        if ai_s is not None:
            c = "#a6e3a1" if ai_s > 0.5 else "#6c7086"
            bg = "#1e3a2a" if ai_s > 0.5 else "#2a1a1a"
            badge_row.addWidget(self._mk_badge(f"🤖 AI {ai_s:.2f}", c, bg))
        badge_row.addStretch()
        ly.addLayout(badge_row)

        self._layout.addWidget(card)

    def _build_ai_section(self, r: dict):
        ai_sum = r.get("ai_summary", "")
        ai_kp = r.get("ai_key_points", [])
        if not ai_sum and not ai_kp:
            return

        self._layout.addWidget(self._mk_section_title("🤖 AI 分析摘要"))

        card = QFrame()
        card.setObjectName("detailAICard")
        ly = QVBoxLayout(card)
        ly.setContentsMargins(10, 8, 10, 8)
        ly.setSpacing(4)

        if ai_sum:
            lbl = self._mk_label(ai_sum, size=13, color="#cdd6f4")
            ly.addWidget(lbl)

        if ai_kp:
            ly.addWidget(self._mk_label("🔑 关键要点:", size=12, bold=True, color="#f9e2af"))
            for kp in ai_kp:
                item = self._mk_label(f"• {kp}", size=12, color="#bac2de")
                ly.addWidget(item)

        self._layout.addWidget(card)

    def _build_match_section(self, r: dict):
        mps = r.get("matched_paragraphs", [])
        if not mps:
            return

        self._layout.addWidget(self._mk_section_title(f"📖 匹配段落 (共 {len(mps)} 处)"))

        for idx, mp in enumerate(mps[:5], 1):
            weight = mp.get("weight", 0)
            stars = "⭐⭐⭐" if weight > 0.6 else ("⭐⭐" if weight > 0.3 else "★☆☆")

            lbl = QLabel(f"匹配 #{idx} — 权重: {stars}")
            lbl.setObjectName("detailMatchTitle")
            lbl.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
            self._layout.addWidget(lbl)

            text_edit = _AutoTextEdit(min_lines=1)
            text_edit.setObjectName("detailMatchText")
            text_edit.setFont(QFont("Microsoft YaHei", 12))
            text_edit.setPlainText(mp.get("text", ""))
            self._layout.addWidget(text_edit)

    def _build_preview(self, text: str):
        if not text:
            return

        self._layout.addWidget(self._mk_section_title("📄 全文预览"))

        text_edit = _AutoTextEdit(min_lines=3)
        text_edit.setObjectName("detailPreviewText")
        text_edit.setFont(QFont("Microsoft YaHei", 12))
        text_edit.setPlainText(text[:5000])
        self._layout.addWidget(text_edit)

    def _build_table_preview(self, file_path: str):
        """表格文件专用预览 — 仿资料稿 QTableWidget"""
        from .file_parser import FileParser
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        data = FileParser.parse_table(file_path, max_rows=100)
        if not data["success"] or not data["rows"]:
            return

        self._layout.addWidget(self._mk_section_title("📊 表格预览"))

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

        # 移除尾部空行列 + 自动调整
        self._trim_empty_tail(table)
        self._auto_adjust_table(table, table.rowCount(), table.columnCount())

        # 列宽拖动时仅重新计算行高
        table.horizontalHeader().sectionResized.connect(
            lambda idx, old, new: self._readjust_rows(table))

        # 自适应高度（使用 trim 后的实际行数）
        h = table.horizontalHeader().height() + sum(table.rowHeight(i) for i in range(table.rowCount())) + 4
        table.setMinimumHeight(min(h, 600))
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._layout.addWidget(table)

    @staticmethod
    def _trim_empty_tail(table):
        """移除尾部全空行和全空列"""
        last_row = -1
        for i in range(table.rowCount() - 1, -1, -1):
            for j in range(table.columnCount()):
                item = table.item(i, j)
                if item and item.text().strip():
                    last_row = i; break
            if last_row >= 0: break
        if last_row < 0: table.setRowCount(0); table.setColumnCount(0); return
        if last_row < table.rowCount() - 1: table.setRowCount(last_row + 1)
        last_col = -1
        for j in range(table.columnCount() - 1, -1, -1):
            for i in range(table.rowCount()):
                item = table.item(i, j)
                if item and item.text().strip():
                    last_col = j; break
            if last_col >= 0: break
        if last_col < table.columnCount() - 1: table.setColumnCount(last_col + 1)

    @staticmethod
    def _auto_adjust_table(table, nrows, ncols):
        """移植资料稿排布算法：QTextDocument 精确测高 + 二分舒适宽度"""
        if ncols == 0 or nrows == 0:
            return
        from PyQt5.QtGui import QTextDocument

        ABS_MIN_W = 80
        COMFORT_FACTOR = 3
        min_row_h = table.verticalHeader().defaultSectionSize()
        comfort_target = min_row_h * COMFORT_FACTOR

        available_w = table.viewport().width() - table.verticalHeader().width() - 4
        if available_w < 200:
            available_w = 800

        def _text_height(text: str, width: int) -> int:
            if not text: return min_row_h
            doc = QTextDocument()
            doc.setPlainText(str(text))
            doc.setTextWidth(width - 10)
            return max(min_row_h, int(doc.size().height()) + 16)

        col_longest = [""] * ncols
        for j in range(ncols):
            for i in range(min(nrows, 150)):
                item = table.item(i, j)
                if item and item.text() and len(item.text()) > len(col_longest[j]):
                    col_longest[j] = item.text()

        def _comfort_width(text: str, max_w: int) -> int:
            if not text: return ABS_MIN_W
            if _text_height(text, max_w) <= comfort_target:
                lo, hi = ABS_MIN_W, max_w
                while lo < hi:
                    mid = (lo + hi) // 2
                    if _text_height(text, mid) <= comfort_target:
                        hi = mid
                    else:
                        lo = mid + 1
                return lo
            return max_w

        comfort_w = [_comfort_width(col_longest[j], available_w) for j in range(ncols)]
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

        for i in range(nrows):
            best_h = min_row_h
            for j in range(ncols):
                item = table.item(i, j)
                if item and item.text():
                    h = _text_height(item.text(), table.columnWidth(j))
                    if h > best_h:
                        best_h = h
            table.setRowHeight(i, best_h)

    @staticmethod
    def _readjust_rows(table):
        """列宽变化时仅重新计算行高"""
        min_row_h = table.verticalHeader().defaultSectionSize()
        from PyQt5.QtGui import QTextDocument
        def _h(text, w):
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

    def _build_footer(self, manager):
        bar = QFrame()
        bar.setObjectName("detailFooterBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 8, 0, 4)
        h.setSpacing(10)
        h.addStretch()

        for label, action in [
            ("📋 复制全文", "copy"),
            ("📤 导出MD", "export"),
            ("📦 加入STDB", "stdb"),
            ("🔍 源文件", "open_file"),
        ]:
            btn = QPushButton(label)
            btn.setObjectName("detailFooterBtn")
            btn.setFixedHeight(34)
            fm = QFontMetrics(btn.font())
            btn.setMinimumWidth(fm.horizontalAdvance(label) + 22)
            btn.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
            btn.setCursor(Qt.PointingHandCursor)
            if manager:
                btn.clicked.connect(lambda checked, a=action: self._handle_action(a, manager))
            h.addWidget(btn)
        h.addStretch()
        self._layout.addWidget(bar)

    # ═══════ 工具方法 ═══════

    def _mk_small_btn(self, text: str) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("smallBtn")
        b.setFixedHeight(28)
        fm = QFontMetrics(b.font())
        w = fm.horizontalAdvance(text) + 14
        b.setMinimumWidth(w)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _mk_section_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("detailSectionTitle")
        lbl.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        return lbl

    def _mk_badge(self, text: str, color: str, bg: str) -> QLabel:
        """徽章——颜色动态传入，保留内联样式"""
        lbl = QLabel(text)
        lbl.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        lbl.setStyleSheet(
            f"color:{color};background:{bg};border-radius:4px;"
            f"padding:2px 10px;border:none;"
        )
        lbl.setFixedHeight(24)
        return lbl

    @staticmethod
    def _fmt_size(sz: int) -> str:
        if not sz: return ""
        if sz > 1048576: return f"{sz/1048576:.1f}MB"
        if sz > 1024: return f"{sz/1024:.0f}KB"
        return f"{sz}B"

    @staticmethod
    def _handle_action(action: str, manager):
        """按钮回调分发"""
        if action == "copy":
            manager._detail_copy()
        elif action == "export":
            manager._detail_export()
        elif action == "stdb":
            manager._detail_to_stdb()
        elif action == "open_file":
            manager._detail_open_file()
