# Service Fast Path Readiness V1 Acceptance

验收日期 2026-11-27。业务日期和无偏移的业务时间均按北京时间。以 [Readiness Audit V1](service_fast_path_readiness_audit_v1.md) 为基准。Ready 表示可由受管宿主直接以固定参数和结构化结果调用，通过 Service 独立验收。

| 能力 | 最终状态 | 固定入口 |
| --- | --- | --- |
| 订单配置 Mix | **Ready** | `python -m workspace.business_scripts.order_config_mix --snapshot PATH --request JSON` |
| 上市累计锁单 | **Ready** | `python -m workspace.business_scripts.launch_lock_summary --snapshot PATH --request JSON` |
| 单表订单刷新 | **Ready** | `jobs.cli --job data_refresh_order_data` |
| 每日订单与下发线索刷新 | **Ready** | `jobs.cli --job data_refresh_daily` |
| 锁单归因刷新 | **Ready** | `jobs.cli --job data_refresh_lock_attribution` |
| 配置刷新 | **Ready，延续 V1** | `jobs.cli --job data_refresh_config_attribute` |
| TP&MIX-ways 上险刷新 | **Ready，延续 V1** | `jobs.cli --job update_tp_and_mix_ways_dataset` |

两条查询可独立执行。旧 DSH Python 入口及 Service 固定 LS8 内饰入口保留，现有监控卡片继续使用官方上市算子和快照退款审批口径。本轮交付 Service 独立 CLI 执行边界和业务结果合同，DSH 注册、生产流量与发布验收属于后续阶段。

## 一、共用只读快照与结果

从 Service 根目录使用 `.venv/bin/python -B`。由宿主提供 `--snapshot` 指向既有 `<version>/snapshot.json`，可选传入 `--definition-version` 固定预期规则版本。查询参数 JSON 只接受下文的业务字段。查询读取 manifest、其中固定的依赖和 Service 算子代码，stdout 输出单一 JSON。禁止客户端将生产路径、刷新或通知操作传为业务参数。

- 接受现有 copy manifest v1。`version` 与目录名一致，请求依赖的数据为同目录常规文件，定义文件在版本目录内，可用定义子目录。数据和定义均需固定 `size_bytes` 与 SHA-256，文件不可写且路径不能经文件级符号链接或越过版本目录。可复用 DSH Data Prepare 产出的已有 copy manifest。旧业务快照若缺哈希或定义，需由宿主先核验并在隔离区按相同格式准备副本。link 模式需要先实体化为 copy。
- `scope.definition_version` 为所有清单定义项的 `{id: sha256}` 按键排序后对 Python 默认 `json.dumps(..., sort_keys=True)` UTF-8 字符串计算的 SHA-256。若 manifest 声明 `definition_version` 或调用方传入预期值，均须匹配。回执同时返回逐定义哈希、`snapshot_version`、输入哈希、行数及清单截止元数据。
- 查询 Result Contract `contract_version=1`，包含 `status/scope/result/warnings/errors` 和现有 Result Contract 公共字段。`success` 或 `partial_success` 退出 0。部分结果需根据告警判断是否适合交付。`error` 退出 1，`errors[0].code` 可机器识别。缺清单、缺依赖、非法路径或大小、哈希不符、规则版本冲突分别用 `SNAPSHOT_MISSING`、`SNAPSHOT_DEPENDENCY_MISSING`、`SNAPSHOT_INVALID`、`SNAPSHOT_HASH_MISMATCH`、`DEFINITION_VERSION_MISMATCH`。输入数据列或时间戳无效为 `INVALID_INPUT_DATA`。
- 同一快照、参数和 Service 代码版本下业务结果可重复。保留执行所用 Service 提交和规则哈希以区分代码、数据、定义三种版本。查询入口没有生产刷新、live fallback、通知或结果文件写入路径。

依据见 [快照读取](../jobs/snapshot.py) · [查询 CLI 与状态](../workspace/utils/snapshot_query.py) · [Result Contract](共享规范/result_contract.md)。

## 二、订单配置 Mix

