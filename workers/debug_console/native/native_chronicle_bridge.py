"""起居注桥接器 — NativeChronicleBridge (M3 v1.2.0)

双向弱联动：将重大底层事件注入起居注上下文。

联动条件:
  - deadlock_suspect → 始终联动，CRON context 标记 ERROR
  - main_loop_no_resp → 始终联动，CRON context 标记 ERROR
  - fd_leak (count > 2000) → 阈值触发，CRON context 标记 ERROR
  - 其他事件 → 不联动

架构:
  native_event → _write_text_log() 原调用路径（文本日志）
               → _maybe_bridge()    新调用路径（起居注）
                   → chronicle._on_error("ERROR", msg) → 标记所有活跃 CRON context

安装方式: bridge.install() 在 _init_native_events() 末尾调用
卸载方式: bridge.uninstall() 在 closeEvent 调用
"""


class NativeChronicleBridge:
    """起居注桥接器 — 重大底层事件注入 CRON 上下文。

    Args:
        manager: NativeEventManager 实例
        log_client: LogClient 实例（用于访问 _chronicle）
    """

    # fd_leak 二次阈值（高于此值才桥接）
    FD_LEAK_BRIDGE_THRESHOLD = 2000

    def __init__(self, manager, log_client):
        self._manager = manager
        self._log_client = log_client

        # 保存原始方法引用
        self._orig_write_text_log = None

    # ── 安装/卸载 ────────────────────────────────────

    def install(self):
        """安装桥接器 — 包装 manager._write_text_log。

        在 _write_text_log 执行完毕后，检查事件是否应桥接到起居注。
        """
        try:
            self._orig_write_text_log = self._manager._write_text_log
        except AttributeError:
            return

        def _bridged_write_text_log(table, level, source, message, location):
            """包装的 _write_text_log — 先写文本日志，再桥接起居注。"""
            try:
                self._orig_write_text_log(table, level, source, message, location)
            except Exception:
                pass
            try:
                self._maybe_bridge(table, level, source, message)
            except Exception:
                pass

        self._manager._write_text_log = _bridged_write_text_log

    def uninstall(self):
        """卸载桥接器 — 恢复原始 _write_text_log。"""
        if self._orig_write_text_log is not None:
            try:
                self._manager._write_text_log = self._orig_write_text_log
            except Exception:
                pass
            self._orig_write_text_log = None

    # ── 桥接逻辑 ─────────────────────────────────────

    def _maybe_bridge(self, table: str, level: str, source: str, message: str):
        """判断事件是否需要桥接到起居注。

        Args:
            table: 表名 (thread_events / resource_events)
            level: 事件级别 (deadlock_suspect / fd_leak 等)
            source: 事件来源
            message: 事件消息
        """
        chronicle = self._get_chronicle()
        if chronicle is None:
            return

        bridge_msg = None

        if table == "thread_events":
            if level == "deadlock_suspect":
                bridge_msg = (
                    f"[NATIVE-BRIDGE] 线程死锁嫌疑: {message[:200]}"
                )
            elif level == "main_loop_no_resp":
                bridge_msg = (
                    f"[NATIVE-BRIDGE] Qt 主循环无响应: {message[:200]}"
                )

        elif table == "resource_events":
            if level == "fd_leak":
                # 从消息中解析句柄数，只桥接超过二次阈值的情况
                count = self._extract_fd_count(message)
                if count > self.FD_LEAK_BRIDGE_THRESHOLD:
                    bridge_msg = (
                        f"[NATIVE-BRIDGE] 文件句柄严重泄漏 "
                        f"({count} handles): {message[:150]}"
                    )

        if bridge_msg:
            chronicle._on_error("ERROR", bridge_msg)

    # ── 辅助 ──────────────────────────────────────────

    def _get_chronicle(self):
        """获取起居注实例。"""
        if not self._log_client:
            return None
        try:
            return getattr(self._log_client, '_chronicle', None)
        except Exception:
            return None

    @staticmethod
    def _extract_fd_count(message: str) -> int:
        """从消息中提取文件句柄数。"""
        try:
            # 消息格式: "File handles: 1234 (threshold: 1000)"
            if "File handles:" in message:
                after = message.split("File handles:")[1].strip()
                count_str = after.split(" ")[0]
                return int(count_str)
        except Exception:
            pass
        return 0
