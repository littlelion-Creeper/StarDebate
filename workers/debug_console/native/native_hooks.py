"""底层事件钩子注册 — native_hooks (M2 v1.1.0)

M1 覆盖:
  L1: Qt C++ 层增强 — 拦截 qWarning/qCritical/qFatal，写入 SQLite
  L2: excepthook 增强 — 未捕获异常写入 SQLite + 完整 traceback

M2 新增 (Python 内部机制):
  L2: unraisablehook 增强 — __del__/生成器/__exit__ 中的异常 (Python 3.8+)
  L2: audithook — import/open/socket/ctypes 审计事件 (Python 3.8+)
  L3: gc.callbacks — 不可回收对象检测 + GC 阶段监控
  L2: c_exception — C 函数异常跟踪 (sys.setprofile，默认关闭)

安装方式: 在 NativeEventManager 初始化后调用 install_native_hooks(manager)
卸载方式: uninstall_native_hooks(saved_refs)

与现有 chronicle_patcher 的关系:
  - chronicle_patcher 写 [CRON] 标签到文本日志（用于起居注上下文标记）
  - native_hooks 写 [NATIVE] 标签到文本日志 + 完整数据到 SQLite
  - 两者并行运行，互不干扰
  - native_hooks 在调用原始 hook 前先写 SQLite（不修改原始行为）

注意: audithook 通过 sys.addaudithook 注册，Python 标准库不提供移除机制，
      因此 uninstall 时无法真正卸载。native 系统通过 manager.is_running 标志
      在 close 后静默跳过所有审计事件。
"""

import sys
import gc
import time
import json
import traceback as tb_module


def install_native_hooks(manager):
    """安装底层事件钩子 (M1: Qt handler + excepthook)。返回保存的原始引用。

    Args:
        manager: NativeEventManager 实例

    Returns:
        dict: 保存的原始引用，供 uninstall_native_hooks() 恢复
    """
    saved = {}

    # ── ① Qt message handler 增强 (L1) ──────────────────────
    try:
        from PyQt5.QtCore import qInstallMessageHandler, QtMsgType
    except ImportError:
        pass
    else:
        _install_qt_hook(manager, saved)

    # ── ② excepthook 增强 (L2) ───────────────────────────────
    _install_excepthook(manager, saved)

    # ── ③ unraisablehook 增强 (L2) ──────────────────────────
    _install_unraisablehook(manager, saved)

    # ── ④ audithook (L2) ────────────────────────────────────
    _install_audithook(manager, saved)

    # ── ⑤ gc.callbacks (L3) ─────────────────────────────────
    _install_gc_callbacks(manager, saved)

    # ── ⑥ c_exception profile (L2, 默认关闭) ───────────────
    _install_c_exception_profile(manager, saved)

    return saved


def uninstall_native_hooks(saved: dict):
    """卸载所有底层事件钩子，恢复原始引用。"""
    if not saved:
        return

    # 恢复 Qt handler
    if "qt_orig_handler" in saved:
        try:
            from PyQt5.QtCore import qInstallMessageHandler
            qInstallMessageHandler(saved["qt_orig_handler"])
        except Exception:
            pass

    # 恢复 excepthook
    if "excepthook" in saved:
        try:
            if hasattr(sys.excepthook, "__native_event_hook__"):
                sys.excepthook = saved["excepthook"]
        except Exception:
            pass

    # 恢复 unraisablehook
    if "unraisablehook" in saved:
        try:
            if hasattr(sys.unraisablehook, "__native_event_hook__"):
                sys.unraisablehook = saved["unraisablehook"]
        except Exception:
            pass

    # 恢复 gc.callbacks
    if "gc_callbacks" in saved:
        try:
            gc.callbacks = saved["gc_callbacks"]
        except Exception:
            pass

    # 恢复 c_exception profile
    if "c_exception_profiler" in saved:
        try:
            import sys as _sys
            _sys.setprofile(saved["c_exception_profiler"])
        except Exception:
            pass

    # 注意: audithook 通过 sys.addaudithook 注册，Python 标准库
    # 不提供移除机制。native 系统通过 manager.is_running 标志在
    # close 后静默跳过。此处记录已关闭状态。
    if "audithook_installed" in saved:
        saved["audithook_installed"] = False


