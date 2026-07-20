# AGENTS.md — mashang Service Guide

## 启动位置与宿主层

**OpenCode 应从仓库根目录启动。** 根目录是所有 Agent 命令、Makefile、MCP 配置的统一执行入口。

mashang-service 根目录是 **Agent Harness / service 宿主层**，承载以下能力：

- `Makefile` / `pyproject.toml` — 构建与调度
- `.opencode/`、`opencode.jsonc`、MCP 配置 — OpenCode / MCP 能力
- `.env` / `.venv/` — 本地环境
- `dataset/` — 共享数据入口
- `mashang_shared/` — 共享 operator/schema
- 根 `AGENTS.md` / `README.md` — 项目级文档

Agent 工作边界：**启动在根目录，工作在 `mashang_workspace/`**。

## 项目定位

mashang-service 是一个**汽车业务数据分析项目**，包含以下分支 / 模块：

| 分支 | 目录 | 定位 |
|------|------|------|
| **Runtime** | `mashang_runtime/` | Legacy / frozen 旧 Runtime 层；当前不作为日常活跃开发目录 |
| **Runtime V2** | `mashang_runtimeV2/` | Runtime V2 / 产品化沉淀层；承接从 `mashang_workspace/` 验证稳定后的能力 |
| **Workspace** | `mashang_workspace/` | AI-native 数据分析工作区（Scripts/Docs/Eval/Tests） |
| **Shared** | `mashang_shared/` | 共享 operator/schema 层（非默认工作区） |

**共享底座**：
- `dataset/` — 原始数据
- `.env` — 环境变量
- `.venv/` — Python 虚拟环境
- `requirements.txt` — 依赖
- `mashang_shared/` — 共享 operator/schema

**核心数据集**：
- `dataset/order_data.parquet` — 订单主表（含锁单、交付、开票、退订等时间戳）
- `dataset/assign_data.csv` — 下发线索表（含渠道拆解、7/30日转化）
- `dataset/config_attribute.parquet` — 选配属性表（配置渗透率分析）

## 工作原则

1. **新分析能力**：优先进入 `mashang_workspace/`
2. **Runtime 分层**：`mashang_runtime/` 是 legacy / frozen 旧 Runtime 层，不作为日常活跃开发目录。`mashang_runtimeV2/` 是产品化沉淀层，承接从 `mashang_workspace/` 验证稳定后的能力。
3. **不要移动 `dataset/` `.env` `.venv/`**
4. **不要在 runtime 中做临时分析**
5. **不要在 workspace 中引入破坏 runtime 的改动**
6. **`mashang_workspace` 是日常唯一主工作区**
7. **OpenCode 应优先读取 `mashang_workspace/AGENTS.md`**
8. **不要在根目录创建新的 `docs/scripts/eval/tests/utils`**
9. **新分析能力优先沉淀到 `mashang_workspace/runtime_scripts/ + research_scripts/ + docs/ + eval/`**
10. **每次完成改动后运行 `make eval` 或 `make ci`**
11. **能力产品化路径**：workspace 中验证稳定的能力，经过明确 V2 / packaging / productization 任务后，迁移到 `mashang_runtimeV2/`。不要绕过 workspace 直接在 runtimeV2 中开发探索性能力。
12. **`mashang_shared/` 边界**：共享 operator/schema 层，不应随意修改。如修改需说明影响范围，并同步相关测试。
13. **MCP 边界**：MCP 能力由根目录统一提供（`.opencode/` / `opencode.jsonc`），workspace 只消费能力。不得将本地 profile、cookies、API key、incoming 原始数据等提交进仓库。

其余原则详见 `mashang_workspace/AGENTS.md`。

## 工作原则

1. **优先阅读 docs**：`docs/` 目录下的文档是首要参考资料，包含业务术语、指标口径、车型映射、时间规则、分析范式、追问规则。
2. **优先复用 scripts**：`scripts/` 已有 13+ 个独立脚本，新需求优先基于现有脚本扩展。
3. **不要随意修改原始数据**：`dataset/` 下的 CSV/Parquet 是原始数据，分析应使用副本或只读方式。

