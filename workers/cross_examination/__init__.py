# -*- coding: utf-8 -*-
"""模拟质询 + 模拟接质 模块

本模块将「模拟质询」（AI 自动生成质询对话）和「模拟接质」
（AI 作为对手提问 + 用户回答 + 评分）的完整功能封装为独立模块。

导出:
    CrossExaminationWorker:  模拟质询 AI 异步线程
    AcceptExaminationWorker: 模拟接质 AI 异步线程（init/respond/end 三模式）
    CrossExaminationManager: 模拟质询 UI 构建 + 业务逻辑 + 数据管理
    AcceptExaminationManager: 模拟接质 UI 构建 + 业务逻辑 + 数据管理
"""
from .cross_exam_worker import CrossExaminationWorker
from .accept_exam_worker import AcceptExaminationWorker
from .cross_exam_manager import CrossExaminationManager
from .accept_exam_manager import AcceptExaminationManager

__all__ = [
    "CrossExaminationWorker",
    "AcceptExaminationWorker",
    "CrossExaminationManager",
    "AcceptExaminationManager",
]
