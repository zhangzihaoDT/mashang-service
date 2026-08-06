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

### 配置表 value_code 解析规则

`config_attribute.parquet` 为 EAV 长表，字段：`Attribute`（属性名）、`value`（显示名）、`value_code`（配置 code）、`required`、`price`。

**核心规律：`value_code` 是配置的唯一稳定标识，`value` 是显示名。**

- 同一 `(Attribute, value_code)` 在不同车型/批次下可能对应多个显示名，需按 value_code 归并（取出现最多者），例如：
  - `激光雷达 | Stand`：LS6 显示为"标准+Orin"/"标准"
  - `内饰 | IN2-AMA`：LS9 显示为"大地象灰 浅"，LS8 显示为"大象灰米"
  - `外饰 | EX1-PYX`：LS9 显示为"奥林匹斯黑"，LS8 另有"星耀黑"
- value_code 语义（跨属性通用档位）：`Y`=是、`N`=否、`Stand`=标准、`Pro`=高阶、`Plus`=增强
- 渗透率判定：`value_code` 为 `N` 或 value 为"否/无/未选" → 未含；`Y`/`Stand`/`Pro`/`Plus` 等档位码 → 含；value_code 缺失时回退 value 文本判断

### "已选"聚合属性（LS8 独有）

**`已选` 是 LS8 车型独有的 Attribute 名**（截至当前数据仅 LS8 有，17,933 单），用于编码 LS8 的配置包/核心配置。它有 3 个 value_code，各有对应的 value 显示名：

| value_code | value（显示名） | 含义 | 参考价 |
|------------|----------------|------|--------|
| `Stand` | 超远距高精度激光雷达 | LS8 标配激光雷达 | 0 |
| `Pro` | 奢华智选包 | 付费选装包 | 4800~9800 |
| `Plus` | 奢华智选包及一体式超广域探射灯 | 付费选装包 + 探射灯 | 13600 |

注意：
- 部分历史行 value_code 为空（2874 行），但 value 显示名仍可识别，按 value 文本判断
- `Pro` 另有"奢华智选包+520雷达"（2 单）等变体显示名
- 分析激光雷达渗透率时，**必须下探"已选"的 value**：`已选=Stand`（超远距高精度激光雷达）即 LS8 标配激光雷达记录，不应遗漏
- 配套脚本：`runtime_scripts/attribute_penetration_report.py` 已按 `(Attribute, value_code)` 归并并覆盖"已选"属性

### 选装包业务展开（config_packages）与冲突消解

`shared/schema/business_definition.json` 的 `config_packages` 定义"选装包 → 实际配置集合"的业务展开：
已选某选装包（如 `已选=Pro` 奢华智选包）的订单，视为实际拥有包内 `included_configs` 列出的配置
（如 520线超视域激光雷达、B&O豪华音响、21寸轮毂＋马牌静音胎等）。

**冲突消解规则**（attribute_penetration_report.py）：
- 包内配置项若配置了 `attribute_match`（包内配置 → 独立属性行关键词），则检查订单的独立属性行：
  - 独立行 value 与包配置**一致**（如 21 寸轮毂 vs 21英寸星耀超多辐豪华轮辋）→ 由显式行计入
  - 独立行 value 与包配置**不一致**（如包定义 21 寸、实际选 22 英寸）→ 排除该订单，避免包展开误计
- 尺寸归一化：查询含"寸"的关键词同时匹配数据中的"英寸"写法（如"21寸"→"21英寸"）
- 结果中 `package_expanded_orders` 标注由选装包展开的订单数，`matched_packages` 标注命中的选装包

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
