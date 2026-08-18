"""Cross-tabulate a segment by an optional second segment, optionally with a metric."""

import argparse

from ._common import emit, load, weighted_mean


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--by", default="SUPER_SEGMENT_DP")
    parser.add_argument("--within", default="YPV_01")
    parser.add_argument("--metric", default=None)
    args = parser.parse_args()
    df, meta = load()
    rows = []
    for left, sub in df.groupby(args.by, dropna=True):
        for right, nested in sub.groupby(args.within, dropna=True):
            row = {
                "segment": str(left),
                "segment_label": (meta.variable_value_labels.get(args.by) or {}).get(left, str(left)),
                "within": str(right),
                "within_label": (meta.variable_value_labels.get(args.within) or {}).get(right, str(right)),
                "n": len(nested),
            }
            if args.metric and args.metric in df.columns:
                row[args.metric] = weighted_mean(nested[args.metric], nested["APEAL_WT"].fillna(1.0))
            rows.append(row)
    emit({"by": args.by, "within": args.within, "metric": args.metric, "rows": rows})


if __name__ == "__main__":
    main()
