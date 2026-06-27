"""
DebateClaw AI - 插件设置页
在 ⚙️ 设置对话框的「插件页面」分区中自动展示

包含：自动审批开关 + 黑名单管理 + 安全写入模式 + 本次运行日志
"""

import json
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QFrame, QTextEdit,
)
from PyQt5.QtCore import Qt

# ═══════════════════════════════════════
#  页面元信息（必需）
# ═══════════════════════════════════════
PAGE_INFO = {
    "name": "DebateClaw",
    "icon": "🦞",
    "order": 120,
    "author": "DebateClaw",
    "version": "1.0.0",
}

# ═══════════════════════════════════════
#  页面参数配置（可选）
# ═══════════════════════════════════════
PAGE_CONFIG = {
    "save_path": "plugins/debate_claw/config/permissions.json",
    "auto_save": True,
}


def get_default_config() -> dict:
    """默认配置"""
    return {
        "auto_approve": {
            "enabled": True,
            "blacklist": [],
        },
        "safe_write_mode": {
            "enabled": False,
        },
    }


def build_page(parent_dialog, current_config: dict) -> QWidget:
    """构建设置页内容"""
    page = QWidget()
    page.setObjectName("settingsPage")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)

    # 标题
    title = QLabel("🦞 DebateClaw AI 设置")
    title.setObjectName("settingsSectionTitle")
    layout.addWidget(title)

    desc = QLabel("配置 AI 自动审批行为。自动通过低风险权限（file_read/file_list），减少手动确认。")
    desc.setObjectName("settingsSectionDesc")
    desc.setWordWrap(True)
    layout.addWidget(desc)

    # ── 自动审批开关卡片 ──
    auto_cfg = current_config.get("auto_approve", {})
    default_auto = get_default_config()["auto_approve"]

    card1 = QFrame()
    card1.setObjectName("settingsCard")
    c1l = QVBoxLayout(card1)
    c1l.setContentsMargins(20, 18, 20, 18)
    c1l.setSpacing(10)

    c1l.addWidget(QLabel("自动审批", objectName="settingsLabel"))

    cb = QCheckBox("启用 low 风险权限自动通过 (file_read / file_list)")
    cb.setObjectName("settingsCheck")
    cb.setChecked(auto_cfg.get("enabled", default_auto["enabled"]))
    page._cb_auto = cb
    c1l.addWidget(cb)

    note = QLabel("关闭后所有权限都需要您在卡片上手动确认")
    note.setStyleSheet("color: #6c7086; font-size: 10px;")
    c1l.addWidget(note)

    layout.addWidget(card1)

    # ── 黑名单管理卡片 ──
    card2 = QFrame()
    card2.setObjectName("settingsCard")
    c2l = QVBoxLayout(card2)
    c2l.setContentsMargins(20, 18, 20, 18)
    c2l.setSpacing(8)

    c2l.addWidget(QLabel("黑名单", objectName="settingsLabel"))

    c2l.addWidget(QLabel(
        "匹配模式中的文件不自动审批（支持通配符 *）",
        styleSheet="color: #6c7086; font-size: 10px;",
    ))

    # 输入行
    inp_row = QHBoxLayout()
    bl_input = QLineEdit()
    bl_input.setPlaceholderText("如 *.key  secret.txt  config/*")
    inp_row.addWidget(bl_input, 1)
    add_btn = QPushButton("+ 添加")
    add_btn.setObjectName("settingsSmallBtn")
    add_btn.setFixedWidth(60)
    inp_row.addWidget(add_btn)
    c2l.addLayout(inp_row)

    # 列表
    bl_list = QListWidget()
    bl_list.setMaximumHeight(100)
    for p in auto_cfg.get("blacklist", default_auto["blacklist"]):
        bl_list.addItem(QListWidgetItem(p))
    c2l.addWidget(bl_list)

    # 删除行
    rm_btn = QPushButton("删除选中")
    rm_btn.setObjectName("settingsSmallBtn")
    rm_btn.setFixedWidth(100)
    c2l.addWidget(rm_btn)

    page._bl_input = bl_input
    page._bl_list = bl_list

    def _add_blacklist():
        txt = bl_input.text().strip()
        if txt and txt not in [bl_list.item(i).text() for i in range(bl_list.count())]:
            bl_list.addItem(QListWidgetItem(txt))
            bl_input.clear()

    def _remove_blacklist():
        for item in bl_list.selectedItems():
            bl_list.takeItem(bl_list.row(item))

    add_btn.clicked.connect(_add_blacklist)
    bl_input.returnPressed.connect(_add_blacklist)
    rm_btn.clicked.connect(_remove_blacklist)

    layout.addWidget(card2)

    # ── 安全写入模式卡片 ──
    swm_cfg = current_config.get("safe_write_mode", {})
    default_swm = get_default_config()["safe_write_mode"]

    card3 = QFrame()
    card3.setObjectName("settingsCard")
    c3l = QVBoxLayout(card3)
    c3l.setContentsMargins(20, 18, 20, 18)
    c3l.setSpacing(10)

    c3l.addWidget(QLabel("安全写入模式", objectName="settingsLabel"))

    cb_swm = QCheckBox("启用安全写入模式（禁用 AI 直接写入文件，仅允许 [DIFF] 修改建议）")
    cb_swm.setObjectName("settingsCheck")
    cb_swm.setChecked(swm_cfg.get("enabled", default_swm["enabled"]))
    page._cb_safe_write = cb_swm
    c3l.addWidget(cb_swm)

    note_swm = QLabel(
        "开启后 AI 无法调用 file_write 工具，只能输出 [DIFF] 格式的修改建议。\n"
        "您可在对话面板标题栏 🔒/🔓 按钮快速切换此模式。"
    )
    note_swm.setWordWrap(True)
    note_swm.setStyleSheet("color: #6c7086; font-size: 10px;")
    c3l.addWidget(note_swm)

    layout.addWidget(card3)

    # ── 运行日志 ──
    log_card = QFrame()
    log_card.setObjectName("settingsCard")
    ll = QVBoxLayout(log_card)
    ll.setContentsMargins(20, 12, 20, 12)
    ll.setSpacing(6)
    ll.addWidget(QLabel("本次运行自动审批记录", objectName="settingsLabel"))
    ll.addWidget(QLabel(
        "以下日志仅记录本次运行，关闭插件后清空",
        styleSheet="color: #6c7086; font-size: 10px;",
    ))

    from workers.permission_handler import _auto_approve_log as _alog
    log_view = QTextEdit()
    log_view.setReadOnly(True)
    log_view.setMaximumHeight(80)
    log_view.setStyleSheet(
        "font-size:9pt; color:#cdd6f4; background:#1e1e2e;"
        " border:1px solid #313244; border-radius:4px; padding:4px;"
    )
    if _alog:
        log_lines = []
        for entry in _alog:
            label = {
                "file_read": "读取文件", "file_list": "列出目录",
                "file_write": "写入文件", "search": "搜索",
                "network": "网络", "execute": "执行代码",
            }.get(entry["type"], entry["type"])
            log_lines.append(f"  {entry['time']}  ✅ {label} {entry['path']}")
        log_view.setPlainText("\n".join(log_lines))
    else:
        log_view.setPlainText("  （暂无记录）")
    ll.addWidget(log_view)
    layout.addWidget(log_card)

    layout.addStretch()
    return page


def collect_config(page_widget: QWidget) -> dict:
    """从页面控件收集当前配置"""
    bl = []
    for i in range(page_widget._bl_list.count()):
        bl.append(page_widget._bl_list.item(i).text())
    config = {
        "auto_approve": {
            "enabled": page_widget._cb_auto.isChecked(),
            "blacklist": bl,
        },
        "safe_write_mode": {
            "enabled": page_widget._cb_safe_write.isChecked(),
        },
    }
    # 同步写入 permissions.json
    _save_to_permissions_json(config)
    return config


def _save_to_permissions_json(config: dict):
    """将自动审批配置写入 permissions.json"""
    try:
        cfg_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "config", "permissions.json",
        )
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"always_granted": [], "always_denied": [], "pending_requests": {}}
        data["auto_approve"] = config["auto_approve"]
        data["safe_write_mode"] = config["safe_write_mode"]
        os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[DebateClaw] 保存自动审批配置失败: {e}")


def get_safe_write_mode_default() -> bool:
    """从 permissions.json 读取安全写入模式默认状态。"""
    try:
        cfg_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "config", "permissions.json",
        )
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("safe_write_mode", {}).get("enabled", False)
    except Exception:
        pass
    return False
