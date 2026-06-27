"""命令处理器 — 调试台命令解析与执行

从 config/command_defs.json 加载命令树（树形结构，空格分隔节点），
支持树遍历执行、逐级补全列表获取、插件动态注册命令。

命令树结构：
    命令集（根）→ 子命令集（可无限嵌套）→ 后缀（具体值 / <参数>）
"""

import os
import json
from typing import Optional, Callable


# ── 命令树加载 ──────────────────────────────────────────────

from components.res_path import get_resource_root


def load_command_tree() -> dict:
    """从 JSON 文件加载命令树。"""
    path = os.path.join(get_resource_root(), "config", "command_defs.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("tree", {})
    except Exception:
        return {}


# 全局命令树缓存（初始加载后常驻内存）
_COMMAND_TREE = load_command_tree()


def get_command_tree() -> dict:
    """获取当前命令树。"""
    return _COMMAND_TREE


def walk_tree(tree: dict, path_tokens: list[str]) -> Optional[dict]:
    """沿路径遍历树，返回最后一个节点（或其 meta 字典）。"""
    node = tree
    for token in path_tokens:
        if not isinstance(node, dict):
            return None
        # 子节点匹配：优先精确匹配
        children = node.get("children", {})
        if token in children:
            node = children[token]
        elif token in node:
            node = node[token]
        else:
            # 尝试模糊匹配（如 <参数ID> 匹配任何输入）
            matched = None
            for key in children:
                if key.startswith("<") and key.endswith(">"):
                    matched = children[key]
                    break
            if matched is not None:
                node = matched
            else:
                # 尝试 node 自身是否有匹配的 key
                for key in node:
                    if key.startswith("<") and key.endswith(">"):
                        matched = node[key]
                        break
                if matched is not None:
                    node = matched
                else:
                    return None
    return node


def get_node_completions(node: dict) -> list:
    """获取节点的下一级补全列表。
    
    Returns:
        每项为 dict: {"name": str, "dynamic": str or None, "is_placeholder": bool}
    """
    completions = []
    children = node.get("children", node) if isinstance(node, dict) else {}
    if not isinstance(children, dict):
        return completions

    for key, val in children.items():
        if key.startswith("_"):
            continue  # 跳过 _meta 等内部键
        entry = {"name": key, "dynamic": None, "is_placeholder": False}
        if isinstance(val, dict):
            dyn = val.get("dynamic")
            if dyn is not None:
                entry["dynamic"] = dyn
        if key.startswith("<") and key.endswith(">"):
            entry["is_placeholder"] = True
        completions.append(entry)

    return completions


def get_node_meta(node: dict) -> dict:
    """获取节点的元数据（cmd/args/desc/cat）。"""
    if isinstance(node, dict):
        meta = node.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}
        return meta
    return {}


def get_flat_help_list(tree: dict, prefix: str = "") -> list[dict]:
    """递归展开树为扁平命令列表（用于 help 显示）。"""
    results = []
    for key, val in tree.items():
        if key.startswith("_"):
            continue
        full_cmd = f"{prefix} {key}".strip() if prefix else key
        if isinstance(val, dict):
            meta = get_node_meta(val)
            children = val.get("children", {})
            # 过滤掉动态/占位子节点
            real_children = {k: v for k, v in children.items()
                             if not k.startswith("<")}
            if real_children:
                # 有子节点 → 递归
                results.extend(get_flat_help_list(real_children, full_cmd))
            else:
                # 无子节点或仅有占位 → 叶节点
                if "dynamic" not in val:
                    entry = {"cmd": full_cmd, "args": meta.get("args", ""),
                             "desc": meta.get("desc", ""), "cat": meta.get("cat", "未分类")}
                    results.append(entry)
        else:
            # 简单值 → 叶节点
            pass
    return results


# ── 命令处理器 ──────────────────────────────────────────────

