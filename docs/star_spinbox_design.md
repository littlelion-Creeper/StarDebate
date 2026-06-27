# StarSpinBox 自定义数字输入框 — 设计方案

> 版本：v1.0.0 | 日期：2026-06-07 | 作者：StarDebate

---

## 一、组件定位

| 项目 | 说明 |
|------|------|
| **位置** | `components/star_spinbox/`（通用组件，与 StarCheckBox 同级） |
| **替代** | Qt 原生 `QSpinBox` / `QDoubleSpinBox` |
| **变体** | `StarSpinBox` (int) + `StarDoubleSpinBox` (double) |
| **图标** | `icon/spinbox/` 下的上/下三角 SVG |

---

## 二、三种布局模式 (`button_layout` 参数切换)

### 模式 A："right" (右侧竖直按钮，默认)
```
┌──────────────────────────────┬──────┐
│                              │  ▲   │  ← up_button (16px)
│         line_edit            │──────│  ← 无分割线
│         (QLineEdit)          │  ▼   │  ← down_button (16px)
└──────────────────────────────┴──────┘
←─────── spin_outer (QFrame) ──────→

尺寸: 总高 32px, 按钮区 22px 宽, 编辑区自适应
适用: 通用场景，与 Qt 原生体验一致
```

### 模式 B："split" (左右分离按钮)
```
┌──────┬──────────────────────────────┬──────┐
│  ▼   │                              │  ▲   │
│      │         line_edit            │      │
│(22px)│         (QLineEdit)          │(22px)│
└──────┴──────────────────────────────┴──────┘
←左按钮→ ←────── 编辑区 ──────────→ ←右按钮→

尺寸: 总高 32px, 左右按钮各 22×32px, 编辑区居中
适用: 步进调节、大按钮场景
```

### 模式 C："embedded" (内嵌箭头，最紧凑)
```
┌──────────────────────────────────────────────┐
│                                    ┌──────┐  │
│         line_edit                  │  ▲   │  │
│                                    │  ▼   │  │
│                                    └──────┘  │
└──────────────────────────────────────────────┘
←──────────── spin_outer (QFrame) ────────────→

尺寸: 总高 32px, 箭头区 20px 宽内嵌右侧
适用: 表格单元格内嵌、空间紧凑场景
```

### 模式对比

| 维度 | 方案 A (right) | 方案 B (split) | 方案 C (embedded) |
|------|:-----------:|:------------:|:----------:|
| 紧凑度 | ★★★ | ★★ | ★★★★ |
| 操作直观性 | ★★★★ | ★★★ | ★★★ |
| 与其他控件对齐 | ★★★ | ★★★★ | ★★★★ |
| 按钮误触风险 | 低 | 低 | 极低 |
| 适合场景 | 通用/设置页 | 步进调节 | 表格/紧凑布局 |

---

## 三、内部 Widget 层级

```
StarSpinBox (QWidget)                         ← 顶层容器
├── spin_outer (QFrame, objName="starSpinBox") ← QSS 边框/圆角在此
│   ├── line_edit (QLineEdit, objName="starSpinEdit")
│   ├── up_button (QPushButton, objName="starSpinUpBtn")
│   │   └── [SVG 图标: arrowtriangle_up_fill]
│   └── down_button (QPushButton, objName="starSpinDownBtn")
│       └── [SVG 图标: arrowtriangle_down_fill]
```

三种模式的内部布局区别：

| 模式 | QHBoxLayout 子控件顺序 |
|------|----------------------|
| A "right" | `[line_edit, vbox(up_btn, down_btn)]` |
| B "split" | `[down_btn, line_edit, up_btn]` |
| C "embedded" | `[line_edit, vbox(up_btn, down_btn)]` (无分隔线) |

---

## 四、SVG 渲染逻辑

### 4.1 动态着色方案（同 StarCheckBox v3.0 机制）

