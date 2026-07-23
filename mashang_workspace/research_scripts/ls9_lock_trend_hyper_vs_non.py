"""
name: ls9_lock_trend_hyper_vs_non
use: python research_scripts/ls9_lock_trend_hyper_vs_non.py [--end-date YYYY-MM-DD] [--days N] [--from YYYY-MM-DD]
summary: LS9 锁单变化评估 — 3 张图（Hyper/电池/版本），输出 HTML 报告
"""

import argparse
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _ROOT.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
_WORKSPACE = str(_ROOT)
if _WORKSPACE not in sys.path:
    sys.path.insert(0, _WORKSPACE)

from utils.plotly_theme import ZH, apply_zh_theme


def _resolve_dates(args):
    if args.end_date:
        end = pd.Timestamp(args.end_date).normalize()
    else:
        end = (pd.Timestamp.now() - timedelta(days=1)).normalize()

    if args.start_date:
        start = pd.Timestamp(args.start_date).normalize()
    else:
        start = end - timedelta(days=args.days)

    return start, end


def _load_data(start, end):
    df = pd.read_parquet(_PROJECT_ROOT / "dataset" / "order_data.parquet")
    df = df[df["lock_time"].notna()].copy()
    df = df[df["order_type"] == "用户车"].copy()
    df["lock_date"] = pd.to_datetime(df["lock_time"]).dt.normalize()

    ls9 = df[(df["series"] == "LS9") & (df["lock_date"] >= start) & (df["lock_date"] <= end)].copy()
    ls9h = df[df["series"] == "LS9Hyper"].copy()
    ls9h["lock_date"] = pd.to_datetime(ls9h["lock_time"]).dt.normalize()
    ls9h = ls9h[(ls9h["lock_date"] >= start) & (ls9h["lock_date"] <= end)].copy()

    return ls9, ls9h


LS9HYPER_LAUNCH = pd.Timestamp("2026-07-16")

def _classify(row):
    name = str(row.get("product_name", ""))
    series = str(row.get("series", ""))
    lock_date = row.get("lock_date")
    has_hyper = "Hyper" in name or series == "LS9Hyper"
    is_hyper = has_hyper and lock_date is not None and lock_date >= LS9HYPER_LAUNCH
    is_52 = "52" in name
    is_66 = "66" in name or ("Hyper" in name) or series == "LS9Hyper"
    battery = "52度" if is_52 else ("66度" if is_66 else "其他")

    is_线控 = "线控" in name
    if is_hyper:
        variant = "Hyper"
    elif is_线控:
        variant = "52 Ultra 线控版"
    elif "52 Ultra" in name:
        variant = "52 Ultra"
    elif "66 Ultra" in name:
        variant = "66 Ultra"
    else:
        variant = "其他"

    return is_hyper, battery, variant


def _auto_tickvals(full, days):
    if days <= 60:
        return full["lock_date"], "%m-%d", -45
    step = 7
    mask = [i % step == 0 for i in range(len(full))]
    return full["lock_date"][mask], "%m-%d", -45


def _build_daily(ls9, ls9h):
    rows = []
    for _, r in pd.concat([ls9, ls9h]).iterrows():
        is_hyper, battery, variant = _classify(r)
        rows.append({"lock_date": r["lock_date"], "is_hyper": is_hyper, "battery": battery, "variant": variant, "order_number": r["order_number"]})
    daily = pd.DataFrame(rows).groupby(["lock_date", "is_hyper", "battery", "variant"])["order_number"].nunique().reset_index()
    daily.columns = ["lock_date", "is_hyper", "battery", "variant", "lock_count"]
    return daily.sort_values("lock_date")


def _fill_series(daily, start, end):
    full = pd.DataFrame(pd.date_range(start=start, end=end, freq="D"), columns=["lock_date"])
    all_dates = full.set_index("lock_date")

    def get_raw(cat_field, cat_val):
        sub = daily[daily[cat_field] == cat_val].groupby("lock_date")["lock_count"].sum()
        return all_dates.join(sub).squeeze()  # NaN where no data

    def get_filled(cat_field, cat_val):
        return get_raw(cat_field, cat_val).fillna(0)

    total = all_dates.join(
        daily.groupby("lock_date")["lock_count"].sum()
    ).fillna(0).squeeze()

    return full, total, get_raw, get_filled


