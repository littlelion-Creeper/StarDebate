"""StarDebate ★ 扩展包管理面板（中心区页面）
============================================================================
使用 SiUI 组件构建的 centre_stack 页面：
  - 顶部工具栏：返回按钮 + 标题 + 安装/打开文件夹按钮
  - 中部滚动区：SiRowCard 平面卡片列表（每个扩展包一张）
  - 底部状态栏：扩展包总数

卡片结构（垂直多行）：
  Row 1: 🔧 名称 v版本              [状态切换]
  Row 2:     作者: xxx              [长按删除]
  Row 3:     描述文本（自动换行）
  Row 4: (禁用态) ⚠ 已禁用 - 重启后将不再加载
============================================================================
"""
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

# SiUI 组件（带 fallback）
try:
    from siui.components.button import SiPushButtonRefactor, SiToggleButtonRefactor, SiLongPressButtonRefactor
    from siui.components.widgets import SiLabel as SiLabel
    from siui.components.container import SiRowCard
    from siui.core import SiGlobal, SiColor
    from siui.components.slider_ import SiScrollAreaRefactor
    _SIUI_AVAILABLE = True
except ImportError:
    SiPushButtonRefactor = None
    SiToggleButtonRefactor = None
    SiLongPressButtonRefactor = None
    SiLabel = None
    SiRowCard = None
    SiGlobal = None
    SiColor = None
    SiScrollAreaRefactor = None
    _SIUI_AVAILABLE = False

from components.theme_colors import tc
from components.icon_loader import load_common_icon
from workers.settings.pages._page_utils import safe_set_style_data
from . import get_manager as get_ext_manager


def _style_toolbar_btn(btn, bg_color: str, fg_color: str):
    """统一设置工具栏按钮样式，匹配主 UI 风格。"""
    safe_set_style_data(btn, "button_color", bg_color)
    safe_set_style_data(btn, "text_color", fg_color)


def _style_toggle_card(card):
    """为扩展包卡片设置背景色。"""
    card.setStyleSheet(f"#extCard {{ background-color: {tc('surface')}; border-radius: 8px; }}")


def _style_label(label, color_str: str):
    """设置 SiLabel 文字颜色。SiLabel 无 style_data，需用 setTextColor。"""
    try:
        label.setTextColor(color_str)
    except Exception:
        safe_set_style_data(label, "text_color", color_str)


