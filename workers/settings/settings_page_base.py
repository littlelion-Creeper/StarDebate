"""
设置页面基类和注册表

每个设置页文件需定义：
  - PAGE_INFO: dict — 页面元信息
  - PAGE_CONFIG: dict (可选) — 页面参数配置
  - build_page(parent_dialog, current_config) → QWidget
  - collect_config(page_widget) → dict
  - get_default_config() → dict (可选)
"""

import os
import sys
import json
import logging
import importlib.util
import traceback
from typing import Any, Callable

# 设置页文件目录（始终从打包资源目录加载页面模块）
from workers.app_config import get_config_path, get_packaged_path
from components.res_path import get_resource_root

BUILTIN_PAGES_DIR = os.path.join(get_resource_root(), "workers", "settings", "pages")

# 全局注册表
_builtin_pages: list[dict] = []
_plugin_pages: list[dict] = []


class SettingsPageInfo:
    """设置页信息结构"""

    __slots__ = (
        "page_id", "name", "icon", "order", "author", "version",
        "source", "plugin_id", "module_path",
        "_module", "_widget",
        "config", "save_path", "auto_save",
        "_create_widget_fn", "_collect_config_fn",
    )

    def __init__(self, page_id: str, meta: dict, source: str = "builtin",
                 plugin_id: str = "", module_path: str = "",
                 create_widget_fn=None, collect_config_fn=None):
        self.page_id = page_id
        self.name = meta.get("name", page_id)
        self.icon = meta.get("icon", "📄")
        self.order = meta.get("order", 100)
        self.author = meta.get("author", "")
        self.version = meta.get("version", "1.0.0")

        self.source = source        # "builtin" | "plugin"
        self.plugin_id = plugin_id
        self.module_path = module_path

        # 页面参数配置
        page_config = meta.get("page_config", {})
        self.config = page_config.get("config", {})
        self.save_path = page_config.get("save_path", "")
        self.auto_save = page_config.get("auto_save", True)

        # 插件页面使用回调而非文件加载
        self._create_widget_fn = create_widget_fn
        self._collect_config_fn = collect_config_fn

        self._module = None
        self._widget = None   # 延迟创建

    def load_module(self) -> bool:
        """加载页面模块，返回是否成功。插件页面无需加载模块。
        支持两种 module_path 格式：
          - 文件路径（原始模式）：os.path.isfile -> spec_from_file_location
          - 模块路径（PyInstaller pkgutil 模式）：importlib.import_module
        """
        if self._module is not None:
            return True
        if self.source == "plugin":
            return True
        if not self.module_path:
            return False
        try:
            if os.path.isfile(self.module_path):
                # 文件路径模式
                spec = importlib.util.spec_from_file_location(
                    f"settings_page_{self.page_id}", self.module_path
                )
                if spec is None or spec.loader is None:
                    return False
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            else:
                # 模块路径模式（dotted notation，适用于 PyInstaller 打包后）
                mod = importlib.import_module(self.module_path)
            self._module = mod
            return True
        except Exception:
            traceback.print_exc()
            return False

    def build_widget(self, parent_dialog) -> Any:
        """构建页面 widget（延迟创建，仅首次调用时构建）"""
        if self._widget is not None:
            return self._widget

        if not self.load_module():
            return None

        try:
            if self.source == "plugin" and self._create_widget_fn:
                # 插件页面：直接回调
                self._widget = self._create_widget_fn()
            else:
                # 内置页面：通过 build_page 函数
                build_func = getattr(self._module, "build_page", None)
                if build_func is None:
                    return None
                current_config = self._load_saved_config()
                self._widget = build_func(parent_dialog, current_config)
            return self._widget
        except Exception:
            traceback.print_exc()
            logging.getLogger(__name__).exception(
                "设置页构建失败: %s", self.name
            )
            return None

    def collect_config(self) -> dict | None:
        """从页面 widget 收集当前配置"""
        if self._widget is None:
            return None
        try:
            if self.source == "plugin" and self._collect_config_fn:
                return self._collect_config_fn(self._widget)
            elif self._module is not None:
                collect_func = getattr(self._module, "collect_config", None)
                if collect_func:
                    return collect_func(self._widget)
        except Exception:
            traceback.print_exc()
            logging.getLogger(__name__).exception(
                "设置页配置收集失败: %s", self.name
            )
        return None

    def get_default_config(self) -> dict:
        """获取默认配置"""
        if self.source == "plugin":
            return {}
        if not self.load_module():
            return {}
        func = getattr(self._module, "get_default_config", None)
        if func:
            return func()
        return {}

    def get_save_path(self) -> str:
        """获取保存路径（绝对路径，持久化目录）"""
        if self.save_path:
            # 保存到持久化配置目录（EXE版为 exe同级/config/）
            return get_config_path(self.save_path)
        return ""

    def _load_saved_config(self) -> dict:
        """从文件加载已保存的配置"""
        save_path = self.get_save_path()
        if save_path and os.path.isfile(save_path):
            try:
                with open(save_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return self.get_default_config()

    def save_config(self) -> bool:
        """保存当前页面配置到文件"""
        config = self.collect_config()
        if config is None:
            return False
        save_path = self.get_save_path()
        if not save_path:
            return False
        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            traceback.print_exc()
            return False

    @property
    def sort_key(self) -> tuple:
        """排序键：(order, name)"""
        return (self.order, self.name)


class PageRegistry:
    """设置页面注册表"""

    @staticmethod
    def scan_builtin_pages() -> list[dict]:
        """扫描 workers/settings/pages/ 目录中的内置设置页。
        返回原始 dict 列表，每个 dict 包含 page_id 和 meta 信息。
        """
        global _builtin_pages
        _builtin_pages.clear()

        if not os.path.isdir(BUILTIN_PAGES_DIR):
            return []

        for entry in sorted(os.listdir(BUILTIN_PAGES_DIR)):
            if entry.startswith("_") or entry.startswith("."):
                continue
            if not entry.endswith(".py"):
                continue

            page_id = os.path.splitext(entry)[0]
            module_path = os.path.join(BUILTIN_PAGES_DIR, entry)

            try:
                spec = importlib.util.spec_from_file_location(
                    f"_scan_{page_id}", module_path
                )
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                page_info = getattr(mod, "PAGE_INFO", None)
                if page_info is None:
                    continue

                page_config = getattr(mod, "PAGE_CONFIG", None) or {}
                meta = dict(page_info)
                meta["page_config"] = page_config

                _builtin_pages.append({
                    "page_id": page_id,
                    "meta": meta,
                    "module_path": module_path,
                })
            except Exception:
                traceback.print_exc()

        _builtin_pages.sort(key=lambda p: p["meta"].get("order", 100))
        return _builtin_pages

    @staticmethod
    def register_plugin_page(page_id: str, meta: dict, plugin_id: str,
                             module_path: str = "", create_widget_fn=None,
                             collect_config_fn=None):
        """注册插件提供的设置页（支持自动扫描 settings.py 或手动回调）"""
        global _plugin_pages
        # 移除同一插件的旧注册
        _plugin_pages = [p for p in _plugin_pages if p["plugin_id"] != plugin_id]
        _plugin_pages.append({
            "page_id": page_id,
            "meta": meta,
            "plugin_id": plugin_id,
            "module_path": module_path,
            "create_widget": create_widget_fn,
            "collect_config": collect_config_fn,
        })
        _plugin_pages.sort(key=lambda p: p["meta"].get("order", 100))

    @staticmethod
    def scan_plugin_pages(plugin_manager=None):
        """扫描所有已启用插件的 settings.py 并注册到全局表。
        由 SettingsDialog 在打开时调用。
        如果 plugin_manager 为 None，则通过 get_manager() 获取。
        """
        global _plugin_pages
        # 清除旧的自动扫描结果
        _plugin_pages = [
            p for p in _plugin_pages
            if p.get("module_path") == ""  # 保留回调注册的页面
        ]

        try:
            from workers.plugin_manager import get_manager
            mgr = plugin_manager or get_manager()
        except Exception:
            return

        for info in mgr.get_all_plugins():
            if not info.enabled:
                continue
            info._auto_register_settings()

    @staticmethod
    def remove_plugin_pages(plugin_id: str):
        """移除指定插件的所有设置页"""
        global _plugin_pages
        _plugin_pages = [p for p in _plugin_pages if p["plugin_id"] != plugin_id]

    @staticmethod
    def get_all_pages() -> list[dict]:
        """获取所有页面（内置 + 插件），按 order 排序"""
        all_pages = list(_builtin_pages) + list(_plugin_pages)
        all_pages.sort(key=lambda p: p["meta"].get("order", 100))
        return all_pages

    @staticmethod
    def create_page_info(raw: dict) -> SettingsPageInfo:
        """根据原始注册信息创建 SettingsPageInfo 实例"""
        source = "plugin" if raw.get("plugin_id") else "builtin"
        module_path = raw.get("module_path", "")
        # 如果有 module_path（自动扫描的 settings.py），按 builtin 方式加载
        if module_path:
            source = "builtin"  # 使用文件加载机制
        return SettingsPageInfo(
            page_id=raw["page_id"],
            meta=raw["meta"],
            source=source,
            plugin_id=raw.get("plugin_id", ""),
            module_path=module_path,
            create_widget_fn=raw.get("create_widget"),
            collect_config_fn=raw.get("collect_config"),
        )


def register_builtin_page(page_id: str, meta: dict, module_path: str):
    """手动注册一个内置页面（供外部调用）"""
    global _builtin_pages
    _builtin_pages.append({
        "page_id": page_id,
        "meta": meta,
        "module_path": module_path,
    })
    _builtin_pages.sort(key=lambda p: p["meta"].get("order", 100))
