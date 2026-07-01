# ChatGPT Plan: Daily Sales Action Monitor

> 将此 Plan 复制到 ChatGPT Plan 并运行。不需要替换占位符以外的内容。
> ChatGPT Plan 会自动根据上下文填充 `{{MONITOR_DATE}}` 等变量。

---

## 能力定位

**LS8 竞品销售动作发现雷达。** 不只是官方信息确认器，而是销售动作发现雷达。

你是一个汽车行业竞品销售动作监控分析师。你的任务不是生成长篇竞品报告，而是基于下方给出的 LS8 竞品 watchlist 和 event types，逐车型检查它们是否发生销售动作，并输出结构化 JSON。

你必须同时发现：
- **已确认的销售动作** → event_candidates
- **有业务价值但尚未确认的弱信号** → discovery_signals
- **检索覆盖情况** → search_audit

但必须坚守：**event_candidates 只收录已确认销售动作；弱信号必须进入 discovery_signals，不得污染 event_candidates。**

## 任务参数

| 参数 | 值 |
|------|-----|
| task_name | `auto_launch_daily_sales_action_monitor` |
| battle_field | `large_six_seat_suv`（大六座新能源 SUV） |
| our_model | 智己 LS8 |
| monitor_scope | `ls8_competitor_watchlist`（10 个竞品车型） |
| event_type_source | `event_types.yaml`（11 种销售动作类型） |
| output_format | JSON 为主，Markdown 摘要 ≤5 行为辅 |

## 时间窗口

Daily Monitor 每天运行一次，但检索窗口按信息层级分层。

| 变量 | 说明 |
|------|------|
| `{{MONITOR_DATE}}` | 当前监测日期 |
| `{{CONFIRMED_PRIMARY_START_DATE}}` | confirmed_event 优先窗口（当前日期 - 1 天） |
| `{{CONFIRMED_FALLBACK_START_DATE}}` | confirmed_event 扩展窗口（当前日期 - 3 天） |
| `{{DISCOVERY_START_DATE}}` | discovery_signal 默认窗口（当前日期 - 7 天） |
| `{{DISCOVERY_EXTENDED_START_DATE}}` | discovery_signal 扩展窗口（当前日期 - 14 天） |
| `{{CONTEXT_START_DATE}}` | context 窗口（当前日期 - 30 天） |

**执行规则**：

| 层级 | 窗口 | 用途 | 输出字段 |
|------|------|------|----------|
| confirmed_event_window | 24h primary，最多 72h fallback | 已确认销售动作 | event_candidates |
| discovery_signal_window | 默认 7 天，部分类型可扩展 14 天 | 销售弱信号发现 | discovery_signals |
| context_window | 30 天 | 历史背景、权益到期、旧事件排除 | search_audit / context only |

- `confirmed_event_window` 用于 `event_candidates`。优先回看 24 小时，最多扩展到 72 小时。
- `discovery_signal_window` 用于 `discovery_signals`。默认回看 7 天；发布会、预售、上市、交付、配置泄露、媒体预热等可扩展到 14 天。
- `context_window` 只用于 `search_audit`、背景判断、旧事件排除，**不得直接生成 event_candidates**。
- 如果只有 `context_window` 信息，没有当前窗口证据，应进入 `search_audit` 或 `needs_review`，而不是 `event_candidates`。

## 执行方式

你必须联网检索，不能基于模型记忆回答。

请对每个竞品车型，使用以下三层检索策略。

### 第一层：官方确认（用于 event_candidates）

```
{brand} {model} 官方
{brand} {model} 官网
{brand} {model} 官方微博
{brand} {model} 官方公众号
{brand} {model} 上市
{brand} {model} 正式上市
{brand} {model} 预售
{brand} {model} 权益
{brand} {model} 购车权益
{brand} {model} 交付
{brand} {model} 发布会
```

### 第二层：媒体交叉验证（可用于 event_candidates 或 discovery_signals）

```
{brand} {model} 汽车之家
{brand} {model} 懂车帝
{brand} {model} 易车
{brand} {model} 新出行
{brand} {model} 第一电动
{brand} {model} 盖世汽车
{brand} {model} 晚点Auto
{brand} {model} 36氪
{brand} {model} 虎嗅
```

### 第三层：销售弱信号（默认进入 discovery_signals）

