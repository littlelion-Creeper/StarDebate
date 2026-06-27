"""调试监视管理器 — DebugMonitorManager

负责：
  - 加载/保存 config/debug_monitor.json 配置
  - 管理 5 项监视开关（变量/函数/插件/API/AI）
  - 提供日志钩子方法供各处调用
  - Layer 1: 通过 multiprocessing.Queue 投递到 LogService 独立进程
  - Layer 2: 队列满/断时自动降级为文件直写（应急模式）
  - 兼容旧版 LogManager 直接引用（向后兼容）
"""

import os
import json
import time
from datetime import datetime
from typing import Callable, Optional

from PyQt5.QtCore import QObject, pyqtSignal


MONITOR_TYPES = ["variable_watch", "function_watch", "plugin_watch", "api_watch", "ai_watch"]

MONITOR_LABELS = {
    "variable_watch": "变量",
    "function_watch": "函数",
    "plugin_watch": "插件",
    "api_watch": "API",
    "ai_watch": "AI",
}

MONITOR_TAGS = {
    "variable_watch": "VAR",
    "function_watch": "FUNC",
    "plugin_watch": "PLUGIN",
    "api_watch": "API",
    "ai_watch": "AI",
}


class DebugMonitorManager(QObject):
    """调试监视管理器 — 单例模式，全局可用"""

    # 信号：配置变更时发出
    config_changed = pyqtSignal(dict)

    _instance: Optional["DebugMonitorManager"] = None

    @classmethod
    def instance(cls, project_root: str = None) -> "DebugMonitorManager":
        """获取单例实例。首次调用需提供 project_root。"""
        if cls._instance is None:
            if project_root is None:
                from components.res_path import get_resource_root
                project_root = get_resource_root()
            cls._instance = cls(project_root)
        return cls._instance

    def __init__(self, project_root: str):
        if self._instance is not None:
            raise RuntimeError("DebugMonitorManager 是单例，请使用 instance() 获取")
        super().__init__()
        self._project_root = project_root
        self._config_path = os.path.join(project_root, "config", "debug_monitor.json")

        # 配置数据
        self._config: dict = {}
        self._log_callback: Optional[Callable[[str, str], None]] = None  # (level, message)
        self._log_mgr = None  # LogManager 引用（旧版兼容）

        # ★ 独立日志队列投递（新版架构，优先使用）
        self._log_queue = None  # multiprocessing.Queue
        self._log_path = None  # 日志文件路径（应急直写用）
        self._emergency_count = 0  # 应急写入计数
        self._last_success_ts: float = 0  # 最后成功投递时间戳

        self._load_config()

    # ═══════════════════════════════════════════════════
    #  配置管理
    # ═══════════════════════════════════════════════════

    def _load_config(self):
        """从 JSON 文件加载配置。"""
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._config = self._default_config()
            self._save_config()

    def _save_config(self):
        """保存配置到 JSON 文件。"""
        try:
            os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
        except OSError:
            pass

    @staticmethod
    def _default_config() -> dict:
        return {
            "debug_mode_enabled": False,
            "monitors": {k: False for k in MONITOR_TYPES},
            "options": {
                "max_log_entries": 10000,
                "variable_skip_builtins": True,
                "function_min_duration_ms": 0,
                "api_trim_body_length": 500,
                "api_log_headers": False,
            },
        }

    def reset_to_default(self):
        """恢复默认配置。"""
        self._config = self._default_config()
        self._save_config()
        self.config_changed.emit(self._config)

    # ── 属性访问 ──────────────────────────────────────

    @property
    def config(self) -> dict:
        return self._config

    @property
    def enabled(self) -> bool:
        return self._config.get("debug_mode_enabled", False)

    @enabled.setter
    def enabled(self, value: bool):
        self._config["debug_mode_enabled"] = value
        self._save_config()
        self.config_changed.emit(self._config)

    @property
    def monitors(self) -> dict:
        return self._config.get("monitors", {})

    @property
    def options(self) -> dict:
        return self._config.get("options", {})

    def is_monitor_enabled(self, monitor_type: str) -> bool:
        """检查某项监视是否启用（需总开关 + 单项开关同时开启）。"""
        if not self.enabled:
            return False
        return self.monitors.get(monitor_type, False)

    def set_monitor(self, monitor_type: str, enabled: bool):
        """设置单项监视开关。"""
        if monitor_type not in MONITOR_TYPES:
            return
        self._config.setdefault("monitors", {})
        self._config["monitors"][monitor_type] = enabled
        self._save_config()
        self.config_changed.emit(self._config)

    def enable_all(self):
        """启用全部监视。"""
        self._config["debug_mode_enabled"] = True
        self._config["monitors"] = {k: True for k in MONITOR_TYPES}
        self._save_config()
        self.config_changed.emit(self._config)

    def disable_all(self):
        """禁用全部监视。"""
        self._config["debug_mode_enabled"] = False
        self._config["monitors"] = {k: False for k in MONITOR_TYPES}
        self._save_config()
        self.config_changed.emit(self._config)

    def get_active_monitors(self) -> list[str]:
        """返回当前激活的监视项标签列表。"""
        if not self.enabled:
            return []
        return [MONITOR_LABELS[k] for k in MONITOR_TYPES if self.monitors.get(k, False)]

    def set_log_manager(self, log_mgr):
        """绑定 LogManager 实例（旧版兼容）。"""
        self._log_mgr = log_mgr

    def set_log_queue(self, log_queue, log_path: str = None):
        """绑定 multiprocessing.Queue（新版架构，优先使用）。

        监视钩子条目通过队列投递到 LogService 独立进程。
        队列满或断开时自动降级为文件直写（_emergency_write）。

        Args:
            log_queue: multiprocessing.Queue 实例
            log_path: 日志文件路径（用于应急降级直写）
        """
        self._log_queue = log_queue
        self._log_path = log_path
        self._emergency_count = 0
        self._last_success_ts = time.time()

    @property
    def emergency_count(self) -> int:
        """应急写入次数（>0 表示日志队列出现异常）。"""
        return self._emergency_count

    @property
    def last_heartbeat(self) -> float:
        """最后成功投递时间戳（用于心跳超时检测）。"""
        return self._last_success_ts

    # ═══════════════════════════════════════════════════
    #  监视钩子方法
    # ═══════════════════════════════════════════════════

    def log_variable_change(self, file_path: str, line_no: int, var_name: str, new_value):
        """记录变量变化。

        Args:
            file_path: 源文件路径
            line_no: 行号
            var_name: 变量名
            new_value: 新值（会自动截断过长内容）
        """
        if not self.is_monitor_enabled("variable_watch"):
            return
        value_str = self._format_value(new_value, 200)
        msg = f"{os.path.basename(file_path)}:{line_no} → {var_name} = {value_str}"
        self._emit_monitor_log("variable_watch", msg)

    def log_function_call(self, module_name: str, func_name: str,
                          success: bool, result=None, error: str = "",
                          duration_ms: float = 0):
        """记录函数运行结果。

        Args:
            module_name: 模块名
            func_name: 函数名
            success: 是否成功
            result: 返回值（可选）
            error: 错误信息（失败时）
            duration_ms: 耗时（毫秒）
        """
        if not self.is_monitor_enabled("function_watch"):
            return
        min_dur = self.options.get("function_min_duration_ms", 0)
        if duration_ms < min_dur:
            return

        if success:
            result_str = self._format_value(result, 150) if result is not None else "None"
            msg = f"{module_name}:{func_name} → ✅ 返回({duration_ms:.0f}ms): {result_str}"
        else:
            msg = f"{module_name}:{func_name} → ❌ 异常({duration_ms:.0f}ms): {error}"
        self._emit_monitor_log("function_watch", msg)

    def log_plugin_status(self, plugin_name: str, status: str, detail: str = ""):
        """记录插件加载状态。

        Args:
            plugin_name: 插件名称
            status: 状态 ("success", "fail", "enabled", "disabled")
            detail: 详细信息
        """
        if not self.is_monitor_enabled("plugin_watch"):
            return
        icons = {"success": "✅", "fail": "❌", "enabled": "▶", "disabled": "⏸"}
        icon = icons.get(status, "•")
        status_cn = {"success": "加载成功", "fail": "加载失败", "enabled": "已启用",
                     "disabled": "已禁用"}
        msg = f"{icon} {plugin_name} {status_cn.get(status, status)}"
        if detail:
            msg += f" | {detail}"
        self._emit_monitor_log("plugin_watch", msg)

    def log_api_result(self, endpoint: str, method: str = "POST",
                       status_code: int = 0, duration_ms: float = 0,
                       request_summary: str = "", response_summary: str = "",
                       error: str = ""):
        """记录 API 运行结果。

        Args:
            endpoint: API 端点路径
            method: HTTP 方法
            status_code: HTTP 状态码
            duration_ms: 耗时
            request_summary: 请求摘要
            response_summary: 响应摘要
            error: 错误信息
        """
        if not self.is_monitor_enabled("api_watch"):
            return

        if status_code == 0 and error:
            msg = f"✗ {method} {endpoint} → 网络错误 | {error}"
        elif 200 <= status_code < 300:
            trim_len = self.options.get("api_trim_body_length", 500)
            resp = response_summary[:trim_len] if response_summary else ""
            msg = f"✓ {method} {endpoint} → {status_code} | {duration_ms:.0f}ms"
            if resp:
                msg += f" | {resp}"
        else:
            msg = f"✗ {method} {endpoint} → {status_code} | {duration_ms:.0f}ms"
            if error:
                msg += f" | {error}"
        self._emit_monitor_log("api_watch", msg)

    def log_ai_result(self, feature_name: str, success: bool,
                      duration_ms: float = 0, result_summary: str = "",
                      error: str = ""):
        """记录 AI 功能运行结果。

        Args:
            feature_name: AI 功能名称（如 "ai_analysis", "speech_writer"）
            success: 是否成功
            duration_ms: 耗时
            result_summary: 结果摘要
            error: 错误信息
        """
        if not self.is_monitor_enabled("ai_watch"):
            return
        if success:
            msg = f"✅ {feature_name} → 成功 | {duration_ms:.0f}ms"
            if result_summary:
                msg += f" | {result_summary[:200]}"
        else:
            msg = f"❌ {feature_name} → 失败 | {duration_ms:.0f}ms"
            if error:
                msg += f" | {error[:200]}"
        self._emit_monitor_log("ai_watch", msg)

    # ═══════════════════════════════════════════════════
    #  内部方法
    # ═══════════════════════════════════════════════════

    def _emit_monitor_log(self, monitor_type: str, message: str):
        """发射监视日志。

        优先级：
          1. 新版架构：通过 log_queue 投递到 LogService 独立进程
          2. 降级应急：队列满/断时直写日志文件
          3. 旧版兼容：无队列时回退到 LogManager 引用
        """
        tag = MONITOR_TAGS.get(monitor_type, "MON")
        entry = f"[{tag}] {message}"

        # ── Layer 1: 队列投递（优先）─────────────────
        if self._log_queue is not None:
            try:
                self._log_queue.put_nowait({
                    "type": "monitor",
                    "level": "INFO",
                    "message": entry,
                    "timestamp": time.time(),
                })
                self._last_success_ts = time.time()
                # 恢复计数：连续成功说明队列恢复
                if self._emergency_count > 0:
                    self._emergency_count = 0
                return
            except Exception:
                # ── Layer 2: 降级应急直写 ─────────────
                if self._log_path:
                    self._emergency_write(entry)
                    return

        # ── Layer 3: 旧版兼容（LogManager 引用）─────
        if self._log_mgr:
            self._log_mgr.info(entry)

    def _emergency_write(self, entry: str):
        """应急降级：直接写日志文件（绕过队列，确保落盘）。

        当 LogService 进程崩溃或队列满时自动触发。
        每 10 次应急写入记录一次内部警告。
        """
        self._emergency_count += 1
        if not self._log_path:
            return
        try:
            now = datetime.now()
            ts = now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"

            # 首次或每 10 次追加一条应急模式告警
            if self._emergency_count == 1 or self._emergency_count % 10 == 0:
                warn_line = (
                    f"[{ts}] [WARN] [MON-EMERGENCY] 监视队列不可用，"
                    f"已降级为文件直写 (第{self._emergency_count}次)\n"
                )
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(warn_line + f"[{ts}] [INFO] {entry}\n")
            else:
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(f"[{ts}] [INFO] {entry}\n")
        except Exception:
            pass

    @staticmethod
    def _format_value(value, max_len: int = 200) -> str:
        """安全地将值格式化为字符串并截断。"""
        try:
            s = repr(value)
        except Exception:
            s = "<无法序列化>"
        if len(s) > max_len:
            s = s[:max_len] + "…"
        return s
