"""更新器 — 更新进程执行脚本（稳定不动）

同进程软重启版：更新管理器直接导入本模块的函数执行文件操作，
不再需要通过 .bat + 独立子进程调用。

本文件作为独立脚本使用时（python update_patch_applier.py --help）
保留兼容入口。但在主流程中，由 update_manager 直接调用导入函数。

保持稳定：本文件永远不进入补丁 manifest 的 modify 列表。
"""

from __future__ import annotations

import os
import sys
import json
import logging

# ── 从 update_utils 导入共享工具函数 ─────────────────────────────────
from .update_utils import (
    get_project_root,
    apply_new_files,
    execute_deletes,
    clean_pycache,
    write_update_state,
)

logger = logging.getLogger("StarDebate.updater.applier")


# ════════════════════════════════════════════════════════════════════════
#  独立脚本入口（兼容模式）
# ════════════════════════════════════════════════════════════════════════

def main() -> int:
    """兼容旧的独立脚本入口。

    用法:
        python update_patch_applier.py --new-files <目录> [--delete-list <文件>]

    在软重启流程中不再需要此入口，保留仅为向后兼容。
    """
    parser = _arg_parse()
    if not parser:
        logger.error("参数不足。用法: --new-files <目录> [--delete-list <文件>]")
        return 1

    new_files_dir = parser.get("new_files_dir", "")
    delete_list_file = parser.get("delete_list_file", "")
    project_root = get_project_root()

    if new_files_dir:
        copied, skipped, paths = apply_new_files(new_files_dir, project_root)
        logger.info(f"文件复制: {copied} 成功, {skipped} 跳过")

    if delete_list_file:
        delete_paths = _load_delete_list(delete_list_file)
        if delete_paths:
            deleted, failed = execute_deletes(delete_paths, project_root)
            logger.info(f"文件删除: {deleted} 成功, {failed} 失败")

    cleaned = clean_pycache()
    if cleaned:
        logger.info(f"__pycache__ 清理: {cleaned} 个目录")

    logger.info("更新完成")
    return 0


def _arg_parse() -> dict | None:
    """简易参数解析。"""
    args = {}
    for i, arg in enumerate(sys.argv):
        if arg == "--new-files" and i + 1 < len(sys.argv):
            args["new_files_dir"] = sys.argv[i + 1]
        elif arg == "--delete-list" and i + 1 < len(sys.argv):
            args["delete_list_file"] = sys.argv[i + 1]
    return args if args else None


def _load_delete_list(filepath: str) -> list[str]:
    """从文件加载删除路径列表。"""
    if not os.path.isfile(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except OSError:
        return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
