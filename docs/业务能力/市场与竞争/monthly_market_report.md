# 月度汽车市场报告 — 标准查询体系

> version: 0.1
> scope: single_table_monthly_market_report

## 能力定位

monthly-market-report v0.1 是基于 `TP&MIX-ways` 现有 6 张预聚合单表的月度汽车市场固定主查询能力。

按月执行 24 个页级主查询问题，输出结构化数据底稿和报告草稿。

### 24 个固定问题是页级主查询

24 个固定问题是**按月运行的页级主查询集合**，每个 query 对应月报中一个独立分析页面（如"整体市场概览""新能源分能源形式表现""各价位段竞争格局"）。

这不是一套追问能力库。24 个固定问题之间没有多轮追问依赖关系，每个 query 独立执行、独立输出结果。

### 分工

| 层 | 文件 | 职责 |
|----|------|------|
| **Skill** | `.opencode/skills/monthly-market-report/SKILL.md` | 告诉 Agent 什么时候触发、怎么跑、如何检查结果 |
| **Query Spec** | `configs/monthly_market_report_queries.yaml` | 沉淀 24 个固定问题的结构化定义（数据集/粒度/指标/维度/过滤） |
| **Runner** | `research_scripts/market_report/run_monthly_market_report.py` | 实际执行：时间参数计算、数据加载、聚合、输出 |

### 数据资产

所有查询基于 `shared.loaders.tp_and_mix_ways_loader` 的 6 张 Parquet 表：

| 表 | 覆盖的 query |
|----|-------------|
| `market_energy_monthly` | q1-q3, q9, q12-q13 |
| `brand_monthly` | q7-q8, q20 |
| `model_monthly` | q16-q19 |
| `geo_monthly` | q5-q6, q21-q24 |
| `price_segment_monthly` | q11, q15 |
| `product_segment_monthly` | q4, q10, q14 |

## 使用方式

### dry-run 模式

默认模式，解析查询规范、展示每个 query 将使用的表和字段，不实际查询数据：

```bash
python workspace/research_scripts/market_report/run_monthly_market_report.py \
  --month 2026-05
```

输出：
- `query_results.json` — 每个 query 的 dry-run 计划
- `report_draft.md` — 报告草稿（含所有 query 信息）
- `run_metadata.json` — 运行元信息

### execute 模式

实际加载 TP&MIX-ways Parquet 数据并执行查询聚合：

```bash
python workspace/research_scripts/market_report/run_monthly_market_report.py \
  --month 2026-05 \
  --execute
```

需要 `TP&MIX-ways` 数据资产已构建（`make build-tp-and-mix-ways-dataset`）。

## 输出文件

执行完成后，输出目录为 `outputs/monthly_market_report/YYYY-MM/`：

| 文件 | 内容 | 格式 |
|------|------|------|
| `query_results.json` | 24 个查询的完整结果（Result Contract 格式） | JSON |
| `query_results.xlsx` | 多 sheet Excel 底稿（仅 execute 模式） | XLSX |
| `report_draft.md` | 可读的 Markdown 报告草稿 | Markdown |
| `run_metadata.json` | 运行元信息（时间参数/成功/失败统计） | JSON |

## 当前查询覆盖情况

### 直接接入（19 queries）

以下 query 可直接映射到单张 TP&MIX-ways 表：

| query id | 表 |
|----------|-----|
| `total_passenger_vehicle_sales` | `market_energy_monthly` |
| `nev_sales_penetration` | `market_energy_monthly` |
| `nev_energy_type_performance` | `market_energy_monthly` |
| `nev_segment_performance` | `product_segment_monthly` |
| `nev_city_tier_performance` | `geo_monthly` |
| `nev_region_performance` | `geo_monthly` |
| `premium_passenger_vehicle_sales` | `brand_monthly` |
| `premium_nev_sales_penetration` | `brand_monthly` |
| `premium_nev_energy_type_performance` | `market_energy_monthly` |
| `premium_nev_segment_performance` | `product_segment_monthly` |
| `tp_price_band_structure` | `price_segment_monthly` |
| `overall_tp_trend` | `market_energy_monthly` |
| `nev_energy_type_tp_trend` | `market_energy_monthly` |
| `nev_body_type_tp_trend` | `product_segment_monthly` |
| `bev_model_ranking_by_price_band` | `model_monthly` |
| `hybrid_model_ranking_by_price_band` | `model_monthly` |
| `premium_bev_model_ranking_by_body_type` | `model_monthly` |
| `premium_hybrid_model_ranking_by_body_type` | `model_monthly` |
| `key_nev_brand_performance` | `brand_monthly` |

