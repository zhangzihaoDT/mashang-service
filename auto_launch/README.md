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
Watchlist → Search → Normalize → Gate → Score → Report → Memory
```

| 阶段 | 模块 | 产出 |
|------|------|------|
| **Watchlist** | `configs/priority_brand_watchlist.yaml`, `configs/ls8_competitor_watchlist.yaml` | 品牌/车型目标列表 |
| **Search** | `src/search_intent_compiler.py`, `src/volc_search_query_builder.py`, `src/volc_search_client.py` | 搜索意图 → 查询计划 → 搜索结果 |
| **Normalize** | `src/normalize_search_results.py`, `src/source_domain_resolver.py` | URL 去重 → 信源分类 → 时间窗口校验 |
| **Cluster** | `src/event_clusterer.py` | 将搜索结果聚类为事件候选 |
| **Gate** | `src/event_candidate_gate.py` | 确定性规则分桶：candidate / discovery_signal / context_only / needs_review |
| **Report** | `src/brand_daily_marketing_watch.py` | Markdown 简报 |
| **Cache** | `src/search_cache.py` | API 请求缓存（TTL 24h） |

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
├── src/                        Python 源码
│   ├── __init__.py
│   ├── search_intent_compiler.py
│   ├── search_task_config_builder.py
│   ├── search_budget_manager.py
│   ├── volc_search_query_builder.py
│   ├── volc_search_client.py
│   ├── volc_search_daily.py
│   ├── normalize_search_results.py
│   ├── search_cache.py
│   ├── source_domain_resolver.py
│   ├── event_clusterer.py
│   ├── event_candidate_gate.py
│   └── brand_daily_marketing_watch.py
├── prompts/                    Prompt 模板（归档）
├── runbooks/                   分析工作手册
├── docs/
│   └── workflow.md            执行链路文档
├── reports/
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
    └── ...（promptbuilder 历史测试）
```

## 如何运行

### Daily Monitor

```bash
# 自有品牌每日营销监控 dry-run
python -m services.auto_launch.cli daily --brand im --brand-name 智己

# 自有品牌每日营销监控（执行搜索）
python -m services.auto_launch.cli daily --brand im --brand-name 智己 --live

# 指定时间窗口
python -m services.auto_launch.cli daily --brand im --brand-name 智己 --window-hours 48
```

### 标准化搜索结果

```bash
python -m services.auto_launch.cli normalize --raw <path> --query-plan <path>
```

### 搜索意图转译

```bash
python -m services.auto_launch.cli search --request "看看极氪最近 7 天都有什么动作"
python -m services.auto_launch.cli search --request "看看极氪最近 7 天都有什么动作" --live
```

### 直接运行脚本

```bash
python services/auto_launch/src/volc_search_daily.py --request "看看极氪最近 7 天都有什么动作"
python services/auto_launch/src/brand_daily_marketing_watch.py --brand im --brand-name 智己
python services/auto_launch/src/normalize_search_results.py --raw <path> --query-plan <path>
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
│   ├── run_manifest.json
│   ├── raw_search_results.json
│   ├── normalized_search_results.json
│   ├── event_clusters.json
│   ├── brand_event_candidates.json
│   ├── brand_discovery_signals.json
│   ├── owned_brand_daily_summary.md
│   └── search_audit.json
└── search_cache/{date}/       API 缓存
```

## 后续 Roadmap

- **Source Coverage Audit**: 检查每个品牌/车型的信源覆盖情况
- **Event Promotion**: 从 discovery_signal → candidate → confirmed 的推进机制
- **impact_score**: 事件影响评分
- **Vehicle Memory**: 基于时间序列的车型事件记忆
- **Golden Case Report**: 优秀 case 沉淀
- **48h Launch Report**: 上市 48h 报告生成器
- **Render Pipeline**: Markdown/HTML report renderer
