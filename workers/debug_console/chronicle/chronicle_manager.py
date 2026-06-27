"""起居注管理器 — ActivityChronicle + ChronicleContext (v2.0.0)
============================================================================
v2.0.0 新增功能（崩溃定位优化）:
  ★ 完整 traceback 记录 — 异常捕获时保留完整堆栈
  ★ 操作元数据 — begin() 支持 metadata 参数记录操作上下文
  ★ 崩溃前 lineage 快照 — 周期性记录当前活跃操作链，供崩溃诊断
  ★ 定时快照线程 — 每 2 秒写入共享状态，crash 后从日志恢复操作路径
  ★ 耗时异常告警 — 超过 max_duration_ms 自动标记 warn

ActivityChronicle 是 LogClient 的内部组件，通过拦截 error/warn 调用
自动检测操作是否成功。无需修改任何现有代码。

标签: [CRON] (Chronicle Record, 4字符)
============================================================================
"""

import os
import json
import time
import traceback
import functools
import threading
from datetime import datetime
from typing import Optional


# ════════════════════════════════════════════════════════
#  ChronicleContext — 单次操作的上下文
# ════════════════════════════════════════════════════════

class ChronicleContext:
    """单次操作的追踪上下文。

    字段:
        category: 类别 ("feature"|"plugin"|"api"|"ai")
        name:     操作名称
        start_time: 开始时间戳
        has_error:  是否发生了 error/warn (由 LogClient 自动标记)
        error_details: 错误详情列表 [{"type":"error"|"warn"|"traceback", "content":"..."}, ...]
        depth:     嵌套深度 (0=顶层)
        ★ metadata: 操作附加元数据 (v2.0.0)，崩溃时随快照输出
    """

    __slots__ = ("category", "name", "start_time", "has_error",
                 "error_details", "depth", "_elapsed", "metadata", "_thread_id")

    def __init__(self, category: str, name: str, depth: int = 0,
                 metadata: dict = None):
        self.category = category
        self.name = name
        self.start_time = time.time()
        self.has_error = False
        self.error_details: list = []
        self.depth = depth
        self._elapsed = 0.0
        self.metadata = metadata if metadata else {}
        self._thread_id = threading.get_ident()  # ★ 记录所在线程 ID

    @property
    def is_top_level(self) -> bool:
        return self.depth == 0

    @property
    def elapsed_ms(self) -> float:
        if self._elapsed > 0:
            return self._elapsed
        return (time.time() - self.start_time) * 1000

    def _set_elapsed(self, ms: float):
        """内部设置最终耗时（供 end 后冻结）。"""
        self._elapsed = ms

    @property
    def thread_id(self) -> int:
        """操作所在线程 ID（用于跨线程崩溃诊断）。"""
        return self._thread_id

    def to_lineage(self) -> str:
        """生成当前操作的路径描述（用于崩溃快照）。"""
        meta_str = ""
        if self.metadata:
            parts = [f"{k}={v}" for k, v in list(self.metadata.items())[:3]]
            if parts:
                meta_str = f" [{', '.join(parts)}]"
        return f"{self.category}·{self.name}{meta_str}"


# ════════════════════════════════════════════════════════
#  哑上下文 — enabled=False 或类别禁用时返回
# ════════════════════════════════════════════════════════

class _DummyContext:
    """哑上下文，end() 不做任何事。"""
    __slots__ = ()
    def __bool__(self): return False
    def __enter__(self): return self
    def __exit__(self, *a): return False


_DUMMY_CTX = _DummyContext()


# ════════════════════════════════════════════════════════
#  ActivityChronicle — 起居注核心 (v2.0.0)
# ════════════════════════════════════════════════════════

