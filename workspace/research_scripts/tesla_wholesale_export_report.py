#!/usr/bin/env python
"""
Tesla 月度批发 / 国内零售 / 上海工厂出口 报告。

数据源:
    dataset/cpca/tesla_monthly_wholesale_retail_export.csv（手动整理，乘联会月报口径）

口径:
    批发     = Tesla 厂家月度批发量
    国内零售 = 国内终端零售量
    出口     = 上海工厂出口量
    出口占比 = 出口 / 批发（脚本按明细重算，不直接采用 CSV 列）

用法:
    python research_scripts/tesla_wholesale_export_report.py
    python research_scripts/tesla_wholesale_export_report.py --format json
    python research_scripts/tesla_wholesale_export_report.py --html
    python research_scripts/tesla_wholesale_export_report.py --html \\
        --source-url https://www.cada.cn/Trends/info_91_10566.html
"""

import re
import csv
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

import plotly.graph_objects as go

REPO_ROOT = Path(__file__).resolve().parents[2]
WS_ROOT = Path(__file__).resolve().parents[1]

if str(WS_ROOT) not in sys.path:
    sys.path.insert(0, str(WS_ROOT))

from utils.paths import DATASET_DIR, REPORTS_DIR  # noqa: E402
from utils.plotly_theme import apply_zh_theme, ZH  # noqa: E402
from utils.result_contract import build_success_contract  # noqa: E402

DEFAULT_CSV = DATASET_DIR / "cpca" / "tesla_monthly_wholesale_retail_export.csv"
DEFAULT_OUTPUT = REPORTS_DIR
REPORT_NAME = "tesla_wholesale_export_report"
ROLLING_WINDOW = 6
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _num(value) -> int:
    return int(str(value).replace(",", "").strip())


