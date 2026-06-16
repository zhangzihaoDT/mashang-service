# Mashang Workspace Capability Inventory

Workspace 能力总览：skills / scripts / data assets / outputs / evaluation

生成时间：2026-06-16 08:05:24
Workspace：mashang_workspace

---

## Summary

| 能力类型 | 数量 |
|---------|------|
| Skills（Agent 会什么） | 3 |
| Scripts（Agent 能调用什么） | 27 |
| Data Assets（Agent 能查什么） | 6 |
| Outputs / Reports（Agent 已沉淀什么） | 35 |
| Evaluation / Quality（Agent 是否可靠） | 6 |

---

## skills. Skills：Agent 会什么

Agent 可以通过 skill 匹配识别任务类型、选择执行方式、调用对应脚本和模板。每个 skill 包含 SKILL.md 指令文件，指导 Agent 如何响应特定场景。

| # | 名称 | 描述 | 状态 |
|---|------|------|------|
| 1 | branded-html-report | 将汽车经营分析、预测模型、回测评估、市场洞察等结果，渲染为具有 Raccoon Research / mashang 风格的 HTML 数据报告。 | active |
| 2 | monthly-market-report | monthly-market-report v0.1 是基于 `passenger_insurance` 现有 6 张预聚合单表的月度汽车市场固... | active |
| 3 | runtime-eval-diagnosis | Diagnose mashang runtime eval reports, including hard_pass, soft_pass, f... | active |

---

## scripts. Scripts：Agent 能调用什么

Agent 可直接调用的 Python 脚本，按功能分为 runtime（稳定运行入口）、research（研究分析）、utility（工具/渲染/验证）和 legacy（历史保留）四类。

| # | 名称 | 描述 | 状态 |
|---|------|------|------|
| 1 | assign_conversion_analysis.py |  | active |
| 2 | atp_price_report.py |  | active |
| 3 | attribute_penetration_report.py |  | active |
| 4 | daily_lock_count.py |  | active |
| 5 | lock_by_model.py |  | active |
| 6 | lock_city_distribution.py |  | active |
| 7 | cohort_forecast.py |  | active |
| 8 | lock_predict_backtest.py |  | active |
| 9 | lock_release_curve.py |  | active |
| 10 | ls8_battery_weekly_share_report.py |  | active |
| 11 | ls8_weekly_model_share.py |  | active |
| 12 | market_report/run_monthly_market_report.py |  | active |
| 13 | passenger_insurance/check_passenger_insurance_asset.py |  | active |
| 14 | quick_lock_ratio.py |  | active |
| 15 | release_curve_analysis.py |  | active |
| 16 | structured_business_forecast.py | 脚本作用：
1) 基于日度矩阵（index_summary_daily_matrix）做结构化业务预测，核心恒等式为 lock_orders =... | active |
| 17 | build_daily_matrix.py |  | active |
| 18 | build_workspace_capability_inventory.py |  | active |
| 19 | build_workspace_skills_catalog.py |  | active |
| 20 | data_dictionary.py |  | active |
| 21 | dataset_validate.py |  | active |
| 22 | generate_eval_cases.py |  | active |
| 23 | render_html_report.py |  | active |
| 24 | skills_attainment_rate_alert.py |  | active |
| 25 | skills_order_observation_daily.py |  | active |
| 26 | voc_theme_analysis.py |  | active |
| 27 | skills_atp_price.py |  | legacy |

---

## data_assets. Data Assets：Agent 能查什么

Agent 可查询的数据来源，包括 dataset/ 下的原始数据文件、shared loader 接入的 service 级数据资产、以及 config 目录下的配置规范。

| # | 名称 | 描述 | 状态 |
|---|------|------|------|
| 1 | passenger_insurance | 乘用车上险数据（6 张 Parquet 表），workspace 通过 shared loaders 消费。 | active |
| 2 | order_data | 订单主表，含锁单/交付/开票/退订时间戳。 | active |
| 3 | assign_data | 下发线索表，含渠道拆解和转化分析。 | active |
| 4 | config_attribute | 选配属性表，用于配置渗透率分析。 | active |
| 5 | monthly_market_report_queries | 24 个固定月报查询的 YAML 规范。 | active |
| 6 | wechat_sync | 微信群消息，VOC 情感/主题挖掘。 | active |

---

## outputs. Outputs / Reports：Agent 已沉淀什么

Agent 执行后沉淀的输出成果，包括 reports/ 下的品牌化 HTML 报告、Markdown 分析和 JSON 数据契约，以及 monthly_market_report/ 下的月报数据底稿。

