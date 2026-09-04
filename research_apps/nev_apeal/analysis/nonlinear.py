"""Continuous / nonlinear exposure analysis (binned panel).

Fills the Topic-C action gap: distinguish linear price->experience from
threshold / saturation / segment-jump patterns, and test whether a bin
pattern survives controls (e.g. is the price jump real or brand mix).
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from ._common import emit, load, weighted_mean

try:
    import statsmodels.formula.api as smf
except ImportError:  # pragma: no cover
    smf = None


def _weighted_ci(series: pd.Series, weights: pd.Series) -> tuple[float, float]:
    m = series.notna() & weights.notna()
    vals, wts = series[m].to_numpy(), weights[m].to_numpy()
    if len(vals) < 3:
        return float("nan"), float("nan")
    mean = float(np.average(vals, weights=wts))
    variance = float(np.average((vals - mean) ** 2, weights=wts))
    n_eff = (wts.sum() ** 2) / (wts**2).sum()
    se = np.sqrt(variance / n_eff)
    return mean - 1.96 * se, mean + 1.96 * se


def _make_bins(df: pd.DataFrame, exposure: str, bins: str, n_bins: int,
               business_edges: list[float]) -> pd.Series:
    x = df[exposure]
    if bins == "business":
        edges = business_edges or [0, 10e4, 15e4, 20e4, 30e4, float("inf")]
        labels = [f"{e/1e4:.0f}-{edges[i+1]/1e4:.0f}万" for i, e in enumerate(edges[:-1])]
        labels[-1] = f"{edges[-2]/1e4:.0f}万+"
        return pd.cut(x, bins=edges, labels=labels, right=False)
    try:
        return pd.qcut(x, n_bins, duplicates="drop", labels=False)
    except ValueError:
        return pd.cut(x, n_bins)


def analyze(df: pd.DataFrame, exposure: str, metric: str, bins: str, n_bins: int,
            business_edges: list[float], controls: list[str]) -> dict:
    controls = [c for c in controls if c in df.columns]
    sub = df[[exposure, metric, "APEAL_WT"] + controls].copy()
    sub = sub.dropna(subset=[exposure, metric])
    bin_col = _make_bins(sub, exposure, bins, n_bins, business_edges)
    sub["_bin"] = bin_col
    rows, deltas = [], []
    prev_mean = None
    prev_label = None
    for label, g in sub.groupby("_bin", observed=True):
        w = g["APEAL_WT"].fillna(1.0)
        mean = weighted_mean(g[metric], w)
        lo, hi = _weighted_ci(g[metric], w)
        rows.append({
            "bin": str(label), "n": int(len(g)),
            "weighted_mean": round(mean, 2), "ci_lo": round(lo, 2), "ci_hi": round(hi, 2),
        })
        if prev_mean is not None:
            deltas.append({"from": str(prev_label), "to": str(label), "delta": round(mean - prev_mean, 2)})
        prev_mean, prev_label = mean, str(label)

    sign_changes = 0
    prev_sign = None
    for d in deltas:
        s = 1 if d["delta"] > 0 else (-1 if d["delta"] < 0 else 0)
        if prev_sign is not None and s != 0 and s != prev_sign:
            sign_changes += 1
        if s != 0:
            prev_sign = s

    nonlinear_test = None
    if smf is not None and len(rows) >= 3:
        fit_linear = smf.ols(f"{metric} ~ {exposure}", data=sub).fit()
        fit_binned = smf.ols(f"{metric} ~ {exposure} + C(_bin)", data=sub).fit()
        from scipy import stats as _stats
        rss_l = float(((fit_linear.resid) ** 2).sum())
        rss_b = float(((fit_binned.resid) ** 2).sum())
        df_diff = fit_binned.df_model - fit_linear.df_model
        df_res = fit_binned.df_resid
        f_stat = ((rss_l - rss_b) / df_diff) / (rss_b / df_res) if df_diff > 0 and rss_b > 0 else float("nan")
        p = float(_stats.f.sf(f_stat, df_diff, df_res)) if not np.isnan(f_stat) else float("nan")
        nonlinear_test = {
            "method": "nested F (linear vs linear+bin dummies)",
            "f": round(f_stat, 3), "df_diff": int(df_diff), "p": p,
            "nonlinear": bool(p < 0.05) if not np.isnan(p) else None,
        }

    adjusted_bin_coefs = []
    if controls and smf is not None:
        ref_bin = str(sub["_bin"].cat.categories[0]) if hasattr(sub["_bin"], "cat") else str(sorted(sub["_bin"].unique())[0])
        fit = smf.ols(f"{metric} ~ C(_bin) + {' + '.join(controls)}", data=sub).fit()
        for term in fit.params.index:
            if "C(_bin)" in term:
                adjusted_bin_coefs.append({
                    "bin": term.split("[T.")[-1].rstrip("]"),
                    "reference": ref_bin,
                    "coef": round(float(fit.params[term]), 2),
                    "p": float(fit.pvalues[term]),
                })

    means = [r["weighted_mean"] for r in rows]
    return {
        "exposure": exposure,
        "metric": metric,
        "method": "bins",
        "bins": rows,
        "adjacent_deltas": deltas,
        "diagnostics": {
            "monotonic": sign_changes == 0,
            "direction_changes": sign_changes,
            "largest_jump": max(deltas, key=lambda d: abs(d["delta"])) if deltas else None,
            "turning_point": rows[int(np.argmax(means))] if rows else None,
            "range": round(float(max(means) - min(means)), 2) if means else 0.0,
            "nonlinear_test": nonlinear_test,
        },
        "adjusted_bin_coefs": adjusted_bin_coefs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="连续/非线性 exposure 分箱诊断")
    parser.add_argument("--exposure", required=True)
    parser.add_argument("--metric", default="APEAL_Index")
    parser.add_argument("--method", default="bins", choices=["bins"])
    parser.add_argument("--bins", default="quantile", choices=["quantile", "business"])
    parser.add_argument("--n-bins", type=int, default=5)
    parser.add_argument("--business-edges", type=str, default="", help="逗号分隔边界(元)，如 0,100000,200000,300000")
    parser.add_argument("--controls", nargs="+", default=[])
    args = parser.parse_args()

    edges = [float(v) for v in args.business_edges.split(",")] if args.business_edges else []
    df, _ = load()
    emit(analyze(df, args.exposure, args.metric, args.bins, args.n_bins, edges, args.controls))


if __name__ == "__main__":
    main()
