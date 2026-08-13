# Project Inventory — mahsang

> Generated: 2026-06-11

## 1. 当前主要目录结构

```
mashang-service/
├── agent/              # Runtime Agent 核心代码
├── dataset/            # 数据文件 (CSV/Parquet)
├── docs/               # 新创建: 文档目录
├── eval/               # Eval 测试框架
├── HTML/               # 工信部新车 HTML 展示
├── logs/               # 运行时日志
├── operators/          # 业务算子
├── outputs/            # 新创建: 输出目录
├── schema/             # Schema/业务定义/配置
├── scripts/            # 自动化脚本 + 报告
├── tools/              # 确定性执行工具
├── 设计方案/           # 设计文档
├── main.py             # CLI 入口
├── feishu_bot.py       # 飞书机器人入口
└── README.md           # 项目文档 (含完整架构说明)
```

## 2. Runtime 代码 (应归入 mashang_runtime/)

| 目录/文件 | 说明 | 建议目标 |
|-----------|------|----------|
| `agent/` | Agent 主循环、规划器、状态管理、路由、运行时决策 | `mashang_runtime/agent/` |
| `tools/` | 查询/比较/统计/合成/多表/快速路径/报告等工具 | `mashang_runtime/tools/` |
| `operators/` | 10 个固定业务算子 (在营门店/留存/转化/预测等) | `mashang_runtime/operators/` |
| `main.py` | 命令行入口 | `mashang_runtime/` (或根) |
| `feishu_bot.py` | 飞书机器人入口 | `mashang_runtime/` (或根) |
| `schema/` | Metric 注册表、业务定义、数据路径、Schema 文档 | `mashang_runtime/schema/` (或根) |

## 3. 数据文件

| 文件 | 格式 | 说明 |
|------|------|------|
| `dataset/order_data.parquet` | Parquet | 订单主表 (445,915 行) |
| `dataset/assign_data.csv` | CSV | 下发线索表 (1,184 行) |
| `dataset/config_attribute.parquet` | Parquet | 选配属性表 (含 value_code 配置 code) |
| `dataset/lock_attribution_data.parquet` | Parquet | 锁单归因表 |
| `dataset/test_drive_data.csv` | CSV | 试驾数据 |
| `dataset/config_attribute_data.csv` | CSV | 2023 选配快照（含 Value 配置 code） |
| `dataset/config_attribute_data2024.csv` | CSV | 2024 选配快照（含 Value 配置 code） |
| `dataset/config_attribute_data2025.csv` | CSV | 2025 选配快照（含 Value 配置 code） |
| `dataset/config_attribute_data2026.csv` | CSV | 2026 选配快照（含 Value 配置 code） |
| `dataset/config_attribute_data_update.csv` | CSV | 最新 Tableau 视图变更增量（mobile 路线） |
| `dataset/order_data_2023.csv` | CSV | 2023 订单数据 |
| `dataset/order_data_2024.csv` | CSV | 2024 订单数据 |
| `dataset/order_data_2025.csv` | CSV | 2025 订单数据 |
| `dataset/order_data_2026.csv` | CSV | 2026 订单数据 |
| `dataset/锁单归因_data_2026.csv` | CSV | 2026 锁单归因 |
| `dataset/品牌 A3 流转.csv` | CSV | 品牌 A3 流转数据 |
| `dataset/TOP10A3 流转_懂车帝.csv` | CSV | TOP10 A3 流转 |
| `dataset/LS6A3流出T+15_1025.csv` | CSV | LS6 A3 流出 |
| `dataset/LS8A3流出T+15_0525.csv` | CSV | LS8 A3 流出 |
| `dataset/LS8A3流出T+30_0525.csv` | CSV | LS8 A3 流出 (30d) |
| `dataset/云图人群资产结构.csv` | CSV | 云图人群资产 |
| `dataset/wechat/销售全员群.parquet` | Parquet | 微信群消息 |
| `dataset/passenger_insurance/` | 目录 | 乘用车上险数据资产（6 张 Parquet + registry + quality） |
| `dataset/passenger_insurance/registry/passenger_insurance_tables.json` | JSON | 上险数据注册表 |
| `dataset/passenger_insurance/raw_csv/` | 目录 | 6 张 Tableau 导出 CSV（UTF-16 LE, tab-delimited, pivot） |
| `logs/last_result.parquet` | Parquet | 上次查询结果缓存 |
| `logs/query_log.jsonl` | JSONL | 查询日志 |
| `agent/.query_agent_memory.json` | JSON | Agent 对话记忆 |

## 4. 分析脚本

| 文件 | 说明 | 建议目标 |
|------|------|----------|
| `scripts/lock_release_curve.py` | 锁单释放曲线分析 (~700 行) | `scripts/` |
| `scripts/quick_lock_ratio.py` | 锁单累计同比分析 (~870 行) | `scripts/` |
| `scripts/lock_predict_backtest.py` | 预测锁单回测 (~326 行) | `scripts/` |
| `scripts/skills_atp_price.py` | ATP 价格月报 (~177 行) | `scripts/` |
| `scripts/skills_order_observation_daily.py` | 每日锁单观察 (~911 行) | `scripts/` |
| `scripts/skills_attainment_rate_alert.py` | 达成率预警 (~195 行) | `scripts/` |
| `scripts/generate_eval_cases.py` | Eval case 生成 (~292 行) | `scripts/` |
| `research_scripts/pk_weekly_ls8_ls9.py` | LS8 vs LS9 周度对比 | `research_scripts/` |
| `research_scripts/competition_a3_flow.py` | A3 人群流转分析 | `research_scripts/` |

