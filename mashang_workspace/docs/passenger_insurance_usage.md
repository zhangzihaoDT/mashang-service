# Passenger Insurance — workspace 使用指南

## 数据资产定位

`passenger_insurance` 是 **service 级共享数据资产**，不属于 workspace 私有数据。

- 数据资产本体：`../dataset/passenger_insurance/`（项目根目录）
- 资产构建：`make build-passenger-insurance-dataset`
- 所有 raw CSV 位于 `dataset/passenger_insurance/raw_csv/`
- workspace 只消费 Parquet / registry，不直接接触 raw CSV

## workspace 如何读取

通过 shared loader 统一读取，无需关心底层存储路径：

```python
from shared.loaders.passenger_insurance_loader import (
    list_passenger_insurance_tables,
    load_passenger_insurance_registry,
    load_passenger_insurance_table,
    load_passenger_insurance_table_duckdb,
)

# 列出可用表
tables = list_passenger_insurance_tables()

# 读取 registry
registry = load_passenger_insurance_registry()

# 加载为 pandas DataFrame
df = load_passenger_insurance_table("brand_monthly")

# 加载为 DuckDB DataFrame
df = load_passenger_insurance_table_duckdb("market_energy_monthly")
```

无需 `sys.path.insert`，`pyproject.toml` 已配置 `pythonpath = ["."]`，`shared/__init__.py` 确保包可正常导入。

## 6 张表及适用场景

| 表 | 数据汇总层次 | 适合回答的问题 |
|----|-------------|---------------|
| `market_energy_monthly` | 市场总量 × 能源类型 | "5 月新能源渗透率是多少？"、"纯电/插混/增程走势？"、"市场总量趋势？"、"各燃料类型价格重心？" |
| `brand_monthly` | 品牌 × 厂商 × 分组 | "5 月品牌销量排名 Top20？"、"豪华品牌份额变化？"、"新势力 vs 传统品牌价格重心？"、"自主/合资/豪华分组对比？" |
| `model_monthly` | 车型 × 子车型 × 级别 × 燃料 | "LS6 和 Model Y 月度销量趋势？"、"品牌内部车型销量结构？"、"各车型价格重心？"、"级别 × 燃料类型分布？" |
| `geo_monthly` | 省份 × 城市 × 线级 × 区域 | "5 月省份销量排名？"、"新能源在哪些城市线级更强？"、"华东/华南区域新能源渗透率？" |
| `price_segment_monthly` | 价格段 × 能源 × 车身 × 级别 | "20-30 万新能源 SUV 市场多大？"、"各价格带月度销量分布？"、"价格带 × 燃料类型交叉分析？" |
| `product_segment_monthly` | 上汽细分市场 × 车身 × 级别 × 驱动 × 尺寸 | "中大型 SUV 市场结构？"、"SUV/轿车/MPV 趋势？"、"各级别车型平均尺寸变化？"、"两驱 vs 四驱销量占比？" |

## 字段速查

### market_energy_monthly

| 字段 | 类型 | 说明 |
|------|------|------|
| `date_month` | date | 月份（统一为当月 1 日） |
| `fuel_type_group` | string | 燃料类型组（如 新能源、燃油） |
| `fuel_type` | string | 燃料类型（纯电动、插电式混合动力、汽油等） |
| `sales` | float | 销量 |
| `weighted_tp` | float | TP 价格重心（加权平均开票价格） |

### brand_monthly

| 字段 | 类型 | 说明 |
|------|------|------|
| `date_month` | date | 月份 |
| `brand` | string | 品牌 |
| `brand_group` | string | 品牌组 |
| `brand_luxury_group` | string | 品牌新豪华分组 |
| `oem_group` | string | 厂商集团 |
| `oem` | string | 厂商 |
| `brand_country` | string | 品牌国别 |
| `ownership_type` | string | 所有权类型 |
| `domestic_import` | string | 国产/进口 |
| `sales` | float | 销量 |
| `weighted_tp` | float | TP 价格重心 |

### model_monthly

