---
name: runtime-eval-diagnosis
description: Diagnose explicitly supplied historical mashang runtime eval reports, including hard_pass, soft_pass, failed, contract mismatch, fact_types, and exit_reason.
---

# Runtime Eval Diagnosis

Use this skill for an explicitly supplied historical Runtime eval report. The Runtime implementations have been retired. Current workspace evaluation uses workspace/eval/run_eval.py and its declared result files.

## Steps

1. Read the historical report path supplied with the task.
2. Count hard_pass, soft_pass, and failed.
3. Group soft_pass by eval_intent.
4. Group soft_pass by exit_reason.
5. Inspect fact_types for over-broad or mismatched evidence.
6. Identify whether the problem is likely:
   - eval rule issue
   - planner intent issue
   - tool_router routing issue
   - contract matcher issue

## Constraints

- Diagnose before changing code.
- Do not modify core runtime logic first.
- Preserve compatibility of the existing passed field.
- Prefer smallest possible fix.
