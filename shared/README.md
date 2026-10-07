# shared — Shared Business Logic & Definition Layer

shared is the shared business logic and business definition layer.

It is consumed by:
- `mashang_workspace` — AI-native analysis workspace
- `jobs` — deterministic execution contract (Hub/Worker)

## Contents

```
shared/
├── README.md
├── operators/       Reusable deterministic business operators
│   ├── atp_analysis.py
│   ├── assign_conversion.py
│   ├── mature_lock_prediction.py
│   ├── effective_locked_orders.py   ELOE / Backlog 有效率 / 风险暴露量
│   └── ...
└── schema/          Shared business schema/config
    ├── business_definition.json   Vehicle/energy/seat mapping rules
    ├── metrics.json                Metric registry
    ├── schema.md                   Dataset field definitions
    ├── store_info_schema.json      Store/dealer master field schema
    └── data_path.md                Data path configuration

Loaders under `shared/loaders/` provide canonical access to shared data assets:
- `model_positioning_loader.py`  Model positioning knowledge (yaml)
- `tp_and_mix_ways_loader.py`     TP&MIX-ways insurance parquet tables
- `store_info_loader.py`          Store/dealer master CSV + store_name → dealer resolution
```

## Principles

- New business analysis capabilities should not be added directly here unless they are stable shared primitives
- Business-facing analysis workflows should first live in `mashang_workspace`
- Operators in `shared/operators/` are the canonical source
- 旧 `mashang_runtime/`（含其 operators/schema 副本）已退役移除；canonical 位置一直是本目录
