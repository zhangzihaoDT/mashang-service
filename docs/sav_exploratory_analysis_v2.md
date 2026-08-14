# .sav 问卷探索性分析研究思路 v2.0

本文档沉淀针对 `.sav`（SPSS 处理后的调查数据集）的探索性分析研究范式。  
新版流程不再把 SAV 视为研究世界的全部，而是以 **Questionnaire × SAV 联合建模** 为起点，先回答“问卷测量了什么、数据实际覆盖了多少”，再进入统计发现与业务解释。

> **当前实现**
>
> - `scripts/parse_nev_apeal_questionnaire.py`：解析问卷 PDF，建立 Question ↔ SAV Variable 映射，并输出模块覆盖率。
> - `scripts/explore_sav.py`：完成 SAV 数据字典、题型识别、QC、描述统计、配置归因、偏好识别、品牌/价位映射、差异扫描、Topic 深挖与统计验证。
>
> 两个脚本共同组成完整分析链路：**Measurement Contract → Data Contract → Statistical Discovery → Business Interpretation**。

---

## 1. 分析总框架

```text
Questionnaire PDF + SAV
        ↓
问卷解析
        ↓
Question ↔ Variable Mapping
        ↓
模块划分 + 数据覆盖率
        ↓
Analysis Scope Gate
        ↓
变量字典 / 题型识别
        ↓
Data QC
        ↓
Descriptive Statistics
        ↓
配置归因 / 偏好 / 品牌价位
        ↓
Module-aware 差异扫描
        ↓
Topic Candidates
        ↓
Topic 深挖
        ↓
统计验证
        ↓
用户 / 产品解释
        ↓
PPT
```

整个流程分为四层：

1. **Measurement Contract**：问卷设计了什么、题目如何组织、哪些题进入数据。
2. **Data Contract**：SAV 中有哪些变量、题型、权重、缺失和派生字段。
3. **Statistical Discovery**：用结构化统计方法找差异、关系和候选 Topic。
4. **Business Interpretation**：把统计证据翻译成用户洞察、产品定义和改进建议。

---

# Layer 1｜Measurement Contract

## 2. 问卷解析

分析不再从 SAV 列开始，而是先解析原始问卷。

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

在统计扫描前先确定“哪些问题值得被分析”。

每个 Topic / Module 至少记录：

```text
module
coverage_rate
coverage_status
question_count
sav_covered_count
missing_questions
open_text_count
analysis_allowed
caveat
```

建议规则：

1. `FULL` 模块默认进入自动扫描。
2. `PARTIAL` 模块进入扫描，但候选 Topic 自动带 coverage caveat。
3. `LIMITED` 模块默认不生成强模块级结论。
4. 如果缺失题正好是该 Topic 的核心测量项，则直接降级。
5. “没有发现差异”不能自动解释成“用户不在乎”，必须先检查 measurement coverage。

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

变量字典是后续统计的查表基础。

原则：

> **先问卷，再字典，后分析。**

---

## 8. 问卷题型识别

根据值标签、列结构和 Question Mapping 联合判断题型。

当前题型体系：

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
- 当前数据是否足够回答某个 Topic？

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

# Layer 3｜Statistical Discovery

## 10. Descriptive Statistics

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

### 切片

核心分组包括：

- 年龄 / 世代；
- 城市；
- 收入；
- 品牌；
- 价格；
- 细分市场；
- BEV / PHEV 等产品结构。

---

## 11. 配置归因（config-scan）

对 APEAL 类满意度研究，配置“有 / 无”的体验差异往往比单纯人口属性差异更接近产品定义。

逻辑：

