PYTHON ?= .venv/bin/python
.PHONY: eval full-eval core-eval research-eval capability-audit test ci data-dict lock-demo parser-demo followup-demo numeric-eval reference-eval atp-demo backtest-demo clean-outputs dataset-update dataset-validate daily-observation-dry-run daily-observation-sync daily-data-pipeline-dry-run daily-data-pipeline render-official-doc render-official-doc-smoke production-golden build-workspace-skills-catalog build-workspace-capability-inventory inventory-status inventory-trend inventory-report lock-attribution lock-attribution-compare

## 生成 Eval 结果（显式产物 unified_eval_result.json）
## 用法: make eval [SUITE=default|ci|all|research|core]
eval:
	$(PYTHON) mashang_workspace/eval/run_eval.py --suite $(or $(SUITE),default) --format terminal --output mashang_workspace/outputs/tables/unified_eval_result.json

## 完整 Eval（含 research）
full-eval:
	$(PYTHON) mashang_workspace/eval/run_eval.py --suite all

## Core Eval（仅 core 脚本）
core-eval:
	$(PYTHON) mashang_workspace/eval/run_eval.py --suite core

## Research Eval（仅 research 脚本）
research-eval:
	$(PYTHON) mashang_workspace/eval/run_eval.py --suite research

## 完整测试
test:
	$(PYTHON) -m pytest mashang_workspace/tests capabilities/ocr/tests -q

## CI 门禁 = 复用 eval(CI-safe) + 数据无关测试
ci:
	$(MAKE) eval SUITE=ci
	$(PYTHON) -m pytest mashang_workspace/tests/test_root_cleanup.py \
		mashang_workspace/tests/test_model_positioning_loader.py \
		mashang_workspace/tests/scripts/test_result_contract.py \
		mashang_workspace/tests/eval/test_context_parser.py \
		mashang_workspace/tests/eval/test_followup_runner.py \
		mashang_workspace/tests/eval/test_numeric_eval.py \
		mashang_workspace/tests/eval/test_result_reference.py \
		mashang_workspace/tests/eval/test_unified_eval.py \
		capabilities/ocr/tests \
		-q

## 数据字典
data-dict:
	$(PYTHON) mashang_workspace/utility_scripts/data_dictionary.py --input dataset --output mashang_workspace/outputs/tables/data_dictionary.csv

## 锁单分析 Demo
lock-demo:
	$(PYTHON) mashang_workspace/runtime_scripts/lock_by_model.py --date 2026-06-10 --format json

## Context Parser Demo
parser-demo:
	$(PYTHON) mashang_workspace/eval/parse_context_cli.py "昨天锁单数分车型"

## Follow-up Runner Demo
followup-demo:
	$(PYTHON) mashang_workspace/eval/run_followup_eval.py \
		--cases mashang_workspace/eval/cases/followup_cases.json \
		--parse-text --as-of-date 2026-06-11

## Numeric Eval
numeric-eval:
	$(PYTHON) mashang_workspace/eval/run_numeric_eval.py

## Reference Eval
reference-eval:
	$(PYTHON) mashang_workspace/eval/run_reference_eval.py

## ATP 月报 Demo
atp-demo:
	$(PYTHON) mashang_workspace/runtime_scripts/atp_price_report.py --month 2026-05 --format json

## 锁单预测回测 Demo
backtest-demo:
	$(PYTHON) mashang_workspace/research_scripts/lock_predict_backtest.py --format json

## ─── Forecast ────────────────────────────────────────────────────

## 锁单月度预估（结构化预测 + Calendar-Regime 后验校正）
## 用法: make lock-forecast AS_OF=2026-07-13 TARGET_MONTH=2026-07 PRIOR_STRENGTH=30
lock-forecast:
	$(PYTHON) mashang_workspace/research_scripts/structured_business_forecast.py \
		--as-of $(or $(AS_OF),$(shell date +%Y-%m-%d)) \
		--target-month $(or $(TARGET_MONTH),$(shell date +%Y-%m)) \
		$(if $(PRIOR_STRENGTH),--prior-strength $(PRIOR_STRENGTH))

