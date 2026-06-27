"""
API 配置设置页 — 使用 PyQt-SiliconUI 重构版组件
v3.0: 新增 Web AI 网页版支持（AI 来源 + 登录管理 + Chromium 检测）
"""

import logging

from PyQt5.QtCore import Qt, QObject, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QButtonGroup,
)

# PyQt-SiliconUI 重构版组件
from siui.components.widgets import SiLabel
from siui.components.editbox import SiCapsuleLineEdit
from siui.components.button import (
    SiPushButtonRefactor, SiProgressPushButton,
    SiRadioButtonR, SiToggleButtonRefactor,
)
from siui.core import SiColor, SiGlobal

from components.theme_colors import tc
from components.icon_loader import load_common_icon, load_common_svg_bytes
from siui.components.spinbox.spinbox import SiIntSpinBox

# 共享设置页工具函数
from workers.settings.pages._page_utils import (
    safe_set_style_data,
    safe_create_card,
    add_silabel,
    make_transparent_row,
)

_logger = logging.getLogger("StarDebate.settings.api_config")

# 主窗口引用缓存（用于刷新标题栏登录按钮）
_main_window_ref = None


class _LoginSignal(QObject):
    """跨线程登录完成信号（用信号槽代替 QTimer.singleShot，更可靠）"""
    done = pyqtSignal(object, object, bool)  # page, btn, success


_login_signal = _LoginSignal()
_login_signal.done.connect(
    lambda p, b, s: _on_login_done(p, b, s)
)


def _get_main_window():
    """获取主窗口引用（优先用缓存，兜底用 topLevelWidgets 查找）"""
    global _main_window_ref
    if _main_window_ref is not None:
        return _main_window_ref
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            _logger.debug("get_main_window: QApplication.instance() 为空")
            return None
        for w in app.topLevelWidgets():
            meta = type(w).__name__
            if hasattr(w, '_refresh_web_login_btn'):
                _logger.debug("get_main_window: 找到主窗口 %s", meta)
                _main_window_ref = w
                return w
            _logger.debug("get_main_window: 略过顶层窗口 %s", meta)
        _logger.debug("get_main_window: 未找到主窗口")
    except Exception as e:
        _logger.debug("get_main_window 异常: %s", e)
    return None


# ═══════════════════════════════════════
#  页面元信息
# ═══════════════════════════════════════

PAGE_INFO = {
    "id": "api_config",
    "name": "API 配置",
    "icon": "api",
    "order": 10,
    "author": "StarDebate",
    "version": "3.0.0",
}

PAGE_CONFIG = {
    "save_path": "config/api_config.json",
    "auto_save": True,
}


def get_default_config() -> dict:
    return {
        "api_url": "https://api.deepseek.com/v1/chat/completions",
        "api_key": "",
        "model": "deepseek-v4-flash",
        "max_tokens": 4096,
        "temperature": 0.7,
        # v3.0 新增（默认 api 模式，不自动安装 Chromium）
        "provider_type": "api",    # api | auto | web
        "provider_id": "deepseek",
    }


def _val(text: str, fallback: str = "未配置") -> str:
    return text if text else fallback


# ── Provider Type 选项 ──
PROVIDER_OPTIONS = [
    ("auto", "自动检测", "无 API Key 时自动使用网页版"),
    ("api", "API 模式", "使用 API Key 连接 AI 服务"),
    ("web", "网页版", "通过浏览器访问 AI 网站（无需 API Key）"),
]


def _get_ptype(page) -> str:
    """获取当前选中的 provider_type"""
    grp = getattr(page, "_provider_radio_group", None)
    if grp:
        btn = grp.checkedButton()
        if btn and hasattr(btn, "_ptype"):
            return btn._ptype
    return "auto"


def _show_api_card(page, show: bool):
    """显示/隐藏 API 设置卡片"""
    card = getattr(page, "_api_card_container", None)
    if card:
        card.setVisible(show)


def _show_web_card(page, show: bool):
    """显示/隐藏网页版设置卡片"""
    card = getattr(page, "_web_card_container", None)
    if card:
        card.setVisible(show)


def _on_provider_changed(page):
    """AI 来源变化时更新卡片可见性"""
    ptype = _get_ptype(page)
    if ptype == "auto":
        _show_api_card(page, True)
        _show_web_card(page, True)
    elif ptype == "api":
        _show_api_card(page, True)
        _show_web_card(page, False)
    elif ptype == "web":
        _show_api_card(page, False)
        _show_web_card(page, True)


