"""立论与驳论 — AI 生成辩题线程"""
import json
import random
import requests
from PyQt5.QtCore import QThread, pyqtSignal
from workers.common.api_helper import monitored_api_post


class DebateExerciseTopicWorker(QThread):
    """在子线程中调用 AI 生成随机辩题和立场"""
    finished = pyqtSignal(bool, str, dict)

    def __init__(self, api_config: dict):
        super().__init__()
        self._api_config = api_config

    def run(self):
        try:
            topic_data = self._generate_topic()
            self.finished.emit(True, "", topic_data)
        except Exception as e:
            self.finished.emit(False, str(e), {})

    def _generate_topic(self) -> dict:
        stance = random.choice(["正方", "反方"])
        system_prompt = (
            "你是一位辩论赛出题专家。请随机生成一个有深度、有争议空间的辩题。\n\n"
            "要求：\n"
            "1. 辩题应具有一定哲学/社会/伦理深度\n"
            "2. 辩题应适合辩论，正反双方都有发挥空间\n"
            "3. 输出纯JSON（禁止任何其他文字）:\n"
            '{"topic":"辩题文本",'
            f'"assigned_stance":"{stance}",'
            '"pro_stance":"正方核心立场简述（30字内）",'
            '"con_stance":"反方核心立场简述（30字内）",'
            '"topic_category":"社会|科技|伦理|教育|文化|经济|法律|环境",'
            '"topic_description":"辩题背景简述（100字内）",'
            '"key_debate_points":["核心争议点1","核心争议点2","核心争议点3"],'
            '"writing_hints":["立论时可关注的角度1","角度2","角度3"]}\n\n'
            f"注意：assigned_stance 必须严格使用 {stance}，不要修改为其他措辞。"
        )
        payload = {
            "model": self._api_config.get("model", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "请随机生成一个有深度的辩论题目。"}
            ],
            "max_tokens": 2048,
            "temperature": 0.9,
            "stream": False
        }
        resp, __elapsed = monitored_api_post(
            self._api_config, payload, timeout=60,
            feature_name="exercise_topic"
        )
        if resp.status_code != 200:
            raise RuntimeError(f"API HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines)
        return json.loads(content)