```bash
.venv/bin/python -B -m workspace.business_scripts.order_config_mix \
  --snapshot "$FAST_PATH_SNAPSHOT" \
  --request '{"generation":"LS8","dimension":"seat_count","time_window":"last_30_days","order_type":"用户车","power_type":"增程"}'
```

请求为闭合 JSON 对象，所有取值均为非空字符串，重复 JSON 字段拒绝。

| 字段 | Schema |
| --- | --- |
| `generation` 或 `family` | 两者恰选一。`generation` 为 `series_group_logic` 规范键，排除“其他”；`family` 为 `model_series_mapping` 规范键。别名和家族歧义由上游解析或澄清。 |
| `dimension` | 必填。`seat_count / power_type / product_version / order_type`，或精确配置属性名称，或 `config:<attribute_code>`。重名多编码要求显式代码。 |
| `metric` | `locked_orders / retained_locked_orders / delivered_orders / invoiced_orders`，默认 `locked_orders`。所有指标按订单号去重。 |
| `time_window` | `since_launch / since_launch_open / range / all / last_7_days / last_30_days / mtd / ytd`，默认 `since_launch`。 |
| `start_date`、`end_date` | 有效北京时间日历日期 `YYYY-MM-DD`。仅 `range` 要求起止两项，终止日含当天；上市窗口可选 `end_date`；其余窗口以所选代际的事件数据截止日为锚。 |
| `order_type` | 可选。枚举 `员工 / 用户车 / 享道 / 集团员工 / 试驾车 / 大客户 / 经销商员工 / 仅批售 / 项目 / 展车 / 海外`。 |
| `test_drives`、`internal_test_orders` | 各为 `include / exclude`。普通时窗默认包含；上市开放时窗强制剔除内部测试单。试驾车由 `order_type` 筛选；内部测试单用官方总部门店与占位号规则。 |
| `group_by`、`power_type` | 仅 `seat_count` 支持。`group_by=power_type` 给出分动力分母，`power_type=增程/纯电` 可限制查询群体。 |

普通锁单使用 `lock_time`，含已审批退款。留存锁单按快照内 `approve_refund_time` 为空计算，结果标注 `snapshot_refund_status`。自然日上市窗口从业务定义 `end` 的零点开始，家族取最早上市日；实际开放窗口复用官方算子，按代际起算，适用于两种锁单指标。代际未登记上市日时返回明确错误。开票和交付沿用固定指标事件字段。

依赖 `business_definition / metrics / config_semantics`；始终读取 `order_data`，座位与 EAV 维度还要求 `config_attribute`。按属性编码识别同一属性，以取值编码及代际语义归一配置，旧表缺编码时保留受控的名称或值回退。座位优先采用配置数据，缺失时使用共享产品算子；冲突仍计入总分母且单列。通用聚合与固定 LS8 入口共享配置归一及订单级冲突解析，固定入口继续对各动力组使用含缺配和冲突的全量分母。

回执 `result` 包含 `total_orders/known_orders/missing_orders/conflict_orders/coverage`，满足总数等于已知、缺失、冲突之和。`groups[]` 输出 `value/count/share_of_known/share_of_total`，比例为 0–1 小数。可选 `by_power_type[]` 含同款字段。另有 `attribute_code`、`latest_matched_config_event_time`、`config_file_mtime` 和去重数量；订单事件实际截止见 `scope.time_window`。配置表 mtime 只表示文件时间。缺失或冲突发出 `CONFIG_INCOMPLETE`，显式结束日晚于可见日期发出 `AS_OF_CAPPED`。错误包括 `INVALID_REQUEST/INVALID_DATE/INVALID_WINDOW/INVALID_ORDER_TYPE/INVALID_GROUPING/UNKNOWN_METRIC/UNKNOWN_GENERATION/UNKNOWN_FAMILY/UNKNOWN_DIMENSION/AMBIGUOUS_DIMENSION/LAUNCH_DATE_UNCONFIRMED/NOT_LAUNCHED/DATA_NOT_COVERED/NO_ORDERS`。

依据见 [Service Mix](../workspace/business_scripts/order_config_mix.py) · [配置语义](../workspace/utils/config_semantics.py) · [固定 LS8 兼容计算](../workspace/utils/ls8_interior_mix.py) · [历史 DSH 查询](../../dsh-superagent-prototype/plugins/order-config-ratio/query.py)。

