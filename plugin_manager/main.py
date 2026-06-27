#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StarDebate ★ 插件项目管理器

独立于 StarDebate 主程序的 PySide6 桌面应用。
用于创建、编辑和管理 StarDebate 插件项目，
并一键打包为 .stp（StarPlugin Package）格式。

使用方法：
  python plugin_manager/main.py

依赖：
  - PySide6（或 PyQt5，API 兼容）
  - Python 3.10+
"""

import sys
import os

# 将项目根目录加入路径，确保插件核心模块可导入
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 将 plugin_manager 目录加入路径
_PM_DIR = os.path.dirname(os.path.abspath(__file__))
if _PM_DIR not in sys.path:
    sys.path.insert(0, _PM_DIR)


def main():
    """启动插件项目管理器"""
    # 兼容 PyQt5 / PySide6
    try:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt
        QT_LIB = "PyQt5"
    except ImportError:
        try:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtCore import Qt
            QT_LIB = "PySide6"
        except ImportError:
            print("错误：需要 PyQt5 或 PySide6。")
            print("  pip install PyQt5")
            sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("StarDebate Plugin Manager")

    # 全局样式
    app.setStyle("Fusion")

    # 深色主题 QSS
    DARK_QSS = """
    QMainWindow, QWidget {
        background-color: #1e1e2e;
        color: #cdd6f4;
    }
    QSplitter::handle {
        background-color: #313244;
        width: 2px;
    }
    QListWidget {
        background-color: #181825;
        border: 1px solid #313244;
        border-radius: 6px;
        padding: 4px;
        outline: none;
    }
    QListWidget::item {
        padding: 6px 10px;
        border-radius: 4px;
    }
    QListWidget::item:selected {
        background-color: #45475a;
        color: #cdd6f4;
    }
    QListWidget::item:hover {
        background-color: #313244;
    }
    QLineEdit, QPlainTextEdit {
        background-color: #181825;
        border: 1px solid #45475a;
        border-radius: 4px;
        padding: 4px 8px;
        color: #cdd6f4;
    }
    QLineEdit:focus, QPlainTextEdit:focus {
        border-color: #89b4fa;
    }
    QPushButton {
        background-color: #313244;
        border: 1px solid #45475a;
        border-radius: 4px;
        padding: 4px 12px;
        color: #cdd6f4;
    }
    QPushButton:hover {
        background-color: #45475a;
    }
    QPushButton:pressed {
        background-color: #585b70;
    }
    QPushButton:disabled {
        background-color: #181825;
        color: #585b70;
    }
    QCheckBox {
        spacing: 6px;
    }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border: 2px solid #585b70;
        border-radius: 3px;
        background-color: #181825;
    }
    QCheckBox::indicator:checked {
        background-color: #89b4fa;
        border-color: #89b4fa;
    }
    QLabel {
        color: #cdd6f4;
    }
    QFrame {
        border: none;
    }
    QScrollArea {
        border: none;
    }
    QStatusBar {
        background-color: #181825;
        color: #a6adc8;
    }
    """
    app.setStyleSheet(DARK_QSS)

    from ui.main_window import PluginManagerWindow
    window = PluginManagerWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
