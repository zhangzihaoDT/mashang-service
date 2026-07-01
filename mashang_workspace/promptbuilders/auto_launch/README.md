# Auto Launch — 竞品上市事件 Prompt Workflow Asset

## 定位

Auto Launch 是**竞品上市事件 Prompt workflow asset**，不是爬虫监控脚本。

核心能力：
- 提供标准化的 Prompt 模板（按场景：日报/48h 简报/72h 跟踪/影响评估/LLM Judge）
- 提供车型配置、战场分类、事件类型、信源分层等资产
- 提供 AI 返回结果的校验和归一化工具
- 保留火山搜索 API 作为可选搜索后端经验

## 架构

### 标准路径（ChatGPT Plan）

```
ChatGPT Plan (plan_templates/)
    │
    ▼ raw_ai_output.json
Intake Workflow (validators/ → intake/)
    │
    ├── normalized.json
    ├── report.md
    └── intake_manifest.json
```

### Volc-assisted 路径

```
Business Task
    │
    ▼
volc_search_query_plan → search_tasks
    │
    ▼ (人工或外部工具执行)
Volc Search results
    │
    ▼
volc_search_result_to_event_brief → raw_ai_output.json
    │
    ▼
Intake Workflow (同标准路径)

### 组件职责

| 组件 | 位置 | 职责 |
|------|------|------|
| ChatGPT Plan | `plan_templates/` | 用户复制到 ChatGPT Plan 的自然语言任务描述 |
| Prompt 模板 | `prompts/` | 标准化的搜索/分析 Prompt，含变量占位、输出格式、校验规则 |
| 配置 | `configs/` | 事件类型、信源分层、战场分类、目标画像的 YAML 定义 |
| Schema | `schemas/` | JSON Schema 定义事件证据和简报的输出结构 |
| Search Adapter | `search_adapters/` | 可选搜索后端经验文档（当前仅 Volc Search） |
| Validator | `validators/validate_ai_response.py` | 校验 AI 输出 JSON 的结构完整性（新 canonical） |
| Normalizer | `validators/normalize_ai_response.py` | 将 raw_ai_output.json 转换为标准化 evidence JSON（新 canonical） |
| Old Validator（compat） | `examples/validate_ai_response.py` | 旧版校验脚本，保留兼容 |
| Old Normalizer（compat） | `examples/normalize_ai_response.py` | 旧版归一化脚本，保留兼容 |
| Promptbuilder CLI | `promptbuilder.py` | 旧版 CLI，渲染 `templates/search_task_prompt.md` |

## 旧 auto_launch_monitor.py

`research_scripts/auto_launch_monitor.py` 已下线，不再保留运行入口。

旧方案是一个 3264 行的单体搜索+提取+裁判脚本，包含火山方舟搜索、Firecrawl（已不可用）、正则提取、LLM Judge、聚合输出等逻辑。

**已迁移的资产**：

| 资产 | 旧位置 | 新位置 |
|------|--------|--------|
| watchlist 配置 | inline + CSV | `configs/ls8_competitor_watchlist.csv`（路径不变） |
| event types 定义 | inline | `configs/event_types.yaml` |
| source tiers 定义 | inline | `configs/source_tiers.yaml` |
| battle fields 分类 | inline | `configs/battle_fields.yaml` |
| target profiles | inline | `configs/target_profiles.yaml` |
| LLM Judge Prompt | inline | `prompts/llm_judge.md` |
| 火山搜索 API 经验 | inline | `search_adapters/volc_search.md` |
| validate/normalize | — | `examples/validate_ai_response.py` + `normalize_ai_response.py` |

**已下线的内容**：
- `research_scripts/auto_launch_monitor.py` → 替换为迁移说明
- `tests/scripts/test_auto_launch_monitor.py` → 删除（3781 行，仅服务旧脚本）
- Makefile `auto-launch-monitor` target → 删除

## 与 MIIT 新车公告的关系

MIIT 新车公告监控（`research_scripts/miit_new_car/`）与 Auto Launch 是**两个独立架构，不直接合并**。

| 维度 | MIIT | Auto Launch |
|------|------|-------------|
| 信息源 | 工信部 EIDC 官网（结构化 DOC） | 公开网络：官网/垂媒/社交媒体 |
| 方式 | Python 直接抓取 + 解析 | ChatGPT Plan + Prompt |
| 输出 | 公告信号简报 + evidence JSON | 事件证据 JSON + 影响评估 |
| 关系 | **官方前置信号源** | 消费 MIIT 信号做市场分析 |

MIIT 输出 `potential_event_signal`，不直接并入 auto_launch 管线。

## 短期 Workflow

```
ChatGPT Plan 执行（用户复制 plan_template 到 ChatGPT）
    │
    ▼ 输出 JSON（含来源链接和可信度标记）
人工保存到 outputs/auto_launch/{日期}_{车型}_{事件}/raw_ai_output.json
    │
    ▼
intake（process_ai_output.py | make auto-launch-intake）
    │
    ├── validated: 结构校验通过
    ├── normalized.json: 统一结构 JSON
    ├── report.md: 人类可读简报
    └── intake_manifest.json: 处理元数据
    │
    ▼
