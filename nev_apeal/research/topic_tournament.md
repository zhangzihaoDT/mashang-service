# Topic Tournament — Production Research 候选竞争

**日期**：2026-08-19
**历史 Round 2 评分维度**（非统计显著性）：新颖性 × 证据强度 × 机制深度 × OEM Actionability × JDP 风格匹配 × PPT 张力（每维 1–5，满分 30）。Final Tournament 改用五个报告价值维度，见文档末尾。
**证据锚定**：各 Topic 在 v2/v3/Holdout run 中的实际证据链（evidence.jsonl / state.yaml）

---

## Research Funnel / Entity Mapping（统计事实源）

**为何存在**：Run、Topic、Finalist 是不同统计单位——Run 是 `research/runs/` 下的实际运行目录（含 `_it3` 复跑），Topic 是合并同主题迭代后的独立研究问题，Finalist 是进入锦标赛的成熟候选。所有"多少主题 / 多少 run / 6 个 Topic 是什么"类问题，**统一以本表为准**，不要从目录或 evidence 临时反推。

| 层级                 | 数量  | 口径                                              |
| -------------------- | ---: | ------------------------------------------------- |
| **Evidence**         | **70** | `evidence.jsonl` 实际落盘证据总数                  |
| **Research Run**     | **16** | `research/runs/` 实际运行目录；含 `_it3` 复跑       |
| **Research Topic**   | **12** | 合并同主题迭代后的独立研究问题（含 `oem_traditional_gap` 已 READY、`charging_lifestyle` 已 READY、`phone_connectivity_ainfo` / `range_fastcharge_trends` 已拒绝验证）|
| **Tournament Finalist** | **8**  | T1–T8，进入 Topic Tournament 的成熟候选             |
| **Champion**         | **1**  | T1 Purchase Mission                              |
| **Production Topic** | **1**  | T1 经 Production Research（P1~P3）深挖后的最终交付主题 |

| Topic            | Run                                                 | Tournament 身份              |
| ---------------- | --------------------------------------------------- | ---------------------------- |
| Purchase Mission | `topic_x`                                           | T1 · Champion · Production   |
| Age / Generation | `age_generation` + `_it3`                           | T2                           |
| Income           | `holdout_h1_income`                                 | T3 · Holdout                 |
| Price Band       | `price_band` + `_it3`                               | T4                           |
| Configuration    | `config_attribution` + `_it3`                       | T5                           |
| BEV / PHEV       | `bev_phev` + `_it3`                                 | T6                           |
| Brand Image      | `holdout_h2_brandimage`                             | Holdout only                 |
| Driver Analysis  | `holdout_h3_driver`                                 | Holdout only                 |
| OEM Experience Gap | `oem_traditional_gap`                            | T8 · Finalist · READY（无品牌级残余，gap=多因素综合） |
| Charging Lifestyle | `charging_lifestyle`                      | T7 · Finalist · READY（机制=补能生活方式分群，观察性） |
| Phone Connectivity（已拒绝验证）| `phone_connectivity_ainfo`                 | Topic 验证 · REJECTED        |
| EV 续航焦虑/快充趋势（已拒绝验证）| `range_fastcharge_trends`                 | Topic 验证 · REJECTED        |

**一句话漏斗**：70 Evidence → 16 Research Runs → 12 Research Topics → 8 Tournament Finalists → 1 Champion → 1 Production Topic

**候选池扩展（2026-08-19，Signal Board 驱动）**：

> **Round 2 起，Tournament 比较单位为 Signal 而非变量**：同一变量可贡献多个不同结构的 Signal（main effect / expectation_wow / discriminator / interaction），各自独立候选。Signal 统一以 `contracts/signal_contract.json` 的 Signal Contract 落盘。

