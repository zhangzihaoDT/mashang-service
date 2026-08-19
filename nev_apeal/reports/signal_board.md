# Signal Board — 候选池扩展扫描

**日期**：2026-08-19 ｜ 数据 `data/source.sav`(9,937×370) ｜ 权重 `APEAL_WT` ｜ 指标 `APEAL_Index`

**性质**：一次性筛选（screening）。横截面加权均值差（gap = 加权 APEAL max − min，组 n≥50）。
**不是机制结论**：未做 confounder 控制；被选中轴仍需走完整验证（PRICE/BRAND/能源 + item 下钻）。

| 轴 | 分组变量 | gap | 最高分组 | 最低分组 | 最高→最低 | 覆盖n |
|---|---|---:|---|---|---|---:|
| 家庭·教育 | CN_EDUCATION | 53.5 | Post graduate 807.8 | High school 754.3 | Post graduate→High school | 9787 |
| 家庭·职业 | CN_OCCUPATION | 52.2 | Government worker 812.5 | Clerical 760.3 | Government worker→Clerical | 9618 |
| 充电生活·慢充频率 | NEV_01 | 51.6 | 2-3 times per month 814.4 | Once a month or less 762.8 | 2-3 times per month→Once a month or less | 9937 |
| 人口·年龄分桶 | AGE_BUCKETS | 49.5 | BETWEEN 25 AND 29 810.7 | BETWEEN 50 AND 54 761.2 | BETWEEN 25 AND 29→BETWEEN 50 AND 54 | 8785 |
| 使用场景·个人/家庭 | NEV_11C | 47.7 | Daily 810.8 | Never/less than once a month 763.1 | Daily→Never/less than once a month | 9937 |
| 充电生活·快充频率 | NEV_08 | 45.1 | Never used fast charging 813.8 | Twice a week or more 768.7 | Never used fast charging→Twice a week or more | 9937 |
| 使用场景·通勤 | NEV_11A | 44.3 | Daily 794.4 | Once a month 750.1 | Daily→Once a month | 9937 |
| 使用场景·商务 | NEV_11B | 31.7 | 2-3 times per month 800.8 | Never/less than once a month 769.1 | 2-3 times per month→Never/less than once a month | 9937 |
| 使用场景·驾驶乐趣 | NEV_11G | 31.3 | Multiple times per week 800.8 | Daily 769.5 | Multiple times per week→Daily | 9937 |
| 使用强度·日均驾驶时长 | NEV_13a | 31.0 | 2-4h 804.2 | 1-2h 773.2 | 2-4h→1-2h | 8417 |
| 家庭·人口规模 | CN_NUMBER_HOUSEHOLD | 30.2 | 4+ 805.0 | 1 774.8 | 4+→1 | 9225 |
| 使用场景·越野 | NEV_11E | 27.9 | Once a week 802.4 | Multiple times per week 774.5 | Once a week→Multiple times per week | 9937 |
| 使用强度·累积里程 | NEV_12 | 26.3 | 1k-5k 795.5 | 10k-20k 769.2 | 1k-5k→10k-20k | 9451 |
| 地理·大区 | Region_DP | 26.0 | East 798.1 | South 772.1 | East→South | 9937 |
| 使用场景·户外 | NEV_11D | 21.1 | Once a week 801.5 | Once a month 780.4 | Once a week→Once a month | 9937 |
| 使用场景·拖拽 | NEV_11F | 19.3 | Once a month 799.0 | Multiple times per week 779.7 | Once a month→Multiple times per week | 9937 |
| 地理·城市层级 | CITY_TIER_DP | 18.8 | Tier 3 803.0 | Tier 2 784.2 | Tier 3→Tier 2 | 9937 |
| OEM 豪华/大众 | PREMMAKE_DP | 17.9 | Premium 805.8 | Mass Market 787.9 | Premium→Mass Market | 9937 |
| OEM 来源结构 | ORIGIN3_DP | 17.8 | International Brands 800.0 | Domestic Traditional Brands 782.2 | International Brands→Domestic Traditional Brands | 9937 |
| 充电生活·家充可用性 | NEV_05_R1 | 17.7 | Yes 795.9 | No 778.2 | Yes→No | 8784 |
| OEM 原产地 | SUB_ORIGIN_DP | 14.7 | North America 801.4 | Asia 786.7 | North America→Asia | 9937 |
| 家庭·车辆数 | YPV_05 | 13.3 | 2 797.7 | 3+ 784.4 | 2→3+ | 9937 |
| 充电生活·车位共享 | NEV_07 | 7.9 | Yes 800.2 | 2.0 792.3 | Yes→2.0 | 5953 |
| 家庭·婚况 | CN_MARITAL_STATUS | 6.2 | Single (never married) 794.8 | Married 788.6 | Single (never married)→Married | 9777 |
| 人口·性别 | GENDER | 4.8 | Female 792.0 | Male 787.2 | Female→Male | 9845 |

