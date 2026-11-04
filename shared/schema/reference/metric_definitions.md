# Metric Definitions — 核心指标口径

> 权威来源: `shared/schema/metrics.json`、`shared/schema/business_definition.json`、`shared/operators/registry.json`
> 本文是语义视图：口径变更先改 schema，再同步本文。
> 数据字典: `python mashang_workspace/utility_scripts/data_dictionary.py`

## 计数类指标

### 锁单数 / 锁单量

- **业务含义**：用户最终确认锁定的订单数量
- **计算口径**：`COUNTD(order_number WHERE lock_time IS NOT NULL)`
- **数据集**：`order_data.parquet`
- **时间字段**：`lock_time`
- **常用别名**：锁单量, 锁单, 订单锁单
- **参考脚本**：`mashang_workspace/business_scripts/daily_lock_count.py`
- **注意事项**：区分于"订单计数"（order_create_date），锁单以 lock_time 为准
- **去重口径**：同一 `order_number` 多行只计一次；所有脚本统一按 `order_number` 去重，不用行数。若锁单行数与唯一 `order_number` 数不一致，先审计再出数。
- **研究脚本**：`mashang_workspace/research_scripts/quick_lock_ratio.py` 等研究脚本复用同一去重底座。

### 交付数

- **业务含义**：已完成车辆交付的订单数
- **计算口径**：`count(order_number)` WHERE `delivery_date IS NOT NULL`
- **数据集**：`order_data.parquet`
- **时间字段**：`delivery_date`

### 开票数

- **业务含义**：已完成发票上传的订单数
- **计算口径**：`count(order_number)` WHERE `invoice_upload_time IS NOT NULL`
- **数据集**：`order_data.parquet`
- **时间字段**：`invoice_upload_time`

### 小订数

- **业务含义**：支付意向金的订单数
- **计算口径**：`count(order_number)` WHERE `intention_payment_time IS NOT NULL`
- **数据集**：`order_data.parquet`
- **时间字段**：`intention_payment_time`

### 大定数

- **业务含义**：支付正式定金的订单数
- **计算口径**：`count(order_number)` WHERE `deposit_payment_time IS NOT NULL`
- **数据集**：`order_data.parquet`
- **时间字段**：`deposit_payment_time`

## 线索类指标

> **两套下发线索数据集，按粒度选用，勿混用：**
>
> | 口径 | 数据集 | 粒度 | 可拆分 | 适用问题 |
> | --- | --- | --- | --- | --- |
> | 门店级 | `dataset/store_daily_leads.csv` | 门店 × 日 | 否（无渠道拆分） | 门店排名、单店线索走势、门店经营观察、门店线索×小订四象限 |
> | 全局渠道级 | `dataset/assign_data.csv` | 全局 × 日 | 门店渠道 / 平台 / APP小程序 / 快慢闪 / 直播 + 当日/7/30 日试驾与锁单 | 总量、渠道结构、快慢闪、直播、渠道转化 |
>
> - 更新入口：门店级 `dataset/updater/store_daily_leads_to_csv.py`（`--mobile` 非办公网）；全局级 `dataset/updater/assign_data_to_csv.py`（`--mobile` 非办公网）。试驾数据（`dataset/test_drive_data.csv`）由 `dataset/updater/test_drive_data_to_csv.py` 独立更新。
> - 互校：完整日两套总量应接近（如 2026-10-02 分别为 22,028 / 22,042）。
> - 注意：`assign_data.csv` 的 `下发线索数（门店）` 是**全局中「门店」这一个渠道**，**不等于** `store_daily_leads.csv` 的门店级明细。

### 门店身份关联（2026-11 code 接入）

