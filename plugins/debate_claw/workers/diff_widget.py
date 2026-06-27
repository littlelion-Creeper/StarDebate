# -*- coding: utf-8 -*-
"""
DebateClaw Diff Card Widget
============================
类似 Cursor/Copilot 的 Diff Widget（代码变更卡片），用于在 AI 气泡中展示段落修改建议。
支持三态切换（pending ⇄ accepted/rejected）、上下对比视图、Accept/Reject/全部接受操作。

Diff 标记格式:
    [DIFF:标题="xxx" +N -M]
    - 被删除的原文行
    + 新增的修改后行
      上下文行（不变）
    [/DIFF]
"""

import re
from enum import Enum

from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QScrollArea, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QFont


# ── Diff 行类型 ──

class _LineType(Enum):
    """Diff 行类型枚举"""
    CONTEXT = "context"   # 无变化上下文行
    DELETED = "deleted"   # 删除行 (-)
    ADDED = "added"       # 新增行 (+)


# ── Diff 块解析正则 ──

_RE_DIFF_BLOCK = re.compile(
    r'\[DIFF\s*:\s*(.*?)\](.*?)\[/DIFF\]',
    re.DOTALL,
)

_RE_DIFF_HEADER = re.compile(r'title\s*=\s*["\']([^"\']*)["\']')
_RE_ADD_DEL = re.compile(r'\+(\d+)\s+-?(\d+)?|-?\d+\s+-(\d+)')
_RE_PARAGRAPH = re.compile(r'段落\s*=\s*["\']([^"\']*)["\']')


def parse_diff_blocks(text: str) -> list:
    """
    从 Markdown 文本中解析所有 [DIFF]...[/DIFF] 块。
    
    Returns:
        list[dict]: 每个 dict 包含:
            - title (str): 标题
            - additions (int): 新增行数
            - deletions (int): 删除行数
            - lines (list[tuple]): [(LineType, str), ...]
    """
    results = []
    for m in _RE_DIFF_BLOCK.finditer(text):
        header_raw = m.group(1).strip()
        body = m.group(2)

        # 解析标题
        title_m = _RE_DIFF_HEADER.search(header_raw)
        title = title_m.group(1).strip() if title_m else "修改建议"

        # 解析 +/- 统计
        additions = 0
        deletions = 0
        stat_m = _RE_ADD_DEL.search(header_raw)
        if stat_m:
            if stat_m.group(1):
                additions = int(stat_m.group(1))
            if stat_m.group(2):
                deletions = int(stat_m.group(2))
            elif stat_m.group(3):
                deletions = int(stat_m.group(3))

        # 解析段落 ID（新增）
        paragraph_id = None
        para_m = _RE_PARAGRAPH.search(header_raw)
        if para_m:
            paragraph_id = para_m.group(1).strip()
        
        # 解析各行
        lines = []
        for line in body.split('\n'):
            stripped = line.rstrip('\r')
            if not stripped:
                # 空行作为 context
                lines.append((_LineType.CONTEXT, ""))
            elif stripped.startswith('- ') or stripped == '-':
                content = stripped[2:] if stripped.startswith('- ') else ""
                lines.append((_LineType.DELETED, content))
            elif stripped.startswith('+ ') or stripped == '+':
                content = stripped[2:] if stripped.startswith('+ ') else ""
                lines.append((_LineType.ADDED, content))
            elif stripped.startswith('  '):
                lines.append((_LineType.CONTEXT, stripped))
            else:
                lines.append((_LineType.CONTEXT, stripped))
        
        results.append({
            "title": title,
            "additions": additions,
            "deletions": deletions,
            "paragraph": paragraph_id,   # 新增：目标段落 ID
            "lines": lines,
            "raw_header": header_raw,
            "raw_body": body,
        })
    
    return results


def strip_diff_blocks(text: str) -> str:
    """
    移除文本中的 [DIFF]...[/DIFF] 标记块，保留其他内容。
    用于获取不含 DIFF 标记的纯文本版本。
    """
    return _RE_DIFF_BLOCK.sub("", text)


# ── 三态枚举 ──

