# 数据集指标与维度定义

本文件是**数据集字段级 schema**：字段、类型、维度、grain。

指标口径不在本文件重复维护：
- 机器可读指标注册表：`metrics.json`
- 人类可读指标口径：`reference/metric_definitions.md`
- 业务定义（上市/预售时间、车系分组、动力/驱动）：`business_definition.json`

## 1. 指标与口径（指针）

指标定义统一维护在以下位置，本文件不再重复：

| 内容 | 位置 |
|---|---|
| 指标注册表（名称 / 别名 / 聚合 / 时间字段 / 算子） | `metrics.json` |
| 人类可读口径（业务含义 / 计算口径 / 注意事项） | `reference/metric_definitions.md` |
| 换算关系（派生率 / 占比） | `metrics.json` 的 `metric_relations` |
| 算子实现与注册 | `shared/operators/`、`shared/operators/registry.json` |

数据集字段和维度见下文。

## 2. 可用维度 (Dimensions)

用于分组、筛选和拆解分析。

### 产品与车型

- `product_name`: 产品名称 (如: 全新智己L6)
- `series`: 车型系列 (如: L6, LS6)
- `series_group_logic`: 二级车型分组（由 `business_definition.json: series_group_logic` 基于 `product_name` 规则生成，如 CM0/CM1/CM2/DM0/DM1/DM2 等；不保证是原始字段）。规则为 `{priority, condition}`，priority 越大越具体/越新代际优先命中，首个命中生效（first-match-wins）。匹配前 `product_name` 与规则 token 均去除全部空白字符（空格不敏感），故「全新一代 智己LS6」与「全新一代智己LS6」同判。
- `product_type`: 燃料类型 / 动力形式。**注意：数据集中无此字段，需通过 product_name 模糊匹配生成。**
  - **增程**: `product_name` 包含 "52" 或 "66"。请使用正则匹配: `filters: [{"field": "product_name", "op": "matches", "value": "52|66"}]`。
  - **纯电**: `product_name` **不**包含 "52" 且 **不**包含 "66"。请使用正则匹配: `filters: [{"field": "product_name", "op": "not matches", "value": "52|66"}]`。
  - **注意**：增程/纯电判定使用 `product_name` 正则 `52|66`；不要拆成多个 `contains` 条件（多个条件是 AND 关系）。
- `drive_type`: 驱动形式（四驱 / 后驱）。由 `business_definition.json: drive_type_logic` 基于 `product_name` 生成，当前仅覆盖 LS6 家族（CM0–CM3），非 LS6 车系保持未命中。
  - **四驱**: `product_name` 含 `Ultra`（CM2/CM3）、`超强性能`（CM0/CM1 老款）或 `AWD`。
  - **后驱**: LS6 且不含上述四驱标记（含 Max / Max+ / Pro Max / Pro / 限定版及全部增程）。
  - **注意**: 智己命名中 `Max+` / `Pro Max` **不**表示四驱（与部分品牌习惯不同）。

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
- `buyer_phone_md5` / `lead_phone_md5` / `capp_phone_md5`: **手机号 MD5**（仅 `order_phone_map.parquet`），
  一行一订单；与 `lc_user_phone_md5` 同算法（`md5(纯11位)`），可跨表等值关联。
  **订单层用三列任一匹配**（覆盖最全），**渠道层用 `lead_phone_md5`** 对接归因表。详见对应章节。
- `lc_user_phone_md5`: **用户手机号 MD5**（仅 `lock_attribution_data.parquet`），无盐 MD5，可按手机号等值匹配；
  详见下文「lock_attribution_data.parquet」章节。注意 `order_data` 无手机号字段。

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

### TP&MIX-ways（乘用车上险数据）

6 张表，覆盖 2020-01 → 2026-09（以 registry 为准），数据源为 Tableau。

