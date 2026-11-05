# Lock Release Curve 计算逻辑

7 个计算步骤 → 1 个 HTML 报告 (`lock_release_curve.html`)

---

## Step 1 — 数据加载

```
order_data.parquet (466,771 orders)
  ↓ 过滤有 first_assign_time AND lock_time
rc_raw (208,127 orders)
  ↓ 计算 day_after = lock_date - assign_date
  ↓ 截取 [0, 60] 天
  最终数据
```

核心映射：每个订单的 `(assign_date, day_after)` 二元组，表达"这批订单分配后第 N 天锁单"。

---

## Step 2 — 逐 Cohort 释放曲线

按 `assign_date` 分组，每个 group 是一个 cohort：

```
for each cohort:
  total_30 = len(group)
  for d in [0, 1, ..., 60]:
    cum_pct[d] = (#orders with day_after <= d) / total_30
```

每条曲线从 0 → 1 单调递增。过滤条件：
- **成熟 cohort**：`assign_date ≤ cutoff - 60`（距今天 ≥ 60 天，完整观察窗口）
- **≥ 5 个订单**（排除噪声）

输出：1,190 条 cohort 曲线。

---

## Step 3 — 加权平均释放曲线

按 cohort 大小加权平均（大 cohort 权重更高，更稳定）：

```
avg_curve[d] = Σ(cohort_i.cum_pct[d] × cohort_i.total_30) / Σtotal_30
```

衍生指标：
- `daily_marginal[d] = avg_curve[d] - avg_curve[d-1]` — 每日边际释放率
- `cum_at_30 = avg_curve[30]` — 30 天归一化基线
- 报告时统一转为 `% of 30-day total`

输出示例：
```
Day  0: cum=44.0%  marg=44.02%
Day  1: cum=53.3%  marg= 9.30%
Day  7: cum=72.7%  marg= 2.48%
Day 30: cum=100.0% marg= 0.76%
Day 60: cum=113.0% marg= 0.23%
```

---

## Step 4 — 逐年对比

将 cohort 按年份分组，每组内再做加权平均：

```
for each year y:
  year_avg[y][d] = Σ(cohort_i.cum_pct[d] × cohort_i.size) / Σsize_i
```

用于观察释放曲线是否随时间变化。

输出示例：
```
Year   Cohorts   Orders     D0%     D7%    D30%
2023      365    31,756   30.3%   60.9%   90.6%
2024      366    61,034   52.7%   81.1%  103.3%
2025      365    85,946   41.7%   70.0%  100.6%
```

---

## Step 5 — 百分位分析

将全部 1,190 条 cohort 曲线堆叠为矩阵 `(1190 × 61)`：

```
curve_matrix[cohort_idx][day] = that cohort's cum_pct[day]
percentiles[p][day] = np.percentile(curve_matrix[:, day], p)
```

- **P10/P90** = 不确定性带（跨 cohort 变异）
- **P50** = 中位数 vs 加权平均（偏态检验）
- **P90-P10 spread** = 量化 cohort 间差异

输出示例：
```
Day  0: P10=12.5%  P25=33.9%  P50=47.6%  P75=59.3%  P90=69.1%  spread=56.6pp
Day  7: P10=31.6%  P25=70.3%  P50=84.4%  P75=92.9%  P90=99.6%  spread=68.0pp
Day 30: P10=81.2%  P25=98.0%  P50=105.8% P75=109.3% P90=110.9% spread=29.8pp
```

---

## Step 6 — Logistic 曲线拟合

模型：`y = L / (1 + exp(-k × (x - x0)))`

纯 numpy 实现，分两步：

### ① 线性化初始值

```
z = ln(L_init / y - 1) = -k × x + k × x0
```

只用 `y ∈ (5%, 95% × L_init)` 区间的数据做 `polyfit`，得到 k、x0 的近似值。

### ② Levenberg-Marquardt 精化

3 参数全部优化（L, k, x0）：

| 参数 | 含义 | 约束 |
|------|------|------|
| L | 渐近线（60天总量） | [50, 150] |
| k | 增长率 | [0.001, 5] |
| x0 | 拐点位置（天） | [0, 60] |

每步计算 Jacobian：
```
∂f/∂L   = 1 / (1 + e^{-k(x-x0)})
∂f/∂k   = L·x·e^{-k(x-x0)} / (1+e^{-k(x-x0)})² - L·x0·e^{-k(x-x0)} / (1+e^{-k(x-x0)})²
∂f/∂x0  = -L·k·e^{-k(x-x0)} / (1+e^{-k(x-x0)})²
```

