# PyQt-SiliconUI 控件参考手册

> 基于 Gallery for siui 示例项目整理 (v1.14.514)
>
> ⚠️ 旧版控件包含缺陷，正逐步被重构控件取代。推荐优先使用重构控件。

---

## 一、按钮（Buttons）

### 1.1 SiPushButtonRefactor（重构按压按钮）⭐ 推荐
`from siui.components.button import SiPushButtonRefactor`

```python
# 纯文字
btn = SiPushButtonRefactor(parent)
btn.setText("按压按钮")
btn.adjustSize()

# 图标+文字
btn = SiPushButtonRefactor(parent)
btn.setSvgIcon(SiGlobal.siui.iconpack.get("ic_fluent_location_filled"))
btn.setText("获取定位")
btn.setToolTip("带经纬度、朝向信息")
btn.adjustSize()

# 纯图标
btn = SiPushButtonRefactor(parent)
btn.setSvgIcon(SiGlobal.siui.iconpack.get("ic_fluent_location_filled"))
btn.setToolTip("获取定位")
btn.adjustSize()

# 工厂方法
btn = SiPushButtonRefactor.withText("随机赋值")
```

### 1.2 SiProgressPushButton（进度按钮）⭐ 推荐
`from siui.components.button import SiProgressPushButton`

```python
btn = SiProgressPushButton(parent)
btn.setText("下载中")
btn.setSvgIcon(SiGlobal.siui.iconpack.get("ic_fluent_arrow_download_filled"))
btn.clicked.connect(lambda: btn.setProgress(random.random() * 1.3))
btn.adjustSize()
```

### 1.3 SiLongPressButtonRefactor（长按确定按钮）⭐ 推荐
`from siui.components.button import SiLongPressButtonRefactor`

```python
btn = SiLongPressButtonRefactor(parent)
btn.setText("格式化磁盘")
btn.setToolTip("长按以确认")
btn.setSvgIcon(SiGlobal.siui.iconpack.get("ic_fluent_delete_filled"))
btn.longPressed.connect(lambda: print("长按触发"))
btn.adjustSize()
```

### 1.4 SiFlatButton（扁平按钮）⭐ 推荐
`from siui.components.button import SiFlatButton`

```python
btn = SiFlatButton(parent)
btn.setText("放大")
btn.adjustSize()

# 仅图标
btn = SiFlatButton(parent)
btn.resize(32, 32)
btn.setSvgIcon(SiGlobal.siui.iconpack.get("ic_fluent_zoom_in_filled"))
btn.setToolTip("放大")
```

### 1.5 SiToggleButtonRefactor（状态切换按钮）⭐ 推荐
`from siui.components.button import SiToggleButtonRefactor`

```python
btn = SiToggleButtonRefactor(parent)
btn.setText("自动保存")
btn.setSvgIcon(SiGlobal.siui.iconpack.get("ic_fluent_save_filled"))
btn.adjustSize()
```

### 1.6 SiCapsuleButton（胶囊按钮）
`from siui.components.button import SiCapsuleButton`

```python
btn = SiCapsuleButton(parent)
btn.setText("Likes")
btn.setValue(114514)
btn.setToolTip("你好世界")
btn.setThemeColor(SiCapsuleButton.Theme.Yellow)  # Yellow / Red
```

### 1.7 SiFlatButtonWithIndicator（带指示器的按钮）
`from siui.components.button import SiFlatButtonWithIndicator`

```python
btn = SiFlatButtonWithIndicator(parent)
btn.setText("日期设置")
btn.setFixedHeight(40)
btn.setChecked(True)    # 选中
# 配合 QButtonGroup 实现单选
group = QButtonGroup(parent)
group.addButton(btn)
group.setExclusive(True)
```

### 1.8 SiOptionButton
`from siui.components.button import SiOptionButton`

### 1.9 旧版按钮（不推荐新项目）
`from siui.components.widgets import SiPushButton, SiSimpleButton, SiToggleButton, SiLongPressButton`

