# -*- coding: utf-8 -*-
"""
DebateClaw 插件
================
辩论聊天助手 — 类 vibe-coding 的辩论对话界面。
支持引用项目文件、资料池文件、框架文件，
通过 📎 按钮或 @ 触发选择，发送时结构化传给 AI。
"""

import datetime
import html
import json, os, sys

# 插件自身的 workers/ 模块：注册到 sys.modules['workers.*'] 下，
# 使原有全部 from workers.xxx import yyy 懒导入语句无需改动即可工作。
_plugin_root = os.path.dirname(os.path.abspath(__file__))
_plugin_workers = os.path.join(_plugin_root, 'workers')
import importlib.util as _iutil
for _mname, _fname in [
    ('ai_reply_worker', 'ai_reply_worker.py'),
    ('ai_worker', 'ai_worker.py'),
    ('permission_handler', 'permission_handler.py'),
    ('memory_handler', 'memory_handler.py'),
    ('diff_widget', 'diff_widget.py'),
    ('search_worker', 'search_worker.py'),
    ('execute_sandbox', 'execute_sandbox.py'),
    ('table_card', 'table_card.py'),
]:
    _mpath = os.path.join(_plugin_workers, _fname)
    if os.path.exists(_mpath):
        _spec = _iutil.spec_from_file_location(f'workers.{_mname}', _mpath)
        if _spec and _spec.loader:
            _mod = _iutil.module_from_spec(_spec)
            sys.modules[f'workers.{_mname}'] = _mod
            _spec.loader.exec_module(_mod)

# 处理 memory_vector 子包
_mv_dir = os.path.join(_plugin_workers, 'memory_vector')
if os.path.isdir(_mv_dir):
    # memory_vector 本身作为包注册
    _mv_init = os.path.join(_mv_dir, '__init__.py')
    if os.path.exists(_mv_init):
        _spec = _iutil.spec_from_file_location('workers.memory_vector', _mv_init)
        if _spec and _spec.loader:
            _mod = _iutil.module_from_spec(_spec)
            sys.modules['workers.memory_vector'] = _mod
            _spec.loader.exec_module(_mod)
    # 子模块 indexer
    _mv_idx = os.path.join(_mv_dir, 'indexer.py')
    if os.path.exists(_mv_idx):
        _spec = _iutil.spec_from_file_location('workers.memory_vector.indexer', _mv_idx)
        if _spec and _spec.loader:
            _mod = _iutil.module_from_spec(_spec)
            sys.modules['workers.memory_vector.indexer'] = _mod
            _spec.loader.exec_module(_mod)

# 从已注册的模块中提取常用名（供模块级直接使用）
from workers.ai_reply_worker import start_ai_reply
from workers.permission_handler import _PERM_LABELS

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QTextBrowser, QFrame, QScrollArea,
    QSizePolicy, QPushButton,
)
from PyQt5.QtCore import Qt, QTimer, QPoint, pyqtSignal, QSize
from PyQt5.QtGui import QFont
from workers.plugin_manager import get_api

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
THEME_DIR = os.path.join(PLUGIN_DIR, "theme")

# ── DeepSeek 计价（¥ / 1M tokens，硬编码常量） ──
_PRICE_INPUT_PER_M = 0.14
_PRICE_OUTPUT_PER_M = 0.28

# ─────────────────────────────────────────────
#  主题 QSS 加载
# ─────────────────────────────────────────────

def _load_theme_qss() -> str:
    """加载 QSS 模板并用当前主题色替换 @ 占位符。"""
    cfg_path = os.path.normpath(os.path.join(PLUGIN_DIR, "..", "..", "config", "config.json"))
    theme = "notion_dark"
    try:
        with open(cfg_path) as f:
            theme = json.load(f).get("theme", "notion_dark")
    except Exception:
        pass
    qss_file = os.path.join(THEME_DIR, "debate_claw_light.qss" if "light" in theme.lower() else "debate_claw.qss")
    try:
        with open(qss_file) as f:
            qss = f.read()
    except Exception:
        return ""
    c = _detect_html_colors()
    for key in ("body", "text", "subtext", "surface", "muted", "accent",
                "user_text", "border", "overlay"):
        qss = qss.replace(f"@{key}", c.get(key, ""))
    return qss

# ─────────────────────────────────────────────
#  文件引用 API 辅助
# ─────────────────────────────────────────────

def _get_project_files(api):
    """列出项目根目录的文件"""
    proot = api.get_current_project_path()
    if not proot:
        return []
    out = []
    for fname in os.listdir(proot):
        fpath = os.path.join(proot, fname)
        if os.path.isfile(fpath) and not fname.startswith("."):
            out.append(dict(name=fname, path=os.path.relpath(fpath, proot), source="project", source_label="项目文件"))
    return out

def _get_pool_files(api):
    """列出资料池文件"""
    out = []
    try:
        for f in (api.list_files() or []):
            if isinstance(f, dict):
                n, p = f.get("name", f.get("path", "")), f.get("path", "")
            else:
                n = p = str(f)
            out.append(dict(name=n, path=p, source="pool", source_label="资料池"))
    except Exception:
        pass
    return out

def _get_framework_files(api):
    """列出框架/辩稿文件"""
    out = []
    try:
        di = api.get_debate_info() or {}
        title = di.get("title", "当前辩题")
        if api.get_framework_data():
            out.append(dict(name=f"{title} - 辩论框架", path="framework://current", source="framework", source_label="框架文件"))
        for side, label in [("pro", "正方一辩稿"), ("con", "反方一辩稿")]:
            c = api.get_speech_content(side)
            if c:
                out.append(dict(name=f"{title} - {label}", path=f"speech://{side}", source="framework", source_label="框架文件"))
    except Exception:
        pass
    return out


_READABLE_EXTS = {".md", ".txt", ".json", ".csv", ".yaml", ".yml",
                  ".html", ".htm", ".py", ".js", ".ts", ".xml", ".log"}
def _build_project_context(api) -> str:
    """构建项目上下文字符串，包含项目路径 + 可读文件清单 + 资料池文件清单。"""
    parts = []
    proot = api.get_current_project_path()
    if proot:
        parts.append(f"## 当前项目\n\n项目目录: `{proot}`\n")
        # 扫描项目文件（仅可读类型）
        proj_files = []
        for fname in sorted(os.listdir(proot)):
            fpath = os.path.join(proot, fname)
            if (os.path.isfile(fpath) and not fname.startswith(".")
                    and os.path.splitext(fname)[1].lower() in _READABLE_EXTS):
                size = os.path.getsize(fpath)
                proj_files.append(f"  - `{fname}` ({_fmt_size(size)})")
        if proj_files:
            parts.append("项目可读文件:\n" + "\n".join(proj_files))
        else:
            parts.append("项目可读文件: (无)")
    else:
        parts.append("## 当前项目\n\n(未打开项目)")

    # 资料池文件
    pool_files = _get_pool_files(api)
    if pool_files:
        pool_lines = [f"  - `{f['name']}`" for f in pool_files]
        parts.append("资料池文件:\n" + "\n".join(pool_lines))
    else:
        parts.append("资料池文件: (空)")

    return "\n\n".join(parts)

def _fmt_size(size: int) -> str:
    if size < 1024: return f"{size}B"
    if size < 1024*1024: return f"{size//1024}KB"
    return f"{size/(1024*1024):.1f}MB"


def _build_paragraph_context(mw, safe_write_mode: bool = False) -> str:
    """从一辩稿编辑器获取段落结构上下文，用于注入 AI system prompt。

    Args:
        mw: 主窗口实例
        safe_write_mode: 是否处于安全写入模式（禁用 file_write）

    Returns:
        str: 段落结构摘要 + [DIFF] 格式说明（安全模式下始终返回格式说明）。
    """
    parts = []
    try:
        speech_mgr = getattr(mw, '_speech_mgr', None)
        if speech_mgr:
            side = speech_mgr.get_current_side()
            ctx = speech_mgr.get_paragraph_context_text(side)
            if not ctx or "尚未结构化" in ctx:
                other = "con" if side == "pro" else "pro"
                ctx = speech_mgr.get_paragraph_context_text(other)
            if ctx and "尚未结构化" not in ctx:
                parts.append(f"## 一辩稿段落结构\n\n{ctx}\n\n")
    except Exception:
        pass

    # ── 安全模式强制说明（无论是否有段落数据）──
    if safe_write_mode:
        parts.append(
            "## ⚠️ 安全写入模式 —— 禁止调用 file_write，只能使用 [DIFF] 格式\n\n"
            "**你目前处于安全写入模式。该模式下 file_write 工具已被系统禁用。**\n"
            "你不能用 file_write 写入任何文件。如果尝试调用，系统会返回错误。\n\n"
            "你**唯一**能做的修改方式就是输出 [DIFF] 标记块。\n"
            "用户会在对话中看到可视化修改卡片，审核通过后系统自动应用。\n\n"
            "[DIFF] 的正确格式如下：\n"
            '```\n[DIFF:标题="修改说明" +N -M]\n'
            '- 需要删除或替换的一整行原文\n'
            '+ 修改后的新内容（一行）\n'
            '+ 如果有多个新增行，每行都加 + \n'
            '  保持不变的行用空格开头\n'
            '[/DIFF]\n```\n\n'
            "核心规则：\n"
            "1. 每行必须以 `- `（删除）、`+ `（新增）或 `  `（空格·不变）开头\n"
            "2. `- `和`+ `后有且只有一个空格\n"
            "3. 所有修改建议**必须**放在 [DIFF]...[/DIFF] 块内，不要在块外用文字解释\n"
            "4. 可以输出多个独立 [DIFF] 块，每个块对应一处修改\n"
            "5. 可选的 `段落=\"段落ID\"` 字段用于精确替换一辩稿的指定段落\n\n"
            "错误示例（不要这样输出）：\n"
            '```\n[DIFF]我建议把这段改成...[/DIFF]\n```\n'
            "（缺少行前缀、没有标题、内容在块外）\n"
        )
        return "\n".join(parts)

    # ── 非安全模式：只是建议优先用 [DIFF] ──
    parts.append(
        "**重要：修改一辩稿时优先使用 [DIFF] 格式而不是 file_write 工具**\n"
        "\n你可以在对话回复中嵌入段落级修改建议，用 [DIFF] 标记块让用户逐条审核后再应用。"
        "这比直接写入文件更安全，用户可以决定是否接受每处修改。\n"
        "\n[DIFF] 格式如下：\n"
        '```\n[DIFF:标题="描述" +新增行数 -删除行数 段落="段落ID"]'
        '\n- 原文中将被替换的句子或段落'
        '+ 替换后的新内容'
        '  （保留不变的上下文行，可选）'
        '[/DIFF]\n```\n'
        "\n其中「段落ID」必须使用上方列出的 id 值（如 opening、definition 等）。"
        "注意：段落修改请使用 [DIFF] 格式，不要直接调用 file_write 修改一辩稿文件，"
        "因为这样会跳过用户的审核流程。\n"
    )
    return "\n".join(parts) if parts else ""


def _apply_accepted_diff(mw, paragraph_id: str | None, accepted_text: str):
    """接受 diff 后更新一辩稿编辑器内容。

    两种模式：
    1. 有 paragraph_id → 精确替换对应段落并重建全文
    2. 无 paragraph_id / 段落 ID 未命中 → 将 accepted_text 作为全文替换当前活跃侧编辑器

    Args:
        mw: 主窗口实例
        paragraph_id: 目标段落 ID（可为 None）
        accepted_text: DiffCard.get_accepted_content() 返回的文本
    """
    speech_mgr = getattr(mw, '_speech_mgr', None)
    if not speech_mgr or not accepted_text:
        return

    # ── 有段落 ID：精确替换 ──
    if paragraph_id:
        new_texts = [t.strip() for t in accepted_text.split('\n\n') if t.strip()]
        if new_texts:
            from workers.speech_editor.paragraph_manager import (
                find_paragraph_by_id, split_content_to_paragraphs,
            )
            applied = False
            for side in ("pro", "con"):
                paras = speech_mgr.get_paragraphs(side)
                # ── 段落数据为空时即时从编辑器内容+结构树重新生成 ──
                if not paras:
                    try:
                        edit = (speech_mgr.edit_pro_speech if side == "pro"
                                else speech_mgr.edit_con_speech)
                        content = edit.toPlainText().strip()
                        leaf_slugs = mw._structure_mgr.get_leaf_slugs(side)
                        if content and leaf_slugs:
                            paras = split_content_to_paragraphs(content, leaf_slugs)
                            # 写回 speech_mgr 供后续使用
                            if side == "pro":
                                speech_mgr.paragraphs_pro = paras
                            else:
                                speech_mgr.paragraphs_con = paras
                    except Exception as ex:
                        print(f"[Diff] regenerate paragraphs error: {ex}",
                              file=sys.stderr)
                if find_paragraph_by_id(paras, paragraph_id):
                    speech_mgr.apply_paragraph_diff(side, paragraph_id, new_texts)
                    if side == "con":
                        speech_mgr.speech_tabs.setCurrentIndex(1)
                    applied = True
                    break
            if applied:
                return
            # 段落 ID 未命中 → 降级到全文替换（打印警告日志）
            print(f"[Diff] accept: paragraph_id='{paragraph_id}' not found in "
                  f"either side, falling back to full-text replacement",
                  file=sys.stderr)

    # ── 无段落 ID / 段落 ID 未命中：全文替换两侧编辑器（尝试两侧，取有内容的那侧）──
    new_text = accepted_text.strip()
    if not new_text or len(new_text) < 10:
        return
    for side in ("pro", "con"):
        edit = speech_mgr.edit_pro_speech if side == "pro" else speech_mgr.edit_con_speech
        if not edit:
            continue
        current = edit.toPlainText().strip()
        if new_text != current:
            edit.setPlainText(new_text)
            speech_mgr._apply_glossary_highlights(edit)
            label = speech_mgr._side_label(side)
            mw._update_status(f"已根据 DIFF 更新{label}一辩稿内容")
            if side == "con":
                speech_mgr.speech_tabs.setCurrentIndex(1)
            return


