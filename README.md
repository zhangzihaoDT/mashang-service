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

关键约定：

- 时间窗口统一按左闭右开 `[start, end)` 执行过滤（`>= start` 且 `< end`）。
- 数据执行尽量保持确定性：LLM 做规划与总结，代码做查询与计算。
- Agent 的真实输出不是“直接查一次就回答”，而是“循环判断是否已拿到足够事实，再决定继续查还是结束回答”。

## v0.4：Evidence-driven Agentic BI Runtime

本版本开始，主循环从“LLM 判断是否结束”升级为“Evidence-driven Runtime”：

- State-first：所有中间态都落入 AgentState
- Structured Result Blocks：每次工具执行生成可追溯的 structured_blocks（同时保留 legacy 文本 blocks）
- Fact Extraction：从 structured_blocks 抽取/生成 Normalized Facts，并强制携带 source.block_id
- Evidence Contract：用 required_fact_types 固化“什么证据足够回答”
- Runtime Decision：先走规则判定是否 finish；不足时再继续 run_dsl
- Grounded Summary：总结层只基于证据输出，并避免将贡献拆解直接表述为因果原因

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

- 2026-05-12
  - 拆分“时间窗口 / 统计函数 / 维度（分组）”职责：时间窗口解析收敛到 `operators/time_windows.py`，统计计算收敛到 `tools/statistics_tool.py`，维度分组由 `agent/planner.py` 统一产出（统计类计划强制按时间字段分组）。
- 2026-05-13（v0.4）
  - 引入 Evidence-driven Runtime：structured_blocks → facts → evidence contract → runtime decision
  - 新增 `statistics.contribution_summary` 用于诊断类问题的贡献拆解（描述性证据）
  - Facts 升级为 Normalized Facts（values / conclusion / source）

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
│   ├── tool_router.py      # 路由与编排（fast_path/operator/comparison/statistics/query）
│   ├── runtime_decision.py # Evidence Contract + Runtime Decision（should_continue）
│   ├── state.py            # 运行时状态（question/loop/planning/results/memory/final）
│   ├── memory_extractor.py # 对话记忆抽取与更新
│   └── llm_config.py       # DeepSeek 模型名配置
├── tools/                 # 确定性执行工具（Query/Comparison/Statistics/FastPath）
├── operators/             # 强口径固定算子
├── schema/                # schema 与数据路径配置
└── 设计方案/               # 方案与设计文档（可选参考）
```

## 示例问题

```text
下发线索数 (门店) 的平均值是多少？
2025年8月1日~10日锁单数日均值是多少？
近30日有多少天锁单数大于120？
昨天的锁单数在近30日的锁单数中处于什么分位？
查询近10周周四/周五门店锁单率环比变化，有多少周是下降的？
```
