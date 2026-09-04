# Final Tournament｜10 Terminal Topics

**日期**：2026-08-19  
**评分对象**：10 个已完成 terminal evidence 的 Topic  
**目的**：选择最值得写成一份有洞察、可执行、可复述的报告，不选择单纯统计最强的 Topic。

## 1. Scoring Principle

每个维度 1–5 分，满分 25 分：

| 维度 | Champion 在问什么 |
|---|---|
| **Evidence strength** | 统计证据是否稳健，控制后是否仍成立？ |
| **Mechanism depth** | 是否知道为什么，而不只是知道有差？ |
| **Novelty** | 相比常识或原始简报，是否产生新增洞察？ |
| **Business actionability** | OEM 能否据此做产品、设计或沟通决策？ |
| **Narrative power** | 能否形成一句强而准确的报告主张？ |

**禁止规则：** Champion 不等于最小 p-value、最大 effect size 或最高单项证据分。总分接近时，优先选择机制闭环更完整、报告边界更清楚的 Topic。

## 2. Terminal Evidence Basis

| ID | Topic | Terminal run | 状态 | Evidence |
|---|---|---|---|---:|
| T1 | Purchase Mission | `topic_x` | READY | 13 |
| T2 | Age / Generation | `age_generation_it3` | READY | 3 |
| T3 | Income | `holdout_h1_income` | READY | 3 |
| T4 | Price Band | `price_band_it3` | READY | 3 |
| T5 | Configuration | `config_attribution_it3` | READY | 3 |
| T6 | BEV / PHEV | `bev_phev_it3` | INCONCLUSIVE | 3 |
| T7 | Charging Lifestyle | `charging_lifestyle` | READY | 6 |
| T8 | OEM Experience Gap | `oem_traditional_gap` | READY | 12 |
| T9 | Expectation Calibration | `expectation_calibration` | READY | 3 |
| T10 | Mileage Experience Lifecycle | `mileage_experience_lifecycle` | INCONCLUSIVE | 3 |

## 3. Five-Dimension Score

| Rank | ID | Topic | Evidence | Mechanism | Novelty | Actionability | Narrative | Total | Tournament role |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| **1** | **T1** | **Purchase Mission｜可感知升级价值** | **5** | **5** | 4 | **5** | **5** | **24** | **Champion / Production Topic** |
| 2 | T9 | Expectation Calibration｜补能预期兑现 | 5 | 4 | **5** | 4 | **5** | **23** | Finalist / strongest challenger |
| 3 | T5 | Configuration｜配置是载体，不是价值 | 4 | 4 | 4 | **5** | 4 | **21** | T1 supporting method |
| 4 | T4 | Price Band｜中端体验断层 | 4 | 3 | 4 | 4 | 4 | 19 | Alternate Topic |
| 4 | T7 | Charging Lifestyle｜补能生活方式分群 | 4 | 3 | 4 | 4 | 4 | 19 | Alternate Topic |
| 4 | T8 | OEM Experience Gap｜品牌差距被结构吸收 | **5** | 3 | 4 | 3 | 4 | 19 | Falsification / boundary Topic |
| 7 | T3 | Income｜收入非线性与舒适短板 | 4 | 3 | 4 | 4 | 3 | 18 | Supporting Topic |
| 8 | T2 | Age / Generation｜世代体验谱系 | 4 | 3 | 3 | 3 | 3 | 16 | Supporting Topic |
| 8 | T10 | Mileage Experience Lifecycle｜里程非线性 | 3 | 2 | 4 | 3 | 4 | 16 | Inconclusive research lead |
| 10 | T6 | BEV / PHEV｜技术路线差异 | 2 | 3 | 3 | 3 | 3 | 14 | Inconclusive / exclude |

## 4. Why T1 Wins

T1 不是因为 effect 最大，也不是因为 p-value 最小，而是五个维度同时过线：

- **Evidence**：13 条 terminal evidence，能源、价格、品牌和 `SEGMENT_DP` 控制后仍成立。
- **Mechanism**：从 purchase mission 到外观、驾驶、座舱，再到总体驾驶感受和转向手感，已经到 item / product-definition 层。
- **Novelty**：增购用户并不是简单要求更多参数，而是在寻找可感知的体验跃迁。
- **Actionability**：OEM 可以把产品定义从 feature checklist 转向 perceived upgrade design。
- **Narrative**：一句话准确、有反转且可用数据支撑：**“增购用户不差补能，差的是驾驶与外观的升级感。”**

### T1 的边界精化

P3 terminal evidence 已拒绝“价格越高，增购优势越大”的简单故事：增购−首购溢价在 15–20 万达到 +20.4，30 万+ 收窄到 +1.4。因此最终报告应写成：

> **中端靠升级感拉开用户，高端靠全民体验基准留在牌桌。**

这让 T1 既有主张，也有边界，不依赖漂亮但错误的单调叙事。

## 5. Why T9 Is Not Champion

T9 是最强挑战者，甚至在 Novelty 上高于 T1：

- “预期兑现”区别于 T7 的补能行为分群。
- 续航和充电时长预期同时控制后仍独立显著。
- 已连接到充电便利、状态可读、整体充电体验和续航 item。

但 T9 仍有两个限制：

1. 预期是车主横截面自报，尚未连接到具体传播承诺、产品规格或纵向兑现过程。
2. 产品决策还需要继续回答“哪一种预期由哪一个设计杠杆兑现”。

因此 T9 是非常强的第二名和后续专题，但 T1 的产品闭环更完整。

## 6. Topic Roles After Tournament

### Champion

- **T1 Purchase Mission**：唯一进入 Production Topic，产出正式报告。

### Finalist / Secondary Report

- **T9 Expectation Calibration**：最值得作为第二篇机制报告，或作为 T1 报告中的补能预期章节。
- **T4 Price Band**：适合作为 T1 的边界章节，不一定独立成主报告。
- **T7 Charging Lifestyle**：观察性分群证据，适合作为补能行为背景，不应写成因果机制。

### Supporting Method / Boundary Evidence

- **T5 Configuration**：不独立争夺 Champion，作为 T1 的配置价值验证方法。
- **T8 OEM Experience Gap**：重要的证伪/边界结果，证明品牌来源不是独立机制。
- **T3 Income、T2 Age**：补充分群背景，产品指向和叙事锋利度不足以争冠。

### Exclude

- **T6 BEV / PHEV**：terminal inconclusive，不能强行形成技术路线故事。
- **T10 Mileage Experience Lifecycle**：里程非线性值得保留为研究线索，但当前不足以支持产品质量衰减报告。

## 7. Final Decision

**Champion：T1 Purchase Mission｜增购用户的可感知升级价值。**

最终报告主张：

> **从参数升级到体验升级：已有车辆经验的用户，正在重新定义新能源车的“升级感”。**

选择逻辑不是“谁的统计最强”，而是：T1 在 terminal evidence、机制深度、OEM actionability 和 narrative power 之间形成了最完整的闭环，同时保留了对价格带非单调边界的诚实说明。
