"""自定义提示弹窗 — 通用控件，替代 Qt 默认 QMessageBox。

提供与 QMessageBox 兼容的静态便捷方法及灵活的 CustomDialog 类。
图标来源：icon/message_box/ 目录下 4 个 SVG 文件，通过 QSvgRenderer 渲染。

使用示例:
    from components.popup_dialog import CustomDialog

    # 信息提示
    CustomDialog.information(self, "提示", "操作已成功完成。")

    # 警告提示
    CustomDialog.warning(self, "警告", "此操作不可撤销。")

    # 错误提示
    CustomDialog.error(self, "错误", "文件读取失败。")

    # 询问确认（返回按钮标识）
    result = CustomDialog.question(self, "确认", "确定要删除吗？",
        buttons=[("取消", "cancel"), ("确定", "ok")])
    if result == "ok":
        ...

    # 确认操作（返回布尔值）
    if CustomDialog.confirm(self, "确认删除", "确定要删除此项目吗？"):
        ...

    # 含复选框
    CustomDialog.information(self, "提示", "已完成", checkbox="不再提示")

    # 高级用法
    dlg = CustomDialog(parent, type="info", title="标题",
        message="内容", buttons=[("确定", "ok")])
    dlg.exec_()
    result = dlg.clicked_button
"""
from .popup_dialog import CustomDialog
