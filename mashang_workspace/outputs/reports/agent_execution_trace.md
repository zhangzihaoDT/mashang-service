# Agent 执行链路：从自然语言目标到分析任务编排

> 图 3 — 面向汽车市场洞察与经营决策的 Agent Harness 智能分析工作台

---

## User Goal

```
分析昨天 LS8 锁单城市分布，并生成经营分析报告。
```

---

## Agent Execution Trace

### [1] Read AGENTS.md

| 字段 | 内容 |
|------|------|
| 文件 | `AGENTS.md`（workspace 级 + 根目录级） |
| 目的 | 理解项目结构、工作原则、脚本路径约定 |
| 关键信息 | `runtime_scripts/` 存放 Core 脚本，`docs/` 存放业务文档，`utils/` 存放共享工具 |
| 输出 | 确认项目结构，确定分析脚本应放在 `runtime_scripts/`，输出放在 `outputs/` |

### [2] Inspect metric definitions

| 字段 | 内容 |
|------|------|
| 文件 | `docs/metric_definitions.md` |
| 目的 | 确认"锁单数"指标口径 |
| 关键信息 | `lock_count = COUNTD(order_number)` WHERE `lock_time IS NOT NULL` |
| 时间字段 | `lock_time` |
| 数据集 | `dataset/order_data.parquet` |

### [3] Parse user intent

```
Input: "分析昨天 LS8 锁单城市分布，并生成经营分析报告。"

Parsed Context:
{
  "metric":           "lock_count",
  "time_window":      "yesterday",
  "series":           "LS8",
  "group_by":         "license_city",
  "analysis_type":    "distribution",
  "output_format":    "report"
}
```

| 意图字段 | 解析值 | 说明 |
|----------|--------|------|
| 指标 | lock_count | 锁单数 |
| 时间 | yesterday → 2026-06-14 | 动态解析为实际日期 |
| 车系 | LS8 | 仅分析 LS8 车型 |
| 维度 | license_city | 按城市分组 |
| 产出 | CSV + 图表 + HTML 报告 | 经营分析报告格式 |

### [4] Resolve execution context

```
Context Resolved:
- date:       2026-06-14 (yesterday from system clock)
- series:     LS8
- metric:     lock_count = COUNTD(order_number)
- dimension:  license_city
- filters:    lock_time >= 2026-06-14 00:00 AND lock_time < 2026-06-15 00:00
- series == "LS8"
```

动态上下文解析完成，传递给执行引擎。

### [5] Execute analysis query

```python
# 伪代码 — 实际实现见 runtime_scripts/demo_ls8_city_distribution.py
df = pd.read_parquet("dataset/order_data.parquet")
df = df[df["lock_time"].notna()]
mask = (df["lock_time"] >= "2026-06-14") &
       (df["lock_time"] <  "2026-06-15") &
       (df["series"] == "LS8")
result = df[mask].groupby("license_city")["order_number"].nunique()
```

| 指标 | 结果 |
|------|------|
| 总锁单数 | 87 |
| 覆盖城市 | 47+ |
| TOP1 城市 | 成都市（7 单） |
| TOP3 集中度 | 19.5% |

### [6] Generate table asset

| 字段 | 内容 |
|------|------|
| 文件 | `outputs/tables/ls8_city_distribution.csv` |
| 格式 | UTF-8 BOM CSV |
| 列 | `license_city`, `lock_count`, `share` |

```csv
license_city,lock_count,share
成都市,7,0.0805
重庆市,6,0.069
北京市,4,0.046
...
```

### [7] Generate chart asset

| 字段 | 内容 |
|------|------|
| 文件 | `outputs/charts/ls8_city_distribution.png` |
| 类型 | 水平条形图（TOP15） |
| 风格 | Raccoon Research 视觉规范 |
| 分辨率 | 180 DPI |

图表要素：
- 水平条形图，按锁单数降序排列
- TOP1 城市（成都）以金色高亮
- 每个条形标注锁单数值
- 底部注明数据来源与口径

### [8] Generate HTML report

| 字段 | 内容 |
|------|------|
| 文件 | `outputs/reports/ls8_city_distribution_report.html` |
| 模板 | 内嵌样式（Raccoon Research 品牌色系） |
| 布局 | KPI 卡片 / 核心结论 / 数据表 / 图表 / 执行链路 / 口径说明 |

报告章节：
1. **KPI 卡片** — 总锁单数、覆盖城市数、TOP1 城市、TOP3 集中度
2. **核心结论** — 4 条关键业务洞察
3. **城市分布 TOP20** — 完整数据表（含排名、锁单数、占比、累计）
4. **城市分布图表** — TOP15 条形图
5. **Agent 执行链路** — 8 步骤 trace 表
6. **生成资产** — 输出文件列表
7. **数据口径说明** — 数据源、时间、筛选条件、口径定义

---

## Generated Assets

```
outputs/
├── tables/
│   └── ls8_city_distribution.csv        # 城市分布数据表
├── charts/
│   └── ls8_city_distribution.png         # 城市分布条形图
└── reports/
    ├── ls8_city_distribution_report.html  # 经营分析报告
    └── agent_execution_trace.md           # 本执行链路文档
```

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Harness                             │
├─────────────────────────────────────────────────────────────┤
│ User Intent  ──→  Context Parser  ──→  Executor  ──→  Assets │
│                                                             │
│  "LS8 城市分布"     metric/series/     run script      CSV  │
│                     time/dimension     + generate      Chart│
│                                        + render       HTML  │
└─────────────────────────────────────────────────────────────┘
```

*Agent Harness · 面向汽车市场洞察与经营决策的智能分析工作台*
