# 数据集指标与维度定义

本文档定义了数据集的业务逻辑、指标计算规则及可用维度，用于指导 Planning Agent 生成准确的分析计划。

## 1. 可用指标 (Metrics)

用于计算总和、平均值、计数等数值指标。指标分为两层：

| 层级              | 说明                                    | 示例                                                     |
| :---------------- | :-------------------------------------- | :------------------------------------------------------- |
| **原始指标**      | field + agg 直接构成，不含业务过滤条件  | sum(invoice_amount), count(order_number)                 |
| **业务 DSL 指标** | 原始指标 + 业务口径规则（强制过滤条件） | 锁单量 = count(order_number) WHERE lock_time IS NOT NULL |

### 1.1 原始指标 (Raw Metrics)

由数据集的原始字段和聚合函数直接构成，LLM 可在此基础上附加用户查询中的过滤条件。

- **订单计数**: `order_number` 计数
- **开票金额**: `invoice_amount` 求和
- **购车人年龄**: `buyer_age` (平均/中位数/分布)
- **车主年龄**: `owner_age` (平均/中位数/分布)

### 1.2 业务 DSL 指标 (Business DSL Metrics)

在原始指标基础上附加了固定的业务口径规则。LLM 必须严格按以下 DSL 映射生成 plan。

#### 1.2.1 计数类 — `order_number` count + 时间字段非空

| 指标名     | 聚合                | 强制过滤条件                         | 时间字段                 | 说明                     |
| :--------- | :------------------ | :----------------------------------- | :----------------------- | :----------------------- |
| **锁单量** | count(order_number) | `lock_time` IS NOT NULL              | `lock_time`              |                          |
| **批售数量** | count(distinct vin) | `lock_time` IS NOT NULL, `order_type` NOT IN ('员工', '经销商员工') | `lock_time` | 锁单去重 VIN，剔除内部员工订单；反映真实市场销量 |
| **交付数** | count(order_number) | `delivery_date` IS NOT NULL          | `delivery_date`          |                          |
| **开票数** | count(order_number) | `invoice_upload_time` IS NOT NULL    | `invoice_upload_time`    | 不要用 order_create_date |
| **小订数** | count(order_number) | `intention_payment_time` IS NOT NULL | `intention_payment_time` |                          |
| **大定数** | count(order_number) | `deposit_payment_time` IS NOT NULL   | `deposit_payment_time`   |                          |

#### 1.2.2 均值类 — mean + 业务过滤

| 指标名           | 聚合                 | 强制过滤条件                                   | 时间字段              |
| :--------------- | :------------------- | :--------------------------------------------- | :-------------------- |
| **平均开票价格** | mean(invoice_amount) | `order_type == '用户车'`, `invoice_amount > 0` | `invoice_upload_time` |

#### 1.2.3 算子类指标

算子类指标由固定算子计算（不走通用 DSL 聚合）。用户查询匹配算子时，PLAN 必须设置 `analysis_intent.type` 为对应 intent 值，让路由层自动匹配算子。

各算子定义详见 `operators/registry.json` 算子注册表。

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
  - **Planning Agent 请注意**: 对于"增程"或"纯电"查询，必须使用 `matches` 或 `not matches` 操作符，并使用正则 `52|66`。不要生成多个 `contains` 过滤器（因为它们是 AND 关系）。

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

数据结构：长表（EAV），每行一个选配项。2026 年起改为 Tableau 规范化视图。通过 `Order Number` 关联 `order_data.parquet` 补充了订单类型和 VIN。

- `Order Number`: 订单号（与 `order_data.parquet` 的 `order_number` 对应，但字段名不同）
- `Attribute`: 选配项名称（内饰、外饰、轮毂、动力电池等，共 63 种）
- `value`: 选配项取值
- `option_flag`: 选装标记（Y/N，Y=已选装）
- `required`: 是否标配（Y/N，Y=标配，N=选装）
- `price`: 选配价格（元，Int64）
- `order_type`: 订单类型（关联自 order_data，如用户车/员工/试驾车等）
- `vin`: 车辆识别代码（关联自 order_data）

---

## 附录：原始字段 Schema 映射

### order_data.parquet (Total Rows: 445915)

