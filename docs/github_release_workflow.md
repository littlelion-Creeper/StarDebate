# StarDebate GitHub Release 发布流程

> 供 AI 助手参考，确保每次发布流程一致。

---

## 1. 前置条件

- 所有变更已 commit 并 push 到 `main`
- `config/config.json` 中的 `version` 已更新
- `config/changelog.html` 已追加当前版本条目

---

## 2. 打标签

```bash
# 找到上一个版本的 commit
git log --oneline -5

# 为上一个版本补标签（如不存在）
git tag v<prev_version> <commit_hash>

# 为当前版本打标签
git tag v<current_version>

# 推送所有标签
git push origin --tags
```

---

## 3. 生成增量补丁包

```bash
python tools/gen_patch.py --from v<prev_version> --to <current_version> -a --no-verify
```

参数说明：
- `--from v6.3.3` — 起始版本 tag
- `--to 6.4.0` — 目标版本号（数字，不带 v）
- `-a` — 从 git commits 自动生成 release notes（仅占位用）
- `--no-verify` — 跳过文件存在性校验（补丁中包含新增文件的目录）

输出：`update_v<prev>_to_v<current>.zip` 到项目根目录。

> ⚠️ **命名规范**：`gen_patch.py` 生成 `update_` 前缀的 ZIP，**上传到 GitHub Release 时保持原名 `update_` 前缀**，链式更新器与本地检测均匹配 `update_.*\.zip`。

---

## 4. 获取 GitHub Token

Token 存储在 git credential manager 中：

```python
import subprocess
r = subprocess.run(
    ['git', 'credential', 'fill'],
    input=b'protocol=https\nhost=github.com\n\n',
    capture_output=True
)
# 从 r.stdout 中提取 password= 行
```

当前 Token 以 `gho_` 开头。

---

## 5. 创建 Release

### 5.1 写入 Release Body

```python
import json

notes = '''## 🎉 StarDebate v<version> 发布！
...
'''
body = {
    'tag_name': 'v<version>',
    'name': '🎉 StarDebate v<version>',
    'body': notes,
    'draft': False,
    'prerelease': False,
}
with open('_release_body.json', 'w', encoding='utf-8') as f:
    json.dump(body, f, ensure_ascii=False)
```

### 5.2 创建 Release API 调用

```python
import json, urllib.request

token = '<token>'
with open('_release_body.json', 'r', encoding='utf-8') as f:
    body = json.load(f)

req = urllib.request.Request(
    'https://api.github.com/repos/Chapin-Y/StarDebate/releases',
    data=json.dumps(body).encode('utf-8'),
    headers={
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    },
)
resp = urllib.request.urlopen(req)
result = json.loads(resp.read().decode())
# 保存 result['id'] 用于上传附件
```

### 5.3 上传补丁附件

```python
import json, os, urllib.request

token = '<token>'
zip_path = 'update_v<prev>_to_v<current>.zip'
with open(zip_path, 'rb') as f:
    zip_data = f.read()

release_id = <release_id>  # 从上一步获取
file_name = os.path.basename(zip_path)
url = f'https://uploads.github.com/repos/Chapin-Y/StarDebate/releases/{release_id}/assets?name={file_name}'

req = urllib.request.Request(
    url, data=zip_data,
    headers={
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/zip',
        'Content-Length': str(len(zip_data)),
    },
    method='POST',
)
resp = urllib.request.urlopen(req)
json.loads(resp.read().decode())
```

---

## 6. Release Body 格式

严格按以下结构（Markdown），对照 `config/changelog.html` 当前版本条目编写：

```markdown
## 🎉 StarDebate vX.X.X 发布！

<亮点概括段落，1-2 句话说明本次最主要的变化>

---

### ✨ 新增

<逐条列出，每条格式：- **<标题>** — <详细说明>（40字以内）>

### ⚡ 优化

### 🛠 修复

### 📦 附件说明

本 Release 附带增量补丁包 update_v<prev>_to_v<current>.zip（<大小>）：
- 从 v<prev> 升级的用户，将 zip 放入软件根目录，重启即自动检测
- 其他版本的用户请下载最新安装包或逐版本升级
```

分类规则：
- **✨ 新增** — 全新功能、新文件、新模块
- **⚡ 优化** — 现有功能改进、性能优化、UI 调整、默认值变更
- **🛠 修复** — Bug 修复
- **📦 附件说明** — 补丁包信息 + 使用指引（固定格式）

---

## 7. 清理临时文件

发布完成后删除：
- `_release_body.json`
- `_release_create.py`
- `_release_upload_asset.py`
- `_release_upload.json`

项目根目录下的 `update_v<prev>_to_v<current>.zip` **保留**（供用户本地使用）。

---

## 历史发布记录

| 版本 | 日期 | 补丁包 |
|---|---|---|
| v6.4.0 | 2026-06-28 | `update_v6.3.3_to_v6.4.0.zip`（157.8 KB） |
