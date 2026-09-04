# mashang_runtime_v2 — Unified Research Runtime

统一研究 Runtime（编排层），对应冻结五层命名（根 README §1）的第 4 层。

消费两类对象：

```text
mashang_runtime_v2
├── Tool / Capability invocation
│     └── mashang_workspace（Daily Business Analytics：确定性业务分析，Result Contract）
└── Research Application orchestration
      ├── MIIT / auto_launch / nev_apeal / project_4 / project_5
      └── 长期驱动、持续产出状态与成果的研究程序（演进目标）
```

## 当前实现状态

**确定性分析一侧（已实现最小闭环）：**

```text
user text
  ↓ context_manager（复用 workspace eval context_parser）
capability_dispatcher（config 声明式匹配，registry 佐证）
  ↓
workspace_script_adapter（只允许 mashang_workspace/runtime_scripts/）
  ↓
Result Contract → response_renderer → answer（支持多轮 session）
```

| 组件 | 现状 |
|------|------|
| `app/runtime_service.py` | NL→context→dispatch→execute→contract→render 闭环 + CLI（`--session` 多轮） |
| `app/capability_dispatcher.py` | config 驱动匹配（详见下文），不硬编码业务能力 |
| `app/workspace_script_adapter.py` | 仅执行 `mashang_workspace/runtime_scripts/`，输出 Result Contract |
| `app/result_contract_adapter.py` / `response_renderer.py` | 契约解析与自然语言渲染 |
| `app/context_manager.py` | 委托 workspace `eval/context_parser` |
| `app/session_store.py` | 多轮会话持久化 |
| `config/runtime_v2_config.json` | 能力开关 / 脚本映射 / dispatch 规则 / 展示标签 |
| `eval/` `tests/` | 单轮 + 多轮 eval 用例与 pytest |

**Research Application 编排一侧**：尚未实现，为演进目标。neval 的 `nev_apeal` 是第一个成熟候选
（已有 engine/state/contracts/gate/artifacts），作为优先 pilot。

## 设计原则

```text
不重新发明分析能力；
调用 workspace 中已治理完成的能力，统一消费 Result Contract；
长期编排独立 Research Applications，不把业务代码复制进本目录；
能力可由 eval 验证。
```

详细设计见 `mashang_workspace/docs/runtime_v2_design.md`；能力晋级规则见 `mashang_workspace/docs/promotion_rules.md`；
候选能力见 `mashang_workspace/registry/capability_registry.json`。
