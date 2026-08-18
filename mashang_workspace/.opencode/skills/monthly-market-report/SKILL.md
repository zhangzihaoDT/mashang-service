---
name: monthly-market-report
version: "0.1"
scope: single_table_monthly_market_report
description: workspace 层的月度汽车市场报告生成 Skill。基于 TP&MIX-ways 现有 6 张预聚合单表，按月运行 24 个固定月报查询问题，输出结构化数据底稿和报告草稿。
---

# monthly-market-report v0.1

## 能力定位

monthly-market-report v0.1 是基于 `TP&MIX-ways` 现有 6 张预聚合单表的月度汽车市场固定主查询能力。

按照固定的 24 个查询问题，按月生成市场月报数据底稿和结构化报告草稿。

数据来源：`shared.loaders.tp_and_mix_ways_loader`（6 张 Parquet 表）

### v0.1 支持范围

- 整体市场
- 新能源市场
- 能源形式
- 细分市场
- 城市线级结构
- 区域市场
- 中高端市场
- 成交价与价位段
- 品牌 / 车型在现有单表可支持范围内的排名

### v0.1 不支持范围

- city×brand 城市内品牌排名
- city×model 城市内车型排名
- city×price_band×brand 城市×价位段×品牌交叉分析
- brand×city_tier 品牌×城市线级交叉分析
- region×model 区域×车型排名
- TOP50 车型散点分布图
- 完整竞争格局页复刻

## 触发场景

当用户说类似下面的话时，应使用该 Skill：

- 生成某月汽车市场报告
- 跑某月市场报告固定问题
- 运行月报 24 个固定问题
- 生成 ways / TP&MIX 月报底稿
- 生成乘用车市场月报数据查询结果
- 跑 monthly market report

## 不适用场景

以下类型的问题不属于 v0.1 范围，不应使用本 Skill：

- city×brand 城市内品牌排名
- city×model 城市内车型排名
- city×price_band×brand 城市×价位段×品牌交叉分析
- brand×city_tier 品牌×城市线级交叉分析
- region×model 区域×车型排名
- TOP50 车型散点分布图
- 完整竞争格局页复刻
- 临时专题分析
- 重点城市专题分析
- 南北方专题分析
- 历史城市附录

上述需求可作为后续 `market-competition-cross-analysis` 能力或 optional query group 扩展，不进入 v0.1 固定主流程。

## 默认输出位置

```
mashang_workspace/outputs/monthly_market_report/YYYY-MM/
```

## Agent 执行步骤

当用户触发该 Skill 时，OpenCode 应按以下流程执行：

### 1. 读取查询规范

从 `mashang_workspace/configs/monthly_market_report_queries.yaml` 加载 24 个固定查询定义。

### 2. 解析月份参数

根据用户指定的月份（如"2026 年 5 月"或 "2026-05"），计算以下时间参数：

| 参数 | 示例 (2026-05) |
|------|----------------|
| `report_month` | 2026-05 |
| `month_start` | 2026-05-01 |
| `month_end` | 2026-05-31 |
| `ytd_start` | 2026-01-01 |
| `ytd_end` | 2026-05-31 |
| `last_year_month_start` | 2025-05-01 |
| `last_year_month_end` | 2025-05-31 |
| `last_year_ytd_start` | 2025-01-01 |
| `last_year_ytd_end` | 2025-05-31 |
| `rolling_12m_start` | 2025-06-01 |
| `rolling_12m_end` | 2026-05-31 |

### 3. 执行查询

调用 runner 脚本：

```bash
python mashang_workspace/research_scripts/market_report/run_monthly_market_report.py \
  --month YYYY-MM \
  --query-spec mashang_workspace/configs/monthly_market_report_queries.yaml \
  --output-dir mashang_workspace/outputs/monthly_market_report/YYYY-MM
```

支持的模式：

```bash
# dry-run 模式（默认）：只解析查询规范，不执行实际数据查询
python .../run_monthly_market_report.py --month 2026-05 --dry-run

# execute 模式：执行实际数据查询
python .../run_monthly_market_report.py --month 2026-05 --execute
```

### 4. 检查输出文件

成功执行后，应生成以下文件：

| 文件 | 说明 |
|------|------|
| `query_results.json` | 24 个查询的完整结构化结果（Result Contract 格式） |
| `query_results.xlsx` | 多 sheet Excel 底稿 |
| `report_draft.md` | 报告草稿（可读的 Markdown 汇总） |
| `run_metadata.json` | 运行元信息（时间参数、查询数量、成功/失败统计） |

如存在 HTML 渲染脚本，可额外生成：
- `report_summary.html` — 品牌化 HTML 报告摘要

### 5. 汇报结果

向用户汇报：

- 本次运行月份
- 成功执行的问题数量
- 失败/跳过的问题数量
- 输出文件路径
- 需要人工确认的数据口径

### 6. 后续可选项

如需进一步渲染为品牌化 HTML 报告，可调用 `branded-html-report` Skill，使用 `templates/` 下的模板进行渲染。

## Skill 边界

- Skill 不直接承载指标计算逻辑。
- 指标计算应放在 `research_scripts/market_report/run_monthly_market_report.py` 脚本中。
- 24 个固定问题应放在 `configs/monthly_market_report_queries.yaml`（Query Spec）中。
- Skill 只负责告诉 Agent 什么时候用、怎么跑、如何检查结果。
- 临时专题、重点城市、南北方专题、历史城市附录不进入固定主流程。

## 引用文件

| 文件 | 用途 |
|------|------|
| `configs/monthly_market_report_queries.yaml` | 24 个固定查询问题规范 |
| `research_scripts/market_report/run_monthly_market_report.py` | 查询执行入口脚本 |
| `shared/loaders/tp_and_mix_ways_loader.py` | 数据加载器 |
| `shared/schema/tp_and_mix_ways_schema.py` | 数据表结构定义 |
| `docs/tp_and_mix_ways_usage.md` | 数据资产使用指南 |
| `utils/paths.py` | 路径工具 |
| `utils/result_contract.py` | Result Contract 构建工具 |
| `outputs/monthly_market_report/` | 月报输出目录 |

## 不涉及的行为

- 不承载指标计算逻辑（由 runner 脚本实现）
- 不修改 TP&MIX-ways 数据资产
- 不复制或移动 dataset/ 下的原始数据
- 不修改 mashang_runtime/ 中的任何文件
- 不引用具体历史报告名称
