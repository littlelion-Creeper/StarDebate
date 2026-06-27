"""StarSpinBox 自定义数字输入框 — 通用组件。

替代 Qt 原生 QSpinBox / QDoubleSpinBox，提供 SVG 图标渲染、动态着色、
三种布局模式切换、长按自动重复、主题自适应。

图标来源：icon/spinbox/ 目录下 4 个 SVG 模板，通过 QSvgRenderer 渲染 +
QPainter.CompositionMode 动态着色。

默认使用白色模板（icon/spinbox/white/），通过 CompositionMode_SourceIn 着色，
与 StarCheckBox v3.0 使用相同的着色机制。
"""

from components.star_spinbox.star_spinbox import StarSpinBox, StarDoubleSpinBox

__all__ = ["StarSpinBox", "StarDoubleSpinBox"]
