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

**Trigger**：26 轴扫描 → 4 Candidate → T7+T8 两轮正式研究 → 2 READY。评估 Signal→Topic 漏斗有效性。

### Q1. Signal Board 排名是否有效？—— ✅ 有效

- **排名 vs 结果**：T7（22 分，Tournament #3）与 T8（17 分）均产出高质量 READY Finalist。前两名 22/17 分排序正确。
- **T8 例外注意**：17 分最低之一却是 READY —— 分数低是因**机制负面**（无品牌级残余）而非证据弱；Signal Board 的 actionability 维度未能预判"研究即证伪"的收尾方式。**非缺陷**：证伪也是预算的有效使用。

### Q2. Signal → Topic 转化率？—— ✅ 高效

| 层级 | 数量 | 存活率 |
|---|---:|---:|
| 扫描轴 | 26 | 100% |
| Candidate（confounder 初筛后入池） | 4 | 15% |
| 激活为主研究 | 2 | 50%（T7/T8） |
| READY Finalist | 2 | 100%（激活后） |

- 26→4：初筛截断 85% 浅层候选（教育/职业重叠 T3、年龄=T2、地理机制弱），**未浪费深度研究预算**。
- 4→2→2：激活即 READY，无中途流产；浅层候选转 C3/C4 或观察位，未消失。

### Q3. 剩余 Candidate 怎么处理？—— 重新判据，不机械升级

**判据**：控制 T7 暴露（NEV08+FULL）后，是否仍有独立残差（anova 联合检验）。

| 候选 | 独立残差 | 判定 | 处理 |
|---|---|---:|---:|
| **NEV_12（累积里程）** | F=11.2, p<0.001；5-10k −14.0 / 10-20k −21.4 非单调 | **独立"蜜月/衰减"问题** | C3 · 保留为 Candidate，需 nonlinear 工具；**不标记 ABSORBED** |
| **NEV_11C（家庭场景）** | 仅"每日使用"单格 +27.8 (p=0.0006, n=289)，余 4 档不显著 | **弱/机制不清** | C4 · 观察位，暂不升级 |

- **NEV_12 未吸收**：T7 H5 中作为控制变量消费（suppression 结构：里程高→快充依赖者体验低），但其独立于 NEV08 的非单调衰减方向（10k-20k 低谷）是 T7 不覆盖的独立问题。
- **NEV_11C 边界**：仅在"每日使用"小格有独立效应，且"熟悉度 vs 车型结构"机制未拆——不足独立成题，保留观察。

**漏斗闭环**：26 Signals → 4 Candidates → 2 Activated → 2 READY，另 2 Candidate 按独立残差判据分流（1 保留 / 1 观察），无 ABSORBED 标记。下一轮扫描（新数据批次）再决定 C3 是否升级。
