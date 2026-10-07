# Runtime Legacy Lessons — 旧 Runtime 经验萃取

> 基于旧 Runtime（agent/tools/operators/schema）的实践经验总结。
> 目标是指导 Runtime V2，而不是维护旧 Runtime。

## 1. 旧 Runtime 的历史定位

旧 Runtime 最初是为探索 Agentic BI 可行性而构建的 productization prototype。
它证明了一条核心链路：自然语言 → Planner → Tool Router → 确定性执行 → 结构化结果 → 总结。

## 2. 旧 Runtime 解决过的问题

- 将自然语言问题转化为结构化 DSL
- 通过 Tool Router 将 DSL 路由到确定性执行工具
- 通过 Evidence Contract 判断何时信息足够回答
- 通过 Structured Result 提供可追溯的执行结果
- 通过 Memory Extractor 实现多轮上下文
- 通过 Clarification Runtime 处理歧义指标选择

## 3. Planner / Tool Router 的价值

Planner（LLM-based）是将自然语言转为 DSL 的核心。
Tool Router 提供了确定性执行层。

**Runtime V2 可以保留的模式**：
- DSL 表示分析意图（metric / dimension / time / filter）
- 确定性执行（不依赖 LLM 做计算）
- 按 analysis_intent 路由到不同执行路径

**Runtime V2 不要复制的模式**：
- Planner 过于庞大（~400 行推理逻辑）
- Router 中混合了 intent 检测、operator 匹配、clarification 处理等多层职责

## 4. Operator 层的可复用价值

旧 Runtime 中有 10 个固定业务算子（active_store, retained_intention, assign_conversion 等）。
这些算子封装了强业务口径，是旧 Runtime 中最有价值的资产。

**可复用**：算子逻辑本身（operators/ 目录中的 Python 代码）
**不推荐直接迁移**：算子注册表、算子匹配路由、算子 eval 策略

## 5. Evidence Contract / Structured Result 的演化经验

旧 Runtime 引入了 Evidence-driven 决策，是其最有价值的设计之一。
关键概念：
- `fact_type`：证据的最小单位
- `evidence_hints`：工具声明的预期证据类型
- `contract`：所需证据的声明
- `missing_facts`：决策依据
- `stall_detection`：防止空转的熔断机制

**这些概念已经沉淀到 workspace**：
- Result Contract（Phase 5）
- Numeric Eval（Phase 5）
- Contract Gate（Phase 6）
- Unified Eval（Phase 6）

## 6. Memory / Follow-up / Clarification 的复杂度教训

旧 Runtime 的 Memory Extractor、Short-term Memory、Clarification Runtime 是复杂度最高的部分。

**经验教训**：
- 短记忆（5 轮 TTL）在实际运行中频繁失效
- Clarification 的指标消歧增加了路由的复杂度
- Fact Extraction 从 structured_blocks 中抽取 facts 的规则复杂且易错

**Runtime V2 简化方向**：
- 多轮上下文优先复用 workspace 的 `context_parser` + `followup_runner` + `result_reference`
- 不重新实现 memory 和 clarification 逻辑
- 利用 Result Contract 的 `followup_context` 做上下文传递

## 7. 为什么 workspace-first 更适合当前主线

旧 Runtime 的问题：
- LLM Planner 不稳定，需要大量 prompt 和 fallback
- 算子注册表与 schema 配置耦合
- Tool Router 中 intent 检测与 keyword 匹配混杂
- 难以测试（Runtime Eval 覆盖有限）

workspace-first 的优势：
- 脚本独立、可测试
- CLI 统一、Result Contract 统一
- Eval 覆盖全面（unified eval / numeric eval / contract gate）
- Capability Registry 提供能力可见性
- Promotion Rules 提供晋级路径

## 8. 已沉淀到 workspace 的经验

| 经验来源 | Workspace 对应 |
|----------|----------------|
| Structured Result | `utils/result_contract.py` (Phase 5) |
| 指标注册表 | `docs/metric_definitions.md` |
| 时间窗口解析 | `docs/time_window_rules.md` |
| 车型映射 | `docs/vehicle_mapping.md` |
| 追问上下文 | `eval/context_parser.py` (Phase 4) |
| 追问继承 | `docs/followup_rules.md` |
| 脚本 CLI | Phase 2 标准 |
| 统一评测 | `eval/run_eval.py` (Phase 6) |
| 能力注册 | `registry/capability_registry.json` (Phase 11) |
| 晋级规则 | `docs/promotion_rules.md` (Phase 11) |

## 9. 仍可复用的旧代码

| 模块 | 复用意途径 |
|------|-----------|
| `operators/` 中的算子 | 可被 workspace scripts 直接 import（如 `atp_price_report.py` 已复用） |
| `schema/business_definition.json` | 车型映射、时间窗口、座位/电池容量规则 |
| `operators/time_windows.py` | 时间语义解析（虽然后续可由 docs 替代） |
| `schema/metrics.json` | 指标注册表参考 |

## 10. Runtime V2 不应重复的模式

| 旧模式 | 替代方案 |
|--------|----------|
| LLM-based Planner | 能力注册表 + rule-based context_parser + deterministic dispatch |
| Hidden Intent Matching | 显式的 analysis_intent 声明 |
| Memory Extractor | Result Contract followup_context |
| Short-term Memory TTL | 每次请求独立，不维护 session 级 cache |
| Clarification Runtime | context_parser 的 ambiguity 检测 + 澄清问题 |
| Operator Registry | Capability Registry |
| Runtime Eval (behavioral) | Unified Eval（数值 + 合约 + 引用） |
