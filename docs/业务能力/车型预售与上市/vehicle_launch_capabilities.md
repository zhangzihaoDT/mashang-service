# 车型预售与上市｜统一入口与业务边界

> **登记不是执行授权。** 本页描述现有能力及真实 CLI；不修改算法、不创建 Job、不触发数据刷新或飞书推送。
> 机器可读专题入口：[`workspace/registry/vehicle_launch_capabilities.json`](../../../workspace/registry/vehicle_launch_capabilities.json)。
> 能力成熟度仍由全局 `workspace/registry/capability_registry.json` 管理，生产 Job 仍由 `jobs/config/jobs_config.json` 管理。

## 一套口径（SSOT）

唯一权威业务时间定义：`shared/schema/business_definition.json` 中的 `time_periods.{generation}`。

| 键 | 业务含义 | 使用场景 |
|---|---|---|
| `start` | **预售开放／资源投入起点** | 预售前风险诊断、预售观察窗口 |
| `end` | **正式上市日** | 上市以来锁单、跨代际 D1..DN 对齐 |
| `finish` | **上市权益结束日** | 上市节奏阶段归因 |

代际归属由 `series_group_logic` 决定；预售窗口另参照 `presale_periods`。没有 `start` 的老车型不能臆造预售日；没有 `end` 的代际（如未确认上市的车型）不得由首笔锁单、`start` 或 `finish` 推断正式上市。研究的零售锁单与监控的全口径锁单、集团全渠道订单是不同指标，**不能在未转换口径时横向比较**。

**预售启动风险快照为何使用 `start`：**预售开始投入资源，通常比上市早约 2–6 周，需在该日**之前最近一个历史观察点**发现 At-Risk Backlog 与存量池质量问题，以保留清积压的主动干预窗口；`end` 不符合本报告目标。注意报告中的全历史风险分位是研究参照，若需要严格“当时可知”前瞻评估，还应检验历史分位基准是否包含后续观察数据。

## 两类业务能力：四份报告 + 一项监控

| ID | 独立入口 | 解决的问题 | 核心时间基准 | 数据与关键限制 |
|---|---|---|---|---|
| `launch_presale_risk_snapshot` | `workspace/research_scripts/launch_risk_snapshot.py` | **预售前置诊断**：风险订单池是否需要清理？ | `start` 前最近观察点 | 历史 At-Risk Backlog；当前不支持按单一代际筛选 |
| `launch_cumulative_lock_compare` | `workspace/research_scripts/launch_cumulative_lock_compare.py` | **上市表现评估**：最新代际相较前代的累计锁单、转化、画像、网络变化？ | `end`，上市后 D1..DN | 默认 DM0/DM1/DM2，`--gens` 可改 |
| `launch_rhythm_incremental_analysis` | `workspace/research_scripts/launch_rhythm_incremental_analysis.py` | **节奏增量归因**：预售、上市爆发、权益期分别贡献多少增量？ | `start/end/finish` | 当前固定七代际 + DM2 参照；无 `--gens` |
| `launch_group_order_compare` | `workspace/research_scripts/group_order_launch_compare.py` | **集团横向对标**：不同车型在同上市后天数的每日和累计订单？ | 各车型比较 `t0` | 观星台全渠道订单，且 MG 07 / ID.ERA 5S 的 `t0` 为近似基准 |
| `vehicle_sales_monitor` | `workspace/business_scripts/vehicle_sales_monitor.py` | **运营监控**：当前预售／上市阶段锁单、新鲜度和飞书卡片？ | 预售 `start`，上市 `end` | 生产运行可能对外推送；先 `--dry-run` |

前四条属于 **research_reports 研究分析能力**，最后一条属于 **monitoring 业务监控能力**。不是五份报告。`launch_rhythm_incremental_html.py` 为渲染依赖，而非独立报告入口。`presale_cumulative_order_compare.py` 是预售上游分析，不算本专题四报告；`workspace/scratch/launch_*.py` 为临时脚本，不纳入稳定入口。

## 从仓库根目录运行的示例

以下为**已有脚本**的真实 CLI，不意味着已验证数据输出；所有脚本应先确认本地数据存在、统计截止时间及输出文件。

```bash
# 1. 预售启动风险快照（HTML 写到 workspace/outputs/reports）
.venv/bin/python workspace/research_scripts/launch_risk_snapshot.py --format html

# 2. 上市后累计零售锁单跨代际表现（可指定上市先后顺序）
.venv/bin/python workspace/research_scripts/launch_cumulative_lock_compare.py --gens DM0 DM1 DM2 --html

# 3. 上市节奏增量贡献：CSV + JSON Contract + HTML
.venv/bin/python workspace/research_scripts/launch_rhythm_incremental_analysis.py --format json --html

# 4. 集团全渠道订单同上市后天数对比：须预先备好重点车型（订单）.csv
.venv/bin/python workspace/research_scripts/group_order_launch_compare.py --html

# 5. 仅预览监控卡片，无刷新、无飞书发送
.venv/bin/python workspace/business_scripts/vehicle_sales_monitor.py --series CM3 --phase launch --dry-run --format json
```

重要差异：`launch_rhythm_incremental_analysis.py --format json` 输出 CSV 和 JSON 契约，但**只有显式加 `--html` 才生成 HTML**。风险报告的 `--format json` 则打印 JSON 到 stdout，不是自动落盘。监控不生产 HTML，`--output` 可以保存 Result Contract。

监控已有 `make sales-monitor`、`make sales-monitor-dry-run` 入口；`make monitor-sync SERIES=CM3 PHASE=launch` **先刷新写入订单表，再发送飞书卡**，与只读预览不同，必须按生产权限执行。实时监控会检查数据新鲜度；显式 `--as-of` 走历史观察口径并跳过实时新鲜度 gate。底层 `utils/monitors/launch.py:resolve_launch_date` 存在 `end → finish → start` 回退，**不能将回退日期当作正式上市日**；严格上市研究和生产入口须明确验证 `end`。

## 选择规则（供人工与后续 Skill / DSH）

1. 问“预售开放前存量订单池是否健康？” → `launch_presale_risk_snapshot`，不改为 `end`。
2. 问“上市 N 天锁单与前代差多少？” → `launch_cumulative_lock_compare`，用内部零售锁单、`end` 对齐。
3. 问“上市活动究竟带来多少增量？” → `launch_rhythm_incremental_analysis`，注意固定研究代际。
4. 问“集团其他品牌新车型相比怎么样？” → `launch_group_order_compare`，显式标记全渠道订单及近似 `t0`。
5. 问“当前预售／上市情况如何，能否推送？” → `vehicle_sales_monitor`，先 dry-run；刷新／推送需独立授权。

## 本阶段边界与待办

当前只完成**统一入口与业务说明**，没有新增业务计算、修改日期逻辑、加入全局成熟度注册表或新增生产 Job。下一阶段如果要暴露为 Agent Skill，必须映射本专题 ID 与真实 CLI，再做参数校验、数据新鲜度、输出产物登记和权限隔离；如果要通过 Hub／DSH 正式执行，必须另行注册 `jobs/` 契约并验收。不得把专题注册表中的“已登记”误认为“已授权自动执行”。

## 专题方法

- [上市节奏增量分析方法](launch_rhythm_incremental_analysis.md)
- [L6 M2 预售分析框架](L6_M2_预售情况汇报分析框架.md)