## 各轴明细

## 短名单与推荐（confounder 初筛后）

> 初筛回归（`regress`，控制 SUPER_SEGMENT_DP + CN_YNV_07 + PREMMAKE_DP，参照组=最低分组）。

| 候选 | 原始gap | 控制后 | 判定 | 理由 |
|---|---|---:|---:|---|---|
| **补能依赖（NEV_08 快充频率）** | 45.1 | **+52.4**（Never vs Everyday, p<0.001），梯度单调 | ✅ 入池 | 控制能源/价格/豪华后效应**放大**，非结构混淆；叙事强（"越不依赖公共快充，体验越好"）；与 T1"补能没差"形成跨用户对照 |
| **使用场景·家庭（NEV_11C）** | 47.7 | Daily +30.9（p<0.001），控制家庭人口后仍显著 | ⚠️ 备选 | 单调但机制不清晰（熟悉度 vs 车型结构待拆） |
| **使用强度·累积里程（NEV_12）** | 26.3 | 非单调（1k-5k 峰值 → 10k-20k 回落） | ⚠️ 备选 | "蜜月期/衰减"故事强，但需 nonlinear 工具（同 T4） |
| 家庭·教育（CN_EDUCATION） | 53.5 | 参照组 n=2 退化，income-family | ❌ 不独立成题 | 与 T3 Income 重叠，参照组测量退化 |
| 家庭·职业（CN_OCCUPATION） | 52.2 | — | ❌ 不独立成题 | 与 T3 Income/教育重叠 |
| 人口·年龄（AGE_BUCKETS） | 49.5 | — | ❌ 已覆盖 | 即 T2 Age/Generation |
| 地理（Region/CITY_TIER） | 26.0/18.8 | 非单调且与收入/价格混杂 | ❌ 低优先 | 有张力但机制弱 |
| OEM 结构（ORIGIN3_DP） | 17.8 | 控制后 +7.5~8.6 → 完整控制归零（无品牌级残余） | ✅ **READY（T8）** | `oem_traditional_gap` 12 条证据，报告 `reports/oem_experience_gap.md` |

## 候选池优先级（资源分配器）

> 原则：Signal Board 只做筛选与优先级排序；Topic 通过竞争获得研究预算，不因发现统计差异就立即建 run。同一时间只推进一个主研究。

| 序号 | 候选 | 状态 | 说明 |
|---|---|---:|---|
| **T7** | **Charging Lifestyle**（NEV_08 快充频率） | **Finalist · READY** · `runs/charging_lifestyle/` | 从不快充组体验全面领先 +27~46（WLS +26.7）；补能生活方式分群，报告 `reports/charging_lifestyle.md` |
| **T8** | **OEM Experience Gap**（ORIGIN3_DP） | **Finalist · READY** · `runs/oem_traditional_gap/` | raw +14.3 → 完整控制归零（+2.7 p=0.53）；无品牌级残余，gap=多因素综合。报告 `reports/oem_experience_gap.md` |
| **C3** | **使用强度·累积里程（NEV_12）** | **CANDIDATE · 独立残差存续**（2026-08-19 retrospective） | 控制 NEV08+FULL 后 F=11.2 p<0.001 独立非单调（5-10k −14.0 / 10-20k −21.4）；与 T7 suppression 结构方向相反 → **独立"蜜月/衰减"问题，未吸收**；需 nonlinear 工具，不机械升级 |
| **C4** | **使用场景·家庭（NEV_11C）** | **WEAK · 仅单格存活**（2026-08-19 retrospective） | 控制 NEV08 后仅"每日使用"格 +27.8(p=0.0006, n=289) 显著、余 4 档全不显著；机制不清（熟悉度 vs 车型结构）→ 不独立成题，保留观察 |

