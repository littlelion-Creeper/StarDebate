"""起居注自动注入钩子 — 运行时 monkey-patch (v2.0.0)
============================================================================
v2.0.0 新增:
  ★ Qt message handler 注入 — 拦截 Qt C++ 层 qWarning/qCritical/qFatal
  ★ Worker 线程异常钩子 — 捕获 QThread Worker 中未处理的异常
  ★ 全局 sys.excepthook 注册 — 由 LogClient 初始化时自动安装

不修改任何源文件，在 StarDebate 启动时注入钩子：
  1. 插件加载/卸载 (PluginInfo.enable/disable)
  2. API 调用 (monitored_api_post)
  3. AI 调用 (PluginSafeAPI.call_ai)
  4. ★ Qt 内部消息 (qInstallMessageHandler)
  5. ★ Worker 线程保护 (QThread Worker)

所有钩子保存原始引用，uninstall_chronicle() 可完全恢复。
============================================================================
"""

import sys
import traceback


def install_chronicle(log_client):
    """启动时调用一次，注入所有自动起居注钩子。

    Args:
        log_client: LogClient 实例 (含 ActivityChronicle)

    Returns:
        dict: 保存的原始引用，供 uninstall_chronicle() 恢复用
    """
    saved = {}

    # ── ① Patch 插件加载/卸载 ──────────────────────────────
    try:
        from workers.plugin_manager import PluginInfo

        saved["PluginInfo.enable"] = PluginInfo.enable
        saved["PluginInfo.disable"] = PluginInfo.disable

        def _patched_enable(self):
            @log_client.track("plugin", self.name,
                              metadata={"plugin_id": getattr(self, 'plugin_id', 'unknown')})
            def _run():
                return saved["PluginInfo.enable"](self)
            return _run()

        def _patched_disable(self):
            @log_client.track("plugin", self.name,
                              metadata={"plugin_id": getattr(self, 'plugin_id', 'unknown')})
            def _run():
                return saved["PluginInfo.disable"](self)
            return _run()

        PluginInfo.enable = _patched_enable
        PluginInfo.disable = _patched_disable

    except ImportError:
        pass

    # ── ② Patch API 调用 ──────────────────────────────────
    try:
        import workers.common.api_helper as _api_mod

        saved["monitored_api_post"] = _api_mod.monitored_api_post

        def _patched_api(*args, **kwargs):
            feature = kwargs.get("feature_name", "unknown")
            @log_client.track("api", feature,
                              metadata={"endpoint": kwargs.get("endpoint", "")[:80]})
            def _call():
                return saved["monitored_api_post"](*args, **kwargs)
            return _call()

        _api_mod.monitored_api_post = _patched_api

    except ImportError:
        pass

    # ── ③ Patch AI 调用 ───────────────────────────────────
    try:
        from workers.plugin_manager.plugin_api import PluginSafeAPI

        saved["PluginSafeAPI.call_ai"] = PluginSafeAPI.call_ai

        def _patched_call_ai(self, messages, **kwargs):
            msg_count = len(messages) if isinstance(messages, list) else 1
            model = kwargs.get("model", "unknown")[:40]
            @log_client.track("ai", "call_ai",
                              metadata={"msg_count": str(msg_count), "model": model})
            def _call():
                return saved["PluginSafeAPI.call_ai"](self, messages, **kwargs)
            return _call()

        PluginSafeAPI.call_ai = _patched_call_ai

    except ImportError:
        pass

    # ★ v2.0.0: ④ 安装 Qt message handler ─────────────────
    _install_qt_handler(log_client, saved)

    # ★ v2.0.0: ⑤ 安装 Worker 线程保护钩子 ────────────────
    _install_worker_hooks(log_client, saved)

    return saved


def uninstall_chronicle(saved: dict):
    """卸载所有起居注钩子，恢复原始方法引用。

    Args:
        saved: install_chronicle() 返回的原始引用字典
    """
    if not saved:
        return

    # ── 恢复插件方法 ──────────────────────────────────────
    if "PluginInfo.enable" in saved:
        try:
            from workers.plugin_manager import PluginInfo
            PluginInfo.enable = saved["PluginInfo.enable"]
            PluginInfo.disable = saved["PluginInfo.disable"]
        except Exception:
            pass

    # ── 恢复 API ──────────────────────────────────────────
    if "monitored_api_post" in saved:
        try:
            import workers.common.api_helper as _api_mod
            _api_mod.monitored_api_post = saved["monitored_api_post"]
        except Exception:
            pass

    # ── 恢复 AI ───────────────────────────────────────────
    if "PluginSafeAPI.call_ai" in saved:
        try:
            from workers.plugin_manager.plugin_api import PluginSafeAPI
            PluginSafeAPI.call_ai = saved["PluginSafeAPI.call_ai"]
        except Exception:
            pass

    # ★ v2.0.0: 恢复 Qt message handler
    _uninstall_qt_handler(saved)

    # ★ v2.0.0: 恢复 Worker 线程钩子
    _uninstall_worker_hooks(saved)


