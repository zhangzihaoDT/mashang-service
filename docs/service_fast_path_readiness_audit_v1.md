# Service Fast Path Readiness Audit V1

审计日期 2026-11-27，业务日期均按北京时间。以 Service `845b6484623c` 和 DSH-superagent `ef6633f190a4` 的本机工作树为基线。Service 工作树已有 CPCA 海报相关改动，DSH 的 019 报告是本机工作文件。历史运行与离线回放分别标注。本次交付范围为文档，执行只读检查和历史快照查询。 [DSH 019 审计](../../dsh-superagent-prototype/docs/019-fast-path-business-job-audit.md)

## 1. 成熟度与注册结论

Ready 表示所列范围可由受管宿主直接调用，参数、回执、授权边界及验证证据足以确定性消费。Partial 表示已有业务能力，仍有会改变业务答案或写入终态的契约缺口。Missing 表示缺少必要的业务计算或执行能力。评级适用于 Service 交接，DSH 的生产路由验收另计。

| 优先级 | 能力 | 成熟度 | 注册前结论 |
| --- | --- | --- | --- |
| P0.1 | 订单配置 Mix | **Partial** | DSH Python 已有通用计算，Service 已有固定 LS8 内饰口径。复用现有实现，先统一业务归属、参数和快照合同。 |
| P0.2 | `data_refresh_daily` | **Partial** | 已注册，且有历史成功回执。订单与下发线索的结果都需补齐存在性、字段和截止验证，并明确部分写入。 |
| P0.2 | `data_refresh_order_data` | **Partial** | Service 独立入口和单表写入边界已得到复核。先补后置验证及中断语义，然后在 DSH 注册这个固定 ID。 |
| P0.2 | `data_refresh_config_attribute` | **Ready** | 适用于经授权刷新当前配置表，按文件元数据及行数回执。配置表无业务日期，新增量与内容订正须按现有状态定义解读。 |
| P0.2 | `data_refresh_lock_attribution` | **Partial** | 已注册，单表范围明确。需补历史底座读取失败和结果验证，并跑独立离线回执用例。 |
| P0.2 | `update_tp_and_mix_ways_dataset` | **Ready** | 适用于刷新 Tableau 可用的最新数据并发布六张月表。指定目标月及月度覆盖保证需要独立合同。 |
| P0.3 | 上市累计锁单 | **Partial** | 官方计算已在 Service，快照 CLI 可以直跑。需补确定性输入校验、开放时刻及历史留存语义，再交给 DSH 消费。 |

