"""WelcomeGuideManager — 介绍与引导页管理器

职责：
  1. 版本比对：判断是首次运行还是版本更新
  2. 构建引导面板（WelcomeGuideStepPanel）并注入 centre_stack
  3. 持久化 last_viewed_intro_version 到 config.json
  4. 帮助菜单「快速上手」按钮 -> 重新显示引导页

监视钩子类别：功能与插件加载与卸载、全局变量值改变、数据在不同模块间的传递
"""

import os
import json
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QWidget

from components.res_path import get_resource_root, get_resource_path


class WelcomeGuideManager(QObject):
    """引导页管理器 — 生命周期管理 + 版本比对 + 触发显示。"""

    # 监视钩子：引导完成/关闭事件
    guide_closed = pyqtSignal()
    guide_completed = pyqtSignal(str)  # 参数：触发模式 "first_run" / "update" / "manual"

    GUIDE_SVG_DIR = os.path.join(get_resource_root(), "icon", "welcome_guide")
    CHANGELOG_PATH = get_resource_path("config/changelog.html")

    def __init__(self, mw, app_cfg):
        super().__init__(mw)
        self._mw = mw
        self._app_cfg = app_cfg
        self._panel = None
        self._centre_stack = None

        # 日志客户端引用（监视钩子：功能监控）
        self._log = getattr(mw, '_log_client', None)
        if self._log:
            self._log.info("[WELCOME] WelcomeGuideManager 初始化")

        # 当前版本
        self._current_version = self._app_cfg.get_app_version()
        # 上次查看引导的版本
        self._last_viewed_version = self._load_last_viewed_version()

        if self._log:
            self._log.info(f"[WELCOME] 当前版本: {self._current_version}, "
                           f"上次查看引导版本: '{self._last_viewed_version}'")

    # ── 公开 API ────────────────────────────────────────────────

    def inject_into_centre_stack(self, centre_stack):
        """构建引导面板并插入 centre_stack（末尾）。"""
        self._centre_stack = centre_stack
        self._panel = self._build_panel()
        self._panel_index = centre_stack.addWidget(self._panel)
        if self._log:
            self._log.info(f"[WELCOME] 引导面板已注入 centre_stack (索引 {self._panel_index})")

    def check_and_show(self):
        """启动时检查：首次运行或版本更新时自动显示引导页。
        
        监视钩子：全局变量值改变（last_viewed_version → current_version 比对结果）。
        """
        mode = self._detect_mode()
        if self._log:
            self._log.info(f"[WELCOME] 启动检测结果: mode={mode}, "
                           f"last={self._last_viewed_version}, current={self._current_version}")
        if mode is None:
            return False
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(200, lambda: self._show_guide(mode))
        return True

    def show_manual(self):
        """用户从帮助菜单「快速上手」主动打开引导页。
        
        监视钩子：手动触发事件追踪。
        """
        if self._log:
            self._log.info("[WELCOME] 手动触发：用户从帮助菜单打开引导页")
            self._log.info(f"[WELCOME] 状态: panel={self._panel is not None}, "
                           f"centre_stack={self._centre_stack is not None}")
        self._show_guide("manual")

    def show_changelog(self):
        """用户从帮助菜单「更新日志」单独打开更新日志面板。
        
        监视钩子：功能与插件加载与卸载（面板存在性检测）。
        """
        if self._panel is None or self._centre_stack is None:
            if self._log:
                self._log.warn("[WELCOME] 面板未就绪，无法显示更新日志")
            return
        if self._log:
            self._log.info("[WELCOME] 打开更新日志（纯日志模式）")
        self._panel.show_changelog_only()
        self._centre_stack.setCurrentWidget(self._panel)

    # ── 内部方法（监视钩子：每 def 函数执行追踪）───────────────

    def _detect_mode(self):
        """检测引导触发模式。"""
        if not self._last_viewed_version:
            return "first_run"
        try:
            if self._compare_versions(self._last_viewed_version, self._current_version) < 0:
                return "update"
        except ValueError:
            return "first_run"
        return None

    def _show_guide(self, mode: str):
        """显示引导面板并切换到它。"""
        if self._panel is None:
            if self._log:
                self._log.warn("[WELCOME] 引导面板为 None，无法显示")
            return
        if self._centre_stack is None:
            if self._log:
                self._log.warn("[WELCOME] centre_stack 为 None，无法显示")
            return
        if self._log:
            self._log.info(f"[WELCOME] 显示引导页, mode={mode}")
        self._panel.set_mode(mode)
        self._centre_stack.setCurrentWidget(self._panel)

    def _on_guide_finished(self):
        """引导完成或跳过后调用。"""
        if self._log:
            self._log.info(f"[WELCOME] 引导结束，持久化版本 {self._current_version}")
        self._save_last_viewed_version(self._current_version)
        if self._centre_stack:
            self._centre_stack.setCurrentIndex(0)
        self.guide_closed.emit()

    def _on_guide_skipped(self):
        if self._log:
            self._log.info("[WELCOME] 用户跳过引导")
        self._on_guide_finished()

    def _on_guide_completed(self):
        if self._log:
            self._log.info("[WELCOME] 用户完成全部引导步骤")
        self._on_guide_finished()
        self.guide_completed.emit(self._last_viewed_version or "first_run")

    def _build_panel(self):
        from .welcome_guide_step_panel import WelcomeGuideStepPanel
        panel = WelcomeGuideStepPanel(self._mw, self)
        panel.finished.connect(self._on_guide_finished)
        panel.skipped.connect(self._on_guide_skipped)
        panel.completed.connect(self._on_guide_completed)
        return panel

    # ── 版本工具 ────────────────────────────────────────────────

    def _compare_versions(self, v1: str, v2: str) -> int:
        parts1 = [int(x) for x in v1.split(".")]
        parts2 = [int(x) for x in v2.split(".")]
        while len(parts1) < 3:
            parts1.append(0)
        while len(parts2) < 3:
            parts2.append(0)
        for a, b in zip(parts1, parts2):
            if a < b:
                return -1
            if a > b:
                return 1
        return 0

    def _load_last_viewed_version(self) -> str:
        try:
            config = self._app_cfg.load_full_config()
            return config.get("last_viewed_intro_version", "") or ""
        except Exception:
            return ""

    def _save_last_viewed_version(self, version: str):
        self._app_cfg.save_config(last_viewed_intro_version=version)