| 表                        | Grain                                                                                                            | 维度                                                                                                                                                                                   | 指标                                                                                                 | 用途                                                   |
| :------------------------ | :--------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------- | :----------------------------------------------------- |
| `market_energy_monthly`   | date_month + fuel_type_group + fuel_type                                                                         | date_month, fuel_type_group, fuel_type                                                                                                                                                 | sales, weighted_tp                                                                                   | 市场总量、能源结构、纯电/插混/增程走势、价格重心       |
| `brand_monthly`           | date_month + brand + ownership_type + oem + domestic_import                                                      | date_month, brand, brand_group, brand_luxury_group, oem_group, oem, brand_country, ownership_type, domestic_import                                                                     | sales, weighted_tp                                                                                   | 品牌排名、品牌份额、品牌分组竞争、价格重心             |
| `model_monthly`           | date_month + brand + model + sub_model + sub_model_id + drive_type + fuel_type                                   | date_month, brand, brand_series, model, sub_model, sub_model_id, fuel_type, fuel_type_group, body_type, vehicle_level, vehicle_level_group, saic_segment, drive_type, drive_type_group | sales, weighted_tp                                                                                   | 车型排名、品牌内车型结构、级别/燃料/驱动分布           |
| `geo_monthly`             | date_month + province + city + city_tier_group + fuel_type_group                                                 | date_month, province, city, region_group, city_tier_2025, city_tier_group, fuel_type_group                                                                                             | sales, weighted_tp                                                                                   | 省市市场、城市线级、区域新能源渗透                     |
| `price_segment_monthly`   | date_month + tp_bucket_5w + tp_bucket_10w + fuel_type_group + body_type + vehicle_level_group                    | date_month, tp_bucket_5w, tp_bucket_10w, fuel_type_group, body_type, vehicle_level_group                                                                                               | sales, weighted_tp                                                                                   | 价格带市场容量、价格带 × 能源 × 车身 × 级别交叉        |
| `product_segment_monthly` | date_month + saic_segment + body_type + vehicle_level + vehicle_level_group + fuel_type_group + drive_type_group | date_month, saic_segment, body_type, vehicle_level, vehicle_level_group, fuel_type_group, drive_type_group                                                                             | sales, weighted_tp, weighted_length_mm, weighted_width_mm, weighted_height_mm, weighted_wheelbase_mm | 细分市场、车身/级别/驱动结构、大车化趋势、产品尺寸重心 |

**字段说明**：

- `sales`: 上险销量（辆），核心聚合指标
- `weighted_tp`: 价格重心（元），销量加权平均成交价
- `weighted_length_mm` / `weighted_width_mm` / `weighted_height_mm` / `weighted_wheelbase_mm`: 销量加权平均尺寸（mm），仅 `product_segment_monthly` 有
- `date_month`: 月粒度日期，格式 `YYYY-MM-01`

### delivery_inventory.parquet (Total Rows: 239,916 · Columns: 14 · Time Range: 2021-12 ~ 2026-08)

| Column Name              | Data Type      | Description                             |
| :----------------------- | :------------- | :-------------------------------------- |
| vin                      | string         | 车辆识别代码（VIN），主标识字段         |
| is_retailed               | string         | 是否零售上报（Y/N），标记车辆是否已完成零售上报 |
| bloc_name                 | string         | 库存归属合作集团名称                    |
| Real As Offline Time     | datetime64[us] | 车辆最早的生产完成时间                  |
| Real Qc Offline Time     | datetime64[us] | 实际质检完成时间                        |
| First In Inv Time        | datetime64[us] | 车辆最早进入库存的时间                  |
| Actual In Inv Time       | datetime64[us] | 当前一次实际入库时间                    |
| Actual Waybill Out Time  | datetime64[us] | 实际运单发运时间                        |
| Real In Dc Time          | datetime64[us] | 实际到达交付中心时间                    |
| Out Delivery Center Time | datetime64[us] | 实际离开交付中心时间                    |
| Schedule Effective Time  | datetime64[us] | 排程或计划正式生效时间                  |
| Order Binding Time       | datetime64[us] | 订单与具体 VIN 绑定时间                 |
| Real Out Vdc Time        | datetime64[us] | 实际离开 VDC（车辆配送中心/中转库）时间 |
| Attribute Dealer Date    | datetime64[us] | 经销商属性分配/确认日期                 |

#### VIN 编码规律

所有 VIN 以 `LSJ` 开头（上汽 WMI 代码），17 位标准编码。前 5 位可唯一识别车系：

