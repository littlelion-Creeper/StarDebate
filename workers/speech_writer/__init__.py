# -*- coding: utf-8 -*-
"""AI写稿模块 - 基于辩论框架稿自动生成一辩稿

目录结构：
    workers/speech_writer/
        __init__.py              # 本文件：模块导出
        speech_writer_worker.py  # AISpeechWriterWorker：AI 写稿异步线程
        speech_writer_manager.py # SpeechWriterManager：UI 构建 + 业务逻辑 + 卡片管理
    style/themes/catppuccin_mocha/
        speech_writer.qss        # AI写稿面板 QSS 样式
"""

from .speech_writer_worker import AISpeechWriterWorker
from .speech_writer_manager import SpeechWriterManager

__all__ = ["AISpeechWriterWorker", "SpeechWriterManager"]
