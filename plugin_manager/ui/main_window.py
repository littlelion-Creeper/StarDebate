"""
插件项目管理器主窗口

双栏布局：
  - 左侧：项目列表（ProjectList）
  - 右侧：元数据编辑器（MetadataEditor）
"""

import os
import sys
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter, QLabel,
    QStatusBar, QFrame, QSizePolicy,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

# 添加父目录到路径以便导入
_PLUGIN_MGR_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PLUGIN_MGR_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_MGR_DIR)

from ui.project_list import ProjectList
from ui.metadata_editor import MetadataEditor


class PluginManagerWindow(QMainWindow):
    """插件项目管理器主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("StarDebate ★ 插件项目管理器")
        self.setMinimumSize(850, 550)
        self.resize(950, 640)
        self._build_ui()

    def _build_ui(self):
        # 中央部件
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 分隔器
        splitter = QSplitter(Qt.Horizontal)

        # 左侧项目列表
        self._project_list = ProjectList()
        self._project_list.project_selected.connect(self._on_project_selected)
        self._project_list.project_count_changed.connect(self._on_count_changed)
        splitter.addWidget(self._project_list)

        # 右侧编辑器
        self._editor = MetadataEditor()
        splitter.addWidget(self._editor)

        splitter.setStretchFactor(0, 0)  # 左侧固定
        splitter.setStretchFactor(1, 1)  # 右侧拉伸
        splitter.setSizes([340, 500])

        layout.addWidget(splitter)

        # 状态栏
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_label = QLabel("就绪")
        self._status_label.setFont(QFont("Microsoft YaHei", 9))
        self._status_bar.addWidget(self._status_label)

    # ── 信号处理 ────────────────────────────────────────────────

    def _on_project_selected(self, dir_path: str):
        """项目选中：加载到编辑器"""
        self._editor.load_project(dir_path)
        if dir_path:
            name = os.path.basename(dir_path)
            self._status_label.setText(f"📂 {name}")
        else:
            self._status_label.setText("就绪")

    def _on_count_changed(self, count: int):
        """项目数量变化：更新窗口标题"""
        if count > 0:
            self.setWindowTitle(f"StarDebate ★ 插件项目管理器 ({count} 个项目)")
        else:
            self.setWindowTitle("StarDebate ★ 插件项目管理器")
