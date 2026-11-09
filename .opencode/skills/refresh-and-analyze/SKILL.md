---
name: refresh-and-analyze
description: Run an authorized dataset refresh and a read-only query on the resulting Ticket snapshot. Use for requests combining a refresh with a metric, breakdown or trend.
---

1. Match the requested metric to the query below or an existing business query. Use its declared inputs and scope. For a new metric or a scope conflict, consult only the applicable references in `shared/schema/reference/` and the dataset registry.
2. Call `business_job` once with `operation=refresh_snapshot` and explicit `plan.jobs` and `plan.datasets`. Let the tool resolve the request automatically unless answering a specific follow-up whose trigger ID is already known. Configuration uses `data-refresh-config-attribute`, orders use `data-refresh-daily`, and lock attribution uses `data-refresh-lock-attribution`. Include query dependencies as inputs and refresh only datasets authorized by the request. On rejection or failure, report the stage and stop.
3. Run the query once on the returned `snapshot_path`. The query runs read-only from the configured business checkout (default `~/Documents/github/mashang-service`) using its `.venv/bin/python`. Use only snapshot data files, with no live dataset fallback. Read `status`, `checks`, `warnings`, and the business cutoff fields. Investigate only failed checks, scope conflicts, or stale coverage material to the request. If the request authorizes refreshing a stale dependency, use a new plan with `continue_snapshot` set to the current snapshot version. Never retry a failed write automatically.
4. Return the core counts and shares, denominator and scope, data cutoff, and actual refresh status (including `no_new_data` when applicable). Mention missing, conflicting, or unknown coverage when material. Use file mtime only as file metadata.

### LS8 interior Mix since launch

- Inputs are `order_data` and `config_attribute`. A configuration refresh uses `data-refresh-config-attribute`; include the daily order Job only if authorized and required.
- Run `.venv/bin/python -B -m jobs.ls8_mix --snapshot "<snapshot_path>"` from the business checkout. The existing query reads maintained launch and vehicle definitions and interior aliases. It counts retained locks for LS8 including LS8Neo, deduplicated by order number, and splits power by the version dictionary. Missing and conflicting interior categories remain in the denominator. Unknown power is reported separately.
- Use `scope.time_window.end` for the order cutoff and `result.latest_matched_config_lock_time` for matched configuration coverage. The configuration input has no intrinsic business cutoff.

### Launch lock orders by generation

- Use `order_data` and, for an authorized order refresh, `data-refresh-daily`. Run `.venv/bin/python -B workspace/business_scripts/vehicle_sales_monitor.py --snapshot "<snapshot_path>" --series "<generation>" --phase launch --force-phase` from the business checkout. For LS8 NEO, use generation `LS8Neo`. Pass `--as-of YYYY-MM-DD` only for a requested observation day.
- Select the requested generation from `result.monitors`. For 上市以来锁单数 report `cumulative_lock_count`; for 留存锁单 use `retention_kept`. The former includes approved refunds and the latter excludes them. Both use the launch opening window, exclude test orders and count distinct order numbers. Use `lock_cutoff` as the metric cutoff. Check `metrics.checks` before reporting.
