"""
STPInstaller — .stp 插件包安装器

职责：
  - 识别 .stp 文件（Zip 注释校验）
  - 解析 manifest（plugin.json）
  - 校验 SHA256 校验和
  - 检查版本兼容性
  - 检查依赖
  - 检查冲突（plugin_id 是否已存在）
  - 执行安装（解压 / 注册 / 清理）
  - 卸载（禁用 / 删除）

依赖：
  - plugin_manager/__init__.py 的 PluginManager
  - plugin_api.py 的 PluginSafeAPI
"""

import json
import os
import shutil
import zipfile
import hashlib

from workers.app_config.config_paths import get_config_path
from components.res_path import get_resource_root

_PLUGIN_ROOT = get_resource_root()
PLUGIN_DIR = os.path.join(_PLUGIN_ROOT, "plugins")
TEMP_DIR = os.path.join(_PLUGIN_ROOT, ".stp_temp")
INSTALLED_JSON = get_config_path("config/installed_plugins.json")

STP_COMMENT = "StarPlugin"

# ── 内部工具 ─────────────────────────────────────────────────────


def _get_app_version() -> str:
    """从 config/config.json 读取当前版本号"""
    try:
        cfg = get_config_path("config/config.json")
        if os.path.isfile(cfg):
            with open(cfg, "r", encoding="utf-8") as f:
                return json.load(f).get("version", "1.0.0")
    except Exception:
        pass
    return "1.0.0"


def _parse_version(v: str) -> tuple:
    """将 '1.2.3' 解析为 (1, 2, 3)"""
    try:
        parts = v.strip().lstrip(">=<").split(".")
        return tuple(int(p) if p.isdigit() else 0 for p in parts[:3])
    except Exception:
        return (0, 0, 0)


def _compare_versions(v1: str, v2: str) -> int:
    """比较两个版本号。v1 >= v2 返回 >=0, v1 < v2 返回 <0"""
    a, b = _parse_version(v1), _parse_version(v2)
    return (a > b) - (a < b)


def _check_version_constraint(installed: str, constraint: str) -> bool:
    """检查 installed 版本是否满足 constraint（如 '>=1.0.0'）"""
    constraint = constraint.strip()
    if constraint.startswith(">="):
        return _compare_versions(installed, constraint[2:]) >= 0
    elif constraint.startswith("<="):
        return _compare_versions(installed, constraint[2:]) <= 0
    elif constraint.startswith(">"):
        return _compare_versions(installed, constraint[1:]) > 0
    elif constraint.startswith("<"):
        return _compare_versions(installed, constraint[1:]) < 0
    elif constraint.startswith("=="):
        return _compare_versions(installed, constraint[2:]) == 0
    else:
        # 精确版本
        return _compare_versions(installed, constraint) == 0


def _compute_checksum(extract_dir: str) -> str:
    """计算目录下所有文件（不含 plugin.json）的 SHA256。

    与打包器的 compute_checksum 保持一致——排除 plugin.json
    避免 checksum 字段自引用循环。
    """
    _EXCLUDE = {"__pycache__", ".pyc", ".DS_Store", "Thumbs.db", "__MACOSX"}
    files = []
    for root, dirnames, filenames in os.walk(extract_dir):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE]
        for f in filenames:
            if f.endswith(".pyc") or f in _EXCLUDE:
                continue
            # 排除 plugin.json（自引用）
            if f == "plugin.json" and root == extract_dir:
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, extract_dir)
            files.append(rel)
    files.sort()
    hasher = hashlib.sha256()
    for rel in files:
        with open(os.path.join(extract_dir, rel), "rb") as fh:
            hasher.update(fh.read())
    return hasher.hexdigest()


def _should_exclude(path: str) -> bool:
    """检查路径是否应该被排除（打包时跳过）"""
    name = os.path.basename(path)
    return name in ("__pycache__", "__MACOSX") or \
           name.endswith(".pyc") or \
           name in (".DS_Store", "Thumbs.db")


# ═══════════════════════════════════════════════════════════════
#  STPInstaller
# ═══════════════════════════════════════════════════════════════

