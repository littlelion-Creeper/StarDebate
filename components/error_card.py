"""错误卡片组件 (v1.0.0)

在欢迎页中嵌入显示启动/加载失败的错误信息卡片。
包含每项独立进度条 + 整体进度 + 超时控制 + 重试/查看日志/忽略/技术详情。
"""
import os
import json
import traceback as tb_module

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QTextEdit,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap

from components.theme_colors import tc
from components.timeout_progress_loader import MultiProgressLoader
from components.res_path import get_resource_root
from workers.app_config.config_paths import get_config_path


# ── 要读取 error.svg 的路径 ────────────────────────────────────────
_ERROR_ICON_PATH = os.path.join(get_resource_root(), "icon", "windows_icon", "error.svg")

# ── log_settings.json 路径 ─────────────────────────────────────────
_LOG_SETTINGS_PATH = get_config_path("config/log_settings.json")


class ErrorCardWidget(QFrame):
    """错误卡片组件。

    内嵌在欢迎页欢迎语下方，当有功能加载失败时显示。

    使用方式:
        card = ErrorCardWidget(main_window_ref)
        card.add_error("模块名", "错误描述", "详细traceback")
        card.add_error("...", "...")
        card.show()

    信号:
        dismissed: 用户点击"忽略"关闭卡片时触发
        retry_done: 所有重试完成 (success_count, fail_count)
    """

    dismissed = pyqtSignal()
    retry_done = pyqtSignal(int, int)  # (success_count, fail_count)

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._log_path = getattr(main_window, '_log_path', "")
        self._errors: list[dict] = []   # [{task_id, name, desc, traceback}]
        self._retrying = False
        self._retry_success = 0
        self._retry_fail = 0

        self.setObjectName("errorCard")
        self.setVisible(False)

        self._build_ui()
        self._load_qss()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # ── 标题行 (error.svg + 文字 + 计数) ──────────────────
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_row.setObjectName("errorCardTitle")

        # error.svg 图标
        self._icon_label = QLabel()
        self._icon_label.setObjectName("errorCardIcon")
        self._icon_label.setFixedSize(24, 24)
        if os.path.exists(_ERROR_ICON_PATH):
            pixmap = QPixmap(_ERROR_ICON_PATH)
            if not pixmap.isNull():
                self._icon_label.setPixmap(pixmap.scaled(
                    24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))
        title_row.addWidget(self._icon_label)

        self._title_text = QLabel("部分功能加载失败")
        self._title_text.setObjectName("errorCardTitleText")
        self._title_text.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        title_row.addWidget(self._title_text)

        self._count_label = QLabel("")
        self._count_label.setObjectName("overallCountdown")
        self._count_label.setFont(QFont("Microsoft YaHei", 10))
        self._count_label.setStyleSheet(f"color: {tc('muted')};")
        title_row.addWidget(self._count_label)

        title_row.addStretch()
        layout.addLayout(title_row)

        # ── 多任务进度加载器 ─────────────────────────────────────
        self._progress_loader = MultiProgressLoader(
            max_timeout_s=30, bar_height=6,
        )
        layout.addWidget(self._progress_loader)

        # ── 按钮行 ──────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.setObjectName("errorCardBtnRow")

        self._view_log_btn = QPushButton("查看日志")
        self._view_log_btn.setObjectName("errorCardViewLogBtn")
        self._view_log_btn.setCursor(Qt.PointingHandCursor)
        self._view_log_btn.clicked.connect(self._on_view_log)
        btn_row.addWidget(self._view_log_btn)

        self._retry_all_btn = QPushButton("全部重试")
        self._retry_all_btn.setObjectName("errorCardRetryBtn")
        self._retry_all_btn.setCursor(Qt.PointingHandCursor)
        self._retry_all_btn.clicked.connect(self._on_retry_all)
        btn_row.addWidget(self._retry_all_btn)

        self._dismiss_btn = QPushButton("忽略")
        self._dismiss_btn.setObjectName("errorCardDismissBtn")
        self._dismiss_btn.setCursor(Qt.PointingHandCursor)
        self._dismiss_btn.clicked.connect(self._on_dismiss)
        btn_row.addWidget(self._dismiss_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── 技术详情（默认折叠） ────────────────────────────────
        self._tech_toggle = QPushButton("详细技术信息 ▸")
        self._tech_toggle.setObjectName("errorCardTechToggle")
        self._tech_toggle.setCursor(Qt.PointingHandCursor)
        self._tech_toggle.clicked.connect(self._toggle_tech)
        layout.addWidget(self._tech_toggle)

        self._tech_content = QTextEdit()
        self._tech_content.setObjectName("errorCardTechContent")
        self._tech_content.setReadOnly(True)
        self._tech_content.setFixedHeight(200)
        self._tech_content.setVisible(False)
        layout.addWidget(self._tech_content)

    def _load_qss(self):
        """加载 error_card.qss 样式。"""
        theme = "catppuccin_mocha"
        try:
            cfg_path = get_config_path("config/config.json")
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    theme = json.load(f).get("theme", "catppuccin_mocha")
        except Exception:
            pass
        qss_path = os.path.join(
            get_resource_root(), "style", "themes", theme, "error_card.qss"
        )
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    # ── 公共接口 ────────────────────────────────────────────────────

    def add_error(self, module_name: str, description: str,
                  traceback_str: str = ""):
        """添加一条加载错误。

        Args:
            module_name: 功能模块名称（显示用）
            description: 错误简要描述
            traceback_str: 完整 traceback（展开技术详情时显示）
        """
        task_id = f"startup_{len(self._errors)}"
        self._errors.append({
            "task_id": task_id,
            "name": module_name,
            "desc": description,
            "traceback": traceback_str,
        })
        self._progress_loader.add_task(task_id, module_name)

        # 更新计数
        self._count_label.setText(f"({len(self._errors)})")

        # 更新技术详情
        self._refresh_tech_content()
        self._refresh_qss_border()
        self.setVisible(True)

    def clear_errors(self):
        """清除所有错误并隐藏卡片。"""
        self._errors.clear()
        self._progress_loader.reset_all()
        self._tech_content.clear()
        self._tech_content.setVisible(False)
        self._tech_toggle.setText("详细技术信息 ▸")
        self._count_label.setText("")
        self._retry_success = 0
        self._retry_fail = 0
        self.setVisible(False)

    def has_errors(self) -> bool:
        return len(self._errors) > 0

    @property
    def error_count(self) -> int:
        return len(self._errors)

    # ── 按钮回调 ────────────────────────────────────────────────────

    def _on_view_log(self):
        """用系统默认程序打开日志文件。"""
        if self._log_path and os.path.exists(self._log_path):
            try:
                os.startfile(self._log_path)
            except Exception:
                pass
        elif self._log_path:
            # 日志文件不存在，尝试打开文件夹
            log_dir = os.path.dirname(self._log_path)
            if log_dir and os.path.isdir(log_dir):
                try:
                    os.startfile(log_dir)
                except Exception:
                    pass

    def _on_retry_all(self):
        """全部重试：重新初始化所有失败的功能模块。"""
        if self._retrying:
            return

        self._retrying = True
        self._retry_success = 0
        self._retry_fail = 0
        self._retry_all_btn.setEnabled(False)
        self._retry_all_btn.setText("重试中...")

        # 自动标记日志保留
        self._auto_keep_log()

        # 启动所有进度条
        self._progress_loader.connect(
            self._progress_loader.task_finished,
            self._on_task_finished
        )
        self._progress_loader.connect(
            self._progress_loader.all_finished,
            self._on_all_retry_done
        )

        # 逐一启动重试（延迟逐个触发，避免同时阻塞）
        self._retry_index = 0
        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(100)  # 每个间隔 100ms 启动一个
        self._retry_timer.timeout.connect(self._retry_next)
        self._retry_timer.start()

    def _retry_next(self):
        """逐个启动重试任务。"""
        if self._retry_index >= len(self._errors):
            self._retry_timer.stop()
            return

        error = self._errors[self._retry_index]
        task_id = error["task_id"]
        self._retry_index += 1

        # 启动该任务的进度条
        loader = self._progress_loader.get_task(task_id)
        if loader:
            loader.start()

            # 实际执行重试逻辑：尝试重新初始化模块
            QTimer.singleShot(50, lambda tid=task_id: self._do_retry(tid))

    def _do_retry(self, task_id: str):
        """执行单个模块的重试。

        通过调用主窗口的对应管理器重新初始化来实现。
        查找方法为: self._failed_non_core 中记录的模块名。
        """
        mw = self._mw
        error = None
        for e in self._errors:
            if e["task_id"] == task_id:
                error = e
                break
        if not error:
            return

        name = error["name"]
        success = False

        try:
            # 根据模块名称尝试重新初始化
            success = self._retry_module(name)
        except Exception:
            success = False

        # 超时检测：如果进度条已超时则不覆盖状态
        loader = self._progress_loader.get_task(task_id)
        if loader and not loader.is_timeout:
            self._progress_loader.set_task_finished(task_id, success)
            if success:
                self._remove_error(task_id)

    def _retry_module(self, module_name: str) -> bool:
        """根据模块名称尝试重新初始化。

        此方法遍历主窗口中可能的初始化方法后缀，尝试重新初始化。
        各模块的重试入口统一为 _reinit_<模块名_lower>()。
        """
        mw = self._mw
        if not mw:
            return False

        # 映射: 模块显示名 → 重试方法名
        retry_map = {
            "AI分析": "_reinit_ai_analysis",
            "模拟质询": "_reinit_cross_exam",
            "模拟接质": "_reinit_accept_exam",
            "AI写稿": "_reinit_speech_writer",
            "AI扩写": "_reinit_ai_expand",
            "辩论框架": "_reinit_framework",
            "便签": "_reinit_notes",
            "模拟训练": "_reinit_training",
            "素材池": "_reinit_material_pool",
            "赛程": "_reinit_tournament",
        }

        method_name = retry_map.get(module_name)
        if method_name and hasattr(mw, method_name):
            fn = getattr(mw, method_name)
            fn()
            return True

        # 如果找不到映射，返回 False
        return False

    def _remove_error(self, task_id: str):
        """从错误列表中移除已成功的任务。"""
        self._errors = [e for e in self._errors if e["task_id"] != task_id]
        self._count_label.setText(f"({len(self._errors)})")
        self._refresh_tech_content()

        if not self._errors:
            # 全部恢复成功
            self.clear_errors()
            self.retry_done.emit(self._retry_success, self._retry_fail)

    def _on_task_finished(self, task_id: str, success: bool):
        """单个任务完成后的处理。"""
        if success:
            self._retry_success += 1
        else:
            self._retry_fail += 1

    def _on_all_retry_done(self):
        """全部重试完成后的处理。"""
        self._retrying = False
        self._retry_all_btn.setEnabled(True)
        self._retry_all_btn.setText("全部重试")

        # 如果还有残留错误，刷新卡片状态
        if self._errors:
            self._refresh_qss_border()

        self.retry_done.emit(self._retry_success, self._retry_fail)

    def _on_dismiss(self):
        """用户点击"忽略"，隐藏卡片。"""
        self.setVisible(False)
        self.dismissed.emit()

    def _toggle_tech(self):
        """折叠/展开技术详情。"""
        visible = not self._tech_content.isVisible()
        self._tech_content.setVisible(visible)
        self._tech_toggle.setText(
            "详细技术信息 ▾" if visible else "详细技术信息 ▸"
        )

    def _refresh_tech_content(self):
        """刷新技术详情内容。"""
        if not self._errors:
            self._tech_content.clear()
            return
        lines = []
        for e in self._errors:
            lines.append(f"── {e['name']} ──────────────────────")
            lines.append(f"  错误: {e['desc']}")
            if e.get("traceback"):
                lines.append(f"  Traceback (摘要):")
                for tb_line in e["traceback"].splitlines()[-10:]:
                    lines.append(f"    {tb_line.strip()}")
            lines.append("")
        self._tech_content.setText("\n".join(lines))

    def _refresh_qss_border(self):
        """根据错误数量更新边框颜色。"""
        if self._errors:
            # 保持红色边框（通过 QSS 控制，无需动态修改）
            pass

    def _auto_keep_log(self):
        """自动设置本次运行的日志保留标记。"""
        try:
            if os.path.exists(_LOG_SETTINGS_PATH):
                with open(_LOG_SETTINGS_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if not cfg.get("log_service", {}).get("keep_normal_exit_log", False):
                    cfg.setdefault("log_service", {})["keep_normal_exit_log"] = True
                    with open(_LOG_SETTINGS_PATH, "w", encoding="utf-8") as f:
                        json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