class DiffState(Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


# ── Diff 卡片组件 ──

class DiffCard(QFrame):
    """
    Diff 修改建议卡片 — 内嵌于 AI 气泡中的自定义组件。
    
    视觉布局:
    ┌──────────────────────────────────────────────┐
    │ 📝 标题文字          [+N -M]                 │  ← 元数据头
    ├──────────────────────────────────────────────┤
    │                                              │
    │  - 被删除的行（红色背景）                     │
    │  + 新增的行（绿色背景）                       │
    │    上下文行（无背景变化）                      │
    │                                              │
    ├──────────────────────────────────────────────┤
    │     [✓ 接受]  [✖ 拒绝]                      │  ← 操作按钮
    └──────────────────────────────────────────────┘
    
    Signals:
        accepted(str): 用户点击接受，传入 card 的唯一标识
        rejected(str): 用户点击拒绝
    """
    
    accepted = pyqtSignal(str)
    rejected = pyqtSignal(str)
    no_paragraph_warning = pyqtSignal(str)  # 安全模式下接受无段落ID的diff时发出
    
    def __init__(self, card_id: str, title: str, additions: int, deletions: int,
                 lines: list, colors: dict, parent=None, paragraph_id: str = None):
        super().__init__(parent)

        self._card_id = card_id
        self._title = title
        self._additions = additions
        self._deletions = deletions
        self._lines = lines  # list of (_LineType, str)
        self._colors = colors
        self._state = DiffState.PENDING
        self._paragraph_id = paragraph_id  # 新增：目标段落 ID（用于段落级精确替换）
        
        self.setObjectName("clawDiffCard")
        self.setMaximumHeight(400)
        
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)
        
        # ── 元数据头 ──
        header = self._build_header()
        lo.addWidget(header)
        
        # ── 内容区（可滚动）──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setObjectName("clawDiffScroll")
        scroll.setStyleSheet(self._scroll_qss())
        
        content_widget = QWidget()
        content_lo = QVBoxLayout(content_widget)
        content_lo.setContentsMargins(10, 6, 10, 6)
        content_lo.setSpacing(1)
        
        for ltype, text in self._lines:
            row = self._build_line(ltype, text)
            content_lo.addWidget(row)
        
        content_lo.addStretch()
        scroll.setWidget(content_widget)
        lo.addWidget(scroll, 1)
        
        # ── 操作按钮栏 ──
        btn_bar = self._build_button_bar()
        lo.addWidget(btn_bar)
        
        self.update_appearance()
    
    @property
    def state(self) -> DiffState:
        return self._state
    
    @property
    def card_id(self) -> str:
        return self._card_id

    @property
    def paragraph_id(self) -> str | None:
        return self._paragraph_id
    
    def get_accepted_content(self) -> str:
        """
        返回被接受的修改后文本（仅 + 和 context 行拼接）。
        用于替换气泡内的原始内容。
        """
        result = []
        for ltype, text in self._lines:
            if ltype != _LineType.DELETED:
                result.append(text if text else "")
        return "\n".join(result).strip()
    
    def get_original_text(self) -> str:
        """
        返回原始文本（仅 - 和 context 行拼接）。
        用于恢复未接受时的原始状态。
        """
        result = []
        for ltype, text in self._lines:
            if ltype != _LineType.ADDED:
                result.append(text if text else "")
        return "\n".join(result).strip()
    
    def set_state(self, state: DiffState):
        """切换状态（支持撤销重选）。"""
        self._state = state
        self.update_appearance()
    
    def toggle_state(self):
        """在 pending ↔ accepted/rejected 间切换。"""
        if self._state == DiffState.PENDING:
            self.set_state(DiffState.ACCEPTED)
            self.accepted.emit(self._card_id)
        elif self._state == DiffState.ACCEPTED:
            self.set_state(DiffState.PENDING)
        elif self._state == DiffState.REJECTED:
            self.set_state(DiffState.PENDING)
    
    def update_appearance(self):
        """根据当前状态更新外观。"""
        c = self._colors
        state = self._state
        
        if state == DiffState.ACCEPTED:
            border_color = "#2E6DDE"
            bg = f"background-color:{c.get('surface', '#313244')};border-left:3px solid {border_color};"
        elif state == DiffState.REJECTED:
            border_color = "#D32F2F"
            bg = f"background-color:{c.get('surface', '#313244')};border-left:3px solid {border_color};opacity:0.65;"
        else:
            bg = f"background-color:{c.get('surface', '#313244')};border:1px solid {c.get('overlay', '#45475a')};border-radius:8px;"
        
        qss = f"QFrame#clawDiffCard{{{bg}}}"
        self.setStyleSheet(qss)
        
        # 更新按钮状态
        self._update_buttons()
    
    # ── 构建子部件 ──
    
    def _build_header(self) -> QFrame:
        """元数据行：图标 + 标题 [+N -M]"""
        f = QFrame(objectName="clawDiffHeader")
        hl = QHBoxLayout(f)
        hl.setContentsMargins(12, 8, 12, 6)
        hl.setSpacing(8)
        
        icon_lbl = QLabel("\u270f\ufe0f")
        icon_lbl.setObjectName("clawDiffIcon")
        icon_lbl.setFont(QFont("HarmonyOS Sans SC", 11))
        icon_lbl.setStyleSheet(f"color:{self._colors.get('accent', '#2E6DDE')};background:transparent;")
        
        title_lbl = QLabel(self._title)
        title_lbl.setObjectName("clawDiffTitle")
        title_lbl.setFont(QFont("HarmonyOS Sans SC", 10, QFont.Bold))
        title_lbl.setStyleSheet(f"color:{self._colors.get('text', '#cdd6f4')};background:transparent;")
        
        stat_lbl = QLabel(f"[+{self._additions} -{self._deletions}]")

        # 段落标签（新增）
        if self._paragraph_id:
            para_lbl = QLabel(f"\u00b6 {self._paragraph_id}")
            para_lbl.setObjectName("clawDiffPara")
            para_lbl.setFont(QFont("Consolas", 9))
            para_lbl.setStyleSheet(
                f"color:{self._colors.get('accent_blue', '#58A6FF')};"
                f"background:transparent;"
            )
            hl.addWidget(para_lbl)
        stat_lbl.setObjectName("clawDiffStat")
        stat_lbl.setFont(QFont("HarmonyOS Sans SC", 9))
        stat_lbl.setStyleSheet(f"color:{self._colors.get('subtext', '#585b70')};background:transparent;")
        
        hl.addWidget(icon_lbl)
        hl.addWidget(title_lbl, 1)
        hl.addWidget(stat_lbl)
        
        f.setStyleSheet(f"QFrame#clawDiffHeader{{background:transparent;}}")
        return f
    
    def _build_line(self, ltype: _LineType, text: str) -> QFrame:
        """单行 diff 内容。"""
        row = QFrame()
        row.setObjectName("clawDiffRow")
        
        lbl = QLabel(text)
        lbl.setObjectName("clawDiffLineText")
        lbl.setFont(QFont("Consolas, 'HarmonyOS Sans SC'", 9))
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl.setWordWrap(True)
        
        rl = QHBoxLayout(row)
        rl.setContentsMargins(6, 2, 6, 2)
        rl.setSpacing(4)
        
        # 前缀标签
        prefix = ""
        prefix_color = ""
        bg_color = ""
        
        if ltype == _LineType.DELETED:
            prefix = "-"
            prefix_color = "#FF6B6B"
            bg_color = "rgba(255,107,107,0.15)"
        elif ltype == _LineType.ADDED:
            prefix = "+"
            prefix_color = "#2EA043"
            bg_color = "rgba(46,160,67,0.15)"
        else:
            prefix = " "
            prefix_color = self._colors.get('muted', '#6c7086')
            bg_color = "transparent"
        
        pfx_lbl = QLabel(prefix)
        pfx_lbl.setFixedWidth(14)
        pfx_lbl.setFont(QFont("Consolas", 9, QFont.Bold))
        pfx_lbl.setStyleSheet(f"color:{prefix_color};background:transparent;")
        pfx_lbl.setAlignment(Qt.AlignTop)
        
        lbl.setStyleSheet(
            f"color:{self._colors.get('text', '#cdd6f4')};"
            f"background-color:{bg_color};"
            f"padding:2px 4px;"
            f"border-radius:3px;"
        )
        
        rl.addWidget(pfx_lbl)
        rl.addWidget(lbl, 1)
        
        row.setStyleSheet("QFrame#clawDiffRow{background:transparent;}")
        return row
    
    def _build_button_bar(self) -> QFrame:
        """底部操作按钮栏 — 使用颜色填充区分功能（无 emoji）。"""
        c = self._colors
        f = QFrame(objectName="clawDiffBtnBar")
        bl = QHBoxLayout(f)
        bl.setContentsMargins(10, 6, 10, 8)
        bl.setSpacing(8)

        _GREEN = "#2EA043"
        _RED = "#D32F2F"
        _DISABLED_BG = "#585b70"
        _DISABLED_FG = "#cdd6f4"

        btn_accept = QPushButton("接受")
        btn_accept.setObjectName("clawDiffBtnAccept")
        btn_accept.setCursor(Qt.PointingHandCursor)
        btn_accept.setFixedHeight(32)
        btn_accept.setStyleSheet(
            f"QPushButton#clawDiffBtnAccept{{"
            f"background:{_GREEN};color:#ffffff;border:none;border-radius:4px;"
            f"font-size:11px;font-weight:bold;padding:0 12px;"
            f"}}"
            f"QPushButton#clawDiffBtnAccept:hover{{background:#3FB950;}}"
            f"QPushButton#clawDiffBtnAccept:disabled{{background:{_DISABLED_BG};color:{_DISABLED_FG};}}"
        )
        btn_accept.clicked.connect(lambda: self._on_accept())

        btn_reject = QPushButton("拒绝")
        btn_reject.setObjectName("clawDiffBtnReject")
        btn_reject.setCursor(Qt.PointingHandCursor)
        btn_reject.setFixedHeight(32)
        btn_reject.setStyleSheet(
            f"QPushButton#clawDiffBtnReject{{"
            f"background:{_RED};color:#ffffff;border:none;border-radius:4px;"
            f"font-size:11px;font-weight:bold;padding:0 12px;"
            f"}}"
            f"QPushButton#clawDiffBtnReject:hover{{background:#F85149;}}"
            f"QPushButton#clawDiffBtnReject:disabled{{background:{_DISABLED_BG};color:{_DISABLED_FG};}}"
        )
        btn_reject.clicked.connect(lambda: self._on_reject())

        bl.addStretch()
        bl.addWidget(btn_accept)
        bl.addWidget(btn_reject)

        self._btn_accept = btn_accept
        self._btn_reject = btn_reject
        self._cached_green = _GREEN
        self._cached_red = _RED
        self._cached_disabled_bg = _DISABLED_BG
        self._cached_disabled_fg = _DISABLED_FG

        f.setStyleSheet("QFrame#clawDiffBtnBar{background:transparent;border-top:1px solid %s;}" %
                        c.get('overlay', '#45475a'))
        return f

    def _btn_qss(self, bg: str, hover: str, disabled: bool = False) -> str:
        """生成按钮 QSS。"""
        return (
            f"background:{bg};color:#ffffff;border:none;border-radius:4px;"
            f"font-size:11px;font-weight:bold;padding:0 12px;"
        )

    def _update_buttons(self):
        """根据状态更新按钮可用性和样式（通过 setStyleSheet 切换填充色）。"""
        state = self._state
        g, r = self._cached_green, self._cached_red
        dbg, dfg = self._cached_disabled_bg, self._cached_disabled_fg

        if state == DiffState.ACCEPTED:
            # 已接受 → 接受绿色填充+禁用，撤销灰底
            self._btn_accept.setEnabled(False)
            self._btn_accept.setText("已应用")
            self._btn_accept.setStyleSheet("QPushButton#clawDiffBtnAccept{background:%s;color:#ffffff;border:none;border-radius:4px;font-size:11px;font-weight:bold;padding:0 12px;}QPushButton#clawDiffBtnAccept:disabled{background:%s;color:%s;}" % (g, dbg, dfg))

            self._btn_reject.setEnabled(True)
            self._btn_reject.setText("撤销")
            self._btn_reject.setStyleSheet("QPushButton#clawDiffBtnReject{background:%s;color:#ffffff;border:none;border-radius:4px;font-size:11px;font-weight:bold;padding:0 12px;}QPushButton#clawDiffBtnReject:hover{background:#F85149;}QPushButton#clawDiffBtnReject:disabled{background:%s;color:%s;}" % (dbg, dbg, dfg))

        elif state == DiffState.REJECTED:
            # 已拒绝 → 重新接受绿色填充，拒绝红色填充+禁用
            self._btn_accept.setEnabled(True)
            self._btn_accept.setText("重新接受")
            self._btn_accept.setStyleSheet("QPushButton#clawDiffBtnAccept{background:%s;color:#ffffff;border:none;border-radius:4px;font-size:11px;font-weight:bold;padding:0 12px;}QPushButton#clawDiffBtnAccept:hover{background:#3FB950;}QPushButton#clawDiffBtnAccept:disabled{background:%s;color:%s;}" % (g, dbg, dfg))

            self._btn_reject.setEnabled(False)
            self._btn_reject.setText("已忽略")
            self._btn_reject.setStyleSheet("QPushButton#clawDiffBtnReject{background:%s;color:#ffffff;border:none;border-radius:4px;font-size:11px;font-weight:bold;padding:0 12px;}QPushButton#clawDiffBtnReject:disabled{background:%s;color:%s;}" % (r, dbg, dfg))

        else:
            # 待定 → 两色正常显示
            self._btn_accept.setEnabled(True)
            self._btn_accept.setText("接受")
            self._btn_accept.setStyleSheet("QPushButton#clawDiffBtnAccept{background:%s;color:#ffffff;border:none;border-radius:4px;font-size:11px;font-weight:bold;padding:0 12px;}QPushButton#clawDiffBtnAccept:hover{background:#3FB950;}QPushButton#clawDiffBtnAccept:disabled{background:%s;color:%s;}" % (g, dbg, dfg))

            self._btn_reject.setEnabled(True)
            self._btn_reject.setText("拒绝")
            self._btn_reject.setStyleSheet("QPushButton#clawDiffBtnReject{background:%s;color:#ffffff;border:none;border-radius:4px;font-size:11px;font-weight:bold;padding:0 12px;}QPushButton#clawDiffBtnReject:hover{background:#F85149;}QPushButton#clawDiffBtnReject:disabled{background:%s;color:%s;}" % (r, dbg, dfg))
    
    def _on_accept(self):
        """处理接受操作。"""
        self.set_state(DiffState.ACCEPTED)
        self.accepted.emit(self._card_id)
        # 无段落 ID 时发出警告（安全写入模式时由 main.py 捕获）
        if not self._paragraph_id:
            self.no_paragraph_warning.emit(self._card_id)
    
    def _on_reject(self):
        """处理拒绝操作（在已接受状态下为撤销）。"""
        if self._state == DiffState.ACCEPTED:
            self.set_state(DiffState.PENDING)
        elif self._state == DiffState.PENDING:
            self.set_state(DiffState.REJECTED)
        self.rejected.emit(self._card_id)
    
    def _scroll_qss(self) -> str:
        """滚动区 QSS。"""
        c = self._colors
        return (
            f"QScrollArea#clawDiffScroll{{background:transparent;border:none;}}"
            f"QScrollArea#clawDiffScroll > QWidget > QWidget{{background:transparent;}}"
            f"QScrollBar:vertical{{background:transparent;width:4px;margin:0;}}"
            f"QScrollBar::handle:vertical{{background:{c.get('muted','#6c7086')};border-radius:2px;min-height:20px;}}"
            f"QScrollBar::handle:vertical:hover{{background:{c.get('subtext','#585b70')};}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}"
        )

    def resizeEvent(self, event):
        """宽度变化时通知布局更新。"""
        super().resizeEvent(event)
        self.updateGeometry()
