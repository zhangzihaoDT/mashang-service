# Batch 410 运行记录

## 概览

- **公示日期**：2026-08-07
- **结果**：7 品牌 17 车型；参数宽表 19 行；13 个字段缺失
- **产物**：[scan_report](../reports/batch_410/scan_report.html) · [category_report](../reports/batch_410/category_report/index.html) · [wide_table](../data/wide_tables/wide_table_410.md)

## 结论

归档管线重构为"可恢复的数据任务"（失败分类 + checkpoint + retry-failed）后，7 品牌 17 车型一次性全部成功。

## 阅读

- [run_log.md](run_log.md) — 时间线
- [issues.md](issues.md) — 遇到的问题
- [lessons.md](lessons.md) — 经验沉淀

## Run Log（时间线）

# Batch 410 run_log

| 时间 | 步骤 | 动作 | 产出 |
|------|------|------|------|
| 2026-08-07 | 公示 | 记录公示页，`workflow/config/batches.yaml` 登记 410（page_id/index/tax_batch=89） | — |
| 2026-08-07 | P1 搜索 | `miit_report.py --batch 410`（26 品牌扫描，命中 7） | scan 快照 + 品牌搜索简报 |
| 2026-08-07 | P2 归档 | `miit_archive_detail.py --batch 410 --all-missing`（重构后首次全量） | 7 品牌 17 车型全部 SUCCESS；fetch_status_410.json checkpoint |
| 2026-08-07 | P4 宽表 | `wide_table.py --batch 410` | 17 车型 / 19 行配置；附件1缺失0 / 附件2缺失13 |
| 2026-08-07 | P5 报告 | `generate_category_report.py --batch 410 --all` | 分类报告 + index |
| 后续 | 目录收敛 | 模块重组为 5 类资产（reports/data/scripts/runs/workflow） | 本 runs/410 记录 |

## Issues（问题）

# Batch 410 issues

| # | 问题 | 现象 | 状态 |
|---|------|------|------|
| 1 | MIIT detail 403 | 详情页抓取偶发 403/风控拦截 | 已解决（分类为 BLOCKED + cookie priming + 失败不拖死整批） |
| 2 | Read timed out | 部分车型详情页响应慢（连接已建立，read 超时） | 已解决（归入 TRANSIENT_ERROR + 有限重试 + checkpoint，`--retry-failed` 可续抓） |
| 3 | 车船税附件晚于拟公告 | 第89批车船税目录晚于 410 公告发布 | 已解决（P3 滞后执行；报告先出，后补电池/续航字段） |
| 4 | 纯电/燃油车型无名称 | 车船税目录只收减免车型，13/17 无电池/续航 | 已解决（`model_name_map.json` 命名映射 + 后续接入购置税目录） |
| 5 | 车船税分类错位风险 | 410 批缺"汽柴油重型货车"段 | 已解决（按表头列签名识别分类，不按位置映射） |

## 数据质量（410 宽表）

- 附件1 详情页缺失：0
- 附件2 车船税缺失：13（纯电/燃油车型不在目录，属正常）
- 完整电池/续航覆盖：4 款增程/插混（问界 M8 增程×2、猛士 X700 增程/插混）

## Lessons（经验）

# Batch 410 lessons

## Run

2026-08-07

## 结果

- 7 品牌
- 17 车型
- 参数宽表 19 行
- 13 个字段缺失

## 遇到的问题

- MIIT detail 403
- 某些型号 timeout
- 车船税附件晚于拟公告

## 解决方案

- cookie priming
- checkpoint
- retry-failed
- random interval

## 关键认识（410 重构核心）

1. **抓取是数据任务，不是一次性脚本**：失败分类（SUCCESS/NOT_FOUND/TRANSIENT_ERROR/BLOCKED/PARSE_ERROR/SKIPPED）+ 有限重试 + checkpoint/resume，
   让"整批成功"从碰运气变成可恢复、可补抓、最终收敛。
2. **`Read timed out` 归入 TRANSIENT_ERROR 而非 FAILED** 是整个恢复系统能正确工作的前提。
3. **车船税分类识别要按表头列签名，不按位置**——批次可能缺段（410 缺"汽柴油重型货车"），位置映射会让全表错位。
4. **车船税只收减免车型**：410 批 17 款仅 4 款命中属正常口径，不是数据错误。

## 下一轮改进

- 自动发现 pageId（现在要人工登记 `batches.yaml`）
- 减少重复抓取（跨批增量识别：新增 vs 改款）
- vehicle identity 标准化（为 product_master / vehicle_parameter 打基础）
- 纯电车型容量/续航：接入减免车辆购置税的新能源汽车车型目录
- `model_name_map.json` 自动更新（公示后跟踪媒体报道自动补充命名）
