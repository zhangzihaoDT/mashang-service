# MIIT 新车申报情报 Promptbuilder 草案

> Version: v0.2 draft
> Source: miit_module_audit_v0.3.3.md + batch_407_official_miit_signal_brief.md
> Scope: Promptbuilder only
> Code changes: none
>
> v0.2 修订基于第 407 批 official Promptbuilder Dry Run 结果，重点补充输入字段清洗、watchlist fallback 检索、字段置信度校验和 dry run 经验。

---

## 1. 项目定位

**当前阶段判断**：

- MIIT 工程层已完成：批次发现、详情页/附件抓取、DOC/DOCX 文本抽取、产品清单解析（1111 条/469 企业/939 型号）、watchlist diff、evidence 分层输出。
- 第 407 批已验证全链路 quality=usable，第 408 批公示可正常发现。
- 当前**不优先继续工程化**。深度参数解析、税收目录结构化、自动推送等属于 V0.4+ 范围，应在 Promptbuilder 验证业务价值后再决定工程投入。
- 下一阶段重点是建立**业务解释层**——把工程输出转化为产品规划、竞品预警和上市节奏判断。

**Promptbuilder 目标**：将工信部新车申报信息转化为可消费的业务情报，通过 prompt 链路完成从数据到洞察的最后一公里。

---

## 2. 当前可用输入资产

| 资产 | 路径模式 | 内容 | 适合 Prompt 模块 | 是否需人工校验 |
|------|----------|------|-----------------|---------------|
| discovery cache | `outputs/miit_new_car/discovery/discovered_batches.json` | 批次号、状态、发布日期、detail_url | 批次扫描 | 不需要 |
| 详情页 HTML | `outputs/miit_new_car/raw/batch_{N}/detail.html` | 附件标题、链接、公示时间 | 批次扫描、附件诊断 | 可选 |
| 附件状态 | `outputs/miit_new_car/raw/batch_{N}/attachment_status.json` | 每个附件下载状态、HTTP 状态 | 批次扫描 | 可选 |
| 抽取文本 | `outputs/miit_new_car/extracted/text/batch_{N}/*.txt` | 附件 1 道路机动车辆完整文本（\x07 分隔表格） | 车型信息抽取、深度参数 | 需要（解析完整性） |
| 产品清单 | `outputs/miit_new_car/product_list/batch_{N}_product_list.json` | enterprise_name, brand, product_name, product_model, quality | 重点车型筛选、差异对比、竞品映射 | 需要（型号前缀可能 incomplete） |
| watchlist diff | `outputs/miit_new_car/diff/batch_{N}_watchlist_diff.json` | watchlist 品牌命中、新增/匹配产品 | 竞品映射、威胁判断 | 需要 |
| official evidence | `outputs/miit_new_car/evidence/batch_{N}_official_source_evidence.json` | evidence_layers（三层）、watchlist_hits、attachment_summary | 全模块入口 | 不需要 |
| watchlist CSV | `configs/重点关注新能源品牌.json` | 14 个品牌 + 关键词 | 竞品映射 | 不需要（可扩展） |

---

## 3. 输入清洗与字段可信度校验

**为什么需要字段清洗**：
- product_list 虽然总体可用，但部分记录存在 enterprise_name / brand / product_name / product_model 字段错位（第 407 批 dry run 中发现小鹏/问界/零跑等多条记录的字段偏移）。
- Promptbuilder 不应无条件信任结构化字段，每次分析前应先执行字段可信度检查。
- 对字段错位、品牌缺失、产品名异常、型号异常的记录，要降级为低置信度。
- 对重点车型，应回看 extracted text 原文或 evidence 文件。

### 字段清洗 Prompt

**用途**：对 product_list 中的记录做字段一致性检查，识别疑似错位记录。

**适用输入**：
- `product_list/batch_{N}_product_list.json`
- `extracted/text/batch_{N}/*.txt`
- `configs/重点关注新能源品牌.json`

**输出字段**：

| 字段 | 说明 |
|------|------|
| original_record | 原始记录（保留完整字段） |
| cleaned_enterprise_name | 清洗后的企业名称 |
| cleaned_brand | 清洗后的品牌 |
| cleaned_product_name | 清洗后的产品名称 |
| cleaned_product_model | 清洗后的产品型号 |
| issue_type | 问题类型 |
| confidence | high/medium/low |
| need_raw_text_check | 是否需要回看 extracted text |
| reason | 判断理由 |

**issue_type 可选值**：

