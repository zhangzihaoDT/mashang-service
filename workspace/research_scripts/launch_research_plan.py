"""v1.2 stable allowlist and the existing A/B/C quality gates.

Capability certification (PASS/UNVERIFIED/FAIL) is separate from per-run Gate A.
No default-pass questions, heuristic narratives, or causal business judgments.
"""
from __future__ import annotations

import html
import math
import re
from html.parser import HTMLParser

QUESTION_SPECS = [
    {'id':'q1','title':'等生命周期累计锁单','status':'PASS','needs':['locks'],'outputs':['cumulative']},
    {'id':'q2','title':'日增与差额形成','status':'PASS','needs':['locks'],'outputs':['daily','gaps']},
    {'id':'q3','title':'首日占比与尾段日均（描述性）','status':'PASS','needs':['locks'],'outputs':['dynamics']},
    {'id':'q4','title':'上市前小订池事件与算术分解','status':'PASS','needs':['presale'],'outputs':['presale','decomposition']},
    {'id':'q5','title':'锁单来源构成（含残余）','status':'PASS','needs':['origin'],'outputs':['origin']},
    {'id':'q6','title':'区域与渠道专题','status':'UNVERIFIED','reason':'未完成独立的计算、结论、呈现联合验收'},
    {'id':'q7','title':'网络与单店专题','status':'UNVERIFIED','reason':'原始描述与归因未分离；舍入后网络分解及主次判断已判 FAIL'},
    {'id':'q8','title':'产品配置与客群','status':'UNVERIFIED','reason':'局部数字核验不等于跨代际完整能力验证'},
    {'id':'q8b','title':'同档客群','status':'UNVERIFIED','reason':'相同电量不足以证明产品与客群可比，旧崩溃修复仅证明可运行'},
    {'id':'q8c','title':'座椅及跨代际六座','status':'UNVERIFIED','reason':'CM3 缺字段，未形成两个案例的有效比较证据'},
    {'id':'q8d','title':'版本缺口解释差额','status':'FAIL','reason':'把同电量存在性当版本可比依据，固定缺口及贡献占比判断不成立'},
    {'id':'q9','title':'订单质量与交付兑现','status':'UNVERIFIED','reason':'历史快照回填与事件语义未完成独立验证'},
    {'id':'q10','title':'待转化、封盘剩余池与未来潜力','status':'FAIL','reason':'锁单与小订退款事件重叠，直接相减重复扣除；流出速度混入非池锁单'},
    {'id':'pk','title':'竞争 PK','status':'UNVERIFIED','reason':'series 粒度与代际粒度不一致，观察周可越过截止日'},
    {'id':'context','title':'延长曲线与 PNG 导出','status':'UNVERIFIED','reason':'不属于本次已验证的正式交付范围'},
    {'id':'verdict','title':'经营主因、需求与购买力判断','status':'FAIL','reason':'量纲混比、由占比推断流程、历史固定文案均缺乏成立依据'},
]
PASS_IDS = {q['id'] for q in QUESTION_SPECS if q['status']=='PASS'}
MIN_LOCKS=30
SMALL_GAP_RATIO=0.05


def build_research_plan(facts: dict) -> dict:
    main=facts['main']; benches=facts['benchmarks']
    gaps={b:facts['cum'][main]-facts['cum'][b] for b in benches}
    return {'version':'1.2-stable','main':main,'benchmarks':benches,
            'as_of':facts['as_of'],'n_days':facts['n_days'],'windows':facts['windows'],
            'questions':[{**q,'required':q['id']!='q3','compares':[main]+benches,
                          'data_deps':q['needs'],'fallback':'block' if q['id']!='q3' else 'skip_and_record'}
                         for q in QUESTION_SPECS if q['status']=='PASS'],
            'excluded':[{**q,'disposition':'本次不提供分析'} for q in QUESTION_SPECS if q['status']!='PASS'],
            'global_constraints':{'gap_values':gaps,
                'small_gap_by_benchmark':{b:abs(v)<=SMALL_GAP_RATIO*max(facts['cum'][main],1) for b,v in gaps.items()},
                'disable_share_of_gap':True},
            'narrative_policy':{'facts_only':True,'no_preset_verdict':True,'inherit_previous_findings':False}}