```python
# SiPushButton
btn = SiPushButton(parent)
btn.resize(128, 32)
btn.attachment().setText("普通按钮")

# 主题过渡
btn = SiPushButton(parent)
btn.setUseTransition(True)
btn.attachment().setText("主题按钮")

# SiSimpleButton - 图标+文字扁平
btn = SiSimpleButton(parent)
btn.resize(96, 32)
btn.attachment().load(SiGlobal.siui.iconpack.get("ic_fluent_arrow_sync_regular"))
btn.attachment().setText("刷新")

# SiToggleButton - 旧版切换
btn = SiToggleButton(parent)
btn.resize(96, 32)
btn.attachment().load(SiGlobal.siui.iconpack.get("ic_fluent_bookmark_regular"))
btn.attachment().setText("收藏")
btn.colorGroup().assign(SiColor.BUTTON_OFF, "#3b373f")
btn.colorGroup().assign(SiColor.BUTTON_ON, "#855198")

# SiLongPressButton - 旧版长按
btn = SiLongPressButton(parent)
btn.resize(128, 32)
btn.attachment().setText("长按按钮")
```

---

## 二、选择控件（Selection）

### 2.1 SiCheckBoxRefactor（重构多选/单选）⭐ 推荐
`from siui.components.button import SiCheckBoxRefactor`

```python
# 多选
ck = SiCheckBoxRefactor(parent)
ck.setText("选项 1")
ck.setDescription("详细说明")

# 单选（autoExclusive=True）
ck = SiCheckBoxRefactor(parent)
ck.setText("选项 A")
ck.setAutoExclusive(True)
ck.setChecked(True)
```

### 2.2 SiRadioButtonR（重构单行单选框）⭐ 推荐
`from siui.components.button import SiRadioButtonR`

```python
rb = SiRadioButtonR(parent)
rb.setText("选项文字")
rb.setChecked(True)
rb.adjustSize()
```

### 2.3 SiRadioButtonWithDescription（带说明）⭐ 推荐
`from siui.components.button import SiRadioButtonWithDescription`

```python
rb = SiRadioButtonWithDescription(parent)
rb.setText("Hello World")
rb.setDescription("This is the description")
rb.setDescriptionWidth(180)
rb.setChecked(True)
rb.adjustSize()
```

### 2.4 SiRadioButtonWithAvatar（带头像）
`from siui.components.button import SiRadioButtonWithAvatar`

```python
rb = SiRadioButtonWithAvatar(parent)
rb.setText("用户名")
rb.setDescription("email@example.com")
rb.setIcon(QIcon("./img/avatar1.png"))
rb.setChecked(True)
rb.adjustSize()
```

### 2.5 SiSwitchRefactor（重构开关）⭐ 推荐
`from siui.components.button import SiSwitchRefactor`

```python
switch = SiSwitchRefactor(parent)
switch.toggled.connect(callback)
```

### 2.6 旧版选择控件
**SiCheckBox**: `from siui.components.button import SiCheckBox`
**SiRadioButton**: `from siui.components.button import SiRadioButton`
**SiSwitch**: `from siui.components.widgets import SiSwitch`

```python
ck = SiCheckBox(parent)
ck.setText("安装基本组件")

rb = SiRadioButton(parent)
rb.setChecked(True)
rb.setText("西红柿炒鸡蛋")

sw = SiSwitch(parent)
```

---

## 三、编辑框（Edit Boxes）

### 3.1 SiCapsuleLineEdit（胶囊输入框）⭐ 推荐
`from siui.components.editbox import SiCapsuleLineEdit`

```python
edit = SiCapsuleLineEdit(parent)
edit.resize(560, 36)
edit.setTitleWidthMode(SiCapsuleLineEdit.TitleWidthMode.Ratio)
edit.setTitle("Repository Name")
edit.setText("PyQt-SiliconUI")
# 右侧添加按钮
btn = SiFlatButton(parent)
btn.setText("确定")
edit.addWidgetToRight(btn)
```

### 3.2 SiLabeledLineEdit（小型文本编辑框）⭐ 推荐
`from siui.components.editbox import SiLabeledLineEdit`

```python
edit = SiLabeledLineEdit(parent)
edit.setTitle("用户名")
edit.setPlaceholderText("您的用户名...")
edit.resize(170, 58)
```

### 3.3 SiSpinBox（整数微调）⭐ 推荐
`from siui.components.editbox import SiSpinBox`

```python
spin = SiSpinBox(parent)
spin.setTitle("运行次数")
spin.resize(170, 58)
```

### 3.4 SiDoubleSpinBox（浮点数微调）⭐ 推荐
`from siui.components.editbox import SiDoubleSpinBox`

