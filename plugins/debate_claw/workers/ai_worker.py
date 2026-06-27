"""
DebateClaw AI 工作线程
======================
职责: 在工作线程中执行 SSE 流式 AI 调用，
      支持原生 tools（Function Calling）+ [PERM:...] 标记降级两种模式。
      检测到权限请求时暂停并通知主线程。
"""

import json, os, re, sys
import requests
from PyQt5.QtCore import QObject, pyqtSignal, QThread

from plugins.debate_claw.workers.permission_handler import (
    scan_permissions, strip_permissions, check_already,
    execute_permission as _exec_perm,
)


# ── Tools 定义（DeepSeek Function Calling）──

TOOLS_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": (
                "读取项目中的文件内容。"
                "支持相对路径（相对于项目根目录）或绝对路径。"
                "当你需要查看一辩稿、资料稿或其他项目文件时使用。"
                "路径示例: 'speech_pro.json', 'data_pool/材料.docx'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string",
                             "description": "文件路径。相对路径相对于项目根目录，或直接写绝对路径。"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": (
                "将内容写入项目中的文件。"
                "支持相对路径（相对于项目根目录）或绝对路径。"
                "可创建新文件或修改已有文件。"
                "注意：当写入一辩稿（speech_pro.json / speech_con.json）时，"
                "content 字段必须使用纯文本格式，"
                "不要包含任何 Markdown 符号（如 # ** - ` > 等），"
                "系统会自动将纯文本包装为 JSON 格式保存。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string",
                             "description": "文件路径，相对于项目根目录或绝对路径。"},
                    "content": {"type": "string",
                                "description": "要写入的内容。写入一辩稿时请使用纯文本，不要包含 Markdown 符号。"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_list",
            "description": (
                "列出项目目录中的文件和子目录。"
                "传入 '.' 可列出项目根目录下的所有文件。"
                "传入子目录名（如 'data_pool'）可查看特定目录内容。"
                "用于探索项目结构、查找文件位置。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "目录路径。传入 '.' 列出项目根目录；传入子目录名（如 'data_pool'）列出该目录。"
                    }
                },
                "required": ["directory"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": (
                "在资料池和项目文件中搜索关键词。"
                "当需要查找特定信息、证据、数据时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "network",
            "description": (
                "访问外部网络搜索资料或抓取 URL 内容。"
                "仅当本地资料不足且需要外部证据时使用，需要用户授权。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url_or_query": {
                        "type": "string",
                        "description": "要访问的 URL（以 http/https 开头）或搜索关键词"
                    }
                },
                "required": ["url_or_query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute",
            "description": (
                "执行 Python 代码进行数据分析或可视化。"
                "仅允许使用 matplotlib、pandas、numpy 等安全库。"
                "需要用户授权并查看代码后执行。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要执行的 Python 代码"
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": (
                "在长期记忆、对话历史和资料文档中语义搜索相关内容。"
                "当你需要回忆之前讨论过的内容、用户偏好、辩论主题或已导入的资料时使用。"
                "返回最相关的记忆片段及其来源类型和匹配度。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要搜索的关键词或自然语言查询，如 '用户偏好'、'辩论赛规则'、'一辩稿论点'"
                    }
                },
                "required": ["query"]
            }
        }
    },
]


