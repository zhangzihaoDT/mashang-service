# Auto Launch Promptbuilder

## 定位

| 模块 | 目录 / 文件 | 职责 |
|------|-------------|------|
| **MIIT Promptbuilder** | `promptbuilders/miit_new_car/` | 公告、参数、目录、资质事实（申报阶段信号） |
| **Auto Launch Promptbuilder** | `promptbuilders/auto_launch/` | 上市传播、价格权益、媒体舆论、竞品对标、用户反馈（市场阶段信号） |

### 职责边界

| 维度 | MIIT 模块 | Auto Launch 模块 |
|------|-----------|-----------------|
| 信息源 | 工信部 EIDC 官网（结构化 DOC） | 公开网络：官网/垂媒/社交媒体/论坛 |
| 数据获取方式 | Python 脚本直接抓取 + 解析 | 生成搜索 Prompt → 交给 AI 搜索能力执行 |
| 可确认的信息 | 企业名、公告型号、产品大类、能源类型 | 商品名、价格、上市时间、配置、权益、舆论 |
| 不可确认的信息 | 商品名、价格、上市时间、续航(主公告) | 资质真实性(需 MIIT 交叉验证) |
| 核心输出 | 公告信号简报 + evidence JSON | 搜索 Prompt → AI raw.md → 标准化报告目录 |

## 使用方式

```bash
# 生成搜索 Prompt（推荐）
python mashang_workspace/promptbuilders/auto_launch/promptbuilder.py \
  --brand 智己 \
  --model LS6 \
  --event-type 上市 \
  --event-date 2026-06-25 \
  --window 48h \
  --competitors "小鹏G6,特斯拉Model Y,问界M5" \
  --output outputs/auto_launch/prompts/ls6_launch_search_task.md
```

## Target Profile / Battle Field Resolver

watchlist 是**竞品池**，不含目标车型自身。为了稳定识别目标车型所在战场（target_group），增加了 Target Profile 机制。

### 配置文件

`configs/target_profiles.yaml` 存储目标车型画像：

```yaml
profiles:
  - brand: 智己
    model: LS8
    display_name: 智己 LS8
    group: 大六座新能源 SUV
    segment: 中大型/大型 SUV
    priority: high
    notes: LS8 战场核心目标车型
```

### target_group 解析优先级

| 优先级 | 来源 | CLI 参数 | 适用场景 |
|--------|------|----------|----------|
| 1 | 用户显式传入 | `--target-group` | 临时指定 |
| 2 | target_profiles.yaml 匹配 | `--target-profile-file` | 常用 target 车型 |
| 3 | watchlist 只有一个 dominant group | — | 竞品全部在同一战场 |
| 4 | 无法解析 | — | 退化为 priority 排序 |

### 三个核心概念的职责

| 概念 | 位置 | 职责 | 建议 |
|------|------|------|------|
| **target_profiles.yaml** | `configs/target_profiles.yaml` | 目标车型画像，包含 brand/model/group | 不建议为了匹配 group 把目标车型硬塞进竞品表 |
| **watchlist CSV** | `configs/ls8_competitor_watchlist.csv` | 竞品池，所有 active 竞品列表 | 只放竞品，不包含目标车型 |
| **target_group** | 运行时解析 | 战场边界，决定哪些竞品优先关注 | 从 profile 自动推导，也可手动指定 |

### 状态字段说明

| 字段 | 说明 | 示例值 |
|------|------|--------|
| target_group | 解析后的竞争分组 | 大六座新能源 SUV |
| target_group_source | target_group 来源 | manual / target_profile / dominant_watchlist_group / unknown |
| group_field_available | watchlist CSV 是否存在 group 字段 | 是 / 否 |
| target_group_resolved | target_group 是否成功解析 | 是 / 否 |
| group_filter_applied | group 同组优先是否生效（需字段存在 + 解析成功） | 是 / 否 |
| fallback_rule | 退化规则说明 | priority_only（target_group 未解析） |

## Watchlist Schema Normalization

Watchlist CSV 的字段结构已经标准化，区分"产品战场"和"品牌阵营"两个维度：

