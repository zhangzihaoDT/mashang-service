# Operating Loop — 每日运行指南

## 每日运行流程

```bash
# 1. 一键日更（dry-run）
python -m auto_launch.cli run-day --date 2026-07-09

# 2. 一键日更（真实搜索 + 写入 facts）
python -m auto_launch.cli run-day --date 2026-07-09 --live
```

run-day 会自动执行：
1. `daily --to-facts` — 搜索 + 标准化 + 写入 facts
2. `facts --audit` — 事实库质量审计
3. `source-audit` — 信源覆盖审计（复用现有 configs，不新增 `source_coverage_expectations.yaml`）
4. `brief` — 生成 Markdown 简报

输出到 `auto_launch/outputs/runs/{YYYYMMDD}/`：
- `run_manifest.json` — 运行元数据（含 `source_audit_summary`）
- `facts_audit.json` — 质量审计 JSON
- `source_audit.json` — 信源覆盖审计 JSON
- `source_audit.md` — 信源覆盖审计 Markdown
- `daily_brief.md` — 每日简报
- `run_summary.md` — 人类可读摘要（含信源覆盖小节）

## 检查事实库质量

```bash
python -m auto_launch.cli facts --audit
```

关注以下指标：
- **brand / model / event_type** 字段完成率应接近 100%
- **source_url** 完成率 — inbox 导入的 facts 可能缺 URL
- **warnings** — 应尽量归零

## 查看简报

```bash
# 最近 1 天
python -m auto_launch.cli brief

# 最近 7 天
python -m auto_launch.cli brief --days 7

# 写入文件
python -m auto_launch.cli brief --days 7 --output brief.md
```

## 查看时间线

```bash
# 全部品牌
python -m auto_launch.cli timeline --days 30

# 按品牌
python -m auto_launch.cli timeline --brand 智己 --days 30

# 按车型 + 事件类型
python -m auto_launch.cli timeline --model LS6 --event-type 权益调整 --days 14

# 写入文件
python -m auto_launch.cli timeline --brand 智己 --output tl.md
```

## 连续回放

```bash
# 日期范围模式（逐日执行 daily dry-run）
python -m auto_launch.cli replay --start-date 2026-07-07 --end-date 2026-07-09

# inbox fixtures 模式（处理预设文件）
python -m auto_launch.cli replay --input-dir auto_launch/tests/fixtures/daily_runs
python -m auto_launch.cli replay --input-dir auto_launch/tests/fixtures/daily_runs --reset-store
```

fixtures 模式输出：
- 总 raw / keep
- inserted / updated facts
- duplicate rate
- top brands

## 信源覆盖审计

```bash
# 24 重点品牌覆盖（默认）
python -m auto_launch.cli source-audit --watchlist priority --days 7

# LS8 竞品覆盖
python -m auto_launch.cli source-audit --watchlist ls8 --days 7

# JSON 输出
python -m auto_launch.cli source-audit --format json --days 14

# 写入文件
python -m auto_launch.cli source-audit --output sa.md
```

source-audit 复用现有配置，**不新增** `source_coverage_expectations.yaml`：
- 品牌期望列表：`priority_brand_watchlist.yaml`
- LS8 竞品列表：`ls8_competitor_watchlist.yaml`
- 信源分级：`source_tiers.yaml`
- 官方域名：`source_domains.yaml`

### 审计指标说明

| 指标 | 含义 | 健康标准 |
|------|------|----------|
| `official_rate` | 官方源（Tier 1）占比 | ≥ 30% |
| `media_rate` | 垂媒（Tier 2-3）占比 | ≥ 20% |
| `weak_source_count` | 社交/弱信源（Tier 4-5）数量 | < 50% |
| `missing_source_url_count` | 缺 source_url 的事实数 | < 30% |
| `expected_missing` | 期望有覆盖但实际缺失的品牌数 | 0 |
| `expected_official_missing` | 某品牌有事实但无官方源 | 建议补搜 |
| `expected_auto_media_missing` | 某品牌有事实但无垂媒源 | 建议补搜 |

## 事实库健康检查清单

- [ ] `facts --audit` 无 warnings
- [ ] `source-audit` official_rate ≥ 30%
- [ ] `source-audit` expected_missing = 0
- [ ] brand / event_type 完成率 > 90%
- [ ] source_url 完成率持续改善
- [ ] 每次 run-day 产生完整输出（含 source_audit.json / source_audit.md）
- [ ] timeline 按品牌过滤正常
