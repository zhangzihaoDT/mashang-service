# Regression Notes — Eval 回归测试记录

> 本文件记录 Runtime Eval / Follow-up Eval 回归测试的状态和注意事项。

## Phase 1: Runtime Eval

- Eval Runner: `eval/run_runtime_eval.py`
- 用例文件: `eval/runtime_cases.jsonl` (自动生成)
- 报告输出: `eval/eval_report.json`
- 用例生成: `utility_scripts/generate_eval_cases.py`

### 运行方式

```bash
# 生成测试用例
python scripts/generate_eval_cases.py

# 运行回归测试
python eval/run_runtime_eval.py

# 带参数运行
python eval/run_runtime_eval.py --limit 10 --verbose
python eval/run_runtime_eval.py --cases eval/runtime_cases.jsonl --report eval/eval_report.json
```

### 检查项

| 检查项 | 说明 |
|--------|------|
| `no_forbidden_exit_reason` | 禁止异常退出 |
| `intent_match` | intent 分类一致性 |
| `contract_match` | Evidence Contract 匹配 |
| `min_structured_blocks` | 最小 structured block 数量 |
| `fact_types_any` | 至少命中一种 fact_type |

### 已知问题

1. 当前 Eval 不校验回答中的具体数值/明细
2. 仅校验 Runtime 行为与证据产出
3. 用例从 `logs/query_log.jsonl` 自动生成后需人工审查

## Phase 2: Follow-up Eval Cases

- 用例文件: `eval/cases/followup_cases.json`
- 覆盖 7 个多轮追问场景

| Case ID | 场景 | 追问题型 |
|---------|------|----------|
| `followup_lock_model_city_001` | 锁单分车型 → 城市分布 | 时间+series+数量代指继承 |
| `followup_ls6_energy_001` | LS6 增程/纯电 → 改时间 | 时间替换，其它继承 |
| `followup_ls8_battery_001` | LS8 分车型 → 加过滤 | 条件追加 |
| `followup_city_then_model_001` | 分城市 → 改分车型 | 维度切换 |
| `followup_forecast_then_release_001` | 预测锁单 → 释放曲线 | 分析类型切换 |
| `followup_multiple_city_refine_001` | 多城市 → 只查上海 | 过滤追加 |
| `followup_energy_to_model_001` | 增程占比 → 看五座 | 引擎不变，条件追加 |

## Phase 3: Follow-up Runner

- Runner: `eval/run_followup_eval.py`
- 规则文档: `docs/followup_runner_rules.md`

### 功能

1. 读取 `eval/cases/followup_cases.json`
2. 逐轮解析 expected_context → 推荐脚本 + CLI 参数
3. 多轮上下文继承 (时间/指标/车型/筛选条件)
4. Symbolic time_window 解析为真实日期
5. dry-run (默认) 或 execute 模式

### 运行方式

```bash
python eval/run_followup_eval.py                            # dry-run
python eval/run_followup_eval.py --format json              # JSON 输出
python eval/run_followup_eval.py --execute                  # 真实执行
python eval/run_followup_eval.py --as-of-date 2026-06-11    # 指定基准日期
```

### Runner 测试

```bash
pytest tests/eval -q                                        # 运行 runner 单元测试
```

测试覆盖:
1. `--help` 正常输出
2. 能读取 followup_cases.json
3. JSON 输出格式正确
4. JSON 写入文件
5. 上下文继承 (followup_ls6_energy_001)
6. 脚本推荐 (followup_lock_model_city_001)
7. Dry-run 不执行
8. 缺失 context 检测

## Phase 4: Context Parser

- Parser: `eval/context_parser.py`
- CLI: `eval/parse_context_cli.py`
- 规则文档: `docs/context_parser_rules.md`

### Context Match Rate

```bash
python eval/run_followup_eval.py --parse-text --as-of-date 2026-06-11
```

目标: >= 80%
当前: **92.9%** (13/14 turns)

### Result Reference

context_parser 支持从文本解析结果引用:
- "这 75 个" → 匹配 followup_context.top_entities
- "刚才那个车型" → 取 top_entities[0]

## Phase 5: Result Contract & Numeric Eval

- Contract 模块: `utils/result_contract.py`
- 规范文档: `docs/result_contract.md`
- Numeric Runner: `eval/run_numeric_eval.py`
- Numeric Cases: `eval/cases/numeric_cases.json`

### Result Contract

