# Auto Launch — 项目状态

## 项目定位

Auto Launch 是 mashang-service 根目录下的一个**独立子项目**（`auto_launch/`），定位为汽车上市 / 营销事件监测服务。不属于 mashang_workspace 的分析脚本集，不依赖 workspace 上下文。

当前项目处于"先收缩、再放大"策略的收缩阶段，重心已转向 **Inbox MVP** 极简信息漏斗：

```
raw 输入 → keep/discard → facts 库 → 查询
```

## 目录结构

```
auto_launch/
├── STATUS.md           ← 本文件
├── README.md           项目说明
├── cli.py              统一 CLI 入口（daily / search / normalize / inbox / facts）
├── __init__.py
├── configs/            7 个配置文件
├── src/                16 个 Python 模块
│   ├── (核心搜索管线 13 模块)
│   └── inbox_*.py      Inbox MVP（parser / filter / runner）
│   └── fact_store.py   事实库（SQLite）
├── docs/
│   ├── workflow.md     执行链路文档
│   └── inbox.md        Inbox MVP 文档
├── outputs/            运行时输出（gitignored）
└── tests/              16 个测试文件（11 核心 + 5 Inbox）
```

## 当前已实现能力

### 搜索管线（核心）

- 搜索意图编译 → 任务配置 → 预算分配 → 查询计划 → Volc Search API → 标准化 → 信源解析 → 事件聚类 → 候选门控 → 品牌监控

### Inbox MVP（新增）

- raw text 解析 / 结构化 Markdown 提取
- keep/discard 二分类（品牌+事件类型+动作关键词规则）
- SQLite 事实库（fingerprint 去重，seen_count 更新）
- 交互模式（粘贴 → 解析 → 确认写入）
- 事实查询（按品牌/车型/事件类型/时间窗口）

### CLI 能力

```bash
python -m auto_launch.cli daily        # 品牌每日监控
python -m auto_launch.cli search       # 搜索意图转译
python -m auto_launch.cli normalize    # 搜索结果标准化
python -m auto_launch.cli inbox        # Inbox 导入（--input 或交互）
python -m auto_launch.cli facts        # 事实库查询
```

## 清理完成项

本轮（2026-07-09）已完成以下清理：

- 删除 Makefile 中 13 个 TODO / 已下线 targets
- 删除 `auto_launch/tests/` 中 9 个旧 promptbuilder 测试文件
- 删除 `mashang_workspace/research_scripts/auto_launch/`（旧源码）
- 删除 `mashang_workspace/promptbuilders/auto_launch/`（旧配置+Prompt）
- 删除 `mashang_workspace/research_scripts/auto_launch_monitor.py`
- 删除 `mashang_workspace/tests/promptbuilders/` 中 9 个旧测试文件
- 删除 `mashang_workspace/tests/research_scripts/` 中 11 个旧测试文件
- 删除 `auto_launch/prompts/`（旧 promptbuilder 归档，不参与运行时）
- 删除 `auto_launch/runbooks/`（旧分析手册，不参与运行时）
- 清理 `auto_launch/reports/` 空目录

## 已知问题

1. **workspace_capability_inventory.json** 中的旧路径是文件扫描结果的历史快照，不影响运行
2. `mashang_workspace/docs/miit_*` 文档中引用 `auto_launch_monitor` 的部分未更新

## 下一阶段建议

| 优先级 | 方向 | 说明 |
|--------|------|------|
| P0 | Auto Launch Inbox MVP | ✓ 已完成（parser / filter / store / runner） |
| P0 | Fact Store | ✓ 已完成（SQLite, fingerprint 去重） |
| P0 | keep/discard filter | ✓ 已完成 |
| P1 | search --to-facts | search 结果直接写入 facts |
| P1 | facts query 增强 | 分页 / 聚合 / 导出 |
| P2 | daily brief | 基于 facts 生成每日简报 |
