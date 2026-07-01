# Auto Launch 情报检索任务

## 任务角色

你是一个汽车行业竞品情报分析师。请基于以下检索范围和搜索任务，在公开网络中收集信息。所有结论必须标注来源，区分"官方确认"、"媒体报道"、"用户传闻"三个可信度层级。

## 业务角色

| 角色 | 品牌 | 车型 | 说明 |
|------|------|------|------|
| **事件车型（event_model）** | 乐道 | L80 | 本次发生上市/预售/发布会等事件的车型 |
| **本品车型（our_model）** | 智己 | LS8 | 我方被影响车型 |
| **竞争战场** | — | large_six_seat_suv | 同战场竞品背景 |

本报告的核心问题是：**event_model（乐道 L80）本次事件，对 our_model（智己 LS8）造成什么影响？**

## 业务输入：目标车型与竞品范围

| 维度 | 值 |
|------|----|
| 目标品牌 | 乐道 |
| 目标车型 | L80 |
| 目标车型竞争分组（group_id） | large_six_seat_suv |
| target_group 来源 | target_profile |
| target_group 已解析 | 是 |
| battle_field_id 字段可用 | 是 |
| ecosystem_group（品牌阵营）可用 | 是 |
| group 字段可用（legacy） | 否 |
| 竞品匹配主字段 | battle_field_id |
| group taxonomy 归一化 | 是 |
| 同战场竞品数量 | 5 |
| 跨战场补充数量 | 0 |
| 竞品来源 | watchlist |
| watchlist 文件路径 | /Users/zihao_/Documents/github/mashang-service/mashang_workspace/configs/ls8_competitor_watchlist.csv |
| active 过滤 | 是 |
| group 同组优先 | 是 |
| 退化规则 | 无 |
| 推导规则 | 优先选择同战场（匹配字段=battle_field_id）；仅保留 priority=high 的竞品 |
| 推导说明 | target_group=large_six_seat_suv（来源=target_profile）；全部 5 个竞品均来自同战场（large_six_seat_suv） |



### 竞品列表

| # | 品牌 | 车型 | battle_field_id | ecosystem_group | 优先级 |
|---|------|------|----------------|----------------|--------|
| 1 | 小鹏 | 小鹏 GX | large_six_seat_suv | new_force_suv | high |
| 2 | 岚图 | 岚图 泰山 X8 PHEV | large_six_seat_suv | central_soe_suv | high |
| 3 | 理想 | 理想 i6 | large_six_seat_suv | new_force_suv | high |
| 4 | 问界 | 问界 M7 | large_six_seat_suv | huawei_ecosystem_suv | high |
| 5 | 零跑 | 零跑 D19 | large_six_seat_suv | new_force_suv | high |

## 检索范围

| 维度 | 值 |
|------|----|
| 事件车型品牌 | 乐道 |
| 事件车型 | L80 |
| 事件类型 | 上市（launch） |
| 时间窗口 | 2026-06-24 至 2026-06-26 |
| 本品品牌 | 智己 |
| 本品车型 | LS8 |
| 关注竞品（战场背景） | 小鹏 GX, 岚图 泰山 X8 PHEV, 理想 i6, 问界 M7, 零跑 D19 |

## 信源优先级

按以下优先级筛选信息（高优先级来源的结论可直接使用，低优先级来源需标注为"待验证"）：

| 优先级 | 信源类型 | 权重 | 代表来源 | 证据级别 |
|--------|---------|------|---------|----------|
| **Tier 1** | 官方一手信息 | 1.0 | 品牌官网、官方App、官方微博、官方微信公众号、发布会直播 | ✅ 高可信度，可直接用于事实结论 |
| **Tier 2** | 行业媒体与垂媒 | 0.7 | 汽车之家、懂车帝、易车、新出行、36氪、虎嗅、第一电动 | ⚠️ 中可信度，需交叉验证 |
| **Tier 3** | 社交平台与用户 | 0.4 | 小红书、知乎、微博(非官方)、车主论坛、抖音 | 🔍 低可信度，仅作舆情参考 |

