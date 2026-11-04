# capabilities/diagram — Diagram Base Capability

## 能力定位

**领域无关的图表数据契约 + 确定性渲染原语。**

当前包含两个图表类型：

> **① Milestone Temporal Dumbbell（里程碑时间哑铃图）**
> 比较两个主体在多个对应里程碑上的时间位置及时间差。
>
> **② Comparison Line（对比折线图）**
> 多个主体在同一组有序类别上的同指标对比，用「颜色 + 线形」双编码区分主体。

- `Dumbbell Chart` — 结构类型：两点 + 连线 + 差值
- `Temporal` — 横轴是真实时间
- `Milestone` — 两个点不是连续测量值，而是关键事件/发布时间节点

不负责任何业务结论、事件事实核验或数据采集——那属于业务层或独立研究仓库。

## namespace 与入口

- Python:
  - `from capabilities.diagram.dumbbell import build_chart, load_chart, render`
  - `from capabilities.diagram.renderers.html import render_html, render_svg`
  - `from capabilities.diagram.compare_line import build_chart, load_chart, render`
  - `from capabilities.diagram.renderers.line import render_line_html, render_line_svg`
- CLI:
  - `python -m capabilities.diagram.dumbbell --input rows.json --format html`
  - `python -m capabilities.diagram.dumbbell --input rows.json --format json`
  - `python -m capabilities.diagram.compare_line --input rows.json --format html|svg|json`
- 消费方统一从仓库根 import `capabilities.diagram.*`。

## 类型一：Milestone Temporal Dumbbell（里程碑时间哑铃图）

### 数据契约（一行一个 milestone）

```text
milestone
entity_a
date_a
event_a
entity_b
date_b
event_b
delta_days   # 派生字段，date_b - date_a，不接受调用方输入
```

`delta_days` 永远由日期计算，保证图面与 JSON 契约一致。

输入 JSON 示例：

```json
{
  "title": "BEV / 端到端智驾方案落地时间差",
  "entity_a": "Tesla",
  "entity_b": "Huawei",
  "source_note": "示例数据",
  "rows": [
    {
      "milestone": "BEV 感知",
      "date_a": "2021-08-19",
      "event_a": "AI Day BEV",
      "date_b": "2022-05-07",
      "event_b": "ADS 1.0"
    }
  ]
}
```

示例文件：`examples/milestone_dumbbell_tesla_huawei.json`。

### 校验规则

- 至少一个 milestone 行
- milestone 非空且不可重复
- 日期支持 `YYYY-MM-DD` / `YYYY/MM/DD` / `YYYY.MM.DD`
- 两个主体名可从图表级或行级解析；行级多值冲突时报错
- 时间差方向固定为 `date_b - date_a`（负数表示 B 早于 A）

### 渲染设计

- 输出自包含 HTML（内联 SVG + 内联 CSS），唯一的远程资源是 Google Fonts 字体表。
- 无 JavaScript、无外部图片、无阴影，4px 网格。
- 横轴按真实日期比例映射，不为排版伪造等距。
- 视觉 token 是 `DumbbellTheme`（白底 / 深蓝墨 / raccoon 金焦点），可按需覆盖，不绑定业务语义。
- SVG 满足可访问性契约：`role="img"` + 前置 `<title>` + 前缀化 `id`。

## 类型二：Comparison Line（对比折线图）

多个主体在同一组**有序类别**（N0–N3、周次、月份、环节）上的数值对比。
重点不是单条序列的趋势，而是「谁在前、差距在哪一天/哪一步拉开」。

### 数据契约

```json
{
  "title": "LS8 NEO vs CM3 / LS8 / LS9 — 预售前 4 日累计小订",
  "categories": ["N0 末", "N1 末", "N2 末", "N3 末"],
  "series": [
    {"name": "LS8 NEO", "role": "own", "values": [3662, 4102, 4567, 4984]},
    {"name": "CM3", "values": [4687, 5014, 5485, 5959]},
    {"name": "LS8", "values": [6271, 7441, 8265, 9046]}
  ],
  "x_label": "第 N 日末",
  "y_label": "累计小订（单）",
  "source_note": "数据来源与口径",
  "markers": true
}
```