### Adapter 多步查询（5 queries）

以下 query 需要多步处理（而非单表直查），通过 adapter 逻辑实现：

| query id | 实现方式 | 执行内容 |
|----------|---------|---------|
| `price_band_brand_competition` | `model_monthly` → weighted_tp 分桶 → 品牌排名 | 从 model_monthly 读取车型数据，按 `weighted_tp` 分桶到 `tp_bucket_5w`，计算各价位段内新能源品牌排名和份额 |
| `tier1_city_competition` | `geo_monthly` → city_tier 过滤 | 一线城市新能源销量、销量份额、渗透率、城市排名 |
| `new_tier1_city_competition` | `geo_monthly` → city_tier 过滤 | 新一线城市新能源销量、销量份额、渗透率、城市排名 |
| `tier2_city_competition` | `geo_monthly` → city_tier 过滤 | 二线城市新能源销量、销量份额、渗透率、城市排名 |
| `tier3_lower_city_competition` | `geo_monthly` → city_tier 过滤 | 三线及以下城市新能源销量、销量份额、渗透率、城市排名 |

### 覆盖率总结

| 状态 | 数量 |
|------|------|
| 直接单表接入 | 19 |
| Adapter 多步接入 | 5 |
| **合计** | **24** |
| execute 模式可全部执行 | **是** ✓ |

## v0.1 范围边界

### v0.1 支持范围

- 整体市场
- 新能源市场
- 能源形式
- 细分市场
- 城市线级结构
- 区域市场
- 中高端市场
- 成交价与价位段
- 品牌 / 车型在现有单表可支持范围内的排名

### v0.1 不支持范围

以下能力需要新增桥接表或宽表，属于后续交叉竞争格局扩展能力，v0.1 不做支持：

| 能力 | 缺少的字段/表 |
|------|-------------|
| city×brand 城市内品牌排名 | 不存在 city×brand 桥接表 |
| city×model 城市内车型排名 | 不存在 city×model 桥接表 |
| city×price_band×brand 城市×价位段×品牌交叉分析 | 需要四维交叉宽表 |
| brand×city_tier 品牌×城市线级交叉分析 | 不存在 brand×geo 桥接表 |
| region×model 区域×车型排名 | 不存在 region×model 桥接表 |
| TOP50 车型散点分布图 | 需要多年级车型级数据 + 可视化 |
| 完整竞争格局页复刻 | 上述能力的综合 |

上述能力需要后续版本新增桥接表或构建交叉宽表后，作为 **Optional Query Group** 或独立 skill 扩展。

## 临时专题扩展（后续可选）

以下类型的分析可作为 `optional query group` 在 Query Spec 中扩展：

- **重点城市专题**：如上海、北京、杭州单独分析
- **南北方专题**：按秦岭-淮河划分的南北方对比
- **历史城市附录**：特定城市的多年数据对比
- **品牌专题**：特定品牌的深度分析

扩展方式：在 `queries` 下新增 group（如 `group: city_deep_dive`），不修改现有 24 个固定 query 的 id 或 group 归属。

## 后续扩展方向

v0.2 可在新增交叉事实表或桥接表后扩展竞争格局查询能力。

可能需要的数据资产包括：

- `city_brand_monthly`
- `city_model_monthly`
- `city_price_band_brand_monthly`
- `region_model_monthly`
- `brand_city_tier_monthly`

这些能力不属于 v0.1 范围，后续可作为独立 skill（命名建议：`market-competition-cross-analysis`）或 optional query group 扩展。

## 附录：上险月报简报结构

以下为版式示例，数字仅用于说明展示方式。

目标：每月更新一次，**5~10 分钟读完**，回答三个问题：

> **这个月市场发生了什么？**
>
> **为什么会这样？**
>
> **哪些变化值得持续跟踪？**

---

## ① Executive Summary

四句话 + Top5 Insights。

```
2026-06 乘用车市场

市场规模    同比 +8.2%  环比 +4.1%
新能源渗透  57.8%       +2.4pct
价格重心    24.7 万元   连续第五个月上升
最大变化    插混继续增长，SUV 继续扩大份额，自主品牌创新高
```

**本月 Top5 Insights**
- 插混首次超过纯电增量
- 豪华品牌继续承压
- 20-25 万价格带成为最大市场
- 三线城市新能源继续提升
- 中大型 SUV 继续扩大

---

## ② Overall Market

数据源：`market_energy_monthly`

### 图1 市场销量
折线：月销量 / YoY / MoM

