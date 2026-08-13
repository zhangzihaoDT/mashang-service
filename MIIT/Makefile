# MIIT Pipeline — 批次一键入口
#
# 编号 = pipeline topology（SOURCE → ENRICHMENT → CANONICAL → DERIVED → REPORT）：
#   01 Gov scan → 02 Gov archive → 03 EIDC fetch
#   04 vehicle tax → 05 purchase tax
#   06 vehicle dataset（canonical）→ 07 wide table
#   08 brand report → 09 category report
#
# 用法（在仓库根目录执行）：
#   make -C MIIT miit-scan BATCH=410      P1 搜索 + 简报
#   make -C MIIT miit-archive BATCH=410   P2 归档全部缺失车型
#   make -C MIIT miit-build BATCH=410     P7 参数宽表
#   make -C MIIT miit-report BATCH=410    P9 分类报告
#   make -C MIIT miit-run BATCH=410       一键 01→09
#
# 说明：P3 车船税补充为手动步骤（附件需人工下载/转换），见 workflow/commands.md

BATCH ?= 410
PY ?= python3
MIIT_ROOT := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))

.PHONY: miit-scan miit-archive miit-archive-retry miit-enrich miit-build miit-dataset miit-eidc-fetch miit-eidc-tax miit-report miit-run test

miit-scan:
	$(PY) $(MIIT_ROOT)/scripts/01_scan_gov_batch.py --batch $(BATCH)

miit-archive:
	$(PY) $(MIIT_ROOT)/scripts/02_archive_gov_vehicle_details.py --batch $(BATCH) --all-missing

miit-archive-retry:
	$(PY) $(MIIT_ROOT)/scripts/02_archive_gov_vehicle_details.py --batch $(BATCH) --retry-failed

miit-enrich:
	@echo "P3 车船税补充为手动步骤：下载附件 .doc → textutil 转 txt → 04_parse_vehicle_tax.py 解析"
	@echo "详见 workflow/commands.md"

miit-build:
	$(PY) $(MIIT_ROOT)/scripts/07_build_wide_table.py --batch $(BATCH)

miit-dataset:
	$(PY) $(MIIT_ROOT)/scripts/06_build_vehicle_dataset.py

miit-eidc-fetch:
	$(PY) $(MIIT_ROOT)/scripts/03_fetch_eidc_batch.py --batch $(BATCH)

miit-eidc-tax:
	@echo "P3 车船税：04_parse_vehicle_tax.py 解析 data/eidc/batch_$(BATCH)/attachment_text_src/ 下的车船税 .txt"
	@echo "购置税：05_parse_purchase_tax.py 解析购置税 .txt"

miit-report:
	$(PY) $(MIIT_ROOT)/scripts/09_generate_category_report.py --batch $(BATCH) --all --output-dir batch_$(BATCH)/category_report

miit-run: miit-scan miit-archive miit-build miit-dataset miit-report
	@echo "Batch $(BATCH) done. 报告见 reports/batch_$(BATCH)/"

test:
	$(PY) -m pytest $(MIIT_ROOT)/scripts/tests -q
