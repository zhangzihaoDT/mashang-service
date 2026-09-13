#!/usr/bin/env python3
"""Deterministically aggregate the daily-feedback survey CSV into survey_stats.json.

This is the v0.2 "direct field" track: the questionnaire ships structured choice
columns, so we parse them directly instead of asking an LLM to code free text.
No semantic judgement happens here — column/option -> code mapping is declared in
preset_questions/daily_feedback_mapping.json, labels come from taxonomy.json.

Inputs (defaults relative to this app):
  runs/<run_id>/run.json                  -> dataset path + study_year
  preset_questions/daily_feedback_mapping.json
  preset_questions/taxonomy.json

Output:
  runs/<run_id>/survey_stats.json

The emitted shape mirrors preset_stats.json for the overlapping parts
(store_ops / availability / ranking groups) so build_report.py can render 02.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MAPPING = APP_DIR / "preset_questions" / "daily_feedback_mapping.json"
DEFAULT_TAXONOMY = APP_DIR / "preset_questions" / "taxonomy.json"
RANKING_GROUPS = [
    "customer_concern",
    "positive_feedback",
    "competitor_attention",
    "purchase_barrier",
    "dissatisfaction_theme",
]
SPLIT_RE = re.compile(r"[,，、;；]")


def load_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def norm_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def split_options(value) -> list[str]:
    raw = norm_text(value)
    if not raw:
        return []
    return [p.strip() for p in SPLIT_RE.split(raw) if p.strip()]


def to_iso_date(raw: str | None) -> str | None:
    if not raw:
        return None
    ts = pd.to_datetime(raw, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date().isoformat()


def fmt_md(iso: str) -> str:
    return f"{iso[5:7]}/{iso[8:10]}"


def group_counts(entries: list[dict], group: str, taxonomy: dict) -> dict:
    codes = taxonomy["groups"][group]["codes"]
    buckets: dict[str, dict] = {}
    for e in entries:
        if e["group"] != group:
            continue
        code = e["code"]
        b = buckets.setdefault(
            code,
            {"code": code, "label": codes.get(code, code), "by_model": {},
             "records_by_model": {}, "details": [], "total": 0},
        )
        model = e["model"]
        b["by_model"][model] = b["by_model"].get(model, 0) + 1
        b["records_by_model"].setdefault(model, set()).add(e["record_index"])
        b["total"] += 1
        if e.get("detail") and e["detail"] not in b["details"]:
            b["details"].append(e["detail"])
    rows = list(buckets.values())
    for b in rows:
        b["records_by_model"] = {m: sorted(s) for m, s in b["records_by_model"].items()}
    rows.sort(key=lambda b: (-b["total"], b["code"]))
    return {"label": taxonomy["groups"][group]["label"], "counts": rows}


def derive(run_dir: Path, mapping_path: Path, taxonomy_path: Path, date_filter: str | None = None) -> dict:
    run = load_json(run_dir / "run.json")
    mapping = load_json(mapping_path)
    taxonomy = load_json(taxonomy_path)
    if mapping["taxonomy_version"] != taxonomy["taxonomy_version"]:
        raise SystemExit(
            f"taxonomy_version mismatch: mapping={mapping['taxonomy_version']} "
            f"taxonomy={taxonomy['taxonomy_version']}"
        )

    dataset = Path(run["dataset"])
    if not dataset.exists():
        raise SystemExit(f"dataset not found: {dataset}")
    df = pd.read_csv(dataset, encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]

    meta = mapping["record_meta"]

    # 日期 cut（日报）：run.json 的 support_date_filter 或 CLI --date
    date_filter = date_filter or run.get("support_date_filter")
    if date_filter:
        target = pd.to_datetime(date_filter, errors="coerce")
        if pd.isna(target):
            raise SystemExit(f"invalid date filter: {date_filter!r}")
        col_date = pd.to_datetime(df[meta["support_date"]], errors="coerce").dt.normalize()
        df = df.loc[col_date == target.normalize()].reset_index(drop=True)
        if df.empty:
            raise SystemExit(f"no records for date filter: {date_filter}")

    def col(name: str):
        if name not in df.columns:
            raise SystemExit(f"column not found in dataset: {name!r}")
        return df[name]

    records = []
    for idx in range(len(df)):
        records.append(
            {
                "record_index": idx,
                "submission_id": norm_text(col(meta["submission_id"]).iloc[idx]),
                "submitter": norm_text(col(meta["submitter"]).iloc[idx]),
                "expert": norm_text(col(meta["expert"]).iloc[idx]),
                "city": norm_text(col(meta["city"]).iloc[idx]),
                "store": norm_text(col(meta["store"]).iloc[idx]),
                "support_date": norm_text(col(meta["support_date"]).iloc[idx]),
                "support_date_iso": to_iso_date(norm_text(col(meta["support_date"]).iloc[idx])),
            }
        )

    # ---- scope (full survey sample) ----
    experts: list[str] = []
    city_stores: list[str] = []
    periods: dict[str, dict] = {}
    for r in records:
        if r["expert"] and r["expert"] not in experts:
            experts.append(r["expert"])
        cs = f"{r['city']}·{r['store']}".strip("·")
        if cs and cs not in city_stores:
            city_stores.append(cs)
        iso = r["support_date_iso"]
        if iso:
            periods.setdefault(iso, {"raw": r["support_date"], "start_date": iso, "end_date": iso})
    support_periods = sorted(periods.values(), key=lambda p: p["start_date"])
    if support_periods:
        start = support_periods[0]["start_date"]
        end = support_periods[-1]["end_date"]
        window = fmt_md(start) if start == end else f"{fmt_md(start)}–{fmt_md(end)}"
    else:
        window = "—"

    # ---- store_ops (direct values per record) ----
    store_ops_codes = taxonomy["groups"]["store_ops"]["codes"]
    store_ops_records = []
    for r in records:
        items = []
        for field in mapping["store_ops"]["fields"]:
            raw = norm_text(col(field["column"]).iloc[r["record_index"]])
            if not raw:
                continue
            quote = raw
            if field.get("kind") == "percent":
                try:
                    num = float(raw)
                    quote = f"{num:.0%}" if num <= 1 else f"{num:g}%"
                except ValueError:
                    pass
            items.append({"code": field["code"], "label": store_ops_codes.get(field["code"], field["code"]), "quote": quote})
        store_ops_records.append(
            {
                "record_index": r["record_index"],
                "expert": r["expert"],
                "store": r["store"],
                "support_date": r["support_date"],
                "items": sorted(items, key=lambda x: x["code"]),
            }
        )

    # ---- availability (multi-select model list per record) ----
    avail = mapping["availability"]
    avail_models = avail["models"]
    display_col = col(avail["display_column"])
    test_col = col(avail["test_drive_column"])
    buckets: dict[tuple[str, str], dict] = {}
    rec_disp = {m: 0 for m in avail_models}
    rec_test = {m: 0 for m in avail_models}
    store_disp = {m: set() for m in avail_models}
    store_test = {m: set() for m in avail_models}
    for r in records:
        idx = r["record_index"]
        display_set = set(split_options(display_col.iloc[idx]))
        test_set = set(split_options(test_col.iloc[idx]))
        raw_display = norm_text(display_col.iloc[idx])
        raw_test = norm_text(test_col.iloc[idx])
        store = r["store"] or "—"
        for model in avail_models:
            b = buckets.setdefault((store, model), {"display": False, "test_drive": False, "quotes": []})
            if model in display_set:
                b["display"] = True
                rec_disp[model] += 1
                store_disp[model].add(store)
            if model in test_set:
                b["test_drive"] = True
                rec_test[model] += 1
                store_test[model].add(store)
            for q in (raw_display, raw_test):
                if q and q not in b["quotes"]:
                    b["quotes"].append(q)
    availability_rows = []
    for (store, model), b in buckets.items():
        availability_rows.append(
            {
                "store": store,
                "model": model,
                # label 用「有/无」以适配报告缺失报备表的列头；code 仍来自 taxonomy。
                "display": {
                    "code": "display_available" if b["display"] else "no_display_car",
                    "label": "有" if b["display"] else "无",
                },
                "test_drive": {
                    "code": "test_drive_available" if b["test_drive"] else "no_test_car",
                    "label": "有" if b["test_drive"] else "无",
                },
                "quotes": b["quotes"],
            }
        )
    availability_rows.sort(
        key=lambda x: (x["store"], avail_models.index(x["model"]) if x["model"] in avail_models else 99)
    )
    availability_summary = {
        "denominator_records": len(records),
        "denominator_stores": len({r["store"] for r in records if r["store"]}),
        "by_model": [
            {
                "model": m,
                "display_records": rec_disp[m],
                "test_drive_records": rec_test[m],
                "display_stores": len(store_disp[m]),
                "test_drive_stores": len(store_test[m]),
            }
            for m in avail_models
        ],
    }

    # ---- ranking groups (deterministic option -> code) ----
    ignore_other = set(mapping.get("ignore_other_values", []))
    entries: list[dict] = []
    unmapped: list[dict] = []
    ignored: list[dict] = []
    for group in RANKING_GROUPS:
        gmap = mapping["groups"][group]
        options = gmap["options"]
        aliases = gmap.get("other_aliases", {})
        for source in gmap["sources"]:
            model = source["model"]
            column = source["column"]
            other_column = source.get("other_column")
            for r in records:
                idx = r["record_index"]
                for token in split_options(col(column).iloc[idx]):
                    code = options.get(token)
                    if code is None:
                        unmapped.append({"group": group, "model": model, "record_index": idx, "value": token})
                        continue
                    detail = ""
                    if code == "other" and other_column and other_column in df.columns:
                        note = norm_text(col(other_column).iloc[idx])
                        mapped = aliases.get(note) if note else None
                        if mapped:
                            code = mapped
                        elif note and note in ignore_other:
                            ignored.append({"group": group, "model": model, "record_index": idx, "value": note})
                            continue
                        else:
                            detail = note
                    entries.append(
                        {"group": group, "model": model, "record_index": idx, "code": code, "detail": detail}
                    )

    stats = {
        "run_id": run_dir.name,
        "taxonomy_version": taxonomy["taxonomy_version"],
        "mapping_version": mapping["mapping_version"],
        "dataset": str(dataset),
        "record_count": len(records),
        "coding_count": len(entries),
        "scope": {
            "product_experts": experts,
            "city_stores": city_stores,
            "support_periods": support_periods,
            "window": window,
        },
        "records": records,
        "store_ops": {"records": store_ops_records},
        "availability": {"rows": availability_rows, "summary": availability_summary},
    }
    for group in RANKING_GROUPS:
        stats[group] = group_counts(entries, group, taxonomy)
    if unmapped:
        stats["unmapped_options"] = unmapped
    if ignored:
        stats["ignored_other_values"] = ignored
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--date", default=None, help="仅保留该提交日期（YYYY-MM-DD 或 YYYY/MM/DD），用于日报 cut")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    stats = derive(args.run_dir, args.mapping, args.taxonomy, date_filter=args.date)
    if args.check:
        print(f"OK {args.run_dir} ({stats['record_count']} records, {stats['coding_count']} codings)")
        return 0

    out = args.run_dir / "survey_stats.json"
    out.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} ({stats['record_count']} records, {stats['coding_count']} codings)")
    if stats.get("unmapped_options"):
        print(f"WARN unmapped options: {len(stats['unmapped_options'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
