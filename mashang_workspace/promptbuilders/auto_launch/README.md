# Auto Launch Promptbuilder

> **DEPRECATED — 此目录已迁移。**
> 完整 auto_launch 服务现已移至 `auto_launch/`。
> 所有 Python 脚本、测试、CLI 入口、配置文件已迁移。
> 本目录保留作为历史 Prompt 资产归档，请勿再通过本目录路径运行或引用。
> 新路径: `services/auto_launch/`

## 1. 项目定位

`promptbuilders/auto_launch/` 是面向 **智己 LS8 竞品车型与重点新能源品牌** 的汽车上市 / 销售 / 营销事件发现体系。

它当前的核心不是生成长篇竞品报告，也不是完整的爬虫或 ETL 系统，而是通过：

- Prompt 母版
- 结构化 watchlist
- 事件类型定义
- 信源分级与域名映射
- Volc Search 检索策略配置

来支持日常发现以下信息：

- 车型级动态
- 品牌级营销事件
- 已确认销售 / 上市 / 权益 / 渠道事件
- 弱信号 / 待确认线索
- 信源覆盖情况与检索审计

当前目录更准确的定位是：

> Auto Launch 的 **Prompt Layer + Config Layer + Search Task Definition Layer**。

它不是完整的 validate → normalize → intake → render → report pipeline。下游处理链路当前主要由 workspace 层脚本承接。

---

## 2. 当前真实目录结构

```text
promptbuilders/auto_launch/
├── README.md                                 项目总文档
├── LS8 竞品车型动态追踪.md                    Model Watch Prompt 母版（10 款车型）
├── 重点关注品牌每日营销事件监控.md               Brand Watch Prompt 母版（24 个品牌）
│
├── configs/
│   ├── event_types.yaml                       19 类事件类型定义
│   ├── source_tiers.yaml                      5 层信源分级
│   ├── source_domains.yaml                    域名/信源分类映射（7 类）
│   ├── volc_search.yaml                       API 配置 + query profiles + 缓存 + 模板
│   ├── ls8_competitor_watchlist.csv           车型列表（CSV，供 Volc Search 读取）
│   ├── ls8_competitor_watchlist.yaml          车型列表（YAML，供目标匹配）
│   └── priority_brand_watchlist.yaml          品牌列表（YAML，供目标匹配）
│
├── runbooks/
│   └── shared_event_source_taxonomy.md        事件/信源交叉分析报告
│
└── templates/
    └── search_intent_compiler.prompt.md        用户意图转译规则文档
```

---

## 3. 当前两层架构

| 层级      | 文件                                                         | 职责                                                                                                       |
| --------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| Prompt 层 | `LS8 竞品车型动态追踪.md`、`重点关注品牌每日营销事件监控.md` | ChatGPT Plan prompt 母版，定义事件发现规则、检索策略、媒体范围、输出格式                                   |
| 配置层    | `configs/*.yaml`、`configs/*.csv`                            | 从 Prompt 母版中抽离出的结构化配置，包括事件类型、信源分级、域名映射、搜索 API 参数、车型 / 品牌 watchlist |

当前 `promptbuilders/auto_launch/` 暂时不是完整 ETL / report pipeline，而是 Search Layer / Prompt Layer / Config Layer 的组合。

---

## 4. Prompt 母版

### 4.1 `LS8 竞品车型动态追踪.md`

定位：**Model Watch Prompt 母版**。

用途：

- 面向 10 款 LS8 竞品车型
- 发现车型级销售动作、上市动作、权益调整、配置变化、交付节奏、渠道动作和传播动作
- 将车型动态限定在 LS8 所在竞争战场中理解
- 输出结构化结果，供下游脚本或人工判断消费

适合的问题：

- 近 24 小时 / 近 72 小时，LS8 竞品车型有什么明确销售动作？
- 哪些车型出现了权益变化、预售、上市、交付、配置变化？
- 哪些只是弱信号，需要继续观察？

### 4.2 `重点关注品牌每日营销事件监控.md`

定位：**Brand Watch Prompt 母版**。

用途：

- 面向 24 个重点新能源品牌
- 发现品牌级营销事件、传播动作、发布会、官方权益、渠道动作、内容营销、社媒动作和弱信号
- 适合作为每日品牌雷达
- 与车型级监控互补：品牌层看声量与动作，车型层看明确销售事件

适合的问题：

- 近 7 日某品牌有哪些营销动作？
- 24 个重点品牌里，哪些品牌今天有值得关注的传播事件？
- 哪些品牌只有弱信号，尚不能进入 confirmed event？

