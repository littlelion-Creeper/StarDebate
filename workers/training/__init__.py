"""模拟训练模块 — 注册表 + 自动发现 + 公共导出"""
import os
import importlib

# ---- 共享 Worker（供多个子功能使用）----
from workers.training.train_question_worker import TrainingQuestionWorker
from workers.training.train_eval_worker import TrainingEvalWorker

# ---- Exercise 专用 Worker（从子目录重导出，保持向后兼容）----
from workers.training.exercise.exercise_topic_worker import DebateExerciseTopicWorker
from workers.training.exercise.exercise_opponent_worker import DebateExerciseOpponentWorker
from workers.training.exercise.exercise_eval_worker import DebateExerciseEvalWorker

# ---- 子功能管理器 ----
from workers.training.training_manager import TrainingManager

# ---- 子功能注册表 ----
_SUB_FEATURES_CACHE: dict = {}
_SCANNED: bool = False

# 插件注册的子功能（{feature_id: {info, manager_class, plugin_id}}）
_PLUGIN_SUB_FEATURES: dict = {}


def register_plugin_sub_feature(plugin_id: str, info: dict, manager_class) -> bool:
    """供插件系统调用：注册一个插件提供的训练子功能。

    Args:
        plugin_id: 插件唯一ID（会自动加前缀避免冲突）
        info: SUB_FEATURE_INFO 字典（id/name/icon/description/tags/order/history_label/accent_color）
        manager_class: 管理器类（需实现 build_pages(stack) 方法）

    返回 True 成功，False 失败（id 无效或已存在）
    """
    if not isinstance(info, dict) or "id" not in info:
        return False

    # 给子功能 ID 加插件前缀，避免与内置子功能冲突
    feature_id = f"plugin_{plugin_id}_{info['id']}"
    if feature_id in _PLUGIN_SUB_FEATURES:
        return False

    # 确保 info 是独立副本（防止插件后续修改影响）
    info_copy = dict(info)
    info_copy["id"] = feature_id  # 使用带前缀的 ID
    # 标记来源，方便后续识别
    info_copy["_plugin_id"] = plugin_id

    _PLUGIN_SUB_FEATURES[feature_id] = {
        "info": info_copy,
        "get_manager": lambda mc=manager_class: mc,
        "module_path": f"plugin:{plugin_id}",
        "plugin_id": plugin_id,
    }

    # 清除缓存，下次 discover 时会合并
    reset_discovery_cache()
    return True


def unregister_plugin_sub_features(plugin_id: str):
    """供插件系统调用：注销指定插件的所有训练子功能"""
    to_remove = [
        fid for fid, data in _PLUGIN_SUB_FEATURES.items()
        if data.get("plugin_id") == plugin_id
    ]
    for fid in to_remove:
        del _PLUGIN_SUB_FEATURES[fid]

    if to_remove:
        reset_discovery_cache()


def discover_sub_features() -> dict:
    """自动扫描 workers/training/ 下所有子目录 + 插件注册的子功能。
    返回 {feature_id: {info, get_manager_class} 的有序字典（按 order 排序）。
    结果会被缓存，多次调用不会重复扫描。
    """
    global _SCANNED, _SUB_FEATURES_CACHE
    if _SCANNED:
        return _SUB_FEATURES_CACHE

    from components.res_path import get_resource_root
    base_dir = os.path.join(get_resource_root(), "workers", "training")
    discovered = {}

    for entry in sorted(os.listdir(base_dir)):
        entry_path = os.path.join(base_dir, entry)
        # 只扫描子目录，排除 __pycache__ 和特殊目录
        if not os.path.isdir(entry_path):
            continue
        if entry.startswith("__") or entry.startswith("."):
            continue
        if entry in ("style", "config"):
            continue

        init_file = os.path.join(entry_path, "__init__.py")
        if not os.path.isfile(init_file):
            continue

        try:
            # 动态导入子功能模块
            module = importlib.import_module(f"workers.training.{entry}")
            info = getattr(module, "SUB_FEATURE_INFO", None)
            if info is None:
                continue
            if not isinstance(info, dict) or "id" not in info:
                continue

            get_manager = getattr(module, "get_manager_class", None)
            if get_manager is None:
                continue

            discovered[info["id"]] = {
                "info": info,
                "get_manager": get_manager,
                "module_path": f"workers.training.{entry}",
            }
        except Exception:
            # 扫描失败不影响其他子功能
            continue

    # 合并插件注册的子功能
    discovered.update(_PLUGIN_SUB_FEATURES)

    # 按 order 排序
    _SUB_FEATURES_CACHE = dict(
        sorted(discovered.items(), key=lambda kv: kv[1]["info"].get("order", 999))
    )
    _SCANNED = True
    return _SUB_FEATURES_CACHE


def get_sub_features() -> list:
    """获取已发现的子功能信息列表（按 order 排序），方便迭代显示"""
    return [
        v["info"] for v in discover_sub_features().values()
    ]


def get_sub_feature(feature_id: str):
    """按 id 获取单个子功能"""
    return discover_sub_features().get(feature_id)


def reset_discovery_cache():
    """清除发现缓存（用于插件热重载等场景）"""
    global _SCANNED, _SUB_FEATURES_CACHE
    _SCANNED = False
    _SUB_FEATURES_CACHE = {}


__all__ = [
    "TrainingQuestionWorker",
    "TrainingEvalWorker",
    "DebateExerciseTopicWorker",
    "DebateExerciseOpponentWorker",
    "DebateExerciseEvalWorker",
    "TrainingManager",
    "discover_sub_features",
    "get_sub_features",
    "get_sub_feature",
    "reset_discovery_cache",
    "register_plugin_sub_feature",
    "unregister_plugin_sub_features",
]
