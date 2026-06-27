# StarDebate 更新补丁封装指南

> 版本：v2.3.0 | 适用于更新器 v5.5.0+

---

## 目录

1. [补丁格式规范](#1-补丁格式规范)
2. [manifest.json 详解](#2-manifestjson-详解)
3. [封装步骤](#3-封装步骤)
4. [使用 gen_version_patch.py 快速生成](#4-使用-gen_version_patchpy-快速生成)
5. [手动封装完整补丁](#5-手动封装完整补丁)
6. [校验与测试](#6-校验与测试)
7. [分发方式](#7-分发方式)
8. [常见问题](#8-常见问题)

---

## 1. 补丁格式规范

更新补丁是一个标准 ZIP 文件，推荐命名格式为 `update_v{旧版本}_to_v{新版本}.zip`。

### 1.1 ZIP 目录结构

```
update_v5.0.0_to_v5.1.0.zip
├── manifest.json                         # 必需：补丁元信息 + 变更清单
└── new_files/                            # 所有新增/修改的文件
    ├── workers/app_config/config_manager.py
    ├── style/themes/notion_dark/main.qss
    ├── config/config.json                 # 配置可更新（自动备份）
    └── icon/common/star.svg
```

**关键约束：**
- `manifest.json` 必须放在 ZIP **根目录**
- 所有新增/修改的文件必须放在 `new_files/` 目录下，保持与项目根目录相同的相对路径
- `new_files/` 前缀由 `update_manager.py` 的 `_NEW_FILES_DIR = "new_files"` 常量定义，不可更改

### 1.2 文件名自动检测

软件启动时会扫描根目录下所有符合正则的 `.zip` 文件：

```
^update_v(.+?)_to_v(.+?)\.zip$
```

匹配示例：
- ✅ `update_v5.0.0_to_v5.1.0.zip`
- ✅ `update_v5.0.0_to_v5.5.0.zip`
- ❌ `patch_v5.0.0.zip`（不匹配命名规则）
- ❌ `my_update_5.0.0_to_5.1.0.zip`（缺少 `v` 前缀）

> 即使文件名不匹配规则，用户仍可通过设置页「选择更新包」按钮手动安装。最终兼容性由 `manifest.json` 内的 `from_version` / `to_version` 字段决定。

---

## 2. manifest.json 详解

### 2.1 完整结构

```json
{
  "from_version": "5.0.0",
  "to_version": "5.1.0",
  "created_at": "2026-06-22",
  "min_app_version": "5.0.0",
  "changes": [
    {
      "action": "modify",
      "path": "workers/app_config/config_manager.py",
      "sha256": "abc123def456..."
    },
    {
      "action": "add",
      "path": "workers/updater/updater.py",
      "sha256": "789012ghi345..."
    },
    {
      "action": "delete",
      "path": "workers/legacy/old_handler.py"
    }
  ],
  "release_notes": "## v5.1.0\n- 新增更新器功能\n- 问题修复"
}
```

### 2.2 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|:----:|------|
| `from_version` | string | 是 | 补丁适用的基础版本号。**严格等于**当前软件版本才能安装 |
| `to_version` | string | 是 | 补丁升级到的目标版本号。`config.json` 中的 `version` 和 `last_viewed_intro_version` 字段会在更新时自动更新（由字段级合并的白名单 `_FORCE_UPDATE_KEYS` 控制），但仍需在 changes 中显式包含 `config/config.json` 的 modify 操作 |
| `created_at` | string | 否 | 补丁创建日期，建议 `YYYY-MM-DD` 格式 |
| `min_app_version` | string | 否 | 补丁要求的最低应用版本（用于未来兼容性检查） |
| `changes` | array | 是 | 变更清单，至少包含 1 项。见下方说明 |
| `release_notes` | string | 否 | 发行说明（Markdown 格式），在更新弹窗中显示 |

### 2.3 change 条目

每个变更条目是一个对象，格式如下：

#### modify（修改文件）

```json
{
  "action": "modify",
  "path": "workers/app_config/config_manager.py",
  "sha256": "abc123..."
}
```

- ZIP 内文件路径：`new_files/workers/app_config/config_manager.py`
- `sha256` 是**新文件**的 SHA256 哈希值，用于安装前校验
- 更新器会校验 SHA256 → 覆盖原文件

#### add（新增文件）

```json
{
  "action": "add",
  "path": "workers/updater/updater.py",
  "sha256": "def456..."
}
```

- 与 modify 结构相同
- 如果目标路径已存在，会被覆盖

#### delete（删除文件）

```json
{
  "action": "delete",
  "path": "workers/legacy/old_handler.py"
}
```

- 不需要 `sha256` 字段
- 如果目标路径不存在，静默跳过（不报错）

### 2.4 排除规则

以下路径即使出现在 `changes` 中也会被更新器自动跳过：

| 路径 | 说明 |
|------|------|
| `plugins/` | 插件独立管理，不参与应用更新 |
| `__pycache__/` | Python 缓存，更新后自动清理 |
| `.git/` | Git 仓库目录 |
| `.codebuddy/` | CodeBuddy 工作目录 |
| `exercise_sessions/` | 训练会话记录 |
| `backups/` | 配置备份目录 |
| `_update_staging/` | 更新暂存目录 |
| 以 `.` 开头的文件 | 隐藏文件 |

> **特别说明**：`update_patch_applier.py` 永远不应出现在 changes 中。该文件是更新进程的执行脚本，必须在所有版本中保持稳定可用。如果需要更新更新器，更新 `update_manager.py` 和 `update_utils.py` 即可（它们在主进程侧运行，退出前已被替换）。
>
> **自举问题**：更新 `update_utils.py` 中的合并逻辑（字段级合并）时，第一次运行新代码需要**一次额外的更新**来生效。这是因为当前进程内存中的是旧版代码，新代码只有在**重启后**才会加载。首次更新时通过 `update_manager.py` 的 hot-patch（`step_4()` 中临时移除合并路径）来确保 `config.json` 被正确覆盖。

---

## 3. 封装步骤

### 3.1 准备工作

1. **确认当前版本**：查看 `config/config.json` 中的 `version` 字段
2. **确定目标版本**：例如 `5.5.0`
3. **对比文件差异**：列出所有从当前版本到目标版本发生变更的文件

### 3.2 计算 SHA256

每个新增/修改的文件都需要计算 SHA256：

```bash
# Windows PowerShell
Get-FileHash -Algorithm SHA256 workers\app_config\config_manager.py | Format-List

# 或使用 Python
python -c "import hashlib; h=hashlib.sha256(); [h.update(open(f,'rb').read()) for f in ['file.py']]; print(h.hexdigest())"
```

### 3.3 组装 ZIP

按以下结构手动组装：

```
update_v5.0.0_to_v5.5.0.zip
├── manifest.json
└── new_files/
    ├── config/config.json
    ├── workers/app_config/config_manager.py
    └── style/themes/notion_dark/updater.qss
```

可以使用 Python、7-Zip 或任意支持标准 ZIP 的工具创建。注意：
- 使用 **Deflate 压缩**（标准 ZIP，不要用 7z 格式）
- 保持路径大小写与源文件一致
- 不要加密或设置密码

### 3.4 更新日志同步规则

每次创建更新补丁时，**必须同步更新 `config/changelog.html`**，将新版本的 release_notes 写入其中。

#### 为什么必须更新？

`config/changelog.html` 是软件内置的更新日志页面（在介绍引导页第 4 步展示），独立于 `manifest.json` 中的 `release_notes`（后者仅在更新弹窗中显示一次）。如果只更新 `release_notes` 而不更新 `changelog.html`，用户下次打开引导页时仍会看到旧的更新日志。

#### 更新规则

1. **changelog.html 必须包含全部历史版本的记录**，不能只保留最新版本
2. **每个版本条目必须包含**：
   - 版本号（如 `v6.1.3`）
   - 变更条目（每个条目带分类徽章：`badge-new` 新增 / `badge-fix` 修复 / `badge-opt` 优化）
3. **最新版本必须标记 `badge-new`**（带绿色脉冲圆点动画）
4. **changelog.html 应始终随补丁包一同分发**，即 `changes` 中必须包含 `config/changelog.html` 的 modify 操作

#### 操作示例

每次创建补丁时，在修改 `config/config.json` 版本号的同时，也修改 `config/changelog.html`：

```html
<div class="version-node">
  <div class="version-header">
    <span class="version-tag">v6.1.3</span>
    <span class="version-badge badge-new">最新</span>
  </div>
  <ul>
    <li><span class="version-badge badge-fix">修复</span> 变更说明</li>
  </ul>
</div>
```

将这段 HTML 插入到 `.timeline` 容器的**最顶部**，并将之前最旧版本的 `badge-new` 移除。

---

## 4. 使用 gen_version_patch.py 快速生成

项目提供了一个参考脚本 `tools/gen_version_patch.py`，用于快速生成**仅更新版本号**的补丁。

### 4.1 用法

```bash
cd StarDebate
python tools/gen_version_patch.py
```

### 4.2 自定义

修改脚本中以下三个值即可生成不同的版本更新：

```python
# 第 27 行：目标版本号
new_config["version"] = "5.5.0"

# 第 46-47 行：manifest 版本信息
"from_version": "5.0.0",
"to_version": "5.5.0",

# 第 57 行：发行说明
"release_notes": "## v5.5.0\n- 新增功能\n- 问题修复"
```

### 4.3 局限性

该脚本**仅生成版本号更新补丁**（只修改 `config/config.json`）。如果补丁涉及多个文件的增删改，请使用手动封装方式。

### 4.4 参考示例：`_update_staging/build_v6.1.0_patch.py`

项目提供了完整的多人文件补丁构建示例供参考：

```
_update_staging/build_v6.1.0_patch.py
```

该脚本演示了：
- 如何声明 add/modify/delete 三种变更类型
- 如何在脚本中计算 SHA256
- 如何在内存中构建 manifest.json 并写入 ZIP
- 如何使用 `zipfile.ZIP_DEFLATED` 压缩

可以直接复制修改 `FILES` 列表和版本号来生成自已的补丁。

---

## 5. 手动封装完整补丁

对于涉及多个文件变更的完整更新，推荐使用以下 Python 脚本模板生成。

> **快捷参考**：项目已提供完整的多文件补丁构建示例 `_update_staging/build_v6.1.0_patch.py`（v6.0.8 → v6.1.0，19 个变更），可直接复制修改。

### 5.1 通用生成脚本模板

将此文件保存为 `tools/build_patch.py`（仅作参考，不要直接 git 跟踪）：

```python
import os, sys, json, zipfile, hashlib

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FROM_VERSION = "5.0.0"
TO_VERSION = "5.5.0"

# ── 变更清单 ──────────────────────────────────────────────────────────
# 格式: (action, src_path_in_project, zip_entry_path)
#   modify/add: (action, 源文件, new_files/下的目标路径)
#   delete:     (action, 空, 要删除的路径)
CHANGES = [
    ("modify", "config/config.json",           "new_files/config/config.json"),
    ("add",    "workers/updater/updater.py",   "new_files/workers/updater/updater.py"),
    ("delete", None,                            "workers/legacy/old_handler.py"),
]

# ── 发行说明 ──────────────────────────────────────────────────────────
RELEASE_NOTES = """## v5.5.0
- 新增更新器功能
- 修复多个问题
"""

def compute_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    tmp_dir = os.path.join(PROJECT_ROOT, "_patch_tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    # 构建 changes 列表
    changes_list = []
    for item in CHANGES:
        action = item[0]
        if action == "delete":
            changes_list.append({"action": "delete", "path": item[2]})
        else:
            src = os.path.join(PROJECT_ROOT, item[1])
            sha = compute_sha256(src)
            changes_list.append({
                "action": action, "path": item[1], "sha256": sha,
            })

    # manifest
    manifest = {
        "from_version": FROM_VERSION,
        "to_version": TO_VERSION,
        "created_at": "2026-06-22",
        "min_app_version": FROM_VERSION,
        "changes": changes_list,
        "release_notes": RELEASE_NOTES,
    }

    # 写 manifest
    manifest_path = os.path.join(tmp_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # 生成 ZIP
    zip_name = f"update_v{FROM_VERSION}_to_v{TO_VERSION}.zip"
    zip_path = os.path.join(PROJECT_ROOT, zip_name)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(manifest_path, "manifest.json")
        for item in CHANGES:
            if item[0] != "delete":
                src = os.path.join(PROJECT_ROOT, item[1])
                zf.write(src, item[2])

    # 清理
    os.remove(manifest_path)
    os.rmdir(tmp_dir)

    print(f"补丁已生成: {zip_name}")
    print(f"  变更: {len(CHANGES)} 项")
    for c in CHANGES:
        print(f"    [{c[0]}] {c[1] if c[1] else c[2]}")
    print(f"\n将补丁文件放入软件根目录，下次启动时将自动检测到更新。")

if __name__ == "__main__":
    main()
```

---

## 6. 校验与测试

### 6.1 手动校验 ZIP 结构

生成补丁后，用此命令验证结构：

```bash
python -c "
import zipfile
z = zipfile.ZipFile('update_v5.0.0_to_v5.5.0.zip')
z.printdir()
m = z.read('manifest.json')
print('--- manifest.json ---')
print(m.decode('utf-8'))
"
```

期望输出：

```
File Name                                             Size
manifest.json                                        398
new_files/config/config.json                         108
```

### 6.2 测试流程（同进程软重启版）

1. 将补丁 ZIP 放入软件根目录（`StarDebate/`）
2. 重启软件
3. 等待 1-2 秒后应弹出 **UpdateFoundDialog**，显示版本号对比
4. 点击「立即更新」
5. 观察进度面板（校验 → 备份 → 解压 → 覆盖文件 → 清理）
6. 弹出更新完成对话框，点击「确定」后软件自动关闭
7. 手动重新启动 StarDebate
8. 检查 `config/config.json` 中版本号是否更新
9. 验证 JSON 字段级合并：用户已有的配置（主题、开发者模式等）不会被覆盖，仅补全新版本新增的字段；`version` 和 `last_viewed_intro_version` 会始终更新为补丁中的新值
10. （可选）转到设置 → 关于 → **配置备份管理**，查看旧配置备份列表

### 6.3 回滚测试

更新前 `config/` 已被全量备份到 `backups/v{旧版本}_config/`：
- 手动删除 `config/` 目录
- 将备份目录复制回 `config/`
- 重启软件，配置应完全恢复

---

## 7. 分发方式

### 7.1 本地分发

直接将 `.zip` 文件分发给用户，用户将其放入软件根目录即可。

### 7.2 内部更新机制（直接覆盖 + 手动重启）

更新流程完全运行在主进程内，**不依赖 .bat 脚本或子进程**：

```
用户确认更新
  ↓
1. SHA256 校验 ──── 监视钩子: updater.validate
2. 备份 config/  ──── 监视钩子: updater.backup
3. 解压到暂存区
4. 直接覆盖 .py 等文件（Python 不锁定 .py 文件）
5. 删除旧文件
6. 清理 __pycache__ ──── 监视钩子: updater.done
7. 弹出更新完成对话框
   ↓
8. 用户点击「确定」→ 自动关闭主窗口
9. 用户手动重新启动 StarDebate
```

所有监视钩子通过 `LogClient.monitor()` 投递到独立 LogService 进程。

### 7.3 注意事项

| 场景 | 行为 |
|------|------|
| 当前版本 ≠ from_version | 弹窗提示"版本不匹配"，拒绝安装 |
| 补丁 SHA256 不匹配 | 弹窗提示"SHA256 校验失败"，停止更新 |
| 补丁已忽略 | 静默跳过，需在设置页重新启用 |
| 更新过程中断电/崩溃 | 下次启动弹出 RecoveryDialog，提供重新执行或忽略清理 |
| 已保留最近 2 次备份 | 第 3 次更新时自动清理最旧的备份 |
| config 字段级合并 | `config/config.json` 自动合并：保留用户现有字段，`version`/`last_viewed_intro_version` 始终更新，其余仅补全新字段 |

---

## 8. 常见问题

### Q: 为什么文件名必须是 `new_files/` 前缀？

A: `update_manager.py` 的 `_NEW_FILES_DIR` 常量定义为 `"new_files"`，SHA256 校验、解压提取、.bat 脚本生成都基于此常量。更换前缀需要同时修改常量。

### Q: 可以只修改一个文件吗？

A: 可以。changes 列表可以只有 1 个条目。

### Q: 配置备份会覆盖用户修改吗？

A: 备份是在更新**开始前**做的全量快照。更新完成后 config/ 已被新版本文件覆盖。如果用户想恢复旧配置，可以：

1. **通过设置页操作**：转到设置 → 关于 → **配置备份管理**，可直接删除或恢复旧配置备份
2. **手动操作**：从 `backups/` 目录复制回来

### Q: 如何管理旧版本配置备份？

A: 转到设置 → 关于 → **配置备份管理**，提供以下功能：

- **查看备份列表**：显示每个备份的版本号、大小和创建时间
- **单个删除**：每行右侧的「删除」按钮，确认后即时移除
- **恢复配置**：点击「恢复」→ 预览将覆盖的文件列表 → 确认后恢复并自动重启
- **一键清理全部**：底部按钮，带空间释放估算和强调确认

系统默认保留最近 2 次备份，第 3 次更新时自动清理最旧的。

### Q: `.pyc` 文件需要手动清理吗？

A: 不需要。更新进程执行完成后会自动递归清理项目根目录下所有 `__pycache__` 目录。

### Q: 插件目录会被更新覆盖吗？

A: 不会。`plugins/` 在排除列表中，补丁无法修改/删除插件文件。插件需要独立更新。

### Q: 补丁文件在更新完成后会自动删除吗？

A: 不会。更新完成后原 `.zip` 文件仍留在根目录。用户可手动删除，或在下一次启动时通过弹窗的"取消"操作→重命名为 `.zip.ignore`。

### Q: 更新后 config.json 中的用户设置（主题、开发者模式等）会被覆盖吗？

A: 不会。自 v2.2.0 起，`config/config.json` 使用**字段级合并**策略：

- `version` 和 `last_viewed_intro_version` **始终**使用补丁中的新值
- 其余字段（主题、最后项目路径、开发者模式等）**保留用户现有值**，仅补全用户尚不存在的字段
- 补丁打包时 `config.json` 只需包含新增/默认字段即可

例如，用户现有配置为：
```json
{"theme": "notion_light", "developer_mode": true}
```
补丁中的配置为：
```json
{"version": "6.2.0", "developer_mode": false, "new_feature_flag": true}
```
合并结果为：
```json
{"theme": "notion_light", "developer_mode": true, "version": "6.2.0", "new_feature_flag": true}
```

注意 `version` 被强制更新为 `6.2.0`，而 `developer_mode` 保留了用户的 `true` 设置。

### Q: `update_manager.py` 中的 hot-patch 有什么用？

A: 这是解决**更新器自举问题**（bootstrap）的临时方案。当更新器需要更新自身（如 `_merge_json_file` 增加新逻辑）时，第一次更新时**内存中运行的仍是旧版代码**。

`update_manager.py` 的 `step_4()` 中在调用 `apply_new_files()` 前执行以下操作：

```python
from workers.updater import update_utils as _uu_mod
_uu_mod._MERGE_JSON_PATHS.discard("config/config.json")
```

这会临时将 `config/config.json` 从字段级合并路径中移除，使本次更新采用直接覆盖（`shutil.copy2`），确保 `version` 能正确更新到新版本号。重启后新的合并逻辑（含 `_FORCE_UPDATE_KEYS` 白名单）才会生效。

### Q: `_FORCE_UPDATE_KEYS` 是什么？

A: 定义在 `update_utils.py` 中的白名单常量：

```python
_FORCE_UPDATE_KEYS = {"version", "last_viewed_intro_version"}
```

字段级合并时，白名单内的字段**始终使用补丁中的新值**，不受"保留用户现有值"规则限制。其他字段（如 `theme`、`developer_mode`、`last_project`）保留用户设置。

### Q: 如何验证补丁的 SHA256 是否计算正确？

A: 校验逻辑等价于以下 Python 代码：

```python
import hashlib
h = hashlib.sha256()
with open("new_files/config/config.json", "rb") as f:
    for chunk in iter(lambda: f.read(65536), b""):
        h.update(chunk)
print(h.hexdigest())
```

确保计算结果与 manifest 中 `sha256` 字段完全一致（不区分大小写）。
