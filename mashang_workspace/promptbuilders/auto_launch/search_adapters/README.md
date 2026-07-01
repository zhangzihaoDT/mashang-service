# Search Adapters — 可选搜索后端

## 定位

Search Adapters 是 Auto Launch **可选的工程化搜索后端**。

它们的职责是：在用户需要时，提供从公开网络搜索候选信息的能力，供后续 Prompt / LLM / Validator 判断。

## 当前状态

| 适配器 | 状态 | 说明 |
|--------|------|------|
| Volc Search (火山方舟) | ✅ 已验证可用 | 旧 auto_launch_monitor.py 中唯一跑通全链路的搜索源 |

## 在新架构中的角色

```
Search Adapter (optional)
    │
    ▼ 返回候选搜索结果 (title + snippet + URL + date)
    │
ChatGPT Plan / Prompt + LLM
    │
    ▼ 判断 + 提取
    │
validator + normalizer
    │
    ▼
标准化 evidence JSON
```

关键约束：
- Search Adapter **只负责搜索候选信息**，不承担事件判断
- 后续的判断、提取、验证由 Prompt + LLM + Validator 完成
- Search Adapter 是 **可选组件**，用户可以纯手工搜索后填入 Prompt
- 不实现完整 monitor 流程，不构造搜索-提取-判断管道
