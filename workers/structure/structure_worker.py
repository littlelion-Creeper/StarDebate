"""AI 结构分析异步线程 - 在子线程中调用 AI 分析一辩稿结构，输出结构化 JSON"""
import requests
from PyQt5.QtCore import QThread, pyqtSignal
from workers.common.api_helper import monitored_api_post


class StructureAnalysisWorker(QThread):
    """在子线程中调用 AI 分析一辩稿结构，输出结构化 JSON"""
    finished = pyqtSignal(bool, str, str)  # success, side, result_json_text

    def __init__(self, api_config: dict, speech_text: str, debate_title: str, side: str):
        super().__init__()
        self._api_config = api_config
        self._speech_text = speech_text
        self._debate_title = debate_title
        self._side = side

    def run(self):
        label = "正方" if self._side == "pro" else "反方"
        system_prompt = (
            "你是一位专业的辩论稿结构分析师。请仔细分析以下一辩稿文本，"
            "提取其逻辑结构和关键论点层次，并按指定 JSON 格式输出。\n\n"
            "要求：\n"
            "1. 将一辩稿分解为 3-6 个主要章节（如：开篇立论/背景引入、核心论点1、"
            "核心论点2、论证展开、反驳预设、总结陈词等）\n"
            "2. 每个章节提取 2-5 个核心关键词（概念、术语、数据维度等）\n"
            "3. 如果某个章节内有清晰的分论点子层级，用 children 字段表达\n"
            "4. 章节名称应简洁有力，反映该段的核心论点\n\n"
            "输出格式（必须是纯 JSON，不要有任何其他文字）：\n"
            "[\n"
            "  {\n"
            "    \"name\": \"章节名称\",\n"
            "    \"keywords\": [\"关键词1\", \"关键词2\"],\n"
            "    \"children\": []\n"
            "  }\n"
            "]\n\n"
            "严格注意：只输出 JSON 数组，不要包含任何解释、markdown 标记或其他文字。"
        )
        user_prompt = (
            f"辩论主题：{self._debate_title}\n"
            f"辩方：{label}\n"
            f"一辩稿内容：\n{self._speech_text}"
        )

        payload = {
            "model": self._api_config.get("model", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 4096,
            "temperature": 0.3,
            "stream": False
        }

        try:
            resp, __elapsed = monitored_api_post(
                self._api_config, payload, timeout=120,
                feature_name="structure_analysis"
            )
            if resp.status_code == 200:
                data = resp.json()
                result = data["choices"][0]["message"]["content"]
                self.finished.emit(True, self._side, result)
            else:
                err = f"API 调用失败 (HTTP {resp.status_code})"
                try:
                    err += f": {resp.json()}"
                except Exception:
                    err += f": {resp.text[:200]}"
                self.finished.emit(False, self._side, err)
        except requests.exceptions.Timeout:
            self.finished.emit(False, self._side, "结构分析请求超时，请检查网络或稍后重试")
        except requests.exceptions.ConnectionError:
            self.finished.emit(False, self._side, "无法连接 API 服务器，请检查 api_config.json 中的 api_url 是否正确")
        except Exception as e:
            self.finished.emit(False, self._side, f"请求异常: {str(e)}")
