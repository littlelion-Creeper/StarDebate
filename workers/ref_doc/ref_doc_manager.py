"""资料稿管理器 - 负责资料稿表格和卡片的 UI、数据、文件管理及表格导入"""
import json
import os
import csv
import re
from components.theme_colors import tc, refresh
from components.star_button import StarButton
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QScrollArea, QGridLayout,
    QFileDialog, QDialog, QComboBox, QFormLayout,
    QStyledItemDelegate, QStyleOptionViewItem, QTextEdit, QHeaderView,
    QApplication, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer, QEvent
from PyQt5.QtGui import QFont, QColor, QTextDocument

from components.popup_dialog import CustomDialog


# ============================================================
# 多行文本代理（资料稿表格专用）
# ============================================================
class RefDocMultilineDelegate(QStyledItemDelegate):
    """资料稿 QTableWidget 多行文本编辑代理，支持 Ctrl+Enter 提交"""

    _min_row_height = 48

    def __init__(self, parent=None):
        super().__init__(parent)

    def createEditor(self, parent, option, index):
        editor = QTextEdit(parent)
        editor.setAcceptRichText(False)
        font = editor.font()
        font.setPointSize(11)
        editor.setFont(font)
        editor.setStyleSheet(
            "QTextEdit {"
            "  background-color: #181825;"
            "  color: #cdd6f4;"
            "  border: 2px solid #2E6DDE;"
            "  border-radius: 4px;"
            "  padding: 2px;"
            "}"
        )
        self._editor = editor
        return editor

    def setEditorData(self, editor, index):
        # 优先使用 EditRole（纯文本），兼容搜索高亮场景
        value = index.data(Qt.EditRole)
        if value:
            editor.setPlainText(str(value))
            return
        # 后备：DisplayRole，如果包含 HTML 高亮则剥离标签
        value = index.data(Qt.DisplayRole)
        if value:
            text = str(value)
            if '<span ' in text:
                text = re.sub(r'<[^>]+>', '', text)
            editor.setPlainText(text)

    def setModelData(self, editor, model, index):
        text = editor.toPlainText()
        model.setData(index, text, Qt.EditRole)
        model.setData(index, text, Qt.DisplayRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

    def eventFilter(self, obj, event):
        if obj is self._editor and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
                self.commitData.emit(obj)
                self.closeEditor.emit(obj)
                return True
        return super().eventFilter(obj, event)

    def sizeHint(self, option, index):
        """根据文本内容返回推荐尺寸"""
        text = index.data(Qt.DisplayRole)
        width = option.rect.width() if option.rect.width() > 50 else 200
        h = self.get_row_height(text if text else "", width)
        return option.rect.size().expandedTo(option.rect)

    def get_row_height(self, text: str, col_width: int) -> int:
        """根据文本内容和列宽估算所需的行高度"""
        if not text:
            return self._min_row_height
        try:
            doc = QTextDocument()
            doc.setPlainText(str(text))
            doc.setTextWidth(col_width - 10)
            h = int(doc.size().height()) + 16
            return max(self._min_row_height, h)
        except Exception:
            return self._min_row_height


# ============================================================
# 资料稿管理器主类
# ============================================================
class RefDocManager:
    """资料稿管理器

    职责：
    - 构建资料稿表格页面和卡片页面的 UI
    - 管理三列数据（论证观点、论证内容、资料来源）的 CRUD
    - JSON 文件持久化存储
    - 智能表格导入（CSV/Excel）及列映射
    - 资料卡片视图展示

    对外 API：
    - build_ui(main_window, centre_stack) → 构建并注册两个页面到 QStackedWidget
    - open_ref_doc() → 打开/切换到表格编辑页
    - show_ref_cards() → 切换到卡片视图
    - load_data_from_file() → 从 JSON 文件加载数据
    - apply_column_ratio() → 按 1:2:2 设置列宽比
    - ref_doc_rows → 数据行列表（getter/setter）
    - ref_doc_table / ref_cards_scroll / ref_cards_grid → 供外部访问
    """

    # 三列表头常量
    COLUMNS = ["论证观点", "论证内容", "资料来源"]
    COL_ARGUMENT = 0
    COL_CONTENT = 1
    COL_SOURCE = 2

    def __init__(self):
        """初始化管理器"""
        # ---- 主窗口引用（build_ui 时注入）----
        self._mw = None

        # ---- 数据 ----
        self._ref_doc_rows: list[dict] = []       # [{"argument":...,"content":...,"source":...}, ...]
        self._ref_cards: list[QFrame] = []         # 当前卡片组件列表

        # ---- UI 组件（由 build_ui 创建）----
        self._ref_doc_table: QTableWidget | None = None
        self._ref_multiline_delegate: RefDocMultilineDelegate | None = None

        self._ref_cards_scroll: QScrollArea | None = None
        self._ref_cards_container: QWidget | None = None
        self._ref_cards_grid: QGridLayout | None = None

        # 工具栏按钮
        self.btn_ref_card_view: StarButton | None = None  # "卡片视图"按钮
        self.btn_cards_to_table: StarButton | None = None  # "表格视图"按钮

        # ---- 重入保护 ----
        self._refcards_reflow_guard: bool = False
        self._refcards_reflow_timer: QTimer | None = None

        # ---- 搜索状态（v1.4.0）----
        self._search_keyword: str = ""
        self._search_edit: QLineEdit | None = None
        self._btn_clear_search: StarButton | None = None

    # ---- 属性 ----
    @property
    def ref_doc_rows(self) -> list[dict]:
        return self._ref_doc_rows

    @ref_doc_rows.setter
    def ref_doc_rows(self, value: list[dict]):
        self._ref_doc_rows = value if isinstance(value, list) else []

    @property
    def ref_doc_table(self) -> QTableWidget | None:
        return self._ref_doc_table

    @property
    def ref_cards_scroll(self) -> QScrollArea | None:
        return self._ref_cards_scroll

    @property
    def ref_cards_grid(self) -> QGridLayout | None:
        return self._ref_cards_grid

    @property
    def ref_cards(self) -> list[QFrame]:
        return self._ref_cards

    @property
    def ref_multiline_delegate(self) -> RefDocMultilineDelegate | None:
        return self._ref_multiline_delegate

    # ================================================================
    #  UI 构建
    # ================================================================
    def build_ui(self, main_window, centre_stack) -> tuple[QWidget, QWidget]:
        """构建资料稿表格页面和卡片页面，添加到 centre_stack 并返回两个页面 widget

        Args:
            main_window: StarDebateWindow 实例
            centre_stack: QStackedWidget，两个页面将被添加到其中

        Returns:
            (page_ref_doc, page_ref_cards) 两个页面 QWidget
        """
        self._mw = main_window

        # ---- 第 4 页：资料稿表格编辑页 ----
        page_ref_doc = QWidget()
        page_ref_doc.setObjectName("refDocPage")
        ref_layout = QVBoxLayout(page_ref_doc)
        ref_layout.setSpacing(10)
        ref_layout.setContentsMargins(10, 10, 10, 10)

        # 工具栏
        ref_toolbar = QHBoxLayout()
        ref_toolbar.setSpacing(8)
        btn_back_ref = StarButton("\u2190 返回辩论详情", None, layout_mode="text_only", ratio_h=0.7)
        btn_back_ref.setFixedHeight(32)
        btn_back_ref.clicked.connect(lambda: centre_stack.setCurrentIndex(1))

        btn_save_ref = StarButton("保存资料稿", None, layout_mode="text_only", ratio_h=0.7)
        btn_save_ref.setObjectName("primaryBtn")
        btn_save_ref.setFixedHeight(32)
        btn_save_ref.clicked.connect(self._on_save_ref_doc)

        btn_add_row = StarButton("\uff0b 添加行", None, layout_mode="text_only", ratio_h=0.7)
        btn_add_row.setFixedHeight(32)
        btn_add_row.clicked.connect(self._on_add_ref_row)

        btn_del_row = StarButton("\u2715 删除行", None, layout_mode="text_only", ratio_h=0.7)
        btn_del_row.setFixedHeight(32)
        btn_del_row.clicked.connect(self._on_delete_ref_row)

        btn_auto_adjust = StarButton("自动调整", None, layout_mode="text_only", ratio_h=0.7)
        btn_auto_adjust.setFixedHeight(32)
        btn_auto_adjust.setToolTip("自动调整三列宽度，使当前窗口内显示尽可能多的行")
        btn_auto_adjust.clicked.connect(self._on_auto_adjust_columns)

        btn_import_table = StarButton("导入表格", None, layout_mode="text_only", ratio_h=0.7)
        btn_import_table.setFixedHeight(32)
        btn_import_table.setToolTip("导入 Excel(.xlsx/.xls) 或 CSV 表格数据，智能匹配列后加入到资料稿")
        btn_import_table.clicked.connect(self._on_import_table_to_ref_doc)

        self.btn_ref_card_view = StarButton("卡片视图", None, layout_mode="text_only", ratio_h=0.7)
        self.btn_ref_card_view.setFixedHeight(32)
        self.btn_ref_card_view.clicked.connect(self._on_show_ref_cards)

        ref_toolbar.addWidget(btn_back_ref)
        ref_toolbar.addStretch()
        ref_toolbar.addWidget(btn_import_table)
        ref_toolbar.addWidget(btn_add_row)
        ref_toolbar.addWidget(btn_del_row)
        ref_toolbar.addWidget(btn_auto_adjust)
        ref_toolbar.addWidget(self.btn_ref_card_view)
        ref_toolbar.addWidget(btn_save_ref)
        ref_toolbar.addStretch()

        # 三列表格
        self._ref_doc_table = QTableWidget(0, 3)
        self._ref_doc_table.setObjectName("refDocTable")
        self._ref_doc_table.setFont(QFont("Microsoft YaHei", 11))
        self._ref_doc_table.setHorizontalHeaderLabels(self.COLUMNS)
        self._ref_doc_table.horizontalHeader().setStretchLastSection(True)
        self._ref_doc_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._ref_doc_table.setSelectionMode(QTableWidget.SingleSelection)
        self._ref_doc_table.setAlternatingRowColors(True)
        self._ref_doc_table.verticalHeader().setVisible(True)
        self._ref_doc_table.verticalHeader().setDefaultSectionSize(48)

        # 多行文本代理
        self._ref_multiline_delegate = RefDocMultilineDelegate(self._ref_doc_table)
        self._ref_doc_table.setItemDelegateForColumn(0, self._ref_multiline_delegate)
        self._ref_doc_table.setItemDelegateForColumn(1, self._ref_multiline_delegate)
        self._ref_doc_table.setItemDelegateForColumn(2, self._ref_multiline_delegate)

        # 表格编辑完成 → 自动调整行高
        self._ref_doc_table.itemChanged.connect(self._on_ref_table_item_changed)
        # 列宽变化 → 重新计算所有行高
        self._ref_doc_table.horizontalHeader().sectionResized.connect(self._on_ref_table_col_resized)
        # 列可拖拽调整宽度
        self._ref_doc_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._ref_doc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self._ref_doc_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)

        ref_layout.addLayout(ref_toolbar)
        ref_layout.addWidget(self._ref_doc_table)
        centre_stack.addWidget(page_ref_doc)

        # ---- 第 5 页：资料卡片视图 ----
        page_ref_cards = QWidget()
        page_ref_cards.setObjectName("refCardsPage")
        cards_layout = QVBoxLayout(page_ref_cards)
        cards_layout.setSpacing(10)
        cards_layout.setContentsMargins(10, 10, 10, 10)

        # 卡片工具栏
        cards_toolbar = QHBoxLayout()
        cards_toolbar.setSpacing(8)
        btn_back_cards = StarButton("\u2190 返回辩论详情", None, layout_mode="text_only", ratio_h=0.7)
        btn_back_cards.setFixedHeight(32)
        btn_back_cards.clicked.connect(lambda: centre_stack.setCurrentIndex(1))

        self.btn_cards_to_table = StarButton("表格视图", None, layout_mode="text_only", ratio_h=0.7)
        self.btn_cards_to_table.setFixedHeight(32)
        self.btn_cards_to_table.clicked.connect(self._on_open_ref_doc)

        # ---- 搜索框（卡片页）----
        self._search_edit = QLineEdit()
        self._search_edit.setObjectName("lineEdit")
        self._search_edit.setPlaceholderText("搜索关键词...")
        self._search_edit.setFont(QFont("Microsoft YaHei", 8))
        self._search_edit.setFixedHeight(32)
        self._search_edit.setMinimumWidth(180)
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.returnPressed.connect(
            lambda: self._on_search_changed(self._search_edit.text()))
        self._search_edit.textChanged.connect(self._on_search_text_changed)

        self._btn_clear_search = StarButton("\u2715 清空", None, layout_mode="text_only", ratio_h=0.7)
        self._btn_clear_search.setFixedHeight(32)
        self._btn_clear_search.clicked.connect(self._on_clear_search)
        self._btn_clear_search.hide()

        btn_refresh_cards = StarButton("刷新卡片", None, layout_mode="text_only", ratio_h=0.7)
        btn_refresh_cards.setFixedHeight(32)
        btn_refresh_cards.clicked.connect(lambda: self._build_ref_cards())

        cards_toolbar.addWidget(btn_back_cards)
        cards_toolbar.addWidget(self._search_edit)
        cards_toolbar.addWidget(self._btn_clear_search)
        cards_toolbar.addStretch()
        cards_toolbar.addWidget(btn_refresh_cards)
        cards_toolbar.addWidget(self.btn_cards_to_table)
        cards_toolbar.addStretch()

        # 卡片滚动区域
        self._ref_cards_scroll = QScrollArea()
        self._ref_cards_scroll.setObjectName("refCardsScroll")
        self._ref_cards_scroll.setWidgetResizable(True)
        self._ref_cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 安装事件过滤器，监听滚动区域尺寸变化
        self._ref_cards_scroll.installEventFilter(main_window)

        self._ref_cards_container = QWidget()
        self._ref_cards_container.setObjectName("refCardsContainer")
        self._ref_cards_grid = QGridLayout(self._ref_cards_container)
        self._ref_cards_grid.setContentsMargins(4, 4, 4, 4)
        self._ref_cards_grid.setSpacing(12)
        self._ref_cards_scroll.setWidget(self._ref_cards_container)

        cards_layout.addLayout(cards_toolbar)
        cards_layout.addWidget(self._ref_cards_scroll)
        centre_stack.addWidget(page_ref_cards)

        return page_ref_doc, page_ref_cards

    # ================================================================
    #  文件名工具
    # ================================================================
    def _get_ref_doc_filename(self) -> str | None:
        """生成资料稿文件路径"""
        mw = self._mw
        if not mw or not mw.current_debate_path:
            return None
        dir_name = os.path.dirname(mw.current_debate_path)
        base = os.path.splitext(os.path.basename(mw.current_debate_path))[0]
        return os.path.join(dir_name, f"{base}_资料稿.json")

    # ================================================================
    #  数据加载与刷新
    # ================================================================
    def load_data_from_file(self) -> None:
        """从文件加载资料稿数据并刷新表格"""
        ref_file = self._get_ref_doc_filename()
        if not ref_file:
            self._ref_doc_rows.clear()
            self._refresh_ref_doc_table()
            return
        if os.path.isfile(ref_file):
            try:
                with open(ref_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                rows = data.get("rows", [])
                self._ref_doc_rows = rows if isinstance(rows, list) else []
            except (json.JSONDecodeError, OSError) as e:
                mw = self._mw
                if mw:
                    mw._update_status(f"资料稿加载失败: {str(e)}")
                self._ref_doc_rows.clear()
        else:
            self._ref_doc_rows.clear()
        self._refresh_ref_doc_table()

    def _refresh_ref_doc_table(self):
        """刷新资料稿表格显示"""
        table = self._ref_doc_table
        if table is None:
            return
        table.blockSignals(True)
        table.setRowCount(0)
        for row_idx, row_data in enumerate(self._ref_doc_rows):
            table.insertRow(row_idx)
            arg_text = row_data.get("argument", "")
            content_text = row_data.get("content", "")
            source_text = row_data.get("source", "")

            arg_item = QTableWidgetItem(arg_text)
            content_item = QTableWidgetItem(content_text)
            source_item = QTableWidgetItem(source_text)

            arg_item.setFont(QFont("Microsoft YaHei", 11))
            content_item.setFont(QFont("Microsoft YaHei", 11))
            source_item.setFont(QFont("Microsoft YaHei", 11))

            table.setItem(row_idx, 0, arg_item)
            table.setItem(row_idx, 1, content_item)
            table.setItem(row_idx, 2, source_item)

        table.blockSignals(False)
        self._update_ref_row_heights()

        if table.rowCount() == 0:
            table.insertRow(0)

    def _update_ref_row_heights(self):
        """根据内容智能计算并设置所有行高度（搜索高亮时使用纯文本计算）"""
        table = self._ref_doc_table
        delegate = self._ref_multiline_delegate
        if table is None or delegate is None:
            return
        for row in range(table.rowCount()):
            max_h = delegate._min_row_height
            for col in range(table.columnCount()):
                col_w = table.columnWidth(col)
                if col_w <= 0:
                    col_w = 200
                item = table.item(row, col)
                if item:
                    # 优先使用 EditRole 纯文本计算高度
                    text = item.data(Qt.EditRole)
                    if not text:
                        text = item.text()
                    text = str(text) if text else ""
                else:
                    text = ""
                h = delegate.get_row_height(text, col_w)
                if h > max_h:
                    max_h = h
            table.setRowHeight(row, max_h)

    # ================================================================
    #  搜索功能（v1.4.0）
    # ================================================================
    @staticmethod
    def _count_hits(row_data: dict, keyword: str) -> int:
        """统计一行数据中关键词的出现次数（不区分大小写）"""
        if not keyword:
            return 0
        kw = keyword.lower()
        total = 0
        for key in ("argument", "content", "source"):
            total += row_data.get(key, "").lower().count(kw)
        return total

    @staticmethod
    def _highlight_keyword(text: str, keyword: str) -> str:
        """将文本中的关键词用金色高亮 span 包裹"""
        if not keyword or not text:
            return text
        return re.sub(
            re.escape(keyword),
            r'<span style="background-color:#f9e2af; color:#1e1e2e; '
            r'font-weight:bold; padding:0 1px; border-radius:2px;">\g<0></span>',
            text,
            flags=re.IGNORECASE
        )

    def _on_search_text_changed(self, text: str):
        """搜索框文字变化 → 实时排序高亮"""
        # 显示/隐藏清空按钮
        if text:
            self._btn_clear_search.show()
        else:
            self._btn_clear_search.hide()
        self._on_search_changed(text)

    def _on_search_changed(self, text: str):
        """执行搜索：更新关键词 → 刷新卡片排序+高亮"""
        self._search_keyword = text.strip()
        # 刷新卡片视图（如果可见）
        if self._mw and hasattr(self._mw, 'centre_stack') and self._mw.centre_stack.currentIndex() == 5:
            self._build_ref_cards()

    def _on_clear_search(self):
        """点击清空按钮 → 清除搜索"""
        if self._search_edit:
            self._search_edit.clear()
            self._search_edit.setFocus()

    # ================================================================
    #  表格事件
    # ================================================================
    def _on_ref_table_item_changed(self, item: QTableWidgetItem):
        """单元格内容编辑完成 → 更新当前行高度"""
        if item is None or self._ref_doc_table is None:
            return
        row = item.row()
        table = self._ref_doc_table
        delegate = self._ref_multiline_delegate
        if delegate is None:
            return
        max_h = delegate._min_row_height
        for col in range(table.columnCount()):
            col_w = table.columnWidth(col)
            if col_w <= 0:
                col_w = 200
            cell = table.item(row, col)
            if cell:
                # 优先用 EditRole（纯文本）计算高度
                text = cell.data(Qt.EditRole)
                if not text:
                    text = cell.text()
                text = str(text) if text else ""
            else:
                text = ""
            h = delegate.get_row_height(text, col_w)
            if h > max_h:
                max_h = h
        table.setRowHeight(row, max_h)

    def _on_ref_table_col_resized(self, col: int, old_w: int, new_w: int):
        """列宽变化 → 重新计算所有行高"""
        self._update_ref_row_heights()

    # ================================================================
    #  表格行操作
    # ================================================================
    def _on_add_ref_row(self):
        """在表格末尾添加一个空行"""
        if self._ref_doc_table:
            self._ref_doc_table.insertRow(self._ref_doc_table.rowCount())

    def _on_delete_ref_row(self):
        """删除表格中选中的行"""
        table = self._ref_doc_table
        if table is None:
            return
        selected = table.selectedItems()
        if not selected:
            CustomDialog.information(self._mw, "提示", "请先选中要删除的行")
            return
        row = selected[0].row()
        result = CustomDialog.question(
            self._mw, "确认删除",
            f"确定要删除第 {row + 1} 行吗？",
            buttons=[("否", "no"), ("是", "yes")])
        if result == "yes":
            table.removeRow(row)

    # ================================================================
    #  保存
    # ================================================================
    def _on_save_ref_doc(self):
        """保存资料稿到文件"""
        mw = self._mw
        if not mw or not mw.current_debate_path:
            CustomDialog.warning(mw, "提示", "当前没有关联的辩论文件")
            return

        ref_file = self._get_ref_doc_filename()
        if not ref_file:
            return

        table = self._ref_doc_table
        rows = []
        for row_idx in range(table.rowCount()):
            arg_item = table.item(row_idx, 0)
            content_item = table.item(row_idx, 1)
            source_item = table.item(row_idx, 2)
            arg = arg_item.text().strip() if arg_item else ""
            content = content_item.text().strip() if content_item else ""
            source = source_item.text().strip() if source_item else ""
            if not arg and not content and not source:
                continue
            rows.append({
                "argument": arg,
                "content": content,
                "source": source,
            })

        self._ref_doc_rows = rows
        data = {"rows": rows}

        try:
            os.makedirs(os.path.dirname(ref_file), exist_ok=True)
            with open(ref_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # 刷新树控件以显示新文件
            project_path = mw._get_current_project_path()
            if project_path:
                mw._build_tree_from_path(project_path)
            mw._update_status(f"资料稿已保存（{len(rows)} 行）: {os.path.basename(ref_file)}")
            CustomDialog.information(mw, "保存成功", f"资料稿已保存\n共 {len(rows)} 行数据")
        except OSError as e:
            CustomDialog.error(mw, "保存失败", f"无法保存资料稿:\n{str(e)}")

    # ================================================================
    #  列宽比例
    # ================================================================
    def apply_column_ratio(self):
        """将资料稿表格三列按 1:2:2 比例分配宽度（前两列手动，第三列 Stretch 填满）"""
        table = self._ref_doc_table
        if table is None:
            return
        total_w = table.viewport().width()
        if total_w <= 0:
            QTimer.singleShot(50, self.apply_column_ratio)
            return
        w0 = max(100, total_w // 5)
        w1 = max(200, total_w * 2 // 5)
        table.setColumnWidth(0, w0)
        table.setColumnWidth(1, w1)

    # ================================================================
    #  自动调整列宽
    # ================================================================
    def _on_auto_adjust_columns(self):
        """自动调整三列宽度，最高优先级确保每个单元格的文字完全显示

        策略：
          1. 对每列，二分查找「舒适宽度」——最长文本在该宽度下不产生过度换行
             （行高 ≤ 3 倍最小行高，即约 144px / 6-7 行中文）
          2. 若三列舒适宽度之和在可用空间内，按舒适宽度分配，剩余均分
          3. 若超出可用空间，将舒适宽度作为最小约束按比例压缩
          4. 最后在满足约束的前提下，微调取总行高最小的方案
        """
        table = self._ref_doc_table
        delegate = self._ref_multiline_delegate
        if table is None or delegate is None:
            return

        viewport_w = table.viewport().width()
        if viewport_w <= 0:
            return

        row_count = table.rowCount()
        if row_count == 0:
            return

        # 纵向表头宽度（行号列）
        vheader_w = table.verticalHeader().width()
        available_w = viewport_w - vheader_w - 4

        ABS_MIN_W = 100      # 绝对最小宽度
        COMFORT_FACTOR = 3   # 行高倍率：舒适 = min_row_height × 3

        # ---- 1. 收集每列的最长文本 ----
        col_longest = ["", "", ""]
        for row in range(row_count):
            for col in range(3):
                item = table.item(row, col)
                text = item.text() if item else ""
                if len(text) > len(col_longest[col]):
                    col_longest[col] = text

        # ---- 2. 二分查找每列的「舒适宽度」 ----
        def _comfort_width(text: str, max_w: int) -> int:
            """找到最小宽度使 text 行高 ≤ COMFORT_FACTOR × min_row_height"""
            if not text:
                return ABS_MIN_W
            target_h = delegate._min_row_height * COMFORT_FACTOR
            lo, hi = ABS_MIN_W, max_w
            # 若最大宽度仍不能满足，取最大宽度
            if delegate.get_row_height(text, hi) <= target_h:
                hi = max_w
            else:
                return max_w  # 可用空间不足，返回最大宽度
            while lo < hi:
                mid = (lo + hi) // 2
                if delegate.get_row_height(text, mid) <= target_h:
                    hi = mid
                else:
                    lo = mid + 1
            return lo

        comfort_w = [
            _comfort_width(col_longest[0], available_w),
            _comfort_width(col_longest[1], available_w),
            _comfort_width(col_longest[2], available_w),
        ]
        total_comfort = sum(comfort_w)

        # ---- 3. 根据可用空间分配基础宽度 ----
        base_widths = [0, 0, 0]
        if total_comfort <= available_w:
            # 空间充足：先满足舒适宽度，剩余按内容密度分配
            extra = available_w - total_comfort
            col_text_len = [max(1, len(t)) for t in col_longest]
            total_len = sum(col_text_len)
            for col in range(3):
                base_widths[col] = comfort_w[col] + int(extra * col_text_len[col] / total_len)
            # 微调使总和精确
            base_widths[2] = available_w - base_widths[0] - base_widths[1]
        else:
            # 空间不足：以舒适宽度为比例压缩，但绝不低于舒适宽度的 50%
            ratio = [cw / total_comfort for cw in comfort_w]
            for col in range(3):
                ideal = int(available_w * ratio[col])
                base_widths[col] = max(ABS_MIN_W, min(ideal, comfort_w[col]),
                                       int(comfort_w[col] * 0.5))
            base_widths[2] = available_w - base_widths[0] - base_widths[1]

        # ---- 4. 在其附近微调，取总行高最小的方案 ----
        best_widths = (base_widths[0], base_widths[1], base_widths[2])
        best_total_h = float("inf")

        # 生成候选：base 左右小幅偏移（±10%, ±20% 在基础宽度间转移）
        candidates = []
        candidates.append((base_widths[0], base_widths[1], base_widths[2]))
        step = max(20, available_w // 40)  # 至少 20px 步长
        for d0 in (-step, 0, step):
            for d1 in (-step, 0, step):
                if d0 == 0 and d1 == 0:
                    continue
                w0 = max(ABS_MIN_W, base_widths[0] + d0)
                w1 = max(ABS_MIN_W, base_widths[1] + d1)
                w2 = available_w - w0 - w1
                if w2 < ABS_MIN_W:
                    continue
                candidates.append((w0, w1, w2))

        for w0, w1, w2 in candidates:
            # 计算总行高
            total_h = 0
            max_single_h = 0
            widths = [w0, w1, w2]
            for row in range(row_count):
                row_max_h = delegate._min_row_height
                for col in range(3):
                    item = table.item(row, col)
                    text = item.text() if item else ""
                    h = delegate.get_row_height(text, widths[col])
                    if h > row_max_h:
                        row_max_h = h
                total_h += row_max_h
                if row_max_h > max_single_h:
                    max_single_h = row_max_h

            # 评分：总行高权重 0.7 + 最大单行行高权重 0.3（惩罚过度换行）
            score = total_h * 0.7 + max_single_h * 0.3 * (row_count / max(1, row_count))
            if score < best_total_h:
                best_total_h = score
                best_widths = (w0, w1, w2)

        # ---- 5. 应用最佳列宽 ----
        if best_widths:
            table.blockSignals(True)
            table.setColumnWidth(0, best_widths[0])
            table.setColumnWidth(1, best_widths[1])
            table.setColumnWidth(2, best_widths[2])
            table.blockSignals(False)
            self._update_ref_row_heights()

        if self._mw:
            self._mw._update_status(
                f"已自动调整列宽 → 列0:{best_widths[0]}px 列1:{best_widths[1]}px 列2:{best_widths[2]}px"
            )

    # ================================================================
    #  公开切换 API
    # ================================================================
    def _on_open_ref_doc(self):
        """打开/切换到资料稿编辑页（表格视图）"""
        mw = self._mw
        if not mw:
            return
        if not mw.current_debate_path:
            CustomDialog.warning(mw, "提示", "请先在左侧树控件中选择一个辩论文件")
            return
        self.load_data_from_file()
        mw.centre_stack.setCurrentIndex(4)
        mw._update_status("资料稿编辑页已打开")

    _open_ref_doc = _on_open_ref_doc  # 兼容别名

    def _on_show_ref_cards(self):
        """打开/切换到资料卡片视图"""
        mw = self._mw
        if not mw:
            return
        if not mw.current_debate_path:
            CustomDialog.warning(mw, "提示", "请先在左侧树控件中选择一个辩论文件")
            return

        if mw.centre_stack.currentIndex() == 4:
            self._sync_table_to_rows()
        else:
            self.load_data_from_file()
        mw.centre_stack.setCurrentIndex(5)
        QTimer.singleShot(80, self._build_ref_cards)
        mw._update_status("资料卡片视图已打开")

    _show_ref_cards = _on_show_ref_cards  # 兼容别名

    def _sync_table_to_rows(self):
        """将表格当前数据同步到 _ref_doc_rows（优先用 EditRole 避免保存 HTML）"""
        table = self._ref_doc_table
        if table is None:
            return
        rows = []
        for row_idx in range(table.rowCount()):
            arg_item = table.item(row_idx, 0)
            content_item = table.item(row_idx, 1)
            source_item = table.item(row_idx, 2)

            def _get_plain(item):
                if not item:
                    return ""
                val = item.data(Qt.EditRole)
                if val:
                    return str(val).strip()
                text = item.text().strip()
                if '<span ' in text:
                    text = re.sub(r'<[^>]+>', '', text)
                return text

            arg = _get_plain(arg_item)
            content = _get_plain(content_item)
            source = _get_plain(source_item)
            if not arg and not content and not source:
                continue
            rows.append({"argument": arg, "content": content, "source": source})
        self._ref_doc_rows = rows

    # ================================================================
    #  资料卡片
    # ================================================================
    def _build_ref_cards(self):
        """根据 _ref_doc_rows 数据构建卡片网格（搜索时按命中数降序）"""
        grid = self._ref_cards_grid
        if grid is None:
            return
        # 清空旧卡片
        while grid.count():
            item = grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._ref_cards_container.updateGeometry()
        self._ref_cards_scroll.updateGeometry()
        QApplication.processEvents()

        if not self._ref_doc_rows:
            empty_label = QLabel("暂无资料数据，请先在表格视图中添加")
            empty_label.setObjectName("refDocEmptyHint")
            empty_label.setFont(QFont("Microsoft YaHei", 13))
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setFixedHeight(60)
            grid.addWidget(empty_label, 0, 0)
            return

        keyword = self._search_keyword

        # 搜索时按命中数降序排列
        if keyword:
            indexed = []
            for i, row_data in enumerate(self._ref_doc_rows):
                hits = self._count_hits(row_data, keyword)
                indexed.append((i, hits, row_data))
            indexed.sort(key=lambda x: (-x[1], x[0]))
        else:
            indexed = [(i, 0, row_data) for i, row_data in enumerate(self._ref_doc_rows)]

        cards = []
        for sort_pos, (orig_idx, _hits, row_data) in enumerate(indexed):
            arg = row_data.get("argument", "")
            content = row_data.get("content", "")
            source = row_data.get("source", "")
            card = self._create_ref_card(sort_pos + 1, arg, content, source)
            cards.append(card)

        self._ref_cards = cards
        self._ref_cards_container.updateGeometry()
        self._ref_cards_scroll.updateGeometry()
        QTimer.singleShot(50, self._arrange_cards_in_grid)
        QTimer.singleShot(250, self._arrange_cards_in_grid)

    def _create_ref_card(self, index: int, argument: str, content: str, source: str) -> QFrame:
        """创建单个资料卡片，搜索关键词以金色高亮"""
        card = QFrame()
        card.setObjectName("refCard")
        card.setFixedWidth(320)

        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(6)
        card_layout.setContentsMargins(14, 12, 14, 12)

        # 序号
        lbl_index = QLabel(f"#{index}")
        lbl_index.setObjectName("refCardIndex")
        lbl_index.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))

        keyword = self._search_keyword

        # 论证观点
        lbl_arg_title = QLabel("▎论证观点")
        lbl_arg_title.setObjectName("refCardSectionArg")
        lbl_arg_title.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))

        if keyword and argument:
            display_arg = self._highlight_keyword(argument, keyword)
            lbl_arg = QLabel(display_arg)
            lbl_arg.setTextFormat(Qt.RichText)
        else:
            lbl_arg = QLabel(argument if argument else "（未填写）")
        lbl_arg.setFont(QFont("Microsoft YaHei", 11))
        lbl_arg.setObjectName("refCardArgText" if argument else "refCardEmptyText")
        lbl_arg.setWordWrap(True)

        # 论证内容
        lbl_content_title = QLabel("▎论证内容")
        lbl_content_title.setObjectName("refCardSectionContent")
        lbl_content_title.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))

        if keyword and content:
            display_content = self._highlight_keyword(content, keyword)
            lbl_content = QLabel(display_content)
            lbl_content.setTextFormat(Qt.RichText)
        else:
            lbl_content = QLabel(content if content else "（未填写）")
        lbl_content.setFont(QFont("Microsoft YaHei", 11))
        lbl_content.setObjectName("refCardContentText" if content else "refCardEmptyText")
        lbl_content.setWordWrap(True)

        # 资料来源
        lbl_source_title = QLabel("▎资料来源")
        lbl_source_title.setObjectName("refCardSectionSource")
        lbl_source_title.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))

        if keyword and source:
            display_source = self._highlight_keyword(source, keyword)
            lbl_source = QLabel(display_source)
            lbl_source.setTextFormat(Qt.RichText)
        else:
            lbl_source = QLabel(source if source else "（未填写）")
        lbl_source.setFont(QFont("Microsoft YaHei", 10))
        lbl_source.setObjectName("refCardSourceText" if source else "refCardEmptyText")
        lbl_source.setWordWrap(True)
        lbl_source.setTextInteractionFlags(Qt.TextSelectableByMouse)

        card_layout.addWidget(lbl_index)
        card_layout.addWidget(lbl_arg_title)
        card_layout.addWidget(lbl_arg)
        card_layout.addWidget(lbl_content_title)
        card_layout.addWidget(lbl_content)
        card_layout.addWidget(lbl_source_title)
        card_layout.addWidget(lbl_source)
        card_layout.addStretch()

        return card

    def _arrange_cards_in_grid(self):
        """根据容器宽度智能选择 1/2 列，动态排布卡片"""
        if self._refcards_reflow_guard:
            return
        self._refcards_reflow_guard = True
        try:
            cards = self._ref_cards
            grid = self._ref_cards_grid
            if grid is None or not cards:
                return

            for card in cards:
                grid.removeWidget(card)

            self._ref_cards_container.updateGeometry()
            self._ref_cards_scroll.updateGeometry()
            QApplication.processEvents()

            container_width = self._ref_cards_scroll.viewport().width()
            if container_width <= 0:
                container_width = self._ref_cards_scroll.width() - (self._ref_cards_scroll.frameWidth() * 2)
            if container_width <= 0:
                container_width = self._ref_cards_scroll.width()
            if container_width <= 0:
                mw = self._mw
                parent_w = mw.centre_stack.currentWidget() if mw else None
                if parent_w:
                    container_width = parent_w.width() - 20
                else:
                    container_width = 800

            margins = grid.contentsMargins()
            avail_w = container_width - margins.left() - margins.right()
            spacing = grid.spacing()

            MIN_TWO_COL = 700
            cols = 2 if avail_w >= MIN_TWO_COL else 1
            actual_card_w = max(280, (avail_w - (cols - 1) * spacing) // cols)

            for col in range(grid.columnCount()):
                grid.setColumnStretch(col, 0)

            for i, card in enumerate(cards):
                row = i // cols
                col = i % cols
                card.setFixedWidth(actual_card_w)
                card.adjustSize()
                grid.addWidget(card, row, col)
                grid.setColumnStretch(col, 1)

            total = len(cards)
            last_row = (total - 1) // cols if total > 0 else 0
            grid.setRowStretch(last_row + 1, 1)

            self._ref_cards_container.updateGeometry()
        finally:
            self._refcards_reflow_guard = False

    # ================================================================
    #  表格导入
    # ================================================================
    def _on_import_table_to_ref_doc(self):
        """导入 Excel/CSV 表格，智能映射列到资料稿三列"""
        mw = self._mw
        if not mw:
            return
        if not mw.current_debate_path:
            CustomDialog.warning(mw, "提示", "请先在左侧树控件中选择一个辩论文件")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            mw, "选择要导入的表格文件",
            "",
            "表格文件 (*.csv *.xlsx *.xls);;CSV 文件 (*.csv);;Excel 文件 (*.xlsx *.xls);;所有文件 (*)"
        )
        if not file_path:
            return

        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == ".csv":
                rows, headers = self._read_csv_file(file_path)
            elif ext in (".xlsx", ".xls"):
                rows, headers = self._read_excel_file(file_path)
            else:
                CustomDialog.warning(mw, "不支持的文件格式",
                                    f"不支持的文件类型: {ext}\n请选择 .csv、.xlsx 或 .xls 文件")
                return
        except Exception as e:
            CustomDialog.error(mw, "读取失败", f"无法读取表格文件:\n{str(e)}")
            return

        if not rows:
            CustomDialog.information(mw, "提示", "文件中没有有效数据行")
            return

        mapping = self._auto_map_columns(headers)
        unmapped = [i for i, (h, target) in enumerate(zip(headers, mapping)) if target is None]

        if unmapped and any(m is not None for m in mapping):
            mapping = self._show_column_mapping_dialog(headers, mapping)
            if mapping is None:
                return

        mapped_count = sum(1 for m in mapping if m is not None)
        if mapped_count == 0:
            CustomDialog.warning(mw, "提示", "没有匹配到任何资料稿列，请手动选择列映射关系")
            mapping = self._show_column_mapping_dialog(headers, [None] * len(headers))
            if mapping is None:
                return

        added = 0
        table = self._ref_doc_table
        for row_data in rows:
            arg, content, source = "", "", ""
            for col_idx, target_field in enumerate(mapping):
                if target_field == "argument" and col_idx < len(row_data):
                    arg = str(row_data[col_idx]).strip() if row_data[col_idx] is not None else ""
                elif target_field == "content" and col_idx < len(row_data):
                    content = str(row_data[col_idx]).strip() if row_data[col_idx] is not None else ""
                elif target_field == "source" and col_idx < len(row_data):
                    source = str(row_data[col_idx]).strip() if row_data[col_idx] is not None else ""

            if not arg and not content and not source:
                continue

            row_idx = table.rowCount()
            table.insertRow(row_idx)
            table.setItem(row_idx, 0, QTableWidgetItem(arg))
            table.setItem(row_idx, 1, QTableWidgetItem(content))
            table.setItem(row_idx, 2, QTableWidgetItem(source))
            table.setRowHeight(row_idx, 48)
            added += 1

        self._sync_table_to_rows()
        mw._update_status(f"已从表格导入 {added} 行数据到资料稿: {os.path.basename(file_path)}")
        CustomDialog.information(mw, "导入完成",
                                f"成功导入 {added} 行数据到资料稿\n来源: {os.path.basename(file_path)}")

    def _read_csv_file(self, file_path: str) -> tuple:
        """读取 CSV 文件，返回 (数据行列表, 表头列表)"""
        rows = []
        headers = []
        for encoding in ["utf-8-sig", "utf-8", "gbk", "gb2312", "latin-1"]:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    reader = csv.reader(f)
                    all_rows = list(reader)
                if not all_rows:
                    continue
                headers = [h.strip() for h in all_rows[0]]
                rows = all_rows[1:]
                break
            except (UnicodeDecodeError, csv.Error):
                continue
        if not rows and not headers:
            raise ValueError("无法读取 CSV 文件，请检查文件编码是否为 UTF-8 或 GBK")
        return rows, headers

    def _read_excel_file(self, file_path: str) -> tuple:
        """读取 Excel 文件，返回 (数据行列表, 表头列表)"""
        ext = os.path.splitext(file_path)[1].lower()
        rows = []
        headers = []

        if ext == ".xlsx":
            try:
                import openpyxl
            except ImportError:
                raise ImportError(
                    "读取 .xlsx 文件需要安装 openpyxl 库。\n请在终端执行: pip install openpyxl"
                )
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            ws = wb.active
            for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
                cell_values = [str(c) if c is not None else "" for c in row]
                if row_idx == 0:
                    headers = [h.strip() for h in cell_values]
                else:
                    rows.append(cell_values)
            wb.close()
        elif ext == ".xls":
            try:
                import xlrd
            except ImportError:
                raise ImportError(
                    "读取 .xls 文件需要安装 xlrd 库。\n请在终端执行: pip install xlrd"
                )
            wb = xlrd.open_workbook(file_path)
            ws = wb.sheet_by_index(0)
            for row_idx in range(ws.nrows):
                cell_values = [
                    str(ws.cell_value(row_idx, col)) if ws.cell_value(row_idx, col) != "" else ""
                    for col in range(ws.ncols)
                ]
                if row_idx == 0:
                    headers = [h.strip() for h in cell_values]
                else:
                    rows.append(cell_values)
        else:
            raise ValueError(f"不支持的 Excel 格式: {ext}")

        # 去除表头为空的列
        if headers:
            valid_indices = [i for i, h in enumerate(headers) if h]
            if valid_indices:
                headers = [headers[i] for i in valid_indices]
                new_rows = []
                for row in rows:
                    new_rows.append([row[i] if i < len(row) else "" for i in valid_indices])
                rows = new_rows

        return rows, headers

    def _auto_map_columns(self, headers: list[str]) -> list:
        """智能匹配表头到资料稿三列
        返回与 headers 等长的列表，每项为 "argument" / "content" / "source" / None
        """
        mapping = [None] * len(headers)

        arg_keywords = ["观点", "论点", "主张", "立场", "argument", "claim", "point", "assertion"]
        content_keywords = ["内容", "论证", "论据", "阐述", "说明", "分析", "content", "detail",
                            "description", "analysis", "reasoning"]
        source_keywords = ["来源", "资料", "出处", "引用", "参考", "source", "reference", "citation", "origin"]

        def match_score(header: str, keywords: list) -> int:
            h = header.lower()
            score = 0
            for kw in keywords:
                kw_low = kw.lower()
                if kw_low == h:
                    score += 10
                elif kw_low in h:
                    score += 5
                elif h in kw_low:
                    score += 3
                common = sum(1 for c in kw_low if c in h)
                score += common * 0.1
            return score

        scores = []
        for header in headers:
            if not header:
                scores.append((0, 0, 0))
                continue
            s_arg = match_score(header, arg_keywords)
            s_content = match_score(header, content_keywords)
            s_source = match_score(header, source_keywords)
            scores.append((s_arg, s_content, s_source))

        assigned = set()
        col_score_list = []
        for col_idx, (s_arg, s_content, s_source) in enumerate(scores):
            max_s = max(s_arg, s_content, s_source)
            if max_s > 0.5:
                field = "argument" if s_arg >= max(s_content, s_source) else (
                    "content" if s_content >= s_source else "source")
                col_score_list.append((max_s, col_idx, field))

        col_score_list.sort(key=lambda x: x[0], reverse=True)

        for max_s, col_idx, field in col_score_list:
            if field not in assigned:
                mapping[col_idx] = field
                assigned.add(field)

        # 宽松匹配
        if "argument" not in assigned:
            for col_idx, header in enumerate(headers):
                if mapping[col_idx] is None and header:
                    h = header.lower()
                    if "辩" in h or "arg" in h[:5] or "论" in h:
                        mapping[col_idx] = "argument"
                        assigned.add("argument")
                        break

        if "content" not in assigned:
            for col_idx, header in enumerate(headers):
                if mapping[col_idx] is None and header:
                    h = header.lower()
                    if "内容" in h or "cont" in h[:5] or "desc" in h[:5] or "说明" in h:
                        mapping[col_idx] = "content"
                        assigned.add("content")
                        break

        if "source" not in assigned:
            for col_idx, header in enumerate(headers):
                if mapping[col_idx] is None and header:
                    h = header.lower()
                    if "来" in h or "sour" in h[:5] or "ref" in h[:5] or "出处" in h:
                        mapping[col_idx] = "source"
                        assigned.add("source")
                        break

        return mapping

    def _show_column_mapping_dialog(self, headers: list[str], auto_mapping: list) -> list | None:
        """显示列映射对话框，让用户选择各列对应的资料稿字段"""
        mw = self._mw
        dialog = QDialog(mw)
        dialog.setWindowTitle("列映射 - 资料稿导入")
        dialog.resize(550, 350)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        lbl_info = QLabel("请为表格中的每一列指定对应的资料稿字段：")
        lbl_info.setObjectName("refDocImportInfo")
        lbl_info.setFont(QFont("Microsoft YaHei", 11))
        layout.addWidget(lbl_info)

        mapping_widget = QWidget()
        mapping_widget.setObjectName("mappingWidget")
        mapping_layout = QFormLayout(mapping_widget)
        mapping_layout.setSpacing(8)
        mapping_layout.setContentsMargins(10, 10, 10, 10)

        field_options = ["（不导入）", "论证观点", "论证内容", "资料来源"]
        combo_boxes: list[QComboBox] = []

        for col_idx, header in enumerate(headers):
            row_layout = QHBoxLayout()
            lbl_col = QLabel(f"列{col_idx + 1}:")
            lbl_col.setObjectName("refDocImportColLabel")
            lbl_col.setFont(QFont("Microsoft YaHei", 10))
            lbl_header = QLabel(f"「{header if header else '(空表头)'}」")
            lbl_header.setObjectName("refDocImportHeaderLabel")
            lbl_header.setFont(QFont("Microsoft YaHei", 10))
            lbl_header.setMinimumWidth(120)

            combo = QComboBox()
            combo.addItems(field_options)
            combo.setFont(QFont("Microsoft YaHei", 10))

            if auto_mapping[col_idx] == "argument":
                combo.setCurrentIndex(1)
            elif auto_mapping[col_idx] == "content":
                combo.setCurrentIndex(2)
            elif auto_mapping[col_idx] == "source":
                combo.setCurrentIndex(3)
            else:
                combo.setCurrentIndex(0)

            combo_boxes.append(combo)
            row_layout.addWidget(lbl_col)
            row_layout.addWidget(lbl_header)
            row_layout.addWidget(combo)
            mapping_layout.addRow(row_layout)

        layout.addWidget(mapping_widget)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = StarButton("取消", None, layout_mode="text_only", ratio_h=0.7)
        btn_cancel.setFixedHeight(34)
        btn_cancel.clicked.connect(dialog.reject)

        btn_confirm = StarButton("确认导入", None, layout_mode="text_only", ratio_h=0.7)
        btn_confirm.setObjectName("primaryBtn")
        btn_confirm.setFixedHeight(34)
        btn_confirm.clicked.connect(dialog.accept)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_confirm)
        layout.addLayout(btn_layout)

        dialog.setStyleSheet(f"""
            QDialog {
                background-color: {tc("base")};
                color: {tc("text")};
                font-family: "Microsoft YaHei";
            }
            #mappingWidget {
                background-color: {tc("surface")};
                border-radius: 10px;
                border: 1px solid {tc("overlay")};
            }
            QComboBox {
                background-color: {tc("crust")};
                border: 1px solid {tc("overlay")};
                border-radius: 6px;
                padding: 4px 10px;
                color: {tc("text")};
                min-width: 130px;
            }
            QComboBox:focus {
                border: 1px solid {tc("accent_blue")};
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: {tc("surface")};
                border: 1px solid {tc("divider")};
                color: {tc("text")};
                selection-background-color: {tc("overlay")};
                selection-color: {tc("accent_blue")};
            }
            QLabel {
                color: {tc("text")};
            }
        """)

        result = dialog.exec_()
        if result != QDialog.Accepted:
            return None

        final_mapping = [None] * len(headers)
        for col_idx, combo in enumerate(combo_boxes):
            idx = combo.currentIndex()
            if idx == 1:
                final_mapping[col_idx] = "argument"
            elif idx == 2:
                final_mapping[col_idx] = "content"
            elif idx == 3:
                final_mapping[col_idx] = "source"

        return final_mapping
