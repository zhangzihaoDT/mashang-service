# Script Tiers — 脚本分层治理

## 四层分类 + 物理目录

| Tier | 目录 | 说明 | 自动调度 | Core Eval | Research Eval | 示例 |
|------|------|------|:--------:|:---------:|:-------------:|------|
| **core** | `runtime_scripts/` | 稳定日常脚本，can be auto-invoked by followup_runner / OpenCode / Runtime V2 | ✅ | ✅ | ❌ | lock_by_model, daily_lock_count |
| **research** | `research_scripts/` | 研发脚本，仅用户明确要求时调用（预测/回测/释放曲线） | ❌ | ❌ | ✅ | cohort_forecast, backtest, release_curve |
| **utility** | `utility_scripts/` | 基础设施脚本（DataOps/SyncOps/数据字典/VOC），非分析能力 | ❌ | ❌ | ❌ | data_dictionary, skills_order_observation_daily |

## 三层物理目录位置

```
mashang_workspace/
├── runtime_scripts/       # Core — Runtime V2 可调度
├── research_scripts/      # Research — 仅手动执行
├── utility_scripts/       # Utility — DataOps/SyncOps 工具
├── outputs/reports/       # 报告输出
├── (scripts/ 已删除)
└── (legacy_scripts/ 已退休)
```

## 脚本 Tier 归属

### Core Scripts (6 个) — `runtime_scripts/`

| 脚本 | 说明 | CLI | Result Contract | Make target |
|------|------|:---:|:---------------:|-------------|
| `daily_lock_count.py` | 每日锁单 | `--date --series --format` | ✅ | `make lock-demo` |
| `lock_by_model.py` | 车型拆分 | `--date --series --limit --format` | ✅ | `make lock-demo` |
| `lock_city_distribution.py` | 城市分布 | `--date --series --by-region --format` | ✅ | — |
| `assign_conversion_analysis.py` | 线索转化 | `--start-date --end-date --format` | ✅ | — |
| `attribute_penetration_report.py` | 配置渗透率 | `--series --attribute --limit --format` | ✅ | — |
| `atp_price_report.py` | ATP 月报 | `--month --format` | ✅ | `make atp-demo` |

### Research Scripts (6 个) — `research_scripts/`

| 脚本 | 说明 | CLI | Result Contract | Make target |
|------|------|:---:|:---------------:|-------------|
| `cohort_forecast.py` | 预测锁单 | `--start-date --end-date --format` | ✅ (partial) | — |
| `lock_predict_backtest.py` | 回测验证 | `--format` | ✅ | `make backtest-demo` |
| `lock_predict_backtest.py` | 回测原脚本 | — | ❌ | — |
| `lock_release_curve.py` | 释放曲线核心 | — | ❌ | — |
| `release_curve_analysis.py` | 释放曲线报告 | `--output --format` | ❌ (wrapper) | — |
| `quick_lock_ratio.py` | 同比分析 | — | ❌ | — |

### Utility Scripts (5 个) — `utility_scripts/`

| 脚本 | 说明 | 定位 |
|------|------|------|
| `data_dictionary.py` | 数据字典 | 数据工具 |
| `voc_theme_analysis.py` | VOC 骨架 | 分析工具 |
| `generate_eval_cases.py` | Eval 用例生成 | 测试工具 |
| `skills_order_observation_daily.py` | 每日数据观察与同步 | **DataOps/SyncOps** |
| `skills_attainment_rate_alert.py` | 达成率预警 | 监控工具 |

## Eval 分层

| Suite | 覆盖 | 数据依赖 |
|-------|------|:--------:|
| `core` | 6 个 core scripts 的 contract + numeric | ✅ |
| `research` | 6 个 research scripts 的 contract + numeric | ✅ |
| `all` | core + research + parser + followup + reference + smoke | ✅ |
| `ci` | parser + followup + reference (不依赖真实数据) | ❌ |

## Makefile 命令

| 命令 | 等价于 |
|------|--------|
| `make eval` | core + parser + followup + reference |
| `make full-eval` | all (core + research + 全部) |
| `make core-eval` | core suites only |
| `make research-eval` | research suites only |
| `make ci` | CI-safe suites |

## 外部数据供给层

数据刷新由 `dataset/updater/` 负责，不属于 workspace 分析脚本：

| 脚本 | 职责 | 写操作 |
|------|------|--------|
| `dataset/updater/update_all_datasets.py` | 从 Tableau/数据源刷新 dataset | ✅ 刷新本地文件 |
| `dataset/updater/order_data_to_parquet.py` | 刷新 order_data.parquet | ✅ |
| `dataset/updater/order_config_to_parquet.py` | 刷新 config_attribute.parquet | ✅ |
| `dataset/updater/lock_attribution_data_to_parquet.py` | 刷新 assign/test_drive/lock_attribution | ✅ |

详见 `docs/daily_data_pipeline.md`。

## 使用规则

1. **OpenCode / followup_runner / Runtime V2** 只能自动调用 **runtime_scripts/** （core tier）脚本
2. 用户明确提到"预测""回测""释放曲线"等关键词时，可调用 **research_scripts/**
3. **legacy_scripts/** 已退休删除，历史脚本已迁移到 runtime_scripts/research_scripts/utility_scripts
4. **skills_order_observation_daily.py** 是 DataOps/SyncOps 脚本，涉及外部写操作，必须通过 dry-run/execute 安全开关
5. **dataset/updater/** 是数据供给基础设施，不属于 workspace 分析能力
6. **Runtime V2 不调度 dataset/updater 和 utility_scripts**
7. 新脚本默认进入 **research_scripts/**，稳定迭代后升为 **runtime_scripts/**
8. 核心口径变更必须先批准再升级
