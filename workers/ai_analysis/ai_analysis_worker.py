# -*- coding: utf-8 -*-
"""AI 分析异步线程 — 调用 DeepSeek API 分析一辩稿"""

import requests
from PyQt5.QtCore import QThread, pyqtSignal
from workers.common.api_helper import monitored_api_post


class AnalysisWorker(QThread):
    """在子线程中调用 DeepSeek API，避免阻塞 UI

    Signals:
        finished(bool, str, str): success, side("pro"/"con"), result_text
    """
    finished = pyqtSignal(bool, str, str)

    def __init__(self, api_config: dict, speech_text: str, debate_title: str, side: str):
        super().__init__()
        self._api_config = api_config
        self._speech_text = speech_text
        self._debate_title = debate_title
        self._side = side

    def run(self):
        label = "正方" if self._side == "pro" else "反方"
        system_prompt = (
            "你是一位专业的辩论教练。请对以下辩手的一辩稿进行分析，"
            "从以下几个维度输出：\n"
            "1. 论点（提炼出主要论点）\n"
            "2. 论证（逻辑链、推理方式）\n"
            "3. 论据（事实、数据、类比等论据是否有力）\n"
            "4. 优势（立论亮点 + 可能被攻击的薄弱点）\n"
            "5. 建议（具体优化方向）\n"
            "请用中文输出。严格禁止输出任何问候语、开场白或结束语，"
            "直接以 ## 标题开始逐条分析，使用 Markdown 排版。"
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
            "max_tokens": self._api_config.get("max_tokens", 2048),
            "temperature": self._api_config.get("temperature", 0.7),
            "stream": False
        }

        try:
            resp, __elapsed = monitored_api_post(
                self._api_config, payload, timeout=60,
                feature_name="ai_analysis"
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
            self.finished.emit(False, self._side, "请求超时，请检查网络或稍后重试")
        except requests.exceptions.ConnectionError:
            self.finished.emit(False, self._side, "无法连接 API 服务器，请检查 api_config.json 中的 api_url 是否正确")
        except Exception as e:
            self.finished.emit(False, self._side, f"请求异常: {str(e)}")