def validate_research_plan(plan: dict, facts: dict) -> dict:
    results=[]; reasons=[]; gens=[facts['main']]+facts['benchmarks']
    if not facts['data_covers_as_of']: reasons.append('锁单快照未覆盖 as-of，禁止缺日补零')
    if facts['order_number_dup'] or facts['missing_order_number']: reasons.append('订单主键重复或缺失')
    if any(facts['cum'][g]<MIN_LOCKS for g in gens): reasons.append('任一代际窗口锁单不足 30')
    if any(facts['days_covered'][g]!=facts['n_days'] for g in gens):
        reasons.append('窗口存在无记录日期，无法区分零值和缺失，本次阻断')
    if any(facts['invalid_event_order'][g] for g in gens): reasons.append('支付/锁单/退款事件时间逆序')
    ids=[q['id'] for q in plan['questions']]
    if set(ids)!=PASS_IDS or len(ids)!=len(set(ids)):
        reasons.append('研究计划必须严格使用已验证能力白名单')
    for q in plan['questions']:
        status='PASS'; reason='能力已验证；本次字段、窗口、样本与主键检查通过'
        if reasons: status='BLOCK'; reason='；'.join(reasons)
        elif q['id']=='q4' and any(facts['pool'][g]<100 for g in gens):
            status='BLOCK';reason='任一代际上市前小订池不足 100'
        elif q['id']=='q3' and facts['n_days']<2:
            status='SKIP';reason='单日窗口没有尾段，本次不提供尾段分析'
        results.append({'id':q['id'],'title':q['title'],'status':status,'reason':reason})
    blocked=[r for r in results if r['status']=='BLOCK']
    # Empty/mutated plans must fail closed as well.
    if reasons and not blocked: blocked=[{'id':'plan','status':'BLOCK','reason':'；'.join(reasons)}]
    return {'gate':'A','verdict':'BLOCK' if blocked else 'PASS','results':results,
            'passed':[r['id'] for r in results if r['status']=='PASS'],
            'skipped':[r for r in results if r['status']=='SKIP'],'blocked':blocked,
            'notes':['能力 PASS 与本次 Gate A PASS 分别核验；未验证专题不进入计划或计算。']}


def direction(v):
    return 'ahead' if v>0 else ('behind' if v<0 else 'equal')


def value_at(ctx: dict, path: str):
    value=ctx
    for key in path.split('.'):
        value=value[int(key)] if isinstance(value,list) else value[key]
    return value


def number_text(value):
    if value is None: return '—'
    if isinstance(value,float): return f'{value:,.4f}'.rstrip('0').rstrip('.')
    if isinstance(value,int): return f'{value:,}'
    return str(value)


