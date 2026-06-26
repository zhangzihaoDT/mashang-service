#!/usr/bin/env python3
"""
车系上市以来分车型锁单数/占比变化，支持周度或月度聚合

用法:
    python research_scripts/model_share_trend.py --series LS8 --period week
    python research_scripts/model_share_trend.py --series LS9 --period month
    python research_scripts/model_share_trend.py --series LS6 --period month --limit 5
    python research_scripts/model_share_trend.py --series LS8 --period week --format csv --output outputs/tables/
    python research_scripts/model_share_trend.py --series LS9 --period month --format json
    python research_scripts/model_share_trend.py --series LS9 --period month --format report
"""

import sys, argparse, json
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = REPO_ROOT / "mashang_workspace"
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

import pandas as pd
from utils.result_contract import build_success_contract, save_contract_json, contract_to_terminal
from utils.plotly_theme import ZH, apply_zh_theme, get_series_color
import plotly.graph_objects as go

ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"


def load_launch_date(series: str) -> str:
    try:
        with open(BUSINESS_DEF) as f:
            bd = json.load(f)
        return bd["time_periods"][series]["end"]
    except Exception:
        return None


def simplify_product(name: str, series: str) -> str:
    for prefix in [f"智己{series} ", f"智己{series}"]:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def period_label(lock_time: pd.Series, period: str) -> pd.Series:
    if period == "week":
        iso = lock_time.dt.isocalendar()
        return iso["year"].astype(int).astype(str) + "-W" + iso["week"].astype(int).astype(str).str.zfill(2)
    elif period == "month":
        return lock_time.dt.to_period("M").astype(str)


def parse_args():
    p = argparse.ArgumentParser(description="车系上市以来分车型锁单数/占比变化（周/月）")
    p.add_argument("--series", type=str, default="LS8", help="车系代码 (e.g. LS8, LS9, LS6)")
    p.add_argument("--period", type=str, choices=["week", "month"], default="week", help="聚合粒度: week 或 month")
    p.add_argument("--output", type=str, help="输出目录 (默认 outputs/tables/)")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "csv", "json", "report"])
    p.add_argument("--limit", type=int, default=0, help="限制展示车型数 (0=全部)")
    p.add_argument("--order-type", type=str, default=None, help="订单类型过滤 (如 用户车, 员工车)")
    return p.parse_args()


