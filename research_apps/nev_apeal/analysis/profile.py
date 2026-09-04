"""Return a labeled profile for a categorical variable."""

import argparse

from ._common import detect_artifact_values, emit, load, valid_groups


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("variable")
    args = parser.parse_args()
    df, meta = load()
    value_labels = meta.variable_value_labels.get(args.variable) or {}
    clean = valid_groups(df, meta, args.variable).dropna()
    counts = clean.value_counts()
    excluded = [d["value"] for d in detect_artifact_values(meta, args.variable)]
    emit({"variable": args.variable, "labels": {str(k): str(v) for k, v in value_labels.items()}, "counts": {str(k): int(v) for k, v in counts.items()}, "excluded_values": excluded})


if __name__ == "__main__":
    main()
