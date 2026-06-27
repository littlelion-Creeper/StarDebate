"""ChromiumChecker — Chromium 浏览器检测与自动下载

Chromium 作为可选扩展包，按需从仓库下载，不随主安装包分发。
"""

import logging
import os
import subprocess
import sys
from typing import Optional, Callable

_logger = logging.getLogger("StarDebate.web_ai.chromium_checker")

# Chromium 默认下载 URL（可配置）
DEFAULT_CHROMIUM_DOWNLOAD_URL = (
    "https://playwright.azureedge.net/builds/chromium/1155/chromium-win64.zip"
)

# Playwright 本地浏览器缓存路径模式
def _get_playwright_browsers_path() -> str:
    """获取 Playwright 浏览器缓存目录"""
    # 优先检查环境变量
    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if env_path:
        return env_path
    # Windows 默认路径
    if sys.platform == "win32":
        return os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
    # macOS
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Caches/ms-playwright")
    # Linux
    return os.path.expanduser("~/.cache/ms-playwright")


class ChromiumChecker:
    """Chromium 检测与安装管理"""

    def __init__(self):
        self._chromium_path: Optional[str] = None
        self._playwright_installed: Optional[bool] = None

    # ── 检测 ──

    def is_playwright_installed(self) -> bool:
        """检测 playwright Python 包是否安装"""
        if self._playwright_installed is not None:
            return self._playwright_installed

        try:
            import playwright
            _ = playwright.__version__
            self._playwright_installed = True
        except ImportError:
            self._playwright_installed = False
        return self._playwright_installed

    def is_chromium_installed(self) -> bool:
        """检测 Chromium 浏览器是否已安装（Playwright 管理的）"""
        if self._chromium_path and os.path.exists(self._chromium_path):
            return True

        # 尝试通过 playwright 命令检测
        try:
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
                capture_output=True,
                timeout=15,
            )
            stdout = result.stdout.decode("utf-8", errors="replace")
            if "Downloading" in stdout or "downloading" in stdout.lower():
                self._chromium_path = None
                return False

            # 查找 chromium 可执行文件
            path = self._find_chromium_exe()
            if path:
                self._chromium_path = path
                return True
        except Exception as e:
            _logger.debug(f"Chromium 检测异常: {e}")

        return False

    def get_chromium_path(self) -> Optional[str]:
        """获取 Chromium 可执行文件路径"""
        if self._chromium_path:
            return self._chromium_path
        return self._find_chromium_exe()

    def get_chromium_version(self) -> str:
        """获取已安装 Chromium 版本号"""
        path = self.get_chromium_path()
        if not path:
            return ""
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True,
                timeout=5,
            )
            return result.stdout.decode("utf-8", errors="replace").strip()
        except Exception:
            return ""

    # ── 安装 ──

    def install_playwright(self, on_progress: Callable[[float, str], None] = None) -> bool:
        """安装 Playwright Python 包

        Args:
            on_progress: 进度回调 (0.0~1.0, status_text)

        Returns:
            True 安装成功
        """
        if self.is_playwright_installed():
            if on_progress:
                on_progress(1.0, "Playwright 已安装")
            return True

        try:
            if on_progress:
                on_progress(0.1, "正在安装 Playwright...")

            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "playwright"],
                capture_output=True,
                timeout=120,
            )
            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""

            if result.returncode != 0:
                _logger.error(f"Playwright 安装失败: {stderr}")
                if on_progress:
                    on_progress(0.0, f"安装失败: {stderr[:100]}")
                return False

            self._playwright_installed = True
            if on_progress:
                on_progress(0.5, "Playwright 安装完成")
            return True

        except subprocess.TimeoutExpired:
            _logger.error("Playwright 安装超时")
            if on_progress:
                on_progress(0.0, "安装超时")
            return False
        except Exception as e:
            _logger.error(f"Playwright 安装异常: {e}")
            if on_progress:
                on_progress(0.0, f"安装异常: {e}")
            return False

    def install_chromium(self, on_progress: Callable[[float, str], None] = None) -> bool:
        """安装 Chromium 浏览器（通过 playwright install）

        Args:
            on_progress: 进度回调 (0.0~1.0, status_text)

        Returns:
            True 安装成功
        """
        if self.is_chromium_installed():
            if on_progress:
                on_progress(1.0, "Chromium 已安装")
            return True

        if not self.is_playwright_installed():
            if on_progress:
                on_progress(0.0, "请先安装 Playwright")
            return False

        try:
            if on_progress:
                on_progress(0.0, "正在下载 Chromium（~130MB）...")

            process = subprocess.Popen(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )

            output_lines = []
            for raw_line in process.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                output_lines.append(line)
                _logger.debug(f"Chromium install: {line.strip()}")

                # 尝试从输出推断进度
                if "Downloading" in line:
                    if on_progress:
                        on_progress(0.1, "下载中...")
                elif "chromium" in line.lower() and "%" in line:
                    try:
                        pct_str = line.split("%")[0].split()[-1]
                        pct = float(pct_str) / 100.0
                        if on_progress:
                            on_progress(max(0.1, min(0.9, pct)), f"下载中 {pct_str}%")
                    except Exception:
                        pass

            process.wait(timeout=300)

            if process.returncode == 0:
                self._chromium_path = self._find_chromium_exe()
                if on_progress:
                    on_progress(1.0, "Chromium 安装完成")
                return True
            else:
                _logger.error(f"Chromium 安装失败")
                if on_progress:
                    on_progress(0.0, "安装失败")
                return False

        except subprocess.TimeoutExpired:
            _logger.error("Chromium 安装超时")
            if on_progress:
                on_progress(0.0, "安装超时")
            return False
        except Exception as e:
            _logger.error(f"Chromium 安装异常: {e}")
            if on_progress:
                on_progress(0.0, f"安装异常: {e}")
            return False

    def is_chromium_installed_fast(self) -> bool:
        """轻量检测 Chromium 是否已安装（仅扫文件系统，不调用子进程）

        适用于设置页等频繁刷新场景，不阻塞 UI。
        """
        if self._chromium_path and os.path.exists(self._chromium_path):
            return True
        path = self._find_chromium_exe()
        if path:
            self._chromium_path = path
            return True
        return False

    # ── 内部方法 ──

    def _find_chromium_exe(self) -> Optional[str]:
        """在 Playwright 缓存目录中查找 chromium 可执行文件"""
        browsers_path = _get_playwright_browsers_path()
        if not browsers_path or not os.path.isdir(browsers_path):
            return None

        # 遍历查找 chromium 目录
        for root, dirs, files in os.walk(browsers_path):
            for d in dirs:
                if "chromium" in d.lower():
                    chromium_dir = os.path.join(root, d)
                    # Windows: chrome.exe, Linux/macOS: chrome
                    for exe_name in ["chrome.exe", "chrome"]:
                        for sub_root, sub_dirs, sub_files in os.walk(chromium_dir):
                            if exe_name in sub_files:
                                return os.path.join(sub_root, exe_name)
        return None


# 全局单例
_chromium_checker: Optional[ChromiumChecker] = None


def get_chromium_checker() -> ChromiumChecker:
    global _chromium_checker
    if _chromium_checker is None:
        _chromium_checker = ChromiumChecker()
    return _chromium_checker
