# 从参数升级到体验升级
## 10 页 Champion Topic Deck

**Production Topic**：T1 Purchase Mission｜增购用户的可感知升级价值
**认知跃迁层**：T9 Expectation Calibration｜参数之外，用户评价的是承诺是否被兑现
**Supporting Topics**：T5 Configuration、T4 Price Boundary
**数据**：`data/source.sav`，9,937 行，权重 `APEAL_WT`
**Deck 任务**：保留完整研究结构（T1 主线 + 机制 + 边界），并在第 6–7 页用 T9 完成从"哪些用户喜欢什么"到"为什么这些产品特征最终会转化成魅力评价"的认知跃迁。

---

## Slide Contract 说明

本 Deck 的每页在标题下方携带一个 **metadata block**（YAML），供人读与 PPT Generator 读取。全文不新增 Topic，只把现有叙事升级为可驱动 production 的 contract。

### 四层信息结构

```text
① Narrative Layer     slide_role / question / answer / takeaway / next
② Claim Layer         claim_level / hero_message
③ Evidence Layer      evidence(topic, run, ids, sample_n, estimator, weight, controls)
④ Governance Layer    boundary / appendix_ref / provenance
```

### 字段枚举

- `slide_role`：`OPENING` / `THESIS` / `EVIDENCE` / `MECHANISM` / `BOUNDARY` / `FRAMEWORK` / `CLOSING`（+ `CONCEPTUAL_BRIDGE` 用于转场页）
- `claim_level`：`OBSERVATION` / `CONTROLLED_FINDING` / `MECHANISM_EVIDENCE` / `MECHANISM_INTERPRETATION` / `CONCEPTUAL_BRIDGE` / `BOUNDARY` / `MANAGERIAL_SYNTHESIS` / `RESEARCH_BOUNDARY`
- `visual.type`：`opening_stat` / `before_after` / `ranked_bar` / `item_drilldown` / `evidence_vs_counterevidence` / `conceptual_flow` / `evidence_chain` / `band_chart` / `framework_map` / `boundary_list`

> **claim_level 的作用**：阻止 PPT Generator 把"管理建议"画得像"统计已直接证明"。`MANAGERIAL_SYNTHESIS`（P9）只能配框架图，不能配显著性标注。

---

# P1｜Opening Thesis

```yaml
---
slide_role: OPENING
question: 已有车辆经验的用户，用什么标准定义新能源车的"升级感"？
answer: 真正的升级不是"多了什么"，而是"能不能马上感觉到不一样"；增购用户 APEAL 高于首购。
claim_level: OBSERVATION
evidence:
  topic: T1
  run: topic_x
  ids: [E-001]
  metric: APEAL_Index
  group: YPV_01
  method: compare（加权差）
  sample_n: 9937
  weight: APEAL_WT
visual:
  type: opening_stat
  primary_metric: 增购 vs 首购 APEAL
  hero: "798.4 vs +11.8"
  annotation:
    - "真正升级 = 可立即感知的差异"
boundary:
  - 封面只呈现一个观察，不展示控制口径（控制后见 P2）
takeaway: 已有车辆经验的用户用不同标准定义升级感。
next: 这个优势在控制能源/价格/品牌/细分后是否仍然成立？
appendix_ref: [A3]
---
```

## 从参数升级到体验升级

### 已有车辆经验的用户，用不同的标准定义新能源车的"升级感"

> **对已有车辆经验的用户，真正的升级不是"多了什么"，而是"能不能马上感觉到不一样"。**

```text
增购用户 APEAL = 798.4
高于首购 +11.8
```

**封面只保留一个问题：**

> 用户第一次开、坐、转向和使用这些配置时，能不能立即感觉这辆车升级了？

**演讲目的：** 先建立"增购人群 + 升级感"的故事，不先讲方法。

---

# P2｜Executive Finding / Controlled Gap

