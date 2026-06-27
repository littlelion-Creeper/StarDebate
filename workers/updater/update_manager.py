"""更新器 — 主进程侧管理器（同进程软重启版 v2.0）

流程：
  1. 校验补丁（manifest + SHA256）
  2. 备份 config/
  3. 解压到暂存区
  4. 直接覆盖文件（不退出进程）
  5. 删除旧文件
  6. 清理 __pycache__
  7. 写入 update_state.json {status: "files_replaced"}
  8. 发出监视钩子 → QApplication.quit()
  9. StarDebate.py 的 main_loop() 检测到 files_replaced
     → 改为 "restarting" → 重新调用 main()
  10. 新主窗口检测 restarting → 显示成功通知 → 清理

LogService 保持运行，队列投递不受影响。
"""

from __future__ import annotations

import os
import json
import zipfile
import shutil
import logging
import time as _time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt5.QtWidgets import QWidget, QMainWindow

from PyQt5.QtCore import QTimer, pyqtSignal, QObject

from .update_utils import (
    get_project_root,
    get_config_version,
    get_staging_dir,
    get_backups_dir,
    get_update_state_path,
    read_update_state,
    write_update_state,
    clean_pycache,
    read_manifest,
    validate_patch_compatibility,
    backup_config_dir,
    list_backups,
    add_ignored_patch,
    remove_ignored_patch,
    get_ignored_patches,
    is_excluded_path,
    apply_new_files,
    execute_deletes,
    needs_restart,
    clear_restart_flag,
    compute_sha256,
)
from .update_checker import UpdateChecker
from .update_dialogs import (
    UpdateFoundDialog,
    UpdateProgressDialog,
    UpdateSuccessToast,
    RecoveryDialog,
)

logger = logging.getLogger("StarDebate.updater.manager")

# ── 常量 ────────────────────────────────────────────────────────────────
_NEW_FILES_DIR = "new_files"


# ════════════════════════════════════════════════════════════════════════
#  UpdateManager — 主进程侧管理器（同进程软重启版）
# ════════════════════════════════════════════════════════════════════════