# ════════════════════════════════════════════════════════
#  Qt Message Handler (L1)
# ════════════════════════════════════════════════════════

_QT_MSG_NAMES = {}  # 懒初始化


def _get_qt_msg_names():
    global _QT_MSG_NAMES
    if not _QT_MSG_NAMES:
        try:
            from PyQt5.QtCore import QtMsgType
            _QT_MSG_NAMES = {
                QtMsgType.QtDebugMsg: ("DEBUG", 0),
                QtMsgType.QtWarningMsg: ("WARN", 1),
                QtMsgType.QtCriticalMsg: ("CRITICAL", 2),
                QtMsgType.QtFatalMsg: ("FATAL", 3),
                QtMsgType.QtInfoMsg: ("INFO", 4),
            }
        except Exception:
            _QT_MSG_NAMES = {0: ("DEBUG", 0), 1: ("WARN", 1),
                             2: ("CRITICAL", 2), 3: ("FATAL", 3), 4: ("INFO", 4)}
    return _QT_MSG_NAMES


def _install_qt_hook(manager, saved: dict):
    """安装增强型 Qt message handler（写 SQLite + 不修改原始行为）。"""
    from PyQt5.QtCore import qInstallMessageHandler

    # 获取当前 handler（可能是 chronicle_patcher 安装的）
    try:
        orig_handler = qInstallMessageHandler(None)  # 获取并暂时重置
    except Exception:
        orig_handler = None
    saved["qt_orig_handler"] = orig_handler

    _QT_LEVEL_MAP = {
        0: ("qt_debug", "DEBUG"),
        1: ("qt_warning", "qt_warning"),
        2: ("qt_critical", "qt_critical"),
        3: ("qt_fatal", "qt_fatal"),
        4: ("qt_info", "INFO"),
    }

    def _native_qt_handler(msg_type, context, msg):
        """底层事件 Qt handler — 写入 SQLite，然后调用原始 handler。

        递归保护: 防止 handler 自身的操作又触发 Qt message。
        """
        # 递归保护
        if getattr(manager._hook_active, 'qt', False):
            if orig_handler:
                try:
                    orig_handler(msg_type, context, msg)
                except Exception:
                    pass
            return

        try:
            manager._hook_active.qt = True

            # 提取 QMessageLogContext
            ctx_file = getattr(context, 'file', '') or ''
            ctx_line = getattr(context, 'line', 0) or 0
            ctx_func = getattr(context, 'function', '') or ''
            ctx_cat = getattr(context, 'category', '') or ''

            # 构建定位串
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

            # 级别映射
            msg_names = _get_qt_msg_names()
            type_name, type_code = msg_names.get(msg_type, ("?", -1))
            level_key = _QT_LEVEL_MAP.get(msg_type, ("qt_warning", "qt_warning"))[0]

            # 构建额外信息
            detail = {}
            if ctx_cat:
                detail["qt_category"] = ctx_cat
            detail["qt_type_name"] = type_name
            detail["qt_type_code"] = type_code

            # 写入 SQLite
            manager.write_event(
                "native_events",
                level=level_key,
                source="QtMsgHandler",
                message=str(msg)[:500],
                location=location,
                detail_json=json.dumps(detail, ensure_ascii=False),
                func_name=ctx_func[:100] if ctx_func else "",
            )

        except Exception:
            pass
        finally:
            manager._hook_active.qt = False

        # 始终调用原始 handler
        if orig_handler:
            try:
                orig_handler(msg_type, context, msg)
            except Exception:
                pass

    # 标记我们的 handler
    _native_qt_handler.__native_event_hook__ = True
    qInstallMessageHandler(_native_qt_handler)
    saved["qt_handler_func"] = _native_qt_handler


# ════════════════════════════════════════════════════════
#  excepthook 增强 (L2)
# ════════════════════════════════════════════════════════

