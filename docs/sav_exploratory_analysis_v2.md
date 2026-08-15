# .sav 问卷探索性分析研究思路 v2.1

本文档沉淀针对 `.sav`（SPSS 处理后的调查数据集）的探索性研究范式。

新版流程不再把任务理解为“先把数据分析完，再总结洞察”，而是区分 **Discovery** 与 **Analysis** 两个阶段：先从数据中发现值得追踪的 Signal，形成可检验的 Hypothesis；再围绕少数高价值 Hypothesis 展开分析、验证和业务解释，最终形成 Insight 与 Topic。

> **核心链路**
>
> **Data → Signal → Hypothesis → Analysis → Insight → Topic**
>
> 在 J.D. Power 这类联合研究 / 咨询型任务中，“根据数据找出 insights，再针对一个 insight 展开分析”中的前一个 insight，更准确地理解为 **insight seed / candidate finding / hypothesis**，而不是最终结论。

> **当前实现**
>
> - `scripts/parse_nev_apeal_questionnaire.py`：解析问卷 PDF，建立 Question ↔ SAV Variable 映射，并输出模块覆盖率。
> - `scripts/explore_sav.py`：完成 SAV 数据字典、题型识别、QC、描述统计、配置归因、偏好识别、品牌/价位映射、差异扫描、Topic 深挖与统计验证。
>
> 两个脚本共同组成完整分析链路：
>
> **Measurement Contract → Data Contract → Signal Discovery → Hypothesis Framing → Topic Analysis → Business Insight**。

---

## 1. 分析总框架

```text
Questionnaire PDF + SAV
        ↓
Measurement Contract
问卷解析 / Question ↔ Variable Mapping / Coverage
        ↓
Data Contract
变量字典 / 题型 / Missing / Weight / QC
        ↓
──────────────── Discovery ────────────────
        ↓
Descriptive Scan + Module-aware Scan
        ↓
Signal
异常 / 差异 / 反常识 / 结构变化 / Gap
        ↓
Hypothesis
“这里可能存在什么值得解释的现象？”
        ↓
Topic Candidate Ranking
        ↓
──────────────── Analysis ─────────────────
        ↓
针对一个 Hypothesis 深挖
        ↓
统计验证 + 分层验证 + 替代解释排除
        ↓
Insight
“现象是什么 + 为什么重要 + 对谁成立”
        ↓
Business Interpretation
用户机制 / 产品机制 / 产品机会
        ↓
Topic PPT
```

整个流程分为五层：

1. **Measurement Contract**：问卷设计了什么、题目如何组织、哪些题进入数据。
2. **Data Contract**：SAV 中有哪些变量、题型、权重、缺失和派生字段。
3. **Signal Discovery**：快速扫描数据，找到异常、差异、Gap 和反常识现象，不急于解释。
4. **Topic Analysis**：针对少数 Hypothesis 做有方向的深挖、验证和排除替代解释。
5. **Business Insight**：把验证后的统计事实翻译成用户洞察、产品定义和可行动的 Topic。

关键原则：

> **探索阶段的目标不是“得出结论”，而是“提出一个值得分析的问题”。**

---

# Layer 1｜Measurement Contract

## 2. 问卷解析

分析不从 SAV 列开始，而是先解析原始问卷。

目标：

- 提取 Question ID、题目文本、模块、页面、题型。
- 区分：
  - 页面说明 / INTRO；
  - 实质题；
  - 拒答副编码；
  - 开放式文本题；
  - 量化题。
- 建立问卷层级：

```text
Module
└─ Question
   └─ Item / Option
      └─ SAV Variable
```

以 NEV-APEAL 当前样本为例：

- PDF 问卷：**193 题**
- 剔除页面说明、拒答副编码等后：**173 道实质题**
- SAV 覆盖：**151 道**
- 整体实质题覆盖率：**87%**
- 缺失 22 道中，12 道为开放式填写题
- 剔除开放文本后，量化题覆盖率接近 **96%**

因此，这份数据应被理解为：**接近完整的量化分析数据集，而非完整的原始问卷数据。**

---

## 3. Question ↔ Variable Mapping

通过问卷编号与 SAV 列结构建立映射。

