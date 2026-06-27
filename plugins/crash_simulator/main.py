# -*- coding: utf-8 -*-
"""
崩溃模拟器插件 v2.1.0
====================
功能：
  1. 在右侧导航栏注册 💣「崩溃测试」按钮
  2. 点击后随机选择一种崩溃方式，让主程序崩溃退出
  3. 验证奔溃弹窗（CrashPopup）是否正常弹出并显示日志

10 种崩溃方式（v2.1.0 新增 Qt C++ 层 4 种）：
  Python 层 (6):
    1. ZeroDivisionError  — 除零错误
    2. IndexError         — 列表越界
    3. KeyError           — 字典键不存在
    4. RecursionError     — 无限递归
    5. segfault           — ctypes 非法内存访问
    6. sys.exit(1)        — 非零退出码

  Qt C++ 层 (4) ★ v2.1.0:
    7. QPainter 空设备    — QPainter.begin(None) → qWarning + 起居注记录
    8. QWidget 双重布局   — setLayout()冲突 → qWarning + 起居注记录
    9. QPixmap OOM        — 超大像素图 → qWarning + 起居注记录
   10. QObject 非法属性   — setProperty 类型冲突 → qWarning + 起居注记录

监视钩子（v2.1.0 增强）：
  - variable_watch: 记录崩溃方式选择、Qt 错误上下文变量
  - function_watch: 记录每个崩溃函数的入口/出口状态
  - plugin_watch:   插件加载/卸载/按钮点击
  - api_watch:      崩溃触发前状态快照
"""
import os
import sys
import random
import ctypes
import time
import traceback
from datetime import datetime

from workers.plugin_manager import get_api

# ── 插件元信息 ──
PLUGIN_ID = "crash_simulator"
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

# ═══════════════════════════════════════
#  辅助：监视钩子统一入口
# ═══════════════════════════════════════

def _hook(api, mtype: str, msg: str):
    """向日志系统发送监视钩子。api 为 None 时静默跳过。"""
    if api:
        try:
            api.log_monitor(mtype, msg)
        except Exception:
            pass


# ═══════════════════════════════════════
#  Python 层崩溃方式 (6 种)
# ═══════════════════════════════════════

def _crash_div_zero(api):
    """方式1：除零错误 → 进程退出"""
    _hook(api, "function_watch", "[崩溃模拟器] ZeroDivisionError 入口")
    _hook(api, "variable_watch", "[崩溃模拟器] 触发变量: 1 // 0")
    try:
        _ = 1 // 0  # noqa: F841
    except ZeroDivisionError:
        traceback.print_exc()
        _hook(api, "function_watch", "[崩溃模拟器] ZeroDivisionError 已捕获，即将退出")
    os._exit(1)


def _crash_index_error(api):
    """方式2：列表越界 → 进程退出"""
    _hook(api, "function_watch", "[崩溃模拟器] IndexError 入口")
    arr = [1, 2, 3]
    _hook(api, "variable_watch",
          f"[崩溃模拟器] 列表长度={len(arr)}，访问索引=999")
    try:
        _ = arr[999]  # noqa: F841
    except IndexError:
        traceback.print_exc()
        _hook(api, "function_watch", "[崩溃模拟器] IndexError 已捕获，即将退出")
    os._exit(1)


def _crash_key_error(api):
    """方式3：字典键不存在 → 进程退出"""
    _hook(api, "function_watch", "[崩溃模拟器] KeyError 入口")
    d = {}
    _hook(api, "variable_watch",
          "[崩溃模拟器] 空字典，访问键='不存在的键'")
    try:
        _ = d["不存在的键"]  # noqa: F841
    except KeyError:
        traceback.print_exc()
        _hook(api, "function_watch", "[崩溃模拟器] KeyError 已捕获，即将退出")
    os._exit(1)


