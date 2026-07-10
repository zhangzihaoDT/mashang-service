# Output Contract — auto_launch 输出体系

## 顶层职责

```
auto_launch/outputs/
├── runs/            ← 唯一业务交付入口。每次 run 的所有产物在此归档。
├── facts/           ← 长期事实资产（SQLite），跨 run 共享，不被清理。
├── search_cache/    ← 性能缓存（API 原始响应，TTL 24h），可安全清理。
└── _legacy/         ← 历史遗留目录归档，仅由 archive 脚本写入。
```

不再允许的顶层目录：`briefs/`、`owned_brand_daily/`、`search/`、`demo/`、`_migration/`。

## runs/ — 对应三层架构

每次 run 的完整产物归档在 `runs/{YYYYMMDD}/{run_mode}/` 下。

`run_mode` 只允许 ASCII 小写字母、数字、下划线（`[a-z0-9_]+`），不允许中文、空格、路径敏感字符。
品牌中文名通过 `BRAND_SLUG_MAP` 映射为 slug（如 `智己` → `zhiji`）。

### 1. `brand_watch_{slug}` — search：搜索到 facts

来源：`python -m auto_launch.cli search --request "..." --live`

必需文件：

```
search/plan.json         ← 合并后的搜索计划
search/raw.json          ← API 原始响应
search/normalized.json   ← 标准化/去重后的 items
search/audit.json        ← 搜索质量审计
```

可选：

```
reports/daily_brief.md   ← LLM 生成的搜索简报
```

### 2. `brand_daily_{slug}` — report --type brand-daily：facts → 品牌日报

来源：`python -m auto_launch.cli report --type brand-daily --brand <品牌>`

必需文件：

```
manifest.json            ← 运行元数据（command=report, report_type=brand-daily）
summary.md               ← 摘要
reports/brand_daily_summary.md   ← 详细品牌日报
```

纯 facts 只读，不涉及搜索。

### 3. `launcher_daily_run` — daily：ChatGPT Daily Run → facts + report

来源：`python -m auto_launch.cli daily --text "..." --then-report daily-brief`
或 launcher 选项 1

必需文件：

```
reports/daily_brief.md   ← 简报
```

facts 写入 SQLite，不在 runs/ 下保留额外文件。

### 4. `run_day_{slug}` — run-day 编排输出

来源：`python -m auto_launch.cli run-day --brand <品牌>`

run-day 是编排 shortcut：search → facts → report。不是独立能力层。

必需文件：

```
manifest.json            ← 标注 is_orchestration=true
summary.md
search/plan.json
search/raw.json
search/normalized.json
search/audit.json
reports/brand_daily_summary.md
reports/source_audit.md
```

## 通用规则

1. **所有写入 outputs/ 的脚本必须通过 `output_paths.py` 获取路径**。
2. 日期格式统一为 `YYYYMMDD`（无横线），human-readable 可用 `YYYY-MM-DD`。
3. `run_mode` 必须进入路径，不允许混入不同 run_type 产物。
4. 新脚本新增输出路径时必须先扩展 `output_paths.py`。
5. 顶层生产目录白名单：`runs/`、`facts/`、`search_cache/`、`_legacy/`。

## 已废弃/不再生成的路径

| 旧路径 | 废弃原因 | 替代路径 |
|--------|----------|----------|
| `outputs/briefs/` | 与 runs 目录重复 | `runs/*/*/reports/` |
| `outputs/owned_brand_daily/` | 早期顶层目录 | `runs/*/brand_daily_{slug}/` |
| `outputs/search/` | 搜索产物不是独立业务入口 | `runs/*/*/search/` |
| `outputs/demo/` | 仅测试用，不应进入生产 outputs | 无 |