def load_monthly(csv_path: Path) -> list:
    """读取月度明细行（跳过 全年 / H1 汇总行）。"""
    rows = []
    with open(csv_path, encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            month = (raw.get("月份") or "").strip()
            if not MONTH_RE.match(month):
                continue
            wholesale = _num(raw["批发"])
            retail = _num(raw["国内零售"])
            export = _num(raw["出口"])
            rows.append({
                "month": month,
                "wholesale": wholesale,
                "retail": retail,
                "export": export,
                "share": (export / wholesale) if wholesale else 0.0,
            })
    rows.sort(key=lambda r: r["month"])
    return rows


def pct(cur, prev):
    if not prev:
        return None
    return round((cur - prev) / prev * 100, 1)


def rolling_share(rows: list, window: int = ROLLING_WINDOW) -> list:
    out = []
    for i in range(len(rows)):
        if i + 1 < window:
            out.append(None)
        else:
            chunk = rows[i - window + 1:i + 1]
            out.append(round(100 * sum(r["share"] for r in chunk) / window, 1))
    return out


def _prev_month(rows: list, idx: int):
    return rows[idx - 1] if idx > 0 else None


def _year_ago(rows: list, idx: int):
    target_year = int(rows[idx]["month"][:4]) - 1
    target = f"{target_year}-{rows[idx]['month'][5:]}"
    for r in rows:
        if r["month"] == target:
            return r
    return None


def analyze(rows: list, source_url: str | None = None) -> dict:
    latest = rows[-1]
    idx = len(rows) - 1
    prev = _prev_month(rows, idx)
    yoy_row = _year_ago(rows, idx)

    yoy_series = []
    for i, r in enumerate(rows):
        base = _year_ago(rows, i)
        yoy_series.append({
            "month": r["month"],
            "yoy": pct(r["wholesale"], base["wholesale"]) if base else None,
        })

    cumulative_wholesale = sum(r["wholesale"] for r in rows)
    cumulative_export = sum(r["export"] for r in rows)
    peak = max(rows, key=lambda r: r["share"])
    max_export = max(rows, key=lambda r: r["export"])
    half_export_months = [r["month"] for r in rows if r["share"] >= 0.5]

    return {
        "data": rows,
        "start_month": rows[0]["month"],
        "latest_month": latest["month"],
        "latest": {
            "wholesale": latest["wholesale"],
            "retail": latest["retail"],
            "export": latest["export"],
            "share_pct": round(latest["share"] * 100, 1),
            "mom_wholesale_pct": pct(latest["wholesale"], prev["wholesale"]) if prev else None,
            "mom_retail_pct": pct(latest["retail"], prev["retail"]) if prev else None,
            "mom_export_pct": pct(latest["export"], prev["export"]) if prev else None,
            "yoy_wholesale_pct": (
                pct(latest["wholesale"], yoy_row["wholesale"]) if yoy_row else None
            ),
            "yoy_retail_pct": pct(latest["retail"], yoy_row["retail"]) if yoy_row else None,
            "yoy_export_pct": pct(latest["export"], yoy_row["export"]) if yoy_row else None,
        },
        "cumulative": {
            "wholesale": cumulative_wholesale,
            "export": cumulative_export,
            "export_share_pct": (
                round(cumulative_export / cumulative_wholesale * 100, 1)
                if cumulative_wholesale else None
            ),
        },
        "peak": {"month": peak["month"], "share_pct": round(peak["share"] * 100, 1)},
        "max_export": {"month": max_export["month"], "export": max_export["export"]},
        "half_export_months": half_export_months,
        "yoy_series": yoy_series,
        "rolling": rolling_share(rows),
        "source_url": source_url,
    }


def format_terminal(r: dict) -> str:
    latest = r["latest"]
    cum = r["cumulative"]
    lines = []
    lines.append(f"Tesla 月度批发/零售/出口（{r['start_month']} ~ {r['latest_month']}）")
    lines.append(
        f"  最近完整月 {r['latest_month']}: 批发 {latest['wholesale']:,} "
        f"(环比 {latest['mom_wholesale_pct']:+.1f}%, 同比 {latest['yoy_wholesale_pct']:+.1f}%)"
    )
    lines.append(
        f"    国内零售 {latest['retail']:,} "
        f"(环比 {latest['mom_retail_pct']:+.1f}%, 同比 {latest['yoy_retail_pct']:+.1f}%)"
    )
    lines.append(
        f"    出口 {latest['export']:,} "
        f"(环比 {latest['mom_export_pct']:+.1f}%, 同比 {latest['yoy_export_pct']:+.1f}%) "
        f"| 出口占比 {latest['share_pct']}%"
    )
    lines.append(
        f"  期间累计批发 {cum['wholesale']:,} / 出口 {cum['export']:,}"
        f"（累计出口占比 {cum['export_share_pct']}%）"
    )
    lines.append(
        f"  出口占比峰值 {r['peak']['month']} {r['peak']['share_pct']}% | "
        f"出口量峰值 {r['max_export']['month']} {r['max_export']['export']:,}"
    )
    lines.append(
        "  口径: 出口占比 = 出口/批发 | "
        "数据源: dataset/cpca/tesla_monthly_wholesale_retail_export.csv"
    )
    return "\n".join(lines)


def _kpi_card(label: str, value: str, change: str, tone: str) -> str:
    return (
        f'<div class="kpi-card">'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f'<div class="change {tone}">{change}</div>'
        f'</div>'
    )


def _table_rows(rows: list) -> str:
    trs = []
    for r in rows:
        share = r["share"] * 100
        badge = ' <span class="badge badge-gold">出口过半</span>' if r["share"] >= 0.5 else ""
        trs.append(
            f'<tr><td class="num">{r["month"]}</td>'
            f'<td class="num">{r["wholesale"]:,}</td>'
            f'<td class="num">{r["retail"]:,}</td>'
            f'<td class="num">{r["export"]:,}</td>'
            f'<td class="num">{share:.1f}%{badge}</td></tr>'
        )
    return "\n".join(trs)


def _chart_html(fig: go.Figure, chart_id: str) -> str:
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        div_id=chart_id,
        config={"displayModeBar": False, "responsive": True},
    )


