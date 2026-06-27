"""
DebateClaw AI Markdown 表格卡片
==============================
从 Markdown 文本中提取表格，创建 QTableWidget 卡片。
"""

import re
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QTextEdit,
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QColor, QFont

# 匹配 Markdown 表格块（多行 |xxx| 结构）
_RE_TABLE_BLOCK = re.compile(
    r'^(\|.+?\|)\n\|[-| ]+\|\n((?:\|.+?\|\n?)*)',
    re.MULTILINE,
)


def parse_tables(text: str) -> list[dict]:
    """解析 Markdown 文本中的表格，返回 [{"header":[...], "rows":[[...],...]}]。"""
    results = []
    for m in _RE_TABLE_BLOCK.finditer(text):
        header_line = m.group(1).strip("|").split("|")
        header = [c.strip() for c in header_line]
        body = m.group(2).strip()
        rows = []
        if body:
            for line in body.strip().split("\n"):
                row = [c.strip() for c in line.strip("|").split("|")]
                if row and any(c for c in row):
                    rows.append(row)
        results.append({"header": header, "rows": rows})
    return results


def strip_tables(text: str) -> str:
    """移除文本中的 Markdown 表格块，保留其他内容。"""
    return _RE_TABLE_BLOCK.sub("", text).strip()


class TableCard(QFrame):
    """简约表格卡片，与 AI 气泡风格统一。"""

    def __init__(self, header: list[str], rows: list[list[str]],
                 max_rows_visible: int = 8, parent=None):
        super().__init__(parent)
        self.setObjectName("clawTableCard")
        self.setStyleSheet(_card_qss())

        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        self._table = QTableWidget()
        self._table.setColumnCount(len(header))
        self._table.setHorizontalHeaderLabels(header)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # 填充行
        self._table.setRowCount(len(rows))
        fm = QFont("HarmonyOS Sans SC", 9)
        for ri, row in enumerate(rows):
            for ci, cell in enumerate(row):
                item = QTableWidgetItem(cell)
                item.setFont(fm)
                self._table.setItem(ri, ci, item)

        # 行高自适应
        rh = fm.pointSize() + 12
        self._table.verticalHeader().setDefaultSectionSize(rh)
        self._table.verticalHeader().setVisible(False)

        # 最大可见行
        visible_h = min(len(rows), max_rows_visible) * rh + self._table.horizontalHeader().height() + 4
        self._table.setFixedHeight(visible_h)
        self._table.setAlternatingRowColors(True)

        lo.addWidget(self._table)

    def update_rows(self, rows: list[list[str]]):
        """流式追加行。"""
        self._table.setRowCount(len(rows))
        fm = QFont("HarmonyOS Sans SC", 9)
        for ri, row in enumerate(rows):
            for ci, cell in enumerate(row):
                item = self._table.item(ri, ci)
                if not item:
                    item = QTableWidgetItem(cell)
                    item.setFont(fm)
                    self._table.setItem(ri, ci, item)
                else:
                    item.setText(cell)


def _card_qss() -> str:
    return (
        "QFrame#clawTableCard{background-color:#F5F5F5;border:1px solid #E0E0E0;"
        "border-radius:6px;margin:4px 0;}"
        "QTableWidget{border:none;background:transparent;"
        "gridline-color:#E0E0E0;font-size:9pt;}"
        "QHeaderView::section{background:#E8E8E8;border:none;padding:4px 8px;"
        "font-weight:bold;font-size:9pt;}"
        "QTableWidget::item{padding:2px 6px;}"
    )
