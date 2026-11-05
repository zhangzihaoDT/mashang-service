# 图 4｜连续多轮追问能力：从车型结构下钻到城市分布

> 面向汽车市场洞察与经营决策的 Agent Harness 智能分析工作台
> 本案例使用真实数据进行计算，展示 Agent Harness 的连续追问能力。

---

## User Goal

通过连续追问，从"昨天锁单数分车型"下钻到"LS8 城市分布"，再进一步识别异常城市，并生成日报结论。

```
R1: 昨天锁单数分车型
R2: 那 LS8 的城市分布呢？
R3: 哪些城市相比近 7 日均值下降明显？
R4: 生成一段可以放进日报的结论
```

---

## Round 1

```
User:
  昨天锁单数分车型

Agent Understanding:
  - metric:      lock_count (锁单数)
  - time_range:  yesterday (昨天 → 2026-06-14)
  - dimension:   model (车型)
  - group_by:    model

Context Created:
  {
    "metric": "lock_count",
    "time_window": "yesterday",
    "group_by": "model"
  }

Script Resolution:
  lock_count + group_by=model → runtime_scripts/lock_by_model.py
  Args: --date 2026-06-14 --limit 7

Agent Output:
```

| 车型 | 锁单数 | 占比 |
|------|--------|------|
| LS6 | 189 | 34.2% |
| LS7 | 33 | 6.0% |
| L6 | 105 | 19.0% |
| L7 | 40 | 7.2% |
| **LS8** | **87** | **15.7%** |
| LS9 | 96 | 17.4% |
| LS9Hyper | 3 | 0.5% |

```
Key Insight: LS8 昨日锁单 87 单，占全车型 15.7%，排名第 4。具备一定规模，
值得进一步下钻分析城市分布。
```

---

## Round 2

```
User:
  那 LS8 的城市分布呢？

Context Inherited (from R1):
  - time_window:  yesterday ✓
  - metric:       lock_count ✓
  - group_by:     model (将被覆盖)

New Parsing:
  - series:   LS8
  - group_by: city ("城市分布")

Context Resolved:
  {
    "metric": "lock_count",
    "time_window": "yesterday",
    "series": "LS8",
    "group_by": "city"
  }

Inheritance Chain:
  R1 ──time──▶ R2  ← time_window inherited from R1
  R1 ──metric─▶ R2  ← metric inherited from R1

Script Resolution:
  lock_count + group_by=city → runtime_scripts/lock_city_distribution.py
  Args: --date 2026-06-14 --series LS8

Agent Output:
```

| # | 城市 | 锁单数 | 占比 |
|---|------|--------|------|
| 1 | 成都 | 7 | 8.0% |
| 2 | 重庆 | 6 | 6.9% |
| 3 | 北京 | 4 | 4.6% |
| 4 | 宁波 | 3 | 3.4% |
| 5 | 苏州 | 3 | 3.4% |
| 6 | 上海 | 3 | 3.4% |
| 7 | 贵阳 | 3 | 3.4% |
| 8 | 太原 | 3 | 3.4% |
| 9-19 | 杭州/福州/绍兴等 | 各 2 | 各 2.3% |
| — | 其他 28+ 城市 | 各 1 | 合计 37.9% |

```
Key Insight: LS8 覆盖 47+ 城市，呈现"多点开花"格局。TOP3 集中度仅 19.5%，
没有单一城市过度依赖。西南双核（成都+重庆）合计 14.9%。
```

---

## Round 3

```
User:
  哪些城市相比近 7 日均值下降明显？

Context Inherited (from R2):
  - series:       LS8 ✓
  - metric:       lock_count ✓
  - group_by:     city ✓
  - time_window:  yesterday ✓

New Parsing:
  - time_window:  last_7_days (作为比较基线)
  - implied:      analysis_type = compare (异常识别)

Context Resolved:
  {
    "metric": "lock_count",
    "time_window": "yesterday",
    "series": "LS8",
    "group_by": "city",
    "analysis_type": "compare",
    "baseline": "last_7_days"
  }

Inheritance Chain:
  R1 ───time──────▶ R2 ──series──▶ R3  ← series inherited from R2
                        ──metric──▶ R3  ← metric inherited from R2
                        ──city────▶ R3  ← group_by inherited from R2

Computation:
  Baseline: 2026-06-07 ~ 2026-06-13 (7 日平均)
  Target:   2026-06-14 (昨日)
  Metric:   COUNTD(order_number) per city per day

Agent Output:
```

