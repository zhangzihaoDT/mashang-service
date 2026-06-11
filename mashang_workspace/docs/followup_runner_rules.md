# Follow-up Runner Rules — 追问 → 脚本调度规则

> 对应: eval/run_followup_eval.py
> Context Parser: eval/context_parser.py (Phase 4)

## 用途

本规则定义如何将"多轮追问的 expected_context"映射为"可执行的脚本 + CLI 参数"。
当前为 deterministic / rule-based 实现，不依赖 LLM。

支持两种模式:

### Expected Context 模式 (Phase 3)
从 cases JSON 中读取 expected_context，直接生成脚本调用计划。
适用于回归验证 runner 本身的正确性。

### Parse Text 模式 (Phase 4)
从用户自然语言文本调用 context_parser，自动解析出 context。
再基于解析结果生成脚本调用计划。
适用于验证 parser 质量。

```bash
# Expected Context 模式 (默认)
python eval/run_followup_eval.py

# Parse Text 模式
python eval/run_followup_eval.py --parse-text
python eval/run_followup_eval.py --parse-text --format json --output outputs/tables/parse_result.json
```

## Context → Script 映射

| expected_context | 推荐脚本 |
|-----------------|----------|
| `metric=lock_count` + `group_by=model/series/energy_type` | `scripts/lock_by_model.py` |
| `metric=lock_count` + `group_by=city` | `scripts/lock_city_distribution.py` |
| `metric=lock_count` (无分组) | `scripts/daily_lock_count.py` |
| `metric=lock_count_share/share` + 任何分组 | `scripts/lock_by_model.py` |
| `metric=reev_share_trend/share_trend` | `scripts/lock_by_model.py` |
| `metric=lock_forecast/forecast_lock_count/cohort_forecast` | `scripts/cohort_forecast.py` |
| `metric=release_curve/lock_release_curve` | `scripts/release_curve_analysis.py` |
| `metric=voc_theme/jtbd_theme` | `scripts/voc_theme_analysis.py` |

## 上下文继承规则 (多轮)

1. **第一轮**：建立初始 context，所有字段来自 expected_context
2. **第二轮起**：
   - 如果当前轮 expected_context 中存在某字段 → 使用当前值（显式覆盖）
   - 如果当前轮 expected_context 中缺少某字段 → 继承上一轮
   - `filter` / `filter_ref` → **追加**到现有 filter 列表（不覆盖）
   - `time_window` → 显式出现时覆盖上一轮
   - `metric` / `series` / `model` / `city` / `group_by` / `analysis_type` → 显式出现时覆盖

### 继承示例

```
Turn 0: {metric: lock_count_share, time_window: last_15_days, series: LS6, group_by: energy_type}
Turn 1: {metric: lock_count_share, time_window: last_7_days, series: LS6, group_by: energy_type}
  → 继承: metric, series, group_by
  → 覆盖: time_window (last_15_days → last_7_days)
```

## 时间窗口解析

| symbolic | 解析规则 |
|----------|----------|
| `yesterday` | `as_of_date - 1` → `--date` |
| `last_7_days` | `[as_of-7, as_of)` → `--start-date / --end-date` |
| `last_15_days` | `[as_of-15, as_of)` |
| `last_30_days` | `[as_of-30, as_of)` |
| `this_month` | `[month_start, as_of)` |
| `last_month` | `[prev_month_start, prev_month_end)` |
| `since_launch` | 从 `business_definition.json` 或 VEHICLE_LAUNCH_DATES 取上市日 → `--start-date` |

## 输出格式

每个 turn 输出：

```json
{
  "turn_index": 0,
  "user": "昨天锁单数分车型",
  "resolved_context": { "metric": "lock_count", "time_window": "yesterday", "group_by": "series" },
  "inherited_context": {},
  "overridden_context": {},
  "missing_context": {},
  "recommended_script": "scripts/lock_by_model.py",
  "recommended_args": ["--date", "2026-06-10", "--format", "terminal"],
  "recommended_command": "python scripts/lock_by_model.py --date 2026-06-10 --format terminal",
  "can_execute": true
}
```

## Dry-run vs Execute

- **Dry-run** (默认): 只生成 recommended_command，不执行
- **Execute** (`--execute`): 用 subprocess 实际执行 recommended_command，捕获 stdout/stderr/return_code
- 单个 case 失败不中断全局
- Execute 模式下限制输出规模 (stdout ≤ 2000 chars)

## 当前限制

1. 不接入 LLM，不处理真正的自然语言理解
2. symbolic time_window 的"今天"使用 `--as-of-date` 参数控制
3. `since_launch` 依赖 `schema/business_definition.json` 或硬编码的上市日期
4. filter 的语义理解（如"大电池组"→具体 SQL）不在本阶段处理