def _make_ma(series):
    return series.rolling(7, min_periods=1).mean()


def _add_endpoint_markers(fig, full, markers):
    """
    markers: list of dicts with keys: ma_series (pd.Series), cum_total (int),
             color (str), label (str)
    Places diamond markers at the last non-null point of each MA series,
    with text positions arranged to avoid overlap.
    """
    points = []
    for m in markers:
        vals = m["ma_series"].values
        # Find last non-NaN value position in the numpy array
        non_nan_mask = ~pd.isna(vals)
        if not non_nan_mask.any():
            continue
        last_idx = len(vals) - 1 - non_nan_mask[::-1].argmax()
        last_val = vals[last_idx]
        last_date = full["lock_date"].iloc[last_idx]
        points.append({"date": last_date, "val": last_val, "total": m["cum_total"],
                       "color": m["color"], "label": m["label"]})

    if not points:
        return

    points.sort(key=lambda p: p["val"], reverse=True)
    positions = ["top center", "bottom center", "top left", "bottom left",
                 "top center", "bottom center", "top left", "bottom left"]
    x_offsets = [0, 0, -0.5, -0.5, 0, 0, 0.5, 0.5]

    for i, p in enumerate(points):
        pos = positions[i % len(positions)]
        offset_days = x_offsets[i % len(x_offsets)]
        x_val = p["date"] + pd.Timedelta(days=offset_days) if offset_days != 0 else p["date"]

        fig.add_trace(go.Scatter(
            x=[x_val], y=[p["val"]],
            mode="markers+text",
            marker=dict(color=p["color"], size=8, symbol="diamond",
                        line=dict(color="white", width=1)),
            text=[f"<b>{p['total']:,}</b>"],
            textposition=pos,
            textfont=dict(size=11, color=p["color"]),
            name=f"{p['label']} 累计",
            showlegend=False,
            hoverinfo="skip",
        ))


def _build_chart(full, traces, title, y_title, tickvals=None, tickformat="%m-%d", tickangle=-45):
    fig = go.Figure()
    for t in traces:
        y_vals = t["y"].values if hasattr(t["y"], "values") else t["y"]
        fig.add_trace(go.Scatter(
            x=full["lock_date"], y=y_vals, mode=t.get("mode", "lines"),
            name=t["name"],
            marker=t.get("marker"),
            line=t.get("line"),
            hovertemplate=t["hover"],
        ))

    apply_zh_theme(fig)
    fig.update_layout(
        title=dict(text=title, font=dict(size=18, color=ZH["own"]), x=0.03, xanchor="left"),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
        margin=dict(t=80, b=40, l=60, r=30),
        yaxis=dict(title=y_title),
    )
    xaxis_kw = dict(tickformat=tickformat, tickangle=tickangle)
    if tickvals is not None:
        xaxis_kw["tickvals"] = tickvals
    fig.update_xaxes(**xaxis_kw)
    return fig


