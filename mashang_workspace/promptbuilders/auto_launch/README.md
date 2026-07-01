# Auto Launch — 竞品上市事件 Prompt Workflow Asset

## 定位

Auto Launch 是**竞品上市事件 Prompt workflow asset**，不是爬虫监控脚本。

核心能力：
- 提供标准化的 Prompt 模板（按场景：日报/48h 简报/72h 跟踪/影响评估/LLM Judge）
- 提供车型配置、战场分类、事件类型、信源分层等资产
- 提供 AI 返回结果的校验和归一化工具
- 保留火山搜索 API 作为可选搜索后端经验

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│  ChatGPT Plan                                                    │
│  (plan_templates/)                                               │
│  定时触发 / 日常雷达 / 简报生成 / 事件判断                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │ 输出 Markdown / JSON
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Promptbuilders                                                  │
│  (prompts/ + configs/ + schemas/)                                │
│  Prompt 模板 / 配置 / 输出结构 / 校验规则                         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ 参考经验
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Volc Search Adapter (optional)                                  │
│  (search_adapters/volc_search.md)                                │
│  仅保留已验证的火山搜索 API / 只返回候选信息 / 不承担事件判断     │
└──────────────────────────┬──────────────────────────────────────┘
                           │ AI raw.md
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  mashang-service                                                 │
│  (validators/ + examples/)                                       │
│  validate_ai_response → normalize_ai_response → 入库/复盘/报告   │
└─────────────────────────────────────────────────────────────────┘
```

### 组件职责

| 组件 | 位置 | 职责 |
|------|------|------|
| ChatGPT Plan | `plan_templates/` | 用户复制到 ChatGPT Plan 的自然语言任务描述 |
| Prompt 模板 | `prompts/` | 标准化的搜索/分析 Prompt，含变量占位、输出格式、校验规则 |
| 配置 | `configs/` | 事件类型、信源分层、战场分类、目标画像的 YAML 定义 |
| Schema | `schemas/` | JSON Schema 定义事件证据和简报的输出结构 |
| Search Adapter | `search_adapters/` | 可选搜索后端经验文档（当前仅 Volc Search） |
| Validator | `examples/validate_ai_response.py` | 校验 AI 返回结果的结构和来源标注 |
| Normalizer | `examples/normalize_ai_response.py` | 将 AI raw.md 转换为标准化 evidence JSON |
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
    ▼ 输出 Markdown / JSON（含来源链接）
人工保存到 outputs/auto_launch/ai_response_examples/*.raw.md
    │
    ▼
validate_ai_response.py → validation.json
    │
    ▼
normalize_ai_response.py → normalized_evidence.json
                         → executive_brief.md
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
│   └── llm_judge.md           # LLM 裁判（从旧 monitor 迁移）
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
│   └── README.md
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

# 查询配置
#   configs/event_types.yaml       事件类型定义
#   configs/source_tiers.yaml      信源分层
#   configs/battle_fields.yaml     战场分类
#   configs/target_profiles.yaml   目标画像
#   ../../configs/ls8_competitor_watchlist.csv  竞品池
```
