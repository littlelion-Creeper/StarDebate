"""
DebateClaw AI 记忆管理（Markdown + 向量检索版）
==============================================
取代原 JSON 键值对存储，改为按主题分 Markdown 文件存储。
保留 [MEM:write key=value] / [MEM:read key] 标记机制作为快捷写入通道。
新增向量检索摘要接口，用于 RAG 场景。
"""

import json
import os
import re
import sys

# ── 路径常量 ──
_MEM_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "MEMORY")
_TOPICS_DIR = os.path.join(_MEM_DIR, "topics")
_DB_PATH = os.path.join(_MEM_DIR, "vector_store.db")

# ── 正则标记 ──
_RE_WRITE = re.compile(r'^\[MEM:write\s+([^=\n]+)=(.+)\]$', re.MULTILINE)
_RE_WRITE_TOPIC = re.compile(r'^\[MEM:write\s+([^:=\n]+):([^=\n]+)=(.+)\]$', re.MULTILINE)
_RE_READ = re.compile(r'^\[MEM:read\s+(.+)\]$', re.MULTILINE)
_RE_ANY_MEM = re.compile(r'^\[MEM:(?:read|write).*\]$', re.MULTILINE)

# ── 默认主题文件映射 ──
_DEFAULT_TOPICS = {
    "user_preferences": "user_preferences.md",
    "debate_topics": "debate_topics.md",
    "project_notes": "project_notes.md",
    "quick_notes": "quick_notes.md",
}


def _ensure_dirs():
    os.makedirs(_MEM_DIR, exist_ok=True)
    os.makedirs(_TOPICS_DIR, exist_ok=True)


def _resolve_topic_name(topic_raw: str) -> str:
    """
    解析主题名。
    1. 如果在 _DEFAULT_TOPICS 映射表中，返回映射键（如 user_preferences）
    2. 否则将主题名降为小写、空格/连字符替换为下划线后作为新主题名
    """
    if topic_raw in _DEFAULT_TOPICS:
        return topic_raw
    # 不在映射表中：空格/连字符 → 下划线，转为小写
    return re.sub(r'[\s\-]+', '_', topic_raw).lower()


def _write_with_header(topic_name: str, content: str, mode: str = "append"):
    """写入主题文件，首次写入时自动添加 H1 标题。"""
    _ensure_dirs()
    path = _topic_path(topic_name)
    is_new = not os.path.exists(path)
    if is_new:
        display_name = topic_name.replace('_', ' ').replace('-', ' ').title()
        header = f"# {display_name}\n\n"
        write_memory_file(topic_name, header + content, mode="overwrite")
    else:
        write_memory_file(topic_name, content, mode=mode)


# ════════════════════════════════════════
# Markdown 文件操作
# ════════════════════════════════════════

def _topic_path(topic_name: str) -> str:
    """获取主题文件的完整路径。"""
    # 支持直接传 .md 文件名，也支持传主题 key
    if topic_name.endswith(".md"):
        return os.path.join(_TOPICS_DIR, topic_name)
    filename = _DEFAULT_TOPICS.get(topic_name, f"{topic_name}.md")
    return os.path.join(_TOPICS_DIR, filename)


def read_memory_file(topic_name: str) -> str:
    """
    读取指定主题的 Markdown 文件内容。
    topic_name: 主题名或 .md 文件名。
    返回文件内容字符串；不存在返回空串。
    """
    path = _topic_path(topic_name)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as ex:
        print(f"[MEM-ERR] read {path}: {ex}", file=sys.stderr)
        return ""


