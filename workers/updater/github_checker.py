"""基于 GitHub Releases 的在线更新检查器（链式补丁版）。

使用 QNetworkAccessManager（PyQt5 内建）异步访问 GitHub 的 Releases List API，
获取所有 Release 的 patch_*.zip 附件，自动构建从当前版本到最新版本的补丁链，
支持串联下载和顺序安装。

API: GET /repos/Chapin-Y/StarDebate/releases?per_page=30
"""

from __future__ import annotations

import json
import re
import os
import logging

from PyQt5.QtCore import QObject, pyqtSignal, QUrl
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

logger = logging.getLogger("StarDebate.updater.github")

_GITHUB_LIST_API = "https://api.github.com/repos/Chapin-Y/StarDebate/releases"
_USER_AGENT = "StarDebate-Updater/1.0"


class GitHubUpdateChecker(QObject):
    """GitHub 更新检查器 — 链式补丁版。

    查询所有 Release → 提取 patch_*.zip → 构建从当前版本到最新的补丁链。
    支持串联下载多个补丁到暂存目录。

    Signals:
        update_chain_available(list[dict]):  发现可用补丁链
        up_to_date():                        当前已是最新版本
        check_failed(str):                   检查过程出错
        download_progress(int, int):         单个文件下载进度 (received, total)
        chain_download_progress(int, int):   链式下载进度 (current_index, total_count)
        download_finished(str):              单个文件下载完成，参数为本地路径
        chain_download_finished(list[str]):  链式全部下载完成，参数为本地路径列表
        download_failed(str):                下载失败，参数为错误信息
    """

    update_chain_available = pyqtSignal(object)  # list[dict]
    up_to_date = pyqtSignal()
    check_failed = pyqtSignal(str)
    download_progress = pyqtSignal(int, int)          # (received, total)
    chain_download_progress = pyqtSignal(int, int)    # (current_idx, total_count)
    download_finished = pyqtSignal(str)               # 单个文件路径
    chain_download_finished = pyqtSignal(object)      # list[str] 全部路径
    download_failed = pyqtSignal(str)

    def __init__(self, current_version: str, parent=None):
        super().__init__(parent)
        self._current_version = current_version
        self._nam = QNetworkAccessManager(self)
        self._nam.finished.connect(self._on_api_response)
        self._download_reply: QNetworkReply | None = None
        self._download_save_path: str = ""

        # 链式下载状态
        self._chain: list[dict] = []
        self._chain_idx: int = 0
        self._chain_save_paths: list[str] = []
        self._staging_dir: str = ""

    # ── 公开 API ────────────────────────────────────────────────────────

    def check_for_updates(self) -> None:
        """异步查询所有 Release，构建补丁链。"""
        req = QNetworkRequest(QUrl(_GITHUB_LIST_API + "?per_page=30"))
        req.setRawHeader(b"User-Agent", _USER_AGENT.encode())
        req.setRawHeader(b"Accept", b"application/vnd.github.v3+json")
        try:
            req.setAttribute(
                QNetworkRequest.RedirectPolicyAttribute,
                QNetworkRequest.NoLessSafeRedirectPolicy,
            )
        except AttributeError:
            pass
        self._nam.get(req)
        logger.info("GitHub 链式更新检查已发起")

    def download_asset(self, url: str, save_path: str) -> None:
        """异步下载单个 Release 附件到本地路径。"""
        self._download_save_path = save_path
        dir_name = os.path.dirname(save_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", _USER_AGENT.encode())
        self._download_reply = self._nam.get(req)
        self._download_reply.downloadProgress.connect(self._on_download_progress)
        self._download_reply.finished.connect(self._on_download_finished)
        logger.info("GitHub 下载已发起: %s", os.path.basename(save_path))

    def download_chain(self, chain: list[dict], staging_dir: str) -> None:
        """串联下载补丁链到暂存目录。

        Args:
            chain: 补丁链列表，每个元素含 version/download_url/size
            staging_dir: 暂存目录路径（每个补丁下载为 patch_vX_to_vY.zip）
        """
        self._chain = chain
        self._chain_idx = 0
        self._chain_save_paths = []
        self._staging_dir = staging_dir
        os.makedirs(staging_dir, exist_ok=True)
        logger.info("GitHub 链式下载启动: %d 个补丁", len(chain))
        self._download_next_in_chain()

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
        # 清理已下载的链文件
        for p in self._chain_save_paths:
            try:
                os.remove(p)
            except OSError:
                pass
        self._chain_save_paths = []
        self._chain = []
        self._chain_idx = 0
        logger.info("GitHub 链式下载已取消")

    # ── 链式下载编排 ────────────────────────────────────────────────────

    def _download_next_in_chain(self) -> None:
        """下载链中的下一个补丁。"""
        if self._chain_idx >= len(self._chain):
            # 全部下载完成
            self.chain_download_finished.emit(self._chain_save_paths)
            return

        entry = self._chain[self._chain_idx]
        version = entry.get("version", "unknown")
        url = entry.get("download_url", "")
        if not url:
            self.download_failed.emit(f"补丁 v{version} 缺少下载地址")
            return

        # 构造带版本信息的文件名
        save_name = f"patch_v{self._current_version}_to_v{version}.zip"
        if self._chain_idx > 0:
            prev_ver = self._chain[self._chain_idx - 1].get("version", "")
            save_name = f"patch_v{prev_ver}_to_v{version}.zip"

        save_path = os.path.join(self._staging_dir, save_name)

        self.chain_download_progress.emit(self._chain_idx + 1, len(self._chain))
        logger.info(
            "链式下载 [%d/%d]: %s → v%s",
            self._chain_idx + 1, len(self._chain),
            self._current_version if self._chain_idx == 0 else self._chain[self._chain_idx - 1]["version"],
            version,
        )
        self.download_asset(url, save_path)

    # ── API 回调 ────────────────────────────────────────────────────────

    def _on_api_response(self, reply: QNetworkReply) -> None:
        if reply.error() != QNetworkReply.NoError:
            err = reply.errorString()
            status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            if status == 403:
                err = "GitHub API 访问频率受限 (60次/小时)，请稍后再试。"
            elif status == 404:
                err = "GitHub 仓库暂无已发布的版本。"
            elif status == 0 and "Connection" in err:
                err = "无法连接到 GitHub，请检查网络连接。"
            self.check_failed.emit(f"网络请求失败: {err}")
            logger.warning("GitHub API 请求失败: %s", err)
            reply.deleteLater()
            return

        try:
            data = reply.readAll().data().decode("utf-8")
            releases = json.loads(data)
        except Exception as e:
            self.check_failed.emit(f"解析 GitHub 响应失败: {e}")
            logger.error("GitHub API 响应解析失败: %s", e)
            reply.deleteLater()
            return
        finally:
            reply.deleteLater()

        # ── 检查是否为 Releases List（数组） ──────────────────────
        if isinstance(releases, dict):
            msg = releases.get("message", "")
            if msg:
                self.check_failed.emit(f"GitHub API 返回: {msg}")
                return
            self.check_failed.emit("GitHub API 返回了非预期的响应格式")
            return

        if not isinstance(releases, list):
            self.check_failed.emit("GitHub API 响应格式异常")
            return

        # ── 构建补丁链 ──────────────────────────────────────────────
        chain = self._build_update_chain(releases)
        if chain is None:
            # 没有可用的更新补丁
            latest_tag = self._find_latest_tag(releases)
            if latest_tag and self._compare_versions(latest_tag, self._current_version) <= 0:
                self.up_to_date.emit()
            else:
                self.check_failed.emit(
                    "没有找到可用的增量补丁 (patch_*.zip)，"
                    "请访问 GitHub Releases 页面手动下载。"
                )
            return

        # ── 检查是否所有补丁均已被忽略 ────────────────────────────
        # (忽略检查在 manager 层完成，此处直接发射)
        logger.info(
            "发现补丁链: %d 个补丁 (%s → ... → v%s)",
            len(chain),
            self._current_version,
            chain[-1]["version"],
        )
        self.update_chain_available.emit(chain)

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
            qba = self._download_reply.readAll()
            save_path = self._download_save_path
            os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
            # 显式转换为 bytes，避免 PyQt5 QByteArray buffer 协议在 Python 3.12+ 下的边界问题
            raw_bytes = qba.data() if hasattr(qba, 'data') else bytes(qba)
            if not raw_bytes:
                raise ValueError("下载数据为空")
            with open(save_path, "wb") as f:
                f.write(raw_bytes)
            logger.info("下载完成: %s (%.1f MB)", save_path, len(raw_bytes) / 1024 / 1024)
            self.download_finished.emit(save_path)

            # 如果是链式下载进行中，触发下一个
            self._chain_save_paths.append(save_path)
            self._chain_idx += 1
            self._download_next_in_chain()
        except Exception as e:
            self.download_failed.emit(f"保存文件失败: {e}")
            logger.error("保存下载文件失败: %s", e)
        finally:
            self._download_reply.deleteLater()
            self._download_reply = None

    # ── 补丁链构建 ──────────────────────────────────────────────────────

    def _build_update_chain(self, releases: list[dict]) -> list[dict] | None:
        """从 Release 列表中构建从当前版本到最新版本的补丁链。

        规则：
        - 跳过预发布版本
        - 每个 Release 必须包含 patch_*.zip 附件
        - 按版本号升序排列
        - 只保留版本 > 当前版本的 Release

        Returns:
            排序后的补丁链列表，无可用链返回 None
        """
        valid: list[dict] = []
        for r in releases:
            if r.get("prerelease", False):
                continue
            tag = r.get("tag_name", "").lstrip("v")
            if not tag:
                continue
            assets = r.get("assets", [])
            patch_asset = self._find_asset(assets, r"patch_.*\.zip")
            if not patch_asset:
                continue

            valid.append({
                "tag_name": r.get("tag_name", ""),
                "version": tag,
                "download_url": patch_asset["browser_download_url"],
                "size": patch_asset.get("size", 0),
                "release_notes": r.get("body", "暂无更新说明"),
                "html_url": r.get("html_url", ""),
                "published_at": r.get("published_at", ""),
            })

        if not valid:
            return None

        # 按版本号升序排列
        def _version_key(v: str) -> list:
            parts = re.split(r"[.\-]", v)
            nums = []
            for p in parts:
                try:
                    nums.append(int(p))
                except ValueError:
                    nums.append(0)
            return nums

        valid.sort(key=lambda x: _version_key(x["version"]))

        # 筛选 > 当前版本的版本
        chain = [v for v in valid if self._compare_versions(v["version"], self._current_version) > 0]
        return chain if chain else None

    @staticmethod
    def _find_latest_tag(releases: list[dict]) -> str:
        """从 Release 列表中找最新版本的 tag（不含 v 前缀）。"""
        tags = []
        for r in releases:
            if r.get("prerelease", False):
                continue
            tag = r.get("tag_name", "").lstrip("v")
            if tag:
                tags.append(tag)
        if not tags:
            return ""
        from .update_utils import compare_versions
        tags.sort(key=lambda t: [int(x) for x in re.split(r"[.\-]", t) if x.isdigit()], reverse=True)
        return tags[0]

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
            return (v1 > v2) - (v1 < v2)
