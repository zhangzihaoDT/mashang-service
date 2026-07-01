# Volc Search Assisted Pilot — 火山搜索辅助 Pilot Run

## 目的

本 runbook 定义 Volc-assisted 路径：利用火山搜索获得候选信息，再由 Prompt 生成 intake-ready JSON。

适用场景：
- 没有 ChatGPT Plan 可用
- 希望通过火山搜索补充候选信息
- 在不恢复旧 auto_launch_monitor 的前提下走通全链路

## 两段式流程

```
第一段：业务任务 → volc_search_query_plan → search tasks
                ↓
        Volc Search（人工或外部工具执行）
                ↓
第二段：Volc Search results → volc_search_result_to_event_brief → raw_ai_output.json
                ↓
第三段：raw_ai_output.json → auto-launch-intake → normalized.json + report.md + intake_manifest.json
                ↓
        auto-launch-index → index.json + index.md
                ↓
        pilot_quality_scorecard → 人工评审
```

## 推荐步骤

### 第 1 步：选择任务

确定 event_model / our_model / event_type / time_window / battle_field。

示例：
- event_brand: 问界
- event_model: M7
- our_model: 智己 LS8
- event_type: launch
- time_window: 过去 48h
- battle_field: large_six_seat_suv

### 第 2 步：生成 query plan

使用 `prompts/volc_search_query_plan.md` 生成火山搜索的查询计划。

将模板中的变量替换为实际值，得到 search_tasks（JSON 格式）。

### 第 3 步：执行 Volc Search

通过人工或外部工具执行第 2 步生成的 search_tasks。

将搜索结果整理为 JSON 或 Markdown。每条结果至少包含：
- source_title
- source_url
- source_tier（official / mainstream_media / industry_media / social_or_forum）
- evidence_snippet

### 第 4 步：生成 raw_ai_output.json

使用 `prompts/volc_search_result_to_event_brief.md`：

1. 将搜索结果填入 `{{volc_search_results}}`
2. 替换其他变量占位符
3. 将 Prompt 提交给 AI（DeepSeek / ChatGPT）
4. 将 AI 输出的 JSON 保存到本地临时文件

### 第 5 步：运行 intake

```bash
make auto-launch-intake \
  SAMPLE=path/to/temp_ai_output.json \
  OUT_DIR=mashang_workspace/outputs/auto_launch/{run_id}
```

### 第 6 步：生成索引

```bash
make auto-launch-index
```

### 第 7 步：人工评审

使用 `templates/pilot_quality_scorecard.md` 做人工评审。

## 边界

本 runbook 明确不做什么：

- ❌ 不实现 Volc API
- ❌ 不负责搜索执行（需人工或外部工具）
- ❌ 不调用 LLM（Prompt 需由 AI 执行）
- ❌ 不做事实核验
- ❌ 不做数据库入库
- ❌ 不创建 golden case
- ✅ 只定义 bridge workflow

## 质量门槛

Volc-assisted pilot 必须满足以下条件：

| 条件 | 说明 |
|------|------|
| source_items 非空 | intake 要求至少 1 条来源 |
| official / mainstream_media 优先 | Tier 1/2 结果必须充分使用 |
| social_or_forum 不得作为 confirmed_fact | 只能用于 unconfirmed_claim |
| confirmed_fact 必须有来源 | 每条事实关联 source_items |
| inference 必须可追溯 | 标注推断依据 |
| missing_evidence 不得为空 | 诚实记录信息缺口 |
| 通过 intake | validate 无报错 |
| 人工 scorecard 评审 | 使用 pilot_quality_scorecard.md |
