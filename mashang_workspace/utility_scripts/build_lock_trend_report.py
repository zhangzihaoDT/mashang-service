#!/usr/bin/env python
"""
锁单趋势报告 — 30 日滚动均线 + 1σ 上下轨

用法:
    python mashang_workspace/utility_scripts/build_lock_trend_report.py
    python mashang_workspace/utility_scripts/build_lock_trend_report.py --output outputs/reports/lock_trend.html
"""

import sys, argparse
from pathlib import Path

import pandas as pd
import numpy as np
import plotly.graph_objects as go

REPO_ROOT = Path(__file__).resolve().parents[2]
WS_ROOT = REPO_ROOT / "mashang_workspace"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(WS_ROOT))

from utils.plotly_theme import ZH, apply_zh_theme, get_series_color

CSS = (WS_ROOT / "templates/report_style.css").read_text(encoding="utf-8")


def parse_args():
    p = argparse.ArgumentParser(description="锁单趋势报告")
    p.add_argument("--output", type=str, default=str(WS_ROOT / "outputs/reports/lock_trend_report.html"))
    return p.parse_args()


def make_fig_main(title, dates, daily, ma7, ma30, upper, lower, outside_mask, y_max):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=daily,
        name="日锁单数", mode="markers",
        marker=dict(
            color=["#D95F59" if o else get_series_color("ash") for o in outside_mask],
            size=[5 if o else 3.5 for o in outside_mask],
            opacity=[1.0 if o else 0.5 for o in outside_mask],
        ),
        hovertemplate="%{x|%m-%d}<br>%{y} 台<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=ma7,
        name="MA7 (7日)", mode="lines",
        line=dict(color=get_series_color("own"), width=2.5),
        hovertemplate="%{x|%m-%d}<br>MA7: %{y:.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=ma30,
        name="MA30 (30日)", mode="lines",
        line=dict(color=get_series_color("event"), width=2),
        hovertemplate="%{x|%m-%d}<br>MA30: %{y:.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=upper,
        name="±1σ 波动带", mode="lines",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=lower,
        name="±1σ 波动带", mode="lines",
        line=dict(width=0),
        fill="tonexty",
        fillcolor="rgba(192,111,69,0.12)",
        hovertemplate="%{x|%m-%d}<br>±1σ: %{y:.0f} ~ %{customdata:.0f}<extra></extra>",
        customdata=[u for u in upper],
    ))

    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center", font=dict(size=16, color=ZH["own"]), y=0.96),
        legend=dict(orientation="h", y=1.0, x=0.5, xanchor="center", font=dict(size=12), yanchor="bottom"),
        hovermode="x unified",
        margin=dict(l=40, r=24, t=60, b=40),
        height=400,
    )
    apply_zh_theme(fig)
    fig.update_yaxes(title_text="锁单数 (台)", tickfont=dict(size=11), range=[0, y_max])
    return fig.to_html(
        full_html=False, include_plotlyjs="cdn",
        config={"displayModeBar": False, "responsive": True},
    )


def make_fig_mid(title, dates, ma30, ma90, ma90_upper, y_max):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=ma30,
        name="MA30 (30日)", mode="lines",
        line=dict(color=get_series_color("own"), width=2.5),
        hovertemplate="%{x|%m-%d}<br>MA30: %{y:.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=ma90,
        name="MA90 (90日)", mode="lines",
        line=dict(color=get_series_color("event"), width=2),
        hovertemplate="%{x|%m-%d}<br>MA90: %{y:.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=ma90_upper,
        name="MA90+1σ (趋势强势线)", mode="lines",
        line=dict(color=get_series_color("clay"), width=1.5, dash="dash"),
        hovertemplate="%{x|%m-%d}<br>+1σ: %{y:.0f}<extra></extra>",
    ))

    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center", font=dict(size=16, color=ZH["own"]), y=0.96),
        legend=dict(orientation="h", y=1.0, x=0.5, xanchor="center", font=dict(size=12), yanchor="bottom"),
        hovermode="x unified",
        margin=dict(l=40, r=24, t=60, b=40),
        height=400,
    )
    apply_zh_theme(fig)
    fig.update_yaxes(title_text="锁单数 (台)", tickfont=dict(size=11), range=[0, y_max])
    return fig.to_html(
        full_html=False, include_plotlyjs="cdn",
        config={"displayModeBar": False, "responsive": True},
    )