def render_html(r: dict, static_prefix: str) -> str:
    latest = r["latest"]
    cum = r["cumulative"]
    data = r["data"]

    months = [d["month"] for d in data]
    yoy_pairs = [(s["month"], s["yoy"]) for s in r["yoy_series"] if s["yoy"] is not None]
    yoy_months = [m for m, _ in yoy_pairs]
    yoy = [v for _, v in yoy_pairs]
    yoy_colors = [ZH["positive"] if v >= 0 else ZH["negative"] for v in yoy]

    fig1 = go.Figure(go.Bar(
        x=yoy_months, y=yoy, marker_color=yoy_colors, opacity=0.9,
        name="批发同比",
        hovertemplate="%{x} 批发同比 %{y:.1f}%<extra></extra>",
    ))
    apply_zh_theme(fig1)
    fig1.update_layout(margin=dict(l=50, r=20, t=20, b=40), height=360)

    fig2 = go.Figure(go.Scatter(
        x=months, y=r["rolling"], mode="lines+markers", connectgaps=False,
        line=dict(color=ZH["event"], width=3), marker=dict(size=6),
        name="出口占比（6个月滚动）",
        hovertemplate="%{x} 6个月滚动占比 %{y:.1f}%<extra></extra>",
    ))
    apply_zh_theme(fig2)
    fig2.update_layout(margin=dict(l=50, r=20, t=20, b=40), height=360)

    source_html = (
        f' · {r["latest_month"]} 拆分值来源 <a href="{r["source_url"]}">{r["source_url"]}</a>'
        if r.get("source_url") else ""
    )

    mom_wholesale = latest["mom_wholesale_pct"]
    mom_tone = "up" if (mom_wholesale is not None and mom_wholesale >= 0) else "down"
    half_note = "、".join(r["half_export_months"][-3:]) if r["half_export_months"] else "无"
    first_yoy_month = next(
        (s["month"] for s in r["yoy_series"] if s["yoy"] is not None), r["start_month"]
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Tesla 月度批发与出口 | Raccoon Research</title>
<link rel="stylesheet" href="{static_prefix}/templates/report_style.css" />
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
</head>
<body class="report-page">
<header>
  <div class="container">
    <div class="brand">
      <img class="brand-avatar" src="{static_prefix}/assets/brand/raccoon_avatar_light.png" alt="" />
      <span class="brand-name">Raccoon Research</span>
    </div>
    <span class="header-meta">Tesla 出口观察 | 数据至 {r['latest_month']} | 生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}</span>
  </div>
</header>

<main class="container">
  <section class="hero">
    <h1>Tesla 月度批发数量与出口占比</h1>
    <p>数据源：乘联会（CPCA）《全国乘用车市场分析》口径 · <code>dataset/cpca/tesla_monthly_wholesale_retail_export.csv</code> · {r['start_month']} 至 {r['latest_month']}{source_html}</p>
  </section>

  <section class="kpi-grid">
    {_kpi_card("期间累计批发", f"{cum['wholesale']:,}", f"{r['start_month']} ~ {r['latest_month']} 完整月", "neutral")}
    {_kpi_card("期间累计出口", f"{cum['export']:,}", f"累计出口占比 {cum['export_share_pct']}%", "neutral")}
    {_kpi_card(f"最近完整月（{r['latest_month']}）", f"{latest['wholesale']:,} 辆", f"环比 {mom_wholesale:+.1f}% · 出口占比 {latest['share_pct']}%", mom_tone)}
    {_kpi_card(f"出口占比峰值（{r['peak']['month']}）", f"{r['peak']['share_pct']}%", "出口为主驱动月份", "neutral")}
  </section>

  <section class="report-section">
    <h2 class="section-title">批发月同比</h2>
    <div class="chart-box">{_chart_html(fig1, "tesla-yoy")}</div>
    <div class="section-note">柱状 = 批发数量月同比（当月批发 / 上年同月 − 1，%）。绿色 = 同比增长，红色 = 同比下降。需上年同期为基数，故从 {first_yoy_month} 起；{r['latest_month']} 批发已公布（{latest['wholesale']:,} 辆）。</div>
  </section>

  <section class="report-section">
    <h2 class="section-title">出口占比 6 个月滚动趋势</h2>
    <div class="chart-box">{_chart_html(fig2, "tesla-rolling")}</div>
    <div class="section-note">折线 = 出口占比（出口/批发，%）的 6 个月滚动均值，平滑月度波动。{r['latest_month']} 批发 {latest['wholesale']:,}，国内零售 {latest['retail']:,}（{round(latest['retail'] / latest['wholesale'] * 100, 1)}%）、上海工厂出口 {latest['export']:,}（{latest['share_pct']}%）。</div>
  </section>

  <section class="report-section">
    <h2 class="section-title">月度明细表</h2>
    <div class="table-wrap"><table class="report-table">
      <thead><tr><th>月份</th><th>批发</th><th>国内零售</th><th>出口</th><th>出口占比</th></tr></thead>
      <tbody>
        {_table_rows(data)}
      </tbody>
    </table></div>
  </section>

  <section class="report-section">
    <h2 class="section-title">解读要点</h2>
    <ul>
      <li>出口占比 ≥ 50% 的月份（金色标记）共 {len(r['half_export_months'])} 个，近期为 {half_note}，属出口集中交付节奏，不代表国内零售走弱。</li>
      <li>出口占比峰值出现在 {r['peak']['month']}（{r['peak']['share_pct']}%）；单月出口量峰值出现在 {r['max_export']['month']}（{r['max_export']['export']:,} 辆）。</li>
      <li>{r['latest_month']} 批发 {latest['wholesale']:,} 辆（同比 {latest['yoy_wholesale_pct']:+.1f}%），国内零售 {latest['retail']:,} 辆（环比 {latest['mom_retail_pct']:+.1f}%、同比 {latest['yoy_retail_pct']:+.1f}%），出口 {latest['export']:,} 辆（环比 {latest['mom_export_pct']:+.1f}%、同比 {latest['yoy_export_pct']:+.1f}%）。</li>
      <li>批零剪刀差月份（批发明显高于零售）多由出口撑起，解读总量时应先分内销/外销。</li>
    </ul>
  </section>
