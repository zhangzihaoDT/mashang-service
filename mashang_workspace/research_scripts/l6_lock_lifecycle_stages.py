#!/usr/bin/env python3
"""
智己各代际生命周期每日锁单量阶段划分研究

研究对象: 按 `business_definition.json` 的代际（CM0/CM1/CM2/CM3、DM0/DM1/DM2、
LS8/LS9/LS9Hyper 等）在其生命周期内的每日锁单变化阶段。

生命周期窗口（本代 end（上市）→ 换代车型 end（上市）-1）:
  - 有换代车型（SUCCESSORS 中定义了后继）:
      [本代.end, 后继.end - 1]
  - 无换代车型（含末代，或后继尚未上市）:
      [本代.end, as-of 前一日]（"至今"），as-of 默认当天
  - 窗口右端总是封顶到 as-of 前一日（不越过"至今"）。

方法:
  1. 锁单口径 = order_data.parquet，retail（order_type ∈ {用户车, NaN}，排除试驾车），
     series_group_logic 归属代际，锁单以 lock_time 非空计（COUNTD order_number）。
  2. 逐日锁单量 → 按 7 日周块聚合（消除周末/日突发噪声）。
  3. 变更点检测：对周序列做 DP 分段常数分割（最小段长 2 周）。
      默认段数 k=5（统一，保证可比）；可通过 --n-segments 覆盖，
      或传 --auto-select 退回 BIC（n·ln(SSE/n) + k·ln(n)）自动选择。
  4. 周段边界映射回日，输出每日/段内总量、日均、趋势与业务阶段名，
     并对照业务锚点（end/finish/换代 end / 至今）。

用法:
  python research_scripts/l6_lock_lifecycle_stages.py
  python research_scripts/l6_lock_lifecycle_stages.py --gen CM0 CM1 CM2 --n-segments 6
  python research_scripts/l6_lock_lifecycle_stages.py --format json --output outputs/tables/
  python research_scripts/l6_lock_lifecycle_stages.py --chart --output outputs/charts/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS = REPO_ROOT / "mashang_workspace"
for p in (str(REPO_ROOT), str(_WS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from research_scripts.l6_m2_launch_lock_metrics_to_feishu import (  # noqa: E402
    _parse_logic,
    _rule_condition,
    apply_series_group_logic,
    load_business_definition,
)

_BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"

SMOOTH_WIN = 7
WEEK_LEN = 7
MIN_WEEKS = 2          # 最小段长（周）
MAX_SEGMENTS = 12
DEFAULT_SEGMENTS = 5   # 默认阶段数（统一，可比；--n-segments 可覆盖）

# 代际换代链：上一代 .end → 下一代 .end（窗口右界 = 下一代的 end - 1）。
# 未列出后继的代际（如 LS8/LS9/末代 DM2 等）= 无换代车型，窗口右界 = as-of 前一日。
SUCCESSORS = {
    "CM0": "CM1", "CM1": "CM2", "CM2": "CM3",
    "DM0": "DM1", "DM1": "DM2",
}
# 无后继（或用"至今"）的代际：窗口右界 = as-of 前一日


def load_order() -> pd.DataFrame:
    df = pd.read_parquet(ORDER_PARQUET)
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    bd = load_business_definition(_BUSINESS_DEF)
    asts = {g: _parse_logic(_rule_condition(c))
            for g, c in bd["series_group_logic"].items()}
    df = apply_series_group_logic(df, bd, asts)
    df = df[(df["order_type"].isna()) | (df["order_type"] == "用户车")].copy()
    return df


def daily_series(df: pd.DataFrame, gen: str,
                 start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    sub = df[(df["series_group_logic"] == gen)
             & (df["lock_time"].notna())
             & (df["lock_time"] >= start)
             & (df["lock_time"] < (end + pd.Timedelta(days=1)))].copy()
    sub["d"] = sub["lock_time"].dt.normalize()
    s = sub.groupby("d").agg({"order_number": "nunique"})["order_number"]
    full = pd.date_range(start.normalize(), end.normalize())
    return s.reindex(full, fill_value=0)


def weekly_dp(values: np.ndarray, min_len: int, max_k: int,
              force_k: int | None = None):
    """周序列分段常数分割，段数由 BIC 自动选择。

    values: 每周一个值；min_len: 最小段长（周）。返回 (k, bounds, seg_means)。
    bounds 为每个段（含）的结束周下标。
    force_k: 若给定则固定段数（用于 --n-segments 覆盖）。
    """
    n = len(values)
    if n == 0:
        return 0, [], []
    ps = np.zeros(n + 1)
    pss = np.zeros(n + 1)
    for i in range(n):
        ps[i + 1] = ps[i] + values[i]
        pss[i + 1] = pss[i] + values[i] * values[i]

    def seg_cost(l, r):  # SSE around mean for weeks l..r
        m = r - l + 1
        s = ps[r + 1] - ps[l]
        ss = pss[r + 1] - pss[l]
        return ss - (s * s) / m

    kmax = max(1, min(max_k, n // max(1, min_len)))
    dp = np.full((kmax + 1, n + 1), np.inf)
    back = np.full((kmax + 1, n + 1), -1, dtype=int)
    dp[0][0] = 0.0
    for k in range(1, kmax + 1):
        row = dp[k]
        prev = dp[k - 1]
        for i in range(k * min_len, n + 1):
            best, bestj = np.inf, -1
            for j in range((k - 1) * min_len, i - min_len + 1):
                c = prev[j] + seg_cost(j, i - 1)
                if c < best:
                    best, bestj = c, j
            row[i] = best
            back[k][i] = bestj

    if force_k is not None:
        k_best = max(1, min(force_k, kmax))
    else:
        # BIC 选段数：取 BIC 最小；若存在更高 k 其 BIC 距离最小点 ≤ ln(n) 且
        # 方差解释提升 ≥ 5%，则取更大 k（避免过度粗化丢失真实阶段）
        bic = {}
        for k in range(1, kmax + 1):
            sse = dp[k][n]
            if not np.isfinite(sse) or sse <= 0:
                continue
            bic[k] = n * np.log(sse / n) + k * np.log(n)
        if not bic:
            return 0, [], []
        k_min = min(bic, key=bic.get)
        total_var = float(np.sum((values - np.mean(values)) ** 2))
        k_best = k_min
        for k in sorted(bic):
            if k <= k_best:
                continue
            if bic[k] <= bic[k_min] + np.log(n):
                expl_k = 1 - dp[k][n] / max(total_var, 1e-9)
                expl_b = 1 - dp[k_best][n] / max(total_var, 1e-9)
                if expl_k - expl_b >= 0.05:
                    k_best = k

    # 回溯（逐段递减，保证还原段数 == k_best）
    chain = []
    i = n
    rem = k_best
    while i > 0 and rem > 0:
        j = back[rem][i]
        if j < 0:
            break
        chain.append(i - 1)
        i = j
        rem -= 1
    chain.reverse()
    means = []
    ps0 = 0
    for e in chain:
        means.append(float(np.mean(values[ps0:e + 1])))
        ps0 = e + 1
    return k_best, chain, means


def _day_index(d: pd.Timestamp, start: pd.Timestamp) -> int:
    return int((d.normalize() - start.normalize()).days)


def build_segments(daily: pd.Series, start: pd.Timestamp,
                   week_bounds: list[int], week_means: list[float],
                   open_end: bool = False) -> list[dict]:
    """把周段边界映射回日，计算每段指标并给业务阶段名。

    open_end=True 表示该代际窗口未收尾（仍在售/无换代），
    末段不标"换代前低迷期"而标当前进行阶段。
    """
    n = len(daily)
    smooth = daily.rolling(SMOOTH_WIN, center=True, min_periods=1).mean()
    global_mean = float(daily.mean())
    segs = []
    prev_day = 0
    for idx, wk_end in enumerate(week_bounds):
        end_day = min((wk_end + 1) * WEEK_LEN - 1, n - 1)
        vals = daily.values[prev_day:end_day + 1]
        sm_vals = smooth.values[prev_day:end_day + 1]
        days = int(end_day - prev_day + 1)
        total = int(vals.sum())
        mean_daily = float(total / days)
        first_sm, last_sm = sm_vals[0], sm_vals[-1]
        change_ratio = (last_sm - first_sm) / max(mean_daily, 1e-9)
        if change_ratio > 0.25:
            trend = "上升"
        elif change_ratio < -0.25:
            trend = "下降"
        else:
            trend = "平稳"
        start_d = start.normalize() + pd.Timedelta(days=prev_day)
        end_d = start.normalize() + pd.Timedelta(days=end_day)
        segs.append({
            "seg": idx + 1,
            "start": start_d.strftime("%Y-%m-%d"),
            "end": end_d.strftime("%Y-%m-%d"),
            "days": days,
            "wk_mean": round(week_means[idx], 2),
            "mean_daily": round(mean_daily, 1),
            "total": total,
            "share": round(total / max(daily.sum(), 1e-9), 4),
            "trend": trend,
            "level_vs_global": _level(mean_daily, global_mean),
        })
        prev_day = end_day + 1
    _label_stages(segs, open_end=open_end)
    return segs


def _level(x: float, ref: float) -> str:
    if ref <= 0:
        return "-"
    if x > 1.3 * ref:
        return "高位"
    if x < 0.7 * ref:
        return "低位"
    return "中位"


def _label_stages(segs: list[dict], open_end: bool = False) -> None:
    """按 峰值/趋势/水平/位置 给出业务阶段名。生命周期起点即上市（end）。

    open_end=True 时末段是进行中的当前阶段，不标"换代前低迷期"。
    """
    global_mean = float(np.mean([s["mean_daily"] for s in segs]))
    peak_idx = int(np.argmax([s["mean_daily"] for s in segs]))
    n = len(segs)
    for i, s in enumerate(segs):
        m = s["mean_daily"]
        lv = s["level_vs_global"]
        tr = s["trend"]
        if open_end and i == n - 1:
            stage = "当前阶段(至今)"
        elif i == n - 1 and (lv == "低位" or tr == "下降"):
            stage = "换代前低迷期"
        elif i == peak_idx:
            stage = "上市冲量峰" if i == 0 else "销量冲量峰"
        elif tr == "上升":
            stage = "回升企稳期"
        elif tr == "下降":
            if lv == "高位":
                stage = "冲量高位回落期" if peak_idx < i else "高位回落期"
            elif lv == "中位":
                stage = "冲量后回落期" if peak_idx < i else "中位回落期"
            else:
                stage = "低位下滑期"
        else:  # 平稳
            stage = ({"高位": "高位平台期", "中位": "中间平台期",
                      "低位": "低位平台期"}.get(lv, "中间平台期"))
        s["stage"] = stage
        s["stage_note"] = (
            f"峰值段(日均 {segs[peak_idx]['mean_daily']})；本段日均 {m}，"
            f"相对全周期均值({round(global_mean,1)})为{lv}，段内趋势{tr}"
        )


def run_lifecycle(df: pd.DataFrame, gen: str,
                  start: str, end: str, anchors: dict,
                  force_k: int | None = None,
                  open_end: bool = False) -> dict:
    start_t = pd.Timestamp(start)
    end_t = pd.Timestamp(end)
    daily = daily_series(df, gen, start_t, end_t)
    n_days = len(daily)
    n_weeks = (n_days + WEEK_LEN - 1) // WEEK_LEN
    # 周聚合：以生命周期起点为第 0 周的 7 日块
    weekly = np.zeros(n_weeks)
    for w in range(n_weeks):
        lo = w * WEEK_LEN
        hi = min(lo + WEEK_LEN, n_days)
        weekly[w] = daily.values[lo:hi].sum()

    _max_k = max(1, min(MAX_SEGMENTS, n_weeks // MIN_WEEKS))
    k, week_bounds, week_means = weekly_dp(weekly, MIN_WEEKS, _max_k, force_k=force_k)
    if k == 0:
        k, week_bounds, week_means = 1, [n_weeks - 1], [float(weekly.sum())]

    segs = build_segments(daily, start_t, week_bounds, week_means, open_end=open_end)
    done = {
        "generation": gen,
        "lifecycle": {"start": start, "end": end},
        "anchors": anchors,
        "n_segments": k,
        "segments": segs,
        "daily": [
            {"date": (start_t.normalize() + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
             "lock_count": int(v), "smooth": round(float(sm), 1)}
            for i, (v, sm) in enumerate(zip(daily.values, daily.rolling(
                SMOOTH_WIN, center=True, min_periods=1).mean().values))
        ],
    }
    return done


def _gen_meta_from_business_def(gen: str, bd: dict, as_of: pd.Timestamp) -> dict:
    """构造单个代际的生命周期窗口。

    窗口右界 = 后继代 .end - 1；无后继时 = as_of 前一日（"至今"）。
    窗口右界封顶到 as_of 前一日（后继 .end 晚于今天时同样取"至今"）。
    open_end=True 表示该代际窗口是开放的（仍在售 / 无换代），
    末段不应标"换代前低迷期"。
    """
    tp = bd["time_periods"]
    end = tp[gen]["end"]
    nxt = SUCCESSORS.get(gen)
    as_of_minus_1 = (as_of.normalize() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    nxt_end = tp[nxt]["end"] if (nxt and "end" in tp.get(nxt, {})) else None
    if nxt_end:
        right = (pd.Timestamp(nxt_end) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        right = as_of_minus_1
    capped = right > as_of_minus_1
    open_end = (nxt_end is None) or capped
    right = min(right, as_of_minus_1)
    anchor_key = "至今(today-1)" if (nxt_end is None or capped) else f"换代{nxt}.end-1"
    return {
        "start": end,
        "end": right,
        "open_end": open_end,
        "anchors": {
            "end(上市)": end,
            "finish(权益结束)": tp[gen].get("finish", ""),
            anchor_key: right,
        },
    }


def build_gen_meta(gens: list[str], as_of: pd.Timestamp) -> dict:
    bd = load_business_definition(_BUSINESS_DEF)
    return {g: _gen_meta_from_business_def(g, bd, as_of) for g in gens}


DEFAULT_GENS = ["CM0", "CM1", "CM2", "LS8", "LS9"]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="智己各代际生命周期每日锁单量阶段划分")
    p.add_argument("--gen", type=str, default=None, nargs="*",
                   help="代际（默认 CM0 CM1 CM2 LS8 LS9）")
    p.add_argument("--as-of", type=str, default=None,
                   help="'至今'基准日（默认今天）；窗口右界取 as-of 前一日")
    p.add_argument("--n-segments", type=int, default=DEFAULT_SEGMENTS,
                   help=f"强制阶段数（默认 {DEFAULT_SEGMENTS}，统一）")
    p.add_argument("--auto-select", action="store_true",
                   help="退回 BIC + 容差自动选择段数（忽略 --n-segments）")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    p.add_argument("--output", type=str, help="JSON 输出目录")
    p.add_argument("--chart", action="store_true", help="输出 matplotlib 图表 PNG")
    args = p.parse_args(argv)

    df = load_order()
    gens = args.gen or DEFAULT_GENS
    as_of = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp.now()
    GEN_META = build_gen_meta(gens, as_of)
    force_k = None if args.auto_select else args.n_segments
    results = {}
    for gen in gens:
        meta = GEN_META[gen]
        results[gen] = run_lifecycle(df, gen, meta["start"], meta["end"],
                                     meta["anchors"], force_k=force_k,
                                     open_end=meta["open_end"])

    if args.chart:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for gen in gens:
            r = results[gen]
            dates = [pd.Timestamp(x["date"]) for x in r["daily"]]
            vals = [x["lock_count"] for x in r["daily"]]
            sm = [x["smooth"] for x in r["daily"]]
            plt.figure(figsize=(14, 5))
            plt.plot(dates, vals, color="#9DB4C8", linewidth=1.0, label="每日锁单")
            plt.plot(dates, sm, color="#174A7C", linewidth=1.8, label=f"{SMOOTH_WIN}日平滑")
            cmap = ["#D79A36", "#7ECDEB", "#7A9C4A", "#8A7CC0", "#C96A4C",
                    "#4CA8A0", "#B0783A", "#6A8FD8", "#C08A8A", "#587A5A",
                    "#9A6AA8", "#D8C03A"]
            _draw_segments(plt, r, dates, cmap)
            plt.title(f"{gen} 生命周期每日锁单量（{r['lifecycle']['start']} ~ {r['lifecycle']['end']}）",
                      color="#06213D")
            plt.ylabel("锁单量"); plt.legend(loc="upper right"); plt.grid(alpha=0.3)
            out_dir = Path(args.output or (REPO_ROOT / "mashang_workspace/outputs/charts"))
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / f"{gen}_lifecycle_lock_stages.png"
            plt.savefig(out, dpi=140, bbox_inches="tight")
            plt.close()
            print(f"图表已输出: {out}")

    if args.format == "json":
        payload = {
            "status": "success",
            "script": "research_scripts/l6_lock_lifecycle_stages.py",
            "scope": {
                "data_source": "dataset/order_data.parquet",
                "filters": {"order_type": "用户车/NaN（零售口径）",
                            "series_group_logic": gens},
                "as_of": as_of.strftime("%Y-%m-%d"),
                "time_windows": {g: {"start": GEN_META[g]["start"],
                                     "end": GEN_META[g]["end"]} for g in gens},
                "metric_definition": "锁单=lock_time 非空 COUNTD(order_number)；"
                                     "周块=7 日；阶段=周序列 DP 分段常数分割，默认 k=5",
            },
            "result": {"summary": f"{'/'.join(gens)} 生命周期每日锁单量阶段划分",
                       "generations": results},
            "artifacts": {},
            "followup_context": {"analysis_type": "lifecycle_stage", "metric": "lock_count_daily",
                                 "generations": gens},
            "warnings": [],
            "errors": [],
        }
        if args.output:
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / (f"lifecycle_lock_stages_{'_'.join(gens)}.json")
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"已输出: {out}")
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for gen in gens:
            r = results[gen]
            print(f"\n===== {gen} 生命周期：{r['lifecycle']['start']} ~ {r['lifecycle']['end']} =====")
            print(f"锚点: " + ",  ".join(f"{k}={v}" for k, v in r["anchors"].items()))
            print(f"变更点检测段数: {r['n_segments']}")
            print(f"{'段':<3}{'起止':<22}{'天数':>5}{'日均':>8}{'总量':>7}{'占比':>7}{'趋势':>5}{'相对全周期':>7}  阶段")
            print("-" * 100)
            for s in r["segments"]:
                span = f"{s['start']}~{s['end']}"
                print(f"{s['seg']:<3}{span:<22}{s['days']:>5}{s['mean_daily']:>8}{s['total']:>7}"
                      f"{s['share']:>7.1%}{s['trend']:>5}{s['level_vs_global']:>7}  {s['stage']}")
            total = sum(x["total"] for x in r["segments"])
            print("-" * 100)
            print(f"生命周期累计锁单: {total}")
    return 0


def _draw_segments(plt, r, dates, cmap):
    prev = 0
    idx = 0
    for s in r["segments"]:
        e = [i for i, d in enumerate(dates) if d.strftime("%Y-%m-%d") == s["end"]][0]
        plt.axvspan(dates[prev], dates[e], color=cmap[idx % len(cmap)], alpha=0.12)
        prev = e + 1
        idx += 1


if __name__ == "__main__":
    raise SystemExit(main())