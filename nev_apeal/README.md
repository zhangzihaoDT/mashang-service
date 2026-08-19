# NEV-APEAL Research

新能源车用户体验研究项目。项目以 `data/source.sav` 为核心数据源，通过可复现的 Research Run、Discovery Engine 和 Topic Tournament，将统计信号沉淀为 OEM 可读的产品洞察与 Topic Deck。

## 当前结论

最终 Champion：

> **T1 Purchase Mission：已有车辆经验的用户，不是要更多参数，而是要立即感觉到体验升级。**

Production Topic 报告主线：

> **从参数升级到体验升级。**

主要证据：增购用户 APEAL 为 `798.4`，控制能源、价格、品牌和细分市场结构后，增购优势仍为 `+18.17`；差异主要集中在外观、驾驶、动力和座舱，而补能差异仅 `+1.3`。

## Project Status

| 项目               | 状态                                  |
| ------------------ | ------------------------------------- |
| Research Engine v1 | `FROZEN`                              |
| Champion Research  | `COMPLETE`                            |
| Topic Tournament   | `COMPLETE`                            |
| Production Deck    | `CONTENT LOCKED`                      |
| Current Phase      | `PPT VISUAL PRODUCTION`               |
| Next Research Gate | `New data wave / Discovery Engine v2` |

## 目录结构

```text
nev_apeal/
├── README.md
├── data/
│   ├── source.sav
│   └── questionnaire_map.json
├── contracts/
│   └── signal_contract.json
├── analysis/
│   ├── _common.py
│   ├── regress.py
│   ├── nonlinear.py
│   ├── segment.py
│   ├── drilldown.py
│   └── ...
├── research/
│   ├── engine.py
│   ├── topic_tournament.md
│   └── runs/
│       ├── topic_x/
│       ├── charging_lifestyle/
│       ├── oem_traditional_gap/
│       ├── expectation_calibration/
│       └── mileage_experience_lifecycle/
├── scratch/
│   ├── signal_scan.py
│   ├── discovery/
│   └── terminal_t9_t10.py
└── reports/
    ├── signal_board.md
    ├── final_tournament_10_topics.md
    ├── from_parameters_to_experience_v4.md
    └── from_parameters_to_experience_topic_deck.md
```

## 数据与口径

- 数据源：`data/source.sav`
- 样本量：9,937 行，370 列
- 权重：`APEAL_WT`
- 核心指标：`APEAL_Index`
- 研究性质：车主横截面、自报体验、观察性分析
- 不能把横截面相关直接写成因果、纵向趋势或产品质量衰减

运行命令默认从仓库根目录执行：

```bash
cd /Users/zihao_/Documents/github/mashang-service/nev_apeal
PYTHONPATH=. ../.venv/bin/python <script.py>
```

## Discovery Engine v1

Discovery Engine v1 已阶段性冻结，采用：

```text
多 Scanner
    ↓
Signal Contract
    ↓
Signal Board
    ↓
Candidate Allocation
    ↓
Topic Qualification
    ↓
Tournament
```

### Analysis Types

| 类型                    | 角色                                     | 默认结果                        |
| ----------------------- | ---------------------------------------- | ------------------------------- |
| `main_effect`           | Round 1 宽扫描，建立优先级               | Screening Signal                |
| `expectation_wow`       | 预期兑现/失望机制                        | Candidate，需 item 下钻         |
| `nonlinear_pattern`     | 台阶、阈值、生命周期结构                 | Candidate，需稳健性与归因       |
| `segment_discriminator` | 发现异质性和 moderator 线索              | Validation Queue                |
| `interaction`           | 已有 parent Signal 的受控 moderator 检验 | 默认 refinement，不自动建 Topic |

Round 1 的 executable registry 为 **25 axes**。历史文档中的“26 axes”是计数错误，冻结版本以实际 registry 和 Signal Board 明细为准。

Interaction 规则：

- 不执行全量 O(p²)
- 每个 exposure contrast cell 原始 `n≥100`
- 至少 3 个可估计 segment
- 必须报告 interaction block、HC1 covariance、BH-FDR q-value 和业务 effect size
- segment spread 只是异质性线索，不是 interaction 证据
- 显著 interaction 默认作为 parent Topic refinement，不自动生成新 Candidate/Topic

相关文档：

- `reports/discovery_engine_v1_freeze.md`
- `reports/discovery_engine_v1_replay.md`
- `reports/discovery_engine_retrospective_round1_round2.md`
- `contracts/signal_contract.json`