def make_fig_yoy(title, dates, ma7_yoy, cum30_yoy, hist_pct, y_lo, y_hi):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=ma7_yoy,
        name="MA7 同比 %", mode="lines",
        line=dict(color=get_series_color("own"), width=2),
        hovertemplate="%{x|%m-%d}<br>MA7同比: %{y:.1f}%<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=cum30_yoy,
        name="30日累计同比 %", mode="lines",
        line=dict(color=get_series_color("event"), width=2),
        hovertemplate="%{x|%m-%d}<br>30日累计同比: %{y:.1f}%<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=hist_pct,
        name="历史同日±7天分位", mode="lines",
        line=dict(color=get_series_color("steel"), width=1.5),
        hovertemplate="%{x|%m-%d}<br>历史分位: %{y:.0f}%<extra></extra>",
    ))

    fig.add_hline(y=0, line=dict(color=get_series_color("neutral"), width=1, dash="dot"))

    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center", font=dict(size=16, color=ZH["own"]), y=0.96),
        legend=dict(orientation="h", y=1.0, x=0.5, xanchor="center", font=dict(size=12), yanchor="bottom"),
        hovermode="x unified",
        margin=dict(l=40, r=24, t=60, b=40),
        height=400,
    )
    apply_zh_theme(fig)
    fig.update_yaxes(title_text="%", tickfont=dict(size=11), range=[y_lo, y_hi],
                     ticksuffix="%")
    return fig.to_html(
        full_html=False, include_plotlyjs="cdn",
        config={"displayModeBar": False, "responsive": True},
    )


def compute_yoy_metrics(daily):
    """Compute YoY and historical percentile series from daily lock counts."""
    df = daily.to_frame("lock_count")
    df["year"] = df.index.year
    df["month"] = df.index.month
    df["day"] = df.index.day

    # same-day last year lookup
    df["key_ly"] = df["month"].astype(str) + "-" + df["day"].astype(str)
    ref = df[df["year"] == 2025][["key_ly", "lock_count"]].copy()
    ref.columns = ["key_ly", "lock_count_ly"]

    # merge last year values, preserve original index
    df_all = df.copy()
    idx_before = df_all.index
    df_all = df_all.merge(ref, on="key_ly", how="left")
    df_all.index = idx_before
    # only keep last-year ref for 2026 (no data before 2025)
    df_all.loc[df_all["year"] != 2026, "lock_count_ly"] = np.nan

    # MA7 YoY (full index)
    ma7 = df_all["lock_count"].rolling(7, min_periods=1).mean()
    ma7_ly = df_all["lock_count_ly"].rolling(7, min_periods=1).mean()
    ma7_yoy = (ma7 - ma7_ly) / ma7_ly * 100

    # 30-day cumulative YoY (full index)
    cum30 = df_all["lock_count"].rolling(30, min_periods=1).sum()
    cum30_ly = df_all["lock_count_ly"].rolling(30, min_periods=1).sum()
    cum30_yoy = (cum30 - cum30_ly) / cum30_ly * 100

    # historical percentile: same calendar day ± 7 day window across years
    df_all["doy"] = df_all.index.dayofyear  # day of year (1-366)
    # handle leap year: clamp doy to 365 for comparisons
    max_doy = 365
    hist_pct = pd.Series(np.nan, index=df_all.index)
    for d in df_all.index:
        v = df_all.loc[d, "lock_count"]
        if pd.isna(v):
            continue
        doy = min(d.dayofyear, max_doy)
        lo, hi = doy - 7, doy + 7
        pool_years = [y for y in [2023, 2024, 2025] if y != d.year]
        pool_vals = []
        for y in pool_years:
            y_start = pd.Timestamp(year=y, month=1, day=1)
            y_end = pd.Timestamp(year=y, month=12, day=31)
            lo_dt = y_start + pd.Timedelta(days=lo - 1)
            hi_dt = y_start + pd.Timedelta(days=hi - 1)
            mask = (df_all.index >= lo_dt) & (df_all.index <= hi_dt)
            pool_vals.extend(df_all.loc[mask, "lock_count"].dropna().values)
        if len(pool_vals) == 0:
            continue
        pool_arr = np.array(pool_vals)
        less = (pool_arr < v).sum()
        equal = (pool_arr == v).sum()
        pct = ((less + 0.5 * equal) / len(pool_arr)) * 100
        hist_pct.loc[d] = pct

    return ma7_yoy, cum30_yoy, hist_pct


