"""
StarDebate 资料池模块
====================
多文件规则结构：
- material_pool_manager.py : MaterialPoolManager 类（UI 构建 + 全部业务逻辑）
- local_search.py          : BM25 本地搜索引擎（倒排索引 + 评分）
- ai_search.py             : AI 语义搜索 + 精排
- file_parser.py           : 多格式文件解析器（PDF/DOCX/XLSX/CSV/MD/TXT）
- index_manager.py         : 索引持久化 + 增量更新 + 缓存管理
- md_viewer.py             : 通用 MD 文件查看器组件

风格文件：
- style/themes/catppuccin_mocha/material_pool.qss : 资料池面板专属 QSS

对外 API（主窗口调用）：
| 属性/方法 | 说明 |
|----------|------|
| build_panel() | 构建面板 UI，返回 QFrame |
| build_nav_button() | 创建导航按钮 + 标签 |
| toggle_visibility() | 切换面板显示/隐藏 |
| close_if_open() | 关闭面板（互斥调用） |
| visible | @property 面板可见状态 |
| panel | @property QFrame 面板引用 |
"""

from .material_pool_manager import MaterialPoolManager

__all__ = ["MaterialPoolManager"]
