"""
所有权转移分析报告 — 基于 ownership_transfer_analysis.py 输出生成 HTML 报告.

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


def _series_breakdown(s: str) -> str:
    """Convert series count string like 'L6=7, LS6=147' to HTML badges."""
    if not s:
        return ''
    parts = []
    for item in s.split(', '):
        k, v = item.split('=')
        parts.append(f'<span class="series-badge">{k}</span> <strong>{v}</strong>')
    return ', '.join(parts)


def _add_tree_rows(nodes, depth=0, parent_label=None):
    """Recursively build table rows for the tree structure."""
    rows = ''
    for i, node in enumerate(nodes):
        label, count, series, children = node
        is_last = i == len(nodes) - 1
        indent = depth * 24
        branch_class = ''
        is_leaf = not children

        if depth == 0:
            section_class = 'tree-root'
        elif depth == 1:
            section_class = 'tree-branch'
        elif depth == 2:
            section_class = 'tree-leaf'
        else:
            section_class = 'tree-twig'

        if parent_label == '国内' and is_last:
            section_class += ' row-highlight'

        rows += f'''
        <tr class="tree-row {section_class}">
          <td style="padding-left:{indent + 12}px;">
            <span class="tree-marker">{"└ " if is_leaf and depth > 0 else ""}{label}</span>
          </td>
          <td class="num">{count:,}</td>
          <td class="series-cell">{_series_breakdown(series)}</td>
        </tr>'''

        if children:
            rows += _add_tree_rows(children, depth + 1, label)
    return rows


def build_html():
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    tree = [
        ("出口", 9005, "", [
            ("上汽国际", 8064, "", []),
            ("海外", 832, "", []),
            ("亚洲", 69, "", []),
            ("T F Motors (Cambodia) Co., Ltd", 23, "", []),
            ("Momenta Europe GmbH.", 14, "", []),
            ("VISION START ME -FZCO 阿尔巴尼亚", 3, "", []),
        ]),
        ("国内", 31082, "", [
            ("物流前阶段（未进入 VDC）", 230, "L6=7, LS6=147, LS7=1, LS8=57, LS9=18", []),
            ("VDC 内", 5, "LS6=5", []),
            ("VDC→DC 在途", 24, "L6=4, LS6=15, LS8=3, LS9=2", []),
            ("DC 在库", 6759, "L6=550, L7=7, LS6=2566, LS7=18, LS8=2541, LS9=1077", [
            ]),
            ("已离开 DC", 24064, "L6=1938, L7=13, LS6=8008, LS7=45, LS8=7182, LS9=6878", [
                ("消费者交付完成", 23961, "L6=1935, L7=13, LS6=7974, LS7=44, LS8=7150, LS9=6845", []),
                ("非零售业务交付", 103, "L6=3, LS6=34, LS7=1, LS8=32, LS9=33", []),
            ]),
        ]),
    ]

    series_data = {
        '总量': 40087,
        '出口': 9005,
        '国内': 31082,
        '消费者交付完成': 23961,
        '非零售业务交付': 103,
        'DC 在库': 6759,
        '物流前阶段': 230,
    }

    tree_rows = _add_tree_rows(tree)

    total_export = 9005
    total_domestic = 31082
    total = 40087
    delivery_rate = round(23961 / total_domestic * 100, 1)
    export_pct = round(total_export / total * 100, 1)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>车辆流转与交付状态 — 2026 H1</title>
  <link rel="stylesheet" href="{STATIC_PREFIX}/templates/report_style.css" />
  <style>
    .tree-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    .tree-table th {{
      text-align: left;
      font-size: 12px;
      font-weight: 600;
      color: var(--zh-deep-blue);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      padding: 10px 12px;
      background: var(--zh-panel);
      border-bottom: 2px solid var(--zh-blue);
    }}
    .tree-table td {{
      padding: 8px 12px;
      border-bottom: 1px solid var(--zh-border);
    }}
    .tree-table .num {{
      font-variant-numeric: tabular-nums;
      font-weight: 700;
      text-align: right;
      width: 100px;
    }}
    .tree-table .series-cell {{
      width: 280px;
      font-size: 13px;
      color: var(--zh-text);
    }}
    .tree-row.tree-root td {{
      font-weight: 700;
      color: var(--zh-deep-blue);
      background: var(--zh-table-section);
    }}
    .tree-row.tree-branch td {{
      font-weight: 600;
      color: var(--zh-blue);
    }}
    .tree-row.tree-leaf td {{
      color: var(--zh-text);
    }}
    .tree-row.tree-twig td {{
      color: var(--zh-muted);
      font-size: 13px;
    }}
    .tree-row.row-highlight td {{
      background: var(--zh-table-section);
    }}
    .tree-row.row-highlight td:first-child {{
      border-left: 3px solid var(--zh-blue);
    }}
    .tree-marker {{
      font-size: 13px;
    }}
    .series-badge {{
      display: inline-block;
      font-size: 11px;
      font-weight: 600;
      color: var(--zh-blue);
      background: rgba(23,74,124,.08);
      padding: 1px 6px;
      border-radius: 4px;
      margin-right: 2px;
    }}
    .validation-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 16px;
    }}
    .validation-card {{
      background: var(--zh-panel);
      border-radius: 8px;
      padding: 16px;
      font-size: 13px;
    }}
    .validation-card h4 {{
      font-size: 13px;
      font-weight: 600;
      color: var(--zh-deep-blue);
      margin-bottom: 8px;
    }}
    .validation-card .check-row {{
      display: flex;
      justify-content: space-between;
      padding: 4px 0;
      border-bottom: 1px solid var(--zh-border);
    }}
    .validation-card .check-row:last-child {{
      border-bottom: none;
    }}
    .validation-card .check-label {{
      color: var(--zh-muted);
    }}
    .validation-card .check-value {{
      font-weight: 600;
    }}
    .check-pass {{ color: var(--status-positive); }}
    .check-warn {{ color: var(--status-warning); }}
    .check-fail {{ color: var(--status-negative); }}
    .flow-card {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 16px;
      background: var(--zh-card);
      border-radius: 8px;
      box-shadow: 0 1px 4px rgba(6,33,61,.06);
      border-left: 4px solid var(--zh-blue);
    }}
    .flow-card .flow-label {{
      font-size: 13px;
      color: var(--zh-muted);
    }}
    .flow-card .flow-value {{
      font-size: 18px;
      font-weight: 700;
      color: var(--zh-deep-blue);
    }}
    .flow-chain {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      padding: 16px 0;
    }}
    .flow-step {{
      text-align: center;
      min-width: 80px;
    }}
    .flow-step .step-count {{
      font-size: 16px;
      font-weight: 700;
      color: var(--zh-deep-blue);
    }}
    .flow-step .step-label {{
      font-size: 11px;
      color: var(--zh-muted);
      margin-top: 2px;
    }}
    .flow-arrow {{
      color: var(--zh-border);
      font-size: 18px;
    }}
    @media (max-width: 640px) {{
      .flow-chain {{ flex-direction: column; align-items: flex-start; }}
      .flow-arrow {{ transform: rotate(90deg); }}
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
    <h1>车辆流转与交付状态分析</h1>
    <p>2026 H1 · bloc_name 归属口径 · 品牌归属 + 终端完成收窄</p>
  </section>

  <div class="summary-grid">
    <div class="summary-card positive">
      <div class="summary-value">{total:,}</div>
      <div class="summary-label">归属总量（含出口）</div>
      <div class="summary-hint">2026-01-01 ~ 2026-06-30</div>
    </div>
    <div class="summary-card">
      <div class="summary-value">{total_domestic:,}</div>
      <div class="summary-label">国内</div>
      <div class="summary-hint">{export_pct}% 出口</div>
    </div>
    <div class="summary-card neutral">
      <div class="summary-value">{total_export:,}</div>
      <div class="summary-label">出口</div>
      <div class="summary-hint">上汽国际 + 海外等 6 个渠道</div>
    </div>
    <div class="summary-card positive">
      <div class="summary-value">{23961:,}</div>
      <div class="summary-label">消费者交付完成</div>
      <div class="summary-hint">国内交付率 {delivery_rate}%</div>
    </div>
    <div class="summary-card warning">
      <div class="summary-value">{6759:,}</div>
      <div class="summary-label">DC 在库</div>
      <div class="summary-hint">LS6={2566} · LS8={2541} · LS9={1077} · L6={550}</div>
    </div>
    <div class="summary-card neutral">
      <div class="summary-value">{103:,}</div>
      <div class="summary-label">非零售业务交付</div>
      <div class="summary-hint">占国内已离开 DC 的 0.4%</div>
    </div>
  </div>

  <div class="card">
    <h2>物流链路总览</h2>
    <div class="flow-chain">
      <div class="flow-step">
        <div class="step-count">{230:,}</div>
        <div class="step-label">物流前</div>
      </div>
      <span class="flow-arrow">→</span>
      <div class="flow-step">
        <div class="step-count">{5:,}</div>
        <div class="step-label">VDC 内</div>
      </div>
      <span class="flow-arrow">→</span>
      <div class="flow-step">
        <div class="step-count">{24:,}</div>
        <div class="step-label">在途</div>
      </div>
      <span class="flow-arrow">→</span>
      <div class="flow-step" style="border-left:3px solid var(--status-warning);padding-left:12px;">
        <div class="step-count">{6759:,}</div>
        <div class="step-label">DC 在库</div>
      </div>
      <span class="flow-arrow">→</span>
      <div class="flow-step" style="border-left:3px solid var(--status-positive);padding-left:12px;">
        <div class="step-count">{24064:,}</div>
        <div class="step-label">已离开 DC</div>
      </div>
    </div>
    <p class="section-note">
      验算：国内 {total_domestic:,} = 物流前 230 + VDC 内 5 + 在途 24 + DC 在库 6,759 + 已离开 DC 24,064
    </p>
  </div>

  <div class="card">
    <h2>树形结构 · 车辆归属与流转</h2>
    <div class="table-wrap">
      <table class="tree-table">
        <thead>
          <tr>
            <th style="width:50%;">节点</th>
            <th style="width:15%;text-align:right;">数量</th>
            <th style="width:35%;">车系分布</th>
          </tr>
        </thead>
        <tbody>
          {tree_rows}
        </tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <h2>非零售业务交付可靠性校验</h2>
    <div class="validation-grid">
      <div class="validation-card">
        <h4>基本数量</h4>
        <div class="check-row">
          <span class="check-label">非零售业务交付数量</span>
          <span class="check-value">103</span>
        </div>
        <div class="check-row">
          <span class="check-label">物流链路完整（7 步全）</span>
          <span class="check-value check-pass">100 / 103</span>
        </div>
        <div class="check-row">
          <span class="check-label">订单系统零痕迹</span>
          <span class="check-value check-pass">103 / 103</span>
        </div>
      </div>
      <div class="validation-card">
        <h4>链路断点</h4>
        <div class="check-row">
          <span class="check-label">schedule_effective_time 缺失</span>
          <span class="check-value check-warn">3</span>
        </div>
        <div class="check-row">
          <span class="check-label">其余 6 步（下线→QC→入库→出库→DC→交付）</span>
          <span class="check-value check-pass">0 缺失</span>
        </div>
        <div class="check-row">
          <span class="check-label">交付完成</span>
          <span class="check-value" style="font-weight:600;color:var(--status-positive);">23,961 辆</span>
        </div>
      </div>
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
          <tr><td>上汽国际</td><td class="num">8,064</td><td class="num">89.6%</td></tr>
          <tr><td>海外</td><td class="num">832</td><td class="num">9.2%</td></tr>
          <tr><td>亚洲</td><td class="num">69</td><td class="num">0.8%</td></tr>
          <tr><td>T F Motors (Cambodia) Co., Ltd</td><td class="num">23</td><td class="num">0.3%</td></tr>
          <tr><td>Momenta Europe GmbH.</td><td class="num">14</td><td class="num">0.2%</td></tr>
          <tr><td>VISION START ME -FZCO 阿尔巴尼亚</td><td class="num">3</td><td class="num">&lt;0.1%</td></tr>
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
          2026-01-01 ~ 2026-06-30（含当日）
        </div>
      </div>
      <div class="method-item">
        <div class="method-icon" style="background:#E8F8FD;color:#2D6FA3;">F</div>
        <div class="method-body">
          <strong>过滤条件</strong><br/>
          dispatched 模式：剔除上汽销售 + 已绑定待开票 + 有开票无交付记录
        </div>
      </div>
      <div class="method-item">
        <div class="method-icon" style="background:#F3F6F8;color:#374151;">M</div>
        <div class="method-body">
          <strong>口径定义</strong><br/>
          消费者交付完成 → 已离开 DC，且存在交付记录<br/>
          非零售业务交付 → 已离开 DC，未关联消费者订单，但具备实际物流流转记录<br/>
          已绑定待开票 → 已离开 DC、有订单绑定，无开票且无交付记录（已排除）<br/>
          待核查 → 已离开 DC、有开票记录但无交付记录（已排除）
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
