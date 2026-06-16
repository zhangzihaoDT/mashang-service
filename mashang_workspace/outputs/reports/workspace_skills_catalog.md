# Mashang Workspace Skills Catalog

Agent Harness 能力目录

生成日期：2026-06-16

本页面展示 mashang_workspace 中可被 OpenCode Agent 调用的 workspace 级 skills。

---

## 概览

| 指标 | 数值 |
|------|------|
| Workspace Skills | 2 |
| Repo-Level Skills | 1 |
| Skills 输出目录 | outputs/reports/ |
| 最近更新 | 2026-06-16 |

## Skills Overview

| Skill | 层级 | 能力定位 | 入口文件 | 默认输出 |
|-------|------|---------|---------|---------|
| branded-html-report | workspace | 将汽车经营分析、预测模型、回测评估、市场洞察等结果，渲染为具有 Raccoon  | `python runtime_scripts/daily_lock_count.py --format json \` | mashang_workspace/outputs/reports/ |
| runtime-eval-diagnosis | workspace | Diagnose mashang runtime eval reports, i | `OpenCode Agent 自动匹配 — SKILL.md 位于 .opencode/skills/runtime-eval-diagnosis/` | — |
| official-document-render | repo | 通用正式材料 Word/PDF/HTML 渲染能力，不计入 workspace  | `scripts/render_official_document.py` | outputs/submission/ |

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
| 默认输出 | mashang_workspace/outputs/reports/ |

### runtime-eval-diagnosis

| 字段 | 内容 |
|------|------|
| 目录 | `.opencode/skills/runtime-eval-diagnosis/` |
| 层级 | workspace |
| 能力定位 | Diagnose mashang runtime eval reports, including hard_pass, soft_pass, failed, contract mismatch, fact_types, and exit_reason. |
| 适用场景 | — |
| 不适用场景 | — |
| 入口命令 | `OpenCode Agent 自动匹配 — SKILL.md 位于 .opencode/skills/runtime-eval-diagnosis/` |
| 默认输出 | — |

## Agent Harness 分层说明

### repo root skills
- 通用生产能力
- official-document-render — Markdown → Word/PDF/HTML 正式材料
- 位于 `.opencode/skills/official_document_render/`

### workspace skills
- 业务场景能力
- branded-html-report — 将汽车经营分析、预测模型、回测评估、市场洞察等结果，渲染为具有 Raccoon 
- runtime-eval-diagnosis — Diagnose mashang runtime eval reports, i
- 位于 `mashang_workspace/.opencode/skills/`

### workspace tools
- utility_scripts/ — 渲染入口脚本
- templates/ — Jinja2 报告模板
- assets/brand/ — 品牌资产
- outputs/reports/ — 报告输出

### repo root tools
- scripts/render_official_document.py
- scripts/smoke_test_official_document_render.py
- skills/official_document_render/

---

> 说明：repo root 的 official-document-render 是通用正式材料渲染能力（Word/PDF/HTML），不归入 workspace skills。本文件仅盘点 mashang_workspace 下的 workspace 级 skills。
