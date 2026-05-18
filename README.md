# Mashang Agentic BI（DeepSeek Tool Calling）

这是一个基于 DeepSeek API（OpenAI 兼容接口）的 **Agentic BI 查询 Agent**：将自然语言问题规划为结构化 DSL，然后在本地数据集上确定性执行，并汇总成可读回答。

本仓库有两个对外入口：

- [main.py](main.py)：命令行单次问答（适合调试/本地跑）。
- [feishu_bot.py](feishu_bot.py)：飞书机器人（WebSocket 长连接收消息，调用同一套 Agent 能力回复）。

## 输入到输出链路

```text
用户问题
  ↓
入口层（main.py / feishu_bot.py）
  ↓
Agent Loop（agent/agent_loop.py）
  - 读取 State（question / loop / planning / results / memory / final）
  - 决定下一步 action：run_dsl 或 finish（Evidence-driven Runtime Decision）
  - 最多循环 5 步，避免重复查询
  ↓
PlanningAgent（agent/planner.py）
  - 将自然语言问题转成 plan / clarification
  - 产出 dataset / metric / time / filters / dimensions / comparison / statistics / fast_path
  ↓
Tool Router（agent/tool_router.py，确定性路由与执行）
  - Fast Path：纯计算 / 闲聊 / ISO 周数等轻量直算
  - Operators：强口径固定算子（避免指标口径漂移）
  - Composition：占比/构成/份额高频 BI 专用工具（周/月/日分组占比）
  - MultiTableMetric：跨表配置渗透率/分布分析（order_data ⋈ config_attribute）
  - Query / Comparison / Statistics：通用 DSL 执行与统计后处理
  ↓
Structured Result Blocks（结构化执行结果）
  - legacy blocks：LLM-readable 文本块（用于总结）
  - structured_blocks：machine-readable 结构化块（用于可追溯与规则判断）
  - 回写到 Agent State.results，供下一轮 loop 继续决策
  ↓
Fact Extraction（agent/memory_extractor.py）
  - 从 structured_blocks 抽取/生成 Normalized Facts（每条 fact 带 source.block_id）
  - 信息不足写入 missing_info（而不是编造）
  ↓
Evidence Contract（agent/runtime_decision.py）
  - 不同分析意图需要的证据集合（required_fact_types）
  - 例如 diagnosis 必须满足 trend_summary + contribution_summary
  ↓
Runtime Decision（agent/runtime_decision.py）
  - 基于 Evidence Contract + Facts 决定继续 run_dsl 或 finish
  - result_satisfies_goal：检查结果列是否满足用户问题所需（时间粒度、拆解维度、占比列等）
  - 不满足时自动生成 repair query 并重试（最多 2 次 repair 后强制 finish）
  ↓
Answer / Summarization
  - 信息不足：回到 Agent Loop 继续 run_dsl
  - 信息充分：生成 grounded summary / 最终自然语言答案
  ↓
Agent 返回
  - 命令行打印答案
  - 或由飞书 Bot 回传消息

旁路（强烈建议落盘）：
  Query Log（规划与执行日志，append-only）
    ↓
  Question Pattern → DSL Prior（planner examples），用于提升规划稳定性（而不是长文本聊天记忆）
```

可以把这条链路简化理解为：

```text
input（用户提问）
  -> Agent Loop 判断要不要查
  -> PlanningAgent 生成 DSL
  -> Tool Router 执行工具
  -> 得到结构化结果
  -> Agent 总结
  -> output（Agent 返回）
```

### DSL 扩展字段

- **`analysis_intent`**：分析意图元信息，用于工具路由与结果校验。

```json
{
  "type": "share_breakdown",
  "numerator_metric": "锁单数",
  "denominator_scope": "within_each_week",
  "time_grain": "week",
  "breakdown_dimension": "product_name"
}
```

**v0.4.4 新增 `attribute_penetration` / `attribute_distribution` 类型**，用于跨表配置属性分析：

```json
{
  "type": "attribute_penetration",
  "attribute_pattern": "激光雷达",        // config_attribute.Attribute 模糊匹配
  "value_contains": "Thor",              // value 模糊过滤（可选）
  "positive_value": "是|标准|高阶|Thor",  // value 正则匹配（可选）
  "dimension_field": "product_name",     // 分组维度
  "dimension_mapping": {                 // 维度值映射（如 5座/6座）
    "五座": "product_name LIKE '%五座%'",
    "六座": "product_name LIKE '%六座%'"
  }
}
```

