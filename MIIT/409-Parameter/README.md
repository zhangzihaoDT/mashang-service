# Parameter 宽表工作流

从 MIIT 公告批次中提取动力系统参数（电池/电机/电控/续航/质量等）并生成宽表。

## 文件说明

| 文件 | 说明 |
|------|------|
| `wide_table.py` | 生成脚本：解析 scan 数据 + 品牌归档 .md + 车船税 JSON → 宽表 |
| `wide_table.csv` | 结构化宽表（本批次产物） |
| `wide_table.md` | Markdown 可读宽表 + 衍生指标汇总（本批次产物） |

## 数据源依赖

| 数据源 | 路径 | 说明 |
|--------|------|------|
| 主公告扫描 | `MIIT/scan_batch_NNN.md` | 品牌+车型清单（含 `cpxh` 产品型号） |
| 品牌归档详情页 | `MIIT/NNN-品牌名/车型型号-产品名.md` | 附件1 企业申报详情页数据 |
| 车船税目录 | `MIIT/车型清单_第XX批车船税.json` | 附件2 车船税减免目录结构化数据 |

## 输出字段

### 核心字段

品牌 / 产品型号 / 产品名称 / 动力形式 / 电机功率(kW) / 电池类型 / 电池容量(kWh) / 电池质量(kg) / 纯电续航(km) / 整备质量(kg) / 增程器 / 长/宽/高(mm)

### 标准化字段

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

### 衍生指标

- **总电量口径近似电耗(kWh/100km)**: 电池总能量 / 纯电续航 × 100。使用总电量而非可用电量，续航工况未统一，适用于**异常值筛查、同平台对比、粗略排序**，不代表官方能耗。
- **电池包能量密度(Wh/kg)**: 电池能量(kWh) / 电池质量(kg) × 1000。含±公差字段输出区间值。
- **单位电量续航(km/kWh)**: 纯电续航 / 电池容量
- **电池质量占整备质量比(%)**: 电池质量 / 整备质量 × 100。含±公差字段输出区间值。

### 数据质量字段

| 字段 | 说明 |
|------|------|
| `tax_catalog_match_flag` | 是否在附件2车船税中匹配到该车型 |
| `metric_scope` | 统计覆盖范围说明 |
| `missing_reason` | 数据缺失原因 |

## 复用方法

```bash
python wide_table.py
```

脚本自动从同级父目录读取 `scan_batch_NNN.md` 和 `NNN-品牌/`。若用于新批次，需：

1. 复制 `wide_table.py` 到新批次目录（如 `410-Parameter/`）
2. 在 `wide_table.py` 中修改 `SCAN_PATH` 和 `TAX_PATH` 路径指向新批次文件
3. 运行 `python wide_table.py`
