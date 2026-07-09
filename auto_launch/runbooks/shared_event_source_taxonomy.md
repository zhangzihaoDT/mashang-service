# auto_launch v2 共性事件类型与信源体系抽取

## 1. 背景

auto_launch 项目已拆分为两个独立能力：

- **LS8 竞品车型动态追踪**（model_watch）：聚焦车型战场，追踪 10 款 LS8 竞品车型的销售动作、产品动作、上市节奏、价格权益、配置变化
- **重点关注品牌每日营销事件监控**（brand_watch）：聚焦品牌战场，追踪 24 个重点新能源品牌的营销动作、传播动作、发布会、权益、战报、渠道活动

两份 Prompt 母版在事件类型和信源体系上存在大量重叠，也有各自专属的能力。本报告从中抽取共性部分，为后续配置化改造做准备。

## 2. 输入 Prompt 母版

| 文件 | 定位 |
|------|------|
| `services/auto_launch/prompts/LS8 竞品车型动态追踪.md` | model_watch：车型级销售动作监控 |
| `services/auto_launch/prompts/重点关注品牌每日营销事件监控.md` | brand_watch：品牌级营销事件监控 |

## 3. 共性 event taxonomy

以下 9 类事件在两个模板中均出现或语义等价，建议作为 shared event types 纳入配置。

| event_type_id | event_type_cn | definition | applies_to | confirmation_level | evidence_required | weak_signal_examples | source_priority | notes |
|---|---|---|---|---|---|---|---|---|
| `launch` | 新车正式上市 | 新车正式上市，公布全系售价和配置 | both | confirmed_event | 官方发布 + 售价+配置信息完整 | 经销商暗示即将到店未定价 | 品牌官方 > 垂直媒体 > 财经媒体 | 最核心事件，品牌/车型模板定义一致 |
| `presale` | 开启预售 | 新车开启预售，公布预售价和预售权益 | both | confirmed_event | 官方公布预售价和预定通道 | "疑似预售价"出自论坛 | 品牌官方 > 垂直媒体 | model_watch 含盲订/预订，brand_watch 含小订/大定，合并 |
| `launch_event` | 发布会/亮相 | 新车发布会、品牌日、技术日、可能公布价格或仅亮相 | both | confirmed_event | 官方预告或媒体报道+明确时间地点 | 经销商销售话术称"月底有活动" | 品牌官方 > 垂直媒体 > 财经媒体 | model_watch 窄（仅新车发布会），brand_watch 宽（含品牌日/技术日） |
| `debut` | 首发亮相 | 新车首次公开亮相/车展首发/实车展示 | both | confirmed_event | 车展官方发布或正式媒体报道 | 渲染图/谍照流出 | 车展官方 > 垂直媒体 > 社交信号 | 两个模板定义一致 |
| `config_release` | 配置发布 | 官方公布详细配置表/参数/版本信息 | both | confirmed_event | 官方发布配置表或权威媒体报道 | 销售话术称"有XX配置" | 品牌官方 > 垂直媒体 | model_watch 窄（仅配置表），brand_watch 含版本信息 |
| `price_release` | 售价公布 | 官方单独公布售价或价格带（非上市场合） | both | confirmed_event | 官方发布或多权威媒体确认 | 论坛流传价格截图 | 品牌官方 > 垂直媒体 | 区别于 launch（上市同时出价格） |
| `delivery_start` | 交付启动/爬坡 | 新车开始交付用户，或明显进入交付爬坡阶段 | both | confirmed_event | 交付仪式报道或官方交付数据 | 个别用户称已提车无官方确认 | 品牌官方 > 垂直媒体 | model_watch 含交付破万/第X台下线，brand_watch 仅交付仪式 |
| `benefit_adjustment` | 购车权益调整 | 限时购车权益、金融方案、置换补贴、保险补贴变化 | both | both_possible | 官方公布权益方案 | 经销商宣传"内部权益""门店额外补贴" | 品牌官方 > 垂直媒体 > 经销商 | model_watch 有独立 `official_rights_update` 子类，合并至此 |
| `official_price_change` | 官方价格调整 | 官方宣布降价、涨价、限时价 | both | confirmed_event | 官方公告或多权威媒体确认 | 经销商降价促销未获官方确认 | 品牌官方 > 垂直媒体 | 两个模板定义一致 |

