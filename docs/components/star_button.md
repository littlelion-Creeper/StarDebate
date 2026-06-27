# StarButton 自定义按钮组件

**版本**：v1.0.0 | **文件位置**：`components/star_button/`

替代 Qt 原生 QPushButton，提供 6 种排布模式、5 种占比模式、自动尺寸、竖排文字、可勾选、主题自适应绘制。

---

## 特性

- **6 种排布模式**：图标左/右、图标上/下、仅文字、仅图标
- **5 种占比模式**：同步/独立/仅水平/仅垂直/自适应（30%~90% 可调）
- **自动尺寸**：`setText()` / `setFont()` 后自动重算按钮宽高
- **竖排文字**：支持文字垂直排列
- **可勾选**：支持 QPushButton 风格的 checkable + toggled 信号
- **完整 API 兼容**：`clicked` / `pressed` / `released` / `toggled` 信号，`setText` / `setIcon` / `setCheckable` / `setChecked` 等方法
- **内置默认样式**：Normal 透明 + Hover 变色 + Accent 实色 + 主题自适应

---

## 构造函数

```python
StarButton(
    text="", parent=None,
    *,
    icon=None, icon_size=24,              # 图标
    layout_mode="h_left",                 # h_left/h_right/v_top/v_bottom/text_only/icon_only
    text_vertical=False,                  # 竖排文字
    text_align=Qt.AlignCenter,            # 文字对齐
    accent=None,                          # 主题色 hex（如 "#89b4fa"），非透明底色用
    ratio_mode="sync",                    # sync/hv/h_only/v_only/auto
    ratio_h=0.8, ratio_v=0.8,            # 占比 30%~90%
    checkable=False, checked=False,
    cursor=None, auto_size=True,
)
```

---

## 核心参数

### 排布模式 (`layout_mode`)

| 模式 | 说明 | 示意图 |
|------|------|--------|
| `h_left` | 图标左，文字右 | `[🔍 搜索]` |
| `h_right` | 图标右，文字左 | `[搜索 🔍]` |
| `v_top` | 图标上，文字下 | 图标在上，文字在下 |
| `v_bottom` | 图标下，文字上 | 文字在上，图标在下 |
| `text_only` | 仅显示文字 | `[搜索]` |
| `icon_only` | 仅显示图标 | `[🔍]` |

### 占比模式 (`ratio_mode`)

| 模式 | 说明 |
|------|------|
| `sync` | 水平 = 垂直 = 同一个百分比 |
| `hv` | 水平、垂直分别设置 |
| `h_only` | 仅控制水平占比（垂直 100%） |
| `v_only` | 仅控制垂直占比（水平 100%） |
| `auto` | 同 sync |

`ratio_h` / `ratio_v` 取值范围：**0.3 ~ 0.9**（30%~90%）

### Accent 参数

当传入 `accent` 参数（如 `accent=tc("accent_blue")`）时，按钮行为变为：

| 状态 | 外观 |
|------|------|
| Normal | `accent` 色实底 + 白色文字 |
| Hover | 深色主题 → 加亮；浅色主题 → 加深 |

不传 `accent` 时，Normal 为透明背景，文字色由 QSS/palette 继承。

---

## 信号

| 信号 | 参数 | 说明 |
|------|------|------|
| `clicked` | — | 点击时发射 |
| `pressed` | — | 按下时发射 |
| `released` | — | 释放时发射 |
| `toggled(bool)` | `checked` | checkable 模式下状态翻转 |

---

## 方法

| 方法 | 说明 |
|------|------|
| `setText(str)` / `text()` | 文字读写，自动触发布局重算 |
| `setIcon(QIcon/str/QPixmap)` / `icon()` | 图标读写 |
| `setIconSize(int/QSize)` / `iconSize()` | 图标尺寸 |
| `setCheckable(bool)` / `isCheckable()` | 是否可勾选 |
| `setChecked(bool)` / `isChecked()` / `toggle()` | 勾选状态 |
| `setEnabled(bool)` / `isEnabled()` | 启用/禁用 |
| `setFont(QFont)` / `font()` | 字体读写 |
| `setFixedSize(w, h)` | 固定尺寸（覆盖 auto_size） |
| `setObjectName(str)` | 设置 QSS 选择器（同步更新子标签） |

### 属性读写

| 属性 | 类型 | 说明 |
|------|------|------|
| `.layout_mode` | str | 排布模式（赋值时自动重建布局） |
| `.ratio_h` | float | 水平占比 |
| `.ratio_v` | float | 垂直占比 |
| `.ratio_mode` | str | 占比模式 |
| `.text_vertical` | bool | 竖排开关 |
| `.auto_size` | bool | 自动尺寸开关 |

---

## 使用示例

### 基础按钮
```python
from components.star_button import StarButton

btn = StarButton("搜索", parent=self)
btn.clicked.connect(self.on_search)
```

### 图标+文字
```python
btn = StarButton("保存", icon="icon/save.svg", layout_mode="h_left")
```

### Accent 主题色按钮
```python
from components.theme_colors import tc

btn = StarButton("保存", accent=tc("accent_blue"))
```

### 仅图标按钮
```python
btn = StarButton(icon="icon/settings.svg", layout_mode="icon_only")
```

### 自定义占比
```python
btn = StarButton("提交", ratio_mode="hv", ratio_h=0.7, ratio_v=0.6)
```

### 可勾选按钮
```python
btn = StarButton("启用", checkable=True)
btn.toggled.connect(lambda checked: print(f"选中: {checked}"))
```

### 配合 objectName 使用 QSS
```python
btn = StarButton("删除", object_name="dangerBtn")
```

### 竖排文字
```python
btn = StarButton("保存设置", text_vertical=True)
```

### 自动尺寸
```python
btn = StarButton("点击加载更多内容", auto_size=True)
```

---

## QSS 说明

StarButton 的 `paintEvent` 完全接管了背景/圆角绘制，因此 QSS 中针对按钮的 `background-color`、`border`、`border-radius` 等属性**不会生效**。文字颜色可通过 QLabel 子标签（`#starBtnText`）的 QSS 控制。

推荐通过 `accent` 参数或 `objectName` + `main.qss` 中的 `color` 属性来定制外观。