def compute_findings(ctx: dict) -> list[dict]:
    main=ctx['main']; n=ctx['n_days']; out=[]; allowed=set(ctx['gate_a']['passed'])
    def add(qid,bench,title,body,paths,dir_='descriptive'):
        if qid not in allowed: return
        out.append({'id':f'{qid}_{bench}','question':qid,'title':title,'body':body,
                    'evidence':paths,'numbers':{p:value_at(ctx,p) for p in paths},
                    'direction':dir_,'scope':f'{main} vs {bench}；各自 D1–D{n}；当前快照事件截断'})
    for b in ctx['benchmarks']:
        d=ctx['deltas'][b]; pm=ctx['presale'][main]; pb=ctx['presale'][b]; de=ctx['source_decomp'][b]
        add('q1',b,f'{main} 对 {b} 累计差 {d["cum_diff"]:+,} 单',
            f'{main} {d["cum_main"]:,} 单，{b} {d["cum_bench"]:,} 单；比值 {d["cum_ratio"]:.4f}。',
            [f'deltas.{b}.{k}' for k in ('cum_main','cum_bench','cum_diff','cum_ratio')],direction(d['cum_diff']))
        add('q2',b,f'对 {b} 的首日及后续差额',
            f'D1 差额 {d["d1_diff"]:+,} 单，'+
            (f'D2–D{n} 合计差额 {d["tail_diff"]:+,} 单；' if n>1 else '无尾段；')+
            f'合计 {d["cum_diff"]:+,} 单。',
            [f'deltas.{b}.{k}' for k in ('d1_diff','tail_diff','cum_diff')],direction(d['cum_diff']))
        if 'q3' in allowed:
            m=ctx['dynamics'][main]; k=ctx['dynamics'][b]
            add('q3',b,f'对 {b} 的观察期节奏',
                f'D1 占比 {m["d1_share_of_cum"]:.1%} vs {k["d1_share_of_cum"]:.1%}；'
                f'D2–D{n} 日均 {m["tail_avg"]:.1f} vs {k["tail_avg"]:.1f} 单。',
                [f'dynamics.{g}.{key}' for g in (main,b) for key in ('d1_share_of_cum','tail_avg')])
        add('q4',b,f'对 {b} 的上市前小订池事件分解',
            f'池总量 {pm["pool_total"]:,} vs {pb["pool_total"]:,}；锁单事件率 '
            f'{pm["pool_lock_rate"]:.1%} vs {pb["pool_lock_rate"]:.1%}。'
            f'规模项 {de["presale_scale_effect"]:+.1f} 单，率项 {de["presale_rate_effect"]:+.1f} 单，'
            f'合计 {de["pool_locked_diff"]:+,} 单；仅为算术分解，不判断经营主因。',
            [f'presale.{g}.{key}' for g in (main,b) for key in ('pool_total','pool_lock_rate')]+
            [f'source_decomp.{b}.{key}' for key in ('presale_scale_effect','presale_rate_effect','pool_locked_diff')])
        o=ctx['origin'][main]; k=ctx['origin'][b]
        add('q5',b,f'对 {b} 的锁单来源构成',
            f'上市前小订转锁 {o["pre"]:,} vs {k["pre"]:,}；上市当日新增小订转锁 '
            f'{o["launch_day"]:,} vs {k["launch_day"]:,}；无小订记录 {o["none"]:,} vs {k["none"]:,}；'
            f'上市日后小订残余 {o["post_launch"]:,} vs {k["post_launch"]:,}。不据占比推断下单流程或需求。',
            [f'origin.{g}.{key}' for g in (main,b) for key in ('pre','launch_day','none','post_launch')])
    return out


def validate_findings(findings: list[dict], ctx: dict) -> dict:
    """Gate B: check all bindings/directions plus independent arithmetic identities."""
    checks=[]
    def check(name,ok): checks.append({'check':name,'ok':bool(ok)})
    check('gate_a_pass',ctx['gate_a']['verdict']=='PASS')
    canonical=compute_findings(ctx)
    check('finding_set_complete',len(findings)==len(canonical) and {f['id'] for f in findings}=={f['id'] for f in canonical})
    expected={f['id']:f for f in canonical}
    for f in findings:
        check('numbers_direction_text_'+f['id'],f==expected.get(f['id']))
    for g,c in ctx['curves']['curves'].items():
        check(g+'_nonnegative_daily',all(isinstance(v,int) and v>=0 for v in c['daily']))
        check(g+'_cumulative',c['cum']==[sum(c['daily'][:i+1]) for i in range(ctx['n_days'])])
        o=ctx['origin'][g]; p=ctx['presale'][g]
        check(g+'_source_identity',sum(o[k] for k in ('pre','launch_day','none','post_launch'))==o['total']==c['cum'][-1])
        for key in ('pre','launch_day','none','post_launch'):
            check(g+'_source_daily_'+key,sum(day[key] for day in o['by_day'].values())==o[key])
            check(g+'_source_share_'+key,math.isclose(o[key+'_share'],o[key]/o['total'],abs_tol=0.00005))
        check(g+'_pool_rate',math.isclose(p['pool_lock_rate'],p['pool_locked']/p['pool_total'],abs_tol=1e-12))
        check(g+'_refund_rate',math.isclose(p['pool_refund_rate'],p['pool_refunded']/p['pool_total'],abs_tol=1e-12))
        check(g+'_pool_events',0<=p['lock_refund_overlap']<=min(p['pool_locked'],p['pool_refunded'])
              and max(p['pool_locked'],p['pool_refunded'])<=p['pool_total'])
        # Keeps the old pool/source reconciliation prerequisite; no guessed repair.
        check(g+'_pool_locks_equal_window_source',p['pool_locked']==o['pre'])
        if 'dynamics' in ctx:
            d=ctx['dynamics'][g]
            check(g+'_dynamics',d=={'d1':c['daily'][0],'cum_total':c['cum'][-1],
                  'd1_share_of_cum':c['daily'][0]/c['cum'][-1], 'tail_days':ctx['n_days']-1,
                  'tail_avg':sum(c['daily'][1:])/(ctx['n_days']-1)})
    main=ctx['main'];cur=ctx['curves']['curves']
    for b,d in ctx['deltas'].items():
        check(b+'_delta_identity',d['d1_diff']+d['tail_diff']==d['cum_diff']==cur[main]['cum'][-1]-cur[b]['cum'][-1])
        check(b+'_d1_tail',d['d1_diff']==cur[main]['daily'][0]-cur[b]['daily'][0] and d['tail_diff']==sum(cur[main]['daily'][1:])-sum(cur[b]['daily'][1:]))
        check(b+'_ratio',math.isclose(d['cum_ratio'],cur[main]['cum'][-1]/cur[b]['cum'][-1],abs_tol=1e-12))
        gap=ctx['curves']['gaps'][b]
        check(b+'_marginal',gap['marginal']==[a-z for a,z in zip(cur[main]['daily'],cur[b]['daily'])])
        check(b+'_gap_curve',gap['cum_gap']==[a-z for a,z in zip(cur[main]['cum'],cur[b]['cum'])])
        s=ctx['source_decomp'][b]
        check(b+'_source_gap',sum(s[k+'_diff'] for k in ('pre','launch_day','none','post_launch'))==s['gap_total']==d['cum_diff'])
        pm,pb=ctx['presale'][main],ctx['presale'][b]
        check(b+'_pool_components',math.isclose(s['presale_scale_effect'],(pm['pool_total']-pb['pool_total'])*pb['pool_lock_rate'],abs_tol=1e-8) and math.isclose(s['presale_rate_effect'],pm['pool_total']*(pm['pool_lock_rate']-pb['pool_lock_rate']),abs_tol=1e-8) and s['pool_locked_diff']==pm['pool_locked']-pb['pool_locked'])
        check(b+'_pool_decomposition',math.isclose(s['presale_scale_effect']+s['presale_rate_effect'],s['pool_locked_diff'],abs_tol=1e-8))
    failed=[c['check'] for c in checks if not c['ok']]
    return {'gate':'B','verdict':'FAIL' if failed else 'PASS','checks':checks,'failed':failed,'checked':len(checks)}


