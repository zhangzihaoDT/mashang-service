#!/usr/bin/env python3
"""Build a date-scoped daily run from an existing product_expert run.

Filters evidence / issues / patterns / findings to a single support_date,
re-derives survey_stats (structured track) and convergence, and rewrites
run.json with the daily record_count. Reusable for daily cuts, e.g.
  python scripts/filter_run_by_date.py runs/run_002 runs/run_002_2026-09-12 --date 2026-09-12
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import derive_survey_stats as survey  # noqa: E402
import derive_convergence as convmod  # noqa: E402

DEFAULT_MAPPING = APP_DIR / "preset_questions" / "daily_feedback_mapping.json"
DEFAULT_TAXONOMY = APP_DIR / "preset_questions" / "taxonomy.json"
DEFAULT_REGISTRY = APP_DIR / "patterns" / "pattern_keys.json"


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def iso_of(raw: str | None) -> str | None:
    ts = pd.to_datetime(raw, errors="coerce")
    return None if pd.isna(ts) else ts.date().isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src_run_dir", type=Path)
    parser.add_argument("dst_run_dir", type=Path)
    parser.add_argument("--date", required=True, help="保留的提交日期 YYYY-MM-DD")
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    args = parser.parse_args()

    target = pd.to_datetime(args.date, errors="coerce")
    if pd.isna(target):
        parser.error(f"invalid --date: {args.date!r}")
    target = target.date().isoformat()

    src, dst = args.src_run_dir, args.dst_run_dir
    dst.mkdir(parents=True, exist_ok=True)

    run = load_json(src / "run.json")
    run["run_id"] = dst.name
    run["support_date_filter"] = target
    (dst / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # structured track (reads dst/run.json)
    stats = survey.derive(dst, args.mapping, args.taxonomy, date_filter=target)
    (dst / "survey_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    run["record_count"] = stats["record_count"]
    run["taxonomy_version"] = stats["taxonomy_version"]
    (dst / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # discovery: evidence -> issues -> patterns
    ev = [e for e in load_jsonl(src / "evidence.jsonl") if iso_of(e["source_ref"].get("support_date")) == target]
    kept_ev = {e["evidence_id"]: e for e in ev}
    ev_store = {eid: (e["source_ref"].get("store") or "") for eid, e in kept_ev.items()}

    issues = []
    for it in load_json(src / "issues.json"):
        eids = [x for x in it["evidence_ids"] if x in kept_ev]
        if not eids:
            continue
        it = dict(it)
        it["evidence_ids"] = eids
        it["evidence_count"] = len(eids)
        stores = sorted({ev_store[x] for x in eids if ev_store[x]})
        it["stores"] = stores
        it["store_count"] = len(stores)
        dates = sorted({iso_of(kept_ev[x]["source_ref"].get("support_date")) for x in eids} - {None})
        if dates:
            it["first_seen_date"] = dates[0]
            it["last_seen_date"] = dates[-1]
        issues.append(it)
    kept_iss = {i["issue_id"] for i in issues}

    patterns = []
    for p in load_json(src / "patterns.json"):
        iids = [x for x in p["issue_ids"] if x in kept_iss]
        if not iids:
            continue
        p = dict(p)
        p["issue_ids"] = iids
        patterns.append(p)
    kept_pat = {p["pattern_id"] for p in patterns}

    with (dst / "evidence.jsonl").open("w", encoding="utf-8") as fh:
        for e in ev:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    (dst / "issues.json").write_text(json.dumps(issues, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (dst / "patterns.json").write_text(json.dumps(patterns, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # convergence + findings
    convergences = convmod.derive(dst, args.registry, run.get("executed_at") or target)
    (dst / "convergence.json").write_text(
        json.dumps(convergences, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    conv_by_pat = {c["pattern_id"]: c["convergence_id"] for c in convergences}

    findings = []
    for f in load_json(src / "findings.json"):
        pids = [x for x in f.get("pattern_ids", []) if x in kept_pat]
        if not pids:
            continue
        f = dict(f)
        f["pattern_ids"] = pids
        f["convergence_ids"] = [conv_by_pat[x] for x in pids if x in conv_by_pat]
        if f.get("issue_ids"):
            f["issue_ids"] = [x for x in f["issue_ids"] if x in kept_iss]
        findings.append(f)
    (dst / "findings.json").write_text(json.dumps(findings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"wrote {dst}: records={run['record_count']} evidence={len(ev)} "
        f"issues={len(issues)} patterns={len(patterns)} findings={len(findings)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
