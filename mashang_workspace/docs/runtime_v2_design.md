# Runtime V2 Design — 基于 Capability Registry 的下一代 Runtime

> 本文件定义 Runtime V2 的基本原则和架构。
> Runtime V2 不重新发明分析能力，只消费 capability_registry 中 eligible 的能力。

## 核心原则

1. **Runtime V2 不重新发明分析能力** — 分析由 workspace runtime_scripts 提供
2. **Runtime V2 只消费 capability_registry 中 eligible 的能力**
3. **Runtime V2 只默认调用 runtime_scripts，不调用 research_scripts**
4. **Runtime V2 统一读取 Result Contract** — 不依赖非结构化的 stdout/stderr
5. **Runtime V2 的 Planner 更薄** — 不再做复杂推理链，只负责 context→capability 匹配
6. **Runtime V2 的 Router 更确定性** — 基于 capability_id 的路由，而非 keyword/intent 模糊匹配
7. **Runtime V2 的核心是 capability dispatch**，而不是复杂推理链
8. **Runtime V2 支持多轮上下文**，但优先复用 workspace 的 context_parser / followup_runner / result_reference
9. **Runtime V2 的每个能力必须能被 eval 验证** — capability audit + numeric eval + contract gate
10. **Runtime V2 从 workspace 晋级能力中生长**，而不是从旧 Runtime 迁移而来

## 建议目录结构

```
mashang_runtime_v2/
├── README.md
├── app/
│   ├── capability_dispatcher.py   # 能力调度核心
│   ├── context_manager.py          # 多轮上下文管理 (可复用 workspace)
│   ├── response_renderer.py        # 结果渲染
│   └── runtime_service.py          # 服务入口
├── adapters/
│   ├── workspace_script_adapter.py # workspace 脚本调用适配器
│   └── result_contract_adapter.py  # Result Contract 解析适配器
├── config/
│   └── runtime_v2_config.yaml      # 配置
├── tests/
│   └── test_dispatch.py
└── eval/
    └── runtime_v2_eval.py
```

## 运行时流程

```
用户输入
  ↓
Context Manager (复用 workspace context_parser)
  ↓
Capability Dispatcher
  ├── 查询 capability_registry → 匹配 capability_id
  ├── 生成 CLI args (复用 workspace _build_args)
  └── 确定调度 plan
  ↓
Workspace Script Adapter
  ├── 调用 runtime_script
  ├── 读取 stdout → 解析 Result Contract
  └── 返回 structured result
  ↓
Response Renderer
  ├── 提取 summary / metrics / dimensions / top_entities
  └── 渲染最终响应 (+ followup_context metadata)
  ↓
返回 (Result Contract + followup_context)
```

## Capability Dispatch

```
context {metric, time_window, series, group_by}
  ↓
capability_registry.json
  ├── 匹配 metric → capability_id (如 lock_count → lock_by_model)
  ├── 检查 tier == runtime
  ├── 检查 auto_schedulable == true
  └── 确定 runtime_script
  ↓
WorkspaceScriptAdapter.invoke(capability, context)
  └── 读取 Result Contract
```

## 与旧 Runtime 的对比

| 维度 | 旧 Runtime | Runtime V2 |
|------|-----------|------------|
| 能力来源 | agent/planner + tools + operators | workspace capability_registry |
| 能力注册 | operators/registry.json | capability_registry.json |
| 路由方式 | LLM Planner + Tool Router intent match | Capability Dispatcher + capability_id |
| 执行方式 | agents + tools + operators | workspace scripts (CLI) |
| 结果格式 | Structured Result Blocks | Result Contract |
| 多轮上下文 | Memory Extractor + Short-term Memory | context_parser + followup_context |
| 评测 | Runtime Eval (behavioral) | Unified Eval (numeric + contract + audit) |
| 晋级路径 | 无 | script_tiers → promotion_rules → registry |

## 首批候选能力

见 `mashang_workspace/registry/capability_registry.json` 中 `runtime_v2_candidate: true` 的能力。

当前候选列表：
- `lock_by_model`
- `lock_city_distribution`
- `daily_lock_count`
- `atp_price_report`
- `attribute_penetration_report`
- `assign_conversion_analysis`