```yaml
---
slide_role: THESIS
question: 增购用户更高的 APEAL，是全面更好还是集中在特定体验？
answer: 增购优势在控制能源/价格/品牌/细分后仍成立（+18.17），但体验结构发生偏斜，集中在感性、动态与座舱。
claim_level: CONTROLLED_FINDING
evidence:
  topic: T1
  run: topic_x
  ids: [E-011]
  metric: APEAL_Index
  group: YPV_01
  method: OLS（控制 SUPER_SEGMENT_DP / CN_YNV_07 / MAKE_DP / SEGMENT_DP）
  estimator: WLS
  sample_n: 9450
  weight: APEAL_WT
visual:
  type: before_after
  comparison_semantics: raw_vs_adjusted
  primary_metric: 增购 − 首购 APEAL gap（控制前 +11.8 → 控制后 +18.17）
  annotation:
    - "结构控制后优势不消失"
boundary:
  - 横截面观察性关联，非因果实验
takeaway: 参数是门槛；能立即感觉到的驾驶、外观和座舱体验才是升级感。
next: 差异究竟落在哪些体验模块？
appendix_ref: [A3]
---
```

## 增购用户要的不是更多参数，而是更明确的体验跃迁

### 主证据：控制后增购优势仍然成立

| 组别 | APEAL |
|---|---:|
| 增购 | 798.4 |
| 首购 | 增购低 11.8 |
| 控制能源/价格/品牌/细分市场后 | 增购优势 +18.17 |

### 一句话结论

> **对已有车辆经验的用户，参数是门槛；能立即感觉到的驾驶、外观和座舱体验，才是升级感。**

**Supporting evidence：** T2/T3 表明用户的年龄与收入会改变体验标准，但不能替代 T1 的主机制；它们作为分层背景，而不是另起主线。

---

# P3｜Experience Structure

```yaml
---
slide_role: EVIDENCE
question: 增购 vs 首购的体验差异是全维度均匀，还是结构性偏斜？
answer: 高度偏斜：外观 +19.3、驾驶 +15.2、动力 +15.1、座舱 +12.5 拉开差距，补能仅 +1.3。
claim_level: OBSERVATION
evidence:
  topic: T1
  run: topic_x
  ids: [E-003]
  metric: 7 个模块指数（AEXT/ADRV/APERF/AINT/ASFTY/ACMFT/AFUEL）
  group: YPV_01
  method: compare（增购 vs 首购加权差；E-003 未控制）
  sample_n: [2481, 6177]
  weight: APEAL_WT
  controlled_anchor: P2 / E-011（总体优势控制后 +18.17 仍成立）
visual:
  type: ranked_bar
  primary_metric: 增购 − 首购 模块 APEAL gap
  categories: [外观, 驾驶, 动力, 座舱, 安全, 舒适, 补能]
  highlight: [外观, 驾驶, 动力, 补能]
  annotation:
    - "升级感集中"
    - "补能不是差异来源"
boundary:
  - 模块指数为聚合结构；AEXT 仅 1 个 rating 题，指数级差距含聚合放大（E-009）
  - T7 说明补能行为是生活方式分群，不能写成"快充导致体验变差"
takeaway: 这不是全面更好，而是体验结构发生了偏斜。
next: 驾驶差异落在哪些具体 item 上？
appendix_ref: [A2, A3]
---
```

## 增购用户的升级感，几乎不是被补能拉开的

### 真正拉开差距的是外观、驾驶、动力与座舱

### 增购 vs 首购的体验结构｜全篇 Hero Chart

```text
外观   +19.3  ████████████████████
驾驶   +15.2  ████████████████
动力   +15.1  ████████████████
座舱   +12.5  █████████████
安全   +10.9  ███████████
舒适    +8.8  █████████
补能    +1.3  ██
```

### 3 秒 Hero message

> **这不是全面更好，而是体验结构发生了偏斜：升级感集中在感性、动态和座舱。**

