# Pilot Run Decision Gate

## 目的

本 runbook 用于评估一次真实 Plan / Volc Search 的输出是否达到 future golden case 标准。

当前 auto_launch 项目尚无 golden cases。`examples/legacy_promptbuilder_cases/` 目录下的历史案例来自旧 auto_launch_monitor / 旧 promptbuilder 的运行产物，**仅用于参考，不代表当前工作流的质量标准，不构成 regression 基准**。

新的 golden case 必须来自真实的 pilot run，且通过人工质量评审。

## 推荐 pilot 输入

建议先选择一个明确、边界清楚的任务，例如：

- event_model: 问界 M7
- our_model: 智己 LS8
- event_type: launch / price_update / configuration_update
- time_window: 48h 或 72h
- battle_field: large_six_seat_suv

注意：不要被本示例限制。可以根据当前关注车型选择更合适的 pilot。

## 两种 pilot 来源

### A. ChatGPT Plan / 手动 AI 输出

流程：

1. 打开 `plan_templates/chatgpt_plan_event_48h.md`，替换占位符
2. 将内容复制到 ChatGPT Plan（或直接粘贴到 DeepSeek / ChatGPT）
3. 要求 Plan 以 JSON 格式输出
4. 将输出保存为 `raw_ai_output.json`
5. 运行 intake：

```bash
make auto-launch-intake \
  SAMPLE=path/to/raw_ai_output.json \
  OUT_DIR=mashang_workspace/outputs/auto_launch/{run_id}
```

### B. Volc Search assisted

流程：

1. 先用火山搜索获得候选信息（当前不实现完整 runner，需手动调用或复制搜索结果）
2. 结合 `prompts/event_48h_brief.md` 或 `impact_vs_our_model.md` 的格式要求
3. 将结果整理为 JSON 格式
4. 保存为 `raw_ai_output.json`
5. 运行 intake（同上）

说明：本轮不实现 Volc Search runner。Volc Search 仅作为候选信息来源，不承担事件判断。

## 推荐 output-dir 命名

```
mashang_workspace/outputs/auto_launch/{YYYY-MM-DD}_{event_brand}_{event_model}_{time_window}_vs_{our_model}/
```

例如：

```
mashang_workspace/outputs/auto_launch/2026-07-01_wenjie_m7_48h_vs_ls8/
```

目录内应生成：

- `raw_ai_output.json`
- `normalized.json`
- `report.md`
- `intake_manifest.json`

## Pilot 质量判断标准

### 必须满足的结构要求

| 检查项 | 标准 |
|--------|------|
| validate passed | intake 无报错 |
| source_items | ≥ 3 条，至少 1 条 Tier 1 或 2 条 Tier 2 |
| confirmed_facts | 每条有来源支撑 |
| inference | 明确标注，不冒充事实 |
| unconfirmed_claims | 单独隔离，不混入 confirmed_facts |
| missing_evidence | 真实记录证据缺口，不为空 |
| confidence_level | 保守（不擅自给 high） |

### 业务质量评分 (1-5)

| 维度 | 说明 |
|------|------|
| source quality | 来源权威性、多样性 |
| fact / inference separation | 事实与推断边界清晰 |
| impact analysis depth | 覆盖价格、配置、空间、续航、补能、智驾、品牌/传播 |
| sales response usefulness | 销售建议是否业务可用 |
| uncertainty handling | 不确定项是否诚实披露 |
| report readability | report.md 能否直接进入业务复盘 |
| reuse value | 该案例能否代表典型任务场景 |

### report.md 验收标准

- 人阅读后是否认可结论质量
- 是否有充分的来源支撑
- 证据缺口是否诚实
- 后续追踪建议是否合理

## 晋升 future golden case 的条件

只有同时满足以下条件，才可以晋升为 golden case：

1. 通过 validate / normalize / intake（无报错）
2. 来源可追溯（每条 confirmed_fact 有 URL，Tier 1 或 Tier 2）
3. 人工认可业务判断（reviewer 签署 scorecard）
4. 没有把 unconfirmed_claim 当作 confirmed_fact
5. report.md 有复用价值（可作为同类事件的参考模板）
6. normalized.json 结构稳定（无 schema 变动风险）
7. 能代表一个典型任务场景（如：竞品上市对本品的 48h 影响评估）

## 不通过时怎么处理

如果 pilot 输出质量一般：

- 保留在 `mashang_workspace/outputs/auto_launch/` 作为运行产物，不删除
- 不迁移到 `promptbuilders/auto_launch/examples/`
- 不进入 golden case
- 记录问题，例如：

| 常见问题 | 示例 |
|----------|------|
| source 不足 | 仅 1 条 Tier 3 来源，无交叉验证 |
| impact 维度缺失 | 缺少价格、配置对比 |
| 结论泛化 | "竞品很强" 而非具体分析 |
| 销售建议不可用 | "建议持续关注" 而非 actionable 建议 |
| 证据缺口虚假 | missing_evidence 为空或明显遗漏关键信息 |