```text
配置是否拥有
      ↓
APEAL / 子指数差异
      ↓
Effect Size
      ↓
人群 / 车型 / 价格混淆检查
      ↓
产品含义
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

> 配置有 / 无的满意度差异属于 observational association，不能直接解释为因果。

---

## 12. 偏好题识别（preference）

识别：

- Most Improved
- Love Most
- 其他最需改进 / 最喜爱类题型

输出：

- Top options；
- 提及率；
- 用户优先级；
- 模块归属。

作用：

- 解释“为什么某项体验得分低 / 高”；
- 为产品改进排序；
- 帮助 Topic 从统计差异转向真实需求。

---

## 13. 品牌 / 价位映射（camp）

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

---

## 14. Module-aware 自动扫描差异

自动扫描不再直接对 370 列“平铺捕鱼”，而是保留问卷层级。

推荐输出结构：

```text
M7 驾驶感受
└─ ACHAR_R 驾驶体验
   └─ Item 04
      ├─ Group: 30万+ vs 20-30万
      ├─ Δ = +X
      ├─ effect_size = ...
      ├─ p_adj = ...
      └─ coverage = FULL
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
× Sample Reliability
× Coverage Confidence
```

---

## 15. Topic Candidates

自动扫描的任务只是找到“值得看哪里”，不是直接生成结论。

每个 Topic 候选至少回答：

1. **What**
   - 发现了什么差异？

2. **Where**
   - 出现在哪个 Module / Question？

3. **Who**
   - 哪类用户 / 产品最明显？

4. **How large**
   - effect size 多大？

5. **Reliable?**
   - 样本量、显著性、coverage 是否足够？

6. **So what**
   - 是否能转成产品行动？

Topic 筛选标准：

- 差异大；
- 可解释；
- 可行动；
- 与研究问题相关；
- 证据链完整；
- 数据覆盖足够。

每轮输出 3–5 个 Topic 候选，而不是一次展开全部变量。

---

## 16. Topic 深挖

对候选 Topic 做多角度验证。

### 换一个维度看

例如：

- 年龄差异是否在不同价格带都成立？
- 品牌差异是否其实由价格驱动？
- 配置差异是否只存在于高端车型？

### 看内部结构

例如：

```text
年轻用户
├─ 高收入
├─ 低收入
├─ 一线城市
└─ 非一线城市
```

### 找解释变量

尝试建立：

```text
用户特征
    ↓
需求 / 场景
    ↓
配置 / 产品形态
    ↓
实际体验
    ↓
APEAL
```

### 排除替代解释

检查：

- 样本量；
- 品牌结构；
- 价格；
- 车型；
- 城市；
- 动力形式；
- measurement coverage；
- missing bias。

---

## 17. 统计验证

正式输出前进行统计检验。

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

自动扫描大量变量时必须做：

- Benjamini-Hochberg FDR

避免只因为变量多而产生大量假阳性。

### 样本量

- 小样本组标注；
- 给置信区间；
- 必要时降级为 directional signal。

---

# Layer 4｜Business Interpretation

## 18. 用户 / 产品解释

统计结果必须被翻译成业务语言。

每个 Topic 建议使用：

```text
数据事实
   ↓
用户 / 场景解释
   ↓
产品机制
   ↓
产品机会
   ↓
设计建议
```

### 用户侧

回答：

- 是谁？
- 在什么场景下？
- 为什么有这个需求？
- 与其他用户有什么不同？

### 产品侧

回答：

- 哪项产品设计 / 配置相关？
- 是“有没有”的问题，还是“做得好不好”的问题？
- 是否存在价格 / 配置层级的 trade-off？
- 车企应该提供什么？

### 事实与推断分离

明确标注：

- **Fact**：数据直接支持；
- **Inference**：业务机制解释；
- **Recommendation**：产品建议。

没有数据支撑的推断不得写成事实。

---

## 19. 面向产品定义的推荐分析结构

对于类似 NEV-APEAL、产品满意度或魅力研究，建议优先使用：

```text
用户是谁
  ↓
开什么 / 买什么
  ↓
有什么配置 / 设计
  ↓
实际体验如何
  ↓
