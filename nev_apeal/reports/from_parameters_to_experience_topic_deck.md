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
appendix_ref: [A3a, A3b]
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
  estimator: OLS + robust inference（E-011 未登记调查权重）
  sample_n: 9450
  weight: none recorded in E-011
visual:
  type: before_after
  comparison_semantics: raw_vs_adjusted
  primary_metric: 受控模型中的增购 − 换购 APEAL gap（+18.17）
  annotation:
    - "结构控制后优势不消失"
boundary:
  - 横截面观察性关联，非因果实验
takeaway: 参数是门槛；能立即感觉到的驾驶、外观和座舱体验才是升级感。
next: 差异究竟落在哪些体验模块？
appendix_ref: [A3c]
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
appendix_ref: [A2]
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
appendix_ref: [A2]
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
  metric: ADRV_Index × SCR_SEAT00_04C_R1（驾驶座记忆）
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
appendix_ref: [A4a, A4b]
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
appendix_ref: [A5a]
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
appendix_ref: [A5a, A5b, A5c]
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
appendix_ref: [A1, A4b, A5b, A7]
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

# Appendix Registry｜Evidence Explainer

> Presentation 主体保持 10 页。附录不只是统计资产索引，而是教读者沿着同一条路径理解证据：**原始问题 → 数据编码 → 比较对象 → 结果指标 → 计算方法 → 能讲什么/不能讲什么**。

## Evidence Anatomy｜一条证据怎么来的

所有核心 Evidence 统一回答六个问题：

```text
① 用户被问了什么？
        ↓
② 回答如何变成分析变量？
        ↓
③ 我们比较了谁和谁？
        ↓
④ Δ / β 是怎么算出来的？
        ↓
⑤ 为什么说它不是随机波动？
⑥ 能讲到哪一步，不能讲到哪一步？
```

### A1｜How to read this research

```text
问卷原题
  ↓ 编码 / 清理 / 分组
分析变量（exposure）
  ↓ 比较或建模
结果指标（APEAL / module / item）
  ↓ 统计不确定性
Evidence + boundary
```

读法纪律：先看用户问题，再看变量；先看比较对象，再看数字；最后看边界。`WLS + HC1` 是计算工具，不是结论本身。

### A2｜Measurement｜从 193 道问卷题到体验指标

```text
原始问卷 193 题
│
├─ R｜Rating：54 题
│   10 分体验评分
│      ↓
│   模块指数 / item 下钻
│
├─ D｜Diagnostic：39 题
│   改进点、喜欢点、与预期相比
│      ↓
│   机制解释 / exposure
│
└─ V｜Verbatim：12 题
    开放回答
       ↓
    定性补充，不直接构成主统计结果
```

`item` 的精确定义：模块指数下钻后的单个 10 分评分题（`*_R_*`），如 `ADRV_R_05`“车辆的总体驾驶感受”。

本研究直接使用数据集已有的 `APEAL_Index`、`ADRV_Index`、`AFUEL_Index` 等字段，**不在本次分析中重新构造指数**。`APEAL_OSAT` 是问卷中的总体拥车和驾驶体验题；`APEAL_Index` 是数据集提供的总体指数，二者不能混写。

来源：`data/questionnaire_map.json`、`data/source.sav`、`contracts/modules.json`。

### A3a｜T1 原始问题与购买任务分组

| 层 | 内容 |
|---|---|
| ① 用户被问了什么？ | 本页主体：`YPV_01` 原题 |
| ② 回答如何变成分析变量？ | 本页主体：`YPV_01` → 首购/换购/增购 |
| ③ 我们比较了谁和谁？ | 增购 vs 首购（raw）/ 增购 vs 换购（受控） |
| ④ Δ / β 是怎么算出来的？ | 见 A3b（raw Δ）与 A3c（受控 Δ） |
| ⑤ 为什么说它不是随机波动？ | 见 A3c（p-value 链） |
| ⑥ 能讲到哪一步，不能讲到哪一步？ | 可讲差异，不可讲因果（见 A3c 边界） |

