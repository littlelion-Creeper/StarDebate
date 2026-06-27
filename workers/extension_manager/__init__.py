"""StarDebate ★ 扩展包管理器
============================================================================
扩展包（.sep）是比插件权限更高的模块化单元：
  - 默认拥有全部系统权限（无需 permission 声明）
  - 安装即启用，禁用/卸载需重启生效
  - 扩展包实体存放于 extensions/ 目录（与 plugins/ 分离）
  - 通过 ExtensionAPI 访问全部核心对象 + 高级方法
============================================================================
"""
import os
import sys
import json
import time
import types
import shutil
import importlib.util
import traceback
import weakref

from workers.app_config.config_paths import get_config_path
from components.res_path import get_resource_root

# 扩展包存放目录（与 plugins/ 完全分离）
EXTENSION_DIR = os.path.join(get_resource_root(), "extensions")

# 已安装扩展包清单
INSTALLED_JSON = get_config_path("config/installed_extensions.json")

# ExtensionAPI 全局引用（由主窗口注入）
_extension_api = None


def set_api(api_instance):
    """由主窗口调用，注入扩展包 API 实例"""
    global _extension_api
    _extension_api = api_instance


def get_api():
    """扩展包内部调用，获取 ExtensionAPI"""
    return _extension_api


class ExtensionInfo:
    """单个扩展包的信息描述"""

    def __init__(self, ext_id: str, manifest: dict):
        self.ext_id = ext_id
        self.name = manifest.get("name", ext_id)
        self.version = manifest.get("version", "1.0.0")
        self.author = manifest.get("author", "未知")
        self.description = manifest.get("description", "")
        self.main_file = manifest.get("main", "main.py")
        self.tags = manifest.get("tags", [])
        # 无 permissions 字段 — 扩展包默认全权限
        self.enabled = False  # 由清单加载后设置
        self._module = None
        self._instance = None

    @property
    def folder(self) -> str:
        return os.path.join(EXTENSION_DIR, self.ext_id)

    @property
    def manifest_path(self) -> str:
        return os.path.join(self.folder, "extension.json")

    def load(self) -> bool:
        """加载扩展包模块（不执行初始化）。"""
        if self._module is not None:
            return True
        main_path = os.path.join(self.folder, self.main_file)
        if not os.path.exists(main_path):
            print(f"[Extension] 未找到入口: {main_path}")
            return False

        try:
            spec = importlib.util.spec_from_file_location(
                f"extension_{self.ext_id}", main_path
            )
            if spec is None or spec.loader is None:
                return False
            self._module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self._module)
            return True
        except Exception:
            print(f"[Extension] 加载 '{self.name}' 失败:")
            traceback.print_exc()
            self._module = None
            return False

    def enable(self):
        """启用扩展包（安装即启用，重启生效）。"""
        if not self.load():
            return False
        try:
            if hasattr(self._module, "on_enable"):
                # 设置 API 上下文
                prev_id = _extension_api._ext_id if _extension_api else ""
                if _extension_api:
                    _extension_api._ext_id = self.ext_id
                self._module.on_enable()
                if _extension_api:
                    _extension_api._ext_id = prev_id
            self.enabled = True
            return True
        except Exception:
            print(f"[Extension] 启用 '{self.name}' 失败:")
            traceback.print_exc()
            self.enabled = False
            return False

    def disable(self):
        """禁用扩展包"""
        try:
            if self._module and hasattr(self._module, "on_disable"):
                self._module.on_disable()
        except Exception:
            traceback.print_exc()
        self.enabled = False

    def unload(self):
        """完全卸载扩展包"""
        self.disable()
        self._instance = None
        mod_ref = self._module
        self._module = None
        if mod_ref is not None:
            for key in list(sys.modules.keys()):
                if key == f"extension_{self.ext_id}":
                    sys.modules.pop(key, None)

    def call(self, method_name: str, *args, **kwargs):
        """安全调用扩展包的指定方法"""
        if not self._module:
            return None
        try:
            func = getattr(self._module, method_name, None)
            if func and callable(func):
                return func(*args, **kwargs)
        except Exception:
            print(f"[Extension] '{self.name}' 方法 '{method_name}' 异常:")
            traceback.print_exc()
        return None


