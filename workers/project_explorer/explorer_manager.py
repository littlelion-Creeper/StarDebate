"""ProjectExplorerManager：项目树管理（构建/刷新/点击/右键菜单/置顶/删除）"""
import os
import json
import shutil
from PyQt5.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QMenu, QFileDialog,
    QInputDialog,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from components.popup_dialog import CustomDialog
from components.icon_loader import load_common_icon
from workers.plugin_manager import get_manager


def _get_file_icon(filename: str) -> "QIcon":
    """根据文件名返回对应类型的 SVG 图标。"""
    if any(k in filename for k in ("_一辩稿", "_正方一辩稿", "_反方一辩稿", "_一辩稿_分析")):
        return load_common_icon("speech.svg")
    if "_资料稿" in filename:
        return load_common_icon("form.svg")
    if "_质询模拟" in filename:
        return load_common_icon("cross.svg")
    if "_接质模拟_" in filename:
        return load_common_icon("accept.svg")
    if filename.startswith("train_") and filename.endswith(".json"):
        return load_common_icon("train.svg")
    if filename.endswith(".stardebate"):
        return load_common_icon("STDB.svg")
    if filename.endswith(".json"):
        return load_common_icon("debate.svg")
    if filename.endswith(".json") and "分析" in filename:
        return load_common_icon("analysis.svg")
    return load_common_icon("unknown.svg")


def _simplify_name(name: str) -> str:
    """简化文件名：去掉第一个 _ 之前的内容 + 去掉扩展名。
    - 辩论_一辩稿.json      → 一辩稿
    - 赛题1_质询模拟.json    → 质询模拟
    - 无下划线的文件.json    → 无下划线的文件
    """
    if "_" not in name:
        return os.path.splitext(name)[0]
    core = name.split("_", 1)[1]
    return os.path.splitext(core)[0]


