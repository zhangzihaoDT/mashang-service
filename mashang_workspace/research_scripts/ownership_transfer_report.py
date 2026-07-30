"""
所有权转移分析报告 — 基于 ownership_transfer_analysis.py 双口径输出生成 HTML 报告.

输出:
  - outputs/reports/ownership_transfer_2026H1.html
"""

import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_REPORT_DIR = _ROOT / 'outputs' / 'reports'
_REPORT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_HTML = str(_REPORT_DIR / 'ownership_transfer_2026H1.html')
STATIC_PREFIX = '../..'

# ── 核心数据（从 ownership_transfer_analysis.py 2026 H1 输出） ──
DATA = {
    'total': 40274,
    'domestic': 30905,
    'export': 9369,
    'real_out_vdc': 40125,
    'export_logistics': {
        'both_h1': 2851,
        'wb_only_h1': 6518,
        'out_dc_total': 5690,
        'out_dc_only_h1': 2839,
    },
    'median_days': 76,
    'export_channels': [
        ('上汽国际', 8424, 'https://www.saicmotor.com'),
        ('海外', 825, ''),
        ('亚洲', 54, ''),
        ('T F Motors (Cambodia)', 23, ''),
        ('Momenta Europe GmbH.', 14, ''),
        ('VISION START ME -FZCO', 0, ''),
    ],
    'by_series': [
        ('LS6', 13947, 4186),
        ('LS9', 7734, 34),
        ('L6', 2904, 5139),
        ('LS8', 6110, 2),
        ('LS7', 135, 8),
        ('L7', 75, 0),
    ],
    'monthly': [
        (1, 4115, 1867),
        (2, 2935, 1381),
        (3, 4333, 712),
        (4, 6716, 1944),
        (5, 7477, 1792),
        (6, 5329, 1673),
    ],
}

export_pct = round(DATA['export'] / DATA['total'] * 100, 1)

