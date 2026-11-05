# docs — 文档索引

本目录统一维护项目架构、业务分析方法、运营手册和历史归档。业务任务入口见 [Workspace](../workspace/README.md)，Agent Skills 见 [项目 Skills](../.opencode/skills/README.md)。
跨层的业务定义（指标 / 术语 / 时间窗口 / 车型映射）已统一到
`shared/schema/reference/`，机器可读契约在 `shared/schema/`。

## 项目与数据接入

| 文档 | 说明 |
|---|---|
| [architecture_baseline.md](architecture_baseline.md) | Service 拆分基线与历史迁移记录 |
| [tp_and_mix_ways_dataset.md](tp_and_mix_ways_dataset.md) | 上险数据构建与数据资产 |
| [feishu_doc_ingestion.md](feishu_doc_ingestion.md) | 飞书文档采集入口 |
| [cpca_market_research.md](cpca_market_research.md) | 乘联会市场数据研究 |
| [sav_exploratory_analysis.md](sav_exploratory_analysis.md) · [v2](sav_exploratory_analysis_v2.md) | 历史 SAV 探索记录 |

## 业务定义（在 shared/schema）

| 文档 | 说明 |
|---|---|
| `shared/schema/reference/metric_definitions.md` | 核心指标口径 |
| `shared/schema/reference/business_glossary.md` | 业务术语表 |
| `shared/schema/reference/time_window_rules.md` | 时间窗口规则 |
| `shared/schema/reference/vehicle_mapping.md` | 车型/代际映射规则 |
| `shared/schema/schema.md` | 数据集字段级 schema |
| `shared/schema/metrics.json` | 指标注册表（机器可读权威） |

## 分析方法与范式

| 文档 | 说明 |
|---|---|
| [analysis_playbook.md](analysis_playbook.md) | 锁单/结构/异常/释放曲线/VOC/ATP/配置分析范式 |
| [followup_rules.md](followup_rules.md) | 追问处理规则 |
| [followup_runner_rules.md](followup_runner_rules.md) | 追问 → 脚本调度规则 |
| [context_parser_rules.md](context_parser_rules.md) | 自然语言 context 解析规则 |
| [promotion_rules.md](promotion_rules.md) | 脚本晋级规则 |
| [monthly_market_report.md](monthly_market_report.md) | 月度市场报告范式 |
| [market_state_v0_2_design.md](market_state_v0_2_design.md) | Market State V0.2 设计 |
| [launch_rhythm_incremental_analysis.md](launch_rhythm_incremental_analysis.md) | 上市节奏增量分析方法 |
| [launch_rhythm_incremental_research_report.md](launch_rhythm_incremental_research_report.md) | 上市节奏增量研究报告 |
| [L6_M2_预售情况汇报分析框架.md](L6_M2_预售情况汇报分析框架.md) | L6 M2 预售汇报分析框架 |
| [tp_and_mix_ways_usage.md](tp_and_mix_ways_usage.md) | 乘用车上险数据使用指南 |
| [tp_and_mix_ways_monthly_brief.md](tp_and_mix_ways_monthly_brief.md) | 上险数据月度简报 |
| [datasets/cpca_weekly_data_capture.md](datasets/cpca_weekly_data_capture.md) | 乘联分会周度数据捕捉契约 |

## 运营与契约

| 文档 | 说明 |
|---|---|
| [result_contract.md](result_contract.md) | Result Contract 统一执行结果协议 |
| [script_tiers.md](script_tiers.md) | 脚本分层治理 |
| [daily_data_pipeline.md](daily_data_pipeline.md) | Daily 数据管道 |
| [capability_registry.md](capability_registry.md) | 能力注册表 |
| [store_information_card.md](store_information_card.md) | 门店信息手卡与全国分布 |
| [report_visual_system.md](report_visual_system.md) | 报告视觉体系 |
| [branded_html_report.md](branded_html_report.md) | 品牌化 HTML 报告 |
| [data_dictionary.md](data_dictionary.md) | 数据字典脚本说明 |

## 数据获取经验

| 文档 | 说明 |
|---|---|
| [懂车帝月销量获取经验.md](懂车帝月销量获取经验.md) | 懂车帝月销量获取 |
| [im_official_guide_price_sourcing.md](im_official_guide_price_sourcing.md) | 官网配置/价格采集 |
| [tableau_semantic_layer_recovery.md](tableau_semantic_layer_recovery.md) | Tableau 遗留 BI 语义层恢复 |
| [双边校准算法_竞品流失归因报告.md](双边校准算法_竞品流失归因报告.md) | 竞品流失归因报告 |

## 盘点 / 历史

这些是历史快照，路径与结论可能已过期，不作为当前口径来源：

| 文档 | 说明 |
|---|---|
| [project_inventory.md](project_inventory.md) | 早期项目盘点 |
| [project_cleanup_audit.md](project_cleanup_audit.md) | 清理审计 |
| [root_cleanup_inventory.md](root_cleanup_inventory.md) | 根目录清理盘点 |
| [legacy_script_contract_inventory.md](legacy_script_contract_inventory.md) | 历史脚本契约盘点 |
| [legacy_lessons.md](legacy_lessons.md) | 历史经验 |
| [workspace_capability_inventory.md](workspace_capability_inventory.md) | 能力总览 |
| [TODO_quick_lock_ratio_performance.md](TODO_quick_lock_ratio_performance.md) | 性能待办 |

## 归档

历史分析材料、原始笔记、已迁移出 schema 的数据/笔记在 [archive/](archive)，仅作追溯，不作为维护入口。