```json
{
  "type": "attribute_distribution",
  "attribute_pattern": "轮毂|轮辋",       // config_attribute.Attribute 模糊匹配
  "top_k": 10                            // 取 Top-K 值，其余归为"其他"
}
```

- **`post_process`**：通用后处理步骤序列，目前支持 `share`（分组占比）与 `window_share`（时间窗口占比）。

```json
{
  "post_process": [
    {
      "type": "share",
      "value_col": "锁单数",
      "partition_by": ["lock_time"],
      "alias": "占比"
    }
  ]
}
```

关键约定：

- 时间窗口统一按左闭右开 `[start, end)` 执行过滤（`>= start` 且 `< end`）。
- 数据执行尽量保持确定性：LLM 做规划与总结，代码做查询与计算。
- Agent 的真实输出不是"直接查一次就回答"，而是"循环判断是否已拿到足够事实，再决定继续查还是结束回答"。

## v0.4：Evidence-driven Agentic BI Runtime

本版本开始，主循环从“LLM 判断是否结束”升级为“Evidence-driven Runtime”：

- State-first：所有中间态都落入 AgentState
- Structured Result Blocks：每次工具执行生成可追溯的 structured_blocks（同时保留 legacy 文本 blocks）
- Fact Extraction：从 structured_blocks 抽取/生成 Normalized Facts，并强制携带 source.block_id
- Evidence Contract：用 required_fact_types 固化“什么证据足够回答”
- Runtime Decision：先走规则判定是否 finish；不足时再继续 run_dsl
- Grounded Summary：总结层只基于证据输出，并避免将贡献拆解直接表述为因果原因

## 核心设计原则

```
intent          →  负责判断问题类型
fact_type       →  负责判断证据是否足够
tool            →  负责生成证据
runtime_decision →  负责是否允许 finish
```

四层各司其职，不跨层越权：

- **intent**（`infer_intent_from_question`）只做 NL 分类，输出 `metric / trend / compare / share / time_grouped_share / composition / ranking / distribution / diagnosis` 之一，不关心具体数据。
- **fact_type**（`SUPPORTED_FACT_TYPES`）定义证据语言，作为 contract 匹配的最小原子单位，不关心 LLM 或工具的实现细节。
- **tool**（QueryTool / Statistics / Composition / Comparison）只负责生成结构化结果，不关心当前缺什么证据、是否应该 finish。
- **runtime_decision**（`evaluate_state_readiness`）对照 contract 检查已有 fact_type，只回答"证据够不够"，不关心数据内容。

## BI 能力矩阵

| 能力类型                | 典型问题                    | 执行工具                              | Evidence Contract（所需证据类型）                               |
| ----------------------- | --------------------------- | ------------------------------------- | --------------------------------------------------------------- |
| 总量查询                | 昨天锁单数是多少            | QueryTool                             | `metric_value`                                                  |
| 趋势分析                | 近30日锁单趋势如何          | Statistics.trend_summary              | `trend_summary`                                                 |
| 对比分析                | 本周 vs 上周变化            | Comparison.wow                        | `comparison_result`                                             |
| 占比分析（share）       | 分车型锁单占比              | Composition.share_by_dimension        | `dimension_breakdown` + `share_summary`                         |
| 构成分析（composition） | 按城市/门店/渠道拆解结果    | QueryTool + GROUP BY                  | `dimension_breakdown`                                           |
| 构成分析（含时间+占比） | 每周分车型锁单占比          | Composition.weekly_share_by_dimension | `time_grouped_metric` + `dimension_breakdown` + `share_summary` |
| 排序分析                | 锁单 TOP10 城市             | QueryTool + ORDER BY                  | `ranking_result`                                                |
| 分布分析                | 锁单用户年龄分布 / 分位水平 | Statistics                            | `distribution_summary`                                          |
| 诊断分析                | 为什么最近一周下滑          | Statistics.contribution_summary       | `trend_summary` + `contribution_summary`                        |
| 配置渗透率分析          | CM2 增程中 Thor 选装率     | MultiTableMetricTool.attribute_penetration  | `dimension_breakdown` + `share_summary`                    |
| 配置分布分析            | LS8 不同轮毂的选装比例     | MultiTableMetricTool.attribute_distribution | `dimension_breakdown` + `share_summary`                    |

