#!/usr/bin/env python
"""
新车型发布时点风险快照 — 各新车型预售发布（time_periods.{series}.start）前最近观察点的
Backlog 风险暴露量（At-Risk Backlog）与存量池质量。

背景:
    新品发布窗口的业务风险是经营预警的核心关注点。本脚本对每个新车型的预售发布时点，
    取发布前最近的历史观察点（当年累计口径），输出该时点的:
        - 风险暴露量 = 名义 Backlog × (1 − 有效率) = 悬置池 − ELOE
        - 池子规模与有效率（风险强度 = 1 − 有效率）
        - 在历史风险暴露分布中所处的分位（判断发布时点是否处于异常风险窗口）

依赖方向：历史观察点序列来自 backlog_rate_trend_report.compute_history（其内部直接消费
shared/operators/effective_locked_orders.py），order_data 经 utils/data_loader 加载；
不依赖 stalled_order_forecast.py。

用法:
    python research_scripts/launch_risk_snapshot.py
    python research_scripts/launch_risk_snapshot.py --as-of 2026-08-16
    python research_scripts/launch_risk_snapshot.py --format json
    python research_scripts/launch_risk_snapshot.py --format html --output outputs/reports/

依赖:
    dataset/order_data.parquet, shared/schema/business_definition.json
"""

import sys, argparse, json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

import pandas as pd
import numpy as np
from mashang_workspace.research_scripts.backlog_rate_trend_report import compute_history
from utils.data_loader import load_order_data as load_data

BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"

COLOR_OWN = "#174A7C"
COLOR_EVENT = "#D79A36"
COLOR_NEG = "#D95F59"
COLOR_POS = "#2A9D8F"
COLOR_ASH = "#9AA3AD"

LAUNCH_LABELS = {
    "CM0": "LS6 (老款)",
    "DM0": "L6 (老款)",
    "CM1": "全新 LS6",
    "DM1": "全新 L6",
    "CM2": "新一代 LS6",
    "LS9": "LS9",
    "LS8": "LS8",
}


def parse_args():
    p = argparse.ArgumentParser(description="新车型发布时点风险快照")
    p.add_argument("--as-of", type=str, default=None, help="报告截止观察点（默认最新数据日）")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json", "html"])
    p.add_argument("--output", type=str, default=str(_WS_ROOT / "outputs" / "reports"), help="输出目录")
    return p.parse_args()


def load_launches() -> list[dict]:
    with open(BUSINESS_DEF, encoding="utf-8") as f:
        bd = json.load(f)
    tp = bd.get("time_periods", {})
    launches = []
    for key, info in tp.items():
        start = info.get("start")
        if not start:
            continue
        launches.append({
            "group": key,
            "label": LAUNCH_LABELS.get(key, key),
            "start": pd.Timestamp(start),
        })
    launches.sort(key=lambda x: x["start"])
    return launches


def build_snapshot(rdf: pd.DataFrame, launches: list[dict]) -> dict:
    rdf["obs"] = pd.to_datetime(rdf["as_of"])
    allrisk = rdf["at_risk"]
    hist = {
        "p25": int(allrisk.quantile(0.25)),
        "p50": int(allrisk.quantile(0.5)),
        "p75": int(allrisk.quantile(0.75)),
        "max": int(allrisk.max()),
        "mean": round(float(allrisk.mean()), 1),
    }
    rows = []
    # 当前值参考行：取最新观察点，便于与各历史发布时点直接对比
    last = rdf.iloc[-1]
    cur_at_risk = float(last["at_risk"])
    rows.append({
        "group": "current",
        "label": "当前",
        "launch": "—",
        "obs": last["as_of"],
        "at_risk": round(cur_at_risk, 1),
        "n_orders": int(last["n_orders"]),
        "rate": round(float(last["rate"]), 4),
        "risk_intensity": round(1.0 - float(last["rate"]), 4),
        "percentile": round(float((allrisk < cur_at_risk).mean()), 4),
    })
    for l in launches:
        t = l["start"]
        prev = rdf[rdf["obs"] < t]
        if prev.empty:
            rows.append({"group": l["group"], "label": l["label"], "launch": str(t.date()),
                         "obs": None, "at_risk": None, "n_orders": None, "rate": None,
                         "percentile": None, "risk_intensity": None})
            continue
        r = prev.iloc[-1]
        at_risk = float(r["at_risk"])
        rows.append({
            "group": l["group"],
            "label": l["label"],
            "launch": str(t.date()),
            "obs": r["as_of"],
            "at_risk": round(at_risk, 1),
            "n_orders": int(r["n_orders"]),
            "rate": round(float(r["rate"]), 4),
            "risk_intensity": round(1.0 - float(r["rate"]), 4),
            "percentile": round(float((allrisk < at_risk).mean()), 4),
        })
    return {"history": hist, "rows": rows}


