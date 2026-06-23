# Mashang Workspace Capability Inventory

Workspace 能力总览：skills / scripts / data assets / outputs / evaluation

生成时间：2026-06-23 03:02:32
Workspace：mashang_workspace

---

## Summary

| 能力类型 | 数量 |
|---------|------|
| Skills（Agent 会什么） | 3 |
| Scripts（Agent 能调用什么） | 39 |
| Data Assets（Agent 能查什么） | 6 |
| Outputs / Reports（Agent 已沉淀什么） | 42 |
| Evaluation / Quality（Agent 是否可靠） | 6 |

---

## skills. Skills：Agent 会什么

Agent 可以通过 skill 匹配识别任务类型、选择执行方式、调用对应脚本和模板。每个 skill 包含 SKILL.md 指令文件，指导 Agent 如何响应特定场景。

| # | 名称 | 描述 | 状态 |
|---|------|------|------|
| 1 | branded-html-report | 生成 mashang_workspace 专属的品牌化 HTML 数据报告，适用于汽车市场洞察、销量预测、锁单释放曲线、模型回测和经营分析报告。... | active |
| 2 | monthly-market-report | workspace 层的月度汽车市场报告生成 Skill。基于 passenger_insurance 现有 6 张预聚合单表，按月运行 24 ... | active |
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
| 7 | skills_atp_price.py |  | active |
| 8 | user_profile.py |  | active |
| 9 | auto_launch_monitor.py |  | active |
| 10 | cohort_forecast.py |  | active |
| 11 | lock_predict_backtest.py |  | active |
| 12 | lock_release_curve.py |  | active |
| 13 | ls8_battery_weekly_share_report.py |  | active |
| 14 | ls8_weekly_model_share.py |  | active |
| 15 | market_report/run_monthly_market_report.py |  | active |
| 16 | miit_new_car/check_text_extractors.py |  | active |
| 17 | miit_new_car/diagnose_attachment_urls.py |  | active |
| 18 | miit_new_car/diff_watchlist.py |  | active |
| 19 | miit_new_car/discover_batches.py |  | active |
| 20 | miit_new_car/extract_attachment_text.py |  | active |
| 21 | miit_new_car/fetch_batch.py |  | active |
| 22 | miit_new_car/http_utils.py |  | active |
| 23 | miit_new_car/monitor.py |  | active |
| 24 | miit_new_car/parse_product_list.py |  | active |
| 25 | miit_new_car/parse_products.py |  | active |
| 26 | passenger_insurance/check_passenger_insurance_asset.py |  | active |
| 27 | quick_lock_ratio.py |  | active |
| 28 | release_curve_analysis.py |  | active |
| 29 | structured_business_forecast.py | 脚本作用：
1) 基于日度矩阵（index_summary_daily_matrix）做结构化业务预测，核心恒等式为 lock_orders =... | active |
| 30 | build_daily_matrix.py |  | active |
| 31 | build_workspace_capability_inventory.py |  | active |
| 32 | build_workspace_skills_catalog.py |  | active |
| 33 | data_dictionary.py |  | active |
| 34 | dataset_validate.py |  | active |
| 35 | generate_eval_cases.py |  | active |
| 36 | render_html_report.py |  | active |
| 37 | skills_attainment_rate_alert.py |  | active |
| 38 | skills_order_observation_daily.py |  | active |
| 39 | voc_theme_analysis.py |  | active |

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
| 1 | .DS_Store | other · 10.0 KB | generated |
| 2 | agent_execution_trace.md | markdown report · 5.4 KB | generated |
| 3 | atp_2026-04.html | html report · 7.7 KB | generated |
| 4 | atp_2026-05.html | html report · 7.7 KB | generated |
| 5 | auto_launch_monitor_2026-06-01_2026-06-17.md | markdown report · 8.7 KB | generated |
| 6 | auto_launch_monitor_2026-06-05_2026-06-07.json | json contract · 2.4 KB | generated |
| 7 | auto_launch_monitor_2026-06-05_2026-06-07.md | markdown report · 4.2 KB | generated |
| 8 | auto_launch_monitor_2026-06-17_2026-06-17.md | markdown report · 6.7 KB | generated |
| 9 | daily_msg_report.html | html report · 25.8 KB | generated |
| 10 | followup_trace_ls8_city.md | markdown report · 9.4 KB | generated |
| 11 | june_2026_forecast.html | html report · 5.9 KB | generated |
| 12 | lock_predict_backtest.html | html report · 34.4 KB | generated |
| 13 | lock_release_curve.html | html report · 74.0 KB | generated |
| 14 | ls8_battery_weekly_share.html | html report · 2950.1 KB | generated |
| 15 | ls8_city_distribution_2026-06-14.html | html report · 11.8 KB | generated |
| 16 | ls8_city_distribution_report.html | html report · 9.4 KB | generated |
| 17 | ls8_user_profile_20260401_20260621.html | html report · 8.3 KB | generated |
| 18 | ls8_user_profile_20260401_20260621.md | markdown report · 1.7 KB | generated |
| 19 | passenger_insurance_workspace_smoke.md | markdown report · 1.1 KB | generated |
| 20 | pk_weekly_compare_ls8_ls9.html | html report · 66.1 KB | generated |
| 21 | quick_lock_ratio.html | html report · 638.5 KB | generated |
| 22 | w24_weekend_analysis.html | html report · 19.3 KB | generated |
| 23 | w24_weekend_analysis.md | markdown report · 4.1 KB | generated |
| 24 | workspace_capability_inventory.html | html report · 37.3 KB | generated |
| 25 | workspace_capability_inventory.json | json contract · 48.7 KB | generated |
| 26 | workspace_capability_inventory.md | markdown report · 9.2 KB | generated |
| 27 | workspace_skills_catalog.html | html report · 14.1 KB | generated |
| 28 | workspace_skills_catalog.json | json contract · 3.9 KB | generated |
| 29 | workspace_skills_catalog.md | markdown report · 3.5 KB | generated |
| 30 | 竞争洞察A3人群流转.html | html report · 4934.7 KB | generated |
| 31 | 2026-02/query_results.json | 月报 · 2026-02 · 21.1 KB | generated |
| 32 | 2026-02/report_draft.md | 月报 · 2026-02 · 8.7 KB | generated |
| 33 | 2026-02/run_metadata.json | 月报 · 2026-02 · 0.6 KB | generated |
| 34 | 2026-03/query_results.json | 月报 · 2026-03 · 497.1 KB | generated |
| 35 | 2026-03/report_draft.md | 月报 · 2026-03 · 15.8 KB | generated |
| 36 | 2026-03/run_metadata.json | 月报 · 2026-03 · 0.6 KB | generated |
| 37 | 2026-05/query_results.json | 月报 · 2026-05 · 501.5 KB | generated |
| 38 | 2026-05/report_draft.md | 月报 · 2026-05 · 15.9 KB | generated |
| 39 | 2026-05/run_metadata.json | 月报 · 2026-05 · 0.6 KB | generated |
| 40 | 2026-12/query_results.json | 月报 · 2026-12 · 21.1 KB | generated |
| 41 | 2026-12/report_draft.md | 月报 · 2026-12 · 8.7 KB | generated |
| 42 | 2026-12/run_metadata.json | 月报 · 2026-12 · 0.6 KB | generated |

---

## evaluation. Evaluation / Quality：Agent 是否可靠

Agent 能力的质量保障体系，包括统一 Eval 框架、上下文解析评测、多轮追问评测、数值校验、pytest 测试套件和回归测试记录。

| # | 名称 | 描述 | 状态 |
|---|------|------|------|
| 1 | eval_suites | 统一 Eval 框架，6 suites。 | active |
| 2 | context_parser | 自然语言 → 结构化 context。 | active |
| 3 | followup_runner | 多轮追问评测。 | active |
| 4 | pytest_tests | 21 个测试文件的 pytest 套件。 | active |
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
