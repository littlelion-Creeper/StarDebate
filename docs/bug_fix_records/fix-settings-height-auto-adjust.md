# Bug 修复记录：设置对话框内容区高度不自动调整

## 摘要

优化设置页（`api_config.py`、`about_page.py`）并抽取共享工具模块 `_page_utils.py` 后，设置对话框内容区高度无法根据当前页面内容自动调整。二次修复后确认两处根因。

---

## 修复 1：`add_silabel` 不添加到 QWidget 父容器

### 问题

2026-06-26 将 `api_config.py` 标题/描述从 inline SiLabel + `layout.addWidget()` 改为共享函数 `add_silabel(page, ...)` 后，标题和描述文字**不显示、不占据布局空间**。

### 根因

`_page_utils.add_silabel()` 只有 `hasattr(parent, "addWidget")` 一条添加路径，但 `QWidget`（`page` 的类型）没有 `addWidget` 方法——只有 `QLayout` 和 `SiPanelCard` 有。因此 `add_silabel(page, "API 配置", ...)` 创建了 SiLabel 却从未加入 page 的 `QVBoxLayout`，静默丢失。

```
# 错误路径
add_silabel(page, "API 配置", SiColor.TEXT_A)
  → SiLabel(page)                          # OK，创建
  → hasattr(page, "addWidget") → False     # QWidget 无 addWidget
  → return lbl                              # 标签被丢弃，不在任何 layout 中
```

### 修复

添加 `elif parent.layout() is not None: parent.layout().addWidget(lbl)` 回退路径。

```python
# _page_utils.py & about_page.py
if hasattr(parent, "addWidget"):
    parent.addWidget(lbl)
elif parent.layout() is not None:
    parent.layout().addWidget(lbl)          # ← 新增 QWidget 回退
```

### 影响范围

- `workers/settings/pages/_page_utils.py`：`add_silabel()` 添加 `elif` 分支
- `workers/settings/pages/about_page.py`：本地 `_add_silabel()` 同步修复

---

## 修复 2：`_select_page` 中 `updateGeometry()` 传播短路

### 问题

切换页面后，scroll area 高度没有跟随新页面尺寸更新，显示区高度**被"钉死"在初始值**。

### 根因

`settings_dialog.py` 的 `_select_page` 中的 `while` 循环负责向上传播 `updateGeometry()`，但循环体在指针移到 `QScrollArea` 后立即 `break`，**跳过了 scroll area 自身的 `updateGeometry()` 调用**。

```python
# 错误循环（2026-06-26 引入）
w: QWidget = self._content_stack
while w:
    w.updateGeometry()
    w = w.parentWidget()         # w 变为 scroll area
    if isinstance(w, QScrollArea):
        break                     # BUG：scroll area 的 updateGeometry 从未执行
```

### 修复

移除 `break`，让循环一直传播到顶层 widget。

```python
# 修复后
w: QWidget = self._content_stack
while w:
    w.updateGeometry()
    w = w.parentWidget()          # 一直传到顶层，不含 break
```

### 影响范围

- `workers/settings/settings_dialog.py`：移除 `isinstance(w, QScrollArea)` 判断

---

## 修复 3：过度移除窗口模式高度钳制

### 问题

移除 `setMinimumHeight`/`setMaximumHeight` 后，窗口模式内容区高度不受控制，底部撑板无法正确吸收剩余空间。

### 背景

原始设计（ID 63629222）明确依赖"窗口模式用 scroll_area(stretch=0) + 底部撑板(stretch=1) + **maxHeight 钳制**"的三件套来保持内容区紧凑。2026-06-26 的优化代码移除了钳制，导致窗口模式布局失效。

### 恢复

还原 `_select_page` 中的钳制逻辑，并在 `_on_exit_maximize` 中同步恢复。

```python
# _select_page
sh = widget.sizeHint()
self._page_sh = sh.height()
self._content_stack.setMinimumHeight(self._page_sh)
if not self.isMaximized():
    self._content_stack.setMaximumHeight(self._page_sh)

# _on_exit_maximize
if self._page_sh is not None:
    self._content_stack.setMaximumHeight(self._page_sh)
```

### 影响

- `workers/settings/settings_dialog.py`：`_select_page` 恢复 min/max 钳制；`_on_exit_maximize` 恢复 `setMaximumHeight(self._page_sh)`

---

## 影响版本

- 2026-06-26 14:00 首次引入（api_config.py 优化 + _page_utils 共享模块）
- 2026-06-26 19:23 第一次修复（add_silabel QWidget 回退）
- 2026-06-26 19:23 第二次修复（updateGeometry 传播 + 钳制恢复）

## 涉及文件

- `workers/settings/pages/_page_utils.py`（新建，65 行）
- `workers/settings/pages/about_page.py`（~150 行小修改）
- `workers/settings/settings_dialog.py`（~20 行小修改）