### 字段职责

| 字段 | 职责 | 用于 | 示例 |
|------|------|------|------|
| `battle_field_id` | **产品战场** — 用于竞品匹配（主字段） | 同战场竞品筛选 | `large_six_seat_suv` |
| `ecosystem_group` | **品牌阵营** — 用于解释来源结构 | 展示、信息分类 | 新势力SUV |
| `group`（legacy） | **旧分组字段** — 仅做 fallback | 向后兼容 | — |
| `priority` | **战场内部排序** | 同战场内排序 | high / medium |
| `active` | **是否进入候选池** | active 过滤 | true / false |

### competitor_match_field 匹配优先级

1. **battle_field_id**（主字段）— CSV 中存在且非空时使用
2. **ecosystem_group**（第一 fallback）— 当 battle_field_id 未提供时使用
3. **group**（第二 fallback）— 向后兼容 legacy CSV

## Group Taxonomy Normalization

Watchlist CSV 中的 `group` 字段和 target_profiles.yaml 中的 `group` 字段可能写法不一致（如"新势力SUV" vs "大六座新能源 SUV"）。Group Taxonomy 通过 `configs/battle_fields.yaml` 建立一个统一的**竞争战场分类体系**，用 canonical `group_id` 进行同组匹配，而不是依赖中文字符串硬匹配。

### 分类体系结构

```yaml
battle_fields:
  - id: large_six_seat_suv          # 稳定的机器字段，用于匹配
    label: 大六座新能源 SUV          # 展示文本
    aliases:                         # 兼容 CSV / target_profiles 中的不同写法
      - 大六座新能源SUV
      - 大六座 SUV
```

| 字段 | 用途 | 示例 |
|------|------|------|
| `id` | 稳定的 group_id，用于跨配置匹配 | `large_six_seat_suv` |
| `label` | 展示文本 | 大六座新能源 SUV |
| `aliases` | 兼容 CSV / target_profiles 中不同写法 | `大六座新能源SUV`, `大六座 SUV` |

### 归一化流程

1. `load_battle_fields()` 加载 `battle_fields.yaml`
2. `build_group_alias_map()` 构建 `别名 → group_id` 映射表
3. Watchlist 加载后，每个条目的 `group` 通过 `normalize_group()` 转为 canonical `group_id`
4. Target profile 的 `group` 同样归一化
5. `derive_competitors()` 使用 canonical `group_id` 进行同组匹配

### 状态字段说明

| 字段 | 说明 |
|------|------|
| `group_normalization_applied` | Group taxonomy 是否已加载并应用 |
| `same_group_competitor_count` | 同组竞品数量 |
| `supplemented_from_other_groups` | 从其他 group 补充的数量 |
| `group_taxonomy_warning` | 如果同组竞品为 0，输出 warning |

### 三个配置文件的关系

| 文件 | 职责 | 更新频率 |
|------|------|----------|
| `battle_fields.yaml` | 战场分类体系（规范） | 低频（定义新战场时） |
| `target_profiles.yaml` | 目标车型画像 | 低频（有新的 target 车型时）|
| `ls8_competitor_watchlist.csv` | 竞品池 | 高频（竞品变化时） |

## Watchlist Adapter

支持从 CSV watchlist 自动推导竞品列表，无需手动输入 `--competitors`。

### 参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--targets-file` | watchlist CSV 文件路径 | `mashang_workspace/configs/ls8_competitor_watchlist.csv` |
| `--competitor-limit` | 推导竞品的最大数量（默认 5） | `5` |
| `--include-priority` | 按优先级筛选：high / medium / all（默认 all） | `high` |

### 参数优先级

1. **手动 `--competitors`** — 最高优先级，显式传入时不使用 watchlist
2. **`--targets-file` + `--target-model`** — 从 watchlist 自动推导竞品
3. **两者均无** — 保持当前行为，Prompt 中 competitors 标记为 `user_provided_required`

### 三个核心字段

