# 多轮追问、上下文解析与脚本调度

## 核心原则

1. **时间继承**：追问省略时间窗口时，继承上一轮的时间范围
2. **指标继承**：追问省略指标时，继承上一轮的指标/口径
3. **代指消解**：识别并解析"这 N 个""刚才那个""昨天 X"等代指
4. **上下文不足时澄清**：不确定时先输出需要澄清的字段
5. **口径一致**：同一次 session 内保持口径一致，除非用户主动要求变更

## 代指消解规则

### 数量代指

```
用户: "昨天锁单数分车型"
Agent: <输出 LS8 75, CM2 62, ...>
用户: "那这 75 个锁单城市分布"
→ 继承: filters: {series: "LS8", time: 昨天}, 新维度: store_city
→ 脚本: workspace/business_scripts/lock_city_distribution.py --date 昨天 --series LS8
```

### 车型代指

```
用户: "LS8 上市以来五六座比例"
Agent: <输出 五座 72%, 六座 28%>
用户: "刚才那个车型的大电池组占比"
→ 继承: series: "LS8", filters: 电池容量=103kwh
```

### 时间代指

```
用户: "近 15 日 LS6 增程和纯电占比"
Agent: <输出>
用户: "那最近 7 天呢？"
→ 继承: 指标、口径，仅时间窗口从 15 日改为 7 日
→ 脚本: 同上，改 --start-date/--end-date
```

### 条件继承

```
用户: "LS8 上市以来分车型结构"
Agent: <输出>
用户: "只看大电池组"
→ 继承: 时间、口径，附加 filters: {product_name: 包含 Ultra 或 Pro Max}
```

## 上下文字段

多轮会话应保留以下上下文：

```json
{
  "previous": {
    "question": "昨天锁单数分车型",
    "time": {"start": "2026-06-10", "end": "2026-06-11"},
    "series": "LS8",
    "metric": "锁单量",
    "filters": [...],
    "result": {...}
  },
  "current": {
    "question": "那 75 个锁单城市分布",
    "inherited": ["time", "metric", "series_filter"]
  }
}
```

## 需继承的字段

| 字段 | 继承规则 | 示例 |
|------|----------|------|
| `time.start` / `time.end` | 追问无显式时间时继承 | 昨天 → 城市分布(仍用昨天) |
| `metric` / `analysis_intent` | 追问无显式指标时继承 | 锁单数 → 分车型(仍用锁单数) |
| `filters` | 追问追加条件而非替换 | 大电池组 → 追加 filter |
| `dimensions` | 追问切换维度 | 分车型 → 改城市分布 |
| `result` 中的关键值 | 用于消解"这 N 个" | 75个 → 上一轮维度值 |

## 追问与脚本映射

当决定调用哪个脚本时，根据继承的上下文选择：

| 追问场景 | 推荐脚本 | 参数继承 |
|----------|----------|----------|
| 改时间窗口 | 同上一轮脚本 | 传新 --start-date/--end-date |
| 加车系过滤 | 同上一轮脚本 + --series | 继承时间、指标 |
| 切换分组维度 | `lock_by_model.py` / `lock_city_distribution.py` | 继承时间、车系 |
| 城市→车型 | `lock_by_model.py` | 继承时间、车系 |
| 车型→城市 | `lock_city_distribution.py` | 继承时间、车系 |
| 加过滤条件 | 同上一轮脚本 + --model/--city | 继承时间、车系 |

## 不明确时的澄清格式

当上下文不足以确定口径时，输出以下格式：

```
你说的"XX"具体指哪个？
1. [选项A] — 说明
2. [选项B] — 说明
3. [选项C] — 说明
```

可用的选项类型：
- 指标选择（多个候选指标）
- 车型选择（LS6 vs L6 vs LS8）
- 时间窗口选择（昨天 vs 近7日 vs 本月）
- 口径选择（门店锁单率 vs 7日锁单率）

## 上下文解析器

对应 `workspace/eval/context_parser.py`。

### 支持的输出字段

