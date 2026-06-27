"""
关于 - 应用信息设置页（含更新器入口）— PyQt-SiliconUI 版
"""

import os
import logging

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QPushButton, QBoxLayout, QLabel,
)

# PyQt-SiliconUI 重构版组件
from siui.components.widgets import SiLabel
from siui.components.button import SiPushButtonRefactor, SiLongPressButtonRefactor
from siui.core import SiColor, SiGlobal

from components.theme_colors import tc

from workers.updater.update_utils import (
    list_backups, delete_backup, restore_config_from_backup,
)
from components.popup_dialog import CustomDialog

_logger = logging.getLogger("StarDebate.settings.about_page")


# ═══════════════════════════════════════
#  页面元信息
# ═══════════════════════════════════════

PAGE_INFO = {
    "id": "about_page",
    "name": "关于",
    "icon": "ℹ️",
    "order": 90,
    "author": "StarDebate",
    "version": "2.0.0",
}

PAGE_CONFIG = {
    "save_path": "config/config.json",
    "auto_save": True,
}


def get_default_config() -> dict:
    return {
        "version": "1.2.0",
        "developer_mode": False,
        "disabled_features": ["debug_console"],
    }


# ═══════════════════════════════════════
#  SiUI 通用辅助
# ═══════════════════════════════════════

def _safe_set_style_data(target, attr, color_str: str):
    """安全设置 SiUI style_data 属性，失败时静默跳过。"""
    try:
        setattr(target.style_data, attr, QColor(color_str))
    except Exception:
        _logger.warning("无法设置 style_data.%s", attr, exc_info=True)


def _safe_create_card(page) -> QWidget | None:
    """尝试创建 SiPanelCard，失败时返回 None。"""
    try:
        from siui.components.container import SiPanelCard
        card = SiPanelCard(page, direction=QBoxLayout.TopToBottom)
        _safe_set_style_data(card, "background_fore_color", tc("surface"))
        _safe_set_style_data(card, "background_back_color", tc("surface"))
        cl = card.layout()
        if cl is not None and hasattr(cl, "setSpacing"):
            cl.setSpacing(0)
        if hasattr(card, "muteStretchWidget"):
            card.muteStretchWidget()
        card.setContentsMargins(20, 18, 20, 18)
        return card
    except Exception:
        _logger.exception("创建 SiPanelCard 失败")
        return None


def _make_sep() -> QFrame:
    """创建水平分隔线。"""
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setStyleSheet(f"color: {tc('border')};")
    sep.setFixedHeight(2)
    return sep


def _add_silabel(parent, text: str, color_key=SiColor.TEXT_B,
                 word_wrap: bool = False, min_height: int | None = None) -> SiLabel | None:
    """添加带 fallback 的 SiLabel。"""
    try:
        lbl = SiLabel(parent)
        lbl.setText(text)
        lbl.setTextColor(lbl.getColor(color_key))
        lbl.setStyleSheet("background: transparent;")
        if word_wrap:
            lbl.setWordWrap(True)
        if min_height is not None:
            lbl.setMinimumHeight(min_height)
        if hasattr(parent, "addWidget"):
            parent.addWidget(lbl)
        elif parent.layout() is not None:
            parent.layout().addWidget(lbl)
        return lbl
    except Exception:
        _logger.warning("SiLabel(%s) 创建失败", text[:20], exc_info=True)
        return None


def _make_transparent_row(parent) -> QWidget:
    """创建透明背景的行容器。"""
    row = QWidget(parent)
    row.setAttribute(Qt.WA_StyledBackground, True)
    row.setStyleSheet("background: transparent;")
    return row


# ═══════════════════════════════════════
#  卡片构建函数
# ═══════════════════════════════════════

