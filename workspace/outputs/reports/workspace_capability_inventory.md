# Mashang Workspace Capability Inventory

Workspace 能力总览：skills / scripts / data assets / outputs / evaluation

生成时间：2026-10-07 09:35:28
Workspace：mashang_workspace

---

## Summary

| 能力类型 | 数量 |
|---------|------|
| Skills（Agent 会什么） | 4 |
| Scripts（Agent 能调用什么） | 99 |
| Data Assets（Agent 能查什么） | 6 |
| Outputs / Reports（Agent 已沉淀什么） | 127 |
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

Agent 可直接调用的 Python 脚本，按功能分为 business（稳定运行入口）、research（研究分析）、utility（工具/渲染/验证）和 legacy（历史保留）四类。

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
| 10 | monthly_sales_order_type_to_feishu.py |  | active |
| 11 | presale_intention_funnel.py |  | active |
| 12 | store_dealer_profile.py |  | active |
| 13 | user_profile.py |  | active |
| 14 | vehicle_sales_monitor.py |  | active |
| 15 | backlog_rate_trend_report.py |  | active |
| 16 | benchmark_conversion_trend.py |  | active |
| 17 | brand_shipments_analysis.py |  | active |
| 18 | brand_shipments_report.py | Brand Shipments 报告 — 基于 brand_shipments_analysis.py 动态计算生成 HTML 报告. | active |
| 19 | cohort_forecast.py |  | active |
| 20 | competition_a3_flow.py | 竞争洞察 A3 人群流转分析 — 情报报告 | active |
| 21 | cpca_weekly_early_signal.py | 乘联分会周度数据早源监控 — Period-Aware | active |
| 22 | cq_lock_share_trend.py |  | active |
| 23 | dc_inventory_trend_report.py |  | active |
| 24 | dc_showroom_age_report.py |  | active |
| 25 | downshift_receiver_screen.py |  | active |
| 26 | group_order_launch_compare.py |  | active |
| 27 | historical_opportunity_validation.py |  | active |
| 28 | invoice_monthly_forecast.py |  | active |
| 29 | l6_m2_daily_lock_by_edition.py |  | active |
| 30 | l6_m2_daily_retention.py |  | active |
| 31 | l6_m2_presale_metrics_to_feishu.py |  | active |
| 32 | l6_m2_presale_report.py |  | active |
| 33 | launch_cumulative_lock_compare.py |  | active |
| 34 | launch_rhythm_incremental_analysis.py |  | active |
| 35 | launch_rhythm_incremental_html.py |  | active |
| 36 | launch_risk_snapshot.py |  | active |
| 37 | lock_attribution_analysis.py |  | active |
| 38 | lock_config_distribution.py |  | active |
| 39 | lock_lifecycle_stages.py |  | active |
| 40 | lock_predict_backtest.py |  | active |
| 41 | lock_release_curve.py |  | active |
| 42 | ls6_invoice_atp_trend.py |  | active |
| 43 | ls8_battery_weekly_share_report.py |  | active |
| 44 | ls8_configuration_selection_report.py |  | active |
| 45 | ls9_battery_weekly_share_report.py |  | active |
| 46 | ls9_hyper_synthetic_control_impact.py | name: ls9_hyper_synthetic_control_impact
 | active |
| 47 | ls9_interior_option_report.py |  | active |
| 48 | ls9_lock_trend_hyper_vs_non.py | name: ls9_lock_trend_hyper_vs_non
 | active |
