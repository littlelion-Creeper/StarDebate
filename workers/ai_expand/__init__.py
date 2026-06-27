# -*- coding: utf-8 -*-
"""AI扩写功能模块

目录结构:
    workers/ai_expand/
    ├── __init__.py              # 模块导出
    ├── ai_expand_worker.py      # AIExpandWorker: AI 扩写异步线程
    └── ai_expand_manager.py     # AIExpandManager: UI 构建 + 业务逻辑 + 卡片管理

样式文件:
    style/themes/catppuccin_mocha/ai_expand.qss
"""

from .ai_expand_worker import AIExpandWorker
from .ai_expand_manager import AIExpandManager

__all__ = ["AIExpandWorker", "AIExpandManager"]
