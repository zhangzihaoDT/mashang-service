"""Drill down into one segment and return its APEAL profile."""

import argparse

from ._common import emit, load, weighted_mean


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--column", default="YPV_01")
    parser.add_argument("--value", type=float, required=True)
    args = parser.parse_args()
    df, _ = load()
    sub = df[df[args.column] == args.value]
    metrics = [c for c in sub.columns if c.endswith("_Index") or c == "APEAL_Index"]
    emit({"filter": {args.column: args.value}, "n": len(sub), "weighted_means": {m: weighted_mean(sub[m], sub["APEAL_WT"].fillna(1.0)) for m in metrics}})


if __name__ == "__main__":
    main()
