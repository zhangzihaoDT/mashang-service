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
| 5 | Watchlist CSV | `configs/miit_new_car_watchlist.csv` | 文件存在，包含目标品牌关键词 |
| 6 | Promptbuilder 方法论 | `docs/miit_promptbuilder_draft.md` | 文件存在 |
| 7 | E2E Runbook | `docs/miit_e2e_runbook.md` | 文件存在 |
| 8 | Prompt Pack 模块 | `promptbuilders/miit_new_car/00~04.prompt.md` | 全部 5 个文件存在 |

## 检查规则

1. **evidence 文件**：读取 `evidence_layers` 下的三层（official_batch / official_attachment / official_product_list），确认每层的 `available` 是否为 `true`。记录 `product_list_count`、`enterprise_count`、`quality`。
2. **product_list 文件**：确认 `records` 数组不为空。记录总记录数。
3. **附件文本**：确认至少 1 个附件提取状态为 `success`。
4. **附件原文**：确认主附件（附件 1，道路机动车辆公告）的 `.txt` 文件大于 0 字节。
5. **缺失资产处理规则**：
   - 如果 evidence 或 product_list 不可用 → **阻断**，无法进入后续分析。
   - 如果附件文本抽取失败但 product_list 可用 → **部分可用**，标记为 `partial`，提取和分析基于 product_list 但标注 "未回看 extracted text"。
   - 如果 watchlist CSV 或方法论文档不存在 → **不阻断**，标记为 "缺少参考文件"。

## 输出格式

### 1. 逐项检查表

| 资产 | 路径 | 是否存在 | 用途 | 是否阻断后续分析 | 备注 |
|------|------|----------|------|-----------------|------|
| evidence JSON | `outputs/miit_new_car/evidence/batch_{N}_official_source_evidence.json` | 是/否 | 批次元信息、三层 evidence | 是（不可用则阻断） | 记录 product_list_count / quality |
| product_list JSON | `outputs/miit_new_car/product_list/batch_{N}_product_list.json` | 是/否 | 结构化产品清单 | 是（不可用则阻断） | 记录记录数 |
| 附件文本抽取 | `outputs/miit_new_car/extracted/batch_{N}_attachment_text.json` | 是/否 | 附件提取结果索引 | 否 | 记录 success/fail 数量 |
| 附件 1 原文 | `outputs/miit_new_car/extracted/text/batch_{N}/*.txt` | 是/否 | 道路机动车辆公告原文 | 否 | 记录文件大小 |
| Watchlist CSV | `configs/miit_new_car_watchlist.csv` | 是/否 | 关注品牌关键词 | 否 | 记录品牌列表 |
| Promptbuilder 方法论 | `docs/miit_promptbuilder_draft.md` | 是/否 | 分析模板参考 | 否 | — |
| E2E Runbook | `docs/miit_e2e_runbook.md` | 是/否 | 执行手册参考 | 否 | — |
| Prompt Pack | `promptbuilders/miit_new_car/*.prompt.md` | 是/否 | 可复用 Prompt 模块 | 否 | — |

### 2. 综合判断

| 判断项 | 结论 |
|--------|------|
| 是否可进入字段清洗（01） | 是 / 否 |
| 是否可进入目标品牌提取（02） | 是 / 否 |
| 是否可进入产品信号解释（03） | 是 / 否 |
| 是否可进入简报输出（04） | 是 / 否 |
| 是否存在高风险缺口 | 是 / 否 |
| 缺口说明 | 文本（如果有缺口，说明具体缺少哪些资产及其影响） |

## 使用示例（第 407 批参考）

运行本 Prompt 前，请粘贴 evidence JSON 内容到 `evidence` 字段位置，粘贴 product_list JSON 的 `summary` 信息到 `product_list` 位置。
