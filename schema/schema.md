# 数据集指标与维度定义

本文档定义了数据集的业务逻辑、指标计算规则及可用维度，用于指导 Planning Agent 生成准确的分析计划。

## 1. 可用指标 (Metrics)

用于计算总和、平均值、计数等数值指标。指标分为两层：

| 层级 | 说明 | 示例 |
| :--- | :--- | :--- |
| **原始指标** | field + agg 直接构成，不含业务过滤条件 | sum(invoice_amount), count(order_number) |
| **业务 DSL 指标** | 原始指标 + 业务口径规则（强制过滤条件、派生逻辑、算子运算） | 锁单量 = count(order_number) WHERE lock_time IS NOT NULL |

### 1.1 原始指标 (Raw Metrics)

由数据集的原始字段和聚合函数直接构成，LLM 可在此基础上附加用户查询中的过滤条件。

- **订单计数**: `order_number` 计数
- **开票金额**: `invoice_amount` 求和
- **购车人年龄**: `buyer_age` (平均/中位数/分布)
- **车主年龄**: `owner_age` (平均/中位数/分布)

### 1.2 业务 DSL 指标 (Business DSL Metrics)

在原始指标基础上附加了固定的业务口径规则。LLM 必须严格按以下 DSL 映射生成计划。

#### 1.2.1 计数类 — `order_number` count + 时间字段非空

| 指标名 | 聚合 | 强制过滤条件 | 时间字段 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| **锁单量** | count(order_number) | `lock_time` IS NOT NULL | `lock_time` | |
| **交付数** | count(order_number) | `delivery_date` IS NOT NULL | `delivery_date` | |
| **开票数** | count(order_number) | `invoice_upload_time` IS NOT NULL | `invoice_upload_time` | 不要用 order_create_date |
| **小订数** | count(order_number) | `intention_payment_time` IS NOT NULL | `intention_payment_time` | |
| **大定数** | count(order_number) | `deposit_payment_time` IS NOT NULL | `deposit_payment_time` | |

#### 1.2.2 均值类 — mean + 业务过滤

| 指标名 | 聚合 | 强制过滤条件 | 时间字段 |
| :--- | :--- | :--- | :--- |
| **平均开票价格** | mean(invoice_amount) | `order_type == '用户车'`, `invoice_amount > 0` | `invoice_upload_time` |

#### 1.2.3 算子类 — 由固定算子计算（不走通用 DSL 聚合）

当用户查询匹配以下算子时，LLM 应生成带对应 `statistics.type` / `analysis_intent` / 算子的 plan，然后将 `statistics` 置为空或不设置，让路由层自动匹配算子（路由优先级确保算子优先于通用 DSL 聚合）。

- **留存小订单数**: 统计在指定时间窗口内支付小订，且在时间窗口结束时未发生退款的独立订单数量。
  - 算子：`operators/retained_intention.py`
  - 时间字段：`intention_payment_time`
  - 如果过滤条件包含 `series` 等于某车型（如 CM2, LS8），算子内部优先使用 `series_group_logic` 精确匹配。
- **留存小订转化率**: 在留存小订基础上，进一步计算从小订到锁单/交付的转化漏斗。
  - 算子：`operators/retained_intention.py`（`run_retained_intention_conversion_operator`）
  - 时间字段：`intention_payment_time`（小订窗口）、`lock_time`（锁单窗口）
  - 需要同时指定小订时间窗口和锁单时间窗口。
- **在营门店数**: 以目标日 `d` 统计"最近 30 天内有活动且在 `d` 当天已开店的门店数"。
  - 算子：`operators/active_store.py`
  - 活动日字段：`order_create_date`
  - 仅保留 `store_name` 与活动日非空记录。
  - 每个门店开店日取 `store_create_date` 的最小值。
  - 活跃门店集合为活动日落在 `[d-29, d]` 的门店。
  - 在营判定为 `open_date <= d`，最终结果为门店 `store_name` 去重计数。
  - 不要把 `store_create_date` 直接当作统计时间字段做简单 count。
