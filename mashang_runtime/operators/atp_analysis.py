from __future__ import annotations
import pandas as pd
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_BUSINESS_DEF_FILE = REPO_ROOT / "shared" / "schema" / "business_definition.json"


def _load_business_definition() -> dict:
    try:
        return json.loads(_BUSINESS_DEF_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def apply_business_logic(df: pd.DataFrame, bdef: dict) -> pd.DataFrame:
    from operators.series_group_logic import apply_series_group_logic
    df = apply_series_group_logic(df, bdef)
    product_name = df["product_name"].astype("string").fillna("")

    product_type_logic = bdef.get("product_type_logic", {})
    df["product_type"] = "未知"
    for ptype, expr in product_type_logic.items():
        from operators.series_group_logic import _eval_series_group_logic_expr
        mask = _eval_series_group_logic_expr(product_name, str(expr))
        if mask.any():
            df.loc[mask, "product_type"] = ptype

    model_series_mapping = bdef.get("model_series_mapping", {})
    group_to_series = {}
    for series, groups in model_series_mapping.items():
        for g in groups:
            group_to_series[g] = series
    df["series_derived"] = df["series_group_logic"].map(group_to_series).fillna(df["series_group_logic"])
    return df


def run_atp_operator(df: pd.DataFrame, start: str, end: str) -> dict:
    start_ts = pd.to_datetime(start, errors="coerce")
    end_ts = pd.to_datetime(end, errors="coerce")
    if pd.isna(start_ts) or pd.isna(end_ts):
        return {"type": "atp", "error": "invalid_time_range", "message": "start/end 时间解析失败"}

    if "lock_time" not in df.columns or "invoice_upload_time" not in df.columns:
        return {"type": "atp", "error": "missing_columns", "message": "缺少 lock_time 或 invoice_upload_time 列"}

    df = df.copy()
    df["invoice_upload_time"] = pd.to_datetime(df["invoice_upload_time"], errors="coerce")

    mask = (
        df["lock_time"].notna()
        & (df["invoice_upload_time"] >= start_ts)
        & (df["invoice_upload_time"] < end_ts)
    )
    if "order_type" in df.columns:
        df["order_type"] = df["order_type"].fillna("Unknown").astype(str)
        mask = mask & (df["order_type"] == "用户车")

    df_filtered = df[mask].copy()
    if df_filtered.empty:
        return {
            "type": "atp",
            "start": start_ts.strftime("%Y-%m-%d"),
            "end": end_ts.strftime("%Y-%m-%d"),
            "total_orders": 0,
            "avg_price": None,
            "total_amount": 0,
            "details": [],
        }

    bdef = _load_business_definition()
    df_processed = apply_business_logic(df_filtered, bdef)
    df_processed["product_name"] = df_processed["product_name"].fillna("Unknown")

    group_cols = ["series_derived", "series_group_logic", "product_type", "product_name"]
    available = [c for c in group_cols if c in df_processed.columns]
    agg_df = df_processed.groupby(available).agg(
        order_count=("order_number", "count"),
        avg_price=("invoice_amount", "mean"),
    ).reset_index()

    agg_df.columns = ["Series", "SeriesGroup", "ProductType", "ProductName", "OrderCount", "AvgPrice"]
    agg_df = agg_df.sort_values(by=["Series", "SeriesGroup", "ProductName"])

    total_count = len(df_processed)
    total_amount = float(df_processed["invoice_amount"].sum())
    total_avg = total_amount / total_count if total_count > 0 else 0.0

    details = []
    for _, row in agg_df.iterrows():
        details.append({
            "series": row["Series"],
            "series_group": row["SeriesGroup"],
            "product_type": row["ProductType"],
            "product_name": row["ProductName"],
            "order_count": int(row["OrderCount"]),
            "avg_price": round(float(row["AvgPrice"]), 2),
        })

    return {
        "type": "atp",
        "start": start_ts.strftime("%Y-%m-%d"),
        "end": end_ts.strftime("%Y-%m-%d"),
        "total_orders": total_count,
        "total_amount": total_amount,
        "avg_price": round(total_avg, 2),
        "details": details,
    }