| Column Name            | Data Type      | Description                                                        |
| :--------------------- | :------------- | :----------------------------------------------------------------- |
| order_number           | string         | 订单号                                                             |
| invoice_amount         | float64        | 开票金额                                                           |
| main_lead_id           | str            | 关联试驾表的主线索 ID                                              |
| series                 | str            | 车型系列                                                           |
| product_name           | str            | 产品名称                                                           |
| parent_region_name     | str            | 大区名称                                                           |
| store_name             | str            | 门店名称                                                           |
| store_create_date      | datetime64[ns] | 门店创建日期                                                       |
| store_city             | str            | 门店城市                                                           |
| license_city           | str            | 上牌城市                                                           |
| first_assign_time      | datetime64[ns] | 首次下发时间                                                       |
| first_assign_lock_time | float64        | 下发线索至锁单时间间隔（天，二级指标=lock_time-first_assign_time） |
| first_touch_time       | datetime64[ns] | 首次接触时间                                                       |
| order_type             | str            | 订单类型                                                           |
| buyer_identity_no      | str            | 购车人身份证号                                                     |
| owner_identity_no      | str            | 车主身份证号                                                       |
| final_payment_way      | category       | 尾款支付方式                                                       |
| delivery_date          | datetime64[ns] | 交付日期                                                           |
| invoice_upload_time    | datetime64[ns] | 发票上传时间                                                       |
| first_test_drive_time  | datetime64[ns] | 首次试驾时间                                                       |
| final_payment_time     | datetime64[ns] | 尾款支付时间                                                       |
| finance_product        | str            | 金融产品                                                           |
| approve_refund_time    | datetime64[ns] | 审批退款时间                                                       |
| apply_refund_time      | datetime64[ns] | 申请退款时间                                                       |
| actual_refund_time     | datetime64[ns] | 实际退款时间                                                       |
| order_create_date      | datetime64[ns] | 订单创建日期                                                       |
| vin                    | str            | 车辆识别代码(VIN)                                                  |
| buyer_age              | float64        | 购车人年龄                                                         |
| owner_age              | float64        | 车主年龄                                                           |
| order_gender           | str            | 购车人性别                                                         |
| owner_gender           | str            | 车主性别                                                           |
| intention_payment_time | datetime64[ns] | 意向金支付时间                                                     |
| intention_refund_time  | datetime64[ns] | 意向金退款时间                                                     |
| deposit_refund_time    | datetime64[ns] | 大定退款时间                                                       |
| deposit_payment_time   | datetime64[ns] | 大定支付时间                                                       |
| lock_time              | datetime64[ns] | 锁单时间                                                           |

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

### config_attribute.parquet (Total Rows: 4452631 · Unique Orders: 274692 · Unique Attributes: 63)

| Column Name  | Data Type | Description                                           |
| :----------- | :-------- | :---------------------------------------------------- |
| Order Number | str       | 订单号（与 `order_data.order_number` 对应）           |
| Attribute    | str       | 选配项名称（含内饰、外饰、轮毂、动力电池等）          |
| value        | str       | 选配项取值                                            |
| option_flag  | str       | 选装标记（Y/N，Y=已选装）                             |
| required     | str       | 是否标配（Y/N，Y=标配，N=选装）                       |
| price        | Int64     | 选配价格（元），空值表示无额外费用或不可单独计价      |
| order_type   | str       | 订单类型（关联自 order_data，如用户车/员工/试驾车等） |
| vin          | str       | 车辆识别代码（关联自 order_data）                     |

### passenger_insurance（乘用车上险数据）

6 张表，覆盖 2020-01-01 → 2026-06-01，数据源为 Tableau。