**Supporting evidence：** T7 说明补能行为本身仍是强分群变量，但其跨模块差异更像生活方式画像，不应被写成"快充导致体验变差"。

---

# P4｜Driving Mechanism

```yaml
---
slide_role: MECHANISM
question: 驾驶模块的差异，是抽象指数还是用户能感觉到的具体 item？
answer: 落实到具体 item：总体驾驶感受（ADRV_R_05，+0.23, d=0.215）为主承载，其次湿滑/常规转向，制动最弱。
claim_level: MECHANISM_EVIDENCE
evidence:
  topic: T1
  run: topic_x
  ids: [E-008]
  metric: ADRV_Index item 下钻（ADRV_R_01~05）
  group: YPV_01
  method: drilldown（增购 vs 首购，WLS）
  sample_n: [2481, 6177]
  weight: APEAL_WT
visual:
  type: item_drilldown
  primary_metric: 增购 − 首购 ADRV item Δ（10 分制）
  highlight: [ADRV_R_05 总体驾驶感受]
  annotation:
    - "主要承载项"
    - "制动弱，不做主叙事"
boundary:
  - Δ/d/p 为加权组间差异，横截面观察
takeaway: 用户感知的是动作与反馈，而不是抽象指数。
next: 但"有一个配置"是否就意味着用户能感觉到价值？
appendix_ref: [A3]
---
```

## 驾驶差异不是抽象指数，而是落实到用户能感觉到的 item

### Item 下钻（增购 vs 首购，WLS `APEAL_WT`，`E-008`）

| 体验层级 | Δ | d | p | 研究指向 |
|---|---:|---:|---:|---|
| **总体驾驶感受** | **+0.23** | **+0.215** | 6.2e-20 | 主要承载项 |
| 湿滑路况转向/操控 | +0.18 | +0.094 | 8.7e-05 | 复杂路况控制感 |
| 常规路况转向/操控 | +0.17 | +0.123 | 3.3e-08 | 日常动态反馈 |
| 制动性能 | +0.13 | +0.112 | 2.5e-06 | 相对较弱，不做主叙事 |

### Why

用户并不会先感知一个"ADRV 指数"，而是在第一次转向、加速和处理路况时，判断整车是否更有质感。

> **升级感的产品语言，应从"多了什么"翻译成"开起来哪里不一样"。**

到这里，T1 回答了"哪些用户、在哪些维度上给出更高评价"。但还没回答：**为什么这些特征最终会转化成魅力评价。**

---

# P5｜Feature ≠ Value

```yaml
---
slide_role: MECHANISM
question: 配置拥有是否自然转化为魅力评价？
answer: 不会。记忆座椅/主驾通风与驾驶体验存在稳定关联（+19.3/+13.3），但换购组拥有率最高（49%）且 APEAL 最低。
claim_level: MECHANISM_INTERPRETATION
evidence:
  topic: T5
  run: topic_x
  ids: [E-012]
  metric: ADRV_Index × SCR_SEAT00_04C_R1（驾驶座电动记忆）
  method: config_match（品牌 × 价格带 cell 内匹配）
  weight: APEAL_WT
visual:
  type: evidence_vs_counterevidence
  left: 配置 → 驾驶体验关联（记忆座椅 +19.3 / 主驾通风 +13.3）
  right: 拥有率 49% 但 APEAL 最低（换购组）
  hero_message: Feature ownership is not perceived value
boundary:
  - 品牌×价格带匹配后的 observational association，非配置因果估值
  - 不能写"配置提升驾驶 APEAL 多少分"
takeaway: 配置是载体，体验才是价值。
next: 用户又通过什么机制判断体验"值不值"？
appendix_ref: [A4]
---
```

## 高感知配置与体验关联，但配置数量本身不能制造魅力

### 机制链 1｜Feature → Experienced Difference

### T5 Configuration：左证据 / 右反证

