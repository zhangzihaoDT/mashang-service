# ChatGPT Plan: 竞品事件 48h 简报

> 将此 Plan 复制到 ChatGPT Plan（或将以下内容粘贴到 ChatGPT）并运行。
> 替换所有 `{{ 占位符 }}` 为实际参数。
> 本 Plan 在 daily_radar 发现重要事件后触发。

---

## 任务

作为汽车行业竞品情报分析师，{{ event_model }} 发生了 {{ event_type }} 事件，请收集该事件的完整信息，生成结构化简报。

## 事件信息

| 维度 | 值 |
|------|----|
| 事件品牌 | {{ event_brand }} |
| 事件车型 | {{ event_model }} |
| 事件类型 | {{ event_type }} |
| 事件日期 | {{ event_date }}（已知/待核实） |
| 触发来源 | {{ trigger_source }}（例如：daily_radar 发现/人工上报/MIIT 信号） |

## 信源优先级

| 层级 | 类型 | 可信度 | 使用规则 |
|------|------|--------|----------|
| Tier 1 | 官方（官网/App/官微/发布会直播） | 高 | 事实依据 |
| Tier 2 | 垂媒（汽车之家/懂车帝/36氪/虎嗅/第一电动/新出行/易车） | 中 | 交叉验证 |
| Tier 3 | 社交（小红书/微博非官方/论坛/抖音/知乎） | 低 | 舆情参考 |

## 检索模块

请搜索以下 6 个模块的信息：

### 模块 1: 事件确认
- 活动正式名称、具体日期、举办城市/地点
- 官方公告/新闻稿原文链接

### 模块 2: 价格与权益
- 各版本售价/预售价、定金金额及膨胀政策
- 限时权益包内容、金融方案、置换补贴
- 保险/充电等附加权益

### 模块 3: 产品定位与核心卖点
- 车型级别、车身尺寸、续航里程/能源类型
- 官方宣传的重点卖点（Top 3-5）
- 智驾方案（硬件+功能）、目标用户描述

### 模块 4: 竞品对标
- 发布会中官方提及的竞品车型
- 媒体横向对比评测的关键结论
- 价格带定位、差异化优势

### 模块 5: 媒体与用户反馈
- 首批媒体评测结论、评分（如有）
- 论坛/社区讨论热度与用户反馈倾向
- 订单量/预订量数据（如有官宣）

### 模块 6: 对我方影响
- 与我方 {{ our_model }} 的竞争重叠度
- 威胁等级（1-5）及理由
- 建议应对动作

## 输出格式

### 1. JSON 输出

```json
{
  "event": {
    "brand": "{{ event_brand }}",
    "model": "{{ event_model }}",
    "event_type": "{{ event_type }}",
    "event_date": "confirmed_date | inferred_date",
    "event_name": "",
    "location": "",
    "official_announcement_url": ""
  },
  "price_and_benefits": {
    "msrp": {"value": "", "confirmed": true|false, "source_url": ""},
    "deposit": {"value": "", "confirmed": true|false, "source_url": ""},
    "limited_offer": {"items": [], "source_url": ""},
    "finance_plan": {"description": "", "source_url": ""}
  },
  "product_positioning": {
    "segment": "",
    "size": "",
    "range": "",
    "key_selling_points": [],
    "autonomous_driving": "",
    "target_users": ""
  },
  "competitive_landscape": {
    "official_benchmark": [],
    "media_comparison": [],
    "price_positioning": "",
    "differentiation": []
  },
  "media_and_user_response": {
    "media_reviews": [],
    "user_sentiment": "",
    "order_hotness": ""
  },
  "impact_on_our_model": {
    "overlap_degree": "high|medium|low",
    "threat_level": 1-5,
    "reasoning": "",
    "recommended_actions": []
  },
  "evidence_quality": {
    "tier1_count": 0,
    "tier2_count": 0,
    "tier3_count": 0,
    "unconfirmed_count": 0
  }
}
```

> **source_url 格式要求**：所有 source_url 字段必须为纯 URL 字符串（如 `https://example.com/page`），不允许 Markdown 链接格式（如 `[text](url)`），不允许 `[url](url)` 嵌套，不允许将多个 URL 拼接在同一字符串中。source_tier / source_name 必须单独字段填写，不要内嵌在 URL 中。

### 2. Markdown 简报

```markdown
# {{ event_model }} {{ event_type }} 48h 简报

## 1. 事件概要
- 事件名称：{name}
- 日期：{date}（{{ confirmed / inferred }}）
- 地点：{location}
- 来源：[Tier 1] 名称: URL

## 2. 价格与权益
- 售价：{price}
- 权益：{benefits}
- 金融方案：{finance}

## 3. 产品核心信息
- 级别/尺寸：{segment}
- 续航/能源：{range}
- 核心卖点：{key points}
- 智驾：{adas}

## 4. 竞品对比
- 官方对标：{benchmarks}
- 媒体对比：{comparisons}

## 5. 舆论热度
- 媒体评价：{reviews}
- 用户反馈：{feedback}
- 订单热度：{orders}

## 6. 对我方影响
- 重叠度：{overlap}
- 威胁等级：{level}/5
- 建议动作：{actions}

## 7. 证据质量
| 层级 | 数量 | 可信度 |
|------|------|--------|
| Tier 1 官方 | {n} | 高 |
| Tier 2 垂媒 | {n} | 中 |
| Tier 3 社交 | {n} | 低 |
| 未确认 | {n} | 待验证 |
```

## 约束条件

1. 每条结论必须附带来源 URL，格式 `[Tier 层级] 来源名称: URL`
2. **source_url 必须是纯 URL 字符串（如 `https://example.com/page`）**；不允许 Markdown 链接格式 `[text](url)`，不允许 `[url](url)`，不允许多个 URL 写在同一字段中
3. 区分 confirmed_fact / cross_validated / single_source / rumor
4. Tier 1 与 Tier 2 信息冲突时以 Tier 1 为准
5. Tier 3 信息不得作为事实结论依据
6. 价格信息标注是官方价、媒体预测还是用户传闻
7. 某模块无信息时写 "未获取到"，不可编造
8. 必须列出 missing_evidence（无法获取但影响判断的关键信息项）
9. 必须给出是否需要进入 72h follow-up 的判断（escalate / monitor / close）
