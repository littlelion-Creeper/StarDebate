"""自动生成 StarDebate 增量更新补丁 ZIP（基于 git）。

原理：
- 使用 `git diff --name-status <from_ref> HEAD` 自动检测变更文件
- 排除 plugins/、__pycache__、.git、_update_staging 等不应打包的目录
- 自动分类 modify / add / delete
- 生成标准 manifest.json + ZIP

用法（基础）：
    python tools/gen_patch.py                          # 全自动：从最新 tag 检测，patch 号 +1
    python tools/gen_patch.py --from v6.3.3            # 指定起始版本
    python tools/gen_patch.py --to v7.0.0              # 指定目标版本
    python tools/gen_patch.py -n release_notes.md      # 从文件读 release notes

用法（进阶）：
    python tools/gen_patch.py --dry-run                # 仅预览，不生成 ZIP
    python tools/gen_patch.py --bump-version           # 同时写入 config.json
    python tools/gen_patch.py --ref v6.3.3..v6.3.4     # 使用任意 git 范围
    python tools/gen_patch.py --since "2 days ago"     # 按时间范围检测
"""

import os
import sys
import json
import zipfile
import hashlib
import subprocess
import re
from datetime import datetime, timezone

# Windows 下强制 UTF-8 输出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── 项目根目录 ──────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 排除的目录/文件（与 update_utils.py _EXCLUDED_DIRS/_EXCLUDED_FILES 保持一致） ──
EXCLUDED_DIRS = {
    "plugins",
    "__pycache__",
    ".git",
    "_update_staging",
    "backups",
    ".codebuddy",
    "exercise_sessions",
    "tools",
    "docs",
    "screenshots",
    "web",
    "extensions",
    "generated-images",
    "Packaged",
    "PRE_Packaged",
    "_patch_tmp",
    "node_modules",
}

EXCLUDED_FILES = {
    "_run_update.bat",
    "_post_update.bat",
    ".gitignore",
    ".gitattributes",
    "requirements.txt",
    "README.md",
    "README.zh.md",
    "LICENSE",
}


# ════════════════════════════════════════════════════════════════════════
#  Git 操作
# ════════════════════════════════════════════════════════════════════════