now = datetime.now().strftime('%Y-%m-%d %H:%M')

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
    .dispatch-summary .primary {{
      grid-column: 1 / -1;
    }}
    .dispatch-card {{
      background: var(--zh-card);
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 1px 4px rgba(6,33,61,.06);
    }}
    .dispatch-card .value {{
      font-size: 28px;
      font-weight: 700;
      color: var(--zh-deep-blue);
    }}
    .dispatch-card .label {{
      font-size: 13px;
      color: var(--zh-muted);
      margin-top: 2px;
    }}
    .dispatch-card .sub {{
      font-size: 12px;
      color: var(--zh-muted);
      margin-top: 4px;
    }}
    .dispatch-card.accent {{
      border-left: 4px solid var(--zh-blue);
    }}
    .dispatch-card.export {{
      border-left: 4px solid var(--zh-raccoon-gold);
    }}
    .dispatch-card.reference {{
      border-left: 4px solid var(--status-warning);
    }}
    .logistics-tree {{
      padding: 12px 0;
    }}
    .logistics-node {{
      padding: 6px 0;
    }}
    .logistics-node .lv {{
      font-size: 15px;
      font-weight: 700;
      color: var(--zh-deep-blue);
    }}
    .logistics-node .lc {{
      font-size: 13px;
      color: var(--zh-muted);
      margin-left: 4px;
    }}
    .logistics-node .indent {{
      padding-left: 24px;
    }}
    .logistics-node .indent2 {{
      padding-left: 48px;
    }}
    .pill {{
      display: inline-block;
      font-size: 11px;
      font-weight: 600;
      color: var(--zh-blue);
      background: rgba(23,74,124,.08);
      padding: 1px 8px;
      border-radius: 10px;
      margin: 2px;
    }}
    .series-bar {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }}
    .bar-cell {{
      flex: 1;
      min-width: 80px;
    }}
    .bar-cell .bar-label {{
      font-size: 11px;
      color: var(--zh-muted);
    }}
    .bar-cell .bar-value {{
      font-size: 14px;
      font-weight: 700;
    }}
    .bar-track {{
      height: 6px;
      background: var(--zh-border);
      border-radius: 4px;
      margin-top: 4px;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      border-radius: 4px;
      background: var(--zh-blue);
    }}
    .bar-fill.gold {{ background: var(--zh-raccoon-gold); }}
    .monthly-table {{
      width: 100%;
      font-size: 13px;
      border-collapse: collapse;
    }}
    .monthly-table th {{
      text-align: left;
      font-size: 11px;
      font-weight: 600;
      color: var(--zh-deep-blue);
      padding: 8px 12px;
      border-bottom: 2px solid var(--zh-blue);
    }}
    .monthly-table td {{
      padding: 6px 12px;
      border-bottom: 1px solid var(--zh-border);
    }}
    .monthly-table .num {{
      text-align: right;
      font-variant-numeric: tabular-nums;
      font-weight: 600;
    }}
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
      <div class="value">{DATA['total']:,}</div>
      <div class="label">业务 Dispatch</div>
      <div class="sub">国内 开票 in H1 = {DATA['domestic']:,} · 出口 waybill in H1 = {DATA['export']:,} · 剔除试驾车</div>
    </div>
    <div class="dispatch-card">
      <div class="value">{DATA['domestic']:,}</div>
      <div class="label">国内 Dispatch</div>
      <div class="sub">invoice_upload_time in [2026-01-01, 2026-06-30)</div>
    </div>
    <div class="dispatch-card export">
      <div class="value">{DATA['export']:,}</div>
      <div class="label">出口 Dispatch</div>
      <div class="sub">actual_waybill_out_time in 区间 · 占比 {export_pct}%</div>
    </div>
    <div class="dispatch-card reference">
      <div class="value">{DATA['real_out_vdc']:,}</div>
      <div class="label">Real Out VDC Time（参考口径）</div>
      <div class="sub">real_out_vdc_time in 区间 · 不含试驾车</div>
    </div>
  </div>

  <div class="card">
    <h2>出口物流跟踪</h2>
    <div class="logistics-tree">
      <div class="logistics-node">
        <span class="lv">{DATA['export']:,}</span><span class="lc">H1 出厂发运（waybill）</span>
      </div>
      <div class="logistics-node indent">
        <span class="lv">{DATA['export_logistics']['both_h1']:,}</span><span class="lc">├─ H1 内完成离港</span>
      </div>
      <div class="logistics-node indent">
        <span class="lv">{DATA['export_logistics']['wb_only_h1']:,}</span><span class="lc">└─ H1 末未离港</span>
      </div>
      <div style="height:8px;"></div>
      <div class="logistics-node">
        <span class="lv">{DATA['export_logistics']['out_dc_total']:,}</span><span class="lc">H1 离港总量（out_delivery_center_time）</span>
      </div>
      <div class="logistics-node indent">
        <span class="lv">{DATA['export_logistics']['both_h1']:,}</span><span class="lc">├─ 来自 H1 出厂</span>
      </div>
      <div class="logistics-node indent">
        <span class="lv">{DATA['export_logistics']['out_dc_only_h1']:,}</span><span class="lc">└─ 来自 H1 前出厂</span>
      </div>
      <div style="height:8px;"></div>
      <div class="logistics-node">
        <span class="lv" style="font-size:13px;font-weight:600;">出厂→离港中位周期</span>
        <span class="lc" style="font-size:15px;font-weight:700;color:var(--zh-raccoon-gold);">{DATA['median_days']} 天</span>
      </div>
      <p style="font-size:12px;color:var(--zh-muted);margin-top:8px;">
        注：出口 Dispatch 采用出厂发运（waybill）作为统计节点，离港通常约 {DATA['median_days']} 天后发生，
        因此 H1 出厂车辆有相当一部分将在 H2 完成离港。
      </p>
    </div>
  </div>

  <div class="card">
    <h2>按车系</h2>
    <div class="series-bar">
      {''.join(f'''
      <div class="bar-cell">
        <div class="bar-label">{s}</div>
        <div class="bar-value">{d:,}</div>
        <div class="bar-track"><div class="bar-fill" style="width:{d/DATA['total']*100:.1f}%"></div></div>
        <div style="font-size:11px;color:var(--zh-muted);">出口 {e:,}</div>
      </div>''' for s, d, e in DATA['by_series'])}
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
            <td>{m}月</td>
            <td class="num">{d:,}</td>
            <td class="num">{e:,}</td>
            <td class="num">{d+e:,}</td>
          </tr>''' for m, d, e in DATA['monthly'])}
          <tr style="font-weight:700;border-top:2px solid var(--zh-blue);">
            <td>合计</td>
            <td class="num">{sum(d for _,d,_ in DATA['monthly']):,}</td>
            <td class="num">{sum(e for _,_,e in DATA['monthly']):,}</td>
            <td class="num">{DATA['total']:,}</td>
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
          {''.join(f'<tr><td>{c}</td><td class="num">{n:,}</td><td class="num">{n/DATA["export"]*100:.1f}%</td></tr>' for c, n, _ in DATA['export_channels'] if n > 0)}
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
