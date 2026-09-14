# Milestone Temporal Dumbbell

**Best for:** 比较两个主体在**多个对应里程碑**上的时间位置及时间差 —— 技术方案落地节奏（Tesla vs Huawei 的 BEV / 端到端）、法规生效对比、两家公司发布计划对齐、标准制定的先后手。横轴是真实时间，成对的事件节点用一条哑铃线连接，线中间标注天数差。

**Not this type:**

- **同量纲的两点数值比较**（before/after、target vs actual、两个 cohort 的指标差）→ 数值型 **Dumbbell**（upstream `type-bar.md` § Dumbbell variant）。两者都叫 dumbbell，但轴不同：数值型比的是**量纲上的距离**，本类型比的是**时间上的先后**。
- **单主体事件沿时间轴铺开**（release history、incident timeline）→ **Timeline**（upstream `type-timeline.md`）。Timeline 是一条基线 + 单向事件流；本类型是成对节点 + 差值。
- **连续趋势** → Line chart（upstream `type-line.md`）。
- **只有一对时间点** → 直接用表格或一句话，不值得画图。

与数值型 Dumbbell 的关系：共享「两点 + 连线 + 差值」的读图语法，但**轴语义不同**，所以在 `mashang-diagram` 里被路由成独立类型，而不是 bar 的变体。

## 数据契约

一行一个 milestone，字段固定：

```text
milestone    里程碑名称（行标签）
entity_a     主体 A 名称
date_a       A 在该里程碑的日期（YYYY-MM-DD）
event_a      A 的事件名（可选）
entity_b     主体 B 名称
date_b       B 在该里程碑的日期
event_b      B 的事件名（可选）
delta_days   date_b − date_a（派生字段，调用方不填）
```

- 主体名可在图表级给一次（`entity_a` / `entity_b`），也可逐行给；逐行给时同一侧必须一致，否则 capability 报错。
- `delta_days` 永远派生。正数表示 B 晚于 A，负数表示 B 早于 A。
- milestone 不可重复；日期不可为空。

规范 JSON 形态与示例见 `capabilities/diagram/examples/milestone_dumbbell_tesla_huawei.json`。

## 渲染与几何

由 `capabilities/diagram` 保证，Skill 不重画：

- **真实时间轴。** x 位置按日期线性映射，轴两端按数据范围留白；不为排版把不等间隔伪造成等距。
- **成对端点。** 每行两个圆点，颜色区分主体；先画连线再画点，让点压住线头。
- **差值标注。** 连线中点上方用遮罩矩形压底，写 `+261d` / `-12d`。
- **方向编码。** 连线在较晚的一端加箭头；差值正负与箭头方向一致。
- **自适应刻度。** 时间跨度小时按周/月，跨度大时按年，刻度标签不重叠。
- **可访问性。** `<svg role="img">` + 前置 `<title>` + 前缀化 `id`（由 capability 生成，满足 upstream `self_check.py`）。

语义 token（默认取自全局视觉识别，可通过 `DumbbellTheme` 覆盖）：

| 角色 | 用途 |
|------|------|
| `paper` | 画布底色、遮罩矩形填充 |
| `ink` / `ink_strong` | 里程碑标签、日期文字 |
| `muted` | 刻度标签、事件名、图例 |
| `entity_a` / `entity_b` | 两个主体的端点色与图例 |
| `accent` | 连线箭头 |
| `brown` | 差值数字 |

## 调用

```bash
python -m capabilities.diagram.dumbbell \
  --input <rows.json> --format html \
  --output-root mashang_workspace/outputs
```

`--format svg` 只出 SVG；`--format json` 出无产物的 Result Contract（含派生 `delta_days`）。

## Anti-patterns

- **伪造等距时间。** 把 2021→2022 和 2022→2024 画成等长，等于篡改时间差。
- **只标一个端点。** 两个日期都要写出；只标差值会让读者无法验证几何。
- **把连线当轨迹。** 哑铃线只表示两点的时间距离，不代表中间发生过什么、也不保证单调。
- **三条以上端点。** 超过两个主体，连线失去意义，应拆成多张图或改用别的类型。
- **差值方向不明。** 必须明确 `delta = B − A`；图例或来源行要写清。
- **缺口端点悄悄丢掉。** 某主体缺日期时，要么标注缺失，要么显式说明剔除，不能静默删行。
- **在路由层写死调色板。** 皮肤只能通过 `DumbbellTheme` 注入。

## 收尾（Skill 职责）

capability 只出图。放进研究报告时，由 Skill 负责：

- 标题与副标题（`title` / `subtitle`）；
- 数据来源、时间窗口、口径（`source_note`，会渲染到页脚）；
- 与正文的衔接说明；
- 生成后跑 `python .opencode/skills/diagram-design/scripts/self_check.py <generated.html>`。

## Examples

- 结构示例：`capabilities/diagram/examples/milestone_dumbbell_tesla_huawei.json`
- 渲染产物示例：`python -m capabilities.diagram.dumbbell --input capabilities/diagram/examples/milestone_dumbbell_tesla_huawei.json --output /tmp/dumbbell.html`
- 测试（含 self_check 集成）：`pytest capabilities/diagram/tests -q`
