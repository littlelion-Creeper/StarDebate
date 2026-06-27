"""StarDebate 日志服务 — 独立进程运行，与主窗口解耦 (v2.1.0)
============================================================================
v2.1.0 新增功能（崩溃定位优化）:
  ★ 守护日志环 — LogClient 内部环形缓冲区，崩溃前最后 N 条日志不丢失
  ★ sys.excepthook — 捕获 Python 未捕获异常，自动关联起居注上下文
  ★ Qt message handler — 拦截 Qt C++ 层 qWarning/qCritical/qFatal
  ★ 崩溃自动分析 — SystemHealthMonitor 分析崩溃前日志，输出诊断摘要
  ★ chronicle 快照传递 — closeEvent 发送 lineage 快照至 LogService

职责：
  - 独立 multiprocessing.Process，主窗口崩溃不影响日志写入
  - 拥有独立的 LogManager 实例，统一管理日志文件
  - 通过 multiprocessing.Queue 接收日志/监视/控制指令
  - 内置 SystemHealthMonitor 线程：主进程存活检测 + 背压监控 + 心跳超时
  - 对外提供 LogClient 轻量客户端（供主进程使用）
  - ★ 内嵌 ActivityChronicle 起居注：自动追踪功能/插件/API/AI 成功/失败

使用方式:
    # 启动器侧
    from star_debate_log import LogService, LogClient

    log_service = LogService(project_root, log_queue, result_queue)
    log_service.start()
    log_path = result_queue.get(timeout=10)['log_path']

    log_client = LogClient(log_queue, log_path)
    log_client.info("应用启动")

    # ★ 起居注装饰器:
    @log_client.track("feature", "my_func")
    def my_func(): ...

    # ★ 起居注上下文管理器:
    with log_client.track_ctx("api", "endpoint"):
        do_request()

    # 关闭时
    log_client.shutdown()
    log_service.join(timeout=5)

依赖:
  - workers/debug_console/log_manager.py → LogManager
  - workers/debug_console/chronicle → ActivityChronicle (起居注)
  - 所有日志写入由 LogService 进程独占，避免文件竞争
============================================================================
"""
import os
import sys
import time
import json
import sqlite3
import ctypes
import threading
import collections
import multiprocessing
import traceback as tb_module
from datetime import datetime
from typing import Optional


# ── 日志管理器（由 LogService 进程独占）─────────────────────────────
from workers.debug_console.log_manager import LogManager

# ── 起居注（LogClient 内嵌组件）───────────────────────────────────
from workers.debug_console.chronicle import ActivityChronicle, ChronicleContext


# ============================================================================
#  LogClient — 主进程使用的轻量日志客户端（通过队列发送，非阻塞）
# ============================================================================

