# CPCA Weekly Data Capture Dataset Contract

## 归属与角色

- `cpca-weekly-data-capture` 是 **workspace Skill**（正式注册）。
- Skill 定义位置：
  `mashang_workspace/.opencode/skills/cpca-weekly-data-capture/SKILL.md`
- `dataset/cpca_weekly/` 是 **service-level runtime dataset asset**。
- dataset 由 `mashang_workspace` 的 `cpca-weekly-data-capture` Skill 管理和更新。
- 底层脚本：`mashang_workspace/research_scripts/cpca_weekly_early_signal.py`

## 运行入口

```bash
make cpca-weekly-data-capture WEEK=2026-W26
```

**`WEEK` 表示数据归属周，不是运行周。**
例如 2026-07-01（周三）运行时，应传 `WEEK=2026-W26`（上一周数据）。

## Dataset 文件

| 文件 | 说明 |
|------|------|
| `cpca_weekly_data_capture.json` | **evidence / 原材料捕捉结果** — first_signal、final_confirmation、evidence、core_metrics |
| `cpca_weekly_fact_result.json` | **事实确认后的结果资产** — 按 detected_period 归因，带置信度和可发布文本 |

## 消费规则

- 下游默认只消费：
  - `best_fact.publish_ready_text`
  - `best_fact.publish_ready_plaintext`
  - `best_fact.structured_metrics`
  - `best_fact.source_consensus`
- `candidate_facts` 仅作候选诊断，**不作为默认发布结果**
- `rejected_facts` 仅作排除原因诊断
- `consumer_contract` 定义在 `fact_result` 顶层字段

## capture_status 规则

| status | 条件 |
|--------|------|
| `evidence_only` | 有命中但未抽取到核心字段 |
| `early_only` | P0 命中 + 抽取到核心字段，CADA 未发布 |
| `final_confirmed` | CADA 发布且数据一致 |
| `conflict` | CADA 发布但数据不一致 |

## Runtime JSON 提交策略

- `dataset/cpca_weekly/*.json` 是运行时产物
- 默认不提交 Git（`dataset/` 在 `.gitignore` 中）
- 无需修改 `.gitignore`
- README 已在 workspace docs 中，不依赖 dataset 目录

## Quality Gates

| Gate | 说明 |
|------|------|
| `period_confirmed` | period 与目标周兼容 |
| `headline_fields_complete` | PV + NEV + PEN 三个头部字段中 ≥2 个 |
| `full_publish_fields_complete` | 全部 11 个结构化字段齐全 |
| `complete_p0_pair_found` | passenger P0 与 NEV P0 均已找到 |
| `final_source_missing` | CADA 官网尚未命中 |

## Source Hierarchy

| 层级 | 源 | 角色 |
|------|-----|------|
| P0 | stcn.com / 人民财讯 / 证券时报网 | early_signal |
| P0_final | CADA 官网 | final_authoritative |
| P1 | 新浪财经、东方财富、财联社、每日经济新闻 | fast_repost |
| P2 | 搜狐 | near_fulltext_sync |
