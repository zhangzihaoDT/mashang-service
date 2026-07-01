# Intake — AI Output Intake Workflow

## 定位

Intake 是 Auto Launch 的**统一入口层**。

当 ChatGPT Plan / DeepSeek / 任意 AI 输出 JSON 格式的竞品情报后，通过 intake 完整执行：

```
AI Output JSON → validate → normalize → markdown report
```

## 输入

符合 `schemas/auto_launch_event.schema.json` 或 `schemas/auto_launch_brief.schema.json` 结构的 JSON 文件。

## 输出

| 产出 | 路径（示例） | 说明 |
|------|-------------|------|
| normalized JSON | `examples/normalized/event_48h_sample.normalized.json` | 统一结构的标准化 JSON |
| markdown report | `examples/reports/event_48h_sample.md` | 人类可读的简报 |

## process_ai_output.py

### 用法

```bash
python intake/process_ai_output.py path/to/ai_output.json \
    --normalized-output path/to/normalized.json \
    --report-output path/to/report.md
```

### 流程

1. **validate**：调用 `validators/validate_ai_response.py` 的校验逻辑，检查必填字段、来源完整性
2. **normalize**：调用 `validators/normalize_ai_response.py` 的归一化逻辑，输出统一结构 JSON
3. **render**：调用 `renderers/render_markdown_report.py` 的渲染逻辑，输出 markdown 简报

### 失败处理

任何一步失败都会停止处理并返回非 0 exit code：
- validate 失败 → 打印失败报告
- normalize 失败 → sys.exit(1)
- render 失败 → sys.exit(1)

## 与 ChatGPT Plan 的关系

Intake 是 ChatGPT Plan **之后**的环节：

```
ChatGPT Plan → AI Output JSON → intake (validate → normalize → render) → 人工使用/入库
```

Intake 不负责：
- 搜索
- 事实核验
- 数据库入库

## 与 mashang-service 的关系

Intake 是 mashang-service **之前**的环节：

```
intake → normalized JSON → mashang-service（入库、复盘、报告沉淀）
```

当前 Phase 4 只做到 intak 生成 normalized JSON 和 markdown。后续 Phase 会将 normalized JSON 接入 mashang-service。
