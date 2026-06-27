# StarDebate ★ 辩之星

> 一款基于 PyQt5 的辩论辅助与训练桌面应用，集成 AI 分析、质询训练、立论写作、资料池管理等功能。

## 功能概览

- **AI 辩论分析** — 调用 DeepSeek API 对辩题进行多角度分析（正方/反方）
- **接质训练** — 模拟质询环节，AI 扮演对方辩友进行交互式训练
- **立论写作助手** — AI 辅助撰写一辩稿、结辩稿等辩论稿件
- **资料池管理** — 导入 PDF/Word/Excel/HTML 文档，AI 自动摘要
- **框架编辑器** — 自定义辩论框架与论点结构
- **计时与赛事** — 辩论计时器与小型赛事管理
- **模块化插件系统** — 支持功能插件的加载与卸载

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/YOUR_USERNAME/StarDebate.git
cd StarDebate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API
#    将 config/config.example.json 复制为 config/config.json
#    将 config/api_config.example.json 复制为 config/api_config.json
#    在 api_config.json 中填入你的 DeepSeek API Key

# 4. 启动
python StarDebate.py
```

## 项目结构

```
StarDebate/
├── StarDebate.py            # 入口文件
├── StarDebate_app.py        # 主应用窗口
├── star_debate_log.py       # 日志系统
├── components/              # 通用 UI 组件
│   └── siui/                # 自研 PyQt5 UI 库（SiliconUI）
├── workers/                 # 功能模块（按功能分文件夹）
│   ├── ai_analysis/         # AI 辩论分析
│   ├── cross_examination/   # 质询练习
│   ├── speech_writer/       # 立论写作
│   ├── material_pool/       # 资料池管理
│   ├── training/            # 训练模块
│   ├── settings/            # 设置页
│   ├── extension_manager/   # 扩展管理器
│   └── welcome_guide/       # 初次引导页
├── plugins/                 # 功能插件
├── style/                   # QSS 样式（模板+主题）
│   ├── qss_templates/       # @key@ 占位符模板
│   └── themes/              # 主题定义（theme.json）
├── icon/                    # SVG 图标
├── config/                  # 用户配置（已 gitignore）
├── tools/                   # 开发/构建工具
└── docs/                    # 开发文档
```

## 技术栈

| 层 | 技术 |
|----|------|
| GUI 框架 | PyQt5 |
| UI 组件 | 自研 SiliconUI（基于 PyQt5） |
| AI | DeepSeek API（兼容 OpenAI 格式） |
| 文档解析 | pdfplumber, python-docx, openpyxl, beautifulsoup4 |
| 加密 | cryptography (Fernet / AES-256-GCM) |
| 样式 | QSS 模板 + Catppuccin 主题 |

## 许可

本项目源码仅供学习和个人使用。
