# Vehicle Mapping — 车型映射规则

> 来源: schema/business_definition.json, schema/schema.md

## 车系 (Series)

| 车系 | 系列分组 | 说明 |
|------|----------|------|
| LS6 | CM0 / CM1 / CM2 | 智己 LS6 (含全新/新一代) |
| L6 | DM0 / DM1 / DM2 | 智己 L6 (含全新 / M2、Jimmy Choo) |
| LS8 | — | 智己 LS8 (单独模型) |
| LS9 | — | 智己 LS9 (单独模型) |
| LS7 | — | 智己 LS7 |
| L7 | — | 智己 L7 |

## 系列分组匹配规则 (series_group_logic)

每条规则为 `{priority, condition}`：**priority 是纯优先级（precedence），仅用于重叠规则裁决**，
数值大的规则优先命中，同分按书写顺序，取首个命中（first-match-wins）。
跨车系、互不重叠的规则可共用同一档（纯 precedence，不是车型排名）。

```
DM2 (precedence=3): product_name LIKE '%L6%' AND product_name LIKE '%M2%' OR product_name LIKE '%Jimmy Choo%' OR product_name LIKE '%JimmyChoo%'
CM2 (precedence=3): product_name LIKE '%新一代%' AND product_name LIKE '%LS6%' OR product_name LIKE '%上汽一亿台限定版%' AND product_name LIKE '%LS6%'
DM1 (precedence=2): product_name LIKE '%全新%' AND product_name LIKE '%L6%'
CM1 (precedence=2): product_name LIKE '%全新%' AND product_name LIKE '%LS6%'
DM0 (precedence=1): product_name LIKE '%L6%' AND NOT 全新
CM0 (precedence=1): product_name LIKE '%LS6%' AND NOT (全新/新一代)
LS8 (precedence=1): product_name LIKE '%LS8%'
LS9 (precedence=1): product_name LIKE '%LS9%'
LS7 (precedence=1): product_name LIKE '%LS7%'
L7  (precedence=1): product_name LIKE '%L7%'
其他 (precedence=0): ELSE
```

**注意**：
- DM2 必须高于 DM1/DM0（否则 L6 M2 / Jimmy Choo 订单会被 DM1/DM0 宽泛规则抢先归入旧代际）。
- DM2 的 `M2` 分支已收紧为 `%L6% AND %M2%`，非 L6 家族的 "M2" 产品不会落入 DM2。
- 旧字符串格式（直接写 `product_name LIKE ...`）仍被执行器兼容，视为 `{priority: 0, condition: <字符串>}`。
- 规则治理：`mashang_workspace/utility_scripts/audit_series_group_overlap.py` 可审计重叠；
  重叠应只发生在族内（LS6/L6 家族），跨车系重叠应视为规则 bug。

## 车系-系列分组关系 (model_series_mapping)

```
LS6 → [CM0, CM1, CM2]
L6  → [DM0, DM1, DM2]
```

## 能源类型 (product_type_logic)

| 能源类型 | 匹配规则 |
|----------|----------|
| 增程 (REEV) | product_name LIKE '%52%' OR product_name LIKE '%66%' |
| 纯电 (BEV) | NOT (product_name LIKE '%52%' OR product_name LIKE '%66%') |

**注意**：数据集中无 `product_type` 字段，需通过 `product_name` 模糊匹配。使用 `matches` 操作符和正则 `52|66`。

## 座位数 (seat_count_logic)

| 座位数 | 匹配规则 |
|--------|----------|
| 五座 | product_name LIKE '%五座%' |
| 六座 | product_name LIKE '%六座%' |

## 电池容量 (battery_capacity_logic)

| 容量 | 匹配规则 |
|------|----------|
| 52kwh | product_name LIKE '%52%' |
| 66kwh | product_name LIKE '%66%' |
| 76kwh | LS6 AND NOT 52/66/103/Ultra/Pro Max |
| 103kwh | LS6 AND (Ultra OR Pro Max OR 103) |

## 车型上市时间窗口 (time_periods)

| 系列分组 | 预售开始 | 预售结束 | 预计成熟 |
|----------|----------|----------|----------|
| CM0 | 2023-08-25 | 2023-10-12 | 2023-11-12 |
| DM0 | 2024-04-08 | 2024-05-13 | 2024-06-15 |
| CM1 | 2024-08-30 | 2024-09-26 | 2024-10-08 |
| CM2 | 2025-08-15 | 2025-09-10 | 2025-10-16 |
| DM1 | 2025-04-18 | 2025-05-13 | 2025-06-15 |
| LS9 | 2025-11-04 | 2025-11-12 | 2025-12-04 |
| LS8 | 2026-03-26 | 2026-04-16 | 2026-05-31 |

## 竞争车型 (6座主销车型)

来源: business_definition.json business_knowledge.main_selling_models_seats_6，更新于 2026年3月。

包含: 极氪9X、岚图泰山、理想L9、领克900、腾势N8L、蔚来ES8、问界M8/M9、银河M9、智己LS9、小鹏X9、零跑D19、ID.ERA 9X、大唐EV、乐道L90 等。
