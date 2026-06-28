# StarDebate 主题开发文档

> 版本：v2.0 | 更新时间：2026-06-08

---

## 目录

1. [概述](#1-概述)
2. [主题文件结构](#2-主题文件结构)
   - [2.1 源码目录（QSS 模板）](#21-源码目录qss-模板)
   - [2.2 主题配色目录](#22-主题配色目录)
3. [theme.json 规范](#3-themejson-规范)
4. [QSS 文件规范](#4-qss-文件规范)
   - [4.1 QSS 文件清单](#41-qss-文件清单)
   - [4.2 objectName 规范](#42-objectname-规范)
   - [4.3 qproperty 动态属性](#43-qproperty-动态属性)
   - [4.4 标题栏按钮颜色](#44-标题栏按钮颜色)
5. [颜色体系](#5-颜色体系)
   - [5.1 语义色值](#51-语义色值)
   - [5.2 三主题配色对照表](#52-三主题配色对照表)
6. [快速创建主题](#6-快速创建主题)
   - [6.1 从现有主题复制](#61-从现有主题复制)
   - [6.2 批量颜色替换脚本](#62-批量颜色替换脚本)
   - [6.3 多主题维护策略](#63-多主题维护策略)
   - [6.4 验证与测试](#64-验证与测试)
   - [6.5 颜色键引用地图工具](#65-颜色键引用地图工具)
7. [主题加载机制](#7-主题加载机制)
8. [SVG 渲染器主题适配](#8-svg-渲染器主题适配)
9. [设置页预览卡片](#9-设置页预览卡片)
10. [常见问题](#10-常见问题)

---

## 1. 概述

StarDebate 主题系统基于 **QSS（Qt Style Sheets）** 实现，每个主题是一个独立的文件夹，包含一个 `theme.json` 元信息文件和若干 `.qss` 样式文件。支持深色/浅色主题无缝切换，切换后即时生效无需重启。

**核心特性：**
- 每个主题完全独立，**28 个 QSS 文件**按功能模块拆分
- `theme.json` 定义主题名、类型、配色表、QSS 文件列表、SVG 渲染方案
- `pyqtProperty` + `qproperty-*` 机制让 Python 控件绘制颜色也可由 QSS 控制
- 设置页「外观」自动扫描发现主题，卡片预览，一键切换
- SVG 图标随主题自动变色

---

## 2. 主题文件结构

### 2.1 源码目录（QSS 模板）

```
style/
├── qss_templates/                   # ★ QSS 模板源码目录（含 @key@ 占位符）
│   ├── main.qss                     # 主窗口全局样式（QMainWindow, QScrollBar, QToolTip 等）
│   ├── title_bar.qss                # 自定义标题栏样式 + 窗口控制按钮颜色 + 顶部导航
│   ├── nav_bar.qss                  # 左右侧边导航栏
│   ├── structure.qss                # 结构树面板
│   ├── settings.qss                 # 设置对话框
│   ├── ref_doc.qss                  # 资料稿卡 + 导入对话框
│   ├── speech_editor.qss            # 一辩稿编辑器 + 关键词卡片 + 右键菜单
│   ├── tournament.qss               # 赛程管理（赛制浏览/编辑/指定）
│   ├── framework.qss                # 辩论框架（思维导图）
│   ├── speech_writer.qss            # AI 写稿面板
│   ├── ai_expand.qss                # AI 扩写面板 + 历史任务卡片
│   ├── notes.qss                    # 便签面板
│   ├── training.qss                 # 模拟训练 + 快速刷题 + 立论驳论
│   ├── ai_analysis.qss              # AI 分析报告页
│   ├── cross_examination.qss        # 模拟质询 + 接质聊天
│   ├── new_debate.qss               # 新建辩论对话框
│   ├── debug_console.qss            # 调试控制台窗口
│   ├── suggest_popup.qss            # 命令补全悬浮框
│   ├── crash_monitor.qss            # 崩溃监控面板
│   ├── popup_dialog.qss             # 自定义提示弹窗（CustomDialog）
│   ├── stardebate_format.qss        # .stardebate 导入/导出对话框 + 模块面板
│   ├── stardebate_editor.qss        # .stardebate 编辑器面板
│   ├── star_checkbox.qss            # 自定义多选框组件
│   ├── star_spinbox.qss             # 自定义数字输入框组件
│   ├── log_settings.qss             # 日志设置面板
│   ├── plugins.qss                  # 插件通用 UI + 插件管理面板
│   ├── svg_renderer.qss             # SVG 渲染器设置页
│   ├── material_pool.qss            # 资料池面板 + MD查看器 + 详情页
│   ├── shadow_container.qss         # 阴影容器样式
│   ├── bind_source_dialog.qss       # 绑定源对话框
│   └── welcome_guide.qss            # 引导页样式
```

### 2.2 主题配色目录（仅 theme.json）

```
style/themes/
└── <theme_id>/                   # 主题目录名即主题 ID（英文，建议 snake_case）
    └── theme.json                # ★ 必需：主题元信息 + 配色表 + SVG 渲染配置
```

> **核心变化**：`qss_templates/` 是唯一的 QSS 源码。各主题目录只保留 `theme.json`（定义 colors）。运行时 `apply_style()` 读取模板 → 将 `@key@` 替换为对应主题色值 → 合成完整 QSS 字符串。旧硬编码 `.qss` 文件已全部删除，不再需要。

---

## 3. theme.json 规范

```json
{
    "name": "主题显示名称",
    "version": "1.0.0",
    "author": "作者",
    "description": "主题简短描述",
    "type": "dark | light",
    "icon_scheme": "white | black",

    "qss_files": [
        "main.qss", "title_bar.qss", "nav_bar.qss",
        "structure.qss", "settings.qss", "ref_doc.qss",
        "speech_editor.qss", "tournament.qss", "framework.qss",
        "speech_writer.qss", "ai_expand.qss", "notes.qss",
        "training.qss", "ai_analysis.qss", "cross_examination.qss",
        "new_debate.qss", "debug_console.qss", "suggest_popup.qss",
        "crash_monitor.qss", "popup_dialog.qss", "stardebate_format.qss",
        "stardebate_editor.qss",
        "star_checkbox.qss", "star_spinbox.qss", "log_settings.qss",
        "plugins.qss", "svg_renderer.qss", "material_pool.qss"
    ],

    "colors": {
        "base": "#1e1e2e",
        "surface": "#181825",
        "overlay": "#313244",
        "text": "#cdd6f4",
        "subtext": "#a6adc8",
        "muted": "#6c7086",
        "accent_green": "#a6e3a1",
        "accent_purple": "#cba6f7",
        "accent_blue": "#89b4fa",
        "accent_pink": "#f5c2e7",
        "accent_yellow": "#f9e2af",
        "accent_red": "#f38ba8"
    },

    "svg_renderer": {
        "mono": { "color": "text" },
        "dual": { "primary": "accent_purple", "accent": "text" }
    }
}
```

### 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | **是** | 主题显示名称，出现在设置页外观卡片上 |
| `version` | string | 否 | 语义化版本号 |
| `author` | string | 否 | 作者名称 |
| `description` | string | 否 | 主题描述文本 |
| `type` | string | **是** | 主题类型：`"dark"`（深色）或 `"light"`（浅色），影响卡片的类型标记 |
| `icon_scheme` | string | **是** | **SVG 图标的色彩方案**：`"white"`（深色主题用白色）或 `"black"`（浅色主题用黑色）。影响窗口控制按钮、导航栏 SVG 图标等通过 `SvgRenderer` 渲染的所有图标。注意：**不**影响标题栏左侧的应用图标（`icon/common/main.png`），那是独立 PNG 图片。
| `qss_files` | string[] | **是** | QSS 文件加载列表，按顺序拼接；文件不存在时静默跳过 |
| `colors` | object | **是** | 12 色配色表，用于设置页预览卡片渲染（见 §5） |
| `svg_renderer` | object | **是** | SVG 图标渲染配置（v2.0 新增）：`mono.color`（单色渲染色键名）、`dual.primary`/`dual.accent`（双色渲染色键名），键名映射到 `colors` 中的 hex 值 |

### `colors` 字段强制要求

`colors` 必须包含以下 12 个键，且值均为有效的 hex 颜色字符串（如 `"#1e1e2e"`）：

```
base, surface, overlay,
text, subtext, muted,
accent_green, accent_purple, accent_blue,
accent_pink, accent_yellow, accent_red
```

缺少任一键将导致外观预览卡片无法正常渲染。

---

## 4. QSS 文件规范

### 4.1 完整 QSS 文件清单（v2.0：28 个文件）

| 文件名 | 负责范围 | 主要选择器 |
|--------|----------|-----------|
| `main.qss` | 主窗口全局 + 通用控件 | `QMainWindow`, `QScrollBar`, `QToolTip`, `QSplitter`, `QTreeWidget`, `QTableWidget`, `QTabWidget`, `QComboBox`, `QLineEdit`, `QTextEdit`, `QPlainTextEdit`, `QListWidget`, `QPushButton`, `QDialog`, `QMessageBox`, `#smallBtn`, `#primaryBtn`, `#treeContextMenu` |
| `title_bar.qss` | 自定义标题栏 + 顶部导航 | `#titleBar`, `#titleIcon`, `#titleDragArea`, `#minBtn`, `#maxBtn`, `#closeBtn`, `#topNavBtn`, `#topNavMenu` |
| `nav_bar.qss` | 左右导航栏 | `#navPanel`, `#navToggleBtn` |
| `structure.qss` | 结构树面板 | `#structurePanel`, `#structSideBtn`, `#aiStructBtn`, `#smallBtn` |
| `settings.qss` | 设置对话框全局 | `#settingsNav`, `#settingsPage`, 导航按钮等 |
| `ref_doc.qss` | 资料稿卡 + 导入对话框 | `#refDocSearch`, `#refCardsScroll`, `#refCardsContainer`, `#refCard`, `#refCardIndex`, `#refCardSection*`, `#refDocImport*` |
| `speech_editor.qss` | 一辩稿编辑器 | `#keywordBar`, `#keywordContainer`, `#keywordCard`, `#cardBtn`, `#addKeywordBtn`, `#speechContextMenu` |
| `tournament.qss` | 赛程管理 | `#formatBrowseTab`, `#formatList`, `#formatDetailScroll`, `#assignNavBtn`, `#assignFormatCombo`, `#assignFormatBtn`, `#assignFormatSaveBtn`, `#positionCard`, `#formatAddBtn` |
| `framework.qss` | 辩论框架（思维导图） | `#frameworkCanvas`, `#fwNode`, `#frameworkPage` |
| `speech_writer.qss` | AI 写稿面板 | `#speechWriterPanel`（复用 aiExpand 系列选择器） |
| `ai_expand.qss` | AI 扩写 + 历史记录 | `#aiExpandPanel`, `#aiExpandHeader`, `#aiExpandResultCard`, `#aiHistoryCard`, `#aiHistoryKeyword`, `#aiHistoryTime`, `#savedFilesList` |
| `notes.qss` | 便签面板 | `#notesPanel`, `#notesHeader`, `#notesScroll`, `#noteCard`, `#noteCardText`, `#noteCardBtn`, `#noteAddBtn`, `#notesInput` |
| `training.qss` | 模拟训练 + 刷题 + 练习 | `#trainingPanel`, `#trainEntryBtn`, `#trainModeBtn`, `#trainDiffBtn`, `#trainOptionBtn`, `#trainResultFrame`, `#scenarioFrame`, `#exerciseTimerFrame`, `#exerciseScoreBlock`, `#trainingCard` |
| `ai_analysis.qss` | AI 分析报告页 | `#analysisPage`, `#analysisTitle`, `#analysisTabs`, `#analysisProScroll`, `#analysisConScroll`, `#analysisMetaCard`, `#analysisCard`, `#analysisCardBody` |
| `cross_examination.qss` | 模拟质询 + 接质 | `#crossExamPage`, `#crossExamScroll`, `#crossExamQuestion`, `#crossExamAnswer`, `#crossExamThinking`, `#acceptChatScroll`, `#acceptMsg*`, `#sideToggleBtn` |
| `new_debate.qss` | 新建辩论对话框 | 表单框架、持方标签、输入框等 |
| `debug_console.qss` | 调试控制台窗口 | 输出区、输入区、工具栏、搜索栏 |
| `suggest_popup.qss` | 命令补全悬浮框 | 补全列表项样式 |
| `crash_monitor.qss` | 崩溃监控面板 | 监控日志列表、状态指示器 |
| `popup_dialog.qss` | 自定义提示弹窗 | `#popupDialog`, `#popupTitleBar`, `#popupMsgLabel`, `#popupCheckbox`, `#popupPrimaryBtn`, `#popupSecondaryBtn` |
| `stardebate_format.qss` | .stardebate 导入/导出 + 模块面板 | `#stdebExportDialog`, `#stdebContentScroll`, `#stdebInfoCard`, `#stdebPasswordCard`, `#stdbModuleTitle`, `#stdbModuleSubtitle` |
| `stardebate_editor.qss` | .stardebate 编辑器面板 | 编辑区域、语法高亮、保存按钮 |
| `star_checkbox.qss` | 自定义多选框组件 | `#starCheckBox`, `#starCheckIcon`, `#starCheckText` |
| `star_spinbox.qss` | 自定义数字输入框组件 | `#starSpinBox`, `#starSpinBtn` |
| `log_settings.qss` | 日志设置面板 | 日志级别选择、路径设置、保存按钮 |
| `plugins.qss` | 插件通用 UI + 管理面板 | `#pluginPanel`, `#pluginCard`, `#pluginInput`, `#pluginCombo`, `#pluginPrimaryBtn`, `#pluginSecondaryBtn`, `#pluginDangerBtn`, `#pluginPanelTitleMajor`, `#pluginCardName` |
| `svg_renderer.qss` | SVG 渲染器设置页 | 渲染模式选择、缓存管理、预览区域 |
| `material_pool.qss` | 资料池 + MD查看器 + 详情页 | `#poolSearchInput`, `#searchResultCard`, `#searchCard*`, `#mdH1`~`#mdH3`, `#mdCodeBlock`, `#mdQuoteBlock`, `#mdLiFrame`, `#detailTopBar`, `#detailInfoCard`, `#detailFooterBtn`, `#poolTableView`, `#poolContentText`, `#exportProgressPanel` |

### 4.2 objectName 规范

项目中所有需要 QSS 控制的控件均设置了 `objectName`，QSS 通过 **ID 选择器**（`#objectName`）匹配。编写 QSS 时应优先使用 ID 选择器而非类型选择器，以保证样式精确隔离。

常用 objectName 示例：

| objectName | QSS 文件 | 说明 |
|------------|----------|------|
| `#smallBtn` | `main.qss` | 小型操作按钮（全局复用） |
| `#primaryBtn` | `main.qss` | 主操作按钮（紫色强调） |
| `#titleBar` | `title_bar.qss` | 标题栏容器 |
| `#minBtn`, `#maxBtn`, `#closeBtn` | `title_bar.qss` | 窗口控制按钮 |
| `#topNavBtn`, `#topNavMenu` | `title_bar.qss` | 顶部导航按钮/菜单 |
| `#navPanel`, `#navToggleBtn` | `nav_bar.qss` | 导航面板/切换按钮 |
| `#analysisCard` | `ai_analysis.qss` | AI 分析维度卡片 |
| `#noteCard` | `notes.qss` | 便签卡片 |
| `#refCard` | `ref_doc.qss` | 资料卡片 |
| `#searchResultCard` | `material_pool.qss` | 搜索卡片 |
| `#pluginCard` | `plugins.qss` | 插件管理卡片 |
| `#popupDialog` | `popup_dialog.qss` | 自定义弹窗容器 |
| `#stdebExportDialog` | `stardebate_format.qss` | .stardebate 导出对话框 |
| `#starCheckBox` | `star_checkbox.qss` | 自定义多选框 |
| `#starSpinBox` | `star_spinbox.qss` | 自定义数字输入框 |
| `#assignNavBtn` | `tournament.qss` | 赛制导航按钮（支持 :checked 伪状态） |
| `#sideToggleBtn` | `cross_examination.qss` | 质询持方切换按钮 |
| `#mdH1`, `#mdH2`, `#mdH3` | `material_pool.qss` | MD 查看器标题元素 |
| `#detailFooterBtn` | `material_pool.qss` | 详情页底部操作按钮 |

### 4.3 qproperty 动态属性

StarDebate 使用 `pyqtProperty` + QSS `qproperty-*` 机制，让 Python `paintEvent` 绘制颜色也可由 QSS 控制。原理是：

1. Python 控件定义 `pyqtProperty` 属性（含 getter/setter）
2. QSS 文件通过 `qproperty-<propertyName>` 设置属性值
3. Qt 样式引擎在应用 QSS 时自动调用 setter 更新属性

```python
# Python 侧（以标题栏按钮为例）
from PyQt5.QtCore import pyqtProperty

class _TitleBarButton(QPushButton):
    @pyqtProperty(QColor)
    def iconNormal(self):
        return self._clr_norm

    @iconNormal.setter
    def iconNormal(self, color):
        self._clr_norm = QColor(color)
        self.update()  # 触发重绘
```

```css
/* QSS 侧 */
#minBtn {
    qproperty-iconNormal: #a6adc8;
    qproperty-iconHover: #cdd6f4;
}
```

**QSS 属性名规则**：Python 属性名 `iconNormal` → QSS 写法 `qproperty-iconNormal`（属性名首字母小写，QSS 用小驼峰）。

### 4.4 标题栏按钮颜色

三个窗口控制按钮（最小化/最大化/关闭）通过 `qproperty-*` 控制绘制颜色，每种主题可在 `title_bar.qss` 中独立配置。

**按钮 objectName：**
| objectName | 按钮 | 位置 |
|------------|------|------|
| `#minBtn` | 最小化（─ 横线） | 最右侧倒数第三 |
| `#maxBtn` | 最大化/还原（□ / □□） | 最右侧倒数第二 |
| `#closeBtn` | 关闭（✕ 交叉线） | 最右侧末尾 |

**可配置的 qproperty 属性：**

| QSS 属性 | 类型 | 说明 |
|----------|------|------|
| `qproperty-iconNormal` | `#rrggbb` | 默认状态图标描边色 |
| `qproperty-iconHover` | `#rrggbb` | hover 时图标描边色 |
| `qproperty-bgHover` | `#rrggbb` | hover 时按钮背景填充色 |
| `qproperty-bgPressed` | `#rrggbb` | pressed 时按钮背景填充色 |

**配置示例：**

```css
/* 最小化和最大化共用 */
#minBtn, #maxBtn {
    qproperty-iconNormal: #a6adc8;
    qproperty-iconHover: #cdd6f4;
    qproperty-bgHover: #313244;
    qproperty-bgPressed: #45475a;
}

/* 关闭按钮独立配色（hover 为红色） */
#closeBtn {
    qproperty-iconNormal: #a6adc8;
    qproperty-iconHover: #ffffff;
    qproperty-bgHover: #f38ba8;
    qproperty-bgPressed: #e0567a;
}
```

**配色建议：**

| 属性 | 浅色主题建议 | 深色主题建议 |
|------|-------------|-------------|
| `iconNormal` | `muted` 或 `subtext` | `subtext` |
| `iconHover` | `text` | `text` |
| `bgHover` | `overlay`（浅色） | `overlay`（深色） |
| `bgPressed` | 比 `overlay` 深一档 | 比 `overlay` 深一档 |
| close `bgHover` | `accent_red` | `accent_red` |

### 4.5 QSS 提取最佳实践

为保证样式可维护性和多主题兼容性，开发功能时应遵循以下规范：

**原则 1：静态样式放入 QSS，动态样式保留内联**

```python
# ✅ 正确：静态样式通过 objectName 绑定到 QSS
label.setObjectName("myLabel")
# 对应 QSS: #myLabel { color: #cdd6f4; border: none; }

# ✅ 正确：运行时动态样式保留内联（如状态颜色、用户自定义色）
label.setStyleSheet(f"color: {dynamic_color};")
```

**原则 2：使用 QSS 伪状态替代动态拼装样式**

```python
# ❌ 错误：手动拼装样式字符串判断 checked 状态
btn.setStyleSheet(_nav_btn_qss(checked))

# ✅ 正确：利用 QSS :checked 伪状态，Python 只调用 setChecked()
btn.setCheckable(True)
btn.setObjectName("assignNavBtn")
btn.setChecked(checked)  # QSS 自动切换样式
```

对应的 QSS：
```css
#assignNavBtn { background-color: #313244; color: #a6adc8; }
#assignNavBtn:hover { background-color: #45475a; color: #cdd6f4; }
#assignNavBtn:checked { background-color: #cba6f7; color: #1e1e2e; }
```

**原则 3：不要给全局 QSS 已控制的控件重复 setStyleSheet()**

`main.qss` 已定义了 `QPushButton`、`QLabel`、`QTextEdit`、`QLineEdit` 等全局控件的通用样式。如果控件使用 `setObjectName("smallBtn")` 等全局组件名，则 **不要再调用 setStyleSheet()**，让全局 QSS 生效即可。

**原则 4：模块化命名**

- `objectName` 使用模块前缀：资料池用 `#pool*`/`#md*`/`#detail*`，赛程用 `#format*`/`#assign*`
- 全局复用组件用简短名：`#smallBtn`、`#primaryBtn`
- 卡片子标签用 `功能Card` + 字段名：`#refCardIndex`、`#pluginCardName`

---

## 5. 颜色体系

### 5.1 语义色值

每个主题定义 12 个语义色值，分为**中性色**（6 个）和**强调色**（6 个）：

| 色值键 | 类别 | 语义 | 使用场景 |
|--------|------|------|----------|
| `base` | 中性 | 基础背景 | 主窗口/页面背景 |
| `surface` | 中性 | 表面背景 | 标题栏、卡片、面板背景 |
| `overlay` | 中性 | 叠加层 | hover 效果、分隔线、边框 |
| `text` | 中性 | 主文字 | 标题、正文、重要文本 |
| `subtext` | 中性 | 次文字 | 提示、辅助信息、按钮常态图标 |
| `muted` | 中性 | 弱化文字 | 禁用态、占位符、水印 |
| `accent_green` | 强调 | 绿色 | 正方/通过/成功/论据维度 |
| `accent_purple` | 强调 | 紫色 | 主题色/选中态/标题图标 |
| `accent_blue` | 强调 | 蓝色 | 论证维度/链接/信息 |
| `accent_pink` | 强调 | 粉色 | 反方/柔和强调 |
| `accent_yellow` | 强调 | 黄色 | 论点维度/搜索高亮/警告 |
| `accent_red` | 强调 | 红色 | 关闭按钮/优势维度/错误/危险 |

### 5.2 两主题配色对照表

| 色值 | Notion Dark（深色） | Notion Light（浅色） |
|------|:---------------:|:----------------:|
| `base` | `#181A1E` | `#FFFFFF` |
| `surface` | `#1E2025` | `#F7F7F5` |
| `overlay` | `#2C2E36` | `#EDEDEB` |
| `text` | `#E0E0E0` | `#37352F` |
| `subtext` | `#A0A0A0` | `#9B9A97` |
| `muted` | `#6B6B6B` | `#C0BFBF` |
| `accent_blue` | `#2E6DDE` | `#2E6DDE` |
| `accent_green` | `#2EA043` | `#2EA043` |
| `accent_red` | `#E74C3C` | `#E74C3C` |
| `accent_yellow` | `#C8A030` | `#D4A017` |
| `accent_purple` | `#2E6DDE` | `#2E6DDE` |
| `accent_pink` | `#D08770` | `#D08770` |
| `border` | `#343640` | `#E0E0E0` |
| `hover` | `#262830` | `#EFEFEF` |
| `selected_bg` | `#1A2A4A` | `#E8F0FE` |

---

## 6. 快速创建主题

### 6.1 从现有主题复制

创建新主题最快捷的方式是复制一个现有主题作为起点：

```bash
# 以 Notion Dark 深色主题为基础创建新主题
cp -r style/themes/notion_dark style/themes/my_theme
```

然后修改 `style/themes/my_theme/theme.json`：

```json
{
    "name": "我的主题",
    "version": "1.0.0",
    "author": "你的名字",
    "description": "自定义主题描述",
    "type": "dark",
    "qss_files": [ ... ],      // 保持与源主题一致
    "colors": { ... }           // 替换为你的配色
}
```

最后在所有 `.qss` 文件中批量替换颜色值（见 6.2）。

### 6.2 批量颜色替换脚本

编写 Python 脚本将 Notion Dark 配色批量替换为目标配色。脚本需覆盖**所有 22+ 个颜色键**（见 theme.json 中的 colors 对象）：

```python
"""
批量颜色替换脚本 — 在 style/themes/<theme_name>/ 目录下运行
将 Notion Dark 的 32 个 QSS 文件中的配色替换为你的配色
"""
import os, glob, json

# 1. 核心 15 色
COLOR_MAP = {
    "#181A1E": "#你的base",
    "#1E2025": "#你的surface",
    "#2C2E36": "#你的overlay",
    "#E0E0E0": "#你的text",
    "#A0A0A0": "#你的subtext",
    "#6B6B6B": "#你的muted",
    "#2E6DDE": "#你的accent_blue",
    "#2EA043": "#你的accent_green",
    "#E74C3C": "#你的accent_red",
    "#C8A030": "#你的accent_yellow",
    "#D08770": "#你的accent_pink",
    "#343640": "#你的border",
    "#262830": "#你的hover",
    "#1A2A4A": "#你的selected_bg",

    # 2. 中间/派生色（Notion Dark 基准，需按比例替换）
    "#14161A": "#你的base深",       # base 加深约 15%
    "#11111b": "#你的crust",        # 最底层
    "#3A3D4A": "#你的toggle_off",   # toggle 关闭状态
    "#2A1A2A": "#你的正方背景",     # 自定
    "#1A2A1A": "#你的接质答复",     # 自定
}

target_dir = "style/themes/my_theme"
qss_files = glob.glob(os.path.join(target_dir, "*.qss"))
for qss_file in qss_files:
    with open(qss_file, "r", encoding="utf-8") as f:
        content = f.read()
    for old, new in COLOR_MAP.items():
        if old in content:
            content = content.replace(old, new)
    with open(qss_file, "w", encoding="utf-8") as f:
        f.write(content)

print(f"颜色替换完成！共处理 {len(qss_files)} 个 QSS 文件。")
```

> **提示**：由于部分颜色在 UI 中同时作为文字色和背景色使用，替换后强烈建议在应用中实际预览各功能面板，确保对比度正常。

### 6.3 模板模式下的主题维护

模板模式（v6.2.0+）下，维护多主题非常简单：

1. **qss_templates/** 是唯一的 QSS 源码，所有主题共用一个模板集
2. **各主题只需维护 theme.json 的 colors 字段**，无需碰任何 .qss 文件
3. 新增主题 = 创建 `style/themes/new_theme/theme.json`（定义 colors），设置页自动发现
4. 修改颜色 = 改 theme.json 中的 hex 值，重启或切换主题即生效
5. 模板本身需要更新时（如新增功能需要新的 QSS 规则）：
   - 在 `qss_templates/xxx.qss` 中编写规则，使用 `@key@` 占位符
   - 运行 `python tools/verify_qss_templates.py` 验证与所有主题兼容
   - 运行 `python tools/qss_color_reference.py --md` 更新引用文档

### 6.4 模板转换与验证

从 v6.2.0 开始，QSS 采用模板模式管理。以下工具用于模板的生成和验证：

**模板转换工具** `tools/convert_to_template.py` — 从参考主题的硬编码 QSS 自动生成 `@key@` 模板：

```bash
# 执行转换（读取 notion_dark → 写入 style/qss_templates/）
python tools/convert_to_template.py

# 预览模式（不写入文件，显示映射表）
python tools/convert_to_template.py --dry-run
```

转换过程：
1. 读取参考主题的 `theme.json`，构建 `hex → @key@` 映射（多键同色时自动选语义最佳的键名）
2. 扫描所有 `.qss` 文件，将 matching hex 替换为 `@key@` 占位符
3. 未映射的色值（不在 theme.json 中的）保持原样，并在报告中列出
4. 自动补全 `theme.json` 中缺失的常用色值（如 `white: #FFFFFF`）

**模板验证工具** `tools/verify_qss_templates.py` — 验证模板替换后与原始文件完全一致：

```bash
# 全部验证
python tools/verify_qss_templates.py

# 仅验证单个文件
python tools/verify_qss_templates.py --file main.qss

# 显示详细 diff
python tools/verify_qss_templates.py --verbose
```

验证流程：
1. 将 `qss_templates/` 中的 `@key@` 替换为 notion_dark 的色值
2. 逐行 diff 对比原始硬编码文件
3. 再对 notion_light 做兼容性检查（确保无残留占位符）

> 新主题开发时：只需编写 `theme.json`，无需碰任何 QSS 文件。
> `tools/convert_to_template.py` 和 `tools/verify_qss_templates.py` 仅在模板本身需要更新时才运行。

### 6.5 颜色键引用地图工具

`tools/qss_color_reference.py` 用于统计分析所有 QSS 模板中 `@key@` 占位符的引用情况，支持三种输出格式：

```bash
# 终端输出（正向+反向引用，带行号和属性名）
python tools/qss_color_reference.py

# 生成 Markdown 文档（docs/qss_color_reference.md）
python tools/qss_color_reference.py --md

# 生成 JSON 数据（qss_color_reference.json，可供程序化消费）
python tools/qss_color_reference.py --json
```

**输出内容：**
- **正向引用**（按颜色键分组）：每个 `@key@` 在哪些模板文件的哪些行被引用，以及引用的 CSS 属性名
- **反向引用**（按模板文件分组）：每个模板文件使用了哪些颜色键

**使用场景：**
| 场景 | 用法 |
|------|------|
| 开发中检查新加的 `@key@` 引用情况 | `python tools/qss_color_reference.py | findstr @my_key@` |
| 删除颜色键前确认影响面 | 正向查找该键被多少文件引用 |
| 修改模板文件的颜色结构 | 反向查看该文件使用了哪些颜色键 |
| 提交前生成文档 | `python tools/qss_color_reference.py --md` |
| CI 中验证引用变更 | `python tools/qss_color_reference.py --json` 后 diff 比对 |

扫描范围包括 `style/qss_templates/` 下所有 `.qss` 文件以及 `plugins/<name>/theme/` 下所有插件 `.qss` 文件。

---

## 7. 主题加载机制（模板模式）

```
┌──────────────────────────────────────────────────────────┐
│ config/config.json                                       │
│ "theme": "notion_dark"          ← 用户选择持久化          │
└───────────────────┬──────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────────────────┐
│ AppConfigManager.apply_style(theme_name)                 │
│                                                          │
│ 1. 读取 theme.json → 获取颜色映射 colors                 │
│ 2. 扫描 qss_templates/ 获取模板文件列表                   │
│ 3. 遍历模板文件：                                         │
│    ├── 主题目录下有同名 .qss 缓存？ → 直接读取（回退）     │
│    └── 无缓存 → 读取模板 + @key@ → hex 实时替换           │
│ 4. 拼接为单个字符串                                      │
│ 5. mw.setStyleSheet(combined_qss)  ← 应用样式            │
└──────────────────────────────────────────────────────────┘
```

**模板替换示例：**
```css
/* qss_templates/title_bar.qss — 含 @key@ 占位符 */
#titleBar {
    background-color: @base@;
    border-bottom: 1px solid @border@;
}
#titleIcon {
    color: @text@;
}
```
```python
# apply_style() 读取后替换为：
# #titleBar {
#     background-color: #181A1E;  ← notion_dark 的 base
#     border-bottom: 1px solid #343640;  ← notion_dark 的 border
# }
# #titleIcon {
#     color: #E0E0E0;  ← notion_dark 的 text
# }
```

**加载顺序：**
1. 应用启动 → `StarDebate.py` 调用 `self._app_cfg.apply_style()`（从 `config.json` 读取 `theme`）
2. 用户切换主题 → `switch_theme(name)` 写入 `config.json` + `theme_colors.refresh()` + `apply_style(name)`
3. 切换过程中同时刷新：SVG 渲染器颜色 / 导航栏图标 / 标题栏按钮 / 悬浮卡片

**容错机制：**
- `theme.json` 不存在 → 回退到默认主题 `notion_dark`
- `qss_templates/` 中某文件不存在 → 静默跳过
- 模板中存在 `@unknown@` 但 theme.json 无对应键 → 记录 warning 日志，保留原样
- `config.json` 中 `theme` 字段不存在 → 使用 `DEFAULT_THEME`
- 主题目录不存在 → 自动回退默认主题

---

## 8. SVG 渲染器主题适配（v2.0 新增）

StarDebate 内置 SVG 渲染器（`components/svg_renderer/`），支持将项目内 SVG 图标按当前主题色自动着色。每个主题通过 `theme.json` 的 `svg_renderer` 字段配置着色方案。

### 渲染模式

| 模式 | 配置键 | 说明 |
|------|--------|------|
| 单色渲染 | `mono.color` | 所有图形使用同一颜色填充 + 描边 |
| 双色渲染 | `dual.primary` / `dual.accent` | 主图形用 primary 色，次要图形用 accent 色 |
| 原生渲染 | 不配置 | 保留 SVG 原始颜色，不应用主题 |

### 配置语法

```json
{
    "svg_renderer": {
        "mono": {
            "color": "text"           // 映射到 colors 中的键名
        },
        "dual": {
            "primary": "accent_purple",
            "accent": "text"
        }
    }
}
```

`svg_renderer` 中的值（如 `"text"`、`"accent_purple"`）是 `colors` 表中的**键名**，运行时自动映射为对应 hex 值。

### 深色/浅色主题建议

| 配置 | 深色主题 | 浅色主题 |
|------|---------|---------|
| `mono.color` | `"text"` | `"text"` |
| `dual.primary` | `"accent_purple"` | `"accent_blue"` |
| `dual.accent` | `"text"` | `"text"` |

> 浅色主题选择 `accent_blue` 而非 `accent_purple` 是因为紫色在浅色背景下视觉辨识度较低，蓝色更醒目。

---

## 9. 设置页预览卡片

设置 → 外观页自动扫描 `style/themes/` 下所有含 `theme.json` 的主题文件夹，每个主题渲染一张 **ThemeCard** 预览卡片。

**卡片规格：**
- 尺寸：195 × 232 px
- 微型界面预览（163 × 120 px），动态渲染：
  - 顶部色条 → 标题栏颜色（`surface`）
  - 侧边色块 → 导航栏颜色（`surface` 变体）
  - 内容区 → 基础背景（`base`）
  - 底部 5 色条 → 5 个 accent 颜色
- 选中态 → `accent_purple` 2px 边框高亮
- 当前使用主题显示 "✓ 当前使用" 标记
- 卡片 `clicked` 信号 → 更新选中 → 保存时触发 `switch_theme()`

**布局模式：**
- 窗口模式：QHBoxLayout 单行 + 横向滚动（滚轮驱动）
- 全屏模式：FlowLayout 自动换行 + 纵向滚动

---

## 10. 常见问题

### Q1: 新建主题后外观页不显示？

检查 `theme.json` 是否：
- 位于 `style/themes/<your_theme>/` 目录下
- 文件名完全匹配 `theme.json`（注意大小写）
- JSON 格式有效（无多余逗号、引号配对正确）
- 包含必需的 `name`、`type`、`colors` 字段

### Q2: QSS 样式部分失效？

可能原因：
1. QSS 文件未在 `theme.json` 的 `qss_files` 列表中声明
2. 控件 `objectName` 与 QSS 选择器不匹配
3. 父级控件覆盖了子控件样式（检查 QSS 级联优先级）

### Q3: 标题栏按钮颜色不改？

标题栏按钮颜色由 `qproperty-*` 注入，确认 `title_bar.qss` 中包含：

```css
#minBtn, #maxBtn {
    qproperty-iconNormal: #xxx;
    qproperty-iconHover: #xxx;
    qproperty-bgHover: #xxx;
    qproperty-bgPressed: #xxx;
}
#closeBtn {
    qproperty-iconNormal: #xxx;
    qproperty-iconHover: #xxx;
    qproperty-bgHover: #xxx;
    qproperty-bgPressed: #xxx;
}
```

### Q4: 颜色替换后某些区域颜色不对？

批量替换脚本可能遗漏了部分颜色。以下派生/中间色也需要替换：

- **更深的底色**：`#11111b`（最深面板背景，base 加深 ~20%）
- **混合背景色**：`#1e1e30`（卡片 hover）`#26263a`（资料卡片 hover）
- **更深边框**：`#45475a`（overlay 加深 ~40%）、`#585b70`（overlay 加深 ~80%）
- **正方/反方专用背景**：`#1a2e2a`、`#241a2e`、`#1a2e1a` 等
- **按钮 hover 亮色**：`#b4befe`（primary hover）、`#94e2d5`（accent_green hover）、`#d4b8ff`（变体）
- **关闭按钮**：`#e0567a`（close pressed 红）

完整派生色表见 §5.2 附表。

### Q5: 可以只提供部分 QSS 文件吗？

可以。`qss_files` 列表中缺失的文件会被静默跳过，不存在的文件对应的模块将回退到 Qt 默认样式。**至少需要 `main.qss`** 来设置全局背景和基本控件样式。

### Q6: 如何同时维护深色和浅色变体？

建议流程：
1. 先完成深色主题的 QSS 编写
2. 用颜色替换脚本生成浅色变体
3. 针对浅色主题手动微调（部分 UI 元素在深浅色下需要不同的对比度策略）
4. 两套主题分别放在 `style/themes/<name_dark>/` 和 `style/themes/<name_light>/`

### Q7: `colors` 字段中的颜色会自动应用到 UI 吗？

不会。`colors` 字段仅用于设置页外观卡片的微型预览渲染，实际 UI 样式由 `.qss` 文件中的硬编码颜色值控制。两者应保持一致性——`theme.json` 的 `colors` 是主题的「调色板声明」，QSS 文件是「实际应用」。

### Q8: SVG 图标的颜色如何随主题变化？

SVG 图标颜色由 `theme.json` 的 `svg_renderer` 字段控制。配置后，项目中所有通过 `SvgRenderer.icon()` 加载的图标会自动应用主题色。详细配置见 §8。
