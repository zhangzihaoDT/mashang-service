# Commands —— 命令速查

> 统一从仓库根目录执行。`BATCH` 为公告批次号（如 410）。

## 一键

```bash
make -C MIIT miit-run BATCH=410   # P1 搜索 → P2 归档 → P4 宽表 → P4.5 统一Dataset → P5 报告
```

## 分步（脚本按管线顺序编号，平铺在 scripts/）

| 步骤 | 命令 |
|------|------|
| 0. 登记批次 | 编辑 `workflow/batches.yaml` |
| 1. 搜索 + 简报 | `python3 MIIT/scripts/01_scan_batch.py --batch 410` |
| 1b. 只生成简报（已有 scan） | `python3 MIIT/scripts/01_scan_batch.py --from-scan --batch 410` |
| 2. 归档全量缺失 | `python3 MIIT/scripts/02_archive_vehicle_details.py --batch 410 --all-missing` |
| 2b. 归档单品牌 | `python3 MIIT/scripts/02_archive_vehicle_details.py --brand 零跑 --batch 410` |
| 2c. 断点续抓失败车型 | `python3 MIIT/scripts/02_archive_vehicle_details.py --batch 410 --retry-failed` |
| 2d. 预览 | `python3 MIIT/scripts/02_archive_vehicle_details.py --batch 410 --all-missing --dry-run` |
| 3. 车船税解析（手动） | 见下方"车船税补充" |
| 4. 参数宽表 | `python3 MIIT/scripts/04_build_wide_table.py --batch 410` |
| 4.5. 统一Dataset | `python3 MIIT/scripts/07_build_vehicle_dataset.py`（Gov proposed + EIDC confirmed，passenger scope） |
| EIDC fresh 抓取 | `python3 MIIT/scripts/09_fetch_eidc_batch.py --batch 408` |
| EIDC fresh 验收 | `python3 MIIT/scripts/eidc_summary_fresh.py` |
| EIDC 超大doc提取 | `python3 MIIT/scripts/eidc_doc_extract.py --input a.doc --output a.txt` |
| 5. 分类报告 | `python3 MIIT/scripts/06_generate_category_report.py --batch 410 --all --output-dir batch_410/category_report` |
| 5b. 单品牌报告 | `python3 MIIT/scripts/05_generate_brand_report.py --batch 409 --brand 小米 --output-dir batch_409/brand_report --batch-label "第409批"` |

## 车船税补充（P3，手动）

附件通常比公告晚 3-5 天发布。

```bash
# 1. 下载附件（批次公示页第4个附件：车船税第XX批车型清单）
curl -L -o 车型清单.doc \
  -H "User-Agent: Mozilla/5.0 ..." \
  -H "Referer: https://www.miit.gov.cn/jgsj/zbys/qcgy/art/2026/art_xxx.html" \
  "https://www.miit.gov.cn/cms_files/filemanager/.../xxx.doc"

# 2. 转纯文本（macOS textutil）
textutil -convert txt -output 车型清单.txt 车型清单.doc

# 3. 解析（相对 --output 落在 data/vehicle_tax/ 下）
python3 MIIT/scripts/03_parse_vehicle_tax.py \
  --input data/vehicle_tax/车型清单_第89批车船税.txt \
  --output 车型清单_第89批车船税 \
  --batch "第八十九批" \
  --date "2026-08-07"
```

## 结果位置

| 产物 | 路径 |
|------|------|
| 品牌搜索简报 | `reports/batch_{batch}/scan_report.html` |
| 车型参数归档 | `data/vehicle_details/{batch}_{型号}-{产品名}.md`（身份 batch:型号） |
| 公告照片 | `data/vehicle_photos/{batch}_{型号}/` |
| 抓取状态 checkpoint | `data/fetch_status/fetch_status_{batch}.json` |
| 车船税结构化 | `data/vehicle_tax/车型清单_第XX批车船税.json` |
| 参数宽表 | `data/wide_tables/wide_table_{batch}.csv` |
| 统一Dataset | `data/vehicle_parameters/product_master.csv` + `vehicle_parameter.csv` |
| EIDC历史归档 | `data/eidc/batch_{401..408}/`（含 import_manifest.json provenance） |
| 分类报告 | `reports/batch_{batch}/category_report/` |

## 其他

```bash
pytest MIIT/scripts/tests -q    # 冒烟：所有脚本 --help 可用
python3 MIIT/scripts/miit_gov_search.py --batch 410 --brand 零跑 --format json   # 只搜索某品牌
```