**① 用户被问了什么？**

问卷题 `YPV_01`：

> 以下哪一个选项最适合描述您的这辆[品牌车型]？

**② 回答如何变成分析变量？**

SAV 中的编码与业务语言：

```text
1｜It replaces another vehicle
       ↓ 换购：代替家中原来的车

2｜It is an additional vehicle to my household
       ↓ 增购：家里新增加的车

3｜It is the first ever vehicle for my household
       ↓ 首购：家里的第一辆车
```

因此，`Purchase Mission` 不是研究人员凭空创造的标签，而是来自一条真实问卷题的回答编码。

来源：`questionnaire_map.json: YPV_01`、`topic_x/evidence.jsonl: E-001`。

### A3b｜T1 Raw Δ｜+11.8 是怎么算的

| 层 | 内容 |
|---|---|
| ① 用户被问了什么？ | 见 A3a（`YPV_01`） |
| ② 回答如何变成分析变量？ | 见 A3a（`YPV_01` → 首购/换购/增购） |
| ③ 我们比较了谁和谁？ | 增购组 vs 首购组（加权平均） |
| ④ Δ / β 是怎么算出来的？ | 本页主体：加权平均差 |
| ⑤ 为什么说它不是随机波动？ | 见 A3c（p-value 链） |
| ⑥ 能讲到哪一步，不能讲到哪一步？ | 见本页“业务翻译” |

**③ 我们比较了谁和谁？**

比较对象是 `YPV_01` 的增购组与首购组，结果指标是 `APEAL_Index`：

```text
YPV_01：购买任务
        │
        ▼
APEAL_Index：总体产品魅力评价
```

本项目直接读取数据集中的 `APEAL_Index`，并使用调查权重 `APEAL_WT` 计算组内平均评价。

```text
首购用户                 增购用户
加权平均 APEAL           加权平均 APEAL
   786.6        →           798.4
```

**④ Δ / β 是怎么算出来的？**

```text
Δ = 增购组加权平均 − 首购组加权平均
  = 798.4 − 786.6
  ≈ +11.8
```

**⑥ 能讲到哪一步，不能讲到哪一步？**

业务翻译：`+11.8` 的意思是，样本中增购用户的加权平均评价比首购用户高约 11.8 分；**不是“增购导致 APEAL 提升 11.8 分”**。

证据：T1 / `E-001`，加权 compare，权重 `APEAL_WT`。

### A3c｜T1 Adjusted Δ｜+18.17 是怎么算的

| 层 | 内容 |
|---|---|
| ① 用户被问了什么？ | 见 A3a（`YPV_01`） |
| ② 回答如何变成分析变量？ | 见 A3a（`YPV_01` → 首购/换购/增购） |
| ③ 我们比较了谁和谁？ | 增购 vs 换购（受控模型） |
| ④ Δ / β 是怎么算出来的？ | 本页主体：受控 OLS 系数 |
| ⑤ 为什么说它不是随机波动？ | 本页主体：稳健标准误 → p-value |
| ⑥ 能讲到哪一步，不能讲到哪一步？ | 本页边界 |

**③ 我们比较了谁和谁？**

先注意比较对象：这里不能把两个数字机械地读成“同一差距控制后变大”。

```text
RAW｜增购 vs 首购
实际观察到的组间平均差
+11.8

ADJUSTED｜增购 vs 换购
控制能源 / 价格 / 品牌 / 细分市场后的组间差
+18.17
```

**④ Δ / β 是怎么算出来的？**

E-011 使用的是 OLS 受控模型；它实际上在问：如果把能源类型、价格、品牌和细分市场这些结构差异纳入模型，增购相对换购还剩多少评价差异？由于 raw 与 adjusted 的参照组不同，不能把 `+18.17 - +11.8` 解读成“控制变量带来的增量”。

因此 `+18.17` 应理解为**受控模型中的增购 vs 换购组间差**，不是一个可以脱离参照组和模型解释的神秘 β。

