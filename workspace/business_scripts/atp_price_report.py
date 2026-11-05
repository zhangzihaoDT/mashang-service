#!/usr/bin/env python
"""
ATP 价格报告 — 统一 CLI + Result Contract

两种报告口径（--report）：
    月度经营 monitor（monthly，现有版 atp_<月>.html）：当月为主窗口，对比上月，附当年累计
    年度经营 monitor（annual，新分类版 atp_annual_<年>.html）：本年至今为主窗口（01-01 ~ 数据最新完整日），
                                                             对比上年同期

两套分类（--state-class）：
    legacy  （默认，向后兼容）：所有车型 / 已有车型 / 当年新车型(含改款) / Sedan / SUV 系列
    series  （新分类）：公司销售车型（2025年已有车型 / 2026年新车型含改款）→
             按车系展开代际（如 LS6 M2/T1），再拆轿车(L6/L7) / SUV(LS6/LS7/LS8/LS9)

--report auto（默认）：series → 年度经营 monitor；legacy → 月度经营 monitor。

用法:
    python workspace/business_scripts/atp_price_report.py --month 2026-09                            # 月度经营 monitor
    python workspace/business_scripts/atp_price_report.py --month 2026-10 --report annual           # 年度经营 monitor
    python workspace/business_scripts/atp_price_report.py --month 2026-10 --state-class series      # 同上（auto 推断）
    python workspace/business_scripts/atp_price_report.py --month 2026-10 --report annual --format html
    python workspace/business_scripts/atp_price_report.py --help
"""

import sys, argparse, json
from pathlib import Path

