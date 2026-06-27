"""StarDebate ★ 扩展包 API
============================================================================
ExtensionAPI 继承自 PluginSafeAPI，额外提供：
  1. 直接暴露 MainWindow 下所有核心管理器引用（get_main_window()）
  2. 高级方法：注册顶层菜单、注册中心页、注册快捷键等
  3. 无权限校验（扩展包默认全权限）
============================================================================
"""
from PyQt5.QtWidgets import QWidget

try:
    from workers.plugin_manager.plugin_api import PluginSafeAPI
except ImportError:
    PluginSafeAPI = object  # fallback


class ExtensionAPI(PluginSafeAPI):
    """扩展包 API — 继承 PluginSafeAPI + 暴露全量核心对象 + 高级方法

    与 PluginSafeAPI 的区别：
      - 无权限校验（扩展包默认全权限）
      - 通过 get_main_window() 直接返回 MainWindow 引用
      - 额外提供高级注册方法
    """

    def __init__(self):
        super().__init__()
        self._ext_id = ""

    def set_context(self, main_window, ext_id: str = ""):
        """设置上下文（覆盖父类的 set_context，跳过 permissions 设置）"""
        self._main_window = main_window
        self._ext_id = ext_id

    # ── 全量核心对象暴露 ──

    def get_main_window(self):
        """直接返回 MainWindow（StarDebateApp）引用，可访问所有核心管理器"""
        return self._main_window

    def get_extension_manager(self):
        """获取 ExtensionManager 实例"""
        from . import get_manager
        return get_manager()

    def get_core_object(self, attr_name: str):
        """通过属性名获取核心对象（如 '_app_cfg', '_nav_mgr', '_analysis_mgr' 等）

        扩展包可通过此方法获取任意核心管理器：
          api.get_core_object('_app_cfg')
          api.get_core_object('_analysis_mgr')
          api.get_core_object('_plugin_manager')
        """
        mw = self._main_window
        if mw is None:
            return None
        return getattr(mw, attr_name, None)

    # ── 高级注册方法 ──

    def register_top_menu(self, menu_id: str, menu_text: str,
                          callback, tooltip: str = ""):
        """在「扩展」菜单下注册一个子菜单项。"""
        mw = self._main_window
        if mw is None:
            return
        try:
            top_nav = getattr(mw, '_top_nav_mgr', None)
            if top_nav is not None:
                sub_data = {
                    "id": menu_id,
                    "text": menu_text,
                    "tooltip": tooltip,
                    "callback": callback,
                    "plugin_id": self._ext_id,
                }
                top_nav.register_plugin_sub_menu("extension_menu", sub_data)
        except Exception:
            import traceback
            traceback.print_exc()

    def register_center_page(self, page_widget: QWidget):
        """注册一个中心页面到 centre_stack 末尾"""
        mw = self._main_window
        if mw is None:
            return
        try:
            stack = getattr(mw, 'centre_stack', None)
            if stack is not None:
                stack.addWidget(page_widget)
        except Exception:
            import traceback
            traceback.print_exc()

    def modify_theme_colors(self, color_overrides: dict):
        """修改主题颜色（影响全局）"""
        from components.theme_colors import tc
        tc._overrides.update(color_overrides)

    def get_app_cfg(self):
        """获取 AppConfigManager"""
        mw = self._main_window
        if mw is None:
            return None
        return getattr(mw, '_app_cfg', None)

    def get_plugin_manager(self):
        """获取 PluginManager"""
        mw = self._main_window
        if mw is None:
            return None
        return getattr(mw, '_plugin_manager', None)
