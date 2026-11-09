# TP&MIX-ways Dataset — 乘用车上险数据

## 数据集定位

**Service 级共享数据资产。**

本数据集由 6 张 Tableau 导出的窄视图 CSV 构建而成，面向 workspace（及经 `jobs/` 调用的上层）提供标准化的乘用车上险数据（TP&MIX-ways Registration Data）查询能力。

### 分层

| 层 | 路径 | 说明 |
|----|------|------|
| Raw Input | `dataset/TP&MIX-ways/raw_csv/` | Tableau 导出的 6 张 CSV（Pivot 格式；落盘为 UTF-8 无 BOM、逗号分隔、CRLF；读取器兼容旧 UTF-16 LE / Tab 导出） |
| Parquet | `dataset/TP&MIX-ways/parquet/` | 6 张独立 grain 的 Parquet，由构建脚本生成 |
| Registry | `dataset/TP&MIX-ways/registry/tp_and_mix_ways_tables.json` | 表清单、grain、行数、日期范围 |
| Quality | `dataset/TP&MIX-ways/quality/` | 质量报告（Markdown + JSON） |
| Schema | `shared/schema/tp_and_mix_ways_schema.py` | 表定义（grain / dimensions / metrics / purpose） |
| Loader | `shared/loaders/tp_and_mix_ways_loader.py` | pandas / DuckDB 数据加载器 |

### 设计原则

- **不合并成一张宽表**：6 张表各有独立 grain，保持 Tableau 导出时的逻辑拆分，避免宽表冗余和歧义。
- **workspace 和 Hub（经 `jobs/`）只消费 Parquet/Registry**，不直接读 raw_csv。
- **loader 不硬编码本机绝对路径**，基于 `__file__` 向上推导 service root。

### Grain 契约

grain 是每张表的**全部自然键**，不是"看起来像主键的少数列"。Tableau 视图会按
所有权、厂商、国产进口、燃料、驱动等维度继续拆分同一品牌/车型的月销量；漏掉这些
拆分列会把合法行误报为重复，也会让 quality 的 duplicate 指标失去意义。

2026-11-04 的只读审计（现有 81 个月 Parquet）结果：

| 表 | 修复前 grain | 修复前重复行（占比） | 修复后 grain | 修复后重复行 |
|----|-------------|---------------------|-------------|-------------|
| `brand_monthly` | `date_month`, `brand` | 33,801 / 35,045（96.45%） | `date_month`, `brand`, `ownership_type`, `oem`, `domestic_import` | 0 |
| `model_monthly` | `date_month`, `brand`, `model`, `sub_model`, `sub_model_id` | 36,498 / 105,506（34.59%） | 原 grain + `drive_type`, `fuel_type` | 0 |

`ownership_type` 与 `drive_type` 必须进入 grain，但单独加入仍不足：brand 还需
`oem`、`domestic_import`，model 还需 `fuel_type`。修复前按旧 grain 统计到
brand 10,833 个、model 17,169 个"销量不一致"的重复键，本质都是合法维度拆分；
修复后重复键与真实冲突均为 0。审计还验证 `brand → brand_group/luxury/country`、
`drive_type → drive_type_group`、`fuel_type → fuel_type_group` 为函数依赖，
因此这些属性列不进入 grain。

---

## Tableau 6 张 Way CSV 的来源

| 文件 | 内容 |
|------|------|
| `way1_market_energy_monthly_data.csv` | 市场总量 × 能源结构 |
| `way2_brand_monthly_data.csv` | 品牌月度 × 厂商/国别/所有权 |
| `way3_model_monthly_data.csv` | 车型月度 × 燃料/级别/驱动/车身 |
| `way4_geo_monthly_data.csv` | 省市月度 × 城市线级/区域 |
| `way5_price_segment_monthly_data.csv` | 价格带 × 能源/车身/级别 |
| `way6_product_segment_monthly_data.csv` | 上汽细分市场 × 车身/级别/驱动/尺寸 |

所有 CSV 均为 **Pivot 格式**（度量名称 + 度量值两列）。当前正式 raw 落盘格式为
**UTF-8（无 BOM）、逗号分隔、CRLF**。构建脚本按文件头自动识别：UTF-16 BOM → Tab
分隔，UTF-8 → 逗号分隔，因此历史遗留的 UTF-16 LE / Tab 导出仍可读取；列顺序与
Tableau 表头别名由 `COLUMN_ALIASES` 归一化，不依赖列出现顺序。

> 2026-11-03 的增量导出只包含 2026-08、2026-09 两个月，却直接覆盖了 79 个月的
> 正式 raw；2026-11-04 已从备份恢复为 81 个月。为杜绝再次发生，正式 raw 写入统一
> 走下面的 staging → 校验 → 原子发布契约。

构建脚本 `scripts/build_tp_and_mix_ways_dataset.py` 自动完成 pivot widen、字段清洗、类型转换。

---

## 6 张 Parquet 表

### 1. market_energy_monthly

