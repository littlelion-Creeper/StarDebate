"""更新器共享工具函数

提供版本比较、SHA256 校验、路径管理、备份管理等通用功能。
本模块被 update_manager（主进程侧）和 update_patch_applier（更新进程侧）共同使用，
因此不依赖 PyQt5/Qt，仅使用 Python 标准库。
"""

from __future__ import annotations

import os
import json
import shutil
import hashlib
import zipfile
import re
import time as _time
import logging

from components.res_path import get_resource_root

from workers.app_config.config_paths import get_config_path

# ── 项目根目录 ───────────────────────────────────────────────────────────
_PROJECT_ROOT: str = get_resource_root()

logger = logging.getLogger("StarDebate.updater.utils")

# ── 常量 ────────────────────────────────────────────────────────────────
_STAGING_DIR_NAME = "_update_staging"
_BACKUPS_DIR_NAME = "backups"
_STATE_FILENAME = "update_state.json"
_IGNORE_LIST_FILENAME = "ignored_updates.json"
_MAX_BACKUPS = 2
_PATCH_PATTERN = r"update_v(.+?)_to_v(.+?)\.zip$"

# ── 排除目录（不参与更新） ────────────────────────────────────────────
_EXCLUDED_DIRS = {
    "plugins",
    "__pycache__",
    ".git",
    "_update_staging",
    "backups",
    ".codebuddy",
    "exercise_sessions",
}

_EXCLUDED_FILES = {
    "_run_update.bat",
    "_post_update.bat",
}

# ── 重启状态常量（同进程软重启用） ─────────────────────────────────
_RESTART_STATE_FILES_REPLACED = "files_replaced"
_RESTART_STATE_RESTARTING = "restarting"
_MAX_RESTART_LOOP = 3


# ════════════════════════════════════════════════════════════════════════
#  路径工具
# ════════════════════════════════════════════════════════════════════════

def get_project_root() -> str:
    """返回项目根目录绝对路径。"""
    return _PROJECT_ROOT


def get_staging_dir() -> str:
    """返回更新暂存目录路径。"""
    return os.path.join(_PROJECT_ROOT, _STAGING_DIR_NAME)


def get_backups_dir() -> str:
    """返回备份目录路径。"""
    return os.path.join(_PROJECT_ROOT, _BACKUPS_DIR_NAME)


def get_update_state_path() -> str:
    """返回更新状态文件路径。"""
    return os.path.join(get_staging_dir(), _STATE_FILENAME)


def get_ignore_list_path() -> str:
    """返回忽略列表文件路径。"""
    return os.path.join(get_staging_dir(), _IGNORE_LIST_FILENAME)


# ════════════════════════════════════════════════════════════════════════
#  版本管理
# ════════════════════════════════════════════════════════════════════════

