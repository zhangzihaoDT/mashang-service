# Daily Data Pipeline

## 完整链路

> canonical 入口为 `data-*` / `observe-*`；下表括号内为兼容旧名。

```
make data-pipeline（旧名 daily-data-pipeline）
  │
  ├── 1. make data-refresh-daily
  │     dataset/updater/update_all_datasets.py --scope daily
  │     仅从 Tableau 刷新 Daily pipeline 必需的两份数据：
  │       - dataset/order_data.parquet（订单数据）
  │       - dataset/assign_data.csv（下发线索）
  │     数据集清单唯一来源于 dataset/updater/dataset_registry.py
  │     结束（无论成败）打印逐数据集结论：本次是否更新 / 状态 / 行数 / 文件更新时间 / 数据最新时点
  │     → 写操作（continue-on-error：单个 step 失败不中断，整体返回非 0）
  │
  │     > 边界：Daily pipeline 只负责订单 + 下发线索。试驾数据 / 锁单归因等其余数据集
  │     > 只在 `make allupdate`（全量更新 + 校验）或各自独立更新入口维护（走“更新 + 整理”路径）。
  │
  ├── 2. make data-validate（旧名 dataset-validate）
  │     mashang_workspace/utility_scripts/dataset_validate.py
  │     检查 dataset 文件是否存在、行数、关键字段
  │     → 只读
  │
  ├── 3. make observe-dry-run（旧名 daily-observation-dry-run）
  │     mashang_workspace/utility_scripts/skills_order_observation_daily.py --dry-run
  │     基于本地 dataset 计算每日观察结果，不写外部系统
  │     → 安全预检
  │
  ├── 4. make observe-sync（旧名 daily-observation-sync）
  │     mashang_workspace/utility_scripts/skills_order_observation_daily.py
  │     计算观察结果并同步到飞书多维表格/飞书机器人
  │     → 写操作（外部系统）
  │
  └── 5. downstream-analysis
       mashang_workspace/business_scripts/
       消费已更新的 dataset 进行问数分析（上层经 jobs/ 由 Hub/Worker 调用）
```

> 注意：`data-pipeline` **不含销售监控**。如需「数据更新 + 监控推送」一体执行，用 `make daily-ops`（= data-pipeline + sales-monitor）。

## 各层职责

| 层级 | 目录 | 职责 | 写操作 |
|------|------|------|--------|
| 数据供给 | `dataset/updater/` | 从数据源拉取最新数据，刷新 dataset | ✅ 刷新本地文件 |
| 数据校验 | `utility_scripts/dataset_validate.py` | 轻量检查 dataset 状态 | ❌ |
| 观察计算 | `utility_scripts/skills_order_observation_daily.py` | 每日锁单/开票/预测/达成率 | ❌ (dry-run) / ✅ (sync) |
| 分析消费 | `business_scripts/` | 稳定分析能力 | ❌ |
| 确定性执行契约 | `jobs/` | Research Application job（Hub/Worker 调用） | ❌ |

> **锁单口径对齐**：`skills_order_observation_daily.py` 的锁单统计与上市/预售监控（`utils/monitors/`）同源——按 `order_number` 去重、剔除测试单（总部主理店 + 假身份号）、LS6 代际分类复用 `utils.monitors.series_group.apply_series_group_logic`。唯一差异是时间窗口：观察为**单日**（自然日）；上市监控卡片「上市至今累计锁单」自上市开放时刻起累计，并另有「当日锁单」行。开票口径不属于本次对齐范围（仍为全量开票，不剔测试单）。

## 层级关系

```
dataset/updater/           ← 数据供给层（infrastructure）
    ↓ 产出
dataset/*.parquet/.csv     ← 数据存储层
    ↓ 消费
utility_scripts/           ← 工具层（校验、观察、DataOps）
    ↓ 消费
business_scripts/           ← 分析能力层
    ↓ 契约
jobs/                      ← 确定性执行契约层（Hub/Worker 调用）
```

## Makefile 命令

> canonical 名优先；括号内为兼容旧名。

### 安全检查流程（推荐每日先用）

```bash
make data-status                # 数据集现状：逐数据集 行数 / 文件更新时间 / 数据最新时点（只读）
make data-validate              # 检查 dataset 完整性（旧名 dataset-validate）
make observe-dry-run            # 预检观察结果（旧名 daily-observation-dry-run）
```

或合并：

```bash
make data-pipeline-dry-run      # data-validate + observe-dry-run（旧名 daily-data-pipeline-dry-run）
```

> `make data-status` 只读，不触发数据源；等价于 `python dataset/updater/update_all_datasets.py --status-only`。
> `data-refresh` 结束也会打印同一张逐数据集结论表（含「本次已更新 N/8」）。

### 完整执行流程（写操作）

```bash
make data-refresh-daily         # 仅刷新订单数据 + 下发线索（Daily pipeline 最小范围）
make data-refresh               # 全量刷新 dataset（含试驾 / 锁单归因；旧名 dataset-update）
make allupdate                  # 全量更新 + 校验 = data-refresh + data-validate（别名 make updateall，供 hub 调度）
make data-validate              # 校验（旧名 dataset-validate）
make observe-dry-run            # 预检（旧名 daily-observation-dry-run）
make observe-sync               # 同步到飞书（旧名 daily-observation-sync）
```

或合并：

```bash
make data-pipeline              # data-refresh-daily + data-validate + observe-sync（旧名 daily-data-pipeline）
make daily-ops                  # data-pipeline + sales-monitor（数据更新 + 监控推送）
```