def _install_excepthook(manager, saved: dict):
    """安装增强型 excepthook — 未捕获异常写入 SQLite。"""
    saved["excepthook"] = sys.excepthook  # 当前可能是 _chronicle_excepthook

    def _native_excepthook(etype, value, tb):
        """底层事件 excepthook — 写 SQLite，然后调用原始 hook。

        递归保护: 防止 SQLite 写失败再次触发 excepthook。
        """
        if getattr(manager._hook_active, 'excepthook', False):
            # 直接调用原始 hook 并返回
            orig = saved.get("excepthook") or sys.__excepthook__
            try:
                orig(etype, value, tb)
            except Exception:
                pass
            return

        try:
            manager._hook_active.excepthook = True

            # 提取 traceback
            tb_str = ""
            try:
                tb_str = "".join(
                    tb_module.format_exception(etype, value, tb)
                )
            except Exception:
                tb_str = f"{etype.__name__}: {value}"

            # 提取顶部函数名
            func_name = ""
            if tb:
                try:
                    last_frame = tb
                    while last_frame.tb_next:
                        last_frame = last_frame.tb_next
                    func_name = last_frame.tb_frame.f_code.co_name[:100]
                except Exception:
                    pass

            detail = {
                "exception_type": etype.__name__,
                "exception_msg": str(value)[:500],
                "traceback": tb_str[:2000],
            }

            # 写入 SQLite
            manager.write_event(
                "native_events",
                level="uncaught",
                source="sys.excepthook",
                message=f"{etype.__name__}: {value}"[:500],
                location="",
                detail_json=json.dumps(detail, ensure_ascii=False),
                func_name=func_name,
            )

        except Exception:
            pass
        finally:
            manager._hook_active.excepthook = False

        # 调用原始 hook
        orig = saved.get("excepthook") or sys.__excepthook__
        try:
            orig(etype, value, tb)
        except Exception:
            # 最后兜底
            try:
                sys.__excepthook__(etype, value, tb)
            except Exception:
                pass

    _native_excepthook.__native_event_hook__ = True
    sys.excepthook = _native_excepthook


# ════════════════════════════════════════════════════════
#  unraisablehook 增强 (L2)
# ════════════════════════════════════════════════════════

def _install_unraisablehook(manager, saved: dict):
    """安装 unraisablehook — 捕获 __del__/生成器/__exit__ 等不可抛出异常。

    sys.unraisablehook (Python 3.8+) 在以下场景被调用:
      - __del__ 方法抛出异常
      - 生成器通过 .throw() 触发但生成器未捕获
      - __exit__ / __enter__ 中异常反复抛出
      - setter 中异常

    这些是 sys.excepthook 无法捕获的"不可抛出的异常"。
    """
    if not hasattr(sys, 'unraisablehook'):
        return  # Python < 3.8

    if not manager._config.get("hooks", {}).get("unraisablehook", True):
        return

    saved["unraisablehook"] = sys.unraisablehook

    def _native_unraisablehook(unraisable):
        """捕获不可抛出的异常 → 写 SQLite + 文本日志。

        unraisable 对象字段:
           exc_type:      异常类型 (Type 对象)
           exc_value:     异常实例
           exc_traceback: traceback 对象
           err_msg:       错误消息
           object:        出错的原始对象
        """
        if getattr(manager._hook_active, 'unraisable', False):
            orig = saved.get("unraisablehook") or sys.__unraisablehook__
            try:
                orig(unraisable)
            except Exception:
                pass
            return

        try:
            manager._hook_active.unraisable = True

            exc_type = getattr(unraisable, 'exc_type', None)
            exc_value = getattr(unraisable, 'exc_value', None)
            exc_tb = getattr(unraisable, 'exc_traceback', None)
            err_msg = getattr(unraisable, 'err_msg', '') or ''
            obj = getattr(unraisable, 'object', None)

            # 提取异常信息
            type_name = getattr(exc_type, '__name__', '?')
            val_str = str(exc_value) if exc_value else ''
            obj_repr = repr(obj)[:100] if obj is not None else ''

            # 提取 traceback
            tb_str = ""
            if exc_tb:
                try:
                    tb_str = "".join(
                        tb_module.format_exception(exc_type, exc_value, exc_tb)
                    )[:2000]
                except Exception:
                    pass

            # 提取函数名
            func_name = ""
            if exc_tb:
                try:
                    last_frame = exc_tb
                    while last_frame.tb_next:
                        last_frame = last_frame.tb_next
                    func_name = last_frame.tb_frame.f_code.co_name[:100]
                except Exception:
                    pass

            # 构建来源标记
            source_hint = ""
            if "del" in err_msg.lower() or "__del__" in err_msg:
                source_hint = "__del__"
            elif "throw" in err_msg.lower():
                source_hint = "generator.throw"
            elif "exit" in err_msg.lower():
                source_hint = "__exit__"
            elif "enter" in err_msg.lower():
                source_hint = "__enter__"
            else:
                source_hint = "unraisable"

            detail = {
                "err_msg": err_msg[:200],
                "object_repr": obj_repr,
                "exception_type": type_name,
                "exception_msg": val_str[:500],
                "traceback": tb_str,
                "source_hint": source_hint,
            }

            message = f"[{source_hint}] {type_name}"
            if val_str:
                message += f": {val_str[:200]}"
            location = f"object={obj_repr}" if obj_repr else ""

            manager.write_event(
                "native_events",
                level="unraisable",
                source="sys.unraisablehook",
                message=message[:500],
                location=location[:200],
                detail_json=json.dumps(detail, ensure_ascii=False),
                func_name=func_name,
            )

        except Exception:
            pass
        finally:
            manager._hook_active.unraisable = False

        # 调用原始 hook
        orig = saved.get("unraisablehook") or sys.__unraisablehook__
        try:
            orig(unraisable)
        except Exception:
            pass

    _native_unraisablehook.__native_event_hook__ = True
    sys.unraisablehook = _native_unraisablehook


