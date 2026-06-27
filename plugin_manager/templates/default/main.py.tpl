# -*- coding: utf-8 -*-
"""
$NAME 插件
==============
$DESCRIPTION

使用方法：
  - 导入插件后，点击导航栏按钮打开面板
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFrame,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from workers.plugin_manager import get_api

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


class $CLASS_NAME:
    """插件主类"""

    def __init__(self):
        self.api = get_api()
        self._panel = None

    def on_enable(self):
        """插件启用时调用"""
        self.api.update_status("$NAME 插件已启用")

        # 注册侧边导航栏按钮
        self.api.register_nav_button(
            side="right",
            emoji="$EMOJI",
            label="$SHORT_NAME",
            tooltip="$DESCRIPTION",
            callback=self._open_panel,
        )

    def on_disable(self):
        """插件禁用时调用"""
        if self._panel:
            self._panel.deleteLater()
            self._panel = None
        self.api.update_status("$NAME 插件已禁用")

    def _open_panel(self):
        """打开插件面板"""
        if self._panel is None:
            self._panel = QWidget()
            layout = QVBoxLayout(self._panel)
            layout.setContentsMargins(12, 12, 12, 12)
            label = QLabel("$NAME 面板")
            label.setFont(QFont("Microsoft YaHei", 14))
            layout.addWidget(label)

        # 打开或切换到面板
        self.api.register_panel(
            side="right",
            title="$SHORT_NAME",
            emoji="$EMOJI",
            tooltip="$DESCRIPTION",
            create_widget=lambda: self._panel,
        )


# 实例化（插件管理器自动发现）
plugin = $CLASS_NAME()
