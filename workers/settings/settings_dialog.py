from components.theme_colors import tc, refresh
"""
设置对话框主体
- 顶部：自定义 TitleBar（复用 components.title_bar）
- 左侧：动态导航栏（自动扫描内置页面 + 加载插件注册页面）
- 右侧：QStackedWidget 显示当前选中页面的内容
- 底部：状态栏 + 保存/取消按钮
"""

import os
import sys
import ctypes
import traceback
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QPushButton, QStackedWidget, QScrollArea, QFrame,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, QEvent, pyqtSignal
from PyQt5.QtGui import QColor, QFont

from components.title_bar import TitleBar
from .settings_page_base import SettingsPageInfo, PageRegistry
from workers.settings.pages._page_utils import safe_set_style_data

# SiUI imports (带 fallback)
try:
    from siui.components.button import SiToggleButtonRefactor, SiPushButtonRefactor
    from siui.components.slider_ import SiScrollAreaRefactor as SiScrollArea
    from siui.components.widgets import SiLabel as SiLabel
    from siui.core import SiGlobal
    _SIUI_AVAILABLE = True
except ImportError:
    SiToggleButtonRefactor = QPushButton
    SiPushButtonRefactor = QPushButton
    SiScrollArea = QScrollArea
    SiLabel = QLabel
    SiGlobal = None
    _SIUI_AVAILABLE = False


class NavButton(SiToggleButtonRefactor):
    """左侧导航栏按钮 (SiUI)"""

    def __init__(self, page_info: SettingsPageInfo, parent=None):
        super().__init__(parent)
        self._page_info = page_info
        self.setFixedHeight(40)

        name = page_info.name
        self.setText(f"  {name}")
        self.setToolTip(f"{name}\n{page_info.author} v{page_info.version}" if page_info.author else name)

        # 应用 SiUI 主题色
        safe_set_style_data(self, "button_color", tc("surface"))
        safe_set_style_data(self, "text_color", tc("text"))       # 未选中：深色主题自动变浅，浅色主题自动变深
        safe_set_style_data(self, "toggled_button_color", tc("accent_blue"))
        safe_set_style_data(self, "toggled_text_color", tc("base"))

        # 直接同步渲染变量（SiToggleButtonRefactor 实际绘制用 _button_rect_color / _text_color，
        # 而非 style_data 本身。style_data 只在动画启动时作为 endValue 读取。
        # 若不立即同步，按钮首次渲染显示的是 style_data 的默认颜色而非主题色）
        try:
            self._button_rect_color = QColor(tc("surface"))
            self._text_color = QColor(tc("text"))
        except Exception:
            pass

    @property
    def page_info(self) -> SettingsPageInfo:
        return self._page_info


class SizeAwareStackedWidget(QStackedWidget):
    """QStackedWidget 子类，sizeHint/minimumSizeHint 仅反映当前页尺寸。

    原生 QStackedWidget 取所有子页的最大尺寸导致内容少的页面也分配相同高度。
    """

    def sizeHint(self):
        w = self.currentWidget()
        if w is not None:
            return w.sizeHint()
        return super().sizeHint()

    def minimumSizeHint(self):
        w = self.currentWidget()
        if w is not None:
            return w.minimumSizeHint()
        return super().minimumSizeHint()

    def setCurrentIndex(self, index: int):
        super().setCurrentIndex(index)
        self.updateGeometry()  # 通知父布局重新询问尺寸


