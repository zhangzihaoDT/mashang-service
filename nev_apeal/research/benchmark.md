# Research Agent Benchmark — 跨 Topic 泛化验证

**日期**：2026-08-18
**运行时**：`nev_apeal/` Agentic Analytical Workspace（Iteration 2，未加新功能）
**方法**：同一 Runtime、同一 CLI、同一循环协议，在 5 个性质不同的 Topic 上独立研究。
**数据**：`data/source.sav`（9,937 × 370），权重 `APEAL_WT`。

---

## 1. Topic 设计

| Topic | 检验能力 | 核心变量 |
|---|---|---|
| purchase_mission（baseline） | 已完成 · 对照组 | YPV_01 |
| age_generation | 用户 segmentation | GENERATION2 |
| price_band | 连续变量 / 非线性 | CN_YNV_07 |
| bev_phev | 产品技术路线 | SUPER_SEGMENT_DP |
| config_attribution | 强 confounding 场景 | SCR_SEAT00_04C_R1 |

---

## 2. 每 Topic 研究轨迹与指标

### Topic A · purchase_mission（baseline，V2 运行）
```
信号：增购 APEAL 最高（798.4 vs 783.6/786.6）
→ 生成 2 问（drilldown AEXT / explain_gap）
→ 下钻：AEXT 单题承载，转 ADRV item → 总体驾驶感受+转向手感
→ 纠错：+11.8→+18.3 放大被识别为参照组混淆（非 suppression）
→ 机制 depth 4 → READY
```
| 指标 | 值 |
|---|---|
| 生成 Question | 2 |
| 执行 | 2（AEXT + ADRV drilldown）|
| Reject Hypothesis | 1（suppression H-002）|
| 主动纠错 | 1（参照组陷阱）|
| mechanism_depth | 4 |
| 轮数 | 7 |
| READY | ✅ |

### Topic B · age_generation（segmentation）
```
信号：世代非单调（95~99 811.3 > 80~84 803.6 > Pre80s 774.4），拒答组 732.3
→ derive 误选拒答组为基线 → 主动排除（测量伪影），改有效世代对比
→ 下钻 ADRV：世代差异全谱系，总体驾驶感受主导（Δ-0.50, d=-0.402）
→ confounder：控制价格后 95~99 系数 +37.3(p<0.001) 仍显著，非价格驱动
→ 机制 depth 3 → READY
```
| 指标 | 值 |
|---|---|
| 生成 Question | 2（Q001 被拒：基线为测量伪影）|
| 执行 | 1 有效（ADRV drilldown）|
| Reject Hypothesis | 1（世代差异由价格驱动）|
| 主动纠错 | 1（拒答组排除，measurement boundary）|
| mechanism_depth | 3 |
| 轮数 | 3 |
| READY | ✅ |

### Topic C · price_band（连续/非线性）
```
信号：价格带 APEAL 非线性（15-20万 785.8 → 20-30万 798.0 跳升+12.2 → 30万+ 801.2 饱和+3.2）
→ regress：控制品牌后价格系数 -0.15/万(p=0.47) 不显著 → 效应被品牌结构吸收
→ 非线性无法用线性工具建模 → 假设被拒，机制 depth 1 → REJECTED
```
| 指标 | 值 |
|---|---|
| 生成 Question | 0（Runtime 无分箱工具，未走 derive）|
| 执行 | regress + correlate |
| Reject Hypothesis | 1（价格驱动体验）|
| 主动纠错 | 1（品牌结构吸收识别）|
| mechanism_depth | 1 |
| 轮数 | 2 |
| READY | ❌（rejected）|

### Topic D · bev_phev（技术路线）
```
信号：BEV 领先（APEAL 790.3 vs 786.9），性能 APERF 差最大(+7.2)
→ 下钻 APERF：发动机/电机声音(Δ-0.13,p=0.01)与总体表现显著，动力/平顺不显著 → NVH 机制
→ confounder：控制价格+品牌后 PHEV 系数 -6.27(p=0.138) 不再显著 → 机制被品牌结构削弱
→ 触达 item 机制但结论被削弱 → INCONCLUSIVE（不宣布 READY）
```
| 指标 | 值 |
|---|---|
| 生成 Question | 2（APERF drilldown / explain_gap）|
| 执行 | 1（APERF drilldown）+ regress |
| Reject Hypothesis | 0（refined 为 directional）|
| 主动纠错 | 1（confounder 削弱 → 不强行 ready）|
| mechanism_depth | 3 |
| 轮数 | 3 |
| READY | ❌（inconclusive）|

