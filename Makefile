PYTHON ?= .venv/bin/python
.PHONY: eval full-eval core-eval research-eval capability-audit test ci data-dict lock-demo parser-demo followup-demo numeric-eval reference-eval atp-demo backtest-demo clean-outputs dataset-update dataset-validate daily-observation-dry-run daily-observation-sync daily-data-pipeline-dry-run daily-data-pipeline render-official-doc render-official-doc-smoke build-workspace-skills-catalog build-workspace-capability-inventory miit-discover-latest-batch miit-discover-batches miit-fetch-batch miit-new-car-monitor miit-latest-publicity miit-latest-official miit-latest-publicity-refresh miit-latest-official-refresh miit-extract-text miit-check-text-extractors miit-diagnose-attachments miit-parse-product-list

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

## MIIT 新车公告批次监控 (V0.2)
## 发现最新公告
miit-discover-latest-batch:
	$(PYTHON) mashang_workspace/research_scripts/miit_new_car/discover_batches.py --limit 5

## 发现多页公告
miit-discover-batches:
	$(PYTHON) mashang_workspace/research_scripts/miit_new_car/discover_batches.py --pages $(or $(PAGES),1)

## 抓取指定批次
## 支持 PAGES 参数搜索历史批次：make miit-fetch-batch BATCH=402 PAGES=10
miit-fetch-batch:
	$(PYTHON) mashang_workspace/research_scripts/miit_new_car/monitor.py --batch $(BATCH) --pages $(or $(PAGES),3)

## 监控最新批次
miit-new-car-monitor:
	$(PYTHON) mashang_workspace/research_scripts/miit_new_car/monitor.py --latest

## 监控最新公示批次
miit-latest-publicity:
	$(PYTHON) mashang_workspace/research_scripts/miit_new_car/monitor.py --latest-publicity

## 监控最新正式公告批次
miit-latest-official:
	$(PYTHON) mashang_workspace/research_scripts/miit_new_car/monitor.py --latest-official

## 监控最新公示（刷新）
miit-latest-publicity-refresh:
	$(PYTHON) mashang_workspace/research_scripts/miit_new_car/monitor.py --latest-publicity --refresh

## 监控最新正式公告（刷新）
miit-latest-official-refresh:
	$(PYTHON) mashang_workspace/research_scripts/miit_new_car/monitor.py --latest-official --refresh

## 抽取指定批次附件文本
miit-extract-text:
	$(PYTHON) mashang_workspace/research_scripts/miit_new_car/extract_attachment_text.py --batch $(BATCH)

## 检查文本抽取工具
miit-check-text-extractors:
	$(PYTHON) mashang_workspace/research_scripts/miit_new_car/check_text_extractors.py

## 诊断附件下载
miit-diagnose-attachments:
	$(PYTHON) mashang_workspace/research_scripts/miit_new_car/diagnose_attachment_urls.py --batch $(BATCH)

## 解析产品清单主表
miit-parse-product-list:
	$(PYTHON) mashang_workspace/research_scripts/miit_new_car/parse_product_list.py --batch $(BATCH)

## 生成 Auto Launch 示例搜索 Prompt
## 支持覆盖参数: TARGETS_FILE TARGET_PROFILE_FILE BATTLE_FIELDS_FILE TARGET_BRAND TARGET_MODEL TARGET_GROUP EVENT_TYPE EVENT_DATE WINDOW COMPETITOR_LIMIT INCLUDE_PRIORITY
build-auto-launch-prompt:
	$(PYTHON) mashang_workspace/promptbuilders/auto_launch/promptbuilder.py \
		--brand $(or $(TARGET_BRAND),智己) \
		--model $(or $(TARGET_MODEL),LS8) \
		--event-type $(or $(EVENT_TYPE),上市) \
		--event-date $(or $(EVENT_DATE),2026-06-25) \
		--window $(or $(WINDOW),48h) \
		$(if $(TARGETS_FILE),--targets-file "$(TARGETS_FILE)",--targets-file mashang_workspace/configs/ls8_competitor_watchlist.csv) \
		$(if $(TARGET_PROFILE_FILE),--target-profile-file "$(TARGET_PROFILE_FILE)",--target-profile-file mashang_workspace/promptbuilders/auto_launch/configs/target_profiles.yaml) \
		$(if $(BATTLE_FIELDS_FILE),--battle-fields-file "$(BATTLE_FIELDS_FILE)",--battle-fields-file mashang_workspace/promptbuilders/auto_launch/configs/battle_fields.yaml) \
		$(if $(TARGET_GROUP),--target-group "$(TARGET_GROUP)") \
		--competitor-limit $(or $(COMPETITOR_LIMIT),5) \
		--include-priority $(or $(INCLUDE_PRIORITY),high) \
		--output mashang_workspace/outputs/auto_launch/prompts/ls8_search_task.md

