"""Compare a grouping variable against one or more APEAL metrics."""

import argparse

from ._common import emit, load, weighted_group


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", default="YPV_01")
    parser.add_argument("--metrics", nargs="+", default=["APEAL_Index"])
    args = parser.parse_args()
    df, meta = load()
    emit({"group": args.group, "metrics": args.metrics, "rows": weighted_group(df, args.group, args.metrics, meta)})


if __name__ == "__main__":
    main()
