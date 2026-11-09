# 数据集获取与更新操作手册

从仓库根目录运行命令。更新与校验使用 [数据集注册表](../../dataset/updater/dataset_registry.py) 中登记的八项数据集。主理、上险及外部市场数据使用各自的入口。字段和指标定义见 [共享规范](../共享规范/README.md)。

| 操作 | 入口 | 范围与影响 |
|---|---|---|
| 查看当前数据 | `.venv/bin/python dataset/updater/update_all_datasets.py --status-only` | 只读，查看文件、行数和可用的数据时点 |
| 每日刷新 | `make data-refresh-daily` | 写入订单和全局下发线索 |
| 全量更新并校验 | `make allupdate` | 执行注册表对应的全量更新流程并校验 |
| 校验本地数据 | `make data-validate` | 只读，检查数据集完整性 |
| 每日观察同步 | `make data-pipeline` | 刷新后写入飞书，先按每日管道手册预检 |

## 按业务数据更新

表中脚本从仓库根目录通过 `.venv/bin/python dataset/updater/<脚本>` 调用。执行单项前先核对该脚本的 `--help`，确认网络环境、输入路径与写入范围。

| 数据域 | 脚本 | 产物与处理方式 |
|---|---|---|
| 订单 | `order_data_to_parquet.py` | 导出近 60 日订单至 `order_data_2026.csv`，以已有 `order_data.parquet` 为底表合并 |
| 选配 | `order_config_to_parquet.py` | 读取年度配置快照与滚动导出，更新 `config_attribute.parquet` |
| 全局下发线索 | `assign_data_to_csv.py` | Tableau 渠道汇总导出至 `assign_data.csv` |
| 试驾 | `test_drive_data_to_csv.py` | Tableau 试驾汇总导出至 `test_drive_data.csv` |
| 锁单归因 | `lock_attribution_data_to_parquet.py` | 导出当年 CSV，按年度整理后发布 `lock_attribution_data.parquet`。已有原始文件时可用 `--no-export` 整理 |
| 交付与库存 | `delivery_inventory_to_parquet.py` | Tableau 导出后更新 `delivery_inventory.parquet`。`--skip-export` 使用已有 CSV，`--full-refresh` 全量刷新 |
| 门店主数据 | `store_info_to_csv.py` | 写入 `STORE_INFO_CSV` 指定位置，默认位于仓库外 |
| 门店下发线索 | `store_daily_leads_to_csv.py` | 滚动窗口合并至 `store_daily_leads.csv` |
| 主理与名册 | `store_daily_zhuli_to_csv.py` | 更新 `门店日报_主理_当月.csv`，用 `--with-roster` 同时更新 `主理信息表.csv` |
| 上险 | `update_tp_and_mix_ways_tableau.py` | 按独立数据包的增量发布契约运行，见 [上险数据集手册](tp_and_mix_ways_dataset.md) |

更新后运行 `make data-validate`，结合汇总核对该项退出状态、关键字段和数据最新时点。文件修改时间只能确认写入。全量编排默认继续处理后续步骤，出现失败时整体退出码非零。先确认失败步骤及已经写入的产物，再重试对应单项。

## 历史重建与内部组件

- `rebuild_config_parquet.py` 依赖四份年度配置快照，直接替换配置 Parquet。使用前核对快照完整性并备份现有产物。
- `rebuild_order_data_parquet.py` 依赖指定年度文件，包括当前目录未见的 `order_data_2026_0428.csv`。先确认来源及完整性，再制定恢复步骤。
- `tableau_export.py` 和 `tableau_views.json` 提供导出与视图配置。 `dataset_registry.py` 提供更新和校验清单，`tp_and_mix_ways_raw_guard.py` 支持上险原始层发布。

## 资产分类与现有位置

| 类别 | 现有位置 | 使用方式 |
|---|---|---|
| 正式业务表 | `dataset/` 根目录的订单、选配、线索、试驾、归因、库存及门店运营产物 | 业务分析按已登记路径读取 |
| 原始与增量输入 | `tableau/orders/`、`tableau/configuration/`、`tableau/attribution/`、`tableau/delivery/` | 更新与重建使用，先区分历史快照和滚动覆盖文件 |
| 市场数据 | `market/gasgoo/`、`market/cpca/`、`market/cpca_weekly/`、`TP&MIX-ways/` | 按来源与频率选用，乘联会周度和上险各有独立契约 |
| 专题样本 | `research/a3_flow/`、`research/audience/`、`research/nev_apeal/` | 追溯原研究范围和截点，专题同名订单及线索文件按样本处理 |
| 接收区 | `incoming/` | 接收 Tableau、飞书和官网配置下载或解析产物 |
| 群聊数据 | `wechat/` | 群聊历史数据与专用同步脚本 |

订单历史重建脚本从仓库外的 original 目录取源文件。交付库存更新脚本也使用仓库外的 Tableau 导出路径，`tableau/delivery/` 内的 CSV 为本地留存。