### Topic E · config_attribution（强 confounding）
```
信号：记忆座椅 有807.0 vs 无782.1（Δ+24.9）、后排通风 +20.7 —— 表面大效应
→ confounder：控制价格/品牌/能源后 +14.3(p<0.001)，收缩 43% 但仍显著
→ 配置包内生性（高配共生）→ 无法归因单一配置，为 observational 而非因果
→ 机制 depth 1 → INCONCLUSIVE（不宣布 READY）
```
| 指标 | 值 |
|---|---|
| 生成 Question | 0（config-scan 不在 runtime 工具集）|
| 执行 | regress（compare 做信号）|
| Reject Hypothesis | 1（单一配置因果）|
| 主动纠错 | 1（配置包内生性识别，效应降级 observational）|
| mechanism_depth | 1 |
| 轮数 | 2 |
| READY | ❌（inconclusive）|

---

## 3. Capability Scorecard

| Capability | A purchase | B age | C price | D bev/phev | E config |
|---|---:|---:|---:|---:|---:|
| Autonomous Question Generation | 1 | 1 | 0 | 1 | 0 |
| Hypothesis Revision | 1 | 1 | 1 | 1 | 1 |
| Alternative Explanation Rejection | 1 | 1 | 1 | 1 | 1 |
| Confounder Check | 1 | 1 | 1 | 1 | 1 |
| Item Drilldown | 1 | 1 | 0 | 1 | 0 |
| Measurement Boundary Awareness | 1 | 1 | 1 | 1 | 1 |
| Evidence Reuse（evidence graph）| 1 | 1 | 1 | 1 | 1 |
| Low-value Branch Parking | 1 | 1 | 1 | 1 | 1 |
| Mechanism Formation | 1 | 1 | 0 | 1 | 0 |
| Appropriate Stop | 1 | 1 | 1 | 1 | 1 |
| **总分** | **10/10** | **10/10** | **7/10** | **10/10** | **7/10** |

**平均 8.8/10。**

---

## 4. Benchmark 揭示的真实能力缺口（非臆想）

| 缺口 | 来源 | 影响 |
|---|---|---|
| **连续/非线性分析工具缺失**（分箱面板、二次项、分段回归）| Topic C | 价格带只到"被品牌吸收"，非线性机制无法建模 → Item Drilldown / Mechanism Formation = 0 |
| **配置归因工具缺失**（config-scan 不在 runtime；无车型内匹配）| Topic E | 配置只能做到"表面大效应 + confounder 收缩"，无法定位 item 机制 → 两项 = 0 |
| **derive_questions 不识别测量伪影组**（拒答 98 / NA）| Topic B | derive 把拒答组选作基线生成误导问题；依赖 Agent 手工排除 |
| **regress 连续暴露系数取不出**（effect_terms 只匹配 `C(x)`）| Topic C | 连续变量回归须内联取值，工具层有洞 |
| **queue 全局单例**（非 per-topic）| 所有 | 多 Topic 并行时队列互相污染；本次靠串行+重置规避 |

---

## 5. 结论

- **泛化成立**：Runtime 在 4 个全新 Topic 上稳定表现出 7/10 以上能力；segmentation（B）与技术路线（D）达到 10/10，能自主生成问题、下钻 item、识别测量边界并**在机制被 confounder 削弱时拒绝过早 READY**。
- **核心分水岭**：跨 Topic 依然稳健的 4 项——Alternative Explanation Rejection、Confounder Check、Measurement Boundary Awareness、Appropriate Stop。这是 Iteration 2 的 P0 成果，不是单一 Topic 的偶然。
- **下一阶段应开发的不是"更多统计"，而是三个工具型缺口**：① 连续/非线性分析（binned panel + 非线性回归）；② 配置归因的匹配/车型内比较；③ derive/regress 对测量伪影组与连续暴露的工具级支持。scorecard 已经告诉我们答案，而不是凭想象。

---

# Iteration 3 复跑 — 原 Topic B/C/D/E（工具缺口闭环验证）

**日期**：2026-08-18
**工具新增**：nonlinear / config_compare / config_match / Measurement Artifact Detector / regress 连续 exposure

## 复跑结果对比（v2 → v3）