```python
spin = SiDoubleSpinBox(parent)
spin.setTitle("参数")
spin.setSingleStep(0.1)
spin.resize(170, 58)
```

### 3.5 旧版输入控件
```python
# SiLineEdit
edit = SiLineEdit(parent)
edit.setFixedSize(252, 32)

# SiLineEditWithDeletionButton
edit = SiLineEditWithDeletionButton(parent)
edit.resize(256, 32)
edit.lineEdit().setText("文字")

# SiLineEditWithItemName
edit = SiLineEditWithItemName(parent)
edit.setName("项目名称")
edit.lineEdit().setText("PyQt-SiliconUI")
edit.resize(512, 32)

# SiIntSpinBox / SiDoubleSpinBox (旧版)
box = SiIntSpinBox(parent)
box.resize(256, 32)
```

---

## 四、滑动条（Sliders）⭐ 推荐

### 4.1 SiSlider（水平/垂直）
`from siui.components.slider_ import SiSlider`

```python
# 水平
slider = SiSlider(parent)
slider.resize(512, 48)

# 垂直
slider = SiSlider(parent)
slider.resize(48, 140)
slider.setOrientation(Qt.Orientation.Vertical)

slider.setValue(5)
slider.setMinimum(-50)
slider.setMaximum(50)
slider.setToolTipConvertionFunc(lambda x: f"{x} ms")
```

### 4.2 SiCoordinatePicker2D（二维坐标）
```python
picker = SiCoordinatePicker2D(parent)
picker.resize(384, 256)
picker.slider_x.setValue(72)
picker.slider_y.setValue(63)
```

### 4.3 SiCoordinatePicker3D（三维坐标）
```python
picker = SiCoordinatePicker3D(parent)
picker.resize(384, 256)
picker.slider_z.setMaximum(6)
picker.slider_z.setValue(6)
```

### 4.4 旧版 SiSliderH
`from siui.components.slider import SiSliderH`

```python
slider = SiSliderH(parent)
slider.resize(500, 32)
slider.setMinimum(-20)
slider.setMaximum(20)
slider.setValue(0, move_to=False)
```

---

## 五、进度条（Progress Bars）

### 5.1 SiProgressBarRefactor（重构条形进度条）⭐ 推荐
`from siui.components.progress_bar_ import SiProgressBarRefactor`

```python
bar = SiProgressBarRefactor(parent)
bar.setMaximum(1000)
bar.setValue(500)

# 状态
bar.setState(bar.State.Loading)     # 加载中
bar.setState(bar.State.Processing)  # 处理中
bar.setState(bar.State.Paused)      # 暂停
bar.setState(bar.State.Error)       # 错误

bar.setFlashing(True)  # 闪烁动画
```

### 5.2 SiLinearPartitionIndicator（区间指示器）
`from siui.components.label import SiLinearPartitionIndicator`

```python
ind = SiLinearPartitionIndicator(parent)
ind.activate()
ind.setFixedSize(200, 4)
ind.setNodeAmount(7)
ind.setEndIndex(1)
ind.setStartIndex(0)
ind.deactivate()
ind.warn()
```

### 5.3 旧版进度条
**SiProgressBar**: `from siui.components.progress_bar import SiProgressBar`

```python
bar = SiProgressBar(parent)
bar.resize(700, 32)
bar.setValue(0.7)  # 0.0~1.0
bar.setState("processing")  # processing / paused / completing
```

**SiCircularProgressBar**: `from siui.components import SiCircularProgressBar`

```python
bar = SiCircularProgressBar(parent)
bar.resize(32, 32)
bar.setValue(0.7)          # 确定进度
bar.setIndeterminate(True) # 不确定（旋转）
```

---

## 六、标签（Labels）

### 6.1 SiLabel（文字标签）⭐ 推荐
`from siui.components.widgets import SiLabel`

```python
label = SiLabel(parent)
label.setSiliconWidgetFlag(Si.AdjustSizeOnTextChanged)
label.setText("测试标签")
label.setAlignment(Qt.AlignCenter)
label.setFixedStyleSheet("border-radius: 4px")  # QSS 不受主题影响
# 主题色固定样式
label.setStyleSheet(f"color: {SiGlobal.siui.colors['TEXT_A']}")
# 动画相关
label.setColorTo(color)  # 背景色(带动画)
label.moveTo(x, y)       # 动画移动
label.resizeTo(w, h)     # 动画改变大小
label.setMoveLimits(l, t, r, b)  # 移动范围
label.setHint("工具提示(支持 HTML)")
```

