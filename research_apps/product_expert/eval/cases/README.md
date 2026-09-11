# eval/cases — 评测样例

每个 case 是一份 **输入锚点 + 期望结构**，用于回归 discovery / review 规则。

## 文件格式

discovery / review 阶段：

```json
{
  "case_id": "case_001_<slug>",
  "description": "这个 case 检验什么",
  "stage": "discovery | review",
  "input_ref": {
    "dataset": "<原始 CSV 路径或登记名>",
    "record_index": 0,
    "source_field": "ls6_weakness"
  },
  "expected": {
    "evidence": [
      {
        "statement_contains": ["<关键词>"],
        "category": "<受控词表>",
        "series": ["LS6"],
        "sentiment": "negative",
        "severity_hint": "blocker"
      }
    ],
    "issues": [
      {
        "title_contains": ["<关键词>"],
        "category": "<受控词表>",
        "series": ["LS6", "LS8"],
        "affected_function": "<功能/部件>",
        "severity": "blocker",
        "business_signal": "purchase_blocker",
        "evidence_count_min": 1,
        "status_after_review": "confirmed"
      }
    ]
  },
  "metrics": [
    "evidence_recall",
    "category_match",
    "severity_match",
    "dedup_correct",
    "traceability"
  ]
}
```

convergence 阶段（统计必须与 `workflow/convergence.md` 冻结规则一致）：

```json
{
  "case_id": "case_002_<slug>",
  "description": "这个 case 检验哪条收敛规则",
  "stage": "convergence",
  "input_ref": {
    "run_id": "run_001",
    "pattern_key": "<已登记 key>",
    "pattern_id": "PAT-####"
  },
  "expected": {
    "attribution": {
      "product_experts": ["<去重专家>"],
      "city_stores": ["<去重门店>"],
      "support_period_count": 2
    },
    "counts": {
      "evidence_count": 4,
      "issue_count": 2,
      "product_expert_count": 3,
      "city_store_count": 3,
      "support_period_count": 2,
      "series_count": 2
    },
    "recurrence": "systemic",
    "evidence_strength": "strong",
    "temporal_comparison_status": "baseline_only"
  },
  "metrics": [
    "attribution_exact",
    "counts_match",
    "recurrence_match",
    "evidence_strength_match",
    "temporal_status_match"
  ]
}
```

## 约定

- `statement_contains` / `title_contains` 用关键词集合判断，不做逐字匹配。
- `input_ref` 必须指向真实存在的原始记录；期望值来自人工判定，不凭空生成。
- 命名：`case_<序号>_<slug>.json`。
- 新增 case 时，同步在 `eval/README.md` 的覆盖表登记它检验的维度。

## 现有样例

| case | stage | 检验重点 |
| --- | --- | --- |
| `case_001_steering_wheel_sightline.json` | discovery | 同段多观察拆分 + 拒购风险严重度 + 跨车系 |
| `case_002_convergence_attribution.json` | convergence | Attribution 三维派生 + counts + systemic/strong 规则 |