| 类型 | 含义 |
|------|------|
| field_shift | 字段错位（如 enterprise_name 和 product_model 互换了） |
| missing_brand | 品牌字段为空 |
| suspicious_product_name | 产品名异常（如为纯数字、过短等） |
| suspicious_model | 型号异常（如为纯中文、过短等） |
| watchlist_keyword_mismatch | watchlist 关键词出现在错误的字段中 |
| ok | 字段正常 |
| uncertain | 不确定 |

**Prompt 模板**：

```
请对以下 product_list 记录做字段一致性检查。

## product_list JSON：
{将 product_list JSON 的 records 数组粘贴于此}

## 检查规则：
1. enterprise_name 应以"公司/厂/集团/有限"等企业后缀结尾
2. brand 应为企业简称或品牌名（长度通常 <=10）
3. product_name 应包含"车"、"轿车"、"客车"、"乘用车"、"货车"等产品关键词
4. product_model 应符合型号模式：大写字母+数字组合
5. 如果 enterprise_name 字段的值看起来像价格/序号/品牌名，标记 field_shift
6. 如果 product_name 字段的值为纯数字，标记 suspicious_product_name
7. 如果 brand 为空，标记 missing_brand

## 输出格式：
| original_record | cleaned_enterprise | cleaned_brand | cleaned_product | cleaned_model | issue_type | confidence | need_raw_text_check | reason |
```

**关键要求**：
- **不要直接覆盖原始数据**，只输出清洗建议。
- 对低置信度记录必须标记 `need_raw_text_check=true`。
- 字段清洗是后续所有 Prompt 模块的前置步骤。

---

## 4. Promptbuilder 总流程

```mermaid
flowchart LR
    A["📦 MIIT 批次发现"] --> B["📄 读取 evidence / product_list / extracted text"]
    B --> C["0️⃣ 输入资产检查"]
    C --> D["0a️⃣ 字段清洗与置信度校验"]
    D --> E["0b️⃣ watchlist fallback 检索"]
    E --> F["1️⃣ 批次扫描"]
    F --> G["2️⃣ 重点车型筛选"]
    G --> H["3️⃣ 车型信息抽取"]
    H --> I["4️⃣ 新旧版本差异"]
    I --> J["5️⃣ 产品意图解读"]
    J --> K["6️⃣ 竞品映射"]
    K --> L["7️⃣ 威胁等级判断"]
    L --> M["8️⃣ MIIT 月度情报简报"]
```

**流程说明**：

0. 输入资产检查 → 确认 evidence / product_list / extracted text 可用性
0a. 字段清洗与置信度校验 → 检查字段错位、品牌缺失、型号异常
0b. watchlist fallback 检索 → 从 product_list / extracted text 全字段检索，优先于 diff 文件
1. 批次扫描 → 确认批次编号、状态、资产完整性
2. 重点车型筛选 → S/A/B/C 分级，过滤噪声
3. 车型信息抽取 → 从文本中抽取企业/品牌/型号/能源形式
4. 新旧版本差异 → 对比上一批或同品牌历史记录
5. 产品意图解读 → 判断全新/改款/版本扩展
6. 竞品映射 → 匹配到我方 watchlist 或关注品牌
7. 威胁等级判断 → 评分式威胁评估
8. 月度简报 → 汇总输出

---

## 5. Prompt 模块一：批次扫描 Prompt

**用途**：识别当前批次基本信息。

**适用输入**：
- `evidence/batch_{N}_official_source_evidence.json`
- `discovery/discovered_batches.json`

**输出字段**：

| 字段 | 说明 | 示例 |
|------|------|------|
| batch_no | 批次号 | 407 |
| status | 公示/正式发布 | official |
| publish_date | 发布日期 | 2026-06-12 |
| attachment_count | 附件数 | 4 |
| product_record_count | 产品清单记录数 | 1111 |
| enterprise_count | 企业数 | 469 |
| product_model_count | 型号前缀数 | 939 |
| quality | product_list 质量 | usable |
| evidence_layers | batch / attachment / product_list 可用性 | `{batch: true, attachment: false, product_list: true}` |
| excluded_attachments | 排除的附件数 | 2 |
| key_observation | 一句话观察 | "第 407 批正式公告包含 469 家企业 939 个型号，质量可用" |

**Prompt 模板**：

