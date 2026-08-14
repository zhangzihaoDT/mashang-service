#!/usr/bin/env python
"""
锁单归因分析 / 锁单归因对比分析

基于 dataset/lock_attribution_data.parquet 输出指定时间窗口内锁单用户的归因指标；
支持对比两个任意锁单样本（时间窗口 / 渠道 / 车系均可不同），输出差异高亮的对比分析报告。
归因指标计算参考 26W06_Tool_calls/index_summary.py 的 _calc_attribution_metrics
（等价实现于 scripts/lock_attribution.py:_calc_attribution_metrics_for_range）。

指标口径:
  - 锁单用户数: 归因表中 lock_time 落在窗口内的去重用户（按 user_phone_md5）
  - 数据完整度: 归因锁单用户数 / order_data 去重锁单人数（order_type != 试驾车）
  - 平均触达次数: 锁单用户首条归因记录的 touch_index 均值
  - 平均转化时长(天): lock_time - create_time 均值
  - 锁单用户主要渠道 TopN: 按 lc_small_channel_name 聚合锁单用户数
  - 锁单用户分类占比（观察口径）: One-Touch / Hesitant / Cross-Channel / Long / Repeat
  - 跨渠道锁单用户主要助攻渠道 TopN

用法:
    python research_scripts/lock_attribution_analysis.py                                  # 2023 全年
    python research_scripts/lock_attribution_analysis.py --start-date 2026-01-01 --end-date 2026-06-30
    python research_scripts/lock_attribution_analysis.py --series LS8
    python research_scripts/lock_attribution_analysis.py --channel 抖音
    # 对比两个样本（示例: 2024 vs 2026 锁单用户）
    python research_scripts/lock_attribution_analysis.py \
        --start-date 2024-01-01 --end-date 2024-12-31 --label "2024年锁单" \
        --compare-start-date 2026-01-01 --compare-end-date 2026-12-31 --compare-label "2026年锁单" \
        --html
    python research_scripts/lock_attribution_analysis.py \
        --start-date 2024-01-01 --end-date 2024-12-31 \
        --compare-start-date 2026-01-01 --compare-end-date 2026-12-31 --format json --output outputs/tables/
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

from utils.result_contract import build_success_contract, contract_to_terminal, save_contract_json

ATTRIBUTION_PARQUET = REPO_ROOT / "dataset" / "lock_attribution_data.parquet"
ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"


def _safe_ratio(numer: float | int, denom: float | int) -> float | None:
    denom = float(denom)
    if denom == 0.0:
        return None
    return float(numer) / denom


def _to_percent_1dp(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{round(value * 100.0, 1):.1f}%"


def _pick_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols_lower = {str(c).lower(): c for c in df.columns}
    for cand in candidates:
        key = str(cand).lower()
        if key in cols_lower:
            return str(cols_lower[key])
    return None


def _resolve_journey_columns(df: pd.DataFrame) -> dict[str, str | None]:
    return {
        "user_phone_md5": _pick_column(df, ["lc_user_phone_md5", "ic_user_phone_md5", "user_phone_md5", "phone_md5"]),
        "main_code": _pick_column(df, ["lc_main_code", "ic_main_code", "main_code", "clue_code"]),
        "channel": _pick_column(
            df,
            [
                "lc_small_channel_name",
                "ic_small_channel_name",
                "lc_small_channel",
                "small_channel_name",
                "channel_name",
            ],
        ),
        "create_time": _pick_column(df, ["lc_create_time", "ic_create_time", "create_time", "created_time"]),
        "lock_time": _pick_column(
            df,
            ["lc_order_lock_time_min", "ic_order_lock_time_min", "order_lock_time_min", "order_lock_time", "lock_time"],
        ),
    }


def _prepare_attribution_df(attribution_path: Path) -> tuple[pd.DataFrame, dict[str, str | None]]:
    cols = [
        "lc_main_code",
        "lc_user_phone_md5",
        "lc_create_time",
        "lc_order_lock_time_min",
        "lc_small_channel_name",
    ]
    try:
        df = pd.read_parquet(attribution_path, columns=cols)
    except Exception:
        df = pd.read_parquet(attribution_path)

    cols_map = _resolve_journey_columns(df)
    main_code_col = cols_map["main_code"] or "lc_main_code"
    user_col = cols_map["user_phone_md5"] or "lc_user_phone_md5"
    create_time_col = cols_map["create_time"] or "lc_create_time"
    lock_time_col = cols_map["lock_time"] or "lc_order_lock_time_min"

    if user_col not in df.columns or create_time_col not in df.columns or lock_time_col not in df.columns:
        return df, cols_map

    df = df.copy()
    df[create_time_col] = pd.to_datetime(df[create_time_col], errors="coerce")
    df[lock_time_col] = pd.to_datetime(df[lock_time_col], errors="coerce")

    if main_code_col in df.columns:
        df = df.drop_duplicates(subset=[main_code_col], keep="first").copy()

    df = df.dropna(subset=[user_col, create_time_col]).copy()
    sort_cols = [user_col, create_time_col]
    if main_code_col in df.columns:
        sort_cols.append(main_code_col)
    df = df.sort_values(sort_cols, kind="mergesort")
    df["touch_index"] = df.groupby(user_col, dropna=False).cumcount() + 1
    delta = df[lock_time_col] - df[create_time_col]
    df["time_to_lock_days"] = (delta.dt.total_seconds() / 86400).astype("Float64")
    return df, cols_map


def _calc_order_lock_people_non_test_drive(
    order_table_path: Path,
    start: pd.Timestamp,
    end_exclusive: pd.Timestamp,
    series: str | None,
) -> int | None:
    cols = ["lock_time", "owner_identity_no", "buyer_identity_no", "order_type"]
    if series is not None:
        cols.append("series")
    try:
        df = pd.read_parquet(order_table_path, columns=cols)
    except Exception:
        return None

    person_col = None
    for cand in ["owner_identity_no", "buyer_identity_no", "owner_cell_phone"]:
        if cand in df.columns:
            person_col = cand
            break

    if "lock_time" not in df.columns or person_col is None:
        return None

    df = df.copy()
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    lock_mask = df["lock_time"].notna() & (df["lock_time"] >= start) & (df["lock_time"] < end_exclusive)
    if "order_type" in df.columns:
        lock_mask = lock_mask & df[person_col].notna() & (df["order_type"] != "试驾车")
    else:
        lock_mask = lock_mask & df[person_col].notna()

    df_lock = df.loc[lock_mask].copy()
    if series is not None:
        if "series" not in df_lock.columns:
            raise ValueError("order_data 缺少 series 字段，无法按车系过滤数据完整度分母")
        df_lock = df_lock[df_lock["series"] == series].copy()

    return int(df_lock[person_col].nunique())


def _calc_main_code_whitelist_from_order(
    order_table_path: Path,
    start: pd.Timestamp,
    end_exclusive: pd.Timestamp,
    series: str,
) -> set[str]:
    cols = ["lock_time", "order_type", "series", "main_lead_id"]
    try:
        df = pd.read_parquet(order_table_path, columns=cols)
    except Exception:
        df = pd.read_parquet(order_table_path)

    for c in ["lock_time", "series", "main_lead_id"]:
        if c not in df.columns:
            raise ValueError(f"order_data 缺少字段 {c}，无法按车系分组过滤")

    df = df.copy()
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    lock_mask = df["lock_time"].notna() & (df["lock_time"] >= start) & (df["lock_time"] < end_exclusive)
    if "order_type" in df.columns:
        lock_mask = lock_mask & (df["order_type"] != "试驾车")

    df_lock = df.loc[lock_mask, ["series", "main_lead_id"]].copy()
    df_lock = df_lock[df_lock["main_lead_id"].notna() & (df_lock["series"] == series)].copy()
    return set(df_lock["main_lead_id"].astype("string").dropna().unique().tolist())


def _calc_attribution_metrics_for_range(
    df: pd.DataFrame,
    cols_map: dict[str, str | None],
    start: pd.Timestamp,
    end_exclusive: pd.Timestamp,
    order_lock_people_non_test_drive: int | None,
    lock_channel_filter: str | None,
    lock_main_code_whitelist: set[str] | None,
    top_n: int = 5,
) -> dict[str, object]:
    main_code_col = cols_map["main_code"] or "lc_main_code"
    user_col = cols_map["user_phone_md5"] or "lc_user_phone_md5"
    create_time_col = cols_map["create_time"] or "lc_create_time"
    lock_time_col = cols_map["lock_time"] or "lc_order_lock_time_min"
    channel_col = cols_map["channel"]

    def _empty_result() -> dict[str, object]:
        return {
            "锁单用户数": 0,
            "数据完整度": (
                None
                if order_lock_people_non_test_drive is None
                else _to_percent_1dp(_safe_ratio(0, order_lock_people_non_test_drive))
            ),
            "平均触达次数": None,
            "平均转化时长(天)": None,
            "锁单用户主要渠道Top%d" % top_n: [],
            "锁单用户分类占比（观察口径）": [],
            "跨渠道锁单用户主要助攻渠道Top%d" % top_n: [],
        }

    if user_col not in df.columns or create_time_col not in df.columns or lock_time_col not in df.columns:
        return _empty_result()

    locked = df[df[lock_time_col].notna() & (df[lock_time_col] >= start) & (df[lock_time_col] < end_exclusive)].copy()
    if locked.empty:
        return _empty_result()

    sort_cols = [user_col, lock_time_col]
    if main_code_col in locked.columns:
        sort_cols.append(main_code_col)
    locked = locked.sort_values(sort_cols, kind="mergesort")
    per_user = locked.groupby(user_col, dropna=False, as_index=False).first()

    if lock_channel_filter is not None and channel_col is not None and channel_col in per_user.columns:
        target = str(lock_channel_filter).strip()
        chan = per_user[channel_col].astype("string").fillna("").str.strip()
        per_user = per_user[chan == target].copy()
        if per_user.empty:
            return _empty_result()

    if lock_main_code_whitelist is not None:
        if main_code_col not in per_user.columns:
            raise ValueError("锁单归因数据缺少 main_code 字段，无法按车系分组过滤")
        whitelist = {str(x) for x in lock_main_code_whitelist if x is not None}
        c = per_user[main_code_col].astype("string")
        per_user = per_user[c.isin(whitelist)].copy()
        if per_user.empty:
            return _empty_result()

    locked_users = int(per_user[user_col].nunique(dropna=True))
    touch_mean = float(per_user["touch_index"].mean()) if not per_user.empty else None
    ttl = per_user["time_to_lock_days"].dropna()
    ttl_mean = float(ttl.mean()) if not ttl.empty else None

    channel_top_out: list[dict[str, object]] = []
    lens_out_records: list[dict[str, object]] = []
    assist_out_records: list[dict[str, object]] = []

    if channel_col is not None and channel_col in df.columns and main_code_col in df.columns:
        lock_time_by_user = per_user[[user_col, lock_time_col, channel_col, "time_to_lock_days", main_code_col]].copy()
        lock_time_by_user = lock_time_by_user.rename(
            columns={
                user_col: "user",
                lock_time_col: "first_lock_time",
                channel_col: "lock_channel",
                "time_to_lock_days": "ttl_days",
                main_code_col: "lock_main_code",
            }
        )
        lock_time_by_user["user"] = lock_time_by_user["user"].astype("string")
        lock_time_by_user["lock_channel"] = lock_time_by_user["lock_channel"].astype("string")

        touches = df[[user_col, main_code_col, channel_col, create_time_col]].copy()
        touches = touches[touches[create_time_col].notna()].copy()
        touches["user"] = touches[user_col].astype("string")
        touches = touches.merge(lock_time_by_user[["user", "first_lock_time"]], on="user", how="inner")
        touches = touches[touches[create_time_col].le(touches["first_lock_time"])].copy()

        touch_agg = touches.groupby("user", dropna=False).agg(
            touches_to_lock=(create_time_col, "size"),
            distinct_channels_to_lock=(channel_col, lambda s: int(pd.Series(s.dropna()).nunique())),
        )
        touch_agg = touch_agg.reset_index()

        user_summary = lock_time_by_user.merge(touch_agg, on="user", how="left")
        user_summary["touches_to_lock"] = user_summary["touches_to_lock"].fillna(0).astype(int)
        user_summary["distinct_channels_to_lock"] = user_summary["distinct_channels_to_lock"].fillna(0).astype(int)

        channel_series = user_summary["lock_channel"].astype("string").fillna("(missing)")
        vc = channel_series.value_counts(dropna=False)
        total_users = int(vc.sum())
        top = vc.head(max(int(top_n), 1))
        channel_top = pd.DataFrame({"channel": top.index.astype("string"), "locked_users": top.values})
        other_cnt = int(vc.iloc[len(top):].sum())
        if other_cnt:
            channel_top = pd.concat(
                [channel_top, pd.DataFrame([{"channel": "其他", "locked_users": other_cnt}])],
                ignore_index=True,
            )
        channel_top["pct"] = channel_top["locked_users"] / max(total_users, 1)
        channel_top["pct"] = channel_top["pct"].map(lambda x: _to_percent_1dp(float(x)) if pd.notna(x) else None)
        channel_top_out = channel_top.to_dict(orient="records")

        one_touch_users = int(user_summary["touches_to_lock"].astype(int).eq(1).sum())
        same_channel_multi_users = int(
            (
                user_summary["touches_to_lock"].astype(int).gt(1)
                & user_summary["distinct_channels_to_lock"].astype(int).eq(1)
            ).sum()
        )
        cross_channel_users = int(user_summary["distinct_channels_to_lock"].astype(int).gt(1).sum())
        long_users = int(user_summary["ttl_days"].astype("Float64").gt(14).fillna(False).sum())
        long_14_60_users = int(
            (
                user_summary["ttl_days"].astype("Float64").gt(14)
                & user_summary["ttl_days"].astype("Float64").lt(60)
            )
            .fillna(False)
            .sum()
        )
        prior_lock_users = df.loc[df[lock_time_col].notna() & df[lock_time_col].lt(start), user_col].astype("string")
        prior_lock_users = set(prior_lock_users.dropna().tolist())
        repeat_lock_users = int(user_summary["user"].astype("string").isin(prior_lock_users).sum())

        lens_out = pd.DataFrame(
            [
                {"category": "One-Touch (Decisive)", "users": one_touch_users},
                {"category": "Hesitant (Same Channel, Multiple Touches)", "users": same_channel_multi_users},
                {"category": "Cross-Channel (Comparison Shopper)", "users": cross_channel_users},
                {"category": "Long Consideration (>14 Days)", "users": long_users},
                {"category": "Long Consideration (>14 Days & <60 Days)", "users": long_14_60_users},
                {"category": "Repeat Lockers (Had Prior Locks)", "users": repeat_lock_users},
            ]
        )
        lens_out["pct"] = lens_out["users"] / max(int(user_summary.shape[0]), 1)
        lens_out["pct"] = lens_out["pct"].map(lambda x: _to_percent_1dp(float(x)) if pd.notna(x) else None)
        lens_out_records = lens_out.to_dict(orient="records")

        if cross_channel_users <= 0:
            assist_out = pd.DataFrame(columns=["assist_channel", "assist_touches", "pct"])
        else:
            cross_users = user_summary.loc[user_summary["distinct_channels_to_lock"].gt(1), "user"].copy()
            assist = touches[touches["user"].astype("string").isin(cross_users.astype("string"))].copy()
            assist = assist.merge(lock_time_by_user[["user", "lock_channel", "lock_main_code"]], on="user", how="left")
            assist["assist_channel"] = assist[channel_col].astype("string")
            assist = assist[
                assist["assist_channel"].notna() & assist["lock_channel"].notna() & assist["lock_main_code"].notna()
            ].copy()
            assist = assist[assist["assist_channel"] != assist["lock_channel"]].copy()
            assist = assist[assist[main_code_col] != assist["lock_main_code"]].copy()

            vc_assist = assist["assist_channel"].value_counts(dropna=False)
            assist_total = int(len(assist))
            top_assist = vc_assist.head(max(int(top_n), 1))
            assist_out = pd.DataFrame(
                {"assist_channel": top_assist.index.astype("string"), "assist_touches": top_assist.values}
            )
            assist_out["pct"] = assist_out["assist_touches"] / max(assist_total, 1)
            assist_out["pct"] = assist_out["pct"].map(lambda x: _to_percent_1dp(float(x)) if pd.notna(x) else None)

        assist_out_records = assist_out.to_dict(orient="records")

    return {
        "锁单用户数": locked_users,
        "数据完整度": (
            None
            if order_lock_people_non_test_drive is None
            else _to_percent_1dp(_safe_ratio(locked_users, order_lock_people_non_test_drive))
        ),
        "平均触达次数": (None if touch_mean is None else round(touch_mean, 2)),
        "平均转化时长(天)": (None if ttl_mean is None else round(ttl_mean, 2)),
        "锁单用户主要渠道Top%d" % top_n: channel_top_out,
        "锁单用户分类占比（观察口径）": lens_out_records,
        "跨渠道锁单用户主要助攻渠道Top%d" % top_n: assist_out_records,
    }


LENS_LABELS = {
    "One-Touch (Decisive)": "单次触达即锁单（决定性）",
    "Hesitant (Same Channel, Multiple Touches)": "同渠道多次触达（犹豫型）",
    "Cross-Channel (Comparison Shopper)": "跨渠道比价（比较型）",
    "Long Consideration (>14 Days)": "长决策（>14 天）",
    "Long Consideration (>14 Days & <60 Days)": "长决策（14–60 天）",
    "Repeat Lockers (Had Prior Locks)": "复购锁单（此前已锁）",
}

# 观察口径按维度分组：前 3 类按触达行为互斥，长决策按转化时长（与触达行为重叠），复购按历史
LENS_DIMENSIONS = [
    (
        "触达行为（互斥，合计 = 100%）",
        ("One-Touch (Decisive)", "Hesitant (Same Channel, Multiple Touches)", "Cross-Channel (Comparison Shopper)"),
    ),
    (
        "转化时长（与触达行为重叠的子集）",
        ("Long Consideration (>14 Days)", "Long Consideration (>14 Days & <60 Days)"),
    ),
    (
        "复购历史（独立维度）",
        ("Repeat Lockers (Had Prior Locks)",),
    ),
]


def _render_barcells(rows: list[dict], value_key: str, text_key: str, total: float | None = None) -> str:
    vals = [float(r[value_key]) for r in rows if r.get(value_key) is not None]
    if not vals:
        return ""
    mx = max(vals)
    parts: list[str] = []
    for r in rows:
        v = float(r.get(value_key) or 0)
        bar_w = _to_percent_1dp(v / mx) if mx else "0%"
        share = _to_percent_1dp(_safe_ratio(v, total)) if total else None
        txt = str(r.get(text_key) or "") + (f"  {share}" if share else "")
        parts.append(
            f'<div class="barcell"><div class="bar" style="width:{bar_w}"></div>'
            f'<div class="txt">{txt}</div></div>'
        )
    return "\n".join(parts)


def _render_channel_table(rows: list[dict], top_n: int) -> str:
    if not rows:
        return '<tr><td colspan="4">无数据</td></tr>'
    total = sum(float(r.get("locked_users") or 0) for r in rows)
    trs: list[str] = []
    for i, r in enumerate(rows, start=1):
        users = int(r.get("locked_users") or 0)
        pct = r.get("pct")
        trs.append(
            f'<tr><td class="rank">{i}</td><td><strong>{r.get("channel", "")}</strong></td>'
            f'<td class="num">{users:,}</td><td class="num">{pct or ""}</td>'
            f'<td class="num">{_to_percent_1dp(_safe_ratio(users, total)) or ""}</td></tr>'
        )
    return "\n".join(trs)


def _render_lens_table(rows: list[dict], total_users: int) -> str:
    if not rows:
        return '<tr><td colspan="3">无数据</td></tr>'
    by_cat = {str(r.get("category", "")): r for r in rows}
    trs: list[str] = []
    for dim_label, cats in LENS_DIMENSIONS:
        group = [by_cat[c] for c in cats if c in by_cat]
        if not group:
            continue
        trs.append(f'<tr class="section-row"><td colspan="4">{dim_label}</td></tr>')
        for r in group:
            label = LENS_LABELS.get(str(r.get("category", "")), str(r.get("category", "")))
            users = int(r.get("users") or 0)
            pct = r.get("pct")
            bar_pct = _to_percent_1dp(_safe_ratio(users, max(total_users, 1)))
            trs.append(
                f'<tr><td style="padding-left:24px;"><strong>{label}</strong></td>'
                f'<td class="num">{users:,}</td>'
                f'<td class="num">{pct or ""}</td>'
                f'<td><div class="barcell"><div class="bar" style="width:{bar_pct or "0%"}"></div>'
                f'<div class="txt">{bar_pct or ""}</div></div></td></tr>'
            )
    return "\n".join(trs)


def _render_assist_table(rows: list[dict], top_n: int) -> str:
    if not rows:
        return '<tr><td colspan="4">无数据</td></tr>'
    total = sum(float(r.get("assist_touches") or 0) for r in rows)
    trs: list[str] = []
    for i, r in enumerate(rows, start=1):
        touches = int(r.get("assist_touches") or 0)
        pct = r.get("pct")
        trs.append(
            f'<tr><td class="rank">{i}</td><td><strong>{r.get("assist_channel", "")}</strong></td>'
            f'<td class="num">{touches:,}</td><td class="num">{pct or ""}</td>'
            f'<td class="num">{_to_percent_1dp(_safe_ratio(touches, total)) or ""}</td></tr>'
        )
    return "\n".join(trs)


def render_html(
    metrics: dict,
    start_label: str,
    end_label: str,
    top_n: int,
    static_prefix: str,
    scope: dict,
    warnings: list[str],
) -> str:
    import html as html_lib

    esc = html_lib.escape

    def _fmt(v) -> str:
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v:,.2f}"
        return str(v)

    channel_rows = metrics.get("锁单用户主要渠道Top%d" % top_n, [])
    lens_rows = metrics.get("锁单用户分类占比（观察口径）", [])
    assist_rows = metrics.get("跨渠道锁单用户主要助攻渠道Top%d" % top_n, [])
    locked_users = int(metrics.get("锁单用户数") or 0)

    filters = scope.get("filters", {})
    filter_parts = []
    if filters.get("series"):
        filter_parts.append(f"车系 {esc(str(filters['series']))}")
    if filters.get("channel"):
        filter_parts.append(f"锁单渠道 {esc(str(filters['channel']))}")
    filter_desc = "、" .join(filter_parts) if filter_parts else "无（全量）"

    completeness = metrics.get("数据完整度")
    completeness_cls = "warning" if completeness and completeness.rstrip("%").endswith("%") and float(completeness.rstrip("%")) > 100.0 else ""

    warnings_html = ""
    if warnings:
        items = "".join(f"<li>{esc(w)}</li>" for w in warnings)
        warnings_html = f'<section class="card"><h2>⚠ 数据提示</h2><ul>{items}</ul></section>'

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>锁单归因分析 | {esc(start_label)} ~ {esc(end_label)}</title>
<link rel="stylesheet" href="{static_prefix}/templates/report_style.css" />
</head>
<body class="report-page">
<header>
  <div class="container">
    <div class="brand">
      <img class="brand-avatar" src="{static_prefix}/assets/brand/raccoon_avatar_light.png" alt="" />
      <span class="brand-name">Raccoon Research</span>
    </div>
    <span class="header-meta">锁单归因分析 | {esc(start_label)} ~ {esc(end_label)}</span>
  </div>
</header>

<main class="container">
  <section class="hero">
    <h1>锁单归因分析</h1>
    <p>{esc(start_label)} ~ {esc(end_label)} · {esc(filter_desc)} · 归因数据源 lock_attribution_data.parquet</p>
  </section>

  <section class="kpi-grid">
    <div class="kpi-card">
      <div class="label">锁单用户数</div>
      <div class="value">{locked_users:,}</div>
      <div class="change neutral">按 user_phone_md5 去重</div>
    </div>
    <div class="kpi-card">
      <div class="label">平均触达次数</div>
      <div class="value">{_fmt(metrics.get("平均触达次数"))}</div>
      <div class="change neutral">首条归因记录前累计触达</div>
    </div>
    <div class="kpi-card">
      <div class="label">平均转化时长（天）</div>
      <div class="value">{_fmt(metrics.get("平均转化时长(天)"))}</div>
      <div class="change neutral">lock_time − create_time</div>
    </div>
    <div class="kpi-card {completeness_cls}">
      <div class="label">数据完整度</div>
      <div class="value">{completeness or "—"}</div>
      <div class="change neutral">归因锁单用户 / order_data 锁单人数</div>
    </div>
  </section>

  {warnings_html}

  <section class="card">
    <h2>① 锁单用户主要渠道 Top{top_n}</h2>
    <div class="chart-box" style="padding:12px 16px;">
      {_render_barcells(channel_rows, "locked_users", "channel", locked_users)}
    </div>
    <div class="table-wrap"><table class="report-table">
      <thead><tr><th>#</th><th>渠道</th><th>锁单用户</th><th>占锁单用户</th><th>占 Top 合计</th></tr></thead>
      <tbody>
        {_render_channel_table(channel_rows, top_n)}
      </tbody>
    </table></div>
    <div class="section-note">按锁单渠道（lc_small_channel_name）聚合锁单用户数；"其他"为 Top{top_n} 之外渠道合计。</div>
  </section>

  <section class="card">
    <h2>② 锁单用户分类占比（观察口径）</h2>
    <div class="table-wrap"><table class="report-table">
      <thead><tr><th>分类</th><th>用户数</th><th>占比</th><th>分布</th></tr></thead>
      <tbody>
        {_render_lens_table(lens_rows, locked_users)}
      </tbody>
    </table></div>
    <div class="section-note">分类分属三个独立维度，百分比按各自口径计算、不可跨维度相加：① 触达行为（单次触达 / 同渠道多次 / 跨渠道比价）互斥，合计 = 100%；② 转化时长（&gt;14 天、14–60 天）与触达行为重叠，如单次触达用户中仍有 46% 转化时长 &gt;14 天；③ 复购为独立维度。</div>
  </section>

  <section class="card">
    <h2>③ 跨渠道锁单用户主要助攻渠道 Top{top_n}</h2>
    <div class="chart-box" style="padding:12px 16px;">
      {_render_barcells(assist_rows, "assist_touches", "assist_channel", sum(float(r.get("assist_touches") or 0) for r in assist_rows))}
    </div>
    <div class="table-wrap"><table class="report-table">
      <thead><tr><th>#</th><th>助攻渠道</th><th>助攻触达</th><th>占助攻触达</th><th>占 Top 合计</th></tr></thead>
      <tbody>
        {_render_assist_table(assist_rows, top_n)}
      </tbody>
    </table></div>
    <div class="section-note">仅统计跨渠道比价用户中，与锁单渠道不同且非锁单主单的触达渠道。</div>
  </section>

  <section class="card">
    <h2>口径与数据说明</h2>
    <table class="report-table scope-table">
      <tbody>
        <tr><td class="scope-label">数据源</td><td>{esc(str(scope.get("data_source", "")))}</td></tr>
        <tr><td class="scope-label">时间窗口</td><td>{esc(start_label)} ~ {esc(end_label)}</td></tr>
        <tr><td class="scope-label">过滤条件</td><td>{esc(filter_desc)}</td></tr>
        <tr><td class="scope-label">指标口径</td><td>{esc(str(scope.get("metric_definition", "")))}</td></tr>
      </tbody>
    </table>
  </section>
</main>

<footer>
  <img class="brand-sig" src="{static_prefix}/assets/brand/zihao_signature_transparent.png" alt="Raccoon Research" />
  <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
</footer>
</body>
</html>
"""


