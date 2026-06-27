#!/usr/bin/env python3
"""
diffuse_qss.py — Phase 2 颜色映射扩散脚本

将 catppuccin_mocha 中新增的 #objectName QSS 规则
根据每个主题的 theme.json 色板，自动扩散到其余 6 个主题。

用法: python tools/diffuse_qss.py
"""

import json
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFERENCE_THEME = "catppuccin_mocha"
TARGET_THEMES = [
    "catppuccin_latte",
    "catppuccin_macchiato",
    "modern_mocha",
    "nord",
    "notion_dark",
    "notion_light",
]

# 已修改的 QSS 文件列表（相对于 style/themes/{theme}/）
MODIFIED_QSS = [
    "training.qss",
    "tournament.qss",
    "settings.qss",
    "notes.qss",
    "material_pool.qss",
    "ai_expand.qss",
    "cross_examination.qss",
    "speech_writer.qss",
    "speech_editor.qss",
]


def load_theme_colors(theme_name: str) -> dict[str, str]:
    """读取主题的 theme.json，返回 color_name → hex 映射"""
    path = os.path.join(PROJECT_ROOT, "style", "themes", theme_name, "theme.json")
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("colors", {})


def build_hex_to_name(colormap: dict[str, str]) -> dict[str, str]:
    """生成 hex → color_name 反向映射"""
    return {v.lower(): k for k, v in colormap.items()}


def parse_objectname_rules(qss_text: str) -> dict[str, str]:
    """提取 QSS 中所有 #objectName { ... } 块，返回 {objectName: block_text}"""
    rules = {}
    pattern = re.compile(r'(#[a-zA-Z]\w*(?::\w+)?(?:\s+[a-zA-Z#]\w*(?::\w+)?)*)\s*\{')
    pos = 0
    while True:
        m = pattern.search(qss_text, pos)
        if not m:
            break
        name = m.group(1)
        brace_start = m.end()
        depth = 1
        i = brace_start
        while i < len(qss_text) and depth > 0:
            if qss_text[i] == '{':
                depth += 1
            elif qss_text[i] == '}':
                depth -= 1
            i += 1
        block = qss_text[m.start():i]
        rules[name] = block
        pos = i
    return rules


def convert_hex_in_block(block: str, ref_hex_to_name: dict[str, str],
                         target_colormap: dict[str, str]) -> str:
    """将 block 中的 hex 颜色从参考色板转换为目标色板"""
    hex_pattern = re.compile(r'#[0-9a-fA-F]{6}\b')

    def replace_hex(m):
        h = m.group(0).lower()
        if h in ref_hex_to_name:
            name = ref_hex_to_name[h]
            if name in target_colormap:
                return target_colormap[name]
        # unknown hex — add FIXME comment
        return f"{h} /* FIXME: manual */"

    return hex_pattern.sub(replace_hex, block)


def main():
    ref_colors = load_theme_colors(REFERENCE_THEME)
    ref_hex_to_name = build_hex_to_name(ref_colors)

    for qss_file in MODIFIED_QSS:
        ref_path = os.path.join(PROJECT_ROOT, "style", "themes",
                                REFERENCE_THEME, qss_file)
        if not os.path.isfile(ref_path):
            print(f"[SKIP] {qss_file} not found in reference")
            continue

        with open(ref_path, "r", encoding="utf-8") as f:
            ref_qss = f.read()

        ref_rules = parse_objectname_rules(ref_qss)
        print(f"\n=== {qss_file} ({len(ref_rules)} total rules in reference) ===")

        for theme in TARGET_THEMES:
            target_path = os.path.join(PROJECT_ROOT, "style", "themes",
                                       theme, qss_file)
            if not os.path.isfile(target_path):
                print(f"  [SKIP] {theme}/{qss_file} — file not found")
                continue

            target_colors = load_theme_colors(theme)
            with open(target_path, "r", encoding="utf-8") as f:
                target_qss = f.read()

            target_rules = parse_objectname_rules(target_qss)
            new_blocks = []
            for name, block in ref_rules.items():
                if name in target_rules:
                    continue  # already exists
                converted = convert_hex_in_block(block, ref_hex_to_name,
                                                  target_colors)
                new_blocks.append(converted)

            if not new_blocks:
                print(f"  [OK] {theme}/{qss_file} — up to date")
                continue

            # Append new blocks
            with open(target_path, "a", encoding="utf-8") as f:
                f.write("\n\n/* === 自动扩散自 catppuccin_mocha === */\n")
                for nb in new_blocks:
                    f.write(nb + "\n\n")

            print(f"  [ADD {len(new_blocks)}] {theme}/{qss_file}")

    print("\n=== Phase 2 颜色映射扩散完成！ ===")


if __name__ == "__main__":
    main()