class ContentSizedScrollArea(QScrollArea):
    """QScrollArea 子类，sizeHint 跟随内容 widget 的尺寸而非视口。

    窗口模式：sizeHint = 内容原始高度，配合底部撑板实现紧凑布局。
    最大化模式：sizePolicy 切换为 Expanding + 解除 maxHeight，内容撑满视图。

    保留 setWidgetResizable(True) 让 Qt 自动管理宽度。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Preferred: 高度锚定 sizeHint，不自动膨胀；空间不足时可收缩（出滚动条）
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def sizeHint(self):
        w = self.widget()
        if w is not None:
            return w.sizeHint()
        return super().sizeHint()

    def minimumSizeHint(self):
        w = self.widget()
        if w is not None:
            hs = w.minimumSizeHint()
            if hs.isValid() and hs.height() > 0:
                return hs
        return super().minimumSizeHint()


class SettingsDialog(QDialog):
    """IDE 风格设置对话框"""

    # 保存完成信号 (用于主窗口刷新版本号等)
    saved = pyqtSignal()
    # 主题变更信号 (theme_name: str)
    theme_changed = pyqtSignal(str)

    def __init__(self, parent=None, app_version: str = "1.2.0",
                 initial_plugin_id: str = "",
                 theme_change_callback: callable = None):
        super().__init__(parent)
        self._app_version = app_version
        self._pages: list[SettingsPageInfo] = []
        self._nav_buttons: list[NavButton] = []
        self._current_page: SettingsPageInfo | None = None
        self._plugin_callbacks: dict[str, callable] = {}  # plugin_id → collect_config 回调
        self._initial_plugin_id = initial_plugin_id
        self._theme_change_callback = theme_change_callback
        self._pending_theme = None  # 待应用的 theme_name
        self._page_sh = None  # 当前页面原始大小提示高度，用于最大化/还原切换

        self.setWindowTitle("⚙️ 设置 - StarDebate")
        self.resize(820, 580)
        self.setMinimumSize(680, 480)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)

        if parent:
            pg = parent.geometry()
            self.move(
                pg.x() + (pg.width() - self.width()) // 2,
                pg.y() + (pg.height() - self.height()) // 2,
            )

        self._setup_ui()
        self._load_style()
        self._scan_and_build_pages()

    # ═══════════════════════════════════════
    #  UI 构建
    # ═══════════════════════════════════════

    def _setup_ui(self):
        """构建对话框主布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 自定义标题栏 ──
        self._title_bar = TitleBar(self, "设置", "⚙️")
        main_layout.addWidget(self._title_bar)

        # ── 主体区域（左侧导航 + 右侧内容）──
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # 左侧导航栏
        self._nav_container = QWidget()
        self._nav_container.setObjectName("settingsNav")
        self._nav_container.setFixedWidth(180)
        nav_scroll = SiScrollArea()
        nav_scroll.setObjectName("settingsNavScroll")
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_scroll.setStyleSheet("")  # 清除 SiScrollAreaRefactor 默认 inline style，让 QSS 接管

        nav_inner = QWidget()
        nav_inner.setObjectName("settingsNavInner")
        self._nav_layout = QVBoxLayout(nav_inner)
        self._nav_layout.setContentsMargins(8, 12, 8, 12)
        self._nav_layout.setSpacing(2)
        self._nav_layout.addStretch()  # 底部弹簧

        nav_scroll.setWidget(nav_inner)

        nav_outer = QVBoxLayout(self._nav_container)
        nav_outer.setContentsMargins(0, 0, 0, 0)
        nav_outer.addWidget(nav_scroll)

        body.addWidget(self._nav_container)

        # 分隔线
        sep = QFrame()
        sep.setObjectName("settingsVertSep")
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
        body.addWidget(sep)

        # 右侧内容区
        right_area = QWidget()
        right_layout = QVBoxLayout(right_area)
        right_layout.setContentsMargins(24, 20, 24, 0)
        right_layout.setSpacing(0)

        self._scroll_area = ContentSizedScrollArea()
        self._scroll_area.setObjectName("settingsContentScroll")
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setFrameShape(QFrame.NoFrame)

        self._content_stack = SizeAwareStackedWidget()
        self._content_stack.setObjectName("settingsContentStack")
        self._scroll_area.setWidget(self._content_stack)

        right_layout.addWidget(self._scroll_area, stretch=0)

        # 底部撑板：窗口模式吸收多余空间；最大化时隐藏
        self._bottom_spacer = QWidget()
        self._bottom_spacer.setObjectName("settingsBottomSpacer")
        self._bottom_spacer.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        right_layout.addWidget(self._bottom_spacer, stretch=1)
        body.addWidget(right_area, stretch=1)
        main_layout.addLayout(body, stretch=1)

        # ── 底部状态栏 ──
        footer = QFrame()
        footer.setObjectName("settingsFooter")
        footer.setFixedHeight(48)
        ft_layout = QHBoxLayout(footer)
        ft_layout.setContentsMargins(16, 0, 16, 0)
        ft_layout.setSpacing(12)

        lbl_info = QLabel(f"v{self._app_version}")
        lbl_info.setObjectName("settingsFooterInfo")
        ft_layout.addWidget(lbl_info)
        ft_layout.addStretch()

        self._btn_test = SiPushButtonRefactor.withText("测试连接")
        self._btn_test.setFixedSize(140, 36)
        self._btn_test.clicked.connect(self._on_test_connection)
        ft_layout.addWidget(self._btn_test)

        btn_cancel = SiPushButtonRefactor.withText("取消")
        btn_cancel.setFixedSize(64, 36)
        btn_cancel.clicked.connect(self.reject)
        ft_layout.addWidget(btn_cancel)

        btn_save = SiPushButtonRefactor.withText("保存")
        btn_save.setFixedSize(100, 36)
        safe_set_style_data(btn_save, "button_color", tc("accent_blue"))
        safe_set_style_data(btn_save, "text_color", tc("base"))
        btn_save.clicked.connect(self._on_save)
        ft_layout.addWidget(btn_save)

        main_layout.addWidget(footer)

        self._footer_info = lbl_info
        self._btn_save = btn_save

        # 刷新 SiUI 主题
        if _SIUI_AVAILABLE:
            try:
                SiGlobal.siui.reloadStyleSheetRecursively(self)
            except Exception:
                pass

    # ═══════════════════════════════════════
    #  页面扫描与构建
    # ═══════════════════════════════════════

    def _scan_and_build_pages(self):
        """扫描内置设置页 + 加载插件设置页，构建导航按钮"""
        # 1. 扫描内置页面
        PageRegistry.scan_builtin_pages()

        # 2. 自动扫描插件 settings.py
        PageRegistry.scan_plugin_pages()

        # 3. 获取所有页面（含插件注册的）
        all_raw = PageRegistry.get_all_pages()

        self._pages.clear()
        for raw in all_raw:
            info = PageRegistry.create_page_info(raw)
            self._pages.append(info)

        # 4. 构建导航按钮
        self._build_nav_buttons()

        # 5. 默认选中第一页（若指定了 initial_plugin_id 则导航到该插件页）
        if self._pages:
            target_idx = 0
            if self._initial_plugin_id:
                target_page_id = f"plugin_{self._initial_plugin_id}_settings"
                for i, info in enumerate(self._pages):
                    if info.page_id == target_page_id:
                        target_idx = i
                        break
            self._select_page(target_idx)

    def _build_nav_buttons(self):
        """重建左侧导航按钮列表"""
        # 清除旧按钮
        for btn in self._nav_buttons:
            self._nav_layout.removeWidget(btn)
            btn.deleteLater()
        self._nav_buttons.clear()

        if not self._pages:
            # 空状态
            empty = QLabel("没有可用的设置页")
            empty.setObjectName("settingsNavEmpty")
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            self._nav_buttons = []
            self._nav_layout.insertWidget(
                self._nav_layout.count() - 1, empty
            )
            return

        builtin_count = 0
        for i, info in enumerate(self._pages):
            # 在最后一个内置页面和第一个插件页面之间插入分隔线
            if info.source == "plugin" and builtin_count == 0:
                builtin_count = sum(1 for p in self._pages if p.source == "builtin")
                if builtin_count > 0:
                    sep_label = SiLabel()
                    sep_label.setText("─── 插件页面 ───")
                    sep_label.setObjectName("settingsNavSep")
                    sep_label.setAlignment(Qt.AlignCenter)
                    sep_label.setFixedHeight(30)
                    self._nav_layout.insertWidget(
                        self._nav_layout.count() - 1, sep_label
                    )

            btn = NavButton(info, self)
            btn.clicked.connect(lambda checked, idx=i: self._select_page(idx))
            self._nav_buttons.append(btn)
            # 插入到 stretch 之前
            self._nav_layout.insertWidget(
                self._nav_layout.count() - 1, btn
            )

    def _select_page(self, index: int):
        """选择并显示指定页面（延迟构建）"""
        if index < 0 or index >= len(self._pages):
            return

        # 更新导航按钮选中状态
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)

        info = self._pages[index]
        self._current_page = info

        # 检查是否已构建
        widget = info.build_widget(self)
        if widget is None:
            # 构建失败，显示错误占位
            err_widget = QLabel(f"页面加载失败: {info.name}")
            err_widget.setAlignment(Qt.AlignCenter)
            err_widget.setStyleSheet(f"color: {tc("accent_red")}; padding: 40px;")
            self._content_stack.addWidget(err_widget)
            self._content_stack.setCurrentWidget(err_widget)
            return

        # 添加或切换到该页面
        idx_in_stack = self._content_stack.indexOf(widget)
        if idx_in_stack < 0:
            self._content_stack.addWidget(widget)
            idx_in_stack = self._content_stack.indexOf(widget)
        self._content_stack.setCurrentIndex(idx_in_stack)

        # ★ 通知页面已被激活（用于设置页的轻量刷新）
        if hasattr(widget, 'on_page_activated'):
            try:
                widget.on_page_activated()
            except Exception:
                pass

        # 记录页面原始高度，钳制内容高度（窗口模式保持紧凑）
        sh = widget.sizeHint()
        self._page_sh = sh.height()
        self._content_stack.setMinimumHeight(self._page_sh)
        if not self.isMaximized():
            self._content_stack.setMaximumHeight(self._page_sh)

        # 沿父链向上传播 updateGeometry，触发布局重算
        w: QWidget = self._content_stack
        while w:
            w.updateGeometry()
            w = w.parentWidget()

        # 更新底部信息
        self._footer_info.setText(f"v{self._app_version}  |  {info.name}")

        # 测试按钮：仅在 API 配置页显示
        self._btn_test.setVisible(info.page_id == "api_config")

    # ═══════════════════════════════════════
    #  保存操作
    # ═══════════════════════════════════════

    def _on_save(self):
        """保存所有设置页，检查主题变更"""
        saved_count = 0
        error_pages = []
        new_theme = None

        for info in self._pages:
            try:
                # 外观页：仅收集配置检测主题变更（文件名匹配 appearance_page.py）
                if info.page_id in ("appearance", "appearance_page"):
                    cfg = info.collect_config()
                    if cfg:
                        new_theme = cfg.get("theme")
                    continue

                if not info.auto_save:
                    continue

                if info.save_config():
                    saved_count += 1
                else:
                    if info.save_path:
                        error_pages.append(info.name)
            except Exception as e:
                error_pages.append(f"{info.name}({e})")

        if error_pages:
            from components.popup_dialog import CustomDialog
            CustomDialog.warning(
                self, "保存提示",
                f"以下页面保存失败:\n" + "\n".join(error_pages) +
                f"\n\n已成功保存 {saved_count} 个页面。"
            )
        else:
            self._update_status(f"已保存 {saved_count} 个设置页")

        # 主题变更：通过回调保存并应用（save_config 内部保存到 config.json）
        if new_theme and self._theme_change_callback:
            self._theme_change_callback(new_theme)

        # 告知主窗口保存完成
        self.saved.emit()
        self.accept()

    def _on_test_connection(self):
        """测试 API 连接（委托给当前 API 配置页的处理）"""
        if self._current_page and self._current_page.page_id == "api_config":
            widget = self._current_page._widget
            if widget and hasattr(widget, '_btn_test'):
                widget._btn_test.click()  # 触发 API 配置页的测试逻辑

    def _update_status(self, msg: str):
        """更新底部状态信息"""
        self._footer_info.setText(msg)

    # ═══════════════════════════════════════
    #  公开 API
    # ═══════════════════════════════════════

    def navigate_to_plugin_page(self, plugin_id: str):
        """导航到指定插件的设置页（公开 API）"""
        target_page_id = f"plugin_{plugin_id}_settings"
        for i, info in enumerate(self._pages):
            if info.page_id == target_page_id:
                self._select_page(i)
                return True
        return False

    def get_page_config(self, page_id: str) -> dict | None:
        """获取指定页面的配置"""
        for info in self._pages:
            if info.page_id == page_id:
                return info.collect_config()
        return None

    def get_all_configs(self) -> dict[str, dict]:
        """获取所有页面的配置"""
        result = {}
        for info in self._pages:
            cfg = info.collect_config()
            if cfg is not None:
                result[info.page_id] = cfg
        return result

    def get_version_from_about(self) -> str:
        """从关于页获取版本号"""
        cfg = self.get_page_config("about_page")
        if cfg:
            return cfg.get("version", self._app_version)
        return self._app_version

    # ═══════════════════════════════════════
    #  窗口事件
    # ═══════════════════════════════════════

    def nativeEvent(self, event_type, message):
        """Windows: 处理无边框窗口的边缘拖拽缩放"""
        if sys.platform != 'win32':
            return False, 0
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST
                x = msg.lParam & 0xFFFF
                y = (msg.lParam >> 16) & 0xFFFF
                g = self.geometry()
                border = 6
                left = x < g.left() + border
                right = x > g.right() - border
                top = y < g.top() + border
                bottom = y > g.bottom() - border
                if top and left:
                    return True, 13
                if top and right:
                    return True, 14
                if bottom and left:
                    return True, 16
                if bottom and right:
                    return True, 17
                if left:
                    return True, 10
                if right:
                    return True, 11
                if top:
                    return True, 12
                if bottom:
                    return True, 15
            return False, 0
        except Exception:
            return False, 0

    def changeEvent(self, event):
        """监听窗口最大化/还原，切换布局模式"""
        if event.type() == QEvent.WindowStateChange:
            if self.isMaximized():
                self._on_enter_maximize()
            else:
                self._on_exit_maximize()
        super().changeEvent(event)

    def _on_enter_maximize(self):
        """最大化：隐藏底部撑板 + 内容撑满视图"""
        self._bottom_spacer.hide()
        self._scroll_area.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        self._content_stack.setMaximumHeight(16777215)

    def _on_exit_maximize(self):
        """还原：显示底部撑板 + 恢复内容高度钳制"""
        self._bottom_spacer.show()
        self._scroll_area.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred
        )
        if self._page_sh is not None:
            self._content_stack.setMaximumHeight(self._page_sh)

    # ═══════════════════════════════════════
    #  样式加载
    # ═══════════════════════════════════════

    def _load_style(self):
        """加载设置对话框 QSS 样式（跟随当前主题）"""
        import json
        from components.res_path import get_resource_root
        project_root = get_resource_root()

        # 从 config.json 读取当前主题
        from workers.app_config.config_paths import get_config_path
        theme_name = "notion_dark"
        config_path = get_config_path("config/config.json")
        if os.path.isfile(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                theme_name = cfg.get("theme", "notion_dark")
            except (json.JSONDecodeError, OSError):
                pass

        theme_dir = os.path.join(project_root, "style", "themes", theme_name)
        # 若主题目录不存在，回退默认
        if not os.path.isdir(theme_dir):
            theme_dir = os.path.join(project_root, "style", "themes", "notion_dark")

        combined = ""
        for qss_name in ("settings.qss", "title_bar.qss", "star_spinbox.qss", "svg_renderer.qss"):
            qss_path = os.path.join(theme_dir, qss_name)
            if os.path.isfile(qss_path):
                try:
                    with open(qss_path, "r", encoding="utf-8") as f:
                        combined += f.read() + "\n"
                except Exception:
                    pass

        if combined:
            self.setStyleSheet(combined)
        else:
            self._apply_fallback_style()

    def _apply_fallback_style(self):
        """备用内联样式"""
        C = {
            "base": tc("base"), "surface": tc("surface"), "overlay": tc("overlay"),
            "crust": tc("crust"), "text": tc("text"), "subtext": tc("subtext"),
            "muted": tc("muted"), "border": tc("border"), "divider": tc("divider"),
            "accent_blue": tc("accent_blue"), "accent_lavender": tc("accent_lavender"),
        }
        qss = """
            QWidget {
                background-color: {base};
                color: {text};
                font-family: "Microsoft YaHei";
            }
            /* 标题栏 */
            #titleBar {
                background-color: {surface};
                border-bottom: 1px solid {overlay};
            }
            #titleIcon { color: {accent_blue}; background: transparent; border: none; font-size: 22px; }
            #titleLabel { color: {text}; background: transparent; border: none; font-size: 16px; }
            #titleDragArea { background: transparent; }
            #minBtn, #maxBtn, #closeBtn { background: transparent; border: none; border-radius: 0px; color: transparent; }
            #settingsNav {
                background-color: {surface};
            }
            #settingsNavScroll {
                background-color: {surface};
            }
            #settingsNavInner {
                background-color: {surface};
            }
            #settingsNavSep {
                color: {border};
                font-size: 11px;
                padding: 4px 0;
            }
            #settingsNavEmpty {
                color: {muted};
                font-size: 12px;
                padding: 20px;
            }
            #settingsVertSep {
                background-color: {overlay};
            }
            #settingsContentScroll {
                background-color: {base};
            }
            #settingsSectionTitle {
                color: {accent_blue};
                font-size: 20px;
                font-weight: bold;
            }
            #settingsSectionDesc {
                color: {muted};
                font-size: 13px;
                margin-bottom: 4px;
            }
            #settingsCard {
                background-color: {surface};
                border: 1px solid {overlay};
                border-radius: 10px;
            }
            #settingsLabel {
                color: {subtext};
                font-size: 13px;
                font-weight: bold;
            }
            #settingsValueLabel {
                color: {text};
                font-size: 14px;
            }
            #settingsHint {
                color: {muted};
                font-size: 12px;
            }
            #settingsInput {
                background-color: {crust};
                border: 1px solid {overlay};
                border-radius: 8px;
                padding: 7px 14px;
                color: {text};
                font-size: 13px;
            }
            #settingsInput:focus {
                border: 1px solid {accent_blue};
            }
            #settingsCombo {
                background-color: {crust};
                border: 1px solid {overlay};
                border-radius: 8px;
                padding: 5px 10px;
                color: {text};
                font-size: 13px;
            }
            #settingsCombo:focus {
                border: 1px solid {accent_blue};
            }
            #settingsCombo QAbstractItemView {
                background-color: {crust};
                border: 1px solid {divider};
                border-radius: 6px;
                color: {text};
                selection-background-color: {accent_blue};
                selection-color: {base};
            }
            #settingsSpin {
                background-color: {crust};
                border: 1px solid {overlay};
                border-radius: 8px;
                padding: 5px 10px;
                color: {text};
                font-size: 13px;
            }
            #settingsSpin:focus {
                border: 1px solid {accent_blue};
            }
            #settingsSep {
                color: {divider};
            }
            #settingsFooter {
                background-color: {surface};
                border-top: 1px solid {overlay};
            }
            #settingsFooterInfo {
                color: {muted};
                font-size: 12px;
                background: transparent;
            }
        """
        for key, val in C.items():
            qss = qss.replace("{" + key + "}", val)
        self.setStyleSheet(qss)
