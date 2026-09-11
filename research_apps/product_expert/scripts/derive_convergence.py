#!/usr/bin/env python3
"""Deterministically derive convergence.json for a product_expert run.

Implements workflow/convergence.md V0.2:
  pattern.issue_ids -> issues[].evidence_ids -> evidence[].source_ref
  -> attribution (product_experts / city_stores / support_periods)
  -> counts -> recurrence -> evidence_strength

The script never writes semantic objects (patterns/issues/evidence). It only
reads them and emits convergence.json, so counts have a single source of truth.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = APP_DIR / "patterns" / "pattern_keys.json"


def load_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_jsonl(path: Path):
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def normalize_period(raw: str, study_year: int) -> dict:
    """Normalize a raw support_date interval into an ISO start/end range.

    Supported forms: "MM/DD-MM/DD" and "M/D-D" (right side day-only inherits
    the left side month). Cross-month ranges are rejected, never guessed.
    """
    raw = raw.strip()
    if "-" not in raw:
        raise ValueError(f"unsupported support_date (no range): {raw!r}")
    left, right = raw.split("-", 1)
    left = left.strip()
    right = right.strip()

    if "/" not in left:
        raise ValueError(f"unsupported support_date left side: {raw!r}")
    l_month, l_day = (int(p) for p in left.split("/", 1))

    if "/" in right:
        r_month, r_day = (int(p) for p in right.split("/", 1))
    else:
        r_month, r_day = l_month, int(right)

    if l_month != r_month:
        raise ValueError(f"cross-month support_date requires explicit month: {raw!r}")
    if not (1 <= l_month <= 12 and 1 <= l_day <= 31 and 1 <= r_day <= 31):
        raise ValueError(f"invalid support_date: {raw!r}")

    return {
        "raw": raw,
        "start_date": f"{study_year:04d}-{l_month:02d}-{l_day:02d}",
        "end_date": f"{study_year:04d}-{r_month:02d}-{r_day:02d}",
    }


def derive_recurrence(city_store_count: int, series_count: int, support_period_count: int) -> str:
    if city_store_count <= 1:
        return "isolated"
    if city_store_count >= 3 and (series_count >= 2 or support_period_count >= 2):
        return "systemic"
    return "repeated"


STRENGTH_BY_RECURRENCE = {
    "isolated": "weak",
    "repeated": "moderate",
    "systemic": "strong",
}


def derive(run_dir: Path, registry_path: Path, derived_at: str) -> list[dict]:
    run = load_json(run_dir / "run.json")
    run_id = run["run_id"]
    study_year = int(run["study_year"])

    patterns = load_json(run_dir / "patterns.json")
    issues = {row["issue_id"]: row for row in load_json(run_dir / "issues.json")}
    evidence = {row["evidence_id"]: row for row in load_jsonl(run_dir / "evidence.jsonl")}
    registry = {row["pattern_key"] for row in load_json(registry_path)["keys"]}

    errors: list[str] = []
    convergences = []

    for index, pattern in enumerate(patterns, start=1):
        pattern_id = pattern["pattern_id"]
        pattern_key = pattern.get("pattern_key")
        if not pattern_key:
            errors.append(f"{pattern_id}: missing pattern_key")
            continue
        if pattern_key not in registry:
            errors.append(f"{pattern_id}: pattern_key not registered: {pattern_key}")

        issue_ids = list(dict.fromkeys(pattern["issue_ids"]))
        evidence_ids: list[str] = []
        series: list[str] = []
        experts: list[str] = []
        stores: list[str] = []
        periods: dict[tuple[str, str], dict] = {}

        for issue_id in issue_ids:
            issue = issues.get(issue_id)
            if issue is None:
                errors.append(f"{pattern_id}: unknown issue_id {issue_id}")
                continue
            for evidence_id in issue["evidence_ids"]:
                if evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)

        for evidence_id in evidence_ids:
            row = evidence.get(evidence_id)
            if row is None:
                errors.append(f"{pattern_id}: unknown evidence_id {evidence_id}")
                continue
            for value in row.get("series", []):
                if value not in series:
                    series.append(value)
            ref = row["source_ref"]
            expert = ref.get("expert")
            store = ref.get("store")
            raw_period = ref.get("support_date")
            if expert and expert not in experts:
                experts.append(expert)
            if store and store not in stores:
                stores.append(store)
            if raw_period:
                period = normalize_period(raw_period, study_year)
                periods[(period["start_date"], period["end_date"])] = period

        if not evidence_ids:
            errors.append(f"{pattern_id}: no evidence resolved")
            continue

        support_periods = sorted(periods.values(), key=lambda p: (p["start_date"], p["end_date"]))
        recurrence = derive_recurrence(len(stores), len(series), len(support_periods))

        convergences.append(
            {
                "convergence_id": f"CONV-{index:04d}",
                "pattern_id": pattern_id,
                "pattern_key": pattern_key,
                "run_id": run_id,
                "source_issue_ids": issue_ids,
                "source_evidence_ids": evidence_ids,
                "attribution": {
                    "product_experts": experts,
                    "city_stores": stores,
                    "support_periods": support_periods,
                },
                "counts": {
                    "evidence_count": len(evidence_ids),
                    "issue_count": len(issue_ids),
                    "product_expert_count": len(experts),
                    "city_store_count": len(stores),
                    "support_period_count": len(support_periods),
                    "series_count": len(series),
                },
                "cross_store": len(stores) >= 2,
                "cross_series": len(series) >= 2,
                "recurrence": recurrence,
                "evidence_strength": STRENGTH_BY_RECURRENCE[recurrence],
                "temporal_comparison": {"status": "baseline_only"},
                "derived_at": derived_at,
            }
        )

    if errors:
        raise SystemExit("derivation failed:\n  - " + "\n  - ".join(errors))

    return convergences


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="path to runs/<run_id>")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--derived-at", default=None, help="YYYY-MM-DD (default: run.executed_at)")
    parser.add_argument("--check", action="store_true", help="validate without writing")
    args = parser.parse_args()

    run = load_json(args.run_dir / "run.json")
    derived_at = args.derived_at or run.get("executed_at")
    if not derived_at:
        parser.error("no --derived-at and run.json has no executed_at")

    convergences = derive(args.run_dir, args.registry, derived_at)

    if args.check:
        print(f"OK {args.run_dir} ({len(convergences)} convergences)")
        return 0

    out_path = args.run_dir / "convergence.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(convergences, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"wrote {out_path} ({len(convergences)} convergences)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