def _crash_recursion(api):
    """方式4：无限递归 → 进程退出"""
    _hook(api, "function_watch", "[崩溃模拟器] RecursionError 入口")
    sys.setrecursionlimit(100)
    _hook(api, "variable_watch",
          f"[崩溃模拟器] recursionlimit=100 (默认 {sys.getrecursionlimit()})")
    try:
        def recurse():
            recurse()
        recurse()
    except RecursionError:
        traceback.print_exc()
        _hook(api, "function_watch", "[崩溃模拟器] RecursionError 已捕获，即将退出")
    os._exit(1)


def _crash_segfault(api):
    """方式5：真正非法内存访问 → 进程硬崩溃"""
    _hook(api, "function_watch", "[崩溃模拟器] segfault 入口")
    _hook(api, "variable_watch",
          "[崩溃模拟器] 目标地址=0x0(NULL)，源=0x12345678，大小=16字节")
    if sys.platform == "win32":
        ctypes.windll.kernel32.RtlMoveMemory(
            ctypes.c_void_p(0x0),
            ctypes.c_void_p(0x12345678),
            ctypes.c_size_t(16),
        )
    else:
        ctypes.string_at(0)
    _hook(api, "function_watch", "[崩溃模拟器] segfault 未触发？执行兜底退出")
    os._exit(1)


def _crash_exit(api):
    """方式6：非零退出码"""
    _hook(api, "function_watch", "[崩溃模拟器] sys.exit(1) 入口")
    _hook(api, "variable_watch", "[崩溃模拟器] exit_code=1")
    sys.exit(1)


# ═══════════════════════════════════════
#  ★ v2.1.0: Qt C++ 层崩溃方式 (4 种)
#  这些方法会触发 Qt 内部 qWarning/qCritical，
#  被起居注的 Qt message handler 拦截并记录
# ═══════════════════════════════════════

def _crash_qt_painter_null(api):
    """方式7：QPainter.begin(None) → qWarning

    Qt 输出:
      QPainter::begin: Paint device returned engine == 0, type: 0
    → 起居注记录: [Qt WARN#1][qpainter.cpp:L...:begin]

    不会导致进程崩溃，仅产生 Qt 内部警告。
    验证 Qt message handler 是否能正确拦截。
    """
    _hook(api, "function_watch", "[崩溃模拟器] QPainter 空设备 入口")
    _hook(api, "variable_watch",
          "[崩溃模拟器] QPainter 目标设备=None (应触发 qWarning)")
    try:
        from PyQt5.QtGui import QPainter
    except ImportError:
        _hook(api, "function_watch", "[崩溃模拟器] PyQt5 不可用，跳过")
        return

    painter = QPainter()
    _hook(api, "variable_watch",
          f"[崩溃模拟器] QPainter 实例已创建，isActive={painter.isActive()}")
    success = painter.begin(None)  # → 触发 qWarning
    _hook(api, "variable_watch",
          f"[崩溃模拟器] begin(None) 返回={success}，预期为 False")
    _hook(api, "function_watch",
          "[崩溃模拟器] QPainter 空设备完成 — 检查日志中 [Qt WARN] 标签")


def _crash_qt_double_layout(api):
    """方式8：QWidget.setLayout() 冲突 → qWarning

    Qt 输出:
      QWidget::setLayout: Attempting to set QLayout on ... which already has a layout
    → 起居注记录: [Qt WARN#1][qwidget.cpp:L...:setLayout]
    """
    _hook(api, "function_watch", "[崩溃模拟器] QWidget 双重布局 入口")
    try:
        from PyQt5.QtWidgets import QWidget, QVBoxLayout
    except ImportError:
        _hook(api, "function_watch", "[崩溃模拟器] PyQt5 不可用，跳过")
        return

    w = QWidget()
    layout1 = QVBoxLayout()
    layout2 = QVBoxLayout()
    w.setLayout(layout1)
    _hook(api, "variable_watch",
          f"[崩溃模拟器] 第一个 layout 已设置，准备设置第二个")
    w.setLayout(layout2)  # → 触发 qWarning
    _hook(api, "variable_watch",
          f"[崩溃模拟器] setLayout 冲突完成 — 检查日志中 [Qt WARN] 标签")
    _hook(api, "function_watch",
          "[崩溃模拟器] QWidget 双重布局完成")