| 字段 | 类型 | 说明 |
|------|------|------|
| `date_month` | date | 月份 |
| `brand` | string | 品牌 |
| `brand_series` | string | 品牌系列 |
| `sub_model_id` | int | SUB_MODEL_ID |
| `model` | string | 车型 |
| `sub_model` | string | 子车型 |
| `fuel_type` | string | 燃料类型 |
| `fuel_type_group` | string | 燃料类型组 |
| `body_type` | string | 车身形式 |
| `vehicle_level` | string | 车型级别 |
| `vehicle_level_group` | string | 车型级别组 |
| `saic_segment` | string | 上汽细分市场 |
| `drive_type` | string | 驱动形式 |
| `drive_type_group` | string | 驱动形式组 |
| `sales` | float | 销量 |
| `weighted_tp` | float | TP 价格重心 |

### geo_monthly

| 字段 | 类型 | 说明 |
|------|------|------|
| `date_month` | date | 月份 |
| `province` | string | 省 |
| `city` | string | 市 |
| `region_group` | string | 区域划分 |
| `fuel_type_group` | string | 燃料类型组 |
| `city_tier_2025` | string | 2025 年城市级别 |
| `city_tier_group` | string | 城市级别组 |
| `sales` | float | 销量 |
| `weighted_tp` | float | TP 价格重心 |

### price_segment_monthly

| 字段 | 类型 | 说明 |
|------|------|------|
| `date_month` | date | 月份 |
| `tp_bucket_5w` | string | TP 5 万 1 档 |
| `tp_bucket_10w` | string | TP 10 万 1 档 |
| `fuel_type_group` | string | 燃料类型组 |
| `body_type` | string | 车身形式 |
| `vehicle_level_group` | string | 车型级别组 |
| `sales` | float | 销量 |
| `weighted_tp` | float | TP 价格重心 |

### product_segment_monthly

| 字段 | 类型 | 说明 |
|------|------|------|
| `date_month` | date | 月份 |
| `saic_segment` | string | 上汽细分市场 |
| `body_type` | string | 车身形式 |
| `vehicle_level` | string | 车型级别 |
| `vehicle_level_group` | string | 车型级别组 |
| `fuel_type_group` | string | 燃料类型组 |
| `drive_type_group` | string | 驱动形式组 |
| `sales` | float | 销量 |
| `weighted_tp` | float | TP 价格重心 |
| `weighted_length_mm` | float | 加权长(mm) |
| `weighted_width_mm` | float | 加权宽(mm) |
| `weighted_height_mm` | float | 加权高(mm) |
| `weighted_wheelbase_mm` | float | 加权轴距(mm) |

## workspace 职责边界

### workspace 做消费，不做构建

| 允许 | 不允许 |
|------|--------|
| 通过 shared loader 读取 Parquet | 直接读取 raw_csv |
| 基于 Parquet 做分析/图表/报告 | 复制 parquet 到 workspace |
| 探索新分析路径 | 维护字段映射 |
| 验证后沉淀到 runtime_scripts/ | 构建 Parquet |
| 为 runtimeV2 提供查询原型 | 修改 registry |
|  | 生成一张大宽表 |

### 成熟分析逻辑迁移路径

1. workspace 中探索 → `research_scripts/`
2. 验证稳定、口径明确 → `runtime_scripts/`
3. runtimeV2 消费 → 注册为 tool / operator
4. passenger_insurance 的数据构建始终在 service 级（`scripts/build_passenger_insurance_dataset.py`）

## 构建与测试

```bash
# 由 service 级 Makefile target 构建
make build-passenger-insurance-dataset

# service 级测试
pytest tests/test_passenger_insurance_dataset_build.py -q

# workspace 侧 smoke test
python mashang_workspace/research_scripts/passenger_insurance/check_passenger_insurance_asset.py
```

---

## 相关文档

- **service 数据集说明**: `docs/passenger_insurance_dataset.md` — 数据构建流程、6 张 Parquet 的 grain/metrics 定义
- **shared schema**: `shared/schema/passenger_insurance_schema.py` — grain / dimensions / metrics 的 Python 定义
- **shared loader**: `shared/loaders/passenger_insurance_loader.py` — pandas / DuckDB 统一读取入口
- **project cleanup audit**: `docs/project_cleanup_audit.md` — 项目结构边界与清理计划
