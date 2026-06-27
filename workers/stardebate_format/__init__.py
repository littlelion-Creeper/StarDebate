"""stardebate_format — .stardebate 专属加密辩论文件格式

提供:
  - StardebateCompiler: 双层加密编译/解包核心
  - StardebateExportDialog: 导出 UI 对话框
  - StardebateImportDialog: 导入 UI 对话框
  - StardebateEditorManager: .stardebate 文件编辑器管理器（内存操作）
  - StardebateModulePanel: 模块浏览卡片面板
  - collect_debate_data / restore_debate_data: 数据收集/恢复工具
  - dpapi_crypto: Windows DPAPI 密码安全存储

用法:
    from workers.stardebate_format import (
        StardebateCompiler, StardebateExportDialog, StardebateImportDialog,
        StardebateEditorManager, StardebateModulePanel,
        collect_debate_data, restore_debate_data,
    )
"""

from .stardebate_compiler import (
    StardebateCompiler,
    collect_debate_data,
    restore_debate_data,
    STDB_MAGIC,
    STDB_VERSION,
)
from .stardebate_export_dialog import StardebateExportDialog
from .stardebate_import_dialog import StardebateImportDialog
from .stardebate_editor_manager import StardebateEditorManager
from .stardebate_module_panel import StardebateModulePanel

__all__ = [
    'StardebateCompiler',
    'StardebateExportDialog',
    'StardebateImportDialog',
    'StardebateEditorManager',
    'StardebateModulePanel',
    'collect_debate_data',
    'restore_debate_data',
    'STDB_MAGIC',
    'STDB_VERSION',
]
