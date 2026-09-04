# T9 Production Readiness｜预期兑现不是参数，而是体验承诺管理

## 决策

**进入最终 Production 报告，但作为 T1 Champion-led 报告的 supporting module，不独立取代 T1，也不升级为新的 Champion。**

推荐叙事：

> 用户评价的不是“参数写了多少”，而是车辆是否兑现了购车时对续航和充电时长的预期；兑现后的价值会落到充电便利、状态可读和总体充电体验。

## 研究问题

T9 原有证据已经显示，续航预期（`AFUEL_D_06`）与充电时长预期（`ACHAR_D_05`）在控制结构、价格、品牌和人口变量后仍分别关联 APEAL。本轮只补一个 Production Gate：

> 在剔除 `99` 等无效值、同时纳入两类预期 exposure 后，是否仍能稳定映射到具体产品体验 item？

## 数据与方法

- 数据源：`data/source.sav`
- 样本：有效预期档位 1/2/3 的共同样本 `n=8,524`
- 权重：`APEAL_WT`
- 结果：`APEAL_Index`、`AFUEL_Index`、`ACHAR_index`、`AFUEL_R_01`、`ACHAR_R_01`、`ACHAR_R_09`
- 模型：WLS + HC1；两类 exposure 同时进入模型，档位 2（About as expected）为参照
- 控制：`SUPER_SEGMENT_DP`、`CN_YNV_07`、`PREMMAKE_DP`、`AGE_BUCKETS`、`CN_INCOME`、`CN_EDUCATION`
- 有效值规则：只保留 1/2/3；不将 `99` 当作真实预期类别

完整结果见：

- `research/runs/expectation_calibration_production/evidence.jsonl`
- `scratch/t9_production_readiness.json`
- `scratch/t9_production_readiness.py`

## 核心证据

| 结果 | 续航预期 Better | 充电时长预期 Better | 解释 |
|---|---:|---:|---|
| `APEAL_Index` | +19.64，p<0.001 | +39.76，p<0.001 | 两类预期都连接总体拥有体验 |
| `AFUEL_Index` | +37.86，p<0.001 | +48.00，p<0.001 | 预期兑现不只是叙事变量，落在补能模块 |
| `ACHAR_index` | +13.60，p<0.001 | +42.80，p<0.001 | 充电时长预期对充电模块更直接 |
| `AFUEL_R_01` | +0.3786，p<0.001 | +0.4800，p<0.001 | 纯电续航总体表现 |
| `ACHAR_R_01` | +0.0892，p=0.184 | +0.4325，p<0.001 | 充电口设计与操作便利性主要承接充电时长预期 |
| `ACHAR_R_09` | +0.2817，p<0.001 | +0.5645，p<0.001 | 总体充电体验是最稳定的承接 item |

Worse 方向在总体、模块和关键 item 上也反向出现。例如充电时长 Worse 对 `ACHAR_R_09` 为 `-0.6328`，说明预期落差具有惩罚方向，而不是只有 Better 群体的正向选择偏差。

## 业务解释

T9 最有价值的地方不是再次证明“续航重要”，而是把补能从参数问题改写为**承诺兑现问题**：

1. 续航预期主要对应续航总体表现与整体 APEAL。
2. 充电时长预期更直接落到充电口操作便利性与总体充电体验。
3. 因此产品与传播不应只管理“标称续航 / 峰值充电速度”，还要管理用户实际感知的等待、操作和状态反馈。
4. 这与 T1 的主线一致：体验升级不是参数堆叠，而是用户能否明确感受到承诺被兑现。

## Production 边界

### 可以写入

- 预期兑现是一个独立且有业务解释力的体验机制。
- 充电时长预期可落到充电口便利性和总体充电体验。
- 续航预期可落到续航总体表现，并与整体拥有体验相连。
- 它适合作为 T1 之后的产品定义与体验管理模块。

### 不可以写成

- 某个宣传承诺必然造成更高 APEAL。
- 某项具体配置的因果 ROI。
- 纵向使用后体验一定衰减或改善。
- T9 已经超过 T1 成为 Champion。

## 最终判断

**T9 值得进入 Production 报告，角色为 supporting module。**

它通过本轮 Production Gate，状态为 `READY`，但 Tournament 身份不变：T1 仍是 Champion；T9 负责补上“如何把参数升级转化为被用户感知的体验兑现”的机制层。

Evidence：`E-001`、`E-002`。Stop-check：`READY`，全部 5 个 gate 通过。