| 字段 | 说明 |
|------|------|
| `metric` | 指标类型 |
| `time_window` | 时间窗口 symbolic 值 |
| `series` | 车系 |
| `model` | 具体车型 |
| `city` | 城市 |
| `group_by` | 分组维度 |
| `filters` | 过滤器列表 (additive) |
| `analysis_type` | 分析类型 |
| `baseline` | 对比基准时间窗口（「相比…均值」时出现，不覆盖主 `time_window`） |
| `limit` | TopN 限制 |
| `confidence` | 解析置信度 0.0~1.0 |

### Metric 解析规则

| 用户说 | metric |
|--------|--------|
| 锁单数/锁单量/锁单 | `lock_count` |
| 占比/结构/份额/率 | `lock_count_share` |
| 预测/cohort 预测 | `cohort_forecast` |
| 释放曲线 | `release_curve` |
| VOC/JTBD/主题分析 | `voc_theme` |
| ATP/均价/价格 | `atp_price` |

### Time Window 解析规则

| 用户说 | symbolic value |
|--------|---------------|
| 昨天/昨日 | `yesterday` |
| 近 N 天/日 | `last_{N}_days` (N=1~365) |
| 最近 N 天/日 | `last_{N}_days` |
| 本月 | `this_month` |
| 上月/上个月 | `last_month` |
| 上市以来 | `since_launch` |

### Series 解析

从文本识别: `LS8`, `LS6`, `L6`, `L7`, `LS9`, `LS7` 等。

### Group By 解析规则

| 用户说 | group_by |
|--------|----------|
| 分车型/车型结构/车型占比 | `model` |
| 分车系/车系结构 | `series` |
| 城市分布/分城市/按城市 | `city` |
| 增程和纯电/能源类型 | `energy_type` |
| 大区/区域分布 | `region` |
| 渠道分布/分渠道 | `channel` |
| JTBD/主题分布 | `jtbd_theme` |

### Filter 解析规则

| 用户说 | filter 值 |
|--------|-----------|
| 只看大电池组 | `large_battery` |
| 只看小电池组 | `small_battery` |
| 只看五座 | `seat_5` |
| 只看六座 | `seat_6` |

### 分析类型 (analysis_type) 规则

| 用户说 | analysis_type |
|--------|---------------|
| 同比/环比/对比/变化 | `compare` |
| 相比/较/对比 …(近 N 日/昨日/…)均值 | `compare` + 记录 `baseline` |
| 生成结论/日报/摘要/总结 | `summary` |
| 趋势/走势/波动 | `trend` |
| 占比/份额 | `share` |

### 对比基准 (baseline) 语义

当用户使用「相比/较/对比 …均值」表达对比基准时：

- `baseline` 记录基准时间窗口（如 `last_7_days`），**不覆盖**主 `time_window`（主窗口继续从上轮继承）
- 同时设置 `analysis_type = compare`

示例：

```
上一轮: 昨天(yesterday) LS8 城市分布 (lock_count, group_by=city)
用户:   "哪些城市相比近 7 日均值下降明显？"
  → time_window = yesterday (继承)
  → baseline    = last_7_days
  → analysis_type = compare
```


### 当前模式

- `parser_mode`: `"rule_based"`
- 置信度: 基于匹配规则数量和精确度计算
- 缺失关键字段时 confidence 减半

### Result Reference (结果引用)

parser 支持通过 `previous_result_context` 参数解析结果引用：

```
用户: "昨天锁单数分车型"  → 返回 top_entities: [{field: "series", value: "LS8", metrics: {lock_count: 75}}, ...]
用户: "这 75 个锁单城市分布"
  → 匹配 top_entities 中 lock_count=75 的实体
  → 自动继承 series=LS8
```

支持的引用模式:

| 用户说 | 解析逻辑 |
|--------|----------|
| 这 N 个 / 这 N 单 | 匹配 top_entities 中 metric_value = N 的实体 |
| 刚才那个车型 / 那个车系 | 取 top_entities[0] |
| 排名第一 | 取 top_entities[0] |

### 未来升级路径

1. 当前: rule-based parser
2. 下一阶段: hybrid (rule-based + LLM fallback)
3. 最终: LLM-first parser with deterministic validation

