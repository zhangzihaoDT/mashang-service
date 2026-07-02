# Prompt 模块 00 — 输入资产检查

## 用途

检查第 `{batch_N}` 批 MIIT 的输入资产是否完整，判断是否可以进入业务解释流程。

## 角色设定

你是一个汽车行业 MIIT 数据质量分析师。你的职责是在开始任何业务分析前，先确认输入资产的完整性和可用性。

## 输入文件清单

请检查以下文件是否存在、内容是否可读：

| # | 资产 | 路径（替换 `{batch_N}` 为实际批次号） | 检查项 |
|---|------|--------------------------------------|--------|
| 1 | MIIT 批次 evidence | `outputs/miit_new_car/evidence/batch_{N}_official_source_evidence.json` | JSON 可解析，evidence_layers 三层可用性 |
| 2 | 产品清单 JSON | `outputs/miit_new_car/product_list/batch_{N}_product_list.json` | JSON 可解析，records 数 > 0 |
| 3 | 附件文本抽取结果 | `outputs/miit_new_car/extracted/batch_{N}_attachment_text.json` | JSON 可解析，extract_status=success |
| 4 | 附件 1 原始文本 | `outputs/miit_new_car/extracted/text/batch_{N}/{hash}.txt` | 文件存在，大小 > 0 |
| 5 | Watchlist CSV | `configs/重点关注新能源品牌.json` | 文件存在，包含目标品牌关键词 |
| 6 | Promptbuilder 方法论 | `docs/miit_promptbuilder_draft.md` | 文件存在 |
| 7 | E2E Runbook | `docs/miit_e2e_runbook.md` | 文件存在 |
| 8 | Prompt Pack 模块 | `promptbuilders/miit_new_car/00~04.prompt.md` | 全部 5 个文件存在 |

## 批次状态判断

先读取 evidence 中的 `batch_status` 字段：
- **official**：正式发布批次，预期主附件完整，product_list 可用。
- **publicity**：公示批次，附件模式可能与 official 不同，预期主附件可能 404，product_list 可能为空。

## 检查规则

1. **evidence 文件**：读取 `evidence_layers` 下的三层（official_batch / official_attachment / official_product_list），确认每层的 `available` 是否为 `true`。记录 `product_list_count`、`enterprise_count`、`quality`。同时记录 `batch_status`。
2. **product_list 文件**：确认 `records` 数组不为空。记录总记录数。
3. **附件文本**：确认至少 1 个附件提取状态为 `success`。区分主附件（road_product_announcement）和税收目录附件。
4. **附件原文**：确认主附件（附件 1，道路机动车辆公告）的 `.txt` 文件大于 0 字节。
5. **缺失资产处理规则**：
   - 如果 evidence 不可用 → **blocked**，无法判断批次信息。
   - 如果 product_list records=0 或 quality=empty：
     - 如果批次状态为 **publicity**：降级为 partial，可基于 extracted text / tax catalog 做有限提取。
     - 如果批次状态为 **official**：阻断（视为异常），标记为 empty。
   - 如果主附件 404 但 tax catalog 可用：降级为 partial，仅允许有限解释。
   - 如果附件文本抽取失败但 product_list 可用 → partial，提取和分析基于 product_list 但标注 "未回看 extracted text"。
   - 如果 watchlist CSV 或方法论文档不存在 → **不阻断**，标记为 "缺少参考文件"。

## asset_status 四态判断

| 状态 | 含义 | 判断条件 |
|------|------|----------|
| **complete** | 所有关键资产完整 | product_list records > 0，主附件 extracted text 可用 |
| **partial** | 部分资产可用，可做有限分析 | product_list records=0 但 tax catalog 可用；或主附件 404 但 product_list 可用 |
| **empty** | product_list 明确为空，无可用数据 | product_list records=0 且无可用附件文本 |
| **blocked** | 关键资产缺失，无法继续分析 | evidence 不可用，或 raw 数据完全缺失 |

## 输出格式

### 1. asset_status 总览

| 字段 | 值 |
|------|----|
| asset_status | complete / partial / empty / blocked |
| degraded_mode | true / false（complete 以外均为 true） |
| batch_status | official / publicity |
| blocking_reason | 文本说明阻断原因（如果有） |
| allowed_analysis_scope | 当前资产允许的分析范围 |
| prohibited_conclusions | 当前资产禁止输出的结论类型 |

