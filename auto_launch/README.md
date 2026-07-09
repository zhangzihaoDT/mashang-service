# Auto Launch Service

## 项目定位

auto_launch 是一个独立的汽车上市 / 营销事件监测服务。它不属于 mashang_workspace 的分析脚本集，而是作为 mashang-service 下的一个独立子项目存在。

## 业务问题

- **LS8 竞品车型**每天有什么销售动作（上市、交付、权益、价格变动）？
- **24 个重点新能源品牌**每天有什么营销事件（发布会、传播、活动）？
- 哪些是**已确认事件**，哪些是**弱信号**，哪些需要人工复核？
- 信息来自什么信源，可信度如何？

## 核心链路

```
Inbox/Search → Normalize → Filter → Facts → Query/Audit
```

| 阶段 | 模块 | 产出 |
|------|------|------|
| **Inbox** | `inbox_parser.py`, `inbox_runner.py` | ChatGPT daily run → raw items |
| **Search** | `search_intent_compiler.py`, `volc_search_*.py` | 搜索意图 → 查询计划 → 搜索结果 |
| **Normalize** | `normalize_search_results.py`, `source_domain_resolver.py` | URL 去重 → 信源分类 → 时间窗口校验 |
| **Filter** | `inbox_filter.py` | keep/discard 二分类 |
| **Facts** | `fact_store.py` | SQLite 事实库（fingerprint 去重） |
| **Query** | `cli.py facts` | 查询、审计、统计、导出 |
| **Intelligence** | `event_clusterer.py`, `event_candidate_gate.py`, `brand_daily_marketing_watch.py` | 事件聚类、候选门控、品牌监控 |
| **Cache** | `search_cache.py` | API 请求缓存（TTL 24h） |

## 目录结构

```
auto_launch/
├── README.md                   本文件
├── cli.py                      CLI 入口
├── __init__.py
├── configs/                    配置文件
│   ├── event_types.yaml        19 类事件类型定义
│   ├── source_tiers.yaml       5 层信源分级
│   ├── source_domains.yaml     域名/信源分类映射
│   ├── volc_search.yaml        API 参数 + query profiles
│   ├── ls8_competitor_watchlist.csv
│   ├── ls8_competitor_watchlist.yaml
│   └── priority_brand_watchlist.yaml
├── src/                        Python 源码（3 层分层）
│   │
│   │   Inbox Core:
│   ├── inbox_parser.py          raw 输入 → raw items
│   ├── inbox_filter.py          keep/discard 二分类
│   ├── fact_store.py            SQLite 事实库
│   ├── inbox_runner.py          管线编排 + 交互模式
│   │
│   │   Search Pipeline:
│   ├── search_intent_compiler.py
│   ├── search_task_config_builder.py
│   ├── search_budget_manager.py
│   ├── volc_search_query_builder.py
│   ├── volc_search_client.py
│   ├── volc_search_daily.py
│   ├── search_cache.py
│   ├── normalize_search_results.py
│   │
│   │   Intelligence Utilities:
│   ├── source_domain_resolver.py
│   ├── event_clusterer.py
│   ├── event_candidate_gate.py
│   └── brand_daily_marketing_watch.py
├── docs/
│   ├── workflow.md             执行链路文档
│   └── inbox.md                Inbox MVP 文档
├── outputs/                    运行时输出
└── tests/                      测试
    ├── test_auto_launch_search_cache.py
    ├── test_auto_launch_source_domain_resolver.py
    ├── test_auto_launch_search_intent_compiler.py
    ├── test_auto_launch_search_task_config_builder.py
    ├── test_auto_launch_search_budget_manager.py
    ├── test_auto_launch_volc_search_query_builder.py
    ├── test_auto_launch_volc_search_daily.py
    ├── test_auto_launch_normalize_search_results.py
    ├── test_auto_launch_candidate_gate.py
    ├── test_auto_launch_time_window_compiler.py
    ├── test_brand_daily_marketing_watch.py
    │
    │   Inbox Core Tests:
    ├── test_inbox_parser.py
    ├── test_inbox_filter.py
    ├── test_fact_store.py
    ├── test_inbox_runner.py
    └── test_cli_inbox.py
```

## 如何运行

所有命令通过统一 CLI 入口 `python -m auto_launch.cli` 执行。

### Daily Monitor

```bash
python -m auto_launch.cli daily --brand im --brand-name 智己
python -m auto_launch.cli daily --brand im --brand-name 智己 --live
python -m auto_launch.cli daily --brand im --brand-name 智己 --window-hours 48
python -m auto_launch.cli daily --brand im --brand-name 智己 --live --to-facts
```

### 搜索意图转译

```bash
python -m auto_launch.cli search --request "看看极氪最近 7 天都有什么动作"
python -m auto_launch.cli search --request "看看极氪最近 7 天都有什么动作" --live
python -m auto_launch.cli search --request "看看极氪最近 7 天都有什么动作" --live --to-facts
```

### 标准化搜索结果

```bash
python -m auto_launch.cli normalize --raw <path> --query-plan <path>
```

### Inbox Intake

```bash
python -m auto_launch.cli inbox --input daily_run.md --date 2026-07-09
python -m auto_launch.cli inbox     # 交互模式
```

