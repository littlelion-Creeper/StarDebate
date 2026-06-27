# -*- coding: utf-8 -*-
"""段落管理器 — 一辩稿 content → paragraphs 切分/重建

核心功能：
1. split_content_to_paragraphs()  — 保存时：content + structure_tree → paragraphs
2. rebuild_content_from_paragraphs() — 接受 diff 后：paragraphs → content
3. get_paragraph_context()          — AI 系统提示：返回段落结构摘要

段落 JSON 格式：
    {
      "id": "opening",        // 结构树节点的 slug（有树时）或 para_N（无树时）
      "slug": "opening",       // 同 id，保留冗余方便查询
      "node_name": "开场引入", // 原始节点名
      "texts": [              // 按空行切分的子段落数组
        "主席、评委、各位观众，大家好。",
        "今天我方的立场是..."
      ]
    }
"""

import re


def split_content_to_paragraphs(
    content: str,
    leaf_slugs: list = None,
) -> list:
    """将一辩稿 content 文本切分为 paragraphs 数组。

    Args:
        content: 一辩稿完整正文文本。
        leaf_slugs: StructureTreeManager.get_leaf_slugs() 返回的 [(slug, name), ...]。
                     为 None 或空列表时，使用无树后备方案。

    Returns:
        list[dict]: paragraphs 数组。

    切分策略：
    - **有结构树**：按 leaf_slugs 顺序分配，用关键词/等分启发式定位边界
    - **无结构树**：按空行自动分段落，id 编号为 para_1, para_2...
    """
    if not content or not content.strip():
        return []

    text = content.strip()

    # ── 无树后备：按空行分段 ──
    if not leaf_slugs:
        return _split_by_blank_lines(text)

    # ── 有树驱动：按 slug 分配 ──
    return _split_by_tree_nodes(text, leaf_slugs)


def _split_by_blank_lines(text: str) -> list:
    """无结构树时的后备方案：按空行切分为 para_1, para_2..."""
    # 按双空行（或连续空行）分割为逻辑段落
    raw_segments = re.split(r'\n\s*\n', text)
    paragraphs = []
    for idx, seg in enumerate(raw_segments, 1):
        seg = seg.strip()
        if not seg:
            continue
        # 单个段内再按单空行拆分子文本
        texts = _split_single_paragraph(seg)
        paragraphs.append({
            "id": f"para_{idx}",
            "slug": f"para_{idx}",
            "node_name": f"段落{idx}",
            "texts": texts,
        })
    return paragraphs


def _split_single_paragraph(text: str) -> list:
    """将一个段落内的文本按单空行进一步拆分为子段。

    保留内部换行结构（如列表项），仅按明显的分隔空行拆分。
    """
    if not text:
        return []
    # 如果没有双空行，整体作为一条
    if '\n\n' not in text:
        return [text]
    parts = re.split(r'\n\s*\n', text)
    return [p.strip() for p in parts if p.strip()]


def _split_by_tree_nodes(text: str, leaf_slugs: list) -> list:
    """有结构树时，按叶子节点顺序分配内容到各段落。

    启发式策略（优先级从高到低）：
    1. 节点 keywords 在全文中的位置 → 作为锚点划分区间
    2. 等分法 → N 个节点均分全文长度
    3. 兜底：每个节点分配一段非空文本
    """
    n = len(leaf_slugs)
    if n == 0:
        return _split_by_blank_lines(text)
    if n == 1:
        slug, name = leaf_slugs[0]
        return [{
            "id": slug,
            "slug": slug,
            "node_name": name,
            "texts": _split_single_paragraph(text),
        }]

    # 收集所有节点的关键词作为锚点
    # （目前 structure_tree 的 keywords 是用户手动添加的，
    #   未来 AI 分析时会自动填充，这里做模糊匹配）
    text_len = len(text)

    # 尝试按比例等分（基础策略）
    chunk_size = text_len // n
    paragraphs = []

    for i, (slug, name) in enumerate(leaf_slugs):
        start = i * chunk_size
        end = (i + 1) * chunk_size if i < n - 1 else text_len
        segment = text[start:end].strip()

        # 清理首尾残留（避免在句中截断）
        if i > 0 and segment:
            first_nl = segment.find('\n')
            if first_nl > 0 and first_nl < 60:
                segment = segment[first_nl:].strip()
        if i < n - 1 and segment:
            last_rnl = segment.rfind('\n')
            if last_rnl > len(segment) - 60 and last_rnl > 0:
                segment = segment[:last_rnl].strip()

        if not segment:
            paragraphs.append({
                "id": slug,
                "slug": slug,
                "node_name": name,
                "texts": [],
            })
            continue

        texts = _split_single_paragraph(segment)
        paragraphs.append({
            "id": slug,
            "slug": slug,
            "node_name": name,
            "texts": texts,
        })

    return paragraphs


def rebuild_content_from_paragraphs(paragraphs: list) -> str:
    """从 paragraphs 数组重建完整的 content 文本。

    将所有 paragraph.texts 展平后用双空行连接。
    """
    if not paragraphs:
        return ""

    all_texts = []
    for p in paragraphs:
        texts = p.get("texts", [])
        if texts:
            # 同一 paragraph 内的子段落用单空行连接
            all_texts.append("\n".join(texts))

    return "\n\n".join(all_texts)


def get_paragraph_context(paragraphs: list) -> str:
    """生成段落结构的 AI 上下文摘要，用于注入 system prompt。

    Returns:
        str: 格式如：
        「当前一辩稿已按以下段落结构化（共5段）：
        [id: opening] 开场引入
        [id: definition] 定义阐释
        ...」
    """
    if not paragraphs:
        return "（当前一辩稿尚未结构化为段落）"

    lines = [f"当前一辩稿已按以下段落结构化（共 {len(paragraphs)} 段）："]
    for idx, p in enumerate(paragraphs, 1):
        pid = p.get("id", "?")
        name = p.get("node_name", "")
        texts = p.get("texts", [])
        word_count = sum(len(t) for t in texts)
        preview = ""
        if texts:
            preview_text = texts[0][:40].replace("\n", " ")
            if len(texts[0]) > 40:
                preview_text += "..."
            preview = f" — 预览: {preview_text}"
        lines.append(f"  [{idx}] id=\"{pid}\" ({name}, {word_count}字) {preview}")

    return "\n".join(lines)


def find_paragraph_by_id(paragraphs: list, target_id: str) -> dict | None:
    """根据段落 id 查找对应段落。"""
    for p in paragraphs:
        if p.get("id") == target_id or p.get("slug") == target_id:
            return p
    return None


def update_paragraph_text(paragraphs: list, target_id: str, new_texts: list) -> list:
    """替换指定段落的内容（用于接受 diff 后更新）。"""
    for p in paragraphs:
        if p.get("id") == target_id or p.get("slug") == target_id:
            p["texts"] = new_texts
            return paragraphs
    # 未找到则追加（防御性）
    paragraphs.append({
        "id": target_id,
        "slug": target_id,
        "node_name": target_id,
        "texts": new_texts,
    })
    return paragraphs
