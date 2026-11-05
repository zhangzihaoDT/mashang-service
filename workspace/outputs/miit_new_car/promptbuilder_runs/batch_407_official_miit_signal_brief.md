# 第 407 批 MIIT 新车申报情报简报（Promptbuilder Dry Run）

> 生成日期: 2026-06-22
> 批次: 407 | 状态: official | 发布日期: 2026-06-12（来自 detail_url）
> 数据来源: `batch_407_official_source_evidence.json` + `batch_407_product_list.json` + `batch_407_watchlist_diff.json`
> 方法: Promptbuilder v0.1 draft — 仅验证输出格式，不代表最终业务结论

---

## 1. Dry Run 说明

- 本报告为 Promptbuilder 样例验证，**不代表最终业务结论**。
- 仅使用当前 workspace 已有 MIIT 输出文件，**未执行任何远程抓取**。
- MIIT 阶段只能判断**潜在信号**，不能等同于上市后的真实竞争威胁。
- 当前 product_list 的状态机解析存在字段偏移问题（品牌/企业名/产品名在部分行中列错位），因此本报告中的车型信息部分包含**人工清洗后的最佳推断**。
- 所有无法确认的信息均标记为 **待验证**。
- 深度参数（续航、电池、电机、尺寸）从 MIIT product_list 无法获取，全部标记 `unknown`。

---

## 2. 输入资产检查

| 输入文件 | 是否存在 | 用途 | 备注 |
|----------|----------|------|------|
| `evidence/batch_407_official_source_evidence.json` | ✅ | 批次元信息、evidence_layers、附件统计 | `product_list_count=1111, quality=usable` |
| `product_list/batch_407_product_list.json` | ✅ | 产品清单主表（企业/品牌/产品名/型号） | 1111 records, 469 enterprises, 939 models, quality=usable |
| `diff/batch_407_watchlist_diff.json` | ✅ | watchlist 增量 diff | 基于 legacy parsed 输出，matched=0（因 parsed 产品数据为空） |
| `extracted/text/batch_407/b43b6a0d1ffb47eba041adefa8541476.txt` | ✅ | 附件 1 道路机动车辆完整文本 | textutil 抽取的纯文本，含 `\x07` 分隔表格，约 400KB |
| `extracted/text/batch_407/9da5e8eab94f46e79e4a29196851c23d.txt` | ✅ | 附件 2 车船税目录文本 | 已排除，不进入 product_list |
| `extracted/text/batch_407/feab2b5562ef4ae0a857c85d32907c45.txt` | ✅ | 附件 3 购置税目录文本 | 已排除，不进入 product_list |
| `configs/miit_new_car_watchlist.csv` | ✅ | 14 个重点品牌 watchlist | 智己/理想/问界/小米/蔚来/小鹏/极氪/阿维塔/深蓝/零跑/腾势/方程豹/比亚迪/特斯拉 |
| `docs/miit_promptbuilder_draft.md` | ✅ | Promptbuilder 模板参考 | v0.1 draft |

---

## 3. 批次扫描结果

| 字段 | 结果 |
|------|------|
| batch_no | 407 |
| status | official（正式发布） |
| publish_date | 2026-06-12（详情页 URL 中包含 `art/2026/6/12/`） |
| product_record_count | 1111（来自 product_list） |
| enterprise_count | 469（来自 product_list summary） |
| product_model_count | 939（来自 product_list summary） |
| attachment_count | 4 个附件链接（3 个 DOC 已跳过存在 + 0 个新下载） |
| quality | usable（enterprise_count > 0, product_model_count > 0） |
| evidence_layers | batch=True, attachment=True, product_list=True |
| excluded_attachments | 2（vehicle_vessel_tax_catalog + purchase_tax_catalog） |
| network_retry_count | 0 |
| **key_observation** | 第 407 批正式公告产品清单质量可用（1111 条/469 企业/939 型号），但 watchlist diff 未命中（因 legacy parsed 层为空），实际 product_list 中包含智己/小鹏/比亚迪/零跑/阿维塔等关注品牌。 |

---

## 4. Watchlist 命中概览

基于 product_list 全文检索（watchlist diff 文件显示 matched=0，因其基于 legacy parsed 层，未覆盖 product_list 新解析结果）。