后续进入 mashang-service（入库、复盘、报告沉淀）
```

## 目录结构

```
promptbuilders/auto_launch/
├── README.md                  # 本文件
├── promptbuilder.py           # CLI Prompt 渲染入口（旧，保留兼容）
├── prompts/                   # 标准 Prompt 模板
│   ├── daily_radar.md         # 日报
│   ├── event_48h_brief.md     # 48h 简报
│   ├── event_72h_followup.md  # 72h 跟踪
│   ├── impact_vs_our_model.md # 影响评估
│   ├── llm_judge.md           # LLM 裁判
│   ├── volc_search_query_plan.md           # Volc 搜索查询计划
│   └── volc_search_result_to_event_brief.md # Volc 搜索结果结构化
├── plan_templates/            # ChatGPT Plan 任务描述
│   ├── chatgpt_plan_daily_radar.md
│   └── chatgpt_plan_event_48h.md
├── configs/                   # 配置
│   ├── event_types.yaml
│   ├── source_tiers.yaml
│   ├── battle_fields.yaml
│   └── target_profiles.yaml
├── schemas/                   # JSON Schema
│   ├── auto_launch_event.schema.json
│   └── auto_launch_brief.schema.json
├── search_adapters/           # 可选搜索后端经验
│   ├── README.md
│   └── volc_search.md
├── validators/                # 质量保证层参考
│   ├── validate_ai_response.py
│   └── normalize_ai_response.py
├── renderers/                 # 格式渲染层
│   ├── README.md
│   └── render_markdown_report.py
├── intake/                    # AI output intake workflow
│   ├── README.md
│   └── process_ai_output.py
├── runbooks/                  # 实际操作指南
│   ├── README.md
│   ├── chatgpt_plan_handoff.md
│   ├── pilot_run_decision_gate.md
│   └── volc_search_assisted_pilot.md
├── templates/                 # 旧模板（保留兼容）
│   ├── search_task_prompt.md
│   └── evidence_schema.json
└── examples/                  # 实现脚本 + 示例
    ├── validate_ai_response.py
    ├── normalize_ai_response.py
    ├── package_ai_report.py
    ├── build_battle_brief.py
    ├── validate_battle_brief.py
    ├── generate_golden_cases.py
    ├── README.md
    └── fixtures/
```

## 快速参考

```bash
# 生成搜索 Prompt（旧 promptbuilder，兼容入口）
make build-auto-launch-prompt

# 生成 Golden Prompt 样例
make build-auto-launch-golden-prompts

# 校验 AI 返回结果
make validate-auto-launch-ai-response

# 归一化 + 打包报告
make build-auto-launch-byd-datang-report

# ★★★ 日常使用 ★★★
# validate → normalize → markdown (output-dir 模式)
make auto-launch-intake SAMPLE=path/to/raw_ai_output.json OUT_DIR=path/to/output_dir/

# 仅校验
make auto-launch-validate SAMPLE=path/to/ai_output.json

# 仅归一化
make auto-launch-normalize SAMPLE=path/to/ai_output.json

# 查询配置
#   configs/event_types.yaml       事件类型定义
#   configs/source_tiers.yaml      信源分层
#   configs/battle_fields.yaml     战场分类
#   configs/target_profiles.yaml   目标画像
#   ../../configs/ls8_competitor_watchlist.csv  竞品池
```

## 产出物结构

使用 `--output-dir` 模式后，每个事件产出 4 个文件：

```
mashang_workspace/outputs/auto_launch/   # runtime run directories (not committed)
├── {run_id}/
│   ├── raw_ai_output.json       ← 原始 AI 输出（from ChatGPT Plan）
│   ├── normalized.json          ← 统一结构 JSON
│   ├── report.md                ← 人类可读简报
│   └── intake_manifest.json     ← 处理元数据
└── ...

promptbuilders/auto_launch/examples/     # committed samples
├── ai_outputs/                  ← 示例 AI 输出（仅用于结构测试）
├── normalized/                  ← 示例 normalized JSON
├── reports/                     ← 示例 markdown 报告
├── legacy_promptbuilder_cases/  ← 旧 promptbuilder 历史案例归档（非 regression 标准）
├── legacy_prompts/              ← 旧 workflow 遗留 Prompt 参考
└── legacy_ai_outputs/           ← 旧 workflow 遗留 AI 返回/报告参考
```

### 边界规则

- `mashang_workspace/outputs/auto_launch/` **只用于新 intake workflow 的 runtime run directories**，默认不提交 git
- 可提交的样例、contract 应放在 `promptbuilders/auto_launch/examples/`
- `legacy_*` 目录下的历史案例来自旧 auto_launch_monitor / 旧 promptbuilder 的运行产物，**仅用于参考，不代表当前工作流的质量标准，不构成 regression 基准**
- 旧 auto_launch_monitor 和旧 promptbuilder 的遗留运行产物不得写入 `outputs/auto_launch/`
- 旧产物已清理或迁移至 `promptbuilders/auto_launch/examples/legacy_*`

### Future Golden Cases

- 当前暂无 golden cases
- 只有通过新 intake workflow、来源可追溯、业务判断被人工认可的案例，才可以晋升为 golden case
- Golden cases 未来应单独建立 registry，而不是直接复用 legacy cases

## Pilot Run Decision Gate

在建立第一个 golden case 之前，所有输出均视为 pilot run。

当前状态：
- **暂无 golden cases**
- `examples/legacy_promptbuilder_cases/` **不是质量基准**
- 新的 golden case **必须来自真实 pilot run**
- Pilot run 的产出先用 `runbooks/pilot_run_decision_gate.md` 评估
- 再通过 `templates/pilot_quality_scorecard.md` 人工评审
- 通过后才考虑晋升为 golden case

完整流程：

```
pilot run → intake → 人工评审 (scorecard) → 通过 → 晋升 golden case
                                            → 不通过 → 保留在 outputs/ 作为记录
```

关键规则：
- Pilot run 的 validate / normalize / report 全部按现有 intake 流程自动完成
- 质量评分和晋升判断完全由人工完成（scorecard）
- 不创建 golden case registry，直到有第一个通过评审的案例
- 不把 legacy_promptbuilder_cases 用作质量标准
