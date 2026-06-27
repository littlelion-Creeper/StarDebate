# -*- coding: utf-8 -*-
"""模拟质询 AI 异步线程

在子线程中调用 AI，同时扮演质询方和应答方，
输出 5-8 轮结构化 JSON 对话。
"""

import requests
from PyQt5.QtCore import QThread, pyqtSignal
from workers.common.api_helper import monitored_api_post


class CrossExaminationWorker(QThread):
    """在子线程中调用 AI 模拟对手质询，输出结构化 JSON"""
    finished = pyqtSignal(bool, str, str)  # success, "", result_json_text

    def __init__(self, api_config: dict, pro_speech: str, con_speech: str,
                 pro_ref_doc: list, con_ref_doc: list, debate_title: str):
        super().__init__()
        self._api_config = api_config
        self._pro_speech = pro_speech
        self._con_speech = con_speech
        self._pro_ref_doc = pro_ref_doc
        self._con_ref_doc = con_ref_doc
        self._debate_title = debate_title

    @staticmethod
    def _format_ref_doc(ref_doc: list) -> str:
        """格式化资料稿为文本"""
        if not ref_doc:
            return "（无资料）"
        lines = []
        for i, row in enumerate(ref_doc, 1):
            arg = row.get("argument", "")
            content = row.get("content", "")
            source = row.get("source", "")
            lines.append(f"  观点{i}：{arg}")
            lines.append(f"  内容{i}：{content}")
            if source:
                lines.append(f"  来源{i}：{source}")
        return "\n".join(lines)

    def run(self):
        pro_ref_text = self._format_ref_doc(self._pro_ref_doc)
        con_ref_text = self._format_ref_doc(self._con_ref_doc)

        system_prompt = (
            "你是一位经验丰富的辩论教练，现在需要模拟一场高质量的质询（Cross-Examination）演练。\n\n"
            "角色设定：你将同时扮演两个角色——\n"
            "1. 质询方（对手）：基于对方的立论和资料，提出尖锐、有针对性的质询问题\n"
            "2. 应答方（辩手）：运用己方一辩稿和资料来回答质询，展现逻辑严密性\n\n"
            "要求：\n"
            "1. 设计 5-8 轮质询，覆盖对方立论的主要逻辑链和核心论点\n"
            "2. 每个质询问题应一针见血，直指对方立论中可能的薄弱点、逻辑跳跃、前提不成立等\n"
            "3. 每个回答应充分调用己方资料稿中的论据和观点，配合一辩稿的论证逻辑\n"
            "4. 每次回答后提供一段「思路解析」，说明为什么这样回答、运用的策略和逻辑要点\n\n"
            "输出格式（必须是纯 JSON，不要有任何其他文字）：\n"
            "{\n"
            "  \"rounds\": [\n"
            "    {\n"
            "      \"round\": 1,\n"
            "      \"side\": \"正方\" 或 \"反方\",\n"
            "      \"question\": \"质询问题\",\n"
            "      \"answer\": \"应答内容\",\n"
            "      \"thinking\": \"思路解析：说明回答的策略逻辑\"\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            "请基于提供的辩方一辩稿和资料，交替质询正方和反方，让双方都有机会应答。"
            "严格注意：只输出 JSON 对象，不要包含任何解释、markdown 标记或其他文字。"
        )
        user_prompt = (
            f"辩论主题：{self._debate_title}\n\n"
            f"=== 正方一辩稿 ===\n{self._pro_speech}\n\n"
            f"=== 反方一辩稿 ===\n{self._con_speech}\n\n"
            f"=== 正方资料稿 ===\n{pro_ref_text}\n\n"
            f"=== 反方资料稿 ===\n{con_ref_text}\n\n"
            f"请基于以上材料，交替模拟对正方和反方的质询，输出 JSON。"
        )

        payload = {
            "model": self._api_config.get("model", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 8192,
            "temperature": self._api_config.get("temperature", 0.7),
            "stream": False
        }

        try:
            resp, __elapsed = monitored_api_post(
                self._api_config, payload, timeout=300,
                feature_name="cross_examination"
            )
            if resp.status_code == 200:
                data = resp.json()
                result = data["choices"][0]["message"]["content"]
                self.finished.emit(True, "", result)
            else:
                err = f"API 调用失败 (HTTP {resp.status_code})"
                try:
                    err += f": {resp.json()}"
                except Exception:
                    err += f": {resp.text[:200]}"
                self.finished.emit(False, "", err)
        except requests.exceptions.Timeout:
            self.finished.emit(False, "", "模拟质询请求超时，请检查网络或稍后重试")
        except requests.exceptions.ConnectionError:
            self.finished.emit(False, "", "无法连接 API 服务器，请检查 api_config.json 中的 api_url 是否正确")
        except Exception as e:
            self.finished.emit(False, "", f"请求异常: {str(e)}")