---

## 5. configs 文件说明

### 5.1 `event_types.yaml`

定义 19 类事件类型。

用途：

- 统一车型 / 品牌事件分类
- 避免每次 Prompt 自创 event_type
- 支撑后续事件归类、统计、筛选和人工复核

典型覆盖方向包括：

- 上市 / 预售 / 发布会
- 价格 / 权益 / 配置变化
- 交付 / 渠道 / 用户运营
- 品牌传播 / 内容营销 / 官方活动
- 弱信号与待确认事件

### 5.2 `source_tiers.yaml`

定义 5 层信源分级。

用途：

- 判断来源可信度
- 区分官方源、权威媒体、汽车垂媒、社交平台、经销商等不同信源层级
- 为 confirmed event 与 discovery signal 提供证据门槛

核心原则：

- 官方源优先用于确认事件
- 垂媒 / 科技财经媒体可用于交叉验证
- 社媒 / 经销商 / 用户侧内容更适合作为弱信号
- 来源冲突或证据不足时进入待复核

### 5.3 `source_domains.yaml`

域名 / 信源分类映射配置，当前覆盖 7 类信源。

用途：

- 识别 official / media / social / dealer / platform 等来源类别
- 支持 source_name、source_title、source_url 等字段的规范化判断
- 辅助区分官方公告、媒体报道、社媒传播、经销商动作和平台线索

它不是搜索结果本身，而是用于解释和归类搜索结果的信源映射表。

### 5.4 `volc_search.yaml`

Volc Search API 相关配置。

用途：

- 配置 API 参数
- 定义 query profiles
- 配置缓存策略
- 定义分 stage query 模板
- 建立用户意图与检索策略之间的映射

当前它是 Search Layer 的关键配置文件，用于支撑不同检索预算和不同任务意图，例如：

- 单品牌近 7 日营销动作
- 10 款车型每日销售动作
- 指定车型 deep dive
- 官方优先检索
- 媒体 / 社媒扩展检索

### 5.5 `ls8_competitor_watchlist.csv`

车型列表 CSV。

用途：

- 供 Volc Search 批量读取
- 适合生成批量搜索任务
- 面向每日车型级监控

该文件更偏执行层读取，强调轻量、表格化和批处理友好。

### 5.6 `ls8_competitor_watchlist.yaml`

车型列表 YAML。

用途：

- 供目标匹配使用
- 保存车型别名、品牌归属、车型关系、battle field 判断等结构化信息
- 支持 Prompt 或脚本进行更精细的目标识别

该文件更偏语义层配置，适合做车型归属、别名识别和战场映射。

### 5.7 `priority_brand_watchlist.yaml`

24 个重点品牌列表。

用途：

- 供品牌级每日营销事件监控使用
- 支持品牌别名、品牌归属、重点车型或关键词匹配
- 与 `重点关注品牌每日营销事件监控.md` 配套使用

它是 Brand Watch 的核心输入之一。

---

## 6. runbooks / templates

### 6.1 `runbooks/shared_event_source_taxonomy.md`

事件 / 信源交叉分析报告。

用途：

- 沉淀事件类型与信源体系之间的关系
- 解释为什么不同事件需要不同信源组合
- 帮助判断哪些事件必须官方确认，哪些事件可以先作为弱信号观察

例如：

- 价格 / 权益更新更依赖官方源
- 渠道动作可能先出现在经销商或社媒
- 发布会 / 传播事件可通过官方 + 媒体交叉确认
- 用户运营或门店活动可能需要社媒 / 经销商作为早期线索

### 6.2 `templates/search_intent_compiler.prompt.md`

用户自然语言意图转译规则文档。

用途：

- 将自然语言需求转译为可执行搜索配置
- 统一 intent、query profile、时间窗口、stage、source strategy 的选择逻辑
- 降低每次手写搜索 Prompt 的成本

典型输入：

- “搜索近 7 日极氪的营销动作”
- “查 LS8 竞品今天有没有销售动作”
- “只看官方源，确认某车型权益是否变化”
- “扩展看社媒和经销商弱信号”

典型输出方向：

- 搜索目标
- 时间窗口
- query profile
- 检索 stage
- source 范围
- confirmed event / discovery signal 判断边界

---

## 7. 当前接入关系

当前 `promptbuilders/auto_launch/` 负责定义 Prompt 与配置，不在本目录内完成完整闭环。

当前 Search Layer 的输出会接入 workspace 层脚本，例如：

