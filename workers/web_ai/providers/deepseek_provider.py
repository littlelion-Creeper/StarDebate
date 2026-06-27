"""DeepSeekProvider — DeepSeek Chat 网页版 Provider

通过 Playwright headless 模拟浏览器使用 chat.deepseek.com。
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional

from workers.web_ai.providers.base_provider import (
    BaseWebAIProvider,
    ProviderError,
    SessionExpiredError,
    TimeoutError,
    SelectorChangedError,
)

_logger = logging.getLogger("StarDebate.web_ai.deepseek_provider")

# ── 选择器常量（多备选，应对页面结构变化） ──

# 文本输入框
SELECTORS_INPUT = [
    'div[contenteditable="true"]',
    '[contenteditable="true"]',
    'textarea[placeholder*="发送消息"]',
    'textarea[placeholder*="消息"]',
    'textarea[placeholder*="message"]',
    '#chat-input',
    'textarea.chat-input',
    'textarea',
    'textarea[name="search"]',           # 兜底（也可能是搜索框）
]

# 发送按钮 — 优先 JS 点击，CSS 选择器列在这里仅作备选
SELECTORS_SEND = [
    '[class*="ds-button"]',
    'div:has(.ds-button__background)',
    'span:has(.ds-button__background)',
    'button.ds-button',
    'button[aria-label*="发送"]',
    'button[aria-label*="send"]',
    'button:has(svg)',
    '.send-btn',
    'button[class*="send"]',
]

# 停止生成按钮（回复中可见）— 为了兼容用 CSS 选择器查找，实际使用 JS 匹配 SVG path
SELECTORS_STOP = [
    'div:has-text("停止")',
    'span:has-text("停止")',
    'button:has-text("停止")',
    'button[aria-label*="停止"]',
    'button[aria-label*="stop"]',
    '.stop-btn',
    '[class*="stop"]',
    '[class*="pause"]',
]

# 停止按钮 SVG path（正方形图标），用于 JS 精确定位
_STOP_SVG_PATH = "M2 4.88C2 3.68009 2 3.08013 2.30557 2.65954C2.40426 2.52371 2.52371 2.40426 2.65954 2.30557C3.08013 2 3.68009 2 4.88 2H11.12C12.3199 2 12.9199 2 13.3405 2.30557C13.4763 2.40426 13.5957 2.52371 13.6944 2.65954C14 3.08013 14 3.68009 14 4.88V11.12C14 12.3199 14 12.9199 13.6944 13.3405C13.5957 13.4763 13.4763 13.5957 13.3405 13.6944C12.9199 14 12.3199 14 11.12 14H4.88C3.68009 14 3.08013 14 2.65954 13.6944C2.52371 13.5957 2.40426 13.4763 2.30557 13.3405C2 12.9199 2 12.3199 2 11.12V4.88Z"

# AI 回复容器
SELECTORS_RESPONSE = [
    '.ds-markdown:last-of-type',
    '.ds-markdown',
    '.message.assistant:last-child',
    '.chat-message.assistant:last-child',
    '[data-role="assistant"]:last-child',
    'div[class*="message"]:last-child',
]

# 登录页面标识
SELECTORS_LOGIN_PAGE = [
    'input[type="password"]',
    'button:has-text("登录")',
    'button:has-text("Log in")',
    '.login-form',
]

# 会话过期提示
SELECTORS_SESSION_EXPIRED = [
    'text=登录已过期',
    'text=重新登录',
    'text=session expired',
    'text=请登录',
]


class DeepSeekProvider(BaseWebAIProvider):
    provider_id = "deepseek"
    provider_name = "DeepSeek Chat"

    CHAT_URL = "https://chat.deepseek.com/"

    def __init__(self):
        super().__init__()
        self._browser = None
        self._context = None
        self._page = None
        self._headless = True

    # ── Playwright 引擎管理 ──

    def _get_playwright(self):
        """延迟导入 Playwright，避免未安装时崩溃"""
        try:
            from playwright.sync_api import sync_playwright
            return sync_playwright
        except ImportError:
            raise ProviderError(
                "Playwright 未安装。请运行: pip install playwright && playwright install chromium"
            )

    def _launch_browser(self, headless: bool = True):
        """启动 Chromium 浏览器实例"""
        sync_playwright = self._get_playwright()
        self._headless = headless
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

    def _close_browser(self):
        """关闭浏览器实例"""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if hasattr(self, "_playwright") and self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._page = None
        self._context = None

    def _new_page(self, state_path: Optional[str] = None):
        """创建新的浏览器上下文和页面"""
        context_kwargs = {"viewport": {"width": 1280, "height": 800}}
        if state_path and os.path.exists(state_path):
            context_kwargs["storage_state"] = state_path

        self._context = self._browser.new_context(**context_kwargs)
        self._page = self._context.new_page()

    # ── 登录 ──

    def login(self, state_path: str) -> bool:
        """打开可见浏览器让用户手动登录 DeepSeek Chat

        Args:
            state_path: storage_state 保存路径

        Returns:
            True 登录成功
        """
        try:
            self._launch_browser(headless=False)
            self._new_page()

            _logger.info("打开 DeepSeek Chat 登录页面...")
            self._page.goto(self.CHAT_URL, wait_until="networkidle", timeout=30000)

            # 等待用户手动完成登录（检测到输入框或聊天界面即认为完成）
            _logger.info("等待用户登录... 请在浏览器中完成登录操作")

            try:
                # 最多等 5 分钟
                self._page.wait_for_selector(
                    'textarea, [contenteditable="true"]',
                    timeout=300000,
                )
            except Exception:
                _logger.warning("登录等待超时，尝试保存当前状态")

            # 检查是否在登录页
            if self._detect_login_page():
                _logger.warning("仍在登录页面，登录可能未完成")
                self._close_browser()
                return False

            # 保存 session 状态
            self._page.context.storage_state(path=state_path)
            _logger.info(f"Session 已保存至: {state_path}")

            self._close_browser()
            return True

        except Exception as e:
            _logger.error(f"登录过程出错: {e}", exc_info=True)
            self._close_browser()
            return False

    def try_auto_login(self, state_path: str) -> bool:
        """自动登录：先 headless 检测 session，无效则弹出浏览器让用户手动登录

        Returns:
            True 登录成功
        """
        # Phase 1: headless 检测已有 session 是否仍有效
        try:
            self._launch_browser(headless=True)
            self._new_page(state_path)
            self._page.goto(self.CHAT_URL, wait_until="networkidle", timeout=15000)
            if not self._detect_login_page():
                # session 仍然有效，刷新保存时间戳
                self._page.context.storage_state(path=state_path)
                self._close_browser()
                _logger.info("已有 session 仍有效，无需重新登录")
                return True
        except Exception:
            pass
        self._close_browser()

        # Phase 2: session 过期 → 弹出可见浏览器让用户手动登录
        _logger.info("Session 已过期，弹出浏览器让用户手动登录")
        return self.login(state_path)

    def is_authenticated(self, state_path: str) -> bool:
        """检查 storage_state 是否可用（仅文件检测，不启动 Chrome）

        Session 文件有效期约 30 天，超过此期限需要重新登录验证。
        注意：本方法不再启动 Chrome 浏览器，仅检查文件是否存在且未过期。
        精确的 session 有效性验证由 try_auto_login() 的 headless 阶段完成。
        """
        if not state_path or not os.path.exists(state_path):
            return False
        # Session 文件保存后 30 天内视为有效
        mtime = os.path.getmtime(state_path)
        age_days = (time.time() - mtime) / 86400
        return age_days < 30

    def logout(self, state_path: str):
        if state_path and os.path.exists(state_path):
            try:
                os.remove(state_path)
                _logger.info(f"已删除 session 文件: {state_path}")
            except OSError as e:
                _logger.warning(f"删除 session 文件失败: {e}")

    # ── 对话 ──

    def chat(self, state_path: str, payload: dict, timeout: int = 60) -> str:
        """发送消息到 DeepSeek Chat 网页并获取回复"""
        if not os.path.exists(state_path):
            raise SessionExpiredError("未找到登录状态，请先登录 DeepSeek 网页版")

        input_text = self.translate_payload(payload)

        try:
            self._launch_browser(headless=True)
            self._new_page(state_path)

            # 导航到 DeepSeek Chat
            self._page.goto(self.CHAT_URL, wait_until="networkidle", timeout=15000)

            # 检测 session 过期
            if self._detect_login_page():
                raise SessionExpiredError("Session 已过期，请重新登录 DeepSeek 网页版")

            # 等待聊天界面加载
            self._page.wait_for_load_state("networkidle")

            # 找到输入框并输入
            input_elem = self._find_element(SELECTORS_INPUT, "text input")
            if not input_elem:
                raise SelectorChangedError("找不到输入框，DeepSeek 网页结构可能已变化")

            input_elem.click()
            input_elem.fill(input_text)

            # 记录发送前的回复区域状态（用于后续提取新回复）
            try:
                pre_elements = self._page.query_selector_all(
                    '.message, .chat-message, [data-role="assistant"], .ds-markdown'
                )
                pre_count = len(pre_elements)
            except Exception:
                pre_count = 0

            # 点击发送 — 优先 JS 找按钮并点击（避免 Enter 触发搜索）
            _logger.info("尝试发送消息...")
            sent = self._js_send_message(input_elem)
            if not sent:
                # 全失败 → press Enter 兜底
                input_elem.press("Enter")
            time.sleep(1)

            # ── 等待回复完成 ──
            content = self._wait_for_response(timeout, pre_count)

            # 等待 Playwright 内部 async task 完成后再关闭连接
            # 避免 "Task exception was never retrieved: TargetClosedError"
            time.sleep(0.15)
            self._close_browser()
            return content

        except (SessionExpiredError, TimeoutError, SelectorChangedError):
            time.sleep(0.15)
            self._close_browser()
            raise
        except Exception as e:
            _logger.error(f"Web AI 调用异常: {e}", exc_info=True)
            time.sleep(0.15)
            self._close_browser()
            raise ProviderError(f"Web AI 调用失败: {e}")

    # ── 内部工具方法 ──

    def _js_send_message(self, input_elem) -> bool:
        """用 JavaScript 在页面中查找发送按钮并点击

        Returns:
            True 表示成功点击
        """
        try:
            return self._page.evaluate("""() => {
                // 发送按钮的特有 SVG path（上传箭头图标）
                const SEND_PATH = 'M8.3125 0.981587C8.66767 1.0545 8.97902 1.20558 9.2627 1.43374C9.48724 1.61438 9.73029 1.85933 9.97949 2.10854L14.707 6.83608L13.293 8.25014L9 3.95717V15.0431H7V3.95717L2.70703 8.25014L1.29297 6.83608L6.02051 2.10854C6.26971 1.85933 6.51277 1.61438 6.7373 1.43374C6.97662 1.24126 7.28445 1.04542 7.6875 0.981587C7.8973 0.94841 8.1031 0.956564 8.3125 0.981587Z';

                // 1. 精确匹配：找到包含发送图标的按钮
                const allSvgs = document.querySelectorAll('svg path');
                for (const path of allSvgs) {
                    if (path.getAttribute('d') === SEND_PATH) {
                        const btn = path.closest('.ds-button, button, [role="button"]');
                        if (btn && btn.offsetParent !== null) {
                            btn.click();
                            return true;
                        }
                    }
                }

                // 2. 兜底：找 .ds-button__background 的父元素
                const bg = document.querySelector('.ds-button__background');
                if (bg && bg.parentElement && bg.parentElement.offsetParent !== null) {
                    bg.parentElement.click();
                    return true;
                }

                // 3. 最后兜底：press Enter
                const ta = document.querySelector('textarea');
                if (ta) {
                    ta.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', keyCode: 13, which: 13}));
                    return true;
                }
                return false;
            }""")
        except Exception:
            return False

    def _find_element(self, selectors: list, label: str = "element"):
        """尝试多个选择器找到页面元素"""
        for sel in selectors:
            try:
                elem = self._page.query_selector(sel)
                if elem and elem.is_visible():
                    return elem
            except Exception:
                continue
        _logger.warning(f"找不到元素({label}): tried {selectors}")
        # 首次找不到时截图保存，辅助调试页面结构变化
        try:
            _debug_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".debug_webai")
            os.makedirs(_debug_dir, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            self._page.screenshot(path=os.path.join(_debug_dir, f"debug_{label}_{ts}.png"))
            _logger.info(f"已保存调试截图至 .debug_webai/debug_{label}_{ts}.png")
        except Exception:
            pass
        return None

    def _detect_login_page(self) -> bool:
        """检测当前是否在登录页面"""
        for sel in SELECTORS_LOGIN_PAGE:
            try:
                elem = self._page.query_selector(sel)
                if elem and elem.is_visible():
                    return True
            except Exception:
                continue
        # 也检测会话过期提示
        for sel in SELECTORS_SESSION_EXPIRED:
            try:
                if self._page.locator(sel).count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _js_is_generating(self) -> bool:
        """用 JS 检查页面是否正在生成回复（通过停止按钮的 SVG icon）"""
        try:
            return self._page.evaluate(f"""() => {{
                const paths = document.querySelectorAll('svg path');
                const target = '{_STOP_SVG_PATH}';
                for (const p of paths) {{
                    if (p.getAttribute('d') === target) return true;
                }}
                return false;
            }}""")
        except Exception:
            return False

    def _wait_for_response(self, timeout: int, pre_count: int = 0) -> str:
        """等待 AI 回复完成并提取文本。

        策略：
        1. 等待停止按钮消失 / 发送按钮重新出现（用 SVG path 精确定位）
        2. 轮询检测回复内容是否稳定（连续 3 次相同）
        3. 最大超时兜底
        """
        start_time = time.time()
        poll_interval = 0.5  # 500ms

        # Phase 1: 等待生成完成（停止按钮消失）
        stop_gone = False
        while time.time() - start_time < timeout:
            if not self._js_is_generating():
                stop_gone = True
                break
            time.sleep(poll_interval)

        # 如果超时还没消失，等待一小段额外时间
        if not stop_gone:
            time.sleep(2)

        # Phase 2: 内容稳定性检测
        last_content = ""
        stable_count = 0
        required_stable = 3

        while time.time() - start_time < timeout:
            content = self._extract_response()
            if content and content == last_content:
                stable_count += 1
                if stable_count >= required_stable:
                    break
            else:
                stable_count = 0
                last_content = content
            time.sleep(poll_interval)

        # 最终提取（可能部分内容）
        final = self._extract_response()
        if final:
            return final
        elif last_content:
            return last_content

        raise TimeoutError(f"等待 AI 回复超时 ({timeout}s)")

    def _extract_response(self) -> str:
        """提取页面中 AI 的回复文本"""
        # 策略：获取最后一条 assistant 消息的全部文本
        try:
            # 尝试用选择器抓取
            for sel in SELECTORS_RESPONSE:
                try:
                    elements = self._page.query_selector_all(sel)
                    if elements:
                        return elements[-1].inner_text().strip()
                except Exception:
                    continue

            # 兜底：取页面中所有 .ds-markdown 的最后一项
            try:
                marks = self._page.query_selector_all(".ds-markdown")
                if marks:
                    return marks[-1].inner_text().strip()
            except Exception:
                pass

            return ""
        except Exception as e:
            _logger.warning(f"提取回复失败: {e}")
            return ""
