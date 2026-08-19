# Discovery Engine Retrospective｜Round 1 + Round 2

**日期**：2026-08-19  
**范围**：从 25 轴 main-effect 扫描到多 Analysis Type Discovery、Candidate Allocation、T9/T10 terminal 和 Interaction Pilot。  
**数据**：`data/source.sav`，9,937 行，权重 `APEAL_WT`。  
**核心判断**：Discovery Engine 已经证明“受控扩池”有效，但也证明了 Interaction 不能由 segment spread 直接推导，必须以 cell coverage 和正式 interaction block 作为独立 Gate。

---

## 1. Executive Verdict

### Engine 是否有效？

**有效，但不是因为产生了很多显著结果，而是因为能把显著结果正确分流。**

- Round 1 用 main effect 做宽扫描，快速从 25 个分析轴中筛出 4 个 Candidate。
- Round 2 把比较单位从“变量”升级为“Signal”，用三类受控 scanner 产生 10 条结构化 Signal。
- T9 通过 item 下钻成为 `READY`。
- T10 证明非线性存在，但因机制和归因不足以 `READY`，以 `INCONCLUSIVE` terminal 结束。
- Interaction Pilot 没有因为 spread 很大就强行制造 Candidate；9 个 tests 全部被 cell-support gate 拦截。

### 最终漏斗

```text
Round 1: 25 axes → 4 Candidates → 2 activated Topics → 2 READY Finalists

Round 2: 10 Signals → 4 mechanism clusters
         → 2 Candidates → T9 READY + T10 INCONCLUSIVE
         → 3 discriminator queues
         → 9 Interaction tests → 0 qualified interaction Signals
```

**最终结论：** 当前架构值得保留和继续使用；但下一阶段应优先优化 moderator coverage 和预注册聚合，而不是扩大变量池或恢复全量 O(p²)。

---

## 2. Round 1 Retrospective

### 2.1 Role

Round 1 的任务不是直接发现 Topic，而是做低成本、宽覆盖的 signal scan：

```text
25 variables / axes × 1 main_effect analysis type
```

输出是加权横截面 gap + 初步 confounder screening，作用是建立候选优先级，不承担机制证明。

### 2.2 Funnel Performance

| 层级 | 数量 | 转化 |
|---|---:|---:|
| 扫描轴 | 25 | 100% |
| Confounder 初筛后 Candidate | 4 | 15% |
| 激活主研究 | 2 | 50% |
| READY Finalist | 2 | 100% of activated |

进入 Candidate 的轴主要是：

- `NEV_08` 快充频率：后续成为 T7 Charging Lifestyle
- `ORIGIN3_DP` OEM 来源结构：后续成为 T8 OEM Experience Gap
- `NEV_12` 累计里程：保留为 C3，等待 nonlinear 工具
- `NEV_11C` 家庭/个人使用场景：仅保留观察位

### 2.3 What Worked

1. **宽扫描截断有效。** 教育/职业与既有收入主题重叠，年龄与既有世代主题重叠，地理变量机制弱；这些没有被错误升级为深度 Topic。
2. **Signal Board 排名对预算有帮助。** T7/T8 都产生 READY 结果；T8 的价值在于证伪品牌级残余，而不是支持品牌差距。
3. **残余判据优于机械升级。** T7 控制后，NEV_12 仍保留独立非线性残差，因此没有被标记为 ABSORBED；NEV_11C 因只有单个小格存活而留在观察位。

### 2.4 Round 1 Limitation

- main effect gap 只能回答“哪里有差异”，不能回答“差异是什么结构”。
- 低门槛扫描容易把变量差异、机制差异和 segment heterogeneity 混在一起。
- `25 axes` 适合作为 Discovery 宽入口，不应继续作为 Tournament 的最小比较单位。

Round 1 的正确沉淀不是扩大 main-effect 变量池，而是引入多个 Analysis Type。

---

## 3. Round 2 Retrospective

### 3.1 Architecture Change

```text
多 Scanner
    ↓
统一 Signal Contract
    ↓
Signal Board
    ↓
Signal Clustering
    ↓
Candidate Allocation
    ↓
Topic Qualification / Validation Queue
```

