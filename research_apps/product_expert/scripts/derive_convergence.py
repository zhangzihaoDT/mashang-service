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
    """Normalize a raw support_date into an ISO start/end range.

    Supported forms: "MM/DD-MM/DD", "M/D-D" (right side day-only inherits the
    left side month), and single-day "YYYY/M/D" or "M/D" (daily-feedback source).
    Cross-month ranges are rejected, never guessed.
    """
    raw = raw.strip()
    if "-" not in raw:
        parts = [p for p in raw.replace(".", "/").split("/") if p != ""]
        if len(parts) == 3:
            year, month, day = (int(p) for p in parts)
        elif len(parts) == 2:
            year = study_year
            month, day = (int(p) for p in parts)
        else:
            raise ValueError(f"unsupported single support_date: {raw!r}")
        if not (1 <= month <= 12 and 1 <= day <= 31):
            raise ValueError(f"invalid support_date: {raw!r}")
        iso = f"{year:04d}-{month:02d}-{day:02d}"
        return {"raw": raw, "start_date": iso, "end_date": iso}
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

RECURRENCE_RANK = {"isolated": 0, "repeated": 1, "systemic": 2}
COUNT_METRICS = [
    "evidence_count",
    "issue_count",
    "product_expert_count",
    "city_store_count",
    "support_period_count",
    "series_count",
]


def baseline_run_ids(run: dict) -> list[str]:
    """Run manifest may declare one baseline run id or a list; return a list."""
    ids = run.get("comparison_baseline_run_ids")
    if ids:
        return list(ids)
    single = run.get("comparison_baseline_run_id")
    return [single] if single else []


def _count_delta(current: int, baseline: int) -> dict:
    return {"baseline": int(baseline), "current": int(current), "delta": int(current) - int(baseline)}


def _periods(conv: dict) -> dict:
    return {(p["start_date"], p["end_date"]): p for p in conv["attribution"]["support_periods"]}


def build_temporal(current: dict, baseline: dict | None, baseline_run_id: str | None) -> dict:
    """Compare a current Convergence against a baseline Convergence by pattern_key.

    Pure set/array arithmetic on already-derived convergences; no re-derivation and
    no causal interpretation. Only describes coverage and count movement.
    """
    if baseline_run_id is None:
        return {"status": "baseline_only", "notes": "本期无已声明的可比基线。"}

    cur_counts = current["counts"]
    cur_attr = current["attribution"]

    if baseline is None:
        counts = {m: _count_delta(cur_counts[m], 0) for m in COUNT_METRICS}
        return {
            "status": "compared",
            "baseline_run_id": baseline_run_id,
            "compared_run_ids": [baseline_run_id],
            "delta": {
                "presence": "new",
                "counts": counts,
                "attribution": {
                    "added_city_stores": sorted(cur_attr["city_stores"]),
                    "removed_city_stores": [],
                    "added_product_experts": sorted(cur_attr["product_experts"]),
                    "removed_product_experts": [],
                    "added_support_periods": list(_periods(current).values()),
                    "removed_support_periods": [],
                },
                "recurrence": {"baseline": None, "current": current["recurrence"], "changed": False},
                "evidence_strength": {"baseline": None, "current": current["evidence_strength"]},
            },
            "notes": "该 pattern_key 在基线中未出现，标记为新增；无历史统计可比。",
        }

    base_counts = baseline["counts"]
    base_attr = baseline["attribution"]
    evidence_delta = cur_counts["evidence_count"] - base_counts["evidence_count"]
    cur_rank = RECURRENCE_RANK[current["recurrence"]]
    base_rank = RECURRENCE_RANK[baseline["recurrence"]]
    if evidence_delta > 0 or cur_rank > base_rank:
        presence = "expanded"
    elif evidence_delta < 0 or cur_rank < base_rank:
        presence = "contracted"
    else:
        presence = "continued"

    cur_p, base_p = _periods(current), _periods(baseline)
    return {
        "status": "compared",
        "baseline_run_id": baseline_run_id,
        "compared_run_ids": [baseline_run_id],
        "delta": {
            "presence": presence,
            "counts": {m: _count_delta(cur_counts[m], base_counts[m]) for m in COUNT_METRICS},
            "attribution": {
                "added_city_stores": sorted(set(cur_attr["city_stores"]) - set(base_attr["city_stores"])),
                "removed_city_stores": sorted(set(base_attr["city_stores"]) - set(cur_attr["city_stores"])),
                "added_product_experts": sorted(
                    set(cur_attr["product_experts"]) - set(base_attr["product_experts"])
                ),
                "removed_product_experts": sorted(
                    set(base_attr["product_experts"]) - set(cur_attr["product_experts"])
                ),
                "added_support_periods": [cur_p[k] for k in sorted(set(cur_p) - set(base_p))],
                "removed_support_periods": [base_p[k] for k in sorted(set(base_p) - set(cur_p))],
            },
            "recurrence": {
                "baseline": baseline["recurrence"],
                "current": current["recurrence"],
                "changed": baseline["recurrence"] != current["recurrence"],
            },
            "evidence_strength": {
                "baseline": baseline["evidence_strength"],
                "current": current["evidence_strength"],
            },
        },
        "notes": "仅描述证据覆盖与统计变化，不作因果解释。",
    }


