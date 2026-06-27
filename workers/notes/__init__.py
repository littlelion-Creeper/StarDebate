"""
StarDebate 便签模块
===================
多文件规则结构：
- notes_manager.py : NotesManager 类（UI 构建 + 全部业务逻辑）

风格文件：
- style/themes/catppuccin_mocha/notes.qss : 便签面板专属 QSS 样式
"""

from .notes_manager import NotesManager

__all__ = ["NotesManager"]
