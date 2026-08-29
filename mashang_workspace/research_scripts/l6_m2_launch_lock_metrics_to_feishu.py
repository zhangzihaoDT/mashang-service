#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
针对车型（time_periods.{series}.end 为上市日）的上市锁单监控脚本。
参考 l6_m2_presale_metrics_to_feishu.py 结构，内容结构见下方卡片说明。

卡片内容：
  - 车型：监控目标（series_group_logic 键，默认 DM2）
  - 锁单数：as_of 当日锁单数（含用户车明细）
  - 上市当日累计：上市日（time_periods.end）当日锁单累计 + 峰值小时
  - 上市至今累计留存：自上市日起累计未退订（approve_refund_time 为空）的唯一订单
  - 留存锁单分类：留存锁单中限定（product_name 含 JimmyChoo/Jimmy Choo，参考 l6_m2_daily_retention.py）/非限定各多少，并列出分 product_name 数量
  - 历史对比：DM1 / CM2 / LS9 / LS8 在相同 N 日窗口的留存
    （N = as_of − 上市日 + 1，口径与 l6_m2_launch_lock_metrics_to_feishu 一致）

口径依据：shared/schema/business_definition.json
  - time_periods.{series}.end = 上市日
  - series_group_logic 归类（支持 {priority, condition} 对象与旧字符串格式）

用法：
  python mashang_workspace/research_scripts/l6_m2_launch_lock_metrics_to_feishu.py             # 默认监控 DM2
  python mashang_workspace/research_scripts/l6_m2_launch_lock_metrics_to_feishu.py --series LS9
  python mashang_workspace/research_scripts/l6_m2_launch_lock_metrics_to_feishu.py --dry-run   # 只打印卡片
  python mashang_workspace/research_scripts/l6_m2_launch_lock_metrics_to_feishu.py --as-of 2026-08-28
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUSINESS_DEF = _REPO_ROOT / "shared" / "schema" / "business_definition.json"
_ORDER_DATA = _REPO_ROOT / "dataset" / "order_data.parquet"

DEFAULT_SERIES = "DM2"
COMPARE_KEYS = ["DM1", "CM2", "LS9", "LS8"]
DEFAULT_GROUP = "其他"
OPEN_HOUR = 20  # 各代际上市日统一在 20:00 开放锁单（已验证 DM1/CM2/LS9/LS8）


