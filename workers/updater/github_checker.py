"""基于 GitHub Releases 的在线更新检查器。

使用 QNetworkAccessManager（PyQt5 内建）异步访问 GitHub API，
支持增量补丁 (patch_*.zip) 和全量安装包 (*Setup.exe) 两种更新类型。

API 地址: https://api.github.com/repos/littlelion-Creeper/StarDebate/releases/latest
"""

from __future__ import annotations

import json
import re
import os
import logging

from PyQt5.QtCore import QObject, pyqtSignal, QUrl
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

logger = logging.getLogger("StarDebate.updater.github")

_GITHUB_API = "https://api.github.com/repos/littlelion-Creeper/StarDebate/releases/latest"
_USER_AGENT = "StarDebate-Updater/1.0"


class GitHubUpdateChecker(QObject):
    """GitHub 更新检查器 — 异步查询/下载。

    Signals:
        update_available(dict):  发现可用更新，参数为 release_info
        up_to_date():            当前已是最新版本
        check_failed(str):       检查过程出错，参数为错误信息
        download_progress(int, int):  下载进度 (received, total)
        download_finished(str):  下载完成，参数为本地文件路径
        download_failed(str):    下载失败，参数为错误信息
    """

    update_available = pyqtSignal(object)  # dict
    up_to_date = pyqtSignal()
    check_failed = pyqtSignal(str)
    download_progress = pyqtSignal(int, int)
    download_finished = pyqtSignal(str)
    download_failed = pyqtSignal(str)

    def __init__(self, current_version: str, parent=None):
        super().__init__(parent)
        self._current_version = current_version
        self._nam = QNetworkAccessManager(self)
        self._nam.finished.connect(self._on_api_response)
        self._download_reply: QNetworkReply | None = None
        self._download_save_path: str = ""
        self._pending_download_url: str = ""

    # ── 公开 API ────────────────────────────────────────────────────────

    def check_for_updates(self) -> None:
        """异步查询 GitHub 最新 Release。"""
        req = QNetworkRequest(QUrl(_GITHUB_API))
        req.setRawHeader(b"User-Agent", _USER_AGENT.encode())
        req.setRawHeader(b"Accept", b"application/vnd.github.v3+json")
        self._nam.get(req)
        logger.info("GitHub 更新检查已发起")

    def download_asset(self, url: str, save_path: str) -> None:
        """异步下载 Release 附件到本地路径。"""
        self._download_save_path = save_path
        self._pending_download_url = url
        dir_name = os.path.dirname(save_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", _USER_AGENT.encode())
        self._download_reply = self._nam.get(req)
        self._download_reply.downloadProgress.connect(self._on_download_progress)
        self._download_reply.finished.connect(self._on_download_finished)
        logger.info("GitHub 下载已发起: %s", os.path.basename(save_path))

    def cancel_download(self) -> None:
        """取消正在进行的下载。"""
        if self._download_reply is not None:
            self._download_reply.abort()
            self._download_reply.deleteLater()
            self._download_reply = None
        if self._download_save_path and os.path.exists(self._download_save_path):
            try:
                os.remove(self._download_save_path)
            except OSError:
                pass
        self._download_save_path = ""
        self._pending_download_url = ""
        logger.info("GitHub 下载已取消")

    # ── API 回调 ────────────────────────────────────────────────────────

    def _on_api_response(self, reply: QNetworkReply) -> None:
        if reply.error() != QNetworkReply.NoError:
            err = reply.errorString()
            # 处理限流
            status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            if status == 403:
                err = "GitHub API 访问频率受限 (60次/小时)，请稍后再试。"
            elif status == 404:
                err = "未找到 GitHub Release 信息，请检查仓库配置。"
            elif status == 0 and "Connection" in err:
                err = "无法连接到 GitHub，请检查网络连接。"
            self.check_failed.emit(f"网络请求失败: {err}")
            logger.warning("GitHub API 请求失败: %s", err)
            reply.deleteLater()
            return

        try:
            data = reply.readAll().data().decode("utf-8")
            release = json.loads(data)
        except Exception as e:
            self.check_failed.emit(f"解析 GitHub 响应失败: {e}")
            logger.error("GitHub API 响应解析失败: %s", e)
            reply.deleteLater()
            return
        finally:
            reply.deleteLater()

        # ── 忽略预发布版本 ────────────────────────────────────────
        if release.get("prerelease", False):
            logger.info("最新 Release 为预发布版本，跳过")
            self.up_to_date.emit()
            return

        tag = release.get("tag_name", "").lstrip("v")
        if not tag:
            self.check_failed.emit("GitHub Release 缺少版本号")
            return

        # ── 版本比对 ──────────────────────────────────────────────
        if self._compare_versions(tag, self._current_version) <= 0:
            logger.info("当前版本 v%s 已是最新 (GitHub: v%s)", self._current_version, tag)
            self.up_to_date.emit()
            return

        # ── 解析附件 ──────────────────────────────────────────────
        assets = release.get("assets", [])
        patch_asset = self._find_asset(assets, r"patch_.*\.zip")
        installer_asset = self._find_asset(assets, r".*Setup\.exe")

        if not patch_asset and not installer_asset:
            self.check_failed.emit("Release 中未找到可识别的更新文件 (patch_*.zip / *Setup.exe)")
            return

        update_type = "patch" if patch_asset else "major"
        info = {
            "tag_name": release.get("tag_name", ""),
            "version": tag,
            "update_type": update_type,
            "release_notes": release.get("body", "暂无更新说明"),
            "html_url": release.get("html_url", ""),
            "published_at": release.get("published_at", ""),
        }

        if patch_asset:
            info["download_url"] = patch_asset["browser_download_url"]
            info["size"] = patch_asset.get("size", 0)
        if installer_asset:
            info["installer_url"] = installer_asset["browser_download_url"]
            info["installer_size"] = installer_asset.get("size", 0)

        logger.info(
            "发现新版本: v%s → v%s (%s, 约 %.1f MB)",
            self._current_version, tag, update_type,
            (info.get("size", 0) + info.get("installer_size", 0)) / 1024 / 1024,
        )
        self.update_available.emit(info)

    # ── 下载回调 ────────────────────────────────────────────────────────

    def _on_download_progress(self, received: int, total: int) -> None:
        self.download_progress.emit(received, total)

    def _on_download_finished(self) -> None:
        if self._download_reply is None:
            return

        if self._download_reply.error() != QNetworkReply.NoError:
            err = self._download_reply.errorString()
            self.download_failed.emit(f"下载失败: {err}")
            logger.error("下载失败: %s", err)
            self._download_reply.deleteLater()
            self._download_reply = None
            return

        try:
            data = self._download_reply.readAll()
            save_path = self._download_save_path
            os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(data)
            logger.info("下载完成: %s (%.1f MB)", save_path, len(data) / 1024 / 1024)
            self.download_finished.emit(save_path)
        except Exception as e:
            self.download_failed.emit(f"保存文件失败: {e}")
            logger.error("保存下载文件失败: %s", e)
        finally:
            self._download_reply.deleteLater()
            self._download_reply = None
            self._pending_download_url = ""

    # ── 工具方法 ────────────────────────────────────────────────────────

    @staticmethod
    def _find_asset(assets: list[dict], pattern: str) -> dict | None:
        """在 Release assets 中匹配指定名称模式的附件。"""
        for asset in assets:
            name = asset.get("name", "")
            if re.search(pattern, name, re.IGNORECASE):
                return asset
        return None

    @staticmethod
    def _compare_versions(v1: str, v2: str) -> int:
        """语义化版本比较。v1 > v2 返回正数，相等返回 0，v1 < v2 返回负数。"""
        try:
            parts1 = [int(x) for x in v1.split(".")]
            parts2 = [int(x) for x in v2.split(".")]
            for a, b in zip(parts1, parts2):
                if a != b:
                    return a - b
            return len(parts1) - len(parts2)
        except (ValueError, AttributeError):
            # 版本格式异常时字符串比较
            return (v1 > v2) - (v1 < v2)
