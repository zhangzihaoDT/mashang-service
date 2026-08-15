# NEV-APEAL Research Loop

```text
Data
  ↓
Measurement Contract / Data Contract
  ↓
Signal Discovery
  ↓
Hypothesis
  ↓
Topic Analysis
  ↓
Validated / Refined Insight
  ↓
Business Question
```

## Run Protocol

1. 先检查 `contracts/measurement.json`、`variables.json` 和 `modules.json`。
2. 使用 `analysis/describe.py` 建立基线，再用 `compare.py`、`segment.py` 寻找 Signal。
3. 在 `runs/<topic>/hypotheses.yaml` 明确待验证解释和反证条件。
4. 使用 `regress.py`、`control.py`、`drilldown.py` 与 `robustness.py` 验证。
5. 把事实、推断和建议分开，最终写入 `reports/<topic>.md`。
