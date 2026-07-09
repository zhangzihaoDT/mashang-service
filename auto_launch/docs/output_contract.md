# Output Contract — Auto Launch 输出规范

## 目录结构

```
outputs/
├── runs/{YYYYMMDD}/          ← ★ 主运行包（每日核心产物）
│   ├── run_manifest.json     ← 运行元数据
│   ├── facts_audit.json      ← 事实库质量审计
│   ├── source_audit.json     ← 信源覆盖审计（JSON）
│   ├── source_audit.md       ← 信源覆盖审计（Markdown）
│   ├── daily_brief.md        ← 每日简报
│   └── run_summary.md        ← 人类可读运行摘要
│
├── facts/                    ← ★ 持久事实资产
│   └── auto_launch_facts.sqlite
│
├── briefs/                   ← △ 独立简报导出
│   └── {date}.md
│
├── search/{date}/{mode}/     ← ○ 搜索管线调试产物
│   ├── search_intent.json
│   ├── search_task_config.json
│   ├── search_budget_plan.json
│   ├── query_plan.json
│   ├── search_results.raw.json
│   ├── search_results.normalized.json
│   └── search_audit.json
│
├── owned_brand_daily/{date}/ ← ○ 品牌每日监控调试产物
│   └── run_manifest.json
│
└── search_cache/{date}/      ← ○ API 缓存（TTL 24h，可安全删除）
    └── *.raw.json
```

## 分层说明

| 层级 | 符号 | 说明 | 可清理 | 日常关注 |
|------|------|------|--------|----------|
| **主运行包** | ★ | `runs/{date}/` — run-day 直接产出 | ❌ | ✅ 优先查看 |
| **持久资产** | ★ | `facts/` — SQLite 事实库，持续积累 | ❌ | ✅ |
| **独立导出** | △ | `briefs/` — 由 `brief --output` 单独导出 | 条件性 ✅ | ⚠ 与 runs/*/daily_brief.md 重复时 |
| **调试产物** | ○ | `search/`, `owned_brand_daily/` — 搜索/监控中间结果 | ✅ | ❌ 除非排查搜索问题 |
| **缓存** | ○ | `search_cache/` — API 原始响应缓存 | ✅ | ❌ |

## 主运行包规范（★）

每次 `run-day` 至少产出 6 个文件到 `runs/{YYYYMMDD}/`：

| 文件 | 格式 | 生成步骤 | 用途 |
|------|------|----------|------|
| `run_manifest.json` | JSON | Step 5 | 运行元数据：命令、日期、品牌、live/dry-run、各步骤日志 |
| `facts_audit.json` | JSON | Step 3 | 事实库质量审计：字段完成率、信源分布、质量标记 |
| `source_audit.json` | JSON | Step 3.5 | 信源覆盖审计：官方源/垂媒/弱信源占比、期望缺失品牌 |
| `source_audit.md` | Markdown | Step 3.5 | 信源覆盖审计人类可读版 |
| `daily_brief.md` | Markdown | Step 4 | 每日简报：当日关键事件汇总 |
| `run_summary.md` | Markdown | Step 6 | 运行摘要：pipeline 状态、审计摘要、信源覆盖摘要 |

### 完整 run 的判断标准

同时存在以上 6 个文件。

## 日常使用指引

```bash
# 1. 查看当日摘要
cat outputs/runs/{YYYYMMDD}/run_summary.md

# 2. 查看每日简报
cat outputs/runs/{YYYYMMDD}/daily_brief.md

# 3. 查看信源覆盖
cat outputs/runs/{YYYYMMDD}/source_audit.md

# 4. 检查运行状态
python -m auto_launch.cli outputs inspect

# 5. 清理调试/缓存产物（dry-run）
python -m auto_launch.cli outputs clean --older-than 7 --dry-run
```

## 不建议直接查看（除非排查问题）

- `search/` — 搜索管线的中间产物，内容与 runs 冗余
- `owned_brand_daily/` — 品牌监控的原始结果
- `search_cache/` — API 缓存的原始响应
