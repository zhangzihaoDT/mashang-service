# mashang_workspace / configs

Workspace 业务监测配置目录。存放各类可复用的分析配置和关注列表。

---

## LS8 竞争关注品牌-车型列表

**文件**: `ls8_competitor_watchlist.csv`

**用途**: 维护 LS8 竞品与相邻市场关注车型池，供新车事件监测脚本等下游消费。

**当前服务对象**: `auto_launch_monitor.py` 后续 v0.4 `--targets-file` 参数。

### 字段说明

| 字段 | 说明 |
|------|------|
| `watchlist_name` | 关注列表名称，固定为 `LS8 竞争关注品牌-车型列表` |
| `target_id` | 英文小写 snake_case，稳定唯一 ID |
| `brand` | 标准中文品牌名 |
| `brand_aliases` | 品牌别名，`\|` 分隔，用于搜索召回 |
| `model` | 标准车型名 |
| `model_aliases` | 车型别名，`\|` 分隔，用于搜索召回和模型归一 |
| `display_name` | 报告展示用品牌+车型 |
| `group` | 竞品分组（新势力SUV、华为系SUV、吉利系SUV 等） |
| `priority` | 优先级：high / medium / low |
| `active` | true / false，仅 active=true 进入默认监测 |
| `notes` | 备注 |

### 使用原则

- `active=true` 才进入默认监测范围
- `aliases` 字段用于搜索 query 构造和车型名归一化匹配
- 该文件是 workspace 业务配置，不是 shared schema
- 如需修改关注车型，直接编辑 CSV 即可

### 当前关注对象（10 个）

| target_id | display_name | group | priority |
|-----------|-------------|-------|----------|
| leapmotor_d19 | 零跑 D19 | 新势力SUV | high |
| voyah_taishan_x8_phev | 岚图 泰山 X8 PHEV | 央国企新能源SUV | high |
| xpeng_gx | 小鹏 GX | 新势力SUV | high |
| li_i6 | 理想 i6 | 新势力SUV | high |
| onvo_l80 | 乐道 L80 | 蔚来系SUV | high |
| vw_id_era_9x | 大众 ID. ERA 9X | 合资新能源SUV | medium |
| aito_m7 | 问界 M7 | 华为系SUV | high |
| avatr_06 | 阿维塔 06 | 华为系SUV | high |
| lynk_900 | 领克 900 | 吉利系SUV | medium |
| zeekr_8x | 极氪 8X | 吉利系SUV | medium |

---

## Monthly Market Report Queries

**文件**: `monthly_market_report_queries.yaml`

**用途**: 24 个月度市场标准查询定义，供市场报告生成脚本使用。

详见文件内注释。
