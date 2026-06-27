"""
SVG 通用渲染器核心模块

提供:
  - render()    通用渲染
  - icon()      单色图标快捷方法
  - bicolor()   双色图标快捷方法
  - named()     按预设名称获取图标
  - qicon()     生成多状态 QIcon
  - set_theme() 主题切换时调用
  - clear_cache() 手动清缓存
"""
import os
from workers.app_config.config_paths import get_config_path
from PyQt5.QtCore import QSize, Qt, QRectF
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QColor
from PyQt5.QtSvg import QSvgRenderer

from .cache import SvgCache
from .color_map import ColorMap
from .parser import SvgParser
from .icons import init_icon_dir, lookup, register, unregister, list_names


class SvgRenderer:
    """SVG 通用渲染器 — 模块级单例"""

    # ── 模块级单例 ──
    _cache = SvgCache()
    _color_map = ColorMap()
    _initialized = False
    _mode = "mono"  # 全局默认渲染模式

    # ── 初始化 ───────────────────────────────────────────────

    @classmethod
    def init(cls, project_root: str):
        """初始化渲染器（应用启动时调用一次）"""
        if cls._initialized:
            return
        init_icon_dir(project_root)
        cls._color_map.init(project_root)
        cls._load_global_config(project_root)
        cls._initialized = True

    @classmethod
    def _load_global_config(cls, project_root: str):
        """加载全局配置"""
        config_path = get_config_path("config/svg_renderer.json")
        cls._cache.load_config(config_path)
        try:
            import json
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cls._mode = data.get("mode", "mono")
        except Exception:
            cls._mode = "mono"

    # ── 公共 API ─────────────────────────────────────────────

    @classmethod
    def render(cls, svg_path: str, size: int | QSize,
               mode: str = None, color: QColor | str = None,
               primary: QColor | str = None, accent: QColor | str = None,
               device_pixel_ratio: float = None,
               use_cache: bool = True) -> QPixmap:
        """通用 SVG 渲染。

        Args:
            svg_path: SVG 文件路径
            size: 渲染尺寸 (int=正方形, QSize=自定义)
            mode: 渲染模式 "mono"/"dual"/"native"，None=使用全局默认
            color: 单色模式颜色 (QColor 或色键字符串如 "text")
            primary: 双色模式主色
            accent: 双色模式辅色
            device_pixel_ratio: DPI 缩放，None=自动检测
            use_cache: 是否使用缓存

        Returns:
            QPixmap
        """
        if not svg_path or not os.path.isfile(svg_path):
            return cls._empty_pixmap(size)

        # 确定模式
        actual_mode = mode or cls._mode
        if actual_mode not in ("mono", "dual", "native"):
            actual_mode = "mono"

        # 解析颜色
        if actual_mode == "mono":
            c = cls._resolve_single_color(color)
            primary_c = c
            accent_c = c
        elif actual_mode == "dual":
            primary_c = cls._resolve_single_color(primary or cls._color_map.dual_primary_key)
            accent_c = cls._resolve_single_color(accent or cls._color_map.dual_accent_key)
        else:
            primary_c = None
            accent_c = None

        # 缓存键
        px = primary_c.name() if primary_c else "none"
        ax = accent_c.name() if accent_c else "none"
        if isinstance(size, int):
            sz_key = size
        else:
            sz_key = (size.width(), size.height())
        cache_key = (svg_path, sz_key, px, ax, actual_mode)

        # 查缓存
        if use_cache:
            cached = cls._cache.get(cache_key)
            if cached is not None:
                return cached

        # 渲染
        result = cls._do_render(svg_path, size, actual_mode,
                                primary_c, accent_c, device_pixel_ratio)

        # 写缓存
        if use_cache and result:
            cls._cache.put(cache_key, result)

        return result

    @classmethod
    def icon(cls, svg_path: str, size: int = 24,
             color: QColor | str = None,
             device_pixel_ratio: float = None) -> QPixmap:
        """单色图标快捷方法。使用当前主题的 mono.color。"""
        return cls.render(svg_path, size, mode="mono", color=color,
                          device_pixel_ratio=device_pixel_ratio)

    @classmethod
    def bicolor(cls, svg_path: str, size: int = 24,
                primary: QColor | str = None,
                accent: QColor | str = None,
                device_pixel_ratio: float = None) -> QPixmap:
        """双色图标快捷方法。使用当前主题的 dual.primary / dual.accent。"""
        return cls.render(svg_path, size, mode="dual",
                          primary=primary, accent=accent,
                          device_pixel_ratio=device_pixel_ratio)

    @classmethod
    def named(cls, name: str, size: int = 24,
              mode: str = None, color: QColor | str = None,
              primary: QColor | str = None, accent: QColor | str = None) -> QPixmap:
        """按预设名称获取图标。"""
        path = lookup(name)
        if not path:
            return cls._empty_pixmap(size)
        return cls.render(path, size, mode=mode, color=color,
                          primary=primary, accent=accent)

    @classmethod
    def qicon(cls, svg_path: str, size: int = 24,
              mode: str = None, color: QColor | str = None,
              primary: QColor | str = None, accent: QColor | str = None,
              disabled_pct: float = 0.4) -> QIcon:
        """生成含有 normal/disabled 状态的 QIcon。

        Args:
            disabled_pct: disabled 状态的颜色透明度（0.0-1.0）
        """
        normal = cls.render(svg_path, size, mode=mode, color=color,
                            primary=primary, accent=accent)
        icon = QIcon(normal)

        # 生成 disabled 版本（降低透明度）
        if not normal.isNull():
            disabled = QPixmap(normal.size())
            disabled.fill(Qt.transparent)
            painter = QPainter(disabled)
            try:
                painter.setOpacity(max(0.0, min(1.0, disabled_pct)))
                painter.drawPixmap(0, 0, normal)
            finally:
                painter.end()
            icon.addPixmap(disabled, QIcon.Disabled, QIcon.Off)

        return icon

    # ── 主题管理 ─────────────────────────────────────────────

    @classmethod
    def set_theme(cls, theme_name: str):
        """切换主题 → 重载颜色映射 + 清空缓存"""
        cls._color_map.set_theme(theme_name)
        cls._cache.clear()

    @classmethod
    def clear_cache(cls):
        """手动清空渲染缓存"""
        cls._cache.clear()

    @classmethod
    def set_mode(cls, mode: str, project_root: str = None):
        """设置全局默认渲染模式并持久化"""
        if mode in ("mono", "dual", "native"):
            cls._mode = mode
            if project_root:
                cls._save_mode_config(project_root)

    # ── 属性（classmethod 获取器，Python 不支持 classmethod+property.setter）──

    @classmethod
    def get_mode(cls) -> str:
        return cls._mode

    @classmethod
    def get_theme_name(cls) -> str:
        return cls._color_map.theme_name

    @classmethod
    def get_cache_size(cls) -> int:
        return cls._cache.size

    @classmethod
    def get_cache_enabled(cls) -> bool:
        return cls._cache.enabled

    @classmethod
    def set_cache_enabled(cls, value: bool):
        cls._cache.enabled = value

    @classmethod
    def get_cache_max(cls) -> int:
        return cls._cache.max_size

    @classmethod
    def set_cache_max(cls, value: int):
        cls._cache.max_size = value

    @classmethod
    def get_color_map(cls) -> ColorMap:
        return cls._color_map

    # classmethod 均需括号调用：SvgRenderer.get_mode(), SvgRenderer.get_cache_size() 等

    # ── 图标注册（供插件使用）──────────────────────────────────

    @classmethod
    def register_icon(cls, name: str, svg_path: str):
        """注册自定义图标名称"""
        register(name, svg_path)

    @classmethod
    def unregister_icon(cls, name: str):
        """取消注册自定义图标"""
        unregister(name)

    @classmethod
    def list_icons(cls) -> list[str]:
        """列出所有已注册图标名称"""
        return list_names()

    # ── 内部方法 ─────────────────────────────────────────────

    @classmethod
    def _do_render(cls, svg_path: str, size: int | QSize,
                   mode: str, primary: QColor | None,
                   accent: QColor | None,
                   dpr: float | None) -> QPixmap:
        """执行实际渲染"""
        # 读取 SVG 内容
        try:
            with open(svg_path, "r", encoding="utf-8") as f:
                svg_content = f.read()
        except (OSError, UnicodeDecodeError):
            return cls._empty_pixmap(size)

        # 颜色替换
        if mode == "mono" and primary:
            svg_content = SvgParser.render_mono(svg_content, primary)
        elif mode == "dual" and primary and accent:
            svg_content = SvgParser.render_dual(svg_content, primary, accent)
        # native → 不替换

        # 渲染为 QPixmap
        if isinstance(size, int):
            qsize = QSize(size, size)
        else:
            qsize = size

        ratio = dpr or cls._get_dpr()
        real_w = int(qsize.width() * ratio)
        real_h = int(qsize.height() * ratio)

        pix = QPixmap(real_w, real_h)
        pix.setDevicePixelRatio(ratio)
        pix.fill(Qt.transparent)

        painter = QPainter(pix)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            # 使用 QString 版本渲染（不依赖 QSvgRenderer 的文件路径构造）
            renderer = QSvgRenderer()
            svg_bytes = svg_content.encode("utf-8")
            renderer.load(svg_bytes)
            if renderer.isValid():
                renderer.render(painter, QRectF(0, 0, qsize.width(), qsize.height()))
        finally:
            painter.end()

        return pix

    @classmethod
    def _resolve_single_color(cls, value: QColor | str | None) -> QColor | None:
        """将颜色参数解析为 QColor"""
        if value is None:
            return cls._color_map.mono_color
        if isinstance(value, QColor):
            return value
        if isinstance(value, str):
            # 尝试在主题色中查找
            c = cls._color_map.resolve(value)
            if c:
                return c
            # 尝试直接 hex
            try:
                return QColor(value)
            except Exception:
                return cls._color_map.mono_color
        return cls._color_map.mono_color

    @classmethod
    def _empty_pixmap(cls, size: int | QSize) -> QPixmap:
        """返回透明占位 pixmap"""
        if isinstance(size, int):
            qsize = QSize(size, size)
        else:
            qsize = size
        pix = QPixmap(qsize)
        pix.fill(Qt.transparent)
        return pix

    @staticmethod
    def _get_dpr() -> float:
        """获取当前屏幕设备像素比"""
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                screen = app.primaryScreen()
                if screen:
                    return screen.devicePixelRatio()
        except Exception:
            pass
        return 1.0

    @classmethod
    def _save_mode_config(cls, project_root: str):
        """保存当前渲染模式到配置文件"""
        import json
        config_path = get_config_path("config/svg_renderer.json")
        try:
            existing = {}
            if os.path.isfile(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            existing["mode"] = cls._mode
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=4)
        except OSError:
            pass
