# Auto Launch Demo Case

## 解决什么问题

Auto Launch 是一个汽车上市 / 营销事件监测服务，解决以下业务问题：

1. **LS8 竞品车型**每天有什么销售动作（上市、交付、权益、价格变动）？
2. **24 个重点新能源品牌**每天有什么营销事件（发布会、传播、活动）？
3. 哪些是**已确认事件**，哪些是**弱信号**，哪些需要人工复核？
4. 信息来自什么信源，可信度如何？

核心方法是从多渠道（搜索、人工输入）收集事实，经过标准化、过滤、去重后存入持久事实库，再通过审计和简报能力将原始信息收敛为可消费的洞察。

## 从 raw/search 收敛到 facts

```
原始信号 (搜索/Inbox)
    │
    ▼ Normalize (去重、信源分类、时间窗口校验)
    │
    ▼ Filter (keep/discard 二分类)
    │
    ▼ Facts (SQLite 事实库，fingerprint 去重)
    │
    ▼ Audit / Brief / Timeline / Source-Audit (可消费输出)
```

核心原则：**事实库是一切消费的单一数据源**。搜索、Inbox、Normalize 都是为 facts 服务的输入管道。每次 `run-day` 或 `demo` 的最终产出是 facts + 基于 facts 的审计/简报/时间线。

## Demo 如何运行

```bash
# 使用 fixtures 数据（不调用真实 API）
python -m auto_launch.cli demo

# 清空事实库后重新演示
python -m auto_launch.cli demo --reset-store
```

Demo 使用 `tests/fixtures/daily_runs/day1.md ~ day3.md` 作为数据源，覆盖 4 个品牌（智己、理想、小米、极氪、问界）、3 个事件类型（权益调整、交付数据、改款上市）。

## Demo 输出文件

```
auto_launch/outputs/demo/
├── demo_manifest.json      — 运行元数据
├── demo_summary.md         — 人类可读摘要
├── facts_audit.json        — 事实库质量审计
├── source_audit.json       — 信源覆盖审计 JSON
├── source_audit.md         — 信源覆盖审计 Markdown
├── daily_brief.md          — 每日简报
├── timeline.md             — 品牌/车型事件时间线
└── outputs_inspect.md      — outputs 目录完整性检查
```

所有文件均为已有能力的产物，demo 只做编排，不新增业务逻辑。

## 从 Demo 能看到什么能力

| 能力 | 对应模块 | 在 Demo 中的体现 |
|------|----------|-----------------|
| Inbox Intake | inbox_parser / inbox_runner | 从 Markdown fixtures 解析结构化事件 |
| 事实去重 | fact_store (fingerprint) | day2/day3 重复事件 → seen_count 递增 |
| 字段完成率 | fact_store.audit() | facts_audit.json 中的 completeness |
| 信源分层 | source_tiers.yaml | source_audit 中的 official/media/weak 占比 |
| 品牌覆盖 | priority_brand_watchlist.yaml | source_audit 中的 expected_flags |
| 简报生成 | brief_renderer | daily_brief.md |
| 时间线 | timeline_renderer | timeline.md |
| 输出契约 | output_manager | outputs_inspect.md |

## 当前能力边界

- **数据源**：当前仅支持 Inbox Markdown 和 Volc Search API。人工 Inbox 是主力数据源。
- **信源分级**：基于域名白名单 + 关键词推测，不完全精确。`tier_3_industry_media` 无法区分垂媒 vs 泛科技媒体。
- **事件类型**：keyword-based 匹配，部分事件可能 miss（如无关键词的"官方价格调整"）。
- **搜索**：仅在 `--live` 模式下执行，dry-run 仅打印查询计划。
- **回放**：`replay` 支持 fixtures 和日期范围模式，但回放不重跑搜索。

## 下一步可扩展方向

| 方向 | 说明 |
|------|------|
| **Impact Score** | 基于事件类型、信源等级、品牌优先级计算事件重要性分数 |
| **Battle Field 聚合** | 按细分市场（如大六座 SUV）聚合竞品事件 |
| **自动补搜** | source-audit 发现 weak source 后自动补充搜索 |
| **多品牌并行监控** | 支持一次 `run-day` 覆盖多个品牌 |
| **可视化 Dashboard** | 基于 outputs 数据的轻量 Web UI |
| **真实 API 集成** | 接入更多数据源（如行业 API、RSS） |
