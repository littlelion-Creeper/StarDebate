"""结构树管理器 - 负责一辩稿结构树的 UI 搭建、数据管理和 AI 分析调度"""
import json
import os
import re
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTreeWidget, QTreeWidgetItem, QMenu, QInputDialog, QDialog, QLineEdit,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QCursor

from components.title_bar import TitleBar
from components.star_button import StarButton

from components.popup_dialog import CustomDialog
from components.theme_colors import tc

from .structure_worker import StructureAnalysisWorker


# ── 名称 → slug 转换 ──

_COMMON_SLUG_MAP = {
    "开场引入": "opening",
    "开篇立论": "opening",
    "定义阐释": "definition",
    "概念界定": "definition",
    "论点展开": "arguments",
    "论证结构": "argument_structure",
    "核心论证": "core_argument",
    "价值升华": "value_judgment",
    "价值层面": "value_judgment",
    "总结陈词": "closing",
    "结语": "closing",
}


def _name_to_slug(name: str) -> str:
    """将中文章节名转换为英文 slug。

    优先查表，无匹配时按规则生成（去空格/标点 → 小写 → 下划线连接）。
    """
    trimmed = name.strip()
    if not trimmed:
        return "unnamed"
    # 常用映射
    slug = _COMMON_SLUG_MAP.get(trimmed)
    if slug:
        return slug
    # 自动生成：保留字母数字和中文拼音首字母，或简单 transliterate
    import re as _re
    cleaned = _re.sub(r'[^\w\u4e00-\u9fff]', '_', trimmed)
    cleaned = _re.sub(r'_+', '_', cleaned).strip('_')
    if not cleaned:
        return "unnamed"
    return cleaned.lower()


