# -*- coding: utf-8 -*-
"""
辩论论据库插件
==============
演示如何使用 register_training_sub_feature API 在模拟训练面板中注册自定义子功能。

功能：
- 在「模拟训练」入口页显示一张「辩论论据库」卡片
- 点击后进入论据浏览页面，展示常见辩题论点模板
- 训练面板标题栏自动生成「📂 论据」历史按钮

使用方法：
  导入插件后，打开「模拟训练」面板即可看到「辩论论据库」入口卡片。
"""

import json
import os
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QScrollArea, QFrame,
)

from components.popup_dialog import CustomDialog

from workers.plugin_manager import get_api

# ── 插件 ID ──
PLUGIN_ID = "debate_argument_bank"
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

# ── 论据模板数据 ──
ARGUMENT_TEMPLATES = [
    {
        "category": "定义与标准",
        "color": "#2E6DDE",
        "items": [
            {
                "title": "概念界定法",
                "content": "在辩论开始前，先明确核心概念的定义边界。\n"
                           "例如：「公平」在本辩题中应理解为机会公平而非结果公平。\n"
                           "公式：X 在本辩题中的核心含义是 Y，而非 Z。",
            },
            {
                "title": "标准前置法",
                "content": "先确立判断标准，再用标准衡量双方观点。\n"
                           "例如：判断一个政策是否合理，核心标准有三：可行性、效率、公平性。\n"
                           "技巧：标准要可量化、有逻辑、对方难以反驳。",
            },
        ],
    },
    {
        "category": "论证结构",
        "color": "#a6e3a1",
        "items": [
            {
                "title": "ARE 结构",
                "content": "Assertion（断言）→ Reasoning（理由）→ Evidence（证据）\n"
                           "示例：短视频对青少年有害（断言），\n"
                           "因为其碎片化内容破坏深度思考能力（理由），\n"
                           "研究表明每天刷短视频2小时以上者专注力下降40%（证据）。",
            },
            {
                "title": "利弊比较法",
                "content": "当一个方案有利有弊时，不否认弊端，而是论证利大于弊。\n"
                           "结构：\n"
                           "1. 承认弊端 X 的存在\n"
                           "2. 论证利端 Y 在重要性/紧迫性上远超 X\n"
                           "3. 提出弥补弊端 X 的配套措施",
            },
            {
                "title": "三段论结构",
                "content": "大前提（普遍规律）→ 小前提（具体事实）→ 结论\n"
                           "示例：\n"
                           "大前提：一切限制自由的政策都需充分论证必要性\n"
                           "小前提：该政策限制了公民的选择自由\n"
                           "结论：该政策的支持者需承担更重的论证责任",
            },
        ],
    },
    {
        "category": "反驳策略",
        "color": "#f38ba8",
        "items": [
            {
                "title": "基石拆除法",
                "content": "找到对方论证中最核心的前提假设，直接攻击。\n"
                           "如果该前提不成立，对方整个论证大厦就会倒塌。\n"
                           "话术：「对方整个立论建立在 X 这个假设上，但事实上…」",
            },
            {
                "title": "归谬法",
                "content": "将对方逻辑推至极端，指出其荒谬后果。\n"
                           "结构：「如果按对方逻辑，那么…也会成立，但这显然是荒谬的。\n"
                           "因此对方的推理过程存在缺陷。」",
            },
            {
                "title": "两面分析法",
                "content": "对方提出的论据，换个角度反而支持己方。\n"
                           "示例：「对方说科技发展提高了效率，\n"
                           "但这恰恰说明我们需要更多教育投入来适应这种变化。」",
            },
        ],
    },
    {
        "category": "总结陈词",
        "color": "#f9e2af",
        "items": [
            {
                "title": "战场收敛法",
                "content": "在辩论尾声，梳理双方核心争议点，逐条总结己方优势。\n"
                           "结构：\n"
                           "1. 今天我们讨论了 X、Y、Z 三个核心问题\n"
                           "2. 在每个问题上，我方的论证优于对方\n"
                           "3. 因此，我们应支持我方立场",
            },
            {
                "title": "价值升华法",
                "content": "将具体辩题提升到更高的价值观层面。\n"
                           "示例：「这不仅是一个技术问题，更是一个关于我们\n"
                           "想建设怎样社会的问题。」\n"
                           "关键：升华要有逻辑关联，不能生硬拔高。",
            },
        ],
    },
]

# ── 历史记录存储路径 ──
HISTORY_FILE = os.path.join(PLUGIN_DIR, "notes_history.json")


def _load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_history(notes: list):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ============================================================
#  Training Sub-feature Manager
# ============================================================

