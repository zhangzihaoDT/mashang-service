#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智己历次预售表现对比集团重点车型的计算脚本

将智己各代际（CM0/CM1/CM2/DM0/DM1/LS8/LS9）预售后 N 天的小订曲线，
与集团重点车型（订单日报2.0 中的预售期小订车型，如 MG 07）做对齐对比。

预售起点判定规则：
  - 集团重点车型：预售小订从 0 突变为 >0 的首日（0→>0 突变）
  - 智己各代际：business_definition.json 的 time_periods.{series}.start

输出：
  - 每个预售小订车型一个 CSV：outputs/tables/预售小订_N天对比_{车型}_vs_智己各代际.csv
    表格为每日行（N=0..k）+ 末尾累计行，k = 该车型预售起至数据窗口末的天数

用法：
  python mashang_workspace/research_scripts/presale_performance_compare.py
  python mashang_workspace/research_scripts/presale_performance_compare.py \
      --order-csv mashang_workspace/outputs/tables/重点车型（订单）.csv \
      --output mashang_workspace/outputs/tables/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WS = _REPO_ROOT / "mashang_workspace"
_DEFAULT_ORDER_CSV = _WS / "outputs" / "tables" / "重点车型（订单）.csv"
_DEFAULT_OUTPUT = _WS / "outputs" / "tables"
_DEFAULT_DATA = _REPO_ROOT / "dataset" / "order_data.parquet"
_BUSINESS_DEF = _REPO_ROOT / "shared" / "schema" / "business_definition.json"

PRESALE_SECTION_LABEL = "预售期小订"
GROUP_KEYS = ["CM0", "CM1", "CM2", "DM0", "DM1", "LS8", "LS9"]


# ---------- product_name LIKE 表达式求值（复用观察脚本解析器） ----------

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
    tokens = []
    i, n = 0, len(expr)
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


def _sg_condition(rule) -> str:
    """series_group_logic 规则解包：兼容旧字符串格式与新的 {priority, condition} 对象格式。"""
    if isinstance(rule, dict):
        return str(rule.get("condition", ""))
    return str(rule)


# ---------- 预售小订车型检测 ----------

def detect_presale_models(order_df: pd.DataFrame) -> list[dict]:
    """识别订单日报中的预售期小订车型，并用 0→>0 规则检测预售起点。

    返回 [{model, start_date, daily:{N: 小订数}}]，start_date 为 None 表示窗口内无突变。
    """
    daily_cols = [c for c in order_df.columns if c.startswith("每日")]
    date_cols = [c.split("_")[1] for c in daily_cols]

    section_idx = None
    for i, name in enumerate(order_df["主体"]):
        if str(name).strip() == PRESALE_SECTION_LABEL:
            section_idx = i
            break
    if section_idx is None:
        return []

    models = []
    for _, row in order_df.iloc[section_idx + 1 :].iterrows():
        name = str(row["主体"]).strip()
        if not name or pd.isna(row[daily_cols[0]] if len(daily_cols) else None):
            if pd.isna(row.get("月度累计")) and pd.isna(row.get("月日均")):
                continue
        vals = [float(v) if pd.notna(v) else float("nan") for v in row[daily_cols]]

        start_idx = None
        prev = None
        for i, v in enumerate(vals):
            if prev is not None and prev == 0 and not pd.isna(v) and v > 0:
                start_idx = i
                break
            prev = v

        if start_idx is None:
            models.append({"model": name, "start_date": None, "daily": {}})
            continue

        start_date = date_cols[start_idx]
        daily = {n: vals[start_idx + n] for n in range(len(vals) - start_idx)}
        models.append({"model": name, "start_date": start_date, "daily": daily})

    return models


# ---------- 智己各代际曲线 ----------

def compute_zhiji_curves(order_data: pd.DataFrame, business_def: dict) -> dict[str, dict[int, int]]:
    """按 series_group_logic 归类智己各代际，对齐 time_periods.start 计算每日小订。"""
    sg = business_def["series_group_logic"]
    tp = business_def["time_periods"]
    asts = {g: _parse_logic(_sg_condition(sg[g])) for g in GROUP_KEYS}

    df = order_data.copy()
    df["intention_payment_time"] = pd.to_datetime(df["intention_payment_time"], errors="coerce")
    df["intention_date"] = df["intention_payment_time"].dt.date
    it = df[df["intention_date"].notna()]

    curves = {}
    for g in GROUP_KEYS:
        if g not in sg or g not in tp or not tp[g].get("start"):
            continue
        sub = it[it["product_name"].map(lambda p: _eval_ast(asts[g], p))]
        d0 = pd.Timestamp(tp[g]["start"]).date()
        sub = sub[sub["intention_date"] >= d0]
        days = (sub["intention_date"] - d0).apply(lambda x: x.days)
        curves[g] = sub.groupby(days)["order_number"].nunique().to_dict()
    return curves


# ---------- 入口 ----------

def main() -> int:
    parser = argparse.ArgumentParser(description="智历次预售表现对比集团重点车型")
    parser.add_argument("--order-csv", type=str, default=str(_DEFAULT_ORDER_CSV), help="重点车型（订单）.csv 路径")
    parser.add_argument("--output", type=str, default=str(_DEFAULT_OUTPUT), help="CSV 输出目录")
    parser.add_argument("--data", type=str, default=str(_DEFAULT_DATA), help="order_data.parquet 路径")
    args = parser.parse_args()

    order_csv = Path(args.order_csv)
    if not order_csv.exists():
        print(f"❌ 订单 CSV 不存在: {order_csv}")
        return 1
    order_df = pd.read_csv(str(order_csv))

    if not Path(args.data).exists():
        print(f"❌ 数据不存在: {args.data}")
        return 1
    order_data = pd.read_parquet(str(args.data))

    with open(_BUSINESS_DEF, encoding="utf-8") as f:
        business_def = json.load(f)

    presale_models = detect_presale_models(order_df)
    if not presale_models:
        print(f"❌ 未在订单 CSV 中找到「{PRESALE_SECTION_LABEL}」分区")
        return 1

    zhiji_curves = compute_zhiji_curves(order_data, business_def)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    print("=" * 70)
    print("智己历次预售表现 vs 集团重点车型（预售小订 N 天对比）")
    print("=" * 70)

    for m in presale_models:
        if m["start_date"] is None:
            print(f"\n[{m['model']}] 窗口内无 0→>0 突变，无法确定预售起点，跳过")
            continue
        n_max = max(m["daily"].keys()) + 1
        print(f"\n[{m['model']}] 预售起点 {m['start_date']}，N=0..{n_max - 1}（{n_max} 天）")

        cols = ["N", m["model"]] + GROUP_KEYS
        rows = []
        for n in range(n_max):
            rows.append([n, int(m["daily"].get(n, 0))] + [zhiji_curves.get(g, {}).get(n, 0) for g in GROUP_KEYS])
        rows.append(["累计", int(sum(m["daily"].values()))] + [sum(zhiji_curves.get(g, {}).get(k, 0) for k in range(n_max)) for g in GROUP_KEYS])
        table = pd.DataFrame(rows, columns=cols)

        fname = f"预售小订_N天对比_{m['model']}_vs_智己各代际.csv"
        out_path = out_dir / fname
        table.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(table.to_string(index=False))
        print(f"  → {out_path}")

    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
