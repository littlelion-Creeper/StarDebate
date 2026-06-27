"""窗口阴影容器 — 通用组件

ShadowContainer 为无边框窗口添加 QGraphicsDropShadowEffect 阴影和圆角效果。
兼容 WA_TranslucentBackground，最大化时自动禁用阴影和圆角。

用法:
    from components.shadow_container import ShadowContainer

    container = ShadowContainer(parent)
    self.setCentralWidget(container)
    content = container.get_content()
    # 将 UI 布局构建在 content 上...

    最大化/恢复时:
    container.set_maximized(True/False)
"""
from .shadow_container import ShadowContainer
