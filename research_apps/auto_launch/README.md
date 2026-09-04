# Auto Launch

事实驱动的汽车营销事件监控系统。

## 三层架构

```
search ─┐
        ├── facts ─── report
daily ──┘
```

- **search**: 联网搜索 → 归一化 → facts
- **daily**: Planner 日报 → 按章节路由 → facts + signals + brand_status + brand_volume
- **report**: facts + signals + brand_status + brand_volume → 每日简报

facts 是共享中间层，search 和 daily 为独立摄入路径。

## 快速开始

```bash
# daily — 导入 Planner 日报
PYTHONPATH=research_apps python3 -m auto_launch.cli daily --input planner_report.md --date 2026-07-26

# report — 生成每日简报 (规则脚本)
PYTHONPATH=research_apps python3 -m auto_launch.cli report --type daily-brief --date 2026-07-26 --days 1 --no-llm

# report — 生成每日简报 (LLM)
PYTHONPATH=research_apps python3 -m auto_launch.cli report --type daily-brief --date 2026-07-26 --days 1 --pipeline daily

# search — 搜索并写入 facts
PYTHONPATH=research_apps python3 -m auto_launch.cli search --request "看看极氪最近 7 天都有什么动作" --live --to-facts

# 交互式入口
PYTHONPATH=research_apps python3 -m auto_launch.cli launch
```

## CLI 命令

| 命令 | 层级 | 职责 | 搜索 | 写入 | 报告 |
|------|------|------|:---:|:----:|:----:|
| `search` | 发现层 | 联网搜索 → 归一化 → facts | ✅ | ✅ | ❌ |
| `daily` | 摄入层 | Planner 日报 → 多表写入 | ❌ | ✅ | ❌ |
| `report` | 报告层 | 四表查询 → 每日简报 | ❌ | ❌ | ✅ |
| `facts` | 辅助 | 查看 facts 库 | ❌ | ❌ | ❌ |
| `launch` | 交互 | 交互式入口 | 可选 | 可选 | 可选 |

## 管线

```
Planner Markdown 日报
  ↓
parse_contract() → 识别 4 类章节 → 解析表格行
  ↓
route() → 按 section_type 路由到目标数据类型
  ↓
upsert() → facts / evidence / signals / brand_status / brand_volume
  ↓
audit_coverage()
```

简报查询时按 `monitor_date`（监测日期）精确过滤，不跨天混入。

章节 → 目标表映射：

| ## 标题模式 | section_type | 目标表 |
|------------|-------------|-------|
| 可入库确认事件 / confirmed | `brand_events` | `facts` + `evidence` |
| 高优先级弱信号 / 待复核 / review | `review_signals` | `signals` |
| 未发现新增动作的品牌 / 品牌状态 | `brand_status` | `brand_status` |
| 品牌声量观察 / 声量 | `brand_volume` | `brand_volume` |

## Report 系统

`report --type daily-brief` 支持两种模式，均按 `monitor_date` 过滤：

| 模式 | 命令 | 输出模块 |
|------|------|---------|
| 规则脚本 | `--no-llm` (默认) | 今日重点 / 待审查信号 / 品牌动作速览 / 事件类型分布 |
| LLM | `--pipeline daily` | 跨表整合为"今日重点"+"待关注" |

## Fact Store

| 表 | 说明 |
|----|------|
| `facts` | 事件主表 (fingerprint 去重, 含 monitor_date) |
| `evidence` | 多信源证据 (关联 facts.fact_id) |
| `signals` | 弱信号 (status=open) |
| `brand_status` | 品牌状态 (按 brand upsert) |
| `brand_volume` | 品牌声量观测 |

## 输出结构

```
outputs/runs/{YYYYMMDD}/
├── daily_brief.md              ← LLM 版
└── daily_brief_no_llm.md       ← 规则脚本版
```

详见 `docs/daily_report_pipeline.md`。
