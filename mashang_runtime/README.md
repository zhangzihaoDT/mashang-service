# mashang_runtime — Agentic BI Runtime (Legacy)

## 状态

> **LEGACY — Frozen**
>
> `mashang_runtime/` 当前代表旧 Runtime / Productization Prototype。
> 详见 `LEGACY_RUNTIME.md`。

## Legacy Runtime Freeze

自 2026-06-11 起，旧 Runtime 已正式冻结。详见 `LEGACY_RUNTIME.md`。

## Runtime V2 Direction

Runtime V2 将基于 `mashang_workspace/capability_registry` 重新设计。
不迁移旧 Runtime 代码，而是从 workspace 能力注册表中晋级能力。

详见 `mashang_workspace/docs/runtime_v2_design.md`。

## Workspace-first Capability Promotion

新能力生命周期：

```
research_script → runtime_script → capability_registry → Runtime V2
```

详见 `mashang_workspace/docs/promotion_rules.md`。

## 状态标注

| 目录 | 说明 | 当前状态 |
|------|------|----------|
| `agent/` | Agent 主循环、规划、状态、路由、运行时决策 | 🧊 Frozen |
| `tools/` | 10 个执行工具 | 🧊 Frozen |
| `operators/` | 10 个固定业务算子 | 🧊 Frozen (可复用) |
| `schema/` | 配置/指标/路径定义 | 🧊 Frozen |
| `main.py` | CLI 入口 | 🧊 Frozen |
| `feishu_bot.py` | 飞书入口 | 🧊 Frozen |
