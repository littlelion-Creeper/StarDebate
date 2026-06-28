# .stp 插件包格式规范

> 版本：v1.0 | 生效时间：2026-06-09 | 适用：StarDebate 1.0+

---

## 目录

1. [概述](#1-概述)
2. [文件格式](#2-文件格式)
3. [内部目录结构](#3-内部目录结构)
4. [plugin.json 完整 schema](#4-pluginjson-完整-schema)
5. [校验和生成算法](#5-校验和生成算法)
6. [安装流程](#6-安装流程)
7. [卸载行为](#7-卸载行为)
8. [权限系统](#8-权限系统)
9. [依赖系统](#9-依赖系统)
10. [生命周期](#10-生命周期)
11. [附录](#11-附录)

---

## 1. 概述

`.stp`（StarPlugin Package）是 StarDebate 的插件封装格式，旨在用**单文件**分发、安装和管理插件。

设计目标：

- **单文件分发**：所有插件资源打包为一个 `.stp` 文件
- **完整性校验**：内置 SHA256 校验和，安装时检测文件是否篡改
- **权限透明**：安装前展示插件声明的权限列表，用户确认后才安装
- **依赖管理**：声明式依赖，缺失依赖阻止安装
- **增量升级**：同名 `plugin_id` 自动进入升级流程

---

## 2. 文件格式

### 2.1 容器格式

`.stp` 文件本质是一个标准 **Zip 压缩包**，采用 Zip 格式（2.0+），兼容所有标准 Zip 工具。

### 2.2 扩展名

- 文件扩展名：`.stp`
- 安装器通过 Zip 注释识别，而非依赖扩展名

### 2.3 Zip 注释标识

打包器**必须**在 Zip 文件的注释（`comment`）字段写入以下内容以标识其为合法 .stp 文件：

```
StarPlugin
```

读取规则：

- 安装器先用 `zipfile.ZipFile` 打开文件
- 读取 `zipfile.comment`，解码为 UTF-8 字符串
- 如果注释精确匹配 `"StarPlugin"`，则视为合法 .stp 文件
- 否则拒绝安装并提示"不是有效的 .stp 文件"

### 2.4 压缩方式

- 使用 `zipfile.ZIP_DEFLATED` 压缩（Deflate 算法）
- 未来可扩展为 `ZIP_BZIP2` 或 `ZIP_LZMA`，需在 `stp_version` 中声明

### 2.5 无加密

.stp **不采用 Zip 加密**。验证完整性依赖 SHA256 校验和（见第 5 节），而非加密。

---

## 3. 内部目录结构

一个标准的 `.stp` 文件解压后的目录结构如下：

```
my_plugin.stp（解压后）
├── plugin.json        ← 必要：插件元数据 + 校验和
├── main.py            ← 必要：插件入口，须包含 StarDebatePlugin 子类
├── settings.py        ← 可选：插件设置 UI
├── README.md          ← 可选：使用说明
├── CHANGELOG.md       ← 可选：变更日志
├── LICENSE            ← 可选：许可证文件
└── resources/         ← 可选：资源目录
    ├── icon.svg
    ├── icon.png
    └── styles.qss
```

打包规则：

- Zip 根目录**必须**包含 `plugin.json` 和 `main.py`
- `plugin.json` 必须位于 Zip 根目录（不嵌套子目录）
- 其他文件和目录均为可选
- 打包器**不应**包含 `__pycache__/`、`.pyc`、`__MACOSX/`、`.DS_Store` 等临时文件

---

## 4. plugin.json 完整 Schema

### 4.1 字段定义

```json
{
    "name": "快速笔记",
    "plugin_id": "StarDebate.quick_notes",
    "version": "1.0.0",
    "author": "StarDebate",
    "description": "在右侧功能区提供快速笔记面板，支持添加、编辑和删除笔记",
    "main": "main.py",
    "enabled": false,
    "stp_version": "1.0",
    "min_app_version": "1.0.0",
    "checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "tags": ["笔记", "工具"],
    "permissions": [
        "file_read",
        "settings_read",
        "settings_write"
    ],
    "dependencies": {
        "StarDebate.some_plugin": ">=1.0.0"
    },
    "config": {
        "max_notes": 50,
        "auto_save": true,
        "font_size": 14
    }
}
```

### 4.2 字段说明

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `name` | string | ✓ | 插件显示名称（中文/英文均可） |
| `plugin_id` | string | ✓ | 插件唯一标识，格式：`author.plugin_name`（见 4.3 节） |
| `version` | string | ✓ | 语义化版本号，格式 `MAJOR.MINOR.PATCH`（符合 [SemVer](https://semver.org/)） |
| `author` | string | ✓ | 开发者名称 |
| `description` | string | ✓ | 插件功能描述，建议 20-100 字 |
| `main` | string | ✓ | 插件入口文件，相对路径（通常为 `main.py`） |
| `enabled` | bool | ✓ | 安装后强制为 `false`，安装器负责设置 |
| `stp_version` | string | ✓ | `.stp` 格式版本，当前为 `"1.0"` |
| `min_app_version` | string | ✓ | 要求的最低 StarDebate 版本号。不满足时阻止安装 |
| `checksum` | string | ✓ | 所有打包文件内容的 SHA256 十六进制字符串（见第 5 节） |
| `tags` | string[] |  | 插件标签，用于分类和搜索（最多 10 个） |
| `permissions` | string[] |  | 插件声明的权限列表（见第 8 节） |
| `dependencies` | object |  | 插件依赖映射（见第 9 节） |
| `config` | object |  | 插件默认配置（由 `settings.py` 渲染 UI 编辑） |

### 4.3 plugin_id 生成规则

- 格式：`author.plugin_name`
- `author`：使用 `author` 字段值，统一转为小写，去空格（如 `"StarDebate"` → `"stardebate"`）
- `plugin_name`：取 `name` 字段，统一转为小写，去空格
- 示例：`name: "快速笔记"`, `author: "StarDebate"` → `plugin_id: "stardebate.快速笔记"`

### 4.4 版本号比较规则

`min_app_version` 和 `dependencies` 中的版本约束采用 **PEP 440** 风格比较：

- `"1.0.0"`：精确匹配
- `">=1.0.0"`：大于等于
- `">=1.0.0,<2.0.0"`：范围匹配
- 主版本号 `MAJOR` 为 0 时视为预发布版本

---

## 5. 校验和生成算法

### 5.1 打包时（封装工具执行）

1. 遍历插件目录，排除 `__pycache__/`、`.pyc`、`__MACOSX/`、`.DS_Store`、`node_modules/` 等
2. 收集所有需要计算校验和的文件列表（**排除 `plugin.json` 自身**，避免 checksum 字段自引用循环）
3. 按**文件名升序**排序（ASCII 顺序）
4. 按排序后的顺序，将每个文件的**内容字节串**依次拼接
5. 计算拼接结果的整体 SHA256 哈希值
6. 将十六进制字符串写入 `plugin.json` 的 `checksum` 字段
7. 然后将包含 `checksum` 的 `plugin.json` 和其他文件一起打包为 `.stp`

注意事项：

- 排序必须**固定**（文件名升序），否则不同系统上文件遍历顺序不同会导致校验和不一致
- **排除 `plugin.json`**：checksum 只代表其他文件的完整性，`plugin.json` 自身由 Zip 容器的 CRC 保护
- 打包时**先写入 checksum，再打包**，确保 checksum 值正确反映打包前的文件状态

### 5.2 安装时（StarDebate 执行）

1. 解压 .stp 文件到临时目录
2. 读取 `plugin.json` 中的 `checksum` 字段
3. 按**同样的排序规则**收集解压后的文件列表
4. 按排序顺序拼接文件内容，重新计算 SHA256
5. 比对计算结果和 `plugin.json` 中的 `checksum`
6. 不一致 → 拒绝安装，弹出"文件校验失败，插件可能已损坏或被篡改"

### 5.3 伪代码

```python
import hashlib, json, os, zipfile

def compute_checksum(package_dir: str) -> str:
    """计算插件目录下所有文件的 SHA256 总校验和。"""
    files = []
    for root, _, filenames in os.walk(package_dir):
        for f in filenames:
            if should_exclude(f):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, package_dir)
            files.append(rel)
    files.sort()  # 按文件名升序

    hasher = hashlib.sha256()
    for rel in files:
        with open(os.path.join(package_dir, rel), "rb") as fh:
            hasher.update(fh.read())
    return hasher.hexdigest()
```

---

## 6. 安装流程

### 6.1 触发方式

安装可通过以下两种方式触发：

- **拖拽安装**：将 `.stp` 文件拖入 StarDebate 主窗口 → 自动识别 → 弹出安装预览窗口
- **菜单安装**：插件管理面板中点击 "📦 安装插件" 按钮 → 弹出文件选择对话框（过滤器 `*.stp`）→ 弹出安装预览窗口

### 6.2 安装预览窗口

预览窗口内容（从上到下）：

| 区域 | 内容 |
|------|------|
| 标题 | "安装插件" |
| 插件信息 | 名称、作者、版本、`plugin_id`、描述 |
| 权限列表 | 声明权限逐行展示，危险权限（`file_write`、`network`）标红高亮 |
| 依赖检查 | 列出所有依赖及其检查结果（✅ 已安装 / ❌ 缺失）|
| 版本兼容 | 检查 `min_app_version` 是否满足 |
| 校验和状态 | ✅ 校验通过 / ❌ 校验失败（失败时不可安装）|
| 冲突检测 | 如果 `plugin_id` 已存在，显示"将覆盖现有版本 vX.X.X" |
| 操作按钮 | 「取消」/ 「确认安装」（校验失败或依赖缺失时禁用）|

### 6.3 版本兼容检查

```python
def check_compatibility(app_version: str, min_version: str) -> bool:
    """检查 StarDebate 版本是否满足插件要求。"""
    return compare_versions(app_version, min_version) >= 0
```

不满足时，预览窗口显示"需要 StarDebate vX.X+，当前版本 vX.X"，安装按钮禁用。

### 6.4 冲突处理

检测到 `plugin_id` 已存在时，预览窗口底部增加选项：

```
⚠ 插件 "快速笔记"（plugin_id: stardebate.quick_notes）已安装
   当前版本：v1.0.0
   新版本：v1.2.0

   ⊙ 覆盖升级（推荐） — 替换现有插件文件
   ○ 取消安装
   ○ 并列安装 — 自动修改 plugin_id 以避免冲突
```

- 默认选中「覆盖升级」
- 选择「并列安装」时，安装器自动修改解压目录和 `plugin_id`（如 `stardebate.quick_notes_2`）

### 6.5 安装执行

1. 校验通过 + 用户确认
2. 将插件解压到 `plugins/<plugin_id>/` 目录
3. 设置 `plugin.json` 的 `enabled: false`
4. 扫描 `config/plugin_registry.json`，注册插件基本信息
5. 弹出提示："✅ 插件安装完成。请前往「插件管理」启用插件。"

### 6.6 安装失败场景

| 场景 | 行为 |
|------|------|
| 非法文件（非 .stp） | 拒绝，提示"不是有效的 .stp 文件" |
| Zip 注释不匹配 | 拒绝，提示"文件格式不匹配" |
| 校验和不符 | 拒绝，提示"文件已损坏或被篡改" |
| 版本不兼容 | 拒绝，安装按钮禁用 |
| 依赖缺失 | 拒绝，列出缺失依赖 |
| 插件目录写入失败 | 回滚已写入的文件，提示错误 |
| 权限拒绝 | 弹窗提示用户权限不够，建议以管理员身份运行 |

### 6.7 StarDebate 主窗口拖拽识别

StarDebate 主窗口 `__init__` 中调用 `setAcceptDrops(True)`，并重写 `dragEnterEvent` / `dropEvent`：

```python
def dragEnterEvent(self, event):
    if event.mimeData().hasUrls():
        for url in event.mimeData().urls():
            if url.toLocalFile().endswith(".stp"):
                event.acceptProposedAction()
                return

def dropEvent(self, event):
    for url in event.mimeData().urls():
        path = url.toLocalFile()
        if path.endswith(".stp"):
            self._stp_installer.install(path)
```

---

## 7. 卸载行为

用户在插件管理面板中点击「卸载」后：

1. 弹出确认对话框，提供两个选项：

   ```
   ⊕ 卸载插件「快速笔记」
   
   ○ 仅禁用（推荐） — 保留插件文件，从导航栏移除，日后可重新启用
   ○ 彻底删除 — 删除插件目录，不可恢复
   
   [取消]  [确认]
   ```

2. 默认选中「仅禁用」
3. 仅禁用：将 `plugin.json` 中 `enabled` 设为 `false`，从导航栏和注册表中移除
4. 彻底删除：删除整个 `plugins/<plugin_id>/` 目录，从注册表中移除

> 卸载不会清理 `config/` 目录中可能残留的用户配置。后续版本可增加"清理配置"选项。

---

## 8. 权限系统

### 8.1 权限声明

插件开发者在 `plugin.json` 的 `permissions` 数组中声明所需权限：

```json
"permissions": ["file_read", "file_write", "network", "ai_api"]
```

### 8.2 权限列表

| 权限 | 层级 | 说明 |
|------|------|------|
| `file_read` | 安全 | 读取插件目录下的文件（默认已有） |
| `file_write` | ⚠ 危险 | 写入插件目录及 `config/` 外的文件 |
| `network` | ⚠ 危险 | 发起 HTTP/HTTPS 网络请求 |
| `ai_api` | 安全 | 调用 StarDebate 的 AI 接口（由用户 API Key 控制成本） |
| `settings_read` | 安全 | 读取 StarDebate 的全局配置 |
| `settings_write` | 中等 | 修改 StarDebate 的全局配置 |

### 8.3 安装时展示

安装预览窗口以卡片形式展示权限：

```
📋 权限请求
   ✅ file_read        — 读取插件文件
   ✅ ai_api           — 使用 AI 分析功能
   ⚠ file_write       — 写入外部文件（注意：可能修改系统文件）
   ⚠ network          — 访问网络（注意：可能发送数据到外部服务器）
```

- 安全权限前缀显示 ✅
- 危险权限前缀显示 ⚠，文字标红

### 8.4 运行时检查（v4.5.0 已实现）

基于 `PluginSafeAPI` 的 `${_check_permission_or_raise}()` 进行运行时权限检查：

- `call_ai` → 检查 `ai_api`
- `read_file_in_project` → 检查 `file_read`
- `write_file_in_project` → 检查 `file_write`
- `import_file` → 检查 `file_write`
- `delete_file` → 检查 `file_write`
- `summarize_document` → 检查 `ai_api`
- `ai_search` → 检查 `ai_api`
- `export_to_stardebate` → 检查 `file_write`
- `get_api_config` → 检查 `settings_read`

缺少权限时抛出 `PermissionError`，错误信息指明缺失的权限和对应的 API 方法。

> 空权限列表（旧插件未声明）视为全部允许，向后兼容。

---

## 9. 依赖系统

### 9.1 依赖声明

```json
"dependencies": {
    "stardebate.argument_bank": ">=1.0.0",
    "stardebate.debate_timer": ">=1.0.0,<2.0.0"
}
```

- 键：被依赖插件的 `plugin_id`
- 值：版本约束字符串，支持 `>=X`、`>=X,<Y`、`==X`、`*`（任意版本）

### 9.2 安装时检查

1. 遍历 `dependencies` 中所有条目
2. 遍历已安装插件的 `plugin_id` 和 `version`
3. 如果某依赖**未安装**或**版本不满足**，则在预览窗口中标记为 ❌
4. 所有依赖不满足时安装按钮**禁用**
5. 预览窗口展示缺失依赖列表

```
📦 依赖检查
   ❌ stardebate.argument_bank ≥1.0.0  — 未安装
   ✅ stardebate.debate_timer ≥1.0.0   — 已安装 v1.2.0
```

### 9.3 依赖作用范围

MVP 阶段不支持：
- 传递依赖（A 依赖 B，B 依赖 C，不自动检测 C）
- 循环依赖检测
- 自动安装缺失依赖

> 这些功能在引入插件市场后考虑加入。

---

## 10. 生命周期

### 10.1 插件状态机

```
         安装预览 → 安装 → [禁用]
                         ↓
                    [启用] → on_load() → 插件运行中
                         ↓
                    on_unload() → [禁用]
                         ↓
                    卸载确认 → 仅禁用/彻底删除
```

### 10.2 状态说明

| 状态 | 说明 |
|------|------|
| 已安装（禁用） | 文件已存在，但不加载，不注册导航栏 |
| 已启用（运行中） | 插件已加载，注册导航栏和面板 |
| 已禁用 | 插件 unload，去除导航栏，文件保留 |
| 已删除 | 插件目录被删除 |

---

## 11. 附录

### 11.1 文件关联

用户双击 `.stp` 文件后的行为由操作系统文件关联决定。当前版本**不注册** `.stp` 文件关联，用户应通过 StarDebate 内部的拖拽或菜单安装。

### 11.2 不支持的功能（v1.0）

- ❌ Zip AES 加密
- ❌ 数字签名
- ❌ 运行时权限拦截
- ❌ 插件市场 / 在线安装
- ❌ 传递依赖解析
- ❌ 自动依赖安装
- ❌ 文件关联（双击安装）

### 11.3 相关文件

| 文件 | 说明 |
|------|------|
| `workers/stp_installer/` | StarDebate 内置安装器 |
| `plugin_manager/` | 独立插件开发/打包/管理器 |
| `docs/plugin_dev_guide.md` | 插件开发 API 文档 |