def format_compare_terminal(comparison: dict) -> str:
    lines: list[str] = []
    lines.append("[Summary]")
    k_user = next((k for k in comparison["kpis"] if k["key"] == "锁单用户数"), None)
    if k_user:
        lines.append(
            f"  {comparison['base_label']} vs {comparison['compare_label']}："
            f"锁单用户 {_fmt_metric_value(k_user['base'],'int')} → {_fmt_metric_value(k_user['compare'],'int')}"
        )
    lines.append("")
    lines.append("[Scope]")
    lines.append(f"  样本 A: {comparison['base_label']}")
    lines.append(f"  样本 B: {comparison['compare_label']}")
    lines.append("")
    lines.append("[Result]")
    lines.append("  KPI 对比:")
    for k in comparison["kpis"]:
        dtxt, dcls = _fmt_delta(k["delta"], k["delta_pct"], k["kind"])
        mark = {"up": "▲", "down": "▼", "flat": "·"}[k["direction"]]
        lines.append(
            f"    {k['key']}: {_fmt_metric_value(k['base'],k['kind'])} → {_fmt_metric_value(k['compare'],k['kind'])}  "
            f"{mark} {dtxt}"
        )
    if comparison["insights"]:
        lines.append("  关键差异点:")
        for it in comparison["insights"]:
            mark = "▲" if it["direction"] == "up" else ("▼" if it["direction"] == "down" else "·")
            lines.append(f"    {mark} {it['title']}: {it['base']} → {it['compare']} ({it['delta']})")
    lines.append("")
    if comparison["channels"]:
        lines.append("  渠道份额变化 (pp):")
        for r in comparison["channels"]:
            d = r["delta_pp"]
            d_txt = "—" if d is None else f"{d:+.1f}pp"
            absent = "  (未进入对方 TopN)" if d is None else ""
            lines.append(
                f"    {r['channel']}: {_fmt_pp(r['base_pct'])} → {_fmt_pp(r['compare_pct'])}  {d_txt}{absent}"
            )
    if comparison["lens"]:
        lines.append("  观察口径变化 (pp):")
        for r in comparison["lens"]:
            d = r["delta_pp"]
            d_txt = "—" if d is None else f"{d:+.1f}pp"
            label = LENS_LABELS.get(r["category"], r["category"])
            lines.append(
                f"    {label}: {_fmt_pp(r['base_pct'])} → {_fmt_pp(r['compare_pct'])}  {d_txt}"
            )
    return "\n".join(lines)


