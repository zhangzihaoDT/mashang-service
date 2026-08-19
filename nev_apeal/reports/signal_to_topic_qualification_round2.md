# Signal → Candidate → Topic Qualification
## Round 2 Discovery 预算分配

**日期**：2026-08-19  
**输入**：`scratch/discovery/_signals_round2.json`（10 Signals）  
**数据**：`data/source.sav`，9,937 行，权重 `APEAL_WT`  
**原则**：Tournament 比较 Signal / 机制簇，不比较原始变量；分层 Signal 若不能形成独立机制，不单独激活 Topic。

---

## 1. Funnel

```text
10 Signals
    ↓ mechanism clustering
4 Signal clusters
    ↓ candidate allocation
2 new Candidates + 2 existing-topic validation queues
    ↓ qualification
T9 activated + T10 activated with scoped budget
```

| 层级 | 数量 | 说明 |
|---|---:|---|
| Round 2 Signals | 10 | expectation 6 + nonlinear 1 + segment discriminator 3 |
| Signal clusters | 4 | 按机制归并，不按变量名归并 |
| New Candidates | 2 | C7 预期校准、C8 里程生命周期 |
| Existing-topic queues | 2 | T7 快充生活方式、C7 的结构段异质性 |
| Activated Topics | 2 | T9 / T10，均为 scoped qualification，不等于 READY |

---

## 2. Signal Clustering

| Cluster | Signals | 共同机制 | 与既有 Topic 的关系 | 处理 |
|---|---|---|---|---|
| **C7 补能预期校准** | `expectation_wow_01/02/04/05` | 用户对续航/充电时长的实际体验是否兑现预期，Better 与 Worse 形成近对称奖惩 | 与 T7 的“补能行为方式”不同：T7 是行为暴露，C7 是承诺兑现/预期管理 | **Candidate → T9** |
| C7 delight 描述 | `expectation_wow_03/06` | Better 亚组报告的启动、静谧、加速、辅助驾驶等 delight 项 | 缺失高，只能做机制线索 | T9 内部验证，不独立计题 |
| **C8 里程生命周期** | `nonlinear_pattern_01` | 1k–5k 蜜月峰值，5k 后回落，10k–50k 低谷，非线性衰减 | 不被 T7 吸收；此前控制 NEV08 后仍有独立残差 | **Candidate → T10** |
| T7 / C7 分层异质性 | `segment_discriminator_nev_08_segment_dp`、`segment_discriminator_afuel_d_06_segment_dp`、`segment_discriminator_achar_d_05_segment_dp` | 同一效应在车型结构段内幅度不同 | 是既有机制的 where/for-whom 证据，不是新机制 | Validation Queue |

### 聚类判断

- `expectation_wow` 的四条核心 Signal 不能简单合并为一个变量结果：续航预期与充电时长预期相关但独立存续，属于一个 Topic 下的两个 exposure。
- `NEV_12` 的非线性结构与 T7 方向不同：T7 解释“快充依赖差异”，C8 解释“使用里程后的体验衰减”，不能标记为 ABSORBED。
- 三条 segment discriminator 没有新增 outcome 或产品机制，只说明“在哪些细分段更强”，暂不消耗独立 Topic 预算。

---

## 3. Candidate Allocation

| Candidate | 证据强度 | 机制独立性 | Actionability | 主要风险 | 预算分配 |
|---|---:|---:|---:|---|---|
| **C7 补能预期校准** | 5/5 | 4/5 | 3/5 | 横截面自报；当前只到模块/总体，产品杠杆尚未拆开 | **中预算，先做 T9 scoped qualification** |
| **C8 里程生命周期** | 4/5 | 5/5 | 4/5 | 10k–50k 样本较小；高里程 50k+ 仅 13 人 | **中预算，做 T10 nonlinear + item 下钻** |
| T7 结构段异质性 | 3/5 | 1/5 | 4/5 | 可能只是结构 mix 或 power | 不开新预算，进入 T7 validation queue |
| C7 结构段异质性 | 3/5 | 1/5 | 3/5 | 需要正式 interaction 才能确认 | 不开新 Topic，作为 T9 分层任务 |

