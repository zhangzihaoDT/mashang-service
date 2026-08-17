# shared — Shared Business Logic & Definition Layer

shared is the shared business logic and business definition layer.

It is consumed by:
- `mashang_workspace` — AI-native analysis workspace
- `mashang_runtime` — Legacy runtime package
- `mashang_runtime_v2` — Future Runtime V2

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
    └── data_path.md                Data path configuration
```

## Principles

- New business analysis capabilities should not be added directly here unless they are stable shared primitives
- Business-facing analysis workflows should first live in `mashang_workspace`
- Operators in `shared/operators/` are the canonical source
- `mashang_runtime/operators/` and `mashang_runtime/schema/` are retained for legacy compatibility