def _add_value_row(parent, label: str, value: str) -> SiLabel | None:
    """向卡片添加一行「标签: 值」，返回值 SiLabel（可能为 None）。"""
    row = _make_transparent_row(parent)
    rl = QHBoxLayout(row)
    rl.setContentsMargins(0, 0, 0, 0)
    val_lbl = None
    try:
        val_lbl = SiLabel(parent)
        val_lbl.setText(value)
        val_lbl.setTextColor(val_lbl.getColor(SiColor.TEXT_D))
        val_lbl.setStyleSheet("background: transparent;")
        val_lbl.setMinimumHeight(36)
        rl.addWidget(val_lbl)
    except Exception:
        pass
    rl.addStretch()
    parent.addWidget(row)
    return val_lbl


def _build_app_info_card(page, layout, current_config):
    """应用信息卡片。"""
    card = _safe_create_card(page)
    if card is None:
        return
    _add_silabel(card, "应用名称", SiColor.TEXT_B)
    _add_value_row(card, "应用名称", "StarDebate 辩之星")

    card.addWidget(_make_sep())

    _add_silabel(card, "应用版本", SiColor.TEXT_B)
    lbl_ver = _add_value_row(card, "应用版本", current_config.get("version", "1.2.0"))

    card.addWidget(_make_sep())

    _add_silabel(card, "开发者", SiColor.TEXT_B)
    _add_value_row(card, "开发者", "Oblivion")

    layout.addWidget(card)
    page._lbl_version = lbl_ver


def _add_info_row(parent, key: str, val: str) -> QWidget:
    """向卡片添加一行「键=值」信息行，含 fallback。"""
    row = _make_transparent_row(parent)
    rl = QHBoxLayout(row)
    rl.setContentsMargins(0, 0, 0, 0)
    rl.setSpacing(12)
    try:
        lk = SiLabel(parent)
        lk.setText(key)
        lk.setTextColor(lk.getColor(SiColor.TEXT_B))
        lk.setStyleSheet("background: transparent;")
        lk.setFixedWidth(80)
        rl.addWidget(lk)
    except Exception:
        label_kw = QLabel(key)
        label_kw.setStyleSheet(f"color: {tc('text')}; font-weight: 600;")
        label_kw.setFixedWidth(80)
        rl.addWidget(label_kw)
    try:
        lv = SiLabel(parent)
        lv.setText(val)
        lv.setTextColor(lv.getColor(SiColor.TEXT_D))
        lv.setWordWrap(True)
        lv.setStyleSheet("background: transparent;")
        rl.addWidget(lv, stretch=1)
    except Exception:
        label_vw = QLabel(val)
        label_vw.setWordWrap(True)
        rl.addWidget(label_vw, stretch=1)
    parent.addWidget(row)
    return row


def _build_about_card(page, layout):
    """关于 StarDebate 卡片。"""
    card = _safe_create_card(page)
    if card is None:
        return
    _add_silabel(card, "关于 StarDebate", SiColor.TEXT_B)
    info_items = [
        ("平台定位", "辩论模拟训练平台"),
        ("技术栈", "PyQt5 + DeepSeek API"),
        ("功能模块", "AI辩论分析 / 模拟质询 / 立论驳论训练 / 插件系统"),
    ]
    for key, val in info_items:
        _add_info_row(card, key, val)
    layout.addWidget(card)


