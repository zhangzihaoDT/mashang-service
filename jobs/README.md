# jobs — 确定性执行契约层

Service 侧唯一的 **Research Application job 执行边界**。

```text
mashang-hub (Control Plane)  ──调度──▶  Worker (Execution Gateway)  ──调用──▶  jobs/ (确定性执行契约)
```

## 定位

- **只负责** job 的声明、参数校验与确定性执行，以及状态/摘要/artifact 契约。
- **不负责** 自然语言路由、多轮会话、答案渲染、UI/CLI 交互；这些由 Hub / Worker / OpenCode 承担。
- Research Application 的业务逻辑留在各项目目录（`research_apps/<app>/`），不复制进本目录。

## 结构

```text
jobs/
├── adapter.py              # execution contract：load_jobs / validate_params / run_job
├── cli.py                  # Worker/Hub 调用入口（--job / --job-param / --list）
├── config/jobs_config.json # 声明式 job 定义（argv 模板 / cwd / 参数白名单 / artifact）
└── tests/                  # hermetic 契约测试
```

## 使用

```bash
python -m jobs.cli --list
python -m jobs.cli --job nev_apeal_production_golden
python -m jobs.cli --job nev_apeal_research_state --job-param topic=topic_x
python -m jobs.cli --job nev_apeal_production_golden --format json
```

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
