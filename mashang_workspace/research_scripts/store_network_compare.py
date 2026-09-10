#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
有效门店 × 经销商网络对比（上市同期窗口，多代际）

对比任意两代际（默认 DM1 vs DM2）在各自上市同期窗口内的「有效门店 × 经销商」
网络规模，按大区（订单侧 parent_region_name，旧架构归一到新架构）分组。

口径：
  - 有效门店 = 上市同期第 1..N 天窗口内真实发生锁单的订单侧门店
    （order_data.store_name，零售口径，不依赖 store_info 停业/暂停/在建状态猜测）
  - 经销商（Bloc）= 有效门店经 shared.loaders.store_info_loader.resolve_dealer_info
    关联到的经销商集团
  - 大区 = order_data.parent_region_name，旧架构（一区/二区/三区-*）经
    utils.regions.norm_region 归一到新架构（东区/西区/北区/华中）
  - 口径与 assign"下发门店"口径量级一致（如 DM2 近 30 日下发门店日均 ≈ 有效门店数）

用法：
  python research_scripts/store_network_compare.py
  python research_scripts/store_network_compare.py --gens DM1 DM2 --as-of 2026-09-06
  python research_scripts/store_network_compare.py --n-days 30
  python research_scripts/store_network_compare.py --format json --output outputs/tables/
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS = REPO_ROOT / "mashang_workspace"
for p in (str(REPO_ROOT), str(_WS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from utils.monitors.phase import load_business_definition  # noqa: E402
from utils.monitors.series_group import apply_series_group_logic  # noqa: E402
from shared.loaders import store_info_loader  # noqa: E402
from utils.regions import norm_region  # noqa: E402

_BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
_ORDER_DATA = REPO_ROOT / "dataset" / "order_data.parquet"
_DEFAULT_TABLE = _WS / "outputs" / "tables"

DEFAULT_GENS = ["DM1", "DM2"]
NON_RETAIL = {"试驾车", "大客户", "员工", "集团员工", "经销商员工", "享道", "仅批售", "项目", "展车", "海外"}


def _retail_mask(order_type: pd.Series) -> pd.Series:
    ot = order_type.fillna("").astype("string")
    return ot.isin(["", "用户车"]) & ~ot.isin(NON_RETAIL)


def resolve_end_day(bd: dict, gen: str) -> pd.Timestamp:
    tp = (bd.get("time_periods", {}) or {}).get(gen, {}) or {}
    return pd.Timestamp(tp["end"]).normalize()


def load_data() -> tuple[pd.DataFrame, dict]:
    """加载 order_data + 应用 series_group_logic，返回 (df, business_def)。"""
    bd = load_business_definition(_BUSINESS_DEF)
    df = pd.read_parquet(_ORDER_DATA)
    for c in ["lock_time", "intention_payment_time", "delivery_date"]:
        if c in df.columns and not pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = pd.to_datetime(df[c], errors="coerce")
    df = apply_series_group_logic(df, bd)
    return df, bd


def compute_store_network(df: pd.DataFrame, gens: list[str], ends: dict,
                          n_days: int) -> dict | None:
    """上市同期窗口的「有效门店 × 经销商」网络对比（活动口径，见模块 docstring）。

    df 须已过滤为零售口径且已带 series_group_logic 列。
    返回 dict（含 rows / total_* / store_metric），供终端、Result Contract 与报告复用。
    """
    if len(gens) < 2:
        return None
    gen_a, gen_b = gens[-2], gens[-1]

    def _active(t: pd.Timestamp) -> pd.DataFrame:
        lo, hi = t, t + pd.Timedelta(days=n_days)
        m = df[df["lock_time"].notna() &
               (df["lock_time"] >= lo) & (df["lock_time"] < hi) &
               df["store_name"].notna()]
        return m[["store_name", "parent_region_name"]].copy()

    dealer_cache: dict = {}
    by_gen: dict[str, dict] = {}
    for key, g in (("a", gen_a), ("b", gen_b)):
        act = _active(ends[g])
        cur: dict[str, set] = {"_stores": set(), "_blocs": set()}
        for sn, reg in act[["store_name", "parent_region_name"]].itertuples(index=False):
            if sn not in dealer_cache:
                dealer_cache[sn] = store_info_loader.resolve_dealer_info(sn)
            info = dealer_cache[sn]
            r = norm_region(reg)
            cur.setdefault(r, {"stores": set(), "blocs": set()})
            cur[r]["stores"].add(sn)
            if r not in ("未知", "虚拟大区"):
                cur["_stores"].add(sn)
            if info and info.get("bloc_name"):
                cur.setdefault(r, {"stores": set(), "blocs": set()})
                cur[r]["blocs"].add(info["bloc_name"])
                cur["_blocs"].add(info["bloc_name"])
        by_gen[key] = cur

    def _regions(key: str) -> set:
        return {r for r in by_gen[key] if not r.startswith("_")}

    regions = sorted(_regions("a") | _regions("b"),
                     key=lambda r: -len(by_gen["b"].get(r, {}).get("stores", set())))
    rows = []
    for r in regions:
        ra = by_gen["a"].get(r, {"stores": set(), "blocs": set()})
        rb = by_gen["b"].get(r, {"stores": set(), "blocs": set()})
        rows.append({
            "region": r,
            "a_stores": len(ra["stores"]), "a_blocs": len(ra["blocs"]),
            "b_stores": len(rb["stores"]), "b_blocs": len(rb["blocs"]),
        })
    return {
        "gen_a": gen_a, "gen_b": gen_b, "n_days": n_days,
        "rows": rows,
        "total_a_stores": len(by_gen["a"]["_stores"]),
        "total_a_blocs": len(by_gen["a"]["_blocs"]),
        "total_b_stores": len(by_gen["b"]["_stores"]),
        "total_b_blocs": len(by_gen["b"]["_blocs"]),
        "store_metric": "active_lock_store",
    }


def _resolve_window(df: pd.DataFrame, bd: dict, gens: list[str],
                    as_of: pd.Timestamp) -> tuple[dict, pd.Timestamp, int]:
    """按业务定义 + as-of 推导各代际上市日与上市同期窗口天数 N（与报告脚本口径一致）。"""
    ends = {g: resolve_end_day(bd, g) for g in gens}
    max_end = max(ends.values())
    max_lock = pd.to_datetime(df["lock_time"], errors="coerce").max()
    if pd.notna(max_lock):
        as_of = min(as_of, pd.Timestamp(max_lock).normalize())
    last_date = as_of.normalize() - pd.Timedelta(days=1)
    n_days = max(1, int((last_date - max_end).days) + 1)
    return ends, as_of, n_days


def render_terminal(data: dict) -> None:
    if not data:
        print("（代际不足 2，跳过网络对比）")
        return
    a, b = data["gen_a"], data["gen_b"]
    print(f"有效门店 × 经销商网络对比：{b} vs {a}（上市同期 {data['n_days']} 天窗口，活动口径）")
    hdr = (f"{'大区':<12}{a + '门店':>8}{a + '经销商':>10}"
           f"{b + '门店':>8}{b + '经销商':>10}")
    print(hdr)
    for r in data["rows"]:
        print(f"{r['region']:<12}{r['a_stores']:>8}{r['a_blocs']:>10}"
              f"{r['b_stores']:>8}{r['b_blocs']:>10}")
    print(f"{'合计':<12}{data['total_a_stores']:>8}{data['total_a_blocs']:>10}"
          f"{data['total_b_stores']:>8}{data['total_b_blocs']:>10}")


def build_contract(data: dict, args: argparse.Namespace, as_of: str) -> dict:
    """构建 Result Contract（复用 utils/result_contract）。"""
    from utils.result_contract import build_success_contract

    rows = data["rows"]
    tables = [{
        "name": "store_network_compare",
        "columns": ["region", "a_stores", "a_blocs", "b_stores", "b_blocs"],
        "rows": rows,
    }]
    dimensions = [{
        "name": "region",
        "items": [{"value": r["region"],
                   "metrics": {"a_stores": r["a_stores"], "a_blocs": r["a_blocs"],
                               "b_stores": r["b_stores"], "b_blocs": r["b_blocs"]}}
                  for r in rows],
    }]
    scope = {
        "data_source": "dataset/order_data.parquet + shared/loaders/store_info_loader.py",
        "time_window": {"type": "since_launch", "n_days": data["n_days"],
                        "gens": [data["gen_a"], data["gen_b"]]},
        "filters": {"order_type": "用户车/NaN（零售口径）",
                    "region_map": "旧架构归一到新架构（utils/regions.py）"},
        "metric_definition": "有效门店 = 上市同期第 1..N 天窗口内有锁单的订单侧门店；"
                             "经销商 = 有效门店关联的 Bloc；大区 = parent_region_name 归一",
    }
    result = {
        "summary": f"{data['gen_b']} 有效门店 {data['total_b_stores']} 家 / 经销商 "
                   f"{data['total_b_blocs']} 家，{data['gen_a']} {data['total_a_stores']} 家 / "
                   f"{data['total_a_blocs']} 家（上市同期 {data['n_days']} 天窗口）",
        "metrics": {
            "a_stores": data["total_a_stores"], "a_blocs": data["total_a_blocs"],
            "b_stores": data["total_b_stores"], "b_blocs": data["total_b_blocs"],
            "store_metric": data["store_metric"],
        },
        "dimensions": dimensions,
        "tables": tables,
    }
    followup_context = {"metric": "active_store_network",
                        "gens": [data["gen_a"], data["gen_b"]],
                        "available_dimensions": ["region", "dealer_bloc", "store"]}
    return build_success_contract(
        script="research_scripts/store_network_compare.py",
        command=" ".join(["python", "research_scripts/store_network_compare.py"] + _render_cli(args)),
        scope=scope, result=result, followup_context=followup_context,
    )


def _render_cli(args: argparse.Namespace) -> list[str]:
    parts = []
    if getattr(args, "gens", None):
        parts += ["--gens"] + args.gens
    if getattr(args, "as_of", None):
        parts += ["--as-of", args.as_of]
    if getattr(args, "n_days", None):
        parts += ["--n-days", str(args.n_days)]
    parts += ["--format", args.format]
    return parts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="有效门店 × 经销商网络对比（上市同期窗口，多代际）")
    p.add_argument("--gens", type=str, nargs="*", default=DEFAULT_GENS,
                   help="代际（默认 DM1 DM2；取最近两代际做对比，需按上市先后传入）")
    p.add_argument("--as-of", type=str, default=None, help="统计基准日 YYYY-MM-DD（默认今天）")
    p.add_argument("--n-days", type=int, default=None,
                   help="上市同期窗口天数 N（默认 = 基准日-1 距最新代际上市日天数）")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    p.add_argument("--output", type=str, default=None, help="JSON 输出目录（仅 --format json）")
    args = p.parse_args(argv)

    if not _ORDER_DATA.exists():
        print(f"❌ 文件不存在: {_ORDER_DATA}")
        return 1

    df, bd = load_data()
    as_of = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp(datetime.now().date())
    ends, as_of, n_days = _resolve_window(df, bd, args.gens, as_of)
    if args.n_days:
        n_days = args.n_days
    retail = df[_retail_mask(df["order_type"])].copy()
    data = compute_store_network(retail, args.gens, ends, n_days)
    if not data:
        print("❌ 需至少两个代际")
        return 1

    if args.format == "terminal":
        render_terminal(data)
        return 0

    contract = build_contract(data, args, as_of.date().isoformat())
    out_dir = Path(args.output) if args.output else _DEFAULT_TABLE
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"store_network_compare_{'_'.join(args.gens)}.json"
    out.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已输出: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
