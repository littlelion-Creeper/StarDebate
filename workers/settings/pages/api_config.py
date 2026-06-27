"""
API 配置设置页 — 使用 PyQt-SiliconUI 重构版组件
仅 API Key 可编辑，其余字段只读展示
"""

import logging

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
)

# PyQt-SiliconUI 重构版组件
from siui.components.widgets import SiLabel
from siui.components.editbox import SiCapsuleLineEdit
from siui.components.button import SiPushButtonRefactor
from siui.core import SiColor, SiGlobal

from components.theme_colors import tc

# 共享设置页工具函数
from workers.settings.pages._page_utils import (
    safe_set_style_data,
    safe_create_card,
    add_silabel,
    make_transparent_row,
)

_logger = logging.getLogger("StarDebate.settings.api_config")


# ═══════════════════════════════════════
#  页面元信息
# ═══════════════════════════════════════

PAGE_INFO = {
    "id": "api_config",
    "name": "API 配置",
    "icon": "api",
    "order": 10,
    "author": "StarDebate",
    "version": "2.0.0",
}

PAGE_CONFIG = {
    "save_path": "config/api_config.json",
    "auto_save": True,
}


def get_default_config() -> dict:
    return {
        "api_url": "",
        "api_key": "",
        "model": "deepseek-v4-flash",
        "max_tokens": 4096,
        "temperature": 0.7,
    }


def _val(text: str, fallback: str = "未配置") -> str:
    return text if text else fallback


def build_page(parent_dialog, current_config: dict) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)

    add_silabel(page, "API 配置", SiColor.TEXT_A)
    add_silabel(page, "配置 AI 模型连接参数，支持 OpenAI 兼容接口", SiColor.TEXT_C, word_wrap=True)

    # ── API 连接卡片 ──
    card = safe_create_card(page)

    if card is None:
        # SiPanelCard 创建失败，使用普通 QWidget 作容器
        from PyQt5.QtWidgets import QFrame, QFormLayout
        card = QFrame(page)
        card.setObjectName("settingsCard")
        card.setStyleSheet(
            f"background-color: {tc('surface')}; border: 1px solid {tc('border')}; "
            f"border-radius: 10px; padding: 16px;"
        )
        fl = QFormLayout(card)
        fl.setSpacing(8)
        url_lbl = QLabel("API 端点")
        url_lbl.setStyleSheet("font-weight: bold;")
        fl.addRow(url_lbl, QLabel(_val(current_config.get("api_url", ""))))

        key_lbl = QLabel("API Key")
        key_lbl.setStyleSheet("font-weight: bold;")
        api_key_input = QLineEdit(current_config.get("api_key", ""))
        api_key_input.setEchoMode(QLineEdit.Password)
        api_key_input.setObjectName("settingsInput")
        fl.addRow(key_lbl, api_key_input)

        model_lbl = QLabel("模型")
        model_lbl.setStyleSheet("font-weight: bold;")
        fl.addRow(model_lbl, QLabel(_val(current_config.get("model", "deepseek-v4-flash"))))

        # 保存引用以便后续 collect_config 取回
        page._edit_key = api_key_input
    else:
        # ★ 正常 SiUI 卡片路径
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
            # 底部焦点指示线条颜色（默认紫色 #D087DF → 跟随主题）
            safe_set_style_data(edit_key, "text_indicator_color_editing", tc("accent_blue"))
            # 刷新内联 QSS（_initStyleSheet 在 __init__ 中将 text_color 写入 QSS，后续修改 style_data 不会自动更新）
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
                        CustomDialog.warning(page, "提示", "请先填写 API Key")
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
                            CustomDialog.information(page, "连接成功", msg)
                        else:
                            CustomDialog.warning(page, "连接失败", msg)

                    worker.test_finished.connect(on_result)
                    worker.start()
                    page._test_worker = worker

                btn_test.clicked.connect(on_test)
                test_row.addWidget(btn_test)
                card.addWidget(test_row_widget)
        except Exception:
            _logger.warning("测试按钮创建失败", exc_info=True)

        # 保存编辑框引用（兼容 SiCapsuleLineEdit 与 QLineEdit 回退）
        page._edit_key = edit_key

        layout.addWidget(card)

    layout.addStretch()

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
    cfg = page_widget._saved_config.copy()
    edit_key = getattr(page_widget, "_edit_key", None)
    if edit_key is not None and hasattr(edit_key, "text"):
        cfg["api_key"] = edit_key.text().strip()
    return cfg
