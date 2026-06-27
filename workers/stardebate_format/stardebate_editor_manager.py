"""StardebateEditorManager — .stardebate 文件编辑器核心管理器。

职责:
  1. 管理已打开的 .stardebate 文件（内存中，不写临时文件）
  2. 提供模块数据给编辑器注入
  3. 从编辑器收集修改后的数据
  4. 退出时自动加密保存
  5. 密码管理（DPAPI 加密存储）

监视钩子:
  - variable_watch: 数据状态变更
  - function_watch: 各 def 函数执行
  - api_watch: 与 StardebateCompiler API 交互
"""

import os
import json
import time
from typing import Optional, Callable
from PyQt5.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QApplication, QStackedWidget,
)
from PyQt5.QtCore import Qt


from .stardebate_compiler import StardebateCompiler
from .dpapi_crypto import (
    load_index, save_index, add_file_to_index,
    remove_file_from_index, get_password_for_file,
    update_password_for_file, encrypt_password,
)
from components.icon_loader import load_common_icon, get_module_svg_icon

# ── 监视钩子 ──────────────────────────────────────────────────────
_MONITOR_TAGS = {
    'variable_watch': 'VAR',
    'function_watch': 'FUNC',
    'plugin_watch': 'PLUGIN',
    'api_watch': 'API',
    'ai_watch': 'AI',
}

def _monitor(mtype: str, message: str):
    import sys
    from datetime import datetime
    tag = _MONITOR_TAGS.get(mtype, 'MON')
    now = datetime.now()
    ts = now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"
    try:
        sys.stderr.write(f"[{ts}] [INFO] [{tag}] {message}\n")
        sys.stderr.flush()
    except Exception:
        pass


# ═════════════════════════════════════════════════════════════════
#  模块 → 页面映射
# ═════════════════════════════════════════════════════════════════

# module_id → (centre_stack_index, description, icon, category)
MODULE_REGISTRY = {
    "basic":          (1,  "辩论基本信息", "📝", "info"),
    "speech_pro":     (2,  "正方一辩稿",   "✏",  "speech"),
    "speech_con":     (2,  "反方一辩稿",   "✏",  "speech"),
    "ref_doc_pro":    (4,  "正方资料稿",   "📊", "ref"),
    "ref_doc_con":    (4,  "反方资料稿",   "📊", "ref"),
    "analysis_pro":   (3,  "正方AI分析",   "🤖", "analysis"),
    "analysis_con":   (3,  "反方AI分析",   "🤖", "analysis"),
    "framework":      (8,  "辩论框架",      "🗺",  "structure"),
    "cross_exam":     (6,  "模拟质询",      "💬", "exam"),
    "accept_exam_pro":(7,  "正方接质",      "🛡",  "exam"),
    "accept_exam_con":(7,  "反方接质",      "🛡",  "exam"),
    "notes":          (1,  "便签",          "📋", "other"),
    "structure":      (1,  "结构树",        "🌳", "structure"),
    "training":       (9,  "训练记录",      "🎯", "other"),
}


def get_page_index(module_id: str) -> int:
    """获取模块对应的 centre_stack 页面索引。"""
    return MODULE_REGISTRY.get(module_id, (1,))[0]


def get_module_label(module_id: str) -> str:
    """获取模块的显示名称。"""
    return MODULE_REGISTRY.get(module_id, ("", module_id))[1]


def get_module_icon(module_id: str) -> str:
    """获取模块图标。"""
    return MODULE_REGISTRY.get(module_id, ("", "", ""))[2]


# ═════════════════════════════════════════════════════════════════
#  StardebateEditorManager
# ═════════════════════════════════════════════════════════════════

