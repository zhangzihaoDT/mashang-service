# Script Tiers — 脚本分层治理

## 四层分类

| Tier | 说明 | 自动调度 | Core Eval | Research Eval | 示例 |
|------|------|:--------:|:---------:|:-------------:|------|
| **core** | 稳定日常脚本，can be auto-invoked by followup_runner / OpenCode | ✅ | ✅ | ❌ | lock_by_model, daily_lock_count |
| **research** | 研发脚本，仅用户明确要求时调用（预测/回测/释放曲线） | ❌ | ❌ | ✅ | cohort_forecast, backtest, release_curve |
| **utility** | 基础设施脚本，非分析能力 | ❌ | ❌ | ❌ | data_dictionary, generate_eval_cases |
| **legacy** | 原始保留脚本，不主动开发 | ❌ | ❌ | ❌ | skills_atp_price, lock_predict_backtest |

## 脚本 Tier 归属

### Core Scripts (6 个)

| 脚本 | 说明 | CLI | Result Contract | Make target |
|------|------|:---:|:---------------:|-------------|
| `daily_lock_count.py` | 每日锁单 | `--date --series --format` | ✅ | `make lock-demo` |
| `lock_by_model.py` | 车型拆分 | `--date --series --limit --format` | ✅ | `make lock-demo` |
| `lock_city_distribution.py` | 城市分布 | `--date --series --by-region --format` | ✅ | — |
| `assign_conversion_analysis.py` | 线索转化 | `--start-date --end-date --format` | ✅ | — |
| `attribute_penetration_report.py` | 配置渗透率 | `--series --attribute --limit --format` | ✅ | — |
| `atp_price_report.py` | ATP 月报 | `--month --format` | ✅ | `make atp-demo` |

### Research Scripts (3 个)

| 脚本 | 说明 | CLI | Result Contract | Make target |
|------|------|:---:|:---------------:|-------------|
| `cohort_forecast.py` | 预测锁单 | `--start-date --end-date --format` | ✅ (partial) | — |
| `lock_predict_backtest_cli.py` | 回测验证 | `--start-date --end-date --format` | ✅ (partial) | `make backtest-demo` |
| `release_curve_analysis.py` | 释放曲线 | `--output --format` | ❌ (wrapper) | — |

### Utility Scripts (4 个)

| 脚本 | 说明 |
|------|------|
| `data_dictionary.py` | 数据字典 |
| `voc_theme_analysis.py` | VOC 骨架 |
| `generate_eval_cases.py` | Eval 用例生成 |
| `skills_attainment_rate_alert.py` | 达成率预警 |

### Legacy Scripts (4 个)

| 脚本 | 说明 |
|------|------|
| `skills_atp_price.py` | ATP 原脚本 |
| `lock_predict_backtest.py` | 回测原脚本 |
| `skills_order_observation_daily.py` | 原每日观察 |
| `quick_lock_ratio.py` | 同比分析（大型脚本） |

## Eval 分层

| Suite | 覆盖 | 数据依赖 |
|-------|------|:--------:|
| `core` | 6 个 core scripts 的 contract + numeric | ✅ |
| `research` | 3 个 research scripts 的 contract + numeric | ✅ |
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

## 使用规则

1. **OpenCode / followup_runner** 只能自动调用 **core** tier 脚本
2. 用户明确提到"预测""回测""释放曲线"等关键词时，可调用 **research** tier
3. **utility / legacy** 脚本不应被自动化工具直接调用（data_dictionary 例外）
4. 新脚本默认进入 **research**，稳定迭代后升为 **core**
5. 核心口径变更必须先批准再升级