### 6.2 SiIconLabel（带 SVG 图标）
`from siui.components.widgets import SiIconLabel`

```python
label = SiIconLabel(parent)
label.load(SiGlobal.siui.iconpack.get("ic_fluent_comment_link_regular"))
label.setText(" 带图标文字")
```

### 6.3 SiPixLabel（图片标签）⭐ 推荐
`from siui.components.widgets import SiPixLabel`

```python
label = SiPixLabel(parent)
label.setFixedSize(80, 80)
label.setBorderRadius(40)   # 圆形
label.load("./img/avatar1.png")
label.setHint("工具提示")
```

### 6.4 SiDraggableLabel（可拖动标签）
`from siui.components.widgets import SiDraggableLabel`

```python
label = SiDraggableLabel(parent)
label.setMoveLimits(0, 0, 526, 80)
label.resize(128, 32)
```

---

## 七、组合框（ComboBox）

### 7.1 SiCapsuleComboBox（重构）⭐ 推荐
`from siui.components.combobox_ import SiCapsuleComboBox`

```python
combo = SiCapsuleComboBox(parent)
combo.setTitle("可编辑组合框")
combo.setMinimumHeight(36)
combo.setEditable(True)
combo.addItems(["Python", "C++", "JavaScript"])
```

### 7.2 SiComboBox（旧版）
`from siui.components.combobox import SiComboBox`

```python
combo = SiComboBox(parent)
combo.resize(256, 32)
combo.addOption("文字")
combo.addOption("文字带值", value=0)
combo.menu().setShowIcon(False)
combo.menu().setIndex(3)
combo.valueChanged.connect(self.on_changed)
combo.colorGroup().assign(SiColor.INTERFACE_BG_B, color)
```

---

## 八、菜单（Menus）

### 8.1 SiRoundedMenu（重构圆角菜单）⭐ 推荐
`from siui.components.menu_ import SiRoundedMenu`

```python
menu = SiRoundedMenu(parent)
menu.setTitle("菜单标题")
menu.setIcon(SiGlobal.siui.iconpack.toIcon("ic_fluent_text_regular"))

# QAction 管理
action = QAction("名称")
action.setIcon(SiGlobal.siui.iconpack.toIcon("ic_fluent_rename_regular"))
action.setShortcut("Ctrl+C")
action.setCheckable(True)
menu.addAction(action)
menu.addSeparator()

# 子菜单
sub = SiRoundedMenu(menu)
sub.setTitle("子菜单")
menu.addMenu(sub)

# 自定义控件项
menu.addCustomWidget(action, ComboboxItemWidget)
```

### 8.2 SiMenu（旧版）
`from siui.components.menu import SiMenu`

```python
menu = SiMenu()
menu.setFixedWidth(260)
menu.addOption("选项", icon=icon, child_menu=child_menu)
menu.setShowIcon(True)
menu.setSelectionMenu(False)
menu.unfold(QCursor.pos().x(), QCursor.pos().y())
```

---

## 九、弹出框（Popover）

### 9.1 SiPopover ⭐ 推荐
`from siui.components.popover import SiPopover`

```python
popover = SiPopover()
stack = SiPopoverStackedWidget(popover)

# 用 SiGraphicWrapperWidget 包装内容
wrapper = SiGraphicWrapperWidget()
wrapper.setWidget(date_picker)
wrapper.setMergeAnimations(
    SiGraphicWrapperWidget.TransitionAnimations.floatUp,
)
stack.addPage(wrapper, "页面标题")

popover.wrapper().setWidget(stack)
popover.wrapper().setMergeAnimations(...)
popover.popup(global_pos)
```

**TransitionAnimations**: `scaleUp`, `fadeIn`, `floatUp`, `floatLeftIn`

---

## 十、选项卡（Option Cards）

### 10.1 SiOptionCardLinear（线性）⭐ 推荐
`from siui.components.option_card import SiOptionCardLinear`

```python
card = SiOptionCardLinear(parent)
card.setTitle("标题", "副标题描述")
card.load(icon)  # 左侧图标
card.addWidget(button)  # 右侧添加控件
```