def write_memory_file(topic_name: str, content: str,
                     mode: str = "append"):
    """
    写入/追加到主题 Markdown 文件。

    Args:
        topic_name: 主题名或 .md 文件名
        content: 要写入的文本
        mode: "append" 追加到末尾，"overwrite" 覆盖整个文件
    """
    _ensure_dirs()
    path = _topic_path(topic_name)
    try:
        if mode == "append" and os.path.exists(path) and content.strip():
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"\n\n{content}")
        else:
            parent = os.path.dirname(path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        print(f"[MEM] Written to {topic_name} ({len(content)} chars)", file=sys.stderr)

        # 触发向量索引更新
        _trigger_index(path)

    except Exception as ex:
        print(f"[MEM-ERR] write {path}: {ex}", file=sys.stderr)


def list_topic_files() -> list[dict]:
    """列出所有已创建的主题记忆文件。"""
    _ensure_dirs()
    result = []
    for fn in sorted(os.listdir(_TOPICS_DIR)):
        if not fn.endswith(".md"):
            continue
        fp = os.path.join(_TOPICS_DIR, fn)
        stat = os.stat(fp)
        result.append({
            "name": fn,
            "path": fp,
            "size": stat.st_size,
            "modified": stat.st_mtime,
        })
    return result


def delete_topic_file(topic_name: str) -> bool:
    """删除指定主题文件。"""
    path = _topic_path(topic_name)
    if not os.path.exists(path):
        return False
    try:
        os.remove(path)
        return True
    except Exception:
        return False


# ════════════════════════════════════════
# 向量检索摘要
# ════════════════════════════════════════

def search_summary(query: str, top_k: int = 5) -> str:
    """
    通过向量检索生成记忆摘要文本，用于注入 system message。
    如果 embedding 不可用则回退到关键词检索。
    返回格式化的摘要字符串；无结果返回空串。
    """
    from workers.memory_vector.vector_store import VectorStore
    from workers.memory_vector.embedding import get_embedding

    store = VectorStore(_DB_PATH)
    emb_engine = get_embedding()

    results = []
    if emb_engine.available:
        emb_list = emb_engine.encode([query])
        if emb_list:
            results = store.search(emb_list[0], top_k=top_k, min_score=0.25)
    else:
        results = store.keyword_search(query, top_k=top_k)

    if not results:
        return ""

    lines = ["## 📚 相关记忆（语义检索）"]
    for i, r in enumerate(results, 1):
        source_label = {
            "memory": "📝 长期记忆",
            "conversation": "💬 对话历史",
            "document": "📄 资料文档",
        }.get(r.chunk.source_type, "📌 其他")
        preview = (r.chunk.content[:200] +
                   ("..." if len(r.chunk.content) > 200 else ""))
        lines.append(f"\n**[{source_label}]** (相关度 {r.score:.2f})")
        lines.append(preview.replace("\n", " "))
    return "\n".join(lines)


def get_vector_stats() -> dict:
    """获取向量索引统计信息。"""
    from workers.memory_vector.vector_store import VectorStore
    return VectorStore(_DB_PATH).stats()


# ════════════════════════════════════════
# 向后兼容：标记机制
# ════════════════════════════════════════

def apply_writes(text: str) -> int:
    """
    扫描 text 中的 [MEM:write] 标记并按主题分发写入。

    新格式（推荐）: [MEM:write 主题名:key=value]
      主题名在 _DEFAULT_TOPICS 映射表中时写入对应文件，
      不在表中时自动创建新文件（降为小写+下划线）。

    旧格式（向后兼容）: [MEM:write key=value] 写入 quick_notes.md。

    返回写入条数。
    """
    count = 0

    # 1. 新格式: [MEM:write 主题名:key=value] （优先处理）
    topic_spans = set()
    for m in _RE_WRITE_TOPIC.finditer(text):
        topic_spans.add(m.span())
        topic_raw = m.group(1).strip()
        key = m.group(2).strip()
        val = m.group(3).strip()
        if not key or not topic_raw:
            continue
        topic_name = _resolve_topic_name(topic_raw)
        entry = f"- **{key}**: {val}"
        _write_with_header(topic_name, entry, mode="append")
        count += 1

    # 2. 旧格式: [MEM:write key=value] → quick_notes（跳过已被新格式处理的位置）
    for m in _RE_WRITE.finditer(text):
        if m.span() in topic_spans:
            continue
        key = m.group(1).strip()
        val = m.group(2).strip()
        if not key:
            continue
        entry = f"- **{key}**: {val}"
        write_memory_file("quick_notes", entry, mode="append")
        count += 1

    return count


def collect_reads(text: str) -> dict[str, str]:
    """
    扫描 text 中的 [MEM:read key]，在所有记忆文件中搜索匹配。
    保留向后兼容。
    """
    result = {}
    keys = {m.group(1).strip() for m in _RE_READ.finditer(text)}
    if not keys:
        return result

    # 在 quick_notes 中搜索键名
    notes = read_memory_file("quick_notes")
    for key in keys:
        pattern = re.escape(key)
        match = re.search(rf'- \*\*{pattern}\*\*:\s*(.+)', notes, re.MULTILINE | re.IGNORECASE)
        result[key] = match.group(1) if match else "(未记录)"
    return result


def strip_memory_markers(text: str) -> str:
    """移除文本中的 [MEM:...] 行。保持向后兼容。"""
    return _RE_ANY_MEM.sub("", text).strip()


def summary() -> str:
    """
    生成记忆摘要，用于注入系统消息。
    兼容旧调用方式：先输出结构化记忆，再附加向量检索片段。
    """
    _ensure_dirs()
    parts = []

    # 1. 结构化记忆（各主题文件的前几行）
    topics_info = []
    for info in list_topic_files():
        if info["size"] == 0:
            continue
        name = info["name"].replace(".md", "")
        content = read_memory_file(name)
        preview = content[:300].strip().replace("\n", " ")
        topics_info.append(f"**{name}**: {preview}")

    if topics_info:
        parts.append("## 已知用户长期记忆\n")
        parts.append("\n".join(topics_info))

    # 2. 向量检索部分由调用方决定是否触发（避免每次都检索）

    return "\n\n".join(parts)


# ════════════════════════════════════════
# 内部：索引触发
# ════════════════════════════════════════

def _trigger_index(file_path: str):
    """当记忆文件变更时更新向量索引。"""
    try:
        from workers.memory_vector.indexer import index_document_file
        from workers.memory_vector.vector_store import VectorStore
        store = VectorStore(_DB_PATH)
        index_document_file(file_path, store)
    except Exception as ex:
        print(f"[MEM-WARN] Index trigger failed: {ex}", file=sys.stderr)
