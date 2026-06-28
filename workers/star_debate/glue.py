"""StarDebate ★ 辩之星 — 跨模块胶水代码 Mixin
============================================================================
将 StarDebateWindow 的面板切换、事件处理、桥接方法、兼容属性抽离至此。
与 UIAssemblyMixin 通过多重继承组合。
============================================================================
"""
import sys
import os
import json
import ctypes

from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton,
    QSplitter, QStackedWidget, QDialog,
)
from PyQt5.QtCore import Qt, QTimer, QEvent
from PyQt5.QtGui import QFontMetrics
from siui.core import SiGlobal
from siui.templates.application.components.layer.layer_right_message_sidebar.layer_right_message_sidebar import (
    LayerRightMessageSidebar,
)

# ── 跨模块引用 ────────────────────────────────────────────────────────
from workers.tournament import COMPETITION_PRESETS
from workers.framework import FRAMEWORK_NODE_TYPES


class GlueCodeMixin:
    """跨模块胶水代码 — 面板切换、事件处理、桥接方法、兼容属性。

    此类包含：
      - 面板切换方法（toggle / plugin panel）
      - 操作回调（设置、新建、赛制、框架）
      - 数据展示 / 路径工具
      - 向后兼容 property
      - 工具方法
      - 桥接方法（供 managers 回调）
      - 窗口事件处理
    """

    # =====================================================================
    # 面板切换方法
    # =====================================================================

    def _toggle_project_tree(self):
        """切换项目树面板"""
        self._project_tree_visible = not self._project_tree_visible
        hsplitter = self.findChildren(QSplitter)[0]
        left_vsplit = hsplitter.widget(0)
        if left_vsplit:
            tree_panel = left_vsplit.widget(0)
            if tree_panel:
                tree_panel.setVisible(self._project_tree_visible)
        self.btn_toggle_project_tree.setChecked(self._project_tree_visible)
        self._update_status(f"项目浏览器: {'显示' if self._project_tree_visible else '隐藏'}")

    def _toggle_structure_tree(self):
        """切换结构树面板"""
        visible = self._structure_mgr.toggle_visibility()
        self.btn_toggle_structure_tree.setChecked(visible)
        self._update_status(f"一辩稿结构树: {'显示' if visible else '隐藏'}")

    def _toggle_match_schedule(self):
        """切换赛程面板"""
        visible = self._tournament_mgr.toggle_visibility()
        if self._tournament_mgr.panel:
            self._tournament_mgr.panel.setVisible(visible)
        self.btn_toggle_match_schedule.setChecked(visible)
        self._update_status(f"赛程管理: {'显示' if visible else '隐藏'}")

    def _toggle_stdb_browser(self):
        """切换 .stardebate 模块浏览面板"""
        visible = not self._stdb_browser_visible
        self._stdb_browser_visible = visible
        if hasattr(self, '_stdb_module_panel') and self._stdb_module_panel:
            self._stdb_module_panel.setVisible(visible)
            if visible:
                self._stdb_module_panel.refresh_file_list()
        self.btn_toggle_stdb_browser.setChecked(visible)
        self._update_status(f".stardebate 模块浏览: {'显示' if visible else '隐藏'}")

    def _toggle_material_pool(self):
        """切换资料池面板"""
        self._material_pool_mgr.toggle_visibility()

    def _toggle_extension_panel(self):
        """切换扩展包管理面板（centre_stack 页面）"""
        try:
            ext_mgr = getattr(self, '_ext_mgr', None)
            if ext_mgr is None:
                self._update_status("扩展包管理器未初始化")
                return
            # 确保面板已构建
            from workers.extension_manager.panel_manager import ExtensionPanelManager
            if not hasattr(self, '_ext_panel_mgr') or self._ext_panel_mgr is None:
                self._ext_panel_mgr = ExtensionPanelManager(self)
                ext_page = self._ext_panel_mgr.build_page()
                self._ext_page_idx = self.centre_stack.addWidget(ext_page)

            # 切换显示
            current_idx = self.centre_stack.currentIndex()
            if current_idx == self._ext_page_idx:
                self.centre_stack.setCurrentIndex(0)
            else:
                self._ext_panel_mgr.refresh_list()
                self.centre_stack.setCurrentIndex(self._ext_page_idx)

            self._update_status("扩展包管理面板已打开")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._update_status(f"打开扩展包管理失败: {e}")

    def _toggle_plugins_panel(self):
        """切换插件管理面板（与其他功能面板互斥）"""
        self._speech_writer_mgr.close_if_open()
        self._plugins_visible = not self._plugins_visible
        self._plugin_panel.setVisible(self._plugins_visible)
        self._nav_mgr.get_button("plugin_manager").setChecked(self._plugins_visible)

        if self._plugins_visible:
            self._ai_expand_mgr.close_if_open()
            self._notes_mgr.close_if_open()
            if self._train_mgr._visible:
                self._train_mgr._visible = False
                self._train_mgr._panel.setVisible(False)
                self._train_mgr._btn_toggle.setChecked(False)
            self._plugin_panel_mgr.refresh_list()
            self._close_all_plugin_registered_panels()
            self._update_status("插件管理面板已打开")
        else:
            self._update_status("插件管理面板已关闭")

    def _toggle_speech_writer_panel(self):
        """切换 AI 写稿面板 → 委托至 SpeechWriterManager"""
        self._speech_writer_mgr.toggle_visibility()
        if self._speech_writer_mgr.is_visible():
            self._on_speech_writer_shown()


    def _toggle_ai_expand_panel(self):
        """切换 AI 扩写面板 → 委托至 AIExpandManager"""
        self._ai_expand_mgr.toggle_visibility()
        if self._ai_expand_mgr.is_visible():
            self._on_ai_expand_shown()


    def _toggle_notes_panel(self):
        """切换便签面板 → 委托至 NotesManager"""
        self._notes_mgr.toggle_visibility()
        if self._notes_mgr.is_visible():
            self._on_notes_shown()


    def _toggle_training_panel(self):
        """切换模拟训练面板 → 委托至 TrainingManager"""
        self._train_mgr.toggle_visibility()
        if self._train_mgr.is_visible():
            self._on_training_shown()


    # =====================================================================
    # 撤销/重做 — 面板切换协调
    # =====================================================================

    def _on_center_page_changed(self, index: int):
        """centre_stack 页面切换时，通知 UndoCoordinator 切换活跃面板。

        Page 映射：
          0: 欢迎页      → None
          1: 辩论详情    → None
          2: 一辩稿编辑  → "speech_editor"
          3: AI 分析      → None（只读展示）
          4,5: 资料稿    → None（暂不支持）
          6: 模拟质询    → None（暂不支持）
          7: 模拟接质    → None（暂不支持）
          8: 辩论框架    → "framework"
          9: 立论驳论    → "exercise_editor"
        """
        mapping = {
            0: None, 1: None, 2: "speech_editor",
            3: None, 4: None, 5: None,
            6: None, 7: None, 8: "framework",
            9: "exercise_editor",
        }
        # 扩展包管理页面（动态索引，用 getattr 安全获取）
        ext_idx = getattr(self, '_ext_page_idx', -1)
        if ext_idx >= 0:
            mapping[ext_idx] = None
        panel_id = mapping.get(index, None)
        from components.undo_coordinator import UndoCoordinator
        UndoCoordinator.instance().set_active_panel(panel_id)

    def _on_speech_writer_shown(self):
        """AI 写稿面板显示时调用。"""
        from components.undo_coordinator import UndoCoordinator
        UndoCoordinator.instance().set_active_panel("speech_writer")

    def _on_ai_expand_shown(self):
        """AI 扩写面板显示时调用。"""
        from components.undo_coordinator import UndoCoordinator
        UndoCoordinator.instance().set_active_panel("ai_expand")

    def _on_notes_shown(self):
        """便签面板显示时调用。"""
        from components.undo_coordinator import UndoCoordinator
        UndoCoordinator.instance().set_active_panel("notes")

    def _on_training_shown(self):
        """模拟训练面板显示时调用。"""
        from components.undo_coordinator import UndoCoordinator
        UndoCoordinator.instance().set_active_panel("training")

    def _on_material_pool_shown(self):
        """资料池面板显示时调用。"""
        from components.undo_coordinator import UndoCoordinator
        UndoCoordinator.instance().set_active_panel("material_pool")


    # =====================================================================
    # 插件注册面板切换
    # =====================================================================

    def _toggle_plugin_registered_panel(self, plugin_id: str, side: str):
        """切换插件注册面板的显示/隐藏"""
        if side == "left":
            self._toggle_plugin_panel_in_stack(plugin_id, side, self._plugin_left_stack,
                                               self._plugin_left_panel_map, "left")
        elif side == "right":
            self._toggle_plugin_panel_in_stack(plugin_id, side, self._plugin_right_stack,
                                               self._plugin_right_panel_map, "right")
        elif side == "center":
            self._toggle_plugin_center_panel(plugin_id)

    def _toggle_plugin_panel_in_stack(self, plugin_id: str, side: str,
                                       stack: QStackedWidget, panel_map: dict, side_key: str):
        """在左侧或右侧 QStackedWidget 中切换插件面板"""
        current_active = self._plugin_active_panel.get(side_key)
        target_idx = panel_map.get(plugin_id)

        if target_idx is None:
            panels = self._plugin_manager.get_enabled_panels(side)
            panel_info = next((p for p in panels if p["plugin_id"] == plugin_id), None)
            if not panel_info or not panel_info.get("create_widget"):
                return
            try:
                widget = panel_info["create_widget"]()
            except Exception:
                import traceback
                traceback.print_exc()
                return
            _min_w = panel_info.get("min_width", 280)
            _max_w = panel_info.get("max_width")  # None = 无上限
            widget.setMinimumWidth(_min_w)
            if _max_w is not None:
                widget.setMaximumWidth(_max_w)
            target_idx = stack.addWidget(widget)
            panel_map[plugin_id] = target_idx
            for p in panels:
                if p["plugin_id"] == plugin_id:
                    p["widget"] = widget
                    break

        if current_active == plugin_id:
            self._close_plugin_panel(side_key, stack, panel_map)
            return

        if current_active:
            self._close_plugin_panel(side_key, stack, panel_map)

        if side_key == "right":
            self._close_existing_function_panels()

        self._plugin_active_panel[side_key] = plugin_id
        stack.setCurrentIndex(target_idx)
        if not stack.isVisible():
            stack.setVisible(True)
            hsplitter = self.findChildren(QSplitter)[0]
            if hsplitter:
                sizes = list(hsplitter.sizes())
                total_w = hsplitter.width()
                handle_w = hsplitter.handleWidth()

                # 修复：将 size=0 的隐藏面板恢复为其 minimumWidth，
                # 防止 setSizes 把 0 值写回 splitter 导致宽度被永久冻结
                for i, w in enumerate(sizes):
                    if w == 0:
                        widget = hsplitter.widget(i)
                        if widget:
                            sizes[i] = max(widget.minimumWidth(), 1)

                # 从面板配置读取宽度参数
                _panels = self._plugin_manager.get_enabled_panels(side)
                _pi = next((p for p in _panels if p["plugin_id"] == plugin_id), {})
                _min_w = _pi.get("min_width", 280)
                _max_w = _pi.get("max_width")  # None = 无上限
                _ratio = _pi.get("width_ratio")  # None = 不限比例

                # 按比例计算目标面板宽度（None 比例时跳过比例计算）
                num_handles = len(sizes) - 1
                if side_key == "left":
                    target_size = int(sum(sizes) * _ratio) if _ratio is not None else sum(sizes) - handle_w * num_handles
                    sizes[2] = max(_min_w, min(_max_w, target_size)) if _max_w is not None else max(_min_w, target_size)
                else:
                    target_size = int(sum(sizes) * _ratio) if _ratio is not None else sum(sizes) - handle_w * num_handles
                    sizes[9] = max(_min_w, min(_max_w, target_size)) if _max_w is not None else max(_min_w, target_size)

                hsplitter.setSizes(sizes)

                # 隐藏面板通过 stretchFactor=0 让 QSplitter 自动折叠，
                # 不依赖显式写入 0 宽度
                for i in (4, 5, 6, 7, 8):
                    w = hsplitter.widget(i)
                    if w and not w.isVisible():
                        hsplitter.setStretchFactor(i, 0)
                    elif w:
                        hsplitter.setStretchFactor(i, 1)

    def _toggle_plugin_center_panel(self, plugin_id: str):
        """切换中心区域插件面板"""
        existing = next((p for p in self._plugin_center_pages if p["plugin_id"] == plugin_id), None)
        current_idx = self.centre_stack.currentIndex()
        if existing:
            target_idx = existing["page_index"]
            if current_idx == target_idx:
                self.centre_stack.setCurrentIndex(0)
                return
            self.centre_stack.setCurrentIndex(target_idx)
        else:
            panels = self._plugin_manager.get_enabled_panels("center")
            panel_info = next((p for p in panels if p["plugin_id"] == plugin_id), None)
            if not panel_info or not panel_info.get("create_widget"):
                return
            try:
                widget = panel_info["create_widget"]()
            except Exception:
                import traceback
                traceback.print_exc()
                return
            page_idx = self.centre_stack.addWidget(widget)
            self._plugin_center_pages.append({
                "plugin_id": plugin_id, "page_index": page_idx, "widget": widget,
            })
            self.centre_stack.setCurrentIndex(page_idx)
            self._close_existing_function_panels()
            self._close_all_plugin_registered_panels()

    def _close_plugin_panel(self, side_key: str, stack: QStackedWidget, panel_map: dict):
        """关闭指定侧的插件面板"""
        stack.setCurrentIndex(0)
        stack.setVisible(False)
        active_pid = self._plugin_active_panel.get(side_key)
        if active_pid:
            btn_key = f"{active_pid}_{side_key}"
            if btn_key in self._plugin_panel_btns:
                self._plugin_panel_btns[btn_key].setChecked(False)
        self._plugin_active_panel[side_key] = None
        hsplitter = self.findChildren(QSplitter)[0]
        if side_key == "left":
            hsplitter.setStretchFactor(2, 0)
        else:
            hsplitter.setStretchFactor(9, 0)

    def _close_all_plugin_registered_panels(self):
        """关闭所有插件注册面板"""
        if hasattr(self, '_plugin_left_stack') and self._plugin_left_stack:
            self._close_plugin_panel("left", self._plugin_left_stack, self._plugin_left_panel_map)
        if hasattr(self, '_plugin_right_stack') and self._plugin_right_stack:
            self._close_plugin_panel("right", self._plugin_right_stack, self._plugin_right_panel_map)

    def _close_existing_function_panels(self):
        """关闭所有右侧功能面板"""
        self._speech_writer_mgr.close_if_open()
        self._ai_expand_mgr.close_if_open()
        self._notes_mgr.close_if_open()
        if self._train_mgr._visible:
            self._train_mgr._visible = False
            self._train_mgr._panel.setVisible(False)
            self._train_mgr._btn_toggle.setChecked(False)
        if self._plugins_visible:
            self._plugins_visible = False
            self._plugin_panel.setVisible(False)
            self._nav_mgr.get_button("plugin_manager").setChecked(False)

    def _remove_plugin_panels(self, plugin_id: str):
        """移除指定插件的所有注册面板"""
        # 左侧
        if hasattr(self, '_plugin_left_panel_map') and plugin_id in self._plugin_left_panel_map:
            idx = self._plugin_left_panel_map.pop(plugin_id)
            if self._plugin_active_panel.get("left") == plugin_id:
                self._close_plugin_panel("left", self._plugin_left_stack, self._plugin_left_panel_map)
            widget = self._plugin_left_stack.widget(idx)
            if widget:
                self._plugin_left_stack.removeWidget(widget)
                widget.deleteLater()
        # 右侧
        if hasattr(self, '_plugin_right_panel_map') and plugin_id in self._plugin_right_panel_map:
            idx = self._plugin_right_panel_map.pop(plugin_id)
            if self._plugin_active_panel.get("right") == plugin_id:
                self._close_plugin_panel("right", self._plugin_right_stack, self._plugin_right_panel_map)
            widget = self._plugin_right_stack.widget(idx)
            if widget:
                self._plugin_right_stack.removeWidget(widget)
                widget.deleteLater()
        # 中心
        for p in self._plugin_center_pages[:]:
            if p["plugin_id"] == plugin_id:
                if self.centre_stack.currentIndex() == p["page_index"]:
                    self.centre_stack.setCurrentIndex(0)
                widget = p["widget"]
                self.centre_stack.removeWidget(widget)
                widget.deleteLater()
                self._plugin_center_pages.remove(p)
        # 面板按钮引用
        keys_to_remove = [k for k in self._plugin_panel_btns if k.startswith(f"{plugin_id}_")]
        for k in keys_to_remove:
            del self._plugin_panel_btns[k]

    # =====================================================================
    # 操作回调（设置、新建、赛制指定、框架）
    # =====================================================================

    def _on_create_project(self):
        """创建项目 → 委托至 ProjectExplorerManager"""
        self._project_explorer.create_project()

    def _on_open_project(self):
        """打开项目 → 委托至 ProjectExplorerManager"""
        self._project_explorer.open_project_dialog()

    def _on_exit_app(self):
        """退出应用 → 触发关闭流程（closeEvent → cleanup → GlueCodeMixin）"""
        self.close()

    def _on_view_menu_clicked(self):
        """视图菜单 → 弹出 SiUI 右侧侧边栏提示正在开发中"""
        from PyQt5.QtGui import QColor
        from PyQt5.QtWidgets import QGraphicsColorizeEffect
        self._ensure_right_message_sidebar()
        sidebar = self._layer_right_message_sidebar
        sidebar.show()
        sidebar.raise_()
        sidebar.send(
            "视图切换功能正在开发中，敬请期待 🚀",
            title="视图功能",
            msg_type=2,
            fold_after=4000,
        )
        # 修复消息卡片图标：透明背景 + 统一白色
        for w in sidebar.widgets():
            try:
                icon = w.content().themeIcon()
                icon.setStyleSheet("background: transparent;")
                effect = QGraphicsColorizeEffect(icon)
                effect.setColor(QColor(Qt.white))
                icon.setGraphicsEffect(effect)
            except Exception:
                pass

    def _ensure_right_message_sidebar(self):
        """按需创建 SiUI 右侧消息侧边栏，首次调用时初始化一次。"""
        if hasattr(self, '_layer_right_message_sidebar') and self._layer_right_message_sidebar is not None:
            return
        # 注册主窗口到 SiGlobal
        SiGlobal.siui.windows["MAIN_WINDOW"] = self
        # 以 ShadowContainer 的内容区为父（跳过阴影 margin），浮动于内容之上
        parent = self._shadow_container.get_content()
        sidebar = LayerRightMessageSidebar(parent)
        sidebar.setObjectName("rightMessageSidebar")
        # 透明背景（用 QSS 而非 WA_TranslucentBackground，避免阴影渲染不稳）
        sidebar.setStyleSheet("#rightMessageSidebar { background: transparent; }")
        # 隐藏 debug_label（默认填充白色矩形遮挡内容）
        sidebar.debug_label.hide()
        sidebar.lower()  # 初始置于底层，发送消息时 raise_
        self._layer_right_message_sidebar = sidebar
        # 初始定位（稍后在 resizeEvent 中持续更新）
        self._update_sidebar_geometry()

    def _update_sidebar_geometry(self):
        """更新右侧消息侧边栏的位置和尺寸。"""
        if not hasattr(self, '_layer_right_message_sidebar') or self._layer_right_message_sidebar is None:
            return
        parent = self._layer_right_message_sidebar.parent()
        if parent is None:
            return
        pw = parent.width()
        ph = parent.height()
        # 贴右边缘，距顶部 80px
        self._layer_right_message_sidebar.setMaximumHeight(ph)
        self._layer_right_message_sidebar.setGeometry(pw - 400, 80, 400, ph - 80)

    def _on_open_settings(self):
        """打开设置对话框"""
        current_version = self._app_cfg.load_full_config().get("version", "1.2.0")
        from workers.settings import SettingsDialog
        dialog = SettingsDialog(
            self, current_version,
            theme_change_callback=self._app_cfg.switch_theme,
        )
        dialog.saved.connect(self._app_cfg.refresh_version_display)
        if dialog.exec_() == QDialog.Accepted:
            new_version = dialog.get_version_from_about()
            if new_version and new_version != current_version:
                self._app_cfg.save_config(version=new_version)
                self._app_cfg.refresh_version_display()
            self._update_status("设置已保存")

    def _on_open_welcome_guide(self):
        """打开介绍与引导页（帮助菜单「快速上手」入口）。

        监视钩子：功能与插件加载与卸载（welcome_guide_mgr 存在性检测）。
        """
        try:
            mgr = getattr(self, '_welcome_guide_mgr', None)
            if mgr is None:
                log = getattr(self, '_log_client', None)
                if log:
                    log.warn("[WELCOME] _welcome_guide_mgr 为 None，无法打开引导页")
                self._update_status("引导页未初始化")
                return
            if not hasattr(mgr, '_panel') or mgr._panel is None:
                log = getattr(self, '_log_client', None)
                if log:
                    log.warn("[WELCOME] 引导面板为 None，无法打开")
                self._update_status("引导面板未就绪")
                return
            mgr.show_manual()
            self._update_status("已打开快速上手引导")
        except Exception as e:
            log = getattr(self, '_log_client', None)
            if log:
                log.error(f"[WELCOME] 打开引导页异常: {e}")
            import traceback
            traceback.print_exc()

    def _on_open_changelog(self):
        """打开更新日志（帮助菜单「更新日志」入口，纯日志模式，不保存版本号）。

        监视钩子：功能与插件加载与卸载（welcome_guide_mgr 存在性检测）。
        """
        try:
            mgr = getattr(self, '_welcome_guide_mgr', None)
            if mgr is None:
                log = getattr(self, '_log_client', None)
                if log:
                    log.warn("[WELCOME] _welcome_guide_mgr 为 None，无法打开更新日志")
                self._update_status("引导页未初始化")
                return
            if not hasattr(mgr, '_panel') or mgr._panel is None:
                log = getattr(self, '_log_client', None)
                if log:
                    log.warn("[WELCOME] 引导面板为 None，无法打开更新日志")
                self._update_status("引导面板未就绪")
                return
            mgr.show_changelog()
            self._update_status("已打开更新日志")
        except Exception as e:
            log = getattr(self, '_log_client', None)
            if log:
                log.error(f"[WELCOME] 打开更新日志异常: {e}")
            import traceback
            traceback.print_exc()

    def _on_open_debug_console(self):
        """打开调试台窗口（含开发者模式防御检查）"""
        disabled = getattr(self, "_disabled_features", [])
        if "debug_console" in disabled:
            return
        from workers.debug_console import DebugConsoleWindow
        self._debug_console_win = DebugConsoleWindow(self)
        self._debug_console_win.show()
        self._update_status("调试台已打开")

    def _on_new_debate(self):
        """打开新建辩论窗口"""
        project_path = self._project_explorer.get_current_project_path()
        if not project_path:
            from components.popup_dialog import CustomDialog
            CustomDialog.warning(self, "提示", "请先打开或创建一个项目")
            return
        from workers.new_debate import NewDebateWindow
        self.new_debate_win = NewDebateWindow(self, project_path,
                                               self._tournament_mgr.competition_formats,
                                               COMPETITION_PRESETS)
        self.new_debate_win.show()
        self._update_status("新建辩论窗口已打开")

    def _on_assign_format_from_detail(self):
        """从详情页打开赛制面板并切换到指定赛制页"""
        if not self.current_debate_path:
            from components.popup_dialog import CustomDialog
            CustomDialog.warning(self, "提示", "请先在左侧项目树中打开一个辩论文件。")
            return
        self._tournament_mgr.set_visible(True)
        self._tournament_mgr.switch_to_assign_page()

    def _on_framework(self):
        """打开框架页面 → 委托至 FrameworkManager"""
        self._framework_mgr.open_framework()

    # =====================================================================
    # 数据展示 / 路径工具
    # =====================================================================

    def _display_debate(self, file_path: str, data: dict):
        """在主界面展示辩论详情"""
        self.lbl_debate_file.setText(f"📄 {file_path}")
        self.lbl_pro.setText(data.get("pro", "—"))
        self.lbl_pro_args.setText(data.get("pro_args", "—"))
        self.lbl_con.setText(data.get("con", "—"))
        self.lbl_con_args.setText(data.get("con_args", "—"))

        format_data = data.get("format")
        if format_data and isinstance(format_data, dict):
            fmt_name = format_data.get("name", "未知赛制")
            team_size = format_data.get("team_size", 0)
            pos_count = len(format_data.get("positions", []))
            self.lbl_format_info.setText(f"🏆 赛制: {fmt_name}（{pos_count}辩位，{team_size}人/方）")
            self.lbl_format_info.setVisible(True)
        else:
            self.lbl_format_info.setVisible(False)

        self.centre_stack.setCurrentIndex(1)

        if hasattr(self, '_tournament_mgr') and self._tournament_mgr:
            self._tournament_mgr.refresh_assign_section()

    def _derive_debate_path(self, speech_file: str, suffix: str):
        """从一辩稿文件路径推导对应的辩论文件路径并缓存"""
        dir_name = os.path.dirname(speech_file)
        speech_fname = os.path.basename(speech_file)
        debate_fname = speech_fname.replace(f"{suffix}.json", ".json")
        candidate = os.path.join(dir_name, debate_fname)
        if os.path.isfile(candidate):
            self.current_debate_path = candidate
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    self.current_debate_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.current_debate_data = None

    def _format_framework_for_ai(self) -> str:
        """将框架节点数据格式化为 AI 可读的文本"""
        if not self._framework_mgr.data:
            return "（无框架内容）"
        groups = {}
        for nd in self._framework_mgr.data:
            ntype = nd.get("node_type", "unknown")
            text = nd.get("text", "").strip()
            if not text:
                continue
            type_label = FRAMEWORK_NODE_TYPES.get(ntype, ("节点", "#888"))[0]
            if type_label not in groups:
                groups[type_label] = []
            groups[type_label].append(text)
        lines = []
        order = ["🧭 立场", "📖 定义", "⚖️ 判准", "💡 论点", "📊 论据", "💎 价值"]
        for label in order:
            if label in groups:
                lines.append("## {}".format(label))
                for i, text in enumerate(groups[label], 1):
                    lines.append("{}. {}".format(i, text))
                lines.append("")
        return "\n".join(lines) if lines else "（无框架内容）"

    # =====================================================================
    # 向后兼容属性 / 委托方法
    # =====================================================================

    @property
    def _speech_writer_visible(self) -> bool:
        return self._speech_writer_mgr.visible

    @_speech_writer_visible.setter
    def _speech_writer_visible(self, value: bool):
        self._speech_writer_mgr._visible = value

    @property
    def _speech_writer_cards_scroll(self):
        return self._speech_writer_mgr.cards_scroll

    @property
    def _speech_writer_cards(self) -> list:
        return self._speech_writer_mgr.cards

    @property
    def _ai_expand_visible(self) -> bool:
        return self._ai_expand_mgr.visible

    @_ai_expand_visible.setter
    def _ai_expand_visible(self, value: bool):
        self._ai_expand_mgr.visible = value

    @property
    def _ai_expand_cards(self) -> list:
        return self._ai_expand_mgr.cards

    @property
    def _notes_visible(self) -> bool:
        return self._notes_mgr.visible

    @_notes_visible.setter
    def _notes_visible(self, value: bool):
        self._notes_mgr._visible = value

    @property
    def _training_visible(self):
        return self._train_mgr._visible

    @_training_visible.setter
    def _training_visible(self, value):
        self._train_mgr._visible = value

    # =====================================================================
    # 工具方法
    # =====================================================================

    def _auto_size_button(self, btn: QPushButton, text: str, height: int,
                          padding_h: int = 24, min_width: int = 40):
        """根据文字实际宽度自动设置按钮最小宽度"""
        fm = QFontMetrics(btn.font())
        text_width = fm.horizontalAdvance(text)
        btn.setFixedHeight(height)
        btn.setMinimumWidth(max(min_width, text_width + padding_h))

    def _set_nav_disabled_state(self, disabled: bool):
        """设置全部导航按钮的禁用状态"""
        self._nav_mgr.set_all_disabled(disabled)
        self._top_nav_mgr.set_all_disabled(disabled)

    def _set_left_panel_disabled(self, disabled: bool):
        """设置左侧面板的禁用状态"""
        self._tree_panel.setEnabled(not disabled)
        self._structure_mgr.set_panel_disabled(disabled)
        if disabled:
            self._tree_panel.setStyleSheet(
                "#treePanel { background-color: #1a1a28; }"
                "QTreeWidget { background-color: #181825; color: #585b70; }"
            )
        else:
            self._tree_panel.setStyleSheet("")
            self.style().unpolish(self._tree_panel)
            self.style().polish(self._tree_panel)
            hsplitter = self.findChild(QSplitter)
            if hsplitter:
                left_vsplit = hsplitter.widget(0)
                if left_vsplit:
                    left_vsplit.setVisible(True)

    def _on_speech_writer_generate(self, side: str):
        """触发 AI 写稿 → 委托"""
        self._speech_writer_mgr.generate(side)

    def _on_ai_expand_request(self, edit, side: str, selected_text: str):
        """AI扩写请求入口 → 委托"""
        self._ai_expand_mgr.request_expand(edit, side, selected_text)

    def _on_accept_examination(self):
        """已模块化 → 委托"""
        self._accept_mgr.open_page()

    def _on_ai_framework(self):
        """触发 AI 框架生成 → 委托"""
        self._framework_mgr.start_ai_framework()

    def _on_export_stardebate(self):
        """导出 .stardebate 文件"""
        if not self.current_debate_data:
            from components.popup_dialog import CustomDialog
            CustomDialog.warning(self, "提示", "请先在项目树中打开一个辩论文件。")
            return
        from workers.stardebate_format import StardebateExportDialog
        self._stardebate_export_win = StardebateExportDialog(self)
        self._stardebate_export_win.show()
        self._update_status(".stardebate 导出窗口已打开")

    def _on_import_stardebate(self):
        """导入 .stardebate 文件 → 使用编辑器管理器打开"""
        from PyQt5.QtWidgets import QFileDialog, QInputDialog, QLineEdit
        from components.popup_dialog import CustomDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 .stardebate 文件", "",
            "StarDebate 文件 (*.stardebate);;所有文件 (*.*)"
        )
        if not file_path:
            return

        if not hasattr(self, '_stdb_editor_mgr') or not self._stdb_editor_mgr:
            CustomDialog.error(self, "错误", "编辑器管理器未初始化。")
            return

        # 尝试无密码打开
        result = self._stdb_editor_mgr.open_file(file_path)

        if not result["success"] and result["error"] == "PASSWORD_REQUIRED":
            # 需要密码
            for attempt in range(5):
                password, ok = QInputDialog.getText(
                    self, "文件已加密",
                    f"此 .stardebate 文件受密码保护。\n请输入密码 (剩余 {5 - attempt} 次):",
                    QLineEdit.Password
                )
                if not ok:
                    self._update_status("已取消 .stardebate 导入")
                    return

                result = self._stdb_editor_mgr.open_file(file_path, password=password)
                if result["success"]:
                    break
                else:
                    CustomDialog.warning(self, "密码错误",
                        f"密码不正确。\n剩余尝试次数: {4 - attempt}")
            else:
                CustomDialog.error(self, "导入失败", "密码尝试次数已用完。")
                return

        if result["success"]:
            # 打开模块浏览面板
            if not self._stdb_browser_visible:
                self._toggle_stdb_browser()
            if hasattr(self, '_stdb_module_panel') and self._stdb_module_panel:
                self._stdb_module_panel.show_file(file_path)
            self._update_status(f"已导入 .stardebate: {os.path.basename(file_path)}")
        else:
            CustomDialog.error(self, "导入失败", result.get("error", "未知错误"))

    def _on_edit_stardebate(self):
        """编辑 .stardebate 文件 — 直接打开文件进行编辑（文件菜单入口）"""
        from PyQt5.QtWidgets import QFileDialog, QInputDialog, QLineEdit
        from components.popup_dialog import CustomDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 .stardebate 文件", "",
            "StarDebate 文件 (*.stardebate);;所有文件 (*.*)"
        )
        if not file_path:
            return

        if not hasattr(self, '_stdb_editor_mgr') or not self._stdb_editor_mgr:
            CustomDialog.error(self, "错误", "编辑器管理器未初始化。")
            return

        # 如果文件已在内存中，直接显示
        if file_path in self._stdb_editor_mgr.open_files:
            self._stdb_editor_mgr._active_file = file_path
            if not self._stdb_browser_visible:
                self._toggle_stdb_browser()
            if hasattr(self, '_stdb_module_panel') and self._stdb_module_panel:
                self._stdb_module_panel.show_file(file_path)
            self._update_status(f"已选择: {os.path.basename(file_path)}")
            return

        # 尝试无密码打开
        result = self._stdb_editor_mgr.open_file(file_path)

        if not result["success"] and result["error"] == "PASSWORD_REQUIRED":
            for attempt in range(5):
                password, ok = QInputDialog.getText(
                    self, "文件已加密",
                    f"此 .stardebate 文件受密码保护。\n请输入密码 (剩余 {5 - attempt} 次):",
                    QLineEdit.Password
                )
                if not ok:
                    return
                result = self._stdb_editor_mgr.open_file(file_path, password=password)
                if result["success"]:
                    break
            else:
                CustomDialog.error(self, "打开失败", "密码尝试次数已用完。")
                return

        if result["success"]:
            if not self._stdb_browser_visible:
                self._toggle_stdb_browser()
            if hasattr(self, '_stdb_module_panel') and self._stdb_module_panel:
                self._stdb_module_panel.show_file(file_path)
            self._update_status(f"已打开 .stardebate: {os.path.basename(file_path)}")
        else:
            CustomDialog.error(self, "打开失败", result.get("error", "未知错误"))

    def _update_status(self, msg: str):
        """更新状态栏消息"""
        if hasattr(self, 'status_label') and self.status_label is not None:
            self.status_label.setText(msg)

    def _update_exercise_word_count_from_editor(self):
        """已废弃"""
        pass

    # =====================================================================
    # 桥接：自建树/配置方法（供 managers 回调）
    # =====================================================================

    def _get_current_project_path(self):
        """供外部 manager 回调，获取当前项目路径"""
        return self._project_explorer.get_current_project_path()

    def _build_tree_from_path(self, root_path: str):
        """供外部 manager 回调，重建项目树"""
        self._project_explorer.build_tree_from_path(root_path)

    def _save_config(self, project_path: str = None, **kwargs):
        """供外部 manager 回调，保存配置"""
        self._app_cfg.save_config(project_path, **kwargs)

    def _load_api_config(self) -> dict:
        """供外部 manager（如 framework_manager）回调，读取 API 配置"""
        return self._app_cfg.load_api_config()

    def _save_api_config(self, config: dict):
        """供外部 manager 回调，保存 API 配置"""
        self._app_cfg.save_api_config(config)

    def _load_full_config(self) -> dict:
        """供外部 manager 回调，读取完整配置"""
        return self._app_cfg.load_full_config()

    # =====================================================================
    # 事件处理
    # =====================================================================

    def eventFilter(self, obj, event):
        """事件过滤器：监听各面板卡片区域尺寸变化"""
        if event.type() == QEvent.KeyPress:
            if self._tournament_mgr.handle_key_press(obj, event.key()):
                return True
        if event.type() == QEvent.Resize:
            if obj is self._ref_doc_mgr.ref_cards_scroll:
                if self.centre_stack.currentIndex() == 5 and self._ref_doc_mgr.ref_cards:
                    mgr = self._ref_doc_mgr
                    if mgr._refcards_reflow_timer is None:
                        mgr._refcards_reflow_timer = QTimer(mgr._mw)
                        mgr._refcards_reflow_timer.setSingleShot(True)
                        mgr._refcards_reflow_timer.timeout.connect(mgr._arrange_cards_in_grid)
                    mgr._refcards_reflow_timer.start(80)
            elif self._cross_mgr.cards_scroll is not None and obj is self._cross_mgr.cards_scroll:
                self._cross_mgr.handle_event_filter(obj, event)
            elif obj is self._speech_writer_cards_scroll:
                self._speech_writer_mgr.handle_scroll_resize()
            elif obj is self._ai_expand_cards_scroll:
                self._ai_expand_mgr.handle_scroll_resize()
            elif obj is self._notes_mgr.cards_scroll:
                self._notes_mgr.handle_scroll_resize()
        if self._notes_mgr.handle_event_filter(obj, event):
            return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_sidebar_geometry()

    def changeEvent(self, event):
        """窗口状态变化时刷新标题栏最大化按钮 + 切换阴影/圆角"""
        if event.type() == QEvent.WindowStateChange:
            if hasattr(self, '_title_bar') and self._title_bar is not None:
                self._title_bar.update_max_btn()
            if hasattr(self, '_shadow_container'):
                self._shadow_container.set_maximized(self.isMaximized())
        super().changeEvent(event)

    def closeEvent(self, event):
        """窗口关闭时保存 .stardebate 文件 + 插件状态 + 扩展包状态 + 写出关闭日志 + 通知崩溃监控进程退出 + 恢复 stderr"""
        # ── 保存扩展包状态 ──────────────────────────────────────
        try:
            if hasattr(self, '_ext_mgr') and self._ext_mgr:
                from workers.extension_manager import get_manager
                ext_mgr = get_manager()
                if ext_mgr:
                    ext_mgr.shutdown()
        except Exception:
            pass

        # ── 自动保存所有打开的 .stardebate 文件（无条件保存，避免编辑丢失）──
        try:
            if hasattr(self, '_stdb_editor_mgr') and self._stdb_editor_mgr:
                open_count = len(self._stdb_editor_mgr.open_files)
                if open_count > 0:
                    self._stdb_editor_mgr.save_all()
        except Exception:
            pass

        try:
            self._plugin_manager.shutdown()
        except Exception:
            pass
        # 后台日志：记录关闭
        try:
            if hasattr(self, '_bg_log_mgr') and self._bg_log_mgr is not None:
                self._bg_log_mgr.info("═══ StarDebate 关闭 ═══")
        except Exception:
            pass
        # 恢复原始 stderr
        try:
            if hasattr(self, '_stderr_redirector') and self._stderr_redirector is not None:
                self._stderr_redirector.uninstall()
        except Exception:
            pass
        # 通知崩溃监控进程正常退出
        try:
            if hasattr(self, '_crash_monitor_event') and self._crash_monitor_event is not None:
                self._crash_monitor_event.set()
            if hasattr(self, '_crash_monitor_process') and self._crash_monitor_process is not None:
                self._crash_monitor_process.join(timeout=3)
                if self._crash_monitor_process.is_alive():
                    self._crash_monitor_process.terminate()
        except Exception:
            pass
        super().closeEvent(event)

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
                    return True, 13   # HTTOPLEFT
                if top and right:
                    return True, 14   # HTTOPRIGHT
                if bottom and left:
                    return True, 16   # HTBOTTOMLEFT
                if bottom and right:
                    return True, 17   # HTBOTTOMRIGHT
                if left:
                    return True, 10   # HTLEFT
                if right:
                    return True, 11   # HTRIGHT
                if top:
                    return True, 12   # HTTOP
                if bottom:
                    return True, 15   # HTBOTTOM
            return False, 0
        except Exception:
            return False, 0
