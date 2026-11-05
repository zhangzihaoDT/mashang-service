# Context Parser Rules — 自然语言 → 结构化 Context 解析规则

> 对应: eval/context_parser.py

## 用途

将用户自然语言（中文）解析为结构化 context，供 Follow-up Runner 生成脚本调用计划。
本阶段为 rule-based 实现（正则匹配），不依赖 LLM。

## Parser 与 Runner 的关系

```
用户自然语言
    ↓
eval/context_parser.py     ← 解析文本为结构化 context
    ↓ (parsed_context + inheritance)
eval/run_followup_eval.py  ← 生成推荐脚本 + CLI 参数
    ↓ (recommended_command)
dry-run / execute
```

## 支持的输出字段

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

## Metric 解析规则

| 用户说 | metric |
|--------|--------|
| 锁单数/锁单量/锁单 | `lock_count` |
| 占比/结构/份额/率 | `lock_count_share` |
| 预测/cohort 预测 | `cohort_forecast` |
| 释放曲线 | `release_curve` |
| VOC/JTBD/主题分析 | `voc_theme` |
| ATP/均价/价格 | `atp_price` |

## Time Window 解析规则

| 用户说 | symbolic value |
|--------|---------------|
| 昨天/昨日 | `yesterday` |
| 近 N 天/日 | `last_{N}_days` (N=1~365) |
| 最近 N 天/日 | `last_{N}_days` |
| 本月 | `this_month` |
| 上月/上个月 | `last_month` |
| 上市以来 | `since_launch` |

## Series 解析

从文本识别: `LS8`, `LS6`, `L6`, `L7`, `LS9`, `LS7` 等。

## Group By 解析规则

| 用户说 | group_by |
|--------|----------|
| 分车型/车型结构/车型占比 | `model` |
| 分车系/车系结构 | `series` |
| 城市分布/分城市/按城市 | `city` |
| 增程和纯电/能源类型 | `energy_type` |
| 大区/区域分布 | `region` |
| 渠道分布/分渠道 | `channel` |
| JTBD/主题分布 | `jtbd_theme` |

## Filter 解析规则

| 用户说 | filter 值 |
|--------|-----------|
| 只看大电池组 | `large_battery` |
| 只看小电池组 | `small_battery` |
| 只看五座 | `seat_5` |
| 只看六座 | `seat_6` |

## 上下文继承规则

1. 第一轮: 所有字段来自文本解析
2. 第二轮起: 文本中未出现的字段从上一轮继承
3. Filters 是累加的 (additive)
4. Time window/metric/series/group_by 可显式覆盖

## 分析类型 (analysis_type) 规则

| 用户说 | analysis_type |
|--------|---------------|
| 同比/环比/对比/变化 | `compare` |
| 相比/较/对比 …(近 N 日/昨日/…)均值 | `compare` + 记录 `baseline` |
| 生成结论/日报/摘要/总结 | `summary` |
| 趋势/走势/波动 | `trend` |
| 占比/份额 | `share` |

## 对比基准 (baseline) 语义

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


## 当前模式

- `parser_mode`: `"rule_based"`
- 置信度: 基于匹配规则数量和精确度计算
- 缺失关键字段时 confidence 减半

## Result Reference (结果引用)

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

## Expected Context 模式 vs Parse Text 模式

| 维度 | expected_context 模式 | parse_text 模式 |
|------|----------------------|-----------------|
| context 来源 | cases JSON 中的 expected_context | context_parser 从 user 文本解析 |
| 适用场景 | 回归验证 runner 本身 | 验证 parser 质量 |
| context_match | 不适用 | 比较 parsed vs expected |
| 匹配率 | 不计算 | 输出 match_rate |

## 未来升级路径

1. 当前: rule-based parser
2. 下一阶段: hybrid (rule-based + LLM fallback)
3. 最终: LLM-first parser with deterministic validation
