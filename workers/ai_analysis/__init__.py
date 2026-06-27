# -*- coding: utf-8 -*-
"""AI 分析模块 — 一辩稿 AI 分析功能

导出:
    AnalysisWorker:  AI 分析异步线程
    AIAnalysisManager:  UI 构建 + 业务逻辑管理器
"""
from .ai_analysis_worker import AnalysisWorker
from .ai_analysis_manager import AIAnalysisManager

__all__ = ["AnalysisWorker", "AIAnalysisManager"]
