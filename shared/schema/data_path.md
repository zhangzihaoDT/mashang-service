下发线索转化率：dataset/assign_data.csv
试驾分析：dataset/test_drive_data.csv
订单分析：dataset/order_data.parquet
锁单归因：dataset/lock_attribution_data.parquet
选配信息：dataset/config_attribute.parquet
微信群聊：dataset/wechat/\*.parquet
正反向对比：/Users/zihao\*/Documents/coding/dataset/original/业务数据记录\_竞争PK（正反向排名）.csv
智己大区分布：/Users/zihao\_/Documents/coding/dataset/original/store_region_business_definition_data.csv
门店信息（门店代码/名称/城市/大区/类型/开业时间/停业时间）：/Users/zihao\_/Documents/coding/dataset/original/store_info.csv
门店信息备注（字段定义见 store_info_schema.json；读取统一用 shared/loaders/store_info_loader.py，data_path 匹配关键词『门店信息』）：/Users/zihao\_/Documents/coding/dataset/original/store_info.csv
交付-库存（VIN 级生产/质检/入库/发运/交付事件时间线）：dataset/delivery_inventory.parquet

> 仓库内路径相对仓库根解析；外部 original 路径为机器特定绝对路径，换机时需更新。
