# Vehicle Mapping — 车型映射规则

> 权威来源: `shared/schema/business_definition.json`、`shared/schema/schema.md`
> 本文是语义视图：规则变更先改 `business_definition.json`，再同步本文。

## 车系 (Series)

| 车系 | 系列分组 | 说明 |
|------|----------|------|
| LS6 | CM0 / CM1 / CM2 / CM3 | 智己 LS6 (含全新、新一代；全新一代即 CM3) |
| L6 | DM0 / DM1 / DM2 | 智己 L6 (含全新 / M2、Jimmy Choo) |
| LS8 | LS8 / LS8Neo | 智己 LS8（含 NEO 纯电版；LS8Neo 为独立代际） |
| LS9 | — | 智己 LS9 (单独模型) |
| LS7 | — | 智己 LS7 |
| L7 | — | 智己 L7 |

## 系列分组匹配规则 (series_group_logic)

每条规则为 `{priority, condition}`：**priority 是纯优先级（precedence），仅用于重叠规则裁决**，
数值大的规则优先命中，同分按书写顺序，取首个命中（first-match-wins）。
跨车系、互不重叠的规则可共用同一档（纯 precedence，不是车型排名）。

```
CM3 (precedence=4): product_name LIKE '%M3%' AND product_name LIKE '%LS6%' OR product_name LIKE '%全新一代智己LS6%'
DM2 (precedence=3): product_name LIKE '%一代%' AND product_name LIKE '%L6%' OR product_name LIKE '%L6%' AND product_name LIKE '%M2%' OR product_name LIKE '%Jimmy Choo%' OR product_name LIKE '%JimmyChoo%'
CM2 (precedence=3): product_name LIKE '%新一代%' AND product_name LIKE '%LS6%' OR product_name LIKE '%上汽一亿台限定版%' AND product_name LIKE '%LS6%'
DM1 (precedence=2): product_name LIKE '%全新%' AND product_name LIKE '%L6%' AND product_name NOT LIKE '%一代%'
CM1 (precedence=2): product_name LIKE '%全新%' AND product_name LIKE '%LS6%'
DM0 (precedence=1): product_name LIKE '%L6%' AND product_name NOT LIKE '%全新%'
CM0 (precedence=1): product_name LIKE '%LS6%' AND product_name NOT LIKE '%全新%' AND product_name NOT LIKE '%新一代%'
LS8Neo (precedence=2): product_name LIKE '%LS8NEO%'
LS8 (precedence=1): product_name LIKE '%LS8%'
LS9 (precedence=1): product_name LIKE '%LS9%'
LS7 (precedence=1): product_name LIKE '%LS7%'
L7  (precedence=1): product_name LIKE '%L7%'
其他 (precedence=0): ELSE
```

**注意**：
- CM3 必须高于 CM2/CM1（否则「全新一代智己LS6」会被 CM2 的「新一代」或 CM1 的「全新」宽泛规则抢先归入旧代际）；
  该 literal 同时含「一代」，但 L6 家族规则均要求含 `L6`，不会误命中 DM2。
- DM2 必须高于 DM1/DM0（否则 L6 M2 / Jimmy Choo 订单会被 DM1/DM0 宽泛规则抢先归入旧代际）。
- **DM2 的核心锚点是「一代」**：M2 代产品在订单数据里的正式命名是「全新一代智己L6 [Max/Pro Max/Ultra]」，
  不含 "M2" 字样；"L6 M2 Pro Max/Max/Ultra" 是试驾车/内部命名。故 DM2 = 一代 L6 家族 + M2 token + Jimmy Choo，
  且 DM1 必须排除「一代」以免把 M2 代基础版抢归旧代际。
- 旧字符串格式（直接写 `product_name LIKE ...`）仍被执行器兼容，视为 `{priority: 0, condition: <字符串>}`。
- 规则治理：`workspace/utility_scripts/audit_series_group_overlap.py` 可审计重叠；
  重叠应只发生在族内（LS6/L6 家族），跨车系重叠应视为规则 bug。

## 车系-系列分组关系 (model_series_mapping)

```
LS6 → [CM0, CM1, CM2, CM3]
L6  → [DM0, DM1, DM2]
LS8 → [LS8, LS8Neo]
```

## 能源类型 (product_type_logic)

