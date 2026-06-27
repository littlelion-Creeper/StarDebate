"""
预设图标注册表

集中管理项目常用的 SVG 图标路径映射。
可通过 SvgRenderer.named("checkmark", 20) 快速获取。

图标分类：
  - checkbox: 复选框
  - message_box: 消息框
  - spinbox: 数字输入框箭头
  - action: 常用操作
"""
import os


# 项目根目录下的图标文件夹
_ICON_DIR = ""

_ICON_REGISTRY: dict[str, dict[str, str]] = {}


def init_icon_dir(project_root: str):
    """初始化图标目录路径（由 SvgRenderer 启动时调用）"""
    global _ICON_DIR, _ICON_REGISTRY
    _ICON_DIR = os.path.join(project_root, "icon")
    _build_registry()


def _build_registry():
    """构建预设图标映射表"""
    global _ICON_REGISTRY
    _ICON_REGISTRY = {
        # ── 复选框 ──
        "checkbox_unchecked": os.path.join(_ICON_DIR, "checkbox", "square.svg"),
        "checkbox_checked": os.path.join(_ICON_DIR, "checkbox", "checkmark_square.svg"),

        # ── 消息框 ──
        "msg_info": os.path.join(_ICON_DIR, "message_box", "info_circle.svg"),
        "msg_warning": os.path.join(_ICON_DIR, "message_box", "exclamationmark_circle.svg"),
        "msg_error": os.path.join(_ICON_DIR, "message_box", "xmark_circle.svg"),
        "msg_question": os.path.join(_ICON_DIR, "message_box", "questionmark_circle.svg"),

        # ── 数字输入框 ──
        "spin_up": os.path.join(_ICON_DIR, "spinbox", "white", "arrowtriangle_up_fill_white.svg"),
        "spin_down": os.path.join(_ICON_DIR, "spinbox", "white", "arrowtriangle_down_fill_white.svg"),

        # ── 常用操作（按需扩展）──
        # "action_search": os.path.join(_ICON_DIR, "action", "search.svg"),
        # "action_add": os.path.join(_ICON_DIR, "action", "add.svg"),
        # "action_close": os.path.join(_ICON_DIR, "action", "close.svg"),
        # "action_save": os.path.join(_ICON_DIR, "action", "save.svg"),
    }


def lookup(name: str) -> str:
    """根据名称查找 SVG 路径。返回路径字符串，未找到返回空字符串。"""
    return _ICON_REGISTRY.get(name, "")


def register(name: str, svg_path: str):
    """插件可调用此方法注册自定义图标"""
    _ICON_REGISTRY[name] = svg_path


def unregister(name: str):
    """取消注册自定义图标"""
    _ICON_REGISTRY.pop(name, None)


def list_names() -> list[str]:
    """列出所有已注册图标名称"""
    return sorted(_ICON_REGISTRY.keys())