统一脚本执行结果协议，包含:
- `status`: success / partial_success / error
- `scope`: 数据源、时间、过滤、口径
- `result`: summary、metrics、dimensions、tables
- `artifacts`: 生成文件路径
- `followup_context`: 下一轮可继承的信息（含 top_entities）
- `warnings / errors`

已支持 Contract 的脚本 (6个):
- `runtime_scripts/daily_lock_count.py` ✅
- `runtime_scripts/lock_by_model.py` ✅
- `runtime_scripts/lock_city_distribution.py` ✅
- `research_scripts/cohort_forecast.py` ✅ (partial_success)
- `runtime_scripts/assign_conversion_analysis.py` ✅
- `runtime_scripts/attribute_penetration_report.py` ✅

### Numeric Eval

```bash
python eval/run_numeric_eval.py
```

验证内容:
1. status 一致性
2. required_fields 存在性
3. metrics 数值条件 (≥0 等)
4. errors 为空

当前结果: 5/5 (100%)

### result_reference

context_parser 支持从文本解析结果引用:
- "这 75 个" → 匹配 followup_context.top_entities
- "刚才那个车型" → 取 top_entities[0]

### Runner execute 增强

- 自动注入 `--format json`
- 尝试解析 contract
- 从 contract.followup_context 提取下一轮信息

## 后续计划

- 增加数值校验 (expected vs actual)
- 统一 three runners (runtime / followup / numeric) 为一个 unified eval runner
- 引入 LLM hybrid parser 处理复杂自然语言
- 将 scripts smoke test + eval test 加入 CI
- 将 parser + runner + contract 接入 OpenCode 或 Mashang Runtime

## Phase 11: Capability Registry & Promotion Gate

- Registry: `mashang_workspace/registry/capability_registry.json`
- Audit Runner: `mashang_workspace/eval/run_capability_audit.py`
- Rules: `mashang_workspace/docs/promotion_rules.md`
- Registry Doc: `mashang_workspace/docs/capability_registry.md`

### Capability Registry

12 个已注册能力:

| Tier | 数量 | 示例 |
|:----:|:----:|------|
| runtime | 6 | daily_lock_count, lock_by_model, lock_city_distribution, assign_conversion, attribute_penetration, atp_price |
| research | 3 | cohort_forecast, lock_predict_backtest, release_curve_analysis |
| utility | 2 | data_dictionary, voc_theme_analysis |
| legacy | 1 | skills_atp_price |

### Promotion Rules

- research→runtime: 10 条条件（CLI + Contract + Numeric + Gate + Docs + 口径）
- runtime→mashang_runtime: 10 条条件（价值 + 稳定性 + Gate + 架构）
- utility/legacy: 需先包装再晋级

### Capability Audit

```bash
python mashang_workspace/eval/run_capability_audit.py
```

覆盖 9 项检查: script_exists, tier_valid, status_valid, runtime_has_contract/numeric/gate, research/legacy_not_auto, promotion_fields.

## Phase 13 Step 2.3: Remove Legacy Workspace Scripts Pool

- `mashang_workspace/scripts/` 已删除
- 脚本已物理分层到 `runtime_scripts/` / `research_scripts/` / `utility_scripts/` / `legacy_scripts/`
- `paths.py` 中 `SCRIPTS_DIR` 已移除
- `skills_order_observation_daily.py` 位于 `utility_scripts/`，DataOps/SyncOps，需要 `--dry-run` 安全模式
- Runtime V2 只调度 `runtime_scripts/`
- 所有代码路径不再引用 `mashang_workspace/scripts/`
- `run_eval.py` output path 双前缀问题已修复（resolve_output_path）
- `outputs/tables/` 中引用旧 `scripts/` 路径的缓存已清理
- `legacy_scripts/README.md` 明确其 frozen reference 定位
- `daily-sync-dry-run` 已废弃，改用 `daily-observation-dry-run`
- `Makefile` 新增 dataset-update / dataset-validate / daily-observation-dry-run / daily-observation-sync / daily-data-pipeline / daily-data-pipeline-dry-run
- `utility_scripts/dataset_validate.py` 新增轻量校验脚本
- `docs/daily_data_pipeline.md` 新增完整 daily data pipeline 文档
- Makefile 所有 `python` 命令统一为 `$(PYTHON)`（`PYTHON ?= .venv/bin/python`）
- `PYTHON` 变量可通过 `PYTHON=python3 make target` 覆盖
- 自然语言入口统一为"数据更新并同步"，非"今天的数据更新并同步"
- `daily-sync-dry-run` 已废弃为别名，指向 `daily-observation-dry-run`
- `make test` 新增 11 个 Makefile PYTHON / wording 检查