| 字段 | 职责 | 示例 | 缺失时行为 |
|------|------|------|-----------|
| `group` | **战场边界** — 同一 group 的车型视为直接竞品 | 新势力SUV、华为系SUV | 退化为仅按 priority 排序，推导说明中注明 |
| `priority` | **战场内部排序** — 同 group 内高优先级先入选 | high / medium | 默认为 medium |
| `active` | **是否进入候选池** — 仅 active=true 参与推导 | true / false | 视为全部 active，推导说明中注明 |

### 推导规则

1. 默认只使用 **active=true** 的车型（如字段不存在则使用全部）
2. 排除目标车型自身（根据 brand + model 匹配）
3. 识别目标车型所在 **group**，记为 target_group
4. **优先选择同 group 竞品**，同 group 内按 priority 排序：high → medium → low
5. 如果同 group 竞品数量不足 `--competitor-limit`，再从**其他 group 的 high priority** 中补充
6. 最终按 `--competitor-limit` 截断

### 竞品来源标记

生成的 Prompt 中 `competitor_source` 字段标记竞品来源：

| 值 | 含义 |
|----|------|
| `manual` | 用户手动传入 `--competitors` |
| `watchlist` | 从 watchlist 自动推导 |
| `watchlist_empty` | watchlist 未推导出竞品（目标车型不在 watchlist 中） |
| `user_provided_required` | 未指定竞品，需用户手动补充 |

### 字段映射

watchlist CSV 中的字段通过候选映射表自动匹配，不依赖固定列名：

| 规范字段 | 候选列名 |
|----------|---------|
| brand | brand, brand_name, make |
| model | model, model_name, model_code |
| priority | priority, tier, level |
| group | group, segment, battle_field, competitor_group, category |
| display_name | display_name, name, competitor_name, full_name |
| active | active, enabled, is_active |

## Golden Prompt Cases

`outputs/auto_launch/prompts/examples/` 下存放标准 Prompt 样例，用于验证 Promptbuilder 的稳定性。

每个 case 包含两个文件：
- `{case_name}.md` — 生成的搜索 Prompt
- `{case_name}.metadata.json` — 输入参数、竞品来源、校验结果

### 生成

```bash
make build-auto-launch-golden-prompts
```

### 当前 Cases

| Case | case_type | Event 车型 | 本品车型 | 事件 | 窗口 | 竞品来源 |
|------|-----------|-----------|---------|------|------|----------|
| ledao_l80_launch_48h_vs_ls8 | impact_vs_our_model | 乐道 L80 | 智己 LS8 | 上市 | 48h | watchlist |
| wenjie_m7_launch_72h_vs_ls8 | impact_vs_our_model | 问界 M7 | 智己 LS8 | 上市 | 72h | watchlist |
| xiaomi_yu7_launch_72h_vs_competitors | **general_event_intelligence** | 小米 YU7 | （未指定） | 上市 | 72h | manual |
| byd_datang_ev_launch_7d_vs_ls8 | impact_vs_our_model | **比亚迪 大唐EV** | **智己 LS8** | 上市 | 7d | watchlist |

### 校验规则

每个 Prompt 必须通过以下校验：
1. 无未渲染占位符
2. 包含目标品牌和车型
3. 包含事件类型
4. 包含时间窗口
5. 包含至少 1 个竞品
6. 包含 evidence schema 要求
7. 包含全部 6 个检索模块

### 用法示例

```bash
# 从 watchlist 自动推导竞品
python mashang_workspace/promptbuilders/auto_launch/promptbuilder.py \
  --brand 智己 \
  --model LS8 \
  --event-type 上市 \
  --event-date 2026-06-25 \
  --window 48h \
  --targets-file mashang_workspace/configs/ls8_competitor_watchlist.csv \
  --competitor-limit 5 \
  --include-priority high

# 手动指定竞品（优先级更高）
python mashang_workspace/promptbuilders/auto_launch/promptbuilder.py \
  --brand 智己 \
  --model LS6 \
  --event-type 上市 \
  --event-date 2026-06-25 \
  --window 48h \
  --competitors "小鹏G6,特斯拉Model Y,问界M5"
```