## Query Log（规划与执行日志）

最优先记录的不是“用户偏好”，而是“问题模式（Question Pattern）”：例如“最近 7 天 + 某车型 + 区域趋势”、或“当前值 vs 近 30 日日均”。这些模式最终会沉淀为 DSL Prior（planner examples），用于提升 PlanningAgent 的稳定性与可控性。

推荐日志结构（建议按 JSONL / SQLite / ClickHouse 这类 append-only 存储）：

```json
{
  "timestamp": "...",
  "question": "...",
  "normalized_question": "...",
  "generated_plan": {},
  "clarification": {},
  "execution_success": true,
  "used_dataset": "...",
  "used_metrics": [],
  "used_dimensions": [],
  "latency_ms": 1200,
  "token_usage": {},
  "result_summary": "...",
  "user_feedback": null
}
```

## 更新日志

- 2026-05-15（v0.4.5 — 数据集更新 Fast Path）
  - 新增 `FastPathTool.data_update`：支持 CLI/飞书触发数据集增量更新
    - `scope="order"` 时调用 `order_data_to_parquet.py`
    - `scope="config"` 时调用 `order_config_to_parquet.py`
    - `scope="lock"` 时调用 `lock_attribution_data_to_parquet.py`
    - 更新后自动读取 `lock_time` 最大日期作为"更新至"时间戳
  - 新增 `FastPathTool.data_sync`：明确触发"数据更新并同步"时连续调用 `skills_order_observation_daily.py`
  - `FastPathTool` 升级：`answer` 字段直出（绕过 LLM 总结）
  - `Planner._parse_fast_path_query`：规则路径前置，匹配"更新订单数据"等自然语言
  - `_normalize_plan` fast_path 白名单加入 `data_update` / `data_sync`
- 2026-05-15（v0.4.4 — MultiTable / Lookup Metric 能力补齐）
  - 新增 `MultiTableMetricTool`（tools/multitable_metric_tool.py）
    - `attribute_penetration`：order_data ⋈ config_attribute，计算配置/属性渗透率（地暖/激光雷达/线控等）
    - `attribute_distribution`：多值属性分布占比（轮毂 share、颜色分布），支持 Top-K
    - 支持 `value_contains` 模糊匹配 variant（如 Thor/Orin 区分）
    - 支持 `series_group_logic`（CM0/CM1/CM2/DM0/DM1）与 `product_type_logic`（增程/纯电）业务规则推导
  - 新增 `ConfigCrossAnalysisTemplates`（tools/config_cross_analysis_templates.py）
    - 17 个配置渗透率模板 + 3 个分布模板，关键词匹配自动填充 `analysis_intent`
    - 通用 fallback：查询含"选装率"但无模板匹配时，自动提取文本作为 attribute_pattern
    - 时间窗口：优先解析用户显式日期（X年X月X日至今）→ 系列上市日（time_periods.end）→ 默认
  - Agent routing：`analysis_intent.type == "attribute_penetration"` / `"attribute_distribution"` → MultiTableMetricTool
  - Planner 规则路径：`_is_penetration_query` + `_build_penetration_plan`，LLM 前稳定命中
  - 独立回测脚本：scripts/ls8_floor_heating_rate.py