```text
APEAL_Index = 购买任务 + 能源 + 价格 + 品牌 + 细分市场 + 误差
```

**⑤ 为什么说它不是随机波动？**

因为估计差异可能受抽样偶然影响：

```text
估计差异 +18.17
       ↓
稳健标准误：估计有多不稳定
       ↓
t = 系数 / 标准误
       ↓
p-value：如果真实没有差异，看到这么大差异有多难
```

`p` 越小，纯随机波动解释当前差异的说服力越弱。技术原名和具体标准误类型应以对应 Evidence 记录为准；E-011 没有登记 `APEAL_WT`，因此本页不把它包装成 WLS 结果。对于明确使用 WLS 的 Evidence，业务翻译才是“按调查权重估计 + 更稳健的不确定性判断”。

**⑥ 能讲到哪一步，不能讲到哪一步？**

边界：横截面观察性分析，不能写成购买任务造成了 APEAL 提升。

证据：T1 / `E-011`，样本 `n=9,450`，完整结构控制。

### A4a｜T5 配置题来自哪里

| 层 | 内容 |
|---|---|
| ① 用户被问了什么？ | 见本页：配置字段非独立原题 |
| ② 回答如何变成分析变量？ | 本页主体：`SCR_SEAT00_04C_R1` → 有/无 |
| ③ 我们比较了谁和谁？ | 有记忆座椅 vs 无记忆座椅（见 A4b 的匹配方式） |
| ④ Δ / β 是怎么算出来的？ | 见 A4b（品牌 × 价格带 cell 内匹配） |
| ⑤ 为什么说它不是随机波动？ | 配置关联未作显著性主证，作为反证使用 |
| ⑥ 能讲到哪一步，不能讲到哪一步？ | 本页边界：配置拥有 ≠ 感知价值 |

**① 用户被问了什么？**

T5 使用的是 SAV 中的配置字段 `SCR_SEAT00_04C_R1`。它不是 `questionnaire_map.json` 中的一条独立原题，而是由 SAV 标签定义的派生配置变量：

```text
Memory seat - Driver seat（驾驶座记忆座椅）
0 = No
1 = Yes
```

**② 回答如何变成分析变量？**

因此业务上应读成“车辆是否拥有驾驶座记忆座椅”，而不是扩展为问卷没有明确写出的“电动记忆”。体验结果则来自 `ADRV_Index` / `ADRV_R_*`：

```text
配置字段：有 / 无记忆座椅
        ↓
体验结果：驾驶体验评分
        ↓
总体 APEAL：作为外部结果指标
```

**⑥ 能讲到哪一步，不能讲到哪一步？**

配置拥有不是感知价值。换购组记忆座椅拥有率最高（49%）但 APEAL 最低，正是 T5 的反证。

来源：`contracts/variables.json: SCR_SEAT00_04C_R1`、`topic_x/evidence.jsonl: E-012`。

### A4b｜T5 什么叫品牌 × 价格带内匹配

| 层 | 内容 |
|---|---|
| ① 用户被问了什么？ | 见 A4a（配置字段） |
| ② 回答如何变成分析变量？ | 有/无记忆座椅（见 A4a） |
| ③ 我们比较了谁和谁？ | 本页主体：同品牌 × 同价格带内 有/无 |
| ④ Δ / β 是怎么算出来的？ | 本页主体：cell 内匹配后比较关联差异 |
| ⑤ 为什么说它不是随机波动？ | 匹配降低结构混淆，但仍非实验 |
| ⑥ 能讲到哪一步，不能讲到哪一步？ | 本页边界：observational association |

**③ 我们比较了谁和谁？**

不要直接比较：

```text
有记忆座椅  vs  无记忆座椅
```

因为有配置的车可能本来就更贵、品牌更强、车型结构不同。

本研究尽量比较“更像的车”：

```text
同品牌 × 同价格带
┌───────────────────────────┐
│ 有记忆座椅    无记忆座椅   │
│      ↓            ↓        │
│   驾驶体验      驾驶体验   │
└───────────────────────────┘
              ↓
          比较关联差异
```

