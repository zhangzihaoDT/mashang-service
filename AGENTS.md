# AGENTS.md — mashang Service Guide

## 启动位置与宿主层

**OpenCode 应从仓库根目录启动。** 根目录是所有 Agent 命令、Makefile、MCP 配置的统一执行入口。

mashang-service 根目录是 **Agent Harness / service 宿主层**，承载以下能力：

- `Makefile` / `pyproject.toml` — 构建与调度
- `.opencode/`、`opencode.jsonc`、MCP 配置 — OpenCode / MCP 能力
- `.env` / `.venv/` — 本地环境
- `dataset/` — 共享数据入口
- `shared/` — 共享 operator/schema
- 根 `AGENTS.md` / `README.md` — 项目级文档

Agent 工作边界：**启动在根目录，工作在 `mashang_workspace/`**。

## 项目定位

mashang-service 是一个**汽车业务数据分析项目**，包含以下分支 / 模块：

| 分支 | 目录 | 定位 |
|------|------|------|
| **Runtime (legacy)** | `mashang_runtime/` | Legacy / frozen 旧 Runtime 层；当前不作为日常活跃开发目录 |
| **Unified Research Runtime** | `mashang_runtime_v2/` | 统一研究 Runtime（编排层）：调用 workspace 确定性业务分析能力 + 长期编排 Research Applications（编排演进中） |
| **Workspace** | `mashang_workspace/` | **Daily Business Analytics Workspace** —— 日常业务分析工具箱（research → runtime → eval） |
| **Shared** | `shared/` | Semantic Foundation —— 共享 operator/schema 层（非默认工作区） |
| **Base Capabilities** | `capabilities/` | 领域无关基础能力层（OCR/Search/Notify 等），与日常业务分析能力平级，供 workspace / runtime_v2 / Research Application 复用 |
| **Research Applications** | `research_apps/`（MIIT / auto_launch / nev_apeal，未来 p4/5） | 独立研究型子项目（研究单元：有自己 state/engine/contracts/gate/artifacts；仅归类不共享；runtime_v2 编排目标） |

**共享底座**：
- `dataset/` — 原始数据
- `.env` — 环境变量
- `.venv/` — Python 虚拟环境
- `requirements.txt` — 依赖
- `shared/` — 共享 operator/schema

**核心数据集**：
- `dataset/order_data.parquet` — 订单主表（含锁单、交付、开票、退订等时间戳）
- `dataset/assign_data.csv` — 下发线索表（含渠道拆解、7/30日转化）
- `dataset/config_attribute.parquet` — 选配属性表（配置渗透率分析）

## 工作原则

1. **新分析能力**：优先进入 `mashang_workspace/`
2. **Runtime 分层**：`mashang_runtime/` 是 legacy / frozen 旧 Runtime 层，不作为日常活跃开发目录。`mashang_runtime_v2/` 是 **Unified Research Runtime（编排层）**，消费 workspace 已治理能力 + 长期编排 Research Applications（MIIT/auto_launch/nev_apeal）。
3. **不要移动 `dataset/` `.env` `.venv/`**
4. **不要在 runtime 中做临时分析**
5. **不要在 workspace 中引入破坏 runtime 的改动**
6. **`mashang_workspace` 是日常唯一主工作区**
7. **OpenCode 应优先读取 `mashang_workspace/AGENTS.md`**
8. **不要在根目录创建新的 `docs/scripts/eval/tests/utils`**
9. **新分析能力优先沉淀到 `mashang_workspace/runtime_scripts/ + research_scripts/ + docs/ + eval/`**
10. **验证范围必须与改动范围匹配**：改动后先 `make verify-scope` 解析本次改动的最小验证范围，再 `make verify` 执行。**scope 外失败不算本次回归**；扩大范围必须显式（`make verify-all` / `--include`），不得把「充分验证」等价成「跑全量 pytest / `make ci`」。契约见 `.opencode/verification/README.md`。
11. **能力产品化路径**：workspace 中验证稳定的能力先成为 `runtime_scripts`，供 `mashang_runtime_v2`（Unified Research Runtime）确定性调度；不要绕过 workspace 直接在 runtime_v2 中开发探索性能力，也不把业务分析代码复制进 runtime_v2 或 legacy runtime。
12. **`shared/` 边界**：共享 operator/schema 层，不应随意修改。如修改需说明影响范围，并同步相关测试。
13. **MCP 边界**：MCP 能力由根目录统一提供（`.opencode/` / `opencode.jsonc`），workspace 只消费能力。不得将本地 profile、cookies、API key、incoming 原始数据等提交进仓库。
14. **`capabilities/` 边界**：Base Capabilities 是领域无关基础能力层。新基础能力先以 `capabilities/ocr/` 为样板归位并自描述（接口 + provider + mock + tests + 消费方记录）；不要在 capabilities/ 中写入业务规则或领域解析逻辑。OCR 已从历史根 `ocr/` 迁移至此（namespace `capabilities.ocr`）。
15. **能力引用口径**：领域无关原语（OCR/检索/抓取/渲染/通知等）若未来复用于多个上层，优先沉淀到 `capabilities/`，而非内嵌在各 Research Application / 模块中复制实现。