def _delta_html(delta: float | None, kind: str) -> str:
    if delta is None:
        return '<span class="delta-neutral">—</span>'
    if kind == "int":
        txt = f"{int(round(delta)):+,}" if abs(delta - round(delta)) < 0.5 else f"{delta:+,}"
    elif kind == "float":
        txt = f"{delta:+.2f}"
    else:
        txt = f"{delta:+.1f}pp"
    cls = "delta-neutral" if delta == 0 else ("delta-positive" if delta > 0 else "delta-negative")
    return f'<span class="{cls}">{txt}</span>'


def _fmt_pp(v: float | None) -> str:
    return "—" if v is None else f"{v:.1f}%"


def render_compare_html(
    comparison: dict,
    base_scope: dict,
    compare_scope: dict,
    top_n: int,
    static_prefix: str,
    warnings: list[str],
) -> str:
    import html as html_lib

    esc = html_lib.escape
    bl = comparison["base_label"]
    cl = comparison["compare_label"]

    def _insight_card(it: dict) -> str:
        arrow = {"up": "▲", "down": "▼"}.get(it["direction"], "·")
        cls = {"up": "positive", "down": "negative"}.get(it["direction"], "neutral")
        return (
            f'<div class="summary-card {cls}">'
            f'<div class="summary-value">{esc(it["title"])}</div>'
            f'<div class="summary-label">{esc(it["base"])} → {esc(it["compare"])}</div>'
            f'<div class="summary-hint">{esc(it["delta"])} · {esc(it["note"])} {arrow}</div>'
            f"</div>"
        )

    insights_html = (
        '<section class="summary-grid">' + "".join(_insight_card(it) for it in comparison["insights"]) + "</section>"
        if comparison["insights"]
        else ""
    )

    kpi_rows = "".join(
        f'<tr><td><strong>{esc(k["key"])}</strong></td>'
        f'<td class="num">{esc(_fmt_metric_value(k["base"], k["kind"]))}</td>'
        f'<td class="num">{esc(_fmt_metric_value(k["compare"], k["kind"]))}</td>'
        f'<td class="num">{_delta_html(k["delta"], k["kind"])}</td></tr>'
        for k in comparison["kpis"]
    )

    chan_rows = "".join(
        f'<tr><td><strong>{esc(r["channel"])}</strong></td>'
        f'<td class="num">{r["base_users"]:,}</td>'
        f'<td class="num">{_fmt_pp(r["base_pct"])}</td>'
        f'<td class="num">{r["compare_users"]:,}</td>'
        f'<td class="num">{_fmt_pp(r["compare_pct"])}</td>'
        f'<td class="num">{_delta_html(r["delta_pp"], "pct")}</td></tr>'
        for r in comparison["channels"]
    )

    lens_by_dim: list[str] = []
    by_cat = {r["category"]: r for r in comparison["lens"]}
    for dim_label, cats in LENS_DIMENSIONS:
        rows = [by_cat[c] for c in cats if c in by_cat]
        if not rows:
            continue
        lens_by_dim.append(f'<tr class="section-row"><td colspan="6">{esc(dim_label)}</td></tr>')
        for r in rows:
            lens_by_dim.append(
                f'<tr><td style="padding-left:24px;"><strong>{esc(LENS_LABELS.get(r["category"], r["category"]))}</strong></td>'
                f'<td class="num">{r["base_users"]:,}</td>'
                f'<td class="num">{_fmt_pp(r["base_pct"])}</td>'
                f'<td class="num">{r["compare_users"]:,}</td>'
                f'<td class="num">{_fmt_pp(r["compare_pct"])}</td>'
                f'<td class="num">{_delta_html(r["delta_pp"], "pct")}</td></tr>'
            )
    lens_rows = "\n".join(lens_by_dim)

    assist_rows = "".join(
        f'<tr><td><strong>{esc(r["channel"])}</strong></td>'
        f'<td class="num">{r["base_touches"]:,}</td>'
        f'<td class="num">{_fmt_pp(r["base_pct"])}</td>'
        f'<td class="num">{r["compare_touches"]:,}</td>'
        f'<td class="num">{_fmt_pp(r["compare_pct"])}</td>'
        f'<td class="num">{_delta_html(r["delta_pp"], "pct")}</td></tr>'
        for r in comparison["assist"]
    )

    def _scope_line(scope: dict, label: str) -> str:
        flt = scope.get("filters", {})
        parts = []
        if flt.get("series"):
            parts.append(f"车系 {flt['series']}")
        if flt.get("channel"):
            parts.append(f"渠道 {flt['channel']}")
        desc = "、".join(parts) if parts else "全量"
        return f'{esc(label)}{"：" if label else ""}{esc(desc)}'

    warnings_html = ""
    if warnings:
        items = "".join(f"<li>{esc(w)}</li>" for w in warnings)
        warnings_html = f'<section class="card"><h2>⚠ 数据提示</h2><ul>{items}</ul></section>'

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>锁单归因对比分析 | {esc(bl)} vs {esc(cl)}</title>
<link rel="stylesheet" href="{static_prefix}/templates/report_style.css" />
</head>
<body class="report-page">
<header>
  <div class="container">
    <div class="brand">
      <img class="brand-avatar" src="{static_prefix}/assets/brand/raccoon_avatar_light.png" alt="" />
      <span class="brand-name">Raccoon Research</span>
    </div>
    <span class="header-meta">锁单归因对比分析 | {esc(bl)} vs {esc(cl)}</span>
  </div>
