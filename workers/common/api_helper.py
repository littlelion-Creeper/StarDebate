"""统一 API 请求辅助模块 — 带调试监视钩子

提供 monitored_api_post() 函数，封装 requests.post() 调用，
自动记录请求/响应信息到 DebugMonitorManager。
v2.0: 支持 Web AI 网页版 Provider 路由（provider_type="web"）。

所有 AI Worker 应使用此函数替代直接的 requests.post()。

使用方式:
    from workers.common.api_helper import monitored_api_post
    resp, elapsed_ms = monitored_api_post(
        api_config, payload, timeout=60,
        feature_name="ai_analysis"
    )
"""

import json
import logging
import time
import requests
from typing import Optional

_logger = logging.getLogger("StarDebate.api_helper")


class _WebResponse:
    """伪 Response 对象，兼容 requests.Response 的 .json() 接口

    Web AI Provider 返回的内容包装为此对象，
    使现有 Worker 的 resp.json()["choices"][0]["message"]["content"] 调用无需修改。
    """

    def __init__(self, content: str, status_code: int = 200):
        self.status_code = status_code
        self._content = content
        self._is_web = True

    def json(self):
        if self.status_code >= 400:
            raise ValueError(self._content)
        return {
            "choices": [{
                "message": {"content": self._content, "role": "assistant"},
                "finish_reason": "stop",
            }],
            "model": "web-deepseek",
            "provider": "web",
        }

    @property
    def text(self):
        return self._content


class _WebErrorResponse(_WebResponse):
    """Web AI 错误响应"""

    def __init__(self, error_text: str):
        super().__init__(error_text, status_code=500)


# ── Provider Type 常量 ──
PROVIDER_AUTO = "auto"       # 自动检测
PROVIDER_API = "api"         # API 模式
PROVIDER_WEB = "web"         # 网页版


def _resolve_provider_type(api_config: dict) -> str:
    """解析实际使用的 Provider 类型

    auto: api_key 存在 → API，否则 → Web
    api:  强制 API；若未配置 API Key → 自动回退 Web
    web:  强制 Web
    """
    ptype = api_config.get("provider_type", PROVIDER_AUTO)
    api_key = api_config.get("api_key", "").strip()

    if ptype == PROVIDER_API:
        if api_key:
            return PROVIDER_API
        _logger.warning("provider_type=api 但未配置 API Key，自动回退到 Web 模式")
        return PROVIDER_WEB

    if ptype == PROVIDER_WEB:
        return PROVIDER_WEB

    # auto 模式
    return PROVIDER_API if api_key else PROVIDER_WEB


def _get_monitor_mgr():
    """惰性获取 DebugMonitorManager 单例，避免循环导入。"""
    try:
        from workers.debug_console.debug_monitor_manager import DebugMonitorManager
        return DebugMonitorManager.instance()
    except Exception:
        return None


def monitored_api_post(
    api_config: dict,
    payload: dict,
    timeout: int = 60,
    feature_name: str = "unknown",
    endpoint: str = "",
) -> tuple:
    """带调试监视的统一 AI 调用入口。

    支持两种模式：
    1. API 模式（provider_type="api" 或 auto+有key）：HTTP POST 到 API
    2. Web 模式（provider_type="web" 或 auto+无key）：Playwright 网页模拟

    Args:
        api_config: API 配置字典，含 api_url / api_key / provider_type / provider_id
        payload: 请求 JSON body（OpenAI Chat Completions 格式）
        timeout: 超时秒数
        feature_name: 调用来源标识
        endpoint: 端点路径

    Returns:
        (response_obj, elapsed_ms): requests.Response 或 _WebResponse
    """
    provider_type = _resolve_provider_type(api_config)

    # ── Web AI 路由 ──
    if provider_type == PROVIDER_WEB:
        return _web_ai_post(api_config, payload, timeout, feature_name, endpoint)

    # ── API 路由（原有逻辑） ──
    return _api_post(api_config, payload, timeout, feature_name, endpoint)