def _build_update_card(page, layout, parent_dialog):
    """更新管理卡片。"""
    card = _safe_create_card(page)
    if card is None:
        return
    btn_row_w = _make_transparent_row(card)
    btn_row = QHBoxLayout(btn_row_w)
    btn_row.setContentsMargins(0, 0, 0, 0)
    btn_row.setSpacing(10)

    # ── 本地补丁按钮 ────────────────────────────────────────────
    try:
        btn_upd = SiPushButtonRefactor(card)
        btn_upd.setText("选择更新包")
        _safe_set_style_data(btn_upd, "button_color", tc("accent_blue"))
        _safe_set_style_data(btn_upd, "background_color", tc("accent_blue_deep"))
        _safe_set_style_data(btn_upd, "text_color", tc("white"))
        _safe_set_style_data(btn_upd, "hover_color", tc("accent_blue_hover"))
        _safe_set_style_data(btn_upd, "click_color", tc("accent_blue_pressed"))
        btn_upd.setMinimumHeight(36)
        btn_upd.setMinimumWidth(140)
        btn_upd.clicked.connect(lambda: _on_select_update(parent_dialog))
        btn_row.addWidget(btn_upd)
    except Exception:
        _logger.warning("SiPushButtonRefactor(选择更新包) 创建失败", exc_info=True)

    # ── GitHub 检查更新按钮 ─────────────────────────────────────
    try:
        btn_github = SiPushButtonRefactor(card)
        btn_github.setText("检查更新")
        _safe_set_style_data(btn_github, "button_color", tc("accent_green"))
        _safe_set_style_data(btn_github, "background_color", "#1a3a2a")
        _safe_set_style_data(btn_github, "text_color", tc("white"))
        _safe_set_style_data(btn_github, "hover_color", "#2a5a3a")
        _safe_set_style_data(btn_github, "click_color", "#1a4a2a")
        btn_github.setMinimumHeight(36)
        btn_github.setMinimumWidth(130)
        btn_github.clicked.connect(lambda: _on_github_check(parent_dialog))
        btn_row.addWidget(btn_github)
    except Exception:
        _logger.warning("SiPushButtonRefactor(检查更新) 创建失败", exc_info=True)

    btn_row.addStretch()
    card.addWidget(btn_row_w)

    # ── 自动检查复选框 ──────────────────────────────────────────
    try:
        from components.star_checkbox import StarCheckBox
        cb_auto = StarCheckBox(
            "启动时自动检查更新",
            checked=True,
            checkbox_size=18,
        )
        cb_auto.toggled.connect(lambda checked: _on_auto_check_toggled(checked))
        card.addWidget(cb_auto)
    except Exception:
        _logger.warning("StarCheckBox(自动检查) 创建失败", exc_info=True)

    page._ignored_container_widget = None
    _refresh_ignored_list(page, parent_dialog, card)
    layout.addWidget(card)


def build_page(parent_dialog, current_config: dict) -> QWidget:
    """构建关于页面"""
    page = QWidget()
    page.setObjectName("settingsPage")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)

    # ═══ 标题 ═══
    try:
        title = SiLabel(page)
        title.setText("关于")
        title.setTextColor(title.getColor(SiColor.TEXT_A))
        layout.addWidget(title)
    except Exception:
        title = QLabel("关于")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

    try:
        desc = SiLabel(page)
        desc.setText("查看应用信息与版本管理")
        desc.setTextColor(desc.getColor(SiColor.TEXT_C))
        desc.setWordWrap(True)
        layout.addWidget(desc)
    except Exception:
        desc = QLabel("查看应用信息与版本管理")
        desc.setWordWrap(True)
        layout.addWidget(desc)

    _build_app_info_card(page, layout, current_config)
    _build_about_card(page, layout)
    _build_update_card(page, layout, parent_dialog)
    _build_backup_management_card(page, parent_dialog, layout)
    _build_developer_mode_card(page, parent_dialog, layout, current_config)

    layout.addStretch()

    try:
        if SiGlobal.siui is not None and hasattr(SiGlobal.siui, "reloadStyleSheetRecursively"):
            SiGlobal.siui.reloadStyleSheetRecursively(page)
    except Exception:
        _logger.warning("SiUI 样式刷新失败（非致命）", exc_info=True)

    return page


def collect_config(page_widget: QWidget) -> dict:
    """收集关于页配置：读取完整 config.json 并合并开发者模式字段。"""
    import json
    from workers.app_config.config_paths import get_config_path

    save_path = get_config_path("config/config.json")
    try:
        with open(save_path, "r", encoding="utf-8") as f:
            full = json.load(f)
    except Exception:
        full = get_default_config()

    # 覆盖开发者模式字段
    btn = getattr(page_widget, "_dev_mode_btn", None)
    if btn is not None:
        full["developer_mode"] = btn.isChecked()
    full["disabled_features"] = getattr(
        page_widget, "_dev_mode_features", ["debug_console"]
    )
    return full


# ── 备份按钮 QSS 工厂 ────────────────────────────────────────────────

