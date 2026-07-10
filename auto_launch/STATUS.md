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
- **daily**: ChatGPT Daily Run → extracted events → facts store
- **report**: facts store → target report (brand-daily, daily-brief)

Facts is the shared middle layer. search and daily are independent ingestion paths.

## CLI Contract

| Command | Role | Search? | Write facts? | Report? |
|---|---|---|---:|---:|
| `search` | web search ingestion | yes | yes | no |
| `daily` | ChatGPT Daily Run ingestion | no | yes | no |
| `report` | facts-to-report generation | no | no | yes |
| `facts` | inspect facts | no | no | no |
| `run-day` | shortcut: search + report | yes | yes | yes |
| `launch` | interactive entry | depends | depends | depends |

## Report Generation

`report --type daily-brief` uses **LLM by default** (DeepSeek):

- LLM generates structured 5-section brief: 今日重点 → 品牌动作速览 → 事件类型分布 → 今日观察 → 信源质量
- LLM merges similar events (e.g. 3 条交付数据 → 1 条 "交付数据亮眼" + 具体增长率)
- LLM provides analytical judgment (今日观察), not template filling
- Falls back to rule-based script if LLM unavailable (`--no-llm` to force rule-based)

Pipeline context:
- `--pipeline search` → 标题 "搜索简报（基于公开搜索发现）"，措辞反映数据来源
- `--pipeline daily` → 标题 "每日简报（基于 facts 库收录的事件）"

## Data Quality

- Every fact has `is_test` (0/1) and `quality_status` (valid/test/invalid)
- `is_test=1` / `quality_status=test|invalid` automatically filtered from reports
- Test/fixture patterns (brand A/B/C/D, title "Test", source "src") auto-tagged at insert
- Legacy data migration on first startup
- DB is production-clean: only real ingestion data, no fixture/test residues

## Known Decisions

- **daily** no longer means brand daily report (→ `report --type brand-daily`)
- **report** never searches. Empty facts → empty-state report with suggestion
- **run-day** is orchestration only, not a core layer
- `resolve_brand()` is the only brand normalization entrypoint
- Chinese slugs forbidden. All run_modes ASCII only via BRAND_SLUG_MAP
