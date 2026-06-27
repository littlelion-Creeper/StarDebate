# StarDebate 插件管理器
# 提供插件的加载、卸载、隔离运行等功能
# 位置：workers/plugin_manager/ — 插件框架核心代码
# 插件实体统一存放在 plugins/ 目录

import os
import sys
import json
import time
import types
import importlib.util
import traceback
import weakref
from typing import Any, Callable

from workers.app_config.config_paths import get_config_path

try:
    from sip import isdeleted as _sip_isdeleted
except ImportError:
    def _sip_isdeleted(obj):
        """fallback: PyQt6 / PySide 不支持 sip，直接返回 False"""
        return False

from components.res_path import get_resource_root

# 插件存放目录（所有插件统一存放于此）
PLUGIN_DIR = os.path.join(get_resource_root(), "plugins")

# 已安装插件清单
INSTALLED_JSON = get_config_path("config/installed_plugins.json")

# 安全的插件 API 引用（由主窗口注入）
_safe_api = None


def _monitor_log(status: str, name: str, detail: str = ""):
    """向 DebugMonitorManager 发送插件监视日志（惰性导入，避免循环依赖）。"""
    try:
        from workers.debug_console.debug_monitor_manager import DebugMonitorManager
        mgr = DebugMonitorManager.instance()
        if mgr.is_monitor_enabled("plugin_watch"):
            mgr.log_plugin_status(name, status, detail)
    except Exception:
        pass


def _install_function_hooks(module, module_name: str):
    """为插件模块的所有顶层函数安装 function_watch 监视钩子。

    仅在 function_watch 监视已开启时安装，否则跳过。
    钩子包装器记录函数调用名称、耗时、返回值或异常。
    """
    try:
        from workers.debug_console.debug_monitor_manager import DebugMonitorManager
        mgr = DebugMonitorManager.instance()
        if not mgr.is_monitor_enabled("function_watch"):
            return
    except Exception:
        return

    # 需要跳过的特殊名称（避免包装入口/生命周期方法导致递归）
    _SKIP = frozenset({"on_enable", "on_disable"})
    # 插件模块的全限定名（用于排除导入的外部函数）
    _module_qname = getattr(module, "__name__", "")

    for attr_name in list(module.__dict__):
        obj = module.__dict__[attr_name]
        if attr_name.startswith("_") or not isinstance(obj, types.FunctionType):
            continue
        # 排除从其他模块导入的函数（只 hook 插件自身定义的函数）
        if getattr(obj, "__module__", None) != _module_qname:
            continue
        original = obj

        def _make_wrapper(orig_fn, name):
            def wrapper(*args, **kwargs):
                t0 = time.perf_counter()
                try:
                    result = orig_fn(*args, **kwargs)
                    elapsed = (time.perf_counter() - t0) * 1000
                    try:
                        if mgr.is_monitor_enabled("function_watch"):
                            mgr.log_function_call(
                                module_name, name, True,
                                result=result, duration_ms=elapsed,
                            )
                    except Exception:
                        pass
                    return result
                except Exception as exc:
                    elapsed = (time.perf_counter() - t0) * 1000
                    try:
                        if mgr.is_monitor_enabled("function_watch"):
                            mgr.log_function_call(
                                module_name, name, False,
                                error=str(exc)[:200], duration_ms=elapsed,
                            )
                    except Exception:
                        pass
                    raise
            return wrapper

        module.__dict__[attr_name] = _make_wrapper(original, attr_name)


def set_api(api_instance):
    """由主窗口调用，注入安全的 API 实例"""
    global _safe_api
    _safe_api = api_instance


def get_api():
    """插件内部调用，获取安全 API"""
    return _safe_api


# ── 回调弱引用包装器 ──

def _make_weak_callback(callback: Callable) -> Callable | weakref.ref:
    """对回调进行弱引用包装。

    对于可弱引用的对象（方法、普通函数）返回 weakref 包装；
    lambda / 内置函数无法弱引用时回退为强引用（直接返回原函数）。
    调用方需通过 _call_weak_ref() 安全调用。
    """
    try:
        if isinstance(callback, types.MethodType):
            # 绑定方法 → WeakMethod
            return weakref.WeakMethod(callback)
        else:
            return weakref.ref(callback)
    except TypeError:
        # lambda / 内置函数等不可弱引用 → 保持原样（强引用）
        return callback