def _build_provider_radios(parent, page, current_config):
    """构建 AI 来源单选组（SiRadioButtonR ×3）"""
    container = make_transparent_row(parent)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 4, 0, 4)
    layout.setSpacing(4)

    group = QButtonGroup(parent)
    page._provider_radio_group = group

    ptype = current_config.get("provider_type", "auto")

    for idx, (key, label, desc) in enumerate(PROVIDER_OPTIONS):
        rb = SiRadioButtonR(parent)
        rb.setText(label)
        rb.adjustSize()
        rb._ptype = key

        # [1] 先设置全部主题色（一定要在 setChecked 之前）
        safe_set_style_data(rb, "text_color", tc("text"))
        safe_set_style_data(rb, "indicator_idle_color", tc("overlay"))
        safe_set_style_data(rb, "indicator_idle_strike_color", tc("surface"))
        safe_set_style_data(rb, "indicator_hover_strike_color", tc("hover"))
        safe_set_style_data(rb, "indicator_flash_color", tc("border"))
        safe_set_style_data(rb, "indicator_flash_strike_color", tc("white"))
        safe_set_style_data(rb, "indicator_selected_color", tc("selected_bg"))
        safe_set_style_data(rb, "indicator_selected_strike_color", tc("accent_blue"))

        # [2] 再触发选中（此时 style_data 已正确，_onToggled 能读到主题色）
        if key == ptype:
            rb.setChecked(True)

        # [3] 强制刷新：文字 QSS + 圆点颜色
        #    SiRadioButtonR._initStyle() / _indi_color 均只在构造时初始化一次，
        #    不会自动跟踪 style_data 的变化，需要手动刷新
        rb._initStyle()  # 刷新文字颜色
        rb._indi_color = QColor(tc("selected_bg" if rb.isChecked() else "overlay"))
        rb._indi_strike_color = QColor(tc("accent_blue" if rb.isChecked() else "surface"))
        rb.update()

        group.addButton(rb, idx)
        layout.addWidget(rb)

        # 描述标签
        if desc:
            desc_lbl = SiLabel(parent)
            desc_lbl.setText(desc)
            desc_lbl.setStyleSheet(f"color: {tc('muted')}; font-size: 11px;")
            desc_lbl.setMinimumHeight(16)
            layout.addWidget(desc_lbl)

    group.buttonClicked.connect(lambda: _on_provider_changed(page))
    return container