### 映射类型

- **完全匹配**
  - Question ID 与 SAV 列直接一致。
  - 如 `SCR_*`、`NEV_*`、`A*R`、`ACHAR_D_*`。

- **部分匹配**
  - 一道题被拆成多个 SAV 变量。
  - 常见形式：
    - 多选展开：`NEV_04_R1 ... R97`
    - 子题拆分：`NEV_11A ... NEV_11G`
    - 区间字段：`START / END`
    - 语义差异矩阵：`YNV_CN_6_1 ... YNV_CN_6_14`
    - 拒答副编码映射回主变量

- **SAV 缺失**
  - 问卷中存在，但当前数据片段没有对应变量。
  - 当前包括：
    - NPS 推荐意愿；
    - 第二排座椅；
    - 轮胎品牌；
    - OTA；
    - 出生年份；
    - 身高体重；
    - 开放式填写题；
    - 页面 INTRO。

### 当前 NEV-APEAL 映射结果

| 映射状态 | 数量 | 含义 |
|---|---:|---|
| 完全匹配 | 131 | Question 与 SAV 列直接对应 |
| 部分匹配 | 26 | 一题多变量 / 子题拆分 |
| SAV 缺失 | 36 | 当前数据片段未提供 |
| **问卷总计** | **193** | — |

> 映射结果用于理解数据边界，而不是直接判断数据质量。  
> 对于多选、矩阵和派生指标，必须回到 Question 层理解业务含义。

---

## 4. 模块覆盖率

数据完整度必须按 **Module / Question** 判断，而不能只看 SAV 单列缺失率。

当前模块覆盖：

| 模块 | 覆盖率 | 建议 |
|---|---:|---|
| M5 座椅储物 | 100% | 可放心深挖 |
| M7 驾驶感受 | 100% | 可放心深挖 |
| M10 补能续航 | 98% | 可放心深挖 |
| M4 座舱内装 | 91% | 高覆盖 |
| M8 安全感知 | 89% | 基本完整 |
| M1 车辆属性 | 88% | 基本完整 |
| M3 进出装载 | 86% | 基本完整 |
| M9 智能化 | 80% | 部分覆盖，注意缺题 |
| M12 用户画像 | 80% | 部分覆盖 |
| M6 动力性能 | 71% | 谨慎下模块级结论 |
| M2 外观造型 | 60% | 适合作辅助证据 |
| M11 品牌感知 | 60% | 适合作辅助证据 |

### Coverage Gate

建议将模块覆盖转换成分析状态：

- **FULL：≥ 90%**
  - 可作为主 Topic 深挖。
  - 可形成模块级结论。

- **PARTIAL：75%–89%**
  - 可以分析。
  - 结论必须结合缺失题检查。
  - 必要时标注“数据覆盖不完整”。

- **LIMITED：< 75%**
  - 默认不作为完整模块结论的唯一依据。
  - 更适合作为辅助证据或局部问题分析。

> 模块缺题属于 **Measurement Coverage** 问题，不应与样本级 Missing Value 混为一谈。

---

## 5. Analysis Scope Gate

Scope Gate 的目的不是提前决定“分析什么结论”，而是决定 **哪些区域有资格进入 Signal Discovery**。

每个 Module 至少记录：

```text
module
coverage_rate
coverage_status
question_count
sav_covered_count
missing_questions
open_text_count
scan_allowed
strong_conclusion_allowed
caveat
```

建议规则：

1. `FULL` 模块默认进入自动扫描。
2. `PARTIAL` 模块进入扫描，但任何 Signal 自动携带 coverage caveat。
3. `LIMITED` 模块可以出现局部 Signal，但默认不升级为完整模块级 Insight。
4. 如果缺失题正好是某个 Hypothesis 的核心测量项，则该 Hypothesis 直接降级。
5. “没有发现差异”不能自动解释为“用户不在乎”，必须先检查 Measurement Coverage。

---

# Layer 2｜Data Contract

## 6. 数据读取（pyreadstat）

使用 `pyreadstat.read_sav()` 读取 `.sav`，同时获得：

- `df`：数据框；
- `meta`：SPSS 元数据。

重点保留：

