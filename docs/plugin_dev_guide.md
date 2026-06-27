# StarDebate 插件开发文档

> 版本：v6.3.0 | 更新时间：2026-06-27
>
> 💡 **需要更高权限和更深集成？** 请参考 [扩展包开发文档](extension_dev_guide.md)。扩展包（.sep）拥有全部系统权限，可直接访问所有核心管理器，适合需要深度定制的场景。

---

## 目录

1. [快速开始](#1-快速开始)
2. [插件结构](#2-插件结构)
3. [生命周期钩子](#3-生命周期钩子)
4. [API 参考](#4-api-参考)
   - [4.1 基本信息](#41-基本信息)
   - [4.2 辩论数据](#42-辩论数据只读)
     - [4.2.1 资料稿查询](#421-资料稿查询) 
     - [4.2.2 赛制参数](#422-赛制参数) 
   - [4.3 框架与结构](#43-框架与结构)
   - [4.4 API 配置](#44-api-配置安全读取)
   - [4.5 UI 操作](#45-ui-操作安全限制内)
   - [4.6 文件操作](#46-文件操作仅限项目目录内)
   - [4.7 AI 调用](#47-ai-调用)
   - [4.8 侧边导航栏按钮注册](#48-侧边导航栏按钮注册)
   - [4.9 顶部导航栏按钮注册](#49-顶部导航栏按钮注册) 
   - [4.10 面板注册](#410-面板注册)
   - [4.11 设置页注册](#411-设置页注册)
   - [4.12 训练子功能注册](#412-训练子功能注册)
   - [4.13 控制台命令执行](#413-控制台命令执行) 
   - [4.14 快捷键注册](#414-快捷键注册) 
   - [4.15 跨插件函数调用](#415-跨插件函数调用) 
   - [4.16 右键菜单项注册](#416-右键菜单项注册) 
   - [4.17 监视日志插入](#417-监视日志插入) 
   - [4.18 控制台自定义命令注册](#418-控制台自定义命令注册) 
   - [4.17a 自定义多选框](#417a-自定义多选框v240-新增) 
   - [4.17b 自定义数字输入框](#417b-自定义数字输入框v290-新增) 
   - [4.17c SVG 通用渲染器](#417c-svg-通用渲染器v290-新增) 
   - [4.17d 自定义按钮](#417d-自定义按钮-v100-新增) 
   - [4.18 监视钩子插入细则](#418-监视钩子插入细则) 
   - [4.19 起居注 (ActivityChronicle)](#419-起居注-activitychronicle) 
   - [4.20 自定义 SVG 图标](#420-自定义-svg-图标v290-新增) 
   - [4.21 资料池 API](#421-资料池-api-v400-新增) 
   - [4.22 获取功能区大小](#422-获取功能区大小v430-新增) 
   - [4.23 一辩稿词汇索引与来源绑定](#423-一辩稿词汇索引与来源绑定v470-新增) 
5. [事件钩子](#5-事件钩子)
6. [插件配置](#6-插件配置)
7. [安全与限制](#7-安全与限制)
   - [7.1 安全沙箱](#71-安全沙箱)
   - [7.2 权限系统](#72-权限系统v450-新增)
   - [7.3 插件能做什么](#73-插件能做什么)
   - [7.4 插件不能做什么](#74-插件不能做什么)
8. [插件UI设计规范](#8-插件ui设计规范) 
   - [8.1 设计原则](#81-设计原则)
   - [8.2 色彩体系](#82-色彩体系)
   - [8.3 字体规范](#83-字体规范)
   - [8.4 间距与圆角](#84-间距与圆角)
   - [8.5 控件 objectName 标准化](#85-控件-objectname-标准化)
   - [8.6 面板设计](#86-面板设计)
   - [8.7 设置页设计](#87-设置页设计)
   - [8.8 对话框设计](#88-对话框设计)
   - [8.9 主题适配](#89-主题适配)
   - [8.10 StarCheckBox 使用](#810-starcheckbox-使用)
   - [8.11 StarSpinBox 使用](#811-starspinbox-使用)
   - [8.12 StarButton 使用](#812-starbutton-使用-v100-新增)
   - [8.13 反模式](#813-反模式应避免的做法)
   - [8.14 完整UI示例](#814-完整ui示例)
9. [插件分发与导入](#9-插件分发与导入)
   - [9.1 分发方式](#91-分发方式)
   - [9.2 .stp 插件包分发](#92-stp-插件包分发)
   - [9.3 用户安装步骤](#93-用户安装步骤)
   - [9.4 安装后操作](#94-安装后操作)
   - [9.5 卸载插件](#95-卸载插件)
   - [9.6 插件升级](#96-插件升级)
   - [9.7 文件夹插件兼容](#97-文件夹插件兼容)
10. [完整示例](#10-完整示例)
11. [常见问题](#11-常见问题)

---

## 1. 快速开始

### 1.1 5 分钟创建你的第一个插件

> **新方式**：StarDebate 现在支持 `.stp`（StarPlugin Package）格式分发和安装。
> 详细规范见 [`docs/stp_format.md`](stp_format.md)。
> 开发者可使用 `plugin_manager/` 工具创建插件项目并打包为 `.stp` 文件。

**步骤一**：创建插件文件夹

```
在 plugins/ 目录下创建 my_plugin/ 文件夹，
复制 plugins/plugin_template.py 中的模板代码
```

**步骤二**：编写插件代码

```python
# my_plugin/main.py
from workers.plugin_manager import get_api

def on_enable():
    """插件启用时 StarDebate 会自动调用此函数"""
    api = get_api()
    api.update_status("我的第一个插件已启用！")

def on_disable():
    """插件禁用时调用"""
    api = get_api()
    api.update_status("我的插件已关闭")

# 你的业务函数
def analyze_debate():
    api = get_api()
    info = api.get_debate_info()
    print(f"当前辩题: {info['title']}")
```

**步骤三**：添加 plugin.json 清单

```json
{
    "name": "我的插件",
    "version": "1.0.0",
    "author": "你的名字",
    "description": "插件描述",
    "main": "main.py",
    "enabled": true,
    "config": {}
}
```

**步骤四**：导入到 StarDebate

1. 打开 StarDebate，点击右侧导航栏 `🔌 插件`
2. 点击 `📦 安装插件`
3. 选择你的 `my_plugin/` 文件夹
4. 插件会自动加载并启用

---

### 1.2 .stp 插件包快速上手

如果你拿到了 `.stp` 插件包：

1. 打开 StarDebate → 点击「插件管理」
2. 点击「📦 安装插件」或直接将 `.stp` 文件**拖入主窗口**
3. 在弹出的预览窗口中确认插件信息、权限和依赖
4. 确认后插件安装完成（默认禁用）
5. 在插件列表中找到插件，点击「启用」

> 如需打包自己的插件为 `.stp`，请使用 `plugin_manager/` 工具，参见 [`docs/stp_format.md`](stp_format.md)。

---

## 2. 插件结构

### 2.1 唯一形式：文件夹插件（多文件）

> **重要**：StarDebate v1.5.0 起仅支持多文件文件夹插件，单文件 .py 插件不再支持。

```
my_plugin/
├── plugin.json       ← 插件清单（必需）
├── main.py           ← 入口文件（必需）
├── settings.py       ← 设置页文件（强烈推荐，自动扫描展示）
├── utils.py          ← 工具函数
├── ui.py             ← 自定义界面
└── data/             ← 数据文件
    └── templates.json
```

### 2.2 plugin.json 清单格式

```json
{
    "name": "辩论计时器",
    "version": "1.0.0",
    "author": "张三",
    "description": "在辩论过程中提供精准的计时功能",
    "main": "main.py",
    "enabled": true,
    "config": {
        "default_duration": 180,
        "warning_time": 30,
        "show_countdown": true
    }
}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 插件显示名称 |
| `version` | string | 是 | 版本号（语义化版本） |
| `author` | string | 否 | 作者名 |
| `description` | string | 否 | 插件描述（显示在卡片上） |
| `main` | string | 是 | 入口 Python 文件名 |
| `enabled` | boolean | 否 | 是否默认启用，默认 true |
| `config` | object | 否 | 插件自定义配置，用户可在设置中修改 |

### 2.3 settings.py 设置页规范

插件**强烈建议**包含 `settings.py` 文件。当用户打开 ⚙️ 设置对话框时，系统会**自动扫描**所有已启用插件的 `settings.py` 并在「插件页面」分区展示。

**settings.py 必须定义：**

```python
# PAGE_INFO: 页面元信息（必需）
PAGE_INFO = {
    "name": "计时器设置",     # 导航栏显示名称
    "icon": "⏱",            # 导航栏图标（emoji）
    "order": 150,            # 排序（建议 100+，避免与内置页冲突）
    "author": "张三",        # 作者名
    "version": "1.0.0",      # 版本号
}

# PAGE_CONFIG: 页面参数配置（可选）
PAGE_CONFIG = {
    "save_path": "plugins/my_plugin/config.json",  # 配置保存路径
    "auto_save": True,                              # 全局保存时是否自动保存
}

# build_page: 构建设置页内容（必需）
def build_page(parent_dialog, current_config: dict) -> QWidget:
    """返回设置页 QWidget"""
    ...

# collect_config: 收集当前配置（必需）
def collect_config(page_widget: QWidget) -> dict:
    """从页面控件收集配置并返回 dict"""
    ...

# get_default_config: 获取默认配置（可选）
def get_default_config() -> dict:
    """返回默认配置"""
    ...
```

### 2.4 settings.py 完整示例

```python
"""我的插件 - 设置页"""
import json, os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QCheckBox, QFrame, QPushButton
)
from PyQt5.QtCore import Qt

PAGE_INFO = {
    "name": "我的插件",
    "icon": "🔌",
    "order": 200,
    "author": "张三",
    "version": "1.0.0",
}

PAGE_CONFIG = {
    "save_path": "plugins/my_plugin/config.json",
    "auto_save": True,
}

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_JSON = os.path.join(PLUGIN_DIR, "plugin.json")

def get_default_config():
    return {"auto_run": True, "theme": "dark"}

def build_page(parent_dialog, current_config):
    page = QWidget()
    page.setObjectName("settingsPage")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)

    title = QLabel("🔌 我的插件设置")
    title.setObjectName("settingsSectionTitle")
    layout.addWidget(title)

    card = QFrame()
    card.setObjectName("settingsCard")
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(20, 18, 20, 18)
    card_layout.setSpacing(12)

    cb_auto = QCheckBox("自动运行")
    cb_auto.setObjectName("settingsCheck")
    cb_auto.setChecked(current_config.get("auto_run", True))
    card_layout.addWidget(cb_auto)

    layout.addWidget(card)
    layout.addStretch()

    page._cb_auto = cb_auto
    return page

def collect_config(page_widget):
    config = {"auto_run": page_widget._cb_auto.isChecked()}
    # 同步写入 plugin.json
    try:
        if os.path.exists(PLUGIN_JSON):
            with open(PLUGIN_JSON, "r", encoding="utf-8") as f:
                m = json.load(f)
            m["config"] = config
            with open(PLUGIN_JSON, "w", encoding="utf-8") as f:
                json.dump(m, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return config
```

---

## 3. 生命周期钩子

插件在以下时机被 StarDebate 自动调用：

```
  [导入插件]
       │
       ▼
  on_enable()  ←── 插件启动（自动调用）
       │         → load() 动态导入 main.py 模块到内存
       │         → 注册面板/按钮/设置页/快捷键等
       │
       ├── 插件正常运行 ──┐
       │                  │
       ▼                  ▼
  用户关闭开关        用户重新开启
       │                  │
       ▼                  ▼
  on_disable()        enable()
  (调用插件清理)      (重新 load() 模块)
       │              (调用 on_enable())
       ▼                  │
  ┌──────────────────────┘
  │
  ▼
  unload()  ←── ★ 完全卸载（v?.?.? 重构）
    ├─ _destroy_widgets()   销毁所有面板 widget（hide → deleteLater 延迟删除）
    ├─ _module = None       释放模块引用
    ├─ _instance = None     释放实例引用
    └─ del sys.modules["plugin_{id}"]     清除模块缓存（确保下次重新执行）
       del sys.modules["plugin_settings_{id}"]  清除设置页模块缓存

  同时清理所有注册项：
    clear_plugin_panels()
    clear_plugin_settings_pages()   ★ 新增
    clear_plugin_training_features()
    clear_plugin_top_nav_items()
    clear_plugin_console_commands()
    unregister_shortcuts()

  [彻底删除]  ←── delete_plugin()：unload + shutil.rmtree 删除磁盘文件
```

> **★ v?.?.? 重要变更**：从本版本起，在插件管理页**关闭**某插件时，插件会从**内存中完全卸载**（而非仅标记为禁用）。具体行为：
> - 所有面板 widget 从界面消失并延迟销毁
> - 设置页从 PageRegistry 中注销
> - Python 模块对象释放，`sys.modules` 缓存清除
> - **重新开启时**会重新 `importlib` 执行插件代码，相当于"冷启动"
>
> 这意味着：
> - 插件的 `on_disable()` 必须可靠清理所有资源（定时器、线程、外部连接）
> - 插件的 `on_enable()` 必须是幂等的（可安全重复调用）
> - 如果 `enable()` 失败（抛异常），系统会自动将 `enabled` 标记回 `false`
>
> 回调函数使用**弱引用**包装（weakref），插件卸载后外传的回调自动失效，避免幽灵回调。

| 钩子函数 | 调用时机 | 说明 |
|----------|----------|------|
| `on_enable()` | 插件导入后 / 用户开启开关 | 初始化资源、注册钩子、创建 UI。必须可**幂等重复调用** |
| `on_disable()` | 用户关闭开关 / 插件卸载前 | 释放资源、取消钩子、清理状态。**必须可靠执行**，否则卸载不完整 |

> **注意**：这两个函数都是可选的。如果你的插件不需要初始化或清理，可以不定义它们。

**示例**：

```python
from workers.plugin_manager import get_api

_timer = None  # 全局状态

def on_enable():
    global _timer
    api = get_api()
    api.update_status("计时器插件已启动")
    # 注册事件监听
    api.on("debate_opened", on_new_debate)

def on_disable():
    global _timer
    _timer = None
    api = get_api()
    api.off("debate_opened", on_new_debate)
    api.update_status("计时器插件已停止")
```

---

## 4. API 参考

> **v4.8.0 新增**：启动安全加载机制 — 核心功能失败自动崩溃退出并弹窗，非核心功能失败自动跳过并在欢迎页显示错误卡片（含进度条、重试、查看日志、超时保护30s）。新增 `components/timeout_progress_loader.py`（通用超时进度条）、`components/error_card.py`（错误卡片组件）。详见 [§4.24 启动安全加载](#424-启动安全加载v480-新增)
> **v4.7.0 新增**：一辩稿词汇索引升级为结构化数据，支持手动解释 + 来源绑定（资料池/便签）。自定义悬浮卡片（300ms 延迟、400px 宽、主题色高亮 + 加粗、SVG 图标）。详见 [§4.23 一辩稿词汇索引与来源绑定](#423-一辩稿词汇索引与来源绑定v470-新增)
> **v2.6.0 更新**：起居注 (ActivityChronicle) — 自动活动日志系统。插件加载/卸载、API/AI 调用自动记录成功/失败，标签 `[CRON]`。无需修改插件代码，启动时自动注入。详见 [§4.18 起居注](#418-起居注-activitychroniclev260-新增) | 完整文档见 `docs/log/起居注说明.md`
> **v1.0.0 新增**：`api.create_button()` — 插件可创建 StarButton 自定义按钮控件，替代 Qt 原生 QPushButton，支持 6 种排布、5 种占比、自动尺寸、主题自适应（见 [4.17d](#417d-自定义按钮-v100-新增)）
> **v2.5.0 更新**：日志系统独立进程架构 — LogService 独立进程运行，主窗口崩溃不影响日志写入；监视钩子三层容灾防护（队列投递→降级直写→系统健康监视）；新增 [§4.17 监视钩子插入细则](#417-监视钩子插入细则v250-新增)（见 §4.14 / §4.17）
> **v2.4.0 新增**：`api.create_checkbox()` — 插件可创建 StarCheckBox 自定义多选框控件，替代 Qt 原生 QCheckBox（见 [4.16](#416-自定义多选框v240-新增)）
> **v2.3.0 新增**：`api.execute_command()` / `api.log_monitor()` / `api.register_console_command()` — 插件可通过控制台运行内置命令、插入监视钩子、注册自定义命令供用户在调试台执行（见 [4.13](#413-控制台命令执行v230-新增) / [4.14](#414-监视日志插入v230v250-重写) / [4.15](#415-控制台自定义命令注册v230-新增)）
> **v2.1.0 新增**：`api.register_training_sub_feature()` — 插件可在「模拟训练」面板中注册自定义子功能（见 [4.12 训练子功能注册](#412-训练子功能注册v210)）
> **v1.6.0 新增**：`api.get_all_competition_formats()` / `api.get_current_debate_format()` — 插件可访问所有赛制参数并获取当前辩论的赛制信息（见 [4.2.2 赛制参数](#422-赛制参数)）
> **v1.4.0 新增**：`api.query_ref_doc_cells()` / `api.search_ref_doc()` — 插件可按行/列查询和搜索资料稿表格（见 [4.2.1 资料稿查询](#421-资料稿查询)）
> **v1.3.0 新增**：`api.register_settings_page()` — 插件可在设置对话框中注册自定义设置页（见 [4.11 设置页注册](#411-设置页注册)）
> **v1.2.0 新增**：`api.register_panel()` — 插件可在主界面注册功能面板（见 [4.9 面板注册](#49-面板注册)）

所有 API 通过 `get_api()` 函数获取：

```python
from workers.plugin_manager import get_api
api = get_api()
```

### 4.1 基本信息

#### `api.get_app_version() -> str`

获取 StarDebate 版本号。

```python
version = api.get_app_version()  # 返回值如 "1.5.0"（来自 config/config.json）
```

#### `api.get_current_project_path() -> str | None`

获取当前打开的项目根目录路径，未打开项目时返回 `None`。

```python
path = api.get_current_project_path()
# "C:/Users/xxx/Documents/MyDebate/"
```

---

### 4.2 辩论数据（只读）

#### `api.get_debate_info() -> dict`

获取当前辩论的基本信息。

```python
info = api.get_debate_info()
# {
#     "title": "人工智能是否应该取代人类决策",
#     "pro_side": "正方：支持AI决策",
#     "con_side": "反方：反对AI决策"
# }
```

#### `api.get_speech_content(side: str = "pro") -> str`

获取一方的一辩稿全文。

```python
# side 参数: "pro"（正方）或 "con"（反方）
pro_text = api.get_speech_content("pro")
con_text = api.get_speech_content("con")

# 使用示例：统计字数
word_count = len(pro_text.replace("\n", ""))
api.update_status(f"正方一辩稿共 {word_count} 字")
```

#### `api.get_analysis_result(side: str = "pro") -> dict`

获取 AI 分析报告的结果（需先执行 AI 分析）。

```python
analysis = api.get_analysis_result("pro")
# {
#     "arguments": [...],    # 论点列表
#     "reasoning": [...],    # 论证列表
#     "evidence": [...],     # 论据列表
#     "strengths": [...],    # 优势
#     "suggestions": [...]   # 改进建议
# }
```

#### `api.get_ref_doc_data(side: str = "pro") -> list`

获取资料稿数据。

```python
docs = api.get_ref_doc_data("pro")
# [
#     {"argument": "观点", "content": "论证内容", "source": "来源"},
#     ...
# ]
```

#### `api.query_ref_doc_cells(rows=None, cols=None) -> dict` 🆕

按指定行和/或列查询资料稿单元格内容。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `rows` | `int \| list[int] \| None` | `None` | 行索引。`None`=全部行，`0`=第1行，`[0,2]`=第1,3行 |
| `cols` | `int \| str \| list[int\|str] \| None` | `None` | 列标识。支持数字(0-2)/英文名("argument""content""source")/中文名("论证观点""论证内容""资料来源")。`None`=全部列 |

**返回**：`dict` 结构：

```python
{
    "columns": ["argument", "content"],  # 查询到的列名列表
    "rows": [
        ["单元格0,0", "单元格0,1"],        # 每行对应 cell 值列表
        ["单元格1,0", "单元格1,1"],
    ],
    "row_count": 2,   # 实际行数
    "col_count": 2,    # 列数
}
```

**示例 1 — 查看第 0 行全部列**：
```python
result = api.query_ref_doc_cells(rows=0)
# {"columns": ["argument","content","source"],
#  "rows": [["AI决策","AI能提高效率...","论文A"]],
#  "row_count": 1, "col_count": 3}
```

**示例 2 — 查看全部行的"论证内容"列**：
```python
result = api.query_ref_doc_cells(cols="论证内容")
# {"columns": ["content"],
#  "rows": [["AI能提高效率..."], ["AI减少偏见..."], ...],
#  "row_count": 5, "col_count": 1}
```

**示例 3 — 查看第 0, 2 行的第 0, 2 列**：
```python
result = api.query_ref_doc_cells(rows=[0, 2], cols=["argument", "source"])
# {"columns": ["argument","source"],
#  "rows": [["AI决策","论文A"],["数据隐私","报告B"]],
#  "row_count": 2, "col_count": 2}
```

**示例 4 — 遍历查询结果**：
```python
result = api.query_ref_doc_cells(cols=[0, 2])  # 全部行的第1和第3列
for i, row_cells in enumerate(result["rows"]):
    print(f"第{i}行: 观点={row_cells[0]}, 来源={row_cells[1]}")
```

> 📌 **列标识速查**：
> | 索引 | 英文名 | 中文名 | 含义 |
> |------|--------|--------|------|
> | 0 | `argument` | `论证观点` / `观点` / `论点` | 论证观点 |
> | 1 | `content` | `论证内容` / `内容` | 论证内容 |
> | 2 | `source` | `资料来源` / `来源` | 资料来源 |

---

#### `api.search_ref_doc(keyword, cols=None, case_sensitive=False) -> list` 🆕

按关键词搜索资料稿表格内容，返回匹配的行及命中位置。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `keyword` | `str` | **必需** | 搜索关键词 |
| `cols` | `int \| str \| list[int\|str] \| None` | `None` | 限定搜索列。`None`=所有列，列标识同 `query_ref_doc_cells` |
| `case_sensitive` | `bool` | `False` | 是否区分大小写 |

**返回**：`list[dict]`，每项结构：

```python
{
    "row_index": 2,                    # 行索引（0-based）
    "match_column": "argument",        # 匹配的列名（英文键名）
    "match_column_cn": "论证观点",      # 匹配的列中文名
    "cell_text": "AI 决策透明度...",    # 整个单元格的文本
    "full_row": {                      # 该行的完整数据
        "argument": "AI 决策透明度",
        "content": "详细内容...",
        "source": "论文 A"
    }
}
```

**示例 1 — 搜索所有列**：
```python
results = api.search_ref_doc("数据")
for hit in results:
    print(f"第{hit['row_index']}行 {hit['match_column_cn']}列: {hit['cell_text'][:50]}...")
```

**示例 2 — 只在"资料来源"列搜索**：
```python
results = api.search_ref_doc("论文", cols="source")
```

**示例 3 — 区分大小写搜索**：
```python
results = api.search_ref_doc("AI", case_sensitive=True)
```

**示例 4 — 插件实用：搜索并导出**：
```python
def export_search_results():
    api = get_api()
    keyword = "人工智能"
    results = api.search_ref_doc(keyword)

    if not results:
        api.update_status(f"未找到包含 '{keyword}' 的资料")
        return

    lines = [f"# 搜索 '{keyword}' 结果"]
    for hit in results:
        lines.append(f"\n## 第{hit['row_index']+1}行 ({hit['match_column_cn']})")
        lines.append(f"- 观点: {hit['full_row']['argument']}")
        lines.append(f"- 内容: {hit['full_row']['content']}")
        lines.append(f"- 来源: {hit['full_row']['source']}")

    api.write_file_in_project(f"search_{keyword}.md", "\n".join(lines))
    api.update_status(f"找到 {len(results)} 条匹配，已导出")
```

---

#### `api.get_notes() -> list`

获取所有便签（返回副本，修改不影响原数据）。

```python
notes = api.get_notes()
for note in notes:
    print(f"[{note['color']}] {note['content']}")
```

---

### 4.2.2 赛制参数 

> **v1.6.0 新增**：插件可访问所有赛制参数并获取当前辩论的赛制信息。

#### `api.get_all_competition_formats() -> dict`

获取所有赛制参数，包括 5 个预设赛制和全部自定义赛制。

**返回**：`dict` 结构：

```python
{
    "presets": [
        {
            "name": "华语辩论赛制",
            "type": "preset",
            "team_size": 4,
            "positions": [
                {
                    "name": "一辩",
                    "phases": [
                        {"name": "立论", "duration": 180},
                        {"name": "接质询", "duration": 120}
                    ]
                },
                # ...更多辩位
            ],
            "free_debate": {
                "name": "自由辩论",
                "duration": 480,
                "description": "双方交替发言"
            }
        },
        # ...更多预设赛制
    ],
    "custom": [
        {
            "name": "校赛",
            "type": "custom",
            "team_size": 4,
            "positions": [...],
            "free_debate": {...}
        },
        # ...更多自定义赛制
    ],
    "total_count": 8
}
```

**示例 1 — 遍历所有赛制**：
```python
formats = api.get_all_competition_formats()
for fmt in formats["presets"]:
    print(f"预设: {fmt['name']}, {fmt['team_size']}人/方")
for fmt in formats["custom"]:
    print(f"自定义: {fmt['name']}, {fmt['team_size']}人/方")
```

**示例 2 — 按名称查找赛制**：
```python
def find_format(name: str) -> dict | None:
    formats = api.get_all_competition_formats()
    for fmt in formats["presets"] + formats["custom"]:
        if fmt["name"] == name:
            return fmt
    return None

fmt = find_format("华语辩论赛制")
if fmt:
    for pos in fmt["positions"]:
        phases_str = ", ".join(f"{p['name']}({p['duration']}s)" for p in pos["phases"])
        print(f"  {pos['name']}: {phases_str}")
```

**示例 3 — 统计所有赛制的环节**：
```python
formats = api.get_all_competition_formats()
phase_names = set()
for fmt in formats["presets"] + formats["custom"]:
    for pos in fmt.get("positions", []):
        for phase in pos.get("phases", []):
            phase_names.add(phase["name"])
print(f"所有赛制共涉及 {len(phase_names)} 种环节类型")
```

---

#### `api.get_current_debate_format() -> dict`

获取当前选中辩论文件的赛制参数。

**返回**：`dict` 结构：

```python
{
    "format": {              # dict | None — 赛制数据（结构与 get_all_competition_formats 中单个赛制一致）
        "name": "华语辩论赛制",
        "team_size": 4,
        "positions": [...],
        "free_debate": {...}
    },
    "debate_path": "C:/.../debate_20260605_120000.json",  # str | None
    "has_format": True       # bool — 是否已指定赛制
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `format` | `dict \| None` | 赛制完整数据，与 `get_all_competition_formats()` 中单个赛制结构一致。未指定赛制时为 `None` |
| `debate_path` | `str \| None` | 当前辩论文件完整路径，未打开辩论时为 `None` |
| `has_format` | `bool` | 是否已指定赛制（`format` 不为 None 且 name 非空） |

**示例 1 — 检查并显示当前赛制**：
```python
current = api.get_current_debate_format()
if not current["debate_path"]:
    api.update_status("未打开任何辩论文件")
elif current["has_format"]:
    fmt = current["format"]
    api.update_status(
        f"当前赛制: {fmt['name']}（{fmt['team_size']}人/方，{len(fmt['positions'])}辩位）"
    )
else:
    api.update_status("当前辩论未指定赛制")
```

**示例 2 — 根据赛制判断可用辩位**：
```python
current = api.get_current_debate_format()
if current["has_format"]:
    fmt = current["format"]
    positions = [pos["name"] for pos in fmt["positions"]]
    print(f"可用辩位: {', '.join(positions)}")

    # 获取每个辩位的总时长
    for pos in fmt["positions"]:
        total_sec = sum(p["duration"] for p in pos["phases"])
        total_min, total_sec = divmod(total_sec, 60)
        print(f"  {pos['name']}: 约 {total_min}分{total_sec}秒")
else:
    print("未指定赛制")
```

**示例 3 — 检查当前赛制是否包含自由辩论**：
```python
current = api.get_current_debate_format()
if current["has_format"]:
    fmt = current["format"]
    if fmt.get("free_debate"):
        fd = fmt["free_debate"]
        print(f"自由辩论: {fd['name']}, 时长 {fd['duration']}秒")
    else:
        print("此赛制无自由辩论环节")
```

**示例 4 — 插件实战：导出赛制摘要**：
```python
def export_format_summary():
    api = get_api()
    current = api.get_current_debate_format()
    if not current["has_format"]:
        api.update_status("无赛制，跳过导出")
        return

    fmt = current["format"]
    lines = [f"# 赛制摘要: {fmt['name']}", "", f"- 队伍人数: {fmt['team_size']}人/方"]

    for idx, pos in enumerate(fmt.get("positions", []), 1):
        lines.append(f"\n## 辩位 {idx}: {pos['name']}")
        for phase in pos.get("phases", []):
            dur = f"{phase['duration'] // 60}分{phase['duration'] % 60}秒"
            cp = f"（对位: {phase['counterpart']}）" if phase.get('counterpart') else ""
            lines.append(f"  - {phase['name']}: {dur}{cp}")

    if fmt.get("free_debate"):
        fd = fmt["free_debate"]
        dur = f"{fd['duration'] // 60}分{fd['duration'] % 60}秒"
        lines.append(f"\n## 自由辩论: {fd['name']} ({dur})")

    api.write_file_in_project("赛制摘要.md", "\n".join(lines))
    api.update_status("赛制摘要已导出")
```

---

### 4.3 框架与结构

#### `api.get_framework_data() -> list`

获取当前已加载的辩论框架（思维导图）节点数据（内存中）。

```python
nodes = api.get_framework_data()
for node in nodes:
    print(f"节点: {node['id']} | 类型: {node['node_type']} | 文本: {node['text']}")
    if "children" in node:
        print(f"  子节点: {node['children']}")
```

**节点类型**：

| node_type | 含义 | 颜色 |
|-----------|------|------|
| `position` | 立场 | 紫色 #cba6f7 |
| `definition` | 定义 | 蓝色 #89b4fa |
| `criterion` | 判准 | 青色 #94e2d5 |
| `argument` | 论点 | 绿色 #a6e3a1 |
| `evidence` | 论据 | 黄色 #f9e2af |
| `value` | 价值 | 红色 #f38ba8 |

#### `api.get_speech_framework_params(side: str = "pro") -> dict` 🆕 v1.7.0

获取当前选中一辩稿文件的框架参数。从一辩稿 JSON 文件中读取已保存的辩论框架数据，返回完整的节点树形结构和按类型汇总的概要信息。

**参数**：
- `side`：辩方，`"pro"`（正方，默认）或 `"con"`（反方）

**返回值**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `speech_file` | `str\|None` | 一辩稿文件路径 |
| `has_framework` | `bool` | 是否包含框架数据 |
| `nodes` | `list[dict]` | 框架节点列表（含 is_root/depth/enriched 信息） |
| `node_count` | `int` | 节点总数 |
| `summary` | `dict` | 按节点类型汇总 `{类型中文名: 数量}` |
| `node_types` | `dict` | 节点类型定义 `{type: {"label": str, "color": str}}` |
| `root_nodes` | `list[dict]` | 根节点列表（顶层节点） |

**每个节点 (`nodes[i]`) 的字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 节点 ID |
| `node_type` | `str` | 节点类型 (position/definition/criterion/argument/evidence/value) |
| `type_label` | `str` | 节点类型中文标签（如"📖 定义"） |
| `text` | `str` | 节点文本内容 |
| `x`, `y`, `width`, `height` | `int` | 画布坐标与尺寸 |
| `children` | `list[int]` | 子节点 ID 列表 |
| `is_root` | `bool` | 是否为根节点（无父节点） |
| `depth` | `int` | 节点在树中的层级深度（0=根节点） |

**示例**：

```python
params = api.get_speech_framework_params("pro")

if params["has_framework"]:
    # 遍历根节点
    for node in params["root_nodes"]:
        print(f"根节点 [{node['type_label']}]: {node['text']}")
    
    # 查看类型汇总
    print(f"论点数量: {params['summary'].get('论点', 0)}")
    print(f"论据数量: {params['summary'].get('论据', 0)}")
    print(f"总节点: {params['node_count']}")

    # 获取某节点的子节点
    id_map = {n["id"]: n for n in params["nodes"]}
    for root in params["root_nodes"]:
        for cid in root["children"]:
            child = id_map[cid]
            print(f"  → 子节点: {child['type_label']} - {child['text']}")
else:
    print("当前一辩稿文件中未保存框架数据")
```

#### `api.get_structure_data() -> dict`

获取一辩稿的结构数据（章节+关键词）。

```python
struct = api.get_structure_data()
# {
#     "pro": {
#         "sections": [...],   # 正方章节
#         "keywords": [...]    # 正方关键词
#     },
#     "con": {...}
# }
```

#### `api.get_keywords(side: str = "pro") -> list`

获取某一方的关键词列表。

```python
keywords = api.get_keywords("pro")
# [{"word": "人工智能", "note": "核心概念", "reference": "见文献A"}, ...]
```

---

### 4.4 API 配置（安全读取）

#### `api.get_api_config() -> dict`

获取 API 配置信息（**API Key 已屏蔽**，仅显示前 4 位）。

```python
config = api.get_api_config()
# {
#     "api_url": "https://api.deepseek.com/v1/chat/completions",
#     "api_key": "sk-a****",     ← Key 已自动屏蔽
#     "model": "deepseek-chat",
#     "temperature": 0.7
# }
```

---

### 4.5 UI 操作（安全限制内）

#### `api.update_status(message: str)`

在主窗口底部状态栏显示消息，自动添加 `[插件名]` 前缀。

```python
api.update_status("数据导出完成！")
# 状态栏显示: [my_plugin] 数据导出完成！
```

#### `api.show_notification(title: str, message: str)`

弹出信息对话框通知用户。

```python
api.show_notification("导出成功", "辩论数据已导出到 output/debate_data.json")
```

#### `api.navigate_to_page(page_index: int)`

切换到主窗口中央区域的指定页面。

| page_index | 页面 |
|------------|------|
| 0 | 欢迎页 |
| 1 | 辩论详情 |
| 2 | 一辩稿编辑 |
| 3 | AI 分析报告 |
| 4 | 资料稿表格 |
| 5 | 资料卡片 |
| 6 | 模拟质询 |
| 7 | 模拟接质 |
| 8 | 辩论框架 |

```python
# 自动跳转到 AI 分析页面
api.navigate_to_page(3)
```

---

### 4.6 文件操作（仅限项目目录内）

#### `api.read_file_in_project(relative_path: str) -> str | None`

读取当前项目中的文件内容。

```python
# 读取项目中的 speech_pro.json 文件
content = api.read_file_in_project("speech_pro.json")
if content:
    print(f"文件内容: {content[:100]}...")
```

> **安全限制**：只能读取当前项目目录内的文件。不能使用 `../` 跳出项目目录。

#### `api.write_file_in_project(relative_path: str, content: str) -> bool`

将内容写入当前项目中的文件（自动创建父目录）。

```python
# 将分析结果导出到项目目录
report = "# 辩论分析报告\n\n## 正方观点\n..."
success = api.write_file_in_project("exports/report.md", report)
if success:
    api.update_status("报告已保存到 exports/report.md")
```

> **安全限制**：只能写入当前项目目录内。不能使用绝对路径或跳出项目目录。

---

### 4.7 AI 调用

> **核心能力**：插件可以直接调用 AI 接口，使用与 StarDebate 相同的 API 配置。

#### `api.call_ai(messages, system_prompt="", model="", max_tokens=4096, temperature=0.7, timeout=120) -> str`

调用 AI 大语言模型，返回 AI 回复文本。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `messages` | `list[dict]` | **必需** | 对话消息列表，每项含 `{"role": "...", "content": "..."}` |
| `system_prompt` | `str` | `""` | 系统提示词（设定 AI 角色行为） |
| `model` | `str` | `""` | 模型名，默认使用 API 配置中的模型 |
| `max_tokens` | `int` | `4096` | 最大输出 token 数（上限 16384） |
| `temperature` | `float` | `0.7` | 温度参数 0-2，越高越随机 |
| `timeout` | `int` | `120` | 请求超时秒数（上限 300） |

**返回**：AI 回复的文本内容。

**异常**：
- `ValueError` — messages 格式错误
- `RuntimeError` — API 未配置、网络错误或调用失败

**示例 1：基础调用**

```python
from workers.plugin_manager import get_api
api = get_api()

result = api.call_ai(
    messages=[
        {"role": "user", "content": "请用一句话解释什么是辩论中的'举证责任'"}
    ],
    system_prompt="你是辩论教育专家，回答简洁专业。",
    max_tokens=200
)
print(result)
# 输出: 举证责任是指在辩论中，提出某一主张的一方有义务提供证据来支持该主张...
```

**示例 2：多轮对话**

```python
def chat_with_ai(user_input: str, history: list) -> str:
    api = get_api()
    messages = history + [{"role": "user", "content": user_input}]
    reply = api.call_ai(
        messages=messages,
        system_prompt="你是辩论助手，帮助用户完善辩论策略。",
        temperature=0.8
    )
    return reply

# 使用
history = []
while True:
    user_msg = input("你: ")
    if user_msg == "退出":
        break
    reply = chat_with_ai(user_msg, history)
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": reply})
    print(f"AI: {reply}")
```

**示例 3：分析辩论内容**

```python
def analyze_debate_quality() -> str:
    api = get_api()
    
    # 获取辩论数据
    pro_text = api.get_speech_content("pro")
    con_text = api.get_speech_content("con")
    
    # 调用 AI 分析
    analysis = api.call_ai(
        messages=[{
            "role": "user",
            "content": f"请分析以下辩论，给出评分(1-10)和改进建议：\n\n正方：\n{pro_text}\n\n反方：\n{con_text}"
        }],
        system_prompt="你是专业辩论裁判，分析公正客观。",
        max_tokens=2048
    )
    
    # 保存结果
    api.write_file_in_project("plugin_analysis.md", f"# AI 辩论分析\n\n{analysis}")
    api.update_status("AI 分析已保存")
    return analysis
```

**安全说明**：
- 使用与 StarDebate 主体相同的 API 配置（URL + Key）
- 插件无法直接读取 API Key
- max_tokens 上限 16384，防止插件消耗过多资源
- timeout 上限 300 秒，防止无限制等待
- 异常会被安全捕获，不会导致主程序崩溃

---

---

### 4.8 侧边导航栏按钮注册

> 插件可以在左侧或右侧导航栏注册自定义按钮，点击即可触发功能。按钮随插件启用/禁用自动显示/消失。
>
> **v1.8.0 更新**：StarDebate 的导航栏已重写为**注册表驱动架构**。左右两侧导航栏的按钮位置和启用状态由 `config/nav_registry.json` 统一管理。插件按钮动态注入到注册表定义的 `plugin_area` 插槽中。

#### 导航栏架构说明

```
config/nav_registry.json          ← 导航栏注册表（控制按钮排列、分组、分隔符）
       ↓
NavBarManager                      ← 管理器：构建/刷新/禁用导航栏
       ↓
  ┌───────────┐  ┌───────────┐
  │  左侧导航  │  │  右侧导航  │
  │ (62px宽)  │  │ (62px宽)  │
  │           │  │           │
  │ [主体按钮] │  │ [主体按钮] │
  │ ─ stretch │  │ ─ stretch │
  │ [plugin_a] │  │ [plugin_a] │  ← plugin_area 插槽
  │ [主体按钮] │  │ [主体按钮] │
  └───────────┘  └───────────┘
```

**注册表中的 `plugin_area` 插槽**：
- 左侧导航栏：`plugin_area_left`（位于 stretch 下方、设置按钮上方）
- 右侧导航栏：`plugin_area_right`（位于 stretch 下方、插件管理按钮上方）

#### `api.register_nav_button(side, emoji, label, tooltip, callback, icon="")`

在 StarDebate 导航栏的插件区注册一个带图标的按钮。

| 参数 | 类型 | 说明 |
|------|------|------|
| `side` | `str` | `"left"`（左侧导航栏插件区）或 `"right"`（右侧导航栏插件区） |
| `emoji` | `str` | 按钮图标（emoji 字符，如 `"⏱"`），`icon` 为空时显示 |
| `label` | `str` | 按钮下方标签（1-2 字最佳） |
| `tooltip` | `str` | 鼠标悬停提示文本 |
| `callback` | `callable` | 点击回调函数（无参数） |
| `icon` | `str` | ★ 可选，图标文件名（如 `"timer.svg"`），自动从 `plugins/你的插件名/icon/` 目录查找 |

> **按钮显示优先级**：`icon` 非空且文件存在 → 显示图标文件；否则回退到 `emoji`（emoji 文字）。

> **注意**：必须在 `on_enable()` 中调用此方法。插件禁用时按钮自动移除，无需手动清理。

**示例（使用 SVG 图标）**：

```python
from workers.plugin_manager import get_api

def open_timer():
    from plugins.debate_timer.main import show_timer
    show_timer()

def on_enable():
    api = get_api()
    api.register_nav_button(
        side="right",
        emoji="⏱",              # icon 加载失败时的后备显示
        icon="timer.svg",        # 存放在 plugins/debate_timer/icon/timer.svg
        label="计时",
        tooltip="打开辩论计时器",
        callback=open_timer,
    )
    api.update_status("计时器插件已就绪")
```

**按钮样式**：
- 尺寸由注册表 `settings.button_size` 控制（默认 50×50），圆角 8px，深色背景
- 标签使用紫色 `#cba6f7` 以区分主体功能按钮（主体按钮标签为灰色 `#6c7086`）
- 多个插件按钮按注册顺序排列

**如何自定义注册表**：

如需调整导航栏中主体按钮的位置、分组或启用状态，编辑 `config/nav_registry.json`：

```json
{
    "left_nav": [
        // 新增按钮（在中间区 position 合适处插入）：
        {"id": "my_feature", "type": "button", "text": "🆕",
         "label": "新功能", "tooltip": "描述", "section": "middle",
         "position": 8, "enabled": true},

        // 添加分隔符：
        {"type": "separator", "id": "sep_custom", "section": "middle", "position": 9},

        // 禁用某个按钮（调试时）：
        // 将对应按钮的 "enabled" 设为 false
    ]
}
```

**SVG 图标颜色配置（v4.7.0 新增）**：

每个按钮可通过 `icon_checked_color` 和 `icon_unchecked_color` 参数自定义 SVG 图标的选中/不选中颜色：

```json
{"id": "my_feature", "type": "button", "icon": "my_icon.svg",
 "icon_checked_color": "white",          // 选中时图标色
 "icon_unchecked_color": "accent_blue",  // 不选中时图标色
 "checkable": true, ...}
```

颜色值为 `theme.json` 中 `colors` 块的键名：
| 键名 | 深色主题效果 | 浅色主题效果 |
|------|-------------|-------------|
| `"white"` | `#FFFFFF` 白色 | `#FFFFFF` 白色 |
| `"text"` | `#E0E0E0` 浅灰 | `#37352F` 深灰 |
| `"subtext"` | `#A0A0A0` 中灰 | `#9B9A97` 中灰 |
| `"accent_blue"` | `#2E6DDE` 蓝 | `#2E6DDE` 蓝 |
| `"accent_green"` | `#2EA043` 绿 | `#2EA043` 绿 |

**全局默认值**在 `settings` 块定义：

```json
"settings": {
    ...
    "icon_checked_color": "white",
    "icon_unchecked_color": ""
}
```

- `icon_unchecked_color` 为空字符串时自动按主题类型选择：深色→`subtext`（灰），浅色→`dual_primary`（蓝）
- 单个按钮的配置可覆盖 settings 全局默认值

> 💡 **提示**：注册表修改后重启 StarDebate 生效。无需改动任何 Python 代码。

---

### 4.9 顶部导航栏按钮注册（v2.2.0 新增）

> 插件可以在顶部菜单栏的插件区注册按钮，或在已有菜单按钮（文件/编辑/视图）下添加子菜单项。
>
> 顶部导航栏与标题栏已融合，菜单按钮由 `TopNavManager` 注入到 `TitleBar`。
> 菜单配置文件为 `config/menu_main_window.json`（每个窗口独立文件）。

#### 顶部导航栏架构说明

```
config/menu_main_window.json     ← 主窗口菜单配置（menu_area + right_area 分区）
       ↓
TopNavManager                       ← 管理器：将按钮注入 TitleBar 各注入区
       ↓
TitleBar (标题栏+菜单栏融合, 42px)   ← ★ v2.0 融合后
  ┌──────────────────────────────────────────────────────────────┐
  │ [🖼] 文件▼ 编辑▼ 视图▼  [drag_area]  [插件A] [插件B] 帮助 [─][□][✕] │
  │ ↑软件图标(icon/common/main.png)   ↑弹性拖拽区  ↑插件区  ↑按钮 ↑窗口控制│
  └──────────────────────────────────────────────────────────────┘
```

> **v6.1.9 更新**：TitleBar 新增 `icon_path` 参数，支持加载 PNG 图片作为标题栏图标（缩放 22×22）。`__init__` 签名：`TitleBar(parent, title, icon: str = "★", icon_path: str = "")`。`icon_path` 非空且文件存在时优先显示图片，回退到文字。
>
> 当前使用时已传入 `icon_path="icon/common/main.png"`（`workers/star_debate/ui_assembly.py:50`）。

**注册表项类型**：

| type | 说明 | section | 示例 |
|------|------|---------|------|
| `menu_button` | 带下拉菜单的按钮 | menu_area | `{"id":"file_menu", "type":"menu_button", "text":"文件"}` |
| `button` | 独立按钮 | right_area | `{"id":"help_btn", "type":"button", "text":"帮助"}` |
| `plugin_area` | 插件动态按钮区 | right_area | `{"id":"plugin_area_top", "type":"plugin_area"}` |
| `separator` | 垂直分隔线 | menu_area/right_area | — |

**已有菜单按钮 ID**（插件可向其注入子项）：
- `file_menu` — 文件菜单
- `edit_menu` — 编辑菜单
- `view_menu` — 视图菜单

#### `api.register_top_nav_button(text, tooltip, callback, btn_id="", emoji="")`

在顶部导航栏的插件区注册一个文本按钮。

| 参数 | 类型 | 说明 |
|------|------|------|
| `text` | `str` | 按钮显示文字（如 `"📊 数据统计"`） |
| `tooltip` | `str` | 鼠标悬停提示 |
| `callback` | `callable` | 点击回调函数（无参数） |
| `btn_id` | `str` | 可选，按钮唯一ID（默认自动生成） |
| `emoji` | `str` | 可选，按钮图标（已包含在 text 中时可省略） |

**示例**：

```python
from workers.plugin_manager import get_api

def open_statistics():
    from my_plugin.stats import show_stats
    show_stats()

def on_enable():
    api = get_api()
    api.register_top_nav_button(
        text="📊 数据统计",
        tooltip="查看辩论数据统计",
        callback=open_statistics,
        btn_id="stats_btn",
    )
```

#### `api.register_top_nav_sub_menu(parent_menu_id, text, callback, sub_id="")`

在顶部导航栏指定菜单按钮下注册一个子菜单项。

| 参数 | 类型 | 说明 |
|------|------|------|
| `parent_menu_id` | `str` | 父菜单ID（`"file_menu"`/`"edit_menu"`/`"view_menu"`） |
| `text` | `str` | 子菜单显示文字（如 `"📤 导出数据"`） |
| `callback` | `callable` | 点击回调函数（无参数） |
| `sub_id` | `str` | 可选，子项唯一ID |

**示例**：

```python
def export_report():
    api = get_api()
    api.write_file_in_project("报告.md", "# 导出报告\n...")
    api.update_status("报告已导出")

def on_enable():
    api = get_api()
    api.register_top_nav_sub_menu(
        parent_menu_id="file_menu",
        text="📤 导出插件报告",
        callback=export_report,
        sub_id="export_report",
    )
```

> **注意**：必须在 `on_enable()` 中调用。插件禁用时自动移除，无需手动清理。

#### 自定义顶部导航栏注册表

编辑 `config/menu_main_window.json` 可修改按钮位置、新增主体功能按钮：

```json
{
    "menu_area": [
        // 在 "文件" 菜单新增命令：
        {"id": "file_menu", "type": "menu_button", "text": "文件", "position": 1,
         "items": [
             {"id": "my_cmd", "type": "sub_menu", "text": "🆕 新命令", "position": 7,
              "callback": "_on_my_command"}
         ]}
    ],
    "right_area": [
        // 新增独立按钮：
        {"id": "new_btn", "type": "button", "text": "🚀 快速操作",
         "tooltip": "快速执行", "position": 9, "callback": "_on_quick_action"}
    ]
}
```

> 📌 **区别**：`register_top_nav_button/register_top_nav_sub_menu` 适合插件动态按钮（随插件开关自动增删），编辑注册表 JSON 适合需要永久固定在顶部的主体功能按钮。
> 📌 **分区说明**：`menu_area` 注入到标题栏图标右侧，`right_area` 注入到窗口控制按钮左侧。

---

### 4.10 面板注册

> **新增功能（v1.2.0）**：插件可以在主界面注册独立的功能面板，面板可以放置在左侧、右侧或中央区域。
>
> **v4.2.0 更新**：新增 `min_width`、`max_width`、`width_ratio` 宽度参数，`icon` 参数已补齐透传。
> **v4.7.0 更新**：`max_width` 和 `width_ratio` 传入 `None` 表示无限制（面板可随功能区无限扩展）。

#### `api.register_panel(side, title, emoji, tooltip, create_widget, *, icon="", min_width=None, max_width=None, width_ratio=None)`

在 StarDebate 主界面注册一个功能面板。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `side` | `str` | 是 | `"left"`（左侧面板区）/ `"right"`（右侧面板区）/ `"center"`（中央功能区） |
| `title` | `str` | 是 | 面板名称（显示在导航按钮标签上，2-3 字最佳） |
| `emoji` | `str` | 是 | 导航按钮图标（emoji 字符），`icon` 为空时显示 |
| `tooltip` | `str` | 是 | 鼠标悬停提示文本 |
| `create_widget` | `callable` | 是 | 无参回调函数，返回 `QWidget` 面板内容 |
| `icon` | `str` | 否 | 图标文件名（如 `"panel.svg"`），自动从 `plugins/你的插件名/icon/` 目录查找 |
| `min_width` | `int` | 否 | 面板最小宽度（px），默认 `280` |
| `max_width` | `int` | 否 | 面板最大宽度（px），`None` 表示无上限（默认 `480`） |
| `width_ratio` | `float` | 否 | 面板打开时占可用空间的比例（`0.0`~`1.0`），`None` 表示不限比例（默认 `0.35`） |

> **按钮显示优先级**：`icon` 非空且文件存在 → 显示图标文件；否则回退到 `emoji`（emoji 文字）。
>
> **注意**：必须在 `on_enable()` 中调用。插件禁用时面板自动移除，面板内容控件也自动销毁。

**宽度参数说明**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `min_width` | `280` | 面板最小宽度，单位 px。若 `min_width > max_width` 会自动交换 |
| `max_width` | `480`（`None`=无上限） | 面板最大宽度，单位 px。传入 `None` 不设上限，面板可无限扩展 |
| `width_ratio` | `0.35`（`None`=不限比例） | 面板打开时，splitter 分配的宽度 = `可用空间 × width_ratio`，最终被 `[min_width, max_width]` 截断。传入 `None` 则跳过比例计算，占满剩余可用空间 |

**面板位置说明**：

| side | 面板位置 | 导航按钮 | 行为 |
|------|----------|----------|------|
| `"left"` | 左侧项目树与中央功能区之间 | 右侧导航栏底部（紫色标签） | 点击切换显示/隐藏，同侧面板互斥 |
| `"right"` | 右侧功能区（与 AI写稿/扩写/便签/训练/插件管理并列） | 右侧导航栏底部（紫色标签） | 点击切换显示/隐藏，与其他右侧功能面板互斥 |
| `"center"` | 中央功能区（替代 centre_stack 当前页） | 右侧导航栏底部（紫色标签） | 点击跳转，再次点击返回欢迎页 |

**示例 1：右侧面板（计时器，自定义宽度）**：

```python
from workers.plugin_manager import get_api
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton

def create_timer_panel():
    """创建计时器面板"""
    panel = QFrame()
    panel.setObjectName("myTimerPanel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(16, 16, 16, 16)

    title_lbl = QLabel("⏱ 辩论计时器")
    title_lbl.setObjectName("pluginSectionTitle")
    title_lbl.setStyleSheet("color: #cdd6f4;")

    time_lbl = QLabel("03:00")
    # 计时器数字保持大字号，但通过 objectName 引用
    time_lbl.setObjectName("timerDisplay")
    time_lbl.setAlignment(Qt.AlignCenter)
    time_lbl.setStyleSheet("color: #cba6f7;")

    btn_start = QPushButton("开始计时")
    btn_start.setObjectName("primaryBtn")
    btn_start.setStyleSheet("""
        QPushButton {
            background-color: #cba6f7; color: #1e1e2e;
            border-radius: 6px; padding: 8px 16px;
            font-weight: bold;
        }
    """)

    layout.addWidget(title_lbl)
    layout.addWidget(time_lbl)
    layout.addStretch()
    layout.addWidget(btn_start)
    return panel

def on_enable():
    api = get_api()
    api.register_panel(
        side="right",
        title="计时",
        emoji="⏱",
        tooltip="打开辩论计时器面板",
        create_widget=create_timer_panel,
        min_width=350,
        max_width=600,
        width_ratio=0.4,
    )
    api.update_status("计时器插件已就绪")
```

**示例 2：中心面板（数据分析）**：

```python
from workers.plugin_manager import get_api
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel

def create_analysis_panel():
    """创建数据分析面板"""
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.addWidget(QLabel("📊 辩论数据分析报告"))
    return panel

def on_enable():
    api = get_api()
    api.register_panel(
        side="center",
        title="分析",
        emoji="📊",
        tooltip="打开辩论分析报告",
        create_widget=create_analysis_panel,
    )
```

**面板样式建议**：
- 深色背景 `background-color: #1e1e2e` 或 `#11111b` 保持一致性
- 通过 `api.update_status()` 反馈操作状态
- 宽度参数可选，不传则使用默认值（最小 280px，最大 480px，比例 0.35）

**互斥规则**：
- 同侧插件面板互斥（打开一个会自动关闭另一个）
- 右侧插件面板与所有右侧功能面板（AI写稿/扩写/便签/训练/插件管理）互斥
- 左侧插件面板独立（不与现有面板冲突）

---

### 4.11 设置页注册

> **v1.5.0 更新**：插件设置页现在通过 `settings.py` 文件**自动扫描注册**。只需在插件文件夹中放置 `settings.py`，系统会自动在 ⚙️ 设置对话框的「插件页面」分区展示。
>
> `api.register_settings_page()` 仍保留用于特殊场景（如需要根据运行状态动态创建设置页），但推荐使用 `settings.py` 文件方式。

#### 方式一（推荐）：settings.py 自动扫描

在插件文件夹中创建 `settings.py`，定义 `PAGE_INFO`、`build_page`、`collect_config` 即可。系统在设置对话框打开时自动扫描所有已启用插件的 `settings.py`。

参见 [2.3 settings.py 设置页规范](#23-settingspy-设置页规范)。

#### 方式二（兼容）：api.register_settings_page()

```python
def on_enable():
    api = get_api()
    api.register_settings_page(
        meta={
            "name": "我的插件",
            "icon": "🔌",
            "order": 200,
            "author": "张三",
            "version": "1.0.0",
        },
        create_widget_fn=build_my_page,
        collect_config_fn=collect_my_config,
    )
```

**设置对话框布局**：

```
┌─────────────────────────────────────┐
│  ⚙️ 设置                      ✕    │
├──────────┬──────────────────────────┤
│ 📡 API配置│                         │
│ 🎨 外观   │    当前选中页面的内容     │
│ ✏️ 编辑器 │                         │
│ ℹ️ 关于   │                         │
│ ──────── │                         │
│ ▲ 插件页面│                         │
│  🤖 智能  │  ← 自动扫描自            │
│   助手设置│     settings.py          │
│  ⏱ 计时器│                         │
├──────────┴──────────────────────────┤
│  v1.2.0            [取消] [💾 保存] │
└─────────────────────────────────────┘
```

- 内置页面（API配置/外观/编辑器/关于）显示在分隔线上方
- 插件 `settings.py` 自动注册的设置页显示在分隔线下方
- 多个插件的页面按 `order` 排序
- 从插件卡片点击「设置」按钮会直接跳转到对应设置页

**示例 2：带开关和多选项的设置页**：

```python
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox, QCheckBox, QFrame
)

def build_settings_page():
    page = QWidget()
    page.setObjectName("settingsPage")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)

    title = QLabel("计时器设置")
    title.setObjectName("settingsSectionTitle")
    layout.addWidget(title)

    # 卡片容器
    card = QFrame()
    card.setObjectName("settingsCard")
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(20, 18, 20, 18)
    card_layout.setSpacing(12)

    # 难度选择
    lbl_diff = QLabel("默认难度")
    lbl_diff.setObjectName("settingsLabel")
    combo_diff = QComboBox()
    combo_diff.setObjectName("settingsCombo")
    combo_diff.addItems(["初级", "中级", "高级"])
    combo_diff.setMinimumHeight(34)
    card_layout.addWidget(lbl_diff)
    card_layout.addWidget(combo_diff)

    # 开关
    cb_auto = QCheckBox("显示倒计时提醒")
    cb_auto.setObjectName("settingsCheck")
    cb_auto.setChecked(True)
    card_layout.addWidget(cb_auto)

    layout.addWidget(card)
    layout.addStretch()

    page._combo_diff = combo_diff
    page._cb_auto = cb_auto
    return page

def collect_settings(page_widget) -> dict:
    return {
        "difficulty": page_widget._combo_diff.currentText(),
        "show_reminder": page_widget._cb_auto.isChecked(),
    }

def on_enable():
    api = get_api()
    api.register_settings_page(
        meta={"name": "计时器", "icon": "⏱", "order": 150},
        create_widget_fn=build_settings_page,
        collect_config_fn=collect_settings,
    )
```

**设置页样式说明**：

| ObjectName | 用途 | 说明 |
|------------|------|------|
| `settingsPage` | 页面根容器 | 默认 `background-color: #1e1e2e` |
| `settingsSectionTitle` | 页面标题 | 18px 紫色粗体 |
| `settingsSectionDesc` | 页面描述 | 12px 灰色 |
| `settingsCard` | 卡片容器 | `#181825` 背景 + 圆角边框 |
| `settingsLabel` | 字段标签 | 12px 粗体 |
| `settingsInput` | 文本输入框 | 深色背景 + 圆角 |
| `settingsCombo` | 下拉选择框 | 深色样式 |
| `settingsSpin` | 数字输入框 | 深色样式 |
| `settingsSmallBtn` | 次级按钮 | `#313244` 背景 |
| `settingsPrimaryBtn` | 主按钮 | 紫色背景 |

> **提示**：使用以上 ObjectName 可以让页面自动获得与内置设置页一致的主题样式（深色/浅色均适配），无需手动编写 QSS。系统 v2.0.0 起支持 3 套主题（Catppuccin Mocha/Latte/Macchiato），所有 ObjectName 对应的配色会自动跟随当前主题切换。

**生命周期说明**：
- `create_widget_fn` 在用户**首次点击该设置页**时调用（延迟构建）
- `collect_config_fn` 在用户**点击保存按钮**时调用
- 插件禁用/删除时，设置页自动从导航栏中移除
- 设置页 widget 在对话框关闭后释放（下次打开重新构建）

### 4.12 训练子功能注册

> **v1.5.0 新增**：插件可以在「模拟训练」面板中注册自定义子功能，系统自动生成入口卡片、历史按钮和子页面。

#### 基本用法

```python
from workers.plugin_manager import get_api

class MyTrainingManager:
    """自定义训练管理器"""
    def __init__(self, train_mgr):
        self._tm = train_mgr       # TrainingManager 实例
        self._mw = train_mgr._mw   # 主窗口引用

    def build_pages(self, parent_stack):
        """构建子功能页面到 QStackedWidget，返回起始索引"""
        # parent_stack 是训练面板的 QStackedWidget
        start = parent_stack.count()
        # ... 创建并添加 QWidget 页面 ...
        return start

    def show_history(self):
        """（可选）显示历史记录"""
        pass

def on_enable():
    api = get_api()
    api.register_training_sub_feature(
        {
            "id": "my_train",              # 唯一标识（仅本插件内唯一）
            "name": "我的训练模式",          # 入口卡片标题
            "icon": "🔧",                  # 卡片图标
            "accent_color": "#f9e2af",     # 标题颜色
            "description": "自定义辩论训练",  # 卡片描述
            "tags": ["自定义", "实战"],      # 特性标签
            "order": 100,                   # 排序（50+ 避免与内置重叠）
            "history_label": "📂 记录",     # 标题栏历史按钮文字
        },
        MyTrainingManager
    )
```

#### `SUB_FEATURE_INFO` 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | str | ✅ | 唯一标识（仅本插件内唯一，系统自动加 `plugin_<插件ID>_` 前缀） |
| `name` | str | ✅ | 入口卡片标题 |
| `icon` | str | ✅ | emoji 图标 |
| `description` | str | ✅ | 卡片描述文字 |
| `order` | int | ✅ | 排序（越小越靠前，建议 50+） |
| `accent_color` | str | ❌ | 标题 CSS 颜色，默认 `#f9e2af` |
| `tags` | list[str] | ❌ | 特性标签列表 |
| `history_label` | str | ❌ | 标题栏历史按钮文字，不提供则不显示按钮 |

#### 管理器类规范

```python
class MyTrainingManager:
    def __init__(self, train_mgr):
        """
        train_mgr: TrainingManager 实例
          - train_mgr._mw          → 主窗口
          - train_mgr._train_stack → QStackedWidget（父页面栈）
          - train_mgr._lbl_train_title / _lbl_train_status → 标题栏控件
          - train_mgr.toggle_visibility() / close_if_open() → 面板控制
        """

    def build_pages(self, parent_stack) -> int:
        """必须实现：在 parent_stack 中构建子页面"""
        return parent_stack.count()  # 返回起始索引

    def show_history(self):
        """可选实现：点击标题栏历史按钮时调用"""
```

#### 生命周期

- **注册时机**：在 `on_enable()` 中调用
- **自动清理**：插件禁用/删除时，子功能自动从训练面板注销
- **入口卡片**：系统自动生成，显示在「模拟训练」首页
- **历史按钮**：系统根据 `history_label` 自动在标题栏创建

### 4.13 控制台命令执行

> 插件可以通过 API 以编程方式执行 StarDebate 调试台的内置命令，获取命令输出结果。

#### `api.execute_command(cmd_line: str) -> dict`

在控制台中执行一条内置命令并返回结果。适用于插件自动化流程中获取系统信息。

| 参数 | 类型 | 说明 |
|------|------|------|
| `cmd_line` | `str` | 要执行的命令字符串，如 `"version"`、`"status"`、`"plugin list"` |

> **注意**：命令格式为 **冒号分隔**（如 `log:level`），与 `config/command_defs.json` 中定义的**树形空格分隔**格式不同。旧格式保留兼容，新代码建议使用空格格式。命令定义以 `config/command_defs.json` 为权威来源，`CommandHandler.BUILTIN_COMMANDS` 和 `SuggestPopup.ARG_DEFS` 可能不同步，新增命令时优先更新 `command_defs.json`。

**返回**：`dict` 结构：

```python
{
    "success": True,          # bool — 命令是否执行成功
    "output": "版本信息...",   # str  — 命令生成的输出文本（多条日志用换行拼接）
    "error": ""               # str  — 错误信息（成功时为空）
}
```

**示例 1：获取系统版本**：

```python
def on_enable():
    api = get_api()
    result = api.execute_command("version")
    if result["success"]:
        api.update_status(f"运行环境: {result['output']}")
```

**示例 2：列出所有插件**：

```python
result = api.execute_command("plugin list")
if result["success"]:
    lines = result["output"].split("\n")
    enabled_count = sum(1 for l in lines if "● 启用" in l)
    api.update_status(f"当前 {enabled_count} 个插件已启用")
```

**示例 3：检查系统状态**：

```python
def check_system_ready():
    api = get_api()
    result = api.execute_command("status")
    if not result["success"]:
        api.show_notification("系统检查失败", result["error"])
        return False
    output = result["output"]
    if "API 连接: 未测试" in output:
        api.update_status("提示: 请先测试 API 连接")
    return True
```

**支持的内置命令**（完整列表可通过 help 查看）：

| 命令 | 说明 | 处理函数 |
|------|------|---------|
| `help` | 显示所有可用命令列表 | `_cmd_help` |
| `clear` | 清空当前日志显示区 | 特殊信号 |
| `status` | 系统状态概览 | `_cmd_status` |
| `version` | 显示 StarDebate 应用版本号 | `_cmd_version` |
| `log level <级别>` | 设置日志显示级别 | `_cmd_log_level` |
| `log export` | 导出当前日志到文件 | `_cmd_log_export` |
| `log clean` | 手动清理超过7天的旧日志 | `_cmd_log_clean` |
| `log path` | 显示当前日志文件路径 | `_cmd_log_path` |
| `log keep` | **一次性标记**：正常退出时保留本次运行日志 | `_cmd_log_keep` |
| `config show` | 显示当前配置信息(Key脱敏) | `_cmd_config_show` |
| `config reload` | 重新加载所有配置文件 | `_cmd_config_reload` |
| `plugin list` | 列出所有已安装插件及状态 | `_cmd_plugin_list` |
| `plugin info <插件ID>` | 查看指定插件详细信息 | `_cmd_plugin_info` |
| `plugin reload` | 重新加载所有插件 | `_cmd_plugin_reload` |
| `plugin enable <插件ID>` | 启用指定插件 | `_cmd_plugin_enable` |
| `plugin disable <插件ID>` | 禁用指定插件 | `_cmd_plugin_disable` |
| `theme` | 显示当前主题名称 | `_cmd_theme` |
| `theme list` | 列出所有可用主题 | `_cmd_theme_list` |
| `theme set <主题名>` | 切换主题（立即生效） | `_cmd_theme_set` |
| `theme reload` | 重新加载当前主题 QSS | `_cmd_theme_reload` |
| `timer start <秒数>` | 启动倒计时器 | `_cmd_timer_start` |
| `timer stop` | 停止当前计时器 | `_cmd_timer_stop` |
| `api test` | 测试 AI API 连接状态 | `_cmd_api_test` |
| `api models` | 列出当前 API 可用模型 | `_cmd_api_models` |
| `api config` | 显示当前 AI 配置 | `_cmd_api_config` |
| `monitor status` | 显示所有监视开关状态 | `_cmd_monitor_status` |
| `monitor enable <类型>` | 启用指定监视类型 | `_cmd_monitor_enable` |
| `monitor disable <类型>` | 禁用指定监视类型 | `_cmd_monitor_disable` |
| `monitor log view` | 查看监视日志(过滤显示) | `_cmd_monitor_log_view` |
| `monitor log export` | 导出监视日志到文件 | `_cmd_monitor_log_export` |
| `panel open <面板名>` | 打开指定功能面板 | `_cmd_panel_open` |
| `panel close` | 关闭当前功能面板 | `_cmd_panel_close` |
| `project info` | 显示当前辩论项目信息 | `_cmd_project_info` |
| `project list` | 列出最近打开的项目 | `_cmd_project_list` |
| `check all` | 全面诊断所有组件加载状态 | `_cmd_check_all` |
| `check manager` | 检查所有管理器加载状态 | `_cmd_check_manager` |
| `check plugin` | 检查插件加载状态 | `_cmd_check_plugin` |
| `check panel` | 检查功能面板加载状态 | `_cmd_check_panel` |

> **注意**：
> - 命令定义以 `config/command_defs.json` 为权威来源（树形结构），新增命令时优先更新此文件。
> - 当前运行时支持 17 条 `:` 格式的基础命令（如 `log:level`），其余命令（`monitor` / `panel` / `project` / `check` / `alias` 等）的 handler 已在 `command_handler.py` 中实现，但尚未全部接入执行分派。文档中的空格格式（如 `log level`）是标准输入格式，代码内部自动转换为 `:` 格式匹配。
> - 插件可通过 `api.execute_command()` 执行当前可用的任意命令。

---

### 4.14 快捷键注册

> **v3.0.0 新增**：插件可注册全局快捷键，用户可在设置页的「快捷键」面板中自定义按键组合。

#### `api.register_shortcut(shortcut_id, keys, description, callback, category="插件快捷键")`

| 参数 | 类型 | 说明 |
|------|------|------|
| `shortcut_id` | `str` | 唯一标识（建议 `"插件ID:功能"` 格式，如 `"timer:start_pause"`） |
| `keys` | `str` | 默认组合键，如 `"Ctrl+Shift+T"` |
| `description` | `str` | 功能描述（如 "开始/暂停计时"） |
| `callback` | `callable` | 触发回调函数（无参数） |
| `category` | `str` | 分类名（在设置页显示），默认 `"插件快捷键"` |

**自动管理**：插件启用时注册，禁用/删除时自动清理，无需在 `on_disable` 中手动调用。

**示例**：

```python
def on_enable():
    api = get_api()

    # 注册一个快捷键
    api.register_shortcut(
        "timer:start_pause",
        "Ctrl+Shift+T",
        "开始/暂停计时",
        on_toggle_timer
    )

    api.register_shortcut(
        "timer:reset",
        "Ctrl+Shift+R",
        "重置计时器",
        on_reset_timer
    )

def on_toggle_timer():
    api = get_api()
    # 切换计时器状态
    ...

def on_reset_timer():
    api = get_api()
    # 重置计时器
    ...
```

**用户自定义**：用户可在「设置 → 快捷键」页面中查看所有已注册的快捷键，点击录制按钮修改按键组合。所有自定义保存在 `config/keyboard_shortcuts.json` 中。

**冲突检测**：如果两个功能使用了相同的组合键，设置页会以红色高亮显示冲突行。

**注意事项**：
- 组合键支持 `Ctrl`、`Shift`、`Alt`、`Meta` + 单字母/数字/功能键
- 插件快捷键与内置快捷键共享全局命名空间，冲突时设置页会提示
- 快捷键回调在 `QShortcut.activated` 信号中触发，确保在主线程执行

#### `api.unregister_shortcuts()`

注销此插件的所有快捷键（仅在极少数需要动态管理的场景中使用，一般无需手动调用）。

```python
def on_disable():
    api = get_api()
    api.unregister_shortcuts()
```

---

### 4.14 撤销栈注册（v1.6.0 新增）

> 如果插件有自己的可编辑内容（文本输入框、树节点等），注册 `QUndoStack`
> 后，「编辑」菜单的撤销/重做将自动绑定到当前激活面板的栈上。

#### `api.register_undo_stack(stack)`

| 参数 | 类型 | 说明 |
|------|------|------|
| stack | `QUndoStack` | 插件的撤销栈实例 |

注册后，当插件面板被激活时，**自动**绑定到「编辑」菜单。

```python
def on_enable():
    api = get_api()
    from PyQt5.QtWidgets import QUndoStack
    from PyQt5.QtWidgets import QUndoCommand

    self._undo_stack = QUndoStack()
    api.register_undo_stack(self._undo_stack)

    # 自定义命令
    class MyEditCommand(QUndoCommand):
        def __init__(self, editor, old_text, new_text):
            super().__init__("编辑")
            self._editor = editor
            self._old, self._new = old_text, new_text
        def undo(self): self._editor.setPlainText(self._old)
        def redo(self): self._editor.setPlainText(self._new)

    # 当用户编辑完成时推入命令
    # self._undo_stack.push(MyEditCommand(editor, old, new))
```

#### `api.unregister_undo_stack()`

在 `on_disable()` 中调用，注销撤销栈。

```python
def on_disable():
    api = get_api()
    api.unregister_undo_stack()
```

#### `api.activate_undo_stack()`

当插件的面板被切换到前台时调用，激活本插件的撤销栈（如果插件自己的面板切换逻辑不经过主窗口导航栏，需要手动调用）。

```python
def on_my_panel_shown():
    api = get_api()
    api.activate_undo_stack()
```

---

### 4.15 跨插件函数调用

> **适用场景**：插件 A 需要调用插件 B 中暴露的函数。例如项目浏览器右键菜单调用 DebateClaw 的 `add_file_to_session()`。

通过 `get_manager()` 获取 `PluginManager`，再用 `get_plugin(id).call()` 安全调用：

```python
from workers.plugin_manager import get_manager

mgr = get_manager()
info = mgr.get_plugin("debate_claw")
if info and info.enabled:
    info.call("add_file_to_session", file_path, file_name)
```

| 方法 | 说明 |
|------|------|
| `get_manager()` | 获取 PluginManager 单例 |
| `mgr.get_plugin(plugin_id)` | 按 ID 查找插件，返回 `PluginInfo` 或 `None` |
| `info.call(func_name, *args)` | 安全调用插件模块中的顶层函数，带 try/except 保护 |

**注意事项**：
- `call()` 只能调用插件模块的**顶层函数**（模块级函数，非嵌套闭包）
- 被调用的函数应当设计为无副作用的**入口函数**
- 调用前务必检查 `info.enabled`，避免调用已禁用的插件

**现有跨插件入口函数**：

| 插件 | 函数 | 说明 |
|------|------|------|
| `debate_claw` | `add_file_to_session(file_path, file_name)` | 添加文件引用到当前 Claw 会话的附件列表 |

### 4.16 右键菜单项注册

> **适用场景**：插件需要在项目浏览器的文件右键菜单中添加自定义菜单项。

通过 `api.register_context_menu_item()` 注册：

```python
def on_enable():
    api = get_api()
    api.register_context_menu_item(
        "菜单项名称",
        lambda file_path: handle_file(file_path),
        order=50,
    )
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `label` | `str` | 菜单显示文本 |
| `callback` | `Callable[[str], None]` | 接收 `file_path` 的回调函数 |
| `order` | `int` | 排序顺序（越小越靠前），默认 `100` |

**注意事项**：
- 推荐在 `on_enable()` 中注册，禁用时会自动清理
- 回调函数接收文件的**绝对路径**作为唯一参数
- 多个插件可同时注册菜单项，按 `order` 排序展示

### 4.17 监视日志插入

> **v2.5.0 架构变更**：日志系统已重构为**独立进程架构**。监视钩子通过 `multiprocessing.Queue` 投递到 `LogService` 独立进程写入文件。主窗口崩溃不影响日志落盘，队列异常时自动降级为文件直写。插件开发者无需任何代码修改，现有调用自动受益。

#### 架构概览

```
插件 → api.log_monitor() → PluginSafeAPI → DebugMonitorManager
                                               │
                            ┌──────────────────┼──────────────────┐
                            ▼                  ▼                  ▼
                      Layer 1:             Layer 2:           Layer 3:
                    log_queue.put()    _emergency_write()   LogManager.info()
                    → LogService       → 直写日志文件       → (旧版兼容)
                    (独立进程)          (队列满/断降级)      (无队列时回退)

LogService (star_debate_log.py) 内部:
  ├── LogManager → 文件写入
  └── SystemHealthMonitor → 主进程存活检测 / 背压监控 / 崩溃快照
```

#### `api.log_monitor(monitor_type: str, message: str)`

向调试监视系统插入一条带标签的日志。如果对应监视类型未开启，此调用无效果（几乎零开销）。

| 参数 | 类型 | 说明 |
|------|------|------|
| `monitor_type` | `str` | 监视类型，取值为: `"variable_watch"` / `"function_watch"` / `"plugin_watch"` / `"api_watch"` / `"ai_watch"` |
| `message` | `str` | 日志消息文本 |

#### 监视类型说明

| monitor_type | 日志标签 | 用途 | 适用场景 |
|-------------|---------|------|----------|
| `variable_watch` | `[VAR]` | 变量变化记录 | 插件内部状态变更、配置更新 |
| `function_watch` | `[FUNC]` | 函数调用结果 | 插件内所有 `def` 函数自动记录（框架自动注入） |
| `plugin_watch` | `[PLUGIN]` | 插件状态变更 | 加载、启用、禁用、数据处理进度 |
| `api_watch` | `[API]` | API 请求详情 | 第三方 HTTP 请求响应 |
| `ai_watch` | `[AI]` | AI 功能结果 | `api.call_ai()` 调用结果 |

#### 三层容灾保障

| 层级 | 触发条件 | 行为 | 数据丢失风险 |
|------|---------|------|-------------|
| Layer 1 | 正常运行时 | `log_queue.put_nowait()` → LogService 独立进程写文件 | 无 |
| Layer 2 | 队列满 / LogService 进程断开 | `_emergency_write()` 直写日志文件（绕过队列） | 极低（仅 OS 级崩溃丢失） |
| Layer 3 | 无队列可用（旧版兼容） | 回退 `LogManager.info()` | 与主进程同命运 |

> **插件无需感知层级切换**：降级全自动完成。首次或每 10 次应急写入会在日志中附加 `[MON-EMERGENCY]` 或 `[EMERGENCY]` 标记，方便事后诊断。

#### 崩溃检测

LogService 内置的 `SystemHealthMonitor` 线程每 3 秒检测主进程存活：
- 连续 3 次检测不到 → 判定主进程崩溃
- 排空队列中所有残留日志条目并写入文件
- 写入 `[SYS]` 崩溃快照（PID、退出时间、队列残留数、应急写入次数、最后心跳时间）

#### 示例

**示例 1：记录插件处理进度**：
```python
def process_debate_data():
    api = get_api()
    api.log_monitor("plugin_watch", "开始分析辩稿数据...")
    # ... 处理逻辑 ...
    api.log_monitor("plugin_watch", "辩稿分析完成，共处理 150 条论点")
```

**示例 2：记录 AI 调用耗时**：
```python
import time

def call_ai_with_monitor():
    api = get_api()
    start = time.time()
    result = api.call_ai([{"role": "user", "content": "分析这个辩题"}])
    elapsed = (time.time() - start) * 1000
    api.log_monitor("ai_watch", f"插件 AI 分析耗时: {elapsed:.0f}ms")
    return result
```

**示例 3：变量变化追踪**：
```python
class PluginState:
    def __init__(self):
        self._status = "idle"

    def set_status(self, new_status):
        api = get_api()
        api.log_monitor("variable_watch",
                        f"PluginState._status: '{self._status}' → '{new_status}'")
        self._status = new_status
```

**示例 4：记录 HTTP API 请求（非 `call_ai` 的第三方 API）**：
```python
import requests

def query_external_api(query: str):
    api = get_api()
    api.log_monitor("api_watch", f"请求: POST https://api.example.com/query")
    resp = requests.post("https://api.example.com/query", json={"q": query})
    status = "✓" if resp.ok else "✗"
    api.log_monitor("api_watch", f"{status} 响应: {resp.status_code} | {len(resp.text)}B")
```

> **提示**：监视日志仅在用户在调试台「调试 ▼」菜单中开启对应监视类型后才会显示。此 API 调用开销极小（仅做简单的开关检查），可放心在每条处理分支中使用。详细插入规范见 [§4.18 监视钩子插入细则](#418-监视钩子插入细则)。
>
> **v4.4.0 自动 function_watch**：插件模块加载后，框架会自动为所有顶层 `def` 函数（不含 `_` 开头的私有函数和 `on_enable`/`on_disable` 生命周期方法）安装函数监视钩子。开启 `function_watch` 后，日志中自动出现 `[FUNC] 插件ID:函数名 → ✅/❌` 条目，插件开发者**无需手动调用 `api.log_monitor("function_watch", ...)` 来追踪函数调用**。

---

### 4.18 控制台自定义命令注册

> 插件可以注册自定义命令，用户可在调试台中直接输入命令名执行。这是插件暴露批处理/管理功能给高级用户的主要方式。

#### `api.register_console_command(cmd_name, handler_fn, args_desc="", description="", category="插件命令")`

注册一个用户可在调试台运行的自定义命令。注册后，输入 `help` 将列出该命令。

| 参数 | 类型 | 说明 |
|------|------|------|
| `cmd_name` | `str` | 命令名称（建议使用 `插件ID:命令` 命名，如 `"timer:start"`） |
| `handler_fn` | `callable` | 命令处理函数，签名 `(args: str) -> str | None`。参数为命令后的所有字符，返回值作为 INFO 日志输出（返回 `None` 无输出） |
| `args_desc` | `str` | 参数说明（如 `"<秒数>"`），显示在 `help` 命令中 |
| `description` | `str` | 命令描述，显示在 `help` 命令中 |
| `category` | `str` | 命令分类（默认 `"插件命令"`），`help` 命令中按分类分组显示 |

> **注意**：必须在 `on_enable()` 中调用。插件禁用/删除时命令自动注销。
>
> **自动补全集成**：注册的命令会自动出现在调试台的 `SuggestPopup` 自动补全列表中，支持：
> - 输入命令名时模糊匹配提示
> - 命令名+空格后进入参数补全模式
> - `args_desc` 为 `<...>` 格式时显示为灰色斜体占位提示（如 `<插件ID>`、`<关键词>`）
> - 如需为自定义命令提供具体的参数可选值列表，需在 `suggest_popup.py` 的 `ARG_DEFS` 注册表中添加对应项

**示例 1：简单的数据查询命令**：

```python
def handle_stats(args):
    """处理统计查询命令"""
    api = get_api()
    pro_text = api.get_speech_content("pro")
    con_text = api.get_speech_content("con")
    pro_chars = len(pro_text.replace("\n", "").replace(" ", ""))
    con_chars = len(con_text.replace("\n", "").replace(" ", ""))
    return f"正方: {pro_chars} 字 | 反方: {con_chars} 字"

def on_enable():
    api = get_api()
    api.register_console_command(
        cmd_name="wordcount",
        handler_fn=handle_stats,
        args_desc="",
        description="统计双方一辩稿字数",
        category="辩论数据"
    )
```

用户在调试台输入 `wordcount` 即可看到字数统计结果。

**示例 2：带参数的命令**：

```python
def handle_search(args):
    """搜索资料稿"""
    if not args:
        return "用法: search <关键词>"
    api = get_api()
    results = api.search_ref_doc(args)
    if not results:
        return f"未找到包含 '{args}' 的资料"
    lines = [f"搜索 '{args}': 找到 {len(results)} 条"]
    for hit in results[:10]:  # 最多显示10条
        lines.append(f"  [{hit['match_column_cn']}] {hit['cell_text'][:60]}")
    return "\n".join(lines)

def on_enable():
    api = get_api()
    api.register_console_command(
        cmd_name="search",
        handler_fn=handle_search,
        args_desc="<关键词>",
        description="搜索资料稿内容",
        category="辩论数据"
    )
```

用户在调试台输入 `search 人工智能` 即可搜索资料稿。

**示例 3：批量操作命令（结合 execute_command）**：

```python
def handle_export_all(args):
    """导出所有可用数据"""
    api = get_api()

    # 获取系统信息
    ver = api.execute_command("version")
    plugins = api.execute_command("plugin:list")

    # 获取辩论数据
    info = api.get_debate_info()
    if not info.get("title"):
        return "请先打开一个辩论项目"

    pro_text = api.get_speech_content("pro")
    con_text = api.get_speech_content("con")

    report = f"""# 辩论数据导出
> 导出时间: {args or '手动导出'}

## 系统信息
- {ver['output']}
- 已启用插件: {len([l for l in plugins['output'].split(chr(10)) if '● 启用' in l])} 个

## 辩题: {info['title']}
### 正方: {info['pro_side']}
{pro_text[:500]}...

### 反方: {info['con_side']}
{con_text[:500]}...
"""
    from datetime import datetime
    filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    api.write_file_in_project(filename, report)
    api.log_monitor("plugin_watch", f"数据导出: {filename}")
    return f"已导出到 {filename}"

def on_enable():
    api = get_api()
    api.register_console_command(
        cmd_name="export:all",
        handler_fn=handle_export_all,
        args_desc="[标签]",
        description="一键导出辩论全部数据为 Markdown",
        category="导出"
    )
```

**命令命名建议**：
- 使用 `插件ID:命令` 格式避免冲突，如 `timer:start`、`export:report`
- 所有命令显示在 `help` 中按分类分组
- 系统命令以空格分隔（如 `log level`、`plugin list`），插件命令可沿用此约定
- 插件命令在自动补全悬浮窗中以 **紫色** 显示并带有 `←插件:分类` 后缀，方便与内置命令区分

---

### 4.17a 自定义多选框

> 插件可使用 API 快速创建 StarCheckBox 自定义多选框控件，替代 Qt 原生 QCheckBox，支持 SVG 图标渲染、可调大小、主题自适应。

#### `api.create_checkbox(text="", checked=False, checkbox_size=20, object_name="")`

创建并返回一个 `StarCheckBox` 控件实例，可添加到插件的自定义面板中。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `text` | `str` | `""` | 标签文字 |
| `checked` | `bool` | `False` | 初始选中状态 |
| `checkbox_size` | `int` | `20` | 图标像素大小（≥12px，文字字号自动跟随 `size × 0.7`） |
| `object_name` | `str` | `""` | QSS objectName（可选，默认 `"starCheckBox"`） |

**返回值**：`StarCheckBox` 控件实例（QWidget 子类）。

**可用信号**（connect 绑定）：
| 信号 | 参数 | 说明 |
|------|------|------|
| `toggled` | `bool` | 状态翻转时发射，参数为新选中状态 |
| `stateChanged` | `int` | 状态改变时发射（`0`=未选中, `2`=选中） |
| `clicked` | — | 点击时发射 |

**可用属性**（property 方式读写）：
| 属性 | 类型 | 说明 |
|------|------|------|
| `.checked` | `bool` | 获选/设置选中状态 |
| `.text_prop` | `str` | 获选/设置标签文字 |
| `.checkbox_size` | `int` | 获选/设置图标大小 |

> **注意**：返回的控件 `parent=None`，需要手动添加到你的面板 layout 中。

**示例 1：基本使用**：

```python
from PyQt5.QtWidgets import QVBoxLayout, QWidget

def build_setting_panel():
    panel = QWidget()
    layout = QVBoxLayout(panel)
    api = get_api()

    # 创建选中状态的复选框（22px 图标）
    cb_auto = api.create_checkbox("启用自动保存", checked=True,
                                   checkbox_size=22)
    cb_auto.toggled.connect(lambda checked:
        print(f"自动保存已{'开启' if checked else '关闭'}"))
    layout.addWidget(cb_auto)

    # 创建未选中的复选框（默认 20px）
    cb_advanced = api.create_checkbox("显示高级选项")
    cb_advanced.stateChanged.connect(lambda state:
        print(f"高级选项状态: {state}"))  # 0=未选中, 2=选中
    layout.addWidget(cb_advanced)

    return panel
```

**示例 2：配合自定义面板使用**：

```python
def on_enable():
    api = get_api()
    api.register_panel(
        side="right",
        title="插件设置",
        emoji="⚙️",
        tooltip="插件配置面板",
        create_widget=build_setting_panel
    )
```

**示例 3：读取/控制状态**：

```python
def on_enable():
    api = get_api()
    # 假设 cb 是之前创建的复选框引用
    cb = api.create_checkbox("自动记录", checked=False)

    # ... 用户交互后 ...

    # 读取状态
    if cb.checked:                    # property 方式
        print("已勾选")

    # 程序控制
    cb.setChecked(True)               # 方法方式
    cb.checkbox_size = 24             # 修改图标大小
    cb.text_prop = "已更改的文字"     # 修改标签
```

**四态交互效果**：
| 状态 | 图标 | 文字颜色 | 说明 |
|------|------|----------|------|
| Normal (未选中) | 空心方框 | subtext 色 | 默认状态 |
| Checked (选中) | 填充方框+勾选 | text 色 | 勾选状态 |
| Hover | 空心/填充不变 | 不变 | overlay 背景微微提亮 |
| Disabled | 40% 透明度 | muted 色 | `setEnabled(False)` 后置灰 |

**主题适配**：
组件自动从 `config.json` 读取当前主题，从对应 `theme.json` 获取配色，三主题（Mocha 深色/Latte 浅色/Macchiato 中深色）均适用。

> **提示**：如需批量创建多个复选框，可以让 `create_checkbox()` 返回的控件存入列表，后续通过遍历操作状态。

---

### 4.17b 自定义数字输入框

> 插件可使用 API 快速创建 StarSpinBox / StarDoubleSpinBox 自定义数字输入框，替代 Qt 原生 QSpinBox / QDoubleSpinBox。支持 SVG 图标渲染、三种布局模式、长按自动重复、主题自适应。

#### `api.create_spinbox()` — 整数输入框

```python
spin = api.create_spinbox(
    value=42,           # 初始值
    min_value=0,        # 最小值
    max_value=100,      # 最大值
    step=5,             # 步长
    suffix=" 人",       # 后缀
    button_layout="right",  # ★ 布局模式: "right"/"split"/"embedded"
    spin_height=32,     # 整体高度
    button_width=22,    # 按钮区宽度
    editable=True,      # 是否可直接编辑
    text_align="left",  # 文字对齐: "left"/"center"/"right"
    font_size=None,     # 文字大小 (None=自动)
)
spin.valueChanged.connect(lambda v: print(f"新值: {v}"))
```

#### `api.create_double_spinbox()` — 浮点数输入框

```python
spin = api.create_double_spinbox(
    value=0.7,          # 初始值
    min_value=0.0,      # 最小值
    max_value=2.0,      # 最大值
    step=0.1,           # 步长
    decimals=2,         # ★ 小数位数
    prefix="温度: ",    # 前缀
)
```

#### 三种布局模式

| 模式 | `button_layout` | 效果 | 适用场景 |
|------|:-----------:|------|----------|
| 右侧竖直 (默认) | `"right"` | `[编辑区 \| ▲▼]` | 通用/设置页 |
| 左右分离 | `"split"` | `[▼ \| 编辑区 \| ▲]` | 步进调节 |
| 紧凑内嵌 | `"embedded"` | `[编辑区 \| ▲▼内嵌]` | 表格/紧凑布局 |

#### 参数速查

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `value` | int/float | 0 | 初始值 |
| `min_value` | int/float | 0 | 最小值 |
| `max_value` | int/float | 99 | 最大值 |
| `step` | int/float | 1 | 步长 |
| `prefix` | str | `""` | 前缀（如 `"$"`） |
| `suffix` | str | `""` | 后缀（如 `" px"`） |
| `button_layout` | str | `"right"` | 布局模式 |
| `spin_height` | int | 32 | 整体高度（≥24px） |
| `button_width` | int | 22 | 按钮区宽度 |
| `editable` | bool | True | 是否可直接编辑 |
| `text_align` | str | `"left"` | 文字对齐 |
| `font_size` | int/None | None | 文字大小（自动） |
| `decimals` | int | 2 | ★ 仅 `create_double_spinbox` |

#### 主要 API

| 方法 | 说明 |
|------|------|
| `value()` | 获取当前值 |
| `setValue(v)` | 设置值（自动 clamp） |
| `setRange(min, max)` | 设置范围 |
| `setButtonLayout(mode)` | 切换布局 |
| `setTextAlign(align)` | 文字对齐 |
| `setFontSize(size)` | 字体大小 |

**信号**：`valueChanged(int/float)` / `editingFinished()`

#### 示例

```python
def on_enable():
    api = get_api()
    api.register_panel(
        side="right", title="计时设置", emoji="⏱️",
        tooltip="辩论计时器配置",
        create_widget=build_timer_panel,
    )

def build_timer_panel():
    panel = QWidget()
    layout = QVBoxLayout(panel)
    api = get_api()

    # 正方时间
    spin_pro = api.create_spinbox(value=180, max_value=600,
                                   step=30, suffix=" 秒",
                                   button_layout="embedded")
    layout.addWidget(spin_pro)

    # 温度参数
    spin_temp = api.create_double_spinbox(value=0.7, min_value=0.0,
                                           max_value=2.0, step=0.1,
                                           decimals=1)
    layout.addWidget(spin_temp)
    return panel
```

> **强制要求**：插件中需要使用数字输入框时，应使用 `api.create_spinbox()` / `api.create_double_spinbox()` 而非 Qt 原生 `QSpinBox` / `QDoubleSpinBox`。

---

### 4.17c SVG 通用渲染器

> **v2.9.0 新增**：插件可以直接使用 SvgRenderer 创建按主题着色的 SVG 图标，替代本地静态 PNG/SVG。

SvgRenderer 是 StarDebate 内置的 SVG 图标渲染引擎，支持单色/双色/原生三种渲染模式。颜色配置嵌入各主题 `theme.json` 的 `svg_renderer` 字段。

#### 直接导入（无需 API 封装）

```python
from components.svg_renderer import SvgRenderer
```

> SvgRenderer 是全局单例，应用启动时自动初始化，插件无需调用 `init()`。

#### `SvgRenderer.icon(svg_path, size, color=None)` → QPixmap

使用当前主题颜色渲染单色 SVG 图标。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `svg_path` | `str` | — | SVG 文件路径（推荐插件本地路径或使用项目 `icon/` 目录） |
| `size` | `int` | — | 图标边长（正方形），如 `24` 即 24×24px |
| `color` | `str\|QColor\|None` | `None` | 主题色键名（如 `"text"`、`"accent_purple"`）或 hex 颜色。`None` 时使用 `theme.json` 中 `svg_renderer.mono.color` |

#### `SvgRenderer.bicolor(svg_path, size, primary=None, accent=None)` → QPixmap

使用双色方案渲染 SVG：按 `data-color="primary"` / `data-color="accent"` 属性分别着色。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `primary` | `str\|QColor\|None` | `None` | 主色键名，`None` 使用 `theme.json.dual.primary` |
| `accent` | `str\|QColor\|None` | `None` | 辅色键名，`None` 使用 `theme.json.dual.accent` |

#### `SvgRenderer.named(name, size)` → QPixmap

按预设名称获取内置图标。

| 预设名称 | 对应图标 |
|----------|----------|
| `"checkbox_unchecked"` | `icon/checkbox/square.svg` |
| `"checkbox_checked"` | `icon/checkbox/checkmark_square.svg` |
| `"msg_info"` | `icon/message_box/info_circle.svg` |
| `"msg_warning"` | `icon/message_box/exclamationmark_circle.svg` |
| `"msg_error"` | `icon/message_box/xmark_circle.svg` |
| `"msg_question"` | `icon/message_box/questionmark_circle.svg` |
| `"spin_up"` | `icon/spinbox/white/arrowtriangle_up_fill_white.svg` |
| `"spin_down"` | `icon/spinbox/white/arrowtriangle_down_fill_white.svg` |

#### `SvgRenderer.qicon(svg_path, size, disabled_pct=0.4)` → QIcon

生成含 Normal/Disabled 状态的 QIcon（常用于 QPushButton 等控件）。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `disabled_pct` | `float` | `0.4` | Disabled 状态图标透明度（0.0–1.0） |

#### 注册自定义预设图标

```python
SvgRenderer.register_icon("my_icon", "plugins/my_plugin/icon_custom.svg")
pix = SvgRenderer.named("my_icon", 24)   # 后续通过名称获取
SvgRenderer.unregister_icon("my_icon")    # 插件禁用时清理
```

#### 主题切换监听

插件面板如含 SVG 图标，建议监听主题切换以刷新：

```python
api.on("theme_changed", lambda name: SvgRenderer.set_theme(name) or SvgRenderer.clear_cache())
```

#### SVG 模板编写规范

推荐使用白色模板（所有 `fill="#FFFFFF"`），渲染器通过 `QPainter.CompositionMode_SourceIn` 动态着色：

```xml
<!-- ✅ 推荐：纯白模板，亮色/深色主题均可自动适配 -->
<svg viewBox="0 0 24 24" fill="none">
  <path fill="#FFFFFF" d="M12 2..."/>
</svg>
```

双色 SVG 需通过 `data-color` 属性标记区域：

```xml
<svg viewBox="0 0 24 24" fill="none">
  <!-- 主色区域 -->
  <path data-color="primary" fill="#FFFFFF" d="M14 2..."/>
  <!-- 辅色区域（如高亮/装饰） -->
  <path data-color="accent" fill="#FFFFFF" d="M14 2v6h6"/>
</svg>
```

#### 完整示例

```python
import os
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtGui import QIcon
from components.svg_renderer import SvgRenderer
from workers.plugin_manager import get_api

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

def on_enable():
    api = get_api()
    svg_path = os.path.join(PLUGIN_DIR, "icon_custom.svg")

    # 单色图标按钮（使用图标文件，自动加载）
    api.register_nav_button(
        side="right", label="我的工具",
        icon="icon_custom.svg",         # ★ 存放在 plugins/插件名/ 下
        emoji="🛠",                     # icon 加载失败时的后备
        tooltip="使用 SVG 图标的导航按钮",
        callback=my_action,
    )

    # 注册面板（支持图标文件）
    api.register_panel(
        side="right", title="工具面板",
        icon="panel.svg",               # ★ 存放在 plugins/插件名/icon/ 下
        emoji="🔧", tooltip="插件面板",
        create_widget=build_panel,
    )

    # 监听主题切换
    api.on("theme_changed", lambda name: (
        SvgRenderer.set_theme(name),
        SvgRenderer.clear_cache(),
    ))

def on_disable():
    SvgRenderer.unregister_icon("my_custom_icon")

def my_action():
    api = get_api()
    api.update_status("按钮被点击！")

def build_panel():
    from PyQt5.QtWidgets import QWidget, QVBoxLayout
    panel = QWidget()
    layout = QVBoxLayout(panel)

    # 预设名称图标
    icon = SvgRenderer.named("msg_info", 20)

    # 双色 SVG 按钮
    dual_svg = os.path.join(PLUGIN_DIR, "icon_dual.svg")
    dual_pix = SvgRenderer.bicolor(dual_svg, 24, primary="accent_purple")
    btn = QPushButton(QIcon(dual_pix), " 分析")
    layout.addWidget(btn)

    return panel
```

---

### 4.17d 自定义按钮（v1.0.0 新增）

> 插件可使用 API 快速创建 StarButton 自定义按钮控件，替代 Qt 原生 QPushButton。支持 6 种排布模式、5 种占比模式、自动尺寸、主题自适应绘制。

#### `api.create_button()` — 自定义按钮

```python
btn = api.create_button(
    text="搜索",                # 按钮文字
    icon=None,                  # 图标（QIcon/QPixmap/文件路径）
    icon_size=24,               # 图标边长（px）
    layout_mode="h_left",       # ★ 排布模式
    text_vertical=False,        # 竖排文字
    text_align="left",          # 文字对齐: "left"/"center"/"right"
    accent=None,                # 主题色 hex（如 "#89b4fa"）
    ratio_mode="sync",          # ★ 占比模式
    ratio_h=0.8,                # 水平占比（0.3~0.9）
    ratio_v=0.8,                # 垂直占比（0.3~0.9）
    checkable=False,            # 是否可勾选
    checked=False,              # 初始勾选状态
    auto_size=True,             # 自动调整尺寸
)
```

**排布模式 (`layout_mode`)：**

| 模式 | 说明 | 效果 |
|------|------|------|
| `h_left` | 图标左、文字右 | `[🔍 搜索]` |
| `h_right` | 图标右、文字左 | `[搜索 🔍]` |
| `v_top` | 图标上、文字下 | 竖排 |
| `v_bottom` | 图标下、文字上 | 竖排 |
| `text_only` | 仅文字 | `[搜索]` |
| `icon_only` | 仅图标 | `[🔍]` |

**占比模式 (`ratio_mode`)：**

| 模式 | 说明 |
|------|------|
| `sync` | 水平 = 垂直 = 同一值 |
| `hv` | 水平、垂直分别设置 |
| `h_only` | 仅水平（垂直 100%） |
| `v_only` | 仅垂直（水平 100%） |
| `auto` | 同 sync |

**返回值：** `StarButton` 控件实例（QWidget 子类）。

**可用信号**（connect 绑定）：

| 信号 | 参数 | 说明 |
|------|------|------|
| `clicked` | — | 点击时发射 |
| `pressed` | — | 按下时发射 |
| `released` | — | 释放时发射 |
| `toggled` | `bool` | checkable 模式下状态翻转 |

**可用方法：**

| 方法 | 说明 |
|------|------|
| `.setText(str)` / `.text()` | 文字读写 |
| `.setIcon(icon)` / `.icon()` | 图标读写 |
| `.setCheckable(bool)` | 设置可勾选 |
| `.setChecked(bool)` / `.isChecked()` | 勾选状态 |
| `.setEnabled(bool)` | 启用/禁用 |
| `.setFont(QFont)` | 字体设置 |
| `.setFixedSize(w, h)` | 固定尺寸 |

**使用示例：**

```python
def build_my_panel():
    panel = QWidget()
    layout = QVBoxLayout(panel)
    api = get_api()

    # 1. 基础按钮
    btn = api.create_button("搜索")
    btn.clicked.connect(lambda: print("搜索"))

    # 2. 主题色按钮（蓝色实底）
    btn_save = api.create_button(
        "保存一辩稿", icon="icon/save.svg",
        accent="#89b4fa", ratio_h=0.75, text_align="left",
    )
    layout.addWidget(btn_save)

    # 3. 可勾选按钮
    btn_toggle = api.create_button("启用功能", checkable=True)
    btn_toggle.toggled.connect(lambda chk: print(f"状态: {chk}"))
    layout.addWidget(btn_toggle)

    # 4. 仅图标导航按钮
    btn_nav = api.create_button(
        icon="icon/home.svg", layout_mode="icon_only",
        icon_size=28,
    )
    layout.addWidget(btn_nav)
    return panel
```

> **注意**：返回的控件 `parent=None`，需要手动添加到你的面板 layout 中。

### 4.18 监视钩子插入细则

> 本节定义在 StarDebate 代码中插入监视钩子的标准规范。适用于核心开发者、插件开发者和贡献者。遵循这些细则可确保监视数据完整、准确且不影响性能。

#### 4.17.1 五种监视类型的插入时机

##### 1. 变量监视 `[VAR]` — `log_variable_change()`

**触发条件**：全局变量或关键实例属性的值发生变化。

**插入位置**：
```python
# ✅ 正确：在变量实际赋值之后立即记录
def set_active_project(self, path: str):
    old = self._active_project
    self._active_project = path
    DebugMonitorManager.instance().log_variable_change(
        file_path=__file__,
        line_no=43,           # 赋值语句的行号
        var_name="_active_project",
        new_value=path,
    )

# ✅ 正确：使用 setter property 统一插入
class Config:
    @property
    def theme(self): return self._theme

    @theme.setter
    def theme(self, value):
        old = self._theme
        self._theme = value
        DebugMonitorManager.instance().log_variable_change(
            __file__, 67, "Config.theme",
            f"{old} → {value}"
        )
```

**插入准则**：
| 准则 | 说明 |
|------|------|
| **仅记录关键变量** | 不是所有变量都需要监视。聚焦于：配置项、状态机状态、辩论数据、插件开关 |
| **记录「变更」而非「访问」** | 仅在 setter/write 操作时记录，getter/read 操作不记录 |
| **截断长值** | `_format_value()` 自动截断超过 200 字符的值，无需手动处理 |
| **行号准确** | `line_no` 参数应指向实际赋值代码的行号，便于定位 |

**不应监视的变量**：
- 循环中的临时变量（`i`, `temp`, `data`）
- UI 控件引用（`self.btn_xxx`, `self.lbl_xxx`）
- 内部计数器（除非是业务关键计数器）

##### 2. 函数监视 `[FUNC]` — `log_function_call()`

**触发条件**：关键函数的执行完成（成功或失败）。

> **v4.4.0 插件函数自动监视**：框架在 `PluginInfo.load()` 执行 `exec_module()` 后，自动遍历插件模块的所有顶层 `def` 函数并安装计时包装器。开启 `function_watch` 后，日志自动包含 `[FUNC] 插件ID:函数名 → ✅/❌` 条目。**插件内函数无需手动插入监视代码**。以下手动插入规范仅适用于框架核心代码。

**核心代码的插入位置**：
```python
# ✅ 正确：在函数返回点（包括异常）记录
def load_debate_file(path: str) -> dict:
    start = time.time()
    try:
        data = _parse_json(path)
        elapsed = (time.time() - start) * 1000
        DebugMonitorManager.instance().log_function_call(
            module_name="debate_loader",
            func_name="load_debate_file",
            success=True,
            result=f"keys={list(data.keys())[:5]}",
            duration_ms=elapsed,
        )
        return data
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        DebugMonitorManager.instance().log_function_call(
            module_name="debate_loader",
            func_name="load_debate_file",
            success=False,
            error=str(e),
            duration_ms=elapsed,
        )
        raise

# ✅ 正确：使用装饰器简化重复代码
def monitored(module: str):
    """函数监视装饰器"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = (time.time() - start) * 1000
                DebugMonitorManager.instance().log_function_call(
                    module, func.__name__, True, str(result)[:150], "", elapsed
                )
                return result
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                DebugMonitorManager.instance().log_function_call(
                    module, func.__name__, False, None, str(e), elapsed
                )
                raise
        return wrapper
    return decorator

@monitored("ai_analysis")
def analyze_speech(text: str) -> dict:
    ...
```

**插入准则**：
| 准则 | 说明 |
|------|------|
| **覆盖正常和异常路径** | 成功和失败都要记录，便于统计成功率 |
| **耗时必填** | `duration_ms` 是诊断性能问题的关键指标 |
| **结果摘要** | `result` 应概括返回值（如 `"3条论点"`, `"keys=['a','b']"`），而非完整数据 |
| **module_name 一致性** | 同一模块内使用相同的 `module_name`，方便过滤 |

**适用最低耗时**：`options.function_min_duration_ms`（默认 0ms，即记录所有调用）。建议对非关键路径设置 10ms 以上的阈值。

##### 3. 插件监视 `[PLUGIN]` — `log_plugin_status()`

**触发条件**：插件生命周期的关键节点。

**插入位置**：
```python
# ✅ PluginManager 内部已自动插入（无需手动添加）：
#   - PluginInfo.load() 成功/失败
#   - PluginInfo.enable() 成功/失败
#   - PluginInfo.disable() 成功/失败

# ✅ 插件主动记录（通过 api.log_monitor）：
def on_enable():
    api = get_api()
    api.log_monitor("plugin_watch", "初始化完成，已连接外部服务")
    api.log_monitor("plugin_watch", f"加载配置: {load_config()}")

def process_batch(items: list):
    api = get_api()
    api.log_monitor("plugin_watch", f"开始批量处理 {len(items)} 条数据")
    for i, item in enumerate(items):
        if i % 50 == 0:  # 每 50 条记录一次进度
            api.log_monitor("plugin_watch", f"处理进度: {i}/{len(items)}")
    api.log_monitor("plugin_watch", f"批量处理完成")
```

**插入准则**：
| 准则 | 说明 |
|------|------|
| **记录关键里程碑** | 初始化、连接、批量操作开始/结束、错误恢复 |
| **避免高频日志** | 不在循环体内逐条记录（每 50-100 条记录一次进度） |
| **状态变更优先** | 状态切换（idle→running→done）比瞬时操作更有价值 |

**已自动监视的节点**（无需手写）：
| 节点 | 标签 | 触发方 |
|------|------|--------|
| 插件模块导入成功 | `✅ 插件名 加载成功` | PluginManager |
| 插件模块导入失败 | `❌ 插件名 加载失败` | PluginManager |
| 用户启用插件 | `▶ 插件名 已启用` | PluginManager |
| 用户禁用插件 | `⏸ 插件名 已禁用` | PluginManager |

##### 4. API 监视 `[API]` — `log_api_result()`

**触发条件**：HTTP API 请求完成（无论成功或失败）。

**插入位置**：
```python
# ✅ 推荐：使用项目内置的 monitored_api_post()
from workers.common import monitored_api_post

# 自动记录：端点、方法、状态码、耗时、请求/响应摘要
response = monitored_api_post(
    feature_name="ai_analysis",      # 功能标识
    endpoint="https://api.example.com/v1/chat",
    json_data={"model": "...", "messages": [...]},
    timeout=120,
)

# ✅ 手动插入（非 HTTP API 或特殊场景）：
DebugMonitorManager.instance().log_api_result(
    endpoint="wss://example.com/socket",  # WebSocket 端点
    method="WS",                          # 自定义方法标识
    status_code=200 if connected else 0,  # 连接状态映射为状态码
    duration_ms=elapsed,
    request_summary=f"subscribe {topic}",
    error="" if connected else str(err),
)
```

**插入准则**：
| 准则 | 说明 |
|------|------|
| **统一使用 monitored_api_post** | 比手动调用 `log_api_result()` 更标准，自动提取摘要 |
| **非 HTTP 协议需手动记录** | WebSocket、gRPC、TCP 等非 REST 协议需手动调用 |
| **敏感数据脱敏** | API Key、Token 绝不写入日志，响应中敏感字段需截断 |
| **超时也要记录** | 网络超时 `status_code=0` + `error="timeout"` |

**自动 API 监视覆盖范围**（已通过 `monitored_api_post()` 自动覆盖）：
| Worker | feature_name |
|--------|-------------|
| AI 分析 | `ai_analysis` |
| AI 写稿 | `speech_writer` |
| AI 扩写 | `ai_expand` |
| 框架生成 | `ai_framework` |
| 结构分析 | `structure_analysis` |
| 模拟质询 | `cross_examination` |
| 模拟接质 | `accept_examination` |
| 快速刷题 | `training_question` |
| 刷题评估 | `training_eval` |
| 立论训练 | `exercise_topic` |
| 驳论训练 | `exercise_opponent` |
| 训练评估 | `exercise_eval` |
| 插件 AI 调用 | `plugin:{plugin_id}` |

##### 5. AI 监视 `[AI]` — `log_ai_result()`

**触发条件**：AI 功能模块的业务层调用完成。

**插入位置**：
```python
# ✅ 在 AI Worker 的 finished 信号处理器中记录
def _on_analysis_finished(self, result: dict):
    mgr = DebugMonitorManager.instance()
    if result.get("success"):
        mgr.log_ai_result(
            feature_name="ai_analysis",
            success=True,
            duration_ms=result.get("duration_ms", 0),
            result_summary=f"生成 {len(result.get('arguments', []))} 条论点",
        )
    else:
        mgr.log_ai_result(
            feature_name="ai_analysis",
            success=False,
            duration_ms=result.get("duration_ms", 0),
            error=result.get("error", "未知错误"),
        )
```

**插入准则**：
| 准则 | 说明 |
|------|------|
| **记录业务层结果** | 在信号处理/回调中记录，而非在 API 层（API 层由 `[API]` 覆盖） |
| **结果摘要简明** | 如 `"3条论点"`, `"字数=150"`, `"分析完成"` |
| **错误信息完整** | 包含 AI 返回的原始错误，便于诊断模型问题 |
| **区分业务和 API** | `[API]` = HTTP 请求层面 | `[AI]` = 业务结果层面 |

**标准 feature_name 命名**：
| feature_name | 功能 |
|-------------|------|
| `ai_analysis` | AI 分析报告 |
| `speech_writer` | AI 写稿 |
| `ai_expand` | AI 扩写 |
| `ai_framework` | 辩论框架生成 |
| `structure_analysis` | 结构分析 |
| `cross_examination` | 模拟质询 |
| `accept_examination` | 模拟接质 |
| `training_question` | 快速刷题 |
| `training_eval` | 刷题评估 |
| `exercise_topic/opponent/eval` | 立论/驳论训练 |
| `plugin:{id}` | 插件 AI 调用 |

#### 4.17.2 性能与频率准则

| 准则 | 说明 | 示例 |
|------|------|------|
| **开关检查优先** | `is_monitor_enabled()` 在所有日志方法中首先执行，关闭时零开销 | `if not self.is_monitor_enabled("var"): return` |
| **避免循环内高频日志** | 单次循环内每秒不超过 10 条监视日志 | 循环内每 50-100 次迭代记录一次 |
| **字符串格式延迟** | 仅在监视开启时才构造消息字符串 | 不要在调用前做 `f"..."` 拼接（已在函数内部判断） |
| **异步不阻塞** | `put_nowait()` 非阻塞投递，不会拖慢主线程 | — |
| **降级不重试** | 队列不可用直写文件，不等待、不重试 | — |

#### 4.17.3 命名与格式规范

**module_name（函数监视）**：
```
✅ "speech_writer"      — 清晰的模块名
✅ "plugin_manager"     — 下划线分隔
✅ "training/quick_quiz" — 支持子路径
❌ "sw"                 — 过于简略
❌ "SpeechWriterManager" — 不必要的大驼峰
```

**日志消息格式**：
```
✅ "[API] ✓ POST /v1/chat → 200 | 1234ms"
✅ "[FUNC] loader:parse → ✅ 返回(12ms): {'keys': 3}"
✅ "[PLUGIN] ▶ my_plugin 已启用 | 配置: 3项"
✅ "[VAR] config.py:42 → theme = 'catppuccin_mocha'"
✅ "[AI] ✅ ai_analysis → 成功 | 2345ms | 生成 5 条论点"
```

#### 4.17.4 调试台中查看监视日志

1. 打开调试台：标题栏 **帮助 ▼** → 🔧 调试台
2. 标题栏「调试 ▼」→ ⚙ **调试模式设置**
3. 开启总开关 + 需要的监视项（5 项独立开关）
4. 日志区中带 `[VAR]` / `[FUNC]` / `[PLUGIN]` / `[API]` / `[AI]` 标签的条目即为监视日志
5. 工具栏下方显示蓝色监视指示条「🔍 监视中: ■变量 ■API ...」

> **快捷键**：调试台命令 `monitor:all` → 一键开启全部 5 项监视

---

### 4.19 起居注 (ActivityChronicle)

> 起居注是 StarDebate v2.6.0 新增的**自动活动日志系统**。它不修改任何现有代码，通过运行时 monkey-patch 自动记录软件中功能运行、插件加载/卸载、API 调用、AI 调用的成功与失败。标签：**`[CRON]`**（Chronicle Record，4 字符）。
>
> 完整说明详见 `docs/log/起居注说明.md`。

#### 4.18.1 对插件开发者意味着什么

**插件无需任何代码修改**。起居注在 StarDebate 启动时自动注入以下钩子：

| 自动记录项 | 触发时机 | 日志示例 |
|-----------|---------|---------|
| 插件加载 | `PluginInfo.enable()` | `[CRON] ▶ plugin·my_timer → ok` |
| 插件卸载 | `PluginInfo.disable()` | `[CRON] ▶ plugin·my_timer → disabled` |
| API 调用 | `monitored_api_post()` | `[CRON] ✓ api·speech_writer → ok (567ms)` |
| AI 调用 | `PluginSafeAPI.call_ai()` | `[CRON] ✅ ai·call_ai → ok (3456ms)` |

> **零改动**：以上四项全自动生效。`plugin_manager/__init__.py`、`api_helper.py`、`plugin_api.py` 源文件均未修改。

#### 4.18.2 插件主动使用起居注

除了自动注入，插件也可主动使用起居注追踪自定义操作：

**方式 A：通过 `api.log_monitor()` 间接触发**（无需修改）：

```python
def on_enable():
    api = get_api()
    # 插件加载时的 API 调用已自动记录，无需手动追踪
    result = api.call_ai([{"role": "user", "content": "ping"}])
    # → 自动: [CRON] ✅ ai·call_ai → ok (1234ms)
```

**方式 B：在自定义函数上使用装饰器**（需访问 LogClient）：

```python
# 适用于核心开发者（插件 API 暂不暴露 LogClient）
# 如需在插件中使用，可在 on_enable() 中通过以下方式获取：
def on_enable():
    api = get_api()
    mw = api.mw  # 主窗口引用
    log_client = mw._log_client  # LogClient 实例

    @log_client.track("feature", "my_custom_pipeline")
    def complex_pipeline():
        step1()
        step2()
        mw._log_client.error("步骤3失败")  # 触发 has_error

    complex_pipeline()
    # → [CRON] ❌ feature·my_custom_pipeline → failed (45ms): 步骤3失败
```

#### 4.18.3 原理简述

起居注通过拦截 `LogClient.error()` 和 `LogClient.warn()` 调用来自动判断操作是否成功：

```
操作开始 → begin("plugin", "my_plugin")
           ctx.has_error = False

操作执行 → ... 正常代码 ...
          如果期间调用 log_client.error("失败")
          或 log_client.warn("警告"):
            → ctx.has_error = True  ★

操作结束 → end(ctx, ms)
          has_error? → [CRON] ❌ plugin·my_plugin → failed
          否则       → [CRON] ▶ plugin·my_plugin → ok
```

**错误传播**：嵌套操作中子操作出错 → 所有父操作也被标记为失败。

#### 4.18.4 起居注 vs 监视钩子

| 维度 | 起居注 `[CRON]` | 监视钩子 `[VAR/FUNC/...]` |
|------|----------------|--------------------------|
| 目的 | 记录"做了什么、成功与否" | 记录"内部发生了什么" |
| 自动性 | 全自动（monkey-patch） | 需手动插入 + 调试台开启 |
| 输出 | 摘要：✅/❌ + 耗时 | 详情：值变化/调用栈/响应体 |
| 开关 | `config/chronicle_config.json` | 调试台「调试模式」 |

#### 4.18.5 配置

`config/chronicle_config.json`：

```json
{
    "enabled": true,
    "categories": {
        "feature": true,
        "plugin": true,
        "api": true,
        "ai": true
    },
    "min_duration_ms": 0
}
```

| 字段 | 说明 |
|------|------|
| `enabled` | 总开关。`false` 后所有追踪失效 |
| `categories.feature` | 功能运行追踪 |
| `categories.plugin` | 插件加载/卸载追踪 |
| `categories.api` | API 调用追踪 |
| `categories.ai` | AI 调用追踪 |
| `min_duration_ms` | 低于此耗时的操作不写入 |

---

### 4.20 自定义 SVG 图标

> **v2.9.0 新增**：插件可在本地 `icons/` 文件夹存放 SVG 文件，通过 API 按主题色动态渲染为图标。

#### 约定：`icons/` 文件夹

插件根目录下创建 `icons/` 文件夹，放置 SVG 模板文件。支持子目录组织：

```
plugins/my_plugin/
├── main.py
├── plugin.json
└── icons/                     ← 推荐目录名
    ├── refresh.svg             # 刷新图标
    ├── export.svg              # 导出图标
    └── toolbar/
        ├── edit.svg            # 编辑图标
        └── delete.svg          # 删除图标
```

> SVG 模板推荐**白色底色**（`fill="#FFFFFF"`），渲染器通过 `SourceIn` 叠加动态着色。

#### `api.get_plugin_dir()` → str

获取插件自身的文件夹路径。

```python
api = get_api()
print(api.get_plugin_dir())  # → "e:/StarDebate/plugins/my_plugin"
```

#### `api.icon_path(name)` → str

获取插件 `icons/` 下 SVG 文件的完整路径。自动检查文件存在性，支持子目录路径和省略 `.svg` 后缀。

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 文件名，如 `"refresh.svg"` 或 `"toolbar/edit"`（省略后缀） |

```python
path = api.icon_path("refresh.svg")       # 完整文件名
path = api.icon_path("toolbar/edit")       # 子目录 + 省略 .svg
if not path:
    print("SVG 文件不存在")
```

#### `api.list_icons()` → list[str]

列出插件 `icons/` 下所有 SVG 文件的相对路径。

```python
icons = api.list_icons()
# → ["export.svg", "refresh.svg", "toolbar/delete.svg", "toolbar/edit.svg"]
```

#### `api.render_icon(name, size=24, color=None)` → QPixmap

渲染插件本地单色 SVG 图标为 QPixmap。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | `str` | — | `icons/` 下的 SVG 文件名 |
| `size` | `int` | `24` | 图标边长（px） |
| `color` | `str\|None` | `None` | 主题色键名，`None` 使用主题 `svg_renderer.mono.color` |

```python
pix = api.render_icon("refresh.svg", 22)
pix_blue = api.render_icon("refresh.svg", 22, color="accent_blue")
```

#### `api.render_bicolor_icon(name, size=24, primary=None, accent=None)` → QPixmap

渲染插件本地双色 SVG 图标。需在 SVG 中通过 `data-color="primary"` / `data-color="accent"` 标记区域。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `primary` | `str\|None` | `None` | 主色色键，`None` 使用主题预设 |
| `accent` | `str\|None` | `None` | 辅色色键，`None` 使用主题预设 |

```python
pix = api.render_bicolor_icon("toolbar/edit.svg", 24,
                               primary="accent_purple", accent="text")
```

#### `api.create_icon_qicon(name, size=24, color=None, disabled_pct=0.4)` → QIcon

渲染插件 SVG 图标为 QIcon（自动生成 Normal + Disabled 双状态）。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `disabled_pct` | `float` | `0.4` | Disabled 状态透明度 |

```python
icon = api.create_icon_qicon("refresh.svg", 22)
btn = QPushButton(icon, "刷新")
btn.setEnabled(False)  # 自动显示半透明置灰状态
```

#### 完整示例

```python
import os
from PyQt5.QtWidgets import QPushButton, QVBoxLayout, QWidget
from PyQt5.QtGui import QIcon
from workers.plugin_manager import get_api

def on_enable():
    api = get_api()

    # 确保 icons/ 中的 SVG 图标可用
    icons = api.list_icons()
    print(f"已加载 {len(icons)} 个 SVG 图标: {', '.join(icons)}")

    # ── 1. 导航按钮：渲染单色图标 ──
    icon_pix = api.render_icon("toolbar/edit.svg", 22)
    api.register_nav_button(
        side="right", label="编辑器",
        icon=QIcon(icon_pix),
        tooltip="打开编辑器面板",
        callback=show_editor,
    )

    # ── 2. 注册面板，内含多个 SVG 按钮 ──
    api.register_panel(
        side="right", title="工具面板", emoji="🔧",
        tooltip="插件工具面板",
        create_widget=build_tool_panel,
    )

    # ── 3. 监听主题切换 ──
    api.on("theme_changed", lambda name: refresh_toolbar())

def on_disable():
    pass  # 管理器自动清理导航按钮和面板

def show_editor():
    api = get_api()
    api.update_status("编辑器已打开")
    api.toggle_panel("my_editor")

_refresh_btn = None
_export_btn = None

def build_tool_panel():
    global _refresh_btn, _export_btn
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setSpacing(8)

    # 刷新按钮（单色）
    _refresh_btn = QPushButton(" 刷新数据")
    _refresh_btn.setIcon(api.create_icon_qicon("refresh.svg", 18))

    # 导出按钮（双色 — 主色紫色 + 辅色正文色）
    export_pix = api.render_bicolor_icon("export.svg", 20,
                                          primary="accent_purple",
                                          accent="text")
    _export_btn = QPushButton(QIcon(export_pix), " 导出报告")

    layout.addWidget(_refresh_btn)
    layout.addWidget(_export_btn)
    layout.addStretch()
    return panel

def refresh_toolbar():
    """主题切换后重绘按钮图标"""
    from components.svg_renderer import SvgRenderer
    SvgRenderer.clear_cache()

    api = get_api()
    if _refresh_btn:
        _refresh_btn.setIcon(api.create_icon_qicon("refresh.svg", 18))
    if _export_btn:
        pix = api.render_bicolor_icon("export.svg", 20,
                                       primary="accent_purple",
                                       accent="text")
        _export_btn.setIcon(QIcon(pix))
```

---

### 4.21 资料池 API (v4.0.0 新增)

> **v4.0.0 新增**：资料池 (MaterialPool) 提供了统一的多格式素材管理、本地BM25快速搜索和AI语义精排能力。插件可通过以下API读写资料池、执行搜索和分析。

**安全说明**：
- 所有只读方法返回深拷贝，插件无法污染内部数据
- 所有操作方法返回 `{"success": bool, "error": str|None}`
- 路径操作有遍历攻击防护（`..` 检测）
- 全部方法 `try/except` 隔离，异常不传播到主程序

---

#### `api.search_pool(keyword, sources=None, limit=20) -> list[dict]`

在资料池中执行搜索（本地BM25 + 异步AI精排），返回统一格式的结果列表。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `keyword` | `str` | **必需** | 搜索关键词 |
| `sources` | `list` | `None` | 搜索源: `["data_pool","project","stardebate"]`，None=全部 |
| `limit` | `int` | `20` | 最大返回结果数 |

**返回**：每项包含 `score`（BM25得分）、`ai_score`（AI语义得分，None=未完成）、`title`、`file`、`source`、`match_count`、`summary`、`matched_paragraphs`、`meta` 等字段。

**示例**：
```python
results = api.search_pool("人工智能 辩论策略")
for r in results[:5]:
    print(f"{r['title']} | BM25={r['score']}, AI={r.get('ai_score','N/A')}")
```

---

#### `api.search_local(keyword, sources=None, limit=20) -> list[dict]`

仅执行本地BM25关键词搜索（不触发AI），速度比 `search_pool` 快10~100倍，适用于快速查找。

```python
fast_results = api.search_local("自由辩论", limit=10)
```

---

#### `api.get_search_history(limit=10) -> list[dict]`

获取当前会话的搜索历史。

```python
for h in api.get_search_history(5):
    print(f"[{h['time']}] {h['query']} → {h['count']}条")
```

---

#### `api.import_file(source_path) -> dict`

**🔒 写操作**：将外部文件导入资料池。支持 MD/PDF/DOCX/XLSX/CSV/TXT/JSON/HTML 格式。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `source_path` | `str` | **必需** | 源文件绝对路径 |

**返回**：`{"success": bool, "error": str|None, "file_info": {"name","type","size"}}`

```python
result = api.import_file("/path/to/reference.pdf")
if result["success"]:
    info = result["file_info"]
    print(f"已导入: {info['name']} ({info['size']} bytes)")
else:
    print(f"失败: {result['error']}")
```

---

#### `api.list_files(recursive=True) -> list[dict]`

列出资料池中所有文件。

```python
for f in api.list_files():
    print(f"{f['name']} ({f['type']}, {f['size']}B)")
```

---

#### `api.get_file_content(relative_path) -> str|None`

**⚠ 路径防护**：获取指定文件的纯文本内容（已解析，非原始二进制）。

```python
text = api.get_file_content("reference.md")
if text:
    print(f"内容: {text[:200]}...")
```

---

#### `api.delete_file(relative_path) -> dict`

**🔒 写操作**：从资料池删除文件。返回 `{"success": bool, "error": str|None}`。

```python
result = api.delete_file("old_data.csv")
```

---

#### `api.get_pool_size() -> dict`

获取资料池统计信息。

**返回**：`{"file_count": int, "total_size": int, "type_counts": dict, "indexed": bool}`

```python
stats = api.get_pool_size()
print(f"{stats['file_count']}个文件, 共{stats['total_size']}字节")
print(f"类型统计: {stats['type_counts']}")
```

---

#### `api.summarize_document(relative_path) -> dict`

**⏳ 异步AI操作**：对资料池中的文档进行AI摘要分析。

**返回**：`{"success": bool, "summary": str|None, "key_points": list, "keywords": list, "error": str|None}`

```python
summary = api.summarize_document("data_report.xlsx")
if summary["success"]:
    print(f"摘要: {summary['summary']}")
    print(f"关键点: {'; '.join(summary['key_points'])}")
```

---

#### `api.ai_search(pool_results) -> list[dict]`

**⏳ 异步AI操作**：对已有的本地搜索结果进行AI语义精排，更新 `ai_score` 和 `ai_summary` 字段。

```python
# 先用本地搜索
local = api.search_local("人工智能", limit=10)
# 对前5条AI精排
ranked = api.ai_search(local[:5])
for r in ranked:
    print(f"{r['title']} → AI评分: {r.get('ai_score')}")
```

---

#### `api.get_ai_analysis_status() -> dict`

获取当前AI分析任务状态。

**返回**：`{"is_running": bool, "progress": int(0-100), "queued": int, "completed": int, "error": str|None}`

---

#### `api.export_summary(results=None, format="md") -> dict`

**🔒 写操作**：将搜索结果导出为MD/TXT汇总文档。

```python
result = api.export_summary(format="md")
if result["success"]:
    print(f"已导出至: {result['path']}")
```

---

#### `api.export_to_stardebate(file_path, results=None) -> dict`

**🔒 写操作**：将搜索结果打包到已打开的 `.stardebate` 加密文件中。

```python
api.export_to_stardebate("debate_package.stardebate", ranked_results)
```

---

#### `api.rebuild_index() -> dict`

**🔒 写操作**：重建资料池的全文搜索索引。

**返回**：`{"success": bool, "file_count": int, "error": str|None}`

---

#### `api.get_index_status() -> dict`

获取索引状态：`{"ready": bool, "total_files": int, "indexed_files": int, ...}`

---

#### `api.pool_is_ready() -> bool`

检查资料池是否已就绪（索引已建立且包含文件）。**推荐插件先调用此方法再使用其他API。**

```python
if not api.pool_is_ready():
    api.rebuild_index()
```

---

#### `api.get_pool_info() -> dict`

获取资料池基本信息：`{"name", "path", "open", "file_count", "search_count", "has_ai"}`

---

#### `api.is_pool_open() -> bool`

资料池面板当前是否打开。

---

#### `api.get_supported_extensions() -> list[str]`

返回支持的文件扩展名：`[".md", ".txt", ".pdf", ".docx", ".xlsx", ".csv", ".json", ".html"]`

---

### 4.23 权限查询 API（v4.5.0 新增）

#### `api.get_permissions() -> list[str]`

获取当前插件声明的权限列表。

```python
perms = api.get_permissions()
if "ai_api" in perms:
    print("插件可以调用 AI 接口")
```

---

#### `api.get_all_permission_defs() -> dict`

获取所有可用权限定义（静态常量），返回 `{权限名: {"level": str, "description": str, "explain": str}}`。

```python
defs = api.get_all_permission_defs()
for name, info in defs.items():
    icon = "🔴" if info["level"] == "dangerous" else "🟢"
    print(f"{icon} {name}: {info['description']}")
```

---

### 完整使用示例

```python
from workers.plugin_manager import get_api
api = get_api()

def on_search_trigger():
    # 1. 确保资料池就绪
    if not api.pool_is_ready():
        api.rebuild_index()

    # 2. 快速本地搜索
    results = api.search_local("人工智能 辩论策略", limit=10)
    api.update_status(f"本地搜索完成: {len(results)}条")

    # 3. AI精排前3条
    ranked = api.ai_search(results[:3])
    for r in ranked:
        ai = r.get('ai_score', 'N/A')
        api.update_status(f"{r['title']} → AI评分: {ai}")

    # 4. 导出汇总
    if ranked:
        api.export_summary(ranked, format="md")
```

---

### 4.22 获取功能区大小 (v4.3.0 新增)

插件可通过 `api.get_panel_size()` 获取自己注册的功能面板的实时宽度和高度，
适用于响应式布局、动态调整 UI 等场景。

**方法签名**：

```python
size_info = api.get_panel_size(panel_title: str = None, panel_index: int = 0) -> dict | None
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `panel_title` | str \| None | None | 面板标题（注册时填写的 title），与 panel_index 二选一 |
| `panel_index` | int | 0 | 面板索引（当插件注册多个面板时），仅在 panel_title 为 None 时生效 |

**返回值**：

```python
{
    "width": int,         # 面板当前宽度（像素）
    "height": int,        # 面板当前高度（像素）
    "panel_title": str,   # 面板标题
    "visible": bool,      # 面板当前是否可见
    "is_created": bool,  # 面板是否已创建（widget 实例是否存在）
}
```

> 面板不存在时返回 `None`。面板已注册但尚未创建（未被用户打开过）时，
> `is_created` 为 `False`，`width` 为注册时的 `min_width`，`height` 为 0。

**使用示例**：

```python
from workers.plugin_manager import get_api

def on_enable():
    api = get_api()

    # 注册面板
    def build_panel():
        from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # 获取面板大小并动态调整字体
        info = api.get_panel_size()
        font_size = 10 if info and info['width'] < 300 else 12
        label = QLabel("欢迎使用我的插件")
        label.setStyleSheet(f"font-size: {font_size}pt;")
        layout.addWidget(label)
        return panel

    api.register_panel("right", "我的面板", "🔌", "我的插件功能区", build_panel)

# 在面板中使用（面板已创建后）
def on_some_action():
    api = get_api()
    info = api.get_panel_size(panel_title="我的面板")
    if info and info['is_created']:
        print(f"面板大小: {info['width']}x{info['height']}px")
        if info['width'] < 250:
            switch_to_compact_layout()
        else:
            switch_to_full_layout()
```

---

### 4.23 一辩稿词汇索引与来源绑定 (v4.7.0 新增)

> **v4.7.0 新增**：一辩稿自定义词汇索引升级为结构化数据，支持手动解释 + 来源绑定（资料池/便签），悬浮卡片 IDE 风格显示。

#### 4.23.1 数据格式

`custom_glossary` 从简单的 `{词: str}` 升级为：

```python
{
    "温室效应": {
        "explanation": "在辩论中，温室效应用来论证...",   # 手动补充解释
        "sources": [                                       # 绑定的来源列表
            {
                "type": "material",            # "material" 或 "note"
                "title": "气候变化报告.pdf",     # 来源标题
                "file_path": ".../data_pool/xxx.pdf",  # 资料路径（type=material时）
                "note_id": 3,                           # 便签 ID（type=note时）
                "excerpt": "温室效应是指大气保温效应..."  # 摘要片段
            }
        ]
    }
}
```

#### 4.23.2 绑定弹窗

`workers/speech_editor/bind_source_dialog.py` — `BindSourceDialog`：
- 用户在一辩稿右击选中文字 → 选择「🔗 绑定资料/便签作为来源」
- 弹窗内可搜索并勾选多个资料/便签，支持手动补充解释
- 支持多来源绑定（复选框）

#### 4.23.3 悬浮卡片

`workers/speech_editor/hover_card.py` — `HoverCard`：
- 鼠标悬停在已绑定索引词上 300ms 后弹出自定义卡片
- 固定宽度 400px，最大高度 900px
- 分区显示：手动解释 / 资料来源 / 便签来源
- 每个来源显示摘要，点击"打开"弹出独立浮动窗口查看内容
- 鼠标离开触发词和卡片后 500ms 自动隐藏

#### 4.23.4 高亮样式

- 索引词从黄色下划线改为**主题 accent 色 + 加粗**
- 有来源绑定的词在文本左前方通过 `paintEvent` 绘制 `has_material.svg` 小图标（主题色 + 55% 透明度）
- 图标不是文本字符，不干扰编辑

#### 4.23.5 相关文件

| 文件 | 说明 |
|------|------|
| `workers/speech_editor/hover_card.py` | 悬浮卡片组件 |
| `workers/speech_editor/bind_source_dialog.py` | 绑定弹窗组件 |
| `workers/speech_editor/speech_editor_widget.py` | SpeechEditor（paintEvent + 自定义 hover） |
| `workers/speech_editor/speech_editor_manager.py` | 管理器（Source binding, data migration） |
| `icon/index/has_material.svg` | 有来源绑定的词前小图标 |

### 4.24 启动安全加载 (v4.8.0 新增)

> **v4.8.0 新增**：启动安全加载机制，防止因单个功能模块加载失败导致整个软件无法使用。

#### 4.24.1 分级保护

| 级别 | 描述 | 失败行为 |
|------|------|----------|
| 🔴 核心功能 | AppConfig, NavBar, TopNav, ProjectExplorer, PluginManager, LogClient | 致命崩溃弹窗(`CrashPopup`) + 退出进程 |
| 🟡 非核心功能 | AI分析/质询/接质/AI写稿/AI扩写/辩论框架/便签/训练/素材池/赛程/.stardebate | 跳过加载 + 欢迎页错误卡片 + 警告对话框 |

#### 4.24.2 相关文件

| 文件 | 说明 |
|------|------|
| `components/timeout_progress_loader.py` | 通用超时进度条组件(TimeoutProgressLoader + MultiProgressLoader, 默认30s超时) |
| `components/error_card.py` | 错误卡片组件(ErrorCardWidget, 内嵌欢迎页欢迎语下方) |
| `style/themes/catppuccin_mocha/error_card.qss` | 错误卡片 QSS 样式 |
| `workers/crash_monitor/crash_monitor.py` | CrashPopup 支持 `startup_failures` 参数；新增 `show_startup_failure_dialog()` |

#### 4.24.3 错误卡片功能

- **显示位置**：欢迎页(`_build_page_empty`)原有欢迎语下方
- **整体进度条**：显示已完成/总任务数和已用时间
- **每项独立进度条**：模块名称右侧，显示倒计时(30s超时)
- **按钮**：查看日志(系统默认程序打开) / 全部重试(仅重试失败模块) / 忽略(隐藏卡片)
- **技术详情**：可折叠展开，显示完整 traceback
- **超时保护**：每项任务最长等待30秒，超时自动终止并标记失败
- **日志保留**：检测到加载错误后自动设置 `keep_normal_exit_log=true`

---

### 4.25 记忆系统与向量检索 API（v5.0.0 新增）

> **v5.0.0 新增**：DebateClaw 插件内置了 Markdown 主题分文件记忆 + 本地向量语义检索能力。插件可通过以下 API 读写长期记忆、索引文档和对话历史。

#### 概览

```
plugins/debate_claw/
├── MEMORY/
│   ├── topics/                    # Markdown 主题分文件
│   │   ├── quick_notes.md         # 快捷笔记
│   │   ├── user_preferences.md    # 用户偏好
│   │   └── debate_topics.md       # 辩论话题
│   ├── vector_store.db            # SQLite 向量索引库
│   └── memory_guide.md           # AI 使用指南
├── workers/
│   ├── memory_handler.py          # Markdown 读写 + 向量摘要接口
│   └── memory_vector/             # 向量模块
│       ├── embedding.py           # sentence-transformers 软依赖
│       ├── vector_store.py        # sqlite3 + numpy 向量存储
│       └── indexer.py             # 后台切片索引器
```

#### 记忆文件读写

```python
from workers.memory_handler import (
    read_memory_file,    # read_memory_file("user_preferences") -> str
    write_memory_file,   # write_memory_file("user_preferences", content)
    list_topic_files,    # list_topic_files() -> list[dict]
    delete_topic_file,   # delete_topic_file("topic_name") -> bool
)

# 读取
content = read_memory_file("user_preferences")
# 写入（append 追加 / overwrite 覆盖）
write_memory_file("quick_notes", "- **新笔记**: 内容", mode="append")
# 列出所有主题文件
for info in list_topic_files():
    print(info["name"], info["size"])
```

#### 向量语义检索

```python
from workers.memory_handler import search_summary

# 在全部记忆（Markdown 文件 + 对话历史 + 资料文档）中语义搜索
summary = search_summary("用户偏好", top_k=5)
# 返回格式化的 Markdown 摘要，包含来源类型和匹配度分数
```

#### 向量统计

```python
from workers.memory_handler import get_vector_stats

stats = get_vector_stats()
# {'total': 150, 'by_source_type': {'memory': 30, 'conversation': 80, 'document': 40}, 'with_embedding': 120}
```

#### 后台索引

```python
from PyQt5.QtCore import QThreadPool
from workers.memory_vector.indexer import IndexerWorker
from workers.memory_handler import _DB_PATH

# 索引对话历史
worker = IndexerWorker(
    db_path=_DB_PATH,
    conv_history=[{"role":"user","content":"..."}, ...],
)
QThreadPool.globalInstance().start(worker)

# 索引单个文档文件
from workers.memory_vector.indexer import index_document_file, VectorStore
store = VectorStore(_DB_PATH)
index_document_file("/path/to/file.md", store)

# 索引整个目录
from workers.memory_vector.indexer import index_document_directory
index_document_directory("/path/to/dir/", store)
```

#### Embedding 引擎状态

```python
from workers.memory_vector.embedding import is_available, get_embedding

if is_available():
    engine = get_embedding()
    vectors = engine.encode(["文本1", "文本2"])
else:
    # sentence_transformers 未安装，回退到关键词匹配
    pass
```

#### 项目上下文自动注入（v5.0.0 新增）

每次 AI 对话启动时，系统自动将当前项目路径、项目可读文件清单、资料池文件清单注入到 system prompt 中，**零权限、零工具调用、零 Token 额外开销**。

```python
# main.py 中的辅助函数
from main import _build_project_context, _READABLE_EXTS

# 手动构建
api = get_api()
context = _build_project_context(api)
# 返回类似：
# ## 当前项目
#
# 项目目录: `E:/Debates/xxx`
#
# 项目可读文件:
#   - `一辩稿.md` (12KB)
#   - `论点整理.txt` (3KB)
#
# 资料池文件:
#   - `数据统计.csv`
```

**支持的扩展名**（定义于 `_READABLE_EXTS`）：
`.md`, `.txt`, `.json`, `.csv`, `.yaml`, `.yml`, `.html`, `.htm`, `.py`, `.js`, `.ts`, `.xml`, `.log`

**AI 工具对应关系**：
| 注入信息 | AI 如何使用 |
|---------|------------|
| 项目路径 | 无操作（AI 自动知道相对路径根目录） |
| 文件清单 | AI 看到文件名后，用 `file_read("一辩稿.md")` 读取（low 风险自动批准） |
| 资料池清单 | AI 看到文件名后，用 `file_read("..pool..文件")` 或 `search(query)` 搜索 |

---

### 4.25 一辩稿导出预览 API (v6.3.0 新增)

> **v6.3.0 新增**：一辩稿编辑器新增「预览导出」功能，支持 HTML 实时预览 + .docx/.pdf 导出，可通过 Ribbon 工具栏调整字体、字号、对齐、首行缩进、行距、纸张大小和方向。

#### 4.25.1 打开预览导出弹窗

```python
# 通过 SpeechEditorManager 打开
from workers.speech_editor.export_preview_dialog import ExportPreviewDialog

mgr = api.get_speech_editor_manager()  # 假设 API 提供
mgr._on_open_export_preview()          # 打开弹窗
```

或在插件中直接使用：

```python
from workers.speech_editor.export_preview_dialog import ExportPreviewDialog

content = api.get_speech_content("pro")  # 获取一辩稿内容
dlg = ExportPreviewDialog(content, parent_widget)
dlg.exec_()
```

#### 4.25.2 编程式导出

```python
from workers.speech_editor.export_worker import (
    export_to_docx,
    export_to_pdf,
    generate_preview_html,
)

# 导出 .docx
export_to_docx(
    content="一辩稿正文文本...",
    filepath="output/speech.docx",
    font_name="宋体",
    font_size=12,
    align="两端对齐",
    indent_chars=2,
    line_spacing=1.5,
    page_size="A4",
    orientation="纵向",
)

# 导出 .pdf
export_to_pdf(content, "output/speech.pdf", ...)

# 生成 HTML 预览
html = generate_preview_html(content, font_name="宋体", font_size=12, ...)
```

#### 4.25.3 关键参数说明

| 参数 | 类型 | 默认值 | 可选值 |
|------|------|--------|--------|
| `font_name` | `str` | `"宋体"` | 宋体、黑体、楷体、仿宋、微软雅黑 |
| `font_size` | `int` | `12` | 10, 11, 12, 14, 16, 18, 20, 22, 24 |
| `align` | `str` | `"两端对齐"` | 左对齐、居中对齐、右对齐、两端对齐 |
| `indent_chars` | `int` | `2` | 0~4（首行缩进字符数） |
| `line_spacing` | `float` | `1.5` | 1.0, 1.25, 1.5, 1.75, 2.0 |
| `page_size` | `str` | `"A4"` | A4, A5, B5, Letter |
| `orientation` | `str` | `"纵向"` | 纵向, 横向 |

#### 4.25.4 新文件清单

| 文件 | 说明 |
|------|------|
| `workers/speech_editor/export_worker.py` | 导出工作器（docx/pdf 生成 + HTML 预览渲染） |
| `workers/speech_editor/export_preview_dialog.py` | 导出预览弹窗（TitleBar + Ribbon + QWebEngineView） |
| `style/qss_templates/export_preview.qss` | 弹窗 QSS 模板 |
| `icon/common/export.svg` | 导出功能 SVG 图标 |

#### 4.25.5 依赖

| 库 | 用途 | 安装 |
|----|------|------|
| `python-docx` | .docx 导出 | `pip install python-docx` |
| `reportlab` | .pdf 导出 | `pip install reportlab` |
| `PyQtWebEngine` | HTML 预览 | `pip install PyQtWebEngine` |

---

## 5. 事件钩子

插件可以监听 StarDebate 的关键事件，在事件发生时自动执行回调。

### 5.1 注册与取消

```python
from workers.plugin_manager import get_api

def on_debate_opened(data):
    api = get_api()
    api.update_status(f"检测到打开辩论: {data}")

def on_enable():
    api = get_api()
    # 注册监听
    api.on("debate_opened", on_debate_opened)

def on_disable():
    api = get_api()
    # 取消监听
    api.off("debate_opened", on_debate_opened)
```

### 5.2 可用事件

| 事件名 | 触发时机 | 回调参数 |
|--------|----------|----------|
| `debate_opened` | 用户打开一个辩论项目 | `data: dict` — 辩论基本信息 |
| `debate_created` | 用户创建新辩论 | `data: dict` — 新辩论信息 |
| `speech_saved` | 一辩稿保存 | `side: str` — "pro" 或 "con" |
| `analysis_complete` | AI 分析完成 | `side: str` — 分析的一方 |
| `app_closing` | 应用即将关闭 | 无参数 |

**示例：监听辩稿保存事件**：

```python
def on_speech_saved(side):
    api = get_api()
    text = api.get_speech_content(side)
    word_count = len(text.replace("\n", ""))
    api.show_notification(
        f"辩稿已保存 ({side})",
        f"共 {word_count} 字"
    )

def on_enable():
    api = get_api()
    api.on("speech_saved", on_speech_saved)
```

---

## 6. 插件配置

### 6.1 定义配置

在 `plugin.json` 的 `config` 字段中定义默认配置：

```json
{
    "name": "辩论计时器",
    "version": "1.0.0",
    "config": {
        "default_duration": 180,
        "warning_time": 30,
        "show_countdown": true,
        "sound_enabled": false,
        "title_template": "第 {n} 环节"
    }
}
```

支持的配置值类型：`bool`、`int`、`float`、`str`。

### 6.2 用户修改配置

用户在插件面板中点击 `设置` 按钮即可看到配置表单：

```
┌────────────────────────────────────┐
│  ⚙ 插件设置 - 辩论计时器           │
├────────────────────────────────────┤
│  基本信息：                        │
│  名称:     辩论计时器              │
│  版本:     v1.0.0                  │
│  作者:     张三                    │
├────────────────────────────────────┤
│  插件配置：                        │
│  default_duration: [180    ]  ▲▼   │
│  warning_time:     [30     ]  ▲▼   │
│  show_countdown:   [True   ▼]      │
│  sound_enabled:    [False  ▼]      │
│  title_template:   [第 {n} 环节]   │
├────────────────────────────────────┤
│       [恢复默认]    [取消] [保存]   │
└────────────────────────────────────┘
```

### 6.3 在代码中读取配置

配置暂不支持直接从 API 读取（因为插件管理器未直接暴露）。推荐方式：在 `on_enable()` 中从 `plugin.json` 自行读取：

```python
import json
import os

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PLUGIN_DIR, "plugin.json")

def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        return manifest.get("config", {})
    except Exception:
        return {}

def on_enable():
    config = load_config()
    duration = config.get("default_duration", 180)
    print(f"计时器默认时长: {duration} 秒")
```

---

## 7. 安全与限制

### 7.1 安全沙箱

StarDebate 的插件系统采用多层隔离，确保插件不会影响主体程序的稳定性：

| 隔离层 | 说明 |
|--------|------|
| **命名空间隔离** | 每个插件在独立的 `plugin_<id>` 模块中运行，互不干扰 |
| **API 沙箱** | 插件仅能通过 `PluginSafeAPI` 访问主程序，无法直接操作主窗口对象 |
| **异常捕获** | 每个插件调用点包裹 try/except，单个插件崩溃不影响其他插件和主程序 |
| **日志独立进程** | 日志系统运行在独立 `LogService` 进程中，主窗口崩溃不影响日志写入 |
| **代码文件保护** | 插件无法修改 `StarDebate_demo01.py` 等主体代码文件 |
| **API Key 保护** | `get_api_config()` 返回的 Key 自动屏蔽，只显示前 4 位 |
| **文件操作限制** | `read/write_file_in_project` 限定在当前项目目录内 |
| **权限声明系统** | 敏感 API 方法需要 `plugin.json` 中声明相应权限，否则运行时抛出 `PermissionError` |
| **导入安全检查** | 检测 `os.remove("/")`、`subprocess.call("rm -rf")` 等危险模式并拒绝 |

### 7.2 权限系统（v4.5.0 新增）

> 配套 `.stp` 插件包格式（`docs/stp_format.md`）。旧插件不声明权限仍然可以正常运行（全部允许）。

#### 7.2.1 权限声明

插件开发者在 `plugin.json` 的 `permissions` 数组中声明所需权限：

```json
{
    "plugin_id": "my_author.my_plugin",
    "permissions": ["file_read", "ai_api", "settings_read"]
}
```

#### 7.2.2 权限列表

| 权限 | 级别 | 说明 | 涉及 API 方法 |
|------|------|------|---------------|
| `file_read` | 安全 | 读取项目目录外的文件 | `read_file_in_project` |
| `file_write` | ⚠ 危险 | 写入/删除文件 | `write_file_in_project`, `import_file`, `delete_file`, `export_to_stardebate` |
| `network` | ⚠ 危险 | 发起网络请求 | 插件自行实现 HTTP 请求时 |
| `ai_api` | 安全 | 调用 AI 接口 | `call_ai`, `summarize_document`, `ai_search` |
| `settings_read` | 安全 | 读取全局配置 | `get_api_config` |
| `settings_write` | 中等 | 修改全局配置 | 待实现 |

#### 7.2.3 运行时行为

- 插件调用敏感 API 时自动检查 `permissions` 列表
- 缺少权限时抛出 `PermissionError`，错误信息指明缺失的权限
- 空权限列表（`"permissions": []` 或缺失该字段）视为旧插件，全部允许（向后兼容）
- 调试台开启 `api_watch` 监视时，每次权限检查都会记录日志

#### 7.2.4 API 自省

插件可通过以下方法检查自身权限：

```python
# 获取当前插件的权限列表
perms = api.get_permissions()  # ["file_read", "ai_api"]

# 获取所有可用权限定义
all_defs = api.get_all_permission_defs()
for perm, info in all_defs.items():
    print(f"{perm}: {info['level']} - {info['description']}")
```

### 7.2.5 DebateClaw AI 权限申请流程（v4.6 新增，v4.8 升级）

> **背景**：DebateClaw 插件支持 AI 在回复过程中动态申请权限（如读取文件），实现"中断-执行-继续"的交互模式。v4.8 版本升级为**混合模式**：优先使用 DeepSeek 原生 tools（Function Calling），降级到 `[PERM:...]` 标记。

#### 架构概览

```
用户发送消息
    ↓
构造 messages + tools 定义（6 类权限工具）
    ↓
调用 DeepSeek API（stream + tools）
    ↓
检测到 tool_calls？
 ├─ 是 → 解析全部 tool_calls → 并行弹出授权卡片（垂直堆叠）
 │           ↓
 │       等待全部卡片响应 → 执行已授权的 tool
 │           ↓
 │       将 tool 结果作为 role=tool 消息发回 API
 │           ↓
 │       AI 继续生成正文（流式输出）
 └─ 否 → 正常流式输出正文
            ↓
        扫描正文中的 [PERM:...] 标记（降级模式）
            ↓
        弹出授权卡片 → 执行 → 重新调用 AI
```

#### 可用权限（6 类）

| 权限标签 | 风险等级 | 说明 | 示例场景 |
|---------|----------|------|---------|
| `file_read` | 低 | 读取项目文件、资料池、框架文件 | "让我看看你的一辩稿…" |
| `file_write` | 中 | 写入/修改文件（支持新建或覆盖） | "需要保存这个论点分析吗？" |
| `file_list` | 低 | 列出目录中的文件和子目录 | "看看项目里有哪些文件…" |
| `search` | 中 | 搜索资料池或项目文件关键词 | "搜索一下关于气候变化的证据…" |
| `network` | 高 | 联网搜索或抓取 URL（默认关闭） | "我帮你搜索一下最新数据…" |
| `execute` | 高 | 执行 Python 代码（沙箱限制） | "用 matplotlib 画个统计图…" |

#### 方式 1：tools 调用（推荐）

DeepSeek 原生 Function Calling 支持：

```python
# ai_worker.py 中的 TOOLS_DEFINITION 示例
{
    "type": "function",
    "function": {
        "name": "file_read",
        "description": "读取指定路径的文件内容...",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }
    }
}
```

**多 tool 并行**：
- AI 一次可调用多个 tool（如同时 `file_read` + `search`）
- 所有授权卡片**垂直堆叠**显示
- 等**全部卡片有响应**后再统一处理
- 拒绝的 tool 返回"用户拒绝"给 AI

**结果注入格式**（严格 OpenAI 格式）：
```python
{"role": "assistant", "content": None,
 "tool_calls": [{"id": "call_xxx", ...}]}
{"role": "tool", "tool_call_id": "call_xxx",
 "content": "执行结果文本"}
```

#### 方式 2：[PERM:...] 标记（降级）

AI 模型通过在输出流中插入标记来请求权限：

```
[PERM:file_read C:\Users\doc\debate.txt]    # 读取文件
[PERM:file_write /path/to/output.md]         # 写入文件
[PERM:file_list ./data]                     # 列出目录
[PERM:search 气候变化]                      # 搜索关键词
[PERM:network https://example.com]          # 抓取 URL
[PERM:execute]                             # 执行代码
```

#### 分级权限策略

| 风险等级 | 行为 |
|----------|------|
| 🟢 **低风险** (file_read, file_list) | 自动批准或快速确认 |
| 🟡 **中风险** (file_write, search) | 每次询问，可记住用户选择 |
| 🔴 **高风险** (network, execute) | 每次询问 + 严重警告 + **禁用"总是允许"** |

#### 关键组件

| 文件 | 说明 | v4.8 改动 |
|------|------|-----------|
| `workers/ai_worker.py` | AIWorker 类，SSE 流式调用 + tools 解析 | **重构**：新增 `tool_calls_received` 信号、tools 多轮逻辑 |
| `workers/permission_handler.py` | 权限扫描、执行、UI 卡片 | **扩充**：6 类权限 + 风险等级样式 + network 禁用 always |
| `workers/search_worker.py` | SerpAPI/Bing 搜索实现 | **新建** |
| `workers/execute_sandbox.py` | 代码安全执行沙箱 | **新建** |
| `config/ai_config.json` | 配置文件 | **新增**：search_provider, search_api_key, network_enabled |

#### file_write 内容安全处理（v4.8.0 新增）

`file_write` 工具在执行写入时自动进行以下安全处理：

**Markdown 剥离（一辩稿专用）**：
- 检测写入路径是否为 `speech_pro.json` / `speech_con.json`
- 自动剥离 `#` `**` `` ` `` `>` `-` `---` 等 Markdown 符号，保留纯文本内容
- 将纯文本包装为完整 JSON 格式 `{"content": "...", "custom_glossary": {...}, "structure_tree": [...], "keywords": [...]}`
- 尽量保留原文件中的自定义词汇索引、结构树和关键词数据

**通用 JSON 包装**：
- 如果写入目标为其他 `.json` 文件且内容不是合法 JSON，自动包装为 `{"content": "..."}` 防止下游 `json.load()` 崩溃

**AI 指导**：
- `ai_worker.py` 中 `TOOLS_DEFINITION` 的 `file_write` description 已提示 AI：写入一辩稿时 content 使用纯文本
- `MEMORY/permissions_guide.md` 已加入详细说明

#### 自动审批系统（v5.0.0 新增）

`file_read` / `file_list` 等低风险权限在满足以下条件时**自动执行，跳过用户确认**：
1. 权限风险等级为 `low`
2. 设置中"自动审批"开关已启用（默认启用）
3. 操作路径不在黑名单中

**黑名单匹配规则**（支持通配符 `*`）：
| 模式 | 匹配示例 |
|------|---------|
| `secret.txt` | 任何目录下名为 `secret.txt` 的文件 |
| `*.key` | 任何 `.key` 结尾的文件 |
| `config/*` | `config/` 目录下的所有文件 |
| `密码*.*` | 以"密码"开头的文件 |

**运行日志**：自动审批的操作记录在会话级日志中，可在设置面板查看，关闭插件后清空。

**UI 表现**：自动审批时聊天区底部显示绿色瞬态提示 `✅ 已自动批准: 读取文件 xxx`，1.5 秒后自动消失。

```python
from plugins.debate_claw.workers.permission_handler import (
    AutoApproveConfig,     # dataclass: enabled(bool) + blacklist(list[str])
    get_auto_config,       # -> AutoApproveConfig
    set_auto_config,       # set_auto_config(cfg) 保存配置
    check_auto_approve,    # check_auto_approve("file_read", "path") -> bool
    check_already,         # 检查是否已授权
    execute_permission,    # 执行权限操作（返回结果文本）
    get_perm_display_label,# 获取显示用标签
    get_risk_level,        # 获取权限风险等级 (v4.8 新增)
    check_network_enabled, # 检查网络权限是否启用 (v4.8 新增)
)

from plugins.debate_claw.workers.ai_worker import AIWorker

# AIWorker 信号：
worker.chunk_received.connect(callback)          # 文本片段
worker.perm_requested.connect(callback)          # [PERM:] 标记模式：权限请求 {type: path}
worker.perm_interrupted.connect(callback)        # [PERM:] 标记模式：因权限中断 (text_before, perms)
worker.tool_calls_received.connect(callback)     # ★ tools 模式：完整 tool_calls 列表 [(id,name,args)]
worker.finished.connect(callback)                # 正常完成
worker.error.connect(callback)                   # 错误

# tools 模式接口：
worker.set_tool_results(results)   # 注入 tool 执行结果
worker.get_pending_tool_calls()   # 获取待处理的 tool_calls
worker.get_messages_snapshot()    # 获取当前消息快照
```

#### AI 回复中断功能（v5.x 新增）

> **背景**：AI 流式回复可能耗时较长（尤其涉及工具调用时），用户需要能够主动中断正在进行的 AI 回复。

**交互方式：发送按钮变身法**

| 状态 | 按钮文字 | 颜色 | 行为 |
|------|---------|------|------|
| AI 空闲中 | `发送` | 蓝色 `#2E6DDE` | 点击 → 发送消息 |
| AI 回复中 | `■ 停止` | 红色 `#E53935` | 点击 → 中断 AI |

**中断处理流程：**

```
用户点击「停止」
    ↓
state["streaming"] = False          ← 停止流式状态
    ↓
_stop_thinking_indicator()           ← 隐藏思考指示器
    ↓
_cleanup_worker()                    ← 停止 AIWorker + 关闭全部授权卡片
    ↓
_flush_stream()                      ← 刷新已有内容到气泡 UI
    ↓
气泡底部追加 "── ⏹ 已中断 ──"       ← 永久标记（灰色小字）
    ↓
_add_system_notification("⏹ 已中断") ← 输入框上方提示（3秒消失）
    ↓
_restore_send_btn()                  ← 恢复按钮为「发送」样式
    ↓
清理流式状态变量                     ← _streaming_segments/text/label 清空
```

**关键函数：**

```python
# 中断入口
def _on_interrupt():
    """用户点击停止时的核心逻辑"""

# 按钮恢复辅助函数
def _restore_send_btn():
    """将停止按钮恢复为发送按钮（蓝色）"""

# 动态路由（替代固定 connect）
def _on_btn_click():
    if _state.get("streaming"):
        _on_interrupt()     # 正在回复 → 中断
    else:
        _on_send()          # 空闲 → 发送
```

**自动恢复时机：**

| 场景 | 恢复动作 |
|------|---------|
| AI 正常完成 (`_on_ai_finished`) | `_restore_send_btn()` |
| AI 出错 (`_on_stream_error`) | `_restore_send_btn()` |
| 用户手动中断 (`_on_interrupt`) | `_restore_send_btn()` |

**已生成内容保留策略：**
- 有内容时：气泡保留已有文本 + 底部「已中断」标记
- 无内容时（仍在思考）：空气泡保留 + 「已中断」标记
- 授权卡片：中断时全部撤销关闭

#### 开发注意事项

- **混合模式**：优先使用 tools，不支持时自动降级到 [PERM:] 标记
- **并行授权**：多个 tool call 同时弹出卡片，等全部响应后才继续
- **多线程安全**：AI 调用在 QThread 中执行，UI 更新必须通过信号槽回到主线程
- **超时机制**：权限卡片 15 秒无响应自动拒绝
- **对话历史管理**：tool 结果以 `role=tool` 注入；[PERM:] 结果以 system message 注入
- **高危限制**：network 权限默认关闭且禁用"总是"；execute 使用沙箱限制库
- **弹窗统一**：权限卡片的「总是」确认弹窗已从 `QMessageBox` 改为调用 `api.show_confirm()`，确保跟随主界面主题样式。插件内如需弹窗应优先使用 API 方法而非直接创建 Qt 对话框（见 8.8 节对话框设计）
- **中断一致性**：`_on_interrupt()` / `_on_ai_finished()` / `_on_stream_error()` 三条结束路径均需调用 `_restore_send_btn()` 确保按钮状态正确恢复

### 7.2.6 DebateClaw Diff 修改卡片格式（v5.0 新增，v5.1 段落级增强）

> **背景**：DebateClaw 插件支持 AI 在回复中嵌入段落修改建议，以类似代码 diff 的可视化卡片展示，用户可直接接受或拒绝。
> **v5.1 增强**：支持段落级精确替换 — AI 可通过 `段落="xxx"` 元数据定位到一辩稿的具体结构化段落，用户接受后自动更新对应段落数据并重建全文。

#### 格式规范

AI 在 Markdown 回复中以 `[DIFF]...[/DIFF]` 标记块输出修改建议：

```
[DIFF:标题="段落优化" +2 -1 段落="opening"]
- 原文中将被删除的句子
+ 替换后的新句子
  未修改的上下文行
[/DIFF]
```

**元数据字段：**

| 字段 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `title` | 否 | 修改建议的标题 | `"段落优化"` |
| `+N` | 否 | 新增行数统计 | `+2` |
| `-M` | 否 | 删除行数统计 | `-1` |
| `段落` | 否 | 目标段落 ID（v5.1 新增） | `"opening"` |

**行前缀规则：**

| 前缀 | 含义 | 视觉效果 |
|------|------|----------|
| `- ` (减号+空格) | 被删除的原文行 | 红色半透明背景 |
| `+ ` (加号+空格) | 新增的修改后行 | 绿色半透明背景 |
| ` ` (空格) 或无前缀 | 上下文行（不变） | 无背景变化 |

#### 段落 ID 系统（v5.1）

一辩稿 JSON 中新增 `paragraphs` 字段，每个段落有唯一 id，AI 通过此 id 定位修改目标：

```json
{
  "content": "完整一辩稿正文...",
  "paragraphs": [
    {
      "id": "opening",
      "slug": "opening",
      "node_name": "开场引入",
      "texts": ["主席、评委、各位观众...", "今天我方的立场是..."]
    },
    {
      "id": "definition",
      "slug": "definition",
      "node_name": "定义阐释",
      "texts": ["首先从定义上看..."]
    }
  ]
}
```

**ID 来源规则：**
- 有结构树时 → 使用树节点的 `slug` 字段（如 `opening`, `definition`）
- 无结构树时 → 自动编号 `para_1`, `para_2`...
- 用户可通过结构树右键菜单「编辑段落ID (slug)」自定义

#### 渲染行为

- Diff 卡片内嵌于 AI 气泡内部，与 `_AutoTB`(文本)、`_TableCard`(表格) 并列
- 每张卡片包含元数据头（含段落标签）、可滚动内容区、底部操作按钮
- **操作按钮：**
  - **接受** — 用修改后的版本替换原文；若有关联段落 ID 则同步更新一辩稿段落数据并重建 content，卡片变绿色"已应用"
  - **拒绝** — 保留原文，卡片变灰色"已忽略"
  - **全部接受** — 当前气泡内所有 Diff 卡片一次性全部接受
- **三态切换**：已接受/已拒绝状态均可撤销，重新切回待定

#### 解析 API

```python
from plugins.debate_claw.workers.diff_widget import parse_diff_blocks, strip_diff_blocks, DiffCard

# 从文本解析所有 DIFF 块
blocks = parse_diff_blocks(ai_reply_text)
# blocks = [
#   {"title": "段落优化", "additions": 2, "deletions": 1,
#    "paragraph": "opening",        # ← v5.1: 段落 ID
#    "lines": [(_LineType.DELETED, "..."), (_LineType.ADDED, "..."), ...]},
# ]

# 移除所有 DIFF 标记，获取纯文本版本
clean_text = strip_diff_blocks(ai_reply_text)

# 创建 DiffCard 组件
card = DiffCard(
    card_id="diff_001",
    title=blocks[0]["title"],
    additions=blocks[0]["additions"],
    deletions=blocks[0]["deletions"],
    lines=blocks[0]["lines"],
    colors=_detect_html_colors(),  # 使用主题色
    paragraph_id=blocks[0].get("paragraph"),  # v5.1: 段落 ID
)
```

#### 文件结构

| 文件 | 说明 |
|------|------|
| `plugins/debate_claw/workers/diff_widget.py` | DiffCard 组件实现 + 解析函数（支持 `段落` 字段） |
| `plugins/debate_claw/theme/debate_claw.qss` | 深色主题 DiffCard QSS |
| `plugins/debate_claw/theme/debate_claw_light.qss` | 浅色主题 DiffCard QSS |
| `workers/speech_editor/paragraph_manager.py` | 段落切分/重建算法（v5.1 新增） |
| `workers/speech_editor/speech_editor_manager.py` | 一辩稿编辑器（集成 paragraphs 保存/加载） |
| `workers/structure/structure_manager.py` | 结构树管理器（节点新增 `slug` 字段 + 右键编辑） |

#### AI System Prompt 指导

如需让 AI 输出 DIFF 块，可在 system prompt 中加入（DebateClaw 已内置自动注入）：

```
## 一辩稿段落结构

当前一辩稿已按以下段落结构化（共 3 段）：
  [1] id="opening" (开场引入, 45字) — 预览: 主席、评委、各位观众...
  [2] id="definition" (定义阐释, 120字) — 预览: 首先，从定义层面...
  [3] id="closing" (总结陈词, 80字) — 预览: 综上所述...

**修改建议格式（当需要建议用户修改一辩稿时使用）**：
你可以用以下格式输出段落级修改建议：

[DIFF:标题="描述" +新增行数 -删除行数 段落="段落ID"]
- 原文中将被替换的句子或段落
+ 替换后的新内容
[/DIFF]

其中「段落ID」必须使用上方列出的 id 值（如 opening、definition 等），这样用户接受后可以精确更新到对应段落。

例如：
[DIFF:标题="论据强化" +3 -1 段落="argument_structure"]
- 这个证据来源于2018年的研究
+ 这个证据距今已有8年，在快速发展的领域中可能已不适用
+ 更新的研究显示...
+ 建议引用2024年后的数据来源以增强论证时效性
  这段论点整体逻辑清晰，但时效性需要加强。
[/DIFF]
```

#### 安全写入模式（v5.1 新增）

> **背景**：某些场景下用户希望 AI 仅输出修改建议，不能直接写入文件，以便逐条审核。

**行为变化：**

| 项目 | 关闭模式 | 安全模式 |
|------|----------|----------|
| `file_write` tool | AI 可正常调用 | 从 tools 定义中移除，AI 不可用 |
| AI 回复方式 | 可选 file_write 或 [DIFF] | 只能用 [DIFF] 格式 |
| 用户操作 | 权限卡片确认后执行 | 无需确认，AI 写不了文件 |
| Diff 卡片接受 | 更新编辑器内容 | 更新编辑器 + 无段落 ID 时警告 |

**触发方式（双重）：**

1. **标题栏按钮**：DebateClaw 聊天面板标题栏 `🔒`/`🔓` 图标，点击快速切换
2. **设置页开关**：⚙ 设置 → 插件页面 → DebateClaw → 安全写入模式，可设默认值

**拦截机制：**

- **Tool 层**：`AIWorker` 构建 payload 时若 `_safe_write_mode=True`，从 `tools` 数组中移除 `file_write`
- **System prompt 层**：注入 `"🔒 安全写入模式已开启 —— 你只能使用 [DIFF] 格式，不可调用 file_write 工具"`
- **运行时拦截层**：`_handle_tool_calls` 中检测到 `file_write` 时返回错误结果，不弹出授权卡片

**文件变化：**

| 文件 | 改动 |
|------|------|
| `plugins/debate_claw/workers/ai_worker.py` | `__init__` 新增 `_safe_write_mode` 属性；payload 构建时动态过滤 file_write |
| `plugins/debate_claw/main.py` | 新增 `_safe_write_mode` 闭包变量 + `_swm_btn` 标题栏按钮 + `_toggle_safe_write_mode()` + 拦截逻辑 + 系统通知 |
| `plugins/debate_claw/workers/diff_widget.py` | DiffCard 新增 `no_paragraph_warning` 信号 |
| `plugins/debate_claw/settings.py` | 新增安全写入模式卡片 + `get_safe_write_mode_default()` |
| `docs/plugin_dev_guide.md` | 本节 |

---

### 7.3 插件能做什么

- 读取辩论数据、框架、便签等所有公开数据
- 在项目目录内读写文件（如导出报告）
- 更新状态栏消息
- 弹出通知对话框
- 监听辩论事件并响应
- 使用 Python 生态中任意安全库（如数据分析、文本处理等）

### 7.4 插件不能做什么

- 修改主体代码文件
- 获取完整的 API Key
- 删除项目目录之外的文件
- 直接访问主窗口的私有方法或属性
- 安装系统级别的软件或修改注册表
- 操作其他插件的文件或数据

### 7.4 最佳实践

1. **最小权限原则**：只申请你的插件真正需要的权限
2. **优雅降级**：API 不可用时应给出友好提示，而非崩溃
3. **资源清理**：在 `on_disable()` 中释放定时器、文件句柄、网络连接等资源
4. **错误处理**：在你的函数中使用 try/except 包裹关键操作
5. **代码审查**：分发插件时建议附带源代码，方便用户审查

---

## 8. 插件UI设计规范 

> **重要**：插件UI必须遵循本规范，以确保与 StarDebate 主体界面风格一致、支持三主题（Mocha/Latte/Macchiato）自动切换，并保证不同插件间的视觉统一性。

### 8.1 设计原则

| 原则 | 说明 |
|------|------|
| **主题驱动** | 所有颜色通过 QSS 管理，代码中**禁止**硬编码颜色 |
| **样式与结构分离** | 样式写在 QSS 文件中，Python 代码仅负责布局逻辑 |
| **objectName 优先** | 通过 `setObjectName()` 引用系统预定义样式，而非内联 `setStyleSheet()` |
| **一致性优先** | 使用系统 objectName 获得与主体一致的视觉效果 |
| **最小字体 10pt** | 所有控件文字大小不低于 10pt（项目规则） |
| **自适应布局** | 注册功能面板时，面板内控件必须在页面宽度变动时动态智能调整高宽（禁止固定宽高死板排列） |

### 8.2 色彩体系

StarDebate 使用 Catppuccin 配色方案，三套主题共享同一色彩命名体系：

#### 8.2.1 主题色板

| 色键 | Mocha (深色) | Macchiato (中深) | Latte (浅色) | 语义用途 |
|------|:---------:|:-----------:|:--------:|----------|
| `base` | `#1e1e2e` | `#24273a` | `#eff1f5` | 页面/窗口背景 |
| `surface` | `#181825` | `#1e2030` | `#e6e9ef` | 卡片/面板背景 |
| `overlay` | `#313244` | `#363a4f` | `#ccd0da` | 按钮/分隔/hover |
| `text` | `#cdd6f4` | `#cad3f5` | `#4c4f69` | 正文文字 |
| `subtext` | `#a6adc8` | `#b8c0e0` | `#6c6f85` | 辅助文字/标签 |
| `muted` | `#6c7086` | `#a5adcb` | `#9ca0b0` | 禁用/占位/单位 |

#### 8.2.2 语义色彩

| 语义色 | Mocha | 用途 |
|--------|--------|------|
| `accent_purple` | `#cba6f7` | 标题、选中高亮、主色调 |
| `accent_green` | `#a6e3a1` | 成功/确认/开始 |
| `accent_yellow` | `#f9e2af` | 警告/暂停/中间态 |
| `accent_red` | `#f38ba8` | 错误/停止/危险操作 |
| `accent_blue` | `#89b4fa` | 信息/链接 |
| `accent_pink` | `#f5c2e7` | 辅助强调 |

#### 8.2.3 正确做法 vs 错误做法

```python
# ❌ 错误：硬编码颜色
label.setStyleSheet("color: #cba6f7; background-color: #1e1e2e;")

# ✅ 正确：使用 objectName 引用系统QSS
label.setObjectName("pluginPanelTitle")

# ✅ 正确：必须内联时，使用主题颜色变量（从 theme.json 读取）
from pathlib import Path
import json
theme_dir = Path(__file__).parent.parent.parent / "style" / "themes" / "catppuccin_mocha"
with open(theme_dir / "theme.json") as f:
    colors = json.load(f)["colors"]
label.setStyleSheet(f"color: {colors['accent_purple']};")
```

### 8.3 字体规范

系统默认字体为 **HarmonyOS Sans SC**（已在 `StarDebate.py` 中通过 `QFontDatabase.addApplicationFont()` 注册 Regular / Medium / Bold / Light / Semibold / Black 六个字重），QSS 中无需额外声明 `font-family` 即可使用。所有字号推荐使用 `pt` 单位，以保持不同 DPI 下的显示一致性。

| 用途 | 字体族 | 字号 | 字重 | objectName |
|------|--------|:----:|------|------------|
| 页面主标题 | HarmonyOS Sans SC | 18px (13.5pt) | Semibold (600) | `pluginPanelTitle` |
| 区域标题 | HarmonyOS Sans SC | 12pt (16px) | Semibold (600) | `pluginSectionTitle` |
| 卡片标题 | HarmonyOS Sans SC | 11pt (15px) | Semibold (600) | `pluginCardTitle` |
| 正文内容 | HarmonyOS Sans SC | 11pt (15px) | Regular (400) | `pluginLabel` |
| 辅助文字/标签 | HarmonyOS Sans SC | 11pt (15px) | Regular (400) | `pluginSubText` |
| 提示/单位文字 | HarmonyOS Sans SC | 10pt (13px) | Regular (400) | `pluginHintText` |
| 按钮文字 | HarmonyOS Sans SC | 11pt (15px) | Medium/Semibold (500–600) | 系统 btn 系列 |
| 计时数字 | Consolas | 视场景 | Regular | — |

> **注意**：代码中不应直接调用 `setFont()`，字体应在 QSS 中通过 objectName 控制。系统已全局注册 `HarmonyOS Sans SC`，插件 QSS 中直接书写 `font-size` 即可生效。

### 8.4 间距与圆角

#### 8.4.1 标准间距

| 场景 | 值 | 说明 |
|------|:--:|------|
| 面板内容内边距 | 16px | `layout.setContentsMargins(16, 16, 16, 16)` |
| 卡片内边距 | 12-20px | 水平 ≥ 16px，垂直 ≥ 12px |
| 布局控件间距 | 8-16px | `layout.setSpacing(12)` |
| 按钮内边距 | 8px 18px | 确保文字完全显示 |
| 输入框高度 | 30-34px | `setMinimumHeight(32)` |

#### 8.4.2 标准圆角

| 控件 | 圆角 |
|------|:----:|
| 面板/页面容器 | 8px |
| 卡片 (QFrame) | 8-12px |
| 按钮 (QPushButton) | 6-8px |
| 输入框 (QLineEdit) | 6-8px |
| 下拉框 (QComboBox) | 6px |

#### 8.4.3 面板最小宽度

| 面板位置 | 最小宽度 |
|----------|:--------:|
| 右侧面板 (side="right") | 280px |
| 左侧面板 (side="left") | 240px |
| 中心面板 (side="center") | 480px |
| 弹窗 (QDialog) | 380-480px |

### 8.5 控件 objectName 标准化

#### 8.5.1 系统预定义 objectName（首选）

以下 objectName 由系统 QSS 预定义，可直接使用并获得主题自适应：

| objectName | 适用控件 | 定义位置 | 说明 |
|------------|----------|----------|------|
| `pluginPanelTitle` | QLabel | plugins.qss | 面板主标题（18px Bold 紫色） |
| `pluginSectionTitle` | QLabel | plugins.qss | 区域标题（14px Bold） |
| `pluginCardTitle` | QLabel | plugins.qss | 卡片标题（12px Bold） |
| `pluginSubText` | QLabel | plugins.qss | 辅助文字（11px subtext色） |
| `pluginHintText` | QLabel | plugins.qss | 提示文字（10px muted色） |
| `pluginCard` | QFrame | plugins.qss | 内容卡片（surface背景+圆角） |
| `pluginInput` | QLineEdit | plugins.qss | 文本输入框 |
| `pluginCombo` | QComboBox | plugins.qss | 下拉选择框 |
| `pluginSpin` | QSpinBox | plugins.qss | 数字输入框 |
| `pluginPrimaryBtn` | QPushButton | plugins.qss | 主操作按钮（紫色高亮） |
| `pluginSecondaryBtn` | QPushButton | plugins.qss | 次要操作按钮 |
| `pluginDangerBtn` | QPushButton | plugins.qss | 危险操作按钮（红色） |
| `pluginScrollArea` | QScrollArea | plugins.qss | 滚动区域（无边框透明） |
| `pluginSeparator` | QFrame | plugins.qss | 水平分隔线 |

#### 8.5.2 插件自定义 objectName 命名规则

当系统 objectName 无法满足需求时，插件自定义 objectName 必须遵循以下命名前缀：

```
plugin_{插件ID}_{元素名}

示例：
  plugin_timer_phaseCard      → 计时器插件的阶段卡片
  plugin_timer_timeLabel      → 计时器插件的时间标签
  plugin_bank_argumentCard    → 论据库插件的论据卡片
  plugin_assistant_statusDot  → 助手插件的状态指示灯
```

> **规则**：必须以 `plugin_` 开头，避免与系统 objectName 冲突。

#### 8.5.3 设置页 objectName

设置页（`settings.py`）应使用以下系统 objectName（已在 `settings.qss` 中预定义）：

| objectName | 适用控件 | 说明 |
|------------|----------|------|
| `settingsPage` | QWidget | 页面根容器 |
| `settingsSectionTitle` | QLabel | 页面标题（18px 紫色粗体） |
| `settingsSectionDesc` | QLabel | 页面描述（12px 灰色） |
| `settingsCard` | QFrame | 卡片容器 |
| `settingsLabel` | QLabel | 字段标签（12px 粗体） |
| `settingsInput` | QLineEdit | 文本输入框 |
| `settingsCombo` | QComboBox | 下拉选择框 |
| `settingsSpin` | QSpinBox | 数字输入框 |
| `settingsCheck` | QCheckBox/StarCheckBox | 复选框 |
| `settingsSmallBtn` | QPushButton | 次级按钮 |
| `settingsPrimaryBtn` | QPushButton | 主按钮 |

### 8.6 面板设计

#### 8.6.1 标准面板结构

插件注册的面板（通过 `api.register_panel()`）应遵循以下三段式结构：

```
┌─────────────────────────────────┐
│ ◆ 面板标题 (pluginPanelTitle)   │  ← 标题栏
├─────────────────────────────────┤
│                                 │
│   [卡片1]  [卡片2]              │  ← 内容区
│   [卡片3]  [卡片4]              │    (QScrollArea)
│   ...                           │
│                                 │
├─────────────────────────────────┤
│        [主操作按钮]              │  ← 底部操作栏
└─────────────────────────────────┘
```

#### 8.6.2 面板代码模板

```python
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton, QScrollArea, QWidget
from PyQt5.QtCore import Qt

def create_plugin_panel():
    """创建插件面板（三段式标准结构）"""
    panel = QFrame()
    panel.setObjectName("pluginPanel")
    panel.setMinimumWidth(280)

    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    # ── 标题栏 ──
    title = QLabel("📋 我的插件面板")
    title.setObjectName("pluginPanelTitle")
    title.setContentsMargins(16, 12, 16, 12)
    layout.addWidget(title)

    # ── 分隔线 ──
    sep = QFrame()
    sep.setObjectName("pluginSeparator")
    sep.setFixedHeight(1)
    layout.addWidget(sep)

    # ── 内容区 ──
    scroll = QScrollArea()
    scroll.setObjectName("pluginScrollArea")
    scroll.setWidgetResizable(True)

    content = QWidget()
    content.setObjectName("pluginContent")
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(16, 12, 16, 12)
    content_layout.setSpacing(12)

    # 你的内容卡片 ...
    card = QFrame()
    card.setObjectName("pluginCard")
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(16, 14, 16, 14)

    card_title = QLabel("卡片标题")
    card_title.setObjectName("pluginCardTitle")
    card_layout.addWidget(card_title)

    card_body = QLabel("卡片内容...")
    card_body.setObjectName("pluginSubText")
    card_body.setWordWrap(True)
    card_layout.addWidget(card_body)

    content_layout.addWidget(card)
    content_layout.addStretch()
    scroll.setWidget(content)
    layout.addWidget(scroll, 1)

    # ── 底部操作栏 ──
    footer = QWidget()
    footer.setObjectName("pluginFooter")
    footer_layout = QVBoxLayout(footer)
    footer_layout.setContentsMargins(16, 12, 16, 12)

    btn_action = QPushButton("执行操作")
    btn_action.setObjectName("pluginPrimaryBtn")
    footer_layout.addWidget(btn_action)

    layout.addWidget(footer)
    return panel
```

#### 8.6.3 按钮尺寸设计规则

> **重要**：新增按钮时，必须综合考虑按钮文字（含 emoji）的字符数来设计宽高，确保文字完全显示。

| 文字长度 | 建议最小宽度 | 建议高度 |
|:--------:|:----------:|:------:|
| 1-2 字 | 50px | 36px |
| 3-4 字 | 80px | 36px |
| 5-6 字 | 120px | 36px |
| 7+ 字 | 160px+ | 40px |

按钮文字最小不应低于 10px。

### 8.7 设置页设计

#### 8.7.1 标准设置页结构

```python
"""我的插件 - 设置页"""
import json
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QComboBox, QSpinBox,
    QPushButton, QLineEdit
)

# ── PAGE_INFO 元信息 ──
PAGE_INFO = {
    "name": "我的插件设置",
    "icon": "🔌",
    "order": 200,
    "author": "作者名",
    "version": "1.0.0",
}

# ── PAGE_CONFIG ──
PAGE_CONFIG = {
    "save_path": "plugins/my_plugin/config.json",
    "auto_save": True,
}

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

def get_default_config():
    return {"option1": True, "option2": "default", "count": 5}

def build_page(parent_dialog, current_config):
    page = QWidget()
    page.setObjectName("settingsPage")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)

    # 标题
    title = QLabel("🔌 我的插件设置")
    title.setObjectName("settingsSectionTitle")
    layout.addWidget(title)

    # ── 卡片1：基本设置 ──
    card1 = QFrame()
    card1.setObjectName("settingsCard")
    c1_layout = QVBoxLayout(card1)
    c1_layout.setContentsMargins(20, 18, 20, 18)
    c1_layout.setSpacing(12)

    # 使用 StarCheckBox 替代 QCheckBox
    from workers.plugin_manager import get_api
    api = get_api()
    cb1 = api.create_checkbox("启用功能", checked=current_config.get("option1", True))
    c1_layout.addWidget(cb1)
    page._cb1 = cb1

    # 下拉框
    lbl_combo = QLabel("选项")
    lbl_combo.setObjectName("settingsLabel")
    c1_layout.addWidget(lbl_combo)

    combo = QComboBox()
    combo.setObjectName("settingsCombo")
    combo.addItems(["选项A", "选项B", "选项C"])
    combo.setCurrentText(current_config.get("option2", "选项A"))
    combo.setMinimumHeight(34)
    c1_layout.addWidget(combo)
    page._combo = combo

    # 数字框
    lbl_spin = QLabel("数量")
    lbl_spin.setObjectName("settingsLabel")
    c1_layout.addWidget(lbl_spin)

    spin = QSpinBox()
    spin.setObjectName("settingsSpin")
    spin.setRange(1, 100)
    spin.setValue(current_config.get("count", 5))
    spin.setMinimumHeight(32)
    c1_layout.addWidget(spin)
    page._spin = spin

    layout.addWidget(card1)

    # ── 重置按钮 ──
    btn_reset = QPushButton("恢复默认设置")
    btn_reset.setObjectName("settingsSmallBtn")
    layout.addWidget(btn_reset)

    layout.addStretch()
    return page

def collect_config(page_widget):
    return {
        "option1": page_widget._cb1.checked,
        "option2": page_widget._combo.currentText(),
        "count": page_widget._spin.value(),
    }
```

> **禁止在设置页中使用内联样式**：`settings.py` 中的控件必须通过 objectName 引用系统 QSS，不应使用 `setStyleSheet()` 或 `setFont()`。读者应能一目了然地知道控件的视觉外观来自系统统一样式。

### 8.8 对话框设计

#### 8.8.1 优先使用 API 弹窗

| 场景 | 推荐API | 说明 |
|------|---------|------|
| 信息提示 | `api.show_notification(title, msg)` | 简单通知，一个确定按钮 |
| 警告提示 | `api.show_warning(title, msg)` | ⚠ 图标 |
| 错误提示 | `api.show_error(title, msg)` | ✕ 图标 |
| 确认操作 | `api.show_confirm(title, msg)` | 返回 True/False |
| 询问选择 | `api.show_question(title, msg, buttons)` | 自定义按钮 |

```python
# ✅ 正确：使用 API 弹窗
api = get_api()
if api.show_confirm("确认删除", "此操作不可撤销，是否继续？"):
    delete_data()
    api.show_notification("操作完成", "数据已成功删除")

# ❌ 错误：直接使用 QMessageBox（样式不统一）
from PyQt5.QtWidgets import QMessageBox
QMessageBox.warning(None, "警告", "请确认操作")
```

#### 8.8.2 自定义 QDialog 规范

当需要更复杂的交互（如多字段输入、实时预览）时，才应使用自定义 QDialog：

```python
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton

class MyPluginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("我的插件窗口")
        self.setMinimumSize(420, 360)

        # ✅ 使用 system objectName，不硬编码颜色
        self.setObjectName("pluginDialog")
        self.setStyleSheet("")  # 清除内联，使用全局 QSS

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("对话框标题")
        title.setObjectName("pluginPanelTitle")
        layout.addWidget(title)

        # ... 内容 ...
        layout.addStretch()

        btn_ok = QPushButton("确定")
        btn_ok.setObjectName("pluginPrimaryBtn")
        btn_ok.clicked.connect(self.accept)
        layout.addWidget(btn_ok)
```

> **弹窗样式限制**：自定义 QDialog 应设置 `setWindowFlags(Qt.Dialog)` 并确保 objectName 以 `plugin_` 开头。

### 8.9 主题适配

#### 8.9.1 主题感知方式

插件应通过以下方式实现主题跟随，**优先级从高到低**：

| 优先级 | 方式 | 说明 |
|:------:|------|------|
| 1 | 使用系统 objectName | 颜色自动跟随主题切换，无需任何代码 |
| 2 | 读取 theme.json 颜色 | 适用于需要动态计算颜色的场景 |
| 3 | 使用 StarCheckBox | 组件内部已处理三主题适配 |

#### 8.9.2 读取当前主题颜色（高级）

当必须硬编码颜色时，应读取当前主题配置：

```python
import json
from pathlib import Path

def _get_theme_colors():
    """读取当前激活主题的色板"""
    project_root = Path(__file__).parent.parent.parent
    config_path = project_root / "config" / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        theme_name = json.load(f).get("theme", "catppuccin_mocha")
    theme_path = project_root / "style" / "themes" / theme_name / "theme.json"
    with open(theme_path, "r", encoding="utf-8") as f:
        return json.load(f)["colors"]

colors = _get_theme_colors()
label.setStyleSheet(f"color: {colors['accent_purple']};")
```

> **警告**：这种方式仅在系统 objectName 无法满足需求时使用，且应缓存结果避免重复 I/O。

#### 8.9.3 插件 QSS 文件

如果你的插件需要自定义 QSS，应按以下结构存放：

```
style/themes/catppuccin_mocha/plugins.qss    ← 系统提供的插件通用 QSS
style/themes/catppuccin_latte/plugins.qss
style/themes/catppuccin_macchiato/plugins.qss
```

你可以在 `plugins.qss` 中追加插件的自定义样式：

```css
/* plugins.qss - 插件通用样式 + 自定义扩展 */

/* 系统预定义 (由 StarDebate 维护) */
#pluginPanel { background-color: --base; }
#pluginPanelTitle { color: --accent_purple; font-size: 18px; font-weight: bold; }
/* ... */

/* 你的插件自定义样式 (添加到文件末尾) */
#plugin_timer_phaseCard {
    background-color: --surface;
    border-radius: 8px;
    padding: 12px;
}
```

### 8.10 StarCheckBox 使用

> **强制要求**：插件中需要使用复选框时，应使用 `api.create_checkbox()` 创建的 **StarCheckBox**，而非 Qt 原生 `QCheckBox`。StarCheckBox 支持 SVG 动态着色，三主题自动适配。

```python
# ✅ 正确
api = get_api()
cb = api.create_checkbox("启用功能", checked=True, checkbox_size=20)
cb.toggled.connect(lambda checked: print(f"状态: {checked}"))
layout.addWidget(cb)

# ❌ 错误
from PyQt5.QtWidgets import QCheckBox
cb = QCheckBox("启用功能")  # 样式不统一，无主题跟随
```

**StarCheckBox 参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `text` | str | `""` | 标签文字 |
| `checked` | bool | `False` | 初始选中状态 |
| `checkbox_size` | int | `20` | 图标像素大小（≥12px） |
| `object_name` | str | `"starCheckBox"` | QSS objectName |
| `icon_scheme` | str | `"auto"` | 图标色系（默认 auto=主题自适应） |

### 8.11 StarSpinBox 使用

> **推荐使用**：插件中需要数字输入框时，应使用 **StarSpinBox / StarDoubleSpinBox** 替代 Qt 原生 `QSpinBox` / `QDoubleSpinBox`。支持 SVG 动态着色、三种布局模式切换、长按自动重复、三主题适配。

#### 8.11.1 基本用法

```python
# ✅ 正确 — 通过 API 创建（推荐）
api = get_api()
spin = api.create_spinbox(value=42, max_value=100, suffix=" 人")

# ✅ 正确 — 直接导入（核心开发用）
from components.star_spinbox import StarSpinBox
spin = StarSpinBox(value=42, max_value=100, suffix=" 人")
spin.valueChanged.connect(lambda v: print(f"新值: {v}"))
layout.addWidget(spin)

# ✅ 正确 — 使用 StarDoubleSpinBox
spin2 = StarDoubleSpinBox(value=0.7, min_value=0.0, max_value=2.0,
                          step=0.1, decimals=2)

# ❌ 错误 — 原生 QSpinBox 无主题跟随
from PyQt5.QtWidgets import QSpinBox
spin = QSpinBox()  # 样式不统一，无主题适配
```

#### 8.11.2 三种布局模式

通过 `button_layout` 参数切换三种模式：

| 模式 | 值 | 效果 | 适用场景 |
|------|-----|------|----------|
| 右侧竖直 (默认) | `"right"` | `[编辑区 \| ▲▼]` | 通用/设置页 |
| 左右分离 | `"split"` | `[▼ \| 编辑区 \| ▲]` | 步进调节/大按钮 |
| 紧凑内嵌 | `"embedded"` | `[编辑区 \| ▲▼内嵌]` | 表格/紧凑布局 |

```python
# 动态切换布局
spin.setButtonLayout("split")
```

#### 8.11.3 StarSpinBox 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `value` | int | 0 | 初始值 |
| `min_value` | int | 0 | 最小值 |
| `max_value` | int | 99 | 最大值 |
| `step` | int | 1 | 步长 |
| `prefix` | str | `""` | 前缀（如 `"$"`） |
| `suffix` | str | `""` | 后缀（如 `" px"`） |
| `button_layout` | str | `"right"` | 布局模式 |
| `spin_height` | int | 32 | 整体高度（≥24px） |
| `button_width` | int | 22 | 按钮区宽度 |
| `editable` | bool | True | 是否可直接编辑 |
| `icon_scheme` | str | `"auto"` | 图标色系 |

**StarDoubleSpinBox 额外参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `decimals` | int | 2 | 小数位数 |

#### 8.11.4 主要 API

| 方法 | 说明 |
|------|------|
| `value()` | 获取当前值 |
| `setValue(v)` | 设置值（自动 clamp） |
| `setRange(min, max)` | 设置范围 |
| `setButtonLayout(mode)` | 切换布局模式 |
| `setSpinHeight(h)` | 调整高度 |
| `setIconScheme(scheme)` | 修改图标色系 |
| `setEnabled(bool)` | 启用/禁用 |
| `refresh_theme()` | 主题热切换刷新 |

**信号：**

| 信号 | 说明 |
|------|------|
| `valueChanged(int/float)` | 值变化时发射 |
| `editingFinished()` | 编辑完成（回车/失焦） |

#### 8.11.5 交互行为

- **单击按钮**：+/- 步长
- **长按按钮** (>400ms)：持续增减（80ms 间隔）
- **鼠标滚轮**：上滚 +step / 下滚 -step
- **键盘 ↑↓**：+/- step
- **键盘 PgUp/PgDn**：+/- step×10
- **Esc**：取消编辑，恢复原值

### 8.12 StarButton 使用

> **推荐使用**：插件中需要任何按钮时，应使用 **StarButton** 替代 Qt 原生 `QPushButton`。提供 6 种排布模式、5 种占比模式、自动尺寸、主题自适应绘制。

StarButton 通过 `api.create_button()` 创建（详见 [4.17d](#417d-自定义按钮-v100-新增)）。

#### 8.12.1 基本用法

```python
# 基础文字按钮
btn = api.create_button("搜索")
btn.clicked.connect(lambda: print("搜索"))

# 带主题色的按钮
btn = api.create_button("保存", accent="#89b4fa")

# 图标+文字
btn = api.create_button(
    "保存", icon="icon/save.svg",
    layout_mode="h_left",
)
```

#### 8.12.2 关键参数建议

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `layout_mode` | `"h_left"`（默认） | 图标左文字右，最符合用户习惯 |
| `ratio_h` | `0.75`~`0.85` | 文字区域占按钮宽度比例 |
| `text_align` | `"left"` 或 `"center"` | 工具栏按钮推荐 left |
| `accent` | `None` 或主题色 | 透明按钮用 None，主要操作按钮用主题色 |

#### 8.12.3 与 QSS 的关系

StarButton 的 `paintEvent` 接管了背景/圆角绘制，QSS 的 `background-color` / `border` / `border-radius` **不会生效**。文字颜色可通过 QSS 控制，自定义样式推荐通过 `accent` 参数设置。

### 8.13 反模式（应避免的做法）

以下是**严格禁止**的 UI 编码实践：

| 反模式 | 说明 | 正确做法 |
|--------|------|----------|
| ❌ `setStyleSheet("color: #cba6f7;")` | 硬编码颜色 | ✅ 使用 objectName |
| ❌ `setFont(QFont("HarmonyOS Sans SC", 14))` | 硬编码字体大小 | ✅ 在 QSS 中定义 |
| ❌ `background-color: #1e1e2e` | 硬编码背景色 | ✅ 使用 `--base` 色键 |
| ❌ 使用原生 `QCheckBox` | 无主题跟随 | ✅ 使用 `api.create_checkbox()` |
| ❌ 使用原生 `QSpinBox` / `QDoubleSpinBox` | 无主题跟随 | ✅ 使用 `api.create_spinbox()` / `api.create_double_spinbox()` |
| ❌ 使用 `QMessageBox` | 样式不统一 | ✅ 使用 `api.show_confirm()` 等 |
| ❌ objectName 无前缀 | 可能冲突 | ✅ 使用 `plugin_{id}_` 前缀 |
| ❌ 文字小于 10pt | 可读性差 | ✅ 最小 ≥10pt |
| ❌ 按钮固定宽高不考虑文字长度 | 文字截断 | ✅ 根据字数设计尺寸 |

### 8.13 完整UI示例

> 以下示例展示一个遵循全部规范的插件面板。

```python
"""插件UI示例 — 展示所有规范"""
import json
from pathlib import Path
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QHBoxLayout,
)
from PyQt5.QtCore import Qt
from workers.plugin_manager import get_api


def build_example_panel():
    """构建规范化的插件面板"""
    api = get_api()

    panel = QFrame()
    panel.setObjectName("pluginPanel")
    panel.setMinimumWidth(320)

    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    # ═══ 标题栏 ═══
    header = QWidget()
    header.setObjectName("pluginHeader")
    header_layout = QHBoxLayout(header)
    header_layout.setContentsMargins(16, 12, 16, 12)

    title = QLabel("📋 辩论分析器")
    title.setObjectName("pluginPanelTitle")
    header_layout.addWidget(title)
    header_layout.addStretch()

    btn_close = QPushButton("✕")
    btn_close.setObjectName("pluginSecondaryBtn")
    btn_close.setFixedSize(32, 32)
    header_layout.addWidget(btn_close)
    layout.addWidget(header)

    # 分隔线
    sep = QFrame()
    sep.setObjectName("pluginSeparator")
    sep.setFixedHeight(1)
    layout.addWidget(sep)

    # ═══ 内容区 ═══
    scroll = QScrollArea()
    scroll.setObjectName("pluginScrollArea")
    scroll.setWidgetResizable(True)

    content = QWidget()
    content.setObjectName("pluginContent")
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(16, 12, 16, 12)
    content_layout.setSpacing(12)

    # ── 卡片1：状态 ──
    card1 = QFrame()
    card1.setObjectName("pluginCard")
    c1 = QVBoxLayout(card1)
    c1.setContentsMargins(16, 14, 16, 14)
    c1.setSpacing(8)

    c1_title = QLabel("📊 当前状态")
    c1_title.setObjectName("pluginCardTitle")
    c1.addWidget(c1_title)

    c1_body = QLabel("正方一辩稿：1,234 字\n反方一辩稿：1,567 字\nAI分析：已完成")
    c1_body.setObjectName("pluginSubText")
    c1.addWidget(c1_body)

    content_layout.addWidget(card1)

    # ── 卡片2：开关 ──
    card2 = QFrame()
    card2.setObjectName("pluginCard")
    c2 = QVBoxLayout(card2)
    c2.setContentsMargins(16, 14, 16, 14)
    c2.setSpacing(10)

    c2_title = QLabel("⚙️ 功能开关")
    c2_title.setObjectName("pluginCardTitle")
    c2.addWidget(c2_title)

    cb1 = api.create_checkbox("自动分析辩论内容", checked=True)
    c2.addWidget(cb1)

    cb2 = api.create_checkbox("保存分析历史记录")
    c2.addWidget(cb2)

    content_layout.addWidget(card2)

    content_layout.addStretch()
    scroll.setWidget(content)
    layout.addWidget(scroll, 1)

    # ═══ 底部操作栏 ═══
    footer = QWidget()
    footer.setObjectName("pluginFooter")
    footer_layout = QVBoxLayout(footer)
    footer_layout.setContentsMargins(16, 12, 16, 12)
    footer_layout.setSpacing(8)

    btn_analyze = QPushButton("🔍 开始分析")
    btn_analyze.setObjectName("pluginPrimaryBtn")
    footer_layout.addWidget(btn_analyze)

    btn_export = QPushButton("📤 导出报告")
    btn_export.setObjectName("pluginSecondaryBtn")
    footer_layout.addWidget(btn_export)

    layout.addWidget(footer)

    # ── 连接信号 ──
    btn_analyze.clicked.connect(lambda: api.update_status("分析完成！"))
    btn_close.clicked.connect(lambda: panel.hide())

    return panel
```

**此示例展示的规范要点**：
- ✅ 三段式结构（标题栏 + 内容滚动区 + 底部操作栏）
- ✅ 全部使用系统 objectName，零硬编码颜色
- ✅ StarCheckBox 替代 QCheckBox
- ✅ 卡片使用 `pluginCard`，嵌套标题使用 `pluginCardTitle`
- ✅ 按钮根据文字长度合理设计尺寸
- ✅ 最小宽度 320px
- ✅ 禁止使用 `setFont()` / `setStyleSheet()` 内联样式
- ✅ 面板控件在宽度变动时能自适应调整布局和尺寸（`QScrollArea` + `QHBoxLayout` / `QGridLayout` / `QSplitter` 等弹性布局）

### 8.7 窗口架构说明

```
StarDebateApp (QMainWindow, FramelessWindowHint + WA_TranslucentBackground)
  └── ShadowContainer (components/shadow_container/)   ← 阴影容器
      └── QVBoxLayout (margin=15px 为阴影留空间)
          └── shadowContainerContent (solid bg + border-radius:12px)
              └── [title_bar + content_wrapper + status_bar]
```

- 主窗口使用 `ShadowContainer` 组件（位于 `components/shadow_container/`）包裹实际内容
- 阴影效果通过 `QGraphicsDropShadowEffect` 实现（blurRadius=30, offset(0,6), rgba(0,0,0,100)）
- 窗口实际尺寸包含 15px 阴影边距，内容区域 = 窗口尺寸 - 30px
- 最大化时自动禁用阴影并清除圆角
- 如果你创建自定义弹窗（`Qt.Dialog | FramelessWindowHint`），可以复用 `ShadowContainer` 获得一致效果
- 阴影容器的 QSS 文件为 `shadow_container.qss`，每个主题下独立配置

### 4.24 更新器 API (v5.2.0 新增)

> 版本：v5.2.0 | 更新时间：2026-06-22

StarDebate 内置本地增量补丁更新系统。插件开发者可通过 `UpdateManager` 访问更新功能。

#### 4.24.1 更新器架构

```
StarDebate/
├── workers/updater/                    # 更新器核心模块
│   ├── __init__.py                     # 模块导出
│   ├── update_utils.py                 # 工具函数（版本比较、SHA256、备份管理、EXE 路径路由）
│   ├── update_checker.py               # 启动时自动检测补丁
│   ├── update_manager.py              # 主进程侧管理器（手动重启提示模式）
│   ├── update_patch_applier.py         # 独立更新进程脚本（稳定不动）
│   └── update_dialogs.py               # UI 对话框组件
├── style/themes/<theme>/updater.qss    # 样式表
└── icon/common/update.svg             # 更新图标
```

#### 4.24.2 基本使用

```python
from workers.updater import UpdateManager, UpdateChecker

# 获取主窗口的更新器实例（已由 StarDebateApp 初始化）
mgr = main_window._updater_mgr

# 手动触发检测
mgr.check_on_startup()

# 弹出文件选择对话框让用户选择补丁
mgr.show_manual_install()
```

#### 4.24.3 补丁格式

**ZIP 文件结构：**
```
update_v5.0.0_to_v5.1.0.zip
├── manifest.json          # 必需：版本信息 + 变更清单 + SHA256
└── files/                 # 所有新增/修改的文件
    ├── workers/app_config/config_manager.py
    └── style/themes/notion_dark/main.qss
```

**manifest.json 格式：**
```json
{
  "from_version": "5.0.0",
  "to_version": "5.1.0",
  "created_at": "2026-06-22",
  "min_app_version": "5.0.0",
  "changes": [
    {"action": "modify", "path": "workers/app_config/config_manager.py", "sha256": "abc..."},
    {"action": "add", "path": "workers/updater/updater.py", "sha256": "def..."},
    {"action": "delete", "path": "workers/legacy/old_handler.py"}
  ],
  "release_notes": "## v5.1.0\n- 新增功能\n- 修复问题"
}
```

**action 类型：**
| 类型 | 说明 | 需要 SHA256 |
|------|------|:-----------:|
| `add` | 新增文件 | 是 |
| `modify` | 修改文件 | 是 |
| `delete` | 删除文件 | 否 |

> **v6.0.0+ EXE 版注意**：在 EXE 打包环境下（`sys.frozen=True`），所有 `.py` 源文件存放于 `src/` 子目录。更新器会自动检测 EXE 环境，在 `apply_new_files()` 和 `execute_deletes()` 中为 `.py` 文件路​​径自动添加 `src/` 前缀。补丁包的 `path` 字段无需特殊处理，仍按**相对于项目根目录**填写（如 `workers/updater/update_utils.py`），更新器会自动路由到正确位置。非 `.py` 文件（config/icon/style 等）不受影响。

#### 4.24.4 UpdateManager 公共方法

| 方法 | 说明 |
|------|------|
| `check_on_startup()` | 启动时自动：先检查上次未完成 → 再扫描根目录补丁 → 弹窗提示 |
| `show_manual_install()` | 弹出文件选择对话框，手动选 .zip 补丁安装 |
| `get_ignored_patches_list()` | 返回被忽略的补丁列表 `[dict]` |
| `reenable_patch(filename)` | 从忽略列表移除指定补丁 |

**Signals：**
| Signal | 触发时机 |
|--------|----------|
| `update_started` | 用户确认开始更新流程 |
| `update_cancelled` | 用户取消或更新失败 |

#### 4.24.5 UpdateChecker（独立使用）

```python
from workers.updater import UpdateChecker

checker = UpdateChecker()
result = checker.scan()  # 扫描根目录
if result:
    print(f"发现: {result['patch_filename']}")
    print(f"目标版本: {result['to_version']}")
    print(f"变更统计: {result['file_stats']}")
```

返回值结构：
```python
{
    "patch_filename": str,      # 补丁文件名
    "patch_path": str,           # 补丁完整路径
    "manifest": dict,            # 完整 manifest 内容
    "to_version": str,           # 目标版本号
    "release_notes": str,        # 发行说明 (Markdown)
    "file_stats": {              # 文件变更统计
        "add": int,
        "modify": int,
        "delete": int,
    },
    "config_affected": bool,     # 是否涉及 config/ 目录
    "config_files": list[str],   # 涉及的 config/ 下文件列表
}
```

#### 4.24.6 update_utils 公共工具函数

```python
from workers.updater import (
    get_project_root,              # 项目根目录路径
    get_config_version,            # 读取当前版本号
    compare_versions(v1, v2),      # 比较版本号 (1/0/-1)
    compute_sha256(filepath),      # 计算 SHA256
    verify_file_hash(path, hash),  # 校验文件哈希
    read_manifest(zip_path),       # 解析 ZIP manifest
    validate_patch_compatibility(manifest, version),  # 校验兼容性
    backup_config_dir(version),    # 全量备份 config/
    apply_new_files(src_dir, dst_root),   # 从 src_dir 复制文件到 dst_root（EXE 版自动 src/ 路由）
    execute_deletes(delete_paths, root_dir),  # 删除指定文件列表（EXE 版自动 src/ 路由）
    list_backups(),               # 列出所有备份
    delete_backup(name),          # 删除指定备份
    clean_pycache(root),          # 清理 __pycache__
)
```

**`apply_new_files(src_dir, dst_root)`：**
- 从 `src_dir` 遍历所有文件，复制到 `dst_root` 对应路径
- **EXE 版**（`sys.frozen=True`）：`.py` 文件自动路由到 `dst_root/src/` 下，非 `.py` 文件不变
- 返回 `(成功数, 跳过数, 已覆盖路径列表)`

**`execute_deletes(delete_paths, root_dir)`：**
- 按 `delete_paths` 列表删除 `root_dir` 下对应文件
- **EXE 版**：`.py` 文件路径自动添加 `src/` 前缀

#### 4.24.7 UI 对话框组件

```python
from workers.updater import (
    UpdateFoundDialog,       # 发现更新的确认弹窗
    UpdateProgressDialog,    # 更新进度面板
    UpdateSuccessToast,      # 更新成功通知 toast
    RecoveryDialog,          # 上次更新失败恢复弹窗
)

# UpdateFoundDialog
dlg = UpdateFoundDialog(parent, patch_info=info_dict)
dlg.update_confirmed.connect(lambda data: print("用户确认更新:", data["to_version"]))
dlg.exec_()

# UpdateSuccessToast
toast = UpdateSuccessToast(
    parent=main_window,
    new_version="5.1.0",
    backup_name="v5.0.0_config",
    has_backup=True,
)
toast.show_toast(duration_ms=8000)  # 8秒后自动关闭
```

#### 4.24.8 更新流程完整说明

```
触发（自动扫描 / 手动选择）
  → 校验版本号匹配 + 逐文件 SHA256
  → 备份 config/ 到 backups/v{version}_config/ （保留最近 2 次）
  → 解压变更文件到 _update_staging/new_files/
  → 写入 batch_info.json + delete_list.txt + run_update.bat
  → 显示进度面板（校验→备份→解压→写脚本）
  → 启动 run_update.bat（DETACHED_PROCESS）→ 主进程退出
  ┌─ run_update.bat:
  │  等待主进程退出(3s)
  │  调用 python update_patch_applier.py --batch-info batch_info.json
  │  ├─ 从 new_files/ 复制所有文件覆盖到项目根目录
  │  │   (v6.0.0+ EXE 版：.py 文件自动路由到 src/ 子目录)
  │  ├─ 根据 delete_list.txt 删除指定文件
  │  │   (v6.0.0+ EXE 版：.py 文件路径自动添加 src/ 前缀)
  │  ├─ 清理 __pycache__
  │  └─ 写入 update_state.json (status="completed")
  └─ 启动 StarDebate.py 重启

重启后:
  → 检测 update_state.json 有"completed"标记
  → 显示 UpdateSuccessToast（含删除备份选项）
  → 清理暂存目录和状态文件
```

#### 4.24.9 排除范围（不参与更新）

以下路径不会被更新：
- `plugins/` — 插件独立管理
- `__pycache__/` — 自动清理
- `.git/`, `_update_staging/`, `backups/`, `.codebuddy/`
- 隐藏文件（以 `.` 开头）

> **注意**：`update_patch_applier.py` 本身永远不参与增量更新，
> 以确保更新器自身的执行逻辑始终可用。

---

## 9. 插件分发与导入

### 9.1 分发方式

StarDebate 插件支持两种分发方式：

| 方式 | 格式 | 适用场景 |
|------|------|----------|
| **📦 .stp 插件包**（推荐） | 单文件 `.stp`（Zip + 校验 + 元数据） | 发布、分享、插件市场 |
| **📁 文件夹插件**（兼容） | 包含 `plugin.json` + `main.py` 的文件夹 | 开发调试、本地使用 |

> 从 v4.5.0 起推荐使用 `.stp` 格式分发，新功能优先支持。

### 9.2 .stp 插件包分发

`.stp`（StarPlugin Package）是基于 Zip 的单文件封装格式，内置 SHA256 校验和与元数据声明。

#### 使用插件项目管理器打包

```bash
# 启动管理器
python plugin_manager/main.py
```

流程：创建/打开插件项目 → 填写元数据 → 点击「📦 打包为 .stp」

#### 使用命令行打包

```bash
# 推荐方式：使用 tools/pack_stp.py 脚本
python tools/pack_stp.py plugins/my_plugin/
python tools/pack_stp.py plugins/my_plugin/ -o my_plugin.stp
python tools/pack_stp.py plugins/my_plugin/ --validate  # 仅验证

# 或直接在 Python 中调用核心模块
python -c "
from plugin_manager.core.stp_packager import package
package('./plugins/my_plugin/', './my_plugin.stp')
print('打包完成')
"
```

#### 打包规范

`.stp` 包的内部结构：

```
my_plugin.stp（Zip 压缩包，注释 "StarPlugin"）
├── plugin.json       ← 必需：含 checksum 和元数据
├── main.py           ← 必需：插件入口
├── settings.py       ← 可选：设置页
├── README.md         ← 可选：说明文档
├── CHANGELOG.md      ← 可选：变更日志
├── LICENSE           ← 可选：许可证
└── resources/        ← 可选：资源文件
    ├── icon.svg
    └── styles.qss
```

详细格式规范见 [`docs/stp_format.md`](stp_format.md)。

### 9.3 用户安装步骤

用户可通过以下两种方式安装 `.stp` 插件包：

#### 方式一：拖拽安装

直接将 `.stp` 文件拖入 StarDebate 主窗口 → 弹出安装预览窗口 → 确认安装。

#### 方式二：菜单安装

1. 点击右侧 `🔌 插件` 按钮打开插件管理面板
2. 点击「📦 安装插件」按钮
3. 选择 `.stp` 文件（或插件文件夹）
4. 在弹出的**安装预览窗口**中确认：
   - 插件名称、作者、版本、描述
   - 所需权限列表（危险权限标红）
   - 依赖检查结果（缺失依赖阻止安装）
   - 版本兼容性
   - 冲突检测（已安装时可选覆盖升级/并列安装/取消）
5. 确认后安装完成（**默认禁用**，需手动启用）

### 9.4 安装后操作

- 插件安装后默认**禁用**，需在插件列表中点击开关按钮启用
- 启用的插件注册的导航按钮会出现在侧边导航栏的插件区
- 启用的插件注册的面板会出现在对应的功能区

### 9.5 卸载插件

在插件列表中点击「删除」按钮：

- **关闭开关（toggle off）**：从内存中**完全卸载**插件
  - 调用 `on_disable()` → 清理所有注册项 → 销毁面板 widget → 释放模块引用 + 清除 `sys.modules` 缓存
  - 插件文件保留在磁盘，用户可重新开启（会重新加载模块）
  - 设置页自动从设置对话框中移除
- **仅禁用**（推荐）：同关闭开关行为，保留插件文件，日后可重新启用
- **彻底删除**：先执行完整卸载流程，再删除插件目录，不可恢复

> **★ v?.?.? 变更**：「仅禁用」和「关闭开关」的行为已统一——都会触发完整的内存卸载。区别仅在是否保留磁盘文件。

### 9.6 插件升级

当安装的 `.stp` 包中包含已存在的 `plugin_id` 时，安装预览窗口会提示冲突：

- **覆盖升级**（推荐）：替换现有插件文件，保留启用状态
- **并列安装**：自动修改 `plugin_id` 以允许两个版本共存
- **取消安装**：不做任何更改

### 9.7 文件夹插件兼容

旧式文件夹插件（无 `plugin.json` 或仅有 `plugin.json` 无新字段）继续受支持：

1. 文件夹插件导入时无需校验和检查
2. 不声明 `permissions` 视为全部权限可用（向后兼容）
3. 不声明 `plugin_id` 时以文件夹名作为标识
4. 建议新开发时手动添加 `.stp` 相关字段以利未来升级

---

## 10. 完整示例

### 示例 1：字数统计插件（文件夹形式）

```
word_counter/
├── plugin.json
├── main.py
└── settings.py
```

**plugin.json**：

```json
{
    "name": "字数统计",
    "plugin_id": "wangwu.word_counter",
    "version": "1.0.0",
    "stp_version": "1.0",
    "min_app_version": "1.0.0",
    "author": "王五",
    "description": "保存辩稿时自动统计字数",
    "main": "main.py",
    "enabled": true,
    "permissions": ["file_read", "settings_read"],
    "tags": ["工具", "文字"],
    "config": {}
}
```

**main.py**：

```python
from workers.plugin_manager import get_api

def on_speech_saved(side):
    api = get_api()
    text = api.get_speech_content(side)
    char_count = len(text.replace("\n", "").replace(" ", ""))
    line_count = len(text.split("\n"))
    side_label = "正方" if side == "pro" else "反方"
    api.show_notification(
        f"📊 {side_label}一辩稿统计",
        f"字符数: {char_count}\n行数: {line_count}"
    )

def on_enable():
    api = get_api()
    api.on("speech_saved", on_speech_saved)
    api.update_status("字数统计插件已就绪")

def on_disable():
    api = get_api()
    api.off("speech_saved", on_speech_saved)
```

**settings.py**：参见 [2.3 settings.py 设置页规范](#23-settingspy-设置页规范) 中的完整示例。



### 示例 2：辩论报告导出插件（文件夹形式）

```
report_exporter/
├── plugin.json
└── main.py
```

**plugin.json**：

```json
{
    "name": "辩论报告导出器",
    "version": "1.0.0",
    "author": "李四",
    "description": "一键导出辩论数据为 Markdown 报告",
    "main": "main.py",
    "enabled": true,
    "config": {
        "include_analysis": true,
        "include_framework": true,
        "output_format": "markdown"
    }
}
```

**main.py**：

```python
import json
import os
from datetime import datetime
from workers.plugin_manager import get_api

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

def load_config():
    with open(os.path.join(PLUGIN_DIR, "plugin.json"), "r", encoding="utf-8") as f:
        return json.load(f).get("config", {})

def export_report():
    api = get_api()
    config = load_config()

    info = api.get_debate_info()
    if not info.get("title"):
        api.show_notification("导出失败", "请先打开一个辩论项目")
        return

    # 构建 Markdown 报告
    lines = []
    lines.append(f"# 辩论报告：{info['title']}")
    lines.append(f"\n> 导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"\n## 基本信息")
    lines.append(f"- 正方：{info['pro_side']}")
    lines.append(f"- 反方：{info['con_side']}")

    # 一辩稿
    lines.append(f"\n## 正方一辩稿")
    pro_speech = api.get_speech_content("pro")
    lines.append(pro_speech if pro_speech else "（无内容）")

    lines.append(f"\n## 反方一辩稿")
    con_speech = api.get_speech_content("con")
    lines.append(con_speech if con_speech else "（无内容）")

    # AI 分析（可选）
    if config.get("include_analysis"):
        lines.append(f"\n## AI 分析报告")
        analysis = api.get_analysis_result("pro")
        if analysis:
            for arg in analysis.get("arguments", []):
                lines.append(f"- **论点**：{arg}")
            for sug in analysis.get("suggestions", []):
                lines.append(f"- 💡 建议：{sug}")

    # 框架（可选）
    if config.get("include_framework"):
        lines.append(f"\n## 辩论框架")
        nodes = api.get_framework_data()
        for node in nodes:
            ntype = node.get("node_type", "?")
            text = node.get("text", "")
            lines.append(f"- [{ntype}] {text}")

    report = "\n".join(lines)

    # 保存到项目目录
    filename = f"debate_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    success = api.write_file_in_project(filename, report)

    if success:
        api.show_notification("导出成功", f"报告已保存到：{filename}")
    else:
        api.show_notification("导出失败", "请确保已打开一个有效项目")

def on_enable():
    api = get_api()
    api.update_status("报告导出插件已就绪，调用 export_report() 导出")
    # 注册快捷键等...
```

### 示例 3：关键词高亮分析插件

```python
# keyword_analyzer.py
"""分析双方一辩稿中的关键词使用频率"""

from workers.plugin_manager import get_api
from collections import Counter

def analyze_keywords():
    api = get_api()
    info = api.get_debate_info()
    if not info.get("title"):
        api.update_status("请先打开辩论项目")
        return

    pro_text = api.get_speech_content("pro")
    con_text = api.get_speech_content("con")

    # 获取预设关键词
    pro_keywords = api.get_keywords("pro")
    con_keywords = api.get_keywords("con")

    def count_keywords(text, keywords):
        result = {}
        for kw in keywords:
            word = kw.get("word", "")
            if word:
                result[word] = text.count(word)
        return result

    pro_counts = count_keywords(pro_text, pro_keywords)
    con_counts = count_keywords(con_text, con_keywords)

    # 生成报告
    report = "## 关键词使用频率分析\n\n"
    report += "### 正方关键词\n"
    for word, count in sorted(pro_counts.items(), key=lambda x: -x[1]):
        report += f"- **{word}**: {count} 次\n"

    report += "\n### 反方关键词\n"
    for word, count in sorted(con_counts.items(), key=lambda x: -x[1]):
        report += f"- **{word}**: {count} 次\n"

    api.write_file_in_project("keyword_analysis.md", report)
    api.show_notification("分析完成", "关键词频率分析已保存")

def on_enable():
    api = get_api()
    api.update_status("关键词分析插件已就绪")
```

---

## 11. 常见问题

### Q: 插件导入后没有反应？

检查你的插件文件夹是否包含 `plugin.json` 和入口 `.py` 文件。至少需要 `plugin.json` 清单文件和 `main.py` 入口文件，`on_enable` 和 `on_disable` 是可选的。

### Q: 能否导入单个 .py 文件作为插件？

v1.5.0 起不再支持单文件插件。所有插件必须以多文件文件夹形式开发，包含 `plugin.json` 清单文件。请将你的 `.py` 文件放入文件夹并添加 `plugin.json`。

### Q: 如何调试插件？

StarDebate 提供四个层级的调试能力：

1. **`print()` 语句**：输出显示在控制台中（如果从终端启动）。

2. **`api.log_monitor()`**：向调试台的监视系统发送结构化日志（需在调试台「调试 ▼」菜单中开启对应监视类型）。
   ```python
   api.log_monitor("plugin_watch", "处理完成: 150条数据")
   ```
   > **v2.5.0 起**：监视日志通过 LogService 独立进程写入，主窗口崩溃不影响日志落盘。

3. **`api.execute_command()`**：从代码中运行内置命令获取系统状态、配置等信息。
   ```python
   result = api.execute_command("status")
   print(result["output"])
   ```

4. **调试台**（标题栏 帮助 ▼ → 🔧 调试台）：可查看所有运行日志、API请求、插件状态，支持 `help` 列出所有可用命令，也可运行插件注册的自定义命令。

### Q: 程序崩溃后如何查看日志？

StarDebate v2.5.0 起日志系统运行在独立进程中，主窗口崩溃**不会**导致日志丢失：

1. **自动保留**：崩溃前的所有日志已通过 LogService 写入 `docs/log/debug_*.log`
2. **崩溃快照**：LogService 检测到主进程异常退出后，自动在日志末尾写入系统快照（PID、退出时间、残留条目数）
3. **弹窗定位**：CrashMonitor 独立进程弹出崩溃弹窗 → 点击「📂 打开日志文件夹」→ 查看日志
4. **应急降级**：即使 LogService 异常，监视钩子也会自动降级为文件直写（日志中标记 `[EMERGENCY]` / `[MON-EMERGENCY]`）

### Q: 插件如何注册可在调试台运行的命令？

在 `on_enable()` 中调用 `api.register_console_command()`：

```python
def handle_mycmd(args):
    return f"执行结果: {args}"

def on_enable():
    api = get_api()
    api.register_console_command(
        cmd_name="myplugin:info",
        handler_fn=handle_mycmd,
        args_desc="[选项]",
        description="显示插件信息",
    )
```

注册后，用户可在调试台输入 `myplugin:info` 执行该命令，输入 `help` 可看到该命令的说明。

### Q: 插件可以使用 pip 安装的第三方库吗？

可以。插件可以直接 `import` 当前 Python 环境中已安装的任何库。

```python
import pandas as pd
import matplotlib.pyplot as plt
from openpyxl import Workbook
```

### Q: 插件崩溃会影响 StarDebate 吗？

不会。所有插件调用都被 try/except 包裹。插件崩溃时：
- 主程序不受影响，继续正常运行
- 状态栏会显示错误提示
- 控制台会打印完整的错误堆栈
- 用户可禁用该插件并重启
- ★ 起居注会自动记录崩溃（`[CRON] ❌ plugin·xxx → failed`）

### Q: 如何查看插件加载/API/AI 调用的成功记录？

StarDebate v2.6.0 起内置**起居注 (ActivityChronicle)** 自动活动日志系统：

1. 打开 `docs/log/debug_*.log` 日志文件
2. 搜索 `[CRON]` 标签查看所有活动记录：
   - `[CRON] ▶ plugin·xxx → ok` — 插件加载/卸载
   - `[CRON] ✓ api·xxx → ok (ms)` — API 调用
   - `[CRON] ✅ ai·xxx → ok (ms)` — AI 调用
   - `[CRON] ❌ feature·xxx → failed (ms): detail` — 失败操作
3. 起居注自动生效，**插件无需任何代码修改**
4. 完整说明见 `docs/log/起居注说明.md`

### Q: 可以创建带 UI 的插件吗？

可以。你可以使用 PyQt5 创建自定义对话框或面板。

```python
from PyQt5.QtWidgets import QDialog, QLabel, QVBoxLayout

class MyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("我的插件窗口")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Hello from plugin!"))
        self.setStyleSheet(
            "QDialog { background-color: #1e1e2e; color: #cdd6f4; }"
        )

def show_my_dialog():
    from workers.plugin_manager import get_api
    api = get_api()
    dialog = MyDialog(api.mw)  # api.mw 是主窗口引用
    dialog.exec_()
```

### Q: 如何让插件在 StarDebate 启动时自动运行？

默认所有 `enabled: true` 的插件在启动时自动加载并调用 `on_enable()`。

### Q: 插件可以访问网络吗？

可以使用 Python 标准库的 `urllib` 或 `requests`，与其他 Python 程序无异。但请注意：
- 网络错误由你的插件自行处理
- 不要在插件中包含硬编码的凭据
- 尊重用户隐私，不要未经同意上传数据

### Q: 如何在导航栏添加按钮？

**方式一 — 侧边导航栏（插件动态按钮）**：在 `on_enable()` 中调用 `api.register_nav_button()`，按钮自动注入到侧边导航栏的插件区（支持 emoji 或 .svg/.png 图标文件）：

```python
def on_enable():
    api = get_api()
    # 使用 emoji 文字
    api.register_nav_button(
        side="right", emoji="⏱", label="计时",
        tooltip="打开计时器", callback=show_my_ui
    )
    # 或使用 SVG 图标文件（存放在 plugins/你的插件/icon/ 目录下）
    api.register_nav_button(
        side="right", emoji="⏱",
        icon="timer.svg",                    # ★ 图标文件
        label="计时",
        tooltip="打开计时器",
        callback=show_my_ui,
    )
```

**方式二 — 顶部导航栏（插件按钮）**：调用 `api.register_top_nav_button()` 在顶部菜单栏添加文本按钮：

```python
def on_enable():
    api = get_api()
    api.register_top_nav_button(
        text="📊 统计", tooltip="查看统计",
        callback=show_stats,
    )
```

**方式三 — 顶部菜单子项（插件子菜单）**：调用 `api.register_top_nav_sub_menu()` 在已有菜单下添加选项：

```python
def on_enable():
    api = get_api()
    api.register_top_nav_sub_menu(
        parent_menu_id="file_menu",
        text="📤 导出报告", callback=export_report,
    )
```

**方式四（主体功能按钮——永久）**：编辑 `config/nav_registry.json`（侧边栏）或 `config/menu_main_window.json`（顶部栏），添加条目后重启生效：

```json
// 侧边栏 nav_registry.json:
{"id": "my_feature", "type": "button", "text": "🆕",
 "label": "新功能", "tooltip": "描述",
 "section": "middle", "position": 8, "enabled": true}

// 顶部栏 menu_main_window.json (right_area):
{"id": "new_btn", "type": "button", "text": "🚀 快速",
 "tooltip": "快速操作", "section": "right_area", "position": 9, "callback": "_on_quick"}
```

> 📌 **区别**：方式一/二/三适合插件动态按钮（随插件开关自动增删），方式四适合需要永久固定的主体功能按钮。

### Q: 插件文件夹已存在但没有显示在列表中？

如果插件文件夹已手动放入 `plugins/` 目录但未注册，点击 `📦 安装插件` → 选择该文件夹或 `.stp` 文件，系统会自动注册并启用。

### Q: 如何为插件添加设置页面？

**推荐方式**：在插件文件夹中创建 `settings.py` 文件，定义 `PAGE_INFO`、`build_page`、`collect_config` 即可。系统在 ⚙️ 设置对话框打开时自动扫描所有已启用插件的 `settings.py` 并展示。

**兼容方式**：在 `on_enable()` 中调用 `api.register_settings_page()`：

```python
def on_enable():
    api = get_api()
    api.register_settings_page(
        meta={"name": "我的插件", "icon": "🔌", "order": 200},
        create_widget_fn=build_my_page,
        collect_config_fn=collect_my_config,
    )
```

详见 [2.3 settings.py 设置页规范](#23-settingspy-设置页规范) 和 [4.11 设置页注册](#411-设置页注册)。

### Q: 如何调试插件中的 API 调用？

StarDebate v1.9.0 起内置了**调试模式监视**功能。打开调试台（标题栏 帮助 ▼ → 🔧 调试台），点击标题栏「调试 ▼」→「⚙ 调试模式设置...」，可开启以下监视：

| 监视项 | 记录内容 | 日志标签 |
|--------|---------|---------|
| API 监视 | 所有 HTTP API 请求的端点、状态码、耗时 | `[API]` |
| 插件监视 | 插件加载成功/失败/启用/禁用 | `[PLUGIN]` |
| AI 监视 | AI 功能的业务结果和错误 | `[AI]` |
| 函数监视 | def 函数的运行结果和异常 | `[FUNC]` |
| 变量监视 | 变量赋值操作的值变化 | `[VAR]` |

> **提示**：插件通过 `api.call_ai()` 发起的 AI 请求会自动被 API 监视捕获并记录（通过 `monitored_api_post` 自动拦截）。详细插入规范见 [§4.17 监视钩子插入细则](#417-监视钩子插入细则v250-新增)。

---

使用 `api.call_ai()` 方法，使用与 StarDebate 相同的 API 配置：

```python
result = api.call_ai(
    messages=[{"role": "user", "content": "分析这个辩题..."}],
    system_prompt="你是辩论专家",
    max_tokens=2048
)
```

---

## 附录：API 速查表

```python
from workers.plugin_manager import get_api
api = get_api()

# ── 基本信息 ──
api.get_app_version()          # -> str
api.get_current_project_path() # -> str | None

# ── 辩论数据（只读） ──
api.get_debate_info()          # -> dict
api.get_speech_content(side)   # -> str   (side="pro"|"con")
api.get_analysis_result(side)  # -> dict
api.get_ref_doc_data(side)     # -> list
api.query_ref_doc_cells(rows, cols)  # -> dict  (v1.4.0 🆕)
api.search_ref_doc(keyword, cols, case_sensitive)  # -> list  (v1.4.0 🆕)
api.get_notes()                # -> list

# ── 框架/结构 ──
api.get_framework_data()            # -> list
api.get_speech_framework_params(side="pro")  # -> dict  (v1.7.0 🆕)
api.get_structure_data()            # -> dict
api.get_keywords(side)              # -> list

# ── API 配置 ──
api.get_api_config()           # -> dict  (Key 已屏蔽)

# ── UI 操作 ──
api.update_status(message)     # 更新状态栏
api.show_notification(title, msg)  # 弹窗通知
api.navigate_to_page(index)    # 切换页面 (0-8)

# ── 文件操作 ──
api.read_file_in_project(path)      # -> str | None
api.write_file_in_project(path, content)  # -> bool

# ── AI 调用 ──
api.call_ai(messages, **kwargs)     # -> str  核心能力！

# ── 导航按钮（侧边栏）──
api.register_nav_button(side, emoji, label, tooltip, callback, icon="")
#   icon="timer.svg"  → 图标文件，自动从 plugins/插件名/icon/ 查找

# ── 顶部导航栏按钮（v2.2.0 🆕）──
api.register_top_nav_button(text, tooltip, callback, btn_id="", emoji="")
api.register_top_nav_sub_menu(parent_menu_id, text, callback, sub_id="")

# ── 面板注册（v1.2.0）──
api.register_panel(side, title, emoji, tooltip, create_widget, icon="")
#   icon="panel.svg"  → 图标文件，自动从 plugins/插件名/icon/ 查找

# ── 设置页注册（v1.3.0）──
api.register_settings_page(meta, create_widget_fn=None, collect_config_fn=None)

# ── 训练子功能注册（v1.5.0）──
api.register_training_sub_feature(info, manager_class)

# ── 控制台命令执行 + 监视日志 + 自定义命令（v2.3.0/v2.5.0 🆕）──
api.execute_command(cmd_line)                      # -> dict  {success, output, error}
api.log_monitor(monitor_type, message)             # 插入监视日志（独立进程写入，三层容灾）
api.register_console_command(cmd_name, handler_fn, args_desc, description, category)

# ── 监视钩子五类型 ──
# variable_watch → [VAR] 变量变化   function_watch → [FUNC] 函数结果（v4.4.0 插件自动注入）
# plugin_watch   → [PLUGIN] 插件状态 api_watch      → [API]  HTTP请求
# ai_watch       → [AI]   AI结果

# ── 起居注 (ActivityChronicle, v2.6.0 🆕) ──
# 自动记录: 插件加载/卸载 | API调用 | AI调用 | 功能运行
# 标签: [CRON]  |  配置: config/chronicle_config.json
# 日志: [CRON] ✅ feature·xxx → ok (ms)  /  [CRON] ❌ xxx → failed (ms): detail
# 完整文档: docs/log/起居注说明.md

# ── 资料池 API（v4.0.0 🆕）──
api.pool_is_ready()                          # -> bool
api.search_pool(keyword, sources, limit)     # -> list[dict]  本地+AI混合搜索
api.search_local(keyword, sources, limit)    # -> list[dict]  纯本地搜索(<100ms)
api.get_search_history(limit)                # -> list[dict]  搜索历史
api.import_file(source_path)                 # -> dict   导入文件 {success,error,info}

# ── 一辩稿索引与来源绑定（v4.7.0 🆕）──
# 数据结构: custom_glossary[term] = {"explanation": str, "sources": [...]}
# 右键菜单: "🔗 为「...」绑定资料/便签作为来源"  → 弹出 BindSourceDialog
# 悬浮卡片: 鼠标悬停已绑定索引词 300ms → HoverCard（400px x 900px 最大）
# 管理器方法:
mgr._bind_source_for_term(word, side)        # 弹窗绑定来源
mgr._on_hover_requested(term, start, end, pos) # 悬浮卡片显示
mgr._open_source_preview(source)             # 弹出来源内容预览窗口
# 高亮: accent 色 + 加粗 + has_material.svg 图标（paintEvent 绘制）
# 旧数据迁移: _maybe_migrate_glossary(side) — 自动检测弹窗迁移
api.list_files(recursive)                    # -> list[dict]  文件列表
api.get_file_content(relative_path)          # -> str|None     文件文本内容
api.delete_file(relative_path)               # -> dict   删除文件 {success,error}
api.get_pool_size()                          # -> dict   统计 {count,size,types}
api.summarize_document(relative_path)        # -> dict   AI摘要 {success,summary,points}
api.ai_search(pool_results)                  # -> list   AI精排搜索结果
api.get_ai_analysis_status()                 # -> dict   AI状态 {running,progress}
api.export_summary(results, format)          # -> dict   导出汇总 {success,path}
api.export_to_stardebate(path, results)      # -> dict   打包到加密文件
api.rebuild_index()                          # -> dict   重建搜索索引
api.get_index_status()                       # -> dict   索引状态
api.get_pool_info()                          # -> dict   资料池信息 {name,path,count}
api.is_pool_open()                           # -> bool  资料池是否打开
api.get_supported_extensions()               # -> list  支持的文件类型

# ── 权限查询（v4.5.0 🆕）──
api.get_permissions()                         # -> list  当前插件声明的权限
api.get_all_permission_defs()                 # -> dict  所有可用权限定义

# ── 自定义多选框（v2.4.0 🆕）──
api.create_checkbox(text, checked, checkbox_size, object_name)  # -> StarCheckBox 控件

# ── 自定义按钮（v1.0.0 🆕）──
api.create_button(text, icon, layout_mode, ratio_h, ...)  # -> StarButton 控件

# ── 事件钩子 ──
api.on(event, callback)        # 注册事件
api.off(event, callback)       # 取消事件

# ── 生命周期 ──
def on_enable(): ...           # 启用时调用（可选）
def on_disable(): ...          # 禁用时调用（可选）
```

---

## 附录二：模拟训练子功能注册机制（v2.0）

模拟训练面板内部采用 **自动发现 + 注册** 机制管理子功能模块。

### 架构概览

```
workers/training/
├── __init__.py              # 注册表 + discover_sub_features() 自动扫描
├── training_manager.py      # 面板框架 + 入口页自动排版 + 子功能委托
├── quick_quiz/              # 子功能 1：快速刷题
│   ├── __init__.py          # SUB_FEATURE_INFO 元信息
│   └── quick_quiz_manager.py
└── exercise/                # 子功能 2：立论驳论
    ├── __init__.py          # SUB_FEATURE_INFO 元信息
    └── exercise_manager.py
```

### 子功能定义规范

每个子功能文件夹的 `__init__.py` 必须定义以下内容：

```python
# workers/training/<your_feature>/__init__.py

SUB_FEATURE_INFO = {
    "id": "my_feature",                    # 唯一标识
    "name": "功能名称",                     # 入口卡片标题
    "icon": "🔧",                          # 卡片图标
    "accent_color": "#f9e2af",             # 标题颜色（CSS 颜色）
    "description": "功能简述",              # 卡片描述
    "tags": ["标签1", "标签2"],             # 特性标签（可选）
    "order": 30,                           # 排序（越小越靠前，留间隔方便插入）
    "history_label": "📂 记录",            # 标题栏历史按钮文字（可选）
}

def get_manager_class():
    """返回子功能管理器类"""
    from .my_feature_manager import MyFeatureManager
    return MyFeatureManager
```

### 管理器类规范

```python
class MyFeatureManager:
    def __init__(self, train_mgr):
        """
        train_mgr: TrainingManager 实例
        可通过 train_mgr._mw 访问主窗口
        可通过 train_mgr._train_stack 访问 QStackedWidget
        """
        self._tm = train_mgr
        self._mw = train_mgr._mw

    def build_pages(self, parent_stack: QStackedWidget) -> int:
        """在 parent_stack 中构建子功能页面，返回起始索引"""
        # 使用 parent_stack.addWidget(page) 添加页面
        start_idx = parent_stack.count()
        # ... 构建 UI ...
        return start_idx

    def show_history(self):
        """显示历史记录（可选）"""
        pass
```

### 自动发现 API

```python
from workers.training import discover_sub_features
from workers.training import get_sub_features
from workers.training import get_sub_feature

# 扫描所有子功能目录
features = discover_sub_features()  # -> {id: {info, get_manager, module_path}}

# 获取排序后的信息列表
for info in get_sub_features():
    print(info["name"], info["order"])

# 按 id 获取单个子功能
f = get_sub_feature("quick_quiz")
```

系统启动时，`TrainingManager.build_panel()` 自动调用 `discover_sub_features()`，扫描 `workers/training/` 下所有子目录，发现 `SUB_FEATURE_INFO` 后：
1. 动态生成入口页面卡片
2. 动态生成标题栏历史按钮
3. 实例化对应的管理器并构建子页面

### 新增子功能流程

只需两步，无需修改 TrainingManager：

1. 创建 `workers/training/<新功能>/` 文件夹
2. 编写 `__init__.py`（定义 `SUB_FEATURE_INFO` + `get_manager_class()`）
3. 编写管理器类（实现 `build_pages(stack)`）

---

## §5 .stardebate 文件格式 (v2.4.0)

### 5.1 概述

`.stardebate` 是 StarDebate 专属的加密辩论文件格式，支持将所有辩论赛参数（基本信息、一辩稿、资料稿、AI分析、框架、质询、接质、便签、结构、训练记录）打包为单一加密文件。

**核心特性**：
- **双层 AES-256-GCM 加密**：第1层内置密钥（仅 StarDebate 可读）+ 第2层用户密码（可选）
- **乱码显示**：其他软件打开时显示为不可辨认的二进制乱码
- **防篡改**：GCM 认证标签确保数据完整性
- **跨会话兼容**：所有 StarDebate 版本可互认

### 5.2 文件结构

```
.stardebate 文件二进制格式 v1:
┌──────────────────────────────────────────────────┐
│ 字节 0-3:   MAGIC (XOR 0x5A) → 记事本显示乱码    │
│ 字节 4-5:   version uint16 BE (= 1)              │
│ 字节 6-7:   flags uint16 BE                      │
│             bit0: has_password                    │
│             bit1: is_compressed                   │
│ 字节 8-23:  password_salt (16B, 无密码时全0)      │
│ 字节 24-35: primary_nonce (12B)                   │
│ 字节 36-..: primary_ciphertext (AES-256-GCM)      │
│ 末尾 16B:   primary_auth_tag                      │
└──────────────────────────────────────────────────┘

primary_ciphertext 解密后:
  IF no password → 直接为 JSON 数据 (zlib压缩)
  IF has password → secondary_nonce(12) + secondary_encrypted
                     → 密码解密后为 JSON 数据
```

### 5.3 加密算法

| 层级 | 算法 | 密钥来源 | 是否可选 |
|------|------|----------|----------|
| 第1层 | AES-256-GCM | PBKDF2("StarDebate" + 内置盐, 100000轮) | 必须（自动） |
| 第2层 | AES-256-GCM | PBKDF2(用户密码, password_salt, 100000轮) | 可选 |
| 压缩 | zlib level 6 | — | 是 |

### 5.4 模块ID列表

导出的模块数据映射：

| module_id | 名称 | 数据来源 |
|-----------|------|----------|
| basic | 辩论基本信息 | current_debate_data |
| speech_pro | 正方一辩稿 | speech_pro.json |
| speech_con | 反方一辩稿 | speech_con.json |
| ref_doc_pro | 正方资料稿 | ref_doc_mgr rows |
| ref_doc_con | 反方资料稿 | ref_doc_mgr rows |
| analysis_pro | 正方AI分析 | analysis files |
| analysis_con | 反方AI分析 | analysis files |
| framework | 辩论框架 | framework_mgr.data |
| cross_exam | 模拟质询 | cross_exam.json |
| accept_exam_pro | 正方接质 | accept_exam files |
| accept_exam_con | 反方接质 | accept_exam files |
| notes | 便签数据 | sticky_notes.json |
| structure | 结构树 | structure_mgr data |
| training | 训练记录 | train_*.json |

### 5.5 插件集成 API

插件可通过以下方式访问 .stardebate 编译器：

```python
# 导入编译器
from workers.stardebate_format import StardebateCompiler

# 检测文件是否是 .stardebate 格式
compiler = StardebateCompiler()
data = open("file.stardebate", "rb").read()
if compiler.verify_magic(data):
    info = compiler.get_file_info(data)
    print(f"版本: {info['version']}, 有密码: {info['has_password']}")
```

### 5.6 入口

- **导出**: 文件菜单 → 📦 导出 .stardebate
- **导入**: 文件菜单 → 📥 导入 .stardebate
- **依赖**: `pip install cryptography`

---

## §6 .stardebate 编辑器 API (v2.7.0)

### 6.1 概述

插件可通过 `PluginSafeAPI` 访问 .stardebate 文件的编辑器功能：打开加密文件、只读查询模块数据、密码管理、保存操作。

所有 `get_*`/`list_*` 方法返回深拷贝，插件无法污染内存数据。密码 API 不暴露明文，仅返回状态 bool。

### 6.2 API 速查表

| 方法 | 返回 | 说明 |
|------|------|------|
| `STDB_MODULE_IDS` | dict | 模块注册表常量（只读） |
| `get_stdb_module_label(id)` | str | 模块中文名称 |
| `open_stdb_file(path, pwd)` | dict | 打开文件（解密到内存） |
| `close_stdb_file(path, save)` | dict | 关闭文件 |
| `save_stdb_file(path, pwd)` | dict | 加密保存到磁盘 |
| `list_stdb_open_files()` | list[str] | 所有已打开文件路径 |
| `get_stdb_file_info(path)` | dict | 文件元信息 |
| `list_stdb_module_ids(path)` | list[str] | 文件内所有模块 ID |
| `get_stdb_module_data(path, id)` | dict\|None | 模块数据（深拷贝） |
| `is_stdb_file_dirty(path)` | bool | 是否有未保存修改 |
| `get_stdb_password_status(path)` | dict | 密码状态（无明文） |
| `change_stdb_password(path, old, new)` | dict | 修改/移除密码 |

### 6.3 使用示例

```python
api = get_api()

# ── 打开文件 ──
result = api.open_stdb_file("C:/debates/辩论.stardebate", password="secret")
if result["success"]:
    print(f"已加载 {result['meta']['module_count']} 个模块")

# ── 只读查询 ──
files = api.list_stdb_open_files()           # ["C:/.../辩论.stardebate"]
info = api.get_stdb_file_info(files[0])       # {uuid, module_count, dirty_modules, ...}
ids  = api.list_stdb_module_ids(files[0])     # ["basic", "speech_pro", ...]
data = api.get_stdb_module_data(files[0], "speech_pro")  # 深拷贝，只读

# ── 模块常量 ──
for mid, (page, label, icon) in api.STDB_MODULE_IDS.items():
    print(f"{icon} {label} → 页面{page}")

# ── 密码管理 ──
status = api.get_stdb_password_status(files[0])
# → {"has_password": True, "is_unlocked": True}
api.change_stdb_password(files[0], "old_pwd", "new_pwd")

# ── 保存/关闭 ──
api.save_stdb_file(files[0])
api.close_stdb_file(files[0], save=True)
```

### 6.4 返回值详解

**`get_stdb_file_info()` 返回结构**：
```python
{
    "path": "C:/.../辩论.stardebate",
    "uuid": "550e8400-e29b-41d4-a716-446655440000",
    "version": 1,
    "has_password": True,
    "module_count": 6,
    "module_ids": ["basic", "speech_pro", "speech_con", ...],
    "dirty_modules": ["speech_pro"],
    "created": 1717700000.0,
    "app_version": "2.3.0",
}
```

**`open_stdb_file()` 返回值**：
```python
{
    "success": True,
    "error": None,
    "meta": {"uuid": str, "module_count": int, "has_password": bool, ...}
}
```

### 6.5 密码安全

- `get_stdb_password_status()` 只返回 `has_password` 和 `is_unlocked` 两个 bool，不暴露明文
- 密码通过 Windows DPAPI 加密存储于 `config/stardebate_index.json`，仅当前用户可解密
- `change_stdb_password()` 需验证旧密码

### 6.6 入口

- **编辑**: 文件菜单 → 📝 编辑 .stardebate
- **面板**: 左侧导航 📦 STDB 按钮 → 模块浏览面板

---

> **文档版本 v2.8.0** | 更新日期 2026-06-07 | StarDebate 插件系统将持续完善。