> MIIT 新车公告监控（原 `research_scripts/miit_new_car/`）实现已随重构移除，历史数据成果归档于 `MIIT/data/eidc/`，能力在 `MIIT/scripts/` 重新实现。

## 5. 配置、业务定义、指标口径

| 文件 | 说明 |
|------|------|
| `schema/business_definition.json` | 业务定义 (时间窗口/电池容量/车型映射/系列分组/座位数) |
| `schema/metrics.json` | 指标注册表 (27 个指标 + 5 个派生率指标) |
| `schema/schema.md` | Schema 详细文档 (字段映射、维度说明) |
| `schema/data_path.md` | 数据路径配置 + 路由架构图 |
| `schema/5A 流转记录.md` | 5A 人群资产流转记录 |
| `schema/销售群动态记录.md` | 销售群动态记录 |
| `schema/销售群动态记录_new.md` | 新销售群动态记录 |
| `operators/registry.json` | 算子注册表 (10 个算子) |
| `operators/operator_catalog.json` | 算子目录 (LLM 提示词用) |
| `agent/llm_config.py` | LLM 模型配置 |
| `.env` | 环境变量 (API Key) |
| `requirements.txt` | Python 依赖 |
| `scripts/lock_release_analysis.md` | 释放曲线计算逻辑文档 |

## 6. Eval/Test 文件

| 文件 | 说明 |
|------|------|
| `eval/run_runtime_eval.py` | Runtime Eval Runner |
| `eval/analyze_eval_report.py` | Eval 结果分析 |
| `eval/eval_report.json` | Eval 报告 |
| `eval/runtime_cases.jsonl` | Runtime 测试用例 |
| `scripts/generate_eval_cases.py` | 从 query_log 生成 eval cases |

## 7. 设计文档

| 文件 | 说明 |
|------|------|
| `设计方案/AgenticBI方案.md` | Agentic BI 整体方案 |
| `设计方案/feishu接入方案.md` | 飞书接入方案 |
| `设计方案/loop方案.md` | Agent Loop 方案 |
| `设计方案/memory方案.md` | Memory 方案 |
| `HTML/工信部新车/Prompt.md` | 工信部新车 Prompt |

## 8. 输出文件 (已有)

| 文件 | 说明 |
|------|------|
| `outputs/reports/atp_2026-04.html` | ATP 月报 2026-04 |
| `outputs/reports/atp_2026-05.html` | ATP 月报 2026-05 |
| `outputs/reports/daily_msg_report.html` | 每日消息报告 |
| `outputs/reports/lock_predict_backtest.html` | 预测回测报告 |
| `outputs/reports/lock_release_curve.html` | 释放曲线报告 |
| `outputs/reports/pk_weekly_compare_ls8_ls9.html` | LS8 vs LS9 周度对比 |
| `outputs/reports/quick_lock_ratio.html` | 锁单累计同比报告 |
| `outputs/reports/竞争洞察A3人群流转.html` | A3 人群流转报告 |

## 9. 基础设施与服务能力

### 9.1 Playwright MCP

- Playwright MCP 已配置在 service 层 `opencode.jsonc`。
- Playwright MCP 的定位是 **service 级 browser ingestion 能力**。
- 浏览器 profile / 登录态保存在 `.local/playwright-mcp/feishu/`（不提交 Git）。

### 9.2 飞书下载入口

飞书等浏览器下载得到的原始文件统一存放在：

```text
dataset/incoming/feishu/
```

此目录已被 `.gitignore` 覆盖，不提交 Git。

`.local/playwright-mcp/feishu/` 只保存浏览器 profile 和登录态 Cookie，
**不保存业务文件**。业务文件请下载到 `dataset/incoming/feishu/`。

**mashang_workspace 不作为 Playwright 下载入口**，
workspace 只消费 `dataset/incoming/feishu/` 中的文件。

### 9.3 mashang_shared

`shared/` 是当前共享算子与 Schema 的 **canonical 位置**。

- `shared/operators/` — canonical 业务算子（14 个）
- `shared/schema/` — metric registry、business definitions
- `shared/loaders/` — dataset loaders（passenger_insurance 等）

`mashang_runtime/operators/` 和 `mashang_runtime/schema/` 保留 legacy 副本，
但 **不再作为 canonical 来源**。

### 9.4 mashang_runtime

`mashang_runtime/` 标记为 **legacy frozen**。

- 当前 workspace **没有**任何 import 指向 `mashang_runtime/`
- 不建议新增依赖
- operators / schema 的 canonical 版本已迁移至 `shared/`
- 未来考虑重命名为 `mashang_runtime.legacy/`

---

## 10. 迁移建议摘要

| 源路径 | 目标路径 | 操作 |
|--------|----------|------|
| `agent/` | `mashang_runtime/agent/` | 先标注，后续迁移 |
| `tools/` | `mashang_runtime/tools/` | 先标注，后续迁移 |
| `operators/` | `mashang_runtime/operators/` | 先标注，后续迁移 |
| `schema/` | `mashang_runtime/schema/` | 先标注，后续迁移 |
| `scripts/` | 保留 | 已有良好结构 |
| `research_scripts/pk_weekly_ls8_ls9.py` | `research_scripts/pk_weekly_ls8_ls9.py` | 已完成迁移 |
| `research_scripts/competition_a3_flow.py` | `research_scripts/competition_a3_flow.py` | 已完成迁移 |
| `eval/` | 保留 | 已有良好结构 |
| `设计方案/` | `docs/design/` | 建议迁移 |
