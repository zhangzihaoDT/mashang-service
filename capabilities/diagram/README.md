# capabilities/diagram — Diagram Base Capability

## 能力定位

**领域无关的图表数据契约 + 确定性渲染原语。**

第一版只包含一个图表类型：

> **Milestone Temporal Dumbbell（里程碑时间哑铃图）**
> 用于比较两个主体在多个对应里程碑上的时间位置及时间差。

- `Dumbbell Chart` — 结构类型：两点 + 连线 + 差值
- `Temporal` — 横轴是真实时间
- `Milestone` — 两个点不是连续测量值，而是关键事件/发布时间节点

不负责任何业务结论、事件事实核验或数据采集——那属于业务层或 Research Application。

## namespace 与入口

- Python:
  - `from capabilities.diagram.dumbbell import build_chart, load_chart, render`
  - `from capabilities.diagram.renderers.html import render_html, render_svg`
- CLI:
  - `python -m capabilities.diagram.dumbbell --input rows.json --format html`
  - `python -m capabilities.diagram.dumbbell --input rows.json --format json`
- 消费方统一从仓库根 import `capabilities.diagram.*`。

## 数据契约（一行一个 milestone）

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

## 渲染设计

- 输出自包含 HTML（内联 SVG + 内联 CSS），唯一的远程资源是 Google Fonts 字体表。
- 无 JavaScript、无外部图片、无阴影，4px 网格。
- 横轴按真实日期比例映射，不为排版伪造等距。
- 视觉 token 是 `DumbbellTheme`（cream 底 / 深蓝墨 / raccoon 金焦点），可按需覆盖，不绑定业务语义。
- SVG 满足可访问性契约：`role="img"` + 前置 `<title>` + 前缀化 `id`。

## outputs

- 默认输出根：仓库 `outputs/diagram/`（`charts/<slug>.html`），可用 `--output-root` 或 `--output` 覆盖。
- `outputs/diagram/` 已 gitignore（可再生产物）。

## tests

- 随包测试：`capabilities/diagram/tests/`，离线全绿。
- 其中 `test_dumbbell.py` 会把生成的 HTML 交给
  `.opencode/skills/diagram-design/scripts/self_check.py` 做可访问性与单文件安全自检（skill 不存在时跳过）。
- 已纳入 `make test` / `make ci` 门禁。

## 适用 / 不适用

- 适用：两个主体在多个对应里程碑上的时间位置与时间差比较，如技术方案落地节奏、法规生效对比、发布计划对齐。
- 不适用（not for）：
  - 连续时间序列趋势（用 line chart）。
  - 单主体事件沿时间轴铺开（用 timeline）。
  - 事件事实核验、数据采集、搜索（属于上层 Research Application）。
  - 业务口径与领域解释（属于 `mashang_workspace/` 或 Research Application）。

## 消费方记录

| 消费方 | 用途 | 状态 |
|--------|------|------|
| `.opencode/skills/mashang-diagram/` | 路由 `Milestone Temporal Dumbbell` 到本能力；type 规范见 `references/type-milestone-dumbbell.md` | 已接入 |
| `.opencode/skills/diagram-design/` | upstream：提供通用类型的视觉规则与 `self_check.py`（对生成 HTML 做自检） | 已接入（只读） |

## 演进约定

新增图表类型时，按本目录模式逐个沉淀（schema + renderer + CLI + tests + README 类型小节），
不提前搭建完整图表平台；只有在日常工作中重复出现时才升级为通用能力。
