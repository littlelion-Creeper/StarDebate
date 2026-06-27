#!/usr/bin/env python3
"""
qss_color_reference.py — 颜色键引用地图工具

扫描 qss_templates/ 及插件 .qss 文件，统计每个 @key@ 占位符的引用情况。
输出三种格式：
    终端（默认）   — 正向+反向引用，带行号和属性名
    --md          — 生成 docs/qss_color_reference.md
    --json        — 生成 qss_color_reference.json

用法:
    python tools/qss_color_reference.py
    python tools/qss_color_reference.py --md
    python tools/qss_color_reference.py --json
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "style", "qss_templates")
PLUGINS_DIR = os.path.join(PROJECT_ROOT, "plugins")
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")

PLACEHOLDER_RE = re.compile(r'@(\w+)@')
COMMENT_LINE_RE = re.compile(r'^\s*(/\*|//|\*)')


def _find_plugin_qss() -> list[str]:
    """扫描 plugins/ 下各插件主题目录的 .qss 文件"""
    qss_files = []
    if not os.path.isdir(PLUGINS_DIR):
        return qss_files
    for plugin_name in os.listdir(PLUGINS_DIR):
        plugin_theme = os.path.join(PLUGINS_DIR, plugin_name, "theme")
        if os.path.isdir(plugin_theme):
            for fname in os.listdir(plugin_theme):
                if fname.endswith(".qss"):
                    qss_files.append(os.path.join(plugin_theme, fname))
    return qss_files


def _extract_property_name(line: str) -> str:
    """从 QSS 行中提取属性名（首个冒号前内容）"""
    colon_idx = line.find(":")
    if colon_idx == -1:
        return "?"
    return line[:colon_idx].strip()


def scan_file(filepath: str) -> list[dict[str, Any]]:
    """扫描单个 .qss 文件，返回所有 @key@ 引用的列表"""
    results: list[dict[str, Any]] = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for lineno, raw_line in enumerate(f, 1):
                stripped = raw_line.strip()
                if not stripped or COMMENT_LINE_RE.match(stripped):
                    continue
                for match in PLACEHOLDER_RE.finditer(stripped):
                    # 跳过注释行内的匹配（行内 /* ... */ 或 // 注释）
                    if "/*" in stripped and "*/" not in stripped:
                        continue
                    key = match.group(1)
                    prop = _extract_property_name(stripped)
                    results.append({
                        "key": key,
                        "line": lineno,
                        "property": prop,
                    })
    except OSError as e:
        print(f"  [WARN] 跳过 {filepath}: {e}", file=sys.stderr)
    return results


def build_map() -> dict[str, Any]:
    """扫描所有 QSS 模板和插件 QSS，构建正向+反向引用地图"""
    forward: dict[str, list[dict[str, Any]]] = defaultdict(list)
    reverse: dict[str, list[dict[str, Any]]] = defaultdict(list)
    scanned_files: list[str] = []

    # 扫描 qss_templates/
    if not os.path.isdir(TEMPLATES_DIR):
        print(f"[ERROR] 模板目录不存在: {TEMPLATES_DIR}", file=sys.stderr)
    else:
        for fname in sorted(os.listdir(TEMPLATES_DIR)):
            if not fname.endswith(".qss"):
                continue
            fpath = os.path.join(TEMPLATES_DIR, fname)
            refs = scan_file(fpath)
            scanned_files.append(fpath)
            for ref in refs:
                entry = {**ref, "file": fname}
                forward[ref["key"]].append(entry)
                reverse[fname].append(entry)

    # 扫描插件 QSS
    plugin_qss = _find_plugin_qss()
    for fpath in plugin_qss:
        rel = os.path.relpath(fpath, PROJECT_ROOT)
        refs = scan_file(fpath)
        scanned_files.append(fpath)
        for ref in refs:
            entry = {**ref, "file": rel}
            forward[ref["key"]].append(entry)
            reverse[rel].append(entry)

    return {
        "scanned": {
            "templates": len([f for f in scanned_files if "qss_templates" in f]),
            "plugins": len(plugin_qss),
            "total_files": len(scanned_files),
        },
        "forward": {
            k: sorted(v, key=lambda x: (x["file"], x["line"]))
            for k, v in sorted(forward.items())
        },
        "reverse": {
            k: sorted(v, key=lambda x: x["line"])
            for k, v in sorted(reverse.items())
        },
    }


# ── 终端输出 ──────────────────────────────────────────────────────────


def _print_terminal(data: dict[str, Any]) -> None:
    scanned = data["scanned"]
    forward = data["forward"]
    reverse = data["reverse"]

    print(f"📊  颜色键引用地图")
    print(f"   生成时间: {datetime.now():%Y-%m-%d %H:%M}")
    print(f"   扫描文件: 模板 {scanned['templates']} 个"
          f" + 插件 {scanned['plugins']} 个 = 共 {scanned['total_files']} 个\n")

    # ── 正向 ──
    print(f"{'=' * 60}")
    print(f"  正向引用（按颜色键分组）")
    print(f"{'=' * 60}\n")

    for key, occurrences in forward.items():
        all_files = sorted(set(o["file"] for o in occurrences))
        print(f"  @{key}@  （引用 {len(all_files)} 个模板文件，共 {len(occurrences)} 处引用）")
        for occ in occurrences:
            print(f"    ├── {occ['file']:42s}   L{occ['line']}({occ['property']})")
        print()

    # ── 反向 ──
    print(f"{'=' * 60}")
    print(f"  反向引用（按模板文件分组）")
    print(f"{'=' * 60}\n")

    for fname, occurrences in reverse.items():
        keys = sorted(set(o["key"] for o in occurrences))
        print(f"  {fname}  （使用 {len(keys)} 个颜色键，共 {len(occurrences)} 处引用）")
        for occ in occurrences:
            print(f"    ├── @{occ['key']}@               L{occ['line']}({occ['property']})")
        print()


# ── Markdown 输出 ─────────────────────────────────────────────────────


def _gen_markdown(data: dict[str, Any]) -> str:
    scanned = data["scanned"]
    forward = data["forward"]
    reverse = data["reverse"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# 颜色键引用地图",
        "",
        f"> 自动生成于 {now} | 扫描 {scanned['total_files']} 个文件"
        f"（模板 {scanned['templates']} + 插件 {scanned['plugins']}）",
        "",
        "---",
        "",
        "## 正向引用（按颜色键分组）",
        "",
    ]

    for key, occurrences in forward.items():
        all_files = sorted(set(o["file"] for o in occurrences))
        lines.append(f"### `@{key}@`  — 引用 {len(all_files)} 个文件，共 {len(occurrences)} 处")
        lines.append("")
        lines.append("| 文件 | 行号 | 属性 |")
        lines.append("|------|------|------|")
        for occ in occurrences:
            fname = occ["file"]
            line_no = occ["line"]
            prop = occ["property"]
            lines.append(f"| `{fname}` | {line_no} | `{prop}` |")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 反向引用（按模板文件分组）",
        "",
    ])

    for fname, occurrences in reverse.items():
        keys = sorted(set(o["key"] for o in occurrences))
        lines.append(f"### `{fname}`  — 使用 {len(keys)} 个颜色键，共 {len(occurrences)} 处")
        lines.append("")
        lines.append("| 颜色键 | 行号 | 属性 |")
        lines.append("|--------|------|------|")
        for occ in occurrences:
            key = occ["key"]
            line_no = occ["line"]
            prop = occ["property"]
            lines.append(f"| `@{key}@` | {line_no} | `{prop}` |")
        lines.append("")

    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="颜色键引用地图工具 — 统计 QSS 模板中 @key@ 占位符的引用情况",
    )
    parser.add_argument("--md", action="store_true",
                        help="生成 docs/qss_color_reference.md")
    parser.add_argument("--json", action="store_true",
                        help="生成 qss_color_reference.json")
    args = parser.parse_args()

    data = build_map()

    if args.md:
        md_path = os.path.join(DOCS_DIR, "qss_color_reference.md")
        content = _gen_markdown(data)
        os.makedirs(DOCS_DIR, exist_ok=True)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[OK] Markdown 已生成: {md_path}")
    elif args.json:
        json_path = os.path.join(PROJECT_ROOT, "qss_color_reference.json")
        data["generated_at"] = datetime.now().isoformat()
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[OK] JSON 已生成: {json_path}")
    else:
        _print_terminal(data)


if __name__ == "__main__":
    main()