def _build_api_card(parent, page, current_config):
    """构建 API 设置卡片"""
    card = safe_create_card(parent)

    if card is None:
        from PyQt5.QtWidgets import QFrame, QLabel, QFormLayout
        card = QFrame(parent)
        card.setObjectName("settingsCard")
        card.setStyleSheet(
            f"background-color: {tc('surface')}; border: 1px solid {tc('border')}; "
            f"border-radius: 10px; padding: 16px;"
        )
        fl = QFormLayout(card)
        fl.setSpacing(8)
        url_lbl = QLabel("API 端点")
        url_lbl.setStyleSheet(f"font-weight: bold; color: {tc('text')};")
        fl.addRow(url_lbl, QLabel(_val(current_config.get("api_url", ""))))
        key_lbl = QLabel("API Key")
        key_lbl.setStyleSheet(f"font-weight: bold; color: {tc('text')};")
        api_key_input = QLineEdit(current_config.get("api_key", ""))
        api_key_input.setEchoMode(QLineEdit.Password)
        api_key_input.setObjectName("settingsInput")
        fl.addRow(key_lbl, api_key_input)
        model_lbl = QLabel("模型")
        model_lbl.setStyleSheet(f"font-weight: bold; color: {tc('text')};")
        fl.addRow(model_lbl, QLabel(_val(current_config.get("model", "deepseek-v4-flash"))))
        page._edit_key = api_key_input
        return card

    # ── API 端点（只读） ──
    add_silabel(card, "API 端点", SiColor.TEXT_B)
    add_silabel(card, _val(current_config.get("api_url", "")), SiColor.TEXT_D, word_wrap=True)

    # ── API Key（可编辑） ──
    add_silabel(card, "API Key", SiColor.TEXT_B)

    key_row_widget = make_transparent_row(card)
    key_row = QHBoxLayout(key_row_widget)
    key_row.setContentsMargins(0, 0, 0, 0)
    key_row.setSpacing(8)

    try:
        edit_key = SiCapsuleLineEdit(card)
        edit_key.setTitle("")
        safe_set_style_data(edit_key, "title_background_color", tc("surface"))
        safe_set_style_data(edit_key, "text_background_color", tc("base"))
        safe_set_style_data(edit_key, "text_color", tc("text"))
        safe_set_style_data(edit_key, "title_color_idle", tc("muted"))
        safe_set_style_data(edit_key, "title_color_focused", tc("text"))
        safe_set_style_data(edit_key, "text_indicator_color_editing", tc("accent_blue"))
        try:
            edit_key._initStyleSheet()
        except Exception:
            pass
        edit_key.setPlaceholderText("sk-...")
        edit_key.setEchoMode(QLineEdit.EchoMode.Password)
        edit_key.setText(current_config.get("api_key", ""))
        edit_key.setMinimumHeight(36)
        key_row.addWidget(edit_key, stretch=1)
    except Exception:
        _logger.warning("SiCapsuleLineEdit 创建失败，回退 QLineEdit", exc_info=True)
        edit_key = QLineEdit(card)
        edit_key.setPlaceholderText("sk-...")
        edit_key.setEchoMode(QLineEdit.EchoMode.Password)
        edit_key.setText(current_config.get("api_key", ""))
        edit_key.setObjectName("settingsInput")
        key_row.addWidget(edit_key, stretch=1)

    try:
        btn_toggle_key = SiPushButtonRefactor.withText("显示", card)
        btn_toggle_key.setMinimumHeight(36)
        btn_toggle_key.setMinimumWidth(60)
        safe_set_style_data(btn_toggle_key, "button_color", tc("overlay"))
        safe_set_style_data(btn_toggle_key, "background_color", tc("border"))
        safe_set_style_data(btn_toggle_key, "text_color", tc("text"))

        key_visible = False
        def toggle_key():
            nonlocal key_visible
            key_visible = not key_visible
            le = edit_key
            cursor_pos = le.cursorPosition()
            current_text = le.text()
            le.setEchoMode(
                QLineEdit.EchoMode.Normal if key_visible
                else QLineEdit.EchoMode.Password
            )
            le.setText(current_text)
            le.setCursorPosition(cursor_pos)
            btn_toggle_key.setText("隐藏" if key_visible else "显示")

        btn_toggle_key.clicked.connect(toggle_key)
    except Exception:
        _logger.warning("SiPushButtonRefactor(切换) 创建失败", exc_info=True)
        btn_toggle_key = None

    if btn_toggle_key is not None:
        key_row.addWidget(btn_toggle_key)
    card.addWidget(key_row_widget)

    # ── 模型（只读） ──
    try:
        row_model = make_transparent_row(card)
        row_model_layout = QHBoxLayout(row_model)
        row_model_layout.setContentsMargins(0, 0, 0, 0)
        add_silabel(row_model, "模型", SiColor.TEXT_B)
        add_silabel(row_model, _val(current_config.get("model", "deepseek-v4-flash")),
                    SiColor.TEXT_D, min_height=18)
        row_model_layout.addStretch()
        card.addWidget(row_model)
    except Exception:
        _logger.warning("模型行创建失败", exc_info=True)

    # ── 测试连接 ──
    try:
        test_row_widget = make_transparent_row(card)
        test_row = QHBoxLayout(test_row_widget)
        test_row.setContentsMargins(0, 0, 0, 0)
        test_row.addStretch()

        btn_test = SiPushButtonRefactor.withText("测试连接", card)
        btn_test.setMinimumHeight(36)
        safe_set_style_data(btn_test, "button_color", tc("accent_blue"))
        safe_set_style_data(btn_test, "background_color", tc("accent_blue_deep"))
        safe_set_style_data(btn_test, "text_color", tc("white"))
        safe_set_style_data(btn_test, "hover_color", tc("accent_blue_hover"))
        safe_set_style_data(btn_test, "click_color", tc("accent_blue_pressed"))

        if hasattr(edit_key, "text"):
            def on_test():
                from components.popup_dialog import CustomDialog
                key = edit_key.text().strip()
                if not key:
                    CustomDialog.warning(parent, "提示", "请先填写 API Key")
                    return
                from workers.settings.api_test_worker import APITestWorker
                test_config = {
                    "api_url": current_config.get("api_url", ""),
                    "api_key": key,
                    "model": current_config.get("model", "deepseek-v4-flash"),
                }
                btn_test.setEnabled(False)
                btn_test.setText("测试中...")
                worker = APITestWorker(test_config)

                def on_result(success, msg):
                    btn_test.setEnabled(True)
                    btn_test.setText("测试连接")
                    if success:
                        CustomDialog.information(parent, "连接成功", msg)
                    else:
                        CustomDialog.warning(parent, "连接失败", msg)

                worker.test_finished.connect(on_result)
                worker.start()
                page._test_worker = worker

            btn_test.clicked.connect(on_test)
            test_row.addWidget(btn_test)
            card.addWidget(test_row_widget)
    except Exception:
        _logger.warning("测试按钮创建失败", exc_info=True)

    page._edit_key = edit_key
    return card


