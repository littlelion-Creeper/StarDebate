# Bug 修复记录：导航栏 SVG 图标在主题切换/状态切换时不刷新

## 摘要
导航栏按钮的 SVG 图标颜色在以下场景未正确刷新：
1. **选中→不选中**：左侧标准按钮不选中后图标颜色不变（停留在白色）
2. **模块按钮**：右侧模块构建按钮（AI写稿/AI扩写/便签/训练）完全无图标颜色切换
3. **主题切换**：切换主题后，大量按钮的 SVG 图标仍停留在旧主题色
4. **窗口控制按钮**：最小化/最大化/关闭三个按钮的颜色不跟随主题切换

## 影响范围
- **文件**:
  - `workers/nav_bar/nav_bar_manager.py` → 图标渲染/切换/刷新核心逻辑
  - `workers/nav_bar/nav_registry.py` → `NavItem` 数据类 + 颜色配置
  - `components/title_bar/title_bar.py` → 窗口控制按钮颜色刷新
  - `workers/app_config/config_manager.py` → 主题切换钩子
  - `config/nav_registry.json` → 颜色默认值配置
- **触发条件**: 点击导航按钮切换状态 / 在设置页切换主题
- **受影响按钮**:
  - 左侧：project_tree / structure_tree / match_schedule / stardebate_browser / new_debate / framework / create_speech / ref_doc / ref_cards / settings
  - 右侧：speech_writer / ai_expand / notes / training / ai_framework / cross_exam / accept_exam / plugin_manager
  - 插件区：所有插件导航按钮和面板按钮
  - 标题栏：_min_btn / _max_btn / _close_btn

## 根因分析

### Bug 1：不选中后图标不变（checked→unchecked）

原代码 `_on_nav_toggle_icon` 的不选中分支使用 `load_nav_icon()`，内部调用 `_render_svg_themed()` 通过 `SvgRenderer.get_color_map().mono_color_key` 取色。选中分支直接用 `_render_svg_colored(白色)`。**两条分支走不同渲染路径**，可能导致颜色不匹配或 QPainter 静默失败。

```python
# 原代码（有问题的 else 分支）
if btn.isChecked():
    icon = self._render_svg_colored(icon_path, white, icon_size)  # 直接指定颜色
else:
    icon = self.load_nav_icon(icon_name)  # 经 SvgRenderer 间接取色，路径不同
```

### Bug 2：模块按钮无图标切换

右侧面板按钮（speech_writer / ai_expand / notes / training / cross_examination / accept_examination / material_pool）使用模块自定义的 `build_nav_button()` 创建按钮，这些方法**没有连接 `toggled` 信号**用于图标颜色切换。

```python
# 模块 builder 中的代码（无 toggled 连接）
btn.setCheckable(True)
...
icon = NavBarManager.load_nav_icon(item.icon)
NavBarManager._apply_icon_to_button(btn, icon)
# ❌ 缺少 btn.toggled.connect(...)
```

### Bug 3：主题切换不刷新

`refresh_nav_icons()` 用 `if not btn.isCheckable(): continue` 跳过了：
- 非 checkable 的操作按钮（新建辩论/框架/资料/设置等）
- 非 checkable 的插件导航按钮

同时 `_plugin_btn_meta` 只存储面板按钮元数据，不存储插件导航按钮，导致主题切换时这些按钮的 SVG 图标数据仍为旧主题色。

### Bug 4：窗口控制按钮颜色固定

`_TitleBarButton.__init__` 在构造时通过 `tc("subtext")`、`tc("text")` 等获取主题色并存入 `QColor` 对象。主题切换后 `tc()` 缓存被清空，但按钮的 `QColor` 对象是**构造时的一次性快照**，不会自动更新。

```python
# 构造时捕获的颜色快照，不会跟随主题变化
self._clr_norm = QColor(tc("subtext"))
```

## 修复方案

### 修复 1：统一颜色渲染路径

弃用不选中分支的 `load_nav_icon()`（内部走 `_render_svg_themed`），改为与选中分支相同的 `_render_svg_colored(颜色)`，颜色通过 `_get_item_color(item_id, checked)` 统一解析。

新增方法链：
```
_get_item_color(item_id, checked)
  ├── checked=True:  icon_checked_color(按钮) → default_icon_checked_color → "white"
  └── checked=False: icon_unchecked_color(按钮) → default_icon_unchecked_color → 自动侦测
                         ├── 深色主题: mono 文字色
                         └── 浅色主题: dual_primary (蓝)
```

