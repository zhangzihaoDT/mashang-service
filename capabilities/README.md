# Base Capabilities — 基础能力层

`capabilities/` 是 mashang-service 的 **Base Capabilities（基础能力）层**：一批**领域无关、跨模块可复用**的底层原语。

它们与业务层的关系遵循目标架构（命名冻结见根 README §1）：

```text
dataset/ + shared/          Semantic Foundation（数据与业务语义底座）
        │
        ├─────────────────────────────┐
        │                             │
        ▼                             ▼
capabilities/                 mashang_workspace/
Base Capabilities             Daily Business Analytics Workspace
OCR / Search / Notify         日常业务分析工具箱
Browser / Parse / Render      research → runtime → eval
        │                             │
        └──────────────┬──────────────┘
                       ▼
              mashang_runtime_v2
           Unified Research Runtime
                       │
          ┌────────────┼────────────┬────────────┬───────
          ▼            ▼            ▼            ▼
        MIIT       auto_launch    nev_apeal   Project 4 ...
            Research Applications
```

## 什么是 Base Capability

一条 Base Capability 是**不绑定任何汽车业务语义/数据/报告形态**的底层能力。判断标准：

- 接口是领域无关的原语（如 `image → text/markdown/tables`），而不是业务结论。
- 不依赖 `dataset/` 的业务表结构，不隐含车系/城市/口径。
- 可被多个上层（Daily Business Analytics workspace scripts、runtime_v2、Research Applications）通过同一份接口复用。
- 自带真实 provider + mock、自描述契约与测试，可离线验证。

`mashang_workspace/`（日常业务分析）与 Research Applications（MIIT / auto_launch / nev_apeal）是**消费者**；
Base Capabilities 是**被消费方**。

## Capability 规范（模板）

每个 `capabilities/<name>/` 目录应自描述，至少包含：

| 项 | 要求 |
|----|------|
| 定位 | 领域无关原语是什么（一句话） |
| namespace | 统一 `capabilities.<name>.*`，消费方从仓库根 import |
| 接口 | 稳定的函数/类接口 + 统一 CLI 入口 |
| providers | real provider + mock（离线可跑） |
| env 依赖 | 显式列出所需环境变量，缺省时给出明确错误 |
| outputs | 默认输出根位于仓库 `outputs/<name>/`（可 `--output-root` 覆盖） |
| tests | 随包 `tests/`，且已纳入 `make test` / `make ci` |
| 消费方记录 | 谁在用、用于什么 |
| not for | 明确「不负责什么」（领域解析属业务层） |

## 能力登记表

### Present（已归位）

| 能力 | 目录 | namespace | 说明 |
|------|------|-----------|------|
| OCR | `capabilities/ocr/` | `capabilities.ocr` | 图片 → 文字/markdown/表格（火山 general_ocr + document_parse），缓存 + QPS + retry |
| Notify | `capabilities/notify/` | `capabilities.notify` | 文本/交互卡片 → 渠道推送（飞书群 Webhook），重试 + dry-run + mock |
| Search | `capabilities/search/` | `capabilities.search` | 网页搜索原语（豆包 Global Search），重试 + 本地缓存 + multi-query + mock |

### Candidate（已存在但散落，待按需收敛）

| 候选能力 | 当前真实落点 | 收敛说明 |
|----------|-------------|----------|
| Browser / Capture | Playwright MCP（根 `opencode.jsonc`）+ `dataset/incoming/` + `source_capture/` | service 级接线能力，尚未包化 |
| Doc Parse | 部分在 `capabilities/ocr` document_parse；MIIT `eidc_doc_extract.py` 为领域内实现 | 通用文档→结构化契约待抽象 |
| Render | `.opencode/skills/official_document_render/` + `mashang_workspace/templates/` | 正式文档/报告渲染能力待收敛 |
| Feishu Bitable 写入 | `mashang_workspace/utility_scripts/skills_order_observation_daily.py`（tenant token + bitable REST） | Notify 之外的飞书 app 数据原语，另议 |

Candidate 不设迁移截止时间；**在出现真实复用需求时**按本 README 的规范逐项收敛，不做大爆炸迁移。

## 边界声明（本轮约定）

- **runtime_v2 编排边界**：`mashang_runtime_v2`（Unified Research Runtime）编排 = Base Capabilities + Daily Business Analytics（workspace 能力）→ 将 MIIT / auto_launch / nev_apeal 作为 **Research Applications** 长期驱动。本层只定义此边界，不在本轮改 runtime_v2 代码。
- **Research Applications 现状**：MIIT / auto_launch / nev_apeal 仍是独立研究项目（各自 CLI / Makefile / state / 数据目录），未接入 runtime_v2 编排；后续按编排化路径演进。
- **不要**在 capabilities/ 里放业务规则、业务脚本或领域解析逻辑——那属于 `mashang_workspace/` 或 Research Application 模块。
