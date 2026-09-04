# mashang_workspace — Daily Business Analytics Workspace

## 定位

`mashang_workspace` 是 **Daily Business Analytics Workspace（日常业务分析工作区）**：面向 OpenCode / Claude Code 等 AI Coding Agent 的标准化业务分析工具箱，解决"今天要查什么、算什么、分析什么"（锁单、库存、门店、车型、渠道等高频、相对确定的业务分析）。
与 `mashang_runtime_v2`（Unified Research Runtime）共享 `dataset/` `.env` `.venv` 等底座资源；成熟能力以 `runtime_scripts` 形态被 runtime_v2 确定性调度。

## 目录结构

```
mashang_workspace/
├── AGENTS.md              # Workspace Agent 指南
├── README.md              # 本文件
├── docs/                  # 业务文档（术语/指标/车型/时间/分析范式/追问/合同）
├── runtime_scripts/       # Core — Runtime V2 可调度（6 个稳定分析脚本）
├── research_scripts/      # Research — 预测/回测/释放曲线/MIIT 新车公告（7 个）
├── utility_scripts/       # Utility — DataOps/SyncOps/工具（5 个）
├── (legacy_scripts/ — 已退休)  # 历史参考脚本已迁移到 runtime_scripts/research_scripts/utility_scripts
├── eval/                  # Eval 测试框架
│   ├── run_followup_eval.py    # 多轮追问 Runner
│   ├── run_numeric_eval.py     # 数值校验 Runner
│   ├── context_parser.py       # 自然语言 → context 解析
│   ├── parse_context_cli.py    # 单轮解析 CLI
│   └── cases/
├── tests/                 # Smoke test（pytest）
│   ├── scripts/           # 脚本级测试
│   └── eval/              # Eval Runner + Parser 测试
├── schema/                # workspace 本地 schema（index_summary_daily_matrix.csv 等；业务定义统一在 shared/schema/）
├── registry/              # 能力注册表（capability_registry.json）
├── utils/                 # 工具模块
│   └── paths.py           # 路径工具
└── outputs/               # 输出文件
    ├── reports/           # HTML/MD 报告（从 scripts/reports/ 迁移）
    ├── charts/            # PNG/SVG 图表
    └── tables/            # CSV/JSON 结果表
```

## 常用命令

```bash
# 数据字典（utility）
python mashang_workspace/utility_scripts/data_dictionary.py --input dataset

# 上险数据 smoke check（research）
python mashang_workspace/research_scripts/tp_and_mix_ways/check_tp_and_mix_ways_asset.py

# 锁单分析（runtime）
python mashang_workspace/runtime_scripts/daily_lock_count.py --date 2026-06-10
python mashang_workspace/runtime_scripts/lock_by_model.py --date 2026-06-10 --limit 5
python mashang_workspace/runtime_scripts/lock_city_distribution.py --date 2026-06-10 --series LS8

# 释放曲线 / 预测（research）
python mashang_workspace/research_scripts/release_curve_analysis.py
python mashang_workspace/research_scripts/cohort_forecast.py

# MIIT 公告情报（MIIT/ 模块，workspace 旧实现已迁移移除）
python3 MIIT/scripts/07_build_wide_table.py --batch 410
python3 MIIT/scripts/06_build_vehicle_dataset.py
python3 MIIT/scripts/validate_eidc_batch.py

# VOC 分析（utility）
python mashang_workspace/utility_scripts/voc_theme_analysis.py

# 线索转化 / 配置渗透率（runtime）
python mashang_workspace/runtime_scripts/assign_conversion_analysis.py
python mashang_workspace/runtime_scripts/attribute_penetration_report.py

# ATP 月报（runtime）
python mashang_workspace/runtime_scripts/atp_price_report.py 2026-05

# Context Parser
python mashang_workspace/eval/parse_context_cli.py "昨天锁单数分车型"
python mashang_workspace/eval/parse_context_cli.py "那最近 7 天呢？" --previous-context '{...}'

# Follow-up Runner
python mashang_workspace/eval/run_followup_eval.py
python mashang_workspace/eval/run_followup_eval.py --parse-text --as-of-date 2026-06-11

# Numeric Eval
python mashang_workspace/eval/run_numeric_eval.py

# Tests
pytest mashang_workspace/tests -q
```

## 数据路径

- 原始数据：`../dataset/`（项目根目录，含 `TP&MIX-ways/` 共享资产）
- 输出文件：`outputs/tables/` `outputs/reports/` `outputs/charts/`
- 业务文档：`docs/`
- 上险数据使用指南：`docs/tp_and_mix_ways_usage.md`

## CLI 规范

所有脚本支持 `--help`，并尽量支持通用参数：

| 参数 | 说明 |
|------|------|
| `--date` | 单日查询 |
| `--start-date` / `--end-date` | 时间范围 |
| `--series` | 车系过滤 |
| `--model` | 车型过滤 |
| `--city` | 城市过滤 |
| `--output` | 输出目录 |
| `--format` | terminal / csv / json |
| `--limit` | TopN |

## Context Parser

`eval/context_parser.py` 将自然语言解析为结构化 context：

```bash
python mashang_workspace/eval/parse_context_cli.py "昨天锁单数分车型"
```

当前 context match rate：**92.9%** (13/14 turns)。

## Follow-up Runner

`eval/run_followup_eval.py` 验证多轮追问场景的脚本调度：

- expected_context 模式（Phase 3）
- parse-text 模式（Phase 4）
- dry-run / execute 模式

## Result Contract

所有脚本的 `--format json` 输出统一 Result Contract，包含 scope/result/followup_context。

## 与 mashang_runtime 的关系

| 维度 | mashang_workspace | mashang_runtime |
|------|------------------|-----------------|
| 定位 | AI Agent 分析工作区 | 产品化 Agentic BI Runtime |
| 用户 | OpenCode / Claude Code | 飞书 Bot / 命令行 |
| 开发方式 | 快速分析脚本 | 稳定算子 + Tool |
| 验证 | pytest + numeric eval | Runtime Eval |
| 回流 | 高频能力→沉淀到 runtime | — |