```text
左：配置 × 体验（品牌 × 价格带 cell 内匹配）
记忆座椅        驾驶体验关联 +19.3（75% cell 一致）
主驾通风        体验关联 +13.3

右：反证
换购组记忆座椅拥有率最高：49%
但换购组 APEAL 最低
```

### 一句话

> **Feature ownership is not perceived value.**

配置是载体，体验才是价值。配置存在不等于产生感知价值；OEM 的验收必须检查用户能否感觉配置改变了驾驶、舒适或座舱体验。

**口径边界：** T5 是品牌×价格带匹配后的 observational association，不是配置的因果估值，也不是"配置提升驾驶 APEAL 多少分"。

---

# P6｜T9 Expectation Calibration ★

```yaml
---
slide_role: CONCEPTUAL_BRIDGE
question: 为什么这些产品特征最终会转化成魅力评价？
answer: 用户心里有一把"预期尺子"，用实际体验去量；参数只定义门槛，预期是否被兑现才定义评价。
claim_level: CONCEPTUAL_BRIDGE
evidence:
  topic: T9
  run: expectation_calibration_production
  derived_from: [P7 证据链（无独立数字页）]
visual:
  type: conceptual_flow
  flow:
    - "T1：哪些用户喜欢什么"
    - "T9：为什么这些特征会转化为魅力评价"
  hero_message: 用户不是先看参数表，而是心里先有一把"预期尺子"
boundary:
  - 转场页，不含统计数字；证据链在 P7
takeaway: 参数只定义了"门槛"；预期是否被兑现，才定义了"评价"。
next: 预期兑现的证据链是什么？
appendix_ref: [A5]
---
```

## 但用户真正评价的并不是参数本身，而是产品是否兑现了原有预期

### 认知跃迁：从"喜欢什么"到"为什么喜欢"

```text
T1  哪些用户喜欢什么
    Purchase Mission → Experience Structure
                ↓
T9  为什么这些特征会转化为魅力评价
    参数只定义了"门槛"
    预期是否被兑现，才定义了"评价"
```

### 一句话跃迁

> **用户不是先看参数表，而是在心里先有一把"预期尺子"，再拿实际体验去量。**

T1 负责指出差异在哪里；T9 负责解释这个差异是怎么被用户加工出来的。

---

# P7｜T9 Evidence Chain

```yaml
---
slide_role: EVIDENCE
question: 预期兑现是否真的连接到具体补能体验与总体 APEAL？
answer: 是。续航/充电时长"优于预期"在完整控制后仍显著关联总体魅力评价，并落到续航总体表现、充电口操作与总体充电体验。
claim_level: CONTROLLED_FINDING
evidence:
  topic: T9
  run: expectation_calibration_production
  ids: [E-001, E-002]
  signal_ids: [expectation_wow_01, expectation_wow_04]
  metric: APEAL_Index / AFUEL_Index / ACHAR_index / AFUEL_R_01 / ACHAR_R_01 / ACHAR_R_09
  exposure: [AFUEL_D_06 续航 vs 预期, ACHAR_D_05 充电时长 vs 预期]
  sample_n: 8524
  estimator: WLS + HC1
  weight: APEAL_WT
  controls: [SUPER_SEGMENT_DP, CN_YNV_07, PREMMAKE_DP, AGE_BUCKETS, CN_INCOME, CN_EDUCATION]
visual:
  type: evidence_chain
  flow:
    - "预期 Better / Worse"
    - "充电便利 · 充电口操作 · 续航总体表现 · 总体充电体验"
    - "Overall APEAL"
  annotation:
    - "兑现 = 加分"
    - "落差 = 扣分"
    - "总体充电体验是最稳定的承接项"
boundary:
  - 横截面、自报预期的观察性关联，非宣传承诺的因果实验
  - 不能写成"兑现预期可以提升 N 分 APEAL"
  - 可写：控制结构、价格、品牌与人口后，预期被兑现的用户评价系统性更高
takeaway: 预期落差是奖惩结构，而不只是正向选择偏差。
next: 这套升级感在不同价格带是否一样强？
appendix_ref: [A5]
---
```