## Topic 状态

| ID  | Topic                                    | 状态                 | 角色                        |
| --- | ---------------------------------------- | -------------------- | --------------------------- |
| T1  | Purchase Mission｜可感知升级价值         | **READY / Champion** | Production Topic            |
| T2  | Age / Generation｜世代体验谱系           | READY                | Supporting context          |
| T3  | Income｜收入非线性与舒适短板             | READY                | Supporting context          |
| T4  | Price Band｜中端体验断层                 | READY                | Boundary finding            |
| T5  | Configuration｜配置是载体，不是价值      | READY                | T1 supporting method        |
| T6  | BEV / PHEV｜技术路线差异                 | INCONCLUSIVE         | 不进入主叙事                |
| T7  | Charging Lifestyle｜补能生活方式分群     | READY                | Supporting insight          |
| T8  | OEM Experience Gap｜品牌差距被结构吸收   | READY                | Falsification boundary      |
| T9  | Expectation Calibration｜补能预期兑现    | READY                | Strongest secondary insight |
| T10 | Mileage Experience Lifecycle｜里程非线性 | INCONCLUSIVE         | 研究边界，不写成质量衰减    |

最终 Tournament 使用五个报告价值维度：

1. Evidence strength
2. Mechanism depth
3. Novelty
4. Business actionability
5. Narrative power

最终 Champion 是 T1，不按最小 p-value 或最大 effect size 选择。

## 主要交付物

### Champion 报告

- `reports/from_parameters_to_experience_v4.md`：完整 Champion-led Topic Report
- `reports/from_parameters_to_experience_topic_deck.md`：10 页 Topic Deck

Deck 结构：

```text
Cover
→ Executive Thesis
→ Hero Finding
→ Why：驾驶 / Item
→ Feature ≠ Value
→ Expectation Calibration
→ Price Boundary
→ OEM Design Framework
→ Evidence Boundaries
→ Takeaway
```

### Tournament 与研究治理

- `reports/final_tournament_10_topics.md`：10 Topic Final Tournament
- `reports/signal_to_topic_qualification_round2.md`：Signal → Candidate → Topic Qualification
- `reports/interaction_discovery_gate_review.md`：Interaction Gate
- `reports/interaction_pilot_round1.md`：Interaction Pilot 终局
- `research/topic_tournament.md`：Topic、Run、Finalist 映射与最终排序
- `reports/signal_board.md`：Signal Board 与 Discovery 记录

## Research Run 格式

每个 Topic Run 通常包含：

```text
research/runs/<topic>/
├── state.yaml
├── hypotheses.yaml
├── queue.yaml
└── evidence.jsonl
```

`state.yaml` 记录 terminal status、confidence、mechanism depth 和 stop reason；`evidence.jsonl` 记录带有 `id`、`relation`、`targets`、`parents` 和分析结果的证据链。

终局状态包括：

- `ready`
- `rejected`
- `inconclusive`
- `insufficient_coverage`

## 复现 Discovery

### Round 2 controlled scanners

```bash
PYTHONPATH=. ../.venv/bin/python scratch/discovery/run_controlled_discovery.py
```

输出：

```text
scratch/discovery/_signals_round2.json
```

### Interaction Pilot

```bash
PYTHONPATH=. ../.venv/bin/python scratch/discovery/interaction_scan.py
```

当前 `SEGMENT_DP` Pilot 因 cell coverage 不足，9 个 tests 均为 `INSUFFICIENT_COVERAGE`，没有产生新的 interaction Topic。

### v1 Replay

```bash
PYTHONPATH=. ../.venv/bin/python scratch/discovery/replay_engine_v1.py
```

输出目录：

```text
scratch/discovery/replay_v1/replay_results.json
```

该 replay 验证同一数据 snapshot 的可复现性，不等于跨数据 wave 的泛化验证。新数据到来后应保持 v1 规则原样重跑，不在 replay 过程中调参追随结果。

## 当前工作边界

研究阶段已在 T1 Champion 处阶段性停止。当前任务是 insight communication 和正式 PPT 产出，不继续扩张 Topic 或无边界执行 Interaction Discovery。

如需重启研究，应先明确：

1. 新数据 wave 或新的数据来源；
2. 是否仍使用 Discovery Engine v1；
3. 若修改 registry、Gate 或预算规则，应建立 `discovery_engine_v2`；
4. 新结果必须重新经过 Signal Contract、Qualification 和 Tournament。

---

_Raccoon Research · 用数据、AI 和一点点常识，研究复杂世界。_