def _web_ai_post(
    api_config: dict,
    payload: dict,
    timeout: int,
    feature_name: str,
    endpoint: str,
) -> tuple:
    """Web AI 网页版调用"""
    t0 = time.perf_counter()
    mgr = _get_monitor_mgr()
    req_summary = f"WebAI | 功能:{feature_name}"

    provider_id = api_config.get("provider_id", "deepseek")

    try:
        from workers.web_ai.web_ai_manager import get_web_ai_manager
        wm = get_web_ai_manager()

        success, error, content = wm.send_chat(payload, provider_id)
        elapsed = (time.perf_counter() - t0) * 1000

        if success:
            if mgr:
                mgr.log_api_result(
                    endpoint=f"webai:{provider_id}",
                    method="POST",
                    status_code=200,
                    duration_ms=elapsed,
                    request_summary=req_summary,
                    response_summary=f"响应长度:{len(content)}字符",
                )
            return _WebResponse(content), elapsed
        else:
            if mgr:
                mgr.log_api_result(
                    endpoint=f"webai:{provider_id}",
                    method="POST",
                    status_code=500,
                    duration_ms=elapsed,
                    request_summary=req_summary,
                    error=error,
                )
            return _WebErrorResponse(error), elapsed

    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        if mgr:
            mgr.log_api_result(
                endpoint=f"webai:{provider_id}",
                method="POST",
                status_code=0,
                duration_ms=elapsed,
                request_summary=req_summary,
                error=str(e),
            )
        return _WebErrorResponse(str(e)), elapsed


def _api_post(
    api_config: dict,
    payload: dict,
    timeout: int,
    feature_name: str,
    endpoint: str,
) -> tuple:
    """原有的 API POST 逻辑"""
    api_url = api_config.get("api_url", "https://api.deepseek.com/v1/chat/completions")

    if not endpoint:
        endpoint = "/" + api_url.split("/", 3)[-1] if "://" in api_url else api_url

    model = payload.get("model", "unknown")
    max_tokens = payload.get("max_tokens", 0)
    temperature = payload.get("temperature", 0)

    mgr = _get_monitor_mgr()
    t0 = time.perf_counter()

    req_summary = f"模型:{model} | Tokens:{max_tokens} | 温度:{temperature}"

    try:
        resp = requests.post(
            api_url,
            headers={
                "Authorization": f"Bearer {api_config.get('api_key', '')}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        elapsed = (time.perf_counter() - t0) * 1000

        if mgr:
            status_code = resp.status_code
            if 200 <= status_code < 300:
                try:
                    data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    resp_summary = f"响应长度:{len(content)}字符" if content else ""
                except Exception:
                    resp_summary = ""
                mgr.log_api_result(
                    endpoint=endpoint,
                    method="POST",
                    status_code=status_code,
                    duration_ms=elapsed,
                    request_summary=req_summary,
                    response_summary=resp_summary,
                )
            else:
                err_text = ""
                try:
                    err_text = str(resp.json())[:300]
                except Exception:
                    err_text = resp.text[:300]
                mgr.log_api_result(
                    endpoint=endpoint,
                    method="POST",
                    status_code=status_code,
                    duration_ms=elapsed,
                    request_summary=req_summary,
                    error=err_text,
                )

        return resp, elapsed

    except requests.exceptions.Timeout:
        elapsed = (time.perf_counter() - t0) * 1000
        if mgr:
            mgr.log_api_result(
                endpoint=endpoint, method="POST", status_code=0,
                duration_ms=elapsed, request_summary=req_summary,
                error="请求超时",
            )
        raise

    except requests.exceptions.ConnectionError:
        elapsed = (time.perf_counter() - t0) * 1000
        if mgr:
            mgr.log_api_result(
                endpoint=endpoint, method="POST", status_code=0,
                duration_ms=elapsed, request_summary=req_summary,
                error="无法连接 API 服务器",
            )
        raise

    except Exception:
        elapsed = (time.perf_counter() - t0) * 1000
        if mgr:
            mgr.log_api_result(
                endpoint=endpoint, method="POST", status_code=0,
                duration_ms=elapsed, request_summary=req_summary,
                error="请求异常",
            )
        raise