### 家庭·教育（CN_EDUCATION）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Primary school | 2 | 632.8 |
| Middle school | 30 | 720.2 |
| High school | 213 | 754.3 |
| Technical/vocational college | 760 | 784.3 |
| University | 8050 | 789.8 |
| Post graduate | 732 | 807.8 |

### 家庭·职业（CN_OCCUPATION）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Professional | 1038 | 794.6 |
| Government worker | 244 | 812.5 |
| General white-collar worker | 2993 | 797.1 |
| Senior management | 703 | 792.5 |
| Middle management | 2447 | 788.1 |
| Technical worker | 731 | 778.5 |
| General blue-collar worker | 244 | 776.4 |
| Teaching | 301 | 808.4 |
| Clerical | 181 | 760.3 |
| Self-employed | 684 | 766.5 |
| Housewife | 29 | 738.1 |
| Student | 11 | 774.7 |
| Unemployed/not working/retired | 12 | 635.3 |

### 充电生活·慢充频率（NEV_01）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Everyday | 305 | 774.8 |
| Twice a week or more | 3389 | 773.6 |
| Once a week | 3014 | 798.3 |
| 2-3 times per month | 1590 | 814.4 |
| Once a month or less | 486 | 762.8 |
| Never used normal charging | 1153 | 793.1 |

### 人口·年龄分桶（AGE_BUCKETS）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| AGE<20 | 3 | 842.8 |
| BETWEEN 20 AND 24 | 250 | 793.6 |
| BETWEEN 25 AND 29 | 2045 | 810.7 |
| BETWEEN 30 AND 34 | 2505 | 794.7 |
| BETWEEN 35 AND 39 | 2292 | 787.8 |
| BETWEEN 40 AND 44 | 1153 | 803.8 |
| BETWEEN 45 AND 49 | 429 | 778.7 |
| BETWEEN 50 AND 54 | 81 | 761.2 |
| BETWEEN 55 AND 59 | 21 | 748.6 |
| BETWEEN 60 AND 64 | 5 | 772.1 |
| BETWEEN 65 AND 69 | 1 | 713.2 |

### 使用场景·个人/家庭（NEV_11C）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Never/less than once a month | 362 | 763.1 |
| Once a month | 1064 | 781.8 |
| 2-3 times per month | 2728 | 786.6 |
| Once a week | 2641 | 789.3 |
| Multiple times per week | 2805 | 795.2 |
| Daily | 337 | 810.8 |

### 充电生活·快充频率（NEV_08）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Everyday | 244 | 771.1 |
| Twice a week or more | 2018 | 768.7 |
| Once a week | 2479 | 788.5 |
| 2-3 times per month | 2066 | 795.6 |
| Once a month or less | 1641 | 788.9 |
| Never used fast charging | 1489 | 813.8 |

### 使用场景·通勤（NEV_11A）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Never/less than once a month | 60 | 750.5 |
| Once a month | 86 | 750.1 |
| 2-3 times per month | 236 | 753.2 |
| Once a week | 297 | 767.2 |
| Multiple times per week | 4101 | 787.7 |
| Daily | 5157 | 794.4 |

### 使用场景·商务（NEV_11B）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Never/less than once a month | 2617 | 769.1 |
| Once a month | 1847 | 793.9 |
| 2-3 times per month | 2657 | 800.8 |
| Once a week | 1480 | 795.8 |
| Multiple times per week | 1223 | 792.5 |
| Daily | 113 | 797.2 |

### 使用场景·驾驶乐趣（NEV_11G）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Never/less than once a month | 1480 | 772.8 |
| Once a month | 2687 | 783.5 |
| 2-3 times per month | 2831 | 793.0 |
| Once a week | 1782 | 800.1 |
| Multiple times per week | 1066 | 800.8 |
| Daily | 91 | 769.5 |