</header>

<main class="container">
  <section class="hero">
    <h1>锁单归因对比分析</h1>
    <p>{esc(bl)} vs {esc(cl)} · {esc(_scope_line(base_scope, "样本 A"))} · {esc(_scope_line(compare_scope, "样本 B"))}</p>
  </section>

  <section class="card">
    <h2>关键差异点</h2>
    <div class="section-note">按差异幅度排序；绿色=上升、红色=下降。</div>
    {insights_html}
  </section>

  {warnings_html}

  <section class="card">
    <h2>核心指标对比</h2>
    <div class="table-wrap"><table class="report-table">
      <thead><tr><th>指标</th><th>{esc(bl)}</th><th>{esc(cl)}</th><th>Δ</th></tr></thead>
      <tbody>
        {kpi_rows}
      </tbody>
    </table></div>
    <div class="section-note">Δ 为绝对差；锁单用户数附相对变化率。</div>
  </section>

  <section class="card">
    <h2>① 锁单用户主要渠道对比（Top{top_n}）</h2>
    <div class="table-wrap"><table class="report-table">
      <thead>
        <tr>
          <th>渠道</th>
          <th>{esc(bl)} 用户</th><th>{esc(bl)} 份额</th>
          <th>{esc(cl)} 用户</th><th>{esc(cl)} 份额</th>
          <th>Δ 份额</th>
        </tr>
      </thead>
      <tbody>
        {chan_rows}
      </tbody>
    </table></div>
    <div class="section-note">份额 = 渠道锁单用户 / 样本锁单用户数；Δ 份额以百分点 (pp) 计，升为绿、降为红。</div>
  </section>

  <section class="card">
    <h2>② 锁单用户分类占比对比（观察口径）</h2>
    <div class="table-wrap"><table class="report-table">
      <thead>
        <tr>
          <th>分类</th>
          <th>{esc(bl)} 用户</th><th>{esc(bl)} 占比</th>
          <th>{esc(cl)} 用户</th><th>{esc(cl)} 占比</th>
          <th>Δ 占比</th>
        </tr>
      </thead>
      <tbody>
        {lens_rows}
      </tbody>
    </table></div>
    <div class="section-note">分类分属三个独立维度（触达行为互斥 / 转化时长重叠 / 复购独立），占比按各口径计算、不可跨维度相加。</div>
  </section>

  <section class="card">
    <h2>③ 跨渠道锁单用户助攻渠道对比（Top{top_n}）</h2>
    <div class="table-wrap"><table class="report-table">
      <thead>
        <tr>
          <th>助攻渠道</th>
          <th>{esc(bl)} 触达</th><th>{esc(bl)} 占比</th>
          <th>{esc(cl)} 触达</th><th>{esc(cl)} 占比</th>
          <th>Δ 占比</th>
        </tr>
      </thead>
      <tbody>
        {assist_rows}
      </tbody>
    </table></div>
    <div class="section-note">仅统计跨渠道比价用户中，与锁单渠道不同且非锁单主单的触达渠道。</div>
  </section>

  <section class="card">
    <h2>口径与数据说明</h2>
    <table class="report-table scope-table">
      <tbody>
        <tr><td class="scope-label">数据源</td><td>{esc(str(base_scope.get("data_source", "")))}</td></tr>
        <tr><td class="scope-label">样本 A</td><td>{esc(bl)}（{esc(_scope_line(base_scope, ""))}）</td></tr>
        <tr><td class="scope-label">样本 B</td><td>{esc(cl)}（{esc(_scope_line(compare_scope, ""))}）</td></tr>
        <tr><td class="scope-label">指标口径</td><td>{esc(str(base_scope.get("metric_definition", "")))}</td></tr>
      </tbody>
    </table>
  </section>
