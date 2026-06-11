# Result Contract — 统一执行结果协议

## 用途

定义脚本执行输出的标准 JSON 结构，供 follow-up runner、OpenCode、Feishu Bot、Mashang Runtime 等消费端复用。

## 标准结构

```json
{
  "status": "success | partial_success | error",
  "script": "scripts/lock_by_model.py",
  "command": "python scripts/lock_by_model.py --date 2026-06-10 --format json",
  "generated_at": "2026-06-11T00:00:00",

  "scope": {
    "data_source": "dataset/order_data.parquet",
    "time_window": {
      "type": "date | range | since_launch",
      "date": "2026-06-10",
      "start_date": "2026-06-10",
      "end_date": "2026-06-11"
    },
    "filters": {
      "series": "LS8",
      "model": null,
      "city": null
    },
    "metric_definition": "lock_count = COUNTD(order_number WHERE lock_time IS NOT NULL)"
  },

  "result": {
    "summary": "一句话结论",
    "metrics": {
      "total_lock_count": 185
    },
    "dimensions": [
      {
        "name": "series",
        "items": [
          {"value": "LS8", "metrics": {"lock_count": 75, "share": 0.405}}
        ]
      }
    ],
    "tables": [
      {
        "name": "lock_by_model",
        "columns": ["series", "lock_count", "share"],
        "rows": [
          {"series": "LS8", "lock_count": 75, "share": 0.405}
        ]
      }
    ]
  },

  "artifacts": {
    "csv": "outputs/tables/20260610_lock_by_model.csv",
    "json": "outputs/tables/20260610_lock_by_model.json",
    "html": null,
    "png": null
  },

  "followup_context": {
    "metric": "lock_count",
    "time_window": "yesterday",
    "date": "2026-06-10",
    "series": null,
    "model": null,
    "city": null,
    "group_by": null,
    "available_dimensions": ["series", "product_name", "license_city"],
    "top_entities": [
      {"field": "series", "value": "LS8", "metrics": {"lock_count": 75}},
      {"field": "series", "value": "LS6", "metrics": {"lock_count": 75}}
    ]
  },

  "warnings": [],
  "errors": []
}
```

## 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|:----:|------|
| `status` | string | ✅ | success / partial_success / error |
| `script` | string | ✅ | 脚本路径 |
| `command` | string | ✅ | 完整执行命令 |
| `generated_at` | string | ✅ | ISO 时间戳 |
| `scope.data_source` | string\|null | ✅ | 数据源路径 |
| `scope.time_window` | dict | ✅ | 时间窗口详情 |
| `scope.filters` | dict | ✅ | 过滤条件（含未使用的字段，值为 null） |
| `scope.metric_definition` | string\|null | ✅ | 指标口径说明 |
| `result.summary` | string | ✅ | 自然语言结论 |
| `result.metrics` | dict | ✅ | 核心数值键值对 |
| `result.dimensions` | list | recommended | 维度分组结果 |
| `result.tables` | list | optional | 完整数据表 |
| `artifacts.*` | string\|null | optional | 生成的文件路径 |
| `followup_context` | dict | ✅ | 供下一轮追问继承的信息 |
| `followup_context.top_entities` | list | recommended | 结果中 top 实体（用于“这 75 个”代指消解） |
| `warnings` | list | ✅ | 可恢复问题 |
| `errors` | list | ✅ | 不可恢复问题 |

## 已支持 Contract 的脚本

| 脚本 | status | support |
|------|--------|---------|
| `scripts/daily_lock_count.py` | success | ✅ |
| `scripts/lock_by_model.py` | success | ✅ |
| `scripts/lock_city_distribution.py` | success | ✅ |
| `scripts/cohort_forecast.py` | partial_success | ✅ |
| `scripts/assign_conversion_analysis.py` | success | ✅ |
| `scripts/attribute_penetration_report.py` | success | ✅ |
| `scripts/release_curve_analysis.py` | html only | ⏳ 保持 wrapper |

## 使用方式

```bash
# 脚本直接输出 JSON contract
python scripts/lock_by_model.py --date 2026-06-10 --format json

# 保存到文件
python scripts/lock_by_model.py --date 2026-06-10 --format json --output outputs/tables/

# followup runner 自动读取 contract（execute 模式）
python eval/run_followup_eval.py --execute --as-of-date 2026-06-11
```

## followup_context 的用途

`followup_context` 供下一轮追问继承：

- `metric` / `time_window` / `series` → 继承到下一轮 `resolved_context`
- `top_entities` → 用于解析“这 75 个”“那个 LS8”等代指
- `available_dimensions` → 提示 Agent 可用的分组维度