- Tableau 门店级视图必须提供 `lc_dealer_name`、`lc_dealer_code`、`lc_bloc_name`、`日(lc_assign_time_min)`、`下发线索数`。
- `dataset/updater/store_daily_leads_to_csv.py` 保留为 `门店 / 日期 / 下发线索数 / 门店代码 / 经销商主体`；后续滚动刷新自动保留 code 和 Bloc。缺列、空身份、同店同日冲突阻断写盘。
- 仍按门店×日期增量覆盖。旧三列历史自动兼容，身份字段留空；不得用新窗口身份回填历史主体。
- 统一消费 `shared/loaders/store_info_loader.py::resolve_dealer_info`：显式 code 或线索库原始简称的最新已观测 code 优先关联主数据 `Dealer Code`，Bloc 做一致性校验。已知编码缺失/不唯一、主体冲突、同店最新日多编码时返回未匹配，不回退模糊名称。
- 没有 code 观测的门店兼容原名称解析；该回退仍可能存在简称歧义。身份查找优先精确原名；简称入口可清除明确的年份、档期、换铺标记后关联已观测身份，仅接受唯一 code/Bloc 组合（传入 Bloc 可进一步限定）。多个候选或冲突观测返回未匹配；保留括号里的投资人等身份信息，不做名称子串扩展。
- 默认身份为该简称最新已观测记录；可传 `as_of=YYYY-MM-DD` 限制观测截止日。门店主数据仍为当前快照，不代表历史状态重建。线索库无观测的日期不视为 code 归属的证明。
- 已运行的长驻进程需重新加载修改后的程序；线索身份文件原子刷新后，loader 按文件时间和大小自动失效身份缓存。
- 独立校验：`.venv/bin/python dataset/updater/store_daily_leads_to_csv.py --dry-run [--mobile]`；通过后去掉 `--dry-run` 执行正式增量更新。全量更新入口仍为 `make allupdate`。

### 下发线索数

- **业务含义**：系统下发给门店/渠道的线索总数
- **计算口径**：`sum(下发线索数)`
- **数据集**：`assign_data.csv`
- **时间字段**：`Assign Time 年/月/日`
- **别名**：总线索数, 线索总数, 线索量

### 下发线索数（门店）

- **业务含义**：门店渠道收到的线索数
- **计算口径**：`sum(下发线索数 (门店))`
- **数据集**：`assign_data.csv`
- **别名**：门店线索, 门店线索数

### 下发门店数

- **业务含义**：接收线索的门店总数
- **计算口径**：`sum(下发门店数)`
- **数据集**：`assign_data.csv`
- **时间字段**：`Assign Time 年/月/日`
- **别名**：门店下发数

### 门店当日锁单率

- **业务含义**：门店线索当日即锁单的比例
- **计算口径**：`下发线索当日锁单数（门店） / 下发线索数（门店）`
- **数据集**：`assign_data.csv`
- **别名**：门店锁单率, 门店线索当日锁单率

### 下发线索转化率

- **业务含义**：下发线索最终锁单的比例（整体线索转化）
- **计算口径**：由 `assign_conversion` 算子计算，基于 `assign_data.csv` 的线索/试驾/锁单预聚合字段
- **数据集**：`assign_data.csv`
- **时间字段**：`Assign Time 年/月/日`
- **常用别名**：线索转化率, 线索转换率
- **参考脚本**：`mashang_workspace/business_scripts/assign_conversion_analysis.py`

### 下发线索加权锁单率

- **业务含义**：按渠道/门店线索量加权的锁单率，避免小样本渠道拉偏
- **计算口径**：由 `weighted_lead_conversion` 算子计算
- **数据集**：`assign_data.csv`
- **时间字段**：`Assign Time 年/月/日`
- **常用别名**：加权锁单率, 线索加权锁单率

## ATP 类指标

### 平均开票价格 (ATP)

- **业务含义**：用户车订单的平均开票金额
- **计算口径**：`mean(invoice_amount)` WHERE `order_type='用户车'` AND `invoice_amount > 0`
- **数据集**：`order_data.parquet`
- **时间字段**：`invoice_upload_time`
- **别名**：开票均价, 平均开票金额, 均价
- **参考脚本**：`mashang_workspace/business_scripts/atp_price_report.py`

