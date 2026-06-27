# StarDebate EXE 打包与更新指南

> 版本：v2.0.0 | 适用版本：v6.0.0+
> 适用场景：从源码修复 → 打包 EXE → 生成安装包 → 创建更新补丁

> **v5.x 用户**：旧版（v5.5.0 及以下）请参考 `exe_build_guide_v5.md`

---

## 目录

1. [EXE 版目录结构](#1-exe-版目录结构)
2. [PRE_Packaged 与源码版的差异](#2-pre_packaged-与源码版的差异)
3. [打包流程速查](#3-打包流程速查)
4. [创建更新补丁](#4-创建更新补丁)
5. [常见 PyInstaller 兼容性问题](#5-常见-pyinstaller-兼容性问题)
6. [FAQ](#6-faq)

---

## 1. EXE 版目录结构

### 1.1 分发目录（`Packaged/v5_0_0/`）

最终交付用户的内容：

```
Packaged/v5_0_0/
├── StarDebate.exe                # 主程序入口（约 135 MB）
├── StarDebate/                   # 运行时支持文件夹（约 640 个文件）
│   ├── _internal/                # PyInstaller 内部文件
│   │   ├── config/               # 配置 JSON（17 个）
│   │   ├── icon/                 # SVG 图标（78 个）
│   │   ├── style/                # QSS 样式 + 字体
│   │   └── *.dll / *.pyd         # DLL + Python 扩展
│   └── StarDebate.exe            # 内部引导器
├── StarDebate.ico                # 应用图标
├── StarDebate_Setup.iss          # Inno Setup 脚本（可选）
└── StarDebate_v5.5.0_Setup.exe   # 安装包（约 358 MB，可选）
```

**关键路径（运行时）：**

| 变量 | 值（示例） | 说明 |
|------|-----------|------|
| `sys._MEIPASS` | `...\Packaged\v5_0_0\StarDebate\_internal` | 数据文件根目录 |
| 启动后 CWD | `sys._MEIPASS`（`StarDebate.py` 中 `os.chdir` 设置） | 所有相对路径以此为基准 |

### 1.2 v6.0.0+ 架构（极简引导器 + 外部源码）

从 v6.0.0 开始，EXE 版采用「极简 PyInstaller 引导器 + 外部源码」架构，
所有 `.py` 文件保持纯文本形式位于 `src/` 目录，支持热更新。

```
Packaged/v6_0_0/
├── StarDebate.exe            # 极简 PyInstaller 引导器（约 40-50 MB）
│                              # 仅包含: Python 解释器 + PyQt5 DLL + 标准库
├── _internal/                 # PyInstaller bundle
│   ├── python3xx.dll
│   ├── PyQt5/*.pyd
│   └── base_library.zip
│
├── src/                      # ★ 全部 StarDebate 源码（纯 .py 文件）
│   ├── StarDebate.py         # 主程序入口（main_loop）
│   ├── StarDebate_app.py     # 主窗口
│   ├── star_debate_log.py    # 日志独立进程
│   ├── workers/...           # 功能模块
│   └── components/...        # UI 组件
│
├── config/                   # 持久化配置（17 个 JSON）
├── icon/                     # SVG 图标（78 个）
└── style/                    # QSS 主题 + 字体（69 个文件）
```

**运行时路径解析：**

| 变量 | 值 | 说明 |
|------|-----|------|
| `sys.executable` | `...\Packaged\v6_0_0\StarDebate.exe` | EXE 路径 |
| `sys.path[0]` | `...\Packaged\v6_0_0\src` | 源码目录（由 boot.py 插入） |
| `get_config_base_dir()` | `...\Packaged\v6_0_0` | 持久化配置基目录 |
| `sys._MEIPASS` | `...\Packaged\v6_0_0\_internal` | PyInstaller 解压目录 |

**关键差异（vs v5.x）：**

| 特性 | v5.x | v6.0.0+ |
|------|------|---------|
| 源码形式 | 编译进 PYZ | 纯 `.py` 文件（`src/`） |
| 配置文件 | 初始在 `_internal/config/` | 初始在 `exe同级/config/` |
| 资源文件 | 打包进 `_internal/` | 外置到 `exe同级/` |
| 热更新支持 | 仅 config/*.json | **全部 .py + config/*.json** |
| EXE 体积 | ~135 MB | ~45 MB（预计） |

### 1.3 源码打包目录（`PRE_Packaged/v6_0_0/`）

```
PRE_Packaged/v6_0_0/
├── boot.py                   # ★ PyInstaller 入口（唯一编译进 EXE 的 .py）
├── build.spec                # 最小化打包配置（排除所有 StarDebate 模块）
├── StarDebate.ico            # 应用图标
├── src/                      # 全部源码（构建时复制到分发目录）
│   ├── StarDebate.py
│   ├── StarDebate_app.py
│   ├── star_debate_log.py
│   ├── workers/...
│   └── components/...
├── config/                   # 默认配置（清空敏感数据）
├── icon/                     # SVG 图标
└── style/                    # QSS 主题 + 字体
```

### 1.4 旧版源码打包目录（`PRE_Packaged/v5_0_0/`）

```
PRE_Packaged/v5_0_0/
├── StarDebate.py                 # 启动入口（含 os.chdir sys._MEIPASS）
├── StarDebate_app.py             # 主窗口
├── star_debate_log.py            # 日志独立进程
├── build.spec                    # PyInstaller 配置（hidden imports + datas）
├── StarDebate.ico                # 应用图标（由 main.png 生成，多尺寸 16×16 ~ 256×256）
├── config/                       # 配置文件（api_key 已清空）
├── components/                   # UI 组件
├── icon/                         # SVG 图标
├── style/                        # QSS 主题 + HarmonyOS 字体
└── workers/                      # 功能模块（debug_console 已剔除）
    ├── log_core/                 # 精简版日志核心（原 debug_console 保留部分）
    ├── plugin_manager/           # 插件运行 API（保留）
    └── ...
```

---

## 2. PRE_Packaged 与源码版的差异

### 2.1 剔除的内容

| 内容 | 原因 |
|------|------|
| `workers/debug_console/` | 开发者调试功能，普通用户不需要 |
| `plugins/`（内置插件本体） | 用户可按需通过 `.stp` 安装 |
| `docs/` | 开发者文档 |
| `tools/` | 开发者工具（gen_version_patch, pack_stp 等） |
| `plugin_manager/`（根目录） | 独立的插件开发管理工具 |
| `custom_formats/` | 用户自定义赛制格式（空/示例） |
| `backups/`, `_update_staging/`, `exercise_sessions/` | 运行时数据 |
| `web/` | HTML 展示页 |
| `HarmonyOS_Sans/`, `HarmonyOS_SansTC/` | 仅保留 `HarmonyOS_SansSC`（简中） |
| `__pycache__/`, `*.pyc` | 字节码缓存 |

### 2.2 修改的内容

| 文件 | 修改 | 原因 |
|------|------|------|
| `StarDebate.py` | 开头 `os.chdir(sys._MEIPASS)` | 修复 PyInstaller 下相对路径找不到的问题 |
| `StarDebate_app.py` | `DebugMonitorManager` 导入改为 try/except | `debug_monitor_manager` 已移入 `log_core/` |
| `star_debate_log.py` | `debug_console` → `log_core` 导入路径 | 模块重组 |
| `workers/log_core/` | 从 `debug_console` 复制的必需文件 | `log_manager.py`, `debug_monitor_manager.py`, `chronicle/`, `native/` |
| `workers/star_debate/glue.py` | `DebugConsoleWindow` 导入加 try/except | 调试台已禁用 |
| `workers/training/__init__.py` | `os.listdir` 加 try/except 回退 `pkgutil` | PyInstaller 无法扫描目录 |
| `workers/settings/settings_page_base.py` | `scan_builtin_pages` 加 pkgutil 回退；`load_module` 支持模块路径 | PyInstaller 兼容 |
| `workers/plugin_manager/__init__.py` | 3 处 `os.listdir` 加 `os.path.isdir` 守卫 | 防止 `FileNotFoundError` |
| `config/api_config.json` | `api_key` 清空 | 保护隐私 |
| `config/installed_plugins.json` | 清空（无内置插件） | 干净启动 |
| `style/themes/*/theme.json` | 移除 `debug_console.qss` 引用 | 剔除调试控制台样式 |

---

## 3. 打包流程速查

### 3.1 v6.0.0+ 首次打包（极简引导器版）

```powershell
# 1. 进入打包源目录
cd PRE_Packaged/v6_0_0

# 2. 执行 PyInstaller
pyinstaller build.spec --distpath=../../Packaged/v6_0_0 --workpath=../../Packaged/v6_0_0/build

# 3. 复制源码和资源到分发目录
Copy-Item -Recurse src  ../../Packaged/v6_0_0/src
Copy-Item -Recurse icon ../../Packaged/v6_0_0/icon
Copy-Item -Recurse style ../../Packaged/v6_0_0/style
Copy-Item -Recurse config ../../Packaged/v6_0_0/config
Copy-Item StarDebate.ico ../../Packaged/v6_0_0/

# 4. 清除构建缓存（可选）
Remove-Item -Recurse -Force "../../Packaged/v6_0_0/build"

# 输出结构:
# Packaged/v6_0_0/
#   StarDebate.exe     ~45 MB
#   src/               全部 .py 源码
#   config/            JSON 配置
#   icon/              SVG 图标
#   style/             QSS + 字体
```

### 3.2 v5.x 旧版打包（源码编译进 EXE）

```powershell
cd PRE_Packaged/v5_0_0
pyinstaller build.spec --distpath=../../Packaged/v5_0_0 --workpath=../../Packaged/v5_0_0/build
Remove-Item -Recurse -Force "../../Packaged/v5_0_0/build"
```

### 3.3 生成安装包

```powershell
# 确保 Inno Setup 6 已安装
& "C:\Program Files (x86)\Inno Setup 6\iscc.exe" "..\..\Packaged\v5_0_0\StarDebate_Setup.iss"
```

### 3.4 版本号更新

修改 `PRE_Packaged/v5_0_0/config/config.json` 中的 `version` 字段，然后再执行上述打包流程。

---

## 4. 创建更新补丁

### 4.1 补丁适用范围

| 版本类型 | 更新方式 | 说明 |
|----------|----------|------|
| 源码版（运行 `.py`） | ZIP 补丁文件 | 放入项目根目录，启动时自动检测安装 |
| **EXE 版（打包后）** | **重新分发 EXE/安装包** | **PyInstaller 将源码编译进 bundle，无法热替换单个 .py 文件** |

**v5.x 及以下：** EXE 版不支持 `.py` 级别的热更新补丁。所有修改必须重新打包整个 EXE。

**v6.0.0+：** EXE 版支持全部源码热更新（因为源码以纯 `.py` 文件形式位于 `exe同级/src/`）。更新补丁只需包含修改过的 `.py` 文件、`config/*.json` 和资源文件，放入对应目录即可。

### 4.2 EXE 版更新流程

```
发现 Bug 或需要更新
        ↓
1. 在源码版（e:\StarDebate\）中修复
        ↓
2. 将修复同步到 PRE_Packaged/v5_0_0/
        ↓
3. 更新 PRE_Packaged 中 config/config.json 版本号
        ↓
4. 重建 EXE
        ↓
5. （可选）重建安装包
        ↓
6. 将新的 EXE/安装包分发给用户
```

### 4.3 同步修复到 PRE_Packaged

修改源码版后，需要用同样的修改更新 `PRE_Packaged/v5_0_0/` 中对应的文件。通常修改的是：

| 源码路径 | PRE_Packaged 路径 |
|----------|-------------------|
| `workers/settings/settings_page_base.py` | `PRE_Packaged/v5_0_0/workers/settings/settings_page_base.py` |
| `StarDebate.py` | `PRE_Packaged/v5_0_0/StarDebate.py` |

手动复制即可：

```powershell
Copy-Item "workers/settings/settings_page_base.py" "PRE_Packaged/v5_0_0/workers/settings/settings_page_base.py"
```

> **注意：** 如果源码版新增了文件依赖（如导入新的模块），需要在 `build.spec` 的 `HIDDEN_IMPORTS` 列表中添加该模块。

---

## 5. 常见 PyInstaller 兼容性问题

### 5.1 `os.listdir()` 扫描自身目录

**症状：**
```
FileNotFoundError: [WinError 3] 系统找不到指定的路径。: '...workers/training'
```

**原因：** PyInstaller 将所有 `.py` 文件编译为 `.pyc` 并压缩到 PYZ 归档中，实际文件系统上不存在对应目录。`os.listdir()` 找不到目录。

**修复模式：**
```python
# 原代码
for entry in sorted(os.listdir(base_dir)):
    ...

# 修复后
try:
    entries = sorted(os.listdir(base_dir))
except (FileNotFoundError, OSError):
    # PyInstaller 回退：使用 pkgutil/importlib
    import pkgutil
    for _, mod_name, is_pkg in pkgutil.walk_packages(...):
        ...
```

**涉及的模块：**
- `workers/training/__init__.py` — 子功能发现
- `workers/settings/settings_page_base.py` — 设置页面扫描
- `workers/plugin_manager/__init__.py` — 插件目录扫描

### 5.2 `__file__` 推导的路径不可用

**症状：** 各种 `FileNotFoundError`、`AttributeError: 'NoneType'`（按钮为 None 因为配置没加载到）

**原因：** 在 PyInstaller bundle 中，`__file__` 指向 `sys._MEIPASS` 临时目录，而非用户眼中的应用目录。`os.path.dirname(os.path.abspath(__file__))` 推导出的路径可能与数据文件的实际位置不符。

**修复模式（一劳永逸）：**
```python
# 在 StarDebate.py 开头添加
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    os.chdir(sys._MEIPASS)
```
此设置确保所有相对路径（`config/nav_registry.json` 等）以 `sys._MEIPASS` 为基准解析。

### 5.3 模块路径 vs 文件路径

**症状：** 设置页完全空白，`load_module()` 返回 False

**原因：** PyInstaller 下用 `pkgutil` 发现模块时获取的是模块路径（`workers.settings.pages.about_page`），但 `load_module()` 中 `os.path.isfile(module_path)` 判断失败——模块路径不是文件路径。

**修复模式：**
```python
# load_module() 中同时支持两种路径
if os.path.isfile(self.module_path):
    spec = importlib.util.spec_from_file_location(...)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
else:
    mod = importlib.import_module(self.module_path)
```

### 5.4 配置写入持久化目录

**症状：** EXE 版修改配置（主题、API Key 等）后重启恢复默认值。

**原因：** 配置文件的路径通过 `__file__` 推导，在 PyInstaller bundle 中指向 `sys._MEIPASS`（`_internal/` 临时解压目录）。写入的配置在重启后随临时目录销毁。

**修复模式（v5.5.0+）：**

1. **新模块 `workers/app_config/config_paths.py`**：
   - `get_config_path(relative)` — 返回持久化配置文件的完整路径
   - `get_packaged_path(relative)` — 返回打包资源目录路径（`_internal/` 下的只读资源）
   - `ensure_config_dir()` — 首次启动时自动将 `_internal/config/` 的默认配置复制到持久目录

2. **路径分离**：
   - 持久化配置 → `exe同级/config/` (通过 `os.path.dirname(sys.executable)` 计算)
   - 打包资源（样式/字体/图标）→ `_internal/` (通过 `sys._MEIPASS` 计算)

3. **调用时机**：
   - `StarDebate.py` 的 `_start_window()` 中首先调用 `ensure_config_dir()`
   - 所有配置文件读写通过 `get_config_path("config/xxx.json")` 而非 `os.path.join(_PROJECT_ROOT, "config", ...)`

**源码版不受影响**（`__file__` 直接指向项目根目录）。

### 5.5 缺少对象的 `clicked` 属性

**症状：**
```
AttributeError: 'NoneType' object has no attribute 'clicked'
```

**原因：** 导航按钮因配置未加载（见 5.2）全部为 `None`。修复 5.2 即可。

---

## 6. FAQ

### 6.1 修改源码后可以直接更新 EXE 吗？

不能。必须：
1. 修改 `PRE_Packaged/v5_0_0/` 中对应的文件
2. 重新运行 PyInstaller 打包
3. 重新分发 EXE

### 6.2 如何修改 build.spec？

`build.spec` 中需要关注的几个部分：

```python
# 添加新的数据目录：
DATAS_DIRS = [
    ('config', 'config'),
    ('icon', 'icon'),
    ('style', 'style'),
    # 新增目录在此添加
]

# 添加新的隐藏导入（新增模块时）：
HIDDEN_IMPORTS = [
    'PyQt5.QtSvg',
    'workers.new_module',    # ← 新增模块
    ...
]
```

### 6.3 为什么打包后的 EXE 有 135 MB？

- PyQt5 捆绑了大量 DLL 和 Qt 插件（~50 MB）
- NumPy 等科学计算库约 20 MB
- Python 标准库约 20 MB
- 数据文件（icon/style/config）约 5 MB
- 编译后的 Python 字节码约 30 MB
- `upx` 压缩无法进一步缩减 PyQt5 的 `qwindows.dll` 等文件

要进一步缩小体积，可以考虑：
- 排除不用的 PyQt5 插件（translations, imageformats 等）
- 排除 `numpy`（如果 AI 功能依赖可切换到 `onnxruntime` 等轻量方案）

### 6.4 安装包的文件关联在哪里配置？

在 `StarDebate_Setup.iss` 的 `[Registry]` 段：

```iss
; .stardebate 文件关联
Root: HKCR; Subkey: ".stardebate"; ...
Root: HKCR; Subkey: "StarDebate.Project"; ...

; .stp 文件关联
Root: HKCR; Subkey: ".stp"; ...
Root: HKCR; Subkey: "StarDebate.Plugin"; ...
```

### 6.5 如何检查新版是否修复了问题？

1. 运行 `StarDebate.exe`
2. 确认能正常显示欢迎页（导航栏/按钮正常）
3. 点击设置齿轮图标，确认设置页能正常打开和切换
4. 如果仍有问题，检查 `docs/log/debug_*.log` 中是否有异常堆栈