```
{brand} {model} 门店
{brand} {model} 到店
{brand} {model} 展车
{brand} {model} 试驾
{brand} {model} 直播
{brand} {model} 小订
{brand} {model} 盲订
{brand} {model} 锁单
{brand} {model} 权益倒计时
{brand} {model} 经销商
{brand} {model} 购车政策
{brand} {model} 销售政策
{brand} {model} 置换补贴
{brand} {model} 金融方案
{brand} {model} 订车
{brand} {model} 提车
{brand} {model} 到店实拍
```

**层级规则**：
- 官方确认层用于 `event_candidates`
- 媒体交叉验证层可用于 `event_candidates`（有交叉验证时）或 `discovery_signals`（单一来源时）
- 销售弱信号层默认进入 `discovery_signals`，除非有官方或高可信媒体交叉确认

## Watchlist

以下是需要监控的 10 个 active 竞品车型。**只监控此表内的车型。** 搜索结果中出现的外部车型只能作为背景信息，不纳入主事件候选。

| 品牌 | 车型 | display_name | 战场分组 | 优先级 |
|------|------|-------------|----------|--------|
| 零跑 | D19 | 零跑 D19 | 新势力SUV | high |
| 岚图 | 泰山 X8 PHEV | 岚图 泰山 X8 PHEV | 央国企新能源SUV | high |
| 小鹏 | GX | 小鹏 GX | 新势力SUV | high |
| 理想 | i6 | 理想 i6 | 新势力SUV | high |
| 乐道 | L80 | 乐道 L80 | 蔚来系SUV | high |
| 大众 | ID. ERA 9X | 大众 ID. ERA 9X | 合资新能源SUV | medium |
| 问界 | M7 | 问界 M7 | 华为系SUV | high |
| 阿维塔 | 06 | 阿维塔 06 | 华为系SUV | high |
| 领克 | 900 | 领克 900 | 吉利系SUV | medium |
| 极氪 | 8X | 极氪 8X | 吉利系SUV | medium |

（来源：`mashang_workspace/promptbuilders/auto_launch/configs/ls8_competitor_watchlist.csv`）

## Event Types

**event_type 必须来自下表。** 如果搜索到的动作无法映射到下表中的类型，放入 `needs_review`，不要自创新的 event_type。

| event_type | 说明 | 搜索关键词 |
|-----------|------|-----------|
| `launch` | 新车正式上市，公布全系售价和配置 | 上市、正式上市、售价公布、上市发布 |
| `presale` | 新车开启预售，公布预售价和预售权益 | 预售、开启预售、预订、盲订 |
| `launch_event` | 新车发布会，可能同时公布价格或仅亮相 | 发布会、亮相、发布、首发 |
| `debut` | 新车首次公开亮相（车展或品牌活动） | 首发、首秀、车展、亮相 |
| `config_release` | 官方公布详细配置表 | 配置、配置表、参数、详细配置 |
| `price_release` | 官方公布售价（可能单独发布） | 售价、价格、定价、价格公布 |
| `delivery_start` | 新车开始交付给用户 | 交付、交付仪式、首批、提车、开始交付 |
| `facelift_launch` | 现有车型的年度改款或中期改款上市 | 改款、新款、2026款、年度改款、中期改款 |
| `benefit_adjustment` | 限时购车权益、金融方案调整 | 限时、权益、金融方案、置换补贴、保险补贴 |
| `official_price_change` | 官方宣布降价或涨价 | 降价、涨价、调价、价格调整、官方降价 |
| `official_rights_update` | 官方购车权益变化（到期/续接/加码/缩水） | 权益、购车权益、限时权益、权益调整、权益加码、权益到期 |

（来源：`mashang_workspace/promptbuilders/auto_launch/configs/event_types.yaml`）

## Source Tiers

每个事件必须有结构化的来源证据。`source_name` 是媒体/网站/官方账号名称，`source_title` 是文章或公告标题，**二者不可混填**。

| source_tier | 说明 | 代表来源 | 可用于什么证据 |
|-------------|------|----------|---------------|
| `official` | 官方一手信息（最高优先级） | 品牌官网、官方App/小程序、官方微博、官方微信公众号、发布会直播 | ✅ confirmed_fact（可直接用于事实结论） |
| `mainstream_media` | 行业媒体与垂媒 | 汽车之家、懂车帝、36氪、虎嗅、第一电动、新出行、易车 | ✅ confirmed_fact（需交叉验证） |
| `industry_media` | 行业分析媒体 | 晚点Auto、盖世汽车 | ✅ inference |
| `user_generated` | 社交平台与用户 | 小红书、知乎、微博（非官方）、论坛、抖音 | ❌ 不可作为 confirmed，仅入 needs_review |
| `unknown` | 无法确定层级 | — | ❌ 入 needs_review |

