#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
读取 order_data.parquet，按 business_definition.json 的口径计算智己 L6 M2（DM2）预售小订监控指标，
并通过飞书自定义机器人 Webhook 发送交互式卡片。

卡片内容：
  - 核心指标：L6 M2（DM2）当前累计小订数
  - 峰值分析：预售首日峰值小时小订数、峰值后 1h、预售当日累计
  - 累计：预售至今累计留存（未退意向金）、累计留存唯一订单用户数
  - 对标：DM1 / CM2 / LS9 / LS8 在相同 N 日窗口的留存（N = 当前日期 - DM2 start + 1）
  - 细分：累计留存分 product_name、分 parent_region_name（含门店 CR5）
  - 附注：预售期起止、N（日）定义、统计时间

口径依据：shared/schema/business_definition.json
  - series_group_logic.DM2：product_name 含 M2 / Jimmy Choo / JimmyChoo
  - time_periods.DM2：start=预售起点, end=预售结束日
  - 对标代际 time_periods.{DM1,CM2,LS9,LS8}.start

用法：
  python mashang_workspace/research_scripts/l6_m2_presale_metrics_to_feishu.py            # 计算并发送飞书
  python mashang_workspace/research_scripts/l6_m2_presale_metrics_to_feishu.py --dry-run  # 只打印卡片
  python mashang_workspace/research_scripts/l6_m2_presale_metrics_to_feishu.py --as-of 2026-08-18  # 指定基准日
