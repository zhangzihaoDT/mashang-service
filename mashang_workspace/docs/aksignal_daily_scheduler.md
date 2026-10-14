# AKsignal Daily external hook — P0

The existing `utility_scripts/sales_scheduler.py` keeps its 08:50 Daily chain and key-day monitoring. It now polls an optional external-trigger registry once per scheduler tick. It uses `Popen`, never waits for the AKsignal business batch, and treats invalid registry/launch errors as soft failures of the external hook.

Default: **disabled**. No `SCHEDULER_EXTERNAL_JOBS_CONFIG` means no external hooks. The versioned `utility_scripts/external_daily_jobs.json.example` has `enabled=false` and uses `--offline`. This file is an example, not an active production configuration. No Scheduler restart or launch configuration change is part of P0.

AKsignal owns the 08:30 Asia/Shanghai eligibility check, exchange calendar, native run-day lock/checkpoint, publication validation and retry budget. The Service hook only invokes its short controller. On wake it selects the latest eligible 08:30 occurrence; it does not replay every missed historical day. Business runs are `make run-day-offline RUN_DATE=... RUN_FLAGS=--require-complete` (offline) or the existing online run-day entry after later authorization.

## Interfaces

- `ExternalDailyJobs.tick`: optional local registry, absolute executable/cwd, argv list, enabled boolean. No shell interpolation.
- `SCHEDULER_EXTERNAL_JOBS_CONFIG`: local registry path; do not set in production during P0.
- AKsignal `python -m src.daily_schedule --plan --offline`: read-only schedule/date plan.
- AKsignal `python -m src.daily_schedule --tick --offline`: checks persisted eligibility and asynchronously launches a native cache-only batch when needed. This is an executing operation, not a dry-run.
- AKsignal `.run_day/scheduler/{trade_date}.json`: persisted attempts, trigger time, process/log, waiting/blocked/published state and receipt; online/offline share the same retry budget. Maximum three attempts, with 30/90-minute backoff after unsuccessful attempts are observed.

Do not enable a config, remove `--offline`, restart the production Scheduler or deploy without the separate approval required by the development task. Stop/Resume/Logs controls in Hub are P1, and automatic artifact delivery is P2.

## Verification

Use `make verify-scope VERIFY_CHANGED="..."` and then `make verify` with the exact P0 paths. Existing user modifications are outside this change. Include `mashang_workspace/tests/test_vehicle_sales_monitor.py` as an explicit additional Scheduler regression target. The example JSON is manually checked for valid syntax, disabled state and offline argv; the generic scope resolver does not classify `.json.example`.

Offline integration uses an isolated `/private/tmp` AKsignal clone, copied existing caches, and a Python socket guard. The production repositories' data and published outputs are not used as writable integration workspaces.
