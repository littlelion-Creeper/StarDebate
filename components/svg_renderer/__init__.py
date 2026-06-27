"""
SVG 通用渲染器 — StarDebate SVG 图标着色引擎

功能：
  - 单色渲染：所有 fill/stroke 替换为单一颜色
  - 双色渲染：按 data-color="primary"/"accent" 属性分别着色
  - 原生渲染：不替换颜色，原样输出
  - 主题跟随：颜色配置嵌入各主题 theme.json 的 svg_renderer 字段
  - LRU 缓存：避免重复渲染

调用示例:
    from components.svg_renderer import SvgRenderer

    # 单色图标
    icon = SvgRenderer.icon("icon/checkbox/checkmark_square.svg", 24)

    # 双色图标
    pix = SvgRenderer.bicolor("path/to/dual.svg", 32,
                              primary="accent_blue", accent="text")

    # 预设图标
    pix = SvgRenderer.named("checkmark", 20)

    # QIcon (含 disabled 状态)
    qicon = SvgRenderer.qicon("path/to/file.svg", 24, disabled_pct=0.4)

    # 主题切换
    SvgRenderer.set_theme("catppuccin_mocha")
"""
from .core import SvgRenderer

__all__ = ["SvgRenderer"]
