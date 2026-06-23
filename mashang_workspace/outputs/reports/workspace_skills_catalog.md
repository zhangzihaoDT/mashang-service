# Mashang Workspace Skills Catalog

Agent Harness 能力目录

生成日期：2026-06-23

本页面展示 mashang_workspace 中可被 OpenCode Agent 调用的 workspace 级 skills。

---

## 概览

| 指标 | 数值 |
|------|------|
| Workspace Skills | 3 |
| Skills 输出目录 | mashang_workspace/outputs/reports/, outputs/miit_new_car/promptbuilder_runs/, mashang_workspace/outputs/monthly_market_report/YYYY-MM/, outputs/auto_launch/ |
| 最近更新 | 2026-06-23 |

## Skills Overview

| Skill | 类型 | 能力定位 | 入口文件 | 默认输出 |
|-------|------|---------|---------|---------|
| branded-html-report | workspace | 将汽车经营分析、预测模型、回测评估、市场洞察等结果，渲染为具有 Raccoon  | `python runtime_scripts/daily_lock_count.py --format json \` | ['mashang_workspace/outputs/reports/'] |
| monthly-market-report | workspace | monthly-market-report v0.1 是基于 `passenge | `OpenCode Agent 自动匹配 — SKILL.md 位于 .opencode/skills/monthly-market-report/` | ['mashang_workspace/outputs/monthly_market_report/YYYY-MM/'] |
| runtime-eval-diagnosis | workspace |  | `OpenCode Agent 自动匹配 — SKILL.md 位于 .opencode/skills/runtime-eval-diagnosis/` | — |
| auto_launch | Promptbuilder / Intelligence Workflow | 生成竞品市场事件检索 Prompt；验证 AI raw response；归一化 | `make build-auto-launch-prompt` | outputs/auto_launch/ |
| miit_new_car | Promptbuilder / MIIT Workflow | MIIT 公告信号解释 Prompt Pack；新车申报情报分析 | `make miit-fetch-batch BATCH=N` | outputs/miit_new_car/promptbuilder_runs/ |

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

### monthly-market-report

| 字段 | 内容 |
|------|------|
| 目录 | `.opencode/skills/monthly-market-report/` |
| 层级 | workspace |
| 能力定位 | monthly-market-report v0.1 是基于 `passenger_insurance` 现有 6 张预聚合单表的月度汽车市场固定主查询能力。 |
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

### auto_launch (Promptbuilder / Intelligence Workflow)

| 字段 | 内容 |
|------|------|
| 目录 | `promptbuilders/auto_launch/` |
| 类型 | Promptbuilder / Intelligence Workflow |
| 能力定位 | 生成竞品市场事件检索 Prompt；验证 AI raw response；归一化 evidence；Raw-first report packaging |
| 入口命令 | `make build-auto-launch-prompt` |

### miit_new_car (Promptbuilder / MIIT Workflow)

| 字段 | 内容 |
|------|------|
| 目录 | `promptbuilders/miit_new_car/` |
| 类型 | Promptbuilder / MIIT Workflow |
| 能力定位 | MIIT 公告信号解释 Prompt Pack；新车申报情报分析 |
| 入口命令 | `make miit-fetch-batch BATCH=N` |

## 文件结构说明

- `.opencode/skills/branded_html_report/` — branded-html-report (workspace skill)
- `.opencode/skills/monthly-market-report/` — monthly-market-report (workspace skill)
- `.opencode/skills/runtime-eval-diagnosis/` — runtime-eval-diagnosis (workspace skill)
- `promptbuilders/auto_launch/` — auto_launch (Promptbuilder / Intelligence Workflow)
- `promptbuilders/miit_new_car/` — miit_new_car (Promptbuilder / MIIT Workflow)
- `utility_scripts/build_workspace_skills_catalog.py` — 本页生成脚本
- `utility_scripts/render_html_report.py` — 品牌化报告渲染脚本
- `templates/` — Jinja2 报告模板 + CSS
- `assets/brand/` — Raccoon Research 品牌资产