def load_business_definition(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    return json.loads(file_path.read_text(encoding="utf-8"))


# ---------- series_group_logic 表达式解析（安全实现，非 eval） ----------

def _like(value, pattern):
    if value is None:
        return False
    pattern = pattern[1:-1] if len(pattern) >= 2 and pattern[0] == "'" and pattern[-1] == "'" else pattern
    parts = []
    for ch in pattern:
        if ch == "%":
            parts.append(".*")
        elif ch == "_":
            parts.append(".")
        else:
            parts.append(re.escape(ch))
    return re.fullmatch("^" + "".join(parts) + "$", str(value)) is not None


def _tokenize(expr):
    tokens, i, n = [], 0, len(expr)
    while i < n:
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue
        if ch in ("(", ")"):
            tokens.append(ch)
            i += 1
            continue
        if ch == "'":
            j = i + 1
            while j < n and expr[j] != "'":
                j += 1
            tokens.append(expr[i : j + 1] if j < n else expr[i:])
            i = j + 1 if j < n else n
            continue
        j = i
        while j < n and (expr[j].isalnum() or expr[j] == "_"):
            j += 1
        tokens.append(expr[i:j])
        i = j
    return [t for t in tokens if t]


def _parse_logic(expr):
    tokens = _tokenize(expr)
    idx = 0

    def peek():
        return tokens[idx] if idx < len(tokens) else None

    def take():
        nonlocal idx
        tok = tokens[idx] if idx < len(tokens) else None
        idx += 1
        return tok

    def parse_expr():
        node = parse_term()
        while True:
            if peek() and peek().upper() == "OR":
                take()
                node = ("OR", node, parse_term())
            else:
                break
        return node

    def parse_term():
        node = parse_factor()
        while True:
            if peek() and peek().upper() == "AND":
                take()
                node = ("AND", node, parse_factor())
            else:
                break
        return node

    def parse_factor():
        if peek() and peek().upper() == "NOT":
            take()
            return ("NOT", parse_factor())
        return parse_atom()

    def parse_atom():
        if peek() == "(":
            take()
            inner = parse_expr()
            if peek() == ")":
                take()
            return inner
        left = take()
        if not left:
            return ("LIT", False)
        not_flag = False
        if peek() and peek().upper() == "NOT":
            take()
            not_flag = True
        if peek() and peek().upper() == "LIKE":
            take()
        pattern = take()
        return ("COND", not_flag, left, pattern)

    return parse_expr()


def _eval_ast(ast, pname):
    op = ast[0]
    if op == "OR":
        return _eval_ast(ast[1], pname) or _eval_ast(ast[2], pname)
    if op == "AND":
        return _eval_ast(ast[1], pname) and _eval_ast(ast[2], pname)
    if op == "NOT":
        return not _eval_ast(ast[1], pname)
    if op == "COND":
        not_flag, left, pattern = ast[1], ast[2], ast[3]
        if not left or str(left) != "product_name":
            return False
        res = _like(pname, pattern or "")
        return (not res) if not_flag else res
    if op == "LIT":
        return bool(ast[1])
    return False


def _rule_condition(rule) -> str:
    """提取规则表达式字符串，兼容旧字符串格式与新的 {priority, condition} 对象格式。"""
    if isinstance(rule, dict):
        return str(rule.get("condition", ""))
    return str(rule)


def _rule_priority(rule, default: int = 0) -> int:
    """提取规则优先级；旧字符串格式视为 priority=0。"""
    if isinstance(rule, dict):
        try:
            return int(rule.get("priority", default))
        except (TypeError, ValueError):
            return default
    return default


def apply_series_group_logic(df: pd.DataFrame, business_def: dict, asts: dict) -> pd.DataFrame:
    logic: dict = business_def.get("series_group_logic", {})
    if "product_name" not in df.columns:
        df["series_group_logic"] = pd.NA
        return df

    default_group = DEFAULT_GROUP
    rules = []
    for i, (group, cond) in enumerate(logic.items()):
        expr = _rule_condition(cond)
        if str(expr).strip().upper() == "ELSE":
            default_group = group
            continue
        rules.append((_rule_priority(cond), i, group))
    rules.sort(key=lambda r: (-r[0], r[1]))

    group_col = pd.Series(pd.NA, index=df.index, dtype="string")
    for _, _, group in rules:
        mask = df["product_name"].map(lambda p: _eval_ast(asts[group], p)).fillna(False)
        assignable = group_col.isna() & mask
        if assignable.any():
            group_col = group_col.where(~assignable, group)

    df["series_group_logic"] = group_col.fillna(default_group).astype("string")
    return df


# ---------- 指标计算 ----------

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
    """product_name 空格归一化：连续空白合并为单空格并去首尾，用于合并同一产品的空格变体。"""
    if pname is None or str(pname).strip() == "":
        return str(pname or "")
    return re.sub(r"\s+", " ", str(pname)).strip()


def _is_real_lock(row) -> bool:
    """真实用户锁单（收紧口径）：锁单前有小订/预售支付记录（小订转大定），
    且排除内部测试单（buyer/owner_identity_no = 9999999）。
    order_type 不作为充分条件（DM2 等新车型 order_type 未填充；且上市前存在无小订的提前用户车锁单）。"""
    it = row.get("intention_payment_time")
    lt = row.get("lock_time")
    if not (pd.notna(it) and pd.notna(lt) and pd.Timestamp(it) <= pd.Timestamp(lt)):
        return False
    buyer = str(row.get("buyer_identity_no", "") or "").strip()
    owner = str(row.get("owner_identity_no", "") or "").strip()
    if buyer == "9999999" or owner == "9999999":
        return False
    return True


def resolve_launch_open_from_data(base: pd.DataFrame, key: str, launch: pd.Timestamp | None, use_data: bool = True) -> pd.Timestamp | None:
    """开放时刻。
    - use_data=True（目标系列）：上市日当天及之后第一个 real 锁单（小订转大定，排除测试单）时间；无则上市日 00:00。
    - use_data=False（历史对比代际）：上市日 20:00（已验证 DM1/CM2/LS9/LS8 的峰值爆发点）。"""
    if launch is None:
        return None
    launch_start = launch.normalize()
    if not use_data:
        return launch_start + pd.Timedelta(hours=OPEN_HOUR)
    real = base.loc[base["series_group_logic"].eq(key)].copy()
    real = real[real.apply(_is_real_lock, axis=1)]
    # 上市日当天及之后的 real 锁单
    real_on_launch = real[real["lock_time"] >= launch_start]
    if real_on_launch.empty:
        return launch_start
    return pd.Timestamp(real_on_launch["lock_time"].min())


def compute_launch_metrics(df: pd.DataFrame, business_def: dict, today: pd.Timestamp, series: str) -> dict:
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

    run_date = today.normalize()
    max_lock_time = df["lock_time"].max()
    as_of_date = run_date
    if pd.notna(max_lock_time):
        as_of_date = min(as_of_date, pd.Timestamp(max_lock_time).normalize())

    # 观察时间 = as-of 当日 23:59:59（观察截止时刻），同时受数据覆盖上限约束
    obs = as_of_date + pd.Timedelta(hours=23, minutes=59, seconds=59)
    if pd.notna(max_lock_time):
        obs = min(obs, pd.Timestamp(max_lock_time))

    time_periods = business_def.get("time_periods", {}) or {}
    launch = resolve_launch_date(time_periods, series)

    base = df.loc[
        df["lock_time"].notna(),
        ["order_number", "lock_time", "approve_refund_time", "owner_identity_no", "buyer_identity_no", "order_type", "series_group_logic", "intention_payment_time", "intention_refund_time", "deposit_refund_time", "deposit_payment_time", "product_name"],
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
        # 真实开放时刻：该代际第一个 real 锁单（用户车/小订转大定）
        open_t = resolve_launch_open_from_data(base, series, launch)

        obs_slice = base.loc[
            base["series_group_logic"].eq(series)
            & (base["lock_time"] >= open_t)
            & (base["lock_time"] <= obs),
            ["order_number", "lock_time", "approve_refund_time", "product_name"],
        ]
        # 上市至今累计：开放时刻至观察时间，锁单累计（不剔除退订）
        retention = int(obs_slice["order_number"].nunique())
        # 上市至今累计留存：累计中至今未退订（approve_refund_time 为空）
        kept_slice = obs_slice.loc[obs_slice["approve_refund_time"].isna()]
        retention_kept = int(kept_slice["order_number"].nunique())
        # 留存锁单分类：限定（JimmyChoo 高定限量版）/ 非限定，及分 product_name 明细
        retention_kept_limited = 0
        retention_kept_non_limited = 0
        retention_kept_by_product: list[dict] = []
        if not kept_slice.empty:
            kept_slice = kept_slice.assign(
                limited=kept_slice["product_name"].map(_is_limited),
                norm_name=kept_slice["product_name"].map(_norm_product_name),
            )
            retention_kept_limited = int(kept_slice.loc[kept_slice["limited"], "order_number"].nunique())
            retention_kept_non_limited = int(
                kept_slice.loc[~kept_slice["limited"], "order_number"].nunique()
            )
            # 按空格归一化后的 product_name 分组，合并同一产品的空格变体
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

        # 峰值小时：观察窗口内按小时统计
        if not obs_slice.empty:
            hourly = (
                obs_slice.assign(hour=obs_slice["lock_time"].dt.hour.astype("int64"))
                .groupby("hour")["order_number"]
                .nunique()
                .reindex(range(24), fill_value=0)
            )
            peak_hour = int(hourly.idxmax())
            peak_count = int(hourly.iloc[peak_hour])

        # 历史对比（精确到小时）：各代际自开放时刻（上市日 20:00）起算与目标相同的时长窗口
        # elapsed = 观察时间 − 目标开放时刻；与上市至今累计同口径，不剔除退订
        elapsed = (obs - open_t).total_seconds() / 3600.0 if obs > open_t else 0.0
        for cmp_key in COMPARE_KEYS:
            cmp_launch = resolve_launch_date(time_periods, cmp_key)
            cmp_open = resolve_launch_open_from_data(base, cmp_key, cmp_launch, use_data=False)
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

    # 锁单数：与上市至今累计同窗口，自开放时刻（20:00）起算至观察时间
    if open_t is not None:
        lock_mask = (
            base["series_group_logic"].eq(series)
            & (base["lock_time"] >= open_t)
            & (base["lock_time"] <= obs)
        )
    else:
        lock_mask = pd.Series(False, index=base.index)
    today_lock_count = int(base.loc[lock_mask, "order_number"].nunique())
    today_user_car_lock_count = int(
        base.loc[lock_mask & (base["order_type"].astype("string") == "用户车"), "order_number"].nunique()
    )
    # 小订转大定：锁单时间之前有预售订单支付记录（intention_payment_time <= lock_time），排除内部测试单；否则为直接锁单
    conv_mask = lock_mask & base["intention_payment_time"].notna() & (base["intention_payment_time"] <= base["lock_time"])
    today_intention_conv = int(base.loc[conv_mask & base.apply(_is_real_lock, axis=1), "order_number"].nunique())
    today_direct_lock = int(today_lock_count) - int(today_intention_conv)

    # 留存小订数：与 l6_m2_presale_metrics_to_feishu.py 对齐
    # = 预售开放时刻（start+20:00）起支付意向金、至今未退意向金的订单数（含已锁单转大定单）
    presale_retained = 0
    if launch is not None:
        tp_key = time_periods.get(series, {}) or {}
        if tp_key.get("start"):
            presale_open = pd.Timestamp(tp_key["start"]).normalize() + pd.Timedelta(hours=OPEN_HOUR)
            retained_mask = (
                df["series_group_logic"].eq(series)
                & df["intention_payment_time"].notna()
                & (df["intention_payment_time"] >= presale_open)
                & (df["intention_payment_time"] <= obs)
                & df["intention_refund_time"].isna()
            )
            presale_retained = int(df.loc[retained_mask, "order_number"].nunique())

    return {
        "series": series,
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


# ---------- 飞书卡片 ----------

def build_feishu_card(metrics: dict, show_notes: bool = True) -> dict:
    series = metrics["series"]
    peak_hour_str = f"{metrics['peak_hour']:02d}:00" if metrics["peak_hour"] is not None else "NA"

    lines = [f"**{series} 上市锁单监控（{metrics['as_of_date']}）**"]

    lines += ["", f"车型：**{series}**"]
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
        lines.append("口径：开放时刻起至观察时间的锁单累计（目标开放时刻 = 上市日当天首个转大定，无则上市日 00:00；排除测试单）；历史对比 = 各代际自上市日 20:00 起算相同时长")
        lines.append("数据源：dataset/order_data.parquet + shared/schema/business_definition.json")

    if metrics["as_of_date"] != metrics["run_date"]:
        lines.append(f"（数据未覆盖运行日 {metrics['run_date']}，锁单数以 {metrics['as_of_date']} 计）")

    body_md = "\n".join(lines)
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📈 {series} 上市锁单监控（{metrics['as_of_date']}）"},
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


def main() -> int:
    parser = argparse.ArgumentParser(description="读取 order_data.parquet 并发送车型上市锁单监控指标到飞书")
    parser.add_argument("--series", type=str, default=DEFAULT_SERIES,
                        help=f"要监控的车型（series_group_logic 键，默认 {DEFAULT_SERIES}）")
    parser.add_argument("--dry-run", action="store_true", help="只打印不发送飞书")
    parser.add_argument("--as-of", type=str, default=None, help="指定统计基准日 YYYY-MM-DD（默认今天）")
    args = parser.parse_args()

    if not _ORDER_DATA.exists():
        print(f"❌ 文件不存在: {_ORDER_DATA}")
        return 1

    business_def = load_business_definition(_BUSINESS_DEF)
    asts = {g: _parse_logic(_rule_condition(cond)) for g, cond in business_def.get("series_group_logic", {}).items()}

    series = args.series.strip()
    if series not in business_def.get("series_group_logic", {}):
        print(f"⚠️ 警告: 车型 '{series}' 不在 series_group_logic 中，但仍会继续执行。")
    if series not in business_def.get("time_periods", {}):
        print(f"⚠️ 警告: 车型 '{series}' 不在 time_periods 中，无法解析上市日。")

    print(f"📖 Loading: {_ORDER_DATA}")
    df = pd.read_parquet(_ORDER_DATA)
    if not pd.api.types.is_datetime64_any_dtype(df["lock_time"]):
        df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    if not pd.api.types.is_datetime64_any_dtype(df["approve_refund_time"]):
        df["approve_refund_time"] = pd.to_datetime(df["approve_refund_time"], errors="coerce")
    df = apply_series_group_logic(df, business_def, asts)

    today = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp(datetime.now().date())
    metrics = compute_launch_metrics(df, business_def, today, series)
    # dry-run 展示口径/数据源；推送时不展示
    card = build_feishu_card(metrics, show_notes=args.dry_run)

    if args.dry_run:
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return 0

    import os

    from dotenv import load_dotenv
    import requests

    load_dotenv()
    webhook_url = os.getenv("FS_WEBHOOK_URL")
    if not webhook_url:
        print("⚠️ 未设置 FS_WEBHOOK_URL，跳过发送")
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return 0

    try:
        resp = requests.post(webhook_url, json=card, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        code = result.get("StatusCode", result.get("code"))
        if code == 0:
            print("✅ 飞书消息发送成功")
            return 0
        print(f"❌ 飞书返回异常: {result}")
        return 1
    except Exception as e:
        print(f"❌ 发送飞书消息失败: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
