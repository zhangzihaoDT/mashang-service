"""
复购 / 老车主拆分 — Shared Operator（v2 · B 方案，唯一正式口径）

本算子度量的是「**同一手机号在此前已有人完成购车**」，即**同号复购**；
手机号是统计身份，**不等同于车主身份**（可能被家庭成员共用、门店代填或变更持有者）。
详见 `shared/schema/reference/metric_definitions.md` 的「复购口径 v2（B 方案）」。

窗口内订单必须且只能落入以下**四桶（互斥且穷尽）**：
    prior_fulfilled        —— 手机号在窗口前已完成购车（复购）✅ 计入 repeat
    no_prior_history       —— 手机号有效，窗口前无已完成购车（首购）
    shared_phone_excluded  —— 共享号码，整号剔除（不计入分母）
    unknown_identity       —— 手机号缺失/无效（计入分母，不计入分子）

恒等式：
    sum(四桶) == target_orders
    target_orders - shared_phone_excluded == valid_base
    repeat / valid_base == repeat_rate

「窗口前已完成购车」＝ 历史锁单（lock_time < window_start）
且 min(delivery_date, invoice_upload_time) < window_start。

共享号码：历史中（仅窗口前**已兑现**订单）与 ≥2 个不同 `owner_identity_no` 关联的手机号。
**严格 PIT**：判定不得使用任何窗口开始后的信息。

订单类型：调用方应传入已过滤为零售（order_type == '用户车'）的 df。
算子不内部读取 order_phone_map.parquet——JOIN 由调用方完成并保证 order_number 唯一。

入口：
    split_repurchase(df, window_start, window_end, series=None)
    run_repurchase_operator(df, window_start, window_end, series=None)
"""

from __future__ import annotations

import pandas as pd

# v2 仅此一种行为；保留常量以兼容既有 import
MODE_FULFILLED = "fulfilled_repurchase"
VALID_MODES = (MODE_FULFILLED,)

BUCKET_PRIOR_FULFILLED = "prior_fulfilled"
BUCKET_NO_PRIOR_HISTORY = "no_prior_history"
BUCKET_SHARED_EXCLUDED = "shared_phone_excluded"
BUCKET_UNKNOWN_IDENTITY = "unknown_identity"

BUCKETS = (
    BUCKET_PRIOR_FULFILLED,
    BUCKET_NO_PRIOR_HISTORY,
    BUCKET_SHARED_EXCLUDED,
    BUCKET_UNKNOWN_IDENTITY,
)

REQUIRED_IDENTITY_COL = "lead_phone_md5"
OWNER_ID_COL = "owner_identity_no"

_PHONE_HEX_RE = r"[0-9a-f]{32}"
_OWNER_ID_RE = r"\d{17}[\dXx]"


def _coerce_dt(df: pd.DataFrame, cols: list[str]) -> None:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")


def _norm_phone(series: pd.Series) -> pd.Series:
    """手机号哈希归一：去空白、小写；合法形态为 32 位十六进制，否则置 NA。"""
    s = series.astype("string").str.strip().str.lower()
    valid = s.str.fullmatch(_PHONE_HEX_RE, na=False)
    return s.where(valid, pd.NA)