def format_terminal(snap: dict) -> str:
    h = snap["history"]
    lines = []
    lines.append(f"新车型发布时点风险快照（历史风险暴露 P25={h['p25']:,} P50={h['p50']:,} P75={h['p75']:,} max={h['max']:,}）")
    lines.append(f"  {'车型':<14}{'预售发布':<12}{'前观察点':<12}{'风险暴露':>8}{'池子':>7}{'有效率':>8}{'风险强度':>8}{'分位':>7}")
    for r in snap["rows"]:
        if r["obs"] is None:
            lines.append(f"  {r['label']:<14}{r['launch']:<12}（无历史观察点）")
            continue
        line = (
            f"  {r['label']:<14}{r['launch']:<12}{r['obs']:<12}{int(r['at_risk']):>8,}"
            f"{r['n_orders']:>7,}{r['rate']:>8.1%}{r['risk_intensity']:>8.1%}{r['percentile']:>7.0%}"
        )
        if r["group"] == "current":
            line += "  ← 当前"
        lines.append(line)
    return "\n".join(lines)


def _static_prefix(output_dir: Path) -> str:
    try:
        return str(Path(_WS_ROOT).resolve().relative_to(output_dir.resolve())).replace("\\", "/")
    except ValueError:
        return "../.."


def render_html(snap: dict, as_of: str, static_prefix: str) -> str:
    h = snap["history"]
    rows = []
    for r in snap["rows"]:
        is_current = r["group"] == "current"
        if r["obs"] is None:
            rows.append(f"<tr><td><strong>{r['label']}</strong></td><td>{r['launch']}</td>"
                        f"<td colspan='5' class='num'>无历史观察点</td></tr>")
            continue
        badge = ""
        if is_current:
            badge = '<span class="badge badge-gold">当前</span>'
        elif r["percentile"] >= 0.75:
            badge = '<span class="badge badge-gold">偏高</span>'
        elif r["percentile"] <= 0.10:
            badge = '<span class="badge badge-blue">偏低</span>'
        tr_style = ' style="background: rgba(23,74,124,.06);"' if is_current else ""
        rows.append(
            f"<tr{tr_style}><td><strong>{r['label']}</strong></td><td>{r['launch']}</td>"
            f"<td>{r['obs']}</td><td class='num'>{int(r['at_risk']):,}</td>"
            f"<td class='num'>{r['n_orders']:,}</td><td class='num'>{r['rate']:.1%}</td>"
            f"<td class='num'>{r['risk_intensity']:.1%}</td>"
            f"<td class='num'>{r['percentile']:.0%}</td><td>{badge}</td></tr>"
        )
    rows_html = "\n".join(rows)

    # 图表数据（含当前参考行；当前点用品牌蓝/绿区分）
    valid = [r for r in snap["rows"] if r["obs"] is not None]
    n_launches = len([r for r in valid if r["group"] != "current"])
    labels = [r["label"] for r in valid]
    atrisk = [int(r["at_risk"]) for r in valid]
    rates = [f"{r['rate']:.4f}" for r in valid]
    pcts = [f"{r['percentile']:.4f}" for r in valid]
    risk_colors = [COLOR_OWN if r["group"] == "current" else COLOR_EVENT for r in valid]
    risk_trace = (
        f"{{x: {json.dumps(labels)}, y: {json.dumps(atrisk)}, type: 'bar', name: '风险暴露量', "
        f"marker: {{color: {json.dumps(risk_colors)}}}, "
        f"hovertemplate: '%{{x}}<br>风险暴露 %{{y:,}} 单<extra></extra>'}}"
    )
    rate_trace = (
        f"{{x: {json.dumps(labels)}, y: {json.dumps(rates)}, type: 'scatter', mode: 'lines+markers', "
        f"name: '有效率', yaxis: 'y2', line: {{color: '{COLOR_OWN}', width: 2}}, "
        f"hovertemplate: '%{{x}}<br>有效率 %{{y:.1%}}<extra></extra>'}}"
    )
    pct_trace = (
        f"{{x: {json.dumps(labels)}, y: {json.dumps(pcts)}, type: 'bar', name: '历史分位', "
        f"marker: {{color: '{COLOR_ASH}', opacity: 0.6}}, hovertemplate: '%{{x}}<br>历史分位 %{{y:.0%}}<extra></extra>'}}"
    )

    # 四象限矩阵：x=风险暴露绝对值, y=风险强度（当前点用品牌蓝 + 稍大标记）
    risk_abs = [int(r["at_risk"]) for r in valid]
    intensities = [r["risk_intensity"] for r in valid]
    quad_labels = [r["label"] for r in valid]
    quad_colors = [COLOR_OWN if r["group"] == "current" else "#7ECDEB" for r in valid]
    quad_sizes = [16 if r["group"] == "current" else 12 for r in valid]
    quad_median_x = float(np.median(risk_abs))
    quad_median_y = float(np.median(intensities))
    quad_xmax = max(risk_abs) * 1.15
    quadrant_trace = (
        f"{{x: {json.dumps(risk_abs)}, y: {json.dumps([f'{v:.4f}' for v in intensities])}, "
        f"mode: 'markers+text', text: {json.dumps(quad_labels)}, textposition: 'top center', "
        f"marker: {{size: {json.dumps(quad_sizes)}, color: {json.dumps(quad_colors)}, "
        f"opacity: 0.9, line: {{width: 1.5, color: 'white'}}}}, "
        f"hovertemplate: '%{{text}}<br>风险暴露 %{{x:,}} 单<br>风险强度 %{{y:.1%}}<extra></extra>'}}"
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>新车型发布时点风险快照 | {as_of}</title>
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
    <span class="header-meta">发布时点风险快照 | 截至 {as_of}</span>
  </div>
</header>

<main class="container">
  <section class="hero">
    <h1>新车型发布时点风险快照</h1>
    <p>Nominal Backlog is a system state; Effective Backlog is a forecast.</p>
    <p>各新车型预售发布（time_periods.start）前最近观察点 · 当年累计口径 · 风险暴露 = 悬置池 − ELOE</p>
  </section>

  <section class="kpi-grid">
    <div class="kpi-card"><div class="label">历史风险暴露 P50</div>
      <div class="value">{h['p50']:,} 单</div>
      <div class="change neutral">P25~P75 {h['p25']:,}~{h['p75']:,}</div></div>
    <div class="kpi-card"><div class="label">历史风险暴露上限</div>
      <div class="value">{h['max']:,} 单</div>
      <div class="change neutral">均值 {h['mean']:.0f}</div></div>
    <div class="kpi-card"><div class="label">发布前观察点数</div>
      <div class="value">{n_launches}</div>
      <div class="change neutral">覆盖 {n_launches} 个上市批次</div></div>
    <div class="kpi-card"><div class="label">当前风险暴露量</div>
      <div class="value">{int(valid[0]['at_risk']):,} 单</div>
      <div class="change neutral">截至 {valid[0]['obs']} · 分位 {valid[0]['percentile']:.0%}</div></div>
  </section>

  <section class="card">
    <h2>① 发布前风险暴露量（按车型）</h2>
    <div class="chart-box" id="chart-risk" style="height:380px;"></div>
    <div class="section-note">绝对量受"当年已运行月数"影响（年初池小、年末池大），横向比较请重点看风险强度与历史分位。</div>
  </section>

  <section class="card">
    <h2>② 发布前有效率 vs 历史分位</h2>
    <div class="chart-box" id="chart-rate" style="height:380px;"></div>
    <div class="section-note">有效率越高 = 发布前存量池质量越健康；历史分位 ≥75% 标注为风险偏高，≤10% 标注为偏低。</div>
  </section>

  <section class="card">
    <h2>③ 风险暴露绝对值 × 风险强度 四象限矩阵</h2>
    <div class="chart-box" id="chart-quadrant" style="height:460px;"></div>
    <div class="section-note">
      横轴 = 风险暴露绝对值（单），纵轴 = 风险强度（1 − 有效率）。四象限含义：<br>
      左上「小池高损」：池子小但质量差（如新一代 LS6），绝对压力有限，重在清积压；<br>
      右上「大池高损」：池子大且质量差（如 LS6 老款），绝对风险最高，最需干预；<br>
      左下「小池低损」：池子小且质量好（如 LS8），最健康；<br>
      右下「大池低损」：池子大但质量好（如 LS9），绝对量可观但兑现把握高。
    </div>
  </section>

  <section class="card">
    <h2>发布时点明细（含当前参考行）</h2>
    <div class="table-wrap"><table class="report-table">
      <thead><tr><th>车型</th><th>预售发布</th><th>前观察点</th><th>风险暴露</th><th>池子</th><th>有效率</th><th>风险强度</th><th>历史分位</th><th>标注</th></tr></thead>
      <tbody>
        {rows_html}
      </tbody>
    </table></div>
    <div class="section-note">首行「当前」为最新观察点参考值，用于与各历史发布时点直接对比当前风险水位。</div>
  </section>
</main>

<footer>
  <img class="brand-sig" src="{static_prefix}/assets/brand/zihao_signature_transparent.png" alt="Raccoon Research" />
  <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
</footer>

<script>
Plotly.newPlot('chart-risk', [
  {risk_trace}
], {{
  title: {{text: '各车型发布前风险暴露量'}},
  yaxis: {{title: '风险暴露量（单）'}},
  margin: {{l: 60, r: 30, t: 50, b: 60}},
  paper_bgcolor: 'white', plot_bgcolor: 'white',
  font: {{family: '-apple-system, sans-serif', color: '#1F2D3D'}},
  shapes: [{{type: 'line', x0: -0.5, x1: {len(valid)-0.5}, y0: {h['p50']:.1f}, y1: {h['p50']:.1f},
            line: {{color: '{COLOR_ASH}', width: 1, dash: 'dot'}}}}]
}});
Plotly.newPlot('chart-rate', [
  {rate_trace}, {pct_trace}
], {{
  title: {{text: '发布前有效率（线）与历史分位（柱）'}},
  yaxis: {{title: '历史分位', tickformat: '.0%', range: [0, 1]}},
  yaxis2: {{title: '有效率', overlaying: 'y', side: 'right', tickformat: '.0%', range: [0, 1]}},
  margin: {{l: 60, r: 60, t: 50, b: 60}},
  paper_bgcolor: 'white', plot_bgcolor: 'white',
  font: {{family: '-apple-system, sans-serif', color: '#1F2D3D'}},
  legend: {{orientation: 'h', y: -0.25}}
}});
Plotly.newPlot('chart-quadrant', [
  {quadrant_trace}
], {{
  title: {{text: '风险暴露绝对值 × 风险强度 四象限'}},
  xaxis: {{title: '风险暴露绝对值（单）', range: [0, {quad_xmax:.0f}]}},
  yaxis: {{title: '风险强度（1 − 有效率）', tickformat: '.0%', range: [0, 1]}},
  margin: {{l: 60, r: 40, t: 50, b: 60}},
  paper_bgcolor: 'white', plot_bgcolor: 'white',
  font: {{family: '-apple-system, sans-serif', color: '#1F2D3D'}},
  shapes: [
    {{type: 'line', x0: 0, x1: {quad_xmax:.0f}, y0: {quad_median_y:.4f}, y1: {quad_median_y:.4f},
      line: {{color: '{COLOR_ASH}', width: 1, dash: 'dot'}}}},
    {{type: 'line', x0: {quad_median_x:.1f}, x1: {quad_median_x:.1f}, y0: 0, y1: 1,
      line: {{color: '{COLOR_ASH}', width: 1, dash: 'dot'}}}}
  ],
  annotations: [
    {{x: 0.02, xref: 'x', y: 0.97, yref: 'y', xanchor: 'left', showarrow: false,
      text: '小池高损 · 清积压', font: {{size: 11, color: '{COLOR_NEG}'}}}},
    {{x: {quad_xmax:.0f}, xref: 'x', y: 0.97, yref: 'y', xanchor: 'right', showarrow: false,
      text: '大池高损 · 最高风险', font: {{size: 11, color: '{COLOR_NEG}'}}}},
    {{x: 0.02, xref: 'x', y: 0.02, yref: 'y', xanchor: 'left', showarrow: false,
      text: '小池低损 · 最健康', font: {{size: 11, color: '{COLOR_POS}'}}}},
    {{x: {quad_xmax:.0f}, xref: 'x', y: 0.02, yref: 'y', xanchor: 'right', showarrow: false,
      text: '大池低损 · 兑现把握高', font: {{size: 11, color: '{COLOR_POS}'}}}}
  ]
}});
</script>
</body>
</html>
"""


def main():
    args = parse_args()
    cmd = "python " + " ".join(sys.argv)

    df_all = load_data()
    as_of_default = df_all["lock_time"].max().normalize()
    as_of = pd.Timestamp(args.as_of) if args.as_of else as_of_default

    rdf = compute_history(as_of)
    if rdf.empty:
        sys.exit("❌ 无历史观察点数据")

    launches = [l for l in load_launches() if l["start"] <= as_of]
    snap = build_snapshot(rdf, launches)

    if args.format == "terminal":
        print(format_terminal(snap))
        return
    if args.format == "json":
        print(json.dumps(snap, ensure_ascii=False, indent=2))
        return

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    html = render_html(snap, str(as_of.date()), _static_prefix(out_dir))
    out_path = out_dir / f"launch_risk_snapshot_{as_of:%Y%m%d}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"✅ 报告已生成: {out_path}")


if __name__ == "__main__":
    main()
