"""
DebateClaw AI 权限管理
====================
职责: 扫描 [PERM:type] 标记、读写配置、创建授权 UI 卡片。
"""

import fnmatch
import json, os, re, sys
from dataclasses import dataclass, field
from typing import Optional
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "config", "permissions.json")

# ── 主题检测 ──
_NOTION_IS_DARK = True  # 默认深色
try:
    _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    _cfg_path = os.path.join(_PROJECT_ROOT, "config", "config.json")
    with open(_cfg_path) as f:
        _theme = json.load(f).get("theme", "notion_dark")
        _NOTION_IS_DARK = "light" not in _theme.lower()
except Exception:
    pass

# ── 权限标记正则 ──
# 支持 [PERM:type] 和 [PERM:type path] 两种格式
_RE_PERM = re.compile(r'^\[PERM:(\w+)(?:\s+(.+?))?\]$', re.MULTILINE)

_PERM_LABELS = {
    "file_read":   "读取文件",
    "file_write":  "写入/保存文件",
    "file_list":   "列出目录",
    "search":      "搜索文件",
    "network":     "网络访问",
    "execute":     "执行代码/命令",
}

# 权限风险等级（用于 UI 样式区分）
_PERM_RISK_LEVEL = {
    "file_read":   "low",      # 安全读操作，可自动批准
    "file_list":   "low",      # 列目录，安全
    "file_write":  "medium",   # 写操作，需确认
    "search":      "low",      # 搜索文件，低风险
    "network":     "high",     # 网络访问，严重警告
    "execute":     "high",     # 代码执行，沙箱限制
}


# ══════════════════════════════════════════
#  配置读写
# ══════════════════════════════════════════

def load_permissions() -> dict:
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"always_granted": [], "always_denied": [], "pending_requests": {}}


def save_permissions(data: dict):
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def scan_permissions(text: str) -> dict[str, str]:
    """扫描文本中的 [PERM:xxx] 或 [PERM:xxx path] 标记，返回 {type: path_or_label} 字典。

    对于有路径的标记（如 [PERM:file_read /path/to/file.txt]），返回完整路径；
    对于无路径的标记，返回类型标签。
    """
    found = {}
    for m in _RE_PERM.finditer(text):
        t = m.group(1)
        if t in _PERM_LABELS and t not in found:
            # group(2) 是可选的路径参数
            path = m.group(2).strip() if m.group(2) else _PERM_LABELS[t]
            found[t] = path
    return found


def get_perm_display_label(perm_type: str, perm_path: str) -> str:
    """获取权限卡片显示用的标签。

    对于 file_read/file_write，只显示文件名；其他显示原始路径或标签。
    """
    if perm_type in ("file_read", "file_write") and perm_path:
        return os.path.basename(perm_path)
    if perm_type == "file_list" and perm_path:
        return os.path.basename(os.path.normpath(perm_path))
    if perm_type == "network" and perm_path:
        # 显示 URL 或搜索关键词（截断过长）
        display = perm_path[:40] + "..." if len(perm_path) > 40 else perm_path
        return f"访问: {display}"
    return _PERM_LABELS.get(perm_type, perm_path)


def strip_permissions(text: str) -> str:
    """移除文本中的 [PERM:xxx] 行。"""
    return _RE_PERM.sub("", text).strip()


def check_already(perm_type: str) -> str | None:
    """返回 'granted', 'denied' 或 None（未决定）。"""
    cfg = load_permissions()
    if perm_type in cfg.get("always_granted", []):
        return "granted"
    if perm_type in cfg.get("always_denied", []):
        return "denied"
    return None


def set_always(perm_type: str, granted: bool):
    """将权限存入「总是」列表。"""
    cfg = load_permissions()
    if granted:
        if perm_type not in cfg.setdefault("always_granted", []):
            cfg["always_granted"].append(perm_type)
        if perm_type in cfg.setdefault("always_denied", []):
            cfg["always_denied"].remove(perm_type)
    else:
        if perm_type not in cfg.setdefault("always_denied", []):
            cfg["always_denied"].append(perm_type)
        if perm_type in cfg.setdefault("always_granted", []):
            cfg["always_granted"].remove(perm_type)
    save_permissions(cfg)


def get_risk_level(perm_type: str) -> str:
    """获取权限风险等级：low / medium / high"""
    return _PERM_RISK_LEVEL.get(perm_type, "medium")


# ══════════════════════════════════════════
#  自动审批配置
# ══════════════════════════════════════════