def _build_web_card(parent, page):
    """构建网页版设置卡片"""
    card = safe_create_card(parent)
    if card is None:
        card = QWidget(parent)
        card.setStyleSheet(
            f"background-color: {tc('surface')}; border: 1px solid {tc('border')}; "
            f"border-radius: 10px; padding: 16px;"
        )
        return card

    # ── 登录状态 ──
    page._web_status_label = SiLabel(card)
    page._web_status_label.setMinimumHeight(20)
    page._web_status_label.setWordWrap(True)
    page._web_status_label.setStyleSheet(f"color: {tc('muted')}; font-size: 12px;")
    card.addWidget(page._web_status_label)

    # ── 登录按钮 (SiToggleButtonRefactor) ──
    try:
        btn_login = SiToggleButtonRefactor(card)
        btn_login.setText("登录 DeepSeek 网页版")
        login_svg = load_common_svg_bytes("key.svg")
        if login_svg:
            btn_login.setSvgIcon(login_svg)
        btn_login.setMinimumHeight(36)
        safe_set_style_data(btn_login, "button_color", tc("accent_blue"))
        safe_set_style_data(btn_login, "text_color", tc("white"))
        safe_set_style_data(btn_login, "toggled_button_color", tc("accent_green"))
        safe_set_style_data(btn_login, "toggled_text_color", tc("white"))
        # 直接覆盖内部变量（动画属性），跳过动画延迟，确保初始渲染正确
        btn_login._button_rect_color = QColor(tc("accent_blue"))
        btn_login._text_color = QColor(tc("white"))
        # 同步动画目标值
        btn_login.reloadStyleData()
        btn_login.adjustSize()
        page._btn_web_login = btn_login
        card.addWidget(btn_login)
    except Exception:
        _logger.warning("SiToggleButtonRefactor(登录) 创建失败", exc_info=True)
        page._btn_web_login = None

    # ── 清除登录状态 ──
    try:
        btn_logout = SiPushButtonRefactor.withText("清除登录状态", card)
        trash_svg = load_common_svg_bytes("trash.svg")
        if trash_svg:
            btn_logout.setSvgIcon(trash_svg)
        btn_logout.setMinimumHeight(36)
        safe_set_style_data(btn_logout, "button_color", tc("overlay"))
        safe_set_style_data(btn_logout, "background_color", tc("border"))
        safe_set_style_data(btn_logout, "text_color", tc("text"))
        page._btn_web_logout = btn_logout
        card.addWidget(btn_logout)
    except Exception:
        _logger.warning("SiPushButtonRefactor(清除登录) 创建失败", exc_info=True)
        page._btn_web_logout = None

    return card


def _build_chromium_card(parent, page):
    """构建 Chromium 引擎状态卡片"""
    card = safe_create_card(parent)
    if card is None:
        card = QWidget(parent)
        card.setStyleSheet(
            f"background-color: {tc('surface')}; border: 1px solid {tc('border')}; "
            f"border-radius: 10px; padding: 16px;"
        )
        return card

    # ── Chromium 状态标签 ──
    page._chromium_status_label = SiLabel(card)
    page._chromium_status_label.setMinimumHeight(20)
    page._chromium_status_label.setWordWrap(True)
    page._chromium_status_label.setStyleSheet(f"color: {tc('muted')}; font-size: 12px;")
    card.addWidget(page._chromium_status_label)

    # ── 安装按钮 (SiProgressPushButton) ──
    try:
        btn_install = SiProgressPushButton(card)
        btn_install.setText("安装 Chromium")
        dl_svg = load_common_svg_bytes("download.svg")
        if dl_svg:
            btn_install.setSvgIcon(dl_svg)
        btn_install.setMinimumHeight(36)
        safe_set_style_data(btn_install, "button_color", tc("accent_blue"))
        safe_set_style_data(btn_install, "text_color", tc("white"))
        safe_set_style_data(btn_install, "progress_color", tc("accent_green"))
        safe_set_style_data(btn_install, "complete_color", tc("accent_green"))
        btn_install._progress_rect_color = QColor(tc("accent_green"))
        btn_install.reloadStyleData()
        btn_install.adjustSize()
        page._btn_chromium_install = btn_install
        card.addWidget(btn_install)
    except Exception:
        _logger.warning("SiProgressPushButton(安装Chromium) 创建失败", exc_info=True)
        page._btn_chromium_install = None

    return card