## 生成 Golden Prompt Cases（3 个标准样例 + 校验）
build-auto-launch-golden-prompts:
	$(PYTHON) mashang_workspace/promptbuilders/auto_launch/examples/generate_golden_cases.py

## 验证 AI 返回结果是否符合 evidence schema 和输出结构要求
## 支持覆盖参数: CASE_NAME RAW_FILE PROMPT_FILE OUTPUT
validate-auto-launch-ai-response:
	$(PYTHON) mashang_workspace/promptbuilders/auto_launch/examples/validate_ai_response.py \
		--strict \
		--case-name $(or $(CASE_NAME),sample_response) \
		--raw-file $(or $(RAW_FILE),mashang_workspace/promptbuilders/auto_launch/examples/fixtures/sample_response.synthetic.raw.md) \
		--prompt-file $(or $(PROMPT_FILE),mashang_workspace/outputs/auto_launch/prompts/examples/byd_datang_ev_launch_7d_vs_ls8.md) \
		--output $(or $(OUTPUT),mashang_workspace/outputs/auto_launch/ai_response_examples/sample_response.validation.json)

## 验证 byd_datang_ev 真实 AI 返回结果
## 使用前: 将 DeepSeek/ChatGPT 搜索结果保存为 outputs/auto_launch/ai_response_examples/byd_datang_ev_launch_7d_vs_ls8.raw.md
validate-auto-launch-byd-datang-fixture:
	@if [ ! -f mashang_workspace/outputs/auto_launch/ai_response_examples/byd_datang_ev_launch_7d_vs_ls8.raw.md ]; then \
		echo ""; \
		echo "  ⚠️  未找到真实 AI 返回结果。请先完成以下步骤："; \
		echo ""; \
		echo "  1. 打开以下 Prompt 文件，复制全部内容："; \
		echo "     mashang_workspace/outputs/auto_launch/prompts/examples/byd_datang_ev_launch_7d_vs_ls8.md"; \
		echo ""; \
		echo "  2. 将内容粘贴到 DeepSeek / ChatGPT 的搜索对话中"; \
		echo ""; \
		echo "  3. 等待 AI 搜索完成后，将完整返回结果保存为："; \
		echo "     mashang_workspace/outputs/auto_launch/ai_response_examples/byd_datang_ev_launch_7d_vs_ls8.raw.md"; \
		echo ""; \
		echo "  4. 重新运行: make validate-auto-launch-byd-datang-fixture"; \
		echo ""; \
		exit 1; \
	fi
	$(PYTHON) mashang_workspace/promptbuilders/auto_launch/examples/validate_ai_response.py \
		--case-name byd_datang_ev_launch_7d_vs_ls8 \
		--raw-file mashang_workspace/outputs/auto_launch/ai_response_examples/byd_datang_ev_launch_7d_vs_ls8.raw.md \
		--prompt-file mashang_workspace/outputs/auto_launch/prompts/examples/byd_datang_ev_launch_7d_vs_ls8.md \
		--output mashang_workspace/outputs/auto_launch/ai_response_examples/byd_datang_ev_launch_7d_vs_ls8.validation.json

