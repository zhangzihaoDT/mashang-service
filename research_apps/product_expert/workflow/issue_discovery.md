# Issue Discovery — 从门店反馈到问题模式

本文件定义 **Product Expert** 研究的发现流程：把非结构化的门店反馈，经
`evidence → issue → pattern → finding` 四级抽象，变成可追溯、可复核、可交付的研究结论。

## 管线总览

```text
原始 CSV（仓库外，只读）
    │  抽取：保留原文锚点 + 归一化
    ▼
Evidence   EV-####   ← schemas/evidence.schema.json
    │  归并：同功能/同维度/同现象合并
    ▼
Issue      ISS-####  ← schemas/issue.schema.json   ← issue_review 门禁
    │  聚类：共享功能 / 共享维度 / 共享对标
    ▼
Pattern    PAT-####  ← schemas/pattern.schema.json  ← issue_review 门禁
    │  语义对象：pattern_key + 机制假设，不携带统计
    │  收敛：从 evidence 确定性派生（见 workflow/convergence.md）
    ▼
Convergence CONV-#### ← schemas/convergence.schema.json
    │  Attribution + Counts + recurrence + evidence_strength + Temporal Comparison
    │  上升：业务含义 + 建议
    ▼
Finding    FND-####  ← schemas/finding.schema.json
```

原则：**只允许向下追溯，不允许跳跃**。任何 finding 都必须能经 pattern、issue 回到
evidence，再回到原始表的某一行某一列（`source_ref`）。跳过 evidence 直接下结论视为无效。

**单一事实来源**：Pattern 是纯语义对象；所有数量、Attribution、`recurrence` 与
`evidence_strength` 都由 Convergence 从 evidence 派生。Pattern、Finding 与 `run.md`
不得再手写这些统计，避免出现「run.md 写 6 位专家、evidence 实际 7 位」这类双份事实漂移。

## 输入

- 原始数据：见 `README.md` 的「数据来源」，仓库外绝对路径，只读引用，不复制进仓库。
- 记录粒度：一行 = 一位产品专家在一次门店支持（v0.2 起为一次每日反馈提交）中的汇总。
- v0.2（2026-09-12 起）数据源为『产品专家支持每日反馈』：前段选择题由
  `scripts/derive_survey_stats.py` 确定性解析（不进本发现流程）；本流程只处理后段自由文本。
- 关键字段映射（`source_ref.source_field`）：

| 原始字段 | source_field | 主要证据类型 | 适用版本 |
| --- | --- | --- | --- |
| L6产品体验弱点 | `l6_weakness` | 用户反馈 / 专家观察 | v0.1 |
| LS6产品体验弱点 | `ls6_weakness` | 用户反馈 / 专家观察 | v0.1 |
| 各车型试驾反馈 | `test_drive_feedback` | 试驾用户反馈 | v0.1 |
| LS8/LS9产品建议或销售情况 | `ls8_ls9_suggestion` | 建议 / 销售情况 / 对标 | v0.1 |
| 门店整体销售情况（客流/试驾/锁单） | `store_sales` | 运营事实 | v0.1 |
| 门店整体印象 | `store_impression` | 专家整体判断 | v0.1 |
| 今日产品专家门店支持最大的感想 | `daily_impression` | 专家观察 / 用户原话 | v0.2 |
| LS6产品体验相关问题 | `product_issue_ls6` | 专家观察 | v0.2 |
| L6产品体验相关问题 | `product_issue_l6` | 专家观察 | v0.2 |
| LS8/LS9产品体验相关问题 | `product_issue_ls8_ls9` | 专家观察 | v0.2 |
| 关于LS6的竞品，用户有什么特别想说的 | `competitor_comment` | 竞品对标 | v0.2 |
| 配图 | `other` | 附件引用 | 通用 |

支持日期 / 产品专家 / 支持城市+门店 不单独抽取，而是作为每条 evidence 的 `source_ref`
上下文保留。

## 步骤

### S1 抽取 Evidence

逐个字段扫描，把一段话拆成独立、原子、可定位的观察：

- **一条 evidence 只描述一个对象的一个现象**。同一段里提到「方向盘挡视线」和「前备箱不灵敏」，
  拆成两条。
- **保留原文**：`quote` 尽量逐字摘录，`statement` 只做归一化（补全对象、明确方向），
  不得加入原文没有的因果或程度词。
- **区分证据类型**：
  - `direct_quote` 用户/店长原话
  - `paraphrase` 专家转述
  - `expert_observation` 专家自身观察（如门店客流结构）
  - `benchmark` 对标友商后得出的差距（如「小鹏 GX 有 B 柱扶手」）
- **正负都记录**：`sentiment=positive` 是有用信号（优势项、正面对标），不要只抽负面。
- **无内容字段跳过**：如「-无展车」「新款未到店」不是产品弱点，可作为 `notes` 或
  `store_sales` 上下文，不强行生成 issue。
