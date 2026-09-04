# 三方声量对比报告：吉利银河 TT vs MG 07 vs MONA L03

**任务日期**: 2026-07-30
**基线版本**: v2.3（claim-level evidence / quality-direction 正交 / value-status 拆分）
**搜索 Profile**: deep_scan
**时间窗口**: 近 7 日（2026-07-23 ~ 2026-07-30）

---

## 一、搜索概况

| 参数 | 吉利银河 TT | MG 07 | MONA L03 |
|------|------------|-------|----------|
| 采集方式 | Agent 闭环 | Agent 闭环 | Agent 闭环 |
| 初始查询 | 微信指数 / 声量热度 / 关注度+抖音+bilibili+话题 | 同左 | 同左 |
| 缺口查询 | 官方公告 | 官方公告 | 官方公告 |
| API 调用 | 4 次 | 4 次 | 4 次 |

---

## 二、单车型结果

### 2.1 吉利银河 TT

**管道结论**: None（未满足任何停止条件） | 独立信源: 11 | 官方源: 0 | 信源类型: media, social

| Claim | value | status | 证据数 | 最佳质量 | direction 分布 |
|-------|-------|--------|--------|---------|--------------|
| 信息来源 | high | confirmed | 7 | quantitative | 全 support |
| 声量信号 | high | confirmed | **19** | quantitative | 全 support |
| 关键事实 | high | confirmed | **26** | quantitative | 全 support |
| 微信提及 | high | **probable** | 3 | quantitative | 全 support |
| 微信指数值 | high | **probable** | 3 | quantitative | 全 support |
| 社交讨论 | high | confirmed | 7 | quantitative | 全 support |
| 情感倾向 | positive | confirmed | 9 | quantitative | 全 support |

**核心话题**：
- Ultra 版预售 27 分钟售罄 999 台，追加 699 台。20.98 万，全系 800V
- 7 月 6 日上海首秀，7 月 21 日 Ultra 版预售
- 对标小米 SU7，15-22 万区间
- 银河品牌整体"纠偏"，半年 193.5 万辆

**管道停止分析**：confirmed 需要 ≥2 官方源（0 ✗），fallback 需要 ≥3 信源类型（仅 media+social，2 ✗），所以未触发任何条件停止。但 coverage 100% 且无 missing fields，gap 无新查询，自然退出。

---

### 2.2 MG 07

**管道结论**: **confirmed** | 独立信源: **19** | 官方源: **2**（MG Europe + 上汽MG） | 信源类型: media, official, social

| Claim | value | status | 证据数 | 最佳质量 | direction 分布 |
|-------|-------|--------|--------|---------|--------------|
| 信息来源 | high | confirmed | 15 | quantitative | 全 support |
| 声量信号 | high | confirmed | 15 | quantitative | 全 support |
| 关键事实 | high | confirmed | 18 | **official** | 全 support |
| 微信提及 | high | confirmed | 9 | quantitative | 全 support |
| 微信指数值 | high | confirmed | 8 | quantitative | 全 support |
| 社交讨论 | high | confirmed | 12 | quantitative | 全 support |
| 情感倾向 | positive | confirmed | 13 | quantitative | **2% contradict** |

**核心话题**：
- 12.59 万起预售，总经理直播被骂下播 → 发 Rap 回怼 → 持续发酵
- "断崖式下滑"、"信任溃败"等复盘
- 8 月下旬上市，宁王电池+半固态+激光雷达

---

### 2.3 MONA L03

**管道结论**: **probable** | 独立信源: 16 | 官方源: 1（小鹏汽车？） | 信源类型: media, official, social

| Claim | value | status | 证据数 | 最佳质量 | direction 分布 |
|-------|-------|--------|--------|---------|--------------|
| 信息来源 | high | confirmed | **20** | quantitative | 全 support |
| 声量信号 | high | confirmed | 18 | quantitative | 全 support |
| 关键事实 | high | confirmed | **23** | quantitative | 全 support |
| 微信提及 | high | confirmed | 12 | quantitative | 全 support |
| 微信指数值 | high | confirmed | 7 | quantitative | 全 support |
| 社交讨论 | high | confirmed | 13 | quantitative | 全 support |
| 情感倾向 | positive | confirmed | 5 | quantitative | 全 support |