class StardebateEditorManager:
    """.stardebate 文件编辑器管理器。

    用法:
        mgr = StardebateEditorManager(mw)
        # 导入文件
        mgr.open_file("C:/.../辩论.stardebate", password="secret")
        # 获取模块数据注入编辑器
        data = mgr.get_module_data(file_path, "speech_pro")
        # 修改后标记
        mgr.mark_dirty(file_path, "speech_pro")
        # 退出时保存
        mgr.save_all()
    """

    def __init__(self, mw):
        """初始化管理器。

        Args:
            mw: StarDebateWindow 实例，需提供:
                - project_tree: QTreeWidget
                - centre_stack: QStackedWidget
                - _update_status(msg)
                - _speech_mgr (SpeechEditorManager)
                - _ref_doc_mgr (RefDocManager)
                - _framework_mgr (FrameworkManager)
                - _cross_mgr (CrossExaminationManager)
                - _accept_mgr (AcceptExaminationManager)
                - _train_mgr (TrainingManager)
                - _structure_mgr (StructureTreeManager)
        """
        self._mw = mw
        self._compiler = StardebateCompiler()

        # 已打开文件的数据: {file_path: {"modules": dict, "meta": dict, "password": str|None, "dirty_modules": set}
        self._open_files: dict = {}

        # 当前选中的文件路径
        self._active_file: Optional[str] = None

        # 模块面板引用（由 ui_assembly 设置）
        self._module_panel = None

        # 项目树中 .stardebate 节点的引用
        self._tree_nodes: dict[str, QTreeWidgetItem] = {}

    # ── 属性 ─────────────────────────────────────────────────────

    @property
    def open_files(self) -> dict:
        return self._open_files

    @property
    def active_file(self) -> Optional[str]:
        return self._active_file

    @property
    def active_data(self) -> Optional[dict]:
        if self._active_file and self._active_file in self._open_files:
            return self._open_files[self._active_file]
        return None

    def set_module_panel(self, panel):
        """设置模块卡片面板引用。"""
        self._module_panel = panel

    # ── 打开文件 ─────────────────────────────────────────────────

    def open_file(self, file_path: str, password: Optional[str] = None) -> dict:
        """打开并解密 .stardebate 文件，数据保存在内存中。

        Args:
            file_path: .stardebate 文件路径
            password: 用户密码（如果有密码保护）

        Returns:
            {"success": bool, "error": str|None, "meta": dict}
        """
        _monitor('function_watch', f'open_file: path={os.path.basename(file_path)}')

        if not os.path.isfile(file_path):
            return {"success": False, "error": "文件不存在", "meta": {}}

        if file_path in self._open_files:
            return {"success": True, "error": None, "meta": self._open_files[file_path]["meta"]}

        # 读取文件
        try:
            with open(file_path, "rb") as f:
                raw_data = f.read()
        except Exception as e:
            return {"success": False, "error": f"读取文件失败: {e}", "meta": {}}

        # 验证格式
        if not self._compiler.verify_magic(raw_data):
            return {"success": False, "error": "不是有效的 .stardebate 文件", "meta": {}}

        # 获取文件信息
        info = self._compiler.get_file_info(raw_data)

        # 解密
        if info["has_password"] and not password:
            return {
                "success": False,
                "error": "PASSWORD_REQUIRED",
                "meta": {"has_password": True, "file_path": file_path, **info},
            }

        result = self._compiler.unpack(raw_data, password=password)
        if not result["success"]:
            _monitor('api_watch', f'open_file: 解密失败 → {result["error"]}')
            return {
                "success": False,
                "error": result["error"],
                "meta": result.get("meta", {}),
            }

        # 存入内存
        self._open_files[file_path] = {
            "modules": result["modules"],
            "meta": result["meta"],
            "password": password,
            "dirty_modules": set(),
        }

        # 添加到索引（持久化）
        file_uuid = result["meta"].get("debate_uuid", "")
        add_file_to_index(file_path, file_uuid, password)

        # 添加到项目树
        self._add_to_project_tree(file_path)

        # 设置为当前活动文件
        self._active_file = file_path

        _monitor('variable_watch',
                 f'open_file: 解密成功, modules={len(result["modules"])}, '
                 f'file={os.path.basename(file_path)}')

        return {"success": True, "error": None, "meta": result["meta"]}

    def open_file_with_stored_password(self, file_path: str) -> dict:
        """尝试用存储的密码打开文件（启动时自动加载）。

        Returns:
            {"success": bool, "error": str|None, "meta": dict}
        """
        _monitor('function_watch', f'open_file_with_stored_password: {os.path.basename(file_path)}')

        password = get_password_for_file(file_path)
        return self.open_file(file_path, password=password)

    # ── 项目树管理 ───────────────────────────────────────────────

    def _add_to_project_tree(self, file_path: str):
        """在项目树中添加 .stardebate 顶级节点。"""
        _monitor('variable_watch', f'_add_to_project_tree: {os.path.basename(file_path)}')
        tree = self._mw.project_tree
        file_name = os.path.basename(file_path)
        data = self._open_files.get(file_path, {})

        # 创建顶级节点
        node = QTreeWidgetItem(tree)
        node.setText(0, file_name)
        node.setData(0, Qt.UserRole + 1, "STARDEBATE")  # 标记类型
        node.setData(0, Qt.UserRole + 2, file_path)       # 存储文件路径
        node.setExpanded(True)
        stdb_icon = load_common_icon("STDB.svg")
        if stdb_icon:
            node.setIcon(0, stdb_icon)

        # 添加模块子节点
        modules = data.get("modules", {})
        for module_id in MODULE_REGISTRY:
            if module_id in modules:
                label = get_module_label(module_id)
                child = QTreeWidgetItem(node)
                child.setText(0, f"  {label}")
                child.setData(0, Qt.UserRole + 1, "STARDEBATE_MODULE")
                child.setData(0, Qt.UserRole + 2, file_path)
                child.setData(0, Qt.UserRole + 3, module_id)
                module_icon = get_module_svg_icon(module_id)
                if module_icon:
                    child.setIcon(0, module_icon)

        self._tree_nodes[file_path] = node
        self._mw._update_status(f"已加载 .stardebate: {file_name}")

    def remove_from_project_tree(self, file_path: str):
        """从项目树移除 .stardebate 节点。"""
        _monitor('variable_watch', f'remove_from_project_tree: {os.path.basename(file_path)}')
        tree = self._mw.project_tree
        root = tree.invisibleRootItem()
        for i in range(root.childCount()):
            child = root.child(i)
            if child.data(0, Qt.UserRole + 1) == "STARDEBATE" and child.data(0, Qt.UserRole + 2) == file_path:
                root.takeChild(i)
                self._tree_nodes.pop(file_path, None)
                break

    def _refresh_tree_node(self, file_path: str):
        """刷新项目树中 .stardebate 节点的显示（标记修改状态）。"""
        node = self._tree_nodes.get(file_path)
        if not node:
            return
        data = self._open_files.get(file_path, {})
        dirty = data.get("dirty_modules", set())
        file_name = os.path.basename(file_path)

        if dirty:
            node.setText(0, f"{file_name} ⚠")
        else:
            node.setText(0, f"{file_name}")

    # ── 模块数据接口 ─────────────────────────────────────────────

    def get_module_data(self, file_path: str, module_id: str) -> Optional[dict]:
        """获取指定模块的数据（用于注入编辑器）。"""
        data = self._open_files.get(file_path, {})
        modules = data.get("modules", {})
        return modules.get(module_id)

    def mark_dirty(self, file_path: str, module_id: str):
        """标记模块已修改。"""
        if file_path in self._open_files:
            self._open_files[file_path]["dirty_modules"].add(module_id)
            self._refresh_tree_node(file_path)
            _monitor('variable_watch', f'mark_dirty: {os.path.basename(file_path)}/{module_id}')

    def update_module_data(self, file_path: str, module_id: str, data: dict):
        """更新内存中的模块数据（从编辑器收集）。"""
        _monitor('function_watch', f'update_module_data: {module_id}')
        if file_path in self._open_files:
            self._open_files[file_path]["modules"][module_id] = data
            self.mark_dirty(file_path, module_id)
            _monitor('variable_watch', f'update_module_data: {module_id} data updated ({len(str(data))} chars)')

    def is_dirty(self, file_path: str) -> bool:
        """检查文件是否有未保存的修改。"""
        data = self._open_files.get(file_path, {})
        return len(data.get("dirty_modules", set())) > 0

    def get_dirty_modules(self, file_path: str) -> set:
        """获取所有已修改的模块 ID。"""
        return self._open_files.get(file_path, {}).get("dirty_modules", set()).copy()

    # ── 收集编辑器数据 ───────────────────────────────────────────

    def collect_all_editor_data(self, file_path: str):
        """从所有现有编辑器中收集最新数据到内存（包括正反两方）。

        调用时机：保存前、切换文件前。
        """
        mw = self._mw
        data = self._open_files.get(file_path)
        if not data:
            return
        modules = data["modules"]

        _monitor('function_watch', f'collect_all_editor_data: {os.path.basename(file_path)}')

        # ── 正方一辩稿 ──
        try:
            if hasattr(mw._speech_mgr, 'edit_pro_speech') and mw._speech_mgr.edit_pro_speech:
                text = mw._speech_mgr.edit_pro_speech.toPlainText()
                modules["speech_pro"] = {
                    "content": text,
                    "keywords": list(mw._speech_mgr.keywords_pro),
                    "custom_glossary": dict(mw._speech_mgr.custom_glossary_pro),
                }
                _monitor('variable_watch',
                         f'collect: speech_pro → {len(text)} chars, '
                         f'{len(mw._speech_mgr.keywords_pro)} keywords')
        except Exception:
            pass

        # ── 反方一辩稿 ──
        try:
            if hasattr(mw._speech_mgr, 'edit_con_speech') and mw._speech_mgr.edit_con_speech:
                text = mw._speech_mgr.edit_con_speech.toPlainText()
                modules["speech_con"] = {
                    "content": text,
                    "keywords": list(mw._speech_mgr.keywords_con),
                    "custom_glossary": dict(mw._speech_mgr.custom_glossary_con),
                }
                _monitor('variable_watch',
                         f'collect: speech_con → {len(text)} chars, '
                         f'{len(mw._speech_mgr.keywords_con)} keywords')
        except Exception:
            pass

        # ── 资料稿 ──
        try:
            if hasattr(mw._ref_doc_mgr, 'ref_doc_rows'):
                rows = mw._ref_doc_mgr.ref_doc_rows
                current_side = getattr(mw._ref_doc_mgr, '_current_stdeb_side', 'pro')
                key = f"ref_doc_{current_side}"
                if key in modules and rows:
                    modules[key]["rows"] = list(rows)
                    _monitor('variable_watch', f'collect: {key} → {len(rows)} rows')
        except Exception:
            pass

        # ── 辩论框架 ──
        try:
            fw_data = mw._framework_mgr.data
            if fw_data and "framework" in modules:
                modules["framework"] = list(fw_data)
                _monitor('variable_watch', f'collect: framework → {len(fw_data)} nodes')
        except Exception:
            pass

        # ── 模拟质询 ──
        try:
            if hasattr(mw._cross_mgr, '_rounds') and "cross_exam" in modules:
                modules["cross_exam"] = {"rounds": list(mw._cross_mgr._rounds)}
                _monitor('variable_watch',
                         f'collect: cross_exam → {len(mw._cross_mgr._rounds)} rounds')
        except Exception:
            pass

        _monitor('function_watch',
                 f'collect_all_editor_data: done, '
                 f'modules in file={[k for k in modules.keys()]}')

    # ── 保存 ─────────────────────────────────────────────────────

    def save_file(self, file_path: str, password: Optional[str] = None) -> dict:
        """保存 .stardebate 文件（加密并写入磁盘）。

        Args:
            file_path: 文件路径
            password: 密码（None 表示使用原密码或无密码）

        Returns:
            {"success": bool, "error": str|None}
        """
        _monitor('function_watch', f'save_file: {os.path.basename(file_path)}')

        data = self._open_files.get(file_path)
        if not data:
            return {"success": False, "error": "文件数据不存在"}

        # 先收集所有编辑器数据
        self.collect_all_editor_data(file_path)

        # 获取密码
        if password is None:
            password = data.get("password")

        try:
            modules = data["modules"]
            meta = data.get("meta", {})
            app_version = meta.get("app_version", "2.3.0")

            # 使用 StardebateCompiler 打包加密
            file_bytes = self._compiler.pack(modules, password=password, app_version=app_version)

            # 写入磁盘
            with open(file_path, "wb") as f:
                f.write(file_bytes)

            # 更新内存状态
            data["password"] = password
            data["dirty_modules"].clear()

            # 更新索引中的密码
            if password is not None:
                update_password_for_file(file_path, password)

            self._refresh_tree_node(file_path)

            _monitor('api_watch',
                     f'save_file: 保存成功, size={len(file_bytes)}, '
                     f'file={os.path.basename(file_path)}')

            self._mw._update_status(f".stardebate 已保存: {os.path.basename(file_path)}")
            return {"success": True, "error": None}

        except Exception as e:
            _monitor('api_watch', f'save_file: 保存失败 → {e}')
            return {"success": False, "error": str(e)}

    def save_all(self) -> list[dict]:
        """保存所有打开的 .stardebate 文件（无条件全部保存）。"""
        _monitor('function_watch', f'save_all: {len(self._open_files)} open files')
        results = []
        for file_path in list(self._open_files.keys()):
            result = self.save_file(file_path)
            results.append({"file": file_path, **result})
        _monitor('api_watch', f'save_all: {len(results)} files saved')
        return results

    # ── 密码管理 ─────────────────────────────────────────────────

    def change_password(self, file_path: str, old_password: str, new_password: Optional[str]) -> dict:
        """修改文件的密码。

        Args:
            file_path: 文件路径
            old_password: 旧密码（用于验证）
            new_password: 新密码（None 表示移除密码保护）

        Returns:
            {"success": bool, "error": str|None}
        """
        _monitor('function_watch', f'change_password: {os.path.basename(file_path)}')

        data = self._open_files.get(file_path)
        if not data:
            return {"success": False, "error": "文件未打开"}

        # 验证旧密码
        current_password = data.get("password")
        if current_password != old_password:
            return {"success": False, "error": "旧密码不正确"}

        # 更新内存中的密码
        data["password"] = new_password
        data["dirty_modules"].add("__password__")  # 标记需要重新加密

        # 更新索引
        update_password_for_file(file_path, new_password)

        _monitor('variable_watch',
                 f'change_password: {"removed" if new_password is None else "updated"} '
                 f'for {os.path.basename(file_path)}')

        self._mw._update_status(
            f"密码已{'移除' if new_password is None else '修改'}: {os.path.basename(file_path)}"
        )
        return {"success": True, "error": None}

    # ── 关闭 ─────────────────────────────────────────────────────

    def close_file(self, file_path: str, save: bool = True):
        """关闭文件（从内存中移除）。

        Args:
            file_path: 文件路径
            save: 是否自动保存
        """
        if save and self.is_dirty(file_path):
            self.save_file(file_path)

        self.remove_from_project_tree(file_path)
        self._open_files.pop(file_path, None)
        self._tree_nodes.pop(file_path, None)

        if self._active_file == file_path:
            self._active_file = None
            # 找下一个活动文件
            if self._open_files:
                self._active_file = next(iter(self._open_files))

        _monitor('variable_watch', f'close_file: {os.path.basename(file_path)}')

    def close_all(self, save: bool = True):
        """关闭所有文件。"""
        _monitor('function_watch', f'close_all: {len(self._open_files)} files, save={save}')
        for file_path in list(self._open_files.keys()):
            self.close_file(file_path, save=save)
        _monitor('variable_watch', f'close_all: done, {len(self._open_files)} files remaining')

    def remove_file(self, file_path: str):
        """从管理器中完全移除文件（不保存）。"""
        _monitor('function_watch', f'remove_file: {os.path.basename(file_path)}')
        self._open_files.pop(file_path, None)
        self.remove_from_project_tree(file_path)
        self._tree_nodes.pop(file_path, None)
        remove_file_from_index(file_path)

        _monitor('variable_watch', f'remove_file: {os.path.basename(file_path)} fully removed')

        if self._active_file == file_path:
            self._active_file = None
            if self._open_files:
                self._active_file = next(iter(self._open_files))

    # ── 启动时自动加载 ───────────────────────────────────────────

    def auto_load_saved_files(self):
        """启动时自动加载索引中所有已保存的 .stardebate 文件。"""
        index = load_index()
        files = index.get("files", [])
        if not files:
            return

        _monitor('function_watch', f'auto_load_saved_files: {len(files)} files in index')

        for entry in files:
            file_path = entry.get("path", "")
            if not file_path or not os.path.isfile(file_path):
                _monitor('api_watch', f'auto_load: 跳过不存在的文件 {file_path}')
                continue

            result = self.open_file_with_stored_password(file_path)
            if result["success"]:
                _monitor('api_watch', f'auto_load: 成功加载 {os.path.basename(file_path)}')
            else:
                error = result.get("error", "未知错误")
                _monitor('api_watch', f'auto_load: 加载失败 {os.path.basename(file_path)} → {error}')
                # 密码错误的文件保留索引但跳过（用户可手动重新导入）
                if error != "PASSWORD_REQUIRED":
                    pass  # 保留在索引中

    # ── 项目树点击处理 ───────────────────────────────────────────

    def on_stardebate_node_clicked(self, item: QTreeWidgetItem):
        """处理项目树中 .stardebate 节点的点击事件。

        Args:
            item: 点击的树节点
        """
        node_type = item.data(0, Qt.UserRole + 1)
        file_path = item.data(0, Qt.UserRole + 2)

        # 自动展开 STDB 面板
        self._auto_show_panel()

        if node_type == "STARDEBATE":
            self._active_file = file_path
            if self._module_panel:
                self._module_panel.show_file(file_path)
            self._mw._update_status(f"已选择: {os.path.basename(file_path)}")

        elif node_type == "STARDEBATE_MODULE":
            module_id = item.data(0, Qt.UserRole + 3)
            self._active_file = file_path
            if self._module_panel:
                self._module_panel.show_file(file_path)
            self.open_module_editor(file_path, module_id)

    def _auto_show_panel(self):
        """自动展开 STDB 面板（如果当前隐藏）。"""
        mw = self._mw
        if not mw._stdb_browser_visible:
            mw._stdb_browser_visible = True
            if self._module_panel:
                self._module_panel.setVisible(True)
                self._module_panel.refresh_file_list()
            mw.btn_toggle_stdb_browser.setChecked(True)
            _monitor('function_watch', 'stdb: panel auto-opened on tree click')

    def open_module_editor(self, file_path: str, module_id: str):
        """打开模块对应的编辑器并注入数据。

        Args:
            file_path: .stardebate 文件路径
            module_id: 模块 ID
        """
        _monitor('function_watch', f'open_module_editor: {module_id}')

        mw = self._mw
        modules = self._open_files.get(file_path, {}).get("modules", {})
        module_data = modules.get(module_id)
        if module_data is None:
            _monitor('api_watch', f'open_module_editor: 模块数据不存在 {module_id}')
            return

        page_idx = get_page_index(module_id)

        # ── 根据模块类型注入数据到对应的编辑器 ──
        if module_id == "basic":
            mw.current_debate_data = module_data
            mw.current_debate_path = file_path
            mw._display_debate(file_path, module_data)
            _monitor('variable_watch', f'open_module_editor: basic → centre_stack[1]')

        elif module_id in ("speech_pro", "speech_con"):
            side = "pro" if "pro" in module_id else "con"
            try:
                mw._speech_mgr.load_stardebate_data(side, module_data)
                _monitor('variable_watch',
                         f'open_module_editor: {module_id} → speech_editor '
                         f'({len(module_data.get("content",""))} chars)')
            except Exception as e:
                _monitor('api_watch', f'open_module_editor: 加载辩稿失败 → {e}')

        elif module_id in ("ref_doc_pro", "ref_doc_con"):
            rows = module_data.get("rows", [])
            mw._ref_doc_mgr.ref_doc_rows = rows if isinstance(rows, list) else []
            mw._ref_doc_mgr._refresh_ref_doc_table()
            mw.centre_stack.setCurrentIndex(4)
            mw._ref_doc_mgr._current_stdeb_side = "pro" if "pro" in module_id else "con"
            _monitor('variable_watch',
                     f'open_module_editor: {module_id} → ref_doc ({len(rows)} rows)')

        elif module_id in ("analysis_pro", "analysis_con"):
            try:
                mw._analysis_mgr.display_analysis(module_data)
                _monitor('variable_watch', f'open_module_editor: {module_id} → analysis')
            except Exception:
                mw.centre_stack.setCurrentIndex(3)

        elif module_id == "framework":
            try:
                mw._framework_mgr.load_stardebate_data(module_data)
                _monitor('variable_watch',
                         f'open_module_editor: framework → centre_stack[8] '
                         f'({len(module_data)} nodes)')
            except Exception:
                mw.centre_stack.setCurrentIndex(8)

        elif module_id == "cross_exam":
            try:
                mw._cross_mgr.load_stardebate_data(module_data)
                _monitor('variable_watch', f'open_module_editor: cross_exam → centre_stack[6]')
            except Exception:
                mw.centre_stack.setCurrentIndex(6)

        elif module_id in ("accept_exam_pro", "accept_exam_con"):
            try:
                mw._accept_mgr.load_stardebate_data(module_data)
                _monitor('variable_watch', f'open_module_editor: {module_id} → centre_stack[7]')
            except Exception:
                mw.centre_stack.setCurrentIndex(7)

        elif module_id == "training":
            try:
                if hasattr(mw._train_mgr, 'load_stardebate_data'):
                    mw._train_mgr.load_stardebate_data(module_data)
                else:
                    mw.centre_stack.setCurrentIndex(9)
                _monitor('variable_watch', f'open_module_editor: training → centre_stack[9]')
            except Exception:
                mw.centre_stack.setCurrentIndex(9)

        elif module_id == "structure":
            try:
                mw._structure_mgr.load_data(module_data)
                _monitor('variable_watch', f'open_module_editor: structure → left panel')
            except Exception:
                pass

        elif module_id == "notes":
            mw.centre_stack.setCurrentIndex(1)
            _monitor('variable_watch', f'open_module_editor: notes → centre_stack[1]')

        else:
            # 默认显示在详情页
            mw.centre_stack.setCurrentIndex(1)

        self._mw._update_status(f"已打开模块: {get_module_label(module_id)} [{os.path.basename(file_path)}]")