其余原则详见 `mashang_workspace/AGENTS.md`。

## 业务分析工作原则

1. **优先阅读 docs**：`mashang_workspace/docs/` 目录下的文档是首要参考资料，包含业务术语、指标口径、车型映射、时间规则、分析范式、追问规则。
2. **优先复用脚本**：`mashang_workspace/runtime_scripts/`（runtime）、`research_scripts/`（research）、`utility_scripts/`（utility）已有脚本，新需求优先基于现有脚本扩展。**根目录不再有 `scripts/`。**
3. **不要随意修改原始数据**：`dataset/` 下的 CSV/Parquet 是原始数据，分析应使用副本或只读方式。

**上市时间必须从业务定义读取**：涉及"上市以来"的时间范围，必须使用 `shared/schema/business_definition.json` 中 `time_periods.{series}.end` 字段，不得从数据中取 `lock_time` 最小值推断。脚本优先使用 `--since-launch` 参数，临时分析使用 `mashang_workspace/utils/business.py` 的 `get_launch_date()`。
4. **不要编造数据**：在数据无法支撑结论时，明确说明"无数据/数据不足"。
5. **所有分析结果必须说明来源**：包括数据源、过滤条件、时间窗口、指标口径。
6. **临时代码放 `scratch/` 或 `outputs/`**，稳定脚本再沉淀到 `mashang_workspace/{runtime_scripts,research_scripts,utility_scripts}/`。
7. **高频能力先在 workspace 内沉淀**：高频分析路径先沉淀到 `mashang_workspace/runtime_scripts/`，供 `mashang_runtime_v2` 确定性调度；旧 `mashang_runtime/` 不作为回流目标，业务代码不复制进 runtime_v2。
8. **回答数据问题前，先看 `docs/data_dictionary.md` 和 `docs/metric_definitions.md`**，确认字段名和口径。
9. **对标准分析问题，优先调用 `mashang_workspace/{runtime_scripts,research_scripts,utility_scripts}/` 下已有脚本**，不要重复造轮子。
10. **如果脚本缺少参数，先小范围补充 CLI 参数，不要重写脚本**。
11. **如果临时分析重复出现 2 次以上，再沉淀为 workspace 稳定脚本**。
12. **所有脚本在 `--format json` 时输出标准 Result Contract**，包含 scope/result/followup_context。
13. **分析结果可通过 `mashang_workspace/eval/run_numeric_eval.py` 做结构校验和非负校验**。

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
python mashang_workspace/utility_scripts/data_dictionary.py              # 终端输出
python mashang_workspace/utility_scripts/data_dictionary.py --format csv # CSV 输出
python mashang_workspace/utility_scripts/data_dictionary.py --format json # JSON 输出
```

### Smoke Test

```bash
pytest mashang_workspace/tests/scripts -q             # 运行所有脚本 smoke test
python mashang_workspace/tests/scripts/test_script_help.py  # 验证 --help
```

### Follow-up Eval Cases

多轮追问测试用例在 `mashang_workspace/eval/cases/followup_cases.json`，覆盖:
- 锁单分车型 → 追问城市分布 (时间继承 + 代指消解)
- LS6 增程/纯电 → 追问改时间窗口 (时间替换)
- LS8 分车型 → 追问加过滤条件 (条件追加)
- 分城市 → 追问改分车型 (维度切换)
- 预测锁单 → 追问释放曲线 (分析类型切换)

## Phase 3: Follow-up Runner & Workflow Validation

### Follow-up Eval Runner

```bash
python mashang_workspace/eval/run_followup_eval.py                     # dry-run 模式 (默认)
python mashang_workspace/eval/run_followup_eval.py --format json       # JSON 输出
python mashang_workspace/eval/run_followup_eval.py --execute           # 真实执行
python mashang_workspace/eval/run_followup_eval.py --as-of-date 2026-06-11  # 指定基准日期
```

Runner 功能:
1. 读取 `mashang_workspace/eval/cases/followup_cases.json`
2. 逐轮解析 expected_context → 推荐脚本 + CLI 参数
3. 多轮上下文继承 (时间/指标/车型/筛选条件)
4. Symbolic time_window 解析为真实日期
5. dry-run (默认) 或 execute 模式

### Context → Script 映射规则

| expected_context | 脚本 |
|-----------------|------|
| lock_count + group_by=model/series | `mashang_workspace/runtime_scripts/lock_by_model.py` |
| lock_count + group_by=city | `mashang_workspace/runtime_scripts/lock_city_distribution.py` |
| lock_count (无分组) | `mashang_workspace/runtime_scripts/daily_lock_count.py` |
| lock_forecast/cohort_forecast | `mashang_workspace/research_scripts/cohort_forecast.py` |
| release_curve | `mashang_workspace/research_scripts/release_curve_analysis.py` |
| voc_theme/jtbd_theme | `mashang_workspace/utility_scripts/voc_theme_analysis.py` |

详见 `mashang_workspace/docs/followup_runner_rules.md`。

### Eval Tests

```bash
pytest mashang_workspace/tests/eval -q               # 运行 eval 测试
pytest mashang_workspace/tests -q                    # 运行所有 workspace 测试
```

## Phase 4: Natural Language Context Parser

### Context Parser

`mashang_workspace/eval/context_parser.py` 将用户自然语言解析为结构化 context，支持两种模式：

```bash
# 单轮解析 CLI
python mashang_workspace/eval/parse_context_cli.py "昨天锁单数分车型"
python mashang_workspace/eval/parse_context_cli.py "那最近 7 天呢？" --previous-context '{"metric":"lock_count_share","time_window":"last_15_days","series":"LS6","group_by":"energy_type"}'

