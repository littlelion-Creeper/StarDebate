# -*- coding: utf-8 -*-
"""AI 写稿异步线程 — 在子线程中调用 AI 基于框架稿写一辩稿，返回多个结果"""

import requests
from PyQt5.QtCore import QThread, pyqtSignal
from workers.common.api_helper import monitored_api_post


class AISpeechWriterWorker(QThread):
    """在子线程中调用 AI 基于框架稿写一辩稿，返回多个结果"""
    finished = pyqtSignal(bool, str, str)  # success, error_msg, result_json_text

    def __init__(self, api_config: dict, framework_text: str, side: str, debate_title: str):
        super().__init__()
        self._api_config = api_config
        self._framework_text = framework_text
        self._side = side
        self._debate_title = debate_title

    def run(self):
        label = "正方" if self._side == "pro" else "反方"
        system_prompt = (
            "你是一位资深的辩论教练和辩词写手，专精于撰写高质量的一辩稿。\n\n"
            "【任务】\n"
            "用户将提供一份辩论框架稿（包含立场、定义、判准、论点、论据等结构化的辩论要素），\n"
            "你需要基于该框架稿，为{s}撰写一份完整、专业的一辩稿。\n\n"
            "【写作要求】\n"
            "1. 严格基于框架稿中的立场和论点进行展开，不得偏离核心论点\n"
            "2. 一辩稿结构：开场引入 → 定义阐释 → 判准申明 → 核心论点展开 → 总结升华\n"
            "3. 每个论点须有清晰的逻辑链：前提→推理→结论\n"
            "4. 语言风格：正式、有说服力，但避免过于学术化，保留辩论的感染力\n"
            "5. 篇幅：800-1500字\n"
            "6. 生成 5 个不同侧重点的版本，每个版本至少保持60%不同的论据和例证\n\n"
            "【输出格式 — 必须严格遵守，否则解析失败】\n"
            "你必须只输出一段合法的 JSON，不要任何额外文字、解释或 markdown 标记。\n"
            "JSON 结构：{{\"drafts\": [稿本对象, ...]}}，共 5 个稿本对象。\n\n"
            "每个稿本对象的字段：\n"
            "  - id: 整数 1-5\n"
            "  - title: 短字符串，概括该版本的核心风格，如「逻辑严密型」「情感打动型」「数据支撑型」「案例丰富型」「价值升华型」\n"
            "  - summary: 50-100字简短摘要，说明该版本的特点和优势\n"
            "  - text: 800-1500字完整一辩稿正文。严禁包含未转义的英文双引号 \"，需要引用时一律用中文引号「」代替\n"
            "  - highlights: 字符串数组，3-5个该版本的核心亮点\n\n"
            "【JSON 合法性检查清单 — 输出前逐项确认】\n"
            "1. 整个文本以 {{ 开头、}} 结尾\n"
            "2. text 字段中不含任何英文双引号 \"（所有引用用「」代替）\n"
            "3. 所有字符串值用英文双引号包裹，内部反斜杠已转义为 \\\\\n"
            "4. 对象和数组的最后一个元素后面没有逗号\n\n"
            "【输出示例 — 严格模仿此格式】\n"
            '{{"drafts":[\n'
            '{{"id":1,"title":"逻辑严密型","summary":"以严谨的逻辑链构建论证体系，层层推进。","text":"主席、评委、各位观众，大家好。今天我方的立场是……（完整一辩稿）……谢谢大家。","highlights":["三层次论证结构","概念精确定义","逻辑无懈可击"]}},\n'
            '{{"id":2,"title":"情感打动型","summary":"用感性的语言和生动的案例打动评委和观众。","text":"主席、评委、各位观众，大家好。今天我方的立场是……（完整一辩稿）……谢谢大家。","highlights":["开篇故事引入","情感共鸣段落","修辞手法丰富"]}}\n'
            ']}}'
        ).format(s=label)

        user_prompt = (
            "辩论主题：{title}\n"
            "辩方：{side}\n\n"
            "【框架稿内容】\n"
            "{framework}\n\n"
            "请基于以上框架稿，为{side}撰写 5 个不同风格的一辩稿版本。"
        ).format(title=self._debate_title, side=label, framework=self._framework_text)

        payload = {
            "model": self._api_config.get("model", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": self._api_config.get("max_tokens", 16384),
            "temperature": 0.85,
            "stream": False
        }

        try:
            resp, __elapsed = monitored_api_post(
                self._api_config, payload, timeout=300,
                feature_name="speech_writer"
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
            self.finished.emit(False, "AI写稿请求超时（300秒），请检查网络或稍后重试", "")
        except requests.exceptions.ConnectionError:
            self.finished.emit(False, "无法连接 API 服务器，请检查 api_config.json 中的 api_url 是否正确", "")
        except Exception as e:
            self.finished.emit(False, "请求异常: {}".format(str(e)), "")