# 本次运行自动审批日志（模块级，垮模块共享）
_auto_approve_log: list[dict] = []  # [{time, type, path, result}, ...]


@dataclass
class AutoApproveConfig:
    """自动审批配置。"""
    enabled: bool = True
    blacklist: list[str] = field(default_factory=list)  # glob patterns


def get_auto_config() -> AutoApproveConfig:
    """读取自动审批配置。"""
    cfg = load_permissions()
    auto_cfg = cfg.setdefault("auto_approve", {})
    return AutoApproveConfig(
        enabled=auto_cfg.get("enabled", True),
        blacklist=auto_cfg.get("blacklist", []),
    )


def set_auto_config(config: AutoApproveConfig):
    """保存自动审批配置。"""
    cfg = load_permissions()
    cfg["auto_approve"] = {
        "enabled": config.enabled,
        "blacklist": config.blacklist,
    }
    save_permissions(cfg)


def _match_blacklist(path: str, patterns: list[str]) -> bool:
    """检查路径是否匹配黑名单中的任意通配符模式。

    匹配方式：
    - 纯文件名匹配：'secret.txt' 匹配路径末尾的 'secret.txt'
    - 带路径的匹配：'config/*' 匹配 'config/settings.ini'
    - 扩展名匹配：'*.key' 匹配任何 .key 结尾的文件
    - 前缀匹配：'密码*.*' 匹配 '密码文件.txt'
    """
    if not patterns or not path:
        return False
    basename = os.path.basename(path)
    for pattern in patterns:
        if not pattern.strip():
            continue
        pattern = pattern.strip()
        # 先匹配完整路径
        if fnmatch.fnmatch(path, pattern):
            return True
        # 再匹配纯文件名
        if fnmatch.fnmatch(basename, pattern):
            return True
        # 最后匹配路径中任何部分（如 config/*）
        norm_path = path.replace("\\", "/")
        norm_pattern = pattern.replace("\\", "/")
        if fnmatch.fnmatch(norm_path, norm_pattern):
            return True
    return False


def check_auto_approve(perm_type: str, path: str | None = None) -> bool:
    """检查指定权限是否应自动批准。

    Args:
        perm_type: 权限类型
        path: 操作路径（可选，用于黑名单匹配）

    Returns:
        True 表示应自动批准，False 表示需用户确认
    """
    # 只有 low 风险可自动批准
    if get_risk_level(perm_type) != "low":
        return False
    # 读取配置
    config = get_auto_config()
    if not config.enabled:
        return False
    # 黑名单检查
    if path and _match_blacklist(path, config.blacklist):
        return False
    return True


# ══════════════════════════════════════════
#  授权 UI 卡片
# ══════════════════════════════════════════