| 候选 | 状态 | 说明 |
|---|---:|---|
| **T7 Charging Lifestyle**（NEV_08） | **Finalist · READY** · `runs/charging_lifestyle/` | raw 45.1 → 控制后 +47.9（WLS +26.7）；H1-Robustness ✔ / H2-三梯度台阶 ✔ / H3-补能最大承载 ✔ / H4-差异全面（非补能特异）✘ / H5-残差仍显著 ✔。报告 `reports/charging_lifestyle.md` |
| **T8 OEM Experience Gap**（ORIGIN3_DP） | **Finalist · READY** · `runs/oem_traditional_gap/` | raw +14.3 → 完整控制（结构+人口学+形象+使用强度）归零（WLS +2.7 p=0.53）；无品牌级残余，gap=多因素综合。E-001~E-012 |
| **C5 · 补能预期校准（AFUEL_D_06 + ACHAR_D_05）** | **CANDIDATE · merged expectation_wow** · `expectation_wow_01/02/04/05` | 两暴露中度相关（Spearman ρ=0.455），但同时纳入 FULL 控制后仍各自显著：续航 Better +53.4 APEAL / +112.7 AFUEL，充电时长 Better +71.1 / +80.7（WLS, p<0.001）。合并为一个主题下的两个独立 Signal，作为 T7 的补充机制层。 |
| **T9 · Expectation Calibration** | **READY · terminal** | C5 已验证为“预期兑现”机制：两类 exposure 同时控制后独立显著，并落到充电便利、状态可读、整体充电体验和续航 item。Run `expectation_calibration/`。 |
| **T10 · Mileage Experience Lifecycle** | **INCONCLUSIVE · terminal** | `nonlinear_pattern_01` 与 AFUEL/item 回落成立，但 APEAL 总体及多数模块不够稳定，不能命名为产品质量衰减。Run `mileage_experience_lifecycle/`。 |

> 原则：Signal Board 只做筛选与优先级排序，Topic 通过竞争获得研究预算（详见 `reports/signal_board.md`）。不是发现统计差异就建 run。

---

## 1. 候选池（8 个已研究 Topic）

| ID | 候选 | 研究结论 | 状态 | mechanism_depth |
|---|---|---|---|---|
| T1 | Purchase Mission｜增购用户的可感知升级价值 | 增购 798.4，控制后 +18.3(p<0.001)，差异集中感性体验（外观/驾驶/座舱），非基础补能 | READY | **4** |
| T2 | Age/Generation｜世代差异与具体体验短板 | 95~99 最高 811.3，控制价格后 +37.3，驾驶差异全谱系（总体驾驶感受主导） | READY | 3 |
| T3 | Income｜收入非线性与舒适体验机制 | <1万 748→3-4万 804 峰值→4万+ 饱和；控制后 +48.6；低收入舒适短板 Δ+0.73 | READY | 3 |
| T4 | Price Band｜20万+ 产品魅力断层 | 20万+ 跳升 +11.9，控制品牌后 +10.8(p=0.003)，性能(+16)/驾驶(+11)承载 | READY | 3 |
| T5 | Configuration｜记忆座椅等配置的真实体验传导 | 三层证据：raw+24.9→控制+14.3→匹配+17.5(71.9%一致)；舒适度传导 +17.4 | READY | 3 |
| T6 | BEV/PHEV｜技术路线差异 | BEV 领先 3.4，性能差 +7.2 且 item 指向发动机 NVH；但控制品牌后 p=0.138 不显著 | INCONCLUSIVE | 3 |
| T7 | Charging Lifestyle｜充电生活方式分群 | 从不快充组体验全面领先 +27~46（控制能源/价格/品牌/人口/强度/场景/家充/慢充后残差仍显著）；差异全方位非补能特异；快慢充速度 item 最大 | READY | 3 |
| T8 | OEM Experience Gap｜来源结构差距 | raw +14.3 被完整控制（结构+人口学+品牌形象+使用强度/场景）完全吸收归零（WLS +2.7 p=0.53）；无品牌级不可归因残余，非独立机制 | READY | 3 |

---

## 2. 六维评分

