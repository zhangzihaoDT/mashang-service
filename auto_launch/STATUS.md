# Auto Launch v1.0 — Status

## 定位

汽车上市 / 营销事件事实库服务样板案例，展示如何将 AI 搜索结果与 daily run 信息沉淀为可审计、可复用、可连续运行的事实资产。

## 当前状态

### 输入 / 运行

| 命令 | 用途 |
|------|------|
| `inbox --input` | 从 Markdown 解析结构化事件 |
| `search --to-facts` | 搜索意图转译 → 搜索结果 → 写入 facts |
| `daily --to-facts` | 品牌每日监控 → 搜索结果 → 写入 facts |
| `run-day` | 一键日更：daily → to-facts → audit → source-audit → brief |
| `demo` | 一键演示：replay fixtures → audit → source-audit → brief → timeline → inspect |

### 事实资产

- **存储**：SQLite (`outputs/facts/auto_launch_facts.sqlite`)
- **去重**：fingerprint-based，seen_count 追踪重复出现
- **字段**：brand / model / event_type / event_date / title / source_name / source_url / source_tier / input_channel

### 治理能力

| 能力 | 说明 |
|------|------|
| `facts --audit` | 字段完成率、信源分布、重复率、质量标记 |
| `source-audit` | 信源覆盖审计（official/media/weak）、brand catalog 期望覆盖 |
| `outputs inspect` | outputs 目录完整性检查、duplicate brief 检测、运行包状态 |

### 消费能力

| 能力 | 说明 |
|------|------|
| `brief` | 基于 facts 的每日简报 |
| `timeline` | 品牌/车型事件时间线 |

### 输出规范

| 包 | 路径 | 说明 |
|----|------|------|
| 主运行包 | `outputs/runs/{date}/` | 6 文件：manifest / audit / source-audit(2) / brief / summary |
| 演示包 | `outputs/demo/` | 8 文件：manifest / summary / audit / source-audit(2) / brief / timeline / inspect |
| 调试产物 | `outputs/search/`, `owned_brand_daily/`, `search_cache/` | 可清理的中间产物 |

### 配置

| 文件 | 用途 |
|------|------|
| `configs/event_types.yaml` | 19 类事件类型定义 |
| `configs/source_tiers.yaml` | 5 层信源分级（Tier 1-5） |
| `configs/source_domains.yaml` | 24 品牌官方域名 + 媒体/社交分类 |
| `configs/priority_brand_watchlist.yaml` | 24 重点品牌 + 车型列表 |
| `configs/ls8_competitor_watchlist.yaml` | 10 款竞品车型列表 |
| `configs/volc_search.yaml` | API 参数 + query profiles |

### 测试

```
210 tests passed (pytest auto_launch/tests/ -q)
```

## 不会做的事

- UI / HTML / Streamlit / Dashboard
- impact_score / battle-brief / report 类型
- outputs clean 的真实删除（仅 dry-run）

## 文档

| 文件 | 说明 |
|------|------|
| `docs/output_contract.md` | 输出分层规范 |
| `docs/demo_case.md` | Demo Case 说明（能力矩阵、边界、扩展方向） |
| `docs/operating_loop.md` | 每日运行指南 |
| `README.md` | 项目主文档 |
