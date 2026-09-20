#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
门店经营状况观察（全门店）

输出每家门店的：门店类型 / 近 N 日下发线索 / 近 N 日锁单 / CM3 留存小订 / 小订÷线索 比值。

口径:
  - 门店类型（运营）: 取「主理在岗统计」(dataset/门店日报_主理_当月.csv) 的 门店类型
    （车城店/商超店/独立慢闪店/城市空间/短期体验中心）
  - 门店形态（我们的 schema）: 取该表 门店编码(Dealer Code) 前缀经 store_info_loader
    .get_store_format 派生（如 IMP/IME=快闪/慢闪）；无编码时仅按 store_info 门店全名**精确**匹配，
    仍无则记「未知」（不做子串猜测）
  - 近 N 日下发线索: dataset/门店下发线索数.csv（增量库）窗口求和
  - 近 N 日锁单: order_data.parquet，lock_time ∈ 窗口（全部车系）
  - CM3 留存小订: order_data.parquet，series_group=CM3 且意向金时间 ∈ [CM3预售开放, 截止) 且未退意向金
  - 小订/线索 = CM3 留存小订 ÷ 近 N 日下发线索
  - 默认只保留「有下发线索 或 有锁单」的门店；--include-relations 额外纳入无数据快闪/慢闪
    popup（仅标关联车城店，不重复计数值）
  - 覆盖全门店 = 线索库 ∪ CM3 订单 ∪ 主理在岗统计 门店并集

用法:
    python utility_scripts/store_operation_observation.py                      # 终端 top20
    python utility_scripts/store_operation_observation.py --format csv         # 落盘 CSV
    python utility_scripts/store_operation_observation.py --format csv --output outputs/tables/
    python utility_scripts/store_operation_observation.py --as-of 2026-09-16 --window-days 7
    python utility_scripts/store_operation_observation.py --limit 50           # 终端展示行数
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(_WS_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from utils.result_contract import build_success_contract, save_contract_json  # noqa: E402
from shared.loaders import store_info_loader as sl  # noqa: E402

ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
LEADS_CSV = REPO_ROOT / "dataset" / "门店下发线索数.csv"
ZHULI_ZAIGANG_CSV = REPO_ROOT / "dataset" / "门店日报_主理_当月.csv"

COLUMNS = ["门店", "门店类型", "门店形态", "关联门店", "近7日下发线索", "近7日锁单", "CM3小订", "小订/线索"]
UNKNOWN_TYPE = "未知"
IGNORED_TYPE_ROWS = {"全部"}
NO_DATA = "—"


def parse_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description="门店经营状况观察（全门店）")
    p.add_argument("--as-of", dest="as_of", help="观测截止日 YYYY-MM-DD（默认订单/线索数据最大日）")
    p.add_argument("--window-days", type=int, default=7, help="下发线索窗口天数（默认 7）")
    p.add_argument("--presale-gen", default="CM3", help="预售代际（默认 CM3）")
    p.add_argument("--limit", type=int, default=20, help="终端展示行数（默认 20）")
    p.add_argument("--include-relations", action="store_true",
                   help="额外纳入无独立数据的快闪/慢闪 popup（仅指明关联车城店，不重复计数值）")
    p.add_argument("--format", default="terminal", choices=["terminal", "csv", "json"])
    p.add_argument("--output", help="输出目录（csv/json 落盘）")
    return p.parse_args(argv)