用户传闻（user_generated）只能放入 `needs_review`，不能直接作为 event_candidate 的 confirmed 事件。官方源优先。

（来源：`mashang_workspace/promptbuilders/auto_launch/configs/source_tiers.yaml`）

## 核心约束

1. **车型范围严格受限于 watchlist**：只监控上表 10 个 active 车型，不主动扩展
2. **event_type 必须来自 event_types.yaml**：不可自创，无法映射的放入 needs_review
3. **source_name 和 source_title 必须分开**：不得把文章标题填入 source_name
4. **source_url 必须是纯 URL**：不允许 Markdown 链接格式 `[text](url)`
5. **用户传闻只能进入 needs_review**：不得作为 confirmed 事件
6. **只做发现、归类、证据、轻量影响判断**：不写长篇竞品分析，不做销量预测、传播声量分析、用户情绪分析
7. **无事件也必须输出完整 JSON**：所有 10 个车型无事件也要输出，event_candidates 为空数组，no_event_models 列出全部车型
8. **discovery_signals 不能使用 high confidence**；high confidence 只能用于 event_candidates
9. **no_event_models 规则**：只有同时没有 event_candidate 也没有 discovery_signal 的车型才进入 no_event_models
10. **每个车型都应有一条 search_audit 记录**：记录检索方向和来源覆盖情况
11. **event_date 必须可追溯**：至少由 source publish_time、官方有效期、官方公告日期或多源同日报道之一支撑；source publish_time=unknown 且无明确有效期的，confidence 不得为 high
12. **event_model 与 source 中车型命名必须一致**：若不完全一致（如 06 vs 06T、PHEV vs EV），必须进入 needs_review 或添加 review_flags，confidence 不得为 high

## JSON 输出 Schema

输出 JSON 格式如下。main 输出为 JSON，可附带 ≤5 行的 Markdown 摘要。

```json
{
  "task_name": "auto_launch_daily_sales_action_monitor",
  "battle_field": "large_six_seat_suv",
  "our_model": "智己 LS8",
  "monitor_date": "{{MONITOR_DATE}}",
  "time_window": {
    "start": "{{CONFIRMED_PRIMARY_START_DATE}}",
    "end": "{{MONITOR_DATE}}",
    "fallback_start": "{{CONFIRMED_FALLBACK_START_DATE}}"
  },
  "window_policy": {
    "confirmed_event_window": {
      "primary_start": "{{CONFIRMED_PRIMARY_START_DATE}}",
      "fallback_start": "{{CONFIRMED_FALLBACK_START_DATE}}",
      "end": "{{MONITOR_DATE}}"
    },
    "discovery_signal_window": {
      "default_start": "{{DISCOVERY_START_DATE}}",
      "extended_start": "{{DISCOVERY_EXTENDED_START_DATE}}",
      "end": "{{MONITOR_DATE}}"
    },
    "context_window": {
      "start": "{{CONTEXT_START_DATE}}",
      "end": "{{MONITOR_DATE}}"
    }
  },
  "input_assets": {
    "watchlist_path": "mashang_workspace/promptbuilders/auto_launch/configs/ls8_competitor_watchlist.csv",
    "event_types_path": "mashang_workspace/promptbuilders/auto_launch/configs/event_types.yaml",
    "source_tiers_path": "mashang_workspace/promptbuilders/auto_launch/configs/source_tiers.yaml",
    "battle_fields_path": "mashang_workspace/promptbuilders/auto_launch/configs/battle_fields.yaml"
  },
  "event_candidates": [
    {
      "event_model": "车型名（如 问界 M7）",
      "event_brand": "品牌名（如 问界）",
      "event_type": "必须来自 event_types.yaml",
      "event_name": "事件名称",
      "event_date": "YYYY-MM-DD 或 unknown",
      "confidence": "high | medium | low",
      "discovered_date": "{{MONITOR_DATE}}",
      "source_publish_time": "YYYY-MM-DD 或 unknown",
      "window_match": "confirmed_event_window | discovery_signal_window | context_window | unknown",
      "review_flags": [],
      "source_items": [
        {
          "source_name": "媒体/网站/官方账号名称",
          "source_title": "文章或公告标题",
          "source_url": "纯 URL",
          "source_tier": "official | mainstream_media | industry_media | user_generated | unknown",
          "publish_time": "YYYY-MM-DD 或 unknown"
        }
      ],
      "impact_vs_our_model": {
        "price_pressure": "high | medium | low | unknown",
        "rights_pressure": "high | medium | low | unknown",
        "configuration_pressure": "high | medium | low | unknown",
        "delivery_pressure": "high | medium | low | unknown"
      },
      "missing_evidence": [
        "具体缺失的证据项"
      ]
    }
  ],
  "discovery_signals": [
    {
      "event_model": "车型名",
      "event_brand": "品牌名",
      "signal_type": "dealer_offer | media_warmup | store_activity | live_stream | social_buzz | rights_countdown | test_drive_push | delivery_hint | config_leak | price_hint | order_lock_hint | unknown",
      "signal_name": "信号描述",
      "possible_event_type": "可能的 event_type",
      "confidence": "low | medium",
      "discovered_date": "{{MONITOR_DATE}}",
      "source_publish_time": "YYYY-MM-DD 或 unknown",
      "window_match": "discovery_signal_window | context_window | unknown",
      "review_flags": [],
      "source_items": [
        {
          "source_name": "媒体/网站名称",
          "source_title": "文章标题",
          "source_url": "纯 URL",
          "source_tier": "mainstream_media | industry_media | user_generated | unknown",
          "publish_time": "YYYY-MM-DD 或 unknown"
        }
      ],
      "why_not_candidate": "未进入 event_candidates 的原因",
      "missing_evidence": [
        "还缺什么证据"
      ]
    }
  ],
  "needs_review": [],
  "no_event_models": [
    "零跑 D19",
    "岚图 泰山 X8 PHEV"
  ],
  "search_audit": [
    {
      "event_model": "车型名",
      "event_brand": "品牌名",
      "searched_layers": {
        "official_confirmation": true,
        "media_cross_check": true,
        "sales_weak_signals": false
      },
      "window_coverage": {
        "confirmed_event_window": true,
        "discovery_signal_window": true,
        "context_window": true
      },
      "source_coverage": {
        "official": 2,
        "mainstream_media": 3,
        "industry_media": 1,
        "user_generated": 0,
        "unknown": 0
      },
      "queries_used": [
        "问界 M7 权益",
        "问界 M7 门店",
        "问界 M7 懂车帝"
      ],
      "coverage_note": "官方源和主流媒体有覆盖，弱信号未发现"
    }
  ]
}
```

