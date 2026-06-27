# Bug 修复记录：DebateClaw 气泡布局重构（QWidget 全组件化 + 圆角 + 宽度修复）

## 摘要

DebateClaw 插件的气泡渲染经历了三次架构迭代，最终落地为 **QWidget 全组件化**方案。本次记录涵盖第三次重构以及后续的宽度修复。

---

## 修复 1：气泡圆角失效（QTextBrowser HTML 引擎限制）

### 问题

2026-06-15 将气泡改为 QTextBrowser 中央 HTML 文档后，`border-radius` 不在 `<td>/<div>` 上生效。Qt 的 QTextDocument 引擎不支持 CSS3 `border-radius`。

### 解决方案

放弃中央 HTML 文档，改为 **QScrollArea + 独立 QWidget 气泡**。每个气泡是一个 QFrame，通过 **QSS `border-radius: 12px`** 实现圆角，Qt 的 QSS 引擎完整支持 CSS3 圆角。

```
QScrollArea
├── QFrame#clawAiBubble    (transparent bg, QSS border-radius:12px)
│   └── QTextBrowser       (内容渲染, 透明背景)
│   └── QLabel             (token 用量)
├── QFrame#clawUserBubble  (accent bg, QSS border-radius:12px + border-left:3px)
│   └── QLabel             (用户文本)
├── QLabel                 (系统消息)
```

### 影响范围

- 删除 `_makesys()`、`_makeuser()`、`_makeai()` HTML 构建函数
- 删除 `_BubbleTextEdit`、`_calc_bubble_te_height()`、`_calc_md_te_height()`
- 删除 `_render_chat()`、`_chat_blocks`、`_streaming_text` 等 HTML 文档全局状态
- 新增 `_add_user_msg()`、`_add_ai_bubble()`、`_add_sys_msg()` QWidget 构建函数
- 新增 `_AutoTB`（自动高度 QTextBrowser 子类）

---

## 修复 2：气泡宽度锁定为功能区一半

### 问题

AI 气泡的宽度被锁定为功能区面板宽度的一半左右。用户气泡没有最大宽度限制，可能填满整个面板。

### 根因

`_add_user_msg` 和 `_add_ai_bubble` 创建气泡时在 QHBoxLayout 中使用了 `hl.addStretch()`，stretch 因子为 1 与气泡 QFrame 的 `Expanding` 策略竞争空间，导致 QFrame 只能分配到约 50% 的宽度。

```
# 错误布局（AI 气泡）
QHBoxLayout
├── QFrame (Expanding)     ← 获取约 50% 宽度
└── QSpacerItem (stretch=1) ← 获取约 50% 宽度

# 错误布局（用户气泡）
QHBoxLayout
├── QSpacerItem (stretch=1) ← 吃满剩余空间
└── QFrame (无最大宽度)    ← 可能填满整个面板
```

### 修复

**AI 气泡**：去掉 `hl.addStretch()`，气泡 QFrame 使用 `Expanding` 策略 + `setMaximumWidth(panel.width())`，自动填满面板宽度。

**用户气泡**：保留 `hl.addStretch()` 用于右对齐，但添加 `setMaximumWidth(panel.width() * 0.85)` 限制宽度不超过 85% 面板。

**统一管理**：新增 `_update_bubble_widths()` 函数，面板 resize 时遍历所有气泡更新最大宽度。

```python
# AI 气泡
f.setMaximumWidth(int(panel.width()))  # 全宽
w = QWidget(); hl = QHBoxLayout(w)
hl.addWidget(f)                         # 不加 stretch
cl.addWidget(w)

# 用户气泡
f.setMaximumWidth(int(panel.width() * 0.85))
w = QWidget(); hl = QHBoxLayout(w)
hl.addStretch(); hl.addWidget(f); hl.addSpacing(12)  # 保留 stretch 右对齐
cl.addWidget(w)
```

### 影响

- `_add_ai_bubble()`：移除 `hl.addStretch()`，添加 `f.setMaximumWidth(int(panel.width()))`
- `_add_user_msg()`：添加 `f.setMaximumWidth(int(panel.width() * 0.85))`
- `_set_ai_max_width()` 重命名为 `_update_bubble_widths()`，覆盖 AI 和用户气泡
- `resizeEvent` 调用 `_update_bubble_widths()`

---

## 修复 3：流式渲染闪烁与高度不稳定

### 问题

流式 AI 回复过程中，每个 chunk 到达都触发全量 `setHtml()`，导致气泡高度反复跳动。

### 修复

- 使用 50ms 单次 QTimer coalesce 多个 chunk
- 增量更新：只对最后一个 AI 气泡内嵌的 `_AutoTB` 调用 `setMarkdown()`
- `_AutoTB` 的 `_adj()` 在 `setMarkdown` 后通过 `QTimer.singleShot(0)` 延迟计算高度

```python
_AutoTB.setMarkdown(text)
    → super().setMarkdown(text)
    → QTimer.singleShot(0, self._adj)
        → doc.setTextWidth(viewport.width())
        → self.setFixedHeight(doc.size().height() + 8)
```

---

## 影响版本

- 2026-06-15 第三次重构（QWidget 全组件化）
- 2026-06-15 宽度修复（stretch 竞争 + 用户气泡 maxWidth）

## 涉及文件

- `plugins/debate_claw/main.py`（全部气泡代码）