| 维度 | T1 Purchase | T2 Age | T3 Income | T4 Price | T5 Config | T6 BEV/PHEV | T7 Charging | T8 OEM |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 新颖性 | 4 | 3 | 4 | 4 | 4 | 3 | 4 | 3 |
| 证据强度 | 5 | 4 | 4 | 4 | 4 | 2 | 4 | 4 |
| 机制深度 | 5 | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| OEM Actionability | 4 | 3 | 4 | 4 | 4 | 3 | 4 | 3 |
| JDP 风格匹配 | **5** | 3 | 4 | 4 | 3 | 3 | 3 | 2 |
| PPT 张力 | 4 | 3 | 3 | 4 | 3 | 3 | 4 | 2 |
| **总分** | **27** | **19** | **22** | **23** | **21** | **17** | **22** | **17** |

> **评分调整说明**：T1 的 JDP fit 从 4 提到 5。理由——T1 已形成完整的「用户任务 → 魅力结构 → Item 体验 → 产品定义」价值链，这正是产品研究公司（J.D. Power 式）的典型价值链；相比之下 T4 的"20 万以上体验跳升"只覆盖价位带层面，未闭环到产品定义。

---

## 3. 逐维依据

### T1 Purchase Mission（27）— 冠军
- **新颖性 4**：「增购人群要的不是更多配置，而是可感知的升级体验」反直觉——传统视角聚焦首购。
- **证据强度 5**：10 条证据链（supports×3 / refines×3 / rules_out×2 / explains×2），控制能源+价格+品牌仍显著（+18.3, p<0.001），参照组陷阱已排除（+11.8→+18.3 放大为对照混淆非 suppression），BEV/PHEV 与各级城市内一致。
- **机制深度 5**：唯一 depth 4（产品机制）；item 级定位——总体驾驶感受与转向手感承载差异，外观单题承载；补能仅 +1.3（聚合结构差异已被解析）。
- **OEM Actionability 4**：可直接落地——对增购人群的产品沟通与设计重点转向整车动态体验与外观，避免续航参数主打；"升级感"是可执行的产品定义语言。
- **JDP 风格 5**：完整闭环「用户任务 → 魅力结构 → Item 体验 → 产品定义」，是产品研究公司典型价值链的最高形态。
- **PPT 张力 4**：核心反转（"补能没差，驾驶才差"）+ 一个数字（798 vs 784）即可讲故事。

### T4 Price Band（23）— 亚军
- **新颖性 4**：v2 曾误判"价格被品牌吸收"，v3 非线性工具推翻为"20万+ 真实断层"——反直觉且过程故事性强。
- **证据强度 4**：nonlinear nested F=611(p<0.001)，控制品牌后 +10.8(p=0.003) 稳健。
- **机制深度 3**：模块级（性能 +16 / 驾驶 +11 承载断层），未到 item/配置级。
- **OEM Actionability 4**：20万+ 体验门槛对定价/配置下放强指导（20万以下补性能/驾驶）。
- **PPT 张力 4**：一图展示跳升断层，直观有力。

### T5 Configuration（21）— 重定位为 T1 的证据方法
- 三层证据链（L1/L2/L3）是最"方法论正确"的候选，Actionability 4（配置价值量化）；但"记忆座椅值不值"张力中等，L3 有 28% 异质性。
- **角色调整**：不作为独立 Topic，而是作为 T1 之后的证据方法——回答"哪些具体配置真的能制造升级体验"，是 T1"OEM 该提供什么"的第二层答案。

### T3 Income（22）
- 新颖性 4（收入非线性+饱和）、Actionability 4（平价车舒适性）、JDP 4；但机制深度 3 且"低收入舒适短板"叙事张力中等。

### T2 Age（19）
- 控制价格后 +37.3 稳健、item 层到达；但世代差异"全谱系拉开"产品指向弱（Actionability 3），叙事张力一般。

### T6 BEV/PHEV（17）— 淘汰
- **证据强度 2**：confounder 削弱（p=0.138），INCONCLUSIVE；item 机制虽到达但结论不成立。
- 技术路线差异是"最常见"的候选，新颖性低；若强行成 Topic 属过度承诺。