def main():
    args = parse_args()
    series = args.series
    period = args.period

    launch_date = load_launch_date(series)
    if not launch_date:
        print(f"错误: 在 business_definition.json 中未找到 {series} 的上市时间")
        sys.exit(1)

    t_start = pd.Timestamp(launch_date)
    t_end = pd.Timestamp(datetime.now().date()) + pd.Timedelta(days=1)

    df = pd.read_parquet(str(ORDER_PARQUET))
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    df = df[df["lock_time"].notna()].copy()

    df_car = df[df["series"] == series].copy()
    df_car = df_car[(df_car["lock_time"] >= t_start) & (df_car["lock_time"] < t_end)]
    if args.order_type:
        df_car = df_car[df_car["order_type"] == args.order_type].copy()

    df_car["period_label"] = period_label(df_car["lock_time"], period)
    df_car.sort_values("lock_time", inplace=True)

    period_total = df_car.groupby("period_label")["order_number"].nunique()
    period_model = df_car.groupby(["period_label", "product_name"])["order_number"].nunique().reset_index()
    period_model.rename(columns={"order_number": "lock_count"}, inplace=True)
    period_model["share"] = period_model.apply(
        lambda r: round(r["lock_count"] / period_total.get(r["period_label"], 1), 4), axis=1
    )
    period_model["model_short"] = period_model["product_name"].apply(lambda n: simplify_product(n, series))

    all_periods = sorted(period_model["period_label"].unique())
    models_in_order = (
        period_model.groupby("product_name")["lock_count"].sum().sort_values(ascending=False).index.tolist()
    )
    if args.limit > 0:
        top_models = models_in_order[:args.limit]
        period_model = period_model[period_model["product_name"].isin(top_models)]
        models_in_order = top_models

    pivot = period_model.pivot_table(
        index="period_label", columns="model_short", values="lock_count", aggfunc="sum", fill_value=0
    )
    pivot_share = period_model.pivot_table(
        index="period_label", columns="model_short", values="share", aggfunc="sum", fill_value=0
    )
    pivot = pivot.reindex(columns=[simplify_product(m, series) for m in models_in_order], fill_value=0)
    pivot_share = pivot_share.reindex(columns=[simplify_product(m, series) for m in models_in_order], fill_value=0)

    total_lock = int(period_total.sum())
    period_count = len(all_periods)
    period_unit = "周" if period == "week" else "个月"

    rows = []
    for lbl in all_periods:
        for _, r in period_model[period_model["period_label"] == lbl].iterrows():
            rows.append({
                "period": lbl, "model": r["model_short"],
                "lock_count": int(r["lock_count"]), "share": r["share"],
            })

    metric_def = f"lock_count = COUNTD(order_number WHERE lock_time IS NOT NULL) per {period} per product_name; share = lock_count / {period}_total"

    filters = {"series": series}
    if args.order_type:
        filters["order_type"] = args.order_type
    scope = {
        "data_source": str(ORDER_PARQUET),
        "time_window": {"start_date": launch_date, "end_date": datetime.now().strftime("%Y-%m-%d"), "type": "since_launch"},
        "filters": filters,
        "metric_definition": metric_def,
    }
    result = {
        "summary": f"{series} 上市({launch_date})以来共 {period_count} {period_unit}，累计锁单 {total_lock} 单",
        "metrics": {"total_lock_count": total_lock, f"{period}_count": period_count},
        "tables": [
            {
                "name": f"{period}ly_lock_count",
                "columns": ["period", "model", "lock_count", "share"],
                "rows": rows,
            },
            {
                "name": f"{period}ly_lock_count_pivot",
                "columns": ["period_label"] + [simplify_product(m, series) for m in models_in_order],
                "rows": [{"period": idx, **{c: int(v) for c, v in row.items()}} for idx, row in pivot.iterrows()],
            },
            {
                "name": f"{period}ly_share_pivot",
                "columns": ["period_label"] + [simplify_product(m, series) for m in models_in_order],
                "rows": [{"period": idx, **{c: round(v, 4) for c, v in row.items()}} for idx, row in pivot_share.iterrows()],
            },
        ],
    }

    cmd = "python " + " ".join(sys.argv)
    ctx = {"metric": "lock_count", "series": series, "group_by": "product_name",
           "time_window": {"start_date": launch_date, "end_date": datetime.now().strftime("%Y-%m-%d")},
           "available_dimensions": ["product_name", "license_city"]}

    contract = build_success_contract(
        script="research_scripts/model_share_trend.py", command=cmd,
        scope=scope, result=result, followup_context=ctx,
    )

    out_dir = Path(args.output) if args.output else REPO_ROOT / "outputs" / "tables"

    if args.format == "terminal":
        print(contract_to_terminal(contract))
        print()
        period_title = "Weekly" if period == "week" else "Monthly"
        print(f"  [{period_title} Lock Count Pivot Table]")
        label_width = 14 if period == "week" else 10
        print(f"  {'Period':<{label_width}}", end="")
        for m in pivot.columns:
            print(f"{m:>28}", end="")
        print()
        for idx, row in pivot.iterrows():
            print(f"  {idx:<{label_width}}", end="")
            for v in row:
                print(f"{int(v):>28}", end="")
            print()
        print()
        print(f"  [{period_title} Share Pivot Table]")
        print(f"  {'Period':<{label_width}}", end="")
        for m in pivot_share.columns:
            print(f"{m:>28}", end="")
        print()
        for idx, row in pivot_share.iterrows():
            print(f"  {idx:<{label_width}}", end="")
            for v in row:
                print(f"{v:>28.1%}", end="")
            print()

    elif args.format == "report":
        _generate_report(series, period, launch_date, pivot, pivot_share, all_periods, total_lock, period_count)

    elif args.format == "csv":
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_count = out_dir / f"{series}_{period}_lock_count.csv"
        csv_share = out_dir / f"{series}_{period}_share.csv"
        pivot.to_csv(csv_count)
        pivot_share.to_csv(csv_share)
        contract["artifacts"] = {
            "csv_lock_count": str(csv_count),
            "csv_share": str(csv_share),
        }
        print(contract_to_terminal(contract))

    elif args.format == "json":
        if args.output:
            out_dir.mkdir(parents=True, exist_ok=True)
            save_contract_json(contract, out_dir / f"{series}_{period}_model_share.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))


def _generate_report(series, period, launch_date, pivot, pivot_share, all_periods, total_lock, period_count):
    ASSETS_DIR = _WS_ROOT / "assets" / "brand"
    REPORT_DIR = _WS_ROOT / "outputs" / "reports"
    raccoon_rel = Path("../../assets/brand/raccoon_avatar_light.png")
    sig_rel = Path("../../assets/brand/zihao_signature_transparent.png")
    period_unit = "周" if period == "week" else "个月"
    period_title = "周度" if period == "week" else "月度"

    chart_colors = [ZH['c1'], ZH['c2'], ZH['c3'], ZH['c4'], ZH['c5'], ZH['c6'], ZH['c7'], ZH['c8']]
    colors = [chart_colors[i % len(chart_colors)] for i in range(len(pivot.columns))]
    fig_cnt = go.Figure()
    for i, col in enumerate(pivot.columns):
        fig_cnt.add_trace(go.Bar(
            name=col, x=all_periods, y=pivot[col].values,
            marker_color=colors[i],
            text=pivot[col].values, textposition="inside",
            textfont=dict(color="#fff", size=11),
            hovertemplate="%{x}<br>%{y} 单<extra></extra>",
        ))
    fig_cnt.update_layout(
        barmode="stack",
        title=dict(text=f"{series} {period_title}分车型锁单量", x=0.5, font=dict(size=16, color="#174A7C")),
        xaxis=dict(title="", tickfont=dict(size=12)),
        yaxis=dict(title="锁单数", tickfont=dict(size=11)),
        legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center", font=dict(size=11)),
        margin=dict(l=40, r=40, t=50, b=80), hovermode="x unified",
        plot_bgcolor="#FFF", paper_bgcolor="#FFF",
    )
    apply_zh_theme(fig_cnt)

    fig_share = go.Figure()
    for i, col in enumerate(pivot_share.columns):
        fig_share.add_trace(go.Bar(
            name=col, x=all_periods, y=pivot_share[col].values * 100,
            marker_color=colors[i],
            text=[f"{v*100:.1f}%" for v in pivot_share[col].values],
            textposition="inside", textfont=dict(color="#fff", size=11),
            hovertemplate="%{x}<br>%{y:.1f}%<extra></extra>",
        ))
    fig_share.update_layout(
        barmode="stack",
        title=dict(text=f"{series} {period_title}分车型锁单占比", x=0.5, font=dict(size=16, color="#174A7C")),
        xaxis=dict(title="", tickfont=dict(size=12)),
        yaxis=dict(title="占比 (%)", tickfont=dict(size=11), ticksuffix="%"),
        legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center", font=dict(size=11)),
        margin=dict(l=40, r=40, t=50, b=80), hovermode="x unified",
        plot_bgcolor="#FFF", paper_bgcolor="#FFF",
    )
    apply_zh_theme(fig_share)

    models = " / ".join(pivot.columns.tolist())
    label_width = 14 if period == "week" else 10

    rows_html = ""
    for label in all_periods:
        cnt_row = pivot.loc[label]
        shr_row = pivot_share.loc[label]
        cells = f"<td style='font-weight:600;color:#174A7C;'>{label}</td>"
        total = int(cnt_row.sum())
        cells += f"<td class='num'>{total}</td>"
        for col in pivot.columns:
            v = int(cnt_row[col])
            p = shr_row[col] * 100
            if v > 0:
                cells += f"<td class='num'>{v}</td><td class='num' style='color:#6B7280;'>{p:.1f}%</td>"
            else:
                cells += "<td class='num' style='color:#D0D5DD;'>-</td><td class='num' style='color:#D0D5DD;'>-</td>"
        rows_html += f"<tr>{cells}</tr>"

    model_headers = ""
    for col in pivot.columns:
        model_headers += f"<th colspan='2'>{col}</th>"

    obs_list = []
    for i, label in enumerate(all_periods):
        row = pivot_share.loc[label]
        top = row.idxmax()
        top_share = row.max() * 100
        obs = f"{label}：主力车型 <strong>{top}</strong> 占比 {top_share:.1f}%"
        if i > 0:
            prev = pivot_share.loc[all_periods[i - 1]]
            changes = []
            for col in pivot.columns:
                delta = (row[col] - prev[col]) * 100
                if abs(delta) > 2:
                    direction = "上升" if delta > 0 else "下降"
                    changes.append(f"{col} {direction} {abs(delta):.1f}pp")
            if changes:
                obs += "；" + "，".join(changes)
        obs_list.append(f"<li>{obs}</li>")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{series} {period_title}分车型锁单报告</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #FAFBFC; color: #1F2D3D; margin: 0; }}
.header {{ background: #FFF; border-bottom: 3px solid #174A7C; padding: 16px 32px; display: flex; align-items: center; gap: 12px; }}
.header img {{ height: 36px; }}
.header .brand {{ font-size: 18px; font-weight: 700; color: #06213D; }}
.header .meta {{ margin-left: auto; font-size: 13px; color: #6B7280; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
.hero {{ background: linear-gradient(135deg, #06213D 0%, #174A7C 100%); color: #FFF; border-radius: 12px; padding: 32px; margin-bottom: 24px; }}
.hero h1 {{ font-size: 26px; margin: 0 0 8px; }}
.hero p {{ font-size: 15px; opacity: 0.85; margin: 0; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }}
.summary-card {{ background: #FFF; border-radius: 10px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
.summary-card .value {{ font-size: 28px; font-weight: 700; color: #174A7C; }}
.summary-card .label {{ font-size: 13px; color: #6B7280; margin-top: 4px; }}
.summary-card .hint {{ font-size: 12px; color: #9AA3AD; margin-top: 2px; }}
.chart-box {{ background: #FFF; border-radius: 10px; padding: 20px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
.chart-box h2 {{ font-size: 16px; color: #06213D; margin: 0 0 4px; }}
.chart-box .note {{ font-size: 12px; color: #9AA3AD; margin-bottom: 12px; }}
.section-card {{ background: #FFF; border-radius: 10px; padding: 24px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
.section-card h2 {{ font-size: 16px; color: #06213D; margin: 0 0 16px; padding-left: 12px; border-left: 3px solid #174A7C; }}
.report-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.report-table th {{ background: #F6F8FA; color: #06213D; padding: 10px 8px; text-align: center; border-bottom: 2px solid #174A7C; font-weight: 600; }}
.report-table td {{ padding: 10px 8px; text-align: center; border-bottom: 1px solid #EEF2F6; }}
.report-table td.num {{ font-variant-numeric: tabular-nums; }}
.report-table tbody tr:hover {{ background: #F3F6F8; }}
.scope-table td:first-child {{ width: 100px; color: #6B7280; }}
.footer {{ text-align: center; padding: 32px; color: #9AA3AD; font-size: 13px; }}
.footer img {{ height: 20px; opacity: 0.5; margin-bottom: 8px; }}
.footer .tagline {{ font-size: 12px; color: #C7CDD4; margin-top: 4px; }}
</style>
</head>
<body>

<div class="header">
  <img src="{raccoon_rel}" alt="Raccoon">
  <span class="brand">mashang · 锁单分析</span>
  <span class="meta">{datetime.now().strftime("%Y-%m-%d")}</span>
</div>

<div class="container">

<div class="hero">
  <h1>{series} {period_title}分车型锁单报告</h1>
  <p>上市 ({launch_date}) 以来共 {period_count} {period_unit}，累计锁单 {total_lock} 单</p>
</div>

<div class="summary-grid">
  <div class="summary-card">
    <div class="value">{total_lock}</div>
    <div class="label">累计锁单</div>
    <div class="hint">自 {launch_date}</div>
  </div>
  <div class="summary-card">
    <div class="value">{period_count}</div>
    <div class="label">数据{period_unit}</div>
    <div class="hint">{all_periods[0]} ~ {all_periods[-1]}</div>
  </div>
  <div class="summary-card">
    <div class="value">{len(pivot.columns)}</div>
    <div class="label">在售车型</div>
    <div class="hint">{models}</div>
  </div>
  <div class="summary-card">
    <div class="value">{int(pivot.iloc[-1].sum())}</div>
    <div class="label">最近{period_unit}锁单</div>
    <div class="hint">{all_periods[-1]}</div>
  </div>
</div>

<div class="chart-box">
  <div id="chart-count"></div>
</div>

<div class="chart-box">
  <div id="chart-share"></div>
</div>

<div class="section-card">
  <h2>{period_title}明细</h2>
  <table class="report-table">
  <thead><tr><th>月份</th><th>总锁单</th>{model_headers}</tr>
  <tr><th colspan='2'></th>{"<th>锁单</th><th>占比</th>" * len(pivot.columns)}</tr></thead>
  <tbody>{rows_html}</tbody>
  </table>
</div>

<div class="section-card">
  <h2>结构变化观察</h2>
  <ul style="padding-left: 20px; line-height: 1.8; font-size: 14px; color: #374151;">
    {''.join(obs_list)}
  </ul>
</div>

<div class="section-card">
  <h2>数据口径</h2>
  <table class="report-table scope-table">
    <tbody>
      <tr><td>数据源</td><td>{ORDER_PARQUET}</td></tr>
      <tr><td>时间窗口</td><td>{launch_date} ~ {datetime.now().strftime("%Y-%m-%d")}</td></tr>
      <tr><td>筛选条件</td><td>series = {series}</td></tr>
      <tr><td>指标口径</td><td>锁单数 = COUNTD(order_number WHERE lock_time IS NOT NULL)，按{period}聚合</td></tr>
    </tbody>
  </table>
</div>

</div>

<div class="footer">
  <img src="{sig_rel}" alt="zihao"><br>
  用数据、AI 和一点点常识，研究复杂世界。
</div>

<script>
var cntData = {fig_cnt.to_json()};
Plotly.newPlot('chart-count', cntData.data, cntData.layout, {{responsive: true}});
var shrData = {fig_share.to_json()};
Plotly.newPlot('chart-share', shrData.data, shrData.layout, {{responsive: true}});
</script>

</body>
</html>"""

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORT_DIR / f"{series}_{period}_model_report_{datetime.now().strftime('%Y%m%d')}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"  HTML: {out_path.resolve()}")


if __name__ == "__main__":
    main()
