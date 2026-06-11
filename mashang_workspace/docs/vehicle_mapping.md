# Vehicle Mapping — 车型映射规则

> 来源: schema/business_definition.json, schema/schema.md

## 车系 (Series)

| 车系 | 系列分组 | 说明 |
|------|----------|------|
| LS6 | CM0 / CM1 / CM2 | 智己 LS6 (含全新/新一代) |
| L6 | DM0 / DM1 | 智己 L6 (含全新) |
| LS8 | — | 智己 LS8 (单独模型) |
| LS9 | — | 智己 LS9 (单独模型) |
| LS7 | — | 智己 LS7 |
| L7 | — | 智己 L7 |

## 系列分组匹配规则 (series_group_logic)

```
CM2: product_name LIKE '%新一代%' AND product_name LIKE '%LS6%'
CM1: product_name LIKE '%全新%' AND product_name LIKE '%LS6%'
CM0: product_name LIKE '%LS6%' AND NOT (全新/新一代)
DM1: product_name LIKE '%全新%' AND product_name LIKE '%L6%'
DM0: product_name LIKE '%L6%' AND NOT 全新
LS8: product_name LIKE '%LS8%'
LS9: product_name LIKE '%LS9%'
LS7: product_name LIKE '%LS7%'
L7:  product_name LIKE '%L7%'
其他: ELSE
```

## 车系-系列分组关系 (model_series_mapping)

```
LS6 → [CM0, CM1, CM2]
L6  → [DM0, DM1]
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
| 76kwh | LS6 AND NOT 52/66/Ultra/Pro Max |
| 103kwh | LS6 AND (Ultra OR Pro Max) |

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