| # | 名称 | 描述 | 状态 |
|---|------|------|------|
| 1 | agent_execution_trace.md | markdown report · 5.4 KB | generated |
| 2 | atp_2026-04.html | html report · 7.7 KB | generated |
| 3 | atp_2026-05.html | html report · 7.7 KB | generated |
| 4 | daily_msg_report.html | html report · 25.8 KB | generated |
| 5 | followup_trace_ls8_city.md | markdown report · 9.4 KB | generated |
| 6 | june_2026_forecast.html | html report · 5.9 KB | generated |
| 7 | lock_predict_backtest.html | html report · 34.4 KB | generated |
| 8 | lock_release_curve.html | html report · 74.0 KB | generated |
| 9 | ls8_battery_weekly_share.html | html report · 2950.1 KB | generated |
| 10 | ls8_city_distribution_2026-06-14.html | html report · 11.8 KB | generated |
| 11 | ls8_city_distribution_report.html | html report · 9.4 KB | generated |
| 12 | passenger_insurance_workspace_smoke.md | markdown report · 1.1 KB | generated |
| 13 | pk_weekly_compare_ls8_ls9.html | html report · 66.1 KB | generated |
| 14 | quick_lock_ratio.html | html report · 638.5 KB | generated |
| 15 | w24_weekend_analysis.html | html report · 19.3 KB | generated |
| 16 | w24_weekend_analysis.md | markdown report · 4.1 KB | generated |
| 17 | workspace_capability_inventory.html | html report · 32.8 KB | generated |
| 18 | workspace_capability_inventory.json | json contract · 35.2 KB | generated |
| 19 | workspace_capability_inventory.md | markdown report · 7.0 KB | generated |
| 20 | workspace_skills_catalog.html | html report · 16.2 KB | generated |
| 21 | workspace_skills_catalog.json | json contract · 4.0 KB | generated |
| 22 | workspace_skills_catalog.md | markdown report · 3.6 KB | generated |
| 23 | 竞争洞察A3人群流转.html | html report · 4934.7 KB | generated |
| 24 | 2026-02/query_results.json | 月报 · 2026-02 · 21.1 KB | generated |
| 25 | 2026-02/report_draft.md | 月报 · 2026-02 · 8.7 KB | generated |
| 26 | 2026-02/run_metadata.json | 月报 · 2026-02 · 0.6 KB | generated |
| 27 | 2026-03/query_results.json | 月报 · 2026-03 · 497.1 KB | generated |
| 28 | 2026-03/report_draft.md | 月报 · 2026-03 · 15.8 KB | generated |
| 29 | 2026-03/run_metadata.json | 月报 · 2026-03 · 0.6 KB | generated |
| 30 | 2026-05/query_results.json | 月报 · 2026-05 · 21.1 KB | generated |
| 31 | 2026-05/report_draft.md | 月报 · 2026-05 · 8.7 KB | generated |
| 32 | 2026-05/run_metadata.json | 月报 · 2026-05 · 0.6 KB | generated |
| 33 | 2026-12/query_results.json | 月报 · 2026-12 · 21.1 KB | generated |
| 34 | 2026-12/report_draft.md | 月报 · 2026-12 · 8.7 KB | generated |
| 35 | 2026-12/run_metadata.json | 月报 · 2026-12 · 0.6 KB | generated |

---

## evaluation. Evaluation / Quality：Agent 是否可靠

Agent 能力的质量保障体系，包括统一 Eval 框架、上下文解析评测、多轮追问评测、数值校验、pytest 测试套件和回归测试记录。

| # | 名称 | 描述 | 状态 |
|---|------|------|------|
| 1 | eval_suites | 统一 Eval 框架，6 suites。 | active |
| 2 | context_parser | 自然语言 → 结构化 context。 | active |
| 3 | followup_runner | 多轮追问评测。 | active |
| 4 | pytest_tests | 19 个测试文件的 pytest 套件。 | active |
| 5 | cached_eval_report | 缓存的 Eval 报告（5 suites, N/A） | generated |
| 6 | regression_notes | Regression 测试文档。 | generated |

---

## Recommended Workflow

- 1. 用户提出业务问题
- 2. Agent 根据 Skill 判断任务类型
- 3. Skill 调度对应 scripts
- 4. scripts 消费 data assets
- 5. outputs 沉淀报告 / JSON / Markdown / HTML
- 6. tests / eval 验证能力稳定性

## Notes

- JSON 为唯一事实源（Single Source of Truth），Markdown 与 HTML 从 JSON 渲染。
- outputs/ 下的文件仅展示文件名、类型、大小和生成时间，不读取文件内容。
- dataset/ 下的数据资产仅展示逻辑路径和元信息，不读取原始数据文件。
- 本 inventory 由脚本自动生成，对应脚本路径：mashang_workspace/utility_scripts/build_workspace_capability_inventory.py
