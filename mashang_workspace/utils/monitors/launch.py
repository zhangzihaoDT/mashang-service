"""上市锁单监控 — 泛化 compute + 飞书卡片。

口径来自 shared/schema/business_definition.json：
  - time_periods.{generation}.end = 上市日
  - monitor.compare_by_series = 历史对标代际

调用方需先对 df 应用 series_group_logic（列 `series_group_logic`）。
"""

from __future__ import annotations

import re
from datetime import datetime

import pandas as pd

from utils.monitors.phase import compare_keys, open_hour, series_label
from utils.monitors.order_filter import flag_test_orders


def resolve_launch_date(time_periods: dict, key: str) -> pd.Timestamp | None:
    """上市日 = time_periods.{key}.end（缺省回退 finish / start）。"""
    tp = (time_periods or {}).get(key, {}) or {}
    date_str = tp.get("end") or tp.get("finish") or tp.get("start")
    if not date_str:
        return None
    return pd.Timestamp(date_str)


def _is_limited(pname) -> bool:
    """限定版（Jimmy Choo 高定限量版）判定，口径同 l6_m2_daily_retention.py。"""
    p = str(pname).lower() if pname is not None else ""
    return "jimmychoo" in p or "jimmy choo" in p


def _norm_product_name(pname) -> str:
    """product_name 空格归一化：连续空白合并为单空格并去首尾。"""
    if pname is None or str(pname).strip() == "":
        return str(pname or "")
    return re.sub(r"\s+", " ", str(pname)).strip()


def _is_real_lock(row) -> bool:
    """真实用户锁单（收紧口径）：锁单前有小订支付记录且排除内部测试单。"""
    it = row.get("intention_payment_time")
    lt = row.get("lock_time")
    if not (pd.notna(it) and pd.notna(lt) and pd.Timestamp(it) <= pd.Timestamp(lt)):
        return False
    buyer = str(row.get("buyer_identity_no", "") or "").strip()
    owner = str(row.get("owner_identity_no", "") or "").strip()
    if buyer == "9999999" or owner == "9999999":
        return False
    return True


def resolve_launch_open_from_data(
    base: pd.DataFrame, key: str, launch: pd.Timestamp | None, use_data: bool = True
) -> pd.Timestamp | None:
    """开放时刻。目标系列用数据首个 real 锁单；历史对比用上市日 open_hour。"""
    if launch is None:
        return None
    launch_start = launch.normalize()
    if not use_data:
        return launch_start + pd.Timedelta(hours=20)
    real = base.loc[base["series_group_logic"].eq(key)].copy()
    real = real[real.apply(_is_real_lock, axis=1)]
    real_on_launch = real[real["lock_time"] >= launch_start]
    if real_on_launch.empty:
        return launch_start
    return pd.Timestamp(real_on_launch["lock_time"].min())


