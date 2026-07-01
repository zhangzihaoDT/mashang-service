# Validators — AI 返回结果校验与归一化

## 定位

Validators 是 Auto Launch workflow 中的**质量保证层**，负责：

1. **validate_ai_response**: 检查 AI 输出 JSON 的结构完整性
2. **normalize_ai_response**: 将 AI 输出 JSON 归一化为统一结构的 normalized JSON

## 文件结构

```
validators/
├── README.md                        # 本文件
├── validate_ai_response.py          # 校验脚本
└── normalize_ai_response.py         # 归一化脚本

examples/
├── ai_outputs/                      # AI 输出样本（仅用于结构测试）
│   ├── daily_radar_sample.json      # event 类型样本
│   └── event_48h_sample.json        # brief 类型样本
└── normalized/                      # 归一化后的输出示例
├── daily_radar_sample.normalized.json
└── event_48h_sample.normalized.json
```

## validate_ai_response.py

### 职责

* 输入：AI 输出 JSON 文件路径
* 自动检测文档类型（event / brief）
* 检查必填字段是否存在且非空
* 检查 source_items 是否存在且非空
* 检查 confirmed_facts / inferences / unconfirmed_claims 是否为数组
* 检查 confidence_level 是否为合法值（high / medium / low / unknown）
* 检查 missing_evidence 或 unresolved_questions 是否存在
* 输出人类可读报告
* 失败时返回非 0 exit code

### 用法

```bash
python validators/validate_ai_response.py path/to/ai_output.json
```

### 输出示例

```
[auto_launch validate] OK
  type: brief
  schema: auto_launch_brief.schema.json
  source_items: 5
  confirmed_facts: 4
  inferences: 2
  unconfirmed_claims: 2
  missing_evidence: 3
  confidence_level: medium
```

## normalize_ai_response.py

### 职责

* 输入：AI 输出 JSON 文件路径 + `--output` 输出路径
* 调用 validate 逻辑进行基础校验
* 输出统一结构的 normalized JSON

### 统一输出结构

```json
{
  "record_type": "event | brief",
  "record_key": "...",
  "our_model": "...",
  "event_model": "...",
  "event_brand": "...",
  "event_type": "...",
  "battle_field": "...",
  "time_window": {},
  "confidence_level": "high | medium | low | unknown",
  "source_items": [],
  "confirmed_facts": [],
  "inferences": [],
  "unconfirmed_claims": [],
  "missing_evidence": [],
  "followup_recommendation": {},
  "raw": {}
}
```

### 约束

* 不做业务推断，只做字段归一化
* 不把 unconfirmed_claims 混入 confirmed_facts
* 不自动提升 confidence_level
* 不访问网络
* 不调用 LLM

### 用法

```bash
python validators/normalize_ai_response.py path/to/ai_output.json --output path/to/normalized.json
```

## AI 输出 JSON 的最小要求

### event 类型

至少包含：
- event_id
- event（含 brand / model / event_type / event_date）
- battle_field
- source_items（非空数组）
- confirmed_facts（数组）
- inferences（数组）
- unconfirmed_claims（数组）
- confidence_level（high/medium/low/unknown）
- missing_evidence（数组）

### brief 类型

至少包含：
- brief_id
- our_model
- event_model
- battle_field
- executive_summary
- source_items（非空数组）
- confirmed_facts（数组）
- inferences（数组）
- unconfirmed_claims（数组）
- missing_evidence（数组）
- confidence_level（high/medium/low/unknown）
- followup_recommendation

## 样本数据说明

`examples/ai_outputs/` 和 `examples/normalized/` 下的 JSON 文件**仅用于结构测试**，不代表真实事实。

- 来源 URL 均为虚构（`https://example.com/`）
- 品牌、车型、价格等数据为示意性内容
- 不反映任何真实市场情报

## Phase 2 结构测试覆盖

`tests/promptbuilders/test_auto_launch_prompt_workflow.py` 覆盖 Prompt 模板结构。

## Phase 3 validate + normalize 测试覆盖

`tests/promptbuilders/test_auto_launch_validate_normalize.py` 覆盖：

| 测试类别 | 测试数 | 说明 |
|----------|--------|------|
| A. validate 成功 | 2 | daily_radar / event_48h 通过 |
| B. validate 失败 | 3 | 缺 source_items / 缺 confidence_level / 缺 confirmed_facts |
| C. normalize 成功 | 5 | record_type / record_key / raw / 分类不混淆 |
| D. CLI 可用 | 2 | validate 无参数报错 / normalize --output 必填 |
| E. Phase 2 兼容 | 1 | 不影响现有结构测试 |

## 后续 Phase 4

将 normalized JSON 接入 mashang-service 的报告或数据沉淀，包含：
- 批量 validate / normalize runner
- 入库 schema 适配
- 报告沉淀与历史回溯
