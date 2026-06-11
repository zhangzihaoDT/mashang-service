# Analysis Playbook — 分析范式

## 锁单分析

```
总量 → 车型 → 城市 → 渠道 → 时间趋势
```

1. 先确认时间窗口（昨天 / 近7日 / 本月）
2. 查询锁单总量
3. 按 `series` / `product_name` 拆解
4. 按 `store_city` / `license_city` 拆解
5. 按渠道来源拆解（门店/平台/直播/APP小程序/快慢闪）
6. 观察随时间变化的趋势

**参考脚本**：
- `scripts/daily_lock_count.py` — 锁单总量查询
- `scripts/lock_by_model.py` — 按车型/车系拆解
- `scripts/lock_city_distribution.py` — 按城市/大区分
- `scripts/skills_order_observation_daily.py` — 每日观察报告

**典型命令**：
```bash
python scripts/daily_lock_count.py --date 2026-06-01 --series LS8
python scripts/lock_by_model.py --start-date 2026-06-01 --end-date 2026-06-10 --limit 5
python scripts/lock_city_distribution.py --date 2026-06-01 --series LS8 --by-region
```

## 结构分析

```
总量 → 分组占比 → TopN → 变化趋势
```

1. 确认分析对象和分组维度
2. 计算各分组绝对值
3. 计算占比（share）
4. 取 TopN 分组
5. 观察占比变化趋势（按周/按月）

**工具**：`CompositionTool` (`tools/composition_tool.py`)
- `share_by_dimension` — 简单分组占比
- `weekly_share_by_dimension` — 按周分组占比
- `topn_share` — TopN 占比
- `cumulative_share` — 累计占比

**参考脚本**：`scripts/lock_by_model.py`（支持 --limit 控制 TopN）

## 异常分析

```
发现波动 → 拆时间 → 拆车型 → 拆城市 → 拆渠道
```

1. 确认异常的时间点和幅度
2. 按日/周拆解时间趋势，定位波动区间
3. 按车型/车系拆解，找出波动的主要贡献者
4. 按城市/大区拆解，确认地域分布
5. 按渠道拆解，确认渠道差异

**工具**：
- `StatisticsTool.trend_summary` — 趋势摘要
- `StatisticsTool.contribution_summary` — 贡献拆解

## 释放曲线分析 (Cohort Release Curve)

```
assign cohort → lock day_after → cumulative rate → forecast
```

1. 按 `first_assign_time` 分组 cohort
2. 计算每个 cohort 在 D0~D60 的锁单累积率
3. 按 cohort 规模加权得到平均释放曲线
4. 使用历史成熟 cohort 推算 r0/r7 基线
5. 对未成熟 cohort 进行三段式预测

**参考脚本**：
- `scripts/release_curve_analysis.py` — 释放曲线包装器
- `scripts/lock_release_curve.py` — 核心分析 (701 行)
- `scripts/lock_predict_backtest.py` — 回测验证

**参考文档**：`scripts/lock_release_analysis.md`

**典型命令**：
```bash
python scripts/release_curve_analysis.py
python scripts/release_curve_analysis.py --output outputs/reports/
```

## VOC 分析 (Voice of Customer)

```
原文 → issue → JTBD → need_theme → 证据
```

1. 获取微信群聊/调研原文数据（`dataset/wechat/*.parquet`）
2. 提取用户反馈的具体 issue
3. 归类为 JTBD（Jobs To Be Done）
4. 聚合为 need_theme
5. 输出典型原文证据

**数据源**：`dataset/wechat/销售全员群.parquet` 等

**参考脚本**：`scripts/voc_theme_analysis.py`（当前为骨架，含基本词频统计）

**典型命令**：
```bash
python scripts/voc_theme_analysis.py
python scripts/voc_theme_analysis.py --model "LS8" --format csv
python scripts/voc_theme_analysis.py --group 销售全员群 --start-date 2026-06-01
```

## ATP 价格分析

```
时间窗口 → 筛选用户车 → 平均开票价格 → 车型分组对比
```

1. 确认时间窗口（按月/按季度）
2. 筛选 `order_type='用户车'` 且 `invoice_amount > 0`
3. 计算全局 ATP
4. 按 `series_group_logic` / `product_type` / `product_name` 分组
5. 对比各车型/系列 ATP 差异

**参考脚本**：`scripts/skills_atp_price.py`

**典型命令**：
```bash
python scripts/skills_atp_price.py 2026-05
python scripts/skills_atp_price.py 2026-05 --output outputs/reports/atp_2026-05.html
```

## 渠道结构分析

```
总线索 → 分渠道线索 → 分渠道转化率 → 渠道结构变化
```

1. 查询总下发线索数
2. 按渠道拆分（门店/平台/直播/APP小程序/快慢闪）
3. 计算各渠道线索占比
4. 计算各渠道的试驾率/锁单率
5. 观察渠道结构随时间的变化趋势

**工具**：`operators/assign_conversion.py`
**参考脚本**：`scripts/skills_order_observation_daily.py`（含线索转化分析）

## 配置渗透率分析

```
车型筛选 → 选配属性匹配 → 渗透率计算 → 分组对比
```

1. 确定分析车型和时间窗口
2. 匹配配置属性（激光雷达/地暖/轮毂等）
3. 计算二值渗透率（是/否）或多值分布
4. 按车型/系列分组对比

**工具**：`tools/multitable_metric_tool.py`
**模板库**：`tools/config_cross_analysis_templates.py` (17 个模板)

## 数据字典查询

```
确认可用数据集 → 查看字段清单 → 确定字段名和类型
```

**参考脚本**：`scripts/data_dictionary.py`

```bash
# 查看所有数据文件的字段信息
python scripts/data_dictionary.py

# 输出 CSV 供后续查阅
python scripts/data_dictionary.py --format csv --output outputs/tables/
```

## 输出文件规范

所有脚本的输出遵循以下目录结构：

| 输出类型 | 目录 | 格式 |
|----------|------|------|
| 分析报告 | `outputs/reports/` | HTML / Markdown |
| 图表 | `outputs/charts/` | PNG / SVG / HTML |
| 结构化数据 | `outputs/tables/` | CSV / JSON / Parquet |

文件命名建议：`YYYYMMDD_主题_口径.{csv,json,html}`
