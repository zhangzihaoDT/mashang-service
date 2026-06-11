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
├── requirements.txt               # 共享依赖
│
├── mashang_runtime/             # Legacy runtime (frozen, packaged)
│   └── README.md
│
└── mashang_workspace/             # ← AI-native 分析工作区（当前所在目录）
│   ├── AGENTS.md                  # 本文件
│   ├── README.md
│   ├── docs/
│   ├── scripts/
│   ├── eval/
│   ├── tests/
│   ├── utils/
│   └── outputs/
```

## 工作原则

1. **不要修改 dataset/ 下的原始数据**
2. **不要移动 .env 或 .venv/**
3. **优先使用已有 scripts/ 脚本**
4. **临时分析写入 outputs/，稳定后再沉淀到 scripts/**
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

| 命令 | 说明 |
|------|------|
| `python scripts/daily_lock_count.py` | 每日锁单 |
| `python scripts/lock_by_model.py --limit 5` | 车型拆分 |
| `python scripts/lock_city_distribution.py` | 城市分布 |
| `python scripts/release_curve_analysis.py` | 释放曲线 |
| `python scripts/cohort_forecast.py` | 预测锁单 |
| `python scripts/voc_theme_analysis.py` | VOC 分析 |
| `python scripts/data_dictionary.py` | 数据字典 |
| `python eval/parse_context_cli.py "..."` | 自然语言解析 |
| `python eval/run_followup_eval.py` | 追问 Runner |
| `python eval/run_numeric_eval.py` | 数值校验 |
| `pytest tests -q` | 全量测试 |
