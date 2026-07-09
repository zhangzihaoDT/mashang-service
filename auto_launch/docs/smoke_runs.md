# Auto Launch 运行记录

## v0.7 — Operating Loop & Timeline

| 日期 | 命令 | 模式 | 结果 |
|------|------|------|------|
| 2026-07-09 | `python -m auto_launch.cli run-day --date 2026-07-09` | dry-run | daily dry-run + brief 生成正常，brief 输出 96 行 |
| 2026-07-09 | `python -m auto_launch.cli run-day --date 2026-07-09 --output /tmp/brief.md` | dry-run | brief 写入 /tmp/brief.md |
| 2026-07-09 | `python -m auto_launch.cli brief --days 7` | query-only | 6 品牌 13 条事实，含 HOT/official/repeated badge |
| 2026-07-09 | `python -m auto_launch.cli facts --audit` | query-only | 6 facts, brand 100%, source_url 0% |
| 2026-07-09 | `python -m auto_launch.cli timeline --days 30` | query-only | 按月份分组时间线 |
| 2026-07-09 | `python -m auto_launch.cli replay --start-date 2026-07-08 --end-date 2026-07-09` | dry-run | 2 天回放完成 |

## v0.6 — Daily Brief from Facts

| 日期 | 命令 | 模式 | 结果 |
|------|------|------|------|
| 2026-07-09 | `python -m auto_launch.cli brief --days 7` | query-only | 6 品牌 13 条事实，含 HOT/official/repeated badge |
| 2026-07-09 | `python -m auto_launch.cli brief --brand 智己 --days 7` | query-only | 按品牌过滤生效 |
| 2026-07-09 | `python -m auto_launch.cli brief --since 2026-07-01 --until 2026-07-09` | query-only | 时间范围过滤生效 |
| 2026-07-09 | `python -m auto_launch.cli brief --output /tmp/brief.md` | query-only | 写入 96 行 Markdown |

## v0.5 — Fact Quality Loop

| 日期 | 命令 | 模式 | 结果 |
|------|------|------|------|
| 2026-07-09 | `python -m auto_launch.cli inbox --input tests/fixtures/daily_run_sample.md --date 2026-07-09` | import | 8 raw → 6 keep / 2 discard |
| 2026-07-09 | `python -m auto_launch.cli inbox --input tests/fixtures/daily_run_golden.md --date 2026-07-09` | import | 7 raw → 6 keep / 1 discard |
| 2026-07-09 | `python -m auto_launch.cli facts --audit` | query-only | brand 100%, model 83%, source_url 0% |
| 2026-07-09 | `python -m auto_launch.cli facts --stats-by brand` | query-only | 6 brands |

## CLI 版本记录

```bash
python -m auto_launch.cli --help
# Available: daily search normalize inbox facts brief run-day replay timeline
```