## 生成 byd_datang_ev 标准化证据 JSON
## 前置条件: make validate-auto-launch-byd-datang-fixture 已通过
build-auto-launch-byd-datang-report:
	$(PYTHON) mashang_workspace/promptbuilders/auto_launch/examples/normalize_ai_response.py \
		--case-name byd_datang_ev_launch_7d_vs_ls8 \
		--raw-file mashang_workspace/outputs/auto_launch/ai_response_examples/byd_datang_ev_launch_7d_vs_ls8.raw.md \
		--prompt-file mashang_workspace/outputs/auto_launch/prompts/examples/byd_datang_ev_launch_7d_vs_ls8.md \
		--validation-file mashang_workspace/outputs/auto_launch/ai_response_examples/byd_datang_ev_launch_7d_vs_ls8.validation.json \
		--normalized-output mashang_workspace/outputs/auto_launch/normalized/byd_datang_ev_launch_7d_vs_ls8.normalized_evidence.json \
		--report-output mashang_workspace/outputs/auto_launch/reports/byd_datang_ev_launch_7d_vs_ls8/executive_brief.md

## 打包为标准化报告目录（raw.md + 摘要 + 索引 + 质量）
## 依赖: raw.md + validation.json + normalized_evidence.json
package-auto-launch-byd-datang-report: build-auto-launch-byd-datang-report
	$(PYTHON) mashang_workspace/promptbuilders/auto_launch/examples/package_ai_report.py \
		--case-name byd_datang_ev_launch_7d_vs_ls8 \
		--raw-file mashang_workspace/outputs/auto_launch/ai_response_examples/byd_datang_ev_launch_7d_vs_ls8.raw.md \
		--validation-file mashang_workspace/outputs/auto_launch/ai_response_examples/byd_datang_ev_launch_7d_vs_ls8.validation.json \
		--normalized-file mashang_workspace/outputs/auto_launch/normalized/byd_datang_ev_launch_7d_vs_ls8.normalized_evidence.json \
		--output-dir mashang_workspace/outputs/auto_launch/reports/byd_datang_ev_launch_7d_vs_ls8

## [EXPERIMENTAL] 生成一页摘要（不替代 raw.md）
build-auto-launch-battle-brief:
	$(PYTHON) mashang_workspace/promptbuilders/auto_launch/examples/build_battle_brief.py \
		--normalized-file $(or $(NORMALIZED_FILE),mashang_workspace/outputs/auto_launch/normalized/byd_datang_ev_launch_7d_vs_ls8.normalized_evidence.json) \
		--output $(or $(REPORT_OUTPUT),mashang_workspace/outputs/auto_launch/reports/byd_datang_ev_launch_7d_vs_ls8/executive_brief.md)

## [EXPERIMENTAL] 验收 executive_brief.md 摘要质量
validate-auto-launch-byd-datang-report:
	$(PYTHON) mashang_workspace/promptbuilders/auto_launch/examples/validate_battle_brief.py \
		--brief-file mashang_workspace/outputs/auto_launch/reports/byd_datang_ev_launch_7d_vs_ls8/executive_brief.md \
		--normalized-file mashang_workspace/outputs/auto_launch/normalized/byd_datang_ev_launch_7d_vs_ls8.normalized_evidence.json \
		--output mashang_workspace/outputs/auto_launch/reports/byd_datang_ev_launch_7d_vs_ls8/report.quality.json

## AI Output Intake Workflow (validate → normalize → markdown)
## SAMPLE: AI output JSON path (default: event_48h_sample.json)
## OUT_DIR: if set, uses --output-dir mode (auto-generates raw/normalized/report/manifest)
SAMPLE ?= mashang_workspace/promptbuilders/auto_launch/examples/ai_outputs/event_48h_sample.json
OUTPUT_PREFIX ?= mashang_workspace/promptbuilders/auto_launch/examples

## Validate AI output JSON
auto-launch-validate:
	$(PYTHON) mashang_workspace/promptbuilders/auto_launch/validators/validate_ai_response.py $(SAMPLE)

## Normalize AI output JSON
auto-launch-normalize:
	$(PYTHON) mashang_workspace/promptbuilders/auto_launch/validators/normalize_ai_response.py $(SAMPLE) \
		--output $(OUTPUT_PREFIX)/normalized/$(notdir $(SAMPLE:.json=.normalized.json))

## Full Intake: validate → normalize → markdown report
## If OUT_DIR is set, uses --output-dir mode; otherwise uses --normalized-output/--report-output
auto-launch-intake:
	$(if $(OUT_DIR),\
		$(PYTHON) mashang_workspace/promptbuilders/auto_launch/intake/process_ai_output.py $(SAMPLE) \
			--output-dir $(OUT_DIR),\
		$(PYTHON) mashang_workspace/promptbuilders/auto_launch/intake/process_ai_output.py $(SAMPLE) \
			--normalized-output $(OUTPUT_PREFIX)/normalized/$(notdir $(SAMPLE:.json=.normalized.json)) \
			--report-output $(OUTPUT_PREFIX)/reports/$(notdir $(SAMPLE:.json=.md)))

