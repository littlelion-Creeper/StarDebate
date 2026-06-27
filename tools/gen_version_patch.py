"""生成版本号更新补丁 (5.0.0 → 5.5.0)

用法: python tools/gen_version_patch.py
输出: StarDebate/update_v5.0.0_to_v5.5.0.zip
"""

import os
import sys
import json
import zipfile
import hashlib


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 读取当前 config.json
    config_path = os.path.join(project_root, "config", "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    current_version = config["version"]
    print(f"当前版本: {current_version}")

    # 创建更新后的 config.json
    new_config = dict(config)
    new_config["version"] = "5.5.0"

    tmp_dir = os.path.join(project_root, "_patch_tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    # 写入 new_files/config/config.json（前缀必须与 update_manager.py 的 _NEW_FILES_DIR 一致）
    new_config_path = os.path.join(tmp_dir, "config.json")
    with open(new_config_path, "w", encoding="utf-8") as f:
        json.dump(new_config, f, ensure_ascii=False, indent=2)

    # 计算 SHA256
    sha256_hash = hashlib.sha256()
    with open(new_config_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256_hash.update(chunk)
    file_sha256 = sha256_hash.hexdigest()

    # 创建 manifest.json
    manifest = {
        "from_version": "5.0.0",
        "to_version": "5.5.0",
        "created_at": "2026-06-22",
        "min_app_version": "5.0.0",
        "changes": [
            {
                "action": "modify",
                "path": "config/config.json",
                "sha256": file_sha256
            }
        ],
        "release_notes": "## v5.5.0\n- 新增本地增量更新器\n- 问题修复与体验优化"
    }

    manifest_path = os.path.join(tmp_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # 生成 ZIP
    zip_name = f"update_v5.0.0_to_v5.5.0.zip"
    zip_path = os.path.join(project_root, zip_name)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # manifest.json 放根目录
        zf.write(manifest_path, "manifest.json")

        # 文件放 new_files/ 目录（前缀必须与 update_manager.py 的 _NEW_FILES_DIR 一致）
        zf.write(new_config_path, "new_files/config/config.json")

    # 清理临时文件
    os.remove(new_config_path)
    os.remove(manifest_path)
    os.rmdir(tmp_dir)

    size_kb = os.path.getsize(zip_path) / 1024
    print(f"补丁已生成: {zip_name} ({size_kb:.1f} KB)")
    print(f"  当前版本: 5.0.0 → 5.5.0")
    print(f"  变更: 1 modify (config/config.json)")
    print(f"  SHA256: {file_sha256[:16]}...")
    print(f"\n将补丁文件放入软件根目录，下次启动时将自动检测到更新。")


if __name__ == "__main__":
    main()