_WS_ROOT = Path(__file__).resolve().parents[1]
_PRJ_ROOT = _WS_ROOT.parent
_TEMPLATES_DIR = _WS_ROOT / "templates"
for p in [str(_WS_ROOT), str(_PRJ_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd
from datetime import datetime, timedelta
from utils.paths import ensure_shared_on_path
ensure_shared_on_path()
try:  # 兼容两种包名（执行脚本目录在 sys.path 首位的场景）
    from utils.result_contract import build_success_contract, build_partial_contract, save_contract_json, contract_to_terminal
except ImportError:  # pragma: no cover
    from workspace.utils.result_contract import (
        build_success_contract, build_partial_contract, save_contract_json, contract_to_terminal)

try:
    from operators.atp_analysis import run_atp_operator, apply_business_logic, _load_business_definition
except ImportError:  # pragma: no cover
    from shared.operators.atp_analysis import run_atp_operator, apply_business_logic, _load_business_definition

ORDER_PARQUET = _PRJ_ROOT / "dataset" / "order_data.parquet"
PRICE_DATA_CSV = _PRJ_ROOT / "dataset" / "incoming" / "tableau" / "price_data_view.csv"
REPORT_STYLE_CSS = _TEMPLATES_DIR / "report_style.css"

# 车系 → 车身形式（公司销售车型分轿车/SUV 口径）
BODY_TYPE_SERIES = {
    "sedan": ["L6", "L7"],
    "suv": ["LS6", "LS7", "LS8", "LS9"],
}
BODY_TYPE_LABEL = {"sedan": "轿车", "suv": "SUV"}
# 分类代际前缀 → 品类标注（M=车型代际，T=改款/同步派生版本）
GENERATION_KIND = {"M": "M", "T": "T"}


def parse_args():
    p = argparse.ArgumentParser(description="ATP 价格报告（月度经营 monitor / 年度经营 monitor）")
    p.add_argument("--month", type=str, help="报告月份 YYYY-MM（默认前一个月）")
    p.add_argument("--start-date", type=str, help="开始日期 (YYYY-MM-DD)")
    p.add_argument("--end-date", type=str, help="结束日期 (YYYY-MM-DD)")
    p.add_argument("--series", type=str, help="车系过滤")
    p.add_argument("--model", type=str, help="具体车型过滤")
    p.add_argument("--city", type=str, help="忽略")
    p.add_argument("--output", type=str, help="输出目录")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json", "csv", "html"])
    p.add_argument("--state-class", type=str, default="legacy", choices=["legacy", "series"],
                   help="分类口径: legacy=原有系别分类(默认); series=公司销售车型→车系代际(如 LS6 M2/T1)→轿车/SUV 新分类")
    p.add_argument("--report", type=str, default="auto", choices=["auto", "monthly", "annual"],
                   help="报告标题口径: monthly=月度经营 monitor(现有 atp_<月>.html); "
                        "annual=年度经营 monitor(本年至今窗口, atp_annual_<年>.html); auto=按 --state-class 推断(series→annual)")
    p.add_argument("--date", type=str, help="忽略"); p.add_argument("--limit", type=int, default=0, help="忽略")
    return p.parse_args()


def _resolve_month(args):
    """解析月份或日期范围。"""
    if args.start_date and args.end_date:
        s = pd.Timestamp(args.start_date)
        e = pd.Timestamp(args.end_date)
        return s, e, f"{args.start_date}~{args.end_date}", "range"
    month = args.month
    if not month:
        today = datetime.now()
        prev = today.replace(day=1) - timedelta(days=1)
        month = prev.strftime("%Y-%m")
    parts = month.split("-")
    y, m = int(parts[0]), int(parts[1])
    t_start = datetime(y, m, 1)
    t_end = (t_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return t_start, t_end, month, "month"


def _resolve_report_kind(args) -> str:
    """报告口径：monthly=月度经营 monitor；annual=年度经营 monitor（本年至今）。

    两版报告与分类口径一一对应：月度经营 monitor = legacy 分类；年度经营 monitor = series 新分类。
    --report auto 时由 --state-class 推断；显式指定时以 --report 为准并回写分类。
    """
    if args.report != "auto":
        return args.report
    return "annual" if args.state_class == "series" else "monthly"


def _resolve_state_class(args, report_kind: str) -> str:
    """分类与报告口径绑定：annual → series；monthly → legacy。"""
    return "series" if report_kind == "annual" else "legacy"


def _detect_data_cutoff(df: pd.DataFrame, as_of: pd.Timestamp) -> tuple[str, list]:
    """探测数据截止日：排除最新一天不满整日的数据（如当日仅零星入数）。

    规则：从 as_of 往前看，末位日期的所有订单开票时间全部落在 00:00:00（且行数明显低于前一日）
    视为“当天未入数”，回退到前一完整日。返回 (截止日 YYYY-MM-DD, 告警列表)。
    """
    warnings = []
    inv = pd.to_datetime(df["invoice_upload_time"], errors="coerce").dropna()
    inv = inv[inv.dt.normalize() <= as_of.normalize()]
    if inv.empty:
        return as_of.strftime("%Y-%m-%d"), ["订单数据在报告期内无开票记录，按报告期截止日计算"]
    daily = inv.dt.normalize().value_counts().sort_index()
    last_day = daily.index[-1]
    # 只看时间部分：末位日是否“全是 00:00:00”（表头/占位行特征）
    day_inv = inv[inv.dt.normalize() == last_day]
    prev_cnt = int(daily.iloc[-2]) if len(daily) > 1 else 0
    last_cnt = int(daily.iloc[-1])
    all_midnight = (day_inv.dt.hour == 0).all() and (day_inv.dt.minute == 0).all()
    if all_midnight and prev_cnt > 0 and last_cnt < prev_cnt * 0.1:
        cutoff = daily.index[-2]
        warnings.append(
            f"最新日期 {last_day.date()} 仅 {last_cnt} 条且时间均为 00:00:00（疑似当日未入数），"
            f"计算截止日回退至 {cutoff.date()}"
        )
        return cutoff.strftime("%Y-%m-%d"), warnings
    return last_day.strftime("%Y-%m-%d"), warnings


# ── 分类构造 ──────────────────────────────────────────────────────────

def _build_legacy_segments(df_wl: pd.DataFrame, bdef: dict, target_year: int):
    time_periods = bdef.get("time_periods", {})

    def _end_year(period):
        """上市日所在年；上市日未确认（预售期只有 start）的代际不计入新/老车型分组。"""
        end = (period or {}).get("end")
        if not end:
            return None
        try:
            return pd.to_datetime(end).year
        except (TypeError, ValueError):
            return None

    new_groups = {g for g, p in time_periods.items() if (_end_year(p) or -1) >= target_year}
    # 上市日未确认的代际既不属于「当年新车型」也不属于「已有车型」，归入兜底层（_old 的未登记分支）
    old_groups = {g for g, p in time_periods.items() if _end_year(p) is not None and _end_year(p) < target_year}
    all_groups = new_groups | old_groups

    def _suv(d): return d[d["series_derived"].isin(BODY_TYPE_SERIES["suv"])]
    def _sedan(d): return d[d["series_derived"].isin(BODY_TYPE_SERIES["sedan"])]
    def _old(d): return d[d["series_group_logic"].isin(old_groups) | ~d["series_group_logic"].isin(all_groups)]
    def _new(d): return d[d["series_group_logic"].isin(new_groups)]

    return [
        ("所有车型", None, "all"),
        ("已有车型", _old, "all"),
        (f"当年新车型(含改款)", _new, "all"),
        ("Sedan (L6+L7)", _sedan, "sedan"),
        ("Sedan 已有车型", lambda d: _old(_sedan(d)), "sedan"),
        ("L6", lambda d: d[d["series_derived"] == "L6"], "sedan"),
        ("Sedan 当年新车型(含改款)", lambda d: _new(_sedan(d)), "sedan"),
        ("SUV (LS6+LS7+LS8+LS9)", _suv, "suv"),
        ("SUV 已有车型", lambda d: _old(_suv(d)), "suv"),
        ("LS6", lambda d: d[d["series_derived"] == "LS6"], "suv"),
        ("LS9", lambda d: d[d["series_derived"] == "LS9"], "suv"),
        ("SUV 当年新车型(含改款)", lambda d: _new(_suv(d)), "suv"),
    ]


def _ms(v) -> str:
    return str(int(v)) if v is not None and not pd.isna(v) else "—"


def _fmt_atp(v) -> str:
    return f"¥{v:,.0f}" if v is not None else "—"


def _fmt_yuan(v) -> str:
    """金额展示：整数（含千分位）；None/NaN 显示 '—'。"""
    if v is None:
        return "—"
    try:
        if pd.isna(v):
            return "—"
    except (TypeError, ValueError):
        return "—"
    return f"¥{float(v):,.0f}"


def _fmt_cnt(v) -> str:
    return f"{v:,}" if v is not None else "—"


def _fmt_rate(v) -> str:
    """折扣率展示：百分数一位小数；None/NaN 显示 '—'。"""
    if v is None:
        return "—"
    try:
        if pd.isna(v):
            return "—"
    except (TypeError, ValueError):
        return "—"
    return f"{float(v) * 100:.1f}%"


def _to_num(s) -> pd.Series:
    """数值列清洗：去千分位逗号后转 float（Tableau 导出常带逗号）。"""
    return pd.to_numeric(s.astype(str).str.replace(",", "", regex=False), errors="coerce")


def load_price_discount(path: Path = PRICE_DATA_CSV) -> pd.DataFrame | None:
    """读取 Tableau Price 视图，返回按 order_number 索引的车价口径价格表。

    支持三种导出格式：
      1) 宽表（当前）：直接含 Vehicle Price / Total Vehicle Discount 列
      2) 长表（过渡）：含「度量名称 / 度量值」，度量名称 ∈ {Vehicle Price, Total Vehicle Discount}
      3) 宽表（最早）：只有 origin_amount / Invoice Amount（无官方车价，用 origin 近似）

    输出列（按 order_number 索引）：
      vehicle_price          MSRP 官方车价（不含选装，= origin_amount − 选装价，已用 config_attribute 验证）
      total_vehicle_discount 当期车价维度总优惠（逐单，会随车型老化增长）
      invoice_amount         开票价（Price 视图 INT([Invoice Amount])）
      option_price           选装价 = origin_amount − vehicle_price（已用 config_attribute 验证 99.2%）
      product                产品名（用于反查上市期 TVD 基准）
      invoice_time           开票时间（用于反查上市期 TVD 基准）
    权益价与折扣率不在此处计算，见 build_equity_baseline / attach_equity_price。
    文件缺失或字段不可用时返回 None（报告降级为不展示折扣列）。
    """
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception:
        return None
    if "Order Number" not in df.columns:
        return None

    df["order_number"] = df["Order Number"].astype(str)
    VP_COL, TVD_COL = "Vehicle Price", "Total Vehicle Discount"

    # —— 宽表（当前）：Vehicle Price / Total Vehicle Discount 为普通列 ——
    if VP_COL in df.columns and TVD_COL in df.columns and "度量名称" not in df.columns:
        base = df.drop_duplicates("order_number").set_index("order_number")
        inv_col = next((c for c in ("INT([Invoice Amount])", "Invoice Amount")
                        if c in base.columns), None)
        out = pd.DataFrame({
            "vehicle_price": _to_num(base[VP_COL]),
            "total_vehicle_discount": _to_num(base[TVD_COL]),
            "invoice_amount": _to_num(base[inv_col]) if inv_col else float("nan"),
            "option_price": _to_num(base["origin_amount"]) - _to_num(base[VP_COL]),
            "product": base.get("Product Name"),
            "order_type": base.get("order_type"),
            "invoice_time": pd.to_datetime(base.get("Invoice Upload Time"), errors="coerce"),
        })
    # —— 长表：度量名称/度量值 透视成宽表 ——
    elif {"度量名称", "度量值"}.issubset(df.columns):
        df["_mv"] = _to_num(df["度量值"])
        wide = df.pivot_table(index="order_number", columns="度量名称",
                              values="_mv", aggfunc="first")
        if VP_COL not in wide.columns or TVD_COL not in wide.columns:
            return None
        out = pd.DataFrame({
            "vehicle_price": _to_num(wide[VP_COL]),
            "total_vehicle_discount": _to_num(wide[TVD_COL]),
        })
        base = df.drop_duplicates("order_number").set_index("order_number")
        inv_col = next((c for c in ("INT([Invoice Amount])", "Invoice Amount")
                        if c in base.columns), None)
        out["invoice_amount"] = _to_num(base[inv_col]) if inv_col else float("nan")
        out["option_price"] = _to_num(base["origin_amount"]) - out["vehicle_price"]
        out["product"] = base.get("Product Name")
        out["order_type"] = base.get("order_type")
        out["invoice_time"] = pd.to_datetime(base.get("Invoice Upload Time"), errors="coerce")
    # —— 宽表（最早）：无官方车价，用 origin−invoice 近似 ——
    else:
        inv_col = "Invoice Amount" if "Invoice Amount" in df.columns else (
            "INT([Invoice Amount])" if "INT([Invoice Amount])" in df.columns else None)
        if inv_col is None or "origin_amount" not in df.columns:
            return None
        base = df.drop_duplicates("order_number").set_index("order_number")
        origin = _to_num(base["origin_amount"])
        out = pd.DataFrame({
            "vehicle_price": origin,
            "total_vehicle_discount": origin - _to_num(base[inv_col]),
            "invoice_amount": _to_num(base[inv_col]),
            "option_price": 0.0,
            "product": base.get("Product Name"),
            "order_type": base.get("order_type"),
            "invoice_time": pd.to_datetime(base.get("Invoice Upload Time"), errors="coerce"),
        })

    return out[out.index.notna()]


# ── 权益价基准：上市期 TVD（锁定口径）────────────────────────────────────────
# 策略（2026-11 固定）：
#   TVD 随车型上市时间单调增长，MSRP 恒定 ⇒ 权益价应锚定「上市期」的 TVD，而非当期 TVD。
#   1) 上市后 EQUITY_WINDOW_DAYS 天内订单 ≥ EQUITY_MIN_N 单 → 用该窗口中位数（method=launch，精确）
#   2) 否则首月订单 ≥ EQUITY_MIN_N → 用首月中位数（method=first_month，精确）
#   3) 否则 → 用「月内中位数的历史最小值」（method=fallback，近似；上市期数据缺失）
#   MSRP 取产品内众数（MSRP 本应恒定；出现多个值说明上游产品名粒度不足，会在 warnings 中告警）
#   权益价 = MSRP(众数) − TVD基准；折扣率 = 1 − 开票价 / (权益价 + 选装挂牌)
EQUITY_WINDOW_DAYS = 60
EQUITY_MIN_N = 30
EQUITY_MIN_MONTH_N = 10


def build_equity_baseline(
    price_df: pd.DataFrame | None,
    gen_by_order: "pd.Series | None" = None,
    bdef: dict | None = None,
) -> dict:
    """按产品计算上市期 TVD 基准与 MSRP 众数，返回
    {product: {"tvd_base", "method", "msrp", "msrp_variants"}}。

    gen_by_order：order_number → 代际（series_group_logic），用于反查上市日。
    bdef：business_definition，上市日取 time_periods.{gen}.end（禁止从数据推断）。
    msrp_variants > 1 表示同一产品名下存在多个 MSRP（多个 SKU 共用产品名），调用方应告警。
    """
    if price_df is None or price_df.empty or "product" not in price_df.columns:
        return {}
    d = price_df.dropna(subset=["product"]).copy()
    # 基准只用「用户车」订单：试驾车/大客户等 TVD 常为 0，会污染基准
    if "order_type" in d.columns:
        d = d[d["order_type"].fillna("").astype(str) == "用户车"]
    if d.empty:
        return {}

    # 上市日：order → 代际 → time_periods[gen].end
    launch_by_order = pd.Series(dtype="datetime64[ns]")
    if gen_by_order is not None and bdef:
        tp = bdef.get("time_periods", {}) or {}
        launch_map = {k: pd.Timestamp(v["end"]) for k, v in tp.items()
                      if isinstance(v, dict) and v.get("end")}
        gen = gen_by_order.reindex(d.index)
        launch_by_order = gen.map(launch_map)
    d["_launch"] = launch_by_order

    out: dict = {}
    for prod, g in d.groupby("product"):
        tv = g["total_vehicle_discount"].dropna()
        if tv.empty:
            continue
        launch = g["_launch"].dropna()
        tvd_base, method = None, "fallback"

        if not launch.empty and g["invoice_time"].notna().any():
            l = launch.iloc[0]
            win = g[(g["invoice_time"] >= l) &
                    (g["invoice_time"] < l + pd.Timedelta(days=EQUITY_WINDOW_DAYS))]["total_vehicle_discount"].dropna()
            if len(win) >= EQUITY_MIN_N:
                tvd_base, method = float(win.median()), "launch"
            else:
                it = g["invoice_time"].dropna()
                if not it.empty:
                    first_m = it.min().to_period("M")
                    # 用 g 自身列构造掩码，避免子集 Series 索引错位
                    fm = g.loc[g["invoice_time"].dt.to_period("M") == first_m,
                               "total_vehicle_discount"].dropna()
                else:
                    fm = pd.Series(dtype=float)
                if len(fm) >= EQUITY_MIN_N:
                    tvd_base, method = float(fm.median()), "first_month"

        if tvd_base is None:
            # 回退：只用月样本 ≥ EQUITY_MIN_MONTH_N 的「月内中位」取最小，避免小样本月把基准拉成 0
            mono = g.groupby(g["invoice_time"].dt.to_period("M"))["total_vehicle_discount"]
            agg = mono.agg(["median", "size"])
            agg = agg[agg["size"] >= EQUITY_MIN_MONTH_N]
            if agg.empty:
                tvd_base = float(tv.quantile(0.05))
            else:
                tvd_base = float(agg["median"].min())
            method = "fallback"

        out[str(prod)] = {
            "tvd_base": tvd_base,
            "method": method,
            # MSRP 取产品内众数：MSRP 本应恒定，多值说明产品名粒度不足
            "msrp": _product_msrp(g["vehicle_price"]),
            "msrp_variants": int(g["vehicle_price"].dropna().nunique()),
        }
    return out


def _product_msrp(s: pd.Series) -> float | None:
    """产品内 MSRP 众数（并列时取较小值，保持稳定）；全空返回 None。"""
    v = s.dropna()
    if v.empty:
        return None
    vc = v.value_counts()
    top = vc[vc == vc.max()].index
    return float(min(top))


def attach_equity_price(price_df: pd.DataFrame | None, baseline: dict) -> pd.DataFrame | None:
    """把产品级 MSRP / TVD 基准接到订单上，计算权益价、应然价与折扣率。

    msrp           = 产品内 MSRP 众数（产品级常量，保证同一产品口径一致）
    equity_price   = msrp − tvd_base（产品级常量，上市期权益车价）
    expected_price = equity_price + option_price（应然价：权益车价 + 全部选装挂牌）
    discount_rate  = 1 − invoice_amount / expected_price

    折扣率用「应然价」作分母：分子分母都含选装，量纲一致，不会把赠送选装误当让利。
    """
    if price_df is None or price_df.empty or not baseline:
        return None
    base_map = {k: v["tvd_base"] for k, v in baseline.items()}
    fb_map = {k: (v["method"] == "fallback") for k, v in baseline.items()}
    msrp_map = {k: v.get("msrp") for k, v in baseline.items()}
    out = price_df.copy()
    out["tvd_base"] = out["product"].map(base_map)
    out["_is_fallback"] = out["product"].map(fb_map).fillna(True).astype(bool)
    # 产品级众数 MSRP（缺失时退回订单级 vehicle_price）
    out["msrp"] = out["product"].map(msrp_map)
    out["msrp"] = out["msrp"].where(out["msrp"].notna(), out["vehicle_price"])
    out["equity_price"] = out["msrp"] - out["tvd_base"]
    # 应然价 = 权益车价 + 选装挂牌
    out["expected_price"] = out["equity_price"] + out["option_price"].fillna(0)
    safe_exp = out["expected_price"].where(out["expected_price"].abs() > 1)
    out["discount_rate"] = (1 - out["invoice_amount"] / safe_exp).where(safe_exp.notna())
    return out


def _discount_for_segment(
    price_df: pd.DataFrame | None,
    seg_df: pd.DataFrame,
    start: str,
    end_excl: str,
) -> dict:
    """计算分组的 MSRP 均价、权益价均价、应然价均价、折扣率与基准可信度。

    订单口径与 run_atp_operator 完全一致：用户车 + 已锁单 + invoice_upload_time 落在窗口内。
    返回 dict（无数据时各标量为 None、n=0）：
      msrp      = Σvehicle_price / n
      equity    = Σ(vehicle_price − tvd_base) / n
      expected  = Σ(equity_price + option_price) / n
      rate      = 1 − Σinvoice_amount / Σexpected_price（金额加权）
      n         参与样本数
      fallback_share  近似基准（上市期数据缺失）订单占比
    """
    empty = {"msrp": None, "equity": None, "expected": None,
             "rate": None, "n": 0, "fallback_share": 0.0}
    if price_df is None or seg_df is None or seg_df.empty:
        return empty
    d = seg_df
    if "order_type" in d.columns:
        d = d[d["order_type"].fillna("Unknown").astype(str) == "用户车"]
    if "invoice_upload_time" not in d.columns or "lock_time" not in d.columns:
        return empty
    iu = pd.to_datetime(d["invoice_upload_time"], errors="coerce")
    st, en = pd.to_datetime(start, errors="coerce"), pd.to_datetime(end_excl, errors="coerce")
    d = d[d["lock_time"].notna() & (iu >= st) & (iu < en)]
    if d.empty:
        return empty

    ids = d["order_number"].astype(str)
    hit = ids[ids.isin(price_df.index)]
    if hit.empty:
        return empty
    sub = price_df.loc[hit.unique()]
    valid = sub[sub["discount_rate"].notna()]
    if valid.empty:
        return empty

    n = len(valid)
    # MSRP 用产品级众数（与权益价同源），避免同产品混多档导致非整数均值
    total_vp = float(valid["msrp"].sum()) if "msrp" in valid.columns else float(valid["vehicle_price"].sum())
    total_eq = float(valid["equity_price"].sum())
    total_exp = float(valid["expected_price"].sum())
    total_inv = float(valid["invoice_amount"].sum())
    # 该分组中「近似基准」订单占比（上市期价格数据缺失 → 退回月内中位最小值）
    fb_share = float(valid["_is_fallback"].mean()) if "_is_fallback" in valid.columns else 0.0
    return {
        "msrp": total_vp / n,
        "equity": total_eq / n,
        "expected": total_exp / n,
        "rate": (1 - total_inv / total_exp) if total_exp else None,
        "n": int(n),
        "fallback_share": fb_share,
    }


def _display_label(generations: list, series: str | None = None) -> str:
    """代际展示标签：按车系上下文简化（如 DM2 → M2，CM0/CM1/CM2 → M0/M1/M2），未知代际保持原样。"""
    out = []
    for g in generations:
        g = str(g)
        m = GEN_DISPLAY.get(g)
        out.append(m[2] if (m and (series is None or m[0] == series)) else g)
    return "/".join(out)


# 代际 → (车系, 品类, 展示标签)：M=车型代际（main model），T=改款/派生版本（tweak）
GEN_DISPLAY = {
    "DM0": ("L6", "M", "M0"),
    "DM1": ("L6", "M", "M1"),
    "DM2": ("L6", "M", "M2"),
    "CM0": ("LS6", "M", "M0"),
    "CM1": ("LS6", "M", "M1"),
    "CM2": ("LS6", "M", "M2"),
    "CM3": ("LS6", "M", "M3"),
    "LS8": ("LS8", "M", "M0"),
    "LS9": ("LS9", "M", "M0"),
}


def _gen_kind(g) -> str:
    """代际类型：M=车型代际，T=改款/派生版本。"""
    return GEN_DISPLAY.get(str(g), ("", "-", ""))[1]


def _build_gen_year_map(bdef: dict) -> dict:
    """代际归年：以 business_definition.json 的 time_periods.{gen}.end（上市日）年份为准。

    业务规定上市时间必须来自业务定义，不得从数据首张开票时间推断
    （见 AGENTS.md / shared/schema/business_definition.json）。
    """
    periods = bdef.get("time_periods", {}) if isinstance(bdef, dict) else {}
    out = {}
    for g, p in periods.items():
        end = (p or {}).get("end")
        if not end:
            continue
        try:
            out[str(g)] = int(pd.Timestamp(end).year)
        except Exception:
            continue
    return out


def _build_series_segments(df_wl: pd.DataFrame, base_year: int, gen_year: dict,
                           as_of: str | None = None):
    """新分类：公司销售车型 → 车系×代际（按年份归组）→ 轿车/SUV。

    代际归年以 business_definition.time_periods.{gen}.end 的年份为准（gen_year 参数）；
    未在业务定义中登记的代际按历史存量车型处理（归入"{base_year-1}年及以前存量车型"层）。
    listing 形如 "LS6 M2/T1"，表示已有代际 M2 / 当年新代际 T1。
    as_of：截面日期（YYYY-MM-DD）。仅展示截至该日期已有用户车开票的代际，
    避免未来代际以 0 台空行混入历史月份报表；缺省展示全部代际。
    """
    u = df_wl[df_wl["order_type"].astype(str) == "用户车"] if "order_type" in df_wl.columns else df_wl
    u = u[u["invoice_upload_time"].notna()]
    # 注意：pd.to_datetime(...).dt.year 的索引不是原索引，必须用 reset_index 对齐后再 groupby
    inv = pd.to_datetime(u["invoice_upload_time"]).reset_index(drop=True)
    gen = u["series_group_logic"].reset_index(drop=True)
    gen_first_invoice = inv.groupby(gen).min()
    net_rollout_year = gen_first_invoice.dt.year.to_dict()   # 仅用于判断"是否已开始交付"
    # 截至截面日期已开始交付（有用户车开票）的代际；历史月份不展示尚未交付的代际空行
    if as_of and len(gen_first_invoice):
        gen_active = set(gen_first_invoice.index[gen_first_invoice <= pd.Timestamp(as_of)])
    else:
        gen_active = set(gen)

    # 公司销售车型 = 6 个在售车型（L6/L7/LS6/LS7/LS8/LS9）用户车，不含兜底桶"其他"。
    # 三层结构：① 全量父行 → ② 同名（剔除{base_year-1}年及以前存量车型）→ ③ 其中：存量车型；
    # 且 ② = {base_year}年已有 + {base_year+1}年新车型，① = ② + ③。
    _pb = (lambda d: d[d["series_derived"].isin(BODY_TYPE_SERIES["sedan"] + BODY_TYPE_SERIES["suv"])])
    segs = [("公司销售车型", _pb, "all", None)]

    # 车系展开：单代际且无改款的车型（如 L7/LS7）不展开，避免冗余代际行
    series_info = []
    for bt, series_list in BODY_TYPE_SERIES.items():
        present = [s for s in series_list if (df_wl["series_derived"] == s).any()]
        for s in present:
            all_gens = sorted(
                [g for g in df_wl.loc[df_wl["series_derived"] == s, "series_group_logic"].dropna().unique() if g != "其他"],
                key=lambda g: _gen_sort_key(g, gen_year),
            )
            if not all_gens:
                continue
            # 代际编号始终按真实先后（历史月份与当月编号一致）：M0=首代，M1=第二代…
            label = {g: f"M{i}" for i, g in enumerate(all_gens)}
            gens_sorted = [g for g in all_gens if g in gen_active]
            g_legacy = [g for g in gens_sorted if gen_year.get(g, 0) < base_year]      # 2024 及以前上市
            g_old = [g for g in gens_sorted if gen_year.get(g, 0) == base_year]        # 2025 年已有车型
            g_new = [g for g in gens_sorted if gen_year.get(g, 0) > base_year]         # 2026 年新车型(含改款)
            series_info.append({
                "body": bt, "series": s,
                "legacy": g_legacy, "old": g_old, "new": g_new,
                "legacy_s": "/".join(label[g] for g in g_legacy) if g_legacy else "/",
                "old_s": "/".join(label[g] for g in g_old) if g_old else "/",
                "new_s": "/".join(label[g] for g in g_new) if g_new else "/",
                "labels": label,
            })

    def _gen_rows(segs, bt, key):
        """挂出某一层级（legacy/old/new）的代际行；bt=None 表示公司销售车型层（不限车身形式）。"""
        for si in series_info:
            if bt is not None and si["body"] != bt:
                continue
            gens = si[key]
            if not gens:
                continue
            total = len(si["legacy"]) + len(si["old"]) + len(si["new"])
            lab = f"{si['series']} {si[key + '_s']}" if total > 1 else si["series"]
            segs.append((f"    {lab}", lambda d, gg=gens: d[d["series_group_logic"].isin(gg)],
                         bt or "all", f"{key}-{si['series']}"))
        if bt is not None and not any(si["body"] == bt and si[key] for si in series_info):
            segs.append(("    /", lambda d: d.iloc[0:0], bt or "all", None))

    def _block(segs, bt, base_title):
        """挂出父行下的三层口径结构：

        ① 父行（全量，已由调用方压入）
        ② {base_title}（剔除{base_year-1}年及以前存量车型）= {base_year}已有 + {base_year+1}新
        ③ 其中：{base_year-1}年及以前存量车型（② 与 ③ 互补，① = ② + ③）
        """
        pfx = (lambda d: d) if bt is None else (lambda d, b=bt: d[d["series_derived"].isin(BODY_TYPE_SERIES[b])])
        def _sel(cond):
            return lambda d, f=pfx: f(d)[cond(f(d))]

        segs.append((f"{base_title}（剔除{base_year - 1}年及以前存量车型）",
                     _sel(lambda d: d["_gen_year"] >= base_year), bt or "all", "excl"))
        segs.append((f"其中：{base_year}年已有车型",
                     _sel(lambda d: d["_gen_year"] == base_year), bt or "all", "old"))
        _gen_rows(segs, bt, "old")
        segs.append((f"其中：{base_year + 1}年新车型(含改款)",
                     _sel(lambda d: d["_gen_year"] > base_year), bt or "all", "new"))
        _gen_rows(segs, bt, "new")
        segs.append((f"其中：{base_year - 1}年及以前存量车型",
                     _sel(lambda d: d["_gen_year"] < base_year), bt or "all", "legacy"))
        _gen_rows(segs, bt, "legacy")

    _block(segs, None, "公司销售车型")
    for bt in BODY_TYPE_SERIES:
        title = f"{BODY_TYPE_LABEL[bt]}系列车型"
        segs.append((title,
                     lambda d, b=bt: d[d["series_derived"].isin(BODY_TYPE_SERIES[b])], bt, None))
        _block(segs, bt, title)

    return segs, gen_year, series_info


def _gen_sort_key(g: str, gen_first_year: dict):
    """代际排序键：首年升序 + M 优先于 T + 名称。"""
    year = gen_first_year.get(g, 9999)
    kind = "0" if "M" in str(g) else "1"
    return (year, kind, str(g))


def main():
    args = parse_args()
    cmd = "python " + " ".join(sys.argv)
    t_start, t_end, t_label, tw_type = _resolve_month(args)
    report_kind = _resolve_report_kind(args)
    is_annual = report_kind == "annual"
    state_class = _resolve_state_class(args, report_kind)
    if args.report != "auto" and args.state_class != state_class:
        print(f"  [note] --report {report_kind} 对应分类口径 {state_class}，已忽略 --state-class {args.state_class}",
              file=sys.stderr)
    report_name = "年度经营 monitor" if is_annual else "月度经营 monitor"

    d_start = t_start.strftime("%Y-%m-%d")
    d_end = t_end.strftime("%Y-%m-%d")

    df = pd.read_parquet(str(ORDER_PARQUET))
    bdef = _load_business_definition()
    df_wl = apply_business_logic(df, bdef)

    if args.series:
        df_wl = df_wl[df_wl["series"] == args.series]
    if args.model:
        df_wl = df_wl[df_wl["product_name"].str.contains(args.model, na=False)]

    warnings = []
    # 主窗口：annual=本年至今（截止数据最新完整日）；monthly=当月
    if is_annual:
        cutoff, warn_cutoff = _detect_data_cutoff(df_wl, pd.Timestamp(d_end))
        warnings.extend(warn_cutoff)
        # 年度报告按月选择"报告期"仅用于确定年份与产物名，主窗口始终为当年年初至数据截止日
        if pd.Timestamp(cutoff).year != t_start.year:
            warnings.append(f"所选月份 {t_label} 与数据截止日 {cutoff} 不同年，年度窗口按数据截止日年份计算")
        cutoff_ts = pd.Timestamp(cutoff)
        period_start = pd.Timestamp(f"{cutoff_ts.year}-01-01")
        period_end = cutoff_ts                    # 含当天
        period_label = f"{cutoff_ts.year}年至今"
        cmp_start = pd.Timestamp(f"{cutoff_ts.year - 1}-01-01")
        cmp_end = pd.Timestamp(f"{cutoff_ts.year - 1}-{cutoff_ts.month:02d}-01") + pd.offsets.MonthBegin(1) - timedelta(days=1)
        cmp_label = f"上年同期({cutoff_ts.year - 1}年1-{cutoff_ts.month}月)"
    else:
        cutoff = d_end
        period_start, period_end = t_start, t_end
        period_label = t_label
        cmp_start, cmp_end = (t_start - timedelta(days=1)).replace(day=1), t_start - timedelta(days=1)
        cmp_label = f"上月({cmp_start.strftime('%Y-%m')})"

    p_start = period_start.strftime("%Y-%m-%d")
    p_end_excl = (period_end + timedelta(days=1)).strftime("%Y-%m-%d")
    c_start = cmp_start.strftime("%Y-%m-%d")
    c_end_excl = (cmp_end + timedelta(days=1)).strftime("%Y-%m-%d")

    base_year = period_end.year - 1  # 报告年-1 为已有车型基线（2026 报告 → 2025 已有车型）
    series_info = None
    if state_class == "series":
        # 代际归年以 business_definition.time_periods.{gen}.end 为准（不依赖数据首张开票时间）
        gen_year = _build_gen_year_map(bdef)
        if not gen_year:
            warnings.append("business_definition.time_periods 为空，无法按业务定义归年")
        undefined = [g for g in df_wl["series_group_logic"].dropna().unique()
                     if g not in gen_year and g != "其他"]
        if undefined:
            warnings.append(
                f"以下代际未在 business_definition.time_periods 登记，按存量车型（{base_year - 1}年及以前）处理: {sorted(undefined)}"
            )
        # 未登记代际以 0 表示"早于任何年份"，归入存量车型（≤ base_year-1）
        df_wl["_gen_year"] = df_wl["series_group_logic"].map(gen_year)
        df_wl.loc[df_wl["series_group_logic"] == "其他", "_gen_year"] = None
        df_wl["_gen_year"] = df_wl["_gen_year"].fillna(0)
        segs, _, series_info = _build_series_segments(df_wl, base_year, gen_year, as_of=cutoff)
    else:
        segments = _build_legacy_segments(df_wl, bdef, period_end.year)
        segs = [(name, fn, grp, None) for name, fn, grp in segments]

    dim_items = []
    overall_orders = 0
    overall_amount = 0.0

    # Price 视图（Vehicle Price / Total Vehicle Discount）用于 MSRP/权益价/折扣率三列；缺失时整列显示 "—"
    price_df = load_price_discount() if is_annual else None
    equity_baseline = {}
    if price_df is not None:
        # 订单 → 代际，用于反查 business_definition 上市日（禁止从数据推断上市时间）
        gen_by_order = df_wl.set_index("order_number")["series_group_logic"] \
            if "series_group_logic" in df_wl.columns else None
        equity_baseline = build_equity_baseline(price_df, gen_by_order, bdef)
        price_df = attach_equity_price(price_df, equity_baseline)
        if price_df is None:
            warnings.append("权益价基准构建失败（缺少 TVD 或产品信息），折扣三列显示为空")
        else:
            n_fb = sum(1 for v in equity_baseline.values() if v["method"] == "fallback")
            if n_fb:
                warnings.append(
                    f"{n_fb}/{len(equity_baseline)} 个产品的上市期价格数据缺失，"
                    "权益价退回「月内中位最小值」近似基准（可能高估 TVD 基准）"
                )
            # 同一产品名存在多个 MSRP → 上游产品名粒度不足（多个 SKU 共用名称）
            multi = sorted((k, v["msrp_variants"], v["msrp"])
                           for k, v in equity_baseline.items() if v.get("msrp_variants", 0) > 1)
            if multi:
                detail = "；".join(f"{k}({nv}档,取众数 {m:,.0f})" for k, nv, m in multi)
                warnings.append(
                    f"{len(multi)} 个产品名下存在多个 MSRP（说明上游产品名未区分 SKU），MSRP 已取产品内众数：{detail}"
                )
    if is_annual and price_df is None:
        warnings.append(
            f"未找到价格数据 {PRICE_DATA_CSV.name} 或字段不全，折扣率三列显示为空；"
            "请先下载 Tableau core_metric_observation/Price 视图到该路径"
        )

    for name, fn, group, band in segs:
        seg_df = df_wl if fn is None else fn(df_wl.copy())
        r_p = run_atp_operator(seg_df, p_start, p_end_excl)
        r_c = run_atp_operator(seg_df, c_start, c_end_excl)
        p_orders = r_p.get("total_orders", 0)
        p_price = r_p.get("avg_price")
        c_orders = r_c.get("total_orders", 0)
        c_price = r_c.get("avg_price")
        pn = round(float(p_price), 2) if p_price is not None else None
        cn = round(float(c_price), 2) if c_price is not None else None
        # MSRP / 权益价 / 应然价 / 折扣率（仅年度报告）：与 ATP 同口径（用户车 + 已锁单 + invoice_upload_time 落期）
        dstat = {"msrp": None, "equity": None, "expected": None, "rate": None,
                 "n": 0, "fallback_share": 0.0}
        if is_annual:
            dstat = _discount_for_segment(price_df, seg_df, p_start, p_end_excl)
        avg_msrp, avg_equity = dstat["msrp"], dstat["equity"]
        avg_expected, disc_rate = dstat["expected"], dstat["rate"]
        eq_fb_share = dstat["fallback_share"]
        # 兼容列：annual 下主窗口即 YTD；monthly 下另算当年累计
        if is_annual:
            y_orders, y_atp = p_orders, pn
        else:
            r_y = run_atp_operator(seg_df, f"{period_end.year}-01-01", p_end_excl)
            y_orders = r_y.get("total_orders", 0)
            y_atp = round(float(r_y["avg_price"]), 2) if r_y.get("avg_price") is not None else None
        dim_items.append({
            "value": name,
            "group": group,
            "band": band,
            "metrics": {
                # 主窗口（annual=本年至今；monthly=当月）
                "vehicle_count": p_orders,
                "avg_atp": pn,
                "compare_vehicle_count": c_orders,
                "compare_avg_atp": cn,
                # 兼容既有字段：monthly 下 ytd_* 仍为当年累计
                "ytd_vehicle_count": y_orders,
                "ytd_avg_atp": y_atp,
                "prev_month_vehicle_count": c_orders,
                "prev_month_avg_atp": cn,
                # MSRP / 权益价 / 应然价 / 折扣率（年度报告）
                "msrp_price": avg_msrp,
                "equity_price": avg_equity,
                "expected_price": avg_expected,
                "discount_rate": disc_rate,
                # 近似基准订单占比：>0.5 表示该分组多数订单的权益价基于回退估算
                "equity_fallback_share": round(float(eq_fb_share or 0.0), 4),
            },
        })
        dim_items[-1].setdefault("label", name.strip())
        if name == "所有车型" or name == "公司销售车型":
            overall_orders = p_orders
            overall_amount = float(p_price) * p_orders if p_price is not None else 0.0

    avg_atp = round(overall_amount / overall_orders, 2) if overall_orders > 0 else None
    total_amount = round(overall_amount, 2)
    vehicle_count = overall_orders

    # 分类口径下的口径核对：父行 vs 子行求和
    if state_class == "series":
        warnings.extend(_check_series_reconcile(dim_items, base_year))

    scope = {
        "data_source": str(ORDER_PARQUET),
        "report": report_name,
        "time_window": {"type": "ytd" if is_annual else tw_type, "report_period": t_label,
                        "period_start": p_start, "period_end": cutoff,
                        "compare_start": c_start, "compare_end": cmp_end.strftime("%Y-%m-%d"),
                        "data_cutoff": cutoff},
        "filters": {"series": args.series, "model": args.model, "state_class": state_class},
        "metric_definition": "ATP = mean(invoice_amount) WHERE order_type='用户车' AND invoice_amount > 0, 按 invoice_upload_time 落期；"
                             f"分类口径: {state_class}",
    }
    if state_class == "series":
        scope["filters"]["generation_year_baseline"] = f"\u003c={base_year} 为已有车型，{base_year + 1} 为新车型(含改款)"
        scope["filters"]["generation_year_rule"] = "代际年 = 该代际在订单数据中首张用户车开票所在年"
    result = {
        "summary": f"ATP {report_name} {period_label}: total_amount={total_amount:,.0f}, vehicle_count={vehicle_count}, avg_atp={avg_atp}",
        "metrics": {"total_amount": total_amount, "vehicle_count": vehicle_count, "avg_atp": avg_atp},
        "dimensions": [{"name": "series", "items": dim_items}],
    }
    if series_info is not None:
        result["generation_mapping"] = [
            {"body_type": si["body"], "series": si["series"],
             "legacy_generations": si["legacy"],
             "existing_generations": si["old"],
             "new_generations": si["new"],
             "labels": si["labels"]}
            for si in series_info
        ]

    artifacts = {}
    if args.output:
        out_dir = Path(args.output)
        if not out_dir.is_absolute():
            out_dir = _WS_ROOT / out_dir
    elif args.format == "html":
        out_dir = _WS_ROOT / "outputs" / "reports"
    else:
        out_dir = _WS_ROOT / "outputs" / "tables"
    # 月度经营 monitor → atp_<月>；年度经营 monitor → atp_annual_<年>（两版互不覆盖）
    prefix = "atp_annual_" if is_annual else "atp_"
    file_tag = str(period_end.year) if is_annual else t_label
    html_path = None
    csv_path = None
    if args.format in ("csv", "html") or args.output:
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.format == "html":
            html_path = out_dir / f"{prefix}{file_tag}.html"
            artifacts["html"] = str(html_path)
        if args.format == "csv":
            csv_path = out_dir / f"{prefix}{file_tag}.csv"
            artifacts["csv"] = str(csv_path)

    ctx = {"metric": "atp_price", "report": report_name, "report_period": t_label,
           "period_start": p_start, "period_end": cutoff, "compare_period": cmp_label,
           "state_class": state_class,
           "available_dimensions": ["series", "product_name", "generation", "body_type"],
           "top_entities": dim_items[:5] if dim_items else []}

    contract = build_success_contract(
        script="workspace/business_scripts/atp_price_report.py", command=cmd,
        scope=scope, result=result, artifacts=artifacts, followup_context=ctx,
        warnings=warnings,
    )

    if args.format in ("terminal", "html") or (args.format == "json" and args.output):
        if is_annual:
            _print_annual(period_label, p_start, cutoff, dim_items, cmp_label)
        else:
            _print_legacy(t_label, dim_items, vehicle_count, avg_atp)

    if args.format == "csv" and csv_path is not None:
        _write_csv(csv_path, dim_items, is_annual=is_annual)

    if args.format == "html" and html_path is not None:
        try:
            if is_annual:
                _render_html_annual(html_path, period_label, p_start, cutoff, dim_items, cmp_label,
                                    series_info or [], base_year, avg_atp, vehicle_count)
            else:
                _render_html(html_path, t_label, t_start, t_end, dim_items)
        except Exception as e:
            print(f"  HTML render failed: {e}", file=sys.stderr)

    if args.format == "json":
        if args.output:
            save_contract_json(contract, out_dir / f"{prefix}{file_tag}.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))


def _check_series_reconcile(items: list, base_year: int) -> list:
    """口径核对（用户车台数）：各"其中/系列"父段内，子行代际加总必须等于父行，且子行两两不重叠。

    注意：标签"其中：{y}年已有车型"在"公司销售车型/轿车/SUV"三个父段下重复出现，
    因此不能按标签建全局字典，必须按行序（父段后紧跟的缩进子行）分组。
    """
    warns = []
    groups = []
    cur = None
    for it in items:
        raw = it["value"]
        if raw.startswith("    "):
            if cur is not None:
                cur["children"].append(it)
        else:
            cur = {"parent": it, "children": []}
            groups.append(cur)
    for g in groups:
        kids = [c for c in g["children"] if c["value"].strip() != "/"]
        if not kids:
            continue
        par = g["parent"]["metrics"]["vehicle_count"]
        sm = sum(c["metrics"]["vehicle_count"] for c in kids)
        if sm != par:
            warns.append(f"口径核对差异：{g['parent']['label']}({par}) != 子行加总({sm})，"
                         f"差 {par - sm} 台（子行：{'、'.join(c['label'] for c in kids)}）")
        # 两级汇总行（如"X（剔除…）"）内部：其中项加总须等于该汇总行
        subs = [c for c in kids if c["value"].strip().startswith("其中")]
        if subs and "剔除" in g["parent"]["label"]:
            ssm = sum(c["metrics"]["vehicle_count"] for c in subs)
            if ssm != par:
                warns.append(f"口径核对差异：{g['parent']['label']}({par}) != 其下其中项加总({ssm})")
    return warns


def _write_csv(path: Path, items: list, is_annual: bool = False):
    import csv
    main_c, main_p, cmp_c, cmp_p = (
        ("本年至今用户车", "本年至今ATP", "上年同期用户车", "上年同期ATP") if is_annual
        else ("本月用户车", "本月ATP", "上月用户车", "上月ATP"))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        head = ["指标项", "车身形式", main_c, main_p, "当年累计用户车", "当年累计ATP", cmp_c, cmp_p]
        if is_annual:  # 年度报告补齐价格三列，与 HTML 对齐（折扣率按百分数输出，避免误读为金额）
            head += ["MSRP", "权益价", "折扣率%"]
        w.writerow(head)
        for it in items:
            m = it["metrics"]
            band = it.get("band") or ""
            bw = band.split("-")[0] if band else ""
            cohort = {"legacy": "存量(≤2024)", "old": "2025已有", "new": "2026新车型"}.get(bw, "")
            row = [it.get("label") or it["value"], BODY_TYPE_LABEL.get(bw, cohort), m["vehicle_count"],
                   m["avg_atp"], m["ytd_vehicle_count"], m["ytd_avg_atp"],
                   m["compare_vehicle_count"], m["compare_avg_atp"]]
            if is_annual:
                msrp_v, eq_v, rate_v = (m.get("msrp_price"), m.get("equity_price"),
                                        m.get("discount_rate"))
                row += [None if msrp_v is None else round(msrp_v, 2),
                        None if eq_v is None else round(eq_v, 2),
                        None if rate_v is None else round(rate_v * 100, 2)]
            w.writerow(row)
    print(f"  CSV: {path.resolve()}")


def _print_annual(period_label: str, p_start: str, cutoff: str, items: list, cmp_label: str):
    print(f"报告口径: 年度经营 monitor（年度口径）")
    print(f"主窗口: {period_label} {p_start} ~ {cutoff}（截止数据最新完整日）")
    print(f"对比窗口: {cmp_label}")
    print()
    labels = ["指标项", "本年至今用户车", "本年至今ATP", "同比ATP", "上年同期用户车", "上年同期ATP"]
    header = "  ".join(f"{l:>{w}}" for l, w in zip(labels, [26, 12, 12, 10, 13, 13]))
    print(header)
    print("-" * len(header))
    for item in items:
        m = item["metrics"]
        delta = _atp_delta(m["avg_atp"], m["compare_avg_atp"])
        print(f"{item['value']:26s} {_fmt_cnt(m['vehicle_count']):>12s} {_fmt_atp(m['avg_atp']):>12s} "
              f"{delta:>10s} {_fmt_cnt(m['compare_vehicle_count']):>13s} {_fmt_atp(m['compare_avg_atp']):>13s}")
    print()


def _print_legacy(month: str, items: list, total_orders: int, avg_atp: float):
    print(f"报告月份: {month}")
    print()
    labels = ["系别", "用户车锁单", "ATP", "累计用户车锁单", "累计ATP"]
    header = "  ".join(f"{l:>{w}}" for l, w in zip(labels, [30, 10, 10, 14, 10]))
    print(header)
    print("-" * len(header))
    for item in items:
        m = item["metrics"]
        m_ps = f"¥{m['avg_atp']:>,.0f}" if m["avg_atp"] is not None else "N/A"
        y_ps = f"¥{m['ytd_avg_atp']:>,.0f}" if m["ytd_avg_atp"] is not None else "N/A"
        print(f"{item['value']:30s} {m['vehicle_count']:>8d} {m_ps:>10s} {m['ytd_vehicle_count']:>10d} {y_ps:>10s}")
    print()


def _print_series(month: str, items: list, prev_month_label: str):
    print(f"报告月份: {month}（对比上月 {prev_month_label}；累计为当年 YTD）")
    print()
    labels = ["指标项", "本月用户车", "本月ATP", "环比ATP", "累计用户车", "累计ATP"]
    header = "  ".join(f"{l:>{w}}" for l, w in zip(labels, [28, 10, 11, 10, 12, 12]))
    print(header)
    print("-" * len(header))
    for item in items:
        m = item["metrics"]
        delta = _atp_delta(m["avg_atp"], m["compare_avg_atp"])
        print(f"{item['value']:28s} {_fmt_cnt(m['vehicle_count']):>10s} {_fmt_atp(m['avg_atp']):>11s} "
              f"{delta:>10s} {_fmt_cnt(m['ytd_vehicle_count']):>12s} {_fmt_atp(m['ytd_avg_atp']):>12s}")
    print()


def _atp_delta(cur, prev) -> str:
    if cur is None or prev is None or prev == 0:
        return "—"
    pct = (cur - prev) / prev * 100
    return f"{pct:+.1f}%"


def _atp_delta_cls(cur, prev) -> str:
    if cur is None or prev is None or prev == 0:
        return "delta-neutral"
    return "delta-positive" if cur >= prev else "delta-negative"


def _render_html(html_path: Path, t_label: str, t_start: datetime, t_end: datetime, items: list):
    start_display = t_start.strftime("%Y-%m-%d")
    end_display = t_end.strftime("%Y-%m-%d")
    bg_map = {"all": "#ffffff", "suv": "#f0f7ff", "sedan": "#fff8f0"}
    tbody = ""
    for item in items:
        bg = bg_map.get(item.get("group", "all"), "#ffffff")
        m = item["metrics"]
        m_ps = f"¥{m['avg_atp']:>,.0f}" if m["avg_atp"] is not None else "N/A"
        y_ps = f"¥{m['ytd_avg_atp']:>,.0f}" if m["ytd_avg_atp"] is not None else "N/A"
        tbody += (
            f"        <tr>"
            f"<td style=\"text-align:left;padding:6px 12px;border:1px solid #d0d5dd;background:{bg};\">{item['value']}</td>"
            f"<td style=\"text-align:right;padding:6px 12px;border:1px solid #d0d5dd;background:{bg};color:#888;\">{m['vehicle_count']:,}</td>"
            f"<td style=\"text-align:right;padding:6px 12px;border:1px solid #d0d5dd;background:{bg};\">{m_ps}</td>"
            f"<td style=\"text-align:right;padding:6px 12px;border:1px solid #d0d5dd;background:{bg};color:#888;\">{m['ytd_vehicle_count']:,}</td>"
            f"<td style=\"text-align:right;padding:6px 12px;border:1px solid #d0d5dd;background:{bg};\">{y_ps}</td>"
            f"</tr>\n"
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>ATP 月报 {t_label}</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:24px;">
<h2 style="margin:0 0 8px 0;">ATP 月报 — {t_label}</h2>
<p style="margin:0 0 4px 0;color:#555;font-size:14px;">月份窗口: {start_display} ~ {end_display}</p>
<p style="margin:0 0 16px 0;color:#555;font-size:14px;">累计窗口: {t_start.year}年1月~{t_start.month}月（{t_start.year}-01-01 ~ {end_display}）</p>
<table style="border-collapse:collapse;font-size:14px;width:auto;">
<thead>
<tr style="background:#1f2a3a;color:#fff;">
<th style="text-align:left;padding:8px 12px;border:1px solid #1f2a3a;">系别</th>
<th style="text-align:right;padding:8px 12px;border:1px solid #1f2a3a;color:#ccc;">用户车锁单</th>
<th style="text-align:right;padding:8px 12px;border:1px solid #1f2a3a;">ATP</th>
<th style="text-align:right;padding:8px 12px;border:1px solid #1f2a3a;color:#ccc;">累计用户车锁单</th>
<th style="text-align:right;padding:8px 12px;border:1px solid #1f2a3a;">累计ATP</th>
</tr>
</thead>
<tbody>
{tbody}</tbody>
</table>
</body></html>"""
    html_path.write_text(html, encoding="utf-8")
    print(f"  HTML: {html_path.resolve()}")


def _render_html_annual(html_path: Path, period_label: str, p_start: str, cutoff: str, items: list,
                        cmp_label: str, series_info: list, base_year: int, avg_atp, vehicle_count):
    """年度经营 monitor（年度口径）HTML 报告。

    主窗口 = 本年至今（当年 01-01 ~ 数据最新完整日）；对比窗口 = 上年同期。
    分类口径：公司销售车型 → {base_year}年已有车型 / {base_year+1}年新车型(含改款) → 轿车/SUV → 车系代际。
    """
    css_href = "file://" + str(REPORT_STYLE_CSS)
    year = int(cutoff[:4])

    def _row(it, level):
        m = it["metrics"]
        label = it.get("label") or it["value"]
        cls = {0: "section-row", 1: "excl-row", 2: "parent-row"}.get(level, "child-row")
        delta = _atp_delta(m["avg_atp"], m["compare_avg_atp"])
        dcls = _atp_delta_cls(m["avg_atp"], m["compare_avg_atp"])
        indent = "" if level == 0 else f" style=\"padding-left:{12 + level * 18}px;\""
        return (
            f"<tr class=\"{cls}\">"
            f"<td{indent}>{label}</td>"
            f"<td class=\"num\">{_fmt_cnt(m['vehicle_count'])}</td>"
            f"<td class=\"num\">{_fmt_atp(m['avg_atp'])}</td>"
            f"<td class=\"num {dcls}\">{delta}</td>"
            f"<td class=\"num\">{_fmt_cnt(m['compare_vehicle_count'])}</td>"
            f"<td class=\"num\">{_fmt_atp(m['compare_avg_atp'])}</td>"
            f"<td class=\"num\">{_fmt_yuan(m.get('msrp_price'))}</td>"
            f"<td class=\"num\">{_fmt_yuan(m.get('equity_price'))}"
            f"{'*' if (m.get('equity_fallback_share') or 0) > 0.5 else ''}</td>"
            f"<td class=\"num\">{_fmt_rate(m.get('discount_rate'))}</td>"
            f"</tr>"
        )

    def level_of(it):
        raw = it["value"]
        if raw.startswith("    /"):
            return 2
        if raw.startswith("    "):
            return 3
        if "剔除" in raw and not raw.strip().startswith("其中"):
            return 1          # ② 同名校验行：父行下的二级汇总
        if raw.strip().startswith("其中"):
            return 2
        return 0

    tbody = "\n".join(_row(it, level_of(it)) for it in items)

    by_label = {it["label"]: it for it in items}
    p = next((it["metrics"] for it in items if it["value"].strip().startswith("公司销售车型")), {})
    new_lab = next((k for k in by_label if "年新车型" in k), None)
    old_it = by_label.get(f"其中：{base_year}年已有车型", {}).get("metrics", {})
    new_it = by_label.get(new_lab, {}).get("metrics", {}) if new_lab else {}
    gap = (new_it.get("avg_atp", 0) - old_it.get("avg_atp", 0)) if (new_it.get("avg_atp") and old_it.get("avg_atp")) else None
    yoy = _atp_delta(p.get("avg_atp"), p.get("compare_avg_atp"))
    yoy_n = (p.get("vehicle_count", 0) - p.get("compare_vehicle_count", 0)) if p.get("vehicle_count") is not None and p.get("compare_vehicle_count") is not None else None
    yoy_txt = f"台数同比 {yoy_n:+,} 台" if yoy_n is not None else "上年同期无数据"

    cards = [
        (f"{period_label} 公司销售车型 ATP", _fmt_atp(p.get("avg_atp")),
         f"用户车 {_fmt_cnt(p.get('vehicle_count'))} 台 · {yoy_txt}"),
        (f"同比 ATP", yoy, f"对比 {cmp_label}"),
        (f"其中：{base_year}年已有车型", _fmt_atp(old_it.get("avg_atp")),
         f"{_fmt_cnt(old_it.get('vehicle_count'))} 台 · 占比 {_pct(old_it.get('vehicle_count'), p.get('vehicle_count'))}"),
        (f"其中：{base_year + 1}年新车型(含改款)", _fmt_atp(new_it.get("avg_atp")),
         f"{_fmt_cnt(new_it.get('vehicle_count'))} 台 · 占比 {_pct(new_it.get('vehicle_count'), p.get('vehicle_count'))}"),
    ]
    cards_html = "\n".join(
        f"<div class=\"summary-card\"><div class=\"summary-value\">{v}</div>"
        f"<div class=\"summary-label\">{l}</div><div class=\"summary-hint\">{h}</div></div>"
        for l, v, h in cards
    )

    mapping_rows = "".join(
        f"<tr><td>{BODY_TYPE_LABEL.get(si['body'], si['body'])}</td><td>{si['series']}</td>"
        f"<td class=\"num\">{si['legacy_s']}</td>"
        f"<td class=\"num\">{si['old_s']}</td>"
        f"<td class=\"num\">{si['new_s']}</td></tr>"
        for si in series_info
    )

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>年度经营 monitor · ATP（公司销售车型分类） {year}</title>
  <link rel="stylesheet" href="{css_href}" />
  <style>
    .excl-row td {{ font-weight: 600; background: var(--zh-table-section); }}
    .parent-row td {{ font-weight: 500; }}
    .child-row td {{ color: var(--zh-text); }}
    .child-row td:first-child {{ color: var(--zh-muted); }}
    /* 对比期三列（同比 ATP / 上年同期用户车 / 上年同期ATP）统一不加粗，仅保留涨跌色 */
    .atp-table tbody tr td:nth-child(4),
    .atp-table tbody tr td:nth-child(5),
    .atp-table tbody tr td:nth-child(6) {{ font-weight: 400; }}
    .keyline {{ color: var(--zh-muted); font-size: 13px; }}
  </style>
</head>
<body class="report-page">
  <header>
    <div class="container">
      <div class="brand">
        <img class="brand-avatar" src="../../assets/brand/raccoon_avatar_light.png" alt="" onerror="this.style.display='none'" />
        <span class="brand-name">Raccoon Research</span>
      </div>
      <span class="header-meta">年度经营 monitor · {year} 年至今</span>
    </div>
  </header>

  <main class="container">
    <section class="hero">
      <h1>年度经营 monitor — ATP 分车型（{year} 年至今）</h1>
      <p>主窗口：{period_label}（{p_start} ~ {cutoff}，截止数据最新完整日）；对比窗口：{cmp_label}。
         分类口径：公司销售车型 → {base_year}年已有车型 / {base_year + 1}年新车型(含改款) → 轿车/SUV → 车系代际（M=车型代际，T=改款）；{base_year - 1} 年及以前存量车型单列。</p>
    </section>

    <div class="summary-grid">
      {cards_html}
    </div>

    <section class="report-section">
      <h2 class="section-title">ATP 分车型（本年至今）</h2>
      <p class="section-note">ATP = 用户车开票均价（invoice_amount 均值，按 invoice_upload_time 落期）；M/T 为代际标签，"LS6 M2/T1" 表示已有代际 M2 / 新代际 T1。<br/>
         <strong>MSRP</strong> = 产品内 <code>Vehicle Price</code> 众数（<strong>官方车价，不含选装</strong>；同一产品名下多档时取众数并告警）；
         <strong>权益价</strong> = MSRP − <strong>上市期 TVD 基准</strong>（见下）；
         <strong>折扣率</strong> = 1 − Σ开票价 / Σ<strong>应然价</strong>（金额加权），其中应然价 = 权益价 + 选装挂牌。
         三者仅统计已开票用户车，数据源：Tableau Price 视图。
         <br/><span style="color:var(--zh-muted);">权益价算法（固定口径）：MSRP 在产品内恒定，而 <code>Total Vehicle Discount</code>（TVD）随车型上市时间单调增长
         （实测月增约 2,000~3,300 元/月，代际内趋势相关 0.72~0.98），故权益价锚定<strong>上市期</strong>的 TVD，而非当期 TVD：
         ① 上市日取 <code>business_definition.time_periods.{{gen}}.end</code>，上市后 60 天内订单 ≥30 单 → 用该窗口中位数（精确）；
         ② 否则首月订单 ≥30 单 → 用首月中位数（精确）；
         ③ 否则退回「月内中位（月样本 ≥10 单）的历史最小值」作近似基准，并在权益价后标 <code>*</code>。
         <br/>已知阶段变化（LS8）：<strong>2026-06-16 之前</strong>「奢华智选包」9,800 为实收项（净支付中位 +9,800）；
         <strong>2026-06-16 起</strong>该包不再单独加价（净支付中位降至 0，7 月起进一步转为负值）。故 LS8 的「选装实付」均值被前后两段摊薄，
         该车系折扣率应结合其选装挂牌（约 2.3~3.5 万）一并理解。
         <br/>折扣率口径：分母用「应然价 = 权益价 + 选装挂牌」，分子分母都含选装、量纲一致。
         不用「开票价 − 选装价」作分子，是因为<strong>选装的收费/赠送策略因车型和阶段而异</strong>——LS6 的车漆+轮毂选装基本全赠送，
         而 LS8 的「奢华智选包」9,800 在 2026-06-16 之前为实收项、之后不再单独加价；全额扣除选装价会把赠送选装误当成让利，抬高折扣率。
         <br/>口径提示：<code>Vehicle Price</code> 即 MSRP（已用选装表验证：<code>origin_amount − Vehicle Price</code> 与配置表选装价吻合 99.2%）；
         TVD 仅含车价维度优惠，<code>vehicle_discount_amount</code> = TVD + 选装优惠。Price 视图自 2026-01 起完整，故三列只给本年至今、不做同比。</span></p>
      <table class="report-table atp-table">
        <thead>
          <tr>
            <th style="text-align:left;">指标项</th>
            <th>本年至今用户车</th>
            <th>本年至今ATP</th>
            <th>同比 ATP</th>
            <th>上年同期用户车</th>
            <th>上年同期ATP</th>
            <th>MSRP</th>
            <th>权益价</th>
            <th>折扣率</th>
          </tr>
        </thead>
        <tbody>
{tbody}
        </tbody>
      </table>
    </section>

    <section class="report-section">
      <h2 class="section-title">车型代际映射</h2>
      <p class="section-note">上市年份取自 <code>business_definition.time_periods.{{gen}}.end</code>（正式上市日）。结构：<strong>父行（全量）</strong> → <strong>同名（剔除 {base_year - 1} 年及以前存量车型）</strong> → 其中：{base_year}年已有车型 / {base_year + 1}年新车型(含改款) / {base_year - 1}年及以前存量车型。全量 = 剔除后 + 存量。</p>
      <table class="report-table">
        <thead><tr><th style="text-align:left;">车身形式</th><th style="text-align:left;">车系</th><th>{base_year - 1}年及以前存量</th><th>{base_year}年已有车型</th><th>{base_year + 1}年新车型(含改款)</th></tr></thead>
        <tbody>{mapping_rows}</tbody>
      </table>
    </section>
  </main>

  <footer>
    <img class="brand-sig" src="../../assets/brand/zihao_signature_transparent.png" alt="Raccoon Research" onerror="this.style.display='none'" />
    <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
  </footer>
</body></html>"""
    html_path.write_text(html, encoding="utf-8")
    print(f"  HTML: {html_path.resolve()}")


def _pct(a, b) -> str:
    if not b or a is None:
        return "—"
    return f"{a / b * 100:.1f}%"


if __name__ == "__main__":
    main()