# ════════════════════════════════════════════════════════════
#  ★ v2.0.0: Qt message handler 注入/卸载
# ════════════════════════════════════════════════════════════

def _install_qt_handler(log_client, saved: dict):
    """安装 Qt message handler 钩子。

    拦截 Qt C++ 层的 qWarning/qCritical/qFatal 消息，
    自动标记起居注上下文为错误状态。

    qDebug 消息仅在调试模式下记录（避免噪音过多）。
    """
    try:
        from PyQt5.QtCore import qInstallMessageHandler, QtMsgType
    except ImportError:
        return

    try:
        orig_handler = qInstallMessageHandler(None)  # 获取当前 handler
        saved["qt_message_handler"] = orig_handler
    except Exception:
        orig_handler = None
        saved["qt_message_handler"] = None

    # QtMsgType 错误代码 → 文本映射
    _QT_MSG_NAMES = {
        QtMsgType.QtDebugMsg: ("DEBUG", 0),
        QtMsgType.QtWarningMsg: ("WARN", 1),
        QtMsgType.QtCriticalMsg: ("CRITICAL", 2),
        QtMsgType.QtFatalMsg: ("FATAL", 3),
        QtMsgType.QtInfoMsg: ("INFO", 4),
    }

    def _qt_handler(msg_type, context, msg):
        """Qt 消息拦截处理器 — 含完整上下文信息。

        context 字段: file, line, function, category
        msg_type: QtDebugMsg(0)/QtWarningMsg(1)/QtCriticalMsg(2)/QtFatalMsg(3)/QtInfoMsg(4)
        """
        try:
            # 提取 QMessageLogContext 信息
            ctx_file = getattr(context, 'file', '') or ''
            ctx_line = getattr(context, 'line', 0) or 0
            ctx_func = getattr(context, 'function', '') or ''
            ctx_cat = getattr(context, 'category', '') or ''

            # 构建上下文定位串
            loc_parts = []
            if ctx_file:
                fname = ctx_file.split('/')[-1].split('\\')[-1]
                loc_parts.append(fname)
            if ctx_line:
                loc_parts.append(f"L{ctx_line}")
            if ctx_func:
                fn = ctx_func.split('(')[0].split('::')[-1]
                if fn and len(fn) < 60:
                    loc_parts.append(fn)
            location = ":".join(loc_parts) if loc_parts else ""
            loc_suffix = f" [{location}]" if location else ""

            type_name, type_code = _QT_MSG_NAMES.get(msg_type, ("?", -1))

            # ★ qFatal/qCritical → 标记为错误
            if msg_type == QtMsgType.QtFatalMsg:
                full_msg = f"[Qt {type_name}#{type_code}]{loc_suffix} {msg[:200]}"
                log_client._chronicle._on_error("ERROR", full_msg)
                log_client.error(full_msg)
            elif msg_type == QtMsgType.QtCriticalMsg:
                full_msg = f"[Qt {type_name}#{type_code}]{loc_suffix} {msg[:200]}"
                log_client._chronicle._on_error("ERROR", full_msg)
                log_client.error(full_msg)
            elif msg_type == QtMsgType.QtWarningMsg:
                full_msg = f"[Qt {type_name}#{type_code}]{loc_suffix} {msg[:200]}"
                log_client.warn(full_msg)
            # QtDebugMsg / QtInfoMsg → 忽略（噪音过多）

        except Exception:
            pass

        # 调用原始 handler（如果存在）
        if orig_handler:
            try:
                orig_handler(msg_type, context, msg)
            except Exception:
                pass

    # 安装新 handler
    qInstallMessageHandler(_qt_handler)
    saved["qt_handler_func"] = _qt_handler


def _uninstall_qt_handler(saved: dict):
    """恢复 Qt message handler。"""
    orig = saved.get("qt_message_handler")
    if orig is not None:
        try:
            from PyQt5.QtCore import qInstallMessageHandler
            qInstallMessageHandler(orig)
        except Exception:
            pass