```
你是一个汽车行业 MIIT 申报分析师。请读取以下 evidence JSON 并生成批次扫描摘要。

## evidence 文件：
{将 evidence JSON 粘贴于此}

## 要求：
1. 提取批次号、状态、发布日期
2. 提取 evidence_layers 三层可用性
3. 提取 product_list 记录数、企业数、型号数、quality
4. 如果 attachment_evidence 不可用，说明原因（如 404）
5. 如果 quality != usable，说明限制
6. 给出 1-2 句话 key_observation

## 输出 JSON 格式：
{
  "batch_no": ...,
  "status": ...,
  "publish_date": ...,
  "product_record_count": ...,
  "enterprise_count": ...,
  "product_model_count": ...,
  "quality": ...,
  "evidence_layers": {...},
  "key_observation": "..."
}
```

**人工校验点**：无。evidence 是工程产物，可直接使用。

---

## 6. Prompt 模块二：重点车型筛选 Prompt

**用途**：从 product_list 和 watchlist diff 中筛选值得关注的车型。

**适用输入**：
- `product_list/batch_{N}_product_list.json`
- `extracted/text/batch_{N}/*.txt`
- `diff/batch_{N}_watchlist_diff.json`
- `configs/重点关注新能源品牌.json`

**watchlist 命中优先级**：

不要只依赖 `diff/batch_N_watchlist_diff.json`。该文件基于 legacy `parsed/` 层输出，可能不反映 product_list 真实现状（如第 407 批 diff 显示 matched=0，但 product_list 包含多条 watchlist 品牌记录）。

命中优先级应调整为：

1. **product_list JSON 全字段检索** — 在 enterprise_name / brand / product_name / product_model 中搜索 watchlist 关键词
2. **extracted text 全文检索** — 对重点品牌回看 extracted text 原文确认
3. **watchlist CSV 关键词匹配** — 使用 `;` 分隔的多个关键词逐条匹配
4. **diff 文件作为参考** — 仅当与 product_list 一致时使用
5. 如果 diff 与 product_list 冲突，以 product_list + extracted text 为准，并标记 `diff_stale_or_incomplete`

**新增字段**：

| 字段 | 说明 | 可选值 |
|------|------|--------|
| source_reliability | 该命中结果的数据源可信度 | `product_list_verified` / `extracted_text_verified` / `diff_only` / `conflict_between_sources` / `low_confidence` |

**四级优先级**：

| 等级 | 含义 | 判断规则 |
|------|------|----------|
| **S 级** | 全新车型、战略车型、直接竞品、高热度品牌 | 1) 品牌在我方 watchlist 且为 S 级品牌（智己/理想/问界/小米/蔚来/小鹏/极氪）；2) 产品名包含"全新/首款/首次"等信号；3) 企业名称匹配 S 级 watchlist |
| **A 级** | 重要改款、新增关键版本、重点品牌新产品 | 1) 品牌在 watchlist 中；2) 产品名为现有车型的新版本；3) 新增高配/低配/增程/纯电版本 |
| **B 级** | 常规新增、补申报、版本扩展 | 1) 品牌在 watchlist 中但非 S/A 级别；2) 已有车型的常规版本扩展 |
| **C 级** | 低相关或暂不关注 | 1) 品牌不在 watchlist 中；2) 非乘用车（卡车/客车/专用车/摩托车） |

**输出表格格式**：

```
| 优先级 | 企业名称 | 品牌 | 产品名称 | 产品型号 | 判断理由 |
|--------|----------|------|----------|----------|----------|
| S      | 上海汽车集团 | 智己 | 纯电动运动型乘用车 | CSA6492 | watchlist 品牌，战略车型 |
| S      | 肇庆小鹏    | 小鹏 | 纯电动多用途乘用车 | NHQ6490 | watchlist 品牌，全新 SUV |
| A      | 北京现代    | 北京现代 | 纯电动轿车 | BH7002 | 现有车型改款 |
```

**Prompt 模板**：

```
你是一个汽车行业竞品分析师。请从以下 product_list 和 watchlist diff 中筛选重点车型。

## product_list JSON：
{将 product_list JSON 的 records 数组粘贴于此}

## watchlist diff JSON（如果可用）：
{将 watchlist diff JSON 粘贴于此}

## watchlist 品牌：
智己, 理想, 问界, 小米, 蔚来, 小鹏, 极氪, 阿维塔, 深蓝, 零跑, 腾势, 方程豹, 比亚迪, 特斯拉

## 分级规则：
- S 级：watchlist 品牌的首次出现车型
- A 级：watchlist 品牌的新版本
- B 级：watchlist 品牌的常规扩展
- C 级：非关注品牌

## 输出格式：
Markdown 表格，包含：优先级, 企业名称, 品牌, 产品名称, 产品型号, 判断理由
```