阻尼高斯-牛顿更新：
```
Δp = (JᵀJ + λ·diag(JᵀJ + ε))⁻¹ · Jᵀ · r
λ 自适应: cost↓则 λ×=0.3, cost↑则 λ×=3
```

跟踪历史最优解，若首次 RMSE > 5pp 自动用第二组初值重试。

输出：
```
y = 112.7 / (1 + exp(-0.0737 × (x - 0.47)))
RMSE = 2.06pp
```

---

## Step 7 — 星期效应

按 `assign_date.dayofweek` 分组 cohort，每组加权平均。

```
Mon vs Tue vs ... vs Sun
```

输出示例：
```
DOW   Cohorts   Orders    D0%     D7%    D30%
Mon     169     23,040   44.7%   75.2%   99.7%
Fri     169     24,475   34.4%   66.8%   95.9%
Sat     170     34,633   50.0%   76.7%  101.6%
Sun     170     34,866   56.1%   80.6%  102.8%
```

周末分配 → 更快锁单（用户有更多时间决策）。

---

## Step 8 — 边际衰减分析

```
Day 0 边际释放率 ≈ 44%/d
边际率降到 Day 0 的一半 → Day 1（次日即半衰）
累计达 50% 的 30 日总量 → Day 1
累计达 80% 的 30 日总量 → Day 12
累计达 90% 的 30 日总量 → Day 20
```

用 `np.searchsorted(avg_curve, target_value)` 实现。

---

## Step 9 — HTML 报告

随机采样 500 个 cohort（性能优化），所有数据打包为 JSON → Plotly.js 渲染 6 个交互图表：

| 图表 | 数据来源 | 目的 |
|------|---------|------|
| 主曲线 | avg_curve + daily_marginal | 累计% + 边际% 双轴 |
| 逐年对比 | year_avg | 曲线稳定性 |
| 散点图 | 500 cohort 的 D0/D7/D14 | cohort 级变异 |
| 百分位带 | P10/P50/P90 | 不确定性量化 |
| Logistic 拟合 | 拟合曲线 vs 实际 | 参数化建模 |
| 星期效应 | DOW 分组曲线 | 周内差异 |

输出：`lock_release_curve.html`

---

## Step 10 — Lead→Lock 传导时滞分布

直接利用逐单级别的 `assign_date` 和 `lock_date`，计算从分配到锁单的真实传导时间分布。

不再通过时间序列相关反推，而是直接计算：

```
Δ = lock_date - assign_date  (day_after)
```

### 核心统计量

| 指标 | 含义 | 计算 |
|------|------|------|
| Mean | 平均传导时滞 | `np.mean(day_after)` |
| P50 | 中位传导时滞（一半订单在此天数内锁单） | `np.median(day_after)` |
| P80 | 80% 订单在此天数内锁单 | `np.percentile(day_after, 80)` |
| P90 | 90% 订单在此天数内锁单 | `np.percentile(day_after, 90)` |

输出示例：
```
  Metric     Value
    Mean     5.23d
     P50     1.00d
     P80     7.00d
     P90    24.00d
```

### 逐年对比

按 `assign_date` 年份分组，分别计算各年的 Mean/P50/P80/P90，观察传导时滞是否随时间缩短或延长。

### 设计思路

- 相比时间序列交叉相关（相关性 ≠ 因果时滞），直接统计 `day_after` 分布更准确、更直观。
- 43.9% D0 锁单率已有力证明"当日转化"是核心特征，Step 10 在此之上量化完整的传导时间谱。
- P50 << Mean 说明分布右偏严重（大量 D0 拉低了中位值，长尾订单拉高了均值）。

---

## 关键设计决策

1. **60 天窗口**而非 30 天 — 观察超过 30 天后的"长尾释放"（60 天达 113% of 30-day）
2. **按 cohort 大小加权** — 避免小 cohort 的随机波动扭曲平均
3. **归一化到 30 天总量** — 消除不同 cohort 转化率本身的差异，聚焦释放节奏
4. **手动 LM 实现** — 不用 scipy，降低部署依赖，且精确控制参数边界
5. **30 天归一化基线** — `cum_at_30 = avg_curve[30]` 作为分母，与业务口径"30 日锁单"对齐