def _crash_qt_pixmap_oom(api):
    """方式9：超大 QPixmap 内存分配 → qWarning

    Qt 输出:
      QPixmap::scaled: Pixmap is a null pixmap
      或内存分配警告
    → 起居注记录: [Qt WARN]
    """
    _hook(api, "function_watch", "[崩溃模拟器] QPixmap OOM 入口")
    try:
        from PyQt5.QtGui import QPixmap, QImage
        from PyQt5.QtCore import QSize
    except ImportError:
        _hook(api, "function_watch", "[崩溃模拟器] PyQt5 不可用，跳过")
        return

    # 尝试创建一个可能导致分配警告的图片
    try:
        pix = QPixmap(50000, 50000)  # 超大尺寸 → 可能触发资源警告
        _hook(api, "variable_watch",
              f"[崩溃模拟器] QPixmap(50000,50000) 创建{'成功' if not pix.isNull() else '失败(null)'}")
    except Exception as e:
        _hook(api, "variable_watch",
              f"[崩溃模拟器] QPixmap 创建异常: {e}")

    # 第二种方式：从 null pixmap 缩放
    null_pix = QPixmap()
    _hook(api, "variable_watch",
          f"[崩溃模拟器] null pixmap isNull={null_pix.isNull()}")
    scaled = null_pix.scaled(100, 100)  # → qWarning: Pixmap is a null pixmap
    _hook(api, "variable_watch",
          f"[崩溃模拟器] null.scaled(100,100) result isNull={scaled.isNull()}")
    _hook(api, "function_watch",
          "[崩溃模拟器] QPixmap OOM 完成 — 检查日志中 [Qt WARN] 标签")


def _crash_qt_invalid_property(api):
    """方式10：QObject.setProperty 类型冲突 → qWarning

    Qt 输出:
      QMetaProperty::write: Writing to property ... with type ... is not supported
    → 起居注记录: [Qt WARN]
    """
    _hook(api, "function_watch", "[崩溃模拟器] QObject 非法属性 入口")
    try:
        from PyQt5.QtCore import QObject
        from PyQt5.QtWidgets import QPushButton
    except ImportError:
        _hook(api, "function_watch", "[崩溃模拟器] PyQt5 不可用，跳过")
        return

    btn = QPushButton("test")
    _hook(api, "variable_watch",
          "[崩溃模拟器] QPushButton 已创建，设置非法属性 'text'")
    # text 是 QPushButton 的 property，但尝试设成不兼容的整数类型
    # 这会触发 Qt 内部类型转换警告
    try:
        btn.setProperty("text", 12345)
        _hook(api, "variable_watch",
              f"[崩溃模拟器] setProperty('text', 12345) 完成 — 检查日志中 [Qt WARN]")
    except Exception as e:
        _hook(api, "variable_watch",
              f"[崩溃模拟器] setProperty 异常: {e}")

    # 再试一个不存在于 QPushButton 的属性
    btn.setProperty("__nonexistent_prop_xyz__", "test")
    _hook(api, "variable_watch",
          "[崩溃模拟器] 动态属性已设置 (不会触发 warning)")
    _hook(api, "function_watch",
          "[崩溃模拟器] QObject 非法属性完成 — 检查日志中 [Qt WARN] 标签")


# ═══════════════════════════════════════
#  ★ M4: 底层事件触发器 (6 种)
# ═══════════════════════════════════════

def _crash_native_qt_critical(api):
    """触发 Qt qCritical → 验证 [NATIVE] [qt_critical] 记录。"""
    _hook(api, "function_watch",
          "[崩溃模拟器] qCritical 入口")
    try:
        from PyQt5.QtCore import qCritical
        qCritical("崩溃模拟器测试 qCritical 消息")
    except Exception as e:
        _hook(api, "function_watch",
              f"[崩溃模拟器] qCritical 异常: {e}")