def _build_timeout_card(parent, page, current_config):
    """构建超时与重试设置卡片"""
    card = safe_create_card(parent)
    if card is None:
        card = QWidget(parent)
        card.setStyleSheet(
            f"background-color: {tc('surface')}; border: 1px solid {tc('border')}; "
            f"border-radius: 10px; padding: 16px;"
        )
        return card

    # 单次超时
    try:
        row_t = make_transparent_row(card)
        row_tl = QHBoxLayout(row_t)
        row_tl.setContentsMargins(0, 0, 0, 0)
        add_silabel(row_t, "单次超时", SiColor.TEXT_B, min_height=18)

        edit_timeout = SiIntSpinBox(card)
        edit_timeout.setMinimum(10)
        edit_timeout.setMaximum(300)
        edit_timeout.setSingleStep(5)
        edit_timeout.setValue(int(current_config.get("webai_timeout", 60)))
        edit_timeout.setMinimumWidth(200)
        edit_timeout.setMaximumWidth(300)
        edit_timeout.setFixedHeight(40)
        # 设置内层输入框颜色以跟随主题
        edit_timeout.lineEdit().setStyleSheet(
            f"color: {tc('text')}; background: transparent; border: none;"
        )
        row_tl.addWidget(edit_timeout)
        add_silabel(row_t, "秒", SiColor.TEXT_D, min_height=18)
        row_tl.addStretch()
        page._edit_timeout = edit_timeout
        card.addWidget(row_t)
    except Exception:
        _logger.warning("超时设置行创建失败", exc_info=True)

    # 最大重试
    try:
        row_r = make_transparent_row(card)
        row_rl = QHBoxLayout(row_r)
        row_rl.setContentsMargins(0, 0, 0, 0)
        add_silabel(row_r, "最大重试", SiColor.TEXT_B, min_height=18)

        edit_retry = SiIntSpinBox(card)
        edit_retry.setMinimum(0)
        edit_retry.setMaximum(10)
        edit_retry.setSingleStep(1)
        edit_retry.setValue(int(current_config.get("webai_max_retries", 2)))
        edit_retry.setMinimumWidth(200)
        edit_retry.setMaximumWidth(300)
        edit_retry.setFixedHeight(40)
        # 设置内层输入框颜色以跟随主题
        edit_retry.lineEdit().setStyleSheet(
            f"color: {tc('text')}; background: transparent; border: none;"
        )
        row_rl.addWidget(edit_retry)
        add_silabel(row_r, "次", SiColor.TEXT_D, min_height=18)
        row_rl.addStretch()
        page._edit_retry = edit_retry
        card.addWidget(row_r)
    except Exception:
        _logger.warning("重试设置行创建失败", exc_info=True)

    return card


# ── 刷新状态辅助 ──

def _format_logged_in_text(state_path: str) -> str:
    """格式化已登录状态文本（含 session 有效期）"""
    import os, time as _time
    if os.path.exists(state_path):
        mtime = os.path.getmtime(state_path)
        age_days = (_time.time() - mtime) / 86400
        remain_days = max(0, 30 - age_days)
        return f"已登录  |  Session 剩余约 {remain_days:.0f} 天"
    return "已登录"