class ArgumentBankManager:
    """辩论论据库 — 训练子功能管理器

    必须实现：
      - __init__(self, train_mgr): 接收 TrainingManager 实例
      - build_pages(self, parent_stack) -> int: 构建子页面

    可选实现:
      - show_history(self): 点击标题栏历史按钮时调用
    """

    def __init__(self, train_mgr):
        """train_mgr 是 TrainingManager 实例，可访问：
        - train_mgr._mw          → 主窗口
        - train_mgr._train_stack → 训练面板的 QStackedWidget
        - train_mgr._lbl_train_title / _lbl_train_status → 标题栏控件
        """
        self._tm = train_mgr
        self._mw = train_mgr._mw
        self._notes: list = _load_history()

    def build_pages(self, parent_stack: QStackedWidget) -> int:
        """在训练面板中构建子页面。

        Args:
            parent_stack: 训练面板的 QStackedWidget

        Returns:
            首个页面在 stack 中的索引
        """
        start_idx = parent_stack.count()

        # 页 0：论据浏览首页
        self._build_browse_page(parent_stack)

        # 页 1：笔记页（用于 show_history）
        self._build_notes_page(parent_stack)

        return start_idx

    # ── 浏览页 ──

    def _build_browse_page(self, stack: QStackedWidget):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # 标题
        lbl_title = QLabel("📚 辩论论据库")
        lbl_title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        lbl_title.setStyleSheet("color: #2E6DDE;")
        layout.addWidget(lbl_title)

        lbl_hint = QLabel("点击下方卡片查看论据模板，可在每个模板下记录自己的心得")
        lbl_hint.setFont(QFont("Microsoft YaHei", 9))
        lbl_hint.setStyleSheet("color: #a6adc8; padding: 2px 0;")
        lbl_hint.setWordWrap(True)
        layout.addWidget(lbl_hint)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(10)

        for category in ARGUMENT_TEMPLATES:
            # 分类标题
            cat_lbl = QLabel(category["category"])
            cat_lbl.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
            cat_lbl.setStyleSheet(f"color: {category['color']}; padding: 4px 0;")
            content_layout.addWidget(cat_lbl)

            # 分类下的论据卡片
            for item in category["items"]:
                card = self._create_argument_card(item, category["color"])
                content_layout.addWidget(card)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, stretch=1)

        # 返回按钮
        btn_back = QPushButton("← 返回训练首页")
        btn_back.setObjectName("smallBtn")
        btn_back.setCursor(Qt.PointingHandCursor)
        btn_back.setFixedHeight(32)
        btn_back.clicked.connect(lambda: self._tm._train_stack.setCurrentIndex(0))
        layout.addWidget(btn_back)

        stack.addWidget(page)

    def _create_argument_card(self, item: dict, accent: str) -> QFrame:
        card = QFrame()
        card.setObjectName("exerciseScoreBlock")
        card.setCursor(Qt.PointingHandCursor)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(6)

        # 标题行
        title_row = QHBoxLayout()
        lbl_title = QLabel(f"📌 {item['title']}")
        lbl_title.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        lbl_title.setStyleSheet(f"color: {accent}; background: transparent;")
        title_row.addWidget(lbl_title)
        title_row.addStretch()

        btn_note = QPushButton("📝 记笔记")
        btn_note.setObjectName("smallBtn")
        btn_note.setCursor(Qt.PointingHandCursor)
        btn_note.setFixedHeight(26)
        # 使用默认参数捕获当前 item
        btn_note.clicked.connect(
            lambda checked, it=item: self._on_add_note(it)
        )
        title_row.addWidget(btn_note)
        card_layout.addLayout(title_row)

        # 内容
        lbl_content = QLabel(item["content"])
        lbl_content.setFont(QFont("Microsoft YaHei", 9))
        lbl_content.setStyleSheet(
            "color: #bac2de; background: transparent; line-height: 1.6;"
        )
        lbl_content.setWordWrap(True)
        card_layout.addWidget(lbl_content)

        return card

    def _on_add_note(self, item: dict):
        """记笔记 — 弹出一个简单对话框"""
        from PyQt5.QtWidgets import QInputDialog

        title = item["title"]
        text, ok = QInputDialog.getMultiLineText(
            self._mw, f"记笔记 — {title}",
            f"关于「{title}」的笔记:",
            ""
        )
        if ok and text.strip():
            note = {
                "template_title": title,
                "content": text.strip(),
                "date": datetime.now().isoformat(),
            }
            self._notes.insert(0, note)
            # 最多保留 50 条
            if len(self._notes) > 50:
                self._notes = self._notes[:50]
            _save_history(self._notes)
            api = get_api()
            if api:
                api.update_status(f"已保存「{title}」笔记")

    # ── 笔记页（历史记录）──

    def _build_notes_page(self, stack: QStackedWidget):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        lbl_title = QLabel("📂 论据笔记")
        lbl_title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        lbl_title.setStyleSheet("color: #cdd6f4;")
        layout.addWidget(lbl_title)

        self._notes_scroll = QScrollArea()
        self._notes_scroll.setWidgetResizable(True)
        self._notes_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        self._notes_container = QWidget()
        self._notes_container.setStyleSheet("background: transparent;")
        self._notes_layout = QVBoxLayout(self._notes_container)
        self._notes_layout.setSpacing(4)
        self._notes_layout.addStretch()
        self._notes_scroll.setWidget(self._notes_container)
        layout.addWidget(self._notes_scroll, stretch=1)

        btn_back = QPushButton("← 返回训练首页")
        btn_back.setObjectName("smallBtn")
        btn_back.setCursor(Qt.PointingHandCursor)
        btn_back.setFixedHeight(32)
        btn_back.clicked.connect(lambda: self._tm._train_stack.setCurrentIndex(0))
        layout.addWidget(btn_back)

        # 清除按钮
        btn_clear = QPushButton("清空笔记")
        btn_clear.setObjectName("smallBtn")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setFixedHeight(32)
        btn_clear.clicked.connect(self._on_clear_notes)
        layout.addWidget(btn_clear)

        stack.addWidget(page)

    def show_history(self):
        """点击标题栏「📂 笔记」按钮时调用"""
        self._refresh_notes_list()
        # 跳转到笔记页（子功能第 2 页 = start_idx + 1）
        from workers.training import get_sub_feature
        feature = get_sub_feature(f"plugin_{PLUGIN_ID}_arg_bank")
        if feature:
            # 通过 _sub_page_map 获取起始索引
            mgr = self._tm._sub_managers.get(f"plugin_{PLUGIN_ID}_arg_bank")
            if mgr:
                start_idx, _ = self._tm._sub_page_map.get(
                    f"plugin_{PLUGIN_ID}_arg_bank", (0, 0)
                )
                if start_idx > 0:
                    self._tm._train_stack.setCurrentIndex(start_idx + 1)

    def _refresh_notes_list(self):
        self._notes = _load_history()
        # 清空现有卡片
        while self._notes_layout.count() > 1:
            item = self._notes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._notes:
            lbl = QLabel("暂无笔记，点击论据卡片上的「📝 记笔记」开始记录")
            lbl.setFont(QFont("Microsoft YaHei", 10))
            lbl.setStyleSheet("color: #6c7086; padding: 20px;")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setWordWrap(True)
            self._notes_layout.insertWidget(0, lbl)
            return

        for note in self._notes:
            date_str = note.get("date", "")[:16].replace("T", " ")
            title = note.get("template_title", "")
            content = note.get("content", "")[:200]

            card = QFrame()
            card.setStyleSheet(
                "QFrame { background-color: #181825; border-radius: 8px; "
                "padding: 8px 12px; }"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 6, 8, 6)
            card_layout.setSpacing(4)

            header = QLabel(f"📌 {title}  ·  {date_str}")
            header.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
            header.setStyleSheet("color: #2E6DDE; background: transparent;")
            card_layout.addWidget(header)

            lbl_content = QLabel(content)
            lbl_content.setFont(QFont("Microsoft YaHei", 9))
            lbl_content.setStyleSheet("color: #bac2de; background: transparent;")
            lbl_content.setWordWrap(True)
            card_layout.addWidget(lbl_content)

            self._notes_layout.insertWidget(
                self._notes_layout.count() - 1, card
            )

    def _on_clear_notes(self):
        result = CustomDialog.question(
            self._mw, "确认清空", "确定要清空所有论据笔记吗？",
            buttons=[("否", "no"), ("是", "yes")])
        if result == "yes":
            self._notes.clear()
            _save_history(self._notes)
            self._refresh_notes_list()
            api = get_api()
            if api:
                api.update_status("论据笔记已清空")


# ============================================================
#  插件生命周期
# ============================================================

def on_enable():
    """插件启用时：注册训练子功能"""
    api = get_api()

    # ★ 核心：调用 register_training_sub_feature 注册子功能 ★
    success = api.register_training_sub_feature(
        # 子功能元信息
        {
            "id": "arg_bank",                      # 唯一标识
            "name": "辩论论据库",                    # 入口卡片标题
            "icon": "📚",                          # 卡片图标
            "accent_color": "#2E6DDE",              # 标题颜色
            "description": "常见辩题论点模板·论证结构·反驳策略",
            "tags": ["论据模板", "论证结构", "反驳策略"],
            "order": 100,                           # 排序在内置功能后
            "history_label": "📂 笔记",             # 标题栏历史按钮
        },
        # 管理器类
        ArgumentBankManager,
    )

    if success:
        api.update_status("辩论论据库已就绪！打开「模拟训练」面板查看")
    else:
        api.update_status("辩论论据库注册失败")


def on_disable():
    """插件禁用时：系统自动清理训练子功能，无需手动处理"""
    api = get_api()
    api.update_status("辩论论据库已停止")
