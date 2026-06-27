"""带超时控制的进度条组件 (v1.0.0)

提供每项/全局进度条 + 倒计时 + 超时自动终止机制。
可复用于: 启动加载、AI 调用、插件加载等异步操作场景。
"""
import time
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QProgressBar, QLabel, QFrame
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont

from components.theme_colors import tc


class TimeoutProgressLoader(QWidget):
    """带超时控制的单条进度加载组件。

    单个加载任务的进度条 + 倒计时标签。
    超时时自动终止并触发 timeout_expired 信号。

    使用方式:
        loader = TimeoutProgressLoader(max_timeout_s=30)
        loader.start()
        # ... loader.finished(True, "加载成功")
        # 或超时自动触发 loader.timeout_expired

    信号:
        timeout_expired: 超时时触发
    """

    timeout_expired = pyqtSignal()

    def __init__(self, parent=None,
                 max_timeout_s: int = 30,
                 bar_height: int = 6,
                 show_countdown: bool = True):
        super().__init__(parent)
        self._max_timeout = max_timeout_s
        self._elapsed = 0.0
        self._running = False
        self._finished = False
        self._start_ts = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(200)  # 200ms 更新一次进度
        self._timer.timeout.connect(self._on_tick)

        self._setup_ui(bar_height, show_countdown)
        self._apply_style()

    def _setup_ui(self, bar_height: int, show_countdown: bool):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 进度条
        self._bar = QProgressBar()
        self._bar.setObjectName("progressLoader")
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(bar_height)
        layout.addWidget(self._bar, 1)

        # 倒计时文字
        if show_countdown:
            self._countdown_label = QLabel(f"0/{self._max_timeout}s")
            self._countdown_label.setObjectName("progressCountdown")
            self._countdown_label.setFont(QFont("Microsoft YaHei", 9))
            self._countdown_label.setFixedWidth(60)
            self._countdown_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            layout.addWidget(self._countdown_label)

    def _apply_style(self):
        """应用动态主题色。"""
        bar_color = tc("accent_blue")
        self._bar.setStyleSheet(f"""
            QProgressBar#progressLoader {{
                background-color: {tc("overlay")};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar#progressLoader::chunk {{
                background-color: {bar_color};
                border-radius: 3px;
            }}
        """)

    # ── 公共接口 ────────────────────────────────────────────────────

    def start(self):
        """开始加载计时。"""
        if self._finished:
            return
        self._running = True
        self._elapsed = 0.0
        self._start_ts = time.time()
        self._bar.setValue(0)
        self._timer.start()

    def stop(self):
        """停止计时（成功或手动取消时调用）。"""
        self._running = False
        self._timer.stop()

    def reset(self):
        """重置进度条到初始状态。"""
        self._running = False
        self._finished = False
        self._elapsed = 0.0
        self._timer.stop()
        self._bar.setValue(0)
        if hasattr(self, '_countdown_label'):
            self._countdown_label.setText(f"0/{self._max_timeout}s")

    def set_finished(self, success: bool = True):
        """标记加载完成。
        
        Args:
            success: True 为成功，False 为失败
        """
        self._finished = True
        self.stop()
        if success:
            self._bar.setValue(100)
        else:
            self._bar.setStyleSheet(f"""
                QProgressBar#progressLoader {{
                    background-color: {tc("overlay")};
                    border: none;
                    border-radius: 3px;
                }}
                QProgressBar#progressLoader::chunk {{
                    background-color: {tc("error")};
                    border-radius: 3px;
                }}
            """)

    @property
    def is_timeout(self) -> bool:
        return self._elapsed >= self._max_timeout

    @property
    def elapsed(self) -> float:
        return self._elapsed

    # ── 内部计时 ────────────────────────────────────────────────────

    def _on_tick(self):
        if not self._running:
            return
        now = time.time()
        self._elapsed = now - self._start_ts

        # 更新进度条
        pct = min(100, int((self._elapsed / self._max_timeout) * 100))
        self._bar.setValue(pct)

        # 更新倒计时
        if hasattr(self, '_countdown_label'):
            remaining = max(0, self._max_timeout - int(self._elapsed))
            self._countdown_label.setText(f"{int(self._elapsed)}/{self._max_timeout}s")

        # 超时检测
        if self._elapsed >= self._max_timeout:
            self.stop()
            self.set_finished(success=False)
            self.timeout_expired.emit()