### 使用强度·日均驾驶时长（NEV_13a）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| 1-2h | 3661 | 773.2 |
| 2-4h | 2360 | 804.2 |
| 4h+ | 310 | 796.5 |
| <1h | 2086 | 775.2 |

### 家庭·人口规模（CN_NUMBER_HOUSEHOLD）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| 1 | 123 | 774.8 |
| 2 | 645 | 793.8 |
| 3 | 5087 | 790.3 |
| 4+ | 3370 | 805.0 |

### 使用场景·越野（NEV_11E）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Never/less than once a month | 7138 | 786.3 |
| Once a month | 1578 | 800.5 |
| 2-3 times per month | 741 | 791.6 |
| Once a week | 331 | 802.4 |
| Multiple times per week | 129 | 774.5 |
| Daily | 20 | 755.3 |

### 使用强度·累积里程（NEV_12）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| 10k-20k | 245 | 769.2 |
| 1k-5k | 6530 | 795.5 |
| 20k-50k | 90 | 769.8 |
| 50k+ | 11 | 790.5 |
| 5k-10k | 1856 | 780.4 |
| <1k | 719 | 779.7 |

### 地理·大区（Region_DP）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| North | 1722 | 790.2 |
| East | 3943 | 798.1 |
| South | 1884 | 772.1 |
| West | 2388 | 786.0 |

### 使用场景·户外（NEV_11D）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Never/less than once a month | 2346 | 788.9 |
| Once a month | 3521 | 780.4 |
| 2-3 times per month | 2617 | 796.3 |
| Once a week | 990 | 801.5 |
| Multiple times per week | 427 | 792.7 |
| Daily | 36 | 810.2 |

### 使用场景·拖拽（NEV_11F）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Never/less than once a month | 8009 | 788.2 |
| Once a month | 887 | 799.0 |
| 2-3 times per month | 603 | 792.2 |
| Once a week | 301 | 786.5 |
| Multiple times per week | 117 | 779.7 |
| Daily | 20 | 754.4 |

### 地理·城市层级（CITY_TIER_DP）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Tier 1 | 1816 | 791.1 |
| Tier 2 | 6126 | 784.2 |
| Tier 3 | 1727 | 803.0 |
| Tier 4 | 268 | 793.9 |

### OEM 豪华/大众（PREMMAKE_DP）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Premium | 1342 | 805.8 |
| Mass Market | 8595 | 787.9 |

### OEM 来源结构（ORIGIN3_DP）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Domestic Traditional Brands | 4125 | 782.2 |
| International Brands | 1747 | 800.0 |
| Domestic Startup Brands | 2060 | 798.5 |
| Domestic Affiliated Brands | 2005 | 786.8 |

### 充电生活·家充可用性（NEV_05_R1）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| No | 3506 | 778.2 |
| Yes | 5278 | 795.9 |

### OEM 原产地（SUB_ORIGIN_DP）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Asia | 8332 | 786.7 |
| Europe | 1130 | 799.5 |
| North America | 475 | 801.4 |

### 家庭·车辆数（YPV_05）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| 1 | 7232 | 786.3 |
| 2 | 2588 | 797.7 |
| 3+ | 117 | 784.4 |

### 充电生活·车位共享（NEV_07）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Yes | 1394 | 800.2 |
| 2.0 | 4559 | 792.3 |

### 家庭·婚况（CN_MARITAL_STATUS）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Married | 8197 | 788.6 |
| Single (never married) | 1580 | 794.8 |

### 人口·性别（GENDER）

| 分组 | n | 加权APEAL |
|---|---:|---:|
| Female | 3339 | 792.0 |
| Male | 6506 | 787.2 |

---

## Discovery Layer Retrospective（2026-08-19）

**Trigger**：25 轴扫描 → 4 Candidate → T7+T8 两轮正式研究 → 2 READY。评估 Signal→Topic 漏斗有效性。

### Q1. Signal Board 排名是否有效？—— ✅ 有效

