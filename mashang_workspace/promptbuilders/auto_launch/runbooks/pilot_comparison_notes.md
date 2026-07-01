# Pilot Comparison Notes

## 背景

截至 2026-07，auto_launch 已完成两个真实 pilot run：

| Pilot | 路径 | 来源 | 事件 |
|-------|------|------|------|
| compatitor_48h | ChatGPT Plan | ChatGPT Plan 直接输出 | 问界M7官方权益调整 |
| wenjie_m7_72h | Volc Search assisted | 火山搜索 → Prompt → intake | 问界M7增程长续航版上市 |

## ChatGPT Plan 路径

### 优势

- **官方源更好**：source_tier 以 official 为主（鸿蒙智行官网、AITO官网），来源权威性高
- **结论保守**：confirmed_facts 均有明确来源支撑，inferences 边界清晰
- **report.md 可直接用**：适合作为日报/晨报直接进入业务讨论
- **证据链完整**：每条事实关联 source_id，missing_evidence 诚实记录

### 问题

- **事件发现偏弱**：Plan 输出更多是 monitor 型结果（权益变化），而非新事件发现
- **对输入 prompt 质量敏感**：如果 prompt 不精确，输出容易泛化
- **无法主动搜索**：依赖 Plan 内置的搜索能力，外部无法控制搜索范围

### 适用场景

- Daily radar / 日常监控
- 已知事件的标准简报
- 需要高权威来源的场景

## Volc-assisted 路径

### 优势

- **事件发现更强**：能主动搜索并发现增量信息（如长续航版上市、交付报道、销量里程碑）
- **媒体覆盖集中**：一次搜索可以覆盖多个主流媒体来源
- **可控性强**：可以根据 query plan 精确控制搜索方向和范围

### 问题

- **官方源不足**：搜索结果以 mainstream_media（新浪系）为主，缺少 official 来源
- **source_name 不规范**：当前 source_name 使用了文章标题而非媒体名称（如 "售价29.98万起..." 而非 "新浪汽车"）
- **来源层级单一**：5 条结果全部来自 mainstream_media，缺少 industry_media 和 official 的多样性

### 适用场景

- Deep dive / 特定事件补证
- 需要主动搜索发现信息的场景
- 作为 Plan 输出的补充验证

## 直接对比

| 维度 | ChatGPT Plan | Volc-assisted |
|------|-------------|---------------|
| 来源权威性 | ✅ official 为主 | ⚠️ mainstream_media 为主 |
| 事件发现能力 | ⚠️ 偏弱 | ✅ 更强 |
| 输出稳定性 | ✅ 稳定 | ⚠️ 依赖搜索结果质量 |
| 来源多样性 | ✅ 较好 | ⚠️ 单一（新浪系） |
| source_name 规范 | ✅ 网站名称 | ⚠️ 文章标题 |
| 适合场景 | 日报 / 日常监控 | Deep dive / 补证 |

## 当前决策

| 决策 | 说明 |
|------|------|
| Plan = daily radar 主路径 | ChatGPT Plan 作为日常监控的标准路径 |
| Volc = deep dive / 补证路径 | Volc-assisted 用于特定事件深度挖掘和 Plan 输出的补充验证 |
| 暂不晋升 golden case | 两个 pilot 各有不足，不满足晋升条件 |

## 后续改进方向

### source_name 规范化

当前 Volc result-to-brief Prompt 输出中 `source_name` 使用了文章标题而非媒体名称。后续应更新 Prompt 要求同时输出：

```json
{
  "source_id": "S1",
  "source_name": "新浪汽车",
  "source_title": "售价29.98万起 全新问界M7增程长续航版正式上市",
  "source_url": "https://k.sina.cn/...",
  "source_tier": "mainstream_media"
}
```

### 官方源覆盖

Volc Search 的 query plan 应增加对官方域名的定向搜索（如 `aito.auto`、`hima.auto`、`鸿蒙智行` 官方渠道），以弥补官方源不足的问题。

### 来源多样性

Volc Search 的 `filter_sites` 应覆盖更多行业媒体（如 36氪、虎嗅、第一电动），避免过度依赖单一来源体系。