# Runner 的 parse-text 模式
python mashang_workspace/eval/run_followup_eval.py --parse-text
python mashang_workspace/eval/run_followup_eval.py --parse-text --format json --output outputs/tables/parse_result.json
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
python mashang_workspace/eval/run_followup_eval.py --parse-text --as-of-date 2026-06-11
```

目标: context match rate >= 80%。当前: **92.9%** (13/14 turns)。

详见 `mashang_workspace/docs/context_parser_rules.md` 和 `mashang_workspace/eval/context_parser.py`。

## Phase 5: Execution Result Contract & Numeric Eval

### Result Contract

所有核心脚本支持 `--format json` 时输出统一 Result Contract：

```json
{
  "status": "success | partial_success | error",
  "script": "mashang_workspace/runtime_scripts/lock_by_model.py",
  "scope": { "data_source": "...", "time_window": {...}, "filters": {...}, "metric_definition": "..." },
  "result": { "summary": "...", "metrics": {...}, "dimensions": [...], "tables": [...] },
  "artifacts": { "csv": "...", "json": "..." },
  "followup_context": { "metric": "...", "top_entities": [...], "available_dimensions": [...] },
  "warnings": [],
  "errors": []
}
```

已支持 Contract 的脚本 (6个):
- `mashang_workspace/runtime_scripts/daily_lock_count.py`
- `mashang_workspace/runtime_scripts/lock_by_model.py`
- `mashang_workspace/runtime_scripts/lock_city_distribution.py`
- `mashang_workspace/research_scripts/cohort_forecast.py`
- `mashang_workspace/runtime_scripts/assign_conversion_analysis.py`
- `mashang_workspace/runtime_scripts/attribute_penetration_report.py`

详见 `mashang_workspace/docs/result_contract.md`。

### Numeric Eval

```bash
python mashang_workspace/eval/run_numeric_eval.py                              # 执行并校验结果
python mashang_workspace/eval/run_numeric_eval.py --format json                # JSON 输出
python mashang_workspace/eval/run_numeric_eval.py --cases mashang_workspace/eval/cases/numeric_cases.json
```

当前: 5/5 cases passing (100%)。

### Result Reference

context_parser 支持解析 "这 75 个" → 自动继承上一轮 top_entities 中的字段值。

```bash
python mashang_workspace/eval/parse_context_cli.py "这 75 个锁单城市分布" --previous-context '{"series":"LS8","top_entities":[{"field":"series","value":"LS8","metrics":{"lock_count":75}}]}'
```

详见 `mashang_workspace/docs/context_parser_rules.md`。

## 追问处理规则

1. **时间继承**：用户追问中省略时间窗口时，优先继承上一轮的 `time.start` / `time.end`。
2. **指标继承**：用户追问中省略指标时，优先继承上一轮的 `metric` / `analysis_intent`。
3. **代指消解**：
   - "这 75 个" → 继承上一轮的过滤结果并作为新的过滤条件
   - "刚才那个车型" → 继承上一轮的 `filters.series` 或 `filters.product_name`
   - "昨天 LS8" → 继承 `series=LS8` + `time=昨天`
4. **上下文不足时**：先输出需要澄清的字段（时间、车型、指标），不要假设业务口径。
5. **口径一致**：同一次 session 内保持口径一致，除非用户主动要求变更。
6. **追问→脚本映射**：根据继承的上下文选择对应脚本并传参（详见 `mashang_workspace/docs/followup_runner_rules.md`）。

## 输出规范

- **简洁结论**：先给结论，再给关键数字
- **表格**：优先用 Markdown 表格呈现结构化结果
- **文件输出**：必要时生成 CSV/HTML/PNG 到 `outputs/` 目录
  - `outputs/tables/` — CSV/JSON 结构化数据
  - `outputs/reports/` — HTML/Markdown 报告
  - `outputs/charts/` — PNG/SVG/HTML 图表
- **口径说明**：每次输出附带数据来源、过滤条件、时间窗口
- **脚本路径**：如果通过 workspace 脚本执行，注明脚本路径（`mashang_workspace/{runtime_scripts,research_scripts,utility_scripts}/...`）

## 目录结构

```
mashang-service/
├── AGENTS.md              ← 本文件 (项目级 Agent 指南)
├── README.md              ← 项目主文档
├── .env                   ← 共享环境变量
├── .venv/                 ← 共享虚拟环境
├── dataset/               ← 共享原始数据
├── requirements.txt       ← 共享依赖
├── shared/        ← 共享 operator/schema（非默认工作区）
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
├── mashang_runtime_v2/     ← Unified Research Runtime（编排层）
│   └── README.md          ← Runtime V2 说明
│
├── capabilities/          ← Base Capabilities（领域无关原语：OCR/Search/Notify/Diagram/Feishu）
│
├── research_apps/         ← Research Applications（MIIT / auto_launch / nev_apeal）
│
└── mashang_workspace/     ← Daily Business Analytics Workspace（日常业务分析工具箱）
    ├── AGENTS.md          ← Workspace Agent 指南
    ├── README.md
    ├── docs/               ← 业务文档
    ├── runtime_scripts/    ← runtime tier（可被 runtime_v2 确定性调度）
    ├── research_scripts/   ← research tier（预测/回测/报告）
    ├── utility_scripts/    ← utility tier（DataOps/SyncOps/生成/检查）
    ├── eval/               ← Eval 测试框架
    ├── tests/              ← Smoke test (pytest)
    ├── utils/              ← 工具模块
    └── outputs/            ← 输出文件
        ├── reports/
        ├── charts/
        └── tables/