- `column_names`
- `column_labels`
- `value_labels`
- `variable_value_labels`

注意：

- 检查 SPSS 用户定义缺失值；
- 中文标签编码；
- 是否存在派生字段；
- 是否存在权重列。

当前 NEV-APEAL 数据包含：

- `APEAL_Index` 及子指数；
- `APEAL_WT` 权重；
- 问卷原始变量；
- 多选拆分变量；
- 若干派生字段。

---

## 7. 变量字典

变量字典不再只是 SAV schema，而要与 Questionnaire Mapping 联合。

推荐字段：

```text
variable_name
variable_label
question_id
question_text
module
question_type
variable_type
value_labels
is_derived
is_weight
coverage_status
missing_rate
valid_n
```

变量字典是后续扫描和验证的查表基础。

原则：

> **先问卷，再字典，再扫描；不是拿到变量就直接建模。**

---

## 8. 问卷题型识别

根据值标签、列结构和 Question Mapping 联合判断题型。题型决定后续的扫描方式与验证方法。

### rating
11 分量表，如：

- `APEAL_OSAT`
- `AEXT_R_01 ...`
- `ACHAR_R_09`

统计口径：

- Mean
- Standard Deviation
- Top-2 Box
- Bottom-2 Box
- 分组差异

注意：

- `99 = N/A` 等特殊值统一转为 `NaN`。

### scale7
7 分语义差异量表，如：

- `YNV_CN_6_1 ... YNV_CN_6_14`

统计口径：

- Mean
- Distribution
- Positioning profile

不能因为标签为数字就误判为普通连续变量。

### categorical
单选或互斥分类，如：

- 城市层级；
- 品牌；
- 细分市场；
- 收入；
- 用户类型。

统计口径：

- 占比；
- 交叉表；
- 卡方；
- Cramér's V。

### multi
多选题以多个二分变量展开，但分析单位应回归 Question。

例如：

```text
NEV_04
├─ NEV_04_R1
├─ NEV_04_R2
...
└─ NEV_04_R97
```

统计口径：

- 提及率；
- 共现；
- 配置有 / 无；
- 多选组合。

### numeric
连续数值，包括：

- 年龄；
- 续航期望；
- 指数；
- 价格；
- 其他连续量。

统计口径：

- Mean / Median
- Quantile
- Correlation
- Regression / group comparison

---

## 9. Data QC

Data QC 分为两层：

### A. Measurement QC

回答：

- 哪些问卷题没有进入 SAV？
- 哪些模块覆盖不足？
- 是否缺失核心测量项？
- 是否存在开放题但当前无法量化？
- 当前数据是否足够验证某个 Hypothesis？

### B. Dataset QC

回答：

- 缺失率；
- 异常值；
- 非法量表值；
- 多选逻辑冲突；
- 跳转逻辑；
- 未映射值标签；
- 权重异常；
- 样本量过小。

特别区分：

> **Question not in SAV ≠ respondent missing value**

这是两类完全不同的数据问题。

---

# Layer 3｜Signal Discovery

这一层只回答：

> **“数据里哪里出现了值得继续追的问题？”**

它不要求一开始就解释为什么，也不要求直接形成最终 Insight。

---

## 10. Descriptive Scan

描述统计在这里的作用不是“完成分析”，而是建立基线并暴露 Signal。

### 分类题

- 频数
- 加权占比
- 有效样本量

### 多选题

- 选项提及率
- 基数 = 有效回答人数
- 不以选项数为分母

### 连续题

- Mean
- Median
- SD
- Quantiles

### Rating

- Mean
- Top-2 Box
- Bottom-2 Box
- Distribution

### 核心切片

- 年龄 / 世代；
- 城市；
- 收入；
- 品牌；
- 价格；
- 细分市场；
- BEV / PHEV 等产品结构。

### 重点寻找四类 Signal

1. **差异（Difference）**
   - 某群体明显高 / 低于另一群体。
2. **异常（Anomaly）**
   - 某结果明显偏离整体规律。
3. **Gap / Mismatch**
   - 价格、配置、品牌定位与实际体验不一致。
4. **Counter-intuitive Pattern**
   - 与常识或行业预期相反的结果。

