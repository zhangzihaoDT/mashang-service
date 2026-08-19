# Discovery Engine v1 Freeze

**冻结日期**：2026-08-19  
**版本**：`discovery_engine_v1`  
**冻结目的**：从探索性设计转为可复现 replay engine；后续新数据批次不得在 replay 过程中临时改变 registry、阈值或 Topic qualification 规则。

## Frozen Input

| 项目 | 值 |
|---|---|
| 数据文件 | `nev_apeal/data/source.sav` |
| SHA-256 | `c57788442e886fd8c06e0cf98908902098c4b4c6` |
| 规模 | 9,937 × 370 |
| 权重 | `APEAL_WT` |
| 核心 outcome | `APEAL_Index` |
| Contract | `contracts/signal_contract.json` schema v1.0 |

## Frozen Analysis Types

1. `main_effect`：Round 1 宽扫描，25 个登记轴，组别 `n≥50`，只产生 screening Signal。历史文档中的“26 轴”是计数错误；以当前 executable registry 和 25 行 Signal Board 明细为准。
2. `expectation_wow`：`AFUEL_D_06`、`ACHAR_D_05`，三档 Worse/About/Better，FULL controls + WLS/OLS。
3. `nonlinear_pattern`：登记 exposure 仅 `NEV_12`，固定业务里程边界。
4. `segment_discriminator`：登记 exposure × `SEGMENT_DP` queue，组内候选对比，不作正式 interaction 证据。
5. `interaction`：Controlled Pilot；当前首批 9 tests，严格 cell gate，不执行全量 O(p²)。

## Frozen Qualification Gates

- Interaction 每个 exposure contrast cell 原始 `n≥100`，至少 3 个可估计 segment。
- 正式 interaction 必须有 interaction block、HC1 covariance、BH-FDR q-value 和业务 effect size。
- Segment spread 只能作为 descriptive heterogeneity clue。
- Interaction 默认是 parent Topic refinement；没有 moderator mechanism + incremental explanation，不创建新 Candidate/Topic。
- T9/T10 的终局规则保持不变：T9 可因 item 机制进入 READY；T10 不得把横截面里程梯度直接命名为质量衰减。

## Frozen Budget Rules

- Round 1：宽扫描，低预算，不直接进入深度研究。
- Round 2：按机制 cluster 分配 Candidate budget；同一变量的多个 Signal 可以独立竞争。
- Interaction：最多 12 个预注册 tests；当前 `SEGMENT_DP` pilot 未通过 coverage 后暂停，不事后降低门槛。
- Replay 只生成候选和 qualification evidence，不自动修改既有 Topic 状态。

## Artifact Manifest

- `scratch/signal_scan.py`
- `scratch/discovery/expectation_wow_scan.py`
- `scratch/discovery/nonlinear_pattern_scan.py`
- `scratch/discovery/segment_discriminator_scan.py`
- `scratch/discovery/interaction_scan.py`
- `contracts/signal_contract.json`
- `reports/signal_board.md`
- `reports/interaction_discovery_gate_review.md`
- `reports/discovery_engine_retrospective_round1_round2.md`

**冻结声明：** replay 结果若改变结论，只能说明数据批次或可复现性存在差异，不能通过修改 v1 规则来追随结果；规则变化应建立 `discovery_engine_v2`。
