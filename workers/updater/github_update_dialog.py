"""GitHub 更新信息对话框 — 链式补丁版。

显示补丁链信息（单补丁或多个补丁），提供「下载并更新」按钮。
已移除全量安装包相关代码，所有更新均走增量补丁 ZIP。

信号通过 __init__ 的 callable 回调传递。
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


def _fmt_size(size_bytes: int) -> str:
    """格式化文件大小。"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / 1024 / 1024:.1f} MB"


class GitHubUpdateDialog(QDialog):
    """GitHub 更新信息对话框（链式版）。

    接收 release_chain（补丁链列表）：
    - 链长=1：常规单补丁显示
    - 链长>1：显示补丁链信息（如 v6.0.0 → v6.1.0 → v6.2.0）
    - 展示最新版本的更新说明

    Callbacks:
        download_clicked(chain):  用户点击「下载并更新」
        ignore_clicked(version):  用户点击「忽略此版本」
    """

    download_clicked = None
    ignore_clicked = None

    def __init__(self, parent: QWidget | None, release_chain: list[dict],
                 on_download=None, on_ignore=None):
        super().__init__(parent)
        self._chain = release_chain
        self._latest = release_chain[-1] if release_chain else {}
        self.download_clicked = on_download
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
        chain_len = len(self._chain)
        if chain_len == 1:
            title_text = "发现新版本"
        else:
            title_text = f"发现 {chain_len} 个更新"
        self._title_bar = TitleBar(self, title=title_text)
        main_layout.addWidget(self._title_bar)

        # ── 内容区 ──────────────────────────────────────────────
        content = QFrame()
        content.setObjectName("updateDialogContent")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 20, 24, 16)
        cl.setSpacing(12)

        current = self._chain[0].get("from_version_hint",
                     self._chain[0].get("current_version", "未知")) if chain_len > 0 else "未知"
        # 取调用方传入的 current_version，或从链首推断

        # ── 版本链展示行 ────────────────────────────────────────
        ver_row = QHBoxLayout()
        ver_row.setSpacing(6)

        # 构造版本链文本: v6.0.0 → v6.1.0 → v6.2.0
        versions = [self._chain[0].get("current_version", "")]
        for entry in self._chain:
            ver = entry.get("version", "?")
            versions.append(ver)
        # 去掉空的首个版本
        versions = [v for v in versions if v]

        chain_label = QLabel(" ".join([
            f"v{versions[0]}" if versions else "",
            *[f"→ v{v}" for v in versions[1:]],
        ]))
        chain_label.setObjectName("updateVerValue")
        chain_label.setWordWrap(True)
        ver_row.addWidget(chain_label, 1)

        # 补丁总数标签
        patch_count_label = QLabel(
            f"{chain_len} 个增量补丁" if chain_len > 1 else "增量补丁",
            objectName="updateTypeLabel",
        )
        ver_row.addWidget(patch_count_label)

        cl.addLayout(ver_row)

        # ── 文件大小信息 ─────────────────────────────────────────
        total_size = sum(e.get("size", 0) for e in self._chain)
        size_label = QLabel(
            f"总大小: {_fmt_size(total_size)} ({chain_len} 个补丁)" if chain_len > 1
            else f"补丁大小: {_fmt_size(total_size)}",
            objectName="updateFileLabel",
        )
        cl.addWidget(size_label)

        # ── 更新说明区域 ───────────────────────────────────────
        notes = self._latest.get("release_notes", "暂无更新说明")
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

        # Git 提交对比链接（使用链首→链尾）
        if chain_len >= 1:
            first_ver = self._chain[0].get("current_version", "")
            last_ver = self._latest.get("version", "")
            html_url = self._latest.get("html_url", "")
            # 如果没有 current_version，用链首版本作为对比起点
            compare_from = first_ver if first_ver else (
                self._chain[0].get("version", "") if chain_len >= 1 else ""
            )
            if html_url and compare_from and last_ver:
                compare_url = html_url.replace("/releases/tag/", "/compare/")
                compare_url = compare_url.rsplit("/", 1)[0] + f"/v{compare_from}...v{last_ver}"
                link_lbl = QLabel(
                    f'<a href="{compare_url}" style="color: {tc("accent_blue")}; '
                    f'text-decoration: none;">在 GitHub 上查看变更</a>',
                    objectName="updateCompareLink",
                )
                link_lbl.setOpenExternalLinks(True)
                nl.addWidget(link_lbl)

        cl.addWidget(notes_frame)

        # ── @components/star_checkbox.StarCheckBox 忽略版本 ─────
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

        # 下载按钮（单链/多链通用）
        if chain_len > 1:
            btn_text = "串联下载并更新"
        else:
            btn_text = "下载并更新"
        btn_download = StarButton(
            btn_text, layout_mode="text_only", ratio_h=0.72,
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
            self.download_clicked(self._chain)
        self.accept()

    def _on_ignore(self):
        self._do_ignore()
        self.reject()

    def _do_ignore(self):
        ver = self._latest.get("version", "")
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
