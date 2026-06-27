"""资源路径统一解析：源码版与 EXE 版共享同一套路径逻辑。

v6.0.0+ 架构中，所有资源（style/、icon/）外置于 EXE 同级目录，
不再打包进 _internal/。本模块提供一个函数 get_resource_root()，
在任何文件中调用它都能得到正确的"资源根目录"。

在源码开发环境中，资源根 = 项目根（src/ 的上级）。
在 EXE 打包环境中，资源根 = sys.executable 所在目录。
"""
import os
import sys

_get_resource_root_cache: str | None = None


def get_resource_root() -> str:
    """获取资源根目录（style/、icon/ 所在的父目录）。"""
    global _get_resource_root_cache
    if _get_resource_root_cache is not None:
        return _get_resource_root_cache

    if getattr(sys, 'frozen', False):
        # EXE 版：所有资源在 EXE 同级目录
        _get_resource_root_cache = os.path.dirname(sys.executable)
    else:
        # 源码版：从 __file__ 向上推 2 级到项目根
        _get_resource_root_cache = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))
    return _get_resource_root_cache


def get_resource_path(relative: str) -> str:
    """获取资源根目录下某文件的完整路径。

    Args:
        relative: 相对于资源根目录的路径，例如 "style/themes/notion_dark/theme.json"
    """
    return os.path.join(get_resource_root(), relative)