class ActivityChronicle:
    """起居注管理器 — LogClient 内部组件 (v2.0.0)。

    通过拦截 LogClient.error/warn 自动标记上下文错误，
    在操作完成时自动判定成功/失败并写入日志。

    类别图标:
        feature → ✅    plugin → ▶    api → ✓    ai → ✅

    ★ v2.0.0 崩溃定位增强:
      - 完整 traceback 记录
      - 操作元数据 (metadata)
      - Lineage 快照 (崩溃前活跃操作链)
      - 定时快照线程
      - 耗时异常告警
    """

    CATEGORY_ICONS = {
        "feature": "✅",
        "plugin": "▶",
        "api": "✓",
        "ai": "✅",
    }

    DEFAULT_CONFIG = {
        "enabled": True,
        "categories": {
            "feature": True,
            "plugin": True,
            "api": True,
            "ai": True,
        },
        "min_duration_ms": 0,
        "max_duration_ms": {  # ★ v2.0.0 耗时异常告警阈值
            "feature": 0,     # 0=不启用
            "api": 0,
            "ai": 0,
            "plugin": 0,
        },
        "log_level": "INFO",
        "snapshot_interval_s": 2.0,    # ★ v2.0.0 快照间隔
        "capture_traceback": True,     # ★ v2.0.0 是否捕获完整traceback
        "keep_ring_log_lines": 200,    # ★ v2.0.0 守护日志环形缓冲区行数
    }

    MAX_TRACEBACK_LINES = 30   # traceback 最大保留行数
    MAX_ERROR_DETAILS = 5      # 每个上下文最多保留的错误详情数

    def __init__(self, log_client):
        """内嵌于 LogClient。

        Args:
            log_client: LogClient 实例 (用于写入 [CRON] 日志)
        """
        self._log = log_client  # LogClient 引用 (调用 info/warn)
        self._stack: list[ChronicleContext] = []
        self._enabled = True
        self._config = self._load_config()

        # ★ v2.0.0: Lineage 快照相关
        self._latest_lineage = ""          # 最近一次操作路径
        self._latest_lineage_ts = 0.0      # 快照时间戳
        self._snapshot_lock = threading.Lock()

        # ★ v2.0.0: 定时快照线程
        self._snapshot_thread: Optional[threading.Thread] = None
        self._snapshot_running = False
        self._start_snapshot_thread()

    # ── 配置 ──────────────────────────────────────────────

    @property
    def config_path(self) -> str:
        import os
        from components.res_path import get_resource_root
        return os.path.join(
            get_resource_root(),
            "config", "chronicle_config.json"
        )

    def _load_config(self) -> dict:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for key in self.DEFAULT_CONFIG:
                if key not in cfg:
                    cfg[key] = self.DEFAULT_CONFIG[key]
            # 深度合并 max_duration_ms
            if "max_duration_ms" in cfg:
                defaults = self.DEFAULT_CONFIG["max_duration_ms"]
                if isinstance(cfg["max_duration_ms"], dict):
                    for cat in defaults:
                        if cat not in cfg["max_duration_ms"]:
                            cfg["max_duration_ms"][cat] = defaults[cat]
                else:
                    cfg["max_duration_ms"] = dict(defaults)
            return cfg
        except Exception:
            return dict(self.DEFAULT_CONFIG)

    def _save_config(self):
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    # ── 属性 ──────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled and self._config.get("enabled", True)

    @enabled.setter
    def enabled(self, value: bool):
        was_enabled = self._enabled
        self._enabled = value
        # 状态切换时管理快照线程
        if value and not was_enabled:
            self._start_snapshot_thread()
        elif not value and was_enabled:
            self._stop_snapshot_thread()

    @property
    def active_count(self) -> int:
        return len(self._stack)

    @property
    def latest_lineage(self) -> str:
        """获取崩溃前活跃操作链快照（线程安全）。"""
        with self._snapshot_lock:
            return self._latest_lineage

    @property
    def active_contexts(self) -> list:
        """返回当前所有活跃上下文的浅拷贝（线程安全）。"""
        with self._snapshot_lock:
            return list(self._stack)

    # ── ★ v2.0.0: 定时快照线程 ────────────────────────────

    def _start_snapshot_thread(self):
        """启动定时 lineage 快照线程。"""
        if self._snapshot_thread and self._snapshot_thread.is_alive():
            return
        self._snapshot_running = True
        self._snapshot_thread = threading.Thread(
            target=self._snapshot_loop,
            daemon=True,
            name="ChronicleSnapshot"
        )
        self._snapshot_thread.start()

    def _stop_snapshot_thread(self):
        """停止定时快照线程。"""
        self._snapshot_running = False

    def _snapshot_loop(self):
        """定时快照循环（独立守护线程）。"""
        interval = self._config.get("snapshot_interval_s", 2.0)
        while self._snapshot_running:
            try:
                self._update_lineage_snapshot()
            except Exception:
                pass
            time.sleep(interval)

    def _update_lineage_snapshot(self):
        """更新 lineage 快照（线程安全）。"""
        if not self._stack:
            return
        with self._snapshot_lock:
            lineage_parts = []
            for ctx in self._stack:
                lineage_parts.append(ctx.to_lineage())
            self._latest_lineage = " → ".join(lineage_parts)
            self._latest_lineage_ts = time.time()

    def get_crash_snapshot(self) -> dict:
        """获取崩溃诊断快照（供 SystemHealthMonitor 读取）。

        Returns:
            {
                "lineage": "操作A → 操作B → 操作C",
                "lineage_ts": 1234567890.0,
                "stack_depth": 3,
                "contexts": [{"category":"feature","name":"export","metadata":{...}, "thread_id":123}, ...],
                "active_count": 3,
            }
        """
        with self._snapshot_lock:
            contexts_info = []
            for ctx in self._stack:
                contexts_info.append({
                    "category": ctx.category,
                    "name": ctx.name,
                    "has_error": ctx.has_error,
                    "error_details": ctx.error_details[:2],
                    "metadata": ctx.metadata,
                    "thread_id": ctx.thread_id,
                    "depth": ctx.depth,
                    "elapsed_ms": ctx.elapsed_ms,
                })
            return {
                "lineage": self._latest_lineage,
                "lineage_ts": self._latest_lineage_ts,
                "stack_depth": len(self._stack),
                "contexts": contexts_info,
                "active_count": len(self._stack),
            }

    # ── 核心方法: 错误通知 ───────────────────────────────

    def _on_error(self, level: str, msg: str):
        """被 LogClient.error/warn 调用。

        遍历当前活跃的所有上下文，标记 has_error。
        错误向上传播：子上下文出错 → 所有父上下文也被标记。
        """
        if not self.enabled:
            return
        if not self._stack:
            return
        detail = msg[:200] if msg else ""
        for ctx in self._stack:
            ctx.has_error = True
            if len(ctx.error_details) < self.MAX_ERROR_DETAILS:
                ctx.error_details.append({
                    "type": "error" if level == "ERROR" else "warn",
                    "content": detail,
                })

    # ── ★ v2.0.0: 记录 traceback 到上下文 ─────────────────

    def _on_exception(self, exc_type, exc_value, tb=None):
        """被装饰器/上下文管理器在捕获异常时调用。

        将异常类型、消息、完整 traceback 写入所有活跃上下文。
        """
        if not self.enabled:
            return
        if not self._stack:
            return

        error_msg = f"{exc_type.__name__}: {exc_value}"
        # 截取 traceback：取最后 MAX_TRACEBACK_LINES 行作为摘要
        tb_lines = []
        if tb is not None:
            tb_lines = traceback.format_tb(tb, limit=self.MAX_TRACEBACK_LINES)
        else:
            # 没有传入 tb 时尝试获取当前
            try:
                import sys
                tb_lines = traceback.format_exc().splitlines()[-self.MAX_TRACEBACK_LINES:]
            except Exception:
                pass

        for ctx in self._stack:
            ctx.has_error = True
            if len(ctx.error_details) < self.MAX_ERROR_DETAILS:
                ctx.error_details.append({
                    "type": "exception",
                    "content": error_msg,
                })
            if tb_lines and len(ctx.error_details) < self.MAX_ERROR_DETAILS:
                ctx.error_details.append({
                    "type": "traceback",
                    "content": "\n".join(tb_lines[-15:]),  # 最多15行
                })

    # ── 核心方法: 开始/结束追踪 ───────────────────────────

    def begin(self, category: str, name: str, metadata: dict = None) -> ChronicleContext | _DummyContext:
        """开始追踪一个操作。

        Args:
            category: 类别 ("feature"|"plugin"|"api"|"ai")
            name: 操作名称 (如 "my_func", "plugin_name")
            metadata: ★ v2.0.0 操作附加元数据 (如 {"debate_path": "...", "format": "..."})
                      崩溃时随 lineage 快照输出，便于重现崩溃场景

        Returns:
            ChronicleContext (enabled) 或 _DummyContext (disabled)
        """
        if not self.enabled:
            return _DUMMY_CTX

        cat_enabled = self._config.get("categories", {}).get(category, True)
        if not cat_enabled:
            return _DUMMY_CTX

        ctx = ChronicleContext(category, name, depth=len(self._stack),
                               metadata=metadata)
        self._stack.append(ctx)

        if ctx.is_top_level:
            meta_info = ""
            if metadata:
                parts = [f"{k}={v}" for k, v in list(metadata.items())[:4]]
                if parts:
                    meta_info = f"  [{', '.join(parts)}]"
            self._log.info(f"[CRON] ▶ {category}·{name} start{meta_info}")

        return ctx

    def end(self, ctx: ChronicleContext | _DummyContext, duration_ms: float = 0):
        """结束追踪，自动判定成功/失败并写入日志。

        Args:
            ctx: begin() 返回的上下文
            duration_ms: 操作耗时 (毫秒)
        """
        if ctx is _DUMMY_CTX or not self.enabled:
            return

        try:
            self._stack.remove(ctx)
        except ValueError:
            pass  # 可能已被先移除

        ctx._set_elapsed(duration_ms)

        min_dur = self._config.get("min_duration_ms", 0)
        if 0 < duration_ms < min_dur:
            return

        icon = self.CATEGORY_ICONS.get(ctx.category, "•")
        indent = "  " * ctx.depth if ctx.depth else ""

        # ★ v2.0.0: 耗时异常告警
        max_dur_map = self._config.get("max_duration_ms", {})
        max_dur = max_dur_map.get(ctx.category, 0) if isinstance(max_dur_map, dict) else 0
        slow_flag = ""
        if max_dur > 0 and duration_ms > max_dur:
            slow_flag = f" ⚠ SLOW (>{max_dur}ms)"

        if not ctx.has_error:
            self._log.info(
                f"{indent}[CRON] {icon} {ctx.category}·{ctx.name}"
                f" → ok ({duration_ms:.0f}ms){slow_flag}"
            )
        else:
            # 汇总错误详情
            error_msgs = [d["content"][:120] for d in ctx.error_details
                          if d.get("type") in ("error", "warn", "exception")]
            detail = error_msgs[0] if error_msgs else "unknown"

            self._log.info(
                f"{indent}[CRON] ❌ {ctx.category}·{ctx.name}"
                f" → failed ({duration_ms:.0f}ms): {detail}{slow_flag}"
            )

            # ★ v2.0.0: 附加 traceback 到日志
            tb_details = [d for d in ctx.error_details
                          if d.get("type") == "traceback"]
            if tb_details:
                for tb_d in tb_details:
                    tb_lines = tb_d["content"].splitlines()
                    for line in tb_lines:
                        self._log.info(f"{indent}  [TB] {line.strip()}")

    # ── 装饰器: @log_client.track("feature", "name") ──────

    def track(self, category: str, name: str = None, metadata: dict = None):
        """装饰器工厂：自动追踪函数执行 (v2.0.0 增强)。

        用法:
            @log_client.track("feature", "ai_analysis")
            def run(): ...

            @log_client.track("api")
            def call_endpoint(): ...   # name 自动取 func.__name__

            @log_client.track("feature", "export", metadata={"path": "/debate"})
            def export(): ...   # ★ v2.0.0 元数据

        Returns:
            decorator
        """
        def decorator(func):
            display_name = name or func.__name__
            func_metadata = dict(metadata) if metadata else {}

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # ★ 合并调用参数到 metadata (截断长值)
                call_meta = dict(func_metadata)
                if args and len(args) <= 3:
                    try:
                        call_meta["args"] = str(args)[:100]
                    except Exception:
                        pass
                ctx = self.begin(category, display_name, metadata=call_meta)
                start = time.time()
                try:
                    result = func(*args, **kwargs)
                    elapsed = (time.time() - start) * 1000
                    self.end(ctx, elapsed)
                    return result
                except Exception as e:
                    # ★ v2.0.0: 记录完整 traceback
                    import sys
                    _, _, tb = sys.exc_info()
                    self._on_exception(type(e), e, tb)
                    elapsed = (time.time() - start) * 1000
                    self.end(ctx, elapsed)
                    raise

            return wrapper
        return decorator

    # ── 上下文管理器: with log_client.track_ctx("api","x") ─

    def track_ctx(self, category: str, name: str, metadata: dict = None):
        """上下文管理器：自动追踪 with 块执行 (v2.0.0 增强)。

        用法:
            with log_client.track_ctx("api", "endpoint") as ctx:
                do_request()
                if fail:
                    log_client.error("failed")  # → ctx.has_error = True

            with log_client.track_ctx("feature", "pipeline",
                                      metadata={"stage": "init"}) as ctx:
                run_pipeline()  # ★ v2.0.0 元数据
        """
        ctx = self.begin(category, name, metadata=metadata)
        start = time.time()

        class _ChronicleCM:
            def __enter__(self):
                return ctx

            def __exit__(self, exc_type, exc_val, exc_tb):
                if exc_type is not None:
                    # ★ v2.0.0: 记录完整 traceback
                    self._chronicle._on_exception(exc_type, exc_val, exc_tb)
                elapsed = (time.time() - start) * 1000
                self._chronicle.end(ctx, elapsed)
                return False  # 不抑制异常

        _ChronicleCM._chronicle = self
        return _ChronicleCM()

    # ── ★ v2.0.0: 守护日志环支持（写入 LogClient ring buffer）──

    def _write_ring_snapshot(self):
        """将当前活跃上下文写入守护日志环（供崩溃后分析）。"""
        if hasattr(self._log, '_ring_buffer') and self._stack:
            lineage = " → ".join(ctx.to_lineage() for ctx in self._stack)
            self._log._ring_snapshot(f"[CRON-SNAP] {lineage}")
