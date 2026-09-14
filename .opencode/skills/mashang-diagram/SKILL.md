---
name: mashang-diagram
description: Project-owned diagram router for mashang-service. Use when a request needs a diagram, chart, or figure (图示/图表/可视化/画图) and you must decide between the project's own chart capability and the upstream diagram-design skill. Routes Milestone Temporal Dumbbell (里程碑时间哑铃图) to capabilities/diagram; routes every other visual type to the diagram-design skill, whose type references, visual rules, style-guide gate, and self_check remain the source of truth.
license: MIT
---

# mashang-diagram

项目自有的 **diagram 路由 Skill**。它不重画图形，也不复制 upstream；它决定**该由谁画**，然后交棒。

## 定位与边界

**Capability 决定「这是什么图、数据怎么算、几何怎么画」；Skill 决定「什么时候该用它、怎么放进研究报告、采用什么视觉皮肤」。**

```text
User intent
   ↓
/diagram → mashang-diagram（本 Skill）
   ↓
识别 visual type
   ├─ 自有类型 → capabilities/diagram（Mashang Diagram Capability）
   └─ 通用类型 → diagram-design（upstream Skill，只读消费）
   ↓
diagram-design visual rules / self_check
```

- 本 Skill **不修改** upstream `diagram-design`（`.opencode/skills/diagram-design` 是 symlink）。
- 本 Skill **不内联**图表几何算法；几何属于 `capabilities/diagram`。
- 视觉皮肤是**参数**，不是路由层的硬编码。路由不写死任何调色板。

## 第一步：识别 visual type

从用户意图里抽出两件事：**这张图在比较什么**，以及**比较的轴是不是时间**。

| 用户意图 | 类型 | 路由 |
|----------|------|------|
| 两个主体在**多个对应里程碑**上的时间位置与时间差（如技术落地节奏、法规生效对比、发布计划对齐） | **Milestone Temporal Dumbbell** | → 自有：`capabilities/diagram` |
| 同量纲两点数值比较，关注差距（before/after、target vs actual） | Dumbbell（数值型，bar 变体） | → upstream `diagram-design`（`type-bar.md`） |
| 单主体事件沿时间轴铺开 | Timeline | → upstream `diagram-design`（`type-timeline.md`） |
| 其他任何类型 | 见 upstream 40 类型表 | → upstream `diagram-design` |

规则：

- 时间轴 + 成对事件节点 → 走自有 Milestone Temporal Dumbbell。
- 时间轴 + 单侧事件序列 → 走 upstream Timeline。
- 量纲是数值而不是日期 → 走 upstream 数值型 Dumbbell（bar 变体）。
- 拿不准时，先读两边对应的 type reference，再选；不要凭标题猜。

## 自有类型：Milestone Temporal Dumbbell

详细规范见 [`references/type-milestone-dumbbell.md`](references/type-milestone-dumbbell.md)。

工作流：

1. **整理数据契约。** 一行一个 milestone，字段：`milestone / entity_a / date_a / event_a / entity_b / date_b / event_b`；`delta_days` 由 capability 从日期派生，不要手填。
2. **决定 skin。** 默认沿用 `DumbbellTheme`（全局视觉识别）；如需项目报告皮肤，构造 `DumbbellTheme` 覆盖 token，而不是在路由层写死颜色。
3. **调用 capability 渲染。**

   ```bash
   python -m capabilities.diagram.dumbbell \
     --input <rows.json> --format html \
     --output-root mashang_workspace/outputs
   ```

   Python API（需要自定义 skin 时）：

   ```python
   from capabilities.diagram.dumbbell import build_chart, render
   from capabilities.diagram.theme import DumbbellTheme
   chart = build_chart(payload).validate()
   html = render(chart, DumbbellTheme(paper="#FFFFFF"))
   ```

4. **跑 upstream 自检。** 生成的 HTML 必须通过：

   ```bash
   python .opencode/skills/diagram-design/scripts/self_check.py <generated.html>
   ```

5. **Skill 负责收尾：** 标题、副标题、说明文字、数据来源与口径、在报告中的版式位置。

## 通用类型：委派 upstream diagram-design

对于任何非自有类型：

1. 读取 `.opencode/skills/diagram-design/SKILL.md`，以它为唯一事实来源，走它自己的 type 选择、style-guide gate、复杂度预算与 `self_check.py`。
2. 不要绕过它的 gate，也不要把自有类型塞进它的类型表。
3. 本 Skill 只保留「识别 + 交棒」职责，不复制它的 type references。

## 视觉与品牌口径

- 图表内容（数据、几何、可访问性）由 capability 保证。
- 报告版式、标题层级、卡片与皮肤，优先沿用 `mashang_workspace/docs/report_visual_system.md` 与 `diagram-design` 的视觉规则。
- 路由层**不得写死** raccoon / 任何调色板；皮肤通过 `DumbbellTheme` 注入。

## 参考

- 自有类型规范：`references/type-milestone-dumbbell.md`
- 数据能力：`capabilities/diagram/README.md`
- upstream 类型：`.opencode/skills/diagram-design/references/type-*.md`
- 接入说明：`.opencode/integrations/diagram-design.md`