class ExtensionManager:
    """扩展包管理器：负责扫描、加载、管理所有扩展包"""

    def __init__(self):
        self._extensions: dict[str, ExtensionInfo] = {}
        os.makedirs(EXTENSION_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(INSTALLED_JSON), exist_ok=True)
        self._load_installed_list()

    # ── 列表管理 ──

    def _load_installed_list(self):
        """从 installed_extensions.json 加载已安装扩展包清单"""
        if os.path.exists(INSTALLED_JSON):
            try:
                with open(INSTALLED_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    ext_id = item.get("id", "")
                    if ext_id:
                        manifest = self._read_manifest(ext_id)
                        if manifest:
                            info = ExtensionInfo(ext_id, manifest)
                            info.enabled = item.get("enabled", True)
                            self._extensions[ext_id] = info
            except Exception as e:
                print(f"[Extension] 加载清单失败: {e}")

        # 自动发现 extensions/ 目录中未注册的文件夹
        self._discover_unregistered()

    def _discover_unregistered(self):
        """扫描 extensions/ 目录，自动注册未记录的新扩展包"""
        if not os.path.isdir(EXTENSION_DIR):
            return
        skip_names = {"__pycache__"}
        try:
            for entry in os.listdir(EXTENSION_DIR):
                entry_path = os.path.join(EXTENSION_DIR, entry)
                if os.path.isdir(entry_path) and entry not in skip_names \
                   and not entry.startswith(".") and entry not in self._extensions:
                    manifest = self._read_manifest(entry)
                    if manifest:
                        info = ExtensionInfo(entry, manifest)
                        self._extensions[entry] = info
            if self._extensions:
                self._save_installed_list()
        except Exception as e:
            print(f"[Extension] 自动发现失败: {e}")

    def enable_all_default(self):
        """启动时启用所有标记为 enabled 的扩展包"""
        for info in self._extensions.values():
            if info.enabled:
                self._safe_enable(info)

    def _save_installed_list(self):
        """保存已安装扩展包清单"""
        data = []
        for ext_id, info in self._extensions.items():
            data.append({"id": ext_id, "enabled": info.enabled})
        try:
            with open(INSTALLED_JSON, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Extension] 保存清单失败: {e}")

    def _read_manifest(self, ext_id: str) -> dict | None:
        """读取扩展包的 extension.json 清单"""
        manifest_path = os.path.join(EXTENSION_DIR, ext_id, "extension.json")
        if not os.path.exists(manifest_path):
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _safe_enable(self, info: ExtensionInfo) -> bool:
        """安全启用扩展包"""
        try:
            return info.enable()
        except Exception:
            print(f"[Extension] 安全启用 '{info.name}' 失败:")
            traceback.print_exc()
            return False

    # ── 公开接口 ──

    def install_extension(self, source_path: str, conflict_mode: str = "overwrite") -> dict:
        """安装扩展包（从 .sep 文件或文件夹安装）。

        Returns:
            {"success": True/False, "error": str}
        """
        if not os.path.exists(source_path):
            return {"success": False, "error": "源路径不存在"}

        # 确定扩展包 ID
        if os.path.isfile(source_path) and source_path.lower().endswith(".sep"):
            # .sep 包安装
            return self._install_from_sep(source_path, conflict_mode)
        elif os.path.isdir(source_path):
            name = os.path.basename(source_path.rstrip("/\\"))
            return self._install_from_folder(source_path, name, conflict_mode)
        else:
            return {"success": False, "error": "不支持的源路径"}

    def _install_from_sep(self, sep_path: str, conflict_mode: str) -> dict:
        """从 .sep ZIP 包安装扩展包"""
        import zipfile
        try:
            with zipfile.ZipFile(sep_path, "r") as zf:
                # 检查注释是否为扩展包标识
                comment = zf.comment.decode("utf-8", errors="replace").strip()
                if comment != "StarExtension":
                    return {"success": False, "error": "不是有效的 .sep 文件"}

                # 读取 extension.json
                if "extension.json" not in zf.namelist():
                    return {"success": False, "error": ".sep 包中缺少 extension.json"}

                manifest_data = zf.read("extension.json")
                import json as _json
                manifest = _json.loads(manifest_data)
                ext_id = manifest.get("extension_id", "") or manifest.get("name", "")
                if not ext_id:
                    return {"success": False, "error": "extension.json 缺少 extension_id"}

                dest = os.path.join(EXTENSION_DIR, ext_id)
                if os.path.exists(dest):
                    if conflict_mode == "overwrite":
                        shutil.rmtree(dest, ignore_errors=True)
                    else:
                        return {"success": False, "error": f"扩展包 '{ext_id}' 已存在"}

                # 解压
                zf.extractall(dest)

        except Exception as e:
            return {"success": False, "error": f"解压 .sep 失败: {e}"}

        return self._register_new(ext_id, conflict_mode)

    def _install_from_folder(self, src_folder: str, ext_id: str, conflict_mode: str) -> dict:
        """从文件夹安装扩展包"""
        dest = os.path.join(EXTENSION_DIR, ext_id)
        if os.path.exists(dest):
            if conflict_mode == "overwrite":
                shutil.rmtree(dest, ignore_errors=True)
            else:
                return {"success": False, "error": f"扩展包 '{ext_id}' 已存在"}

        try:
            shutil.copytree(src_folder, dest)
        except Exception as e:
            return {"success": False, "error": f"复制文件夹失败: {e}"}

        return self._register_new(ext_id, conflict_mode)

    def _register_new(self, ext_id: str, conflict_mode: str) -> dict:
        """注册新安装的扩展包"""
        manifest = self._read_manifest(ext_id)
        if not manifest:
            return {"success": False, "error": "安装后无法读取 extension.json"}

        info = ExtensionInfo(ext_id, manifest)
        info.enabled = True
        self._extensions[ext_id] = info
        self._save_installed_list()
        return {"success": True}

    def delete_extension(self, ext_id: str):
        """删除扩展包（从磁盘移除）"""
        info = self._extensions.pop(ext_id, None)
        if info:
            info.unload()
        folder = os.path.join(EXTENSION_DIR, ext_id)
        if os.path.isdir(folder):
            shutil.rmtree(folder, ignore_errors=True)
        self._save_installed_list()

    def set_enabled(self, ext_id: str, enabled: bool):
        """设置扩展包启用状态（下次重启生效）"""
        info = self._extensions.get(ext_id)
        if not info:
            return
        info.enabled = enabled
        self._save_installed_list()

    def get_all(self) -> list[ExtensionInfo]:
        """获取所有扩展包信息"""
        return list(self._extensions.values())

    def get(self, ext_id: str) -> ExtensionInfo | None:
        """获取指定扩展包信息"""
        return self._extensions.get(ext_id)

    def open_extension_folder(self):
        """在文件管理器中打开扩展包目录"""
        os.makedirs(EXTENSION_DIR, exist_ok=True)
        os.startfile(EXTENSION_DIR)

    def shutdown(self):
        """关闭所有扩展包并保存状态"""
        self._save_installed_list()
        for info in self._extensions.values():
            try:
                info.unload()
            except Exception:
                pass


# 全局单例
_manager: ExtensionManager | None = None


def get_manager() -> ExtensionManager:
    global _manager
    if _manager is None:
        _manager = ExtensionManager()
    return _manager