class LogClient:
    """轻量日志发送客户端 (v2.1.0 崩溃定位增强)。

    在主进程中使用，将所有日志/监视指令通过 multiprocessing.Queue
    发送到 LogService 独立进程。队列满或断开时自动降级为文件直写。

    ★ 内嵌 ActivityChronicle 起居注：error/warn 自动标记上下文，
      装饰器/上下文管理器自动追踪操作成功/失败。标签: [CRON]

    ★ v2.1.0 新增:
      - 守护日志环 (_ring_buffer): 内存中保留最近 N 条日志，崩溃时随快照写入
      - sys.excepthook 注入: 捕获未处理异常
      - Qt message handler 注入: 拦截 Qt 内部错误
    """

    # 守护日志环默认容量
    DEFAULT_RING_SIZE = 200

    def __init__(self, log_queue: multiprocessing.Queue, log_path: Optional[str] = None,
                 ring_size: int = None):
        self._queue = log_queue
        self._log_path = log_path
        self._emergency_count = 0
        self._last_success_ts = time.time()

        # ★ v2.1.0 守护日志环
        self._ring_size = ring_size or self.DEFAULT_RING_SIZE
        self._ring_buffer = collections.deque(maxlen=self._ring_size)
        self._ring_lock = threading.Lock()

        # ★ 起居注 (内嵌组件)
        self._chronicle = ActivityChronicle(self)

        # ★ v2.1.0 安装全局异常钩子
        self._install_global_hooks()

    # ── ★ v2.1.0 全局异常钩子 ──────────────────────────────────

    def _install_global_hooks(self):
        """安装全局异常钩子（sys.excepthook + Qt message handler）。

        注意：Qt message handler 需要在 QApplication 创建后安装，
        由 StarDebate_app._init_chronicle() 在 QApplication 创建后调用。
        """
        # sys.excepthook: 捕获 Python 未捕获异常
        self._orig_excepthook = sys.excepthook

        def _chronicle_excepthook(etype, value, tb):
            """未捕获异常统一出口 → 起居注自动标记。

            ★ v2.2.0: 增强鲁棒性
            - try/except 内每步独立保护，避免日志环节卡住整个进程
            - 始终调用原始 hook 输出到 stderr（内层 + 外层双重保障）
            - 紧急情况直接 sys.__excepthook__ 兜底
            """
            # 第一步：无论如何先把异常信息写到 stderr（不依赖任何队列）
            try:
                default_hook = getattr(sys, '__excepthook__', sys.excepthook)
                if default_hook is not _chronicle_excepthook:
                    default_hook(etype, value, tb)
                elif self._orig_excepthook:
                    self._orig_excepthook(etype, value, tb)
            except Exception:
                pass

            # 第二步：轻量内存操作（环形缓冲区）
            try:
                self._ring_snapshot(
                    f"[UNCAUGHT] {etype.__name__}: {value}"
                )
            except Exception:
                pass

            # 第三步：起居注记录
            try:
                self._chronicle._on_exception(etype, value, tb)
            except Exception:
                pass

            # 第四步：traceback 提取和记录（有超时风险的操作独立 try）
            try:
                tb_str = "".join(tb_module.format_exception(etype, value, tb))
                self.error(f"[UNCAUGHT] {etype.__name__}: {value}")
                with self._ring_lock:
                    for line in tb_str.splitlines()[-20:]:
                        self._ring_buffer.append(
                            (time.time(), "ERROR", f"[TB] {line.strip()}")
                        )
            except Exception:
                # 队列投递失败 → 紧急直写 stderr
                try:
                    sys.stderr.write(
                        f"[UNCAUGHT] {etype.__name__}: {value}\n"
                    )
                except Exception:
                    pass

        sys.excepthook = _chronicle_excepthook

    def install_qt_handler(self):
        """安装 Qt message handler（需在 QApplication 创建后调用）。

        拦截 QMessageHandler 级别的 qWarning/qCritical/qFatal，
        自动关联起居注上下文标记。

        ★ 记录完整 QMessageLogContext（文件/行号/函数/分类 + 错误代码）
        """
        try:
            from PyQt5.QtCore import qInstallMessageHandler, QtMsgType
        except ImportError:
            return

        # QtMsgType 错误代码映射
        _QT_MSG_NAMES = {
            QtMsgType.QtDebugMsg: ("DEBUG", 0),
            QtMsgType.QtWarningMsg: ("WARN", 1),
            QtMsgType.QtCriticalMsg: ("CRITICAL", 2),
            QtMsgType.QtFatalMsg: ("FATAL", 3),
            QtMsgType.QtInfoMsg: ("INFO", 4),
        }

        # 保存原始 handler
        self._orig_qt_handler = None

        def _qt_message_handler(msg_type, context, msg):
            """Qt 内部消息拦截 → 起居注自动记录（含完整上下文）。"""
            try:
                # 提取 QMessageLogContext 信息
                ctx_file = getattr(context, 'file', '') or ''
                ctx_line = getattr(context, 'line', 0) or 0
                ctx_func = getattr(context, 'function', '') or ''
                ctx_cat = getattr(context, 'category', '') or ''

                # 构建定位串: qwidget.cpp:L4832:QWidget::setParent
                loc_parts = []
                if ctx_file:
                    fname = ctx_file.split('/')[-1].split('\\')[-1]
                    loc_parts.append(fname)
                if ctx_line:
                    loc_parts.append(f"L{ctx_line}")
                if ctx_func:
                    fn = ctx_func.split('(')[0].split('::')[-1]
                    if fn and len(fn) < 60:
                        loc_parts.append(fn)
                location = ":".join(loc_parts) if loc_parts else ""
                loc_suffix = f" [{location}]" if location else ""
                type_name, type_code = _QT_MSG_NAMES.get(msg_type, ("?", -1))

                if msg_type == QtMsgType.QtFatalMsg:
                    full_msg = f"[Qt {type_name}#{type_code}]{loc_suffix} {msg[:200]}"
                    self._chronicle._on_error("ERROR", full_msg)
                    self.error(full_msg)
                elif msg_type == QtMsgType.QtCriticalMsg:
                    full_msg = f"[Qt {type_name}#{type_code}]{loc_suffix} {msg[:200]}"
                    self._chronicle._on_error("ERROR", full_msg)
                    self.error(full_msg)
                elif msg_type == QtMsgType.QtWarningMsg:
                    full_msg = f"[Qt {type_name}#{type_code}]{loc_suffix} {msg[:200]}"
                    self.warn(full_msg)
            except Exception:
                pass

        self._orig_qt_handler = qInstallMessageHandler(_qt_message_handler)

    def uninstall_qt_handler(self):
        """恢复 Qt message handler。"""
        if hasattr(self, '_orig_qt_handler') and self._orig_qt_handler:
            try:
                from PyQt5.QtCore import qInstallMessageHandler
                qInstallMessageHandler(self._orig_qt_handler)
            except Exception:
                pass

    def uninstall_global_hooks(self):
        """卸载全局异常钩子，恢复原始状态。"""
        if hasattr(self, '_orig_excepthook') and self._orig_excepthook:
            sys.excepthook = self._orig_excepthook
        self.uninstall_qt_handler()

    # ── ★ v2.1.0 守护日志环 ──────────────────────────────────

    def _ring_snapshot(self, message: str):
        """写入环形缓冲区（不经过队列，崩溃时保留本地）。"""
        with self._ring_lock:
            self._ring_buffer.append(
                (time.time(), "SNAP", message)
            )

    def dump_ring_buffer(self) -> list:
        """导出环形缓冲区全部内容（崩溃快照用）。"""
        with self._ring_lock:
            return list(self._ring_buffer)

    def get_ring_size(self) -> int:
        """获取环形缓冲区当前条目数。"""
        with self._ring_lock:
            return len(self._ring_buffer)

    # ── 公开日志方法 ──────────────────────────────────────────

    def info(self, message: str):
        self._send("INFO", message)

    def warn(self, message: str):
        self._send("WARN", message)
        self._chronicle._on_error("WARN", message)  # ★ 起居注: 标记当前上下文错误

    def error(self, message: str):
        self._send("ERROR", message)
        self._chronicle._on_error("ERROR", message)  # ★ 起居注: 标记当前上下文错误

    def debug(self, message: str):
        self._send("DEBUG", message)

    def log(self, level: str, message: str):
        """兼容 LogManager.log() 接口。"""
        self._send(level, message)
        if level in ("ERROR", "WARN"):
            self._chronicle._on_error(level, message)  # ★ 起居注

    # ── 监视专用通道 ──────────────────────────────────────────

    def monitor(self, tag: str, message: str):
        """发送监视钩子日志（带标签）。"""
        self._send_monitor(tag, message)

    # ── 控制指令 ──────────────────────────────────────────────

    def shutdown(self):
        """通知 LogService 正常退出。"""
        try:
            self._queue.put_nowait({"type": "shutdown"})
        except Exception:
            pass

    def set_emergency_info(self, emergency_count: int, last_heartbeat: float,
                           chronicle_snapshot: dict = None,
                           ring_buffer_data: list = None):
        """主进程关闭前向 LogService 发送应急统计（用于崩溃快照）。

        ★ v2.1.0: 新增 chronicle_snapshot + ring_buffer_data
        """
        try:
            payload = {
                "type": "emergency_info",
                "emergency_count": emergency_count,
                "last_heartbeat": last_heartbeat,
            }
            if chronicle_snapshot is not None:
                payload["chronicle_snapshot"] = chronicle_snapshot
            if ring_buffer_data is not None:
                payload["ring_buffer_data"] = ring_buffer_data
            self._queue.put_nowait(payload)
        except Exception:
            pass

    # ── ★ 起居注公开 API ─────────────────────────────────────

    def track(self, category: str, name: str = None, metadata: dict = None):
        """装饰器工厂：自动追踪函数执行。标签: [CRON]

        用法:
            @log_client.track("feature", "ai_analysis")
            def run(): ...

            @log_client.track("api")
            def call(): ...  # name 自动取 func.__name__

            @log_client.track("feature", "export", metadata={"path": "/x"})
            def export(): ...  # ★ v2.0.0 元数据

        函数正常返回 → [CRON] ✅ category·name → ok (ms)
        函数内 error/warn → [CRON] ❌ category·name → failed (ms): detail
        """
        return self._chronicle.track(category, name, metadata)

    def track_ctx(self, category: str, name: str, metadata: dict = None):
        """上下文管理器：自动追踪 with 块执行。标签: [CRON]

        用法:
            with log_client.track_ctx("api", "endpoint") as ctx:
                do_request()
                if fail:
                    log_client.error("failed")  # → ctx.has_error = True

        with 正常退出 → [CRON] ✓ category·name → ok (ms)
        with 内 error/warn → [CRON] ❌ category·name → failed (ms): detail
        """
        return self._chronicle.track_ctx(category, name, metadata)

    @property
    def chronicle_enabled(self) -> bool:
        """起居注总开关。"""
        return self._chronicle.enabled

    @chronicle_enabled.setter
    def chronicle_enabled(self, value: bool):
        self._chronicle.enabled = value

    @property
    def chronicle(self) -> ActivityChronicle:
        """起居注实例（供高级用法）。"""
        return self._chronicle

    # ── 内部方法 ──────────────────────────────────────────────

    def _send(self, level: str, message: str):
        """发送普通日志指令。队列满/断时降级为文件直写。

        ★ v2.1.0: 同时写入守护日志环
        """
        # ★ 写入环形缓冲区
        with self._ring_lock:
            self._ring_buffer.append(
                (time.time(), level, message)
            )

        try:
            self._queue.put_nowait({
                "type": "log",
                "level": level,
                "message": str(message),
            })
            self._last_success_ts = time.time()
            # 恢复计数：连续成功说明队列恢复
            if self._emergency_count > 0:
                self._emergency_count = 0
        except Exception:
            self._emergency_write(level, str(message))

    def _send_monitor(self, tag: str, message: str):
        """发送监视钩子日志指令。

        ★ v2.2.0: 每 5 次监视调用附带一次环缓冲区快照
        """
        with self._ring_lock:
            self._ring_buffer.append(
                (time.time(), "MONITOR", f"[{tag}] {message}")
            )

        try:
            self._queue.put_nowait({
                "type": "monitor",
                "level": "INFO",
                "message": f"[{tag}] {message}",
                "timestamp": time.time(),
            })
            self._last_success_ts = time.time()
            if self._emergency_count > 0:
                self._emergency_count = 0
        except Exception:
            self._emergency_write("INFO", f"[{tag}] {message}")

        # ★ v2.2.0: 周期性发送环缓冲区快照（每 5 次监视触发一次）
        self._monitor_call_count = getattr(self, '_monitor_call_count', 0) + 1
        if self._monitor_call_count % 5 == 0:
            try:
                snap = self.dump_ring_buffer()
                chronicle_snap = self._chronicle.get_crash_snapshot()
                self._queue.put_nowait({
                    "type": "emergency_info",
                    "emergency_count": self._emergency_count,
                    "last_heartbeat": self._last_success_ts,
                    "ring_buffer_data": snap[-100:],  # 只传最近 100 条
                    "chronicle_snapshot": chronicle_snap,
                })
            except Exception:
                pass

    def _emergency_write(self, level: str, message: str):
        """应急降级：直接写日志文件（绕过队列，确保落盘）。

        当 LogService 进程崩溃或队列满时自动触发。
        每 10 次应急写入记录一次警告。
        """
        self._emergency_count += 1
        if not self._log_path:
            return
        try:
            now = datetime.now()
            ts = now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"
            entry = f"[{ts}] [{level}] {message}\n"

            # 每 10 次应急写入前追加一条警告
            if self._emergency_count == 1 or self._emergency_count % 10 == 0:
                warn_entry = (
                    f"[{ts}] [WARN] [EMERGENCY] 日志队列不可用，"
                    f"已降级为文件直写 (第{self._emergency_count}次)\n"
                )
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(warn_entry + entry)
            else:
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(entry)
        except Exception:
            pass

    @property
    def emergency_count(self) -> int:
        return self._emergency_count

    @property
    def last_heartbeat(self) -> float:
        return self._last_success_ts


