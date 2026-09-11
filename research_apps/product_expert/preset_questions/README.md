# preset_questions/ — 预设问题编码

本目录定义 **Preset Question Coding（预设问题抽取与编码统计）**。

它与 `workflow/issue_discovery.md` 的 **Open Discovery（开放问题发现）** 是两种不同的研究方法：

```text
原始自由文本
    │
    ├───────────────────┬───────────────────┐
    ▼                   ▼
Preset Coding          Open Discovery
预设问题编码            开放问题发现
    │                   │
问题事先已知            问题事先未知
LLM = 编码器            LLM = 发现器
固定 taxonomy 抽取      Evidence → Issue
确定性计数              → Pattern → Convergence
    │                   │
    ▼                   ▼
结构化统计图表          问题详情
```

- **Preset Coding**：问题在抽取前已定义，LLM 只把原文映射到固定 `question_code`；计数由
  `scripts/derive_preset_stats.py` 确定性聚合。
- **Open Discovery**：不预设问题，由模型从原始文本发现新问题。

两条链路的结果**不得互相替代，也不得混加**。

## 文件

- `taxonomy.json`：预设问题与受控 code（含 `taxonomy_version`）。
- `../schemas/preset_coding.schema.json`：编码条目结构。
- `../runs/<run_id>/preset_coding.json`：某次 run 的编码结果。
- `../runs/<run_id>/preset_stats.json`：由 `derive_preset_stats.py` 派生的计数。

## 编码纪律

- 每条编码必须保留 `source_ref`（record_index + source_field）与逐字 `quote`。
- 只为**明确表达**的内容编码；无法确定的进入 `unclassified`/不编码，不强行归类。
- L6 与 LS6 必须分开统计；非 L6/LS6 的具体车型归入对应 model（如 LS8/LS9）。
- 原文只到门店层级、未指向具体车型的（门店客流、无试驾车、门店价格口径等）记为 `STORE`（全店 / 未区分车型），**不要**塞进 `OTHER`。`OTHER` 仅指其他具体车型。
- 竞品名称做 canonical 归一，但保留原始名称。
- 「下单阻碍」只统计明确表达，不从客流、销量或主观印象反推。
- 计数只由脚本聚合；`preset_coding.json` 中不写任何统计数字。

## 与 Open Discovery 的边界

Preset Coding 回答：“预设问题在样本中各出现了多少次？”

Open Discovery 回答：“原始文本里还发现了哪些事先没有预设的问题？”

二者合在一起：既不丢失业务已知指标，也不限制模型发现未知问题。

## 当前数据说明（run_001）

当前源表只有 10 列，不含独立的「客流高峰 / 展车 / 试驾车 / 客户关心主题 / 满意点 / 竞品 /
下单核心原因 / 不满意主题」字段。因此：

- `store_ops` / `availability` / `customer_concern` / `positive_feedback` /
  `competitor_attention` / `purchase_barrier` 均为 `coded_from_text`，从自由文本抽取；
- `dissatisfaction_theme` 暂缓启用；
- 任何未在文本中明确出现的问题，报告中显示为 **unavailable（未记录）**，不编造。
