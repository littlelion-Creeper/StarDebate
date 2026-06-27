"""BaseWebAIProvider — Web AI Provider 抽象基类"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

_logger = logging.getLogger("StarDebate.web_ai.base_provider")


class ProviderError(Exception):
    """Provider 通用异常"""


class SessionExpiredError(ProviderError):
    """Session 过期，需要重新登录"""


class TimeoutError(ProviderError):
    """请求超时"""


class SelectorChangedError(ProviderError):
    """网页结构变化，选择器失效"""


# ── OpenAI Chat 格式 Payload 类型 ──
OpenAIPayload = dict  # {model, messages: [{role, content}], max_tokens, temperature, stream}


class BaseWebAIProvider(ABC):
    """Web AI Provider 抽象基类

    每个公开 AI 聊天网站都是一个独立的 provider 实现。
    Provider 负责：Payload → 网页操作 翻译、回复提取、异常处理。

    Lifecycle:
        1. __init__()
        2. login() — 首次手动登录，持久化 session
        3. is_authenticated() — 检查登录态
        4. chat(payload) → str — 发送对话，返回回复文本
        5. logout() — 清除登录态
    """

    provider_id: str = "base"
    provider_name: str = "Base"

    def __init__(self):
        self._state_path: Optional[str] = None

    # ── 身份验证 ──

    @abstractmethod
    def login(self, state_path: str) -> bool:
        """首次手动登录，弹出可见浏览器窗口让用户登录。

        Args:
            state_path: 持久化 storage_state 的文件路径 (.json)

        Returns:
            True 登录成功
        """

    @abstractmethod
    def is_authenticated(self, state_path: str) -> bool:
        """检查 session 是否有效。

        Args:
            state_path: storage_state 文件路径

        Returns:
            True session 有效
        """

    @abstractmethod
    def logout(self, state_path: str):
        """清除登录态（删除 storage_state 文件）"""

    # ── 对话调用 ──

    @abstractmethod
    def chat(self, state_path: str, payload: OpenAIPayload, timeout: int = 60) -> str:
        """发送对话并获取回复。

        Args:
            state_path: storage_state 文件路径
            payload: OpenAI Chat Completions 格式
            timeout: 单次超时秒数

        Returns:
            AI 回复文本

        Raises:
            SessionExpiredError: session 过期
            TimeoutError: 超时
            SelectorChangedError: 网页结构变化
            ProviderError: 其他错误
        """

    # ── 参数映射（子类可覆盖） ──

    def translate_payload(self, payload: OpenAIPayload) -> str:
        """将 OpenAI payload 翻译为网页输入文本。

        默认行为：system message 拼入 user message 前缀，
        忽略 model / max_tokens / temperature（网页版不支持）。
        """
        messages = payload.get("messages", [])
        user_texts = []
        system_texts = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system" and content:
                system_texts.append(content)
            elif role == "user" and content:
                user_texts.append(content)

        parts = []
        if system_texts:
            parts.append("【系统指令】\n" + "\n".join(system_texts))
        if user_texts:
            parts.append("\n\n".join(user_texts))

        return "\n\n".join(parts)

    def get_provider_info(self) -> dict:
        return {
            "id": self.provider_id,
            "name": self.provider_name,
        }
