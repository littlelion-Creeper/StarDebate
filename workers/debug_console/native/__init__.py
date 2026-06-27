"""底层事件记录系统 (Native Event Logging) v1.3.0 — M4 第三方库+UI+分析扩展

覆盖 6 类底层 Bug 捕获:
  L1: Qt C++ 层 (qFatal/qCritical/qWarning)
  L2: Python 全局异常 (excepthook + unraisablehook + audithook + c_exception)
  L3: GC 回收异常 (gc.callbacks)
  L4: 资源跟踪 (fd 统计 + Qt 无父 widget + atexit 扫描)
  L5: 线程健康 (线程死/卡死/死锁/主循环心跳)
  L6: 第三方库错误 (requests/urllib3/ctypes/json) ✓

标签前缀: [NATIVE] / [THREAD] / [RES] / [EXT]
SQLite 库: docs/log/native.db (3 表 WAL 模式)
"""

from .native_log_manager import NativeEventManager
from .native_hooks import install_native_hooks, uninstall_native_hooks
from .native_thread_monitor import NativeThreadMonitor
from .native_resource_monitor import NativeResourceMonitor
from .native_chronicle_bridge import NativeChronicleBridge
from .native_lib_wrapper import install_lib_wrappers, uninstall_lib_wrappers

__all__ = [
    "NativeEventManager",
    "install_native_hooks",
    "uninstall_native_hooks",
    "NativeThreadMonitor",
    "NativeResourceMonitor",
    "NativeChronicleBridge",
    "install_lib_wrappers",
    "uninstall_lib_wrappers",
]
__version__ = "1.3.0"
