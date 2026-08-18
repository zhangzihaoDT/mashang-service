# TP&MIX-ways — Workspace Smoke Report

Generated: 2026-08-18 12:39:40
Loader: `shared.loaders.tp_and_mix_ways_loader`
Schema: `shared.schema.tp_and_mix_ways_schema`
Registry: `dataset/TP&MIX-ways/registry/tp_and_mix_ways_tables.json`

---

## Table Overview

| Table | Status | Rows | Columns | Date Min | Date Max | Sales Sum |
|-------|--------|------|---------|----------|----------|-----------|
| market_energy_monthly | ok | 643 | 5 | 2020-01-01 | 2026-07-01 | 140086422 |
| brand_monthly | ok | 34178 | 11 | 2020-01-01 | 2026-07-01 | 140086422 |
| model_monthly | ok | 102589 | 16 | 2020-01-01 | 2026-07-01 | 140086422 |
| geo_monthly | ok | 53198 | 9 | 2020-01-01 | 2026-07-01 | 140086422 |
| price_segment_monthly | ok | 13529 | 8 | 2020-01-01 | 2026-07-01 | 140086422 |
| product_segment_monthly | ok | 11507 | 13 | 2020-01-01 | 2026-07-01 | 140086422 |

---

**Summary**: 6 tables loaded successfully
**Errors**: 0

### Notes

- This smoke check uses `shared.loaders`, not raw CSV paths.
- No Parquet files were copied into workspace.
- No raw CSV files were read.
- This script does not build or modify the dataset.
