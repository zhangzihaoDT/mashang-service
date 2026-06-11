# Promotion Rules — 能力晋级规则

## 能力生命周期

```
research_script → runtime_script → mashang_runtime (产品化)
                      ↑
                  utility_script (需包装)
                      ↑
                  legacy_script  (需包装)
```

## research → runtime 晋级条件

必须全部满足：

| # | 条件 | 检查方式 | 优先级 |
|---|------|----------|:------:|
| 1 | 脚本运行时间可控（< 5 分钟） | 手动计时 | P0 |
| 2 | CLI 参数清晰（--help 完整） | `test_script_help` | P0 |
| 3 | 输出标准 Result Contract | Contract Gate | P0 |
| 4 | 至少 1 个 numeric eval case | `numeric_cases.json` | P0 |
| 5 | 纳入 Contract Gate | `run_eval.py CONTRACT_SCRIPTS` | P0 |
| 6 | 有 docs 说明用途和口径 | 检查 docs 字段 | P1 |
| 7 | 业务口径清晰可文档化 | 人工审查 | P1 |
| 8 | 不依赖人工解释才能使用 | 人工审查 | P1 |
| 9 | 不会产生外部副作用 | 人工审查 | P1 |
| 10 | 可被自然语言 parser / followup runner 映射 | 人工审查 | P1 |

## runtime → mashang_runtime 晋级条件

必须全部满足：

| # | 条件 | 检查方式 | 优先级 |
|---|------|----------|:------:|
| 1 | 高频使用或明确业务价值 | 频率统计 / 业务需求 | P0 |
| 2 | 指标口径稳定 | 人工审查 | P0 |
| 3 | Result Contract 稳定（字段不改） | 版本对比 | P0 |
| 4 | core/runtime eval 通过 | `make core-eval` | P0 |
| 5 | 有 followup case 或明确的调度场景 | followup_cases.json | P1 |
| 6 | 有错误处理（status != error） | 人工审查 | P1 |
| 7 | 有 docs 文档 | 检查 docs 字段 | P1 |
| 8 | 可接入 tool_router 或 operators | 架构评审 | P1 |
| 9 | 对外输出格式稳定（不临时改） | 人工审查 | P1 |
| 10 | 不依赖临时路径或临时数据 | 人工审查 | P1 |

## utility / legacy 处理规则

| 情况 | 处理方式 |
|------|----------|
| utility_script 有价值 | 包装为 runtime_script 后再晋级 |
| legacy_script 仍有需求 | 写 wrapper → runtime_script 再晋级 |
| legacy_script 无需求 | 归档到 archive/ |
| 工具类（data_dictionary） | 不晋级，保留为 utility |

## 晋级流程

```
1. 人工评估：对照上述条件逐项检查
2. Capability Audit：自动检查条件 #1-#5（对 runtime）
3. 写入 PRD / RFC 说明晋级原因
4. 修改 capability_registry.json 更新 tier + promotion
5. 如有代码移动，更新 script 字段
6. 运行 make full-eval 确保未破坏
7. 人工审核通过后合并
```
