"""GitHub 更新信息对话框 — 使用 @components 中的通用组件。

脉冲对话框场景：
  1. 检测到增量补丁 (patch_*.zip) → 显示「下载并更新」按钮
  2. 检测到大版本安装包 (*Setup.exe) → 显示「一键下载安装包」+「前往 GitHub 页面」按钮
"""

from __future__ import annotations

import os
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt5.QtWidgets import QWidget

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTextBrowser, QApplication,
)

from components.title_bar import TitleBar
from components.star_button import StarButton
from components.star_checkbox import StarCheckBox
from components.theme_colors import tc

logger = logging.getLogger("StarDebate.updater.github_dialog")


def _load_github_dialog_qss() -> str:
    """加载 GitHub 更新对话框的 QSS（利用现有的 updater.qss 主题）。"""
    try:
        from workers.updater.update_dialogs import _load_updater_qss
        return _load_updater_qss()
    except Exception:
        return ""


class GitHubUpdateDialog(QDialog):
    """GitHub 更新信息对话框。

    使用 @components/title_bar.TitleBar 作为标题栏，
    使用 @components/star_button.StarButton 作为按钮，
    使用 @components/star_checkbox.StarCheckBox 作为选项。

    Signals:
        download_clicked:   用户点击「下载并更新」/「一键下载安装包」
        navigate_clicked:   用户点击「前往 GitHub 页面」
        ignore_clicked:     用户点击「忽略此版本」
    """

    download_clicked = None  # 由 __init__ 传入的 callable
    navigate_clicked = None
    ignore_clicked = None

    def __init__(self, parent: QWidget | None, release_info: dict,
                 on_download=None, on_navigate=None, on_ignore=None):
        super().__init__(parent)
        self._info = release_info
        self.download_clicked = on_download
        self.navigate_clicked = on_navigate
        self.ignore_clicked = on_ignore

        self.setObjectName("updateFoundDialog")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setWindowModality(Qt.ApplicationModal)
        self._setup_ui()
        qss = _load_github_dialog_qss()
        if qss:
            self.setStyleSheet(qss)
        QTimer.singleShot(0, self._deferred_init)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── @components/title_bar.TitleBar ──────────────────────
        title_text = "发现大版本更新" if self._info.get("update_type") == "major" else "发现新版本"
        self._title_bar = TitleBar(self, title=title_text)
        main_layout.addWidget(self._title_bar)

        # ── 内容区 ──────────────────────────────────────────────
        content = QFrame()
        content.setObjectName("updateDialogContent")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 20, 24, 16)
        cl.setSpacing(12)

        info = self._info
        current = info.get("current_version", "未知")
        to_ver = info.get("version", "未知")
        update_type = info.get("update_type", "patch")
        notes = info.get("release_notes", "暂无更新说明")
        patch_size = info.get("size", 0)
        installer_size = info.get("installer_size", 0)
        html_url = info.get("html_url", "")

        # ── 版本对比行 ──────────────────────────────────────────
        ver_row = QHBoxLayout()
        ver_row.setSpacing(8)

        lbl_cur = QLabel("当前版本:")
        lbl_cur.setObjectName("updateVerLabel")
        ver_row.addWidget(lbl_cur)

        lbl_cur_val = QLabel(f"v{current}")
        lbl_cur_val.setObjectName("updateVerValue")
        ver_row.addWidget(lbl_cur_val)

        ver_row.addWidget(QLabel("→", objectName="updateVerArrow"))

        lbl_new_pre = QLabel("最新版本:")
        lbl_new_pre.setObjectName("updateVerLabel")
        ver_row.addWidget(lbl_new_pre)

        lbl_new_val = QLabel(f"v{to_ver}")
        lbl_new_val.setObjectName("updateVerValueNew")
        ver_row.addWidget(lbl_new_val)

        ver_row.addStretch()

        # 更新类型标签
        type_label = QLabel(
            "增量补丁" if update_type == "patch" else "全量安装包",
            objectName="updateTypeLabel",
        )
        ver_row.addWidget(type_label)

        cl.addLayout(ver_row)

        # ── 文件大小信息 ─────────────────────────────────────────
        size_parts = []
        if update_type == "patch" and patch_size:
            size_parts.append(f"补丁大小: {_fmt_size(patch_size)}")
        if installer_size:
            size_parts.append(f"安装包大小: {_fmt_size(installer_size)}")
        if size_parts:
            cl.addWidget(QLabel("  ".join(size_parts), objectName="updateFileLabel"))

        # ── 大版本额外提示 ───────────────────────────────────────
        if update_type == "major":
            warn_lbl = QLabel(
                "⚠ 此版本涉及重大变更，需要下载完整安装包覆盖安装。",
                objectName="updateMajorWarn",
            )
            warn_lbl.setWordWrap(True)
            cl.addWidget(warn_lbl)

        # ── 更新说明区域 ───────────────────────────────────────
        notes_frame = QFrame()
        notes_frame.setObjectName("updateNotesFrame")
        nl = QVBoxLayout(notes_frame)
        nl.setContentsMargins(14, 10, 14, 10)
        nl.setSpacing(6)

        notes_title = QLabel("更新说明", objectName="updateNotesTitle")
        nl.addWidget(notes_title)

        notes_text = QTextBrowser()
        notes_text.setObjectName("updateNotesText")
        notes_text.setMarkdown(notes)
        notes_text.setMinimumHeight(100)
        notes_text.setMaximumHeight(160)
        nl.addWidget(notes_text)

        # Git 提交对比链接
        if html_url:
            compare_url = html_url.replace("/releases/tag/", "/compare/")
            compare_url = compare_url.rsplit("/", 1)[0] + f"/v{current}...v{to_ver}"
            link_lbl = QLabel(
                f'<a href="{compare_url}" style="color: {tc("accent_blue")}; '
                f'text-decoration: none;">在 GitHub 上查看变更</a>',
                objectName="updateCompareLink",
            )
            link_lbl.setOpenExternalLinks(True)
            nl.addWidget(link_lbl)

        cl.addWidget(notes_frame)

        # ── @components/star_checkbox.StarCheckBox 自动检查 ─────
        self._cb_ignore = StarCheckBox(
            "忽略此版本",
            checked=False,
            checkbox_size=18,
            object_name="updateIgnoreCb",
        )
        cl.addWidget(self._cb_ignore)

        # ── 底部操作栏 (@components/star_button.StarButton) ────
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)

        # 忽略按钮
        btn_ignore = StarButton(
            "忽略此版本", layout_mode="text_only", ratio_h=0.72,
            auto_size=True,
        )
        btn_ignore.setFixedHeight(34)
        btn_ignore.clicked.connect(self._on_ignore)
        btn_bar.addWidget(btn_ignore)

        btn_bar.addStretch()

        if update_type == "patch":
            # 增量补丁: 仅「下载并更新」主按钮
            btn_download = StarButton(
                "下载并更新", layout_mode="text_only", ratio_h=0.72,
                auto_size=True, accent=tc("accent"),
            )
            btn_download.setFixedHeight(34)
            btn_download.clicked.connect(self._on_download)
            btn_bar.addWidget(btn_download)
        else:
            # 大版本: 「前往 GitHub 页面」+「一键下载安装包」
            btn_nav = StarButton(
                "前往 GitHub 页面", layout_mode="text_only", ratio_h=0.72,
                auto_size=True,
            )
            btn_nav.setFixedHeight(34)
            btn_nav.clicked.connect(self._on_navigate)
            btn_bar.addWidget(btn_nav)

            btn_download = StarButton(
                "一键下载安装包", layout_mode="text_only", ratio_h=0.72,
                auto_size=True, accent=tc("accent"),
            )
            btn_download.setFixedHeight(34)
            btn_download.clicked.connect(self._on_download)
            btn_bar.addWidget(btn_download)

        cl.addLayout(btn_bar)
        main_layout.addWidget(content, 1)

    # ── 内部回调 ────────────────────────────────────────────────────────

    def _on_download(self):
        if self._cb_ignore.isChecked():
            self._do_ignore()
        if callable(self.download_clicked):
            self.download_clicked(self._info)
        self.accept()

    def _on_navigate(self):
        if self._cb_ignore.isChecked():
            self._do_ignore()
        if callable(self.navigate_clicked):
            self.navigate_clicked(self._info)
        self.accept()

    def _on_ignore(self):
        self._do_ignore()
        self.reject()

    def _do_ignore(self):
        ver = self._info.get("version", "")
        if ver and callable(self.ignore_clicked):
            self.ignore_clicked(ver)

    # ── 布局 ────────────────────────────────────────────────────────────

    def _deferred_init(self):
        self._adjust_size()
        self._center_on_parent()

    def _adjust_size(self):
        sw = QApplication.primaryScreen().availableGeometry().width()
        dialog_w = min(580, max(480, int(sw * 0.48)))
        self.setFixedWidth(int(dialog_w))
        self.setFixedHeight(max(440, int(dialog_w * 0.85)))

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


def _fmt_size(size_bytes: int) -> str:
    """格式化文件大小。"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
