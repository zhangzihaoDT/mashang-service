"""预售小订监控 — 泛化 compute + 飞书卡片。

口径来自 shared/schema/business_definition.json：
  - time_periods.{generation}.start = 预售起点
  - monitor.open_hour_by_series.{generation} = 预售开放时刻（默认 20:00）
  - monitor.open_minute_by_series.{generation} = 预售开放分钟（默认 0，如 CM2=20:55）
  - monitor.compare_by_series = 历史对标代际

调用方需先对 df 应用 series_group_logic（列 `series_group_logic`）。
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from utils.monitors.phase import (
    compare_keys,
    open_hour,
    open_minute,
    series_label,
)
from utils.monitors.order_filter import flag_test_orders


def compute(df: pd.DataFrame, business_def: dict, today: pd.Timestamp, generation: str) -> dict:
    time_periods: dict = business_def.get("time_periods", {})
    tp = time_periods.get(generation, {}) or {}
    start = pd.Timestamp(tp["start"]) if tp.get("start") else None
    end = pd.Timestamp(tp["end"]) if tp.get("end") else None
    open_h = open_hour(business_def, generation)
    open_m = open_minute(business_def, generation)
    label = series_label(business_def, generation)

    # 剔除测试单（总部主理店 + 假身份号）；计数按当前代际口径
    test_mask = flag_test_orders(df, business_def)
    if "series_group_logic" in df.columns:
        test_excluded = int((test_mask & df["series_group_logic"].eq(generation)).sum())
    else:
        test_excluded = int(test_mask.sum())
    if test_mask.any():
        df = df.loc[~test_mask].copy()

    # 观测截止点：数据最新时刻，封顶当日 23:59:59
    obs = today.normalize() + pd.Timedelta(hours=23, minutes=59, seconds=59)
    max_it = df["intention_payment_time"].max()
    if pd.notna(max_it):
        obs = min(obs, pd.Timestamp(max_it))

    base = df.loc[
        df["intention_payment_time"].notna(),
        [
            "order_number",
            "intention_payment_time",
            "intention_refund_time",
            "series_group_logic",
            "product_name",
            "parent_region_name",
            "buyer_identity_no",
            "store_name",
        ],
    ].copy()

    metrics = {
        "generation": generation,
        "label": label,
        "open_hour": open_h,
        "open_minute": open_m,
        "test_orders_excluded": test_excluded,
        "today": today.date().isoformat(),
        "series_start": start.date().isoformat() if start is not None else None,
        "series_end": end.date().isoformat() if end is not None else None,
        "obs": obs.isoformat(),
        "elapsed_hours": 0,
        "cum": 0,
        "retention": 0,
        "retention_users": 0,
        "peak_hour": None,
        "peak_count": 0,
        "next_hour_count": 0,
        "start_day_total": 0,
        "start_day_retained": 0,
        "launch_day_total": 0,
        "launch_day_retention": 0,
        "retention_by_product": [],
        "retention_by_region": [],
        "retention_no_region": 0,
        "compare": {},
    }

    if start is None:
        return metrics

    open_t = start + pd.Timedelta(hours=open_h, minutes=open_m)

    current_mask = (
        base["series_group_logic"].eq(generation)
        & (base["intention_payment_time"] >= open_t)
        & (base["intention_payment_time"] <= obs)
    )

    metrics["cum"] = int(base.loc[current_mask, "order_number"].nunique())

    retention_slice = base.loc[
        current_mask & base["intention_refund_time"].isna(),
        ["order_number", "product_name", "parent_region_name", "buyer_identity_no", "store_name"],
    ]
    metrics["retention"] = int(retention_slice["order_number"].nunique()) if not retention_slice.empty else 0

    if not retention_slice.empty:
        order_counts_per_user = retention_slice.groupby("buyer_identity_no")["order_number"].nunique()
        metrics["retention_users"] = int((order_counts_per_user == 1).sum())

        product_counts = retention_slice.groupby("product_name")["order_number"].nunique()
        metrics["retention_by_product"] = sorted(
            [
                {
                    "product_name": p,
                    "count": int(c),
                    "share": round(c / metrics["retention"] * 100, 1),
                    "limited": "限量版" in (p or ""),
                }
                for p, c in product_counts.items()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )

        region_rows = []
        for region_name, region_slice in retention_slice.groupby("parent_region_name"):
            count = int(region_slice["order_number"].nunique())
            cr5 = None
            store_counts = region_slice.dropna(subset=["store_name"]).groupby("store_name")["order_number"].nunique()
            total = float(store_counts.sum())
            if total > 0:
                cr5 = round(float(store_counts.nlargest(5).sum()) / total * 100, 1)
            region_rows.append(
                {
                    "region_name": region_name,
                    "count": count,
                    "share": round(count / metrics["retention"] * 100, 1),
                    "cr5": cr5,
                }
            )
        metrics["retention_by_region"] = sorted(region_rows, key=lambda x: x["count"], reverse=True)
        metrics["retention_no_region"] = int(
            retention_slice.loc[retention_slice["parent_region_name"].isna(), "order_number"].nunique()
        )

    day_window_end = open_t + pd.Timedelta(hours=24)
    day_slice = base.loc[
        base["series_group_logic"].eq(generation)
        & (base["intention_payment_time"] >= open_t)
        & (base["intention_payment_time"] < day_window_end),
        ["order_number", "intention_payment_time", "intention_refund_time"],
    ].copy()
    if not day_slice.empty:
        day_slice["hour"] = day_slice["intention_payment_time"].dt.hour.astype("int64")
        hourly = day_slice.groupby("hour")["order_number"].nunique().reindex(range(24), fill_value=0)
        peak_hour = int(hourly.idxmax())
        metrics["peak_hour"] = peak_hour
        metrics["peak_count"] = int(hourly.iloc[peak_hour])
        metrics["next_hour_count"] = int(hourly.iloc[peak_hour + 1]) if peak_hour < 23 else 0
        metrics["start_day_total"] = int(hourly.sum())
        # 留存口径：窗口内支付且未退（退订晚于窗口末视为留存）
        metrics["start_day_retained"] = int(
            day_slice.loc[
                day_slice["intention_refund_time"].isna()
                | (day_slice["intention_refund_time"] > day_window_end),
                "order_number",
            ].nunique()
        )

    launch_day_end = start + pd.Timedelta(days=1)
    launch_slice = base.loc[
        base["series_group_logic"].eq(generation)
        & (base["intention_payment_time"] >= open_t)
        & (base["intention_payment_time"] < launch_day_end),
        ["order_number", "intention_refund_time"],
    ]
    metrics["launch_day_total"] = int(launch_slice["order_number"].nunique())
    metrics["launch_day_retention"] = int(
        launch_slice.loc[
            launch_slice["intention_refund_time"].isna() | (launch_slice["intention_refund_time"] > launch_day_end),
            "order_number",
        ].nunique()
    )

    if obs > open_t:
        metrics["elapsed_hours"] = round((obs - open_t).total_seconds() / 3600, 1)

    for cmp_key in compare_keys(business_def, generation):
        cmp_tp = time_periods.get(cmp_key, {}) or {}
        if not cmp_tp.get("start"):
            metrics["compare"][cmp_key] = None
            continue
        cmp_start = pd.to_datetime(cmp_tp["start"])
        cmp_open = cmp_start + pd.Timedelta(
            hours=open_hour(business_def, cmp_key), minutes=open_minute(business_def, cmp_key)
        )
        cmp_end = cmp_open + pd.Timedelta(hours=metrics["elapsed_hours"])
        cmp_slice = base.loc[
            base["series_group_logic"].eq(cmp_key)
            & (base["intention_payment_time"] >= cmp_open)
            & (base["intention_payment_time"] <= cmp_end)
            & ((base["intention_refund_time"] > cmp_end) | base["intention_refund_time"].isna()),
            "order_number",
        ]
        metrics["compare"][cmp_key] = int(cmp_slice.nunique())

    return metrics


def build_card(metrics: dict, show_notes: bool = False) -> dict:
    label = metrics.get("label") or metrics["generation"]
    open_h = metrics.get("open_hour", 20)
    open_m = metrics.get("open_minute", 0)
    open_str = f"{open_h:02d}:{open_m:02d}"
    peak_hour_str = f"{metrics['peak_hour']:02d}:00" if metrics["peak_hour"] is not None else "NA"

    cum = metrics.get("cum", 0)
    retention = metrics.get("retention", 0)
    retention_users = metrics.get("retention_users", 0)
    peak_count = metrics.get("peak_count", 0)
    next_hour = metrics.get("next_hour_count", 0)
    start_day_retained = metrics.get("start_day_retained", 0)
    launch_day_retention = metrics.get("launch_day_retention", 0)
    launch_day_total = metrics.get("launch_day_total", 0)

    lines = [f"**{label} 预售指标（{metrics['today']}）**"]

    lines += ["", f"预售小订：**{cum:,}**（预售至今累计意向金支付）"]
    lines.append(f"　累计留存订单：**{retention:,}**（唯一订单用户 {retention_users:,}）")
    lines.append(f"峰值小时：**{peak_count:,}**（{peak_hour_str}）｜峰值后 1h **{next_hour:,}**")
    lines.append(f"开放后 24h 累计留存：**{start_day_retained:,}**")
    lines.append(f"发布会当日留存：**{launch_day_retention:,}**（小订 {launch_day_total:,}）")

    kept_by_product = metrics.get("retention_by_product") or []
    if kept_by_product:
        limited_items = [i for i in kept_by_product if i.get("limited")]
        if limited_items:
            normal_items = [i for i in kept_by_product if not i.get("limited")]
            limited_total = sum(i["count"] for i in limited_items)
            normal_total = sum(i["count"] for i in normal_items)
            lines.append(f"留存分类：限量版 **{limited_total:,}** ｜ 非限量 **{normal_total:,}**")
            for tag, items in (("限量版", limited_items), ("非限量", normal_items)):
                for item in items:
                    lines.append(f"　· {tag}：{item['product_name']}：{item['count']:,}（{item['share']}%）")
        else:
            lines.append("留存明细：")
            for item in kept_by_product:
                lines.append(f"　· {item['product_name']}：{item['count']:,}（{item['share']}%）")
    else:
        lines.append("留存明细：暂无留存订单")

    region_items = metrics.get("retention_by_region") or []
    if region_items:
        parts = [f"{i['region_name']} {i['share']}%" for i in region_items[:5]]
        if len(region_items) > 5:
            parts.append("…")
        no_region = metrics.get("retention_no_region") or 0
        if no_region > 0 and retention:
            parts.append(f"无大区 {round(no_region / retention * 100, 1)}%")
        lines.append(f"分大区：{'｜'.join(parts)}")
    else:
        lines.append("分大区：暂无留存订单")

    compare_str = " / ".join(
        f"{k}（{v:,}）" if v is not None else f"{k}（无数据）" for k, v in metrics["compare"].items()
    )
    lines.append(f"历史对比（自开放起同期留存，相同时长）：**{compare_str}**")

    lines += ["", f"预售期：{metrics.get('series_start', '—')} ~ {metrics.get('series_end', '—')}"]
    obs_raw = metrics.get("obs")
    obs_str = pd.Timestamp(obs_raw).strftime("%Y-%m-%d %H:%M") if obs_raw else "—"
    lines.append(f"观察时间：{obs_str}")

    if show_notes:
        lines.append(f"口径：自开放时刻（{open_str}）起算，不含预售日白天零星订单；小订 = 当日未退意向金订单；留存 = 意向金未退（退订晚于观测截止视为留存）")
        lines.append(f"N=0 发布会当日留存：开放 {open_str} 至当日 24:00 内支付且未退（退订晚于当日 24:00 视为留存）")
        lines.append(f"对标：各代际自开放时刻起与目标相同时长（{metrics.get('elapsed_hours', 0)} 小时）内的留存小订")
        if metrics.get("test_orders_excluded"):
            lines.append(f"已剔除测试单：{metrics['test_orders_excluded']} 笔（总部主理店 + 假身份号）")
        lines.append("数据源：dataset/order_data.parquet + shared/schema/business_definition.json")

    body_md = "\n".join(lines)
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📊 {label} 预售小订监控（{metrics['today']}）"},
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