def derive(
    run_dir: Path,
    registry_path: Path,
    derived_at: str,
    baseline_dir: Path | None = None,
) -> list[dict]:
    run = load_json(run_dir / "run.json")
    run_id = run["run_id"]
    study_year = int(run["study_year"])

    patterns = load_json(run_dir / "patterns.json")
    issues = {row["issue_id"]: row for row in load_json(run_dir / "issues.json")}
    evidence = {row["evidence_id"]: row for row in load_jsonl(run_dir / "evidence.jsonl")}
    registry = {row["pattern_key"] for row in load_json(registry_path)["keys"]}

    errors: list[str] = []

    # Baseline resolution: explicit --baseline wins, else manifest baseline id(s).
    baseline_dirs: list[tuple[str, Path]] = []
    if baseline_dir is not None:
        baseline_run = load_json(baseline_dir / "run.json") if (baseline_dir / "run.json").exists() else {}
        baseline_dirs.append((baseline_run.get("run_id") or baseline_dir.name, baseline_dir))
    else:
        for bid in baseline_run_ids(run):
            baseline_dirs.append((bid, run_dir.parent / bid))

    baseline_index: dict[str, dict] = {}
    for bid, bdir in baseline_dirs:
        bpath = bdir / "convergence.json"
        if not bpath.exists():
            errors.append(f"baseline run not found: {bid} ({bpath})")
            continue
        for row in load_json(bpath):
            key = row["pattern_key"]
            if key in baseline_index:
                errors.append(f"duplicate pattern_key {key} across baselines ({bid})")
                continue
            baseline_index[key] = row
    baseline_primary = baseline_dirs[0][0] if baseline_dirs else None

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

        temporal = build_temporal(
            {
                "run_id": run_id,
                "counts": {
                    "evidence_count": len(evidence_ids),
                    "issue_count": len(issue_ids),
                    "product_expert_count": len(experts),
                    "city_store_count": len(stores),
                    "support_period_count": len(support_periods),
                    "series_count": len(series),
                },
                "attribution": {
                    "product_experts": experts,
                    "city_stores": stores,
                    "support_periods": support_periods,
                },
                "recurrence": recurrence,
                "evidence_strength": STRENGTH_BY_RECURRENCE[recurrence],
            },
            baseline_index.get(pattern_key),
            baseline_primary,
        )
        if temporal.get("status") == "compared" and baseline_dirs:
            temporal["compared_run_ids"] = [bid for bid, _ in baseline_dirs]

        convergence = {
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
            "temporal_comparison": temporal,
            "derived_at": derived_at,
        }
        convergences.append(convergence)

    if errors:
        raise SystemExit("derivation failed:\n  - " + "\n  - ".join(errors))

    return convergences


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="path to runs/<run_id>")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--derived-at", default=None, help="YYYY-MM-DD (default: run.executed_at)")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="override baseline run dir (default: run.json comparison_baseline_run_id)",
    )
    parser.add_argument("--check", action="store_true", help="validate without writing")
    args = parser.parse_args()

    run = load_json(args.run_dir / "run.json")
    derived_at = args.derived_at or run.get("executed_at")
    if not derived_at:
        parser.error("no --derived-at and run.json has no executed_at")

    convergences = derive(args.run_dir, args.registry, derived_at, baseline_dir=args.baseline)

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