### 10.2 SiOptionCardPlane（平面）⭐ 推荐
`from siui.components.option_card import SiOptionCardPlane`

```python
card = SiOptionCardPlane(parent)
card.setTitle("标题")
# header(水平) / body(垂直) / footer(水平) 三个区域
card.header().addWidget(widget, side="right")
card.body().addWidget(widget, side="top")
card.footer().setFixedHeight(64)
card.footer().addWidget(widget, side="left")
card.footer().setSpacing(8)
card.footer().setAlignment(Qt.AlignCenter)
card.adjustSize()
```

### 10.3 SiTriSectionPanelCard / SiTriSectionRowCard
`from siui.components.container import SiTriSectionPanelCard, SiTriSectionRowCard`

```python
card = SiTriSectionPanelCard(parent)
card.setTitle("标题")
card.body().addWidget(widget)

bar = SiTriSectionRowCard(parent, pixmap)
bar.actionsContainer().addWidget(SiSwitchRefactor(self))
```

---

## 十一、容器（Containers）

### 11.1 SiDenseHContainer（水平密堆积）⭐ 推荐
`from siui.components import SiDenseHContainer`

```python
c = SiDenseHContainer(parent)
c.setFixedHeight(32)
c.addWidget(label, "left")   # 靠左
c.addWidget(label, "right")  # 靠右
c.setSpacing(16)
c.setAlignment(Qt.AlignCenter)
```

### 11.2 SiDenseVContainer（垂直密堆积）⭐ 推荐
`from siui.components import SiDenseVContainer`

```python
c = SiDenseVContainer(parent)
c.setFixedHeight(300)
c.addWidget(label, "top")
c.addWidget(label, "bottom")
c.setSpacing(6)
c.setAdjustWidgetsSize(True)
```

### 11.3 SiDenseContainer（通用）
`from siui.components.container import SiDenseContainer`

```python
c = SiDenseContainer(parent, QBoxLayout.LeftToRight)
c.layout().setSpacing(12)
```

### 11.4 SiDividedHContainer（水平分割）
`from siui.components import SiDividedHContainer`

```python
c = SiDividedHContainer(parent)
c.addSection(width=120, height=32, alignment=Qt.AlignLeft)
c.arrangeWidgets()
```

### 11.5 SiDividedVContainer（垂直分割）
`from siui.components import SiDividedVContainer`

```python
c = SiDividedVContainer(parent)
c.addSection(width=256, height=48, alignment=Qt.AlignTop)
c.arrangeWidgets()
```

### 11.6 SiFlowContainer（流式布局）⭐ 推荐
`from siui.components import SiFlowContainer`

```python
c = SiFlowContainer(parent)
c.resize(1000, 32)
c.setSiliconWidgetFlag(Si.EnableAnimationSignals)
c.addWidget(widget, ani=False)
c.regDraggableWidget(widget)
c.arrangeWidgets(ani=False, all_fade_in=True)
c.shuffle(ani=True)
c.insertToByIndex(from_idx, to_idx)
c.setLineHeight(96)
```

### 11.7 SiMasonryContainer（瀑布流）⭐ 推荐
`from siui.components import SiMasonryContainer`

```python
c = SiMasonryContainer(parent)
c.setAutoAdjustColumnAmount(True)
c.setColumns(4)
c.setColumnWidth(512)
c.setSpacing(horizontal=16, vertical=16)
c.addWidget(widget, ani=False)
c.regDraggableWidget(widget)
```

### 11.8 SiTitledWidgetGroup（带标题控件组）⭐ 推荐
`from siui.components import SiTitledWidgetGroup`

```python
g = SiTitledWidgetGroup(parent)
g.setSpacing(32)
g.setAdjustWidgetsSize(True)
with g as group:
    group.addTitle("分组标题")
    group.addWidget(widget)
    group.addPlaceholder(16)
```

### 11.9 SiScrollArea
`from siui.components import SiScrollArea`

```python
area = SiScrollArea(parent)
area.setAttachment(content_widget)
```

---

## 十二、表格（Table）

### 12.1 SiTableView ⭐ 推荐
`from siui.components.widgets.table import SiTableView`