| 品牌/关键词 | 命中数量 | 代表车型/产品名（从 product_list 人工提取，字段可能有偏移） | 判断 |
|:---|---:|:---|:---|
| 比亚迪 | 8 | 插电式混合动力多用途乘用车 BYD6510/BYD6520；纯电动客车 BYD6113；纯电动栏板式货车 | 常规申报 |
| 智己 | 3 | **插电式增程混合动力运动型乘用车 CSA6492**（关键信号） | **S 级关注** |
| 小鹏 | 2 | 含插电式增程混合动力多用途乘用车（品牌匹配） | **S 级关注** |
| 问界/赛力斯 | 2 | 插电式增程混合动力多用途乘用车（品牌匹配） | A 级关注 |
| 零跑 | 2 | 纯电动多用途乘用车（注：字段偏移，名称待确认） | A 级关注 |
| 理想 | 1 | 北京理想汽车有限公司（字段偏移严重） | 待确认具体产品 |
| 阿维塔 | 1 | 阿维塔（AVATR）牌（字段偏移严重） | 待确认具体产品 |
| 蔚来 | 0 | 未在当前 product_list 中发现 | — |
| 小米 | 0 | 未在当前 product_list 中发现 | — |
| 极氪 | 0 | 未在当前 product_list 中发现 | — |
| 特斯拉 | 0 | 未在当前 product_list 中发现 | — |

**注意**：当前 product_list 状态机解析存在字段偏移问题，部分行的 `enterprise_name`、`brand`、`product_name`、`product_model` 列错位。上表中的"代表车型"含义为"在这些字段中匹配到了品牌关键词"，不代表字段内容完全正确。实际产品信息需对照原始 extracted text 确认。

---

## 5. 重点车型 S/A/B/C 分级

基于 product_list 中可识别的 watchlist 品牌记录（受字段偏移影响，部分等级标记为**待验证**）。

| 优先级 | 企业（最佳猜测） | 品牌 | 产品名称（最佳猜测） | 型号/前缀 | 分级理由 | 置信度 | 待验证事项 |
|:------|:---|:---|:---|:---|---:|:---|:---|
| **S** | 上海汽车集团股份有限公司 | **智己** | 插电式增程混合动力运动型乘用车 | CSA6492 | 智己新增增程版本，战略补齐产品线 | high | 具体上市时间、价格 |
| **S** | 赛力斯汽车（湖北）有限公司 | **问界** | 插电式增程混合动力多用途乘用车 | 未确认 | 问界品牌新增增程车型 | medium | 具体型号前缀需对照原文 |
| **S** | 肇庆小鹏新能源投资有限公司 | **小鹏** | 含插电式增程混合动力多用途乘用车 | 未确认 | 小鹏品牌有增程版本信号 | low（字段偏移严重） | 需对照 extracted text 确认具体产品 |
| **A** | 比亚迪汽车工业有限公司 | **比亚迪** | 插电式混合动力多用途乘用车 | BYD6510/BYD6520 | 比亚迪新增 PHEV MPV 版本 | medium | 是否为全新车型或改款 |
| **A** | 零跑汽车有限公司 | **零跑** | 纯电动多用途乘用车 | 未确认 | 零跑新增纯电动 SUV/MPV | low（字段偏移） | 具体产品名称和型号 |
| **B** | 比亚迪汽车工业有限公司 | **比亚迪** | 纯电动客车 | BYD6113 | 常规客车申报 | high | — |
| **B** | 比亚迪汽车工业有限公司 | **比亚迪** | 纯电动栏板式货车 | 未确认 | 常规货车申报 | medium | — |
| **C** | 其他 | — | — | — | 非关注品牌 or 非乘用车 or 低识别度 | — | — |

---

## 6. 车型信息抽取样例

选择 5 个重点车型，按 Promptbuilder 输出格式。

