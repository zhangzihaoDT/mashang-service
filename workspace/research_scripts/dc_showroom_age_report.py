#!/usr/bin/env python
"""
待销现车库龄与下线时间分布报告 — 固定库存分析工作流。

口径（复用 shared/operators/dealer_unsold_inventory.py）:
    待销现车  = is_dc_showroom_domestic = 物理位置=DC内 + 未进入订单表(无订单) + 剔除上汽国际/海外
    核心库存  = is_dc_domestic_uninvoiced = DC内 + 非海外 + 未开票
    核心库存  = 待销现车 + 有订单未开票
库龄     = real_in_dc_time(进交付中心) → as_of
下线距今 = real_as_offline_time(实际下线) → as_of

用法:
    python research_scripts/dc_showroom_age_report.py
    python research_scripts/dc_showroom_age_report.py --as-of 2026-08-05 --html
    python research_scripts/dc_showroom_age_report.py --format json --output outputs/tables/
    python research_scripts/dc_showroom_age_report.py --html --output outputs/reports/
"""

import sys
import json
import argparse
import importlib.util
from datetime import date
from pathlib import Path

import pandas as pd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
WS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
if str(WS_ROOT) not in sys.path:
    sys.path.insert(0, str(WS_ROOT))

spec = importlib.util.spec_from_file_location(
    "d", REPO_ROOT / "shared/operators" / "dealer_unsold_inventory.py"
)
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)

from utils.result_contract import build_success_contract  # noqa: E402
from utils.business import is_corporate_owner  # noqa: E402

SERIES_MAP = {"LSJEL": "LS8", "LSJEH": "LS9", "LSJWL": "LS7",
              "LSJWR": "LS6", "LSJWT": "L6", "LSJE3": "L7"}
MODELS = ["LS6", "LS8", "LS9", "L6", "LS7", "L7"]
COLOR_MAP = {"LS6": "#D79A36", "LS8": "#174A7C", "LS9": "#7ECDEB",
             "L6": "#7A4A24", "LS7": "#6B7C8F", "L7": "#06213D"}
DEFAULT_OUTPUT = WS_ROOT / "outputs" / "reports"
SALES_WINDOW_DAYS = 30

AGE_BUCKETS = [("0-30", 0), ("31-60", 31), ("61-90", 61),
               ("91-180", 91), ("181-365", 181), (">365", 366)]
OFFLINE_BUCKETS = [("0-30", 0), ("31-60", 31), ("61-90", 61),
                   ("91-180", 91), ("181-365", 181), ("366-730", 366), (">730", 731)]


def bucketize(days: pd.Series, buckets) -> pd.Series:
    labels = [b[0] for b in buckets]
    edges = [b[1] for b in buckets] + [float("inf")]
    return pd.cut(days, bins=edges, labels=labels, right=False, include_lowest=True)


def _pivot(show: pd.DataFrame, bucket_col: str) -> dict:
    piv = show.pivot_table(index=bucket_col, columns="series",
                           values="vin", aggfunc="count", fill_value=0)
    total = piv.sum(axis=1)
    out = []
    for bucket in piv.index:
        row = {"bucket": str(bucket)}
        for m in MODELS:
            row[m] = int(piv.loc[bucket, m]) if m in piv.columns else 0
        row["total"] = int(total.loc[bucket])
        row["share_pct"] = round(float(total.loc[bucket] / len(show) * 100), 1)
        out.append(row)
    return out


def monthly_sales(odf: pd.DataFrame, as_of: pd.Timestamp, window_days: int = SALES_WINDOW_DAYS) -> dict:
    start = as_of - pd.Timedelta(days=window_days)
    inv = odf[pd.to_datetime(odf["invoice_upload_time"]).between(start, as_of)]
    inv = inv[inv["lock_time"].notna()]
    if "owner_identity_no" in inv.columns:
        corp = inv["owner_identity_no"].apply(lambda x: is_corporate_owner(x) if pd.notna(x) else False)
        inv = inv[~corp]
    return {m: int(inv.loc[inv["series"] == m, "order_number"].nunique()) for m in MODELS}


