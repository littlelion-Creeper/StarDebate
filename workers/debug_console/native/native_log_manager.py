"""底层事件管理器 — NativeEventManager (M1 v1.0.0)

协调 SQLite 双写 + 文本主日志双写 + 钩子注册 + 配置管理。

架构:
  ┌───────────────────────┐      ┌──────────────────────┐
  │ native_hooks.py       │ ──→  │ NativeEventManager   │
  │ Qt handler / excepthook│      │                      │
  │ unraisable / audit    │      │  native_events queue  │
  │ gc / c_exception      │      │  └→ batch writer t[]   │
  │ thread monitor        │      │      └→ SQLite (WAL)  │
  │ resource monitor      │      │      → text log       │
  └───────────────────────┘      └──────────────────────┘

SQLite 写入:
  - 独立守护线程批量写入 (200ms / 100 条)
  - WAL journal_mode + synchronous=NORMAL（崩溃安全）
  - 启动时自动清理 7 天前 + 超 5 万行数据

文本日志:
  - 通过 LogClient 写入现有 debug_*.log
  - 标签前缀: [NATIVE] / [THREAD] / [RES] / [EXT]
"""

import os
import json
import time
import queue
import sqlite3
import threading
import collections
from typing import Optional
from datetime import datetime


# ════════════════════════════════════════════════════════
#  默认配置
# ════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    "enabled": True,
    "db_path": "docs/log/native.db",
    "batch_interval_ms": 200,
    "batch_max_size": 100,
    "max_rows_per_table": 50000,
    "retention_days": 7,
    "text_log_enabled": True,
    "text_log_level": "INFO",
    "hooks": {
        "qt_handler": True,
        "excepthook": True,
        "unraisablehook": True,
        "audithook": True,
        "gc_callbacks": True,
        "c_exception_profile": True,
    },
    "throttle": {
        "enable": True,
        "max_per_second_per_category": 50,
    },
}


# ════════════════════════════════════════════════════════
#  表结构 DDL
# ════════════════════════════════════════════════════════

TABLE_DDL = {
    "native_events": """
        CREATE TABLE IF NOT EXISTS native_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            level TEXT NOT NULL,
            source TEXT NOT NULL,
            location TEXT DEFAULT '',
            message TEXT NOT NULL,
            detail_json TEXT DEFAULT '',
            thread_id INTEGER DEFAULT 0,
            thread_name TEXT DEFAULT '',
            func_name TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_nev_ts ON native_events(ts);
        CREATE INDEX IF NOT EXISTS idx_nev_level ON native_events(level);
        CREATE INDEX IF NOT EXISTS idx_nev_source ON native_events(source);
    """,
    "thread_events": """
        CREATE TABLE IF NOT EXISTS thread_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            kind TEXT NOT NULL,
            thread_id INTEGER DEFAULT 0,
            thread_name TEXT DEFAULT '',
            last_func TEXT DEFAULT '',
            stuck_seconds REAL DEFAULT 0.0,
            detail TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_te_ts ON thread_events(ts);
        CREATE INDEX IF NOT EXISTS idx_te_kind ON thread_events(kind);
    """,
    "resource_events": """
        CREATE TABLE IF NOT EXISTS resource_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            kind TEXT NOT NULL,
            obj_type TEXT DEFAULT '',
            obj_repr TEXT DEFAULT '',
            count INTEGER DEFAULT 0,
            detail TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_re_ts ON resource_events(ts);
        CREATE INDEX IF NOT EXISTS idx_re_kind ON resource_events(kind);
    """,
}

# 清理行数的 SQL（每个表）
_CLEAN_SQL_CAP = (
    "DELETE FROM {table} WHERE id NOT IN ("
    "  SELECT id FROM {table} ORDER BY id DESC LIMIT ?"
    ")"
)
_CLEAN_SQL_AGE = "DELETE FROM {table} WHERE ts < ?"


# ════════════════════════════════════════════════════════
#  NativeEventManager
# ════════════════════════════════════════════════════════

