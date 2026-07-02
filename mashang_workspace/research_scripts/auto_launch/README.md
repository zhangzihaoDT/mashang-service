# Auto Launch — 搜索意图转译与执行

## 定位

将用户自然语言需求精准转译为可执行的 Volc Search 搜索任务，并完成搜索结果采集、标准化和审计。

## 完整链路

```
user_request
  → search_intent_compiler         user_request → search_intent
  → search_task_config_builder     search_intent → search_task_config
  → volc_search_query_builder      search_task_config → query_plan
  → volc_search_client             query_plan → raw search results
  → normalize_search_results       raw results → normalized + audit
```

## dry-run vs live-run

### dry-run（默认）

仅完成意图转译链路，不调用外部 API。无需环境变量。

```bash
python mashang_workspace/research_scripts/auto_launch/volc_search_daily.py \
  --request "看看极氪最近 7 天都有什么动作" \
  --date 2026-07-02
```

输出 3 个文件：

```
outputs/auto_launch/search/{date}/{mode}/
├── search_intent.json
├── search_task_config.json
└── query_plan.json
```

### live-run

完整执行搜索到审计链路。需要配置环境变量。

```bash
export VOLC_SEARCH_BASE_URL="https://your-instance.volcengine.com"
export VOLC_SEARCH_API_KEY="your-api-key"

python mashang_workspace/research_scripts/auto_launch/volc_search_daily.py \
  --request "看看极氪最近 7 天都有什么动作" \
  --date 2026-07-02 \
  --live
```

输出 6 个文件：

```
outputs/auto_launch/search/{date}/{mode}/
├── search_intent.json             用户需求 → 结构化意图
├── search_task_config.json        意图 → 可执行任务配置（含 enriched aliases + tier 策略）
├── query_plan.json                任务 → 搜索查询计划（多条 query，各带 event_type + source_tier）
├── search_results.raw.json        原始搜索结果（含顶层 envelope + 单条结果 + errors）
├── search_results.normalized.json 标准化搜索结果（每项含 source_tier_guess）
└── search_audit.json              搜索质量审计（覆盖率、失败统计、信源分布）
```

## 环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `VOLC_SEARCH_BASE_URL` | live-run 必填 | Volc Search API 地址 |
| `VOLC_SEARCH_API_KEY` | live-run 必填 | API Key（不会写入任何输出文件） |

dry-run 不需要环境变量。

## 输出文件规范

### search_results.raw.json

```json
{
  "task_name": "auto_launch_volc_search",
  "mode": "brand_watch",
  "monitor_date": "2026-07-02",
  "user_request": "看看极氪最近 7 天都有什么动作",
  "query_count": 8,
  "results": [
    {
      "query": "...",
      "target_id": "zeekr",
      "status": "success",
      "result_count": 10,
      "results": [...],
      "meta": { ... }
    }
  ],
  "errors": []
}
```

单条 query 失败不中断整体任务，记录到 errors 和 failed_queries。

### search_results.normalized.json

```json
{
  "items": [
    {
      "query": "...",
      "target_id": "zeekr",
      "mode": "brand_watch",
      "title": "...",
      "url": "...",
      "snippet": "...",
      "source_name": "...",
      "source_type_guess": "vertical_auto_media",
      "source_tier_guess": "tier_2_authoritative_media",
      "publish_time": "...",
      "retrieved_at": "...",
      "raw_rank": 1
    }
  ]
}
```

注意：normalize 层不做事件判断，不生成 event_candidates。source_tier_guess 仅为搜索层启发式猜测。

## search_layer 与 event_layer 的边界

| 层 | 负责 | 不负责 |
|---|---|---|
| **search_layer**（本轮） | 意图转译、query 生成、API 调用、结果标准化、搜索审计 | 事件判断、event_candidates 生成、日报渲染 |
| **event_layer**（下一步） | LLM 事件真实性判断、event_candidates 生成、discovery_signals 提取 | 搜索、标准化 |

search_layer 的输出（normalized.json）可直接作为 event_layer 的输入。

## 测试

```bash
pytest mashang_workspace/tests/research_scripts/test_auto_launch_search_intent_compiler.py -q
pytest mashang_workspace/tests/research_scripts/test_auto_launch_search_task_config_builder.py -q
pytest mashang_workspace/tests/research_scripts/test_auto_launch_volc_search_query_builder.py -q
pytest mashang_workspace/tests/research_scripts/test_auto_launch_volc_search_daily.py -q
```

mock 测试覆盖：
- dry-run 只生成前 3 个文件
- live-run (mock) 生成全部 6 个文件
- 单条 query 失败不中断整体任务
- raw.json envelope 结构验证
- normalized.json 字段完整性
- search_audit 字段完整性 + failed_queries 统计

## 下一步进入 LLM event extraction

1. `normalize_search_results.py` 的输出（`items[...]`）作为 LLM 输入
2. 新增 `llm_event_extractor.py`，接收 `{items: [...], search_intent}` 输出 `event_candidates`
3. 事件判断规则参考 `event_types.yaml` 的 `confirmation_level`
4. `source_tier_guess` 作为 LLM evidence 权重参考

## 配置

| 文件 | 作用 |
|---|---|
| `configs/priority_brand_watchlist.yaml` | 24 个品牌级监控对象 |
| `configs/ls8_competitor_watchlist.yaml` | 10 款 LS8 竞品车型 |
| `configs/event_types.yaml` | 19 类事件类型 |
| `configs/source_tiers.yaml` | 5 层信源分级 |
| `configs/volc_search.yaml` | Volc Search API 配置 + 搜索模板 |