```python
table = SiTableView(parent)
table.resize(752, 360)
table.addColumn("歌曲名", 190, 40, Qt.AlignLeft | Qt.AlignVCenter)
table.addRow(data=["どうして", "高瀬統也", "どうして", "03:01"])
table.setManager(MyTableManager(table))
```

---

## 十三、导航栏（Navigation Bar）

### 13.1 SiNavigationBarH（水平）
`from siui.components.widgets.navigation_bar import SiNavigationBarH`

```python
bar = SiNavigationBarH(parent)
bar.addItem("基本信息")
bar.setCurrentIndex(0)
bar.setNoIndicator(True)  # 用作选择栏
```

### 13.2 SiNavigationBarV（垂直）
`from siui.components.widgets.navigation_bar import SiNavigationBarV`

```python
bar = SiNavigationBarV(parent)
bar.addItem("唱歌")
bar.setCurrentIndex(0)
bar.setNoIndicator(True)
```

---

## 十四、时间与日期

### 14.1 SiCalenderView（日历）
`from siui.components.widgets.timedate import SiCalenderView`

```python
cal = SiCalenderView(parent)
cal.setDate(datetime.date.today())
cal.adjustSize()
```

### 14.2 SiTimePicker（时间）
`from siui.components.widgets.timedate import SiTimePicker`

```python
picker = SiTimePicker(parent)
picker.setTime(datetime.time(0, 0, 0))
picker.adjustSize()
```

### 14.3 SiTimeSpanPicker（时长）
`from siui.components.widgets.timedate import SiTimeSpanPicker`

```python
picker = SiTimeSpanPicker(parent)
picker.setTimeSpan(datetime.timedelta())
picker.adjustSize()
```

---

## 十五、时间线（Timeline）

### 15.1 SiTimeLine ⭐ 推荐
`from siui.components.widgets.timeline import SiTimeLine, SiTimeLineItem`

```python
tl = SiTimeLine(parent)
tl.setFixedWidth(600)

item = SiTimeLineItem(parent)
item.setContent("11:45:14", "描述文字")
item.setIcon(SiGlobal.siui.iconpack.get("ic_fluent_warning_shield_filled"))
item.setIconHint("安全警告")
item.setThemeColor(color)
tl.addWidget(item)
```

---

## 十六、图表（Charts）

### 16.1 SiTrendChart（趋势折线图）⭐ 推荐
`from siui.components.chart import SiTrendChart`

```python
chart = SiTrendChart(parent)
chart.resize(900, 340)
chart.setPointList([QPointF(i, random.random()) for i in range(-50, 51)])
chart.setToolTipFunc(lambda x, y: f"X:{x} Y:{y}")
chart.setQuality(1)
chart.adjustViewRect()
```

---

## 十七、消息与对话框

### 17.1 侧边栏消息
```python
# 简单
SiGlobal.siui.windows["MAIN_WINDOW"].LayerRightMessageSidebar().send(
    "消息内容", msg_type=1, fold_after=5000)

# 带标题
SiGlobal.siui.windows["MAIN_WINDOW"].LayerRightMessageSidebar().send(
    title="标题", text="内容", msg_type=4, icon=icon, fold_after=5000,
    slot=lambda: print("clicked"))

# 自定义消息框
box = SiSideMessageBox()
box.setMessageType(type_)
box.setFoldAfter(3000)
SiGlobal.siui.windows["MAIN_WINDOW"].LayerRightMessageSidebar().sendMessageBox(box)
```
**msg_type**: 0=标准, 1=成功, 2=提示, 3=警告, 4=错误

### 17.2 子页面 & 模态弹窗
```python
# 子页面
SiGlobal.siui.windows["MAIN_WINDOW"].layerChildPage().setChildPage(MyPage(self))

# 模态弹窗
SiGlobal.siui.windows["MAIN_WINDOW"].layerModalDialog().setDialog(MyDialog(self))

# 全局抽屉
SiGlobal.siui.windows["MAIN_WINDOW"].layerLeftGlobalDrawer().showLayer()
```

---

## 十八、页面框架（SiPage）⭐ 推荐

`from siui.components.page import SiPage`

```python
class MyPage(SiPage):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setPadding(64)
        self.setScrollMaximumWidth(1000)
        self.setScrollAlignment(Qt.AlignLeft)
        self.setTitle("页面标题")
        self.setAttachment(self.titled_widgets_group)
```