def _crash_native_qt_warning(api):
    """触发 Qt qWarning → 验证 [NATIVE] [qt_warning] 记录。"""
    _hook(api, "function_watch",
          "[崩溃模拟器] qWarning 入口")
    try:
        from PyQt5.QtCore import qWarning
        qWarning("崩溃模拟器测试 qWarning 消息")
    except Exception as e:
        _hook(api, "function_watch",
              f"[崩溃模拟器] qWarning 异常: {e}")


def _crash_native_unraisable(api):
    """触发 __del__ 异常 → 验证 [NATIVE] [unraisable] 记录。"""
    _hook(api, "function_watch",
          "[崩溃模拟器] unraisable 入口")
    import gc as _gc
    try:
        class _DelRaiser:
            def __del__(self):
                _ = 1 // 0  # noqa: F841
        _obj = _DelRaiser()
        del _obj
        _gc.collect()
    except Exception as e:
        _hook(api, "function_watch",
              f"[崩溃模拟器] unraisable 异常: {e}")


def _crash_native_audit_open(api):
    """触发审计事件 open() → 验证 [NATIVE] [audit] 记录。"""
    _hook(api, "function_watch",
          "[崩溃模拟器] audit_open 入口")
    try:
        open("/nonexistent_crash_test_path_12345", "r")
    except FileNotFoundError:
        _hook(api, "function_watch",
              "[崩溃模拟器] audit_open: FileNotFoundError 已捕获")
    except Exception as e:
        _hook(api, "function_watch",
              f"[崩溃模拟器] audit_open 异常: {e}")


def _crash_native_deadlock(api):
    """模拟 2 线程互锁 90s → 验证 [THREAD] [deadlock_suspect] 记录。"""
    _hook(api, "function_watch",
          "[崩溃模拟器] deadlock 入口")
    import threading as _t
    try:
        _lock_a = _t.Lock()
        _lock_b = _t.Lock()

        _lock_a.acquire()
        _lock_b.acquire()

        def _thread_1():
            try:
                _lock_b.acquire(timeout=120)
            except Exception:
                pass

        def _thread_2():
            try:
                _lock_a.acquire(timeout=120)
            except Exception:
                pass

        _t.Thread(target=_thread_1, daemon=True,
                  name="NativeTestDeadlock1").start()
        _t.Thread(target=_thread_2, daemon=True,
                  name="NativeTestDeadlock2").start()
        _hook(api, "function_watch",
              "[崩溃模拟器] deadlock: 2 线程已持有不同锁并互锁")
    except Exception as e:
        _hook(api, "function_watch",
              f"[崩溃模拟器] deadlock 异常: {e}")


def _crash_native_fd_leak(api):
    """模拟打开 2000 个临时文件 → 验证 [RES] [fd_leak] 记录。"""
    _hook(api, "function_watch",
          "[崩溃模拟器] fd_leak 入口")
    _temp_files = []
    try:
        import tempfile
        for i in range(2000):
            try:
                tf = tempfile.TemporaryFile()
                _temp_files.append(tf)
            except OSError:
                break
        _hook(api, "function_watch",
              f"[崩溃模拟器] fd_leak: 已打开 {len(_temp_files)} 个临时文件")
    except Exception as e:
        _hook(api, "function_watch",
              f"[崩溃模拟器] fd_leak 异常: {e}")


# ═══════════════════════════════════════
#  崩溃方式注册表
# ═══════════════════════════════════════