**④ Δ / β 是怎么算出来的？**

匹配后的关联差异来自 `E-012`：记忆座椅对驾驶感受（ADRV）的匹配效应 `+19.3`、主驾通风 `+13.3`；增购记忆座椅拥有率 41.9% vs 首购 24.4%，但换购拥有率最高（49%）且 APEAL 最低。

**⑥ 能讲到哪一步，不能讲到哪一步？**

这仍不是因果实验，因为同品牌、同价格带内的用户和车辆还可能存在未观察差异。正确说法是“匹配后的 observational association”，不能说“记忆座椅带来 N 分 APEAL ROI”。

证据：T5 / `E-012`，品牌 × 价格带 cell 内匹配。

### A5a｜T9 两个原始“预期”问题

| 层 | 内容 |
|---|---|
| ① 用户被问了什么？ | 本页主体：两个“与购车预期相比”原题 |
| ② 回答如何变成分析变量？ | 本页主体：Worse / About / Better |
| ③ 我们比较了谁和谁？ | 预期被兑现 vs 未兑现（约当参照组） |
| ④ Δ / β 是怎么算出来的？ | 见 A5b（同时进入受控模型） |
| ⑤ 为什么说它不是随机波动？ | 见 A5b（HC1 → p-value） |
| ⑥ 能讲到哪一步，不能讲到哪一步？ | 见 A5c（观察性边界） |

**① 用户被问了什么？**

**续航预期：** `AFUEL_D_06`

> 这个续航里程和您购车时预期的行驶里程相比，是怎样的？

**充电时长预期：** `ACHAR_D_05`

> 当前这辆车的充电时间与您购车时的预期相比，是怎样的？

**② 回答如何变成分析变量？**

```text
1 Worse than I expected       比预期差
2 About the same as expected  和预期差不多
3 Better than I expected      比预期好
```

`ACHAR_D_05` 另有 `99 N/A` 档位：

```text
99 N/A                        无效/不适用，剔除
```

分析只保留两类预期 exposure 的有效档位 1/2/3，`About as expected` 为参照组，共同样本 `n=8,524`。

来源：`questionnaire_map.json: AFUEL_D_06 / ACHAR_D_05`、`expectation_calibration_production/evidence.jsonl: E-001`。

### A5b｜T9 从 Better/Worse 到总体评价

| 层 | 内容 |
|---|---|
| ① 用户被问了什么？ | 见 A5a（`AFUEL_D_06` / `ACHAR_D_05`） |
| ② 回答如何变成分析变量？ | 见 A5a（Worse / About / Better） |
| ③ 我们比较了谁和谁？ | Better/Worse vs About（约当） |
| ④ Δ / β 是怎么算出来的？ | 本页主体：同时进入受控模型 |
| ⑤ 为什么说它不是随机波动？ | 本页主体：HC1 稳健 → p<0.001 |
| ⑥ 能讲到哪一步，不能讲到哪一步？ | 见 A5c |

**④ Δ / β 是怎么算出来的？**

```text
AFUEL_D_06：续航 vs 购车预期
ACHAR_D_05：充电时长 vs 购车预期
                 ↓
      Worse / As expected / Better
                 ↓
同时进入 WLS + HC1
                 +
价格 / 细分市场 / 品牌类型 / 年龄 / 收入 / 教育
                 ↓
APEAL_Index       AFUEL_Index       ACHAR_index
                 ↓
AFUEL_R_01 / ACHAR_R_01 / ACHAR_R_09
```

这不是“跑了一个 fancy regression”，而是两个直观的用户问题，在控制结构后仍然连接到总体评价和具体体验 item：

- 续航预期主要承接到 `AFUEL_R_01` 纯电续航总体表现；
- 充电时长预期主要承接到 `ACHAR_R_01` 充电口设计与操作便利性；
- `ACHAR_R_09` 总体充电体验是两类预期最稳定的承接项。