### SiliconApplication 应用模板
`from siui.templates.application.application import SiliconApplication`

```python
class MyApp(SiliconApplication):
    def __init__(self):
        super().__init__()
        self.layerMain().setTitle("Title")
        self.layerMain().addPage(MyPage(self), icon=icon, hint="提示", side="top")
        self.layerMain().setPage(0)
        SiGlobal.siui.reloadAllWindowsStyleSheet()
```

---

## 十九、图标包（Icon Pack）

```python
# 获取图标（用于 setSvgIcon）
icon = SiGlobal.siui.iconpack.get("ic_fluent_home_filled")

# 转 QPixmap
pixmap = SiGlobal.siui.iconpack.toPixmap("ic_fluent_icon_name")

# 转 QIcon
qicon = SiGlobal.siui.iconpack.toIcon("ic_fluent_icon_name")

# 自定义颜色
SiGlobal.siui.iconpack.get("ic_fluent_icon", color_code=color)

# 从 SVG 数据构建
SiGlobal.siui.iconpack.getFromData(svg_data, color)

# 图标包管理
SiGlobal.siui.iconpack.getClassNames()  # 所有图标包名称
SiGlobal.siui.iconpack.getDict(package) # 图标字典型
# 加载图标
siui.core.globals.SiGlobal.siui.loadIcons(icons_dict)
```

---

## 二十、颜色与主题

### 20.1 常用 SiColor Token
| Token | 用途 |
|-------|------|
| `SiColor.TEXT_A` | 主文字色 |
| `SiColor.TEXT_B` | 次要文字色 |
| `SiColor.TEXT_C` | 辅助文字色 |
| `SiColor.TEXT_D` | 弱化文字色 |
| `SiColor.THEME` | 主题色 |
| `SiColor.INTERFACE_BG_A ~ E` | 背景色 (A 最深, E 最浅) |
| `SiColor.BUTTON_OFF / ON / HOVER` | 按钮状态色 |
| `SiColor.SVG_NORMAL` | SVG 图标色 |
| `SiColor.PROGRESS_BAR_COMPLETING` | 进度条完成色 |
| `SiColor.SIDE_MSG_THEME_SUCCESS` | 消息栏成功色 |
| `SiColor.TITLE_INDICATOR` | 标题指示色 |
| `SiColor.SURFACE` | 卡片表面色 |

### 20.2 工具方法
```python
color = SiColor.trans(base_color, alpha)  # 透明度混合
self.getColor(SiColor.TEXT_A)            # 获取颜色
```

---

## 二十一、字体（Font）

```python
from siui.gui import SiFont
from siui.core import GlobalFont

label.setFont(SiFont.tokenized(GlobalFont.XL_MEDIUM))  # 超大
label.setFont(SiFont.tokenized(GlobalFont.M_NORMAL))   # 中等
label.setFont(SiFont.tokenized(GlobalFont.M_BOLD))     # 中等加粗
label.setFont(SiFont.tokenized(GlobalFont.S_NORMAL))   # 小
SiFont.getFont(size=14)  # 自定义字号
```

---

## 二十二、特效（Effects）

```python
from siui.core import SiQuickEffect

# 投影
SiQuickEffect.applyDropShadowOn(widget, color=(28, 25, 31, 255), blur_radius=48)
```

---

## 二十三、原子操作

| 分类 | 操作 | 说明 |
|------|------|------|
| **Flag** | `setSiliconWidgetFlag(Si.AdjustSizeOnTextChanged)` | 文字变化时自动调整尺寸 |
| **Flag** | `setSiliconWidgetFlag(Si.EnableAnimationSignals)` | 启用动画信号 |
| **颜色** | `setColorTo(color)` | 背景色动画过渡 |
| **颜色** | `setFixedStyleSheet(qss)` | 固定样式(不受主题影响) |
| **颜色** | `colorGroup().assign(SiColor.XXX, value)` | 自定义某颜色的值 |
| **提示** | `setHint(html)` | 工具提示(支持 HTML) |
| **动画** | `moveTo(x, y)` | 移动到坐标 |
| **动画** | `resizeTo(w, h)` | 调整到尺寸 |
| **SVG** | `setSvgSize(w, h)` | 设置 SVG 图标尺寸 |

---

*文档生成日期: 2026-06-26*
*基于 Gallery for siui v1.14.514 代码分析*
