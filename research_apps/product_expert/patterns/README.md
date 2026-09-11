# patterns/ — 跨 run 的语义主键注册表

本目录是 `pattern_key` 的唯一事实来源。`pattern_key` 是 Pattern 的**跨 run 稳定语义身份**：

```text
pattern_id      = 本次 run 的实例 ID      （PAT-0001，可随 run 变化）
pattern_key     = 跨 run 的稳定语义身份   （cockpit_ergonomics_steering_visibility）
convergence_id  = 本次 run × pattern 快照 （CONV-0001）
```

## 为什么需要 pattern_key

Temporal Comparison 必须判断「不同 run 里的两个 Pattern 是不是同一个问题」。
如果只靠 `pattern_id`，编号会随 run 重排，比较会碎掉。`pattern_key` 提供稳定锚点。

## 使用规则（也见 `workflow/convergence.md`）

创建 Pattern 之前：

1. **匹配优先**：先在 `pattern_keys.json` 中按语义匹配（功能 / 体验维度 / 对标）。
   命中即 `reuse` 已有 key，包括把新表述登记为 `aliases`。
2. **确为新语义才新建**：只有找不到可复用 key 时，才提出新 key 候选。
   新 key 必须写进 `pattern_keys.json`，并记录 `first_pattern_id` / `first_run_id`。
3. **不允许**由单次 run 的 Agent 自由生成未登记的 key。
4. 已废弃的 key 标 `retired`，不删除，保留历史可追溯。

## 匹配示例

```text
已有 key：cockpit_ergonomics_steering_visibility

新表述：「方向盘挡流媒体后视镜」
新表述：「方向盘上沿影响驾驶员后视镜观察」

→ 语义命中，reuse cockpit_ergonomics_steering_visibility，追加为 aliases
→ 不创建新 key
```

## 文件

- `pattern_keys.json`：注册表本体，结构见 `../schemas/pattern_keys.schema.json`。
