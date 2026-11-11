"""Behavioral regression for the v1.2 stable allowlist and delivery gates.

Real-case checks recompute from raw parquet without calling production computation
or filtering helpers. Shared generation assignment remains the canonical contract.
"""
import copy
import json
import os
from pathlib import Path
import re
import sys

import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'workspace'))
from research_scripts import launch_deep_dive as engine
from research_scripts import launch_research_plan as plan
from research_scripts import launch_deep_dive_report as report


def facts():
    return {'main':'A','benchmarks':['B'],'as_of':'2026-11-09','n_days':5,
        'windows':{'A':['2026-11-05','2026-11-10'],'B':['2026-09-23','2026-09-28']},
        'cum':{'A':100,'B':120},'pool':{'A':1000,'B':1200},
        'days_covered':{'A':5,'B':5},'order_number_dup':0,'missing_order_number':0,
        'data_covers_as_of':True,'invalid_event_order':{'A':0,'B':0}}


@pytest.mark.parametrize('field,value',[
    ('data_covers_as_of',False),('order_number_dup',1),('missing_order_number',1),
    ('cum',{'A':29,'B':120}),('pool',{'A':99,'B':1200}),
    ('days_covered',{'A':4,'B':5}),('invalid_event_order',{'A':1,'B':0})])
def test_gate_a_blocks(field,value):
    f=facts();f[field]=value
    assert plan.validate_research_plan(plan.build_research_plan(f),f)['verdict']=='BLOCK'


def test_allowlist_and_single_day():
    f=facts();p=plan.build_research_plan(f)
    assert {q['id'] for q in p['questions']}=={'q1','q2','q3','q4','q5'}
    assert {q['status'] for q in p['excluded']}=={'FAIL','UNVERIFIED'}
    p['questions'].append({'id':'q8','title':'unverified'})
    assert plan.validate_research_plan(p,f)['verdict']=='BLOCK'
    p['questions']=[]
    assert plan.validate_research_plan(p,f)['verdict']=='BLOCK'
    f['n_days']=1;f['days_covered']={'A':1,'B':1}
    g=plan.validate_research_plan(plan.build_research_plan(f),f)
    assert g['verdict']=='PASS' and 'q3' not in g['passed']


def test_future_benchmark_blocks():
    bd={'time_periods':{'A':{'end':'2026-11-05'},'B':{'end':'2026-12-01'}}}
    with pytest.raises(ValueError): engine.build_windows(bd,['A','B'],pd.Timestamp('2026-11-09'))


def test_pool_overlap_not_hidden_by_old_identity():
    # The old tautology passed despite double subtraction. Keep the failure test.
    p={'A':{'pool_total':100,'launch_intent_total':20,'pool_pending':70,
             'pool_locked':20,'pool_refunded':10}}
    q={'A':{'stock_total':120,'locked':25,'refunded':15,'remaining':80,'lock_refund_overlap':4}}
    a=engine.validate_pool_identities(p,q,['A'])['A']
    assert a['checks']['stock_eq_pool_plus_launch']
    assert a['checks']['remaining_eq_locked_refunded']
    assert not a['ok'] and not a['checks']['events_disjoint']
    del q['A']['lock_refund_overlap']
    assert not engine.validate_pool_identities(p,q,['A'])['A']['ok']


