# mashang-service

`mashang-service` 是一个面向汽车业务数据分析的 AI-native Analytics Workspace + Runtime System。

它不是单一的自然语言问数 Agent，而是一套从共享业务语义、分析能力孵化、能力治理，到 Runtime 产品化的完整工程体系。

当前项目主线是：

```text
1. Semantic Foundation（dataset + shared）
  ↓
2. Base Capabilities（capabilities） +  3. Daily Business Analytics（mashang_workspace）
  ↓
4. Unified Research Runtime（mashang_runtime_v2）
  ↓
5. Research Applications（MIIT / auto_launch / nev_apeal / …）
```

也就是说：

- `shared/` + `dataset/` 提供共享业务语义、业务算子、业务定义与原始数据（Semantic Foundation）；
- `capabilities/` 提供领域无关基础能力（OCR / Search / Notify 等），与日常业务分析能力平级，供上层复用（Base Capabilities）；
- `mashang_workspace/` 是**日常业务分析工作区（Daily Business Analytics）**：负责分析、脚本开发、文档沉淀、Result Contract、Eval 与 Capability Registry，回答"今天要查什么/算什么"；
- `mashang_runtime_v2/` 是 **Unified Research Runtime**：一方面调用 workspace 的确定性业务分析能力，另一方面长期编排独立 Research Applications；
- MIIT / auto_launch / nev_apeal 是承载长期研究对象的 **Research Applications**（研究单元），有自己的状态、流程、contracts、gate 与产物。

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
   capabilities/                 mashang_workspace/
   OCR / Search / Notify         日常业务分析工具箱
   Browser / Parse / Render      research → runtime → eval
        │                             │
        └──────────────┬──────────────┘
                       ▼
4. Unified Research Runtime      mashang_runtime_v2
                       │
          ┌────────────┼────────────┬────────────┬───────
          ▼            ▼            ▼            ▼
5. Research Applications
        MIIT       auto_launch    nev_apeal   Project 4 ...
   （工信部车型申报研究） （上市与竞争动态研究） （新能源用户体验研究）
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
├── mashang_workspace/     # 3. Daily Business Analytics Workspace（日常业务分析工具箱）
│   ├── runtime_scripts/   #    高频确定业务分析，成熟后被 Runtime V2 调用
│   ├── research_scripts/
│   ├── utility_scripts/
│   ├── registry/
│   ├── eval/
│   ├── tests/
│   ├── docs/
│   └── utils/
│
├── mashang_runtime_v2/    # 4. Unified Research Runtime（编排层）
├── mashang_runtime/       #   legacy frozen runtime（已冻结，canonical 迁至 shared/）
│
├── research_apps/         # 5. Research Applications（研究单元归类层：只归类，不提供共享逻辑）
│   ├── MIIT/              #    Research Application：工信部车型与申报研究
│   ├── auto_launch/       #    Research Application：新车上市与竞争动态研究
│   └── nev_apeal/         #    Research Application：新能源用户体验研究
│
├── ocr/ 已迁移 → capabilities/ocr   （历史路径不再使用）
├── main.py
├── feishu_bot.py
├── Makefile
├── pyproject.toml
└── README.md
```

> 分层要点：`capabilities/`（Base Capabilities）与 `mashang_workspace/`（Daily Business Analytics）是两支平级的能力来源；
> `mashang_runtime_v2`（Unified Research Runtime）负责两类消费——调用 workspace 日常业务分析能力 + 长期编排 Research Applications。

## Research Applications（冻结定义）

`MIIT / auto_launch / nev_apeal`（及未来第 4、5 个项目）不是"Feature 子项目"，而是**独立研究型子项目（Research Applications / Research Programs）**：

- 解决的是一个**长期问题**，不是一次查询；
- 拥有**自己的状态、流程、研究对象、产物、阶段与演化历史**——有自己的 engine/state 流转、contracts、QA gate 与 artifacts；
- 是**持续存在的研究对象/研究程序**，可被 Runtime V2 长期驱动，而不只是一个脚本。

| Research Application | 研究对象 |
|----------------------|----------|
| `MIIT` | 工信部车型与申报研究 |
| `auto_launch` | 新车上市与竞争动态研究 |
| `nev_apeal` | 新能源用户体验研究 |
| `project_4 / project_5` | 未来项目（应符合上述准则再立项） |

`mashang_workspace/` 与它们**不是同一概念**：workspace 是**日常业务分析工作区**，回答"今天我要查什么、算什么"；Research Applications 回答"我要持续研究的一个长期问题"。当前 `nev_apeal` 是第一个成熟、已具备 engine/state/contracts/gate/artifacts 的 Research Application，作为迁入 Runtime V2 编排的优先候选。

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

## 2.2 Daily Business Analytics Workspace（mashang_workspace）

目录：

```text
mashang_workspace/
```

**日常业务分析工作区**：解决"今天我要查什么、算什么、分析什么"（锁单、库存、门店、车型、渠道等高频、相对确定的业务分析）。这是项目最重要的日常工作区，也是 OpenCode 的主要工作区域。

推荐日常所有分析工作都从这里开始。负责：

- 能力孵化（research_scripts → runtime_scripts）；
- 数据探索；
- Runtime Script 管理；
- Result Contract；
- Eval；
- Capability Registry；
- 文档沉淀；
- 能力治理。

成熟后的 `runtime_scripts` 会被 Unified Research Runtime（mashang_runtime_v2）以确定性方式调用。

---

## 2.3 Unified Research Runtime（mashang_runtime_v2）

目录：

```text
mashang_runtime_v2/
```

**统一研究 Runtime**。消费两类对象：

```text
mashang_runtime_v2
├── Tool / Capability invocation
│     └── mashang_workspace（确定性业务分析，Result Contract）
└── Research Application orchestration
      ├── MIIT / auto_launch / nev_apeal / project_4 / project_5
      └── 长期驱动、持续产出状态与成果的研究程序
```

原则：

```text
Runtime V2 不重新发明分析能力；
Runtime V2 调用 Workspace 中已经治理完成的能力，统一消费 Result Contract；
Runtime V2 长期编排独立 Research Applications。
```

当前已实现的最小运行链路（确定性分析一侧）：

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

Research Application 编排为演进目标，见 §1「Research Applications（冻结定义）」。

---

## 2.4 Legacy Runtime Layer（mashang_runtime，frozen）

目录：

```text
mashang_runtime/
```

Legacy / frozen 旧 Runtime（产品化沉淀层的历史形态，已冻结）。operators/schema 的 canonical 版本已迁移至 `shared/`，不再作为活跃开发目录；不作为新能力回流目标。

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

## source_capture / ocr

```text
source_capture/      # 抓取/归档原图
ocr/                 # （历史）→ 已迁移为 capabilities/ocr（Base Capability）
```

OCR 作为领域无关基础能力归位于：

```text
capabilities/ocr/    # Base Capability：截图 → 文字/markdown/表格（火山 OCR），缓存/QPS/retry
```

详见 `capabilities/README.md` 与 `capabilities/ocr/README.md`。

---

## shared

`shared/` 是当前共享算子、Schema、Loader 的**唯一可信来源**。

```text
shared/
├── operators/     # 14 个 canonical 业务算子
├── schema/        # metric registry, business definitions
└── loaders/       # dataset loaders (TP&MIX-ways 等)
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
