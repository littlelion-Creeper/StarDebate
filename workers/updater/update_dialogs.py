"""更新器 — UI 对话框组件

包含：
  - UpdateFoundDialog: 检测到补丁时的确认弹窗
  - UpdateProgressDialog: 更新进度面板（主程序退出前）
  - UpdateSuccessToast: 更新成功后的通知
  - RecoveryDialog: 上次更新未完成恢复弹窗

复用 @components/title_bar (TitleBar) 和 @components/star_button (StarButton)。
"""

from __future__ import annotations

import os
import json
from workers.app_config.config_paths import get_config_path
import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QFrame, QTextBrowser, QProgressBar, QApplication,
)
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect,
    pyqtSignal,
)
from PyQt5.QtGui import QFont, QPixmap

from components.star_button import StarButton
from components.star_checkbox import StarCheckBox
from components.title_bar import TitleBar
from components.theme_colors import tc
from components.popup_dialog import CustomDialog
from components.svg_renderer import SvgRenderer
from components.res_path import get_resource_root

logger = logging.getLogger("StarDebate.updater.dialogs")

_PROJECT_ROOT = get_resource_root()
_ICON_DIR = os.path.join(_PROJECT_ROOT, "icon", "message_box")

# ── QSS 缓存 ────────────────────────────────────────────────────────────
_updater_qss_cache: str | None = None
_updater_qss_theme: str | None = None


