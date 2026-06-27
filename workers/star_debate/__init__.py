"""StarDebate 主窗口拆分模块

本模块将 StarDebateWindow 按职责拆分为三个文件：
  - ui_assembly.py  → UIAssemblyMixin：UI 面板组装
  - glue.py         → GlueCodeMixin：跨模块胶水代码

入口文件 StarDebate.py 通过多重继承组合这两个 Mixin。
"""

from workers.star_debate.ui_assembly import UIAssemblyMixin
from workers.star_debate.glue import GlueCodeMixin

__all__ = ["UIAssemblyMixin", "GlueCodeMixin"]
