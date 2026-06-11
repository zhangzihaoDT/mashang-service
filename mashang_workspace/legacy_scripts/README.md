# legacy_scripts — Frozen Reference Area

`legacy_scripts/` is a **frozen reference area** for historical scripts that have been superseded.

## Rules

- **Do not** add new scripts here.
- **Do not** call `legacy_scripts/` from Runtime V2.
- **Do not** use `legacy_scripts/` as default analysis entrypoints.
- If a legacy script is still valuable, wrap it into `runtime_scripts/` or `utility_scripts/` with Result Contract and eval.
- Legacy scripts are not expected to pass modern Contract Gate or Numeric Eval.

## Contents

| File | Superseded By | Notes |
|------|---------------|-------|
| `skills_atp_price.py` | `runtime_scripts/atp_price_report.py` | Kept as historical source/reference for atp_price_report.py |