def _norm_owner_id(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip()
    return s.where(s.str.fullmatch(_OWNER_ID_RE, na=False), pd.NA)


def split_repurchase(
    df: pd.DataFrame,
    window_start,
    window_end,
    *,
    mode: str = MODE_FULFILLED,
    identity_col: str = REQUIRED_IDENTITY_COL,
    lock_col: str = "lock_time",
    delivery_col: str = "delivery_date",
    invoice_col: str = "invoice_upload_time",
    owner_id_col: str = OWNER_ID_COL,
    series: str | None = None,
    series_col: str = "series_group_logic",
) -> dict:
    """复购 / 首购四桶拆分（v2 / B 方案）。

    df      —— 订单数据，须含 identity_col（默认 lead_phone_md5）；调用方负责
               JOIN order_phone_map 与零售过滤，并保证 order_number 唯一。
    window  —— [window_start, window_end) 左闭右开。
    series  —— 若指定，仅把该 series_group_logic 的订单作为「窗口订单」评估；
               历史不按 series 过滤（老车主可能来自任何既往代际）。
    """
    if df is None or df.empty:
        return {"n": 0, "error": "no_data", "message": "无可用数据。"}
    if mode not in VALID_MODES:
        return {
            "error": "invalid_mode",
            "message": f"v2 仅支持 mode={VALID_MODES}（prior_locker 已移除），收到: {mode}",
        }

    work = df.copy()
    _coerce_dt(work, [lock_col, delivery_col, invoice_col])

    if lock_col not in work.columns or identity_col not in work.columns:
        return {
            "error": "missing_columns",
            "message": f"缺少必需列: {lock_col} 或 {identity_col}"
                       f"（phone JOIN 应在上游调用方完成）",
        }

    start = pd.Timestamp(window_start).normalize()
    end = pd.Timestamp(window_end).normalize()
    if end <= start:
        return {"error": "invalid_window", "message": "window_end 必须晚于 window_start"}

    work["__phone"] = _norm_phone(work[identity_col])

    # ---- 目标窗口订单 ----
    target = work[work[lock_col].notna()
                  & (work[lock_col] >= start) & (work[lock_col] < end)].copy()
    if series is not None and series_col in target.columns:
        target = target[target[series_col].astype(str).eq(str(series))]
    target = target.drop_duplicates(subset=["order_number"])
    n = int(len(target))

    # ---- 窗口前历史（任意代际，不做 series 过滤）----
    hist = work[work[lock_col].notna() & (work[lock_col] < start)].copy()
    hist_at = hist[[delivery_col, invoice_col]].min(axis=1)
    fulfilled_hist = hist[hist_at.notna() & (hist_at < start)]

    # 已完成购车的手机号
    repeat_phones = set(fulfilled_hist["__phone"].dropna().unique())

    # 共享号码（严格 PIT：仅用窗口前已兑现历史判定）
    shared_phones: set = set()
    if owner_id_col in fulfilled_hist.columns and not fulfilled_hist.empty:
        pair = pd.DataFrame({
            "phone": fulfilled_hist["__phone"].values,
            "owner": _norm_owner_id(fulfilled_hist[owner_id_col]).values,
        }).dropna()
        if not pair.empty:
            per_phone = pair.drop_duplicates().groupby("phone")["owner"].nunique()
            shared_phones = set(per_phone[per_phone > 1].index)

    # ---- 四桶（互斥且穷尽）----
    ph = target["__phone"]
    is_shared = ph.isin(shared_phones)
    is_unknown = ph.isna()
    is_repeat = ph.isin(repeat_phones) & ~is_shared & ~is_unknown
    is_first = ~is_shared & ~is_unknown & ~is_repeat

    n_prior_fulfilled = int(is_repeat.sum())
    n_no_prior = int(is_first.sum())
    n_shared = int(is_shared.sum())
    n_unknown = int(is_unknown.sum())

    valid_base = n - n_shared
    repeat_rate = round(n_prior_fulfilled / valid_base, 4) if valid_base else None
    known = n_prior_fulfilled + n_no_prior + n_unknown

    return {
        "type": "repurchase",
        "version": "v2_phone_shared_excluded",
        "mode": mode,
        "window_start": start.strftime("%Y-%m-%d"),
        "window_end": end.strftime("%Y-%m-%d"),
        "series": series,
        "scope": {
            "identity_col": identity_col,
            "identity_semantics": "手机号统计身份（同号复购），不等同于车主身份",
            "fulfilled_by": [delivery_col, invoice_col],
            "history_cutoff": "lock_time < window_start；兑现事件亦须早于 window_start",
            "shared_phone_rule": "窗口前已兑现历史中与 ≥2 个不同 owner_identity_no "
                                 "关联的手机号整号剔除",
            "shared_phone_pit": "仅使用 window_start 之前已兑现的历史判定，不使用未来信息",
            "bucket_definition":
                "互斥且穷尽：prior_fulfilled / no_prior_history / "
                "shared_phone_excluded / unknown_identity",
        },
        "buckets": {
            BUCKET_PRIOR_FULFILLED: n_prior_fulfilled,
            BUCKET_NO_PRIOR_HISTORY: n_no_prior,
            BUCKET_SHARED_EXCLUDED: n_shared,
            BUCKET_UNKNOWN_IDENTITY: n_unknown,
        },
        # 必披露 6 项（metric_definitions「复购口径 v2」第 6 节）
        "report": {
            "target_orders": n,
            "excluded_shared_phone_orders": n_shared,
            "valid_base": valid_base,
            "repeat_orders": n_prior_fulfilled,
            "phone_missing_orders": n_unknown,
            "repeat_rate": repeat_rate,
        },
        "summary": {
            "n": n,
            "repeat": n_prior_fulfilled,
            "suspended": 0,  # v2 不细分退订/悬置
            "first": n_no_prior,
            "unknown": n_unknown,
            "known": known,
            "repeat_rate": repeat_rate,
            "known_pct": round((1 - n_unknown / n) * 100, 1) if n else 0.0,
            "valid_base": valid_base,
            "excluded_shared": n_shared,
            "shared_phones": len(shared_phones),
        },
        "checks": {
            "buckets_sum_equals_target":
                (n_prior_fulfilled + n_no_prior + n_shared + n_unknown) == n,
            "valid_base_identity": (n - n_shared) == valid_base,
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