---

## 4. 淘汰与决策

**Round 1（证据关）淘汰**：T6 BEV/PHEV —— 证据不足以形成强 Topic（用户已确认），排除。

**Round 2（竞争关）**：T1 Purchase Mission 在证据强度（5）与机制深度（5）上独一档，且在 Actionability 与 PPT 张力上并列最高。

**最终 Top 1 = T1 Purchase Mission｜增购用户的可感知升级价值**

选择理由（一句话）：它是唯一 mechanism_depth 4、证据链最厚、产品指向最直接、且叙事具有反直觉张力的候选——"增购用户不差补能，差的是驾驶与外观的升级感"。

**替补顺序**：T4 Price Band（20万+ 断层）→ T5 Configuration（T1 的证据方法）≈ T3 Income → T2 Age >>> T6 BEV/PHEV。

> **最终排序**：T1 > T4 > T5 ≈ T3 > T2 >>> T6。其中 T5 上升是因为它作为 T1 之后的证据方法（回答"哪些具体配置真的能制造升级体验"），不是独立 Topic。

---

# Final Tournament｜10 Terminal Topics（2026-08-19）

最终 Tournament 改用五个“报告价值”维度，而非 Discovery 阶段的统计筛选分数：**Evidence strength / Mechanism depth / Novelty / Business actionability / Narrative power**，每维 1–5 分，满分 25。Champion 不按最小 p-value 或最大 effect size 决定。

完整评分与终局证据见 `reports/final_tournament_10_topics.md`。

| Rank | ID | Topic | Evidence | Mechanism | Novelty | Actionability | Narrative | Total | 状态 |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| **1** | **T1** | **Purchase Mission｜可感知升级价值** | 5 | 5 | 4 | 5 | 5 | **24** | **Champion / Production Topic** |
| 2 | T9 | Expectation Calibration｜补能预期兑现 | 5 | 4 | 5 | 4 | 5 | **23** | Finalist |
| 3 | T5 | Configuration｜配置是载体，不是价值 | 4 | 4 | 4 | 5 | 4 | **21** | T1 supporting method |
| 4 | T4 | Price Band｜中端体验断层 | 4 | 3 | 4 | 4 | 4 | **19** | Alternate |
| 4 | T7 | Charging Lifestyle｜补能生活方式分群 | 4 | 3 | 4 | 4 | 4 | **19** | Alternate |
| 4 | T8 | OEM Experience Gap｜品牌差距被结构吸收 | 5 | 3 | 4 | 3 | 4 | **19** | Boundary Topic |
| 7 | T3 | Income｜收入非线性与舒适短板 | 4 | 3 | 4 | 4 | 3 | **18** | Supporting |
| 8 | T2 | Age / Generation｜世代体验谱系 | 4 | 3 | 3 | 3 | 3 | **16** | Supporting |
| 8 | T10 | Mileage Experience Lifecycle｜里程非线性 | 3 | 2 | 4 | 3 | 4 | **16** | Inconclusive |
| 10 | T6 | BEV / PHEV｜技术路线差异 | 2 | 3 | 3 | 3 | 3 | **14** | Inconclusive |

**Final Champion：T1 Purchase Mission。** 它的优势是最完整的“用户任务 → 体验结构 → item 机制 → 产品定义”链条，而不是某个单独统计量最高。T9 是最强挑战者，但仍缺少从预期自报到具体产品承诺/设计杠杆的完整闭环。

---

## 5. 进入 Production Research 的下一步（针对 Top 1）

- 已有：参照组陷阱排除、confounder 全覆盖（能源/价格/品牌）、item 级机制（ADRV 总体驾驶感受/转向手感）。
- 待补（按优先级，非顺序）：

