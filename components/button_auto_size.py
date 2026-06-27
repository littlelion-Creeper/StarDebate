"""按钮/控件自动尺寸工具

提供三个函数：
  - calc_auto_size(widget, text, ...) → (w, h)  计算理想尺寸
  - set_fixed_size_by_text(widget, text, ...)     设置固定尺寸
  - set_text_auto_size(widget, text, ...)         设置文字+自动调尺寸

适用场景：QPushButton / SiPushButton / QLabel / StarButton 等所有 QWidget 子类。
SiPushButton 需传入 text_setter: lambda t: btn.label.setText(t)
"""

from PyQt5.QtGui import QFont, QFontMetrics
from PyQt5.QtWidgets import QWidget, QApplication


def calc_auto_size(
    widget: QWidget,
    text: str,
    pad_w: int = 40,
    pad_h: int = 16,
    min_w: int = 20,
    min_h: int = 36,
) -> tuple[int, int]:
    """根据控件当前字体 + 文字内容计算最小合适宽高

    Args:
        widget: 任意 QWidget 子类（用于取 font()）
        text:  需要显示的文本
        pad_w: 水平两侧 padding 总和
        pad_h: 垂直两侧 padding 总和
        min_w: 最小宽度下限
        min_h: 最小高度下限

    Returns:
        (width, height) 像素值
    """
    font = widget.font()
    if not font or font.family() == "":
        font = QFont()
        font.setPixelSize(14)
    fm = QFontMetrics(font)
    w = max(fm.horizontalAdvance(text) + pad_w, min_w)
    h = max(fm.height() + pad_h, min_h)
    return (w, h)


def set_fixed_size_by_text(widget: QWidget, text: str, **kw):
    """以 calc_auto_size 计算的值调用 widget.setFixedSize()

    可传入 calc_auto_size 的全部关键字参数：pad_w / pad_h / min_w / min_h
    """
    w, h = calc_auto_size(widget, text, **kw)
    widget.setFixedSize(w, h)


def set_text_auto_size(
    widget: QWidget,
    text: str,
    text_setter=None,
    **kw,
):
    """设置文字并自动调整控件尺寸

    典型用法:
        # QPushButton / QLabel（有 setText 方法）
        set_text_auto_size(btn, "测试连接")

        # SiPushButton（需指定 text_setter）
        set_text_auto_size(si_btn, "显示",
                           text_setter=lambda t: si_btn.label.setText(t))

    Args:
        widget:    目标控件
        text:      要设置的文字
        text_setter: 文字设置回调，默认使用 widget.setText()
        **kw:      传给 set_fixed_size_by_text 的额外参数
    """
    if text_setter is not None:
        text_setter(text)
    else:
        set_text = getattr(widget, "setText", None)
        if set_text is None:
            raise TypeError(
                f"{type(widget).__name__} 没有 setText 方法，请提供 text_setter"
            )
        set_text(text)
    set_fixed_size_by_text(widget, text, **kw)
