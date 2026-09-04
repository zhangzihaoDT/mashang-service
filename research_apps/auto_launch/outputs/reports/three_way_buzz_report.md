# 三方声量对比报告：MG 07 vs 智己 LS9 vs 小米澎程 N90

**任务日期**: 2026-07-30
**基线版本**: v2.3（claim-level evidence / quality-direction 正交 / value-status 拆分）
**搜索 Profile**: deep_scan（confirmed ≥5源+≥2官源+≥90%覆盖 / fallback ≥8源+≥3类型+≥80%覆盖）
**时间窗口**: 近 7 日（2026-07-23 ~ 2026-07-30）

---

## 一、v2.3 架构变更

### 1.1 核心分层

```
Coverage 负责: Search Loop（field-level binary coverage，决定是否继续搜索）
Claim    负责: Result Understanding（claim-level multi-quality evidence，分析结果含义）
```

两套系统互不污染。`claim_evaluate` 是纯分析模块，不参与搜索循环控制。

### 1.2 数据结构

证据有两个正交维度：

| 维度 | 取值 | 含义 |
|------|------|------|
| `quality` | mention_only / qualitative / quantitative / official | 证据本身是什么 |
| `direction` | support / contradict / neutral | 证据支持还是反对 claim |

Claim 有两个聚合维度：

| 维度 | 取值 | 含义 |
|------|------|------|
| `value` | high / low / positive / negative / mixed / present | 结论的具体内容 |
| `status` | unknown / partial / probable / confirmed | 对该结论的确信度 |

### 1.3 Claim 状态聚合

```
score = sum(evidence quality scores)
  official      +3
  quantitative  +2
  qualitative   +1
  mention_only   0

≥6 → confirmed  3-5 → probable  1-2 → partial  0 → unknown
```

---

## 二、搜索概况

| 参数 | MG 07 | 智己 LS9 | 小米澎程 N90 |
|------|-------|---------|-------------|
| 采集方式 | Agent 闭环 | Agent 闭环 | 定向搜索（4 组查询，含抖音/bilibili 关键词） |
| 初始查询 | 微信指数 / 声量热度 / 关注度+抖音+bilibili+话题 | 同左 | SkyNomad+抖音+bilibili / N90增程+声量+热度 / 发布会讨论 / 关注度+话题 |
| 缺口查询 | 官方公告 | 公众号+微信讨论+微信指数+官方公告 | — |
| API 调用 | 4 次 | 8 次（微信指数类 gap 补充） | 4 次 |
| 缓存策略 | 禁用（--fresh） | 禁用（--fresh） | 禁用 |

---

## 三、单车型结果

### 3.1 MG 07

**结论**: `confirmed` | 独立信源: **18** | 官方源: **2**（MG Europe + 上汽MG） | 信源类型: media, official, social

| Claim | value | status | 最佳质量 | 证据数 | 概要 |
|-------|-------|--------|---------|--------|------|
| 信息来源 | high | confirmed | quantitative | 15 | 多源定量数据支撑 |
| 声量信号 | high | confirmed | quantitative | 16 | 多源定量数据支撑 |
| 关键事实 | high | confirmed | **official** | 19 | 有官方确认 |
| 微信提及 | high | confirmed | quantitative | 8 | 多源定量数据支撑 |
| 微信指数值 | high | confirmed | quantitative | 7 | 多源定量数据支撑 |
| 社交讨论 | high | confirmed | quantitative | 14 | 多源定量数据支撑 |
| 情感倾向 | positive | confirmed | quantitative | 13 | 含方向反证（部分 evidence 方向=contradict） |

**核心话题**：MG 07 预售 12.59 万起，总经理直播被骂下播后发 Rap 回怼，持续发酵。"断崖式下滑"、"信任溃败"等后续讨论出现。8 月下旬上市。

**evidence 示例**：
- `[quantitative][support]` "15万级塞满30万配置!MG 07预售，总经理却被冲下播"
- `[qualitative][support]` "直播被骂哭后，车企总经理怒发新歌:WO CHAO"
- `[quantitative][contradict]` "名爵MG07断崖式下滑:陈萃靠半固态噱头难掩高端化溃败"
- `[official][support]` "MG Motor Europe Press Releases"

---

### 3.2 智己 LS9

**结论**: `probable` | 独立信源: **20** | 官方源: 1（智己汽车官网） | 信源类型: media, official, social

| Claim | value | status | 最佳质量 | 证据数 | 概要 |
|-------|-------|--------|---------|--------|------|
| 信息来源 | high | confirmed | **official** | **31** | 官方确认 |
| 声量信号 | high | confirmed | quantitative | 20 | 多源定量数据支撑 |
| 关键事实 | high | confirmed | **official** | **49** | 官方确认 |
| 微信提及 | high | confirmed | quantitative | 9 | 多源定量数据支撑 |
| 微信指数值 | high | confirmed | quantitative | 7 | 多源定量数据支撑 |
| 社交讨论 | high | confirmed | quantitative | 22 | 多源定量数据支撑 |
| 情感倾向 | positive | confirmed | quantitative | 12 | 多源定量数据支撑 |