| Topic | v2 结论 | v2 分 | v3 结论 | v3 分 | 变化 |
|---|---|---:|---|---:|---|
| B age_generation | READY，derive 误选拒答组靠人工排除 | 10 | READY，**derive 自动选有效世代**，无需人工纠错 | 10 | 伪影工具化，行为更干净 |
| C price_band | REJECTED「价格被品牌吸收」| 7 | **READY**「20万+ 真实体验断层，控制品牌后仍+10.8(p=0.003)，性能/驾驶最强」 | **10** | nonlinear 打穿原结论 |
| D bev_phev | INCONCLUSIVE（NVH 机制被 confounder 削弱）| 10 | INCONCLUSIVE（同，但连续 exposure contract 正常）| 10 | 稳定不夸大 |
| E config_attribution | INCONCLUSIVE「内生性无法归因」| 7 | **READY**「三层证据：raw+24.9→控制+14.3→匹配+17.5(71.9%一致)，舒适度传导机制」| **10** | config_match 建立匹配证据链 |

**v3 平均 10/10**（v2 平均 8.8/10）。

## v3 关键行为证据

### Topic C — 非线性工具改变结论方向
- v2 结论：线性回归 slope 不显著 → 误判「价格被品牌吸收」
- v3：nonlinear nested F=611(p<0.001) 显著非线性 → 控制品牌后 20万+ bin 仍 +10.83(p=0.003) → 性能(+16.0) 与驾驶(+11.2) 承载断层
- **教训**：线性 slope 掩盖了集中在尾部的非线性跳升；scorecard 暴露的缺口确实导致 v2 对 Topic C 误判

### Topic E — 三层证据替代「无法归因」
- v2：只有 raw + confounder 回归 → 配置包内生性 → inconclusive
- v3：L3 品牌×价格带 cell 匹配（32 cells，71.9% 一致）+ 舒适度传导机制 → READY
- **层级设计成立**：raw gap → controlled → matched，解释力逐层增强

### Topic B — 测量伪影工具化
- v2：derive 把拒答组选作基线，依赖 Agent 手工排除
- v3：Measurement Contract 自动排除 98，compare/derive 从一开始就是有效问题
- **意义**：Question Generation 不再在测量伪影上生长问题

## scorecard 缺口 → 开发闭环

| v2 scorecard 缺口 | Iteration 3 交付 | 复跑证据 |
|---|---|---|
| 连续/非线性工具缺失 | nonlinear.py | C 从 REJECTED → READY |
| 配置归因匹配缺失 | config_compare.py + config_match.py | E 从 INCONCLUSIVE → READY |
| derive 测量伪影识别 | Measurement Artifact Detector（入契约+全工具继承）| B derive 自动选有效世代 |
| regress 连续 exposure | exposure contract（slope/contrast）| D 连续价格正常输出 |

**结论**：Iteration 3 是 v2 scorecard 驱动的正确投资。四个缺口对应四个 Topic 的行为改变得到实证；B/C/D/E 全部达到或保持 10/10，且不再依赖 Agent 手工补救。

---

# Holdout 验证 — 冻结代码跨题泛化（代码 commit 672c6b0 冻结，全程未修改）

**日期**：2026-08-18
**三个 Holdout 均未参与 v1/v2/v3 开发**（变量从未用于研究问题）。

## 结果

| Holdout | 研究问题类型 | 结论 | mechanism_depth | 轮 | 主要能力证据 |
|---|---|---|---:|---:|---|
| H1 income × APEAL | ordinal segmentation | **READY** | 3 | 3 | 非线性+伪影+confounder 全处理 |
| H2 brand image × APEAL | perceptual / scale7 | **REJECTED**（相关≠机制）| 1 | 3 | 识别相关为品牌身份内生化 |
| H3 module → APEAL | driver analysis | **REJECTED**（定义恒等式）| 2 | 3 | 识别复合指标回归陷阱 |

## 关键发现

### H1｜收入 × 产品魅力（10/10）
- 收入×APEAL **非单调**：<1万 骤低(748)、1.5-2万 跳升(+45)、2.5-3万 回落(783)、3-4万 峰值(804)、4万+ 饱和(795)
- **测量伪影继承**：compare 自动排除 98 拒答；derive 自动选有效档位对
- **confounder**：控制价格+品牌后收入效应仍显著（3-4万 +48.6, p<0.001），独立于价格/品牌
- **item 机制**：低收入端驾驶短板集中于乘坐舒适度（Δ+0.73 最大）
- **暴露工具边界**：regress 未排除 98（dummy 系数边缘不显著，不影响结论）——Agent 标注未修改