**上市时间必须从业务定义读取**：涉及"上市以来"的时间范围，必须使用 `shared/schema/business_definition.json` 中 `time_periods.{series}.end` 字段，不得从数据中取 `lock_time` 最小值推断。脚本优先使用 `--since-launch` 参数，临时分析使用 `mashang_workspace/utils/business.py` 的 `get_launch_date()`。
4. **不要编造数据**：在数据无法支撑结论时，明确说明"无数据/数据不足"。
5. **所有分析结果必须说明来源**：包括数据源、过滤条件、时间窗口、指标口径。
6. **临时代码放 scratch/ 或 outputs/**，稳定脚本再沉淀到 `scripts/`。
7. **高频能力先在 workspace 内沉淀**：高频分析路径先沉淀到 `mashang_workspace/runtime_scripts/`；经过明确 V2 任务后再迁移至 `mashang_runtimeV2/`。旧 `mashang_runtime/` 不作为回流目标。
8. **回答数据问题前，先看 `docs/data_dictionary.md` 和 `docs/metric_definitions.md`**，确认字段名和口径。
9. **对标准分析问题，优先调用 `scripts/` 下已有脚本**，不要重复造轮子。
10. **如果脚本缺少参数，先小范围补充 CLI 参数，不要重写脚本**。
11. **如果临时分析重复出现 2 次以上，再沉淀为 `scripts/` 稳定脚本**。
12. **所有脚本在 `--format json` 时输出标准 Result Contract**，包含 scope/result/followup_context。
13. **分析结果可通过 `eval/run_numeric_eval.py` 做结构校验和非负校验**。

## Phase 2: Script Interface & Data Contract

### 标准 CLI 参数

所有核心脚本至少支持 `--help`，并尽量支持以下通用参数：

| 参数 | 说明 | 示例 |
|------|------|------|
| `--date` | 单日查询 | `--date 2026-06-01` |
| `--start-date` | 开始日期 | `--start-date 2026-06-01` |
| `--end-date` | 结束日期 | `--end-date 2026-06-10` |
| `--series` | 车系过滤 | `--series LS8` |
| `--model` | 车型过滤 | `--model "66 Ultra"` |
| `--city` | 城市过滤 | `--city 上海` |
| `--output` | 输出目录 | `--output outputs/tables/` |
| `--format` | 输出格式 | `--format csv` / `--format json` |
| `--limit` | TopN | `--limit 5` |

### 统一输出格式

```
[Summary]
  一句话结论

[Scope]
  数据源:
  时间窗口:
  过滤条件:
  指标口径:

[Result]
  核心表格或关键数字

[Output]
  输出文件路径 (如果有)
```

### 数据字典

```bash
python scripts/data_dictionary.py                    # 终端输出
python scripts/data_dictionary.py --format csv       # CSV 输出
python scripts/data_dictionary.py --format json      # JSON 输出
```

### Smoke Test

```bash
pytest tests/scripts -q                               # 运行所有脚本 smoke test
python tests/scripts/test_script_help.py              # 验证 --help
```

### Follow-up Eval Cases

多轮追问测试用例在 `eval/cases/followup_cases.json`，覆盖:
- 锁单分车型 → 追问城市分布 (时间继承 + 代指消解)
- LS6 增程/纯电 → 追问改时间窗口 (时间替换)
- LS8 分车型 → 追问加过滤条件 (条件追加)
- 分城市 → 追问改分车型 (维度切换)
- 预测锁单 → 追问释放曲线 (分析类型切换)

## Phase 3: Follow-up Runner & Workflow Validation

### Follow-up Eval Runner

```bash
python eval/run_followup_eval.py                     # dry-run 模式 (默认)
python eval/run_followup_eval.py --format json       # JSON 输出
python eval/run_followup_eval.py --execute           # 真实执行
python eval/run_followup_eval.py --as-of-date 2026-06-11  # 指定基准日期
```

Runner 功能:
1. 读取 `eval/cases/followup_cases.json`
2. 逐轮解析 expected_context → 推荐脚本 + CLI 参数
3. 多轮上下文继承 (时间/指标/车型/筛选条件)
4. Symbolic time_window 解析为真实日期
5. dry-run (默认) 或 execute 模式

### Context → Script 映射规则

| expected_context | 脚本 |
|-----------------|------|
| lock_count + group_by=model/series | `scripts/lock_by_model.py` |
| lock_count + group_by=city | `scripts/lock_city_distribution.py` |
| lock_count (无分组) | `scripts/daily_lock_count.py` |
| lock_forecast/cohort_forecast | `scripts/cohort_forecast.py` |
| release_curve | `scripts/release_curve_analysis.py` |
| voc_theme/jtbd_theme | `scripts/voc_theme_analysis.py` |

详见 `docs/followup_runner_rules.md`。

### Eval Tests

```bash
pytest tests/eval -q                                 # 运行 eval 测试
pytest tests/ -q                                     # 运行所有测试
```

## Phase 4: Natural Language Context Parser

### Context Parser

`eval/context_parser.py` 将用户自然语言解析为结构化 context，支持两种模式：

```bash
# 单轮解析 CLI
python eval/parse_context_cli.py "昨天锁单数分车型"
python eval/parse_context_cli.py "那最近 7 天呢？" --previous-context '{"metric":"lock_count_share","time_window":"last_15_days","series":"LS6","group_by":"energy_type"}'

# Runner 的 parse-text 模式
python eval/run_followup_eval.py --parse-text
python eval/run_followup_eval.py --parse-text --format json --output outputs/tables/parse_result.json
```

### Parser 支持的字段

| 字段 | 说明 | 示例解析 |
|------|------|----------|
| metric | 指标类型 | "锁单数"→lock_count, "占比"→lock_count_share |
| time_window | 时间窗口 | "昨天"→yesterday, "近15日"→last_15_days |
| series | 车系 | "LS6", "LS8" |
| model | 车型 | 含具体型号的文本 |
| city | 城市 | "上海" |
| group_by | 分组维度 | "分车型"→model, "城市分布"→city |
| filters | 过滤器 | "只看大电池组"→large_battery |
| analysis_type | 分析类型 | "趋势"→trend, "回测"→backtest |

### Context Match Rate

Parse-text 模式下比较 parsed context 与 expected_context，评估解析质量。

```bash
python eval/run_followup_eval.py --parse-text --as-of-date 2026-06-11
```

目标: context match rate >= 80%。当前: **92.9%** (13/14 turns)。

详见 `docs/context_parser_rules.md` 和 `eval/context_parser.py`。

## Phase 5: Execution Result Contract & Numeric Eval

### Result Contract

所有核心脚本支持 `--format json` 时输出统一 Result Contract：

```json
{
  "status": "success | partial_success | error",
  "script": "scripts/lock_by_model.py",
  "scope": { "data_source": "...", "time_window": {...}, "filters": {...}, "metric_definition": "..." },
  "result": { "summary": "...", "metrics": {...}, "dimensions": [...], "tables": [...] },
  "artifacts": { "csv": "...", "json": "..." },
  "followup_context": { "metric": "...", "top_entities": [...], "available_dimensions": [...] },
  "warnings": [],
  "errors": []
}
```

已支持 Contract 的脚本 (6个):
- `scripts/daily_lock_count.py`
- `scripts/lock_by_model.py`
- `scripts/lock_city_distribution.py`
- `scripts/cohort_forecast.py`
- `scripts/assign_conversion_analysis.py`
- `scripts/attribute_penetration_report.py`

详见 `docs/result_contract.md`。

### Numeric Eval

```bash
python eval/run_numeric_eval.py                              # 执行并校验结果
python eval/run_numeric_eval.py --format json                # JSON 输出
python eval/run_numeric_eval.py --cases eval/cases/numeric_cases.json
```

当前: 5/5 cases passing (100%)。

### Result Reference

context_parser 支持解析 "这 75 个" → 自动继承上一轮 top_entities 中的字段值。

```bash
python eval/parse_context_cli.py "这 75 个锁单城市分布" --previous-context '{"series":"LS8","top_entities":[{"field":"series","value":"LS8","metrics":{"lock_count":75}}]}'
```

详见 `docs/context_parser_rules.md`。

## 追问处理规则

1. **时间继承**：用户追问中省略时间窗口时，优先继承上一轮的 `time.start` / `time.end`。
2. **指标继承**：用户追问中省略指标时，优先继承上一轮的 `metric` / `analysis_intent`。
3. **代指消解**：
   - "这 75 个" → 继承上一轮的过滤结果并作为新的过滤条件
   - "刚才那个车型" → 继承上一轮的 `filters.series` 或 `filters.product_name`
   - "昨天 LS8" → 继承 `series=LS8` + `time=昨天`
4. **上下文不足时**：先输出需要澄清的字段（时间、车型、指标），不要假设业务口径。
5. **口径一致**：同一次 session 内保持口径一致，除非用户主动要求变更。
6. **追问→脚本映射**：根据继承的上下文选择对应脚本并传参（详见 `docs/followup_runner_rules.md`）。

## 输出规范

- **简洁结论**：先给结论，再给关键数字
- **表格**：优先用 Markdown 表格呈现结构化结果
- **文件输出**：必要时生成 CSV/HTML/PNG 到 `outputs/` 目录
  - `outputs/tables/` — CSV/JSON 结构化数据
  - `outputs/reports/` — HTML/Markdown 报告
  - `outputs/charts/` — PNG/SVG/HTML 图表
- **口径说明**：每次输出附带数据来源、过滤条件、时间窗口
- **脚本路径**：如果是通过 `scripts/` 下的脚本执行，注明脚本路径

## 目录结构

```
mashang-service/
├── AGENTS.md              ← 本文件 (项目级 Agent 指南)
├── README.md              ← 项目主文档
├── .env                   ← 共享环境变量
├── .venv/                 ← 共享虚拟环境
├── dataset/               ← 共享原始数据
├── requirements.txt       ← 共享依赖
├── mashang_shared/        ← 共享 operator/schema（非默认工作区）
│
├── mashang_runtime/       ← Legacy / frozen 旧 Runtime（非活跃开发，仅历史兼容）
│   ├── agent/             ← Agent Loop / Planner / Router / Decisions
│   ├── tools/             ← 确定性执行工具
│   ├── operators/         ← 固定业务算子
│   ├── schema/            ← 配置/指标/路径定义
│   ├── main.py            ← CLI 入口
│   ├── feishu_bot.py      ← 飞书入口
│   └── README.md          ← Runtime 说明
│
├── mashang_runtimeV2/     ← Runtime V2 / 产品化沉淀层（从 workspace 验证稳定后迁移至此）
│   └── README.md          ← Runtime V2 说明
│
└── mashang_workspace/     ← AI-native 分析工作区
    ├── AGENTS.md          ← Workspace Agent 指南
    ├── README.md
    ├── docs/               ← 业务文档
    ├── scripts/            ← 独立分析脚本 (16 个)
    ├── eval/               ← Eval 测试框架
    ├── tests/              ← Smoke test (pytest)
    ├── utils/              ← 工具模块
    └── outputs/            ← 输出文件
        ├── reports/
        ├── charts/
        └── tables/
```

## Fast Reference

| 查询类型 | CLI 方式 |
|----------|----------|
| CLI 问答 | `python main.py "昨天锁单数"` |
| 锁单总览 | `python mashang_workspace/runtime_scripts/daily_lock_count.py` | runtime |
| 车型拆分 | `python mashang_workspace/runtime_scripts/lock_by_model.py --limit 5` | runtime |
| 城市分布 | `python mashang_workspace/runtime_scripts/lock_city_distribution.py` | runtime |
| 线索转化 | `python mashang_workspace/runtime_scripts/assign_conversion_analysis.py` | runtime |
| 配置渗透率 | `python mashang_workspace/runtime_scripts/attribute_penetration_report.py` | runtime |
| ATP 月报 | `python mashang_workspace/runtime_scripts/atp_price_report.py 2026-05` | runtime |
| 释放曲线 | `python mashang_workspace/research_scripts/release_curve_analysis.py` | research |
| 预测锁单 | `python mashang_workspace/research_scripts/cohort_forecast.py` | research |
| 回测 | `python mashang_workspace/research_scripts/lock_predict_backtest.py` | research |
| 同比分析 | `python mashang_workspace/research_scripts/quick_lock_ratio.py` | research |
| 锁单月度预估 | `make lock-forecast` 或 `python mashang_workspace/research_scripts/structured_business_forecast.py --as-of YYYY-MM-DD --target-month YYYY-MM [--prior-strength N]` | research |
| 开票月度预估 | `make invoice-forecast` 或 `python mashang_workspace/research_scripts/invoice_monthly_forecast.py --as-of YYYY-MM-DD --target-month YYYY-MM --lock-regime mode` | research |
| Auto Launch 搜索 | `python -m auto_launch.cli search --request "看看极氪最近 7 天都有什么动作"` | service |
| Auto Launch Daily 摄入 | `python -m auto_launch.cli daily --input <file>` | service |
| Auto Launch 品牌日报 | `python -m auto_launch.cli report --type brand-daily --brand 智己` | service |
| Auto Launch 完整日更 | `python -m auto_launch.cli run-day --brand 智己` | service |
| Auto Launch 测试 | `pytest auto_launch/tests/ -q` | service |
| VOC 分析 | `python mashang_workspace/utility_scripts/voc_theme_analysis.py` | utility |
| 数据字典 | `python mashang_workspace/utility_scripts/data_dictionary.py` | utility |
| 每日观察 | `python mashang_workspace/utility_scripts/skills_order_observation_daily.py` | utility |
| 达成率预警 | `python mashang_workspace/utility_scripts/skills_attainment_rate_alert.py --days 10` | utility |
| 生成 Eval | `python mashang_workspace/utility_scripts/generate_eval_cases.py` | utility |
| 数据更新并同步 | `make daily-data-pipeline` (写操作) | DataOps |
| 预检数据 | `make daily-data-pipeline-dry-run` | DataOps |
| 运行 Runtime Eval | `python eval/run_runtime_eval.py` |
| 运行 Follow-up Eval | `python mashang_workspace/eval/run_followup_eval.py` |
| 运行 Numeric Eval | `python mashang_workspace/eval/run_numeric_eval.py` |
| 解析自然语言 | `python mashang_workspace/eval/parse_context_cli.py "昨天锁单数分车型"` |
| Smoke Test | `pytest mashang_workspace/tests -q` |
| 全量测试 | `pytest tests/ -q` |
