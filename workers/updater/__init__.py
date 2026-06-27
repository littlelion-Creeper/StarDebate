"""StarDebate 更新器模块

提供本地增量补丁更新功能：
  - 启动时自动检测根目录补丁文件
  - 手动选择补丁文件安装
  - 版本校验 + SHA256 完整性校验
  - 配置全量备份（保留最近 2 次）
  - 独立进程执行文件替换 + 重启

文件结构：
  workers/updater/
  ├── __init__.py              (本文件)
  ├── update_utils.py          (共享工具函数)
  ├── update_checker.py        (启动时自动检测逻辑)
  ├── update_manager.py        (主进程侧管理器：UI触发、校验、备份、暂存)
  ├── update_patch_applier.py  (更新进程执行脚本，稳定不动)
  └── update_dialogs.py        (UI 对话框组件)

样式表：style/themes/<theme>/updater.qss

使用示例:
    from workers.updater import UpdateManager
    mgr = UpdateManager(main_window)
    mgr.check_on_startup()          # 启动时自动检测
    mgr.show_manual_install_dialog() # 手动选择补丁
"""

from .update_utils import (
    get_project_root,
    get_config_version,
    compare_versions,
    compute_sha256,
    get_staging_dir,
    get_backups_dir,
    get_update_state_path,
    read_update_state,
    write_update_state,
    clean_pycache,
    read_manifest,
    validate_patch_compatibility,
    backup_config_dir,
    restore_config_from_backup,
    cleanup_old_backups,
    add_ignored_patch,
    remove_ignored_patch,
    get_ignored_patches,
    load_ignore_list,
    save_ignore_list,
)

from .update_checker import UpdateChecker
from .update_manager import UpdateManager
from .update_dialogs import (
    UpdateFoundDialog,
    UpdateProgressDialog,
    UpdateSuccessToast,
    RecoveryDialog,
)
# GitHub 更新器通过 update_manager 内延迟导入，
# 避免 EXE 下 PyQt5.QtNetwork 未打包导致的模块级崩溃。