| 前5位 | 对应车系 |
|:------|:---------|
| `LSJEL` | LS8 |
| `LSJEH` | LS9 |
| `LSJWL` | LS7 |
| `LSJWR` | LS6 |
| `LSJWT` | L6 |
| `LSJE3` | L7 |

各位置含义：
- 第4位：`E` = LS8/LS9/L7 平台，`W` = LS7/LS6/L6 平台
- 第5位：车系级标识（需结合第4位）；`L`=LS7(4=W)/LS8(4=E), `H`=LS9, `R`=LS6, `T`=L6, `3`=L7
- 第6位：`4` = 主流设计代，`6` = L7 独立平台
- 第10位：车型年份（`S`=2025, `T`=2026, `V`=2027）

### 库存分类模型

本表采用"物理位置 × 业务状态"二维分类。DC（交付中心）为经销商接车节点，DC内库存归属经销商端。

**物理位置（physical_position）：**

| 位置 | 判断逻辑 |
|:-----|:---------|
| VDC内 | 已进入库存链，`Real Out Vdc Time` 为空 |
| VDC→DC在途 | `Real Out Vdc Time` 非空，`Real In Dc Time` 为空 |
| DC内 | `Real In Dc Time` 非空，`Out Delivery Center Time` 为空 |
| 已离开DC | `Out Delivery Center Time` 非空 |
| 未进入物流链 | 无任何库存/物流事件 |

**业务分类（business_classification）：**

| 业务分类 | 归属 | 说明 |
|:---------|:-----|:-----|
| 总部可控(VDC内/在途) | 总部 | VDC内 + VDC→DC在途，总部可调配 |
| 经销商端(DC在库) | 经销商 | DC内，经销商前置仓 |
| 经销商端已锁单 | 经销商 | 已离店、已锁单 |
| 经销商端未锁单 | 经销商 | 已离店、未锁单 |
| 历史直营已售车辆 | 已售 | 2022 年直营模式，有订单无 Dealer Attribute |
| 未进入物流链 | — | 尚未进入物流体系 |

**核心库存指标（2026-07-28）：**

| 指标 | 数量 | 说明 |
|:-----|-----:|:-----|
| 总部可控(VDC内/在途) | 714 | VDC内 + VDC→DC在途 |
| 经销商端(DC在库) | 15,883 | 物理在 DC 的全部车辆 |
| **★ 国内DC在库_未开票** | **9,504** | **核心库存监控指标**。国内DC物理库存扣除已开票车辆；bloc_name 不为"上汽国际"或"海外"（剔除出口库存） |
| 经销商端未锁单 | 11,498 | 经销商责任、尚未锁单 |
| 经销商端责任合计 | 27,381 | DC在库 + 已离店未锁单 |

**口径说明：** `物理位置=DC内` + `bloc_name` 不为上汽国际/海外（剔除出口）+ `invoice_upload_time` 为空（未开票）。反映国内经销商端交付中心中，已到店、未开票的实物库存，即当前可售现车供给水平。

**算子路径：** `shared/operators/dealer_unsold_inventory.py`

### lock_attribution_data.parquet (Total Rows: 620,923 含 1 行合计 · 真实记录 620,922 · Columns: 7)

线索与锁单归因表：**一行 = 一个手机号在一个线索渠道下的一条留资/锁单记录**。是当前唯一可按**手机号**定位客户的数据集。

| Column Name             | Data Type      | Description                                 |
| :---------------------- | :------------- | :------------------------------------------ |
| `lc_small_channel_name` | str            | 线索小渠道（如 `APP-试乘试驾`、`小程序留资`、`懂车帝卖车通`、`总部孵化线索`、`IM智己达人车主种草`） |
| `lc_main_code`          | str            | 主线索编码，形如 `M202410021032087924`      |
| `lc_order_lock_time_min`| **date**（Parquet 存为 datetime64、均 00:00:00） | **最早锁单时间，仅到「日」精度**；为空表示该记录**未关联**锁单时间（≠ 该渠道促成锁单） |
| `种子用户_md5锁单`      | int64          | **常量字段，恒为 1**（除全表合计行外无变化），无区分能力，不可用于判断锁单状态 |
| `lc_user_phone_md5`     | str            | **用户手机号的 MD5（32 位小写十六进制）**，见表下说明 |
| `lc_create_time`        | **date**（Parquet 存为 datetime64、均 00:00:00） | **留资时间，仅到「日」精度**（线索创建日期） |
| `来源辅助标记`          | int64          | 线索来源辅助标记（0/1），按渠道系统性分布，语义未在源系统定义；**不等于锁单状态** |

