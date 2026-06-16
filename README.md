# mashang-service

`mashang-service` 是一个面向汽车业务数据分析的 AI-native Analytics Workspace + Runtime System。

它不是单一的自然语言问数 Agent，而是一套从共享业务语义、分析能力孵化、能力治理，到 Runtime 产品化的完整工程体系。

当前项目主线是：

```text
shared
  ↓
mashang_workspace
  ↓
mashang_runtime_v2
  ↓
mashang_runtime（产品能力沉淀）
```

也就是说：

- `shared/` 提供共享业务算子与业务定义；
- `mashang_workspace/` 是日常工作的主阵地，负责分析、脚本开发、文档沉淀、Result Contract、Eval 与 Capability Registry；
- `mashang_runtime_v2/` 用于验证和产品化新的 Runtime 架构；
- `mashang_runtime/` 承载已经稳定、高频、口径清晰的产品能力。

---

# 快速开始

## 环境准备

推荐使用 Python 3.10+。

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

## 验证环境

执行：

```bash
make test
```

或：

```bash
make ci
```

如果能够正常运行，则说明项目环境基本可用。

---

## 最推荐的使用方式

### 日常工作：使用 Workspace

绝大多数情况下，应直接在：

```text
mashang_workspace/
```

中开展工作。

推荐让 OpenCode 在 Workspace 中完成：

- 业务分析；
- 数据探索；
- 编写分析脚本；
- 补充业务文档；
- 沉淀 Result Contract；
- 编写 Eval Case；
- 注册 Capability；
- 验证能力质量。

Workspace 是能力孵化与治理中心，也是项目的主要开发入口。

---

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

### 运行 Runtime V2 Demo

```bash
make runtime-v2-demo
```

或：

```bash
make runtime-v2-city-demo
```

用于验证 Runtime V2 的能力调度链路。

---

## 开发者工作流

推荐遵循以下工作模式：

```text
业务问题
  ↓
mashang_workspace
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
mashang_runtime
```

其中：

- Workspace 用于探索和沉淀能力；
- Runtime 用于承载已经成熟的产品能力；
- 不建议直接在 Runtime 中开发新业务逻辑。

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
make runtime-v2-audit
```

检查 Runtime V2 就绪状态。

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
mashang_workspace/runtime_scripts/
mashang_workspace/research_scripts/
mashang_workspace/docs/
mashang_workspace/eval/
```

---

### Runtime 开发者

重点关注：

```text
mashang_runtime_v2/
mashang_runtime/
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
mashang_runtime/
```

这里存放已经沉淀完成的产品能力。

---

## 典型开发流程

新增一个分析能力：

### Step 1

在：

```text
mashang_workspace/research_scripts/
```

完成业务验证。

### Step 2

封装为：

```text
mashang_workspace/runtime_scripts/
```

标准 Runtime Script。

### Step 3

输出标准 Result Contract。

### Step 4

补充 Eval Case。

### Step 5

注册到：

```text
mashang_workspace/registry/capability_registry.json
```

### Step 6

通过 Audit 与 Eval。

### Step 7

经过实际使用验证。

### Step 8

对于稳定、高频、口径清晰的能力：

```text
mashang_workspace
  ↓
mashang_runtime
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

# 1. Architecture Overview

当前项目采用四层架构：

```text
mashang-service/
├── shared/                 # 共享业务语义层
│   ├── operators/
│   └── schema/
│
├── mashang_workspace/      # 能力孵化与治理层（主工作区）
│   ├── runtime_scripts/
│   ├── research_scripts/
│   ├── utility_scripts/
│   ├── legacy_scripts/
│   ├── registry/
│   ├── eval/
│   ├── tests/
│   ├── docs/
│   └── utils/
│
├── mashang_runtime_v2/     # 新 Runtime 架构实验与产品化
│
├── mashang_runtime/        # 产品能力层
│
├── dataset/
├── main.py
├── feishu_bot.py
├── Makefile
├── pyproject.toml
└── README.md
```

---

# 2. Four-layer Design

## 2.1 Shared Layer

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
mashang_workspace
mashang_runtime
mashang_runtime_v2
```

原则：

```text
shared 只存放稳定业务原语。
新能力先进入 workspace，再决定是否沉淀到 shared。
```

---

## 2.2 Workspace Layer

目录：

```text
mashang_workspace/
```

这是项目最重要的工作区。

推荐日常所有分析工作都从这里开始。

负责：

- 能力孵化；
- 数据探索；
- Runtime Script 管理；
- Result Contract；
- Eval；
- Capability Registry；
- 文档沉淀；
- 能力治理。

OpenCode 的主要工作区域也应当是 Workspace。

---

## 2.3 Runtime V2 Layer

目录：

```text
mashang_runtime_v2/
```

用于验证新的 Runtime 架构。

原则：

```text
Runtime V2 不重新发明分析能力；
Runtime V2 优先消费 Workspace 中已经治理完成的能力；
Runtime V2 统一消费 Result Contract。
```

最小运行链路：

