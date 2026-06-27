"""
memory_vector: 本地向量记忆模块
================================
提供 embedding 生成、向量存储、语义检索能力。
"""

from .embedding import EmbeddingEngine, get_embedding
from .vector_store import VectorStore, Chunk, ChunkResult

__all__ = [
    "EmbeddingEngine",
    "get_embedding",
    "VectorStore",
    "Chunk",
    "ChunkResult",
]
