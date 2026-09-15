# Verification Scope Contract

把「充分验证」定义为**「命中改动范围的验证」**，而不是「扩大 pytest scope」。

## 问题

仓库此前没有机器可读的验证范围定义，加上根 `AGENTS.md` 的旧规则「每次完成改动后运行 `make eval` 或 `make ci`」，会产生一个错误等价：

```
充分验证  ==  扩大 pytest scope  ==  跑全量测试
```

后果：

- 一个小改动会触发全量 pytest，命中大量历史失败；
- 无法区分「本次回归」与「仓库存量问题」；
- Agent 的完成标准被无关失败淹没，于是继续扩大范围，进入测试范围膨胀的循环。

## 契约

```text
.opencode/verification/
├── scope_contract.json              # 契约本体（targets / rules / baseline_failures / policy）
├── resolve_verification_scope.py    # 解析器（计划 + baseline-aware --run）
├── tests/test_verification_scope.py # 自测
└── README.md
```

- **targets**：具名可执行检查（命令、是否依赖 dataset、层级）。
- **rules**：路径 glob → 最小 required targets（含动态 target：脚本 `--help`、改动测试文件、模块 `tests/`）。
- **baseline_failures**：已登记的历史失败，**不算本次回归**，P1 处理。
- **policy**：范围边界规则。

## 用法

```bash
# 只计划：解析最小验证范围（不执行）
python .opencode/verification/resolve_verification_scope.py --worktree
# 或 make verify-scope

# 执行 scope 内验证，baseline 失败不阻断
python .opencode/verification/resolve_verification_scope.py --worktree --run
# 或 make verify

# 针对一次具体改动 / 一段提交
python .opencode/verification/resolve_verification_scope.py \
  --changed Makefile docs/x.md mashang_workspace/research_scripts/y.py --run
python .opencode/verification/resolve_verification_scope.py --range origin/main..HEAD --run

# 显式扩大范围（必须显式，才会跑全部 target）
python .opencode/verification/resolve_verification_scope.py --all --run
```

输出为 Result Contract（`scope` / `result` / `errors`），其中 `scope` 显式包含：

- `required_targets`：本次**要跑**的；
- `out_of_scope_targets`：本次**不跑**、失败不算回归的；
- `excluded_baseline_failures`：已知历史失败。

## 判定规则

| 情况 | 判定 |
|------|------|
| 纯文档改动 | `decision=no-op`，不运行测试 |
| scope 内全部通过 | `success` |
| scope 内仅命中 `baseline_failures` | `passed_with_baseline`，`success` |
| scope 内出现非 baseline 失败 | `error`，列出 `regressions` |
| 存在未分类文件 | 提示，`decision=review` |

## 边界

- **不因外部失败扩大范围**：`out_of_scope_targets` 的失败，不是本次回归。
- **不隐式全量**：只有 `--all` 才解析全部 target。
- **不改动本身**：契约只回答「该验证什么」，不回答「怎么修」。
- **worktree 模式**会纳入当前工作区全部未提交改动；只验证某次改动时用 `--changed` / `--range`。

## 扩展

新增验证维度时：

1. 在 `scope_contract.json` 的 `targets` 增加具名 target；
2. 在 `rules` 增加路径 glob 映射；
3. 更新 `tests/test_verification_scope.py`（schema 校验会自动检查 target 引用是否存在）。
