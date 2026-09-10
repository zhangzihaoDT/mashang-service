"""预售/上市监控公共模块。

- series_group : series_group_logic 统一入口（直载 shared operator）
- phase        : active 代际 + phase 判定（口径来自 business_definition）
- freshness    : order_data 按小时新鲜度 gate
- presale      : 预售小订监控 compute + 飞书卡片
- launch       : 上市锁单监控 compute + 飞书卡片
"""