**⚠️ 表内合计行（1 行）**：`lc_small_channel_name` 与 `lc_main_code` 均为字符串 `全部`，
其余字段全为空（含 `lc_user_phone_md5`）。该行是 Tableau 导出的**总计行，不是真实记录**，
所有统计必须先剔除：`df[df['lc_main_code'] != '全部']`，否则行数虚增 1、渠道维度被污染。

**`lc_user_phone_md5` 说明（重要）**：

- **存储形态**：`md5(纯 11 位手机号)`，**无盐、无前缀、无后缀**，小写 32 位十六进制。
  例：手机号 `13800138000`（虚构示例）→ `md5("13800138000") = 7945bd83237335e5376ff44d62e4f0ae`。
- **可直接匹配**：把目标手机号做一次 MD5，与该字段做**等值匹配**即可定位到该用户的全部留资记录，
  直接读出其**线索渠道**（`lc_small_channel_name`）、**留资时间**（`lc_create_time`）、
  **锁单时间**（`lc_order_lock_time_min`）。这是该字段设计上支持的查询方式。
- **粒度提示**：同一手机号通常有多行（跨渠道、跨时间多次留资），匹配后是**多条线索记录**而非单条。
  全表 239,036 个去重手机号中，**55.4% 的用户属于“部分行带锁单时间、部分行不带”的混合状态**
  （均属已锁单用户，详见下方「三个计数口径」），因此：
  查“某个手机号”时返回的是**该用户的全部触点记录**，需要人数时按 `lc_user_phone_md5` 去重；
  **不能用 `种子用户_md5锁单` 判断**（该字段恒为 1，见上表），也不要用标记列求和当用户数。
- **锁单时间口径**：`lc_order_lock_time_min` 是该用户的**最早锁单时间**（字段名 `min` 即最小/最早），
  会被回填到该用户的每条渠道记录上，故存在**锁单时间早于留资时间**的 143 行
  （同用户另一条渠道更早锁单，回填到本条）。这是**日粒度 + 用户级回填**的结果，
  **不是**时序倒挂异常；零差（90,926 行）也**不应统一按异常剔除**，详见下方「时间精度」章节。
- **上游规范化**：`dataset/updater/lock_attribution_data_to_parquet.py:normalize_phone_md5`
  仅做 `strip + lower`、空值归一，并丢弃非 32 位十六进制的脏值；不参与哈希计算。
- ⚠️ **安全提示（无盐 MD5 可逆）**：手机号搜索空间约 10 亿，无盐 MD5 可被快速穷举还原，
  该字段**不提供实质匿名保护**，应按**个人信息**同等级别管控：限定分发范围、禁止批量导出，
  且仅限合规用途定向查询。若需长期安全方案，应改用带密钥的 HMAC-SHA256 加盐哈希。

### 三个计数口径（必须区分，禁止混用）

`lc_order_lock_time_min` 非空**只说明该记录关联了锁单时间**，**不能证明该线索渠道促成了锁单**。
同一用户跨渠道留资时，其锁单时间会被回填到该用户的**每一条**记录上
（见下方证据），若直接按渠道汇总“有锁单时间的记录数”，会**在渠道维度上重复计算锁单**。

> **⚠️ 本表是「已锁单用户池」，不含未锁单线索**：239,036 个去重手机号**每一个都至少有一条**
> 带锁单时间的记录（`n_locked >= 1` 的占比 100%）。因此：
> - **不能**用 `lc_order_lock_time_min` 非空率计算“线索→锁单转化率”，分母缺失；
> - **不能**用本表做线索总量 / 未成交线索分析，需另接线索池数据；
> - 369,770 条空格锁单时间记录，全部属于“该用户在其他渠道已锁单”的情形，
>   它们是**同用户的其他留资触点**，不是未成交线索。

