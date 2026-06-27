"""
DebateClaw 代码执行沙箱
======================
提供安全的 Python 代码执行环境。
仅允许 matplotlib/pandas/numpy 等数据分析库，
禁止 os/subprocess/socket 等危险模块。
"""

import io, sys, re, traceback
from contextlib import redirect_stdout, redirect_stderr


# ── 安全白名单 ──

# 允许导入的模块（及其子模块）
_SAFE_IMPORTS = {
    # 数据分析核心
    "numpy", "np",
    "pandas", "pd",
    "matplotlib", "matplotlib.pyplot", "plt",
    "math", "cmath",
    "random",
    "statistics",
    "collections", "itertools",
    "datetime", "time",
    "json", "re",
    "string", "textwrap",
    "fractions", "decimal",
    "copy", "functools",
    "typing",
}

# 禁止使用的内置函数/属性
_FORBIDDEN_BUILTINS = {
    "__import__",
    "eval", "exec", "compile",
    "open", "input",
    "breakpoint",
    "globals", "locals",
    "vars", "dir",
    "getattr", "setattr", "delattr",
    "hasattr",
}


# ── 危险模式检测 ──

_DANGEROUS_PATTERNS = [
    r'\bimport\s+os\b',
    r'\bfrom\s+os\b',
    r'\bimport\s+subprocess\b',
    r'\bfrom\s+subprocess\b',
    r'\bimport\s+socket\b',
    r'\bfrom\s+socket\b',
    r'\bimport\s+shutil\b',
    r'\bimport\s+sys\b.*\bsys\.exit',
    r'__import__\s*\(',
    r'\beval\s*\(',
    r'\bexec\s*\(',
    r'\bcompile\s*\(',
    r'\bos\.',
    r'\bsubprocess\.',
    r'\bsocket\.',
    r'\bopen\s*\([',
    r'\brm\s*\(|\brmdir\s*\(',
    r'\bshutil\.',
]


def _check_code_safety(code: str) -> tuple[bool, str]:
    """检查代码安全性。

    Returns:
        (is_safe, error_message)
    """
    for pattern in _DANGEROUS_PATTERNS:
        if re.search(pattern, code):
            return False, f"检测到危险操作: {pattern}"

    return True, ""


# ── 安全执行环境构建 ──

def _create_safe_namespace() -> dict:
    """创建受限的执行命名空间。"""
    safe_ns = {}

    # 只允许安全的内置函数
    builtins = __builtins__.__dict__ if isinstance(__builtins__, type) else __builtins__
    safe_builtins = {}
    for name, obj in builtins.items():
        if name not in _FORBIDDEN_BUILTINS:
            safe_builtins[name] = obj
    safe_ns["__builtins__"] = safe_builtins

    # 预导入常用安全库的别名
    try:
        import numpy as np
        safe_ns["np"] = np
        safe_ns["numpy"] = np
    except ImportError:
        pass

    try:
        import pandas as pd
        safe_ns["pd"] = pd
        safe_ns["pandas"] = pd
    except ImportError:
        pass

    try:
        import matplotlib.pyplot as plt
        safe_ns["plt"] = plt
    except ImportError:
        pass

    # 数学常量
    import math
    safe_ns.update({
        "pi": math.pi,
        "e": math.e,
    })

    return safe_ns


# ── 图片输出处理 ──

_OUTPUT_DIR = None  # 延迟初始化

def _get_output_dir() -> str:
    global _OUTPUT_DIR
    if _OUTPUT_DIR is None:
        from plugins.debate_claw.workers.permission_handler import (
            _CONFIG_PATH as _cfg_p)
        base = os.path.dirname(_cfg_p)
        _OUTPUT_DIR = os.path.join(base, "..", "..", "_claw_exec_output")
        os.makedirs(_OUTPUT_DIR, exist_ok=True)
    return _OUTPUT_DIR


