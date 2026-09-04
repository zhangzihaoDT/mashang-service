# Interaction Discovery Pilot｜Round 1

**执行日期**：2026-08-19  
**脚本**：`scratch/discovery/interaction_scan.py`  
**输出**：`scratch/discovery/_signals_interaction.json`  
**测试数**：9 个预注册 tests  
**Moderator**：`SEGMENT_DP`  
**边界**：segment spread 只作描述性 effect aid；正式证据必须来自 interaction block + HC1 + FDR/q-value + business effect size。

## Terminal Result

**本轮没有一个 test 通过正式 qualification。**

原因不是 interaction block 不显著，而是更前置的 cell-support gate：在 exposure 两侧各自 `n≥100`、且至少 3 个结构段满足条件后，9 个 exposure × outcome 组合均没有形成足够的可估计 segment 集合。特别是 `NEV_08` 的“Everyday vs Never”在 `SEGMENT_DP` 内高度稀疏，不能把全样本 block p-value 或 segment spread 当作正式 interaction 证据。

| exposure | outcome 数 | 可估计结构段 | interaction block | FDR/q-value | 处理 |
|---|---:|---:|---|---|---|
| `NEV_08` | 3 | <3 | 未估计 | N/A | `INSUFFICIENT_COVERAGE`，不降低 cell 门槛 |
| `AFUEL_D_06` | 2 | <3 | 未估计 | N/A | `INSUFFICIENT_COVERAGE` |
| `ACHAR_D_05` | 2 | <3 | 未估计 | N/A | `INSUFFICIENT_COVERAGE` |
| `NEV_12` | 2 | <3 | 未估计 | N/A | `INSUFFICIENT_COVERAGE` |

## Boundary Decisions

1. **没有把 segment spread 升格为 interaction 证据。** 之前的 76~118 点 spread 仍然只是异质性线索。
2. **没有把未能估计的 interaction 写成“不显著”。** 正确状态是 `INSUFFICIENT_COVERAGE`，因为模型没有通过预设 cell gate。
3. **没有新增 Candidate/Topic。** 本轮既没有正式 interaction evidence，也没有 parent Topic 的增量机制结论。
4. **没有事后降低 `n≥100`。** 如果要继续，必须重新过 Gate，预先规定 moderator 聚合方式或换到 cell 支持更充分的 moderator。

## Next Decision

Interaction Discovery 仍保持 **Controlled Pilot**，但 `SEGMENT_DP` 第一轮因覆盖不足暂停。下一次只允许两种明确路径：

- 预注册结构段合并规则后重跑，不根据结果临时合并；或
- 切换到已有业务定义、cell 支持更充分的 moderator（例如价格带/豪华定位），重新建立 test registry。

在此之前，所有结果保持 validation queue，不进入 Tournament Candidate。
