"""配置路径解析：统一处理源码版与 EXE 版的配置目录差异。

在 EXE 版中，PyInstaller 的 sys._MEIPASS 是临时解压目录，
写入的配置文件在重启后会丢失。因此所有可写配置必须保存到
EXE 所在目录（持久位置），而静态资源（样式/字体/图标）仍从打包目录读取。

使用方式：
    from workers.app_config.config_paths import get_config_path, ensure_config_dir

    # 程序启动时调用一次
    ensure_config_dir()

    # 任何读写配置的地方
    path = get_config_path("config/config.json")
"""

import os
import sys
import shutil

_CONFIG_DIR: str | None = None
_PACKAGED_DIR: str | None = None


def _compute_source_base() -> str:
    """源码版：从 __file__ 向上推导项目根目录（与 icon/ 同级）。"""
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))


def get_config_base_dir() -> str:
    """获取持久化配置的基础目录。

    在该目录下应有 'config/' 子目录存放所有 JSON 配置文件。
    """
    global _CONFIG_DIR
    if _CONFIG_DIR is not None:
        return _CONFIG_DIR

    if getattr(sys, 'frozen', False):
        # EXE 版：EXE 所在目录（持久位置）
        _CONFIG_DIR = os.path.dirname(sys.executable)
    else:
        _CONFIG_DIR = _compute_source_base()
    return _CONFIG_DIR


def get_packaged_base_dir() -> str:
    """获取静态资源根目录（样式/字体/图标/默认配置）。

    v6.0.0+ 架构：所有资源外置于 EXE 同级目录，不再打包进 _internal/。
    """
    global _PACKAGED_DIR
    if _PACKAGED_DIR is not None:
        return _PACKAGED_DIR

    if getattr(sys, 'frozen', False):
        # v6.0.0+：资源在 EXE 同级目录（外置，非 _MEIPASS）
        _PACKAGED_DIR = os.path.dirname(sys.executable)
    else:
        _PACKAGED_DIR = _compute_source_base()
    return _PACKAGED_DIR


def get_config_path(relative: str) -> str:
    """获取持久化配置文件的完整路径。

    Args:
        relative: 相对于配置基础目录的路径，例如 "config/config.json"

    Returns:
        该文件的绝对路径
    """
    return os.path.join(get_config_base_dir(), relative)


def get_packaged_path(relative: str) -> str:
    """获取打包目录下文件的完整路径。

    Args:
        relative: 相对于打包基础目录的路径，例如 "style/themes/..."

    Returns:
        该文件的绝对路径
    """
    return os.path.join(get_packaged_base_dir(), relative)


def ensure_config_dir() -> None:
    """确保持久化配置目录存在。

    首次启动时（持久 config/ 目录为空或不存在的场景），
    自动将打包目录中的默认配置文件复制过去。
    后续启动不再重复复制，已修改的配置不会被覆盖。
    """
    config_dir = os.path.join(get_config_base_dir(), "config")
    os.makedirs(config_dir, exist_ok=True)

    # 从打包目录复制默认配置（仅首次）
    packaged_config_dir = os.path.join(get_packaged_base_dir(), "config")
    if os.path.isdir(packaged_config_dir):
        for fname in os.listdir(packaged_config_dir):
            if fname.endswith('.json') or fname.startswith('.api_key'):
                target = os.path.join(config_dir, fname)
                if not os.path.exists(target):
                    src = os.path.join(packaged_config_dir, fname)
                    try:
                        shutil.copy2(src, target)
                    except Exception:
                        pass
