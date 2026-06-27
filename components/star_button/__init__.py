"""自定义按钮 — StarButton 通用组件，替代 Qt 默认 QPushButton。

排布模式:
    h_left    图标左文字右 (默认)  /  h_right    图标右文字左
    v_top     图标上文字下         /  v_bottom   图标下文字上
    text_only 仅文字              /  icon_only  仅图标

占比模式:
    sync   水平=垂直同一值 (默认)  /  hv     水平垂直分别设置
    h_only 仅水平                 /  v_only 仅垂直
    auto   同 sync

使用示例:
    from components.star_button import StarButton
    btn = StarButton("搜索", parent=self)
    btn = StarButton("保存", icon="icon/save.svg", layout_mode="h_left")
    btn = StarButton("提交", ratio_mode="hv", ratio_h=0.7, ratio_v=0.6)
    btn = StarButton("启用", checkable=True)
"""

from .star_button import StarButton

__all__ = ["StarButton"]