| 口径 | 定义（SQL 等价） | 全表值 | 适用场景 |
| :--- | :--- | ---: | :--- |
| **① 线索记录数** | `COUNT(*)`，剔除合计行 | 620,922 | 渠道触点规模、渠道结构占比（**非人数**） |
| **② 去重锁单用户数** | `COUNT(DISTINCT lc_user_phone_md5)` | 239,036 | 锁单用户总量（本表所有用户均锁单） |
| **③ 渠道归因锁单数** | 每个用户**只归属一个渠道**后再计数，**各渠道之和必须等于 ②** | 见各渠道 | 渠道贡献对比、渠道 ROI |

**关键关系**：① ≥ ③，且 Σ③ = ② = 239,036。每用户平均 **2.60 条**记录（620,922 / 239,036）。

**三种典型错算及偏差（均为实测）**：

| 错误做法 | 得到的值 | 相对 ② 的偏差 | 错在哪 |
| :--- | ---: | :--- | :--- |
| 用 ① 当锁单数 | 620,922 | **+159.8%** | 把多渠道触点当人 |
| 用“含锁单时间的记录数”当锁单数 | 251,152 | **+5.1%** | 回填使每用户 1–n 条记录带锁单时间 |
| 用“全行均锁单的用户数”当锁单用户数 | 106,547 | **−55.4%** | 漏掉 55.4% 有混合行的用户 |

**渠道归因归属规则（③ 的最小可实现方案）**：由于表内无“渠道先后顺序”字段，
推荐按**该用户首次留资渠道**归属（`lc_create_time` 最小者，并列时取 `lc_main_code` 最小以保证确定性）；
不推荐“取有锁单时间的那条记录的渠道”，因为回填会使同一用户在多个渠道都带锁单时间。

**已观测到的重复计算证据**：

- 多行用户共 133,765 个，其中 **125,099 个（93.5%）的所有行携带完全相同的 `lc_order_lock_time_min`**，
  说明锁单时间是**用户级回填**，而非该渠道自身成交时间。

### 时间精度与“零时间差”口径

**两个时间字段都只有「日」精度**：`lc_create_time` 与 `lc_order_lock_time_min` 的时分秒
**100% 为 00:00:00**（实测 620,922 行无一例外），Parquet 中的 `datetime64` 类型不改变这一事实。

由此导致三个必须成立的口径约束：

1. **不能计算小时级转化时长**，也不能断言“锁单早于留资”——负值（143 行）是日粒度下
   跨渠道回填的产物，不是时序倒挂的业务异常。
2. **差值为 0 天只能读作“同日”，不能读作“即时转化”或“异常回填”**。
3. 原始的负值（143 行）与零值（90,926 行）**都不得删除**，应在报告中单列说明。

**零时间差（90,926 行，占有关联锁单时间记录的 36.2%）不整体视为异常**，实测特征表明它是
**真实当日转化与渠道回填的混合体**，需按渠道区分解读：

| 渠道 | 关联锁单行数 | 零差占比 | 中位差（天） | 解读 |
| :--- | ---: | ---: | ---: | :--- |
| `直接大定` | 8,818 | 79.2% | 0 | **真实当日转化**。该渠道语义为“留资即锁单”，同日属预期 |
| `自然客流` | 94,509 | 41.5% | 2 | **真实当日转化为主**。到店当场成交，同日合理 |
| `车展（门店）` / `Popup（门店）` / `地推（门店）` | 25,596 | 42.9% | 1 | 线下场景，当日成交合理 |
| `意向金` | 12,227 | 6.6% | 22 | 零差极少，**说明数据未整体失真**，是重要反证 |
| `懂车帝卖车通` / `汽车之家车商汇` / `APP-试乘试驾` | 10,628 | 13.0% | 8 | 线上或试驾链路，零差极少，符合业务预期 |

**结论（回答“零差是真实转化还是回填”）**：两者都有，但**以真实当日转化为主，不能一刀切视为异常**：

- **回填机制确实存在**（93.5% 的多行用户各行锁单时间完全相同），但它的后果是
  **跨渠道重复计数**，而不是把非当日成交伪装成当日——因为回填的是**用户真实的最早锁单日**，
  对“该用户哪天锁单”这一事实并未失真。