## 开票月度预估（条件概率模型，与锁单预测共享 prior-strength）
## 用法: make invoice-forecast AS_OF=2026-07-13 TARGET_MONTH=2026-07 LOCK_REGIME=mode PRIOR_STRENGTH=30
invoice-forecast:
	$(PYTHON) mashang_workspace/research_scripts/invoice_monthly_forecast.py \
		--as-of $(or $(AS_OF),$(shell date +%Y-%m-%d)) \
		--target-month $(or $(TARGET_MONTH),$(shell date +%Y-%m)) \
		$(if $(LOCK_REGIME),--lock-regime $(LOCK_REGIME)) \
		$(if $(PRIOR_STRENGTH),--prior-strength $(PRIOR_STRENGTH))

## ─── Lock Attribution ───────────────────────────────────────────

## 锁单归因分析（单样本；默认 2023 全年）
## 用法: make lock-attribution START=2024-01-01 END=2024-12-31 SERIES=LS6 CHANNEL="新媒体-抖音" HTML=1
lock-attribution:
	$(PYTHON) mashang_workspace/research_scripts/lock_attribution_analysis.py \
		--start-date $(or $(START),2023-01-01) \
		--end-date $(or $(END),2023-12-31) \
		$(if $(SERIES),--series $(SERIES)) \
		$(if $(CHANNEL),--channel "$(CHANNEL)") \
		$(if $(HTML),--html)

## 锁单归因对比分析（两个任意锁单样本；默认 2024 vs 2026 同期 01-01~08-01）
## 用法: make lock-attribution-compare START=2024-01-01 END=2024-08-01 START_B=2026-01-01 END_B=2026-08-01 \
##        LABEL="2024年01-08月" LABEL_B="2026年01-08月" HTML=1 \
##        [SERIES/SERIES_B/CHANNEL/CHANNEL_B 按样本过滤] [FORMAT=terminal|json]
lock-attribution-compare:
	$(PYTHON) mashang_workspace/research_scripts/lock_attribution_analysis.py \
		--start-date $(or $(START),2024-01-01) \
		--end-date $(or $(END),2024-08-01) \
		--compare-start-date $(or $(START_B),2026-01-01) \
		--compare-end-date $(or $(END_B),2026-08-01) \
		$(if $(LABEL),--label "$(LABEL)") \
		$(if $(LABEL_B),--compare-label "$(LABEL_B)") \
		$(if $(SERIES),--series $(SERIES)) \
		$(if $(CHANNEL),--channel "$(CHANNEL)") \
		$(if $(SERIES_B),--compare-series $(SERIES_B)) \
		$(if $(CHANNEL_B),--compare-channel "$(CHANNEL_B)") \
		$(if $(HTML),--html) \
		$(if $(FORMAT),--format $(FORMAT))

## 库存核心指标查询
inventory-status:
	$(PYTHON) -c "import pandas as pd, importlib.util; from pathlib import Path; REPO_ROOT=Path('.'); spec=importlib.util.spec_from_file_location('d', REPO_ROOT/'shared/operators/dealer_unsold_inventory.py'); d=importlib.util.module_from_spec(spec); spec.loader.exec_module(d); inv=pd.read_parquet(REPO_ROOT/'dataset/delivery_inventory.parquet'); odf=pd.read_parquet(REPO_ROOT/'dataset/order_data.parquet'); df=d.compute(inv, odf); r=d.report(df); core=r.get('国内DC在库_未开票',0); series_map={'LSJEL':'LS8','LSJEH':'LS9','LSJWL':'LS7','LSJWR':'LS6','LSJWT':'L6','LSJE3':'L7'}; df['series']=df['vin'].str[:5].map(series_map).fillna('其他'); print('========================================'); print('  核心库存监控指标'); print('========================================'); print(f'  国内DC在库_未开票: {core:,}'); print(); [print(f'  {s}: {len(df[(df.series==s)&(df.is_dc_domestic_uninvoiced==1)]):>5,}') for s in ['LS8','LS6','LS9','L6','LS7','L7']]; print('========================================')"

## 库存趋势 HTML 报告
inventory-trend:
	$(PYTHON) mashang_workspace/research_scripts/dc_inventory_trend_report.py

## 库存详细分析报告
inventory-report:
	$(PYTHON) mashang_workspace/utility_scripts/generate_delivery_inventory_report.py