"""

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

SERIES = "DM2"
SERIES_LABEL = "L6 M2"
COMPARE_KEYS = ["DM1", "CM2", "LS9", "LS8"]
DEFAULT_GROUP = "其他"


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


def _apply_series_group_logic(df: pd.DataFrame, business_def: dict, asts: dict) -> pd.DataFrame:
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

def compute_presale_metrics(df: pd.DataFrame, business_def: dict, today: pd.Timestamp) -> dict:
    time_periods: dict = business_def.get("time_periods", {})
    tp = time_periods.get(SERIES, {}) or {}
    start = pd.Timestamp(tp["start"]) if tp.get("start") else None
    end = pd.Timestamp(tp["end"]) if tp.get("end") else None

    n_raw = int((today.normalize() - start.normalize()).days + 1) if start is not None else 1
    n = max(1, n_raw)

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
        "today": today.date().isoformat(),
        "series_start": start.date().isoformat() if start is not None else None,
        "series_end": end.date().isoformat() if end is not None else None,
        "n": n,
        "n_raw": n_raw,
        "cum": 0,
        "retention": 0,
        "retention_users": 0,
        "peak_hour": None,
        "peak_count": 0,
        "next_hour_count": 0,
        "start_day_total": 0,
        "n_day_cum": 0,
        "retention_by_product": [],
        "retention_by_region": [],
        "compare": {},
    }

    if start is None:
        return metrics

    current_mask = (
        base["series_group_logic"].eq(SERIES)
        & (base["intention_payment_time"] >= start)
        & (base["intention_payment_time"] < (today + pd.Timedelta(days=1)))
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
                {"product_name": p, "count": int(c), "share": round(c / metrics["retention"] * 100, 1)}
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

    start_excl = start + pd.Timedelta(days=1)
    day_slice = base.loc[
        base["series_group_logic"].eq(SERIES)
        & (base["intention_payment_time"] >= start)
        & (base["intention_payment_time"] < start_excl),
        ["order_number", "intention_payment_time"],
    ].copy()
    if not day_slice.empty:
        day_slice["hour"] = day_slice["intention_payment_time"].dt.hour.astype("int64")
        hourly = day_slice.groupby("hour")["order_number"].nunique().reindex(range(24), fill_value=0)
        peak_hour = int(hourly.idxmax())
        metrics["peak_hour"] = peak_hour
        metrics["peak_count"] = int(hourly.iloc[peak_hour])
        metrics["next_hour_count"] = int(hourly.iloc[peak_hour + 1]) if peak_hour < 23 else 0
        metrics["start_day_total"] = int(hourly.sum())

    if end is not None:
        window_end_excl = min(start + pd.Timedelta(days=n), end + pd.Timedelta(days=1))
    else:
        window_end_excl = start + pd.Timedelta(days=n)
    metrics["n_day_cum"] = int(
        base.loc[
            base["series_group_logic"].eq(SERIES)
            & (base["intention_payment_time"] >= start)
            & (base["intention_payment_time"] < window_end_excl),
            "order_number",
        ].nunique()
    )

    for cmp_key in COMPARE_KEYS:
        cmp_tp = time_periods.get(cmp_key, {}) or {}
        if not cmp_tp.get("start"):
            metrics["compare"][cmp_key] = None
            continue
        cmp_start = pd.to_datetime(cmp_tp["start"])
        cmp_window_end = cmp_start + pd.Timedelta(days=n)
        cmp_slice = base.loc[
            base["series_group_logic"].eq(cmp_key)
            & (base["intention_payment_time"] >= cmp_start)
            & (base["intention_payment_time"] < cmp_window_end)
            & ((base["intention_refund_time"] > cmp_window_end) | base["intention_refund_time"].isna()),
            "order_number",
        ]
        metrics["compare"][cmp_key] = int(cmp_slice.nunique())

    return metrics


# ---------- 飞书卡片 ----------

def _section(title: str) -> list:
    return ["", f"**{title}**"]


def build_feishu_card(metrics: dict) -> dict:
    peak_hour_str = f"{metrics['peak_hour']:02d}:00" if metrics["peak_hour"] is not None else "NA"

    lines = [f"**{SERIES_LABEL} 预售指标（{metrics['today']}）**"]

    lines += _section("① 核心指标")
    lines.append(f"当前累计小订数：{metrics['cum']}")
    lines.append(f"累计留存订单数：{metrics['retention']}")
    lines.append(f"累计留存唯一订单用户数：{metrics['retention_users']}")

    lines += _section("② 峰值分析")
    lines.append(f"峰值小时小订数：{metrics['peak_count']}（{peak_hour_str}）")
    lines.append(f"峰值后 1h：{metrics['next_hour_count']}")
    lines.append(f"预售当日累计：{metrics['start_day_total']}")

    lines += _section("③ 累计")
    lines.append(f"预售至今累计留存：{metrics['retention']}")
    lines.append(f"预售至 N 日累计小订：{metrics['n_day_cum']}")

    compare_str = "｜".join(
        f"{k}（{v}）" if v is not None else f"{k}（无数据）" for k, v in metrics["compare"].items()
    )
    lines += _section("④ 对标（同 N 日窗口留存）")
    lines.append(compare_str)

    lines += _section("⑤ 细分")
    if metrics.get("retention_by_product"):
        lines.append("**分 product_name：**")
        for item in metrics["retention_by_product"]:
            lines.append(f"  - {item['product_name']}：{item['count']}（{item['share']}%）")
    else:
        lines.append("分 product_name：暂无留存订单")

    if metrics.get("retention_by_region"):
        lines.append("**分 parent_region_name：**")
        for item in metrics["retention_by_region"]:
            cr5_str = f"｜CR5（{item['cr5']}%）" if item.get("cr5") is not None else ""
            lines.append(f"  - {item['region_name']}：{item['count']}（{item['share']}%）{cr5_str}")
    else:
        lines.append("分 parent_region_name：暂无留存订单")

    lines += _section("⑥ 附注")
    if metrics.get("series_start") and metrics.get("series_end"):
        lines.append(f"预售期：{metrics['series_start']} ~ {metrics['series_end']}")
    lines.append(f"N（日）= 当前日期 - {SERIES} startday + 1 = {metrics['n']}")
    lines.append("对标口径：历史代际预售起同样 N 日窗口内，意向金未退的唯一订单数（退订晚于窗口末视为留存）")
    lines.append("数据源：dataset/order_data.parquet + shared/schema/business_definition.json")

    body_md = "\n".join(lines)
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📊 {SERIES_LABEL} 预售小订监控（{metrics['today']}）"},
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
    parser = argparse.ArgumentParser(description=f"读取 order_data.parquet 并发送 {SERIES_LABEL} 预售小订监控指标到飞书")
    parser.add_argument("--dry-run", action="store_true", help="只打印不发送飞书")
    parser.add_argument("--as-of", type=str, default=None, help="指定统计基准日 YYYY-MM-DD（默认今天）")
    args = parser.parse_args()

    if not _ORDER_DATA.exists():
        print(f"❌ 文件不存在: {_ORDER_DATA}")
        return 1

    business_def = load_business_definition(_BUSINESS_DEF)
    asts = {g: _parse_logic(_rule_condition(cond)) for g, cond in business_def.get("series_group_logic", {}).items()}

    print(f"📖 Loading: {_ORDER_DATA}")
    df = pd.read_parquet(_ORDER_DATA)
    if not pd.api.types.is_datetime64_any_dtype(df["intention_payment_time"]):
        df["intention_payment_time"] = pd.to_datetime(df["intention_payment_time"], errors="coerce")
    if not pd.api.types.is_datetime64_any_dtype(df["intention_refund_time"]):
        df["intention_refund_time"] = pd.to_datetime(df["intention_refund_time"], errors="coerce")
    df = _apply_series_group_logic(df, business_def, asts)

    today = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp(datetime.now().date())
    metrics = compute_presale_metrics(df, business_def, today)
    card = build_feishu_card(metrics)

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