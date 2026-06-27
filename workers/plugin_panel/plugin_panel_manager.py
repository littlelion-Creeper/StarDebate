"""PluginPanelManager：插件管理面板 UI + 全部业务逻辑（导入/删除/开关/设置/文档/导航刷新）"""
import os
import sys
import traceback
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QSizePolicy, QStackedWidget, QSplitter, QWidget,
    QFileDialog, QInputDialog,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from components.star_button import StarButton
from components.theme_colors import tc
from components.popup_dialog import CustomDialog

# .stp 安装支持
from workers.stp_installer.stp_installer import STPInstaller
from workers.stp_installer.install_preview import STPInstallPreview


class PluginPanelManager:
    """管理插件面板 UI 和全部插件操作"""

    def __init__(self, mw):
        """
        Args:
            mw: StarDebateWindow 实例引用，需提供：
                - _plugin_manager
                - _plugin_api (已设置上下文)
                - _nav_mgr (NavBarManager)
                - _top_nav_mgr (TopNavManager)
                - _speech_writer_mgr / _ai_expand_mgr / _notes_mgr / _train_mgr
                - _plugin_left_stack / _plugin_right_stack
                - _plugin_left_panel_map / _plugin_right_panel_map
                - _plugin_active_panel
                - _plugin_panel_btns
                - _plugin_center_pages
                - _plugin_panel (QFrame，由本管理器构建后设置)
                - centre_stack (QStackedWidget)
                - _build_tree_from_path / _update_status / _load_full_config / _save_config
                - _train_mgr.refresh_sub_features_ui()
        """
        self._mw = mw
        self._pm = mw._plugin_manager

        # .stp 安装器
        self._stp_installer = STPInstaller(mw)

        # 插件列表 UI 引用
        self._plugin_list_container: QWidget | None = None
        self._plugin_list_layout: QVBoxLayout | None = None
        self._plugin_empty_hint: QLabel | None = None
        self._plugin_count_label: QLabel | None = None
        self._plugin_cards: list[QFrame] = []

    def build_panel(self) -> QFrame:
        """构建插件管理面板，返回 QFrame"""
        panel = QFrame()
        panel.setObjectName("pluginPanel")
        panel.setMinimumWidth(480)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 12, 12, 12)
        panel_layout.setSpacing(10)

        # ── 标题栏 ──
        header = QHBoxLayout()
        header.setSpacing(8)
        title_lbl = QLabel("插件管理")
        title_lbl.setObjectName("pluginPanelTitleMajor")
        title_lbl.setFont(QFont("Microsoft YaHei", 15, QFont.Bold))

        btn_close = StarButton("✕ 关闭", None, layout_mode="text_only", ratio_h=0.7)
        btn_close.setObjectName("pluginCloseBtn")
        btn_close.clicked.connect(lambda: self._mw._toggle_plugins_panel())

        header.addWidget(title_lbl)
        header.addStretch()
        header.addWidget(btn_close)
        panel_layout.addLayout(header)

        # ── 免责声明 ──
        warning_card = QFrame()
        warning_card.setObjectName("pluginWarningCard")
        warning_layout = QVBoxLayout(warning_card)
        warning_layout.setContentsMargins(12, 10, 12, 10)
        warning_layout.setSpacing(4)
        warn_title = QLabel("⚠ 免责声明")
        warn_title.setObjectName("pluginWarningTitle")
        warn_title.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        warn_text = QLabel(
            "插件由用户自行管理。插件运行在隔离环境中，无法修改主体代码。\n"
            "插件引发的崩溃或异常与软件主体无关。请确认插件来源可信。"
        )
        warn_text.setObjectName("pluginWarningBody")
        warn_text.setFont(QFont("Microsoft YaHei", 9))
        warn_text.setWordWrap(True)
        warning_layout.addWidget(warn_title)
        warning_layout.addWidget(warn_text)
        panel_layout.addWidget(warning_card)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        btn_install = StarButton("📦 安装插件", None, layout_mode="text_only", ratio_h=0.7)
        btn_install.setObjectName("pluginToolBtn")
        btn_install.setToolTip("安装 .stp 插件包或导入插件文件夹")
        btn_install.clicked.connect(self._on_install_plugin)
        btn_open_folder = StarButton("打开文件夹", None, layout_mode="text_only", ratio_h=0.7)
        btn_open_folder.setObjectName("pluginToolBtn")
        btn_open_folder.setToolTip("在文件管理器中打开插件目录")
        btn_open_folder.clicked.connect(self._pm.open_plugin_folder)
        toolbar.addWidget(btn_install)
        toolbar.addWidget(btn_open_folder)
        toolbar.addStretch()
        panel_layout.addLayout(toolbar)

        # ── 分隔线 ──
        sep = QFrame()
        sep.setObjectName("pluginPanelSeparator")
        sep.setFrameShape(QFrame.HLine)
        panel_layout.addWidget(sep)

        # ── 插件列表滚动区域 ──
        scroll = QScrollArea()
        scroll.setObjectName("pluginScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._plugin_list_container = QWidget()
        self._plugin_list_container.setObjectName("pluginListContainer")
        self._plugin_list_container.setMinimumWidth(0)
        self._plugin_list_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self._plugin_list_layout = QVBoxLayout(self._plugin_list_container)
        self._plugin_list_layout.setContentsMargins(0, 0, 0, 0)
        self._plugin_list_layout.setSpacing(8)
        self._plugin_list_layout.addStretch()

        scroll.setWidget(self._plugin_list_container)
        panel_layout.addWidget(scroll, stretch=1)

        # ── 空状态提示 ──
        self._plugin_empty_hint = QLabel("📦 暂无插件\n点击「📦 安装插件」添加")
        self._plugin_empty_hint.setObjectName("pluginPanelEmptyHint")
        self._plugin_empty_hint.setFont(QFont("Microsoft YaHei", 11))
        self._plugin_empty_hint.setAlignment(Qt.AlignCenter)
        self._plugin_empty_hint.setWordWrap(True)
        self._plugin_empty_hint.setVisible(True)
        self._plugin_list_layout.insertWidget(0, self._plugin_empty_hint)

        # ── 底部状态栏 ──
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self._plugin_count_label = QLabel("插件总数: 0")
        self._plugin_count_label.setObjectName("pluginPanelSubHint")
        self._plugin_count_label.setFont(QFont("Microsoft YaHei", 9))
        footer.addStretch()
        footer.addWidget(self._plugin_count_label)
        panel_layout.addLayout(footer)

        return panel

    # ========== 插件列表刷新 ==========

    def refresh_list(self):
        """刷新插件列表显示"""
        if self._plugin_list_layout is None:
            return
        for card in self._plugin_cards:
            self._plugin_list_layout.removeWidget(card)
            card.deleteLater()
        self._plugin_cards.clear()

        plugins = self._pm.get_all_plugins()
        if not plugins:
            if self._plugin_empty_hint:
                self._plugin_empty_hint.setVisible(True)
            self._plugin_count_label.setText("插件总数: 0")
            return

        if self._plugin_empty_hint:
            self._plugin_empty_hint.setVisible(False)

        for info in plugins:
            card = self._create_card(info)
            self._plugin_list_layout.insertWidget(self._plugin_list_layout.count() - 1, card)
            self._plugin_cards.append(card)

        self._plugin_count_label.setText(f"插件总数: {len(plugins)}")

    def _create_card(self, info) -> QFrame:
        """创建单个插件卡片"""
        card = QFrame()
        card.setObjectName("pluginCard")
        card.setMinimumWidth(0)
        main_layout = QVBoxLayout(card)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(6)

        # 第一行
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        name_lbl = QLabel(info.name)
        name_lbl.setObjectName("pluginCardName")
        name_lbl.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        name_lbl.setWordWrap(True)
        name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        name_lbl.setMinimumWidth(0)

        ver_lbl = QLabel(f"v{info.version}")
        ver_lbl.setObjectName("pluginCardDesc")
        ver_lbl.setFont(QFont("Microsoft YaHei", 9))

        top_row.addWidget(name_lbl, stretch=1)
        top_row.addWidget(ver_lbl)
        top_row.addStretch()

        btn_delete = StarButton("删除", None, layout_mode="text_only", ratio_h=0.7)
        btn_delete.setObjectName("pluginCardBtn")
        btn_delete.clicked.connect(lambda pid=info.plugin_id: self._on_delete_plugin(pid))

        toggle_initial = info.enabled
        btn_toggle = StarButton("", None, layout_mode="text_only", ratio_h=0.7,
                                accent=tc("accent_green") if toggle_initial else tc("toggle_off"),
                                auto_size=False)
        btn_toggle.setObjectName("pluginToggleBtn")
        btn_toggle.setFixedSize(48, 24)
        btn_toggle.setToolTip("开启/关闭 插件")
        btn_toggle._toggle_state = toggle_initial
        # 手动维护 toggle 状态，因 StarButton checkable 不支持双态色
        btn_toggle.clicked.connect(
            lambda pid=info.plugin_id, btn=btn_toggle:
            self._on_toggle_click(pid, btn)
        )

        top_row.addWidget(btn_delete)
        top_row.addWidget(btn_toggle)
        main_layout.addLayout(top_row)

        author_lbl = QLabel(f"作者: {info.author}")
        author_lbl.setObjectName("pluginCardVersion")
        author_lbl.setFont(QFont("Microsoft YaHei", 9))
        main_layout.addWidget(author_lbl)

        if info.description:
            desc_lbl = QLabel(info.description)
            desc_lbl.setObjectName("pluginCardAuthor")
            desc_lbl.setFont(QFont("Microsoft YaHei", 9))
            desc_lbl.setWordWrap(True)
            desc_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            desc_lbl.setMinimumWidth(0)
            main_layout.addWidget(desc_lbl)

        card._toggle_btn = btn_toggle
        card._plugin_id = info.plugin_id
        return card

    # ========== 导入插件 ==========

    def _on_install_plugin(self):
        """安装插件：支持 .stp 文件（优先）和插件文件夹（兼容旧版）"""
        file_path, _ = QFileDialog.getOpenFileName(
            self._mw, "选择插件包",
            "", "StarDebate 插件包 (*.stp);;所有文件 (*)",
        )
        if file_path:
            # 尝试作为 .stp 安装
            if self._stp_installer.is_stp_file(file_path):
                self._on_install_stp(file_path)
                return
            # 如果选中的是 .py 文件，改为选择同文件夹
            if file_path.lower().endswith(".py"):
                folder = os.path.dirname(file_path)
                self._on_import_folder(folder)
                return
            # 其他类型提示
            CustomDialog.warning(self._mw, "不支持",
                                "请选择 .stp 插件包或插件文件夹。")
            return

        # 文件对话框取消后，回退到文件夹选择（兼容旧操作流程）
        self._on_import_folder()

    def _on_import_folder(self, folder_path: str = ""):
        """导入插件文件夹（旧式兼容）"""
        if not folder_path:
            folder_path = QFileDialog.getExistingDirectory(self._mw, "选择插件文件夹")
        if not folder_path:
            return
        # 安全检查
        try:
            dangerous_patterns = ["os.remove(\"/\")", "shutil.rmtree(\"/\")",
                                  "os.system(\"format", "__import__(\"os\").system",
                                  "subprocess.call([\"rm\", \"-rf\", \"/\"]"]
            for root, dirs, files in os.walk(folder_path):
                for f in files:
                    if f.endswith(".py"):
                        fpath = os.path.join(root, f)
                        try:
                            with open(fpath, "r", encoding="utf-8") as fh:
                                content = fh.read()
                            for pattern in dangerous_patterns:
                                if pattern in content.lower():
                                    CustomDialog.warning(self._mw, "安全警告",
                                                        f"文件 {f} 包含潜在危险代码，已拒绝导入。")
                                    return
                        except Exception:
                            pass
        except Exception:
            pass

        success, msg = self._pm.import_plugin(folder_path)
        if success:
            self._mw._update_status(msg)
            self.refresh_list()
            self._refresh_nav_buttons()
        else:
            CustomDialog.warning(self._mw, "导入失败", msg)

    def _on_install_stp(self, filepath: str):
        """执行 .stp 文件安装全流程（校验 → 预览 → 安装）"""
        # 读取 manifest
        manifest = self._stp_installer.get_manifest_from_stp(filepath)
        if not manifest:
            CustomDialog.warning(self._mw, "安装失败",
                                "无法读取插件包信息，文件可能已损坏。")
            return

        # 预检查
        missing_deps = self._stp_installer.check_dependencies(manifest)
        conflict = self._stp_installer.check_conflict(manifest)
        compat_ok, compat_msg = self._stp_installer.check_version_compatibility(manifest)

        # 显示预览对话框
        preview = STPInstallPreview(
            self._mw, manifest, missing_deps,
            conflict, compat_ok, compat_msg,
        )
        if preview.exec_() != STPInstallPreview.Accepted:
            return  # 用户取消

        conflict_mode = preview.get_conflict_mode()

        # 如果用户选择 cancel（在冲突选项中），直接跳过
        if conflict_mode == "cancel":
            return

        # 执行安装
        self._mw._update_status(f"[插件] 正在安装 {manifest.get('name', '')} ...")
        result = self._stp_installer.install(filepath, conflict_mode=conflict_mode)

        if result["success"]:
            self._mw._update_status(
                f"✅ 插件 \"{manifest.get('name', '')}\" 安装完成。"
                f"请前往「插件管理」启用插件。"
            )
            self.refresh_list()
            self._refresh_nav_buttons()
            self._mw._train_mgr.refresh_sub_features_ui()
        else:
            CustomDialog.warning(self._mw, "安装失败", result.get("error", "未知错误"))

    # ========== 删除插件 ==========

    def _on_delete_plugin(self, plugin_id: str):
        """卸载插件（默认仅禁用，可选彻底删除）"""
        info = self._pm.get_plugin(plugin_id)
        if not info:
            return

        # 三按钮选择：取消 / 仅禁用 / 彻底删除
        choice = CustomDialog.question(
            self._mw, f"卸载插件「{info.name}」",
            f"版本: v{info.version} | 作者: {info.author}\n\n"
            f"○ 仅禁用（推荐）— 保留文件，日后可重新启用\n"
            f"○ 彻底删除 — 删除插件目录，不可恢复",
            buttons=[("取消", "cancel"), ("仅禁用", "disable"), ("彻底删除", "delete")],
        )
        if choice == "disable":
            self._stp_installer.uninstall(plugin_id, mode="disable")
            self._mw._update_status(f"插件已禁用: {info.name}")
            self.refresh_list()
            self._refresh_nav_buttons()
            self._mw._train_mgr.refresh_sub_features_ui()
            self._mw._remove_plugin_panels(plugin_id)
        elif choice == "delete":
            self._mw._remove_plugin_panels(plugin_id)
            self._pm.delete_plugin(plugin_id)
            self._mw._update_status(f"插件已删除: {info.name}")
            self.refresh_list()
            self._refresh_nav_buttons()
            self._mw._train_mgr.refresh_sub_features_ui()

    # ========== 开关插件 ==========

    def _on_toggle_click(self, plugin_id: str, btn: StarButton):
        """手动切换 toggle 按钮状态（StarButton 不支持双态色，手动管理 accent）。"""
        new_state = not btn._toggle_state
        btn._toggle_state = new_state
        btn._accent = tc("accent_green") if new_state else tc("toggle_off")
        btn.update()
        self._on_toggle_plugin(plugin_id, new_state)

    def _on_toggle_plugin(self, plugin_id: str, enabled: bool):
        """开关插件"""
        success = self._pm.toggle_plugin(plugin_id, enabled)
        info = self._pm.get_plugin(plugin_id)
        if info:
            state = "已启用" if enabled else "已禁用"
            self._mw._update_status(f"插件 {state}: {info.name}")
            if enabled and not success:
                CustomDialog.warning(self._mw, "插件启用失败",
                                    f"插件 \"{info.name}\" 启用失败，请检查插件代码是否正确。")
        if not enabled:
            self._mw._remove_plugin_panels(plugin_id)
        self._mw._train_mgr.refresh_sub_features_ui()
        QTimer.singleShot(0, self._refresh_nav_buttons)

    # ========== 导航按钮刷新 ==========

    def _refresh_nav_buttons(self):
        """刷新导航栏和顶部导航栏的插件按钮"""
        self._mw._nav_mgr.rebuild_plugin_buttons(self._pm)
        self._mw._top_nav_mgr.rebuild_plugin_buttons(self._pm)
        self._mw._left_nav_btns = self._mw._nav_mgr.plugin_left_btns
        self._mw._right_nav_btns = self._mw._nav_mgr.plugin_right_btns
