"""
向量存储（sqlite3 + numpy 可选）
=================================
用内置 sqlite3 存 metadata，numpy 做向量 Top-K 检索（可选，失败时回退到纯 Python + array 模块）。
"""

import array as _array
import json
import os
import sqlite3
import sys
import threading
from dataclasses import dataclass, field
from typing import Optional

# ── numpy 可选依赖 ──
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    np = None
    _HAS_NUMPY = False


def _serialize_vector(vec: list[float]) -> bytes:
    """将向量序列化为 bytes（标准库 array 模块，不依赖 numpy）。"""
    return _array.array('f', vec).tobytes()


def _deserialize_vector(blob: bytes) -> list[float]:
    """从 bytes 反序列化向量。"""
    return _array.array('f', blob).tolist()

# ── 数据结构 ──

@dataclass
class Chunk:
    """一个文本切片（向量化单元）。"""
    chunk_id: str          # 唯一 ID（如 "conv_20260614_001" 或 "doc_file_003"）
    source_type: str       # 来源类型: "memory" / "conversation" / "document"
    source_path: str       # 原始文件路径或标识
    content: str           # 原始文本内容
    embedding: list[float] | None = None  # 向量（可选，未安装 embedding 时为 None）
    metadata: dict = field(default_factory=dict)  # 额外元数据


@dataclass
class ChunkResult:
    """搜索结果。"""
    chunk: Chunk
    score: float           # 相似度分数 [0, 1]


# ── VectorStore ──