# ════════════════════════════════════════════════════════
#  audithook (L2)
# ════════════════════════════════════════════════════════

# 感兴趣的审计事件白名单（过滤低价值事件）
_AUDIT_INTERESTING_EVENTS = frozenset({
    "import",
    "open",
    "socket.connect",
    "socket.bind",
    "subprocess.Popen",
    "ctypes.dlopen",
    "ctypes.call_function",
    "os.system",
    "os.exec",
    "os.fork",
    "os.kill",
    "winreg.*",
    "builtins.input",
})

# 事件名匹配函数（支持通配符 *）
def _match_audit_event(event: str) -> bool:
    """判断审计事件是否在白名单中。"""
    if event in _AUDIT_INTERESTING_EVENTS:
        return True
    for pattern in _AUDIT_INTERESTING_EVENTS:
        if pattern.endswith('*') and event.startswith(pattern[:-1]):
            return True
    return False


def _install_audithook(manager, saved: dict):
    """安装 audithook — 记录 import/open/socket/ctypes 等安全敏感操作。

    注意:
      - sys.addaudithook 是 append-only，无移除机制。
      - 因此 audithook 的 uninstall 是"软卸载"：关闭时设置
        saved["audithook_installed"] = False，hook 函数内部检查
        manager.is_running 则跳过。
      - 也可以通过替换 audit_hook 为 no-op 并保存原始引用来解决，
        但对于已有多个 audit hook 的环境可能干扰其他 hook。
        软卸载是当前最安全的做法。
    """
    if not hasattr(sys, 'addaudithook'):
        return  # Python < 3.8

    if not manager._config.get("hooks", {}).get("audithook", True):
        return

    def _native_audithook(event: str, args):
        """审计事件回调 — 过滤白名单后写 SQLite。

        递归保护: 通过 saved["audithook_installed"] 标志控制。
        """
        # 软卸载检测
        if not saved.get("audithook_installed", True):
            return
        if not manager.is_running:
            return

        # 递归保护
        if getattr(manager._hook_active, 'audit', False):
            return
        if not _match_audit_event(event):
            return

        try:
            manager._hook_active.audit = True

            # 参数摘要
            arg_summary = ""
            try:
                arg_parts = []
                for a in args[:3]:  # 最多 3 个参数
                    s = str(a)[:80]
                    if s:
                        arg_parts.append(s)
                arg_summary = ", ".join(arg_parts)
            except Exception:
                pass

            detail = {
                "event": event,
                "arg_summary": arg_summary[:300],
            }

            # 如果参数包含完整 path，放入 location
            location = ""
            try:
                if event == "open" and args:
                    path = str(args[0])[:200]
                    location = path
                elif event == "import" and args:
                    mod_name = str(args[0])[:100]
                    location = f"import {mod_name}"
                elif event == "ctypes.dlopen" and args:
                    lib = str(args[0])[:100]
                    location = f"dlopen({lib})"
            except Exception:
                pass

            message = event
            if arg_summary:
                message += f" ({arg_summary[:200]})"

            manager.write_event(
                "native_events",
                level="audit",
                source="sys.addaudithook",
                message=message[:500],
                location=location[:200],
                detail_json=json.dumps(detail, ensure_ascii=False),
            )

        except Exception:
            pass
        finally:
            manager._hook_active.audit = False

    try:
        sys.addaudithook(_native_audithook)
        saved["audithook_installed"] = True
        saved["audithook_func"] = _native_audithook
    except Exception:
        pass