## 三、上市累计锁单

```bash
.venv/bin/python -B -m workspace.business_scripts.launch_lock_summary \
  --snapshot "$FAST_PATH_SNAPSHOT" --request '{"generation":"LS9","as_of":"2026-01-31"}'
```

| 字段 | Schema |
| --- | --- |
| `generation` | 必填规范代际键，接受 `LS9`、`LS9M1` 等；家族及别名须在宿主解析。 |
| `as_of` | 可选有效北京时间日历日期 `YYYY-MM-DD`，缺省取已剔除测试单的最新锁单日期。 |
| `retention_basis` | `snapshot_refund_status`（默认）或 `refund_approval_as_of`（PIT 显式选择）。 |

闭合对象，只读 `order_data` 和 `business_definition`。源截止从排除内部测试单后的全快照锁单时点取得，查询截止为该时点与请求日结束时刻的较早值。实际开放取上市日后第一笔合格锁单，结果标注 `first_qualifying_lock`；无合格候选时沿用官方上市日零点回退并标注 `launch_day_start_fallback`。用户车严格按 `order_type=用户车` 计数。

`result` 输出 `generation/launch_date/launch_open_at/launch_open_source/requested_as_of/lock_data_cutoff/lock_cutoff/cumulative_lock_count/user_car_lock_count/user_car_share/retained_lock_count/retention_basis/order_type_filled_count/order_type_filled_ratio/test_orders_excluded/checks`。用户车占比以累计锁单为分母，分母为零或填充低于 50% 时为 `null`，仍保留真实计数。填充不足 100% 时给 `ORDER_TYPE_INCOMPLETE`。请求超出源数据日发出 `AS_OF_CAPPED`。

未知代际、上市日期未确认、请求日早于上市日、数据未覆盖上市日、未到实际开放时点及算子校验失败分别返回 `UNKNOWN_GENERATION`、`LAUNCH_DATE_UNCONFIRMED`、`NOT_LAUNCHED`、`DATA_NOT_COVERED`、`LAUNCH_NOT_OPEN` 和 `METRIC_CHECK_FAILED`。窗口有效且已覆盖的空样本返回真实零。

默认留存沿用官方监控，按快照中退款审批为空判定。PIT 合同只以审批事件重建留存，保留审批为空或审批时点晚于 `lock_cutoff` 的锁单；截止时点已审批的订单剔除。PIT 用于显式历史留存请求。订单和代际等其他字段仍使用所绑定快照的字段值。

依据见 [只读上市摘要](../workspace/business_scripts/launch_lock_summary.py) · [官方上市算子](../workspace/utils/monitors/launch.py) · [现行监控入口](../workspace/business_scripts/vehicle_sales_monitor.py) · [业务定义](../shared/schema/business_definition.json)。

## 四、刷新作业

五项沿用 `jobs.cli` 固定 argv。业务输入 Schema 全部为 `{"type":"object","properties":{},"additionalProperties":false}`。配置及上险维持 production v1 的业务条件及范围。订单、daily、归因本轮在原外层回执上增加 `contract_version=2`。以下固定调用是交接说明，生产调用需独立授权。

```bash
.venv/bin/python -m jobs.cli --job data_refresh_order_data --format json
.venv/bin/python -m jobs.production status data-refresh-order-data --repo-root "$PWD" --run-id "$SERVICE_RUN_ID"
.venv/bin/python -m jobs.production recover data-refresh-order-data --repo-root "$PWD" --run-id "$SERVICE_RUN_ID"
```