def _call_weak_ref(wrapped) -> Any | None:
    """安全调用被弱引用包装的回调。返回 None 表示回调已失效。"""
    if wrapped is None:
        return None
    if isinstance(wrapped, (weakref.ref, weakref.WeakMethod)):
        cb = wrapped()
        if cb is None:
            return None  # 已被 GC，回调失效
        return cb
    # 强引用（lambda 等）直接调用
    return wrapped


class PluginInfo:
    """单个插件的信息描述"""

    def __init__(self, plugin_id: str, manifest: dict):
        self.plugin_id = plugin_id
        self.name = manifest.get("name", plugin_id)
        self.version = manifest.get("version", "1.0.0")
        self.author = manifest.get("author", "未知")
        self.description = manifest.get("description", "")
        self.main_file = manifest.get("main", "main.py")
        self.enabled = manifest.get("enabled", True)
        self.config = manifest.get("config", {})
        self.permissions = manifest.get("permissions", [])  # v1.0.0 .stp 权限声明
        self._module = None
        self._instance = None
        self.nav_buttons: list[dict] = []  # [{side, icon, emoji, label, tooltip, callback}]
        self.panels: list[dict] = []  # [{side, icon, title, emoji, tooltip, create_widget, widget}]
        self.settings_pages: list[dict] = []  # [{page_id, meta, collect_config}]
        self.training_features: list[dict] = []  # [{feature_id, info}] 已注册的训练子功能
        self.top_nav_buttons: list[dict] = []  # [{id, text, tooltip, callback, area}] 顶部导航栏插件按钮
        self.top_nav_sub_menus: list[dict] = []  # [{id, parent_menu_id, text, callback}] 顶部菜单插件子项
        self.console_commands: list[dict] = []  # [{cmd, args, desc, cat, handler_fn}] 插件注册的控制台命令
        self.shortcut_ids: list[str] = []  # [shortcut_id, ...] 插件注册的快捷键 ID

    @property
    def folder(self) -> str:
        return os.path.join(PLUGIN_DIR, self.plugin_id)

    @property
    def manifest_path(self) -> str:
        return os.path.join(self.folder, "plugin.json")

    @property
    def settings_path(self) -> str:
        """获取插件的 settings.py 文件路径"""
        return os.path.join(self.folder, "settings.py")

    @property
    def has_settings(self) -> bool:
        """检查插件是否包含 settings.py 文件"""
        return os.path.isfile(self.settings_path)

    def load(self) -> bool:
        """加载插件模块（不执行初始化）。仅支持文件夹插件。"""
        if self._module is not None:
            return True  # 已加载
        main_path = os.path.join(self.folder, self.main_file)
        if not os.path.exists(main_path):
            _monitor_log("fail", self.name, f"未找到插件入口: {main_path}")
            print(f"[Plugin] 未找到插件入口: {main_path}")
            return False

        try:
            spec = importlib.util.spec_from_file_location(
                f"plugin_{self.plugin_id}", main_path
            )
            if spec is None or spec.loader is None:
                _monitor_log("fail", self.name, "spec/loader 为空")
                return False
            self._module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self._module)
            _install_function_hooks(self._module, self.plugin_id)
            _monitor_log("success", self.name)
            return True
        except Exception:
            err = traceback.format_exc().split("\n")[-2] if traceback.format_exc() else "未知错误"
            _monitor_log("fail", self.name, err.strip() if err else "加载异常")
            print(f"[Plugin] 加载插件 '{self.name}' 失败:")
            traceback.print_exc()
            self._module = None
            return False

    def _auto_register_settings(self):
        """自动扫描并注册插件的 settings.py 设置页"""
        if not self.has_settings:
            return
        try:
            spec = importlib.util.spec_from_file_location(
                f"plugin_settings_{self.plugin_id}", self.settings_path
            )
            if spec is None or spec.loader is None:
                return
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            page_info = getattr(mod, "PAGE_INFO", None)
            if page_info is None:
                print(f"[Plugin] 插件 '{self.name}' 的 settings.py 缺少 PAGE_INFO")
                return

            page_config = getattr(mod, "PAGE_CONFIG", None) or {}
            meta = dict(page_info)
            meta["page_config"] = page_config

            # 注册到全局注册表（通过 PluginManager）
            page_id = f"plugin_{self.plugin_id}_settings"
            get_manager().register_settings_page(
                self.plugin_id, page_id, meta,
                module_path=self.settings_path
            )
        except Exception:
            print(f"[Plugin] 自动注册插件 '{self.name}' 设置页失败:")
            traceback.print_exc()

    def enable(self):
        """启用插件。失败时自动回滚 enabled 状态。"""
        if not self.load():
            _monitor_log("fail", self.name, "模块加载失败 → 自动标记 disabled")
            self.enabled = False
            return False
        try:
            if hasattr(self._module, "on_enable"):
                # 清除旧的导航按钮和面板注册，防止反复开关导致重复累积
                self.nav_buttons.clear()
                self.panels.clear()
                self.settings_pages.clear()
                self.top_nav_buttons.clear()
                self.top_nav_sub_menus.clear()
                self.console_commands.clear()
                self.shortcut_ids.clear()  # ★ v3.0.0: 快捷键注册表
                # 在调用 on_enable 前设置 API 的 plugin_id 和 permissions
                prev_id = _safe_api._plugin_id if _safe_api else ""
                if _safe_api:
                    _safe_api._plugin_id = self.plugin_id
                    _safe_api.set_permissions(self.permissions)
                self._module.on_enable()
                if _safe_api:
                    _safe_api._plugin_id = prev_id

            # 自动扫描并注册 settings.py 设置页
            self._auto_register_settings()

            self.enabled = True
            _monitor_log("enabled", self.name)
            return True
        except Exception:
            err = traceback.format_exc().split("\n")[-2] if traceback.format_exc() else "未知错误"
            _monitor_log("fail", self.name, f"on_enable 异常: {err.strip() if err else ''} → 自动标记 disabled")
            print(f"[Plugin] 启用插件 '{self.name}' 失败:")
            traceback.print_exc()
            self.enabled = False
            return False

    def disable(self):
        """禁用插件"""
        try:
            if self._module and hasattr(self._module, "on_disable"):
                self._module.on_disable()
        except Exception:
            traceback.print_exc()
        self.enabled = False
        _monitor_log("disabled", self.name)

    def _destroy_widgets(self):
        """销毁插件已创建的所有面板 widget（先隐藏，延迟删除避免崩溃）。"""
        count = 0
        for p in self.panels:
            w = p.get("widget")
            if w is not None and not _sip_isdeleted(w):
                try:
                    w.hide()
                    w.deleteLater()
                    count += 1
                except Exception:
                    pass
                p["widget"] = None
        # 清空所有注册列表中的 widget 引用
        self.panels.clear()
        _monitor_log("info", self.name, f"销毁 {count} 个面板 widget")

    def unload(self):
        """完全卸载插件：禁用 → 销毁 UI → 释放模块 → 清除 sys.modules 缓存"""
        self.disable()
        # 销毁所有面板 widget
        self._destroy_widgets()
        # 释放模块和实例引用
        self._instance = None
        mod_ref = self._module
        self._module = None
        # 从 sys.modules 中清除缓存，确保下次 load() 真正重新执行
        cleared_keys = []
        if mod_ref is not None:
            for key in list(sys.modules.keys()):
                if key == f"plugin_{self.plugin_id}" or key == f"plugin_settings_{self.plugin_id}":
                    sys.modules.pop(key, None)
                    cleared_keys.append(key)
        _monitor_log("unloaded", self.name, f"sys.modules 已清除: {cleared_keys}")

    def get_config(self) -> dict:
        """获取插件配置（从 manifest 读取最新）"""
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                self.config = manifest.get("config", {})
            except Exception:
                pass
        return self.config

    def save_config(self, config: dict):
        """保存插件配置"""
        self.config = config
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                manifest["config"] = config
                with open(self.manifest_path, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[Plugin] 保存插件配置失败: {e}")

    def call(self, method_name: str, *args, **kwargs) -> Any:
        """安全调用插件的指定方法，捕获所有异常"""
        if not self._module:
            return None
        try:
            func = getattr(self._module, method_name, None)
            if func and callable(func):
                return func(*args, **kwargs)
        except Exception:
            print(f"[Plugin] 插件 '{self.name}' 方法 '{method_name}' 调用异常:")
            traceback.print_exc()
        return None


class PluginManager:
    """插件管理器：负责加载、卸载、管理所有插件"""

    def __init__(self):
        self._plugins: dict[str, PluginInfo] = {}
        self._hook_listeners: dict[str, list[Callable]] = {}
        self._context_menu_items: list[dict] = []  # [{plugin_id, label, callback, order}]
        os.makedirs(PLUGIN_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(INSTALLED_JSON), exist_ok=True)
        self._load_installed_list()

    # ── 列表管理 ──

    def _load_installed_list(self):
        """从 installed_plugins.json 加载已安装插件清单（不自动启用，等 API 注入后再启用）"""
        if os.path.exists(INSTALLED_JSON):
            try:
                with open(INSTALLED_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    pid = item.get("id", "")
                    if pid:
                        manifest = self._read_manifest(pid)
                        if manifest:
                            manifest["enabled"] = item.get("enabled", True)
                            info = PluginInfo(pid, manifest)
                            self._plugins[pid] = info
            except Exception as e:
                print(f"[Plugin] 加载插件清单失败: {e}")

        # 自动发现：扫描 plugins/ 目录中未注册的文件夹
        self._discover_unregistered()

    def _discover_unregistered(self):
        """扫描 plugins/ 目录，自动注册未被 installed.json 记录的插件文件夹"""
        if not os.path.isdir(PLUGIN_DIR):
            return
        skip_names = {"__pycache__"}
        try:
            for entry in os.listdir(PLUGIN_DIR):
                entry_path = os.path.join(PLUGIN_DIR, entry)
                if os.path.isdir(entry_path) and entry not in skip_names \
                   and not entry.startswith(".") and entry not in self._plugins:
                    manifest = self._read_manifest(entry)
                    if manifest:
                        info = PluginInfo(entry, manifest)
                        self._plugins[entry] = info

            # 保存更新后的清单
            if len(self._plugins) > 0:
                self._save_installed_list()

        except Exception as e:
            print(f"[Plugin] 自动发现插件失败: {e}")

    def enable_all_default(self):
        """API 注入后调用，启用所有默认启用的插件"""
        for info in self._plugins.values():
            if info.enabled:
                self._safe_enable(info)

    def _save_installed_list(self):
        """保存已安装插件清单到 config/installed_plugins.json"""
        data = []
        for pid, info in self._plugins.items():
            data.append({"id": pid, "enabled": info.enabled})
        try:
            with open(INSTALLED_JSON, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Plugin] 保存插件清单失败: {e}")

    def _read_manifest(self, plugin_id: str) -> dict | None:
        """读取插件的 plugin.json 清单文件"""
        manifest_path = os.path.join(PLUGIN_DIR, plugin_id, "plugin.json")
        if not os.path.exists(manifest_path):
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _safe_enable(self, info: PluginInfo) -> bool:
        """安全地启用插件，捕获所有异常。返回是否成功。"""
        try:
            return info.enable()
        except Exception:
            print(f"[Plugin] 安全启用 '{info.name}' 失败:")
            traceback.print_exc()
            return False

    def _register_existing_plugin(self, name: str):
        """注册一个已存在于 plugins/ 目录但未注册的插件文件夹"""
        dest = os.path.join(PLUGIN_DIR, name)

        py_files = [f for f in os.listdir(dest) if f.endswith(".py") and not f.startswith("__")]
        if not py_files:
            return False, f"插件 \"{name}\" 文件夹中没有 Python 入口文件 (.py)"

        settings_file = os.path.join(dest, "settings.py")
        has_settings = os.path.isfile(settings_file)

        manifest = self._read_manifest(name)
        if manifest is None:
            main_file = py_files[0]
            for f in py_files:
                if f.lower() == "main.py":
                    main_file = f
                    break
            manifest = {
                "name": name,
                "version": "1.0.0",
                "author": "未知",
                "description": "从文件夹自动注册",
                "main": main_file,
                "enabled": True,
                "config": {},
            }
            with open(os.path.join(dest, "plugin.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

        info = PluginInfo(name, manifest)
        self._plugins[name] = info
        success = self._safe_enable(info)
        self._save_installed_list()

        if not has_settings:
            return True, f"插件 \"{name}\" 已注册（缺少 settings.py，无独立设置页）"
        return True, f"插件 \"{name}\" 自动注册成功"

    # ── 公开接口 ──

    def import_plugin(self, source_path: str):
        """导入插件（仅支持多文件文件夹插件）。返回 (success: bool, message: str)"""
        if not os.path.exists(source_path):
            return False, "源路径不存在"

        if not os.path.isdir(source_path):
            return False, "StarDebate 仅支持多文件文件夹插件，请选择插件文件夹（而非 .py 文件）"

        name = os.path.basename(source_path.rstrip("/\\"))
        if name in ("__init__", "__pycache__"):
            return False, f"不允许导入系统目录: {name}"
        dest = os.path.join(PLUGIN_DIR, name)

        if os.path.exists(dest):
            if name in self._plugins:
                return False, f"插件 \"{name}\" 已存在，请先删除再导入"
            return self._register_existing_plugin(name)

        import shutil
        try:
            shutil.copytree(source_path, dest)
        except Exception as e:
            return False, f"复制文件夹失败: {e}"

        py_files = [f for f in os.listdir(dest) if f.endswith(".py") and not f.startswith("__")]
        if not py_files:
            shutil.rmtree(dest, ignore_errors=True)
            return False, "插件文件夹中没有找到 Python 入口文件 (.py)"

        settings_file = os.path.join(dest, "settings.py")
        has_settings = os.path.isfile(settings_file)

        manifest = self._read_manifest(name)
        if manifest is None:
            main_file = py_files[0]
            for f in py_files:
                if f.lower() == "main.py":
                    main_file = f
                    break
            manifest = {
                "name": name,
                "version": "1.0.0",
                "author": "未知",
                "description": "",
                "main": main_file,
                "enabled": True,
                "config": {},
            }
            with open(os.path.join(dest, "plugin.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
        else:
            manifest["enabled"] = True

        info = PluginInfo(name, manifest)
        self._plugins[name] = info
        self._safe_enable(info)
        self._save_installed_list()

        if not has_settings:
            return True, f"插件 \"{name}\" 导入成功（提示：建议添加 settings.py 以提供设置页）"
        return True, f"插件 \"{name}\" 导入成功"

    def delete_plugin(self, plugin_id: str):
        """删除插件（从磁盘移除）"""
        import shutil
        info = self._plugins.pop(plugin_id, None)
        if info:
            info.unload()
            self.clear_plugin_settings_pages(plugin_id)
            self.clear_plugin_training_features(plugin_id)
            self.clear_plugin_top_nav_items(plugin_id)
            self.clear_plugin_console_commands(plugin_id)
            self.unregister_shortcuts(plugin_id)  # ★ v3.0.0
        folder = os.path.join(PLUGIN_DIR, plugin_id)
        if os.path.isdir(folder):
            shutil.rmtree(folder, ignore_errors=True)
        self._save_installed_list()

    def toggle_plugin(self, plugin_id: str, enabled: bool) -> bool:
        """开关指定插件。先保存用户意图，再尝试激活/停用。返回是否成功。"""
        info = self._plugins.get(plugin_id)
        if not info:
            return False
        _monitor_log("info", info.name, f"toggle → {'enable' if enabled else 'disable'}")
        if enabled:
            success = self._safe_enable(info)
        else:
            # 1. 调用插件的 on_disable()
            info.disable()
            # 2. 清理所有注册项
            self.clear_plugin_panels(plugin_id)
            self.clear_plugin_settings_pages(plugin_id)
            self.clear_plugin_training_features(plugin_id)
            self.clear_plugin_top_nav_items(plugin_id)
            self.clear_plugin_console_commands(plugin_id)
            self.clear_plugin_context_menu_items(plugin_id)
            self.unregister_shortcuts(plugin_id)
            # 3. 销毁面板 widget 并完全卸载模块（释放内存 + 清 sys.modules 缓存）
            info.unload()
            success = True
        self._save_installed_list()
        return success

    def get_all_plugins(self) -> list[PluginInfo]:
        return list(self._plugins.values())

    def get_plugin(self, plugin_id: str) -> PluginInfo | None:
        # 先按 key 查找（文件夹名），再按 manifest.plugin_id 回退查找
        info = self._plugins.get(plugin_id)
        if info is not None:
            return info
        for p in self._plugins.values():
            if p.plugin_id == plugin_id:
                return p
        return None

    def open_plugin_folder(self):
        """在文件管理器中打开插件目录"""
        os.makedirs(PLUGIN_DIR, exist_ok=True)
        os.startfile(PLUGIN_DIR)

    # ── 导航按钮 ──

    def register_nav_button(self, plugin_id: str, side: str, emoji: str,
                            label: str, tooltip: str, callback: Callable,
                            icon: str = ""):
        """在侧边导航栏的插件区注册一个带图标的按钮。
        支持图标文件（.svg/.png）存放于插件自身目录下。
        Args:
            side: "left" 或 "right"
            emoji: 按钮 emoji（icon 为空时的后备显示）
            icon: 图标文件名（如 "timer.svg"），自动从 plugins/<plugin_id>/ 查找
        """
        info = self._plugins.get(plugin_id)
        if not info:
            return
        info.nav_buttons.append({
            "side": side,
            "icon": icon,
            "emoji": emoji,
            "label": label,
            "tooltip": tooltip,
            "callback": _make_weak_callback(callback),
        })

    # ── 面板注册 ──

    def register_panel(self, plugin_id: str, side: str, title: str, emoji: str,
                       tooltip: str, create_widget, icon: str = "",
                       min_width: int = None, max_width: int = None,
                       width_ratio: float = None) -> bool:
        """注册一个插件面板（切换按钮支持图标文件）。

        Args:
            icon: 图标文件名（如 "panel.svg"），自动从 plugins/<plugin_id>/ 查找
            min_width: 面板最小宽度（px），默认 280
            max_width: 面板最大宽度（px），默认 480
            width_ratio: 占可用空间比例（0.0~1.0），默认 0.35
        """
        info = self._plugins.get(plugin_id)
        if not info:
            return False
        # 校验宽度参数：None 表示无限制
        _min_w = min_width if min_width is not None else 280
        _max_w = max_width  # None 表示无上限
        if _max_w is not None and _min_w > _max_w:
            _min_w, _max_w = _max_w, _min_w
        info.panels.append({
            "side": side,
            "title": title,
            "icon": icon,
            "emoji": emoji,
            "tooltip": tooltip,
            "create_widget": _make_weak_callback(create_widget),
            "widget": None,
            "min_width": _min_w,
            "max_width": _max_w,
            "width_ratio": width_ratio,  # None 表示不限比例
        })
        return True

    def get_enabled_panels(self, side: str) -> list[dict]:
        panels = []
        for info in self._plugins.values():
            if info.enabled:
                for p in info.panels:
                    if p["side"] == side:
                        entry = {"plugin_id": info.plugin_id, **p}
                        # 解包弱引用回调供消费者使用
                        entry["create_widget"] = _call_weak_ref(p["create_widget"])
                        panels.append(entry)
        return panels

    def clear_plugin_panels(self, plugin_id: str):
        info = self._plugins.get(plugin_id)
        if info:
            info.panels.clear()

    def get_enabled_nav_buttons(self, side: str) -> list[dict]:
        buttons = []
        for info in self._plugins.values():
            if info.enabled:
                for btn in info.nav_buttons:
                    if btn["side"] == side:
                        entry = {"plugin_id": info.plugin_id, **btn}
                        # 解包弱引用回调供消费者使用
                        entry["callback"] = _call_weak_ref(btn["callback"])
                        buttons.append(entry)
        return buttons

    # ── 顶部导航栏按钮 ──

    def register_top_nav_button(self, plugin_id: str, btn_id: str, text: str,
                                 tooltip: str, callback: Callable, area: str = "plugin_area_top"):
        """在顶部导航栏 plugin_area 注册一个插件按钮。"""
        info = self._plugins.get(plugin_id)
        if not info:
            return
        info.top_nav_buttons.append({
            "id": f"plugin_top_{plugin_id}_{btn_id}",
            "text": text,
            "tooltip": tooltip,
            "callback": _make_weak_callback(callback),
            "area": area,
        })

    def register_top_nav_sub_menu(self, plugin_id: str, parent_menu_id: str,
                                   sub_id: str, text: str, callback: Callable):
        """在顶部导航栏指定菜单按钮下注册一个插件子菜单项。"""
        info = self._plugins.get(plugin_id)
        if not info:
            return
        info.top_nav_sub_menus.append({
            "id": f"plugin_sub_{plugin_id}_{sub_id}",
            "parent_menu_id": parent_menu_id,
            "text": text,
            "callback": _make_weak_callback(callback),
        })

    def get_enabled_top_nav_buttons(self) -> list[dict]:
        """获取所有已启用插件的顶部导航栏按钮。"""
        buttons = []
        for info in self._plugins.values():
            if info.enabled:
                for btn in info.top_nav_buttons:
                    entry = {"plugin_id": info.plugin_id, **btn}
                    entry["callback"] = _call_weak_ref(btn["callback"])
                    buttons.append(entry)
        return buttons

    def get_enabled_top_nav_sub_menus(self) -> list[dict]:
        """获取所有已启用插件的顶部导航栏子菜单项。"""
        items = []
        for info in self._plugins.values():
            if info.enabled:
                for sub in info.top_nav_sub_menus:
                    entry = {"plugin_id": info.plugin_id, **sub}
                    entry["callback"] = _call_weak_ref(sub["callback"])
                    items.append(entry)
        return items

    def clear_plugin_top_nav_items(self, plugin_id: str):
        """清除指定插件的所有顶部导航栏项。"""
        info = self._plugins.get(plugin_id)
        if info:
            info.top_nav_buttons.clear()
            info.top_nav_sub_menus.clear()

    # ── Hook 系统 ──

    def register_hook(self, hook_name: str, callback: Callable):
        if hook_name not in self._hook_listeners:
            self._hook_listeners[hook_name] = []
        self._hook_listeners[hook_name].append(_make_weak_callback(callback))

    def unregister_hook(self, hook_name: str, callback: Callable):
        if hook_name in self._hook_listeners:
            try:
                self._hook_listeners[hook_name].remove(callback)
            except ValueError:
                pass

    def trigger_hook(self, hook_name: str, *args, **kwargs):
        alive_callbacks = []
        for cb in self._hook_listeners.get(hook_name, []):
            try:
                real_cb = _call_weak_ref(cb)
                if real_cb is None:
                    continue  # 回调已失效，跳过
                real_cb(*args, **kwargs)
                alive_callbacks.append(cb)
            except Exception:
                print(f"[Plugin] Hook '{hook_name}' 执行异常:")
                traceback.print_exc()
        # 清理失效的弱引用
        self._hook_listeners[hook_name] = alive_callbacks

    # ── 设置页注册 ──

    def register_settings_page(self, plugin_id: str, page_id: str, meta: dict,
                               create_widget_fn=None, collect_config_fn=None,
                               module_path: str = ""):
        info = self._plugins.get(plugin_id)
        if not info:
            return False

        info.settings_pages = [
            sp for sp in info.settings_pages if sp.get("page_id") != page_id
        ]
        info.settings_pages.append({
            "page_id": page_id,
            "meta": meta,
            "create_widget": create_widget_fn,
            "collect_config": collect_config_fn,
            "module_path": module_path,
        })

        from workers.settings.settings_page_base import PageRegistry
        PageRegistry.register_plugin_page(
            page_id, meta, plugin_id,
            module_path=module_path,
            create_widget_fn=create_widget_fn,
            collect_config_fn=collect_config_fn,
        )
        return True

    def get_enabled_settings_pages(self) -> list[dict]:
        pages = []
        for info in self._plugins.values():
            if info.enabled:
                for sp in info.settings_pages:
                    pages.append({"plugin_id": info.plugin_id, **sp})
        return pages

    def clear_plugin_settings_pages(self, plugin_id: str):
        info = self._plugins.get(plugin_id)
        if info:
            info.settings_pages.clear()
        from workers.settings.settings_page_base import PageRegistry
        PageRegistry.remove_plugin_pages(plugin_id)

    # ── 训练子功能注册（v2.1.0）──

    def register_training_sub_feature(self, plugin_id: str, info: dict,
                                      manager_class) -> bool:
        """注册一个插件提供的模拟训练子功能"""
        info_obj = self._plugins.get(plugin_id)
        if not info_obj:
            return False

        from workers.training import register_plugin_sub_feature
        success = register_plugin_sub_feature(plugin_id, info, manager_class)

        if success:
            # 记录到 PluginInfo 以便后续清理
            feature_id = f"plugin_{plugin_id}_{info['id']}"
            info_obj.training_features.append({
                "feature_id": feature_id,
                "info": info,
            })

        return success

    def clear_plugin_training_features(self, plugin_id: str):
        """清理指定插件的所有训练子功能"""
        from workers.training import unregister_plugin_sub_features
        unregister_plugin_sub_features(plugin_id)

        info = self._plugins.get(plugin_id)
        if info:
            info.training_features.clear()

    # ── 控制台命令注册（v2.3.0 新增）──

    def register_console_command(self, plugin_id: str, cmd_name: str,
                                  handler_fn, args_desc: str = "",
                                  description: str = "", category: str = "插件命令"):
        """注册一个插件自定义控制台命令。

        Args:
            plugin_id: 插件 ID
            cmd_name: 命令名称（如 "timer:start"）
            handler_fn: 命令处理函数 (args: str) -> str | None
            args_desc: 参数说明
            description: 命令描述
            category: 分类名
        """
        info = self._plugins.get(plugin_id)
        if not info:
            return False

        # 去重
        info.console_commands = [
            c for c in info.console_commands if c["cmd"] != cmd_name
        ]

        info.console_commands.append({
            "cmd": cmd_name,
            "args": args_desc,
            "desc": description,
            "cat": category,
            "handler_fn": _make_weak_callback(handler_fn),
            "plugin_id": plugin_id,
        })
        return True

    def get_enabled_console_commands(self) -> list[dict]:
        """获取所有已启用插件的控制台命令列表。"""
        commands = []
        for info in self._plugins.values():
            if info.enabled:
                for cmd in info.console_commands:
                    entry = dict(cmd)
                    entry["handler_fn"] = _call_weak_ref(cmd["handler_fn"])
                    commands.append(entry)
        return commands

    def clear_plugin_console_commands(self, plugin_id: str):
        """清除指定插件的所有控制台命令。"""
        info = self._plugins.get(plugin_id)
        if info:
            info.console_commands.clear()

    # ── 右键菜单项注册（v4.7.0 新增）──

    def register_context_menu_item(self, plugin_id: str, label: str,
                                     callback: Callable[[str], None],
                                     order: int = 100):
        """注册项目浏览器右键菜单项。

        Args:
            plugin_id: 插件 ID
            label: 菜单显示文本
            callback: 回调函数，接收 file_path 参数
            order: 排序顺序（越小越靠前），默认 100
        """
        # 去重
        self._context_menu_items = [
            i for i in self._context_menu_items
            if not (i["plugin_id"] == plugin_id and i["label"] == label)
        ]
        self._context_menu_items.append({
            "plugin_id": plugin_id,
            "label": label,
            "callback": callback,
            "order": order,
        })

    def get_context_menu_items(self) -> list[dict]:
        """获取所有已注册的右键菜单项（按 order 排序）。"""
        return sorted(self._context_menu_items, key=lambda x: x.get("order", 100))

    def clear_plugin_context_menu_items(self, plugin_id: str):
        """清除指定插件注册的所有右键菜单项。"""
        self._context_menu_items = [
            i for i in self._context_menu_items
            if i["plugin_id"] != plugin_id
        ]

    # ── 快捷键注册（v3.0.0 新增）──

    def register_shortcut(self, plugin_id: str, shortcut_id: str, keys: str,
                          description: str, callback, category: str = "插件快捷键"):
        """插件注册一个全局快捷键。

        快捷键会立即通过 ShortcutManager 绑定到主窗口。
        插件禁用/删除时自动清理。
        """
        info = self._plugins.get(plugin_id)
        if not info:
            return False

        try:
            from workers.shortcuts import get_shortcut_manager
            mgr = get_shortcut_manager()
            source = f"plugin:{plugin_id}"
            # 对回调做弱引用包装后传给 ShortcutManager
            wrapped = _make_weak_callback(callback)
            success = mgr.register(
                shortcut_id, keys, description, category, wrapped, source=source
            )
            if success:
                # 去重记录（存储原始引用用于后续清理）
                if shortcut_id not in info.shortcut_ids:
                    info.shortcut_ids.append(shortcut_id)
            return success
        except Exception:
            import traceback
            traceback.print_exc()
            return False

    def unregister_shortcuts(self, plugin_id: str):
        """注销指定插件的所有快捷键"""
        info = self._plugins.get(plugin_id)
        if info:
            info.shortcut_ids.clear()
        try:
            from workers.shortcuts import get_shortcut_manager
            mgr = get_shortcut_manager()
            mgr.unregister_plugin_shortcuts(plugin_id)
        except Exception:
            pass

    def shutdown(self):
        """关闭所有插件并保存状态"""
        self._save_installed_list()
        for info in self._plugins.values():
            try:
                info.unload()
            except Exception:
                pass


# 全局单例
_manager: PluginManager | None = None


def get_manager() -> PluginManager:
    global _manager
    if _manager is None:
        _manager = PluginManager()
    return _manager