### 修复 2：模块按钮统一连接 toggled

在 `build()` 方法中，模块按钮返回后自动添加 `toggled.connect`：

```python
if btn.isCheckable() and item.icon:
    btn.toggled.connect(
        lambda checked, b=btn, n=item.icon, s=_icon_size, iid=item.id:
        self._on_nav_toggle_icon(b, n, s, iid)
    )
```

也更新了标准按钮 `_create_button` 的 lambda，追加 `iid=item.id` 参数以传入注册表 ID。

### 修复 3：初始加载也走注册表颜色

`_create_button` 中 checkable 按钮的初始图标改用 `_get_initial_color(item)` + `_render_svg_colored`，而非 `load_nav_icon` + `_render_svg_themed`，保证默认未选中时即为注册表配置色（浅色主题→蓝，深色主题→灰）。

```python
# 修复后的初始加载
if os.path.isfile(icon_path) and item.checkable:
    color = self._get_initial_color(item)          # 注册表颜色系统
    icon = self._render_svg_colored(icon_path, color, icon_size)
```

### 修复 4：refresh_nav_icons 全覆盖

移除 `btn.isCheckable()` 过滤，非 checkable 按钮用 `_get_theme_icon_color()` 刷新：

```python
for item_id, btn in self._buttons.items():
    ...
    if btn.isCheckable():
        color = self._get_item_color(item_id, btn.isChecked())
    else:
        color = self._get_theme_icon_color()  # ★ 新增非 checkable 分支
```

`_plugin_btn_meta` 扩展为同时存储插件导航按钮（非 checkable）和面板按钮（checkable）的元数据，在 `_add_plugin_button` 和 `_add_panel_button` 中均存入。

### 修复 5：窗口控制按钮主题刷新

`_TitleBarButton` 新增 `_auto_*` 标志跟踪哪些颜色是自动从 `tc()` 获取的，`refresh_theme_colors()` 只刷新 auto 标志为 True 的颜色：

```python
# 构造时记录
self._auto_clr_norm = not bool(icon_normal)
self._auto_clr_hover = not bool(icon_hover)
self._auto_bg_hover = not bool(bg_hover)
self._auto_bg_press = not bool(bg_pressed)
```

`TitleBar.refresh_theme_colors()` 遍历三个窗口按钮逐个刷新：
```python
def refresh_theme_colors(self):
    for btn in (self._min_btn, self._max_btn, self._close_btn):
        btn.refresh_theme_colors()
```

### 修复 6：主题切换钩子

在 `switch_theme()` 末尾依次刷新导航栏和标题栏：

```python
# switch_theme() 末尾追加
if hasattr(self._mw, '_nav_mgr'):
    self._mw._nav_mgr.refresh_nav_icons()
if hasattr(self._mw, '_title_bar'):
    self._mw._title_bar.refresh_theme_colors()
```

## 关键代码变更

### `nav_bar_manager.py` — 核心变更

| 方法 | 变更类型 | 说明 |
|------|---------|------|
| `_get_icon_color(key)` | 新增 | 颜色键名→QColor 解析（"white"→#FFFFFF，其他→tc(key)） |
| `_get_theme_icon_color()` | 重写 | 自动侦测：深色→mono，浅色→dual_primary（蓝） |
| `_get_item_color(id, checked)` | 新增 | 注册表+settings 解析最终颜色 |
| `_get_initial_color(item)` | 新增 | 初始加载时按注册表取色 |
| `_on_nav_toggle_icon` | 重写 | 统一走 `_get_item_color` + `_render_svg_colored` |
| `_on_plugin_toggle_icon` | 重写 | 选中走白，不选中走 `_get_theme_icon_color` |
| `_create_button` | 修改 | checkable 初始加载走注册表颜色系统 |
| `build()` | 修改 | 模块按钮追加 `toggled.connect`，lambda 传入 `iid` |
| `refresh_nav_icons()` | 重写 | 覆盖全部三类按钮（checkable/非checkable/插件） |
| `_add_plugin_button` | 修改 | 存入 `_plugin_btn_meta` |
| `_add_panel_button` | 修改 | 存入 `_plugin_btn_meta` |
| `rebuild_plugin_buttons` | 修改 | 清空 `_plugin_btn_meta` |

