# Workspace Capability Inventory

## 能力定位

Workspace Capability Inventory（能力总览）是 mashang_workspace 的**完整能力地图**，
回答以下核心问题：

- Workspace 到底能让 Agent 做什么？
- Agent 会什么（skills）？
- Agent 能调用什么（scripts）？
- Agent 能查什么（data assets）？
- Agent 已经沉淀了什么（outputs / reports）？
- Agent 的质量如何被验证（evaluation / tests）？

## 与 workspace_skills_catalog 的关系

| 维度 | workspace_skills_catalog | workspace_capability_inventory |
|------|--------------------------|-------------------------------|
| 范围 | Skills 层（Agent 会什么） | Workspace 全部能力资产 |
| 覆盖 | 3 个 workspace skills | Skills + Scripts + Data + Outputs + Quality |
| 粒度 | Skill 级（含 SKILL.md 详情） | 五类资产概览 |
| 用途 | Agent skill 注册与发现 | Workspace 能力地图 / 文档 / 准入 |

**两者互补**：
- `skills_catalog` = Agent 会什么（skill 层）
- `capability_inventory` = Workspace 总能力图谱（全部资产层）

## 五类能力资产说明

### 1. Skills（Agent 会什么）

从 `workspace_skills_catalog.json` 读取（如不存在则回退扫描 `.opencode/skills/`）。

- branded-html-report
- monthly-market-report
- runtime-eval-diagnosis

### 2. Scripts（Agent 能调用什么）

扫描四个脚本目录：

| 目录 | 分类 | 说明 |
|------|------|------|
| `runtime_scripts/` | runtime | 稳定运行入口 |
| `research_scripts/` | research | 研究分析脚本 |
| `utility_scripts/` | utility | 工具、渲染、目录生成脚本 |
| ~~`legacy_scripts/`~~ | ~~legacy~~ | ~~已退休删除~~ |

### 3. Data Assets（Agent 能查什么）

从 docs / configs / shared 引用中提取已知数据资产。

- TP&MIX-ways（6 张 Parquet 表 · shared 数据资产）
- order_data（订单主表）
- assign_data（下发线索表）
- config_attribute（选配属性表）
- monthly_market_report_queries（YAML 查询规范）
- wechat_sync（VOC 微信群消息）

### 4. Outputs / Reports（Agent 已沉淀什么）

扫描 `outputs/reports/` 和 `outputs/monthly_market_report/`。

仅展示文件名、扩展名、修改时间、文件大小。不读取文件内容。

### 5. Evaluation / Quality（Agent 是否可靠）

扫描 `eval/` 和 `tests/` 目录，检测：

- Eval suites（core / research / parser / followup / numeric / reference）
- 测试文件数量
- Eval 报告缓存
- Regression 文档

## 生成方式

```bash
# 推荐方式（Makefile target）
make build-workspace-capability-inventory

# 或直接运行
python mashang_workspace/utility_scripts/build_workspace_capability_inventory.py
```

## 输出文件说明

| 文件 | 格式 | 说明 |
|------|------|------|
| `outputs/reports/workspace_capability_inventory.json` | JSON | 唯一事实源（Single Source of Truth） |
| `outputs/reports/workspace_capability_inventory.md` | Markdown | 可读总览 |
| `outputs/reports/workspace_capability_inventory.html` | HTML | 品牌化页面 |

## 如何扩展新的 Group

1. 在 `build_workspace_capability_inventory.py` 中新增扫描函数（如 `scan_xxx()`）。
2. 在 `build_inventory()` 中调用新函数并追加到 `groups` 列表。
3. 在 `GROUP_LABELS` 中注册标题和副标题。
4. JSON 自动包含新 group。
5. Markdown 和 HTML 自动渲染新 group（从 JSON 读取，无需修改渲染逻辑）。

## 注意事项

- **不扫描 raw data**：`dataset/` 下的原始数据仅展示逻辑路径，不读取文件内容。
- **不展示敏感本地路径**：所有路径均为 workspace 相对路径（`mashang_workspace/...`）。
- **不包含本地用户路径**：输出中不会出现 `/Users/xxx/` 等本地绝对路径。
- **JSON 为唯一事实源**：Markdown 和 HTML 只能从 JSON 渲染，不再扫描文件系统。
- **不扫描大体积文件**：outputs 仅展示元信息（文件名、大小、时间）。