def _lazy_refresh_status_once(page):
    """轻量刷新状态（页面切入时调用，不启动 Chrome / 子进程）"""
    # 登录状态（文件 mtime 检测，不启动 Chrome）
    from workers.web_ai.web_ai_manager import get_web_ai_manager
    wm = get_web_ai_manager()
    is_auth = wm.is_authenticated("deepseek")
    status_label = getattr(page, "_web_status_label", None)
    btn_login = getattr(page, "_btn_web_login", None)
    if status_label:
        if is_auth:
            state_path = wm.get_state_path("deepseek")
            status_label.setText(_format_logged_in_text(state_path))
            status_label.setStyleSheet(f"color: {tc('accent_green')}; font-size: 12px;")
            if btn_login:
                btn_login.setChecked(True)
                safe_set_style_data(btn_login, "toggled_button_color", tc("accent_green"))
                safe_set_style_data(btn_login, "toggled_text_color", tc("white"))
                btn_login._button_rect_color = QColor(tc("accent_green"))
                btn_login._text_color = QColor(tc("white"))
                btn_login.reloadStyleData()
        else:
            status_label.setText("未登录  |  请先登录 DeepSeek 网页版")
            status_label.setStyleSheet(f"color: {tc('warning')}; font-size: 12px;")
            if btn_login:
                btn_login.setChecked(False)
                safe_set_style_data(btn_login, "button_color", tc("accent_blue"))
                safe_set_style_data(btn_login, "text_color", tc("white"))
                btn_login._button_rect_color = QColor(tc("accent_blue"))
                btn_login._text_color = QColor(tc("white"))
                btn_login.reloadStyleData()

    # Chromium 状态（文件系统扫描，不调用子进程）
    from workers.web_ai.chromium_checker import get_chromium_checker
    checker = get_chromium_checker()
    installed = checker.is_chromium_installed_fast()
    status_label = getattr(page, "_chromium_status_label", None)
    btn_install = getattr(page, "_btn_chromium_install", None)
    if status_label:
        if installed:
            status_label.setText("Chromium 已安装")
            status_label.setStyleSheet(f"color: {tc('accent_green')}; font-size: 12px;")
            if btn_install:
                btn_install.setEnabled(False)
                btn_install.setProgress(1.0)
                btn_install.setText("Chromium 已安装")
        else:
            status_label.setText("Chromium 未安装  |  需下载 ~130MB（仅网页版需要）")
            status_label.setStyleSheet(f"color: {tc('warning')}; font-size: 12px;")
            if btn_install:
                btn_install.setEnabled(True)
                btn_install.setProgress(0.0)
                btn_install.setText("安装 Chromium")


def _refresh_web_status(page):
    """刷新网页版登录状态"""
    from workers.web_ai.web_ai_manager import get_web_ai_manager

    status_label = getattr(page, "_web_status_label", None)
    btn_login = getattr(page, "_btn_web_login", None)

    if not status_label:
        return

    try:
        wm = get_web_ai_manager()
        state_path = wm.get_state_path("deepseek")
        is_auth = wm.is_authenticated("deepseek")

        if is_auth:
            check_icon = load_common_icon("check.svg")
            status_label.setText(_format_logged_in_text(state_path))
            status_label.setStyleSheet(f"color: {tc('accent_green')}; font-size: 12px;")

            if btn_login:
                btn_login.setChecked(True)
                # 选中态应修改 toggled_* 属性（_onButtonToggled(True) 读取这些值）
                safe_set_style_data(btn_login, "toggled_button_color", tc("accent_green"))
                safe_set_style_data(btn_login, "toggled_text_color", tc("white"))
                btn_login._button_rect_color = QColor(tc("accent_green"))
                btn_login._text_color = QColor(tc("white"))
                btn_login.reloadStyleData()
        else:
            warn_icon = load_common_icon("warning.svg")
            status_label.setText("未登录  |  请先登录 DeepSeek 网页版")
            status_label.setStyleSheet(f"color: {tc('warning')}; font-size: 12px;")

            if btn_login:
                btn_login.setChecked(False)
                safe_set_style_data(btn_login, "button_color", tc("accent_blue"))
                safe_set_style_data(btn_login, "text_color", tc("white"))
                btn_login._button_rect_color = QColor(tc("accent_blue"))
                btn_login._text_color = QColor(tc("white"))
                btn_login.reloadStyleData()
    except Exception:
        status_label.setText("检测中...")
        status_label.setStyleSheet(f"color: {tc('muted')}; font-size: 12px;")