| 能源类型 | 匹配规则 |
|----------|----------|
| 增程 (REEV) | product_name LIKE '%52%' OR product_name LIKE '%66%' |
| 纯电 (BEV) | product_name LIKE '%93%' OR product_name LIKE '%103%' OR NOT (product_name LIKE '%52%' OR product_name LIKE '%66%') |

**注意**：
- 本表仅适用于 LS6 / L6 / LS9 等非 LS8 车系。
- **LS8 / LS8Neo 的动力类型由 `product_version_series` 唯一决定**，不走本表；93/103 是纯电电量段，不要再用「含 52/66 即增程」的旧规则。
- 数据集中无 `product_type` 字段；新代码优先调用 `resolve_product_attributes`，本表只作旧脚本兼容兜底。

## 驱动形式 (drive_type_logic)

| 驱动形式 | 匹配规则（当前覆盖 LS6 家族 CM0–CM3） |
|----------|----------------------------------------|
| 四驱 | `product_name` 含 `Ultra`（CM2/CM3）、`超强性能`（CM0/CM1 老款）或 `AWD` |
| 后驱 | LS6 且不含上述四驱标记（Max / Max+ / Pro Max / Pro / 限定版及全部增程） |

**注意**：
- 非 LS6 车系暂不分类（保持未命中）。
- 智己命名中 `Max+` / `Pro Max` **不**表示四驱；CM2/CM3 仅 `Ultra` 为双电机四驱，官方称其余为「超级后驱」。
- CM0/CM1 老款的四驱版型为「超强性能」（如 `LS6 Max 超强性能版`、`全新LS6 超强性能灵蜥智享版`），工程命名含 `AWD`（如 `LS6 M1 100AWD Max`）。
- 应用到 DataFrame：`utils.monitors.drive_type.apply_drive_type_logic`。

来源：智己官网配置表 `immotors.com/website/vehicle_config/ls6m2`；太平洋汽车 / 易车「智己LS6 2026款」参数库。

## 座位数 (seat_count_logic)

| 座位数 | 匹配规则 |
|--------|----------|
| 五座 | product_name LIKE '%五座%' OR product_name LIKE '%5座%' |
| 六座 | product_name LIKE '%六座%' OR product_name LIKE '%6座%' |

## 产品版本 (product_version_logic)

Canonical 定义位于 `shared/schema/business_definition.json` 的
`product_version_logic.{series}`，每个版本为 `{priority, condition}`。
匹配前去除全部空白；按 priority 降序、同分按定义顺序首次命中。
LS8 当前定义 52 Max+、52 Lite、66 Ultra、93 RWD；LS8Neo 定义 NEO93 Max+、NEO103 Max+；
LS9 定义 Ultra 电池版本、线控版及 Hyper 版本。新增版本应维护共享定义，不在日报中添加匹配规则。
未知版本返回“未分类”，未知座位返回“未标座位”，保证统计闭合。

Workspace 脚本统一调用：

```python
from utils.business import classify_product_names

# 输入已按车系筛选、含 product_name 的 DataFrame；结果保留输入索引。
classified = classify_product_names(orders, "LS8")
# 返回列：product_version、seat_count；可选传入已加载的 business_definition。
```

每日报表 LS8 按“版本 → 座位”展示，LS9 按版本横向展示、不显示座位。
本次仅日报切换到该入口，其他历史报告的独立分类尚未迁移。

### 版本动力字典 (product_version_series)

`business_definition.json → product_version_series` 是动力类型的**单一事实来源**：
`product_name → series_group_logic（代际）→ product_version（版本）→ power_type（动力）`。

| 车系 | 版本 | 动力 | battery_kwh |
|------|------|------|-------------|
| LS8 | 52 Max+ | 增程 | 未证实 |
| LS8 | 52 Lite | 增程 | 未证实 |
| LS8 | 66 Ultra | 增程 | 未证实 |
| LS8 | 93 RWD | 纯电 | 未证实 |
| LS8Neo | NEO93 Max+ | 纯电 | 未证实 |
| LS8Neo | NEO103 Max+ | 纯电 | 未证实 |

- 动力类型只由本表决定；新增版本先补字典，不要改 `product_type_logic`。
- JSON 中 `product_version_series.series` 把 NEO93/NEO103 挂在 `LS8` 键下（同一车系字典）；
  而 `product_version_logic` 用独立的 `LS8Neo` 代际组匹配 `NEO93 Max+` / `NEO103 Max+`。上表按代际分开展示以便对照。