def _load_updater_qss() -> str:
    """加载 updater.qss，使用模板替换（与 config_manager.apply_style 一致）。

    策略：
      1. 优先读取主题目录下缓存的 updater.qss（如有）
      2. 否则从 qss_templates/updater.qss 读取模板，用 theme.json 的 colors
         替换 @key@ → hex 值
      3. 缓存结果，只有主题切换时重新生成
    """
    global _updater_qss_cache, _updater_qss_theme

    try:
        # 读取当前主题名
        cfg_path = get_config_path("config/config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        theme = cfg.get("theme", "notion_dark")
    except Exception:
        theme = "notion_dark"

    # 缓存命中
    if _updater_qss_cache is not None and _updater_qss_theme == theme:
        return _updater_qss_cache

    theme_dir = os.path.join(_PROJECT_ROOT, "style", "themes", theme)

    # 1) 优先缓存文件
    cached_path = os.path.join(theme_dir, "updater.qss")
    if os.path.isfile(cached_path):
        try:
            with open(cached_path, "r", encoding="utf-8") as f:
                qss = f.read()
            _updater_qss_cache = qss
            _updater_qss_theme = theme
            return qss
        except Exception:
            pass

    # 2) 模板替换
    template_path = os.path.join(_PROJECT_ROOT, "style", "qss_templates", "updater.qss")
    if not os.path.isfile(template_path):
        _updater_qss_cache = ""
        _updater_qss_theme = theme
        return ""

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()
    except Exception:
        _updater_qss_cache = ""
        _updater_qss_theme = theme
        return ""

    # 加载 theme.json 颜色映射 {"@key@": "#hex"}
    colors = {}
    theme_json = os.path.join(theme_dir, "theme.json")
    if os.path.isfile(theme_json):
        try:
            with open(theme_json, "r", encoding="utf-8") as f:
                theme_cfg = json.load(f)
            raw = theme_cfg.get("colors", {})
            colors = {f"@{k}@": v for k, v in raw.items()}
        except Exception:
            pass

    # 替换 @key@ → hex
    qss = template
    for key, value in colors.items():
        qss = qss.replace(key, value)

    _updater_qss_cache = qss
    _updater_qss_theme = theme
    return qss


def _render_svg(svg_name: str, size=64, color_key="text") -> QPixmap:
    """渲染 SVG 图标为 QPixmap。"""
    path = os.path.join(_ICON_DIR, f"{svg_name}.svg")
    if not getattr(SvgRenderer, "_initialized", False):
        SvgRenderer.init(get_resource_root())
    return SvgRenderer.icon(path, size, color=color_key)


# ════════════════════════════════════════════════════════════════════════
#  UpdateFoundDialog — 发现新版本弹窗
# ════════════════════════════════════════════════════════════════════════

class UpdateFoundDialog(QDialog):
    """发现可用补丁时显示的确认弹窗。

    使用 TitleBar 作为标题栏（含拖拽 + 关闭按钮），
    底部按钮使用 StarButton（text_only 排布，自动缩放）。

    Signals:
        update_confirmed: 用户确认更新，携带 manifest 数据
    """

    update_confirmed = pyqtSignal(dict)

    def __init__(self, parent=None, patch_info: dict | None = None):
        super().__init__(parent)
        self._info = patch_info or {}
        self._keep_backup = True
        self.setObjectName("updateFoundDialog")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setWindowModality(Qt.ApplicationModal)
        self._setup_ui()
        self._load_theme_qss()
        QTimer.singleShot(0, self._deferred_init)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── @components/title_bar.TitleBar ────────────────────────
        self._title_bar = TitleBar(self, title="发现新版本更新")
        main_layout.addWidget(self._title_bar)

        # ── 内容区 ────────────────────────────────────────────────
        content = QFrame()
        content.setObjectName("updateDialogContent")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 20, 24, 16)
        cl.setSpacing(12)

        info = self._info
        current = info.get("current_version", "未知")
        to_ver = info.get("to_version", "未知")
        notes = info.get("release_notes", "暂无说明")
        stats = info.get("file_stats", {})
        fname = info.get("patch_filename", "")
        config_affected = info.get("config_affected", False)

        # 版本对比行
        ver_row = QHBoxLayout()
        ver_row.setSpacing(8)

        lbl_cur = QLabel("当前版本:")
        lbl_cur.setObjectName("updateVerLabel")
        ver_row.addWidget(lbl_cur)

        lbl_cur_val = QLabel(f"v{current}")
        lbl_cur_val.setObjectName("updateVerValue")
        ver_row.addWidget(lbl_cur_val)

        ver_row.addStretch()

        lbl_new_pre = QLabel("新版本:")
        lbl_new_pre.setObjectName("updateVerLabel")
        ver_row.addWidget(lbl_new_pre)

        lbl_new_val = QLabel(f"v{to_ver}")
        lbl_new_val.setObjectName("updateVerValueNew")
        ver_row.addWidget(lbl_new_val)

        cl.addLayout(ver_row)

        # 发行说明区域
        notes_frame = QFrame()
        notes_frame.setObjectName("updateNotesFrame")
        nl = QVBoxLayout(notes_frame)
        nl.setContentsMargins(14, 10, 14, 10)
        nl.setSpacing(6)

        notes_title = QLabel("更新说明")
        notes_title.setObjectName("updateNotesTitle")
        notes_title.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        nl.addWidget(notes_title)

        notes_text = QTextBrowser()
        notes_text.setObjectName("updateNotesText")
        notes_text.setMarkdown(notes)
        notes_text.setMinimumHeight(100)
        notes_text.setMaximumHeight(160)
        nl.addWidget(notes_text)
        cl.addWidget(notes_frame)

        # 文件统计
        cl.addWidget(QLabel(
            f"本次更新将修改 {stats.get('modify', 0)} 个文件，"
            f"新增 {stats.get('add', 0)} 个文件，"
            f"删除 {stats.get('delete', 0)} 个文件"
            + (f"\n（config/ 目录中的配置将被自动备份）"
               if config_affected else ""),
            objectName="updateStatLabel",
        ))
        # 补丁文件名
        cl.addWidget(QLabel(f"更新包: {fname}", objectName="updateFileLabel"))

        # 备份选项
        if config_affected:
            self._cb_backup = StarCheckBox(
                "更新后保留配置备份",
                checked=True,
                checkbox_size=18,
                object_name="updateBackupCb",
            )
            self._cb_backup.toggled.connect(self._on_backup_toggled)
            cl.addWidget(self._cb_backup)
        else:
            self._cb_backup = None

        # ── 底部操作栏（@components/star_button.StarButton） ────
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)
        btn_bar.addStretch()

        self._btn_cancel = StarButton(
            "取消", layout_mode="text_only", ratio_h=0.72,
            auto_size=True,
        )
        self._btn_cancel.setObjectName("popupDialogBtn")
        self._btn_cancel.setFixedHeight(34)
        self._btn_cancel.clicked.connect(self.reject)
        btn_bar.addWidget(self._btn_cancel)

        self._btn_update = StarButton(
            "立即更新", layout_mode="text_only", ratio_h=0.72,
            auto_size=True, accent=tc("accent"),
        )
        self._btn_update.setObjectName("popupDialogBtn")
        self._btn_update.setFixedHeight(34)
        self._btn_update.clicked.connect(self._on_confirm)
        btn_bar.addWidget(self._btn_update)

        cl.addLayout(btn_bar)
        main_layout.addWidget(content, 1)

    def _on_backup_toggled(self, checked: bool):
        self._keep_backup = checked

    def _on_confirm(self):
        result = dict(self._info)
        result["keep_backup"] = self._keep_backup
        self.update_confirmed.emit(result)
        self.accept()

    def _load_theme_qss(self):
        self.setStyleSheet(_load_updater_qss())

    def _deferred_init(self):
        self._adjust_size()
        self._center_on_parent()

    def _adjust_size(self):
        sw = QApplication.primaryScreen().availableGeometry().width()
        dialog_w = min(560, max(460, int(sw * 0.45)))
        self.setFixedWidth(int(dialog_w))
        self.setFixedHeight(max(420, int(dialog_w * 0.85)))

    def _center_on_parent(self):
        if self.parent() and self.parent().isVisible():
            pg = self.parent().geometry()
            self.move(
                pg.x() + (pg.width() - self.width()) // 2,
                pg.y() + (pg.height() - self.height()) // 2,
            )
        else:
            screen = QApplication.primaryScreen().geometry()
            self.move(
                (screen.width() - self.width()) // 2,
                (screen.height() - self.height()) // 2,
            )