例如：

```text
价格更高
   ≠
某项设计魅力更高
```

此时只记录为 **Signal**，不要立刻写成“高端用户不在乎设计”等强结论。

---

## 11. 配置扫描（config-scan）

对 APEAL 类满意度研究，配置“有 / 无”的体验差异往往是高价值 Signal 来源。

Discovery 阶段逻辑：

```text
配置是否拥有
      ↓
APEAL / 子指数差异
      ↓
Δ + Effect Size + N
      ↓
Signal
```

输出：

- 加权均值；
- Δ；
- Welch t-test；
- Cohen's d；
- 样本量。

过滤：

- 最小样本量；
- `Other`
- `Don't know`
- `Do not have`
- 非产品业务选项。

注意：

> Discovery 阶段看到的“配置有 / 无差异”只是 observational signal，不是配置效果的因果证明。

是否由价格、品牌、人群结构驱动，要留到 Topic Analysis 阶段验证。

---

## 12. 偏好题扫描（preference）

识别：

- Most Improved
- Love Most
- 其他最需改进 / 最喜爱类题型

输出：

- Top options；
- 提及率；
- 用户优先级；
- 模块归属。

Discovery 作用：

- 找到“高分但仍想改进”的矛盾；
- 找到“得分一般但用户特别在意”的机会；
- 识别满意度指标与显性偏好之间的 Gap；
- 为 Hypothesis 提供解释方向。

---

## 13. 品牌 / 价位 / 产品结构扫描（camp）

可按业务需要建立：

- 品牌阵营；
- 价格带；
- 产品类型；
- 细分市场；
- 动力形式。

当前品牌阵营映射属于分析假设，报告中必须注明。

注意：

- 样本结构 ≠ 市场份额；
- 没有外部销量数据时，不做“市场份额变化”结论。

这一层尤其适合寻找：

```text
定位 / 价格 / 配置
       ↓
预期体验
       ↕ Gap
实际 APEAL 体验
```

---

## 14. Module-aware Signal Scan

自动扫描不再直接对 370 列“平铺捕鱼”，而是保留问卷层级。

推荐输出结构：

```text
Signal ID: S-017
Module: M7 驾驶感受
Question: ACHAR_R 驾驶体验 / Item 04
Pattern: 30万+ vs 20-30万存在明显差异
Δ: +X
Effect Size: ...
N: ...
Coverage: FULL
Signal Type: difference
```

扫描内容：

- 分组均值差异；
- 分组占比差异；
- Pearson / Spearman；
- Cramér's V；
- 多选共现；
- 与总体偏离；
- 配置有 / 无；
- 产品属性 × 体验；
- 用户属性 × 体验。

排序优先级不只看 p 值，而应综合：

```text
Business Relevance
× Effect Size
× Pattern Novelty
× Sample Reliability
× Coverage Confidence
```

其中 **Pattern Novelty** 用于提高“反常识 / Gap / 新鲜结构”的优先级，避免扫描结果被大量正确但平庸的相关性淹没。

---

## 15. Signal → Hypothesis → Topic Candidate

这是 v2.1 的关键变化。

自动扫描的输出不直接叫 Insight，而先经过三层：

```text
Signal
数据里看到了什么？
        ↓
Hypothesis
这个现象可能意味着什么？
        ↓
Topic Candidate
它是否值得投入进一步分析？
```

### A. Signal

必须是数据可直接描述的事实，例如：

> 40 万+车型在部分座舱设计评价上没有明显高于 30–40 万车型。

### B. Hypothesis

是对 Signal 的 **待验证解释**，例如：

> 新能源高端化可能存在“价格升级快于用户可感知设计价值升级”的现象。

此时不能写成最终结论。

### C. Topic Candidate

把 Hypothesis 转成一个值得回答的商业问题：

> 高端新能源如何把价格溢价真正转化为用户可感知的设计魅力？

每个候选至少记录：

```text
signal_id
signal_statement
signal_type
module
question
segment
hypothesis
business_question
business_relevance
novelty
coverage
sample_reliability
analysis_plan
candidate_score
```

### 候选评分

建议综合：

