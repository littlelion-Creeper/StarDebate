"""立论与驳论 — AI 综合评分线程"""
import json
import requests
from PyQt5.QtCore import QThread, pyqtSignal
from workers.common.api_helper import monitored_api_post


class DebateExerciseEvalWorker(QThread):
    """在子线程中调用 AI 对立论和驳论进行综合评分"""
    finished = pyqtSignal(bool, str, dict)

    def __init__(self, api_config: dict, topic: str, user_stance: str,
                 position_speech: str, ai_speech: str, rebuttal_speech: str):
        super().__init__()
        self._api_config = api_config
        self._topic = topic
        self._user_stance = user_stance
        self._position_speech = position_speech
        self._ai_speech = ai_speech
        self._rebuttal_speech = rebuttal_speech

    def run(self):
        try:
            eval_data = self._do_evaluation()
            self.finished.emit(True, "", eval_data)
        except Exception as e:
            self.finished.emit(False, str(e), {})

    def _do_evaluation(self) -> dict:
        system_prompt = (
            "你是一位资深辩论裁判。请对用户的表现进行评分。\n\n"
            "评分分两大部分：\n"
            "一、立论评分（满分100）:\n"
            "  - 论点清晰度(25分): 论点是否明确、可理解\n"
            "  - 逻辑严密性(25分): 论证逻辑是否完整、自洽\n"
            "  - 论据充分度(25分): 论据是否有说服力、多样性\n"
            "  - 表达文采(25分): 语言表达是否精炼、有力\n\n"
            "二、驳论评分（满分100）:\n"
            "  - 驳论针对性(25分): 是否准确识别并回应对方核心论点\n"
            "  - 逻辑拆解(25分): 是否有效拆解对方逻辑\n"
            "  - 论据反驳(25分): 是否有力反驳对方论据\n"
            "  - 表达力度(25分): 驳论语言是否犀利有力\n\n"
            "输出纯JSON（禁止任何其他文字）:\n"
            '{"position_score": {"clarity": N, "logic": N, "evidence": N, "expression": N, "total": N},'
            '"rebuttal_score": {"targeting": N, "deconstruction": N, "refutation": N, "force": N, "total": N},'
            '"total_score": N,'
            '"strengths": ["优点1","优点2"],'
            '"weaknesses": ["不足1","不足2"],'
            '"suggestions": ["建议1","建议2"],'
            '"summary":"200字以内的综合评价"}'
        )

        user_prompt = (
            f"辩题: {self._topic}\n"
            f"用户立场: {self._user_stance}\n\n"
            f"=== 用户立论稿 ===\n{self._position_speech[:2000]}\n\n"
            f"=== AI对手一辩稿 ===\n{self._ai_speech[:2000]}\n\n"
            f"=== 用户驳论稿 ===\n{self._rebuttal_speech[:2000]}"
        )

        payload = {
            "model": self._api_config.get("model", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 2048,
            "temperature": 0.7,
            "stream": False
        }
        resp, __elapsed = monitored_api_post(
            self._api_config, payload, timeout=60,
            feature_name="exercise_eval"
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
