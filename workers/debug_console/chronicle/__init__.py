"""起居注 (ActivityChronicle) 模块 (v2.0.0)
============================================================================
v2.0.0 新增功能（崩溃定位优化）:
  ★ 完整 traceback — 异常捕获保留完整堆栈
  ★ 操作元数据 — begin() 支持 metadata 参数
  ★ Lineage 快照 — 崩溃前活跃操作链
  ★ Qt message handler — 拦截 Qt C++ 层错误
  ★ Worker 线程保护 — QThread Worker 异常捕获
  ★ 守护日志环 — 崩溃前最后 N 条日志保留

提供自动活动日志功能：不修改任何现有代码，通过运行时 monkey-patch
自动记录功能/插件/API/AI 的执行成功/失败。

标签: [CRON] (Chronicle Record)

使用方式:
    # 启动时注入自动钩子 (StarDebate_app._init_chronicle):
    from workers.debug_console.chronicle import install_chronicle
    saved_refs = install_chronicle(log_client)

    # 手动装饰器追踪:
    @log_client.track("feature", "my_func")
    def my_func(): ...

    # 上下文管理器追踪:
    with log_client.track_ctx("api", "endpoint"):
        do_request()

    # 关闭时卸载:
    from workers.debug_console.chronicle import uninstall_chronicle
    uninstall_chronicle(saved_refs)
============================================================================
"""

from .chronicle_manager import ActivityChronicle, ChronicleContext
from .chronicle_patcher import install_chronicle, uninstall_chronicle

__all__ = [
    "ActivityChronicle",
    "ChronicleContext",
    "install_chronicle",
    "uninstall_chronicle",
]
__version__ = "2.0.0"