| 企业 | 品牌 | 产品名称 | 产品型号 | 型号前缀 | 可确认事实 | unknown_fields | confidence |
|:---|:---|:---|:---|---:|:---|:---|---:|
| 上海汽车集团股份有限公司 | 智己 | 插电式增程混合动力运动型乘用车 | CSA6492 (含 LFSHEV3/LFSHEV4) | CSA6492 | 智己品牌、插电式增程、运动型乘用车、型号前缀 CSA6492 | energy_type, vehicle_type, battery, motor, range, size | high（智己记录字段对齐较好） |
| 赛力斯汽车（湖北）有限公司 | 问界 | 插电式增程混合动力多用途乘用车 | 未确认 | 未确认 | 问界/赛力斯品牌、增程混动、多用途乘用车 | product_model, model_prefix, battery, motor, range, size | medium（品牌和能源形式可确认） |
| 比亚迪汽车工业有限公司 | 比亚迪 | 插电式混合动力多用途乘用车 | BYD6510/BYD6520 | BYD65 | 比亚迪品牌、插电混动、多用途乘用车 | specific_model, battery, motor, range, size | high（字段对齐较好） |
| 比亚迪汽车工业有限公司 | 比亚迪 | 纯电动客车 | BYD6113 | BYD61 | 比亚迪品牌、纯电动、客车 | battery, motor, range, size | high |
| 零跑汽车有限公司 | 零跑 | 纯电动多用途乘用车（最佳猜测） | 未确认 | 未确认 | 零跑品牌、纯电动 | product_model, model_prefix, battery, motor, range, size | low（字段偏移，产品名存疑） |

**所有字段说明**：当前 product_list 工程输出**不解析**续航、电池容量、电机功率、尺寸等深度参数。所有 `unknown_fields` 均为待后续版本或非 MIIT 来源补充。

---

## 7. 新旧版本差异初步判断

**限制说明**：
- `diff/batch_407_watchlist_diff.json` 基于 legacy `parsed/` 层输出（matched=0），未覆盖新 `product_list/` 数据。
- 缺少第 406 批的 `product_list` 数据，无法做严格的两批 product_list 逐行对比。
- 以下判断基于 product_list 中 watchlist 品牌的型号前缀出现情况，与其他批次做**弱对比**（参考 evidence 中 `previous_batch=406`）。

| 差异类型 | 企业 | 品牌 | 产品名称 | 依据 | 置信度 | 待验证事项 |
|:---|:---|:---|:---|:---|---:|:---|
| **new_variant** | 上海汽车集团 | 智己 | 插电式增程混合动力运动型乘用车 CSA6492 | 智己此前 L6/LS6 只有 BEV 版本，本次 CSA6492 前缀下出现增程版本 | high | 确认 CSA6492 是否为已有纯电平台扩展 |
| **new_variant** | 比亚迪 | 比亚迪 | 插电式混合动力多用途乘用车 BYD6510/BYD6520 | BYD65 前缀在往批已有纯电版本，本次新增插混版本 | medium | 需往批数据确认 |
| **uncertain** | 肇庆小鹏 | 小鹏 | 插电式增程混合动力多用途乘用车 | 字段偏移严重，无法确认具体型号 | low | 需对照 extracted text |
| **uncertain** | 赛力斯 | 问界 | 插电式增程混合动力多用途乘用车 | 字段偏移，无法确认型号 | low | 需对照 extracted text |

---

## 8. 产品意图解读

### 车型：智己 L6/LS6 增程版（CSA6492LFSHEV3 / LFSHEV4）

| 层级 | 内容 |
|:---|:---|
| **事实** | 第 407 批正式公告中，上海汽车集团股份有限公司以"智己"品牌申报了"插电式增程混合动力运动型乘用车"，型号前缀 CSA6492，包含 LFSHEV3 和 LFSHEV4 两个版本。两个版本的铭牌信息（质量、电池等）在附件 1 文本中可确认不同。 |
| **合理推断** | 1) 智己正在从纯电（BEV-only）向增程（EREV）扩展产品线。2) 型号前缀 CSA6492 延续了已有纯电版本（CSA6492LBEVK/LBEVG/LBEVH）的平台编号，推断为同一平台的增程衍生版本。3) 两个版本推断为不同电池容量/续航配置。 |
| **待验证假设** | 1) 上市时间（预计 Q3-Q4 2026）。2) 定价（预计 25-35 万区间，待验证）。3) 具体续航参数（非 MIIT 可获取）。4) 是否同时开发增程 + 纯电双线销售。5) 与 LS6 的品牌定位关系（智己 vs 飞凡 vs 荣威）。 |

### 车型：比亚迪海狮 08 PHEV 版（BYD6510BN6HEV1 / BYD6510BN6HEV2）

