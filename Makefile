.PHONY: eval full-eval core-eval research-eval capability-audit test ci data-dict lock-demo parser-demo followup-demo numeric-eval reference-eval atp-demo backtest-demo clean-outputs

## 默认 Eval（core + parser + followup + reference，不含 research）
eval:
	python mashang_workspace/eval/run_eval.py --suite default

## 完整 Eval（含 research）
full-eval:
	python mashang_workspace/eval/run_eval.py --suite all

## Core Eval（仅 core 脚本）
core-eval:
	python mashang_workspace/eval/run_eval.py --suite core

## Research Eval（仅 research 脚本）
research-eval:
	python mashang_workspace/eval/run_eval.py --suite research

## 完整测试
test:
	pytest mashang_workspace/tests -q

## CI 门禁（CI-safe suites + 测试）
ci:
	python mashang_workspace/eval/run_eval.py --suite ci --format json --output mashang_workspace/outputs/tables/unified_eval_result.json
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
	python mashang_workspace/scripts/data_dictionary.py --input dataset --output mashang_workspace/outputs/tables/data_dictionary.csv

## 锁单分析 Demo
lock-demo:
	python mashang_workspace/scripts/lock_by_model.py --date 2026-06-10 --format json

## Context Parser Demo
parser-demo:
	python mashang_workspace/eval/parse_context_cli.py "昨天锁单数分车型"

## Follow-up Runner Demo
followup-demo:
	python mashang_workspace/eval/run_followup_eval.py \
		--cases mashang_workspace/eval/cases/followup_cases.json \
		--parse-text --as-of-date 2026-06-11

## Numeric Eval
numeric-eval:
	python mashang_workspace/eval/run_numeric_eval.py

## Reference Eval
reference-eval:
	python mashang_workspace/eval/run_reference_eval.py

## ATP 月报 Demo
atp-demo:
	python mashang_workspace/scripts/atp_price_report.py --month 2026-05 --format json

## 锁单预测回测 Demo
backtest-demo:
	python mashang_workspace/scripts/lock_predict_backtest_cli.py --format json

## Capability Audit
capability-audit:
	python mashang_workspace/eval/run_capability_audit.py --format json --output mashang_workspace/outputs/tables/capability_audit_result.json

## Runtime V2 Readiness Audit
runtime-v2-audit:
	python mashang_workspace/eval/run_runtime_v2_audit.py --format json --output mashang_workspace/outputs/tables/runtime_v2_audit_result.json

## Shared Audit
shared-audit:
	python -c "from mashang_workspace.utils.paths import BUSINESS_DEFINITION_PATH, ensure_shared_on_path; ensure_shared_on_path(); import operators; print('shared ok:', BUSINESS_DEFINITION_PATH)"

## Runtime V2 Demo
runtime-v2-demo:
	python mashang_runtime_v2/app/runtime_service.py "昨天锁单数分车型"

runtime-v2-city-demo:
	python mashang_runtime_v2/app/runtime_service.py "昨天 LS8 锁单城市分布"

runtime-v2-followup-demo:
	python mashang_runtime_v2/app/runtime_service.py "昨天锁单数分车型" --session demo --reset-session
	python mashang_runtime_v2/app/runtime_service.py "LS8 的城市分布" --session demo

runtime-v2-eval:
	python mashang_runtime_v2/eval/run_runtime_v2_eval.py

runtime-v2-clean-sessions:
	python mashang_runtime_v2/app/runtime_service.py --cleanup-sessions

## 清理输出文件
clean-outputs:
	find mashang_workspace/outputs -type f ! -name "README.md" -delete

## 帮助
help:
	@echo "make eval            默认 Eval（core + parser + followup + reference）"
	@echo "make full-eval       完整 Eval（含 research）"
	@echo "make core-eval       Core 脚本 Eval"
	@echo "make research-eval   Research 脚本 Eval"
	@echo "make test            完整测试"
	@echo "make ci              CI 门禁"
	@echo "make data-dict       数据字典"
	@echo "make lock-demo       锁单 Demo"
	@echo "make parser-demo     Context Parser Demo"
	@echo "make followup-demo   Follow-up Runner Demo"
	@echo "make numeric-eval    Numeric Eval"
	@echo "make reference-eval  Reference Eval"
	@echo "make atp-demo        ATP 月报 Demo"
	@echo "make backtest-demo   锁单预测回测 Demo"
	@echo "make capability-audit  Capability Audit"
	@echo "make shared-audit     Shared Layer Audit"
	@echo "make runtime-v2-audit  Runtime V2 Readiness Audit"
	@echo "make runtime-v2-demo  Runtime V2 Demo (锁单车型)"
	@echo "make runtime-v2-city-demo  Runtime V2 Demo (城市分布)"
	@echo "make runtime-v2-followup-demo  Runtime V2 多轮追问 Demo"
	@echo "make runtime-v2-eval  Runtime V2 Eval"
	@echo "make runtime-v2-clean-sessions  Runtime V2 清理过期 Session"
	@echo "make clean-outputs     清理输出文件"
