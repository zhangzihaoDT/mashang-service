# Search Intent Compiler — 用户需求转译规则

## 输入

- `user_request`: 用户自然语言需求
- `monitor_date`: 当前监控日期
- `brand_watchlist`: `configs/priority_brand_watchlist.yaml` — 24 个品牌级监控对象的 catalog/brand/alias/models
- `model_watchlist`: `configs/ls8_competitor_watchlist.yaml` — 10 款 LS8 竞品车型的 brand/model/alias
- `event_types`: `configs/event_types.yaml` — 19 类事件的 event_type_id/搜索关键词
- `source_tiers`: `configs/source_tiers.yaml` — 5 层信源分级的 tier 定义与用途

## 输出

结构化 `search_intent` JSON，包含 mode / targets / time_window / event_scope / source_strategy。

## 规则

### 1. mode 判断

| 用户表达 | mode |
|---|---|
| 品牌名 + 最近/近期 + 动作/消息/营销/事件 | `brand_watch` |
| 车型名 + 最近/近期 + 动作/权益/价格/上市/交付 | `model_watch` |
| 明确说"品牌" | `brand_watch` |
| 明确说"车型"或具体车型名 | `model_watch` |
| 同时包含品牌和车型 | 优先 `model_watch`，但保留 brand context |
| 无法判断 | `unknown`，输出 ambiguity |

### 2. target 识别

从 `priority_brand_watchlist.yaml` 和 `ls8_competitor_watchlist.yaml` 中匹配：

- 先按车型名（含品牌）匹配，最长子串优先
- 再按品牌名匹配
- 支持中文名和英文 alias
- 支持子品牌（鸿蒙智行→问界/智界/享界/尊界/尚界）
- 未匹配的目标标记为 `ad_hoc_user_request`

### 3. 时间窗口识别

| 用户表达 | 解析 |
|---|---|
| 最近 N 天 | `days=N` |
| 近一周/本周 | `days=7` |
| 最近 24/48 小时 | `hours=24/48` |
| 今天/今日 | `days=0` |
| 昨天/昨日 | `days=1` |
| 过去一个月 | `days=30` |
| 未指定 | 默认 `days=1`, fallback `days=7` |

### 4. event_scope 识别

| 用户表达 | event_type_ids |
|---|---|
| 有什么动作/消息/事件 | 全量 19 类 |
| 价格/降价/售价 | `official_price_change` |
| 权益/优惠/金融/置换 | `benefit_adjustment` |
| 上市 | `launch` |
| 预售 | `presale` |
| 交付 | `delivery_start`, `order_milestone` |
| 订单/大定/锁单/战报 | `order_milestone`, `sales_milestone` |
| 发布会/亮相 | `launch_event`, `debut` |
| 营销/传播/campaign | `brand_campaign` |
| 活动/试驾 | `channel_campaign`, `user_event` |
| 爆料/路透/风声 | `rumor_or_leak` |
| 技术/智驾/电池 | `technology_release` |

### 5. source_strategy 识别

| 用户表达 | 策略 |
|---|---|
| 默认（未指定） | 官方优先 + 媒体交叉验证 + 社交弱信号 |
| 只看官方 | 仅 tier_1 official |
| 销售端风声/爆料 | 放开 tier_4/tier_5，全部 as discovery only |
| 媒体怎么说 | 提高 tier_2/tier_3 权重 |
| 传播热度 | 加入社交平台和内容平台关键词 |

### 6. ambiguity 处理

以下情况输出 ambiguity：

- mode 无法判断
- 未识别到目标品牌/车型
- 时间窗口模糊且无法推断
- 目标同时存在于品牌和车型 watchlist 且有歧义

## 示例

### 示例 1: brand_watch 开放式

输入：
> 看看极氪最近 7 天都有什么动作

输出：
- mode: brand_watch
- targets: [极氪, brand, high confidence]
- time_window: 最近 7 天 (start/end 明确日期)
- event_scope: 全量相关事件（19 类）
- source_strategy: 默认（官方优先 + 媒体 + 社交弱信号）

### 示例 2: model_watch 指定事件

输入：
> 看看问界 M7 最近 7 天权益和价格有什么变化

输出：
- mode: model_watch
- targets: [问界 M7, model, high confidence (in ls8_watchlist)]
- event_scope: benefit_adjustment, official_price_change
- source_strategy: 默认

### 示例 3: brand_watch 官方源限定

输入：
> 只看官方，看看蔚来 ES8 今天有没有新权益

输出：
- mode: model_watch
- source_strategy: official_first=true, include_media=false, include_social=false
- time_window: today

### 示例 4: brand_watch 销售风声

输入：
> 看看理想最近销售端有没有风声

输出：
- mode: brand_watch
- source_strategy: include_social_signals=true, allow_unverified=true, social_signals_as_discovery_only=true
- event_scope: rumor_or_leak, benefit_adjustment, official_price_change
