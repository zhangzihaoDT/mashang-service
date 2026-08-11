# MIIT Gov Proposed Vehicle Intelligence Pipeline — 批次一键入口
#
# 用法（在仓库根目录执行）：
#   make -C MIIT miit-scan BATCH=410      P1 搜索 + 简报
#   make -C MIIT miit-archive BATCH=410   P2 归档全部缺失车型
#   make -C MIIT miit-build BATCH=410     P4 参数宽表
#   make -C MIIT miit-report BATCH=410    P5 分类报告
#   make -C MIIT miit-run BATCH=410       一键 P1→P5
#
# 说明：P3 车船税补充为手动步骤（附件需人工下载/转换），见 workflow/commands.md

BATCH ?= 410
PY ?= python3
MIIT_ROOT := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))

.PHONY: miit-scan miit-archive miit-archive-retry miit-enrich miit-build miit-report miit-run test

miit-scan:
	$(PY) $(MIIT_ROOT)/scripts/01_scan_batch.py --batch $(BATCH)

miit-archive:
	$(PY) $(MIIT_ROOT)/scripts/02_archive_vehicle_details.py --batch $(BATCH) --all-missing

miit-archive-retry:
	$(PY) $(MIIT_ROOT)/scripts/02_archive_vehicle_details.py --batch $(BATCH) --retry-failed

miit-enrich:
	@echo "P3 车船税补充为手动步骤：下载附件 .doc → textutil 转 txt → 03_parse_vehicle_tax.py 解析"
	@echo "详见 workflow/commands.md"

miit-build:
	$(PY) $(MIIT_ROOT)/scripts/04_build_wide_table.py --batch $(BATCH)

miit-report:
	$(PY) $(MIIT_ROOT)/scripts/06_generate_category_report.py --batch $(BATCH) --all --output-dir batch_$(BATCH)/category_report

miit-run: miit-scan miit-archive miit-build miit-report
	@echo "Batch $(BATCH) done. 报告见 reports/batch_$(BATCH)/"

test:
	$(PY) -m pytest $(MIIT_ROOT)/scripts/tests -q
