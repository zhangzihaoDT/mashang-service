# ChatGPT Plan Handoff Runbook

## 这个 runbook 解决什么问题

ChatGPT Plan 负责定时搜索和生成 JSON，auto_launch 本地 workflow 负责校验、归一化、渲染和沉淀。

Plan 输出 JSON 后，通过这个 runbook 将「AI 输出落地为项目中可追踪的产物」。

## 推荐使用流程

### 第 1 步：ChatGPT Plan 执行

在 ChatGPT Plan 中使用 `plan_templates/` 下的模板。

要求 Plan 以 JSON 格式输出（Plan 模板已内置 JSON output 格式约束），输出结构应靠近 `schemas/auto_launch_event.schema.json` 或 `schemas/auto_launch_brief.schema.json`。

### 第 2 步：保存原始 AI 输出

将 ChatGPT Plan 的 JSON 输出保存到本地文件。

推荐命名：

```
mashang_workspace/outputs/auto_launch/{date}_{event_model}_{event_type}/raw_ai_output.json
```

例如：

```
mashang_workspace/outputs/auto_launch/2026-07-01_aito_m7_launch/raw_ai_output.json
```

### 第 3 步：运行 intake

```bash
# 使用 output-dir 模式（推荐）
make auto-launch-intake \
  SAMPLE=mashang_workspace/outputs/auto_launch/2026-07-01_aito_m7_launch/raw_ai_output.json \
  OUT_DIR=mashang_workspace/outputs/auto_launch/2026-07-01_aito_m7_launch

# 或直接运行 Python
python mashang_workspace/promptbuilders/auto_launch/intake/process_ai_output.py \
  mashang_workspace/outputs/auto_launch/2026-07-01_aito_m7_launch/raw_ai_output.json \
  --output-dir mashang_workspace/outputs/auto_launch/2026-07-01_aito_m7_launch
```

### 第 4 步：检查 report.md

产出的 `report.md` 可直接阅读。包含：
- 一句话结论
- 基本信息
- 已确认事实、推断、未确认说法
- 证据缺口
- 来源列表

### 第 5 步：后续动作

- 如需汇总，可手动整理到周报/月报
- 如需入库，等待后续 Phase（mashang-service 入库）

## 文件命名建议

```
mashang_workspace/outputs/auto_launch/
└── {YYYY-MM-DD}_{event_brand}_{event_model}_{event_type}/
    ├── raw_ai_output.json        ← 原始 AI 输出（来自 ChatGPT Plan）
    ├── normalized.json           ← 归一化后的统一结构 JSON
    ├── report.md                 ← 人类可读的 markdown 简报
    └── intake_manifest.json      ← 处理元数据（record_type / counts 等）
```

## 质量规则

| 规则 | 说明 |
|------|------|
| 无 source 不入库 | source_items 为空时 intake 直接失败 |
| 分类不混淆 | unconfirmed_claim 不得写入 confirmed_facts |
| 置信度不提升 | confidence_level 不允许自动提升 |
| 证据缺口保留 | missing_evidence 必须保留，不能删除 |
| 报告仅作简报 | report.md 只做渲染，不代表最终事实数据库 |

## 当前边界

| 能力 | 状态 |
|------|------|
| 搜索 | ❌ 不负责（由 ChatGPT Plan 完成） |
| API 调用 | ❌ 不负责 |
| 数据库 | ❌ 不负责 |
| 事实核验 | ❌ 不负责 |
| 人工判断替代 | ❌ 不替代 |
