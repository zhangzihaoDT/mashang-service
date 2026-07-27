# Auto Launch

事实驱动的汽车营销事件监控系统。

## 三层架构

```
search ─┐
        ├── facts ─── report
daily ──┘
```

- **search**: 联网搜索 → 归一化 → facts
- **daily**: Planner 日报 / ChatGPT Daily Run → 按章节路由 → facts + signals + brand_status + brand_volume
- **report**: facts 只读 → 品牌日报 / 每日简报 (含信号+状态+声量)

facts 是共享中间层，search 和 daily 为独立摄入路径。

## 快速开始

```bash
# daily — 导入 Planner 日报 (推荐, 自动路由到 4 张表)
python3 -m auto_launch.cli daily --input planner_daily_report.md --date 2026-07-26

# daily — 导入 ChatGPT Daily Run 文本 (legacy 向后兼容)
python3 -m auto_launch.cli daily --input chatgpt_daily.md

# report — 从 facts 生成每日简报 (含信号/状态/声量)
python3 -m auto_launch.cli report --type daily-brief --date 2026-07-26 --days 1 --no-llm

# search — 搜索并写入 facts
python3 -m auto_launch.cli search --request "看看极氪最近 7 天都有什么动作" --live --to-facts

# run-day — shortcut: search + report
python3 -m auto_launch.cli run-day --brand 智己

# 交互式入口
python3 -m auto_launch.cli launch
```

## CLI 命令

| 命令 | 层级 | 职责 | 搜索 | 写入 | 报告 |
|------|------|------|:---:|:----:|:----:|
| `search` | 发现层 | 联网搜索 → 归一化 → facts | ✅ | ✅（--to-facts） | ❌ |
| `daily` | 摄入层 | Planner 日报 / ChatGPT Daily Run → 多表写入 | ❌ | ✅ | ❌ |
| `report` | 报告层 | facts + signals + status + volume → 简报 | ❌ | ❌ | ✅ |
| `facts` | 辅助 | 查看 facts 库及审计 | ❌ | ❌ | ❌ |
| `run-day` | 编排 | shortcut: search + report | ✅ | ✅ | ✅ |

## Inbox 管线

```
输入文本 ─→ parse_contract() 检测源类型
                │
         ┌──────┴──────┐
         ▼              ▼
   Planner 日报     Legacy 文本
         │              │
   按章节路由       keep/discard
    ┌──┼──┬──┐          │
    ▼  ▼  ▼  ▼          ▼
  facts signals status volume
```

自动识别章节:

| ## 标题模式 | section_type | 目标表 |
|------------|-------------|-------|
| 可入库确认事件 / confirmed | `brand_events` | `facts` + `evidence` |
| 高优先级弱信号 / 待复核 / review | `review_signals` | `signals` |
| 未发现新增动作的品牌 / 品牌状态 | `brand_status` | `brand_status` |
| 品牌声量观察 / 声量 | `brand_volume` | `brand_volume` |

## Report 系统

`report --type daily-brief` 同时查询 facts + signals + brand_status + brand_volume 四表，输出 4 模块简报：

- **今日重点**: facts 聚类 top 5
- **待审查信号**: 弱信号列表 (含未确认原因)
- **品牌动作速览**: facts 按品牌分组
- **事件类型分布**: facts 按 event_type 聚合

## Fact Store 多表架构

| 表 | 行数查询 | 说明 |
|----|---------|------|
| `facts` | `store.query()` | 事件主表 (fingerprint 去重, 含 quality_status) |
| `evidence` | `store.get_evidence(fact_id)` | 多信源证据 |
| `signals` | `store.get_signals()` | 弱信号 (status=open) |
| `brand_status` | `store.get_brand_status()` | 品牌状态 (按 brand upsert) |
| `brand_volume` | `store.get_brand_volume()` | 声量观测 |

## 数据质量

- 每条 fact 标记 `is_test` / `quality_status`，测试数据自动过滤
- `--pipeline` 参数可按来源（search/daily）筛选
- Facts 库仅含生产数据，无 fixture/test 残留

## 输出结构

```
outputs/runs/{YYYYMMDD}/
├── launcher_daily_run/       ← daily 摄入简报
│   └── reports/daily_brief.md
├── brand_watch_{slug}/       ← search 原始证据
│   ├── search/{plan,raw,normalized,audit}.json
│   └── reports/daily_brief.md
└── brand_daily_{slug}/       ← report --type brand-daily
    └── reports/brand_daily_summary.md
```

详见 `docs/output_contract.md`。
