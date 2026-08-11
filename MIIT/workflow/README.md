# Workflow —— 系统大脑

这个目录回答：**这个系统为什么存在、一轮怎么跑、Agent 应该调用哪个命令**。

## 阅读顺序

1. **这个模块是什么** → [../README.md](../README.md)（模块总览 + 5 类资产）
2. **管线怎么跑** → [pipeline.md](pipeline.md)（P1~P5 技术细节）
3. **命令速查** → [commands.md](commands.md)
4. **批次怎么配** → [batches.yaml](batches.yaml)
5. **数据契约** → [schemas/](schemas/)
6. **批次索引 / 字段口径** → [docs/](docs/)
7. **上一批踩了什么坑** → [../runs/](../runs/)

## 主链路

```
MIIT.gov.cn
  → P1 搜索   → data/search_results/ + reports/batch_{batch}/scan_report.html
  → P2 归档   → data/vehicle_details/ + data/vehicle_photos/ + data/fetch_status/
  → P3 补充   → data/vehicle_tax/车型清单_第XX批车船税.json
  → P4 Dataset→ data/wide_tables/wide_table_{batch}.csv
  → P5 报告   → reports/batch_{batch}/
```

## 快速跑一轮（Makefile）

```bash
make -C MIIT miit-scan BATCH=410     # P1 搜索 + 简报
make -C MIIT miit-archive BATCH=410  # P2 归档全部缺失车型
make -C MIIT miit-build BATCH=410    # P4 宽表
make -C MIIT miit-report BATCH=410   # P5 分类报告
make -C MIIT miit-run BATCH=410      # 一键 P1→P5（P3 车船税需手动，见 commands.md）
```

## 配置归属（workflow/ 平铺）

| 文件 | 内容 |
|------|------|
| `batches.yaml` | 唯一批次配置（page_id/index/日期/车船税批次/文件名） |
| `brand_watchlist.yaml` | 关注品牌清单（按分类分组） |
| `model_name_map.json` | 车型通用名称映射（车船税缺失车型命名补充） |
| `schemas/` | vehicle / scan / fetch_status 数据契约 |
| `docs/` | 公告批次索引、附件字段来源汇总、历史勘探产物 |