**不确定时如何标记**：
- 如果品牌不在 watchlist 但企业名称包含关键词 → 标记为 `A?`（待确认）
- 如果产品名称不明确 → `remarks: "产品名称不完整，待确认"`

---

## 7. Prompt 模块三：车型信息抽取 Prompt

**用途**：从 extracted text 或 product_list 中抽取单车基础信息。

**适用输入**：
- `extracted/text/batch_{N}/{attachment1}.txt`（附件 1 原始文本片段）
- `product_list/batch_{N}_product_list.json`（单条记录）

**输出字段**：

| 字段 | 说明 | 必须/可选 | 示例 |
|------|------|-----------|------|
| enterprise_name | 企业全称 | 必须 | 上海汽车集团股份有限公司 |
| brand | 品牌 | 必须 | 智己 |
| product_name | 产品名称 | 必须 | 纯电动运动型乘用车 |
| product_model | 产品型号 | 必须 | CSA6492 |
| model_prefix | 型号前缀（当前解析粒度） | 必须 | CSA6492 |
| energy_type | 能源类型（如果从文本可识别） | 可选 | BEV |
| vehicle_type | 车辆类型（如果可识别） | 可选 | 运动型乘用车 |
| raw_text_evidence | 原始文本证据 | 必须 | 原文片段 |
| confidence | high/medium/low | 必须 | high |
| unknown_fields | 未解析字段列表 | 必须 | ["续航", "电池容量", "电机功率"] |

**关键要求**：
- 如果原始文本没有可靠信息，必须标记 `unknown`，**不要编造**。
- 当前工程阶段不解析续航、电池、电机、尺寸等深度参数。
- 从 product_list 只能得到企业名/品牌/产品名/型号前缀。

**Prompt 模板**：

```
请从以下文本中抽取车型基础信息。

## 文本片段：
{将产品清单单条记录或 extracted text 片段粘贴于此}

## 输出字段：
- enterprise_name（企业全称）
- brand（品牌）
- product_name（产品名称）
- product_model（产品型号）
- model_prefix（型号前缀）
- energy_type（能源类型：BEV/PHEV/EREV/ICE/FCV/unknown）
- vehicle_type（车辆类型：轿车/SUV/MPV/客车/货车/专用车/unknown）
- raw_text_evidence（支撑上述信息的原文片段）
- confidence（high/medium/low）
- unknown_fields（无法确定的字段列表）

## 规则：
1. 不能从 product_name 推断能源类型（例如"纯电动"算 BEV，"插电式增程混合动力"算 PHEV）
2. 如果文本中不包含某字段信息，必须在 unknown_fields 中列出
3. 不要编造续航、电池容量、电机功率、尺寸等数据
4. confidence=high 仅当字段直接从原文提取；推导得到的标记 medium 或 low
```

---

## 8. Prompt 模块四：新旧版本差异 Prompt

**用途**：对比两批 product_list，识别新增、消失、改款、扩展。

**适用输入**：
- `product_list/batch_{N}_product_list.json`
- `product_list/batch_{N-1}_product_list.json`（上一批）
- 或 `diff/batch_{N}_watchlist_diff.json`

**差异类型定义**：

| 类型 | 含义 | 判断依据 |
|------|------|----------|
| new_model | 全新车型 | 品牌+企业相同，但型号前缀完全新增 |
| removed_model | 消失车型 | 上一批存在但本批不存在 |
| new_variant | 新增变体 | 同一型号前缀下新增变体后缀 |
| possible_refresh | 疑似改款 | 产品名或产品类型有变化 |
| naming_change | 命名变更 | 企业名或产品名变化 |
| uncertain | 不明 | 数据不足以判断 |

**输出字段**：

```
| 类型 | 企业 | 品牌 | 产品名 | 型号 | 本批状态 | 上批状态 | 说明 |
|------|------|------|--------|------|----------|----------|------|
| new_model | 上海汽车 | 智己 | ... | CSA6492 | NEW | absent | 全新车型申报 |
| new_variant | ... | ... | ... | CSA6492-V2 | NEW | CSA6492 | 同一平台新增 |
| removed_model | ... | ... | ... | ... | absent | PRESENT | 上批有本批无 |
```

**Prompt 模板**：