| 属性 | 值 |
|------|----|
| Parquet | `market_energy_monthly.parquet` |
| Grain | `date_month`, `fuel_type_group`, `fuel_type` |
| 度量 | `sales`, `weighted_tp` |
| 用途 | 市场总量、能源结构、新能源/燃油/纯电/插混/增程走势、价格重心 |
| 适合回答 | 月度乘用车市场总量趋势？新能源渗透率走势？纯电/插混/增程销量结构？各燃料类型价格重心变化？ |

### 2. brand_monthly

| 属性 | 值 |
|------|----|
| Parquet | `brand_monthly.parquet` |
| Grain | `date_month`, `brand`, `ownership_type`, `oem`, `domestic_import` |
| 维度 | `brand_group`, `brand_luxury_group`, `oem_group`, `oem`, `brand_country`, `ownership_type`, `domestic_import` |
| 度量 | `sales`, `weighted_tp` |
| 用途 | 品牌排名、品牌份额、品牌价格重心、品牌分组竞争 |
| 适合回答 | 月度品牌销量排名 Top20？豪华品牌市场份额变化？新势力品牌价格重心？自主/合资/豪华品牌分组对比？ |

### 3. model_monthly

| 属性 | 值 |
|------|----|
| Parquet | `model_monthly.parquet` |
| Grain | `date_month`, `brand`, `model`, `sub_model`, `sub_model_id`, `drive_type`, `fuel_type` |
| 维度 | `brand_series`, `fuel_type`, `fuel_type_group`, `body_type`, `vehicle_level`, `vehicle_level_group`, `saic_segment`, `drive_type`, `drive_type_group` |
| 度量 | `sales`, `weighted_tp` |
| 用途 | 车型排名、车型趋势、品牌内部车型结构、车型级别/燃料/驱动结构 |
| 适合回答 | 月度车型销量排名 Top20？品牌内部车型销量结构？各车型价格重心对比？车型级别 × 燃料类型的销量分布？ |

### 4. geo_monthly

| 属性 | 值 |
|------|----|
| Parquet | `geo_monthly.parquet` |
| Grain | `date_month`, `province`, `city`, `city_tier_group`, `fuel_type_group` |
| 维度 | `region_group`, `city_tier_2025` |
| 度量 | `sales`, `weighted_tp` |
| 用途 | 省市市场、城市线级结构、区域市场、新能源区域渗透 |
| 适合回答 | 省份月度销量排名 Top10？城市线级销量结构？华东/华南区域新能源渗透率？各城市价格重心差异？ |

### 5. price_segment_monthly

| 属性 | 值 |
|------|----|
| Parquet | `price_segment_monthly.parquet` |
| Grain | `date_month`, `tp_bucket_5w`, `tp_bucket_10w`, `fuel_type_group`, `body_type`, `vehicle_level_group` |
| 度量 | `sales`, `weighted_tp` |
| 用途 | 价格带市场、20-30 万市场容量、价格结构、价格带 × 能源 × 车身 × 级别 |
| 适合回答 | 各价格带月度销量分布？20-30 万价格带市场容量？价格带 × 燃料类型交叉分析？价格重心在价格带间的差异？ |

### 6. product_segment_monthly

| 属性 | 值 |
|------|----|
| Parquet | `product_segment_monthly.parquet` |
| Grain | `date_month`, `saic_segment`, `body_type`, `vehicle_level`, `vehicle_level_group`, `fuel_type_group`, `drive_type_group` |
| 度量 | `sales`, `weighted_tp`, `weighted_length_mm`, `weighted_width_mm`, `weighted_height_mm`, `weighted_wheelbase_mm` |
| 用途 | 细分市场、车身结构、级别结构、驱动结构、大车化趋势、产品尺寸重心 |
| 适合回答 | 上汽细分市场销量结构？SUV/轿车/MPV 车身结构趋势？各级别车型平均尺寸变化？驱动形式（两驱/四驱）销量占比？ |

---

## Workspace 如何读取

读取示例、字段速查和分析场景见 [Workspace 使用指南](../业务能力/市场与竞争/tp_and_mix_ways_usage.md)。

---

## Hub / 其他上层如何读取

与 workspace 导入方式一致：

```python
from shared.loaders.tp_and_mix_ways_loader import (
    load_tp_and_mix_ways_table,
    load_tp_and_mix_ways_table_duckdb,
)

# 按需加载对应 Parquet 表
df = load_tp_and_mix_ways_table("geo_monthly")
```

上层 **不应直接引用** `dataset/TP&MIX-ways/raw_csv/` 下的原始 CSV，也不应自行维护另一份副本。

---

## 为什么不合并成一张宽表

1. **Grain 不一致**：6 张表的分组维度不同（品牌/车型/城市/价格带/产品细分），合并后大量 cell 为 NaN，降低查询效率。
2. **语义清晰**：每张表对应一类分析视角，表名即说明分析场景，用户按需选择。
3. **性能**：窄表按 grain 分区存储，查询时只加载需要的表，无需扫描无关列。
4. **维护性**：Tableau 导出结构调整时，只需更新对应单表的 column mapping，不影响其他表。

---

## 增量更新与跨层发布契约

