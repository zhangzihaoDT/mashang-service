# Daily Data Pipeline

## 完整链路

```
daily-data-pipeline
  │
  ├── 1. dataset-update
  │     dataset/updater/update_all_datasets.py
  │     从 Tableau/数据源刷新 dataset/*.parquet / *.csv
  │     → 写操作
  │
  ├── 2. dataset-validate
  │     mashang_workspace/utility_scripts/dataset_validate.py
  │     检查 dataset 文件是否存在、行数、关键字段
  │     → 只读
  │
  ├── 3. daily-observation-dry-run
  │     mashang_workspace/utility_scripts/skills_order_observation_daily.py --dry-run
  │     基于本地 dataset 计算每日观察结果，不写外部系统
  │     → 安全预检
  │
  ├── 4. daily-observation-sync
  │     mashang_workspace/utility_scripts/skills_order_observation_daily.py
  │     计算观察结果并同步到飞书多维表格/飞书机器人
  │     → 写操作（外部系统）
  │
  └── 5. downstream-analysis
       mashang_workspace/runtime_scripts/ 和 mashang_runtime_v2/
       消费已更新的 dataset 进行问数分析
```

## 各层职责

| 层级 | 目录 | 职责 | 写操作 |
|------|------|------|--------|
| 数据供给 | `dataset/updater/` | 从数据源拉取最新数据，刷新 dataset | ✅ 刷新本地文件 |
| 数据校验 | `utility_scripts/dataset_validate.py` | 轻量检查 dataset 状态 | ❌ |
| 观察计算 | `utility_scripts/skills_order_observation_daily.py` | 每日锁单/开票/预测/达成率 | ❌ (dry-run) / ✅ (sync) |
| 分析消费 | `runtime_scripts/` | 稳定分析能力 | ❌ |
| 产品化问数 | `mashang_runtime_v2/` | Runtime V2 问数服务 | ❌ |

## 层级关系

```
dataset/updater/           ← 数据供给层（infrastructure）
    ↓ 产出
dataset/*.parquet/.csv     ← 数据存储层
    ↓ 消费
utility_scripts/           ← 工具层（校验、观察、DataOps）
    ↓ 消费
runtime_scripts/           ← 分析能力层
    ↓ 调度
mashang_runtime_v2/        ← 产品化问数层
```

## Makefile 命令

### 安全检查流程（推荐每日先用）

```bash
make dataset-validate              # 检查 dataset 完整性
make daily-observation-dry-run     # 预检观察结果
```

或合并：

```bash
make daily-data-pipeline-dry-run   # dataset-validate + daily-observation-dry-run
```

### 完整执行流程（写操作）

```bash
make dataset-update                # 刷新 dataset（从数据源拉取）
make dataset-validate              # 校验
make daily-observation-dry-run     # 预检
make daily-observation-sync        # 同步到飞书
```

或合并：

```bash
make daily-data-pipeline           # dataset-update + dataset-validate + daily-observation-sync
```

**注意**：
- `dataset-update` 和 `daily-observation-sync` 是写操作
- `daily-observation-sync` 会写入飞书多维表格和发送飞书机器人通知
- 不要在 CI 中自动执行写操作

## 自然语言入口

中文自然语言入口：**数据更新并同步**

- 这是 workspace-level **DataOps 指令**，不是带日期条件的分析问题
- 不应理解为"只更新今天的数据"
- 它表示从数据源拉取最新数据、刷新 dataset、校验、生成观察结果并同步飞书

| 入口 | 对应命令 |
|------|----------|
| "数据更新并同步" | `make daily-data-pipeline` |
| "预检数据" | `make daily-data-pipeline-dry-run` |

## Runtime V2 关系

- Runtime V2 当前**只负责问数分析**（基于 capability_registry 分发给 `runtime_scripts/`）
- Runtime V2 **不负责数据源刷新**（那是 `dataset/updater/` 的职责）
- Runtime V2 **不调度 `utility_scripts/`**（包括 dataset_validate 和 skills_order_observation_daily）
- Runtime V2 **不响应"数据更新并同步"指令**
- 如果要产品化每日数据同步能力，需包装为 `daily_data_pipeline` runtime capability，并带 `dry-run` / `execute` 安全边界

## 废弃说明

`make daily-sync-dry-run` 已废弃。
请使用 `make daily-observation-dry-run` 替代。
