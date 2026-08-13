# mashang_workspace / configs

Workspace 业务监测配置目录。存放各类可复用的分析配置和关注列表。

---

## Monthly Market Report Queries

**文件**: `monthly_market_report_queries.yaml`

**用途**: 24 个月度市场标准查询定义，供市场报告生成脚本使用。

详见文件内注释。

---

## 重点关注新能源品牌

**文件**: `重点关注新能源品牌.json`

**用途**: 重点关注新能源品牌及车型列表。24 个品牌，覆盖鸿蒙智行/蔚来汽车/极氪科技三大分类，以及 14 个独立品牌。

**结构**：
```json
{
  "catalog": "鸿蒙智行",              // 分类名（可包含多个品牌）
  "keywords": ["鸿蒙智行", "HIMA"],    // 分类级 MIIT 匹配关键词
  "brands": [
    {
      "name": "问界",                 // 品牌名
      "keywords": ["问界", "AITO"],    // 品牌级关键词（覆盖 catalog 级）
      "models": ["M9", "M8"]          // 关注车型列表
    }
  ]
}
```

**规则**:
- 一个 catalog 可包含多个 brand（如鸿蒙智行→问界/智界/享界/尊界/尚界）
- brand 级 keywords 优先于 catalog 级（如领克不用 umbrella 的"极氪;领克"）
- 无 brand 级 keywords 的子品牌继承 catalog 级 keywords
- 同一品牌跨 catalog 出现时，models 合并，keywords 取独立条目

**加载方式**: 原 `research_scripts/miit_new_car/diff_watchlist.py` 已随重构移除；当前 MIIT 模块使用 `MIIT/workflow/brand_watchlist.yaml`。

**品牌一览**（24 个）:

| catalog | brand | keywords | 车型数 |
|---------|-------|----------|--------|
| 鸿蒙智行 | 问界/智界/享界/尊界/尚界 | AITO/LUXEED/STELATO/MAEXTRO/SAIC | 3-6 |
| 智己 | 智己 | 智己;IM;上汽集团 | 4 |
| 理想 | 理想 | 理想 | 7 |
| 小米 | 小米 | 小米汽车;小米 | 2 |
| 蔚来汽车 | 蔚来/乐道/萤火虫 | 蔚来/乐道;ONVO/萤火虫;FIREFLY | 1-6 |
| 小鹏 | 小鹏/MONA | 小鹏/MONA;小鹏 | 8 |
| 阿维塔 | 阿维塔 | 阿维塔;AVATR | 3 |
| 深蓝 | 深蓝 | 深蓝 | 6 |
| 零跑 | 零跑 | 零跑 | 9 |
| 腾势 | 腾势 | 腾势;DENZA | 4 |
| 方程豹 | 方程豹 | 方程豹 | 4 |
| 比亚迪 | 比亚迪 | 比亚迪 | 0 |
| 特斯拉 | 特斯拉 | 特斯拉 | 3 |
| 极氪科技 | 极氪/领克 | 极氪/领克 | 7/5 |
| 埃安 | 埃安 | 埃安;AION | 7 |
| 岚图 | 岚图 | 岚图;VOYAH | 5 |

---

## 已移出

| 文件 | 新位置 | 说明 |
|------|--------|------|
| `ls8_competitor_watchlist.csv` | `auto_launch/configs/ls8_competitor_watchlist.csv` | auto_launch 专属 watchlist |
