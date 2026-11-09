# 数据更新程序

| 类别 | 入口 |
|---|---|
| 统一编排 | `update_all_datasets.py` |
| 单项更新 | 订单、选配、线索、试驾、归因、库存、门店、主理与上险 |
| 历史重建 | `rebuild_order_data_parquet.py`、`rebuild_config_parquet.py` |
| 公共组件 | `dataset_registry.py`、`tableau_export.py`、`tableau_views.json`、`tp_and_mix_ways_raw_guard.py` |

各脚本的输入、产物、适用范围和校验见 [数据集获取与更新操作手册](../../docs/数据获取/dataset_operations.md)。