> **Daily pipeline 的更新范围**：`data-pipeline` / `daily-ops` 只刷新 `order_data.parquet` 与 `assign_data.csv`；
> 其余数据集（选配、试驾、锁单归因、交付-库存、门店主数据、门店下发线索）不在每日链路内，
> 需要时用 `make allupdate` 全量刷新，或走各自的独立更新入口。

**注意**：
- `data-refresh` 和 `observe-sync` 是写操作
- `observe-sync` 会写入飞书多维表格和发送飞书机器人通知
- 不要在 CI 中自动执行写操作

### 数据集清单（update-all 覆盖范围）

清单在 `dataset/updater/dataset_registry.py` 维护，`update_all_datasets.py`（刷新/汇总）与 `dataset_validate.py`（校验）同源消费，共 8 个。

`update_all_datasets.py --scope` 控制实际刷新范围：

- `--scope full`（默认，`make data-refresh` / `make allupdate`）：按 step 1–6 刷新全部 8 个数据集。
- `--scope daily`（`make data-refresh-daily`，供 Daily pipeline）：只刷新 step 1（订单数据）与 step 3 的 `assign_data`（下发线索）。

| step | 数据集 | 文件 | 必需 | 数据最新时点口径 | daily 是否刷新 |
|------|--------|------|------|------------------|----------------|
| 1 | 订单数据 | `dataset/order_data.parquet` | ✅ | `lock_time` 等业务时间列 | ✅ |
| 2 | 选配信息 | `dataset/config_attribute.parquet` | ✅ | 无日期列（看文件更新时间） | ❌ |
| 3 | 下发线索 | `dataset/assign_data.csv` | ✅ | `Assign Time 年/月/日` | ✅ |
| 3 | 试驾数据 | `dataset/test_drive_data.csv` | | `create_date 年/月/日` | ❌ |
| 3 | 锁单归因 | `dataset/lock_attribution_data.parquet` | | `lc_order_lock_time_min` | ❌ |
| 4 | 交付-库存 | `dataset/delivery_inventory.parquet` | | `attribute_dealer_date` | ❌ |
| 5 | 门店主数据 | `<original>/store_info.csv`（可用 `STORE_INFO_CSV` 覆盖） | | 无日期列 | ❌ |
| 6 | 每日下发线索（by门店） | `dataset/store_daily_leads.csv` | | `日期` | ❌ |

各数据集的更新脚本（按职责独立）：

| 数据集 | 更新脚本 |
|--------|----------|
| 订单数据 | `dataset/updater/order_data_to_parquet.py` |
| 选配信息 | `dataset/updater/order_config_to_parquet.py` |
| 下发线索 | `dataset/updater/assign_data_to_csv.py` |
| 试驾数据 | `dataset/updater/test_drive_data_to_csv.py` |
| 锁单归因 | `dataset/updater/lock_attribution_data_to_parquet.py` |
| 交付-库存 | `dataset/updater/delivery_inventory_to_parquet.py` |
| 门店主数据 | `dataset/updater/store_info_to_csv.py` |
| 每日下发线索（by门店） | `dataset/updater/store_daily_leads_to_csv.py` |

> Tableau REST 导出能力统一抽到 `dataset/updater/tableau_export.py`，各 updater 复用，不再彼此反向依赖。

### 网络回退（办公网 / 移动链路）

Tableau 在办公网与移动网络使用不同入口。`update_all_datasets.py` 启动时会探测办公网 Tableau 是否可达：

- 可达 → 走默认办公网链路
- 不可达（DNS/连接失败）→ 自动对全部步骤回退移动链路（`--mobile`），无需手动干预

也可显式强制移动链路（例如已知当前不在办公网）：

```bash
make data-refresh MOBILE=1
# 或
python dataset/updater/update_all_datasets.py --mobile
```

> 历史问题：`order_config_to_parquet.py` 等子步骤没有单体自动回退，只在办公网探测失败时才由编排层统一传 `--mobile`；因此请通过 `update_all_datasets.py` / `make data-refresh` 编排执行，不要单独调用子脚本。

## 自然语言入口

中文自然语言入口：**数据更新并同步**

- 这是 workspace-level **DataOps 指令**，不是带日期条件的分析问题
- 不应理解为"只更新今天的数据"
- 它表示从数据源拉取最新数据、刷新 dataset、校验、生成观察结果并同步飞书

| 入口 | 对应命令 |
|------|----------|
| "数据更新并同步" | `make data-pipeline`（旧名 `daily-data-pipeline`） |
| "预检数据" | `make data-pipeline-dry-run`（旧名 `daily-data-pipeline-dry-run`） |

## 与 jobs / Hub 的关系

- `jobs/` 是确定性执行契约层（Research Application job），**不负责数据源刷新**（那是 `dataset/updater/` 的职责）
- `jobs/` **不调度 `utility_scripts/`**（包括 dataset_validate 和 skills_order_observation_daily）
- `jobs/` **不响应"数据更新并同步"指令**（由 Hub/Worker 调度触发）
- runtime 已不是 service 内的 Python package：运行时系统 = **Hub + Worker + OpenCode**
- 如果要产品化每日数据同步能力，需在 `jobs/` 定义确定性 job，并带 `dry-run` / `execute` 安全边界

## 废弃说明

`make daily-sync-dry-run` 已废弃。
请使用 `make observe-dry-run`（旧名 `make daily-observation-dry-run`）替代。
