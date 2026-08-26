#!/usr/bin/env python
"""
LS6 开票 ATP 走势图 — 起点为 CM2（新一代 LS6）上市时间

用法:
    python mashang_workspace/research_scripts/ls6_invoice_atp_trend.py
    python mashang_workspace/research_scripts/ls6_invoice_atp_trend.py --format json
    python mashang_workspace/research_scripts/ls6_invoice_atp_trend.py --output outputs/charts/
    python mashang_workspace/research_scripts/ls6_invoice_atp_trend.py --help
"""

import sys, argparse, json
from pathlib import Path

_WS_ROOT = Path(__file__).resolve().parents[1]
_PRG_ROOT = _WS_ROOT.parent
_RUNTIME_DIR = _PRG_ROOT / "mashang_runtime"
for p in [str(_WS_ROOT), str(_PRG_ROOT), str(_RUNTIME_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd

from utils.paths import ensure_shared_on_path
ensure_shared_on_path()
from operators.atp_analysis import apply_business_logic, _load_business_definition

ORDER_PARQUET = _PRG_ROOT / "dataset" / "order_data.parquet"
SERIES = "LS6"
CM2_LAUNCH = "2025-09-10"


def parse_args():
    p = argparse.ArgumentParser(description="LS6 开票 ATP 走势图（起点 CM2 上市）")
    p.add_argument("--start-date", type=str, default=CM2_LAUNCH,
                   help=f"开始日期（默认 CM2 上市 {CM2_LAUNCH}）")
    p.add_argument("--end-date", type=str, default=None, help="结束日期（默认最新数据日）")
    p.add_argument("--output", type=str, default=None, help="输出目录（默认 outputs/charts 与 outputs/tables）")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json", "csv"])
    return p.parse_args()


def load_baseline_df():
    df = pd.read_parquet(str(ORDER_PARQUET))
    bdef = _load_business_definition()
    df = apply_business_logic(df, bdef)
    df = df[df["series_derived"] == SERIES].copy()
    df["invoice_upload_time"] = pd.to_datetime(df["invoice_upload_time"], errors="coerce")
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    df["order_type"] = df["order_type"].fillna("Unknown").astype(str)
    return df


def weekly_atp(df, start, end):
    start_ts = pd.to_datetime(start)
    end_ts = pd.to_datetime(end) if end else df["invoice_upload_time"].max()
    mask = (
        df["lock_time"].notna()
        & (df["invoice_upload_time"] >= start_ts)
        & (df["invoice_upload_time"] <= end_ts)
        & (df["order_type"] == "用户车")
    )
    sub = df[mask].copy()
    sub["week"] = sub["invoice_upload_time"].dt.to_period("W-MON").dt.start_time
    w = sub.groupby("week").agg(
        atp=("invoice_amount", "mean"),
        vehicles=("order_number", "count"),
        amount=("invoice_amount", "sum"),
    ).reset_index().sort_values("week")
    return w, start_ts, end_ts


def build_chart(weekly, start_ts, out_path):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from utils.plotly_theme import ZH, apply_zh_theme, get_series_color, align_dual_zero

    x = weekly["week"]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=x, y=weekly["vehicles"], name="每周开票台数",
               marker_color=get_series_color("ash"), opacity=0.35, width=3.2e9),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(x=x, y=weekly["atp"], name="周度开票 ATP",
                   mode="lines+markers",
                   line=dict(color=get_series_color("own"), width=2.5),
                   marker=dict(size=6, color=get_series_color("own"))),
        secondary_y=False,
    )

    cm2_ts = pd.Timestamp(CM2_LAUNCH)
    if x.min() <= cm2_ts <= x.max() or x.min() >= cm2_ts:
        fig.add_vline(x=cm2_ts, line=dict(color=ZH["event"], width=1.5, dash="dash"))
        fig.add_annotation(x=cm2_ts, yref="paper", y=1.02, text="CM2 上市 2025-09-10",
                           showarrow=False, font=dict(size=11, color=ZH["event"]))

    fig.update_layout(
        title=dict(text="LS6 开票 ATP 走势（自 CM2 上市以来）", x=0.01,
                   font=dict(size=18, color=ZH["own"])),
        barmode="overlay",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.1, x=0.01),
        margin=dict(l=60, r=60, t=90, b=40),
    )
    fig.update_yaxes(title_text="开票 ATP（元）", secondary_y=False)
    fig.update_yaxes(title_text="每周开票台数", secondary_y=True, showgrid=False)
    fig.update_xaxes(title_text="周（周一为起点）")
    apply_zh_theme(fig, emphasize_zero=True)
    align_dual_zero(fig, y1=weekly["atp"].tolist(), y2=weekly["vehicles"].tolist())
    fig.write_html(str(out_path), include_plotlyjs=True)
    return fig