# ════════════════════════════════════════════════════════════════════════
#  UpdateProgressDialog — 更新进度面板
# ════════════════════════════════════════════════════════════════════════

class UpdateProgressDialog(QWidget):
    """主程序退出前显示的更新准备进度面板。

    底部取消按钮使用 StarButton。
    Signals:
        cancelled: 用户点击取消
    """

    cancelled = pyqtSignal()

    _WIDTH = 400
    _HEIGHT = 200

    STEPS = [
        ("正在校验补丁...", 15),
        ("正在备份配置...", 30),
        ("正在解压更新文件...", 60),
        ("正在覆盖文件...", 80),
        ("正在清理缓存...", 95),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("updateProgressPanel")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.ApplicationModal)
        self._current_step = 0
        self._total_steps = len(self.STEPS)
        self._setup_ui()
        self._load_theme_qss()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("正在准备更新...")
        title.setObjectName("updateProgressTitle")
        title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        layout.addWidget(title)

        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("updateProgressBar")
        self._progress_bar.setFixedHeight(10)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)

        self._status_label = QLabel("准备中...")
        self._status_label.setObjectName("updateStatusLabel")
        layout.addWidget(self._status_label)

        # 取消按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._btn_cancel = StarButton(
            "取消更新", layout_mode="text_only", ratio_h=0.72,
            auto_size=True,
        )
        self._btn_cancel.setObjectName("updateCancelBtn")
        self._btn_cancel.setFixedHeight(32)
        self._btn_cancel.clicked.connect(lambda: self.cancelled.emit())
        btn_row.addWidget(self._btn_cancel)

        layout.addLayout(btn_row)

    def show(self):
        self.setFixedSize(self._WIDTH, self._HEIGHT)
        self._center_on_parent()
        super().show()
        self.raise_()

    def _center_on_parent(self):
        if self.parent() and self.parent().isVisible():
            pg = self.parent().geometry()
            self.move(
                pg.x() + (pg.width() - self._WIDTH) // 2,
                pg.y() + (pg.height() - self._HEIGHT) // 2,
            )
        else:
            screen = QApplication.primaryScreen().geometry()
            self.move(
                (screen.width() - self._WIDTH) // 2,
                (screen.height() - self._HEIGHT) // 2,
            )

    def _load_theme_qss(self):
        self.setStyleSheet(_load_updater_qss())

    def set_step(self, step_index: int) -> None:
        if step_index >= len(self.STEPS):
            return
        self._current_step = step_index
        msg, pct = self.STEPS[step_index]
        self._status_label.setText(msg)
        self._progress_bar.setValue(pct)

    def set_custom_status(self, message: str, pct: int) -> None:
        self._status_label.setText(message)
        self._progress_bar.setValue(pct)

    def complete(self) -> None:
        self._status_label.setText("准备完成，即将重启...")
        self._progress_bar.setValue(100)
        self._btn_cancel.setEnabled(False)


