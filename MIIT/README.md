# MIIT Gov Proposed Vehicle Intelligence Pipeline

工信部拟公告新车情报模块：**发现拟公告 → 找到关注车型 → 归档车型事实 → 结构化参数 → 补充监管附件 → 生成分析数据与报告。**

管线技术细节见 [workflow/pipeline.md](workflow/pipeline.md)，命令速查见 [workflow/commands.md](workflow/commands.md)。

## 主链路

```
MIIT.gov.cn
  → P1 搜索   → data/search_results/ + reports/batch_{batch}/scan_report.html
  → P2 归档   → data/vehicle_details/ + data/vehicle_photos/ + data/fetch_status/
  → P3 补充   → data/vehicle_tax/车型清单_第XX批车船税.json
  → P4 Dataset→ data/wide_tables/wide_table_{batch}.csv
  → P5 报告   → reports/batch_{batch}/
```

## 5 类资产（阅读顺序）

| 目录 | 是什么 | 什么时候打开 |
|------|--------|--------------|
| [workflow/](workflow/) | 规则、规划、配置、命令 | **想知道怎么用 / 为什么存在** |
| [scripts/](scripts/) | 所有可执行脚本（平铺，按管线顺序编号） | **想运行** |
| [data/](data/) | 获取的数据 + 加工中间数据（按内容命名） | **想看原始 / 中间数据** |
| [reports/](reports/) | 最终给人看的产出 | **想看结论** |
| [runs/](runs/) | 每轮运行记录 / 经验沉淀 | **想知道上一批踩了什么坑** |

```
MIIT/
├── README.md
├── Makefile
├── reports/       ① 最终报告（batch_409/ batch_410/）
├── data/          ② 事实数据（search_results/ vehicle_details/ vehicle_photos/ raw_html/ vehicle_tax/ vehicle_parameters/ wide_tables/ fetch_status/）
├── scripts/       ③ 执行脚本（01~06 按管线编号平铺 + miit_gov_search / miit_paths / report_common / tests）
├── runs/          ④ 运行记录（batch_409.md batch_410.md）
└── workflow/      ⑤ 规则与配置（pipeline.md commands.md batches.yaml brand_watchlist.yaml model_name_map.json schemas/ docs/）
```

> 这不是标准 Python package，而是一个**持续运行、持续积累数据、持续形成分析结果的 Research Intelligence Workspace**。
> 顶层只保留 5 个认知入口；脚本按管线顺序 `01→06` 平铺在 scripts/。

## 快速跑一轮

```bash
make -C MIIT miit-run BATCH=410   # P1 搜索 → P2 归档 → P4 宽表 → P5 报告
```

分步见 [workflow/commands.md](workflow/commands.md)；P3 车船税补充为手动步骤。

## 当前状态

已处理 **409**（2026-07-07）、**410**（2026-08-07）两批。409 归档 14 品牌；410 归档 7 品牌 17 车型（宽表 19 行）。
批次索引见 [workflow/docs/公告批次.md](workflow/docs/公告批次.md)，各批运行经验见 [runs/](runs/)。

## 测试

```bash
make -C MIIT test       # 冒烟：所有脚本 --help 可用
```

## 后续方向

- 统一 Dataset：`product_master` / `vehicle_parameter` → `data/vehicle_parameters/`
- 自动发现 pageId；新增 vs 改款自动标识；差异增量通知
- 接入 EIDC 双源（`data/raw/eidc/` → 统一落 `data/vehicle_parameters/`）
