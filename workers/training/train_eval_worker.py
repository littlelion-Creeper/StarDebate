"""模拟训练 AI 评估线程"""
import requests
from PyQt5.QtCore import QThread, pyqtSignal
from workers.common.api_helper import monitored_api_post


class TrainingEvalWorker(QThread):
    """在子线程中调用 AI 对训练结果进行综合评价"""
    finished = pyqtSignal(bool, str, str)  # success, error_msg, eval_text

    def __init__(self, api_config: dict, questions: list, mode: str, difficulty: str,
                 training_format: str = "", training_position: str = ""):
        super().__init__()
        self._api_config = api_config
        self._questions = questions
        self._mode = mode
        self._difficulty = difficulty
        self._training_format = training_format
        self._training_position = training_position

    def run(self):
        try:
            eval_text = self._do_evaluation()
            self.finished.emit(True, "", eval_text)
        except Exception as e:
            self.finished.emit(False, str(e), "")

    def _do_evaluation(self) -> str:
        total = len(self._questions)
        correct = sum(1 for q in self._questions if q.get("is_correct"))
        diff_map = {"easy": 10, "medium": 15, "hard": 20}
        topics = {}
        for q in self._questions:
            if q.get("is_correct"):
                pass  # score handled separately
            cat = q.get("topic_category", "综合")
            if cat not in topics:
                topics[cat] = [0, 0]
            topics[cat][0] += 1
            if q.get("is_correct"):
                topics[cat][1] += 1

        topics_summary = "\n".join(
            f"  {cat}: {v[0]}题/正确{v[1]}" for cat, v in topics.items())

        diff_stats = {}
        for q in self._questions:
            d = q.get("difficulty", self._difficulty)
            if d not in diff_stats:
                diff_stats[d] = {"total": 0, "correct": 0}
            diff_stats[d]["total"] += 1
            if q.get("is_correct"):
                diff_stats[d]["correct"] += 1

        diff_summary = "\n".join(
            f"  {'简单' if d == 'easy' else '中等' if d == 'medium' else '困难'}: "
            f"{v['correct']}/{v['total']}"
            for d, v in diff_stats.items())

        system_prompt = (
            "你是一位资深辩论教练。用户刚完成了一场辩论模拟训练，"
            "请基于以下数据，给出200-300字的综合评价。\n\n"
            "评价应包含:\n"
            "1. 整体表现概览\n"
            "2. 优势领域（根据正确率高的题型/类别）\n"
            "3. 薄弱环节（根据错误集中的题型/类别）\n"
            "4. 针对性提升建议\n\n"
            "输出纯文本，不要markdown标记。"
        )
        user_prompt = (
            f"训练模式: {self._mode}\n"
            f"难度: {self._difficulty}\n"
            f"总题数: {total}  正确: {correct}  错误: {total - correct}\n"
            f"正确率: {(correct / total * 100):.0f}%\n\n")
        if self._training_format:
            if self._training_position:
                user_prompt += f"专精赛制: {self._training_format} · 辩位: {self._training_position}\n\n"
            else:
                user_prompt += f"专精赛制: {self._training_format}\n\n"
        user_prompt += (f"各类型正确率:\n{topics_summary}\n\n"
                        f"按难度统计:\n{diff_summary}\n\n"
                        "请给出综合评价。")

        payload = {
            "model": self._api_config.get("model", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 1024,
            "temperature": 0.7,
            "stream": False
        }
        resp, __elapsed = monitored_api_post(
            self._api_config, payload, timeout=60,
            feature_name="training_eval"
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        else:
            return f"(AI评价生成失败 HTTP {resp.status_code})"