| 层级 | 内容 |
|:---|:---|
| **事实** | 比亚迪申报了 BYD6510 和 BYD6520 两个型号前缀的"插电式混合动力多用途乘用车"。从 evidence 中 attachment 2/3 为税收目录判断，该车型可能同时进入了减免车船税/购置税目录。 |
| **合理推断** | BYD6510 在往批纯电版本（BYD6510BNBEV1-3）基础上新增插混版本，推断为海狮 08 的 DM-i/DM-p 版本，覆盖 BEV+PHEV 双线。 |
| **待验证假设** | 1) 是否为海狮 08 系列扩展。2) 纯电续航里程。3) 与腾势/方程豹的产品线边界。 |

### 车型：问界增程版（赛力斯汽车湖北有限公司）

| 层级 | 内容 |
|:---|:---|
| **事实** | product_list 中识别到"赛力斯汽车（湖北）有限公司"和"插电式增程混合动力多用途乘用车"、"问界牌"等字段。字段有偏移，需对照 extracted text 确认具体型号。 |
| **合理推断** | 问界品牌持续强化增程产品线，第 407 批可能涉及 M7/M9 的改款或新配置版本。 |
| **待验证假设** | 1) 具体车型（M8? M7 改款?）。2) 型号前缀。3) 与现有 M5/M7/M9 的关系。 |

---

## 9. 竞品映射初步判断

围绕我方重点车型（LS6、LS8）进行竞品映射。

| 申报车型 | 可能相关市场 | 可能相关竞品/我方车型 | 映射理由 | 置信度 | 待验证事项 |
|:---|:---|:---|:---|---:|:---|
| 智己插电式增程运动型乘用车 CSA6492 | 中大型增程 SUV（25-35 万） | **LS6**（同集团定位接近） | 同为上汽集团，智己品牌定位高于 LS6/LS8；增程版本直接补充 BEV 短板 | medium | LS6 为飞凡/荣威品牌 vs 智己品牌定位差异 |
| 问界/赛力斯增程多用途乘用车 | 中大型增程 SUV（25-40 万） | **LS8**（直接竞品） | 问界品牌在增程 SUV 市场已有 M7/M9；本批次新增版本可能延续此定位 | medium | 未确认具体是 M7/M9 的改款还是全新车型 |
| 比亚迪 PHEV 多用途乘用车 BYD6510 | 中型 PHEV SUV（20-30 万） | LS6（间接竞品） | 比亚迪 PHEV 主力价格带低于 LS6，但品牌声量高 | medium | 需确认具体车型和定价 |
| 小鹏增程多用途乘用车 | 中大型增程 SUV（25-35 万） | **LS6 / LS8**（直接竞品） | 小鹏品牌直接对标蔚来/理想/智己 | low（字段偏移严重） | 需确认具体产品 |

---

## 10. 威胁等级判断

**前置声明**：本轮评分为低置信度 dry run，仅用于验证 Promptbuilder 输出格式。由于当前 product_list 缺少深度参数（续航、价格、上市时间），且部分品牌字段偏移严重，评分基于品牌 + 产品类型 + 企业信息的弱推断。

| 车型 | threat_score | threat_level | reason | evidence | uncertainty | follow_up_needed |
|:---|---:|:---|:---|:---|:---|---:|
| 智己增程版 CSA6492 | 68 | ⚠️ 中高优先级关注 | 智己品牌、增程 SUV、CSA6492 平台已验证；品牌声量高；与 LS6/LS8 市场重叠大 | product_list 记录字段对齐、evidence 完整 | medium（上市时间和价格未确认） | 是 — 跟踪上市节奏和配置发布 |
| 问界/赛力斯增程版 | 55 | 👀 常规跟踪 | 问界品牌在增程 SUV 市场已有份额；但具体车型未确认 | product_list 字段偏移 | high（具体型号未确认） | 是 — 获取具体型号后再升级 |
| 比亚迪 PHEV BYD6510 | 45 | 👀 常规跟踪 | 比亚迪 PHEV 产品线成熟，但 BYD65 系列定位中端 | evidence 中有税收目录关联 | medium | 否 — 常规跟踪 |
| 小鹏增程版 | 30 | 🔍 低优先级观察 | 字段偏移严重，无法确认具体产品 | product_list 字段严重偏移 | high | 待字段清洗后再评估 |

---

## 11. 本批次一句话结论

| 版本 | 一句话结论 |
|:---|:---|
| **管理层版** | 第 407 批正式公告中，智己新增增程版本为战略级信号，建议持续关注；问界、比亚迪、小鹏有常规或增量申报，暂不构成紧急预警。 |
| **产品规划版** | 智己正在从纯电向增程扩展产品线，CSA6492 平台新增增程版本（LFSHEV3/4），推断为 L6/LS6 的增程衍生版，补齐纯电短板。 |
| **情报跟踪版** | 后续应重点跟踪：智己增程版上市节奏、问界新增具体车型、小鹏增程版产品形态；建议提取 extracted text 清洗字段偏移问题。 |