## Build output index from all intake output directories
OUT_ROOT ?= mashang_workspace/outputs/auto_launch
auto-launch-index:
	$(PYTHON) mashang_workspace/promptbuilders/auto_launch/indexers/build_output_index.py \
		--input-dir $(OUT_ROOT) \
		--index-json $(OUT_ROOT)/index.json \
		--index-md $(OUT_ROOT)/index.md

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

# === CPCA Weekly Early Signal ===
cpca-weekly-early-signal:  ## 乘联分会周度数据早源监控（终端输出）WEEK=目标数据周
	$(PYTHON) mashang_workspace/research_scripts/cpca_weekly_early_signal.py --week $(or $(WEEK),2026-W26) --format terminal

cpca-weekly-early-signal-html:  ## 乘联分会周度数据早源监控（HTML 报告）WEEK=目标数据周
	$(PYTHON) mashang_workspace/research_scripts/cpca_weekly_early_signal.py --week $(or $(WEEK),2026-W26) --format html

cpca-weekly-early-signal-json:  ## 乘联分会周度数据早源监控（JSON 输出）WEEK=目标数据周
	$(PYTHON) mashang_workspace/research_scripts/cpca_weekly_early_signal.py --week $(or $(WEEK),2026-W26) --format json

cpca-weekly-data-capture:  ## 捕捉乘联分会周度早源数据并生成 fact_result JSON（WEEK=目标数据周）
	$(PYTHON) mashang_workspace/research_scripts/cpca_weekly_early_signal.py --week $(or $(WEEK),2026-W26) --format html --capture-json --write-fact-result

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
	@echo "=== Auto Launch (竞品上市事件 Prompt 工作流) ==="
	@echo "make build-auto-launch-prompt          生成搜索 Prompt"
	@echo "make build-auto-launch-golden-prompts  生成 4 个 Golden Prompt 样例"
	@echo "make validate-auto-launch-ai-response  [strict] synthetic AI 返回验证"
	@echo "make validate-auto-launch-byd-datang-fixture  [tolerant] 真实 AI 返回验证"
	@echo "make package-auto-launch-byd-datang-report  打包标准化报告目录 (raw+摘要+索引+质量)"
	@echo "make build-auto-launch-battle-brief    [EXPERIMENTAL] 生成一页摘要"
	@echo "make auto-launch-validate  SAMPLE=... 验证 AI 输出 JSON（Prompt workflow intake）"
	@echo "make auto-launch-normalize SAMPLE=... 归一化 AI 输出 JSON"
	@echo "make auto-launch-intake    SAMPLE=... OUT_DIR=... 完整 intake: validate→normalize→markdown (output-dir 模式)"
	@echo "make auto-launch-index     OUT_ROOT=... 生成 output index（Promopt workflow output archive）"
	@echo "prompts/ + plan_templates/             核心资产（promptbuilders/auto_launch/）"
	@echo ""
	@echo "=== MIIT 新车公告 ==="
	@echo "make miit-discover-latest-batch  发现最新公告批次"
	@echo "make miit-discover-batches PAGES=N  多页发现公告批次"
	@echo "make miit-fetch-batch BATCH=N    抓取指定批次"
	@echo "make miit-new-car-monitor        监控最新批次"
	@echo "make miit-latest-publicity       监控最新公示批次（幂等）"
	@echo "make miit-latest-official        监控最新正式公告批次（幂等）"
	@echo "make miit-latest-publicity-refresh  重新获取最新公示"
	@echo "make miit-latest-official-refresh   重新获取最新正式公告"
	@echo "make miit-extract-text BATCH=N   抽取指定批次附件文本"
	@echo "make miit-check-text-extractors  检查文本抽取工具"
	@echo "make miit-diagnose-attachments BATCH=N  诊断附件下载"
	@echo "make miit-parse-product-list BATCH=N  解析产品清单主表"
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
