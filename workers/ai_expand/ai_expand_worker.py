# -*- coding: utf-8 -*-
"""AIExpandWorker — 在子线程中调用 AI 对选中关键词进行扩写，返回多个方案"""

import requests
from workers.common.api_helper import monitored_api_post

from PyQt5.QtCore import QThread, pyqtSignal


class AIExpandWorker(QThread):
    """在子线程中调用 AI 对选中关键词进行扩写，返回多个方案"""
    finished = pyqtSignal(bool, str, str)  # success, error_msg, result_json_text

    def __init__(self, api_config: dict, full_text: str, keyword: str, side: str, debate_title: str):
        super().__init__()
        self._api_config = api_config
        self._full_text = full_text
        self._keyword = keyword
        self._side = side
        self._debate_title = debate_title

    def run(self):
        label = "正方" if self._side == "pro" else "反方"
        system_prompt = (
            "你是一位资深辩论教练，擅长帮助辩手完善辩论稿。\n"
            "用户将提供一段一辩稿全文和一个关键词，你需要围绕该关键词对相关内容进行扩写。\n\n"
            "扩写要求（非常重要，请严格遵守）：\n"
            "1. 仔细理解关键词周围的上下文，确保扩写内容与原文内容保持一致\n"
            "2. 重点完善逻辑链——从前提、推理到结论必须清晰连贯\n"
            "3. 补充具体论据——可以加入事实、数据、案例、理论、类比等，使论证更有力\n"
            "4. 保持与原文相同的语言风格和论证方向\n"
            "5. 扩写内容应直接嵌入原关键词位置，避免重复已有的内容\n\n"
            "【输出格式 — 不遵守将导致解析失败，请逐字核对后再输出】\n"
            "你必须只输出一段合法的 JSON，不要任何额外文字、解释或 markdown 标记。\n"
            "JSON 结构：{\"schemes\": [方案对象, ...]}，共 4 个方案对象。\n\n"
            "每个方案对象的字段：\n"
            "  - id: 整数 1-4\n"
            "  - angle: 短字符串，如\"逻辑深化\"、\"数据支撑\"、\"案例说明\"、\"反向论证\"\n"
            "  - text: 300-800 字纯文本段落。⚠️ 严禁包含未转义的英文双引号 \"\n"
            "    正确做法：需要引用时一律用中文引号「」代替英文双引号\n"
            "    错误示例：他说\"这是错的\" ← 这会导致 JSON 损坏！\n"
            "  - highlights: 字符串数组，3-5 个关键论点\n\n"
            "⚠️ JSON 合法性检查清单（输出前逐项确认）：\n"
            "1. 整个文本是一个合法的 JSON 对象，以 { 开头、} 结尾\n"
            "2. text 字段中不含任何英文双引号 \"（所有引用用「」代替）\n"
            "3. 所有字符串值用英文双引号包裹，内部的反斜杠已转义为 \\\\\n"
            "4. 对象和数组的最后一个元素后面没有逗号\n\n"
            "输出示例（严格模仿此格式）：\n"
            '{"schemes":[\n'
            '{"id":1,"angle":"逻辑深化","text":"此处写300-800字扩写内容。引用他人观点时用「中文引号」。","highlights":["论点1","论点2"]},\n'
            '{"id":2,"angle":"数据支撑","text":"此处写扩写内容。所有引用依旧使用「中文引号」。","highlights":["数据1","数据2"]},\n'
            '{"id":3,"angle":"案例说明","text":"此处写扩写内容。","highlights":["案例1","案例2"]},\n'
            '{"id":4,"angle":"反向论证","text":"此处写扩写内容。","highlights":["观点1","观点2"]}\n'
            ']}\n'
            "只输出 JSON，不要任何额外文字。"
        )
        user_prompt = (
            f"辩论主题：{self._debate_title}\n"
            f"辩方：{label}\n"
            f"关键词（需要围绕它扩写）：{self._keyword}\n\n"
            f"一辩稿全文：\n{self._full_text}"
        )

        payload = {
            "model": self._api_config.get("model", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": self._api_config.get("max_tokens", 8192),
            "temperature": 0.8,
            "stream": False
        }

        try:
            resp, __elapsed = monitored_api_post(
                self._api_config, payload, timeout=120,
                feature_name="ai_expand"
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                self.finished.emit(True, "", content)
            else:
                err = f"API 调用失败 (HTTP {resp.status_code})"
                try:
                    err += f": {resp.json()}"
                except Exception:
                    err += f": {resp.text[:200]}"
                self.finished.emit(False, err, "")
        except requests.exceptions.Timeout:
            self.finished.emit(False, "AI扩写请求超时，请检查网络或稍后重试", "")
        except requests.exceptions.ConnectionError:
            self.finished.emit(False, "无法连接 API 服务器，请检查 api_config.json 中的 api_url 是否正确", "")
        except Exception as e:
            self.finished.emit(False, f"请求异常: {str(e)}", "")