class PermissionAuthCard(QFrame):
    """弹入式权限授权卡片，位于输入区上方。

    支持 normal / high_risk 两种样式，network/execute 使用 high_risk 样式。
    """

    # 用户响应 -> (perm_type, "once"|"always"|"deny")
    responded = pyqtSignal(str, str)

    def __init__(self, perm_type: str, perm_label: str, parent=None,
                 risk_level: str = "medium", code_preview: str = None):
        super().__init__(parent)
        self._perm_type = perm_type
        self._risk_level = risk_level
        self.setObjectName("clawPermCard")
        self.setStyleSheet(_card_qss(risk_level))
        self.setFrameShape(QFrame.StyledPanel)

        # 卡片高度（不含代码预览额外增加）
        if risk_level == "high":
            base_h = 130 if not code_preview else 170
        else:
            base_h = 110
        self.setFixedHeight(base_h)

        lo = QVBoxLayout(self)
        lo.setContentsMargins(14, 8, 14, 8)
        lo.setSpacing(6)

        # 标题行：根据风险等级显示不同图标和颜色
        if risk_level == "high":
            icon = "⚠"
            title_text = f"{icon} 危险操作确认：{perm_label}"
            warning_hint = QLabel("⛔ AI 将访问外部资源或执行代码，请仔细确认", objectName="clawPermWarning")
            warning_hint.setFont(QFont("HarmonyOS Sans SC", 9))
            lo.addWidget(warning_hint)
        else:
            icon = "🔐"
            title_text = f"{icon} AI 请求授权：{perm_label}"

        title = QLabel(title_text, objectName="clawPermTitle")
        lo.addWidget(title)

        # 代码预览区域（execute 权限专用）
        if code_preview:
            code_area = QFrame(objectName="clawCodePreview")
            code_lo = QVBoxLayout(code_area); code_lo.setContentsMargins(8,4,8,4)
            code_lb = QLabel(code_preview[:200] + ("..." if len(code_preview) > 200 else ""),
                           objectName="clawCodeLabel")
            code_lb.setFont(QFont("Consolas", 9))
            code_lb.setStyleSheet("background:transparent;")
            code_lb.setWordWrap(True)
            code_lo.addWidget(code_lb)
            lo.addWidget(code_area)

        # 按钮行
        bl = QHBoxLayout()
        bl.setSpacing(8)
        bl.addStretch()

        btn_once = QPushButton("仅一次")
        btn_once.setObjectName("clawPermOnce")
        btn_once.clicked.connect(self._on_once)
        bl.addWidget(btn_once)

        btn_always = QPushButton("总是")
        btn_always.setObjectName("clawPermAlways")

        # network 权限禁用"总是允许"
        if perm_type == "network":
            btn_always.setEnabled(False)
            btn_always.setToolTip("网络权限不支持自动授权")
        else:
            btn_always.clicked.connect(self._on_always)

        # btn_always 样式已由 _card_qss 中 QPushButton#clawPermAlways 统一控制

        bl.addWidget(btn_always)

        btn_deny = QPushButton("不允许")
        btn_deny.setObjectName("clawPermDeny")
        btn_deny.clicked.connect(lambda: self._respond("deny"))
        bl.addWidget(btn_deny)

        lo.addLayout(bl)

    def _on_once(self):
        self._respond("once")

    def _on_always(self):
        from workers.plugin_manager import get_api
        api = get_api()
        label = _PERM_LABELS.get(self._perm_type, self._perm_type)
        confirmed = api.show_confirm(
            "⚠ 永久授权确认",
            f"确认要「总是」授予「{label}」权限？\n\n"
            "此操作将跳过后续所有同类授权请求，AI 可在无确认的情况下使用该权限。",
            ok_text="确认授权",
            cancel_text="取消",
        )
        if confirmed:
            self._respond("always")

    def _respond(self, mode: str):
        self.setParent(None)  # 立即从布局中移除，防止 pending delete 导致布局索引错乱
        self.deleteLater()
        self.responded.emit(self._perm_type, mode)


def _card_qss(risk_level: str = "medium") -> str:
    """根据风险等级和当前主题返回卡片 QSS。"""
    # ── 主题色值 ──
    if _NOTION_IS_DARK:
        bg       = "#1E2025"   # surface
        bd       = "#2C2E36"   # divider
        text     = "#E0E0E0"   # text
        subtext  = "#A0A0A0"   # subtext
        btn_blue = "#2E6DDE"   # accent
        btn_txt  = "#FFFFFF"
        danger   = "#D32F2F"   # red
        yellow   = "#E5C07B"   # yellow border
        code_clr = "#B0B0B0"
    else:
        bg       = "#FFFFFF"   # white
        bd       = "#EDEDEB"   # divider
        text     = "#37352F"   # text
        subtext  = "#9B9A97"   # subtext
        btn_blue = "#2E6DDE"   # accent
        btn_txt  = "#FFFFFF"
        danger   = "#D32F2F"   # red
        yellow   = "#E5C07B"   # yellow border
        code_clr = "#666666"

    # ── 公共按钮 QSS（按钮加高 padding:6px 14px）──
    btn_common = (
        f"QPushButton{{font-family:'HarmonyOS Sans SC';font-size:10pt;"
        f"  border-radius:4px;padding:6px 14px;background:transparent;"
        f"  border:1px solid {bd};color:{text};}}"
        f"QPushButton#clawPermOnce{{background-color:{btn_blue};color:{btn_txt};border:none;}}"
        f"QPushButton#clawPermAlways{{background-color:{danger};color:{btn_txt};border:none;}}"
        f"QPushButton#clawPermAlways:disabled{{background-color:{bd};color:{subtext};border:none;}}"
        f"QPushButton#clawPermDeny{{border:1px solid {bd};color:{subtext};}}"
    )

    # ── 代码预览 ──
    code_qss = (
        f"QFrame#clawCodePreview{{"
        f"  background:transparent;border:1px solid {bd};border-radius:4px;}}"
        f"QLabel#clawCodeLabel{{color:{code_clr};background:transparent;}}"
    )

    if risk_level == "high":
        return (
            f"QFrame#clawPermCard{{"
            f"  background-color:{bg};"
            f"  border:3px solid {danger};border-radius:8px;}}"
            f"QLabel{{background:transparent;}}"
            f"QLabel#clawPermTitle{{color:{danger};font-weight:bold;"
            f"  font-family:'HarmonyOS Sans SC';font-size:11pt;}}"
            f"QLabel#clawPermWarning{{color:{yellow};"
            f"  font-family:'HarmonyOS Sans SC';font-size:9pt;}}"
            + btn_common + code_qss
        )
    elif risk_level == "low":
        return (
            f"QFrame#clawPermCard{{"
            f"  background-color:{bg};"
            f"  border:3px solid {yellow};border-radius:8px;}}"
            f"QLabel{{background:transparent;}}"
            f"QLabel#clawPermTitle{{color:{text};font-weight:bold;"
            f"  font-family:'HarmonyOS Sans SC';font-size:11pt;}}"
            + btn_common + code_qss
        )
    else:  # medium
        return (
            f"QFrame#clawPermCard{{"
            f"  background-color:{bg};"
            f"  border:1px solid {bd};border-radius:8px;}}"
            f"QLabel{{background:transparent;}}"
            f"QLabel#clawPermTitle{{color:{text};font-weight:bold;"
            f"  font-family:'HarmonyOS Sans SC';font-size:11pt;}}"
            + btn_common + code_qss
        )


