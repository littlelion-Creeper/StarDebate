"""统一 API 请求辅助模块 — 带调试监视钩子

提供 monitored_api_post() 函数，封装 requests.post() 调用，
自动记录请求/响应信息到 DebugMonitorManager。

所有 AI Worker 应使用此函数替代直接的 requests.post()。

使用方式:
    from workers.common.api_helper import monitored_api_post
    resp, elapsed_ms = monitored_api_post(
        api_config, payload, timeout=60,
        feature_name="ai_analysis"
    )
"""

import time
import requests
from typing import Optional


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
    """带调试监视的 API POST 请求。

    自动从 api_config 提取 api_url 和 api_key，构建请求头。
    记录 API 请求/响应/错误到 DebugMonitorManager（如已激活）。

    Args:
        api_config: API 配置字典，含 api_url / api_key
        payload: 请求 JSON body
        timeout: 超时秒数
        feature_name: 调用来源标识（如 "ai_analysis", "speech_writer"）
        endpoint: 端点路径（为空时从 api_url 提取）

    Returns:
        (response_obj, elapsed_ms): requests.Response 对象和耗时（毫秒）
        异常时可能返回 (None, elapsed_ms)
    """
    api_url = api_config.get("api_url", "https://api.deepseek.com/v1/chat/completions")

    if not endpoint:
        # 从 api_url 提取路径部分
        endpoint = "/" + api_url.split("/", 3)[-1] if "://" in api_url else api_url

    model = payload.get("model", "unknown")
    max_tokens = payload.get("max_tokens", 0)
    temperature = payload.get("temperature", 0)

    mgr = _get_monitor_mgr()
    t0 = time.perf_counter()

    # 构建请求摘要
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
