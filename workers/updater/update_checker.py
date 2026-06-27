"""更新器 — 启动时自动检测补丁文件

在软件启动时扫描根目录下的 update_*.zip 补丁文件，
读取 manifest 校验版本兼容性，返回可用的更新信息。
"""

from __future__ import annotations

import os
import re
import logging

from .update_utils import (
    get_project_root,
    get_config_version,
    read_manifest,
    validate_patch_compatibility,
    load_ignore_list,
    is_excluded_path,
)

logger = logging.getLogger("StarDebate.updater.checker")

# 匹配 update_vX.Y.Z_to_vA.B.C.zip 的正则
_PATCH_RE = re.compile(
    r"^update_v(.+?)_to_v(.+?)\.zip$", re.IGNORECASE
)


class UpdateChecker:
    """启动时自动检测补丁文件。

    用法:
        checker = UpdateChecker()
        result = checker.scan()
        if result:
            # 弹出 UpdateFoundDialog
            pass
    """

    def __init__(self):
        self._project_root = get_project_root()
        self._current_version = get_config_version()
        self._ignored_list: list[dict] = []

    def scan(self) -> dict | None:
        """扫描项目根目录，查找可用的补丁文件。

        Returns:
            检测到有效补丁时返回 dict，否则返回 None::

                {
                    "patch_filename": "update_v5.0.0_to_v5.1.0.zip",
                    "patch_path": "/full/path/to/...",
                    "manifest": {...},
                    "to_version": "5.1.0",
                    "release_notes": "...",
                    "file_stats": {"add": N, "modify": N, "delete": N},
                    "config_affected": bool,
                }
        """
        self._load_ignore()

        # 扫描根目录下所有 .zip 文件
        candidates = []
        for fname in os.listdir(self._project_root):
            if not fname.lower().endswith(".zip"):
                continue
            match = _PATCH_RE.match(fname)
            if not match:
                continue

            # 检查是否在忽略列表中
            if self._is_ignored(fname):
                logger.info(f"跳过已忽略的补丁: {fname}")
                continue

            full_path = os.path.join(self._project_root, fname)
            candidates.append((fname, full_path))

        # 逐个验证
        for filename, filepath in candidates:
            result = self._validate_patch(filename, filepath)
            if result:
                return result

        return None

    def _load_ignore(self) -> None:
        """加载忽略列表。"""
        try:
            self._ignored_list = load_ignore_list()
        except Exception:
            self._ignored_list = []

    def _is_ignored(self, filename: str) -> bool:
        """检查补丁是否被忽略。"""
        return any(e["filename"] == filename for e in self._ignored_list)

    def _validate_patch(
        self, filename: str, filepath: str,
    ) -> dict | None:
        """验证单个补丁文件的合法性。"""
        # 读取 manifest
        manifest = read_manifest(filepath)
        if not manifest:
            logger.warning(f"无法读取 manifest.json: {filename}")
            return None

        # 版本校验
        compatible, error_msg = validate_patch_compatibility(
            manifest, self._current_version,
        )
        if not compatible:
            logger.warning(f"补丁不兼容 ({filename}): {error_msg}")
            return None

        to_version = manifest.get("to_version", "")
        release_notes = manifest.get("release_notes", "")
        changes = manifest.get("changes", [])

        # 统计变更
        add_count = sum(1 for c in changes if c["action"] == "add")
        mod_count = sum(1 for c in changes if c["action"] == "modify")
        del_count = sum(1 for c in changes if c["action"] == "delete")

        # 判断是否涉及 config/ 目录
        config_paths = [
            c for c in changes
            if c["action"] in ("add", "modify")
            and c["path"].startswith("config/")
        ]

        logger.info(
            f"发现可用补丁: {filename} "
            f"({self._current_version} → {to_version}), "
            f"+{add_count} ~{mod_count} -{del_count}"
        )

        return {
            "patch_filename": filename,
            "patch_path": filepath,
            "manifest": manifest,
            "to_version": to_version,
            "release_notes": release_notes,
            "file_stats": {
                "add": add_count,
                "modify": mod_count,
                "delete": del_count,
            },
            "config_affected": len(config_paths) > 0,
            "config_files": [c["path"] for c in config_paths],
        }