def _make_backup_action_qss(color_hex: str) -> str:
    """生成删除/恢复按钮的 QSS 字符串（hover 时背景色＝边框色）。"""
    return (
        "QPushButton {"
        "  background: transparent;"
        f"  border: 1px solid {color_hex};"
        "  border-radius: 4px;"
        f"  color: {color_hex};"
        "  font-size: 12px;"
        "}"
        "QPushButton:hover {"
        f"  background: {color_hex};"
        f"  color: {tc('base')};"
        "}"
    )


# ── 更新器辅助函数 ─────────────────────────────────────────────────────

def _get_updater_manager(parent_dialog):
    """从 parent_dialog 获取 UpdateManager 实例。"""
    mw = None
    if hasattr(parent_dialog, 'parent') and parent_dialog.parent():
        mw = parent_dialog.parent()
    elif hasattr(parent_dialog, '_mw'):
        mw = getattr(parent_dialog, '_mw', None)

    if mw is not None:
        if hasattr(mw, '_updater_mgr'):
            return mw._updater_mgr
        # 如果还没创建，尝试从 workers.updater 创建
        try:
            from workers.updater import UpdateManager
            mw._updater_mgr = UpdateManager(mw)
            return mw._updater_mgr
        except Exception:
            pass
    return None


def _on_select_update(parent_dialog):
    """点击"选择更新包"按钮回调。"""
    mgr = _get_updater_manager(parent_dialog)
    if mgr:
        mgr.show_manual_install()


def _on_github_check(parent_dialog):
    """点击"检查更新"按钮回调 — 启动 GitHub 更新检查。"""
    mgr = _get_updater_manager(parent_dialog)
    if mgr:
        mgr.check_github()


