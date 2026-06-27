"""一辩稿编辑模块

提供：
- SpeechEditor: IDE 风格编辑器（行号+当前行高亮+等宽字体）
- SpeechEditorManager: 一辩稿编辑管理器（UI构建+业务逻辑）
- KeywordCard: 关键词卡片组件
- AddKeywordButton: 添加关键词按钮
"""

from .speech_editor_widget import (
    SpeechEditor, KeywordCard, AddKeywordButton, _wrap_tooltip_text,
)
from .speech_editor_manager import SpeechEditorManager