### 实际折扣率（权益价口径）

- **业务含义**：客户实付开票价相对「应然价」的让利幅度；应然价 = 上市期权益车价 + 全部选装挂牌价
- **计算口径**：`1 − Σ(invoice_amount) / Σ(expected_price)`（金额加权）
  - `MSRP` = 产品内 `Vehicle Price` **众数**（官方车价，不含选装）；同一产品名下出现多个 MSRP 时取众数并在 warnings 告警（说明上游产品名未区分 SKU）
  - `权益价` = `MSRP − 上市期 TVD 基准`
  - `应然价` = `权益价 + 选装挂牌`
- **样本口径**：`order_type='用户车'` AND 已开票（`invoice_upload_time` 非空）
- **负值含义**：开票价高于应然价（当期让利小于上市期权益），实测占比 < 0.1%
- **口径要点**：
  - 权益价锚定**上市期** TVD，而非当期 TVD（TVD 随车型老化单调增长，实测月增约 2,000~3,300 元/月）
  - 折扣率分母含选装挂牌，与分子（开票价含选装）量纲一致；**不用**「开票价 − 选装价」作分子，避免把赠送选装误当让利
  - 选装收费策略因车型、阶段而异：LS6 车漆+轮毂基本全赠送；LS8「奢华智选包」9,800 在 **2026-06-16 之前为实收**（净支付中位 +9,800），**之后不再单独加价**（净支付中位降至 0，7 月起转负）
  - 2026-11-04 起 Price 视图覆盖 2025-01 起，早期代际（CM1/DM0 及以前）仍因上市期无数据而回退近似基准
- **数据集**：`order_data.parquet` + `dataset/incoming/tableau/price_data_view.csv`（Tableau `core_metric_observation/Price`）
- **参考脚本**：`mashang_workspace/business_scripts/atp_price_report.py`（年度报告 `--report annual`）

## 算子类指标

### 在营门店数

- **业务含义**：30天滚动窗口内存在订单活动的活跃门店数
- **计算口径**：去重计数 store_name，窗口内存在订单且开店日 <= 当天
- **时间字段**：`order_create_date`

### 留存小订数

- **业务含义**：支付小订后在窗口结束时仍未退款的订单数
- **计算口径**：intention_payment_time 在预售期内，exit_time 为空或 >= 当日+1天
- **时间字段**：`intention_payment_time`

### 留存小订转化率

- **业务含义**：留存小订中最终锁单/交付的比例
- **计算口径**：留存小订中 lock_time 非空的比例

### 待开票未退订锁单数（状态指标）

- **业务含义**：系统当前处于"锁单 & 未开票 & 未退订"状态的订单数，纯事实状态计数（open_locked_orders）
- **计算口径**：`count(distinct order_number) WHERE lock_time IS NOT NULL AND invoice_upload_time IS NULL AND apply_refund_time IS NULL AND actual_refund_time IS NULL`
- **数据集**：`order_data.parquet`
- **时间字段**：`lock_time`
- **常用别名**：open_locked_orders, 待开票有效锁单数（历史名，已停用）
- **退订判定**：`apply_refund_time` 或 `actual_refund_time` 任一非空即视为已退订（与 `shared/schema/reference/business_glossary.md` 一致）
- **注意事项**：这是**纯状态指标**，只描述"账面上还有多少单处于该状态"，不含对兑现概率的任何判断。它不直接代表可交付量。

### 有效锁单率（质量指标）

- **业务含义**：当前 Backlog 预计最终兑现（开票）的比例，即"这些状态订单还有多少会真正成交"
- **计算口径**：`有效锁单当量 ÷ 待开票未退订锁单数`（Backlog realization rate）
- **数据集**：`order_data.parquet`
- **参考脚本**：`mashang_workspace/research_scripts/stalled_order_forecast.py`
- **常用别名**：Backlog 有效率, 有效待交付率, backlog_realization_rate
- **注意事项**：质量指标描述兑现概率，与状态指标的计数含义不同，二者不可混用。