## Auto Launch — 本品品牌日报（从 facts 库生成，报告层）
auto-launch-owned-brand-daily:
	$(PYTHON) -m auto_launch.cli report --type brand-daily \
		--brand $(or $(BRAND),im) \
		$(if $(BRAND_NAME),--brand-name $(BRAND_NAME)) \
		$(if $(DATE),--date $(DATE)) \
		--window-hours $(or $(WINDOW_HOURS),24) \
		$(if $(LIMIT),--limit $(LIMIT))

auto-launch-owned-brand-daily-dry-run:
	$(PYTHON) -m auto_launch.cli report --type brand-daily \
		--brand $(or $(BRAND),im) \
		$(if $(BRAND_NAME),--brand-name $(BRAND_NAME)) \
		$(if $(DATE),--date $(DATE)) \
		--window-hours $(or $(WINDOW_HOURS),24)

## Auto Launch — Volc Search 搜索意图转译与执行
auto-launch-search:
	$(PYTHON) -m auto_launch.cli search \
		--request "$(or $(REQUEST),看看极氪最近 7 天都有什么动作)" \
		$(if $(DATE),--date $(DATE)) \
		$(if $(LIVE),--live) \
		$(if $(QUERY_PROFILE),--query-profile $(QUERY_PROFILE))

## Auto Launch — 标准化搜索结果
auto-launch-normalize-results:
	$(PYTHON) -m auto_launch.cli normalize \
		--raw $(RAW) \
		--query-plan $(QUERY_PLAN) \
		$(if $(OUTPUT_PREFIX),--output-prefix $(OUTPUT_PREFIX))

## Capability Audit
capability-audit:
	$(PYTHON) mashang_workspace/eval/run_capability_audit.py --format json --output mashang_workspace/outputs/tables/capability_audit_result.json

## Runtime V2 Readiness Audit
runtime-v2-audit:
	$(PYTHON) mashang_workspace/eval/run_runtime_v2_audit.py --format json --output mashang_workspace/outputs/tables/runtime_v2_audit_result.json

## Shared Audit
shared-audit:
	$(PYTHON) -c "from mashang_workspace.utils.paths import BUSINESS_DEFINITION_PATH, ensure_shared_on_path; ensure_shared_on_path(); import operators; print('shared ok:', BUSINESS_DEFINITION_PATH)"

## Runtime V2 Demo
runtime-v2-demo:
	$(PYTHON) mashang_runtime_v2/app/runtime_service.py "昨天锁单数分车型"

runtime-v2-city-demo:
	$(PYTHON) mashang_runtime_v2/app/runtime_service.py "昨天 LS8 锁单城市分布"

runtime-v2-followup-demo:
	$(PYTHON) mashang_runtime_v2/app/runtime_service.py "昨天锁单数分车型" --session demo --reset-session
	$(PYTHON) mashang_runtime_v2/app/runtime_service.py "LS8 的城市分布" --session demo

runtime-v2-eval:
	$(PYTHON) mashang_runtime_v2/eval/run_runtime_v2_eval.py

runtime-v2-clean-sessions:
	$(PYTHON) mashang_runtime_v2/app/runtime_service.py --cleanup-sessions

## ─── Daily Data Pipeline ──────────────────────────────────────────

## 数据集更新（从 Tableau/数据源刷新 dataset/*.parquet/.csv）
## 注意：写操作，会修改本地 dataset 文件
dataset-update:
	$(PYTHON) dataset/updater/update_all_datasets.py

## 数据集完整性校验（只读）
dataset-validate:
	$(PYTHON) mashang_workspace/utility_scripts/dataset_validate.py

## 每日观察预检 dry-run（仅本地计算，不写外部系统）
daily-observation-dry-run:
	$(PYTHON) mashang_workspace/utility_scripts/skills_order_observation_daily.py --dry-run

## 每日观察同步（计算并写入飞书多维表格/机器人）
## 注意：写操作，会同步外部系统
daily-observation-sync:
	$(PYTHON) mashang_workspace/utility_scripts/skills_order_observation_daily.py

## 每日数据管道 dry-run（安全预检，不含写操作）
daily-data-pipeline-dry-run: dataset-validate daily-observation-dry-run