class VectorStore:
    """
    基于 sqlite3 + numpy 的轻量向量存储。

    用法：
        store = VectorStore("path/to/vector_store.db")
        store.add_chunks([Chunk(...)])
        results = store.search("用户问题", top_k=5)
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._ensure_table()

    # ── 表结构初始化 ──

    def _ensure_table(self):
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id         TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_path TEXT DEFAULT '',
                    content     TEXT NOT NULL,
                    embedding   BLOB,            -- 序列化的 float32 numpy 数组
                    metadata    TEXT DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_type);
            """)
        print(f"[MEM] VectorStore ready at {self._db_path}", file=sys.stderr)

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── 写入 ──

    def add_chunks(self, chunks: list[Chunk]) -> int:
        """批量写入 chunks。返回成功条数。"""
        if not chunks:
            return 0
        count = 0
        with self._lock:
            with self._get_conn() as conn:
                for ch in chunks:
                    emb_blob = None
                    if ch.embedding is not None:
                        emb_blob = _serialize_vector(ch.embedding)
                    try:
                        conn.execute(
                            "INSERT OR REPLACE INTO chunks "
                            "(id, source_type, source_path, content, embedding, metadata) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (ch.chunk_id, ch.source_type, ch.source_path,
                             ch.content, emb_blob, json.dumps(ch.metadata)),
                        )
                        count += 1
                    except Exception as ex:
                        print(f"[ERR] add_chunk failed {ch.chunk_id}: {ex}", file=sys.stderr)
                conn.commit()
        if count:
            print(f"[MEM] Indexed {count} chunks", file=sys.stderr)
        return count

    def remove_by_source(self, source_type: str, source_path_prefix: str = "") -> int:
        """按来源删除 chunks。"""
        with self._lock:
            with self._get_conn() as conn:
                if source_path_prefix:
                    cur = conn.execute(
                        "DELETE FROM chunks WHERE source_type=? AND source_path LIKE ?",
                        (source_type, f"{source_path_prefix}%"),
                    )
                else:
                    cur = conn.execute(
                        "DELETE FROM chunks WHERE source_type=?",
                        (source_type,),
                    )
                conn.commit()
                return cur.rowcount

    # ── 读取 ──

    def get_all_embeddings(self):
        """
        获取所有有向量的 chunk。
        返回 (embedding_matrix_or_lists, ids)。
        - 有 numpy 时返回 np.ndarray 矩阵
        - 无 numpy 时返回 list[list[float]]
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL"
            ).fetchall()
        if not rows:
            return ([], []) if not _HAS_NUMPY else (np.empty((0, 0)), [])
        ids = [r["id"] for r in rows]
        if _HAS_NUMPY:
            embeddings = [np.frombuffer(r["embedding"], dtype=np.float32) for r in rows]
            return np.vstack(embeddings), ids
        else:
            embeddings = [_deserialize_vector(r["embedding"]) for r in rows]
            return embeddings, ids

    def get_chunk_by_id(self, chunk_id: str) -> Chunk | None:
        """按 ID 查找单个 chunk。"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM chunks WHERE id=?", (chunk_id,)
            ).fetchone()
        if row is None:
            return None
        emb = None
        if row["embedding"] is not None:
            emb = _deserialize_vector(row["embedding"])
        meta = {}
        try:
            meta = json.loads(row["metadata"])
        except Exception:
            pass
        return Chunk(
            chunk_id=row["id"],
            source_type=row["source_type"],
            source_path=row["source_path"],
            content=row["content"],
            embedding=emb,
            metadata=meta,
        )

    def get_chunks_by_source(self, source_type: str, limit: int = 50) -> list[Chunk]:
        """按来源获取最近的 chunks。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE source_type=? ORDER BY rowid DESC LIMIT ?",
                (source_type, limit),
            ).fetchall()
        result = []
        for row in rows:
            emb = None
            if row["embedding"]:
                emb = _deserialize_vector(row["embedding"])
            result.append(Chunk(
                chunk_id=row["id"],
                source_type=row["source_type"],
                source_path=row["source_path"],
                content=row["content"],
                embedding=emb,
            ))
        return result

    # ── 检索 ──

    def search(self, query_embedding: list[float],
               top_k: int = 5, min_score: float = 0.3) -> list[ChunkResult]:
        """
        余弦相似度 Top-K 检索。
        query_embedding 必须已归一化。
        使用 numpy（可用时）或纯 Python 实现。
        """
        matrix_or_lists, ids = self.get_all_embeddings()
        if not ids:
            return []

        if _HAS_NUMPY:
            matrix = matrix_or_lists
            q = np.array(query_embedding, dtype=np.float32).reshape(1, -1)
            # 余弦相似度 = 点积（因为都已归一化）
            scores = (matrix @ q.T).flatten().tolist()
        else:
            vectors = matrix_or_lists
            q = query_embedding
            # 纯 Python 余弦相似度
            scores = []
            for vec in vectors:
                dot = sum(a * b for a, b in zip(q, vec))
                scores.append(dot)

        # 排序取 Top-K
        scored = sorted(zip(ids, scores), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        for cid, sc in scored:
            if sc < min_score:
                continue
            ch = self.get_chunk_by_id(cid)
            if ch:
                results.append(ChunkResult(chunk=ch, score=float(sc)))
        return results

    def keyword_search(self, query: str,
                       top_k: int = 5, source_type: str | None = None) -> list[ChunkResult]:
        """
        关键词回退检索（当 embedding 不可用时使用）。
        简单的 LIKE 匹配 + TF-IDF 近似。
        """
        keywords = query.lower().split()
        if not keywords:
            return []

        with self._get_conn() as conn:
            sql = "SELECT id, content, source_type, source_path, metadata FROM chunks"
            params = []
            if source_type:
                sql += " WHERE source_type=?"
                params.append(source_type)
            rows = conn.execute(sql, params).fetchall()

        scored = []
        for row in rows:
            text = (row["content"] or "").lower()
            hits = sum(1 for kw in keywords if kw in text)
            if hits > 0:
                score = hits / len(keywords)
                scored.append((row, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for row, sc in scored[:top_k]:
            meta = {}
            try:
                meta = json.loads(row["metadata"])
            except Exception:
                pass
            results.append(ChunkResult(
                chunk=Chunk(
                    chunk_id=row["id"],
                    source_type=row["source_type"],
                    source_path=row["source_path"],
                    content=row["content"],
                    metadata=meta,
                ),
                score=sc,
            ))
        return results

    # ── 统计 ──

    def stats(self) -> dict[str, int]:
        """返回各来源类型的 chunk 数量。"""
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            by_type = dict(conn.execute(
                "SELECT source_type, COUNT(*) FROM chunks GROUP BY source_type"
            ).fetchall())
            with_emb = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL"
            ).fetchone()[0]
        return {
            "total": total,
            "by_source_type": by_type,
            "with_embedding": with_emb,
        }

    def clear(self):
        """清空所有数据。"""
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM chunks")
                conn.commit()
