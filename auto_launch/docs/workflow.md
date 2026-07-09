# Auto Launch Workflow

## 完整执行链路

### 链路 1: 搜索意图转译与执行 (volc_search_daily)

```
user_request (str)
     │
     ▼
┌─────────────────────┐
│ search_intent_      │  search_intent_compiler.py
│ compiler            │  输入: user_request + monitor_date
│                     │  输出: search_intent (JSON)
│                     │  读取: event_types.yaml, source_tiers.yaml,
│                     │        priority_brand_watchlist.yaml,
│                     │        ls8_competitor_watchlist.yaml
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│ search_task_config  │  search_task_config_builder.py
│ builder             │  输入: search_intent
│                     │  输出: search_task_config (JSON)
│                     │  读取: 同上 + source_tiers.yaml
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│ search_budget_      │  search_budget_manager.py
│ manager             │  输入: search_intent + CLI profile
│                     │  输出: budget_plan (JSON)
│                     │  读取: volc_search.yaml
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│ query_plan builder  │  volc_search_query_builder.py
│                     │  输入: task_config + budget_plan
│                     │  输出: query_plan (JSON)
│                     │  读取: volc_search.yaml
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│ Volc Search API     │  volc_search_client.py (+ search_cache.py)
│ (with cache)        │  输入: query_plan
│                     │  输出: raw search_results (JSON)
│                     │  缓存: outputs/search_cache/
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│ normalize + audit   │  normalize_search_results.py
│                     │  输入: raw_results + query_plan
│                     │  输出: normalized (JSON) + audit (JSON)
│                     │  依赖: source_domain_resolver.py
└─────────────────────┘
```

### 链路 2: 自有品牌每日营销监控 (brand_daily_marketing_watch)

```
brand + brand_name + monitor_date + window_hours
     │
     ▼
┌─────────────────────┐
│ Build intent +      │
│ task_config         │  硬编码 intent + task_config
│                     │  含 official_direct 查询
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│ budget_plan +       │  search_budget_manager.py +
│ query_plan          │  volc_search_query_builder.py
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│ Search (with cache) │  VolcSearchClient + search_cache
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│ Normalize + audit   │  normalize_search_results.py
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│ Event cluster       │  event_clusterer.py
│                     │  输入: normalized items
│                     │  输出: clustered events
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│ Candidate gate      │  event_candidate_gate.py
│                     │  输出分桶:
│                     │  - candidates (confirmed)
│                     │  - discovery_signals (weak)
│                     │  - context_only (out of window)
│                     │  - needs_review (unclear)
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│ Markdown report     │  owned_brand_daily_summary.md
└─────────────────────┘
```

## 关键数据结构

### search_intent

```json
{
  "user_request": "看看极氪最近7天都有什么动作",
  "monitor_date": "2026-07-02",
  "mode": "brand_watch",
  "targets": [{"target_id": "zeekr", "brand": "极氪", ...}],
  "time_window": {"start_date": "...", "end_date": "..."},
  "event_scope": {"scope_type": "all_relevant_actions", "event_type_ids": [...]},
  "source_strategy": {"official_first": true, ...},
  "query_budget": {"query_budget_per_target": 8, "result_limit_per_query": 10}
}
```

### normalized item

```json
{
  "title": "...",
  "url": "...",
  "canonical_url": "...",
  "source_name": "...",
  "source_type_guess": "official_website|vertical_auto_media|...",
  "source_tier_guess": "tier_1_official|tier_3_industry_media|...",
  "time_window_status": "in_window|out_of_window|unknown_publish_time",
  "is_out_of_window": false,
  "routing_bucket": null,
  "eligible_for_event_cluster": true
}
```

### candidate_gate output

```json
{
  "candidates": [...],
  "discovery_signals": [...],
  "context_only": [...],
  "needs_review": [...]
}
```

## 关键文件

| 文件 | 定位 | 规模 |
|------|------|------|
| `configs/event_types.yaml` | 事件类型定义 | 19 types |
| `configs/source_tiers.yaml` | 信源分级 | 5 tiers |
| `configs/source_domains.yaml` | 域名映射 | ~60 domains |
| `configs/volc_search.yaml` | API 参数 + query profiles | 134 lines |
| `src/source_domain_resolver.py` | 域名解析器 | 222 lines |
| `src/normalize_search_results.py` | 标准化主逻辑 | 535 lines |
| `src/event_candidate_gate.py` | 候选事件门控 | 166 lines |
| `src/brand_daily_marketing_watch.py` | 自有品牌监控 | 348 lines |

## 当前已知问题

1. **volc_search.yaml 的 cache.root_dir** — search_budget_manager 已硬编码 cache 路径为 `SERVICE_ROOT / "outputs" / "search_cache"`，不再从 YAML 读取
2. **无 48h Launch Report** — 上市 48h 报告生成器尚未实现

## 下一步建议

### P0
- Auto Launch Inbox MVP（已完成：parser / filter / store / runner）
- Fact Store（已完成：SQLite, fingerprint 去重）
- keep/discard filter（已完成）

### P1
- search --to-facts: search 结果直接写入 facts
- facts query 增强: 分页 / 聚合 / 导出

### P2
- daily brief: 基于 facts 生成每日简报