**合并说明**：

- model_watch 的 `official_rights_update`（权益变化）与 brand_watch 的 `benefit_adjustment` 本质相同，合并为 `benefit_adjustment`，通过子字段 `rights_action: extend/add/reduce/expire` 区分
- model_watch 的 `benefit_adjustment` 原定义为"限时购车权益、金融方案调整"，brand_watch 同名字段定义更宽（含置换/保险），取并集

## 4. model_watch only event types

以下 1 类事件只出现在「LS8 竞品车型动态追踪」中，不适合纳入品牌级监控。

| event_type_id | event_type_cn | definition | 为何不适合 brand_watch |
|---|---|---|---|
| `facelift_launch` | 年度改款/中期改款上市 | 现有车型年度改款或中期改款上市 | 改款是车型生命周期事件，品牌级监控关注的是新车上市而非改款节奏；改款信息通常被品牌级 launch 覆盖 |

## 5. brand_watch only event types

以下 8 类事件只出现在「重点关注品牌每日营销事件监控」中，不适合纳入车型级监控。

| event_type_id | event_type_cn | definition | 为何不适合 model_watch |
|---|---|---|---|
| `brand_campaign` | 品牌传播战役 | 品牌片、广告片、品牌主张更新、品牌焕新 | 车型级监控关注销售动作，品牌传播不直接对应车型销售 |
| `sales_milestone` | 销量/订单里程碑 | 销量、交付量、订单破万、大定、锁单战报 | 车型级已有 delivery_start，订单数据通常品牌整体发布 |
| `production_milestone` | 产能里程碑 | 下线、量产、第X台、产能爬坡 | 车型级更关注交付而非产能 |
| `technology_release` | 技术传播 | 智驾、电池、平台、座舱、补能等技术发布 | 技术传播是品牌级能力，不绑定单一车型 |
| `channel_campaign` | 渠道活动 | 门店、试驾、巡展、城市活动、商超展 | 用户运营动作，不生成可追踪的车型级竞品事件 |
| `user_event` | 用户活动 | 车主活动、用户大会、粉丝节、车友会 | 用户运营动作，不生成车型级竞品事件 |
| `partnership` | 联名/代言/合作 | 代言人、联名款、跨界合作、体育/娱乐赞助 | 品牌级营销，不绑定单一车型 |
| `executive_voice` | 高管发声 | 董事长/CEO/高管直播、访谈、社媒表态 | 高管言论通常涉及品牌战略而非车型细节 |
| `public_opinion` | 舆情事件 | 争议、投诉、事故、公关回应、声明 | 舆情管理是品牌级能力，车型不单独处理 |

## 6. 共性 source taxonomy

以下信源在两个模板中共用。按信任层级分组。

### Tier 1: 官方源

| source_type_id | source_type_cn | examples | trust_level | can_confirm_event | best_for | limitations | recommended_usage |
|---|---|---|---|---|---|---|---|
| `official_website` | 品牌/车型官网 | immotors.com, nio.cn, xiaopeng.com | tier_1_official | yes | 售价、配置、权益官方确认 | 更新频率低，可能滞后 | 作为其他来源的验证锚点 |
| `official_app` | 品牌官方App/社区 | 智己App, 蔚来App, 理想App | tier_1_official | yes | 实时推送品牌动作、用户活动、交付动态 | 需登录；非公开可查时需二次源验证 | 强信号源，但需注意是否仅限内部可见 |
| `official_social` | 官方社媒账号 | 品牌微博、微信公众号、视频号、抖音号 | tier_1_official | yes | 发布会预告、权益公告、品牌片首发、直播预告 | 营销内容为主，可能夸大或模糊 | 发布会、品牌campaign、高管直播的首发源 |
| `official_newsroom` | 官方新闻中心/新闻稿 | brand.newsroom.com | tier_1_official | yes | 正式价格、上市、重大合作等高度结构化信息 | 内容正式但时效性可能弱于社媒 | 价格/上市/合作的权威确认源 |

