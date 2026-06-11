# Capability Registry — 能力注册表

> 来源: `mashang_workspace/registry/capability_registry.json`

## 能力总览

| capability_id | tier | status | Auto | Contract | Numeric | Gate | Followup | 晋级评估 |
|---------------|:----:|:------:|:----:|:--------:|:-------:|:----:|:--------:|----------|
| `daily_lock_count` | runtime | active | ✅ | ✅ | ✅ | ✅ | ✅ | ⏳ 等待评估 |
| `lock_by_model` | runtime | active | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ 可产品化 |
| `lock_city_distribution` | runtime | active | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ 可产品化 |
| `assign_conversion_analysis` | runtime | active | ✅ | ✅ | ✅ | ✅ | ✅ | ⏳ 口径对齐 |
| `attribute_penetration_report` | runtime | active | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ 可产品化 |
| `atp_price_report` | runtime | active | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ 可产品化 |
| `cohort_forecast` | research | active | ❌ | ✅ | ❌ | ✅ | ❌ | ⏳ 可升级 script |
| `lock_predict_backtest` | research | active | ❌ | ✅ | ✅ | ✅ | ❌ | ⏳ 可升级 script |
| `release_curve_analysis` | research | active | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ 需先加 Contract |
| `data_dictionary` | utility | active | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ 工具类 |
| `skills_atp_price` | legacy | deprecated | ❌ | ❌ | ❌ | ❌ | ❌ | ⏳ 已替代 |
| `voc_theme_analysis` | utility | experimental | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ 需先集成 NLP |

## 字段说明

| 字段 | 说明 |
|------|------|
| `capability_id` | 唯一标识 |
| `tier` | runtime / research / utility / legacy |
| `status` | active / partial / experimental / deprecated |
| `auto_schedulable` | 是否可由 followup_runner / OpenCode 自动调用 |
| `result_contract` | 是否输出标准 Result Contract |
| `numeric_eval_case` | 关联的 numeric eval case ID |
| `contract_gate` | 是否在 Contract Gate 中 |
| `followup_supported` | 是否可被 followup runner 映射 |
| `promotion.current_stage` | 当前所在阶段 |
| `promotion.eligible_for_runtime_productization` | 是否适合产品化 |
| `promotion.blocked_reasons` | 阻塞原因 |