- **排名 vs 结果**：T7（22 分，Tournament #3）与 T8（17 分）均产出高质量 READY Finalist。前两名 22/17 分排序正确。
- **T8 例外注意**：17 分最低之一却是 READY —— 分数低是因**机制负面**（无品牌级残余）而非证据弱；Signal Board 的 actionability 维度未能预判"研究即证伪"的收尾方式。**非缺陷**：证伪也是预算的有效使用。

### Q2. Signal → Topic 转化率？—— ✅ 高效

| 层级 | 数量 | 存活率 |
|---|---:|---:|
| 扫描轴 | 25 | 100% |
| Candidate（confounder 初筛后入池） | 4 | 15% |
| 激活为主研究 | 2 | 50%（T7/T8） |
| READY Finalist | 2 | 100%（激活后） |

- 25→4：初筛截断 84% 浅层候选（教育/职业重叠 T3、年龄=T2、地理机制弱），**未浪费深度研究预算**。
- 4→2→2：激活即 READY，无中途流产；浅层候选转 C3/C4 或观察位，未消失。

### Q3. 剩余 Candidate 怎么处理？—— 重新判据，不机械升级

**判据**：控制 T7 暴露（NEV08+FULL）后，是否仍有独立残差（anova 联合检验）。

| 候选 | 独立残差 | 判定 | 处理 |
|---|---|---:|---:|
| **NEV_12（累积里程）** | F=11.2, p<0.001；5-10k −14.0 / 10-20k −21.4 非单调 | **独立"蜜月/衰减"问题** | C3 · 保留为 Candidate，需 nonlinear 工具；**不标记 ABSORBED** |
| **NEV_11C（家庭场景）** | 仅"每日使用"单格 +27.8 (p=0.0006, n=289)，余 4 档不显著 | **弱/机制不清** | C4 · 观察位，暂不升级 |

- **NEV_12 未吸收**：T7 H5 中作为控制变量消费（suppression 结构：里程高→快充依赖者体验低），但其独立于 NEV08 的非单调衰减方向（10k-20k 低谷）是 T7 不覆盖的独立问题。
- **NEV_11C 边界**：仅在"每日使用"小格有独立效应，且"熟悉度 vs 车型结构"机制未拆——不足独立成题，保留观察。

**漏斗闭环**：25 axes → 4 Candidates → 2 Activated → 2 READY，另 2 Candidate 按独立残差判据分流（1 保留 / 1 观察），无 ABSORBED 标记。下一轮扫描（新数据批次）再决定 C3 是否升级。

---

## Round 2：多 Analysis Type 扫描（2026-08-19）

**架构升级**：从"单变量 main-effect 扫描"扩展为 **多 Scanner → 统一 Signal Contract → Signal Board → Candidate Allocation → Validation Queue**。Tournament 比较单位从**变量**改为 **Signal**（同一变量可贡献多个不同结构的 Signal，各自独立候选）。

**Scanner 目录**（`scratch/discovery/`，执行顺序按用户指定，interaction 第四避免 O(p²) 淘金）：

| 顺序 | Scanner | 分析类型 | 状态 |
|---|---|---|---|
| 1 | `expectation_wow_scan.py` | `expectation_wow` | ✅ 已执行（本轮） |
| 2 | `nonlinear_pattern_scan.py` | `nonlinear_pattern` | ✅ 已执行（承接 C3 NEV_12） |
| 3 | `segment_discriminator_scan.py` | `segment_discriminator` | ✅ 已执行（受控 queue） |
| 4 | `interaction_scan` | `interaction` | ✅ Controlled Pilot executed · `SEGMENT_DP` insufficient coverage |

**Signal Contract**：`contracts/signal_contract.json`（schema v1.0）。字段：`analysis_type / exposure / moderator / outcome / effect_size / sample_support / stability / novelty / interpretation`（+`controls/direction/caveats/wow_structure/coverage`）。

### expectation_wow 扫描结果

