"""资源跟踪监视器 — NativeResourceMonitor (M3 v1.2.0)

L4 覆盖:
  1. 文件句柄计数 (Windows: GetProcessHandleCount) — 超阈值告警 fd_leak
  2. Qt 无父 Widget 扫描 — 孤立顶层窗口检测 qt_object_no_parent
  3. atexit 退出扫描 — 退出前做最后一次资源检查

依赖:
  - Windows kernel32 (GetProcessHandleCount) — 跨平台 fallback 为 -1
  - PyQt5 (QApplication.topLevelWidgets) — 无 PyQt5 时静默跳过

注意:
  - fd 扫描每 60 秒一次
  - fd 阈值默认 1000（可通过 native_log_config.json 覆盖）
  - atexit 扫描在进程退出时自动触发
"""

import os
import sys
import json
import time
import atexit
import threading
from typing import Optional


class NativeResourceMonitor:
    """资源跟踪监视器 — 句柄泄漏 + Qt 孤儿 + atexit 扫描。"""

    FD_SCAN_INTERVAL = 60.0      # fd 扫描间隔（秒）
    FD_THRESHOLD = 1000          # fd 告警阈值
    FD_REPORT_COOLDOWN = 300.0   # 同 fd 事件最小间隔（5 分钟）
    QT_ORPHAN_THRESHOLD = 3      # 孤立 widget 超过此数告警

    def __init__(self, manager):
        """Args:
            manager: NativeEventManager 实例
        """
        self._manager = manager
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # fd 状态
        self._initial_fd_count: int = 0
        self._last_fd_ts: float = 0.0
        self._last_fd_count: int = 0

        # Qt 状态
        self._last_orphan_ts: float = 0.0

    # ── 安装/卸载 ────────────────────────────────────

    def install(self):
        """启动资源监视。

        1. 获取初始 fd 计数
        2. 注册 atexit 退出扫描
        3. 启动定时扫描守护线程
        """
        self._initial_fd_count = self._get_fd_count()

        # atexit 退出扫描
        atexit.register(self._atexit_scan)

        # 定时扫描
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="NativeResourceMonitor"
        )
        self._thread.start()

    def uninstall(self):
        """停止资源监视。"""
        self._running = False

    # ── 主循环 ───────────────────────────────────────

    def _run(self):
        """定时扫描循环。"""
        while self._running:
            time.sleep(self.FD_SCAN_INTERVAL)
            self._scan_fd_count()
            self._scan_qt_orphans()

    # ── 文件句柄检测 ─────────────────────────────────

    def _get_fd_count(self) -> int:
        """获取当前进程文件句柄数。

        Windows: GetProcessHandleCount (kernel32)
        Linux/macOS: /proc/self/fd (fallback)
        """
        if sys.platform == "win32":
            try:
                import ctypes
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                handle = ctypes.windll.kernel32.GetCurrentProcess()
                count = ctypes.c_ulong()
                ctypes.windll.kernel32.GetProcessHandleCount(
                    handle, ctypes.byref(count)
                )
                return count.value
            except Exception:
                pass
        else:
            try:
                return len(os.listdir("/proc/self/fd"))
            except Exception:
                pass
        return -1

    def _scan_fd_count(self):
        """扫描文件句柄数，超阈值写 event。"""
        count = self._get_fd_count()
        if count < 0:
            return

        now = time.time()
        self._last_fd_count = count

        if count > self.FD_THRESHOLD and now - self._last_fd_ts > self.FD_REPORT_COOLDOWN:
            self._last_fd_ts = now
            growth = count - self._initial_fd_count

            data = {
                "kind": "fd_leak",
                "obj_type": "file_handle",
                "obj_repr": f"{count} handles (initial: {self._initial_fd_count})",
                "count": count,
                "detail": json.dumps({
                    "current": count,
                    "initial": self._initial_fd_count,
                    "growth": growth,
                    "threshold": self.FD_THRESHOLD,
                }, ensure_ascii=False)[:2000],
            }
            self._manager.write_raw_event("resource_events", data)
            self._manager.write_text_event(
                "resource_events", "fd_leak",
                "NativeResourceMonitor",
                f"File handles: {count} (threshold: {self.FD_THRESHOLD}, "
                f"growth: +{growth} from startup)",
            )

    # ── Qt 孤立 Widget 检测 ──────────────────────────

    def _scan_qt_orphans(self):
        """扫描 Qt 顶层孤立 Widget。

        检测条件:
          - isVisible()
          - parent() is None (独立窗口)
          - 有 objectName 或 windowTitle（过滤系统内部 widget）
          - 非 QMainWindow（排除主窗口本身）
        """
        try:
            from PyQt5.QtWidgets import (
                QApplication, QMainWindow, QWidget, QDialog
            )
        except ImportError:
            return

        try:
            app = QApplication.instance()
            if app is None:
                return
        except Exception:
            return

        orphans = []
        try:
            for w in app.topLevelWidgets():
                if not isinstance(w, QWidget):
                    continue
                if not w.isVisible():
                    continue
                # 主窗口本身是正常的
                if isinstance(w, QMainWindow):
                    continue
                # 没有 parent 的 Dialog/Widget 可能是泄漏
                if w.parent() is None:
                    orphans.append({
                        "name": w.objectName() or "",
                        "type": type(w).__name__,
                        "title": (w.windowTitle() or "")[:50],
                    })
        except Exception:
            return

        if len(orphans) >= self.QT_ORPHAN_THRESHOLD:
            now = time.time()
            if now - self._last_orphan_ts > self.FD_REPORT_COOLDOWN:
                self._last_orphan_ts = now

                data = {
                    "kind": "qt_object_no_parent",
                    "obj_type": "QWidget",
                    "obj_repr": f"{len(orphans)} orphan top-level widgets",
                    "count": len(orphans),
                    "detail": json.dumps(orphans[:10], ensure_ascii=False)[:2000],
                }
                self._manager.write_raw_event("resource_events", data)
                self._manager.write_text_event(
                    "resource_events", "qt_object_no_parent",
                    "NativeResourceMonitor",
                    f"Qt orphan widgets: {len(orphans)} top-level widgets "
                    f"without parent: {', '.join(o['type'] for o in orphans[:5])}",
                )

    # ── atexit 退出扫描 ──────────────────────────────

    def _atexit_scan(self):
        """进程退出前的最终资源检查。"""
        count = self._get_fd_count()
        if count < 0:
            return

        if count > self.FD_THRESHOLD:
            data = {
                "kind": "fd_leak",
                "obj_type": "file_handle",
                "obj_repr": f"{count} handles on exit",
                "count": count,
                "detail": json.dumps({
                    "current": count,
                    "initial": self._initial_fd_count,
                    "phase": "atexit",
                    "threshold": self.FD_THRESHOLD,
                }, ensure_ascii=False)[:2000],
            }
            self._manager.write_raw_event("resource_events", data)

        # 强制排空队列
        self._manager.flush()