# ══════════════════════════════════════════
#  路径解析（相对路径 → 项目绝对路径）
# ══════════════════════════════════════════

def _resolve_project_path(raw_path: str) -> str:
    """将相对路径解析为项目根目录下的绝对路径。

    如果 raw_path 已是绝对路径，直接返回；
    如果是相对路径，拼接项目根目录后返回。
    项目根目录通过插件 API 获取，回退到 StarDebate 项目根目录。
    如果解析后路径不存在，再回退到 StarDebate 项目根。
    """
    if os.path.isabs(raw_path):
        norm = os.path.normpath(raw_path)
        exists = os.path.exists(norm)
        print(f"[DBG] _resolve_project_path: abs path={norm} exists={exists}", file=sys.stderr)
        return norm

    # 内建回退根：permission_handler.py 位于 plugins/debate_claw/workers/ 下
    _FALLBACK_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))

    # 获取项目根目录
    proot = None
    try:
        from workers.plugin_manager import get_api as _get_api
        _api = _get_api()
        if _api:
            proot = _api.get_current_project_path()
    except Exception:
        pass

    if not proot:
        proot = _FALLBACK_ROOT

    resolved = os.path.normpath(os.path.join(proot, raw_path))

    # 如果解析后路径不存在，回退到 StarDebate 项目根
    if not os.path.exists(resolved):
        resolved = os.path.normpath(os.path.join(_FALLBACK_ROOT, raw_path))

    print(f"[DBG] _resolve_project_path: raw={raw_path} proot={proot} -> {resolved} exists={os.path.exists(resolved)}", file=sys.stderr)

    return resolved


# ══════════════════════════════════════════
#  权限执行
# ══════════════════════════════════════════

def execute_permission(perm_type: str, path: str, **kwargs) -> str:
    """执行权限操作，返回执行结果文本。

    支持的权限类型:
        file_read   - 读取文件内容
        file_write  - 写入文件（AI 提供路径和内容）
        file_list   - 列出目录文件
        search      - 搜索资料池/项目关键词
        network     - 联网搜索或抓取 URL（默认关闭）
        execute     - 执行代码（沙箱限制）

    Args:
        perm_type: 权限类型
        path: 操作路径/参数
        **kwargs: 额外参数，如 file_write 的 content、execute 的 code 等

    Returns:
        执行结果的文本描述

    Raises:
        PermissionError: 权限类型不支持或操作失败
    """
    # 文件/目录操作：将相对路径解析为项目绝对路径
    if perm_type in ("file_read", "file_write", "file_list"):
        path = _resolve_project_path(path)

    print(f"[DBG] execute_permission: type={perm_type} resolved_path={path[:80]}", file=sys.stderr)

    if perm_type == "file_read":
        return _exec_file_read(path)
    elif perm_type == "file_write":
        content = kwargs.get("content", "")
        return _exec_file_write(path, content)
    elif perm_type == "file_list":
        return _exec_file_list(path)
    elif perm_type == "search":
        return _exec_search(path)
    elif perm_type == "network":
        # 先检查是否启用
        if not check_network_enabled():
            raise PermissionError("网络权限未启用。请在设置中开启 network_enabled")
        return _exec_network_fetch(path)
    elif perm_type == "execute":
        code = kwargs.get("code", "")
        from workers.execute_sandbox import safe_execute as _safe_exec
        return _safe_exec(code)
    else:
        raise PermissionError(f"未知权限类型: {perm_type}")


