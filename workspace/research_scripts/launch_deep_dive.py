#!/usr/bin/env python3
"""vehicle-launch-deep-dive v1.2 stable: verified descriptive comparisons only."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS = REPO_ROOT / "workspace"
for _p in (str(REPO_ROOT), str(_WS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.monitors.order_filter import flag_test_orders
from utils.monitors.phase import load_business_definition
from utils.monitors.series_group import apply_series_group_logic

BUSINESS_DEF = REPO_ROOT / "shared/schema/business_definition.json"
ORDER_PARQUET = REPO_ROOT / "dataset/order_data.parquet"
NON_RETAIL = {"试驾车", "大客户", "员工", "集团员工", "经销商员工", "享道",
              "仅批售", "项目", "展车", "海外"}
TIME_COLUMNS = ["lock_time", "intention_payment_time", "intention_refund_time",
                "order_create_date"]

def _non_user_mask(df: pd.DataFrame) -> pd.Series:
    ot = df["order_type"].fillna("").astype("string")
    return ot.isin(NON_RETAIL) | (ot.ne("") & ot.ne("用户车"))



def _hq_mask(df: pd.DataFrame) -> pd.Series:
    return df["store_name"].astype("string").eq("总部主理店")



def lock_mask(df: pd.DataFrame, bd: dict) -> pd.Series:
    """锁单口径：用户单零售（严格 用户车），剔除测试单 / 内测店 / 非零售类型。"""
    ot = df["order_type"].fillna("").astype("string")
    return (ot.eq("用户车") & ~flag_test_orders(df, bd)
            & ~_hq_mask(df) & ~_non_user_mask(df))



def pool_mask(df: pd.DataFrame, bd: dict) -> pd.Series:
    """小订池口径：允许 order_type 未回填（空），其余同锁单口径。"""
    ot = df["order_type"].fillna("").astype("string")
    return (ot.isin(["", "用户车"]) & ~flag_test_orders(df, bd)
            & ~_hq_mask(df) & ~_non_user_mask(df))



def retail_mask(df: pd.DataFrame, bd: dict) -> pd.Series:  # 兼容旧调用名
    return lock_mask(df, bd)



def exclusion_report(df: pd.DataFrame, bd: dict, win: dict) -> dict:
    """各代际的剔除量（审计用）：测试单 / 内测店 / 非零售类型 / 空类型。"""
    ot = df["order_type"].fillna("").astype("string")
    test = flag_test_orders(df, bd)
    hq = _hq_mask(df)
    out = {}
    for g, w in win["windows"].items():
        t0, hi = w["launch"], w["window_end"]
        in_win = (df["series_group_logic"].eq(g) & df["lock_time"].notna()
                  & (df["lock_time"] >= t0) & (df["lock_time"] < hi))
        pool = (df["series_group_logic"].eq(g) & df["intention_payment_time"].notna()
                & (df["intention_payment_time"] < t0 + pd.Timedelta(days=1)))
        out[g] = {
            "lock_test_orders": int(df.loc[in_win & test, "order_number"].nunique()),
            "lock_hq_orders": int(df.loc[in_win & hq & ~test, "order_number"].nunique()),
            "lock_non_retail": int(df.loc[in_win & ~hq & ~test & _non_user_mask(df),
                                   "order_number"].nunique()),
            "lock_blank_type": int(df.loc[in_win & ~hq & ~test & ot.eq(""),
                                    "order_number"].nunique()),
            "pool_test_orders": int(df.loc[pool & test, "order_number"].nunique()),
            "pool_hq_orders": int(df.loc[pool & hq & ~test, "order_number"].nunique()),
            "pool_non_retail": int(df.loc[pool & ~hq & ~test & _non_user_mask(df),
                                    "order_number"].nunique()),
            "pool_blank_type": int(df.loc[pool & ~hq & ~test & ot.eq(""),
                                    "order_number"].nunique()),
        }
    return out



def resolve_gen(bd: dict, token: str) -> str:
    """把用户输入的代际 token（LS8NEO / ls8neo / 显示名）解析成 series_group_logic 键。

    只认业务配置：先精确匹配 key，再忽略大小写匹配 key，最后匹配 model_series_mapping
    的族名或 monitor.series_labels 显示名。不做前缀/子串猜测。
    """
    token = str(token).strip()
    keys = list((bd.get("series_group_logic") or {}).keys())
    if token in keys:
        return token
    low = {k.lower(): k for k in keys}
    if token.lower() in low:
        return low[token.lower()]
    labels = (bd.get("monitor") or {}).get("series_labels") or {}
    for k, v in labels.items():
        if token == v:
            return k
    raise SystemExit(
        f"无法解析代际 '{token}'：不在 series_group_logic 键 {keys} 中，"
        f"也不是已知显示名 {list(labels.values())}"
    )



def launch_day(bd: dict, gen: str) -> pd.Timestamp:
    tp = (bd.get("time_periods") or {}).get(gen) or {}
    if not tp.get("end"):
        raise SystemExit(f"business_definition.time_periods.{gen}.end 缺失，无法确定上市日")
    return pd.Timestamp(tp["end"]).normalize()



def presale_start_day(bd: dict, gen: str) -> pd.Timestamp | None:
    tp = (bd.get("time_periods") or {}).get(gen) or {}
    return pd.Timestamp(tp["start"]).normalize() if tp.get("start") else None



def build_windows(bd: dict, gens: list[str], as_of: pd.Timestamp) -> dict:
    """统一生命周期窗口：主代际 N 天，所有对标代际只取自身前 N 天。"""
    main = gens[0]
    t0 = launch_day(bd, main)
    intended = int((as_of.normalize() - t0).days) + 1
    if intended <= 0:
        raise SystemExit(f"as-of {as_of.date()} 早于 {main} 上市日 {t0.date()}，窗口无效")

    # 等窗口上限：任一参照代际的上市日若晚于主代际，其自身可观察天数可能不足 N 天。
    # 此时按「所有代际都能覆盖的最大等长天数」收窗，绝不把缺失日期补零。
    avail = {}
    for g in gens:
        la = launch_day(bd, g)
        avail[g] = max(int((as_of.normalize() - la).days) + 1, 0)
    if any(v <= 0 for v in avail.values()):
        raise ValueError("至少一个代际在 as-of 之前无可用窗口")
    n_days = min([intended] + list(avail.values()))
    if n_days <= 0:
        raise SystemExit("至少一个代际在 as-of 之前无可用窗口，无法等窗口比较")
    capped = n_days < intended

    out = {}
    for g in gens:
        la = launch_day(bd, g)
        out[g] = {
            "gen": g,
            "launch": la,
            "n_days": n_days,
            "n_days_intended": intended,
            "available_days": avail[g],
            "window_end": la + pd.Timedelta(days=n_days),  # 左闭右开
            "presale_start": presale_start_day(bd, g),
            "weekdays": [d.strftime("%a") for d in pd.date_range(la, periods=n_days)],
        }
    return {"main": main, "n_days": n_days, "n_days_intended": intended,
            "window_capped": capped, "as_of": as_of.normalize(),
            "last_date": as_of.normalize(), "gens": gens, "windows": out}



def compute_curves(df: pd.DataFrame, win: dict) -> dict:
    """每日新增 / 累计锁单（D1..DN），以及相对两个对标的累计差额与边际差额。"""
    n = win["n_days"]
    curves: dict[str, dict] = {}
    for g, w in win["windows"].items():
        lo, hi = w["launch"], w["window_end"]
        sub = df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
                 & (df["lock_time"] >= lo) & (df["lock_time"] < hi)]
        daily = (sub.groupby(sub["lock_time"].dt.normalize())["order_number"]
                 .nunique().reindex(pd.date_range(lo, hi - pd.Timedelta(days=1)),
                                    fill_value=0).astype(int))
        curves[g] = {
            "gen": g,
            "launch": lo.date().isoformat(),
            "dates": [d.date().isoformat() for d in daily.index],
            "weekdays": w["weekdays"],
            "daily": [int(v) for v in daily.values],
            "cum": [int(v) for v in daily.cumsum().values],
        }

    main = win["main"]
    m = curves[main]
    gaps = {}
    for g in win["gens"]:
        if g == main:
            continue
        b = curves[g]
        cum_gap, marg = [], []
        for d in range(n):
            gd = m["cum"][d] - b["cum"][d]
            cum_gap.append(int(gd))
            marg.append(int(gd - cum_gap[d - 1]) if d else int(gd))
        gaps[g] = {"gen": g, "cum_gap": cum_gap, "marginal": marg}
    return {"curves": curves, "gaps": gaps, "n_days": n, "main": main,
            "gens": win["gens"],
            "benchmarks": [g for g in win["gens"] if g != main]}



def compute_origin_split(df: pd.DataFrame, win: dict) -> dict:
    """窗口内零售锁单按来源精确三分：预售小订转锁 / 上市当日新增小订转锁 / 直接锁单。

    小订在上市日 24:00 停收（业务定义），因此：
      预售        = intention_payment_time < T0
      上市当日新增 = T0 <= intention_payment_time < T0 + 1 天
      直接锁单    = 无 intention_payment_time（跳过小订）
    另有极少数小订晚于上市日 24:00（数据残余，各代际 2–4 单），单列为 post_launch，
    不计入上述三类，避免把口径外样本混进主口径。
    """
    out = {}
    for g, w in win["windows"].items():
        t0, hi = w["launch"], w["window_end"]
        day_end = t0 + pd.Timedelta(days=1)
        s = df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
               & (df["lock_time"] >= t0) & (df["lock_time"] < hi)]
        if not len(s):
            out[g] = {"gen": g, "total": 0}
            continue
        ip = s["intention_payment_time"]
        pre = s[ip.notna() & (ip < t0)]
        launch_day = s[ip.notna() & (ip >= t0) & (ip < day_end)]
        post = s[ip.notna() & (ip >= day_end)]
        nopay = s[ip.isna()]
        total = int(s["order_number"].nunique())
        by_day = {}
        for d, grp in s.groupby(s["lock_time"].dt.normalize()):
            gip = grp["intention_payment_time"]
            by_day[d.date().isoformat()] = {
                "pre": int((gip.notna() & (gip < t0)).sum()),
                "launch_day": int((gip.notna() & (gip >= t0) & (gip < day_end)).sum()),
                "post_launch": int((gip.notna() & (gip >= day_end)).sum()),
                "none": int(gip.isna().sum()),
            }
        out[g] = {
            "gen": g, "total": total,
            "pre": int(len(pre)), "launch_day": int(len(launch_day)),
            "post_launch": int(len(post)), "none": int(len(nopay)),
            "pre_share": round(len(pre) / total, 4) if total else None,
            "launch_day_share": round(len(launch_day) / total, 4) if total else None,
            "post_launch_share": round(len(post) / total, 4) if total else None,
            "none_share": round(len(nopay) / total, 4) if total else None,
            "by_day": by_day,
        }
    return out



def validate_pool_identities(presale: dict, pool: dict, gens: list[str]) -> dict:
    """跨口径恒等式校验：预售池待转化 ≠ 封盘池剩余，二者必须能对上。

    stock_total      = pool_total + launch_intent_total
    remaining(封盘)   = pool_pending(预售待转化) + 上市当日新增未转化部分
    """
    out = {}
    for g in gens:
        p_, q_ = presale.get(g) or {}, pool.get(g) or {}
        stock = q_.get("stock_total") or 0
        pool_total = p_.get("pool_total") or 0
        launch_intent = p_.get("launch_intent_total") or 0
        locked = q_.get("locked") or 0
        refunded = q_.get("refunded") or 0
        remaining = q_.get("remaining") or 0
        pool_pending = p_.get("pool_pending") or 0
        launch_remaining = (launch_intent
                            - (locked - (p_.get("pool_locked") or 0))
                            - (refunded - (p_.get("pool_refunded") or 0)))
        checks = {
            "events_disjoint": q_.get("lock_refund_overlap") == 0,
            "nonnegative_parts": min(remaining, pool_pending, launch_remaining) >= 0,
            "stock_eq_pool_plus_launch": stock == pool_total + launch_intent,
            "remaining_eq_locked_refunded": remaining == stock - locked - refunded,
            "remaining_eq_parts": remaining == pool_pending + launch_remaining,
        }
        out[g] = {
            "ok": all(checks.values()),
            "checks": checks,
            "stock_total": stock, "pool_total": pool_total,
            "launch_intent_total": launch_intent,
            "remaining_stock": remaining,
            "remaining_presale_part": pool_pending,
            "remaining_launch_part": launch_remaining,
            "note": ("封盘池剩余 = 预售池待转化 + 上市当日新增未转化；"
                     "两者不是同一指标，报告标签必须区分"),
        }
    return out



def load_orders(bd: dict) -> pd.DataFrame:
    cols = ["order_number", "product_name", "series", "store_name", "order_type",
            "buyer_identity_no", "owner_identity_no"] + TIME_COLUMNS
    df = pd.read_parquet(ORDER_PARQUET, columns=cols)
    for c in TIME_COLUMNS:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    return apply_series_group_logic(df, bd)


def input_fingerprints() -> dict:
    result = {}
    for p in (ORDER_PARQUET, BUSINESS_DEF):
        with p.open('rb') as handle:
            result[str(p.relative_to(REPO_ROOT))] = hashlib.file_digest(handle, 'sha256').hexdigest()
    return result


def probe_research(gen: str, benchmarks: list[str], as_of: pd.Timestamp,
                   *, prepared=None) -> dict:
    """Gate A: inspect inputs only; never compute deferred research topics."""
    bd, raw = prepared if prepared is not None else _load_inputs()
    main = resolve_gen(bd, gen)
    benches = list(dict.fromkeys(resolve_gen(bd, b) for b in benchmarks))
    if main in benches or not benches:
        raise ValueError("至少需要一个不同于主代际的对标，不能自身对比")
    win = build_windows(bd, [main] + benches, as_of)
    df, pool = raw[lock_mask(raw, bd)], raw[pool_mask(raw, bd)]
    selected = pool[pool.series_group_logic.isin(win['gens'])]
    facts = {
        "main": main, "benchmarks": benches, "as_of": str(as_of.date()),
        "n_days": win['n_days'], "window_capped": win['window_capped'],
        "windows": {g: [str(w['launch'].date()), str(w['window_end'].date())]
                    for g, w in win['windows'].items()},
        "cum": {}, "pool": {}, "days_covered": {}, "pool_overlap": {},
        "pool_pre_open": {}, "invalid_event_order": {},
        "order_number_dup": int(selected.order_number.duplicated().sum()),
        "missing_order_number": int(selected.order_number.isna().sum()),
        "data_covers_as_of": bool(df.lock_time.notna().any()
                                  and df.lock_time.max().normalize() >= as_of),
        "max_lock_time": str(df.lock_time.max()),
    }
    for g, w in win['windows'].items():
        t0, hi = w['launch'], w['window_end']
        s = df[df.series_group_logic.eq(g) & df.lock_time.ge(t0) & df.lock_time.lt(hi)]
        p = pool[pool.series_group_logic.eq(g)]
        pre = p[p.intention_payment_time.lt(t0)]
        stock = p[p.intention_payment_time.lt(t0 + pd.Timedelta(days=1))]
        facts['cum'][g] = int(s.order_number.nunique())
        facts['pool'][g] = int(pre.order_number.nunique())
        facts['days_covered'][g] = int(s.lock_time.dt.normalize().nunique())
        facts['pool_overlap'][g] = int((stock.lock_time.lt(hi)
                                        & stock.intention_refund_time.lt(hi)).sum())
        facts['pool_pre_open'][g] = (int(pre.intention_payment_time.lt(w['presale_start']).sum())
                                    if w['presale_start'] is not None else None)
        facts['invalid_event_order'][g] = int((
            s.intention_payment_time.gt(s.lock_time)).sum()) + int((
            stock.intention_refund_time.dt.normalize().lt(stock.intention_payment_time.dt.normalize())).sum())
    return facts


def _load_inputs():
    bd = load_business_definition(BUSINESS_DEF)
    return bd, load_orders(bd)


def compute_dynamics(curves: dict) -> dict:
    """Observed daily counts, not a future momentum or demand judgment."""
    out = {}
    for g, c in curves['curves'].items():
        daily = c['daily']; n = len(daily); total = c['cum'][-1]
        out[g] = {'d1': daily[0], 'cum_total': total,
                  'd1_share_of_cum': daily[0] / total if total else None,
                  'tail_days': n - 1,
                  'tail_avg': sum(daily[1:]) / (n - 1) if n > 1 else None}
    return out


def compute_presale_pool(df: pd.DataFrame, win: dict) -> dict:
    """Keep independently countable events only. Lock and refund may overlap.

    Historical pool definition is all intention payments before launch, including
    pre-open records. It is NOT the strictly configured presale-period cohort.
    """
    out = {}
    for g, w in win['windows'].items():
        t0, hi = w['launch'], w['window_end']
        p = df[df.series_group_logic.eq(g) & df.intention_payment_time.lt(t0)]
        locked = p.lock_time.lt(hi)
        refunded = p.intention_refund_time.lt(hi)
        total = int(p.order_number.nunique())
        out[g] = {
            'gen': g, 'pool_total': total,
            'pool_locked': int(p.loc[locked, 'order_number'].nunique()),
            'pool_refunded': int(p.loc[refunded, 'order_number'].nunique()),
            'lock_refund_overlap': int(p.loc[locked & refunded, 'order_number'].nunique()),
            'presale_pre_open': (int(p.intention_payment_time.lt(w['presale_start']).sum())
                                 if w['presale_start'] is not None else None),
            'presale_days': ((t0 - w['presale_start']).days
                             if w['presale_start'] is not None else None),
        }
        out[g]['pool_lock_rate'] = out[g]['pool_locked'] / total if total else None
        out[g]['pool_refund_rate'] = out[g]['pool_refunded'] / total if total else None
    return out


def compute_source_decomp(ctx: dict) -> dict:
    """Exact additive identities; no contribution shares or causal ranking."""
    out = {}; main = ctx['main']
    for b in ctx['benchmarks']:
        m, k = ctx['origin'][main], ctx['origin'][b]
        pm, pb = ctx['presale'][main], ctx['presale'][b]
        scale = (pm['pool_total'] - pb['pool_total']) * pb['pool_lock_rate']
        rate = pm['pool_total'] * (pm['pool_lock_rate'] - pb['pool_lock_rate'])
        out[b] = {'bench': b, 'gap_total': m['total'] - k['total'],
                  **{f'{v}_diff': m[v] - k[v] for v in ('pre','launch_day','none','post_launch')},
                  'presale_scale_effect': scale, 'presale_rate_effect': rate,
                  'pool_locked_diff': pm['pool_locked'] - pb['pool_locked']}
    return out


def _compute_deltas(ctx: dict) -> dict:
    c = ctx['curves']['curves']; m = c[ctx['main']]
    return {b: {'cum_main': m['cum'][-1], 'cum_bench': c[b]['cum'][-1],
                'cum_diff': m['cum'][-1] - c[b]['cum'][-1],
                'cum_ratio': m['cum'][-1] / c[b]['cum'][-1],
                'd1_diff': m['daily'][0] - c[b]['daily'][0],
                'tail_diff': sum(m['daily'][1:]) - sum(c[b]['daily'][1:])}
            for b in ctx['benchmarks']}


def build_context(gen: str, benchmarks: list[str], as_of: pd.Timestamp,
                  context_days: int = 0, allowed: set[str] | None = None,
                  *, prepared=None, fingerprints=None) -> tuple[dict, pd.DataFrame]:
    from research_scripts.launch_research_plan import (
        build_research_plan, validate_research_plan, compute_findings, validate_findings,
    )
    if context_days:
        raise ValueError('延长参考曲线未纳入稳定能力，本次不提供分析')
    bd, raw = prepared if prepared is not None else _load_inputs()
    facts = probe_research(gen, benchmarks, as_of, prepared=(bd, raw))
    plan = build_research_plan(facts); gate = validate_research_plan(plan, facts)
    if gate['verdict'] != 'PASS':
        raise ValueError('Gate A BLOCK: ' + json.dumps(gate['blocked'], ensure_ascii=False))
    if allowed is not None and set(allowed) != set(gate['passed']):
        raise ValueError('allowed 必须与本次 Gate A PASS 集合一致，不能绕过核验')
    win = build_windows(bd, [facts['main']] + facts['benchmarks'], as_of)
    df = raw[lock_mask(raw, bd)].copy()
    pool_df = raw[pool_mask(raw, bd)].copy()
    ctx = {
        'version': '1.2-stable', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'main': facts['main'], 'benchmarks': facts['benchmarks'], 'as_of': facts['as_of'],
        'n_days': win['n_days'], 'n_days_intended': win['n_days_intended'],
        'window_capped': win['window_capped'], 'input_fingerprints': fingerprints or input_fingerprints(),
        'windows': {g: {'launch': str(w['launch'].date()),
                        'window_end_exclusive': str(w['window_end'].date()),
                        'presale_start': str(w['presale_start'].date()) if w['presale_start'] is not None else None}
                    for g, w in win['windows'].items()},
        'audit': facts, 'exclusions': exclusion_report(raw, bd, win),
        'research_plan': plan, 'gate_a': gate,
        'curves': compute_curves(df, win),
        'presale': compute_presale_pool(pool_df, win),
        'origin': compute_origin_split(df, win),
    }
    if 'q3' in gate['passed']:
        ctx['dynamics'] = compute_dynamics(ctx['curves'])
    ctx['deltas'] = _compute_deltas(ctx)
    ctx['source_decomp'] = compute_source_decomp(ctx)
    ctx['findings'] = compute_findings(ctx)
    ctx['gate_b'] = validate_findings(ctx['findings'], ctx)
    return ctx, df


def _warnings(ctx: dict) -> list[str]:
    warnings = [
        '历史重建使用当前订单快照与事件时间；代际、订单类型及退款等字段可能被事后回填，不等于历史冻结快照。',
        '上市前小订池含早于配置预售开始日的记录，非严格预售期 cohort；预售天数不同，不据此判断需求强弱。',
        '小订退款为日期粒度，只能按日比较；锁单与小订退款事件可重叠；不提供待转化、封盘剩余池、订单质量或后续潜力判断。',
        '无小订记录只表示字段缺失，不能证明下单链路一致或直接需求强弱。',
        '分解是指定基准下的算术恒等式，不是因果归因；不提供贡献占比或经营主次判断。',
    ]
    if ctx['window_capped']:
        warnings.append(f"观察窗口已从 {ctx['n_days_intended']} 天收窄为共同可用的 {ctx['n_days']} 天。")
    return warnings


def save_tables(ctx: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for g, c in ctx['curves']['curves'].items():
        for i, count in enumerate(c['daily']):
            rows.append({'gen':g, 'day':i+1, 'date':c['dates'][i], 'daily':count, 'cum':c['cum'][i]})
    tables = {'daily_cumulative': rows,
              'gap': [{'bench': b, **d} for b,d in ctx['deltas'].items()],
              'presale_events': list(ctx['presale'].values()),
              'origin': [{k:v for k,v in o.items() if k != 'by_day'} for o in ctx['origin'].values()],
              'source_decomposition': list(ctx['source_decomp'].values())}
    paths = {}
    for name, values in tables.items():
        p=out_dir / f'{name}.csv'; pd.DataFrame(values).to_csv(p,index=False,encoding='utf-8-sig')
        paths[name]=str(p)
    p=out_dir/'metrics.json'; p.write_text(json.dumps(ctx,ensure_ascii=False,indent=2,allow_nan=False))
    paths['metrics_json']=str(p)
    p=out_dir/'research_plan.json'
    p.write_text(json.dumps({k:ctx[k] for k in ('research_plan','gate_a','findings','gate_b','gate_c') if k in ctx},
                            ensure_ascii=False,indent=2,allow_nan=False))
    paths['research_plan']=str(p)
    return paths


def build_contract(ctx: dict, artifacts: dict) -> dict:
    ok = ctx['gate_a']['verdict'] == ctx['gate_b']['verdict'] == 'PASS'
    ok = ok and ctx.get('gate_c', {'verdict':'PASS'})['verdict'] == 'PASS'
    return {
        'status':'success' if ok else 'error', 'script':'workspace/research_scripts/launch_deep_dive.py',
        'scope': {'data_source':'dataset/order_data.parquet + shared/schema/business_definition.json',
                  'time_window':{'as_of':ctx['as_of'],'n_days':ctx['n_days'],'windows':ctx['windows']},
                  'filters': {'locks':'用户车，剔除测试单、总部主理店与非零售',
                              'pool':'用户车或空类型，剔除测试单、总部主理店与非零售',
                              'dedup':'order_number 唯一性前置阻断'},
                  'metric_definition':'按 lock_time 统计各代际上市 [T0,T0+N) 零售锁单；上市前小订池 ip<T0，事件截止各自 T0+N。'},
        'result':{'summary':f"{ctx['main']} D1–D{ctx['n_days']}，仅提供已验证的描述性分析。",
                  'metrics':{'cum_locks':{g:c['cum'][-1] for g,c in ctx['curves']['curves'].items()}},
                  'findings':ctx['findings'], 'unavailable':ctx['research_plan']['excluded'],
                  'tables':[{'name':k,'path':v} for k,v in artifacts.items() if k in
                            ('daily_cumulative','gap','presale_events','origin','source_decomposition')]},
        'artifacts':artifacts, 'followup_context':{'main_gen':ctx['main'],'benchmarks':ctx['benchmarks'],
             'metric':'cumulative_retail_lock', 'available_dimensions':['lifecycle_day','presale_origin']},
        'warnings':_warnings(ctx), 'errors':[] if ok else ['质量门禁未通过'],
    }


def main(argv=None) -> int:
    ap=argparse.ArgumentParser(description='vehicle-launch-deep-dive v1.2 stable（仅已验证能力）')
    ap.add_argument('--gen',required=True);ap.add_argument('--benchmarks',nargs='+',required=True)
    ap.add_argument('--as-of',required=True,help='最后完整观察日 YYYY-MM-DD')
    ap.add_argument('--format',choices=['terminal','json','html','all'],default='terminal')
    ap.add_argument('--output',default=str(_WS/'outputs'))
    ap.add_argument('--plan',action='store_true')
    ap.add_argument('--context-days',type=int,default=0,help='稳定版仅接受 0，参考延长线暂不提供')
    ap.add_argument('--export-charts',action='store_true',help='稳定版不提供 PNG 导出（显式报错）')
    args=ap.parse_args(argv)
    from research_scripts.launch_research_plan import build_research_plan,validate_research_plan,validate_report
    try:
        if args.export_charts or args.context_days:
            raise ValueError('参考延长线及 PNG 导出未纳入稳定能力，本次不提供分析；请移除对应参数')
        as_of=pd.Timestamp(args.as_of).normalize()
        before=input_fingerprints();prepared=_load_inputs()
        facts=probe_research(args.gen,args.benchmarks,as_of,prepared=prepared)
        plan=build_research_plan(facts);gate=validate_research_plan(plan,facts)
        if args.plan:
            print(json.dumps({'plan':plan,'gate_a':gate},ensure_ascii=False,indent=2))
            return 3 if gate['verdict']=='BLOCK' else 0
        if gate['verdict']!='PASS':
            raise ValueError('Gate A BLOCK: '+json.dumps(gate['blocked'],ensure_ascii=False))
        ctx,_=build_context(args.gen,args.benchmarks,as_of,prepared=prepared,fingerprints=before)
        if ctx['gate_b']['verdict']!='PASS':
            raise ValueError('Gate B FAIL: '+json.dumps(ctx['gate_b'],ensure_ascii=False))
        from research_scripts.launch_deep_dive_report import render_report,render_method_doc
        # Render in memory and validate before creating any deliverable.
        report=render_report(ctx)
        ctx['gate_c']=validate_report(report,ctx['findings'],ctx)
        if ctx['gate_c']['verdict']!='PASS':
            raise ValueError('Gate C FAIL: '+json.dumps(ctx['gate_c'],ensure_ascii=False))
        if before!=input_fingerprints():
            raise ValueError('计算期间输入数据发生变化，请用稳定快照重新运行')
        out=Path(args.output).resolve()/'vehicle_launch_v12_stable'/f"{ctx['main']}_D{ctx['n_days']}_{ctx['as_of']}"
        paths=save_tables(ctx,out/'tables')
        if args.format in ('html','all'):
            p=out/'report.html';p.write_text(report,encoding='utf-8');paths['report_html']=str(p)
        p=out/'method.md';p.write_text(render_method_doc(ctx),encoding='utf-8');paths['method_doc']=str(p)
        paths['result_contract']=str(out/'result_contract.json')
        contract=build_contract(ctx,paths)
        (out/'result_contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2,allow_nan=False))
        if args.format in ('json','all'):
            print(json.dumps(contract,ensure_ascii=False,indent=2,allow_nan=False))
        else:
            print('[Summary]\n'+contract['result']['summary'])
            print('[Scope]\n'+json.dumps(contract['scope'],ensure_ascii=False))
            print('[Result]\n'+'\n'.join(f['body'] for f in ctx['findings']))
            print('[Output]\n'+str(out))
        return 0
    except (ValueError,KeyError,OSError) as exc:
        print(json.dumps({'status':'error','script':'workspace/research_scripts/launch_deep_dive.py',
                         'scope':{'gen':args.gen,'benchmarks':args.benchmarks,'as_of':args.as_of},
                         'result':{},'followup_context':{},'artifacts':{},'errors':[str(exc)]},ensure_ascii=False))
        return 3


if __name__=='__main__':
    raise SystemExit(main())