def build_charts(result_df, daily, ma7_yoy, cum30_yoy, hist_pct):
    dates = result_df["lock_time"]

    # slice YoY series to display range (align with dates)
    t_min, t_max = dates.min(), dates.max()
    ma7_yoy = ma7_yoy.reindex(daily.index).loc[t_min:t_max]
    cum30_yoy = cum30_yoy.reindex(daily.index).loc[t_min:t_max]
    hist_pct = hist_pct.reindex(daily.index).loc[t_min:t_max]

    # clip extreme YoY values for readable axis
    valid_yoy = pd.concat([ma7_yoy, cum30_yoy]).replace([np.inf, -np.inf], np.nan).dropna()
    y_lo = max(valid_yoy.quantile(0.01), -100) if len(valid_yoy) > 0 else -50
    y_hi = min(valid_yoy.quantile(0.99), 200) if len(valid_yoy) > 0 else 100
    if y_lo > -5:
        y_lo = -10

    y_max_1 = result_df["upper_1σ"].max() * 1.08
    if np.isnan(y_max_1):
        y_max_1 = result_df["lock_count"].max() * 1.08

    y_max_2 = max(result_df["MA90"].max(), result_df["MA90_upper"].max()) * 1.08

    fig1 = make_fig_main("短期趋势主图 — MA7 / MA30 / ±1σ", dates,
                         result_df["lock_count"], result_df["MA7"],
                         result_df["MA30"], result_df["upper_1σ"], result_df["lower_1σ"],
                         (result_df["outside"] != "within").values,
                         y_max_1)

    fig2 = make_fig_mid("中期趋势确认 — MA30 / MA90 / MA90+1σ", dates,
                        result_df["MA30"], result_df["MA90"], result_df["MA90_upper"],
                        y_max_2)

    fig3 = make_fig_yoy("同比与历史同日±7天分位 — 判断季节性 vs 真实趋势", dates,
                        ma7_yoy, cum30_yoy, hist_pct, y_lo, y_hi)

    return fig1, fig2, fig3


def format_num(v):
    if np.isnan(v):
        return "-"
    return f"{int(v)}"


