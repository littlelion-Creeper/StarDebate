"""
ai_export_worker.py — 资料池 AI 综合总结导出工作线程
=====================================================
功能：对资料池中所有已导入文件逐个调用 AI 生成详细总结，
     最终合并为一份完整的 Markdown 综合总结文件。

对外 API：
| 类/方法 | 说明 |
|----------|------|
| AIExportWorker | QRunnable，后台处理所有文件 |
| AIExportSignals | 进度/完成信号 |

使用方式（在 material_pool_manager 中）：
    w = AIExportWorker(file_list, api_config)
    w.signals.progress_updated.connect(self._on_export_progress)
    w.signals.finished.connect(self._on_export_complete)
    self._thread_pool.start(w)
"""

import os
import time
import datetime
from PyQt5.QtCore import QObject, QRunnable, pyqtSignal
from workers.common.api_helper import monitored_api_post
from .file_parser import FileParser


# ── 详细总结的 System Prompt ──
SYSTEM_PROMPT = (
    "你是一位专业的辩论资料分析专家。你的任务是对给定的文档内容进行"
    "详尽、深入的总结分析。请严格按以下 JSON 格式返回（不要添加其他文字）：\n"
    '{\n'
    '  "detailed_summary": "详细的文档核心内容总结（500字以上，涵盖核心论点、' 
    '论据、数据、案例、逻辑推理等）",\n'
    '  "key_points": ["要点1：...", "要点2：...", "要点3：...", '
    '"要点4：...", "要点5：..."],\n'
    '  "core_content": "文档的核心内容概述（100字以内）",\n'
    '  "relevant_topics": ["相关辩题/话题1", "相关辩题/话题2"]\n'
    '}'
)


class AIExportSignals(QObject):
    """AI 导出线程的信号"""
    progress_updated = pyqtSignal(int, int, str, dict)
    """(completed, total, current_file_name, partial_result)"""
    finished = pyqtSignal(list)
    """全部分析完成，携带所有结果列表"""