- **年龄代际分布**: 根据身份证号或年龄字段推算出生年份，按 00后/95后/90后/…/60前 分组统计人数及占比。
  - 算子：`operators/age_cohort.py`
  - 默认年龄字段：`owner_age`；用户明确提到"购车人年龄/订单用户年龄"时使用 `buyer_age`。
  - 支持车系过滤。
- **城市线级分布**: 将城市按内置 mapping 归为 一线/新一线/二线/三线及以下 四档，统计各档人数及占比。
  - 算子：`operators/city_tier.py`
  - 默认城市字段：`license_city`；用户明确提到"门店城市"时使用 `store_city`。
  - 支持车系过滤。
- **省份 TopK 占比**: 将城市映射到省份，按用户指定的 TopK 统计省份集中度及占比。
  - 算子：`operators/province_topk.py`
  - 默认城市字段：`license_city`；用户明确提到"门店城市"时使用 `store_city`。
  - TopK 从用户查询中解析（如"前5"、"Top 3"）。
  - 支持车系过滤。
- **店均锁单数**: 日锁单数 / 在营门店数，计算窗口内每日店均锁单量及整体均值。
  - 算子：`operators/store_avg_lock.py`
  - 在营门店定义：当天及往前29天存在订单活动且已开业的门店。
  - 时间字段：`lock_time`
- **下发线索转化率**: 基于 assign_data 计算下发线索在各渠道、各窗口（当日/7日/30日）的试驾率与锁单率。
  - 算子：`operators/assign_conversion.py`
  - 数据集：`assign_data`
  - 输出共13项比率，均由算子根据 assign_data 原始字段（下发线索数、下发线索当日试驾数、下发线索 7/30 日锁单数等）实时计算得出：门店线索占比、下发线索当日试驾率、下发 (门店)线索当日锁单率、下发线索7日锁单率、下发线索30日锁单率，以及分渠道（门店/直播/平台/APP小程序/快慢闪）的7日/30日锁单率。
- **下发线索加权锁单率**: 0.4 × (门店当日锁单率 × 门店线索占比) + 0.4 × 下发线索7日锁单率 + 0.2 × 下发线索30日锁单率。
  - 算子：`operators/weighted_lead_conversion.py`
  - 数据集：`assign_data`
- **预测锁单数（简称）** / **下发线索成熟度预测锁单数（标准名）** / **Lead Maturity Forecast Locks（英文）**: 基于成熟度曲线（Maturity Curve）修正右删失数据，对未完全成熟的下发线索 cohort（age < 30d）预测其最终30日锁单数。
  - 算子：`operators/mature_lock_prediction.py`
  - 数据集：`assign_data`
  - 三段式规则，无指数模型：
    - **age >= 30d**: 直接使用原始30日锁单数（已成熟）
    - **7d <= age < 30d**: 原始7日锁单数 ÷ r7（r7 = 历史完全成熟 cohort 中 lock_7 / lock_30）
    - **age < 7d**: 0.5 × (线索数 × 历史平均30日锁单率) + 0.5 × (当日锁单数 ÷ r0)（r0 = 历史完全成熟 cohort 中 lock0 / lock_30）
  - 输出：每日 cohort 的年龄、原始值、预测值、预测方法，以及窗口汇总统计和历史比率（avg_30d_rate, r7, r0）

#### 1.2.4 派生类 — 基于已有字段计算的二级指标

- **下发线索至锁单时间间隔(天)**: `first_assign_lock_time` (平均/中位数)
  - 定义：`(lock_time - first_assign_time)` 换算为天，负值视为无效。
  - 用途：衡量从首次下发线索到锁单的转化时长。
  - 时间筛选通常基于 `lock_time`。

### 1.3 外部线索指标 (仅限 assign_data, 预聚合字段)