def compute(df: pd.DataFrame, business_def: dict, today: pd.Timestamp, generation: str) -> dict:
    required_cols = [
        "lock_time",
        "order_number",
        "approve_refund_time",
        "owner_identity_no",
        "buyer_identity_no",
        "order_type",
        "series_group_logic",
        "intention_payment_time",
        "intention_refund_time",
        "deposit_refund_time",
        "deposit_payment_time",
        "product_name",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise KeyError(f"数据缺少列: {', '.join(missing)}")

    # 剔除测试单（总部主理店 + 假身份号）；计数按当前代际口径
    test_mask = flag_test_orders(df, business_def)
    if "series_group_logic" in df.columns:
        test_excluded = int((test_mask & df["series_group_logic"].eq(generation)).sum())
    else:
        test_excluded = int(test_mask.sum())
    if test_mask.any():
        df = df.loc[~test_mask].copy()

    run_date = today.normalize()
    max_lock_time = df["lock_time"].max()
    as_of_date = run_date
    if pd.notna(max_lock_time):
        as_of_date = min(as_of_date, pd.Timestamp(max_lock_time).normalize())

    obs = as_of_date + pd.Timedelta(hours=23, minutes=59, seconds=59)
    if pd.notna(max_lock_time):
        obs = min(obs, pd.Timestamp(max_lock_time))

    time_periods = business_def.get("time_periods", {}) or {}
    launch = resolve_launch_date(time_periods, generation)
    label = series_label(business_def, generation)

    base = df.loc[
        df["lock_time"].notna(),
        [
            "order_number",
            "lock_time",
            "approve_refund_time",
            "owner_identity_no",
            "buyer_identity_no",
            "order_type",
            "series_group_logic",
            "intention_payment_time",
            "intention_refund_time",
            "deposit_refund_time",
            "deposit_payment_time",
            "product_name",
        ],
    ].copy()
    for col in ["intention_payment_time", "intention_refund_time", "deposit_refund_time", "deposit_payment_time"]:
        if not pd.api.types.is_datetime64_any_dtype(base[col]):
            base[col] = pd.to_datetime(base[col], errors="coerce")

    retention = 0
    retention_kept = 0
    retention_kept_limited = 0
    retention_kept_non_limited = 0
    retention_kept_by_product: list[dict] = []
    peak_hour = None
    peak_count = 0
    today_lock_count = 0
    today_user_car_lock_count = 0
    today_intention_conv = 0
    today_direct_lock = 0
    compare: dict = {}

    open_t = None
    if launch is not None:
        open_t = resolve_launch_open_from_data(base, generation, launch)

        obs_slice = base.loc[
            base["series_group_logic"].eq(generation)
            & (base["lock_time"] >= open_t)
            & (base["lock_time"] <= obs),
            ["order_number", "lock_time", "approve_refund_time", "product_name"],
        ]
        retention = int(obs_slice["order_number"].nunique())
        kept_slice = obs_slice.loc[obs_slice["approve_refund_time"].isna()]
        retention_kept = int(kept_slice["order_number"].nunique())
        if not kept_slice.empty:
            kept_slice = kept_slice.assign(
                limited=kept_slice["product_name"].map(_is_limited),
                norm_name=kept_slice["product_name"].map(_norm_product_name),
            )
            retention_kept_limited = int(kept_slice.loc[kept_slice["limited"], "order_number"].nunique())
            retention_kept_non_limited = int(
                kept_slice.loc[~kept_slice["limited"], "order_number"].nunique()
            )
            product_counts = kept_slice.groupby("norm_name")["order_number"].nunique()
            retention_kept_by_product = sorted(
                [
                    {
                        "product_name": p,
                        "count": int(c),
                        "share": round(c / retention_kept * 100, 1),
                        "limited": bool(_is_limited(p)),
                    }
                    for p, c in product_counts.items()
                ],
                key=lambda x: x["count"],
                reverse=True,
            )

        if not obs_slice.empty:
            hourly = (
                obs_slice.assign(hour=obs_slice["lock_time"].dt.hour.astype("int64"))
                .groupby("hour")["order_number"]
                .nunique()
                .reindex(range(24), fill_value=0)
            )
            peak_hour = int(hourly.idxmax())
            peak_count = int(hourly.iloc[peak_hour])

        elapsed = (obs - open_t).total_seconds() / 3600.0 if obs > open_t else 0.0
        for cmp_key in compare_keys(business_def, generation):
            cmp_launch = resolve_launch_date(time_periods, cmp_key)
            cmp_open = (
                cmp_launch.normalize() + pd.Timedelta(hours=open_hour(business_def, cmp_key))
                if cmp_launch is not None
                else None
            )
            if cmp_open is None or elapsed <= 0:
                compare[cmp_key] = None
                continue
            cmp_window_end = cmp_open + pd.Timedelta(hours=elapsed)
            cmp_slice = base.loc[
                base["series_group_logic"].eq(cmp_key)
                & (base["lock_time"] >= cmp_open)
                & (base["lock_time"] <= cmp_window_end),
                "order_number",
            ]
            compare[cmp_key] = int(cmp_slice.nunique())

    if open_t is not None:
        lock_mask = (
            base["series_group_logic"].eq(generation)
            & (base["lock_time"] >= open_t)
            & (base["lock_time"] <= obs)
        )
    else:
        lock_mask = pd.Series(False, index=base.index)
    today_lock_count = int(base.loc[lock_mask, "order_number"].nunique())
    today_user_car_lock_count = int(
        base.loc[lock_mask & (base["order_type"].astype("string") == "用户车"), "order_number"].nunique()
    )
    conv_mask = lock_mask & base["intention_payment_time"].notna() & (base["intention_payment_time"] <= base["lock_time"])
    today_intention_conv = int(base.loc[conv_mask & base.apply(_is_real_lock, axis=1), "order_number"].nunique())
    today_direct_lock = int(today_lock_count) - int(today_intention_conv)

    presale_retained = 0
    if launch is not None:
        tp_key = time_periods.get(generation, {}) or {}
        if tp_key.get("start"):
            presale_open = pd.Timestamp(tp_key["start"]).normalize() + pd.Timedelta(hours=open_hour(business_def, generation))
            retained_mask = (
                df["series_group_logic"].eq(generation)
                & df["intention_payment_time"].notna()
                & (df["intention_payment_time"] >= presale_open)
                & (df["intention_payment_time"] <= obs)
                & df["intention_refund_time"].isna()
            )
            presale_retained = int(df.loc[retained_mask, "order_number"].nunique())

    return {
        "generation": generation,
        "label": label,
        "series": generation,
        "test_orders_excluded": test_excluded,
        "today": today.date().isoformat(),
        "launch": launch.date().isoformat() if launch is not None else None,
        "obs": obs.isoformat(sep=" ", timespec="minutes"),
        "as_of_date": as_of_date.date().isoformat(),
        "run_date": run_date.date().isoformat(),
        "retention": retention,
        "retention_kept": retention_kept,
        "retention_kept_limited": retention_kept_limited,
        "retention_kept_non_limited": retention_kept_non_limited,
        "retention_kept_by_product": retention_kept_by_product,
        "peak_hour": peak_hour,
        "peak_count": peak_count,
        "today_lock_count": today_lock_count,
        "today_user_car_lock_count": today_user_car_lock_count,
        "today_intention_conv": today_intention_conv,
        "today_direct_lock": today_direct_lock,
        "presale_retained": presale_retained,
        "compare": compare,
    }


def build_card(metrics: dict, show_notes: bool = True) -> dict:
    generation = metrics["generation"]
    label = metrics.get("label") or generation
    peak_hour_str = f"{metrics['peak_hour']:02d}:00" if metrics["peak_hour"] is not None else "NA"

    lines = [f"**{label} 上市锁单监控（{metrics['as_of_date']}）**"]

    lines += ["", f"车型：**{label}（{generation}）**"]
    lines.append(
        f"锁单数：**{metrics['today_lock_count']:,}**（用户车 {metrics['today_user_car_lock_count']:,}）"
    )
    lines.append(
        f"　小订转大定：**{metrics['today_intention_conv']:,}**/{metrics['presale_retained']:,}（转大定/留存小订）"
    )
    lines.append(f"　直接锁单数：**{metrics['today_direct_lock']:,}**")

    kept_limited = metrics.get("retention_kept_limited") or 0
    kept_non_limited = metrics.get("retention_kept_non_limited") or 0
    lines.append(
        f"留存锁单分类：限定（Jimmy Choo 高定）**{kept_limited:,}** ｜ 非限定 **{kept_non_limited:,}**"
    )
    kept_by_product = metrics.get("retention_kept_by_product") or []
    if kept_by_product:
        limited_items = [i for i in kept_by_product if i.get("limited")]
        normal_items = [i for i in kept_by_product if not i.get("limited")]
        if limited_items:
            lines.append("　· 限定：")
            for item in limited_items:
                lines.append(f"　　  {item['product_name']}：{item['count']:,}（{item['share']}%）")
        if normal_items:
            lines.append("　· 非限定：")
            for item in normal_items:
                lines.append(f"　　  {item['product_name']}：{item['count']:,}（{item['share']}%）")
    else:
        lines.append("　· 暂无留存锁单明细")

    lines.append(
        f"上市至今累计：**{metrics['retention']:,}**，峰值小时 **{metrics['peak_count']:,}**（{peak_hour_str}）"
    )
    lines.append(f"上市至今累计留存：**{metrics['retention_kept']:,}**")

    compare_str = " / ".join(
        f"{k}（{v:,}）" if v is not None else f"{k}（无数据）" for k, v in metrics["compare"].items()
    )
    lines.append(f"历史对比：**{compare_str}**")

    lines += ["", f"上市日：{metrics['launch']}"]
    lines.append(f"观察时间：{metrics['obs']}")

    if show_notes:
        lines.append("口径：开放时刻起至观察时间的锁单累计（目标开放时刻 = 上市日当天首个转大定，无则上市日 00:00；排除测试单）；历史对比 = 各代际自上市日开放时刻起算相同时长")
        if metrics.get("test_orders_excluded"):
            lines.append(f"已剔除测试单：{metrics['test_orders_excluded']} 笔（总部主理店 + 假身份号）")
        lines.append("数据源：dataset/order_data.parquet + shared/schema/business_definition.json")

    if metrics["as_of_date"] != metrics["run_date"]:
        lines.append(f"（数据未覆盖运行日 {metrics['run_date']}，锁单数以 {metrics['as_of_date']} 计）")

    body_md = "\n".join(lines)
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📈 {label} 上市锁单监控（{metrics['as_of_date']}）"},
                "template": "blue",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": body_md}},
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "content": f"统计时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}],
                },
            ],
        },
    }
