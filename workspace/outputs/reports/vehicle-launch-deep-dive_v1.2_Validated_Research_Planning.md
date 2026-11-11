# vehicle-launch-deep-dive v1.2 — Validated Research Planning 交付报告

- 版本：`1.1 → 1.2`
- 日期：2026-11-11
- 定位：把"能自动执行分析"升级为"先判断哪些研究该做、哪些不该做，再执行并验证结论"
- 边界：未修改 `dataset/`、`shared/schema/business_definition.json`、`jobs/`、既有 business_scripts；计算模块全部复用

---

## 一、流程改造

```
研究任务
  → 数据审计（轻量探测 probe_research：样本量 / 字段 / 电量段 / 门店数 / 预售池）
  → 研究计划 ResearchPlan（13 个研究问题，含比较对象、指标、数据依赖、可比性条件、输出物）
  → Gate A 前置核验（PASS / SKIP / BLOCK）
  → 正式计算 build_context（只执行 PASS 的问题）
  → ResearchFindings（每条结论绑定指标、数值、方向、边界）
  → Gate B 结论核验（数值 / 方向 / 一致性）
  → 渲染（消费 Findings，不再内联固定判断）
  → Gate C 报告一致性（标题、关键数字、禁用语）
```

关键点：**Gate A 未通过的研究问题不进入计算链路**。`build_context(..., allowed=...)` 按 Gate A 的 PASS 集合决定是否调用
`compute_same_battery_profile` / `compute_version_gap` / `compute_slice_compares` —— 不是"算完再跳过渲染"，
而是"根本不算"。

---

## 二、ResearchPlan 契约

文件：`workspace/research_scripts/launch_research_plan.py`
落盘：`<table_dir>/research_plan.json`（`plan` + `gate_a` + `findings` + `gate_b` + `gate_c`）

```json
{
  "version": "1.2", "main": "CM3", "benchmarks": ["LS8", "LS9"],
  "as_of": "2026-09-27", "n_days": 5,
  "global_constraints": {"small_gap": true, "gap_values": {"LS8": -34, "LS9": 42},
                         "disable_share_of_gap": true},
  "questions": [{
    "id": "q8b", "title": "同档客群对比", "required": false,
    "compares": ["CM3", "LS8"],
    "metrics": ["segment_share", "segment_profile"],
    "data_deps": ["segment"],
    "comparability": ["主代际与第一个对标都必须有 93kWh 段（该区块只比这一对）",
                      "各侧同档样本 ≥ 30"],
    "outputs": ["table_same_battery"],
    "fallback": "skip_and_record",
    "blocked_by": ["LS8 无 93kWh 段"]
  }],
  "narrative_policy": {"no_preset_verdict": true, "inherit_previous_findings": false}
}
```

| 字段 | 作用 |
|---|---|
| `comparability` | 该问题的可比性前提，Gate A 逐条核对 |
| `data_deps` | 依赖的数据域（locks/presale/segment/seat_field/store/province…） |
| `outputs` | 该问题负责的图表/表格；未 PASS 则整块不渲染 |
| `fallback` | 不可执行时的处置（`skip_and_record`） |
| `global_constraints.disable_share_of_gap` | 差额过小时全局禁用「贡献占比」类指标 |

计划可程序化核验，不是 Prompt 里的自然语言说明。

---

## 三、Gate A 核验规则与结果

| 判定 | 触发条件 | 后果 |
|---|---|---|
| PASS | 数据可得、口径可比、样本达标 | 进入计算 |
| SKIP | 可选专题不可比（缺电量段/缺配置字段/样本不足） | 跳过计算与渲染，写明原因 |
| BLOCK | 关键问题不成立（窗口锁单 < 30、预售池 < 100） | 引擎退出（exit 3），不产生任何结论 |

### CM3 vs LS8 / LS9（as-of 2026-09-27）

| 问题 | 结果 | 依据 |
|---|---|---|
| q1–q8, q9, q10 | PASS（10 项） | 样本、门店、预售池均达标 |
| **q8b 同档客群** | **SKIP** | LS8 无 93kWh 段；LS9 无 93kWh 段 |
| **q8c 座椅拆分** | **SKIP** | CM3 的「座椅」有效值覆盖 0% |
| **q8d 版本缺口** | **SKIP** | 同档前提不成立 |

验证"不成立的问题不进入计算"：CM3 的 `metrics.json` 中 `same_battery = {}`、`version_gap = {}`、
`slice_compares = {}` —— 计算链路确实被跳过，而不是算完丢弃。

### LS8Neo vs CM3 / LS8（as-of 2026-11-09）

| 问题 | 结果 |
|---|---|
| 全部 13 项（含 q8b / q8c / q8d） | **PASS**，无 SKIP、无 BLOCK |

说明新增核验**没有误杀有效分析**：因为同档/版本缺口只比较「主代际 vs 第一个对标」（LS8Neo vs CM3），
两者都有 93kWh 与 76kWh 缺口，条件成立。

---

## 四、ResearchFindings 契约与 Gate B

`compute_findings(ctx)` 生成 5 条结论，每条含：`id / title / body / evidence / numbers / direction / scope`。
标题按数据方向生成，**不再继承任何历史案例措辞**。

### CM3 案例（修复前 vs 修复后）

