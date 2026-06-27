"""
DebateClaw AI 回复工作线程
=======================
使用 QRunnable + QThreadPool（项目标准模式）。
"""

import json, os
from PyQt5.QtCore import QObject, QRunnable, pyqtSignal, QThreadPool

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "ai_config.json")

_DEFAULT_SYSTEM_PROMPT = (
    "你是一个专业的辩论助手，名为 DebateClaw。"
    "你擅长分析辩论问题、提供正反方论点、构建辩论框架、评估论证力度。"
    "请用简洁清晰的中文回答用户的辩论相关问题。"
    "如果用户上传了文件，请结合文件内容回答。"
    "请使用 Markdown 格式组织你的回复，包括标题、列表、粗体、代码块等。"
)


def _load_cfg() -> dict:
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _load_system_prompt() -> str:
    return _load_cfg().get("system_prompt", _DEFAULT_SYSTEM_PROMPT)


class _AiSignal(QObject):
    """主线程创建，信号自动 QueuedConnection。"""
    result = pyqtSignal(str)


class _AiRunnable(QRunnable):
    """后台任务。"""

    def __init__(self, signal: _AiSignal, api, messages, system_prompt, model, timeout):
        super().__init__()
        self._signal = signal
        self._api = api
        self._messages = messages
        self._system_prompt = system_prompt
        self._model = model
        self._timeout = timeout

    def run(self) -> None:
        try:
            print("[CLAW_W] call_ai 开始...")
            reply = self._api.call_ai(
                messages=self._messages,
                system_prompt=self._system_prompt,
                model=self._model,
                timeout=self._timeout,
            )
            print(f"[CLAW_W] call_ai 成功, len={len(reply)}")
            self._signal.result.emit(reply)
        except Exception as ex:
            print(f"[CLAW_W] call_ai 异常: {ex}")
            import traceback
            traceback.print_exc()
            self._signal.result.emit(f"__ERR__❌ AI 回复失败：{ex}")


def start_ai_reply(messages, on_done, on_error, api, model="", max_tokens=4096, temperature=0.7):
    """QRunnable 批量 AI 调用。"""
    cfg = _load_cfg()
    system_prompt = _load_system_prompt()
    model = model or cfg.get("model", "")
    mt = max_tokens or cfg.get("max_tokens", 4096)
    tp = temperature if temperature != 0.7 else cfg.get("temperature", 0.7)

    sig = _AiSignal()
    sig.result.connect(lambda text: (
        on_error(text[6:]) if text.startswith("__ERR__") else on_done(text)
    ))
    runnable = _AiRunnable(sig, api, messages, system_prompt, model, 30)
    QThreadPool.globalInstance().start(runnable)
