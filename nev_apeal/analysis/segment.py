"""Cross-tabulate a segment by an optional second segment."""

import argparse

from ._common import emit, load


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--by", default="SUPER_SEGMENT_DP")
    parser.add_argument("--within", default="YPV_01")
    args = parser.parse_args()
    df, meta = load()
    rows = []
    for left, sub in df.groupby(args.by, dropna=True):
        for right, nested in sub.groupby(args.within, dropna=True):
            rows.append({"segment": str(left), "segment_label": (meta.variable_value_labels.get(args.by) or {}).get(left, str(left)), "within": str(right), "within_label": (meta.variable_value_labels.get(args.within) or {}).get(right, str(right)), "n": len(nested)})
    emit({"by": args.by, "within": args.within, "rows": rows})


if __name__ == "__main__":
    main()
