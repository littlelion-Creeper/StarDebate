#!/usr/bin/env python3
"""
verify_qss_templates.py — 验证 QSS 模板与原始硬编码文件的一致性

流程：
  1. 读取 qss_templates/ 中的 @key@ 模板
  2. 用 notion_dark 的 theme.json colors 替换占位符
  3. 逐行 diff 对比原始 notion_dark QC 文件
  4. 报告不一致之处

用法:
    python tools/verify_qss_templates.py              # 全部验证
    python tools/verify_qss_templates.py --file main.qss  # 验证单个文件
    python tools/verify_qss_templates.py --verbose     # 显示详细 diff
"""

import argparse
import json
import os
import re
import sys
from difflib import Differ

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REFERENCE_THEME = "notion_dark"
THEMES_DIR = os.path.join(PROJECT_ROOT, "style", "themes")
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "style", "qss_templates")

REMAINING_RE = re.compile(r'@\w+@')


def load_colors(theme_name: str) -> dict[str, str]:
    """加载 theme.json 的 colors 字段"""
    path = os.path.join(THEMES_DIR, theme_name, "theme.json")
    if not os.path.isfile(path):
        print(f"[ERROR] {path} 不存在", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("colors", {})


def replace_template(content: str, colors: dict[str, str]) -> str:
    """替换模板中的 @key@ 为 colors 中的 hex 值"""
    result = content
    for key, hex_val in colors.items():
        result = result.replace(f"@{key}@", hex_val)
    # 检查未替换的占位符
    remaining = REMAINING_RE.findall(result)
    return result, remaining


def verify_file(fname: str, colors: dict[str, str],
                verbose: bool = False) -> tuple[bool, list[str]]:
    """验证单个模板文件，返回 (是否一致, 差异行列表)"""
    template_path = os.path.join(TEMPLATES_DIR, fname)
    original_path = os.path.join(THEMES_DIR, REFERENCE_THEME, fname)

    if not os.path.isfile(template_path):
        return False, [f"模板文件不存在: {template_path}"]
    if not os.path.isfile(original_path):
        return False, [f"原始文件不存在: {original_path}"]

    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()
    with open(original_path, "r", encoding="utf-8") as f:
        original = f.read()

    replaced, remaining = replace_template(template, colors)

    if remaining:
        # 有残留占位符：需要在原始文件中确认这些 keystring 是否存在
        # 如果原始文件也有这些 keystring（不是作为键，而是恰好文本），则一致
        for placeholder in remaining:
            if placeholder not in original:
                return False, [
                    f"未替换的占位符: {placeholder}",
                    "(此键在 theme.json 中不存在)"
                ]

    if replaced == original:
        return True, []

    # 有差异：逐行 diff
    differ = Differ()
    orig_lines = original.splitlines(keepends=True)
    repl_lines = replaced.splitlines(keepends=True)
    diff_lines = list(differ.compare(orig_lines, repl_lines))

    # 过滤出实际差异
    changes = [
        line for line in diff_lines
        if line.startswith('- ') or line.startswith('+ ')
    ]

    if verbose:
        # 显示全部 diff
        return False, diff_lines
    else:
        # 仅显示差异行数统计
        return False, [f"差异行数: {len(changes)} (使用 --verbose 查看详情)"]


def main():
    parser = argparse.ArgumentParser(
        description="验证 QSS 模板与原始硬编码文件的一致性"
    )
    parser.add_argument("--file", "-f", type=str, default=None,
                        help="仅验证单个文件")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="显示详细 diff")
    args = parser.parse_args()

    colors = load_colors(REFERENCE_THEME)
    print(f"[verify] 验证参考主题: {REFERENCE_THEME}")
    print(f"   模板目录: {TEMPLATES_DIR}")
    print(f"   颜色键数: {len(colors)}")
    print()

    # 收集文件
    if args.file:
        files = [args.file]
    else:
        files = sorted(f for f in os.listdir(TEMPLATES_DIR) if f.endswith(".qss"))

    total = len(files)
    passed = 0
    failed = 0

    for fname in files:
        ok, issues = verify_file(fname, colors, verbose=args.verbose)
        if ok:
            passed += 1
            print(f"  [OK] {fname}")
        else:
            failed += 1
            print(f"  [FAIL] {fname}")
            for issue in issues[:20]:  # 最多显示 20 行差异
                print(f"    {issue}")
            if len(issues) > 20:
                print(f"    ... (还有 {len(issues) - 20} 行)")

    print()
    print(f"[结果] 通过: {passed}/{total}, 失败: {failed}/{total}")

    # 如果全部通过，也可以验证 notion_light
    if failed == 0 and not args.file:
        print()
        print("[verify] 使用 notion_light 颜色验证模板兼容性...")
        light_colors = load_colors("notion_light")
        light_ok = 0
        for fname in files:
            template_path = os.path.join(TEMPLATES_DIR, fname)
            if not os.path.isfile(template_path):
                continue
            with open(template_path, "r", encoding="utf-8") as f:
                content = f.read()
            _, remaining = replace_template(content, light_colors)
            if remaining:
                print(f"  [WARN] {fname}: 仍有 {len(remaining)} 个未替换占位符")
            else:
                light_ok += 1
        print(f"  notion_light 兼容: {light_ok}/{len(files)} 个文件无残留占位符")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