def independent_counts(gen,benches,as_of):
    bd=json.loads(engine.BUSINESS_DEF.read_text())
    raw=pd.read_parquet(engine.ORDER_PARQUET)
    for c in engine.TIME_COLUMNS: raw[c]=pd.to_datetime(raw[c],errors='coerce')
    from utils.monitors.series_group import apply_series_group_logic
    raw=apply_series_group_logic(raw,bd)
    store=raw.store_name.fillna('');identity=raw.buyer_identity_no.fillna('').astype(str)
    hq=(bd.get('monitor',{}).get('test_order_filter',{}).get('hq_stores') or ['总部主理店'])
    fake=~identity.str.fullmatch(r'\d{17}[\dXx]') & ~identity.str.lower().isin(['','nan','none','null'])
    clean=~(store.isin(hq)&fake)&store.ne('总部主理店')
    retail=raw[clean & raw.order_type.eq('用户车')]
    pool=raw[clean & raw.order_type.fillna('').isin(['用户车',''])]
    n=(pd.Timestamp(as_of)-pd.Timestamp(bd['time_periods'][gen]['end']).normalize()).days+1
    result={}
    for g in [gen]+benches:
        t0=pd.Timestamp(bd['time_periods'][g]['end']).normalize();end=t0+pd.Timedelta(days=n)
        locks=retail[retail.series_group_logic.eq(g)&retail.lock_time.between(t0,end,inclusive='left')]
        pre=pool[pool.series_group_logic.eq(g)&pool.intention_payment_time.lt(t0)]
        locked=pre.lock_time.lt(end); refunded=pre.intention_refund_time.lt(end)
        daily=[locks.loc[locks.lock_time.dt.normalize().eq(t0+pd.Timedelta(days=i)),'order_number'].nunique() for i in range(n)]
        ip=locks.intention_payment_time
        origins={'pre':int(ip.lt(t0).sum()),'launch_day':int(ip.between(t0,t0+pd.Timedelta(days=1),inclusive='left').sum()),
                 'none':int(ip.isna().sum()),'post_launch':int(ip.ge(t0+pd.Timedelta(days=1)).sum())}
        result[g]={'daily':[int(v) for v in daily], 'cum':int(locks.order_number.nunique()),
             'pool_total':int(pre.order_number.nunique()),'pool_locked':int(pre.loc[locked,'order_number'].nunique()),
             'pool_refunded':int(pre.loc[refunded,'order_number'].nunique()),
             'overlap':int(pre.loc[locked&refunded,'order_number'].nunique()),'origin':origins}
    return result


@pytest.fixture(scope='module',params=[('CM3',['LS8','LS9'],'2026-09-27'),('LS8Neo',['CM3','LS8'],'2026-11-09')],ids=['CM3','LS8Neo'])
def real_case(request,tmp_path_factory):
    gen,benches,date=request.param
    base=Path(os.environ.get('STABLE_REGRESSION_OUTPUT_DIR',str(tmp_path_factory.mktemp('launch_stable'))))
    destination=base/gen
    argv=['--gen',gen,'--benchmarks',*benches,'--as-of',date,'--format','all','--output',str(destination)]
    assert engine.main(argv)==0
    case_dir=destination/'vehicle_launch_v12_stable'/f'{gen}_D5_{date}'
    ctx=json.loads((case_dir/'tables/metrics.json').read_text())
    raw=independent_counts(gen,benches,date)
    return ctx,case_dir,argv,raw