---

## 4. Qualification

### T9｜Expectation Calibration

**激活结论：✅ 激活，限定为 scoped qualification。**

**为什么值得投入：**

- APEAL 全量样本中，续航 Better−About 为 `+49.8`，充电时长 Better−About 为 `+51.0`。
- FULL 控制后两类 exposure 仍独立显著：同时建模后，续航 Better `+53.4`、充电时长 Better `+71.1` APEAL points，均 `p<0.001`。
- Worse 方向也存在近对称扣分，初步更像“承诺兑现”而不是只奖励惊喜。
- 与 T7 的行为分群有明确增量：T7 问“用户如何补能”，T9 问“产品承诺是否被体验兑现”。

**Qualification 边界：** 当前只能证明预期校准与体验评价强相关，不能直接证明 OEM 的宣传承诺造成了体验变化。T9 只有在 item/产品属性下钻后才可升级 READY。

**T9 必做验证：**

1. 将 AFUEL_D_06 与 ACHAR_D_05 分别连接到续航、充电速度、充电便利性和跨模块 item。
2. 检验“Better”是否只是高质量车型/品牌的残余 mix。
3. 比较预期校准与 T7 快充依赖的增量解释，避免同一补能体验被重复计价。
4. 使用 `SEGMENT_DP` 做预注册分层，正式 interaction 放在第四阶段。

### T10｜Mileage Experience Lifecycle

**激活结论：✅ 激活，限定为 nonlinear / lifecycle 主题。**

**为什么值得投入：**

- `NEV_12` 分箱范围 `34.5` APEAL points，线性模型与分箱模型增量检验 `F=10.51, p<0.001`。
- 加入能源、价格、豪华/大众、年龄、收入、教育后，非线性仍存在；1k–5k 是峰值，10k–50k 明显回落。
- 该结构与 T7 不同：不是“是否依赖快充”，而是“使用里程增长后体验是否衰减”。
- 具备明确 OEM actionability：首个保有期、软件更新、能耗/补能体验、异响/舒适性与售后触点都可形成验证路径。

**Qualification 边界：** 这是横截面里程梯度，不是纵向同一用户的体验变化；10k–50k 各档样本有限，不能把回落直接命名为产品质量衰减。

**T10 必做验证：**

1. 对 1k–5k、5k–10k、10k–20k、20k–50k 做 item/module 下钻。
2. 排除车龄、车型上市时间和车主结构的替代解释。
3. 复核不同 `SEGMENT_DP` 内是否保留同方向的回落。
4. 不把 `50k+` 13 人小样本作为主叙事证据。

---

## 5. Final Allocation

| Topic | 状态 | 下一步 | 暂不做什么 |
|---|---|---|---|
| **T9 Expectation Calibration** | **READY · terminal** | 预期类型已连接到 item/产品杠杆；与 T7 的增量边界已验证 | 不直接宣称因果或“惊喜营销” |
| **T10 Mileage Experience Lifecycle** | **INCONCLUSIVE · terminal** | nonlinear 信号和 AFUEL/item 回落成立，但跨模块机制与归因不足 | 不把横截面梯度写成质量衰减 |
| T7 segment discriminator | Validation Queue | 正式 interaction | 不新增 T11 |
| T9 segment discriminator | Validation Queue | 分层复核 | 不把 spread 当作交互显著性 |

**最终判断：** Round 2 产生了一个可 READY 的新 Topic（T9）和一个有价值但证据不足以升级的终止 Topic（T10）。T9 的价值在“预期兑现机制”；T10 的价值在确认“里程非线性存在，但不能直接命名为质量衰减”。其余 Signal 负责定位边界，不应继续扩张 Topic 数量。
