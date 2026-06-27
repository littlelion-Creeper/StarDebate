# StarDebate ★ 插件项目管理器

用于创建、编辑和管理 StarDebate 插件项目，并一键打包为 `.stp` 格式。

## 快速开始

```bash
# GUI 方式：启动管理器
python plugin_manager/main.py

# CLI 方式：使用命令行打包脚本（无 GUI）
python tools/pack_stp.py plugins/quick_notes -o quick_notes.stp
```

## 功能

| 功能 | 说明 |
|------|------|
| **新建插件** | 从最小模板创建 `plugin.json` + `main.py` |
| **编辑元数据** | 表单编辑名称/ID/版本/作者/权限/标签/依赖 |
| **打开 .stp 文件** | 解压 .stp 到临时目录后编辑，移除时自动清理 |
| **打开已有插件** | 导入现有插件目录 |
| **一键打包** | 自动校验 + 计算 SHA256 + 生成 `.stp` |

## 打包流程

1. 填写插件元数据 → 点击「保存」
2. 点击「📦 打包为 .stp」
3. 选择输出位置
4. 生成的 `.stp` 文件可通过 StarDebate 的拖拽或「📦 安装插件」按钮安装

## 项目结构

```
plugin_manager/
├── main.py                    # 入口（PyQt5/PySide6）
├── README.md
├── core/
│   ├── stp_packager.py        # 打包逻辑（校验和 + Zip 注释）
│   └── template.py            # 插件模板生成
├── ui/
│   ├── main_window.py         # 主窗口（双栏布局）
│   ├── project_list.py        # 左侧项目列表
│   └── metadata_editor.py     # 右侧元数据编辑器
└── templates/
    └── default/               # 默认模板
        ├── plugin.json.tpl
        └── main.py.tpl
```

## 依赖

- Python 3.10+
- PyQt5 或 PySide6