def load_type_map() -> dict[str, str]:
    """门店名 → 运营门店类型。（主理在岗统计，剔除聚合行）"""
    m: dict[str, str] = {}
    if ZHULI_ZAIGANG_CSV.exists():
        z = pd.read_csv(ZHULI_ZAIGANG_CSV, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        if "门店类型" not in z.columns and "门店类型 " in z.columns:
            z = z.rename(columns={"门店类型 ": "门店类型"})
        if "门店名称" in z.columns and "门店类型" in z.columns:
            z = z.drop_duplicates("门店名称")
            for name, kind in z[["门店名称", "门店类型"]].itertuples(index=False):
                name = str(name).strip()
                kind = str(kind).strip()
                if name and name not in IGNORED_TYPE_ROWS and kind not in IGNORED_TYPE_ROWS:
                    m[name] = kind
    return m


def load_code_map() -> dict[str, str]:
    """门店名 → Dealer Code（主理在岗统计，数据侧门店名 ↔ 编码的直接映射，剔除聚合行）。"""
    m: dict[str, str] = {}
    if ZHULI_ZAIGANG_CSV.exists():
        z = pd.read_csv(ZHULI_ZAIGANG_CSV, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        if "门店名称" in z.columns and "门店编码" in z.columns:
            z = z.drop_duplicates("门店名称")
            for name, code in z[["门店名称", "门店编码"]].itertuples(index=False):
                name, code = str(name).strip(), str(code).strip()
                if name and name not in IGNORED_TYPE_ROWS and code and code not in IGNORED_TYPE_ROWS:
                    m[name] = code
    return m


def load_leads(as_of: pd.Timestamp | None, window_days: int) -> tuple[pd.Series, pd.Timestamp | None]:
    if not LEADS_CSV.exists():
        return pd.Series(dtype="int64"), None
    df = pd.read_csv(LEADS_CSV, encoding="utf-8-sig")
    df["门店"] = df["门店"].astype("string").str.strip()
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
    df["下发线索数"] = pd.to_numeric(df["下发线索数"], errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["日期"])
    if df.empty:
        return pd.Series(dtype="int64"), None
    asof = pd.Timestamp(as_of).normalize() if as_of else pd.Timestamp(df["日期"].max()).normalize()
    start = asof - pd.Timedelta(days=window_days - 1)
    w = df[(df["日期"] >= start) & (df["日期"] <= asof)]
    return w.groupby("门店")["下发线索数"].sum(), asof


def load_orders(as_of: pd.Timestamp | None, window_days: int) -> tuple[pd.Series, pd.Timestamp | None]:
    """近 N 日锁单数（按门店，全部车系）。返回 (by_store, as_of)。"""
    if not ORDER_PARQUET.exists():
        return pd.Series(dtype="int64"), None
    df = pd.read_parquet(ORDER_PARQUET, columns=["order_number", "store_name", "lock_time"])
    df["store_name"] = df["store_name"].astype("string").str.strip()
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    df = df.dropna(subset=["lock_time"])
    if df.empty:
        return pd.Series(dtype="int64"), None
    asof = pd.Timestamp(as_of).normalize() if as_of else pd.Timestamp(df["lock_time"].max()).normalize()
    start = asof - pd.Timedelta(days=window_days - 1)
    w = df[(df["lock_time"] >= start) & (df["lock_time"] < asof + pd.Timedelta(days=1))]
    return w.groupby("store_name")["order_number"].nunique(), asof


def load_cm3(as_of: pd.Timestamp | None, presale_gen: str) -> tuple[pd.Series, pd.Timestamp | None, pd.Timestamp | None]:
    """CM3 留存小订（累计至 as_of）。返回 (by_store, as_of, presale_open)。"""
    if not ORDER_PARQUET.exists():
        return pd.Series(dtype="int64"), as_of, None
    from utils.monitors.series_group import apply_series_group_logic
    from utils.monitors.phase import load_business_definition, open_hour, open_minute

    bd = load_business_definition(BUSINESS_DEF)
    df = pd.read_parquet(ORDER_PARQUET, columns=[
        "order_number", "store_name", "series", "product_name",
        "intention_payment_time", "intention_refund_time", "lock_time",
    ])
    df["store_name"] = df["store_name"].astype("string").str.strip()
    for c in ("intention_payment_time", "intention_refund_time", "lock_time"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df = apply_series_group_logic(df, bd)
    if as_of is None:
        asof = pd.Timestamp(df["lock_time"].max()).normalize()
    else:
        asof = pd.Timestamp(as_of).normalize()
    end = asof + pd.Timedelta(days=1)
    tp = bd.get("time_periods", {}).get(presale_gen, {})
    if not tp.get("start"):
        return pd.Series(dtype="int64"), asof, None
    open_ts = pd.Timestamp(tp["start"]) + pd.Timedelta(
        hours=open_hour(bd, presale_gen), minutes=open_minute(bd, presale_gen))
    sel = df[(df["series_group_logic"] == presale_gen)
             & (df["intention_payment_time"] >= open_ts)
             & (df["intention_payment_time"] < end)
             & (df["intention_refund_time"].isna() | (df["intention_refund_time"] >= end))]
    return sel.groupby("store_name")["order_number"].nunique(), asof, open_ts


def _base_name(s: str) -> str:
    """门店名归一化基名：去 popup/日期后缀 与 城市展厅/临时展厅/体验中心 等店型后缀。"""
    import re
    s = re.sub(r"^popup\s*", "", str(s or ""))
    s = re.sub(r"\s*\d{4}-\d{4}.*$", "", s)
    s = re.sub(r"\s*\d{2}[/.]\d{2}.*$", "", s)
    s = re.sub(r"城市展厅|临时展厅|城市空间|城市体验中心|体验中心|展厅", "", s)
    return re.sub(r"[\s（）()]+", "", s)


def load_checheng() -> list[dict]:
    """关联车城店候选（主理在岗统计 门店类型=车城店）。"""
    out: list[dict] = []
    if ZHULI_ZAIGANG_CSV.exists():
        z = pd.read_csv(ZHULI_ZAIGANG_CSV, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        if "门店类型" not in z.columns and "门店类型 " in z.columns:
            z = z.rename(columns={"门店类型 ": "门店类型"})
        cols = [c for c in ("门店名称", "经销商主体", "城市", "门店类型") if c in z.columns]
        if "门店名称" in cols and "门店类型" in cols:
            z = z.drop_duplicates("门店名称")
            for r in z[cols].to_dict("records"):
                if str(r.get("门店类型", "")).strip() == "车城店" and str(r.get("门店名称", "")).strip():
                    out.append({"name": str(r["门店名称"]).strip(),
                                "bloc": str(r.get("经销商主体", "")).strip(),
                                "city": str(r.get("城市", "")).replace("市", "")})
    return out


def _lcs_len(a: str, b: str) -> int:
    """最长公共子串长度（用于选关联车城店）。"""
    import re
    a = re.sub(r"[\s（）()]+", "", str(a or ""))
    b = re.sub(r"[\s（）()]+", "", str(b or ""))
    best = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def find_associated_checheng(store: str, info: dict | None, che: list[dict]) -> str | None:
    """无独立数据的 popup → 同主体同城市车城店（名称最长公共子串择优）。"""
    if not che:
        return None
    bloc = (info or {}).get("bloc_name") or ""
    city = ((info or {}).get("city_name") or "").replace("市", "")
    cand = [c for c in che if c["bloc"] == bloc] if bloc else []
    if city:
        same = [c for c in cand if c["city"] == city]
        if same:
            cand = same
    if not cand:
        return None
    target = (info or {}).get("dealer_name_fc") or store
    return max(cand, key=lambda c: _lcs_len(target, c["name"]))["name"]


def build_table(args) -> tuple[pd.DataFrame, dict]:
    leads, leads_asof = load_leads(args.as_of, args.window_days)
    orders, orders_asof = load_orders(args.as_of, args.window_days)
    cm3, asof, presale_open = load_cm3(pd.Timestamp(args.as_of).normalize() if args.as_of else None, args.presale_gen)
    if asof is None:
        asof = leads_asof or orders_asof
    type_map = load_type_map()
    code_map = load_code_map()

    names = set(leads.index) | set(orders.index) | set(cm3.index) | set(type_map.keys())
    # store_info 门店全名 → store_format（仅精确匹配；用于补充 popup 或精确命中，不做子串猜测）
    si = sl.load_store_info()
    si_format: dict[str, str] = {}
    if si is not None and "store_format" in si.columns:
        for nm, fm in si.drop_duplicates("Dealer Name Fc")[["Dealer Name Fc", "store_format"]].itertuples(index=False):
            nm = str(nm).strip()
            if nm:
                si_format[nm] = str(fm)
    # 补充 store_info 中「快闪/慢闪(IMP/IME)」在营门店（仅 --include-relations 时；popup 常无独立数据）
    if getattr(args, "include_relations", False) and si_format:
        data_bases = {_base_name(n) for n in names}
        popup_names = set(si.loc[(si["store_format"] == "快闪/慢闪")
                                 & (si["Store Create Status Desc"] == "开业"), "Dealer Name Fc"]
                          .dropna().astype(str).str.strip())
        names |= {p for p in popup_names if p and _base_name(p) not in data_bases}
    names = sorted(names)
    che = load_checheng()
    rows = []
    for n in names:
        L = int(leads.get(n, 0))
        O = int(orders.get(n, 0))
        C = int(cm3.get(n, 0))
        kind = type_map.get(n) or UNKNOWN_TYPE                       # 运营门店类型（主理在岗统计）
        # 门店形态：只认 Dealer Code 前缀（主理在岗统计门店编码，其次 store_info 精确名称），不猜
        if code_map.get(n):
            fmt = sl.get_store_format(code_map[n])
        else:
            fmt = si_format.get(n, UNKNOWN_TYPE)
        # 无独立数据的快闪/慢闪 popup：不重复列数值，只指明关联车城店
        assoc, lead_v, order_v, cm3_v, ratio_v = "", L, O, C, (f"{C / L * 100:.1f}%" if L else "—")
        if fmt == "快闪/慢闪" and L == 0 and O == 0 and C == 0:
            assoc = find_associated_checheng(n, sl.resolve_dealer_info(n), che) or ""
            if assoc:
                lead_v = order_v = cm3_v = ratio_v = NO_DATA
        rows.append({
            "门店": n,
            "门店类型": kind,
            "门店形态": fmt,
            "关联门店": assoc,
            "近7日下发线索": lead_v,
            "近7日锁单": order_v,
            "CM3小订": cm3_v,
            "小订/线索": ratio_v,
            "_ratio": (C / L) if L else -1.0,
            "_leads_num": L,
            "_order_num": O,
        })
    df = pd.DataFrame(rows).sort_values(["_ratio", "_leads_num"], ascending=[False, False]).reset_index(drop=True)
    if not getattr(args, "include_relations", False):
        # 只保留「有下发线索 或 有订单(近N日锁单)」的门店，过滤无活动的空店
        df = df[(df["_leads_num"] > 0) | (df["_order_num"] > 0)].reset_index(drop=True)
    meta = {"as_of": asof, "leads_asof": leads_asof, "presale_open": presale_open,
            "window_days": args.window_days, "presale_gen": args.presale_gen}
    return df, meta


def render_terminal(df: pd.DataFrame, meta: dict, limit: int, out_path: Path | None) -> str:
    lines = ["[Summary]",
             f"  门店经营状况观察（{len(df)} 家；线索窗口近 {meta['window_days']} 日，截至 {meta['as_of'].date()}）",
             "",
             "[Scope]",
             f"  数据源: {LEADS_CSV}（线索）; {ORDER_PARQUET}（{meta['presale_gen']} 小订）; {ZHULI_ZAIGANG_CSV}（门店类型）",
             f"  口径: 近N日下发线索=窗口求和; CM3小订=预售开放({meta['presale_open']})起未退意向金累计; 小订/线索=CM3小订÷近N日线索",
             "",
             "[Result]"]
    lines.append("\t".join(COLUMNS))
    for _, r in df.head(limit).iterrows():
        lines.append("\t".join([r["门店"], r["门店类型"], r["门店形态"], r["关联门店"],
                                str(r["近7日下发线索"]), str(r["近7日锁单"]), str(r["CM3小订"]), r["小订/线索"]]))
    lines.append(f"  （共 {len(df)} 家，仅显示前 {min(limit, len(df))} 家）")
    if out_path:
        lines.append(f"\n[Output]\n  CSV: {out_path}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    df, meta = build_table(args)

    out_dir = Path(args.output) if args.output else _WS_ROOT / "outputs" / "tables"
    csv_path = None
    if args.format == "csv" or args.output:
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_dir / "store_operation_observation.csv"
        df[COLUMNS].to_csv(csv_path, index=False, encoding="utf-8-sig")

    scope = {
        "data_source": f"{LEADS_CSV}; {ORDER_PARQUET}",
        "filters": {"window_days": args.window_days, "as_of": str(meta["as_of"].date()), "presale_gen": meta["presale_gen"]},
        "metric_definition": ("门店类型=主理在岗统计门店类型; 门店形态=主理在岗统计门店编码前缀(store_format)"
                              "(缺省回落 store_info); 近N日下发线索=SUM(下发线索数); 近N日锁单=COUNTD(order_number) lock窗口; "
                              "CM3小订=COUNTD(order_number) series_group=CM3 未退; 小订/线索=CM3小订÷近N日下发线索; "
                              "默认保留 下发线索>0 或 锁单>0"),
    }
    result = {
        "summary": f"门店经营状况观察：{len(df)} 家门店（截至 {meta['as_of'].date()}）",
        "metrics": {"store_count": len(df),
                    "stores_with_leads": int((pd.to_numeric(df['近7日下发线索'], errors='coerce').fillna(0) > 0).sum()),
                    "stores_with_cm3": int((pd.to_numeric(df['CM3小订'], errors='coerce').fillna(0) > 0).sum())},
        "tables": [{"name": "store_operation_observation", "columns": COLUMNS,
                    "rows": df[COLUMNS].to_dict("records")}],
    }
    artifacts = {"csv": str(csv_path)} if csv_path else {}
    contract = build_success_contract(
        script="utility_scripts/store_operation_observation.py",
        command="python " + " ".join(sys.argv),
        scope=scope, result=result, artifacts=artifacts,
    )

    if args.format == "json":
        if args.output:
            save_contract_json(contract, out_dir / "store_operation_observation.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(render_terminal(df, meta, args.limit, csv_path if args.output or args.format == "csv" else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