| Job ID | production 目标 | 受权写入及结果 |
| --- | --- | --- |
| `data_refresh_order_data` | `data-refresh-order-data` | 只发布订单 Parquet，允许本 Job 的导出缓存和运行记录。使用 `order_number` 主键和 `lock_time` 业务截止验证。 |
| `data_refresh_daily` | `data-refresh-daily` | 逐步发布订单和下发线索。下发线索按 `Assign Time 年/月/日` 校验日期主键、必需指标、行数和截止。 |
| `data_refresh_lock_attribution` | `data-refresh-lock-attribution` | 只发布归因 Parquet，允许归因 Tableau 导出缓存。按 `lc_user_phone_md5 + lc_main_code` 校验组合键，兼容历史未匹配手机号，`lc_order_lock_time_min` 为验证截止。历史底座不可读时保留正式文件。 |
| `data_refresh_config_attribute` | `data-refresh-config-attribute` | 只发布配置 Parquet 并读取订单补齐字段。沿用配置键、行数和 mtime 校验，配置文件没有自身业务截止。 |
| `update_tp_and_mix_ways_dataset` | `update-tp-and-mix-ways-dataset` | 更新六张上险月表、对应 raw、registry、quality 和发布事务记录。以各表 `date_month` 交付上游最新可用月。 |

三个 V2 作业在同一文件系统中暂存输出，校验可读性、必需字段、业务截止、主键和行数后原子替换。实际文件哈希相同则保留原文件。生产作业另核对刷新前后的结构和内容哈希，检查已记录的 updater 完成状态及输出是否仍匹配。允许作业内只读查看其他 registry 项；`before/after/dataset_results/changed_datasets` 才是主要范围回执。 [原子发布和文件验证](../dataset/updater/refresh_validation.py) · [目标范围](../jobs/config/jobs_config.json) · [Updater 分派与逐步记录](../dataset/updater/update_all_datasets.py)

- **权限和请求幂等。** 仅从受管主 checkout 执行。固定白名单负责数据范围，Source、操作者及写入授权由调用方控制。`MASHANG_JOB_RUN_ID` 由宿主持久化分配，有效格式 `[A-Za-z0-9][A-Za-z0-9_-]{0,127}`。同一 ID 绑定同一 Job，同 ID 重提交读取已有记录或恢复，新的有意执行使用新 ID。锁被占用可能返回 `busy`。直接绕开生产 Job 的旧 Make/updater 调用不参与该请求幂等。
- **兼容外层。** `jobs.cli` 的 `summary_json` 是 production 业务回执，外层 `status/returncode` 只反映执行包装。内层 `version=1`，V2 三项另有 `contract_version=2`。顶层 `status` 沿用 `success/no_new_data/failed/timeout/verification_failed/busy` 及中间态 `running`。
- **V2 结果。** `outcome=all_succeeded` 表示目标全部执行核验通过且业务截止或行数增加，`updated_existing` 表示内容变化但无新增，`no_new_data` 表示目标执行核验通过且哈希保持一致，`partial_write` 表示存在目标文件变化且整体未通过。结合 `status` 判断是失败、超时还是校验异常。逐表 `dataset_results` 含 `execution_status/publish_status/returncode/before_sha256/after_sha256/verified/verification_errors`。发布状态包括 `published/unchanged/invalid/changed_unconfirmed`。仅凭结束后出现的不同文件不能确认中断作业已成功发布。
- **业务截止与恢复。** V2 使用 `after[dataset].validated_cutoff` 和 `validated_cutoff_column` 作回执，兼容字段 `latest_data_time` 沿用 registry 时点定义。刷新内层默认 1,800 秒，状态核验 180 秒，外部 adapter 默认 2,100 秒。外部超时或中断时，先按 run ID 读取记录。`recover` 只补写运行回执，持锁核验实际文件和逐步记录，无重新刷新。仍有运行中的 updater 时返回 `running`，证据不足时返回待核验或失败状态；已完成回执直接重放。

依据见 [生产回执、超时及恢复](../jobs/production.py) · [Job adapter](../jobs/adapter.py) · [订单 updater](../dataset/updater/order_data_to_parquet.py) · [归因 updater](../dataset/updater/lock_attribution_data_to_parquet.py)。

## 五、独立验收

### 历史快照回放

