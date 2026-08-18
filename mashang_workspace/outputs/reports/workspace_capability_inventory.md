# Mashang Workspace Capability Inventory

Workspace 能力总览：skills / scripts / data assets / outputs / evaluation

生成时间：2026-08-18 04:40:32
Workspace：mashang_workspace

---

## Summary

| 能力类型 | 数量 |
|---------|------|
| Skills（Agent 会什么） | 4 |
| Scripts（Agent 能调用什么） | 60 |
| Data Assets（Agent 能查什么） | 6 |
| Outputs / Reports（Agent 已沉淀什么） | 82 |
| Evaluation / Quality（Agent 是否可靠） | 6 |

---

## skills. Skills：Agent 会什么

Agent 可以通过 skill 匹配识别任务类型、选择执行方式、调用对应脚本和模板。每个 skill 包含 SKILL.md 指令文件，指导 Agent 如何响应特定场景。

| # | 名称 | 描述 | 状态 |
|---|------|------|------|
| 1 | branded-html-report | 生成 mashang_workspace 专属的品牌化 HTML 数据报告，适用于汽车市场洞察、销量预测、锁单释放曲线、模型回测和经营分析报告。... | active |
| 2 | cpca-weekly-data-capture | 第一时间捕捉乘联分会周度核心数据，并生成带置信度的三句话 fact_result JSON | active |
| 3 | monthly-market-report | workspace 层的月度汽车市场报告生成 Skill。基于 TP&MIX-ways 现有 6 张预聚合单表，按月运行 24 个固定月报查询问... | active |
| 4 | runtime-eval-diagnosis | Diagnose mashang runtime eval reports, including hard_pass, soft_pass, f... | active |

---

## scripts. Scripts：Agent 能调用什么

Agent 可直接调用的 Python 脚本，按功能分为 runtime（稳定运行入口）、research（研究分析）、utility（工具/渲染/验证）和 legacy（历史保留）四类。

| # | 名称 | 描述 | 状态 |
|---|------|------|------|
| 1 | assign_conversion_analysis.py |  | active |
| 2 | atp_price_report.py |  | active |
| 3 | attribute_penetration_report.py |  | active |
| 4 | config_decision_engine.py |  | active |
| 5 | current_state_diagnosis.py |  | active |
| 6 | daily_dc_inventory_change.py |  | active |
| 7 | daily_lock_count.py |  | active |
| 8 | lock_by_model.py |  | active |
| 9 | lock_city_distribution.py |  | active |
| 10 | user_profile.py |  | active |
| 11 | backlog_rate_trend_report.py |  | active |
| 12 | benchmark_conversion_trend.py |  | active |
| 13 | brand_shipments_analysis.py |  | active |
| 14 | brand_shipments_report.py | Brand Shipments 报告 — 基于 brand_shipments_analysis.py 动态计算生成 HTML 报告. | active |
| 15 | cohort_forecast.py |  | active |
| 16 | competition_a3_flow.py | 竞争洞察 A3 人群流转分析 — 情报报告 | active |
| 17 | cpca_weekly_early_signal.py | 乘联分会周度数据早源监控 — Period-Aware | active |
| 18 | dc_inventory_trend_report.py |  | active |
| 19 | dc_showroom_age_report.py |  | active |
| 20 | invoice_monthly_forecast.py |  | active |
| 21 | l6_m2_presale_metrics_to_feishu.py |  | active |
| 22 | launch_risk_snapshot.py |  | active |
| 23 | lock_attribution_analysis.py |  | active |
| 24 | lock_predict_backtest.py |  | active |
| 25 | lock_release_curve.py |  | active |
| 26 | ls8_battery_weekly_share_report.py |  | active |
| 27 | ls8_configuration_selection_report.py |  | active |
| 28 | ls9_battery_weekly_share_report.py |  | active |
| 29 | ls9_hyper_synthetic_control_impact.py | name: ls9_hyper_synthetic_control_impact
 | active |
| 30 | ls9_interior_option_report.py |  | active |
| 31 | ls9_lock_trend_hyper_vs_non.py | name: ls9_lock_trend_hyper_vs_non
 | active |
