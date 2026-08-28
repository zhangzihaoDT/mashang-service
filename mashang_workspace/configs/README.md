# mashang_workspace / configs

Workspace 业务监测配置目录。存放各类可复用的分析配置和关注列表。

---

## Studies（研究配置域）

**目录**: `studies/`

**用途**: 研究 Runtime 的配置域。将"写死在 plan.md 和 Python 脚本里的分析意图"抽象为机器可读、可校验、可版本化的研究实例（StudySpec），作为研究与脚本之间唯一的意图契约。`StudySpec` 是代码里的类型名，不在目录名/文件名里重复出现。

**布局**:
```text
configs/
└── studies/
    ├── schema.json                 # 本配置域 StudySpec 的 schema（结构规范）
    ├── specs/
    │   └── *.yaml                  # 具体研究实例（文件名 = 实例 id）
    └── classifiers/
        └── *.yaml                  # Classifier Spec（Runtime 判定规则，可带 research/experimental 状态）
```

**文件**:
| 文件 | 说明 |
|------|------|
| `studies/schema.json` | StudySpec JSON Schema（结构规范） |
| `studies/specs/tp_and_mix_ways_market_volume.yaml` | 实例：TP&MIX-ways 细分市场与爆款车型研究（分析研究） |
| `studies/specs/price_down_volume_opportunity.yaml` | 实例：价格下去，什么市场能出量（分析研究，复用同一算法与数据源，改窗口） |
| `studies/specs/historical_opportunity_validation.yaml` | 实例：历史机会验证（两段式验证研究） |
| `studies/specs/price_band_migration.yaml` | 实例：产品升级 or 消费降级（价格带迁移诊断） |
| `studies/specs/mature_market_shock.yaml` | 实例：成熟市场冲击研究（案例对照） |
| `studies/classifiers/market_opportunity_v03_research.yaml` | Classifier Spec：V0.3 Market Opportunity Runtime（research 状态） |

**两种时间形态**（`window` 二选一）：
1. **分析研究**：`window.default`（单段窗口 start/end）
2. **验证研究**：`window.observation`（含 `freeze_date`）+ `window.validation`（两段式，观测窗口只允许冻结判断、验证窗口测量兑现，杜绝 hindsight bias）；验证设计（冻结快照/兑现测量/混淆矩阵/Event Cases/评估问题）放在顶层可选字段 `validation_design`

**校验**:
```bash
python mashang_workspace/utility_scripts/validate_study_spec.py
python mashang_workspace/utility_scripts/validate_study_spec.py --spec <path> --json
```
内置结构校验（必需字段/类型/枚举/语义一致性），若环境安装 `jsonschema` 则额外按 `studies/schema.json` 严格校验。

**约定**:
- 分析意图优先沉淀为研究实例，脚本只保留实现（`analyses[].script_fn` 对应实现函数）
- 扩展新能力域时遵循同构：`studies/specs/`、`classifiers/` 等作为 `studies/` 的子域
- 每次修改实例或校验器后运行 `pytest mashang_workspace/tests/test_study_spec_validator.py -q`

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