```
比较以下两批 product_list，识别差异。

## 本批（batch_{N}）：
{本批 product_list JSON 的 records}

## 上批（batch_{N-1}）：
{上批 product_list JSON 的 records}

## 差异类型定义：
- new_model：全新型号前缀
- removed_model：上一批有但本批消失
- new_variant：同一型号前缀的新变体
- possible_refresh：产品名变化
- naming_change：企业名或产品名更改
- uncertain：无法判断

## 输出格式：
Markdown 表格：类型, 企业, 品牌, 产品名, 型号, 本批状态, 上批状态, 说明

## 约束：
- 只输出 watchlist 品牌的差异或明显重要的差异（企业数 > 全部输出则太长）
- 不确定的类型标记为 uncertain
```

---

## 9. Prompt 模块五：产品意图解读 Prompt

**用途**：从申报变化中推断车企产品意图。

**适用输入**：
- 车型信息抽取输出
- 新旧版本差异输出

**产品意图类型**：

| 意图类型 | 说明 | 典型证据 |
|----------|------|----------|
| 全新车型上市前信号 | 首次出现某系列型号前缀 | 全新 model_prefix，非往批衍生 |
| 年款/改款 | 已有车型的常规迭代 | 型号前缀相同，后缀变化 |
| 新增低配/高配版本 | 同一前缀下新增/减少配置级 | 同一产品名下新增/减少型号 |
| 补齐产品短板 | 新增纯电/增程/混动版本补齐能源线 | 已有 ICE 版本，新增 BEV/PHEV/EREV |
| 扩展价格带 | 新增入门/旗舰版本扩展价格覆盖 | 产品名变化暗示定位变化 |
| 强化卖点 | 续驶里程/智驾/动力等参数升级 | 不能仅从 MIIT 判断（需参数） |
| 常规申报 | 无明显战略信号 | 上述均不匹配 |
| 无法判断 | 数据不足以推断 | 信息不完整 |

**事实 vs 推断区分**：

- **事实**（F）：直接来自申报文本。例如："型号 CSA6492LFSHEV3"
- **合理推断**（R）：基于事实的合理推测。例如："该型号前缀首次出现，推断为全新车型"
- **待验证假设**（H）：需要非 MIIT 来源验证。例如："该车型可能定价 20-30 万"

```
## 输出格式：
| 企业 | 品牌 | 产品名 | 型号 | 意图判断 | 类型(F/R/H) | 事实依据 |
|------|------|--------|------|----------|-------------|----------|
| 上汽 | 智己 | 插电式增程混合动力运动型乘用车 | CSA6492LFSHEV3 | 补齐产品短板（新增增程版本） | F | "插电式增程混合动力"表明新增增程动力 |
```

**Prompt 模板**：

```
请分析以下申报记录的产品的意图。

## 申报记录：
{车型信息抽取输出 / 多行产品记录}

## 当前批次差异信息（如果可用）：
{差异分析结果}

## 意图类型：
{插入上述意图类型表}

## 要求：
1. 区分事实(F)、合理推断(R)、待验证假设(H)
2. 每条判断都必须引用申报文本为依据
3. 不要过度解读
4. 如果无法判断，写"无法判断"

## 输出格式：
Markdown 表格：企业, 品牌, 产品名, 型号, 意图判断, 类型(F/R/H), 事实依据
```

---

## 10. Prompt 模块六：竞品映射 Prompt

**用途**：判断申报车型可能对应的直接竞品。

**适用输入**：
- 车型信息抽取输出
- watchlist CSV

**竞品映射维度**：

| 维度 | 说明 |
|------|------|
| 品牌 | 是否是 watchlist 品牌 |
| 车型级别 | 中型轿车/中大型 SUV/紧凑型 MPV 等 |
| 车身形式 | 轿车/SUV/MPV/跨界/跑车 |
| 能源形式 | BEV/PHEV/EREV/ICE/FCV |
| 可能价格带 | 基于品牌+车型级别的推断 |
| 用户场景 | 家用/商务/营运/个性化 |
| 与我方车型相关性 | 高/中/低/无关 |
| 置信度 | high/medium/low |

**输出表格**：

```
| 申报企业 | 品牌 | 产品名 | 型号 | 可能级别 | 能源 | 可能价格带 | 我方相关车型 | 相关性 | 置信度 |
|----------|------|--------|------|----------|------|-----------|-------------|--------|--------|
| 上汽 | 智己 | 纯电动运动型乘用车 | CSA6492 | 中大型 SUV | BEV | 30-40 万 | LS6 | 高 | high |
| 肇庆小鹏 | 小鹏 | 纯电动多用途乘用车 | NHQ6490 | 中大型 SUV | BEV | 25-35 万 | LS6 | 中 | medium |
```

**Prompt 模板**：