class MultiProgressLoader(QFrame):
    """多任务进度加载器。

    包含:
    - 顶部整体进度条（总进度 + 倒计时）
    - 下方每个任务独立的进度条行

    使用方式:
        loader = MultiProgressLoader(max_timeout_s=30)
        loader.add_task("task_id_1", "模块名称")
        loader.add_task("task_id_2", "另一个模块")
        loader.start_all()

        # 单个任务完成
        loader.set_task_finished("task_id_1", True)
        # 或失败
        loader.set_task_finished("task_id_2", False)

        # 全部完成时自动触发全部完成回调

    属性:
        max_timeout_s: 每项最大超时时间（秒）
        tasks: dict[str, _TaskData] 当前所有任务
    """

    # 信号：某任务完成 (task_id, success)
    task_finished = pyqtSignal(str, bool)
    # 信号：全部任务完成 (所有任务都已 stop)
    all_finished = pyqtSignal()

    class _TaskData:
        __slots__ = ("name", "loader", "label", "status_label", "row", "done")

        def __init__(self, name, loader, label, status_label, row):
            self.name = name
            self.loader = loader
            self.label = label
            self.status_label = status_label
            self.row = row
            self.done = False

    def __init__(self, parent=None, max_timeout_s: int = 30, bar_height: int = 6):
        super().__init__(parent)
        self._max_timeout = max_timeout_s
        self._bar_height = bar_height
        self._bar_color = tc("accent_blue")
        self._tasks: dict[str, MultiProgressLoader._TaskData] = {}
        self._task_count = 0
        self._finished_count = 0

        self.setObjectName("multiProgressLoader")
        self.setVisible(False)

        self._build_ui()

    def _build_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 12, 16, 12)
        self._layout.setSpacing(8)

        # ── 整体进度 ──────────────────────────────────────────────
        overall_row = QHBoxLayout()
        overall_row.setSpacing(8)

        overall_label = QLabel("加载进度:")
        overall_label.setObjectName("overallProgressLabel")
        overall_label.setFont(QFont("Microsoft YaHei", 10))
        overall_row.addWidget(overall_label)

        self._overall_bar = QProgressBar()
        self._overall_bar.setObjectName("overallProgressBar")
        self._overall_bar.setRange(0, 100)
        self._overall_bar.setValue(0)
        self._overall_bar.setTextVisible(False)
        self._overall_bar.setFixedHeight(self._bar_height + 2)
        overall_row.addWidget(self._overall_bar, 1)

        self._overall_countdown = QLabel("0s")
        self._overall_countdown.setObjectName("overallCountdown")
        self._overall_countdown.setFont(QFont("Microsoft YaHei", 9))
        self._overall_countdown.setFixedWidth(80)
        self._overall_countdown.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        overall_row.addWidget(self._overall_countdown)

        self._layout.addLayout(overall_row)

        # ── 任务列表容器 ──────────────────────────────────────────
        self._tasks_container = QVBoxLayout()
        self._tasks_container.setSpacing(6)
        self._layout.addLayout(self._tasks_container)

        # ── 全局计时器（仅用于更新整体进度条状态）───────────────
        self._overall_timer = QTimer(self)
        self._overall_timer.setInterval(500)
        self._overall_timer.timeout.connect(self._update_overall)

    # ── 公共接口 ────────────────────────────────────────────────────

    def add_task(self, task_id: str, name: str) -> TimeoutProgressLoader:
        """添加一个加载任务。

        Args:
            task_id: 唯一任务 ID
            name: 显示名称

        Returns:
            该任务的 TimeoutProgressLoader 实例
        """
        if task_id in self._tasks:
            return self._tasks[task_id].loader

        # 任务行
        row = QHBoxLayout()
        row.setSpacing(8)

        label = QLabel(name)
        label.setObjectName("taskProgressName")
        label.setFont(QFont("Microsoft YaHei", 10))
        label.setFixedWidth(140)
        row.addWidget(label)

        loader = TimeoutProgressLoader(
            max_timeout_s=self._max_timeout,
            bar_height=self._bar_height,
            show_countdown=True,
        )
        loader.timeout_expired.connect(lambda tid=task_id: self._on_task_timeout(tid))
        row.addWidget(loader, 1)

        status_label = QLabel("等待中")
        status_label.setObjectName("taskProgressStatus")
        status_label.setFont(QFont("Microsoft YaHei", 9))
        status_label.setFixedWidth(70)
        status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(status_label)

        self._tasks_container.addLayout(row)
        self._task_count += 1

        data = MultiProgressLoader._TaskData(name, loader, label, status_label, row)
        self._tasks[task_id] = data

        self._update_overall()
        return loader

    def remove_task(self, task_id: str):
        """移除一个任务（对应的行会被删除）。"""
        data = self._tasks.pop(task_id, None)
        if data:
            data.loader.stop()
            # 从布局中移除行
            for i in range(self._tasks_container.count()):
                item = self._tasks_container.itemAt(i)
                if item and item.layout() is data.row:
                    self._tasks_container.removeItem(item)
                    # 清理行内的 widget
                    while data.row.count():
                        child = data.row.takeAt(0)
                        if child.widget():
                            child.widget().deleteLater()
                    break
            self._task_count -= 1
            self._update_overall()

    def start_all(self):
        """启动所有任务的计时器。"""
        self.setVisible(True)
        self._finished_count = 0
        self._overall_bar.setValue(0)
        self._overall_bar.setStyleSheet(f"""
            QProgressBar#overallProgressBar {{
                background-color: {tc("overlay")};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar#overallProgressBar::chunk {{
                background-color: {self._bar_color};
                border-radius: 3px;
            }}
        """)
        self._overall_timer.start()

        for data in self._tasks.values():
            data.done = False
            data.loader.reset()
            data.loader.start()
            data.status_label.setText(f"0/{self._max_timeout}s")

    def stop_all(self):
        """停止所有任务。"""
        self._overall_timer.stop()
        for data in self._tasks.values():
            data.loader.stop()

    def reset_all(self):
        """重置所有任务到初始状态。"""
        self._overall_timer.stop()
        for data in self._tasks.values():
            data.loader.reset()
            data.status_label.setText("等待中")
            data.done = False
        self._finished_count = 0
        self._overall_bar.setValue(0)
        self.setVisible(False)

    def set_task_finished(self, task_id: str, success: bool = True):
        """标记某个任务完成。

        Args:
            task_id: 任务 ID
            success: True=成功, False=失败
        """
        data = self._tasks.get(task_id)
        if not data or data.done:
            return

        data.done = True
        data.loader.set_finished(success)
        data.loader.stop()

        if success:
            data.status_label.setText("✓ 已恢复")
            data.status_label.setStyleSheet(f"color: {tc('success')};")
        else:
            remaining = self._max_timeout - int(data.loader.elapsed)
            data.status_label.setText(f"⏱ 超时({remaining}s)")
            data.status_label.setStyleSheet(f"color: {tc('error')};")
            data.status_label.setText(f"已超时 ({int(data.loader.elapsed)}s)")
            data.status_label.setStyleSheet(f"color: {tc('warning')};")

        self._finished_count += 1
        self._update_overall()
        self.task_finished.emit(task_id, success)

        # 检查是否全部完成
        if self._finished_count >= self._task_count:
            self._overall_timer.stop()
            self.all_finished.emit()

    def is_all_done(self) -> bool:
        return self._finished_count >= self._task_count

    def get_task(self, task_id: str) -> TimeoutProgressLoader | None:
        data = self._tasks.get(task_id)
        return data.loader if data else None

    # ── 内部方法 ────────────────────────────────────────────────────

    def _on_task_timeout(self, task_id: str):
        """单个任务超时后的处理。"""
        self.set_task_finished(task_id, success=False)

    def _update_overall(self):
        """更新整体进度条。"""
        if self._task_count == 0:
            self._overall_bar.setValue(0)
            self._overall_countdown.setText("0s")
            return

        # 计算整体进度（已完成任务数占百分比）
        pct = int((self._finished_count / self._task_count) * 100)
        self._overall_bar.setValue(pct)

        # 计算整体已用时间（取所有任务中最大的 elapsed）
        max_elapsed = 0
        for data in self._tasks.values():
            if data.loader.elapsed > max_elapsed:
                max_elapsed = data.loader.elapsed
        self._overall_countdown.setText(
            f"{self._finished_count}/{self._task_count}  {int(max_elapsed)}s"
        )