def get_config_version() -> str:
    """从 config/config.json 读取当前版本号。"""
    config_path = get_config_path("config/config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return cfg.get("version", "1.0.0")
    except Exception:
        return "1.0.0"


def set_config_version(version: str) -> bool:
    """写入新版本号到 config/config.json。"""
    config_path = get_config_path("config/config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["version"] = version
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        logger.error(f"写入版本号失败: {version}")
        return False


def compare_versions(v1: str, v2: str) -> int:
    """比较两个版本号。

    Returns:
         1  if v1 > v2
         0  if v1 == v2
        -1  if v1 < v2
    """
    def _parse(v):
        parts = re.split(r"[.\-]", v)
        nums = []
        for p in parts:
            try:
                nums.append(int(p))
            except ValueError:
                nums.append(p)
        return nums

    p1, p2 = _parse(v1), _parse(v2)
    max_len = max(len(p1), len(p2))

    for i in range(max_len):
        n1 = p1[i] if i < len(p1) else 0
        n2 = p2[i] if i < len(p2) else 0
        # 混合类型比较：数字 > 字符串
        if isinstance(n1, int) and isinstance(n2, str):
            return 1
        elif isinstance(n1, str) and isinstance(n2, int):
            return -1
        else:
            if n1 > n2:
                return 1
            elif n1 < n2:
                return -1
    return 0


# ════════════════════════════════════════════════════════════════════════
#  SHA256 校验
# ════════════════════════════════════════════════════════════════════════

def compute_sha256(filepath: str) -> str:
    """计算文件的 SHA256 哈希值。

    Args:
        filepath: 文件路径

    Returns:
        十六进制哈希字符串，计算失败返回空字符串
    """
    h = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, IOError):
        logger.error(f"计算 SHA256 失败: {filepath}")
        return ""


def verify_file_hash(filepath: str, expected_hash: str) -> bool:
    """校验文件 SHA256 是否匹配预期值。

    Args:
        filepath: 文件路径
        expected_hash: 预期 SHA256 值

    Returns:
        True 匹配，False 不匹配或计算失败
    """
    actual = compute_sha256(filepath)
    if not actual:
        return False
    match = actual.lower() == expected_hash.lower()
    if not match:
        logger.warning(
            f"SHA256 不匹配: {os.path.basename(filepath)} "
            f"(期望={expected_hash[:12]}... 实际={actual[:12]}...)"
        )
    return match


# ════════════════════════════════════════════════════════════════════════
#  manifest 解析与校验
# ════════════════════════════════════════════════════════════════════════

def read_manifest(zip_path: str) -> dict | None:
    """从补丁 ZIP 中读取并解析 manifest.json。

    Args:
        zip_path: 补丁 ZIP 文件路径

    Returns:
        manifest dict，解析失败返回 None
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if "manifest.json" not in zf.namelist():
                logger.error(f"补丁缺少 manifest.json: {zip_path}")
                return None
            raw = zf.read("manifest.json").decode("utf-8")
            return json.loads(raw)
    except Exception as e:
        logger.error(f"读取 manifest.json 失败 ({zip_path}): {e}")
        return None


def validate_patch_compatibility(
    manifest: dict,
    current_version: str,
) -> tuple[bool, str]:
    """验证补丁是否与当前版本兼容。

    Args:
        manifest: 解析后的 manifest 字典
        current_version: 当前应用版本号

    Returns:
        (是否兼容, 错误信息)
    """
    from_version = manifest.get("from_version", "")
    to_version = manifest.get("to_version", "")

    if not from_version or not to_version:
        return False, "manifest 缺少 from_version 或 to_version"

    if compare_versions(current_version, from_version) != 0:
        return (
            False,
            f"版本不匹配：当前版本为 v{current_version}，"
            f"此补丁要求基础版本为 v{from_version}"
        )

    changes = manifest.get("changes", [])
    if not isinstance(changes, list):
        return False, "manifest 的 changes 字段格式错误"

    # 校验每个变更项必需字段
    for item in changes:
        action = item.get("action", "")
        path = item.get("path", "")
        if action not in ("add", "modify", "delete"):
            return False, f"未知操作类型: {action}"
        if not path:
            return False, "变更项缺少 path 字段"
        if action in ("add", "modify") and not item.get("sha256"):
            return False, f"{action} 操作缺少 sha256 校验值: {path}"

    return True, ""


# ════════════════════════════════════════════════════════════════════════
#  更新状态持久化
# ════════════════════════════════════════════════════════════════════════

def read_update_state() -> dict:
    """读取更新状态文件。"""
    state_path = get_update_state_path()
    if not os.path.exists(state_path):
        return {}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_update_state(state: dict) -> bool:
    """写入更新状态文件。"""
    state_path = get_update_state_path()
    staging = get_staging_dir()
    try:
        os.makedirs(staging, exist_ok=True)
        state["updated_at"] = _time.strftime("%Y-%m-%d %H:%M:%S")
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"写入更新状态失败: {e}")
        return False


# ════════════════════════════════════════════════════════════════════════
#  配置备份 / 恢复 / 清理
# ════════════════════════════════════════════════════════════════════════

def backup_config_dir(version_label: str = "") -> str | None:
    """全量备份 config/ 目录到 backups/v{version}_config/。

    Args:
        version_label: 用于命名备份文件夹的版本标签

    Returns:
        备份目录路径，失败返回 None
    """
    src = get_config_path("config")
    if not os.path.isdir(src):
        logger.warning("config/ 目录不存在，跳过备份")
        return None

    backups_dir = get_backups_dir()
    os.makedirs(backups_dir, exist_ok=True)

    label = version_label or get_config_version()
    backup_name = f"v{label}_config"
    dest = os.path.join(backups_dir, backup_name)

    try:
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        logger.info(f"配置已备份至: {dest}")

        # 清理旧备份
        cleanup_old_backups()

        return dest
    except Exception as e:
        logger.error(f"备份 config/ 目录失败: {e}")
        return None


def restore_config_from_backup(backup_subdir: str) -> bool:
    """从指定备份目录恢复 config/。

    Args:
        backup_subdir: backups/ 下的子目录名，如 "v5.0.0_config"

    Returns:
        True 成功，False 失败
    """
    backups_dir = get_backups_dir()
    src = os.path.join(backups_dir, backup_subdir)
    dest = get_config_path("config")

    if not os.path.isdir(src):
        logger.error(f"备份不存在: {src}")
        return False

    try:
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        logger.info(f"配置已从备份恢复: {src}")
        return True
    except Exception as e:
        logger.error(f"恢复配置失败: {e}")
        return False


def cleanup_old_backups() -> None:
    """清理旧备份，只保留最近 MAX_BACKUPS 个。"""
    backups_dir = get_backups_dir()
    if not os.path.isdir(backups_dir):
        return

    # 找出所有 v*_config 备份
    entries = []
    for name in os.listdir(backups_dir):
        full = os.path.join(backups_dir, name)
        if os.path.isdir(full) and name.endswith("_config"):
            mtime = os.path.getmtime(full)
            entries.append((name, mtime))

    # 按修改时间倒序排列，保留最新的 N 个
    entries.sort(key=lambda x: x[1], reverse=True)
    for name, _ in entries[_MAX_BACKUPS:]:
        old_path = os.path.join(backups_dir, name)
        try:
            shutil.rmtree(old_path)
            logger.info(f"清理旧备份: {old_path}")
        except OSError:
            pass


def delete_backup(backup_subdir: str) -> bool:
    """删除指定备份目录。"""
    target = os.path.join(get_backups_dir(), backup_subdir)
    if not os.path.isdir(target):
        return False
    try:
        shutil.rmtree(target)
        logger.info(f"已删除备份: {target}")
        return True
    except OSError as e:
        logger.error(f"删除备份失败: {e}")
        return False


def list_backups() -> list[dict]:
    """列出所有配置备份。

    Returns:
        [{name, path, size_mb, created_time}, ...]
    """
    backups_dir = get_backups_dir()
    result = []
    if not os.path.isdir(backups_dir):
        return result

    for name in sorted(os.listdir(backups_dir)):
        full = os.path.join(backups_dir, name)
        if os.path.isdir(full) and name.endswith("_config"):
            stat = os.stat(full)
            result.append({
                "name": name,
                "path": full,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_time": _time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    _time.localtime(stat.st_mtime),
                ),
            })
    return result


# ════════════════════════════════════════════════════════════════════════
#  忽略列表管理
# ════════════════════════════════════════════════════════════════════════

def load_ignore_list() -> list[dict]:
    """加载忽略列表。"""
    ignore_path = get_ignore_list_path()
    if not os.path.exists(ignore_path):
        return []
    try:
        with open(ignore_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_ignore_list(data: list[dict]) -> bool:
    """保存忽略列表。"""
    staging = get_staging_dir()
    ignore_path = get_ignore_list_path()
    try:
        os.makedirs(staging, exist_ok=True)
        with open(ignore_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存忽略列表失败: {e}")
        return False


def add_ignored_patch(patch_filename: str, patch_path: str, to_version: str = "") -> None:
    """将补丁添加到忽略列表。"""
    data = load_ignore_list()
    entry = {
        "filename": patch_filename,
        "path": patch_path,
        "to_version": to_version,
        "ignored_at": _time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    # 去重（按 filename）
    data = [e for e in data if e["filename"] != patch_filename]
    data.append(entry)
    save_ignore_list(data)


def remove_ignored_patch(patch_filename: str) -> None:
    """从忽略列表移除指定补丁。"""
    data = load_ignore_list()
    data = [e for e in data if e["filename"] != patch_filename]
    save_ignore_list(data)


def get_ignored_patches() -> list[dict]:
    """获取所有被忽略的补丁。"""
    return load_ignore_list()


# ════════════════════════════════════════════════════════════════════════
#  __pycache__ 清理
# ════════════════════════════════════════════════════════════════════════

def clean_pycache(root_dir: str | None = None, dry_run: bool = False) -> int:
    """递归清理指定目录下的所有 __pycache__ 目录。

    Args:
        root_dir: 要清理的根目录，默认为项目根目录
        dry_run: 仅统计不实际删除

    Returns:
        清理的目录数量
    """
    target = root_dir or _PROJECT_ROOT
    count = 0
    for dirpath, dirnames, filenames in os.walk(target):
        for d in dirnames[:]:
            if d == "__pycache__":
                full = os.path.join(dirpath, d)
                if dry_run:
                    count += 1
                    logger.info(f"[DRY RUN] 将删除: {full}")
                else:
                    try:
                        shutil.rmtree(full)
                        count += 1
                        logger.info(f"已清理 __pycache__: {full}")
                    except OSError as e:
                        logger.error(f"清理 __pycache__ 失败: {full}: {e}")
                dirnames.remove(d)
    return count


# ════════════════════════════════════════════════════════════════════════
#  排除检查
# ════════════════════════════════════════════════════════════════════════

def is_excluded_path(relative_path: str) -> bool:
    """检查路径是否在排除范围内（不参与更新）。"""
    parts = relative_path.replace("\\", "/").split("/")
    if parts and parts[0] in _EXCLUDED_DIRS:
        return True
    basename = os.path.basename(relative_path)
    if basename in _EXCLUDED_FILES or basename.startswith("."):
        return True
    return False


# ════════════════════════════════════════════════════════════════════════
#  重启状态判断（用于同进程软重启流程）
# ════════════════════════════════════════════════════════════════════════

def needs_restart() -> bool:
    """检查是否需要软重启（文件已替换，等待重新 main()）。"""
    state = read_update_state()
    return state.get("status") == _RESTART_STATE_FILES_REPLACED


def clear_restart_flag() -> None:
    """清除重启标记（处理完成或放弃时调用）。"""
    staging = get_staging_dir()
    if os.path.exists(staging):
        try:
            shutil.rmtree(staging)
        except OSError:
            pass
    write_update_state({})


# ════════════════════════════════════════════════════════════════════════
#  文件替换工具（同进程直接覆盖用）
# ════════════════════════════════════════════════════════════════════════

# JSON 配置文件路径列表（字段级合并而非直接覆盖）
_MERGE_JSON_PATHS = {
    "config/config.json",
}

# 字段级合并中"始终覆盖"的键名白名单（不受 preserve 保护）
_FORCE_UPDATE_KEYS = {
    "version",
    "last_viewed_intro_version",
}


def _merge_json_file(new_path: str, dst_path: str) -> bool:
    """字段级合并一个 JSON 配置文件。

    读取新旧两个 JSON 文件：
    - `_FORCE_UPDATE_KEYS` 中的字段始终使用新版本的值
    - 其余字段保留用户现有值，仅补全用户尚不存在的字段
    新旧均非有效 JSON 时回退到直接覆盖。

    Args:
        new_path: 补丁包中的新文件路径
        dst_path: 目标文件路径（用户现有的文件）

    Returns:
        True 表示合并成功，False 表示回退到直接覆盖
    """
    try:
        with open(new_path, "r", encoding="utf-8") as f:
            new_data: dict = json.load(f)
    except Exception:
        logger.warning(f"新 JSON 格式异常，回退直接覆盖: {new_path}")
        return False

    if not isinstance(new_data, dict):
        logger.warning(f"新 JSON 不是 dict 类型，回退直接覆盖: {new_path}")
        return False

    # 读取现有文件
    existing_data: dict = {}
    if os.path.isfile(dst_path):
        try:
            with open(dst_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception:
            logger.warning(f"现有 JSON 格式异常，将直接使用新版: {dst_path}")
            existing_data = {}
    else:
        logger.info(f"目标 JSON 不存在，将直接写入新版: {dst_path}")

    # 字段级合并
    merged: dict = dict(existing_data)
    updated_count = 0
    added_count = 0
    for key, value in new_data.items():
        if key in existing_data:
            if key in _FORCE_UPDATE_KEYS:
                # 白名单字段：强制更新为新版本的值
                merged[key] = value
                updated_count += 1
            # 非白名单已有字段：保留用户的值
        else:
            # 新字段：补充
            merged[key] = value
            added_count += 1

    # 写回
    try:
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with open(dst_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        logger.info(
            f"JSON 字段级合并完成: {os.path.basename(dst_path)} "
            f"(新增 {added_count}, 更新 {updated_count}, "
            f"保留 {len(existing_data) - updated_count} 字段)"
        )
        return True
    except Exception as e:
        logger.error(f"JSON 合并写入失败 ({dst_path}): {e}")
        return False


def apply_new_files(src_dir: str, dst_root: str) -> tuple[int, int, list[str]]:
    """从 src_dir 复制所有文件到 dst_root。

    v6.0.0+ EXE 版使用与源码版一致的布局：.py 文件直接位于项目根目录，
    无需特殊路径路由。

    对 config/config.json 执行字段级合并而非直接覆盖，
    以保留用户配置（如主题、开发者模式设置等）。

    Returns:
        (成功数, 跳过数, 已成功覆盖的文件路径列表)
    """
    copied = 0
    skipped = 0
    applied_paths: list[str] = []

    if not os.path.isdir(src_dir):
        logger.warning(f"源目录不存在: {src_dir}")
        return 0, 0, applied_paths

    for dirpath, _, filenames in os.walk(src_dir):
        for fname in filenames:
            src_full = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(src_full, src_dir).replace("\\", "/")

            if is_excluded_path(rel_path):
                skipped += 1
                continue

            dst_full = os.path.join(dst_root, rel_path)
            dst_dir = os.path.dirname(dst_full)

            try:
                os.makedirs(dst_dir, exist_ok=True)
            except OSError as e:
                logger.error(f"无法创建目录 {dst_dir}: {e}")
                skipped += 1
                continue

            # ── JSON 配置文件：字段级合并 ──────────────────────
            if rel_path in _MERGE_JSON_PATHS:
                if _merge_json_file(src_full, dst_full):
                    copied += 1
                    applied_paths.append(rel_path)
                    continue
                # 合并失败，回退到直接覆盖

            try:
                shutil.copy2(src_full, dst_full)
                copied += 1
                applied_paths.append(rel_path)
                logger.debug(f"覆盖: {rel_path}")
            except OSError as e:
                logger.error(f"复制失败 ({rel_path}): {e}")
                skipped += 1

    return copied, skipped, applied_paths


def execute_deletes(delete_paths: list[str], root_dir: str) -> tuple[int, int]:
    """从项目根目录删除指定文件列表。

    v6.0.0+ EXE 版使用与源码版一致的布局：.py 文件直接位于项目根目录，
    无需特殊路径路由。

    Args:
        delete_paths: 相对于项目根目录的文件路径列表
        root_dir: 项目根目录

    Returns:
        (成功删除数, 失败数)
    """
    deleted = 0
    failed = 0

    for rel_path in delete_paths:
        if is_excluded_path(rel_path):
            continue

        target = os.path.join(root_dir, rel_path)
        try:
            if os.path.isfile(target):
                os.remove(target)
                deleted += 1
                logger.debug(f"删除: {rel_path}")
            elif os.path.isdir(target):
                shutil.rmtree(target)
                deleted += 1
                logger.debug(f"删除(目录): {rel_path}")
            else:
                logger.debug(f"跳过(不存在): {rel_path}")
        except OSError as e:
            logger.error(f"删除失败 ({rel_path}): {e}")
            failed += 1

    return deleted, failed