```
┌─────────────┐    ┌──────────────┐    ┌──────────────────────┐
│ SVG 模板文件 │───▶│ QSvgRenderer │───▶│ QPixmap (原始渲染)  │
│ (白色三角)   │    │ .render()    │    │ 16×16 @ HiDPI       │
└─────────────┘    └──────────────┘    └─────────┬────────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────┐
│ ★ 着色步骤 (CompositionMode_SourceIn)                       │
│                                                              │
│   painter.setCompositionMode(CompositionMode_SourceIn)       │
│   painter.fillRect(pixmap_rect, tint_color)                  │
│                                                              │
│   效果：白色像素 → tint_color / 透明像素 → 保持透明           │
│        半透明像素 → tint_color × alpha                       │
└──────────────────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌────────────────┐    ┌──────────────┐    ┌──────────────────┐
│ 缓存 key:      │◀───│ 缓存存取      │───▶│ QIcon (设到按钮) │
│ (up/down,      │    │ _cached_icons │    │ button.setIcon() │
│  size, tint)   │    │ dict          │    │ setIconSize(16)  │
└────────────────┘    └──────────────┘    └──────────────────┘
```

### 4.2 状态着色

| 状态 | 着色颜色 | 按钮背景 |
|------|---------|---------|
| Normal | theme.text | transparent |
| Hover | theme.text | theme.overlay |
| Pressed | theme.text | theme.surface (略深) |
| Disabled | theme.text + 40% 透明度 | transparent |

### 4.3 图标选择

`icon_scheme="auto"` 时，自动根据主题类型选择：
- dark 主题 → `icon/spinbox/white/` 模板
- light 主题 → `icon/spinbox/black/` 模板

也可使用 `icon_scheme="#hex"` 或 `"accent_xxx"` 自定义着色（同 StarCheckBox）。

---

## 五、组件参数

### StarSpinBox 构造参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `parent` | QWidget | None | 父控件 |
| `value` | int | 0 | 初始值 |
| `min_value` | int | 0 | 最小值 |
| `max_value` | int | 99 | 最大值 |
| `step` | int | 1 | 步长 |
| `prefix` | str | "" | 前缀 (如 "$") |
| `suffix` | str | "" | 后缀 (如 " px") |
| `button_layout` | str | "right" | 布局模式: "right"\|"split"\|"embedded" |
| `spin_height` | int | 32 | 整体高度 (≥24px) |
| `button_width` | int | 22 | 按钮区宽度 (模式A/C) 或单按钮宽 (模式B) |
| `editable` | bool | True | 是否可直接编辑 |
| `icon_scheme` | str | "auto" | 图标色系 |
| `object_name` | str | "" | QSS objectName |
| `text_align` | str | "left" | 文字对齐："left"/"center"/"right" |
| `font_size` | int/None | None | 文字大小（None=自动计算，int=固定 ≥10px） |

### StarDoubleSpinBox 额外参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `decimals` | int | 2 | 小数位数 |
| `value` | float | 0.0 | 初始值 |
| `step` | float | 1.0 | 步长 |

---

## 六、公开 API

### 值读写
- `value() -> int/float` — 获取当前值
- `setValue(v)` — 设置值 (自动 clamp)
- `setRange(min, max)` — 设置范围
- `setStep(step)` — 设置步长
- `setPrefix(s)` / `setSuffix(s)` — 设置前/后缀

### 布局切换
- `setButtonLayout(mode)` — 动态切换布局 ("right"/"split"/"embedded")
- `buttonLayout() -> str` — 获取当前布局模式
- `setSpinHeight(h)` — 调整高度 (自动重设按钮尺寸)
- `setButtonWidth(w)` — 调整按钮宽度

### 外观
- `setIconScheme(scheme)` — 图标色系
- `setEditable(bool)` — 切换可编辑/只读
- `setFontSize(size)` — 文字大小（None=自动，int=固定 ≥10px）
- `fontSize() -> int|None` — 获取文字大小
- `setTextAlign(align)` — 文字对齐（"left"/"center"/"right"）
- `textAlign() -> str` — 获取对齐方式
- `refresh_theme()` — 主题热切换刷新

### 信号
- `valueChanged(int/float)` — 值变化时发射 (兼容 QSpinBox)
- `editingFinished()` — 编辑完成 (回车/失焦)

---

## 七、交互行为

### 鼠标
- 单击 ▲/▶ 按钮：值 +step
- 单击 ▼/◀ 按钮：值 -step
- 长按按钮 (>400ms)：启动 QTimer (80ms 间隔) 持续增减
- 鼠标滚轮 (编辑区)：上滚 +step，下滚 -step