### Tier 2: 垂直汽车媒体

| source_type_id | source_type_cn | examples | trust_level | can_confirm_event | best_for | limitations | recommended_usage |
|---|---|---|---|---|---|---|---|
| `vertical_auto_media` | 汽车垂直媒体 | 汽车之家, 懂车帝, 易车, 新出行, 第一电动, 盖世汽车 | tier_2_authoritative_media | yes（需交叉验证） | 车型报道、上市新闻、配置解读、价格报道 | 部分内容为转载或厂商通稿 | 主力发现源，单源不得确认正式事件，需2家以上交叉验证 |
| `vertical_industry_media` | 行业媒体 | 盖世汽车, 网通社, 太平洋汽车, 有驾, 车东西 | tier_2_authoritative_media | with_cross_validation | 供应链、产能、技术细节 | 权威性略低于主流垂直媒体 | 作为补充交叉验证源 |

### Tier 3: 科技/财经/商业媒体

| source_type_id | source_type_cn | examples | trust_level | can_confirm_event | best_for | limitations | recommended_usage |
|---|---|---|---|---|---|---|---|
| `tech_biz_media` | 科技/财经/商业媒体 | 晚点Auto, 36氪, 虎嗅, 财经汽车, 经济观察报, 界面新闻, 澎湃新闻 | tier_3_industry_media | with_cross_validation | 独家报道、深度分析、战略解读、内幕消息 | 独家信息需警惕来源可靠性；转载需溯源 | 独家报道作为 discovery signal，交叉验证后可升级 |
| `auto_channel_portal` | 门户汽车频道 | 新浪汽车, 腾讯汽车, 网易汽车 | tier_3_industry_media | with_cross_validation | 常规车型报道、行业新闻整合 | 多为转载，原创比例低 | 作为信息扩散确认而非发现源 |

### Tier 4: 社交信号

| source_type_id | source_type_cn | examples | trust_level | can_confirm_event | best_for | limitations | recommended_usage |
|---|---|---|---|---|---|---|---|
| `social_platform` | 社交平台 | 微博热搜、小红书种草、抖音短视频、B站评测、知乎讨论 | tier_4_social_signal | no | 传播热度、用户口碑、舆情扩散、弱信号发现 | 无法确认事实；易被操控 | 仅作为 weak_signal，不得单独确认正式事件 |
| `dealer_channel` | 经销商渠道 | 门店销售朋友圈、经销商公众号、汽车报价平台 | tier_4_social_signal | no | 价格松动信号、区域促销、库存状态 | 非官方口径；区域性或个别门店行为 | 仅作为 weak_signal，除非多城市经销商信息一致且有媒体交叉验证 |
| `forum_community` | 论坛/社区 | 车友群、品牌社区、懂车帝车友圈 | tier_4_social_signal | no | 用户反馈、交付进度、实际体验、早期爆料 | 无法验证真实性；样本偏差 | 仅作为 weak_signal，不可用于正式事件 |

## 7. model_watch preferred sources

model_watch 侧重**销售动作的快速发现与确认**，优先使用垂直汽车媒体 + 品牌官方源组合。

| 使用层级 | source 类型 | 角色 |
|---|---|---|
| 主力发现 | 垂直汽车媒体（汽车之家、懂车帝、易车、新出行、第一电动、盖世汽车） | 每日扫网发现销售动作 |
| 验证层 | 品牌官方源 | 验证价格/权益/交付信息 |
| 补充层 | 科技/财经媒体（晚点Auto、36氪、虎嗅） | 独家报道发现 |
| 弱信号层 | 经销商/社区/社交平台 | 仅作为 weak_signal |

