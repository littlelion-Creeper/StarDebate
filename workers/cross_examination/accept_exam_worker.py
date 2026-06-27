# -*- coding: utf-8 -*-
"""模拟接质 AI 异步线程

支持三种模式：
  - init:    生成辩论稿 + 第一个质询问题
  - respond: 评分用户回答 + 提出下一个质询问题
  - end:     综合总结
"""

import json
import re
import requests
from PyQt5.QtCore import QThread, pyqtSignal
from workers.common.api_helper import monitored_api_post


class AcceptExaminationWorker(QThread):
    """模拟接质：AI 作为对方四辩质询，用户作为我方一辩回答并打分"""
    finished = pyqtSignal(bool, str, dict)  # success, error_msg, result_dict

    def __init__(self, api_config: dict, mode: str, user_side: str,
                 debate_title: str, pro_speech: str, con_speech: str,
                 messages: list = None, user_answer: str = "",
                 round_num: int = 1):
        """
        mode: "init" (生成一辩稿+首问) | "respond" (打分+下一问) | "end" (总结)
        """
        super().__init__()
        self._api_config = api_config
        self._mode = mode
        self._user_side = user_side
        self._debate_title = debate_title
        self._pro_speech = pro_speech
        self._con_speech = con_speech
        self._messages = messages or []
        self._user_answer = user_answer
        self._round_num = round_num

    def run(self):
        try:
            if self._mode == "init":
                result = self._do_init()
            elif self._mode == "respond":
                result = self._do_respond()
            elif self._mode == "end":
                result = self._do_end()
            else:
                self.finished.emit(False, "", {"error": f"未知模式: {self._mode}"})
                return
            self.finished.emit(True, "", result)
        except Exception as e:
            self.finished.emit(False, "", {"error": str(e)})

    def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        """通用 API 调用"""
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
        resp, __elapsed = monitored_api_post(
            self._api_config, payload, timeout=300,
            feature_name="accept_examination"
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        else:
            err = f"API 调用失败 (HTTP {resp.status_code})"
            try:
                err += f": {resp.json()}"
            except Exception:
                err += f": {resp.text[:200]}"
            raise RuntimeError(err)

    def _do_init(self) -> dict:
        """生成一辩稿 + 第一个质询问题"""
        side_label = self._side_label(self._user_side)
        opponent_label = "反方" if side_label == "正方" else "正方"

        system_prompt = (
            "你是一位专业的辩论教练，现在需要模拟一场正规辩论比赛中的接质（接受质询）训练。\n\n"
            "角色设定：\n"
            f"- AI 扮演：{opponent_label}四辩（质询方），负责对{side_label}一辩进行质询\n"
            f"- 用户扮演：{side_label}一辩（接质方），需要回答质询并维护己方立场\n\n"
            "任务步骤：\n"
            f"1. 根据辩题和立场，首先生成一份{side_label}一辩稿大纲（300-500字）\n"
            f"2. 以{opponent_label}四辩身份，提出第一个犀利的质询问题\n\n"
            "要求：\n"
            "- 一辩稿应包含清晰的论点、论据和逻辑链\n"
            "- 质询问题应针对立论的潜在弱点，具有挑战性\n"
            "- 问题应直接、简洁，便于辩手回应\n\n"
            "输出格式（纯 JSON，不要任何其他文字）：\n"
            "{\n"
            f'  "speech_title": "{side_label}一辩稿大纲",\n'
            '  "speech_content": "一辩稿内容（300-500字）",\n'
            '  "question": "第一个质询问题",\n'
            '  "question_tip": "质询方向提示（帮助接质方理解问题意图）"\n'
            "}"
        )

        user_prompt = (
            f"辩论主题：{self._debate_title}\n\n"
            f"=== 正方一辩稿 ===\n{self._pro_speech or '（未提供）'}\n\n"
            f"=== 反方一辩稿 ===\n{self._con_speech or '（未提供）'}\n\n"
            f"用户选择持方：{side_label}\n"
            f"请基于以上信息，生成{side_label}一辩稿大纲并以{opponent_label}四辩身份提出第一个质询问题。"
        )

        text = self._call_api(system_prompt, user_prompt)
        return self._parse_init_response(text)

    def _parse_init_response(self, text: str) -> dict:
        """解析 init 阶段的 JSON 返回"""
        text = text.strip()
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            text = m.group(1)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
        return {"speech_content": text[:500], "question": "请开始你的接质。"}

    def _do_respond(self) -> dict:
        """评分用户回答 + 提出下一个质询问题"""
        side_label = self._side_label(self._user_side)
        opponent_label = "反方" if side_label == "正方" else "正方"

        history_text = self._build_history_text()

        system_prompt = (
            "你是一位专业的辩论教练兼评委，现在正在进行接质训练。\n\n"
            f"角色设定：你同时扮演{opponent_label}四辩（质询方）和评委。\n\n"
            "任务：\n"
            f"1. 评估{side_label}一辩刚才的接质回答质量\n"
            f"2. 给出0-10分的评分（整数）\n"
            f"3. 提供简短点评（优点+改进建议）\n"
            f"4. 以{opponent_label}四辩身份提出下一个质询问题\n\n"
            "评分标准：\n"
            "- 逻辑性（3分）：回答是否逻辑清晰、自洽\n"
            "- 针对性（3分）：是否回应了问题的核心\n"
            "- 论据运用（2分）：是否充分调用己方论据\n"
            "- 表达力（2分）：语言是否简洁有力、有辩论感\n\n"
            "注意：\n"
            "- 如果是第6轮之后（含），is_end 可以设为 true 表示建议结束\n"
            "- 如果检测到用户要求结束，is_end 必须为 true\n"
            "- 如果 is_end 为 true，不再提出新问题\n\n"
            "输出格式（纯 JSON）：\n"
            "{\n"
            '  "score": 8,\n'
            '  "feedback": "点评内容（优点+改进建议，60-100字）",\n'
            '  "next_question": "下一个质询问题（is_end=false时必须提供）",\n'
            '  "question_tip": "本问的质询方向提示",\n'
            '  "is_end": false\n'
            "}"
        )

        user_prompt = (
            f"辩论主题：{self._debate_title}\n"
            f"用户持方：{side_label}\n"
            f"当前轮次：第{self._round_num}轮\n\n"
            f"=== 对话历史 ===\n{history_text}\n\n"
            f"=== {side_label}一辩刚才的回答 ===\n{self._user_answer}\n\n"
            f"请评分并提出下一个质询问题。"
        )

        text = self._call_api(system_prompt, user_prompt)
        return self._parse_json_response(text)

    def _do_end(self) -> dict:
        """总结接质训练"""
        side_label = self._side_label(self._user_side)
        history_text = self._build_history_text()

        system_prompt = (
            "你是一位专业的辩论教练，正在为接质训练做最终总结。\n\n"
            "任务：\n"
            f"1. 回顾{side_label}一辩在整个接质过程中的表现\n"
            "2. 给出综合评分（0-100分）\n"
            "3. 总结亮点和待改进之处\n"
            "4. 提供整体训练建议\n\n"
            "输出格式（纯 JSON）：\n"
            "{\n"
            '  "total_score": 85,\n'
            '  "summary": "综合总结（150-200字）",\n'
            '  "highlights": "接质亮点",\n'
            '  "improvements": "改进建议",\n'
            '  "advice": "训练建议"\n'
            "}"
        )

        user_prompt = (
            f"辩论主题：{self._debate_title}\n"
            f"接质方：{side_label}\n"
            f"总轮次：{self._round_num - 1}轮\n\n"
            f"=== 完整对话历史 ===\n{history_text}\n\n"
            "请给出综合总结和评分。"
        )

        text = self._call_api(system_prompt, user_prompt)
        return self._parse_json_response(text)

    def _parse_json_response(self, text: str) -> dict:
        """解析通用 JSON 返回"""
        text = text.strip()
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            text = m.group(1)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
        return {"score": -1, "feedback": text[:200], "next_question": "", "is_end": False,
                "total_score": -1, "summary": text[:200]}

    def _build_history_text(self) -> str:
        """构建对话历史文本"""
        lines = []
        for msg in self._messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "speech":
                lines.append(f"[一辩稿] {content}")
            elif role == "ai_question":
                lines.append(f"[AI质询] {content}")
            elif role == "user_answer":
                lines.append(f"[用户回答] {content}")
            elif role == "ai_score":
                lines.append(f"[AI评分] {content}")
            elif role == "feedback":
                lines.append(f"[AI点评] {content}")
        return "\n".join(lines)

    @staticmethod
    def _side_label(flag: str) -> str:
        return "正方" if flag == "pro" else "反方"