def main():
    p = argparse.ArgumentParser(description="LS9 锁单变化评估报告")
    p.add_argument("--end-date", default=None, help="截止日期（默认 T-1）")
    p.add_argument("--days", type=int, default=60, help="回溯天数（默认 60，与 --from 互斥）")
    p.add_argument("--from", "--start-date", dest="start_date", default=None, help="起始日期（覆盖 --days）")
    p.add_argument("--html-out", default=str(_ROOT / "outputs" / "reports" / "ls9_lock_trend_hyper_comparison.html"),
                   help="HTML 输出路径")
    args = p.parse_args()

    start, end = _resolve_dates(args)
    ls9, ls9h = _load_data(start, end)
    daily = _build_daily(ls9, ls9h)
    full, total_daily, get_raw, get_filled = _fill_series(daily, start, end)
    tickvals, fmt, angle = _auto_tickvals(full, (end - start).days)
    days_str = f"近{(end - start).days}日" if not args.start_date else f"{start.date()}~{end.date()}"

    non_hyper_raw = get_raw("is_hyper", False)
    hyper_raw = get_raw("is_hyper", True)
    bat_52_raw = get_raw("battery", "52度")
    bat_66_raw = get_raw("battery", "66度")

    non_hyper = get_filled("is_hyper", False)
    hyper = get_filled("is_hyper", True)
    bat_52 = get_filled("battery", "52度")
    bat_66 = get_filled("battery", "66度")

    variants = ["Hyper", "52 Ultra", "66 Ultra", "52 Ultra 线控版"]
    variant_colors = {
        "Hyper": ZH["event"],
        "52 Ultra": ZH["steel"],
        "66 Ultra": ZH["clay"],
        "52 Ultra 线控版": ZH["sage"],
    }
    var_raw = {v: get_raw("variant", v) for v in variants}
    var_data = {v: get_filled("variant", v) for v in variants}

    total_plot = total_daily.where(total_daily > 0)

    # ── Summary Stats ──
    total_all = int(total_daily.sum())
    total_non = int(non_hyper.sum())
    total_hyp = int(hyper.sum())
    total_52 = int(bat_52.sum())
    total_66 = int(bat_66.sum())
    hyper_days = int((hyper > 0).sum())
    var_totals = {v: int(var_data[v].sum()) for v in variants}

    # Pre-compute MA series once
    ma_non = _make_ma(non_hyper_raw)
    ma_hyper = _make_ma(hyper_raw)
    ma_52 = _make_ma(bat_52_raw)
    ma_66 = _make_ma(bat_66_raw)
    ma_var = {v: _make_ma(var_raw[v]) for v in variants}

    # ── Chart 1: Hyper vs 非Hyper ──
    fig1 = _build_chart(full, [
        dict(y=total_plot, mode="markers", name="LS9 日锁单总量",
             marker=dict(color=ZH["ash"], size=4, symbol="circle"),
             hover="%{x|%m-%d}<br>总量: %{y}单<extra></extra>"),
        dict(y=ma_non, name="非Hyper MA7",
             line=dict(color=ZH["own"], width=2),
             hover="%{x|%m-%d}<br>非Hyper MA7: %{y:.1f}单<extra></extra>"),
        dict(y=ma_hyper, name="Hyper MA7",
             line=dict(color=ZH["event"], width=2),
             hover="%{x|%m-%d}<br>Hyper MA7: %{y:.1f}单<extra></extra>"),
    ], title="LS9 锁单趋势 — Hyper vs 非Hyper",
       y_title="锁单数", tickvals=tickvals, tickformat=fmt, tickangle=angle)
    _add_endpoint_markers(fig1, full, [
        dict(ma_series=ma_non, cum_total=total_non, color=ZH["own"], label="非Hyper"),
        dict(ma_series=ma_hyper, cum_total=total_hyp, color=ZH["event"], label="Hyper"),
    ])

    # ── Chart 2: 52度 vs 66度 ──
    fig2 = _build_chart(full, [
        dict(y=total_plot, mode="markers", name="LS9 日锁单总量",
             marker=dict(color=ZH["ash"], size=4, symbol="circle"),
             hover="%{x|%m-%d}<br>总量: %{y}单<extra></extra>"),
        dict(y=ma_52, name="52度电池 MA7",
             line=dict(color=ZH["steel"], width=2),
             hover="%{x|%m-%d}<br>52度 MA7: %{y:.1f}单<extra></extra>"),
        dict(y=ma_66, name="66度电池 MA7",
             line=dict(color=ZH["clay"], width=2),
             hover="%{x|%m-%d}<br>66度 MA7: %{y:.1f}单<extra></extra>"),
    ], title="LS9 锁单趋势 — 52度 vs 66度电池",
       y_title="锁单数", tickvals=tickvals, tickformat=fmt, tickangle=angle)
    _add_endpoint_markers(fig2, full, [
        dict(ma_series=ma_52, cum_total=total_52, color=ZH["steel"], label="52度"),
        dict(ma_series=ma_66, cum_total=total_66, color=ZH["clay"], label="66度"),
    ])

    # ── Chart 3: Variant ──
    fig3 = _build_chart(full, [dict(y=total_plot, mode="markers", name="LS9 日锁单总量",
         marker=dict(color=ZH["ash"], size=4, symbol="circle"),
         hover="%{x|%m-%d}<br>总量: %{y}单<extra></extra>")] + [
        dict(y=ma_var[v], name=f"{v} MA7",
             line=dict(color=variant_colors[v], width=2),
             hover=f"%{{x|%m-%d}}<br>{v} MA7: %{{y:.1f}}单<extra></extra>")
        for v in variants
    ], title="LS9 锁单趋势 — 按车型版本",
       y_title="锁单数", tickvals=tickvals, tickformat=fmt, tickangle=angle)
    _add_endpoint_markers(fig3, full, [
        dict(ma_series=ma_var[v], cum_total=var_totals[v], color=variant_colors[v], label=v)
        for v in variants if var_totals[v] > 0
    ])

    chart1_html = fig1.to_html(full_html=False, include_plotlyjs="cdn")
    chart2_html = fig2.to_html(full_html=False, include_plotlyjs=False)
    chart3_html = fig3.to_html(full_html=False, include_plotlyjs=False)

    page_title = f"LS9Hyper 上市评估 — {days_str}锁单变化"
    html_path = Path(args.html_out)
    html_path.parent.mkdir(parents=True, exist_ok=True)

    var_card_rows = "".join(
        f'<div class="card"><div class="num">{var_totals[v]:,}</div><div class="label">{v}</div></div>\n'
        for v in variants
    )

    report_html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title}</title>
