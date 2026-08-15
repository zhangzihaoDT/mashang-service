"""Return a labeled profile for a categorical variable."""

import argparse

from ._common import emit, load


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("variable")
    args = parser.parse_args()
    df, meta = load()
    value_labels = meta.variable_value_labels.get(args.variable) or {}
    counts = df[args.variable].value_counts(dropna=False)
    emit({"variable": args.variable, "labels": {str(k): str(v) for k, v in value_labels.items()}, "counts": {str(k): int(v) for k, v in counts.items()}})


if __name__ == "__main__":
    main()
