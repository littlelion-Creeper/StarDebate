# Bug 修复记录：插件注册面板展开后功能面板宽度被冻结为 0

## 摘要
`_toggle_plugin_panel_in_stack` 在展开插件注册面板时，调用 `hsplitter.setSizes(sizes)` 将已隐藏功能面板（索引 4~8）的 0 宽度值显式写回 QSplitter，导致这些面板再打开时宽度仍为 0，无法正常显示。

## 影响范围
- **文件**: `workers/star_debate/glue.py` → `_toggle_plugin_panel_in_stack` 方法
- **触发条件**: 打开任意注册在右侧（side="right"）的插件面板（如 quick_notes）
- **受影响面板**: [4]AI写稿、[5]AI扩写、[6]便签、[7]模拟训练、[8]插件管理
- **不受影响**: [0]左侧分栏、[1]AI一辩稿展示、[2]插件左栈、[3]中心区域、[9]插件右栈

## 根因分析

### QSplitter 行为特性
当 `widget.setVisible(False)` 时，QSplitter 自动将该 widget 的宽度折叠为 0，`hsplitter.sizes()` 返回的对应值为 0。

### 原代码执行流程
```
Step 1: _close_existing_function_panels()
  → 功能面板 4~8 全部 setVisible(False)
  → QSplitter 自动将它们折叠，hsplitter.sizes() 返回 [..., 0, 0, 0, 0, 0, 0]

Step 2: sizes = list(hsplitter.sizes())     # 读取到包含 0 的数组

Step 3: sizes[9] = target_w                  # 仅修改索引 9（插件右栈）

Step 4: hsplitter.setSizes(sizes)            # ⚠️ 将 0 值永久写回 4~8
```

### 后果
QSplitter 记住 4~8 的宽度为 0。后续即使 `setVisible(True)`，QSplitter 仍按记住的 0 值分配，功能面板宽度为 0。

## 修复方案

### 核心思路
不要将 0 值写入 `setSizes()`。在 `setSizes` 之前恢复隐藏面板为其 `minimumWidth()`，让 QSplitter 按正常值分配空间，再通过 `setStretchFactor(i, 0)` 让隐藏面板自动折叠。

### 修复后流程
```
Step 1: _close_existing_function_panels()
  → 功能面板 4~8 全部 setVisible(False)，QSplitter 自动折叠为 0

Step 2: sizes = list(hsplitter.sizes())     # 读到 [..., 0, 0, 0, 0, 0, 0]

Step 3: ★ 恢复隐藏面板的 minimumWidth
  for i, w in enumerate(sizes):
      if w == 0:
          widget = hsplitter.widget(i)
          if widget:
              sizes[i] = max(widget.minimumWidth(), 1)
  # sizes = [..., minWidth, minWidth, ...]

Step 4: 按比例计算目标面板宽度并写入 sizes

Step 5: hsplitter.setSizes(sizes)            # ✅ 正常值，不含 0

Step 6: ★ 用 stretchFactor 控制隐藏面板
  for i in (4, 5, 6, 7, 8):
      if widget and not isVisible():
          hsplitter.setStretchFactor(i, 0)   # stretch=0 → QSplitter 自动折叠
      else:
          hsplitter.setStretchFactor(i, 1)    # stretch=1 → 正常参与分配
```

### 关键代码（glue.py:171-214）
```python
sizes = list(hsplitter.sizes())

# 修复：将 size=0 的隐藏面板恢复为其 minimumWidth
for i, w in enumerate(sizes):
    if w == 0:
        widget = hsplitter.widget(i)
        if widget:
            sizes[i] = max(widget.minimumWidth(), 1)

# 按比例计算目标面板宽度
if side_key == "left":
    sizes[2] = int(sum(sizes) * _ratio)
    sizes[2] = max(_min_w, min(_max_w, sizes[2]))
else:
    sizes[9] = int(sum(sizes) * _ratio)
    sizes[9] = max(_min_w, min(_max_w, sizes[9]))

hsplitter.setSizes(sizes)

# 隐藏面板通过 stretchFactor=0 让 QSplitter 自动折叠
for i in (4, 5, 6, 7, 8):
    w = hsplitter.widget(i)
    if w and not w.isVisible():
        hsplitter.setStretchFactor(i, 0)
    elif w:
        hsplitter.setStretchFactor(i, 1)
```

## 经验教训

### 规则：QSplitter 中慎用 setSizes()
> 当 QSplitter 中存在 `setVisible(False)` 的隐藏 widget 时，`hsplitter.sizes()` 会返回这些 widget 的宽度为 0。**绝不能直接将包含 0 的 sizes 数组原样写回 `setSizes()`**，否则 QSplitter 会永久记住这些 0 值。

### 推荐模式
| 场景 | 做法 |
|------|------|
| 展开面板 | 使用 `setVisible(True)` + `setStretchFactor(i, weight)` |
| 折叠面板 | 使用 `setVisible(False)` + `setStretchFactor(i, 0)` |
| 分配空间 | `setSizes` 前先恢复隐藏面板为 minimumWidth |

### 类似风险点排查
项目中所有调用 `hsplitter.setSizes()` 的位置：
1. `glue.py:205` — **已修复**（本次修复）
2. `training/exercise/exercise_manager.py:651` — `splitter.setSizes([...center_w, 0, 0, 0...])` — **存在相同风险**，但该 splitter 仅供立论编辑页面内部使用，不在主 hsplitter 中，影响范围有限

## 修复日期
2026-06-08
