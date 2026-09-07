"""
复购 / 老车主拆分 — Shared Operator

对指定窗口内零售锁单，按车主身份（owner_identity_no）拆分购车历史，判定是否「复购」。

底层四类互斥桶（逐窗口订单，不重叠）：
    prior_fulfilled    —— 身份在窗口开始前已完成过兑现购车（存在历史零售锁单，
                           且该历史订单的交付或开票时间早于窗口开始）
    prior_unfulfilled  —— 身份在窗口开始前有过零售锁单，但从未兑现（或兑现晚于窗口开始）
                           ＝「悬置历史」，不代表已购车
    no_prior_history   —— 身份有效，窗口开始前无任何零售锁单
    unknown_identity   —— 身份缺失 / 无效（非 18 位身份证格式）

派生口径（mode，互斥，计数不重叠）：
    fulfilled_repurchase（canonical，默认）
        repeat = prior_fulfilled（真·老车主复购）；suspended = prior_unfulfilled
    prior_locker（宽松对照，对齐 lock_attribution_analysis "Repeat Lockers (Had Prior Locks)"）
        repeat = prior_fulfilled + prior_unfulfilled（窗口前已锁即算）；suspended = 0
    （no_prior_history 恒为 first；unknown_identity 恒为 unknown）

PIT（不穿越）：
    判定一律以事件时间早于窗口开始为界：
      - 窗口前锁单、窗口后才交付/开票 → 该窗口下计 prior_unfulfilled；
        当用更晚的窗口再评估时，兑现时间已落在新窗口前，自动转为 prior_fulfilled。
    → 不引入任何窗口后信息，历史口径可复现、可重算。

数据集：order_data（lock_time / delivery_date / invoice_upload_time / owner_identity_no；
      调用方应传入已按零售口径过滤的 df）
入口：
    run_repurchase_operator(df, window_start, window_end, series=None, mode=...)
"""

from __future__ import annotations

import re

import pandas as pd

_IDENTITY_RE = re.compile(r"^\d{17}[\dXx]$")

# 支持的模式
MODE_FULFILLED = "fulfilled_repurchase"
MODE_PRIOR_LOCKER = "prior_locker"
VALID_MODES = (MODE_FULFILLED, MODE_PRIOR_LOCKER)


def _is_valid_identity(v: object) -> bool:
    return isinstance(v, str) and bool(_IDENTITY_RE.match(v.strip()))


def _coerce_dt(df: pd.DataFrame, cols: list[str]) -> None:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")