def main():
    args = parse_args()
    df = load_baseline_df()
    weekly, start_ts, end_ts = weekly_atp(df, args.start_date, args.end_date)

    n_weeks = len(weekly)
    overall_vehicles = int(weekly["vehicles"].sum())
    overall_amount = float(weekly["amount"].sum())
    overall_atp = round(overall_amount / overall_vehicles, 2) if overall_vehicles else None
    last_week = weekly.iloc[-1]

    out_dir = Path(args.output) if args.output else _WS_ROOT / "outputs"
    chart_path = out_dir / "charts" / "ls6_invoice_atp_trend.html"
    csv_path = out_dir / "tables" / "ls6_invoice_atp_trend.csv"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)
    (out_dir / "tables").mkdir(parents=True, exist_ok=True)

    summary = (
        f"LS6 自 CM2 上市（{CM2_LAUNCH}）以来累计开票用户车 {overall_vehicles} 台，"
        f"累计开票 ATP {overall_atp:,.0f} 元；"
        f"最近周（{last_week['week'].strftime('%Y-%m-%d')}）ATP {last_week['atp']:,.0f} 元 / {int(last_week['vehicles'])} 台"
    )

    if args.format in ("terminal", "json"):
        build_chart(weekly, start_ts, chart_path)
        csv_cols = weekly.rename(columns={
            "week": "week_start", "atp": "weekly_atp", "vehicles": "weekly_vehicles", "amount": "weekly_amount"
        })
        csv_cols.to_csv(csv_path, index=False)

        print("[Summary]")
        print(f"  {summary}")
        print()
        print("[Scope]")
        print(f"  数据源: {ORDER_PARQUET}")
        print(f"  时间窗口: {start_ts.strftime('%Y-%m-%d')} ~ {end_ts.strftime('%Y-%m-%d')}")
        print(f"  过滤条件: series_derived=LS6 (CM0/CM1/CM2) + order_type='用户车' + lock_time 非空")
        print(f"  指标口径: 周度开票 ATP = mean(invoice_amount) by invoice_upload_time (W-MON)")
        print()
        print("[Result]")
        print(f"  周数: {n_weeks} | 累计开票用户车: {overall_vehicles} 台 | 累计 ATP: {overall_atp:,.0f} 元")
        print(f"  最近周: {last_week['week'].strftime('%Y-%m-%d')} ATP {last_week['atp']:,.0f} 元 / {int(last_week['vehicles'])} 台")
        print()
        print("[Output]")
        print(f"  HTML: {chart_path.resolve()}")
        print(f"  CSV : {csv_path.resolve()}")

    if args.format == "json":
        contract = {
            "status": "success",
            "script": "mashang_workspace/research_scripts/ls6_invoice_atp_trend.py",
            "scope": {
                "data_source": str(ORDER_PARQUET),
                "time_window": {"start_date": start_ts.strftime("%Y-%m-%d"), "end_date": end_ts.strftime("%Y-%m-%d")},
                "filters": {"series": SERIES, "order_type": "用户车", "lock_time": "notna"},
                "metric_definition": "weekly ATP = mean(invoice_amount) by invoice_upload_time week (W-MON); 起点 CM2 上市 = business_definition.time_periods.CM2.end",
            },
            "result": {
                "summary": summary,
                "metrics": {
                    "overall_vehicles": overall_vehicles,
                    "overall_atp": overall_atp,
                    "weekly_rows": n_weeks,
                    "last_week_start": last_week["week"].strftime("%Y-%m-%d"),
                    "last_week_atp": round(float(last_week["atp"]), 2),
                    "last_week_vehicles": int(last_week["vehicles"]),
                },
                "tables": [
                    {"name": "weekly_atp", "path": str(csv_path),
                     "columns": ["week_start", "weekly_atp", "weekly_vehicles", "weekly_amount"]}
                ],
            },
            "artifacts": {"html": str(chart_path), "csv": str(csv_path)},
            "followup_context": {
                "metric": "atp_price", "series": SERIES, "group_by": "week",
                "available_dimensions": ["product_name", "energy_type", "city"],
                "top_entities": [],
            },
            "warnings": [],
            "errors": [],
        }
        print(json.dumps(contract, ensure_ascii=False, indent=2))

    if args.format == "csv":
        csv_cols = weekly.rename(columns={
            "week": "week_start", "atp": "weekly_atp", "vehicles": "weekly_vehicles", "amount": "weekly_amount"
        })
        print(csv_cols.to_csv(index=False), end="")


if __name__ == "__main__":
    main()