**设计**：预期违背（expectation disconfirmation）三档序数 1=Worse / 2=About / 3=Better 为 exposure，Outcome = APEAL_Index + 模块指数（AFUEL_Index，补能续航模块）。FULL 控制组 = [SUPER_SEGMENT_DP, CN_YNV_07, PREMMAKE_DP, AGE_BUCKETS, CN_INCOME, CN_EDUCATION]，OLS+WLS(APEAL_WT)。产出 `scratch/discovery/_signals_expectation_wow.json`（6 条 Signal）。

| Signal | exposure | outcome | 三档加权均值 | wow_gap (Better−About) | penalty (About−Worse) | WLS Better (p) | WLS Worse (p) | n_reg |
|---|---|---|---|---|---|---|---:|---:|---:|---:|
| expectation_wow_01 | **AFUEL_D_06 续航 vs 预期** | APEAL_Index | 740.7 / 784.4 / 834.2 | +49.8 | 43.8 | +42.8 (p<0.001) | −43.4 (p<0.001) | 8572 |
| expectation_wow_02 | **AFUEL_D_06 续航 vs 预期** | AFUEL_Index | 704.0 / 789.9 / 862.6 | +72.7 | 85.9 | +65.3 (p<0.001) | −85.3 (p<0.001) | 8572 |
| expectation_wow_04 | **ACHAR_D_05 充电时长 vs 预期** | APEAL_Index | 730.5 / 778.3 / 829.3 | +51.0 | 47.8 | +48.7 (p<0.001) | −41.2 (p<0.001) | 8572 |
| expectation_wow_05 | **ACHAR_D_05 充电时长 vs 预期** | AFUEL_Index | 707.5 / 781.3 / 850.3 | +68.9 | 73.8 | +65.6 (p<0.001) | −54.6 (p<0.001) | 8572 |

**解读**：

- **效应强度高**：两个补能预期违背变量在 FULL 控制后仍产生 ±40~85 点 APEAL/模块指数差异，远超第一轮 25 轴中多数 main-effect gap（多数 10~30 点）。
- **结构近对称**：wow_gap（Better−About）≈ penalty（About−Worse），即"超预期→加分 / 未达预期→扣分"幅度接近——更接近**预期校准（expectation calibration）**，而非纯 delight 不对称。这提示：补能体验的 APEAL 溢价主要来自"兑现承诺"而非"制造惊喜"。
- **模块指数放大**：效应在 AFUEL_Index（本模块）上约为总 APEAL 的 1.4~1.6 倍——预期违背主要作用于补能模块自身评价，跨模块外溢较小（与 T7 H-004"补能特异"一致）。

**delight 交叉（Better 亚组，缺失 40~60% 仅描述）**：

| exposure | 最常宣称的 delight 项 |
|---|---|
| AFUEL_D_06 续航超预期 | 加速(郊区/高速)、启动按钮、驾驶辅助有效性 |
| ACHAR_D_05 充电超预期 | 启动界面、驾驶辅助、静谧性、加速 |

**候选判定（Signal 级）**：

| Signal | 状态 | 理由 |
|---|---|---|
| expectation_wow_01/02 + 04/05（AFUEL_D_06 + ACHAR_D_05） | **C5 · 合并候选** | 两暴露中度相关（Spearman ρ=0.455, pairwise n=9,882），但同时纳入 FULL 控制后仍各自显著：续航 Better +53.4 APEAL / +112.7 AFUEL，充电时长 Better +71.1 / +80.7（WLS, p<0.001）。合并为一个主题下的两个独立 Signal，是 T7 的机制补充维度。 |
| expectation_wow_03/06（delight 交叉） | **观察位** | 缺失率高、仅 Better 亚组描述，不作独立候选 |

**下一步**：将合并后的“补能预期校准”作为 T7 的补充机制层进入验证队列（同一 owner 可同主题多 Signal）；后续验证两类预期违背是否对应不同产品/沟通杠杆。

### 受控 nonlinear / segment 扫描