## 每日数据管道完整执行（包含写操作）
## 注意：会刷新 dataset 并同步外部系统
daily-data-pipeline: dataset-update dataset-validate daily-observation-sync

## 单日 DC 库存变动分析（默认昨天）
dc-inventory-change:
	$(PYTHON) mashang_workspace/runtime_scripts/daily_dc_inventory_change.py

dc-inventory-change-date:
	$(PYTHON) mashang_workspace/runtime_scripts/daily_dc_inventory_change.py --date $(DATE)

## 业务状态排查（库存 × 待开票未退订 × 风险暴露；滚动365d + 当年累计双口径）
## 用法: make state-diagnosis [AS_OF=2025-04-17] [SERIES=LS8] [FORMAT=json] [OUTPUT=outputs/tables/]
## AS_OF 支持任意历史时点（point-in-time 重建）；缺省 = 最新数据日
state-diagnosis:
	$(PYTHON) mashang_workspace/runtime_scripts/current_state_diagnosis.py \
		$(if $(AS_OF),--as-of $(AS_OF)) \
		$(if $(SERIES),--series $(SERIES)) \
		$(if $(FORMAT),--format $(FORMAT)) \
		$(if $(OUTPUT),--output $(OUTPUT))

.PHONY: shock-scan shock-backtest shock-research shock-check market-observe

## 月度市场观察（V0.3 Runtime：市场状态评估 + 品牌化 HTML 报告）
## 用法: make market-observe [AS_OF=2026-07]   # 缺省 = 当前年月
market-observe:
	$(PYTHON) mashang_workspace/research_scripts/market_state_assessment.py \
		--as-of $(if $(AS_OF),$(AS_OF),$(shell date +%Y-%m)) \
		--format html

## Shock Detector 滚动扫描（V0.3 research，最近 12 个月崛起冲击者）
## 用法: make shock-scan [AS_OF=2026-06] [FORMAT=json]   # 默认 FORMAT=json（Result Contract）
shock-scan: FORMAT ?= json
shock-scan:
	$(PYTHON) mashang_workspace/research_scripts/shock_detector_rolling.py \
		$(if $(AS_OF),--as-of $(AS_OF)) \
		--format $(FORMAT)

## Shock Detector 滚动回溯验证（历史 as-of → 后续 12M 爆款命中率）
shock-backtest: FORMAT ?= json
shock-backtest:
	$(PYTHON) mashang_workspace/research_scripts/shock_detector_backtest.py \
		--format $(FORMAT)

## Shock Detector 早期规则研究（三期扫描，含 Market State 2×2 增量检验）
shock-research: FORMAT ?= json
shock-research:
	$(PYTHON) mashang_workspace/research_scripts/shock_detector_scan.py \
		--format $(FORMAT)

## Shock Detector 全量研究校验（修改 classifier / detector 规则后一次跑完）
shock-check:
	$(MAKE) shock-backtest
	$(MAKE) shock-research

## [废弃] 请使用 daily-observation-dry-run 替代
daily-sync-dry-run:
	@echo "[DEPRECATED] Use 'make daily-observation-dry-run' instead."
	$(MAKE) daily-observation-dry-run

## 增量更新 TP&MIX-ways 数据集（从 Tableau 拉取 → CSV → parquet）
update-tp-and-mix-ways-dataset:
	$(PYTHON) dataset/updater/update_tp_and_mix_ways_tableau.py

## 仅重新构建（不上 Tableau 下载，使用已有 CSV）
rebuild-tp-and-mix-ways-dataset:
	$(PYTHON) dataset/updater/update_tp_and_mix_ways_tableau.py --skip-export

## 完整重建（从 raw_csv 全量重建 parquet，build 脚本模式）
build-tp-and-mix-ways-dataset:
	$(PYTHON) scripts/build_tp_and_mix_ways_dataset.py

## watchlist 品牌销量月报（本品智己对标 + 行业 benchmark；默认报告月=上月）
## 用法: make watchlist-brand-monthly-report MONTH=2026-07
watchlist-brand-monthly-report:
	$(PYTHON) mashang_workspace/research_scripts/watchlist_brand_monthly_report.py $(if $(MONTH),--month $(MONTH),)