- **零差占比按渠道从 6.6% 到 79.2% 系统性分层**，且与渠道业务形态吻合（直接大定为留资即锁单、
  自然客流为到店成交），同时线上渠道与意向金渠道零差极少——若是系统性回填缺陷，
  不可能出现这种渠道分化。
- 因此零差**应保留全部 90,926 行**，只在报告中注明“日粒度、含当日转化与跨渠道回填”；
  处理重复计数的正确做法是采用 ② 去重用户数或 ③ 首渠道归属，**而非按零差剔除**。

**时间趋势佐证**：2022 年零差占比约 0–8%，2025 年 12 月后升至 25–57%，
提示近年线索系统链路（APP/小程序/新媒体）接入增多、同日留资-锁单确实更普遍；
该趋势与“渠道结构变化”一致，未呈现“某时点起突变至 100%”的典型回填故障特征。

**与其他表的关联（渠道层）**：本表**没有**身份证号与订单号，因此**本身不能直接定位订单**。
按手机号查订单请走 `order_phone_map.parquet`（见下一节）：

```
order_phone_map.lead_phone_md5 → lock_attribution_data.lc_user_phone_md5
                               → 渠道 / 留资时间 / 锁单时间
```

本表定位为**渠道维度补充**：`order_phone_map` 负责「买了什么」，本表负责「从哪来」。

> ⚠️ **不要用 `lc_main_code` → `order_data.main_lead_id` 关联订单**：
> 全表仅 **43.3%** 可命中（268,736 / 620,922），且 `main_lead_id` 存在一对多
> （54,641 个 lead_id 对应多订单，占 11.7%），会虚增订单数。
> 历史审计亦记录该路径匹配率偏低（早期口径约 14.8%，见
> `docs/业务能力/车型预售与上市/L6_M2_预售情况汇报分析框架.md:126`）。
> 该路径**不可作为手机号→订单的可靠通路**，应改用 `order_phone_map`。

**数据源**：`dataset/updater/lock_attribution_data_to_parquet.py`（Tableau `1h/sheet10` → 本表；仅 `allupdate` 或独立更新）。

### order_phone_map.parquet (Total Rows: 554,295 · Columns: 5)

**订单 ↔ 手机号映射表**：补上「订单表无手机号、归因表无订单」的结构缺口，
使 **手机号 → 订单明细 → 线索渠道** 可连通。粒度 = **一行一个 `order_number`（唯一）**。

| Column Name       | Data Type | Description |
| :---------------- | :-------- | :---------- |
| `order_number`    | str       | 订单号，关联 `order_data.order_number`（唯一） |
| `buyer_phone_md5` | str       | **购车人**手机号 MD5（32 位小写十六进制），订单层匹配用 |
| `lead_phone_md5`  | str       | **线索**手机号 MD5，对接 `lc_user_phone_md5` 查渠道用 |
| `capp_phone_md5`  | str       | **CAPP 订单**手机号 MD5（约 4,130 行为空），订单层匹配用（早期订单可能仅此列命中） |
| `has_phone`       | bool      | 三个手机号至少一个非空（本表恒为 true，建表时已过滤） |

**哈希口径（与现有表严格对齐）**：

- 算法为 `md5(纯 11 位手机号)`，**无盐、无前缀、无后缀**，小写 32 位十六进制
  —— 与 `lock_attribution_data.lc_user_phone_md5` **完全一致**，两表可直接等值关联。
- 例（虚构）：`md5("13800138000") = 7945bd83237335e5376ff44d62e4f0ae`。
- 输出**只保留哈希，不落明文**；明文 CSV 位于 `dataset/tableau-hs/orders/order_phone_map.csv`（被 `.gitignore` 忽略）。

**三个手机号字段的关系（实测）**：

| 对比 | 一致行数 | 占比 |
| :--- | ---: | ---: |
| `buyer` = `lead` | 553,852 / 554,295 | 99.92% |
| `buyer` = `capp` | 522,138 / 554,295 | 94.2% |
| 三者全等 | 522,127 / 554,295 | 94.2% |

三者高度一致但**不完全等价**，因此**按查询目的分层使用，不要混用**：