## 输入参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--brand` | 品牌（必填） | 智己 |
| `--model` | 车型（必填） | LS6 |
| `--event-type` | 事件类型（必填） | 上市 |
| `--event-date` | 事件日期（与 --window 搭配） | 2026-06-25 |
| `--window` | 时间窗口：48h / 72h / 7d / 14d | 48h |
| `--start` | 自定义开始日期（优先级高于 event-date） | 2026-06-23 |
| `--end` | 自定义结束日期 | 2026-06-27 |
| `--competitors` | 竞品列表（逗号分隔） | 小鹏G6,Model Y |
| `--output` | 输出路径 | outputs/auto_launch/prompts/task.md |

## Migration from auto_launch_monitor

`mashang_workspace/research_scripts/auto_launch_monitor.py` 是旧版搜索+执行+裁判一体脚本（v0.5.8），**已标记 DEPRECATED**。

| 维度 | 旧 auto_launch_monitor | 新 promptbuilder |
|------|----------------------|-----------------|
| 定位 | 搜索+提取+裁判一体 | 搜索 Prompt 生成器 |
| 搜索能力 | 内置 Huoshan 方舟搜索 API 调用 | ❌ 不直接搜索（生成 Prompt → 交给 AI 执行） |
| LLM Judge | 内置 DeepSeek LLM 裁判 | ❌ 不调用 LLM |
| 事件检测 | 规则引擎 + 评分卡 + 多级过滤 | ❌ 不执行事件检测（委托 AI 搜索能力） |
| 事件类型 | 内置 8 种 + CLI 参数 | 从 configs/event_types.yaml 读取 |
| 信源分层 | 内置域名列表 + CLI 参数 | 从 configs/source_tiers.yaml 读取 |
| Watchlist | CSV 文件加载 + 别名匹配 + 冲突检测 | ❌ 不内置（CLI 传入 --competitors） |
| 输出 | JSON/Markdown 报告 | 搜索 Prompt Markdown 文件 |

### 已迁移的概念

| 旧能力 | 新位置 | 说明 |
|--------|--------|------|
| event_types | `configs/event_types.yaml` | 10 种事件类型，含搜索关键词和必需模块 |
| source_types (信源分层) | `configs/source_tiers.yaml` | 3 层信源（Tier 1 官方 / Tier 2 垂媒 / Tier 3 社交） |
| 6 大检索模块 | `templates/search_task_prompt.md` | 事件确认/价格权益/产品定位/竞品对标/媒体反馈/影响判断 |
| evidence schema | `templates/evidence_schema.json` | JSON 输出 schema，含证据溯源 |
| 输出文件命名 | `promptbuilder.py` `--output` | 统一管理 |

### 暂不迁移的旧能力

| 旧能力 | 不迁移理由 |
|--------|-----------|
| 搜索 API 调用（Huoshan/火山引擎） | promptbuilder 职责是生成 Prompt，搜索由 AI 执行 |
| LLM Judge（DeepSeek 裁判） | 同上 |
| 事件提取规则引擎 | 委托 AI 搜索能力完成 |
| 别名匹配 + 冲突检测 | 委托 AI 搜索能力完成 |
| crawl diagnostics | 不再需要（无爬取） |
| 低质量来源过滤（polluted snippet） | 委托 AI 搜索能力完成 |
| 2 个 Config CSV（watchlist / targets） | 通过 `--competitors` CLI 参数传入 |

## 核心问题

Auto Launch Promptbuilder 支持两种用法场景：

| 场景 | case_type | 说明 | CLI 参数要求 |
|------|-----------|------|-------------|
| **竞品事件对本品影响分析** | `impact_vs_our_model` | 判断某竞品的上市/预售/发布事件对我方本品的影响 | 必填 `--our-brand`/`--our-model` |
| **单车型上市事件情报检索** | `general_event_intelligence` | 收集某车型上市事件的市场信息（无本产品对照） | 无需 `--our-brand`/`--our-model` |

推荐主线是 **impact_vs_our_model**，这是 auto_launch Promptbuilder 的核心业务价值。

核心问题：
> **某竞品市场事件，对我方本品造成什么影响？**

系统区分三个业务角色：

