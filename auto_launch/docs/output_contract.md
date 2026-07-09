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

不再允许的顶层目录：`briefs/`、`owned_brand_daily/`、`search/`、`_migration/`。

## runs/ — 三类 run_mode

每次 run 的完整产物归档在 `runs/{YYYYMMDD}/{run_mode}/` 下。

`run_mode` 只允许 ASCII 小写字母、数字、下划线（`[a-z0-9_]+`），不允许中文、空格、路径敏感字符。
品牌中文名通过 `BRAND_SLUG_MAP` 映射为 slug（如 `智己` → `zhiji`），不可映射时 sanitize 为纯 ASCII。

### 1. `brand_watch_{slug}` — 单次 ad-hoc 搜索

来源：`python -m auto_launch.cli search --request "..." --live`

**必需文件：**

```
search/plan.json         ← 合并后的搜索计划（含 intent / task_config / budget / query_plan）
search/raw.json          ← API 原始响应
search/normalized.json   ← 标准化/去重后的 items
search/audit.json        ← 搜索质量审计
```

这是最简 run_mode。不写入 facts，不生成 reports。`raw.json` 是不可复现的证据，建议长期保留。

### 2. `brand_daily_{slug}` — 自动化品牌每日 Pipeline

来源：`python -m auto_launch.cli run-day --brand ... --brand-name ...` 或 `python -m auto_launch.cli daily --brand ... --brand-name ...`

**必需文件：**

```
manifest.json        ← 运行元数据（命令、参数、log）
summary.md           ← 人类可读摘要
search/plan.json     ← 搜索计划
search/raw.json      ← API 原始响应
search/normalized.json
search/audit.json
facts/facts_audit.json
reports/daily_brief.md
reports/source_audit.json
reports/source_audit.md
```

完整 pipeline：搜索 → 归一化 → facts 入库 → facts audit → source audit → 简报。

### 3. `launcher_daily_run` — 手动 Intake / Launcher Run

来源：`python -m auto_launch.cli launch` 交互菜单 选项 1

**必需文件：**

```
manifest.json     ← 运行元数据（command、input_channel、kept/discard/inserted/updated）
summary.md        ← 运行摘要
reports/daily_brief.md   ← 简报
```

**可选文件：**

```
search/plan.json       ← 仅当 launcher 触发搜索时
search/raw.json
search/normalized.json
search/audit.json
facts/facts_audit.json  ← 仅当 facts 被写入时
```

`manifest.json` 必须包含 `input_channel` 和 `stage`/`status` 字段，表明这是手动输入、可能不含搜索证据。

---

## 通用规则

1. **所有写入 outputs/ 的脚本必须通过 `output_paths.py` 获取路径**，不得硬编码。
2. 日期格式统一为 `YYYYMMDD`（无横线），仅在 human-readable 场景可用 `YYYY-MM-DD`。
3. `run_mode` 必须进入路径，不允许将不同 run_type 的产物混入同一目录。
4. 新脚本新增输出路径时必须先扩展 `output_paths.py`。
5. 顶层生产目录白名单：`runs/`、`facts/`、`search_cache/`、`demo/`、`_legacy/`。
6. `facts/` 和 `search_cache/` 不被 archive 脚本移动。
7. `brand_watch_蔚来` 等历史中文目录保留不重命名，但新 run 必须使用 slug。

## 已废弃/不再生成的路径

| 旧路径 | 废弃原因 | 替代路径 |
|--------|----------|----------|
| `outputs/briefs/` | 与 `runs/{date}/{mode}/reports/daily_brief.md` 重复 | `runs/*/*/reports/daily_brief.md` |
| `outputs/owned_brand_daily/` | 早期顶层目录 | `runs/*/brand_daily_{slug}/` |
| `outputs/search/` | 搜索产物不是独立业务入口 | `runs/*/*/search/` |