class AIWorker(QObject):
    """AI 调用工作线程——支持 tools 模式 + [PERM:...] 标记降级。

    信号:
        chunk_received(str)              — 纯文本片段到达（正文流）
        perm_requested(dict)             — [PERM:...] 标记模式：检测到新权限 {type: path}
        perm_interrupted(str, dict)      — [PERM:...] 标记模式：因权限中断 (text_before, {type:path})
        tool_calls_received(list)         — tools 模式：检测到完整 tool_calls [(id, name, args)]
        finished(str)                     — 正常完成 (full_text)
        error(str)                        — 出错
    """

    chunk_received = pyqtSignal(str)
    perm_requested = pyqtSignal(dict)
    perm_interrupted = pyqtSignal(str, dict)
    tool_calls_received = pyqtSignal(list)
    usage_received = pyqtSignal(dict)   # {"prompt_tokens":N, "completion_tokens":N, "total_tokens":N}
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, api_config: dict, messages: list, state: dict,
                 conversation_history_ref: list):
        super().__init__()
        self._api_cfg = api_config
        self._messages = messages
        self._state = state
        self._conv_history = conversation_history_ref
        self._paused = False
        self._interrupted = False
        self._current_perms: dict = {}
        self._text_before_perm = ""
        self._should_stop = False

        # tools 模式状态
        self._tool_mode_active = True       # 是否启用 tools 模式
        self._safe_write_mode = False       # 安全写入模式（禁用 file_write）
        self._pending_tool_calls: list = [] # 收集到的 tool_calls
        self._tool_call_id_counter = 0      # 用于生成唯一 ID

    def stop(self):
        self._should_stop = True

    # ── tools 模式接口 ──

    def set_tool_results(self, results: list[dict]):
        """注入 tool 执行结果，准备继续调用 API。

        Args:
            results: [{"tool_call_id": str, "result": str}, ...]
        """
        first_id = results[0]["tool_call_id"][:12] if results else "none"
        print(f"[DBG] AIWorker.set_tool_results: {len(results)} results, first_id={first_id}", file=sys.stderr)

        # 追加 assistant 的 tool_calls 消息
        assistant_msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}
                }
                for tc in self._pending_tool_calls
            ],
        }
        self._messages.append(assistant_msg)

        # 追加每个 tool 的结果
        for r in results:
            self._messages.append({
                "role": "tool",
                "tool_call_id": r["tool_call_id"],
                "content": r["result"],
            })

        # 清空 pending
        self._pending_tool_calls.clear()
        self._paused = False

    def get_pending_tool_calls(self) -> list:
        """获取当前待处理的 tool_calls 列表。"""
        return self._pending_tool_calls[:]

    def get_messages_snapshot(self) -> list:
        """获取当前消息历史快照。"""
        print(f"[DBG] AIWorker.get_messages_snapshot: {len(self._messages)} msgs", file=sys.stderr)
        for i, m in enumerate(self._messages):
            role = m.get("role", "?")
            content = m.get("content", "")
            tc = m.get("tool_calls")
            marker = ""
            if content:
                marker = f" content_len={len(content)}"
            if tc:
                marker = f" tool_calls={len(tc)}"
            print(f"  msg[{i}] role={role}{marker}", file=sys.stderr)
        return self._messages[:]

    # ── 原有接口兼容 ──

    def resume_with_result(self, granted: bool, perm_type: str,
                           perm_path: str, result_text: str | None = None):
        """[PERM:...] 标记模式的恢复接口（保持向后兼容）。

        注意：不设置 _interrupted = False，让旧 worker 保持中断状态，
        防止旧 worker 继续运行并发出过期的 finished 信号覆盖 state。
        """
        if granted and result_text is not None:
            self._inject_permission_result(perm_type, perm_path, result_text)
        self._paused = False

    def get_state_snapshot(self) -> tuple[str, list]:
        """[PERM:...] 标记模式的状态快照（保持向后兼容）。"""
        return (self._text_before_perm, self._messages[:])

    def _inject_permission_result(self, perm_type: str, perm_path: str, result_text: str):
        perm_label = {
            "file_read": "文件读取", "file_write": "文件写入",
            "file_list": "列出目录", "search": "搜索文件",
            "network": "网络访问", "execute": "执行代码",
        }.get(perm_type, perm_type)

        result_msg = (
            f"[系统] 用户已授权 {perm_label} 操作（路径: {perm_path}）。"
            f"\n\n执行结果:\n```\n{result_text}\n```"
        )
        self._messages.append({"role": "system", "content": result_msg})

    # ── 核心：SSE 流式调用 ──

    def run(self):
        """在工作线程中执行 SSE 流式 AI 调用（含 tools 模式）。"""
        url = self._api_cfg.get("api_url", "")
        key = self._api_cfg.get("api_key", "")
        model = self._api_cfg.get("model", "deepseek-chat")

        if not url or not key:
            self.error.emit("API 未配置")
            return

        payload = {
            "model": model,
            "messages": self._messages,
            "max_tokens": 4096,
            "temperature": 0.7,
            "stream": True,
        }

        # 如果启用 tools 模式，添加 tools 定义
        if self._tool_mode_active:
            if self._safe_write_mode:
                # 安全写入模式：排除 file_write tool
                payload["tools"] = [
                    t for t in TOOLS_DEFINITION
                    if t.get("function", {}).get("name") != "file_write"
                ]
            else:
                payload["tools"] = TOOLS_DEFINITION
            payload["tool_choice"] = "auto"

        try:
            resp = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                stream=True,
                timeout=60,
            )
            resp.raise_for_status()

            full_text = ""
            perm_seen_local = set()   # [PERM:...] 模式的已见权限
            tool_chunks_buffer = []   # tool call 的 chunk 缓冲区
            has_seen_tools = False    # 是否收到过任何 tool_calls chunk
            no_tool_chunk_count = 0   # 无 tool_calls 的连续 chunk 计数

            for line in resp.iter_lines():
                if self._should_stop or not self._state.get("streaming"):
                    break

                while self._paused and not self._should_stop:
                    QThread.msleep(100)

                if self._should_stop or not self._state.get("streaming"):
                    break

                if not line:
                    continue

                ld = line.decode("utf-8", errors="replace")
                if not ld.startswith("data: ") or ld[6:].strip() == "[DONE]":
                    continue

                try:
                    chunk = json.loads(ld[6:])
                except json.JSONDecodeError:
                    continue

                choices = chunk.get("choices", [{}])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                finish_reason = choices[0].get("finish_reason", None)

                # ── 捕获 usage（可能出现在最后一个 choices chunk 或独立行）──
                usage = chunk.get("usage")
                if usage:
                    self.usage_received.emit(dict(usage))

                # ── 1. 检测 tool_calls（tools 模式）──
                if "tool_calls" in delta:
                    has_seen_tools = True
                    no_tool_chunk_count = 0
                    tc_delta = delta["tool_calls"]

                    for tcd in tc_delta:
                        idx = tcd.get("index", 0)
                        # 确保列表长度足够
                        while len(tool_chunks_buffer) <= idx:
                            tool_chunks_buffer.append({
                                "id": "", "name": "",
                                "arguments": "", "finished": False
                            })

                        entry = tool_chunks_buffer[idx]
                        if tcd.get("id"):
                            entry["id"] = tcd["id"]
                        if tcd.get("function", {}).get("name"):
                            entry["name"] = tcd["function"]["name"]
                        if tcd.get("function", {}).get("arguments"):
                            entry["arguments"] += tcd["function"]["arguments"]

                        # DeepSeek 用 finish_reason="tool_calls" 表示结束
                        if finish_reason == "tool_calls":
                            entry["finished"] = True

                # ── 2. 正文文本 ──
                c = delta.get("content", "")
                if c:
                    full_text += c
                    # 发送正文片段给 UI
                    self.chunk_received.emit(c)

                    # ── 3. [PERM:...] 降级扫描 ──
                    scanned = scan_permissions(full_text)
                    new_perms = {
                        k: v for k, v in scanned.items()
                        if k not in perm_seen_local
                    }
                    # 如果已设置"总是允许"，记录日志后仍弹卡片（确保执行）
                    for k in scanned:
                        status = check_already(k)
                        if status == "granted":
                            print(f"[DBG] [PERM:{k}] already granted, still showing card for execution", file=sys.stderr)

                    if new_perms:
                        perm_seen_local.update(new_perms.keys())
                        self._current_perms = new_perms
                        self._text_before_perm = strip_permissions(full_text)

                        self.perm_requested.emit(new_perms)
                        self._paused = True
                        self._interrupted = True
                        self.perm_interrupted.emit(self._text_before_perm, new_perms)

                        while self._paused and not self._should_stop:
                            QThread.msleep(100)

                        if self._should_stop:
                            break
                        break  # 需要重新调用 API

                # ── 4. 检测工具调用完成 ──
                if finish_reason == "tool_calls" or (
                    has_seen_tools and all(e["finished"] for e in tool_chunks_buffer)
                ):
                    # 解析完整的 tool_calls
                    parsed_calls = []
                    for entry in tool_chunks_buffer:
                        if entry["name"]:
                            try:
                                args_json = json.loads(entry["arguments"]) \
                                    if entry["arguments"] else {}
                            except json.JSONDecodeError:
                                args_json = {}

                            parsed_calls.append({
                                "id": entry["id"] or f"call_{self._tool_call_id_counter}",
                                "name": entry["name"],
                                "arguments": args_json,
                            })
                            self._tool_call_id_counter += 1

                    if parsed_calls:
                        self._pending_tool_calls = parsed_calls
                        # 保存中断前的正文（如有）
                        self._text_before_perm = strip_permissions(full_text)
                        # 通知主线程显示并行授权卡片
                        self.tool_calls_received.emit(parsed_calls)
                        # 进入暂停等待状态
                        self._paused = True
                        self._interrupted = True

                        while self._paused and not self._should_stop:
                            QThread.msleep(100)

                        if self._should_stop:
                            break
                        break  # 主线程会调用 set_tool_results 后重启 run

                # ── 5. 正常结束检测 ──
                elif finish_reason is not None and finish_reason != "tool_calls":
                    if not self._interrupted:
                        self.finished.emit(full_text)
                    return

                # 降级模式切换：如果启用 tools 但连续多 chunk 无 tool_calls，
                # 且正文中出现 [PERM:...] 标记，说明模型可能不支持 tools
                if self._tool_mode_active and not has_seen_tools:
                    no_tool_chunk_count += 1
                    if no_tool_chunk_count > 10 and "[PERM:" in full_text:
                        # 自动降级到标记模式，下次不再发送 tools 参数
                        self._tool_mode_active = False

            # 流正常结束
            if not self._interrupted:
                self.finished.emit(full_text)

        except requests.exceptions.RequestException as ex:
            if not self._interrupted:
                self.error.emit(f"AI 回复失败：{ex}")
        except Exception as ex:
            if not self._interrupted:
                self.error.emit(f"AI 调用异常：{ex}")