这些字段已由 Tableau 数据源预计算，LLM 直接按字段名查询即可。

- `下发线索数`: 下发线索总数
- `下发线索当日试驾数`: 下发当日完成试驾的数量
- `下发线索 7 日试驾数`: 下发 7 日内完成试驾的数量
- `下发线索 7 日锁单数`: 下发 7 日内完成锁单的数量
- `下发线索 30日试驾数`: 下发 30 日内完成试驾的数量
- `下发线索 30 日锁单数`: 下发 30 日内完成锁单的数量
- `下发门店数`: 接收线索的门店总数
- `下发线索数 (门店)`: 门店渠道收到的线索总数
- `下发线索当日锁单数 (门店)`: 门店渠道线索当天即锁单的数量

## 2. 可用维度 (Dimensions)

用于分组、筛选和拆解分析。

### 产品与车型

- `product_name`: 产品名称 (如: 全新智己L6)
- `series`: 车型系列 (如: L6, LS6)
- `series_group_logic`: 二级车型分组（由 `business_definition.json: series_group_logic` 基于 `product_name` 规则生成，如 CM0/CM1/CM2/DM0/DM1 等；不保证是原始字段）。
- `product_type`: 燃料类型 / 动力形式。**注意：数据集中无此字段，需通过 product_name 模糊匹配生成。**
  - **增程**: `product_name` 包含 "52" 或 "66"。请使用正则匹配: `filters: [{"field": "product_name", "op": "matches", "value": "52|66"}]`。
  - **纯电**: `product_name` **不**包含 "52" 且 **不**包含 "66"。请使用正则匹配: `filters: [{"field": "product_name", "op": "not matches", "value": "52|66"}]`。
  - **Planning Agent 请注意**: 对于“增程”或“纯电”查询，必须使用 `matches` 或 `not matches` 操作符，并使用正则 `52|66`。不要生成多个 `contains` 过滤器（因为它们是 AND 关系）。

### 地理位置

- `store_city`: 门店城市
- `store_name`: 门店名称
- `parent_region_name`: 大区名称
- `license_city`: 上牌城市

### 渠道与客户

- `order_gender`: 购车人性别
- `owner_gender`: 车主性别
- `buyer_identity_no`: 购车人身份证号
- `owner_identity_no`: 车主身份证号

### 其他

- `order_type`: 订单类型
- `finance_product`: 金融产品
- `final_payment_way`: 尾款支付方式
- `main_lead_id`: 关联试驾表的主线索 ID
- `vin`: 车辆识别代码(VIN)

### 选配信息 (仅限 config_attribute.parquet)

- `Order Number`: 订单号（与 `order_data.parquet` 的 `order_number` 对应，但字段名不同）
- `Attribute`: 选配项名称
- `value`: 选配项取值（常见为“是/否”，也可能是具体配置值）
- `is_staff`: 是否员工单标记（布尔）

---

## 附录：原始字段 Schema 映射

### order_data.parquet (Total Rows: 445915)