| 表                        | Grain                                                                                                            | 维度                                                                                                                                                                                   | 指标                                                                                                 | 用途                                                   |
| :------------------------ | :--------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------- | :----------------------------------------------------- |
| `market_energy_monthly`   | date_month + fuel_type_group + fuel_type                                                                         | date_month, fuel_type_group, fuel_type                                                                                                                                                 | sales, weighted_tp                                                                                   | 市场总量、能源结构、纯电/插混/增程走势、价格重心       |
| `brand_monthly`           | date_month + brand                                                                                               | date_month, brand, brand_group, brand_luxury_group, oem_group, oem, brand_country, ownership_type, domestic_import                                                                     | sales, weighted_tp                                                                                   | 品牌排名、品牌份额、品牌分组竞争、价格重心             |
| `model_monthly`           | date_month + brand + model + sub_model + sub_model_id                                                            | date_month, brand, brand_series, model, sub_model, sub_model_id, fuel_type, fuel_type_group, body_type, vehicle_level, vehicle_level_group, saic_segment, drive_type, drive_type_group | sales, weighted_tp                                                                                   | 车型排名、品牌内车型结构、级别/燃料/驱动分布           |
| `geo_monthly`             | date_month + province + city + city_tier_group + fuel_type_group                                                 | date_month, province, city, region_group, city_tier_2025, city_tier_group, fuel_type_group                                                                                             | sales, weighted_tp                                                                                   | 省市市场、城市线级、区域新能源渗透                     |
| `price_segment_monthly`   | date_month + tp_bucket_5w + tp_bucket_10w + fuel_type_group + body_type + vehicle_level_group                    | date_month, tp_bucket_5w, tp_bucket_10w, fuel_type_group, body_type, vehicle_level_group                                                                                               | sales, weighted_tp                                                                                   | 价格带市场容量、价格带 × 能源 × 车身 × 级别交叉        |
| `product_segment_monthly` | date_month + saic_segment + body_type + vehicle_level + vehicle_level_group + fuel_type_group + drive_type_group | date_month, saic_segment, body_type, vehicle_level, vehicle_level_group, fuel_type_group, drive_type_group                                                                             | sales, weighted_tp, weighted_length_mm, weighted_width_mm, weighted_height_mm, weighted_wheelbase_mm | 细分市场、车身/级别/驱动结构、大车化趋势、产品尺寸重心 |

**字段说明**：

- `sales`: 上险销量（辆），核心聚合指标
- `weighted_tp`: 价格重心（元），销量加权平均成交价
- `weighted_length_mm` / `weighted_width_mm` / `weighted_height_mm` / `weighted_wheelbase_mm`: 销量加权平均尺寸（mm），仅 `product_segment_monthly` 有
- `date_month`: 月粒度日期，格式 `YYYY-MM-01`

### delivery_inventory.parquet (Total Rows: 231657 · Columns: 9 · Time Range: 2021-12 ~ 2026-07)

| Column Name | Data Type | Description |
|:------------|:----------|:------------|
| vin | string | 车辆识别代码（VIN），主标识字段 |
| Real As Offline Time | datetime64[us] | 车辆最早的生产完成时间 |
| Real Qc Offline Time | datetime64[us] | 实际质检完成时间 |
| First In Inv Time | datetime64[us] | 车辆最早进入库存的时间 |
| Actual In Inv Time | datetime64[us] | 当前一次实际入库时间 |
| Actual Waybill Out Time | datetime64[us] | 实际运单发运时间 |
| Real In Dc Time | datetime64[us] | 实际到达交付中心时间 |
| Out Delivery Center Time | datetime64[us] | 实际离开交付中心时间 |
| Schedule Effective Time | datetime64[us] | 排程或计划正式生效时间 |

**时间顺序链**：

`Real As Offline Time` → `Real Qc Offline Time` → `First / Actual In Inv Time` → `Actual Waybill Out Time` → `Real In Dc Time` → `Out Delivery Center Time`

**数据源说明**：当前 `delivery_inventory` 表仅收录已通过质检的车辆（`real_as_offline_time` 和 `real_qc_offline_time` 均为 100% 非空），因此排产中、已下线待质检、工厂库存等早期状态在本表中无法观测。

**核心原则**：
- **车辆位置**看 `physical_stage`（仅依赖事件时间字段）
- **订单匹配**看 `lock_time`（有则为已匹配，无则可能是未匹配或非标准业务）
- **非标准业务（大客户批售、试驾车、仅批售等）不要求存在 `lock_time`**，不应视为数据异常
- 库存统计统一使用 `physical_stage`，不受 `lock_time` 缺失影响

**字段说明**：

`Schedule Effective Time` 为排程或计划正式生效时间，不等同于"排产最早记录时间"。同一 VIN 若有多条排产记录，需取 `MIN(Schedule Effective Time)` 才能得到最早一次排产记录。

#### VIN 生命周期状态机（三层架构）

通过 `vin` 串联 `order_data.parquet`（`lock_time`、`delivery_date`）与本表。状态判定分为三层，互不覆盖：

##### 第一层：physical_stage（物理位置）

仅依赖车辆事件时间字段，不受订单状态影响，用于库存统计。