def _on_auto_check_toggled(checked: bool):
    """自动检查更新复选框切换回调。"""
    from workers.app_config.config_paths import get_config_path
    import json
    try:
        cfg_path = get_config_path("config/config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["auto_check_github_update"] = checked
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        _logger.warning("保存自动检查更新设置失败", exc_info=True)


def _refresh_ignored_list(page: QWidget, parent_dialog, card):
    """刷新已忽略的补丁列表（card 为 SiPanelCard）。"""
    old = getattr(page, "_ignored_container_widget", None)
    if old is not None:
        cl = card.layout()
        if cl is not None and hasattr(cl, "removeWidget"):
            cl.removeWidget(old)
        old.deleteLater()
        page._ignored_container_widget = None

    mgr = _get_updater_manager(parent_dialog)
    if mgr is None:
        return

    container = mgr.show_ignored_in_settings(page)
    if container:
        sep = _make_sep()
        card.addWidget(sep)
        card.addWidget(container)
        page._ignored_container_widget = container


def _build_developer_mode_card(
    page: QWidget, parent_dialog, layout: QVBoxLayout, current_config: dict
):
    """构建"开发者模式"卡片 — QPushButton checkable 版。"""
    card = _safe_create_card(page)
    if card is None:
        return

    _add_silabel(card, "开发者模式", SiColor.TEXT_B)
    _add_silabel(card, "启用开发者模式后可使用调试台等开发工具", SiColor.TEXT_C, word_wrap=True)
    card.addWidget(_make_sep())

    # 开关按钮行
    toggle_row = _make_transparent_row(card)
    tr = QHBoxLayout(toggle_row)
    tr.setContentsMargins(0, 0, 0, 0)
    tr.setSpacing(12)

    tr.addStretch()

    dev_enabled = current_config.get("developer_mode", False)
    btn_toggle = QPushButton(f"● 开发者模式")
    btn_toggle.setCheckable(True)
    btn_toggle.setChecked(dev_enabled)
    btn_toggle.setFixedHeight(34)
    btn_toggle.setMinimumWidth(140)
    btn_toggle.setCursor(Qt.PointingHandCursor)
    btn_toggle.setStyleSheet(
        f"QPushButton {{"
        f"  background: transparent;"
        f"  border: 1px solid {tc('border')};"
        f"  border-radius: 6px;"
        f"  color: {tc('text')};"
        f"  font-size: 13px;"
        f"  padding: 4px 12px;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background: {tc('overlay')};"
        f"}}"
        f"QPushButton:checked {{"
        f"  background: {tc('accent_blue_deep')};"
        f"  border-color: {tc('accent_blue')};"
        f"  color: {tc('white')};"
        f"}}"
    )
    btn_toggle.toggled.connect(
        lambda checked: _on_dev_mode_toggled(parent_dialog, btn_toggle, checked)
    )
    tr.addWidget(btn_toggle)

    card.addWidget(toggle_row)

    # 禁用功能名单
    disabled = current_config.get("disabled_features", ["debug_console"])
    card.addWidget(_make_sep())
    _add_silabel(card, "禁用功能名单（关闭开发者模式后隐藏）", SiColor.TEXT_B)

    feature_names = {"debug_console": "调试台"}
    for feat_id in disabled:
        feat_name = feature_names.get(feat_id, feat_id)
        try:
            fl = SiLabel(card)
            fl.setText(f"● {feat_name}")
            fl.setTextColor(fl.getColor(SiColor.TEXT_D))
            fl.setStyleSheet("background: transparent; font-size: 12px; padding-left: 8px;")
            card.addWidget(fl)
        except Exception:
            flq = QLabel(f"● {feat_name}")
            flq.setStyleSheet(f"color: {tc('muted')}; font-size: 12px; padding-left: 8px;")
            card.addWidget(flq)

    card.addWidget(_make_sep())
    _add_silabel(card, "提示：更改开发者模式后需要重启才能生效", SiColor.TEXT_C, word_wrap=True)

    layout.addWidget(card)

    page._dev_mode_btn = btn_toggle
    page._dev_mode_features = disabled


def _on_dev_mode_toggled(parent_dialog, btn, checked: bool):
    """开发者模式开关切换回调（QPushButton checkable 版）。"""
    if checked:
        result = CustomDialog.warning(
            parent_dialog,
            "开启开发者模式",
            "开发者功能仅供漏洞排查、插件开发等场景使用。\n"
            "使用开发者功能所造成软件问题作者概不负责。\n\n"
            "确定要开启开发者模式吗？",
            buttons=[("取消", "cancel"), ("确定开启", "ok")],
        )
        if result != "ok":
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
            return

    # 更新按钮文字颜色反馈
    mode_label = "开启" if checked else "关闭"
    CustomDialog.information(
        parent_dialog,
        "需要重启",
        f"已{mode_label}开发者模式，需要重启软件才能生效。\n\n"
        f"请点击设置页面的「保存」按钮保存配置，\n"
        f"然后重启 StarDebate。",
    )


# ════════════════════════════════════════════════════════════════════════
#  配置备份管理（删除 / 恢复 / 一键清理）
# ════════════════════════════════════════════════════════════════════════

def _get_main_window(parent_dialog):
    """从设置对话框获取主窗口引用。"""
    if hasattr(parent_dialog, 'parent') and parent_dialog.parent():
        return parent_dialog.parent()
    if hasattr(parent_dialog, '_mw'):
        return getattr(parent_dialog, '_mw', None)
    return None


def _get_backup_file_list(backup_path: str) -> list[str]:
    """获取备份目录中的文件列表（用于恢复预览）。"""
    files = []
    if not os.path.isdir(backup_path):
        return files
    for root, dirs, filenames in os.walk(backup_path):
        rel = os.path.relpath(root, backup_path)
        for f in sorted(filenames):
            if rel == ".":
                files.append(f"  ├ {f}")
            else:
                files.append(f"  ├ {rel}/{f}")
    return files if files else ["  (空)"]


def _build_backup_management_card(page: QWidget, parent_dialog, layout: QVBoxLayout):
    """构建"配置备份管理"卡片 — SiLongPressButtonRefactor 版。"""
    card = _safe_create_card(page)
    if card is None:
        return

    _add_silabel(card, "配置备份管理", SiColor.TEXT_B)
    _add_silabel(card, "管理更新时自动备份的旧版本配置文件", SiColor.TEXT_C, word_wrap=True)

    # 备份条目容器
    entries_container = QFrame(card)
    entries_container.setObjectName("backupEntriesContainer")
    entries_container.setStyleSheet("background: transparent;")
    entries_lay = QVBoxLayout(entries_container)
    entries_lay.setContentsMargins(0, 0, 0, 0)
    entries_lay.setSpacing(6)
    card.addWidget(entries_container)

    # 一键清理按钮行
    cleanup_row = _make_transparent_row(card)
    cr = QHBoxLayout(cleanup_row)
    cr.setContentsMargins(0, 0, 0, 0)
    cr.addStretch()
    try:
        btn_cleanup = SiLongPressButtonRefactor(card)
        btn_cleanup.setText("一键清理全部")
        btn_cleanup.setToolTip("长按以清理全部配置备份")
        _safe_set_style_data(btn_cleanup, "button_color", tc("accent_red"))
        _safe_set_style_data(btn_cleanup, "text_color", tc("text"))
        btn_cleanup.setMinimumWidth(160)
        btn_cleanup.setMinimumHeight(36)
        btn_cleanup.longPressed.connect(lambda: _on_cleanup_all_backups(parent_dialog, page))
        cr.addWidget(btn_cleanup)
    except Exception:
        _logger.warning("SiLongPressButtonRefactor(一键清理) 创建失败", exc_info=True)
        btn_cleanup = None
    card.addWidget(cleanup_row)

    layout.addWidget(card)

    page._backup_card = card
    page._backup_entries_layout = entries_lay
    page._backup_cleanup_btn = btn_cleanup

    _refresh_backup_list(page, parent_dialog)


def _refresh_backup_list(page: QWidget, parent_dialog):
    """刷新备份条目列表。"""
    entries_lay = getattr(page, "_backup_entries_layout", None)
    if entries_lay is None:
        return

    # 清除旧条目
    while entries_lay.count():
        item = entries_lay.takeAt(0)
        w = item.widget()
        if w:
            w.deleteLater()

    backups = list_backups()
    if not backups:
        # 空状态提示
        empty_lbl = QLabel("暂无配置备份，更新后将自动备份旧配置")
        empty_lbl.setObjectName("settingsValueLabel")
        empty_lbl.setStyleSheet(f"color: {tc('muted')}; padding: 8px 0;")
        entries_lay.addWidget(empty_lbl)
        # 隐藏一键清理按钮
        btn = getattr(page, "_backup_cleanup_btn", None)
        if btn:
            btn.setVisible(False)
        return

    # 显示一键清理按钮
    btn = getattr(page, "_backup_cleanup_btn", None)
    if btn:
        btn.setVisible(True)

    for bk in backups:
        row_widget = QWidget()
        row_widget.setObjectName("backupEntryRow")
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(8)

        # 版本号
        label_text = bk["name"].replace("_config", "")
        lbl_name = QLabel(label_text)
        lbl_name.setObjectName("settingsValueLabel")
        lbl_name.setFixedWidth(110)

        # 大小
        lbl_size = QLabel(f"{bk['size_mb']} MB")
        lbl_size.setObjectName("settingsValueLabel")
        lbl_size.setFixedWidth(60)
        lbl_size.setStyleSheet(f"color: {tc('muted')}; font-size: 12px;")

        # 创建时间
        lbl_time = QLabel(bk["created_time"])
        lbl_time.setObjectName("settingsValueLabel")
        lbl_time.setStyleSheet(f"color: {tc('muted')}; font-size: 12px;")

        subdir = bk["name"]

        # 删除按钮
        btn_del = QPushButton("删除")
        btn_del.setFixedSize(50, 26)
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.setStyleSheet(_make_backup_action_qss(tc("accent_red")))
        btn_del.clicked.connect(
            lambda checked, s=subdir: _on_delete_backup(parent_dialog, s, page)
        )

        # 恢复按钮
        btn_restore = QPushButton("恢复")
        btn_restore.setFixedSize(50, 26)
        btn_restore.setCursor(Qt.PointingHandCursor)
        btn_restore.setStyleSheet(_make_backup_action_qss(tc("accent_green")))
        btn_restore.clicked.connect(
            lambda checked, s=subdir: _on_restore_backup(parent_dialog, s)
        )

        row.addWidget(lbl_name)
        row.addWidget(lbl_size)
        row.addWidget(lbl_time, stretch=1)
        row.addWidget(btn_del)
        row.addWidget(btn_restore)

        entries_lay.addWidget(row_widget)


def _on_delete_backup(parent_dialog, backup_subdir: str, page: QWidget):
    """删除单个配置备份（带确认）。"""
    confirmed = CustomDialog.confirm(
        parent_dialog,
        "删除配置备份",
        f"确定删除备份「{backup_subdir}」？\n\n此操作不可撤销。",
    )
    if not confirmed:
        return

    ok = delete_backup(backup_subdir)
    if ok:
        _refresh_backup_list(page, parent_dialog)
        CustomDialog.information(
            parent_dialog, "删除完成", f"已删除备份「{backup_subdir}」",
        )
    else:
        CustomDialog.error(
            parent_dialog, "删除失败", f"无法删除备份「{backup_subdir}」，请检查文件权限。",
        )


def _on_restore_backup(parent_dialog, backup_subdir: str):
    """恢复配置备份（带文件预览 + 确认 + 重启提示）。"""
    from workers.updater.update_utils import get_backups_dir
    backup_path = os.path.join(get_backups_dir(), backup_subdir)
    if not os.path.isdir(backup_path):
        CustomDialog.error(parent_dialog, "恢复失败", "备份目录不存在。")
        return

    # 列出备份中的文件
    file_list = _get_backup_file_list(backup_path)
    file_text = "\n".join(file_list)
    file_count = sum(1 for f in file_list if "├" in f and "(空)" not in f)

    # 文件预览弹窗
    preview_msg = (
        f"即将恢复备份「{backup_subdir}」，\n"
        f"将覆盖当前 config/ 目录中的以下 {file_count} 个文件：\n\n"
        f"{file_text}\n\n"
        f"⚠ 当前配置将被覆盖，此操作不可撤销。"
    )
    confirmed = CustomDialog.confirm(
        parent_dialog,
        "恢复配置备份",
        preview_msg,
        ok_text="确定并重启",
    )
    if not confirmed:
        return

    # 执行恢复
    ok = restore_config_from_backup(backup_subdir)
    if not ok:
        CustomDialog.error(parent_dialog, "恢复失败", "配置恢复失败，请检查日志。")
        return

    # 恢复成功，提示重启
    CustomDialog.information(
        parent_dialog,
        "恢复完成",
        "配置已成功恢复，需要重启才能生效。\n\n点击「确定」后将自动关闭应用。",
    )

    # 自动关闭主窗口
    mw = _get_main_window(parent_dialog)
    if mw:
        mw.close()


def _on_cleanup_all_backups(parent_dialog, page: QWidget):
    """一键清理全部配置备份（带强调二次确认）。"""
    backups = list_backups()
    if not backups:
        return

    total_count = len(backups)
    total_size = sum(b["size_mb"] for b in backups)

    confirmed = CustomDialog.confirm(
        parent_dialog,
        "清理全部备份",
        f"确定删除全部 {total_count} 个配置备份？\n"
        f"这将释放约 {total_size:.1f} MB 空间。\n\n"
        f"⚠ 建议保留至少一个备份，以防需要回退配置。\n"
        f"此操作不可撤销。",
    )
    if not confirmed:
        return

    success_count = 0
    for bk in backups:
        if delete_backup(bk["name"]):
            success_count += 1

    _refresh_backup_list(page, parent_dialog)

    if success_count == total_count:
        CustomDialog.information(
            parent_dialog, "清理完成",
            f"已成功清理全部 {total_count} 个配置备份，释放 {total_size:.1f} MB 空间。",
        )
    else:
        CustomDialog.warning(
            parent_dialog, "部分清理失败",
            f"成功清理 {success_count}/{total_count} 个备份，"
            f"部分文件可能正在使用中。",
        )
