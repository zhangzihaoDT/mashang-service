"""Compute pairwise Pearson correlations for declared numeric measures."""

import argparse

from ._common import emit, load


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("metrics", nargs="+", default=["APEAL_Index"])
    args = parser.parse_args()
    df, _ = load()
    matrix = df[args.metrics].corr().round(4).to_dict()
    emit({"metrics": args.metrics, "correlation": matrix})


if __name__ == "__main__":
    main()