```

## Canonical Entry Map（入口与副作用分级）

同一能力存在多个入口时，以下为 canonical 入口；旧名作为兼容别名保留。新文档、新脚本、Agent 路由一律引用 canonical 名。

| 能力 | Canonical 入口 | 旧名 / 兼容别名 | 副作用等级 |
|------|----------------|-----------------|-----------|
| 数据集刷新 | `make data-refresh` | `dataset-update` | local write |
| 数据集校验 | `make data-validate` | `dataset-validate` | read-only |
| 每日观察预检 | `make observe-dry-run` | `daily-observation-dry-run` | read-only |
| 每日观察同步 | `make observe-sync` | `daily-observation-sync` | Feishu write（多维表 + 机器人） |
| 数据管道 | `make data-pipeline` | `daily-data-pipeline` | local + Feishu write |
| 数据管道预检 | `make data-pipeline-dry-run` | `daily-data-pipeline-dry-run` | read-only |
| 每日运营 | `make daily-ops` | — | local + Feishu write + 卡片 |
| 当前预售/上市监控 | `make sales-monitor` | `monitor` | Feishu card |
| 监控预检 | `make sales-monitor-dry-run` | `monitor-dry-run` | read-only |
| 数据更新+指定代际监控走廊 | `make monitor-sync SERIES=<GEN> [PHASE=launch\|presale] [DRY=1]` | `sales-monitor-sync` | local write（仅订单表）+ Feishu card |
| 指定代际预售小订快照 | `make presale-snapshot SERIES=<GEN>`（= `sales-monitor --force-phase --phase presale`） | — | Feishu card |
| 常驻调度 | `make sales-scheduler` | `scheduler` | 常驻 + local + Feishu |
| 预售累计订单对比报告 | `presale_cumulative_order_compare.py` | `l6_m2_presale_report.py`（shim） | local write（可选 Feishu docx） |

副作用等级定义：

- **read-only**：只读本地数据，可安全直接执行。
- **local write**：写本地 `dataset/` 或 `outputs/`。
- **Feishu write**：写飞书多维表 / 云文档。
- **Feishu card**：发送飞书群卡片消息。
- **常驻**：常驻进程，写日志并周期性触发上述副作用。

**推送类操作（Feishu card / Feishu write）执行前必须先 `--dry-run` 预览**，确认口径后再正式发送；stale 数据默认阻断正式推送，只有显式 `ALLOW_STALE=1` / `--allow-stale` 才可强制发送。

### 小订 / 预售 / 上市入口边界（勿混用）

- “小订监控 / 预售小订” 默认指**指定代际预售快照** → `make presale-snapshot SERIES=<GEN>`（底层 `presale_metrics_to_feishu.py` shim → `vehicle_sales_monitor --force-phase --phase presale`）。
- **唯一监控实现** = `runtime_scripts/vehicle_sales_monitor.py`：`sales-monitor`（按 active phase）与 `presale-snapshot`（`--force-phase` 忽略 phase）共用同一 compute/card，不再有独立预售实现。
- “当前预售/上市监控” 指**当前 active 代际的 phase 监控** → `make sales-monitor`（底层 `vehicle_sales_monitor.py`，带 freshness gate；**不刷新数据**）。
- “数据更新并同步 <代际> 上市/小订/预售监控”（**仅刷新订单表** → 计算 → 推送）→ `make monitor-sync SERIES=<GEN> PHASE=<launch|presale>`（`DRY=1` 预览；底层 `order_data_to_parquet.py` + `vehicle_sales_monitor.py`）。对应关系：上市监控→`PHASE=launch`，小订/预售监控→`PHASE=presale`。
- 指定代际已进入 `launch` 阶段时，`sales-monitor` / `monitor-sync` 会按 launch 口径监控，而 `presale-snapshot` 仍按该代际预售口径生成快照（用于上市日最终预售快照）。
- 发送指定代际快照时，输出必须标注：统计截止时间、预售窗口、当前所处阶段（presale/launch）。
- `make data-pipeline` / `daily-data-pipeline` **不含**销售监控；如需“数据更新 + 监控推送”一体执行：全量数据用 `make daily-ops`，仅订单表用 `make monitor-sync`。
- `monitor-sync` 仅刷新订单表（`order_data`），不等价于 `make data-refresh`（全量数据集）；需要全量刷新时改用 `make daily-ops` 或先 `make data-refresh`。

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
| 业务状态排查 | `make state-diagnosis` 或 `python mashang_workspace/runtime_scripts/current_state_diagnosis.py [--as-of YYYY-MM-DD]`(库存×待开票未退订×风险暴露;`AS_OF` 支持历史时点 PIT 重建,可选 `SERIES/FORMAT/OUTPUT`) | runtime |
| 门店→经销商主体画像 | `python mashang_workspace/runtime_scripts/store_dealer_profile.py 门店1 门店2`(返回 门店/经销商主体(Bloc)/大区/该主体门店数(在营)/城市分布 + 近期主理 + 近7日下发线索 + 近7日锁单及车系分布 + CM3留存小订，含主体内排名占比，无独立口径时回落关联车城店;`--status` 在营口径;`--as-of`/`--window-days`;`--format json/csv`) | runtime |
| 主理数据更新 | `python dataset/updater/store_daily_zhuli_to_csv.py [--with-roster]`(Tableau→`dataset/门店日报_主理_当月.csv`;`--with-roster` 另出 `dataset/主理信息表.csv`) | DataOps |
| 每日下发线索（by门店）更新 | `python dataset/updater/store_daily_leads_to_csv.py`(Tableau 165 门店级视图 → `dataset/store_daily_leads.csv`;**滚动窗口增量合并**,逐日扩长;`--dry-run`/`--rebuild`) | DataOps |
| 门店经营状况观察 | `python mashang_workspace/utility_scripts/store_operation_observation.py`(全门店 门店/门店类型/门店形态/近7日下发线索/CM3小订/小订线索比;默认仅保留有线索或小订的门店,`--include-relations` 额外纳入无数据快闪/慢闪并标关联门店;`--format csv` 落 `outputs/tables/store_operation_observation.csv`) | utility |
| 门店线索×小订四象限 | `python mashang_workspace/research_scripts/store_leads_intention_quadrant.py`(读观察 CSV → 四象限散点 HTML;高/低线索×高/低转化,中位数切分;`--color-by type/format/quadrant` 默认按门店分类着色;`--input`/`--top-label`;落 `outputs/reports/`) | research |
| 释放曲线 | `python mashang_workspace/research_scripts/release_curve_analysis.py` | research |
| 预测锁单 | `python mashang_workspace/research_scripts/cohort_forecast.py` | research |
| 回测 | `python mashang_workspace/research_scripts/lock_predict_backtest.py` | research |
| 同比分析 | `python mashang_workspace/research_scripts/quick_lock_ratio.py` | research |
| 预售累计订单跨代际对比 | `python mashang_workspace/research_scripts/presale_cumulative_order_compare.py --gens DM1 CM2 LS9 LS8 DM2 --as-of YYYY-MM-DD --format html`(通用预售固定框架:末位=主代际,其余为对标;默认当前 presale 代际;`--format terminal/json/html`;`--to-feishu` 额外产出飞书云文档,默认仅 HTML) | research |
| 预售累计订单跨代际对比（旧入口 shim） | `python mashang_workspace/research_scripts/l6_m2_presale_report.py` 已降为 **compatibility shim**（默认 DM2 + HTML，转调上面的通用脚本）；后续功能扩展一律走通用入口，勿再围绕旧脚本开发 | research |
| 预售小订转化漏斗 | `python mashang_workspace/runtime_scripts/presale_intention_funnel.py --series CM3 --as-of YYYY-MM-DD`(泛化任意代际;`--series A B C` 多代际对比;`--list` 列可用代际;`--format terminal/json/csv`;`make presale-funnel SERIES=CM3`;固定链路=series_group_logic→预售窗口→小订池→退订/留存/转大定/锁单) | runtime |
| 锁单月度预估 | `make lock-forecast` 或 `python mashang_workspace/research_scripts/structured_business_forecast.py --as-of YYYY-MM-DD --target-month YYYY-MM [--prior-strength N]` | research |
| 开票月度预估 | `make invoice-forecast` 或 `python mashang_workspace/research_scripts/invoice_monthly_forecast.py --as-of YYYY-MM-DD --target-month YYYY-MM --lock-regime mode` | research |
| 锁单归因分析 | `make lock-attribution START=2026-01-01 END=2026-08-31 HTML=1`(单样本;可选 `SERIES/CHANNEL`) | make |
| 锁单归因对比 | `make lock-attribution-compare START=2024-01-01 END=2024-08-01 START_B=2026-01-01 END_B=2026-08-01 HTML=1`(两任意样本对比,差异高亮报告;可选 `LABEL/LABEL_B/SERIES_B/CHANNEL_B`) | make |
| Auto Launch 搜索 | `PYTHONPATH=research_apps python -m auto_launch.cli search --request "看看极氪最近 7 天都有什么动作"` | service |
| Auto Launch Daily 摄入 | `PYTHONPATH=research_apps python -m auto_launch.cli daily --input <file>` | service |
| Auto Launch 品牌日报 | `PYTHONPATH=research_apps python -m auto_launch.cli report --type brand-daily --brand 智己` | service |
| Auto Launch 完整日更 | `PYTHONPATH=research_apps python -m auto_launch.cli run-day --brand 智己` | service |
| Auto Launch 测试 | `pytest research_apps/auto_launch/tests/ -q` | service |
| VOC 分析 | `python mashang_workspace/utility_scripts/voc_theme_analysis.py` | utility |
| 数据字典 | `python mashang_workspace/utility_scripts/data_dictionary.py` | utility |
| 分组重叠审计 | `python mashang_workspace/utility_scripts/audit_series_group_overlap.py [--json] [--strict]` | utility |
| 每日观察 | `python mashang_workspace/utility_scripts/skills_order_observation_daily.py` | utility |
| 达成率预警 | `python mashang_workspace/utility_scripts/skills_attainment_rate_alert.py --days 10` | utility |
| 生成 Eval | `python mashang_workspace/utility_scripts/generate_eval_cases.py` | utility |
| 数据更新并同步 | `make data-pipeline`（写操作；旧名 `daily-data-pipeline`；办公网不可达时自动回退移动链路，可 `MOBILE=1` 强制） | DataOps |
| 数据更新 + 监控推送 | `make daily-ops`（写操作：data-pipeline + sales-monitor） | DataOps |
| 预检数据 | `make data-pipeline-dry-run`（只读；旧名 `daily-data-pipeline-dry-run`） | DataOps |
| 当前预售/上市监控 | `make sales-monitor`（当前 active 代际 + phase；旧名 `monitor`；先 `make sales-monitor-dry-run` 预览） | monitor |
| 数据更新+指定代际监控走廊 | `make monitor-sync SERIES=CM3 PHASE=launch|presale [DRY=1]`（仅刷新订单表 → 计算 → 推送/dry-run；旧名 `sales-monitor-sync`） | monitor |
| 指定代际小订快照 | `make presale-snapshot SERIES=CM3`（先 `DRY=1` 预览；底层 `presale_metrics_to_feishu.py --series CM3`） | monitor |
| 常驻调度 | `make sales-scheduler`（旧名 `scheduler`） | monitor |
| 解析验证范围 | `make verify-scope`（按改动解析最小验证范围） | harness |
| 执行验证 | `make verify`（仅 scope 内；baseline 不算回归） | harness |
| 扩大验证 | `make verify-all`（显式全量） | harness |
| 运行 Runtime Eval | `python mashang_workspace/eval/run_runtime_eval.py` |
| 运行 Follow-up Eval | `python mashang_workspace/eval/run_followup_eval.py` |
| 运行 Numeric Eval | `python mashang_workspace/eval/run_numeric_eval.py` |
| 解析自然语言 | `python mashang_workspace/eval/parse_context_cli.py "昨天锁单数分车型"` |
| Smoke Test | `pytest mashang_workspace/tests -q` |
| 根数据集构建测试 | `pytest tests/ -q`（根 `tests/`，TP&MIX-ways 构建契约） |