| 角色 | CLI 参数 | 说明 |
|------|----------|------|
| **event_model** | `--event-brand` / `--event-model` | 本次发生上市/预售/发布等事件的车型 |
| **our_model** | `--our-brand` / `--our-model` | 我方被影响车型（本品） |
| **competitor_context** | `--competitors` / `--targets-file` | 同战场竞品背景 |

这三个角色在 Prompt 的"业务角色"章节中明确列出，影响判断模块会直接写：
> "判断 event_model 本次事件对 our_model 的潜在影响，并结合 competitor_context 判断战场压力。"

### 历史参数兼容

`--brand` / `--model` 已弃用，请改用 `--event-brand` / `--event-model`。旧参数仍可使用但会输出 deprecation warning。

## 模块边界

| 维度 | MIIT 模块 | Auto Launch 模块 |
|------|-----------|-----------------|
| 信息源 | 工信部 EIDC 官网（结构化 DOC） | 公开网络：官网/垂媒/社交媒体/论坛 |
| 数据获取方式 | Python 脚本直接抓取 + 解析 | 生成搜索 Prompt → 交给 AI 搜索能力执行 |
| 可确认的信息 | 企业名、公告型号、产品大类、能源类型、目录序号 | 商品名、价格、上市时间、配置、权益、舆论 |
| 不可确认的信息 | 商品名、价格、上市时间、续航(主公告) | 资质真实性（需 MIIT 交叉验证） |
| 核心输出 | 公告信号简报 + evidence JSON | 搜索任务 Prompt + 搜索结果摘要 |
| 职责分界 | **公告事实**：参数、目录、资质 | **市场信号**：上市传播、价格权益、媒体舆论、竞品对标、用户反馈 |

## Raw-first Workflow

Auto Launch 采用 **Raw-first** 策略：AI 原始返回（raw.md）是主报告，其余文件均为辅助产物。

### 报告产物优先级

| 优先级 | 文件 | 定位 | 是否可读 |
|--------|------|------|----------|
| 1 | `report.raw.md` | **主报告** — AI 原始返回，原样保留 | ✅ 是，完整信息 |
| 2 | `executive_brief.md` | 一页摘要 — 不替代 raw.md，标注"以 raw.md 为准" | ✅ 是 |
| 3 | `report.index.json` | 机器索引 — event / price / threat / competitors 概要 | ❌ JSON |
| 4 | `report.quality.json` | 质量检查 — validation / schema_gaps / evidence_risk | ❌ JSON |
| 5 | `normalized_evidence.json` | 结构化证据 — 用于索引和质量检查 | ❌ JSON |

### 完整链路

```
promptbuilder.py → 搜索 Prompt (Golden Prompt)
        ↓ (粘贴到 DeepSeek/ChatGPT)
    AI 返回 raw.md
        ↓
validate_ai_response.py → validation.json
normalize_ai_response.py → normalized_evidence.json
package_ai_report.py → report.raw.md + executive_brief.md + report.index.json + report.quality.json
```

### 说明

- **battle_brief.md** 已标记为 `[EXPERIMENTAL]`，不再是主报告。完整业务判断请以 `report.raw.md` 为准。
- **auto_launch_monitor.py** 仍未删除，v0.6 再处理 Legacy Cleanup。

## 文件结构

```
promptbuilders/auto_launch/
├── README.md                        # 本文件
├── promptbuilder.py                 # CLI 入口
├── templates/
│   ├── search_task_prompt.md        # 搜索任务 Prompt 模板
│   └── evidence_schema.json         # 输出 JSON schema
└── configs/
    ├── event_types.yaml             # 事件类型定义
    └── source_tiers.yaml            # 信源分层配置
```

## 六大检索模块

1. **事件确认** — 车型、时间、地点、官方渠道
2. **价格与权益** — 售价、定金、限时权益、金融方案
3. **产品定位与核心卖点** — 尺寸、续航、智驾、动力、差异化卖点
4. **竞品对标** — 价格、配置、参数交叉对比
5. **媒体与用户反馈** — 媒体评价、用户舆情、订单热度
6. **对我方车型影响判断** — 重叠度、威胁评估、应对建议
