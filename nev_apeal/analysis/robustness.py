"""Run the primary comparison across BEV/PHEV strata."""

from ._common import emit, load, weighted_group


def main() -> None:
    df, meta = load()
    rows = []
    for value in sorted(df["SUPER_SEGMENT_DP"].dropna().unique()):
        sub = df[df["SUPER_SEGMENT_DP"] == value]
        rows.append({"energy_value": value, "energy_label": (meta.variable_value_labels.get("SUPER_SEGMENT_DP") or {}).get(value, str(value)), "purchase_groups": weighted_group(sub, "YPV_01", ["APEAL_Index"], meta)})
    emit({"stratifier": "SUPER_SEGMENT_DP", "rows": rows})


if __name__ == "__main__":
    main()
