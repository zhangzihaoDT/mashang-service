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
│   ├── signal_contract.json
│   ├── slide_contract.json
│   ├── render_qa_contract.json
│   └── golden_case_v1.json
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
│   ├── validate_slide_contract.py
│   ├── render_qa.py
│   ├── replay_golden_case.py
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
- `reports/from_parameters_to_experience_topic_deck.md`：10 页 Topic Deck（含每页 Slide Contract metadata block）

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

### Slide Contract（Production 机制）

Deck 每页标题下携带一个 YAML **metadata block**，作为 Research → Production 的 canonical presentation contract，供人读与 PPT Generator 读取。schema 定义在 `contracts/slide_contract.json`，每页包含四层信息：

```text
① Narrative Layer     slide_role / question / answer / takeaway / next
② Claim Layer         claim_level / hero_message
③ Evidence Layer      evidence(topic, run, ids, sample_n, estimator, weight, controls)
④ Governance Layer    boundary / appendix_ref / provenance
```

- `slide_role`：OPENING / THESIS / EVIDENCE / MECHANISM / CONCEPTUAL_BRIDGE / BOUNDARY / FRAMEWORK / CLOSING
- `claim_level`：OBSERVATION / CONTROLLED_FINDING / MECHANISM_EVIDENCE / MECHANISM_INTERPRETATION / CONCEPTUAL_BRIDGE / BOUNDARY / MANAGERIAL_SYNTHESIS / RESEARCH_BOUNDARY
- `appendix_ref`：指向文件尾 Appendix Registry（A1–A7），用于追问层取证

### Production 链路（Semantic Lint → Render QA）

目标是**第一次就完整输出**，把语义/视觉错误在生成机制内阻止，而不是人工发现后返工。

```text
deck.md（Slide Contract metadata）
  ↓
validate_slide_contract.py      ← 结构 + semantic lint
  ↓
resolve evidence / provenance   ← evidence.jsonl 交叉验证
  ↓
generate PPT                    ← brand_palette.json + visual_identity.md 约束
  ↓
render all slides to PNG/HTML
  ↓
render_qa.py                    ← 视觉 QA 门
  ↓
PASS → deliver ｜ FAIL → regenerate
```

#### 第 1 层：Semantic Lint（`scratch/validate_slide_contract.py`）

在结构校验之外做跨字段一致性检查，阻止"YAML 合法但 PPT 语义画错"：

| 规则 | 说明 |
|---|---|
| evidence.ids 真实性 | 必须存在于对应 run 的 `evidence.jsonl` |
| signal_ids 真实性 | 必须存在于 `contract.signal_sources` 指定的 signal 记录（`scratch/discovery/_signals_*.json` / `signal_board.md`） |
| OBSERVATION 无因果语言 | question/answer/hero 不得出现"导致/造成/causes/leads to" |
| controlled_anchor 有效 | 必须指向 CONTROLLED_FINDING / MECHANISM_EVIDENCE 页 |
| 综合页无显著性 hero | MANAGERIAL_SYNTHESIS / CONCEPTUAL_BRIDGE 不得在 hero 出现 p-value / 显著 |
| 边界页不高亮为正向发现 | BOUNDARY / RESEARCH_BOUNDARY 的 highlight 不得暗示"主要正向发现" |
| visual × role 兼容矩阵 | `framework_map` 只能用于 FRAMEWORK / MANAGERIAL_SYNTHESIS 等 |
| before_after 需声明语义 | 必须写 `comparison_semantics`（raw_vs_adjusted / group_a_vs_b），防止画成时间变化 |

规则定义在 `contracts/slide_contract.json` 的 `semantic_rules` / `visual_role_compatibility` / `causal_language`。

```bash
PYTHONPATH=. ../.venv/bin/python scratch/validate_slide_contract.py \
    --deck reports/from_parameters_to_experience_topic_deck.md
PYTHONPATH=. ../.venv/bin/python scratch/validate_slide_contract.py --format json
```

新 Deck 或修改后必须通过（0 error）才能进入渲染。

#### 第 2 层：Render QA（`scratch/render_qa.py`）

对渲染产物（PPT HTML export 或 deck.html 预览）做浏览器内检查，清单定义在 `contracts/render_qa_contract.json`：

| 检查 | 级别 | 捕获的问题 |
|---|---|---|
| 无 console error | error | 脚本错误 |
| 页数 = contract 页数 | error | 10 页被压成 6 页、T9 挤掉 T5/T4 |
| 无元素溢出 / 文字截断 | error | 排版越界 |
| 颜色来自 brand palette | warn | 颜色跑偏 |
| 标题是结论句 | warn | "Page 2" 式标签 |
| 数据页有结构化载体（table/bar/pre/split/flow） | error | 全部退化成 metric cards |
| CONCEPTUAL_BRIDGE 与分析页节奏区分 | warn | 转场页被画成数据页 |
| footer / source / 权重完整 | warn | 来源缺失 |

```bash
PYTHONPATH=. ../.venv/bin/python scratch/render_qa.py \
    --html reports/from_parameters_to_experience_topic_deck.html \
    --deck reports/from_parameters_to_experience_topic_deck.md
```

门禁：任何 `error` 阻止交付；`warn` 进入人工复核清单。

### Golden Case（Production Pipeline v1）

把当前状态冻结为**不可回退的系统能力**。定义在 `contracts/golden_case_v1.json`，固定产物与验收结果：

```text
固定：10 页 deck.md · deck.html · Slide Contract v1.1 · Visual Identity
      Brand Palette · Semantic Lint 预期 · Render QA 预期

验收只看 7 个数：
  slides            = 10
  semantic errors   = 0
  semantic warnings = 0
  evidence refs     > 0 且全部解析
  signal refs       > 0 且全部解析
  render errors     = 0
  render warnings   = 0
```

回归重放（统一入口）：

```bash
make production-golden                       # 仓库根目录
# 或
PYTHONPATH=. ../.venv/bin/python scratch/replay_golden_case.py
```

输出：

```text
Production Golden Case v1
──────────────────────────
Slides               10 / 10   PASS
Semantic errors           0    PASS
Semantic warnings         0    PASS
Evidence refs            13    PASS
Signal refs               2    PASS
Render errors             0    PASS
Render warnings           0    PASS

RESULT: PASS
```

**触发规则**：任何修改以下组件后，必须重放本 Golden Case，PASS 才允许合并——

- `contracts/slide_contract.json` / `contracts/render_qa_contract.json`
- `scratch/validate_slide_contract.py` / `scratch/render_qa.py`
- `reports/from_parameters_to_experience_topic_deck.md` / `.html`
- `~/.config/opencode/assets/brand/visual_identity.md` / `brand_palette.json`
- `.opencode/skills/nev-research/SKILL.md`
- README 的 Production 链路章节

任何 `error` 阻塞合并；`warn` 人工复核后显式放行。

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
