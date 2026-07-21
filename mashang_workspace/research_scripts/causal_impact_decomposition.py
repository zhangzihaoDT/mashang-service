"""
name: causal_impact_decomposition
use: python research_scripts/causal_impact_decomposition.py --series LS9 --start-base 2026-06-21 --end-base 2026-07-15 --start-near 2026-07-16 --end-near 2026-07-20
summary: 双因子因果推断 — 将锁单增量分解为"下发线索效应"和"转化率效应"，评估上市/营销事件对锁单的驱动来源。

因子分解公式:
  ΔLock = (Leads_near - Leads_base) × Conv_base       ← 线索量效应
         + (Conv_near - Conv_base) × Leads_base        ← 转化率效应
         + (Leads_near - Leads_base) × (Conv_near - Conv_base)  ← 交互效应
"""

import argparse
import pandas as pd
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    adf = pd.read_csv(ROOT.parent / "dataset" / "assign_data.csv")
    adf["date"] = pd.to_datetime(adf["Assign Time 年/月/日"], format="%Y年%m月%d日")
    odf = pd.read_parquet(ROOT.parent / "dataset" / "order_data.parquet")
    odf["lock_date"] = odf["lock_time"].dt.date
    return adf, odf


def run_analysis(
    series: str,
    start_base: date, end_base: date,
    start_near: date, end_near: date,
    order_type: str = "用户车",
) -> dict:
    adf, odf = load_data()

    def _stats(start, end, label):
        leads = adf[(adf["date"].dt.date >= start) & (adf["date"].dt.date <= end)]["下发线索数"]
        locks = odf[
            (odf["lock_date"] >= start) & (odf["lock_date"] <= end)
            & (odf["series"] == series)
            & (odf["order_type"] == order_type)
        ]
        days = (end - start).days + 1
        dl = leads.mean()
        ll = len(locks) / days
        cv = ll / dl if dl else 0
        return {"days": days, "daily_leads": dl, "daily_locks": ll, "conv": cv,
                "total_leads": leads.sum(), "total_locks": len(locks)}

    base = _stats(start_base, end_base, "基准期")
    near = _stats(start_near, end_near, "近N日")

    dl = near["daily_locks"] - base["daily_locks"]
    le = (near["daily_leads"] - base["daily_leads"]) * base["conv"]
    ce = (near["conv"] - base["conv"]) * base["daily_leads"]
    ia = (near["daily_leads"] - base["daily_leads"]) * (near["conv"] - base["conv"])

    return {
        "series": series,
        "order_type": order_type,
        "base_period": f"{start_base} ~ {end_base} ({base['days']}天)",
        "near_period": f"{start_near} ~ {end_near} ({near['days']}天)",
        "base": base,
        "near": near,
        "decomposition": {
            "total_delta": round(dl, 2),
            "leads_effect": round(le, 2),
            "conv_effect": round(ce, 2),
            "interaction": round(ia, 2),
            "leads_pct": round(le / dl * 100, 1) if dl else 0,
            "conv_pct": round(ce / dl * 100, 1) if dl else 0,
            "interact_pct": round(ia / dl * 100, 1) if dl else 0,
        },
    }


def format_output(r: dict) -> str:
    b, n, d = r["base"], r["near"], r["decomposition"]
    lines = [
        f"=== {r['series']} 锁单因果分解 ({r['order_type']}) ===",
        f"",
        f"  基准期:  {r['base_period']}",
        f"  近N日:   {r['near_period']}",
        f"",
        f"  {'因子':<20} {'基准期(日均)':<16} {'近N日(日均)':<14} {'变化':<10}",
        f"  {'-'*60}",
        f"  {'下发线索':<20} {b['daily_leads']:<16,.0f} {n['daily_leads']:<14,.0f} {(n['daily_leads']-b['daily_leads']):+,.0f}",
        f"  {'锁单':<20} {b['daily_locks']:<16.1f} {n['daily_locks']:<14.1f} {n['daily_locks']-b['daily_locks']:+.1f}",
        f"  {'转化率':<20} {b['conv']*100:<11.4f}%  {n['conv']*100:<8.4f}%  {(n['conv']-b['conv'])*100:+.4f}%",
        f"",
        f"  === 锁单日均增量分解 ===",
        f"  总增量: {d['total_delta']:+.1f} / 日",
        f"    ① 下发线索效应: +{d['leads_effect']:.1f} ({d['leads_pct']}%)",
        f"    ② 转化率效应:   +{d['conv_effect']:.1f} ({d['conv_pct']}%)",
        f"    ③ 交互效应:     +{d['interaction']:.1f} ({d['interact_pct']}%)",
        f"",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--series", default="LS9")
    p.add_argument("--start-base", default="2026-06-21")
    p.add_argument("--end-base", default="2026-07-15")
    p.add_argument("--start-near", default="2026-07-16")
    p.add_argument("--end-near", default="2026-07-20")
    p.add_argument("--order-type", default="用户车")
    args = p.parse_args()

    result = run_analysis(
        series=args.series,
        start_base=date.fromisoformat(args.start_base),
        end_base=date.fromisoformat(args.end_base),
        start_near=date.fromisoformat(args.start_near),
        end_near=date.fromisoformat(args.end_near),
        order_type=args.order_type,
    )

    print(format_output(result))
