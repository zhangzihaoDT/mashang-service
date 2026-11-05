# shared/schema — 业务定义与语义视图

本目录是 service 的 **业务定义唯一入口**，分两层：

| 层 | 内容 | 权威性 | 更新方式 |
|---|---|---|---|
| 机器可读契约 | `*.json` / `*.yaml` / `*.py` | **权威来源**，代码直接加载 | 先改这里 |
| 人类可读视图 | `reference/*.md` | 解释性视图，不得单独修改口径 | 跟随契约更新 |

## 机器可读契约

| 文件 | 内容 | 主要消费方 |
|---|---|---|
| `metrics.json` | 指标注册表（指标 / derived / relation / 别名） | `shared/schema/__init__.py`、分析脚本 |
| `business_definition.json` | 上市/预售时间、车系分组、动力/版本/驱动规则、对公判定 | `shared/operators/*`、`workspace/utils/business.py` |
| `config_semantics.json` | 选配语义（Attribute / value_code / category） | `workspace/utils/config_semantics.py` |
| `model_positioning.yaml` | 车型定位知识 | `shared/loaders/model_positioning_loader.py` |
| `store_info_schema.json` | 门店/经销商主数据字段与编码定义 | `shared/loaders/store_info_loader.py` |
| `tp_and_mix_ways_schema.py` | 乘用车上险数据 6 张表的 grain / dimensions / metrics | `shared/loaders/tp_and_mix_ways_loader.py` |
| `schema.md` | 数据集字段级 schema（订单 / 线索 / 选配 / 库存 / 门店 / 群聊） | 人类查阅；`test_store_info_loader.py` 校验登记 |
| `data_path.md` | 数据路径登记（行情/外部 original 文件） | `workspace/utils/paths.py`、`shared/loaders/store_info_loader.py` |

## 人类可读语义视图（`reference/`）

| 文档 | 对应的权威来源 |
|---|---|
| `reference/metric_definitions.md` | `metrics.json` + `shared/operators/registry.json` |
| `reference/business_glossary.md` | `metrics.json` + `business_definition.json` + `schema.md` |
| `reference/time_window_rules.md` | `shared/operators/time_windows.py` |
| `reference/vehicle_mapping.md` | `business_definition.json`（`series_group_logic` / `model_series_mapping`） |

## 更新规则

1. **口径变更先改机器可读契约**（`metrics.json` / `business_definition.json` / `config_semantics.json`），再同步 `reference/*.md`。
2. `reference/*.md` 中引用的脚本/数据路径必须真实存在；由 `workspace/tests/test_schema_docs_sync.py` 守护。
3. 不在本目录放分析范式、运营手册、项目盘点或原始笔记；这些属于 `docs/`。
4. `schema.md` / `data_path.md` 留在顶层，因为代码与测试按固定路径读取；不要移动。

## 相关文档

- workspace 文档索引：`docs/README.md`
- service 级文档：仓库根 `docs/`