def _undo_accepted_diff(mw, undo_info: dict):
    """撤销一次段落接受：恢复段落原始内容并重建编辑器。

    Args:
        mw: 主窗口实例
        undo_info: dict with keys:
            - side: "pro" or "con"
            - para_id: 段落 ID
            - old_texts: list[str] 原始 texts 数组
    """
    speech_mgr = getattr(mw, '_speech_mgr', None)
    if not speech_mgr:
        return
    side = undo_info.get("side")
    para_id = undo_info.get("para_id")
    old_texts = undo_info.get("old_texts")
    if not side or not para_id or old_texts is None:
        return
    from workers.speech_editor.paragraph_manager import (
        find_paragraph_by_id, rebuild_content_from_paragraphs,
    )
    paras = speech_mgr.get_paragraphs(side)
    p = find_paragraph_by_id(paras, para_id)
    if p:
        p["texts"] = old_texts
        content = rebuild_content_from_paragraphs(paras)
        edit = speech_mgr.edit_pro_speech if side == "pro" else speech_mgr.edit_con_speech
        edit.setPlainText(content)
        speech_mgr._apply_glossary_highlights(edit)
        label = speech_mgr._side_label(side)
        mw._update_status(f"已撤销段落 [{para_id}] 的修改")
        if side == "con":
            speech_mgr.speech_tabs.setCurrentIndex(1)


def _read_file_content(api, fi):
    """按 file_info 读取文件内容"""
    src, path = fi.get("source"), fi.get("path", "")
    try:
        if src == "project":
            return api.read_file_in_project(path) or "(空)"
        if src == "pool":
            return api.get_file_content(path) or "(空)"
        if src == "framework":
            if path.startswith("speech://"):
                return api.get_speech_content(path.split("://")[1]) or "(空)"
            if path.startswith("framework://"):
                nodes = api.get_framework_data()
                return "\n".join(f"- {n.get('text','')}" for n in (nodes or [])) or "(框架无节点)"
    except Exception:
        pass
    return "(读取失败)"

def _build_file_block(files, api):
    """将已选文件拼成发送块"""
    if not files:
        return ""
    lines = ["\n━━━ 引用文件 ━━━"]
    for f in files:
        c = _read_file_content(api, f)
        lines.append(f"\n📎 [{f.get('name')}]({f.get('source_label')})\n{'─'*30}\n{c.strip()}")
    lines.append("━" * 30)
    return "\n".join(lines)

# ─────────────────────────────────────────────
#  文件图标 & 主题色检测
# ─────────────────────────────────────────────

_FILE_ICON_MAP = {
    ".docx": "📄", ".doc": "📄",
    ".xlsx": "📊", ".xls": "📊", ".csv": "📊",
    ".pdf": "📕",
    ".txt": "📝", ".md": "📝",
    ".json": "📋",
    ".py": "🐍", ".js": "🐍",
    ".png": "🖼", ".jpg": "🖼", ".jpeg": "🖼", ".gif": "🖼", ".svg": "🖼",
}

def _get_file_icon(name: str) -> str:
    return _FILE_ICON_MAP.get(os.path.splitext(name)[1].lower(), "📎")

def _format_file_size(fi: dict, api) -> str:
    """获取文件可读大小，虚拟文件返回"—" """
    src, path = fi.get("source"), fi.get("path", "")
    real_path = None
    if src == "project":
        p = api.get_current_project_path()
        if p: real_path = os.path.join(p, path)
    elif src == "pool":
        p = api.get_current_project_path()
        if p: real_path = os.path.join(p, "data_pool", path)
    if real_path and os.path.isfile(real_path):
        b = os.path.getsize(real_path)
        for u in ("B", "KB", "MB"):
            if b < 1024: return f"{b:.1f} {u}"
            b /= 1024
        return f"{b:.1f} GB"
    return "—"

# ── HTML 气泡主题色（与 Qt QSS 保持一致）──

def _detect_html_colors():
    """通过 components.theme_colors.tc() 获取当前主题颜色。"""
    try:
        from components.theme_colors import tc as _tc
        is_light = _tc("base", "#1e1e2e") >= "#999999"  # 粗略判断浅色
    except Exception:
        # 降级：从 config.json 直接读取主题
        cfg_path = os.path.normpath(os.path.join(PLUGIN_DIR, "..", "..", "config", "config.json"))
        is_light = False
        try:
            with open(cfg_path) as f:
                is_light = "light" in json.load(f).get("theme", "").lower()
        except Exception:
            pass

        if is_light:
            return dict(
                body="#FFFFFF", text="#37352F", subtext="#9B9A97",
                surface="#E8E8E6", muted="#C0BFBF",
                accent="#2E6DDE",
                user_bg="#2E6DDE", user_text="#FFFFFF",
                ai_bg="#F0F0F0", ai_text="#37352F",
                border="#EDEDEB", overlay="#EDEDEB",
                warn_bg="rgba(166,227,161,0.1)", warn_text="#2e7d32",
            )
        return dict(
            body="#1e1e2e", text="#cdd6f4", subtext="#585b70",
            surface="#313244", muted="#6c7086",
            accent="#2E6DDE",
            user_bg="#2E6DDE", user_text="#FFFFFF",
            ai_bg="#313244", ai_text="#cdd6f4",
            border="#45475a", overlay="#45475a",
            warn_bg="rgba(166,227,161,0.1)", warn_text="#a6e3a1",
        )

    # 通过 tc() 获取动态色值
    short_tc = lambda k: _tc(k, {"base": "#1e1e2e", "surface": "#1E2025", "text": "#E0E0E0",
        "subtext": "#A0A0A0", "muted": "#6B6B6B", "accent": "#2E6DDE",
        "overlay": "#2C2E36", "success": "#2EA043"}.get(k, "#181A1E"))
    return dict(
        body=short_tc("base"),
        text=short_tc("text"),
        subtext=short_tc("subtext"),
        surface=short_tc("surface"),
        muted=short_tc("muted"),
        accent=short_tc("accent"),
        user_bg=short_tc("accent"),
        user_text=short_tc("base") if is_light else "#FFFFFF",
        ai_bg=short_tc("surface"),
        ai_text=short_tc("text"),
        border=short_tc("overlay"),
        overlay=short_tc("overlay"),
        warn_bg="rgba(46,160,67,0.12)",
        warn_text=short_tc("success"),
    )

# ── HTML 消息构建函数 ──

_FONT_FAMILY = '"HarmonyOS Sans SC", -apple-system, sans-serif'
_HTML_HEADER = (f'<html><head><meta charset="utf-8"/></head>'
                f'<body style="margin:0;padding:8px;'
                f'font-family:{_FONT_FAMILY};font-size:11pt;'
                f'line-height:1.6;">')
_HTML_FOOTER = '</body></html>'
_WELCOME_MSG = ("🤖 Claw 助手 · 开始对话<br/>"
                "输入辩论相关问题开始交流")

def _makesys(text):
    """系统消息 HTML 块（居中、灰色）。"""
    return (f'<p align="center" style="color:{_detect_html_colors()["subtext"]};'
            f'font-size:10pt;padding:8px 16px;margin:4px 0;">{text}</p>')

def _makeuser(text, file_infos):
    """用户消息 HTML 块（靠右、蓝色背景气泡）。"""
    c = _detect_html_colors()
    safe = html.escape(text).replace("\n", "<br/>")
    cards_html = ""
    if file_infos:
        items = []
        for fi in file_infos:
            nm = fi.get("name", "")
            display = nm if len(nm) <= 5 else nm[:4] + "…"
            icon = _get_file_icon(nm)
            items.append(
                f'<td style="width:80px;background:{c["overlay"]};'
                f'padding:6px 8px;text-align:center;vertical-align:top;">'
                f'<div style="font-size:13pt;">{icon}</div>'
                f'<div style="font-size:9pt;color:{c["text"]};">{html.escape(display)}</div>'
                f"</td>"
            )
        cards_html = f'<table cellpadding="2" cellspacing="2" style="margin-top:6px;"><tr>{"".join(items)}</tr></table>'
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:4px 0;">'
        f'<tr><td width="12%"></td>'
        f'<td style="background:{c["user_bg"]};color:{c["user_text"]};'
        f'padding:10px 14px;font-size:11pt;line-height:1.6;">'
        f"{safe}{cards_html}</td></tr></table>"
    )

def _makeai(text, colors=None, extra_bottom=""):
    """AI 消息 HTML 块（靠左、全宽透明背景）。"""
    c = colors or _detect_html_colors()
    body = (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:4px 0;">'
        f'<tr><td style="background:transparent;color:{c["ai_text"]};'
        f'padding:10px 14px;font-size:11pt;line-height:1.6;">'
        f"{text}</td></tr></table>"
    )
    if extra_bottom:
        body += (f'<p style="color:{c["subtext"]};font-size:9pt;padding:0 4px;'
                 f'margin:2px 0 6px;">{extra_bottom}</p>')
    return body


# ─────────────────────────────────────────────
#  文件标签栏 _FileTagBar
# ─────────────────────────────────────────────

class _FileTagBar(QFrame):
    """已选文件紧凑标签行"""
    tagRemoved = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("clawFileTagBar")
        self.setFixedHeight(32)
        self._lo = QHBoxLayout(self)
        self._lo.setContentsMargins(8, 2, 8, 2)
        self._lo.setSpacing(4)
        self._lo.addStretch()
        self._tags = []

    def add_tag(self, idx, name):
        t = QFrame(objectName="clawFileTag")
        lo = QHBoxLayout(t); lo.setContentsMargins(4,1,4,1); lo.setSpacing(4)
        lb = QLabel(name, objectName="clawFileTagLabel")
        lb.setFont(QFont("HarmonyOS Sans SC", 10))
        cx = QLabel("✕", objectName="clawFileTagClose")
        cx.setFont(QFont("HarmonyOS Sans SC", 10))
        cx.mousePressEvent = lambda e, i=idx: self.tagRemoved.emit(i)
        lo.addWidget(lb); lo.addWidget(cx)
        self._lo.insertWidget(self._lo.count() - 1, t)
        self._tags.append(t)

    def clear_tags(self):
        for t in self._tags:
            t.deleteLater()
        self._tags.clear()

# ─────────────────────────────────────────────
#  文件选择浮层 _FileSelectorPopover
# ─────────────────────────────────────────────