## 事件类型定义

上市（新车正式上市，公布全系售价和配置）
  搜索关键词：上市、正式上市、售价公布、上市发布

## 六大检索模块

### 模块1：事件确认

**目标**：确认该车型的事件基本信息。

| 检索项 | 说明 | 预期来源 |
|--------|------|----------|
| 事件名称 | 官方活动的正式名称 | Tier 1 官方公告 |
| 日期确认 | 事件发生的具体日期和时间 | Tier 1 官方发布 |
| 举办地点 | 发布会/活动举办城市 | Tier 1 + Tier 2 |
| 官方公告 | 官方新闻稿或公告原文链接 | Tier 1 |
| 核心宣传语 | 官方使用的 Slogan 或主题词 | Tier 1 |

### 模块2：价格与权益

**目标**：收集价格信息和购车权益。

| 检索项 | 说明 | 预期来源 |
|--------|------|----------|
| 售价 | 各版本的正式售价或预售价 | Tier 1 官方发布 |
| 定金 | 预售定金金额和膨胀政策 | Tier 1 官方App/小程序 |
| 限时权益 | 上市/预售限时权益包 | Tier 1 |
| 金融方案 | 分期/贷款/租赁方案 | Tier 1 + Tier 2 |
| 置换补贴 | 本品/他品置换政策 | Tier 1 |
| 保险/充电权益 | 附赠的保险或充电权益 | Tier 1 |

### 模块3：产品定位与核心卖点

**目标**：理解该车型的产品定位和差异化卖点。

| 检索项 | 说明 | 预期来源 |
|--------|------|----------|
| 车型级别 | 中大型SUV/中型轿车等 | Tier 1 + Tier 2 |
| 车身尺寸 | 长/宽/高/轴距 | Tier 1 + Tier 2 |
| 续航里程 | CLTC续航或能源类型 | Tier 1 + Tier 2 |
| 核心卖点 | 官方宣传的Top 3-5卖点 | Tier 1 |
| 智驾方案 | 辅助驾驶硬件和功能 | Tier 1 + Tier 2 |
| 目标用户 | 官方描述的目标人群 | Tier 1 |
| 定位话术 | 官方定位语句 | Tier 1 |

### 模块4：竞品对标

**目标**：分析该车型与竞品的对比。

| 检索项 | 说明 | 预期来源 |
|--------|------|----------|
| 官方对标 | 官方发布会中提及的竞品 | Tier 1 |
| 媒体对比 | 媒体做的横向对比评测 | Tier 2 |
| 价格对标 | 与竞品的价格带对比 | Tier 2 |
| 参数对标 | 与竞品的核心参数对比 | Tier 2 |
| 差异化优势 | 媒体/官方认为该车的差异化优势 | Tier 1 + Tier 2 |

### 模块5：媒体与用户反馈

**目标**：收集媒体评价和用户舆情。

| 检索项 | 说明 | 预期来源 |
|--------|------|----------|
| 媒体首测评价 | 首批媒体评测的关键结论 | Tier 2 |
| 媒体评分 | 如果有点评分数或推荐指数 | Tier 2 |
| 论坛热度 | 车友圈/论坛的讨论热度 | Tier 3 |
| 用户订单情报 | 订单量（如有官宣）或用户反馈 | Tier 1 + Tier 3 |
| 社交媒体讨论 | 微博/小红书上的用户讨论倾向 | Tier 3 |

### 模块6：对我方车型影响判断

**目标**：判断 **event_model（乐道 L80）** 本次事件对 **our_model（智己 LS8）** 的潜在影响，并结合 competitor_context 判断战场压力。

| 检索项 | 说明 | 预期来源 |
|--------|------|----------|
| 目标用户重叠 | event_model 与 our_model 的用户画像重叠度 | 综合判断 |
| 价格带重叠 | event_model 与 our_model 的价格区间重叠 | 综合判断 |
| 产品形态重叠 | 车身形式/级别/能源形式重叠 | 综合判断 |
| 战场压力 | 结合 competitor_context 判断 event_model 加入后战场竞争强度变化 | 综合判断 |
| 威胁评估 | 高/中/低威胁判断 | 综合判断 |
| 建议应对 | 是否需要调整我方产品/营销策略 | 综合判断 |

