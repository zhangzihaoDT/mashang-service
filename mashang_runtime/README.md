# mashang_runtime — Legacy Frozen Runtime

## 状态

> **LEGACY — FROZEN (Permanent)**
>
> `mashang_runtime/` 是旧版 Agentic BI Runtime 的 frozen snapshot。
> 该目录**保留原路径**，作为 historical backup / legacy reference。
> 不规划 rename，不移动目录。
> 未来如果 `main.py` 和 `feishu_bot.py` 不再使用，只清理 root shim 本身，不牵动 runtime 目录。

## 冻结声明

自 2026-06-11 起：

- **不再新增依赖** — 新代码不应添加对 `mashang_runtime/` 中任何模块的 import
- **不再新增 operator / schema / loader** — 所有新业务原语应写入 `shared/`
- **不再新增 tool / agent 模块** — 新 Runtime 架构在 `mashang_runtime_v2/` 中实验

## Canonical Shared Logic

当前 `mashang_runtime/operators/` 和 `mashang_runtime/schema/` 保留 legacy 副本，
但 canonical 版本已迁移到 `mashang_shared/`（即根目录 `shared/`）：

| 能力 | Canonical 位置 | 本目录副本 |
|------|---------------|-----------|
| 业务算子 (14 个) | `shared/operators/` | `mashang_runtime/operators/` (frozen copy) |
| 业务 Schema | `shared/schema/` | `mashang_runtime/schema/` (frozen copy) |
| 数据 Loader | `shared/loaders/` | — |

如需复用能力，**优先使用 `shared/`**，而非 `mashang_runtime/`。

## 当前 workspace 实际依赖

当前 workspace **没有任何** import 指向 `mashang_runtime/`。
该目录仅被以下历史入口文件引用：

- `main.py` (root) → 委托 `mashang_runtime.main`
- `feishu_bot.py` (root) → 委托 `mashang_runtime.feishu_bot`

## 相关文档

- `shared/README.md` — shared canonical layer 说明
- `mashang_workspace/docs/runtime_v2_design.md` — Runtime V2 设计
- `mashang_workspace/docs/promotion_rules.md` — workspace-first 能力晋阶规则
- `mashang_workspace/docs/project_cleanup_audit.md` — 项目结构边界审计

## 目录状态

| 目录 | 内容 | 当前状态 |
|------|------|----------|
| `agent/` | Agent 主循环、规划、状态、路由、运行时决策 | 🧊 Frozen |
| `tools/` | 10 个执行工具 | 🧊 Frozen |
| `operators/` | 14 个业务算子（legacy 副本，canonical 在 `shared/operators/`） | 🧊 Frozen |
| `schema/` | 配置/指标/路径定义（legacy 副本，canonical 在 `shared/schema/`） | 🧊 Frozen |
| `main.py` | CLI 入口 | 🧊 Frozen |
| `feishu_bot.py` | 飞书入口 | 🧊 Frozen |