CRASH_METHODS = [
    # Python 层 (6)
    {
        "name": "ZeroDivisionError",
        "icon": "➗",
        "desc": "除零错误 (1/0)",
        "layer": "Python",
        "fn": lambda api: _crash_div_zero(api),
    },
    {
        "name": "IndexError",
        "icon": "📋",
        "desc": "列表越界访问",
        "layer": "Python",
        "fn": lambda api: _crash_index_error(api),
    },
    {
        "name": "KeyError",
        "icon": "🔑",
        "desc": "字典键不存在",
        "layer": "Python",
        "fn": lambda api: _crash_key_error(api),
    },
    {
        "name": "RecursionError",
        "icon": "🔄",
        "desc": "无限递归溢出",
        "layer": "Python",
        "fn": lambda api: _crash_recursion(api),
    },
    {
        "name": "segfault",
        "icon": "💥",
        "desc": "非法内存访问 (ctypes)",
        "layer": "Python",
        "fn": lambda api: _crash_segfault(api),
    },
    {
        "name": "sys.exit(1)",
        "icon": "🚪",
        "desc": "非零退出码 (exit 1)",
        "layer": "Python",
        "fn": lambda api: _crash_exit(api),
    },
    # ★ v2.1.0: Qt C++ 层 (4)
    {
        "name": "QPainter空设备",
        "icon": "🎨",
        "desc": "QPainter.begin(None) → qWarning",
        "layer": "Qt C++",
        "fn": lambda api: _crash_qt_painter_null(api),
    },
    {
        "name": "QWidget双重布局",
        "icon": "📐",
        "desc": "setLayout() 冲突 → qWarning",
        "layer": "Qt C++",
        "fn": lambda api: _crash_qt_double_layout(api),
    },
    {
        "name": "QPixmap OOM",
        "icon": "🖼",
        "desc": "超大/null Pixmap → qWarning",
        "layer": "Qt C++",
        "fn": lambda api: _crash_qt_pixmap_oom(api),
    },
    {
        "name": "QObject非法属性",
        "icon": "📛",
        "desc": "setProperty 类型冲突 → qWarning",
        "layer": "Qt C++",
        "fn": lambda api: _crash_qt_invalid_property(api),
    },
    # ★ M4: 底层事件触发器 (6)
    {
        "name": "qCritical",
        "icon": "🔴",
        "desc": "触发 Qt qCritical → [NATIVE] [qt_critical]",
        "layer": "Native",
        "fn": lambda api: _crash_native_qt_critical(api),
    },
    {
        "name": "qWarning",
        "icon": "🟡",
        "desc": "触发 Qt qWarning → [NATIVE] [qt_warning]",
        "layer": "Native",
        "fn": lambda api: _crash_native_qt_warning(api),
    },
    {
        "name": "unraisable",
        "icon": "👻",
        "desc": "触发 __del__ 异常 → [NATIVE] [unraisable]",
        "layer": "Native",
        "fn": lambda api: _crash_native_unraisable(api),
    },
    {
        "name": "audit_open",
        "icon": "🔓",
        "desc": "触发审计事件 open() → [NATIVE] [audit]",
        "layer": "Native",
        "fn": lambda api: _crash_native_audit_open(api),
    },
    {
        "name": "deadlock",
        "icon": "🔗",
        "desc": "模拟 2 线程互锁 90s → [THREAD] [deadlock_suspect]",
        "layer": "Native",
        "fn": lambda api: _crash_native_deadlock(api),
    },
    {
        "name": "fd_leak",
        "icon": "📂",
        "desc": "模拟打开 2000 个临时文件 → [RES] [fd_leak]",
        "layer": "Native",
        "fn": lambda api: _crash_native_fd_leak(api),
    },
]


# ═══════════════════════════════════════
#  崩溃触发
# ═══════════════════════════════════════