def run_git(args: list[str]) -> str:
    """执行 git 命令并返回 stdout。"""
    result = subprocess.run(
        ["git"] + args,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        if result.stderr:
            print(f"  [git error] {result.stderr.strip()}")
        return ""
    return result.stdout.strip()


def git_root_ok() -> bool:
    """确认当前目录是 git 工作区。"""
    return bool(run_git(["rev-parse", "--git-dir"]))


def get_all_tags() -> list[str]:
    """获取所有标签（按版本号排序）。"""
    out = run_git(["tag", "-l", "v*", "--sort=-version:refname"])
    return [t for t in out.split("\n") if t] if out else []


def find_from_ref(from_version: str | None = None) -> str | None:
    """
    查找变更起点 ref。
    优先级：CLI --ref > CLI --from > 最新 git tag > commit message 版本号
    """
    # 1. 尝试 git tag
    tags = get_all_tags()
    if from_version:
        # 查找匹配的 tag
        for t in tags:
            if t.lstrip("v") == from_version.lstrip("v"):
                return t
        # 尝试模糊匹配版本号在 commit message 中
        candidate = find_version_commit(from_version)
        if candidate:
            return candidate
        return None

    # 2. 自动找最新 tag
    if tags:
        print(f"  🔖 检测到最新 tag: {tags[0]}")
        return tags[0]

    # 3. 从 config.json 读版本号并回退 patch
    current_ver = read_config_version()
    print(f"  ⚠ 未找到 git tag，从 config.json 读取当前版本: v{current_ver}")
    # 从 commit message 搜索上一个版本号
    parts = current_ver.split(".")
    if len(parts) == 3:
        parts[-1] = str(max(0, int(parts[-1]) - 1))
        prev_ver = ".".join(parts)
        candidate = find_version_commit(prev_ver)
        if candidate:
            return candidate
        # 再回退一个
        parts[-1] = str(max(0, int(parts[-1])))
        prev_ver = ".".join(parts)
        candidate = find_version_commit(prev_ver)
        if candidate:
            return candidate

    return None


def find_version_commit(version: str) -> str | None:
    """在 commit message 中搜索版本号。"""
    pattern = version.lstrip("v")
    # 搜索最近 30 条 commit
    out = run_git(["log", "--oneline", "-30", "--grep", f"v{pattern}", "--format=%H"])
    if out:
        commits = out.split("\n")
        print(f"  📌 在 commit 中找到版本 {pattern}: {commits[0][:7]}")
        return commits[0]

    # 宽松搜索：只搜数字
    out = run_git(["log", "--oneline", "-30", "--grep", pattern, "--format=%H"])
    if out:
        commits = out.split("\n")
        print(f"  📌 宽松匹配到版本 {pattern}: {commits[0][:7]}")
        return commits[0]
    return None


def get_changed_files(from_ref: str, include_uncommitted: bool = False) -> list[tuple[str, str]]:
    """
    获取变更文件列表。
    返回: [(status, path), ...]  status ∈ {A, M, D, R}
    """
    out = run_git(["diff", "--name-status", "--diff-filter=ACMR", from_ref, "HEAD"])
    files: list[tuple[str, str]] = []
    seen: set[str] = set()

    def collect(output: str):
        if not output:
            return
        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            status, path = parts[0], parts[1]
            if path in seen:
                continue
            seen.add(path)

            if status.startswith("R"):
                # 重命名：R100 old_path\tnew_path
                sub_parts = line.split("\t")
                if len(sub_parts) >= 3:
                    path = sub_parts[2]
                status = "A"
            files.append((status, path))

    collect(out)

    # 包含未提交的修改
    if include_uncommitted:
        # 未暂存修改
        ws_out = run_git(["diff", "--name-status", "--diff-filter=ACMR"])
        collect(ws_out)
        # 已暂存但未提交
        idx_out = run_git(["diff", "--cached", "--name-status", "--diff-filter=ACMR"])
        collect(idx_out)
        # 未跟踪新文件
        untracked = run_git(["ls-files", "--others", "--exclude-standard"])
        if untracked:
            for line in untracked.split("\n"):
                line = line.strip()
                if not line or line in seen:
                    continue
                seen.add(line)
                files.append(("A", line))

        if ws_out or idx_out:
            print(f"  📝 已包含工作区未提交的变更")

    if not out and not include_uncommitted:
        print("  ⚠ git diff 无输出（尝试 --include-uncommitted 或 --no-verify）")

    return files


def is_excluded(path: str) -> bool:
    """判断文件/路径是否应被排除。"""
    parts = path.replace("\\", "/").split("/")
    # 检查根目录排除
    if parts[0] in EXCLUDED_DIRS:
        return True
    # 嵌套排除（如 workers/__pycache__/...）
    for p in parts:
        if p in EXCLUDED_DIRS:
            return True
    # 文件名排除
    if parts[-1] in EXCLUDED_FILES:
        return True
    # 排除 .pyc .pyo
    if parts[-1].endswith((".pyc", ".pyo")):
        return True
    # 排除 update_*.zip
    if re.match(r"update_v.+_to_v.+\.zip$", parts[-1]):
        return True
    # 排除示例配置
    if parts[-1].endswith(".example.json"):
        return True
    return False


# ════════════════════════════════════════════════════════════════════════
#  版本号 / config.json
# ════════════════════════════════════════════════════════════════════════

def read_config_version() -> str:
    """从 config/config.json 读取版本号。"""
    path = os.path.join(PROJECT_ROOT, "config", "config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("version", "1.0.0")


def bump_patch(version: str) -> str:
    """patch 号 +1。"""
    parts = version.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def bump_minor(version: str) -> str:
    """minor 号 +1，patch 归零。"""
    parts = version.split(".")
    parts[1] = str(int(parts[1]) + 1)
    parts[2] = "0"
    return ".".join(parts)


def bump_major(version: str) -> str:
    """major 号 +1，minor/patch 归零。"""
    parts = version.split(".")
    parts[0] = str(int(parts[0]) + 1)
    parts[1] = "0"
    parts[2] = "0"
    return ".".join(parts)


def write_config_version(new_version: str):
    """将新版本号写回 config.json。"""
    path = os.path.join(PROJECT_ROOT, "config", "config.json")
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["version"] = new_version
    config["last_viewed_intro_version"] = new_version
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"  📝 config.json version → {new_version}")


# ════════════════════════════════════════════════════════════════════════
#  SHA256
# ════════════════════════════════════════════════════════════════════════

def compute_sha256(filepath: str) -> str:
    """计算文件 SHA256。"""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ════════════════════════════════════════════════════════════════════════
#  Release Notes
# ════════════════════════════════════════════════════════════════════════

def auto_release_notes(from_ref: str, to_version: str) -> str:
    """从 git commit messages 自动生成 release notes。"""
    out = run_git(["log", "--oneline", f"{from_ref}..HEAD", "--no-merges"])
    if not out:
        return f"## v{to_version}\n\n- 未记录变更详情"

    lines = []
    for line in out.split("\n"):
        line = line.strip()
        if not line:
            continue
        # 移除 commit hash
        match = re.match(r"^[0-9a-f]+\s+(.+)$", line)
        if match:
            msg = match.group(1)
            # 分类前缀
            if msg.startswith("feat:"):
                lines.append(f"- ✨ {msg[5:].strip()}")
            elif msg.startswith("fix:"):
                lines.append(f"- 🐛 {msg[4:].strip()}")
            elif msg.startswith("refactor:"):
                lines.append(f"- ♻ {msg[9:].strip()}")
            elif msg.startswith("style:"):
                lines.append(f"- 💄 {msg[6:].strip()}")
            elif msg.startswith("perf:"):
                lines.append(f"- ⚡ {msg[5:].strip()}")
            else:
                lines.append(f"- {msg}")

    header = f"## v{to_version}"
    result = header + "\n" + "\n".join(lines)
    # 清理无效代理字符（Windows PowerShell 输出可能带入）
    result = result.encode("utf-8", errors="replace").decode("utf-8")
    return result


def load_release_notes_from_file(filepath: str) -> str | None:
    """从文件读取 release notes。"""
    path = os.path.join(PROJECT_ROOT, filepath) if not os.path.isabs(filepath) else filepath
    if not os.path.isfile(path):
        print(f"  ⚠ 文件不存在: {path}")
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


# ════════════════════════════════════════════════════════════════════════
#  主流程
# ════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="自动生成 StarDebate 增量更新补丁 ZIP（基于 git）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python tools/gen_patch.py                          # 全自动
  python tools/gen_patch.py --from v6.3.3            # 指定 from
  python tools/gen_patch.py --to v7.0.0 -b           # 指定 to + 升版本号
  python tools/gen_patch.py --since "2 days ago"     # 按时间范围
  python tools/gen_patch.py --dry-run                # 仅预览
  python tools/gen_patch.py -n release_notes.md      # 从文件读 release notes
        """,
    )
    parser.add_argument("--from", dest="from_ver", help="起始版本号 (如 v6.3.3 或 6.3.3)")
    parser.add_argument("--to", dest="to_ver", help="目标版本号 (如 v6.3.4 或 6.3.4)，默认 patch+1")
    parser.add_argument("--ref", help="git 范围 (如 v6.3.3..v6.3.4 或 v6.3.3 或 v6.3.3..HEAD)")
    parser.add_argument("--since", help="按时间范围 (如 '2 days ago', '2026-06-20')")
    parser.add_argument("--include-uncommitted", "-u", action="store_true",
                        help="同时包含工作区未提交的修改 (git diff + git status)")
    parser.add_argument("--bump-version", "-b", action="store_true", help="生成 ZIP 后同步更新 config.json 版本号")
    parser.add_argument("--bump-minor", action="store_true", help="目标版本为 minor+1")
    parser.add_argument("--bump-major", action="store_true", help="目标版本为 major+1")
    parser.add_argument("--notes", "-n", help="Release Notes 文件路径 (.md)")
    parser.add_argument("--notes-auto", "-a", action="store_true", help="从 git commits 自动生成 release notes")
    parser.add_argument("--dry-run", "-d", action="store_true", help="仅预览变更文件列表，不生成 ZIP")
    parser.add_argument("--no-verify", action="store_true", help="跳过文件存在性校验")
    parser.add_argument("--output-dir", "-o", default=PROJECT_ROOT, help="ZIP 输出目录 (默认项目根目录)")
    args = parser.parse_args()

    # ── 0. 检查 git 环境 ──
    if not git_root_ok():
        print("❌ 当前目录不是 git 工作区")
        sys.exit(1)

    # ── 1. 确定 from_ref ──
    from_ref = None
    if args.ref:
        from_ref = args.ref.split("..")[0] if ".." in args.ref else args.ref
    elif args.since:
        # 找到 since 时间点之前的最后一个 commit
        out = run_git(["rev-list", "-1", "--before", args.since, "HEAD"])
        if out:
            from_ref = out
            print(f"  🕐 since '{args.since}' → commit {from_ref[:7]}")
    else:
        from_ref = find_from_ref(args.from_ver)

    if not from_ref:
        print("❌ 无法确定变更起点。请使用 --from 或 --ref 指定。")
        print("  提示：也可以先打一个 git tag: git tag v6.3.3")
        sys.exit(1)

    # ── 2. 确定版本号 ──
    from_version = args.from_ver.lstrip("v") if args.from_ver else read_config_version()
    # 尝试从 tag 名提取
    if from_ref.startswith("v"):
        from_version = from_ref.lstrip("v")

    if args.to_ver:
        to_version = args.to_ver.lstrip("v")
    elif args.bump_major:
        to_version = bump_major(from_version)
    elif args.bump_minor:
        to_version = bump_minor(from_version)
    else:
        to_version = bump_patch(from_version)

    print(f"\n{'='*60}")
    print(f"  StarDebate Patch Generator")
    print(f"  {from_version} → {to_version}")
    print(f"  From ref: {from_ref}")
    print(f"{'='*60}\n")

    # ── 3. 获取变更文件 ──
    print("📂 扫描变更文件...")
    changed = get_changed_files(from_ref, include_uncommitted=args.include_uncommitted)

    if not changed:
        print("  ✅ 无变更文件，无需生成补丁")
        return

    # 分类 + 排除
    modified = []
    added = []
    deleted = []
    skipped = []

    for status, path in changed:
        if is_excluded(path):
            skipped.append((status, path))
            continue
        if status in ("M",):
            modified.append(path)
        elif status in ("A", "C"):
            added.append(path)
        elif status in ("D",):
            deleted.append(path)
        elif status.startswith("R"):
            added.append(path)

    # 确保 config.json 始终包含（如果有变更）
    config_path = "config/config.json"
    chlog_path = "config/changelog.html"

    print(f"\n  修改 ({len(modified)} 项):")
    for p in modified:
        print(f"    [M] {p}")
    print(f"  新增 ({len(added)} 项):")
    for p in added:
        print(f"    [A] {p}")
    if deleted:
        print(f"  删除 ({len(deleted)} 项):")
        for p in deleted:
            print(f"    [D] {p}")
    if skipped:
        print(f"  已跳过 ({len(skipped)} 项):")
        for s, p in skipped:
            print(f"    [-] [{s}] {p}")

    if args.dry_run:
        print(f"\n  🏁 DRY RUN — 未生成 ZIP")
        return

    # ── 4. 校验文件存在性 ──
    if not args.no_verify:
        for p in modified + added:
            full = os.path.join(PROJECT_ROOT, p)
            if not os.path.isfile(full):
                print(f"\n  ❌ 文件缺失: {p}")
                print(f"     请确认文件存在或使用 --no-verify 跳过校验")
                sys.exit(1)

    # ── 5. 构建 changes 列表 + 计算 SHA256 ──
    print("\n🔐 计算 SHA256...")
    changes_list = []

    for rel_path in modified:
        src = os.path.join(PROJECT_ROOT, rel_path)
        sha = compute_sha256(src)
        changes_list.append({"action": "modify", "path": rel_path, "sha256": sha})
        print(f"  [M] [{sha[:12]}] {rel_path}")

    for rel_path in added:
        src = os.path.join(PROJECT_ROOT, rel_path)
        sha = compute_sha256(src)
        changes_list.append({"action": "add", "path": rel_path, "sha256": sha})
        print(f"  [A] [{sha[:12]}] {rel_path}")

    for rel_path in deleted:
        changes_list.append({"action": "delete", "path": rel_path, "sha256": ""})
        print(f"  [D] {rel_path}")

    # ── 6. 处理 release notes ──
    if args.notes:
        release_notes = load_release_notes_from_file(args.notes)
        if not release_notes:
            sys.exit(1)
    elif args.notes_auto:
        release_notes = auto_release_notes(from_ref, to_version)
        print(f"\n📝 自动生成 Release Notes (来自 git commits):")
        print(release_notes[:500])
    else:
        # 交互式输入
        print(f"\n📝 请输入 Release Notes (输入 END 结束，留空使用自动生成):")
        lines = []
        while True:
            try:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            except (EOFError, KeyboardInterrupt):
                break
        if lines:
            release_notes = "\n".join(lines)
        else:
            release_notes = auto_release_notes(from_ref, to_version)
            print("  (使用自动生成)")

    # ── 7. 构建 manifest ──
    # 清理所有字符串中的代理字符（Windows 终端输出可能含 \udcXX）
    def _sanitize(obj):
        if isinstance(obj, str):
            return obj.encode("utf-8", errors="replace").decode("utf-8")
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(i) for i in obj]
        return obj

    manifest = {
        "from_version": from_version,
        "to_version": to_version,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "min_app_version": from_version,
        "changes": _sanitize(changes_list),
        "release_notes": _sanitize(release_notes),
    }

    # ── 8. 生成 ZIP ──
    zip_name = f"update_v{from_version}_to_v{to_version}.zip"
    zip_path = os.path.join(args.output_dir, zip_name)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for entry in changes_list:
            if entry["action"] == "delete":
                continue
            rel_path = entry["path"]
            src = os.path.join(PROJECT_ROOT, rel_path)
            zf.write(src, f"new_files/{rel_path}")

    sz_kb = os.path.getsize(zip_path) / 1024

    # ── 9. 可选：更新 config.json ──
    if args.bump_version:
        write_config_version(to_version)

    # ── 10. 输出结果 ──
    print(f"\n{'='*60}")
    print(f"  ✅ 补丁已生成")
    print(f"  📦 {zip_name}")
    print(f"  📏 {sz_kb:.1f} KB")
    print(f"  📝 {len(modified)} 修改 + {len(added)} 新增 + {len(deleted)} 删除")
    print(f"  📍 {zip_path}")
    print(f"\n  💡 下一步:")
    if args.bump_version:
        print(f"     git add config/config.json && git commit -m 'chore: bump version to v{to_version}'")
    print(f"     git tag v{to_version}")
    print(f"     git push --tags")
    print(f"     将 {zip_name} 放入软件根目录，启动时自动检测")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
