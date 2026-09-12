# Product Expert — 产品专家门店支持研究

Research Application（第 4 个成员）。研究对象：**L6 M2 / LS6 M3 产品专家门店支持信息收集**，
即一线门店产品专家在支持期间记录的车型体验弱点、试驾反馈、门店销售与整体印象。

> 当前阶段：**双研究方法 + V0.2 架构**。数据源于 2026-09-12 切换为『产品专家支持每日反馈』
> 问卷（`run_002`）：前段选择题由 `scripts/derive_survey_stats.py` 确定性解析，后段自由文本走
> Open Discovery。`run_001`（文本编码期）保留归档。两条链路互不替代：
> **A. 业务主题扫描** 与 **B. 开放问题发现（Open Discovery）**。
> 首次 run（run_001）产出 83 条编码 / 55 evidence / 30 issue / 15 pattern / 15 convergence / 12 finding；
> run_002 产出 289 条结构化编码 / 30 evidence / 13 issue / 8 pattern / 8 convergence / 6 finding。
> 确定性 engine / gate / artifacts 仍按需演进。

## 两种研究方法

```text
原始数据
    │
    ├───────────────────┬───────────────────┐
    ▼                   ▼
① 业务主题扫描         ② 开放问题发现
Preset Coding /         Open Discovery
Survey Direct-Read
    │                   │
问题事先已知            问题事先未知
LLM = 编码器 (v0.1)     LLM = 发现器
/ 直读问卷列 (v0.2)      Evidence → Issue
确定性计数              → Pattern → Convergence
    │                   │
    ▼                   ▼
结构化统计图表          问题详情
```

- **A. 业务主题扫描**：问题定义在 `preset_questions/taxonomy.json`。
  - v0.1（文本编码期）：LLM 把自由文本映射到固定 `question_code`，计数由
    `scripts/derive_preset_stats.py` 确定性聚合，产出 `preset_coding.json` / `preset_stats.json`。
  - v0.2（问卷直读期）：问卷自带选择题，`scripts/derive_survey_stats.py` 直读列、展开多选、按
    `daily_feedback_mapping.json` 映射 code 并计数，产出 `survey_stats.json`，**不经 LLM**。
  - 规则见 `preset_questions/README.md`。
- **B. Open Discovery**：不预设问题，由模型从自由文本发现；产出 `evidence / issues / patterns /
  convergence / findings`。规则见 `workflow/issue_discovery.md` 与 `workflow/convergence.md`。

两条链路的结果**不得互相替代或混加**。业务报告 `reports/` 分开呈现 A 与 B。

## 数据来源

原始数据位于**仓库外**，只读引用，**不复制、不提交进仓库**（遵循根 `AGENTS.md` 数据边界）。

当前（v0.2，run_002）：

```text
/Users/zihao_/Documents/coding/dataset/original/L6 M2_LS6 M3 产品专家门店支持信息收集汇总_产品专家支持每日反馈_收集结果.csv
```

历史（v0.1，run_001；原文件已不在原路径，仅存于 run 产物）：

```text
/Users/zihao_/Documents/coding/dataset/original/L6 M2_LS6 M3 产品专家门店支持信息收集汇总_数据表_表格.csv
```

## 数据概况

### v0.2 每日反馈问卷（run_002）

| 项目 | 内容 |
| --- | --- |
| 文件格式 | CSV（UTF-8-BOM，字段内嵌换行） |
| 有效记录 | 12 条（一位专家一天一条提交） |
| 列数 | 40 |
| 时间范围 | `2026/09/11` – `2026/09/12` |
| 覆盖城市 | 贵阳、遵义、重庆、重庆万州 |
| 覆盖门店 | 10 家（含快闪/慢闪/交付中心/商超店） |
| 产品专家 | 11 位 |
| 结构 | 前段约 30 列为选择题（单选/多选 + 「其他-补充内容」），最后 4 列为自由文本 |

### v0.1 汇总表（run_001，归档）

| 项目 | 内容 |
| --- | --- |
| 有效记录 | 9 条（原始 12 行，含 3 行空行） |
| 列数 | 10（全部自由文本） |
| 时间范围 | `08/29` – `09/13` |

## 字段清单（v0.2）

| 字段组 | 字段 | 说明 |
| --- | --- | --- |
| 元数据 | 自动编号、提交人、提交时间、产品专家姓名、支援城市、支援门店 | 每次提交一行 |
| 展车/试驾 | 门店展车有哪些、门店试驾车有哪些（+ 其他补充） | 多选车型列表 → availability 确定性推导 |
| 客流 | 今日门店客流（组）、客流相比往常如何、客流高峰时段、关注LS6的客户占比 | store_ops，确定性直读 |
| LS6 主题 | 客户关心的主题、最不满意的主题、满意的产品点、关心的竞品、影响下单的核心原因（均含其他补充） | customer_concern / dissatisfaction_theme / positive_feedback / competitor_attention / purchase_barrier |
| L6 主题 | 客户关心的主题、最不满意的主题、感兴趣的产品点、关心的竞品、影响下单的核心原因（均含其他补充） | 同上（model=L6） |
| 自由文本 | LS6/L6/LS8-LS9 产品体验相关问题、今日产品专家门店支持最大的感想、关于LS6的竞品用户特别想说的 | Open Discovery 输入 |
| 附件 | 配图 | 本表未采集 |

> v0.1 的 10 个自由文本字段（L6/LS6 体验弱点、各车型试驾反馈、LS8/LS9 建议、门店销售、门店印象、配图）
> 映射见 `workflow/issue_discovery.md`。

## 研究管线

把非结构化门店反馈，经五级抽象变为可追溯结论。每一级都可回指上一级，最终回到原始表某行某列：

