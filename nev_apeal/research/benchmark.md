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
