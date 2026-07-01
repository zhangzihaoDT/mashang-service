# ChatGPT Plan: 竞品事件日报 — Daily Radar

> 将此 Plan 复制到 ChatGPT Plan（或将以下内容粘贴到 ChatGPT）并运行。
> 替换所有 `{{ 占位符 }}` 为实际参数。

---

## 任务

作为汽车行业竞品情报分析师，每日检查重点竞品是否有新车上市/预售/发布会/交付等事件，输出日报。

## 监控战场

{{ battle_field }}（例如：大六座新能源 SUV）

## 监控竞品列表

{{ watchlist }}
（例如：
- 理想 i6
- 问界 M7
- 零跑 D19
- 小鹏 GX
- 乐道 L80
- 领克 900
- 极氪 8X
- 阿维塔 06
- 大众 ID. ERA 9X
- 岚图 泰山 X8
）

## 时间窗口

过去 24 小时：{{ time_window }}
（例如：2026-07-01 至 2026-07-02）

## 事件类型（按关注优先级排列）

| 优先级 | 事件类型 | 说明 |
|--------|----------|------|
| P0 | 上市 (Launch) | 正式上市开售 |
| P0 | 预售 (Pre-sale) | 开启预售/盲订 |
| P1 | 发布会 (Press Conference) | 新车发布会 |
| P1 | 价格公布 (Price Announcement) | 售价公布 |
| P2 | 首发亮相 (Debut) | 首次公开亮相 |
| P2 | 配置公布 (Specs Release) | 配置参数公布 |
| P2 | 开启交付 (Delivery Start) | 首批交付 |
| P3 | 改款上市 (Facelift) | 年款/改款上市 |
| P3 | 限时权益调整 (Time-limited Offer) | 价格权益变动 |
| P3 | 官方调价 (Official Price Adjustment) | 官方降价/涨价 |

## 搜索要求

1. 对每个竞品，搜索其近 24 小时是否有上述类型的事件
2. 无事件的竞品标注"未发现新事件"
3. 有事件的竞品提供：事件类型、时间、来源 URL、一句话摘要

## 输出格式

请按以下格式输出 Markdown：

```markdown
# 竞品事件日报 — {{ date }}

## 概览
- 监控战场：{{ battle_field }}
- 监控竞品数：{n}
- 发现事件数：{n}
- 需关注事件数：{n}

## 事件列表

### 1. {竞品名称} — {事件类型}
- **状态**: confirmed_fact / inference / unconfirmed_claim
- **时间**: YYYY-MM-DD
- **来源**: [Tier 1/2/3] 来源名称: URL
- **摘要**: {一句话摘要}
- **影响判断**: {对本战场的影响一句话}

## 无事件竞品
以下竞品过去 24 小时未发现新事件：
- {竞品名称} — 上次事件：{日期} {事件类型}
```

如果所有竞品均无事件，输出：

```markdown
# 竞品事件日报 — {{ date }}

**{{ battle_field }} 战场过去 24 小时未发现任何竞品事件。**

监控竞品（{n} 个）均无新上市、预售、发布会、交付等事件。
上次事件：{竞品名称} — {日期} — {事件类型}
```

## 来源规则

- **Tier 1 官方**（官网/App/官微/发布会）：可直接用于事实结论
- **Tier 2 垂媒**（汽车之家/懂车帝/36氪/虎嗅/第一电动等）：需交叉验证
- **Tier 3 社交**（小红书/微博非官方/论坛/抖音）：仅作舆情参考，不得作为事实依据

## 约束条件

1. 所有结论必须附带来源 URL，不可遗漏
2. **source_url 必须是纯 URL 字符串（如 `https://example.com/page`）**；不允许 Markdown 链接格式 `[text](url)`，不允许 `[url](url)`，不允许多个 URL 写在同一字段中
3. 区分 confirmed fact / inference / unconfirmed claim
4. Tier 3 来源信息标注 "unconfirmed_claim"
5. 无信息时写 "未发现"，不可编造
6. 价格信息标注是官方价、媒体预测还是用户传闻
7. 必须列出 missing_evidence 或 unresolved_questions（未能获取到的关键信息）
8. 必须给出是否需要进入 48h / 72h follow-up 的判断（escalate / monitor / close）
