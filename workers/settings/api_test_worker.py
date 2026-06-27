"""API 连接测试异步线程"""

import json
import time
import urllib.request
import urllib.error
from PyQt5.QtCore import QThread, pyqtSignal


class APITestWorker(QThread):
    """异步测试 API 连接"""

    test_finished = pyqtSignal(bool, str)

    def __init__(self, config: dict):
        super().__init__()
        self._config = config

    def run(self):
        api_url = self._config.get("api_url", "")
        t0 = time.perf_counter()
        try:
            headers = {
                "Authorization": f"Bearer {self._config['api_key']}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self._config.get("model", "deepseek-v4-flash"),
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 10,
                "temperature": 0,
            }
            req = urllib.request.Request(
                api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=10)
            elapsed = (time.perf_counter() - t0) * 1000
            data = json.loads(resp.read().decode("utf-8"))
            model_used = data.get("model", "?")
            result = f"连接成功！\n响应模型: {model_used}"
            self._log_api_monitor(api_url, 200, elapsed, result)
            self.test_finished.emit(True, result)
        except urllib.error.HTTPError as e:
            elapsed = (time.perf_counter() - t0) * 1000
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            err_msg = f"HTTP {e.code}: {e.reason}\n{body}"
            self._log_api_monitor(api_url, e.code, elapsed, error=err_msg)
            self.test_finished.emit(False, err_msg)
        except urllib.error.URLError as e:
            elapsed = (time.perf_counter() - t0) * 1000
            err_msg = f"网络错误: {str(e.reason)}"
            self._log_api_monitor(api_url, 0, elapsed, error=err_msg)
            self.test_finished.emit(False, err_msg)
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            err_msg = f"连接失败: {str(e)}"
            self._log_api_monitor(api_url, 0, elapsed, error=err_msg)
            self.test_finished.emit(False, err_msg)

    @staticmethod
    def _log_api_monitor(endpoint: str, status_code: int, elapsed: float,
                         summary: str = "", error: str = ""):
        """记录 API 测试结果到监视管理器。"""
        try:
            from workers.debug_console.debug_monitor_manager import DebugMonitorManager
            mgr = DebugMonitorManager.instance()
            if mgr.is_monitor_enabled("api_watch"):
                mgr.log_api_result(
                    endpoint=endpoint, method="POST",
                    status_code=status_code, duration_ms=elapsed,
                    response_summary=summary, error=error,
                )
        except Exception:
            pass
