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
- **daily**: Planner 日报 → 按章节路由 → 多表写入
- **report**: facts + signals + brand_status + brand_volume → 每日简报

Facts is the shared middle layer. search and daily are independent ingestion paths.

## Inbox Pipeline (daily 摄入层)

仅接受 Planner 日报格式（`##` 章节标题 + Markdown 表格）。4 种章节类型：

| 章节标题模式 | section_type | 路由目标 | 表 |
|-------------|-------------|---------|----|
| 可入库确认事件 / 品牌新事件 / confirmed | `brand_events` | confirmed_fact | `facts` + `evidence` |
| 高优先级弱信号 / 待复核 / review | `review_signals` | review_signal | `signals` |
| 未发现新增动作的品牌 / 品牌状态 | `brand_status` | brand_status | `brand_status` (upsert) |
| 品牌声量观察 / 声量 | `brand_volume` | brand_volume | `brand_volume` |

管线：`parse_contract → validate → route → upsert → audit`

每行事实同时记录 `event_date`（事件发生日）和 `monitor_date`（监测日报撰写日），简报按 `monitor_date` 精确过滤。

## Fact Store 多表架构

| 表 | 用途 | 写入来源 |
|----|------|---------|
| `facts` | 事件主表 (fingerprint 去重, 含 monitor_date) | Planner brand_events |
| `evidence` | 多信源证据 (关联 facts.fact_id) | facts insert 时自动写入 |
| `signals` | 弱信号 / 待审查 (fingerprint 去重, status=open) | Planner review_signals |
| `brand_status` | 品牌状态快照 (按 brand 幂等 upsert) | Planner brand_status |
| `brand_volume` | 品牌声量观测 (含 claim/type/intensity/evidence) | Planner brand_volume |

## CLI Contract

| Command | Role | Search? | Write facts? | Report? |
|---|---|---|---|---:|---:|
| `search` | web search ingestion | yes | yes | no |
| `daily` | Planner 日报摄入 | no | yes | no |
| `report` | facts + signals + status + volume → 简报 | no | no | yes |
| `facts` | inspect facts | no | no | no |
| `run-day` | shortcut: search + report | yes | yes | yes |
| `launch` | interactive entry | depends | depends | depends |

## Report Generation

`report --type daily-brief` 支持两种模式，均按 `monitor_date` 过滤当日事实：

### 规则脚本模式（默认, `--no-llm`）

同时查询 facts + signals + brand_status + brand_volume 四表，输出 4 模块：

- **今日重点**: facts 按 event_date 聚类，取当日 Top 5
- **待审查信号**: signals 列表（含未确认原因和来源）
- **品牌动作速览**: facts 按品牌分组
- **事件类型分布**: facts 按 event_type 聚合

### LLM 模式 (`--pipeline daily`)

跨表整合 facts + signals 为"今日重点"，生成自然语言"待关注"总结。

## Data Quality

- Every fact has `is_test` / `quality_status` / `monitor_date`
- Test/fixture patterns auto-tagged at insert
- DB is production-clean: only Planner 日报 ingestion data

## Known Decisions

- **daily** only accepts Planner 日报格式 (no legacy free text)
- **report** never searches. Empty facts → empty-state report
- **monitor_date** 是简报查询的主过滤维度，event_date 仅作展示
- **run-day** is orchestration only, not a core layer
- Chinese slugs forbidden. All run_modes ASCII only via BRAND_SLUG_MAP
