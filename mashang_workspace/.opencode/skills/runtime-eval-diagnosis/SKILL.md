---
name: runtime-eval-diagnosis
description: Diagnose mashang runtime eval reports, including hard_pass, soft_pass, failed, contract mismatch, fact_types, and exit_reason.
---

# Runtime Eval Diagnosis

Use this skill when analyzing eval/eval_report.json or runtime eval results.

## Steps

1. Read eval/eval_report.json.
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
