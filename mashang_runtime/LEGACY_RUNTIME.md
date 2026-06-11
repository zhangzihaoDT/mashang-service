# Legacy Runtime Freeze

> 生效日期: 2026-06-11
> 本文件标记 `mashang_runtime/` 当前状态，并说明后续策略。

## 状态

`mashang_runtime/` 当前代表：

```
旧 Runtime / Productization Prototype
```

**不再作为日常主开发入口。**

## 冻结规则

1. **新能力不得直接进入旧 agent/tools/operators/schema**
2. 新能力必须先进入 `mashang_workspace`：
   - `research_scripts` → `runtime_scripts` → `capability_registry` → `promotion_rules`
3. 旧 Runtime 中的 `agent/` `tools/` `operators/` `schema/` `main.py` `feishu_bot.py` 作为**历史资产和经验参考保留**
4. 旧 Runtime **不会被强行整体迁移**，而是由 Runtime V2 基于 `capability_registry` 重新设计
5. 如需复用旧代码，应先包装进入 workspace `runtime_scripts` 或 `research_scripts`，再注册为 capability
6. 旧 Runtime 的维护策略：**freeze by default, patch only if required for historical reproducibility**

## 已记录的经验

旧 Runtime 中已萃取的经验教训见：
- `mashang_workspace/docs/runtime_legacy_lessons.md`

## Runtime V2 方向

Runtime V2 设计见：
- `mashang_workspace/docs/runtime_v2_design.md`

Runtime V2 候选能力见：
- `mashang_workspace/registry/capability_registry.json` → `promotion.runtime_v2_candidate`