## watchlist 品牌 12 个月销量趋势（含大盘与重点品牌折线图）
## 用法: make watchlist-brand-trend MONTH=2026-07 BRANDS=智界,方程豹
watchlist-brand-trend:
	$(PYTHON) mashang_workspace/research_scripts/watchlist_brand_trend.py $(if $(MONTH),--month $(MONTH),) $(if $(BRANDS),--brands $(BRANDS),)

## watchlist 异常品牌车型贡献拆解（归因分析）
## 用法: make watchlist-brand-driver MONTH=2026-07 THRESHOLD=0.20 BRANDS=智界,特斯拉
watchlist-brand-driver:
	$(PYTHON) mashang_workspace/research_scripts/watchlist_brand_driver_decomposition.py $(if $(MONTH),--month $(MONTH),) $(if $(THRESHOLD),--threshold $(THRESHOLD),) $(if $(BRANDS),--brands $(BRANDS),)

## ─── ──────────────────────────────────────────────────────────────

## 清理输出文件
# # 正式材料排版渲染（Markdown → HTML/PDF/DOCX）
# 用法: make render-official-doc INPUT=path/to/doc.md BASENAME=输出文件名
render-official-doc:
	$(PYTHON) scripts/render_official_document.py \
		--input "$(INPUT)" \
		--basename "$(BASENAME)" \
		--formats html,pdf,docx

# 正式材料排版渲染 Smoke Test
render-official-doc-smoke:
	$(PYTHON) scripts/smoke_test_official_document_render.py

## Production Golden Case v1（NEV-APEAL 生产链回归门）
## 固定：10 页 deck / semantic 0·0 / evidence+signal refs 解析 / render 0·0
## 改 Slide Contract / validator / renderer / visual identity / palette / SKILL / production routing 后必须重放
production-golden:
	$(PYTHON) nev_apeal/scratch/replay_golden_case.py

# === CPCA Weekly Early Signal ===
cpca-weekly-early-signal:  ## 乘联分会周度数据早源监控（终端输出）WEEK=目标数据周（默认自动计算最近周日所在周）
	$(PYTHON) mashang_workspace/research_scripts/cpca_weekly_early_signal.py $(if $(WEEK),--week $(WEEK)) --format terminal

cpca-weekly-early-signal-html:  ## 乘联分会周度数据早源监控（HTML 报告）WEEK=目标数据周（默认自动计算）
	$(PYTHON) mashang_workspace/research_scripts/cpca_weekly_early_signal.py $(if $(WEEK),--week $(WEEK)) --format html

cpca-weekly-early-signal-json:  ## 乘联分会周度数据早源监控（JSON 输出）WEEK=目标数据周（默认自动计算）
	$(PYTHON) mashang_workspace/research_scripts/cpca_weekly_early_signal.py $(if $(WEEK),--week $(WEEK)) --format json

cpca-weekly-data-capture:  ## 捕捉乘联分会周度早源数据并生成 fact_result JSON（WEEK=目标数据周，默认自动计算）
	$(PYTHON) mashang_workspace/research_scripts/cpca_weekly_early_signal.py $(if $(WEEK),--week $(WEEK)) --format html --capture-json --write-fact-result

# Workspace Skills Catalog
build-workspace-skills-catalog:
	$(PYTHON) mashang_workspace/utility_scripts/build_workspace_skills_catalog.py

# Workspace Capability Inventory
build-workspace-capability-inventory:
	$(PYTHON) mashang_workspace/utility_scripts/build_workspace_capability_inventory.py

clean-outputs:
	find mashang_workspace/outputs -type f ! -name "README.md" -delete

