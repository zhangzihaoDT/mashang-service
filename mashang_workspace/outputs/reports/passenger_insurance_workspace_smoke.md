# Passenger Insurance — Workspace Smoke Report

Generated: 2026-06-16 12:07:12
Loader: `shared.loaders.passenger_insurance_loader`
Schema: `shared.schema.passenger_insurance_schema`
Registry: `dataset/passenger_insurance/registry/passenger_insurance_tables.json`

---

## Table Overview

| Table | Status | Rows | Columns | Date Min | Date Max | Sales Sum |
|-------|--------|------|---------|----------|----------|-----------|
| market_energy_monthly | ok | 628 | 5 | 2020-01-01 | 2026-05-01 | 136926671 |
| brand_monthly | ok | 33314 | 11 | 2020-01-01 | 2026-05-01 | 136926671 |
| model_monthly | ok | 99702 | 16 | 2020-01-01 | 2026-05-01 | 136926671 |
| geo_monthly | ok | 51836 | 9 | 2020-01-01 | 2026-05-01 | 136926671 |
| price_segment_monthly | ok | 13158 | 8 | 2020-01-01 | 2026-05-01 | 136926671 |
| product_segment_monthly | ok | 11404 | 13 | 2020-01-01 | 2026-05-01 | 136926671 |

---

**Summary**: 6 tables loaded successfully
**Errors**: 0

### Notes

- This smoke check uses `shared.loaders`, not raw CSV paths.
- No Parquet files were copied into workspace.
- No raw CSV files were read.
- This script does not build or modify the dataset.