- `role="own"` 标记本品，只影响视觉强调（solid + 加粗 + 最上层），不携带业务语义；至多一个。
- `color` / `dash` 可逐条覆盖默认调色板（如客户已有品牌色）。
- 其余可选字段：`y_min` / `y_max` / `y_step`、`decimals`、`value_suffix`、`markers`（不填时 ≤ 8 个点自动显示标记点）。

校验规则：至少 2 个类别且不重复；至少 2 条序列、名称唯一；每条 `values` 长度必须等于类别数且为有限数值；`role` 只能是 `own` / `peer`。

### 视觉规则（沉淀经验）

1. **一个主体 = 一种颜色 + 一种线形**，颜色与线形双编码；四条以上同图时，仅靠颜色无法区分。
2. 本品固定 solid + 3.0px + 深蓝，且最后绘制压在最上层；对标主体按 clay/dash → sage/dashdot → mauve/longdash → steel/dash 轮换。
3. 图例画**线段样例**（带 dash），不画色块——读者先认线形，再认颜色。
4. 每条线在末端直接标数值，按最小 17px 间距避让，省掉图例与曲线之间的往返。
5. 点数 ≤ 8 显示标记点；更多点只保留线与末端点，避免点阵噪声。
6. 纵轴默认含 0（累计/存量类指标不截断）；确实需要放大差异时显式传 `y_min`，并在 `subtitle` 注明。

### CLI

```bash
python -m capabilities.diagram.compare_line --input capabilities/diagram/examples/comparison_line_ls8neo.json --format html
python -m capabilities.diagram.compare_line --input rows.json --format svg
python -m capabilities.diagram.compare_line --input rows.json --format json   # Result Contract
```

示例文件：`examples/comparison_line_ls8neo.json`（LS8 NEO 预售前 4 日累计小订实测数据）。

## outputs

- 默认输出根：仓库 `outputs/diagram/`（`charts/<slug>.html`），可用 `--output-root` 或 `--output` 覆盖。
- `outputs/diagram/` 已 gitignore（可再生产物）。

## tests

- 随包测试：`capabilities/diagram/tests/`，离线全绿。
- 其中 `test_dumbbell.py` 会把生成的 HTML 交给
  `.opencode/skills/diagram-design/scripts/self_check.py` 做可访问性与单文件安全自检（skill 不存在时跳过）。
- 已纳入 `make test` / `make ci` 门禁。

## 适用 / 不适用

- 适用：
  - Dumbbell：两个主体在多个对应里程碑上的时间位置与时间差，如技术方案落地节奏、法规生效对比、发布计划对齐。
  - Comparison Line：多个主体在同一组有序类别上的同指标对比，如预售前 N 日小订、分环节转化率、跨代际累计曲线。
- 不适用（not for）：
  - 单条序列在真实时间轴上的连续趋势（Comparison Line 的横轴是有序类别，不是时间刻度）。
  - 单主体事件沿时间轴铺开（用 timeline）。
  - 事件事实核验、数据采集、搜索（属于上层独立研究仓库）。
  - 业务口径与领域解释（属于 `mashang_workspace/` 或独立研究仓库）。

## 消费方记录

| 消费方 | 用途 | 状态 |
|--------|------|------|
| `.opencode/skills/mashang-diagram/` | 路由 `Milestone Temporal Dumbbell` 到本能力；type 规范见 `references/type-milestone-dumbbell.md` | 已接入 |
| `.opencode/skills/diagram-design/` | upstream：提供通用类型的视觉规则与 `self_check.py`（对生成 HTML 做自检） | 已接入（只读） |

## 演进约定

新增图表类型时，按本目录模式逐个沉淀（schema + renderer + CLI + tests + README 类型小节），
不提前搭建完整图表平台；只有在日常工作中重复出现时才升级为通用能力。
