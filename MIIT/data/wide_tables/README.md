# wide_tables/ —— 参数宽表

P4 参数宽表（`04_build_wide_table.py` 产出），从 附件1 详情页 + 附件2 车船税 合并生成。

```
wide_tables/
├── wide_table_409.csv / .md
└── wide_table_410.csv / .md
```

## 核心字段

品牌 / 产品型号 / 产品名称 / 动力形式 / 电机功率(kW) / 电池类型 / 电池容量(kWh) / 电池质量(kg) / 纯电续航(km) / 整备质量(kg) / 增程器 / 长/宽/高(mm)

## 标准化字段

| 字段 | 说明 | 示例值 |
|------|------|--------|
| `battery_chemistry` | 电池化学体系代码 | `LFP` / `NCM` / `OTHER` |
| `battery_chemistry_cn` | 电池化学体系中文 | `磷酸铁锂` / `三元锂` |
| `battery_ncm_explicit_flag` | 是否明确写"镍钴锰" | `1` / `0` |
| `motor_count` | 驱动电机数量 | `1` / `2` / `3` |
| `motor_total_peak_kw` | 合计峰值功率(kW) | `310` / `890` |
| `single_multi_motor` | 单/多电机标识 | `单电机` / `2电机` / `3电机` |
| `cell_supplier` | 电芯企业 | `宁德时代新能源科技股份有限公司` |
| `pack_supplier` | 电池总成企业 | `宜宾三江时代新能源科技有限公司` |
| `cell_supplier_group` | 电芯集团级 | `宁德时代系` / `弗迪系` / `中创新航` |
| `vertical_integration_flag` | 垂直整合模式 | `same_company` / `same_group` / `cross_group` |

## 衍生指标

- **总电量口径近似电耗(kWh/100km)**: 电池总能量 / 纯电续航 × 100。使用总电量而非可用电量，续航工况未统一，适用于**异常值筛查、同平台对比、粗略排序**，不代表官方能耗。
- **电池包能量密度(Wh/kg)**: 电池能量(kWh) / 电池质量(kg) × 1000。含±公差字段输出区间值。
- **单位电量续航(km/kWh)**: 纯电续航 / 电池容量
- **电池质量占整备质量比(%)**: 电池质量 / 整备质量 × 100。含±公差字段输出区间值。

## 数据质量字段

| 字段 | 说明 |
|------|------|
| `tax_catalog_match_flag` | 是否在附件2车船税中匹配到该车型 |
| `metric_scope` | 统计覆盖范围说明 |
| `missing_reason` | 数据缺失原因 |

## 批次覆盖（410）

7 品牌 17 车型（零跑 3、领克 1、魏牌 3、问界 4、智界 3、爱咖 1、猛士 2）。
附件1 缺失 0；附件2 缺失 13（纯电/燃油车型不在车船税目录，`metric_scope=仅增程/插混`）。
完整覆盖电池/续航的为 4 款增程/插混：问界 M8 增程×2 配置、猛士 X700 增程/插混。

## 数据源

| 数据源 | 路径 |
|--------|------|
| 主公告扫描 | `data/search_results/scan_batch_NNN.md` |
| 品牌归档详情页 | `data/vehicle_details/车型型号-产品名.md` |
| 车船税目录 | `data/vehicle_tax/车型清单_第XX批车船税.json` |

## 生成

```bash
python3 MIIT/scripts/04_build_wide_table.py --batch 410
```

新批次只需在 `workflow/batches.yaml` 登记 scan / 车船税文件名即可复用。
