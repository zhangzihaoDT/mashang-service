# mashang-service · 汽车业务分析

从仓库根目录运行命令。日常分析在 `workspace/` 开展，共享数据从根目录 `dataset/` 读取。

| 我要做什么 | 从哪里开始 |
|---|---|
| 查锁单、门店、库存、预售或上市；更新数据 | [业务任务索引](workspace/README.md)，按问题选命令，查看数据写入和飞书推送影响 |
| 找数据、核对指标或上市日 | [数据集声明](dataset/updater/dataset_registry.py) · [字段与业务口径](shared/schema/README.md) |
| 通过 Hub/Worker 运行固定任务 | [已发布 Job](jobs/config/jobs_config.json) · [调用方式与返回值](jobs/README.md) |
| 让 dsh-superagent 查某代际上市以来锁单 | [LS9 查询示例与工单执行说明](workspace/README.md#dsh-launch-monitor) |
| 开发业务脚本、维护共享算子或 OCR 等通用工具 | [工作区规则](workspace/AGENTS.md) · [共享层](shared/README.md) · [基础能力](capabilities/README.md) |

**统一资料入口**　[文档索引](docs/README.md) · [Agent Skills](.opencode/skills/README.md)。

**结果位置**　日常分析表、图、报告分别交付到 `workspace/outputs/{tables,charts,reports}/`。终端查询直接返回结果；DSH 只读查询使用工单指定的临时文件。

**仓库边界**　Service 维护业务数据、计算和查询入口。Hub/Worker 负责调度，DSH 负责工单和只读工作副本。MIIT 公告采集与归档已迁至平级仓库 [mashang-miit](../mashang-miit)，Service 消费其数据的接口尚未实现。其他研究项目见下文「独立产品与研究仓库」。

## 项目定位与分层

mashang-service 专注汽车业务数据生产、指标与分析。Service 维护从数据更新到业务计算的链路，并通过确定性 Job 向 Hub/Worker 提供稳定入口。

| 职责 | 主要目录 | 维护内容 |
|---|---|---|
| 数据生产 | [dataset/](dataset/README.md) | 数据获取、更新、校验与资产索引。Tableau 导出、外部市场数据和研究样本分区存放 |
| 指标与业务口径 | [shared/](shared/README.md) | 字段定义、业务口径、共享算子与数据读取 |
| 业务分析 | [workspace/](workspace/README.md) | 稳定业务脚本、专题研究与分析产物 |
| 对外执行接口 | [jobs/](jobs/README.md) | 确定性任务、参数白名单、执行状态与产物契约 |
| 通用支撑 | [capabilities/](capabilities/README.md) | OCR、检索、飞书、通知与图表能力 |
| 使用与维护说明 | [docs/](docs/README.md) | 业务专题、数据获取手册、共享规范和历史归档 |

项目 Agent 配置、Skills 和验证契约位于 `.opencode/`。业务产物位于 `workspace/outputs/`，服务级产物按既有入口写入根 `outputs/`。

## 下一阶段

目标是**数据资产登记完整、指标口径可核验、业务能力可稳定调用**。

第一轮以「订单与下发线索刷新 → 数据校验 → 每日锁单查询」贯通现有入口。按三项验收。

- **数据资产**。核对订单与下发线索的来源、更新入口、产物路径、最新数据时点和校验规则。
- **指标口径**。以每日锁单为样例，对照权威指标定义核对日期窗口、去重键和过滤条件，并检查脚本输出中的口径说明。
- **稳定调用**。使用现有 Job 验证固定参数、结果结构和失败状态。生产刷新链路按既有写入权限单独验收。

首轮验收后再收拢。将验证过的登记字段、口径检查和调用要求推广到其他核心数据与业务能力，合并重复说明，并逐项确认历史路径和流程入口的消费者后再清理。

# 快速开始

## 环境准备

使用 Python 3.11+。

项目依赖通过 `pyproject.toml` 管理。

创建虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate
```

安装依赖：

```bash
pip install -e .
```

或：

```bash
pip install -r requirements.txt
```

（如果项目中存在 requirements 文件）

---

## 数据准备

项目默认从根目录读取数据：

```text
dataset/
```

请确保：

```text
mashang-service/
├── dataset/
├── .env
└── .venv/
```

不要随意移动：

```text
dataset/
.env
.venv/
```

否则部分脚本和 Runtime 路径解析可能失效。

---

## 检查入口

在根目录运行 `make jobs-list` 查看已发布 Job。日常查询见 [Workspace 业务任务索引](workspace/README.md)。开发改动的验证范围见 [验证契约](.opencode/verification/README.md)。

### 查看锁单分析能力

运行 Demo：

```bash
make lock-demo
```

示例问题：

```text
昨天锁单数分车型
昨天 LS8 锁单城市分布
```

---

### 查看 ATP 分析能力

```bash
make atp-demo
```

---

### 查看数据字典

```bash
make data-dict
```

---

### 运行 service job

```bash
make jobs-list
make jobs-run JOB=daily_lock_count JOB_PARAMS="--job-param date=2026-11-03"
```

用于验证 `jobs/` 确定性执行契约（Hub/Worker 调用入口）。

---

## 开发者工作流

推荐遵循以下工作模式：

```text
业务问题
  ↓
workspace
  ↓
分析脚本
  ↓
Result Contract
  ↓
Eval
  ↓
Capability Registry
  ↓
稳定能力
  ↓
jobs
```

其中：

- Workspace 用于探索和沉淀能力；
- Hub/Worker 通过已声明的 Job 调用稳定业务脚本，业务实现由 Workspace 维护。

---

## 常用检查命令

```bash
make eval
```

运行核心评测。

```bash
make full-eval
```

运行全量评测。

```bash
make capability-audit
```

检查 Capability Registry。

```bash
make ci
```

运行 CI 安全检查。

---

## 项目目录导航

如果你是：

### 业务分析开发者

重点关注：

```text
workspace/business_scripts/
workspace/research_scripts/
docs/
workspace/eval/
```

---

### Runtime 开发者

重点关注：

```text
jobs/
```

---

### 业务规则维护者

重点关注：

```text
shared/schema/business_definition.json
shared/operators/
```

---

### 产品能力维护者

重点关注：

```text
jobs/
```

这里存放确定性 Job Contract（供 Hub/Worker 调用）。

---

## 典型开发流程

新增一个分析能力：

### Step 1

在：

```text
workspace/research_scripts/
```

完成业务验证。

### Step 2

封装为：

```text
workspace/business_scripts/
```

标准 Runtime Script。

### Step 3

输出标准 Result Contract。

### Step 4

补充 Eval Case。

### Step 5

注册到：

```text
workspace/registry/capability_registry.json
```

### Step 6

通过 Audit 与 Eval。

### Step 7

经过实际使用验证。

### Step 8

对于稳定、高频、口径清晰的能力：

```text
workspace
  ↓
jobs
```

完成产品化沉淀。

---

## 项目定位

`mashang-service` 的目标是构建一个面向汽车业务分析的 AI-native 数据服务系统。

它支持：

- 用自然语言描述业务问题；
- 将问题解析为可执行分析上下文；
- 调度标准化 Runtime Scripts；
- 输出结构化 Result Contract；
- 支持多轮追问；
- 通过 Eval / Contract / Registry 管理能力质量；
- 将成熟能力逐步产品化。

核心思想是：

```text
不是把所有逻辑写进一个复杂 Agent，

而是在 Workspace 中持续沉淀业务能力，
通过文档、脚本、Result Contract 和 Eval 管理质量，

最终把成熟能力回流到 Runtime，
形成稳定可复用的产品能力。
```

---

## Backlog 分析原则

预测链中的一条核心原则（也是 `research_scripts/stalled_order_forecast.py` 存在的理由）：

```text
Nominal Backlog is a system state; Effective Backlog is a forecast.
```

账面上的"待开票未退订锁单数"只是系统状态，不直接代表可交付量。

锁单账龄越久，最终开票概率越低。`stalled_order_forecast.py` 用历史条件开票曲线把每个悬置订单折算为兑现概率，得到 **有效锁单当量（Effective Locked Order Equivalent, ELOE）**：

```text
ELOE = Σ P(最终开票 | 当前仍悬置)
```

它把 Backlog 从静态库存概念变成概率资产概念，并形成预测闭环：

```text
未来新增锁单预测 → 锁单兑现模型 → Effective Backlog → 未来开票/交付预测
```

对应指标（`shared/schema/metrics.json`）：

| 层级 | 指标 | 含义 |
|------|------|------|
| 状态 | 待开票未退订锁单数 | 系统还有多少单处于该状态，纯事实 |
| 质量 | 有效锁单率 | 这些订单预计还有多少比例会兑现 |
| 预测 | 有效锁单当量 (ELOE) | 当前 Backlog 预计贡献多少未来开票 |

---

# 1. Architecture Overview

冻结的五层命名与分层：

```text
1. Semantic Foundation            dataset/ + shared/
        │
        ├─────────────────────────────┐
        │                             │
        ▼                             ▼
2. Base Capabilities          3. Daily Business Analytics Workspace
   capabilities/                 workspace/
   OCR / Search / Notify         日常业务分析工具箱
   Browser / Parse / Render      research → business → eval
        │                             │
        └──────────────┬──────────────┘
                       ▼
4. Jobs（确定性执行契约）          jobs/

5. 独立研究仓库（平级，不在本仓库内）
   ../mashang-auto-launch / ../mashang-product-expert /
   ../mashang-nev-apeal / ../mashang-miit
```

```text
mashang-service/
├── dataset/               # 1. Semantic Foundation — 共享原始数据
├── shared/                #   语义底座：operators / schema / loaders
│
├── capabilities/          # 2. Base Capabilities（领域无关基础能力）
│   ├── README.md
│   ├── ocr/               # OCR 原语（火山 general_ocr + document_parse，缓存/QPS/retry）
│   ├── notify/            # 飞书 Webhook 通知推送
│   └── search/            # 豆包 Global Search 检索原语
│
├── workspace/     # 3. Daily Business Analytics Workspace（日常业务分析工具箱）
│   ├── business_scripts/   #    高频确定业务分析，成熟后经 jobs/ 被 Hub 确定性调度
│   ├── research_scripts/
│   ├── utility_scripts/
│   ├── registry/
│   ├── eval/
│   ├── tests/
│   └── utils/
│
├── jobs/                  # 4. 确定性执行契约层（service job）
│
├── ocr/ 已迁移 → capabilities/ocr   （历史路径不再使用）
├── Makefile
├── pyproject.toml
└── README.md
```

> 分层要点：`capabilities/`（Base Capabilities）与 `workspace/`（Daily Business Analytics）是两支平级的能力来源；
> `jobs/`（确定性执行契约）供 Hub/Worker 调用 workspace 业务能力。

## 独立产品与研究仓库

| 仓库 | 职责 |
|------|------|
| `mashang-fetch` | 获取与整理资料 |
| `mashang-miit` | 获取与整理工信部汽车公告 |
| `mashang-auto-launch` | 新车上市与竞争动态研究 |
| `mashang-product-expert` | 产品专家门店支持研究 |
| `mashang-nev-apeal` | 新能源用户体验研究（归档） |
| `mashang-service` | 利用汽车行业数据开展业务分析与产品战略研究 |

以上仓库平级维护。MIIT 的代码、配置、依赖、原始证据、结构化数据、管线报告与运行记录均在 `mashang-miit`；研究应用的代码、配置、数据与产物在各自仓库。Service 不再内置这些实现，也不通过导入兄弟仓库源码运行。

Service 不保留 `research_apps/` 目录；`auto_launch` / `product_expert` / `nev_apeal` 已在平级仓库独立维护。MIIT 的 Service 数据消费接口尚未实现。

从 Service 根目录可进入独立仓库运行：

```bash
cd ../mashang-miit
make miit-run BATCH=411
```

完整命令与数据契约以独立仓库的 README、AGENTS.md 和 workflow/ 为准。工作台开发交接方案已迁至 [MIIT V1 handoff](../mashang-miit/workflow/miit_workbench_v1_handoff.md)，由 MIIT 仓库维护。

---

# 2. Layered Design

五层命名与定义见 §1（冻结）。以下为各层实现要点。

## 2.1 Shared Layer（Semantic Foundation）

目录：

```text
shared/
├── operators/
└── schema/
```

共享业务语义层，包含：

- 共享业务算子；
- 指标定义；
- 业务规则；
- 车型与配置定义；
- 时间窗口定义；
- `business_definition.json`。

Canonical Path：

```text
shared/schema/business_definition.json
```

被以下模块共同消费：

```text
workspace
shared
jobs
```

原则：

```text
shared 只存放稳定业务原语。
新能力先进入 workspace，再决定是否沉淀到 shared。
```

---

## 2.2 Daily Business Analytics Workspace（workspace）

目录：

```text
workspace/
```

**日常业务分析工作区**：解决"今天我要查什么、算什么、分析什么"（锁单、库存、门店、车型、渠道等高频、相对确定的业务分析）。这是项目最重要的日常工作区，也是 OpenCode 的主要工作区域。

推荐日常所有分析工作都从这里开始。负责：

- 能力孵化（research_scripts → business_scripts）；
- 数据探索；
- Runtime Script 管理；
- Result Contract；
- Eval；
- Capability Registry；
- 文档沉淀；
- 能力治理。

成熟后的 `business_scripts` 会被 Hub 经 `jobs/` 以确定性方式调用。

---

## 2.3 Jobs（确定性执行契约，jobs/）

目录：

```text
jobs/
├── adapter.py              # execution contract：load_jobs / validate_params / run_job
├── cli.py                  # Worker/Hub 调用入口（--job / --job-param / --list）
├── config/jobs_config.json # 声明式 job 定义
└── tests/
```

**确定性执行契约层**。运行时系统由 **Hub（Control Plane）+ Worker（Execution Gateway）+ OpenCode**
组成，`jobs/` 是 service 侧唯一被调度的确定性边界：

```text
jobs/
├── Job 声明             config/jobs_config.json（argv 模板 / cwd / 参数白名单 / artifact）
├── 参数校验             validate_params（date / pattern / 未声明参数拒绝）
├── 确定性执行           run_job（无 shell，固定 argv，超时）
└── Execution Contract   status / returncode / duration / summary / artifacts
```

原则：

```text
jobs 不重新发明分析能力；
jobs 调用 workspace 已治理能力（不复制业务代码）；
jobs 只做声明、校验、执行与结果契约，不做 NL 路由 / 会话 / 渲染 / UI。
```

独立研究仓库的编排不在 service 内；service 只保留 workspace job 契约。

---

## 2.4 Legacy Runtime（已退役）

旧 `mashang_runtime/`（legacy frozen）与 `mashang_runtime_v2/`（NL 问数 Runtime）均已**退役移除**。
operators/schema 的 canonical 版本一直在 `shared/`；确定性的 service job 能力已收敛到根目录 `jobs/`。

---

# 3. Capability Lifecycle

推荐生命周期：

```text
research_scripts
  ↓
business_scripts
  ↓
Result Contract
  ↓
Eval
  ↓
Capability Registry
  ↓
业务验证
  ↓
jobs
```

对应：

```text
研究探索
  ↓
标准封装
  ↓
输出协议
  ↓
质量验证
  ↓
能力治理
  ↓
实际使用
  ↓
产品沉淀
```

---

# 4. Script Tiers

| Tier     | Directory           | Role         | Auto Schedulable | Default Eval |
| -------- | ------------------- | ------------ | ---------------- | ------------ |
| runtime  | `business_scripts/`  | 稳定分析能力 | yes              | yes          |
| research | `research_scripts/` | 研究能力     | no               | no           |
| utility  | `utility_scripts/`  | 工具脚本     | no               | no           |
| legacy   | `legacy_scripts/`   | 历史脚本     | no               | no           |

原则：

```text
普通业务问题默认只调度 business_scripts。
research_scripts 必须显式调用。
```

---

# 5. Capability Registry

注册表：

```text
workspace/registry/capability_registry.json
```

当前核心能力：

```text
daily_lock_count
lock_by_model
lock_city_distribution
assign_conversion_analysis
attribute_penetration_report
atp_price_report
```

Registry 的核心作用是：

```text
记录能力状态，
帮助判断哪些能力已经具备产品化条件。
```

---

# 6. Result Contract

标准输出结构：

```json
{
  "status": "success",
  "metric": "...",
  "scope": {},
  "summary": {},
  "dimensions": [],
  "followup_context": {}
}
```

文档：

```text
docs/共享规范/result_contract.md
```

---

# 7. Evaluation System

常用命令：

```bash
make eval
```

```bash
make full-eval
```

```bash
make ci
```

```bash
make test
```

Eval 的目标不是测试代码本身，而是验证：

- 业务口径；
- 数值正确性；
- Result Contract；
- Follow-up 能力；
- 产品化准备度。

---

# 8. Current jobs Status

`jobs/` 当前声明的 service job：

```text
daily_lock_count   # --job-param date=YYYY-MM-DD → Result Contract JSON
```

调用：

```bash
make jobs-list
make jobs-run JOB=daily_lock_count JOB_PARAMS="--job-param date=2026-11-03"
```

> 普通问数不由 service 内部 Runtime 承担：运行时系统 = Hub（Control Plane）+ Worker（Execution Gateway）+ OpenCode。

---

## 拆分记录

旧 Runtime 的退役范围和迁移记录见 [Service 架构基线](docs/共享规范/architecture_baseline.md)。

---

# 10. One-sentence Summary

```text
shared              # shared business semantics
workspace   # capability incubation and governance
jobs                # deterministic execution contract (Hub/Worker)
```

核心原则：

```text
平时主要在 Workspace 中工作，
让 OpenCode 分析、写脚本、补文档、沉淀 Eval 和 Result Contract；

当能力经过验证、使用频繁且业务口径稳定后，
再经 jobs/ 契约被 Hub 确定性调度，成为真正的产品能力。
```

---

# 11. Project Structure Boundaries / 项目结构边界

## service 层

根目录配置属于 service 层，包括：

```text
opencode.jsonc       # OpenCode 配置（MCP server、agent 定义）
Makefile             # 项目级命令（eval / build / pipeline）
pyproject.toml       # Python 项目配置
.github/             # CI 工作流
```

Playwright MCP 是 service 级 **browser ingestion** 能力，配置在 `opencode.jsonc` 中。
Playwright 的浏览器 profile 和登录态存储在 `.local/playwright-mcp/`，不提交 Git。

---

## dataset/incoming/

`dataset/incoming/` 是 service 级**外部原始数据入口**。

用于存放通过浏览器、飞书内部系统、API 下载等方式获取的原始文件。飞书下载入口统一为：

```text
dataset/incoming/feishu/
```

该目录**不提交 Git**，由 `.gitignore` 覆盖。

---

## .local/

`.local/` 存放本地浏览器 profile、登录态 Cookie、临时环境数据。

```text
.local/playwright-mcp/feishu/     # Chrome profile + session cookies
```

该目录**永不提交 Git**，仅用于本地开发时的登录态持久化。

---

## workspace

`workspace/` 是当前 Agent 工作区，负责：

- 分析探索（`research_scripts/`）
- 稳定分析脚本（`business_scripts/`）
- 工具脚本（`utility_scripts/`）
- 数据管道（DataOps）
- 测试（`tests/`）
- 评测（`eval/`）
- 文档沉淀（`docs/`）
- 输出产物（`outputs/`）

workspace **消费** `dataset/incoming/` 中的文件，但**不作为 Playwright 下载入口**。
所有通过 Playwright / 浏览器下载的文件，统一写入 `dataset/incoming/`。

---

## ocr

```text
ocr/                 # （历史）→ 已迁移为 capabilities/ocr（Base Capability）
```

OCR 作为领域无关基础能力归位于：

```text
capabilities/ocr/    # Base Capability：截图 → 文字/markdown/表格（火山 OCR），缓存/QPS/retry
```

详见 `capabilities/README.md` 与 `capabilities/ocr/README.md`。

> `source_capture/`（一次性抓图/归档原图）已移除。浏览器下载统一写入 `dataset/incoming/`，原始截图不再落仓库。

---

## shared

`shared/` 是当前共享算子、Schema、Loader 的**唯一可信来源**。

```text
shared/
├── operators/     # 14 个 canonical 业务算子
├── schema/        # metric registry, business definitions
└── loaders/       # dataset loaders (TP&MIX-ways 等)
```

`shared/` 中的 operators 是 canonical 版本（旧 Runtime 副本已随 `mashang_runtime/` 退役移除）。

---

## mashang_runtime（已退役）

`mashang_runtime/` 已**退役移除**：

- operators 和 schema 的 canonical 版本一直是 `shared/`
- 根 `main.py` / `feishu_bot.py` 兼容 shim 一并移除
- workspace 不再有任何 import 指向旧 Runtime

---

## outputs

输出产物分为三层：

| 路径 | 内容 | Git 策略 |
|------|------|----------|
| `outputs/assets/brand/` | 品牌资产（logo、签名） | ✅ 提交 |
| `outputs/reports/` | 正式渲染报告（HTML/PDF/DOCX） | 🟡 按需 |
| `outputs/submission/` | 正式申报材料 | 🟡 按需 |
| `workspace/outputs/reports/` | 分析报告 | 🟡 按需 |
| `workspace/outputs/tables/` | 结构化数据 | 🟡 考虑 gitignore |
| `workspace/outputs/charts/` | 可视化图表 | 🟡 考虑 gitignore |

原则：可复现产物（CSV/JSON/图表）建议不提交；展示资产（品牌 logo / 正式报告）按需提交。