def _refresh_chromium_status(page):
    """刷新 Chromium 安装状态"""
    from workers.web_ai.chromium_checker import get_chromium_checker

    status_label = getattr(page, "_chromium_status_label", None)
    btn_install = getattr(page, "_btn_chromium_install", None)

    if not status_label:
        return

    try:
        checker = get_chromium_checker()
        installed = checker.is_chromium_installed()
        version = checker.get_chromium_version() if installed else ""

        if installed:
            check_icon = load_common_icon("check.svg")
            status_label.setText(f"Chromium 已安装  {version}")
            status_label.setStyleSheet(f"color: {tc('accent_green')}; font-size: 12px;")
            if btn_install:
                btn_install.setEnabled(False)
                btn_install.setProgress(1.0)
                btn_install.setText("Chromium 已安装")
        else:
            warn_icon = load_common_icon("warning.svg")
            status_label.setText("Chromium 未安装  |  需下载 ~130MB（仅网页版需要）")
            status_label.setStyleSheet(f"color: {tc('warning')}; font-size: 12px;")
            if btn_install:
                btn_install.setEnabled(True)
                btn_install.setProgress(0.0)
                btn_install.setText("安装 Chromium")
    except Exception:
        status_label.setText("检测中...")
        status_label.setStyleSheet(f"color: {tc('muted')}; font-size: 12px;")


def _on_login_clicked(page):
    """登录按钮点击：自动登录（临时线程，不阻塞 UI）"""
    from components.popup_dialog import CustomDialog
    from workers.web_ai.web_ai_manager import get_web_ai_manager
    wm = get_web_ai_manager()

    btn = getattr(page, "_btn_web_login", None)
    if btn is None:
        return

    if wm.is_authenticated("deepseek"):
        result = CustomDialog.question(
            page, "确认登出", "确定要清除 DeepSeek 登录状态吗？\n下次使用将需要重新登录。"
        )
        if result:
            wm.logout("deepseek")
        _refresh_web_status(page)
        _refresh_title_bar_login_btn()
        return

    # 未登录 → 在临时线程中执行 provider.try_auto_login
    btn.setEnabled(False)
    btn.setText("登录中...")

    import threading
    provider = wm.get_provider("deepseek")
    state_path = wm.get_state_path("deepseek")

    def _run():
        try:
            ok = provider.try_auto_login(state_path)
            # 用信号线程安全地回到主线程回调（比 QTimer.singleShot 更可靠）
            _login_signal.done.emit(page, btn, ok)
        except Exception as e:
            _logger.error("登录线程异常: %s", e, exc_info=True)
            _login_signal.done.emit(page, btn, False)

    threading.Thread(target=_run, daemon=True).start()


def _refresh_title_bar_login_btn():
    """同步刷新主界面标题栏的登录按钮"""
    mw = _get_main_window()
    if mw is None:
        return
    try:
        mw._refresh_web_login_btn()
    except Exception:
        pass


def _on_login_done(page, btn, success: bool, error: str = ""):
    """登录完成回调（在主线程执行，由信号触发）"""
    try:
        _refresh_title_bar_login_btn()
        _refresh_web_status(page)

        if btn is not None:
            btn.setEnabled(True)
            btn.setText("登录 DeepSeek 网页版")

        if not success and error and "未完成" not in error and "取消" not in error:
            from components.popup_dialog import CustomDialog
            CustomDialog.warning(page, "登录失败", error)
    except Exception as e:
        _logger.error("登录完成回调异常: %s", e, exc_info=True)


def _on_logout_clicked(page):
    """清除登录状态按钮"""
    from components.popup_dialog import CustomDialog
    result = CustomDialog.question(
        page, "确认清除", "确定要清除 DeepSeek 登录状态吗？\n下次使用将需要重新登录。"
    )
    if not result:
        return

    from workers.web_ai.web_ai_manager import get_web_ai_manager
    wm = get_web_ai_manager()
    wm.logout("deepseek")
    _refresh_web_status(page)
    _refresh_title_bar_login_btn()


def _on_install_chromium(page):
    """安装 Chromium 按钮"""
    btn = getattr(page, "_btn_chromium_install", None)
    if btn is None:
        return

    from workers.web_ai.chromium_checker import get_chromium_checker
    checker = get_chromium_checker()

    if checker.is_playwright_installed() and checker.is_chromium_installed():
        return  # 已安装

    btn.setEnabled(False)
    btn.setProgress(0.0)

    def on_progress(pct: float, text: str):
        try:
            btn.setProgress(pct)
            btn.setText(f"下载中 {int(pct * 100)}%")
        except Exception:
            pass

    from PyQt5.QtCore import QThread, pyqtSignal

    class InstallThread(QThread):
        progress = pyqtSignal(float, str)
        finished = pyqtSignal(bool)

        def run(self):
            try:
                checker = get_chromium_checker()
                if not checker.is_playwright_installed():
                    ok = checker.install_playwright(
                        lambda p, t: self.progress.emit(p * 0.3, t)
                    )
                    if not ok:
                        self.finished.emit(False)
                        return
                ok = checker.install_chromium(
                    lambda p, t: self.progress.emit(0.3 + p * 0.7, t)
                )
                self.finished.emit(ok)
            except Exception:
                self.finished.emit(False)

    thread = InstallThread(page)
    thread.progress.connect(on_progress)

    def on_done(success):
        btn.setEnabled(True)
        if success:
            btn.setProgress(1.0)
            btn.setText("Chromium 已安装")
        else:
            btn.setProgress(0.0)
            btn.setText("安装失败，点击重试")
        _refresh_chromium_status(page)

    thread.finished.connect(on_done)
    thread.start()
    page._install_thread = thread


