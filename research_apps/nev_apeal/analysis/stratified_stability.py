"""Stratified stability test: International vs DomesticTraditional residual premium.

Last-validated: controls within strata are price + premium (for segment strata) or
premium + segment (for price strata). No new controls added; this is a terminal
adjudication run, not a further expansion.
"""
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from analysis._common import load

df, meta = load()

OEM = {1.0: 'DomesticTraditional', 2.0: 'International', 3.0: 'DomesticStartup'}
df['OEM'] = df['ORIGIN2_DP'].map(OEM)

# Restrict to the two groups under adjudication
df = df[df['OEM'].isin(['International', 'DomesticTraditional'])].copy()
df['OEM'] = df['OEM'].replace({'International': 'Intl', 'DomesticTraditional': 'Trad'})

# Price in yuan; band edges 10/15/20/30 wan = 10e4/15e4/20e4/30e4
bins = [0, 10e4, 15e4, 20e4, 30e4, np.inf]
band_labels = ['<10万', '10-15万', '15-20万', '20-30万', '30万+']
df = df[df['CN_YNV_07'].notna()]
df['PRICE_BAND'] = pd.cut(df['CN_YNV_07'], bins=bins, labels=band_labels, right=False)


def fit(sub, formula):
    try:
        return smf.wls(formula, data=sub, weights=sub['APEAL_WT']).fit()
    except Exception as exc:
        return None


def extract(fit, level='INTL'):
    if fit is None:
        return None
    try:
        coef = fit.params[level]
        se = fit.bse[level]
        p = fit.pvalues[level]
        ci = fit.conf_int().loc[level]
        n = int(fit.nobs)
        return {'coef': coef, 'se': se, 'p': p, 'ci_lo': ci[0], 'ci_hi': ci[1], 'n': n}
    except (KeyError, IndexError):
        return None


def extract_intl(fit):
    """Return Intl-minus-Trad coefficient regardless of baseline coding."""
    r = extract(fit, level='INTL')
    if r is not None:
        return r
    t = extract(fit, level='C(OEM)[T.Trad]')
    if t is None:
        return None
    return {**t, 'coef': -t['coef'], 'se': t['se'], 'p': t['p'],
            'ci_lo': -t['ci_hi'], 'ci_hi': -t['ci_lo']}


def summarize_rows(rows, group):
    coefs = [r['coef'] for r in rows if r is not None]
    if not coefs:
        return []
    summary = {
        'group': group,
        'strata': len(rows),
        'usable_strata': len(coefs),
        'all_positive': all(c > 0 for c in coefs),
        'frac_positive': sum(c > 0 for c in coefs) / len(coefs),
        'coef_median': float(np.median(coefs)),
        'coef_q1': float(np.percentile(coefs, 25)),
        'coef_q3': float(np.percentile(coefs, 75)),
        'coef_min': float(np.min(coefs)),
        'coef_max': float(np.max(coefs)),
        'sig_strata': sum(1 for r in rows if r is not None and r['p'] < 0.05),
        'ci_cross_zero_share': sum(1 for r in rows if r is not None and r['ci_lo'] <= 0 <= r['ci_hi']) / len(coefs),
    }
    return summary


def run_segment_strata():
    rows = []
    for seg in sorted(df['SEGMENT_DP'].dropna().unique()):
        sub = df[df['SEGMENT_DP'] == seg]
        if sub['OEM'].nunique() < 2:
            rows.append(None)
            continue
        fit = smf.wls(
            'APEAL_Index ~ C(OEM) + CN_YNV_07 + C(PREMMAKE_DP)',
            data=sub, weights=sub['APEAL_WT']).fit()
        r = extract_intl(fit)
        if r:
            r['label'] = f"SEGMENT_DP={seg}"
            n_grp = sub.groupby('OEM').size().to_dict()
            r['n_trad'] = int(n_grp.get('Trad', 0)); r['n_intl'] = int(n_grp.get('Intl', 0))
        rows.append(r)
    return [r for r in rows if r is not None]


def run_price_band_strata():
    rows = []
    for band in band_labels:
        sub = df[df['PRICE_BAND'] == band]
        if sub['OEM'].nunique() < 2:
            rows.append(None)
            continue
        fit = smf.wls(
            'APEAL_Index ~ C(OEM) + C(PREMMAKE_DP) + C(SEGMENT_DP)',
            data=sub, weights=sub['APEAL_WT']).fit()
        r = extract_intl(fit)
        if r:
            r['label'] = f"PRICE={band}"
            n_grp = sub.groupby('OEM').size().to_dict()
            r['n_trad'] = int(n_grp.get('Trad', 0)); r['n_intl'] = int(n_grp.get('Intl', 0))
        rows.append(r)
    return [r for r in rows if r is not None]


if __name__ == '__main__':
    import json
    out = {'segment_strata': [], 'price_band_strata': []}

    seg_rows = run_segment_strata()
    for r in seg_rows:
        out['segment_strata'].append(r)
        print(f"{r['label']:20s} n_Trad={r['n_trad']:5d}/{r['n_intl']:4d}  "
              f"coef={r['coef']:+.2f} [{r['ci_lo']:+.2f},{r['ci_hi']:+.2f}]  p={r['p']:.3f}")
    print()
    print('SEGMENT summary:', json.dumps(summarize_rows(seg_rows, 'SEGMENT_DP'), ensure_ascii=False))

    band_rows = run_price_band_strata()
    for r in band_rows:
        print(f"{r['label']:12s} n_Trad={r['n_trad']:5d}/{r['n_intl']:4d}  "
              f"coef={r['coef']:+.2f} [{r['ci_lo']:+.2f},{r['ci_hi']:+.2f}]  p={r['p']:.3f}")
    print()
    print('PRICE_BAND summary:', json.dumps(summarize_rows(band_rows, 'PRICE_BAND'), ensure_ascii=False))