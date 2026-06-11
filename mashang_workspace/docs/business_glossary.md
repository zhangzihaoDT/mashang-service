# Business Glossary — 业务术语表

> 来源: schema/metrics.json, schema/schema.md, schema/business_definition.json, operators/registry.json

## 核心术语

| 术语 | 英文 | 定义 | 备注 |
|------|------|------|------|
| 线索 | Lead | 潜在购车用户信息，经系统下发至门店 | 来源: 平台/APP/直播/快慢闪/门店 |
| 有效线索 | Valid Lead | 经过初步筛选合格的线索 | 口径见 assign_data |
| 下发线索 | Assigned Lead | 已分配至门店或渠道的线索 | `dataset/assign_data.csv` |
| 试驾 | Test Drive | 用户到店完成试驾体验 | 关联字段: `first_test_drive_time` |
| 锁单 | Lock Order | 用户最终确认订单（不可退/条件可退） | 核心指标，字段: `lock_time` |
| 小订 | Intention / Deposit | 支付意向金（通常可退） | 字段: `intention_payment_time` |
| 大定 | Down Payment | 支付正式定金 | 字段: `deposit_payment_time` |
| 退订 | Refund / Cancel | 取消订单并退款 | 字段: `apply_refund_time`, `actual_refund_time` |
| 上险 | Insurance Registration | 车辆完成保险注册 | 关联开票/交付状态 |
| ATP | Average Transaction Price | 平均开票价格/成交均价 | 字段: `invoice_amount`, 条件: `order_type='用户车'` |

## 分析概念

| 术语 | 定义 | 来源 |
|------|------|------|
| Cohort | 按首次分配时间分组的用户批次 | `lock_release_curve.py` |
| 释放曲线 | Release Curve | 每个 cohort 随时间推移的锁单释放累积比例 | `scripts/lock_release_curve.py` |
| 车型 | Product | 具体产品名称（如"全新智己LS6 52kwh 五座"） | `product_name` 字段 |
| 车系 | Series | 车型系列（LS6/L6/LS8/LS9/LS7/L7） | `series` 字段 |
| 系列分组 | Series Group | 二级车型分组（CM0/CM1/CM2/DM0/DM1） | `business_definition.json` |
| 城市线级 | City Tier | 城市等级（一线/新一线/二线/三线及以下） | `city_tier` 算子 |
| 大区 | Region | 销售大区划分 | `parent_region_name` 字段 |
| 渠道 | Channel | 线索来源（门店/平台/直播/APP小程序/快慢闪） | `assign_data` 分渠道字段 |
| 在营门店 | Active Store | 30天内存在订单活动的门店 | `active_store` 算子 |
| 留存小订 | Retained Intention | 在预售期内支付小订且窗口结束时未退款的订单 | `retained_intention` 算子 |
| VOC | Voice of Customer | 客户声音/反馈分析 | 来源: 微信群聊/调研 |
| JTBD | Jobs To Be Done | 用户待办任务分析框架 | VOC 分析方法论 |

## 订单类型

| 类型 | 说明 |
|------|------|
| 用户车 | 普通用户购车订单 |
| 员工车 | 内部员工购车 |
| 展车/试驾车 | 门店展车或试驾用车的订单 |

## 能源类型

| 类型 | 匹配规则 |
|------|----------|
| 增程 (REEV) | `product_name` 包含 "52" 或 "66"（对应 52kwh/66kwh 电池） |
| 纯电 (BEV) | `product_name` 不包含 "52" 且不包含 "66" |

## 电池容量分组

| 容量 | 匹配规则 |
|------|----------|
| 52kwh | product_name LIKE '%52%' |
| 66kwh | product_name LIKE '%66%' |
| 76kwh | LS6 且非 52/66/Ultra/Pro Max |
| 103kwh | LS6 且 Ultra 或 Pro Max |