class CommandHandler:
    """调试台命令解析与执行器。

    从 command_defs.json 加载命令树，支持树遍历执行和多级补全。
    """

    MAX_HISTORY = 50

    ALIASES_FILE = ""

    def __init__(self):
        self._history: list[str] = []
        self._history_index: int = -1
        self._plugin_handlers: dict[str, Callable] = {}
        self._tree = get_command_tree()
        self._aliases: dict[str, str] = {}
        self._load_aliases()

    def get_tree(self) -> dict:
        """返回当前命令树。"""
        return self._tree

    def reload(self):
        """重新加载命令树。"""
        global _COMMAND_TREE
        _COMMAND_TREE = load_command_tree()
        self._tree = _COMMAND_TREE

    # ── 历史记录 ──────────────────────────────────────────────

    def add_history(self, cmd: str):
        cmd = cmd.strip()
        if not cmd:
            return
        if self._history and self._history[-1] == cmd:
            return
        self._history.append(cmd)
        if len(self._history) > self.MAX_HISTORY:
            self._history.pop(0)
        self._history_index = len(self._history)

    def history_up(self) -> Optional[str]:
        if not self._history:
            return None
        if self._history_index > 0:
            self._history_index -= 1
        return self._history[self._history_index]

    def history_down(self) -> Optional[str]:
        if not self._history:
            return None
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            return self._history[self._history_index]
        else:
            self._history_index = len(self._history)
            return ""

    # ── 插件命令管理 ──────────────────────────────────────

    def set_plugin_commands(self, commands: list[dict]):
        """设置插件动态注册的命令列表。
        
        Args:
            commands: 每项含 cmd/args/desc/cat/handler_fn/plugin_id
        """
        self._plugin_handlers.clear()
        for entry in commands:
            cmd_name = entry.get("cmd", "").replace(":", " ")
            handler = entry.get("handler_fn")
            if cmd_name and handler:
                self._plugin_handlers[cmd_name] = handler

    def get_plugin_command_names(self) -> list[str]:
        return list(self._plugin_handlers.keys())

    # ── 别名管理 ──────────────────────────────────────────

    def _aliases_path(self) -> str:
        if not self.ALIASES_FILE:
            self.ALIASES_FILE = os.path.join(
                get_resource_root(), "config", "aliases.json"
            )
        return self.ALIASES_FILE

    def _load_aliases(self):
        path = self._aliases_path()
        try:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    self._aliases = json.load(f)
        except Exception:
            self._aliases = {}

    def _save_aliases(self):
        path = self._aliases_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._aliases, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_aliases(self) -> dict[str, str]:
        return dict(self._aliases)

    def set_alias(self, name: str, command: str) -> bool:
        if not name or not command:
            return False
        self._aliases[name] = command
        self._save_aliases()
        return True

    def remove_alias(self, name: str) -> bool:
        if name in self._aliases:
            del self._aliases[name]
            self._save_aliases()
            return True
        return False

    def expand_alias(self, cmd_line: str) -> str:
        """如果命令开头匹配别名，展开为完整命令。"""
        first = cmd_line.split(maxsplit=1)[0] if cmd_line else ""
        if first in self._aliases:
            expansion = self._aliases[first]
            rest = cmd_line[len(first):].strip()
            return f"{expansion} {rest}".strip() if rest else expansion
        return cmd_line

    # ── 命令执行 ──────────────────────────────────────────────

    def execute(self, cmd_line: str,
                log_fn: Callable[[str, str], None],
                mw=None) -> bool:
        """解析并执行一条命令。

        沿命令树逐层匹配，最长的匹配路径为命令名，剩余部分为参数。
        """
        cmd_line = cmd_line.strip()
        if not cmd_line:
            return True

        # !! 重复上一条命令
        if cmd_line == "!!":
            if self._history:
                return self.execute(self._history[-1], log_fn, mw)
            log_fn("WARN", "没有可重复的历史命令")
            return True

        # 展开别名
        expanded = self.expand_alias(cmd_line)
        if expanded != cmd_line:
            log_fn("INFO", f"展开别名: {cmd_line} → {expanded}")
            cmd_line = expanded

        tokens = cmd_line.split()

        # 优先匹配插件命令
        for end in range(len(tokens), 0, -1):
            path_str = " ".join(tokens[:end]).lower()
            if path_str in self._plugin_handlers:
                args = " ".join(tokens[end:])
                try:
                    result = self._plugin_handlers[path_str](args)
                    if result is not None and isinstance(result, str):
                        log_fn("INFO", f"[插件] {result}")
                except Exception as e:
                    log_fn("ERROR", f"插件命令执行异常: {e}")
                return True

        # 匹配内置命令
        for end in range(len(tokens), 0, -1):
            path_tokens = tokens[:end]
            args = " ".join(tokens[end:])
            node = walk_tree(self._tree, path_tokens)
            if node is not None:
                if self._dispatch_command(path_tokens, args, log_fn, mw):
                    return True

        log_fn("ERROR", f"未知命令: {cmd_line}  （输入 help 查看可用命令）")
        return False

    def _dispatch_command(self, path_tokens: list[str], args: str,
                          log_fn: Callable, mw) -> bool:
        """根据路径分派到对应命令处理方法。"""
        path_str = " ".join(path_tokens).lower()

        # ── 基本操作 ──
        if path_str == "help":
            self._cmd_help(log_fn)
            return True
        elif path_str == "clear":
            log_fn("__CLEAR__", "")
            return True
        elif path_str == "status":
            self._cmd_status(log_fn, mw)
            return True

        # ── 日志命令 ──
        elif path_str == "log level":
            self._cmd_log_level(log_fn, args)
            return True
        elif path_str == "log export":
            self._cmd_log_export(log_fn, mw)
            return True
        elif path_str == "log clean":
            self._cmd_log_clean(log_fn, mw)
            return True
        elif path_str == "log path":
            self._cmd_log_path(log_fn, mw)
            return True
        elif path_str == "log keep":
            self._cmd_log_keep(log_fn, mw)
            return True

        # ── 配置命令 ──
        elif path_str == "config show":
            self._cmd_config_show(log_fn, mw)
            return True
        elif path_str == "config reload":
            self._cmd_config_reload(log_fn, mw)
            return True

        # ── 插件命令 ──
        elif path_str == "plugin list":
            self._cmd_plugin_list(log_fn, mw)
            return True
        elif path_str == "plugin info":
            self._cmd_plugin_info(log_fn, mw, args)
            return True

        # ── 系统命令 ──
        elif path_str == "version":
            self._cmd_version(log_fn, mw)
            return True
        elif path_str == "theme":
            self._cmd_theme(log_fn, mw)
            return True
        elif path_str == "theme list":
            self._cmd_theme_list(log_fn, mw)
            return True
        elif path_str == "api test":
            self._cmd_api_test(log_fn, mw)
            return True

        # ── 计时器命令 ──
        elif path_str == "timer start":
            self._cmd_timer_start(log_fn, args)
            return True
        elif path_str == "timer stop":
            self._cmd_timer_stop(log_fn)
            return True

        # ── 插件管理增强 ──
        elif path_str == "plugin reload":
            self._cmd_plugin_reload(log_fn, mw)
            return True
        elif path_str == "plugin disable":
            self._cmd_plugin_disable(log_fn, mw, args)
            return True
        elif path_str == "plugin enable":
            self._cmd_plugin_enable(log_fn, mw, args)
            return True

        # ── 主题增强 ──
        elif path_str == "theme set":
            self._cmd_theme_set(log_fn, mw, args)
            return True
        elif path_str == "theme reload":
            self._cmd_theme_reload(log_fn, mw)
            return True

        # ── API 增强 ──
        elif path_str == "api models":
            self._cmd_api_models(log_fn, mw)
            return True
        elif path_str == "api config":
            self._cmd_api_config(log_fn, mw)
            return True

        # ── 调试监视 ──
        elif path_str == "monitor status":
            self._cmd_monitor_status(log_fn, mw)
            return True
        elif path_str == "monitor enable":
            self._cmd_monitor_enable(log_fn, mw, args)
            return True
        elif path_str == "monitor disable":
            self._cmd_monitor_disable(log_fn, mw, args)
            return True
        elif path_str == "monitor log view":
            self._cmd_monitor_log_view(log_fn, mw)
            return True
        elif path_str == "monitor log export":
            self._cmd_monitor_log_export(log_fn, mw)
            return True

        # ── 面板导航 ──
        elif path_str == "panel open":
            self._cmd_panel_open(log_fn, mw, args)
            return True
        elif path_str == "panel close":
            self._cmd_panel_close(log_fn, mw)
            return True

        # ── 项目管理 ──
        elif path_str == "project info":
            self._cmd_project_info(log_fn, mw)
            return True
        elif path_str == "project list":
            self._cmd_project_list(log_fn, mw)
            return True

        # ── 别名管理 ──
        elif path_str == "alias set":
            self._cmd_alias_set(log_fn, args)
            return True
        elif path_str == "alias remove":
            self._cmd_alias_remove(log_fn, args)
            return True
        elif path_str == "alias list":
            self._cmd_alias_list(log_fn)
            return True

        # ── 系统诊断 ──
        elif path_str == "check":
            self._cmd_check_all(log_fn, mw)
            return True
        elif path_str == "check all":
            self._cmd_check_all(log_fn, mw)
            return True
        elif path_str == "check manager":
            self._cmd_check_manager(log_fn, mw)
            return True
        elif path_str == "check plugin":
            self._cmd_check_plugin(log_fn, mw)
            return True
        elif path_str == "check panel":
            self._cmd_check_panel(log_fn, mw)
            return True

        return False

    # ═══════════════════════════════════════════════════
    #  命令实现（与原来相同，仅更新 help 换行符）
    # ═══════════════════════════════════════════════════

    def _cmd_help(self, log_fn):
        flat = get_flat_help_list(self._tree)
        # 添加插件命令
        for pname in self._plugin_handlers:
            flat.append({"cmd": pname, "args": "", "desc": "插件自定义命令",
                         "cat": "插件命令"})
        log_fn("INFO", "═══ 可用命令列表 ═══")
        current_cat = ""
        for entry in sorted(flat, key=lambda x: (x.get("cat", ""), x["cmd"])):
            if entry["cat"] != current_cat:
                current_cat = entry["cat"]
                log_fn("INFO", f"  ── {current_cat} ──")
            args_str = f" {entry['args']}" if entry.get("args") else ""
            log_fn("INFO", f"  {entry['cmd']}{args_str}  —  {entry.get('desc', '')}")
        log_fn("INFO", "═══ 共 {} 条命令 ═══".format(len(flat)))

    def _cmd_status(self, log_fn, mw):
        log_fn("INFO", "═══ StarDebate 系统状态 ═══")
        if mw and hasattr(mw, "_app_cfg"):
            try:
                ver = mw._app_cfg.get_app_version()
                log_fn("INFO", f"  版本: {ver}")
            except Exception:
                log_fn("INFO", "  版本: 未知")
        if mw and hasattr(mw, "_app_cfg"):
            try:
                theme = mw._app_cfg.get_theme_name()
                log_fn("INFO", f"  主题: {theme}")
            except Exception:
                log_fn("INFO", "  主题: 未知")
        if mw:
            log_fn("INFO", f"  当前项目: {getattr(mw, 'current_debate_path', '无') or '无'}")
        if mw and hasattr(mw, "_plugin_manager"):
            try:
                plugins = mw._plugin_manager.get_enabled_plugins()
                log_fn("INFO", f"  已安装插件: {len(plugins)} 个")
            except Exception:
                log_fn("INFO", "  已安装插件: 未知")
        else:
            log_fn("INFO", "  已安装插件: 未知")
        log_fn("INFO", "  API 连接: 未测试 (输入 api test 测试)")

    def _cmd_log_level(self, log_fn, args):
        levels = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3}
        if args.upper() in levels:
            log_fn("__LEVEL__", args.upper())
            log_fn("INFO", f"日志显示级别已设为: {args.upper()}")
        else:
            log_fn("WARN", f"无效级别: {args}  （可选: DEBUG, INFO, WARN, ERROR）")

    def _cmd_log_export(self, log_fn, mw):
        if mw and hasattr(mw, "_debug_log_mgr"):
            path = mw._debug_log_mgr.export_log()
            if path:
                log_fn("INFO", f"日志已导出至: {path}")
                log_fn("__DIALOG_INFO__", f"日志导出成功\n{path}")
            else:
                log_fn("ERROR", "日志导出失败")
        else:
            log_fn("WARN", "无法访问日志管理器")

    def _cmd_log_clean(self, log_fn, mw):
        if mw and hasattr(mw, "_debug_log_mgr"):
            log_dir = mw._debug_log_mgr.log_dir
            before = 0
            if os.path.isdir(log_dir):
                before = len([f for f in os.listdir(log_dir) if f.endswith('.log')])
            n = mw._debug_log_mgr.manual_clean()
            after = 0
            if os.path.isdir(log_dir):
                after = len([f for f in os.listdir(log_dir) if f.endswith('.log')])
            log_fn("INFO", f"已清理 {n} 个过期日志文件 （剩余 {after} 个日志文件）")
        else:
            log_fn("WARN", "无法访问日志管理器")

    def _cmd_log_path(self, log_fn, mw):
        if mw and hasattr(mw, "_debug_log_mgr"):
            log_fn("INFO", f"日志文件: {mw._debug_log_mgr.log_path}")
        else:
            log_fn("WARN", "无法访问日志管理器")

    def _cmd_log_keep(self, log_fn, mw):
        """一次性命令：保留本次运行日志，正常退出时不删除。"""
        log_cfg_path = os.path.join(
            get_resource_root(), "config", "log_settings.json")
        try:
            with open(log_cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if cfg.get("log_service", {}).get("keep_normal_exit_log", False):
                log_fn("INFO", "已标记过保留，本次退出日志不会删除")
            else:
                cfg.setdefault("log_service", {})["keep_normal_exit_log"] = True
                with open(log_cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                log_fn("INFO", "✓ 已标记保留，此次退出时日志不会被删除")
        except Exception as e:
            log_fn("ERROR", f"标记保留日志失败: {e}")

    def _cmd_config_show(self, log_fn, mw):
        if mw and hasattr(mw, "_app_cfg"):
            try:
                config = mw._app_cfg.load_full_config()
                api_config = mw._app_cfg.load_api_config()
                log_fn("INFO", "═══ 应用配置 ═══")
                log_fn("INFO", f"  config.json: {json.dumps(config, ensure_ascii=False)}")
                if api_config:
                    masked = dict(api_config)
                    if "api_key" in masked and masked["api_key"]:
                        key = str(masked["api_key"])
                        if len(key) > 6:
                            masked["api_key"] = key[:4] + "****" + key[-2:]
                    log_fn("INFO", f"  api_config.json: {json.dumps(masked, ensure_ascii=False)}")
            except Exception as e:
                log_fn("ERROR", f"读取配置失败: {e}")
        else:
            log_fn("WARN", "无法访问配置管理器")

    def _cmd_config_reload(self, log_fn, mw):
        if mw and hasattr(mw, "_app_cfg"):
            try:
                mw._app_cfg.load_api_config()
                mw._app_cfg.load_full_config()
                if hasattr(mw._app_cfg, "refresh_version_display"):
                    mw._app_cfg.refresh_version_display()
                log_fn("INFO", "配置已重新加载")
            except Exception as e:
                log_fn("ERROR", f"重新加载配置失败: {e}")
        else:
            log_fn("WARN", "无法访问配置管理器")

    def _cmd_plugin_list(self, log_fn, mw):
        if mw and hasattr(mw, "_plugin_manager"):
            try:
                all_plugins = mw._plugin_manager.get_all_plugins()
                log_fn("INFO", f"═══ 已安装插件 ({len(all_plugins)} 个) ═══")
                for p in all_plugins:
                    status = "● 启用" if p.enabled else "○ 禁用"
                    log_fn("INFO", f"  {status}  {p.plugin_id} — {p.name} v{p.version}")
            except Exception as e:
                log_fn("ERROR", f"获取插件列表失败: {e}")
        else:
            log_fn("WARN", "无法访问插件管理器")

    def _cmd_plugin_info(self, log_fn, mw, args):
        if not args:
            log_fn("WARN", "用法: plugin info <插件ID>")
            return
        if mw and hasattr(mw, "_plugin_manager"):
            try:
                info = mw._plugin_manager.get_plugin(args)
                if info:
                    log_fn("INFO", f"═══ 插件详情: {info.plugin_id} ═══")
                    log_fn("INFO", f"  名称: {info.name}")
                    log_fn("INFO", f"  版本: {info.version}")
                    log_fn("INFO", f"  作者: {getattr(info, 'author', '未知')}")
                    log_fn("INFO", f"  描述: {getattr(info, 'description', '')}")
                    log_fn("INFO", f"  状态: {'启用' if info.enabled else '禁用'}")
                else:
                    log_fn("WARN", f"未找到插件: {args}")
            except Exception as e:
                log_fn("ERROR", f"获取插件信息失败: {e}")
        else:
            log_fn("WARN", "无法访问插件管理器")

    def _cmd_version(self, log_fn, mw):
        if mw and hasattr(mw, "_app_cfg"):
            try:
                ver = mw._app_cfg.get_app_version()
                log_fn("INFO", f"StarDebate 版本: {ver}")
            except Exception:
                log_fn("INFO", "StarDebate 版本: 未知")
        else:
            log_fn("INFO", "StarDebate 版本: 未知")

    def _cmd_theme(self, log_fn, mw):
        if mw and hasattr(mw, "_app_cfg"):
            try:
                theme = mw._app_cfg.get_theme_name()
                log_fn("INFO", f"当前主题: {theme}")
            except Exception:
                log_fn("INFO", "当前主题: 未知")
        else:
            log_fn("INFO", "当前主题: 未知")

    def _cmd_theme_list(self, log_fn, mw):
        if mw and hasattr(mw, "_app_cfg"):
            try:
                themes_dir = mw._app_cfg.get_themes_dir()
                if os.path.isdir(themes_dir):
                    themes = [
                        d for d in os.listdir(themes_dir)
                        if os.path.isdir(os.path.join(themes_dir, d))
                        and os.path.exists(os.path.join(themes_dir, d, "theme.json"))
                    ]
                    log_fn("INFO", f"═══ 可用主题 ({len(themes)} 个) ═══")
                    for t in themes:
                        try:
                            with open(os.path.join(themes_dir, t, "theme.json"),
                                      "r", encoding="utf-8") as f:
                                meta = json.load(f)
                            tp = {"dark": "🌙 深色", "light": "☀ 浅色"}.get(meta.get("type", ""), "未知")
                            log_fn("INFO", f"  {tp}  {t} — {meta.get('name', t)}")
                        except Exception:
                            log_fn("INFO", f"  {t}")
                else:
                    log_fn("WARN", f"主题目录不存在: {themes_dir}")
            except Exception as e:
                log_fn("ERROR", f"获取主题列表失败: {e}")
        else:
            log_fn("WARN", "无法访问配置管理器")

    def _cmd_api_test(self, log_fn, mw):
        if mw and hasattr(mw, "_app_cfg"):
            try:
                api_config = mw._app_cfg.load_api_config()
                api_url = api_config.get("api_url", "")
                api_key = api_config.get("api_key", "")
                if not api_url or not api_key:
                    log_fn("WARN", "API 配置不完整，请先在设置中配置 API")
                    return
                log_fn("INFO", f"正在测试 API 连接: {api_url} ...")
                try:
                    import requests
                    headers = {"Authorization": f"Bearer {api_key}",
                               "Content-Type": "application/json"}
                    resp = requests.get(api_url.rstrip("/") + "/models",
                                        headers=headers, timeout=10)
                    if resp.status_code == 200:
                        log_fn("INFO", "✅ API 连接正常")
                    else:
                        log_fn("WARN", f"⚠  API 返回状态码: {resp.status_code}")
                except ImportError:
                    log_fn("WARN", "未安装 requests 库，跳过 API 测试")
                except Exception as e:
                    log_fn("ERROR", f"❌ API 连接失败: {e}")
            except Exception as e:
                log_fn("ERROR", f"加载 API 配置失败: {e}")
        else:
            log_fn("WARN", "无法访问配置管理器")

    def _cmd_timer_start(self, log_fn, args):
        try:
            seconds = int(args)
            if seconds <= 0:
                log_fn("WARN", "秒数必须为正整数")
                return
            log_fn("INFO", f"⏱ 计时器已启动: {seconds} 秒")
            log_fn("__TIMER_START__", str(seconds))
        except ValueError:
            log_fn("WARN", f"无效秒数: {args}  （示例: timer start 300）")

    def _cmd_timer_stop(self, log_fn):
        log_fn("__TIMER_STOP__", "")
        log_fn("INFO", "⏱ 计时器已停止")

    # ═══════════════════════════════════════════════════
    #  插件管理增强
    # ═══════════════════════════════════════════════════

    def _cmd_plugin_reload(self, log_fn, mw):
        if mw and hasattr(mw, "_plugin_manager"):
            try:
                mw._plugin_manager.reload_all()
                log_fn("INFO", "所有插件已重新加载")
            except Exception as e:
                log_fn("ERROR", f"重新加载插件失败: {e}")
        else:
            log_fn("WARN", "无法访问插件管理器")

    def _cmd_plugin_disable(self, log_fn, mw, args):
        if not args:
            log_fn("WARN", "用法: plugin disable <插件ID>")
            return
        if mw and hasattr(mw, "_plugin_manager"):
            try:
                mw._plugin_manager.disable_plugin(args)
                log_fn("INFO", f"插件已禁用: {args}")
            except Exception as e:
                log_fn("ERROR", f"禁用插件失败: {e}")
        else:
            log_fn("WARN", "无法访问插件管理器")

    def _cmd_plugin_enable(self, log_fn, mw, args):
        if not args:
            log_fn("WARN", "用法: plugin enable <插件ID>")
            return
        if mw and hasattr(mw, "_plugin_manager"):
            try:
                mw._plugin_manager.enable_plugin(args)
                log_fn("INFO", f"插件已启用: {args}")
            except Exception as e:
                log_fn("ERROR", f"启用插件失败: {e}")
        else:
            log_fn("WARN", "无法访问插件管理器")

    # ═══════════════════════════════════════════════════
    #  主题增强
    # ═══════════════════════════════════════════════════

    def _cmd_theme_set(self, log_fn, mw, args):
        if not args:
            log_fn("WARN", "用法: theme set <主题名>")
            return
        if mw and hasattr(mw, "_app_cfg"):
            try:
                mw._app_cfg.switch_theme(args)
                log_fn("INFO", f"主题已切换为: {args}")
            except Exception as e:
                log_fn("ERROR", f"切换主题失败: {e}")
        else:
            log_fn("WARN", "无法访问配置管理器")

    def _cmd_theme_reload(self, log_fn, mw):
        if mw and hasattr(mw, "apply_style"):
            try:
                mw.apply_style()
                log_fn("INFO", "当前主题 QSS 已重新加载")
            except Exception as e:
                log_fn("ERROR", f"重新加载主题失败: {e}")
        else:
            log_fn("WARN", "无法重新加载主题")

    # ═══════════════════════════════════════════════════
    #  API 增强
    # ═══════════════════════════════════════════════════

    def _cmd_api_models(self, log_fn, mw):
        if mw and hasattr(mw, "_app_cfg"):
            try:
                api_config = mw._app_cfg.load_api_config()
                api_url = api_config.get("api_url", "")
                api_key = api_config.get("api_key", "")
                if not api_url or not api_key:
                    log_fn("WARN", "API 配置不完整，请先配置 API")
                    return
                try:
                    import requests
                    headers = {"Authorization": f"Bearer {api_key}",
                               "Content-Type": "application/json"}
                    resp = requests.get(api_url.rstrip("/") + "/models",
                                        headers=headers, timeout=10)
                    if resp.status_code == 200:
                        models = resp.json()
                        log_fn("INFO", "═══ 可用模型列表 ═══")
                        for m in models.get("data", models if isinstance(models, list) else []):
                            mid = m.get("id", str(m))
                            log_fn("INFO", f"  {mid}")
                    else:
                        log_fn("WARN", f"API 返回状态码: {resp.status_code}")
                except ImportError:
                    log_fn("WARN", "未安装 requests 库，无法获取模型列表")
                except Exception as e:
                    log_fn("ERROR", f"获取模型列表失败: {e}")
            except Exception as e:
                log_fn("ERROR", f"加载 API 配置失败: {e}")
        else:
            log_fn("WARN", "无法访问配置管理器")

    def _cmd_api_config(self, log_fn, mw):
        if mw and hasattr(mw, "_app_cfg"):
            try:
                cfg = mw._app_cfg.load_api_config()
                log_fn("INFO", "═══ API 配置 ═══")
                log_fn("INFO", f"  URL:   {cfg.get('api_url', '未设置')}")
                log_fn("INFO", f"  Model: {cfg.get('model', '未设置')}")
                log_fn("INFO", f"  Token: {cfg.get('max_tokens', '未设置')}")
                has_key = bool(cfg.get("api_key"))
                log_fn("INFO", f"  Key:   {'✅ 已配置' if has_key else '❌ 未配置'}")
            except Exception as e:
                log_fn("ERROR", f"读取 API 配置失败: {e}")
        else:
            log_fn("WARN", "无法访问配置管理器")

    # ═══════════════════════════════════════════════════
    #  调试监视
    # ═══════════════════════════════════════════════════

    def _get_monitor_mgr(self, mw):
        """获取调试监视管理器实例。"""
        if mw and hasattr(mw, "_debug_log_mgr"):
            from .debug_monitor_manager import DebugMonitorManager
            try:
                return DebugMonitorManager.instance()
            except Exception:
                pass
        return None

    MONITOR_TYPE_MAP = {
        "variable": "variable_watch",
        "function": "function_watch",
        "plugin": "plugin_watch",
        "api": "api_watch",
        "ai": "ai_watch",
    }

    def _cmd_monitor_status(self, log_fn, mw):
        mm = self._get_monitor_mgr(mw)
        if not mm:
            log_fn("WARN", "无法访问调试监视管理器")
            return
        log_fn("INFO", "═══ 监视开关状态 ═══")
        labels = {
            "variable_watch": "变量监视",
            "function_watch": "函数监视",
            "plugin_watch": "插件监视",
            "api_watch": "API 监视",
            "ai_watch": "AI 监视",
        }
        for key, label in labels.items():
            state = "● 开启" if mm.is_monitor_enabled(key) else "○ 关闭"
            log_fn("INFO", f"  {state}  {label}")
        log_fn("INFO", f"调试模式总开关: {'● 开启' if mm.enabled else '○ 关闭'}")

    def _cmd_monitor_enable(self, log_fn, mw, args):
        if not args:
            log_fn("WARN", "用法: monitor enable <类型>  (all/variable/function/plugin/api/ai)")
            return
        mm = self._get_monitor_mgr(mw)
        if not mm:
            log_fn("WARN", "无法访问调试监视管理器")
            return
        if args == "all":
            mm.enable_all()
            log_fn("INFO", "全部监视已启用")
        elif args in self.MONITOR_TYPE_MAP:
            key = self.MONITOR_TYPE_MAP[args]
            mm.set_monitor(key, True)
            log_fn("INFO", f"监视已启用: {args}")
        else:
            log_fn("WARN", f"未知监视类型: {args}  (可选: all/variable/function/plugin/api/ai)")

    def _cmd_monitor_disable(self, log_fn, mw, args):
        if not args:
            log_fn("WARN", "用法: monitor disable <类型>  (all/variable/function/plugin/api/ai)")
            return
        mm = self._get_monitor_mgr(mw)
        if not mm:
            log_fn("WARN", "无法访问调试监视管理器")
            return
        if args == "all":
            mm.disable_all()
            log_fn("INFO", "全部监视已禁用")
        elif args in self.MONITOR_TYPE_MAP:
            key = self.MONITOR_TYPE_MAP[args]
            mm.set_monitor(key, False)
            log_fn("INFO", f"监视已禁用: {args}")
        else:
            log_fn("WARN", f"未知监视类型: {args}  (可选: all/variable/function/plugin/api/ai)")

    def _cmd_monitor_log_view(self, log_fn, mw):
        if mw and hasattr(mw, "_debug_log_mgr"):
            monitor_tags = ["[VAR]", "[FUNC]", "[PLUGIN]", "[API]", "[AI]"]
            entries = mw._debug_log_mgr.entries
            found = 0
            for entry in entries:
                if any(tag in entry for tag in monitor_tags):
                    log_fn("INFO", entry)
                    found += 1
            if found == 0:
                log_fn("INFO", "没有监视日志条目")
            else:
                log_fn("INFO", f"共 {found} 条监视日志")
        else:
            log_fn("WARN", "无法访问日志管理器")

    def _cmd_monitor_log_export(self, log_fn, mw):
        if mw and hasattr(mw, "_debug_log_mgr"):
            path = mw._debug_log_mgr.export_log()
            if path:
                log_fn("INFO", f"监视日志已导出至: {path}")
            else:
                log_fn("ERROR", "监视日志导出失败")
        else:
            log_fn("WARN", "无法访问日志管理器")

    # ═══════════════════════════════════════════════════
    #  面板导航
    # ═══════════════════════════════════════════════════

    def _cmd_panel_open(self, log_fn, mw, args):
        panels = {
            "speech": "_speech_writer_panel",
            "expand": "_ai_expand_panel",
            "notes": "_notes_panel",
            "training": "_training_panel",
            "material": "_material_pool_panel",
        }
        if not args:
            log_fn("WARN", "用法: panel open <面板名>  (speech/expand/notes/training/material)")
            return
        if args not in panels:
            log_fn("WARN", f"未知面板: {args}")
            return
        attr = panels[args]
        if mw and hasattr(mw, attr):
            panel = getattr(mw, attr)
            if panel and hasattr(panel, "setVisible"):
                panel.setVisible(True)
                panel.raise_()
                log_fn("INFO", f"面板已打开: {args}")
            else:
                log_fn("WARN", f"面板不可用: {args}")
        else:
            log_fn("WARN", f"面板未初始化: {args}")

    def _cmd_panel_close(self, log_fn, mw):
        if mw and hasattr(mw, "_toggle_panel"):
            try:
                mw._toggle_panel(None)
                log_fn("INFO", "当前面板已关闭")
            except Exception as e:
                log_fn("ERROR", f"关闭面板失败: {e}")
        else:
            log_fn("WARN", "无法关闭面板")

    # ═══════════════════════════════════════════════════
    #  项目管理
    # ═══════════════════════════════════════════════════

    def _cmd_project_info(self, log_fn, mw):
        if not mw:
            log_fn("WARN", "无法访问主窗口")
            return
        log_fn("INFO", "═══ 当前项目信息 ═══")
        path = getattr(mw, "current_debate_path", None) or "无"
        log_fn("INFO", f"  路径: {path}")
        side = getattr(mw, "current_side", None) or "未知"
        log_fn("INFO", f"  持方: {side}")
        topic = getattr(mw, "current_topic", None) or "未知"
        log_fn("INFO", f"  辩题: {topic}")

    def _cmd_project_list(self, log_fn, mw):
        if mw and hasattr(mw, "_app_cfg"):
            try:
                config = mw._app_cfg.load_full_config()
                projects = config.get("recent_projects", [])
                if not projects:
                    log_fn("INFO", "没有最近打开的项目")
                    return
                log_fn("INFO", f"═══ 最近项目 ({len(projects)} 个) ═══")
                for i, p in enumerate(projects, 1):
                    log_fn("INFO", f"  {i}. {p}")
            except Exception as e:
                log_fn("ERROR", f"获取项目列表失败: {e}")
        else:
            log_fn("WARN", "无法访问配置管理器")

    # ═══════════════════════════════════════════════════
    #  系统诊断
    # ═══════════════════════════════════════════════════

    MANAGER_ATTRS = [
        ("_app_cfg", "应用配置"),
        ("_plugin_manager", "插件管理器"),
        ("_nav_bar_manager", "导航栏"),
        ("_top_nav_manager", "顶部导航"),
        ("_project_explorer", "项目浏览器"),
        ("_speech_writer_manager", "AI 写稿"),
        ("_ai_expand_manager", "AI 扩写"),
        ("_notes_manager", "便签"),
        ("_training_manager", "训练"),
        ("_speech_editor_manager", "一辩稿编辑"),
        ("_ref_doc_manager", "资料稿"),
        ("_ai_analysis_manager", "AI 分析"),
        ("_cross_exam_manager", "模拟质询"),
        ("_structure_tree_manager", "结构树"),
        ("_tournament_manager", "赛程管理"),
        ("_settings_manager", "设置"),
        ("_plugin_panel_manager", "插件面板"),
    ]

    PANEL_ATTRS = [
        ("_speech_writer_panel", "AI 写稿面板"),
        ("_ai_expand_panel", "AI 扩写面板"),
        ("_notes_panel", "便签面板"),
        ("_training_panel", "训练面板"),
        ("_material_pool_panel", "资料池面板"),
    ]

    def _check_attr(self, mw, attr, label) -> bool:
        ok = mw and hasattr(mw, attr) and getattr(mw, attr) is not None
        return ok

    def _cmd_check_all(self, log_fn, mw):
        self._cmd_check_manager(log_fn, mw)
        self._cmd_check_plugin(log_fn, mw)
        self._cmd_check_panel(log_fn, mw)

    def _cmd_check_manager(self, log_fn, mw):
        log_fn("INFO", "═══ 管理器状态检查 ═══")
        total = ok_count = 0
        for attr, label in self.MANAGER_ATTRS:
            total += 1
            ok = self._check_attr(mw, attr, label)
            if ok:
                ok_count += 1
            symbol = "✅" if ok else "❌"
            log_fn("INFO", f"  {symbol} {label}")
        log_fn("INFO", f"结果: {ok_count}/{total} 个管理器加载成功")

    def _cmd_check_plugin(self, log_fn, mw):
        log_fn("INFO", "═══ 插件状态检查 ═══")
        if mw and hasattr(mw, "_plugin_manager"):
            try:
                all_plugins = mw._plugin_manager.get_all_plugins()
                total = len(all_plugins)
                enabled = sum(1 for p in all_plugins if p.enabled)
                for p in all_plugins:
                    symbol = "✅" if p.enabled else "⏸"
                    log_fn("INFO", f"  {symbol} {p.plugin_id} v{p.version}")
                log_fn("INFO", f"结果: {enabled}/{total} 个插件已启用")
            except Exception as e:
                log_fn("ERROR", f"获取插件列表失败: {e}")
        else:
            log_fn("WARN", "插件管理器不可用")

    def _cmd_check_panel(self, log_fn, mw):
        log_fn("INFO", "═══ 面板状态检查 ═══")
        total = ok_count = 0
        for attr, label in self.PANEL_ATTRS:
            total += 1
            ok = self._check_attr(mw, attr, label)
            if ok:
                ok_count += 1
            symbol = "✅" if ok else "❌"
            log_fn("INFO", f"  {symbol} {label}")
        log_fn("INFO", f"结果: {ok_count}/{total} 个面板已加载")

    # ═══════════════════════════════════════════════════
    #  别名管理
    # ═══════════════════════════════════════════════════

    def _cmd_alias_set(self, log_fn, args):
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            log_fn("WARN", "用法: alias set <别名> <命令>")
            return
        name, cmd = parts[0], parts[1]
        if self.set_alias(name, cmd):
            log_fn("INFO", f"别名已设置: {name} → {cmd}")
        else:
            log_fn("WARN", "别名设置失败")

    def _cmd_alias_remove(self, log_fn, args):
        if not args:
            log_fn("WARN", "用法: alias remove <别名>")
            return
        if self.remove_alias(args):
            log_fn("INFO", f"别名已删除: {args}")
        else:
            log_fn("WARN", f"别名不存在: {args}")

    def _cmd_alias_list(self, log_fn):
        aliases = self.get_aliases()
        if not aliases:
            log_fn("INFO", "没有已设置的别名")
            return
        log_fn("INFO", "═══ 已设置别名 ═══")
        for name, cmd in sorted(aliases.items()):
            log_fn("INFO", f"  {name}  →  {cmd}")
        log_fn("INFO", f"共 {len(aliases)} 个别名")