| 32 | market_report/generate_monthly_brief.py |  | active |
| 33 | market_report/run_monthly_market_report.py |  | active |
| 34 | model_order_monthly_compare_report.py |  | active |
| 35 | model_share_trend.py |  | active |
| 36 | pk_weekly_ls8_ls9.py | name: pk_weekly_compare_ls8_ls9
use: python research_scripts/pk_weekly_l... | active |
| 37 | presale_comparison_report.py |  | active |
| 38 | presale_performance_compare.py |  | active |
| 39 | quick_lock_ratio.py |  | active |
| 40 | release_curve_analysis.py |  | active |
| 41 | saic_group_order_daily_parse.py |  | active |
| 42 | saic_sales_profile_report.py |  | active |
| 43 | stalled_order_forecast.py |  | active |
| 44 | structured_business_forecast.py | 脚本作用：
1) 基于日度矩阵（index_summary_daily_matrix）做结构化业务预测，核心恒等式为 lock_orders =... | active |
| 45 | tp_and_mix_ways/check_tp_and_mix_ways_asset.py |  | active |
| 46 | build_config_semantics.py |  | active |
| 47 | build_daily_matrix.py |  | active |
| 48 | build_lock_trend_report.py |  | active |
| 49 | build_workspace_capability_inventory.py |  | active |
| 50 | build_workspace_skills_catalog.py |  | active |
| 51 | config_code_normalization.py |  | active |
| 52 | data_dictionary.py |  | active |
| 53 | dataset_validate.py |  | active |
| 54 | generate_delivery_inventory_report.py |  | active |
| 55 | generate_eval_cases.py |  | active |
| 56 | render_html_report.py |  | active |
| 57 | skills_attainment_rate_alert.py |  | active |
| 58 | skills_order_observation_daily.py |  | active |
| 59 | skills_store_lock_alert.py |  | active |
| 60 | voc_theme_analysis.py |  | active |

---

## data_assets. Data Assets：Agent 能查什么

Agent 可查询的数据来源，包括 dataset/ 下的原始数据文件、shared loader 接入的 service 级数据资产、以及 config 目录下的配置规范。