class AIExportWorker(QRunnable):
    """对资料池中所有文件逐个进行 AI 详细总结分析"""

    def __init__(self, file_list: list, api_config: dict):
        """
        Args:
            file_list: 文件信息列表 [{"name": str, "path": str, "size": int, "type": str}, ...]
            api_config: API 配置字典 {api_url, api_key, model, ...}
        """
        super().__init__()
        self._files = file_list
        self._api_cfg = api_config
        self.signals = AIExportSignals()

    def run(self):
        """逐个处理文件，收集结果后发送 finished 信号"""
        all_results = []
        total = len(self._files)

        for idx, finfo in enumerate(self._files):
            fp = finfo.get("path", "")
            fname = finfo.get("name", "")
            result = {
                "file_name": fname,
                "file_path": fp,
                "file_size": finfo.get("size", 0),
                "file_type": finfo.get("type", ""),
                "success": False,
                "detailed_summary": "",
                "key_points": [],
                "core_content": "",
                "relevant_topics": [],
                "error": None,
            }

            try:
                # 1. 读取文件内容
                doc_text = FileParser.get_text(fp)
                if not doc_text or len(doc_text.strip()) < 10:
                    result["error"] = "文件内容为空或无法读取"
                    all_results.append(result)
                    self.signals.progress_updated.emit(
                        idx + 1, total, fname, result)
                    continue

                # 2. 截取前 8000 字符（避免 Token 超限）
                doc_text = doc_text[:8000]

                # 3. 调用 AI 生成详细总结
                user_prompt = (
                    f"请对以下文档内容进行详尽的总结分析。\n\n"
                    f"=== 文档内容 ===\n{doc_text}"
                )

                payload = {
                    "model": self._api_cfg.get(
                        "model", "deepseek-v4-flash"),
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 4096,
                    "temperature": 0.3,
                }

                resp, _elapsed = monitored_api_post(
                    self._api_cfg, payload, timeout=120,
                    feature_name="material_pool:ai_export",
                )

                if not resp:
                    result["error"] = "AI 请求无响应"
                    all_results.append(result)
                    self.signals.progress_updated.emit(
                        idx + 1, total, fname, result)
                    continue

                resp_data = resp.json()
                content_text = ""
                if "choices" in resp_data and resp_data["choices"]:
                    content_text = resp_data["choices"][0].get(
                        "message", {}).get("content", "")
                elif "response" in resp_data:
                    content_text = resp_data.get("response", "")

                if not content_text:
                    result["error"] = "AI 返回内容为空"
                    all_results.append(result)
                    self.signals.progress_updated.emit(
                        idx + 1, total, fname, result)
                    continue

                # 4. 解析 JSON
                parsed = self._parse_ai_response(content_text)
                if parsed:
                    result["success"] = True
                    result["detailed_summary"] = parsed.get(
                        "detailed_summary", content_text[:500])
                    result["key_points"] = parsed.get("key_points", [])
                    result["core_content"] = parsed.get(
                        "core_content", "")
                    result["relevant_topics"] = parsed.get(
                        "relevant_topics", [])
                else:
                    # JSON 解析失败，直接使用原文前 500 字符
                    result["success"] = True
                    result["detailed_summary"] = content_text[:500]
                    result["core_content"] = content_text[:100]

            except Exception as e:
                result["error"] = str(e)[:200]

            all_results.append(result)
            self.signals.progress_updated.emit(
                idx + 1, total, fname, result)

        # 全部完成
        self.signals.finished.emit(all_results)

    @staticmethod
    def _parse_ai_response(text: str) -> dict | None:
        """解析 AI 返回的 JSON 文本"""
        if not text:
            return None
        import re
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        import json as json_module
        try:
            data = json_module.loads(match.group(0))
            return data
        except (json_module.JSONDecodeError, ValueError):
            return None

    @staticmethod
    def build_markdown(all_results: list, project_name: str = "") -> str:
        """将所有 AI 分析结果组装为一份 Markdown 综合总结文件

        Args:
            all_results: AIExportWorker 返回的结果列表
            project_name: 项目名称（可选）

        Returns:
            str: 完整的 Markdown 内容
        """
        lines = []
        total = len(all_results)
        success = sum(1 for r in all_results if r.get("success"))
        fail = total - success
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        # ── 标题区 ──
        lines.append("# 📚 资料池 AI 综合总结\n")
        lines.append(f"**生成时间**: {now}")
        lines.append(f"**资料池**: {project_name or 'StarDebate 资料池'}")
        lines.append(f"**文件总数**: {total} 个")
        lines.append(f"**成功处理**: {success} 个")
        if fail:
            lines.append(f"**失败**: {fail} 个")
        lines.append("")
        lines.append("---\n")

        # ── 目录 ──
        lines.append("## 📑 目录\n")
        for idx, r in enumerate(all_results, 1):
            status = "✅" if r.get("success") else "❌"
            fname = r.get("file_name", f"文件{idx}")
            lines.append(f"- {status} [{idx}. {fname}](#{idx}{fname})")
        lines.append("")
        lines.append("---\n")

        # ── 各文件详情 ──
        for idx, r in enumerate(all_results, 1):
            fname = r.get("file_name", f"文件{idx}")
            fp = r.get("file_path", "")
            fsize = r.get("file_size", 0)
            ftype = r.get("file_type", "")
            success_flag = r.get("success", False)

            # 大小格式化
            size_str = f"{fsize / 1024:.1f} KB" if fsize else "未知"
            type_label = {
                ".md": "Markdown", ".txt": "文本",
                ".pdf": "PDF", ".docx": "Word",
                ".xlsx": "Excel", ".csv": "CSV",
                ".json": "JSON", ".html": "HTML",
            }.get(ftype, ftype.upper() if ftype else "未知")

            lines.append(f"<a id='{idx}{fname}'></a>\n")
            emoji = "✅" if success_flag else "❌"
            lines.append(f"## {emoji} {idx}. {fname}\n")

            # 文件信息
            lines.append("### 📋 文件信息")
            lines.append(f"- **文件名**: {fname}")
            lines.append(f"- **类型**: {type_label}")
            lines.append(f"- **大小**: {size_str}")
            lines.append(f"- **路径**: `{fp}`")
            lines.append("")

            if success_flag:
                # AI 详细总结
                lines.append("### 🤖 AI 详细总结\n")
                ds = r.get("detailed_summary", "")
                if ds:
                    lines.append(ds)
                lines.append("")

                # 关键要点
                kps = r.get("key_points", [])
                if kps:
                    lines.append("### 🔑 关键要点\n")
                    for i, kp in enumerate(kps, 1):
                        lines.append(f"{i}. {kp}")
                    lines.append("")

                # 核心内容
                cc = r.get("core_content", "")
                if cc:
                    lines.append("### 📌 核心内容\n")
                    lines.append(f"> {cc}")
                    lines.append("")

                # 相关话题
                topics = r.get("relevant_topics", [])
                if topics:
                    lines.append("### 🏷 相关话题\n")
                    for t in topics:
                        lines.append(f"- {t}")
                    lines.append("")
            else:
                err = r.get("error", "未知错误")
                lines.append("### ❌ 处理失败\n")
                lines.append(f"> 错误信息: {err}")
                lines.append("")

            lines.append("---\n")

        return "\n".join(lines)
