# Product Expert — 产品专家门店支持研究

Research Application（第 4 个成员）。研究对象：**L6 M2 / LS6 M3 产品专家门店支持信息收集**，
即一线门店产品专家在支持期间记录的车型体验弱点、试驾反馈、门店销售与整体印象。

> 当前阶段：**双研究方法 + V0.2 架构**，首次 run 完成（`runs/run_001/`），并已产出业务报告
> （`reports/run_001/`）。同一份自由文本上运行两条互不替代的链路：
> **A. 预设问题编码（Preset Coding）** 与 **B. 开放问题发现（Open Discovery）**。
> 产出 83 条预设编码 / 55 evidence / 30 issue / 15 pattern / 15 convergence / 12 finding。
> 确定性 engine / gate / artifacts 仍按需演进。

## 两种研究方法

```text
原始自由文本
    │
    ├───────────────────┬───────────────────┐
    ▼                   ▼
① 预设问题抽取统计     ② 开放问题发现
Preset Coding          Open Discovery
    │                   │
问题事先已知            问题事先未知
LLM = 编码器            LLM = 发现器
固定 taxonomy 抽取      Evidence → Issue
确定性计数              → Pattern → Convergence
    │                   │
    ▼                   ▼
结构化统计图表          问题详情
```

- **A. Preset Coding**：问题定义在 `preset_questions/taxonomy.json`；LLM 只把原文映射到固定
  `question_code`；计数由 `scripts/derive_preset_stats.py` 确定性聚合。产出 `preset_coding.json`
  与 `preset_stats.json`。规则见 `preset_questions/README.md`。
- **B. Open Discovery**：不预设问题，由模型从原文发现；产出 `evidence / issues / patterns /
  convergence / findings`。规则见 `workflow/issue_discovery.md` 与 `workflow/convergence.md`。

两条链路的结果**不得互相替代或混加**。业务报告 `reports/` 分开呈现 A 与 B。

## 数据来源

原始数据位于**仓库外**，只读引用，**不复制、不提交进仓库**（遵循根 `AGENTS.md` 数据边界）：

```text
/Users/zihao_/Documents/coding/dataset/original/L6 M2_LS6 M3 产品专家门店支持信息收集汇总_数据表_表格.csv
```

## 数据概况

| 项目 | 内容 |
| --- | --- |
| 文件格式 | CSV（UTF-8，字段内嵌换行） |
| 有效记录 | 9 条（原始 12 行，含 3 行空行） |
| 列数 | 10 |
| 时间范围 | `08/29` – `09/13` |
| 覆盖门店 | 遵义吾悦广场、安徽亳州诚谯（交付）、阜阳商厦时代广场、金华永康万达、温州印象城MEGA、金华世贸广场 |
| 记录人 | 吴昊、郑少伟、李文涛、周正成、陈晓雪、胡然、方园园 |

## 字段清单

| 字段 | 说明 |
| --- | --- |
| 支持日期 | 门店支持时间段（如 `08/29-08/30`） |
| 产品专家 | 记录人 |
| 支持城市+门店 | 城市与门店名 |
| L6产品体验弱点 | L6 的体验弱点反馈 |
| LS6产品体验弱点 | LS6 的体验弱点反馈 |
| 各车型试驾反馈 | 试驾用户反馈 |
| LS8/LS9产品建议或销售情况 | 高阶车型建议或销售情况 |
| 门店整体销售情况（客流/试驾/锁单） | 门店经营口径 |
| 门店整体印象 | 主观整体评价 |
| 配图 | 附件图片文件名 |

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
│   └── taxonomy.json           预设问题与受控 code（版本化）
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
│   ├── preset_coding.schema.json 预设问题编码条目
│   └── finding.schema.json     面向业务的结论（引用 pattern + convergence）
├── patterns/
│   ├── README.md
│   └── pattern_keys.json       跨 run 语义主键注册表
├── scripts/
│   ├── derive_convergence.py   从 run 目录确定性派生 convergence.json
│   ├── derive_preset_stats.py  从 preset_coding.json 确定性聚合 preset_stats.json
│   └── build_report.py         生成 Field Intelligence Report（md + html）
├── eval/
│   ├── README.md
│   └── cases/
├── reports/
│   ├── README.md
│   └── run_001/                A 预设编码统计 + B 开放问题发现
└── runs/
    ├── README.md
    └── run_001/
        ├── run.json            运行元数据（含 study_year / record_count）
        ├── preset_coding.json   83 条预设问题编码（逐字 quote + source_ref）
        ├── preset_stats.json    预设问题确定性聚合结果
        ├── evidence.jsonl       55 条最小可追溯观察
        ├── issues.json          30 个问题
        ├── patterns.json        15 个语义模式
        ├── convergence.json     15 个统计快照
        ├── findings.json        12 条结论
        └── run.md               本次 run 报告
```

## 研究性质与边界

- **定性、自报、门店样本**：内容为产品专家主观记录，非结构化指标、非随机抽样。
- 不可将个别门店反馈直接外推为总体结论；引用需保留门店与时间上下文。
- 配图字段仅记录文件名，原始图片未随本仓库管理。

## 后续结构（按需扩展，尚未创建）

当前已有 discovery / review / convergence 规则、五级 schema、语义主键注册表、统计派生脚本、
评测样例与首次 run 产物。后续按需补建：

- 确定性抽取 / 校验 / 评测执行（`scripts/` 已含 `derive_convergence.py`，可继续补抽取与校验）；
- `data/`（跨 run 的 canonical 结构化产物，与 `runs/` 快照区分）；
- `reports/`（面向业务的结论交付）。

跨应用复用一律沉淀到既有共享层（业务语义 → `shared/`，领域原语 → `capabilities/`，
日常分析 → `mashang_workspace/`），不在本层新建隐形公共底座。

---

_Product Expert · 用数据、AI 和一点点常识，研究复杂世界。_