```text
Topic Potential
= Business Relevance
× Evidence Strength
× Novelty
× Explainability
× Actionability
```

每轮只保留 **3–5 个 Topic Candidates**。

这里的目标不是“证明所有候选都成立”，而是决定：

> **哪一个值得花最多分析资源去打穿。**

---

# Layer 4｜Topic Analysis

从这一层开始，才真正进入“针对一个 insight 展开分析”。

这里的分析不是漫无目的继续切数据，而是围绕一个明确 Hypothesis 建立证据链。

---

## 16. Hypothesis-driven Topic 深挖

每个 Topic 必须先写一句 Hypothesis：

```text
我们观察到 ________（Signal），
怀疑背后存在 ________（Hypothesis），
因此需要验证 ________（Research Question）。
```

然后再决定分析动作。

### Who：对谁成立？

- 年龄 / 世代；
- 收入；
- 城市；
- 品牌；
- 价格带；
- 细分市场；
- 动力形式。

### Where：出现在哪些体验上？

- 哪个 Module？
- 是一个 Item，还是多个 Question 同方向？
- 是总体魅力，还是具体体验？

### How robust：是否稳定？

例如：

- 年龄差异是否在不同价格带都成立？
- 品牌差异是否其实由价格驱动？
- 配置差异是否只存在于高端车型？
- 换一种统计口径后是否还存在？

### Why：可能的机制是什么？

尝试建立：

```text
用户特征
    ↓
需求 / 使用场景
    ↓
产品设计 / 配置
    ↓
实际感知体验
    ↓
APEAL / Overall Appeal
```

### What else：排除替代解释

检查：

- 样本量；
- 品牌结构；
- 价格；
- 车型；
- 城市；
- 动力形式；
- Measurement Coverage；
- Missing Bias。

Topic 深挖的核心不是增加图表数量，而是不断回答：

> **“这个 Hypothesis 还站得住吗？”**

---

## 17. Statistical Validation

统计验证服务于 Hypothesis，不反过来由统计方法定义 Topic。

### 分类 × 分类

- Chi-square
- Cramér's V

### 分类 × 连续 / 量表

- t-test
- ANOVA
- Welch ANOVA

### 非正态

- Mann-Whitney
- Kruskal-Wallis

### 效应量

- Cohen's d
- η²
- Cramér's V

### 多重比较

Discovery 阶段自动扫描大量变量时必须做：

- Benjamini-Hochberg FDR

避免只因为变量多而产生大量假阳性。

### 样本量

- 小样本组标注；
- 给置信区间；
- 必要时降级为 directional signal。

### 最终状态

每个 Hypothesis 最终只能进入以下状态之一：

- **SUPPORTED**：多组证据支持，可升级为 Insight。
- **REFINED**：原假设过宽，收敛为更具体结论。
- **DIRECTIONAL**：方向存在，但样本 / Coverage 不足。
- **REJECTED**：进一步分析后不成立。

> **REJECTED 不是失败。**  
> Discovery 本来就允许大量 Signal 在验证阶段被淘汰。

---

# Layer 5｜Business Insight

## 18. Analysis → Insight

只有经过 Topic Analysis 后，Hypothesis 才有资格升级为 Insight。

一个完整 Insight 至少包含三部分：

```text
What happened
数据证明了什么？
        +
Why it matters
为什么这是值得关注的用户 / 产品问题？
        +
For whom / where
这个结论对谁、在哪些场景下成立？
```

例如：

```text
Signal
高价车型在若干设计维度并未同步获得更高评价
        ↓
Hypothesis
价格升级可能快于用户可感知设计价值升级
        ↓
Analysis
价格带 × 模块 × 品牌 × 用户分层验证
        ↓
Insight
高端用户并非简单追求更多配置；
真正拉开魅力差距的是能被持续感知的设计体验
```

因此：

> **Insight 不是一个显著性结果，而是经过验证的、具有商业意义的数据解释。**

---

## 19. Insight → Product Interpretation

统计结果必须被翻译成业务语言。

推荐证据链：

```text
Validated Insight
       ↓
用户 / 使用场景
       ↓
产品机制
       ↓
当前产品 Gap
       ↓
产品机会
       ↓
设计建议
```