- `battery_kwh` 为 `null` 表示未证实，不得用版本编号（52/66/93/103）回填。
- 版本未登记时必须返回「未知」并告警，不得默认纯电。

#### LS8 口径补充

- **裸名 `智己LS8` 订单**：2026-10-29 审计时点，`product_name` 去空格等于 `智己LS8` 的订单全部未锁单，属预售占位定金单，不能回填具体版本；做版本/动力占比时需显式排除并标注，不得默认归入任一版本。
- **LS8 66 Ultra 占比**：分子按 `product_version == '66 Ultra'`，不能用 `product_name` 包含 "66" 判断（例如「66周年纪念版」会误计）；分母为 LS8 代际组（`series_group_logic == 'LS8'`），不含 `LS8Neo`；窗口起点为 `time_periods.LS8.end`（上市日），不是预售 `start`。
- **动力未知**：版本字典未登记的 LS8/LS8Neo 版本返回「未知」并告警，不得默认归为纯电或增程。

## 电池容量 (battery_capacity_logic)

| 容量 | 匹配规则 |
|------|----------|
| 52kwh | product_name LIKE '%52%' |
| 66kwh | product_name LIKE '%66%' OR product_name LIKE '%Hyper%' |
| 76kwh | product_name LIKE '%LS6%' AND product_name NOT LIKE '%52%' AND product_name NOT LIKE '%66%' AND product_name NOT LIKE '%103%' AND product_name NOT LIKE '%Ultra%' AND product_name NOT LIKE '%Pro Max%' |
| 103kwh | product_name LIKE '%LS6%' AND product_name LIKE '%Ultra%' OR product_name LIKE '%LS6%' AND product_name LIKE '%Pro Max%' OR product_name LIKE '%LS6%' AND product_name LIKE '%103%' |

## 车型上市时间窗口 (time_periods)

| 系列分组 | 预售开始 | 上市日 | 预计成熟 |
|----------|----------|--------|----------|
| L7 | — | 2022-04-17 | — |
| LS7 | — | 2023-02-10 | — |
| CM0 | 2023-08-25 | 2023-10-12 | 2023-11-12 |
| DM0 | 2024-04-08 | 2024-05-13 | 2024-06-15 |
| CM1 | 2024-08-30 | 2024-09-26 | 2024-10-08 |
| CM2 | 2025-08-15 | 2025-09-10 | 2025-10-16 |
| DM1 | 2025-04-18 | 2025-05-13 | 2025-06-15 |
| LS9 | 2025-11-04 | 2025-11-12 | 2025-12-04 |
| LS8 | 2026-03-26 | 2026-04-16 | 2026-05-31 |
| LS9Hyper | — | 2026-07-16 | 2026-08-31 |
| DM2 | 2026-08-18 | 2026-08-28 | 2026-10-08 |
| CM3 | 2026-09-10 | 2026-09-23 | 2026-10-23 |
| LS8Neo | 2026-10-29 | 待确认 | — |

> L7/LS7 为历史存量车型，无预售期；LS8Neo 仅登记 start，`end`（上市日）未确认时按 open-ended 预售窗口（`start + monitor.presale_open_ended_window_days`，默认 3 天）处理，确认后自动按 `[start, end)` 收口。详见 `time_window_rules.md`。
>
> LS9Hyper 是 LS9 的 Hyper 版本上市事件（只有 `end`/`finish`，无独立预售期）；`series` 值含 `LS9Hyper` 的记录默认归入 LS9 统计，只有需要单独看 Hyper 版本上市节奏时才独立使用。详见 `metric_definitions.md`。

> **上市事件业务备注**（`business_definition.json` → `business_knowledge.launch_events`）：
> - **CM0（2023-10-12）**：上市当日发生 **APP 故障**，锁单被压制（D0 仅 11 单），需求顺延至次日（D1=2288 单）。
>   故 CM0 首日不是正常爆发力样本，上市节奏对比时应剔除或按 2023-10-13 等效锚定。

## 竞争车型 (6座主销车型)

来源: business_definition.json business_knowledge.main_selling_models_seats_6，更新于 2026年3月。

包含: 极氪9X、岚图泰山、理想L9、领克900、腾势N8L、蔚来ES8、问界M8/M9、银河M9、智己LS9、小鹏X9、零跑D19、ID.ERA 9X、大唐EV、乐道L90 等。