### 有效锁单当量（预测指标）— Effective Locked Order Equivalent (ELOE)

- **业务含义**：当前 Backlog 预计能贡献多少未来开票。基于每个悬置订单的兑现概率累加：
  `ELOE = Σ P_i(最终开票 | 当前仍悬置)`，即把"账面订单数"折算为"概率化开票预期"
- **计算口径**：对每个待开票未退订订单估计 `P(最终开票 | Lock Age)`（v1 单变量），按 v2 扩展为 `P(最终开票 | Lock Age, Series)` 并做 sample-size shrinkage，逐单累加
- **数据集**：`order_data.parquet`
- **共享算子**：`shared/operators/effective_locked_orders.py`（metrics.json 中 `有效锁单当量` 的 `operator` 即指向它；生产核心在此）
- **参考脚本**：`mashang_workspace/research_scripts/stalled_order_forecast.py`（研究层消费者：验证 / 图表 / CLI）
- **派生指标**：Backlog 有效率 = ELOE ÷ 悬置池；风险暴露量 = 悬置池 − ELOE
- **常用别名**：ELOE, effective_locked_orders, 有效待交付当量, 有效Backlog当量
- **模型方法**：基于历史锁单的 **conditional outcome curve / landmark probability**——在 Lock Age=t 时仍有效（未开票未退订）的历史订单中，最终开票的比例。注意：v1 的经验比例尚不等同于完整的竞争风险生存模型（cause-specific hazard / CIF），后者需按时间动态估计开票与退订两个 competing events 后才可正式命名，文档与代码注释应保持这一严谨性。
- **注意事项**：这是预测指标，对账龄越久的订单打折越狠（如 >90 天开票概率仅个位数）。它与前端锁单预测（`mashang_workspace/research_scripts/structured_business_forecast.py`）衔接，构成 Demand → Order → Invoice/Delivery 预测链。



### 预测锁单数

- **业务含义**：基于成熟度曲线修正右删失后预测的最终30日锁单数
- **计算口径**：三段式: age>=30d 用原始值, 7d≤age<30d 用 lock_7÷r7, age<7d 用 0.5×avg+0.5×lock0
- **数据集**：`assign_data.csv`
- **参考脚本**：`mashang_workspace/research_scripts/cohort_forecast.py`, `mashang_workspace/research_scripts/lock_predict_backtest.py`

### 店均锁单数

- **业务含义**：每日锁单数 ÷ 在营门店数
- **计算口径**：日锁单数 / 在营门店数（30天窗口活跃门店）

### 年龄代际分布

- **业务含义**：用户年龄代际分组统计
- **分组**：00后/95后/90后/85后/80后/75后/70后/65后/60前

### 城市线级分布

- **业务含义**：城市等级分组统计
- **分组**：一线/新一线/二线/三线及以下

### 省份 TopK 占比

- **业务含义**：TopK 省份的锁单集中度
- **计算口径**：将城市映射到省份，按锁单数排序取 TopK

## 用户画像指标

### 购车人年龄

- **业务含义**：订单购车人年龄（均值）
- **计算口径**：`mean(buyer_age)`
- **数据集**：`order_data.parquet`
- **时间字段**：`lock_time`
- **别名**：订单年龄, 订单用户年龄

### 车主年龄

- **业务含义**：车主年龄（均值）
- **计算口径**：`mean(owner_age)`
- **数据集**：`order_data.parquet`
- **时间字段**：`lock_time`

### 复购锁单数

- **业务含义**：老车主再次购车并完成锁单的订单数
- **计算口径**：`repurchase` 算子的 `summary.repeat`
- **数据集**：`order_data.parquet`
- **时间字段**：`lock_time`
- **共享算子**：`shared/operators/repurchase.py`
- **别名**：复购