- **订单层（查“买了什么”）**：用 **三列任一匹配**
  `buyer_phone_md5 OR lead_phone_md5 OR capp_phone_md5`，覆盖最全。
  实测仅用 `lead_phone_md5` 会**漏单**——部分早期订单的 CAPP 下单手机号与线索手机号不同，
  仅命中 `capp_phone_md5`（如下方漏单示例）。
- **渠道层（查“渠道来源”）**：用 `lead_phone_md5` 对接
  `lock_attribution_data.lc_user_phone_md5`（两者语义同为“线索手机号”，可精确等值关联）。

**仅用 `lead_phone_md5` 的漏单示例（27 个样本手机号实测）**：

| 样本（脱敏） | 仅 `lead` 匹配订单数 | 三列任一匹配 | 差额来源 |
| :--- | ---: | ---: | :--- |
| 样本 1 | 14 | 16 | 2 单仅 `capp_phone_md5` 命中 |
| 样本 2 | 2 | 3 | 1 单仅 `capp_phone_md5` 命中 |
| 样本 3 | 4 | 5 | 1 单仅 `capp_phone_md5` 命中 |
| 样本 4 | 4 | 5 | 1 单仅 `capp_phone_md5` 命中 |

> 上表手机号已脱敏。含真实号码的排查明细仅保留在本地分析产物（`outputs/`），不进入版本库。

> 差异集中在 2021–2022 年早期订单（APP 下单手机号 ≠ 线索留资手机号）。
> 若只看渠道，用 `lead` 不影响结果；若要统计完整购车历史，必须三列并用。

**覆盖度（相对 `order_data`）**：

- 本表 554,295 个订单号中 **553,878 个（99.92%）** 可在 `order_data` 命中；
- 反向覆盖 `order_data` 559,513 单中的 **98.99%**；
- 4,417 个订单匹配不上（本表多 417 / 订单表多 5,635），差异来自两表导出时点与范围不同，**关联时用 LEFT JOIN 并以订单表为主表**。

**与其他表的关联（推荐两层路径）**：

```
① 订单层：只关心「这个手机号买了什么」
   手机号 --md5--> order_phone_map.lead_phone_md5  (OR buyer_ OR capp_)
          --> order_data.order_number   （车型 / 门店 / 开票 / 交付 / 金额）

② 渠道层：需要渠道来源时，再用 lead 手机号对接归因表
   order_phone_map.lead_phone_md5
          --> lock_attribution_data.lc_user_phone_md5
          --> 线索渠道 / 留资时间 / 锁单时间
```

> ✅ **首选路径**：第①层完全不需要 `lock_attribution_data`，即可回答
> 「这个手机号买了什么车」——比旧的 `main_lead_id → lc_main_code` 路径
> 命中率高得多（99% vs 43.3%），且能拿到订单明细。
>
> ⚠️ **备选路径（不推荐，仅作兼容）**：
> `order_data.main_lead_id → lock_attribution_data.lc_main_code` 全表仅 **43.3%** 可命中
> （268,736 / 620,922），且 `main_lead_id` 存在一对多（54,641 个 lead_id 对应多订单，占 11.7%）。
> 该路径**不可作为正式渠道归因口径**；渠道归因请一律走第②层的 `lead_phone_md5` 等值关联。
>
> ⚠️ **统计订单数前必须按 `order_number` 去重**（本表已保证 `order_number` 唯一，
> 但 JOIN `order_data` 后若再 JOIN 其他一对多表需注意行数膨胀）。
> 另注意：本表匹配出的订单数**不等于锁单数或成交数**，需按
> `order_data.lock_time` / `invoice_upload_time` / `delivery_date` 自行过滤。

**为什么独立成表（而非并入 order_data）**：

- 隔离隐私面：`order_data` 是 6 个分析脚本的核心主表，加手机号会让敏感字段扩散到所有下游产物；
- 粒度正确：手机号是人粒度、订单表是订单粒度，并入会产生按人重复冗余；
- 可替换：若平台未来提供正式映射，整表替换即可，不动主表；
- 可单独授权：敏感表可独立设定访问权限与发布策略。

**⚠️ 安全提示**：无盐 MD5 可被穷举还原（手机号空间约 10 亿），本表**不提供实质匿名保护**，
应按个人信息同等级别管控：限定分发范围、禁止批量导出、仅限合规用途定向查询。

