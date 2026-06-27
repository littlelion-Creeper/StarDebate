"""
local_search.py — BM25 本地搜索引擎
====================================
基于倒排索引 + BM25 评分算法，支持中文分词和同义词扩展。

对外 API:
| 方法 | 说明 |
|------|------|
| search(query, index, pool_path) → list[dict] | 执行本地搜索 |
"""

import os
import math
import re
import time
from collections import defaultdict

from .file_parser import FileParser


class LocalSearcher:
    """BM25 本地搜索引擎"""

    # BM25 参数
    K1 = 1.5       # 词频饱和参数
    B = 0.75       # 长度归一化参数

    def __init__(self):
        pass

    # ── 搜索入口 ────────────────────────────────────────────

    @staticmethod
    def search(query: str, index_data: dict,
               pool_path: str, max_results: int = 50) -> list[dict]:
        """执行关键词搜索

        Args:
            query: 用户输入的搜索关键词
            index_data: IndexManager.load_index() 返回的索引
            pool_path: data_pool 目录路径
            max_results: 最大返回结果数

        Returns:
            [{score, title, file, file_type, source, match_count,
              snippet, file_path, meta}, ...]
        """
        start_time = time.perf_counter()
        files_index = index_data.get("files", {})
        inverted = index_data.get("inverted", {})

        # 1. 关键词预处理
        query_tokens = LocalSearcher._preprocess_query(query)

        # 2. 倒排索引查询 → 计算 BM25 得分
        N = len(files_index)
        if N == 0:
            return []

        # 统计每个文档总长度（从索引中读取）
        doc_lengths = {}
        for rel_path, meta in files_index.items():
            doc_lengths[rel_path] = meta.get("total_chars", 100)

        avgdl = sum(doc_lengths.values()) / max(N, 1)

        # 查询 token → 包含该 token 的文档列表
        token_docs = {}
        for token in query_tokens:
            token_docs[token] = inverted.get(token, [])

        # 收集所有命中文档
        all_hit_docs = set()
        for docs in token_docs.values():
            all_hit_docs.update(docs)

        if not all_hit_docs:
            return []

        # 计算每个文档的 BM25 得分
        scores = {}
        match_counts = {}
        for rel_path in all_hit_docs:
            if rel_path not in files_index:
                continue
            doc_len = doc_lengths.get(rel_path, avgdl)
            score = 0.0
            match_count = 0

            for token in query_tokens:
                docs_with_token = token_docs.get(token, [])
                if rel_path not in docs_with_token:
                    continue

                # IDF
                n = len(docs_with_token)
                idf = math.log((N - n + 0.5) / (n + 0.5) + 1.0)

                # TF (简化：用索引中存在性替代词频；对中文更稳定)
                tf = 1.0
                # 尝试获取实际词频
                full_path = os.path.join(pool_path, rel_path)
                if os.path.isfile(full_path):
                    body = LocalSearcher._read_file_safe(full_path, 100000)
                    if body:
                        actual_count = sum(1 for _ in
                                           re.finditer(re.escape(token), body,
                                                       re.IGNORECASE))
                        tf = actual_count if actual_count > 0 else 1

                # BM25 得分
                num = tf * (LocalSearcher.K1 + 1)
                denom = tf + LocalSearcher.K1 * (1 - LocalSearcher.B + LocalSearcher.B * doc_len / avgdl)
                score += idf * (num / denom)
                match_count += 1

            scores[rel_path] = score
            match_counts[rel_path] = match_count

        # 3. 排序 + 截断
        sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        results = []
        for rel_path, score in sorted_docs[:max_results]:
            meta = files_index.get(rel_path, {})
            file_path = os.path.join(pool_path, rel_path)
            snippet = LocalSearcher._extract_snippet(file_path, query_tokens)

            results.append({
                "score": round(score, 2),
                "ai_score": None,
                "title": meta.get("title", os.path.basename(rel_path)),
                "file": os.path.basename(rel_path),
                "file_type": meta.get("type", ""),
                "source": "data_pool",
                "match_count": match_counts.get(rel_path, 0),
                "summary": snippet[:120],
                "matched_paragraphs": [{"text": snippet[:200]}],
                "snippet": snippet[:200],
                "file_path": file_path,
                "rel_path": rel_path,
                "meta": {
                    "size": meta.get("size", 0),
                    "mtime": meta.get("mtime", ""),
                    "file_path": file_path,
                    "total_chars": meta.get("total_chars", 0),
                },
                "search_time": round((time.perf_counter() - start_time) * 1000),
            })

        return results

    # ── 预处理 ──────────────────────────────────────────────

    @staticmethod
    def _preprocess_query(query: str) -> list[str]:
        """预处理查询：中文分词 + 去停用词 + 去重"""
        tokens = []
        query = query.strip().lower()

        try:
            import jieba
            words = jieba.cut_for_search(query)
            for w in words:
                w = w.strip()
                if len(w) >= 2:
                    tokens.append(w)
        except ImportError:
            # 回退：中文 2-gram + 英文 split
            # 英文
            for w in re.findall(r"[a-z0-9]+", query):
                if len(w) >= 2:
                    tokens.append(w)
            # 中文
            chars = "".join(re.findall(r"[\u4e00-\u9fff]+", query))
            for i in range(len(chars) - 1):
                tokens.append(chars[i:i + 2])

        # 去停用词
        stopwords = {"的", "了", "在", "是", "我", "有", "和", "就", "不",
                     "人", "都", "一", "一个", "上", "也", "很", "到", "说",
                     "要", "去", "你", "会", "着", "没有", "看", "好", "自己"}
        tokens = [t for t in tokens if t not in stopwords]

        # 去重
        return list(dict.fromkeys(tokens))

    # ── 片段提取 ────────────────────────────────────────────

    @staticmethod
    def _read_file_safe(file_path: str, max_chars: int = 50000) -> str:
        """使用 FileParser 读取任意格式文件的文本内容"""
        text = FileParser.get_text(file_path)
        if text and max_chars:
            text = text[:max_chars]
        return text or ""

    @staticmethod
    def _extract_snippet(file_path: str, query_tokens: list[str]) -> str:
        """从文件中提取包含查询词的上下文片段"""
        text = LocalSearcher._read_file_safe(file_path)
        if not text:
            return ""

        # 找第一个匹配位置
        best_pos = -1
        for token in query_tokens:
            pos = text.lower().find(token.lower())
            if pos >= 0 and (best_pos < 0 or pos < best_pos):
                best_pos = pos

        if best_pos < 0:
            return text[:120].replace("\n", " ")

        # 取匹配位置前后各 60 字符
        start = max(0, best_pos - 60)
        end = min(len(text), best_pos + 120)
        snippet = text[start:end].replace("\n", " ")
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        return snippet