## 脚本调度验证

对应 `workspace/eval/run_followup_eval.py`。

### Runner 模式

本规则定义如何将"多轮追问的 expected_context"映射为"可执行的脚本 + CLI 参数"。
当前为 deterministic / rule-based 实现，不依赖 LLM。

支持两种模式:

#### Expected Context 模式 (Phase 3)
从 cases JSON 中读取 expected_context，直接生成脚本调用计划。
适用于回归验证 runner 本身的正确性。

#### Parse Text 模式 (Phase 4)
从用户自然语言文本调用 context_parser，自动解析出 context。
再基于解析结果生成脚本调用计划。
适用于验证 parser 质量。

```bash
# Expected Context 模式 (默认)
python workspace/eval/run_followup_eval.py

# Parse Text 模式
python workspace/eval/run_followup_eval.py --parse-text
python workspace/eval/run_followup_eval.py --parse-text --format json --output outputs/tables/parse_result.json
```

### Context → Script 映射

| expected_context | 推荐脚本 |
|-----------------|----------|
| `metric=lock_count` + `group_by=model/series/energy_type` | `workspace/business_scripts/lock_by_model.py` |
| `metric=lock_count` + `group_by=city` | `workspace/business_scripts/lock_city_distribution.py` |
| `metric=lock_count` (无分组) | `workspace/business_scripts/daily_lock_count.py` |
| `metric=lock_count_share/share` + 任何分组 | `workspace/business_scripts/lock_by_model.py` |
| `metric=reev_share_trend/share_trend` | `workspace/business_scripts/lock_by_model.py` |
| `metric=lock_forecast/forecast_lock_count/cohort_forecast` | `workspace/research_scripts/cohort_forecast.py` |
| `metric=release_curve/lock_release_curve` | `workspace/research_scripts/release_curve_analysis.py` |
| `metric=voc_theme/jtbd_theme` | `workspace/utility_scripts/voc_theme_analysis.py` |

Runner 的 Expected Context 模式沿用上文继承规则。显式字段覆盖上轮值，`filter` 与 `filter_ref` 追加到现有过滤条件。

### 时间窗口解析

| symbolic | 解析规则 |
|----------|----------|
| `yesterday` | `as_of_date - 1` → `--date` |
| `last_7_days` | `[as_of-7, as_of)` → `--start-date / --end-date` |
| `last_15_days` | `[as_of-15, as_of)` |
| `last_30_days` | `[as_of-30, as_of)` |
| `this_month` | `[month_start, as_of)` |
| `last_month` | `[prev_month_start, prev_month_end)` |
| `since_launch` | 优先读取 `business_definition.json` 中的上市日 → `--start-date` |

### 输出格式

每个 turn 输出：

```json
{
  "turn_index": 0,
  "user": "昨天锁单数分车型",
  "resolved_context": { "metric": "lock_count", "time_window": "yesterday", "group_by": "series" },
  "inherited_context": {},
  "overridden_context": {},
  "missing_context": {},
  "recommended_script": "workspace/business_scripts/lock_by_model.py",
  "recommended_args": ["--date", "2026-06-10", "--format", "terminal"],
  "recommended_command": "python workspace/business_scripts/lock_by_model.py --date 2026-06-10 --format terminal",
  "can_execute": true
}
```

### Dry-run vs Execute

- **Dry-run** (默认): 只生成 recommended_command，不执行
- **Execute** (`--execute`): 用 subprocess 实际执行 recommended_command，捕获 stdout/stderr/return_code
- 单个 case 失败不中断全局
- Execute 模式下限制输出规模 (stdout ≤ 2000 chars)

### 当前限制

1. 不接入 LLM，不处理真正的自然语言理解
2. symbolic time_window 的"今天"使用 `--as-of-date` 参数控制
3. Runner 仍存在历史上市日期回退逻辑。业务分析应以 `shared/schema/business_definition.json` 的 `time_periods.{series}.end` 为准。
4. filter 的语义理解（如"大电池组"→具体 SQL）不在本阶段处理
