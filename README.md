# Mashang Agentic BI（DeepSeek Tool Calling）

这是一个基于 DeepSeek API（OpenAI 兼容接口）的 **Agentic BI 查询 Agent**：将自然语言问题规划为结构化 DSL，然后在本地数据集上确定性执行，并汇总成可读回答。

本仓库有两个对外入口：
- [main.py](file:///Users/zihao_/Documents/github/mashang-service：0.1/main.py)：命令行单次问答（适合调试/本地跑）。
- [feishu_bot.py](file:///Users/zihao_/Documents/github/mashang-service：0.1/feishu_bot.py)：飞书机器人（WebSocket 长连接收消息，调用同一套 Agent 能力回复）。

## 总体架构

```text
用户问题
  ↓
PlanningAgent（LLM 规划）→ 生成 plan（dataset/metric/time/filters/dimensions/comparison/statistics/fast_path）
  ↓
Tool Router（确定性路由与执行）
  - Fast Path：纯计算/闲聊/ISO 周数等轻量直算
  - Operators：强口径固定算子（避免指标口径漂移）
  - Query / Comparison / Statistics：通用 DSL 执行与统计后处理
  ↓
Answer（LLM 总结 或 Grounded Summary）
```

关键约定：
- 时间窗口统一按左闭右开 `[start, end)` 执行过滤（`>= start` 且 `< end`）。
- 数据执行尽量保持确定性：LLM 做规划与总结，代码做查询与计算。

## 数据与 Schema

本项目默认在本地加载 CSV/Parquet 数据集：
- 数据路径配置： [schema/data_path.md](file:///Users/zihao_/Documents/github/mashang-service：0.1/schema/data_path.md)
  - 支持绝对路径与通配符（例如 `assign*data.csv`）
  - 该文件当前包含本机路径示例，换机器需要自行修改
- Schema 与业务定义：
  - [schema/schema.md](file:///Users/zihao_/Documents/github/mashang-service：0.1/schema/schema.md)
  - [schema/business_definition.json](file:///Users/zihao_/Documents/github/mashang-service：0.1/schema/business_definition.json)

## 支持的能力（路由一览）

- Fast Path（[tools/fast_path_tool.py](file:///Users/zihao_/Documents/github/mashang-service：0.1/tools/fast_path_tool.py)）
  - `numeric_ratio`：纯数字环比/同比直算
  - `current_iso_week`：当前日期 ISO 周
  - `small_talk_contextual`：致谢/闲聊（结合最近 memory）
- Comparison（[tools/comparison_tool.py](file:///Users/zihao_/Documents/github/mashang-service：0.1/tools/comparison_tool.py)）
  - `yoy` / `wow` / `dod`
- Statistics（[tools/statistics_tool.py](file:///Users/zihao_/Documents/github/mashang-service：0.1/tools/statistics_tool.py)）
  - `weekly_decline_ratio`：周序列环比 + 下降周数占比
  - `daily_threshold_count`：近 N 日阈值计数（支持 `> >= < <= == !=`）
  - `daily_mean`：近 N 日（或指定窗）按日聚合后的日均
  - `daily_percentile_rank`：参考日在近 N 日分布中的分位
  - `weekend_percentile_rank`：参考周末在近 N 个周末分布中的分位
  - `weekday_percentile_rank`：参考“某个星期几”在近 N 次该 weekday 分布中的分位
- Operators（[operators/registry.py](file:///Users/zihao_/Documents/github/mashang-service：0.1/operators/registry.py)）
  - 用于承接强业务口径的固定算子（例如在营门店等）

## 环境变量

在项目根目录创建 `.env`（不要提交到仓库）：

```env
# DeepSeek（必填）
DEEPSEEK_API_KEY=sk-xxx

# 飞书 Bot（仅运行飞书入口需要）
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
```

模型配置位于 [agent/llm_config.py](file:///Users/zihao_/Documents/github/mashang-service：0.1/agent/llm_config.py)。

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
├── main.py                # 入口：命令行单次问答（代理到 agent.run_main_agent）
├── feishu_bot.py          # 入口：飞书机器人
├── agent/                 # Agent 主循环、规划与状态
│   ├── agent_loop.py       # run_main_agent：主循环入口
│   ├── planner.py          # PlanningAgent：NL → plan（规划 DSL）
│   ├── tool_router.py      # 路由与编排（fast_path/operator/comparison/statistics/query）
│   ├── state.py            # 运行时状态（history/facts/working_memory/result_blocks）
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