## 输出格式

### 1. 结构化 JSON 证据

请按以下 JSON schema 组织检索到的证据，每个模块一个子对象，所有结论必须包含来源URL和置信度标记。

```json
{
  "schema_version": "auto_launch_evidence.v0.1",
  "description": "Auto Launch 搜索结果证据 schema — 用于结构化存储检索到的上市/预售/发布会情报",
  "top_level_fields": {
    "brand": {
      "type": "string",
      "description": "品牌名",
      "required": true
    },
    "model": {
      "type": "string",
      "description": "车型名",
      "required": true
    },
    "event_type": {
      "type": "string",
      "description": "事件类型",
      "required": true,
      "enum": [
        "launch",
        "presale",
        "launch_event",
        "debut",
        "config_release",
        "price_release",
        "delivery_start",
        "facelift_launch",
        "权益_adjustment",
        "official_price_change"
      ]
    },
    "event_date": {
      "type": "string",
      "description": "事件日期",
      "required": true,
      "format": "date"
    },
    "search_time_window": {
      "type": "object",
      "description": "搜索时间窗口",
      "required": true,
      "properties": {
        "start": {
          "type": "string",
          "format": "date"
        },
        "end": {
          "type": "string",
          "format": "date"
        }
      }
    },
    "event_confirmation": {
      "$ref": "#/definitions/event_confirmation"
    },
    "pricing_and_权益": {
      "$ref": "#/definitions/pricing_and_权益"
    },
    "product_positioning": {
      "$ref": "#/definitions/product_positioning"
    },
    "competitive_analysis": {
      "$ref": "#/definitions/competitive_analysis"
    },
    "media_and_user_feedback": {
      "$ref": "#/definitions/media_and_user_feedback"
    },
    "impact_assessment": {
      "$ref": "#/definitions/impact_assessment"
    },
    "evidence_trail": {
      "$ref": "#/definitions/evidence_trail"
    }
  },
  "definitions": {
    "event_confirmation": {
      "type": "object",
      "description": "模块1: 事件确认",
      "properties": {
        "event_name": {
          "type": "string",
          "description": "事件官方名称"
        },
        "event_date_confirmed": {
       
```

### 2. Markdown 情报简报

在 JSON 之外，同步输出一份 Markdown 格式的情报简报，结构如下：

```
# {品牌} {车型} {事件类型} 情报简报

## 1. 事件概要
- 事件：{事件名称}
- 日期：{日期}
- 地点：{地点}
- 一句话总结：{}

## 2. 价格与权益
- 售价：{}
- 权益：{}
- 金融方案：{}

## 3. 产品核心信息
- 定位：{}
- 核心卖点：{}
- 关键参数：{}

## 4. 竞品对比
- 官方对标：{}
- 媒体对比结论：{}

## 5. 舆论热度
- 媒体评价：{}
- 用户反馈：{}
- 订单热度：{}

## 6. 对我方影响
- 威胁等级：{}
- 建议动作：{}

## 7. 证据质量
| 来源层级 | 使用数量 | 可信度 |
|----------|---------|--------|
| Tier 1 官方 | {} | 高 |
| Tier 2 媒体 | {} | 中 |
| Tier 3 社交 | {} | 低 |
| 未确认传闻 | {} | 待验证 |
```

### 3. 证据引用规则

1. **每条结论必须附带来源**，格式为 `[来源类型] 来源名称: URL`
2. **区分确认状态**：confirmed（官方可验证）/ cross_validated（多个媒体交叉验证）/ single_source（单一来源）/ rumor（传闻）
3. **Tier 1 和 Tier 2 冲突时，以 Tier 1 为准**
4. **Tier 3 信息不得作为事实结论依据**
5. **所有价格信息必须标注是官方价、媒体预测还是用户传闻**
