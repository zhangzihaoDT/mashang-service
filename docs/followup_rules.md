# Follow-up Rules — 多轮追问规则

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
→ 脚本: scripts/lock_city_distribution.py --date 昨天 --series LS8
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

## 自动化 Runner

项目提供 `eval/run_followup_eval.py` 用于自动化验证追问→脚本映射：

```bash
# dry-run (默认)
python eval/run_followup_eval.py

# 真实执行推荐命令
python eval/run_followup_eval.py --execute

# 指定基准日期
python eval/run_followup_eval.py --as-of-date 2026-06-11
```

Runner 的规则映射详见 `docs/followup_runner_rules.md`。

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
