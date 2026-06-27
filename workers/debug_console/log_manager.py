"""日志管理器 — 日志写入、导出、自动清理

LogManager 负责：
  - 将日志条目写入 docs/log/debug_YYYYMMDD_HHMMSS.log
  - 启动时自动清理超过 7 天的旧 debug_*.log
  - 导出当前会话日志到指定文件
"""

import os
import time
from datetime import datetime, timedelta
from typing import Callable, Optional


class LogManager:
    """调试台日志管理器"""

    LOG_DIR = "docs/log"  # 相对于项目根目录
    LOG_PREFIX = "debug_"
    LOG_SUFFIX = ".log"
    MAX_AGE_DAYS = 7

    def __init__(self, project_root: str):
        self._project_root = project_root
        self._log_dir = os.path.join(project_root, self.LOG_DIR)
        self._log_path: Optional[str] = None
        self._entries: list[str] = []
        self._log_callback: Optional[Callable[[str], None]] = None

        # 确保日志目录存在
        os.makedirs(self._log_dir, exist_ok=True)

        # 创建本次会话的日志文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_path = os.path.join(
            self._log_dir, f"{self.LOG_PREFIX}{timestamp}{self.LOG_SUFFIX}"
        )

    # ── 属性 ──────────────────────────────────────────────────

    @property
    def log_path(self) -> str:
        return self._log_path or ""

    @property
    def log_dir(self) -> str:
        return self._log_dir

    @property
    def entries(self) -> list[str]:
        return self._entries

    def set_log_callback(self, callback: Callable[[str], None]):
        """设置日志追加回调（用于 UI 实时刷新）。"""
        self._log_callback = callback

    # ── 日志写入 ──────────────────────────────────────────────

    def log(self, level: str, message: str):
        """记录一条日志。

        Args:
            level: 日志级别 (INFO/WARN/ERROR/DEBUG)
            message: 日志内容
        """
        now = datetime.now()
        timestamp = now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"
        entry = f"[{timestamp}] [{level}] {message}"

        self._entries.append(entry)

        # 写入文件
        if self._log_path:
            try:
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(entry + "\n")
            except OSError:
                pass

        # 通知 UI 回调
        if self._log_callback:
            self._log_callback(entry)

    def info(self, message: str):
        self.log("INFO", message)

    def warn(self, message: str):
        self.log("WARN", message)

    def error(self, message: str):
        self.log("ERROR", message)

    def debug(self, message: str):
        self.log("DEBUG", message)

    # ── 日志导出 ──────────────────────────────────────────────

    def export_log(self, export_path: Optional[str] = None) -> str:
        """导出当前会话日志到指定文件。

        Args:
            export_path: 目标文件路径，为 None 时使用默认路径

        Returns:
            实际保存的文件路径
        """
        if export_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_path = os.path.join(
                self._log_dir, f"export_{timestamp}.log"
            )

        try:
            with open(export_path, "w", encoding="utf-8") as f:
                for entry in self._entries:
                    f.write(entry + "\n")
            return export_path
        except OSError:
            return ""

    # ── 自动清理 ──────────────────────────────────────────────

    def auto_clean(self) -> int:
        """自动清理超过 MAX_AGE_DAYS 天的旧日志文件。

        仅删除 debug_*.log 文件，保留其他文件（如 .md 文档）。

        Returns:
            删除的文件数量
        """
        if not os.path.isdir(self._log_dir):
            return 0

        cutoff = time.time() - self.MAX_AGE_DAYS * 24 * 3600
        deleted = 0

        try:
            for fname in os.listdir(self._log_dir):
                if not (fname.startswith(self.LOG_PREFIX) and fname.endswith(self.LOG_SUFFIX)):
                    continue

                fpath = os.path.join(self._log_dir, fname)
                try:
                    mtime = os.path.getmtime(fpath)
                except OSError:
                    continue

                if mtime < cutoff:
                    try:
                        os.remove(fpath)
                        deleted += 1
                    except OSError:
                        pass
        except OSError:
            pass

        return deleted

    def manual_clean(self) -> int:
        """手动触发清理（与 auto_clean 相同逻辑）。"""
        return self.auto_clean()

    # ── 日志查询 ──────────────────────────────────────────────

    def get_entries_by_level(self, level: str) -> list[str]:
        """按级别筛选日志条目。"""
        pattern = f"[{level}]"
        return [e for e in self._entries if pattern in e]

    def get_entry_count(self) -> int:
        return len(self._entries)
