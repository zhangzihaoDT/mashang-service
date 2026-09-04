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
  → P4.5 统一Dataset → data/vehicle_parameters/product_master + vehicle_parameter
  → P5 报告   → reports/batch_{batch}/
```

## EIDC（confirmed 双源）

EIDC 正式公告（miit-eidc.org.cn）作为 confirmed source，与 Gov proposed 共用同一 canonical 出口：

```
EIDC 官方公告页
  → 03_fetch_eidc_batch.py（source 抓取/解析/归档）
  → data/eidc/batch_{N}/（product_list.json + import_manifest + 附件 evidence）
  → 06_build_vehicle_dataset.py（canonical 唯一入口，与 Gov 共用）
  → data/vehicle_parameters/（source=eidc, stage=confirmed）
```

- **source 层**（`eidc_source.py` / `eidc_parser.py`）只回答"官方页面提供了什么"；**领域解释**在 `vehicle_record_builder.py`；**canonical writer** 只有 `06`。
- 当前 **401-408 全部为 fresh rebuild**（官方公告 → 全量解析 → passenger scope gate），legacy 导入已删除。
- 分类维度 `vehicle_category` / `analysis_scope` 为派生，不参与 identity。
- **canonical scope**：Source archive 保留全量道路机动车辆；`vehicle_parameters/` 只落乘用车（`model_code valid AND vehicle_category==passenger_vehicle`）。Gov/EIDC 共用同一 `is_canonical_in_scope()` gate。

**完整技术说明 / source contract / pipeline 细节见 [data/eidc/README.md](data/eidc/README.md)。**

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
├── data/          ② 事实数据（eidc/ search_results/ vehicle_details/ vehicle_photos/ raw_html/ vehicle_tax/ vehicle_parameters/ wide_tables/ fetch_status/）
├── scripts/       ③ 执行脚本（01~09 管线 entrypoint 平铺；未编号 = 内部实现/validation）
├── runs/          ④ 运行记录（batch_409.md batch_410.md eidc_fresh_rebuild.md）
└── workflow/      ⑤ 规则与配置（pipeline.md commands.md batches.yaml brand_watchlist.yaml model_name_map.json schemas/ docs/）
```

> 这不是标准 Python package，而是一个**持续运行、持续积累数据、持续形成分析结果的 Research Intelligence Workspace**。
> 顶层只保留 5 个认知入口；脚本按管线顺序 `01→07` 平铺在 scripts/。

## 快速跑一轮

```bash
make -C MIIT miit-run BATCH=410   # P1 搜索 → P2 归档 → P4 宽表 → P4.5 统一Dataset → P5 报告
```

分步见 [workflow/commands.md](workflow/commands.md)；P3 车船税补充为手动步骤。

## 当前状态

已处理 **401–410** 全部批次。统一 Dataset（`data/vehicle_parameters/product_master` + `vehicle_parameter`）当前 **831 车型，全部为乘用车（`vehicle_category == passenger_vehicle`）**：
- **miit_gov / proposed**：409:49 + 410:17（66）
- **eidc / confirmed**：**401-408 全部 fresh rebuild**，合计 765
  - 401:117 / 402:135 / 403:43 / 404:84 / 405:63 / 406:94 / 407:96 / 408:133

> **401-408 EIDC fresh/confirmed + 409-410 Gov fresh/proposed = 干净版本节点。**
> canonical 收敛为乘用车业务事实层：Source archive 保留全量道路机动车辆，`vehicle_parameters/` 只落乘用车（`model_code valid AND vehicle_category==passenger_vehicle`）。

观测时间轴：`observation_id = {batch}:{model_code}:{stage}`，401 confirmed → 410 proposed。
批次索引见 [workflow/docs/公告批次.md](workflow/docs/公告批次.md)，各批运行经验见 [runs/](runs/)。

## 测试

```bash
make -C MIIT test       # 冒烟：所有脚本 --help 可用
```

## 后续方向

- 自动发现 pageId；新增 vs 改款自动标识；差异增量通知
- 跨批次 diff（401 confirmed → 410 proposed）：默认 `analysis_scope='in_scope'`（乘用车）为母体
- 409/410 Gov proposed 批次 fresh 解析（当前为公示 scan，可补 Gov 官方详情页深度参数）
- Agent / API 默认消费 `vehicle_parameters/`（乘用车业务层），不再过滤全量