| Column Name | Data Type | Description |
| :--- | :--- | :--- |
| order_number | string | 订单号 |
| invoice_amount | float64 | 开票金额 |
| main_lead_id | str | 关联试驾表的主线索 ID |
| series | str | 车型系列 |
| product_name | str | 产品名称 |
| parent_region_name | str | 大区名称 |
| store_name | str | 门店名称 |
| store_create_date | datetime64[ns] | 门店创建日期 |
| store_city | str | 门店城市 |
| license_city | str | 上牌城市 |
| first_assign_time | datetime64[ns] | 首次下发时间 |
| first_assign_lock_time | float64 | 下发线索至锁单时间间隔（天，二级指标=lock_time-first_assign_time） |
| first_touch_time | datetime64[ns] | 首次接触时间 |
| order_type | str | 订单类型 |
| buyer_identity_no | str | 购车人身份证号 |
| owner_identity_no | str | 车主身份证号 |
| final_payment_way | category | 尾款支付方式 |
| delivery_date | datetime64[ns] | 交付日期 |
| invoice_upload_time | datetime64[ns] | 发票上传时间 |
| first_test_drive_time | datetime64[ns] | 首次试驾时间 |
| final_payment_time | datetime64[ns] | 尾款支付时间 |
| finance_product | str | 金融产品 |
| approve_refund_time | datetime64[ns] | 审批退款时间 |
| apply_refund_time | datetime64[ns] | 申请退款时间 |
| actual_refund_time | datetime64[ns] | 实际退款时间 |
| order_create_date | datetime64[ns] | 订单创建日期 |
| vin | str | 车辆识别代码(VIN) |
| buyer_age | float64 | 购车人年龄 |
| owner_age | float64 | 车主年龄 |
| order_gender | str | 购车人性别 |
| owner_gender | str | 车主性别 |
| intention_payment_time | datetime64[ns] | 意向金支付时间 |
| intention_refund_time | datetime64[ns] | 意向金退款时间 |
| deposit_refund_time | datetime64[ns] | 大定退款时间 |
| deposit_payment_time | datetime64[ns] | 大定支付时间 |
| lock_time | datetime64[ns] | 锁单时间 |

### assign_data.csv (Total Rows: 1184)

| Column Name                      | Data Type | Description                         |
| :------------------------------- | :-------- | :---------------------------------- |
| Assign Time 年/月/日             | str       | 下发时间                            |
| 下发线索 30 日锁单数 (APP小程序) | int64     | 下发线索30日内锁单数量（APP小程序） |
| 下发线索 30 日锁单数 (平台)      | int64     | 下发线索30日内锁单数量（平台）      |
| 下发线索 30 日锁单数 (快慢闪)    | int64     | 下发线索30日内锁单数量（快慢闪）    |
| 下发线索 30 日锁单数 (直播)      | int64     | 下发线索30日内锁单数量（直播）      |
| 下发线索 30 日锁单数 (门店)      | int64     | 下发线索30日内锁单数量（门店）      |
| 下发线索 30 日锁单数             | int64     | 下发线索30日内锁单数量（合计）      |
| 下发线索 30日试驾数              | int64     | 下发线索30日内试驾数量              |
| 下发线索 7 日试驾数              | int64     | 下发线索7日内试驾数量               |
| 下发线索 7 日锁单数 (平台)       | int64     | 下发线索7日内锁单数量（平台）       |
| 下发线索 7 日锁单数 (直播)       | int64     | 下发线索7日内锁单数量（直播）       |
| 下发线索 7 日锁单数 (门店)       | int64     | 下发线索7日内锁单数量（门店）       |
| 下发线索 7 日锁单数              | int64     | 下发线索7日内锁单数量（合计）       |
| 下发线索当日试驾数               | int64     | 下发线索当日试驾数量                |
| 下发线索当日锁单数 (门店)        | int64     | 当日门店渠道线索当天即锁单的数量    |
| 下发线索数 (门店)                | int64     | 当日门店渠道收到的线索总数          |
| 下发线索数                       | int64     | 下发线索总数                        |
| 下发线索数（APP小程序)           | int64     | 下发线索总数（APP小程序）           |
| 下发线索数（平台)                | int64     | 下发线索总数（平台）                |
| 下发线索数（快慢闪)              | int64     | 下发线索总数（快慢闪）              |
| 下发线索数（直播）               | int64     | 下发线索总数（直播）                |
| 下发门店数                       | int64     | 下发门店数量                        |
| 主要渠道统计覆盖率               | float64   | 主要渠道统计覆盖率                  |

### config_attribute.parquet (Total Rows: 2196954)

| Column Name | Data Type | Description |
| :--- | :--- | :--- |
| Order Number | str | 订单号 |
| Attribute | str | 选配项名称 |
| value | str | 选配项取值 |
| is_staff | boolean | 是否员工单标记 |
