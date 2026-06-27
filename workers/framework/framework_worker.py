# -*- coding: utf-8 -*-
"""AI 框架生成异步线程"""

import requests
from PyQt5.QtCore import QThread, pyqtSignal
from workers.common.api_helper import monitored_api_post


class AIFrameworkWorker(QThread):
    """在子线程中调用 AI 分析一辩稿，生成结构化辩论框架"""

    finished = pyqtSignal(bool, str, str)  # success, error_msg, result_json_text

    def __init__(self, api_config: dict, speech_text: str, side: str, debate_title: str):
        super().__init__()
        self._api_config = api_config
        self._speech_text = speech_text
        self._side = side
        self._debate_title = debate_title

    def run(self):
        label = "正方" if self._side == "pro" else "反方"
        system_prompt = (
            "你是一位辩论分析专家，从一辩稿中提取结构化框架。\n\n"
            "提取以下类型的节点（node_type）：\n"
            "- position：核心立场\n"
            "- definition：关键概念定义，1-2个\n"
            "- criterion：评判标准，1-2个\n"
            "- argument：主要论点，2-4个\n"
            "- evidence：对应论点的论据\n"
            "- value：价值升华点，1-2个\n\n"
            "层级关系：position是根节点→definition/criterion/value是position子节点"
            "→argument是criterion子节点→evidence是argument子节点。\n\n"
            '输出纯JSON，结构：{"nodes":[{obj},...]}，每个对象含：\n'
            '  id(自增整数)、node_type、text(20-50字)、children(子节点id数组)\n'
            "禁止输出任何非JSON文字。text中禁用英文双引号。"
        )

        user_prompt = (
            "辩论主题：" + str(self._debate_title) + "\n"
            "辩方：" + label + "\n\n"
            "一辩稿内容：\n" + str(self._speech_text)
        )

        payload = {
            "model": self._api_config.get("model", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": self._api_config.get("max_tokens", 8192),
            "temperature": 0.7,
            "stream": False
        }

        try:
            resp, __elapsed = monitored_api_post(
                self._api_config, payload, timeout=90,
                feature_name="ai_framework"
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                self.finished.emit(True, "", content)
            else:
                err = "API 调用失败 (HTTP {})".format(resp.status_code)
                try:
                    err += ": {}".format(resp.json())
                except Exception:
                    err += ": {}".format(resp.text[:200])
                self.finished.emit(False, err, "")
        except requests.exceptions.Timeout:
            self.finished.emit(False, "AI框架生成请求超时，请检查网络或稍后重试", "")
        except requests.exceptions.ConnectionError:
            self.finished.emit(False, "无法连接 API 服务器，请检查 api_config.json 中的 api_url 是否正确", "")
        except Exception as e:
            self.finished.emit(False, "请求异常: {}".format(str(e)), "")
