# 数据获取

本目录维护数据源、采集方法、构建契约和来源恢复记录。共享原始数据和更新脚本位于仓库根目录的 `dataset/`。

| 数据源 | 文档 | 内容 |
|---|---|---|
| Tableau 上险数据 | [TP&MIX-ways 数据集](tp_and_mix_ways_dataset.md) | 六张表的来源、构建、增量更新与发布契约 |
| Tableau 历史工作簿 | [BI 语义层恢复](tableau_semantic_layer_recovery.md) | 从工作簿和提取文件恢复数据定义 |
| 乘联会 | [市场数据来源与观察框架](cpca_market_research.md) · [周度采集契约](cpca_weekly_data_capture.md) | 数据来源、观察框架和周度采集 |
| 飞书 | [文档采集](feishu_doc_ingestion.md) | 文档下载、解析与素材提取 |
| 智己官网 | [配置和指导价采集](im_official_guide_price_sourcing.md) | 官方数据来源和采集规则 |
| 懂车帝 | [月销量获取经验](懂车帝月销量获取经验.md) | 月销量数据获取与验证 |
| 订单与下发线索 | [Daily 数据管道](daily_data_pipeline.md) | 数据刷新、校验与观察同步的运行边界 |

[数据集获取与更新操作手册](dataset_operations.md) 提供资产分类、更新器选择、刷新范围和校验步骤。