| 项 | v1.1（修复前） | v1.2（现在） |
|---|---|---|
| 第 1 条标题 | 绝对水平**落后四成**，落后幅度在上市夜就基本定档 | **总量与对标基本持平（99%），差异不在规模** |
| 第 2 条 | 对 LS8「一次性定档」、对 LS9「起点落后叠加每日失速」 | **首日集中度明显更高（82.3% vs 66.2%），后续释放更弱** |
| 第 3 条 | 差额主体是预售池规模（固定判断） | **预售池规模更小 44%，转化率差异相对次要** |
| 报告残留矛盾措辞 | 「落后四成」「全面落后」「持续失速」 | **0 处** |

### LS8Neo 案例（未被误伤，方向仍正确）

| 结论 | 方向 |
|---|---|
| 绝对水平落后，为对标的 58%（差 1,573 单） | behind ✅ |
| 释放节奏与对标接近，首日占比差异不足 3pp | parity ✅ |
| 预售池规模更小 37%，转化率差异相对次要 | mixed ✅ |
| 单店产出低于 38%，网络规模差异（−7%）是次要项 | mixed ✅ |
| 下单链路一致：直锁占比跨代际仅差 6.3pp | mixed ✅ |

Gate B 逐条核对：结论数值 = metrics 数值、方向与 ratio 一致、池/门店数值可对账。

---

## 五、Gate B / Gate C 验证记录

| 案例 | Gate A | Gate B | Gate C |
|---|---|---|---|
| CM3 vs LS8/LS9 | PASS（10 PASS / 3 SKIP） | PASS（5/5 结论核验） | PASS（标题全命中、无禁用语） |
| LS8Neo vs CM3/LS8 | PASS（13 PASS） | PASS（5/5） | PASS |

Gate C 检查项：
1. 每条结论标题必须出现在报告中（防止"结论被算出来但没进报告"）；
2. 关键数字与 findings 绑定值一致；
3. 禁用与数据矛盾的措辞（ratio ≥ 0.9 时禁止"落后四成"；ratio ≥ 1 时禁止"全面落后/持续失速"）。

---

## 六、指标有效性约束（对应问题 3）

| 场景 | v1.1 | v1.2 |
|---|---|---|
| 总差额 +42 单 | 「D1 占总差额 **2179%**」 | 「D1 领先 915 单，D2–D5 净回吐 873 单，最终领先 42 单」 |
| 预售差额分解 | 「解释对 LS8 预售差额的 **864%**」 | 「池规模效应 −1,391 单、转化率效应 +1,230 单（方向相反、部分抵消，净额 −161 单）」 |
| 版本缺口 | 固定写「对标独有的 76kWh 入门档，占差额 3982%」 | 按 `missing_segments` 生成；CM3 场景为「无版本缺口（主代际覆盖对标全部电量段）」 |
| 单店产出方向 | 「单店产出比 LS8 低 −13%」 | 「单店产出高 13%（8.74 vs 7.73 单/店）」 |

规则：`global_constraints.disable_share_of_gap = true`（差额 ≤ 主车累计 5%）时，全局禁用占比类表达，
改用绝对差额叙述；分解类只在分母为"已解释差额"且方向一致时才给百分比。

---

## 七、可复现性

同参数两次运行（CM3 案例）：

| 对象 | 结果 |
|---|---|
| `plan` | 完全一致 |
| `gate_a` | 完全一致 |
| `findings` | 完全一致 |
| `gate_b` | 完全一致 |
| `metrics.json`（排除 `generated_at`） | 完全一致 |

---

## 八、交付物

| 产物 | 路径 |
|---|---|
| 计划与核验模块 | `workspace/research_scripts/launch_research_plan.py`（新增） |
| 引擎改造 | `workspace/research_scripts/launch_deep_dive.py`（probe / Gate A 接线 / 计算门控 / Gate B、C） |
| 渲染层改造 | `workspace/research_scripts/launch_deep_dive_report.py`（findings 消费 / Q1 与经营判断数据化 / 区块门控） |
| Skill | `.opencode/skills/vehicle-launch-deep-dive/SKILL.md`（v1.2 流程）+ `references/method.md`（Gate A 章节） |
| CM3 回归报告 | `workspace/scratch/v12/reports/CM3_上市第5天深度研究.html` |
| LS8Neo 回归报告 | `workspace/scratch/v12_neo/reports/LS8Neo_上市第5天深度研究.html` |
| 计划与核验记录 | 各案例 `tables/launch_deep_dive/<GEN>_D5/research_plan.json` |

---

## 九、已知限制

1. **Gate A 只核验"能不能做"，不核验"值不值得做"**：重要性排序仍由 `compute_narrative` 的启发式规则决定。
2. **SKIP 的粒度到问题级**：例如 q8d 被跳过时，Q6 的区域分析仍然保留，但"省份差额是否由版本缺口造成"这一问不再回答。
3. **结论仍是模板化生成**：5 条 findings 的结构固定（水平/节奏/池/网络/来源），真正的自由叙事（如专题追问）仍由分析者驱动。
4. **Gate C 是文本级兜底**：靠标题匹配与禁用语清单，不能证明语义完全正确；结论与正文的深层一致性仍靠 Gate B 的数值绑定。
5. **数据漂移**：与 v1.0 报告的逐字节比对仍不可行（订单表已刷新），回归以"结构 + 方向 + 禁用语"为准。
