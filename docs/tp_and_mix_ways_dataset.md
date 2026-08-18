# TP&MIX-ways Dataset — 乘用车上险数据

## 数据集定位

**Service 级共享数据资产。**

本数据集由 6 张 Tableau 导出的窄视图 CSV 构建而成，面向 mashang_workspace 和 mashang_runtime_v2 提供标准化的乘用车上险数据（TP&MIX-ways Registration Data）查询能力。

### 分层

| 层 | 路径 | 说明 |
|----|------|------|
| Raw Input | `dataset/TP&MIX-ways/raw_csv/` | Tableau 导出的 6 张 CSV（UTF-16 LE, tab-delimited, pivot 格式） |
| Parquet | `dataset/TP&MIX-ways/parquet/` | 6 张独立 grain 的 Parquet，由构建脚本生成 |
| Registry | `dataset/TP&MIX-ways/registry/tp_and_mix_ways_tables.json` | 表清单、grain、行数、日期范围 |
| Quality | `dataset/TP&MIX-ways/quality/` | 质量报告（Markdown + JSON） |
| Schema | `shared/schema/tp_and_mix_ways_schema.py` | 表定义（grain / dimensions / metrics / purpose） |
| Loader | `shared/loaders/tp_and_mix_ways_loader.py` | pandas / DuckDB 数据加载器 |

### 设计原则

- **不合并成一张宽表**：6 张表各有独立 grain，保持 Tableau 导出时的逻辑拆分，避免宽表冗余和歧义。
- **workspace 和 runtimeV2 只消费 Parquet/Registry**，不直接读 raw_csv。
- **loader 不硬编码本机绝对路径**，基于 `__file__` 向上推导 service root。

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

所有 CSV 均为 **UTF-16 LE、Tab 分隔、Pivot 格式**（度量名称 + 度量值两列）。

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
| Grain | `date_month`, `brand` |
| 维度 | `brand_group`, `brand_luxury_group`, `oem_group`, `oem`, `brand_country`, `ownership_type`, `domestic_import` |
| 度量 | `sales`, `weighted_tp` |
| 用途 | 品牌排名、品牌份额、品牌价格重心、品牌分组竞争 |
| 适合回答 | 月度品牌销量排名 Top20？豪华品牌市场份额变化？新势力品牌价格重心？自主/合资/豪华品牌分组对比？ |

### 3. model_monthly

| 属性 | 值 |
|------|----|
| Parquet | `model_monthly.parquet` |
| Grain | `date_month`, `brand`, `model`, `sub_model`, `sub_model_id` |
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

## workspace 如何读取

```python
from shared.loaders.tp_and_mix_ways_loader import (
    load_tp_and_mix_ways_registry,
    list_tp_and_mix_ways_tables,
    load_tp_and_mix_ways_table,
    load_tp_and_mix_ways_table_duckdb,
)

# 查看注册表
registry = load_tp_and_mix_ways_registry()

# 列出可用表
tables = list_tp_and_mix_ways_tables()

# 加载为 pandas DataFrame
df = load_tp_and_mix_ways_table("market_energy_monthly")

# 加载为 DuckDB DataFrame
df = load_tp_and_mix_ways_table_duckdb("brand_monthly")
```

无需 `sys.path.insert`，`pyproject.toml` 已配置 `pythonpath = ["."]`，`shared/__init__.py` 确保包可正常导入。

---

## runtimeV2 如何读取

与 workspace 导入方式一致：

```python
from shared.loaders.tp_and_mix_ways_loader import (
    load_tp_and_mix_ways_table,
    load_tp_and_mix_ways_table_duckdb,
)

# 按需加载对应 Parquet 表
df = load_tp_and_mix_ways_table("geo_monthly")
```

runtimeV2 **不应直接引用** `dataset/TP&MIX-ways/raw_csv/` 下的原始 CSV，也不应自行维护另一份副本。

---

## 为什么不合并成一张宽表

1. **Grain 不一致**：6 张表的分组维度不同（品牌/车型/城市/价格带/产品细分），合并后大量 cell 为 NaN，降低查询效率。
2. **语义清晰**：每张表对应一类分析视角，表名即说明分析场景，用户按需选择。
3. **性能**：窄表按 grain 分区存储，查询时只加载需要的表，无需扫描无关列。
4. **维护性**：Tableau 导出结构调整时，只需更新对应单表的 column mapping，不影响其他表。

---

## 重新构建

```bash
make build-tp-and-mix-ways-dataset
```

等价于：

```bash
.venv/bin/python scripts/build_tp_and_mix_ways_dataset.py
```

构建流程：
1. 从 `dataset/TP&MIX-ways/raw_csv/` 读取 6 张 CSV
2. pivot widen（度量名称 → 独立列）
3. 字段清洗、类型转换
4. 输出 Parquet → `dataset/TP&MIX-ways/parquet/`
5. 输出 Registry → `dataset/TP&MIX-ways/registry/tp_and_mix_ways_tables.json`
6. 输出质量报告 → `dataset/TP&MIX-ways/quality/`

---

## 测试

```bash
pytest tests/test_tp_and_mix_ways_dataset_build.py -q
```

测试覆盖：
- Schema 定义完整性（6 张表、grain、dimensions、metrics、purpose）
- Loader 路径推导
- Registry 读取
- 构建脚本字段映射
- 不存在宽表合并逻辑
- Parquet 文件存在性及可读性
- Raw CSV 缺失时的错误处理

---

## 相关文档

- **workspace 使用指南**: `mashang_workspace/docs/tp_and_mix_ways_usage.md` — 6 张表的适用场景、字段速查、workspace 消费规范
- **数据集构建**: `scripts/build_tp_and_mix_ways_dataset.py` — service 级构建脚本
- **schema 定义**: `shared/schema/tp_and_mix_ways_schema.py` — grain / dimensions / metrics
- **loader**: `shared/loaders/tp_and_mix_ways_loader.py` — pandas / DuckDB 读取入口