def _save_figure_if_exists(fig_id: int | None = None) -> str | None:
    """如果当前有 matplotlib 图表，保存并返回路径。"""
    try:
        import matplotlib.pyplot as plt

        # 检查是否有活跃图表
        figs = plt.get_fignums()
        if not figs:
            return None

        out_dir = _get_output_dir()
        fig_num = fig_id if fig_id is not None else figs[-1]
        fig = plt.figure(fig_num)

        img_path = os.path.join(out_dir, f"exec_fig_{fig_num}.png")
        fig.savefig(img_path, dpi=100, bbox_inches="tight")
        plt.close(fig)

        return img_path
    except Exception:
        return None


# ══════════════════════════════════════════
#  公共接口
# ══════════════════════════════════════════

def safe_execute(code: str, timeout: int = 30) -> str:
    """在安全沙箱中执行 Python 代码。

    Args:
        code: 要执行的 Python 代码
        timeout: 超时时间（秒），默认 30 秒

    Returns:
        执行结果文本，格式：
        - 成功时：输出内容 + 图片路径（如有）
        - 失败时：错误信息
    """
    # 1. 安全校验
    is_safe, error_msg = _check_code_safety(code)
    if not is_safe:
        return (
            "❌ 代码安全检查未通过\n"
            f"原因: {error_msg}\n"
            "\n请移除以下类型的操作后重试:\n"
            "- 文件读写 (open/rm/shutil)\n"
            "- 系统命令 (os/subprocess)\n"
            "- 网络访问 (socket)\n"
            "- 动态执行 (eval/exec/__import__)"
        )

    # 2. 创建安全执行空间
    exec_ns = _create_safe_namespace()

    # 3. 执行代码并捕获输出/错误
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    result_parts = []

    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            # 使用 compile 先编译，捕获语法错误
            compiled = compile(code, "<sandbox>", "exec")
            exec(compiled, exec_ns)

        stdout_val = stdout_capture.getvalue().strip()
        stderr_val = stderr_capture.getvalue().strip()

        if stdout_val:
            result_parts.append(f"**输出:**\n```\n{stdout_val}\n```")

        if stderr_val:
            result_parts.append(f"**警告:**\n```\n{stderr_val}\n```")

        # 检查是否有生成的图片
        img_path = _save_figure_if_exists()
        if img_path:
            size_kb = os.path.getsize(img_path) // 1024
            result_parts.append(
                f"\n📊 已生成图表:\n"
                f"  文件: {img_path}\n"
                f"  大小: {size_kb} KB"
            )

        if result_parts:
            return "\n".join(result_parts)
        return "✅ 代码执行成功（无输出）"

    except SyntaxError as e:
        return (
            f"❌ 语法错误（第 {e.lineno or '?'} 行）:\n"
            f"`{e.msg}`\n"
            f"\n{e.text or ''}"
        )
    except NameError as e:
        return f"❌ 名称错误: `{e}`\n提示: 请检查变量名是否正确，或确认所需库已安装。"
    except ImportError as e:
        return f"❌ 导入错误: `{e}`\n注意: 仅允许使用 numpy/pandas/matplotlib 等数据分析库。"
    except Exception as e:
        tb_lines = traceback.format_exc().splitlines()
        # 只保留最后几行关键信息
        short_tb = "\n".join(tb_lines[-5:]) if len(tb_lines) > 5 else "\n".join(tb_lines)
        return f"❌ 执行错误:\n```\n{short_tb}\n```"


def get_execution_history(limit: int = 10) -> list:
    """获取最近的执行输出文件列表。"""
    out_dir = _get_output_dir()
    if not os.path.isdir(out_dir):
        return []

    files = []
    for f in sorted(os.listdir(out_dir), reverse=True)[:limit]:
        fpath = os.path.join(out_dir, f)
        if f.endswith(('.png', '.jpg', '.svg')) and os.path.isfile(fpath):
            stat = os.stat(fpath)
            files.append({
                "name": f,
                "path": fpath,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
    return files
