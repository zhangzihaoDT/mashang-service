# Convergence — 统计收敛与时间比较

本文件定义 **Product Expert V0.2** 的收敛层规则：把语义对象 Pattern 派生为可复核的
统计快照 Convergence，并在此基础上做跨 run 的 Temporal Comparison。

```text
Evidence → Issue → Pattern
                    │  semantic object
                    ▼
               Convergence
               ├─ Attribution           产品专家 / 城市+门店 / 支持时间
               ├─ Counts                 evidence / issue / expert / store / period / series
               └─ Temporal Comparison     跨 run 变化
                    │
                    ▼
                  Finding                 只引用 Pattern + Convergence
```

## 核心原则

1. **单一事实来源**：所有数量、来源归属与复现层级只存在于 Convergence。
   Pattern 是纯语义对象，Finding 不复制统计，`run.md` 只引用 Convergence 结果。
2. **全部确定性派生**：Convergence 由 `pattern → issue_ids → evidence_ids → evidence.source_ref`
   计算得到，不允许人工填写或 LLM 再判断。
3. **Attribution 固定三维**：产品专家、城市+门店、支持时间。更复杂的统计只能建立在这三维之上。
4. **不跳跃**：任何统计都必须能回到 evidence，再回到原始记录。

## 输入

- 本次 run 的 `patterns.json`（含 `pattern_key` 与 `issue_ids`）
- 本次 run 的 `issues.json`（含 `evidence_ids`）
- 本次 run 的 `evidence.jsonl`（含 `source_ref`）
- `patterns/pattern_keys.json`（跨 run 语义主键注册表）
- 本次 run 的 `run.json`（含 `study_year`，用于时间标准化）

## 步骤

### C1 展开来源

```text
pattern.issue_ids
  → issues[].evidence_ids
  → 去重 source_evidence_ids
  → evidence[].source_ref
```

- `source_issue_ids` = pattern 的 issue，去重。
- `source_evidence_ids` = 所有 issue 的 evidence，去重。

### C2 计算 Attribution（固定三维）

全部从 `source_evidence_ids` 对应的 `source_ref` 去重：

| 维度 | 来源字段 | 派生字段 |
| --- | --- | --- |
| 产品专家 | `source_ref.expert` | `attribution.product_experts` |
| 城市+门店 | `source_ref.store` | `attribution.city_stores` |
| 支持时间 | `source_ref.support_date` | `attribution.support_periods` |

### C3 时间标准化

原始 `support_date` 是区间字符串，必须标准化后再比较。**年份只从 run manifest 读取，不从字符串猜测。**

`run.json`：

```json
{ "run_id": "run_001", "study_year": 2026 }
```

解析规则：

```text
"08/29-08/30" → start 08/29, end 08/30, year=study_year
"09/05-09/06" → start 09/05, end 09/06
"9/10-13"     → start 9/10,  end 9/13（右端无月份时继承左端月份）
```

输出：

```json
{ "raw": "9/10-13", "start_date": "2026-09-10", "end_date": "2026-09-13" }
```

边界：当前规则不处理跨月区间（如 `08/29-09/02`）；遇到跨月必须显式补全年月，不得猜测。

### C4 计算 Counts

| 字段 | 规则 |
| --- | --- |
| `evidence_count` | `len(source_evidence_ids)` |
| `issue_count` | `len(source_issue_ids)` |
| `product_expert_count` | `len(attribution.product_experts)` |
| `city_store_count` | `len(attribution.city_stores)` |
| `support_period_count` | `len(attribution.support_periods)` |
| `series_count` | 该 pattern 展开 evidence 的 `series` 去重数 |

派生布尔：

```text
cross_store  = city_store_count ≥ 2
cross_series = series_count ≥ 2
```

### C5 派生 recurrence（冻结规则 V0.2）

```text
isolated  = city_store_count = 1
repeated  = city_store_count ≥ 2 且不满足 systemic
systemic  = city_store_count ≥ 3 且 (cross_series 或 support_period_count ≥ 2)
```

口径要点：

- 门店以**独立城市+门店**去重，不以记录条数计。
- `systemic` 必须在覆盖 ≥3 家门店之外，另有跨车型或跨支持时间区间的证据。
- 阈值可在后续版本校准，但任何校准都必须写进本文件并同步 `convergence.schema.json`。

### C6 派生 evidence_strength（冻结映射 V0.2）

```text
isolated → weak
repeated → moderate
systemic → strong
```

`evidence_strength` 只由 `recurrence` 映射，不再由 LLM 二次判断；Pattern 的 `confidence`
是研究者对语义机制的置信判断，两者不得互相覆盖。

### C7 Temporal Comparison

第一个 wave（只有一次 run）时：

```json
{ "status": "baseline_only" }
```

出现新 wave（新 run）后，比较同一 `pattern_key` 的 Convergence：

| 比较项 | 说明 |
| --- | --- |
| `counts` | evidence / issue / expert / store / period / series 增减 |
| `attribution` | 产品专家、城市+门店、支持时间的新增与消失 |
| `recurrence` | `isolated → repeated → systemic` 的升降 |
| `evidence_strength` | 由 recurrence 同步变化 |
| 主题状态 | 新出现 / 持续 / 消退（由 presence + recurrence 判断） |

对齐方式：

```text
按 pattern_key 对齐，不按 pattern_id
```

Temporal Comparison 只描述变化，**不直接下因果结论**；因果判断属于 Finding，并需显式标注边界。

## pattern_key 生命周期

```text
新 Pattern 候选
    │
    ├─ 在 patterns/pattern_keys.json 命中语义匹配 → reuse，追加 aliases
    │
    └─ 无匹配 → propose new key → 登记 first_pattern_id / first_run_id
```

- key 采用小写字母、数字、下划线，如 `cockpit_ergonomics_steering_visibility`。
- key 一经登记不得重命名；语义变化时新建 key，旧 key 标 `retired`。
- `pattern_id` 只标识本次 run 的实例，禁止用于跨 run 对齐。

## 产物

```text
runs/<run_id>/
├── run.json            运行元数据（含 study_year）
├── patterns.json       语义对象（含 pattern_key，无派生统计）
├── convergence.json    统计快照（本文件规则的输出）
└── findings.json       只引用 pattern_ids + convergence_ids

patterns/
└── pattern_keys.json   跨 run 语义主键注册表
```

## 门禁

- `convergence.json` 中每个 `source_evidence_id` 必须存在且可回到 `source_ref`。
- `pattern_key` 必须存在于 `patterns/pattern_keys.json`。
- `recurrence` / `evidence_strength` 必须与 C5 / C6 规则一致；不一致即视为派生错误。
- `run.md`、Finding、Pattern 中出现的任何数量必须能在 `convergence.json` 中找到来源。

## 派生脚本

`scripts/derive_convergence.py` 按本文件规则，从一个 run 目录确定性生成 `convergence.json`：

```bash
python research_apps/product_expert/scripts/derive_convergence.py research_apps/product_expert/runs/run_001
```

脚本只读 `patterns.json` / `issues.json` / `evidence.jsonl` / `run.json` /
`patterns/pattern_keys.json`，不修改任何语义对象。

## 边界

- Convergence 是**统计收敛**，不替代 Pattern 的语义判断，也不做因果推断。
- 样本为定性、自报、非随机门店样本，统计量用于发现问题与形成假设，不用于估计总体比例。
