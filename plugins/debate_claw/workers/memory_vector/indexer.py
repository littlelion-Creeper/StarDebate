"""
索引器（后台线程）
=================
负责：
  - 对话历史切片 + embedding + 入库
  - 资料文档切片 + embedding + 入库
  - QRunnable 异步执行，不阻塞 UI
"""

import os
import sys
import uuid

from PyQt5.QtCore import QObject, pyqtSignal, QRunnable

from .vector_store import VectorStore, Chunk
from .embedding import get_embedding


# ── 切片工具 ──

def chunk_text(text: str, max_chars: int = 512,
               overlap: int = 64) -> list[str]:
    """
    将长文本按段落/句子切分为 chunks。
    保持语义完整性：优先在换行、句号处断开。
    """
    if not text or len(text) <= max_chars:
        return [text] if text else []

    # 先按段落切分
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        # 没有段落分隔符时按句子切分
        sentences = _split_sentences(text)
        paragraphs = sentences

    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 1 <= max_chars:
            current = (current + "\n" + para).strip() if current else para
        else:
            if current:
                chunks.append(current)
            if len(para) <= max_chars:
                current = para
            else:
                # 段落本身太长，强制截断
                sub_chunks = _force_split(para, max_chars, overlap)
                chunks.extend(sub_chunks[:-1])
                current = sub_chunks[-1] if sub_chunks else ""
    if current:
        chunks.append(current)

    return chunks


def _split_sentences(text: str) -> list[str]:
    """简单句子分割。"""
    import re
    parts = re.split(r'(?<=[。！？.!?])\s*', text)
    return [p.strip() for p in parts if p.strip()]


def _force_split(text: str, max_len: int, overlap: int) -> list[str]:
    """硬性按字符数截断。"""
    result = []
    start = 0
    while start < len(text):
        end = min(start + max_len, len(text))
        result.append(text[start:end])
        start += max_len - overlap
    return result


# ── 对话历史索引 ──

def index_conversation_history(
    conv_history: list[dict],
    store: VectorStore,
) -> int:
    """
    将对话历史切片并索引入库。
    conv_history: [{role, content}, ...]
    返回入库的 chunk 数。
    """
    chunks_list = []
    for i, msg in enumerate(conv_history):
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if not content or role == "system":
            continue

        # 标记角色前缀
        prefix = "User: " if role == "user" else ("Assistant: " if role == "assistant" else f"{role}: ")
        full_text = prefix + content

        # 切片
        pieces = chunk_text(full_text, max_chars=400, overlap=50)
        for j, piece in enumerate(pieces):
            chunks_list.append(Chunk(
                chunk_id=f"conv_{uuid.uuid4().hex[:8]}_{i}_{j}",
                source_type="conversation",
                source_path="current_session",
                content=piece,
                metadata={"role": role, "msg_index": i},
            ))

    # 批量 embedding
    emb_engine = get_embedding()
    texts = [c.content for c in chunks_list]
    embeddings = emb_engine.encode(texts) if emb_engine.available else None
    if embeddings:
        for c, emb in zip(chunks_list, embeddings):
            c.embedding = emb

    count = store.add_chunks(chunks_list)
    print(f"[MEM] Indexed {count} conversation chunks from {len(conv_history)} messages",
          file=sys.stderr)
    return count


# ── 文档索引 ──

def index_document_file(file_path: str, store: VectorStore) -> int:
    """
    将单个文件切片并索引入库。
    支持 txt / md / json 等文本文件。
    返回入库的 chunk 数。
    """
    if not os.path.exists(file_path):
        print(f"[MEM] File not found: {file_path}", file=sys.stderr)
        return 0

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="gbk") as f:
                text = f.read()
        except Exception as ex:
            print(f"[ERR] Cannot read {file_path}: {ex}", file=sys.stderr)
            return 0
    except Exception as ex:
        print(f"[ERR] Cannot read {file_path}: {ex}", file=sys.stderr)
        return 0

    if not text.strip():
        return 0

    # 文档用稍大的 chunk
    pieces = chunk_text(text, max_chars=600, overlap=80)
    filename = os.path.basename(file_path)

    chunks_list = []
    for i, piece in enumerate(pieces):
        chunks_list.append(Chunk(
            chunk_id=f"doc_{filename[:16]}_{i}",
            source_type="document",
            source_path=file_path,
            content=piece,
            metadata={"filename": filename, "chunk_index": i},
        ))

    # 批量 embedding
    emb_engine = get_embedding()
    embeddings = emb_engine.encode([c.content for c in chunks_list]) \
        if emb_engine.available else None
    if embeddings:
        for c, emb in zip(chunks_list, embeddings):
            c.embedding = emb

    count = store.add_chunks(chunks_list)
    print(f"[MEM] Indexed document {filename}: {count} chunks ({len(text)} chars)",
          file=sys.stderr)
    return count


def index_document_directory(dir_path: str, store: VectorStore,
                             extensions: tuple[str, ...] = (".txt", ".md", ".json", ".py"),
                             recursive: bool = True) -> int:
    """
    索引目录下所有支持的文件。
    """
    total = 0
    if not os.path.isdir(dir_path):
        return total

    pattern = "**/*" if recursive else "*"
    import glob
    for ext in extensions:
        for fp in glob.glob(os.path.join(dir_path, pattern + ext), recursive=recursive):
            if not os.path.isfile(fp) or fp.endswith("__pycache__"):
                continue
            total += index_document_file(fp, store)

    print(f"[MEM] Directory index complete: {dir_path}, total {total} chunks",
          file=sys.stderr)
    return total


# ── 后台索引 Worker（QRunnable） ──

class IndexerWorker(QRunnable):
    """
    后台索引任务。
    可索引对话历史、单个文件或整个目录。
    """

    def __init__(self, db_path: str,
                 conv_history: list | None = None,
                 files_to_index: list[str] | None = None,
                 dir_to_index: str | None = None):
        super().__init__()
        self._db_path = db_path
        self._conv_history = conv_history
        self._files = files_to_index
        self._dir = dir_to_index
        self.setAutoDelete(True)

    def run(self):
        store = VectorStore(self._db_path)
        total = 0

        if self._conv_history:
            total += index_conversation_history(self._conv_history, store)

        if self._files:
            for fp in self._files:
                total += index_document_file(fp, store)

        if self._dir and os.path.isdir(self._dir):
            total += index_document_directory(self._dir, store)

        print(f"[MEM] IndexerWorker finished: {total} total chunks indexed",
              file=sys.stderr)