# ════════════════════════════════════════════════════════
#  gc.callbacks (L3)
# ════════════════════════════════════════════════════════

def _install_gc_callbacks(manager, saved: dict):
    """安装 gc.callbacks — 监测 GC 周期 + 不可回收对象。

    gc.callbacks 在以下阶段被调用:
      - "start" / "stop" (全局 GC)
      - "start" / "stop" + generation=0/1/2 (分代 GC)
      - info dict 包含: generation, collected, uncollectable

    只关注:
      - "stop" 阶段的 uncollectable > 0
      - "stop" 阶段的 collected 异常值（如 0 但 generation 非空）
    """
    if not hasattr(gc, 'callbacks'):
        return  # Python < 3.3

    if not manager._config.get("hooks", {}).get("gc_callbacks", True):
        return

    # 保存原始回调列表
    saved["gc_callbacks"] = list(gc.callbacks)

    def _native_gc_callback(phase: str, info: dict):
        """GC 阶段回调 — 记录不可回收对象 + 异常情况。"""
        if getattr(manager._hook_active, 'gc', False):
            return
        if not manager.is_running:
            return

        try:
            manager._hook_active.gc = True

            generation = info.get("generation", -1)
            collected = info.get("collected", 0)
            uncollectable = info.get("uncollectable", 0)

            if phase == "stop" and uncollectable > 0:
                # 检测不可回收对象详情
                unreachable = []
                try:
                    # gc.garbage 在 Python 3.4+ 不再存储不可达对象，
                    # 改用 gc.get_stats() 获取更多信息
                    stats = gc.get_stats()
                    if stats and generation >= 0 and generation < len(stats):
                        gen_stats = stats[generation]
                        unreachable.append(
                            f"gen{generation}: collected={collected} "
                            f"uncollectable={uncollectable}"
                        )
                except Exception:
                    pass

                # 尝试获取当前不可回收对象的类型分布
                type_counts = {}
                try:
                    for obj in gc.get_objects():
                        if not gc.is_tracked(obj):
                            continue
                        try:
                            refs = gc.get_referrers(obj)
                            if any(isinstance(r, type) for r in refs):
                                tname = type(obj).__name__
                                type_counts[tname] = type_counts.get(tname, 0) + 1
                        except Exception:
                            pass
                except Exception:
                    pass

                detail = {
                    "generation": generation,
                    "collected": collected,
                    "uncollectable": uncollectable,
                    "stats": unreachable,
                    "type_counts": type_counts,
                }

                gc_count = sum(
                    s.get("collected", 0) for s in gc.get_stats()
                )

                manager.write_event(
                    "resource_events",
                    kind="gc_uncollectable",
                    obj_type="mixed",
                    obj_repr=f"{uncollectable} uncollectable objects in gen{generation}",
                    count=gc_count,
                    detail=json.dumps(detail, ensure_ascii=False)[:2000],
                )

            elif phase == "stop" and collected == 0 and generation >= 0:
                # 异常: GC 扫描了但没有收集（可能循环引用泄漏）
                detail = {
                    "generation": generation,
                    "collected": 0,
                    "uncollectable": uncollectable,
                }
                manager.write_event(
                    "resource_events",
                    kind="gc_uncollectable",
                    obj_type="suspect",
                    obj_repr=f"gen{generation} collected 0 objects",
                    count=0,
                    detail=json.dumps(detail, ensure_ascii=False)[:500],
                )

        except Exception:
            pass
        finally:
            manager._hook_active.gc = False

    try:
        gc.callbacks.append(_native_gc_callback)
        saved["gc_callback_func"] = _native_gc_callback
    except Exception:
        pass


