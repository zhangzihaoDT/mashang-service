# Auto Launch

事实驱动的汽车营销事件监控系统。

## 三层架构

```
search ─┐
        ├── facts ─── report
daily ──┘
```

- **search**: 联网搜索 → 归一化 → facts
- **daily**: ChatGPT Daily Run 文本 → 抽取 → facts
- **report**: facts 只读 → 品牌日报 / 搜索简报 / 每日简报

facts 是共享中间层，search 和 daily 为独立摄入路径。

## 快速开始

```bash
# search — 搜索并写入 facts
python3 -m auto_launch.cli search --request "看看极氪最近 7 天都有什么动作" --live --to-facts

# daily — 处理 ChatGPT Daily Run 并写入 facts
python3 -m auto_launch.cli daily --input chatgpt_daily.md
python3 -m auto_launch.cli daily --text "...内容..." --then-report daily-brief

# report — 从 facts 生成简报（默认 LLM，降级规则脚本）
python3 -m auto_launch.cli report --type daily-brief --pipeline search
python3 -m auto_launch.cli report --type daily-brief --pipeline daily
python3 -m auto_launch.cli report --type daily-brief --no-llm           # 强制规则脚本
python3 -m auto_launch.cli report --type brand-daily --brand 智己

# run-day — shortcut: search + report
python3 -m auto_launch.cli run-day --brand 智己

# 交互式入口
python3 -m auto_launch.cli launch
```

## CLI 命令

| 命令 | 层级 | 职责 | 搜索 | 写 facts | 报告 |
|------|------|------|:---:|:--------:|:----:|
| `search` | 发现层 | 联网搜索 → 归一化 → facts | ✅ | ✅（--to-facts） | ❌ |
| `daily` | 摄入层 | ChatGPT Daily Run → facts | ❌ | ✅ | ❌ |
| `report` | 报告层 | facts → 品牌日报/搜索简报/每日简报 | ❌ | ❌ | ✅ |
| `facts` | 辅助 | 查看 facts 库 | ❌ | ❌ | ❌ |
| `run-day` | 编排 | shortcut: search + report | ✅ | ✅ | ✅ |

## Report 系统

`report --type daily-brief` 默认使用 **LLM（DeepSeek）** 生成简报：

- **LLM 模式**：事件智能合并、分析判断、结构化 5 段式（今日重点/品牌速览/事件类型/今日观察/信源质量）
- **规则脚本**：`--no-llm` 降级到机械分组聚类的旧模式
- **pipeline 感知**：`--pipeline search` → "搜索简报"，`--pipeline daily` → "每日简报"

## 数据质量

- 每条 fact 标记 `is_test` / `quality_status`，测试数据自动过滤
- `--pipeline` 参数可按来源（search/daily）筛选
- Facts 库仅含生产数据，无 fixture/test 残留

## 输出结构

```
outputs/runs/{YYYYMMDD}/
├── launcher_daily_run/       ← daily 摄入简报
│   └── reports/daily_brief.md
├── brand_watch_{slug}/       ← search 搜索简报 + 原始证据
│   ├── search/{plan,raw,normalized,audit}.json
│   └── reports/daily_brief.md
└── brand_daily_{slug}/       ← report --type brand-daily
    └── reports/brand_daily_summary.md
```

详见 `docs/output_contract.md`。