class ExtensionPanelManager:
    """扩展包管理面板管理器（中心区页面）"""

    def __init__(self, main_window):
        self._mw = main_window
        self._page = None
        self._scroll_content = None
        self._card_layout = None
        self._count_label = None
        self._empty_hint = None
        self._ext_mgr = get_ext_manager()

    def build_page(self) -> QWidget:
        """构建扩展包管理页面，返回 QWidget。由 centre_stack 调用。"""
        page = QWidget()
        page.setObjectName("extensionManagerPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── 顶部工具栏 ──
        toolbar = self._build_toolbar()
        layout.addWidget(toolbar)

        # ── 统计标签 ──
        self._count_label = SiLabel(page) if _SIUI_AVAILABLE else self._fallback_label(page)
        self._count_label.setText("扩展包总数: 0")
        _style_label(self._count_label, tc("muted"))
        self._count_label.setFixedHeight(24)
        layout.addWidget(self._count_label)

        # ── 滚动区域 ──
        scroll = SiScrollAreaRefactor(page) if _SIUI_AVAILABLE else QScrollArea(page)
        scroll.setWidgetResizable(True)
        scroll.setObjectName("extensionScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        if hasattr(scroll, 'setBorderRadius'):
            scroll.setBorderRadius(8)

        scroll_content = QWidget()
        scroll_content.setObjectName("extensionScrollContent")
        card_layout = QVBoxLayout(scroll_content)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(8)
        card_layout.setAlignment(Qt.AlignTop)

        scroll.setWidget(scroll_content)
        self._scroll_content = scroll_content
        self._card_layout = card_layout

        layout.addWidget(scroll, stretch=1)

        self._page = page

        # ── 空状态提示 ──
        self._empty_hint = SiLabel(page) if _SIUI_AVAILABLE else self._fallback_label(page)
        self._empty_hint.setText("暂无扩展包，点击上方「安装扩展包」按钮安装")
        self._empty_hint.setAlignment(Qt.AlignCenter)
        _style_label(self._empty_hint, tc("muted"))
        self._empty_hint.setFixedHeight(80)

        return page

    def _build_toolbar(self) -> QWidget:
        """构建顶部工具栏"""
        toolbar = QWidget()
        toolbar.setObjectName("extToolbar")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(10)

        # 返回按钮（普通按钮，surface 背景）
        btn_back = SiPushButtonRefactor(toolbar) if _SIUI_AVAILABLE else self._fallback_btn(toolbar)
        btn_back.setText("←  返回")
        btn_back.setToolTip("返回欢迎页")
        self._auto_size_btn(btn_back, "←  返回", 32)
        _style_toolbar_btn(btn_back, tc("surface"), tc("text"))
        btn_back.clicked.connect(self._on_back)

        # 标题
        title = SiLabel(toolbar) if _SIUI_AVAILABLE else self._fallback_label(toolbar)
        title.setText("扩展包管理")
        _style_label(title, tc("text"))
        title.setFixedHeight(32)
        font = title.font()
        font.setPointSize(14)
        font.setBold(True)
        title.setFont(font)

        tb_layout.addWidget(btn_back)
        tb_layout.addWidget(title, stretch=1)

        # 安装按钮（主操作按钮，蓝色强调色）
        btn_install = SiPushButtonRefactor(toolbar) if _SIUI_AVAILABLE else self._fallback_btn(toolbar)
        btn_install.setText("📦 安装扩展包")
        btn_install.setToolTip("安装 .sep 扩展包文件")
        self._auto_size_btn(btn_install, "📦 安装扩展包", 32)
        _style_toolbar_btn(btn_install, tc("accent_blue"), tc("base"))
        btn_install.clicked.connect(self._on_install_extension)

        # 打开文件夹按钮（普通按钮）
        btn_open = SiPushButtonRefactor(toolbar) if _SIUI_AVAILABLE else self._fallback_btn(toolbar)
        btn_open.setText("打开文件夹")
        btn_open.setToolTip("在资源管理器中打开扩展包目录")
        self._auto_size_btn(btn_open, "打开文件夹", 32)
        _style_toolbar_btn(btn_open, tc("surface"), tc("text"))
        btn_open.clicked.connect(self._on_open_folder)

        tb_layout.addWidget(btn_install)
        tb_layout.addWidget(btn_open)

        return toolbar

    def refresh_list(self):
        """刷新扩展包列表"""
        if self._card_layout is None:
            return

        # 清空现有卡片（_empty_hint 是持久控件，仅从布局移除，不 deleteLater）
        while self._card_layout.count() > 0:
            item = self._card_layout.takeAt(0)
            if item and item.widget():
                if item.widget() is self._empty_hint:
                    continue  # 保留 C++ 对象，后续可能会重新 addWidget
                item.widget().deleteLater()

        extensions = self._ext_mgr.get_all()
        count = len(extensions)

        # 更新计数
        if self._count_label:
            self._count_label.setText(f"已安装 {count} 个扩展包")

        if count == 0:
            # 显示空状态
            if self._empty_hint:
                self._card_layout.addWidget(self._empty_hint)
                self._empty_hint.setVisible(True)
            return

        if self._empty_hint:
            self._empty_hint.setVisible(False)

        # 为每个扩展包创建卡片
        for info in extensions:
            card = self._create_card(info)
            self._card_layout.addWidget(card)

        # 添加底部弹性空间
        self._card_layout.addStretch()

    def _create_card(self, info) -> QWidget:
        """为单个扩展包创建卡片"""
        card = QFrame()
        card.setObjectName("extCard")
        _style_toggle_card(card)
        # 使用 QFrame + QVBoxLayout 作为平面行卡容器
        main_layout = QVBoxLayout(card)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(4)

        # ── 第 1 行：图标 + 名称 + 版本 + 状态切换按钮 ──
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        name_label = SiLabel(card) if _SIUI_AVAILABLE else self._fallback_label(card)
        if info.tags:
            icon_char = info.tags[0][:1] if info.tags[0] else "🧩"
        else:
            icon_char = "🧩"
        name_label.setText(f"{icon_char}  {info.name}    v{info.version}")
        _style_label(name_label, tc("text"))
        font = name_label.font()
        font.setPointSize(12)
        font.setBold(True)
        name_label.setFont(font)

        # 状态切换按钮（SiToggleButtonRefactor，匹配 NavButton 风格）
        toggle_btn = SiToggleButtonRefactor(card) if _SIUI_AVAILABLE else self._fallback_btn(card)
        toggle_btn.setCheckable(True)
        toggle_btn.setFixedSize(90, 28)
        toggle_btn.setChecked(info.enabled)
        toggle_btn.setText("已启用" if info.enabled else "已禁用")
        if info.enabled:
            safe_set_style_data(toggle_btn, "button_color", tc("accent_blue"))
            safe_set_style_data(toggle_btn, "text_color", tc("base"))
            safe_set_style_data(toggle_btn, "toggled_button_color", tc("accent_blue"))
            safe_set_style_data(toggle_btn, "toggled_text_color", tc("base"))
        else:
            safe_set_style_data(toggle_btn, "button_color", tc("surface"))
            safe_set_style_data(toggle_btn, "text_color", tc("muted"))
            safe_set_style_data(toggle_btn, "toggled_button_color", tc("accent_blue"))
            safe_set_style_data(toggle_btn, "toggled_text_color", tc("base"))
        # 同步渲染变量
        try:
            toggle_btn._button_rect_color = QColor(tc("accent_blue") if info.enabled else tc("surface"))
            toggle_btn._text_color = QColor(tc("base") if info.enabled else tc("muted"))
        except Exception:
            pass
        toggle_btn.clicked.connect(lambda: self._on_toggle_click(info.ext_id, toggle_btn))

        row1.addWidget(name_label, stretch=1)
        row1.addWidget(toggle_btn)
        main_layout.addLayout(row1)

        # ── 第 2 行：作者 + 长按删除按钮 ──
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        author_label = SiLabel(card) if _SIUI_AVAILABLE else self._fallback_label(card)
        author_label.setText(f"    作者: {info.author}")
        _style_label(author_label, tc("muted"))
        font = author_label.font()
        font.setPointSize(10)
        author_label.setFont(font)

        # 长按删除按钮（红色危险操作）
        #   未按下：红字(surface背景)，按下时亮红填充从左到右增长 + 白字
        del_btn = SiLongPressButtonRefactor(card) if _SIUI_AVAILABLE else self._fallback_btn(card)
        del_btn.setText("长按删除")
        del_btn.setToolTip("长按即可删除此扩展包")
        del_btn.setFixedSize(90, 26)
        safe_set_style_data(del_btn, "button_color", tc("surface"))           # 未填充区域
        safe_set_style_data(del_btn, "progress_color", tc("accent_red"))      # 填充增长颜色（亮红）
        safe_set_style_data(del_btn, "text_color", tc("accent_red"))          # 未按下时红字
        safe_set_style_data(del_btn, "click_color", tc("accent_red"))         # 点击闪烁色
        del_btn.longPressed.connect(lambda: self._on_delete_extension(info.ext_id))

        row2.addWidget(author_label, stretch=1)
        row2.addWidget(del_btn)
        main_layout.addLayout(row2)

        # ── 第 3 行：描述文本 ──
        if info.description:
            desc_label = SiLabel(card) if _SIUI_AVAILABLE else self._fallback_label(card)
            desc_label.setText(f"    {info.description}")
            desc_label.setWordWrap(True)
            _style_label(desc_label, tc("text"))
            font = desc_label.font()
            font.setPointSize(10)
            desc_label.setFont(font)
            main_layout.addWidget(desc_label)

        # ── 第 4 行（仅禁用态）：提示文字 ──
        if not info.enabled:
            warn_label = SiLabel(card) if _SIUI_AVAILABLE else self._fallback_label(card)
            warn_label.setText("    ⚠ 已禁用 - 重启后将不再加载")
            warn_label.setWordWrap(True)
            _style_label(warn_label, tc("accent_yellow"))
            font = warn_label.font()
            font.setPointSize(10)
            warn_label.setFont(font)
            main_layout.addWidget(warn_label)

        # 保存引用供 toggle 更新用
        card._toggle_btn = toggle_btn
        card._ext_id = info.ext_id

        return card

    def _on_toggle_click(self, ext_id: str, btn):
        """点击状态切换按钮"""
        info = self._ext_mgr.get(ext_id)
        if info is None:
            return
        new_state = not info.enabled
        info.enabled = new_state
        self._ext_mgr.set_enabled(ext_id, new_state)

        # 更新按钮状态（完整刷新 style_data + 渲染变量）
        btn.setText("已启用" if new_state else "已禁用")
        if new_state:
            safe_set_style_data(btn, "button_color", tc("accent_blue"))
            safe_set_style_data(btn, "text_color", tc("base"))
        else:
            safe_set_style_data(btn, "button_color", tc("surface"))
            safe_set_style_data(btn, "text_color", tc("muted"))
        try:
            btn._button_rect_color = QColor(tc("accent_blue") if new_state else tc("surface"))
            btn._text_color = QColor(tc("base") if new_state else tc("muted"))
            btn.update()
        except Exception:
            pass

        # 显示 Toast
        self._show_toast("已" + ("启用" if new_state else "禁用") + "，重启后生效")

        # 重建卡片（刷新禁用提示行）
        self.refresh_list()

    def _on_delete_extension(self, ext_id: str):
        """点击删除扩展包"""
        from components.popup_dialog import CustomDialog
        info = self._ext_mgr.get(ext_id)
        name = info.name if info else ext_id
        dlg = CustomDialog(
            self._mw,
            dialog_type="custom",
            title="删除扩展包",
            message=f"确定要删除扩展包「{name}」吗？\n\n此操作将从磁盘中移除扩展包文件，且不可撤销。",
            buttons=[("取消", "cancel"), ("确认删除", "delete")],
        )
        dlg.exec_()
        if dlg.clicked_button == "delete":
            self._ext_mgr.delete_extension(ext_id)
            self.refresh_list()
            self._show_toast(f"已删除扩展包: {name}")

    def _on_install_extension(self):
        """点击安装扩展包"""
        from PyQt5.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self._page.parent() if self._page else None,
            "选择扩展包文件", "",
            "扩展包文件 (*.sep);;所有文件 (*.*)"
        )
        if not file_path:
            return

        result = self._ext_mgr.install_extension(file_path)
        if result["success"]:
            self.refresh_list()
            self._show_toast("扩展包安装成功，重启后生效")
        else:
            from components.popup_dialog import CustomDialog
            CustomDialog.warning(
                self._page.parent() if self._page else None,
                "安装失败",
                result.get("error", "未知错误"),
            )

    def _on_open_folder(self):
        """打开扩展包文件夹"""
        self._ext_mgr.open_extension_folder()

    def _on_back(self):
        """返回欢迎页"""
        mw = self._mw
        if mw and hasattr(mw, 'centre_stack'):
            mw.centre_stack.setCurrentIndex(0)

    def _show_toast(self, msg: str):
        """显示简单 Toast"""
        mw = self._mw
        if mw and hasattr(mw, '_update_status'):
            mw._update_status(f"🔧 {msg}")

    def _auto_size_btn(self, btn, text: str, height: int, padding_h: int = 16):
        """自动计算按钮宽度"""
        if btn is None:
            return
        try:
            fm = btn.fontMetrics()
            text_width = fm.horizontalAdvance(text)
            btn.setFixedHeight(height)
            btn.setMinimumWidth(max(40, text_width + padding_h))
        except Exception:
            btn.setFixedHeight(height)
            btn.setMinimumWidth(80)

    # ── 回退控件工厂（SiUI 不可用时）──

    def _fallback_label(self, parent):
        from PyQt5.QtWidgets import QLabel
        return QLabel(parent)

    def _fallback_btn(self, parent):
        from PyQt5.QtWidgets import QPushButton
        return QPushButton(parent)
