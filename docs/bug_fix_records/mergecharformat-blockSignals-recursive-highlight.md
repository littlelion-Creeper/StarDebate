# Bug 修复记录：悬浮卡片弹出后全文高亮（accent 色扩散）

## 摘要

`_apply_glossary_highlights` 中 `blockSignals(False)` 过早释放，导致 `mergeCharFormat` 误触 `textChanged` 信号，触发 `_schedule_glossary_refresh` → `_apply_glossary_highlights` 递归循环。在特定时序下（悬浮卡片弹出窗口），格式被错误地应用到整个文档，所有文字永久变为 accent 色 + 加粗，直到重启软件。

## 影响范围

- **文件**: `workers/speech_editor/speech_editor_manager.py` → `_apply_glossary_highlights` 方法
- **触发条件**: 绑定资料/资料稿/便签来源后，鼠标悬停在高亮词语上等待 300ms（悬浮卡片弹出的一瞬间）
- **受影响功能**: 词汇索引高亮（绑定词显示 accent 色 + 加粗）
- **恢复方式**: 重启软件（从 JSON 重新加载文本 + 重建格式）

## 根因分析

### Qt 内部行为

`QTextCursor.mergeCharFormat(QTextCharFormat)` 按 Qt 文档说明是纯格式操作，不应触发 `textChanged`。但在 Qt5 的部分版本/平台上，`mergeCharFormat` 确实会触发 `QTextDocument::contentsChanged`，进而被 `QPlainTextEdit` 转发为 `textChanged` 信号。

### 原代码执行流程

```
_apply_glossary_highlights(edit):

  edit.blockSignals(True)
  edit.setPlainText(text)       # 清除旧格式（信号被阻塞）
  edit.blockSignals(False)       # ← ⚠️ 过早放开信号

  for term, entry in custom_glossary.items():
    ...
    cursor.mergeCharFormat(fmt)  # ← 误触 textChanged
    #  ↓
    #  textChanged → _schedule_glossary_refresh(800ms timer)
    #  ↓
    #  800ms 后 → _apply_glossary_highlights 再次被调用
    #  ↓
    #  setPlainText(text) 再次清除格式 → mergeCharFormat 再次触发
    #  ↓
    #  ← 形成永久 800ms 递归循环 →
```

### 递归循环与全文高亮的关联

每次循环中 `setPlainText(text)` 会临时清除格式再重新应用。在正常情况下格式正确重建。但在某些时序下（尤其是 300ms 悬浮卡片弹出窗口与 800ms 刷新定时器重叠时），`mergeCharFormat` 的文档内部处理发生竞态条件，导致格式被应用到整个文档，且不自动恢复。

### 为什么重启后正常

`mergeCharFormat` 只修改运行时 `QTextDocument` 的 `QTextCharFormat`，不修改底层 `toPlainText()` 返回的文本内容。JSON 文件中保存的是纯文本，重启后重新调用 `_apply_glossary_highlights` 时从干净的文档开始，格式重建正确。

## 修复方案

### 核心思路

将 `blockSignals(False)` 移到所有 `mergeCharFormat` 调用完成之后，让格式化操作全程屏蔽信号，切断递归链。

### 修复后流程

```
_apply_glossary_highlights(edit):

  edit.blockSignals(True)
  edit.setPlainText(text)       # 清除旧格式（信号被阻塞）

  for term, entry in custom_glossary.items():
    ...
    cursor.mergeCharFormat(fmt)  # 格式合并（信号仍被阻塞）

  edit.blockSignals(False)       # ✅ 所有 mergeCharFormat 完成后才放开

  cursor = edit.textCursor()
  cursor.setPosition(...)
  edit.setTextCursor(cursor)     # ← 此处发出的 cursorPositionChanged 正常
  edit._end_batch_update()
```

### 关键代码（speech_editor_manager.py:1168-1216）

```python
edit._begin_batch_update()
saved_cursor_pos = edit.textCursor().position()

# 重置格式
edit.blockSignals(True)
edit.setPlainText(text)

# 重新应用格式（全程 blockSignals，防止 mergeCharFormat 误触 textChanged）
for term, entry in custom_glossary.items():
    if not term:
        continue
    ...
    while True:
        idx = text.find(term, idx)
        if idx == -1:
            break
        ...
        cursor = QTextCursor(edit.document())
        cursor.setPosition(idx)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, term_len)
        cursor.mergeCharFormat(fmt)
        idx += term_len

edit.blockSignals(False)          # ★ 移到这里

cursor = edit.textCursor()
cursor.setPosition(min(saved_cursor_pos, len(text)))
edit.setTextCursor(cursor)
edit._end_batch_update()

cache = self._build_bound_terms_cache(...)
edit.set_bound_terms_cache(cache)
```

### 不影响的功能

- `setTextCursor(cursor)` 发出的 `cursorPositionChanged` → `_highlight_current_line` 仍在 `blockSignals(False)` 之后，正常工作
- `_end_batch_update()` 恢复行高亮绘制，正常工作
- `_build_bound_terms_cache` 和 `set_bound_terms_cache` 更新绘图缓存，正常工作

## 经验教训

### 规则：QPlainTextEdit 批量格式化时全程阻塞信号

> 对 `QPlainTextEdit` 进行批量格式化操作（`mergeCharFormat`/`setCharFormat`）时，应全程使用 `blockSignals(True)`，直到所有格式操作完成后才恢复。即使 `mergeCharFormat` 文档上说不触发 `textChanged`，实际 Qt5 中它可能通过 `QTextDocument::contentsChanged` 间接触发。

### 推荐模式

```python
edit.blockSignals(True)           # 开始阻塞
edit.setPlainText(text)           # 重置文档

# ... 所有 mergeCharFormat 调用 ...

edit.blockSignals(False)          # 完成后再放开

# 然后恢复光标、更新视图（这些操作发出的信号是期望的）
edit.setTextCursor(cursor)
```

## 修复日期
2026-06-11