### 用户侧

回答：

- 是谁？
- 在什么场景下？
- 为什么对这个体验敏感？
- 与其他用户有什么不同？

### 产品侧

回答：

- 哪项产品设计 / 配置相关？
- 是“有没有”的问题，还是“做得好不好”的问题？
- 是配置数量，还是体验整合？
- 是否存在价格 / 配置层级的 trade-off？
- 车企到底应该提供什么样的设计？

### 事实与推断分离

明确标注：

- **Fact**：数据直接支持；
- **Inference**：对用户 / 产品机制的解释；
- **Recommendation**：产品建议。

没有数据支撑的推断不得写成事实。

---

## 20. Topic PPT

Topic PPT 不是“分析过程汇报”，而是围绕一个 Insight 建立完整论证。

建议结构：

1. **Topic / Executive Insight**
   - 一句话说明真正发现了什么。
2. **Why this matters**
   - 为什么这个问题值得 OEM 关注。
3. **Signal**
   - 最初观察到了什么反常 / Gap。
4. **Evidence 1｜核心差异**
   - 证明现象确实存在。
5. **Evidence 2｜Who / Where**
   - 对谁、在哪些产品 / 场景最明显。
6. **Evidence 3｜Mechanism / Robustness**
   - 排除主要替代解释，解释背后的产品机制。
7. **Refined Insight**
   - 把最初 Hypothesis 收敛成最终结论。
8. **What OEM should do**
   - 对产品定义 / 设计 / 配置提出建议。
9. **Other Signals**
   - 其余 2–4 个候选 insight seeds，体现探索广度。
10. **Method / Data Appendix**
   - Measurement Coverage、N、Weight、检验方法等。

原则：

- **先讲 Topic，再讲证据，不从方法页开始。**
- 每页一个观点；
- 图表只承担证据作用；
- 每个数字可溯源；
- 标注 N、权重、检验方法；
- 低覆盖模块标注“数据受限”；
- 不展示为了“显得分析很多”而存在的图表。

---

# 通用原则

## 1. Data Contract 先于 Insight Discovery

在开始扫描之前，必须知道：

- 问卷测了什么；
- 哪些题进入 SAV；
- 哪些题没进入；
- 每个模块覆盖多少；
- 每个变量对应什么业务问题。

## 2. Discovery 先于 Analysis

不要一开始就对所有变量做深度分析。

正确顺序：

```text
先广度扫描
→ 找 Signal
→ 提 Hypothesis
→ 选 Topic
→ 再投入深度分析
```

这比：

```text
把所有数据分析一遍
→ 最后从结果里挑几个结论
```

更适合开放式商业研究任务。

## 3. Signal ≠ Insight

Signal 是“数据里发生了什么”。

Insight 是：

> **经过验证后，对现象形成了什么具有业务意义的解释。**

## 4. Hypothesis 必须写在 Analysis 前面

任何深挖动作都应该能回答：

> “这一步是在验证什么？”

如果回答不出来，往往是在进行无方向的数据切片。

## 5. Question 是业务单位，Variable 是统计单位

多选和矩阵在 SAV 中可能展开成几十列，但不能把每一列当成独立业务问题。

## 6. Module 是证据组织单位，Topic 是最终叙事单位

Module 帮助形成一致 evidence；Topic 可以跨 Module，只要服务于同一个 Hypothesis。

例如一个“高端化设计价值错位”的 Topic，可以同时使用：

- 座舱内装；
- 座椅；
- 智能化；
- 品牌感知；
- 价格带。

## 7. 自动化负责发现，研究者负责判断

自动化负责：

> “哪里值得看？”

研究者负责：

> “这意味着什么？”

以及：

> “为什么值得讲？应该怎么做？”

## 8. Effect Size 优先于单纯显著性

样本量大时 p 值很容易显著，必须同时关注：

- 差异大小；
- 效应量；
- 样本规模；
- Coverage；
- Business Relevance；
- Pattern Novelty。

## 9. 关联不等于因果

尤其是：

- 配置有 / 无；
- 品牌差异；
- 价格差异；
- 高低配差异。

必须检查第三变量和替代解释。