### 复购率

- **业务含义**：锁单用户中老车主复购的占比
- **计算口径**：`repurchase` 算子的 `summary.repeat_rate`
- **数据集**：`order_data.parquet`
- **时间字段**：`lock_time`
- **共享算子**：`shared/operators/repurchase.py`
- **常用别名**：老车主复购率, 复购占比

## 派生指标

### 下发线索至锁单时间间隔（天）

- **计算口径**：`(lock_time - first_assign_time)` 换算为天，负值视为无效
- **数据集**：`order_data.parquet`
- **字段**：`first_assign_lock_time`
- **别名**：线索转锁单天数, 下发至锁单天数
- **说明**：均值/中位数分析时，时间筛选通常基于 `lock_time`

## 派生率指标

| 指标名称 | 分子 | 分母 | 别名 |
|----------|------|------|------|
| 门店下发线索数占比 | 下发线索数（门店） | 下发线索数 | 门店线索占比 |
| 下发线索当日试驾率 | 下发线索当日试驾数 | 下发线索数 | 当日试驾率, 试驾率 |
| 下发线索7日锁单率 | 下发线索7日锁单数 | 下发线索数 | 七日锁单率, 7日锁单率 |
| 下发线索30日锁单率 | 下发线索30日锁单数 | 下发线索数 | 三十日锁单率, 30日锁单率 |
| 门店当日锁单率 | 下发线索当日锁单数（门店） | 下发线索数（门店） | 门店锁单率 |
| 有效锁单率 | 有效锁单当量 | 待开票未退订锁单数 | Backlog有效率, 有效待交付率 |

## 数据筛选口径

### 用户车

- **业务含义**：终端零售客户订单（排除大客户/集团员工/经销商员工/试驾车/展车/仅批售/海外/享道等）
- **筛选口径**：`order_type = '用户车'`
- **数据集**：`order_data.parquet`
- **常用场景**：锁单数、开票数、交付数的零售口径汇总
- **注意事项**：ATP（平均开票价格）默认即为用户车口径

### 对公批售（企业订单）

- **业务含义**：企业客户批量订单，owner_identity_no 为统一社会信用代码（企业税号），不具有个人锁单流程（lock_time 为空），order_type 通常也为空。
- **判定口径**：`owner_identity_no` 为 18 位且包含非末尾 X 的字母（A-Z），即判定为统一社会信用代码。
- **数据集**：`order_data.parquet`
- **筛选字段**：`owner_identity_no`
- **判定函数**：`utils.business.is_corporate_owner()`
- **数据来源**：`shared/schema/business_definition.json` 中 `corporate_order_detection` 定义
- **注意事项**：此类订单在计算终端零售开票数时应排除（仅统计用户车口径）。对公批售订单有完整物流链路（real_in_dc_time, out_delivery_center_time, order_binding_time 等），但缺少 lock_time 和 order_type。

### 用户车标准输出格式

涉及锁单/开票/交付三口径的分车系汇总，统一按以下格式输出：

| 车系 | 锁单 | 开票 | 交付 |
|---|---|---|---|
| LS6 | N | N | N |
| LS8 | N | N | N |
| LS9 | N | N | N |
| L6 | N | N | N |
| ... | N | N | N |
| **合计** | **N** | **N** | **N** |

规则：
- 仅输出有数据的车系，零值车系不显示
- 锁单时间字段：`lock_time`
- 开票时间字段：`invoice_upload_time`
- 交付时间字段：`delivery_date`
- `series` 值含 `LS9Hyper` 的记录默认归入 LS9 统计

## 如何查看数据字段

运行以下命令获取所有数据集的字段清单：

```bash
python mashang_workspace/utility_scripts/data_dictionary.py
python mashang_workspace/utility_scripts/data_dictionary.py --format csv --output outputs/tables/
```
