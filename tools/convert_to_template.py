#!/usr/bin/env python3
"""
convert_to_template.py — 将现有硬编码 QSS 转换为 @key@ 模板

读取 notion_dark（参考主题）的 theme.json 和 QSS 文件，
将 theme.json 中定义的 hex 颜色替换为 @key@ 占位符，
输出到 style/qss_templates/。

同时为 theme.json 补充常用的硬编码色（如 #FFFFFF），
确保模板既精简又完整。

用法:
    python tools/convert_to_template.py          # 执行转换
    python tools/convert_to_template.py --dry-run  # 预览改动
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REFERENCE_THEME = "notion_dark"
THEMES_DIR = os.path.join(PROJECT_ROOT, "style", "themes")
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "style", "qss_templates")

HEX_RE = re.compile(r'#[0-9a-fA-F]{6}\b')


# 补充常用色值（检测到缺失时会自动补入 theme.json）
EXTRA_COLORS: dict[str, str] = {}


def load_theme_colors(theme_name: str) -> dict[str, str]:
    """读取 theme.json 的 colors 字段"""
    path = os.path.join(THEMES_DIR, theme_name, "theme.json")
    if not os.path.isfile(path):
        print(f"[ERROR] 找不到 {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("colors", {})


def build_hex_to_key(colors: dict[str, str]) -> dict[str, str]:
    """构建 hex -> canonical_key 映射。
    当多个键对应同一 hex 时，按语义优先级选择最合适的键名。"""
    groups: dict[str, list[str]] = defaultdict(list)
    for key, hex_val in colors.items():
        groups[hex_val.upper()].append(key)

    PRIORITY = [
        "base", "surface", "overlay", "mantle", "crust",
        "text", "subtext", "muted",
        "border", "divider",
        "hover", "pressed", "selected_bg", "toggle_off",
        "accent_blue", "selected", "accent_blue_hover",
        "accent_green", "accent_red",
        "accent_yellow", "accent_yellow_light", "accent_orange", "accent_pink",
        "accent_purple",
        "accent",
        "accent_blue_alt", "accent_blue_deep", "accent_blue_pressed",
        "accent_green_hover",
        "border_dim", "surface_dim",
        "bg_question", "bg_answer",
        "white", "close_pressed",
    ]

    result: dict[str, str] = {}
    for hex_upper, keys in groups.items():
        chosen = keys[0]
        for p in PRIORITY:
            if p in keys:
                chosen = p
                break
        result[hex_upper] = chosen
    return result


def add_extra_colors_to_theme(theme_name: str) -> dict[str, str]:
    """补充 theme.json 中缺失的常用色值，返回完整 colors 字典"""
    path = os.path.join(THEMES_DIR, theme_name, "theme.json")
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    colors = cfg.get("colors", {})
    added = False
    for key, hex_val in EXTRA_COLORS.items():
        if key not in colors:
            colors[key] = hex_val
            added = True
            print(f"  [ADD] {theme_name}/theme.json +{key}: {hex_val}")
    if added:
        cfg["colors"] = colors
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
    return colors


def replace_hex_in_line(line: str, hex_to_key: dict[str, str],
                         stats: dict) -> str:
    """替换行内所有 hex 颜色为 @key@，返回替换后的行"""
    def replacer(m):
        hex_val = m.group(0).upper()
        key = hex_to_key.get(hex_val)
        if key:
            stats["replaced"] += 1
            return f"@{key}@"
        else:
            stats["skipped"].add(hex_val)
            return m.group(0)

    return HEX_RE.sub(replacer, line)


def convert_qss_file(src_path: str, dst_path: str,
                     hex_to_key: dict[str, str],
                     stats: dict) -> int:
    """转换单个 QSS 文件，返回有替换的行数"""
    if not os.path.isfile(src_path):
        print(f"  [SKIP] 源文件不存在: {src_path}")
        return 0

    with open(src_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    output_lines: list[str] = []
    file_replaced_lines = 0
    in_comment_block = False

    for line in lines:
        stripped = line.strip()

        # 跳过注释块
        if "/*" in stripped and "*/" not in stripped:
            in_comment_block = True
            output_lines.append(line)
            continue
        if in_comment_block:
            output_lines.append(line)
            if "*/" in stripped:
                in_comment_block = False
            continue
        if stripped.startswith("//"):
            output_lines.append(line)
            continue
        if not stripped or stripped.startswith("*"):
            output_lines.append(line)
            continue

        # 替换 hex 颜色
        new_line = replace_hex_in_line(line, hex_to_key, stats)
        output_lines.append(new_line)
        if new_line != line:
            file_replaced_lines += 1

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, "w", encoding="utf-8") as f:
        f.writelines(output_lines)

    return file_replaced_lines


def main():
    parser = argparse.ArgumentParser(
        description="将硬编码 QSS 转换为 @key@ 模板"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="预览模式，不写入文件")
    args = parser.parse_args()

    print("[convert] 主题 QSS 模板转换工具")
    print(f"  参考主题: {REFERENCE_THEME}")
    print(f"  模板目录: {TEMPLATES_DIR}")
    print()

    # 0) 补充 theme.json
    if not args.dry_run:
        print("[phase 0] 补充 theme.json 缺失色值...")
        ref_colors = add_extra_colors_to_theme("notion_dark")
        add_extra_colors_to_theme("notion_light")
        print()
    else:
        ref_colors = load_theme_colors(REFERENCE_THEME)

    # 1) 构建 hex -> key 映射
    hex_to_key = build_hex_to_key(ref_colors)
    print(f"[phase 1] 颜色映射: {len(hex_to_key)} 个 hex -> key")
    print()

    if args.dry_run:
        print("  Hex -> Key 映射表:")
        for hex_val, key in sorted(hex_to_key.items()):
            print(f"    {hex_val:>8s}  ->  @{key}@")
        print()

    # 2) 扫描 QSS 文件
    ref_dir = os.path.join(THEMES_DIR, REFERENCE_THEME)
    qss_files = sorted(
        f for f in os.listdir(ref_dir) if f.endswith(".qss")
    )
    print(f"[phase 2] 发现 {len(qss_files)} 个 QSS 文件")
    print()

    stats = {
        "replaced": 0,
        "skipped": set(),
        "files_processed": 0,
        "files_with_replacement": 0,
    }

    # 3) 转换
    print("[phase 3] 转换中...")
    for i, fname in enumerate(qss_files, 1):
        src = os.path.join(THEMES_DIR, REFERENCE_THEME, fname)
        dst = os.path.join(TEMPLATES_DIR, fname)

        if args.dry_run:
            with open(src, "r", encoding="utf-8") as f:
                content = f.read()
            hexes = HEX_RE.findall(content)
            known = sum(1 for h in hexes if h.upper() in hex_to_key)
            unknown = len(hexes) - known
            status = f"[{i}/{len(qss_files)}] {fname:40s} {known:<3d} 处替换, {unknown:<3d} 处保持"
            if unknown > 0:
                status += " [有未映射色值]"
            print(f"  {status}")
            continue

        count = convert_qss_file(src, dst, hex_to_key, stats)
        stats["files_processed"] += 1
        if count > 0:
            stats["files_with_replacement"] += 1

    # 4) 报告
    print()
    print("[report] 转换完成:")
    if not args.dry_run:
        print(f"  处理文件: {stats['files_processed']} 个")
        print(f"  有替换的文件: {stats['files_with_replacement']} 个")
        print(f"  替换总数: {stats['replaced']} 次")
        if stats["skipped"]:
            print()
            print("  以下 hex 色值不在 theme.json 中，已保持原样:")
            for h in sorted(stats["skipped"]):
                print(f"    {h}")
            print("  如需模板化，请将这些值补充到 theme.json 后重新运行。")
        print()
        print(f"[done] 模板已生成到: {TEMPLATES_DIR}")
    else:
        print(f"  共扫描 {len(qss_files)} 个文件, {len(hex_to_key)} 个颜色键可用")


if __name__ == "__main__":
    main()