## 10. 每个数字必须可溯源

至少保留：

```text
Signal ID
Hypothesis ID
Question
Variable
Module
Filter
Weight
N
Statistic
Test
Effect Size
Coverage
```

## 11. 允许 Hypothesis 被推翻

探索性分析不是为了证明第一个想法。

证据不足时使用：

- “方向性发现”
- “数据受限”
- “待进一步验证”
- “原假设不成立”

比为了完成 PPT 强行包装成 Insight 更可靠。

---

# 当前 NEV-APEAL 实现

## A. 问卷解析与映射

```bash
python scripts/parse_nev_apeal_questionnaire.py
```

输出：

```text
outputs/reports/nev_apeal_questionnaire_map.md
outputs/reports/nev_apeal_questionnaire_map.json
```

主要内容：

- 193 题问卷结构；
- 173 道实质题；
- 151 道 SAV 覆盖；
- Question ↔ Variable Mapping；
- 模块覆盖率；
- SAV 缺失题；
- 派生指标 / 权重附录。

---

## B. SAV 探索分析

```bash
# Data Contract
python scripts/explore_sav.py dict
python scripts/explore_sav.py types
python scripts/explore_sav.py qc

# Discovery baseline
python scripts/explore_sav.py describe

# Signal sources
python scripts/explore_sav.py config-scan
python scripts/explore_sav.py config-scan --min-has 100
python scripts/explore_sav.py preference
python scripts/explore_sav.py camp

# Module-aware Signal Discovery
python scripts/explore_sav.py scan
python scripts/explore_sav.py scan --group-by SUPER_SEGMENT_DP CITY_TIER_DP

# Hypothesis-driven Topic Analysis
python scripts/explore_sav.py topic --group-by GENERATION2 --metric APEAL_Index
python scripts/explore_sav.py topic --group-by CN_INCOME --metric APEAL_Index --pairwise
```

现有 `scan` / `topic` 命令可以继续使用，但语义建议明确为：

```text
scan
= 广度扫描 → Signal → Hypothesis Candidates

topic
= 输入一个 Hypothesis → 深挖 / 验证 → Insight
```

---

# 下一步工程化建议

当前两个脚本已经覆盖：

```text
Questionnaire Parser
        +
SAV Explorer
```

下一步最重要的工程化方向，不是继续增加更多统计命令，而是显式增加 **Signal / Hypothesis 中间层**。

建议增加统一 analysis manifest：

```json
{
  "questionnaire": "...",
  "sav": "...",
  "mapping": "...",
  "modules": "...",
  "weight": "APEAL_WT",
  "primary_metric": "APEAL_Index",
  "coverage_gate": {
    "full": 0.90,
    "partial": 0.75
  },
  "discovery": {
    "max_topic_candidates": 5,
    "rank_by": [
      "business_relevance",
      "effect_size",
      "novelty",
      "sample_reliability",
      "coverage"
    ]
  }
}
```

建议新增标准化中间产物：

```text
outputs/analysis/signals.json
outputs/analysis/hypotheses.json
outputs/analysis/topic_candidates.md
outputs/analysis/topics/{topic_id}/evidence.json
```

其中：

### `signals.json`

只记录数据事实：

```text
signal_id
module
question
segment
pattern
magnitude
sample
coverage
```

### `hypotheses.json`

记录研究判断：

```text
hypothesis_id
source_signal_ids
hypothesis
business_question
why_interesting
analysis_plan
status
```

### Topic evidence

记录验证链：

```text
hypothesis
supporting_evidence
contradicting_evidence
alternative_explanations
statistical_validation
refined_insight
business_implication
```

最终形成：

```text
Measurement Contract
        ↓
Data Contract
        ↓
Automated Signal Discovery
        ↓
Research Hypothesis
        ↓
Hypothesis-driven Analysis
        ↓
Validated / Refined Insight
        ↓
Business Topic
        ↓
Topic PPT
```

这套流程的目标不是“把 370 个变量都分析一遍”，而是把一个大型调查数据集压缩成：

> **少数几个值得追踪的 Signal → 3–5 个可检验 Hypothesis → 1 个被真正打穿、能够指导产品定义的 Topic。**