在固定 Service Python 下运行，不启动 DSH、Harness、Worker 或模型。历史 copy manifest `26402169-6c50-4957-96b4-0261de5c82d9` 直接验证并消费。两个旧版本在隔离目录复制原数据文件并对文件加哈希，规则绑定本次 Service 定义；源快照保持只读。两份规则集合摘要为 `b69031aff155cab0c8052bcc9f63a89028bebea8224567cdded525ccf3447e81`（隔离副本）及 `2ecf9bd32a97db4b2df144eb301663cb5b3478a62d1b725660d888c7a30fa565`（原 Data Prepare copy）。每组新查询实际调用两次，去掉生成时间后 JSON 一致。

| 快照 | 请求 | 结果 |
| --- | --- | --- |
| `12e90376-cf4b-41d3-be1f-26d600892716` | LS8 近 30 日增程用户车座位 | 总数 687，五座 573、六座 114，缺失和冲突均为 0。锁单截止 2026-11-23 12:00:54。 |
| 同上 | CM3 上市以来用户车内饰 | 总数 9,118，象灰米 5,994、骑士黑 3,090、大地橘 34。订单事件截止 2026-11-23 09:53:43。 |
| 同上 | LS8 全系上市以来普通与留存锁单内饰 | 普通 16,196、留存 13,562。留存已知 13,561、缺失 1。固定 LS8 兼容入口仍为增程 10,261、纯电 3,288、未知动力 13。 |
| `26402169…` | LS8 近 30 日全部订单座位 | 799 笔，五座 683、六座 114、缺失 2。 |
| `a38788cc-ce3c-47b3-9f16-f2caf82e1eea` | LS9 截至 2026-11-09 | 开放为 2025-11-12 16:53:23，锁单截止 2026-11-09 13:12:50。累计 21,726，用户车 20,941，占 96.39%，留存 16,462。 |
| 同上 | LS9 截至 2026-01-31，分别请求默认及 PIT | 截止 2026-01-31 23:59:59。两者累计 12,805，用户车 12,334，占 96.32%。默认留存 9,028；PIT 留存 10,192，差 1,164。 |
| `26402169…` | LS9 截至 2026-11-16 | 锁单截止 2026-11-16 22:15:00，累计 21,834，用户车 20,998，占 96.17%，留存 16,554。 |

LS9 样本附 `ORDER_TYPE_INCOMPLETE`，用户车占比按可见订单类型定义输出。生产数据文件仅以只读方式验证当前三项 schema 和主键；类型与字段验证使用隔离数据及 updater 替身。正式环境没有触发刷新、群消息或发布。

### 测试与回归

| 检查 | 结果 |
| --- | --- |
| scoped 验证计划 | `make verify-scope` 通过，按本轮文件解析，排除了既有 CPCA 工作树改动；三个 workspace 辅助模块虽未被路径规则分类，已有测试直接覆盖其消费者。 |
| 全量验证 | 按验证解析器的 `--all --run` 执行 18 个目标。16 个首轮通过，其中包括 CI/Core Eval、workspace 全量、dataset、市场观察、监控、订单语义、CLI 冒烟。两项 Jobs 目标报告同两个 fixture 失败，原因分别是未补生产读数所需日期解析和重复重写 Parquet。修正隔离 fixture 后，Jobs 全量与监控、预售、daily 流水线定向回归共 **165 项通过**，包含这两个原失败用例。 |
| 基础能力回归 | **120 项通过**。首次运行有一个 Feishu 测试受本机 dotenv 的默认文件夹设置影响，空值覆盖该环境变量后全套通过。测试使用 fake HTTP。 |
| 快照 CLI | 实测非法参数、缺表、可写文件、同大小内容变化和规则版本冲突返回结构化错误。历史回放九组查询各运行两次，业务回执一致。 |
| 隔离刷新及恢复 | 用实际分派器、临时主 checkout 和本地 updater 替身覆盖订单单表范围、daily 部分写入、归因等时点订正和无新增。模拟终止 runner 后，子进程持锁至结束，按同 run ID 恢复原回执且未重复执行。暂存用例验证键冲突、时点或行数异常及归因旧底座不可读时原文件保留。 |

依据见 [快照查询用例](../jobs/tests/test_fast_path_queries.py) · [生产 Job 和恢复用例](../jobs/tests/test_production_job.py) · [原子发布用例](../jobs/tests/test_refresh_validation.py) · [验证范围契约](../.opencode/verification/README.md)。
