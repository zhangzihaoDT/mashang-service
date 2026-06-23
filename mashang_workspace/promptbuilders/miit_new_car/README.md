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

## 降级模式 / Degraded Mode

当批次状态为 **publicity**（公示）而非 official（正式发布），或主附件返回 404、product_list 为空（quality=empty）时，Prompt Pack 自动进入降级模式。

### 降级模式行为

| 模块 | 正常模式 | 降级模式 |
|------|----------|----------|
| 00_asset_check | 预期所有资产完整 | 输出 asset_status=partial/empty，标记 blocking_reason |
| 01_field_cleaning | 对 product_list records 做字段清洗 | 跳过（0 records），输出 skipped_empty_product_list |
| 02_target_brand_extract | 基于 product_list + extracted text | 仅基于 tax catalog / extracted text fallback，source_reliability 受限 |
| 03_product_signal_interpretation | 可输出完整车型判断，含 S/A/B/C | 仅输出"观察信号"，不允许 S 级判断，所有结论标记 low confidence |
| 04_brief_output | 标准简报 | 含"输入资产降级说明"章节，明确告知结论适用范围限制 |

### 降级模式使用限制

- 降级模式下只能做**有限信号提取**，不能输出完整车型判断。
- 所有结论必须注明输入来源限制（如"基于 tax catalog 数据，非完整产品清单"）。
- 降级模式不阻断分析，但会显著降低结论置信度。
- 建议在批次转为 **official** 后复跑完整流程。

## 边界验证案例

| 批次 | 状态 | 特点 | 验证意义 |
|------|------|------|----------|
| 第 407 批 | official | 主附件完整，product_list 1111 条/469 企/939 型号 | 正常路径验证 |
| 第 408 批 | publicity | 3 个附件 404，product_list empty (quality=empty)，仅 tax catalog 可用 | 降级路径验证 |

## 版本

- **Version**: v0.2
- **Source**: `docs/miit_promptbuilder_draft.md` v0.2 draft + 第 408 批 publicity 边界验证
- **Date**: 2026-06-23
- **Key changes**: 新增 degraded mode 全流程支持，asset_status 四态判断，empty product_list 处理路径，tax catalog fallback 限制，降级模式 S 级判断禁止规则，简报新增输入资产降级说明章节
