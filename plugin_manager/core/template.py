"""
插件模板管理器 — 生成插件项目脚手架
"""

import os
import json
import shutil

_TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates",
    "default",
)


def get_template_dir() -> str:
    """获取默认模板目录路径。"""
    return _TEMPLATE_DIR


def create_project(target_dir: str, fields: dict) -> list[str]:
    """在 target_dir 下创建插件项目。

    Args:
        target_dir: 目标目录（将创建以 plugin_id 为名的子目录）
        fields: 模板填充字段，支持：
            - name (str): 插件名称
            - plugin_id (str): 插件 ID
            - version (str): 版本号
            - author (str): 作者
            - description (str): 描述
            - min_app_version (str): 最低 StarDebate 版本
            - permissions (list): 权限列表
            - tags (list): 标签列表
            - emoji (str): 导航栏 emoji
            - short_name (str): 简称
            - class_name (str): Python 类名

    Returns:
        list[str]: 生成的文件路径列表（相对 target_dir）
    """
    # 补全字段
    name = fields.get("name", "新插件")
    plugin_id = fields.get("plugin_id", "author.new_plugin")
    fields.setdefault("version", "1.0.0")
    fields.setdefault("author", "作者")
    fields.setdefault("description", "插件功能描述")
    fields.setdefault("min_app_version", "1.0.0")
    fields.setdefault("permissions", [])
    fields.setdefault("tags", [])
    fields.setdefault("emoji", "🔧")
    fields.setdefault("short_name", name if len(name) <= 4 else name[:4])
    fields.setdefault("class_name", _to_class_name(plugin_id))

    # 创建项目目录
    project_dir = os.path.join(target_dir, plugin_id)
    os.makedirs(project_dir, exist_ok=True)

    generated = []

    # 生成 plugin.json
    tpl_json = _read_template("plugin.json.tpl")
    content_json = _fill_template(tpl_json, fields)
    json_path = os.path.join(project_dir, "plugin.json")
    with open(json_path, "w", encoding="utf-8") as f:
        # 用 JSON 格式化确保合法性
        data = json.loads(content_json)
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    generated.append(os.path.join(plugin_id, "plugin.json"))

    # 生成 main.py
    tpl_py = _read_template("main.py.tpl")
    content_py = _fill_template(tpl_py, fields)
    py_path = os.path.join(project_dir, "main.py")
    with open(py_path, "w", encoding="utf-8") as f:
        f.write(content_py)
    generated.append(os.path.join(plugin_id, "main.py"))

    return generated


def _read_template(name: str) -> str:
    """读取模板文件内容。"""
    path = os.path.join(_TEMPLATE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _fill_template(content: str, fields: dict) -> str:
    """填充模板变量（$VAR 替换）。"""
    result = content
    for key, value in fields.items():
        placeholder = f"${key.upper()}"
        if isinstance(value, list):
            str_value = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, bool):
            str_value = str(value).lower()
        else:
            str_value = str(value)
        result = result.replace(placeholder, str_value)
    return result


def _to_class_name(plugin_id: str) -> str:
    """将 plugin_id 转换为合法的 Python 类名。"""
    # 取最后一段（如 "author.my_plugin" → "my_plugin"）
    name = plugin_id.split(".")[-1] if "." in plugin_id else plugin_id
    # 下划线命名转 PascalCase
    parts = name.replace("-", "_").split("_")
    return "".join(p.capitalize() for p in parts if p)