</main>

<footer>
  <img class="brand-sig" src="{static_prefix}/assets/brand/zihao_signature_transparent.png" alt="Raccoon Research" />
  <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
</footer>
</body>
</html>
"""


def _compute_static_prefix(output_dir: Path) -> str:
    try:
        return str(WS_ROOT.resolve().relative_to(output_dir.resolve())).replace("\\", "/")
    except ValueError:
        return "../.."


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tesla 月度批发/零售/出口报告")
    parser.add_argument("--csv", type=str, default=str(DEFAULT_CSV), help="Tesla 月度数据 CSV 路径")
    parser.add_argument("--output", type=str, default=None, help="输出目录（默认 outputs/reports/）")
    parser.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    parser.add_argument("--html", action="store_true", help="生成品牌化 HTML 报告")
    parser.add_argument("--source-url", type=str, default=None, help="最新月份数据来源链接")
    args = parser.parse_args(argv)

    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = REPO_ROOT / csv_path
    out_dir = Path(args.output) if args.output else DEFAULT_OUTPUT
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_monthly(csv_path)
    if not rows:
        raise SystemExit(f"未在 {csv_path} 找到月度明细行")
    r = analyze(rows, source_url=args.source_url)

    cmd = "python research_scripts/tesla_wholesale_export_report.py"
    if args.source_url:
        cmd += f" --source-url {args.source_url}"
    if args.html:
        cmd += " --html"

    artifacts = {}
    if args.html:
        html = render_html(r, _compute_static_prefix(out_dir))
        html_path = out_dir / f"{REPORT_NAME}.html"
        html_path.write_text(html, encoding="utf-8")
        artifacts["html"] = str(html_path.resolve())

    latest = r["latest"]
    result = {
        "summary": (
            f"{r['latest_month']} Tesla 批发 {latest['wholesale']:,} 辆"
            f"（环比 {latest['mom_wholesale_pct']:+.1f}%、同比 {latest['yoy_wholesale_pct']:+.1f}%），"
            f"国内零售 {latest['retail']:,}、出口 {latest['export']:,}，出口占比 {latest['share_pct']}%。"
        ),
        "metrics": {
            "latest_month": r["latest_month"],
            "wholesale": latest["wholesale"],
            "retail": latest["retail"],
            "export": latest["export"],
            "export_share_pct": latest["share_pct"],
            "mom_wholesale_pct": latest["mom_wholesale_pct"],
            "yoy_wholesale_pct": latest["yoy_wholesale_pct"],
            "mom_retail_pct": latest["mom_retail_pct"],
            "yoy_retail_pct": latest["yoy_retail_pct"],
            "mom_export_pct": latest["mom_export_pct"],
            "yoy_export_pct": latest["yoy_export_pct"],
            "cumulative_wholesale": r["cumulative"]["wholesale"],
            "cumulative_export": r["cumulative"]["export"],
            "cumulative_export_share_pct": r["cumulative"]["export_share_pct"],
        },
        "tables": [{
            "name": "monthly",
            "columns": ["month", "wholesale", "retail", "export", "export_share"],
            "rows": [
                {"month": d["month"], "wholesale": d["wholesale"], "retail": d["retail"],
                 "export": d["export"], "export_share": round(d["share"], 3)}
                for d in rows
            ],
        }],
    }

    contract = build_success_contract(
        script="research_scripts/tesla_wholesale_export_report.py",
        command=cmd,
        scope={
            "data_source": (
                str(csv_path.relative_to(REPO_ROOT))
                if csv_path.is_relative_to(REPO_ROOT) else str(csv_path)
            ),
            "time_window": {"start_date": r["start_month"], "end_date": r["latest_month"]},
            "filters": {},
            "metric_definition": "Tesla 月度批发/国内零售/上海工厂出口；出口占比 = 出口/批发",
        },
        result=result,
        artifacts=artifacts,
        followup_context={
            "metric": "tesla_wholesale_retail_export",
            "latest_month": r["latest_month"],
            "available_dimensions": ["month", "metric"],
        },
        warnings=[],
    )

    if args.format == "json":
        print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(format_terminal(r))
        if artifacts.get("html"):
            print(f"  HTML: {artifacts['html']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
