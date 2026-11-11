"""v1.2 stable report: bound facts and tables only; no business verdict templates."""
from __future__ import annotations

import html
import sys
from pathlib import Path

_WS = Path(__file__).resolve().parents[1]
if str(_WS) not in sys.path:
    sys.path.insert(0, str(_WS))

from research_scripts.launch_research_plan import number_text, value_at


def report_tables(ctx: dict) -> list:
    """Each visible data cell points to a validated metric; Gate C checks its text."""
    gens=ctx['curves']['gens']; benches=ctx['benchmarks']; tables=[]
    tables.append(('等生命周期窗口（末日不含）', ['代际','上市日','窗口末日','配置预售开始日'],
        [[f'curves.curves.{g}.gen',f'windows.{g}.launch',f'windows.{g}.window_end_exclusive',
          f'windows.{g}.presale_start'] for g in gens]))
    for g in gens:
        tables.append((f'{g} 每日锁单', ['日期','新增锁单','累计锁单'],
            [[f'curves.curves.{g}.dates.{i}',f'curves.curves.{g}.daily.{i}',f'curves.curves.{g}.cum.{i}']
             for i in range(ctx['n_days'])]))
    tables.append(('逐对标差额', ['对标','主代际累计','对标累计','累计差额','主/对标比值','首日差额','尾段合计差额'],
        [[f'benchmarks.{i}']+[f'deltas.{b}.{k}' for k in
         ('cum_main','cum_bench','cum_diff','cum_ratio','d1_diff','tail_diff')] for i,b in enumerate(benches)]))
    if 'dynamics' in ctx:
        tables.append(('观察期节奏（占比为 0–1）',['代际','首日锁单','首日占比','尾段天数','尾段日均'],
            [[f'curves.curves.{g}.gen']+[f'dynamics.{g}.{k}' for k in
              ('d1','d1_share_of_cum','tail_days','tail_avg')] for g in gens]))
    tables.append(('上市前小订池事件（锁单与退款可重叠，率为 0–1）',
        ['代际','总池','锁单事件','退款事件','二者重叠','锁单事件率','退款事件率','配置预售天数','早于配置起日'],
        [[f'presale.{g}.{k}' for k in ('gen','pool_total','pool_locked','pool_refunded','lock_refund_overlap',
          'pool_lock_rate','pool_refund_rate','presale_days','presale_pre_open')] for g in gens]))
    tables.append(('窗口锁单来源（四类合计等于总锁单）',
        ['代际','总锁单','上市前小订','上市当日小订','无小订记录','上市日后残余'],
        [[f'origin.{g}.{k}' for k in ('gen','total','pre','launch_day','none','post_launch')] for g in gens]))
    tables.append(('差额算术分解（单位：单）',
        ['对标','总差','上市前来源差','上市当日来源差','无小订记录差','残余差','池规模项','池率项','池锁单事件差'],
        [[f'source_decomp.{b}.{k}' for k in ('bench','gap_total','pre_diff','launch_day_diff','none_diff',
          'post_launch_diff','presale_scale_effect','presale_rate_effect','pool_locked_diff')] for b in benches]))
    return tables