class _Cells(HTMLParser):
    def __init__(self):
        super().__init__(); self.cells=[]; self.active=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='td' and 'data-path' in attrs: self.active=[attrs['data-path'],'']
    def handle_data(self,data):
        if self.active is not None: self.active[1]+=data
    def handle_endtag(self,tag):
        if tag=='td' and self.active is not None:
            self.cells.append(self.active);self.active=None


def validate_report(report: str, findings: list[dict], ctx: dict) -> dict:
    """Gate C checks rendered numeric cells, findings and exclusion disclosures."""
    from research_scripts.launch_deep_dive_report import report_tables
    issues=[];plain=html.unescape(re.sub(r'<[^>]+>','',report))
    for f in findings:
        if f['title'] not in plain or f['body'] not in plain: issues.append('结论缺失或被改写：'+f['id'])
    parser=_Cells();parser.feed(report)
    expected=[path for _,_,rows in report_tables(ctx) for row in rows for path in row]
    if [p for p,_ in parser.cells]!=expected: issues.append('报告指标绑定清单不完整或次序不符')
    for path,shown in parser.cells:
        try:
            if shown!=number_text(value_at(ctx,path)): issues.append('显示数值不一致：'+path)
        except (KeyError,IndexError,TypeError): issues.append('未知指标路径：'+path)
    for q in ctx['research_plan']['excluded']:
        if q['title'] not in plain or q['reason'] not in plain: issues.append('缺少未提供分析说明：'+q['id'])
    # Preserve and strengthen the prior contradiction checks.
    ratio=ctx['deltas'][ctx['benchmarks'][0]]['cum_ratio']
    forbidden=['落后四成','落后四 成'] if ratio>=0.9 else []
    if ratio>=1: forbidden+=['全面落后','持续失速']
    forbidden+=['转化率差异相对次要','下单链路一致：','剩余潜力预计','占总差额']
    for phrase in forbidden:
        if phrase in plain: issues.append('报告出现不成立判断：'+phrase)
    return {'gate':'C','verdict':'FAIL' if issues else 'PASS','issues':issues,
            'checked_findings':len(findings),'checked_cells':len(parser.cells)}