**⑤ 为什么说它不是随机波动？**

模型使用 `APEAL_WT` 的 WLS 与 HC1 稳健标准误：续航 Better 对 `AFUEL_R_01` `+0.3786`（p<0.001）、充电时长 Better 对 `ACHAR_R_09` `+0.5645`（p<0.001），Worse 方向相反。

证据：T9 / `expectation_calibration_production/E-001/E-002`。

### A5c｜T9 为什么仍然不是因果

| 层 | 内容 |
|---|---|
| ① 用户被问了什么？ | 见 A5a（两个预期原题） |
| ② 回答如何变成分析变量？ | 见 A5a（Worse / About / Better） |
| ③ 我们比较了谁和谁？ | Better/Worse vs About（约当） |
| ④ Δ / β 是怎么算出来的？ | 见 A5b（受控模型） |
| ⑤ 为什么说它不是随机波动？ | 见 A5b（HC1 → p<0.001） |
| ⑥ 能讲到哪一步，不能讲到哪一步？ | 本页主体 |

**⑥ 能讲到哪一步，不能讲到哪一步？**

T9 的证据可以支持：

> 控制结构、价格、品牌与人口后，预期被兑现的用户评价系统性更高。

不能支持：

```text
把宣传承诺改成 X
        ↓
APEAL 必然提升 N 分
```

原因是本数据为车主横截面、自报预期观察；用户预期、车辆选择、使用环境和体验评价可能同时受其他因素影响。要估计传播承诺或具体配置的因果 ROI，需要实验或纵向数据。

证据：T9 / `expectation_calibration_production/E-001/E-002`。

### A6｜T4 价格带怎么切、Δ 怎么读

| 层 | 内容 |
|---|---|
| ① 用户被问了什么？ | 购车总花费（`CN_YNV_07` 填写题） |
| ② 回答如何变成分析变量？ | `CN_YNV_07` → 业务价格带分组 |
| ③ 我们比较了谁和谁？ | 各价格带内：增购 vs 首购 |
| ④ Δ / β 是怎么算出来的？ | 本页主体：带内加权平均差 |
| ⑤ 为什么说它不是随机波动？ | 作为边界条件，不作显著性主证 |
| ⑥ 能讲到哪一步，不能讲到哪一步？ | 本页边界：价格带是边界，不是单调规律 |

**② 回答如何变成分析变量？**

价格带来自购车总花费 `CN_YNV_07` 的业务分组，比较对象仍是 `YPV_01` 的购买任务组。

**④ Δ / β 是怎么算出来的？**

每个价格带内先计算增购与首购的 APEAL 差值：

```text
每个价格带
    增购加权平均 APEAL
  − 首购加权平均 APEAL
    = 该价格带 Δ
```

**⑥ 能讲到哪一步，不能讲到哪一步？**

结果不是单调上升：15–20 万 `+20.4`，30 万+ `+1.4`。因此价格带在这里是**边界条件**，不是“价格越高升级感越强”的证据。

证据：T4 / `topic_x/E-013`，权重 `APEAL_WT`。

### A7｜Topic Tournament 与研究治理

主 Deck 的层级不是按 p-value 从小到大排列，而是经过五个价值维度选择：

```text
Evidence strength
Mechanism depth
Novelty
Business actionability
Narrative power
```

最终角色：

```text
T1 Champion              提出主论点
T5 / T9 / T4             解释机制与边界
T2 / T3 / T7             提供 supporting context
T8 / T6 / T10            保护研究边界
```

因此 `READY Topic` 用来支撑主张；`INCONCLUSIVE Topic` 用来保护主张边界。附录中的技术字段用于复核，不应取代业务解释，也不应把观察性结果升级成因果结论。

来源：`research/topic_tournament.md`、`reports/final_tournament_10_topics.md`、各 Topic `state.yaml` 与 `evidence.jsonl`。

---

*Raccoon Research · 用数据、AI 和一点点常识，研究复杂世界。*