class UpdateManager(QObject):
    """主进程侧更新管理器（软重启版）。

    用法:
        mgr = UpdateManager(main_window)
        mgr.check_on_startup()          # 启动时自动检测
        mgr.show_manual_install()       # 手动选择补丁

    Signals:
        update_started:    更新流程已开始
        update_completed:  更新流程已完成（文件已替换）
        update_cancelled:  用户取消或更新失败
    """

    update_started = pyqtSignal()
    update_completed = pyqtSignal()
    update_cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_window = parent
        self._project_root = get_project_root()
        self._checker = UpdateChecker()
        self._progress_panel: UpdateProgressDialog | None = None
        self._current_patch: dict | None = None
        self._updating = False
        # 日志客户端引用（由 StarDebateApp 注入）
        self._log_client = None

    def inject_log_client(self, log_client):
        """注入 LogClient 实例用于监视钩子。"""
        self._log_client = log_client

    # ── 监视钩子快捷方法 ────────────────────────────────────────────
    def _monitor(self, event: str, detail: str = ""):
        """发送监视钩子到日志系统（不阻塞）。"""
        if self._log_client is not None:
            try:
                self._log_client.monitor(f"updater.{event}", detail)
            except Exception:
                pass
        logger.info(f"[monitor] updater.{event} → {detail}")

    # ═══════════════════════════════════════════════════════════════════
    #  启动检测
    # ═══════════════════════════════════════════════════════════════════

    def check_on_startup(self) -> None:
        """启动时检查：先检查残留暂存（重启状态），再扫描新补丁。"""
        state = read_update_state()
        if state:
            status = state.get("status", "")
            if status == "updating":
                logger.warning("检测到上次未完成的更新")
                self._show_recovery(state)
                return
            elif status == "restarting":
                # 软重启后：显示成功通知并清理
                QTimer.singleShot(1500, lambda: self._show_success_notification(state))
                return
            elif status == "files_replaced":
                # 异常情况：文件已替换但未重启 → 当作重启成功处理
                logger.warning("检测到 files_replaced 残留状态，清理并显示通知")
                QTimer.singleShot(1500, lambda: self._show_success_notification({**state, "status": "restarting"}))
                return

        # 正常扫描补丁
        result = self._checker.scan()
        if result:
            self._current_patch = result
            result["current_version"] = get_config_version()
            QTimer.singleShot(500, lambda: self._show_found_dialog(result))

    def show_manual_install(self) -> None:
        """弹出文件选择对话框让用户手动选择补丁。"""
        from PyQt5.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self._main_window or None,
            "选择更新补丁",
            self._project_root,
            "更新包 (*.zip);;所有文件 (*)",
        )
        if not file_path:
            return

        manifest = read_manifest(file_path)
        if not manifest:
            from components.popup_dialog import CustomDialog
            CustomDialog.error(
                self._main_window, "读取失败",
                f"无法读取补丁的 manifest.json。\n\n文件: {os.path.basename(file_path)}",
            )
            return

        current_ver = get_config_version()
        compatible, error_msg = validate_patch_compatibility(manifest, current_ver)
        if not compatible:
            from components.popup_dialog import CustomDialog
            CustomDialog.error(self._main_window, "版本不兼容", error_msg)
            return

        to_version = manifest.get("to_version", "")
        changes = manifest.get("changes", [])
        result = {
            "patch_filename": os.path.basename(file_path),
            "patch_path": file_path,
            "manifest": manifest,
            "to_version": to_version,
            "release_notes": manifest.get("release_notes", ""),
            "file_stats": {
                "add": sum(1 for c in changes if c["action"] == "add"),
                "modify": sum(1 for c in changes if c["action"] == "modify"),
                "delete": sum(1 for c in changes if c["action"] == "delete"),
            },
            "config_affected": any(
                c["path"].startswith("config/")
                for c in changes if c["action"] in ("add", "modify")
            ),
            "config_files": [
                c["path"] for c in changes
                if c["action"] in ("add", "modify") and c["path"].startswith("config/")
            ],
            "current_version": current_ver,
        }
        self._current_patch = result
        self._show_found_dialog(result)

    # ── 弹窗回调 ────────────────────────────────────────────────────

    def _show_found_dialog(self, patch_info: dict) -> None:
        dlg = UpdateFoundDialog(self._main_window, patch_info=patch_info)
        dlg.update_confirmed.connect(self._on_user_confirmed)
        dlg.exec_()

    def _show_recovery(self, state: dict) -> None:
        dlg = RecoveryDialog(self._main_window, state_info=state)
        dlg.retry_clicked.connect(lambda: self._on_retry_update())
        dlg.ignore_clicked.connect(lambda: self._on_ignore_recovery(state))
        dlg.exec_()

    def _show_success_notification(self, state: dict) -> None:
        new_version = state.get("target_version", "")
        has_backup = state.get("has_backup", False)
        backups = list_backups()
        latest_backup_name = backups[0]["name"] if backups else ""

        toast = UpdateSuccessToast(
            parent=self._main_window,
            new_version=new_version,
            backup_name=latest_backup_name,
            has_backup=has_backup,
        )
        toast.show_toast()
        toast.dismissed.connect(self._cleanup_completed_state)

    # ── 用户操作回调 ────────────────────────────────────────────────

    def _on_user_confirmed(self, info: dict) -> None:
        if self._updating:
            return
        self._updating = True
        self.update_started.emit()

        self._progress_panel = UpdateProgressDialog(self._main_window)
        self._progress_panel.cancelled.connect(self._on_cancelled)
        self._progress_panel.show()

        self._monitor("confirmed", f"用户确认更新: v{info.get('current_version','')} → v{info['to_version']}")
        self._execute_update_steps(info)

    def _on_retry_update(self) -> None:
        state = read_update_state()
        if not state:
            return
        patch_path = state.get("patch_path", "")
        if not patch_path or not os.path.exists(patch_path):
            from components.popup_dialog import CustomDialog
            CustomDialog.error(self._main_window, "补丁不存在",
                               f"原始补丁文件不存在或已被移动:\n{patch_path}")
            return

        manifest = read_manifest(patch_path)
        if not manifest:
            return
        changes = manifest.get("changes", [])
        info = {
            "patch_filename": os.path.basename(patch_path),
            "patch_path": patch_path,
            "manifest": manifest,
            "to_version": manifest.get("to_version", ""),
            "release_notes": manifest.get("release_notes", ""),
            "file_stats": {
                "add": sum(1 for c in changes if c["action"] == "add"),
                "modify": sum(1 for c in changes if c["action"] == "modify"),
                "delete": sum(1 for c in changes if c["action"] == "delete"),
            },
            "config_affected": any(
                c["path"].startswith("config/")
                for c in changes if c["action"] in ("add", "modify")
            ),
            "keep_backup": True,
            "current_version": get_config_version(),
        }

        if self._updating:
            return
        self._updating = True
        self._progress_panel = UpdateProgressDialog(self._main_window)
        self._progress_panel.cancelled.connect(self._on_cancelled)
        self._progress_panel.show()

        self._monitor("confirmed", "重新执行更新")
        self._execute_update_steps(info)

    def _on_ignore_recovery(self, state: dict) -> None:
        clear_restart_flag()
        self._monitor("ignore", "用户忽略并清理了残留更新")

    def _on_cancelled(self) -> None:
        self._updating = False
        self.update_cancelled.emit()
        self._monitor("cancelled", "用户取消更新")
        if self._progress_panel:
            self._progress_panel.close()
            self._progress_panel = None

    # ═══════════════════════════════════════════════════════════════════
    #  核心更新执行流程（同进程直接覆盖版）
    # ═══════════════════════════════════════════════════════════════════

    def _execute_update_steps(self, info: dict) -> None:
        """异步逐步执行更新：校验 → 备份 → 解压 → 覆盖 → 删除 → 清理 → 重启。"""

        def step_0():
            if self._progress_panel:
                self._progress_panel.set_step(0)
            QTimer.singleShot(200, step_1)

        def step_1():
            """校验 SHA256"""
            if not self._validate_sha256(info):
                self._fail_update("SHA256 校验失败，请检查补丁完整性")
                self._monitor("validate", "FAILED - SHA256 不匹配")
                return
            self._monitor("validate", f"通过，{len(info['manifest'].get('changes',[]))} 个文件")
            QTimer.singleShot(100, step_2)

        def step_2():
            """备份 config/"""
            if self._progress_panel:
                self._progress_panel.set_step(1)
            if info.get("config_affected"):
                backup_path = backup_config_dir(get_config_version())
                if backup_path:
                    self._monitor("backup", f"配置已备份至 {os.path.basename(backup_path)}")
                else:
                    self._monitor("backup", "警告：备份失败")
            else:
                self._monitor("backup", "跳过（无 config 变更）")
            QTimer.singleShot(100, step_3)

        def step_3():
            """解压变更文件到暂存区"""
            if self._progress_panel:
                self._progress_panel.set_step(2)
            if not self._extract_to_staging(info):
                self._fail_update("解压更新文件失败")
                self._monitor("extract", "FAILED")
                return
            self._monitor("extract", "解压完成")
            QTimer.singleShot(100, step_4)

        def step_4():
            """直接覆盖文件（同进程）"""
            if self._progress_panel:
                self._progress_panel.set_step(3)
            self._progress_panel.set_custom_status("正在覆盖文件...", 65)

            # ★ 临时移除 config.json 的字段级合并路径，
            #   确保本次更新可以直接覆盖版本号字段。
            #   后续版本将由重启后加载的新版 _merge_json_file
            #   （含 _FORCE_UPDATE_KEYS 白名单）处理合并。
            from workers.updater import update_utils as _uu_mod
            _uu_mod._MERGE_JSON_PATHS.discard("config/config.json")

            staging = get_staging_dir()
            new_files_dir = os.path.join(staging, _NEW_FILES_DIR)

            copied, skipped, applied = apply_new_files(new_files_dir, self._project_root)
            self._monitor("file", f"覆盖 {copied} 个文件，跳过 {skipped} 个")

            # 每文件单独钩子（只记录前 10 个）
            for p in applied[:10]:
                self._monitor("file.op", f"覆盖: {p}")
            if len(applied) > 10:
                self._monitor("file.op", f"... 及另 {len(applied)-10} 个文件")

            # 执行删除
            changes = info["manifest"].get("changes", [])
            delete_paths = [
                c["path"] for c in changes if c["action"] == "delete"
                and not is_excluded_path(c["path"])
            ]
            if delete_paths:
                deleted, failed = execute_deletes(delete_paths, self._project_root)
                self._monitor("delete", f"删除 {deleted} 个文件，{failed} 个失败")
            else:
                self._monitor("delete", "无删除操作")

            QTimer.singleShot(100, step_5)

        def step_5():
            """清理 __pycache__"""
            if self._progress_panel:
                self._progress_panel.set_step(4)
            cleaned = clean_pycache()
            self._monitor("pycache", f"清理 {cleaned} 个 __pycache__ 目录")
            QTimer.singleShot(100, step_6)

        def step_6():
            """写入完成状态 + 触发软重启"""
            if self._progress_panel:
                self._progress_panel.complete()

            state = {
                "status": "files_replaced",   # 标记文件已替换，等待 main_loop 检测
                "target_version": info["to_version"],
                "patch_filename": info.get("patch_filename", ""),
                "patch_path": info.get("patch_path", ""),
                "has_backup": info.get("config_affected", False),
                "has_config_changes": info.get("config_affected", False),
                "started_at": _time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            write_update_state(state)
            self._monitor("restart", f"文件替换完成，准备软重启至 v{info['to_version']}")

            QTimer.singleShot(800, self._trigger_restart)

        step_0()

    # ── 工具方法 ────────────────────────────────────────────────────

    def _validate_sha256(self, info: dict) -> bool:
        """校验补丁 ZIP 内文件的 SHA256。"""
        zip_path = info["patch_path"]
        changes = info["manifest"].get("changes", [])

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()

                for item in changes:
                    action = item["action"]
                    path = item["path"]
                    expected_sha = item.get("sha256", "")

                    if action in ("add", "modify"):
                        zip_entry = f"{_NEW_FILES_DIR}/{path}"
                        if zip_entry not in names:
                            logger.error(f"补丁缺少文件: {zip_entry}")
                            continue

                        tmp_dir = os.path.join(get_staging_dir(), "_tmp_verify")
                        os.makedirs(tmp_dir, exist_ok=True)
                        tmp_file = os.path.join(tmp_dir, os.path.basename(path))

                        try:
                            with zf.open(zip_entry) as src, open(tmp_file, "wb") as dst:
                                dst.write(src.read())

                            from .update_utils import verify_file_hash
                            if not verify_file_hash(tmp_file, expected_sha):
                                return False
                        finally:
                            if os.path.exists(tmp_file):
                                os.remove(tmp_file)

            tmp_dir = os.path.join(get_staging_dir(), "_tmp_verify")
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)
            return True

        except Exception as e:
            logger.error(f"SHA256 校验过程出错: {e}")
            return False

    def _extract_to_staging(self, info: dict) -> bool:
        """解压变更文件到暂存目录。"""
        zip_path = info["patch_path"]
        staging = get_staging_dir()

        try:
            os.makedirs(staging, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                members = [m for m in zf.namelist()
                           if m.startswith(f"{_NEW_FILES_DIR}/")]
                if not members:
                    logger.warning("补丁中没有 new_files/ 内容")
                    return False
                zf.extractall(staging, members=members)
            logger.info(f"已解压到暂存区: {staging}")
            return True
        except Exception as e:
            logger.error(f"解压失败: {e}")
            return False

    def _trigger_restart(self) -> None:
        """标记更新完成、弹出提示并自动关闭应用。

        更新完成后弹出完成对话框，用户点击确定后自动关闭主窗口，
        用户需自行重新打开 StarDebate 以使用新版本。
        """
        from components.popup_dialog import CustomDialog
        logger.info("更新完成 → 弹窗提示 + 自动关闭")

        self._updating = False

        # 关闭进度面板
        if self._progress_panel:
            self._progress_panel.close()
            self._progress_panel = None

        # 在清理前保存目标版本号（清理后会清除状态文件）
        state_before = read_update_state()
        target_version = state_before.get("target_version", "")

        # 清理已完成的状态文件和暂存目录
        self._cleanup_completed_state()

        # ★ 弹出完成对话框，点击确定后自动关闭主窗口
        msg = (
            f"StarDebate 已成功更新至 v{target_version}！\n\n"
            "点击「确定」后将自动关闭软件。\n\n"
            "请重新启动 StarDebate 以使用新版本。"
        )
        CustomDialog.information(
            self._main_window,
            "✨ 更新完成",
            msg,
        )

        # 发出更新完成信号（UI 可据此刷新状态显示）
        self.update_completed.emit()

        # ★ 自动关闭主窗口
        logger.info("自动关闭主窗口")
        if self._main_window:
            self._main_window.close()

    def _fail_update(self, reason: str) -> None:
        """标记更新失败。"""
        self._updating = False
        self._monitor("error", reason)
        if self._progress_panel:
            self._progress_panel.close()
            self._progress_panel = None

        from components.popup_dialog import CustomDialog
        CustomDialog.error(self._main_window, "更新失败", reason)

        clear_restart_flag()
        self.update_cancelled.emit()

    def _cleanup_completed_state(self) -> None:
        """清理已完成的状态文件和暂存目录。"""
        clear_restart_flag()
        self._monitor("done", "更新完成，已清理临时文件")

    # ── 公共接口 ────────────────────────────────────────────────────

    def get_ignored_patches_list(self) -> list[dict]:
        return get_ignored_patches()

    def reenable_patch(self, filename: str) -> bool:
        remove_ignored_patch(filename)
        return True

    def show_ignored_in_settings(self, parent_widget) -> QWidget | None:
        ignored = get_ignored_patches()
        if not ignored:
            return None

        from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel, QHBoxLayout
        from PyQt5.QtGui import QFont
        from components.star_button import StarButton

        container = QFrame()
        container.setObjectName("settingsCard")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        title_lbl = QLabel("已忽略的更新")
        title_lbl.setObjectName("settingsLabel")
        title_lbl.setFont(QFont("Microsoft YaHei", 11))
        layout.addWidget(title_lbl)

        for entry in ignored:
            row = QHBoxLayout()
            row.setSpacing(8)

            name_lbl = QLabel(entry.get("filename", ""))
            name_lbl.setObjectName("settingsValueLabel")
            name_lbl.setMinimumHeight(30)
            row.addWidget(name_lbl, 1)

            btn_reenable = StarButton(
                "重新启用", layout_mode="text_only",
                ratio_h=0.65, auto_size=False,
            )
            btn_reenable.setFixedHeight(28)
            btn_reenable.setFixedWidth(80)
            btn_reenable.setObjectName("settingsSmallBtn")
            fname = entry.get("filename", "")

            def _reenable(f=fname):
                self.reenable_patch(f)
                if hasattr(parent_widget, '_refresh_ignored_list'):
                    parent_widget._refresh_ignored_list()

            btn_reenable.clicked.connect(_reenable)
            row.addWidget(btn_reenable)
            layout.addLayout(row)

        return container
