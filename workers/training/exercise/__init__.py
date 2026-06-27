"""立论驳论子功能 — 注册元信息"""
SUB_FEATURE_INFO = {
    "id": "exercise",
    "name": "立论与驳论",
    "icon": "📝",
    "accent_color": "#89b4fa",
    "description": "AI出题·限时写作·AI对辩·综合评分",
    "tags": ["限时写作", "AI对辩", "综合评分"],
    "order": 20,
    "history_label": "论辩记录",
}


def get_manager_class():
    """返回子功能管理器类"""
    from workers.training.exercise.exercise_manager import ExerciseManager
    return ExerciseManager


__all__ = ["SUB_FEATURE_INFO", "get_manager_class"]
