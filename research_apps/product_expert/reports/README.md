# reports/ — Field Intelligence Report

打开本目录，看到的就是 Product Expert 从一线文字里发现了什么。

视觉遵循 `.opencode/skills/diagram-design` 的 editorial 设计系统：**白底** `#ffffff` + 浅中性灰卡片、
jet-black 文字、blue-slate 次级、**atomic-tangerine 焦点**（`#eb6c36`，1–2 处），
thin rules、无阴影、无品牌吉祥物；字体使用本机 `Noto Sans CJK SC`，不引入远程字体。
颜色 token 集中在 `build_report.py` 的 `:root`，可整体换肤。

报告对同一份自由文本使用 **两种不同的研究方法**，并严格分开呈现：

```text
原始自由文本
    │
    ├───────────────────┬───────────────────┐
    ▼                   ▼
A. 预设问题编码        B. 开放问题发现
Preset Coding          Open Discovery
    │                   │
问题事先已知            问题事先未知
LLM = 编码器            LLM = 发现器
固定 taxonomy 抽取      Evidence → Issue
确定性计数              → Pattern → Convergence
    │                   │
    ▼                   ▼
结构化统计图表          问题详情 + 一线原文
```

## 结构

```text
reports/
└── run_001/
    ├── product_expert_report.md     可审阅、可 diff 的源报告
    └── product_expert_report.html   面向阅读的自包含 HTML
```

## 生成命令

```bash
python research_apps/product_expert/scripts/derive_preset_stats.py research_apps/product_expert/runs/run_001
python research_apps/product_expert/scripts/derive_convergence.py research_apps/product_expert/runs/run_001
python research_apps/product_expert/scripts/build_report.py research_apps/product_expert/runs/run_001
```

## 报告结构

```text
01 本期概览
   数据规模行 + 研究观察（可选，≤3 条；仅 confirmed 且全部 systemic）

02 业务主题扫描
   A1 门店支持概况
   A2 现场客流情况
   A3 展车 / 试驾车缺失报备（按车型的展车/试驾车覆盖率统计 + 折叠的缺失门店×车型明细；❌ 标缺失）
   A4 客户关注主题（LS6 / L6 分开，记录覆盖率）
   A5 正向产品反馈（LS6 / L6 分开，记录覆盖率）
   A6 竞品关注（LS6 / L6 分开，记录覆盖率）
   A7 下单阻碍（LS6 / L6 分开，记录覆盖率）
   A8 不满意主题（LS6 / L6 分开，记录覆盖率）

> A4–A8 为**记录覆盖率**：分子是命中该主题的去重 `record_index` 数，分母是门店记录数（run 的记录数）。
> 同一记录可命中多个主题，故各行分数不可相加；编码条目数（mentions）作为附注保留。

03 一线问题发现
   指标卡：N 条门店记录 → 识别出 M 个开放问题
   B1–B3 问题详情（LLM 提炼 + 一线上报原文）：
   问题 Top 3 展开，其余问题折叠；每张卡一线上报只显示前 3 条，其余折叠
   Baseline only
   Runtime Trace（折叠）
```

## A 与 B 的数据边界

| 部分 | 内容 | 来源 |
| --- | --- | --- |
| A | 预设问题/问卷计数 | v0.2 `survey_stats.json`（`derive_survey_stats.py` 直读问卷）；v0.1 `preset_stats.json`（由 `preset_coding.json` 确定性聚合） |
| A | 编码原文 | v0.2 问卷选项/补充原文；v0.1 `preset_coding.json` 的 `quote` |
| B | 问题语义、LLM 提炼 | `patterns.json` |
| B | 提及次数、来源、复现层级 | `convergence.json` |
| B | 一线原文 | `evidence.jsonl` |
| — | 研究观察（≤3） | `findings.json` |

- A **不生成任何文字**：只渲染脚本聚合出的计数与原文引用。
- 两条链路的数量**不得混加，也不得互相替代**。
- A3 的车型维度区分 `L6/LS6/LS8/LS9` 与 `全店`（`STORE`，原文只到门店层级）；
  `其他车型` 仅指其他具体车型，门店级事实不得记成 `OTHER`。

### 原文纪律（硬约束）

- A 的编码 `quote`、B 的「一线上报」均逐字取自源数据；报告**不生成、不改写、不润色**任何原话。
- 若某条 evidence 没有 `quote`，只能回退其已存 `statement` 并标注「归一化陈述，非原文」。
- 禁止从 Pattern、Finding、Issue 反向拼接合成看似真实的话。
- `PAT-*` / `pattern_key` / `CONV-*` / 证据强度 / 复现层级属于 **Runtime Trace**，折叠在末尾，不叫「原始证据」。

## 当前数据边界（run_001）

源表只有 10 列，不含独立的「客流高峰 / 展车 / 试驾车 / 客户关心主题 / 满意点 / 竞品 /
下单核心原因」字段。因此 A 部分全部为 `coded_from_text`（从自由文本抽取），并保留 `source_ref`。
未在文本中明确出现的内容显示为 **unavailable（未记录）**，不编造。

这份报告的价值不是替人说话，而是让人看到 AI 如何从真实的一线文字中编码与发现问题。
