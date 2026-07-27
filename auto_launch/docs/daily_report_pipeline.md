# 日报处理流程 v0.2：Planner 日报 → 事实库 → 每日简报

核心变化：**不再靠 LLM 猜事件，而是按 Markdown 章节契约解析，再按 section_type 稳定路由入库。**

## 1. 输入

输入为一份结构化 Markdown 日报：

```text
24 品牌每日营销事件监控
├── 一、可入库确认事件
├── 二、高优先级弱信号 / 待复核
├── 三、今日品牌声量观察
├── 五、今日未发现明确新增动作的品牌
└── 其他说明章节
```

这类输入被识别为 `planner_daily_report`，它不是普通新闻文本，而是已经经过人工 / Planner 预筛选的结构化日报。

## 2. 解析：inbox_parser.parse_contract()

`inbox_parser.parse_contract()` 负责把 Markdown 日报解析成标准合同对象 `ParseContract`。

处理逻辑：

1. 检测源类型，识别为 `planner_daily_report`；
2. 按 `##` 标题切分章节；
3. 根据章节标题识别 `section_type`；
4. 解析 Markdown 表格；
5. 将表格列名映射为标准字段；
6. 输出统一结构：

```text
ParseContract {
  source_type,
  sections[],
  items[]
}
```

章节映射关系：

| 日报章节           | section_type   | 含义                 |
| -------------- | -------------- | ------------------ |
| 可入库确认事件        | brand_events   | 已确认、可入 facts 的正式事件 |
| 高优先级弱信号 / 待复核  | review_signals | 未确认但值得追踪的信号        |
| 今日品牌声量观察       | brand_volume   | 品牌动作与声量观察          |
| 今日未发现明确新增动作的品牌 | brand_status   | 品牌覆盖状态             |

## 3. 路由：inbox_filter.route()

`inbox_filter.route()` 根据 item 是否带有 `section_type` 分两套逻辑处理。

### Planner item

Planner 日报中解析出的 item 已经带有 `section_type`，因此不再走通用 keep / discard 分类，而是直接按章节路由：

| section_type   | route_to       | 目标       |
| -------------- | -------------- | -------- |
| brand_events   | confirmed_fact | 写入正式事实   |
| review_signals | review_signal  | 写入弱信号    |
| brand_status   | brand_status   | 写入品牌状态   |
| brand_volume   | brand_volume   | 写入品牌声量观察 |

### Legacy item

旧格式输入如果没有 `section_type`，继续走原有 `classify()` 逻辑：

```text
legacy item → classify() → keep / discard
```

这样可以同时兼容新版 Planner 日报和旧版非结构化输入。

## 4. 入库：fact_store

`fact_store` 负责把不同类型的数据写入对应表。

| route_to       | 写入表          | 说明                                           |
| -------------- | ------------ | -------------------------------------------- |
| confirmed_fact | facts        | 正式事件主表，基于 fingerprint 去重                     |
| confirmed_fact | evidence     | 正式事件的来源证据表                                   |
| review_signal  | signals      | 弱信号表，默认 status=open                          |
| brand_status   | brand_status | 品牌覆盖状态表，按 brand 幂等 upsert                    |
| brand_volume   | brand_volume | 品牌声量观察表，包含 claim / type / intensity / evidence |

注意：这里可以理解为 **4 类业务数据表 + 1 张 evidence 证据表**。也就是业务视角是 4 类，物理表实际是 5 张。

入库后执行覆盖审计：

```text
audit_coverage()
```

用于统计本次导入在以下表中的写入结果：

```text
facts
signals
brand_status
brand_volume
evidence
```

## 5. 生成简报：brief_renderer.generate_brief()

`brief_renderer.generate_brief()` 不再只读取 `facts` 表，而是同时读取：

```text
facts
signals
brand_status
brand_volume
```

输出每日简报 `daily_brief.md`。

简报包含 4 个核心模块：

| 模块     | 数据来源                 | 说明               |
| ------ | -------------------- | ---------------- |
| 今日重点   | facts                | 正式事件聚类，默认取 Top 5 |
| 待审查信号  | signals              | 展示弱信号、未确认原因和来源   |
| 品牌动作速览 | facts + brand_volume | 按品牌汇总今日动作        |
| 事件类型分布 | facts                | 按 event_type 聚合  |

## 6. CLI 执行链

### Step 1：导入 Planner 日报

```bash
python -m auto_launch.cli daily \
  --input planner_report.md \
  --date 2026-07-26
```

执行链路：

```text
parse_contract
→ validate
→ route
→ upsert
→ audit
```

### Step 2：生成每日简报

```bash
python -m auto_launch.cli report \
  --type daily-brief \
  --date 2026-07-26 \
  --days 1 \
  --no-llm
```

执行链路：

```text
query facts / signals / brand_status / brand_volume
→ aggregate
→ render daily_brief.md
```

## 7. 关键变更对照

| 模块             | 旧流程                       | 新流程                                                          |
| -------------- | ------------------------- | ------------------------------------------------------------ |
| inbox_parser   | 按 `##` 切块后猜测 key:value 字段 | 识别 4 类章节 schema，并解析 Markdown 表格行                             |
| inbox_filter   | 全量走 keep / discard 二分类    | Planner item 按 section_type 直接路由；legacy item 保留原分类           |
| fact_store     | 单表 facts                  | facts + evidence + signals + brand_status + brand_volume     |
| inbox_runner   | parse → filter → write    | parse_contract → validate → route → upsert → audit           |
| brief_renderer | 只读 facts 表                | 同时读取 facts / signals / brand_status / brand_volume，生成 4 模块简报 |

## 8. 当前流程的本质变化

新版流程的核心不是"让模型重新判断日报内容"，而是把 Planner 日报视为一种结构化输入合同。

也就是说：

```text
Planner 日报 = 已预筛选的半结构化事实源
```

系统要做的是：

1. 稳定解析；
2. 稳定路由；
3. 幂等入库；
4. 保留弱信号；
5. 保留品牌覆盖状态；
6. 最终生成更适合阅读和分发的简报。

这样可以避免两类问题：

第一，避免 LLM 在导入阶段二次误判，把弱信号误写入正式事件；

第二，避免只存 facts，导致"没有动作的品牌""弱信号""品牌声量观察"在后续简报中丢失。

## 9. 验收标准

本轮流程更新后，建议用以下标准验收：

| 验收项          | 通过标准                                   |
| ------------ | -------------------------------------- |
| Planner 日报识别 | 能识别 `source_type=planner_daily_report` |
| 确认事件入库       | `可入库确认事件` 只写入 facts / evidence         |
| 弱信号保留        | `高优先级弱信号` 写入 signals，且 status=open     |
| 品牌覆盖保留       | `未发现新增动作品牌` 写入 brand_status            |
| 声量观察保留       | `今日品牌声量观察` 写入 brand_volume             |
| 去重           | 同一事件重复导入不新增 facts                      |
| 简报生成         | daily-brief 能同时展示重点事件、弱信号、品牌动作和事件分布    |
| no-llm 模式    | 在不调用 LLM 的情况下可稳定生成基础简报                 |

## 10. 一句话总结

新版日报处理流程已经从"非结构化文本分类"升级为"结构化日报合同解析"：Planner 负责事实筛选，系统负责解析、路由、入库、审计和简报渲染。