class ProjectExplorerManager:
    """管理项目树控件的全部操作"""

    def __init__(self, mw):
        """
        Args:
            mw: StarDebateWindow 实例引用，需提供以下属性/方法：
                - project_tree: QTreeWidget
                - centre_stack: QStackedWidget
                - current_debate_path / current_debate_data
                - _pinned_items: set
                - _ref_doc_mgr
                - _speech_mgr (SpeechEditorManager)
                - _cross_mgr (CrossExaminationManager)
                - _accept_mgr (AcceptExaminationManager)
                - _train_mgr (TrainingManager)
                - _tournament_mgr (TournamentManager)
                - _update_status(msg)
                - _display_debate(file_path, data)
                - _build_tree_from_path(path)
                - _derive_debate_path(file_path, suffix)
        """
        self._mw = mw

    @property
    def tree(self) -> QTreeWidget:
        return self._mw.project_tree

    # ========== 初始化 ==========

    def populate_tree(self):
        """初始化树形控件（空状态）"""
        self.tree.clear()
        hint = QTreeWidgetItem(self.tree, ["请通过「文件 → 打开项目」选择文件夹"])
        hint.setFlags(Qt.NoItemFlags)

    # ========== 项目操作 ==========

    def create_project(self):
        """创建项目：选择父目录并输入项目名"""
        parent_dir = QFileDialog.getExistingDirectory(self._mw, "选择项目父目录")
        if not parent_dir:
            return
        project_name, ok = QInputDialog.getText(
            self._mw, "创建项目", "请输入项目名称:", text="MyProject"
        )
        if not ok or not project_name.strip():
            return
        project_name = project_name.strip()
        project_path = os.path.join(parent_dir, project_name)
        if os.path.exists(project_path):
            CustomDialog.warning(self._mw, "创建失败", f"文件夹已存在:\n{project_path}")
            return
        try:
            os.makedirs(project_path)
            self._mw._update_status(f"项目已创建: {project_path}")
            self._mw._build_tree_from_path(project_path)
            self._mw._save_config(project_path)
        except OSError as e:
            CustomDialog.error(self._mw, "创建失败", f"无法创建项目:\n{str(e)}")

    def open_project_dialog(self):
        """打开项目：选择文件夹"""
        folder = QFileDialog.getExistingDirectory(self._mw, "选择项目文件夹")
        if not folder:
            return
        self._mw._update_status(f"已打开项目: {folder}")
        self._mw._build_tree_from_path(folder)
        self._mw._save_config(folder)

    def build_tree_from_path(self, root_path: str):
        """递归扫描文件夹，展示到树控件"""
        self.tree.clear()
        folder_name = os.path.basename(root_path) or root_path
        root_item = QTreeWidgetItem(self.tree, [folder_name])
        root_item.setData(0, Qt.UserRole, root_path)
        root_item.setIcon(0, load_common_icon("folder.svg"))
        root_item.setExpanded(True)

        # 读取是否简化文件名
        config = self._mw._app_cfg.load_full_config()
        simplify = config.get("simplify_tree_names", True)

        self._populate_dir(root_item, root_path, simplify)
        self._mw._update_status(f"项目加载完成: {os.path.basename(root_path)}")

    def _populate_dir(self, parent_item: QTreeWidgetItem, dir_path: str, simplify: bool = True):
        """递归填充目录子节点（置顶项排在前面）"""
        try:
            entries_raw = os.listdir(dir_path)
        except PermissionError:
            error_item = QTreeWidgetItem(parent_item, ["[权限不足]"])
            return

        def _entry_key(name: str):
            full = os.path.join(dir_path, name)
            pinned = full in self._mw._pinned_items
            return (not pinned, name.lower())

        entries = sorted(entries_raw, key=_entry_key)

        for name in entries:
            full_path = os.path.join(dir_path, name)
            is_dir = os.path.isdir(full_path)
            display_name = name if is_dir else (_simplify_name(name) if simplify else name)
            node = QTreeWidgetItem(parent_item, [display_name])
            node.setData(0, Qt.UserRole, full_path)
            if is_dir:
                node.setIcon(0, load_common_icon("folder.svg"))
                self._populate_dir(node, full_path, simplify)
            else:
                node.setIcon(0, _get_file_icon(name))
                if full_path in self._mw._pinned_items:
                    node.setText(0, f"{display_name}")

    def get_current_project_path(self):
        """获取当前在 tree 中打开的项目根路径

        兼容两种节点类型：
        - 文件夹项目节点：路径存在 Qt.UserRole
        - .stardebate 节点：文件路径存在 Qt.UserRole + 2，需取其父目录
        """
        root = self.tree.invisibleRootItem()
        if root.childCount() == 0:
            return None
        first = root.child(0)
        if not first or first.flags() == Qt.NoItemFlags:
            return None

        # 1. 尝试标准路径（文件夹项目）
        proot = first.data(0, Qt.UserRole)
        if proot and os.path.isdir(proot):
            return proot

        # 2. 尝试 .stardebate 节点路径（路径存在 UserRole+2）
        stdb_path = first.data(0, Qt.UserRole + 2)
        if stdb_path and os.path.isfile(stdb_path):
            return os.path.dirname(stdb_path)

        # 3. 遍历所有一级节点查找
        for i in range(root.childCount()):
            child = root.child(i)
            p = child.data(0, Qt.UserRole)
            if p and os.path.isdir(p):
                return p
            sp = child.data(0, Qt.UserRole + 2)
            if sp and os.path.isfile(sp):
                return os.path.dirname(sp)

        return None

    # ========== 树点击 ==========

    def on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """点击树控件节点"""
        # ── 检测 .stardebate 节点 ──
        node_type = item.data(0, Qt.UserRole + 1)
        if node_type in ("STARDEBATE", "STARDEBATE_MODULE"):
            if hasattr(self._mw, '_stdb_editor_mgr') and self._mw._stdb_editor_mgr:
                self._mw._stdb_editor_mgr.on_stardebate_node_clicked(item)
            return

        file_path = item.data(0, Qt.UserRole)
        if not file_path or not os.path.isfile(file_path):
            return
        ext = os.path.splitext(file_path)[1].lower()
        if ext != ".json":
            return
        mw = self._mw
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            fname = os.path.basename(file_path)

            if "_资料稿" in fname:
                mw._derive_debate_path(file_path, "_资料稿")
                rows = data.get("rows", [])
                mw._ref_doc_mgr.ref_doc_rows = rows if isinstance(rows, list) else []
                mw._ref_doc_mgr._refresh_ref_doc_table()
                mw.centre_stack.setCurrentIndex(4)
                mw._update_status(f"已加载资料稿: {fname}")
            elif any(s in fname for s in ("_一辩稿", "_正方一辩稿", "_反方一辩稿", "_一辩稿_分析")):
                if mw._speech_mgr.handle_tree_click(file_path, fname):
                    pass
            elif "_质询模拟" in fname:
                mw._derive_debate_path(file_path, "_质询模拟")
                mw._cross_mgr.handle_tree_click(file_path, data)
            elif "_接质模拟_" in fname:
                mw._derive_debate_path(file_path, "_接质模拟_")
                if not mw._accept_mgr.handle_tree_click(file_path):
                    CustomDialog.warning(mw, "加载失败", f"无法加载接质模拟文件:\n{file_path}")
            elif fname.startswith("train_") and fname.endswith(".json"):
                session_data = data
                session_data["_filepath"] = file_path
                if not mw._train_mgr._visible:
                    mw._train_mgr.toggle_visibility()
                mw._train_mgr._current_history_session = session_data
                mw._train_mgr._on_view_session(session_data)
                mw._update_status(f"已加载训练记录: {fname}")
            else:
                mw.current_debate_path = file_path
                mw.current_debate_data = data
                mw._display_debate(file_path, data)
                mw._update_status(f"已加载辩论: {os.path.basename(file_path)}")
        except (json.JSONDecodeError, OSError) as e:
            mw._update_status(f"加载失败: {str(e)}")

    # ========== 右键菜单 ==========

    def on_context_menu(self, pos):
        """树控件右键菜单"""
        item = self.tree.itemAt(pos)
        if not item:
            return
        file_path = item.data(0, Qt.UserRole)
        if not file_path:
            return
        menu = QMenu(self._mw)
        menu.setObjectName("treeContextMenu")
        is_root = (item.parent() is None)
        is_pinned = (file_path in self._mw._pinned_items)

        if is_pinned:
            action_unpin = menu.addAction("取消置顶")
            action_unpin.triggered.connect(lambda: self._on_pin_item(item, file_path, False))
        else:
            action_pin = menu.addAction("置顶")
            action_pin.triggered.connect(lambda: self._on_pin_item(item, file_path, True))

        menu.addSeparator()
        # 从注册表读取外部菜单项
        mgr = get_manager()
        for item_info in mgr.get_context_menu_items():
            a = menu.addAction(item_info["label"])
            cb = item_info["callback"]
            a.triggered.connect(lambda checked=False, c=cb, fp=file_path: c(fp))
        menu.addSeparator()
        action_delete = menu.addAction("删除")
        action_delete.triggered.connect(lambda: self._on_delete_item(item, file_path, is_root))
        menu.exec_(self.tree.viewport().mapToGlobal(pos))

    # ========== 删除 ==========

    def _on_delete_item(self, item: QTreeWidgetItem, file_path: str, is_root: bool):
        """删除树节点对应的文件或文件夹"""
        name = os.path.basename(file_path)
        type_name = "项目文件夹" if is_root else ("文件夹" if os.path.isdir(file_path) else "文件")

        result = CustomDialog.question(
            self._mw, "确认删除",
            f"确定要删除{type_name}\n「{name}」吗？\n\n此操作不可撤销！",
            buttons=[("否", "no"), ("是", "yes")])
        if result != "yes":
            return
        try:
            if os.path.isdir(file_path):
                shutil.rmtree(file_path)
            else:
                os.remove(file_path)
            self._mw._pinned_items.discard(file_path)
            parent = item.parent() or self.tree.invisibleRootItem()
            parent.removeChild(item)
            if is_root:
                self.populate_tree()
            self._mw._update_status(f"已删除: {name}")
        except OSError as e:
            CustomDialog.error(self._mw, "删除失败", f"无法删除:\n{str(e)}")

    # ========== 置顶 ==========

    def _on_pin_item(self, item: QTreeWidgetItem, file_path: str, pin: bool):
        """置顶/取消置顶树节点"""
        name = os.path.basename(file_path)
        if pin:
            parent = item.parent() or self.tree.invisibleRootItem()
            index = parent.indexOfChild(item)
            if index > 0:
                taken = parent.takeChild(index)
                parent.insertChild(0, taken)
                self.tree.setCurrentItem(taken)
            self._mw._pinned_items.add(file_path)
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
            self._mw._update_status(f"已置顶: {name}")
        else:
            self._mw._pinned_items.discard(file_path)
            font = item.font(0)
            font.setBold(False)
            item.setFont(0, font)
            self._mw._update_status(f"已取消置顶: {name}")