def main():
    args = parse_args()
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(str(REPO_ROOT / "dataset/order_data.parquet"))
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    df = df[df["lock_time"].notna()].copy()

    today = pd.Timestamp.now().normalize()
    yesterday = today - pd.Timedelta(days=1)
    display_start = yesterday - pd.Timedelta(days=364)  # 365 days inclusive
    end = today  # exclusive upper bound

    mask = (df["lock_time"] >= df["lock_time"].min()) & (df["lock_time"] < end)
    daily = df[mask].set_index("lock_time").resample("D")["order_number"].nunique()
    daily.name = "lock_count"

    window = 30
    ma = daily.rolling(window).mean()
    rs = daily.rolling(window).std()
    upper = ma + rs
    lower = ma - rs

    result_df = pd.DataFrame({
        "lock_count": daily,
        "MA30": ma,
        "upper_1σ": upper,
        "lower_1σ": lower,
    }).reset_index()

    ma7 = daily.rolling(7).mean()
    rs7 = daily.rolling(7).std()
    result_df["MA7"] = ma7.values
    result_df["MA7_upper"] = (ma7 + rs7).values
    result_df["MA7_lower"] = (ma7 - rs7).values

    ma90 = daily.rolling(90).mean()
    rs90 = daily.rolling(90).std()
    result_df["MA90"] = ma90.values
    result_df["MA90_upper"] = (ma90 + rs90).values
    result_df["MA90_lower"] = (ma90 - rs90).values

    result_df["outside"] = "within"
    result_df.loc[result_df["lock_count"] > result_df["upper_1σ"], "outside"] = "above"
    result_df.loc[result_df["lock_count"] < result_df["lower_1σ"], "outside"] = "below"

    # slice to display range (last ~1 year)
    result_df = result_df[result_df["lock_time"] >= display_start].copy()
    daily_display = daily[daily.index >= display_start]

    # compute YoY from full data for proper comparison
    ma7_yoy, cum30_yoy, hist_pct = compute_yoy_metrics(daily)

    fig1_html, fig2_html, fig3_html = build_charts(result_df, daily_display, ma7_yoy, cum30_yoy, hist_pct)

    total_days = len(result_df)

    recent = result_df.tail(30)
    up_count = len(recent[recent["outside"] == "above"])
    dn_count = len(recent[recent["outside"] == "below"])

    latest = result_df.iloc[-1]
    latest_lock = int(latest["lock_count"])
    latest_ma30 = latest["MA30"]
    latest_ma7 = latest["MA7"]
    latest_ma90 = latest["MA90"]

    latest_yoy = ma7_yoy.reindex(daily_display.index).iloc[-1] if not ma7_yoy.empty else None
    latest_hist = hist_pct.reindex(daily_display.index).iloc[-1] if not hist_pct.empty else None

    # ── Signal computation ──
    signal_short = ("🟢 短期转强", "MA7 上穿 MA30") if latest_ma7 > latest_ma30 else ("🔴 短期偏弱", "MA7 持续低于 MA30")
    if not pd.isna(latest["upper_1σ"]):
        if latest_lock > latest["upper_1σ"]:
            signal_break = ("🔴 放量突破", f"当前 {latest_lock} > MA30+1σ ({latest['upper_1σ']:.0f})")
        else:
            signal_break = ("🟢 正常", f"当前在 MA30+1σ 以内")
    else:
        signal_break = ("⚪ 数据不足", "")
    signal_mid = ("🟢 中枢上移", "MA30 上穿 MA90") if latest_ma30 > latest_ma90 else ("🔴 中枢下移", "MA30 低于 MA90")
    if latest_yoy is not None:
        signal_yoy = ("🟢 好于去年", f"MA7 同比 {latest_yoy:+.1f}%") if latest_yoy > 0 else ("🔴 弱于去年", f"MA7 同比 {latest_yoy:+.1f}%")
    else:
        signal_yoy = ("⚪ 无数据", "")
    if latest_hist is not None:
        signal_season = ("🟢 历史同日偏强", f"分位 {latest_hist:.0f}%") if latest_hist >= 50 else ("🔴 历史同日偏弱", f"分位 {latest_hist:.0f}%")
    else:
        signal_season = ("⚪ 无数据", "")

    # overall judgment
    positives = sum([
        latest_ma7 > latest_ma30,
        latest_lock > latest["upper_1σ"] if not pd.isna(latest.get("upper_1σ", np.nan)) else False,
        latest_ma30 > latest_ma90,
        latest_yoy > 0 if latest_yoy is not None else False,
        latest_hist >= 50 if latest_hist is not None else False,
    ])
    if positives >= 4:
        signal_overall = ("🟢 全面强势", "多个维度共振，趋势确认")
    elif positives >= 2:
        if latest_ma7 <= latest_ma30 and latest_ma30 <= latest_ma90:
            signal_overall = ("🔴 全面偏弱", "短/中/同比均偏弱，建议关注")
        elif latest_ma7 > latest_ma30 and latest_ma30 <= latest_ma90:
            signal_overall = ("🟡 短期修复，中期待确认", "MA7 改善但未传导至 MA30/MA90")
        elif latest_ma7 <= latest_ma30 and latest_ma30 > latest_ma90:
            signal_overall = ("🟡 中期偏强，短期走弱", "MA90 以上但 MA7 回落")
        else:
            signal_overall = ("🟡 分化", "多信号不一致，需综合判断")
    else:
        signal_overall = ("🔴 全面偏弱", "多数指标处于弱势区间")

    signals = [
        ("短期动量", signal_short[0], signal_short[1]),
        ("短期异常", signal_break[0], signal_break[1]),
        ("中期趋势", signal_mid[0], signal_mid[1]),
        ("同比表现", signal_yoy[0], signal_yoy[1]),
        ("季节位置", signal_season[0], signal_season[1]),
    ]

    def card_class(s):
        if "🟢" in s: return "positive"
        if "🔴" in s: return "negative"
        return "neutral"

    signal_cards = "".join(
        f'<div class="summary-card {card_class(s)}"><div class="summary-value">{s}</div><div class="summary-label">{l}</div><div class="summary-hint">{d}</div></div>'
        for l, s, d in signals
    )
    overall_class = card_class(signal_overall[0])
    signal_cards += (
        f'<div class="summary-card {overall_class}" style="grid-column:span 2"><div class="summary-value">{signal_overall[0]}</div><div class="summary-label">综合判断</div><div class="summary-hint">{signal_overall[1]}</div></div>'
    )



    table_rows = ""
    for _, r in result_df.tail(30).iterrows():
        cls = ""
        delta_cls = "delta-neutral"
        delta = ""
        if r["outside"] == "above":
            cls = ' class="row-highlight"'
            delta_cls = "delta-positive"
            delta = f"+{int(r['lock_count'] - r['MA30'])}"
        elif r["outside"] == "below":
            cls = ' class="row-highlight"'
            delta_cls = "delta-negative"
            delta = f"{int(r['lock_count'] - r['MA30'])}"
        table_rows += f"""<tr{cls}>
            <td>{r['lock_time'].strftime('%m-%d')}</td>
            <td class="num">{int(r['lock_count'])}</td>
            <td class="num">{format_num(r['MA30'])}</td>
            <td class="num">{format_num(r['upper_1σ'])}</td>
            <td class="num">{format_num(r['lower_1σ'])}</td>
            <td class="num {delta_cls}">{delta}</td>
        </tr>"""

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>锁单趋势报告 — MA30 ± 1σ</title>
  <style>{CSS}</style>