## 帮助
help:
	@echo "=== Eval / Test ==="
	@echo "make eval            生成 Eval 结果（显式产物，SUITE 可选）"
	@echo "make full-eval       完整 Eval（含 research）"
	@echo "make core-eval       Core 脚本 Eval"
	@echo "make research-eval   Research 脚本 Eval"
	@echo "make test            完整测试"
	@echo "make ci              完整质量检查 = eval(CI-safe) + 测试"
	@echo ""
	@echo "=== Analysis Demos ==="
	@echo "make data-dict       数据字典"
	@echo "make lock-demo       锁单 Demo"
	@echo "make parser-demo     Context Parser Demo"
	@echo "make followup-demo   Follow-up Runner Demo"
	@echo "make numeric-eval    Numeric Eval"
	@echo "make reference-eval  Reference Eval"
	@echo "make atp-demo        ATP 月报 Demo"
	@echo "make backtest-demo   锁单预测回测 Demo"
	@echo ""
	@echo "=== Forecast ==="
	@echo "make lock-forecast         锁单月度预估（结构化预测）"
	@echo "make invoice-forecast      开票月度预估（条件概率模型）"
	@echo "=== Lock Attribution ==="
	@echo "make lock-attribution       锁单归因分析（单样本）START/END/SERIES/CHANNEL/HTML"
	@echo "make lock-attribution-compare  锁单归因对比分析（两样本，差异高亮）START/END/START_B/END_B/LABEL/LABEL_B/HTML"
	@echo "  示例: make lock-attribution-compare START=2024-01-01 END=2024-08-01 START_B=2026-01-01 END_B=2026-08-01 HTML=1"
	@echo "=== Auto Launch (独立 service: auto_launch/) ==="
	@echo "make auto-launch-owned-brand-daily         本品品牌日报（从 facts 生成，报告层）BRAND=im BRAND_NAME=智己"
	@echo "make auto-launch-owned-brand-daily-dry-run 本品品牌日报（dry-run，同上）"
	@echo "make auto-launch-search                    Volc Search 搜索意图转译 (REQUEST=...) [dry-run]"
	@echo "make auto-launch-normalize-results         标准化搜索结果 (RAW=... QUERY_PLAN=...)"
	@echo "  配置目录: auto_launch/configs/"
	@echo "  文档:      auto_launch/README.md, auto_launch/docs/workflow.md"
	@echo ""
	@echo "=== Inventory ==="
	@echo "make inventory-status     查询核心库存指标（国内DC在库_未开票）"
	@echo "make inventory-trend      生成库存趋势 HTML 报告"
	@echo "make inventory-report     生成库存详细分析报告"
	@echo ""
	@echo "=== Audit ==="
	@echo "make capability-audit  Capability Audit"
	@echo "make shared-audit     Shared Layer Audit"
	@echo "make runtime-v2-audit  Runtime V2 Readiness Audit"
	@echo ""
	@echo "=== Runtime V2 ==="
	@echo "make runtime-v2-demo  Runtime V2 Demo (锁单车型)"
	@echo "make runtime-v2-city-demo  Runtime V2 Demo (城市分布)"
	@echo "make runtime-v2-followup-demo  Runtime V2 多轮追问 Demo"
	@echo "make runtime-v2-eval  Runtime V2 Eval"
	@echo "make runtime-v2-clean-sessions  Runtime V2 清理过期 Session"
	@echo ""
	@echo "=== Daily Data Pipeline ==="
	@echo "make dataset-update           刷新 dataset（写操作）"
	@echo "make dataset-validate         校验 dataset（只读）"
	@echo "make daily-observation-dry-run  每日观察预检（只读）"
	@echo "make daily-observation-sync    每日观察同步（写操作）"
	@echo "make daily-data-pipeline-dry-run  管道 dry-run（安全预检）"
	@echo "make daily-data-pipeline      完整管道（含写操作）"
	@echo "make daily-sync-dry-run       [DEPRECATED]"
	@echo ""
	@echo "=== Render ==="
	@echo "make render-official-doc       正式材料排版渲染（Markdown→PDF/HTML/DOCX）"
	@echo "make render-official-doc-smoke 正式材料排版渲染 Smoke Test"
	@echo ""
	@echo "=== NEV-APEAL Production ==="
	@echo "make production-golden         Production Golden Case v1 回归门（slide contract + semantic lint + render QA）"
	@echo ""
	@echo ""
	@echo "=== Catalog ==="
	@echo "make build-workspace-skills-catalog         生成 workspace skills catalog（JSON/MD/HTML）"
	@echo "make build-workspace-capability-inventory  生成 workspace capability inventory（JSON/MD/HTML）"
	@echo ""
	@echo "=== Utility ==="
	@echo "make clean-outputs     清理输出文件"