- 每条分配 `EV-####`，`source_ref` 必须指向真实 `record_index` + `source_field`。

### S2 归并 Issue

把 evidence 聚成「同一个问题」：

- **同一性判据**（满足任一即倾向合并）：
  1. 同一 `affected_function`（如「前备箱开启」）；
  2. 同一体验维度 + 同一现象（如「内饰做工/尖角划伤」）；
  3. 同一明确诉求（如「增加取送车服务」）。
- 跨门店、跨专家出现同一现象 → **合并为一个 issue**，累加 `store_count`、`store_count` 去重。
- 保留 `first_seen_date` / `last_seen_date`。
- 典型 example：遵义「椭圆方向盘挡视线」与亳州「圆角/线控」若指向同一部件与现象才合并；
  仅同属 `cockpit_ergonomics` 不足以合并。

### S3 聚类 Pattern（语义对象）

把 issue 上升为机制假设。Pattern 只表达语义，不承载统计：

- 聚类轴（优先级从高到低）：
  1. **共享功能/部件**（如「前备箱 + 前舱储物箱」→ 储物设计假设）；
  2. **共享体验维度**（如多处「豪华感/高级感不足」→ 内饰价值感假设）；
  3. **共享竞争对标**（如多处对标小鹏 GX / 极氪 7X → 竞争差距假设）。
- `hypothesis` 必须写成**可被推翻的假设**，不得写成结论。
- 若证据只支持「存在现象」而不支持「为什么」，标 `confidence=low` 或 `inconclusive`。
- **pattern_key（跨 run 语义主键）**：写 Pattern 之前先查 `patterns/pattern_keys.json`：
  - 语义命中已有 key → **reuse**，必要时把新表述追加为 `aliases`；
  - 确为新语义 → **propose new key** 并登记 `first_pattern_id` / `first_run_id`。
  - 禁止由单次 run 自由生成未登记的 key；`pattern_id` 只标识本次 run 实例，不用于跨 run 对齐。
- **不在 Pattern 上写统计**：`evidence_count` / `store_count` / `recurrence` /
  `evidence_strength` / `cross_store` / `cross_series` 一律由 Convergence 派生。

### S3.1 派生 Convergence

按 `workflow/convergence.md` 从 Pattern 确定性派生 Convergence：

- 来源链：`pattern.issue_ids → issues[].evidence_ids → evidence[].source_ref`。
- Attribution 固定三维：产品专家 / 城市+门店 / 支持时间。
- Counts、`recurrence`、`evidence_strength`、Temporal Comparison 均由规则计算，不由 LLM 判断。
- 可用 `scripts/derive_convergence.py <run_dir>` 生成 `convergence.json`。

### S4 形成 Finding 候选

- 只有 `status=confirmed` 的 pattern 才能进入 finding。
- finding 必须回答：**结论是什么 → 证据有多强 → 业务意味着什么 → 建议做什么 → 边界在哪**。
- finding 只引用 `pattern_ids` + `convergence_ids`；证据强度、复现层级、覆盖门店/专家/时间从
  Convergence 读取，**不在 finding 内复制**。研究者判断写入 `confidence`。
- 结论与观察分离：`statement` 中若含推断，必须在 `boundary` 标注。

## 受控词表

- **series**：`L6` `LS6` `LS7` `LS8` `LS9` `OTHER`
- **category**：`exterior` `interior` `cockpit_ergonomics` `seating_space` `storage`
  `charging` `driving_dynamics` `nvh` `smart_cockpit` `adas` `quality_reliability`
  `configuration` `sales_service` `other`
- **business_signal**：`purchase_blocker` `complaint` `feature_request` `competitive_gap`
  `operational` `positive_signal` `other`
- **severity**：`blocker` `high` `medium` `low`（口径见 `issue_review.md`）
- **recurrence**：`isolated` `repeated` `systemic` —— **由 Convergence 派生**，不在 Pattern 手写
- **evidence_strength**：`weak` `moderate` `strong` —— **由 Convergence 派生**，不由 LLM 判断

新增词表值前，先在 `schemas/*.schema.json` 的 enum 中登记，再使用。

## 门禁与产物

- Issue / Pattern 定稿前必须过 `issue_review.md` 的评审清单。
- 产物落到本应用自身目录，路径相对 `research_apps/product_expert/`：
  - 结构与字段契约：`schemas/`
  - 发现流程与评审规则：`workflow/`
  - 跨 run 语义主键：`patterns/pattern_keys.json`
  - 统计派生：`runs/<run_id>/convergence.json`（`scripts/derive_convergence.py`）
  - 评测样例与期望输出：`eval/cases/`
- 原始 CSV 与原始图片不落仓库。

## 边界

- 样本为**定性、自报、门店非随机样本**，结论用于**发现问题与形成假设**，不用于估计总体比例。
- 不得把某家店的个别反馈写成全市场事实；引用保留门店、时间、样本量。
- 不得用「销量差」等结果变量反推单一原因，除非有直接证据支持。