class STPInstaller:
    """.stp 插件包安装器"""

    def __init__(self, mw):
        self._mw = mw
        self._pm = mw._plugin_manager if hasattr(mw, "_plugin_manager") else None

    # ── 文件识别 ─────────────────────────────────────────────────

    def is_stp_file(self, filepath: str) -> bool:
        """检查文件是否为合法的 .stp 文件（Zip 注释匹配）"""
        try:
            if not os.path.isfile(filepath):
                return False
            with zipfile.ZipFile(filepath, "r") as zf:
                comment = zf.comment.decode("utf-8", errors="replace").strip()
                return comment == STP_COMMENT
        except Exception:
            return False

    # ── manifest 读取 ───────────────────────────────────────────

    def get_manifest_from_stp(self, filepath: str) -> dict | None:
        """从 .stp 中读取 plugin.json，不进行解包"""
        try:
            with zipfile.ZipFile(filepath, "r") as zf:
                if "plugin.json" not in zf.namelist():
                    return None
                with zf.open("plugin.json") as f:
                    return json.load(f)
        except Exception:
            return None

    def get_manifest_from_dir(self, dirpath: str) -> dict | None:
        """从已解压的目录读取 plugin.json"""
        mf = os.path.join(dirpath, "plugin.json")
        if os.path.isfile(mf):
            try:
                with open(mf, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    # ── 校验 ────────────────────────────────────────────────────

    def validate_checksum(self, extract_dir: str, manifest: dict) -> bool:
        """校验解压后文件的 SHA256 是否与 manifest 一致"""
        expected = manifest.get("checksum", "")
        if not expected:
            # 无 checksum = 旧包 / 未加密，跳过校验
            return True
        actual = _compute_checksum(extract_dir)
        return actual == expected

    # ── 版本兼容 ────────────────────────────────────────────────

    def check_version_compatibility(self, manifest: dict) -> tuple[bool, str]:
        """检查 StarDebate 版本是否满足插件要求"""
        req = manifest.get("min_app_version", "")
        if not req:
            return True, ""
        app_ver = _get_app_version()
        ok = _compare_versions(app_ver, req) >= 0
        msg = f"需要 StarDebate {req}，当前版本 {app_ver}" if not ok else ""
        return ok, msg

    # ── 依赖检查 ────────────────────────────────────────────────

    def check_dependencies(self, manifest: dict) -> list[dict]:
        """检查依赖，返回缺失/版本不匹配的依赖列表"""
        deps = manifest.get("dependencies", {})
        if not deps:
            return []
        missing = []
        for dep_id, version_req in deps.items():
            info = self._get_installed_plugin_info(dep_id)
            if info is None:
                missing.append({
                    "id": dep_id,
                    "required": version_req,
                    "installed": None,
                    "status": "missing",
                })
            elif not _check_version_constraint(info.version, version_req):
                missing.append({
                    "id": dep_id,
                    "required": version_req,
                    "installed": info.version,
                    "status": "version_mismatch",
                })
        return missing

    def _get_installed_plugin_info(self, plugin_id: str):
        """获取已安装的插件信息"""
        if self._pm:
            return self._pm.get_plugin(plugin_id)
        return None

    # ── 冲突检查 ────────────────────────────────────────────────

    def check_conflict(self, manifest: dict) -> dict:
        """检查插件是否已安装"""
        plugin_id = manifest.get("plugin_id", "")
        if not plugin_id:
            return {"has_conflict": False}
        info = self._get_installed_plugin_info(plugin_id)
        if info:
            return {
                "has_conflict": True,
                "plugin_id": plugin_id,
                "current_version": info.version,
                "new_version": manifest.get("version", "0.0.0"),
                "name": manifest.get("name", plugin_id),
            }
        return {"has_conflict": False}

    # ── 安装主流程 ──────────────────────────────────────────────

    def install(self, filepath: str, conflict_mode: str = "overwrite") -> dict:
        """
        执行 .stp 安装（不含预览对话框，由调用方处理 UI 确认）。

        Args:
            filepath: .stp 文件路径
            conflict_mode: "overwrite" | "parallel" | "cancel"

        Returns:
            {"success": bool, "plugin_id": str, "error": str}
        """
        if not os.path.isfile(filepath):
            return {"success": False, "plugin_id": "", "error": "文件不存在"}

        if not self.is_stp_file(filepath):
            return {"success": False, "plugin_id": "", "error": "不是有效的 .stp 文件"}

        # 1. 读取 manifest（从 .stp 包内读取，无需解压）
        manifest = self.get_manifest_from_stp(filepath)
        if not manifest:
            return {"success": False, "plugin_id": "",
                    "error": "无法读取 plugin.json，文件可能已损坏"}

        plugin_id = manifest.get("plugin_id", "")
        if not plugin_id:
            return {"success": False, "plugin_id": "",
                    "error": "plugin.json 缺少 plugin_id 字段"}

        # 2. 解压到临时目录
        extract_dir = self._extract_to_temp(filepath)
        if not extract_dir:
            return {"success": False, "plugin_id": plugin_id,
                    "error": "解压插件包失败"}

        try:
            # 3. 校验 checksum
            if not self.validate_checksum(extract_dir, manifest):
                return {"success": False, "plugin_id": plugin_id,
                        "error": "文件校验失败，插件可能已损坏或被篡改"}

            # 4. 版本兼容检查
            compat_ok, compat_msg = self.check_version_compatibility(manifest)
            if not compat_ok:
                return {"success": False, "plugin_id": plugin_id,
                        "error": compat_msg}

            # 5. 处理冲突
            conflict = self.check_conflict(manifest)
            if conflict_mode == "cancel" and conflict["has_conflict"]:
                return {"success": False, "plugin_id": plugin_id,
                        "error": f"插件 \"{conflict['name']}\" 已安装"}

            if conflict_mode == "parallel" and conflict["has_conflict"]:
                plugin_id = self._make_parallel_id(plugin_id)

            # 6. 复制到 plugins/ 目录
            dest = os.path.join(PLUGIN_DIR, plugin_id)
            if os.path.exists(dest):
                shutil.rmtree(dest, ignore_errors=True)

            # 复制前设置 enabled = false
            self._set_enabled_false(extract_dir)

            shutil.copytree(extract_dir, dest)

            # 7. 注册到 PluginManager
            if self._pm:
                # 先清除旧注册（如果有）
                old_info = self._pm.get_plugin(plugin_id)
                if old_info:
                    self._pm.delete_plugin(plugin_id)
                ok, msg = self._pm._register_existing_plugin(plugin_id)
                if not ok:
                    shutil.rmtree(dest, ignore_errors=True)
                    return {"success": False, "plugin_id": plugin_id,
                            "error": f"注册失败: {msg}"}
                self._pm._save_installed_list()

            return {"success": True, "plugin_id": plugin_id, "error": None}

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "plugin_id": plugin_id,
                    "error": f"安装异常: {str(e)}"}
        finally:
            self._clean_temp()

    # ── 卸载 ────────────────────────────────────────────────────

    def uninstall(self, plugin_id: str, mode: str = "disable") -> bool:
        """
        卸载插件。

        Args:
            plugin_id: 插件标识
            mode: "disable" — 仅禁用 / "delete" — 彻底删除

        Returns:
            bool: 是否成功
        """
        if not self._pm:
            return False

        if mode == "disable":
            info = self._pm.get_plugin(plugin_id)
            if info:
                info.disable()
                info.enabled = False
                self._pm.clear_plugin_panels(plugin_id)
                self._pm.clear_plugin_training_features(plugin_id)
                self._pm.clear_plugin_top_nav_items(plugin_id)
                self._pm.clear_plugin_console_commands(plugin_id)
                self._pm.unregister_shortcuts(plugin_id)
                self._pm._save_installed_list()
            return True

        elif mode == "delete":
            self._pm.delete_plugin(plugin_id)
            return True

        return False

    # ── 内部方法 ────────────────────────────────────────────────

    def _extract_to_temp(self, filepath: str) -> str | None:
        """解压 .stp 到临时目录"""
        self._clean_temp()
        os.makedirs(TEMP_DIR, exist_ok=True)
        try:
            with zipfile.ZipFile(filepath, "r") as zf:
                zf.extractall(TEMP_DIR)
            return TEMP_DIR
        except Exception:
            return None

    def _set_enabled_false(self, dirpath: str):
        """将插件目录的 plugin.json 中 enabled 设为 false"""
        mf_path = os.path.join(dirpath, "plugin.json")
        try:
            with open(mf_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["enabled"] = False
            with open(mf_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @staticmethod
    def _make_parallel_id(plugin_id: str) -> str:
        """生成并列安装 ID"""
        import re
        suffix = 2
        base = plugin_id.rstrip("0123456789")
        while True:
            candidate = f"{base}_{suffix}"
            if not os.path.isdir(os.path.join(PLUGIN_DIR, candidate)):
                return candidate
            suffix += 1

    @staticmethod
    def _clean_temp():
        """清理临时目录"""
        if os.path.isdir(TEMP_DIR):
            try:
                shutil.rmtree(TEMP_DIR, ignore_errors=True)
            except Exception:
                pass