- 2026-05-14（v0.4.2 — Fact Production Layer 稳定化）
  - 工具层与路由
    - 新增 `analysis_intent` + `post_process` DSL 字段，用于表达占比/构成类分析意图
    - 新增 `CompositionTool`（tools/composition_tool.py）：专用占比分析工具（周/月/日分组占比、Top-N、帕累托累计占比）
    - 路由：`plan.analysis_intent.type == "share_breakdown"` → CompositionTool
    - `QueryTool._apply_post_process`：通用 DataFrame 后处理（share 计算）
    - `runtime_decision.result_satisfies_goal`：基于用户问题提取 required slots，检查结果列是否满足需求；不满足时自动生成 repair query 重试（最多 2 次）
    - 语义过滤增强：自动识别用户查询中的具体产品名并添加 product_name 过滤条件
    - 时间窗口增强：`_parse_time_window` 新增"本周"支持（ISO 周 Mon–today）
  - 确定性 Fact 抽取
    - **所有 builder 改为 summary 格式**：每个 block × 每种 fact_type 最多 1 条，含 `content` + `metadata`，旧 `values`/`rows`/`time_series` 数组全部移除
    - **新增 `_make_fact`**：统一 fact 构造入口
    - **column-based detection**（`memory_extractor.py`）：7 个 `_detect_*_columns` 函数用 keyword substring 匹配（中英文），替代硬编码列名集合
    - **`_FALLBACK_HINTS`**：为每个 block_type 声明预期 fact_type 集合
    - **gap-filling**：block_type handlers 产出不足时，自动用 column-based 补齐缺失的 fact_type（如 `trend_summary` → `trend_summary` + `time_grouped_metric`）
    - **`evidence_hints`**：工具层注入到 `structured.result`（tool_router.py `_infer_evidence_hints`），fact 抽取从猜测升级为声明
    - **`_comparison_df_to_dict`**：comparison DataFrame 转为 dict + evidence_hints（保留 rows 结构）
    - **`[Eval]` debug line**：runtime_decision 每次决策输出 `question | intent | required | available | missing | action | finish_reason` 一行
  - **10 问题回测全过**：`metric / trend / compare / composition / share / time_grouped_share / ranking / distribution / diagnosis`
- 2026-05-13（v0.4）
  - 引入 Evidence-driven Runtime：structured_blocks → facts → evidence contract → runtime decision
  - 新增 `statistics.contribution_summary` 用于诊断类问题的贡献拆解（描述性证据）
  - Facts 升级为 Normalized Facts（values / conclusion / source）
- 2026-05-12
  - 拆分"时间窗口 / 统计函数 / 维度（分组）"职责：时间窗口解析收敛到 `operators/time_windows.py`，统计计算收敛到 `tools/statistics_tool.py`，维度分组由 `agent/planner.py` 统一产出（统计类计划强制按时间字段分组）。

## 数据与 Schema

本项目默认在本地加载 CSV/Parquet 数据集：

- 数据路径配置： [schema/data_path.md](schema/data_path.md)
  - 支持绝对路径与通配符（例如 `assign*data.csv`）
  - 该文件当前包含本机路径示例，换机器需要自行修改
- Schema 与业务定义：
  - [schema/schema.md](schema/schema.md)
  - [schema/business_definition.json](schema/business_definition.json)

## 支持的能力（路由一览）

- Fast Path（[tools/fast_path_tool.py](tools/fast_path_tool.py)）
  - `numeric_ratio`：纯数字环比/同比直算
  - `current_iso_week`：当前日期 ISO 周
  - `small_talk_contextual`：致谢/闲聊（结合最近 memory）
- Comparison（[tools/comparison_tool.py](tools/comparison_tool.py)）
  - `yoy` / `wow` / `dod`
- Statistics（[tools/statistics_tool.py](tools/statistics_tool.py)）
  - `weekly_decline_ratio`：周序列环比 + 下降周数占比
  - `daily_threshold_count`：近 N 日阈值计数（支持 `> >= < <= == !=`）
  - `daily_mean`：近 N 日（或指定窗）按日聚合后的日均
  - `daily_mean_median`：近 N 日（或指定窗）按日聚合后的日均 + 中位数
  - `trend_summary`：近 N 日趋势摘要（方向、斜率、波动、连续涨跌、峰谷值等）
  - `contribution_summary`：贡献拆解摘要（baseline vs target，描述性证据）
  - `daily_percentile_rank`：参考日在近 N 日分布中的分位
  - `weekend_percentile_rank`：参考周末在近 N 个周末分布中的分位
  - `weekday_percentile_rank`：参考“某个星期几”在近 N 次该 weekday 分布中的分位
- Operators（[operators/registry.py](operators/registry.py)）
  - 用于承接强业务口径的固定算子（例如在营门店等）
