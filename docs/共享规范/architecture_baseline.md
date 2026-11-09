# Architecture Baseline — Service 边界封板

> 记录日期: 2026-10-07
> 架构 tag: `arch-service-boundary-v1`
> 目的: 冻结「mashang-service 只保留业务能力 + 确定性 Job Contract」这一架构边界。

## 2026-11-05 工作区归并

当前工作区名称为 `workspace/`。业务文档统一在根 `docs/`，项目 Skills 统一在根 `.opencode/skills/`。Makefile、Job、Python 导入、能力注册表、CI 和验证范围配置使用新路径。业务产物随工作区位于 `workspace/outputs/`；服务级产物仍按根 `outputs/` 的既有入口维护。

DSH 仓库示例 profile 已同步新查询路径。部署前须将其干净 checkout 更新到包含本次迁移的 Service 版本，然后在同一次部署中同步生产 profile 的查询脚本和必读资料路径，并对新 Ticket 执行 Prepare 与只读查询验收。当前本机部署 checkout 是另一份旧版本工作副本，生产 profile 应与其代码版本配套。

| 查询声明 | 新路径 |
|---|---|
| 上市监控 | `workspace/business_scripts/vehicle_sales_monitor.py` |
| 工作区规则 | `workspace/AGENTS.md` |
| 数据字典 | `docs/共享规范/data_dictionary.md` |
| 字段定义 | `shared/schema/schema.md` |
| 指标定义 | `shared/schema/reference/metric_definitions.md` |

Hub Worker 的默认产物目录声明已加入 `workspace/outputs`。部署 Worker 新版本后，新路径报告可经原产物发现入口返回。原路径兼容项保留用于其他旧版本工作副本。

本轮迁移验证通过工作区 519 项测试、Job 契约、验证工具自测和 CI 评测；新路径 LS9 查询与每日锁单 Job 均实际执行通过。DSH 示例 profile 的 Prepare 契约测试以及 Hub Worker 的产物策略、解析器和工作区注册测试通过。

文件核对覆盖 901 个既有输出、scratch 和本地文件。迁移本身未改变这些文件内容；随后既有回归测试重生成了以下 9 个本地文件，其他 892 个文件内容一致。

- `workspace/outputs/reports/lock_predict_backtest.html`
- `workspace/outputs/monthly_market_report/2026-02/` 下的 `run_metadata.json`、`query_results.xlsx`、`query_results.json`、`report_draft.md`
- `workspace/outputs/monthly_market_report/2026-12/` 下的上述四个文件

以下章节记录此前的拆分基线。

## 1. 运行时边界

运行时系统不再是 service 内的 Python package，而是：

```text
mashang-hub    Hub（Control Plane） + Worker（Execution Gateway）
OpenCode       交互 / 编排
mashang-service  业务能力 + 确定性 Job Contract（本仓库）
```

service 侧目录职责：

```text
mashang-service/
├── workspace/      # 业务能力（business / research / utility tier）
│   └── business_scripts/   # 稳定运行入口
├── jobs/                   # 确定性执行契约（service job；Hub/Worker 调用）
├── shared/                 # 共享 operator / schema / loader
├── capabilities/           # 领域无关基础能力（OCR / Search / Notify / Diagram / Feishu）
└── dataset/                # 共享原始数据
```

## 2. 本次封板包含的变更

- **退役 legacy Runtime**：删除 `mashang_runtime/`、根 `main.py` / `feishu_bot.py` shim、旧路径注入与相关测试；`shared/operators/province_topk.py` 去除对旧 `tools` 的隐藏依赖。
- **退役 NL 问数 Runtime**：删除 `mashang_runtime_v2/`（NL routing / session / rendering / CLI / eval），`jobs/` 承接确定性 job 编排。
- **新增 `jobs/`**：`jobs/adapter.py`（`load_jobs` / `validate_params` / `run_job`）、`jobs/cli.py`、`jobs/config/jobs_config.json`、`jobs/tests/`。
- **Daily pipeline 边界收敛**：`data-pipeline` 只刷新订单 + 下发线索；`allupdate`/`updateall` 全量更新；`sales_scheduler` 09:00 同用 daily scope。拆出 `assign_data_to_csv.py` / `test_drive_data_to_csv.py`，Tableau 导出能力集中到 `dataset/updater/tableau_export.py`。
- **命名清理（Phase 4）**：`workspace/runtime_scripts/` → `business_scripts/`；`RUNTIME_SCRIPTS_DIR` → `BUSINESS_SCRIPTS_DIR`；tier `runtime` → `business`；registry 路径与 promotion 字段同步；验证 scope rule `runtime-script` → `business-script`。

## 3. 验证基线

封板时以下验证全部通过（`make verify`）：

```text
eval.ci, eval.core, harness.selftest, jobs.tests,
pytest.eval, pytest.scripts, pytest.workspace,
pytest:capabilities/notify/tests,
pytest:workspace/tests/{research_scripts/test_backlog_pit,test_daily_data_pipeline,
  test_repurchase_operator,test_script_tier_physicalization,test_shared_operators_schema,
  test_vehicle_sales_monitor}.py,
smoke: business_scripts/*（全部）, eval/run_eval.py, eval/run_followup_eval.py,
  research_scripts/*（锁单归因对比等）, utility_scripts/*
```

复现：

```bash
make verify-scope   # 解析最小验证范围
make verify         # 执行 scope 内验证
make ci             # CI 门禁（eval.ci + 数据无关测试）
```

## 4. 关键入口

```bash
make jobs-list                                   # 列出 service job
make jobs-run JOB=daily_lock_count JOB_PARAMS="--job-param date=2026-11-03"
make data-pipeline                               # Daily：订单 + 下发线索 → 观察同步
make updateall                                   # 全量更新 + 校验（别名 allupdate）
make sales-monitor-dry-run                       # 预售/上市监控预览
```

## 5. 非目标（本基线不处理）

- 历史归档文档、`workspace/outputs/**` 生成物、报告内模型命名（如 “V0.3 Runtime”）中的旧措辞保留；目标是不再存在 **service 内 active Runtime 组件**，而非机械消灭英文单词。