## Expectation Better / Worse → 具体补能体验 → Overall APEAL

### 证据链条

```text
体验优于预期 / 差于预期
        ↓
充电便利 · 充电口操作 · 续航总体表现 · 总体充电体验
        ↓
Overall APEAL
```

### 控制口径下的关联

> **在控制价格、细分市场、品牌类型和人口特征后，"体验优于预期"的用户仍表现出显著更高的总体魅力评价。**

| 预期 exposure | 总体魅力评价（控制后关联） | p |
|---|---:|---:|
| 续航"体验优于预期" | 显著更高 | <0.001 |
| 充电时长"体验优于预期" | 显著更高 | <0.001 |
| 任一项"体验差于预期" | 对应反向更低 | 同向成立 |

### Item 层：预期落到了具体体验

| 具体体验 item | 承接预期 | 控制后关联 |
|---|---:|---:|
| 纯电续航总体表现 | 续航预期 | 正关联，p<0.001 |
| 充电口设计与操作便利性 | 充电时长预期 | 正关联，p<0.001 |
| 总体充电体验 | 两类预期最稳定的承接项 | 正关联，p<0.001 |

**样本与口径：** 有效预期档位 1/2/3 共同样本 `n=8,524`；WLS + HC1，两类预期同时进入模型；控制 `SUPER_SEGMENT_DP`、`CN_YNV_07`、`PREMMAKE_DP`、`AGE_BUCKETS`、`CN_INCOME`、`CN_EDUCATION`。

### 边界纪律

- 这是横截面、自报预期的**观察性关联**，不是宣传承诺的因果实验。
- **不能写成"兑现预期可以提升 N 分 APEAL"。**
- 可以写的是：控制结构、价格、品牌与人口后，预期被兑现的用户评价系统性地更高。

---

# P8｜Price Boundary

```yaml
---
slide_role: BOUNDARY
question: 升级感会随价格线性放大吗？
answer: 不会。增购优势在 15–20 万最强（+20.4），30 万+ 收窄（+1.4）——不是越贵越强。
claim_level: BOUNDARY
evidence:
  topic: T4
  run: topic_x
  ids: [E-013]
  metric: APEAL_Index × CN_YNV_07（价格带）× YPV_01
  method: segment（价格带内增购 vs 首购）
  weight: APEAL_WT
visual:
  type: band_chart
  primary_metric: 增购 − 首购 APEAL（分价格带）
  categories: [10–15万, 15–20万, 20–30万, 30万+]
  highlight: [15–20万]
  annotation:
    - "中端靠升级感拉开用户"
    - "高端靠全民体验基准留在牌桌"
boundary:
  - 不能把 T1 写成"越贵，增购优势越强"
  - 30 万+ 首购用户也已进入高体验基准
takeaway: 中端是体验升级最容易被拉开的区间。
next: 那 OEM 应该怎么改变验收方式？
appendix_ref: [A6]
---
```

## 升级感不会随价格线性放大

### T4：增购 vs 首购的价格带边界

| 价格带 | 增购−首购 |
|---|---:|
| 10–15 万 | +3.1 |
| **15–20 万** | **+20.4** |
| 20–30 万 | +3.3 |
| 30 万+ | +1.4 |

### 正确的边界主张

> **中端靠升级感拉开用户，高端靠全民体验基准留在牌桌。**

不能把 T1 写成"越贵，增购优势越强"。15–20 万是体验升级最容易被拉开的区间；30 万+ 则是首购用户也已进入高体验基准。

---

# P9｜OEM Design Framework

