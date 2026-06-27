"""第三方库错误包装器 — native_lib_wrapper (M4 v1.3.0)

覆盖 requests/ctypes/json 常见底层错误记录。

包装方式:
  - requests: 包装 requests.Session.request() 捕获 SSLError/ConnectionError
  - ctypes: 包装 ctypes.WinDLL/CDLL 加载调用
  - json: 包装 json.loads 捕获 DecodeError 带 line/col

不 monkey-patch 标准库，使用包装器模式。
所有包装器可通过 native_log_config.json 的 hooks 开关控制。
"""

import sys
import json as _json


def install_lib_wrappers(manager):
    """安装第三方库包装器。

    Args:
        manager: NativeEventManager 实例

    Returns:
        dict: 保存的原始引用（当前为空，暂不需 uninstall）
    """
    saved = {}

    # ── requests 包装 ────────────────────────────────────
    _install_requests_wrapper(manager, saved)

    # ── ctypes 包装 ──────────────────────────────────────
    _install_ctypes_wrapper(manager, saved)

    # ── json 包装 ────────────────────────────────────────
    _install_json_wrapper(manager, saved)

    return saved


def uninstall_lib_wrappers(saved: dict):
    """卸载第三方库包装器，恢复原始引用。"""
    # requests
    if "orig_requests_request" in saved:
        try:
            import requests as _r
            _r.Session.request = saved["orig_requests_request"]
        except Exception:
            pass

    # ctypes
    if "orig_ctypes_win_dll_init" in saved:
        try:
            import ctypes as _c
            _c.WinDLL.__init__ = saved["orig_ctypes_win_dll_init"]
        except Exception:
            pass
    if "orig_ctypes_cdll_init" in saved:
        try:
            import ctypes as _c
            _c.CDLL.__init__ = saved["orig_ctypes_cdll_init"]
        except Exception:
            pass

    # json
    if "orig_json_loads" in saved:
        try:
            _json.loads = saved["orig_json_loads"]
        except Exception:
            pass


# ════════════════════════════════════════════════════════
#  requests 包装
# ════════════════════════════════════════════════════════

def _install_requests_wrapper(manager, saved: dict):
    """包装 requests.Session.request 捕获网络/SSL 错误。"""
    try:
        import requests
    except ImportError:
        return

    try:
        saved["orig_requests_request"] = requests.Session.request

        def _wrapped_request(self, method, url, **kwargs):
            try:
                return saved["orig_requests_request"](self, method, url, **kwargs)
            except requests.exceptions.SSLError as e:
                _write_lib_error(manager, "requests", "SSLError",
                                 f"SSL 错误: {e}", url=str(url)[:200])
                raise
            except requests.exceptions.ConnectionError as e:
                _write_lib_error(manager, "requests", "ConnectionError",
                                 f"连接失败: {e}", url=str(url)[:200])
                raise
            except requests.exceptions.Timeout as e:
                _write_lib_error(manager, "requests", "Timeout",
                                 f"请求超时: {e}", url=str(url)[:200])
                raise
            except requests.exceptions.RequestException as e:
                _write_lib_error(manager, "requests", "RequestException",
                                 f"请求异常: {e}", url=str(url)[:200])
                raise

        requests.Session.request = _wrapped_request
    except Exception:
        pass


# ════════════════════════════════════════════════════════
#  ctypes 包装
# ════════════════════════════════════════════════════════

def _install_ctypes_wrapper(manager, saved: dict):
    """包装 ctypes.WinDLL/CDLL 加载操作。"""
    try:
        import ctypes
    except ImportError:
        return

    try:
        saved["orig_ctypes_win_dll_init"] = ctypes.WinDLL.__init__

        def _wrapped_win_dll_init(self, name, *args, **kwargs):
            try:
                return saved["orig_ctypes_win_dll_init"](
                    self, name, *args, **kwargs
                )
            except OSError as e:
                _write_lib_error(manager, "ctypes", "WinDLLLoadError",
                                 f"WinDLL 加载失败: {e}",
                                 detail=f"name={name}, args={args}")
                raise

        ctypes.WinDLL.__init__ = _wrapped_win_dll_init
    except Exception:
        pass

    try:
        saved["orig_ctypes_cdll_init"] = ctypes.CDLL.__init__

        def _wrapped_cdll_init(self, name, *args, **kwargs):
            try:
                return saved["orig_ctypes_cdll_init"](
                    self, name, *args, **kwargs
                )
            except OSError as e:
                _write_lib_error(manager, "ctypes", "CDLLLoadError",
                                 f"CDLL 加载失败: {e}",
                                 detail=f"name={name}, args={args}")
                raise

        ctypes.CDLL.__init__ = _wrapped_cdll_init
    except Exception:
        pass


# ════════════════════════════════════════════════════════
#  json 包装
# ════════════════════════════════════════════════════════

def _install_json_wrapper(manager, saved: dict):
    """包装 json.loads 捕获 DecodeError 带行列号。"""
    try:
        saved["orig_json_loads"] = _json.loads

        def _wrapped_json_loads(s, *args, **kwargs):
            try:
                return saved["orig_json_loads"](s, *args, **kwargs)
            except _json.JSONDecodeError as e:
                # 提取行列号 + 上下文片段
                line = getattr(e, 'lineno', 0)
                col = getattr(e, 'colno', 0)
                pos = getattr(e, 'pos', 0)
                snippet = ""
                if s and pos > 0:
                    start = max(0, pos - 20)
                    end = min(len(s), pos + 20)
                    snippet = s[start:end]

                _write_lib_error(
                    manager, "json", "JSONDecodeError",
                    f"JSON 解析失败: {e}",
                    detail=f"line={line}, col={col}, pos={pos}, "
                           f"snippet=[{snippet}]",
                )
                raise

        _json.loads = _wrapped_json_loads
    except Exception:
        pass


# ════════════════════════════════════════════════════════
#  错误写入辅助
# ════════════════════════════════════════════════════════

def _write_lib_error(manager, lib_name: str, error_type: str,
                     message: str, url: str = "", detail: str = ""):
    """统一的第三方库错误写入。"""
    detail_json = _json.dumps({
        "library": lib_name,
        "error_type": error_type,
        "detail": detail[:500],
        "url": url[:200],
    }, ensure_ascii=False)[:2000]

    manager.write_event(
        "native_events",
        level="ext_error",
        source=f"ext.{lib_name}",
        message=f"[{lib_name}] {error_type}: {message[:300]}",
        location=url[:200] if url else lib_name,
        detail_json=detail_json,
    )
