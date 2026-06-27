"""StarDebate ★ 测试扩展包
============================================================================
用于验证扩展包系统的安装、加载、API 访问和卸载流程。
============================================================================
"""
from workers.extension_manager import get_api


def on_enable():
    """扩展包启用时调用（安装即启用，重启生效）。"""
    api = get_api()
    if api is None:
        print("[TestExtension] API 不可用")
        return

    mw = api.get_main_window()
    if mw is None:
        print("[TestExtension] 无法获取主窗口")
        return

    # ── 测试 1：通过 get_core_object 获取管理器 ──
    app_cfg = api.get_core_object("_app_cfg")
    nav_mgr = api.get_core_object("_nav_mgr")
    analysis_mgr = api.get_core_object("_analysis_mgr")

    print(f"[TestExtension] _app_cfg = {app_cfg}")
    print(f"[TestExtension] _nav_mgr = {nav_mgr}")
    print(f"[TestExtension] _analysis_mgr = {analysis_mgr}")

    # ── 测试 2：通过专用方法获取管理器 ──
    ext_mgr = api.get_extension_manager()
    plugin_mgr = api.get_plugin_manager()
    cfg = api.get_app_cfg()

    print(f"[TestExtension] ExtensionManager = {ext_mgr}")
    print(f"[TestExtension] PluginManager = {plugin_mgr}")
    print(f"[TestExtension] AppConfig = {cfg}")

    # ── 测试 3：读取配置 ──
    if cfg is not None:
        try:
            full_cfg = cfg.load_full_config()
            version = full_cfg.get("version", "未知")
            print(f"[TestExtension] StarDebate 版本: {version}")
        except Exception as e:
            print(f"[TestExtension] 读取配置失败: {e}")

    # ── 测试 4：通过主窗口直接访问 UI ──
    if hasattr(mw, 'centre_stack'):
        print(f"[TestExtension] centre_stack 共有 {mw.centre_stack.count()} 页")

    # ── 测试 5：注册一个顶部菜单按钮 ──
    api.register_top_menu(
        "test_ext_btn",
        "测试扩展",
        lambda: print("[TestExtension] 测试按钮被点击"),
        tooltip="测试扩展包注册的顶部按钮",
    )

    # ── 输出到状态栏 ──
    try:
        mw._update_status("✅ 测试扩展包已加载")
    except Exception:
        pass

    print("[TestExtension] ✅ on_enable 执行完成")


def on_disable():
    """扩展包禁用时调用。"""
    print("[TestExtension] 扩展包已禁用")
    mw = get_api().get_main_window() if get_api() else None
    if mw:
        try:
            mw._update_status("🔧 测试扩展包已禁用")
        except Exception:
            pass
