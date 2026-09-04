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

**Research Application 编排一侧**：PoC 已落地 —— `app/feature_job_adapter.py` 通过
`config/feature_jobs` 声明式调用外部 Research Application 的 job（固定 argv 模板 + 白名单参数 +
cwd/subprocess，无 shell；status/duration/artifact/摘要）。当前已接入 nev_apeal 两个 job：

- `nev_apeal_production_golden`（Golden Gate，--format json → PASS/FAIL + 7 个验收数）
- `nev_apeal_research_state`（`--job-param topic=<run>` → topic state YAML + state.yaml artifact）

```bash
make runtime-v2-feature-job-demo JOB=nev_apeal_production_golden
make runtime-v2-feature-job-demo JOB=nev_apeal_research_state JOB_PARAMS="--job-param topic=topic_x"
```

nev_apeal 是第一个成熟 Research Application（已有 engine/state/contracts/gate/artifacts），
作为编排 pilot；验证模式后 MIIT / auto_launch / project_4 等按同一 config 约定接入。

## 设计原则

```text
不重新发明分析能力；
调用 workspace 中已治理完成的能力，统一消费 Result Contract；
长期编排独立 Research Applications，不把业务代码复制进本目录；
能力可由 eval 验证。
```

详细设计见 `mashang_workspace/docs/runtime_v2_design.md`；能力晋级规则见 `mashang_workspace/docs/promotion_rules.md`；
候选能力见 `mashang_workspace/registry/capability_registry.json`。