### 字段说明

| 顶层字段 | 说明 |
|----------|------|
| `event_candidates` | 有明确销售动作证据的事件列表 |
| `discovery_signals` | 有业务价值但尚未确认的销售动作线索 |
| `needs_review` | 证据不足、event_type 无法归类、来源冲突、疑似传闻的项目 |
| `no_event_models` | 搜索后未发现有效销售动作或信号的车型 |
| `search_audit` | 检索覆盖记录，便于判断"没发现"是真的没事件还是覆盖不足 |

| 字段层级 | 规则 |
|----------|------|
| `event_candidates[].confidence` | 允许 high / medium / low |
| `event_candidates[].event_date` | 必须由以下至少一项支撑：source publish_time、官方页面明确权益有效期、官方公告发布日期、多个高可信媒体在同一日期报道；若 source publish_time=unknown 且无明确有效期，confidence 不得为 high |
| `event_candidates[].window_match` | 允许 `confirmed_event_window` / `discovery_signal_window` / `unknown`；若为 `context_window` 则不合规 |
| `event_candidates` 中 event_model 命名一致性 | 若 event_model 与 source 中车型命名不完全一致（如 06 vs 06T、PHEV vs EV），必须进入 `needs_review` 或添加 `review_flags`，confidence 不得为 high |
| `discovery_signals[].confidence` | **不允许 high**，仅 low / medium |
| `discovery_signals[].window_match` | 允许 `discovery_signal_window` / `context_window` / `unknown`；若为 `context_window`，`why_not_candidate` 必填 |
| `discovery_signals[].why_not_candidate` | 必须说明未进入 event_candidates 的原因 |
| `search_audit[].searched_layers` | 记录三层检索策略各层是否覆盖 |
| `search_audit[].window_coverage` | 记录各窗口是否覆盖 |
| `search_audit[].source_coverage` | 各来源类型的检索结果数量 |

## 输出后处理建议

运行完成后，将输出的 JSON 保存到本地：

```
mashang_workspace/outputs/auto_launch/{{MONITOR_DATE}}_daily_monitor/raw_ai_output.json
```

然后在项目根目录运行：

```bash
make auto-launch-intake \
  SAMPLE=mashang_workspace/outputs/auto_launch/{{MONITOR_DATE}}_daily_monitor/raw_ai_output.json \
  OUT_DIR=mashang_workspace/outputs/auto_launch/{{MONITOR_DATE}}_daily_monitor
```
