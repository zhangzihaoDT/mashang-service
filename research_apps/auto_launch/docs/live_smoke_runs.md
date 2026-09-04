# Live Smoke Runs

## 2026-07-08 / 2026-07-09 — 首次真实 Daily Run 冒烟

| 项目 | 内容 |
|------|------|
| **入口** | `python -m auto_launch.cli launch` |
| **路径** | 选项 1 — 处理 ChatGPT Daily Run |
| **日期** | 2026-07-08（7 条事件）和 2026-07-09（5 条事件） |
| **数据源** | 24 品牌每日营销事件监控（人工整理 Markdown 表格） |
| **结果（7/8）** | 7 raw → 6 keep → 1 discard → 6 facts INSERT |
| **结果（7/9）** | 5 raw → 5 keep → 0 discard → 5 facts INSERT |
| **累计 facts** | 11 |

### 发现问题

| # | 问题 | 影响 | 修复 |
|---|------|------|------|
| 1 |`brief_renderer` 简报标题日期使用 `datetime.today()` | `outputs/briefs/2026-07-08.md` 标题显示"2026-07-09" | v1.0.2: 传入 `brief_date` 参数，fallback 到 facts event_date |
| 2 | launcher 只写 `outputs/briefs/`，`outputs/runs/` 为空 | 与 output contract 中 runs 为主运行包的定位不一致 | v1.0.2: launcher 同时写 `outputs/runs/{date}/` 运行包 |
| 3 | 品牌分布为全 1 条时仍输出"最活跃品牌：阿维塔（1 条）" | 误导性信息 | v1.0.2: 全 1 条时输出"品牌分布较分散" |

### 修复状态

- 三个问题已在 v1.0.2 Smoke Hardening 中修复
- 测试覆盖新增 8 个用例

### 其他发现

- 表格格式（Markdown table）的 daily run inbox parser 不支持，需手动转换为 `## title + - field: value` 格式
- 部分事件被 inbox_filter `no_event_or_action` 规则过滤（因摘要中无明确营销动作关键词）

---

## 2026-07-09 — Search Live Smoke — 极氪 7 天动作

| 项目 | 内容 |
|------|------|
| **入口** | `python -m auto_launch.cli launch` → 选项 2 |
| **Request** | 极氪 最近 7 天 动作 |
| **Live** | yes |
| **queries** | 5（scout 3 + refine 2） |
| **raw results** | 40 |
| **normalized** | 37 |
| **kept / written** | 17 keep → 17 facts INSERT（fact_id 12–28） |
| **discarded** | 20 |
| **facts total after run** | 28 |

### 入库内容摘要

- **交付数据：** 6 月交付 35,169 台（+111%），1-6 月累计 178,370 台（+97%），猎装月交付破万
- **OTA：** 7.2 推送（40 项新功能）、5.6（车道级导航）、6.5（车位到车位领航）
- **市场动态：** 7X 韩国上市（定价高于 Model Y）、007 限时权益
- **渠道：** 9X 五座版可订门店、门店促销信息（含韩语内容）

### 人工观察

| # | 发现 | 影响 |
|---|------|------|
| 1 | Search live 链路通过，search → facts 写入成功 | ✅ 基础链路可用 |
| 2 | **9X 预售未重复入库**（仅 1 条"可订门店"信息） | ✅ 但 daily run 的 9X 预售不在同一次搜索中出现 |
| 3 | **delivery_start 严重重复**（6 条内容基本相同的交付新闻） | 需要 title 相似度去重或 fingerprint 策略优化 |
| 4 | **source_tier 判断偏弱**：易车等垂媒被标为 tier_5 | source_domain_resolver 子域名覆盖不全 |
| 5 | **event_date 缺失**：search 结果 17/28 无日期 | 应 fallback 到 first_seen 或 monitor_date |
| 6 | **model 字段缺失**：search 结果 model 完成率仅 35.7% | 搜索结果的品牌/车型映射未传递到 facts |
| 7 | **brief 排序**：--days 1 排除 daily run 的 9X 预售（7/8）；极氪内部 OTA 应排在交付重复之前 | 需要按 event_type 权重排序，并在无 event_date 时用 first_seen |
| 8 | **_EVENT_TYPE_GROUPS 缺 delivery_start / channel_campaign / technology_release** | 17 条极氪数据落入"其他"分组 |


### 修复状态（v1.0.3）

| # | 问题 | 修复 |
|---|------|------|
| 3 | **交付数据重复入库** | 新增 delivery/sales semantic fingerprint：brand + period + core numbers 相同则合并 |
| 4 | **易车等被标 tier_5** | 补充 `source_domains.yaml`：易车/新浪财经子域名、autohome 子域名、dongchedi 子域名 |
| 8 | **_EVENT_TYPE_GROUPS 未覆盖** | 补充 delivery_start / channel_campaign / technology_release / benefit_adjustment 到对应分组 |
| 5 | **--days 日期过滤不合理** | `query()` 增加 `last_seen OR event_date` 双条件；brief 标题日期使用输入日期 |
| — | **semantic fingerprint** | 6 月交付 35,169 的 6 条重复新闻 → 合并为 1 条（seen_count=6） |