---

## 12. 后续 7/30/90 天追踪清单

| 时间窗口 | 追踪事项 | 触发信号 | 负责人/使用场景 |
|:---|:---|:---|:---|
| 7 天 | 对 product_list 中字段偏移的 watchlist 品牌记录，对照 extracted text 进行人工清洗 | 字段偏移导致品牌/产品名/型号错位 | Promptbuilder 数据质量 |
| 7 天 | 提取智己 CSA6492 增程版的完整 extracted text 片段 | 用于确认增程版本数量和配置 | 车型信息抽取 |
| 7 天 | 检查第 408 批是否有智己/问界/小鹏新增信号 | 下一批更新时间: 约 7 月 10 日 | 批次扫描 |
| 30 天 | 跟踪智己增程版是否进入工信部能耗目录 | 能耗公布 → 续航和能耗可确认 | 产品规划团队 |
| 30 天 | 跟踪问界新增车型的媒体信息 | 媒体曝光 → 具体车型确认 | 竞品分析师 |
| 90 天 | 智己增程版是否开启预售/亮相车展 | 预售 → 价格和配置确认 | 定价/产品团队 |
| 90 天 | 小鹏增程版是否进入下一批公告 | 下一批出现完整字段 → 确认产品形态 | 竞品分析师 |

---

## 13. Promptbuilder 问题清单

本次 dry run 暴露出的问题：

| 问题 | 类型 | 影响 | 建议 |
|:---|:---|:---|:---|
| **product_list 字段偏移** | 输入字段不足 / 数据质量问题 | watchlist 准确性降低；品牌/产品名/型号错位 | 在 Promptbuilder 层增加"字段清洗"步骤：先对每行记录验证 enterprise_name 是否以"公司/厂/集团"结尾，不符合则认为字段偏移 |
| **watchlist diff 未覆盖 product_list** | 输入字段不足 | diff 输出 matched=0，无法直接用于 Promptbuilder | 短期内可通过 product_list 全文检索替代 diff；长期 fix `diff_watchlist.py` 使用 product_list 数据源 |
| **缺少上一批 product_list** | 输入字段不足 | 无法做严格新旧版本对比 | 建议为每批 product_list 保留快照；Promptbuilder 层可先做"品牌内型号前缀变化"的弱对比 |
| **深度参数全部未知** | 能力边界 | 威胁等级评分缺乏关键输入（续航、价格） | 明确在报告中标注；后续可通过能耗目录或税收目录补充 |
| **Prompt 模板缺少字段清洗步骤** | Prompt 模板不清晰 | 人工校验工作量大 | 建议在 Promptbuilder draft 中新增"数据准备"步骤 |
| **低置信度汽车企业数据** | 需要人工校验 | 部分记录仅含非乘用车（卡车/客车/摩托车） | 建议 Promptbuilder 先过滤 vehicle_type=乘用车 |

---

## 14. 下一步建议

| 优先级 | 动作 | 产出 | 备注 |
|:------|:---|:---|:---|
| 1 | **在 Promptbuilder draft 中补充"数据准备与字段清洗"步骤** | 修复第 13 节中暴露的字段偏移问题 | 不改工程代码 |
| 2 | **用 cleanest watchlist 品牌（智己/比亚迪）跑一次完整 8 步 Promptbuilder 流程** | 验证提示词的有效性 | 字段偏移最轻的品牌 |
| 3 | **创建 `outputs/miit_new_car/promptbuilder_runs/` 目录索引 README** | 标记 dry run 结果和后续计划 | 轻量文档 |
| 4 | **暂缓深度参数解析工程化** | 不投入 DOC 结构化工程 | 如 Promptbuilder 验证需要续航等参数，优先从税收目录 / 能耗目录补充 |
| 5 | **暂缓 `diff_watchlist.py` 改造** | 不改工程代码 | Promptbuilder 层可先用 product_list 全文检索替代 |

---

*本报告由 Promptbuilder v0.1 draft 生成，仅用于验证输出格式。所有"待验证"标记的事项均需人工确认后方可用于业务决策。*
