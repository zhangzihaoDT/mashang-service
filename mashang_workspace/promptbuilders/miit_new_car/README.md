# MIIT New Car Promptbuilder Pack

## 定位

| 目录 / 文件 | 定位 |
|-------------|------|
| `research_scripts/miit_new_car/` | 官方信息获取与结构化（工程层） |
| `docs/miit_promptbuilder_draft.md` | 方法论母版（Prompt 设计和迭代记录） |
| `docs/miit_e2e_runbook.md` | 端到端执行手册（操作指引） |
| `promptbuilders/miit_new_car/` | **可复用 Prompt 模块**（本 Pack） |
| `outputs/miit_new_car/promptbuilder_runs/` | 业务解释结果沉淀区（curated business outputs） |

## 推荐使用顺序

```
1. 00_asset_check.prompt.md          输入资产完整性检查
2. 01_field_cleaning.prompt.md       字段可信度校验与清洗
3. 02_target_brand_extract.prompt.md  目标品牌信息提取
4. 03_product_signal_interpretation.prompt.md  产品信号业务解释
5. 04_brief_output.prompt.md         业务情报简报输出
```

## 适用输入

| 输入 | 来源 | 用于哪个 Prompt |
|------|------|-----------------|
| `evidence/batch_{N}_official_source_evidence.json` | `make miit-fetch-batch` | 00, 02, 04 |
| `product_list/batch_{N}_product_list.json` | `make miit-fetch-batch` | 00, 01, 02, 03, 04 |
| `extracted/text/batch_{N}/*.txt` | `make miit-extract-text` | 01, 02 |
| `extracted/batch_{N}_attachment_text.json` | `make miit-extract-text` | 00, 02 |
| `configs/miit_new_car_watchlist.csv` | 项目配置 | 02 |
| `docs/miit_promptbuilder_draft.md` | 项目文档 | 全流程参考 |
| `docs/miit_e2e_runbook.md` | 项目文档 | 全流程参考 |

## 输出文件夹说明

| 路径 | 内容 | 是否可提交 |
|------|------|-----------|
| `outputs/miit_new_car/raw/` | 附件 DOC 原始文件 | 不提交（runtime） |
| `outputs/miit_new_car/parsed/` | 附件级结构化记录 | 不提交（runtime） |
| `outputs/miit_new_car/diff/` | Watchlist 增量 diff | 不提交（runtime） |
| `outputs/miit_new_car/evidence/` | Evidence 分层 JSON | 不提交（runtime） |
| `outputs/miit_new_car/state/` | 最新批次状态缓存 | 不提交（runtime） |
| `outputs/miit_new_car/extracted/` | 附件文本抽取 JSON / 纯文本 | 不提交（runtime） |
| `outputs/miit_new_car/product_list/` | 结构化产品清单 | 不提交（runtime） |
| `outputs/miit_new_car/diagnostics/` | 附件可用性诊断 | 不提交（runtime） |
| `outputs/miit_new_car/discovery/` | 批次发现缓存 | 不提交（runtime） |
| `outputs/miit_new_car/promptbuilder_runs/` | **业务简报（curated markdown）** | **可提交** |

## 使用方式

每个 `.prompt.md` 文件可独立复制到 OpenCode / ChatGPT / DeepSeek 的对话中。将 `{batch_N}` 替换为实际批次号，将 `{target_brands}` 替换为目标品牌列表，将对应输入文件的 JSON / 文本内容粘贴到 Prompt 中的指定位置。

## 版本

- **Version**: v0.1
- **Source**: `docs/miit_promptbuilder_draft.md` v0.2 draft
- **Date**: 2026-06-23
