# Bug 修复记录：HarmonyApp 页面 Scroll 内容默认垂直居中

## 摘要
HarmonyOS 应用（HarmonyApp）中，所有使用 `Scroll` 组件包裹卡片列表的页面，当卡片数量较少、内容总高度小于 Scroll 视口时，内容会被垂直居中显示，而非预期的靠顶部排列。涉及项目浏览器、便签页、框架页三个页面。

## 影响范围
- **文件**：
  - `entry/src/main/ets/pages/ProjectBrowserPage.ets` → 第 322 行的 `Scroll()`
  - `entry/src/main/ets/pages/NotesPage.ets` → 第 198 行的 `Scroll()`
  - `entry/src/main/ets/pages/FrameworkPage.ets` → 第 348 行的 `Scroll()`
- **触发条件**：Scroll 内子组件（Column / Flex）的内容高度小于 Scroll 的可用视口高度时
- **受影响**：所有含有 `Scroll` 滚动容器的页面
- **不受影响**：纯 `Column` 布局的页面（如 WelcomeContent、对话框）；内容总能填满 Scroll 视口的情况

## 根因分析

### ArkUI Scroll 组件的 align 默认值
ArkUI 中 `Scroll` 组件的 `align` 属性**默认值为 `Alignment.Center`**。这意味着当 Scroll 内部的子组件（即滚动内容）在尺寸上小于 Scroll 容器本身时，该子组件会在 Scroll 的交叉轴上（垂直方向）被居中放置。

### 原代码执行表现
```
Scroll 可用高度 = 视口高度 N px
  ↓
Column(卡片列表) 实际高度 = M px (M < N)
  ↓
Scroll 默认 align = Alignment.Center
  ↓
Column(卡片列表) 被垂直移动到 (N - M) / 2 处 → 视觉上"居中"
```

### 为什么代码中没有显式设置居中仍出现居中
`Scroll` 的 `align` 是一个**隐式默认值**（类似 `Column` 默认 `justifyContent(FlexAlign.Start)`、`Stack` 默认 `Alignment.Center`），开发者不设置时就使用该默认值。这与 `Stack` 默认居中弹窗的逻辑一致，但在滚动列表的场景中不符合直觉。

### 为什么之前没有发现
项目初期卡片数量较多（示例数据填充 + 固定高度 140px 的 NoteCard），总高度通常超过 Scroll 视口，不会触发对齐行为。当用户减少项目或新建项目较少时，内容高度不足，居中现象才显现。

## 修复方案

### 核心思路
在所有 `Scroll` 组件上显式设置 `.align(Alignment.Top)`，覆盖默认的 `Alignment.Center`，确保滚动内容始终从顶部开始排列。

### 修复后行为
```
Scroll 可用高度 = 视口高度 N px
  ↓
Column(卡片列表) 实际高度 = M px (M < N)
  ↓
Scroll align = Alignment.Top ✅
  ↓
Column(卡片列表) 固定在顶部，底部留空 → 已滚动到底部时无更多内容
```

### 关键代码
```typescript
// 之前（ProjectBrowserPage.ets）
Scroll() {
  Column() {
    ForEach(this.filteredProjects(), (item: ProjectItem) => {
      ProjectCard({ ... })
    })
  }
  .width('100%')
}
.layoutWeight(1)
.width('100%')

// 之后
Scroll() {
  Column() {
    ForEach(this.filteredProjects(), (item: ProjectItem) => {
      ProjectCard({ ... })
    })
  }
  .width('100%')
}
.layoutWeight(1)
.width('100%')
.align(Alignment.Top)        // ← 新增
```

### 同步修复的其他文件
| 文件 | 修改 |
|---|---|
| `NotesPage.ets` | 便签列表 `Scroll` + `.align(Alignment.Top)` |
| `FrameworkPage.ets` | 内容区 `Scroll` + `.align(Alignment.Top)` |

## 经验教训

### 规则：ArkUI Scroll 的 align 默认值为 Center
> 在 ArkUI 中，`Scroll` 组件的 `align` 属性默认为 `Alignment.Center`。当滚动内容不足视口高度时，内容会被垂直居中。需要靠顶排列时必须显式设置 `.align(Alignment.Top)`。

### 推荐检查清单
| 场景 | 做法 |
|------|------|
| Scroll 包裹的列表/内容区 | 显式设置 `.align(Alignment.Top)` |
| Scroll 包裹的弹窗/浮层 | 根据需求选择 `Top` 或 `Center` |
| 未来新增的 Scroll 页面 | 优先添加 `.align(Alignment.Top)` 避免忘记 |
| Content 为空时的空状态 | 用 `if/else` 分支显示空状态提示（已正确处理） |

### 项目中其他潜在风险点
`Scroll` 在所有 .ets 页面中的使用情况：

| 文件 | 是否已修复 | 备注 |
|------|-----------|------|
| `ProjectBrowserPage.ets` | ✅ | 项目卡片列表 |
| `NotesPage.ets` | ✅ | 便签卡片网格 |
| `FrameworkPage.ets` | ✅ | 辩题信息 + 框架节点树 |
| `NewDebateDialog.ets` | 🔲 不需要 | 表单 Scroll 内容通常充满视口 |

## 修复日期
2026-06-23
