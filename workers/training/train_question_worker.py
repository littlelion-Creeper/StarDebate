"""模拟训练 AI 出题线程"""
import json
import random
import requests
from PyQt5.QtCore import QThread, pyqtSignal
from workers.common.api_helper import monitored_api_post


class TrainingQuestionWorker(QThread):
    """在子线程中调用 AI 生成训练题目"""
    finished = pyqtSignal(bool, str, dict)  # success, error_msg, question_data

    def __init__(self, api_config: dict, mode: str, difficulty: str, debate_title: str,
                 training_format: str = "", training_position: str = ""):
        super().__init__()
        self._api_config = api_config
        self._mode = mode
        self._difficulty = difficulty
        self._debate_title = debate_title
        self._training_format = training_format
        self._training_position = training_position

    def _position_context(self) -> str:
        """生成专精辩位提示文本"""
        if not self._training_position:
            return ""
        parts = []
        if self._training_format:
            parts.append(f"赛制: {self._training_format}")
        parts.append(f"专精辩位: {self._training_position}")
        parts.append("请生成与该辩位职责、技巧密切相关的题目")
        return "【" + " · ".join(parts) + "】\n"

    def run(self):
        try:
            if self._mode == "scenario":
                question_data = self._generate_scenario()
            else:
                question_data = self._generate_technique()
            self.finished.emit(True, "", question_data)
        except Exception as e:
            self.finished.emit(False, str(e), {})

    def _generate_technique(self) -> dict:
        diff_guide = {
            "easy": "考察单一概念记忆，4个选项区分度≥70%，错误选项有明显缺陷",
            "medium": "2-3个关联概念对比辨析，需结合应用场景判断，2个选项各有合理性需权衡",
            "hard": "多概念综合推理，混入隐蔽的错误逻辑，选项设计要精致"
        }

        question_types = ["choice", "choice", "choice", "truefalse"]
        qtype = random.choice(question_types)
        correct_choice = random.choice(["A", "B", "C", "D"])
        pos_ctx = self._position_context()

        if qtype == "truefalse":
            correct_tf = random.choice(["A", "B"])
            system_prompt = (
                "你是一位辩论教练。生成一道辩论技巧判断题。\n\n"
                f"{pos_ctx}"
                f"难度: {self._difficulty} ({diff_guide.get(self._difficulty, '')})\n"
                "输出纯JSON（禁止任何其他文字）:\n"
                '{"type":"truefalse","question":"...","options":["正确","错误"],'
                f'"correct":"{correct_tf}",'
                f'"difficulty":"{self._difficulty}",'
                '"topic_category":"逻辑推理|论证方法|谬误辨析|辩位职责|辩论理论",'
                '"explanation":{"A":"...","B":"..."},'
                '"improvement_tips":{"A":"...","B":"..."}\n'
                f"注意：正确答案必须是 {correct_tf} 选项（{'正确' if correct_tf == 'A' else '错误'}），请据此设置题目的正确性。\n"
                "question使用正常从句，不要用倒装或古汉语结构。"
            )
        else:
            system_prompt = (
                "你是一位辩论教练。生成一道辩论技巧选择题（4选项）。\n\n"
                f"{pos_ctx}"
                f"难度: {self._difficulty} ({diff_guide.get(self._difficulty, '')})\n"
                "考察范围: 论证方法、逻辑谬误、辩位职责、辩论术语、推理方法、需根解损等\n"
                "输出纯JSON（禁止任何其他文字）:\n"
                '{"type":"choice","question":"...",'
                '"options":["A. ...","B. ...","C. ...","D. ..."],'
                f'"correct":"{correct_choice}",'
                f'"difficulty":"{self._difficulty}",'
                '"topic_category":"逻辑推理|论证方法|谬误辨析|辩位职责|辩论理论",'
                f'"explanation":{"A":"...","B":"...","C":"...","D":"...（正确）"如果正确答案是{correct_choice}，请在对应选项的explanation末尾标注"（正确）"},'
                '"improvement_tips":{"A":"...","B":"...","C":"...","D":"..."}\n'
                f"重要：正确答案必须放在 {correct_choice} 选项中。请先构思好哪个选项是正确答案，然后将正确内容放在 {correct_choice} 位置。\n"
                "question使用正常从句，不要用倒装或古汉语结构。"
            )

        user_prompt = f"辩论主题背景: {self._debate_title}\n请生成一道适合该辩题背景的辩论技巧测试题。"
        return self._call_api(system_prompt, user_prompt)

    def _generate_scenario(self) -> dict:
        diff_guide = {
            "easy": "1个冲突点，正确策略明显占优，3个错误选项各有明显缺陷",
            "medium": "2个冲突点，2个策略各有合理性需权衡，需分析风险与收益",
            "hard": "3个冲突点互相纠缠，3个备选策略都有部分合理性但各有一个致命缺陷，需多维度分析"
        }
        correct_choice = random.choice(["A", "B", "C", "D"])
        pos_ctx = self._position_context()

        if self._training_position:
            role_instruction = f"用户将扮演「{self._training_position}」角色，请围绕该辩位的职责和任务设计场景"
        else:
            role_instruction = "随机分配辩位角色（正方/反方，一辩~四辩）"

        system_prompt = (
            "你是一位辩论教练。基于辩题，随机生成一个辩论场景模拟题。\n\n"
            f"{pos_ctx}"
            f"难度: {self._difficulty} ({diff_guide.get(self._difficulty, '')})\n\n"
            "要求:\n"
            f"1. {role_instruction}\n"
            "2. 设计具体辩论局面（立论、驳辩、盘问、接质、总结等场景）\n"
            "3. 给出4个应对策略选项，1个最佳、3个有真实迷惑性的次优选项\n"
            "4. 次优选项要反映辩手常见误区\n\n"
            "输出纯JSON（禁止任何其他文字）:\n"
            '{"type":"scenario","category":"scenario",'
            f'"difficulty":"{self._difficulty}",'
            '"scenario":{"debate_title":"...","your_role":"正方二辩（驳辩位）",'
            '"situation":"反方一辩刚才立论指出...","task":"你需要驳斥..."},'
            '"question":"简化问题描述",'
            '"options":["A. 策略1...","B. 策略2...","C. 策略3...","D. 策略4..."],'
            f'"correct":"{correct_choice}",'
            '"topic_category":"场景策略|攻防决策|危机应对",'
            f'"strategy_analysis":{"A":"...","B":"...","C":"...","D":"...（最佳策略）"如果正确答案是{correct_choice}，请在对应选项的分析末尾标注"（最佳策略）"},'
            '"improvement_tips":{"A":"...","B":"...","C":"...","D":"..."}\n'
            f"重要：最佳策略必须放在 {correct_choice} 选项中。请先构思好4个策略，然后将最佳策略放在 {correct_choice} 位置，其余3个放在其他位置。\n"
            "scenario中的所有文本使用正常现代汉语，拒绝文言文或倒装结构。"
        )

        user_prompt = f"辩论主题背景: {self._debate_title}\n请基于此辩题生成一个辩论场景模拟题。"
        return self._call_api(system_prompt, user_prompt)

    def _call_api(self, system_prompt: str, user_prompt: str) -> dict:
        payload = {
            "model": self._api_config.get("model", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": self._api_config.get("max_tokens", 4096),
            "temperature": 0.8,
            "stream": False
        }
        resp, __elapsed = monitored_api_post(
            self._api_config, payload, timeout=120,
            feature_name="training_question"
        )
        if resp.status_code != 200:
            raise RuntimeError(f"API HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines)
        result = json.loads(content)
        result["category"] = self._mode
        if self._mode == "scenario":
            result["category"] = "scenario"
        else:
            result["category"] = "technique"
        return result