- `nonlinear_pattern_01`（NEV_12 累计里程）：业务分箱范围 34.5 点，线性模型 vs 分箱模型增量检验 F=10.51，p<0.001；1k–5k 为峰值，10k–50k 回落，支持 C3 保留为独立候选。
- `segment_discriminator_nev_08_segment_dp`：快充频率在 10 个车型结构段中筛选，组内对比 spread=84.5 点；进入 **validation queue**，不直接宣称 interaction。
- `segment_discriminator_afuel_d_06_segment_dp` / `segment_discriminator_achar_d_05_segment_dp`：预期违背在车型结构段内仍有 76.0 / 118.1 点幅度 spread；作为 C5 主题的分层验证信号，不新增独立 Topic。

本轮合并产物：`scratch/discovery/_signals_round2.json`。Interaction Pilot 已执行 9 个预注册 tests，但因 `SEGMENT_DP` coverage 不足未产生正式 interaction evidence。

### Signal → Candidate → Topic Qualification

Round 2 qualification 已落盘：`reports/signal_to_topic_qualification_round2.md`。

- **T9 Expectation Calibration**：**READY · terminal**；补能预期兑现已落到具体 item，是 T7 行为分群之外的独立机制。
- **T10 Mileage Experience Lifecycle**：**INCONCLUSIVE · terminal**；NEV_12 非线性及 AFUEL/item 回落成立，但不足以支持总体质量衰减叙事。
- 车型结构段 discriminator：进入 T7/T9 validation queue，不新增 Topic。

### Interaction Gate

第四类 `interaction` 已通过 Gate Review，并完成首轮 9 个预注册 tests；但 `SEGMENT_DP` 在 exposure 两侧各自 `n≥100` 的严格门槛下覆盖不足，未产生正式 interaction evidence。没有降低门槛，也没有新增 Candidate/Topic。详见 `reports/interaction_discovery_gate_review.md` 与 `reports/interaction_pilot_round1.md`。

---

## Round 1 + Round 2 Discovery Engine Retrospective

完整复盘已落盘：`reports/discovery_engine_retrospective_round1_round2.md`。

### Analysis Type Role

| Analysis Type | 最终角色 | 默认产出 |
|---|---|---|
| `main_effect` | Round 1 宽扫描，建立 Signal Board 优先级 | Signal，不直接建 Topic |
| `expectation_wow` | 预期兑现/失望机制 scanner | Candidate，需 item qualification |
| `nonlinear_pattern` | 台阶、阈值、生命周期结构 scanner | Candidate，需稳健性与归因 qualification |
| `segment_discriminator` | heterogeneity / moderator 线索 scanner | Validation Queue，不是 interaction evidence |
| `interaction` | 已有 parent Signal 的 confirmatory moderator pilot | 默认 refinement，极少数情况下才 Candidate |

### Gate Decision

所有新 Signal 必须依次通过：`Registration → Coverage → Interaction block/HC1/FDR → Business effect → Mechanism → Incremental explanation → Tournament`。Interaction 的 `SEGMENT_DP` 首轮因 exposure 两侧各自 `n≥100` 的 cell gate 未通过，不能降门槛或把 spread 当作正式证据。

### Budget Decision

- 保留 Multi Scanner → Signal Contract → Signal Board → Candidate Allocation → Qualification。
- Round 1 main effect 保持宽覆盖，但不无边界扩展变量池。
- Round 2 scanner 继续按机制簇分配预算；T9 `READY`，T10 `INCONCLUSIVE`，segment discriminator 留在 validation queue。
- 当前 `SEGMENT_DP` Interaction queue 暂停；全量 O(p²) 不开放。
- 只有预先定义 segment 聚合、切换到 coverage 更充分的 moderator，或新数据使 cells 达标后，才重新过 Gate。

### Discovery Engine v1 Freeze / Replay

- v1 已冻结：`reports/discovery_engine_v1_freeze.md`。
- 当前 snapshot replay 已完成：`reports/discovery_engine_v1_replay.md`。
- Replay 复现 25 个 Round 1 axes、10 个 Round 2 Signals 和 9 个 Interaction Pilot tests；T9/T10 的既有终局分流保持不变，Interaction 仍为 `INSUFFICIENT_COVERAGE`。
- 该 replay 证明的是同一 snapshot 的可复现性，不是跨数据 wave 的泛化验证；新数据批次到来后应原样重跑，不在 v1 内调参追随结果。