正式 `raw_csv` 是历史真源，**任何 Tableau 导出不得直接覆盖它**。视图只返回一个日期
窗口且列顺序不固定，2026-11-03 的 2 个月导出覆盖 79 个月历史即由此触发。现在统一由
`dataset/updater/tp_and_mix_ways_raw_guard.py` 执行，顺序是“staging 全部完成并校验
后再一次性发布”：

1. 导出写入 `staging/runs/<run_id>/increment/raw_csv/`。
2. 与正式 raw 在 staging 合并：增量中包含的月份整月替换（消失的键计入
   `removed_rows`），未出现在增量中的历史月份原样保留；重叠键值变化计为
   restatement。每表每月记录旧行数、新行数、删除行数与删除比例；超过阈值默认
   阻断（`--max-month-deletion-ratio`，默认 0.50）。
3. 校验 6 张表齐全、列集合与契约一致、主键无重复、月份可解析、销量非负，且合并后
   月份覆盖当前 parquet 基线。正式数据集已有派生层时，parquet 6 文件 + registry +
   quality 任一缺失都直接报错，不再静默跳过。
4. 从 staging merged raw 全量构建 parquet / registry / quality 到 staging，并校验
   raw 与 parquet 的月份集合一致；任何构建/校验失败都不会触碰正式文件。
5. 全部层通过后才进入跨层事务发布：先把本次要替换的 raw + derived 文件快照到
   `staging/backups/<run_id>/`，写 `transaction_manifest.json`，再逐文件
   `os.replace`；任一文件失败按 manifest 恢复本次事务已修改的全部文件。
6. `os.replace` 只提供**文件级**原子性，不保证整个数据集的一致可见性；事务
   manifest 是恢复依据。更新入口持有 `staging/.update.lock` 运行锁，启动时会自动
   回滚上次中断留下的 `publishing` manifest；回滚失败会标记 `recovery_failed` 并
   阻断新的更新。

`--dry-run` 只做导出/合并/全链路构建与校验，不发布；`--skip-export` 仅从正式 raw
重建派生层。备份与 manifest 不自动删除。

## 重新构建与增量更新

```bash
# 从正式 raw 全量重建 parquet / registry / quality
make build-tp-and-mix-ways-dataset

# 等价入口：updater --skip-export（staging 构建后跨层事务发布）
make rebuild-tp-and-mix-ways-dataset

# Tableau → staging → 合并/校验/派生层构建 → 跨层事务发布
make update-tp-and-mix-ways-dataset
```

等价命令：

```bash
.venv/bin/python scripts/build_tp_and_mix_ways_dataset.py
.venv/bin/python dataset/updater/update_tp_and_mix_ways_tableau.py --skip-export
.venv/bin/python dataset/updater/update_tp_and_mix_ways_tableau.py
```

构建流程（`build` 脚本，供全量重建与 updater 派生层共用）：
1. 从 raw 目录读取 6 张 CSV（自动识别 UTF-8 逗号 / UTF-16 Tab）
2. pivot widen（度量名称 → 独立列），按 `COLUMN_ALIASES` 归一化表头
3. 字段清洗、类型转换；按 natural-key grain 统计重复
4. 输出 Parquet → `parquet/`（临时文件 + `os.replace` 原子写）
5. 输出 Registry → `registry/tp_and_mix_ways_tables.json`
6. 输出质量报告 → `quality/`

---

## 测试

```bash
pytest tests/test_tp_and_mix_ways_dataset_build.py -q
pytest tests/test_tp_and_mix_ways_raw_guard.py -q
```

`test_tp_and_mix_ways_raw_guard.py` 不依赖本地数据资产，使用临时 fixture 覆盖：
- 增量导出不能覆盖历史月份
- 列顺序变化 / 表头别名 / UTF-16 Tab 输入
- 主键冲突与列集合变化被拒绝
- 历史月份缺失时拒绝发布
- 跨层事务失败时 raw + parquet/registry/quality 全部回滚
- 跨层月份不一致、基线文件缺失时拒绝发布
- 运行锁阻止并发、陈旧锁可恢复、重复运行可继续
- 未完成 publishing manifest 的自动回滚与回滚失败告警
- 整月大规模删除审计与可配置阈值
- 合并后重建的一致性 / 确定性，以及 grain 修复前后的重复率

`test_tp_and_mix_ways_dataset_build.py` 中依赖 `dataset/TP&MIX-ways/` 的用例在没有
本地数据时跳过（数据目录被 `.gitignore` 排除），其余 schema/构建契约用例照常运行。

---

## 相关文档

- **workspace 使用指南**: `docs/业务能力/市场与竞争/tp_and_mix_ways_usage.md` — 6 张表的适用场景、字段速查、workspace 消费规范
- **数据集构建**: `scripts/build_tp_and_mix_ways_dataset.py` — service 级构建脚本
- **schema 定义**: `shared/schema/tp_and_mix_ways_schema.py` — grain / dimensions / metrics
- **loader**: `shared/loaders/tp_and_mix_ways_loader.py` — pandas / DuckDB 读取入口