class NativeEventManager:
    """底层事件管理器 — 协调 SQLite 双写 + 文本主日志 + 钩子注册。

    Args:
        project_root: 项目根目录路径
        log_client: LogClient 实例（用于文本日志双写）
    """

    CONFIG_FILENAME = "native_log_config.json"

    def __init__(self, project_root: str, log_client=None):
        self._project_root = project_root
        self._log_client = log_client
        self._config = self._load_config()

        # 事件队列（线程安全）
        self._event_queue: queue.Queue = queue.Queue()

        # 状态
        self._running = False
        self._writer_thread: Optional[threading.Thread] = None
        self._db_path: str = ""
        self._flush_count = 0  # 统计

        # 递归保护（每个 hook 类别独立）
        self._hook_active = threading.local()
        self._hook_active.qt = False
        self._hook_active.excepthook = False

        # 节流状态
        self._throttle_counter: dict = {}
        self._throttle_lock = threading.Lock()

        # 统计计数器
        self._stats_lock = threading.Lock()
        self._stats = {
            "total_events": 0,
            "dropped_throttled": 0,
            "sqlite_flush_count": 0,
            "start_time": time.time(),
        }

        if self._config.get("enabled", True):
            self._start()

    # ── 属性 ──────────────────────────────────────────

    @property
    def db_path(self) -> str:
        return self._db_path

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def queue_size(self) -> int:
        return self._event_queue.qsize()

    @property
    def stats(self) -> dict:
        with self._stats_lock:
            return dict(self._stats)

    # ── 配置 ──────────────────────────────────────────

    def _config_path(self) -> str:
        return os.path.join(self._project_root, "config", self.CONFIG_FILENAME)

    def _load_config(self) -> dict:
        cfg_path = self._config_path()
        try:
            if os.path.isfile(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                # 合并默认值
                return self._merge_config(cfg)
            else:
                cfg = dict(DEFAULT_CONFIG)
                self._save_config(cfg)
                return cfg
        except Exception:
            return dict(DEFAULT_CONFIG)

    def _merge_config(self, cfg: dict) -> dict:
        """递归合并用户配置与默认配置。"""
        result = {}
        for key, default_val in DEFAULT_CONFIG.items():
            if key in cfg:
                if isinstance(default_val, dict) and isinstance(cfg[key], dict):
                    sub = dict(default_val)
                    sub.update(cfg[key])
                    result[key] = sub
                else:
                    result[key] = cfg[key]
            else:
                result[key] = default_val
        return result

    def _save_config(self, cfg: dict = None):
        try:
            cfg_path = self._config_path()
            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg or self._config, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def reload_config(self):
        """运行时重新加载配置（不影响已启动线程）。"""
        self._config = self._load_config()

    # ── 启动/停止 ─────────────────────────────────────

    def _start(self):
        """启动 SQLite 数据库 + 后台写入线程。"""
        self._init_db()
        self._running = True
        self._writer_thread = threading.Thread(
            target=self._batch_writer_loop,
            daemon=True,
            name="NativeEventWriter",
        )
        self._writer_thread.start()

    def close(self):
        """关闭管理器：排空队列 + 清理旧数据。"""
        self._running = False
        if self._writer_thread:
            # 排空剩余事件
            self.flush()
            self._writer_thread.join(timeout=3)
        # 清理过期数据
        self._clean_old_data()

    # ── SQLite 初始化 ─────────────────────────────────

    def _init_db(self):
        """创建 SQLite 数据库 + 建表（WAL 模式，崩溃安全）。"""
        db_rel = self._config.get("db_path", "docs/log/native.db")
        self._db_path = os.path.join(self._project_root, db_rel)
        db_dir = os.path.dirname(self._db_path)
        try:
            os.makedirs(db_dir, exist_ok=True)
        except OSError:
            return

        try:
            conn = sqlite3.connect(self._db_path, timeout=3)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=3000")
            for ddl in TABLE_DDL.values():
                conn.executescript(ddl)
            conn.commit()
            conn.close()
        except Exception as e:
            self._emergency_log(f"SQLite 初始化失败: {e}")

    def _ensure_db(self) -> Optional[sqlite3.Connection]:
        """获取数据库连接（带重连）。"""
        try:
            conn = sqlite3.connect(self._db_path, timeout=3)
            # 快速测试
            conn.execute("SELECT 1")
            return conn
        except Exception:
            try:
                self._init_db()
                conn = sqlite3.connect(self._db_path, timeout=3)
                conn.execute("SELECT 1")
                return conn
            except Exception:
                return None

    # ── 批量写入循环 ─────────────────────────────────

    def _batch_writer_loop(self):
        """后台守护线程：每 batch_interval_ms 或满 batch_max_size 写一次。"""
        interval = self._config.get("batch_interval_ms", 200) / 1000.0
        max_batch = self._config.get("batch_max_size", 100)

        while self._running:
            batch = []
            deadline = time.time() + interval
            # 收集中止条件：超时 或 满批
            while time.time() < deadline and len(batch) < max_batch:
                try:
                    item = self._event_queue.get(timeout=0.05)
                    batch.append(item)
                except queue.Empty:
                    break

            if batch:
                self._flush_sqlite(batch)

    def _flush_sqlite(self, batch: list):
        """将一批事件写入 SQLite。"""
        conn = self._ensure_db()
        if conn is None:
            return

        try:
            for table, data in batch:
                columns = ", ".join(data.keys())
                placeholders = ", ".join(["?"] * len(data))
                sql = (
                    f"INSERT INTO {table} ({columns}) "
                    f"VALUES ({placeholders})"
                )
                conn.execute(sql, list(data.values()))
            conn.commit()

            with self._stats_lock:
                self._stats["sqlite_flush_count"] += 1
                self._stats["total_events"] += len(batch)
        except Exception:
            conn.rollback()
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def flush(self):
        """强制排空队列（关闭时调用）。"""
        batch = []
        while not self._event_queue.empty():
            try:
                batch.append(self._event_queue.get_nowait())
            except queue.Empty:
                break
        if batch:
            self._flush_sqlite(batch)

    # ── 事件写入（公共 API） ──────────────────────────

    def write_event(self, table: str, level: str, source: str, message: str,
                    location: str = "", detail_json: str = "",
                    thread_id: int = 0, thread_name: str = "",
                    func_name: str = "",
                    **extra_kw) -> bool:
        """写入一条事件到 SQLite 队列 + 文本日志。

        文本日志前缀规则:
          native_events 表 → [NATIVE]
          thread_events 表 → [THREAD]
          resource_events 表 → [RES]

        Args:
            table: 表名 (native_events / thread_events / resource_events)
            level: 级别字符串 (如 "qt_fatal" / "uncaught" / "thread_died")
            source: 信号源标识 (如 "QtMsgHandler" / "sys.excepthook")
            message: 主消息
            location: 定位串
            detail_json: JSON 格式的补充数据
            thread_id: 线程 ID
            thread_name: 线程名
            func_name: 函数名
            **extra_kw: 额外字段（传入表特定字段如 kind/obj_type/count 等）

        Returns:
            True=成功入队, False=被节流丢弃
        """
        if not self._running:
            return False

        # 节流检查
        if self._config.get("throttle", {}).get("enable", True):
            if self._check_throttle(source):
                with self._stats_lock:
                    self._stats["dropped_throttled"] += 1
                return False

        # 构建数据
        now = time.time()
        data = {
            "ts": now,
            "level": level,
            "source": source,
            "message": str(message)[:500],
            "location": str(location)[:200],
            "detail_json": str(detail_json)[:2000],
            "thread_id": thread_id or threading.get_ident(),
            "thread_name": thread_name or (
                threading.current_thread().name[:50]
            ),
            "func_name": str(func_name)[:100],
        }
        # 合并额外字段（覆盖同名）
        data.update(extra_kw)

        self._event_queue.put((table, data))

        # 文本日志双写
        self._write_text_log(table, level, source, message, location)

        return True

    def write_raw_event(self, table: str, data: dict) -> bool:
        """写入一条自定义列的事件到 SQLite（供 thread/resource 表使用）。

        与 write_event() 的区别:
          - 不强制添加 level/source/message/detail_json 等 native_events 列
          - 由调用者提供完整列映射（表结构由 DDL 定义）
          - 自动注入 ts 时间戳
          - 不自动写入文本日志（调用者需自行调用 write_text_event）

        Args:
            table: 表名 (thread_events / resource_events)
            data: 列名→值的映射（自动添加 ts 字段）

        Returns:
            True=成功入队, False=被丢弃
        """
        if not self._running:
            return False
        data["ts"] = time.time()
        self._event_queue.put((table, dict(data)))
        return True

    def write_text_event(self, table: str, level: str, source: str,
                         message: str, location: str = ""):
        """写入纯文本日志条目（供 write_raw_event 调用者使用）。

        绕过 write_event 的自动文本日志逻辑，只写文本日志。
        """
        self._write_text_log(table, level, source, message, location)

    # ── 节流 ──────────────────────────────────────────

    def _check_throttle(self, source: str) -> bool:
        """检查是否超过当前秒的节流阈值。"""
        now_sec = int(time.time())
        max_per_sec = self._config.get("throttle", {}).get(
            "max_per_second_per_category", 50
        )

        with self._throttle_lock:
            if now_sec != getattr(self, "_throttle_ts", 0):
                self._throttle_ts = now_sec
                self._throttle_counter.clear()

            count = self._throttle_counter.get(source, 0) + 1
            self._throttle_counter[source] = count
            return count > max_per_sec

    # ── 文本日志双写 ─────────────────────────────────

    TAG_MAP = {
        "native_events": "[NATIVE]",
        "thread_events": "[THREAD]",
        "resource_events": "[RES]",
    }

    LEVEL_MAP = {
        "qt_fatal": "ERROR",
        "qt_critical": "ERROR",
        "qt_warning": "WARN",
        "uncaught": "ERROR",
        "unraisable": "ERROR",
        "audit": "WARN",
        "gc": "WARN",
        "thread_died": "WARN",
        "thread_stuck": "WARN",
        "deadlock_suspect": "ERROR",
        "main_loop_no_resp": "ERROR",
        "fd_leak": "WARN",
        "gc_uncollectable": "WARN",
        "qt_object_leak": "WARN",
    }

    def _write_text_log(self, table: str, level: str, source: str,
                        message: str, location: str):
        """将事件写入文本主日志（通过 LogClient）。"""
        if not self._config.get("text_log_enabled", True):
            return
        if not self._log_client:
            return

        tag = self.TAG_MAP.get(table, "[NATIVE]")
        log_level = self.LEVEL_MAP.get(level, "INFO")
        config_level = self._config.get("text_log_level", "INFO")
        level_order = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3}
        if level_order.get(log_level, 1) < level_order.get(config_level, 1):
            return  # 低于配置级别则跳过

        loc_suffix = f" {location}" if location else ""
        full_msg = f"{tag} [{level}]{loc_suffix}: {message[:300]}"

        try:
            if log_level == "ERROR":
                self._log_client.error(full_msg)
            elif log_level == "WARN":
                self._log_client.warn(full_msg)
            else:
                self._log_client.info(full_msg)
        except Exception:
            pass

    def _emergency_log(self, message: str):
        """紧急日志（不依赖 LogClient，直接 stderr）。"""
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            sys.stderr.write(f"[{ts}] [ERROR] [NATIVE-MGR] {message}\n")
        except Exception:
            pass

    # ── 数据清理 ──────────────────────────────────────

    def _clean_old_data(self):
        """启动时清理过期 + 超出上限的数据。"""
        max_rows = self._config.get("max_rows_per_table", 50000)
        retention_sec = self._config.get("retention_days", 7) * 86400
        cutoff = time.time() - retention_sec

        conn = self._ensure_db()
        if conn is None:
            return

        try:
            for table in ("native_events", "thread_events", "resource_events"):
                # 按时间清理
                conn.execute(_CLEAN_SQL_AGE.format(table=table), (cutoff,))
                # 按数量清理（保留最近 max_rows 条）
                conn.execute(_CLEAN_SQL_CAP.format(table=table), (max_rows,))
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ── 健康检查 ──────────────────────────────────────

    def health_check(self):
        """启动 30 秒后自检：尝试写一条测试事件并回读验证。

        在 StarDebate_app._init_native_events 中通过 QTimer 调用。
        """
        # 写入一条测试事件
        self.write_event(
            "native_events",
            "audit", "native.health_check",
            "NativeEventManager 健康检查通过",
            location="native_log_manager.py:health_check",
        )
        self.flush()

        # 验证 SQLite 可读
        try:
            conn = sqlite3.connect(self._db_path, timeout=3)
            cursor = conn.execute(
                "SELECT COUNT(*) FROM native_events WHERE source=?",
                ("native.health_check",)
            )
            count = cursor.fetchone()[0]
            conn.close()
            if count > 0:
                msg = f"底层事件 SQLite 自检通过 ({count} 条测试记录)"
                self._emergency_log(msg)
            else:
                self._emergency_log("底层事件 SQLite 自检失败: 回读零条")
        except Exception as e:
            self._emergency_log(f"底层事件 SQLite 自检异常: {e}")


import sys  # 用于 _emergency_log
