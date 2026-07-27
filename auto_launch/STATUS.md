# Auto Launch Status

## Current Positioning

auto_launch is a fact-driven marketing event monitoring system for NEV brands and models.

Three core entrypoints:

```
search ─┐
        ├── facts ─── report
daily ──┘
```

- **search**: web search → normalized evidence → facts store
- **daily**: Planner 日报 / ChatGPT Daily Run → 按章节路由 → 多表写入
- **report**: facts store → target report (brand-daily, daily-brief)

Facts is the shared middle layer. search and daily are independent ingestion paths.

## Inbox Pipeline (daily 摄入层)

当前支持两种输入源，自动检测并走对应管线：

### 1. Planner 日报 (推荐)

结构化日报，带 `##` 章节标题 + Markdown 表格。4 种章节类型：

| 章节标题模式 | section_type | 路由目标 | 表 |
|-------------|-------------|---------|----|
| 可入库确认事件 / 品牌新事件 / confirmed | `brand_events` | confirmed_fact | `facts` + `evidence` |
| 高优先级弱信号 / 待复核 / review | `review_signals` | review_signal | `signals` |
| 未发现新增动作的品牌 / 品牌状态 | `brand_status` | brand_status | `brand_status` (upsert) |
| 品牌声量观察 / 声量 | `brand_volume` | brand_volume | `brand_volume` |

管线：`parse_contract → validate → route → upsert → audit`

### 2. Legacy 自由文本 (向后兼容)

传统 `## 标题 + - key: value` 格式或纯文本。走原有 keep/discard 二分类后写入 `facts` 表。

## Fact Store 多表架构

| 表 | 用途 | 写入来源 |
|----|------|---------|
| `facts` | 事件主表 (confirmed facts, fingerprint 去重) | Planner brand_events / legacy keep |
| `evidence` | 多信源证据 (关联 facts.fact_id) | facts insert 时自动写入 |
| `signals` | 弱信号 / 待审查 (fingerprint 去重, status=open) | Planner review_signals |
| `brand_status` | 品牌状态快照 (按 brand 幂等 upsert) | Planner brand_status |
| `brand_volume` | 品牌声量观测 (含 claim/type/intensity/evidence) | Planner brand_volume |

## CLI Contract

| Command | Role | Search? | Write facts? | Report? |
|---|---|---|---|---:|---:|
| `search` | web search ingestion | yes | yes | no |
| `daily` | Planner 日报 / Legacy 文本摄入 | no | yes | no |
| `report` | facts-to-report generation | no | no | yes |
| `facts` | inspect facts | no | no | no |
| `run-day` | shortcut: search + report | yes | yes | yes |
| `launch` | interactive entry | depends | depends | depends |

## Report Generation

`report --type daily-brief` 使用 **规则脚本** (`--no-llm` 默认)，同时查询 facts + signals + brand_status + brand_volume 四表：

- **今日重点**: facts 聚类 top 5
- **待审查信号**: signals 列表 (含原因/来源)
- **品牌动作速览**: facts 按品牌分组
- **事件类型分布**: facts 按 event_type 聚合

## Data Quality

- Every fact has `is_test` (0/1) and `quality_status` (valid/test/invalid)
- `is_test=1` / `quality_status=test|invalid` automatically filtered from reports
- Test/fixture patterns (brand A/B/C/D, title "Test", source "src") auto-tagged at insert
- Legacy data migration on first startup
- DB is production-clean: only real ingestion data, no fixture/test residues

## Known Decisions

- **daily** no longer means brand daily report (→ `report --type brand-daily`)
- **daily** now auto-detects Planner 日报 vs legacy text
- **report** never searches. Empty facts → empty-state report with suggestion
- **run-day** is orchestration only, not a core layer
- `resolve_brand()` is the only brand normalization entrypoint
- Chinese slugs forbidden. All run_modes ASCII only via BRAND_SLUG_MAP