def render_report(ctx: dict, out_root: Path | None = None) -> str:
    """Return HTML in memory. The CLI writes only after Gate C passes."""
    from research_scripts.launch_deep_dive import _warnings
    esc=lambda x:html.escape(str(x),quote=True)
    style=(Path(__file__).resolve().parents[1]/'templates/report_style.css').read_text()
    title=f"{ctx['main']} 上市 D1–D{ctx['n_days']}｜v1.2 稳定版"
    s=['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
       '<meta name="viewport" content="width=device-width, initial-scale=1">',
       f'<title>{esc(title)}</title><style>{style}</style>',
       '<style>.report-container{max-width:1180px;margin:auto;padding:24px;overflow-wrap:anywhere}.table-scroll{overflow-x:auto}'
       '.report-table{min-width:580px}.finding{margin:18px 0}.scope{overflow-wrap:anywhere}</style></head>',
       f'<body class="report-page"><main class="report-container"><h1 class="report-title">{esc(title)}</h1>',
       f'<p>Raccoon Research · 对标 {esc("、".join(ctx["benchmarks"]))} · 观察截止 {esc(ctx["as_of"])}</p>',
       '<p>仅提供已验证的描述性分析。上市日来自业务定义，各对标使用自身等长窗口。</p>',
       '<section class="report-section"><h2 class="section-title">已验证发现</h2>']
    for f in ctx['findings']:
        s.append(f'<article class="finding"><h3>{esc(f["title"])}</h3><p>{esc(f["body"])}</p>'
                 f'<p class="section-note">{esc(f["scope"])}</p></article>')
    s.append('</section>')
    for title,headers,rows in report_tables(ctx):
        s.append(f'<section class="report-section"><h2 class="section-title">{esc(title)}</h2>'
                 '<div class="table-scroll"><table class="report-table"><thead><tr>')
        s.append(''.join(f'<th>{esc(h)}</th>' for h in headers)+'</tr></thead><tbody>')
        for row in rows:
            s.append('<tr>'+''.join(f'<td class="num" data-path="{esc(path)}">'
                     f'{esc(number_text(value_at(ctx,path)))}</td>' for path in row)+'</tr>')
        s.append('</tbody></table></div></section>')
    s.append('<section class="report-section"><h2 class="section-title">本次不提供分析</h2><ul>')
    for q in ctx['research_plan']['excluded']:
        s.append(f'<li>{esc(q["title"])}：{esc(q["status"])} — {esc(q["reason"])}</li>')
    for q in ctx['gate_a']['skipped']:
        s.append(f'<li>{esc(q["title"])}：{esc(q["reason"])}</li>')
    s.append('</ul></section><section class="report-section"><h2 class="section-title">来源、口径与限制</h2>')
    s.append('<p>数据：dataset/order_data.parquet；代际与上市时间：shared/schema/business_definition.json。'
             '锁单仅用户车，剔除测试单、总部主理店及非零售；小订池允许订单类型为空。'
             '按订单号唯一性核验。来源按小订支付时间分类，单独保留上市日后残余。</p>')
    s.append('<p>池规模项 = (P主−P标)×r标；池率项 = P主×(r主−r标)。两项之和 = 池锁单事件差。'
             '来源四项差额之和 = 窗口总锁单差；首日差额 + 尾段差额 = 累计差额。</p>')
    s.append('<ul>'+''.join(f'<li>{esc(w)}</li>' for w in _warnings(ctx))+'</ul>')
    s.append('<p>质量核验：Gate A 前置通过，Gate B 数值、方向与分解恒等式通过；'
             'HTML 的 Gate C 结果见 research_plan.json。</p>')
    s.append('<p class="scope">输入指纹：'+esc(str(ctx['input_fingerprints']))+'</p>')
    s.append('<p class="scope">逐代际过滤审计：'+esc(str(ctx['exclusions']))+'</p>')
    s.append('<p class="scope">封盘池锁退事件重叠（仅质量审计，不计算剩余）：'+esc(str(ctx['audit']['pool_overlap']))+'</p>')
    s.append(f'<p>生成时间 {esc(ctx["generated_at"])}；可复现入口 workspace/research_scripts/launch_deep_dive.py。</p>')
    s.append('</section></main></body></html>')
    return '\n'.join(s)


def render_method_doc(ctx: dict, out_root: Path | None = None) -> str:
    from research_scripts.launch_deep_dive import _warnings
    rows=['# vehicle-launch-deep-dive v1.2 稳定版口径',
          f"\n对象：{ctx['main']}；对标：{'、'.join(ctx['benchmarks'])}；截止：{ctx['as_of']}；N={ctx['n_days']}。",
          '\n数据源：dataset/order_data.parquet。上市日与归属：shared/schema/business_definition.json。',
          '\n锁单：用户车，剔测试单、总部主理店及非零售，order_number 唯一。',
          '\n小订池：允许空订单类型；intention_payment_time < 上市日，含配置预售起日前记录。',
          '\n事件截止：各代际 lock_time / intention_refund_time < 上市日+N；锁与退可重叠。',
          '\n来源：上市前小订、上市当日小订、无小订记录、上市日后残余，四项互斥完备。',
          '\n分解：(P主-P标)×r标 + P主×(r主-r标) = 池锁单事件差。仅算术，不代表因果。',
          '\n窗口：'+str(ctx['windows']), '\n输入 SHA256：'+str(ctx['input_fingerprints']),
          '\n限制：', *['- '+w for w in _warnings(ctx)],
          '\n本次不提供：', *['- '+q['title']+'：'+q['status']+'；'+q['reason'] for q in ctx['research_plan']['excluded']]]
    return '\n'.join(rows)+'\n'
