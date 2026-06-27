"""立论与驳论 — AI 生成对手一辩稿线程"""
import requests
from PyQt5.QtCore import QThread, pyqtSignal
from workers.common.api_helper import monitored_api_post


class DebateExerciseOpponentWorker(QThread):
    """在子线程中调用 AI 生成对立立场的一辩稿"""
    finished = pyqtSignal(bool, str, str)

    def __init__(self, api_config: dict, topic: str, user_stance: str, user_speech: str):
        super().__init__()
        self._api_config = api_config
        self._topic = topic
        self._user_stance = user_stance
        self._user_speech = user_speech

    def run(self):
        try:
            speech_text = self._generate_opponent_speech()
            self.finished.emit(True, "", speech_text)
        except Exception as e:
            self.finished.emit(False, str(e), "")

    def _generate_opponent_speech(self) -> str:
        opponent_stance = "反方" if self._user_stance == "正方" else "正方"

        if self._user_speech.strip():
            system_prompt = (
                f"你是一位经验丰富的辩论选手。你正在参加一场辩论赛，辩题是：{self._topic}\n\n"
                f"你的对手是{self._user_stance}，他/她已经发表了以下立论稿：\n"
                f"---\n{self._user_speech[:1500]}\n---\n\n"
                f"请你作为{opponent_stance}，撰写一篇{opponent_stance}的一辩立论稿。\n\n"
                "要求：\n"
                "1. 字数800-1200字\n"
                "2. 包含明确的定义、标准（判断标准）、核心论点（2-3个）、论据支撑\n"
                "3. 逻辑清晰，论证有力，有力反驳对手的核心观点\n"
                "4. 输出纯文本（不要markdown标记），格式如下：\n\n"
                "定义：...\n"
                "标准：...\n"
                "论点一：...\n"
                "论据：...\n"
                "论点二：...\n"
                "论据：...\n"
                "（如有论点三同理）\n"
                "总结：..."
            )
        else:
            system_prompt = (
                f"你是一位经验丰富的辩论选手。你正在参加一场辩论赛，辩题是：{self._topic}\n\n"
                f"请你作为{opponent_stance}，撰写一篇{opponent_stance}的一辩立论稿。\n\n"
                "要求：\n"
                "1. 字数800-1200字\n"
                "2. 包含明确的定义、标准（判断标准）、核心论点（2-3个）、论据支撑\n"
                "3. 逻辑清晰，论证有力，观点鲜明\n"
                "4. 输出纯文本（不要markdown标记），格式如下：\n\n"
                "定义：...\n"
                "标准：...\n"
                "论点一：...\n"
                "论据：...\n"
                "论点二：...\n"
                "论据：...\n"
                "（如有论点三同理）\n"
                "总结：..."
            )

        payload = {
            "model": self._api_config.get("model", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请生成{opponent_stance}的一辩立论稿。"}
            ],
            "max_tokens": 3072,
            "temperature": 0.7,
            "stream": False
        }
        resp, __elapsed = monitored_api_post(
            self._api_config, payload, timeout=90,
            feature_name="exercise_opponent"
        )
        if resp.status_code != 200:
            raise RuntimeError(f"API HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]