> 一句话：市场恢复情况。

### 图2 能源结构
堆积面积：燃油 / BEV / PHEV / REEV

回答：
- 新能源是谁贡献？
- 燃油下降了吗？
- 插混是不是继续替代？

### 图3 渗透率
折线：新能源渗透率 / BEV 占比 / PHEV 占比 / REEV 占比

> 一句话：新能源结构有没有切换。

### 图4 市场成交价
折线：`weighted_tp`

> 一句话：市场是在升级还是降价。

---

## ③ Brand Landscape

数据源：`brand_monthly`

### 品牌 TOP20
排名 · 销量 · 份额 · 同比 · 环比 · 价格 · 变化 ↑↓

### 品牌份额变化
Share Gain / Share Loss（例：BYD +1.8%, Tesla -0.9%）

### 品牌集团
自主 / 合资 / 豪华 或 国企 / 民企 / 外资，观察谁在吃市场。

### OEM
吉利 / 比亚迪 / 上汽 / 奇瑞 / 长安 集团竞争。

---

## ④ Model Ranking

数据源：`model_monthly`

- TOP50 车型：销量 · 排名变化 · 价格
- 新进入 TOP20（例：L6, YU7, LS9）
- 品牌车型结构（例：BYD 卖的是秦还是汉）
- 新能源车型排行：BEV / PHEV / REEV 分别排行

---

## ⑤ Product Structure

数据源：`product_segment_monthly`

这是 Schema 最有价值的部分。建议重点。

### 车身
SUV / Sedan / MPV 份额变化。

### 级别
A / A+ / B / C 是否继续大型化。

### 驱动
2WD / 4WD 四驱比例变化。

### 产品尺寸
利用 `weighted_length_mm` / `weighted_wheelbase_mm` 画趋势。

> 一句话：市场继续大车化。

---

## ⑥ Price Analysis

数据源：`price_segment_monthly`

### 价格带销量
0-10 / 10-15 / 15-20 / 20-25 / 25-30 / 30-40 / 40+ 市场容量。

### 增长最快价格带
例：20-25 万 +18%。

### 新能源价格带
BEV / PHEV / REEV 分别在哪个价格带集中。

### SUV 价格带
20-25 万 SUV、25-30 万 SUV，直接看到战场。

---

## ⑦ Geographic

数据源：`geo_monthly`

- 省份 TOP20：销量 · 新能源渗透
- 城市 TOP20：销量
- 城市等级：一线 / 新一线 / 二线 / 三线 变化
- 区域：华东 / 华南 / 华北 哪个恢复最快

---

## ⑧ Deep Insight

固定回答五个问题：

1. **本月最大的赢家是谁？**（品牌 / 车型 / 价格带）
2. **本月最大的输家是谁？**
3. **本月最大的结构变化是什么？**（例：SUV 首次超过 55%）
4. **本月最大的价格变化？**（例：20-25 万继续扩张）
5. **本月值得关注的新趋势？**（例：四驱比例增加 / 增程开始放缓）

---

## ⑨ Watch List

| 指标 | 本月 | 上月 | 趋势 |
|------|------|------|------|
| 总销量 | | | ↑ |
| 新能源渗透 | | | ↑ |
| BEV 占比 | | | ↓ |
| PHEV 占比 | | | ↑ |
| 平均成交价 | | | ↑ |
| SUV 份额 | | | ↑ |
| 中大型 SUV | | | ↑ |
| 豪华份额 | | | ↓ |
| 自主份额 | | | ↑ |
| 四驱比例 | | | → |

---

## ⑩ Change Detection（月度变化检测）

自动化检测异常变化，按历史分位标记。

| 模块 | 指标 | 本月变化 | 历史分位 | 是否异常 |
|------|------|----------|----------|----------|
| 市场 | 总销量 | +6.1% MoM | P82 | 🟢 |
| 能源 | PHEV 份额 | +2.1pct | P97 | 🔴 |
| 品牌 | 吉利份额 | +1.3pct | P94 | 🔴 |
| 价格 | 20-25 万 | +18% | P96 | 🔴 |
| 产品 | 中大型 SUV | +11% | P95 | 🔴 |
| 区域 | 三线城市新能源 | +4.2pct | P93 | 🔴 |

---

## 阅读顺序

1. **Executive Summary**：一句话掌握全局。
2. **Change Detection**：先看哪些指标出现历史级别变化。
3. **五大专题（市场 / 品牌 / 车型 / 产品 / 区域）**：定位变化发生在哪里。
4. **Deep Insight**：提炼值得关注的长期趋势。