def check_network_enabled() -> bool:
    """检查网络权限是否已启用。"""
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "config", "ai_config.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return cfg.get("network_enabled", False)
    except Exception:
        return False





def _exec_file_read(file_path: str) -> str:
    """读取文件并返回内容摘要。"""
    print(f"[DBG] _exec_file_read: path={file_path} exists={os.path.exists(file_path)}", file=sys.stderr)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 如果文件过大（>50KB），只返回前 5000 字符
        MAX_CONTENT_LEN = 50000
        PREVIEW_LEN = 5000
        if len(content) > MAX_CONTENT_LEN:
            return (
                f"文件: {os.path.basename(file_path)}\n"
                f"大小: {len(content):,} 字符\n"
                f"--- 内容预览（前 {PREVIEW_LEN} 字符）---\n\n"
                f"{content[:PREVIEW_LEN]}\n\n"
                f"[... 文件过长，已截断 ...]"
            )

        return (
            f"文件: {os.path.basename(file_path)}\n"
            f"大小: {len(content):,} 字符\n"
            f"--- 完整内容 ---\n\n"
            f"{content}\n```\n"
        )
    except UnicodeDecodeError:
        for enc in ("gbk", "gb2312", "latin-1"):
            try:
                with open(file_path, "r", encoding=enc) as f:
                    content = f.read()
                return (
                    f"文件: {os.path.basename(file_path)} (编码: {enc})\n"
                    f"大小: {len(content):,} 字符\n"
                    f"--- 内容 ---\n\n{content}\n"
                )
            except Exception:
                continue
        # ── 所有文本编码都失败 → 尝试用 file_parser 解析二进制格式 ──
        try:
            from workers.material_pool.file_parser import FileParser
            parsed = FileParser.parse(file_path)
            if parsed.get("success"):
                text = parsed.get("text", "")
                total = parsed.get("total_chars", 0)
                preview = text[:5000] + ("\n[... 过长截断]" if len(text) > 5000 else "")
                return (
                    f"文件: {os.path.basename(file_path)}"
                    f" ({parsed.get('file_type', 'binary')})\n"
                    f"大小: {total:,} 字符\n"
                    f"--- 内容 ---\n\n{preview}\n"
                )
            else:
                err = parsed.get("error", "未知错误")
                raise PermissionError(f"解析文件失败: {err}")
        except ImportError:
            raise PermissionError(
                f"无法读取二进制文件: {file_path}\n"
                f"（需要安装 python 库: openpyxl / pdfplumber / python-docx）"
            )
        except Exception as ex:
            raise PermissionError(f"解析文件失败: {ex}")
    except Exception as ex:
        raise PermissionError(f"读取文件失败: {ex}")


def _strip_markdown(text: str) -> str:
    """移除文本中的 Markdown 符号，保留纯文本内容。

    处理规则：
    - `#` 标题 → 移除 `#` 前缀
    - `**bold**` / `*italic*` → 去掉 `*`
    - 行首 `- ` / `* ` 列表标记 → 去掉
    - `> ` 引用 → 去掉
    - ```code``` → 去掉代码块标记
    - `[text](url)` → text
    - 行内 `` `code` `` → code
    - `---` / `***` 分割线 → 空行
    - 行首 `1. ` 数字列表 → 去掉编号
    """
    lines = text.split("\n")
    out = []
    in_code_block = False
    for line in lines:
        # 代码块
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue  # 跳过 ``` 标记本身
        if in_code_block:
            out.append(line)
            continue

        # 引用
        if stripped.startswith(">"):
            line = re.sub(r'^>+\s*', '', line)

        # 标题
        line = re.sub(r'^#{1,6}\s+', '', line)

        # 列表标记
        line = re.sub(r'^[\*\-\+]\s+', '', line)
        line = re.sub(r'^\d+\.\s+', '', line)

        # 分割线
        if re.match(r'^[-*_]{3,}\s*$', line.strip()):
            out.append("")
            continue

        # 链接 [text](url) → text
        line = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', line)
        # 图片 ![alt](url) → alt
        line = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', line)
        # 行内代码 `code` → code
        line = re.sub(r'`([^`]+)`', r'\1', line)
        # 加粗/斜体 ** ** * *
        line = re.sub(r'\*\*([^*]+)\*\*', r'\1', line)
        line = re.sub(r'\*([^*]+)\*', r'\1', line)
        # 删除线 ~~ ~~
        line = re.sub(r'~~([^~]+)~~', r'\1', line)

        out.append(line)

    return "\n".join(out).strip()