### `nav_registry.py` — 颜色配置

```python
@dataclass
class NavItem:
    ...
    icon_checked_color: str = ""    # 选中时的 theme.json 颜色键名
    icon_unchecked_color: str = ""  # 不选中时的 theme.json 颜色键名

# NavRegistry settings 属性
default_icon_checked_color   → settings["icon_checked_color"]  # 默认 "white"
default_icon_unchecked_color → settings["icon_unchecked_color"]  # 默认 ""(自动侦测)
```

### `title_bar.py` — 窗口按钮刷新

```python
class _TitleBarButton(QPushButton):
    def refresh_theme_colors(self):
        """只刷新 auto 标志为 True 的颜色（显式 hex 不变的保持）。"""
        ...

class TitleBar(QWidget):
    def refresh_theme_colors(self):
        """遍历三个窗口按钮刷新颜色。"""
        for btn in (self._min_btn, self._max_btn, self._close_btn):
            btn.refresh_theme_colors()
```

### `config/nav_registry.json` — 默认颜色

```json
"settings": {
    ...
    "icon_checked_color": "white",
    "icon_unchecked_color": ""
}
```

### `config_manager.py` — 主题切换钩子

```python
def switch_theme(self, theme_name):
    ...
    self.apply_style(theme_name)
    if hasattr(self._mw, '_nav_mgr'):
        self._mw._nav_mgr.refresh_nav_icons()
    if hasattr(self._mw, '_title_bar'):
        self._mw._title_bar.refresh_theme_colors()
    self._mw._update_status(f"主题已切换: {theme_name}")
```

## 经验教训

### 规则：QSS 级联与 `setStyleSheet` 的注意事项

> 对 QLabel 使用 `setStyleSheet("color: xxx;")` 会重置 Qt 的 QSS 级联，丢失默认的 `background-color: transparent`。必须显式声明 `background-color: transparent;`。

详见 `docs/bug_fix_records/qss_background_transparency_fix.md`。

### 规则：SVG 图标颜色切换统一走一条渲染路径

> 选中/不选中两个状态的图标颜色切换必须走**同一条渲染方法**（`_render_svg_colored`），避免 `_render_svg_themed`（经 SvgRenderer 间接取色）与 `_render_svg_colored`（直接指定颜色）之间的路径差异导致颜色不匹配或 QPainter 静默失败。

### 规则：主题色的捕获时机

> `tc()` 返回的 `QColor` 是调用时刻的快照。在构造时捕获后，主题切换时不会自动更新。需要显式调用 `refresh_tc()` 并重新读取。`_TitleBarButton` 的 `_auto_*` 标志模式可复用。

### 规则：refresh_nav_icons 必须覆盖全部类型

> 导航栏按钮有三种类型：
> 1. checkable 标准/模块按钮 → `_get_item_color(id, isChecked)`
> 2. 非 checkable 按钮（新建辩论/设置等） → `_get_theme_icon_color()`
> 3. 插件按钮（导航 + 面板） → 通过 `_plugin_btn_meta` 元数据遍历
>
> 任一遗漏都会导致该按钮在主题切换时图标不变。

### 规则：`setSizes` 前必须保证无 0 值

> 当 QSplitter 中存在隐藏 widget 时，`sizes()` 会返回 0。直接将含 0 的数组写回 `setSizes()` 会导致 QSplitter 永久记住这些 0 值。详见 `docs/bug_fix_records/fix-splitter-zero-width-freeze.md`。

## 类似风险点排查

项目中所有通过 `tc()` 捕获颜色并在运行时需要跟随主题切换的位置：

| 位置 | 当前状态 | 说明 |
|------|---------|------|
| `nav_bar_manager.py` → `_on_nav_toggle_icon` | 已修复 | 每次 toggle 实时解析 |
| `nav_bar_manager.py` → `refresh_nav_icons` | 已修复 | 主题切换时遍历刷新 |
| `title_bar.py` → `_TitleBarButton` | 已修复 | `_auto_*` 标志 + `refresh_theme_colors()` |
| `startup_banner.py` → `_load_banner_colors` | 已修复 | 每次新建横幅时读取 theme.json |
| `startup_banner.py` → 标签 setStyleSheet | 已修复 | 显式声明 `background-color: transparent` |

## 修复日期
2026-06-11
