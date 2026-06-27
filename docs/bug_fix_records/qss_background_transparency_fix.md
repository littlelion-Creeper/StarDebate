# Bug 修复记录：QSS 背景色透明化

> 日期：2026-06-09
> 涉及主题：catppuccin_mocha, nord, modern_mocha, notion_dark, notion_light

---

## 问题特征

列表项/卡片/框架显示为不透明深色块，表现为：

1. **视觉**：文本（如数字、标题）被深灰色/黑色矩形背景块包裹，横向贯穿容器宽度
2. **位置**：辩论详情页（proFrame/conFrame）、接质模拟页（聊天气泡）、资料稿卡片页（refCard）、SVG 设置页（svgThemeSubCard）
3. **跨主题**：在 notion_dark 下最明显（深色块），notion_light 下也有浅色块

---

## 分析与溯源方法

### 1. 定位问题控件

搜索 QSS 文件中带 `background-color: #xxx` 的控件规则：

```bash
# 查找所有非 transparent 的背景色规则
grep -rn "background-color:\s*#[0-9a-fA-F]" style/themes/notion_dark/
```

或搜索 Python 文件中 `setStyleSheet` 含 `background-color` 的代码：

```bash
grep -rn "setStyleSheet.*background-color" workers/
```

### 2. 判断是否异常

正常情况：
- **容器控件**（QFrame/QWidget 作为布局容器）→ 可有背景色
- **子控件**（QLabel/QTextEdit 等展示内容的控件）→ 应为 `transparent`，否则会遮挡父容器背景

异常情况：子控件或卡片有独立背景色，形成"深色条纹堆叠"效果。

### 3. 根因判断

- QSS 文件中的 `#xxx { background-color: #xxx; }` → 硬编码主题色，不跟随主题切换
- Python 中的 `setStyleSheet("#xxx { background-color: #xxx; }")` → 硬编码且不跟随主题
- `QLabel` 使用 `setStyleSheet("color: xxx;")` → Qt 会重置该控件的所有 QSS 继承，导致 `background-color`/`padding`/`font-size` 丢失

---

## 修复方法

### 通用修复原则

1. **容器背景用 QSS 控制**（各主题独立定义）
2. **内容控件的背景一律设为 `transparent`**
3. **控件间区分靠左边框/文字颜色/圆角**，不靠背景色
4. **避免 Python 内联 `setStyleSheet`**，改用 objectName + QSS 文件

### 具体修复步骤

#### 第一步：全局 QLabel 规则补全

```qss
/* 在每个主题的 main.qss 中 */
QLabel {
    background-color: transparent;
    color: <各主题文字色>;
    padding: 0px;
}
```

涉及文件：5 个主题的 `main.qss`

#### 第二步：修复内联 setStyleSheet

搜索 `setStyleSheet.*color:` 且只设了 color 没设 background-color 的代码：

```python
# 错误：setStyleSheet 重置了 QLabel 的 QSS 继承
label.setStyleSheet(f"color: {tc('accent_green')};")

# 修复：改用 objectName + QSS 文件控制
label.setObjectName("detailProHeader")
# 在 main.qss 中添加规则
# #detailProHeader { background-color: transparent; color: #a6e3a1; ... }
```

#### 第三步：统一 objectName

| 控件类型 | 通用 objectName | 说明 |
|---------|:--------------:|------|
| QLineEdit | `lineEdit` | 所有单行文本框 |
| QTextEdit/QPlainTextEdit | `textEdit` | 所有多行文本框 |
| QLabel | `label` | 所有标签（需配合父容器 + `:first`/`:last` 伪类区分） |

#### 第四步：修复具体控件

| 控件 | 修复内容 |
|------|---------|
| `#proFrame` / `#conFrame` | `background-color` → `transparent` |
| `#acceptMsgAI/User/System/Score/Speech` | `background-color` → `transparent` |
| `#acceptScoreBar` / `#acceptInputFrame` | `background-color` → `transparent` |
| `#refCard` | `background-color` → `transparent`（hover 也改） |
| `#svgThemeSubCard` | 内联 `background-color: #11111b` → `transparent` |

---

## 涉及文件清单

### 全局 QLabel 规则（5 个主题的 main.qss）

| 文件 | 修改内容 |
|------|---------|
| `style/themes/catppuccin_mocha/main.qss` | QLabel 追加 `background-color: transparent; padding: 0px;` |
| `style/themes/nord/main.qss` | 同上 |
| `style/themes/modern_mocha/main.qss` | 同上 |
| `style/themes/notion_dark/main.qss` | 同上 |
| `style/themes/notion_light/main.qss` | 同上 |

### 独立 objectName 逐条修补（notion_dark + notion_light）

| 文件 | 修补规则数 |
|------|:---------:|
| `ai_expand.qss` | ~8 |
| `cross_examination.qss` | ~16 |
| `training.qss` | ~44 |
| `tournament.qss` | ~14 |
| `notes.qss` | ~8 |
| `material_pool.qss` | ~56 |
| `speech_writer.qss` | ~14 |
| `plugins.qss` | ~6 |

### 辩论详情页修复

| 文件 | 修改内容 |
|------|---------|
| `workers/star_debate/ui_assembly.py` | 8 个 QLabel：加 objectName、删 setStyleSheet |
| `5 个主题的 main.qss` | 添加 `#detailPage > QLabel:first/middle` / `#proFrame > QLabel:first/last` 等伪类规则 |

### 接质模拟页修复

| 文件 | 修改内容 |
|------|---------|
| `notion_dark/cross_examination.qss` | 7 个气泡/栏背景 → `transparent` |
| `notion_light/cross_examination.qss` | 同上 |

### 资料稿卡片页修复

| 文件 | 修改内容 |
|------|---------|
| `notion_dark/main.qss` | `#refCard` 背景 → `transparent` |
| `notion_light/main.qss` | 同上 |

### SVG 设置页修复

| 文件 | 修改内容 |
|------|---------|
| `workers/settings/pages/svg_settings_page.py` | 内联 `background-color: #11111b` → `transparent` |

### 文本框 objectName 统一

| 文件数 | 说明 |
|:-----:|------|
| 16 个 Python 文件 | 所有 QLineEdit/QTextEdit 的 setObjectName 改为 `lineEdit`/`textEdit` |
| 6 个 catppuccin_mocha QSS 文件 | 删除对应的独立 `#xxx` 规则（已由 main.qss 类选择器覆盖） |

---

## 快速排查清单

下次遇到类似"深色遮罩"问题时：

```
□ 是 QLabel 显示异常？→ 检查是否用了 setStyleSheet("color: ...") 未带 background-color
□ 是卡片/列表项？→ 搜索 background-color: # 在 QSS 文件中
□ 是内联样式？→ 搜索 setStyleSheet.*background-color 在 Python 文件中
□ 修复方式：
  1. objectName + QSS 替代 setStyleSheet
  2. background-color: transparent + 保留边框/左边框区分
  3. 沿父容器链检查，确保子控件透明
```
