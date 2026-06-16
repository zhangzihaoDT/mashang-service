# Mashang Workspace Capability Catalog

Agent Harness 能力目录

生成日期：2026-06-16

本页面展示 mashang_workspace 中可被 OpenCode Agent 调用的 workspace 级 skills，按能力类型分组。

---

## 概览

| 指标 | 数值 |
|------|------|
| Workspace Skills | 3 |
| Capability Groups | 2 |
| 最近更新 | 2026-06-16 |

## Skills Overview

| Skill | Group | Level | Description |
|-------|-------|-------|-------------|
| branded-html-report | reporting | workspace | 将汽车经营分析、预测模型、回测评估、市场洞察等结果，渲染为具有 Raccoon Research / mashang 风格的 HTML 数据报告。 |
| monthly-market-report | reporting | workspace | monthly-market-report v0.1 是基于 `passenger_insurance` 现有 6 张预聚合单表的月度汽车市场固定主查询能力。 |
| runtime-eval-diagnosis | evaluation | workspace | Diagnose mashang runtime eval reports, including hard_pass, soft_pass, failed, |

---

## Evaluation Skills

### runtime-eval-diagnosis

| 字段 | 内容 |
|------|------|
| Description | Diagnose mashang runtime eval reports, including hard_pass, soft_pass, failed, contract mismatch, fact_types, and exit_reason. |
| Skill Entry | `.opencode/skills/runtime-eval-diagnosis/SKILL.md` |
| Related Scripts | — |
| Outputs | — |
| Tags | 报告 / Eval / 诊断 / Runtime |
| Status | active |

## Reporting Skills

### branded-html-report

| 字段 | 内容 |
|------|------|
| Description | 将汽车经营分析、预测模型、回测评估、市场洞察等结果，渲染为具有 Raccoon Research / mashang 风格的 HTML 数据报告。 |
| Skill Entry | `.opencode/skills/branded_html_report/SKILL.md` |
| Related Scripts | `runtime_scripts/daily_lock_count.py`, `utility_scripts/render_html_report.py` |
| Outputs | `mashang_workspace/outputs/reports/` |
| Tags | HTML / 品牌 / 报告 / 预测 / 回测 / 市场 / Raccoon Research |
| Use Cases | 销量预测报告、锁单释放曲线报告、模型回测报告、汽车市场洞察报告、经营复盘报告、用户反馈 / VOC 分析报告、车型结构、城市分布、渠道分析报告 |
| Non-goals | 政府正式申报书、通知/公文风材料、Word / PDF 正式材料、简历、PPT、纯命令行日志 |
| Status | active |

### monthly-market-report

| 字段 | 内容 |
|------|------|
| Description | monthly-market-report v0.1 是基于 `passenger_insurance` 现有 6 张预聚合单表的月度汽车市场固定主查询能力。 |
| Skill Entry | `.opencode/skills/monthly-market-report/SKILL.md` |
| Related Scripts | `research_scripts/market_report/run_monthly_market_report.py` |
| Outputs | `mashang_workspace/outputs/monthly_market_report/YYYY-MM/` |
| Tags | 报告 / 市场 |
| Use Cases | 生成某月汽车市场报告、跑某月市场报告固定问题、运行月报 24 个固定问题、生成 ways / TP&MIX 月报底稿、生成乘用车市场月报数据查询结果、跑 monthly market report |
| Non-goals | city×brand 城市内品牌排名、city×model 城市内车型排名、city×price_band×brand 城市×价位段×品牌交叉分析、brand×city_tier 品牌×城市线级交叉分析、region×model 区域×车型排名、TOP50 车型散点分布图、完整竞争格局页复刻、临时专题分析、重点城市专题分析、南北方专题分析、历史城市附录 |
| Status | active |

---

## 文件结构说明

- `.opencode/skills/branded_html_report/` — branded-html-report skill
- `.opencode/skills/monthly-market-report/` — monthly-market-report skill
- `.opencode/skills/runtime-eval-diagnosis/` — runtime-eval-diagnosis skill
- `utility_scripts/build_workspace_skills_catalog.py` — 本页生成脚本
