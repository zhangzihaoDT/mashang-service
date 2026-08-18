# Mashang Workspace Skills Catalog

Agent Harness 能力目录

生成日期：2026-08-18

本页面展示 mashang_workspace 中可被 OpenCode Agent 调用的 workspace 级 skills。

---

## 概览

| 指标 | 数值 |
|------|------|
| Workspace Skills | 4 |
| Skills 输出目录 | mashang_workspace/outputs/monthly_market_report/YYYY-MM/, mashang_workspace/outputs/reports/, dataset/cpca_weekly/cpca_weekly_data_capture.json   # evidence/capture 原材料 |
| 最近更新 | 2026-08-18 |

## Skills Overview

| Skill | 类型 | 能力定位 | 入口文件 | 默认输出 |
|-------|------|---------|---------|---------|
| branded-html-report | workspace | 将汽车经营分析、预测模型、回测评估、市场洞察等结果，渲染为具有 Raccoon  | `python runtime_scripts/daily_lock_count.py --format json \` | ['mashang_workspace/outputs/reports/'] |
| cpca-weekly-data-capture | workspace | 第一时间捕捉乘联分会/乘联会周度核心数据，比 CADA 官网更早获取 P0 早源 | `make cpca-weekly-data-capture WEEK=2026-W25` | ['dataset/cpca_weekly/cpca_weekly_data_capture.json   # evidence/capture 原材料'] |
| monthly-market-report | workspace | monthly-market-report v0.1 是基于 `TP&MIX-w | `OpenCode Agent 自动匹配 — SKILL.md 位于 .opencode/skills/monthly-market-report/` | ['mashang_workspace/outputs/monthly_market_report/YYYY-MM/'] |
| runtime-eval-diagnosis | workspace |  | `OpenCode Agent 自动匹配 — SKILL.md 位于 .opencode/skills/runtime-eval-diagnosis/` | — |

## Workspace Skills 详情

### branded-html-report

| 字段 | 内容 |
|------|------|
| 目录 | `.opencode/skills/branded_html_report/` |
| 层级 | workspace |
| 能力定位 | 将汽车经营分析、预测模型、回测评估、市场洞察等结果，渲染为具有 Raccoon Research / mashang 风格的 HTML 数据报告。 |
| 适用场景 | 销量预测报告、锁单释放曲线报告、模型回测报告、汽车市场洞察报告、经营复盘报告、用户反馈 / VOC 分析报告 |
| 不适用场景 | 政府正式申报书、通知/公文风材料、Word / PDF 正式材料、简历 |
| 入口命令 | `python runtime_scripts/daily_lock_count.py --format json \` |
| 默认输出 | ['mashang_workspace/outputs/reports/'] |

### cpca-weekly-data-capture

| 字段 | 内容 |
|------|------|
| 目录 | `.opencode/skills/cpca-weekly-data-capture/` |
| 层级 | workspace |
| 能力定位 | 第一时间捕捉乘联分会/乘联会周度核心数据，比 CADA 官网更早获取 P0 早源。 |
| 适用场景 | 每周三下午监控 2026-W26 等数据周的核心指标、需要比 CADA 官网更早获取乘用车零售/新能源零售/渗透率、需要结构化 JSON + 可发布文本的 fact_result、需要追踪 first_signal 与 CADA final confirmation 的时间差 |
| 不适用场景 | 逐日高频监控（不是日内 tick 级工具）、个股/单一车型分析、非乘联分会发布的其他数据源 |
| 入口命令 | `make cpca-weekly-data-capture WEEK=2026-W25` |
| 默认输出 | ['dataset/cpca_weekly/cpca_weekly_data_capture.json   # evidence/capture 原材料'] |

### monthly-market-report

| 字段 | 内容 |
|------|------|
| 目录 | `.opencode/skills/monthly-market-report/` |
| 层级 | workspace |
| 能力定位 | monthly-market-report v0.1 是基于 `TP&MIX-ways` 现有 6 张预聚合单表的月度汽车市场固定主查询能力。 |
| 适用场景 | — |
| 不适用场景 | city×brand 城市内品牌排名、city×model 城市内车型排名、city×price_band×brand 城市×价位段×品牌交叉分析、brand×city_tier 品牌×城市线级交叉分析 |
| 入口命令 | `OpenCode Agent 自动匹配 — SKILL.md 位于 .opencode/skills/monthly-market-report/` |
| 默认输出 | ['mashang_workspace/outputs/monthly_market_report/YYYY-MM/'] |

### runtime-eval-diagnosis

| 字段 | 内容 |
|------|------|
| 目录 | `.opencode/skills/runtime-eval-diagnosis/` |
| 层级 | workspace |
| 能力定位 |  |
| 适用场景 | — |
| 不适用场景 | — |
| 入口命令 | `OpenCode Agent 自动匹配 — SKILL.md 位于 .opencode/skills/runtime-eval-diagnosis/` |
| 默认输出 | — |

## 文件结构说明

- `.opencode/skills/branded_html_report/` — branded-html-report (workspace skill)
- `.opencode/skills/cpca-weekly-data-capture/` — cpca-weekly-data-capture (workspace skill)
- `.opencode/skills/monthly-market-report/` — monthly-market-report (workspace skill)
- `.opencode/skills/runtime-eval-diagnosis/` — runtime-eval-diagnosis (workspace skill)
- `utility_scripts/build_workspace_skills_catalog.py` — 本页生成脚本
- `utility_scripts/render_html_report.py` — 品牌化报告渲染脚本
- `templates/` — Jinja2 报告模板 + CSS
- `assets/brand/` — Raccoon Research 品牌资产
