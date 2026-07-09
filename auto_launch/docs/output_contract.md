# Output Contract — auto_launch 输出体系

## 顶层职责

```
auto_launch/outputs/
├── runs/            ← 唯一业务交付入口。每次 run 的所有产物在此归档。
├── facts/           ← 长期事实资产（SQLite），跨 run 共享，不被清理。
├── search_cache/    ← 性能缓存（API 原始响应，TTL 24h），可安全清理。
├── demo/            ← 非生产演示产物，标注为 _demo。
└── _legacy/         ← 历史遗留目录归档，仅由 archive 脚本写入。
```

### runs/ — 唯一业务交付入口

每次 run（daily 监控、搜索、竞品分析）的完整产物都归档在 `runs/{YYYYMMDD}/{run_mode}/` 下。

**单次 run 的标准目录结构**

```
runs/{YYYYMMDD}/{run_mode}/
├── manifest.json                    ← 运行元数据（命令、参数、log）
├── summary.md                       ← 人类可读摘要
├── search/                          ← 搜索管线证据链
│   ├── plan.json                    ← 合并后的搜索计划（含 intent / task_config / budget / query_plan）
│   ├── raw.json                     ← API 原始响应
│   ├── normalized.json              ← 标准化/去重后的 items
│   └── audit.json                   ← 搜索质量审计
├── facts/                           ← 事实变更记录
│   ├── facts_delta.json             ← 本次 run 新增/更新的事实
│   └── facts_audit.json             ← 事实库质量审计
└── reports/                         ← 最终交付物
    ├── daily_brief.md               ← 每日简报（Markdown）
    ├── daily_brief.html             ← 每日简报（HTML，可选）
    ├── source_audit.md              ← 信源覆盖审计（Markdown）
    └── source_audit.json            ← 信源覆盖审计（JSON）
```

**文件分类**

| 类型 | 文件 | 可复现 | 可清理 | 说明 |
|------|------|--------|--------|------|
| 交付物 | `reports/daily_brief.md` | 可复现（从 facts 生成） | 谨慎 | 最终用户可见 |
| 交付物 | `reports/source_audit.*` | 可复现 | 谨慎 | 质量审计报告 |
| 证据链 | `search/*.json` | 不可复现（API 依赖） | 保留原始 | 搜索管线中间件 |
| 元数据 | `manifest.json` | 不可复现 | 保留 | 运行记录 |
| 摘要 | `summary.md` | 可复现 | 可清理 | 运行摘要 |
| 事实变更 | `facts/*.json` | 可复现（从 SQLite 导出） | 可清理 | 增量审计 |

> `raw.json` 是唯一**不可复现**的证据文件（API 响应可能过期），建议长期保留。

### facts/ — 长期事实资产

SQLite 数据库 `auto_launch_facts.sqlite`，跨 run 累积的精选事实。
- 手动清理，不应被 `outputs clean` 自动删除。
- 是 `runs/*/facts/` 和 `reports/` 的数据上游。

### search_cache/ — 性能缓存

Volc Search API 的原始响应缓存，按日期和 query hash 组织。
- TTL 24h，可安全清理。
- `outputs clean` 命令默认清理此目录。

### demo/ — 非生产演示产物

`python -m auto_launch.cli demo` 的输出。
- 标注为非生产产物。
- 不应混入生产 run 路径。

## 已废弃/不再生成的路径

以下路径**不再**由代码写入。历史数据可通过 `archive_legacy_outputs.py` 归档到 `_legacy/`。

| 旧路径 | 废弃原因 | 新路径 |
|--------|----------|--------|
| `outputs/briefs/` | 与 `runs/{date}/{mode}/reports/daily_brief.md` 重复 | `runs/*/*/reports/daily_brief.md` |
| `outputs/owned_brand_daily/` | 与 `runs/` 职责重叠，早期遗留目录 | `runs/*/{run_mode}/` |
| `outputs/search/` | 搜索产物是 run 的证据链，不应作为独立业务入口 | `runs/*/*/search/` |

## 规则

1. **所有写入 outputs/ 的脚本必须通过 `output_paths.py` 获取路径**，不得硬编码。
2. 日期格式统一为 `YYYYMMDD`（无横线），仅在 human-readable 场景可用 `YYYY-MM-DD`。
3. `run_mode` 必须进入路径，不允许将不同 run_type 的产物混入同一目录。
4. 新脚本新增输出路径时必须先扩展 `output_paths.py`。
5. 顶层生产目录白名单：`runs/`、`facts/`、`search_cache/`、`demo/`、`_legacy/`。
6. `facts/` 和 `search_cache/` 不被 archive 脚本移动。
