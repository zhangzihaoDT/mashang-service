#!/usr/bin/env python
"""
国内DC在库_未开票 库存趋势报告 — 事件回放生成每日库存水位 HTML 图表。

用法:
    python research_scripts/dc_inventory_trend_report.py
    python research_scripts/dc_inventory_trend_report.py --output outputs/reports/
"""

import sys, json, importlib.util
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
WS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

spec = importlib.util.spec_from_file_location(
    "d", REPO_ROOT / "shared/operators" / "dealer_unsold_inventory.py"
)
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)

OVERSEAS = {"上汽国际", "海外"}
SERIES_MAP = {"LSJEL":"LS8","LSJEH":"LS9","LSJWL":"LS7","LSJWR":"LS6","LSJWT":"L6","LSJE3":"L7"}
COLOR_MAP = {'LS8':'#174A7C','LS6':'#D79A36','LS9':'#7ECDEB','L6':'#7A4A24','LS7':'#6B7C8F','L7':'#06213D'}
MODELS = ['LS8','LS6','LS9','L6','LS7','L7']
DEFAULT_OUTPUT = WS_ROOT / "outputs" / "reports"


def build_trend_data(df):
    domestic = df[~df['bloc_name'].isin(OVERSEAS)].copy()
    domestic['arrival'] = pd.to_datetime(domestic['real_in_dc_time'])
    domestic['exit'] = domestic[['out_delivery_center_time', 'order_invoice_upload_time']].min(axis=1)
    domestic['series'] = domestic['vin'].str[:5].map(SERIES_MAP).fillna("其他")

    today_end = pd.Timestamp(date.today()) + timedelta(days=1)
    dates = pd.date_range(domestic['arrival'].min().normalize(), today_end, freq='D')

    model_data = {}
    total_series = [0] * len(dates)
    model_series = {m: [0] * len(dates) for m in MODELS}

    for i, d in enumerate(dates):
        d_end = d + timedelta(days=1)
        for m in MODELS:
            sub = domestic[domestic['series'] == m]
            cnt = int(((sub['arrival'] < d_end) & ((sub['exit'].isna()) | (sub['exit'] >= d_end))).sum())
            model_series[m][i] = cnt
        total_series[i] = sum(model_series[m][i] for m in MODELS)

    for m in MODELS:
        series = [int(v) for v in model_series[m]]
        # 首辆车入库前不划线（设为 null）
        first_nonzero = next((i for i, v in enumerate(series) if v > 0), None)
        if first_nonzero is not None:
            for i in range(first_nonzero):
                series[i] = None
        model_data[m] = {
            'dates': [str(d.date()) for d in dates],
            'inventory': series,
        }
    model_data['总计'] = {
        'dates': [str(d.date()) for d in dates],
        'inventory': [int(v) for v in total_series],
    }
    return model_data


