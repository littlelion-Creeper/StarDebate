# StarDebate 插件 API
# 提供给插件调用的安全接口，所有操作都是只读或受限的。
# 该 API 实例由主窗口在初始化时注入。
# 位置：workers/plugin_manager/plugin_api.py

import json
import os
import copy
import shutil

from components.popup_dialog import CustomDialog

# 延迟导入（避免启动时的循环依赖）
def _get_mgr():
    from workers.plugin_manager import get_manager
    return get_manager()


# ════════════════════════════════════════════════════════════
#  权限系统定义
# ════════════════════════════════════════════════════════════

PERMISSION_DEFS = {
    "file_read": {
        "level": "safe",
        "description": "读取项目目录外的文件",
        "explain": "允许插件读取辩论项目文件和资料池（默认）",
    },
    "file_write": {
        "level": "dangerous",
        "description": "写入项目目录外的文件",
        "explain": "允许插件创建、修改、删除项目目录外的文件",
    },
    "network": {
        "level": "dangerous",
        "description": "发起网络请求",
        "explain": "允许插件自行发起 HTTP/HTTPS 网络请求",
    },
    "ai_api": {
        "level": "safe",
        "description": "调用 AI 接口",
        "explain": "允许插件使用 StarDebate 的 AI 功能（由用户 API Key 控制成本）",
    },
    "settings_read": {
        "level": "safe",
        "description": "读取全局配置",
        "explain": "允许插件读取 StarDebate 的系统配置和 API 配置",
    },
    "settings_write": {
        "level": "medium",
        "description": "修改全局配置",
        "explain": "允许插件修改 StarDebate 的系统设置",
    },
}

# 权限级别映射（用于 UI 展示排序和风险标记）
PERMISSION_LEVEL_ORDER = {
    "safe": 0,
    "medium": 1,
    "dangerous": 2,
}


class PermissionError(RuntimeError):
    """插件权限不足时抛出的异常。"""
    pass