<link rel="stylesheet" href="../../templates/report_style.css">
<style>
body{{margin:24px;background:var(--zh-bg);color:var(--zh-text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;}}
h1{{margin:0 0 12px 0;font-size:20px;color:var(--zh-blue);border-left:4px solid var(--zh-blue);padding-left:12px;}}
h2{{margin:20px 0 8px 0;font-size:16px;color:var(--zh-deep-blue);}}
.meta{{margin:0 0 12px 0;padding:12px 14px;background:var(--zh-panel);border:1px solid var(--zh-border);border-radius:8px;}}
.meta ul{{margin:0;padding-left:18px;}}
.summary-cards{{display:flex;gap:12px;margin:12px 0;flex-wrap:wrap;}}
.card{{flex:1;min-width:130px;padding:14px 16px;background:var(--zh-card);border:1px solid var(--zh-border);border-radius:8px;text-align:center;}}
.card .num{{font-size:24px;font-weight:700;color:var(--zh-blue);}}
.card .label{{font-size:12px;color:var(--zh-muted);margin-top:4px;}}
.card.hyper .num{{color:var(--zh-raccoon-gold);}}
.card.bat52 .num{{color:#4F6F82;}}
.card.bat66 .num{{color:#C06F45;}}
</style>
</head>
<body>
<h1>{page_title}</h1>
<div class="meta">
<ul>
<li>时间窗口: {start.date()} ~ {end.date()}（{days_str}）</li>
<li>数据源: order_data.parquet（lock_time 非空）</li>
<li>过滤: order_type = "用户车"</li>
<li>口径: COUNTD(order_number)</li>
<li>Hyper 界定: product_name 含 "Hyper" 或 series = "LS9Hyper"，仅统计 {LS9HYPER_LAUNCH.date()} 后</li>
</ul>
</div>

<div class="summary-cards">
  <div class="card">
    <div class="num">{total_all:,}</div>
    <div class="label">LS9 累计锁单</div>
  </div>
  <div class="card">
    <div class="num">{total_non:,}</div>
    <div class="label">非Hyper</div>
  </div>
  <div class="card hyper">
    <div class="num">{total_hyp:,}</div>
    <div class="label">Hyper</div>
  </div>
{var_card_rows}</div>

<h2>图1: Hyper vs 非Hyper</h2>
{chart1_html}

<h2>图2: 52度 vs 66度电池</h2>
{chart2_html}

<h2>图3: 按车型版本</h2>
{chart3_html}
</body>
</html>"""

    html_path.write_text(report_html, encoding="utf-8")
    print(f"HTML: {html_path}")


if __name__ == "__main__":
    main()
