# Auto Launch Promptbuilder

## 定位

**LS8 竞品销售动作日更监控器。** 这是竞品上市事件 Prompt Workflow Asset。

Auto Launch 是一个竞品销售动作发现 + 归类 + 证据 + 轻量影响判断的工作流资产，不是泛化的汽车新闻搜索工具，不是爬虫监控系统。

## 核心输入

| 资产 | 路径 |
|------|------|
| 竞品 watchlist | `configs/ls8_competitor_watchlist.csv` |
| 事件类型定义 | `configs/event_types.yaml` |
| 信源分层 | `configs/source_tiers.yaml` |
| 战场分类 | `configs/battle_fields.yaml` |

## 主链路

```
ls8_competitor_watchlist.csv
  ↓
event_types.yaml
  ↓
daily_sales_action_monitor.md  (ChatGPT Plan)
  ↓
event_candidates.json
  ↓
auto_launch intake workflow (validate → normalize → render)
  ↓
needs_review / accepted_event / ignored_event
  ↓
重要事件 → event_impact_vs_our_model.md
```

## Daily Monitor 能做什么

发现、归类、证据、轻量影响判断：

- 每天检查 LS8 竞品 watchlist 中车型是否发生销售动作
- 事件分类严格使用 `event_types.yaml`
- 车型范围严格限制在 watchlist
- 来源证据结构化（source_name / source_title / source_url 分离）
- 输出可进入 intake workflow 的 JSON
- Markdown 摘要只用于人读辅助

## Daily Monitor 不做什么

- ❌ 深度竞品分析报告
- ❌ 销量预测
- ❌ 传播声量分析
- ❌ 用户评论情绪分析
- ❌ 长篇报告生成
- ❌ 扩展到非 LS8 战场
- ❌ 自创 event_type

## 两阶段分析

```
第一阶段: daily_sales_action_monitor  →  发现事件
第二阶段: event_impact_vs_our_model   →  分析影响
```

不要把深度影响分析塞回 Daily Monitor。

## 输出格式

JSON 为主，Markdown 摘要为辅。

Daily Monitor 的主输出 JSON 遵循 `examples/daily_sales_action_monitor_output.json` 的结构。

Markdown 摘要只用于人读，不能替代 JSON。

## 质量要求

- event_type 必须来自 `event_types.yaml`，否则放入 `needs_review`
- 车型必须来自 watchlist，否则只能作为背景信息
- `source_name` 与 `source_title` 必须分开
- `source_url` 必须是纯 URL，不允许 Markdown 链接格式
- 不确定项目进入 `needs_review`
- 搜过但无事件的车型必须列入 `no_event_models`
- `impact_vs_our_model` 只做轻量压力判断（high / medium / low / unknown）

## 目录结构

```
promptbuilders/auto_launch/
├── README.md                        # 本文件
├── prompts/
│   ├── daily_sales_action_monitor.md   # 日更监控 Prompt（主入口）
│   └── event_impact_vs_our_model.md    # 单事件深度影响分析（impact_vs_our_model.md）
├── configs/
│   ├── ls8_competitor_watchlist.csv     # LS8 竞品 watchlist
│   ├── event_types.yaml                # 事件类型定义
│   ├── source_tiers.yaml               # 信源分层
│   ├── battle_fields.yaml              # 战场分类
│   └── target_profiles.yaml            # 目标车型画像
├── plan_templates/                   # ChatGPT Plan 任务描述
│   ├── chatgpt_plan_daily_radar.md
│   └── chatgpt_plan_event_48h.md
├── examples/                        # 实现脚本 + 示例（committed samples）
│   ├── daily_sales_action_monitor_input.md
│   ├── daily_sales_action_monitor_output.json
│   ├── daily_sales_action_monitor_summary.md
│   ├── legacy_promptbuilder_cases/   # 旧 promptbuilder 历史案例归档（非 regression 标准）
│   ├── legacy_ai_outputs/            # 旧 workflow 遗留 AI 返回参考
│   └── legacy_prompts/               # 旧 workflow 遗留 Prompt 参考
├── validators/                       # 校验与归一化
│   ├── validate_ai_response.py
│   └── normalize_ai_response.py
├── renderers/                        # 格式渲染
│   └── render_markdown_report.py
├── intake/                           # intake workflow
│   └── process_ai_output.py
├── indexers/                         # output index
│   └── build_output_index.py
├── runbooks/                         # 操作指南
│   ├── chatgpt_plan_handoff.md
│   ├── pilot_run_decision_gate.md
│   ├── volc_search_assisted_pilot.md
│   └── pilot_comparison_notes.md
├── schemas/                          # JSON Schema
│   ├── auto_launch_event.schema.json
│   └── auto_launch_brief.schema.json
├── search_adapters/                  # 可选搜索后端经验
│   ├── README.md
│   └── volc_search.md
└── templates/                        # 模板
    ├── search_task_prompt.md
    ├── evidence_schema.json
    └── pilot_quality_scorecard.md
```

## 快速参考

```bash
# 生成 Daily Monitor Prompt
# 使用 prompts/daily_sales_action_monitor.md

# 运行 intake
make auto-launch-intake SAMPLE=path/to/raw_ai_output.json OUT_DIR=path/to/output/

# 验证
make auto-launch-validate SAMPLE=path/to/output.json

# 生成索引
make auto-launch-index OUT_ROOT=mashang_workspace/outputs/auto_launch

# Volc-assisted 搜索（可选 deep dive 路径）
# 见 runbooks/volc_search_assisted_pilot.md
```

## 历史参考

旧 `auto_launch_monitor.py` 已下线。旧 `prompts/daily_radar.md` 等历史 Prompt 保留在目录中作为参考，不作为当前工作流的标准入口。当前 canonical 入口为 `prompts/daily_sales_action_monitor.md`。

## 边界规则

- `mashang_workspace/outputs/auto_launch/` **只用于新 intake workflow 的 runtime run directories**，默认不提交 git
- 可提交的样例、contract 应放在 `promptbuilders/auto_launch/examples/`
- `legacy_*` 目录下的历史案例来自旧 auto_launch_monitor / 旧 promptbuilder 的运行产物，**仅用于参考，不代表当前工作流的质量标准，不构成 regression 基准**
- 旧 auto_launch_monitor 和旧 promptbuilder 的遗留运行产物不得写入 `outputs/auto_launch/`
- 旧产物已清理或迁移至 `promptbuilders/auto_launch/examples/legacy_*`

## Pilot Run Decision Gate

当前暂无 golden cases。`examples/legacy_promptbuilder_cases/` **不是质量基准**。新的 golden case **必须来自真实 pilot run**，通过 `runbooks/pilot_run_decision_gate.md` 评估和 `templates/pilot_quality_scorecard.md` 人工评审后才考虑晋升。

## Future Golden Cases

- 当前暂无 golden cases
- 只有通过新 intake workflow、来源可追溯、业务判断被人工认可的案例，才可以晋升为 golden case
- Golden cases 未来应单独建立 registry，而不是直接复用 legacy cases