Signal Contract 将最小比较单位从变量改为 Signal，允许同一变量产生不同结构：main effect、expectation wow、nonlinear、discriminator、interaction。

### 3.2 Output by Analysis Type

| Analysis Type | 输出 | 价值 | 终局 |
|---|---:|---|---|
| `expectation_wow` | 6 Signals | 发现“预期兑现”结构；4 条核心 Signal + 2 条低覆盖 delight 描述 | C7 → T9 READY |
| `nonlinear_pattern` | 1 Signal | 识别 NEV_12 的里程峰值与回落，避免线性假设 | C8 → T10 INCONCLUSIVE |
| `segment_discriminator` | 3 Signals | 发现 where/for-whom 线索，给 Interaction 提供 parent question | 进入 validation queue |
| `interaction` | 9 tests | 正式检验 moderator 是否调节 parent effect | 0 qualified；`INSUFFICIENT_COVERAGE` |

### 3.3 Signal Clustering and Allocation

10 Signals 被归并为 4 个机制簇：

1. 补能预期校准核心 Signal：T7 行为分群之外的新机制。
2. 补能预期 delight 描述：缺失较高，作为 T9 线索，不独立成题。
3. 里程体验生命周期：与 T7 不同，保留为 T10 qualification。
4. 车型结构段异质性：回答“在哪些 segment 更强”，不自动成为新 Topic。

这一步是 Round 2 最重要的机制进步：**变量被合并或拆分的依据不再是变量名，而是机制结构和增量解释。**

### 3.4 Terminal Outcomes

#### T9 Expectation Calibration

- 两个 exposure 同时进入 FULL 控制后仍独立显著。
- 续航 Better 对 APEAL `+53.4`，充电时长 Better 对 APEAL `+71.1`。
- 结果落到充电便利、状态可读、整体充电体验和续航 item。
- 状态：`READY`。
- 边界：仍是横截面、自报预期与体验评价的稳定关联，不宣称宣传承诺的因果效果。

#### T10 Mileage Experience Lifecycle

- `NEV_12` 非线性检验 `F=10.51, p<0.001`。
- AFUEL 模块和 `AFUEL_R_01` 在较长里程段回落。
- APEAL 总体及多数模块没有形成足够稳定的跨模块机制。
- 状态：`INCONCLUSIVE`。
- 正确结论是“里程非线性存在，但不能直接写成产品质量衰减”。

#### Interaction Pilot

- 9 个预注册 tests，首个 moderator 为 `SEGMENT_DP`。
- 严格要求 exposure 两侧各自 `n≥100`，且至少 3 个 segment 可估计。
- 所有 tests 在 cell-support gate 被拦截，未进入正式 interaction block qualification。
- 没有把 segment spread 当成 interaction evidence，没有降低样本门槛，没有新增 Candidate/Topic。

---

## 4. What the Engine Learned

### 4.1 Analysis Type 是不同的研究角色

Analysis Type 不是并列的统计工具，而是不同预算阶段的研究角色：

| Role | 适合回答 | 不适合回答 |
|---|---|---|
| `main_effect` | 哪些轴值得进入候选池？ | 机制、调节关系、因果 |
| `expectation_wow` | 预期兑现/失望是否形成奖惩结构？ | 直接证明宣传因果 |
| `nonlinear_pattern` | 是否存在台阶、峰值、饱和或生命周期结构？ | 把横截面梯度直接解释为质量衰减 |
| `segment_discriminator` | 效应可能对谁/在哪些结构段更强？ | 正式证明 interaction |
| `interaction` | moderator 是否正式改变 parent effect？ | 从全变量笛卡尔积中淘金 |

### 4.2 Negative Results Are Budget Results

- T8 证明品牌级残余不存在，仍是有效预算使用。
- T10 阻止了“非线性 = 质量衰减”的漂亮叙事。
- Interaction Pilot 阻止了“spread = interaction”的统计越界。

Discovery Engine 的产出不只是 READY Topics，还包括被正确关闭的错误叙事。

### 4.3 Coverage Is a First-Class Gate

Round 2 最明确的新认识是：