def split_repurchase(
    df: pd.DataFrame,
    window_start,
    window_end,
    *,
    mode: str = MODE_FULFILLED,
    identity_col: str = "owner_identity_no",
    lock_col: str = "lock_time",
    delivery_col: str = "delivery_date",
    invoice_col: str = "invoice_upload_time",
    series: str | None = None,
    series_col: str = "series_group_logic",
) -> dict:
    """核心拆分算子（底层四桶互斥，上层按 mode 派生）。

    df      —— 全量订单（含窗口前历史 + 窗口订单），须已带 series_group_logic；
    window_start / window_end —— 目标窗口 [start, end)，左闭右开；
    series  —— 若指定，仅把该 series_group_logic 的订单作为「窗口订单」评估；
               历史（窗口前）不按 series 过滤，因老车主可能是任何既往代际车型。
    返回：四桶计数 + 派生 repeat/suspended/first/unknown + known_pct。
    """
    if df is None or df.empty:
        return {"n": 0, "error": "no_data", "message": "无可用数据。"}
    if mode not in VALID_MODES:
        return {"error": "invalid_mode", "message": f"mode 仅支持 {VALID_MODES}，收到: {mode}"}

    work = df.copy()
    _coerce_dt(work, [lock_col, delivery_col, invoice_col])
    if lock_col not in work.columns or identity_col not in work.columns:
        return {"error": "missing_columns",
                "message": f"缺少必需列: {lock_col} 或 {identity_col}"}

    start = pd.Timestamp(window_start).normalize()
    end = pd.Timestamp(window_end).normalize()
    if end <= start:
        return {"error": "invalid_window", "message": "window_end 必须晚于 window_start"}

    # ---- 目标窗口订单（待评估对象）----
    target = work[work[lock_col].notna()
                  & (work[lock_col] >= start) & (work[lock_col] < end)].copy()
    if series is not None and series_col in target.columns:
        target = target[target[series_col].astype(str).eq(str(series))]
    target = target.drop_duplicates(subset=["order_number"])
    n = int(len(target))

    # ---- 窗口前全部历史锁单（任意代际，不做 series 过滤）----
    hist = work[work[lock_col].notna() & (work[lock_col] < start)].copy()

    def _valid_ids(frame: pd.DataFrame) -> pd.Series:
        if frame.empty:
            return pd.Series(dtype=bool)
        s = frame[identity_col].fillna("").astype(str).str.strip()
        return s.map(_is_valid_identity)

    # 已兑现历史 = 历史锁单中交付或开票早于窗口开始
    fulfilled_hist = hist[hist[delivery_col].notna() | hist[invoice_col].notna()].copy()
    ful_at = fulfilled_hist[[delivery_col, invoice_col]].min(axis=1)
    fulfilled_hist = fulfilled_hist[ful_at < start]
    prior_fulfilled_ids = set(fulfilled_hist.loc[_valid_ids(fulfilled_hist).values,
                                                 identity_col].astype(str).unique())
    # 任意历史锁单（含悬置）
    prior_locked_ids = set(hist.loc[_valid_ids(hist).values, identity_col].astype(str).unique())
    # 互斥：先 fulfilled 后，其余有历史锁单者归 prior_unfulfilled
    prior_unfulfilled_ids = prior_locked_ids - prior_fulfilled_ids

    # ---- 逐目标订单分桶 ----
    tgt_idn = target[identity_col].fillna("").astype(str).str.strip()
    valid = tgt_idn.map(_is_valid_identity)

    prior_fulfilled = int((valid & tgt_idn.isin(prior_fulfilled_ids)).sum())
    prior_unfulfilled = int((valid & ~tgt_idn.isin(prior_fulfilled_ids)
                             & tgt_idn.isin(prior_unfulfilled_ids)).sum())
    no_prior_history = int((valid & ~tgt_idn.isin(prior_locked_ids)).sum())
    unknown_identity = int(n - valid.sum())

    # ---- 按 mode 派生 ----
    if mode == MODE_FULFILLED:
        repeat, suspended = prior_fulfilled, prior_unfulfilled
    else:  # MODE_PRIOR_LOCKER
        repeat, suspended = prior_fulfilled + prior_unfulfilled, 0
    first = no_prior_history
    unknown = unknown_identity

    known = repeat + first + suspended
    return {
        "type": "repurchase",
        "mode": mode,
        "window_start": start.strftime("%Y-%m-%d"),
        "window_end": end.strftime("%Y-%m-%d"),
        "series": series,
        "scope": {
            "identity_col": identity_col,
            "fulfilled_by": [delivery_col, invoice_col],
            "history_cutoff": "lock_time < window_start；兑现事件亦须早于 window_start",
            "bucket_definition": "互斥：prior_fulfilled / prior_unfulfilled / no_prior_history / unknown_identity",
        },
        "buckets": {
            "prior_fulfilled": prior_fulfilled,
            "prior_unfulfilled": prior_unfulfilled,
            "no_prior_history": no_prior_history,
            "unknown_identity": unknown_identity,
        },
        "summary": {
            "n": n,
            "repeat": repeat,
            "suspended": suspended,
            "first": first,
            "unknown": unknown,
            "known": known,
            "repeat_rate": round(repeat / known, 4) if known else None,
            "known_pct": round(valid.mean() * 100, 1) if n else 0.0,
        },
    }


def run_repurchase_operator(
    df: pd.DataFrame,
    window_start: str,
    window_end: str,
    *,
    mode: str = MODE_FULFILLED,
    series: str | None = None,
    series_col: str = "series_group_logic",
) -> dict:
    """算子层入口（registry 调用）。window_start/end 传 ISO 日期字符串。"""
    try:
        start = pd.Timestamp(window_start).normalize()
        end = pd.Timestamp(window_end).normalize()
    except Exception:
        return {"type": "repurchase", "error": "invalid_window",
                "message": f"window 格式错误: {window_start} ~ {window_end}"}
    return split_repurchase(
        df, start, end, mode=mode, series=series, series_col=series_col,
    )
