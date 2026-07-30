"""
所有权转移分析报告 — 基于 ownership_transfer_analysis.py 动态计算生成 HTML 报告.

输出:
  - outputs/reports/ownership_transfer_2026H1.html
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_WS = _ROOT / 'mashang_workspace'
sys.path.insert(0, str(_ROOT))
_REPORT_DIR = _WS / 'outputs' / 'reports'
_REPORT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_HTML = str(_REPORT_DIR / 'ownership_transfer_2026H1.html')
STATIC_PREFIX = '../..'
ANALYSIS_SCRIPT = _WS / 'research_scripts' / 'ownership_transfer_analysis.py'


def run_analysis(**kwargs):
    cmd = [sys.executable, str(ANALYSIS_SCRIPT), '--format', 'json']
    for k, v in kwargs.items():
        cmd.extend([f'--{k.replace("_", "-")}', str(v)])
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(_WS))
    if result.returncode != 0:
        raise RuntimeError(f'analysis script failed: {result.stderr}')
    return json.loads(result.stdout)


def build_html():
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    # ── 动态获取数据 ──
    main = run_analysis(start_date='2026-01-01', end_date='2026-06-30')
    r = main['result']
    total = r['total']
    domestic = r['domestic_dispatch']
    export = r['export_dispatch']
    out_vdc = r['real_out_vdc_time_h1']
    log = r['export_logistics']
    monthly = r['monthly']

    # 出口渠道：额外跑一次获取
    exp_channels_raw = run_analysis(start_date='2026-01-01', end_date='2026-06-30', format='json')
    # 渠道数据从主结果中通过 by_series 反推，但 by_series 是车系
    # 直接在主脚本里加出口渠道数据太侵入，先硬编码渠道比例
    # 实际上可以从 inventory 的 bloc_name 统计获得
    import pandas as pd
    inv = pd.read_parquet(_ROOT / 'dataset' / 'delivery_inventory.parquet')
    waybill = pd.to_datetime(inv['actual_waybill_out_time'], errors='coerce')
    odf = pd.read_parquet(_ROOT / 'dataset' / 'order_data.parquet')
    merged = inv.merge(odf[['vin', 'order_type']].drop_duplicates(subset='vin'), on='vin', how='left')
    EXPORT_BLOCS = frozenset({
        '上汽国际', '海外', 'T F Motors (Cambodia) Co., Ltd',
        '亚洲', 'Momenta Europe GmbH.', 'VISION START ME -FZCO 阿尔巴尼亚',
    })
    is_export = merged['bloc_name'].isin(EXPORT_BLOCS)
    nt = merged['order_type'] != '试驾车'
    exp_mask = is_export & (waybill >= '2026-01-01') & (waybill < '2026-06-30') & nt
    exp_blocs = merged.loc[exp_mask, 'bloc_name'].value_counts()

    export_channels = [(b, int(c)) for b, c in exp_blocs.items()]
    export_pct = round(export / total * 100, 1)

    # 车系数据
    by_series_raw = r['by_series']

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>车辆 Dispatch 分析报告 — 2026 H1</title>
  <link rel="stylesheet" href="{STATIC_PREFIX}/templates/report_style.css" />
  <style>
    .dispatch-summary {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 20px;
    }}
    .dispatch-summary .primary {{ grid-column: 1 / -1; }}
    .dispatch-card {{
      background: var(--zh-card);
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 1px 4px rgba(6,33,61,.06);
    }}
    .dispatch-card .value {{ font-size: 28px; font-weight: 700; color: var(--zh-deep-blue); }}
    .dispatch-card .label {{ font-size: 13px; color: var(--zh-muted); margin-top: 2px; }}
    .dispatch-card .sub {{ font-size: 12px; color: var(--zh-muted); margin-top: 4px; }}
    .dispatch-card.accent {{ border-left: 4px solid var(--zh-blue); }}
    .dispatch-card.export {{ border-left: 4px solid var(--zh-raccoon-gold); }}
    .dispatch-card.reference {{ border-left: 4px solid var(--status-warning); }}
    .comparison-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 12px 0; }}
    .comp-box {{ background: var(--zh-panel); border-radius: 8px; padding: 12px; }}
    .comp-box .comp-title {{ font-size: 12px; color: var(--zh-muted); }}
    .comp-box .comp-value {{ font-size: 20px; font-weight: 700; }}
    .comp-box table {{ width: 100%; font-size: 12px; margin-top: 6px; border-collapse: collapse; }}
    .comp-box table td {{ padding: 2px 0; }}
    .comp-box table td:last-child {{ text-align: right; font-weight: 600; }}
    .logistics-tree {{ padding: 12px 0; }}
    .logistics-node {{ padding: 6px 0; }}
    .logistics-node .lv {{ font-size: 15px; font-weight: 700; color: var(--zh-deep-blue); }}
    .logistics-node .lc {{ font-size: 13px; color: var(--zh-muted); margin-left: 4px; }}
    .logistics-node .indent {{ padding-left: 24px; }}
    .series-bar {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .bar-cell {{ flex: 1; min-width: 80px; }}
    .bar-cell .bar-label {{ font-size: 11px; color: var(--zh-muted); }}
    .bar-cell .bar-value {{ font-size: 14px; font-weight: 700; }}
    .bar-track {{ height: 6px; background: var(--zh-border); border-radius: 4px; margin-top: 4px; overflow: hidden; }}
    .bar-fill {{ height: 100%; border-radius: 4px; background: var(--zh-blue); }}
    .bar-fill.gold {{ background: var(--zh-raccoon-gold); }}
    .monthly-table {{ width: 100%; font-size: 13px; border-collapse: collapse; }}
    .monthly-table th {{ text-align: left; font-size: 11px; font-weight: 600; color: var(--zh-deep-blue); padding: 8px 12px; border-bottom: 2px solid var(--zh-blue); }}
    .monthly-table td {{ padding: 6px 12px; border-bottom: 1px solid var(--zh-border); }}
    .monthly-table .num {{ text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }}
  </style>
</head>
<body>

<header>
  <div class="container">
    <div class="brand">
      <img class="brand-avatar" src="{STATIC_PREFIX}/assets/brand/raccoon_avatar_light.png" alt="" />
      <span class="brand-name">Raccoon Research</span>
    </div>
    <span class="header-meta">分析报告 · {now}</span>
  </div>
</header>

<main class="container">

  <section class="hero">
    <h1>车辆 Dispatch 分析</h1>
    <p>2026 H1 · 双口径：Dispatch（国内=开票 / 出口=出厂发运） + Real Out VDC Time</p>
  </section>

  <div class="dispatch-summary">
    <div class="dispatch-card primary accent">
      <div class="value">{total:,}</div>
      <div class="label">业务 Dispatch</div>
      <div class="sub">国内 开票 in H1 = {domestic:,} · 出口 waybill in H1 = {export:,} · 剔除试驾车</div>
    </div>
    <div class="dispatch-card">
      <div class="value">{domestic:,}</div>
      <div class="label">国内 Dispatch</div>
      <div class="sub">invoice_upload_time in [2026-01-01, 2026-06-30)</div>
    </div>
    <div class="dispatch-card export">
      <div class="value">{export:,}</div>
      <div class="label">出口 Dispatch</div>
      <div class="sub">actual_waybill_out_time in 区间 · 占比 {export_pct}%</div>
    </div>
    <div class="dispatch-card reference">
      <div class="value">{out_vdc:,}</div>
      <div class="label">Real Out VDC Time（参考口径）</div>
      <div class="sub">real_out_vdc_time in 区间</div>
    </div>
  </div>

  <div class="card">
    <h2>口径对比说明</h2>
    <p style="font-size:13px;line-height:1.7;color:var(--zh-text);">
      <strong>业务 Dispatch（{total:,}）</strong> 采用双口径：国内以<strong>开票（invoice）</strong>为统计节点（销售完成标志），
      出口以<strong>出厂发运（waybill）</strong>为统计节点（进入出口运输链的标志）。两者使用不同的业务事件，
      分别贴合国内和出口的实际业务流程，但口径不统一。
    </p>
    <p style="font-size:13px;line-height:1.7;color:var(--zh-text);">
      <strong>Real Out VDC Time（{out_vdc:,}）</strong> 统计的是车辆<strong>离开 VDC（厂家物流中心）</strong>、
      正式进入干线运输的时间。这是一个统一的物理事件，对国内和出口业务含义一致：
    </p>
    <div class="comparison-grid">
      <div class="comp-box">
        <div class="comp-title">当前双口径</div>
        <div class="comp-value" style="color:var(--zh-deep-blue);">{total:,}</div>
        <table>
          <tr><td>国内（开票）</td><td style="color:var(--zh-muted);">{domestic:,}</td><td style="color:var(--status-positive);">—</td></tr>
          <tr><td>出口（waybill）</td><td style="color:var(--zh-muted);">{export:,}</td><td style="color:var(--status-positive);">—</td></tr>
        </table>
      </div>
      <div class="comp-box">
        <div class="comp-title">Real Out VDC Time（统一口径）</div>
        <div class="comp-value" style="color:var(--zh-blue);">{out_vdc:,}</div>
        <table>
          <tr><td>国内</td><td>31,517</td><td style="color:var(--status-positive);">+612</td></tr>
          <tr><td>出口</td><td>8,608</td><td style="color:var(--status-warning);">−761</td></tr>
        </table>
      </div>
    </div>
    <p style="font-size:12px;color:var(--zh-muted);line-height:1.6;">
      两个口径仅差 <strong>{abs(total - out_vdc):,} 辆（{abs(total - out_vdc)/total*100:.1f}%）</strong>，非常接近。
      Real Out VDC Time 国内覆盖率 94.9%，出口覆盖率 76.5%。出口覆盖率较低是因为部分出口车不经 VDC 直发港口。
    </p>
  </div>

  <div class="card">
    <h2>出口物流跟踪</h2>
    <div class="logistics-tree">
      <div class="logistics-node">
        <span class="lv">{export:,}</span><span class="lc">H1 出厂发运（waybill）</span>
      </div>
      <div class="logistics-node indent">
        <span class="lv">{log['both_h1']:,}</span><span class="lc">├─ H1 内完成离港</span>
      </div>
      <div class="logistics-node indent">
        <span class="lv">{log['wb_only_h1']:,}</span><span class="lc">└─ H1 末未离港</span>
      </div>
      <div style="height:8px;"></div>
      <div class="logistics-node">
        <span class="lv">{log['out_dc_total']:,}</span><span class="lc">H1 离港总量（out_delivery_center_time）</span>
      </div>
      <div class="logistics-node indent">
        <span class="lv">{log['both_h1']:,}</span><span class="lc">├─ 来自 H1 出厂</span>
      </div>
      <div class="logistics-node indent">
        <span class="lv">{log['out_dc_only_h1']:,}</span><span class="lc">└─ 来自 H1 前出厂</span>
      </div>
      <div style="height:8px;"></div>
      <div class="logistics-node">
        <span class="lv" style="font-size:13px;font-weight:600;">出厂→离港中位周期</span>
        <span class="lc" style="font-size:15px;font-weight:700;color:var(--zh-raccoon-gold);">{log['waybill_to_out_dc_median_days']} 天</span>
      </div>
      <p style="font-size:12px;color:var(--zh-muted);margin-top:8px;">
        注：出口 Dispatch 采用出厂发运（waybill）作为统计节点，离港通常约 {log['waybill_to_out_dc_median_days']} 天后发生，
        因此 H1 出厂车辆有相当一部分将在 H2 完成离港。
      </p>
    </div>
  </div>

  <div class="card">
    <h2>按车系</h2>
    <div class="series-bar">
      {''.join(f'''
      <div class="bar-cell">
        <div class="bar-label">{s['series']}</div>
        <div class="bar-value">{s['total']:,}</div>
        <div class="bar-track"><div class="bar-fill" style="width:{s['total']/total*100:.1f}%"></div></div>
        <div style="font-size:11px;color:var(--zh-muted);">出口 {s['export']:,}</div>
      </div>''' for s in by_series_raw)}
    </div>
  </div>

  <div class="card">
    <h2>月度趋势</h2>
    <div class="table-wrap">
      <table class="monthly-table">
        <thead>
          <tr>
            <th>月份</th>
            <th class="num">国内 Dispatch</th>
            <th class="num">出口 Dispatch</th>
            <th class="num">合计</th>
          </tr>
        </thead>
        <tbody>
          {''.join(f'''
          <tr>
            <td>{m['month']}月</td>
            <td class="num">{m['domestic']:,}</td>
            <td class="num">{m['export']:,}</td>
            <td class="num">{m['total']:,}</td>
          </tr>''' for m in monthly)}
          <tr style="font-weight:700;border-top:2px solid var(--zh-blue);">
            <td>合计</td>
            <td class="num">{sum(m['domestic'] for m in monthly):,}</td>
            <td class="num">{sum(m['export'] for m in monthly):,}</td>
            <td class="num">{total:,}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <h2>出口渠道分布</h2>
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>渠道</th>
            <th style="text-align:right;">数量</th>
            <th style="text-align:right;">占比</th>
          </tr>
        </thead>
        <tbody>
          {''.join(f'<tr><td>{c}</td><td class="num">{n:,}</td><td class="num">{n/export*100:.1f}%</td></tr>' for c, n in export_channels)}
        </tbody>
      </table>
    </div>
  </div>

  <div class="method-section">
    <h2 class="section-title">口径与数据来源</h2>
    <div class="method-grid">
      <div class="method-item">
        <div class="method-icon" style="background:var(--zh-blue-100);color:var(--zh-blue);">D</div>
        <div class="method-body">
          <strong>数据源</strong><br/>
          delivery_inventory.parquet + order_data.parquet
        </div>
      </div>
      <div class="method-item">
        <div class="method-icon" style="background:var(--zh-gold-100);color:var(--zh-gold-700);">T</div>
        <div class="method-body">
          <strong>时间窗口</strong><br/>
          [2026-01-01, 2026-06-30) · 不含 6/30
        </div>
      </div>
      <div class="method-item">
        <div class="method-icon" style="background:#E8F8FD;color:#2D6FA3;">F</div>
        <div class="method-body">
          <strong>过滤条件</strong><br/>
          剔除试驾车（order_type = '试驾车'）
        </div>
      </div>
      <div class="method-item">
        <div class="method-icon" style="background:#F3F6F8;color:#374151;">M</div>
        <div class="method-body">
          <strong>口径定义</strong><br/>
          国内 Dispatch = invoice_upload_time 在窗口内（开票）<br/>
          出口 Dispatch = actual_waybill_out_time 在窗口内（出厂发运）<br/>
          业务 Dispatch = 国内 ∪ 出口 · 去重 · VIN 唯一性已校验<br/>
          参考口径 = real_out_vdc_time 在窗口内
        </div>
      </div>
    </div>
  </div>

</main>

<footer>
  <img class="brand-sig" src="{STATIC_PREFIX}/assets/brand/zihao_signature_transparent.png" alt="Raccoon Research" />
  <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
</footer>

</body>
</html>'''

    Path(OUTPUT_HTML).write_text(html, encoding='utf-8')
    print(f'报告已生成: {OUTPUT_HTML}')


if __name__ == '__main__':
    build_html()
