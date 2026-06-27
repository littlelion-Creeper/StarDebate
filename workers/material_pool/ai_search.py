"""
ai_search.py — AI 语义搜索与精排
=================================
对本地搜索结果进行 AI 语义分析：重评分、生成摘要、提取关键段落。

对外 API:
| 方法 | 说明 |
|------|------|
| rerank_results(query, results, api_config, pool_path) → list[dict] | AI 精排 |
| summarize_document(file_path, api_config) → dict | AI 摘要 |
"""

import json as json_module
import time
import os

from workers.common.api_helper import monitored_api_post
from .file_parser import FileParser


class AISearcher:
    """AI 语义搜索与精排引擎"""

    DEFAULT_PROMPT = (
        "你是一位专业的辩论资料分析助手。你的任务是从提供的文本中提取"
        "与搜索关键词相关的核心观点和关键数据。\n\n"
        "请严格按以下JSON格式返回（不要添加其他文字）：\n"
        '{"relevance": 0.0-1.0, "summary": "50字以内的核心摘要", '
        '"key_points": ["观点1", "观点2", "观点3"], '
        '"matched_sentences": ["原文句子1", "原文句子2"]}'
    )

    @staticmethod
    def rerank_results(query: str, results: list[dict],
                       api_config: dict, pool_path: str,
                       max_to_rerank: int = 5,
                       callback=None) -> list[dict]:
        """对本地搜索结果进行 AI 语义精排（同步/批量）。

        Args:
            query: 搜索关键词
            results: 本地搜索结果列表
            api_config: API 配置 {api_url, api_key, model}
            pool_path: data_pool 目录
            max_to_rerank: 最多对前 N 条进行 AI 分析
            callback: 可选回调 function(completed, total, result)

        Returns:
            更新后的 results 列表（原地修改 + 返回）
        """
        top_n = results[:max_to_rerank]
        for idx, item in enumerate(top_n):
            file_path = item.get("file_path", "")
            if not os.path.isfile(file_path):
                continue

            try:
                ai_result = AISearcher._analyze_single(
                    query, file_path, api_config, item)
                if ai_result:
                    item["ai_score"] = ai_result.get("relevance", 0)
                    item["ai_summary"] = ai_result.get("summary", "")
                    item["ai_key_points"] = ai_result.get("key_points", [])
                    # 用 AI 找到的更精确段落替换 snippet
                    matched = ai_result.get("matched_sentences", [])
                    if matched:
                        item["matched_paragraphs"] = [
                            {"text": s} for s in matched
                        ]
                        item["summary"] = matched[0][:120] if matched else item.get("summary", "")
                else:
                    item["ai_score"] = 0
            except Exception:
                item["ai_score"] = 0
                continue

            if callback:
                callback(idx + 1, len(top_n), item)

        # 重新按混合得分排序
        results.sort(
            key=lambda x: AISearcher._hybrid_score(x),
            reverse=True
        )
        return results

    @staticmethod
    def _hybrid_score(item: dict) -> float:
        """混合评分: BM25 × 0.4 + AI × 60"""
        bm25 = item.get("score", 0)
        ai = item.get("ai_score", 0)
        if ai is None:
            ai = 0
        return bm25 * 0.4 + ai * 60

    @staticmethod
    def _analyze_single(query: str, file_path: str,
                        api_config: dict, item: dict) -> dict | None:
        """对单个文件进行 AI 语义分析"""
        # 通过 FileParser 读取任意格式文件的文本
        content = FileParser.get_text(file_path)
        if not content:
            return None
        content = content[:8000]

        if len(content.strip()) < 10:
            return None

        # 构建 Prompt
        prompt = (
            f"{AISearcher.DEFAULT_PROMPT}\n\n"
            f"=== 搜索关键词 ===\n{query}\n\n"
            f"=== 文件内容 ===\n{content}"
        )

        payload = {
            "model": api_config.get("model", "deepseek-v4-flash"),
            "messages": [
                {"role": "system",
                 "content": "你是一位专业辩论资料分析助手。只返回JSON，不要其他内容。"},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1024,
            "temperature": 0.3,
        }

        try:
            resp, elapsed = monitored_api_post(
                api_config, payload, timeout=30,
                feature_name="material_pool:ai_rerank",
            )
            if not resp:
                return None

            # 解析响应 — monitored_api_post 返回 requests.Response 对象
            resp_data = resp.json()
            content_text = ""
            if "choices" in resp_data and resp_data["choices"]:
                content_text = resp_data["choices"][0].get("message", {}).get("content", "")
            elif "response" in resp_data:
                content_text = resp_data.get("response", "")

            # 提取 JSON
            return AISearcher._parse_ai_response(content_text)

        except Exception:
            return None

    @staticmethod
    def _parse_ai_response(text: str) -> dict | None:
        """解析 AI 返回的 JSON"""
        if not text:
            return None
        # 尝试提取 JSON 块
        import re
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            data = json_module.loads(match.group(0))
            if "relevance" in data:
                data["relevance"] = float(data["relevance"])
            return data
        except (json_module.JSONDecodeError, ValueError):
            return None

    @staticmethod
    def summarize_document(file_path: str, api_config: dict) -> dict:
        """对单个文档进行 AI 摘要"""
        if not os.path.isfile(file_path):
            return {"success": False, "summary": None,
                    "key_points": [], "keywords": [],
                    "error": "文件不存在"}

        content = FileParser.get_text(file_path)
        if not content:
            return {"success": False, "summary": None,
                    "key_points": [], "keywords": [],
                    "error": "文件读取失败"}
        content = content[:6000]

        prompt = (
            "请对以下文档内容进行摘要，按JSON格式返回：\n"
            '{"summary": "100字以内的文档摘要", '
            '"key_points": ["要点1","要点2","要点3"], '
            '"keywords": ["关键词1","关键词2"]}\n\n'
            f"=== 文档内容 ===\n{content}"
        )

        payload = {
            "model": api_config.get("model", "deepseek-v4-flash"),
            "messages": [
                {"role": "system", "content": "你是一位专业文档摘要助手。只返回JSON。"},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 800,
            "temperature": 0.3,
        }

        try:
            resp, _ = monitored_api_post(
                api_config, payload, timeout=30,
                feature_name="material_pool:summarize",
            )
            resp_data = resp.json() if resp else {}
            content_text = ""
            if resp_data and "choices" in resp_data and resp_data["choices"]:
                content_text = resp_data["choices"][0].get("message", {}).get("content", "")

            data = AISearcher._parse_ai_response(content_text)
            if data:
                return {
                    "success": True,
                    "summary": data.get("summary", ""),
                    "key_points": data.get("key_points", []),
                    "keywords": data.get("keywords", []),
                    "error": None,
                }
            return {"success": True,
                    "summary": content_text[:200],
                    "key_points": [], "keywords": [],
                    "error": None}
        except Exception as e:
            return {"success": False, "summary": None,
                    "key_points": [], "keywords": [],
                    "error": str(e)}
