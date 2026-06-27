"""WebAIQueue — Web AI 全局串行队列

Web Provider 同一时间只能处理一个请求（同一浏览器实例）。
"""

import logging
import threading
from typing import Optional

_logger = logging.getLogger("StarDebate.web_ai.queue")


class WebAIQueue:
    """全局串行任务队列（线程安全）

    确保 Web AI 调用按顺序执行，同时只运行一个请求。
    API 调用不受此限制（天然并发）。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._is_busy = False
        self._pending_count = 0

    def acquire(self) -> bool:
        """申请执行权限（阻塞等待）"""
        _logger.debug(f"Queue acquire: pending={self._pending_count}")
        self._pending_count += 1
        self._lock.acquire()
        self._pending_count -= 1
        self._is_busy = True
        return True

    def release(self):
        """释放执行权限"""
        self._is_busy = False
        try:
            self._lock.release()
        except RuntimeError:
            pass  # 可能已被释放
        _logger.debug("Queue released")

    @property
    def is_busy(self) -> bool:
        return self._is_busy

    @property
    def pending_count(self) -> int:
        return self._pending_count

    def queue_status_text(self) -> str:
        """获取排队状态文本"""
        if not self._is_busy and self._pending_count == 0:
            return ""
        if self._pending_count > 0:
            return f"排队中...（第 {self._pending_count + 1} 位）"
        return ""


# 全局单例
_global_queue: Optional[WebAIQueue] = None


def get_web_ai_queue() -> WebAIQueue:
    """获取全局 Web AI 队列单例"""
    global _global_queue
    if _global_queue is None:
        _global_queue = WebAIQueue()
    return _global_queue