def trigger_crash():
    """随机选择一种崩溃方式并触发。"""
    api = get_api()
    if not api:
        return

    method = random.choice(CRASH_METHODS)

    # ── 监视钩子：记录崩溃触发信息 ──
    _hook(api, "function_watch",
          "[崩溃模拟器] trigger_crash() 入口")
    _hook(api, "variable_watch",
          f"[崩溃模拟器] 用户点击崩溃测试按钮，随机种子={random.getstate()[0]}")

    _hook(api, "plugin_watch",
          f"[崩溃模拟器] 随机选中 [{method['layer']}] "
          f"{method['icon']} {method['name']} — {method['desc']}")

    # 记录方法详情
    _hook(api, "variable_watch",
          f"[崩溃模拟器] 选中方式详情: name={method['name']}, "
          f"layer={method['layer']}, icon={method['icon']}")

    api.update_status(
        f"💣 正在触发崩溃 [{method['layer']}]: "
        f"{method['name']} — 奔溃弹窗应自动弹出..."
    )

    # 触发前快照
    _hook(api, "api_watch",
          f"[崩溃模拟器] 即将执行: {method['name']} (层级={method['layer']})")

    # ── 强制执行日志刷新 ──
    try:
        time.sleep(0.3)
    except Exception:
        pass

    # ★ v2.1.0: Qt C++ 层的测试不会真正崩溃进程，
    # ★ M4: Native 层同样为非进程退出类方法
    is_safe_layer = method.get("layer") in ("Qt C++", "Native")

    if is_safe_layer:
        # Qt/Native 层测试：不退出进程，在日志中验证标签
        _hook(api, "function_watch",
              f"[崩溃模拟器] 执行 Qt 层测试: {method['name']}")
        method["fn"](api)
        _hook(api, "function_watch",
              f"[崩溃模拟器] Qt 层测试完成: {method['name']}")
        api.update_status(
            f"✅ Qt 层测试完成 [{method['name']}] — "
            f"请在调试台查看 [Qt WARN] 日志条目"
        )
        # 弹窗提示用户检查日志
        layer_name = method.get("layer", "")
        api.show_notification(
            f"{layer_name} 层底层事件测试",
            f"已执行 {layer_name} 层错误模拟:\n{method['desc']}\n\n"
            f"请在调试台中搜索 '[NATIVE]'、'[THREAD]'\n"
            f"或 '[RES]' 验证底层事件系统是否正确记录。\n"
            f"此类测试不会导致程序崩溃。"
        )
    else:
        # Python 层测试：会真正导致进程退出
        _hook(api, "function_watch",
              f"[崩溃模拟器] 执行进程退出类崩溃: {method['name']}")
        method["fn"](api)


def trigger_crash_by_index(idx: int):
    """按编号触发指定的崩溃方式。

    Args:
        idx: 0-based 索引
    """
    api = get_api()
    if not api:
        return

    if idx < 0 or idx >= len(CRASH_METHODS):
        return

    method = CRASH_METHODS[idx]
    _hook(api, "variable_watch",
          f"[崩溃模拟器] 按编号触发: idx={idx}, name={method['name']}")

    is_safe_layer = method.get("layer") in ("Qt C++", "Native")

    if is_safe_layer:
        method["fn"](api)
        tag_hint = method.get("layer", "")
        api.update_status(
            f"✅ {tag_hint} 层测试完成 [{method['name']}] — 请在调试台查看日志"
        )
    else:
        import time as _t
        _t.sleep(0.3)
        method["fn"](api)


# ═══════════════════════════════════════
#  命令注册
# ═══════════════════════════════════════

def _cmd_crash_list(args: str) -> str:
    """控制台命令：列出所有崩溃方式"""
    lines = ["💣 可用崩溃方式 (共 {} 种):".format(len(CRASH_METHODS))]
    lines.append("─" * 50)
    py_count = sum(1 for m in CRASH_METHODS if m.get("layer") == "Python")
    qt_count = sum(1 for m in CRASH_METHODS if m.get("layer") == "Qt C++")
    native_count = sum(1 for m in CRASH_METHODS if m.get("layer") == "Native")
    lines.append(f"  Python 层: {py_count} 种 (会导致进程退出)")
    lines.append(f"  Qt C++ 层: {qt_count} 种 (仅触发 Qt 内部警告，不退出)")
    lines.append(f"  Native 层: {native_count} 种 (底层事件验证，不退出)")
    lines.append("─" * 50)
    for i, m in enumerate(CRASH_METHODS, 1):
        tag = "💀" if m.get("layer") == "Python" else "⚠"
        lines.append(f"  {i:2d}. {m['icon']} {tag} {m['name']:16s} — {m['desc']}")
    return "\n".join(lines)


