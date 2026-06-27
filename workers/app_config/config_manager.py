"""AppConfigManager：应用配置持久化（config.json + api_config.json）和样式加载"""
import os
import json
import logging

from PyQt5.QtGui import QFont

# ── 配置路径分离：持久化配置 vs 打包资源 ──────────────────────────
from workers.app_config.config_paths import get_packaged_base_dir


class AppConfigManager:
    """管理应用级配置文件和主题样式加载

    API 配置文件 (api_config.json) 已启用透明加密：
      - 保存时自动使用 Fernet 对称加密写入磁盘
      - 读取时自动检测密文/明文并解密
      - 密钥文件存储在 config/.api_key_store（Windows 下自动隐藏）
      - 所有消费者（Worker / 插件 / 管理器）无需任何代码改动

    路径分离说明：
      - config.json / api_config.json → 持久化配置目录（EXE版为 exe同级/config/）
      - style/themes/ → 打包资源目录（始终从 _internal/ 读取）
    """

    DEFAULT_THEME = "notion_dark"

    def __init__(self, mw, config_file: str, api_config_file: str):
        """
        Args:
            mw: StarDebateWindow 实例引用，需提供 _update_status(msg), version_label, setStyleSheet 等方法
            config_file: config.json 完整路径（持久化目录）
            api_config_file: api_config.json 完整路径（持久化目录）
        """
        self._mw = mw
        self.CONFIG_FILE = config_file
        self.API_CONFIG_FILE = api_config_file
        # ── 主题样式路径始终从打包资源目录读取 ───────────────────
        self._project_root = get_packaged_base_dir()

        # ── API 配置加解密引擎（透明，无需用户操作）──
        from workers.api_config_encrypt import APIEncryptEngine
        config_dir = os.path.dirname(os.path.abspath(api_config_file))
        self._api_encrypt = APIEncryptEngine(config_dir)

    # ========== 应用配置 (config.json) ==========

    def load_full_config(self) -> dict:
        """加载完整配置文件，缺失字段使用默认值"""
        defaults = {"version": "1.0.0", "last_project": "", "theme": self.DEFAULT_THEME, "simplify_tree_names": True}
        if not os.path.isfile(self.CONFIG_FILE):
            return defaults
        try:
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
            for key, val in defaults.items():
                if key not in config:
                    config[key] = val
            return config
        except (json.JSONDecodeError, OSError):
            return defaults

    def save_config(self, project_path: str = None, **kwargs):
        """保存配置到 JSON 文件"""
        config = self.load_full_config()
        if project_path is not None:
            config["last_project"] = project_path
        config.update(kwargs)
        try:
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def load_config(self):
        """从 JSON 配置文件读取最后打开的项目路径"""
        return self.load_full_config().get("last_project") or None

    def auto_load_last_project(self):
        """启动时自动加载上次打开的项目"""
        last_path = self.load_config()
        if last_path and os.path.isdir(last_path):
            self._mw._build_tree_from_path(last_path)
            self._mw._update_status(f"已恢复项目: {os.path.basename(last_path)}")
        else:
            self._mw._project_explorer.populate_tree()
            self._mw._update_status("就绪")

    # ========== API 配置 (api_config.json, 透明加密) ==========

    def load_api_config(self) -> dict:
        """读取 api_config.json（自动检测并解密密文）。

        透明加解密：调用方无需关心文件是明文还是密文，
        此方法始终返回可用的配置字典。
        """
        config = self._api_encrypt.decrypted_load()
        if not config.get("api_url"):
            config["api_url"] = ""
        if not config.get("api_key"):
            config["api_key"] = ""
        if not config.get("model"):
            config["model"] = "deepseek-v4-flash"
        return config

    def save_api_config(self, config: dict):
        """加密保存 API 配置到 api_config.json。

        自动加密后写入磁盘，文件内容为不可读的 Fernet 密文。
        若密钥文件 (.api_key_store) 不存在则自动生成。
        """
        from components.popup_dialog import CustomDialog
        try:
            success = self._api_encrypt.encrypted_save(config)
            if success:
                self._mw._update_status("API 配置已保存（加密存储）")
            else:
                CustomDialog.warning(
                    self._mw, "保存失败",
                    "无法加密保存 API 配置，请检查磁盘空间和权限。"
                )
        except Exception as e:
            CustomDialog.warning(self._mw, "保存失败", f"无法保存 API 配置:\n{str(e)}")

    # ========== 主题管理 ==========

    def get_theme_name(self) -> str:
        """获取当前保存的主题名称，若未设置则返回默认值"""
        config = self.load_full_config()
        theme = config.get("theme", self.DEFAULT_THEME)
        # 验证主题目录是否存在，不存在则回退
        theme_dir = os.path.join(self._project_root, "style", "themes", theme)
        if not os.path.isdir(theme_dir):
            theme = self.DEFAULT_THEME
        return theme

    def get_themes_dir(self) -> str:
        """返回主题根目录路径"""
        return os.path.join(self._project_root, "style", "themes")

    def apply_style(self, theme_name: str = None):
        """加载 QSS 样式，支持模板模式。

        加载策略：
          1. 优先读取主题目录下缓存的 .qss 文件（向后兼容）
          2. 不存在缓存时，从 qss_templates/ 读取 @key@ 模板，
             用当前主题 theme.json 的 colors 实时替换为 hex 值

        Args:
            theme_name: 主题目录名，为 None 时从 config.json 读取
        """
        if theme_name is None:
            theme_name = self.get_theme_name()

        theme_dir = os.path.join(self.get_themes_dir(), theme_name)

        # 若主题不存在，回退到默认
        if not os.path.isdir(theme_dir):
            theme_name = self.DEFAULT_THEME
            theme_dir = os.path.join(self.get_themes_dir(), theme_name)

        # 1) 读取当前主题的颜色映射
        colors = self._load_theme_colors(theme_dir)

        # 2) 获取模板文件列表（从 qss_templates/ 扫描）
        template_dir = os.path.join(self._project_root, "style", "qss_templates")
        if not os.path.isdir(template_dir):
            # 无模板目录时回退到旧模式（直接读主题目录下的 QSS）
            self._apply_style_legacy(theme_dir)
            return

        template_files = sorted(
            f for f in os.listdir(template_dir) if f.endswith(".qss")
        )

        # 3) 加载 QSS 内容（缓存优先，模板替补）
        combined_qss = ""
        for fname in template_files:
            # 主题目录下的缓存文件优先
            cached = os.path.join(theme_dir, fname)
            if os.path.isfile(cached):
                with open(cached, "r", encoding="utf-8") as f:
                    combined_qss += f.read() + "\n"
            else:
                # 从模板实时替换 @key@ -> hex
                template_path = os.path.join(template_dir, fname)
                if os.path.isfile(template_path):
                    with open(template_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    content = self._replace_qss_colors(content, colors)
                    combined_qss += content + "\n"

        # 4) 应用样式
        if combined_qss:
            self._mw.setStyleSheet(combined_qss)

        # 5) 同步 SiGlobal 颜色（PyQt-SiliconUI 主题桥接）
        self._sync_siglobal_colors(colors)

        self._mw._title_bar_applied = False

    def _apply_style_legacy(self, theme_dir: str):
        """旧模式：直接从主题目录读取 QSS 文件（无模板目录时的回退）"""
        theme_config = os.path.join(theme_dir, "theme.json")
        qss_files = ["main.qss", "structure.qss"]
        if os.path.isfile(theme_config):
            try:
                with open(theme_config, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                qss_files = cfg.get("qss_files", qss_files)
            except (json.JSONDecodeError, OSError):
                pass
        combined_qss = ""
        for fname in qss_files:
            fpath = os.path.join(theme_dir, fname)
            if os.path.isfile(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    combined_qss += f.read() + "\n"
        if combined_qss:
            self._mw.setStyleSheet(combined_qss)

        # 同步 SiGlobal 颜色（旧模式：从 theme.json 重新加载颜色）
        theme_config = os.path.join(theme_dir, "theme.json")
        if os.path.isfile(theme_config):
            try:
                with open(theme_config, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                legacy_colors = cfg.get("colors", {})
                legacy_colors_wrapped = {f"@{k}@": v for k, v in legacy_colors.items()}
                self._sync_siglobal_colors(legacy_colors_wrapped)
            except Exception:
                pass

    @staticmethod
    def _load_theme_colors(theme_dir: str) -> dict[str, str]:
        """从 theme.json 加载颜色映射，键名已包含 @ 包裹

        Returns:
            {"@text@": "#E0E0E0", "@base@": "#181A1E", ...}
        """
        path = os.path.join(theme_dir, "theme.json")
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            colors = cfg.get("colors", {})
            return {f"@{k}@": v for k, v in colors.items()}
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _sync_siglobal_colors(colors: dict[str, str]):
        """同步 StarDebate 主题色到 PyQt-SiliconUI 的 SiGlobal 颜色系统

        将 theme.json 的 @key@ 色值映射到 SiColor 的枚举 token，
        使 Si* 组件在调用 reloadStyleSheet() 时能获取正确的颜色。
        """
        try:
            from siui.core import SiColor, SiGlobal
        except ImportError:
            # siui 未安装时静默跳过
            return

        # 从 @key@ 格式还原为裸 key，方便按名称查找
        raw = {}
        for k, v in colors.items():
            raw[k.strip("@")] = v

        def c(key: str, fallback: str = "#000000") -> str:
            return raw.get(key, fallback)

        # ── 映射 SiColor token → theme.json 颜色键 ──
        mapping = {
            SiColor.TEXT_A:            c("text"),
            SiColor.TEXT_B:            c("text"),
            SiColor.TEXT_C:            c("subtext"),
            SiColor.TEXT_D:            c("muted"),
            SiColor.TEXT_E:            c("muted", "#666666"),
            SiColor.TEXT_THEME:        c("accent_blue"),
            SiColor.INTERFACE_BG_A:    c("mantle"),
            SiColor.INTERFACE_BG_B:    c("base"),
            SiColor.INTERFACE_BG_C:    c("surface"),
            SiColor.INTERFACE_BG_D:    c("overlay"),
            SiColor.INTERFACE_BG_E:    c("hover"),
            SiColor.BUTTON_PANEL:      c("overlay"),
            SiColor.BUTTON_SHADOW:     c("mantle"),
            SiColor.BUTTON_THEMED_BG_A:  c("accent_blue"),
            SiColor.BUTTON_THEMED_BG_B:  c("accent_blue_hover", c("accent_blue")),
            SiColor.BUTTON_THEMED_SHADOW_A: c("accent_blue_deep", c("accent_blue")),
            SiColor.BUTTON_THEMED_SHADOW_B: c("accent_blue_pressed", c("accent_blue")),
            SiColor.BUTTON_FLASH:      c("accent_blue"),
            SiColor.BUTTON_HOVER:      c("hover"),
            SiColor.SVG_NORMAL:        c("text"),
            SiColor.SVG_THEME:         c("accent_blue"),
            SiColor.THEME:             c("accent_blue"),
            SiColor.THEME_TRANSITION_A: c("accent_blue"),
            SiColor.THEME_TRANSITION_B: c("accent_blue_hover", c("accent_blue")),
            SiColor.SIDE_MSG_THEME_NORMAL: c("surface", "#332E38"),
            SiColor.SIDE_MSG_THEME_SUCCESS: c("accent_green"),
            SiColor.SIDE_MSG_THEME_WARNING: c("accent_yellow", "#986351"),
            SiColor.SIDE_MSG_THEME_ERROR: c("accent_red"),
            SiColor.LAYER_DIM:         "#60000000",
            SiColor.BUTTON_ON:         c("accent_blue"),
            SiColor.BUTTON_OFF:        c("overlay"),

            # ── 以下为新增映射（补全 DarkColorGroup/BrightColorGroup 中所有令牌）──

            # 工具提示 / 菜单背景
            SiColor.TOOLTIP_BG:           c("overlay", "#332E38"),
            SiColor.MENU_BG:              c("surface", "#332E38"),

            # 按钮空闲状态（完全透明）
            SiColor.BUTTON_IDLE:          "#00FFFFFF",

            # 单选按钮
            SiColor.RADIO_BUTTON_UNCHECKED: c("mantle", "#211F25"),
            SiColor.RADIO_BUTTON_CHECKED:   c("accent_blue", "#9c65ae"),

            # 复选框
            SiColor.CHECKBOX_SVG:          c("base", "#1C191F"),
            SiColor.CHECKBOX_UNCHECKED:    c("muted", "#979797"),
            SiColor.CHECKBOX_CHECKED:      c("accent_blue", "#9c65ae"),

            # 纯文字按钮
            SiColor.BUTTON_TEXT_BUTTON_IDLE:  c("accent_blue", "#c58bc2"),
            SiColor.BUTTON_TEXT_BUTTON_FLASH: c("accent_blue", "#c58bc2"),
            SiColor.BUTTON_TEXT_BUTTON_HOVER: c("accent_blue_hover", "#fabef8"),

            # 长按按钮
            SiColor.BUTTON_LONG_PRESS_PANEL:    c("accent_red", "#932a48"),
            SiColor.BUTTON_LONG_PRESS_SHADOW:   c("mantle", "#642d41"),
            SiColor.BUTTON_LONG_PRESS_PROGRESS: c("accent_red", "#DA3462"),

            # 开关
            SiColor.SWITCH_DEACTIVATE:     c("toggle_off", "#D2D2D2"),
            SiColor.SWITCH_ACTIVATE:       c("accent_blue_deep", "#100912"),

            # 滚动条
            SiColor.SCROLL_BAR:            "#50FFFFFF",

            # 进度条
            SiColor.PROGRESS_BAR_TRACK:       c("mantle", "#252229"),
            SiColor.PROGRESS_BAR_PROCESSING:  c("accent_blue", "#66CBFF"),
            SiColor.PROGRESS_BAR_COMPLETING:  c("accent_yellow", "#FED966"),
            SiColor.PROGRESS_BAR_PAUSED:      c("muted", "#7F7F7F"),
            SiColor.PROGRESS_BAR_FLASHES:     c("white", "#FFFFFF"),

            # 标题指示器 / 高亮
            SiColor.TITLE_INDICATOR:      c("accent_blue", "#c58bc2"),
            SiColor.TITLE_HIGHLIGHT:      c("selected_bg", "#52324E"),

            # 侧栏消息闪烁 / 信息色
            SiColor.SIDE_MSG_FLASH:       "#90FFFFFF",
            SiColor.SIDE_MSG_THEME_INFO:  c("accent_purple", "#855198"),
        }

        # 写入 SiGlobal 颜色字典
        colors_ref = SiGlobal.siui.colors
        try:
            for token, hex_val in mapping.items():
                if hex_val:
                    colors_ref.assign(token, hex_val)
            # 同步 iconpack 默认色
            SiGlobal.siui.iconpack.setDefaultColor(c("text"))
        except Exception as exc:
            logger = logging.getLogger(__name__)
            logger.warning("SiGlobal 颜色同步失败: %s", exc)

    @staticmethod
    def _replace_qss_colors(content: str,
                            color_map: dict[str, str]) -> str:
        """将模板中的 @key@ 占位符替换为 theme.json 中的 hex 值

        不存在的 @unknown@ 占位符会记录 warning 并保持原样。
        """
        import logging
        for placeholder, hex_val in color_map.items():
            content = content.replace(placeholder, hex_val)

        # 检测剩余的未替换占位符
        import re
        remaining = re.findall(r'@\w+@', content)
        if remaining:
            logger = logging.getLogger(__name__)
            logger.warning(
                "QSS 模板中存在未定义的 @key@ 占位符: %s",
                ", ".join(sorted(set(remaining)))
            )
        return content

    def switch_theme(self, theme_name: str):
        """切换主题：保存到 config.json 并立即应用样式"""
        if not theme_name:
            return
        theme_dir = os.path.join(self.get_themes_dir(), theme_name)
        if not os.path.isdir(theme_dir):
            self._mw._update_status(f"主题 '{theme_name}' 不存在")
            return
        # 保存到配置
        self.save_config(theme=theme_name)
        # 刷新全局色板缓存（确保 tc() 返回新主题颜色）
        from components.theme_colors import refresh as refresh_tc
        refresh_tc()
        # 通知 SVG 渲染器切换主题色
        from components.svg_renderer import SvgRenderer
        SvgRenderer.set_theme(theme_name)
        # 立即应用样式
        self.apply_style(theme_name)
        # 刷新导航栏 SVG 图标颜色（跟随新主题）
        if hasattr(self._mw, '_nav_mgr'):
            try:
                self._mw._nav_mgr.refresh_nav_icons()
            except Exception:
                pass
        # 刷新标题栏三个窗口按钮颜色（跟随新主题）
        if hasattr(self._mw, '_title_bar'):
            try:
                self._mw._title_bar.refresh_theme_colors()
            except Exception:
                pass
        # 刷新一辩稿悬浮卡片颜色（跟随新主题）
        if hasattr(self._mw, '_speech_editor_mgr'):
            try:
                self._mw._speech_editor_mgr.refresh_hover_card_theme()
            except Exception:
                pass
        self._mw._update_status(f"主题已切换: {theme_name}")

    # ========== 版本显示 ==========

    def get_app_version(self) -> str:
        """获取当前应用版本号"""
        return self.load_full_config().get("version", "1.0.0")

    def refresh_version_display(self):
        """从配置文件重新读取版本号并更新显示"""
        app_version = self.get_app_version()
        self._mw.version_label.setText(f"v{app_version}")