### 键盘
- ↑ 键：值 +step
- ↓ 键：值 -step
- PageUp：值 +step×10
- PageDown：值 -step×10
- 数字键：直接输入
- Enter：提交编辑，发射 editingFinished
- Esc：取消编辑，恢复原值

### 长按自动重复
```
pressDown ──400ms──▶ 首次触发 ──80ms──▶ 连续触发 ──► release
(初始延迟)          (开始加速)        (等间隔)      (停止)
```

---

## 八、四态交互样式

### objectName 清单

| objectName | 控件 | 说明 |
|------------|------|------|
| `starSpinBox` | QFrame | 外框 (圆角 + 边框 + 背景) |
| `starSpinEdit` | QLineEdit | 编辑区 |
| `starSpinUpBtn` | QPushButton | ▲ 增值按钮 |
| `starSpinDownBtn` | QPushButton | ▼ 减值按钮 |

### 状态样式

| 状态 | spin_outer | line_edit | 按钮 |
|------|-----------|-----------|------|
| Normal | bg=surface, border=1px overlay, radius=6 | bg=transparent, color=text | bg=transparent |
| Hover | border=accent_purple | - | bg=overlay, radius=3 |
| Focus | border=accent_purple | - | - |
| Disabled | opacity 40% | color=muted | 图标 40% 透明度 |

---

## 九、尺寸适配规则

### 高度
- `spin_height` ≥ 24px
- 模式 A/C：上下按钮各 = spin_height / 2
- 模式 B：左右按钮 = spin_height × spin_height

### 宽度
- 模式 A "right"：最小 72px (50+22)
- 模式 B "split"：最小 94px (22+50+22)
- 模式 C "embedded"：最小 70px (50+20)

### 文字/图标尺寸
- font_size = max(10, int(spin_height × 0.33))
- SVG 图标大小 = max(8, int(spin_height × 0.5))

---

## 十、文件结构

```
components/star_spinbox/             # ★ 通用组件目录
├── __init__.py                      # 导出 StarSpinBox, StarDoubleSpinBox
└── star_spinbox.py                  # 主体代码 (~450行)

style/themes/catppuccin_mocha/       # 深色主题
├── star_spinbox.qss                 # SpinBox 专属 QSS
└── theme.json                       # qss_files 新增 "star_spinbox.qss"

style/themes/catppuccin_latte/       # 浅色主题
└── star_spinbox.qss

style/themes/catppuccin_macchiato/   # 中深色主题
└── star_spinbox.qss

icon/spinbox/                        # ★ 已有图标
├── white/
│   ├── arrowtriangle_up_fill_white.svg
│   └── arrowtriangle_down_fill_white.svg
└── black/
    ├── arrowtriangle_up_fill_black.svg
    └── arrowtriangle_down_fill_black.svg
```

---

## 十一、使用示例

```python
from components.star_spinbox import StarSpinBox, StarDoubleSpinBox

# 模式 A (默认): 右侧竖直按钮
spin1 = StarSpinBox(value=42, min_value=0, max_value=100,
                    suffix=" 人", button_layout="right")

# 模式 B: 左右分离按钮
spin2 = StarSpinBox(value=50, step=5, button_layout="split",
                    spin_height=36, button_width=26)

# 模式 C: 紧凑嵌入 (适合表格)
spin3 = StarSpinBox(value=10, max_value=99,
                    button_layout="embedded", spin_height=28)

# 双精度浮点数
spin4 = StarDoubleSpinBox(value=0.7, min_value=0.0, max_value=2.0,
                          step=0.1, decimals=2)

# 动态切换布局
spin1.setButtonLayout("split")

# 信号连接
spin1.valueChanged.connect(lambda v: print(f"新值: {v}"))
```

---

## 十二、监视钩子

| 钩子类型 | 触发点 |
|----------|--------|
| `variable_watch` | value 值变化 (setValue/step_change/滚轮) |
| `variable_watch` | button_layout 模式切换 |
| `function_watch` | 组件构造 / setRange / setStep / refresh_theme |
| `module_watch` | 组件加载时注册 |