```text
mashang_workspace/research_scripts/auto_launch/
mashang_workspace/outputs/
mashang_workspace/outputs/reports/
```

因此，请不要把 `promptbuilders/auto_launch/` 理解为已经包含以下完整模块：

```text
validate → normalize → intake → render → report
```

更准确的理解是：

```text
Prompt 母版
  ↓
结构化配置
  ↓
Search Task / ChatGPT Plan
  ↓
Raw / structured output
  ↓
workspace 层 research_scripts / outputs / reports 承接后续处理
```

---

## 8. 当前已实现能力边界

### 已实现

- 车型级 Prompt 母版：10 款 LS8 竞品车型动态追踪
- 品牌级 Prompt 母版：24 个重点品牌每日营销事件监控
- 19 类事件类型定义
- 5 层信源分级
- 7 类域名 / 信源分类映射
- Volc Search query profiles / cache / stage templates / intent mappings
- 车型 watchlist：CSV + YAML 双格式
- 品牌 watchlist：YAML
- 用户意图转译模板
- 事件 / 信源 taxonomy runbook

### 未在本目录实现

- JSON Schema 校验器
- 归一化模块
- intake workflow
- Markdown / HTML renderer
- 报告生成器
- output indexer
- golden case registry
- 完整 regression test fixture
- 独立 search adapter 包装层

这些能力可能存在于 workspace 层脚本或未来规划中，但不属于当前 `promptbuilders/auto_launch/` 的事实目录结构。

---

## 9. Roadmap / 未实现设计目录

以下目录曾作为 ChatGPT Plan 下游链路的设计方向出现，但当前没有在 `promptbuilders/auto_launch/` 内创建，不应在 README 中描述为已实现模块。

```text
prompts/
plan_templates/
examples/
validators/
renderers/
intake/
reports/
indexers/
schemas/
search_adapters/
```

这些目录原本对应的完整链路是：

```text
validate → normalize → intake → render → report
```

当前处理方式是：

- Prompt 与配置沉淀在 `promptbuilders/auto_launch/`
- 运行、验证、报告等后续处理由 workspace 层脚本承接
- 等这些模块真正迁入本目录后，再更新 README 和目录结构

---

## 10. 使用方式

### 10.1 车型级日常监控

使用：

```text
LS8 竞品车型动态追踪.md
configs/ls8_competitor_watchlist.csv
configs/ls8_competitor_watchlist.yaml
configs/event_types.yaml
configs/source_tiers.yaml
configs/source_domains.yaml
configs/volc_search.yaml
```

适合任务：

- 每日检查 10 款 LS8 竞品车型是否有新销售动作
- 识别 confirmed event、discovery signal、needs review
- 输出给 workspace 层脚本做后续处理

### 10.2 品牌级每日雷达

使用：

```text
重点关注品牌每日营销事件监控.md
configs/priority_brand_watchlist.yaml
configs/event_types.yaml
configs/source_tiers.yaml
configs/source_domains.yaml
configs/volc_search.yaml
```

适合任务：

- 每日检查 24 个重点品牌是否有营销事件
- 发现官方动作、内容传播、社媒动作、渠道信号
- 作为品牌级情报雷达

### 10.3 自然语言搜索意图转译

使用：

```text
templates/search_intent_compiler.prompt.md
configs/volc_search.yaml
configs/source_domains.yaml
```

适合任务：

- 把“查某品牌近 7 日营销动作”转成可执行检索计划
- 把“只看官方源”转成 official-first / official-only 检索策略
- 把“扩大搜索”转成 higher budget query profile

---

## 11. 维护规则

1. README 必须以当前真实目录为准。
2. 新增目录后，才可以把它写入“当前目录结构”。
3. 未创建、未实现、未接入的模块只能写入 Roadmap / 未实现设计。
4. Prompt 母版负责业务规则表达，configs 负责结构化配置。
5. watchlist、event types、source tiers、source domains 的变更应优先进入 configs。
6. 不要在 Prompt 母版中长期硬编码可配置数据。
7. 下游 validate / normalize / intake / render / report 若迁入本目录，需要同步更新 README。
8. workspace 层脚本路径变化时，需要同步更新“当前接入关系”。

---

## 12. 历史口径说明

旧 README 曾把 `promptbuilders/auto_launch/` 描述为包含完整 intake 和 report pipeline 的目录，并列出多个规划目录。

当前已修正为事实口径：

- 本目录保留 Prompt 母版与 configs 为核心
- 未实现目录进入 Roadmap
- 下游处理链路归入 workspace 层
- 当前不再把未创建目录描述为已实现能力