```yaml
---
slide_role: FRAMEWORK
question: 从 Feature Checklist 转向 Expectation × Experience Management，OEM 应该改变什么？
answer: 用四步框架重定义验收：识别用户任务 → 设计可感知差异 → 让配置附着体验 → 验证预期兑现。
claim_level: MANAGERIAL_SYNTHESIS
evidence:
  derived_from:
    - T1 / E-008（驾驶 item 承载可感知差异）
    - T5 / E-012（配置拥有 ≠ 感知价值）
    - T9 / expectation_calibration_production E-001 + E-002（预期兑现机制）
visual:
  type: framework_map
  mechanism: "Feature → Expectation → Experienced Difference → Perceived Upgrade"
  steps:
    - "Identify the user task｜T1"
    - "Design the felt difference｜T1"
    - "Attach features to experience｜T5"
    - "Validate expectation delivery｜T9"
  old_vs_new:
    - ["多了什么配置？", "用户能否立即感觉不一样？"]
    - ["参数是否领先？", "参数是否转化为可感知体验？"]
    - ["功能是否上线？", "用户第一次使用时是否觉得升级？"]
    - ["标称续航是否够长？", "用户是否觉得续航'兑现了承诺'？"]
boundary:
  - 管理综合（managerial synthesis），不是新统计结果
  - 由 T5/T9/T1 证据共同推导，不是四条孤立建议
takeaway: 参数是门槛，预期兑现才是评价来源。
next: 哪些结论被证据边界保护，不能讲？
appendix_ref: [A1, A4, A5, A7]
---
```

## 从 Feature Checklist 转向 Expectation × Experience Management

### 机制模型｜Feature → Expectation → Experienced Difference → Perceived Upgrade

```text
T5  Feature ≠ Value
    配置存在，不等于用户感知到价值
              ↓
T9  Expectation → Reward / Penalty
    体验超过或低于预期，形成奖惩结构
              ↓
T1  Experienced Difference → Perceived Upgrade
    驾驶、外观、座舱的变化被用户立即感觉到
              ↓
OEM  Expectation × Experience Management
    参数是门槛，预期兑现才是评价来源
```

**机制结论：** P9 不是四条孤立建议，而是由 T5、T9 和 T1 的证据共同推导出的产品设计框架。

### 四步产品框架

```text
1. Identify the user task｜T1
   增购用户要确认"这次真的升级了吗？"

2. Design the felt difference｜T1
   外观、驾驶、动力、座舱优先于参数堆叠

3. Attach features to experience｜T5
   高感知配置必须在第一次使用时被感觉到

4. Validate expectation delivery｜T9
   续航、充电和便利性承诺必须兑现
```

### OEM 应该改变的验收问题

| 旧问题 | 新问题 |
|---|---|
| 多了什么配置？ | 用户能否立即感觉不一样？ |
| 参数是否领先？ | 参数是否转化为可感知体验？ |
| 功能是否上线？ | 用户第一次使用时是否觉得升级？ |
| 标称续航是否够长？ | 用户是否觉得续航"兑现了承诺"？ |

**Supporting evidence：** T2/T3 用于定义不同用户的体验门槛；T7 用于识别补能生活方式；它们为设计分层提供 context，不改变 T1 主框架。

---

# P10｜Evidence Boundary + Final Takeaway

```yaml
---
slide_role: CLOSING
question: 哪些结论不能讲？
answer: T8（OEM 归零 p=0.53）、T6（p=0.138）、T10（INCONCLUSIVE）、T9（观察性）都是边界，不是可营销主张。
claim_level: RESEARCH_BOUNDARY
evidence:
  boundaries:
    - topic: T8
      run: oem_traditional_gap
      ids: [E-012]
      claim: "OEM 来源结构 raw gap 在完整控制后归零（WLS +2.7, p=0.53）"
    - topic: T6
      run: bev_phev_it3
      ids: [E-003]
      claim: "技术路线部分 item 有差异，但控制品牌后不显著（p=0.138）"
    - topic: T10
      run: mileage_experience_lifecycle
      ids: [E-003]
      claim: "里程峰值与回落成立但归因不稳定，terminal INCONCLUSIVE"
    - topic: T9
      run: expectation_calibration_production
      ids: [E-001, E-002]
      claim: "横截面、自报预期的观察关联，只能写控制后系统性更高"
visual:
  type: boundary_list
  annotation:
    - "READY Topic 用来支撑主张"
    - "INCONCLUSIVE Topic 用来保护主张边界"
boundary:
  - 本页内容是研究纪律本身，不允许在传播中弱化
takeaway: 从参数升级到体验升级：用户要的是"马上感觉到不一样"。
next: 收束（进入 Appendix）
appendix_ref: [A7]
---
```

