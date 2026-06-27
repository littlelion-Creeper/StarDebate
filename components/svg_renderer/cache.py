"""
SvgRenderer LRU 缓存管理

缓存键: (svg_path, size, primary_hex, accent_hex, mode)
缓存值: QPixmap
"""
import os
import json
from collections import OrderedDict
from PyQt5.QtGui import QPixmap


class SvgCache:
    """线程安全的 LRU 缓存（单进程 Qt 主线程，无需加锁）"""

    def __init__(self, max_size: int = 256):
        self._max_size = max(1, max_size)
        self._enabled = True
        self._store: OrderedDict[tuple, QPixmap] = OrderedDict()

    # ── 公共 API ─────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
        if not value:
            self.clear()

    @property
    def max_size(self) -> int:
        return self._max_size

    @max_size.setter
    def max_size(self, value: int):
        self._max_size = max(1, value)
        self._evict()

    def get(self, key: tuple) -> QPixmap | None:
        """命中返回 QPixmap，否则返回 None"""
        if not self._enabled:
            return None
        if key in self._store:
            self._store.move_to_end(key)
            return self._store[key]
        return None

    def put(self, key: tuple, pixmap: QPixmap):
        """写入缓存并驱逐超出上限的旧条目"""
        if not self._enabled or pixmap is None:
            return
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = pixmap
        self._evict()

    def clear(self):
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)

    # ── 内部 ────────────────────────────────────────────────

    def _evict(self):
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    # ── 配置持久化 ───────────────────────────────────────────

    def load_config(self, config_path: str):
        """从 svg_renderer.json 读取缓存配置"""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._enabled = data.get("cache_enabled", True)
            self._max_size = data.get("cache_max", 256)
        except (json.JSONDecodeError, OSError):
            pass

    def save_config(self, config_path: str):
        """保存当前缓存配置到 svg_renderer.json"""
        try:
            existing = {}
            if os.path.isfile(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            existing["cache_enabled"] = self._enabled
            existing["cache_max"] = self._max_size
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=4)
        except OSError:
            pass
