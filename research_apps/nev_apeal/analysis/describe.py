"""Describe the dataset and core APEAL indices."""

import argparse

from ._common import WEIGHT, emit, load, weighted_group, weighted_mean


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("metric", nargs="?", default="APEAL_Index")
    parser.add_argument("--by", default=None)
    args = parser.parse_args()
    df, _ = load()
    metrics = [args.metric] if args.metric in df.columns else [c for c in df.columns if c.endswith("_Index")]
    result = {"rows": len(df), "columns": len(df.columns), "weight": WEIGHT, "weighted_means": {m: weighted_mean(df[m], df[WEIGHT].fillna(1.0)) for m in metrics}}
    if args.by:
        _, meta = load()
        result["by"] = args.by
        result["groups"] = weighted_group(df, args.by, metrics, meta)
    emit({
        **result,
    })


if __name__ == "__main__":
    main()