def render_html(model_data) -> str:
    total = model_data['总计']
    traces = []
    for m in MODELS:
        inv_list = model_data[m]['inventory']
        texts = []
        last_val = None
        for v in inv_list:
            if v is not None:
                last_val = v
        for v in inv_list:
            if v is not None and v == last_val:
                texts.append(str(v))
            else:
                texts.append('')
        traces.append(
            f"{{x: {json.dumps(model_data[m]['dates'])}, y: {json.dumps(inv_list)}, "
            f"text: {json.dumps(texts)}, textposition: 'middle right', textfont: {{size: 12, color: '{COLOR_MAP[m]}'}}, "
            f"type: 'scatter', mode: 'lines+text', name: '{m}', connectgaps: false, cliponaxis: false, line: {{width: 2, color: '{COLOR_MAP[m]}'}}}}"
        )
    traces_str = ',\n'.join(traces)

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>国内DC在库_未开票 库存趋势</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
body {{ font-family: -apple-system, sans-serif; background: #FFF9EF; margin: 0; padding: 20px; color: #1F2D3D; }}
h1 {{ color: #174A7C; font-size: 22px; margin-bottom: 5px; }}
.subtitle {{ color: #6B7C8F; font-size: 14px; margin-bottom: 20px; }}
.summary {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
.card {{ background: white; border-radius: 12px; padding: 16px 24px; min-width: 140px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }}
.card .num {{ font-size: 28px; font-weight: 700; color: #174A7C; }}
.card .label {{ font-size: 12px; color: #6B7C8F; }}
.chart {{ background: white; border-radius: 12px; padding: 16px; margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }}
.info {{ background: #DDEFF8; border-radius: 8px; padding: 12px 16px; margin-bottom: 20px; font-size: 13px; color: #174A7C; }}
.info code {{ background: rgba(23,74,124,0.1); padding: 1px 6px; border-radius: 4px; }}
.footer {{ color: #6B7C8F; font-size: 12px; text-align: center; margin-top: 30px; }}
</style>
</head>
<body>
<h1>国内DC在库_未开票 库存趋势</h1>
<div class="subtitle">事件回放：入库(real_in_dc_time) → 出库(out_delivery_center_time / invoice_upload_time) | 数据截至 {date.today()}</div>
<div class="summary">
  <div class="card"><div class="num">{total['inventory'][-1]:,}</div><div class="label">当前库存</div></div>
  <div class="card"><div class="num">{max(total['inventory'][-90:]):,}</div><div class="label">近90日最高</div></div>
  <div class="card"><div class="num">{min(total['inventory'][-90:]):,}</div><div class="label">近90日最低</div></div>
</div>
<div class="info">
  <strong>口径：</strong>国内DC在库_未开票 — <code>physical_position = DC内</code> + <code>bloc_name</code> 不为上汽国际/海外 + <code>invoice_upload_time</code> 为空<br>
  <strong>事件回放逻辑：</strong>入库事件（<code>real_in_dc_time</code>）推高库存，出库事件（<code>out_delivery_center_time</code> 或 <code>invoice_upload_time</code>，取较早者）降低库存。逐日回放得到完整趋势。
</div>
<div class="chart" id="chart-total"></div>
<div class="chart" id="chart-model"></div>
<script>
var totalData = {json.dumps(total['inventory'])};
var totalDates = {json.dumps(total['dates'])};
Plotly.newPlot('chart-total', [{{
    x: totalDates, y: totalData, type: 'scatter', mode: 'lines',
    line: {{color: '#174A7C', width: 2}},
    name: '国内DC在库_未开票',
    fill: 'tozeroy', fillcolor: 'rgba(23,74,124,0.08)'
}}], {{
    title: {{text: '国内DC在库_未开票 — 总量趋势（事件回放）'}},
    xaxis: {{title: '日期', showgrid: true, gridcolor: '#f0f0f0'}},
    yaxis: {{title: '库存量（辆）', showgrid: true, gridcolor: '#f0f0f0'}},
    margin: {{l: 60, r: 30, t: 40, b: 40}},
    paper_bgcolor: 'white', plot_bgcolor: 'white',
    font: {{family: '-apple-system, sans-serif', color: '#1F2D3D'}},
    hovermode: 'x unified'
}});
Plotly.newPlot('chart-model', [{traces_str}], {{
    title: {{text: '国内DC在库_未开票 — 分车型趋势（事件回放）'}},
    xaxis: {{title: '日期', showgrid: true, gridcolor: '#f0f0f0'}},
    yaxis: {{title: '库存量（辆）', showgrid: true, gridcolor: '#f0f0f0'}},
    margin: {{l: 60, r: 80, t: 40, b: 40}},
    paper_bgcolor: 'white', plot_bgcolor: 'white',
    font: {{family: '-apple-system, sans-serif', color: '#1F2D3D'}},
    hovermode: 'x unified',
    legend: {{orientation: 'h', y: -0.2}}
}});
</script>
<div class="footer">生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} | 算子: shared/operators/dealer_unsold_inventory.py</div>
</body>
</html>'''


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="国内DC在库_未开票 库存趋势报告")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="输出目录")
    args = parser.parse_args(argv)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("📖 读取数据 ...")
    inv = pd.read_parquet(REPO_ROOT / "dataset" / "delivery_inventory.parquet")
    odf = pd.read_parquet(REPO_ROOT / "dataset" / "order_data.parquet")
    df = d.compute(inv, odf)

    print("📊 事件回放计算库存趋势 ...")
    model_data = build_trend_data(df)
    html = render_html(model_data)

    out_path = out_dir / "dc_inventory_trend.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"✅ 报告已保存: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
