"""快速刷曲子功能 — 注册元信息"""
SUB_FEATURE_INFO = {
    "id": "quick_quiz",
    "name": "快速刷题",
    "icon": "⚡",
    "accent_color": "#f9e2af",
    "description": "随机题库，快速提升辩论能力",
    "tags": ["选择题", "判断题", "场景题"],
    "order": 10,
    "history_label": "刷题记录",
}


def get_manager_class():
    """返回子功能管理器类"""
    from workers.training.quick_quiz.quick_quiz_manager import QuickQuizManager
    return QuickQuizManager


__all__ = ["SUB_FEATURE_INFO", "get_manager_class"]
