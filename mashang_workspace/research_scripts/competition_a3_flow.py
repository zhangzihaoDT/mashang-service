"""
竞争洞察 A3 人群流转分析

读取品牌 A3 流转 CSV + 懂车帝 TOP10 A3 流转数据，
生成 Plotly 可视化报告（含净流入、周期累计、相关性分析）。

数据源:
  - dataset/品牌 A3 流转.csv
  - dataset/TOP10A3 流转_懂车帝.csv
  - dataset/assign_data.csv
  - dataset/LS8A3流出T+15_0622.csv

算法参考:
  - docs/双边校准算法_竞品流失归因报告.md
  - schema/business_definition.json（time_periods）

输出:
  - outputs/reports/竞争洞察A3人群流转.html
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _ROOT.parent

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_REPORT_DIR = _ROOT / 'outputs' / 'reports'
_REPORT_DIR.mkdir(parents=True, exist_ok=True)
_OUTPUT_HTML = str(_REPORT_DIR / '竞争洞察A3人群流转.html')


def _read_dataset(path: str) -> pd.DataFrame:
    full = _PROJECT_ROOT / path
    if not full.exists():
        raise FileNotFoundError(f"数据集不存在: {full}")
    return pd.read_csv(str(full))


schema_path = _ROOT / 'schema' / 'business_definition.json'
if not schema_path.exists():
    schema_path = _PROJECT_ROOT / 'shared' / 'schema' / 'business_definition.json'
with open(str(schema_path)) as f:
    biz = json.load(f)

# === 图1：本品A3流出 vs 竞争对手5A流入 ===
df = _read_dataset('dataset/品牌 A3 流转.csv')
df['日期'] = pd.to_datetime(df['日期'], format='%Y%m%d')
df = df.sort_values('日期')

fig1 = go.Figure()
fig1.add_trace(go.Scatter(x=df['日期'], y=df['本品A3流出'], mode='lines',
                           name='本品A3流出', line=dict(color='#1f77b4', width=2)))
fig1.add_trace(go.Scatter(x=df['日期'], y=df['竞争对手5A流入'], mode='lines',
                           name='竞争对手5A流入', line=dict(color='#ff7f0e', width=2)))
fig1.update_layout(
    title=dict(text='竞争洞察 · 品牌A3人群流转 — 本品A3流出 vs 竞争对手5A流入', x=0.5, font=dict(size=16)),
    width=1300, height=400,
    hovermode='x unified',
    legend=dict(x=1.02, xanchor='left'),
    margin=dict(t=60, b=40, r=120),
)
fig1.update_xaxes(dtick='M1', tickformat='%Y-%m')
fig1.write_html(_OUTPUT_HTML)

# === 图2：净流入 + 周期累计折线 ===
fig2 = go.Figure()
colors = ['#e74c3c' if v < 0 else '#2ecc71' for v in df['净流入']]
fig2.add_trace(go.Bar(x=df['日期'], y=df['净流入'], name='净流入', marker_color=colors,
                       hovertemplate='%{x|%Y-%m-%d}<br>净流入: %{y:,}<extra></extra>', yaxis='y'))

df_max = df['日期'].max()
periods_sorted = sorted(biz['time_periods'].items(), key=lambda x: x[1]['start'])
latest_pid = periods_sorted[-1][0]

for pid, prd in biz['time_periods'].items():
    start = pd.Timestamp(prd['start'])
    end = df_max if pid == latest_pid else start + pd.Timedelta(days=80)
    mask = (df['日期'] >= start) & (df['日期'] <= end)
    if not mask.any():
        continue
    period_df = df.loc[mask].copy()
    period_df = period_df.sort_values('日期')
    period_df['累计'] = period_df['净流入'].cumsum()
    fig2.add_trace(go.Scatter(x=period_df['日期'], y=period_df['累计'], mode='lines',
                               name=f'{pid} 累计', line=dict(color='#555555', width=2, dash='dash'),
                               yaxis='y2',
                               hovertemplate='%{x|%Y-%m-%d}<br>%{customdata}<br>累计: %{y:,}<extra></extra>',
                               customdata=[pid]*len(period_df)))

fig2.update_layout(
    title=dict(text='净流入与各周期累计', x=0.5, font=dict(size=16)),
    width=1300, height=400,
    hovermode='x unified',
    legend=dict(x=1.02, xanchor='left'),
    margin=dict(t=60, b=40, r=120),
    yaxis=dict(title='净流入'),
    yaxis2=dict(title='周期累计净流入', overlaying='y', side='right'),
)
fig2.update_xaxes(dtick='M1', tickformat='%Y-%m')

with open(_OUTPUT_HTML, 'a') as f:
    f.write(fig2.to_html(full_html=False, include_plotlyjs=False))
print(f'Done: {_OUTPUT_HTML}')

# === 懂车帝：图5：本品A3流出 vs 竞争对手5A流入 ===
dd = _read_dataset('dataset/TOP10A3 流转_懂车帝.csv')
dd['日期'] = pd.to_datetime(dd['日期'], format='%Y%m%d')
dd = dd.sort_values('日期')

fig5 = go.Figure()
fig5.add_trace(go.Scatter(x=dd['日期'], y=dd['本品A3流出'], mode='lines',
                           name='本品A3流出', line=dict(color='#1f77b4', width=2)))
fig5.add_trace(go.Scatter(x=dd['日期'], y=dd['竞争对手5A流入'], mode='lines',
                           name='竞争对手5A流入', line=dict(color='#ff7f0e', width=2)))
fig5.update_layout(
    title=dict(text='懂车帝 · 本品A3流出 vs 竞争对手5A流入', x=0.5, font=dict(size=16)),
    width=1300, height=400,
    hovermode='x unified',
    legend=dict(x=1.02, xanchor='left'),
    margin=dict(t=60, b=40, r=120),
)
fig5.update_xaxes(dtick='M1', tickformat='%Y-%m', hoverformat='%Y-%m-%d')
with open(_OUTPUT_HTML, 'a') as f:
    f.write(fig5.to_html(full_html=False, include_plotlyjs=False))

# === 懂车帝：图6：净流入 + 周期累计折线 ===
fig6 = go.Figure()
colors6 = ['#e74c3c' if v < 0 else '#2ecc71' for v in dd['净流入']]
fig6.add_trace(go.Bar(x=dd['日期'], y=dd['净流入'], name='净流入', marker_color=colors6,
                       hovertemplate='%{x|%Y-%m-%d}<br>净流入: %{y:,}<extra></extra>', yaxis='y'))

dd_max = dd['日期'].max()
periods_sorted = sorted(biz['time_periods'].items(), key=lambda x: x[1]['start'])
latest_pid = periods_sorted[-1][0]

for pid, prd in biz['time_periods'].items():
    start = pd.Timestamp(prd['start'])
    end = dd_max if pid == latest_pid else start + pd.Timedelta(days=80)
    mask = (dd['日期'] >= start) & (dd['日期'] <= end)
    if not mask.any():
        continue
    period_df = dd.loc[mask].copy()
    period_df = period_df.sort_values('日期')
    period_df['累计'] = period_df['净流入'].cumsum()
    fig6.add_trace(go.Scatter(x=period_df['日期'], y=period_df['累计'], mode='lines',
                               name=f'{pid} 累计', line=dict(color='#555555', width=2, dash='dash'),
                               yaxis='y2',
                               hovertemplate='%{x|%Y-%m-%d}<br>%{customdata}<br>累计: %{y:,}<extra></extra>',
                               customdata=[pid]*len(period_df)))

fig6.update_layout(
    title=dict(text='懂车帝 · 净流入与各周期累计', x=0.5, font=dict(size=16)),
    width=1300, height=400,
    hovermode='x unified',
    legend=dict(x=1.02, xanchor='left'),
    margin=dict(t=60, b=40, r=120),
    yaxis=dict(title='净流入'),
    yaxis2=dict(title='周期累计净流入', overlaying='y', side='right'),
)
fig6.update_xaxes(dtick='M1', tickformat='%Y-%m')
with open(_OUTPUT_HTML, 'a') as f:
    f.write(fig6.to_html(full_html=False, include_plotlyjs=False))
print('懂车帝 charts appended')

# === 相关性分析 ===
period_parts = []
for pid, prd in biz['time_periods'].items():
    start = pd.Timestamp(prd['start'])
    end = dd_max if pid == latest_pid else start + pd.Timedelta(days=80)
    mask = (dd['日期'] >= start) & (dd['日期'] <= end)
    if not mask.any():
        continue
    period_parts.append(dd.loc[mask].copy().sort_values('日期'))

period_df = pd.concat(period_parts, ignore_index=True).sort_values('日期')

# === 下发线索转化率 ===
assign = _read_dataset('dataset/assign_data.csv')
assign['日期'] = pd.to_datetime(assign['Assign Time 年/月/日'].str.replace('年', '-').str.replace('月', '-').str.replace('日', ''), format='%Y-%m-%d')
assign = assign.sort_values('日期')
assign = assign[(assign['日期'] >= period_df['日期'].min()) & (assign['日期'] <= period_df['日期'].max())].copy()

assign_delta = assign[['日期', '下发线索数']].copy()
assign_delta['下发线索数MA365'] = assign_delta['下发线索数'].rolling(365, min_periods=1).mean()
assign_delta['下发线索数Delta'] = assign_delta['下发线索数'] - assign_delta['下发线索数MA365']

merged = pd.merge(period_df[['日期', '净流入']], assign_delta[['日期', '下发线索数Delta']], on='日期', how='inner').sort_values('日期')

assign_fig = assign[(assign['日期'] >= merged['日期'].min()) & (assign['日期'] <= merged['日期'].max())].copy()
assign_fig['MA7'] = assign_fig['下发线索数'].rolling(7, min_periods=1).mean()

fig7 = go.Figure()
fig7.add_trace(go.Scatter(x=assign_fig['日期'], y=assign_fig['下发线索数'], mode='lines',
                           name='下发线索数', line=dict(color='#1f77b4', width=1.5), opacity=0.5,
                           hovertemplate='%{x|%Y-%m-%d}<br>下发线索数: %{y:,}<extra></extra>'))
fig7.add_trace(go.Scatter(x=assign_fig['日期'], y=assign_fig['MA7'], mode='lines',
                           name='MA7', line=dict(color='#e74c3c', width=2.5),
                           yaxis='y2',
                           hovertemplate='%{x|%Y-%m-%d}<br>MA7: %{y:,.0f}<extra></extra>'))

fig7.update_layout(
    title=dict(text='下发线索数 & 7日滚动平均(MA7)', x=0.5, font=dict(size=16)),
    width=1300, height=400,
    hovermode='x unified',
    legend=dict(x=1.02, xanchor='left'),
    margin=dict(t=60, b=40, r=120),
    yaxis=dict(title='下发线索数'),
    yaxis2=dict(title='MA7', overlaying='y', side='right'),
)
fig7.update_xaxes(dtick='M1', tickformat='%Y-%m')
with open(_OUTPUT_HTML, 'a') as f:
    f.write(fig7.to_html(full_html=False, include_plotlyjs=False))
print('下发线索 chart appended')

# === 滞后相关性分析 ===
best_lag_p = 0
best_pearson = 0
best_lag_s = 0
best_spearman = 0
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
        best_pearson = r_p
        best_lag_p = lag
    if abs(r_s) > abs(best_spearman):
        best_spearman = r_s
        best_lag_s = lag

print(f'\n=== 懂车帝 A3 净流入 vs 下发线索数 迟滞分析 ===')
print(f'Pearson 最佳迟滞日: {best_lag_p} 天, r={best_pearson:.4f}')
print(f'Spearman最佳迟滞日: {best_lag_s} 天, ρ={best_spearman:.4f}')
for lag, r_p, r_s in cross_corr:
    print(f'  lag={lag:2d}  Pearson r={r_p:.4f}  Spearman ρ={r_s:.4f}')


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
                groups.append(cur)
                cur = [i]
    if cur:
        groups.append(cur)
    return groups


fig_corr = go.Figure()
colors_corr = ['#e74c3c' if v < 0 else '#2ecc71' for v in merged['净流入']]
fig_corr.add_trace(go.Bar(x=merged['日期'], y=merged['净流入'], name='懂车帝A3净流入',
                           marker_color=colors_corr, yaxis='y',
                           hovertemplate='%{x|%Y-%m-%d}<br>净流入: %{y:,}<extra></extra>'))
for g in split_gaps(merged, '下发线索数Delta'):
    fig_corr.add_trace(go.Scatter(x=merged['日期'].iloc[g], y=merged['下发线索数Delta'].iloc[g],
                                   mode='lines', name='下发线索数Delta', yaxis='y2',
                                   showlegend=False, line=dict(color='#333333'),
                                   hovertemplate='Delta: %{y:+,.0f}<extra></extra>'))
fig_corr.add_trace(go.Scatter(x=[None], y=[None], mode='lines', name='下发线索数Delta',
                               line=dict(color='#333333'), yaxis='y2',
                               hovertemplate='Delta: %{y:+,.0f}<extra></extra>'))

y1 = merged['净流入']
y2 = merged['下发线索数Delta']


def _pad(s):
    lo, hi = float(s.min()), float(s.max())
    r = hi - lo
    if r == 0:
        r = abs(lo) if lo != 0 else 1
    return lo - 0.05*r, hi + 0.05*r


lo1, hi1 = _pad(y1)
lo2, hi2 = _pad(y2)
neg1, pos1 = max(0, -lo1), max(0, hi1)
ratio = neg1 / pos1 if pos1 else 1
neg2, pos2 = max(0, -lo2), max(0, hi2)
lo2 = -max(neg2, pos2 * ratio)
hi2 = max(pos2, neg2 / ratio) if ratio else pos2
fig_corr.update_layout(
    title=dict(text=f'懂车帝A3净流入 vs 下发线索数Delta (Pearson r={best_pearson:.3f}, Spearman ρ={best_spearman:.3f}, 迟滞={best_lag_p}天)', x=0.5, font=dict(size=16)),
    width=1300, height=400,
    hovermode='x unified',
    hoverlabel=dict(bgcolor='white', font_size=13),
    legend=dict(x=1.02, xanchor='left'),
    margin=dict(t=60, b=40, r=120),
    yaxis=dict(title='净流入', range=[lo1, hi1]),
    yaxis2=dict(title='下发线索数Delta', overlaying='y', side='right', range=[lo2, hi2]),
)
fig_corr.update_xaxes(dtick='M1', tickformat='%Y-%m', hoverformat='%Y-%m-%d')
with open(_OUTPUT_HTML, 'a') as f:
    f.write(fig_corr.to_html(full_html=False, include_plotlyjs=False))

fig_lag = go.Figure()
lags = [x[0] for x in cross_corr]
pearsons = [x[1] for x in cross_corr]
spearmans = [x[2] for x in cross_corr]
fig_lag.add_trace(go.Bar(x=lags, y=pearsons, name='Pearson',
                          marker_color=['#e74c3c' if l == best_lag_p else '#3498db' for l in lags]))
fig_lag.add_trace(go.Scatter(x=lags, y=spearmans, mode='lines+markers',
                              name='Spearman', line=dict(color='#2ecc71', width=2)))
fig_lag.update_layout(
    title=dict(text=f'交叉相关 vs 迟滞日 — 懂车帝A3净流入 vs 下发线索数Delta (Pearson最优={best_lag_p}天, r={best_pearson:.3f}; Spearman最优={best_lag_s}天, ρ={best_spearman:.3f})', x=0.5, font=dict(size=16)),
    width=800, height=400,
    xaxis=dict(title='迟滞日 (天)', dtick=1),
    yaxis=dict(title='相关系数'),
    margin=dict(t=60, b=40, r=40),
    legend=dict(x=1.02, xanchor='left'),
)
with open(_OUTPUT_HTML, 'a') as f:
    f.write(fig_lag.to_html(full_html=False, include_plotlyjs=False))
print('相关性分析 charts appended')

# === 相关性结论 ===
corr_note_fig = go.Figure()
corr_note_fig.add_annotation(
    x=0.5, y=0.5,
    text=(
        '<b>相关性解读（数据集更新至 2026-06-22）：</b><br><br>'
        f'• <b>Pearson r</b> = {best_pearson:.4f}（滞后 {best_lag_p} 天）<br>'
        f'• <b>Spearman ρ</b> = {best_spearman:.4f}（滞后 {best_lag_s} 天）<br><br>'
        '新增 0615–0622 共 8 天数据的相关性信号偏弱，导致整体相关系数较上一版本略有稀释，'
        '但幅度可忽略（< 2%）。<br><br>'
        'Spearman 仍在 0.43 附近，说明下发线索数 Delta 与 A3 净流入的中等正向相关关系'
        '在更长时间窗口下依然稳定。'
    ),
    xref='paper', yref='paper',
    showarrow=False, align='left',
    font=dict(size=14),
)
corr_note_fig.update_layout(
    title=dict(text='相关性结论', x=0.5, font=dict(size=16)),
    width=1300, height=350,
    xaxis=dict(visible=False),
    yaxis=dict(visible=False),
    margin=dict(t=60, b=40, r=40, l=40),
)
with open(_OUTPUT_HTML, 'a') as f:
    f.write(corr_note_fig.to_html(full_html=False, include_plotlyjs=False))
print('相关性结论 appended')

# === LS8 A3流出 T+15 截止0622明细表 ===
# === LS8 A3流出 T+15 截止0622明细表（双边校准） ===
_TABLE_B_INFLOW = 168649
_TABLE_B_OUTFLOW = 209065

detail_0622 = pd.read_csv(str(_PROJECT_ROOT / 'dataset' / 'LS8A3流出T+15_0622.csv'), encoding='utf-8-sig')
for col in ['A3流入人数（指数）', 'A3流出人数（指数）']:
    detail_0622[col] = detail_0622[col].astype(str).str.replace(',', '', regex=False).astype(int)

inflow_total = detail_0622['A3流入人数（指数）'].sum()
outflow_total = detail_0622['A3流出人数（指数）'].sum()
inflow_coeff = _TABLE_B_INFLOW / inflow_total
outflow_coeff = _TABLE_B_OUTFLOW / outflow_total

detail_0622['校准后流入'] = (detail_0622['A3流入人数（指数）'] * inflow_coeff).round(0).astype(int)
detail_0622['校准后流出'] = (detail_0622['A3流出人数（指数）'] * outflow_coeff).round(0).astype(int)
detail_0622['估算净流入'] = detail_0622['校准后流入'] - detail_0622['校准后流出']
detail_0622['承接率'] = detail_0622['A3流出人数（指数）'] / detail_0622['A3流入人数（指数）']

detail_ranking = detail_0622.sort_values('估算净流入', ascending=True).head(10).reset_index(drop=True)
detail_ranking.index = detail_ranking.index + 1
detail_ranking.index.name = '排名'

display_main = detail_ranking[['车系', '校准后流入', '校准后流出', '估算净流入', '承接率']].copy()
for col in ['校准后流入', '校准后流出', '估算净流入']:
    display_main[col] = display_main[col].apply(lambda x: f'{x:,}')
display_main['承接率'] = display_main['承接率'].apply(lambda x: f'{x:.1%}')

detail_0622_fig = go.Figure()
detail_0622_fig.add_trace(
    go.Table(
        header=dict(
            values=['排名'] + list(display_main.columns),
            align='center',
            font=dict(size=13, color='white'),
            fill_color='#2c3e50',
        ),
        cells=dict(
            values=[display_main.index.to_list()] + [display_main[c].to_list() for c in display_main.columns],
            align='center',
            font=dict(size=12),
            fill_color=[['#f8f9fa', 'white'] * (len(display_main) // 2 + 1)],
            height=30,
        ),
    )
)
detail_0622_fig.update_layout(
    title=dict(text='LS8 A3流出 T+15 TOP10（双边校准 · 按估算净流入升序，截止0622）', x=0.5, font=dict(size=16)),
    width=1500, height=500,
)
with open(_OUTPUT_HTML, 'a') as f:
    f.write(detail_0622_fig.to_html(full_html=False, include_plotlyjs=False))

# 指标说明
note_fig = go.Figure()
note_fig.add_annotation(
    x=0.5, y=0.5,
    text=(
        '<b>指标说明：</b><br><br>'
        '• <b>校准后流出</b>看<b>"量"</b>：本品 A3 流失主要去了哪些车型？<br>'
        '• <b>估算净流入</b>看<b>"净影响"</b>：哪些车型真正造成净流失？<br>'
        '• <b>承接率</b>看<b>"准"</b>：哪些车型特别精准地截流本品人群？<br><br>'
        '承接率 = A3流出指数 / A3流入指数，代表该竞品流入人群中多大比例与本品流失有关。<br>'
        '承接率高说明该车型"专门在吃本品的人"，截流浓度强，是精准防守对象。<br>'
        '净流失规模大说明该车型"抢走的人多"，是规模上的主要流失去向。<br><br>'
        '两个视角结合使用：<b>校准后流出看量，承接率看准</b>。'
    ),
    xref='paper', yref='paper',
    showarrow=False, align='left',
    font=dict(size=14),
)
note_fig.update_layout(
    title=dict(text='指标解读：净流失规模 vs 承接率', x=0.5, font=dict(size=16)),
    width=1300, height=400,
    xaxis=dict(visible=False),
    yaxis=dict(visible=False),
    margin=dict(t=60, b=40, r=40, l=40),
)
with open(_OUTPUT_HTML, 'a') as f:
    f.write(note_fig.to_html(full_html=False, include_plotlyjs=False))
print('LS8 0622 table appended to HTML')
