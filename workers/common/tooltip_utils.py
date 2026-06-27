"""工具函数：tooltip 文本自动换行"""
def _wrap_tooltip_text(text: str, chars_per_line: int = 20) -> str:
    """将纯文本按固定字数强制换行，保留已有的 \\n 换行"""
    if not text:
        return text
    if text.strip().startswith("<html") or text.strip().startswith("<!DOCTYPE"):
        return text
    lines = text.split("\n")
    wrapped_lines = []
    for line in lines:
        if len(line) <= chars_per_line:
            wrapped_lines.append(line)
        else:
            for i in range(0, len(line), chars_per_line):
                wrapped_lines.append(line[i:i + chars_per_line])
    return "\n".join(wrapped_lines)