# ════════════════════════════════════════════════════════════════════════
#  UpdateSuccessToast — 更新成功通知
# ════════════════════════════════════════════════════════════════════════

class UpdateSuccessToast(QWidget):
    """重启后的更新成功通知。
    右下角弹出，提供删除备份/关闭操作。按钮使用 StarButton。
    """

    dismissed = pyqtSignal()

    def __init__(
        self, parent=None,
        new_version: str = "",
        backup_name: str = "",
        has_backup: bool = False,
    ):
        super().__init__(parent)
        self.setObjectName("updateSuccessToast")
        self._new_version = new_version
        self._backup_name = backup_name
        self._has_backup = has_backup
        self._fade_anim = None
        self._setup_ui()
        self._load_theme_qss()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setObjectName("toastIcon")
        icon_lbl.setFixedSize(28, 28)
        pix = _render_svg("checkmark_circle", 28, "success")
        if not pix.isNull():
            icon_lbl.setPixmap(pix)
        layout.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        text_col.addWidget(QLabel(
            f"已成功更新至 v{self._new_version}",
            objectName="toastTitle",
        ))

        if self._has_backup:
            text_col.addWidget(QLabel(
                f"配置备份已保存至 backups/{self._backup_name}",
                objectName="toastDesc",
            ))

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        if self._has_backup:
            self._btn_delete = StarButton(
                "删除备份", layout_mode="text_only", ratio_h=0.72,
                auto_size=True,
            )
            self._btn_delete.setObjectName("toastBtn")
            self._btn_delete.setFixedHeight(26)
            self._btn_delete.clicked.connect(self._on_delete_backup)
            btn_row.addWidget(self._btn_delete)

        self._btn_close = StarButton(
            "知道了", layout_mode="text_only", ratio_h=0.72,
            auto_size=True,
        )
        self._btn_close.setObjectName("toastBtn")
        self._btn_close.setFixedHeight(26)
        self._btn_close.clicked.connect(self.dismiss)
        btn_row.addWidget(self._btn_close)

        text_col.addLayout(btn_row)
        layout.addLayout(text_col, 1)

    def show_toast(self, duration_ms: int = 8000) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        w = min(400, int(screen.width() * 0.35))
        h = 120 if self._has_backup else 80
        x = screen.right() - w - 20
        y = screen.bottom() - h - 40
        self.setGeometry(x, y, w, h)
        self.show()
        self.raise_()
        self._fade_in()
        QTimer.singleShot(duration_ms, self.dismiss)

    def dismiss(self) -> None:
        self._fade_out()

    def _fade_in(self):
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(300)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _fade_out(self):
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(250)
        anim.setStartValue(self.windowOpacity())
        anim.setEndValue(0.0)
        anim.finished.connect(self.close)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _on_delete_backup(self):
        from .update_utils import delete_backup
        if delete_backup(self._backup_name):
            self._has_backup = False
            self._btn_delete.setEnabled(False)
            self._btn_delete.setText("已删除")

    def _load_theme_qss(self):
        self.setStyleSheet(_load_updater_qss())


# ════════════════════════════════════════════════════════════════════════
#  RecoveryDialog — 上次更新失败恢复弹窗
# ════════════════════════════════════════════════════════════════════════