class _FileSelectorPopover(QFrame):
    """Popover 浮层，按分组列出可引用文件，自动调整高度并支持滚动"""
    fileSelected = pyqtSignal(dict)

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self._api = api
        self._MAX_HEIGHT = 400

        self.setObjectName("clawFilePopover")
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setStyleSheet("QFrame#clawFilePopover{background:#1e1e2e;border:1px solid #343640;border-radius:8px;}")
        self.setFixedWidth(280)

        self._lo = QVBoxLayout(self)
        self._lo.setContentsMargins(8, 8, 8, 8)
        self._lo.setSpacing(2)

        title = QLabel("引用文件", objectName="clawPopoverTitle")
        title.setFont(QFont("HarmonyOS Sans SC", 10, QFont.Bold))
        title.setStyleSheet("color:#cdd6f4;background:transparent;padding:4px 0;")
        self._lo.addWidget(title)

        # 滚动区域包裹文件列表
        self._scroll_area = QScrollArea(objectName="clawPopoverScroll")
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll_area.setStyleSheet(
            "QScrollArea#clawPopoverScroll{background:transparent;border:none;}"
            "QScrollBar:vertical{background:transparent;width:4px;margin:0;}"
            "QScrollBar::handle:vertical{background:#3A3D4A;border-radius:2px;min-height:30px;}"
            "QScrollBar::handle:vertical:hover{background:#6B6B6B;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )

        self._scroll_content = QWidget()
        self._scroll_content.setStyleSheet("background:transparent;")
        self._items_area = QVBoxLayout(self._scroll_content)
        self._items_area.setContentsMargins(0, 0, 0, 0)
        self._items_area.setSpacing(1)
        self._items_area.addStretch()

        self._scroll_area.setWidget(self._scroll_content)
        self._lo.addWidget(self._scroll_area, stretch=1)

    def refresh(self):
        # 清空 items_area（保留最后的 stretch）
        while self._items_area.count() > 1:
            it = self._items_area.takeAt(0)
            if it.widget(): it.widget().deleteLater()

        api = self._api
        groups = [
            ("项目文件", _get_project_files(api)),
            ("资料池", _get_pool_files(api)),
            ("框架文件", _get_framework_files(api)),
        ]
        count = 0
        for glabel, flist in groups:
            if not flist:
                continue
            gl = QLabel(glabel)
            gl.setFont(QFont("HarmonyOS Sans SC", 10))
            gl.setStyleSheet("color:#6c7086;background:transparent;padding:4px 0 2px 0;")
            self._items_area.insertWidget(self._items_area.count() - 1, gl)
            for fi in flist:
                self._items_area.insertWidget(self._items_area.count() - 1, self._mk_item(fi))
                count += 1
        if count == 0:
            e = QLabel("暂无可用文件")
            e.setFont(QFont("HarmonyOS Sans SC", 10))
            e.setStyleSheet("color:#6c7086;background:transparent;padding:8px;")
            e.setAlignment(Qt.AlignCenter)
            self._items_area.insertWidget(self._items_area.count() - 1, e)

    def _mk_item(self, fi):
        f = QFrame(objectName="clawFileItem")
        f.setStyleSheet("QFrame#clawFileItem{border-radius:4px;padding:4px 6px;}"
                        "QFrame#clawFileItem:hover{background:rgba(52,54,64,0.5);}")
        lo = QHBoxLayout(f); lo.setContentsMargins(6,4,6,4)
        lb = QLabel(fi.get("name", ""))
        lb.setFont(QFont("HarmonyOS Sans SC", 10))
        lb.setStyleSheet("background:transparent;color:#cdd6f4;")
        lb.setWordWrap(True)
        lo.addWidget(lb, 1)
        f.mousePressEvent = lambda e, fi2=fi: self._pick(fi2)
        return f

    def _pick(self, fi):
        self.fileSelected.emit(fi)
        self.close()

    def show_at(self, anchor):
        self.refresh()
        # 计算最佳高度：标题 + 实际内容，最多不超过 _MAX_HEIGHT
        content_h = self._scroll_content.sizeHint().height()
        margins = self._lo.contentsMargins()
        title_label = self._lo.itemAt(0).widget()
        title_h = title_label.sizeHint().height() if title_label else 0
        ideal_h = title_h + content_h + margins.top() + margins.bottom() + 8
        self.setFixedHeight(min(ideal_h, self._MAX_HEIGHT))
        self.move(anchor.mapToGlobal(QPoint(0, anchor.height() + 4)))
        self.show()

# ─────────────────────────────────────────────
#  聊天消息元素
# ─────────────────────────────────────────────

# ── 旧气泡渲染（已移除，改用 _makesys / _makeuser / _makeai HTML 构建函数）──
# ─────────────────────────────────────────────
#  主面板

# ─────────────────────────────────────────────
#  主面板
# ─────────────────────────────────────────────

_chat_layout_ref = None
_claw_state = {}     # 面板就绪后注册到这里
_claw_pending = []   # 面板未就绪时暂存待处理文件
_conversation_history = []  # [{role, content}]

def add_file_to_session(file_path: str, file_name: str):
    """供外部调用的入口：从项目浏览器等来源添加文件到当前会话"""
    fi = dict(name=file_name, path=file_path, source="project", source_label="项目文件")
    state = _claw_state.get("debate_claw")
    if not state:
        # 面板尚未创建，暂存到待处理队列
        for f in _claw_pending:
            if f.get("path") == file_path:
                return
        _claw_pending.append(fi)
        return
    for f in state["files"]:
        if f.get("path") == file_path:
            return
    state["files"].append(fi)
    state["tag_bar"].add_tag(len(state["files"]) - 1, file_name)
    state["count_label"].setText(f"附件: {len(state['files'])}")

def create_claw_panel():
    global _chat_layout_ref
    panel = QWidget(objectName="clawPanel")
    ml = QVBoxLayout(panel); ml.setContentsMargins(0,0,0,0); ml.setSpacing(0)

    # ── 标题栏 ──
    tb = QFrame(objectName="clawTitleBar")
    tl = QHBoxLayout(tb); tl.setContentsMargins(16,0,12,0)
    ttl = QLabel("🦞  DebateClaw", objectName="clawTitleLabel")
    ttl.setFont(QFont("HarmonyOS Sans SC", 10, QFont.Bold))
    tl.addWidget(ttl)

    # ── 安全写入模式开关（标题栏图标按钮）──
    # 从设置页读取默认状态
    _safe_write_default = False
    try:
        _perm_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "permissions.json")
        if os.path.exists(_perm_path):
            with open(_perm_path, "r", encoding="utf-8") as _pf:
                _perm_data = json.load(_pf)
            _safe_write_default = _perm_data.get("safe_write_mode", {}).get("enabled", False)
    except Exception:
        pass
    _safe_write_mode = [_safe_write_default]  # 闭包可变引用

    tl.addStretch()

    api = get_api()
    mw = api.mw  # 主窗口引用（供闭包中的 _apply_accepted_diff 使用）

    cfg_btn = _build_buttons([dict(text="🔧", tooltip="设置")], api)[0]; cfg_btn.clicked.connect(lambda: _show_settings_dialog(panel)); tl.addWidget(cfg_btn)
    swm_cfg = dict(text="🔒" if _safe_write_default else "🔓", tooltip="安全写入模式：开启时 AI 不可直接写入文件，只能输出 [DIFF] 修改建议")
    _swm_btn = _build_buttons([swm_cfg], api)[0]; _swm_btn.clicked.connect(lambda: _toggle_safe_write_mode()); tl.addWidget(_swm_btn)
    clr_btn = _build_buttons([dict(text="🗑", tooltip="清空对话")], api)[0]; tl.addWidget(clr_btn)

    def _toggle_safe_write_mode():
        _safe_write_mode[0] = not _safe_write_mode[0]
        _swm_btn.setText("🔒" if _safe_write_mode[0] else "🔓")
        _swm_btn.setToolTip(
            "安全写入模式已开启 - AI 不能直接写入文件，只能输出 [DIFF] 修改建议"
            if _safe_write_mode[0] else
            "安全写入模式：关闭时 AI 不可直接写入文件，只能输出 [DIFF] 修改建议"
        )
        # 更新状态提示
        if _safe_write_mode[0]:
            _add_system_notification("🔒 安全写入模式已开启\nAI 将使用 [DIFF] 格式输出修改建议，您可逐条审核后再接受")
        else:
            _add_system_notification("🔓 安全写入模式已关闭\nAI 可以正常调用 file_write 工具")
    ml.addWidget(tb)

    # ── 聊天区（QWidget 气泡容器）──
    sa = QScrollArea(objectName="clawChatScroll")
    sa.setFrameShape(QFrame.NoFrame)
    sa.setWidgetResizable(True)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    cw = QWidget(objectName="clawChatWidget")
    cl = QVBoxLayout(cw); cl.setContentsMargins(12,4,12,4); cl.setSpacing(4)
    cl.setAlignment(Qt.AlignTop)
    sa.setWidget(cw); ml.addWidget(sa, 1)

    _colors = _detect_html_colors()
    # 流式状态
    _streaming_segments = []    # [{"seg": (type,...), "widget": QWidget}, ...]
    _streaming_text = ""        # 当前累积的 AI 全文
    _streaming_label = None     # token 用量 QLabel 引用
    _streaming_wrapper = None   # 流式气泡的外层 QWidget（以便定位）

    # 思考指示器状态（L2 三点动画 + L3 计时）
    _thinking_widget = None     # 思考指示器 QFrame
    _thinking_dots = None       # 动画三点 QLabel
    _thinking_elapsed = None    # 计时 QLabel
    _thinking_dot_timer = None  # 三点动画 QTimer
    _thinking_elapsed_timer = None  # 计时 QTimer
    _thinking_elapsed_secs = 0

    # 全局「全部接受」按钮
    _global_accept_btn = None   # QPushButton, 在气泡底部（流式结束后可见）

    # 内容容器（隔离静态组件与动态段，确保段索引从 0 开始）
    _content_container = None   # QWidget, 所有段 text/table/diff 放入此容器的布局

    # 流式状态（供 _on_btn_click / _on_interrupt / _on_ai_finished 共享）
    _state = dict(full_text="", streaming=False)

    # 撤销数据（接受时保存段落原内容，撤销时恢复）
    _undo_snapshots = {}        # {card_id: {"side": str, "para_id": str, "old_texts": list}}

    def _scroll_bottom():
        QTimer.singleShot(10, lambda: sa.verticalScrollBar().setValue(
            sa.verticalScrollBar().maximum()))

    # ── 气泡构建辅助 ──
    def _make_bubble_frame(object_name, bg_color, border_color=None):
        """创建带圆角的 QFrame 容器。padding 由 layout margins 控制。"""
        f = QFrame(objectName=object_name)
        qss = f"QFrame#{object_name}{{background:{bg_color};border-radius:12px;"
        if border_color:
            qss += f"border-left:3px solid {border_color};"
        qss += "}"
        f.setStyleSheet(qss)
        lo = QVBoxLayout(f); lo.setContentsMargins(14, 16, 14, 16); lo.setSpacing(8)
        return f, lo

    class _AutoTB(QTextBrowser):
        """内嵌于气泡的自动高度 QTextBrowser — sizeHint + updateGeometry 驱动。"""
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setReadOnly(True)
            self.setFrameShape(QFrame.NoFrame)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.viewport().setAutoFillBackground(False)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            f = QFont("HarmonyOS Sans SC", 10)
            self.setFont(f)
            self.document().setDocumentMargin(2)

        def sizeHint(self):
            """返回内容所需精确高度，适配 markdown 中不同字号（## 大标题等）。"""
            doc = self.document()
            fm = self.fontMetrics()
            w = self.viewport().width()
            if w < 10:
                w = 400
            doc.setTextWidth(w - 4)

            # 文档引擎的 layout 高度已正确包含不同字号 heading 的行高
            doc_h = doc.size().height()
            # 底部留白：基础字体 descent + 安全边距，给大号字体足够空间
            extra = fm.descent() + 16
            h = int(doc_h + extra)
            return QSize(super().sizeHint().width(), max(h, 24))

        def setMarkdown(self, text):
            super().setMarkdown(text)
            self.updateGeometry()

        def resizeEvent(self, event):
            """宽度变化 → 内容换行改变 → 通知布局重算高度。"""
            super().resizeEvent(event)
            w = self.viewport().width()
            if w > 10:
                self.document().setTextWidth(w - 4)
            self.updateGeometry()

    def _add_user_msg(text, file_infos):
        """添加用户消息气泡（右对齐，内容自适应宽度，最多 85% 功能区）。"""
        f, lo = _make_bubble_frame("clawUserBubble", _colors["user_bg"], _colors["accent"])
        f.setMaximumWidth(int(panel.width() * 0.85))
        lb = QLabel(text)
        lb.setWordWrap(True)
        lb.setStyleSheet(f"color:{_colors['user_text']};background:transparent;font-size:11pt;")
        lo.addWidget(lb)
        if file_infos:
            cards_row = QHBoxLayout(); cards_row.setSpacing(6); cards_row.setContentsMargins(0,6,0,0)
            for fi in file_infos:
                nm = fi.get("name", "")
                display = nm if len(nm) <= 5 else nm[:4] + "…"
                cf = QFrame()
                cf.setStyleSheet(f"QFrame{{background:{_colors['overlay']};border-radius:8px;padding:6px 8px;}}")
                cv = QVBoxLayout(cf); cv.setContentsMargins(0,0,0,0); cv.setSpacing(1)
                ci = QLabel(_get_file_icon(nm)); ci.setStyleSheet("background:transparent;font-size:13pt;")
                cn = QLabel(html.escape(display)); cn.setStyleSheet(f"background:transparent;color:{_colors['text']};font-size:9pt;")
                cv.addWidget(ci, 0, Qt.AlignCenter)
                cv.addWidget(cn, 0, Qt.AlignCenter)
                cards_row.addWidget(cf)
            cards_row.addStretch()
            lo.addLayout(cards_row)
        # 靠右容器（stretch 右对齐，内容自适应宽度，不超过 maxWidth）
        w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(0,2,0,2)
        hl.addStretch(); hl.addWidget(f); hl.addSpacing(12)
        cl.addWidget(w)

    def _add_sys_msg(text):
        """添加系统消息气泡（居中，灰色小字）。"""
        lb = QLabel(text)
        lb.setAlignment(Qt.AlignCenter)
        lb.setWordWrap(True)
        lb.setStyleSheet(f"color:{_colors['subtext']};background:transparent;font-size:10pt;padding:8px 16px;")
        cl.addWidget(lb)

    def _update_bubble_widths():
        """面板 resize / 全屏切换时更新全部气泡宽度，强制 _AutoTB/_TableCard/DiffCard 重算。"""
        pw = panel.width()
        if pw < 200:
            return
        ai_mw = int(pw)
        user_mw = int(pw * 0.85)
        for i in range(cl.count()):
            it = cl.itemAt(i)
            if not it or not it.widget():
                continue
            w = it.widget()
            f = w.findChild(QFrame, "clawAiBubble")
            if f:
                f.setMaximumWidth(ai_mw)
                for tb in f.findChildren(QTextBrowser):
                    tb.updateGeometry()
                for card in f.findChildren(QFrame, "clawTableCard"):
                    card.setMaximumWidth(ai_mw)
                    card.updateGeometry()
                for dc in f.findChildren(QFrame, "clawDiffCard"):
                    dc.setMaximumWidth(ai_mw)
                    dc.updateGeometry()
                continue
            f = w.findChild(QFrame, "clawUserBubble")
            if f:
                f.setMaximumWidth(user_mw)

    # ── Markdown 解析 → 自定义段落（text / table / diff）──

    def _parse_md_segments(text):
        """将 Markdown 拆分为交替的 text/table/diff 段。"""
        from workers.diff_widget import parse_diff_blocks as _parse_diff

        # 预先提取所有完整 DIFF 块，记录其位置范围
        diff_blocks = _parse_diff(text)
        diff_spans = []
        for db in diff_blocks:
            raw_header = db["raw_header"]
            raw_body = db["raw_body"]
            full_tag_start = f"[DIFF:{raw_header}]"
            start = text.find(full_tag_start)
            if start >= 0:
                end = start + len(full_tag_start) + len(raw_body) + len("[/DIFF]")
                diff_spans.append((start, end, db))
            else:
                end = text.find(f"[/DIFF]", text.find(full_tag_start)) + len("[/DIFF]") if f"[/DIFF]" in text[text.find(full_tag_start):] else -1
                diff_spans.append((start, end, db))

        # 排序并合并相邻/重叠的 span
        diff_spans.sort(key=lambda x: x[0])

        # 分割非 DIFF 区域为 text/table 段
        segments = []
        pos = 0
        for ds, de, db in diff_spans:
            if de < 0:
                continue  # 不完整的 DIFF 块跳过
            # 处理前方的普通文本区域
            before = text[pos:ds].strip()
            if before:
                for seg in _split_text_table(before):
                    segments.append(seg)
            # 插入 diff 块
            segments.append(("diff", db))
            pos = de
        # 处理尾部剩余文本
        tail = text[pos:].strip()
        if tail:
            for seg in _split_text_table(tail):
                segments.append(seg)

        return segments or [("text", text)]

    def _split_text_table(text):
        """辅助：将纯文本拆分为 text/table 段列表。"""
        segments = []
        lines = text.split('\n')
        i = 0
        while i < len(lines):
            ln = lines[i].strip()
            if ln.startswith('|') and ln.endswith('|') and '|' in ln[1:-1]:
                headers = [c.strip() for c in ln.split('|')[1:-1]]
                i += 1
                if i < len(lines) and set(lines[i].strip()) <= set('|-: '):
                    i += 1
                rows = []
                while i < len(lines):
                    rs = lines[i].strip()
                    if not (rs.startswith('|') and rs.endswith('|')):
                        break
                    cells = [c.strip() for c in rs.split('|')[1:-1]]
                    rows.append(cells)
                    i += 1
                if headers:
                    segments.append(("table", headers, rows))
            else:
                buf = [lines[i]]
                i += 1
                while i < len(lines):
                    if lines[i].strip().startswith('|'):
                        break
                    buf.append(lines[i])
                    i += 1
                joined = '\n'.join(buf).strip()
                if joined:
                    segments.append(("text", joined))
        return segments

    class _CellText(QTextBrowser):
        """表格单元格——轻量文本显示，sizeHint 返回内容实际高度。"""
        def __init__(self, text, text_color, bold=False, parent=None):
            super().__init__(parent)
            self.setReadOnly(True)
            self.setFrameShape(QFrame.NoFrame)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.viewport().setAutoFillBackground(False)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            self.document().setDocumentMargin(1)
            self.setStyleSheet(
                f"color:{text_color};background:transparent;font-size:10pt;")
            if bold:
                self.setHtml(f"<b>{text}</b>")
            else:
                self.setPlainText(text)

        def sizeHint(self):
            """返回内容实际高度，适配 markdown 中不同字号。"""
            doc = self.document()
            w = self.viewport().width()
            if w < 10:
                w = 100
            doc.setTextWidth(w - 2)
            h = int(doc.size().height()) + 18
            return QSize(super().sizeHint().width(), max(h, 20))

        def resizeEvent(self, event):
            super().resizeEvent(event)
            self.updateGeometry()

    class _TableCard(QFrame):
        """自定义表格卡片 — 每个单元格 _CellText 自动高度。支持流式 add_row。"""
        def __init__(self, headers, rows, colors, parent=None):
            super().__init__(parent)
            self.setObjectName("clawTableCard")
            self.setMaximumWidth(int(panel.width()))
            self.setStyleSheet(
                f"QFrame#clawTableCard{{background:{colors['surface']};"
                f"border:1px solid {colors['overlay']};border-radius:8px;}}")
            lo = QVBoxLayout(self); lo.setContentsMargins(0,0,0,0); lo.setSpacing(1)

            n_cols = len(headers)
            self._n_cols = n_cols
            self._colors = colors
            self._row_count = 0
            self._last_data_row = None
            self._card_layout = lo

            # 表头
            hf = QFrame()
            hf.setStyleSheet(
                f"background:{colors['accent']};border-radius:7px 7px 0 0;")
            hl = QHBoxLayout(hf); hl.setContentsMargins(10, 8, 10, 8)
            for h in headers:
                ct = _CellText(h, "#FFFFFF", bold=True)
                hl.addWidget(ct, 1)
            lo.addWidget(hf)

            # 数据行
            for idx, row in enumerate(rows):
                rf = QFrame()
                bg = colors['surface'] if idx % 2 == 0 else colors['body']
                br = "border-radius:0 0 7px 7px;" if idx == len(rows) - 1 else ""
                rf.setStyleSheet(f"background:{bg};{br}")
                rl = QHBoxLayout(rf); rl.setContentsMargins(10, 6, 10, 6)
                for ci in range(n_cols):
                    c = row[ci] if ci < len(row) else ""
                    ct = _CellText(c, colors['text'])
                    rl.addWidget(ct, 1)
                lo.addWidget(rf)
                self._row_count += 1
                self._last_data_row = rf

            self.updateGeometry()

        def add_row(self, cells):
            """流式追加一行到表格末尾。"""
            # 移除前最后一行的底部圆角
            if self._last_data_row:
                old_ss = self._last_data_row.styleSheet()
                self._last_data_row.setStyleSheet(
                    old_ss.replace("border-radius:0 0 7px 7px;", ""))
            bg = self._colors['surface'] if self._row_count % 2 == 0 else self._colors['body']
            rf = QFrame()
            rf.setStyleSheet(f"background:{bg};border-radius:0 0 7px 7px;")
            rl = QHBoxLayout(rf); rl.setContentsMargins(10, 6, 10, 6)
            for ci in range(self._n_cols):
                val = cells[ci] if ci < len(cells) else ""
                ct = _CellText(val, self._colors['text'])
                rl.addWidget(ct, 1)
            self._card_layout.addWidget(rf)
            self._last_data_row = rf
            self._row_count += 1
            self.updateGeometry()

        def resizeEvent(self, event):
            """宽度变化时强制所有单元格重算高度，适配风格线等宽字符换行。"""
            super().resizeEvent(event)
            for cell in self.findChildren(_CellText):
                cell.updateGeometry()

    def _add_ai_bubble():
        """添加空气泡容器（无内容），流式过程中由 _flush_stream 动态填充。返回 (frame, token_lbl)。"""
        f, lo = _make_bubble_frame("clawAiBubble", "transparent")
        f.setMaximumWidth(int(panel.width()))

        # ── 思考指示器（L2 三点动画 + L3 计时）──
        th_frame = QFrame(objectName="clawThinkingIndicator")
        th_hl = QHBoxLayout(th_frame)
        th_hl.setContentsMargins(0, 0, 0, 8)
        th_hl.setSpacing(4)
        th_icon = QLabel("🤔")
        th_icon.setStyleSheet(f"color:{_colors['subtext']};background:transparent;font-size:12pt;")
        th_text = QLabel("思考中")
        th_text.setStyleSheet(f"color:{_colors['subtext']};background:transparent;font-size:10pt;")
        th_dots = QLabel("")
        th_dots.setStyleSheet(f"color:{_colors['subtext']};background:transparent;font-size:10pt;")
        th_elapsed = QLabel("⏱ 0s")
        th_elapsed.setStyleSheet(f"color:{_colors['muted']};background:transparent;font-size:9pt;")
        th_hl.addWidget(th_icon); th_hl.addWidget(th_text); th_hl.addWidget(th_dots)
        th_hl.addStretch(); th_hl.addWidget(th_elapsed)
        lo.addWidget(th_frame)

        nonlocal _thinking_widget, _thinking_dots, _thinking_elapsed
        _thinking_widget = th_frame
        _thinking_dots = th_dots
        _thinking_elapsed = th_elapsed

        # ── 内容容器（隔离动态段与静态组件，段索引从 0 开始）──
        _cc = QWidget(objectName="clawContentContainer")
        _cc.setStyleSheet("background:transparent;")
        _ccl = QVBoxLayout(_cc)
        _ccl.setContentsMargins(0, 0, 0, 0)
        _ccl.setSpacing(8)
        lo.addWidget(_cc)
        nonlocal _content_container
        _content_container = _cc

        # ── 全局「全部接受」按钮（气泡底部，流式结束后可见）──
        acc_btn = QPushButton("✅ 全部接受")
        acc_btn.setObjectName("clawGlobalAcceptBtn")
        acc_btn.setCursor(Qt.PointingHandCursor)
        acc_btn.setFixedHeight(32)
        acc_btn.setStyleSheet(
            "QPushButton#clawGlobalAcceptBtn{"
            f"background:{_colors.get('accent', '#2E6DDE')};color:#ffffff;"
            "border:none;border-radius:6px;"
            "font-size:11px;font-weight:bold;padding:0 16px;"
            "}"
            "QPushButton#clawGlobalAcceptBtn:hover{background:#58A6FF;}"
        )
        acc_btn.setVisible(False)
        lo.addWidget(acc_btn)
        nonlocal _global_accept_btn
        _global_accept_btn = acc_btn
        acc_btn.clicked.connect(lambda: _on_diff_all_accepted(mw))

        tk = QLabel(objectName="clawAiToken")
        tk.setVisible(False)
        tk.setStyleSheet(f"color:{_colors['subtext']};background:transparent;font-size:9pt;padding:0 4px;")
        lo.addWidget(tk)
        w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(0,2,0,2)
        hl.addWidget(f)
        cl.addWidget(w)
        nonlocal _streaming_wrapper
        _streaming_wrapper = w

        # 启动思考指示器
        _start_thinking_indicator()

        return f, tk

    _add_sys_msg("🤖 Claw 助手 · 开始对话\n输入辩论相关问题开始交流")

    # ── 思考指示器（L2 三点动画 + L3 计时）──
    _dot_states = ["", ".", "..", "..."]
    _dot_idx = 0

    def _tick_dots():
        nonlocal _dot_idx
        _dot_idx = (_dot_idx + 1) % 4
        if _thinking_dots:
            _thinking_dots.setText(_dot_states[_dot_idx])

    def _tick_elapsed():
        nonlocal _thinking_elapsed_secs
        _thinking_elapsed_secs += 1
        if _thinking_elapsed:
            _thinking_elapsed.setText(f"⏱ {_thinking_elapsed_secs}s")

    _thinking_dot_timer = QTimer()
    _thinking_dot_timer.setInterval(500)
    _thinking_dot_timer.timeout.connect(_tick_dots)

    _thinking_elapsed_timer = QTimer()
    _thinking_elapsed_timer.setInterval(1000)
    _thinking_elapsed_timer.timeout.connect(_tick_elapsed)

    def _start_thinking_indicator():
        """启动三点动画 + 计时。"""
        nonlocal _thinking_elapsed_secs
        _thinking_elapsed_secs = 0
        if _thinking_elapsed:
            _thinking_elapsed.setText("⏱ 0s")
        if _thinking_dots:
            _thinking_dots.setText("")
        if _thinking_widget:
            _thinking_widget.setVisible(True)
        _thinking_dot_timer.start()
        _thinking_elapsed_timer.start()

    def _stop_thinking_indicator():
        """停止三点动画 + 计时，隐藏指示器。"""
        if _thinking_dot_timer and _thinking_dot_timer.isActive():
            _thinking_dot_timer.stop()
        if _thinking_elapsed_timer and _thinking_elapsed_timer.isActive():
            _thinking_elapsed_timer.stop()
        if _thinking_widget:
            _thinking_widget.setVisible(False)
    _chat_layout_ref = cl; panel._chat_layout = cl

    # ── 附件引用按钮（输入区上方）──
    att_btn = _build_buttons([dict(text="📎", tooltip="引用文件")], api)[0]

    # ── 输入区 ──
    ia = QFrame(objectName="clawInputArea")
    il = QVBoxLayout(ia); il.setContentsMargins(12,8,12,8); il.setSpacing(4)

    # 附件按钮 + 文件标签栏
    att_row = QHBoxLayout(); att_row.setContentsMargins(0,0,0,4); att_row.setSpacing(6)
    att_row.addWidget(att_btn)
    att_row.addStretch()
    il.addLayout(att_row)

    # 文件标签栏
    ftb = _FileTagBar(); il.addWidget(ftb)

    # 输入行
    ir = QHBoxLayout(); ir.setSpacing(8)
    ie = QTextEdit(objectName="clawInputEdit")
    ie.setPlaceholderText("输入你的问题... (Alt+Enter 发送, @ 引用文件)")
    ie.setMinimumHeight(60); ie.setFont(QFont("HarmonyOS Sans SC", 11)); ie.setAcceptRichText(False)
    ir.addWidget(ie, 1)
    snd = _build_buttons([dict(text="发送", accent="#2E6DDE")], api)[0]; ir.addWidget(snd)
    il.addLayout(ir)

    # 底部信息栏
    bb = QFrame(objectName="clawBottomBar")
    bl = QHBoxLayout(bb); bl.setContentsMargins(4,0,4,0)
    wc = QLabel("字数：0/2000", objectName="clawWordCount")
    wc.setFont(QFont("HarmonyOS Sans SC", 10))
    bl.addWidget(wc); bl.addStretch()
    fc = QLabel("附件: 0", objectName="clawFileCount")
    fc.setFont(QFont("HarmonyOS Sans SC", 10)); fc.setStyleSheet("background:transparent;")
    bl.addWidget(fc)
    il.addWidget(bb)
    ml.addWidget(ia)

    # ── 状态 ──
    sel_files = []  # list[dict]
    # 导入面板创建前已通过 add_file_to_session 添加的待处理文件
    for pf in _claw_pending:
        sel_files.append(pf)
        ftb.add_tag(len(sel_files) - 1, pf.get("name", "?"))
    if _claw_pending:
        fc.setText(f"附件: {len(sel_files)}")
        _claw_pending.clear()
    # 注册到模块状态，供外部（项目浏览器等）调用
    _claw_state["debate_claw"] = dict(
        files=sel_files, tag_bar=ftb, count_label=fc, api=api
    )

    # ── Popover ──
    pop = _FileSelectorPopover(api)

    # ── 信号 ──
    def _on_send():
        nonlocal _streaming_segments, _streaming_text, _streaming_label, _streaming_wrapper, _state
        txt = ie.toPlainText().strip()
        if not txt and not sel_files:
            return
        snap = list(sel_files)
        # 隐藏欢迎语（移除第一个系统消息）
        if cl.count() > 0:
            it0 = cl.itemAt(0)
            if it0 and it0.widget():
                w0 = it0.widget()
                if isinstance(w0, QLabel) and "Claw 助手" in w0.text():
                    w0.deleteLater()
        # 添加用户消息
        _add_user_msg(txt, snap)
        ai_input = txt + (_build_file_block(snap, api) if snap else "")
        _conversation_history.append({"role": "user", "content": ai_input})
        ie.clear()
        sel_files.clear(); ftb.clear_tags(); fc.setText("附件: 0")
        
        # AI 流式空气泡（含思考指示器，由 _add_ai_bubble 自动启动）
        _, tk = _add_ai_bubble()
        _streaming_segments = []
        _streaming_text = ""
        _streaming_label = tk
        _scroll_bottom()
        _state = dict(full_text="", streaming=True)
        QTimer.singleShot(100, lambda: _do_ai_call(_state, api.mw))

        # ── 发送后：按钮变为「停止」──
        snd.setText("停止")
        snd.setStyleSheet(
            "QPushButton {"
            "  background-color: #E53935;"
            "  color: #FFFFFF;"
            "  border-radius: 6px;"
            "  padding: 6px 16px;"
            "  font-size: 11pt;"
            "}"
        )
        snd.setToolTip("停止 AI 回复")

    def _on_clear():
        nonlocal _tool_call_round, _streaming_segments, _streaming_text, _streaming_label, _streaming_wrapper, _content_container
        _stop_thinking_indicator()
        _undo_snapshots.clear()
        if _global_accept_btn:
            _global_accept_btn.setVisible(False)
        while cl.count():
            it = cl.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        _add_sys_msg("🤖 Claw 助手 · 对话已清空\n输入辩论相关问题开始交流")
        _streaming_segments = []
        _streaming_text = ""
        _streaming_label = None
        _streaming_wrapper = None
        _content_container = None
        sel_files.clear(); ftb.clear_tags(); fc.setText("附件: 0")
        _conversation_history.clear()
        _tool_call_round = 0

    def _on_attach():
        pop.show_at(att_btn)

    def _on_file_picked(fi):
        p = fi.get("path", "")
        if any(f.get("path") == p for f in sel_files):
            return
        sel_files.append(fi)
        ftb.add_tag(len(sel_files) - 1, fi.get("name", "?"))
        fc.setText(f"附件: {len(sel_files)}")

    def _on_tag_rm(idx):
        if 0 <= idx < len(sel_files):
            del sel_files[idx]
            ftb.clear_tags()
            for i, f in enumerate(sel_files):
                ftb.add_tag(i, f.get("name", "?"))
            fc.setText(f"附件: {len(sel_files)}")

    # 按钮点击路由：根据当前状态决定是发送还是停止
    def _on_btn_click():
        if _state.get("streaming"):
            _on_interrupt()
        else:
            _on_send()
    snd.clicked.connect(_on_btn_click)
    clr_btn.clicked.connect(_on_clear)
    att_btn.clicked.connect(_on_attach)
    pop.fileSelected.connect(_on_file_picked)
    ftb.tagRemoved.connect(_on_tag_rm)

    # Alt+Enter / @ 触发
    _orig_kp = ie.keyPressEvent
    def _kp(e):
        if e.key() == Qt.Key_Return and e.modifiers() == Qt.AltModifier:
            _on_send()
        elif e.text() == "@":
            _orig_kp(e)
            pop.show_at(att_btn)
        else:
            _orig_kp(e)
    ie.keyPressEvent = _kp

    ie.textChanged.connect(lambda: wc.setText(f"字数：{len(ie.toPlainText())}/2000"))

    qss = _load_theme_qss()
    if qss: panel.setStyleSheet(qss)

    # ── 面板 resize / 全屏切换 → 更新全部气泡宽度 ──
    _orig_resize = panel.resizeEvent
    def _on_panel_resize(e):
        _orig_resize(e)
        _update_bubble_widths()
    panel.resizeEvent = _on_panel_resize

    from PyQt5.QtCore import QEvent
    _orig_change = panel.changeEvent
    def _on_change(e):
        _orig_change(e)
        if e.type() == QEvent.WindowStateChange:
            QTimer.singleShot(100, _update_bubble_widths)
    panel.changeEvent = _on_change

    # ── 流式 AI 回调（实时解析 text/table/diff 分段，增量创建/更新 widget）──
    _stream_timer = QTimer()
    _stream_timer.setSingleShot(True)
    
    # Diff 卡片回调：用户接受/拒绝/全部接受时的处理闭包
    def _make_diff_callback(diff_card):
        """为单个 DiffCard 创建接受/拒绝回调。"""
        from workers.diff_widget import DiffState
        from workers.speech_editor.paragraph_manager import find_paragraph_by_id
        
        def on_accept(card_id):
            """接受：将 DiffCard 替换为修改后的文本（_AutoTB）。

            如果 DiffCard 关联了段落 ID（paragraph_id），精确替换对应段落；
            否则将 accepted_text 作为全文替换当前活跃侧的编辑器内容。
            """
            accepted_text = diff_card.get_accepted_content()
            para_id = diff_card.paragraph_id

            # ── 保存撤销数据（接受前快照段落原始内容）──
            if para_id:
                sm = getattr(mw, '_speech_mgr', None)
                if sm:
                    for s_side in ("pro", "con"):
                        pp = find_paragraph_by_id(sm.get_paragraphs(s_side), para_id)
                        if pp:
                            _undo_snapshots[diff_card.card_id] = {
                                "side": s_side,
                                "para_id": para_id,
                                "old_texts": list(pp.get("texts", [])),
                            }
                            break

            # ── 先更新一辩稿编辑器（独立于气泡 UI，即使气泡已销毁也能执行）──
            if accepted_text:
                try:
                    _apply_accepted_diff(mw, para_id, accepted_text)
                except Exception as ex:
                    print(f"[Diff] accept error: {ex}", file=sys.stderr)

            # ── 再处理气泡内 UI 替换（使用内容容器布局，索引从 0 开始）──
            f = _streaming_wrapper.findChild(QFrame, "clawAiBubble") if _streaming_wrapper else None
            if not f:
                return
            cc = f.findChild(QWidget, "clawContentContainer")
            if not cc:
                return
            clo = cc.layout()
            for idx, s in enumerate(_streaming_segments):
                if s.get("widget") is diff_card and s["seg"][0] == "diff":
                    diff_card.deleteLater()
                    old_w = clo.takeAt(clo.indexOf(diff_card))
                    if old_w and old_w.widget():
                        pass
                    tb = _AutoTB()
                    tb.setMarkdown(accepted_text)
                    clo.insertWidget(idx, tb)
                    _streaming_segments[idx] = {"seg": ("text", accepted_text), "widget": tb}
                    tb.updateGeometry()
                    _scroll_bottom()
                    break

        def on_reject(card_id):
            """拒绝：将 DiffCard 替换为原始文本（_AutoTB）。
            
            如果是撤销（此前为 ACCEPTED 状态），同时恢复一辩稿编辑器内容。
            """
            # ── 如果是撤销操作（状态从 ACCEPTED → PENDING），恢复编辑器 ──
            if diff_card.state == DiffState.PENDING:
                info = _undo_snapshots.pop(diff_card.card_id, None)
                if info:
                    try:
                        _undo_accepted_diff(mw, info)
                    except Exception as ex:
                        print(f"[Diff] undo error: {ex}", file=sys.stderr)

            # ── 气泡内 UI 替换 ──
            f = _streaming_wrapper.findChild(QFrame, "clawAiBubble") if _streaming_wrapper else None
            if not f:
                return
            cc = f.findChild(QWidget, "clawContentContainer")
            if not cc:
                return
            clo = cc.layout()
            for idx, s in enumerate(_streaming_segments):
                if s.get("widget") is diff_card and s["seg"][0] == "diff":
                    orig_text = diff_card.get_original_text()
                    diff_card.deleteLater()
                    clo.takeAt(clo.indexOf(diff_card))
                    tb = _AutoTB()
                    tb.setMarkdown(orig_text)
                    clo.insertWidget(idx, tb)
                    _streaming_segments[idx] = {"seg": ("text", orig_text), "widget": tb}
                    tb.updateGeometry()
                    _scroll_bottom()
                    break

        return on_accept, on_reject
    
    def _on_diff_all_accepted(mw):
        """全部接受：扫描整个对话历史中所有气泡内的 pending DiffCard，批量接受。

        A: 全局按钮取代卡片内「全部接受」
        B: 按段落 ID 去重后统一写入编辑器
        C: 扫描 cl 布局中所有气泡（不仅当前气泡）
        """
        from workers.diff_widget import DiffCard, DiffState
        import workers.speech_editor.paragraph_manager as PM

        # A+C: 扫描整个 cl 布局中的所有 DiffCard
        pending = []
        for i in range(cl.count()):
            item = cl.itemAt(i)
            if not item or not item.widget():
                continue
            for card in item.widget().findChildren(DiffCard):
                if card.state == DiffState.PENDING:
                    pending.append(card)
        if not pending:
            return

        speech_mgr = getattr(mw, '_speech_mgr', None)

        # B: 收集所有待接受 diff，按 (side, para_id) 去重（最后一条胜出）
        batched = {}  # key=(side, para_id) or (None, card_id) → accepted_text
        for card in pending:
            para_id = card.paragraph_id
            text = card.get_accepted_content()
            if speech_mgr and para_id:
                found_side = None
                for side in ("pro", "con"):
                    if PM.find_paragraph_by_id(speech_mgr.get_paragraphs(side), para_id):
                        found_side = side
                        break
                if found_side:
                    batched[(found_side, para_id)] = text
                    continue
            # 无 para_id 或未命中段落 → 作为全文替换项
            batched[(None, card.card_id)] = text

        # ── 批量接受前保存所有卡片撤销数据 ──
        for card in pending:
            pid = card.paragraph_id
            if pid and speech_mgr:
                for s_side in ("pro", "con"):
                    pp = PM.find_paragraph_by_id(
                        speech_mgr.get_paragraphs(s_side), pid)
                    if pp:
                        _undo_snapshots[card.card_id] = {
                            "side": s_side,
                            "para_id": pid,
                            "old_texts": list(pp.get("texts", [])),
                        }
                        break

        # 执行批量接受（先隐藏全局按钮，防止重复点击）
        if _global_accept_btn:
            _global_accept_btn.setEnabled(False)

        for (side_or_none, pid), text in batched.items():
            para_id = pid if side_or_none is not None else None
            _apply_accepted_diff(mw, para_id, text)

        # 更新所有卡片 UI 状态
        for card in pending:
            card.set_state(DiffState.ACCEPTED)

        mw._update_status(f"✅ 全部接受：{len(pending)} 处修改已应用")
        if _global_accept_btn:
            _global_accept_btn.setVisible(False)

    def _flush_stream():
        nonlocal _streaming_segments, _streaming_text, _streaming_wrapper
        text = _streaming_text
        if not text:
            return
        segments = _parse_md_segments(text)
        segs = _streaming_segments
        # 检测 _streaming_wrapper 是否已被删除（面板关闭、清空对话等）
        try:
            f = _streaming_wrapper.findChild(QFrame, "clawAiBubble") if _streaming_wrapper else None
        except RuntimeError:
            _streaming_wrapper = None
            f = None
        if not f:
            return
        # 使用内容容器布局（段索引从 0 开始，不受静态组件干扰）
        cc = f.findChild(QWidget, "clawContentContainer") if _content_container else None
        if not cc:
            return
        clo = cc.layout()
        i = 0
        while i < len(segments):
            seg = segments[i]
            if i < len(segs):
                existing = segs[i]
                etype = seg[0]
                old_type = existing["seg"][0]
                if etype != old_type:
                    existing["widget"].deleteLater()
                    clo.takeAt(clo.indexOf(existing["widget"]))
                    if etype == "text":
                        tb = _AutoTB()
                        tb.setMarkdown(seg[1])
                        clo.insertWidget(i, tb)
                        segs[i] = {"seg": seg, "widget": tb}
                        tb.updateGeometry()
                    elif etype == "table":
                        card = _TableCard(seg[1], seg[2], _colors)
                        clo.insertWidget(i, card)
                        segs[i] = {"seg": seg, "widget": card}
                        card.updateGeometry()
                    elif etype == "diff":
                        dc = _create_diff_widget(seg[1])
                        clo.insertWidget(i, dc)
                        segs[i] = {"seg": seg, "widget": dc}
                        dc.updateGeometry()
                elif etype == "text":
                    if seg[1] != existing["seg"][1]:
                        existing["widget"].setMarkdown(seg[1])
                    existing["seg"] = seg
                elif etype == "table":
                    _, hdrs, new_rows = seg
                    _, _, old_rows = existing["seg"]
                    if hdrs != existing["seg"][1]:
                        existing["widget"].deleteLater()
                        new_card = _TableCard(hdrs, new_rows, _colors)
                        clo.insertWidget(i, new_card)
                        clo.takeAt(clo.indexOf(existing["widget"]))
                        segs[i] = {"seg": seg, "widget": new_card}
                        new_card.updateGeometry()
                    elif len(new_rows) > len(old_rows):
                        card = existing["widget"]
                        for r in new_rows[len(old_rows):]:
                            card.add_row(r)
                        existing["seg"] = seg
                        card.updateGeometry()
                elif etype == "diff":
                    # Diff 段每次重建（内容可能变化）
                    existing["widget"].deleteLater()
                    clo.takeAt(clo.indexOf(existing["widget"]))
                    dc = _create_diff_widget(seg[1])
                    clo.insertWidget(i, dc)
                    segs[i] = {"seg": seg, "widget": dc}
                    dc.updateGeometry()
                i += 1
            else:
                etype = seg[0]
                if etype == "text":
                    tb = _AutoTB()
                    tb.setMarkdown(seg[1])
                    clo.addWidget(tb)
                    segs.append({"seg": seg, "widget": tb})
                    tb.updateGeometry()
                elif etype == "table":
                    card = _TableCard(seg[1], seg[2], _colors)
                    clo.addWidget(card)
                    segs.append({"seg": seg, "widget": card})
                    card.updateGeometry()
                elif etype == "diff":
                    dc = _create_diff_widget(seg[1])
                    clo.addWidget(dc)
                    segs.append({"seg": seg, "widget": dc})
                    dc.updateGeometry()
                i += 1
        while len(segs) > len(segments):
            item = segs.pop()
            w = item["widget"]
            clo.removeWidget(w)
            w.deleteLater()
        _scroll_bottom()

    def _create_diff_widget(diff_data):
        """创建 DiffCard 并连接信号。"""
        from workers.diff_widget import DiffCard
        cid = f"diff_{id(diff_data)}_{hash(str(diff_data.get('lines','')))}"
        dc = DiffCard(
            card_id=cid,
            title=diff_data.get("title", "修改建议"),
            additions=diff_data.get("additions", 0),
            deletions=diff_data.get("deletions", 0),
            lines=diff_data.get("lines", []),
            colors=_colors,
            paragraph_id=diff_data.get("paragraph"),  # 段落 ID（新增）
        )
        cb_acc, cb_rej = _make_diff_callback(dc)
        dc.accepted.connect(cb_acc)
        dc.rejected.connect(cb_rej)
        dc.no_paragraph_warning.connect(
            lambda _cid: _add_system_notification(
                "✅ 内容已更新到一辩稿编辑器（全文替换）。\n"
                "提示：若需要精确替换段落，可请 AI 在 [DIFF] 中添加段落=\"xxx\" 字段。"
            )
        )
        return dc
    _stream_timer.timeout.connect(_flush_stream)

    def _on_stream_chunk(state, chunk, mw):
        """逐字片段到达：累积全文，触发 50ms coalesce 刷新。"""
        nonlocal _streaming_text
        if not state.get("streaming"):
            return
        # ── 首次收到内容时隐藏思考指示器 ──
        if _thinking_widget and _thinking_widget.isVisible():
            _stop_thinking_indicator()
        state["full_text"] += chunk
        _streaming_text = state["full_text"]
        if not _stream_timer.isActive():
            _stream_timer.start(50)

    # ── 权限弹窗引用 ──
    _perm_seen = set()
    _tool_call_round = 0    # tools 模式调用轮次计数
    # 当前活跃的 AIWorker 引用（用于权限恢复）
    _active_worker = None
    _active_thread = None

    # 并行授权状态
    _pending_auth_cards: dict = {}   # {tool_call_id: card_widget}
    _auth_responses: dict = {}       # {tool_call_id: {"mode": str, "result": str|None}}
    _expected_tool_count = 0         # 预期的授权响应数量
    _auto_approve_log = None  # 运行时从 permission_handler 获取，见 _handle_tool_calls
    _last_usage: dict | None = None  # 最近一次 AI 回答的 token 用量

    def _cleanup_worker():
        """清理当前 worker 和 thread。"""
        nonlocal _active_worker, _active_thread, _pending_auth_cards, _auth_responses
        if _active_worker:
            try:
                _active_worker.stop()
                _active_worker.disconnect()
            except Exception:
                pass
            _active_worker = None
        if _active_thread:
            try:
                _active_thread.quit()
                _active_thread.wait(3000)
            except Exception:
                pass
            _active_thread = None
        # 清理残留的授权卡片
        for card in _pending_auth_cards.values():
            try:
                card.deleteLater()
            except Exception:
                pass
        _pending_auth_cards.clear()
        _auth_responses.clear()

    def _do_ai_call(state, mw):
        """使用工作线程执行 SSE 流式 AI 调用 + 权限中断-重调协议（含 tools 模式）。"""
        import json, requests
        from PyQt5.QtCore import QThread
        from workers.ai_worker import AIWorker
        from workers.permission_handler import (
            scan_permissions, strip_permissions, check_already,
            PermissionAuthCard, set_always, get_perm_display_label, get_risk_level,
            execute_permission,
        )
        nonlocal _active_worker, _active_thread, _perm_seen, _tool_call_round

        # 先清理旧的 worker
        _cleanup_worker()

        cfg_path = os.path.join(os.path.dirname(__file__), "config", "ai_config.json")
        sp = ("你是一个专业的辩论助手，名为 DebateClaw。"
              "你擅长分析辩论问题、提供正反方论点、构建辩论框架、评估论证力度。"
              "请用简洁清晰的中文回答用户的辩论相关问题。"
              "请使用 Markdown 格式组织你的回复。"
              "\n\n"
              "**权限申请**：当你需要读取文件、写入文件、列出目录、搜索内容时，"
              "请通过系统提供的 tools 工具进行调用。\n\n"
              "**降级格式**：如果工具不可用，可输出 [PERM:type path] 标记。\n"
              "例如：[PERM:file_read C:\\Users\\doc\\debate.txt]"
              "\n\n"
              "**安全写入模式规则（重要）**：如果 system prompt 中出现"
              "「🔒 安全写入模式已开启」的标记，说明当前模式禁用 file_write 工具。"
              "此时你**只能**使用 [DIFF] 格式输出修改建议，不要尝试调用 file_write。"
              "\n\n"
              "**非安全模式下**：修改一辩稿时优先使用 [DIFF] 格式，"
              "不要直接调用 file_write 写入一辩稿文件。"
              "[DIFF] 格式会在对话中生成可视化修改卡片，用户可以逐条审核后再决定是否应用。"
              "直接写入文件会跳过用户的审核流程。")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    sp = json.load(f).get("system_prompt", sp)
            except Exception:
                pass
        acfg = api.mw._load_api_config()
        url = acfg.get("api_url", "")
        key = acfg.get("api_key", "")
        model = acfg.get("model", "deepseek-chat")
        if not url or not key:
            _on_stream_error(state, "❌ API 未配置", mw)
            return
        # 载入文档 + 项目上下文 + 记忆摘要
        docs = [sp]
        for name in ("permissions_guide.md", "memory_guide.md"):
            p = os.path.join(os.path.dirname(__file__), "MEMORY", name)
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    docs.append(f.read())
        # 注入项目路径 + 文件清单（零权限，自动注入）
        docs.append(_build_project_context(api))
        from workers.memory_handler import summary as mem_summary
        mem = mem_summary()
        if mem:
            docs.append(mem)

        # ── 注入一辩稿段落结构上下文 ──
        _para_ctx = _build_paragraph_context(mw, _safe_write_mode[0])
        if _para_ctx:
            docs.append(_para_ctx)
        msgs = [{"role":"system","content": "\n\n".join(docs)}]
        msgs.extend(list(_conversation_history))
        _perm_seen.clear()

        # 创建工作线程和 worker
        _active_thread = QThread()
        _active_worker = AIWorker(acfg, msgs, state, _conversation_history)
        # 安全写入模式：禁止 AI 使用 file_write tool
        _active_worker._safe_write_mode = _safe_write_mode[0]
        # 跨轮次复用：如果之前已经降级，新消息也禁用 tools
        if _tool_call_round >= 3:
            _active_worker._tool_mode_active = False
        _active_worker.moveToThread(_active_thread)

        # 连接信号
        _active_thread.started.connect(_active_worker.run)

        # 文本片段到达 -> 更新UI
        _active_worker.chunk_received.connect(
            lambda c: _on_stream_chunk(state, c, mw))

        # [PERM:...] 标记模式：权限请求 -> 显示卡片
        _active_worker.perm_requested.connect(
            lambda perms: _show_perm_cards(perms, ia, state, mw))

        # [PERM:...] 标记模式：因权限中断 -> 保存状态
        _active_worker.perm_interrupted.connect(
            lambda text_before, perms: _on_permission_interrupted(
                state, text_before, perms, mw))

        # ★★★ tools 模式：tool_calls 到达 -> 并行授权卡片 ★★★
        _active_worker.tool_calls_received.connect(
            lambda tool_calls: _handle_tool_calls(tool_calls, ia, state, mw))

        # token 用量
        _active_worker.usage_received.connect(lambda u: _set_usage(u))

        # 正常完成
        _active_worker.finished.connect(
            lambda full: _on_ai_finished(state, full, mw))
        _active_worker.finished.connect(_active_thread.quit)

        # 出错
        _active_worker.error.connect(
            lambda err: _on_stream_error(state, err, mw))
        _active_worker.error.connect(_active_thread.quit)

        # 启动线程
        _active_thread.start()

    def _on_permission_interrupted(state, text_before, perms, mw):
        """AI流因 [PERM:...] 标记中断时的处理。"""
        from workers.memory_handler import strip_memory_markers
        clean_text = strip_memory_markers(text_before) or text_before
        _streaming_text = clean_text
        _flush_stream()

    def _handle_tool_calls(tool_calls: list, ia, state, mw):
        """tools 模式：收到完整 tool_calls 后，创建并行授权卡片。

        Args:
            tool_calls: [{"id": str, "name": str, "arguments": dict}, ...]
        """
        from workers.permission_handler import get_risk_level, PermissionAuthCard
        nonlocal _pending_auth_cards, _auth_responses, _expected_tool_count, _active_worker, _active_thread
        print(f"[DBG] _handle_tool_calls: {len(tool_calls)} tools received, names={[t.get('name','') for t in tool_calls]}", file=sys.stderr)

        _pending_auth_cards.clear()
        _auth_responses.clear()
        _expected_tool_count = len(tool_calls)

        for tc in tool_calls:
            tc_id = tc["id"]
            tc_name = tc["name"]
            tc_args = tc.get("arguments", {})

            # ── 安全写入模式：拦截 file_write ──
            if _safe_write_mode[0] and tc_name == "file_write":
                _expected_tool_count -= 1
                # 从 AIWorker 的 _pending_tool_calls 中移除该条目
                if _active_worker and hasattr(_active_worker, '_pending_tool_calls'):
                    _active_worker._pending_tool_calls = [
                        ptc for ptc in _active_worker._pending_tool_calls
                        if ptc.get("id") != tc_id
                    ]
                _add_system_notification(
                    f"🔒 安全模式下已拦截 file_write（{tc_args.get('path','?')}）\n"
                    "请使用 [DIFF] 格式输出修改建议"
                )
                continue

        # 全部工具都被安全模式拦截时 → 截断最后 assistant + 注入 system 消息 + 重启 AI
        if _expected_tool_count <= 0:
            if _active_worker:
                msgs = _active_worker.get_messages_snapshot()
                # 移除最后一条 assistant 消息（含 file_write tool_call）
                while msgs and msgs[-1].get("role") == "assistant":
                    msgs.pop()
                # 注入系统提示，要求 AI 改用 [DIFF] 格式
                msgs.append({
                    "role": "system",
                    "content": (
                        "## 🔒 安全写入模式 - file_write 被拦截，请重新输出\n\n"
                        "你刚才尝试调用 file_write，但该工具在当前模式下已被系统禁用。\n"
                        "你的那条 tool_call 已被丢弃，现在需要你重新生成回复。\n\n"
                        "**你唯一能做的修改方式是输出 [DIFF] 标记块。**\n"
                        "请直接输出一个或多个 [DIFF] 块，不要在块外用文字解释。\n\n"
                        "[DIFF] 正确格式：\n"
                        '```\n[DIFF:标题="修改说明" +N -M]\n'
                        '- 需要删除的原文行\n'
                        '+ 修改后的新内容\n'
                        '+ 如果有多个新增行\n'
                        '  保持不变的行用空格开头\n'
                        '[/DIFF]\n```\n\n'
                        "规则：\n"
                        "- `- `（减号+空格）= 删除这行\n"
                        "- `+ `（加号+空格）= 新增这行\n"
                        "- `  `（两个空格）= 这行不变\n"
                        "- 所有改动必须放在 [DIFF]...[/DIFF] 内\n"
                        "- 可以同时输出多个 [DIFF] 块，不要混在文字中\n"
                    ),
                })
                old_worker, old_thread = _active_worker, _active_thread
                _active_worker = None
                _active_thread = None
                QTimer.singleShot(200, lambda: _do_ai_restart(
                    state, mw, msgs, old_worker, old_thread))
            return

        # 第二轮循环：为剩余工具构造显示标签并创建授权卡片
        for tc in tool_calls:
            tc_id = tc["id"]
            tc_name = tc["name"]
            tc_args = tc.get("arguments", {})

            # 跳过已被安全模式拦截的 file_write
            if _safe_write_mode[0] and tc_name == "file_write":
                continue

            # 构造显示标签
            if tc_name in ("file_read", "file_write"):
                display_label = tc_args.get("path", tc_name)
            elif tc_name == "file_list":
                display_label = tc_args.get("directory", tc_name)
            elif tc_name == "search":
                display_label = f"搜索: {tc_args.get('query', '')[:30]}"
            elif tc_name == "network":
                display_label = tc_args.get("url_or_query", "")
            elif tc_name == "execute":
                display_label = "执行代码"
            else:
                display_label = str(tc_args)

            risk = get_risk_level(tc_name)

            # ── 自动审批：low 风险 + 已启用 + 不在黑名单 → 直接执行 ──
            from workers.permission_handler import check_auto_approve, execute_permission, _auto_approve_log as _aal
            perm_path = (tc_args.get("path") or tc_args.get("directory")
                         or tc_args.get("url_or_query") or tc_args.get("query")
                         or "")
            if check_auto_approve(tc_name, perm_path):
                try:
                    extra_kwargs = {}
                    if tc_name == "file_write":
                        extra_kwargs["content"] = tc_args.get("content", "")
                    if tc_name == "execute":
                        extra_kwargs["code"] = tc_args.get("code", "")
                    result_text = execute_permission(tc_name, perm_path, **extra_kwargs)
                    _auth_responses[tc_id] = {"mode": "auto", "result": result_text}
                    _aal.append({
                        "time": datetime.datetime.now().strftime("%H:%M:%S"),
                        "type": tc_name,
                        "path": perm_path,
                        "result": "success" if result_text else "empty",
                    })
                    # 瞬态提示（1.5 秒自动消失）
                    _add_auto_approve_notification(tc_name, perm_path)
                    print(f"[AUTO] {tc_name} {perm_path[:60]} auto-approved", file=sys.stderr)
                    _check_all_tool_responses_done(state, mw)
                    continue  # 跳过卡片创建
                except Exception as ex:
                    print(f"[AUTO] {tc_name} auto-approve failed: {ex}", file=sys.stderr)
                    # 降级：fall through 到卡片

            # ── 需手动审批 ──
            code_preview = tc_args.get("code") if tc_name == "execute" else None

            card = PermissionAuthCard(tc_name, display_label, panel,
                                      risk_level=risk, code_preview=code_preview)

            # 超时定时器（15秒自动拒绝）
            timeout_timer = QTimer()
            timeout_timer.setSingleShot(True)
            timeout_timer.timeout.connect(lambda c=card, tid=tc_id: _on_tool_timeout(c, tid))
            timeout_timer.start(15000)

            # 用户响应处理
            def _make_tool_handler(tid, tname, targs, tmr):
                def handler(mode):
                    _on_tool_response(tid, tname, targs, mode, tmr, state, mw)
                return handler

            card.responded.connect(_make_tool_handler(tc_id, tc_name, tc_args, timeout_timer))
            _pending_auth_cards[tc_id] = card

            # 插入卡片到 UI（垂直堆叠在输入区上方）
            _card_inserted = False
            _parent_w = ia.parentWidget() if ia else None
            _parent_lo = _parent_w.layout() if _parent_w else None
            _idx = -1
            if _parent_lo:
                _idx = _parent_lo.indexOf(ia)
                if _idx >= 0:
                    _parent_lo.insertWidget(_idx, card)
                    _card_inserted = True
            print(f"[DBG] Card for {tc_name}: inserted={_card_inserted} parent={_parent_w is not None} layout={_parent_lo is not None} idx={_idx}",
                  file=sys.stderr)

        _scroll_bottom()

    def _on_tool_response(tool_call_id: str, tool_name: str, tool_args: dict,
                          mode: str, timer, state, mw):
        """tools 模式：单个授权卡片响应。"""
        from workers.permission_handler import execute_permission, set_always
        nonlocal _auth_responses

        timer.stop()

        result_text = None

        if mode == "deny":
            _auth_responses[tool_call_id] = {"mode": "deny", "result": None}
            set_always(tool_name, False)
            # 不立即处理，等全部响应
            _check_all_tool_responses_done(state, mw)
            return

        if mode == "always" and tool_name != "network":
            set_always(tool_name, True)
        # network 的 always 按钮已禁用，不会走到这里

        # 执行权限操作
        try:
            extra_kwargs = {}
            if tool_name == "file_write":
                extra_kwargs["content"] = tool_args.get("content", "")
            if tool_name == "execute":
                extra_kwargs["code"] = tool_args.get("code", "")

            # ── search_memory 工具：语义搜索记忆 ──
            query_for_path = tool_args.get("query", "")
            if tool_name == "search_memory":
                from workers.memory_handler import search_summary
                result_text = search_summary(query_for_path, top_k=5) or "(未找到相关记忆)"
                perm_path = query_for_path
            else:
                # 其他工具走权限执行
                perm_path = (tool_args.get("path") or tool_args.get("directory")
                             or tool_args.get("url_or_query") or query_for_path
                             or "")
                result_text = execute_permission(tool_name, perm_path, **extra_kwargs)
        except Exception as ex:
            result_text = f"执行失败: {ex}"

        _result_preview = (result_text[:120].replace("\n", "\\n") if result_text else "NONE")
        print(f"[DBG] tool={tool_name} path={perm_path[:60]} result_len={len(result_text or '')} content=[{_result_preview}]", file=sys.stderr)

        _auth_responses[tool_call_id] = {"mode": mode, "result": result_text}

        # 检查是否全部响应完毕
        _check_all_tool_responses_done(state, mw)

    def _on_tool_timeout(card, tool_call_id: str):
        """tools 模式：授权卡片超时 -> 自动拒绝。"""
        nonlocal _auth_responses
        _auth_responses[tool_call_id] = {"mode": "deny", "result": None}
        card.deleteLater()
        _check_all_tool_responses_done(None, None)

    def _check_all_tool_responses_done(state, mw):
        """检查所有 tool 授权是否都已响应。"""
        nonlocal _active_worker, _auth_responses, _expected_tool_count, _tool_call_round

        if len(_auth_responses) < _expected_tool_count:
            return  # 还有未响应的卡片

        # 全部响应完毕 → 清理卡片引用（卡片自身已通过 _respond() 执行 deleteLater）
        _pending_auth_cards.clear()

        # 构建 tool 结果列表
        results = []
        pending_calls = _active_worker.get_pending_tool_calls() if _active_worker else []
        for tc in pending_calls:
            tc_id = tc["id"]
            resp = _auth_responses.get(tc_id, {"mode": "deny", "result": None})
            if resp["mode"] == "deny" or resp["result"] is None:
                results.append({"tool_call_id": tc_id,
                               "result": "[系统] 用户拒绝了该操作的执行请求"})
            else:
                results.append({"tool_call_id": tc_id, "result": resp["result"]})

        print(f"[DBG] All {len(results)} tool responses done, round={_tool_call_round+1}", file=sys.stderr)

        # 注入结果并重启 AI 调用
        if _active_worker:
            _tool_call_round += 1
            _active_worker.set_tool_results(results)
            QTimer.singleShot(100, lambda: _do_ai_restart_from_tools(
                state, mw))
        else:
            state["streaming"] = False

    def _show_perm_cards(perms: dict, ia, state, mw):
        """在输入区上方显示授权卡片，支持超时和回调。"""
        from workers.permission_handler import (
            PermissionAuthCard, set_always, get_perm_display_label,
            execute_permission,
        )
        from PyQt5.QtCore import QTimer

        for ptype, ppath in perms.items():
            display_label = get_perm_display_label(ptype, ppath)
            card = PermissionAuthCard(ptype, display_label, panel)

            timeout_timer = QTimer()
            timeout_timer.setSingleShot(True)
            timeout_timer.timeout.connect(
                lambda c=card, p=ptype: _on_perm_timeout(c, p))
            timeout_timer.start(15000)

            def _make_handler(pt, pp, tmr):
                def handler(mode):
                    _on_perm_response(pt, pp, mode, tmr, state, mw)
                return handler

            card.responded.connect(_make_handler(ptype, ppath, timeout_timer))

            if ia and ia.parentWidget():
                parent_layout = ia.parentWidget().layout()
                if parent_layout:
                    idx = parent_layout.indexOf(ia)
                    if idx >= 0:
                        parent_layout.insertWidget(idx, card)

    def _on_perm_response(perm_type: str, perm_path: str, mode: str,
                          timer, state, mw):
        """用户点击权限卡片按钮后的处理。"""
        from workers.permission_handler import execute_permission, set_always
        nonlocal _active_worker, _streaming_text
        timer.stop()

        if mode == "deny":
            set_always(perm_type, False)
            state["streaming"] = False
            final = state.get("full_text", "")
            _streaming_text = f"{final}\n\n*（权限已被拒绝）*"
            _flush_stream()
            _streaming_segments = []
            _streaming_text = ""
            _conversation_history.append({"role": "assistant",
                                           "content": final or "(空)"})
            return

        if mode == "always":
            set_always(perm_type, True)

        result_text = None
        granted = True
        try:
            result_text = execute_permission(perm_type, perm_path)
        except (PermissionError, FileNotFoundError, Exception) as ex:
            result_text = f"权限执行失败: {ex}"

        if _active_worker:
            _active_worker.resume_with_result(granted, perm_type, perm_path, result_text)
            _continue_ai_after_permission(state, mw)

    def _on_perm_timeout(card, perm_type: str):
        """权限卡片超时未响应 -> 自动拒绝。"""
        card.deleteLater()

    def _continue_ai_after_permission(state, mw):
        """[PERM:...] 模式：用户授权后重新调用 AI，继续生成回复。"""
        nonlocal _active_worker, _active_thread

        if _active_worker:
            _, updated_msgs = _active_worker.get_state_snapshot()
            old_worker = _active_worker
            old_thread = _active_thread
            _active_worker = None
            _active_thread = None
            QTimer.singleShot(100, lambda: _do_ai_restart(
                state, mw, updated_msgs, old_worker, old_thread))
        else:
            state["streaming"] = False

    def _do_ai_restart_from_tools(state, mw):
        """tools 模式：tool 执行完成后重新发起 AI 调用。"""
        import json
        from PyQt5.QtCore import QThread
        from workers.ai_worker import AIWorker
        nonlocal _active_worker, _active_thread, _tool_call_round

        if not _active_worker:
            state["streaming"] = False
            return

        updated_msgs = _active_worker.get_messages_snapshot()
        print(f"[DBG] _do_ai_restart_from_tools: msgs_count={len(updated_msgs)}, round={_tool_call_round}", file=sys.stderr)
        old_worker = _active_worker
        old_thread = _active_thread
        _active_worker = None
        _active_thread = None

        QTimer.singleShot(200, lambda: _do_ai_restart(
            state, mw, updated_msgs, old_worker, old_thread))

    def _do_ai_restart(state, mw, msgs, old_worker=None, old_thread=None):
        """使用更新后的 messages 重新发起 AI 调用（通用重启函数）。"""
        import json
        from PyQt5.QtCore import QThread
        from workers.ai_worker import AIWorker
        from workers.permission_handler import strip_permissions
        from workers.memory_handler import strip_memory_markers, apply_writes
        nonlocal _active_worker, _active_thread, _tool_call_round

        if old_worker:
            try:
                old_worker.stop()
                old_worker.disconnect()
            except Exception:
                pass
        if old_thread:
            try:
                old_thread.quit()
                old_thread.wait(2000)
            except Exception:
                pass

        state["streaming"] = True

        acfg = api.mw._load_api_config()
        _active_thread = QThread()
        _active_worker = AIWorker(acfg, msgs, state, _conversation_history)
        _active_worker.moveToThread(_active_thread)

        if _tool_call_round >= 3:
            print(f"[DBG] Tools round={_tool_call_round} >= 3, degrading to text-only mode", file=sys.stderr)
            _active_worker._tool_mode_active = False

        _active_thread.started.connect(_active_worker.run)
        print(f"[DBG] _do_ai_restart: msgs={len(msgs)} tool_mode={_active_worker._tool_mode_active} round={_tool_call_round}", file=sys.stderr)

        _active_worker.chunk_received.connect(lambda c: _on_stream_chunk(state, c, mw))

        _active_worker.tool_calls_received.connect(
            lambda tool_calls: _handle_tool_calls(tool_calls, ia, state, mw))
        _active_worker.perm_requested.connect(
            lambda perms: _show_perm_cards(perms, ia, state, mw))
        _active_worker.perm_interrupted.connect(
            lambda tb, perms: _on_permission_interrupted(state, tb, perms, mw))
        _active_worker.usage_received.connect(lambda u: _set_usage(u))
        _active_worker.finished.connect(lambda full: _on_ai_finished(state, full, mw))
        _active_worker.finished.connect(_active_thread.quit)
        _active_worker.error.connect(lambda err: _on_stream_error(state, err, mw))
        _active_worker.error.connect(_active_thread.quit)

        _active_thread.start()

    # ── 中断功能 ──

    def _restore_send_btn():
        """将停止按钮恢复为发送按钮。"""
        snd.setText("发送")
        snd.setStyleSheet(
            "QPushButton {"
            "  background-color: #2E6DDE;"
            "  color: #FFFFFF;"
            "  border-radius: 6px;"
            "  padding: 6px 16px;"
            "  font-size: 11pt;"
            "}"
        )
        snd.setToolTip("发送消息")

    def _on_interrupt():
        """用户点击「停止」时中断 AI 回复。"""
        nonlocal _streaming_segments, _streaming_text, _streaming_label, _streaming_wrapper
        print(f"[DBG] User interrupted AI response", file=sys.stderr)

        # 停止流式状态
        if _state.get("streaming"):
            _state["streaming"] = False
        # 隐藏思考指示器
        _stop_thinking_indicator()
        # 清理 worker（停止 AI + 关闭授权卡片）
        _cleanup_worker()

        # 刷新已有内容到 UI
        _flush_stream()

        # 在气泡内容容器底部添加「已中断」标记
        cc = _content_container
        if cc:
            clo = cc.layout()
            interrupt_label = QLabel("── ⏹ 已中断 ──")
            interrupt_label.setAlignment(Qt.AlignCenter)
            interrupt_label.setStyleSheet(
                f"color:{_colors['muted']};font-size:9pt;padding:4px 0;"
                f"background:transparent;border:none;"
            )
            clo.addWidget(interrupt_label)

        # 系统通知（3 秒消失）
        _add_system_notification("⏹ 已中断")

        # 恢复发送按钮
        _restore_send_btn()

        # 清理流式状态变量
        _streaming_segments = []
        _streaming_text = ""
        _scroll_bottom()

    def _on_ai_finished(state, full_text, mw):
        """流完成：气泡内容已由 _flush_stream 实时渲染，只需展示 token。"""
        global _conversation_history
        nonlocal _tool_call_round, _streaming_text, _streaming_label
        nonlocal _streaming_segments, _streaming_wrapper
        # 确保思考指示器已隐藏
        _stop_thinking_indicator()
        print(f"[DBG] AI finished: len={len(full_text or '')} round={_tool_call_round}", file=sys.stderr)
        state["streaming"] = False
        text = full_text or "（空回复）"
        from workers.permission_handler import strip_permissions
        from workers.memory_handler import strip_memory_markers, apply_writes
        clean_text = strip_permissions(text)
        apply_writes(clean_text)
        text = strip_memory_markers(clean_text) or text

        # 确保最后一次 flush 渲染完整
        _streaming_text = text
        _flush_stream()

        QTimer.singleShot(5000, lambda: _schedule_indexing())

        # 展示 token 标签
        token_text = ""
        if _last_usage:
            pt = _last_usage.get("prompt_tokens", 0)
            ct = _last_usage.get("completion_tokens", 0)
            tt = _last_usage.get("total_tokens", pt + ct)
            cost = (pt * _PRICE_INPUT_PER_M + ct * _PRICE_OUTPUT_PER_M) / 1_000_000
            token_text = f"⚡ {pt} + {ct} = {tt} tokens · ¥{cost:.4f}"
        if _streaming_label:
            _streaming_label.setText(token_text)
            _streaming_label.setVisible(bool(token_text))

        # ── 显示全局「全部接受」按钮（有 pending DiffCard 时）──
        if _global_accept_btn:
            from workers.diff_widget import DiffCard, DiffState
            has_pending = False
            for s in _streaming_segments:
                w = s.get("widget")
                if isinstance(w, DiffCard) and w.state == DiffState.PENDING:
                    has_pending = True
                    break
            if has_pending:
                cnt = sum(1 for s in _streaming_segments
                          if isinstance(s.get("widget"), DiffCard)
                          and s.get("widget").state == DiffState.PENDING)
                _global_accept_btn.setText(f"✅ 全部接受（{cnt} 处）")
                _global_accept_btn.setVisible(True)

        _streaming_segments = []
        _streaming_text = ""
        _streaming_label = None
        _streaming_wrapper = None
        _conversation_history.append({"role": "assistant", "content": text})
        _update_bubble_widths()
        _scroll_bottom()
        # 恢复发送按钮
        _restore_send_btn()

    def _set_usage(usage: dict):
        nonlocal _last_usage
        _last_usage = dict(usage)

    def _on_stream_timeout(state, mw):
        if state.get("streaming"):
            _on_stream_error(state, "❌ AI 响应超时（15 秒无数据）", mw)

    def _on_stream_error(state, error, mw):
        nonlocal _tool_call_round, _streaming_segments, _streaming_text
        _stop_thinking_indicator()
        print(f"[DBG] AI error: {error[:60]} round={_tool_call_round}", file=sys.stderr)
        state["streaming"] = False
        _streaming_text = f"**{error}**"
        _flush_stream()
        _streaming_segments = []
        _streaming_text = ""
        _scroll_bottom()
        # 恢复发送按钮
        _restore_send_btn()

    # ── 后台索引调度 ──

    def _schedule_indexing():
        """对话结束后延迟触发向量索引（后台线程，不阻塞 UI）。"""
        from PyQt5.QtCore import QThreadPool
        from workers.memory_vector.indexer import IndexerWorker
        from workers.memory_handler import _DB_PATH
        if not list(_conversation_history):
            return
        worker = IndexerWorker(
            db_path=_DB_PATH,
            conv_history=list(_conversation_history),
        )
        QThreadPool.globalInstance().start(worker)

    # ── 自动审批瞬态提示 ──

    def _add_auto_approve_notification(perm_type, path):
        """在聊天区底部添加短暂提示（1.5 秒自动消失，QLabel 圆角）。"""
        display = os.path.basename(path) if path else _PERM_LABELS.get(perm_type, perm_type)
        note = QLabel(f"✅ 已自动批准: {_PERM_LABELS.get(perm_type, perm_type)} {display}")
        note.setStyleSheet(
            f"color:{_colors['warn_text']};font-size:10pt;padding:4px 10px;"
            f"background:{_colors['warn_bg']};border-radius:6px;"
        )
        note.setMaximumHeight(28)
        cl.addWidget(note)
        QTimer.singleShot(1500, note.deleteLater)
        _scroll_bottom()

    # ── 系统通知 ──

    def _add_system_notification(msg: str):
        """在聊天区底部添加系统通知（3 秒自动消失）。"""
        note = QLabel(msg)
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color:{_colors['text']};font-size:9pt;padding:6px 10px;"
            f"background:{_colors['surface']};border-radius:6px;"
            f"border:1px solid {_colors['accent']};"
        )
        cl.addWidget(note)
        QTimer.singleShot(3000, note.deleteLater)
        _scroll_bottom()

    # ── 设置弹窗 ──

    def _show_settings_dialog(parent_widget):
        """打开快速设置弹窗：运行日志 + 快捷入口到主设置页。"""
        from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                     QPushButton, QLabel, QFrame, QTextEdit)
        from PyQt5.QtCore import Qt
        from workers.permission_handler import _auto_approve_log as _aal

        dlg = QDialog(parent_widget)
        dlg.setWindowTitle("🔧 DebateClaw 运行日志")
        dlg.setFixedSize(460, 320)
        dlo = QVBoxLayout(dlg)
        dlo.setContentsMargins(16, 12, 16, 12)
        dlo.setSpacing(8)

        # ── 顶部提示 ──
        note = QLabel(
            "⚙️ 自动审批开关与黑名单请在 ⚙ 设置 → 插件页面 → DebateClaw 设置 中配置\n"
            "💡 以下日志仅记录本次运行，关闭插件后清空"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#a6adc8; font-size:10px; padding:4px 0;")
        dlo.addWidget(note)

        # ── 分隔线 ──
        sep = QFrame(frameShape=QFrame.HLine)
        sep.setStyleSheet("color:#313244;")
        dlo.addWidget(sep)

        # ── 运行日志 ──
        dlo.addWidget(QLabel("本次运行自动审批记录:"))
        log_text = QTextEdit()
        log_text.setReadOnly(True)
        log_text.setMaximumHeight(160)
        log_text.setStyleSheet("font-size:9pt; color:#cdd6f4; background:#1e1e2e; border:1px solid #313244; border-radius:4px; padding:4px;")
        if _aal:
            lines = []
            for entry in _aal:
                label = _PERM_LABELS.get(entry["type"], entry["type"])
                lines.append(f"  {entry['time']}  ✅ {label} {entry['path']}")
            log_text.setPlainText("\n".join(lines))
        else:
            log_text.setPlainText("  （暂无记录）")
        dlo.addWidget(log_text)

        # ── 底部按钮 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setFixedWidth(80)
        btn_row.addWidget(close_btn)
        dlo.addLayout(btn_row)

        close_btn.clicked.connect(dlg.accept)
        dlg.exec_()

    return panel

def _scroll_bottom(sa):
    """（旧版，兼容用）"""
    QTimer.singleShot(50, lambda: sa.verticalScrollBar().setValue(sa.verticalScrollBar().maximum()))

def _add_ai_reply(text, browser, mw):
    """在主线程添加 AI 回复气泡并更新对话历史（HTML 版）。"""
    global _conversation_history
    from PyQt5.QtCore import QTimer
    c = _detect_html_colors()
    html = _HTML_HEADER + _makeai(html.escape(text), c) + _HTML_FOOTER
    # 追加到文档
    cursor = browser.textCursor()
    cursor.movePosition(cursor.End)
    cursor.insertHtml(html)
    _conversation_history.append({"role": "assistant", "content": text})
    QTimer.singleShot(50, lambda: browser.verticalScrollBar().setValue(
        browser.verticalScrollBar().maximum()))

# ─────────────────────────────────────────────
#  生命周期
# ─────────────────────────────────────────────

def on_enable():
    api = get_api()
    api.register_panel(side="right", title="Claw", emoji="🦞",
        tooltip="打开 DebateClaw 聊天面板", create_widget=create_claw_panel,
        min_width=500, max_width=None, width_ratio=None)
    api.register_context_menu_item(
        "添加到 Claw 会话",
        lambda fp: add_file_to_session(fp, os.path.basename(fp)),
        order=50,
    )
    api.update_status("DebateClaw 插件已启用")

def _build_buttons(cfgs, api):
    btns = []
    for c in cfgs:
        kw = dict(text=c["text"], layout_mode=c.get("layout_mode","text_only"),
                  accent=c.get("accent"), auto_size=c.get("auto_size",True))
        rh = c.get("ratio_h")
        if rh is not None: kw["ratio_h"] = rh
        rv = c.get("ratio_v")
        if rv is not None: kw["ratio_v"] = rv
        btn = api.create_button(**kw)
        if "tooltip" in c: btn.setToolTip(c["tooltip"])
        btns.append(btn)
    return btns

def on_disable():
    _claw_state.clear()
    _claw_pending.clear()
    get_api().update_status("DebateClaw 插件已禁用")
