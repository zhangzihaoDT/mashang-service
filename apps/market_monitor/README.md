# 中国乘用车市场观察台 · China Automotive Market Monitor

V1.0 是 `mashang-service` 内的独立 Web App，部署目标为 Sealos。应用以月为粒度展示市场表现和公告记录，两路来源默认打开各自最新的可用月份。

| 来源 | 数据接口及覆盖口径 | 界面 |
| --- | --- | --- |
| TP&MIX-ways 上险数 | 通过 `shared.loaders.tp_and_mix_ways_loader` 读取 `market_energy_monthly`、`brand_monthly`，按上险统计月展示 | 上险量、同比及环比、新能源渗透率、销量加权价格重心、6/12 月趋势、能源结构与品牌 Top 10 |
| MIIT 工信部公告 | 只读消费平级 `mashang-miit` 的 canonical `data/vehicle_parameters/product_master.json`，按上游 `publish_date` 归月 | 按月查看归档乘用车记录，按批次、发布阶段和关键词筛选，可访问官方证据链接 |

`mashang-miit` 是 MIIT 正式入库数据资产的唯一权威来源，负责采集、解析、核验、入库及覆盖管理。观察台通过 canonical 导出契约解耦。记录是否进入 canonical 数据资产与公告当前所处阶段是两个字段语义，界面沿用上游对公示及正式发布的状态定义。不同月份的归档范围可能不同。

TP&MIX-ways 的业务计算复用 `workspace/research_scripts/market_report/generate_monthly_brief.py` 的整体市场和品牌算子。颜色、显示单位、Top 10 截取和筛选属于前端呈现。两源按各自粒度展示。

## 本地运行

从 `mashang-service` 根目录执行：

```sh
.venv/bin/python -m apps.market_monitor.backend refresh
.venv/bin/python -m apps.market_monitor.backend serve --local
```

预览地址为 `http://127.0.0.1:8765`。默认从平级 `mashang-miit` 定位 canonical 导出，或设置 `MARKET_MONITOR_MIIT_FILE` 为正式导出文件的绝对路径。`MARKET_MONITOR_SNAPSHOT_DIR` 可替换默认快照目录 `apps/market_monitor/var`。预览监听回环地址，`--local` 仅用于本机调试。生产门禁、独立 URL 配置与月度运行见 [Sealos 部署](deploy/README.md)。

## 数据快照与 API

每个来源生成一个 `schema_version=1` 的 JSON 快照，携带来源、源资产时间、快照生成时间和数据月份。上险的源资产时间沿用 registry 构建时间，MIIT 使用 canonical 导出文件的修改时间。快照生成按来源校验并原子发布。首次无来源快照时显示为不可用，所选月份没有数据时返回缺测；历史趋势中缺失月保留空位。

| GET 接口 | 内容 |
| --- | --- |
| `/api/v1/status` | 月度更新频次、可用月份、最新覆盖月、上游时间和快照生成时间 |
| `/api/v1/insurance/YYYY-MM` | 当月指标、能源结构、品牌 Top 10，以及截至当月的 12 个日历月趋势 |
| `/api/v1/miit/YYYY-MM` | 当月 canonical 乘用车归档记录 |

[市场与竞争能力说明](../../docs/业务能力/市场与竞争/README.md) · [上险数据用法](../../docs/业务能力/市场与竞争/tp_and_mix_ways_usage.md)
