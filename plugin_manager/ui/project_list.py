"""
左侧面板：插件项目列表

显示所有插件项目，支持：
  - 新建项目（从模板）
  - 打开已有插件目录
  - 打开 .stp 文件（解压到临时目录后编辑）
  - 选中项目（触发右侧编辑区刷新）
  - 删除项目（临时目录自动清理）
"""

import os
import json
import zipfile
import shutil
import tempfile
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QFileDialog, QInputDialog,
    QMessageBox, QFrame, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont


class ProjectList(QWidget):
    """左侧项目列表面板"""

    project_selected = pyqtSignal(str)  # 选中某个项目目录路径
    project_count_changed = pyqtSignal(int)  # 项目数量变化

    def __init__(self, parent=None):
        super().__init__(parent)
        self._projects: dict[str, str] = {}  # display_name -> dir_path
        self._current_dir = ""  # 当前选中的项目目录

        self.setMinimumWidth(240)
        self.setMaximumWidth(360)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 标题
        title = QLabel("📦 插件项目")
        title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        layout.addWidget(title)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        btn_new = QPushButton("新建")
        btn_new.setObjectName("pmBtn")
        btn_new.setFixedSize(65, 28)
        btn_new.setCursor(Qt.PointingHandCursor)
        btn_new.setFont(QFont("Microsoft YaHei", 10))
        btn_new.clicked.connect(self._on_new)
        btn_row.addWidget(btn_new)

        btn_open = QPushButton("文件夹")
        btn_open.setObjectName("pmBtn")
        btn_open.setFixedSize(80, 28)
        btn_open.setCursor(Qt.PointingHandCursor)
        btn_open.setFont(QFont("Microsoft YaHei", 10))
        btn_open.clicked.connect(self._on_open)
        btn_row.addWidget(btn_open)

        btn_open_stp = QPushButton(" .stp")
        btn_open_stp.setObjectName("pmBtn")
        btn_open_stp.setFixedSize(90, 28)
        btn_open_stp.setCursor(Qt.PointingHandCursor)
        btn_open_stp.setFont(QFont("Microsoft YaHei", 10))
        btn_open_stp.clicked.connect(self._on_open_stp)
        btn_row.addWidget(btn_open_stp)

        btn_delete = QPushButton("删除")
        btn_delete.setObjectName("pmBtn")
        btn_delete.setFixedSize(65, 28)
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.setFont(QFont("Microsoft YaHei", 10))
        btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(btn_delete)

        layout.addLayout(btn_row)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        # 项目列表
        self._list = QListWidget()
        self._list.setObjectName("pmProjectList")
        self._list.setFont(QFont("Microsoft YaHei", 10))
        self._list.currentRowChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list, stretch=1)

        # 提示
        self._hint = QLabel("💡 点击「新建」创建插件项目\n或「打开」已有插件文件夹")
        self._hint.setFont(QFont("Microsoft YaHei", 9))
        self._hint.setAlignment(Qt.AlignCenter)
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

    # ── 新增项目 ────────────────────────────────────────────────

    def _on_new(self):
        """从模板创建新项目"""
        from plugin_manager.core.template import create_project

        # 填写基本信息
        name, ok = QInputDialog.getText(self, "新建插件", "插件名称（如：快速笔记）:")
        if not ok or not name:
            return

        plugin_id, ok = QInputDialog.getText(
            self, "插件 ID", f"插件 ID（如：author.{name}）:",
            text=f"author.{name}",
        )
        if not ok or not plugin_id:
            return

        author, ok = QInputDialog.getText(self, "作者", "作者名称:")
        if not ok or not author:
            author = "开发者"

        description, ok = QInputDialog.getText(self, "描述", "插件功能描述（一行）:")
        if not ok:
            description = name

        # 创建项目
        try:
            from plugin_manager.core.stp_packager import validate_package
            # 选择存储目录
            base_dir = QFileDialog.getExistingDirectory(self, "选择项目存放目录")
            if not base_dir:
                return

            fields = {
                "name": name,
                "plugin_id": plugin_id,
                "author": author,
                "description": description,
                "permissions": ["file_read", "settings_read"],
                "tags": [],
                "emoji": "🔧",
            }
            generated = create_project(base_dir, fields)

            # 加入列表
            project_dir = os.path.join(base_dir, plugin_id)
            self.add_project(name, project_dir)

            QMessageBox.information(self, "创建成功",
                f"插件项目已创建：{project_dir}\n\n"
                f"生成文件：\n" + "\n".join(f"  {g}" for g in generated))

        except Exception as e:
            QMessageBox.critical(self, "创建失败", f"创建插件项目失败：{e}")

    def _on_open(self):
        """打开已有插件目录"""
        folder = QFileDialog.getExistingDirectory(self, "选择插件文件夹")
        if not folder:
            return

        # 检查是否有 plugin.json
        mf = os.path.join(folder, "plugin.json")
        if not os.path.isfile(mf):
            QMessageBox.warning(self, "打开失败",
                              "所选文件夹中没有 plugin.json")
            return

        try:
            with open(mf, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            name = manifest.get("name", os.path.basename(folder))
            self.add_project(name, folder)
        except Exception as e:
            QMessageBox.warning(self, "读取失败", f"无法读取 plugin.json：{e}")

    def _on_open_stp(self):
        """打开 .stp 文件并解压到临时目录进行编辑"""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "打开 .stp 插件包",
            "", "StarPlugin 包 (*.stp);;所有文件 (*)",
        )
        if not filepath:
            return

        # 验证文件格式
        try:
            with zipfile.ZipFile(filepath, "r") as zf:
                comment = zf.comment.decode("utf-8", errors="replace").strip()
                if comment != "StarPlugin":
                    QMessageBox.warning(self, "打开失败", "不是有效的 .stp 文件（Zip 注释不匹配）")
                    return
                if "plugin.json" not in zf.namelist():
                    QMessageBox.warning(self, "打开失败", "文件中没有 plugin.json")
                    return
        except Exception:
            QMessageBox.warning(self, "打开失败", "无法读取文件，可能已损坏")
            return

        # 解压到临时目录
        temp_dir = tempfile.mkdtemp(prefix="stp_", suffix=None)
        try:
            with zipfile.ZipFile(filepath, "r") as zf:
                zf.extractall(temp_dir)

            # 读取 manifest 获取名称
            mf = os.path.join(temp_dir, "plugin.json")
            with open(mf, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            name = manifest.get("name", os.path.basename(filepath))
            # 用原始文件名加后缀区分临时项目
            display_name = f"{name} (from .stp)"
            self.add_project(display_name, temp_dir)

        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            QMessageBox.critical(self, "打开失败", f"解压或读取失败：{e}")

    def _on_delete(self):
        """从列表中移除项目（临时目录自动清理）"""
        item = self._list.currentItem()
        if not item:
            return
        name = item.text()
        reply = QMessageBox.question(self, "移除项目",
            f"确定将「{name}」从列表中移除吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            dir_path = self._projects.pop(name, "")
            row = self._list.row(item)
            self._list.takeItem(row)
            self.project_count_changed.emit(self._list.count())

            # 如果是临时目录（from .stp），清理文件
            if dir_path and dir_path.startswith(tempfile.gettempdir()):
                shutil.rmtree(dir_path, ignore_errors=True)

            if dir_path == self._current_dir:
                self._current_dir = ""
                self.project_selected.emit("")

    # ── 公开方法 ────────────────────────────────────────────────

    def add_project(self, name: str, dir_path: str):
        """添加一个项目到列表"""
        # 去重
        if dir_path in self._projects.values():
            return
        self._projects[name] = dir_path
        self._list.addItem(name)
        self._list.setCurrentRow(self._list.count() - 1)
        self.project_count_changed.emit(self._list.count())
        self._hint.setVisible(False)

    def get_current_project_dir(self) -> str:
        """获取当前选中的项目目录"""
        return self._current_dir

    # ── 内部 ────────────────────────────────────────────────────

    def _on_selection_changed(self, row: int):
        """列表选中项变化"""
        if row < 0 or row >= self._list.count():
            return
        name = self._list.item(row).text()
        self._current_dir = self._projects.get(name, "")
        self.project_selected.emit(self._current_dir)