哪些体验最影响整体魅力
  ↓
哪个群体最敏感
  ↓
车企应该提供什么设计
```

这比单纯寻找“哪个变量和 APEAL_Index 相关最高”更接近 Product Insights。

---

## 20. PPT

建议结构：

1. 研究问题
2. 数据与方法说明
3. Measurement Coverage
4. 核心发现
5. Topic 1
6. Topic 1 深挖
7. Topic 1 用户 / 产品机制
8. 产品建议
9. 其他候选发现
10. 方法附录

原则：

- 结论先行；
- 每页一个观点；
- 图表只承担证据作用；
- 每个数字可溯源；
- 标注 N、权重、检验方法；
- 低覆盖模块标注“数据受限”。

---

# 通用原则

## 1. 先建立 Measurement Contract

在开始统计之前，必须知道：

- 问卷测了什么；
- 哪些题进入 SAV；
- 哪些题没进入；
- 每个模块覆盖多少。

## 2. 再建立 Data Contract

明确：

- 每个变量是什么；
- 属于哪道题；
- 题型是什么；
- 是否派生；
- 是否权重；
- 缺失值如何处理。

## 3. QC 不过不下钻

Measurement Coverage、Missing、异常、逻辑问题未澄清前，不做强结论。

## 4. Question 是业务单位，Variable 是统计单位

多选和矩阵在 SAV 中可能展开成几十列，但不能把每一列当成独立业务问题。

## 5. Module 是洞察组织单位

最终 Topic 应优先形成模块内一致的 evidence，而不是依赖一个孤立显著变量。

## 6. 扫描是辅助，判断是核心

自动化负责：

> “哪里值得看”

研究者负责：

> “为什么值得讲，以及应该怎么做”

## 7. Effect Size 优先于单纯显著性

样本量大时 p 值很容易显著，必须同时关注：

- 差异大小；
- 效应量；
- 样本规模；
- Coverage。

## 8. 关联不等于因果

尤其是：

- 配置有 / 无；
- 品牌差异；
- 价格差异；
- 高低配差异。

必须检查第三变量。

## 9. 每个数字必须可溯源

至少保留：

```text
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

## 10. 没有数据支撑的观点不写成结论

证据不足时使用：

- “方向性发现”
- “数据受限”
- “待进一步验证”

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
# 变量字典
python scripts/explore_sav.py dict

# 题型识别
python scripts/explore_sav.py types

# Dataset QC
python scripts/explore_sav.py qc

# 描述统计
python scripts/explore_sav.py describe

# 配置归因
python scripts/explore_sav.py config-scan
python scripts/explore_sav.py config-scan --min-has 100

# 偏好题
python scripts/explore_sav.py preference

# 品牌 / 价位
python scripts/explore_sav.py camp

# 差异扫描
python scripts/explore_sav.py scan
python scripts/explore_sav.py scan --group-by SUPER_SEGMENT_DP CITY_TIER_DP

# Topic 深挖
python scripts/explore_sav.py topic --group-by GENERATION2 --metric APEAL_Index
python scripts/explore_sav.py topic --group-by CN_INCOME --metric APEAL_Index --pairwise
```

---

# 下一步工程化建议

当前两个脚本已经覆盖：

```text
Questionnaire Parser
        +
SAV Explorer
```

下一步建议增加一个统一的 analysis manifest，例如：

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
  }
}
```

让后续 `scan` / `topic` 自动读取：

- Question Mapping；
- Module；
- Coverage；
- Raw / Derived；
- Weight；
- Metric。

最终形成：

```text
Measurement Contract
        ↓
Data Contract
        ↓
Automated Discovery
        ↓
Research Judgment
        ↓
Product Insight
```

这套流程的目标不是“把 370 个变量都分析一遍”，而是把一个大型调查数据集压缩成：

> **少数几个证据完整、统计可靠、可以真正指导产品定义的 Topic。**