- Composition（[tools/composition_tool.py](tools/composition_tool.py)）
  - `share_by_dimension`：简单分组占比
  - `weekly_share_by_dimension`：按周分拆占比（ISO 周合并，自动重聚合）
  - `monthly_share_by_dimension`：按月分拆占比
  - `topn_share`：Top-N 占比
  - `cumulative_share`：累计占比（帕累托）
  - 路由条件：`plan.analysis_intent.type == "share_breakdown"`
- MultiTable / Lookup Metric（[tools/multitable_metric_tool.py](tools/multitable_metric_tool.py)）
  - `attribute_penetration`：主表右连选配表，计算配置/属性渗透率（二值 是/否），支持 variant 模糊匹配
  - `attribute_distribution`：多值属性分布占比（如轮毂类型 share、颜色分布）
  - 路由条件：`plan.analysis_intent.type == "attribute_penetration"` 或 `"attribute_distribution"`
  - 模板库：[tools/config_cross_analysis_templates.py](tools/config_cross_analysis_templates.py)，覆盖 17 个配置项模板（地暖/轮毂/激光雷达/线控/礼包等）
  - 支持业务规则推导：series_group_logic（CM0/CM1/CM2/DM0/DM1）、product_type_logic（增程/纯电）

## 环境变量

在项目根目录创建 `.env`（不要提交到仓库）：

```env
# DeepSeek（必填）
DEEPSEEK_API_KEY=sk-xxx

# 飞书 Bot（仅运行飞书入口需要）
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx

# 可选：E2B Code Interpreter（当前未接入主流程；仅 tools/code_interpreter.py 使用）
E2B_API_KEY=xxx
```

模型配置位于 [agent/llm_config.py](agent/llm_config.py)。

## 安装与运行

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 入口 1：命令行（main.py）

```bash
python3 main.py "下发线索数 (门店) 的平均值是多少？"
```

不传入问题时会使用内置示例问题。

### 入口 2：飞书机器人（feishu_bot.py）

```bash
python3 feishu_bot.py
```

该入口使用飞书官方 SDK 的 WebSocket 长连接事件订阅模式：程序启动后会过滤启动前的历史消息，并对 message_id 做简单去重。

## 目录结构

```text
.
├── main.py                # 入口：命令行单次问答（代理到 agent.agent_loop.run_main_agent）
├── feishu_bot.py          # 入口：飞书机器人
├── agent/                 # Agent 主循环、规划与状态
│   ├── agent_loop.py       # run_main_agent：主循环入口
│   ├── planner.py          # PlanningAgent：NL → plan（规划 DSL）
│   ├── schema.py           # schema/data_path 等加载约定
│   ├── tool_router.py      # 路由与编排（fast_path/operator/composition/comparison/statistics/query）
│   ├── runtime_decision.py # Evidence Contract + Runtime Decision（should_continue）
│   ├── state.py            # 运行时状态（question/loop/planning/results/memory/final）
│   ├── memory_extractor.py # 对话记忆抽取与更新
│   └── llm_config.py       # DeepSeek 模型名配置
├── tools/                 # 确定性执行工具（Query/Comparison/Statistics/FastPath/Composition/MultiTableMetric）
│   ├── query_tool.py
│   ├── comparison_tool.py
│   ├── statistics_tool.py
│   ├── composition_tool.py
│   ├── fast_path_tool.py
│   ├── multitable_metric_tool.py    # 跨表属性渗透率/分布分析
│   └── config_cross_analysis_templates.py  # 配置分析模板库（17 个模板）
├── operators/             # 强口径固定算子
├── schema/                # schema 与数据路径配置
├── scripts/               # 固定自动化脚本（定时调度用）
└── 设计方案/               # 方案与设计文档（可选参考）
```

## 示例问题

```text
下发线索数 (门店) 的平均值是多少？
2025年8月1日~10日锁单数日均值是多少？
近30日有多少天锁单数大于120？
昨天的锁单数在近30日的锁单数中处于什么分位？
查询近10周周四/周五门店锁单率环比变化，有多少周是下降的？
输出LS8上市以来，每周分车型的锁单数占比分别是多少？
本周智己LS8 66 Ultra 奢享大六座的锁单总数
按月分门店看交付数占比
各门店锁单量Top-5占比
```
