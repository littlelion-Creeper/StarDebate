"""自定义多选框 — StarCheckBox 通用组件，替代 Qt 默认 QCheckBox。

v3.0 着色机制：
    - 模板 SVG（square.svg / checkmark_square.svg）统一为白色
    - 渲染后通过 QPainter.CompositionMode_SourceIn + fillRect 动态着色
    - icon_scheme 支持："auto" / "white" / "black" / "#hex" / "accent_xxx"

提供与 QCheckBox 兼容的核心 API：
    - isChecked() / setChecked() / toggle()
    - toggled / stateChanged / clicked 信号
    - setText() / text()
    - setCheckboxSize() / checkboxSize()
    - iconScheme() / setIconScheme()  ← 动态色系读写

使用示例:
    from components.star_checkbox import StarCheckBox

    # 基本用法
    cb = StarCheckBox("同意用户协议", parent=self)
    cb.toggled.connect(lambda checked: print(f"选中: {checked}"))

    # 自定义大小 + 初始选中
    cb = StarCheckBox("我是会员", parent=self, checkbox_size=28, checked=True)

    # 主题跟随（默认）
    cb = StarCheckBox("自动颜色", icon_scheme="auto")

    # 自定义图标色（hex 颜色或主题配色键）
    cb = StarCheckBox("蓝色图标", icon_scheme="accent_blue")
    cb = StarCheckBox("蓝色图标", icon_scheme="#89b4fa")

    # 动态修改图标色
    cb.setIconScheme("accent_green")

    # 读取属性
    if cb.checked:
        print(cb.text())
"""

from .star_checkbox import StarCheckBox, _refresh_theme_cache, _resolve_tint_color
