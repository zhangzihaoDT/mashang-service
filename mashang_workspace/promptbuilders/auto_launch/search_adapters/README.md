# Search Adapters — 可选搜索后端

## 定位

Search Adapters 是 Auto Launch **可选的工程化搜索后端**。

它们的职责是：在用户需要时，提供从公开网络搜索候选信息的能力，供后续 Prompt / LLM / Validator 判断。

## 当前状态

| 适配器 | 状态 | 说明 |
|--------|------|------|
| Volc Search (火山方舟) | ✅ 已验证可用 | 旧 auto_launch_monitor.py 中唯一跑通全链路的搜索源 |

## Volc Search Prompt Bridge

Volc Search 现在通过 **Prompt Bridge** 使用，而非直接集成 runner：

1. **查询计划**：`prompts/volc_search_query_plan.md` — 根据业务任务生成搜索 query plan
2. **结果结构化**：`prompts/volc_search_result_to_event_brief.md` — 将搜索结果整理为 intake-ready JSON
3. **Pilot runbook**：`runbooks/volc_search_assisted_pilot.md` — 完整操作流程

当前仍不实现 runner。Volc Search Adapter 只负责候选信息，不负责事件判断。

## 在新架构中的角色

```
Search Adapter (optional)
    │
    ▼ 返回候选搜索结果 (title + snippet + URL + date)
    │
volc_search_result_to_event_brief Prompt
    │
    ▼ 提取 + 结构化
    │
validator + normalizer (validators/)
    │
    ▼
标准化 evidence JSON
```

关键约束：
- Search Adapter **只负责搜索候选信息**，不承担事件判断
- 后续的判断、提取、验证由 Prompt + Validator 完成
- Search Adapter 是 **可选组件**，用户可以纯手工搜索后填入 Prompt
- 不实现完整 monitor 流程，不构造搜索-提取-判断管道