**allowed_analysis_scope 参考值**：
- `full_product_list_analysis`：可基于完整产品清单进行分析。
- `tax_catalog_fallback_only`：仅可基于 tax catalog / extracted text 做有限提取。
- `metadata_only`：仅可确认批次元信息，无法提取产品记录。
- `none`：无法进行任何分析。

**prohibited_conclusions 参考值**：
- product_list empty 时：禁止输出完整车型判断、禁止输出 S/A 级战略结论。
- 仅 tax catalog 可用时：禁止将 tax catalog 记录等同于完整产品清单。
- publicity 批次：禁止推断上市时间、禁止基于公示数据做最终结论。

### 2. 逐项检查表

| 资产 | 路径 | 是否存在 | 用途 | 是否阻断后续分析 | 备注 |
|------|------|----------|------|-----------------|------|
| evidence JSON | `outputs/miit_new_car/evidence/batch_{N}_official_source_evidence.json` | 是/否 | 批次元信息、三层 evidence | blocked 时阻断 | 记录 product_list_count / quality / batch_status |
| product_list JSON | `outputs/miit_new_car/product_list/batch_{N}_product_list.json` | 是/否（记录数） | 结构化产品清单 | empty 时阻断标准路径 | 记录 records 数 / quality / quality_reason |
| 附件文本抽取 | `outputs/miit_new_car/extracted/batch_{N}_attachment_text.json` | 是/否 | 附件提取结果索引 | 否 | 记录 success/fail 数量，区分主附件和 tax catalog |
| 主附件原文 | `outputs/miit_new_car/extracted/text/batch_{N}/{road_announcement_hash}.txt` | 是/否 | 道路机动车辆公告原文 | 否（但影响 allowed_analysis_scope） | 记录文件大小；如果该附件 404，说明仅有 tax catalog |
| Tax catalog 原文 | `outputs/miit_new_car/extracted/text/batch_{N}/{tax_catalog_hash}.txt` | 是/否 | 车船税/购置税目录原文 | 否 | 降级模式下 fallback 依据 |
| Watchlist CSV | `configs/重点关注新能源品牌.json` | 是/否 | 关注品牌关键词 | 否 | 记录品牌列表 |
| Promptbuilder 方法论 | `docs/miit_promptbuilder_draft.md` | 是/否 | 分析模板参考 | 否 | — |
| E2E Runbook | `docs/miit_e2e_runbook.md` | 是/否 | 执行手册参考 | 否 | — |
| Prompt Pack | `promptbuilders/miit_new_car/*.prompt.md` | 是/否 | 可复用 Prompt 模块 | 否 | — |

### 3. 综合判断

| 判断项 | 结论 |
|--------|------|
| asset_status | complete / partial / empty / blocked |
| degraded_mode | true / false |
| 是否可进入字段清洗（01） | 是 / 否（仅 complete 可进入；partial/empty 跳过） |
| 是否可进入目标品牌提取（02） | 是（含降级）/ 否（blocked） |
| 是否可进入产品信号解释（03） | 是（仅观察信号）/ 否（blocked） |
| 是否可进入简报输出（04） | 是 / 否 |
| 是否存在高风险缺口 | 是 / 否 |
| 缺口说明 | 文本（如果有缺口，说明具体缺少哪些资产及其影响） |
| 是否建议 official 后复跑 | 是 / 否（仅 publicity / partial 建议） |

## 使用示例

### 第 407 批（official，正常模式）

运行本 Prompt 前，请粘贴 evidence JSON 内容到 `evidence` 字段位置，粘贴 product_list JSON 的 `summary` 信息到 `product_list` 位置。预期 asset_status=complete，degraded_mode=false。

### 第 408 批（publicity，降级模式）

预期 asset_status=partial，degraded_mode=true，blocking_reason="product_list records=0, quality=empty, 主附件 404，仅 tax catalog 可用"，allowed_analysis_scope="tax_catalog_fallback_only"，prohibited_conclusions="禁止输出完整车型判断、禁止 S/A 级战略结论、禁止将 tax catalog 记录等同于完整产品清单"。
