#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
观星台集团订单日报 — 车型订单查询脚本

按快照（日期）查询集团重点车型的订单数/成交数，复用 saic_group_order_daily_parse.parse_sheet 的布局解析。

用法:
  # 指定单个快照文件 + 车型
  python research_scripts/saic_group_order_query.py \
      --file /path/订单日报2.0-0823.xlsx --models "MG 07,至境L7 BEV,大众ID.ERA 5S"

  # 按 as-of 日期从目录自动匹配快照
  python research_scripts/saic_group_order_query.py \
      --dir /path/saic观星台集团订单日报 --as-of 2026-08-23 --models "MG 07"

  # 查看某个快照全部车型 / 目录内可用快照
  python research_scripts/saic_group_order_query.py --file <xlsx> --list-models
  python research_scripts/saic_group_order_query.py --dir <目录> --list-snapshots

  # 成交口径 + JSON 输出
  python research_scripts/saic_group_order_query.py --file <xlsx> --models "MG 07" --metric invoice --format json

字段口径（以 0823 快照为例）:
  - 月度累计/月日均  = 报表月(7月)全月累计与日均
  - 下月累计/下月日均 = 快照所在月(8月)累计与日均，即「截止快照日的当月订单数」
  - 周度日均 = 近4周(7月W5~8月W3)周度日均
  - 每日 = 近9日每日订单
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
for p in (str(_REPO_ROOT), str(_WS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from research_scripts.saic_group_order_daily_parse import parse_sheet

DEFAULT_GX_DIR = Path("/Users/zihao_/Documents/coding/dataset/original/saic观星台集团订单日报")
SHEET_BY_METRIC = {"order": "重点车型 (订单)", "invoice": "重点车型 (成交)"}
LABEL_BY_METRIC = {"order": "国内订单", "invoice": "成交(开票)"}

FLOAT_FIELDS = {"月度累计", "月日均", "下月累计", "下月日均"}
DEFAULT_OUTPUT = _WS / "outputs" / "tables"


def _fmt(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    if isinstance(v, float) and abs(v - round(v)) < 1e-6:
        return f"{int(v):,}"
    if isinstance(v, (int, float)):
        return f"{v:,.1f}"
    return str(v)


def load_snapshot(path: Path, metric: str) -> pd.DataFrame:
    xl = pd.ExcelFile(str(path))
    raw = xl.parse(SHEET_BY_METRIC[metric], header=None)
    return parse_sheet(raw, filepath=path)  # type: ignore[arg-type]


def list_snapshots(directory: Path) -> list[str]:
    dates = []
    for p in sorted(directory.glob("订单日报*.xlsx")):
        try:
            df = load_snapshot(p, "order")
            if not df.empty and "数据日期" in df.columns:
                dates.append(str(df["数据日期"].iloc[0]))
        except Exception:
            continue
    return dates


def resolve_snapshot(directory: Path, as_of: str) -> Path | None:
    target = as_of.replace("-", "")
    for p in sorted(directory.glob("订单日报*.xlsx")):
        try:
            df = load_snapshot(p, "order")
            if not df.empty and "数据日期" in df.columns:
                if str(df["数据日期"].iloc[0]).replace("-", "") == target:
                    return p
        except Exception:
            continue
    return None


def _norm(s) -> str:
    return re.sub(r"\s+", "", str(s))


def query(df: pd.DataFrame, models: list[str] | None) -> list[dict]:
    weekly_cols = [c for c in df.columns if c.startswith("周度") or re.match(r"^.{2,}\(\d+~\d+\)$", c)]
    daily_cols = [c for c in df.columns if c.startswith("每日_")]
    week_keys = [c.split("(")[0] for c in weekly_cols]

    if models:
        norm_models = {_norm(m) for m in models}
    else:
        norm_models = None

    rows = []
    for _, r in df.iterrows():
        name = str(r["主体"]).strip()
        if norm_models is not None and _norm(name) not in norm_models:
            continue
        week = {k: _fmt(r[c]) for k, c in zip(week_keys, weekly_cols)}
        daily = {}
        for c in daily_cols:
            md = c.split("_")[1]
            daily[md] = _fmt(r[c])
        rows.append({
            "model": name,
            "monthly_cum": _fmt(r["月度累计"]),
            "monthly_avg": _fmt(r["月日均"]),
            "next_month_cum": _fmt(r.get("下月累计")),
            "next_month_avg": _fmt(r.get("下月日均")),
            "weekly": week,
            "daily": daily,
            "yoy": _fmt(r.get("同比")),
            "mom": _fmt(r.get("环比")),
        })
    return rows


def render_terminal(path: Path, metric: str, snapshot_date: str | None, rows: list[dict]) -> None:
    print(f"快照: {path.name} · 数据日期: {snapshot_date or '—'} · 口径: {LABEL_BY_METRIC[metric]}")
    print("=" * 70)
    if not rows:
        print("（无匹配车型）")
        return
    for r in rows:
        print(f"[{r['model']}]")
        print(f"  本月累计: {r['monthly_cum']:<12} 本月日均: {r['monthly_avg']}")
        print(f"  下月累计(截止快照日): {r['next_month_cum']:<12} 下月日均: {r['next_month_avg']}")
        if r["weekly"]:
            w = "  ".join(f"{k}={v}" for k, v in r["weekly"].items())
            print(f"  周度日均: {w}")
        if r["daily"]:
            d = "  ".join(f"{k}={v}" for k, v in r["daily"].items())
            print(f"  每日近{len(r['daily'])}日: {d}")
        print("-" * 70)


def main() -> int:
    p = argparse.ArgumentParser(description="观星台集团订单日报 — 车型订单查询")
    p.add_argument("--file", type=str, help="单个订单日报 xlsx 快照文件")
    p.add_argument("--dir", type=str, default=str(DEFAULT_GX_DIR), help="观星台订单日报目录")
    p.add_argument("--as-of", type=str, help="按数据日期匹配快照 (YYYY-MM-DD)")
    p.add_argument("--models", type=str, default="", help="车型过滤，逗号分隔（默认全部）")
    p.add_argument("--metric", type=str, default="order", choices=["order", "invoice"], help="order=订单 / invoice=成交")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    p.add_argument("--output", type=str, help="JSON 输出目录")
    p.add_argument("--list-models", action="store_true", help="列出快照内全部车型")
    p.add_argument("--list-snapshots", action="store_true", help="列出目录内可用快照日期")
    args = p.parse_args()

    if args.list_snapshots:
        dates = list_snapshots(Path(args.dir))
        for d in dates:
            print(d)
        return 0

    if args.file:
        path = Path(args.file)
    elif args.as_of:
        path = resolve_snapshot(Path(args.dir), args.as_of)
        if path is None:
            print(f"❌ 目录 {args.dir} 中未找到 {args.as_of} 对应快照（可用: {list_snapshots(Path(args.dir))}）")
            return 1
    else:
        p.print_help()
        return 1

    if not path.exists():
        print(f"❌ 快照文件不存在: {path}")
        return 1

    df = load_snapshot(path, args.metric)
    if args.list_models:
        for m in sorted(df["主体"].dropna().astype(str).str.strip().unique()):
            print(m)
        return 0

    models = [m.strip() for m in args.models.split(",") if m.strip()] if args.models else None
    rows = query(df, models)
    snapshot_date = str(df["数据日期"].iloc[0]) if "数据日期" in df.columns and not df.empty else None

    if args.format == "json":
        contract = {
            "status": "success",
            "script": "research_scripts/saic_group_order_query.py",
            "scope": {
                "data_source": str(path),
                "snapshot_date": snapshot_date,
                "metric": LABEL_BY_METRIC[args.metric],
                "models": models,
            },
            "result": {"models": rows},
        }
        if args.output:
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / f"group_order_{path.stem}.json"
            out.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"已输出: {out}")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        render_terminal(path, args.metric, snapshot_date, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
