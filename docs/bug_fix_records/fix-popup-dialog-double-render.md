# Bug 修复记录：CustomDialog 弹窗渲染两次（双层窗口堆叠）

## 摘要
`CustomDialog` 在 `_adjust_size()` 改用 `QFontMetrics.boundingRect()` 精确计算尺寸后，弹窗显示时出现两个独立窗口上下堆叠：上层窗口使用未调整的旧尺寸（固定 420 宽 + 手算高度），下层窗口为正确调整后的自适应尺寸。拖拽任一窗口时两者同步移动。

## 影响范围
- **文件**: `components/popup_dialog/popup_dialog.py` → `__init__()`, `_adjust_size()`
- **触发条件**: 调用 `CustomDialog.information/warning/error/question/confirm()` 等任意静态方法或直接实例化
- **受影响**: 所有使用 `CustomDialog` 的模块（29 个文件）
- **不受影响**: 其他 QDialog 子类（CrashPopup、SettingsDialog、BindSourceDialog 等）

## 根因分析

### Qt setStyleSheet() 异步生效机制
PyQt5 中 `setStyleSheet()` 的执行是**异步**的——调用时样式表被排队，实际字体/颜色等属性变更需等待**下一个事件循环**才真正应用到控件上。

### 原代码执行流程
```
Step 1: _setup_ui()
  → 创建所有控件（QLabel、QPushButton、QFrame 等）
  → 控件此时使用系统默认字体（Windows 默认 ~8~9pt）

Step 2: _load_theme_qss()
  → 调用 self.setStyleSheet(qss_content)
  → QSS 中定义 font-size: 11pt ← ⚠️ 异步排队，尚未生效

Step 3: _adjust_size()
  → msg_label.fontMetrics() ← 读到的是系统默认 ~9pt，而非 11pt
  → fm.horizontalAdvance(line) 偏小 → 文本宽度估算偏小
  → fm.boundingRect(QRect, TextWordWrap, text) 高度偏少行数
  → setFixedWidth(420~630) / setFixedHeight(180~N) ← 用错误数据设了尺寸

Step 4: _center_on_parent()
  → 用偏小的尺寸居中定位窗口

Step 5: dlg.exec_()
  → 进入模态事件循环
  → setStyleSheet() 正式生效！字体从 ~9pt 突变为 11pt
  → 控件实际需要的空间 > 当前固定宽高
  → Qt 布局引擎与 Windows DWM 冲突
  → 出现第二层窗口（DWM 重绘异常产物）
```

### 为什么拖拽触发第二个窗口
第一个弹窗在 `exec_()` 开始前已用**错误的较小尺寸**完成首次渲染。进入事件循环后 QSS 生效导致布局需要更多空间，但窗口已被 `setFixedWidth/Height` 锁定。当用户拖拽窗口时 Windows DWM 尝试重绘该区域，触发了"幽灵窗口"——即第二个渲染层。

### 对比：为什么旧代码没有此问题
旧版 `_adjust_height()` 使用**手算字符逐个累加宽度**的方式，对字体大小变化不敏感（字符数不变则换行数不变），即使字体从 9pt 变到 11pt 也只是文本溢出一点点，不会引发完整的二次渲染。而新版 `boundingRect(TextWordWrap)` 是像素级精确计算，字体差值会被放大成显著的尺寸差异。

## 修复方案

### 核心思路
将 `_adjust_size()` 和 `_center_on_parent()` 从 `__init__()` 同步调用改为 `QTimer.singleShot(0, ...)` 延迟到**下一个事件循环**执行，确保 `setStyleSheet()` 的所有样式属性（特别是字体）已完全生效后再读取 `fontMetrics()`。

### 修复后流程
```
Step 1: __init__()
  → _setup_ui()          创建控件（默认字体）
  → _load_theme_qss()    setStyleSheet() 异步排队
  → QTimer.singleShot(0, self._deferred_init)
    ↓ 返回，当前帧结束

[下一个事件循环开始]
Step 2: _deferred_init()
  → setStyleSheet() 已生效 ✅ 字体 = 11pt
  → _adjust_size()       fontMetrics() 读到正确的 11pt ✅
  → _center_on_parent()   用正确尺寸居中 ✅
  → exec_()               显示时尺寸已是最终值，无二次渲染 ✅
```

### 关键代码（popup_dialog.py）

#### 导入修改
```python
# 之前
from PyQt5.QtCore import Qt, QSize, QRect, pyqtProperty

# 之后
from PyQt5.QtCore import Qt, QSize, QRect, QTimer, pyqtProperty
```

#### __init__ 末尾替换
```python
# 之前
self._setup_ui()
self._load_theme_qss()
self._adjust_size()
self._center_on_parent()

# 之后
self._setup_ui()
self._load_theme_qss()
# 延迟到下一个事件循环，确保 setStyleSheet() 的字体/样式已生效
QTimer.singleShot(0, self._deferred_init)

def _deferred_init(self):
    """延迟初始化：在 QSS 生效后计算尺寸并居中（避免双渲染）。"""
    self._adjust_size()
    self._center_on_parent()
```

## 经验教训

### 规则：setStyleSheet() 后不能立即读取受影响的属性
> 在 PyQt5 中调用 `setStyleSheet()` 后，**必须等到下一个事件循环**才能通过 `fontMetrics()`、`sizeHint()`、`palette()` 等方法获取到样式表设定的新值。同步读取只会拿到旧值。

### 推荐模式
| 场景 | 做法 |
|------|------|
| 设置完 QSS 后立即读取字体/颜色 | 使用 `QTimer.singleShot(0, callback)` 延迟一帧 |
| 需要在 exec_/show() 前确定尺寸 | 将尺寸计算放在 showEvent 或 singleShot(0) 中 |
| 多个连续 setStyleSheet 调用 | 合并为一次调用，减少异步重绘次数 |

### 项目中类似风险点排查
项目中所有在 `setStyleSheet()` 之后立即调用 `fontMetrics()` / `sizeHint()` 的位置：
| 文件 | 行号 | 风险评估 |
|------|------|----------|
| `popup_dialog.py` | ~~原 243-248~~ | **本次修复** |
| `crash_monitor.py` (CrashPopup) | ~320 | CrashPopup 使用独立进程运行，不受主线程事件循环影响，风险较低 |
| `settings_dialog.py` | ~180 | SettingsDialog 在 show() 时才完全可见，通常无问题 |

## 修复日期
2026-06-12
