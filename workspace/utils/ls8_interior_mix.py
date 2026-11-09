"""LS8 interior Mix using the launch lock-order and configuration definitions."""
import pandas as pd

from operators.product_attributes import resolve_product_attributes
from utils.config_semantics import resolve_value_code


def mix(orders: pd.DataFrame, config: pd.DataFrame, definition: dict, interior_spec: dict) -> dict:
    start = definition["time_periods"]["LS8"]["end"]
    locks = pd.to_datetime(orders["lock_time"], errors="coerce")
    cutoff = locks.max()
    if pd.isna(cutoff):
        raise ValueError("订单数据缺少有效锁单截止时间")
    # LS8 is the series, including the separately classified LS8Neo generation.
    scope = orders.loc[locks.ge(start) & orders["series"].eq("LS8") &
                       orders["approve_refund_time"].isna() & orders["order_number"].notna()].copy()
    attrs = resolve_product_attributes(scope, definition)
    scope["power"] = attrs.power_type
    pairs = scope[["order_number", "power"]].drop_duplicates()
    if pairs["order_number"].duplicated().any():
        raise ValueError("同一订单存在冲突的动力类型")

    colors = config.loc[
        config["Attribute"].eq("内饰") & config["Order Number"].isin(pairs["order_number"]),
        ["Order Number", "value", "value_code"],
    ].rename(
        columns={"Order Number": "order_number", "value": "color"}
    )
    colors["color"] = colors["color"].astype("string").str.strip()
    colors = colors.loc[colors["color"].notna() & colors["color"].ne("")]
    colors["color"] = [
        resolve_value_code(interior_spec, None if pd.isna(code) else code, color)[1] or color
        for code, color in zip(colors["value_code"], colors["color"])
    ]
    colors = colors[["order_number", "color"]].drop_duplicates()
    coverage = scope.loc[scope["order_number"].isin(colors["order_number"]), "lock_time"]
    matched_cutoff = pd.to_datetime(coverage, errors="coerce").max()
    joined = pairs.merge(colors, how="left", on="order_number")
    conflicts = joined["order_number"].duplicated(keep=False)
    joined.loc[conflicts, "color"] = "配置冲突"
    joined = joined.drop_duplicates("order_number")
    result = {}
    for power in ("增程", "纯电"):
        group = joined.loc[joined["power"].eq(power)]
        counts = group["color"].fillna("缺少内饰配置").value_counts()
        result[power] = {
            "total_orders": len(group),
            "colors": [
                {"color": color, "orders": int(count), "share": int(count) / len(group)}
                for color, count in counts.items()
            ],
        }
    denominators_match = all(
        group["total_orders"] == int(pairs["power"].eq(power).sum())
        and group["total_orders"] == sum(row["orders"] for row in group["colors"])
        for power, group in result.items()
    )
    return {
        "checks": {
            "deduplication": {
                "status": "passed" if joined["order_number"].is_unique and len(joined) == len(pairs) else "failed",
                "eligible_rows": len(scope),
                "distinct_orders": len(pairs),
            },
            "denominators": {"status": "passed" if denominators_match else "failed"},
        },
        "start": start,
        "order_cutoff": cutoff.isoformat(),
        "latest_matched_config_lock_time": None if pd.isna(matched_cutoff) else matched_cutoff.isoformat(),
        "groups": result,
        "unknown_power_orders": int((~pairs["power"].isin(result)).sum()),
        "conflicting_color_orders": int(joined["color"].eq("配置冲突").sum()),
        "warnings": attrs.warnings,
    }