| 物理位置 | 判断逻辑（从后往前匹配首个非空） |
|:---------|:-------------------------------|
| 已质检待入库 | `Real Qc Offline Time` 非空，`First In Inv Time` 为空 |
| 工厂库存 | `First In Inv Time` 非空，`Actual Waybill Out Time` 为空 |
| 在途 | `Actual Waybill Out Time` 非空，`Real In Dc Time` 为空 |
| 交付中心库存 | `Real In Dc Time` 非空，`Out Delivery Center Time` 为空 |
| 已离开交付中心 | `Out Delivery Center Time` 非空 |

##### 第二层：order_relation（订单关系）

仅依赖订单关联状态，不覆盖物理位置。

| 订单关系 | 判断逻辑 |
|:---------|:---------|
| 已锁单 | `lock_time` 非空 |
| 订单已关联但锁单时间缺失 | VIN 存在于 `order_data`，但 `lock_time` 为空 |
| 未关联 | VIN 不在 `order_data` 中 |

##### 第三层：vin_lifecycle_status（合并展示）

合并物理位置 + 订单关系。**注意**："订单已关联但锁单时间缺失" 不覆盖物理位置，这类车辆仍保留其 `physical_stage` 信息。

**16 类常规状态**：

| 状态 | 物理位置 | 订单关系 |
|:-----|:---------|:---------|
| 已锁单待排产 | 无任何进度事件 | 已锁单 |
| 已排产待下线_未匹配 | 已排产待下线 | 未关联 |
| 已排产待下线_已锁单 | 已排产待下线 | 已锁单 |
| 已下线待质检_未匹配 | 已下线待质检 | 未关联 |
| 已下线待质检_已锁单 | 已下线待质检 | 已锁单 |
| 已质检待入库_未匹配 | 已质检待入库 | 未关联 |
| 已质检待入库_已锁单 | 已质检待入库 | 已锁单 |
| 工厂库存_未匹配 | 工厂库存 | 未关联 |
| 工厂库存_已锁单待发运 | 工厂库存 | 已锁单 |
| 在途_未匹配 | 在途 | 未关联 |
| 在途_已锁单 | 在途 | 已锁单 |
| 交付中心库存_未匹配 | 交付中心库存 | 未关联 |
| 交付中心库存_已锁单待交付 | 交付中心库存 | 已锁单 |
| 已离开交付中心_未匹配 | 已离开交付中心 | 未关联 |
| 已离开交付中心_已锁单 | 已离开交付中心 | 已锁单 |
| 已交付 | 已离开交付中心且 `delivery_date` 非空 | — |

**3 类特殊状态**：

| 状态 | 判断逻辑 |
|:-----|:---------|
| 订单已关联但锁单时间缺失 | `physical_stage` 保留，`order_relation` 为"订单已关联但锁单时间缺失" |
| 退款待重新匹配 | `actual_refund_time` 非空 |
| 数据异常或状态未知 | 无法归入上述任何状态 |

**当前数据集分布（231,657 VIN）**：

| 物理位置 | 已锁单 | 订单已关联但锁单时间缺失 | 未关联 | 合计 |
|:---------|------:|----------------------:|------:|-----:|
| 已质检待入库 | 21 | 110 | 6,707 | 6,838 |
| 在途 | 17 | 0 | 499 | 516 |
| 交付中心库存 | 399 | 201 | 13,771 | 14,371 |
| 已离开交付中心 | 189,209 | 3,250 | 17,473 | 209,932 |
| **合计** | **189,646** | **3,561** | **38,450** | **231,657** |

库存统计应使用第一层 `physical_stage`：工厂库存 0、在途 516、交付中心库存 14,371。`lock_time` 缺失不影响物理库存位置判定。

## 3. 微信群聊消息 (wechat_sync)

由外部工具 `获取微信群聊记录` 定期同步生成，每个群聊一个独立 Parquet 文件。`dataset` 参数为群聊名称（即文件名不含 `.parquet` 的部分）。

### 3.1 可用字段

| 字段名      | 类型           | 说明                          |
| :---------- | :------------- | :---------------------------- |
| message_id  | int64          | 消息 ID（递增，用于增量同步） |
| group_name  | string         | 群聊名称                      |
| sender_name | string         | 发送者微信 ID                 |
| content     | string         | 文字消息内容                  |
| timestamp   | datetime64[ns] | 发送时间                      |

### 3.2 查询示例

- 查询某群聊消息量：`dataset="群聊名称" metrics=[{"field": "message_id", "agg": "count"}]`
- 按时间筛选：加 `filters` 条件 `{"field": "timestamp", "op": ">=", "value": "2026-01-01"}`