def _is_speech_json_path(file_path: str) -> bool:
    """判断路径是否指向一辩稿 JSON 文件（speech_pro.json / speech_con.json）。"""
    basename = os.path.basename(file_path).lower()
    return basename in ("speech_pro.json", "speech_con.json")


def _exec_file_write(file_path: str, content: str) -> str:
    """写入或修改文件。

    特殊处理：
    - 一辩稿 JSON：自动移除 MD 符号 → 包装为标准 JSON 结构后写入
    - 其他 .json：自动包装为 {"content": ...} 确保 JSON 合法
    - 非 .json：直接写入
    """
    try:
        dir_name = os.path.dirname(file_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

        mode = "修改" if os.path.exists(file_path) else "新建"
        write_content = content
        write_note = ""

        # ── 一辩稿 .json — 纯文本 → 标准 JSON ──
        if _is_speech_json_path(file_path):
            plain = _strip_markdown(content)
            speech_data = {
                "content": plain,
                "custom_glossary": {} if not os.path.exists(file_path) else (
                    json.load(open(file_path, "r", encoding="utf-8")).get("custom_glossary", {})
                    if os.path.getsize(file_path) > 0 else {}
                ),
                "structure_tree": [],
                "keywords": [],
            }
            # 尽量保留旧文件中的结构和词汇
            try:
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    with open(file_path, "r", encoding="utf-8") as f:
                        old = json.load(f)
                    speech_data["custom_glossary"] = old.get("custom_glossary", {})
                    speech_data["structure_tree"] = old.get("structure_tree", [])
                    speech_data["keywords"] = old.get("keywords", [])
            except Exception:
                pass
            write_content = json.dumps(speech_data, ensure_ascii=False, indent=2)
            write_note = f" [纯文本→JSON包装]"

        # ── 其他 .json — 自动包装为 {content: ...} ──
        elif file_path.lower().endswith(".json"):
            # 如果内容本身还不是 JSON 结构，包装为 {"content": ...}
            try:
                json.loads(content)
                # 已经是合法 JSON，直接写入
            except (json.JSONDecodeError, ValueError):
                wrapped = {"content": content}
                write_content = json.dumps(wrapped, ensure_ascii=False, indent=2)
                write_note = f" [包装为JSON]"

        # ── 写入 ──
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(write_content)

        return (
            f"✅ 文件{mode}成功:\n"
            f"  路径: {file_path}\n"
            f"  大小: {len(write_content):,} 字符\n"
            f"  操作: {mode}{write_note}"
        )
    except PermissionError as ex:
        raise PermissionError(f"写入权限不足: {ex}")
    except Exception as ex:
        raise PermissionError(f"写入文件失败: {ex}")


def _exec_file_list(directory: str) -> str:
    """列出目录中的文件和子目录。"""
    print(f"[DBG] _exec_file_list: dir={directory} isdir={os.path.isdir(directory)}", file=sys.stderr)
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"目录不存在: {directory}")

    try:
        items = []
        for name in sorted(os.listdir(directory)):
            full_path = os.path.join(directory, name)
            if os.path.isfile(full_path):
                size = os.path.getsize(full_path)
                size_str = f"{size:,} B" if size < 1024 else f"{size/1024:.1f} KB"
                items.append(f"📄 {name} ({size_str})")
            elif os.path.isdir(full_path):
                items.append(f"📁 {name}/")
            else:
                items.append(f"  {name}")

        if not items:
            return f"目录为空: {directory}"

        return (
            f"📂 目录: {os.path.abspath(directory)}\n"
            f"共 {len(items)} 项:\n\n"
            + "\n".join(items[:100]) +
            (f"\n\n[... 共 {len(items)} 项，仅显示前 100 项 ...]" if len(items) > 100 else "")
        )
    except PermissionError:
        raise PermissionError(f"无权限访问目录: {directory}")
    except Exception as ex:
        raise PermissionError(f"列出目录失败: {ex}")


def _exec_search(query: str) -> str:
    """在资料池/项目中搜索关键词。"""
    from workers.search_worker import search_files as _search_files
    return _search_files(query)


def _exec_network_fetch(url_or_query: str) -> str:
    """联网搜索或抓取 URL。"""
    from workers.search_worker import network_search as _net_search
    return _net_search(url_or_query)
