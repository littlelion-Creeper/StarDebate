#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StarDebate ★ .stp 插件包打包工具（命令行）

用法：
  python tools/pack_stp.py ./plugins/my_plugin/
  python tools/pack_stp.py ./plugins/my_plugin/ -o my_plugin.stp
  python tools/pack_stp.py ./plugins/my_plugin/ --validate

无 GUI 依赖，适合 CI 流程和批处理。
仅需 Python 3.10+ 标准库。
"""

import sys
import os
import argparse

# ── 路径配置 ──────────────────────────────────────────────────
# 将项目根目录加入 sys.path，以便导入核心模块
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def main():
    parser = argparse.ArgumentParser(
        description="将 StarDebate 插件目录打包为 .stp 文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  %(prog)s ./plugins/my_plugin/\n"
            "  %(prog)s ./plugins/my_plugin/ -o my_plugin.stp\n"
            "  %(prog)s ./plugins/my_plugin/ --validate\n"
        ),
    )
    parser.add_argument(
        "source",
        help="插件目录路径（应包含 plugin.json 和 main.py）",
    )
    parser.add_argument(
        "-o", "--output",
        default="",
        help="输出 .stp 文件路径（默认：当前目录/插件名.stp）",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="仅验证插件目录，不打包",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细输出",
    )

    args = parser.parse_args()

    # ── 导入核心模块 ────────────────────────────────────────────
    from plugin_manager.core.stp_packager import (
        validate_package, read_manifest, package,
    )

    source = os.path.abspath(args.source)
    if not os.path.isdir(source):
        print(f"错误：目录不存在: {source}")
        sys.exit(1)

    # ── 验证 ────────────────────────────────────────────────────
    errors = validate_package(source)
    if errors:
        print(f"验证失败 ({len(errors)} 个问题):")
        for e in errors:
            print(f"  [FAIL] {e}")
        sys.exit(1)

    manifest = read_manifest(source)
    name = manifest.get("name", "未知") if manifest else "未知"
    pid = manifest.get("plugin_id", "") if manifest else ""
    version = manifest.get("version", "") if manifest else ""
    perms = manifest.get("permissions", []) if manifest else []

    print(f"[PASS] 插件目录: {source}")
    print(f"  名称:     {name}")
    print(f"  ID:       {pid}")
    print(f"  版本:     {version}")
    print(f"  权限:     {', '.join(perms) if perms else '(无)'}")

    if args.validate:
        print()
        print("验证通过，未打包。")
        sys.exit(0)

    # ── 打包 ────────────────────────────────────────────────────
    try:
        output_path = package(source, args.output)
        size_kb = os.path.getsize(output_path) / 1024
        print()
        print(f"[DONE] 打包完成: {output_path}")
        print(f"  大小:     {size_kb:.1f} KB")
        print(f"  格式:     .stp (Zip + StarPlugin 注释 + SHA256)")
        sys.exit(0)

    except Exception as e:
        print(f"错误：打包失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