def _cmd_crash_run(args: str) -> str | None:
    """控制台命令：执行指定编号的崩溃方式"""
    try:
        idx = int(args.strip()) - 1
        if 0 <= idx < len(CRASH_METHODS):
            api = get_api()
            method = CRASH_METHODS[idx]
            _hook(api, "plugin_watch",
                  f"[崩溃模拟器] 控制台命令触发 [{method.get('layer')}]: {method['name']}")
            if api:
                api.update_status(
                    f"💣 控制台触发崩溃 [{method.get('layer')}]: {method['name']}"
                )
            if method.get("layer") == "Qt C++":
                trigger_crash_by_index(idx)
            else:
                import time as _t
                _t.sleep(0.3)
                method["fn"](api)
        else:
            return f"无效编号: {args}，有效范围 1-{len(CRASH_METHODS)}"
    except ValueError:
        return f"请输入数字编号 (1-{len(CRASH_METHODS)})"
    return None


# ════════════════════════════════════════════════════════
#  生命周期钩子
# ════════════════════════════════════════════════════════

def on_enable():
    """插件启用时调用"""
    api = get_api()

    # ── 监视钩子：插件加载 ──
    _hook(api, "plugin_watch",
          "[崩溃模拟器] 插件已加载 v2.1.0 — 10 种崩溃方式已就绪")
    _hook(api, "variable_watch",
          f"[崩溃模拟器] Python 层 6 种 + Qt C++ 层 4 种")
    _hook(api, "function_watch",
          "[崩溃模拟器] on_enable() 入口 — 注册导航按钮+控制台命令")

    # 注册右侧导航栏按钮
    api.register_nav_button(
        side="right",
        emoji="💣",
        label="崩溃测试",
        tooltip="随机触发崩溃方式 (Python/Qt C++)\n"
                "Python 层会导致进程退出;\n"
                "Qt C++ 层仅触发警告,可用来验证起居注的 Qt handler",
        callback=trigger_crash,
    )

    # 注册控制台命令
    api.register_console_command(
        cmd_name="crash:list",
        handler_fn=_cmd_crash_list,
        args_desc="",
        description="列出所有可用的崩溃模拟方式 (含 Qt 层)",
        category="插件",
    )
    api.register_console_command(
        cmd_name="crash:run",
        handler_fn=_cmd_crash_run,
        args_desc="<编号>",
        description="执行指定编号的崩溃方式 (1-{})".format(len(CRASH_METHODS)),
        category="插件",
    )

    _hook(api, "api_watch",
          "[崩溃模拟器] on_enable() 完成 — 导航按钮+2条控制台命令已注册")
    api.update_status(
        "💣 崩溃模拟器 v2.1.0 已就绪 — "
        "10 种崩溃方式 (6 Python + 4 Qt C++)"
    )


def on_disable():
    """插件禁用时调用"""
    api = get_api()

    _hook(api, "plugin_watch",
          "[崩溃模拟器] 插件已卸载")
    _hook(api, "function_watch",
          "[崩溃模拟器] on_disable() 入口")

    api.update_status("崩溃模拟器已停止")


# ════════════════════════════════════════════════════════
#  独立测试入口
# ════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 55)
    print("  💣 崩溃模拟器 v2.1.0")
    print("  请在 StarDebate 中导入此插件使用")
    print("=" * 55)
    print()
    print("可用崩溃方式 (共 {} 种):".format(len(CRASH_METHODS)))
    print()
    py_methods = [m for m in CRASH_METHODS if m.get("layer") == "Python"]
    qt_methods = [m for m in CRASH_METHODS if m.get("layer") == "Qt C++"]
    print("  Python 层 ({} 种，会导致进程退出):".format(len(py_methods)))
    for i, m in enumerate(py_methods, 1):
        print(f"    {i}. {m['icon']} {m['name']:20s} — {m['desc']}")
    print()
    print("  Qt C++ 层 ({} 种，仅触发警告，不退出):".format(len(qt_methods)))
    for i, m in enumerate(qt_methods, 1):
        print(f"    {i+len(py_methods)}. {m['icon']} {m['name']:20s} — {m['desc']}")
    print()
    print("导入步骤：")
    print("  1. 打开 StarDebate → 🔌 插件 → 📥 导入插件")
    print("  2. 选择 crash_simulator 文件夹")
    print("  3. 点击右侧导航栏 💣 按钮测试")
