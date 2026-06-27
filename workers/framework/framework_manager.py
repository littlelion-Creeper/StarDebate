# -*- coding: utf-8 -*-
"""辩论框架管理器 — UI 构建 + 数据持久化 + AI 框架生成调度

负责：
  - 框架画布页面的 UI 构建（toolbar + 节点按钮 + 画布）
  - 框架数据的加载/保存/修复/清空
  - AI 框架生成的触发、回调处理与自动布局
  - 状态栏消息的统一输出
"""

import os
import json

from PyQt5.QtWidgets import (
    QUndoStack,
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QDialog, QListWidget, QStackedWidget,
)
from PyQt5.QtCore import Qt, QTimer, QRect, QSize
from PyQt5.QtGui import QFont, QFontMetrics

from . import FRAMEWORK_NODE_TYPES, get_node_type_color
from .framework_worker import AIFrameworkWorker
from .framework_widgets import FrameworkCanvas
from components.popup_dialog import CustomDialog
from components.star_button import StarButton


class FrameworkManager:
    """辩论框架全生命周期管理器"""

    def __init__(self, mw):
        """mw: StarDebateWindow 主窗口实例"""
        self._mw = mw
        self._data: list[dict] = []        # 框架节点数据
        self._next_id: int = 1             # 节点自增 ID
        self._canvas: FrameworkCanvas | None = None  # 框架画布
        self._page: QWidget | None = None  # 框架页面容器
        self._page_index: int = -1         # centre_stack 中的页面索引

        # ── 撤销栈 ──────────────────────────────────────
        self._undo_stack = QUndoStack()
        from components.undo_coordinator import UndoCoordinator
        UndoCoordinator.instance().register_stack("framework", self._undo_stack)

    # ── 属性访问（供主窗口兼容）──

    @property
    def canvas(self) -> FrameworkCanvas | None:
        return self._canvas

    @property
    def data(self) -> list:
        return self._data

    @property
    def next_id(self) -> int:
        return self._next_id

    # ── 状态栏代理 ──

    def update_status(self, msg: str):
        """委托主窗口更新状态栏"""
        try:
            self._mw._update_status(msg)
        except RuntimeError:
            pass

    # ── 文件路径辅助 ──

    def _get_save_path(self) -> str | None:
        """获取框架保存路径（存入正方一辩稿文件）"""
        try:
            return self._mw._structure_mgr._get_speech_filename("pro")
        except RuntimeError:
            return None

    # ════════════════════════════════════════════
    #  UI 构建
    # ════════════════════════════════════════════

    def build_ui(self):
        """构建框架页面并添加到 centre_stack，返回页面索引"""
        page = QWidget()
        page.setObjectName("frameworkPage")
        layout = QVBoxLayout(page)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        # ── 顶部工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        btn_back = StarButton("← 返回辩论详情", ratio_h=0.85)
        btn_back.clicked.connect(lambda: self._mw.centre_stack.setCurrentIndex(1))

        toolbar.addWidget(btn_back)
        toolbar.addStretch()

        # ── 画布 ──
        self._canvas = FrameworkCanvas(self)

        # ── 侧边工具栏 ──
        side_tools = QHBoxLayout()
        side_tools.setSpacing(6)
        lbl_hint = QLabel("添加节点:")
        lbl_hint.setObjectName("frameworkHint")
        lbl_hint.setFont(QFont("Microsoft YaHei", 15))
        side_tools.addWidget(lbl_hint)

        for ntype, (label, _) in FRAMEWORK_NODE_TYPES.items():
            btn = QPushButton(label)
            btn.setObjectName("smallBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(32)
            btn.setStyleSheet(
                f"#smallBtn {{ border-left: 3px solid {get_node_type_color(ntype)}; }}"
            )
            btn.clicked.connect(lambda checked, t=ntype: self._canvas._add_root_node(t))
            side_tools.addWidget(btn)

        side_tools.addStretch()
        btn_adjust = StarButton("自动调整")
        btn_adjust.setObjectName("smallBtn")
        btn_adjust.setToolTip("根据文字自动调整节点大小并智能排列位置")
        btn_adjust.clicked.connect(self._canvas.auto_adjust_layout)
        side_tools.addWidget(btn_adjust)

        btn_clear = StarButton("清空")
        btn_clear.setObjectName("smallBtn")
        btn_clear.clicked.connect(self.clear_framework)
        side_tools.addWidget(btn_clear)

        # ── 组装 ──
        layout.addLayout(toolbar)
        layout.addLayout(side_tools)
        layout.addWidget(self._canvas, stretch=1)

        self._page = page
        self._page_index = self._mw.centre_stack.count()
        self._mw.centre_stack.addWidget(page)

        return self._page_index

    # ════════════════════════════════════════════
    #  数据管理
    # ════════════════════════════════════════════

    def open_framework(self):
        """打开框架页面并加载数据"""
        if not self._mw.current_debate_path:
            CustomDialog.warning(self._mw, "提示", "请先在左侧树控件中选择一个辩论文件。")
            return
        self.load_data()
        self._canvas.set_data(self._data, self._next_id)
        self._mw.centre_stack.setCurrentIndex(self._page_index)

    def save_data(self):
        """将框架数据保存到一辩稿 JSON 文件中"""
        filepath = self._get_save_path()
        if not filepath:
            return
        try:
            data = {}
            if os.path.isfile(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            # 同步 canvas 中的节点数据（保存前计算相对偏移量）
            try:
                if self._canvas and self._canvas._data is not None:
                    self._canvas._compute_and_store_offsets()
                    self._data = self._canvas._data
                    self._next_id = self._canvas._next_id
            except RuntimeError:
                return  # 画布已销毁，不保存
            data["framework"] = {
                "nodes": self._data,
                "next_id": self._next_id
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except (OSError, json.JSONDecodeError) as e:
            self.update_status(f"保存框架失败: {str(e)}")

    def load_stardebate_data(self, data: list):
        """从 .stardebate 文件加载框架数据到画布。

        Args:
            data: 框架节点列表 [{"id": 1, "text": "...", ...}]
        """
        if not isinstance(data, list):
            return
        self._data = data
        self._next_id = max((n.get("id", 0) for n in data), default=0) + 1 if data else 1
        if self._canvas:
            self._canvas.rebuild_from_data(self._data)
        self._mw.centre_stack.setCurrentIndex(self._page_index if self._page_index >= 0 else 8)

    def load_data(self):
        """从一辩稿 JSON 文件中加载框架数据"""
        filepath = self._get_save_path()
        if filepath and os.path.isfile(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                fw = data.get("framework", {})
                self._data = fw.get("nodes", [])
                self._next_id = fw.get("next_id", 1)
                if not self._data:
                    self._next_id = 1
                else:
                    self._next_id = max(
                        n["id"] for n in self._data) + 1 if self._data else 1
                # 修复可能存在的循环引用
                try:
                    self.repair_cycles()
                except Exception:
                    pass
            except (json.JSONDecodeError, OSError):
                self._data = []
                self._next_id = 1
        else:
            self._data = []
            self._next_id = 1

    def repair_cycles(self):
        """检测并修复框架数据中的循环引用"""
        if not self._data:
            return
        node_map = {n["id"]: n for n in self._data}
        repaired = False

        def _is_reachable(from_id, to_id, visited=None):
            if visited is None:
                visited = set()
            if from_id in visited:
                return False
            visited.add(from_id)
            node = node_map.get(from_id)
            if node:
                for child_id in node.get("children", []):
                    if child_id == to_id:
                        return True
                    if _is_reachable(child_id, to_id, visited):
                        return True
            return False

        for node in self._data:
            children = node.get("children", [])
            if not children:
                continue
            safe_children = []
            for child_id in children:
                if child_id == node["id"]:
                    repaired = True
                    continue
                if _is_reachable(child_id, node["id"]):
                    repaired = True
                    continue
                safe_children.append(child_id)
            if len(safe_children) != len(children):
                node["children"] = safe_children

        if repaired:
            self.update_status("⚠️ 框架数据中存在循环引用，已自动修复")

    def clear_framework(self):
        """清空框架"""
        self._data = []
        self._next_id = 1
        self._canvas.set_data([], 1)
        self.save_data()
        self.update_status("框架已清空")

    # ════════════════════════════════════════════
    #  AI 框架生成
    # ════════════════════════════════════════════

    def start_ai_framework(self):
        """触发 AI 框架生成：选择正方或反方一辩稿，让 AI 提取辩论框架"""
        pro_speech = self._mw.edit_pro_speech.toPlainText().strip()
        con_speech = self._mw.edit_con_speech.toPlainText().strip()

        if not pro_speech and not con_speech:
            CustomDialog.warning(self._mw, "提示", "正方和反方一辩稿均为空，请先编辑一辩稿内容。")
            return

        # 选择辩方
        items = []
        if pro_speech:
            items.append(("pro", "🟢 正方一辩稿", pro_speech[:60] + ("…" if len(pro_speech) > 60 else "")))
        if con_speech:
            items.append(("con", "🔴 反方一辩稿", con_speech[:60] + ("…" if len(con_speech) > 60 else "")))

        if not items:
            return

        # 自定义对话框
        dlg = QDialog(self._mw)
        dlg.setWindowTitle("AI 框架生成")

        fm = QFontMetrics(QFont("Microsoft YaHei", 11))
        fm_title = QFontMetrics(QFont("Microsoft YaHei", 12))
        margin = 16 * 2
        btn_w = 80 * 2 + 8

        label_w = fm_title.horizontalAdvance("选择要基于哪方一辩稿来生成辩论框架：") + margin + 24
        max_item_w = 0
        item_heights = []
        list_w = 480
        for _, label, preview in items:
            w1 = fm.horizontalAdvance("{}".format(label)) + 24
            w2 = min(fm.horizontalAdvance("{}".format(preview)), list_w - 24) + 24
            max_item_w = max(max_item_w, w1, w2)
            full_text = "{}\n{}".format(label, preview)
            rect = fm.boundingRect(QRect(0, 0, list_w - 24, 1000),
                                   Qt.AlignLeft | Qt.TextWordWrap, full_text)
            item_heights.append(rect.height() + 16)

        calc_w = max(label_w, max_item_w + margin, btn_w + margin) + 30
        win_w = max(400, min(calc_w, 750))

        total_item_h = sum(item_heights)
        win_h = fm_title.height() + 12 + total_item_h + 40 + 16 * 2 + 12 * 3
        win_h = max(180, min(win_h, 500))

        dlg.setObjectName("aiFrameworkDialog")
        dlg.setFixedSize(win_w, win_h)
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(16, 16, 16, 16)
        dlg_layout.setSpacing(12)

        lbl = QLabel("选择要基于哪方一辩稿来生成辩论框架：")
        lbl.setFont(QFont("Microsoft YaHei", 12))
        dlg_layout.addWidget(lbl)

        lst = QListWidget()
        lst.setFont(QFont("Microsoft YaHei", 11))
        lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lst.setStyleSheet("")  # 样式由 QSS 控制
        for side, label, preview in items:
            item_text = "{}\n{}".format(label, preview)
            lst.addItem(item_text)
        lst.setCurrentRow(0)
        lst.setWordWrap(True)
        dlg_layout.addWidget(lst)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("btnCancelFramework")
        btn_cancel.setFixedSize(80, 32)
        btn_cancel.clicked.connect(dlg.reject)

        btn_ok = QPushButton("确定")
        btn_ok.setObjectName("btnOkFramework")
        btn_ok.setFixedSize(80, 32)
        btn_ok.clicked.connect(dlg.accept)
        lst.itemDoubleClicked.connect(dlg.accept)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        dlg_layout.addLayout(btn_layout)

        if dlg.exec() != QDialog.Accepted:
            return

        selected_row = lst.currentRow()
        if selected_row < 0 or selected_row >= len(items):
            return

        side = items[selected_row][0]
        speech_text = pro_speech if side == "pro" else con_speech

        # API 配置
        api_config = self._mw._load_api_config()
        if not api_config.get("api_key"):
            CustomDialog.warning(
                self._mw, "缺少 API Key",
                "请在 api_config.json 中填写您的 DeepSeek API Key 后再使用 AI 框架功能。"
            )
            return

        # 辩论标题
        debate_title = ""
        if self._mw.current_debate_data:
            pro = self._mw.current_debate_data.get("pro", "")
            con = self._mw.current_debate_data.get("con", "")
            debate_title = "{} vs {}".format(pro, con)

        side_label = "正方" if side == "pro" else "反方"

        result = CustomDialog.question(
            self._mw, "确认 AI 框架生成",
            "将基于【{}】一辩稿自动提取辩论框架。\n\n"
            "一辩稿预览：\n{}\n\n是否开始？".format(
                side_label, speech_text[:200] + ("…" if len(speech_text) > 200 else "")
            ),
            buttons=[("否", "no"), ("是", "yes")]
        )
        if result != "yes":
            return

        # 显示加载条
        self._mw._ai_loading_bar.show_loading("AI正在生成辩论框架…")

        # 安全定时器
        safety_timer = QTimer(self._mw)
        safety_timer.setSingleShot(True)
        safety_timer.timeout.connect(self._safety_close)
        safety_timer.start(95000)

        # 启动异步线程
        self._ai_worker = AIFrameworkWorker(
            api_config, speech_text, side, debate_title
        )
        self._ai_worker.finished.connect(self._on_ai_finished)
        self._ai_worker.start()
        self.update_status("AI框架生成进行中: {}…".format(side_label))

    def _safety_close(self):
        """安全关闭加载条（防止信号丢失导致无法关闭）"""
        self._mw._ai_loading_bar.hide_loading()
        self.update_status("AI框架生成超时或异常，已取消")

    def _on_ai_finished(self, success: bool, error_msg: str, result_text: str):
        """AI框架生成完成回调"""
        self._mw._ai_loading_bar.hide_loading()

        if not success:
            self.update_status("AI框架生成失败: {}".format(error_msg))
            CustomDialog.error(self._mw, "AI 框架生成失败", error_msg)
            return

        # 解析 JSON 结果
        try:
            json_text = result_text.strip()
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0].strip()
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0].strip()

            data, parse_err = self._mw._robust_json_parse(json_text)
            if data is None:
                raise ValueError(parse_err or "无法解析 AI 返回的 JSON 格式")

            nodes = data.get("nodes", [])
            if not nodes:
                raise ValueError("AI返回的框架节点列表为空")

            # 自动布局并转换为框架数据格式
            framework_nodes = self._auto_layout(nodes)

            # 更新框架数据
            self._data = framework_nodes
            max_id = max(n["id"] for n in framework_nodes) if framework_nodes else 0
            self._next_id = max_id + 1

            # 加载到框架画布
            if self._canvas:
                self._canvas.set_data(self._data, self._next_id)
            self.save_data()

            # 自动跳转到框架页面
            self.open_framework()

            self.update_status(
                "AI框架生成完成，共 {} 个节点".format(len(framework_nodes))
            )
            CustomDialog.information(
                self._mw, "AI 框架生成完成",
                "已成功从一辩稿提取辩论框架，共 {} 个节点。\n"
                "框架已自动布局并加载到框架画布中。".format(len(framework_nodes))
            )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            self.update_status("解析AI框架返回失败")
            raw_preview = result_text[:500] + ("…" if len(result_text) > 500 else "")
            CustomDialog.warning(
                self._mw, "JSON 解析失败",
                "AI 返回的内容无法解析为 JSON。\n错误：{}\n\n"
                "返回内容预览（前500字）：\n{}".format(e, raw_preview)
            )

    def _auto_layout(self, ai_nodes: list) -> list:
        """将 AI 返回的节点列表自动布局为框架画布可用的格式"""
        node_map = {nd["id"]: nd for nd in ai_nodes}

        START_X = 80
        GAP_X = 200
        GAP_Y = 68
        NODE_W = 160
        NODE_H = 52

        def assign_level(node_id, visited=None):
            if visited is None:
                visited = set()
            if node_id in visited:
                return 0
            visited.add(node_id)
            for nd in ai_nodes:
                if node_id in nd.get("children", []):
                    return assign_level(nd["id"], visited) + 1
            return 0

        levels = {}
        for nd in ai_nodes:
            levels[nd["id"]] = assign_level(nd["id"])

        level_groups = {}
        for nd in ai_nodes:
            lv = levels[nd["id"]]
            if lv not in level_groups:
                level_groups[lv] = []
            level_groups[lv].append(nd)

        type_order = {"position": 0, "definition": 1, "criterion": 2,
                      "value": 3, "argument": 4, "evidence": 5}
        for lv in level_groups:
            level_groups[lv].sort(key=lambda nd: type_order.get(nd.get("node_type", ""), 99))

        result = []
        START_Y = 60
        for lv in sorted(level_groups.keys()):
            nodes_at_level = level_groups[lv]
            for i, nd in enumerate(nodes_at_level):
                x = START_X + lv * GAP_X
                y = START_Y + i * GAP_Y
                node = {
                    "id": nd["id"],
                    "node_type": nd.get("node_type", "argument"),
                    "text": nd.get("text", ""),
                    "x": x,
                    "y": y,
                    "width": NODE_W,
                    "height": NODE_H,
                    "children": [c for c in nd.get("children", []) if c in node_map],
                }
                result.append(node)

        return result
