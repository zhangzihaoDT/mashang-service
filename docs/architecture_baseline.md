# Architecture Baseline — Service 边界封板

> 记录日期: 2026-10-07
> 架构 tag: `arch-service-boundary-v1`
> 目的: 冻结「mashang-service 只保留业务能力 + 确定性 Job Contract」这一架构边界。

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
├── mashang_workspace/      # 业务能力（business / research / utility tier）
│   └── business_scripts/   # 稳定运行入口
├── research_apps/          # Research Applications（MIIT / auto_launch / nev_apeal / …）
├── jobs/                   # 确定性执行契约（Research Application job；Hub/Worker 调用）
├── shared/                 # 共享 operator / schema / loader
├── capabilities/           # 领域无关基础能力（OCR / Search / Notify / Diagram / Feishu）
└── dataset/                # 共享原始数据
```

## 2. 本次封板包含的变更

- **退役 legacy Runtime**：删除 `mashang_runtime/`、根 `main.py` / `feishu_bot.py` shim、旧路径注入与相关测试；`shared/operators/province_topk.py` 去除对旧 `tools` 的隐藏依赖。
- **退役 NL 问数 Runtime**：删除 `mashang_runtime_v2/`（NL routing / session / rendering / CLI / eval），`jobs/` 承接确定性 job 编排。
- **新增 `jobs/`**：`jobs/adapter.py`（`load_jobs` / `validate_params` / `run_job`）、`jobs/cli.py`、`jobs/config/jobs_config.json`、`jobs/tests/`。
- **Daily pipeline 边界收敛**：`data-pipeline` 只刷新订单 + 下发线索；`allupdate`/`updateall` 全量更新；`sales_scheduler` 09:00 同用 daily scope。拆出 `assign_data_to_csv.py` / `test_drive_data_to_csv.py`，Tableau 导出能力集中到 `dataset/updater/tableau_export.py`。
- **命名清理（Phase 4）**：`mashang_workspace/runtime_scripts/` → `business_scripts/`；`RUNTIME_SCRIPTS_DIR` → `BUSINESS_SCRIPTS_DIR`；tier `runtime` → `business`；registry 路径与 promotion 字段同步；验证 scope rule `runtime-script` → `business-script`。

## 3. 验证基线

封板时以下验证全部通过（`make verify`）：

```text
eval.ci, eval.core, harness.selftest, jobs.tests,
pytest.eval, pytest.scripts, pytest.workspace,
pytest:capabilities/notify/tests,
pytest:mashang_workspace/tests/{research_scripts/test_backlog_pit,test_daily_data_pipeline,
  test_repurchase_operator,test_script_tier_physicalization,test_shared_operators_schema,
  test_vehicle_sales_monitor}.py,
smoke: business_scripts/*（全部）, eval/run_eval.py, eval/run_followup_eval.py,
  research_scripts/*（锁单归因对比等）, utility_scripts/*, research_apps/product_expert
```

复现：

```bash
make verify-scope   # 解析最小验证范围
make verify         # 执行 scope 内验证
make ci             # CI 门禁（eval.ci + 数据无关测试）
```

## 4. 关键入口

```bash
make jobs-list                                   # 列出 Research Application job
make jobs-run JOB=nev_apeal_production_golden    # 执行 job
make data-pipeline                               # Daily：订单 + 下发线索 → 观察同步
make updateall                                   # 全量更新 + 校验（别名 allupdate）
make sales-monitor-dry-run                       # 预售/上市监控预览
```

## 5. 非目标（本基线不处理）

- 历史归档文档、`mashang_workspace/outputs/**` 生成物、报告内模型命名（如 “V0.3 Runtime”）中的旧措辞保留；目标是不再存在 **service 内 active Runtime 组件**，而非机械消灭英文单词。