两项 Ready 以受管主 checkout、经授权的固定入口和宿主持久化请求去重为前提。当前 Service CLI 可脱离 Agent Loop 独立执行，直接重复提交同一运行编号仍可能发起第二次写入。三类需求均有可复用业务实现，本次主范围无 Missing。DSH 019 将查询底层能力标为 Ready，本报告按完整结果合同评审，将已复现的错误语义计入评级。 [Service Jobs](../jobs/README.md) · [DSH 已注册 Job](../../dsh-superagent-prototype/src/app/business-jobs.ts#L33)

## 2. Local Job 和 Capability 清单

| 所在层 | ID / 入口 | 用途 |
| --- | --- | --- |
| Service 已声明 Job，本次刷新范围 | `data_refresh_daily`、`data_refresh_order_data`、`data_refresh_config_attribute`、`data_refresh_lock_attribution`、`update_tp_and_mix_ways_dataset` | 固定 CLI、空业务参数、生产受控写入。 |
| Service 已声明 Job，范围外 | `daily_lock_count`、`data_refresh_tableau_hs`、`data_refresh_assign_data`、`data_refresh_delivery_inventory`、`data_refresh_test_drive_data`、`cpca-market-retail-poster` | 当前本机目录其余条目。海报来自既有本地改动。日锁单 Job 的单日口径与 P0.3 有别。 |
| Service 独立业务查询 | `jobs.ls8_mix --snapshot`、`vehicle_sales_monitor.py --snapshot` | 固定 LS8 内饰及预售/上市监控查询。两个入口均在 `feature_jobs` 清单之外。 |
| Service 快照与 DataOps | `jobs.snapshot`、`jobs.production check/status`、`make data-status` | 快照复制与读取、运行记录、数据集状态。运行记录状态与数据快照状态可独立读取。 |
| DSH 原有查询与编排 | `order_config_ratio` → `query.py`、`data_prepare` / `dataPreparation.ensure`、`business_job.refresh_snapshot`、Prepare `launch-monitor` | 配置计算、只读快照准备、授权刷新后绑定及官方查询声明。四个刷新已在 DSH 注册，其中缺独立订单刷新。 |
| Service 基础能力 | `capabilities/{diagram,feishu,notify,ocr,search}` | 领域无关原语。上市普通监控可经 Notify 发卡，上市快照分支直接输出 JSON。 |

依据见 [Job 配置](../jobs/config/jobs_config.json) · [基础能力](../capabilities/README.md) · [快照与查询说明](../jobs/README.md#ls8-内饰订单-mix) · [DSH Prepare](../../dsh-superagent-prototype/docs/011-workspace-prepare.md)。

## 3. P0.1 订单配置 Mix

### 3.1 权威来源与计算归属

- Service 管理订单事件、代际与产品版本规则、配置语义及原始数据。`business_definition.json` 按优先级解析 `product_name`，定义家族、代际、上市日、座位和动力。LS8 动力来自版本字典。配置表为订单 × 属性 EAV，连接键为 `order_data.order_number` 与 `config_attribute."Order Number"`。属性身份用 `attribute_code`，取值身份用 `value_code`，显示名允许随代际变化。锁单以 `lock_time` 为准，按订单号去重。 [数据字典](共享规范/data_dictionary.md) · [字段 Schema](../shared/schema/schema.md) · [指标定义](../shared/schema/reference/metric_definitions.md#锁单数--锁单量) · [业务字典](../shared/schema/business_definition.json) · [配置字典](../shared/schema/config_semantics.json) · [产品算子](../shared/operators/product_attributes.py#L147)
- 已上线的通用查询计算主体在 DSH `query.py`。它复用 Service 的分类、产品算子和上市开放判定，同时独立实现了别名、时间窗、事件过滤、去重、订单与 EAV 关联、配置冲突处置、分母和覆盖、质量及展示。普通 `since_launch` 按上市自然日，`since_launch_open` 才调用 Service 的开放时刻与内部测试单过滤。`exclude_test_orders` 在普通路径实际排除 `order_type=试驾车`，与上市监控定义的内部测试单是两个筛选条件。现有配置映射主要按 `Attribute` 文本选取，跨代际按属性编码合并的业务规则还需明确落实。 [通用查询](../../dsh-superagent-prototype/plugins/order-config-ratio/query.py#L1120) · [配置映射](../../dsh-superagent-prototype/plugins/order-config-ratio/query.py#L807) · [配置分析口径](业务能力/通用业务分析/analysis_playbook.md#属性名归并用-attribute_code-而非-attribute)
- Service `jobs.ls8_mix` 复用 `utils.ls8_interior_mix.mix` 和配置语义工具。固定 `series=LS8` 含 LS8Neo，从 LS8 上市自然日开始，保留退款审批为空的锁单，无用户车参数。动力组分母含缺配与冲突，未知动力另计。DSH 普通 Mix 的 `share` 以已知配置为分母，`share_of_total` 以全部入组订单为分母。两条链路同时承担配置聚合，且口径存在明确差异。 [固定 CLI](../jobs/ls8_mix.py#L22) · [LS8 计算](../workspace/utils/ls8_interior_mix.py#L8) · [通用分母](../../dsh-superagent-prototype/plugins/order-config-ratio/query.py#L999)
- `attribute_penetration_report.py` 按显式配置记录分析配置渗透率。`ls8_configuration_selection_report.py` 用车型版本、配置字典与业务规则分析 LS8 配置拥有率和选装。`config_decision_engine.py` 按权益、价格与冲突证据判断标配、免费与付费，语义及分母有各自用途。`refresh-and-analyze` 记录固定快照入口，`vehicle-launch-deep-dive` 约束报告筛选与配置展示。上述资产可用于口径对照和回归。 [渗透率](../workspace/business_scripts/attribute_penetration_report.py) · [LS8 报告](../workspace/research_scripts/ls8_configuration_selection_report.py) · [配置判定](../workspace/business_scripts/config_decision_engine.py) · [刷新分析 Skill](../.opencode/skills/refresh-and-analyze/SKILL.md) · [上市分析 Skill](../.opencode/skills/vehicle-launch-deep-dive/SKILL.md)

### 3.2 当前参数化程度和离线实测

通用 Python CLI 可独立执行，依赖 Service checkout、Python 环境和数据快照。支持代际或家族、显式起止日期、上市日/开放时刻、近 7/30 日、当月/当年/全量、订单类型及城市过滤。指标来自 `metrics.json` 中按订单号计数且有事件时间的订单主表项；维度包括座位、动力、版本、订单类型及配置属性。座位可按动力分组，API 未声明动力过滤字段。Service 固定 LS8 入口仅接受快照路径。 [DSH Tool 参数与输出 Schema](../../dsh-superagent-prototype/plugins/order-config-ratio/index.js#L110) · [时窗解析](../../dsh-superagent-prototype/plugins/order-config-ratio/query.py#L1028) · [指标注册表](../shared/schema/metrics.json)

以下结果使用历史只读快照，锁单指标与快照业务截止各自标明。快照 `12e90376-cf4b-41d3-be1f-26d600892716` 的订单/配置 SHA-256 前缀分别为 `f6429663c2aefbee`、`254d2c0244dc811c`，两文件权限均为 `0444`。

| 回放 | 实测 |
| --- | --- |
| LS8 代际近 30 日用户车锁单，座位按动力拆分 | 2026-10-25 起，代际指标截止 2026-11-23 12:00:54。增程 687 单，五座 573、六座 114，缺失 0。应从正式 `group_by=power_type` 的结构化分组读取。 |
| CM3 上市以来用户车锁单内饰 | 2026-09-23 起，代际指标截止 2026-11-23 09:53:43。分母 9,118，象灰米 5,994、骑士黑 3,090、大地橘 34，缺失 0。 |
| 同快照对照 LS8 全系内饰 | Service 固定留存口径为增程 10,261、纯电 3,288、未知动力 13，共 13,562。DSH 输入 `retained_locked_orders` 或“留存锁单”时，宽松匹配落为普通“锁单量”，分母 16,196、已知 16,195。两条回执不能作为同口径平替。 |
| 异常输入与缺表 | 未知车型返回 `UNKNOWN_VEHICLE`，CLI 退出 0。坏起始日、未知字段可被忽略，查询仍为 `ok`。在只有订单表的 `a38788cc…` 快照查询 LS9 内饰，返回 `UNKNOWN_DIMENSION`，未准确指明配置依赖。 |
| Data Prepare copy 快照 | `26402169-6c50-4957-96b4-0261de5c82d9` 的三份定义哈希与清单相符。LS8 近 30 日全订单类型座位分母 799、已知 797、缺失 2，五座 683、六座 114；这份历史快照以代际锁单截止 2026-11-16 18:29:42 计算窗口。 |

当前通用结果有 `ok/partial/error`、`result.denominator/known_denominator/missing/coverage/groups`、`quality.checks`、过滤、数据截止与快照来源。旧 Tool 的输出 Schema 宽松，同样的 `ok` 可以附陈旧或其他质量告警。日期、枚举及未知字段校验不足；全量锁单与留存要用显式指标。通用查询应归到 Service，由现有逻辑迁入一个只读入口，固定 LS8 CLI 保持历史语义并复用相同底层构件。DSH 保留参数映射、快照绑定、权限和结构化结果消费。 [输入解析](../../dsh-superagent-prototype/plugins/order-config-ratio/query.py#L474) · [结果及质量](../../dsh-superagent-prototype/plugins/order-config-ratio/query.py#L1599) · [异常退出](../../dsh-superagent-prototype/plugins/order-config-ratio/query.py#L2008)

### 3.3 快照机制

| 快照来源 | 现有保证 | 接入差异 |
| --- | --- | --- |
| DSH `data_prepare` | 根据数据集和定义需求复用或创建，包含新鲜度、覆盖、只读权限、SHA-256。支持 `copy` 本地副本和 `link` 引用已绑定的只读文件。 | DSH Mix 可消费两种模式，并优先用清单中的定义。业务 helper 仍从 checkout 导入。Service 读器要求数据文件与 manifest 同目录，当前可读 copy，拒绝外部引用的 link 路径。 |
| DSH `business_job.refresh_snapshot` + Service `jobs.snapshot` | 先校验授权计划和生产终态，再在生产 Job 同一把锁下复制请求表。对有已核验记录的表比对 mtime/大小，复制时检查源文件签名，输出 `0444` 文件，宿主发布版本清单。 | Service 读取时核对版本目录、同目录绝对路径、非符号链接和大小。现有清单不固定业务字典或文件哈希，读取也不校验 SHA-256 和权限。只读查询优先消费已经发布的快照。 |
| Worker Prepare | 按 profile 将数据复制到 Ticket worktree，记录行数、SHA-256、只读权限、时点和官方查询声明。 | 工作树约定支撑原 `launch-monitor` 模板。固定 Fast Path 应显式传快照清单和受管定义版本。 |

Fast Path 查询侧需拒绝缺清单、缺依赖或校验失败的输入。DSH 旧查询在无有效工单快照时可回退 worktree 或生产表，个别快照读取异常也可能触发回退。旧插件 `refresh=true` 路径意图依次进行 daily 与配置刷新，存在生产写入面，同时源码读取生产状态的层级与当前 `jobs.cli` 的 `summary_json` 包装不一致，可能在实际写入后报告刷新失败并回退。只读合同应移除这一入口能力，仍需刷新时由受管写入 Job 单独授权。配置表无业务截止，分别报告 mtime、同窗匹配覆盖和有效订单事件截止。 [DSH 数据准备](../../dsh-superagent-prototype/plugins/dsh-data-prep/README.md) · [校验与链接](../../dsh-superagent-prototype/plugins/dsh-data-prep/index.js#L674) · [Service 快照](../jobs/snapshot.py) · [DSH 刷新绑定](../../dsh-superagent-prototype/src/app/business-jobs.ts#L299) · [旧刷新与回退](../../dsh-superagent-prototype/plugins/order-config-ratio/query.py#L1194)

## 4. P0.2 数据刷新

### 4.1 每个 Job 的作业范围

五项均已在 `feature_jobs` 声明 `params={}`、固定 argv、仓库根目录、JSON 摘要和 2,100 秒外层预算。五个主 checkout `check` 均通过，五个 `scope=full` 未声明参数探针均在启动子进程前被拒绝。以下范围由固定 Make 目标、`build_steps` 离线枚举及历史回执交叉核对。 [配置](../jobs/config/jobs_config.json) · [白名单](../jobs/adapter.py#L54) · [Make 目标](../Makefile#L210) · [更新脚本分派](../dataset/updater/update_all_datasets.py#L117)

| Job ID | 固定目标与允许的正式数据变更 | 结果校验与本地历史 |
| --- | --- | --- |
| `data_refresh_daily` | `data-refresh-daily` → 两步更新 `order_data.parquet` 和 `assign_data.csv`。 | 两表前后状态；最近一条成功为 11-23 12:36:57，22.22 秒，`dsh-be83bfdf…`。默认逐步执行，首表可已发布而另一表失败，旧回执缺分步提交状态。 |
| `data_refresh_order_data` | `data-refresh-order-data` → `--scope order_data` → 仅 `order_data_to_parquet.py`。读、合并、按订单号去重后写 `order_data.parquet`。 | 2026-11-26 08:18:58 成功，27.94 秒，`dsh-recover-0e9589db-20261126`。前后状态键仅 `order_data`，业务截止 11-25 23:22:28（`lock_time`）。 |
| `data_refresh_config_attribute` | `data-refresh-config-attribute` → 强制增量更新 `config_attribute.parquet`；读订单表补充订单属性。 | 专门验证存在、非空、mtime。增量保留历史键，暂存 Parquet 回读后原子替换。2026-11-23 12:37:11 成功，13.16 秒，`dsh-d8691867…`。配置业务时点为 `null`。 |
| `data_refresh_lock_attribution` | `data-refresh-lock-attribution` → 归因导出与整理 → `lock_attribution_data.parquet`，registry 名 `lock_attribution`。 | 后验主要检测行数与截止回退。旧 Parquet 读取失败可退为仅新数据；读取不可用的旧行数不足以保护历史。查阅的本机运行记录未见该独立 Job 回执。 |
| `update_tp_and_mix_ways_dataset` | `update-tp-and-mix-ways-dataset` → Tableau 增量、raw_csv 整月替换、六张月表及 registry/quality 发布。 | 六表必须存在、非空且有最大月；下层在 staging 校验历史月、键和跨层一致性，发布有回滚及中断恢复。2026-11-17 有失败后重试成功的记录，成功为 10:36:17，68.70 秒，`dsh-bde9c1ce…`，六表最大月均 2026-10。 |

**订单单表刷新范围已确认。** `data_refresh_order_data` 的刷新分支只选订单更新器，`make data-status` 及 registry 会读取多表状态，`latest_data_time_by_dataset` 也可能带其他表的时点。回执应以 `before/after`、`changed_datasets` 和预期写入集合为准。更新器还可能写订单自身的导出缓存及视图发现配置，Job 会写运行记录，两者均属于运行副作用。该目标的调用链没有下发线索、配置、归因、日报同步或发送卡片的步骤。现有 Skill 把授权订单刷新导向 daily，原因是 DSH 可选清单没有单表入口；只授权订单的请求应绑定单表 ID。 [生产目标集合](../jobs/production.py#L38) · [步骤筛选](../dataset/updater/update_all_datasets.py#L274) · [只读状态](../dataset/updater/update_all_datasets.py#L319) · [订单更新器](../dataset/updater/order_data_to_parquet.py#L971) · [配置暂存](../dataset/updater/order_config_to_parquet.py#L582) · [归因写入](../dataset/updater/lock_attribution_data_to_parquet.py#L290) · [上险事务](../dataset/updater/update_tp_and_mix_ways_tableau.py#L469)

### 4.2 生产护栏、幂等与结果校验

| 检查 | 现行契约及缺口 |
| --- | --- |
| 生产目录与授权 | adapter 由本机包位置绑定仓库根目录；production 要求 `.git` 目录、git toplevel、Makefile、虚拟环境及 updater/registry，拒绝 linked worktree 与 submodule。根目录检查允许其他结构符合的独立 checkout，生产根、可执行文件及环境应由宿主管理。Source、人类身份、明确写入授权和 Job 白名单由 DSH 校验；`requested_by` 为留痕字段。 |
| 执行锁 | 五项在 `run_job` 使用默认 `data-refresh-daily.lock`，与 Service 快照复制共用。非阻塞 `flock` 冲突返回 `busy`。直接 Make、`monitor-sync` 与部分 scheduler 调用绕过这把锁；上险更新器另有自己的锁。运行记录在锁前写入，`latest` 可能被并发拒绝改写，应以 `run_id` 回读。 |
| 超时 | 内层刷新 1,800 秒，状态命令 180 秒，刷新子进程用新进程组，超时发送 TERM/KILL；外层 Job 2,100 秒，DSH 目前也等 35 分钟。外层超时、取消或调用方中断时，应按 run ID 查询终态。内层终止先观察 leader 的退出，缺少对仍存活子进程的回归；外层 timeout 无同级的进程组清理保证。 |
| 幂等 | 订单按订单号合并去重，配置按订单属性键覆盖并保留历史，上险按月替换且有恢复清单。以上支撑同一批输入的业务粒度重跑。Service `run_id` 用于记录定位，重复提交可重跑或覆写记录；DSH 现有 Fast `executeTrigger` 用持久化 `fast-path:<triggerId>` 恢复同一运行。请求去重与数据自然键幂等需分别验收。 |
| 校验与结果完整性 | 每次执行读取 registry 前后状态并运行 `data-status`。其退出 0 表示状态采集结束。通用比较按行数、时点和 mtime 标记变更，以行数增加或时点推进判定 `new_data`。离线比较证实，前后都缺失、或行数从 3 变成不可读的 `None`，均无异常；若刷新和状态命令均为 0，可落入 `no_new_data`。配置/上险另有显式存在性门槛，daily/订单/归因缺这层。等行数、等截止的订正可能显示 `no_new_data`；mtime 变化仍可见。 |
| 部分写入 | 订单与归因更新器直接写正式 Parquet，daily 两步无事务。非零退出、校验失败或中断后文件可能已经变化；需要检查前后证据再处理。配置采用经回读的单文件原子发布，上险事务用跨层核验及回滚。 |

依据见 [生产根与固定命令](../jobs/production.py#L98) · [锁与超时](../jobs/production.py#L162) · [状态比较](../jobs/production.py#L282) · [执行与核验](../jobs/production.py#L375) · [服务调度](../workspace/utility_scripts/sales_scheduler.py#L195) · [DSH 持久化去重](../../dsh-superagent-prototype/src/app/business-jobs.ts#L367)。

### 4.3 现有可交接刷新合同

受管宿主在 Service 主 checkout 执行固定 argv，替换 `JOB_ID` 为上表固定 ID。

```bash
.venv/bin/python -m jobs.cli --job JOB_ID --format json
```

- **业务参数**为闭合空对象 `{"type":"object","properties":{},"additionalProperties":false}`。运行编号 `MASHANG_JOB_RUN_ID` 与操作者标识 `MASHANG_JOB_REQUESTED_BY` 为受管环境输入。路径、网络、时间预算、Make 环境属于宿主设置，用户请求只能选择已授权的作业范围。
- **结果**为外层 `job_id/status/returncode/summary_json` 与内层 production v1 记录。内层 `job/run_id/status/before/after/changed_datasets/new_data/latest_data_time/latest_data_time_by_dataset/warnings/error/record_path` 为主证据。正常 JSON stdout 消费 `summary_json`，中断后按受管 `run_id` 读取生产记录。adapter 只解析 JSON，外层 `ok` 也可能缺有效内层摘要。比对 ID、版本、终态和获授权的 `before/after` 键集合后再回执。
- **终态**内层 `success/no_new_data` 对应生产退出 0；`busy` 为 2；`failed/timeout/verification_failed` 通常为 1，CLI 顶层异常为 3。外层 CLI 把子进程非零汇总成退出 1，细分状态须读内层。允许错误回执缺表状态、耗时或摘要；`running` 是记录中的中间态，取消或等待超时可以先交付运行编号。拒绝未经核验的成功、将状态采集超时归入核验异常，恢复同请求时查询已有结果。
- **数据截止**按各表 `after[dataset].data_asof` 与 `data_asof_column` 回执。`order_data` 的 registry 时点取多种订单事件中的最大值，可能为小订或大定时间。若产品要求锁单专用截止，应补 `lock_time` 字段或另做只读读取。配置只给 mtime 和行数。上险给六表业务月，合同范围为自动获取上游可用的最新数据。
- **授权与交接**在 DSH 既有注册中，daily、配置、归因、上险均有固定 ID。配置与上险可按当前限定范围做独立验收和交付。订单单表 ID 已可离线校验参数和范围，在第 6 节所述修正通过后注册。生产操作需授权；允许顺序验证时仍应保持每个意图的写入范围。

依据见 [adapter 包装](../jobs/adapter.py#L197) · [CLI](../jobs/cli.py#L39) · [终态退出码](../jobs/production.py#L572) · [截止计算](../dataset/updater/dataset_registry.py#L199) · [DSH 运行器](../../dsh-superagent-prototype/src/app/business-jobs.ts#L195)。

## 5. P0.3 上市累计锁单

### 5.1 官方路径、业务定义与结果

- **权威计算在 Service。** `vehicle_sales_monitor.py` 调用 `workspace/utils/monitors/launch.py`。以 `series_group_logic` 的优先级对 `product_name` 分代。LS9 车系包含 `LS9` 与 `LS9M1`，“全新 LS9”优先归 `LS9M1`，“大F M0/M1”有明确映射，裸“大F”是家族。固定 CLI 的 `--series LS9` 查询 LS9 一代；面向用户时，应先根据原请求判断是否明确指定这一代。 [代际规则](../shared/schema/business_definition.json#L300) · [分类执行](../workspace/utils/orders/classification.py) · [监控入口](../workspace/business_scripts/vehicle_sales_monitor.py#L120)
- **上市日期、开放时刻与截止。** 上市日由 `time_periods[generation].end` 定义，现有 helper 缺 end 时依次回退 finish/start，该降级会将未确认上市误作正式窗口。目标代际开放时刻是上市日起首个符合条件的真实锁单，条件包括锁单前或同刻已付小订，且排除内部测试单；没有有效候选则回退上市日零点。对标代际采用配置的开放小时、分钟。锁单截止取请求日末与剔除测试单后全表最大 `lock_time` 的较早值，可能不同于该代际最后一笔锁单和 registry 多事件截止。开放时刻未直接出现在监控结果中。 [上市计算](../workspace/utils/monitors/launch.py#L35) · [截止与窗口](../workspace/utils/monitors/launch.py#L112) · [业务字典](../shared/schema/business_definition.json)
- **累计锁单、留存与用户车。** 窗口内按 `order_number` 去重，累计含退款已审批订单；`metrics.retention_kept` 以快照中的 `approve_refund_time` 为空计算，审批未完成仍计入。历史 `as_of` 只裁切锁单，后来审批的退款仍会从留存剔除。用户车按 `order_type == "用户车"` 取累计锁单子集，内部测试单按总部门店与假号组合或买方/车主占位号剔除。用户车占比应以累计锁单为分母；JSON 当前给计数及 `order_type_filled_ratio`，没有用户车占比。卡片在填充率低于 50% 时标记未回填，JSON 没有同等质量状态。 [锁单与留存](../workspace/utils/monitors/launch.py#L172) · [用户车和填充率](../workspace/utils/monitors/launch.py#L243) · [测试单规则](../workspace/utils/orders/filters.py#L62)
- **两种官方调用。** 本机 DSH Prepare Profile `launch-monitor` 与仓库示例相同，固定 `--dry-run --format json`，追加代际、强制 launch、Prepare 锁单截止日与临时 `--output`。计算读取 Ticket worktree 中的订单副本，stdout 可能混有卡片，消费保存的 JSON。Profile 的字段提取和断言仍由 Worker 执行，现有模板只覆盖累计及用户车。Service 已有显式 `--snapshot` 分支，强制 JSON、跳过 live 新鲜度、不生成/发送卡片。用这条路径才能直接获得快照版本、输入元数据和 `lock_cutoff`。当前定义从 checkout 加载，需一同绑定规则版本。 [Profile 示例](../../dsh-superagent-prototype/examples/workspace-profiles/mashang-service.example.json#L22) · [Prepare 历史验收](../../dsh-superagent-prototype/docs/012-prepare-acceptance.md) · [Service 快照分支](../workspace/business_scripts/vehicle_sales_monitor.py#L239)

### 5.2 离线回放

以下均通过 Service 快照 CLI 运行，使用 LS9 代际、全订单类型累计池并剔除内部测试单。用户车占比在审计中用两个返回计数核算。

| 快照 / 请求日 | 业务截止 | 累计锁单 | 用户车 | 用户车占比 | 审批后留存 |
| --- | --- | ---: | ---: | ---: | ---: |
| `a38788cc-ce3c-47b3-9f16-f2caf82e1eea` / 2026-11-09 | 2026-11-09 13:12:50 | 21,726 | 20,941 | 96.39% | 16,462 |
| `26402169-6c50-4957-96b4-0261de5c82d9` / 2026-11-16 | 2026-11-16 22:15:00 | 21,834 | 20,998 | 96.17% | 16,554 |
| `a38788cc…` / 2026-01-31 | 2026-01-31 23:59:59 | 12,805 | 12,334 | 96.32% | 9,028 |

第一个样本订单 Parquet 权限为 `0444`，SHA-256 前缀 `0a673b8cdac503fb`。按业务定义独立交叉核算，LS9 上市日为 2025-11-12，实际开放为 16:53:23，首行三个计数一致。对 2026-01-31 同一快照，如仅剔除在该时间点已审批退款的订单，留存是 10,192，现有 JSON 为 9,028，差 1,164 单。这说明 `as_of` 历史留存语义必须显式固定。历史 11-03 官方 Prepare 另有 21,655、20,872 的回执，对应不同快照时点。 [历史验收记录](../../dsh-superagent-prototype/docs/012-prepare-acceptance.md) · [留存规则](../shared/schema/reference/metric_definitions.md#上市监控累计留存锁单数)

未知 `BOGUS` 代际强制 launch 返回 `success`、上市日 `null`、全零且 checks 通过；已登记但在请求日未上市的 `LS9M1` 以及上市前的 LS9 也成功返回零。无效 `--as-of bad-date` 抛解析异常，stdout 无 JSON。快照中的去重检查以同一锁单集合核对 distinct 计数，能报告重复行，但不会验证冲突订单类型。上线前需区别未知代际、未上市、数据未覆盖和窗口内真实零。 [代际与日期处理](../workspace/business_scripts/vehicle_sales_monitor.py#L125) · [现有计算校验](../workspace/utils/monitors/launch.py#L350)

### 5.3 已有独立入口

从 Service 根目录执行。路径和日期由宿主传入，代际填写规范键。

```bash
.venv/bin/python -B workspace/business_scripts/vehicle_sales_monitor.py \
  --snapshot "$FAST_PATH_SNAPSHOT" --series LS9 --phase launch --force-phase --as-of 2026-11-09
```

消费者目前可检查 `scope.snapshot_version/inputs`，从 `result.monitors` 唯一选中请求代际与 `phase=launch`，读取 `metrics.launch/lock_cutoff/cumulative_lock_count/cumulative_user_car_lock_count/retention_kept/order_type_filled_count/order_type_filled_ratio/checks`。适用于输入已核验后的回放。出口 `partial_success` 仍可能为 0，须读 JSON 状态和各检查。现有入口具备独立计算能力，固定合同需要补齐输入、异常和度量字段，见下一节。 [Result Contract](共享规范/result_contract.md) · [JSON 输出](../workspace/business_scripts/vehicle_sales_monitor.py#L284)

## 6. 最小开发清单与 DSH 交接合同

以下查询合同是开发目标。本次交付中的现有可执行合同为第 4.3 节和第 5.3 节；配置通用查询可按第 7 节独立回放。两条查询在相同快照、相同规则版本、相同参数下应返回相同业务结果。生成时间及运行耗时属于运行元数据。

| 顺序与归属 | 最小改动 | 完成标准 |
| --- | --- | --- |
| 1 · Service 配置 Mix | 从 DSH 迁移已有通用查询的纯读取及业务计算，复用 Service 分类、产品与配置语义。严格校验时间窗、事件指标和参数组合；明确普通/留存锁单、代际/家族、缺失/冲突、双分母。沿用固定 LS8 入口的存量口径。 | 一个受管只读 CLI 覆盖约定变体。已有 Worker 样本同语义等值。保留固定 LS8 的历史回归，检查跨代际遇到未登记属性时的处理。 |
| 2 · Service 上市摘要 | 在现有快照分支或薄的只读入口上收敛参数，继续调用同一个上市算子。显式验证规范代际、业务上市日及开放时间，输出占比、低填充和留存的观测方式。 | 未知、未上市、覆盖不足、真实零有各自结构状态；入口能输出经过验证的唯一结果、开放时刻和精确锁单截止。 |
| 3 · Service 共用快照读入 | 两个查询复用现有 reader，接收经宿主验证的同目录 copy manifest。固定或验证关联的字典版本和哈希，要求数据集、字段、权限和哈希满足约定。对 link 可先由宿主选择 copy；如需支持 link，按既有受管路径与哈希约束接入。 | 快照替换、缺依赖或定义版本冲突时拒绝；准备一次即可执行；无 live 回退、生产刷新及外部推送。 |
| 4 · Service 数据刷新 | 优先补订单单表，再复用规则到 daily 与归因。对目标文件做存在、可读、主键/必需字段、行数及口径截止检查，订单/归因暂存核验后再发布，归因旧底座读取异常时停止发布。让 daily 回执带逐表完成情况。验证外层超时后的记录恢复和内层进程组终止。 | 空或损坏文件不会成为已完成状态；失败/超时能判定哪些产物已发布；单表无连带写入。配置与上险沿用现有合同。 |
| 5 · Service 与 DSH 调用边界 | DSH 复用按 Trigger 去重、授权和 run ID 回读。若开放其他调用方，Service 再提供同 run ID 的原子 claim/replay 并校验调用 ID；需要覆盖直接 updater 或调度并发时统一现有写入/快照锁的参与者。不同调用方的生产根和环境由宿主明确绑定。 | 同一授权请求重复到达只产生一个运行；调用方失联可恢复，另一个重叠刷新受锁拒绝或串行化。 |
| 后续 · DSH | 配置/上市引用 Service 固定 CLI，移除插件重复的汽车计算路径。独立订单刷新绑定 `data_refresh_order_data`，升级原线程回执以给出数据截止和运行编号。当前配置/上险注册可直接沿用。 | 原请求辨清范围，测试替身与真实入口使用同一 Schema，宿主从结构字段取数。 |

### 6.1 配置 Mix 只读合同草案

- **请求**闭合对象。首版要求单个规范 `generation` 和一个 `dimension`，支持 `seat_count/power_type/product_version/order_type` 或已登记的配置属性；由 Service 维护可用属性 ID。若启用家族，使用带显式 `family` 的另一个分支，记录覆盖代际和规则。业务上属家族的别名进入澄清或现有 Native。
- **指标与窗口**首版白名单为 `locked_orders` 及经 Service 明确定义的 `retained_locked_orders`，默认普通锁单。使用 `since_launch`（业务上市日）、`since_launch_open`（官方开放逻辑）、`last_7_days`、`last_30_days` 或显式 `range`。显式日期为有效日历日期，日窗为北京时间左闭右开，终止日包含当日。未登记上市日、混用时间参数或开始晚于结束应返回确定错误。开票/交付等现有候选后续逐项固定指标白名单。
- **订单过滤**可选明确 `order_type`。座位按动力查询时沿用现有 `group_by=power_type` 并使用对应子组作为分母。若需要仅返回指定动力，由 Service 约定该子组提取规则或增设经校验的座位场景参数。
- **输入绑定**由宿主传入只读 manifest、定义版本和适用的请求基准时间。请求 Schema 不接受路径、`refresh`、任意过滤表达式或未识别的属性。Service 入口依赖查询声明的数据资产，无需 Ticket、Worker 或 OpenCode。
- **回执**沿用 `status/scope/result/warnings/errors`，附契约版本和错误码。明确快照 ID、输入与规则版本、订单时间窗、指标截止、配置文件更新时间和匹配覆盖时点。返回 `total_orders/known_orders/missing_orders/conflict_orders/coverage` 及组别 `count/share_of_known/share_of_total`，比率为 0–1 小数，分母为零时返回 `null`。明确冲突归类规则。状态包含缺依赖、输入不合法、无订单、低覆盖、数据陈旧、校验失败及可用结果。使用 `partial_success` 时同时提供具体质量码。

### 6.2 上市累计锁单只读合同草案

- **请求**闭合对象 `{"generation":"LS9","as_of":"2026-11-09"}`。只允许一个规范代际。显式日期为有效北京时间日历日期，未传时采用已验证的订单锁单截止日，先解析为固定输入。用户输入若指向 LS9 家族或多代际，宿主先澄清。由宿主传入订单快照与规则版本，禁止覆盖生产路径及启用通知。
- **回执**至少包含 `generation/launch_date/launch_open_at/launch_open_source/requested_as_of/lock_cutoff/cumulative_lock_count/user_car_lock_count/user_car_share/retained_lock_count/retention_basis/order_type_filled_ratio`、测试单规则、快照版本、输入哈希和规则版本。有累计分母且订单类型可用时，`user_car_share = user_car_lock_count / cumulative_lock_count`，低填充或分母为零给 `null` 和明确状态，保留可核对的原始计数。
- **留存和异常**首版可沿用当前治理口径 `retention_basis=snapshot_refund_status`。明确用户要历史时点留存时，使用专门的事件时点口径及回归后再开放。未确认上市、未到上市、缺覆盖及字段异常均有明确状态。只有上市窗口有效且数据已覆盖的空样本才可交付真实零。

## 7. 独立执行验收方案

### 本次已完成的证据

| 检查 | 证据与边界 |
| --- | --- |
| 配置 Mix | 独立 Python CLI 对历史快照运行 LS8、CM3、缺配置和未知车型；固定 Service 查询同版本回放；核对旧查询的指标误解析和日期宽松行为。 |
| 数据刷新 | 运行五个只读 `jobs.production check`、五个无效参数拒绝、纯函数步骤枚举及状态比较探针；查阅 13 条本地历史生产记录，核对单表 scope 与历史上险业务月。 |
| 上市锁单 | 两份历史只读快照实际运行，另用早期日期、未上市、未知代际和无效日期复现边界。对 LS9 一个完整窗口和一个历史截面用快照列独立复核。 |
| 自动化覆盖审阅 | Service 有快照缺件/替换、LS8 缺配分母、上市只读且不发卡的测试；生产 Job 有正常、无新增、失败、超时、互斥、linked worktree、配置 scope 及 adapter 包装测试；上险有历史保护、回滚与恢复。DSH 有 Prepare、生产权限、快照绑定、Job 恢复与 data-prep 查询样例。现有套件只做源码审阅，DSH 019 的历史测试结果属于上游审计。 |

覆盖来源见 [LS8 用例](../jobs/tests/test_ls8_mix.py) · [快照用例](../jobs/tests/test_snapshot.py) · [上市快照用例](../workspace/tests/test_vehicle_sales_monitor.py#L978) · [生产 Job 用例](../jobs/tests/test_production_job.py) · [Daily 步骤用例](../workspace/tests/test_daily_data_pipeline.py#L621) · [上险事务用例](../tests/test_tp_and_mix_ways_raw_guard.py) · [DSH Prepare 用例](../../dsh-superagent-prototype/tests/prepare.spec.ts) · [DSH Job 用例](../../dsh-superagent-prototype/tests/business-jobs.spec.ts) · [DSH 查询验证样例](../../dsh-superagent-prototype/plugins/dsh-data-prep/dev/verify-query.mjs)。

### 后续用于注册的验收

1. **冻结输入。** 从历史结果抽取小规模去标识 fixtures，固定数据哈希、定义哈希、北京时间及参数，保留已知结果。完整版本数据继续使用本机既有受管快照。用同一组输入重复执行，忽略运行元数据后结构结果一致；核对生产目录文件清单与通知调用次数无变化。
2. **直接运行查询。** 使用 Service Python、生产入口形式和测试快照，不启动 Agent Loop。配置覆盖 LS8 增程座位、CM3 内饰、订单类型、普通/留存、含末日、重号、缺值、冲突、缺表、未登记属性与快照篡改。核对已知分母、全量分母、缺失与冲突闭合。上市覆盖 LS9 及 LS9M1 代际、开启前及首单、申请退款未审批、观察日前后审批、测试单、低填充、真实零以及无效参数。比较现行官方结果；历史留存口径有变动时另提供基准。
3. **模拟刷新。** 在临时主 checkout 用固定 Make 目标和 updater 替身产生 Parquet/CSV；记录 argv、文件指纹、锁和生产 JSON。五项各跑成功、无新增、失败；对 daily 模拟第二步失败，对订单测试清空/损坏结果、同截止内容订正及只有订单数据发生变化，对归因测试旧底座不可读，对上险测试缺月和中断恢复。额外验证 busy、重复 run ID、宿主恢复、根路径拒绝与超时后子进程收敛。需要重跑的业务更新按授权范围和状态决定。
4. **独立宿主接受测试。** 用受管宿主直接传结构参数与快照。两条查询各一次准备、一次查询、零生产刷新、零飞书推送。刷新请求绑定单 Job ID，返回前后截止、是否新增、终态和运行编号。检查未授权和同触发重送。生产回放在开发修正和离线验收通过后单独授权。

### 本机回放入口

从 Service 根目录运行。`FAST_PATH_SNAPSHOT` 指向已存在的历史 `snapshot.json`，`ORDER_CONFIG_REQUEST_JSON` 是审计者构造的 JSON，含 `business_root`、已核验的 `snapshot_dir`、`refresh:false` 与第 3.2 节参数。三个历史版本可按版本号在本机 DSH `business-jobs/snapshots` 或 `data-prep/snapshots` 中定位。

```bash
.venv/bin/python -B -m jobs.ls8_mix --snapshot "$FAST_PATH_SNAPSHOT"
.venv/bin/python -B ../dsh-superagent-prototype/plugins/order-config-ratio/query.py --request "$ORDER_CONFIG_REQUEST_JSON"
.venv/bin/python -B -m jobs.production check data-refresh-order-data --repo-root "$PWD"
```

本轮未启动真实数据刷新、修改 DSH、运行 Decision 或推送外部消息。报告的成熟度以可核对源码、离线查询和本地历史记录为证据，真实生产流量验收仍按独立任务处理。