**核心话题**：
- 7 分钟大定破 2 万，1 小时冲到 46,859 台
- 12.38 万起售，10-15 万价位段
- 女性用户占比 65%，欧阳娜娜发布车评
- 小鹏整体订单暴降 72%，爆款热度退潮

> 注意：MONA 作为通用名词产生少量噪声（非汽车类结果），但不影响 claim 聚合——7 条 claim 全部 confirmed。

---

## 三、三方对比

### 3.1 核心指标

| 维度 | 吉利银河 TT | MG 07 | MONA L03 |
|------|------------|-------|----------|
| **管道结论** | —（未触发停止） | **confirmed** | **probable** |
| **独立信源** | 11 | **19** | 16 |
| **官方源** | 0 | **2** | 1 |
| **信源类型** | media, social | media, **official**, social | media, **official**, social |
| **总 evidence** | 74 | **90** | **98** |
| **全部 confirmed** | 5/7 | **7/7** | **7/7** |

### 3.2 Claim 对比

| Claim | 吉利银河 TT | MG 07 | MONA L03 |
|-------|------------|-------|----------|
| 信息来源 | value=high, **confirmed** (n=7) | value=high, **confirmed** (n=15) | value=high, **confirmed** (n=20) |
| 声量信号 | value=high, **confirmed** (n=**19**) | value=high, **confirmed** (n=15) | value=high, **confirmed** (n=18) |
| 关键事实 | value=high, **confirmed** (n=**26**) | value=high, **confirmed** (n=18) | value=high, **confirmed** (n=23) |
| 微信提及 | value=high, **probable** (n=3) | value=high, **confirmed** (n=9) | value=high, **confirmed** (n=12) |
| 微信指数值 | value=high, **probable** (n=3) | value=high, **confirmed** (n=8) | value=high, **confirmed** (n=7) |
| 社交讨论 | value=high, **confirmed** (n=7) | value=high, **confirmed** (n=12) | value=high, **confirmed** (n=13) |
| 情感倾向 | value=positive, **confirmed** (n=9) | value=positive, **confirmed** (n=13) | value=positive, **confirmed** (n=5) |

### 3.3 Evidence 质量构成

| quality | 吉利银河 TT | MG 07 | MONA L03 |
|---------|------------|-------|----------|
| official | 0% | **2%** | **1%** |
| quantitative | **34%** | **50%** | **28%** |
| qualitative | 66% | 48% | 72% |
| contradict | 0% | **1%** | 0% |

MG 07 的 quantitative 比例最高（50%），与其中包含大量具体数字（12.59 万、5 款配置、15000+ 销量）相关。MONA L03 以 qualitative 为主（72%），虽然有订单数字，但媒体报道以定性描述居多。银河 TT 介于两者之间。

### 3.4 声量阶段判断

| 车型 | 阶段 | 特征 | 预判 |
|------|------|------|------|
| 吉利银河 TT | **预售爆发期** | 27 分钟售罄话题集中，证据密集（26 条 key_fact），但信源类型不足触发深 scan 停止条件 | 追加预售 + 8 月交付可能续热 |
| MG 07 | **舆情发酵期** | 信源最广（19），官方源最完整（2），quantitative 证据占比最高 | 8 月上市可能带来二次热度，但舆情消退趋势明显 |
| MONA L03 | **销量稳定期** | 证据最丰富（98 条总 evidence），所有 claim 密集 confirmed，但小鹏整体下滑隐忧 | 长期稳态销冠，增量看点在新车型 |

---

## 四、指标口径

- **数据源**：豆包搜索 API，全量实时搜索，禁用缓存
- **时间窗口**：2026-07-23 ~ 2026-07-30（近 7 日）
- **覆盖公式**：v2.2；**Claim 聚合**：official=+3，quantitative=+2，qualitative=+1；≥6 confirmed，3-5 probable
- **停止策略**：deep_scan — confirmed（≥5 源 + ≥2 官源 + ≥90% 覆盖），fallback（≥8 源 + ≥3 类型 + ≥80% 覆盖）

---

*报告由 Auto Launch Agent v2.3 自动生成*