| 城市 | 昨日 | 7日均值 | 变化 | 降幅 |
|------|------|---------|------|------|
| 北京 | 4 | 2.43 | +1.57 | +65% |
| 成都 | 7 | 5.86 | +1.14 | +19% |
| 宁波 | 3 | 2.14 | +0.86 | +40% |
| 重庆 | 6 | 5.29 | +0.71 | +13% |
| 上海 | 3 | 2.43 | +0.57 | +23% |
| 苏州 | 3 | 2.57 | +0.43 | +17% |
| 杭州 | 2 | 2.29 | -0.29 | -13% |
| 广州 | 2 | 2.57 | -0.57 | -22% ⚠ |
| 福州 | 2 | 2.71 | -0.71 | -26% ⚠ |
| 南京 | 2 | 2.86 | -0.86 | -30% ⚠ |

```
Key Insight: 广州、福州、南京等城市昨日锁单量低于近 7 日均值 20% 以上，
建议排查区域运营动作与市场波动。
```

---

## Round 4

```
User:
  生成一段可以放进日报的结论

Context Inherited (from R3):
  - series:        LS8 ✓
  - metric:        lock_count ✓
  - time_window:   yesterday ✓
  - group_by:      city ✓
  - analysis_type: summary

Context Resolved:
  {
    "metric": "lock_count",
    "time_window": "yesterday",
    "series": "LS8",
    "group_by": "city",
    "analysis_type": "summary"
  }

Inheritance Chain:
  R1 ──time──▶ R2 ──series──▶ R3 ──full──▶ R4
                  ──metric──▶        context
                  ──city────▶        inherited

Agent Output:
```

```
┌─────────────────────────────────────────────────────────────────────┐
│ 📋 LS8 锁单日报 · 2026-06-14                                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   昨日 LS8 共计 87 单，覆盖 47+ 城市，城市分布广泛。                 │
│                                                                     │
│   头部城市表现：成都(7单,较均值+1)、重庆(6单,较均值+1)、            │
│   北京(4单,较均值+2)                                                │
│                                                                     │
│   ⚠ 异常关注城市：广州、福州、南京等昨日锁单量低于近 7 日均值       │
│   20% 以上，建议排查区域运营动作与市场波动。                         │
│                                                                     │
│   整体评价：LS8 锁单态势平稳，多点开花，西南双城持续发力。中腰部    │
│   城市（宁波、苏州、贵阳）表现稳定，可择机加大运营投放。            │
├─────────────────────────────────────────────────────────────────────┤
│  生成时间: 2026-06-15 14:30:00                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Why This Matters

本案例展示 Agent Harness 的核心差异化能力：

| 能力 | Round 1 → 2 | Round 2 → 3 | Round 3 → 4 |
|------|------------|------------|------------|
| **时间继承** | yesterday ✓ | yesterday ✓ | yesterday ✓ |
| **指标继承** | lock_count ✓ | lock_count ✓ | lock_count ✓ |
| **维度继承** | — | city ✓ | city ✓ |
| **车系继承** | — | LS8 ✓ | LS8 ✓ |
| **分析深化** | 车型结构 → 城市分布 | 分布 → 异常识别 | 异常 → 日报结论 |

**系统不是单次问数工具，而是能够继承上下文、连续下钻、对比分析并生成业务结论的 Data Agent Harness。**

---

## Architecture: Context Inheritance Chain

```
Round 1                   Round 2                   Round 3                   Round 4
┌──────────────┐        ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│ 分车型       │  ──▶   │ LS8城市分布  │  ──▶   │ 异常识别     │  ──▶   │ 生成日报结论 │
│              │        │              │        │              │        │              │
│ metric       │──time──│ metric      │──series│ metric       │──full──│ metric       │
│ time         │──metric│ time         │──metric│ series       │        │ series       │
│ group_by     │        │ series       │──city──│ group_by     │        │ group_by     │
│              │        │ group_by     │        │ baseline     │        │ output_style │
└──────────────┘        └──────────────┘        └──────────────┘        └──────────────┘
```

---

## Generated Scripts & Assets

| 轮次 | Script | Command |
|------|--------|---------|
| R1 | `runtime_scripts/lock_by_model.py` | `--date 2026-06-14 --limit 7` |
| R2 | `runtime_scripts/lock_city_distribution.py` | `--date 2026-06-14 --series LS8` |
| R3 | `runtime_scripts/demo_followup_ls8_city.py` | (comparison engine, inline) |
| R4 | `runtime_scripts/demo_followup_ls8_city.py` | (generation engine, inline) |

| Asset | Path |
|-------|------|
| Trace Document | `outputs/reports/followup_trace_ls8_city.md` |
| Demo Script | `runtime_scripts/demo_followup_ls8_city.py` |
| Eval Case | `eval/cases/followup_cases.json` (case: followup_ls8_four_round_001) |

---

*Agent Harness · 面向汽车市场洞察与经营决策的智能分析工作台*