```
请将以下 MIIT 申报车型映射到我方竞品 watchlist。

## 申报车型：
{车型信息抽取输出}

## 我方关注品牌：
智己, 理想, 问界, 小米, 蔚来, 小鹏, 极氪, 阿维塔, 深蓝, 零跑, 腾势, 方程豹, 比亚迪, 特斯拉

## 我方核心车型：
LS6（中大型纯电动 SUV）、LS8（全尺寸纯电动 SUV）、LS9（旗舰 SUV）

## 映射维度：
品牌、车型级别、车身形式、能源形式、可能价格带、用户场景

## 输出格式：
Markdown 表格：申报企业, 品牌, 产品名, 型号, 可能级别, 能源, 可能价格带, 我方相关车型, 相关性, 置信度

## 约束：
- price_estimate 应基于品牌+车型级别+能源形式推断，标注 "estimate"
- 相关性和置信度必须明确（高/中/低）
```

---

## 11. Prompt 模块七：威胁等级判断 Prompt

**用途**：判断某条申报信息对我方的潜在威胁。

**适用输入**：
- 竞品映射输出
- 车型信息抽取输出

**评分维度**：

| 维度 | 权重 | 评分规则（1-10） |
|------|------|------------------|
| 价格带重叠 | 25% | 10=完全重叠，1=无重叠 |
| 产品形态重叠 | 20% | 10=同级别同车身，1=完全不同 |
| 核心卖点冲突 | 20% | 10=直接对标同一卖点，1=无冲突 |
| 品牌/声量影响 | 15% | 10=头部品牌，1=小众品牌 |
| 上市时间临近度 | 10% | 10=1-3 个月内，1=12 个月以上 |
| 对我方现款/新款影响 | 10% | 10=直接影响现款销量，1=不影响 |

**威胁等级**：

| 分数区间 | 等级 | 行动建议 |
|----------|------|----------|
| 80–100 | 🚨 高优先级预警 | 立即启动详细竞品分析 |
| 60–79 | ⚠️ 中高优先级关注 | 纳入月度跟踪清单 |
| 40–59 | 👀 常规跟踪 | 简要记录，下次更新时关注 |
| 20–39 | 🔍 低优先级观察 | 累计信息，无需主动跟踪 |
| 0–19 | ✅ 暂不关注 | 与本业务无关 |

**输出字段**：

```
{
  "enterprise": "...",
  "brand": "...",
  "product_name": "...",
  "product_model": "...",
  "threat_score": 72,
  "threat_level": "中高优先级关注",
  "reasons": [
    "价格带与 LS6 重叠",
    "同为纯电动 SUV",
    "小鹏品牌声量高"
  ],
  "evidence": "NHQ6490BEVVB 纯电动多用途乘用车",
  "uncertainty": "medium（上市时间和价格未确认）",
  "follow_up_needed": true,
  "suggested_action": "关注定价和上市时间"
}
```

**关键限制**：
- MIIT 阶段只能判断**潜在威胁**，不能等同于上市后的真实威胁。
- 价格带、上市时间、配置等关键信息的确认需要其他来源。

---

## 12. Prompt 模块八：MIIT 月度情报简报 Prompt

**用途**：将一个批次或一个月内的 MIIT 申报整理为业务简报。

**适用输入**：
- 以上 1-7 号模块的全部输出
- 多批次的 evidence / product_list / diff

**报告结构**：