</main>

<footer>
  <img class="brand-sig" src="{static_prefix}/assets/brand/zihao_signature_transparent.png" alt="Raccoon Research" />
  <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
</footer>
</body>
</html>
"""


def parse_args():
    p = argparse.ArgumentParser(description="锁单归因分析 / 对比分析")
    p.add_argument("--start-date", type=str, default="2023-01-01", help="样本 A 开始日期 (YYYY-MM-DD)")
    p.add_argument("--end-date", type=str, default="2023-12-31", help="样本 A 结束日期 (YYYY-MM-DD)")
    p.add_argument("--channel", type=str, default=None, help="样本 A 锁单渠道过滤 (lc_small_channel_name)")
    p.add_argument("--series", type=str, default=None, help="样本 A 车系过滤 (LS6/L6/LS7/LS8/LS9)")
    p.add_argument("--label", type=str, default=None, help="样本 A 显示标签 (默认 日期范围)")
    p.add_argument("--compare-start-date", type=str, default=None, help="样本 B 开始日期 (YYYY-MM-DD)")
    p.add_argument("--compare-end-date", type=str, default=None, help="样本 B 结束日期 (YYYY-MM-DD)")
    p.add_argument("--compare-channel", type=str, default=None, help="样本 B 锁单渠道过滤")
    p.add_argument("--compare-series", type=str, default=None, help="样本 B 车系过滤")
    p.add_argument("--compare-label", type=str, default=None, help="样本 B 显示标签 (默认 日期范围)")
    p.add_argument("--top-n", type=int, default=5, help="TopN 渠道数量 (默认 5)")
    p.add_argument("--output", type=str, default=None, help="输出目录 (默认 outputs/tables/)")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    p.add_argument("--html", action="store_true", help="输出品牌化 HTML 报告到 outputs/reports/")
    return p.parse_args()


def _compute_static_prefix(output_dir: Path) -> str:
    try:
        return str(Path(_WS_ROOT).resolve().relative_to(output_dir.resolve())).replace("\\", "/")
    except ValueError:
        return "../.."


def _pct_to_float(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().rstrip("%").strip()
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _sample_label(start_date: str, end_date: str, series: str | None, channel: str | None) -> str:
    parts: list[str] = []
    if series:
        parts.append(f"series={series}")
    if channel:
        parts.append(f"channel={channel}")
    suffix = "[" + ", ".join(parts) + "]" if parts else ""
    return f"{start_date}~{end_date}{suffix}"


def _compute_sample(
    start_date: str,
    end_date: str,
    series: str | None,
    channel: str | None,
    top_n: int,
    attr_df: pd.DataFrame,
    cols_map: dict[str, str | None],
) -> tuple[dict, list[str], dict]:
    start = pd.Timestamp(start_date).normalize()
    end_exclusive = pd.Timestamp(end_date).normalize() + pd.Timedelta(days=1)
    if end_exclusive <= start:
        raise ValueError("end-date 不能早于 start-date")

    main_code_whitelist = None
    denom = None
    if series is not None:
        if not ORDER_PARQUET.exists():
            raise FileNotFoundError(f"指定 --series 时需提供 order_data {ORDER_PARQUET}")
        main_code_whitelist = _calc_main_code_whitelist_from_order(ORDER_PARQUET, start, end_exclusive, series)
        denom = _calc_order_lock_people_non_test_drive(ORDER_PARQUET, start, end_exclusive, series)
    elif ORDER_PARQUET.exists():
        denom = _calc_order_lock_people_non_test_drive(ORDER_PARQUET, start, end_exclusive, None)

    metrics = _calc_attribution_metrics_for_range(
        df=attr_df,
        cols_map=cols_map,
        start=start,
        end_exclusive=end_exclusive,
        order_lock_people_non_test_drive=denom,
        lock_channel_filter=channel,
        lock_main_code_whitelist=main_code_whitelist,
        top_n=top_n,
    )

    warnings: list[str] = []
    if metrics.get("数据完整度") and metrics["数据完整度"].startswith(("1", "2", "3", "4", "5", "6", "7", "8", "9")) and float(metrics["数据完整度"].rstrip("%")) > 100.0:
        warnings.append(
            "数据完整度 > 100%：归因表锁单用户数多于 order_data 去重锁单人数，"
            "说明 lock_attribution_data.parquet 覆盖范围大于 order_data 主表，请按业务口径解释"
        )

    return metrics, warnings, {"channel": channel, "series": series}


def _fmt_metric_value(v, kind: str) -> str:
    if v is None:
        return "—"
    if kind == "int":
        return f"{int(v):,}"
    if kind == "float":
        return f"{float(v):,.2f}"
    return str(v)


def _fmt_delta(delta: float | None, delta_pct: float | None, kind: str) -> tuple[str, str]:
    """返回 (delta 文本, css class)。"""
    if delta is None:
        return "—", "delta-neutral"
    if kind == "int":
        if abs(delta - round(delta)) < 0.5:
            txt = f"{int(round(delta)):+,}"
        else:
            txt = f"{delta:+,}"
    elif kind == "float":
        txt = f"{delta:+.2f}"
    else:  # pct
        txt = f"{delta:+.1f}pp"
    if delta_pct is not None and kind == "int":
        txt += f" ({delta_pct:+.1f}%)"
    if delta == 0:
        return txt, "delta-neutral"
    return txt, ("delta-positive" if delta > 0 else "delta-negative")


def _compute_comparison(
    base: dict,
    compare: dict,
    base_label: str,
    compare_label: str,
    top_n: int,
) -> dict:
    bm, cm = base["metrics"], compare["metrics"]
    out: dict = {"base_label": base_label, "compare_label": compare_label}

    # ── KPI 对比 ──
    kpis: list[dict] = []
    for key, kind in [("锁单用户数", "int"), ("平均触达次数", "float"), ("平均转化时长(天)", "float"), ("数据完整度", "pct")]:
        b = bm.get(key)
        c = cm.get(key)
        bnum = _pct_to_float(b) if kind == "pct" else (None if b is None else float(b))
        cnum = _pct_to_float(c) if kind == "pct" else (None if c is None else float(c))
        delta = (cnum - bnum) if (bnum is not None and cnum is not None) else None
        delta_pct = None
        if bnum is not None and cnum is not None and bnum != 0:
            delta_pct = (cnum - bnum) / abs(bnum) * 100
        direction = "flat"
        if delta is not None and abs(delta) > 1e-9:
            direction = "up" if delta > 0 else "down"
        kpis.append(
            {
                "key": key,
                "kind": kind,
                "base": b,
                "compare": c,
                "delta": delta,
                "delta_pct": delta_pct,
                "direction": direction,
            }
        )
    out["kpis"] = kpis

    # ── 渠道份额对比（合并两样本 TopN 渠道集） ──
    bchan = bm.get("锁单用户主要渠道Top%d" % top_n, [])
    cchan = cm.get("锁单用户主要渠道Top%d" % top_n, [])
    bmap = {str(r.get("channel")): r for r in bchan}
    cmap = {str(r.get("channel")): r for r in cchan}
    channels: list[dict] = []
    for name in list(bmap.keys()) + [n for n in cmap if n not in bmap]:
        br, cr = bmap.get(name) or {}, cmap.get(name) or {}
        b_pct, c_pct = _pct_to_float(br.get("pct")), _pct_to_float(cr.get("pct"))
        dpp = (c_pct - b_pct) if (b_pct is not None and c_pct is not None) else None
        channels.append(
            {
                "channel": name,
                "base_users": int(br.get("locked_users") or 0),
                "compare_users": int(cr.get("locked_users") or 0),
                "base_pct": b_pct,
                "compare_pct": c_pct,
                "delta_pp": dpp,
            }
        )
    channels.sort(key=lambda r: (r["delta_pp"] is None, -(r["delta_pp"] or 0)))
    out["channels"] = channels

    # ── 观察口径分类对比 ──
    blen = bm.get("锁单用户分类占比（观察口径）", [])
    clen = cm.get("锁单用户分类占比（观察口径）", [])
    bmap = {str(r.get("category")): r for r in blen}
    cmap = {str(r.get("category")): r for r in clen}
    lens: list[dict] = []
    for cat in LENS_LABELS:
        br, cr = bmap.get(cat) or {}, cmap.get(cat) or {}
        b_pct, c_pct = _pct_to_float(br.get("pct")), _pct_to_float(cr.get("pct"))
        dpp = (c_pct - b_pct) if (b_pct is not None and c_pct is not None) else None
        lens.append(
            {
                "category": cat,
                "base_users": int(br.get("users") or 0),
                "compare_users": int(cr.get("users") or 0),
                "base_pct": b_pct,
                "compare_pct": c_pct,
                "delta_pp": dpp,
            }
        )
    out["lens"] = lens

    # ── 助攻渠道对比 ──
    bas = bm.get("跨渠道锁单用户主要助攻渠道Top%d" % top_n, [])
    cas = cm.get("跨渠道锁单用户主要助攻渠道Top%d" % top_n, [])
    bmap = {str(r.get("assist_channel")): r for r in bas}
    cmap = {str(r.get("assist_channel")): r for r in cas}
    assist: list[dict] = []
    for name in list(bmap.keys()) + [n for n in cmap if n not in bmap]:
        br, cr = bmap.get(name) or {}, cmap.get(name) or {}
        b_pct, c_pct = _pct_to_float(br.get("pct")), _pct_to_float(cr.get("pct"))
        dpp = (c_pct - b_pct) if (b_pct is not None and c_pct is not None) else None
        assist.append(
            {
                "channel": name,
                "base_touches": int(br.get("assist_touches") or 0),
                "compare_touches": int(cr.get("assist_touches") or 0),
                "base_pct": b_pct,
                "compare_pct": c_pct,
                "delta_pp": dpp,
            }
        )
    assist.sort(key=lambda r: (r["delta_pp"] is None, -(r["delta_pp"] or 0)))
    out["assist"] = assist

    # ── 关键差异点 ──
    insights: list[dict] = []

    def _add_insight(title: str, base: str, compare: str, delta_txt: str, direction: str, note: str = "", score: float = 0.0):
        insights.append(
            {
                "title": title,
                "base": base,
                "compare": compare,
                "delta": delta_txt,
                "direction": direction,
                "note": note,
                "score": abs(score),
            }
        )

    k_user = next(k for k in kpis if k["key"] == "锁单用户数")
    if k_user["delta"] is not None and k_user["delta"] != 0:
        dtxt, _ = _fmt_delta(k_user["delta"], k_user["delta_pct"], "int")
        _add_insight(
            "锁单用户规模",
            _fmt_metric_value(k_user["base"], "int"),
            _fmt_metric_value(k_user["compare"], "int"),
            dtxt,
            k_user["direction"],
            note=f"{base_label} 锁单用户 {_fmt_metric_value(k_user['base'],'int')} → {compare_label} {_fmt_metric_value(k_user['compare'],'int')}",
            score=k_user["delta_pct"] if k_user["delta_pct"] is not None else 0,
        )
    k_touch = next(k for k in kpis if k["key"] == "平均触达次数")
    if k_touch["delta"] is not None and abs(k_touch["delta"]) > 0.05:
        dtxt, _ = _fmt_delta(k_touch["delta"], k_touch["delta_pct"], "float")
        _add_insight("平均触达次数", _fmt_metric_value(k_touch["base"], "float"), _fmt_metric_value(k_touch["compare"], "float"), dtxt, k_touch["direction"], score=k_touch["delta"])
    k_ttl = next(k for k in kpis if k["key"] == "平均转化时长(天)")
    if k_ttl["delta"] is not None and abs(k_ttl["delta"]) > 0.5:
        dtxt, _ = _fmt_delta(k_ttl["delta"], k_ttl["delta_pct"], "float")
        _add_insight("平均转化时长（天）", _fmt_metric_value(k_ttl["base"], "float"), _fmt_metric_value(k_ttl["compare"], "float"), dtxt, k_ttl["direction"], score=k_ttl["delta"])

    chan_with_delta = [r for r in channels if r["delta_pp"] is not None]
    if chan_with_delta:
        top_up = max(chan_with_delta, key=lambda r: r["delta_pp"])
        top_dn = min(chan_with_delta, key=lambda r: r["delta_pp"])
        if top_up["delta_pp"] >= 0.5:
            _add_insight(
                f"渠道份额上升 ↑ {top_up['channel']}",
                _fmt_metric_value(top_up["base_pct"], "float") + "%" if top_up["base_pct"] is not None else "—",
                _fmt_metric_value(top_up["compare_pct"], "float") + "%" if top_up["compare_pct"] is not None else "—",
                f"{top_up['delta_pp']:+.1f}pp",
                "up",
                note=f"份额 {top_up['base_pct'] or 0:.1f}% → {top_up['compare_pct'] or 0:.1f}%",
                score=top_up["delta_pp"],
            )
        if top_dn["delta_pp"] <= -0.5:
            _add_insight(
                f"渠道份额下降 ↓ {top_dn['channel']}",
                _fmt_metric_value(top_dn["base_pct"], "float") + "%" if top_dn["base_pct"] is not None else "—",
                _fmt_metric_value(top_dn["compare_pct"], "float") + "%" if top_dn["compare_pct"] is not None else "—",
                f"{top_dn['delta_pp']:+.1f}pp",
                "down",
                note=f"份额 {top_dn['base_pct'] or 0:.1f}% → {top_dn['compare_pct'] or 0:.1f}%",
                score=abs(top_dn["delta_pp"]),
            )

    for dim_label, cats in LENS_DIMENSIONS:
        dim_rows = [r for r in lens if r["category"] in cats and r["delta_pp"] is not None]
        if not dim_rows:
            continue
        biggest = max(dim_rows, key=lambda r: abs(r["delta_pp"]))
        if abs(biggest["delta_pp"]) >= 0.5:
            _add_insight(
                f"{dim_label.split('（')[0]}变化：{LENS_LABELS.get(biggest['category'], biggest['category'])}",
                _fmt_metric_value(biggest["base_pct"], "float") + "%" if biggest["base_pct"] is not None else "—",
                _fmt_metric_value(biggest["compare_pct"], "float") + "%" if biggest["compare_pct"] is not None else "—",
                f"{biggest['delta_pp']:+.1f}pp",
                "up" if biggest["delta_pp"] > 0 else "down",
                score=biggest["delta_pp"],
            )

    assist_with_delta = [r for r in assist if r["delta_pp"] is not None]
    if assist_with_delta:
        biggest = max(assist_with_delta, key=lambda r: abs(r["delta_pp"]))
        if abs(biggest["delta_pp"]) >= 0.5:
            _add_insight(
                f"助攻渠道变动：{biggest['channel']}",
                _fmt_metric_value(biggest["base_pct"], "float") + "%" if biggest["base_pct"] is not None else "—",
                _fmt_metric_value(biggest["compare_pct"], "float") + "%" if biggest["compare_pct"] is not None else "—",
                f"{biggest['delta_pp']:+.1f}pp",
                "up" if biggest["delta_pp"] > 0 else "down",
                score=biggest["delta_pp"],
            )

    insights.sort(key=lambda r: r["score"], reverse=True)
    out["insights"] = insights[:8]
    return out


def main():
    args = parse_args()

    if not ATTRIBUTION_PARQUET.exists():
        print(f"错误: 未找到锁单归因数据 {ATTRIBUTION_PARQUET}", file=sys.stderr)
        sys.exit(1)

    attr_df, cols_map = _prepare_attribution_df(ATTRIBUTION_PARQUET)
    cmd = "python " + " ".join(sys.argv)

    compare_mode = any(
        x is not None
        for x in (args.compare_start_date, args.compare_end_date, args.compare_channel, args.compare_series)
    )

    base_metric_def = (
        "锁单用户数 = COUNTD(user_phone_md5 WHERE lock_time in range)；"
        "数据完整度 = 归因锁单用户数 / order_data 去重锁单人数(非试驾车)；"
        "平均触达次数 = 首条归因记录 touch_index 均值；"
        "平均转化时长 = lock_time - create_time 均值"
    )

    try:
        if compare_mode:
            if args.compare_start_date is None or args.compare_end_date is None:
                print("错误: 对比模式需同时提供 --compare-start-date 和 --compare-end-date", file=sys.stderr)
                sys.exit(1)
            base_metrics, base_warnings, base_filters = _compute_sample(
                args.start_date, args.end_date, args.series, args.channel, args.top_n, attr_df, cols_map
            )
            compare_metrics, compare_warnings, compare_filters = _compute_sample(
                args.compare_start_date,
                args.compare_end_date,
                args.compare_series,
                args.compare_channel,
                args.top_n,
                attr_df,
                cols_map,
            )
            base_label = args.label or _sample_label(args.start_date, args.end_date, args.series, args.channel)
            compare_label = args.compare_label or _sample_label(
                args.compare_start_date, args.compare_end_date, args.compare_series, args.compare_channel
            )
            comparison = _compute_comparison(
                {"metrics": base_metrics},
                {"metrics": compare_metrics},
                base_label,
                compare_label,
                args.top_n,
            )

            base_scope = {
                "data_source": str(ATTRIBUTION_PARQUET),
                "time_window": {"start_date": args.start_date, "end_date": args.end_date},
                "filters": base_filters,
                "metric_definition": base_metric_def,
            }
            compare_scope = {
                "data_source": str(ATTRIBUTION_PARQUET),
                "time_window": {"start_date": args.compare_start_date, "end_date": args.compare_end_date},
                "filters": compare_filters,
                "metric_definition": base_metric_def,
            }
            warnings = list(dict.fromkeys(base_warnings + compare_warnings))

            k_user = next((k for k in comparison["kpis"] if k["key"] == "锁单用户数"), None)
            summary = (
                f"{base_label} vs {compare_label}：锁单用户 "
                f"{_fmt_metric_value(k_user['base'],'int')} → {_fmt_metric_value(k_user['compare'],'int')}"
                if k_user
                else f"{base_label} vs {compare_label} 锁单归因对比"
            )
            result = {"summary": summary, "comparison": comparison}

            scope = {
                "data_source": str(ATTRIBUTION_PARQUET),
                "comparison": {
                    "base": {"label": base_label, "time_window": base_scope["time_window"], "filters": base_filters},
                    "compare": {"label": compare_label, "time_window": compare_scope["time_window"], "filters": compare_filters},
                },
                "metric_definition": base_metric_def,
            }
            ctx = {
                "metric": "lock_attribution_comparison",
                "available_dimensions": ["channel", "series", "touch_category"],
                "base": {"label": base_label, "start_date": args.start_date, "end_date": args.end_date},
                "compare": {
                    "label": compare_label,
                    "start_date": args.compare_start_date,
                    "end_date": args.compare_end_date,
                },
            }
            fname_prefix = (
                f"lock_attribution_compare_{args.start_date}_{args.end_date}"
                f"_vs_{args.compare_start_date}_{args.compare_end_date}"
            )
            terminal_text = format_compare_terminal(comparison)
        else:
            metrics, warnings, filters = _compute_sample(
                args.start_date, args.end_date, args.series, args.channel, args.top_n, attr_df, cols_map
            )
            label = args.label or _sample_label(args.start_date, args.end_date, args.series, args.channel)
            result = {
                "summary": f"{label} 锁单用户数: {metrics['锁单用户数']}",
                "metrics": metrics,
                "dimensions": [
                    {
                        "name": "锁单用户主要渠道Top%d" % args.top_n,
                        "items": metrics.get("锁单用户主要渠道Top%d" % args.top_n, []),
                    }
                ],
            }
            scope = {
                "data_source": str(ATTRIBUTION_PARQUET),
                "time_window": {"start_date": args.start_date, "end_date": args.end_date},
                "filters": filters,
                "metric_definition": base_metric_def,
            }
            ctx = {
                "metric": "lock_attribution",
                "available_dimensions": ["channel", "series", "touch_category"],
                "start_date": args.start_date,
                "end_date": args.end_date,
            }
            if args.channel:
                ctx["channel"] = args.channel
            if args.series:
                ctx["series"] = args.series
            fname_prefix = f"lock_attribution_{args.start_date}_{args.end_date}"
            terminal_text = None
    except (ValueError, FileNotFoundError) as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    artifacts = {}
    out_path = None
    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{fname_prefix}.json"
        out_path = out_dir / fname
        artifacts["json"] = str(out_path)

    html_path = None
    if args.html:
        html_dir = Path(args.output) if args.output else _WS_ROOT / "outputs" / "reports"
        html_dir.mkdir(parents=True, exist_ok=True)
        html_path = html_dir / f"{fname_prefix}.html"
        artifacts["html"] = str(html_path)

    contract = build_success_contract(
        script="mashang_workspace/research_scripts/lock_attribution_analysis.py",
        command=cmd,
        scope=scope,
        result=result,
        followup_context=ctx,
        warnings=warnings,
        artifacts=artifacts,
    )

    if args.format == "json":
        if out_path is not None:
            save_contract_json(contract, out_path)
            print(str(out_path))
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        if compare_mode and terminal_text is not None:
            print(terminal_text)
        else:
            print(contract_to_terminal(contract))

    if html_path is not None:
        if compare_mode:
            html = render_compare_html(
                comparison=comparison,
                base_scope=base_scope,
                compare_scope=compare_scope,
                top_n=args.top_n,
                static_prefix=_compute_static_prefix(html_path.parent),
                warnings=warnings,
            )
        else:
            html = render_html(
                metrics=metrics,
                start_label=args.start_date,
                end_label=args.end_date,
                top_n=args.top_n,
                static_prefix=_compute_static_prefix(html_path.parent),
                scope=scope,
                warnings=warnings,
            )
        html_path.write_text(html, encoding="utf-8")

    return result


if __name__ == "__main__":
    main()