> 一个 interaction 线索即使 spread 很大、全样本 p-value 看起来显著，只要 moderator cell 不支持，就没有资格进入正式 interaction evidence。

因此 coverage 不是报告末尾的 caveat，而是 Candidate Allocation 之前的硬 Gate。

---

## 5. Final Analysis Type Role / Gate / Budget Decision

### 5.1 Role Decision

| Analysis Type | Final Role | Default Output |
|---|---|---|
| `main_effect` | Round 1 breadth scanner；低成本建立 Signal Board | Signal，不直接建 Topic |
| `expectation_wow` | 机制 scanner；优先发现预期兑现/失望结构 | Candidate，需 item qualification |
| `nonlinear_pattern` | 结构 scanner；识别阈值、台阶和生命周期 | Candidate，需稳健性和归因 qualification |
| `segment_discriminator` | 线索 scanner；定位 heterogeneity 和 moderator 候选 | Validation Queue，不是 interaction evidence |
| `interaction` | confirmatory pilot；只检验已有 parent Signal 的 moderator hypothesis | Refinement evidence；极少数情况下才 Candidate |

### 5.2 Gate Decision

所有新 Signal 统一经过以下 Gate：

1. **Registration Gate**：exposure、moderator、outcome、controls 和业务问题预先登记。
2. **Coverage Gate**：每个 interaction cell 原始 `n≥100`；至少 3 个可估计 cells/segments。
3. **Inference Gate**：正式模型必须报告 interaction block、HC1 covariance 和 FDR/q-value。
4. **Business Gate**：完整控制后 effect size 仍超过预先设定的业务阈值。
5. **Mechanism Gate**：必须产生可解释的“对谁/在哪种结构下成立”机制。
6. **Incremental Gate**：相对于 parent Topic 有增量解释；否则只标记 `REFINES`。
7. **Tournament Gate**：只有通过上述条件的 Signal 才能进入 Candidate Allocation；没有自动晋级。

### 5.3 Budget Decision

| 阶段 | 预算政策 | 当前决定 |
|---|---|---|
| Round 1 main effect | 宽覆盖、低成本、只做优先级 | 保留；不继续无边界扩展变量池 |
| Round 2 controlled scanners | 每类先登记 exposure，再按机制簇分配 | 保留；T9 READY，T10 terminal INCONCLUSIVE |
| Segment discriminator | 小预算、只做 moderator 线索 | 保留在 validation queue |
| Interaction Pilot | 严格预注册、cell gate、最多 12 tests | 当前 `SEGMENT_DP` 队列暂停 |
| 下一次 Interaction | 只有预先聚合 segment 或换到 coverage 更充分的 moderator 才重开 | 需重新 Gate；不自动追加预算 |

### Final Budget Rule

**预算跟随“新机制增量”，不跟随“显著性数量”。**

- 有 parent signal、覆盖充分、正式 interaction 成立，但只是强化 T7/T9/T10：进入 refinement，不新增 Topic。
- 有 parent signal、moderator 机制清晰、对 parent 有增量解释：才允许 Candidate Allocation。
- 只有 spread、单格显著、低 coverage 或重复主效应：不分配新 Topic 预算。

---

## 6. Next Operating State

### 保留

- Multi Scanner → Signal Contract → Signal Board → Candidate Allocation → Qualification。
- Signal 作为 Tournament 最小比较单位。
- T9 的 READY 机制和 T10 的 INCONCLUSIVE 边界。
- Interaction 的受控 Pilot 角色。

### 暂停

- 当前 `SEGMENT_DP` interaction queue。
- 全量 O(p²) 搜索。
- 从 segment spread 直接创建 Candidate/Topic。

### 允许重开条件

1. 预先定义 `SEGMENT_DP` 合并规则并重新计算 cell coverage；或
2. 选择已有业务定义且 cell 支持充分的 moderator，如价格带或豪华定位；或
3. 获得新数据批次，使当前 exposure × `SEGMENT_DP` 的两侧 cell 达到门槛。

**Round 1 + Round 2 的最终贡献，不是把 Discovery 变成更大的搜索器，而是把它变成一个知道何时扩张、何时停止、何时不应相信漂亮数字的研究预算系统。**