model_watch **不优先使用**：品牌传播阵地、小红书、B站、用户活动报道等，这些对销售动作发现帮助有限。

## 8. brand_watch preferred sources

brand_watch 侧重**品牌营销动作的全面覆盖**，品牌官方源 + 社交信号的重要性提升。

| 使用层级 | source 类型 | 角色 |
|---|---|---|
| 主力发现 | 品牌官方源（官网、App、社媒、新闻中心） | 品牌campaign、发布会、权益、高管发声 |
| 辅助发现 | 垂直汽车媒体 | 车型相关动作的媒体报道 |
| 深度层 | 科技/财经/商业媒体 | 品牌战略、独家报道、行业分析 |
| 传播层 | 社交平台（微博、小红书、抖音、B站、知乎） | 传播效果评估、舆情监控 |
| 弱信号层 | 经销商渠道、论坛/社区 | 区域信号、用户反馈 |

brand_watch **更依赖**官方社媒源（比 model_watch 多出微博、微信公众号、视频号/抖音号的系统性监控）。

## 9. 事件确认规则

### 正式事件确认条件（两个模板共用）

满足以下至少一项，可进入正式事件：

1. 官方发布或官方账号确认
2. 权威汽车媒体明确报道
3. 多家媒体交叉验证
4. 明确包含时间、品牌/车型、动作和结果信息
5. 对竞争格局有实际业务意义

### 必须降级为 weak_signal 的情况

以下情况不得进入正式事件：

1. 只有经销商口径
2. 只有论坛/社区/自媒体爆料
3. 只有"预计""或将""有望""疑似"等不确定措辞
4. 只有旧新闻二次传播（无新信息）
5. 无明确日期
6. 不能确认是否为官方行为
7. 车型/品牌/动作/对象存在歧义
8. 高管/KOL 的社交平台非正式表达，未形成品牌动作（brand_watch 独有）

## 10. 后续配置化建议

### event_types 配置化

建议将 shared event types（9 类）和各自的专属 event types（model_watch 1 类 + brand_watch 9 类）抽离为独立 JSON 配置：

- `configs/event_types.common.json`：共享事件类型
- `configs/event_types.model_watch.json`：车型监控专属
- `configs/event_types.brand_watch.json`：品牌监控专属

每个 event_type 条目应包含：

```json
{
  "event_type_id": "launch",
  "event_type_cn": "新车正式上市",
  "definition": "新车正式上市，公布全系售价和配置",
  "applies_to": "both",
  "confirmation_level": "confirmed_event",
  "search_keywords": ["上市", "正式上市", "售价公布"],
  "source_priority": ["official_website", "official_social", "vertical_auto_media"],
  "weak_signal_keywords": ["即将上市", "有望", "预计售价"]
}
```

### source_tiers 配置化

将 5 层信源体系抽离为独立 JSON 配置：

- `configs/source_tiers.common.json`：共享信源分级

每个 source_type 条目应包含：

```json
{
  "source_type_id": "vertical_auto_media",
  "source_type_cn": "汽车垂直媒体",
  "examples": ["汽车之家", "懂车帝", "易车"],
  "trust_level": "tier_2_authoritative_media",
  "can_confirm_event": "with_cross_validation",
  "model_watch_weight": "primary",
  "brand_watch_weight": "secondary",
  "weak_signal_only": false
}
```

### 下一步建议

1. 将本报告的 event/source taxonomy 转化为 JSON schema（event_types 和 source_tiers）
2. 在 validator 层增加 event_type 合法性校验（基于配置而非硬编码）
3. 在 Prompt 中引入参数化引用（`{{event_types}}`、`{{source_tiers}}`），从配置动态注入
4. 将 model_watch 和 brand_watch 的 Prompt 中事件枚举段替换为配置引用
5. 评估是否需要增加 `event_sub_type` 字段（如 benefit_adjustment 下细分 extend/add/reduce/expire）

> 注意：上述建议涉及 schema/validator/Prompt 改造，属于后续阶段工作，不在本轮执行范围内。