```markdown
# MIIT 月度情报简报 | 2026 年 6 月

## 1. 本批次一句话结论
第 407 批正式公告涉及 S 级关注品牌 7 家，其中智己新增增程版本为战略级信号。

## 2. 本批次重点车型清单（S 级 + A 级）
| 品牌 | 企业 | 产品名 | 型号 | 等级 |
|------|------|--------|------|------|
| 智己 | 上汽 | 插电式增程混合动力运动型乘用车 | CSA6492LFSHEV3 | S |
| 小鹏 | 肇庆小鹏 | 纯电动多用途乘用车 | NHQ6490/NHQ6510 | S |

## 3. S/A 级车型详解
### 3.1 智己 L6 增程版（CSA6492LFSHEV3）
- **企业**：上海汽车集团股份有限公司
- **产品**：插电式增程混合动力运动型乘用车
- **型号**：CSA6492LFSHEV3 / CSA6492LFSHEV4（两个版本）
- **意图**：补齐产品短板（新增增程动力）
- **我方影响**：LS6 增程版本预计面临同集团定位挑战

### 3.2 小鹏 L05 / G9L（NHQ6490/NHQ6510）
- **企业**：肇庆小鹏新能源投资有限公司
- **产品**：纯电动多用途乘用车 / 插电式增程混合动力多用途乘用车
- **型号**：NHQ6490 / NHQ6510 多版本
- **意图**：小鹏 L05 全新产品线
- **我方影响**：中大型 SUV 市场竞争加剧

## 4. 新车/改款/新增版本分类
| 类型 | 数量 | 代表 |
|------|------|------|
| 全新车型 | 2 | 小鹏 L05、岚图泰山 X8 |
| 新增增程版本 | 3 | 智己 L6、小鹏 G9L |
| 改款 | 5 | ... |
| 常规新增 | 12+ | ... |

## 5. 重点车型产品意图解读
- 智己：从纯电向增程扩展，覆盖主流 PHEV/EREV 市场
- 小鹏：L05 全新产品线 + G9L 增程版，双线布局

## 6. 对我方相关车型影响
- LS6：智己 L6 增程版 + 小鹏 L05 构成竞品
- LS8：小鹏 G9L 增程版直接竞争

## 7. 后续上市节奏观察
- 智己 L6 增程版：预计 2026 Q3-Q4 上市
- 小鹏 L05：预计 2026 Q4 上市
- G9L 增程版：预计 2026 Q3 上市

## 8. 7/30/90 天追踪清单
| 车型 | 7 天 | 30 天 | 90 天 |
|------|------|-------|-------|
| 智己 L6 增程 | 获取参数配置 | 跟踪上市预告 | 准备对比分析 |
| 小鹏 L05 | 获取更多信息 | 关注定价策略 | 实测对比 |

## 9. 数据缺口与待验证事项
- 价格带：MIIT 数据不包含定价，需其他来源
- 续航与配置：需等工信部能耗目录或上市发布会
- 车型详细参数：底盘/智驾/电池等非 MIIT 可获取
```

**Prompt 模板**：

```
请根据以下 MIIT 申报分析报告生成月度情报简报。

## 输入素材：
{以上 1-7 号模块的全部输出}

## 简报结构要求：
{插入上述报告结构}

## 输出约束：
1. 所有结论必须标注来源（MIIT 申报 / 推断 / 待验证）
2. 涉及价格、上市时间、配置等需标注 "estimate" 或 "待确认"
3. 不超过 3 页 A4
4. 使用 Markdown 格式
```

---

## 13. 人工校验规则

以下内容必须人工校验，不应由 AI 独立输出：

| 内容 | 校验原因 | 建议校验人 |
|------|----------|-----------|
| 车型真实上市节奏 | MIIT 申报到上市有 3-12 个月延迟 | 产品规划团队 |
| 全新车型 vs 改款判断 | 型号前缀变化不一定代表全新车型 | 产品分析师 |
| 价格带判断 | 仅基于品牌+车型级别的推测 | 定价团队 |
| 竞品映射 | 可能漏掉间接竞品 | 竞品分析师 |
| 威胁等级评分 | 仅供参考，非精确量化 | 管理层审阅 |
| 管理层建议 | 涉及资源分配的决策 | 产品负责人 |
| 涉及内部车型/产品规划的判断 | 可能涉及机密 | 部门负责人 |

---

## 14. 不应优先工程化的部分

基于摸排报告（`miit_module_audit_v0.3.3.md`），以下内容当前不建议优先工程化：

| 项目 | 原因 | 触发条件 |
|------|------|----------|
| 深度参数解析（续航/电池/电机/尺寸） | DOC 文本格式不统一，工程投入大，收益不确定 | Promptbuilder 验证需要后 |
| 税收目录结构化（附件 2/3） | 仅排除不做解析，当前够用 | 需要车船税/购置税分析时 |
| 自动定时任务（cron/GitHub Actions） | 工信部网站不稳定，自动运行易产生噪声 | 批次发现稳定后 |
| 飞书/邮件推送 | 业务需求未形成 | 有明确消费方时 |
| 与 auto_launch_monitor 联动 | 跨模块耦合，时机未到 | 两个模块都成熟后 |
| 大规模历史批次回填（第 100-398 批） | 每批需人工验证，ROI 低 | 有明确分析需求时 |

---

## 15. 第 407 批 Dry Run 经验

### 关键发现