class PluginSafeAPI:
    """
    安全的插件 API，暴露给插件的方法在此定义。
    原则：
      - 所有方法只读或通过安全的钩子操作
      - 不允许插件直接修改主体代码文件
      - 插件崩溃不会影响主体运行

    权限系统（v1.0.0 新增）：
      - 插件在 plugin.json 的 permissions 中声明所需权限
      - 安装时预览窗口展示权限列表供用户确认
      - 运行时敏感 API 方法自动检查权限
      - 缺少权限时抛出 PermissionError 或返回错误结果
    """

    def __init__(self):
        self._main_window = None
        self._plugin_id = ""
        self._permissions: list[str] = []  # 当前插件声明的权限列表

    def set_context(self, main_window, plugin_id: str, permissions: list[str] | None = None):
        """由管理器调用，设置当前插件的上下文"""
        self._main_window = main_window
        self._plugin_id = plugin_id
        if permissions is not None:
            self._permissions = list(permissions)
        else:
            self._permissions = []

    def set_permissions(self, permissions: list[str]):
        """设置当前插件的权限列表（由管理器在启用时注入）。"""
        self._permissions = list(permissions)

    def get_permissions(self) -> list[str]:
        """获取当前插件声明的权限列表。"""
        return list(self._permissions)

    @staticmethod
    def get_all_permission_defs() -> dict:
        """获取所有可用的权限定义（只读常量）。"""
        return dict(PERMISSION_DEFS)

    def _check_permission(self, perm: str, method_name: str = "") -> bool:
        """检查当前插件是否有指定权限。无权限时记录监视日志并返回 False。

        兼容旧插件：空权限列表（未声明）视为全部允许。
        """
        # 空权限列表 = 旧式插件/无声明，向后兼容
        if not self._permissions:
            return True
        granted = perm in self._permissions
        try:
            from workers.debug_console.debug_monitor_manager import DebugMonitorManager
            mgr = DebugMonitorManager.instance()
            if mgr:
                if not granted and mgr.is_monitor_enabled("plugin_watch"):
                    mgr.log_plugin_status(
                        self._plugin_id, "permission_denied",
                        f"缺少权限 '{perm}'，方法: {method_name or '未知'}"
                    )
                if mgr.is_monitor_enabled("api_watch"):
                    status = "granted" if granted else "denied"
                    mgr._emit_monitor_log(
                        "api_watch",
                        f"[PluginPermission] {self._plugin_id} {status}: "
                        f"{perm} in {method_name or '未知'}"
                    )
        except Exception:
            pass
        return granted

    def _check_permission_or_raise(self, perm: str, method_name: str = ""):
        """检查权限，不足时抛出 PermissionError。"""
        if not self._check_permission(perm, method_name):
            def_info = PERMISSION_DEFS.get(perm, {})
            raise PermissionError(
                f"插件 '{self._plugin_id}' 缺少必要权限 '{perm}'"
                f"（{def_info.get('description', '')}）。"
                f"请在 plugin.json 中添加 \"{perm}\" 到 permissions 数组后重新安装。"
            )

    @property
    def mw(self):
        """获取主窗口引用（受限访问）"""
        return self._main_window

    # ============================================================
    #  基本信息
    # ============================================================

    def get_app_version(self) -> str:
        """获取 StarDebate 版本号，从 config/config.json 读取"""
        try:
            from workers.app_config.config_paths import get_config_path
            import json as _json
            config_path = get_config_path("config/config.json")
            if os.path.isfile(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    data = _json.load(f)
                return data.get("version", "1.0.0")
        except Exception:
            pass
        return "1.0.0"

    def get_current_project_path(self) -> str | None:
        """获取当前打开的项目路径"""
        return self.mw._get_current_project_path()

    # ============================================================
    #  辩论数据（只读）
    # ============================================================

    def get_debate_info(self) -> dict:
        """获取当前辩论基本信息"""
        return {
            "title": getattr(self.mw, "_debate_title", ""),
            "pro_side": getattr(self.mw, "_pro_side", "正方"),
            "con_side": getattr(self.mw, "_con_side", "反方"),
        }

    def get_speech_content(self, side: str = "pro") -> str:
        """获取一方的一辩稿内容"""
        editor = getattr(self.mw, f"edit_{side}_speech", None)
        if editor:
            return editor.toPlainText()
        return ""

    def get_analysis_result(self, side: str = "pro") -> dict:
        """获取 AI 分析结果"""
        attr = f"_analysis_{side}_data"
        return getattr(self.mw, attr, {})

    def get_notes(self) -> list:
        """获取便签列表（只读副本）"""
        data = getattr(self.mw, "_notes_data", [])
        return list(data)

    def get_ref_doc_data(self, side: str = "pro") -> list:
        """获取资料稿数据（全部行）"""
        mgr = getattr(self.mw, "_ref_doc_mgr", None)
        if mgr:
            return list(mgr.ref_doc_rows)
        return []

    # ============================================================
    #  资料稿查询（v1.4.0 新增）
    # ============================================================

    _COL_NAME_MAP = {
        "argument": 0, "论证观点": 0, "viewpoint": 0, "观点": 0, "论点": 0,
        "content": 1, "论证内容": 1, "detail": 1, "内容": 1,
        "source": 2, "资料来源": 2, "ref": 2, "来源": 2,
    }

    def _get_col_index(self, col: int | str) -> int | None:
        if isinstance(col, int):
            return col if 0 <= col <= 2 else None
        if isinstance(col, str):
            return self._COL_NAME_MAP.get(col, None)
        return None

    def _get_col_name(self, index: int) -> str:
        mapping = {0: "argument", 1: "content", 2: "source"}
        return mapping.get(index, "")

    def query_ref_doc_cells(
        self,
        rows: int | list[int] | None = None,
        cols: int | str | list[int | str] | None = None,
    ) -> dict:
        """按指定行和/或列查询资料稿单元格内容。"""
        mgr = getattr(self.mw, "_ref_doc_mgr", None)
        all_rows = list(mgr.ref_doc_rows) if mgr else []

        if rows is None:
            selected_indices = list(range(len(all_rows)))
        elif isinstance(rows, int):
            selected_indices = [rows]
        elif isinstance(rows, list):
            selected_indices = [r for r in rows if isinstance(r, int)]
        else:
            selected_indices = []

        col_identifiers = [0, 1, 2]
        if cols is not None:
            if not isinstance(cols, list):
                cols = [cols]
            mapped = []
            for c in cols:
                idx = self._get_col_index(c)
                if idx is not None:
                    mapped.append(idx)
            if mapped:
                col_identifiers = mapped

        col_names = [self._get_col_name(i) for i in col_identifiers]

        result_rows = []
        for idx in selected_indices:
            if 0 <= idx < len(all_rows):
                row_data = all_rows[idx]
                cells = [row_data.get(cn, "") for cn in col_names]
                result_rows.append(cells)

        return {
            "columns": col_names,
            "rows": result_rows,
            "row_count": len(result_rows),
            "col_count": len(col_names),
        }

    def search_ref_doc(
        self,
        keyword: str,
        cols: int | str | list[int | str] | None = None,
        case_sensitive: bool = False,
    ) -> list:
        """按关键词搜索资料稿表格内容，返回匹配的行及命中位置。"""
        mgr = getattr(self.mw, "_ref_doc_mgr", None)
        all_rows = list(mgr.ref_doc_rows) if mgr else []

        if not keyword:
            return []

        cn_name_map = {0: "论证观点", 1: "论证内容", 2: "资料来源"}

        if cols is None:
            col_indices = [0, 1, 2]
        else:
            if not isinstance(cols, list):
                cols = [cols]
            col_indices = []
            for c in cols:
                idx = self._get_col_index(c)
                if idx is not None:
                    col_indices.append(idx)
            if not col_indices:
                col_indices = [0, 1, 2]

        search_key = keyword if case_sensitive else keyword.lower()
        results = []

        for row_idx, row_data in enumerate(all_rows):
            for col_idx in col_indices:
                col_key = self._get_col_name(col_idx)
                cell_text = row_data.get(col_key, "")
                test_text = cell_text if case_sensitive else cell_text.lower()
                if search_key in test_text:
                    results.append({
                        "row_index": row_idx,
                        "match_column": col_key,
                        "match_column_cn": cn_name_map.get(col_idx, ""),
                        "cell_text": cell_text,
                        "full_row": dict(row_data),
                    })

        return results

    # ============================================================
    #  API 配置（只读）
    # ============================================================

    def get_api_config(self) -> dict:
        """获取 API 配置（屏蔽 Key）"""
        self._check_permission_or_raise("settings_read", "get_api_config")
        config = self.mw._load_api_config()
        masked = dict(config)
        if "api_key" in masked:
            masked["api_key"] = masked["api_key"][:4] + "****" if masked["api_key"] else ""
        return masked

    # ============================================================
    #  赛制参数（v1.6.0 新增）
    # ============================================================

    def get_all_competition_formats(self) -> dict:
        """获取所有赛制参数（预设 + 自定义），返回完整赛制数据。

        返回: dict 结构:
            {
                "presets": [ {...}, ... ],   # 预设赛制列表（5个）
                "custom":  [ {...}, ... ],   # 自定义赛制列表
                "total_count": int           # 赛制总数
            }

        每个赛制 dict 字段:
            - name (str): 赛制名称
            - type (str): "preset" | "custom"
            - team_size (int): 每方人数
            - positions (list): 辩位列表，每项 {"name": str, "phases": [{"name": str, "duration": int, "counterpart": str|null}, ...]}
            - free_debate (dict|null): 自由辩论，{"name": str, "duration": int, "counterpart": str, "description": str|null} 或 null

        示例:
            formats = api.get_all_competition_formats()
            for fmt in formats["presets"]:
                print(f"预设: {fmt['name']}, {fmt['team_size']}人/方")
            for fmt in formats["custom"]:
                print(f"自定义: {fmt['name']}")
        """
        from workers.tournament import COMPETITION_PRESETS

        presets = []
        for name, data in COMPETITION_PRESETS.items():
            fmt = {"name": name, "type": "preset"}
            fmt.update(data)
            presets.append(fmt)

        mgr = getattr(self.mw, "_tournament_mgr", None)
        custom = []
        if mgr:
            for fmt in list(mgr.competition_formats):
                c = {"name": fmt.get("name", "未命名"), "type": "custom"}
                c.update({k: v for k, v in fmt.items() if k != "type"})
                custom.append(c)

        return {
            "presets": presets,
            "custom": custom,
            "total_count": len(presets) + len(custom),
        }

    def get_current_debate_format(self) -> dict:
        """获取当前选中辩论文件的赛制参数。

        返回: dict 结构:
            {
                "format": dict | None,     # 赛制数据（同 get_all_competition_formats 中的单个赛制结构），无赛制时为 None
                "debate_path": str | None, # 当前辩论文件路径，未打开辩论时为 None
                "has_format": bool         # 是否已指定赛制
            }

        示例:
            current = api.get_current_debate_format()
            if current["has_format"]:
                fmt = current["format"]
                api.update_status(f"当前赛制: {fmt['name']}（{fmt['team_size']}人/方，{len(fmt['positions'])}辩位）")
            else:
                api.update_status("当前辩论未指定赛制")
        """
        debate_data: dict | None = getattr(self.mw, "current_debate_data", None)
        debate_path: str | None = getattr(self.mw, "current_debate_path", None)

        fmt: dict | None = None
        if debate_data and isinstance(debate_data.get("format"), dict):
            fmt = dict(debate_data["format"])

        return {
            "format": fmt,
            "debate_path": debate_path,
            "has_format": fmt is not None and bool(fmt.get("name")),
        }

    # ============================================================
    #  框架/结构化数据
    # ============================================================

    def get_framework_data(self) -> list:
        """获取当前已加载的辩论框架节点列表（内存数据）。"""
        mgr = getattr(self.mw, "_framework_mgr", None)
        if mgr:
            return list(mgr.data)
        return []

    def get_speech_framework_params(self, side: str = "pro") -> dict:
        """获取当前选中一辩稿文件的框架参数。

        从一辩稿 JSON 文件中读取已保存的辩论框架数据，
        返回完整的节点树形结构和按类型汇总的概要信息。

        Args:
            side: 辩方，"pro"（正方，默认）或 "con"（反方）

        Returns:
            dict:
                - speech_file (str|None): 一辩稿文件路径
                - has_framework (bool): 是否包含框架数据
                - nodes (list[dict]): 框架节点列表，每个节点含:
                    - id (int): 节点ID
                    - node_type (str): 节点类型 (position/definition/criterion/argument/evidence/value)
                    - type_label (str): 节点类型中文标签
                    - text (str): 节点文本内容
                    - x/y/width/height: 画布坐标
                    - children (list[int]): 子节点ID列表
                    - is_root (bool): 是否为根节点（无父节点）
                    - depth (int): 节点在树中的层级深度
                - node_count (int): 节点总数
                - summary (dict): 按节点类型汇总 {type_label: count}
                - node_types (dict): 节点类型定义 {type: {"label": str, "color": str}
                - root_nodes (list[dict]): 根节点列表（顶层节点）

        示例:
            params = api.get_speech_framework_params("pro")
            if params["has_framework"]:
                for node in params["root_nodes"]:
                    print(f"根节点: {node['type_label']} - {node['text']}")
                print(f"论点数量: {params['summary'].get('论点', 0)}")
                print(f"总节点: {params['node_count']}")
        """
        from workers.framework import FRAMEWORK_NODE_TYPES

        # 获取一辩稿文件路径
        speech_mgr = getattr(self.mw, "_speech_mgr", None)
        if speech_mgr:
            speech_file = speech_mgr.get_speech_filename(side)
        else:
            speech_file = None

        import os as _os
        import json as _json

        nodes = []
        if speech_file and _os.path.isfile(speech_file):
            try:
                with open(speech_file, "r", encoding="utf-8") as f:
                    data = _json.load(f)
                fw = data.get("framework", {})
                nodes = fw.get("nodes", [])
            except (_json.JSONDecodeError, OSError):
                nodes = []

        has_framework = bool(nodes)

        # 构建节点类型定义
        node_types = {
            ntype: {"label": label, "color": color}
            for ntype, (label, color) in FRAMEWORK_NODE_TYPES.items()
        }

        # 计算每个节点是否为根节点（不被任何其他节点作为 children 引用）
        all_ids = {n["id"] for n in nodes}
        child_ids = set()
        for n in nodes:
            for cid in n.get("children", []):
                child_ids.add(cid)
        root_ids = all_ids - child_ids

        # 计算节点深度
        id_to_node = {n["id"]: n for n in nodes}

        def calc_depth(node_id, visited=None):
            if visited is None:
                visited = set()
            if node_id in visited:
                return 0
            visited.add(node_id)
            for n in nodes:
                if node_id in n.get("children", []):
                    return calc_depth(n["id"], visited) + 1
            return 0  # 根节点

        # 丰富节点信息
        enriched_nodes = []
        summary = {}
        for n in nodes:
            ntype = n.get("node_type", "argument")
            type_label = FRAMEWORK_NODE_TYPES.get(ntype, ("❓ 未知", "#ffffff"))[0]
            node_id = n["id"]
            enriched = {
                "id": node_id,
                "node_type": ntype,
                "type_label": type_label,
                "text": n.get("text", ""),
                "x": n.get("x", 0),
                "y": n.get("y", 0),
                "width": n.get("width", 160),
                "height": n.get("height", 52),
                "children": list(n.get("children", [])),
                "is_root": node_id in root_ids,
                "depth": calc_depth(node_id),
            }
            enriched_nodes.append(enriched)
            # 汇总计数（用中文标签）
            cn_label = type_label.split(" ", 1)[-1] if " " in type_label else type_label
            summary[cn_label] = summary.get(cn_label, 0) + 1

        # 根节点列表
        root_nodes = [n for n in enriched_nodes if n["is_root"]]

        return {
            "speech_file": speech_file,
            "has_framework": has_framework,
            "nodes": enriched_nodes,
            "node_count": len(enriched_nodes),
            "summary": summary,
            "node_types": node_types,
            "root_nodes": root_nodes,
        }

    def get_structure_data(self) -> dict:
        return getattr(self.mw, "_struct_data", {})

    def get_keywords(self, side: str = "pro") -> list:
        attr = f"_keywords_{side}"
        return list(getattr(self.mw, attr, []))

    # ============================================================
    #  UI 操作（安全限制内）
    # ============================================================

    def update_status(self, message: str):
        self.mw._update_status(f"[{self._plugin_id}] {message}")

    # ============================================================
    #  自定义提示弹窗
    # ============================================================

    def show_notification(self, title: str, message: str):
        """弹出信息通知弹窗（info 类型，单确定按钮）。
        已有 API，保持向后兼容。"""
        from components.popup_dialog import CustomDialog
        CustomDialog.information(self.mw, title, message)

    def show_dialog(
        self,
        dialog_type: str = "info",
        title: str = "提示",
        message: str = "",
        buttons: list | None = None,
        checkbox: str = "",
    ) -> str:
        """弹出自定义对话框，返回用户点击的按钮标识符。

        支持五种类型，可自定义按钮文字和可选复选框。

        Args:
            dialog_type: 弹窗类型："info"（信息）/ "warning"（警告）/
                         "error"（错误）/ "question"（询问）/ "custom"（自定义）
            title: 标题栏文字
            message: 消息内容文本（支持换行）
            buttons: 按钮列表 [(文字, 标识符), ...]。
                     默认 [("确定", "ok")]，末位按钮高亮为主按钮。
            checkbox: 可选复选框文字（空字符串=不显示）

        Returns:
            str: 用户点击的按钮标识符（如 "ok"、"cancel"、"yes" 等）

        Example:
            result = api.show_dialog("question", "确认删除",
                "确定要删除这条记录吗？此操作不可恢复。",
                buttons=[("取消", "cancel"), ("删除", "delete")])
            if result == "delete":
                # 执行删除
                pass
        """
        from components.popup_dialog import CustomDialog
        if buttons is None:
            buttons = [("确定", "ok")]
        dlg = CustomDialog(self.mw, dialog_type, title, message, buttons, checkbox)
        dlg.exec_()
        return dlg.clicked_button

    def show_warning(
        self,
        title: str = "警告",
        message: str = "",
        buttons: list | None = None,
        checkbox: str = "",
    ) -> str:
        """弹出警告弹窗（warning 类型 + ⚠ 图标）。

        Args:
            title: 标题栏文字
            message: 消息内容文本
            buttons: 按钮列表，默认 [("确定", "ok")]
            checkbox: 可选复选框文字

        Returns:
            str: 用户点击的按钮标识符

        Example:
            api.show_warning("导入失败",
                "文件格式不支持，请使用 .json 或 .csv 格式。")
        """
        return self.show_dialog("warning", title, message, buttons, checkbox)

    def show_error(
        self,
        title: str = "错误",
        message: str = "",
        buttons: list | None = None,
        checkbox: str = "",
    ) -> str:
        """弹出错误弹窗（error 类型 + ✕ 图标）。

        Args:
            title: 标题栏文字
            message: 消息内容文本
            buttons: 按钮列表，默认 [("确定", "ok")]
            checkbox: 可选复选框文字

        Returns:
            str: 用户点击的按钮标识符

        Example:
            api.show_error("AI 调用失败",
                "无法连接到 API 服务器，请检查网络连接。")
        """
        return self.show_dialog("error", title, message, buttons, checkbox)

    def show_question(
        self,
        title: str = "确认",
        message: str = "",
        buttons: list | None = None,
        checkbox: str = "",
    ) -> str:
        """弹出询问确认弹窗（question 类型 + ? 图标）。

        默认提供「取消」和「确定」两个按钮。

        Args:
            title: 标题栏文字
            message: 消息内容文本
            buttons: 按钮列表，默认 [("取消", "cancel"), ("确定", "ok")]
            checkbox: 可选复选框文字

        Returns:
            str: 用户点击的按钮标识符

        Example:
            result = api.show_question("覆盖文件",
                "目标文件已存在，是否覆盖？")
            if result == "ok":
                # 执行覆盖
                pass
        """
        if buttons is None:
            buttons = [("取消", "cancel"), ("确定", "ok")]
        return self.show_dialog("question", title, message, buttons, checkbox)

    def show_confirm(
        self,
        title: str = "确认",
        message: str = "",
        ok_text: str = "确定",
        cancel_text: str = "取消",
        checkbox: str = "",
    ) -> bool:
        """弹出确认操作弹窗，直接返回 True/False。

        Args:
            title: 标题栏文字
            message: 消息内容文本
            ok_text: 确认按钮文字（默认"确定"）
            cancel_text: 取消按钮文字（默认"取消"）
            checkbox: 可选复选框文字

        Returns:
            bool: 用户点击确认按钮返回 True，否则 False

        Example:
            if api.show_confirm("删除项目", "确定要删除当前项目吗？",
                               ok_text="删除", cancel_text="取消"):
                # 执行删除
                pass
        """
        result = self.show_question(
            title, message,
            buttons=[(cancel_text, "cancel"), (ok_text, "ok")],
            checkbox=checkbox,
        )
        return result == "ok"

    def navigate_to_page(self, page_index: int):
        centre = getattr(self.mw, "centre_stack", None)
        if centre and 0 <= page_index < centre.count():
            centre.setCurrentIndex(page_index)

    def read_file_in_project(self, relative_path: str) -> str | None:
        self._check_permission_or_raise("file_read", "read_file_in_project")
        project_path = self.get_current_project_path()
        if not project_path:
            return None
        full_path = os.path.join(project_path, relative_path)
        if not full_path.startswith(project_path):
            return None
        if os.path.exists(full_path) and os.path.isfile(full_path):
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return None
        return None

    def write_file_in_project(self, relative_path: str, content: str) -> bool:
        self._check_permission_or_raise("file_write", "write_file_in_project")
        project_path = self.get_current_project_path()
        if not project_path:
            return False
        full_path = os.path.join(project_path, relative_path)
        if not full_path.startswith(project_path):
            return False
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception:
            return False

    # ============================================================
    #  导航按钮注册
    # ============================================================

    def register_nav_button(self, side: str, emoji: str, label: str, tooltip: str, callback):
        """在侧边导航栏注册一个按钮。插件启用时显示，禁用时自动消失。"""
        mgr = _get_mgr()
        mgr.register_nav_button(self._plugin_id, side, emoji, label, tooltip, callback)

    # ============================================================
    #  顶部导航栏按钮注册（v2.2.0 新增）
    # ============================================================

    def register_top_nav_button(self, text: str, tooltip: str, callback,
                                 btn_id: str = "", emoji: str = ""):
        """在顶部导航栏的插件区注册一个按钮。插件启用时显示，禁用时自动消失。

        Args:
            text: 按钮显示文字（如 "📊 统计"）
            tooltip: 鼠标悬停提示
            callback: 点击回调函数（无参数）
            btn_id: 按钮唯一ID（可选，默认自动生成）
            emoji: 按钮图标（可选，已包含在 text 中时可不传）
        """
        mgr = _get_mgr()
        btn_id = btn_id or f"btn_{len(mgr.get_plugin(self._plugin_id).top_nav_buttons) if mgr.get_plugin(self._plugin_id) else 0}"
        display_text = f"{emoji} {text}" if emoji and not text.startswith(emoji) else text
        mgr.register_top_nav_button(self._plugin_id, btn_id, display_text, tooltip, callback)

    def register_top_nav_sub_menu(self, parent_menu_id: str, text: str, callback,
                                   sub_id: str = ""):
        """在顶部导航栏指定菜单按钮下注册一个子菜单项。

        Args:
            parent_menu_id: 父菜单按钮ID（如 "file_menu"、"edit_menu"、"view_menu"）
            text: 子菜单显示文字（如 "📤 导出数据"）
            callback: 点击回调函数（无参数）
            sub_id: 子项唯一ID（可选）
        """
        mgr = _get_mgr()
        sub_id = sub_id or f"sub_{len(mgr.get_plugin(self._plugin_id).top_nav_sub_menus) if mgr.get_plugin(self._plugin_id) else 0}"
        mgr.register_top_nav_sub_menu(self._plugin_id, parent_menu_id, sub_id, text, callback)

    # ============================================================
    #  面板注册（插件可创建主界面功能区）
    # ============================================================

    def register_panel(self, side: str, title: str, emoji: str, tooltip: str, create_widget,
                       *, icon: str = "", min_width: int = None, max_width: int = None,
                       width_ratio: float = None):
        """在主界面注册一个功能面板。

        Args:
            side: "left" / "right" / "center"
            title: 面板名称（2-3字最佳）
            emoji: 导航按钮 emoji 图标
            tooltip: 鼠标悬停提示文本
            create_widget: 无参回调，返回 QWidget
            icon: 图标文件名（如 "panel.svg"），自动从 plugins/<plugin_id>/ 查找
            min_width: 面板最小宽度（px），默认 280
            max_width: 面板最大宽度（px），默认 480
            width_ratio: 占可用空间比例（0.0~1.0），默认 0.35
        """
        mgr = _get_mgr()
        mgr.register_panel(self._plugin_id, side, title, emoji, tooltip, create_widget,
                            icon=icon, min_width=min_width, max_width=max_width,
                            width_ratio=width_ratio)

    def get_panel_size(self, panel_title: str = None, panel_index: int = 0) -> dict | None:
        """获取插件自己功能区的实时大小。

        插件可通过此方法获取自己注册的面板的当前宽度和高度，
        用于响应式布局、动态调整UI等场景。

        Args:
            panel_title: 面板标题（注册时填写的 title），与 panel_index 二选一。
            panel_index: 面板索引（当插件注册多个面板时，0 表示第一个），
                         仅在 panel_title 为 None 时生效。

        Returns:
            dict | None: 包含大小信息的字典:
                {
                    "width": int,         # 面板当前宽度（像素）
                    "height": int,        # 面板当前高度（像素）
                    "panel_title": str,   # 面板标题
                    "visible": bool,      # 面板当前是否可见
                    "is_created": bool,  # 面板是否已创建（widget 实例是否存在）
                }
            面板不存在返回 None；面板未创建时 width 为预期最小宽度，height 为 0。

        Example:
            # 获取第一个面板的实时大小
            info = api.get_panel_size()
            if info and info['is_created']:
                print(f"面板: {info['width']}x{info['height']}px, 可见={info['visible']}")

            # 根据面板宽度切换布局
            if info and info['width'] < 300:
                use_compact_layout()
            else:
                use_full_layout()

            # 按标题获取指定面板
            info = api.get_panel_size(panel_title="数据面板")
        """
        mgr = _get_mgr()
        if not mgr:
            return None

        info = mgr._plugins.get(self._plugin_id)
        if not info or not info.panels:
            return None

        # 根据 panel_title 或 panel_index 选择面板
        target_panel = None
        if panel_title is not None:
            for p in info.panels:
                if p.get("title") == panel_title:
                    target_panel = p
                    break
        else:
            if 0 <= panel_index < len(info.panels):
                target_panel = info.panels[panel_index]

        if not target_panel:
            return None

        widget = target_panel.get("widget")
        result = {
            "panel_title": target_panel.get("title", ""),
            "is_created": widget is not None,
            "visible": False,
        }

        if widget is not None:
            result["width"] = widget.width()
            result["height"] = widget.height()
            result["visible"] = widget.isVisible()
        else:
            result["width"] = target_panel.get("min_width", 280)
            result["height"] = 0

        # 监视钩子（API 监视）
        try:
            from workers.debug_console.debug_monitor_manager import DebugMonitorManager
            dmgr = DebugMonitorManager.instance()
            if dmgr.is_monitor_enabled("api_watch"):
                tag = result["panel_title"] or f"index={panel_index}"
                dmgr._log_mgr.info(
                    f"[API] get_panel_size(plugin={self._plugin_id}, "
                    f"panel={tag}) -> {result['width']}x{result['height']}, "
                    f"visible={result['visible']}"
                )
        except Exception:
            pass

        return result

    # ============================================================
    #  设置页注册
    # ============================================================

    def register_settings_page(self, meta: dict, create_widget_fn=None,
                               collect_config_fn=None):
        """在设置对话框中注册一个设置页。"""
        mgr = _get_mgr()
        page_id = meta.get("id", self._plugin_id + "_settings")
        mgr.register_settings_page(
            self._plugin_id, page_id, meta,
            create_widget_fn, collect_config_fn
        )

    # ============================================================
    #  训练子功能注册（v2.1.0）
    # ============================================================

    def register_training_sub_feature(self, info: dict, manager_class) -> bool:
        """在「模拟训练」面板中注册一个子功能（入口卡片 + 子页面）。

        插件启用时调用一次，禁用/删除时自动清理。

        Args:
            info: 子功能元信息字典，必需字段：
                - id (str): 唯一标识（仅限本插件内唯一，系统自动加插件前缀）
                - name (str): 入口卡片标题
                - icon (str): 图标 emoji
                - description (str): 卡片描述文字
                - order (int): 排序（越小越靠前，建议 50+ 避免与内置功能重叠）
                可选字段：
                - accent_color (str): 标题 CSS 颜色，默认 "#f9e2af"
                - tags (list[str]): 特性标签
                - history_label (str): 标题栏历史按钮文字（如 "📂 记录"）
            manager_class: 管理器类，需实现：
                - __init__(self, train_mgr): train_mgr 为 TrainingManager 实例
                - build_pages(self, parent_stack: QStackedWidget) -> int: 构建子页面并返回起始索引
                - show_history(self): （可选）显示历史记录

        Returns:
            bool: 注册成功 True，失败 False

        Example:
            class MyTrainManager:
                def __init__(self, train_mgr):
                    self._tm = train_mgr
                    self._mw = train_mgr._mw

                def build_pages(self, parent_stack):
                    # 添加子页面到 parent_stack
                    return parent_stack.count() - 1

            api.register_training_sub_feature(
                {"id": "my_train", "name": "我的训练", "icon": "🔧",
                 "description": "自定义训练模式", "order": 100},
                MyTrainManager
            )
        """
        mgr = _get_mgr()
        return mgr.register_training_sub_feature(self._plugin_id, info, manager_class)

    # ============================================================
    #  Hook 注册
    # ============================================================

    def on(self, event: str, callback):
        """注册事件钩子"""
        mgr = _get_mgr()
        mgr.register_hook(event, callback)

    def off(self, event: str, callback):
        """取消事件钩子"""
        mgr = _get_mgr()
        mgr.unregister_hook(event, callback)

    # ============================================================
    #  控制台命令执行（v2.3.0 新增）
    # ============================================================

    def execute_command(self, cmd_line: str) -> dict:
        """在调试台控制台中执行一条内置命令，返回结果。

        插件可通过此 API 以编程方式运行 StarDebate 的内置控制台命令
        （如 version、status、plugin:list 等），并获取命令输出。

        Args:
            cmd_line: 要执行的命令字符串，如 "version"、"plugin:list"、"status"

        Returns:
            dict: {"success": bool, "output": str, "error": str}
                  - success: 命令是否执行成功
                  - output: 命令生成的输出文本（多条日志用换行拼接）
                  - error: 失败时的错误信息

        Example:
            result = api.execute_command("version")
            if result["success"]:
                print(f"版本信息: {result['output']}")

            # 列出所有插件
            result = api.execute_command("plugin:list")
            print(result["output"])
        """
        try:
            from workers.debug_console.command_handler import CommandHandler
            handler = CommandHandler()
            lines = []

            def log_collector(level, message):
                if level.startswith("__"):
                    return
                lines.append(f"[{level}] {message}")

            success = handler.execute(cmd_line, log_fn=log_collector, mw=self.mw)
            return {
                "success": success,
                "output": "\n".join(lines),
                "error": "" if success else f"未知命令: {cmd_line}",
            }
        except Exception as e:
            import traceback
            return {"success": False, "output": "", "error": str(e)}

    def log_monitor(self, monitor_type: str, message: str):
        """向调试监视管理器插入一条监视日志。

        如果对应监视类型已在调试台中开启，日志将出现在调试台的日志区。
        如果未开启，此调用无效果（不会产生任何输出）。

        Args:
            monitor_type: 监视类型，可选值:
                "variable_watch" — 变量监视（标签 [VAR]）
                "function_watch" — 函数监视（标签 [FUNC]）
                "plugin_watch"   — 插件监视（标签 [PLUGIN]）
                "api_watch"      — API 监视（标签 [API]）
                "ai_watch"       — AI 监视（标签 [AI]）
            message: 日志消息文本

        Example:
            api.log_monitor("plugin_watch", "自定义数据处理完成")
            api.log_monitor("ai_watch", "插件 AI 分析耗时 2.3s")
        """
        try:
            from workers.debug_console.debug_monitor_manager import DebugMonitorManager, MONITOR_TYPES
            if monitor_type not in MONITOR_TYPES:
                return
            mgr = DebugMonitorManager.instance()
            if mgr.is_monitor_enabled(monitor_type):
                mgr._emit_monitor_log(monitor_type, message)
        except Exception:
            pass

    def register_console_command(self, cmd_name: str, handler_fn,
                                   args_desc: str = "", description: str = "",
                                   category: str = "插件命令"):
        """注册一个插件自定义命令，用户可在调试台中运行。

        注册后，输入 help 将列出该命令，用户可在控制台直接输入命令名执行。
        命令处理函数接收参数字符串，可返回结果日志或使用 api.log_monitor 输出。

        Args:
            cmd_name: 命令名称（建议使用 "插件ID:命令" 命名，如 "timer:start"）
            handler_fn: 命令处理函数，签名为 (args: str) -> str | None
                        参数 args 是命令后的参数字符串
                        返回的字符串将作为 INFO 日志输出（返回 None 表示无输出）
            args_desc: 参数说明（如 "<秒数>"，显示在 help 中）
            description: 命令描述（显示在 help 中）
            category: 命令分类（显示在 help 中分组），默认 "插件命令"

        Example:
            def handle_timer_start(args):
                seconds = int(args) if args else 60
                api.log_monitor("plugin_watch", f"插件计时器启动: {seconds}s")
                return f"计时器已启动，{seconds} 秒"

            api.register_console_command(
                cmd_name="timer:start",
                handler_fn=handle_timer_start,
                args_desc="<秒数>",
                description="启动插件计时器",
                category="计时器"
            )
        """
        mgr = _get_mgr()
        mgr.register_console_command(
            self._plugin_id, cmd_name, handler_fn,
            args_desc, description, category
        )

    # ============================================================
    #  快捷键注册（v3.0.0 新增）
    # ============================================================

    def register_shortcut(self, shortcut_id: str, keys: str, description: str,
                          callback, category: str = "插件快捷键"):
        """注册一个全局快捷键。插件启用时注册，禁用时自动清理。

        Args:
            shortcut_id: 唯一标识（建议 "插件ID:功能" 格式，如 "timer:start_pause"）
            keys: 默认组合键，如 "Ctrl+Shift+T"（用户可在设置中修改）
            description: 功能描述（如 "开始/暂停计时"）
            callback: 触发回调函数（无参数）
            category: 分类名（在设置页显示），默认 "插件快捷键"

        Example:
            api.register_shortcut(
                "timer:start_pause", "Ctrl+Shift+T",
                "开始/暂停计时", on_toggle_timer
            )
        """
        mgr = _get_mgr()
        mgr.register_shortcut(
            self._plugin_id, shortcut_id, keys,
            description, callback, category
        )

    def unregister_shortcuts(self):
        """注销此插件的所有快捷键（通常在 on_disable 中调用）"""
        mgr = _get_mgr()
        mgr.unregister_shortcuts(self._plugin_id)

    # ============================================================
    #  右键菜单项注册（v4.7.0 新增）
    # ============================================================

    def register_context_menu_item(self, label: str, callback, order: int = 100):
        """在项目浏览器的文件右键菜单中注册一个自定义菜单项。

        Args:
            label: 菜单显示文本（如 "添加到 Claw 会话"）
            callback: 回调函数，接收 file_path 参数
            order: 排序顺序（越小越靠前），默认 100
        """
        mgr = _get_mgr()
        mgr.register_context_menu_item(self._plugin_id, label, callback, order)

    # ============================================================
    #  自定义多选框（v2.4.0 新增）
    # ============================================================

    def create_checkbox(self, text: str = "", checked: bool = False,
                        checkbox_size: int = 20, object_name: str = ""):
        """创建一个 StarCheckBox 自定义多选框控件，替代 Qt 原生 QCheckBox。

        返回的控件可添加到插件的自定义面板中。支持 SVG 图标渲染、
        可调大小、三主题自适应、四态交互（Normal/Hover/Checked/Disabled）。

        Args:
            text: 标签文字
            checked: 初始选中状态
            checkbox_size: 图标像素大小（≥12px，文字字号自动跟随）
            object_name: QSS objectName（可选，默认 "starCheckBox"）

        Returns:
            StarCheckBox: 自定义多选框控件实例

        Signals (可直接 connect):
            - toggled(bool): 状态翻转时发射，参数为新状态
            - stateChanged(int): 状态改变时发射（0=未选中, 2=选中）
            - clicked(): 点击时发射

        Properties:
            - .checked (bool): 读写选中状态
            - .text_prop (str): 读写标签文字
            - .checkbox_size (int): 读写图标大小

        Example:
            def build_my_panel():
                panel = QWidget()
                layout = QVBoxLayout(panel)
                api = get_api()

                cb = api.create_checkbox("启用自动保存", checked=True,
                                          checkbox_size=22)
                cb.toggled.connect(lambda checked:
                    print(f"自动保存: {checked}"))
                layout.addWidget(cb)

                cb2 = api.create_checkbox("显示高级选项",
                                          checkbox_size=18)
                layout.addWidget(cb2)
                return panel
        """
        from components.star_checkbox import StarCheckBox
        return StarCheckBox(
            text=text, parent=None,
            checked=checked, checkbox_size=checkbox_size,
            object_name=object_name,
        )

    # ============================================================
    #  自定义数字输入框（v2.9.0 新增）
    # ============================================================

    def create_spinbox(self, value: int = 0, min_value: int = 0,
                       max_value: int = 99, step: int = 1,
                       prefix: str = "", suffix: str = "",
                       button_layout: str = "right",
                       spin_height: int = 32, button_width: int = 22,
                       editable: bool = True,
                       text_align: str = "left", font_size=None):
        """创建一个 StarSpinBox 自定义数字输入框控件，替代 Qt 原生 QSpinBox。

        支持 SVG 图标渲染、三种布局模式切换、长按自动重复、三主题自适应。

        Args:
            value: 初始值
            min_value: 最小值
            max_value: 最大值
            step: 步长
            prefix: 前缀（如 "$"）
            suffix: 后缀（如 " px"）
            button_layout: 布局模式 — "right"(默认)/"split"/"embedded"
            spin_height: 整体高度（≥24px）
            button_width: 按钮区宽度
            editable: 是否可直接编辑
            text_align: 文字对齐 — "left"/"center"/"right"
            font_size: 文字大小（None=自动, int=固定 ≥10px）

        Returns:
            StarSpinBox: 自定义整数输入框控件实例

        Signals:
            - valueChanged(int): 值变化时发射
            - editingFinished(): 编辑完成时发射

        Example:
            def build_my_panel():
                panel = QWidget()
                layout = QVBoxLayout(panel)
                api = get_api()

                spin = api.create_spinbox(value=42, max_value=100,
                                          suffix=" 人")
                spin.valueChanged.connect(lambda v:
                    print(f"新值: {v}"))
                layout.addWidget(spin)
                return panel
        """
        from components.star_spinbox import StarSpinBox
        return StarSpinBox(
            parent=None, value=value, min_value=min_value,
            max_value=max_value, step=step,
            prefix=prefix, suffix=suffix,
            button_layout=button_layout,
            spin_height=spin_height, button_width=button_width,
            editable=editable,
            text_align=text_align, font_size=font_size,
        )

    def create_double_spinbox(self, value: float = 0.0, min_value: float = 0.0,
                              max_value: float = 99.0, step: float = 1.0,
                              decimals: int = 2,
                              prefix: str = "", suffix: str = "",
                              button_layout: str = "right",
                              spin_height: int = 32, button_width: int = 22,
                              editable: bool = True,
                              text_align: str = "left", font_size=None):
        """创建一个 StarDoubleSpinBox 自定义浮点数输入框，替代 Qt 原生 QDoubleSpinBox。

        Args:
            value: 初始值
            min_value: 最小值
            max_value: 最大值
            step: 步长
            decimals: 小数位数
            prefix: 前缀
            suffix: 后缀
            button_layout: 布局模式 — "right"/"split"/"embedded"
            spin_height: 整体高度（≥24px）
            button_width: 按钮区宽度
            editable: 是否可直接编辑
            text_align: 文字对齐 — "left"/"center"/"right"
            font_size: 文字大小（None=自动, int=固定 ≥10px）

        Returns:
            StarDoubleSpinBox: 自定义浮点数输入框控件实例
        """
        from components.star_spinbox import StarDoubleSpinBox
        return StarDoubleSpinBox(
            parent=None, value=value, min_value=min_value,
            max_value=max_value, step=step, decimals=decimals,
            prefix=prefix, suffix=suffix,
            button_layout=button_layout,
            spin_height=spin_height, button_width=button_width,
            editable=editable,
            text_align=text_align, font_size=font_size,
        )

    # ============================================================
    #  自定义按钮（v1.0.0 新增）
    # ============================================================

    def create_button(
        self, text: str = "",
        *,
        icon=None, icon_size: int = 24,
        layout_mode: str = "h_left",
        text_vertical: bool = False,
        text_align="left",
        accent=None,
        ratio_mode: str = "sync",
        ratio_h: float = 0.8, ratio_v: float = 0.8,
        checkable: bool = False, checked: bool = False,
        auto_size: bool = True,
    ):
        """创建一个 StarButton 自定义按钮控件，替代 Qt 原生 QPushButton。

        支持 6 种排布模式、5 种占比模式、自动尺寸、竖排文字、可勾选、主题自适应绘制。

        Args:
            text: 按钮文字
            icon: 图标（QIcon/QPixmap/文件路径）
            icon_size: 图标边长（px）
            layout_mode: 排布模式 — "h_left"(默认)/"h_right"/"v_top"/"v_bottom"/"text_only"/"icon_only"
            text_vertical: 是否竖排文字
            text_align: 文字对齐 — "left"/"center"/"right"
            accent: 主题色 hex（如 "#89b4fa"），设置后按钮有实色背景
            ratio_mode: 占比模式 — "sync"(默认)/"hv"/"h_only"/"v_only"/"auto"
            ratio_h: 水平占比（0.3~0.9，默认 0.8）
            ratio_v: 垂直占比（0.3~0.9，默认 0.8）
            checkable: 是否可勾选（默认 False）
            checked: 初始勾选状态（默认 False）
            auto_size: 是否根据文字自动调整尺寸（默认 True）

        Returns:
            StarButton: 自定义按钮控件实例

        Signals (可直接 connect):
            - clicked(): 点击时发射
            - pressed(): 按下时发射
            - released(): 释放时发射
            - toggled(bool): checkable 模式下状态翻转

        Example:
            def build_my_panel():
                panel = QWidget()
                layout = QVBoxLayout(panel)
                api = get_api()

                # 基础按钮
                btn = api.create_button("搜索")
                btn.clicked.connect(lambda: print("搜索"))

                # 带主题色的保存按钮
                btn_save = api.create_button(
                    "保存", icon="icon/save.svg",
                    accent="#89b4fa", ratio_h=0.75,
                )
                layout.addWidget(btn_save)

                # 可勾选按钮
                btn_toggle = api.create_button("启用", checkable=True)
                btn_toggle.toggled.connect(
                    lambda chk: print(f"选中: {chk}")
                )
                layout.addWidget(btn_toggle)
                return panel
        """
        from components.star_button import StarButton
        from PyQt5.QtCore import Qt

        align_map = {
            "left": Qt.AlignLeft,
            "center": Qt.AlignCenter,
            "right": Qt.AlignRight,
        }
        return StarButton(
            text=text, parent=None,
            icon=icon, icon_size=icon_size,
            layout_mode=layout_mode,
            text_vertical=text_vertical,
            text_align=align_map.get(text_align, Qt.AlignLeft),
            accent=accent,
            ratio_mode=ratio_mode,
            ratio_h=ratio_h, ratio_v=ratio_v,
            checkable=checkable, checked=checked,
            auto_size=auto_size,
        )

    # ============================================================
    #  自定义 SVG 图标（v2.9.0 新增）
    #
    #  插件在 plugins/<id>/icons/ 下存放 SVG 文件，
    #  通过以下 API 按主题色渲染为 QPixmap / QIcon。
    # ============================================================

    def get_plugin_dir(self) -> str:
        """获取插件自身的文件夹路径。

        Returns:
            插件的完整目录路径（如 ``plugins/my_plugin/``）。
        """
        from components.res_path import get_resource_root
        return os.path.join(get_resource_root(), "plugins", self._plugin_id)

    def icon_path(self, name: str) -> str:
        """获取插件 icons/ 文件夹下 SVG 文件的完整路径。

        Args:
            name: SVG 文件名（如 ``"my_icon.svg"`` 或 ``"category/edit.svg"`` 子目录）。

        Returns:
            完整文件路径，如 ``plugins/my_plugin/icons/my_icon.svg``。
            若文件不存在，返回空字符串。
        """
        plugin_dir = self.get_plugin_dir()
        icon_dir = os.path.join(plugin_dir, "icons")
        full_path = os.path.join(icon_dir, name)
        if os.path.isfile(full_path):
            return os.path.normpath(full_path)
        # 回退：尝试不带 .svg 后缀
        if not name.endswith(".svg"):
            full_path_svg = os.path.join(icon_dir, name + ".svg")
            if os.path.isfile(full_path_svg):
                return os.path.normpath(full_path_svg)
        return ""

    def list_icons(self) -> list[str]:
        """列出插件 icons/ 文件夹下所有 SVG 文件（相对路径）。

        Returns:
            SVG 文件相对路径列表，如 ``["refresh.svg", "toolbar/edit.svg", ...]``。
        """
        plugin_dir = self.get_plugin_dir()
        icon_dir = os.path.join(plugin_dir, "icons")
        if not os.path.isdir(icon_dir):
            return []
        result = []
        for root, __dirs, files in os.walk(icon_dir):
            for f in files:
                if f.lower().endswith(".svg"):
                    rel = os.path.relpath(
                        os.path.join(root, f), icon_dir
                    ).replace("\\", "/")
                    result.append(rel)
        result.sort()
        return result

    def render_icon(self, name: str, size: int = 24,
                    color: str = None) -> 'QPixmap':
        """使用当前主题色渲染插件 icons/ 下的单色 SVG 图标。

        Args:
            name: SVG 文件名（如 ``"refresh.svg"`` 或 ``"category/filter.svg"``）。
            size: 图标边长（正方形像素）。
                    color: 主题色键名（如 ``"text"``, ``"accent_blue"``），
                   ``None`` 使用主题预设颜色。

        Returns:
            QPixmap。若文件不存在返回空的 QPixmap。
        """
        path = self.icon_path(name)
        if not path:
            from PyQt5.QtGui import QPixmap
            from PyQt5.QtCore import Qt
            pix = QPixmap(size, size)
            pix.fill(Qt.transparent)
            return pix
        from components.svg_renderer import SvgRenderer
        return SvgRenderer.icon(path, size, color=color)

    def render_bicolor_icon(self, name: str, size: int = 24,
                            primary: str = None, accent: str = None) -> 'QPixmap':
        """使用当前主题色渲染插件 icons/ 下的双色 SVG 图标。

        双色 SVG 需通过 ``data-color="primary"`` / ``data-color="accent"``
        属性标记区域，参见 §4.17c SVG 渲染器文档。

        Args:
            name: SVG 文件名。
            size: 图标边长。
            primary: 主色主题色键名（默认使用主题预设）。
            accent: 辅色主题色键名（默认使用主题预设）。

        Returns:
            QPixmap。
        """
        path = self.icon_path(name)
        if not path:
            from PyQt5.QtGui import QPixmap
            from PyQt5.QtCore import Qt
            pix = QPixmap(size, size)
            pix.fill(Qt.transparent)
            return pix
        from components.svg_renderer import SvgRenderer
        return SvgRenderer.bicolor(path, size, primary=primary, accent=accent)

    def create_icon_qicon(self, name: str, size: int = 24,
                          color: str = None, disabled_pct: float = 0.4) -> 'QIcon':
        """渲染插件 SVG 图标为 QIcon（含 Normal/Disabled 状态）。

        Args:
            name: SVG 文件名。
            size: 图标边长。
            color: 主题色键名（默认使用主题预设）。
            disabled_pct: Disabled 状态透明度（0.0–1.0）。

        Returns:
            QIcon，可直接用于 QPushButton.setIcon() 等。
        """
        path = self.icon_path(name)
        if not path:
            from PyQt5.QtGui import QIcon
            return QIcon()
        from components.svg_renderer import SvgRenderer
        return SvgRenderer.qicon(path, size, color=color, disabled_pct=disabled_pct)

    # ============================================================
    #  AI 调用（插件的核心能力）
    # ============================================================

    def call_ai(
        self,
        messages: list,
        system_prompt: str = "",
        model: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: int = 120
    ) -> str:
        """调用 AI 接口，返回 AI 回复文本。"""
        self._check_permission_or_raise("ai_api", "call_ai")
        import requests
        import traceback
        from workers.common.api_helper import monitored_api_post

        if not isinstance(messages, list) or len(messages) == 0:
            raise ValueError("messages 必须是非空列表")

        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise ValueError(f"messages[{i}] 必须是字典")
            if "role" not in msg or "content" not in msg:
                raise ValueError(f"messages[{i}] 必须包含 'role' 和 'content'")

        config = self.mw._load_api_config()
        api_url = config.get("api_url", "")
        api_key = config.get("api_key", "")
        if not api_url or not api_key:
            raise RuntimeError("API 未配置。请在 StarDebate 设置中配置 API URL 和 Key。")

        built_messages = []
        if system_prompt:
            built_messages.append({"role": "system", "content": system_prompt})
        built_messages.extend(messages)

        max_tokens = max(1, min(max_tokens, 16384))
        temperature = max(0.0, min(temperature, 2.0))
        timeout = max(10, min(timeout, 300))

        payload = {
            "model": model or config.get("model", "deepseek-chat"),
            "messages": built_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        try:
            self.mw._update_status(f"[{self._plugin_id}] AI 请求中...")
            resp, __elapsed = monitored_api_post(
                {"api_url": api_url, "api_key": api_key}, payload,
                timeout=timeout, feature_name=f"plugin:{self._plugin_id}"
            )

            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                self.mw._update_status(f"[{self._plugin_id}] AI 响应完成")
                return content
            else:
                err_detail = ""
                try:
                    err_detail = str(resp.json())[:300]
                except Exception:
                    err_detail = resp.text[:300]
                raise RuntimeError(
                    f"API 返回错误 (HTTP {resp.status_code}): {err_detail}"
                )

        except requests.exceptions.Timeout:
            raise RuntimeError(f"AI 请求超时 ({timeout}s)，请增加 timeout 参数或检查网络")
        except requests.exceptions.ConnectionError:
            raise RuntimeError("无法连接到 API 服务器，请检查 API URL 和网络")
        except RuntimeError:
            raise
        except Exception as e:
            traceback.print_exc()
            raise RuntimeError(f"AI 调用异常: {str(e)}")

    # ============================================================
    #  .stardebate 编辑器 API（v2.7.0 新增）
    #
    #  提供插件对 .stardebate 加密文件的只读查询和受控操作。
    #  所有 get_/list_ 方法返回深拷贝，插件无法污染内存数据。
    #  密码 API 不暴露明文，仅返回状态 bool。
    # ============================================================

    # ── 模块注册表（只读常量）────────────────────────────────────

    @property
    def STDB_MODULE_IDS(self) -> dict:
        """.stardebate 模块注册表：module_id → (page_index, label, icon)。

        插件可通过此表了解文件内包含哪些模块类型。
        """
        try:
            from workers.stardebate_format.stardebate_editor_manager import MODULE_REGISTRY
            return dict(MODULE_REGISTRY)
        except ImportError:
            return {}

    def get_stdb_module_label(self, module_id: str) -> str:
        """获取模块的中文名称。"""
        try:
            from workers.stardebate_format.stardebate_editor_manager import get_module_label
            return get_module_label(module_id)
        except ImportError:
            return module_id

    # ── 文件管理 ─────────────────────────────────────────────────

    def open_stdb_file(self, file_path: str, password: str | None = None) -> dict:
        """打开 .stardebate 文件（解密到内存）。

        Args:
            file_path: .stardebate 文件的绝对路径
            password: 用户密码（有密码保护时必须提供）

        Returns:
            {"success": bool, "error": str|None,
             "meta": {"uuid": str, "module_count": int, "has_password": bool, ...}
        """
        try:
            mw = self.mw
            if not mw or not hasattr(mw, '_stdb_editor_mgr') or not mw._stdb_editor_mgr:
                return {"success": False, "error": ".stardebate 编辑器未初始化", "meta": {}}

            mgr = mw._stdb_editor_mgr
            result = mgr.open_file(file_path, password=password)
            return {"success": result["success"],
                    "error": result.get("error"),
                    "meta": result.get("meta", {})}
        except Exception as e:
            return {"success": False, "error": str(e), "meta": {}}

    def close_stdb_file(self, file_path: str, save: bool = True) -> dict:
        """关闭 .stardebate 文件（从内存移除）。

        Args:
            file_path: 文件路径
            save: 关闭前是否自动保存

        Returns:
            {"success": bool, "error": str|None}
        """
        try:
            mw = self.mw
            if not mw or not hasattr(mw, '_stdb_editor_mgr') or not mw._stdb_editor_mgr:
                return {"success": False, "error": "编辑器未初始化"}
            mgr = mw._stdb_editor_mgr
            if file_path not in mgr.open_files:
                return {"success": False, "error": "文件未打开"}
            mgr.close_file(file_path, save=save)
            return {"success": True, "error": None}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_stdb_file(self, file_path: str, password: str | None = None) -> dict:
        """加密保存 .stardebate 文件到磁盘。

        Args:
            file_path: 文件路径
            password: 新密码（None 表示使用原密码）

        Returns:
            {"success": bool, "error": str|None}
        """
        try:
            mw = self.mw
            if not mw or not hasattr(mw, '_stdb_editor_mgr') or not mw._stdb_editor_mgr:
                return {"success": False, "error": "编辑器未初始化"}
            mgr = mw._stdb_editor_mgr
            if file_path not in mgr.open_files:
                return {"success": False, "error": "文件未打开"}
            return mgr.save_file(file_path, password=password)
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 只读查询 ─────────────────────────────────────────────────

    def list_stdb_open_files(self) -> list[str]:
        """获取所有已打开的 .stardebate 文件路径列表。"""
        try:
            mw = self.mw
            if not mw or not hasattr(mw, '_stdb_editor_mgr') or not mw._stdb_editor_mgr:
                return []
            return list(mw._stdb_editor_mgr.open_files.keys())
        except Exception:
            return []

    def get_stdb_file_info(self, file_path: str) -> dict:
        """获取 .stardebate 文件的元信息（只读）。

        Returns:
            {"path": str, "uuid": str, "version": int, "has_password": bool,
             "module_count": int, "module_ids": [str, ...],
             "dirty_modules": [str, ...], "created": float, "app_version": str}
            文件未打开返回空 dict。
        """
        try:
            mw = self.mw
            if not mw or not hasattr(mw, '_stdb_editor_mgr') or not mw._stdb_editor_mgr:
                return {}
            mgr = mw._stdb_editor_mgr
            data = mgr.open_files.get(file_path)
            if not data:
                return {}
            meta = data.get("meta", {})
            modules = data.get("modules", {})
            return {
                "path": file_path,
                "uuid": meta.get("debate_uuid", ""),
                "version": meta.get("version", 1),
                "has_password": meta.get("has_password", False),
                "module_count": len(modules),
                "module_ids": list(modules.keys()),
                "dirty_modules": sorted(mgr.get_dirty_modules(file_path)),
                "created": meta.get("created", 0),
                "app_version": meta.get("app_version", ""),
            }
        except Exception:
            return {}

    def list_stdb_module_ids(self, file_path: str) -> list[str]:
        """获取文件中所有模块 ID 列表。

        Returns:
            ["basic", "speech_pro", "speech_con", ...]  文件未打开返回 []。
        """
        try:
            mw = self.mw
            if not mw or not hasattr(mw, '_stdb_editor_mgr') or not mw._stdb_editor_mgr:
                return []
            mgr = mw._stdb_editor_mgr
            data = mgr.open_files.get(file_path)
            if not data:
                return []
            return list(data.get("modules", {}).keys())
        except Exception:
            return []

    def get_stdb_module_data(self, file_path: str, module_id: str) -> dict | None:
        """获取模块数据（深拷贝，只读）。

        Returns:
            模块数据 dict，文件未打开或模块不存在返回 None。
        """
        try:
            import copy
            mw = self.mw
            if not mw or not hasattr(mw, '_stdb_editor_mgr') or not mw._stdb_editor_mgr:
                return None
            mgr = mw._stdb_editor_mgr
            data = mgr.get_module_data(file_path, module_id)
            if data is None:
                return None
            return copy.deepcopy(data)
        except Exception:
            return None

    def is_stdb_file_dirty(self, file_path: str) -> bool:
        """检查文件是否有未保存的修改。"""
        try:
            mw = self.mw
            if not mw or not hasattr(mw, '_stdb_editor_mgr') or not mw._stdb_editor_mgr:
                return False
            return mw._stdb_editor_mgr.is_dirty(file_path)
        except Exception:
            return False

    # ── 密码管理 ─────────────────────────────────────────────────

    def get_stdb_password_status(self, file_path: str) -> dict:
        """获取文件密码状态（不暴露明文）。

        Returns:
            {"has_password": bool, "is_unlocked": bool}
            has_password: 文件本身是否启用了密码保护
            is_unlocked: 当前是否已成功解密（已提供正确密码或无需密码）
        """
        try:
            mw = self.mw
            if not mw or not hasattr(mw, '_stdb_editor_mgr') or not mw._stdb_editor_mgr:
                return {"has_password": False, "is_unlocked": False}
            mgr = mw._stdb_editor_mgr
            data = mgr.open_files.get(file_path)
            if not data:
                return {"has_password": False, "is_unlocked": False}
            meta = data.get("meta", {})
            return {
                "has_password": meta.get("has_password", False),
                "is_unlocked": True,  # 能打开说明已解密
            }
        except Exception:
            return {"has_password": False, "is_unlocked": False}

    def change_stdb_password(self, file_path: str, old_password: str,
                              new_password: str | None) -> dict:
        """修改或移除文件密码。

        Args:
            file_path: 文件路径
            old_password: 旧密码（验证用）
            new_password: 新密码，None 表示移除密码保护

        Returns:
            {"success": bool, "error": str|None}
        """
        try:
            mw = self.mw
            if not mw or not hasattr(mw, '_stdb_editor_mgr') or not mw._stdb_editor_mgr:
                return {"success": False, "error": "编辑器未初始化"}
            mgr = mw._stdb_editor_mgr
            if file_path not in mgr.open_files:
                return {"success": False, "error": "文件未打开"}
            return mgr.change_password(file_path, old_password, new_password)
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ════════════════════════════════════════════════════════════
    #  资料池 API（v4.0.0 新增）
    # ════════════════════════════════════════════════════════════

    def _get_material_pool(self):
        """惰性获取 MaterialPoolManager"""
        mw = getattr(self, '_main_window', None)
        if not mw: return None
        return getattr(mw, '_material_pool_mgr', None)

    # ── 搜索查询 ──

    def search_pool(self, keyword: str, sources: list = None,
                    limit: int = 20) -> list:
        """在资料池中搜索关键词（本地BM25 + 异步AI精排）"""
        try:
            pool = self._get_material_pool()
            if not pool: return []
            return pool.search(keyword, sources, limit)
        except Exception: return []

    def search_local(self, keyword: str, sources: list = None,
                     limit: int = 20) -> list:
        """仅执行本地BM25搜索（快速）"""
        try:
            pool = self._get_material_pool()
            if not pool: return []
            return pool.search_local(keyword, sources, limit)
        except Exception: return []

    def get_search_history(self, limit: int = 10) -> list:
        """获取搜索历史"""
        try:
            pool = self._get_material_pool()
            if not pool: return []
            return copy.deepcopy(
                getattr(pool, '_search_history', [])[-limit:])
        except Exception: return []

    # ── 文件管理 ──

    def import_file(self, source_path: str) -> dict:
        """将外部文件导入资料池"""
        self._check_permission_or_raise("file_write", "import_file")
        try:
            if not os.path.isfile(source_path):
                return {"success": False, "error": "文件不存在", "file_info": None}
            ext = os.path.splitext(source_path)[1].lower()
            # 获取项目路径
            project_path = self.get_current_project_path()
            if not project_path:
                return {"success": False, "error": "请先打开项目", "file_info": None}
            pool_dir = os.path.join(project_path, "data_pool")
            os.makedirs(pool_dir, exist_ok=True)
            dest = os.path.join(pool_dir, os.path.basename(source_path))
            import shutil
            shutil.copy2(source_path, dest)
            pool = self._get_material_pool()
            if pool: pool.notify_file_added(dest)
            return {"success": True, "error": None,
                    "file_info": {"name": os.path.basename(dest),
                                  "type": ext,
                                  "size": os.path.getsize(dest)}}
        except Exception as e:
            return {"success": False, "error": str(e), "file_info": None}

    def list_files(self, recursive: bool = True) -> list:
        """列出资料池文件"""
        try:
            pool = self._get_material_pool()
            if not pool: return []
            return copy.deepcopy(pool.list_files(recursive))
        except Exception: return []

    def get_file_content(self, relative_path: str) -> str:
        """获取文件文本内容"""
        try:
            if ".." in relative_path: return None
            pool = self._get_material_pool()
            if not pool: return None
            return pool.get_file_text(relative_path)
        except Exception: return None

    def delete_file(self, relative_path: str) -> dict:
        """从资料池删除文件"""
        self._check_permission_or_raise("file_write", "delete_file")
        try:
            project_path = self.get_current_project_path()
            if not project_path: return {"success": False, "error": "无项目"}
            if ".." in relative_path: return {"success": False, "error": "非法路径"}
            fp = os.path.join(project_path, "data_pool", relative_path)
            if not fp.startswith(os.path.join(project_path, "data_pool")):
                return {"success": False, "error": "路径越权"}
            if not os.path.isfile(fp): return {"success": False, "error": "文件不存在"}
            os.remove(fp)
            pool = self._get_material_pool()
            if pool: pool.notify_file_removed(relative_path)
            return {"success": True, "error": None}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_pool_size(self) -> dict:
        """获取资料池统计"""
        try:
            pool = self._get_material_pool()
            if not pool: return {"file_count": 0, "total_size": 0,
                                  "type_counts": {}, "indexed": False}
            return copy.deepcopy(pool.get_stats())
        except Exception:
            return {"file_count": 0, "total_size": 0,
                    "type_counts": {}, "indexed": False}

    # ── AI 分析 ──

    def summarize_document(self, relative_path: str) -> dict:
        """AI摘要文档"""
        self._check_permission_or_raise("ai_api", "summarize_document")
        try:
            if ".." in relative_path:
                return {"success": False, "summary": None,
                        "key_points": [], "keywords": [], "error": "非法路径"}
            pool = self._get_material_pool()
            if not pool:
                return {"success": False, "summary": None,
                        "key_points": [], "keywords": [], "error": "资料池未就绪"}
            return pool.summarize_file(relative_path)
        except Exception as e:
            return {"success": False, "summary": None,
                    "key_points": [], "keywords": [], "error": str(e)}

    def ai_search(self, pool_results: list) -> list:
        """AI语义精排搜索结果"""
        try:
            pool = self._get_material_pool()
            if not pool: return copy.deepcopy(pool_results)
            return pool.ai_rerank(pool_results[:5])
        except Exception: return copy.deepcopy(pool_results)

    def get_ai_analysis_status(self) -> dict:
        """获取AI分析状态"""
        try:
            pool = self._get_material_pool()
            if not pool: return {"is_running": False, "progress": 0,
                                  "queued": 0, "completed": 0, "error": None}
            return {"is_running": getattr(pool, '_ai_searching', False),
                    "progress": getattr(pool, '_ai_analysis_progress', 0),
                    "queued": getattr(pool, '_ai_completed', 0),
                    "completed": getattr(pool, '_ai_completed', 0),
                    "error": getattr(pool, '_ai_last_error', None)}
        except Exception:
            return {"is_running": False, "progress": 0,
                    "queued": 0, "completed": 0, "error": None}

    # ── 导出 ──

    def export_summary(self, results: list = None, fmt: str = "md") -> dict:
        """导出搜索结果汇总"""
        try:
            pool = self._get_material_pool()
            if not pool: return {"success": False, "path": None, "error": "资料池未就绪"}
            path = pool.export_results(results, fmt)
            if path: return {"success": True, "path": path, "error": None}
            return {"success": False, "path": None, "error": "导出失败"}
        except Exception as e:
            return {"success": False, "path": None, "error": str(e)}

    def export_to_stardebate(self, file_path: str,
                              results: list = None) -> dict:
        """导出到.stardebate加密包"""
        self._check_permission_or_raise("file_write", "export_to_stardebate")
        try:
            pool = self._get_material_pool()
            if not pool: return {"success": False, "error": "资料池未就绪"}
            ok = pool.export_to_stdb(file_path, results)
            return {"success": ok, "error": None if ok else "导出失败"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 索引管理 ──

    def rebuild_index(self) -> dict:
        """重建资料池搜索索引"""
        try:
            pool = self._get_material_pool()
            if not pool: return {"success": False, "file_count": 0, "error": "资料池未就绪"}
            pool._rebuild_index()
            return {"success": True, "file_count": len(pool._file_list), "error": None}
        except Exception as e:
            return {"success": False, "file_count": 0, "error": str(e)}

    def get_index_status(self) -> dict:
        """获取索引状态"""
        try:
            pool = self._get_material_pool()
            if not pool:
                return {"ready": False, "total_files": 0, "indexed_files": 0,
                        "last_rebuilt": "", "index_version": 0}
            return {"ready": getattr(pool, '_index_ready', False),
                    "total_files": len(getattr(pool, '_file_list', [])),
                    "indexed_files": len(getattr(pool, '_index_data', {}).get("files", {})),
                    "last_rebuilt": ""}
        except Exception:
            return {"ready": False, "total_files": 0, "indexed_files": 0,
                    "last_rebuilt": "", "index_version": 0}

    def pool_is_ready(self) -> bool:
        """资料池是否可用"""
        try:
            s = self.get_index_status()
            return s.get("ready", False) and s["total_files"] > 0
        except Exception: return False

    # ── 信息 ──

    def get_pool_info(self) -> dict:
        """获取资料池基本信息"""
        try:
            pool = self._get_material_pool()
            pp = self.get_current_project_path() or ""
            dp = os.path.join(pp, "data_pool") if pp else ""
            api_key = self.get_api_config().get("api_key", "")
            return {"name": "资料池", "path": dp,
                    "open": bool(pool and pool.visible) if pool else False,
                    "file_count": len(getattr(pool, '_file_list', [])) if pool else 0,
                    "search_count": len(getattr(pool, '_search_history', [])) if pool else 0,
                    "has_ai": bool(api_key)}
        except Exception:
            return {"name": "", "path": "", "open": False, "file_count": 0,
                    "search_count": 0, "has_ai": False}

    def is_pool_open(self) -> bool:
        """资料池面板是否打开"""
        try:
            pool = self._get_material_pool()
            return bool(pool and pool.visible)
        except Exception: return False

    def get_supported_extensions(self) -> list:
        """获取支持的文件扩展名"""
        return [".md", ".txt", ".pdf", ".docx", ".xlsx", ".csv",
                ".json", ".html"]

    # ============================================================
    #  撤销栈注册（v1.6.0 新增）
    # ============================================================

    def register_undo_stack(self, stack):
        """注册插件的 QUndoStack 到撤销协调器。

        插件面板被激活时，「编辑」菜单的撤销/重做将自动绑定到此栈。

        Args:
            stack: QUndoStack 实例

        注意事项：
          - 应在插件 on_enable 或面板 build 时调用
          - 在 on_disable 时调用 unregister_undo_stack() 注销

        Example:
            from PyQt5.QtWidgets import QUndoStack
            stack = QUndoStack()
            api.register_undo_stack(stack)
            # 将文本编辑操作包装为 QUndoCommand 并 push 到 stack 中
        """
        from components.undo_coordinator import UndoCoordinator
        UndoCoordinator.instance().register_plugin_stack(self._plugin_id, stack)

    def unregister_undo_stack(self):
        """注销插件的 QUndoStack。

        应在插件 on_disable 时调用，避免无效引用。
        """
        from components.undo_coordinator import UndoCoordinator
        UndoCoordinator.instance().unregister_plugin_stack(self._plugin_id)

    def activate_undo_stack(self):
        """激活插件的撤销栈（面板切换到插件时调用）。"""
        from components.undo_coordinator import UndoCoordinator
        UndoCoordinator.instance().set_active_plugin_panel(self._plugin_id)