def test_real_case_independent_every_retained_capability(real_case):
    ctx,case_dir,_,raw=real_case
    checks={k:[] for k in sorted(plan.PASS_IDS)}
    for g,r in raw.items():
        c=ctx['curves']['curves'][g]
        assert c['daily']==r['daily'] and c['cum'][-1]==r['cum'];checks['q1'].append(g);checks['q2'].append(g)
        d=ctx['dynamics'][g]
        assert d['d1_share_of_cum']==pytest.approx(r['daily'][0]/r['cum'])
        assert d['tail_avg']==pytest.approx(sum(r['daily'][1:])/4);checks['q3'].append(g)
        p=ctx['presale'][g]
        for key in ('pool_total','pool_locked','pool_refunded'): assert p[key]==r[key]
        assert p['lock_refund_overlap']==r['overlap']
        assert p['pool_lock_rate']==pytest.approx(r['pool_locked']/r['pool_total']);checks['q4'].append(g)
        for key,count in r['origin'].items(): assert ctx['origin'][g][key]==count
        assert sum(r['origin'].values())==r['cum'];checks['q5'].append(g)
    m=raw[ctx['main']]
    for b in ctx['benchmarks']:
        r=raw[b];s=ctx['source_decomp'][b]
        assert s['presale_scale_effect']==pytest.approx((m['pool_total']-r['pool_total'])*r['pool_locked']/r['pool_total'])
        assert s['presale_rate_effect']==pytest.approx(m['pool_total']*(m['pool_locked']/m['pool_total']-r['pool_locked']/r['pool_total']))
        assert ctx['deltas'][b]['cum_diff']==m['cum']-r['cum']
        assert s['gap_total']==sum(s[k+'_diff'] for k in ('pre','launch_day','none','post_launch'))
    assert ctx['gate_b']['verdict']==ctx['gate_c']['verdict']=='PASS'
    for key in ('network','geo','product','same_battery','slice_compares','quality','forward','pk','pool','narrative'):
        assert key not in ctx
    assert all('pending' not in k and 'remaining' not in k for p in ctx['presale'].values() for k in p)
    evidence={'case':ctx['main'],'as_of':ctx['as_of'],'input_fingerprints':ctx['input_fingerprints'],
       'capabilities':{k:{'status':'PASS','independent_generations':v} for k,v in checks.items()},
       'raw_counts':raw,'gate_b_checks':ctx['gate_b']['checked'],'gate_c_cells':ctx['gate_c']['checked_cells']}
    (case_dir/'independent_evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))


def test_real_case_reproducibility(real_case):
    ctx,case_dir,argv,_=real_case
    contract=json.loads((case_dir/'result_contract.json').read_text())
    files=[Path(path) for path in contract['artifacts'].values()]
    before={str(p.relative_to(case_dir)):p.read_text(encoding='utf-8-sig') for p in files}
    assert engine.main(argv)==0
    regenerated=json.loads((case_dir/'tables/metrics.json').read_text())['generated_at']
    for name,text in before.items():
        after=(case_dir/name).read_text(encoding='utf-8-sig')
        assert text.replace(ctx['generated_at'],'<TIME>')==after.replace(regenerated,'<TIME>'),name
    (case_dir/'reproducibility.json').write_text(json.dumps({'status':'PASS','compared_files':sorted(before),
                                                         'excluded_field':'generated_at'},indent=2))


def test_real_case_mutations_and_gates(real_case,monkeypatch,tmp_path):
    ctx,case_dir,argv,_=real_case
    f=copy.deepcopy(ctx['findings']);f[0]['numbers'][next(iter(f[0]['numbers']))]+=1
    assert plan.validate_findings(f,ctx)['verdict']=='FAIL'
    f=copy.deepcopy(ctx['findings']);f[0]['direction']='ahead' if f[0]['direction']!='ahead' else 'behind'
    assert plan.validate_findings(f,ctx)['verdict']=='FAIL'
    assert plan.validate_findings(ctx['findings'][:-1],ctx)['verdict']=='FAIL'
    mutated=copy.deepcopy(ctx);b=ctx['benchmarks'][0]
    mutated['source_decomp'][b]['presale_scale_effect']+=1
    mutated['source_decomp'][b]['presale_rate_effect']-=1
    assert plan.validate_findings(plan.compute_findings(mutated),mutated)['verdict']=='FAIL'
    original=report.render_report(ctx)
    bad=original.replace('data-path="deltas.'+b+'.cum_main">','data-path="deltas.'+b+'.cum_main">9',1)
    assert plan.validate_report(bad,ctx['findings'],ctx)['verdict']=='FAIL'
    bad=original.replace(ctx['findings'][0]['title'],'wrong finding')
    assert plan.validate_report(bad,ctx['findings'],ctx)['verdict']=='FAIL'
    # Gate failures must not write success artifacts. Use an already computed context
    # so this exercises delivery behavior without repeating the raw-data regression.
    monkeypatch.setattr(engine,'input_fingerprints',lambda:{})
    monkeypatch.setattr(engine,'_load_inputs',lambda:(None,None))
    monkeypatch.setattr(engine,'probe_research',lambda *a,**kw:ctx['audit'])
    monkeypatch.setattr(engine,'build_context',lambda *a,**kw:(copy.deepcopy(ctx),None))
    call=argv[:-1]+[str(tmp_path/'blocked')]
    with monkeypatch.context() as mp:
        mp.setattr(plan,'validate_report',lambda *a,**k:{'verdict':'FAIL','issues':['injected']})
        assert engine.main(call)==3
        assert not (tmp_path/'blocked').exists()
    broken=copy.deepcopy(ctx);broken['gate_b']={'verdict':'FAIL','failed':['injected']}
    monkeypatch.setattr(engine,'build_context',lambda *a,**kw:(broken,None))
    assert engine.main(call)==3
    assert not (tmp_path/'blocked').exists()
