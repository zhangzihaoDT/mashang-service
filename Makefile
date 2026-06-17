PYTHON ?= .venv/bin/python
.PHONY: eval full-eval core-eval research-eval capability-audit test ci data-dict lock-demo parser-demo followup-demo numeric-eval reference-eval atp-demo backtest-demo clean-outputs dataset-update dataset-validate daily-observation-dry-run daily-observation-sync daily-data-pipeline-dry-run daily-data-pipeline render-official-doc render-official-doc-smoke build-workspace-skills-catalog build-workspace-capability-inventory

## 默认 Eval（core + parser + followup + reference，不含 research）
eval:
	$(PYTHON) mashang_workspace/eval/run_eval.py --suite default

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
	$(PYTHON) -m pytest mashang_workspace/tests -q

## CI 门禁（CI-safe suites + 测试）
ci:
	$(PYTHON) mashang_workspace/eval/run_eval.py --suite ci --format json --output outputs/tables/unified_eval_result.json
	pytest mashang_workspace/tests/test_root_cleanup.py \
		mashang_workspace/tests/test_result_contract.py \
		mashang_workspace/tests/eval/test_context_parser.py \
		mashang_workspace/tests/eval/test_followup_runner.py \
		mashang_workspace/tests/eval/test_numeric_eval.py \
		mashang_workspace/tests/eval/test_result_reference.py \
		mashang_workspace/tests/eval/test_unified_eval.py \
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

## 新车事件监测（Tavily + Firecrawl，支持品牌/事件类型/来源类型/关键词过滤）
auto-launch-monitor:
	@if [ -f .env ]; then set -a; . .env 2>/dev/null; set +a; fi; \
	$(PYTHON) mashang_workspace/research_scripts/auto_launch_monitor.py \
		--start $(or $(START),$(shell date -v-7d +%Y-%m-%d)) \
		--end $(or $(END),$(shell date +%Y-%m-%d)) \
		--max-results $(or $(MAX_RESULTS),8) \
		$(if $(BRANDS),--brands "$(BRANDS)") \
		$(if $(EVENT_TYPES),--event-types "$(EVENT_TYPES)") \
		$(if $(SOURCE_TYPES),--source-types "$(SOURCE_TYPES)") \
		$(if $(KEYWORDS),--keywords "$(KEYWORDS)") \
		$(if $(EXCLUDE_KEYWORDS),--exclude-keywords "$(EXCLUDE_KEYWORDS)") \
		--format markdown \
		--output mashang_workspace/outputs/reports/

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

## [废弃] 请使用 daily-observation-dry-run 替代
daily-sync-dry-run:
	@echo "[DEPRECATED] Use 'make daily-observation-dry-run' instead."
	$(MAKE) daily-observation-dry-run

## 构建乘用车上险数据集（Passenger Insurance Dataset）
build-passenger-insurance-dataset:
	$(PYTHON) scripts/build_passenger_insurance_dataset.py

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
	@echo "make eval            默认 Eval（core + parser + followup + reference）"
	@echo "make full-eval       完整 Eval（含 research）"
	@echo "make core-eval       Core 脚本 Eval"
	@echo "make research-eval   Research 脚本 Eval"
	@echo "make test            完整测试"
	@echo "make ci              CI 门禁"
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
	@echo "make auto-launch-monitor  新车事件监测（START= END= MAX_RESULTS=8 BRANDS= EVENT_TYPES= SOURCE_TYPES= KEYWORDS= EXCLUDE_KEYWORDS= 可选）"
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
	@echo ""
	@echo "=== Catalog ==="
	@echo "make build-workspace-skills-catalog         生成 workspace skills catalog（JSON/MD/HTML）"
	@echo "make build-workspace-capability-inventory  生成 workspace capability inventory（JSON/MD/HTML）"
	@echo ""
	@echo "=== Utility ==="
	@echo "make clean-outputs     清理输出文件"
