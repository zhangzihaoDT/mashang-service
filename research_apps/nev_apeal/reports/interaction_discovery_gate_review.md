# Interaction Discovery Gate Review
## 是否正式开放第四类 Analysis Type

**日期**：2026-08-19  
**评估对象**：`interaction_scan`  
**前置结果**：Expectation→Wow、Nonlinear Pattern、Segment Discriminator 已完成第一轮受控扩池；Interaction Controlled Pilot 已执行，但 `SEGMENT_DP` 因 cell coverage 不足未产生正式证据。

---

## 1. Gate Input

| 指标 | 结果 | 判断 |
|---|---:|---|
| 已执行 Analysis Type | 3 | 达到开启第四类的最小前置条件 |
| Discovery Signals | 10 | 不是单一变量扫描结果 |
| 机制簇 | 4 | 已能从变量层上升到机制层 |
| 新 Candidate | 2 | T9 READY；T10 INCONCLUSIVE |
| 既有 Topic validation queue | 2 | discriminator 没有被误报为新 Topic |
| Signal → Candidate 转化 | 2/10 | 有效但不宽松，未出现大规模统计淘金 |
| READY 新 Topic | 1/10 | 有真实预算回报，但仍需控制搜索规模 |

### 结论

**Gate 通过，但只批准“受控 Interaction Pilot”，不批准全量 O(p²) 淘金。**

前三类已经证明两件事：

1. 同一个变量可以通过不同 analysis type 产生不同结构的 Signal。
2. Segment Discriminator 已经发现足以值得正式检验的异质性，但当前 spread 不是正式 interaction 证据。

因此继续关闭 Interaction 会把已经出现的机制线索停在“分层描述”阶段；直接开放全量 interaction 又会破坏当前漏斗的预算纪律。

---

## 2. Why Open Now

### 2.1 已有 parent signal，而不是凭空找交互

Interaction 候选必须来自已有 Signal 的明确问题：

| Parent Signal | 候选 moderator | 当前线索 | Interaction 问题 |
|---|---|---:|---|
| `segment_discriminator_nev_08_segment_dp` | `SEGMENT_DP` | within-segment spread 84.5 | 快充生活方式差异是否集中在特定车型结构段？ |
| `expectation_wow_01/02` | `SEGMENT_DP` | spread 76.0 | 续航预期兑现是否只对部分车型结构段有效？ |
| `expectation_wow_04/05` | `SEGMENT_DP` | spread 118.1 | 充电时长预期兑现是否存在结构段调节？ |
| `nonlinear_pattern_01` | `SEGMENT_DP` | 里程非线性已成立 | 里程回落是否在特定结构段才出现？ |

这些是“已观察到的异质性 → 正式检验”，不是任意两列相乘。

### 2.2 前三类已完成搜索空间的降维

- `expectation_wow` 将候选限制在预期违背结构和少数补能 exposure。
- `nonlinear_pattern` 只对登记的连续/有序 exposure 做业务分箱。
- `segment_discriminator` 只对预注册 exposure × `SEGMENT_DP` 队列做组内对比。

Interaction 应继承同一原则：**先由 parent Signal 提供 exposure，再由机制问题提供 moderator。**

---

## 3. Scope Approved for Pilot

### Exposure registry

第一轮只允许：

- `NEV_08`
- `AFUEL_D_06`
- `ACHAR_D_05`
- `NEV_12`

不得把 370 列全部纳入 interaction 候选池。

### Moderator registry

第一轮只允许：

- `SEGMENT_DP`：车型结构/技术路线代理
- `CN_YNV_07`：价格结构
- `PREMMAKE_DP`：豪华/大众定位
- `SUPER_SEGMENT_DP`：能源结构

优先级顺序：`SEGMENT_DP` → `CN_YNV_07` → `PREMMAKE_DP`。`SUPER_SEGMENT_DP` 只在已有结果明确需要时使用，避免与结构变量重复。

### Outcome registry

- `APEAL_Index`
- `AFUEL_Index`
- `ACHAR_index`

不得在第一轮 interaction 同时扩展到所有模块和全部 item。

### Maximum test budget

第一轮最多 **12 个预注册 interaction tests**：

- 4 exposures × 1 primary moderator = 4
- 其中 T9 两个 exposure 可分别测试 APEAL/补能模块 = 4
- T10 NEV_12 可增加一个结构稳健性 outcome = 2
- 2 个 reserve tests，仅在前面结果出现明确方向时启用

超过 12 个测试必须重新过 Gate，不得通过临时增加 moderator 扩大搜索空间。

---

## 4. Qualification Rules

Interaction Signal 只有同时满足以下条件，才能进入 Candidate Allocation：

1. Parent exposure 已有 `Signal Contract`，且不是纯描述性 delight Signal。
2. 每个 interaction cell 原始 n≥100；低于该门槛只做观察，不进入 Tournament。
3. WLS interaction term 的方向与 segment discriminator 线索一致。
4. 通过 HC1 稳健标准误，并报告多重检验校正后的 q-value。
5. 加入完整结构/人口控制后仍有业务意义的 effect size，不以 p-value 单独晋级。
6. 至少有一个可解释的 moderator 机制，能回答“对谁/在哪种产品结构下成立”。
7. 必须与 parent Topic 做增量解释；若只是重现 T7/T9 主效应，标记为 `REFINES`，不新建 Topic。

### Stop / reject rules

- 仅有单个小 cell 显著：`OBSERVATION`。
- 方向在相邻 segment 间随机翻转：`FRAGILE`。
- 加入 moderator 后 parent effect 消失且无清晰机制：`ABSORBED`。
- 多重检验后无稳定结果：关闭本轮 Interaction，不继续淘金。

---

## 5. Allocation Decision

| 决策项 | 结果 |
|---|---|
| 是否开放第四类 Analysis Type | **是** |
| 开放形态 | **Controlled Interaction Pilot** |
| 是否运行全量 O(p²) | **否** |
| 首个 moderator | `SEGMENT_DP` |
| 首批 exposure | `NEV_08`, `AFUEL_D_06`, `ACHAR_D_05`, `NEV_12` |
| 是否新建 Topic | 只有通过 Qualification 后才允许；默认先进入 T7/T9/T10 validation queue |
| 下一步 | 建立 `interaction_scan.py`，按 12-test registry 执行 |

**最终判断：** 前三类受控扩池已经证明开启 Interaction 的研究价值和必要性，但还没有证明可以承受无约束的交互搜索。因此本轮批准的是一个有 parent Signal、有 moderator registry、有测试上限、有 FDR 和 cell-size 门槛的第四类 Pilot。
