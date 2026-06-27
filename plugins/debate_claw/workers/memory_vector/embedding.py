"""
Embedding 引擎（软依赖 sentence-transformers）
============================================
未安装时优雅降级为 None，上层回退到关键词匹配。
"""

import os
import sys

# 全局单例
_engine: "EmbeddingEngine | None" = None
_available = False  # 是否可用


class EmbeddingEngine:
    """sentence-transformers + bge-m3 的轻量封装。"""

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self._model = None
        self._model_name = model_name
        self._dim = 0
        try:
            from sentence_transformers import SentenceTransformer
            print(f"[MEM] Loading embedding model: {model_name}", file=sys.stderr)
            self._model = SentenceTransformer(model_name)
            self._dim = self._model.get_sentence_embedding_dimension()
            _available = True
            print(f"[MEM] Embedding engine ready, dim={self._dim}", file=sys.stderr)
        except ImportError:
            print("[WARN] sentence_transformers not installed. "
                  "Run: pip install sentence-transformers", file=sys.stderr)
        except Exception as ex:
            print(f"[ERR] Failed to load embedding model: {ex}", file=sys.stderr)

    @property
    def available(self) -> bool:
        return self._model is not None

    @property
    def dimension(self) -> int:
        return self._dim if self._model else 0

    def encode(self, texts: list[str]) -> list[list[float]] | None:
        """
        将文本列表编码为向量。
        失败返回 None，调用方应回退到关键词匹配。
        """
        if not self._model:
            return None
        try:
            # batch encoding，自动截断
            embeddings = self._model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            return [emb.tolist() for emb in embeddings]
        except Exception as ex:
            print(f"[ERR] encode failed: {ex}", file=sys.stderr)
            return None


def get_embedding() -> "EmbeddingEngine":
    """获取全局 embedding 单例。"""
    global _engine
    if _engine is None:
        _engine = EmbeddingEngine()
    return _engine


def is_available() -> bool:
    """embedding 模块是否可用。"""
    global _available
    return _available
