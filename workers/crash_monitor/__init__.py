"""奔溃弹窗模块 — CrashMonitor

独立进程监控主程序是否崩溃，崩溃后弹出日志查看窗口。
同时提供 stderr 重定向功能，将 Python 错误输出写入日志文件。

使用方式:
    from workers.crash_monitor import start_crash_monitor, StderrToLogRedirector

    # stderr 重定向（确保崩溃 traceback 写入日志）
    redirector = StderrToLogRedirector(log_file_path)
    redirector.install()

    # 启动崩溃监控
    event, process = start_crash_monitor(pid, log_path, project_root)

    # 正常退出前通知监控进程
    event.set()
    process.join(timeout=3)

模块导出:
    - start_crash_monitor: 启动监控进程
    - CrashPopup: 崩溃弹窗（独立进程使用）
    - StderrToLogRedirector: stderr → 日志文件重定向器
"""

from .crash_monitor import (start_crash_monitor, CrashPopup, StderrToLogRedirector,
                             show_startup_failure_dialog)

__all__ = [
    "start_crash_monitor", "CrashPopup", "StderrToLogRedirector",
    "show_startup_failure_dialog",
]