| 发现 | 影响 | v0.2 修订动作 |
|:---|:---|:---|
| **product_list 字段偏移**：小鹏/问界/零跑等品牌的多条记录中 enterprise_name / brand / product_name / product_model 列错位 | watchlist 命中准确率降低；品牌/产品名/型号信息不可靠 | 新增"输入清洗与字段可信度校验"章节（§3），增加字段清洗 Prompt 模块 |
| **diff 文件未覆盖 product_list**：`watchlist_diff` 基于 legacy `parsed/` 层输出 matched=0，但 `product_list/` 实际包含多条 watchlist 品牌记录 | 仅依赖 diff 会漏掉全部重点信号 | 调整 watchlist 命中优先级，product_list 全字段检索优先于 diff 文件 |
| **智己增程版为 S 级信号**：CSA6492LFSHEV3/4 字段对齐好、品牌确定，推断为 L6/LS6 增程版 | 验证了 product_list 对字段对齐良好的品牌可提供有用信号 | 作为 S 级观察对象写入 dry run 经验，后续仍需官网/公告/上市信息验证 |
| **缺少上一批 product_list 快照**：仅有一批数据无法做严格两批对比，新旧版本差异只能做弱判断 | 新旧版本差异模块在当前数据条件下实用性有限 | 建议为每批 product_list 保留快照；短期内可在 Promptbuilder 层做"品牌内型号前缀第一次出现"的弱判断 |
| **深度参数全部 unknown**：续航/电池/电机/尺寸均不可得 | 威胁等级评分缺乏关键输入（续航、价格），评分置信度低 | 明确标注深度参数不应由当前 product_list 推断；后续可通过能耗目录/税收目录补充 |

### 方法论调整

1. **MIIT Promptbuilder 第一层不是业务解读，而是输入可信度校验**。在跑任何业务分析 prompt 前，必须先做字段清洗和置信度判断。

2. **watchlist 命中必须支持 product_list / extracted text fallback**。不能只依赖一个数据源（如 diff 文件）。多源交叉验证才能降低漏报。

3. **新旧版本差异必须依赖历史批次快照**。如果只有单批数据，差异分析只能做弱判断（如"品牌内型号前缀是否首次出现"），无法做严格对比。

4. **深度参数不应由当前 product_list 推断**。续航、电池、电机、尺寸等参数当前不可用，不应编造。如需这些信息，应通过税收目录/能耗目录/上市发布会等非 MIIT 来源补充。

5. **对智己增程版这类信号，可以作为 S 级观察对象**，但仍需后续官网/公告/上市信息验证。MIIT 申报到上市有 3-12 个月延迟，不能等同于真实竞争威胁。

---

### 使用示例

**输入**：

```
evidence: outputs/miit_new_car/evidence/batch_407_official_source_evidence.json
product_list: outputs/miit_new_car/product_list/batch_407_product_list.json
watchlist_diff: outputs/miit_new_car/diff/batch_407_watchlist_diff.json
```

**处理流程**：

0. 运行输入资产检查 → 确认 evidence / product_list / extracted text 可用
0a. 运行字段清洗 Prompt → 检测字段错位、品牌缺失、型号异常
0b. 运行 watchlist fallback 检索 → 从 product_list 全字段检索 + extracted text 确认
1. 运行批次扫描 Prompt → 确认第 407 批正式公告，1111 条记录，quality=usable
2. 运行重点车型筛选 Prompt → 识别 S/A 级车型（智己增程版等）
3. 运行车型信息抽取 Prompt → 抽取完整车型信息（标注 unknown_fields）
4. 运行新旧版本差异 Prompt → 如果无上批快照，做弱判断（首次出现分析）
5. 运行产品意图解读 Prompt → 判断智己增程 = 补齐短板
6. 运行竞品映射 Prompt → 映射到 LS6/LS8 竞品
7. 运行威胁等级判断 Prompt → 智己增程版 threat_score=68（中高，dry run 低置信度）
8. 运行月度简报 Prompt → 生成简报

**预期输出**：
- 本批次重点车型清单（5-10 条）
- 潜在竞品威胁分析（3-5 条）
- 后续追踪清单（7/30/90 天）
- 数据缺口（待确认事项）

---

## 16. 版本说明

- **Version**: v0.2 draft
- **Source**: miit_module_audit_v0.3.3.md + batch_407_official_miit_signal_brief.md
- **Scope**: Promptbuilder only — 不修改任何 MIIT 工程代码
- **Code changes**: none
- **Key update**: add input cleaning, field confidence check, watchlist fallback search, dry run learnings
- **Date**: 2026-06-22
- **Next version triggers**:
  - v0.3：基于第二批/第三批 dry run 经验迭代 prompt 模板
  - v1.0：验证业务价值后，部分 prompt 可固化到 `scripts/` 或 `eval/` 中