| 49 | market_report/generate_monthly_brief.py |  | active |
| 50 | market_report/run_monthly_market_report.py |  | active |
| 51 | market_state_assessment.py |  | active |
| 52 | mature_market_shock.py |  | active |
| 53 | model_order_monthly_compare_report.py |  | active |
| 54 | model_share_trend.py |  | active |
| 55 | pk_weekly_compare.py | name: pk_weekly_compare
use: python research_scripts/pk_weekly_compare. | active |
| 56 | pk_weekly_ls8_ls9.py |  | active |
| 57 | presale_comparison_report.py |  | active |
| 58 | presale_cumulative_order_compare.py |  | active |
| 59 | presale_metrics_to_feishu.py |  | active |
| 60 | presale_performance_compare.py |  | active |
| 61 | price_band_migration.py |  | active |
| 62 | quick_lock_ratio.py |  | active |
| 63 | region_series_preference.py |  | active |
| 64 | release_curve_analysis.py |  | active |
| 65 | saic_group_order_daily_parse.py |  | active |
| 66 | saic_group_order_query.py |  | active |
| 67 | saic_sales_profile_report.py |  | active |
| 68 | shock_detector_backtest.py |  | active |
| 69 | shock_detector_rolling.py |  | active |
| 70 | shock_detector_scan.py |  | active |
| 71 | stalled_order_forecast.py |  | active |
| 72 | store_leads_intention_quadrant.py |  | active |
| 73 | store_network_compare.py |  | active |
| 74 | structured_business_forecast.py | 脚本作用：
1) 基于日度矩阵（index_summary_daily_matrix）做结构化业务预测，核心恒等式为 lock_orders =... | active |
| 75 | tesla_wholesale_export_report.py |  | active |
| 76 | tp_and_mix_ways/check_tp_and_mix_ways_asset.py |  | active |
| 77 | tp_and_mix_ways_market_volume.py |  | active |
| 78 | watchlist_brand_driver_decomposition.py |  | active |
| 79 | watchlist_brand_monthly_report.py |  | active |
| 80 | watchlist_brand_trend.py |  | active |
| 81 | audit_series_group_overlap.py |  | active |
| 82 | build_config_semantics.py |  | active |
| 83 | build_daily_matrix.py |  | active |
| 84 | build_lock_trend_report.py |  | active |
| 85 | build_workspace_capability_inventory.py |  | active |
| 86 | build_workspace_skills_catalog.py |  | active |
| 87 | config_code_normalization.py |  | active |
| 88 | data_dictionary.py |  | active |
| 89 | dataset_validate.py |  | active |
| 90 | docx2md.py |  | active |
| 91 | generate_delivery_inventory_report.py |  | active |
| 92 | render_html_report.py |  | active |
| 93 | sales_scheduler.py |  | active |
| 94 | skills_attainment_rate_alert.py |  | active |
| 95 | skills_order_observation_daily.py |  | active |
| 96 | skills_store_lock_alert.py |  | active |
| 97 | store_operation_observation.py |  | active |
| 98 | validate_study_spec.py |  | active |
| 99 | voc_theme_analysis.py |  | active |

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
| 1 | .DS_Store | other · 10.0 KB | generated |
| 2 | CDG_2026-06_lock.html | html report · 7.3 KB | generated |
| 3 | CDG_2026-07_lock.html | html report · 7.3 KB | generated |
| 4 | CDG_2026-08_lock.html | html report · 7.5 KB | generated |
| 5 | L6_M2_预售情况汇报_2026-08-24.html | html report · 25.5 KB | generated |
| 6 | L6_M2_预售情况汇报_2026-08-24.md | markdown report · 19.5 KB | generated |
| 7 | L6_M2_预售情况汇报_2026-08-25.html | html report · 27.1 KB | generated |
| 8 | L6_M2_预售情况汇报_2026-08-25.md | markdown report · 19.8 KB | generated |
| 9 | L6_M2_预售情况汇报_2026-08-26.html | html report · 27.1 KB | generated |
| 10 | L6_M2_预售情况汇报_2026-08-26.md | markdown report · 19.9 KB | generated |
| 11 | L6_lifecycle_lock_stages.md | markdown report · 5.3 KB | generated |
| 12 | LS8_week_model_report_20260626.html | html report · 30.4 KB | generated |
| 13 | LS9_month_model_report_20260626.html | html report · 24.3 KB | generated |
| 14 | Lifecycle_lock_stages_CM_LS.md | markdown report · 8.6 KB | generated |
| 15 | _ma7_test.html | html report · 90.1 KB | generated |
| 16 | agent_execution_trace.md | markdown report · 5.4 KB | generated |
| 17 | atp_2026-04.html | html report · 7.7 KB | generated |
| 18 | atp_2026-05.html | html report · 7.7 KB | generated |
| 19 | atp_2026-06.html | html report · 7.6 KB | generated |
| 20 | atp_2026-07.html | html report · 7.6 KB | generated |
| 21 | atp_2026-08.html | html report · 7.7 KB | generated |
| 22 | atp_2026-09.html | html report · 7.7 KB | generated |
| 23 | audience_evolution_2026.html | html report · 149.0 KB | generated |
| 24 | audience_evolution_2026.md | markdown report · 43.5 KB | generated |
| 25 | audience_evolution_2026_digest.html | html report · 54.2 KB | generated |
| 26 | audience_evolution_2026_digest.md | markdown report · 16.6 KB | generated |
| 27 | auto_launch_monitor_2026-06-05_2026-06-07.md | markdown report · 3.5 KB | generated |
| 28 | backlog_rate_history_20260816.html | html report · 294.8 KB | generated |
| 29 | benchmark_conversion_trend.html | html report · 22.1 KB | generated |
| 30 | brand_marketing_timeline_0716_0720.html | html report · 8.8 KB | generated |
| 31 | brand_shipments_2026H1.html | html report · 13.9 KB | generated |
| 32 | causal_impact_ls9_hyper.html | html report · 9.1 KB | generated |
| 33 | cm2_user_profile_report.html | html report · 34.9 KB | generated |
| 34 | cpca_weekly_early_signal.html | html report · 40.0 KB | generated |
| 35 | cq_lock_share_trend.html | html report · 67.8 KB | generated |
| 36 | daily_msg_report.html | html report · 25.8 KB | generated |
| 37 | dc_inventory_trend.html | html report · 271.2 KB | generated |
| 38 | dc_showroom_age_2026-08-05.html | html report · 12.4 KB | generated |
| 39 | dc_showroom_age_report_20260805.html | html report · 8.1 KB | generated |
| 40 | delivery_inventory_analysis_report.md | markdown report · 4.8 KB | generated |
| 41 | downshift_receiver_validation_2024-03_2025-03.md | markdown report · 15.9 KB | generated |
| 42 | downshift_receiver_validation_downshift_receiver.md | markdown report · 15.9 KB | generated |
| 43 | followup_trace_ls8_city.md | markdown report · 9.4 KB | generated |
| 44 | historical_opportunity_validation_202303.md | markdown report · 7.5 KB | generated |
| 45 | historical_opportunity_validation_202403.md | markdown report · 7.0 KB | generated |
| 46 | historical_opportunity_validation_202503.md | markdown report · 7.5 KB | generated |
| 47 | historical_opportunity_validation_multi_period.md | markdown report · 5.3 KB | generated |
| 48 | june_2026_forecast.html | html report · 5.9 KB | generated |
| 49 | launch_cum_lock_compare_20260907.html | html report · 50.7 KB | generated |
| 50 | launch_cum_lock_compare_20260925.html | html report · 37.9 KB | generated |
| 51 | launch_cum_lock_compare_20260928.html | html report · 59.3 KB | generated |
| 52 | launch_cum_lock_compare_20261005.html | html report · 85.3 KB | generated |
| 53 | launch_rhythm_incremental_analysis.html | html report · 16.1 KB | generated |
| 54 | launch_risk_snapshot_20260816.html | html report · 9.7 KB | generated |
| 55 | lock_attribution_2023-01-01_2023-12-31.html | html report · 9.1 KB | generated |
| 56 | lock_attribution_compare_2024-01-01_2024-08-01_vs_2026-01-01_2026-08-01.html | html report · 12.1 KB | generated |
| 57 | lock_attribution_compare_2024-01-01_2024-12-31_vs_2026-01-01_2026-12-31.html | html report · 11.9 KB | generated |
| 58 | lock_attribution_compare_2025-09-10_2025-09-16_vs_2026-09-23_2026-09-29.html | html report · 12.1 KB | generated |
| 59 | lock_predict_backtest.html | html report · 438.6 KB | generated |
| 60 | lock_release_curve.html | html report · 75.4 KB | generated |
| 61 | lock_trend_report.html | html report · 220.9 KB | generated |
| 62 | ls8_battery_weekly_share.html | html report · 2960.7 KB | generated |
| 63 | ls8_city_distribution_2026-06-14.html | html report · 11.8 KB | generated |
| 64 | ls8_city_distribution_report.html | html report · 9.4 KB | generated |
| 65 | ls8_configuration_selection_since_launch.html | html report · 9.5 KB | generated |
| 66 | ls9_battery_weekly_share.html | html report · 2943.8 KB | generated |
| 67 | ls9_hyper_synthetic_control_impact.html | html report · 8.9 KB | generated |
| 68 | ls9_interior_option_report.html | html report · 12.4 KB | generated |
| 69 | ls9_lock_trend_hyper_comparison.html | html report · 90.9 KB | generated |
| 70 | market_state_observation_2026-07.html | html report · 29.5 KB | generated |
| 71 | mature_market_shock_2022-04_2026-03.md | markdown report · 3.4 KB | generated |
| 72 | miit_dual_vehicle_compare.html | html report · 9.5 KB | generated |
| 73 | model_order_monthly_compare.html | html report · 9.2 KB | generated |
| 74 | pk_weekly_compare_LS6_09-21_09-27.html | html report · 7.8 KB | generated |
| 75 | pk_weekly_compare_LS6_09-22_09-28.html | html report · 8.7 KB | generated |
| 76 | pk_weekly_compare_ls8_ls9.html | html report · 1.4 KB | generated |
| 77 | presale_cum_order_compare_CM3_CM2_CM1_CM0_LS8_LS9_20260915.html | html report · 106.0 KB | generated |
| 78 | presale_small_deposit_compare.html | html report · 13.2 KB | generated |
| 79 | price_band_migration_2022-04_2026-03.md | markdown report · 16.2 KB | generated |
| 80 | price_down_volume_opportunity_202304_202403.md | markdown report · 19.8 KB | generated |
| 81 | quick_lock_ratio.html | html report · 683.3 KB | generated |
| 82 | raw-field-notes-evidence-flow.html | html report · 9.7 KB | generated |
| 83 | raw-field-notes-evidence-issue-pattern-finding.html | html report · 9.2 KB | generated |
| 84 | region_series_preference.html | html report · 17.4 KB | generated |
| 85 | shock_detector_backtest_2023-06_2025-06.md | markdown report · 12.9 KB | generated |
| 86 | shock_detector_scan_2022-04_2026-03.md | markdown report · 7.4 KB | generated |
| 87 | store_bloc_distribution.md | markdown report · 8.7 KB | generated |
| 88 | store_leads_intention_quadrant.html | html report · 48.9 KB | generated |
| 89 | store_leads_intention_quadrant_by_quadrant.html | html report · 48.0 KB | generated |
| 90 | store_leads_intention_quadrant_chongqing.html | html report · 50.3 KB | generated |
| 91 | store_lock_alert_report.md | markdown report · 2.3 KB | generated |
| 92 | tesla_wholesale_export_report.html | html report · 24.9 KB | generated |
| 93 | tp_and_mix_ways_market_volume_2025-08_2026-07.md | markdown report · 20.9 KB | generated |
| 94 | tp_and_mix_ways_market_volume_research_plan.md | markdown report · 6.7 KB | generated |
| 95 | tp_and_mix_ways_workspace_smoke.md | markdown report · 1.1 KB | generated |
| 96 | w24_weekend_analysis.html | html report · 19.3 KB | generated |
| 97 | w24_weekend_analysis.md | markdown report · 4.1 KB | generated |
| 98 | watchlist_brand_driver_2026-07.html | html report · 16.0 KB | generated |
| 99 | watchlist_brand_sales_2026-07.html | html report · 15.9 KB | generated |
| 100 | watchlist_brand_trend_2026-07.html | html report · 45.4 KB | generated |
| 101 | workspace_capability_inventory.html | html report · 51.0 KB | generated |
| 102 | workspace_capability_inventory.json | json contract · 78.4 KB | generated |
| 103 | workspace_capability_inventory.md | markdown report · 13.7 KB | generated |
| 104 | workspace_skills_catalog.html | html report · 16.9 KB | generated |
| 105 | workspace_skills_catalog.json | json contract · 5.4 KB | generated |
| 106 | workspace_skills_catalog.md | markdown report · 4.7 KB | generated |
| 107 | 上汽销售库存流转探查.html | html report · 19.4 KB | generated |
| 108 | 小鹏_product_line.md | markdown report · 7.3 KB | generated |
| 109 | 日频综合声量指数_折线图.html | html report · 50.4 KB | generated |
| 110 | 智己_product_line.md | markdown report · 2.7 KB | generated |
| 111 | 竞争洞察A3人群流转.html | html report · 416.8 KB | generated |
| 112 | 门店观察_2026新开门店_2026-08-25.md | markdown report · 19.6 KB | generated |
| 113 | 阿维塔_product_line.md | markdown report · 2.6 KB | generated |
| 114 | 2026-02/query_results.json | 月报 · 2026-02 · 21.2 KB | generated |
| 115 | 2026-02/query_results.xlsx | 月报 · 2026-02 · 22.5 KB | generated |
| 116 | 2026-02/report_draft.md | 月报 · 2026-02 · 8.7 KB | generated |
| 117 | 2026-02/run_metadata.json | 月报 · 2026-02 · 0.6 KB | generated |
| 118 | 2026-03/query_results.json | 月报 · 2026-03 · 497.1 KB | generated |
| 119 | 2026-03/report_draft.md | 月报 · 2026-03 · 15.8 KB | generated |
| 120 | 2026-03/run_metadata.json | 月报 · 2026-03 · 0.6 KB | generated |
| 121 | 2026-05/query_results.json | 月报 · 2026-05 · 501.5 KB | generated |
| 122 | 2026-05/report_draft.md | 月报 · 2026-05 · 15.9 KB | generated |
| 123 | 2026-05/run_metadata.json | 月报 · 2026-05 · 0.6 KB | generated |
| 124 | 2026-12/query_results.json | 月报 · 2026-12 · 21.2 KB | generated |
| 125 | 2026-12/query_results.xlsx | 月报 · 2026-12 · 22.5 KB | generated |
| 126 | 2026-12/report_draft.md | 月报 · 2026-12 · 8.7 KB | generated |
| 127 | 2026-12/run_metadata.json | 月报 · 2026-12 · 0.6 KB | generated |

---

## evaluation. Evaluation / Quality：Agent 是否可靠

Agent 能力的质量保障体系，包括统一 Eval 框架、上下文解析评测、多轮追问评测、数值校验、pytest 测试套件和回归测试记录。

| # | 名称 | 描述 | 状态 |
|---|------|------|------|
| 1 | eval_suites | 统一 Eval 框架，6 suites。 | active |
| 2 | context_parser | 自然语言 → 结构化 context。 | active |
| 3 | followup_runner | 多轮追问评测。 | active |
| 4 | pytest_tests | 37 个测试文件的 pytest 套件。 | active |
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
