"""Cross-tabulate a segment by an optional second segment, optionally with a metric."""

import argparse

from ._common import emit, load, valid_groups, weighted_mean


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--by", default="SUPER_SEGMENT_DP")
    parser.add_argument("--within", default="YPV_01")
    parser.add_argument("--metric", default=None)
    args = parser.parse_args()
    df, meta = load()
    by_clean = valid_groups(df, meta, args.by)
    within_clean = valid_groups(df, meta, args.within)
    rows = []
    for left, sub in df.assign(_by=by_clean, _within=within_clean).groupby(["_by", "_within"], dropna=True):
        (by_val, within_val), nested = left, sub
        row = {
            "segment": str(by_val),
            "segment_label": (meta.variable_value_labels.get(args.by) or {}).get(by_val, str(by_val)),
            "within": str(within_val),
            "within_label": (meta.variable_value_labels.get(args.within) or {}).get(within_val, str(within_val)),
            "n": len(nested),
        }
        if args.metric and args.metric in df.columns:
            row[args.metric] = weighted_mean(nested[args.metric], nested["APEAL_WT"].fillna(1.0))
        rows.append(row)
    emit({"by": args.by, "within": args.within, "metric": args.metric, "rows": rows})


if __name__ == "__main__":
    main()
