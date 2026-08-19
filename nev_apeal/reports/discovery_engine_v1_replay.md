# Discovery Engine v1 Replay

**执行日期**：2026-08-19  
**Engine**：`discovery_engine_v1`  
**输入**：`data/source.sav`，SHA-256 `c57788442e886fd8c06e0cf98908902098c4b4c6`  
**Replay 输出**：`scratch/discovery/replay_v1/replay_results.json`

## 1. Replay Scope

本次不是新数据批次，而是对已冻结的同一 `data/source.sav` 做 deterministic replay。因此它验证的是：

- v1 registry 是否可执行；
- Signal Contract 是否稳定产出；
- Round 1/2 的筛选和分流是否可复现；
- 不同运行路径是否意外改变结果。

它**不能**证明跨数据批次的泛化能力。泛化验证需要新的样本或新的数据 wave。

## 2. Replay Output

| 层级 | 冻结预期 | Replay | 结果 |
|---|---:|---:|---|
| Round 1 main-effect axes | 25 | 25 | ✅ |
| Round 2 expectation signals | 6 | 6 | ✅ |
| Round 2 nonlinear signals | 1 | 1 | ✅ |
| Round 2 discriminator signals | 3 | 3 | ✅ |
| Interaction pilot tests | 9 | 9 | ✅ |
| Interaction qualified signals | 0 | 0 | ✅ |

### Round 1

Replay 的 top axes 与原 Signal Board 一致：

- `CN_EDUCATION` gap `53.5`
- `CN_OCCUPATION` gap `52.2`
- `NEV_01` gap `51.6`
- `AGE_BUCKETS` gap `49.5`
- `NEV_11C` gap `47.7`
- `NEV_08` gap `45.1`

这说明 main-effect 宽扫描的排序和 n≥50 screening gate 可复现。

### Round 2

Replay 保持相同的 10 Signal 结构：

- `expectation_wow`：6
- `nonlinear_pattern`：1
- `segment_discriminator`：3

其机制分流也保持一致：预期校准进入 T9 机制路径，里程非线性进入 T10 qualification，segment discriminator 保持 validation queue。

### Interaction

9 个预注册 tests 全部在 `SEGMENT_DP` cell-support gate 被拦截，状态均为 `INSUFFICIENT_COVERAGE`。Replay 没有把 spread 重新解释为 interaction evidence，也没有因为结果显著而创建新 Candidate/Topic。

## 3. Does v1 Reproduce High-Quality Topics?

### Same-snapshot answer

**可以复现高质量 Topic 的候选入口和分流路径，但本次 replay 不是独立的 Topic replication。**

- T9 的核心输入 Signal、FULL controls、item qualification 路径完全复现；结合已完成的 terminal run，T9 保持 `READY`。
- T10 的 nonlinear signal 完全复现；结合 terminal run，T10 保持 `INCONCLUSIVE`，没有被漂亮的非线性结构强行升级。
- Interaction 没有产生伪 Candidate，说明 v1 的保守 Gate 在 replay 中保持有效。

### Quality judgment

| 判断项 | 结果 |
|---|---|
| 可执行性 | PASS |
| 结果可复现性 | PASS |
| Signal clustering 稳定性 | PASS |
| Candidate 分流纪律 | PASS |
| 产生新 Topic 的独立泛化证据 | NOT TESTED |
| 跨 wave 稳健性 | NOT TESTED |

## 4. Freeze Decision

Discovery Engine v1 可以继续冻结，不需要为同一 snapshot 做 v1.1 微调。当前最合理的下一步不是修改规则追求更多 Candidate，而是等待新数据 wave 后重复同一 replay：

1. 保持 25-axis Round 1 registry 不变。
2. 保持 Round 2 的 3 类受控 scanner 不变。
3. 保持 Interaction 的 `n≥100` cell gate，不对 `SEGMENT_DP` 事后降门槛。
4. 用新 wave 的 Signal overlap、Candidate overlap、READY rate 和 rejection quality 评估真正的泛化能力。

**结论：** v1 已通过“同一数据快照的可复现性验收”，暂不宣称通过“跨数据批次高质量 Topic 复现验收”。
