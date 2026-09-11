# Run 001 — 首次 Evidence → Issue → Pattern → Finding

## 元数据

| 项目     | 内容                                                                                                                        |
| -------- | --------------------------------------------------------------------------------------------------------------------------- |
| Run ID   | `run_001`                                                                                                                   |
| 执行日期 | 2026-09-11                                                                                                                  |
| 方法     | `workflow/issue_discovery.md`（发现）+ `workflow/issue_review.md`（评审门禁）+ `workflow/convergence.md`（统计收敛）        |
| 数据源   | `/Users/zihao_/Documents/coding/dataset/original/L6 M2_LS6 M3 产品专家门店支持信息收集汇总_数据表_表格.csv`（仓库外，只读） |
| 样本     | 9 条有效记录，6 家门店，7 位产品专家（以 evidence 实际派生为准）                                                            |
| 时间范围 | `08/29` – `09/13`（3 个原始支持时间区间）                                                                                   |
| 评审     | 30 个 issue、15 个 pattern 全部 `confirmed`；finding 全部 `ready`                                                           |
| 执行者   | opencode-agent                                                                                                              |

> 说明：专家数以 `convergence.json` 从 evidence 派生为准。
> 上一版手写的「6 位」与 evidence 实际（7 位）不一致，正是 V0.2 用 Convergence 消除的双份事实漂移。

## 产出规模

| 层级        | 数量 | 文件                                                          |
| ----------- | ---- | ------------------------------------------------------------- |
| Evidence    | 55   | `evidence.jsonl`                                              |
| Issue       | 30   | `issues.json`                                                 |
| Pattern     | 15   | `patterns.json`                                               |
| Convergence | 15   | `convergence.json`（由 `scripts/derive_convergence.py` 派生） |
| Finding     | 12   | `findings.json`                                               |

校验：结构 / enum / 交叉引用 / 可追溯性 **0 error 0 warning**；55 条 evidence 全部被 issue 引用，
30 个 issue 全部归入 pattern，15 个 pattern 全部有 convergence 且 `pattern_key` 已登记。

## 分布

**Issue 严重度**：blocker 1 · high 5 · medium 17 · low 7

**Issue 业务信号**：complaint 13 · feature_request 8 · positive_signal 3 · purchase_blocker 2 · competitive_gap 2 · operational 1 · other 1

**Finding 优先级**：P1 3 · P2 5 · P3 4

**Convergence recurrence（派生）**：isolated 6 · repeated 4 · systemic 5

**Convergence evidence_strength（派生）**：weak 6 · moderate 4 · strong 5

## 主要发现

### P1

| ID       | 结论                                             | 证据强度 / 复现       |
| -------- | ------------------------------------------------ | --------------------- |
| FND-0002 | 内饰豪华感与质感不足是跨车型、跨门店的系统性问题 | strong · 5 店 4 车型  |
| FND-0003 | 配置减配感知削弱产品价值感                       | moderate · 2 店跨车型 |
| FND-0004 | 售后服务与智驾可信度是购前主要顾虑               | moderate · 2 店       |

### P2

| ID       | 结论                                               |
| -------- | -------------------------------------------------- |
| FND-0001 | 椭圆方向盘存在视线遮挡与拒购风险（单店，待扩样）   |
| FND-0005 | 储物与后排人体工程存在场景化痛点                   |
| FND-0006 | 竞品对标暴露明确的便利配置差距与设计偏好           |
| FND-0007 | 品牌认知与门店渠道吸引力约束销售                   |
| FND-0008 | 内饰锐角存在磕碰与划伤安全风险（按安全项单列复核） |

### P3

| ID       | 结论                                                       |
| -------- | ---------------------------------------------------------- |
| FND-0009 | 智能座舱语音与 NVH 细节需优化                              |
| FND-0010 | 驾驶卖点传达受损（后轮转向/线控不可试驾）                  |
| FND-0011 | 已验证优势项（雨天智驾、LS8 人群适配、门店服务）应保留放大 |
| FND-0012 | 用户观望等待新款影响短期转化节奏                           |

## 值得单独关注

- **椭圆方向盘（PAT-0001 / ISS-0001）**：严重度按用户原话为 `blocker`（明确拒购风险），但仅 1 店 2 条证据，证据强度 `weak`，按 `issue_review.md` 的 P0/P1 门槛只能列 **P2**，需扩样验证。这是评审纪律优先于直觉优先的示例。
- **内饰锐角（PAT-0004 / ISS-0007）**：涉及人身磕碰/划伤，同理受证据宽度限制列 P2，但在报告中标记为安全项单独复核。
- **运营信号与产品问题分离**：品牌认知、竞品分流、观望等归入 PAT-0013/PAT-0014，不和产品 issue 混计。
- **V0.2 派生复现层级重算**：改用 `workflow/convergence.md` 冻结规则后，以下 pattern 由手写的
  `repeated` 变为派生的 `systemic`（≥3 城市+门店且跨车型或跨支持时间区间）：
  PAT-0002、PAT-0011、PAT-0013、PAT-0015。这是规则优先于主观判断的结果，不是数据变化。
  其余 11 个 pattern 的 `recurrence` / `evidence_strength` 与手写一致。

## 受控词表变更

本次数据出现 **LS7**（record 5，售后负面口碑），原 `series` enum 不含该值。按 `workflow/issue_discovery.md`「新增词表值前先在 schema 登记」的规则，已将 `LS7` 加入四个 schema 的 `series` enum（finding schema 无 series 字段，未改）。

## 边界与纪律

- 样本为**定性、自报、非随机门店样本**，结论用于发现问题与形成假设，**不用于估计总体比例**。
- 复现层级不再主观标注：`recurrence` / `evidence_strength` 由 `workflow/convergence.md`
  的冻结规则从 evidence 派生（单店 isolated；≥2 店 repeated；≥3 店且跨车型/跨时间 systemic）。
- 引用均保留门店与时间上下文；`stated intent`（口头意向）未等同于实际锁单/退订行为。
- 合规：原始 CSV 与配图未复制进仓库。

## 产物

```text
runs/run_001/
├── run.json           运行元数据（study_year=2026）
├── evidence.jsonl     55 条最小可追溯观察
├── issues.json        30 个问题
├── patterns.json      15 个语义模式 / 机制假设
├── convergence.json   15 个统计快照（Attribution + Counts + Temporal）
├── findings.json      12 条结论（引用 pattern + convergence）
└── run.md             本报告
```

## 下一步建议

1. 扩充门店/数据 wave，重点验证 PAT-0001（方向盘）、PAT-0004（锐角）的普遍性；新 run 触发 Temporal Comparison。
2. 为 PAT-0008（减配感知）核对配置表，区分「感知」与「事实」。
3. 将本 run 固化为 `eval/cases/` 的回归输入，检验抽取/归并/评审/收敛规则的稳定性。
4. 用 `scripts/derive_convergence.py` 作为后续 run 的固定派生入口，避免再次手写统计。