class RecoveryDialog(QDialog):
    """启动时检测到上次更新未完成的恢复弹窗。

    使用 TitleBar 作为标题栏，按钮使用 StarButton。

    Signals:
        retry_clicked: 用户选择重新执行更新
        ignore_clicked: 用户选择忽略并清理暂存
    """

    retry_clicked = pyqtSignal()
    ignore_clicked = pyqtSignal()

    def __init__(self, parent=None, state_info: dict | None = None):
        super().__init__(parent)
        self._state = state_info or {}
        self.setObjectName("recoveryDialog")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setWindowModality(Qt.ApplicationModal)
        self._setup_ui()
        self._load_theme_qss()
        QTimer.singleShot(0, self._deferred_init)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── @components/title_bar.TitleBar ────────────────────────
        self._title_bar = TitleBar(self, title="更新恢复")
        main_layout.addWidget(self._title_bar)

        # ── 内容区 ────────────────────────────────────────────────
        content = QFrame()
        content.setObjectName("recoveryContent")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 24, 24, 20)
        cl.setSpacing(14)

        # 警告图标 + 文字
        msg_row = QHBoxLayout()
        msg_row.setSpacing(16)

        warn_icon = QLabel()
        warn_icon.setObjectName("recoveryWarnIcon")
        warn_icon.setFixedSize(48, 48)
        pix = _render_svg("exclamationmark_circle", 48, "accent_red")
        if not pix.isNull():
            warn_icon.setPixmap(pix)
        msg_row.addWidget(warn_icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(6)

        text_col.addWidget(QLabel(
            "上次更新未完成",
            objectName="recoveryTitle",
        ))
        text_col.addWidget(QLabel(
            "检测到残留的更新暂存文件。\n"
            "可能原因：更新进程意外中断或冲突。\n\n"
            "请选择处理方式：",
            objectName="recoveryDesc",
        ))

        msg_row.addLayout(text_col, 1)
        cl.addLayout(msg_row)

        # 暂存信息
        state = self._state
        target_ver = state.get("target_version", "未知")
        patch_file = state.get("patch_filename", "")

        info_frame = QFrame()
        info_frame.setObjectName("recoveryInfoFrame")
        il = QVBoxLayout(info_frame)
        il.setContentsMargins(12, 8, 12, 8)
        il.setSpacing(4)

        il.addWidget(QLabel(f"目标版本: v{target_ver}"))
        if patch_file:
            il.addWidget(QLabel(f"补丁文件: {patch_file}"))
        cl.addWidget(info_frame)

        # ── 底部操作栏（@components/star_button.StarButton） ────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self._btn_ignore = StarButton(
            "忽略并清理", layout_mode="text_only", ratio_h=0.72,
            auto_size=True,
        )
        self._btn_ignore.setObjectName("popupDialogBtn")
        self._btn_ignore.setFixedHeight(34)
        self._btn_ignore.clicked.connect(self._on_ignore)
        btn_row.addWidget(self._btn_ignore)

        self._btn_retry = StarButton(
            "重新执行", layout_mode="text_only", ratio_h=0.72,
            auto_size=True, accent=tc("accent"),
        )
        self._btn_retry.setObjectName("popupDialogBtn")
        self._btn_retry.setFixedHeight(34)
        self._btn_retry.clicked.connect(self._on_retry)
        btn_row.addWidget(self._btn_retry)

        cl.addLayout(btn_row)
        main_layout.addWidget(content, 1)

    def _on_retry(self):
        self.retry_clicked.emit()
        self.accept()

    def _on_ignore(self):
        self.ignore_clicked.emit()
        self.accept()

    def _load_theme_qss(self):
        self.setStyleSheet(_load_updater_qss())

    def _deferred_init(self):
        self.setFixedWidth(480)
        self.setFixedHeight(360)
        self._center_on_parent()

    def _center_on_parent(self):
        if self.parent() and self.parent().isVisible():
            pg = self.parent().geometry()
            self.move(
                pg.x() + (pg.width() - self.width()) // 2,
                pg.y() + (pg.height() - self.height()) // 2,
            )
        else:
            screen = QApplication.primaryScreen().geometry()
            self.move(
                (screen.width() - self.width()) // 2,
                (screen.height() - self.height()) // 2,
            )