# ════════════════════════════════════════════════════════════
#  ★ v2.0.0: Worker 线程保护钩子
# ════════════════════════════════════════════════════════════

def _install_worker_hooks(log_client, saved: dict):
    """安装 QThread Worker 异常保护钩子。

    扫描 workers/ 下所有 *Worker 类，为它们的 run() 方法注入
    起居注异常捕获，确保 Worker 线程中的未处理异常被记录。
    """
    saved["worker_orig_runs"] = {}
    saved["worker_patched_classes"] = []

    # 需要 patch 的 Worker 类（模块路径 → 类名列表）
    worker_targets = [
        ("workers.ai_analysis.ai_analysis_worker", ["AnalysisWorker"]),
        ("workers.cross_examination.cross_exam_worker", ["CrossExaminationWorker"]),
        ("workers.cross_examination.accept_exam_worker", ["AcceptExaminationWorker"]),
        ("workers.speech_writer.speech_writer_worker", ["AISpeechWriterWorker"]),
        ("workers.ai_expand.ai_expand_worker", ["AIExpandWorker"]),
        ("workers.framework.framework_worker", ["AIFrameworkWorker"]),
        ("workers.structure.structure_worker", ["StructureAnalysisWorker"]),
        ("workers.training.train_question_worker", ["TrainQuestionWorker"]),
        ("workers.training.train_eval_worker", ["TrainEvalWorker"]),
        ("workers.training.exercise.exercise_topic_worker", ["DebateExerciseTopicWorker"]),
        ("workers.training.exercise.exercise_opponent_worker", ["DebateExerciseOpponentWorker"]),
        ("workers.training.exercise.exercise_eval_worker", ["DebateExerciseEvalWorker"]),
    ]

    for module_path, class_names in worker_targets:
        try:
            mod = sys.modules.get(module_path)
            if mod is None:
                __import__(module_path)
                mod = sys.modules.get(module_path)
            if mod is None:
                continue

            for class_name in class_names:
                worker_cls = getattr(mod, class_name, None)
                if worker_cls is None:
                    continue
                _patch_worker_run(log_client, saved, worker_cls, class_name)

        except Exception:
            pass


def _patch_worker_run(log_client, saved: dict, worker_cls, class_name: str):
    """为单个 Worker 类的 run() 方法注入异常保护。"""
    orig_run = getattr(worker_cls, "run", None)
    if orig_run is None:
        return

    # 保存原始方法
    key = f"worker_{class_name}_run"
    saved["worker_orig_runs"][key] = (worker_cls, orig_run)
    saved["worker_patched_classes"].append(class_name)

    def _patched_run(self):
        """带起居注保护的 run() 方法。"""
        worker_name = class_name
        ctx = log_client._chronicle.begin(
            "feature", worker_name,
            metadata={"worker": class_name}
        )
        try:
            result = orig_run(self)
            elapsed = (time_import() - start_time) * 1000
            log_client._chronicle.end(ctx, elapsed)
            return result
        except Exception as e:
            import sys as _sys
            _, _, tb = _sys.exc_info()
            log_client._chronicle._on_exception(type(e), e, tb)
            elapsed = (time_import() - start_time) * 1000
            log_client._chronicle.end(ctx, elapsed)
            raise

    # 使用闭包捕获 start_time 和 time_import
    import time as _time
    def _make_patched(orig, wname):
        def _inner(self):
            worker_name = wname
            ctx = log_client._chronicle.begin(
                "feature", worker_name,
                metadata={"worker": wname}
            )
            start = _time.time()
            try:
                result = orig(self)
                elapsed = (_time.time() - start) * 1000
                log_client._chronicle.end(ctx, elapsed)
                return result
            except Exception as e:
                import sys as _sys
                _, _, tb = _sys.exc_info()
                log_client._chronicle._on_exception(type(e), e, tb)
                elapsed = (_time.time() - start) * 1000
                log_client._chronicle.end(ctx, elapsed)
                raise
        return _inner

    worker_cls.run = _make_patched(orig_run, class_name)


def _uninstall_worker_hooks(saved: dict):
    """恢复所有被 patch 的 Worker 类。"""
    orig_runs = saved.get("worker_orig_runs", {})
    for key, (worker_cls, orig_run) in orig_runs.items():
        try:
            worker_cls.run = orig_run
        except Exception:
            pass