### P1（第一优先）车型/品牌×价格结构内，增购 vs 首购差异还剩多少
**这是最后一个可能威胁主叙事的大 confounder。** 若控制车型/品牌×价格结构后差异大幅消失，Topic 必须改写。数据无车型级列，用 SEGMENT_DP（细分市场段，17 类 = 车身尺寸/级别 × BEV/PHEV 技术路线组合，最接近车型/级别的代理）作为代理，叠加品牌与价格做全结构控制。

### P2（第二优先）把 ADRV 连接到产品属性/配置
现在知道"总体驾驶感受、转向手感"有差异，但还没完全回答 OEM"具体该提供什么"。复用 T5 三层证据法（config_compare/config_match）：在增购 vs 首购差异内，哪些配置/产品属性真正与驾驶体验差异共变。

### P3（第三优先）增购 × 价格带交互
最有潜力的融合方向——若成立，T1 与 T4 合并成一个更强 Topic：

> **20 万以上的增购用户，购买的不是更多参数，而是更明确的体验跃迁。**

这会把 T1 从"人群叙事"升级为"人群 × 价位带"的双重锋利故事。检验方式：nonlinear 分带 × 购买任务交互（增购优势是否随价格带上移而增强）。

### P4 产品叙事组装
P1~P3 稳定后，组装 JDP Topic PPT（Signal→Evidence→Who/Where→Mechanism→OEM should do）。

---

# Production Research 深挖结果（P1→P2→P3，已执行）

**日期**：2026-08-18 ｜ 证据落盘于 `runs/topic_x/evidence.jsonl`（E-011~E-013）

## P1 — 车型/品牌×价格结构内，增购差异还剩多少 → **主叙事经受考验**

- 控制细分市场段 SEGMENT_DP（17 类，车身级别 × 技术路线，车型结构代理）+品牌+价格+能源后，增购系数 **+18.17（p=5.4e-07）**，与基准 +18.3 几乎一致
- **最后一个大 confounder 无法解释差异** → Topic 无需改写（E-011）

## P2 — ADRV 差异对应的产品属性/配置 → **配置是载体，不是主因**

- 记忆座椅→驾驶感受匹配效应 **+19.3**（75% cell 一致）、主驾通风 +13.3
- 增购记忆座椅拥有率 41.9% vs 首购 24.4% —— 增购车配置水平更高
- 但**换购拥有率最高(49%)且 APEAL 最低** → 配置多寡不能解释增购优势，差异在感知体验本身（E-012）
- OEM 含义：记忆/通风座椅等"高感知配置"是制造驾驶/舒适体验差异的有效载体，而非堆参数

## P3 — 增购×价格带交互 → **融合假设被数据拒绝，但得到更真实的结构**

| 价格带 | 增购 | 首购 | 换购 | 增购−首购 | 增购−换购 |
|---|---:|---:|---:|---:|---:|
| <10万 | 787.4 | 779.6 | 768.9 | +7.8 | +18.5 |
| 10-15万 | 788.1 | 785.0 | 763.8 | +3.1 | +24.3 |
| **15-20万** | **801.8** | 781.4 | 788.2 | **+20.4** | +13.7 |
| 20-30万 | 802.1 | 798.8 | 788.2 | +3.3 | +13.9 |
| 30万+ | 804.9 | 803.5 | 790.9 | +1.4 | +14.0 |

- 融合假设「越高价格带增购越要求升级感」**不成立**（非单调）
- 真实结构：**增购 vs 首购 的溢价峰值在中端 15-20万（+20.4），高端 30万+ 收窄至 +1.4（首购也拉满）**；增购 vs 换购 全带稳定 +14~24
- 叙事含义：20万+ 价格带把所有人（尤其首购）的体验都抬起来；增购用户的"体验升级感"在中端最被拉开，高端市场是全民体验竞争（E-013）

## 对 Top 1 主叙事的最终影响

- P1：主叙事安全（+18.17 不变）
- P2：主叙事强化（配置是载体，体验才是差异）
- P3：主叙事**精化**而非推翻——升级感溢价在中端最强；可加一句：**"增购用户在中端价位就已靠体验区别于首购，而高端价位体验已全民拉满"**
