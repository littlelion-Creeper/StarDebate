"""调试台模块 — DebugConsole

提供运行时日志查看、命令执行、日志导出/清理、调试模式监视等功能。

使用方式:
    from workers.debug_console import DebugConsoleWindow

    console = DebugConsoleWindow(parent_window)
    console.show()

调试监视管理器:
    from workers.debug_console import DebugMonitorManager
    mgr = DebugMonitorManager.instance(project_root)
    mgr.log_variable_change(...)  # 记录变量变化
    mgr.log_function_call(...)    # 记录函数结果
    mgr.log_plugin_status(...)    # 记录插件状态
    mgr.log_api_result(...)       # 记录 API 结果
    mgr.log_ai_result(...)        # 记录 AI 结果
"""

from .debug_console_window import DebugConsoleWindow
from .suggest_popup import SuggestPopup
from .debug_monitor_manager import DebugMonitorManager
from .debug_mode_dialog import DebugModeDialog

__all__ = [
    "DebugConsoleWindow",
    "SuggestPopup",
    "DebugMonitorManager",
    "DebugModeDialog",
]
