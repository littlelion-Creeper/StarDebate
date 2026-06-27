# StarDebate 扩展包开发文档

> 版本：v1.0.0 | 更新时间：2026-06-27

---

## 目录

1. [概述](#1-概述)
2. [扩展包 vs 插件](#2-扩展包-vs-插件)
3. [快速开始](#3-快速开始)
4. [扩展包结构](#4-扩展包结构)
5. [extension.json 清单](#5-extensionjson-清单)
6. [生命周期钩子](#6-生命周期钩子)
7. [ExtensionAPI 参考](#7-extensionapi-参考)
   - [7.1 继承自 PluginSafeAPI 的方法](#71-继承自-pluginsafeapi-的方法)
   - [7.2 获取全量核心对象](#72-获取全量核心对象)
   - [7.3 高级注册方法](#73-高级注册方法)
8. [打包与分发](#8-打包与分发)
9. [完整示例](#9-完整示例)
10. [常见问题](#10-常见问题)

---

## 1. 概述

**扩展包（.sep）** 是 StarDebate 中比插件权限更高、集成度更深的模块化单元。与插件不同，扩展包：

- **默认拥有全部系统权限**，无需声明 `permissions` 字段
- **安装即启用**，禁用/卸载需重启应用生效
- **可访问所有核心管理器**，通过 ExtensionAPI 直接操作 MainWindow
- **在 UI 构建前加载**，可在面板组装之前注册自定义 UI 元素

扩展包适用于需要深度集成 StarDebate 的场景，例如：
- 替换或增强核心功能（AI 分析引擎、主题系统）
- 注册全局快捷键和顶层菜单
- 直接操作配置系统和内部数据流
- 需要调用插件权限系统中未覆盖的底层操作

---

## 2. 扩展包 vs 插件

| 特性 | 插件（Plugin） | 扩展包（Extension） |
|------|---------------|--------------------|
| 存放目录 | `plugins/` | `extensions/` |
| 分发格式 | `.stp`（Zip + `"StarPlugin"` 注释） | `.sep`（Zip + `"StarExtension"` 注释） |
| 清单文件 | `plugin.json`（含 `permissions` 字段） | `extension.json`（**无** `permissions` 字段） |
| 权限 | 声明式权限（需用户在安装时确认） | **默认全权限**，无权限校验 |
| API 接口 | `PluginSafeAPI`（只读或受限操作） | `ExtensionAPI`（继承 PluginSafeAPI + 全量核心对象 + 高级方法） |
| 安装后 | 需手动启用 | **安装即启用** |
| 禁用 | 热禁用（立即生效） | 需重启应用生效 |
| 加载时序 | UI 构建完成后加载 | **阶段 D 后、阶段 E 前**（管理器就绪后、UI 构建前） |
| 入口 | `on_enable()` / `on_disable()` | `on_enable()` / `on_disable()`（同插件） |

---

## 3. 快速开始

### 3.1 创建扩展包目录

```
extensions/my_extension/
├── extension.json
└── main.py
```

### 3.2 编写 extension.json

```json
{
    "name": "我的扩展包",
    "extension_id": "my_extension",
    "version": "1.0.0",
    "min_app_version": "6.0.0",
    "author": "作者名",
    "description": "扩展包功能描述",
    "main": "main.py",
    "tags": ["标签1", "标签2"]
}
```

### 3.3 编写 main.py

```python
"""我的扩展包 — 入口文件"""
from workers.extension_manager import get_api


def on_enable():
    """扩展包启用时自动调用"""
    api = get_api()
    mw = api.get_main_window()
    mw._update_status("我的扩展包已加载")
    print("[MyExtension] 已启用")


def on_disable():
    """扩展包禁用时自动调用"""
    print("[MyExtension] 已禁用")
```

### 3.4 测试运行

将 `my_extension` 文件夹放入 `extensions/` 目录，重启 StarDebate。在顶部导航栏点击「扩展」→「管理扩展包」可查看已安装的扩展包。

---

## 4. 扩展包结构

```
extensions/<extension_id>/
├── extension.json        # [必需] 扩展包清单
├── main.py               # [必需] 入口文件（可自定义文件名）
├── settings.py           # [可选] 设置页定义
├── *.py                  # [可选] 其他 Python 模块
├── *.qss                 # [可选] 样式表
└── *.svg / *.png         # [可选] 资源文件
```

---

## 5. extension.json 清单

| 字段 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | string | 是 | — | 扩展包显示名称 |
| `extension_id` | string | 是 | — | 唯一标识符，作为文件夹名 |
| `version` | string | 是 | `"1.0.0"` | 语义化版本号 |
| `min_app_version` | string | 否 | `"1.0.0"` | 兼容的最低 StarDebate 版本 |
| `author` | string | 否 | `"未知"` | 作者名 |
| `description` | string | 否 | `""` | 功能描述 |
| `main` | string | 否 | `"main.py"` | 入口文件名 |
| `tags` | string[] | 否 | `[]` | 标签列表 |

**与 plugin.json 的关键区别：** 没有 `permissions` 字段。扩展包默认拥有全部系统权限，无需声明。

---

## 6. 生命周期钩子

### `on_enable()`

扩展包启用时调用。在此函数中进行初始化：

```python
def on_enable():
    api = get_api()
    # 读取配置
    # 注册菜单项
    # 创建面板
    # 绑定事件
```

### `on_disable()`

扩展包禁用时调用（下次启动生效）。在此函数中清理资源：

```python
def on_disable():
    # 保存状态
    # 清理临时文件
    # 解绑事件
```

### 生命周期时序

```
应用启动（阶段 D 后）
  └→ ExtensionManager 扫描 extensions/
      └→ 读取 installed_extensions.json
          └→ 对 enabled=True 的每个扩展包：
              ├→ importlib 加载 main.py
              ├→ 调用 on_enable()
              └→ 标记为活跃
                  └→ UI 构建（阶段 E）  ← 扩展包已可在此时注册 UI
       ...
应用关闭
  └→ 调用 on_disable() （每个扩展包）
      └→ 保存 installed_extensions.json
```

---

## 7. ExtensionAPI 参考

在扩展包代码中通过 `get_api()` 获取 ExtensionAPI 实例：

```python
from workers.extension_manager import get_api

api = get_api()
```

### 7.1 继承自 PluginSafeAPI 的方法

ExtensionAPI 继承自 `PluginSafeAPI`，因此以下方法均可使用（无权限校验）：

```python
# 基本信息
api.get_app_version()

# 辩论数据（只读）
api.get_debate_info()
api.get_speech_content("pro")       # "pro" 或 "con"

# AI 调用
api.call_ai(messages, model="deepseek-chat")

# UI 操作
api.show_notification("消息内容")
api.update_status("状态文字")

# 注册导航按钮
api.register_nav_button(side="right", emoji="🔧",
                         label="我的按钮", tooltip="描述",
                         callback=my_handler)

# 注册面板
api.register_panel(side="left", title="我的面板",
                   emoji="📋", tooltip="描述",
                   create_widget=build_my_panel)

# 事件钩子
api.on("debate_loaded", my_handler)
api.off("debate_loaded", my_handler)
```

> 完整继承方法列表请参考 [`docs/plugin_dev_guide.md`](plugin_dev_guide.md) 的 [4. API 参考](#4-api-参考) 章节。

### 7.2 获取全量核心对象

扩展包特有方法，可直接获取任意核心管理器引用：

#### `get_main_window()`

直接返回 `MainWindow`（`StarDebateApp`）引用。通过返回值可访问所有 `_*_mgr` 属性：

```python
mw = api.get_main_window()

# 访问任意管理器
cfg = mw._app_cfg              # AppConfigManager
nav = mw._nav_mgr               # NavBarManager
analysis = mw._analysis_mgr     # AIAnalysisManager
framework = mw._framework_mgr   # FrameworkManager
train = mw._train_mgr           # TrainingManager
material = mw._material_pool_mgr  # MaterialPoolManager

# 访问 UI 元素
stack = mw.centre_stack         # QStackedWidget
status = mw.status_label        # 状态栏标签
```

#### `get_core_object(attr_name: str)`

通过属性名安全获取核心管理器（返回 `None` 如果属性不存在）：

```python
app_cfg = api.get_core_object("_app_cfg")
nav_mgr = api.get_core_object("_nav_mgr")
plugin_mgr = api.get_core_object("_plugin_manager")
ext_mgr = api.get_core_object("_ext_mgr")
```

#### `get_extension_manager()`

获取 `ExtensionManager` 实例：

```python
ext_mgr = api.get_extension_manager()
all_exts = ext_mgr.get_all()        # 所有扩展包列表
info = ext_mgr.get("ext_id")        # 获取指定扩展包
```

#### `get_plugin_manager()`

获取 `PluginManager` 实例：

```python
pm = api.get_plugin_manager()
plugins = pm.get_all_plugins()
```

#### `get_app_cfg()`

获取 `AppConfigManager` 实例：

```python
cfg = api.get_app_cfg()
full = cfg.load_full_config()       # 读取完整配置
api_cfg = cfg.load_api_config()     # 读取 API 配置
```

### 7.3 高级注册方法

扩展包特有的高级方法，插件无法调用。

#### `register_top_menu(menu_id, menu_text, callback, tooltip="")`

在顶部导航栏的「扩展」菜单下注册一个子菜单项：

```python
def on_test_click():
    print("测试按钮被点击")

api.register_top_menu(
    "test_ext_btn",
    "测试入口",
    on_test_click,
    tooltip="点击测试",
)
```

#### `register_center_page(page_widget)`

将一个 QWidget 注册为中心功能区的一页（添加到 `centre_stack` 末尾）：

```python
from PyQt5.QtWidgets import QLabel

page = QLabel("这是我的扩展页面")
api.register_center_page(page)
```

#### `modify_theme_colors(color_overrides)`

修改全局主题颜色：

```python
api.modify_theme_colors({
    "accent_blue": "#ff6600",   # 将蓝色强调色改为橙色
})
```

---

## 8. 打包与分发

### 8.1 打包为 .sep 文件

使用以下 Python 脚本将扩展包目录打包为 `.sep` 文件：

```python
import zipfile
import os

src = "extensions/my_extension"
out = "my_extension.sep"

with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(src):
        for f in files:
            if f.endswith((".pyc", ".pyo")) or "__pycache__" in root:
                continue
            full_path = os.path.join(root, f)
            arcname = os.path.relpath(full_path, src)
            zf.write(full_path, arcname)
    # 设置注释标识为扩展包格式
    zf.comment = b"StarExtension"

print(f"已创建: {out}")
```

### 8.2 .sep 包格式

| 项目 | 值 |
|------|-----|
| 格式 | 标准 ZIP |
| 扩展名 | `.sep` |
| ZIP 注释 | `StarExtension` |
| 必须包含 | `extension.json` |
| 打包排除 | `__pycache__`、`*.pyc`、`*.pyo` |

### 8.3 安装方式

1. **通过 UI 安装**：点击「扩展」→「管理扩展包」→「安装扩展包」，选择 `.sep` 文件
2. **文件夹安装**：将扩展包文件夹放入 `extensions/` 目录，重启应用后自动发现
3. **拖拽安装**：将 `.sep` 文件拖拽到 StarDebate 窗口（需在主窗口实现 `dragEnterEvent` / `dropEvent`，当前版本仅支持 `.stp` 拖拽）

### 8.4 禁用与卸载

1. **禁用**：在扩展包管理页面点击状态切换按钮 → 标记为禁用 → 重启后生效（文件保留）
2. **删除**：长按「长按删除」按钮 → 确认 → 从磁盘移除（不可恢复）

---

## 9. 完整示例

### 示例：数据统计扩展包

```python
"""数据统计扩展包 — 展示 ExtensionAPI 全功能"""
from workers.extension_manager import get_api


def on_enable():
    api = get_api()
    mw = api.get_main_window()

    # ── 1. 获取核心对象 ──
    app_cfg = api.get_app_cfg()
    analysis_mgr = api.get_core_object("_analysis_mgr")
    
    # ── 2. 读取应用配置 ──
    if app_cfg is not None:
        cfg = app_cfg.load_full_config()
        version = cfg.get("version", "未知")
        print(f"[Stats] StarDebate 版本: {version}")

    # ── 3. 通过主窗口访问 UI ──
    if hasattr(mw, 'centre_stack'):
        page_count = mw.centre_stack.count()
        print(f"[Stats] 中心功能区共 {page_count} 页")

    # ── 4. 注册到扩展菜单 ──
    def show_stats():
        mw._update_status("📊 统计信息已收集")
    
    api.register_top_menu(
        "stats_show",
        "📊 显示统计",
        show_stats,
        tooltip="显示应用统计信息",
    )

    # ── 5. 注册到面板 ──
    api.register_nav_button(
        side="right",
        emoji="📊",
        label="统计",
        tooltip="打开统计面板",
        callback=show_stats,
    )

    mw._update_status("📊 数据统计扩展包已加载")
    print("[Stats] 已启用")


def on_disable():
    api = get_api()
    mw = api.get_main_window() if api else None
    if mw:
        mw._update_status("📊 数据统计扩展包已禁用")
    print("[Stats] 已禁用")
```

### 对应 extension.json

```json
{
    "name": "数据统计",
    "extension_id": "stats_extension",
    "version": "1.0.0",
    "min_app_version": "6.0.0",
    "author": "开发者",
    "description": "收集并展示 StarDebate 的应用统计数据",
    "main": "main.py",
    "tags": ["统计", "工具"]
}
```

---

## 10. 常见问题

### Q: 扩展包和插件的 API 有什么区别？

A: 扩展包使用 `ExtensionAPI`，它**完全继承** `PluginSafeAPI` 的所有方法（包括 `call_ai()`、`register_nav_button()`、`register_panel()` 等），并额外提供：
- `get_main_window()` — 直接返回 MainWindow
- `get_core_object(attr)` — 获取任意核心管理器
- `register_top_menu()` — 注册顶部菜单项
- `register_center_page()` — 注册中心页面
- `modify_theme_colors()` — 修改主题

### Q: 扩展包能直接操作文件系统吗？

A: **可以**。扩展包默认拥有全部权限，可以直接使用 Python 的 `open()`、`os`、`shutil` 等模块操作文件系统。

### Q: 扩展包崩溃会影响主程序吗？

A: 扩展包的 `on_enable()` 和 `on_disable()` 调用被 `try/except` 包裹，异常不会导致主程序崩溃。但扩展包通过 `get_main_window()` 获取到核心对象引用后，如果操作不当可能影响主程序稳定性。建议在扩展代码中做好异常处理。

### Q: 如何调试扩展包？

A: 扩展包与插件共享调试机制：
- 控制台 `print()` 输出可见
- 使用内置调试台查看日志
- 错误日志写入 `log/` 目录
- 可通过 `api.update_status()` 在状态栏显示信息

### Q: 扩展包如何获取自己的目录路径？

A: 通过 `ExtensionManager`：

```python
from workers.extension_manager import get_manager
mgr = get_manager()
info = mgr.get("my_extension_id")
folder = info.folder  # 如 extensions/my_extension/
```

### Q: 现有插件能否升级为扩展包？

A: 可以。需要做的修改：
1. 将目录从 `plugins/` 移到 `extensions/`
2. 将 `plugin.json` 改为 `extension.json`，移除 `permissions` 字段
3. 将 API 调用从 `get_api()`（来自 `workers.plugin_manager`）改为从 `workers.extension_manager` 导入
4. 安装后需重启生效
