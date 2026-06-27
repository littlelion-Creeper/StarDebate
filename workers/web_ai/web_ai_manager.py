"""WebAIManager — Web AI 全局管理器（单例）

职责：
1. 管理 Provider 注册与选择
2. Session 登录态生命周期
3. 全局串行队列调度
4. 对 monitored_api_post 暴露统一 send_chat() 入口
"""

import json
import logging
import os
import threading
from typing import Optional, Dict

from workers.web_ai.providers.base_provider import (
    BaseWebAIProvider,
    ProviderError,
    SelectorChangedError,
    SessionExpiredError,
    TimeoutError,
)
from workers.web_ai.providers.deepseek_provider import DeepSeekProvider
from workers.web_ai.web_ai_queue import get_web_ai_queue
from workers.web_ai.chromium_checker import get_chromium_checker

_logger = logging.getLogger("StarDebate.web_ai.manager")

# ── 配置路径 ──
DEFAULT_CONFIG_PATH = "config/web_ai_config.json"
DEFAULT_STATE_DIR = "config/web_ai_sessions/"


class WebAIManager:
    """Web AI 全局管理器（单例）"""

    _instance: Optional["WebAIManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._providers: Dict[str, BaseWebAIProvider] = {}
        self._config: dict = {}
        self._config_path = DEFAULT_CONFIG_PATH

        # 注册内置 providers
        self._register(DeepSeekProvider())

        self._load_config()

    # ── Provider 注册 ──

    def _register(self, provider: BaseWebAIProvider):
        self._providers[provider.provider_id] = provider
        _logger.info(f"已注册 WebAI Provider: {provider.provider_id} ({provider.provider_name})")

    def get_provider(self, provider_id: str = "deepseek") -> Optional[BaseWebAIProvider]:
        return self._providers.get(provider_id)

    def get_current_provider(self) -> Optional[BaseWebAIProvider]:
        pid = self._config.get("provider_id", "deepseek")
        return self.get_provider(pid)

    def list_providers(self) -> list:
        return [p.get_provider_info() for p in self._providers.values()]

    # ── 配置 ──

    def _load_config(self):
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
            else:
                self._config = self._get_default_config()
                self._save_config()
        except Exception as e:
            _logger.warning(f"加载 Web AI 配置失败: {e}，使用默认值")
            self._config = self._get_default_config()

    def _save_config(self):
        try:
            os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            _logger.error(f"保存 Web AI 配置失败: {e}")

    @staticmethod
    def _get_default_config() -> dict:
        return {
            "provider_id": "deepseek",
            "webai_timeout": 60,
            "webai_max_retries": 2,
            "state_dir": DEFAULT_STATE_DIR,
        }

    def get_config(self, key: str, default=None):
        return self._config.get(key, default)

    def set_config(self, key: str, value):
        self._config[key] = value
        self._save_config()

    # ── Session 管理 ──

    def get_state_path(self, provider_id: str = "deepseek") -> str:
        state_dir = self._config.get("state_dir", DEFAULT_STATE_DIR)
        os.makedirs(state_dir, exist_ok=True)
        return os.path.join(state_dir, f"{provider_id}_state.json")

    def is_authenticated(self, provider_id: str = "deepseek") -> bool:
        provider = self.get_provider(provider_id)
        if not provider:
            return False
        return provider.is_authenticated(self.get_state_path(provider_id))

    def login(self, provider_id: str = "deepseek") -> bool:
        """弹出浏览器手动登录"""
        provider = self.get_provider(provider_id)
        if not provider:
            return False
        return provider.login(self.get_state_path(provider_id))

    def logout(self, provider_id: str = "deepseek"):
        provider = self.get_provider(provider_id)
        if provider:
            provider.logout(self.get_state_path(provider_id))

    # ── 自动登录（临时线程，不阻塞主线程） ──

    def auto_login(self, provider_id: str = "deepseek") -> (bool, str):
        """在临时线程中执行自动登录（headless 检测 → manual 降级）

        调用方（worker 线程）阻塞等待结果，主线程保持空闲。

        Returns:
            (success, error_message)
        """
        provider = self.get_provider(provider_id)
        if not provider:
            return False, f"未知的 WebAI Provider: {provider_id}"

        state_path = self.get_state_path(provider_id)
        result_box: dict = {}
        done_event = threading.Event()

        def _run():
            try:
                ok = provider.try_auto_login(state_path)
                result_box["success"] = ok
                if not ok:
                    result_box["error"] = "登录未完成或已取消"
            except Exception as e:
                result_box["error"] = str(e)
            finally:
                done_event.set()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        done_event.wait(timeout=600)  # 10 分钟超时（手动登录可能较慢）

        if "error" in result_box:
            return False, result_box["error"]
        return result_box.get("success", False), ""

    # ── 对话入口（由 api_helper 调用） ──

    def send_chat(self, payload: dict, provider_id: str = "deepseek") -> (bool, str, str):
        """通过 Web Provider 发送对话并获取回复（在临时线程中运行 Playwright）

        Playwright sync API（greenlet）只能在创建它的线程中切换。
        本方法在临时线程中执行 provider.chat()，调用线程（worker QThread）阻塞等待。
        主线程不被阻塞，UI 保持响应。

        Args:
            payload: OpenAI Chat Completions 格式
            provider_id: Provider ID

        Returns:
            (success, error_text, result_text)
        """
        provider = self.get_provider(provider_id)
        if not provider:
            return False, f"未知的 WebAI Provider: {provider_id}", ""

        state_path = self.get_state_path(provider_id)
        if not os.path.exists(state_path):
            return False, "SessionExpired: 请先在设置中登录 DeepSeek 网页版", ""

        timeout = self._config.get("webai_timeout", 60)
        max_retries = self._config.get("webai_max_retries", 2)

        # ── 串行队列 ──
        queue = get_web_ai_queue()
        queue.acquire()

        try:
            result_box: dict = {}
            done_event = threading.Event()

            def _run():
                """在临时线程中执行 Playwright 调用"""
                try:
                    attempt = 0
                    last_error = ""
                    while attempt <= max_retries:
                        try:
                            if attempt > 0:
                                _logger.info(f"Web AI 重试 {attempt}/{max_retries}")
                            content = provider.chat(state_path, payload, timeout)
                            result_box["success"] = True
                            result_box["content"] = content
                            return
                        except SessionExpiredError as e:
                            result_box["error"] = f"SessionExpired: {e}"
                            return
                        except TimeoutError as e:
                            last_error = str(e)
                            attempt += 1
                        except SelectorChangedError as e:
                            result_box["error"] = f"SelectorChanged: {e}"
                            return
                        except ProviderError as e:
                            last_error = str(e)
                            attempt += 1
                    result_box["error"] = (
                        f"Web AI 调用失败（已重试{max_retries}次）: {last_error}"
                    )
                except Exception as e:
                    result_box["error"] = str(e)
                finally:
                    done_event.set()

            t = threading.Thread(target=_run, daemon=True)
            t.start()

            # 阻塞调用线程（worker QThread），主线程保持空闲
            total_wait = timeout * (max_retries + 1) + 60
            if not done_event.wait(timeout=total_wait):
                return False, f"Web AI 调用超时（{total_wait}s）", ""

            if "error" in result_box:
                return False, result_box["error"], ""
            return True, "", result_box.get("content", "")

        finally:
            queue.release()

    # ── Chromium 状态 ──

    def get_chromium_status(self) -> dict:
        """获取 Chromium 安装状态"""
        checker = get_chromium_checker()
        return {
            "playwright_installed": checker.is_playwright_installed(),
            "chromium_installed": checker.is_chromium_installed(),
            "chromium_version": checker.get_chromium_version(),
        }

    def install_chromium(self, on_progress=None) -> bool:
        """安装 Chromium（含 Playwright）"""
        checker = get_chromium_checker()
        if not checker.is_playwright_installed():
            if not checker.install_playwright(on_progress):
                return False
        return checker.install_chromium(on_progress)


# 全局便捷入口
def get_web_ai_manager() -> WebAIManager:
    return WebAIManager()
