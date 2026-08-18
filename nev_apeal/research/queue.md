# Research Queue

Queue is the Agent's prioritized unresolved-question list. Each round should select one highest-priority `open` item, execute the smallest sufficient analysis, append evidence, and update state.

## Per-topic isolation（Runtime isolation）

Queue 是 **per-topic** 的，存放在：

```text
research/runs/<topic>/queue.yaml
```

不同 Topic 的队列互不污染，可并行推进。`stop_conditions` 也随 per-topic 队列一起维护（每个 run 可定义自己的 required_confounders / mechanism 门槛）。

- `derive-questions --apply` 写入当前 topic 的队列
- `next` / `stop-check` 读取当前 topic 的队列
- 引擎在 `research/runs/<topic>/queue.yaml` 不存在时回退到默认 stop_conditions（无全局单例）

Use:

```bash
python nev_apeal/cli.py research next --topic topic_x
python nev_apeal/cli.py research stop-check --topic topic_x
```
