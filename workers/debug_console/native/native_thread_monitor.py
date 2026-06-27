"""线程健康监视器 — NativeThreadMonitor (M3 v1.2.0)

4 类检测:
  1. 线程存活扫描 (每 10s) — 发现消失的线程 → thread_died
  2. 线程卡死检测 (每 5s) — 栈帧 30s 未变化 → thread_stuck
  3. 死锁嫌疑检测 (每 30s) — Lock.acquire 等待 60s → deadlock_suspect
  4. Qt 主循环心跳 (每 3s) — QTimer 5s 无更新 → main_loop_no_resp

独立性: 所有检测均通过 sys._current_frames() + threading.enumerate()
完成，不依赖 Qt 事件循环（除 Qt heartbeat 需外部 QTimer 驱动）。
"""

import sys
import time
import threading
from typing import Optional


class NativeThreadMonitor:
    """线程健康监视器 — 独立守护线程运行。"""

    # 默认配置（可从 native_log_config.json 覆盖）
    ALIVE_SCAN_INTERVAL = 10.0
    STUCK_SCAN_INTERVAL = 5.0
    STUCK_THRESHOLD = 30.0          # 栈帧 30s 不变 → 卡死
    DEADLOCK_SCAN_INTERVAL = 30.0
    DEADLOCK_THRESHOLD = 60.0       # Lock.acquire 等待 60s → 死锁嫌疑
    QT_HEARTBEAT_INTERVAL = 3.0
    QT_HEARTBEAT_TIMEOUT = 5.0      # Qt 主循环 5s 无响应 → 阻塞

    def __init__(self, manager):
        """Args:
            manager: NativeEventManager 实例（用于 write_raw_event）
        """
        self._manager = manager
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # 线程卡死检测状态: thread_id -> (frame_signature, timestamp)
        self._stuck_cache: dict = {}

        # 死锁嫌疑检测状态: "deadlock_{tid}" -> (frame_signature, timestamp)
        self._deadlock_cache: dict = {}

        # 已报告的线程（防重复）
        self._reported_stuck: set = set()
        self._reported_deadlock: set = set()

        # 线程存活检测
        self._known_threads: dict = {}   # tid -> name
        self._reported_died: set = set()

        # Qt 心跳
        self._qt_heartbeat_ts: float = 0.0
        self._qt_initialized: bool = False

    # ── 外部控制 ─────────────────────────────────────

    def set_qt_heartbeat(self):
        """更新 Qt 主循环心跳（由外部 QTimer 每秒调用）。"""
        self._qt_heartbeat_ts = time.time()
        self._qt_initialized = True

    def start(self):
        """启动监视器守护线程。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="NativeThreadMonitor"
        )
        self._thread.start()

    def stop(self):
        """停止监视器。"""
        self._running = False

    # ── 主循环 ───────────────────────────────────────

    def _run(self):
        """监视器主循环 — 每秒 tick 一次，按间隔分派检测。"""
        last_alive = 0.0
        last_stuck = 0.0
        last_deadlock = 0.0
        last_qt = 0.0

        while self._running:
            now = time.time()

            if now - last_alive >= self.ALIVE_SCAN_INTERVAL:
                self._scan_thread_alive(now)
                last_alive = now

            if now - last_stuck >= self.STUCK_SCAN_INTERVAL:
                self._scan_thread_stuck(now)
                last_stuck = now

            if now - last_deadlock >= self.DEADLOCK_SCAN_INTERVAL:
                self._scan_deadlock_suspect(now)
                last_deadlock = now

            if now - last_qt >= self.QT_HEARTBEAT_INTERVAL:
                self._check_qt_heartbeat(now)
                last_qt = now

            time.sleep(1.0)

    # ── 检测 1: 线程存活 ─────────────────────────────

    def _scan_thread_alive(self, now: float):
        """检测线程消失（非预期终止）。"""
        current = {}
        for t in threading.enumerate():
            tid = t.ident
            if tid is not None:
                current[tid] = t.name

        # 检查已记录的线程是否消失
        for tid, tname in list(self._known_threads.items()):
            if tid not in current and tid not in self._reported_died:
                self._reported_died.add(tid)

                data = {
                    "kind": "thread_died",
                    "thread_id": tid,
                    "thread_name": tname[:50],
                    "last_func": "",
                    "stuck_seconds": 0.0,
                    "detail": f"Thread {tname} (ID={tid}) is no longer alive"[:500],
                }
                self._manager.write_raw_event("thread_events", data)
                self._manager.write_text_event(
                    "thread_events", "thread_died",
                    "NativeThreadMonitor",
                    f"Thread died: {tname} (ID={tid})",
                )

        self._known_threads = current

    # ── 检测 2: 线程卡死 ─────────────────────────────

    def _scan_thread_stuck(self, now: float):
        """检测线程卡死（栈帧长时间未变化）。"""
        try:
            frames = sys._current_frames()
        except Exception:
            return

        main_tid = threading.main_thread().ident

        for tid, frame in frames.items():
            if tid == main_tid:
                continue  # 跳过主线程
            if tid not in self._known_threads:
                continue  # 跳过未知线程

            sig = self._frame_signature(frame)
            tname = self._known_threads.get(tid, f"Thread-{tid}")

            if tid in self._stuck_cache:
                prev_sig, prev_ts = self._stuck_cache[tid]
                if sig == prev_sig:
                    stuck_for = now - prev_ts
                    if stuck_for >= self.STUCK_THRESHOLD and tid not in self._reported_stuck:
                        self._reported_stuck.add(tid)

                        data = {
                            "kind": "thread_stuck",
                            "thread_id": tid,
                            "thread_name": tname[:50],
                            "last_func": self._frame_top_func(frame)[:200],
                            "stuck_seconds": stuck_for,
                            "detail": f"Stack unchanged for {stuck_for:.0f}s: {sig[:200]}"[:500],
                        }
                        self._manager.write_raw_event("thread_events", data)
                        self._manager.write_text_event(
                            "thread_events", "thread_stuck",
                            "NativeThreadMonitor",
                            f"Thread stuck: {tname} stuck for {stuck_for:.0f}s at {sig[:100]}",
                        )
                else:
                    # 帧变化了 → 解除卡死标记
                    self._stuck_cache[tid] = (sig, now)
                    self._reported_stuck.discard(tid)
            else:
                self._stuck_cache[tid] = (sig, now)

    # ── 检测 3: 死锁嫌疑 ─────────────────────────────

    def _scan_deadlock_suspect(self, now: float):
        """检测死锁嫌疑（Lock.acquire 长时间阻塞）。"""
        try:
            frames = sys._current_frames()
        except Exception:
            return

        for tid, frame in frames.items():
            # 沿调用栈查找是否卡在 Lock.acquire 中
            f = frame
            lock_depth = 0
            lock_location = ""
            while f and lock_depth < 20:
                code = f.f_code
                fn = code.co_name
                filename = (code.co_filename or "").replace('\\', '/')

                if ('acquire' in fn and
                    any(m in filename for m in ('threading', '_thread', 'lock', 'condition'))):
                    lock_depth += 1
                    lock_location = (
                        f"{filename.split('/')[-1]}:{f.f_lineno}:{fn}"
                    )
                f = f.f_back

            if lock_depth == 0:
                continue  # 不在锁等待中

            # 检测是否持久阻塞
            cache_key = f"deadlock_{tid}"
            tname = self._known_threads.get(tid, f"Thread-{tid}")
            sig = self._frame_signature(frame)

            if (cache_key in self._deadlock_cache and
                cache_key not in self._reported_deadlock):
                prev_sig, prev_ts = self._deadlock_cache[cache_key]
                if sig == prev_sig:
                    stuck_for = now - prev_ts
                    if stuck_for >= self.DEADLOCK_THRESHOLD:
                        self._reported_deadlock.add(cache_key)

                        data = {
                            "kind": "deadlock_suspect",
                            "thread_id": tid,
                            "thread_name": tname[:50],
                            "last_func": lock_location[:200],
                            "stuck_seconds": stuck_for,
                            "detail": (
                                f"Thread stuck in Lock.acquire for "
                                f"{stuck_for:.0f}s at {lock_location[:200]}"
                            )[:500],
                        }
                        self._manager.write_raw_event("thread_events", data)
                        self._manager.write_text_event(
                            "thread_events", "deadlock_suspect",
                            "NativeThreadMonitor",
                            f"Deadlock suspect: {tname} in Lock.acquire for {stuck_for:.0f}s",
                        )
                else:
                    self._deadlock_cache[cache_key] = (sig, now)
            else:
                self._deadlock_cache[cache_key] = (sig, now)

    # ── 检测 4: Qt 主循环心跳 ────────────────────────

    def _check_qt_heartbeat(self, now: float):
        """检测 Qt 主循环是否阻塞。"""
        if not self._qt_initialized:
            return

        elapsed = now - self._qt_heartbeat_ts
        if elapsed >= self.QT_HEARTBEAT_TIMEOUT:
            data = {
                "kind": "main_loop_no_resp",
                "thread_id": threading.main_thread().ident or 0,
                "thread_name": "MainThread",
                "last_func": "",
                "stuck_seconds": elapsed,
                "detail": f"Qt main loop no heartbeat for {elapsed:.0f}s"[:500],
            }
            self._manager.write_raw_event("thread_events", data)
            self._manager.write_text_event(
                "thread_events", "main_loop_no_resp",
                "NativeThreadMonitor",
                f"Qt main loop not responding for {elapsed:.0f}s",
            )

    # ── 辅助 ──────────────────────────────────────────

    @staticmethod
    def _frame_signature(frame) -> str:
        """生成栈帧签名（文件名:行号:函数名 的串联，最多 10 帧）。"""
        parts = []
        f = frame
        for _ in range(10):
            if f is None:
                break
            code = f.f_code
            fname = (code.co_filename or '?').split('\\')[-1].split('/')[-1]
            parts.append(f"{fname}:{f.f_lineno}:{code.co_name}")
            f = f.f_back
        return "|".join(parts)

    @staticmethod
    def _frame_top_func(frame) -> str:
        """获取栈顶函数信息。"""
        if frame is None:
            return ""
        code = frame.f_code
        fname = (code.co_filename or '?').split('\\')[-1].split('/')[-1]
        return f"{fname}:{frame.f_lineno}:{code.co_name}"
