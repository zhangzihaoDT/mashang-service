"""
竞争洞察 A3 人群流转分析 — 情报报告

数据源:
  - dataset/品牌 A3 流转.csv
  - dataset/TOP10A3 流转_懂车帝.csv
  - dataset/assign_data.csv
  - dataset/LS8A3流出T+7_0622.csv
  - dataset/LS8A3流出T+15_0622.csv

输出:
  - outputs/reports/竞争洞察A3人群流转.html
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from utils.plotly_theme import ZH, apply_zh_theme, align_dual_zero
_PROJECT_ROOT = _ROOT.parent

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_REPORT_DIR = _ROOT / 'outputs' / 'reports'
_REPORT_DIR.mkdir(parents=True, exist_ok=True)
_OUTPUT_HTML = str(_REPORT_DIR / '竞争洞察A3人群流转.html')

_EXTRA_MODELS = ['岚图', '零跑']


def _read_dataset(path: str) -> pd.DataFrame:
    full = _PROJECT_ROOT / path
    if not full.exists():
        raise FileNotFoundError(f"数据集不存在: {full}")
    return pd.read_csv(str(full))


def _build_table_html(title, df, time_label):
    """Build HTML data table with lightweight header and status colors."""
    rows_html = ''
    for _, r in df.iterrows():
        net = r['估算净流入'].replace(',', '')
        net_val = int(net) if net.lstrip('-').isdigit() else 0
        if net_val < 0:
            net_style = 'color:#D95F59;font-weight:600;'
        elif net_val > 0:
            net_style = 'color:#2A9D8F;font-weight:600;'
        else:
            net_style = ''
        is_key = any(m in r['车系'] for m in _EXTRA_MODELS)
        badge = '<span class="badge-key">关键</span>' if is_key else ''
        rows_html += (
            f'<tr>'
            f'<td style="text-align:center;font-weight:600;color:#5F6B7A;">{int(r.name)}</td>'
            f'<td>{r["车系"]}{badge}</td>'
            f'<td style="text-align:right;font-variant-numeric:tabular-nums;">{r["校准后流入"]}</td>'
            f'<td style="text-align:right;font-variant-numeric:tabular-nums;">{r["校准后流出"]}</td>'
            f'<td style="text-align:right;font-variant-numeric:tabular-nums;{net_style}">{r["估算净流入"]}</td>'
            f'<td style="text-align:right;color:#6B7280;">{r["流入流出比"]}</td>'
            f'</tr>\n'
        )
    return f'''
<div class="report-section">
  <h2>{title}</h2>
  <p class="section-note">{time_label}</p>
  <div class="table-wrap">
    <table class="report-table">
      <thead><tr>
        <th style="text-align:center;width:48px;">排名</th>
        <th style="text-align:left;">车系</th>
        <th style="text-align:right;">校准后流入</th>
        <th style="text-align:right;">校准后流出</th>
        <th style="text-align:right;min-width:100px;">估算净流入</th>
        <th style="text-align:right;min-width:80px;">流入流出比</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</div>
'''


def _build_method_note():
    return '''
<div class="method-section">
  <h2>指标体系与方法说明</h2>
  <div class="method-grid">
    <div class="method-item">
      <div class="method-icon" style="background:rgba(23,74,124,.1);color:#174A7C;">规</div>
      <div class="method-body">
        <strong>校准后流出</strong>看规模：本品 A3 流失主要去了哪些车型？
      </div>
    </div>
    <div class="method-item">
      <div class="method-icon" style="background:rgba(23,74,124,.1);color:#174A7C;">分</div>
      <div class="method-body">
        <strong>流失承接率</strong>看分布：某车型承接了本品总流失的多少比例？
      </div>
    </div>
    <div class="method-item">
      <div class="method-icon" style="background:rgba(215,154,54,.12);color:#A96F1F;">果</div>
      <div class="method-body">
        <strong>估算净流入</strong>看结果：哪些车型最终对本品是净增量还是净流失？
      </div>
    </div>
    <div class="method-item">
      <div class="method-icon" style="background:rgba(215,154,54,.12);color:#A96F1F;">压</div>
      <div class="method-body">
        <strong>流入流出比</strong>看压力：本品和该竞品之间的攻防压力是否失衡？
      </div>
    </div>
  </div>
  <p class="method-footnote">
    流入流出比 = A3流出指数 / A3流入指数。比值越高说明本品面对该竞品的防守压力越大，
    比值越低说明本品在该竞品人群中的吸引力更强。四个视角结合使用：规模看校准后流出，分布看流失承接率，结果看估算净流入，压力看流入流出比。
  </p>
  <p class="method-footnote" style="margin-top:12px;">
    算法参考：docs/双边校准算法_竞品流失归因报告.md · schema/business_definition.json（time_periods）
  </p>
</div>
'''


def _build_bar_colors(series, highlight_indices=None):
    """Return muted bar colors by default, only highlight key days."""
    colors = []
    for i, v in enumerate(series):
        if highlight_indices and i in highlight_indices:
            colors.append(ZH['negative'] if v < 0 else ZH['positive'])
        elif v < 0:
            colors.append('rgba(217,95,89,.45)')
        else:
            colors.append('rgba(42,157,143,.35)')
    return colors


# ── Data Loading ──
schema_path = _ROOT / 'schema' / 'business_definition.json'
if not schema_path.exists():
    schema_path = _PROJECT_ROOT / 'shared' / 'schema' / 'business_definition.json'
with open(str(schema_path)) as f:
    biz = json.load(f)

df = _read_dataset('dataset/品牌 A3 流转.csv')
df['日期'] = pd.to_datetime(df['日期'], format='%Y%m%d')
df = df.sort_values('日期')

dd = _read_dataset('dataset/TOP10A3 流转_懂车帝.csv')
dd['日期'] = pd.to_datetime(dd['日期'], format='%Y%m%d')
dd = dd.sort_values('日期')

df_max = df['日期'].max()
dd_max = dd['日期'].max()
periods_sorted = sorted(biz['time_periods'].items(), key=lambda x: x[1]['start'])
latest_pid = periods_sorted[-1][0]
total_net = df['净流入'].sum()
max_outflow_model = ''
net_days_positive = (df['净流入'] > 0).sum()
net_days_negative = (df['净流入'] < 0).sum()

# ── Correlation analysis ──
period_parts = []
for pid, prd in biz['time_periods'].items():
    start = pd.Timestamp(prd['start'])
    end = dd_max if pid == latest_pid else start + pd.Timedelta(days=80)
    mask = (dd['日期'] >= start) & (dd['日期'] <= end)
    if not mask.any():
        continue
    period_parts.append(dd.loc[mask].copy().sort_values('日期'))
period_df = pd.concat(period_parts, ignore_index=True).sort_values('日期')

assign = _read_dataset('dataset/assign_data.csv')
assign['日期'] = pd.to_datetime(assign['Assign Time 年/月/日'].str.replace('年', '-').str.replace('月', '-').str.replace('日', ''), format='%Y-%m-%d')
assign = assign.sort_values('日期')
assign = assign[(assign['日期'] >= period_df['日期'].min()) & (assign['日期'] <= period_df['日期'].max())].copy()
assign_delta = assign[['日期', '下发线索数']].copy()
assign_delta['下发线索数MA365'] = assign_delta['下发线索数'].rolling(365, min_periods=1).mean()
assign_delta['下发线索数Delta'] = assign_delta['下发线索数'] - assign_delta['下发线索数MA365']
merged = pd.merge(period_df[['日期', '净流入']], assign_delta[['日期', '下发线索数Delta']], on='日期', how='inner').sort_values('日期')

best_lag_p, best_pearson, best_lag_s, best_spearman = 0, 0, 0, 0
cross_corr = []
for lag in range(0, 31):
    shifted = merged['下发线索数Delta'].shift(-lag)
    valid = merged['净流入'].notna() & shifted.notna()
    if valid.sum() < 10:
        continue
    x = merged.loc[valid, '净流入']
    y = shifted.loc[valid]
    r_p = x.corr(y)
    r_s = x.rank().corr(y.rank())
    cross_corr.append((lag, r_p, r_s))
    if abs(r_p) > abs(best_pearson):
        best_pearson = r_p; best_lag_p = lag
    if abs(r_s) > abs(best_spearman):
        best_spearman = r_s; best_lag_s = lag

# ── Identify top outlier days for highlight ──
df['净流入_abs'] = df['净流入'].abs()
top_outliers = df.nlargest(5, '净流入_abs').index.tolist()

# ════════════════════════════════════════════
#  HTML HEAD
# ════════════════════════════════════════════
corr_summary = (
    f'Pearson r={best_pearson:.3f}（滞后{best_lag_p}天）· '
    f'Spearman ρ={best_spearman:.3f}（滞后{best_lag_s}天）'
)

html_head = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>竞争洞察 · A3 人群流转报告</title>
<link rel="stylesheet" href="../../templates/report_style.css">
</head>
<body class="report-page">
<div class="report-container">

<h1 class="report-title">竞争洞察 · A3 人群流转</h1>
<p class="report-subtitle">
  数据源：品牌 A3 流转 + 懂车帝 TOP10 · 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}
</p>

<div class="summary-grid">
  <div class="summary-card">
    <div class="summary-value" style="color:#174A7C;">{total_net:+,}</div>
    <div class="summary-label">期间累计净流入</div>
    <div class="summary-hint">品牌 A3 流转 · 正{net_days_positive}天 / 负{net_days_negative}天</div>
  </div>
  <div class="summary-card">
    <div class="summary-value" style="color:#4F6F82;">—</div>
    <div class="summary-label">最大承接车型</div>
    <div class="summary-hint">T+15 按估算净流入升序</div>
  </div>
  <div class="summary-card">
    <div class="summary-value" style="color:#174A7C;">{best_lag_p} 天</div>
    <div class="summary-label">最佳迟滞 (Pearson)</div>
    <div class="summary-hint">r = {best_pearson:.3f}</div>
  </div>
  <div class="summary-card">
    <div class="summary-value" style="color:#D79A36;">{best_lag_s} 天</div>
    <div class="summary-label">最佳迟滞 (Spearman)</div>
    <div class="summary-hint">ρ = {best_spearman:.3f}</div>
  </div>
</div>
'''

# ════════════════════════════════════════════
#  CHART 1: A3本流出 vs 竞品5A流入
# ════════════════════════════════════════════
fig1 = go.Figure()
fig1.add_trace(go.Scatter(x=df['日期'], y=df['本品A3流出'], mode='lines',
                           name='本品A3流出', line=dict(color=ZH['own'], width=2)))
fig1.add_trace(go.Scatter(x=df['日期'], y=df['竞争对手5A流入'], mode='lines',
                           name='竞争对手5A流入', line=dict(color=ZH['event'], width=2)))
fig1.update_layout(title=dict(text='本品A3流出 vs 竞争对手5A流入', x=0.5, font=dict(size=15)),
    width=1300, height=380, hovermode='x unified', legend=dict(x=1.02, xanchor='left'), margin=dict(t=50, b=40, r=120))
fig1.update_xaxes(dtick='M1', tickformat='%Y-%m')
apply_zh_theme(fig1)
chart1_html = fig1.to_html(full_html=False, include_plotlyjs='cdn')

html_section_1 = f'''
<div class="report-section">
  <h2>A3 流出总览</h2>
  <p class="section-note">本品 LS8 的 A3 人群流出与竞品 5A 流入的长期趋势对比。</p>
  <div class="chart-box"><div class="chart-wrap">{chart1_html}</div></div>
</div>
'''

# ════════════════════════════════════════════
#  CHART 2: 净流入 + 周期累计
# ════════════════════════════════════════════
fig2 = go.Figure()
bar_colors = _build_bar_colors(df['净流入'], highlight_indices=top_outliers)
fig2.add_trace(go.Bar(x=df['日期'], y=df['净流入'], name='净流入', marker_color=bar_colors,
                       hovertemplate='%{x|%Y-%m-%d}<br>净流入: %{y:,}<extra></extra>', yaxis='y'))

y2_all = np.array([])
for pid, prd in biz['time_periods'].items():
    start = pd.Timestamp(prd['start'])
    end = df_max if pid == latest_pid else start + pd.Timedelta(days=80)
    mask = (df['日期'] >= start) & (df['日期'] <= end)
    if not mask.any():
        continue
    p_df = df.loc[mask].copy().sort_values('日期')
    p_df['累计'] = p_df['净流入'].cumsum()
    y2_all = np.concatenate([y2_all, p_df['累计'].values])
    fig2.add_trace(go.Scatter(x=p_df['日期'], y=p_df['累计'], mode='lines',
        name=f'{pid} 累计', line=dict(color=ZH['ash'], width=2, dash='dash'), yaxis='y2',
        hovertemplate='%{x|%Y-%m-%d}<br>%{customdata}<br>累计: %{y:,}<extra></extra>', customdata=[pid]*len(p_df)))

fig2.update_layout(title=dict(text='每日净流入与周期累计', x=0.5, font=dict(size=15)),
    width=1300, height=380, hovermode='x unified', legend=dict(x=1.02, xanchor='left'), margin=dict(t=50, b=40, r=120),
    yaxis=dict(title='净流入'), yaxis2=dict(title='周期累计净流入', overlaying='y', side='right'))
fig2.update_xaxes(dtick='M1', tickformat='%Y-%m')
apply_zh_theme(fig2)
align_dual_zero(fig2, y1=df['净流入'].values, y2=y2_all)
chart2_html = fig2.to_html(full_html=False, include_plotlyjs=False)

html_section_2 = f'''
<div class="report-section">
  <h2>净流入趋势</h2>
  <p class="section-note">每日净流入（柱状图，低饱和 = 普通波动，高饱和 = Top 5 波动日）及周期累计线。</p>
  <div class="chart-box"><div class="chart-wrap">{chart2_html}</div></div>
</div>
'''

# ════════════════════════════════════════════
#  CHART 3: 懂车帝 · A3流出 vs 竞品流入
# ════════════════════════════════════════════
fig5 = go.Figure()
fig5.add_trace(go.Scatter(x=dd['日期'], y=dd['本品A3流出'], mode='lines',
                           name='本品A3流出', line=dict(color=ZH['own'], width=2)))
fig5.add_trace(go.Scatter(x=dd['日期'], y=dd['竞争对手5A流入'], mode='lines',
                           name='竞争对手5A流入', line=dict(color=ZH['event'], width=2)))
fig5.update_layout(title=dict(text='懂车帝 · 本品A3流出 vs 竞争对手5A流入', x=0.5, font=dict(size=15)),
    width=1300, height=350, hovermode='x unified', legend=dict(x=1.02, xanchor='left'), margin=dict(t=50, b=40, r=120))
fig5.update_xaxes(dtick='M1', tickformat='%Y-%m', hoverformat='%Y-%m-%d')
apply_zh_theme(fig5)
chart5_html = fig5.to_html(full_html=False, include_plotlyjs=False)

html_section_3 = f'''
<div class="report-section">
  <h2>懂车帝平台 · A3 流转对比</h2>
  <p class="section-note">懂车帝 TOP10 数据源，本品 A3 流出 vs 竞品 5A 流入的交叉验证。</p>
  <div class="chart-box"><div class="chart-wrap">{chart5_html}</div></div>
</div>
'''

# ════════════════════════════════════════════
#  CHART 4: 懂车帝 · 净流入
# ════════════════════════════════════════════
fig6 = go.Figure()
dd_top_outliers = dd.nlargest(5, '净流入_abs').index.tolist() if '净流入_abs' in dd.columns else []
dd_bar_colors = _build_bar_colors(dd['净流入'], highlight_indices=dd_top_outliers)
fig6.add_trace(go.Bar(x=dd['日期'], y=dd['净流入'], name='净流入', marker_color=dd_bar_colors,
                       hovertemplate='%{x|%Y-%m-%d}<br>净流入: %{y:,}<extra></extra>', yaxis='y'))

y6_all = np.array([])
for pid, prd in biz['time_periods'].items():
    start = pd.Timestamp(prd['start'])
    end = dd_max if pid == latest_pid else start + pd.Timedelta(days=80)
    mask = (dd['日期'] >= start) & (dd['日期'] <= end)
    if not mask.any():
        continue
    p_df = dd.loc[mask].copy().sort_values('日期')
    p_df['累计'] = p_df['净流入'].cumsum()
    y6_all = np.concatenate([y6_all, p_df['累计'].values])
    fig6.add_trace(go.Scatter(x=p_df['日期'], y=p_df['累计'], mode='lines',
        name=f'{pid} 累计', line=dict(color=ZH['ash'], width=2, dash='dash'), yaxis='y2',
        hovertemplate='%{x|%Y-%m-%d}<br>%{customdata}<br>累计: %{y:,}<extra></extra>', customdata=[pid]*len(p_df)))

fig6.update_layout(title=dict(text='懂车帝 · 每日净流入与周期累计', x=0.5, font=dict(size=15)),
    width=1300, height=350, hovermode='x unified', legend=dict(x=1.02, xanchor='left'), margin=dict(t=50, b=40, r=120),
    yaxis=dict(title='净流入'), yaxis2=dict(title='周期累计净流入', overlaying='y', side='right'))
fig6.update_xaxes(dtick='M1', tickformat='%Y-%m')
apply_zh_theme(fig6)
align_dual_zero(fig6, y1=dd['净流入'].values, y2=y6_all)
chart6_html = fig6.to_html(full_html=False, include_plotlyjs=False)

html_section_4 = f'''
<div class="report-section">
  <h2>懂车帝 · 净流入趋势</h2>
  <p class="section-note">懂车帝数据源的每日净流入及周期累计。</p>
  <div class="chart-box"><div class="chart-wrap">{chart6_html}</div></div>
</div>
'''

# ════════════════════════════════════════════
#  CHART 5: 下发线索数 & MA7
# ════════════════════════════════════════════
assign_fig = assign[(assign['日期'] >= merged['日期'].min()) & (assign['日期'] <= merged['日期'].max())].copy()
assign_fig['MA7'] = assign_fig['下发线索数'].rolling(7, min_periods=1).mean()

fig7 = go.Figure()
fig7.add_trace(go.Scatter(x=assign_fig['日期'], y=assign_fig['下发线索数'], mode='lines',
    name='下发线索数', line=dict(color=ZH['own'], width=1.5), opacity=0.5,
    hovertemplate='%{x|%Y-%m-%d}<br>下发线索数: %{y:,}<extra></extra>'))
fig7.add_trace(go.Scatter(x=assign_fig['日期'], y=assign_fig['MA7'], mode='lines',
    name='MA7', line=dict(color=ZH['negative'], width=2.5), yaxis='y2',
    hovertemplate='%{x|%Y-%m-%d}<br>MA7: %{y:,.0f}<extra></extra>'))
fig7.update_layout(title=dict(text='下发线索数与 7 日滚动平均', x=0.5, font=dict(size=15)),
    width=1300, height=350, hovermode='x unified', legend=dict(x=1.02, xanchor='left'), margin=dict(t=50, b=40, r=120),
    yaxis=dict(title='下发线索数'), yaxis2=dict(title='MA7', overlaying='y', side='right'))
fig7.update_xaxes(dtick='M1', tickformat='%Y-%m')
apply_zh_theme(fig7)
chart7_html = fig7.to_html(full_html=False, include_plotlyjs=False)

html_section_5 = f'''
<div class="report-section">
  <h2>下发线索数与 MA7</h2>
  <p class="section-note">下发线索数与 7 日滚动平均趋势。</p>
  <div class="chart-box"><div class="chart-wrap">{chart7_html}</div></div>
</div>
'''

# ════════════════════════════════════════════
#  CHART 6: 懂车帝A3净流入 vs 下发线索数Delta
# ════════════════════════════════════════════
def split_gaps(df, col):
    groups, cur = [], []
    for i in range(len(df)):
        if not cur:
            cur.append(i)
        else:
            gap = (df['日期'].iloc[i] - df['日期'].iloc[cur[-1]]).days
            if gap <= 1:
                cur.append(i)
            else:
                groups.append(cur); cur = [i]
    if cur:
        groups.append(cur)
    return groups

fig_corr = go.Figure()
merged_outliers = merged.nlargest(5, '净流入_abs').index.tolist() if '净流入_abs' in merged.columns else []
corr_colors = _build_bar_colors(merged['净流入'], highlight_indices=merged_outliers)
fig_corr.add_trace(go.Bar(x=merged['日期'], y=merged['净流入'], name='懂车帝A3净流入',
    marker_color=corr_colors, yaxis='y', hovertemplate='%{x|%Y-%m-%d}<br>净流入: %{y:,}<extra></extra>'))
for g in split_gaps(merged, '下发线索数Delta'):
    fig_corr.add_trace(go.Scatter(x=merged['日期'].iloc[g], y=merged['下发线索数Delta'].iloc[g],
        mode='lines', name='下发线索数Delta', yaxis='y2', showlegend=False, line=dict(color=ZH['ash']),
        hovertemplate='Delta: %{y:+,.0f}<extra></extra>'))
fig_corr.add_trace(go.Scatter(x=[None], y=[None], mode='lines', name='下发线索数Delta',
    line=dict(color=ZH['ash']), yaxis='y2', hovertemplate='Delta: %{y:+,.0f}<extra></extra>'))

y1 = merged['净流入']; y2 = merged['下发线索数Delta']
def _pad(s):
    lo, hi = float(s.min()), float(s.max())
    r = hi - lo
    if r == 0: r = abs(lo) if lo != 0 else 1
    return lo - 0.05*r, hi + 0.05*r
lo1, hi1 = _pad(y1); lo2, hi2 = _pad(y2)
neg1, pos1 = max(0, -lo1), max(0, hi1)
ratio = neg1 / pos1 if pos1 else 1
neg2, pos2 = max(0, -lo2), max(0, hi2)
lo2 = -max(neg2, pos2 * ratio)
hi2 = max(pos2, neg2 / ratio) if ratio else pos2

fig_corr.update_layout(title=dict(text=f'A3净流入 vs 下发线索数Delta', x=0.5, font=dict(size=15)),
    width=1300, height=350, hovermode='x unified', hoverlabel=dict(bgcolor='white', font_size=13),
    legend=dict(x=1.02, xanchor='left'), margin=dict(t=50, b=40, r=120),
    yaxis=dict(title='净流入', range=[lo1, hi1]),
    yaxis2=dict(title='下发线索数Delta', overlaying='y', side='right', range=[lo2, hi2]))
fig_corr.update_xaxes(dtick='M1', tickformat='%Y-%m', hoverformat='%Y-%m-%d')
apply_zh_theme(fig_corr)
chart_corr_html = fig_corr.to_html(full_html=False, include_plotlyjs=False)

html_section_6 = f'''
<div class="report-section">
  <h2>A3 净流入 vs 下发线索数 Delta</h2>
  <p class="section-note">双轴对比：柱状图为懂车帝 A3 每日净流入，折线为下发线索数偏离基线的 Delta。</p>
  <div class="chart-box"><div class="chart-wrap">{chart_corr_html}</div></div>
</div>
'''

# ════════════════════════════════════════════
#  CHART 7: Cross-correlation / Lag
# ════════════════════════════════════════════
fig_lag = go.Figure()
lags = [x[0] for x in cross_corr]
pearsons = [x[1] for x in cross_corr]
spearmans = [x[2] for x in cross_corr]
fig_lag.add_trace(go.Bar(x=lags, y=pearsons, name='Pearson',
    marker_color=[ZH['negative'] if l == best_lag_p else ZH['steel'] for l in lags]))
fig_lag.add_trace(go.Scatter(x=lags, y=spearmans, mode='lines+markers',
    name='Spearman', line=dict(color=ZH['positive'], width=2)))
fig_lag.update_layout(title=dict(text='交叉相关 vs 迟滞日', x=0.5, font=dict(size=15)),
    width=800, height=350, xaxis=dict(title=dict(text='迟滞日 (天)'), dtick=1),
    yaxis=dict(title=dict(text='相关系数')), margin=dict(t=50, b=40, r=40), legend=dict(x=1.02, xanchor='left'))
apply_zh_theme(fig_lag)
chart_lag_html = fig_lag.to_html(full_html=False, include_plotlyjs=False)

html_section_7 = f'''
<div class="report-section">
  <h2>传导迟滞分析</h2>
  <p class="section-note">Pearson 与 Spearman 交叉相关 vs 迟滞天数。最优迟滞：Pearson {best_lag_p} 天 (r={best_pearson:.3f})，Spearman {best_lag_s} 天 (ρ={best_spearman:.3f})。</p>
  <div class="chart-box"><div class="chart-wrap">{chart_lag_html}</div></div>
</div>
'''

# ════════════════════════════════════════════
#  T+7 / T+15 Ranking Tables (HTML)
# ════════════════════════════════════════════
_TABLE_B_INFLOW = 168649
_TABLE_B_OUTFLOW = 209065

def _build_ranking_df(csv_path):
    detail = pd.read_csv(str(csv_path), encoding='utf-8-sig')
    for col in ['A3流入人数（指数）', 'A3流出人数（指数）']:
        detail[col] = detail[col].astype(str).str.replace(',', '', regex=False).astype(int)
    inflow_total = detail['A3流入人数（指数）'].sum()
    outflow_total = detail['A3流出人数（指数）'].sum()
    inflow_coeff = _TABLE_B_INFLOW / inflow_total
    outflow_coeff = _TABLE_B_OUTFLOW / outflow_total
    detail['校准后流入'] = (detail['A3流入人数（指数）'] * inflow_coeff).round(0).astype(int)
    detail['校准后流出'] = (detail['A3流出人数（指数）'] * outflow_coeff).round(0).astype(int)
    detail['估算净流入'] = detail['校准后流入'] - detail['校准后流出']
    detail['流入流出比'] = detail['A3流出人数（指数）'] / detail['A3流入人数（指数）']
    full = detail.sort_values('估算净流入', ascending=True).reset_index(drop=True)
    full.index = full.index + 1
    full.index.name = '排名'
    top10 = full.head(10)
    extra = full[full['车系'].str.contains('|'.join(_EXTRA_MODELS), na=False)]
    ranking = pd.concat([top10, extra]).drop_duplicates(subset='车系').sort_values('估算净流入', ascending=True)
    display = ranking[['车系', '校准后流入', '校准后流出', '估算净流入', '流入流出比']].copy()
    for col in ['校准后流入', '校准后流出', '估算净流入']:
        display[col] = display[col].apply(lambda x: f'{x:,}')
    display['流入流出比'] = display['流入流出比'].apply(lambda x: f'{x:.1%}')
    return display

t7_df = _build_ranking_df(_PROJECT_ROOT / 'dataset' / 'LS8A3流出T+7_0622.csv')
t15_df = _build_ranking_df(_PROJECT_ROOT / 'dataset' / 'LS8A3流出T+15_0622.csv')

html_section_8 = _build_table_html('LS8 A3 承接车型排名 · T+7', t7_df, 'T+7 窗口（截止 2026-06-22）')
html_section_9 = _build_table_html('LS8 A3 承接车型排名 · T+15', t15_df, 'T+15 窗口（截止 2026-06-22）')

# ════════════════════════════════════════════
#  Methodology + Footer
# ════════════════════════════════════════════
html_method = _build_method_note()

html_footer = '''
<div style="text-align:center;padding:32px 0 16px;font-size:12px;color:#6B7280;border-top:1px solid #E5EAF0;margin-top:16px;">
  Raccoon Research · mashang-service · Generated by competition_a3_flow.py
</div>
</div>
</body>
</html>
'''

# ════════════════════════════════════════════
#  WRITE HTML
# ════════════════════════════════════════════
with open(_OUTPUT_HTML, 'w', encoding='utf-8') as f:
    f.write(html_head)
    f.write(html_section_1)
    f.write(html_section_2)
    f.write(html_section_3)
    f.write(html_section_4)
    f.write(html_section_5)
    f.write(html_section_6)
    f.write(html_section_7)
    f.write(html_section_8)
    f.write(html_section_9)
    f.write(html_method)
    f.write(html_footer)

print(f'竞争洞察 A3 报告已生成: {_OUTPUT_HTML}')