**数据源**：Tableau 视图 `W14/2`
（`https://tableau-hs.immotors.com/#/views/W14/2`）→
`dataset/tableau-hs/orders/order_phone_map.csv` → 本表。
更新入口：`dataset/updater/order_phone_map_to_parquet.py`（`make allupdate` 的 STEP 2；
`--no-export` 仅整理本地 CSV，`--input` 指定输入）。

### store_info.csv — 门店/经销商主数据（外部 original 目录，非 dataset/）

> 字段级机器可读定义见 `shared/schema/store_info_schema.json`；读取统一走
> `shared/loaders/store_info_loader.py`（含 store_name 简称 → 经销商归属解析）。

| Column (原始列名)             | Data Type | 语义 |
| :---------------------------- | :-------- | :--- |
| Bloc Name                    | string    | **经销商集团/投资人名称**（如 上海易茂、青岛鸿发）——门店上卷到经销商维度的关键字段 |
| Dealer Name Fc               | string    | **门店完整名**（如 合肥包河用户中心）；与 order_data.store_name（简称）需归一化匹配 |
| Dealer Code                  | string    | **门店业务代码（主键）**，形如 IMA236/IMD236/IMS236/IMH404；同门店名可对应多个代码 |
| Dealer_type                  | string    | 业态枚举：交付店/体验店/售后服务店/未分类 |
| City Code / City Name        | string    | 门店所在城市（Code=行政区划码，Name 带『市』后缀） |
| Province Name                | string    | 门店所在省份 |
| Region Name                  | string    | 大区（渠道销售区，如 华中区/东区-鲁豫） |
| Sd Tax No                    | string    | 税号（同 Bloc 集团共享） |
| Store Create Status Desc     | string    | 门店状态：开业/暂停/在建/停业 |
| store_create_time（原始列名为 Tableau 计算式）| datetime | 门店开业时间（读取时经 loader rename） |
| store_stop_time（原始列名为 Tableau 计算式） | datetime | 门店停业时间（空=在营） |
| store_format（派生）          | string    | 门店形态/店型，由 Dealer Code 前缀派生（见下『门店编码定义』），非原始列 |

**规模**：1,788 行 / 1,103 门店名 / 214 经销商集团（Bloc）；Grain = Dealer Code。

**门店编码定义（店型分类模型）**：

> 完整机器可读定义见 `store_info_schema.json` 的 `dealer_code_prefix_definitions`；
> 读取统一用 `store_info_loader.get_store_format(code)`（`load_store_info()` 已派生 `store_format` 列）。

| Dealer Code 前缀 | store_format | 典型业态 | 名称形态 |
| :--- | :--- | :--- | :--- |
| IMA | 授权经销商门店 | 交付店 | 用户中心 / 体验中心 |
| IMD / IMS | 交付/售后中心 | 交付店 / 售后服务店 | 用户中心 |
| IMH / IMV | 体验店 | 体验店 | 体验中心 |
| IMM | 体验及交付服务中心 | 体验店 / 售后服务店 | 体验及交付服务中心 |
| **IMP / IME** | **快闪/慢闪** | 未分类 | 城市展厅 / 临时展厅（pop-up） |
| IMB / IMF / IMJ / IMK / IML | 城市空间 | 未分类 | 城市空间 |
| IMX | 快闪交付中心 | 未分类 | -XN交付中心 |
| IMO / IMT | 海外网点 | 未分类 | 上汽国际 / 海外 |
| IMC / IMG / IMI | 其他 | 未分类 | 单店/特殊 |
| 其他/空 | 未知 | — | — |

**关联口径（order_data → 经销商）**：

- order_data 只有 `store_name` 门店简称；store_info `Dealer Name Fc` 是完整名。
- 用 `store_info_loader.resolve_dealer_info(store_name)` 做归一化子串匹配，返回
  `bloc_name / dealer_type / store_format / region_name / city_name / dealer_code`。
- 覆盖约 92% 门店；popup 快闪店、跨集团同名、作废/新址门店可能不命中，需人工补录。

**数据源**：`dataset/updater/store_info_to_csv.py`（Tableau store_info_1 视图 → external original）。

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
