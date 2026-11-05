# TP&MIX-ways — Workspace Smoke Report

Generated: 2026-11-03 14:53:10
Loader: `shared.loaders.tp_and_mix_ways_loader`
Schema: `shared.schema.tp_and_mix_ways_schema`
Registry: `dataset/TP&MIX-ways/registry/tp_and_mix_ways_tables.json`

---

## Table Overview

| Table | Status | Rows | Columns | Date Min | Date Max | Sales Sum |
|-------|--------|------|---------|----------|----------|-----------|
| market_energy_monthly | ok | 657 | 5 | 2020-01-01 | 2026-09-01 | 143286867 |
| brand_monthly | ok | 35045 | 11 | 2020-01-01 | 2026-09-01 | 143286867 |
| model_monthly | ok | 105506 | 16 | 2020-01-01 | 2026-09-01 | 143286867 |
| geo_monthly | ok | 54559 | 9 | 2020-01-01 | 2026-09-01 | 143286867 |
| price_segment_monthly | ok | 13887 | 8 | 2020-01-01 | 2026-09-01 | 143286867 |
| product_segment_monthly | ok | 11792 | 13 | 2020-01-01 | 2026-09-01 | 143286867 |

---

**Summary**: 6 tables loaded successfully
**Errors**: 0

### Notes

- This smoke check uses `shared.loaders`, not raw CSV paths.
- No Parquet files were copied into workspace.
- No raw CSV files were read.
- This script does not build or modify the dataset.