| # | 名称 | 描述 | 状态 |
|---|------|------|------|
| 1 | tp_and_mix_ways | 乘用车上险数据（6 张 Parquet 表），workspace 通过 shared loaders 消费。 | active |
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
| 1 | .DS_Store | other · 14.0 KB | generated |
| 2 | CDG_2026-06_lock.html | html report · 7.3 KB | generated |
| 3 | CDG_2026-07_lock.html | html report · 7.3 KB | generated |
| 4 | LS8_week_model_report_20260626.html | html report · 30.4 KB | generated |
| 5 | LS9_month_model_report_20260626.html | html report · 24.3 KB | generated |
| 6 | _ma7_test.html | html report · 90.1 KB | generated |
| 7 | agent_execution_trace.md | markdown report · 5.4 KB | generated |
| 8 | atp_2026-04.html | html report · 7.7 KB | generated |
| 9 | atp_2026-05.html | html report · 7.7 KB | generated |
| 10 | atp_2026-06.html | html report · 7.6 KB | generated |
| 11 | atp_2026-07.html | html report · 7.6 KB | generated |
| 12 | audience_evolution_2026.html | html report · 149.0 KB | generated |
| 13 | audience_evolution_2026.md | markdown report · 43.5 KB | generated |
| 14 | audience_evolution_2026_digest.html | html report · 54.2 KB | generated |
| 15 | audience_evolution_2026_digest.md | markdown report · 16.6 KB | generated |
| 16 | auto_launch_monitor_2026-06-05_2026-06-07.md | markdown report · 3.5 KB | generated |
| 17 | backlog_rate_history_20260816.html | html report · 294.8 KB | generated |
| 18 | benchmark_conversion_trend.html | html report · 22.1 KB | generated |
| 19 | brand_marketing_timeline_0716_0720.html | html report · 8.8 KB | generated |
| 20 | brand_shipments_2026H1.html | html report · 13.9 KB | generated |
| 21 | causal_impact_ls9_hyper.html | html report · 9.1 KB | generated |
| 22 | cm2_user_profile_report.html | html report · 34.9 KB | generated |
| 23 | cpca_weekly_early_signal.html | html report · 40.0 KB | generated |
| 24 | daily_msg_report.html | html report · 25.8 KB | generated |
| 25 | dc_inventory_trend.html | html report · 271.2 KB | generated |
| 26 | dc_showroom_age_2026-08-05.html | html report · 12.4 KB | generated |
| 27 | dc_showroom_age_report_20260805.html | html report · 8.1 KB | generated |
| 28 | delivery_inventory_analysis_report.md | markdown report · 4.8 KB | generated |
| 29 | followup_trace_ls8_city.md | markdown report · 9.4 KB | generated |
| 30 | june_2026_forecast.html | html report · 5.9 KB | generated |
| 31 | launch_risk_snapshot_20260816.html | html report · 9.7 KB | generated |
| 32 | lock_attribution_2023-01-01_2023-12-31.html | html report · 9.1 KB | generated |
| 33 | lock_attribution_compare_2024-01-01_2024-08-01_vs_2026-01-01_2026-08-01.html | html report · 12.1 KB | generated |
| 34 | lock_attribution_compare_2024-01-01_2024-12-31_vs_2026-01-01_2026-12-31.html | html report · 11.9 KB | generated |
| 35 | lock_predict_backtest.html | html report · 424.9 KB | generated |
| 36 | lock_release_curve.html | html report · 75.4 KB | generated |
| 37 | lock_trend_report.html | html report · 220.9 KB | generated |
| 38 | ls8_battery_weekly_share.html | html report · 2960.7 KB | generated |
| 39 | ls8_city_distribution_2026-06-14.html | html report · 11.8 KB | generated |
| 40 | ls8_city_distribution_report.html | html report · 9.4 KB | generated |
| 41 | ls8_configuration_selection_since_launch.html | html report · 9.5 KB | generated |
| 42 | ls9_battery_weekly_share.html | html report · 2943.8 KB | generated |
| 43 | ls9_hyper_synthetic_control_impact.html | html report · 8.9 KB | generated |
| 44 | ls9_interior_option_report.html | html report · 11.9 KB | generated |
| 45 | ls9_lock_trend_hyper_comparison.html | html report · 90.9 KB | generated |
| 46 | miit_dual_vehicle_compare.html | html report · 9.5 KB | generated |
| 47 | model_order_monthly_compare.html | html report · 9.1 KB | generated |
| 48 | pk_weekly_compare_ls8_ls9.html | html report · 29.0 KB | generated |
| 49 | presale_small_deposit_compare.html | html report · 13.2 KB | generated |
| 50 | quick_lock_ratio.html | html report · 683.3 KB | generated |
| 51 | store_bloc_distribution.md | markdown report · 8.7 KB | generated |
| 52 | store_lock_alert_report.md | markdown report · 2.3 KB | generated |
| 53 | tesla_wholesale_export_report.html | html report · 25.3 KB | generated |
| 54 | tp_and_mix_ways_workspace_smoke.md | markdown report · 1.1 KB | generated |
| 55 | w24_weekend_analysis.html | html report · 19.3 KB | generated |
| 56 | w24_weekend_analysis.md | markdown report · 4.1 KB | generated |
| 57 | workspace_capability_inventory.html | html report · 51.0 KB | generated |
| 58 | workspace_capability_inventory.json | json contract · 78.4 KB | generated |
| 59 | workspace_capability_inventory.md | markdown report · 13.7 KB | generated |
| 60 | workspace_skills_catalog.html | html report · 16.9 KB | generated |
| 61 | workspace_skills_catalog.json | json contract · 5.4 KB | generated |
| 62 | workspace_skills_catalog.md | markdown report · 4.7 KB | generated |
| 63 | 上汽销售库存流转探查.html | html report · 19.4 KB | generated |
| 64 | 小鹏_product_line.md | markdown report · 7.3 KB | generated |
| 65 | 日频综合声量指数_折线图.html | html report · 50.4 KB | generated |
| 66 | 智己_product_line.md | markdown report · 2.7 KB | generated |
| 67 | 竞争洞察A3人群流转.html | html report · 416.8 KB | generated |
| 68 | 阿维塔_product_line.md | markdown report · 2.6 KB | generated |
| 69 | 2026-02/query_results.json | 月报 · 2026-02 · 21.2 KB | generated |
| 70 | 2026-02/query_results.xlsx | 月报 · 2026-02 · 22.5 KB | generated |
| 71 | 2026-02/report_draft.md | 月报 · 2026-02 · 8.7 KB | generated |
| 72 | 2026-02/run_metadata.json | 月报 · 2026-02 · 0.6 KB | generated |
| 73 | 2026-03/query_results.json | 月报 · 2026-03 · 497.1 KB | generated |
| 74 | 2026-03/report_draft.md | 月报 · 2026-03 · 15.8 KB | generated |
| 75 | 2026-03/run_metadata.json | 月报 · 2026-03 · 0.6 KB | generated |
| 76 | 2026-05/query_results.json | 月报 · 2026-05 · 501.5 KB | generated |
| 77 | 2026-05/report_draft.md | 月报 · 2026-05 · 15.9 KB | generated |
| 78 | 2026-05/run_metadata.json | 月报 · 2026-05 · 0.6 KB | generated |
| 79 | 2026-12/query_results.json | 月报 · 2026-12 · 21.2 KB | generated |
| 80 | 2026-12/query_results.xlsx | 月报 · 2026-12 · 22.5 KB | generated |
| 81 | 2026-12/report_draft.md | 月报 · 2026-12 · 8.7 KB | generated |
| 82 | 2026-12/run_metadata.json | 月报 · 2026-12 · 0.6 KB | generated |

---

## evaluation. Evaluation / Quality：Agent 是否可靠

Agent 能力的质量保障体系，包括统一 Eval 框架、上下文解析评测、多轮追问评测、数值校验、pytest 测试套件和回归测试记录。

| # | 名称 | 描述 | 状态 |
|---|------|------|------|
| 1 | eval_suites | 统一 Eval 框架，6 suites。 | active |
| 2 | context_parser | 自然语言 → 结构化 context。 | active |
| 3 | followup_runner | 多轮追问评测。 | active |
| 4 | pytest_tests | 23 个测试文件的 pytest 套件。 | active |
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