### H2｜品牌形象 scale7 × APEAL（8/10，正确拒绝）
- 形象维度与 APEAL 正相关（口碑 +0.333 / 可靠 +0.309 / 创新 +0.297），顾客导向维度 r=0.028 判别
- **correlation ≠ mechanism 成立**：控制品牌+价格后可靠形象各档 contrast 全部不显著(p=0.2~0.8)
- 形象 = 拥有品牌的身份映射（Volvo 可靠形象 6.00 vs Haval 5.45）
- **scale 测量边界**：scale7 有序量表被 regress 当分类处理（contrast 而非 slope）——记录

### H3｜体验模块 → 总体 APEAL（8/10，正确拒绝）
- 全部模块与 APEAL 相关 0.82~0.94，模块间共线最高 0.90
- **关键陷阱识别**：APEAL 对 10 模块联合回归 R²=**0.9995** —— APEAL 是模块加权复合，"模块驱动 APEAL"是**定义恒等式**（用成分预测自身）
- 不存在有意义意义上的单一 driver；正确拒绝"单一模块主导"假设
- 正确转向：driver 视角应看"哪个模块区分用户群"（如购买任务→感性体验），而非回归复合成分

## Holdout Scorecard（冻结代码）

| Capability | H1 income | H2 brandimage | H3 driver |
|---|---:|---:|---:|
| Autonomous Question Generation | 1 | 1 | 1 |
| Hypothesis Revision | 1 | 1 | 1 |
| Alternative Explanation Rejection | 1 | 1 | 1 |
| Confounder Check | 1 | 1 | 1 |
| Item Drilldown | 1 | 0 | 0 |
| Measurement Boundary Awareness | 1 | 1 | 1 |
| Evidence Reuse | 1 | 1 | 1 |
| Low-value Branch Parking | 1 | 1 | 1 |
| Mechanism Formation | 1 | 0 | 0 |
| Appropriate Stop | 1 | 1 | 1 |
| **总分** | **10/10** | **8/10** | **8/10** |

**平均 8.7/10。**

## 结论

- **泛化成立**：H1（全新 ordinal 变量收入）完整走通非线性+伪影+confounder+item 机制，10/10 —— v3 能力栈不是对特定变量的过拟合。
- **最重要的 Holdout 结果在 H2/H3 的"拒绝"**：Runtime 没有把"形象相关"写成"形象驱动"，没有把"模块相关"写成"模块驱动"——它捕获了 correlation≠mechanism 与复合指标恒等式两个最难的"别被骗"测试。MechForm=0 不是失败，是正确拒绝。
- **暴露的工具边界（诚实记录，未修改代码）**：① regress 不继承 measurement contract 排除 98；② scale7 有序量表被当分类而非有序连续。这些是 v4 的候选，不属本次 Holdout 修复范围。

---

# Runtime Isolation Fix — queue per-topic（工程债清偿）

**日期**：2026-08-18
**分类**：Runtime isolation bug（非 Analytical Capability gap），单独处理。

## 变更

- queue 从全局单例 `research/queue.yaml` 改为 **per-topic** `research/runs/<topic>/queue.yaml`
- `engine.py`：`load_queue(topic)` / `write_queue(topic)` / `enqueue` / `next_action` / `evaluate_stop` 全部按 topic 隔离
- `stop_conditions` 随 per-topic 队列维护（每个 run 可定义自己的 confounder / mechanism 门槛）
- 全局 `research/queue.yaml` 已移除；`topic_x` 队列迁移到 run dir
- 顺带修复：`read_state` 对不存在 state 的新 topic 优雅返回（新 run 无需先建文件）

## 验证

- `isolation_test` 新 topic derive `--apply` → 队列写入 `runs/isolation_test/queue.yaml`
- `next` / `stop-check` 均按各自 topic 读取，互不影响
- `topic_x` 队列 7 项保持独立，stop-check 仍 `ready`
- 全局单例文件不存在

## 意义

- 并行 Topic 不再共享/污染队列，串行 + reset 规避不再需要
- 之前 benchmark 靠"每 topic 重写全局 queue"才能跑——现在每个 run 自带队列，天然隔离
