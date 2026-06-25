---
name: cpca-weekly-data-capture
description: 第一时间捕捉乘联分会周度核心数据，并生成带置信度的三句话 fact_result JSON
---

# 乘联分会周度数据捕捉

## 能力定位

第一时间捕捉乘联分会/乘联会周度核心数据，比 CADA 官网更早获取 P0 早源。
完成 companion recall、全文 hydration、字段抽取、多源合并、period 防错，
并输出可消费的三句话 fact_result JSON。

## 适用场景

- 每周三下午监控 2026-W26 等数据周的核心指标
- 需要比 CADA 官网更早获取乘用车零售/新能源零售/渗透率
- 需要结构化 JSON + 可发布文本的 fact_result
- 需要追踪 first_signal 与 CADA final confirmation 的时间差

## 不适用场景

- 逐日高频监控（不是日内 tick 级工具）
- 个股/单一车型分析
- 非乘联分会发布的其他数据源

## 核心命令

make cpca-weekly-data-capture WEEK=2026-W25

## 默认输出位置

```
dataset/cpca_weekly/cpca_weekly_data_capture.json   # evidence/capture 原材料
dataset/cpca_weekly/cpca_weekly_fact_result.json     # 事实确认后的结果资产
mashang_workspace/outputs/reports/cpca_weekly_early_signal.html  # HTML 报告
```

## 核心 Workflow

1. Search P0/P1/P2 sources via 火山方舟 API
2. Companion recall: 发现 NEV 后自动补搜 passenger P0 文章
3. Hydrate: 对 P0/P0_final 文章抓取全文
4. Extract: 从全文提取 11 个结构化字段
5. Merge: 按 fact_period 合并多源 passenger/NEV/penetration
6. Select best_fact: 按字段完整度 + period 最新 + 置信度排序
7. Write: capture JSON + fact_result JSON + HTML report

## 重要约束

- WEEK 参数代表**数据归属周**，不是运行周
- 下周三运行时应传上一周的 WEEK
- 下游默认消费 best_fact，candidate_facts 和 rejected_facts 仅作诊断
- historical_mismatch 和 unknown period 不得进入 best_fact
- fact_result 中 publish_ready_level=full 时 confidence >= 0.9
- 无 CADA final source 时 confidence 最高 0.93
