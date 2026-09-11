#!/usr/bin/env python3
"""Deterministically aggregate preset_coding.json into preset_stats.json.

Preset Coding is the "encoder" research method: the questions are known in
advance (preset_questions/taxonomy.json), the LLM only maps free text to fixed
codes, and all counting happens here. This script never invents content.

Outputs (into the same run dir):
  preset_stats.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
RANKING_GROUPS = ["customer_concern", "positive_feedback", "competitor_attention", "purchase_barrier"]


def load_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def sample(entry: dict) -> dict:
    ref = entry["source_ref"]
    return {
        "record_index": ref["record_index"],
        "source_field": ref["source_field"],
        "expert": ref.get("expert", ""),
        "store": ref.get("store", ""),
        "support_date": ref.get("support_date", ""),
        "quote": entry["quote"],
    }


def grouped_counts(entries: list[dict], group: str) -> list[dict]:
    buckets: dict[str, dict] = {}
    for e in entries:
        if e["group"] != group:
            continue
        b = buckets.setdefault(
            e["question_code"],
            {"code": e["question_code"], "label": e["label"], "by_model": {},
             "records_by_model": {}, "samples": []},
        )
        model = e["model"]
        b["by_model"][model] = b["by_model"].get(model, 0) + 1
        b["records_by_model"].setdefault(model, set()).add(e["source_ref"]["record_index"])
        b["samples"].append(sample(e))
    rows = list(buckets.values())
    for b in rows:
        b["total"] = sum(b["by_model"].values())
        b["records_by_model"] = {m: sorted(s) for m, s in b["records_by_model"].items()}
    rows.sort(key=lambda b: (-b["total"], b["code"]))
    return rows


def store_ops_by_record(entries: list[dict]) -> list[dict]:
    records: dict[int, dict] = {}
    for e in entries:
        if e["group"] != "store_ops":
            continue
        ref = e["source_ref"]
        rec = records.setdefault(
            ref["record_index"],
            {"record_index": ref["record_index"], "expert": ref.get("expert", ""),
             "store": ref.get("store", ""), "support_date": ref.get("support_date", ""), "items": []},
        )
        rec["items"].append({"code": e["question_code"], "label": e["label"], "quote": e["quote"]})
    out = sorted(records.values(), key=lambda r: r["record_index"])
    for r in out:
        r["items"].sort(key=lambda x: x["code"])
    return out


DISPLAY_STATUS = {"display_available": "有", "no_display_car": "无", "not_arrived": "未到店", "not_open": "未开放"}
TEST_DRIVE_STATUS = {"test_drive_available": "有", "no_test_car": "无"}


def availability_rows(entries: list[dict]) -> list[dict]:
    """One row per (store, model): display-car and test-drive status + verbatim quotes."""
    buckets: dict[tuple[str, str], dict] = {}
    for e in entries:
        if e["group"] != "availability":
            continue
        ref = e["source_ref"]
        store = ref.get("store", "")
        key = (store, e["model"])
        b = buckets.setdefault(key, {"store": store, "model": e["model"],
                                     "display": None, "test_drive": None, "quotes": []})
        if e["question_code"] in DISPLAY_STATUS:
            b["display"] = {"code": e["question_code"], "label": DISPLAY_STATUS[e["question_code"]], "quote": e["quote"]}
        elif e["question_code"] in TEST_DRIVE_STATUS:
            b["test_drive"] = {"code": e["question_code"], "label": TEST_DRIVE_STATUS[e["question_code"]], "quote": e["quote"]}
        if e["quote"] not in b["quotes"]:
            b["quotes"].append(e["quote"])
    return sorted(buckets.values(), key=lambda r: (r["store"], r["model"]))


def derive(run_dir: Path, taxonomy_path: Path) -> dict:
    taxonomy = load_json(taxonomy_path)
    entries = load_json(run_dir / "preset_coding.json")
    version = taxonomy["taxonomy_version"]

    bad = [e["coding_id"] for e in entries if e.get("taxonomy_version") != version]
    if bad:
        raise SystemExit(f"taxonomy_version mismatch for: {bad}")

    return {
        "run_id": run_dir.name,
        "taxonomy_version": version,
        "coding_count": len(entries),
        "store_ops": {"records": store_ops_by_record(entries)},
        "availability": {"rows": availability_rows(entries)},
        **{g: {"label": taxonomy["groups"][g]["label"], "counts": grouped_counts(entries, g)} for g in RANKING_GROUPS},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--taxonomy", type=Path, default=APP_DIR / "preset_questions" / "taxonomy.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    stats = derive(args.run_dir, args.taxonomy)
    if args.check:
        print(f"OK {args.run_dir} ({stats['coding_count']} codings)")
        return 0

    out = args.run_dir / "preset_stats.json"
    out.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} ({stats['coding_count']} codings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
