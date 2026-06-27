# STP 插件包安装器
# 提供 .stp 文件的识别、校验、安装、卸载功能
# 位置：workers/stp_installer/

from .stp_installer import STPInstaller

__all__ = ["STPInstaller"]