### 查询事实库

```bash
python -m auto_launch.cli facts                           # 最近 7 天
python -m auto_launch.cli facts --brand 智己               # 按品牌
python -m auto_launch.cli facts --model LS6               # 按车型
python -m auto_launch.cli facts --event-type 权益调整       # 按事件类型
python -m auto_launch.cli facts --source-tier tier_1_official  # 按信源等级
python -m auto_launch.cli facts --days 14                 # 最近 14 天
python -m auto_launch.cli facts --since 2026-07-01 --until 2026-07-09
python -m auto_launch.cli facts --stats                   # 统计概览
python -m auto_launch.cli facts --stats-by brand          # 按字段统计
python -m auto_launch.cli facts --audit                   # 质量审计
python -m auto_launch.cli facts --export                  # JSON 导出
```

### 一键日更

```bash
python -m auto_launch.cli run-day                          # dry-run
python -m auto_launch.cli run-day --live                   # 真实执行
python -m auto_launch.cli run-day --date 2026-07-09 --brief-output brief.md
```

run-day 执行：daily → to-facts → audit → source-audit → brief，输出到 `outputs/runs/{date}/`。

输出文件：
- `run_manifest.json` — 运行元数据（含 `source_audit_summary`）
- `facts_audit.json` — 质量审计
- `source_audit.json` — 信源覆盖审计 JSON
- `source_audit.md` — 信源覆盖审计 Markdown
- `daily_brief.md` — 每日简报
- `run_summary.md` — 人类可读摘要（含信源覆盖小节）

### 信源覆盖审计

```bash
python -m auto_launch.cli source-audit                           # 默认 7 天，priority watchlist
python -m auto_launch.cli source-audit --watchlist priority       # 24 重点品牌覆盖审计
python -m auto_launch.cli source-audit --watchlist ls8            # LS8 竞品车型覆盖审计
python -m auto_launch.cli source-audit --days 14                  # 最近 14 天
python -m auto_launch.cli source-audit --format json              # JSON 输出
python -m auto_launch.cli source-audit --output sa.md             # 写入文件
```

source-audit 复用现有 configs，**不新增** `source_coverage_expectations.yaml`：
- 品牌期望列表来自 `priority_brand_watchlist.yaml`
- LS8 竞品列表来自 `ls8_competitor_watchlist.yaml`
- 信源分级来自 `source_tiers.yaml`
- 官方域名来自 `source_domains.yaml`

### 连续回放

```bash
python -m auto_launch.cli replay --start-date 2026-07-07 --end-date 2026-07-09
python -m auto_launch.cli replay --input-dir tests/fixtures/daily_runs
python -m auto_launch.cli replay --input-dir tests/fixtures/daily_runs --reset-store
```

### 事件时间线

```bash
python -m auto_launch.cli timeline --days 30                               # 全部
python -m auto_launch.cli timeline --brand 智己 --days 30                   # 按品牌
python -m auto_launch.cli timeline --model LS6 --event-type 权益调整 --days 14
python -m auto_launch.cli timeline --output tl.md                          # 写入文件
```

## 主要配置说明

| 文件 | 用途 |
|------|------|
| `configs/volc_search.yaml` | Volc Search API 参数、query profiles、缓存策略 |
| `configs/event_types.yaml` | 19 类事件类型定义 |
| `configs/source_tiers.yaml` | 5 层信源分级 |
| `configs/source_domains.yaml` | 域名 → 信源分类映射 |
| `configs/priority_brand_watchlist.yaml` | 24 个重点品牌列表 |
| `configs/ls8_competitor_watchlist.yaml` | 10 款竞品车型列表 |

## 输出文件说明

```
outputs/
├── search/{date}/{mode}/     搜索管线输出
│   ├── search_intent.json
│   ├── search_task_config.json
│   ├── search_budget_plan.json
│   ├── query_plan.json
│   ├── search_results.raw.json
│   ├── search_results.normalized.json
│   └── search_audit.json
├── owned_brand_daily/{date}/  品牌每日监控输出
├── runs/{date}/               run-day 输出（manifest / audit / source-audit / brief / summary）
│   ├── run_manifest.json
│   ├── facts_audit.json
│   ├── source_audit.json
│   ├── source_audit.md
│   ├── daily_brief.md
│   ├── run_summary.md
│   ├── raw_search_results.json
│   ├── normalized_search_results.json
│   ├── event_clusters.json
│   ├── brand_event_candidates.json
│   ├── brand_discovery_signals.json
│   ├── owned_brand_daily_summary.md
│   └── search_audit.json
└── search_cache/{date}/       API 缓存
```

## Roadmap

| 版本 | 方向 | 状态 |
|------|------|------|
| v0.5 | Fact Quality Loop | ✓ facts audit / stats / export / to-facts |
| v0.6 | Daily Brief from Facts | ✓ brief / brief_rank / badge |
| v0.7 | Operating Loop & Timeline | ✓ run-day / replay / timeline |
| v0.8 | Source Coverage Audit | ✓ 复用现有 configs，不新增 source_coverage_expectations.yaml |
| v0.9 | Impact / Battle Field | |
| v1.0 | Demo Case | |
