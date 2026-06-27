"""
STP Packager — .stp 插件包打包器

负责：
  - 从插件目录读取 plugin.json
  - 自动计算所有文件的 SHA256 总校验和
  - 将校验和写入 plugin.json
  - 创建 Zip 包，写入 Zip 注释 "StarPlugin"
  - 输出 .stp 文件

纯 Python 实现，无 Qt 依赖。
"""

import json
import os
import zipfile
import hashlib


# 打包时需要排除的文件/目录
EXCLUDE_NAMES = frozenset({
    "__pycache__", "__MACOSX", ".DS_Store", "Thumbs.db",
})
EXCLUDE_SUFFIXES = frozenset({".pyc", ".pyo"})


def compute_checksum(package_dir: str) -> str:
    """计算插件目录下所有文件（不含 plugin.json 自身）的 SHA256。

    plugin.json 包含 checksum 字段，排除它避免自引用循环。
    打包时先计算其他文件 → 写入 checksum → 打包。
    验证时也排除 plugin.json，比对一致即通过。
    """
    files = _collect_file_list(package_dir)
    hasher = hashlib.sha256()
    for rel in files:
        with open(os.path.join(package_dir, rel), "rb") as fh:
            hasher.update(fh.read())
    return hasher.hexdigest()


def _collect_file_list(package_dir: str) -> list[str]:
    """收集需要计算校验和/打包的文件列表（排除 plugin.json 自身）。"""
    files = []
    for root, dirnames, filenames in os.walk(package_dir):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_NAMES]
        for f in filenames:
            if f in EXCLUDE_NAMES or f.endswith(tuple(EXCLUDE_SUFFIXES)):
                continue
            # 排除 plugin.json 自身（自引用）
            if f == "plugin.json" and root == package_dir:
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, package_dir)
            files.append(rel)
    files.sort()
    return files


def collect_files(package_dir: str) -> list[str]:
    """收集需要打包的文件列表（相对路径，已排序，含 plugin.json）。"""
    files = []
    for root, dirnames, filenames in os.walk(package_dir):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_NAMES]
        for f in filenames:
            if f in EXCLUDE_NAMES or f.endswith(tuple(EXCLUDE_SUFFIXES)):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, package_dir)
            files.append(rel)
    files.sort()
    return files


def read_manifest(package_dir: str) -> dict | None:
    """读取插件目录下的 plugin.json。"""
    mf = os.path.join(package_dir, "plugin.json")
    if os.path.isfile(mf):
        try:
            with open(mf, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return None


def write_manifest(package_dir: str, manifest: dict):
    """写回 plugin.json（更新 checksum 后调用）。"""
    mf = os.path.join(package_dir, "plugin.json")
    # 保留原有缩进风格
    with open(mf, "r", encoding="utf-8") as f_old:
        old_content = f_old.read()
    # 检测缩进
    indent = 4
    if old_content.lstrip().startswith("{"):
        # 尝试检测缩进
        for line in old_content.split("\n"):
            if line.startswith("  ") and not line.startswith("    "):
                indent = 2
                break
    with open(mf, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=indent)
        f.write("\n")


def package(package_dir: str, output_path: str = "") -> str:
    """将插件目录打包为 .stp 文件。

    Args:
        package_dir: 插件目录路径
        output_path: 输出路径（默认：当前目录/插件名.stp）

    Returns:
        str: 生成的 .stp 文件绝对路径
    """
    package_dir = os.path.abspath(package_dir)
    if not os.path.isdir(package_dir):
        raise NotADirectoryError(f"插件目录不存在: {package_dir}")

    # 1. 读取 manifest
    manifest = read_manifest(package_dir)
    if manifest is None:
        raise ValueError(f"无法读取 {package_dir}/plugin.json")

    plugin_id = manifest.get("plugin_id", "")
    if not plugin_id:
        raise ValueError("plugin.json 缺少 plugin_id 字段")

    # 2. 计算校验和（写入前）
    checksum = compute_checksum(package_dir)
    manifest["checksum"] = checksum

    # 3. 写回 plugin.json（含 checksum）
    write_manifest(package_dir, manifest)

    # 4. 确定输出路径
    if not output_path:
        name = manifest.get("name", plugin_id)
        output_path = os.path.join(os.getcwd(), f"{name}.stp")
    else:
        output_path = os.path.abspath(output_path)

    # 5. 收集文件列表
    files = collect_files(package_dir)

    # 6. 打包（先写 checksum 再打包）
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            full = os.path.join(package_dir, rel)
            zf.write(full, rel)
        zf.comment = b"StarPlugin"

    return output_path


def validate_package(package_dir: str) -> list[str]:
    """检查插件目录是否符合打包要求。返回错误信息列表（空 = 通过）。"""
    errors = []

    if not os.path.isdir(package_dir):
        return [f"目录不存在: {package_dir}"]

    mf = os.path.join(package_dir, "plugin.json")
    if not os.path.isfile(mf):
        errors.append("缺少 plugin.json")
        return errors

    manifest = read_manifest(package_dir)
    if manifest is None:
        errors.append("plugin.json 格式错误")
        return errors

    required = ["name", "plugin_id", "version", "author", "main"]
    for field in required:
        if field not in manifest or not manifest[field]:
            errors.append(f"plugin.json 缺少必要字段: {field}")

    main_file = manifest.get("main", "")
    if main_file:
        main_path = os.path.join(package_dir, main_file)
        if not os.path.isfile(main_path):
            errors.append(f"入口文件不存在: {main_file}")

    if not manifest.get("plugin_id", ""):
        errors.append("缺少 plugin_id，运行前请先填写")

    return errors