def evaluate_mos(mos: float, old_share_pct: float) -> str:
    if mos is None:
        return "无近30天销量"
    if mos < 1.5 and old_share_pct < 25:
        return "健康"
    if mos >= 2.5 or old_share_pct >= 40:
        return "去库存压力较大"
    return "可接受，关注老库存"


def analyze(inv: pd.DataFrame, odf: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    out = d.compute(inv, odf)
    out["series"] = out["vin"].str[:5].map(SERIES_MAP).fillna("其他")

    core = out[out["is_dc_domestic_uninvoiced"] == 1]
    show = out[out["is_dc_showroom_domestic"] == 1].copy()
    show["dc_age"] = np.clip((as_of - show["real_in_dc_time"]).dt.days, 0, None)
    show["off_age"] = np.clip((as_of - show["real_as_offline_time"]).dt.days, 0, None)
    show["dc_bucket"] = bucketize(show["dc_age"], AGE_BUCKETS)
    show["off_bucket"] = bucketize(show["off_age"], OFFLINE_BUCKETS)

    locked_uninvoiced = int((core["has_order"] == 1).sum())
    no_bloc = show[show["bloc_name"].isna()]
    gap = (show["real_in_dc_time"] - show["real_as_offline_time"]).dt.days

    sales = monthly_sales(odf, as_of)
    mos_table = []
    for m in MODELS:
        inventory = int((show["series"] == m).sum())
        sales_30d = sales[m]
        mos = round(inventory / sales_30d, 2) if sales_30d > 0 else None
        old_share = round(float((show["dc_age"] > 90).loc[show["series"] == m].mean() * 100), 1) if inventory else 0.0
        mos_table.append({
            "series": m,
            "inventory": inventory,
            "sales_30d": sales_30d,
            "mos": mos,
            "old_share_pct": old_share,
            "evaluation": evaluate_mos(mos, old_share),
        })

    return {
        "as_of": as_of.strftime("%Y-%m-%d"),
        "kpis": {
            "showroom_total": int(len(show)),
            "core_inventory": int(len(core)),
            "locked_uninvoiced": locked_uninvoiced,
            "dc_age_median": int(show["dc_age"].median()),
            "dc_age_mean": round(float(show["dc_age"].mean()), 0),
            "off_age_median": int(show["off_age"].median()),
            "off_age_mean": round(float(show["off_age"].mean()), 0),
            "dc_under_90d_share_pct": round(float((show["dc_age"] <= 90).mean() * 100), 1),
            "off_over_3m_share_pct": round(float((show["off_age"] >= 91).mean() * 100), 1),
            "off_over_6m_share_pct": round(float((show["off_age"] >= 181).mean() * 100), 1),
            "gap_dc_mean_days": round(float(gap.mean()), 0),
            "gap_dc_median_days": int(gap.median()),
        },
        "by_series": {m: int((show["series"] == m).sum()) for m in MODELS},
        "dc_age_table": _pivot(show, "dc_bucket"),
        "offline_age_table": _pivot(show, "off_bucket"),
        "mos_table": mos_table,
        "sales_window_days": SALES_WINDOW_DAYS,
        "no_bloc": {
            "count": int(len(no_bloc)),
            "median_days": int(no_bloc["dc_age"].median()) if len(no_bloc) else 0,
            "mean_days": round(float(no_bloc["dc_age"].mean()), 0) if len(no_bloc) else 0,
            "max_days": int(no_bloc["dc_age"].max()) if len(no_bloc) else 0,
        },
    }


def format_terminal(r: dict) -> str:
    k = r["kpis"]
    lines = []
    lines.append(f"待销现车库龄分析（as-of {r['as_of']}）")
    lines.append(f"  待销现车(剔除海外): {k['showroom_total']:,} | 核心库存: {k['core_inventory']:,} "
                 f"(= 待销现车 + 有订单未开票 {k['locked_uninvoiced']:,})")
    lines.append(f"  分系列: " + "、".join(f"{m} {r['by_series'][m]}" for m in MODELS))
    lines.append("")
    lines.append(f"库龄(进DC至今): 中位 {k['dc_age_median']} 天 / 均值 {k['dc_age_mean']:.0f} 天 | "
                 f"≤90天占 {k['dc_under_90d_share_pct']}%")
    for row in r["dc_age_table"]:
        cells = " ".join(f"{m} {row[m]}" for m in MODELS if row[m])
        lines.append(f"  {row['bucket']:<8} 合计 {row['total']:<6} ({row['share_pct']}%)  {cells}")
    lines.append("")
    lines.append(f"下线距今: 中位 {k['off_age_median']} 天 / 均值 {k['off_age_mean']:.0f} 天 | "
                 f"≥3月 {k['off_over_3m_share_pct']}% | ≥6月 {k['off_over_6m_share_pct']}%")
    for row in r["offline_age_table"]:
        cells = " ".join(f"{m} {row[m]}" for m in MODELS if row[m])
        lines.append(f"  {row['bucket']:<8} 合计 {row['total']:<6} ({row['share_pct']}%)  {cells}")
    lines.append("")
    lines.append(f"📊 经营分析（MOS = 当前库存 / 近30天销量，销量=零售开票剔除对公）")
    lines.append(f"  {'系列':<5}{'当前库存':>8}{'近30天销量':>10}{'MOS':>8}{'90天以上占比':>12}  评价")
    for row in r["mos_table"]:
        mos = f"{row['mos']:.2f}" if row["mos"] is not None else "—"
        lines.append(f"  {row['series']:<5}{row['inventory']:>8,}{row['sales_30d']:>10,}{mos:>8}"
                     f"{row['old_share_pct']:>11.1f}%  {row['evaluation']}")
    lines.append("")
    n = r["no_bloc"]
    lines.append(f"无经销商归属: {n['count']:,} 辆，库龄中位 {n['median_days']} 天 / 均值 {n['mean_days']:.0f} / 最长 {n['max_days']} 天")
    lines.append("")
    lines.append("口径: is_dc_showroom_domestic（DC内+无订单+非海外） | "
                 "数据源: dataset/delivery_inventory.parquet + order_data.parquet")
    return "\n".join(lines)


def _row_table_html(rows, is_badge_on_row) -> str:
    trs = []
    for row in rows:
        badge_idx = None
        if is_badge_on_row:
            maxv = 0
            for m in MODELS:
                if row[m] > maxv:
                    maxv, badge_idx = row[m], m
        tds = [f"<td>{row['bucket']}</td>"]
        for m in MODELS:
            cls = f' class="badge badge-gold"' if (m == badge_idx and row[m] > 0) else ""
            tds.append(f"<td>{f'<span{cls}>{row[m]}</span>' if cls else row[m]}</td>")
        tds.append(f"<td><strong>{row['total']:,}</strong></td>")
        tds.append(f"<td>{row['share_pct']}%</td>")
        trs.append("<tr>" + "".join(tds) + "</tr>")
    return "\n".join(trs)


def render_html(r: dict, static_prefix: str) -> str:
    k = r["kpis"]
    n = r["no_bloc"]
    series_rows = "".join(
        f"<tr><td>{m}</td><td>{r['by_series'][m]:,}</td></tr>" for m in MODELS
    )
    t1 = _row_table_html(r["dc_age_table"], is_badge_on_row=True)
    t2 = _row_table_html(r["offline_age_table"], is_badge_on_row=True)

    def mos_badge(ev: str) -> str:
        if ev == "健康":
            return '<span class="badge badge-blue">健康</span>'
        if ev == "去库存压力较大":
            return '<span class="badge badge-gold">去库存压力较大</span>'
        return '<span class="badge badge-outline">可接受，关注老库存</span>'

    mos_rows = "".join(
        f"<tr><td><strong>{row['series']}</strong></td>"
        f"<td>{row['inventory']:,}</td>"
        f"<td>{row['sales_30d']:,}</td>"
        f"<td><strong>{row['mos']:.2f}</strong></td>"
        f"<td>{row['old_share_pct']:.1f}%</td>"
        f"<td>{mos_badge(row['evaluation'])}</td></tr>"
        for row in r["mos_table"]
    )

    # Plotly 堆积条形图数据
    def series_vectors(rows):
        return {m: [row[m] for row in rows] for m in MODELS}

    vec1 = series_vectors(r["dc_age_table"])
    vec2 = series_vectors(r["offline_age_table"])
    buckets1 = [row["bucket"] for row in r["dc_age_table"]]
    buckets2 = [row["bucket"] for row in r["offline_age_table"]]

    traces1 = ",\n".join(
        f"{{x: {json.dumps(buckets1, ensure_ascii=False)}, y: {json.dumps(vec1[m])}, "
        f"type: 'bar', name: '{m}', marker: {{color: '{COLOR_MAP[m]}'}}}}" for m in MODELS
    )
    traces2 = ",\n".join(
        f"{{x: {json.dumps(buckets2, ensure_ascii=False)}, y: {json.dumps(vec2[m])}, "
        f"type: 'bar', name: '{m}', marker: {{color: '{COLOR_MAP[m]}'}}}}" for m in MODELS
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>待销现车库龄分析 | {r['as_of']}</title>
<link rel="stylesheet" href="{static_prefix}/templates/report_style.css" />
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
</head>
<body>
<header>
  <div class="container">
    <div class="brand">
      <img class="brand-avatar" src="{static_prefix}/assets/brand/raccoon_avatar_light.png" alt="" />
      <span class="brand-name">Raccoon Research</span>
    </div>
    <span class="header-meta">待销现车分析 | {r['as_of']}</span>
  </div>
</header>

<main class="container">
  <section class="hero">
    <h1>待销现车库龄与下线时间分布</h1>
    <p>国内 DC 在库 · 未开票 · 未绑定订单，截至 {r['as_of']}，共 {k['showroom_total']:,} 辆</p>
  </section>

  <section class="kpi-grid">
    <div class="kpi-card">
      <div class="label">待销现车（剔除海外）</div>
      <div class="value">{k['showroom_total']:,}</div>
      <div class="change neutral">= 核心库存 {k['core_inventory']:,} − 有订单未开票 {k['locked_uninvoiced']:,}</div>
    </div>
    <div class="kpi-card">
      <div class="label">进 DC 库龄 · 中位数</div>
      <div class="value">{k['dc_age_median']} 天</div>
      <div class="change neutral">均值 {k['dc_age_mean']:.0f} 天</div>
    </div>
    <div class="kpi-card">
      <div class="label">下线距今 · 中位数</div>
      <div class="value">{k['off_age_median']} 天</div>
      <div class="change down">均值 {k['off_age_mean']:.0f} 天，比库龄更老</div>
    </div>
    <div class="kpi-card">
      <div class="label">下线距今 ≥ 3 个月</div>
      <div class="value">{k['off_over_3m_share_pct']}%</div>
      <div class="change down">{k['off_over_6m_share_pct']}% 在半年以上</div>
    </div>
  </section>

  <section class="card">
    <h2>① 进 DC 库龄分布（库龄 = 进交付中心至今）</h2>
    <div class="chart-box" id="chart-dc"></div>
    <div class="table-wrap"><table class="data-table">
      <thead>
        <tr><th>库龄</th><th>LS6</th><th>LS8</th><th>LS9</th><th>L6</th><th>LS7</th><th>L7</th><th>合计</th><th>占比</th></tr>
      </thead>
      <tbody>
        {t1}
      </tbody>
    </table></div>
    <div class="section-note">库龄 ≤ 90 天占 {k['dc_under_90d_share_pct']}%。金色标记为该档最大系列。</div>
  </section>

  <section class="card">
    <h2>② 经营分析：MOS（库存月数 = 当前库存 / 近30天销量）</h2>
    <div class="table-wrap"><table class="data-table">
      <thead>
        <tr><th>车型</th><th>当前库存</th><th>近30天销量</th><th>MOS</th><th>90天以上库存占比</th><th>评价</th></tr>
      </thead>
      <tbody>
        {mos_rows}
      </tbody>
    </table></div>
    <div class="section-note">销量口径 = 近30天零售开票（剔除对公批售）。90天以上占比 = 待销现车库龄 &gt; 90 天的比例。评价规则：MOS&lt;1.5 且老库存&lt;25% → 健康；MOS≥2.5 或老库存≥40% → 去库存压力较大；其余 → 可接受。</div>
  </section>

  <section class="card">
    <h2>③ 下线时间距今分布（下线 = real_as_offline_time）</h2>
    <div class="chart-box" id="chart-off"></div>
    <div class="table-wrap"><table class="data-table">
      <thead>
        <tr><th>下线距今</th><th>LS6</th><th>LS8</th><th>LS9</th><th>L6</th><th>LS7</th><th>L7</th><th>合计</th><th>占比</th></tr>
      </thead>
      <tbody>
        {t2}
      </tbody>
    </table></div>
    <div class="section-note">下线距今 ≥ 3 个月占 {k['off_over_3m_share_pct']}%，≥ 6 个月占 {k['off_over_6m_share_pct']}%。下线 → 进 DC 平均 {k['gap_dc_mean_days']:.0f} 天（中位 {k['gap_dc_median_days']} 天），因此下线距今整体比库龄更老。</div>
  </section>

  <section class="card">
    <h2>分系列一览</h2>
    <div class="table-wrap"><table class="data-table">
      <thead><tr><th>系列</th><th>待销现车</th></tr></thead>
      <tbody>
        {series_rows}
      </tbody>
    </table></div>
  </section>

  <section class="insight-grid">
    <div class="insight-card">
      <div class="insight-num">LS8</div>
      <div class="insight-content">
        <h3>批次性积压：下线后 2-6 个月</h3>
        <p>LS8 待销现车 {r['by_series']['LS8']:,} 辆集中在 61-180 天下线档，6 个月后档位归零，批次特征清晰。</p>
      </div>
    </div>
    <div class="insight-card">
      <div class="insight-num">LS6</div>
      <div class="insight-content">
        <h3>两极分化：新车到库 + 半年档积压</h3>
        <p>LS6 新近到库与 181-365 天下线档并存，需关注老库存去化。</p>
      </div>
    </div>
    <div class="insight-card">
      <div class="insight-num">停产</div>
      <div class="insight-content">
        <h3>停产车型沉淀最深</h3>
        <p>&gt;730 天档基本为 LS7 / L7 停产车型，已失去销售时效性。</p>
      </div>
    </div>
    <div class="insight-card">
      <div class="insight-num">{n['count']}</div>
      <div class="insight-content">
        <h3>无经销商归属 = 历史积压</h3>
        <p>无 bloc_name {n['count']:,} 辆，库龄中位 {n['median_days']} 天、最长 {n['max_days']} 天，为遗留库存。</p>
      </div>
    </div>
  </section>

  <section class="card">
    <h2>口径说明</h2>
    <table class="data-table scope-table">
      <tbody>
        <tr><td class="scope-label"><strong>数据源</strong></td><td>dataset/delivery_inventory.parquet + dataset/order_data.parquet</td></tr>
        <tr><td class="scope-label"><strong>截止时间</strong></td><td>{r['as_of']}</td></tr>
        <tr><td class="scope-label"><strong>指标口径</strong></td><td>待销现车 = shared/operators/dealer_unsold_inventory.py 中 is_dc_showroom_domestic（物理位置=DC内 + 未进入订单表 + 剔除上汽国际/海外）</td></tr>
        <tr><td class="scope-label"><strong>库龄定义</strong></td><td>real_in_dc_time（进交付中心）→ {r['as_of']} 的天数</td></tr>
        <tr><td class="scope-label"><strong>下线定义</strong></td><td>real_as_offline_time（实际下线）→ {r['as_of']} 的天数</td></tr>
        <tr><td class="scope-label"><strong>MOS 定义</strong></td><td>MOS = 待销现车库存 / 近30天销量（零售开票·剔除对公批售，窗口 {r['sales_window_days']} 天）；90天以上占比 = 库龄 &gt; 90 天占比</td></tr>
        <tr><td class="scope-label"><strong>口径关系</strong></td><td>核心库存 {k['core_inventory']:,} = 待销现车 {k['showroom_total']:,} + 有订单未开票 {k['locked_uninvoiced']:,}（待销现车 ⊂ 核心库存）</td></tr>
      </tbody>
    </table>
  </section>
</main>

<footer>
  <img class="brand-sig" src="{static_prefix}/assets/brand/zihao_signature_transparent.png" alt="Raccoon Research" />
  <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
</footer>
<script>
Plotly.newPlot('chart-dc', [{traces1}], {{
    title: {{text: '进DC库龄分布（分系列）'}},
    barmode: 'stack',
    xaxis: {{title: '库龄档'}},
    yaxis: {{title: '辆'}},
    margin: {{l: 60, r: 30, t: 40, b: 40}},
    paper_bgcolor: 'white', plot_bgcolor: 'white',
    font: {{family: '-apple-system, sans-serif', color: '#1F2D3D'}},
    legend: {{orientation: 'h', y: -0.2}}
}});
Plotly.newPlot('chart-off', [{traces2}], {{
    title: {{text: '下线距今分布（分系列）'}},
    barmode: 'stack',
    xaxis: {{title: '下线距今档'}},
    yaxis: {{title: '辆'}},
    margin: {{l: 60, r: 30, t: 40, b: 40}},
    paper_bgcolor: 'white', plot_bgcolor: 'white',
    font: {{family: '-apple-system, sans-serif', color: '#1F2D3D'}},
    legend: {{orientation: 'h', y: -0.2}}
}});
</script>
</body>
</html>
"""


def _compute_static_prefix(output_dir: Path) -> str:
    try:
        return str(Path(WS_ROOT).resolve().relative_to(output_dir.resolve())).replace("\\", "/")
    except ValueError:
        return "../.."


def main(argv=None):
    parser = argparse.ArgumentParser(description="待销现车库龄与下线时间分布报告")
    parser.add_argument("--as-of", type=str, default=None, help="截止日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--output", type=str, default=None, help="输出目录（json/html）")
    parser.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    parser.add_argument("--html", action="store_true", help="生成品牌化 HTML 报告")
    args = parser.parse_args(argv)

    as_of = pd.Timestamp(args.as_of or date.today().strftime("%Y-%m-%d"))
    out_dir = Path(args.output) if args.output else DEFAULT_OUTPUT
    out_dir.mkdir(parents=True, exist_ok=True)

    print("📖 读取数据 ...")
    inv = pd.read_parquet(REPO_ROOT / "dataset" / "delivery_inventory.parquet")
    odf = pd.read_parquet(REPO_ROOT / "dataset" / "order_data.parquet")
    r = analyze(inv, odf, as_of)

    cmd = "python research_scripts/dc_showroom_age_report.py"
    if args.as_of:
        cmd += f" --as-of {args.as_of}"
    if args.html:
        cmd += " --html"

    if args.format == "json":
        contract = build_success_contract(
            script="research_scripts/dc_showroom_age_report.py",
            command=cmd,
            scope={
                "data_source": "dataset/delivery_inventory.parquet + dataset/order_data.parquet",
                "as_of": r["as_of"],
                "metric_definition": "待销现车 = is_dc_showroom_domestic（DC内+无订单+非海外）；库龄/下线距今分布",
            },
            result=r,
            followup_context={
                "metric": "dc_showroom_age",
                "as_of": r["as_of"],
                "available_dimensions": ["series", "store", "bloc_name"],
            },
        )
        out_path = out_dir / f"dc_showroom_age_{r['as_of']}.json"
        out_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(format_terminal(r))

    if args.html:
        html = render_html(r, _compute_static_prefix(out_dir))
        html_path = out_dir / f"dc_showroom_age_{r['as_of']}.html"
        html_path.write_text(html, encoding="utf-8")
        print(f"  HTML: {html_path.resolve()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
