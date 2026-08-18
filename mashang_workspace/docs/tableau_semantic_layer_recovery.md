# Tableau 遗留 BI 系统：语义层恢复笔记

> 记录 2026-08-18 TP&MIX-ways（原 passenger_insurance）数据集全量恢复事件中沉淀的工程认知。
> 适用于以后处理 Tableau / Power BI 类遗留 BI 系统的数据恢复与重建。

## 核心洞察：.hyper 是事实层，.twb 是语义层

遗留 Tableau 系统里，"数据"并不是单一实体，而是分层的：

| 层 | 载体 | 保存什么 |
|----|------|----------|
| **事实层** | `.hyper` extract（或发布的数据源） | 最细粒度的原始记录（本案例 1229 万行，城市 × 车型 × 月度） |
| **语义层** | `.twb` / `.tds` workbook 定义 | 大量**没有进入原始数据表**的业务计算定义 |
| **展示层** | worksheet / dashboard | 视图组织、日期过滤、度量展示 |

**恢复数据时不能只找底表**，必须同时恢复语义层。本次事故中最难复刻的
恰恰不是 1229 万行原始数据，而是 .twb 里的这些业务定义：

### .twb 里典型会出现的语义定义

1. **维度分组（categorical-bin）**：品牌 → 传统自主/新势力/自主新品牌；品牌 → 非豪华/其他豪华/新豪华/BBA（189 个品牌的手写映射）；省 → 七大区域；车型级别 → A/A0/B/C/D。
2. **燃料/驱动归类**：燃料类型 → 新能源/其他能源；几十种驱动写法 → 前驱/后驱/四驱。
3. **字段别名（alias）**：如 `25年城市级别` 的 NULL → "四五线"（别名在数据导出时生效，最隐蔽）。
4. **计算字段（calculation）**：加权均价 `SUM(TP*销量)/SUM(销量)`、加权尺寸；特定车型的级别/驱动/命名覆盖（问界M9→四轮、智己L6→B、SU7→小米SU7 等）。
5. **视图级过滤**：相对日期过滤（`relative-date`），这是"view 只导出最近 N 月"的根因。

## 推荐恢复流程（本次验证有效）

1. **下载 workbook（.twbx）**：`GET /sites/{site}/workbooks/{id}/content`，取其中 .twb 解析。
2. **下载发布数据源（.hyper）**：`GET /sites/{site}/datasources/{id}/content`；用 `tableauhyperapi` 读取。
3. **从 .twb 提取语义定义**：bin / alias / calculation / filter 全部结构化导出。
4. **在 Hyper 引擎内复刻聚合**：把语义定义翻译成 SQL CASE 表达式，`GROUP BY` 直接算出各 view 的表（避免把 1229 万行拉回 Python）。
5. **用当月 view 导出做验证**：让现有 view 导出最近一个月数据，与重建结果逐 grain、逐值对比，0 差异后才算口径一致。
6. **全量重建**：去掉日期过滤跑全量，写入 raw → 走既有 build pipeline 生成 parquet / registry / quality。

## 对 Power BI 的类比

Power BI 对应物：`.pbix` 里的 Power Query（M）、计算列/度量（DAX）、字段别名与排序、
行级安全。恢复 Power BI 数据时同样**不能只导底表**，需保留 DAX 度量与 M 清洗逻辑。

## 本次事件的教训

- **不要用"当前月 raw 导出"全量重建历史**：Tableau view 的日期过滤会让 raw 只有最近月份，
  全量 rebuild 会覆盖掉历史 parquet（本案例即因此丢失 2020-01 ~ 2026-06 数据）。
  历史数据只存在于 .hyper extract 或逐月累积的 parquet 中。
- 恢复链路应保留为可重复的脚本（下载 extract → 提取语义 → SQL 聚合 → 验证 → 重建），
  而不是一次性临时脚本。
- `tableauhyperapi` 属于低频恢复工具，不应进入主 `requirements.txt`；若恢复路径产品化，
  建议单独维护 `requirements-data-recovery.txt` 或 optional dependency。
