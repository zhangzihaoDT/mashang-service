# Plans · 固定流程与常驻任务

DSH-superagent macOS App 的业务目录对接入口。机器读取 [catalog.json](catalog.json)，人工查阅本页；当前仅完成 Service 侧归类，尚未接入 App。

此目录集中可执行入口，复用现有 Make target 和业务脚本。数据更新实现仍在 `dataset/updater/`，业务计算仍在 `business_scripts/`，调度和同步仍在 `utility_scripts/`；不复制实现，也不改变现有 Make 命令。脚本可从任意目录通过绝对路径调用，会自动切回仓库根目录，以 `make -j1` 保持上游依赖串行执行。

| 入口 | 进程 | 范围 | 副作用 |
|---|---|---|---|
| [scheduler.sh](scheduler.sh) | **常驻** | 08:50 每日管道+监控；关键日 20–23 点整刷新订单+监控（按当前配置） | 本地数据、飞书表格和消息 |
| [daily_pipeline.sh](daily_pipeline.sh) | 单次 | 订单+下发线索→校验→每日观察同步 | 本地数据、飞书表格和消息 |
| [full_data_update.sh](full_data_update.sh) | 单次 | 全量更新+校验，含试驾、锁单归因 | 本地数据 |
| [daily_ops.sh](daily_ops.sh) | 单次 | Daily pipeline→销售监控 | 本地数据、飞书表格和消息 |
| [sales_monitor.sh](sales_monitor.sh) | 单次 | 当前 active 代际预售/上市监控，不刷新 | 飞书卡片 |
| [monitor_sync.sh](monitor_sync.sh) | 单次 | 仅刷新订单→指定代际监控 | 本地数据、飞书卡片 |
| [presale_snapshot.sh](presale_snapshot.sh) | 单次 | 指定代际固定预售口径快照，不刷新 | 飞书卡片 |

## 常用调用

```bash
# 仓库根目录；参数遵循已有 Make 接口
bash workspace/plans/full_data_update.sh
bash workspace/plans/daily_pipeline.sh
bash workspace/plans/scheduler.sh SERIES=CM3
bash workspace/plans/monitor_sync.sh SERIES=CM3 PHASE=launch DRY=1
bash workspace/plans/presale_snapshot.sh SERIES=CM3 DRY=1
```

推送前先按 `catalog.json` 的 `preview_argv` 预览并核对口径，再调用正式入口。参数以 `KEY=value` 追加到 argv；App 应按 `parameters` 白名单构造参数，不能把用户文本拼接成 shell 命令。`null` 代表没有等价的完整流程预检，不代表可跳过其中推送步骤的预览：

- Daily pipeline：`make -j1 data-pipeline-dry-run`，只检查现有数据和每日观察，不刷新。
- 当前阶段监控：`make -j1 sales-monitor-dry-run SERIES=CM3`。
- 指定代际监控：`make -j1 monitor-sync SERIES=CM3 PHASE=launch DRY=1`。**仍会刷新并写订单数据**。
- 预售快照：`make -j1 presale-snapshot SERIES=CM3 DRY=1`。
- Scheduler / daily-ops：分别预览每日观察和销售监控；Scheduler 自身 `--once --dry-run` 只打印订单刷新+监控命令，不预览整条每日管道，也不计算真实卡片。
- 全量更新没有等价完整 dry-run；`make -j1 data-validate` 仅检查现有数据。

## App 对接约定

- `id` 是稳定任务标识；`argv` 相对仓库根目录解析，执行时 cwd 设置为该根目录。Python 环境沿用根 Makefile 默认 `.venv/bin/python`。
- `process_type=daemon` 只有 Scheduler；其余为单次流程，是否配置周期由 App 决定。全量更新当前没有内置定时计划。
- 时间为北京时间，现有 Scheduler 使用机器本地时间；部署机器需设置 `Asia/Shanghai`。
- Scheduler 的 Make 入口默认 `SERIES=CM3`；传 `SERIES=` 才恢复全部 active 代际。阶段和关键日来自 `shared/schema/business_definition.json`。
- App 托管 Scheduler 时保留子进程 stdout/stderr 并管理进程组停止；避免与已有 Scheduler 或 App 自己的同时间周期任务重复启动。现有脚本没有跨进程互斥和断电补跑保证。
- Scheduler 日志为根 `logs/scheduler/YYYY-MM-DD.log`。单次任务输出和退出码沿用原入口；这份目录清单不是 Hub Job Result Contract，也不新增统一结果协议。
- 正式发送仍受新鲜度门控；仅显式授权时传 `ALLOW_STALE=1`，不要将其设为 App 默认值。

更多数据范围与链路说明见 [每日数据管道](../../docs/数据获取/daily_data_pipeline.md)。