# ============================================================================
#  SystemHealthMonitor — LogService 内的独立系统监视线程 (v2.1.0)
# ============================================================================

class SystemHealthMonitor(threading.Thread):
    """系统健康监视线程（在 LogService 进程内运行）(v2.1.0 崩溃分析增强)。

    职责：
      - 主进程 PID 存活检测（每 3 秒）
      - 日志队列背压监控
      - 监视心跳超时检测
      - 崩溃时写入系统快照 ★ 含起居注 lineage + 自动分析报告
      - ★ v2.1.0 守护日志环数据合并
    """

    CHECK_INTERVAL = 3.0  # 检测间隔（秒）
    HEARTBEAT_TIMEOUT = 15.0  # 心跳超时（秒）
    QUEUE_BACKPRESSURE_THRESHOLD = 500  # 队列积压阈值
    MAX_CONSECUTIVE_MISSES = 3  # 连续不可达次数才判定崩溃

    def __init__(self, main_pid: int, log_queue: multiprocessing.Queue, log_mgr: LogManager):
        super().__init__(daemon=True, name="SysHealthMonitor")
        self._main_pid = main_pid
        self._log_queue = log_queue
        self._log_mgr = log_mgr
        self._running = True
        self._crash_detected = False
        self._last_heartbeat = time.time()
        self._emergency_count = 0
        # ★ v2.1.0: 起居注快照数据
        self._chronicle_snapshot: dict = {}
        # ★ v2.1.0: 守护日志环数据
        self._ring_buffer_data: list = []

    def stop(self):
        """通知线程停止。"""
        self._running = False

    def update_heartbeat(self, timestamp: float):
        """更新主进程监视心跳时间（由收到的监视条目触发）。"""
        if timestamp > self._last_heartbeat:
            self._last_heartbeat = timestamp

    def update_emergency_info(self, emergency_count: int, last_heartbeat: float,
                              chronicle_snapshot: dict = None,
                              ring_buffer_data: list = None):
        """更新应急统计信息。

        ★ v2.1.0: 接收起居注快照 + 守护日志环数据
        """
        self._emergency_count = emergency_count
        if last_heartbeat > self._last_heartbeat:
            self._last_heartbeat = last_heartbeat
        if chronicle_snapshot is not None:
            self._chronicle_snapshot = chronicle_snapshot
        if ring_buffer_data is not None:
            self._ring_buffer_data = ring_buffer_data

    @property
    def crash_detected(self) -> bool:
        return self._crash_detected

    def run(self):
        """线程主循环。"""
        # 启动后等待 5 秒，避免启动期间误判
        time.sleep(5)

        consecutive_miss = 0

        while self._running:
            try:
                # ── ① 主进程存活检测 ──────────────────────
                alive = self._is_process_alive(self._main_pid)

                if not alive:
                    consecutive_miss += 1
                    if consecutive_miss >= self.MAX_CONSECUTIVE_MISSES:
                        self._on_main_process_crash()
                        break
                else:
                    consecutive_miss = 0

                # ── ② 队列背压监控 ────────────────────────
                try:
                    qsize = self._log_queue.qsize()
                    if qsize > self.QUEUE_BACKPRESSURE_THRESHOLD:
                        self._log_mgr.warn(
                            f"[SYS] 日志队列积压: {qsize} 条 (阈值: {self.QUEUE_BACKPRESSURE_THRESHOLD})"
                        )
                except NotImplementedError:
                    pass

                # ── ③ 监视心跳超时检测 ────────────────────
                elapsed = time.time() - self._last_heartbeat
                if elapsed > self.HEARTBEAT_TIMEOUT and self._last_heartbeat > 0:
                    self._log_mgr.warn(
                        f"[SYS] 监视心跳超时: {elapsed:.0f}秒无新数据 "
                        f"(最后心跳: {datetime.fromtimestamp(self._last_heartbeat).strftime('%H:%M:%S')})"
                    )
                    self._last_heartbeat = time.time()

            except Exception as e:
                try:
                    self._log_mgr.warn(f"[SYS] 健康监视异常: {e}")
                except Exception:
                    pass

            time.sleep(self.CHECK_INTERVAL)

    def _on_main_process_crash(self):
        """主进程崩溃处理：排空队列 + 起居注快照 + 日志回读 + 自动分析。"""
        self._crash_detected = True

        # ── ① 排空队列，收集为结构化数据 ─────────────────
        drained = 0
        drained_entries: list = []  # [(level, message, ts), ...]
        try:
            while True:
                try:
                    cmd = self._log_queue.get_nowait()
                    if cmd.get("type") in ("log", "monitor"):
                        level = cmd.get("level", "INFO")
                        message = cmd.get("message", "")
                        ts = cmd.get("timestamp", time.time())
                        self._log_mgr.log(level, f"[DRAINED] {message}")
                        drained_entries.append((level, message, ts))
                        drained += 1
                except Exception:
                    break
        except Exception:
            pass

        # ── ② 回读日志文件尾部（兜底数据源）────────────────
        log_tail_lines: list[str] = []
        try:
            log_path = self._log_mgr.log_path
            if log_path and os.path.isfile(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    # 读取最后 ~100 行（约 5-8KB）
                    all_lines = f.readlines()
                    log_tail_lines = all_lines[-100:] if len(all_lines) > 100 else all_lines
        except Exception:
            pass

        # ── 写入系统崩溃快照 ───────────────────────────────
        self._log_mgr.error("═" * 60)
        self._log_mgr.error("═══ [SYS] 主进程异常退出 ═══")
        self._log_mgr.error("═" * 60)
        self._log_mgr.error(f"  PID: {self._main_pid}")
        self._log_mgr.error(
            f"  退出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self._log_mgr.error(f"  队列残留条目（已排空）: {drained} 条")
        self._log_mgr.error(f"  应急写入次数: {self._emergency_count}")
        if self._last_heartbeat > 0:
            delta = time.time() - self._last_heartbeat
            self._log_mgr.error(
                f"  最后监视心跳: {datetime.fromtimestamp(self._last_heartbeat).strftime('%H:%M:%S')} "
                f"({delta:.0f}秒前)"
            )

        # ★ 起居注 lineage 快照
        if self._chronicle_snapshot:
            cs = self._chronicle_snapshot
            self._log_mgr.error("─" * 40)
            self._log_mgr.error("═══ [CRON] 起居注崩溃快照 ═══")
            lineage = cs.get("lineage", "(未知)")
            if lineage:
                self._log_mgr.error(f"  崩溃时活跃操作链: {lineage}")
            self._log_mgr.error(f"  活跃上下文数量: {cs.get('active_count', 0)}")
            contexts = cs.get("contexts", [])
            for i, ctx_info in enumerate(contexts):
                status = "⚠ 已报错" if ctx_info.get("has_error") else "运行中"
                thread_id = ctx_info.get("thread_id", "?")
                elapsed = ctx_info.get("elapsed_ms", 0)
                self._log_mgr.error(
                    f"    [{i}] {ctx_info['category']}·{ctx_info['name']} "
                    f"(depth={ctx_info['depth']}) [{status}] "
                    f"已运行{elapsed:.0f}ms 线程:{thread_id}"
                )
                err_details = ctx_info.get("error_details", [])
                for ed in err_details[:2]:
                    self._log_mgr.error(f"       └ {ed.get('content', '')[:120]}")
                metadata = ctx_info.get("metadata", {})
                if metadata:
                    meta_str = ", ".join(
                        f"{k}={v}" for k, v in list(metadata.items())[:4]
                    )
                    self._log_mgr.error(f"       └ 元数据: {meta_str}")

        # ★ 守护日志环数据（来自周期性心跳快照）
        if self._ring_buffer_data:
            self._log_mgr.error("─" * 40)
            self._log_mgr.error(
                f"═══ [RING] 守护日志环 (最后心跳快照 {len(self._ring_buffer_data)} 条) ═══"
            )
            recent = self._ring_buffer_data[-50:]
            for ts, level, msg in recent:
                dt = datetime.fromtimestamp(ts).strftime('%H:%M:%S')
                self._log_mgr.error(f"  [{dt}] [{level}] {msg[:200]}")

        # ★ 崩溃自动分析（三数据源：排空队列 + 日志尾部 + 环缓冲区）
        self._analyze_crash(
            drained_entries=drained_entries,
            ring_data=self._ring_buffer_data,
            chronicle_snap=self._chronicle_snapshot,
            log_tail_lines=log_tail_lines,
            drained_count=drained,
        )

        self._log_mgr.error("═" * 60)

    # ── ★ v2.2.0: 崩溃自动分析（全面重写）─────────────────

    def _analyze_crash(self, drained_entries: list, ring_data: list,
                       chronicle_snap: dict, log_tail_lines: list,
                       drained_count: int):
        """多数据源崩溃自动分析（v2.2.0 全面重写）。

        数据源:
          - drained_entries: 排空队列中的结构化条目 [(level, msg, ts), ...]
          - ring_data:       守护日志环快照（周期性心跳附带）
          - chronicle_snap:  起居注崩溃快照（closeEvent 发送）
          - log_tail_lines:  日志文件尾部回读（兜底）
          - drained_count:   队列残留数量

        分析维度 (8 项):
          1. CRC 操作链 — 崩溃时 [CRON] 上下文状态
          2. 崩溃前错误 — 时间窗口内 error/warn 统计
          3. 重复错误模式 — 同一类错误反复出现
          4. 错误类型归类 — segfault/Qt/HTTP/超时等
          5. 文件热点 — 报错最频繁的源文件
          6. 线程状态 — 多线程活跃/竞争检测
          7. 时间间隔 — 最后日志到崩溃的时间差
          8. 队列残留 — 积压是否接近阈值
        """
        self._log_mgr.error("─" * 40)
        self._log_mgr.error("═══ 💡 崩溃自动分析 ═══")

        findings = []
        crash_window = 10.0  # 崩溃前 10 秒
        now = time.time()

        # 合并数据源：优先 drained_entries > ring_data > log_tail
        all_entries: list = []  # [(ts, level, msg), ...]
        for level, msg, ts in drained_entries:
            all_entries.append((ts, level, msg))
        for ts, level, msg in ring_data:
            all_entries.append((ts, level, msg))
        # 解析日志尾部
        import re as _re
        _log_pattern = _re.compile(
            r'\[(\d{2}:\d{2}:\d{2}(?:\.\d{3})?)\]\s+\[(\w+)\]\s+(.*)'
        )
        for line in log_tail_lines:
            m = _log_pattern.match(line)
            if m:
                try:
                    dt = datetime.strptime(m.group(1).split('.')[0], '%H:%M:%S')
                    log_ts = now - (now % 86400) + (dt.hour * 3600 + dt.minute * 60 + dt.second)
                    all_entries.append((log_ts, m.group(2), m.group(3)))
                except Exception:
                    pass

        # 去重 + 按时间排序
        all_entries.sort(key=lambda x: x[0])
        if len(all_entries) > 200:
            all_entries = all_entries[-200:]  # 只看最近 200 条

        # ═══════════════════════════════════════════════════
        #  ① CRON 操作链分析
        # ═══════════════════════════════════════════════════
        opened_ops = []
        cron_active = False
        for ts, level, msg in all_entries:
            if "[CRON] ▶" in msg:
                opened_ops.append(msg)
                cron_active = True
            elif "[CRON]" in msg and ("→ ok" in msg or "→ failed" in msg):
                if opened_ops:
                    opened_ops.pop()

        if opened_ops:
            op_names = [
                o.split("▶")[-1].split(" start")[0].strip()
                for o in opened_ops[:3]
            ]
            findings.append(
                f"🔴 未完成的操作 ({len(opened_ops)} 个): {' → '.join(op_names)}"
            )
        elif cron_active:
            findings.append("🟢 CRON 操作链正常闭合")
        else:
            findings.append("⚪ 起居注未活跃（无 [CRON] 条目）")

        # ═══════════════════════════════════════════════════
        #  ② 崩溃前错误/warn 统计
        # ═══════════════════════════════════════════════════
        recent_errors = []
        recent_warns = []
        for ts, level, msg in all_entries:
            if (now - ts) <= crash_window:
                if level == "ERROR":
                    recent_errors.append(msg)
                elif level == "WARN":
                    recent_warns.append(msg)

        if recent_errors:
            findings.append(
                f"🔴 崩溃前 {crash_window}秒内 ERROR: {len(recent_errors)} 条"
            )
            for em in recent_errors[-3:]:
                self._log_mgr.error(f"    [ERROR] {em[:150]}")
        else:
            findings.append("🟢 崩溃前无 ERROR 级别日志")

        if recent_warns:
            findings.append(
                f"🟡 崩溃前 {crash_window}秒内 WARN: {len(recent_warns)} 条"
            )

        # ═══════════════════════════════════════════════════
        #  ③ 重复错误模式检测
        # ═══════════════════════════════════════════════════
        from collections import Counter
        error_sigs = Counter()
        for ts, level, msg in all_entries:
            if level in ("ERROR", "WARN"):
                # 提取错误签名：取消息前 80 字符作为指纹
                sig = msg[:80].split(":")[0].split("(")[0].strip()
                if len(sig) > 10:
                    error_sigs[sig] += 1

        repeated = [(sig, cnt) for sig, cnt in error_sigs.most_common(5) if cnt >= 2]
        if repeated:
            findings.append(
                f"🟡 重复错误模式 ({len(repeated)} 类): "
            )
            for sig, cnt in repeated[:3]:
                findings.append(
                    f"    ↻ 出现 {cnt} 次: {sig[:80]}"
                )

        # ═══════════════════════════════════════════════════
        #  ④ 错误类型归类
        # ═══════════════════════════════════════════════════
        error_types = {
            "Qt 内部错误": 0,
            "段错误/访问违例": 0,
            "Python 异常": 0,
            "超时": 0,
            "HTTP/API": 0,
        }
        for ts, level, msg in all_entries:
            if level not in ("ERROR", "WARN"):
                continue
            if "Qt " in msg or "QWidget" in msg or "QPainter" in msg or "QLayout" in msg:
                error_types["Qt 内部错误"] += 1
            if "access violation" in msg.lower() or "segfault" in msg.lower() or "OSError" in msg:
                error_types["段错误/访问违例"] += 1
            if "Error" in msg or "Exception" in msg or "IndexError" in msg or "KeyError" in msg:
                error_types["Python 异常"] += 1
            if "超时" in msg or "timeout" in msg.lower() or "Timeout" in msg:
                error_types["超时"] += 1
            if "HTTP" in msg or "API" in msg or "http" in msg.lower():
                error_types["HTTP/API"] += 1

        active_types = [(t, c) for t, c in error_types.items() if c > 0]
        if active_types:
            active_types.sort(key=lambda x: x[1], reverse=True)
            type_summary = ", ".join(
                f"{t}:{c}" for t, c in active_types[:4]
            )
            findings.append(f"📊 错误类型分布: {type_summary}")

            # 根据主导错误类型给出针对性建议
            top_type, top_count = active_types[0]
            if top_type == "Qt 内部错误" and top_count >= 3:
                findings.append("    ► Qt 错误频繁：检查控件生命周期/布局/setParent 调用")
            if top_type == "段错误/访问违例":
                findings.append("    ► 硬件级崩溃：检查 ctypes 调用/第三方 C 扩展/野指针")
            if top_type == "Python 异常" and top_count >= 2:
                findings.append("    ► Python 异常未捕获：检查 Worker 线程的 try/except")

        # ═══════════════════════════════════════════════════
        #  ⑤ 文件热点分析
        # ═══════════════════════════════════════════════════
        file_counter = Counter()
        for ts, level, msg in all_entries:
            if level == "ERROR":
                match = _re.search(
                    r'File\s+"([^"]+)"\s*,\s*line\s+(\d+)', msg
                )
                if match:
                    fname = match.group(1).split('\\')[-1].split('/')[-1]
                    file_counter[fname] += 1

        if file_counter:
            top_files = file_counter.most_common(3)
            hot_files = ", ".join(
                f"{f}:{c}" for f, c in top_files
            )
            findings.append(f"📁 错误热点文件: {hot_files}")

        # ═══════════════════════════════════════════════════
        #  ⑥ 线程状态
        # ═══════════════════════════════════════════════════
        if chronicle_snap:
            contexts = chronicle_snap.get("contexts", [])
            thread_ids = {c.get("thread_id") for c in contexts}
            if len(thread_ids) > 2:
                findings.append(
                    f"🟡 {len(thread_ids)} 个线程活跃，可能存在竞争"
                )
            # 检查是否有报错线程
            errored = [c for c in contexts if c.get("has_error")]
            if errored:
                findings.append(
                    f"⚠ {len(errored)} 个上下文已报错，错误向上传播中"
                )

        # ═══════════════════════════════════════════════════
        #  ⑦ 时间间隔分析
        # ═══════════════════════════════════════════════════
        if all_entries:
            last_log_ts = all_entries[-1][0]
            gap = now - last_log_ts
            if gap > 30:
                findings.append(
                    f"🟡 最后日志距崩溃 {gap:.0f}秒，可能为静默卡死"
                )
            elif gap > 5:
                findings.append(
                    f"ℹ 最后日志距崩溃 {gap:.1f}秒"
                )
        elif self._last_heartbeat > 0:
            gap = now - self._last_heartbeat
            findings.append(
                f"🟡 无日志条目，最后心跳在 {gap:.0f}秒前"
            )

        # ═══════════════════════════════════════════════════
        #  ⑧ 队列残留
        # ═══════════════════════════════════════════════════
        if drained_count > 100:
            findings.append(
                f"🔴 队列严重积压: {drained_count} 条（日志风暴/IO瓶颈）"
            )
        elif drained_count > 20:
            findings.append(f"🟡 队列残留: {drained_count} 条")

        if self._emergency_count > 0:
            findings.append(
                f"🔴 应急写入 {self._emergency_count} 次（队列断开前兆）"
            )

        # ═══════════════════════════════════════════════════
        #  ⑨ 底层事件统计 (NATIVE/THREAD/RES/EXT 标签)
        # ═══════════════════════════════════════════════════
        native_tags = {
            "[NATIVE]": 0,
            "[THREAD]": 0,
            "[RES]": 0,
            "[EXT]": 0,
        }
        for ts, level, msg in all_entries:
            for tag in native_tags:
                if tag in msg:
                    native_tags[tag] += 1

        native_active = [(t, c) for t, c in native_tags.items() if c > 0]
        if native_active:
            tag_summary = ", ".join(f"{t}:{c}" for t, c in native_active)
            findings.append(f"📊 底层事件分布: {tag_summary}")

            # 特定底层事件模式识别
            native_errors = []
            for ts, level, msg in all_entries:
                if ("deadlock_suspect" in msg or
                    "main_loop_no_resp" in msg or
                    "fd_leak" in msg):
                    native_errors.append(msg)

            if native_errors:
                findings.append(
                    f"🔴 重大底层事件 ({len(native_errors)} 条): "
                    f"{native_errors[-1][:100]}"
                )

        # ═══════════════════════════════════════════════════
        #  ⑩ SQLite 原生事件快照 (从 native.db 读取最近事件)
        # ═══════════════════════════════════════════════════
        try:
            _native_db_path = os.path.join(
                os.path.dirname(self._log_mgr.log_dir),
                "log", "native.db"
            )
            if os.path.isfile(_native_db_path):
                _conn = sqlite3.connect(_native_db_path, timeout=2)
                _cursor = _conn.execute(
                    "SELECT level, source, message, location, ts "
                    "FROM native_events ORDER BY ts DESC LIMIT 5"
                )
                _native_recent = _cursor.fetchall()
                _conn.close()

                if _native_recent:
                    findings.append(
                        f"📁 SQLite native.db 最近 {len(_native_recent)} 条:"
                    )
                    for _row in _native_recent:
                        _lev, _src, _msg, _loc, _ts = _row
                        _ts_str = datetime.fromtimestamp(
                            _ts
                        ).strftime('%H:%M:%S')
                        _short = _msg[:80]
                        findings.append(
                            f"    [{_ts_str}] [{_lev}] {_src}: {_short}"
                        )
        except Exception:
            pass

        # ═══════════════════════════════════════════════════
        #  输出分析结果
        # ═══════════════════════════════════════════════════
        if findings:
            for i, f in enumerate(findings, 1):
                self._log_mgr.error(f"  {i}. {f}")
        else:
            self._log_mgr.error("  (无可疑迹象)")

        # ═══════════════════════════════════════════════════
        #  综合诊断建议
        # ═══════════════════════════════════════════════════
        self._log_mgr.error("  ─── 建议 ───")
        suggestions = []

        if any("未完成的操作" in f for f in findings):
            suggestions.append("检查未完成操作的异常处理，优先排查相关代码路径")
        if any("静默卡死" in f for f in findings):
            suggestions.append("检查是否有死锁/无限循环/Qt 事件循环阻塞")
        if any("段错误" in f for f in findings) or any("访问违例" in f for f in findings):
            suggestions.append("C 层崩溃：检查 ctypes 调用/第三方扩展内存安全")
        if any("Qt 内部错误" in f for f in findings) and any("Qt " in f for f in findings):
            suggestions.append("Qt 层错误频繁：检查控件生命周期/布局冲突")
        if any("重复错误模式" in f for f in findings):
            suggestions.append("同一错误反复出现，应在日志中查找最早出现点并追溯根因")
        if any("队列严重积压" in f for f in findings) or any("日志风暴" in f for f in findings):
            suggestions.append("日志量过大导致 IO 瓶颈，降低日志级别或关闭调试监视")
        if any("线程" in f for f in findings) and "活跃" in " ".join(findings):
            suggestions.append("多线程状态异常，检查 Worker 生命周期/线程泄露")
        if any("重大底层事件" in f for f in findings):
            suggestions.append("存在重大底层事件（死锁/fd 泄漏），查看 SQLite native.db 获取详情")
        if not recent_errors and not drained_entries:
            suggestions.append("无声崩溃（无日志前兆）：可能为 kill/硬件/系统级终止")

        if suggestions:
            for s in suggestions:
                self._log_mgr.error(f"  → {s}")
        else:
            self._log_mgr.error("  → 无可识别模式，建议人工检查完整日志文件")

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        """检查指定 PID 的进程是否存活。

        Windows: kernel32 OpenProcess + GetExitCodeProcess
        Linux/macOS: os.kill(pid, 0)
        """
        if sys.platform != "win32":
            try:
                os.kill(pid, 0)
                return True
            except (OSError, PermissionError):
                return False

        # ── Windows: kernel32 API ──────────────────────────
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259

        try:
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if handle == 0 or handle is None:
                return False

            exit_code = ctypes.c_ulong()
            result = ctypes.windll.kernel32.GetExitCodeProcess(
                handle, ctypes.byref(exit_code)
            )
            ctypes.windll.kernel32.CloseHandle(handle)

            if result == 0:
                return False
            return exit_code.value == STILL_ACTIVE
        except Exception:
            return False


# ============================================================================
#  LogService — 日志服务独立进程
# ============================================================================

class LogService(multiprocessing.Process):
    """日志服务独立进程。

    主进程通过 multiprocessing.Queue 发送指令，LogService 在独立
    进程中写入日志文件。主窗口崩溃不影响日志写入。

    指令格式:
        {"type": "log", "level": "INFO", "message": "..."}
        {"type": "monitor", "level": "INFO", "message": "[TAG] ...", "timestamp": 1234567890.0}
        {"type": "emergency_info", "emergency_count": 5, "last_heartbeat": 1234567890.0,
         "chronicle_snapshot": {...}, "ring_buffer_data": [...]}  ★ v2.1.0
        {"type": "shutdown"}
    """

    def __init__(
        self,
        project_root: str,
        log_queue: multiprocessing.Queue,
        result_queue: multiprocessing.Queue,
        auto_clean_enabled: bool = True,
    ):
        super().__init__(name="StarDebate-LogService", daemon=False)
        self._project_root = project_root
        self._log_queue = log_queue
        self._result_queue = result_queue
        self._auto_clean_enabled = auto_clean_enabled

    def run(self):
        """进程入口：初始化 LogManager → 启动健康监视 → 主循环处理指令。"""
        log_mgr: Optional[LogManager] = None
        health_monitor: Optional[SystemHealthMonitor] = None

        try:
            # ── ① 初始化 LogManager ──────────────────────────
            log_mgr = LogManager(self._project_root)
            log_mgr.info("═══ LogService 已启动 ═══")

            # ── ② 自动清理旧日志（根据配置决定）─────────────
            if self._auto_clean_enabled:
                cleaned = log_mgr.auto_clean()
                if cleaned > 0:
                    log_mgr.info(f"自动清理: 已删除 {cleaned} 个过期日志文件（>7天）")
                else:
                    log_mgr.info("自动清理: 无过期日志文件")
            else:
                log_mgr.info("自动清理: 已关闭（log_settings.json 中 auto_clean=false）")

            log_mgr.info(f"日志文件: {log_mgr.log_path}")

            # ── ③ 发送初始化结果给主进程 ─────────────────────
            self._result_queue.put({
                "log_path": log_mgr.log_path,
                "log_dir": log_mgr.log_dir,
                "status": "ready",
            })

            # ── ④ 启动系统健康监视线程 ───────────────────────
            main_pid = os.getppid()  # LogService 的父进程 = 启动器 = 主进程
            health_monitor = SystemHealthMonitor(main_pid, self._log_queue, log_mgr)
            health_monitor.start()
            log_mgr.info(f"[SYS] 系统健康监视已启动 (监控 PID: {main_pid})")

            # ── ⑤ 主循环：处理日志队列指令 ───────────────────
            log_mgr.info("[SYS] 日志服务进入主循环，等待指令...")

            while True:
                try:
                    # 阻塞等待指令，超时 1 秒以检查健康监视状态
                    cmd = self._log_queue.get(timeout=1.0)

                    cmd_type = cmd.get("type", "")

                    if cmd_type == "shutdown":
                        log_mgr.info("═══ LogService 正常关闭 ═══")
                        break

                    elif cmd_type == "log":
                        level = cmd.get("level", "INFO")
                        message = cmd.get("message", "")
                        log_mgr.log(level, message)

                    elif cmd_type == "monitor":
                        level = cmd.get("level", "INFO")
                        message = cmd.get("message", "")
                        timestamp = cmd.get("timestamp", time.time())
                        log_mgr.log(level, message)
                        # 更新健康监视心跳
                        if health_monitor:
                            health_monitor.update_heartbeat(timestamp)

                    elif cmd_type == "emergency_info":
                        emergency_count = cmd.get("emergency_count", 0)
                        last_heartbeat = cmd.get("last_heartbeat", time.time())
                        chronicle_snapshot = cmd.get("chronicle_snapshot", {})
                        ring_buffer_data = cmd.get("ring_buffer_data", [])
                        if health_monitor:
                            health_monitor.update_emergency_info(
                                emergency_count, last_heartbeat,
                                chronicle_snapshot, ring_buffer_data
                            )

                    else:
                        log_mgr.warn(f"[SYS] 未知指令类型: {cmd_type}")

                except Exception:
                    # 超时或其他异常，检查是否需要退出
                    if health_monitor and health_monitor.crash_detected:
                        # 主进程已崩溃，健康监视已写入快照
                        break
                    continue

        except Exception as e:
            # LogService 自身异常：尝试写入错误信息
            try:
                if log_mgr:
                    log_mgr.error(f"[SYS] LogService 内部异常: {e}")
            except Exception:
                pass
            # 通知主进程初始化失败
            try:
                self._result_queue.put({
                    "log_path": "",
                    "status": "error",
                    "error": str(e),
                })
            except Exception:
                pass

        finally:
            # ── 清理 ──────────────────────────────────────────
            if health_monitor:
                health_monitor.stop()
                health_monitor.join(timeout=3)
            if log_mgr:
                try:
                    log_mgr.info("[SYS] LogService 进程退出")
                except Exception:
                    pass


# ============================================================================
#  模块导出
# ============================================================================

__all__ = [
    "LogService",
    "LogClient",
    "SystemHealthMonitor",
    "ActivityChronicle",
    "ChronicleContext",
]