# ═══════════════════════════════════════
#  主构建函数
# ═══════════════════════════════════════

def build_page(parent_dialog, current_config: dict) -> QWidget:
    # 缓存主窗口引用（供 _refresh_title_bar_login_btn 使用）
    _get_main_window()

    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    add_silabel(page, "API 配置", SiColor.TEXT_A)
    add_silabel(page, "配置 AI 连接方式，支持 API 与网页版", SiColor.TEXT_C, word_wrap=True)

    # ── 1. AI 来源 ──
    provider_row = _build_provider_radios(page, page, current_config)
    layout.addWidget(provider_row)

    # ── 2. API 设置 ──
    page._api_card_container = _build_api_card(page, page, current_config)
    layout.addWidget(page._api_card_container)

    # ── 3. 网页版设置 ──
    page._web_card_container = _build_web_card(page, page)
    layout.addWidget(page._web_card_container)

    # ── 4. Chromium 引擎 ──
    page._chromium_card_container = _build_chromium_card(page, page)
    layout.addWidget(page._chromium_card_container)

    # ── 5. 超时与重试 ──
    page._timeout_card_container = _build_timeout_card(page, page, current_config)
    layout.addWidget(page._timeout_card_container)

    layout.addStretch()

    # ── 绑定按钮事件 ──
    if getattr(page, "_btn_web_login", None):
        page._btn_web_login.clicked.connect(lambda: _on_login_clicked(page))

    if getattr(page, "_btn_web_logout", None):
        page._btn_web_logout.clicked.connect(lambda: _on_logout_clicked(page))

    if getattr(page, "_btn_chromium_install", None):
        page._btn_chromium_install.clicked.connect(lambda: _on_install_chromium(page))

    # ── 初始可见性 ──
    _on_provider_changed(page)

    # ── 页面激活回调（由 settings_dialog 在页面切换时调用） ──
    def _on_page_activated():
        """轻量刷新状态（不启动 Chrome / 子进程）"""
        _lazy_refresh_status_once(page)

    page.on_page_activated = _on_page_activated

    # ── 保存引用 / 配置 ──
    page._saved_config = {
        "api_url": current_config.get("api_url", ""),
        "model": current_config.get("model", "deepseek-v4-flash"),
        "max_tokens": current_config.get("max_tokens", 4096),
        "temperature": current_config.get("temperature", 0.7),
    }

    # ── 安全刷新 SiUI 样式 ──
    try:
        if SiGlobal.siui is not None and hasattr(SiGlobal.siui, "reloadStyleSheetRecursively"):
            SiGlobal.siui.reloadStyleSheetRecursively(page)
    except Exception:
        _logger.warning("SiUI 样式刷新失败（非致命）", exc_info=True)

    return page


def collect_config(page_widget: QWidget) -> dict:
    """收集页面所有配置"""
    cfg = page_widget._saved_config.copy()

    # API Key
    edit_key = getattr(page_widget, "_edit_key", None)
    if edit_key is not None and hasattr(edit_key, "text"):
        cfg["api_key"] = edit_key.text().strip()

    # Provider 类型
    cfg["provider_type"] = _get_ptype(page_widget)
    cfg["provider_id"] = "deepseek"

    # 超时与重试（SiSpinBox 使用 .value()）
    try:
        t = getattr(page_widget, "_edit_timeout", None)
        if t is not None and hasattr(t, "value"):
            cfg["webai_timeout"] = t.value()
    except Exception:
        cfg["webai_timeout"] = 60

    try:
        r = getattr(page_widget, "_edit_retry", None)
        if r is not None and hasattr(r, "value"):
            cfg["webai_max_retries"] = r.value()
    except Exception:
        cfg["webai_max_retries"] = 2

    return cfg
