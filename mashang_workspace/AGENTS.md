# AGENTS.md — mashang_workspace Guide

等同于项目根目录 `AGENTS.md` 的 workspace 专用版本。
所有 workspace 内的 AI Agent 请优先阅读此文档和根目录 AGENTS.md。

## 项目结构

```
mashang-service/                   # 总项目根目录
├── AGENTS.md                      # 根目录 Agent 指南（项目级）
├── README.md                      # 项目主文档
├── Makefile                       # 常用命令
├── pyproject.toml                 # 项目配置
├── .github/workflows/             # CI 配置
├── .env                           # 共享环境变量
├── .venv/                         # 共享虚拟环境
├── dataset/                       # 共享原始数据
│   └── passenger_insurance/       #   └── 乘用车上险数据（6 张 Parquet + registry + quality）
├── requirements.txt               # 共享依赖
│
├── mashang_runtime/             # Legacy runtime (frozen, packaged)
│   └── README.md
│
└── mashang_workspace/             # ← AI-native 分析工作区（当前所在目录）
│   ├── AGENTS.md                  # 本文件
│   ├── README.md
│   ├── docs/
│   ├── runtime_scripts/           # Core — Runtime V2 可调度
│   ├── research_scripts/          # Research — 预测/回测/释放曲线
│   ├── utility_scripts/           # Utility — DataOps/SyncOps 工具
│   ├── legacy_scripts/            # Legacy — 历史保留
│   ├── (scripts/ — 已删除)        # 原始混合池已删除
│   ├── eval/
│   ├── tests/
│   ├── utils/
│   └── outputs/
```

## 工作原则

1. **不要修改 dataset/ 下的原始数据**
2. **不要移动 .env 或 .venv/**
3. **优先使用已有 runtime_scripts/ / research_scripts/ / utility_scripts/ 脚本**
4. **临时分析写入 outputs/，稳定后再沉淀到 runtime_scripts/**
5. **所有分析结果说明数据来源、时间窗口、口径**
6. **高频能力回流到 mashang_runtime/**
7. **每次改动后运行 `make eval` 或 `make ci`**

## 常用 Make 命令

```bash
make eval             # 完整 Eval（6 suites）
make test             # 完整测试
make ci               # CI 门禁
make data-dict        # 数据字典
make lock-demo        # 锁单 Demo
make parser-demo      # Context Parser
make followup-demo    # Follow-up Runner
make numeric-eval     # Numeric Eval
make reference-eval   # Reference Eval
make dataset-validate # 校验 dataset 完整性
make daily-observation-dry-run  # 每日观察预检
```

## CI 门禁

GitHub Actions 在每次 push/PR 时自动运行：

```bash
python mashang_workspace/eval/run_eval.py --suite ci
pytest mashang_workspace/tests/test_root_cleanup.py ... -q
```

CI-safe suites 包含 `parser + followup + reference`，不依赖真实 dataset。
本地完整测试使用 `make eval`。

## Result Contract

所有脚本 `--format json` 输出统一 Result Contract，包含 scope/result/followup_context。
详见 `docs/result_contract.md`。

## Unified Eval

`eval/run_eval.py` 是 workspace 健康检查入口。

```bash
python mashang_workspace/eval/run_eval.py --suite all    # 完整
python mashang_workspace/eval/run_eval.py --suite ci     # CI-safe
python mashang_workspace/eval/run_eval.py --suite parser  # 单套件
```

## 核心脚本速查

| 命令 | 说明 | 层级 |
|------|------|------|
| `python runtime_scripts/daily_lock_count.py` | 每日锁单 | runtime |
| `python runtime_scripts/lock_by_model.py --limit 5` | 车型拆分 | runtime |
| `python runtime_scripts/lock_city_distribution.py` | 城市分布 | runtime |
| `python research_scripts/release_curve_analysis.py` | 释放曲线 | research |
| `python research_scripts/cohort_forecast.py` | 预测锁单 | research |
| `python utility_scripts/voc_theme_analysis.py` | VOC 分析 | utility |
| `python utility_scripts/data_dictionary.py` | 数据字典 | utility |
| `python utility_scripts/skills_order_observation_daily.py` | 每日数据观察(DataOps) | utility |
| `python eval/parse_context_cli.py "..."` | 自然语言解析 | eval |
| `python eval/run_followup_eval.py` | 追问 Runner | eval |
| `python eval/run_numeric_eval.py` | 数值校验 | eval |
| `pytest tests -q` | 全量测试 | test |

## Passenger Insurance Data Asset / 乘用车上险数据资产

### 资产定位

passenger_insurance 是 **service 级共享数据资产**，不属于 workspace 私有数据。
数据资产本体位于 `../dataset/passenger_insurance/`（项目根目录）。

### 使用规则

- workspace **不直接读取 raw_csv**
- workspace **不复制 parquet** 到 workspace 内
- workspace **不维护字段映射**
- workspace 仅通过 shared loader 读取：

```python
from shared.loaders.passenger_insurance_loader import (
    load_passenger_insurance_table,
    load_passenger_insurance_registry,
    list_passenger_insurance_tables,
)
```

### 6 张可用表

| Parquet | Grain | 用途 |
|---------|-------|------|
| `market_energy_monthly` | date_month, fuel_type_group, fuel_type | 市场总量、能源结构、新能源渗透率 |
| `brand_monthly` | date_month, brand | 品牌排名、品牌份额、品牌价格重心 |
| `model_monthly` | date_month, brand, model, sub_model, sub_model_id | 车型排名、车型趋势、品牌内部车型结构 |
| `geo_monthly` | date_month, province, city, city_tier_group, fuel_type_group | 省市市场、城市线级、区域结构 |
| `price_segment_monthly` | date_month, tp_bucket_5w, tp_bucket_10w, fuel_type_group, body_type, vehicle_level_group | 价格带市场、20-30 万、价格结构 |
| `product_segment_monthly` | date_month, saic_segment, body_type, vehicle_level, vehicle_level_group, fuel_type_group, drive_type_group | 细分市场、车身结构、级别结构、驱动结构、尺寸重心 |

### workspace 的职责

**负责**：
- 分析探索
- 图表输出
- 报告生成
- 验证后为 runtimeV2 提供查询原型

**不负责**：
- 读取 Tableau raw_csv
- 构建 Parquet
- 修改 registry
- 维护另一份 loader
- 生成一张大宽表

详见 `docs/passenger_insurance_usage.md`。

## 自然语言指令

| 用户说 | 含义 | 对应操作 |
|--------|------|----------|
| "数据更新并同步" | DataOps 指令，非日期分析问题 | `make daily-data-pipeline`（注意：写操作） |
| "预检数据" | 安全预检 | `make daily-data-pipeline-dry-run` |

注意：
- "数据更新并同步" 不是带日期条件的分析问题，不表示"只更新今天的数据"
- Runtime V2 不响应这个指令

## Visual Identity Usage

This project inherits the global Raccoon Research visual identity.

Apply it only to user-facing outputs, including:

- HTML reports
- dashboard mockups
- article assets
- README screenshots
- Agent UI pages

Do not apply it to:

- raw data files
- logs
- tests
- CLI debug output
- internal JSON artifacts
- analytical chart interiors

In this project, the visual system should behave as a data product style, not as a decorative mascot style.

Use the raccoon avatar or brand wordmark only in report headers, footers, cover pages, empty states, and final signatures.

Charts, tables, and metric cards should remain clean, readable, and data-first.

Default output path for branded reports:

```text
outputs/reports/
```

Default template path:

```text
templates/report_base.html
templates/report_style.css
```