**核心话题**：LS9 Hyper 34.98 万上市，首周末门店挤爆，线控转向标配。LS6 占比降至四成，LS8+LS9 齐发力。

**evidence 示例**：
- `[quantitative][support]` "34.98万带走升级版9系旗舰!智己LS9把线控转向引入30万市场"
- `[qualitative][support]` "爆火出圈!上汽亿台里程碑神车!"
- `[official][support]` "智己汽车官网 - 智己LS9配置表"

---

### 3.3 小米澎程 N90

**结论**: —（定向搜索） | 独立信源: **10** | 结果: **29 条**

| Claim | value | status | 最佳质量 | 证据数 | 概要 |
|-------|-------|--------|---------|--------|------|
| 信息来源 | high | confirmed | quantitative | 22 | 多源定量数据支撑 |
| 声量信号 | high | confirmed | quantitative | 13 | 多源定量数据支撑 |
| 关键事实 | high | confirmed | quantitative | **24** | 多源定量数据支撑 |
| 微信提及 | high | confirmed | quantitative | 6 | 多源定量数据支撑 |
| 微信指数值 | unknown | **unknown** | — | **0** | 定向搜索未覆盖微信指数关键词 |
| 社交讨论 | high | confirmed | quantitative | 18 | 多源定量数据支撑 |
| 情感倾向 | positive | confirmed | quantitative | 7 | 多源定量数据支撑 |

**核心话题**：SkyNomad（澎程）7 月 9 日公布，7 月 30 日（今天）技术发布会。N70/N90 定价 22-33 万。昆仑增程器，续航超 1300km。92 号汽油争议引发全网讨论。未上市先火，F 码被炒至上万。

> 微信指数值 claim 为 unknown 的原因是定向查询未包含微信指数相关关键词，非声量不足。补充微信指数查询即可覆盖。

---

## 四、Claim-level 三方对比

### 4.1 核心指标

| 维度 | MG 07 | 智己 LS9 | 小米澎程 N90 |
|------|-------|---------|-------------|
| **管道结论** | **confirmed** | probable | —（定向搜索） |
| **独立信源** | 18 | **20** | 10 |
| **官方源** | **2** | 1 | 0 |
| **信源类型** | media, official, social | media, official, social | media, social |
| **总 evidence 数** | 92 | **150** | 90 |
| **覆盖公式** | v2.2 | v2.2 | — |

### 4.2 Claims 横比

| Claim | MG 07 | 智己 LS9 | 小米澎程 N90 |
|-------|-------|---------|-------------|
| 信息来源 | value=high, **confirmed** | value=high, **confirmed** | value=high, **confirmed** |
| 声量信号 | value=high, **confirmed** | value=high, **confirmed** | value=high, **confirmed** |
| 关键事实 | value=high, **confirmed** | value=high, **confirmed** | value=high, **confirmed** |
| 微信提及 | value=high, **confirmed** | value=high, **confirmed** | value=high, **confirmed** |
| 微信指数值 | value=high, **confirmed** | value=high, **confirmed** | **unknown**（未覆盖） |
| 社交讨论 | value=high, **confirmed** | value=high, **confirmed** | value=high, **confirmed** |
| 情感倾向 | value=positive, **confirmed** | value=positive, **confirmed** | value=positive, **confirmed** |

### 4.3 Evidence 质量构成

| quality | MG 07 | 智己 LS9 | 小米澎程 N90 |
|---------|-------|---------|-------------|
| official | 2% | **7%** | 0% |
| quantitative | **52%** | **53%** | **40%** |
| qualitative | 46% | 40% | 60% |
| (contradict direction) | **4%**（情感部分） | 0% | 0% |

智己 LS9 的 official 比例最高（7%），澎程 N90 的 qualitative 比例最高（60%）——发布会预热期的讨论以定性描述为主。MG 07 有 4% 的证据方向为 contradict（主要来自"口碑差"、"暴跌"、"被骂"等负面情感信号）。

### 4.4 声量阶段判断

| 车型 | 阶段 | 证据特征 | 预判 |
|------|------|----------|------|
| MG 07 | 舆情退潮期 | evidence 分散，qualitative 为主，有 contradict 方向 | 若无二次引爆自然回落，8 月上市可能小高峰 |
| 智己 LS9 | 上市首周 | evidence 高度密集（150 条），official 比例最高 | 产品热度持续，经销商风波是否再起是关键变量 |
| 小米澎程 N90 | 发布会前夜 | evidence 以 qualitative 为主（60%），缺少 official | 今晚发布会后进入主升浪，需补充官方源覆盖 |

---

## 五、指标口径

- **数据源**：豆包搜索 API，全量实时搜索，禁用缓存
- **时间窗口**：2026-07-23 ~ 2026-07-30（近 7 日）
- **覆盖公式**：`coverage = sum(tier_covered_weight × tier_weight) / sum(tier_total_weight × tier_weight)`，v2.2
- **Claim 聚合**：official=+3，quantitative=+2，qualitative=+1，mention_only=0；≥6 confirmed，3-5 probable，1-2 partial，0 unknown
- **证据方向**：按 field 配置反证关键词（sentiment→"投诉"/"被骂"/"暴跌"等），非全局一刀切

---

*报告由 Auto Launch Agent v2.3 自动生成*