</head>
<body>
  <header>
    <div class="container">
      <div class="brand">
        <img class="brand-avatar" src="../../assets/brand/raccoon_avatar_light.png" alt="" />
        <span class="brand-name">Raccoon Research</span>
      </div>
      <span class="header-meta">报告生成: {today.strftime('%Y-%m-%d')} | 数据源: order_data.parquet</span>
    </div>
  </header>

  <main class="container">
    <section class="hero">
      <h1>锁单趋势 — 短期 / 中期 / 同比三维分析</h1>
      <p>{display_start.strftime('%Y-%m-%d')} ~ {yesterday.strftime('%Y-%m-%d')}  |  {total_days} 个自然日</p>
    </section>

    <section class="summary-grid">
      {signal_cards}
    </section>

    <section class="report-section">
      <h2 class="section-title">趋势图表</h2>
      <p class="section-note">上图(短期): 灰点=日锁单(红点=突破±1σ) ｜ 蓝=MA7 ｜ 金=MA30 ｜ 橙色面积=±1σ波动带<br>中图(中期): 蓝=MA30 ｜ 金=MA90 ｜ 红虚线=MA90+1σ趋势强势线<br>下图(同比&历史分位): 蓝=MA7同比% ｜ 金=30日累计同比% ｜ 灰=历史同日±7天窗口分位(mid-rank)</p>
      <div class="chart-box">
        <div class="chart-wrap">{fig1_html}</div>
      </div>
      <div class="chart-box">
        <div class="chart-wrap">{fig2_html}</div>
      </div>
      <div class="chart-box">
        <div class="chart-wrap">{fig3_html}</div>
      </div>
    </section>

    <section class="report-section">
      <h2 class="section-title">近 30 日波动明细</h2>
      <p class="section-note">超出 ±1σ 波动带的日期标注高亮</p>
      <div class="table-wrap">
        <table class="report-table">
          <thead><tr>
            <th>日期</th><th>锁单数</th><th>MA30</th><th>+1σ</th><th>-1σ</th><th>偏离</th>
          </tr></thead>
          <tbody>{table_rows}</tbody>
        </table>
      </div>
    </section>

    <section class="method-section">
      <h2 class="section-title">计算方法</h2>
      <div class="method-grid">
        <div class="method-item">
          <div class="method-icon" style="background:var(--zh-blue-100);color:var(--zh-blue);">M</div>
          <div class="method-body">
            <strong>MA30</strong> — 每日锁单数的 30 日滚动均值，反映中期趋势。
          </div>
        </div>
        <div class="method-item">
          <div class="method-icon" style="background:var(--zh-gold-100);color:var(--zh-gold-700);">σ</div>
          <div class="method-body">
            <strong>±1σ 波动带</strong> — 基于 30 日滚动标准差，MA30 ± 1σ。超出此带视为统计异常。
          </div>
        </div>
      </div>
      <div class="method-footnote">
        {df['lock_time'].min().strftime('%Y-%m-%d')} ~ {yesterday.strftime('%Y-%m-%d')} ｜ 近30日: 上穿 {up_count} 次 / 下穿 {dn_count} 次
      </div>
    </section>
  </main>

  <footer>
    <img class="brand-sig" src="../../assets/brand/zihao_signature_transparent.png" alt="Raccoon Research" />
    <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
  </footer>
</body>
</html>"""

    out_path.write_text(html, encoding="utf-8")
    print(f"✅ 报告已生成: {out_path}")


if __name__ == "__main__":
    main()