# ════════════════════════════════════════════════════════
#  c_exception profile (L2, 默认关闭)
# ════════════════════════════════════════════════════════

def _install_c_exception_profile(manager, saved: dict):
    """安装 sys.setprofile — 仅捕获 c_exception 事件。

    注意:
      - sys.setprofile 在每次函数调用/返回时触发，有性能开销。
      - 默认关闭（需要 native_log_config.json 中显式启用）。
      - 启用后只关注 c_exception 事件，其他事件忽略（但仍被调用）。
      - 建议只在调试 CPU 使用率不敏感的场合启用。
    """
    if not manager._config.get("hooks", {}).get("c_exception_profile", False):
        return  # 默认关闭

    # 保存当前 profiler
    try:
        saved["c_exception_profiler"] = sys.getprofile()
    except Exception:
        saved["c_exception_profiler"] = None

    # 内部计数器（用于日志消噪：每秒最多记录 5 条同源异常）
    _c_exception_counter = {}

    def _native_profile(frame, event, arg):
        """sys.setprofile 回调 — 仅关注 c_exception。

        注意: 即使只关心 c_exception，setprofile 仍然会在
        每次函数调用/返回时调用此函数（然后被 event != "c_exception" 短路）。
        这是 setprofile 的 API 限制，无法避免。
        """
        if event != "c_exception":
            # 调用原始 profiler（如果有）
            orig_prof = saved.get("c_exception_profiler")
            if orig_prof:
                try:
                    orig_prof(frame, event, arg)
                except Exception:
                    pass
            return

        # 递归保护
        if getattr(manager._hook_active, 'c_exception', False):
            return
        if not manager.is_running:
            return

        try:
            manager._hook_active.c_exception = True

            # 提取异常信息
            exc_type = None
            exc_value = None
            if isinstance(arg, tuple) and len(arg) >= 2:
                exc_type = arg[0]
                exc_value = arg[1]
            elif arg is not None:
                exc_type = type(arg).__name__

            type_name = getattr(exc_type, '__name__', str(exc_type))

            # 消噪：每秒同类型最多 5 条
            now_sec = int(time.time())
            key = (type_name, frame.f_code.co_name)
            counter_key = (now_sec, key)
            count = _c_exception_counter.get(counter_key, 0) + 1
            # 清理旧计数（保留最近 2 秒）
            if len(_c_exception_counter) > 100:
                old_keys = [k for k in _c_exception_counter if k[0] < now_sec - 2]
                for k in old_keys:
                    del _c_exception_counter[k]
            _c_exception_counter[counter_key] = count
            if count > 5:
                return

            # 构建详情
            code = frame.f_code
            func_name = code.co_name[:100]
            filename = code.co_filename.split('\\')[-1].split('/')[-1]
            lineno = frame.f_lineno

            detail = {
                "c_exception_type": type_name,
                "calling_frame": f"{filename}:L{lineno}:{func_name}",
                "locals_sample": {},
            }

            # 采样局部变量（最多 5 个，截断值）
            try:
                sample = {}
                for k, v in list(frame.f_locals.items())[:5]:
                    try:
                        sample[k] = str(v)[:80]
                    except Exception:
                        sample[k] = "<?>"
                detail["locals_sample"] = sample
            except Exception:
                pass

            location = f"{filename}:L{lineno}"
            val_str = str(exc_value)[:200] if exc_value else ""

            message = f"[C_EXCEPTION] {type_name}"
            if val_str:
                message += f": {val_str}"

            manager.write_event(
                "native_events",
                level="uncaught",
                source="sys.setprofile",
                message=message[:500],
                location=location[:200],
                detail_json=json.dumps(detail, ensure_ascii=False),
                func_name=func_name,
            )

        except Exception:
            pass
        finally:
            manager._hook_active.c_exception = False

            # 调用原始 profiler
            orig_prof = saved.get("c_exception_profiler")
            if orig_prof:
                try:
                    orig_prof(frame, event, arg)
                except Exception:
                    pass

    try:
        sys.setprofile(_native_profile)
        saved["c_exception_profiler_func"] = _native_profile
    except Exception:
        pass