## 研究纪律：知道哪些结论不能讲

### 不能讲的三条边界

- **T8**：OEM 来源结构 raw gap 在完整控制后归零（WLS `+2.7, p=0.53`）。不能把体验差异归因给"某类 OEM 天生更会做升级感"。
- **T6**：技术路线部分 item 有差异，但控制品牌后不显著（`p=0.138`）。不能强行写成"BEV/PHEV 决定体验"。
- **T10**：里程峰值与回落成立，但归因不稳定，terminal 为 `INCONCLUSIVE`。不能把横截面里程梯度写成纵向质量衰减。
- **T9**：预期关联是横截面、自报预期的观察关系，不是因果实验；只能写"控制后系统性更高"。

> **READY Topic 用来支撑主张；INCONCLUSIVE Topic 用来保护主张边界。**

## 最终 Takeaway

### 主结论

> **新能源车的下一轮升级，不是把参数表做得更长，而是让用户在第一次开、坐、转向和使用配置时，立即感觉这辆车真的变得更好。**

### 三个记忆点

1. **用户任务变了**：已有车辆经验的用户要的是可感知的体验跃迁。
2. **产品定义要变**：驾驶、外观、座舱和高感知配置要形成真实体验，而不是 feature count。
3. **验收标准要变**：参数必须兑现预期，体验必须在正确的价格区间里被看见。

### Final report architecture

```text
T1 Champion：提出主论点
T5 / T9 / T4：解释机制与边界
T2 / T3 / T7：提供 supporting context
T8 / T6 / T10：保护研究边界
```

**最终一句话：**

> **从参数升级到体验升级：当用户已经拥有过一辆车，真正的产品竞争就不再是"多了什么"，而是"他能不能马上感觉到不一样"。**

---

# Appendix Registry

> Presentation 主体保持 10 页。附录用于追问层：面试官问"18.17 怎么来的？为什么是 WLS？T5 为什么不能解释成因果？"时，从这里取证据。

| 编号 | 内容 | 关联页 | 来源 |
|---|---|---|---|
| **A1** | Methodology｜研究设计、权重、WLS/HC1、观察性边界 | P9 | `research/benchmark.md`、`analysis/_common.py` |
| **A2** | Variable / measurement definitions｜R/D/V 三档、item 定义、模块指数 | P3、P7 | `data/questionnaire_map.json` |
| **A3** | T1 full regression｜增购优势控制链（+11.8 → +18.17） | P1–P2 | `topic_x/evidence.jsonl` E-011 |
| **A4** | T5 matched cells｜品牌 × 价格带配置匹配 | P5 | `topic_x/evidence.jsonl` E-012 |
| **A5** | T9 full model｜预期兑现 FULL 控制回归 + item 下钻 | P6–P7 | `expectation_calibration_production/evidence.jsonl` E-001/E-002 |
| **A6** | T4 price segmentation｜价格带边界 | P8 | `topic_x/evidence.jsonl` E-013 |
| **A7** | Topic Tournament｜10 Topic 排序与研究治理 | P9–P10 | `research/topic_tournament.md`、`reports/final_tournament_10_topics.md` |

---

*Raccoon Research · 用数据、AI 和一点点常识，研究复杂世界。*
