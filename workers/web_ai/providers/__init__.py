"""Web AI Provider 抽象层"""

from workers.web_ai.providers.base_provider import BaseWebAIProvider
from workers.web_ai.providers.deepseek_provider import DeepSeekProvider

__all__ = ["BaseWebAIProvider", "DeepSeekProvider"]