```text
user text
  ↓
context_parser
  ↓
capability_dispatcher
  ↓
workspace_script_adapter
  ↓
runtime_scripts
  ↓
Result Contract
  ↓
response_renderer
```

---

## 2.4 Runtime Layer

目录：

```text
mashang_runtime/
```

产品能力层。

这里不承担探索工作，而承担：

- 稳定能力沉淀；
- 高频能力复用；
- 产品接口输出；
- 飞书机器人能力；
- API 能力。

原则：

```text
Workspace 负责成长能力；
Runtime 负责承载成熟能力。
```

---

# 3. Capability Lifecycle

推荐生命周期：

```text
research_scripts
  ↓
runtime_scripts
  ↓
Result Contract
  ↓
Eval
  ↓
Capability Registry
  ↓
业务验证
  ↓
mashang_runtime
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
| runtime  | `runtime_scripts/`  | 稳定分析能力 | yes              | yes          |
| research | `research_scripts/` | 研究能力     | no               | no           |
| utility  | `utility_scripts/`  | 工具脚本     | no               | no           |
| legacy   | `legacy_scripts/`   | 历史脚本     | no               | no           |

原则：

```text
普通业务问题默认只调度 runtime_scripts。
research_scripts 必须显式调用。
```

---

# 5. Capability Registry

注册表：

```text
mashang_workspace/registry/capability_registry.json
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
mashang_workspace/docs/result_contract.md
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

# 8. Current Runtime V2 Status

当前支持能力：

```text
lock_by_model
lock_city_distribution
```

示例问题：

```text
昨天锁单数分车型
昨天 LS8 锁单城市分布
```

---

# 9. Project Roadmap

已完成：

```text
Phase 11：Promotion Gate & Capability Registry
Phase 12：Legacy Runtime Freeze & Runtime V2 Foundation
Phase 12.5：Legacy Runtime Packaging
Phase 12.6：Archive Cleanup
Phase 12.7：Shared Operators & Schema Extraction
Phase 12.8：Rename mashang_shared to shared
```

进行中：

```text
Phase 13：Runtime V2 Minimal Implementation
Phase 14：Runtime V2 Multi-turn & Response Quality
Phase 15：Feishu / API Product Output
```

长期目标：

```text
Workspace 持续成长能力
        ↓
Eval 与 Registry 治理
        ↓
Runtime 产品化沉淀
```

---

# 10. One-sentence Summary

```text
shared              # shared business semantics
mashang_workspace   # capability incubation and governance
mashang_runtime_v2  # runtime architecture evolution
mashang_runtime     # productized capabilities
```

核心原则：

```text
平时主要在 Workspace 中工作，
让 OpenCode 分析、写脚本、补文档、沉淀 Eval 和 Result Contract；

当能力经过验证、使用频繁且业务口径稳定后，
再回流到 Runtime，成为真正的产品能力。
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

## mashang_workspace

`mashang_workspace/` 是当前 Agent 工作区，负责：

- 分析探索（`research_scripts/`）
- 稳定分析脚本（`runtime_scripts/`）
- 工具脚本（`utility_scripts/`）
- 数据管道（DataOps）
- 测试（`tests/`）
- 评测（`eval/`）
- 文档沉淀（`docs/`）
- 输出产物（`outputs/`）

workspace **消费** `dataset/incoming/` 中的文件，但**不作为 Playwright 下载入口**。
所有通过 Playwright / 浏览器下载的文件，统一写入 `dataset/incoming/`。

---

## shared

`shared/` 是当前共享算子、Schema、Loader 的**唯一可信来源**。

```text
shared/
├── operators/     # 14 个 canonical 业务算子
├── schema/        # metric registry, business definitions
└── loaders/       # dataset loaders (passenger_insurance 等)
```

`shared/` 中的 operators 是 canonical 版本。
`mashang_runtime/operators/` 保留 legacy 副本，已不再作为活跃来源。

---

## mashang_runtime

`mashang_runtime/` 是 **legacy frozen runtime**。

- 不再作为当前 workspace 的 canonical source
- 不建议新增依赖
- operators 和 schema 的 canonical 版本已迁移到 `shared/`
- 未来考虑重命名为 `mashang_runtime.legacy/`

当前 workspace **没有**任何 import 指向 `mashang_runtime/`。

---

## outputs

输出产物分为三层：

| 路径 | 内容 | Git 策略 |
|------|------|----------|
| `outputs/assets/brand/` | 品牌资产（logo、签名） | ✅ 提交 |
| `outputs/reports/` | 正式渲染报告（HTML/PDF/DOCX） | 🟡 按需 |
| `outputs/submission/` | 正式申报材料 | 🟡 按需 |
| `mashang_workspace/outputs/reports/` | 分析报告 | 🟡 按需 |
| `mashang_workspace/outputs/tables/` | 结构化数据 | 🟡 考虑 gitignore |
| `mashang_workspace/outputs/charts/` | 可视化图表 | 🟡 考虑 gitignore |

原则：可复现产物（CSV/JSON/图表）建议不提交；展示资产（品牌 logo / 正式报告）按需提交。
