# jobs — 确定性执行契约层

Service 侧唯一的 **确定性 job 执行边界**（当前承载 workspace 业务能力）。

```text
mashang-hub (Control Plane)  ──调度──▶  Worker (Execution Gateway)  ──调用──▶  jobs/ (确定性执行契约)
```

## 定位

- **只负责** job 的声明、参数校验与确定性执行，以及状态/摘要/artifact 契约。
- **不负责** 自然语言路由、多轮会话、答案渲染、UI/CLI 交互；这些由 Hub / Worker / OpenCode 承担。
- 业务逻辑留在各项目目录（当前为 `workspace/…`），不复制进本目录。

## 结构

```text
jobs/
├── adapter.py              # execution contract：load_jobs / validate_params / run_job
├── cli.py                  # Worker/Hub 调用入口（--job / --job-param / --list）
├── production.py           # 受控生产写入：固定 job、主 checkout 校验、锁、超时、data-status 核验
├── config/jobs_config.json # 声明式 job 定义（argv 模板 / cwd / 参数白名单 / artifact）
└── tests/                  # hermetic 契约测试
```

## 使用

```bash
python -m jobs.cli --list
python -m jobs.cli --job daily_lock_count --job-param date=2026-11-03
python -m jobs.cli --job data_refresh_daily --format json
python -m jobs.cli --job daily_lock_count --job-param date=2026-11-03 --format json
```

`data_refresh_daily` 是受控生产写入：只在主 checkout 执行
`make data-refresh-daily`，随后自动执行 `make data-status`，并比较刷新前后的
`order_data` / `assign_data` 状态。它拒绝 linked worktree、带执行锁和 30 分钟超时，
返回 success / no_new_data / failed / timeout / verification_failed / busy。

`data_refresh_tableau_hs` 通过 `make data-refresh-tableau-hs` 更新
`dataset/tableau-hs/` 的订单、选配、锁单归因和交付库存导出及对应 Parquet。
它复用主 checkout 校验、刷新前后状态核验，并与 `data_refresh_daily` 共用写入锁。
该 Job 无可传入参数，刷新超时为 60 分钟。

```bash
python -m jobs.cli --job data_refresh_tableau_hs --format json
```

单数据集刷新复用同一把写入锁，只比较所选数据集的刷新前后状态。例如只刷新配置：

```bash
python -m jobs.cli --job data_refresh_config_attribute --format json
```

可用单数据集 Job：`data_refresh_order_data`、`data_refresh_assign_data`、`data_refresh_config_attribute`、`data_refresh_lock_attribution`、`data_refresh_delivery_inventory`、`data_refresh_test_drive_data`。

## Execution Contract

`run_job(job_id, params)` 返回结构化结果：

| 字段 | 说明 |
|------|------|
| `status` | `ok` / `failed` / `error` |
| `returncode` | 子进程退出码 |
| `duration_s` | 执行耗时 |
| `command` / `cwd` | 实际执行命令与目录（无 shell 注入） |
| `params` | 通过白名单校验后的参数 |
| `summary_json` | `summary: json` 时解析的结构化摘要 |
| `artifacts` | 声明产物的存在性 / 大小 / 修改时间 |
| `error` | 失败原因（超时 / 非零退出 / 参数非法 / 未知 job） |

安全约束：

- argv 仅由 config 模板拼装；`{python}` / `{repo_root}` 与已声明参数是仅有的可替换 token。
- 参数经白名单校验（`date` / `pattern`），未知参数直接拒绝；用户文本不进入 shell。
- `cwd` 来自 config（相对仓库根解析）。

## 新增 job

在 `config/jobs_config.json` 的 `feature_jobs` 增加条目，声明 `argv_template`、`cwd`、
`params`（含类型/必填/pattern）、`summary`、`artifacts`、`timeout_seconds` 即可，
无需改动 adapter。

## LS8 内饰订单 Mix

配置刷新只写入并比较 `config_attribute`。Superagent 核验该 Job 后，通过固定的
`python -m jobs.ls8_mix` 入口在 Ticket 状态目录创建版本化只读副本并查询。
查询按 LS8 车系（含 LS8Neo）上市以来的留存锁单统计，动力沿用版本字典。
各动力分母包含该组所有去重订单，缺少内饰和内饰冲突单列，未知动力单独报告。
配置表没有业务时间列，结果分别报告文件更新时间和可匹配的最新锁单时间。

## 刷新后分析

Superagent 的 `refresh_snapshot` 组合操作按固定 Job 清单执行刷新，
通过 `jobs.snapshot` 核对生产运行记录，并将所需数据集复制到 Ticket 的版本化只读目录。
快照数据集来自 registry，查询输入以本次返回的文件路径为准。编排见
`.opencode/skills/refresh-and-analyze/SKILL.md`。原 LS8 组合入口保留到真实验收通过。

只读查询可直接接收 Superagent 返回的 `snapshot_path`，无需再次复制或刷新。例如从业务仓库根目录运行：

```bash
.venv/bin/python -m jobs.ls8_mix --snapshot "/absolute/path/to/snapshot.json"
```

其他算子可复用 `jobs.snapshot.read_snapshot_inputs` 从同一版本清单读取各自声明的数据集。
清单缺少所需数据集、文件路径越界或大小不符时拒绝查询。LS8 入口返回 Result Contract，
包含输入版本、业务截止时间、内饰覆盖时间、去重和分母校验以及查询耗时。

上市锁单监控沿用原有代际与锁单口径，也支持同一只读清单。该模式仅输出 JSON，无飞书通知：

```bash
.venv/bin/python -B workspace/business_scripts/vehicle_sales_monitor.py --snapshot "/absolute/path/to/snapshot.json" --series LS8Neo --phase launch --force-phase
```
