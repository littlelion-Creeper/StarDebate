"""
SVG XML 解析与颜色替换

支持:
  - 单色: 替换所有 fill/stroke 属性为目标颜色
  - 双色: 按 data-color="primary" / "accent" 属性分别替换
  - 原生: 不修改，原样返回
"""
import re
from PyQt5.QtGui import QColor


class SvgParser:
    """SVG 颜色属性提取与替换"""

    # SVG 颜色属性匹配正则
    _FILL_RE = re.compile(r'\bfill\s*=\s*["\'][^"\']*["\']', re.IGNORECASE)
    _STROKE_RE = re.compile(r'\bstroke\s*=\s*["\'][^"\']*["\']', re.IGNORECASE)
    _COLOR_ATTR_RE = re.compile(r'\bdata-color\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)

    # 非着色属性（需要跳过的 fill 值）
    _SKIP_FILL = frozenset({"none", "transparent"})
    _SKIP_STROKE = frozenset({"none", "transparent"})

    @classmethod
    def render_mono(cls, svg_content: str, color: QColor) -> str:
        """单色渲染：将所有 fill/stroke 替换为指定颜色（跳过 none/transparent）。"""
        hex_color = color.name()  # 返回 "#rrggbb" 字符串
        return cls._replace_all_colors(svg_content, fill_hex=hex_color, stroke_hex=hex_color)

    @classmethod
    def render_dual(cls, svg_content: str,
                    primary: QColor, accent: QColor) -> str:
        """双色渲染：按 data-color 属性分别着色。

        约定：
          data-color="primary" → primary 色
          data-color="accent"  → accent 色
          无 data-color 标记 → primary 色（默认作为主路径）
        """
        primary_hex = primary.name()
        accent_hex = accent.name()

        # 检查是否含有 data-color 标记
        if 'data-color=' not in svg_content:
            # 无标记 → 全部当作 primary
            return cls._replace_all_colors(svg_content, fill_hex=primary_hex,
                                           stroke_hex=primary_hex)

        # 有标记 → 拆分处理
        lines = svg_content.split('\n')
        result_lines = []
        for line in lines:
            m = cls._COLOR_ATTR_RE.search(line)
            if m:
                target = m.group(1).strip().lower()
                if target == "primary":
                    result_lines.append(cls._replace_line_colors(line, primary_hex, primary_hex))
                elif target == "accent":
                    result_lines.append(cls._replace_line_colors(line, accent_hex, accent_hex))
                else:
                    result_lines.append(line)
            else:
                # 无标记行 → 默认 primary
                result_lines.append(cls._replace_line_colors(line, primary_hex, primary_hex))

        return '\n'.join(result_lines)

    @classmethod
    def render_native(cls, svg_content: str) -> str:
        """原生渲染：不做颜色替换，直接返回。"""
        return svg_content

    # ── 内部方法 ─────────────────────────────────────────────

    @classmethod
    def _replace_all_colors(cls, svg: str, fill_hex: str, stroke_hex: str) -> str:
        """替换整个 SVG 中所有颜色属性"""
        return cls._replace_line_colors(svg, fill_hex, stroke_hex)

    @classmethod
    def _replace_line_colors(cls, line: str, fill_hex: str, stroke_hex: str) -> str:
        """替换单行中的 fill 和 stroke 属性值"""
        # 替换 fill
        def fill_replacer(m):
            attr = m.group(0)
            # 提取当前值
            val = cls._extract_attr_value(attr)
            if val.lower() in cls._SKIP_FILL:
                return attr
            return f'fill="{fill_hex}"'

        # 替换 stroke
        def stroke_replacer(m):
            attr = m.group(0)
            val = cls._extract_attr_value(attr)
            if val.lower() in cls._SKIP_STROKE:
                return attr
            return f'stroke="{stroke_hex}"'

        line = cls._FILL_RE.sub(fill_replacer, line)
        line = cls._STROKE_RE.sub(stroke_replacer, line)
        return line

    @staticmethod
    def _extract_attr_value(attr_str: str) -> str:
        """从 fill="xxx" 中提取 xxx"""
        m = re.search(r'["\']([^"\']*)["\']', attr_str)
        if m:
            return m.group(1)
        return ""

    @classmethod
    def detect_mode(cls, svg_content: str) -> str:
        """检测 SVG 模板类型：'dual' (含 data-color) 或 'mono'。"""
        if 'data-color=' in svg_content:
            return "dual"
        return "mono"
