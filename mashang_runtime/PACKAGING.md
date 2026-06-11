# Legacy Runtime Packaging

## 已打包资产

以下旧 Runtime 资产已从根目录打包到 `mashang_runtime/`：

| 源路径 | 目标路径 | 文件数 | 说明 |
|--------|----------|:------:|------|
| `agent/` | `mashang_runtime/agent/` | 11 | Agent 循环、Planner、Router |
| `tools/` | `mashang_runtime/tools/` | 22 | 确定性执行工具 |
| `operators/` | `mashang_runtime/operators/` | 29 | 业务算子 |
| `schema/` | `mashang_runtime/schema/` | 9 | 配置/指标/路径定义 |
| `main.py` | `mashang_runtime/main.py` | 1 | CLI 入口 |
| `feishu_bot.py` | `mashang_runtime/feishu_bot.py` | 1 | 飞书入口 |
| `设计方案/` | `mashang_runtime/design_docs/` | 4 | 设计文档 |

## 根目录兼容入口

根目录仍保留 `main.py` 和 `feishu_bot.py`，但已改为轻量 wrapper：

- `python main.py` → 自动转发到 `mashang_runtime/main.py`
- `python feishu_bot.py` → 自动转发到 `mashang_runtime/feishu_bot.py`

wrapper 通过 `runpy.run_path()` 将实际执行委托给 `mashang_runtime/` 中的真实入口。
同时确保 `mashang_runtime/` 和项目根目录都在 `sys.path` 中，以便旧 import 路径正常工作。

## 旧 Runtime 内部 import 兼容策略

旧 Runtime 内部使用相对路径：

```python
from agent.xxx import ...
from tools.xxx import ...
from operators.xxx import ...
from schema.xxx import ...
```

迁移后，这些 import 能正常工作因为：
1. `main.py` wrapper 将 `mashang_runtime/` 加入 `sys.path`
2. `mashang_runtime/runtime_paths.py` 在模块级自动将 `mashang_runtime/` 和项目根目录加入 `sys.path`

## 冻结原则

- 旧 Runtime **不再作为日常主开发入口**
- **新能力不得直接进入 `mashang_runtime/` 下的 agent/tools/operators/schema**
- 维护策略：**freeze by default, patch only if required**

## workspace 与旧 Runtime 的关系

workspace 脚本可能仍 import 旧 Runtime 的模块：

```python
from operators.atp_analysis import ...
from schema.xxx import ...
```

迁移后，`mashang_workspace/utils/paths.py` 的 `ensure_runtime_on_path()` 会将 `mashang_runtime/` 加入 `sys.path`。
长期建议逐步改为导入 workspace 中的稳定包装。

## Runtime V2 与旧 Runtime 的关系

Runtime V2 不继承旧 Runtime 目录结构。
Runtime V2 基于 `mashang_workspace/capability_registry` 重新设计。

详见 `mashang_workspace/docs/runtime_v2_design.md`。

## 不应在旧 Runtime 中新增新能力

- 新能力必须先进入 `mashang_workspace` → `research_scripts` → `runtime_scripts` → `capability_registry`
- 满足 promotion_rules 后才能进入 Runtime V2