class StructureTreeManager(QFrame):
    """结构树管理面板，包含结构树的 UI 和全部操作逻辑
    
    管理正方/反方两套独立的章节树数据，每套数据格式：
    [
        {
            "name": "章节名",
            "keywords": [{"word": "..."}, ...],
            "children": [...]  # 子章节，同格式
        }
    ]
    """

    # 信号：当结构树数据变更时发出（用于主窗口同步状态栏等）
    structure_changed = pyqtSignal(str)  # 参数: 变更描述文本

    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_window = parent  # 主窗口引用（StarDebateWindow）

        # ---- 数据结构 ----
        self._structure_data_pro: list = []
        self._structure_data_con: list = []
        self._struct_side: str = "pro"  # 当前显示侧
        self._visible: bool = True

        # ---- AI 分析线程 ----
        self._struct_worker: StructureAnalysisWorker | None = None

        # ---- UI 组件（由 build_ui 创建） ----
        self.structure_tree: QTreeWidget | None = None
        self.btn_struct_pro: QPushButton | None = None
        self.btn_struct_con: QPushButton | None = None
        self.btn_add_root_section: QPushButton | None = None
        self.btn_ai_structure: QPushButton | None = None
        self.btn_struct_expand: QPushButton | None = None
        self.btn_struct_collapse: QPushButton | None = None

    # ---- 对外属性 ----
    @property
    def structure_data_pro(self) -> list:
        return self._structure_data_pro

    @structure_data_pro.setter
    def structure_data_pro(self, value: list):
        self._structure_data_pro = value

    @property
    def structure_data_con(self) -> list:
        return self._structure_data_con

    @structure_data_con.setter
    def structure_data_con(self, value: list):
        self._structure_data_con = value

    @property
    def current_side(self) -> str:
        return self._struct_side

    @property
    def is_visible(self) -> bool:
        return self._visible

    def set_visible(self, visible: bool):
        self._visible = visible

    # ---- UI 构建（由主窗口 _setup_ui 调用） ----
    def build_ui(self) -> 'StructureTreeManager':
        """构建结构树面板的全部 UI 组件，返回 self 以支持链式调用"""
        self.setObjectName("structurePanel")
        self.setMinimumWidth(550)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # === 标题行 ===
        title_row = QHBoxLayout()
        title_row.setSpacing(4)
        title = QLabel("一辩稿结构")
        title.setObjectName("structTitle")
        title_row.addWidget(title)
        title_row.addStretch()

        # === 正方/反方切换按钮 ===
        side_row = QHBoxLayout()
        side_row.setSpacing(4)

        self.btn_struct_pro = QPushButton("正方")
        self.btn_struct_pro.setObjectName("structSideBtn")
        self.btn_struct_pro.setCheckable(True)
        self.btn_struct_pro.setChecked(True)
        self.btn_struct_pro.setCursor(Qt.PointingHandCursor)
        self.btn_struct_pro.setFixedHeight(26)
        self.btn_struct_pro.clicked.connect(lambda: self._switch_side("pro"))

        self.btn_struct_con = QPushButton("反方")
        self.btn_struct_con.setObjectName("structSideBtn")
        self.btn_struct_con.setCheckable(True)
        self.btn_struct_con.setCursor(Qt.PointingHandCursor)
        self.btn_struct_con.setFixedHeight(26)
        self.btn_struct_con.clicked.connect(lambda: self._switch_side("con"))

        side_row.addWidget(self.btn_struct_pro)
        side_row.addWidget(self.btn_struct_con)
        side_row.addStretch()

        # === 结构树控件 ===
        self.structure_tree = QTreeWidget()
        self.structure_tree.setObjectName("structTree")
        self.structure_tree.setHeaderHidden(True)
        self.structure_tree.setIndentation(16)
        self.structure_tree.setAnimated(True)
        self.structure_tree.setCursor(Qt.PointingHandCursor)
        self.structure_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.structure_tree.customContextMenuRequested.connect(self._on_context_menu)
        self.structure_tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        # === 底部按钮栏 ===
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_add_root_section = QPushButton("新增章节")
        self.btn_add_root_section.setObjectName("smallBtn")
        self.btn_add_root_section.setCursor(Qt.PointingHandCursor)
        self.btn_add_root_section.setFixedHeight(28)
        self.btn_add_root_section.clicked.connect(self._add_root_section)

        self.btn_struct_expand = QPushButton("展开")
        self.btn_struct_expand.setObjectName("smallBtn")
        self.btn_struct_expand.setCursor(Qt.PointingHandCursor)
        self.btn_struct_expand.setFixedHeight(28)
        self.btn_struct_expand.clicked.connect(lambda: self.structure_tree.expandAll())

        self.btn_struct_collapse = QPushButton("折叠")
        self.btn_struct_collapse.setObjectName("smallBtn")
        self.btn_struct_collapse.setCursor(Qt.PointingHandCursor)
        self.btn_struct_collapse.setFixedHeight(28)
        self.btn_struct_collapse.clicked.connect(lambda: self.structure_tree.collapseAll())

        self.btn_ai_structure = QPushButton("AI 分析结构")
        self.btn_ai_structure.setObjectName("aiStructBtn")
        self.btn_ai_structure.setCursor(Qt.PointingHandCursor)
        self.btn_ai_structure.setFixedHeight(28)
        self.btn_ai_structure.clicked.connect(self._on_ai_analyze)

        btn_row.addWidget(self.btn_add_root_section)
        btn_row.addWidget(self.btn_ai_structure)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_struct_expand)
        btn_row.addWidget(self.btn_struct_collapse)

        # === 组装 ===
        layout.addLayout(title_row)
        layout.addLayout(side_row)
        layout.addWidget(self.structure_tree)
        layout.addLayout(btn_row)

        # 初始加载正方结构
        self._refresh_tree("pro")
        return self

    # ---- 侧切换 ----
    def _switch_side(self, side: str):
        """切换结构树的显示侧（正方/反方）"""
        self._struct_side = side
        self.btn_struct_pro.setChecked(side == "pro")
        self.btn_struct_con.setChecked(side == "con")
        self._refresh_tree(side)

    # ---- 数据访问 ----
    def _get_data(self, side: str) -> list:
        """获取指定侧的结构树数据"""
        return self._structure_data_pro if side == "pro" else self._structure_data_con

    @staticmethod
    def _side_label(flag: str) -> str:
        return "正方" if flag == "pro" else "反方"

    # ---- 关键词规范化 ----
    def _normalize_keywords(self, keywords: list) -> list:
        """将旧格式（纯字符串）关键词转换为新格式（dict），并原地更新"""
        for i, item in enumerate(keywords):
            if isinstance(item, str):
                keywords[i] = {"word": item}
        return keywords

    def _normalize_node(self, node: dict):
        """递归规范化结构树节点中的关键词"""
        if "keywords" in node and isinstance(node["keywords"], list):
            self._normalize_keywords(node["keywords"])
        for child in node.get("children", []):
            if isinstance(child, dict):
                self._normalize_node(child)

    # ---- 结构树渲染 ----
    def _refresh_tree(self, side: str):
        """刷新结构树控件内容"""
        self.structure_tree.clear()
        data = self._get_data(side)
        label = self._side_label(side)

        root = QTreeWidgetItem(self.structure_tree, [f"{label}一辩稿结构"])
        root.setData(0, Qt.UserRole, "__root__")
        root.setFont(0, QFont("Microsoft YaHei", 10, QFont.Bold))
        root.setExpanded(True)

        if not data:
            hint = QTreeWidgetItem(root, ["（暂无结构，点击下方 新增章节 添加）"])
            hint.setFlags(Qt.NoItemFlags)
            return

        for section in data:
            self._populate_node(root, section)

    def _populate_node(self, parent_item: QTreeWidgetItem, node_data: dict):
        """递归填充结构树的一个节点"""
        name = node_data.get("name", "未命名")
        keywords = self._normalize_keywords(node_data.get("keywords", []))
        children = node_data.get("children", [])

        kw_count = len(keywords)
        display_text = f"{name} [{kw_count}]" if kw_count > 0 else name

        item = QTreeWidgetItem(parent_item, [display_text])
        item.setData(0, Qt.UserRole, node_data)
        item.setExpanded(True)

        # 关键词子节点
        for idx, kw_data in enumerate(keywords):
            word = kw_data.get("word", "")
            kw_item = QTreeWidgetItem(item, [f" {word}"])
            kw_item.setData(0, Qt.UserRole, f"__kwidx__{idx}")
            kw_item.setFont(0, QFont("Microsoft YaHei", 9))

        # 递归子节点
        for child in children:
            self._populate_node(item, child)

    # ---- 右键菜单 ----
    def _on_context_menu(self, pos):
        """结构树右键菜单"""
        item = self.structure_tree.itemAt(pos)
        if not item:
            return

        node_data = item.data(0, Qt.UserRole)
        side = self._struct_side
        label = self._side_label(side)

        menu = QMenu(self)
        menu.setObjectName("treeContextMenu")

        # 根节点
        if node_data == "__root__":
            action_add = menu.addAction("新增章节")
            action_add.triggered.connect(self._add_root_section)
            menu.exec_(self.structure_tree.viewport().mapToGlobal(pos))
            return

        # 关键词子节点
        if isinstance(node_data, str) and node_data.startswith("__kwidx__"):
            idx = int(node_data.replace("__kwidx__", ""))
            parent_item = item.parent()
            if not parent_item:
                return
            pdata = parent_item.data(0, Qt.UserRole)
            if not isinstance(pdata, dict):
                return
            keywords = self._normalize_keywords(pdata.get("keywords", []))
            if idx >= len(keywords):
                return
            kw_data = keywords[idx]
            word = kw_data.get("word", "")

            action_rename_kw = menu.addAction(f"重命名「{word}」")
            action_rename_kw.triggered.connect(lambda: self._rename_keyword(parent_item, idx))

            action_del_kw = menu.addAction(f"删除关键词「{word}」")
            action_del_kw.triggered.connect(lambda: self._delete_keyword(parent_item, idx))
            menu.exec_(self.structure_tree.viewport().mapToGlobal(pos))
            return

        # 章节节点
        section_name = node_data.get("name", "未命名")

        action_add_child = menu.addAction("添加子章节")
        action_add_child.triggered.connect(lambda: self._add_child_section(item))

        action_add_kw = menu.addAction("添加关键词")
        action_add_kw.triggered.connect(lambda: self._add_keyword_to_section(item))

        menu.addSeparator()

        action_rename = menu.addAction("重命名")
        action_rename.triggered.connect(lambda: self._rename_section(item))

        action_edit_slug = menu.addAction("编辑段落ID (slug)")
        action_edit_slug.triggered.connect(lambda: self._edit_section_slug(item))

        action_delete = menu.addAction("删除章节")
        action_delete.triggered.connect(lambda: self._delete_section(item))

        menu.exec_(self.structure_tree.viewport().mapToGlobal(pos))

    def _on_item_double_clicked(self, item: QTreeWidgetItem, col: int):
        """双击结构树节点 - 编辑章节名称"""
        node_data = item.data(0, Qt.UserRole)
        if not node_data or node_data == "__root__":
            return
        if isinstance(node_data, dict):
            self._rename_section(item)

    # ---- 文件 I/O 辅助 ----
    def _get_speech_filename(self, side: str) -> str | None:
        """根据当前辩论文件路径，生成正方/反方独立的一辩稿文件名"""
        mw = self._main_window
        if not mw.current_debate_path:
            return None
        dir_name = os.path.dirname(mw.current_debate_path)
        base = os.path.splitext(os.path.basename(mw.current_debate_path))[0]
        label = self._side_label(side)
        return os.path.join(dir_name, f"{base}_{label}一辩稿.json")

    def _update_status(self, msg: str):
        """快捷状态栏更新"""
        if hasattr(self._main_window, '_update_status'):
            self._main_window._update_status(msg)

    def get_leaf_slugs(self, side: str) -> list:
        """按广度优先顺序返回结构树所有叶子节点的 (slug, name) 列表。

        Returns:
            list[tuple]: [(slug, node_name), ...]
        """
        data = self._get_data(side)
        result = []

        def _walk(nodes):
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                children = node.get("children", [])
                if children:
                    _walk(children)
                else:
                    result.append((node.get("slug", _name_to_slug(node.get("name", ""))), node.get("name", "")))

        _walk(data)
        return result

    # ---- 数据持久化 ----
    def save_data(self, side: str):
        """将结构树数据保存到对应的一辩稿 JSON 文件中"""
        speech_file = self._get_speech_filename(side)
        if not speech_file:
            return

        data = self._get_data(side)
        try:
            existing = {}
            if os.path.isfile(speech_file):
                with open(speech_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            existing["structure_tree"] = data
            with open(speech_file, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, OSError) as e:
            self._update_status(f"保存结构树失败: {str(e)}")

    def load_data(self, side: str):
        """从一辩稿 JSON 文件中加载结构树数据"""
        speech_file = self._get_speech_filename(side)
        if side == "pro":
            self._structure_data_pro = []
        else:
            self._structure_data_con = []

        if speech_file and os.path.isfile(speech_file):
            try:
                with open(speech_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                loaded = data.get("structure_tree", [])
                if isinstance(loaded, list):
                    for node in loaded:
                        if isinstance(node, dict):
                            self._normalize_node(node)
                            # 向后兼容：旧节点无 slug 时自动生成
                            node.setdefault("slug", _name_to_slug(node.get("name", "")))
                    if side == "pro":
                        self._structure_data_pro = loaded
                    else:
                        self._structure_data_con = loaded
            except (json.JSONDecodeError, OSError) as e:
                label = self._side_label(side)
                self._update_status(f"{label}一辩稿加载失败: {str(e)}")

    def load_legacy_data(self, data: dict):
        """从旧版合并的一辩稿 JSON 中加载结构树数据"""
        st = data.get("structure_tree", {})
        self._structure_data_pro = st.get("pro", []) if isinstance(st, dict) else []
        self._structure_data_con = st.get("con", []) if isinstance(st, dict) else []
        for node in self._structure_data_pro:
            if isinstance(node, dict):
                self._normalize_node(node)
                node.setdefault("slug", _name_to_slug(node.get("name", "")))
        for node in self._structure_data_con:
            if isinstance(node, dict):
                self._normalize_node(node)
                node.setdefault("slug", _name_to_slug(node.get("name", "")))
        self._refresh_tree(self._struct_side)

    # ---- 章节 CRUD ----
    def _add_root_section(self):
        """添加一个根级章节"""
        side = self._struct_side
        label = self._side_label(side)

        name, ok = QInputDialog.getText(
            self, f"新增章节 - {label}一辩稿",
            "请输入章节名称（如：开篇立论、核心论证、总结陈词）："
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        data = self._get_data(side)
        data.append({"name": name, "slug": _name_to_slug(name), "keywords": [], "children": []})
        self._refresh_tree(side)
        self.save_data(side)
        self._update_status(f"已为{label}一辩稿添加章节: {name}")

    def _add_child_section(self, parent_item: QTreeWidgetItem):
        """在选中章节下添加子章节"""
        side = self._struct_side
        label = self._side_label(side)
        parent_data = parent_item.data(0, Qt.UserRole)
        if not isinstance(parent_data, dict):
            return

        parent_name = parent_data.get("name", "父章节")
        name, ok = QInputDialog.getText(
            self, f"添加子章节 - {label}一辩稿",
            f"在「{parent_name}」下添加子章节："
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        child_data = {"name": name, "slug": _name_to_slug(name), "keywords": [], "children": []}
        parent_data.setdefault("children", []).append(child_data)
        self._refresh_tree(side)
        self.save_data(side)
        self._update_status(f"已在「{parent_name}」下添加子章节: {name}")

    # ---- 重命名对话框 ----
    def _create_rename_dialog(self, title: str, label_text: str,
                              initial_text: str = "") -> tuple[str, bool]:
        """创建带 TitleBar 的 Frameless 圆角输入对话框。

        Returns:
            (text, accepted) — text 为用户输入内容, accepted 为 True/False
        """
        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        dlg.setAttribute(Qt.WA_TranslucentBackground)
        dlg.resize(420, 200)

        # 透明窗口的根布局
        root_layout = QVBoxLayout(dlg)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 实心内容容器（圆角 + 边框）
        container = QWidget()
        container.setObjectName("renameDialogContainer")
        container.setStyleSheet(
            f"#renameDialogContainer {{"
            f"  background-color: {tc('base')};"
            f"  border: 1px solid {tc('surface0')};"
            f"  border-radius: 12px;"
            f"}}"
        )
        clayout = QVBoxLayout(container)
        clayout.setContentsMargins(0, 0, 0, 0)
        clayout.setSpacing(0)

        # TitleBar
        tb = TitleBar(container, title=title, icon="✏️")
        tb._min_btn.setVisible(False)
        tb._max_btn.setVisible(False)
        clayout.addWidget(tb)

        # 内容区域
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        inner = QVBoxLayout(content)
        inner.setContentsMargins(16, 12, 16, 16)

        lbl = QLabel(label_text)
        lbl.setFont(QFont("Microsoft YaHei", 10))
        lbl.setStyleSheet(f"color: {tc('text')}; background: transparent;")
        lbl.setWordWrap(True)
        inner.addWidget(lbl)

        edit = QLineEdit()
        edit.setText(initial_text)
        edit.selectAll()
        edit.setFont(QFont("Microsoft YaHei", 11))
        edit.setStyleSheet(
            f"QLineEdit {{"
            f"  background-color: {tc('surface0')};"
            f"  color: {tc('text')};"
            f"  border: 1px solid {tc('surface1')};"
            f"  border-radius: 6px;"
            f"  padding: 8px 12px;"
            f"  font-size: 11pt;"
            f"}}"
            f"QLineEdit:focus {{"
            f"  border: 1px solid {tc('accent')};"
            f"}}"
        )
        inner.addWidget(edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = StarButton(text="取消", parent=container, auto_size=True)
        cancel_btn.clicked.connect(dlg.reject)

        ok_btn = StarButton(
            text="确定", parent=container,
            accent=tc("accent"), auto_size=True,
        )
        ok_btn.clicked.connect(dlg.accept)

        edit.returnPressed.connect(dlg.accept)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        inner.addLayout(btn_row)

        clayout.addWidget(content, 1)

        root_layout.addWidget(container)

        # TitleBar 关闭按钮 → reject 对话框
        tb._close_btn.clicked.disconnect()
        tb._close_btn.clicked.connect(dlg.reject)

        result = dlg.exec_()
        text = edit.text().strip()
        return (text, result == QDialog.Accepted)

    # ---- 关键词重命名 ----
    def _rename_keyword(self, parent_item: QTreeWidgetItem, idx: int):
        """重命名关键词"""
        side = self._struct_side
        pdata = parent_item.data(0, Qt.UserRole)
        if not isinstance(pdata, dict):
            return
        keywords = self._normalize_keywords(pdata.get("keywords", []))
        if idx < 0 or idx >= len(keywords):
            return

        word = keywords[idx].get("word", "")
        section_name = pdata.get("name", "章节")

        text, ok = self._create_rename_dialog(
            "重命名关键词",
            f"将关键词「{word}」（{section_name}）重命名为：",
            word,
        )
        if not ok or not text:
            return

        keywords[idx]["word"] = text
        self._refresh_tree(side)
        self.save_data(side)
        self._update_status(f"关键词已重命名: {word} → {text}")

    def _rename_section(self, item: QTreeWidgetItem):
        """重命名章节"""
        side = self._struct_side
        node_data = item.data(0, Qt.UserRole)
        if not isinstance(node_data, dict):
            return

        old_name = node_data.get("name", "")

        text, ok = self._create_rename_dialog(
            "重命名章节",
            f"将章节「{old_name}」重命名为：",
            old_name,
        )
        if not ok or not text:
            return

        node_data["name"] = text
        self._refresh_tree(side)
        self.save_data(side)
        self._update_status(f"章节已重命名: {old_name} → {text}")

    def _edit_section_slug(self, item: QTreeWidgetItem):
        """编辑章节的段落 ID（slug）"""
        side = self._struct_side
        node_data = item.data(0, Qt.UserRole)
        if not isinstance(node_data, dict):
            return

        section_name = node_data.get("name", "未命名")
        old_slug = node_data.get("slug", "")
        slug, ok = QInputDialog.getText(
            self, "编辑段落ID",
            f"为「{section_name}」设置段落标识符（英文，用于 AI diff 引用）：\n"
            f"例如: opening, definition, argument_1",
            text=old_slug,
        )
        if not ok or not slug.strip():
            return

        import re as _re
        new_slug = _re.sub(r'[^a-z0-9_]', '', slug.strip().lower())
        if not new_slug:
            CustomDialog.warning(self, "提示", "slug 只允许小写字母、数字和下划线")
            return

        node_data["slug"] = new_slug
        self._refresh_tree(side)
        self.save_data(side)
        self._update_status(f"段落ID已更新: {section_name} → {new_slug}")

    def _delete_section(self, item: QTreeWidgetItem):
        """删除选中的章节"""
        side = self._struct_side
        node_data = item.data(0, Qt.UserRole)
        if not isinstance(node_data, dict):
            return

        name = node_data.get("name", "未命名")
        result = CustomDialog.question(
            self, "确认删除",
            f"确定要删除章节「{name}」及其所有子章节和关键词吗？",
            buttons=[("否", "no"), ("是", "yes")])
        if result != "yes":
            return

        data = self._get_data(side)
        self._remove_node(data, node_data)
        self._refresh_tree(side)
        self.save_data(side)
        self._update_status(f"已删除章节: {name}")

    def _remove_node(self, data_list: list, target: dict) -> bool:
        """递归从数据列表中移除目标节点"""
        for i, node in enumerate(data_list):
            if node is target:
                data_list.pop(i)
                return True
            if "children" in node:
                if self._remove_node(node["children"], target):
                    return True
        return False

    # ---- 关键词 CRUD ----
    def _add_keyword_to_section(self, item: QTreeWidgetItem):
        """为选中的章节添加关键词"""
        side = self._struct_side
        label = self._side_label(side)
        node_data = item.data(0, Qt.UserRole)
        if not isinstance(node_data, dict):
            return

        section_name = node_data.get("name", "章节")
        existing = node_data.get("keywords", [])
        existing_words = ", ".join([k.get("word", k) if isinstance(k, dict) else k for k in existing])
        hint = f"已有关键词: {existing_words}" if existing_words else "暂无关键词"

        keyword, ok = QInputDialog.getText(
            self, f"添加关键词 - {label}一辩稿",
            f"为「{section_name}」添加关键词（多个用空格或逗号分隔）：\n{hint}"
        )
        if not ok or not keyword.strip():
            return

        new_kws = re.split(r'[,，\s]+', keyword.strip())
        new_kws = [k.strip() for k in new_kws if k.strip()]

        keywords_list = self._normalize_keywords(node_data.setdefault("keywords", []))
        added = 0
        existing_words_set = {k.get("word", "") for k in keywords_list}
        for kw in new_kws:
            if kw not in existing_words_set:
                keywords_list.append({"word": kw})
                existing_words_set.add(kw)
                added += 1

        if added > 0:
            self._refresh_tree(side)
            self.save_data(side)
            self._update_status(f"已为「{section_name}」添加 {added} 个关键词")
        else:
            CustomDialog.information(self, "提示", "关键词已存在或未输入有效关键词")

    def _delete_keyword(self, parent_item: QTreeWidgetItem, idx: int):
        """删除关键词（按索引）"""
        side = self._struct_side
        parent_data = parent_item.data(0, Qt.UserRole)
        if not isinstance(parent_data, dict):
            return

        section_name = parent_data.get("name", "章节")
        keywords_list = self._normalize_keywords(parent_data.get("keywords", []))
        if 0 <= idx < len(keywords_list):
            word = keywords_list[idx].get("word", "")
            keywords_list.pop(idx)
            self._refresh_tree(side)
            self.save_data(side)
            self._update_status(f"已从「{section_name}」删除关键词: {word}")

    # ---- 章节注释与原文引用（已移除 v5.x）----

    # ---- AI 自动分析结构 ----
    def _on_ai_analyze(self):
        """调用 AI 自动分析一辩稿结构"""
        side = self._struct_side
        label = self._side_label(side)
        mw = self._main_window
        edit = mw.edit_pro_speech if side == "pro" else mw.edit_con_speech
        speech_text = edit.toPlainText().strip()
        if not speech_text:
            CustomDialog.warning(self, "提示", f"{label}一辩稿内容为空，请先输入或加载一辩稿内容")
            return

        api_config = mw._load_api_config()
        if not api_config.get("api_key"):
            CustomDialog.warning(
                self, "缺少 API Key",
                "请在 api_config.json 中填写您的 DeepSeek API Key 后再使用 AI 分析功能。"
            )
            return

        debate_title = ""
        if mw.current_debate_data:
            pro = mw.current_debate_data.get("pro", "")
            con = mw.current_debate_data.get("con", "")
            debate_title = f"{pro} vs {con}"

        mw._ai_loading_bar.show_loading(f"AI正在分析{label}一辩稿结构…")

        self._struct_worker = StructureAnalysisWorker(api_config, speech_text, debate_title, side)
        self._struct_worker.finished.connect(self._on_analysis_finished)
        self._struct_worker.start()

    def cancel_worker(self):
        """取消结构分析 worker"""
        if hasattr(self, "_struct_worker") and self._struct_worker:
            self._struct_worker.terminate()
            self._struct_worker.wait(2000)
            self._update_status("已取消 AI 结构分析")

    def _on_analysis_finished(self, success: bool, side: str, result: str):
        """AI 结构分析完成回调"""
        mw = self._main_window
        mw._ai_loading_bar.hide_loading()

        if not success:
            CustomDialog.warning(self, "结构分析失败", f"AI 分析出错：\n{result}")
            self._update_status("AI 结构分析失败")
            return

        label = self._side_label(side)

        try:
            cleaned = result.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned = "\n".join(lines)
            struct_data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            CustomDialog.warning(
                self, "结构解析失败",
                f"AI 返回的格式无法解析为 JSON。\n错误：{e}\n\n"
                f"AI 原始返回（前500字）：\n{result[:500]}"
            )
            self._update_status("AI 结构分析：JSON 解析失败")
            return

        if not isinstance(struct_data, list):
            CustomDialog.warning(self, "结构解析失败", "AI 返回的 JSON 结构不是数组格式")
            return

        for node in struct_data:
            if not isinstance(node, dict):
                continue
            node.setdefault("name", "未命名")
            node.setdefault("slug", _name_to_slug(node["name"]))
            node.setdefault("children", [])
            if "keywords" not in node or not isinstance(node.get("keywords"), list):
                node["keywords"] = []
            self._normalize_node(node)

        if side == "pro":
            self._structure_data_pro = struct_data
        else:
            self._structure_data_con = struct_data

        self._refresh_tree(side)
        self.save_data(side)

        chapter_count = len(struct_data)
        kw_count = sum(len(n.get("keywords", [])) for n in struct_data if isinstance(n, dict))
        self._update_status(f"AI 结构分析完成：{label}一辩稿 {chapter_count} 个章节, {kw_count} 个关键词")

        CustomDialog.information(
            self, "结构分析完成",
            f"AI 已自动分析{label}一辩稿结构：\n"
            f"• {chapter_count} 个章节\n"
            f"• {kw_count} 个关键词\n\n"
            f"结构树已自动更新，您可以在左侧拖动调整章节位置，"
            f"或右键编辑章节名称和关键词。"
        )

    # ---- 面板显示/隐藏 ----
    def toggle_visibility(self) -> bool:
        """切换面板可见性，返回新的可见状态"""
        self._visible = not self._visible
        self.setVisible(self._visible)
        return self._visible

    def set_panel_disabled(self, disabled: bool):
        """设置面板禁用状态（用于立论驳论暂停模式）"""
        self.setEnabled(not disabled)
        if disabled:
            self.setStyleSheet(
                f"#structurePanel {{ background-color: {tc('mantle')}; }}"
                f"QTreeWidget {{ background-color: {tc('base')}; color: {tc('pressed')}; }}"
            )
        else:
            self.setStyleSheet("")
            self.style().unpolish(self)
            self.style().polish(self)