```text
原始 CSV
  │ 抽取
  ▼
Evidence    EV-####    ← schemas/evidence.schema.json
  │ 归并（同功能/同现象）
  ▼
Issue       ISS-####   ← schemas/issue.schema.json    ← issue_review 门禁
  │ 聚类（共享功能/维度/对标）
  ▼
Pattern     PAT-####   ← schemas/pattern.schema.json   ← issue_review 门禁
  │                    语义对象：pattern_key + 假设，不含统计
  │ 收敛（从 evidence 确定性派生）
  ▼
Convergence CONV-####  ← schemas/convergence.schema.json
  │                    Attribution + Counts + recurrence + evidence_strength
  │ 上升（业务含义 + 建议）
  ▼
Finding     FND-####   ← schemas/finding.schema.json
```

核心边界：

- **Pattern = 语义对象**；**Convergence = 统计与来源派生**。统计只有一个来源，避免双份事实漂移。
- **pattern_key = 跨 run 稳定语义身份**（`patterns/pattern_keys.json`），用于 Temporal Comparison；
  `pattern_id` / `convergence_id` 只是本次 run 的实例 / 快照 ID。
- **Attribution 固定三维**：产品专家 / 城市+门店 / 支持时间。更复杂统计建立在这三维之上。

- 发现规则：`workflow/issue_discovery.md`
- 统计收敛：`workflow/convergence.md`
- 评审门禁：`workflow/issue_review.md`
- 语义主键：`patterns/pattern_keys.json`
- 派生脚本：`scripts/derive_convergence.py`
- 评测样例：`eval/cases/`

## 目录结构

```text
product_expert/
├── README.md
├── preset_questions/
│   ├── README.md
│   ├── taxonomy.json              预设问题与受控 code（v0.2，含问卷直读）
│   ├── taxonomy_v0.1.json         v0.1 文本编码期 taxonomy（归档，可复现 run_001）
│   └── daily_feedback_mapping.json 问卷列/选项 → code 确定性映射
├── workflow/
│   ├── issue_discovery.md      发现流程（evidence → issue → pattern → convergence → finding）
│   ├── convergence.md          统计收敛（Attribution / Counts / recurrence / Temporal）
│   └── issue_review.md         评审门禁（去重 / 证据充分性 / 严重度 / 伪因果）
├── schemas/
│   ├── evidence.schema.json    最小可追溯观察单元
│   ├── issue.schema.json       问题归并单元
│   ├── pattern.schema.json     语义模式对象（含 pattern_key，不含统计）
│   ├── convergence.schema.json 统计快照（Attribution + Counts + Temporal）
│   ├── pattern_keys.schema.json 跨 run 语义主键注册表结构
│   ├── preset_coding.schema.json 预设问题编码条目（v0.1）
│   ├── survey_stats.schema.json 结构化问卷确定性统计（v0.2）
│   ├── daily_feedback_mapping.schema.json 问卷映射契约（v0.2）
│   └── finding.schema.json     面向业务的结论（引用 pattern + convergence）
├── patterns/
│   ├── README.md
│   └── pattern_keys.json       跨 run 语义主键注册表
├── scripts/
│   ├── derive_survey_stats.py  从日报问卷确定性派生 survey_stats.json（v0.2，无 LLM）
│   ├── derive_preset_stats.py  从 preset_coding.json 确定性聚合 preset_stats.json（v0.1）
│   ├── derive_convergence.py   从 run 目录确定性派生 convergence.json
│   └── build_report.py         生成 Field Intelligence Report（md + html）
├── eval/
│   ├── README.md
│   └── cases/
├── reports/
│   ├── README.md
│   ├── run_001/                v0.1 报告（归档）
│   └── run_002/                v0.2 报告（当前）
└── runs/
    ├── README.md
    ├── run_001/                文本编码期基线（归档）
    └── run_002/                每日反馈问卷期
        ├── run.json            运行元数据（dataset / record_count / taxonomy_version）
        ├── survey_stats.json   289 条结构化编码（确定性统计）
        ├── evidence.jsonl      30 条最小可追溯观察
        ├── issues.json         13 个问题
        ├── patterns.json       8 个语义模式
        ├── convergence.json    8 个统计快照
        └── findings.json       6 条结论
```

## 研究性质与边界

- **定性、自报、门店样本**：内容为产品专家主观记录，非结构化指标、非随机抽样。
- 不可将个别门店反馈直接外推为总体结论；引用需保留门店与时间上下文。
- v0.2 问卷的「最后 4 个文本题」中，当前导出仅 `今日产品专家门店支持最大的感想` 有量，
  另 3 个 `产品体验相关问题` 近乎为空；仍保留通道，待数据积累。
- v0.2 availability 只采集「有什么车」，不区分无展车/未到店/未开放，故该语义被合并。

## 后续结构（按需扩展，尚未创建）

当前已有 discovery / review / convergence 规则、schema、语义主键注册表、确定性派生脚本
（`derive_survey_stats.py` / `derive_preset_stats.py` / `derive_convergence.py`）、评测样例与两次 run 产物。
后续按需补建：

- 抽取 / 校验 / 评测执行（`scripts/` 已含确定性派生，可继续补 schema 校验与 CI）；
- `data/`（跨 run 的 canonical 结构化产物，与 `runs/` 快照区分）；
- 跨期 comparison（`run_001` 与 `run_002` 口径不同，暂不做 Temporal Comparison）。

跨应用复用一律沉淀到既有共享层（业务语义 → `shared/`，领域原语 → `capabilities/`，
日常分析 → `mashang_workspace/`），不在本层新建隐形公共底座。

---

_Product Expert · 用数据、AI 和一点点常识，研究复杂世界。_
