# Workspace · 汽车业务任务索引

下列命令都在 **mashang-service 仓库根目录**执行。示例日期、代际、门店按问题替换。查询先核对数据截止日；“上市以来”的起点取业务定义中的 `time_periods.{series}.end`。[字段说明](../shared/schema/schema.md) · [指标口径](../shared/schema/reference/metric_definitions.md) · [车型与上市日](../shared/schema/business_definition.json)

## 日常查询

| 业务问题 | 从根目录执行的示例 | 结果 |
|---|---|---|
| 指定日期锁了多少单？ | `make jobs-run JOB=daily_lock_count JOB_PARAMS="--job-param date=2026-11-03"` | Job 返回执行状态和业务摘要 |
| 当天锁单最多的是哪些车型？ | `.venv/bin/python workspace/business_scripts/lock_by_model.py --date 2026-11-03 --limit 5` | 终端列出前五车型 |
| 哪个经销商经营这家店？近期线索和锁单如何？ | `.venv/bin/python workspace/business_scripts/store_dealer_profile.py --store 遵义吾悦广场城市展厅` | 终端返回门店、经销商及经营指标 |
| 某日库存和待开票锁单情况如何？ | `make state-diagnosis AS_OF=2026-11-03 SERIES=LS8` | 按历史时点重建库存与风险暴露，输出到终端 |
| 某代际预售小订有多少留存、转大定或锁单？ | `make presale-funnel SERIES=CM3 AS_OF=2026-11-03` | 终端返回预售小订漏斗 |
| 查看指定代际的预售快照或当前阶段的监控卡 | `make presale-snapshot SERIES=CM3 DRY=1` 或 `make sales-monitor-dry-run` | 前者固定预售口径，后者按活跃代际和阶段预览；两者均使用已有订单数据，不发卡 |

跨代际预售对比使用 [累计订单对比脚本](research_scripts/presale_cumulative_order_compare.py)。其他常用入口包括[线索转化](business_scripts/assign_conversion_analysis.py)、[配置渗透率](business_scripts/attribute_penetration_report.py)、[ATP 月报](business_scripts/atp_price_report.py)和[上险数据使用指南](../docs/tp_and_mix_ways_usage.md)。

<a id="dsh-launch-monitor"></a>
## DSH 只读查询示例 · LS9 上市以来累计锁单

当工单询问累计锁单和其中的用户车锁单时，读取 Prepare 记录，在工单工作副本中使用已声明的 `officialQueries` 条目 `launch-monitor`。执行参数和结果字段以该工单的契约为准。

1. 代际取工单点名的 LS9，阶段固定为 `launch`，启用 `--force-phase`。将 Prepare 中订单快照的 `lock_time` 截止日期传给 `--as-of`。
2. 使用 [上市监控脚本](business_scripts/vehicle_sales_monitor.py) 的 `--dry-run --format json --output`，将结果写入工单唯一的临时 JSON 文件。
3. 从该文件读取结果。核对状态、错误、警告和筛选条件，在 `result.monitors` 中唯一匹配 LS9 和 launch；读取 `metrics.cumulative_lock_count` 与 `metrics.cumulative_user_car_lock_count`。两者应为非负整数，用户车数应小于或等于累计数。核对上市日与统计日期，答复时注明快照的实际截止时间。遇到空结果、匹配不唯一或口径冲突时按契约调查。

## 车型预售与上市 · 统一入口

专题入口已整理为 **一套业务时间口径、两类能力、四份独立研究报告与一项监控**。业务问题、完整 CLI、输出文件、SSOT 例外与推送风险见 [车型上市专题说明](../docs/vehicle_launch_capabilities.md)，机器可读入口见 [vehicle_launch_capabilities.json](registry/vehicle_launch_capabilities.json)。本阶段仅登记入口，不自动开放生产 Job。

## 数据更新与推送

以下操作按实际授权选择。向飞书写入前先预览并核对口径，正式推送遵守对应入口的新鲜度门槛。

| 要做的事 | 入口 | 对数据和外部系统的影响 |
|---|---|---|
| 预检日常观察 | `make data-pipeline-dry-run` | 校验现有数据，预览观察内容；不刷新、不推送 |
| 刷新每日数据 | `make data-refresh-daily` | 写本地订单和下发线索 |
| 全量刷新并校验 | `make allupdate` | 写本地数据，含试驾、锁单归因；执行数据校验 |
| 更新订单并预览指定代际上市监控 | `make monitor-sync SERIES=CM3 PHASE=launch DRY=1` | **会先刷新并写入订单表**，随后预览卡片；不发送飞书 |
| 更新订单并推送指定代际上市监控 | 核对上行预览后运行 `make monitor-sync SERIES=CM3 PHASE=launch` | 再次刷新订单表，并发送飞书卡片 |

每日观察同步和运营组合命令见[每日数据管道](../docs/daily_data_pipeline.md)，执行步骤以根 [Makefile](../Makefile) 为准。

## 维护与交付

- 稳定业务脚本放在 [business_scripts](business_scripts)，预测与回测放在 [research_scripts](research_scripts)，整理和同步工具放在 [utility_scripts](utility_scripts)。能力成熟度查 [Workspace 注册表](registry/capability_registry.json)，能通过 Hub/Worker 调用的 Job 查 [Job 声明](../jobs/config/jobs_config.json)。
- 原始数据统一从根 `dataset/` 读取。临时分析写到 workspace 的 `scratch/`，业务表格、图和报告分别放在 workspace 的 `outputs/tables/`、`outputs/charts/`、`outputs/reports/`。导出时按脚本的 `--output` 约定指定位置。
- 分析方法与专题手册见[文档索引](../docs/README.md)，结构化业务结果见 [Result Contract](../docs/result_contract.md)。任务执行边界见[根 AGENTS](../AGENTS.md)和[Workspace AGENTS](AGENTS.md)。
