# Data Dictionary — 数据字典

> 生成方式: `python scripts/data_dictionary.py`

## 生成命令

```bash
# 终端输出
python scripts/data_dictionary.py

# CSV 输出 (含全部字段详情)
python scripts/data_dictionary.py --format csv --output outputs/tables/

# JSON 输出
python scripts/data_dictionary.py --format json --output outputs/tables/

# 指定扫描目录
python scripts/data_dictionary.py --input dataset --format csv
```

## 扫描范围

脚本扫描以下目录（默认 `dataset/`），识别 `.parquet`、`.csv`、`.xlsx`、`.json` 文件：

| 目录 | 说明 |
|------|------|
| `dataset/` | 核心数据目录 |
| `data/` | 备用数据目录 |

## 输出字段说明

| 字段 | 说明 |
|------|------|
| `file_path` | 文件绝对路径 |
| `file_name` | 文件名 |
| `file_type` | 文件格式 (parquet/csv/xlsx/json) |
| `row_count` | 行数（大文件可能为采样行数） |
| `column_name` | 字段名 |
| `dtype` | 数据类型 (int64/float64/object/datetime64 等) |
| `non_null_count` | 非空值数量 |
| `null_count` | 空值数量 |
| `sample_values` | 前 5 个样例值（逗号分隔） |

## 使用场景

1. **快速了解数据集结构**：运行 `python scripts/data_dictionary.py` 查看所有数据文件的字段清单
2. **确定查询字段**：在写分析脚本前先看数据字典确认字段名和类型
3. **数据质量检查**：通过 null_count 快速发现空值严重的字段

## 注意事项

- 大文件（>1000 行）只读取 schema 和前 1000 行样例，不加载全量
- CSV 中的日期字段可能被读为字符串，使用 `pd.to_datetime()` 转换
- 建议每次数据集更新后重新运行数据字典
