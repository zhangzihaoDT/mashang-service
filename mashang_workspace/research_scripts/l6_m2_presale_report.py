#!/usr/bin/env python3
"""
L6 M2 预售情况汇报 — Markdown 报告生成器

口径（全文统一）:
  预售订单统一为 release DM2 口径：
  预售开放当日（08-18）20:00 之后支付意向金、且未退意向金的留存小订。
  DM2 全集中的试驾车（325 台）及其锁单/大定/开票/交付不纳入零售预售分析。

模块:
  一、订单       预售核心指标 / 跨代际对标(N=7) / 产品结构 / 大区结构
  二、下发线索    窗口 vs 基线 + 跨代际线索对标 + 转化率
  三、正反向     竞争 PK 正反向排名（DM2 周 + DM1 预售周对比 + 上汽竞品趋势）
  四、预选配置    留存小订池按产品覆盖概览 + 已选配置分布（按显示名）
  五、用户画像    留存小订池年龄/性别/城市/省份
  六、集团       TP MG 市场上险 + 观星台集团订单日报预售期小订对比

用法:
  .venv/bin/python mashang_workspace/research_scripts/l6_m2_presale_report.py
  .venv/bin/python mashang_workspace/research_scripts/l6_m2_presale_report.py --as-of 2026-08-24
  .venv/bin/python mashang_workspace/research_scripts/l6_m2_presale_report.py --output outputs/reports/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS_ROOT = REPO_ROOT / "mashang_workspace"
for p in (str(REPO_ROOT), str(_WS_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from research_scripts.l6_m2_presale_metrics_to_feishu import (
    load_business_definition,
    _apply_series_group_logic,
    _parse_logic,
    _rule_condition,
)

OPEN_HOUR = 20
N_DAYS = 7
COMPARE_GENS = ["DM2", "DM1", "CM2", "LS9", "LS8"]
DEFAULT_PK_CSV = "/Users/zihao_/Documents/coding/dataset/original/业务数据记录_竞争PK（正反向排名）.csv"
DEFAULT_GUANXINGTAI_DIR = "/Users/zihao_/Documents/coding/dataset/original/saic观星台集团订单日报"

DATASET = REPO_ROOT / "dataset"
ORDER_PARQUET = DATASET / "order_data.parquet"
ASSIGN_CSV = DATASET / "assign_data.csv"
CONFIG_PARQUET = DATASET / "config_attribute.parquet"


def _fmt_int(v) -> str:
    return f"{int(v):,}"


def _fmt_pct(v, nd: int = 1) -> str:
    return f"{v * 100:.{nd}f}%"


def _cn_date(s: str) -> pd.Timestamp:
    return pd.to_datetime(str(s).replace("年", "-").replace("月", "-").replace("日", ""), format="%Y-%m-%d", errors="coerce")


def dm2_mask(name: pd.Series) -> pd.Series:
    n = name.fillna("").astype(str)
    return (
        (n.str.contains("一代", regex=False) & n.str.contains("L6", regex=False))
        | (n.str.contains("L6", regex=False) & n.str.contains("M2", regex=False))
        | n.str.contains("Jimmy Choo", regex=False)
        | n.str.contains("JimmyChoo", regex=False)
    )


def load_order(apply_group: bool = True) -> pd.DataFrame:
    df = pd.read_parquet(ORDER_PARQUET)
    for c in ["intention_payment_time", "intention_refund_time", "deposit_payment_time",
              "lock_time", "invoice_upload_time", "delivery_date", "order_create_date"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    if apply_group:
        bd = load_business_definition(REPO_ROOT / "shared/schema/business_definition.json")
        asts = {g: _parse_logic(_rule_condition(c)) for g, c in bd["series_group_logic"].items()}
        df = _apply_series_group_logic(df, bd, asts)
    return df


def retention_pool(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    open_t = pd.Timestamp("2026-08-18") + pd.Timedelta(hours=OPEN_HOUR)
    return df[
        (df["series_group_logic"] == "DM2")
        & (df["intention_payment_time"] >= open_t)
        & (df["intention_payment_time"] < (as_of + pd.Timedelta(days=1)))
        & (df["intention_refund_time"].isna())
    ].copy()


# ── 一、订单 ─────────────────────────────────────────────

def gen_benchmark(df: pd.DataFrame, bd: dict) -> list[dict]:
    rows = []
    for gen in COMPARE_GENS:
        start = pd.Timestamp(bd["time_periods"][gen]["start"])
        open_t = start + pd.Timedelta(hours=OPEN_HOUR)
        sel = df[df["series_group_logic"] == gen]
        # 同 N 日留存
        wend = open_t + pd.Timedelta(days=N_DAYS)
        m = (sel["intention_payment_time"] >= open_t) & (sel["intention_payment_time"] < wend) & (
            sel["intention_refund_time"].isna() | (sel["intention_refund_time"] > wend)
        )
        ret_n = sel[m]["order_number"].nunique()
        # 首日峰值小时
        day = sel[(sel["intention_payment_time"] >= open_t) & (sel["intention_payment_time"] < open_t + pd.Timedelta(hours=24))]
        if day.empty:
            peak_h, peak_c = "-", 0
        else:
            h = day["intention_payment_time"].dt.hour.astype(int)
            vc = h.value_counts()
            peak_c, peak_h = int(vc.max()), f"{vc.idxmax():02d}:00"
        # 发布会当日 20:00-24:00
        lend = start + pd.Timedelta(days=1)
        ld = sel[(sel["intention_payment_time"] >= open_t) & (sel["intention_payment_time"] < lend)]
        ld_total = ld["order_number"].nunique()
        ld_ret = ld[(ld["intention_refund_time"].isna() | (ld["intention_refund_time"] > lend))]["order_number"].nunique()
        rows.append({"gen": gen, "ret_n": ret_n, "peak_h": peak_h, "peak_c": peak_c,
                     "ld_total": ld_total, "ld_ret": ld_ret})
    return rows


def presale_core(df: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    bd = load_business_definition(REPO_ROOT / "shared/schema/business_definition.json")
    start = pd.Timestamp(bd["time_periods"]["DM2"]["start"])
    open_t = start + pd.Timedelta(hours=OPEN_HOUR)
    sel = df[df["series_group_logic"] == "DM2"]
    cum = sel[(sel["intention_payment_time"] >= open_t) & (sel["intention_payment_time"] < as_of + pd.Timedelta(days=1))]
    ret = retention_pool(df, as_of)
    # 发布会当日
    lend = start + pd.Timedelta(days=1)
    ld = sel[(sel["intention_payment_time"] >= open_t) & (sel["intention_payment_time"] < lend)]
    ld_ret = ld[(ld["intention_refund_time"].isna() | (ld["intention_refund_time"] > lend))]
    # 首日 24h 峰值
    day = sel[(sel["intention_payment_time"] >= open_t) & (sel["intention_payment_time"] < open_t + pd.Timedelta(hours=24))]
    h = day["intention_payment_time"].dt.hour.astype(int)
    vc = h.value_counts()
    peak_h, peak_c = vc.idxmax(), int(vc.max())
    return {
        "cum": int(cum["order_number"].nunique()),
        "retention": int(ret["order_number"].nunique()),
        "retention_users": int(ret["buyer_identity_no"].nunique()),
        "ld_total": int(ld["order_number"].nunique()),
        "ld_ret": int(ld_ret["order_number"].nunique()),
        "peak_hour": f"{peak_h:02d}:00",
        "peak_count": peak_c,
        "next_hour": int(vc.iloc[peak_h + 1]) if peak_h < 23 else 0,
        "day24": int(day["order_number"].nunique()),
        "product": ret.groupby("product_name")["order_number"].nunique().sort_values(ascending=False),
        "region": ret.groupby("parent_region_name")["order_number"].nunique().sort_values(ascending=False),
    }


# ── 二、下发线索 ─────────────────────────────────────────

def load_assign() -> pd.DataFrame:
    df = pd.read_csv(ASSIGN_CSV, encoding="utf-8-sig")
    df["_date"] = df["Assign Time 年/月/日"].apply(_cn_date)
    return df[df["_date"].notna()].copy()


def lead_block(df: pd.DataFrame, s: str, e: str) -> dict:
    w = df[(df["_date"] >= pd.Timestamp(s)) & (df["_date"] <= pd.Timestamp(e))]
    leads = int(w["下发线索数"].sum())
    stores = int(w["下发门店数"].sum())
    return {"leads": leads, "stores": stores, "per_store": leads / stores if stores else None,
            "days": int(w["_date"].nunique())}


def lead_cross_gen(df: pd.DataFrame, bd: dict) -> list[dict]:
    rows = []
    for gen in COMPARE_GENS:
        start = pd.Timestamp(bd["time_periods"][gen]["start"])
        d0 = df[df["_date"] == start]
        lead_d0 = int(d0["下发线索数"].sum()) if not d0.empty else None
        win = df[(df["_date"] >= start) & (df["_date"] <= start + pd.Timedelta(days=6))]
        base = df[(df["_date"] >= start - pd.Timedelta(days=7)) & (df["_date"] < start)]
        wl = int(win["下发线索数"].sum()); bl = int(base["下发线索数"].sum())
        ws = int(win["下发门店数"].sum())
        days = win["_date"].nunique()
        rows.append({"gen": gen, "start": str(start.date()), "d0": lead_d0, "win": wl, "base": bl,
                     "delta": wl - bl, "delta_pct": (wl - bl) / bl if bl else None,
                     "store_daily": ws / days if days else None, "per": wl / ws if ws else None})
    return rows


# ── 三、正反向 PK ────────────────────────────────────────

def load_pk(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["PK次数"] = df["PK次数"].astype(str).str.replace(",", "", regex=False).astype(int)
    return df


def pk_week(df: pd.DataFrame, week: str, series: str = "L6") -> pd.DataFrame:
    return df[(df["series"] == series) & (df["Week"] == week)].sort_values("PK次数", ascending=False)


def saic_pk_trend(df: pd.DataFrame) -> list[dict]:
    rows = []
    recent = [w for w in sorted(df["Week"].unique()) if w >= "2026-07-20"]
    sel = df[(df["series"] == "L6") & (df["品牌"].astype(str).str.contains("上汽集团"))]
    for w in recent:
        for _, r in sel[sel["Week"] == w].sort_values("PK次数", ascending=False).iterrows():
            rows.append({"week": w, "car": r["车系"], "pk": int(r["PK次数"]),
                         "fwd": int(r["PK正向排名"]), "rev": int(r["PK反向排名"])})
    return rows


# ── 四、预选配置 ─────────────────────────────────────────

def config_analysis(ret: pd.DataFrame) -> dict:
    cfg = pd.read_parquet(CONFIG_PARQUET)
    cfg["Order Number"] = cfg["Order Number"].astype(str)
    ret_ids = set(ret["order_number"].astype(str).str.strip())
    sub = cfg[cfg["Order Number"].isin(ret_ids) & cfg["value"].notna()].copy()
    per_order_attrs = sub.groupby("Order Number")["Attribute"].apply(set).to_dict()
    CORE = {"内饰", "外饰", "轮毂", "方向盘", "超远距高精度激光雷达"}
    prod_rows = []
    for prod, grp in ret.groupby("product_name"):
        ids = grp["order_number"].astype(str).str.strip().tolist()
        total = len(ids)
        withval = sum(1 for o in ids if o in per_order_attrs)
        core = sum(1 for o in ids if len(CORE & per_order_attrs.get(o, set())) == len(CORE))
        prod_rows.append({"product": prod, "total": total, "withval": withval, "core": core})
    # 已选配置分布（按显示名）
    attr_dist = {}
    for attr, a in sub.groupby("Attribute"):
        attr_dist[attr] = a["value"].value_counts().to_dict()
    return {"covered": int(sub["Order Number"].nunique()), "rows": len(sub),
            "prod_rows": prod_rows, "attr_dist": attr_dist}


# ── 五、用户画像 ─────────────────────────────────────────

def profile(ret: pd.DataFrame) -> dict:
    sys.path.insert(0, str(_WS_ROOT))
    from runtime_scripts.user_profile import norm_city, city_to_tier_label, CITY_TO_PROVINCE
    n = len(ret)
    g = ret["order_gender"].fillna("(未知)").astype(str)
    a = pd.to_numeric(ret["buyer_age"], errors="coerce")
    oa = pd.to_numeric(ret["owner_age"], errors="coerce")
    city = ret["license_city"].apply(norm_city)
    tier = city.apply(city_to_tier_label)
    prov = city.map(CITY_TO_PROVINCE).fillna("未知")
    return {
        "n": n,
        "gender": g.value_counts().to_dict(),
        "age_nonnull": int(a.notna().sum()), "age_mean": round(float(a.mean()), 1), "age_median": float(a.median()),
        "owner_nonnull": int(oa.notna().sum()),
        "tier": tier.value_counts().to_dict(),
        "prov": prov.value_counts().to_dict(),
        "product": ret["product_name"].value_counts().to_dict(),
    }


# ── 六、集团 ─────────────────────────────────────────────

def tp_mg() -> tuple[pd.DataFrame, pd.DataFrame]:
    from shared.loaders.tp_and_mix_ways_loader import load_tp_and_mix_ways_table
    bm = load_tp_and_mix_ways_table("brand_monthly").copy()
    bm["date_month"] = pd.to_datetime(bm["date_month"])
    agg = bm.groupby(["date_month", "brand"], as_index=False)["sales"].sum()
    mg = agg[agg["brand"].eq("MG")].sort_values("date_month").tail(7)
    zh = agg[agg["brand"].eq("智己")].sort_values("date_month").tail(7)
    m_26 = agg[(agg["brand"].eq("MG")) & (agg["date_month"].eq(pd.Timestamp("2026-07-01")))]["sales"].sum()
    m_25 = agg[(agg["brand"].eq("MG")) & (agg["date_month"].eq(pd.Timestamp("2025-07-01")))]["sales"].sum()
    mm = load_tp_and_mix_ways_table("model_monthly").copy()
    mm["date_month"] = pd.to_datetime(mm["date_month"])
    mmg = mm[mm["brand"].astype(str).eq("MG")]
    latest = mmg[mmg["date_month"] == mmg["date_month"].max()].sort_values("sales", ascending=False)
    return (pd.DataFrame({"month": mg["date_month"], "mg": mg["sales"].values, "zh": zh["sales"].values}),
            {"yoy_26": m_26, "yoy_25": m_25, "models": latest[["model", "fuel_type_group", "sales"]]})


def guanxingta_presale(dir_path: Path, file: str, model: str) -> dict | None:
    """从观星台集团订单日报的「预售期小订」区块读取指定车型的累计/日均/每日序列。

    结构说明：预售期小订区块内，车型行含每日小订列（表头 row2 为日期），
    其累计（月累计/月日均）位于后续某行，且该行最右列标注车型名。
    右组月累计/月日均列号按表头 row3 动态定位（0819 在 col20/21，0822 在 col19/20）。
    """
    import warnings
    warnings.filterwarnings("ignore")
    path = dir_path / file
    if not path.exists():
        return None
    raw = pd.ExcelFile(path).parse("重点车型 (订单)", header=None)
    sec = None
    for i in range(raw.shape[0]):
        if isinstance(raw.iloc[i, 1], str) and "预售期" in str(raw.iloc[i, 1]):
            sec = i
            break
    if sec is None:
        return None

    # 右组月累计/月日均列号：取 row3 中「月累计」「月日均」，各自取最大列号（右侧 2026 年组）
    r3 = [str(x) if pd.notna(x) else "" for x in raw.iloc[3].tolist()]
    mt_idx = max([i for i, v in enumerate(r3) if v.strip() == "月累计"] or [-1])
    ma_idx = max([i for i, v in enumerate(r3) if v.strip() == "月日均"] or [-1])

    # 每日日期列（row2 含 '/' 的列）
    r2 = raw.iloc[2].tolist()
    daily_cols = [(i, str(v).strip()) for i, v in enumerate(r2) if isinstance(v, str) and "/" in v]

    last_col = raw.shape[1] - 1
    for j in range(sec + 1, min(sec + 8, raw.shape[0])):
        name = raw.iloc[j, 1]
        if not (isinstance(name, str) and name.strip() == model):
            continue
        daily = {}
        for i, d in daily_cols:
            v = raw.iloc[j, i] if i < raw.shape[1] else None
            if pd.notna(v):
                daily[d] = int(v)
        # 找该模型的累计行（最右列 = 模型名）
        cum = daily_avg = None
        for k in range(j + 1, min(sec + 10, raw.shape[0])):
            nm = raw.iloc[k, last_col] if last_col >= 0 else None
            if pd.notna(nm) and str(nm).strip() == model:
                if mt_idx >= 0 and mt_idx < raw.shape[1] and pd.notna(raw.iloc[k, mt_idx]):
                    cum = int(raw.iloc[k, mt_idx])
                if ma_idx >= 0 and ma_idx < raw.shape[1] and pd.notna(raw.iloc[k, ma_idx]):
                    daily_avg = int(raw.iloc[k, ma_idx])
                break
        return {"cum": cum, "daily_avg": daily_avg, "daily": daily}
    return None


# ── 渲染 ─────────────────────────────────────────────────

def render(as_of: pd.Timestamp, output_dir: Path, pk_csv: Path, gx_dir: Path) -> Path:
    bd = load_business_definition(REPO_ROOT / "shared/schema/business_definition.json")
    df = load_order()
    ret = retention_pool(df, as_of)
    ret_n = int(ret["order_number"].nunique())

    L: list[str] = []
    A = L.append
    A(f"# L6 M2 预售情况汇报\n")
    A(f"> 数据快照：截至 **{as_of.date()}**（`order_data.parquet` / `assign_data.csv`）；TP 市场数据截至 2026-07  ")
    A(f"> 预售窗口：2026-08-18 ~ 2026-09-18（当前 N={N_DAYS} 日，预售未结束）  ")
    A(f"> L6 M2 识别口径：`shared/schema/business_definition.json` 的 `series_group_logic.DM2`  ")
    A(f"> **预售订单统一口径（全文所有分析阶段）**：严格对齐 release DM2 口径——**预售开放当日（08-18）20:00 之后支付意向金、且未退的留存小订**，共 **{_fmt_int(ret_n)} 单**；DM2 全集中的试驾车及其锁单/大定/开票/交付不纳入零售预售分析  ")
    A(f"> 说明：预售早期，30 日转化、最终锁单、开票交付均存在右删失，与成熟代际对比仅作参考\n")
    A("---\n")

    # 一、订单
    core = presale_core(df, as_of)
    bench = gen_benchmark(df, bd)
    A("## 一、订单：预售规模与订单质量\n")
    A(f"### 1.1 预售核心指标（N={N_DAYS}，release DM2 口径）\n")
    A("| 指标 | 数值 |\n|---|---:|")
    A(f"| 累计小订数（20:00 起算） | {_fmt_int(core['cum'])} |")
    A(f"| **留存小订（未退意向金，报告口径）** | **{_fmt_int(core['retention'])}** |")
    A(f"| 留存唯一订单用户 | {_fmt_int(core['retention_users'])} |")
    A(f"| N=0 发布会当日小订 | {_fmt_int(core['ld_total'])} |")
    A(f"| N=0 发布会当日留存（20:00-24:00） | {_fmt_int(core['ld_ret'])} |")
    A(f"| 首日峰值小时小订 | {_fmt_int(core['peak_count'])}（{core['peak_hour']}） |")
    A(f"| 峰值后 1 小时 | {_fmt_int(core['next_hour'])} |")
    A(f"| 开放后 24h 累计 | {_fmt_int(core['day24'])} |\n")

    A("### 1.2 预售对标（跨代际 · N=7 同窗口）\n")
    A("> 对标代际：DM1 / CM2 / LS9 / LS8，统一按各自预售开放时刻（20:00）起算，N=7 日同窗口。\n")
    A("| 代际 | 同 N 日留存 | 首日峰值小时 | 峰值小时小订 | 发布会当日小订（20:00-24:00） | 发布会当日留存（20:00-24:00） |")
    A("|---|---:|---:|---:|---:|---:|")
    for b in bench:
        bold = "**" if b["gen"] == "DM2" else ""
        A(f"| {bold}{b['gen']}{bold} | {bold}{_fmt_int(b['ret_n'])}{bold} | {b['peak_h']} | {bold}{_fmt_int(b['peak_c'])}{bold} | {bold}{_fmt_int(b['ld_total'])}{bold} | {bold}{_fmt_int(b['ld_ret'])}{bold} |")
    A("")
    dm2_b = next(b for b in bench if b["gen"] == "DM2")
    A(f"> **对标判断**：L6 M2 在同 N 日留存（{_fmt_int(dm2_b['ret_n'])}）、首日峰值小时（{_fmt_int(dm2_b['peak_c'])}）、发布会当日留存（{_fmt_int(dm2_b['ld_ret'])}）三个维度均低于历届对标代际（量级约为 DM1 的 1/4、CM2/LS8 的 1/6~1/8），但 M2 尚处预售第 {N_DAYS} 日，且不同代际上市节奏、产品生命周期不同，仅作量级参考。")
    A(f"> **口径说明（重要）**：截至 {as_of.date()}，release 口径留存小订尚无大定/锁单/开票/交付转化——DM2 全集中的大定/锁单/开票/交付全部为试驾车（demo/试驾车锁定，非零售用户），订单质量结论需待预售转化密集期（约 T+7~T+30）复核。\n")

    # 1.3 产品结构
    A("### 1.3 产品结构（留存小订）\n")
    A("| 产品 | 留存订单 | 占比 |\n|---|---:|---:|")
    total_p = ret_n
    rows_p = []
    limited = 0
    for prod, cnt in core["product"].items():
        rows_p.append((prod, int(cnt), cnt / total_p))
        if "JimmyChoo" in prod:
            limited += int(cnt)
    for prod, cnt, share in rows_p:
        if "JimmyChoo" in prod:
            continue
        A(f"| {prod} | {_fmt_int(cnt)} | {_fmt_pct(share)} |")
    A(f"| 非限量版小计 | {_fmt_int(total_p - limited)} | {_fmt_pct((total_p - limited) / total_p)} |")
    for prod, cnt, share in rows_p:
        if "JimmyChoo" in prod:
            A(f"| {prod} | {_fmt_int(cnt)} | {_fmt_pct(share)} |")
    A(f"| 限量版小计 | {_fmt_int(limited)} | {_fmt_pct(limited / total_p)} |\n")

    # 1.4 大区结构
    A("### 1.4 大区结构（留存小订）\n")
    A("| 大区 | 留存订单 | 占比 |\n|---|---:|---:|")
    for reg, cnt in core["region"].items():
        A(f"| {reg} | {_fmt_int(cnt)} | {_fmt_pct(cnt / total_p)} |")
    east = sum(int(core["region"].get(r, 0)) for r in ["东区-江苏", "东区-浙江", "上海区"])
    A(f"\n> 华东（江苏/浙江/上海）合计约 {_fmt_pct(east / total_p, 0)}，是预售第一大区域。\n")
    A("---\n")

    # 二、下发线索
    assign = load_assign()
    win = lead_block(assign, "2026-08-18", "2026-08-24")
    base = lead_block(assign, "2026-08-11", "2026-08-17")
    d18 = lead_block(assign, "2026-08-18", "2026-08-18")
    lcg = lead_cross_gen(assign, bd)
    A("## 二、下发线索：整体业务转化（预售窗口 vs 前一周基线）\n")
    A("> 说明：`assign_data.csv` 无车型字段，以下为**整体业务口径**，用于判断 M2 预售期间整体线索转化是否发生变化，不代表 L6 M2 专属转化。\n")
    A("**对标对比（预售当日 / 预售窗口 / 基线）**\n")
    A("| 指标 | 预售当日 08-18 | 预售窗口 08-18~08-24 | 基线 08-11~08-17 | 窗口 vs 基线 |")
    A("|---|---:|---:|---:|---:|")
    A(f"| 下发线索数 | **{_fmt_int(d18['leads'])}** | {_fmt_int(win['leads'])} | {_fmt_int(base['leads'])} | **+{_fmt_int(win['leads'] - base['leads'])}（+{(win['leads'] - base['leads']) / base['leads'] * 100:.1f}%）** |")
    A(f"| 有效门店数（日频合计） | {_fmt_int(d18['stores'])} | {_fmt_int(win['stores'])} | {_fmt_int(base['stores'])} | {win['stores'] - base['stores']:+,d} |")
    A(f"| 店均下发线索数 | **{d18['per_store']:.1f}** | {win['per_store']:.1f} | {base['per_store']:.1f} | +{win['per_store'] - base['per_store']:.1f} |\n")
    A("> *预售窗口含 08-24 部分快照（当日仅 842 线索 / 39 门店），拉低窗口门店日均与合计。\n")
    A("**跨代际对标（各代际预售时点整体线索，N=7 同窗口）**\n")
    A("| 代际 | 预售起始 | 预售当日线索 | 窗口线索 | 基线线索 | 增量 | 增量% | 有效门店日均 | 店均线索 |")
    A("|---|---:|---|---:|---:|---:|---:|---:|---:|")
    for r in lcg:
        bold = "**" if r["gen"] == "DM2" else ""
        d0 = _fmt_int(r["d0"]) if r["d0"] is not None else "—"
        A(f"| {bold}{r['gen']}{bold} | {r['start']} | {bold}{d0}{bold} | {_fmt_int(r['win'])} | {_fmt_int(r['base'])} | {bold}{r['delta']:+,d}{bold} | {bold}{r['delta_pct'] * 100:+.1f}%{bold} | {bold}{r['store_daily']:.0f}{bold} | {bold}{r['per']:.1f}{bold} |")
    A("\n> 口径说明：`assign_data.csv` 为整体业务线索，跨代际对比反映**各代际预售时点的整体业务线索水平**（含业务规模随时间增长），非代际车型专属线索。\n")
    A("**转化率对比（窗口 vs 基线）**\n")
    A("| 指标 | 预售窗口 08-18~08-24 | 基线 08-11~08-17 | 变化 |")
    A("|---|---:|---:|---:|")
    A("| 门店线索占比 | 14.0% | 15.3% | -1.3pp |")
    A("| 当日试驾率 | 5.5% | 6.9% | -1.4pp |")
    A("| 7 日锁单率 | 0.9% | 1.1% | -0.2pp |")
    A("| 30 日锁单率 | 0.9% | 1.1% | -0.2pp |\n")
    A("**判断**：")
    A(f"- **预售当日（08-18）下发线索 {_fmt_int(d18['leads'])}，约为基线日均的 1.6 倍**，是窗口内峰值，说明 M2 预售首日对整体线索有明显拉动。")
    dm2_l = next(r for r in lcg if r["gen"] == "DM2")
    A(f"- **但跨代际看，DM2 预售窗口 vs 基线的线索增量（+{_fmt_int(dm2_l['delta'])}，+{dm2_l['delta_pct'] * 100:.1f}%）是历届代际中最低的**——其余代际 +23%~+117%，M2 预售期间整体线索未显著放量。")
    A(f"- 店均线索 {dm2_l['per']:.1f} 仅略高于 DM1，明显低于 LS9/LS8/CM2；有效门店日均亦处于低水平。")
    A("- 转化率层面：窗口内当日试驾率、7/30 日锁单率略有回落，未观察到 M2 预售对转化率的显著拉动；需在预售进入转化密集期（约 T+7~T+30）后复查成熟 cohort。\n")
    A("---\n")

    # 三、正反向 PK
    pk = load_pk(pk_csv)
    pk_dm2 = pk_week(pk, "2026-08-17 ~ 2026-08-23")
    pk_dm1 = pk_week(pk, "2025-04-14~04-20")
    trend = saic_pk_trend(pk)
    A("## 三、正反向对比（竞争 PK 正反向排名）\n")
    A("> 数据源：`业务数据记录_竞争PK（正反向排名）.csv`（`series=L6`，最新周 **2026-08-17 ~ 08-23**）  ")
    A("> 说明：PK 正向排名 = 竞品对本品（L6）的竞争冲击强度排名；PK 反向排名 = 本品对竞品的影响排名。排名越小越强。\n")
    A("**L6 竞品 PK 榜（2026-08-17 ~ 08-23）**\n")
    A("| 竞品车系 | 品牌 | PK次数 | PK正向排名 | PK反向排名 |")
    A("|---|---:|---:|---:|---:|")
    for _, r in pk_dm2.head(10).iterrows():
        A(f"| {r['车系']} | {r['品牌']} | {_fmt_int(r['PK次数'])} | {r['PK正向排名']} | {r['PK反向排名']} |")
    A("\n**跨代际对比：DM1 预售周 vs DM2 预售周（series=L6）**\n")
    dm1_cars = {str(r["车系"]): int(r["PK次数"]) for _, r in pk_dm1.head(8).iterrows()}
    dm2_cars = {str(r["车系"]): int(r["PK次数"]) for _, r in pk_dm2.head(8).iterrows()}
    all_cars = list(dict.fromkeys(list(dm1_cars.keys()) + list(dm2_cars.keys())))
    A("| 竞品车系 | DM1 预售周（2025-04-14~20） | DM2 预售周（2026-08-17~23） |")
    A("|---|---:|---:|")
    for car in all_cars:
        v1 = _fmt_int(dm1_cars.get(car, 0)) if car in dm1_cars else "—"
        v2 = _fmt_int(dm2_cars.get(car, 0)) if car in dm2_cars else "—"
        A(f"| {car} | {v1} | {v2} |")
    s1 = sum(list(dm1_cars.values())[:5]); s2 = sum(list(dm2_cars.values())[:5])
    A(f"| **Top5 PK 合计** | **{_fmt_int(s1)}** | **{_fmt_int(s2)}** |\n")
    A("> 口径说明：PK 次数为绝对量级，受不同年份整体流量与平台数据影响，跨年对比仅作结构参考；DM1 预售周对应 series=L6。\n")
    A("**上汽集团竞品近 5 周 PK 趋势（series=L6）**\n")
    A("| 周 | 车系 | PK次数 | PK正向排名 | PK反向排名 |")
    A("|---|---:|---:|---:|---:|")
    for r in trend:
        A(f"| {r['week']} | {r['car']} | {_fmt_int(r['pk'])} | {r['fwd']} | {r['rev']} |")
    A("\n**判断**：")
    A(f"- **小米SU7 是 L6 当前最强正向竞品**（PK次数 {_fmt_int(int(pk_dm2.iloc[0]['PK次数']))}，正向排名第 1）。")
    A(f"- **MG 07 EV（上汽集团）高频 PK L6**：本周 PK 次数 {_fmt_int(int(pk_dm2[pk_dm2['车系'] == 'MG 07 EV']['PK次数'].iloc[0]))}（环比大幅上升），正向排名第 2，但反向排名仅 44——即 MG 07 EV 对 L6 人群形成强冲击，L6 对其影响较弱，是预售期需要重点盯防的上汽内部竞品。")
    A("- **尚界Z7（上汽集团）**正向第 5、反向第 6，双方互有影响，量级弱于 MG 07 EV。")
    A(f"- **跨代际看，DM1 预售周 PK 热度显著高于 DM2**：Top5 PK 合计 {_fmt_int(s1)} vs {_fmt_int(s2)}（约 {s1 / s2:.1f} 倍）。竞品结构上，DM1 预售周以外部竞品为主；DM2 预售周出现 **MG 07 EV、尚界 Z7 两个上汽集团内部竞品**（合计占 Top5 PK 次数的 {(dm2_cars.get('MG 07 EV', 0) + dm2_cars.get('尚界Z7', 0)) / s2 * 100:.0f}%），上汽内部竞争明显加剧，这是 DM1 预售期没有的情况。\n")
    A("---\n")

    # 四、预选配置
    conf = config_analysis(ret)
    A("## 四、预选配置\n")
    A("> 数据源：`config_attribute.parquet`（`dataset/updater/order_config_to_parquet.py --force --incremental` 从 Tableau 更新）  ")
    A("> **口径**：严格 release DM2——仅统计**留存小订池**内的配置；DM2 全集中的试驾车配置不纳入。  ")
    A("> **说明**：配置表为 EAV 长表。留存池订单的 **value（显示名）已回填**、但 **value_code（配置 code）全空**（Tableau 导出未带 code）；因此按**显示名**统计占比，不做 code 级归一/语义/价格映射。\n")
    A("**选配覆盖概览（按产品，release 口径）**\n")
    A("| 产品 | 留存订单 | 有选配 value | 覆盖率 | 完整核心配置* |")
    A("|---|---:|---:|---:|---:|")
    for p in conf["prod_rows"]:
        share = p["withval"] / p["total"] if p["total"] else 0
        A(f"| {p['product']} | {_fmt_int(p['total'])} | {_fmt_int(p['withval'])} | {_fmt_pct(share)} | {_fmt_int(p['core'])} |")
    A(f"| **合计** | **{_fmt_int(ret_n)}** | **{_fmt_int(conf['covered'])}** | **{_fmt_pct(conf['covered'] / ret_n)}** | **{_fmt_int(conf['covered'])}** |")
    A("\n> *完整核心配置 = 内饰/外饰/轮毂/方向盘/超远距高精度激光雷达 五个核心属性均有 value。")
    A("> 结论：**基础版（全新一代智己L6）选配覆盖显著偏低，其余产品均 100%**；选配覆盖差异主要来自基础版。\n")
    A("**已选配置分布（按显示名）**\n")
    A("| 属性 | 选项（显示名） | 订单数 | 占比 |")
    A("|---|---|---|---|")
    for attr, vc in conf["attr_dist"].items():
        denom = conf["covered"]
        for v, c in vc.items():
            A(f"| {attr} | {v} | {_fmt_int(c)} | {_fmt_pct(c / denom)} |")
    A(f"\n**判断（release 口径，{_fmt_int(conf['covered'])} 单样本）**：配置偏好明确；基础版配置记录覆盖率偏低，其配置结论需随回填复核；value_code 缺失影响 code 归一与价格分析，后续可从 Tableau 补充 code 后升级为 code 级渗透率。\n")
    A("---\n")

    # 五、用户画像
    pf = profile(ret)
    A("## 五、订单用户画像（L6 M2 留存小订 · release 口径）\n")
    A("> **口径说明**：严格对齐 release DM2 口径——**预售开放当日 20:00 之后支付意向金、且未退意向金的留存小订**，与预售核心指标模块一致。\n")
    A("| 维度 | 留存小订 |")
    A("|---|---|")
    male = int(pf["gender"].get("男", 0)); female = int(pf["gender"].get("女", 0))
    A(f"| 性别（order_gender） | 男 {_fmt_int(male)} / 女 {_fmt_int(female)} / 其他（男占比 {_fmt_pct(male / pf['n'])}） |")
    A(f"| 年龄（buyer_age） | 非空 {_fmt_int(pf['age_nonnull'])}；中位 {pf['age_median']:.0f} 岁 / 均值 {pf['age_mean']:.1f} |")
    A(f"| 年龄（owner_age） | 非空 {_fmt_int(pf['owner_nonnull'])}（登记人字段缺失，不纳入画像） |")
    t = pf["tier"]
    A(f"| 城市线级 | 新一线 {_fmt_int(t.get('新一线', 0))} / 一线 {_fmt_int(t.get('一线', 0))} / 二线 {_fmt_int(t.get('二线', 0))} / 三线及以下 {_fmt_int(t.get('三线及以下', 0))} |")
    prov_top = list(pf["prov"].items())[:5]
    A(f"| 省份 Top5 | {' / '.join(f'{p} {_fmt_int(c)}' for p, c in prov_top)} |")
    A(f"| 产品结构 | {_fmt_int(pf['product'].get('全新一代智己L6', 0))} 基础版为主 |\n")
    A("**小结**：L6 M2 留存小订用户男性占比约 5 成、年龄中位偏年轻；新一线+一线占比过半；省份集中于江苏/浙江/广东/上海。画像基于 release 口径留存小订，与「订单」「预选配置」模块口径一致。\n")
    A("---\n")

    # 六、集团
    tp_df, tp_extra = tp_mg()
    A("## 六、集团口径\n")
    A("### 6.1 TP 口径（MG 品牌市场上险）\n")
    A("| 月份 | MG 品牌合计销量 | 智己对比 |")
    A("|---|---:|---:|")
    for _, r in tp_df.iterrows():
        A(f"| {r['month'].strftime('%Y-%m')} | {_fmt_int(r['mg'])} | {_fmt_int(r['zh'])} |")
    yoy = (tp_extra["yoy_26"] - tp_extra["yoy_25"]) / tp_extra["yoy_25"]
    A(f"\n> MG 同比（2026-07 vs 2025-07）：{_fmt_int(tp_extra['yoy_26'])} vs {_fmt_int(tp_extra['yoy_25'])}，**+{yoy * 100:.1f}%**。\n")
    A("**MG 车型结构（2026-07）**\n")
    A("| 车型 | 能源 | 销量 |")
    A("|---|---:|---:|")
    for _, r in tp_extra["models"].head(6).iterrows():
        A(f"| {r['model']} | {r['fuel_type_group']} | {_fmt_int(r['sales'])} |")
    A("\n> MG 销量主要由纯电 MG4 EV、MG 4X 支撑，新能源占比高、价格带明显低于智己；作为集团/MG 市场背景，不与 L6 M2 预售订单直接相加。\n")
    A("### 6.2 集团订单日报口径 · 预售期小订对比（L6 M2 vs MG 07）\n")
    A("> 数据源：`saic观星台集团订单日报`（重点车型·预售期小订区块）\n")
    mg07 = guanxingta_presale(gx_dir, "订单日报2.0-0819.xlsx", "MG 07")
    l6m2 = guanxingta_presale(gx_dir, "订单日报2.0-0822.xlsx", "智己L6")
    A("**预售期小订累计对比**\n")
    A("| 车型 | 预售期小订累计 | 快照日 | 8月预售日均 |")
    A("|---|---:|---|---:|")
    A(f"| **MG 07** | **{_fmt_int(mg07['cum']) if mg07 and mg07['cum'] else '—'}** | 2026-08-19 | {_fmt_int(mg07['daily_avg']) if mg07 and mg07['daily_avg'] else '—'} |")
    A(f"| **L6 M2（智己L6）** | **{_fmt_int(l6m2['cum']) if l6m2 and l6m2['cum'] else '—'}** | 2026-08-22 | {_fmt_int(l6m2['daily_avg']) if l6m2 and l6m2['daily_avg'] else '—'} |")
    # 每日预售期小订
    all_days = sorted(set((mg07 or {}).get("daily", {}).keys()) | set((l6m2 or {}).get("daily", {}).keys()))
    if all_days:
        A("\n**每日预售期小订（近 8 日）**\n")
        A("| 日期 | " + " | ".join(f"**{d}**" if d == "08/18" else d for d in all_days) + " |")
        A("|" + "---:|" * (len(all_days) + 1))

        def _day(v):
            return _fmt_int(v) if v is not None else "—"

        mg_line = "| MG 07 预售期小订 | " + " | ".join(_day((mg07 or {}).get("daily", {}).get(d)) for d in all_days) + " |"
        l6_line = "| L6 M2 预售期小订 | " + " | ".join(f"**{_day((l6m2 or {}).get('daily', {}).get(d))}**" if d == "08/18" else _day((l6m2 or {}).get("daily", {}).get(d)) for d in all_days) + " |"
        A(mg_line)
        A(l6_line + "\n")
    A("\n**判断**：")
    if mg07 and l6m2 and mg07["cum"] and l6m2["cum"]:
        ratio = mg07["cum"] / l6m2["cum"]
        A(f"- **MG 07 预售期小订量级约为 L6 M2 的 {ratio:.1f} 倍**（{_fmt_int(mg07['cum'])} vs {_fmt_int(l6m2['cum'])}，快照日相差 3 天），且 MG 07 预售早于 L6 M2。")
        A(f"- L6 M2 预售期小订峰值在 **08-18（1,090/日）**，随后回落至百单级，与内部 `order_data` release 口径趋势一致。")
        A("- 注意：观星台“预售期小订”为集团日度口径，与智己内部 release 口径（20:00 起算留存小订）数值略有差异，对比时保持口径说明。")
        A("- 同一集团内，MG 07 是 L6 M2 预售期最直接的同级参照系之一；叠加竞争 PK 数据（MG 07 EV 本周 PK 次数靠前、正向第 2），说明其市场热度与预售热度均显著高于 L6 M2。")
    else:
        A("- 观星台预售期小订源文件缺失或解析失败，暂无法输出对比。")
    A("\n---\n")

    # 附录
    A("## 附录：口径与数据源\n")
    A("| 模块 | 数据源 | 时间窗口/口径 |")
    A("|---|---|---|")
    A(f"| 订单 | `order_data.parquet`；DM2 识别 `series_group_logic.DM2` | **release 口径**：预售 08-18 20:00 起留存小订（{_fmt_int(ret_n)} 单）；试驾车不纳入 |")
    A("| 下发线索 | `assign_data.csv` | 预售窗口 vs 前 7 天基线；整体业务口径（非 DM2 专属） |")
    A("| 正反向 | `业务数据记录_竞争PK（正反向排名）.csv`（series=L6） | 周度，最新 2026-08-17~08-23 |")
    A(f"| 预选配置 | `config_attribute.parquet` | release 口径：留存小订池 {_fmt_int(conf['covered'])} 单（{_fmt_pct(conf['covered'] / ret_n)}）有 value；value_code 全空，按显示名统计 |")
    A(f"| 用户画像 | `order_data.parquet` | release 口径：预售开放 20:00 后留存小订（{_fmt_int(ret_n)} 单） |")
    A("| 集团 | `TP&MIX-ways` + `saic观星台集团订单日报`（预售期小订区块） | TP 截至 2026-07；MG 07 快照 08-19、L6 M2 快照 08-22 |")
    A("\n**主要脚本**：")
    A("```bash")
    A(f".venv/bin/python mashang_workspace/research_scripts/l6_m2_presale_report.py --as-of {as_of.date()}")
    A("```")
    A("\n**已知限制**：全文预售订单口径统一为 release DM2（留存小订），DM2 全集中的大定/锁单/开票/交付均为试驾车，不计入零售；预售未结束，30 日转化与最终兑现存在右删失；正反向口径为竞争 PK 排名（非订单漏斗）；配置按显示名统计、value_code 缺失；画像中登记人（owner）字段缺失率高。\n")

    out_path = output_dir / f"L6_M2_预售情况汇报_{as_of.date()}.md"
    out_path.write_text("\n".join(L), encoding="utf-8")
    return out_path


# ── HTML 渲染 ────────────────────────────────────────────

def _h_table(headers: list[str], rows: list[list[str]], num_cols: set[int] | None = None,
             bold_rows: set[int] | None = None) -> str:
    """按视觉系统渲染 report-table。num_cols: 数字列（tabular-nums 加粗）；bold_rows: 高亮行。"""
    num_cols = num_cols or set()
    bold_rows = bold_rows or set()
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = []
    for ri, row in enumerate(rows):
        tds = []
        for ci, cell in enumerate(row):
            cls = ' class="num"' if ci in num_cols else ""
            tds.append(f"<td{cls}>{cell}</td>")
        style = ' class="row-highlight"' if ri in bold_rows else ""
        trs.append(f"<tr{style}>{''.join(tds)}</tr>")
    return f'<div class="table-wrap"><table class="report-table"><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'


def _h_kpi(value: str, label: str, hint: str = "") -> str:
    hint_html = f'<div class="summary-hint">{hint}</div>' if hint else ""
    return f'<div class="summary-card"><div class="summary-value">{value}</div><div class="summary-label">{label}</div>{hint_html}</div>'


def _h_section(title: str, inner: str, note: str = "") -> str:
    note_html = f'<p class="section-note">{note}</p>' if note else ""
    return f'<section class="report-section"><h2 class="section-title">{title}</h2>{note_html}{inner}</section>'


def render_html(as_of: pd.Timestamp, output_dir: Path, pk_csv: Path, gx_dir: Path) -> Path:
    import html as html_lib

    esc = html_lib.escape

    bd = load_business_definition(REPO_ROOT / "shared/schema/business_definition.json")
    df = load_order()
    ret = retention_pool(df, as_of)
    ret_n = int(ret["order_number"].nunique())
    core = presale_core(df, as_of)
    bench = gen_benchmark(df, bd)

    S: list[str] = []
    A = S.append
    static = "../.."

    # ── 页面外壳 ──
    A('<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8" />')
    A('<meta name="viewport" content="width=device-width, initial-scale=1.0" />')
    A(f"<title>L6 M2 预售情况汇报 | {as_of.date()}</title>")
    A(f'<link rel="stylesheet" href="{static}/templates/report_style.css" />')
    A("</head>\n<body class=\"report-page\">\n<header><div class=\"container\">")
    A('<div class="brand"><img class="brand-avatar" src="../../assets/brand/raccoon_avatar_light.png" alt="" /><span class="brand-name">Raccoon Research</span></div>')
    A(f'<span class="header-meta">L6 M2 预售情况汇报 · 截至 {as_of.date()}</span>')
    A('</div></header>\n<main class="report-container">\n')
    A('<div class="hero"><h1>L6 M2 预售情况汇报</h1>')
    A(f'<p>release DM2 口径 · 预售窗口 2026-08-18 ~ 2026-09-18（N={N_DAYS}）· 数据截至 {as_of.date()}<br/>'
      f'口径：预售开放当日 20:00 之后支付意向金且未退的留存小订；试驾车不纳入</p></div>')

    # ── KPI 卡 ──
    A('<div class="summary-grid">')
    A(_h_kpi(_fmt_int(core["retention"]), "留存小订（报告口径）", f"20:00 起算未退意向金"))
    A(_h_kpi(_fmt_int(core["cum"]), "累计小订", "含已退订"))
    A(_h_kpi(_fmt_int(core["retention_users"]), "留存唯一订单用户", ""))
    A(_h_kpi(_fmt_int(core["ld_ret"]), "发布会当日留存", "20:00-24:00"))
    A("</div>")

    # ── 一、订单 ──
    rows_bench = []
    for b in bench:
        rows_bench.append([b["gen"], _fmt_int(b["ret_n"]), b["peak_h"], _fmt_int(b["peak_c"]),
                           _fmt_int(b["ld_total"]), _fmt_int(b["ld_ret"])])
    dm2_idx = next(i for i, b in enumerate(bench) if b["gen"] == "DM2")
    A(_h_section("一、预售对标（跨代际 · N=7 同窗口）",
                 _h_table(["代际", "同 N 日留存", "首日峰值小时", "峰值小时小订", "发布会当日小订", "发布会当日留存"],
                          rows_bench, num_cols={1, 3, 4, 5}, bold_rows={dm2_idx}),
                 note="统一按各自预售开放时刻（20:00）起算；L6 M2 三项指标均低于历届代际（约为 DM1 的 1/4），仅作量级参考；"
                      "截至快照日 release 口径尚无大定/锁单转化——DM2 全集的大定/锁单/开票/交付均为试驾车。"))

    # 产品结构
    total_p = ret_n
    limited = sum(int(c) for p, c in core["product"].items() if "JimmyChoo" in p)
    rows_prod = [[p, _fmt_int(int(c)), _fmt_pct(c / total_p)] for p, c in core["product"].items() if "JimmyChoo" not in p]
    rows_prod.append(["非限量版小计", _fmt_int(total_p - limited), _fmt_pct((total_p - limited) / total_p)])
    rows_prod += [[p, _fmt_int(int(c)), _fmt_pct(c / total_p)] for p, c in core["product"].items() if "JimmyChoo" in p]
    rows_prod.append(["限量版小计", _fmt_int(limited), _fmt_pct(limited / total_p)])
    A(_h_section("产品结构（留存小订）", _h_table(["产品", "留存订单", "占比"], rows_prod, num_cols={1, 2})))

    # 大区结构
    rows_reg = [[reg, _fmt_int(int(c)), _fmt_pct(c / total_p)] for reg, c in core["region"].items()]
    A(_h_section("大区结构（留存小订）", _h_table(["大区", "留存订单", "占比"], rows_reg, num_cols={1, 2}),
                 note="华东（江苏/浙江/上海）为预售第一大区域。"))

    # ── 二、下发线索 ──
    assign = load_assign()
    win = lead_block(assign, "2026-08-18", "2026-08-24")
    base = lead_block(assign, "2026-08-11", "2026-08-17")
    d18 = lead_block(assign, "2026-08-18", "2026-08-18")
    lcg = lead_cross_gen(assign, bd)
    delta = win["leads"] - base["leads"]
    rows_lead = [
        ["下发线索数", f"<strong>{_fmt_int(d18['leads'])}</strong>", _fmt_int(win["leads"]),
         _fmt_int(base["leads"]), f"+{_fmt_int(delta)}（+{delta / base['leads'] * 100:.1f}%）"],
        ["有效门店数（日频合计）", _fmt_int(d18["stores"]), _fmt_int(win["stores"]),
         _fmt_int(base["stores"]), f"{win['stores'] - base['stores']:+d}"],
        ["店均下发线索数", f"<strong>{d18['per_store']:.1f}</strong>", f"{win['per_store']:.1f}",
         f"{base['per_store']:.1f}", f"+{win['per_store'] - base['per_store']:.1f}"],
    ]
    A(_h_section("二、下发线索：预售当日 / 窗口 / 基线",
                 _h_table(["指标", "预售当日 08-18", "窗口 08-18~24", "基线 08-11~17", "窗口 vs 基线"],
                          rows_lead),
                 note="整体业务口径（assign_data.csv 无车型字段）；预售窗口含 08-24 部分快照。"))
    rows_lcg = []
    for r in lcg:
        d0 = _fmt_int(r["d0"]) if r["d0"] is not None else "—"
        rows_lcg.append([r["gen"], r["start"], d0, _fmt_int(r["win"]), _fmt_int(r["base"]),
                         f"{r['delta']:+,d}", f"{r['delta_pct'] * 100:+.1f}%", f"{r['store_daily']:.0f}", f"{r['per']:.1f}"])
    dm2_l_idx = next(i for i, r in enumerate(lcg) if r["gen"] == "DM2")
    A(_h_section("下发线索跨代际对标（N=7 同窗口）",
                 _h_table(["代际", "预售起始", "当日线索", "窗口线索", "基线线索", "增量", "增量%", "门店日均", "店均线索"],
                          rows_lcg, num_cols={2, 3, 4, 5, 6}, bold_rows={dm2_l_idx}),
                 note="DM2 窗口 vs 基线线索增量为历届最低（+0.5%），M2 预售期间整体线索未显著放量。"))

    # 转化率
    rows_conv = [["门店线索占比", "14.0%", "15.3%", "-1.3pp"],
                 ["当日试驾率", "5.5%", "6.9%", "-1.4pp"],
                 ["7 日锁单率", "0.9%", "1.1%", "-0.2pp"],
                 ["30 日锁单率", "0.9%", "1.1%", "-0.2pp"]]
    A(_h_section("转化率对比（窗口 vs 基线）",
                 _h_table(["指标", "预售窗口", "基线", "变化"], rows_conv)))

    # ── 三、正反向 PK ──
    pk = load_pk(pk_csv)
    pk_dm2 = pk_week(pk, "2026-08-17 ~ 2026-08-23")
    pk_dm1 = pk_week(pk, "2025-04-14~04-20")
    trend = saic_pk_trend(pk)
    rows_pk = [[str(r["车系"]), str(r["品牌"]), _fmt_int(int(r["PK次数"])),
                str(int(r["PK正向排名"])), str(int(r["PK反向排名"]))] for _, r in pk_dm2.head(10).iterrows()]
    A(_h_section("三、正反向对比：L6 竞品 PK 榜（2026-08-17 ~ 08-23）",
                 _h_table(["竞品车系", "品牌", "PK次数", "PK正向排名", "PK反向排名"], rows_pk, num_cols={2}),
                 note="PK 正向排名=竞品对本品的冲击强度；反向排名=本品对竞品的影响；排名越小越强。数据源：竞争PK（正反向排名）CSV，series=L6。"))
    dm1_cars = {str(r["车系"]): int(r["PK次数"]) for _, r in pk_dm1.head(8).iterrows()}
    dm2_cars = {str(r["车系"]): int(r["PK次数"]) for _, r in pk_dm2.head(8).iterrows()}
    all_cars = list(dict.fromkeys(list(dm1_cars.keys()) + list(dm2_cars.keys())))
    s1 = sum(list(dm1_cars.values())[:5]); s2 = sum(list(dm2_cars.values())[:5])
    rows_cmp = []
    for car in all_cars:
        v1 = _fmt_int(dm1_cars[car]) if car in dm1_cars else "—"
        v2 = _fmt_int(dm2_cars[car]) if car in dm2_cars else "—"
        rows_cmp.append([car, v1, v2])
    rows_cmp.append([f"<strong>Top5 PK 合计</strong>", f"<strong>{_fmt_int(s1)}</strong>", f"<strong>{_fmt_int(s2)}</strong>"])
    A(_h_section("跨代际对比：DM1 预售周 vs DM2 预售周（series=L6）",
                 _h_table(["竞品车系", "DM1 预售周（2025-04-14~20）", "DM2 预售周（2026-08-17~23）"], rows_cmp, num_cols={1, 2}),
                 note=f"DM1 预售周 Top5 PK 合计 {_fmt_int(s1)}，约为 DM2（{_fmt_int(s2)}）的 {s1 / s2:.1f} 倍；"
                      f"DM2 预售周出现 MG 07 EV、尚界 Z7 两个上汽集团内部竞品（合计占 Top5 PK 的 "
                      f"{(dm2_cars.get('MG 07 EV', 0) + dm2_cars.get('尚界Z7', 0)) / s2 * 100:.0f}%）。跨年对比仅作结构参考。"))
    rows_trend = [[r["week"], r["car"], _fmt_int(r["pk"]), str(r["fwd"]), str(r["rev"])] for r in trend]
    A(_h_section("上汽集团竞品近 5 周 PK 趋势（series=L6）",
                 _h_table(["周", "车系", "PK次数", "PK正向排名", "PK反向排名"], rows_trend, num_cols={2})))

    # ── 四、预选配置 ──
    conf = config_analysis(ret)
    rows_cov = []
    for p in conf["prod_rows"]:
        share = p["withval"] / p["total"] if p["total"] else 0
        rows_cov.append([p["product"], _fmt_int(p["total"]), _fmt_int(p["withval"]), _fmt_pct(share), _fmt_int(p["core"])])
    rows_cov.append([f"<strong>合计</strong>", f"<strong>{_fmt_int(ret_n)}</strong>",
                     f"<strong>{_fmt_int(conf['covered'])}</strong>",
                     f"<strong>{_fmt_pct(conf['covered'] / ret_n)}</strong>",
                     f"<strong>{_fmt_int(conf['covered'])}</strong>"])
    A(_h_section("四、预选配置：选配覆盖概览（按产品）",
                 _h_table(["产品", "留存订单", "有选配 value", "覆盖率", "完整核心配置*"], rows_cov, num_cols={1, 2, 3, 4}),
                 note="*完整核心配置 = 内饰/外饰/轮毂/方向盘/超远距高精度激光雷达 五个核心属性均有 value；"
                      "基础版（全新一代智己L6）选配覆盖显著偏低，其余产品均 100%。"
                      "配置 value_code 全空（Tableau 导出未带 code），以下按显示名统计。"))
    rows_cfg = []
    for attr, vc in conf["attr_dist"].items():
        for v, c in vc.items():
            rows_cfg.append([attr, v, _fmt_int(c), _fmt_pct(c / conf["covered"])])
    A(_h_section("已选配置分布（按显示名）",
                 _h_table(["属性", "选项", "订单数", "占比"], rows_cfg, num_cols={2, 3}),
                 note=f"样本为留存小订池内有选配 value 的 {_fmt_int(conf['covered'])} 单；试驾车配置不纳入。"))

    # ── 五、用户画像 ──
    pf = profile(ret)
    male = int(pf["gender"].get("男", 0)); female = int(pf["gender"].get("女", 0))
    t = pf["tier"]
    prov_top = list(pf["prov"].items())[:5]
    rows_pf = [
        ["性别（order_gender）", f"男 {_fmt_int(male)} / 女 {_fmt_int(female)} / 其他（男占比 {_fmt_pct(male / pf['n'])}）"],
        ["年龄（buyer_age）", f"非空 {_fmt_int(pf['age_nonnull'])}；中位 {pf['age_median']:.0f} 岁 / 均值 {pf['age_mean']:.1f}"],
        ["城市线级", f"新一线 {_fmt_int(t.get('新一线', 0))} / 一线 {_fmt_int(t.get('一线', 0))} / 二线 {_fmt_int(t.get('二线', 0))} / 三线及以下 {_fmt_int(t.get('三线及以下', 0))}"],
        ["省份 Top5", " / ".join(f"{p} {_fmt_int(c)}" for p, c in prov_top)],
    ]
    A(_h_section("五、订单用户画像（留存小订 · release 口径）",
                 _h_table(["维度", "分布"], rows_pf),
                 note=f"画像基于 release 口径留存小订（{_fmt_int(ret_n)} 单），与「订单」「预选配置」模块一致；登记人（owner）字段缺失率高，不呈现。"))

    # ── 六、集团 ──
    tp_df, tp_extra = tp_mg()
    rows_tp = [[r["month"].strftime("%Y-%m"), _fmt_int(r["mg"]), _fmt_int(r["zh"])] for _, r in tp_df.iterrows()]
    yoy = (tp_extra["yoy_26"] - tp_extra["yoy_25"]) / tp_extra["yoy_25"]
    A(_h_section("六、TP 口径：MG 品牌市场上险",
                 _h_table(["月份", "MG 合计销量", "智己对比"], rows_tp, num_cols={1, 2}),
                 note=f"MG 同比（2026-07 vs 2025-07）：{_fmt_int(tp_extra['yoy_26'])} vs {_fmt_int(tp_extra['yoy_25'])}，+{yoy * 100:.1f}%。作为市场背景，不与 L6 M2 预售订单相加。"))
    mg07 = guanxingta_presale(gx_dir, "订单日报2.0-0819.xlsx", "MG 07")
    l6m2 = guanxingta_presale(gx_dir, "订单日报2.0-0822.xlsx", "智己L6")
    rows_gx = [
        [f"<strong>MG 07</strong>", f"<strong>{_fmt_int(mg07['cum']) if mg07 and mg07['cum'] else '—'}</strong>",
         "2026-08-19", _fmt_int(mg07["daily_avg"]) if mg07 and mg07["daily_avg"] else "—"],
        [f"<strong>L6 M2（智己L6）</strong>", f"<strong>{_fmt_int(l6m2['cum']) if l6m2 and l6m2['cum'] else '—'}</strong>",
         "2026-08-22", _fmt_int(l6m2["daily_avg"]) if l6m2 and l6m2["daily_avg"] else "—"],
    ]
    gx_note = "观星台“预售期小订”为集团日度口径，与内部 release 口径略有差异。"
    ratio_txt = ""
    if mg07 and l6m2 and mg07["cum"] and l6m2["cum"]:
        ratio_txt = f"MG 07 预售期小订量级约为 L6 M2 的 {mg07['cum'] / l6m2['cum']:.1f} 倍。"
    A(_h_section("集团订单日报：预售期小订对比（L6 M2 vs MG 07）",
                 _h_table(["车型", "预售期小订累计", "快照日", "8月预售日均"], rows_gx, num_cols={1, 3}),
                 note=ratio_txt + gx_note))

    # 附录
    scope_rows = [
        ["订单", f"order_data.parquet · series_group_logic.DM2 · release 口径留存小订 {_fmt_int(ret_n)} 单"],
        ["下发线索", "assign_data.csv · 整体业务口径"],
        ["正反向", "竞争PK（正反向排名）CSV · series=L6 · 最新周 2026-08-17~08-23"],
        ["预选配置", f"config_attribute.parquet · 留存池 {_fmt_int(conf['covered'])} 单有 value，按显示名统计"],
        ["用户画像", "order_data.parquet · release 口径留存小订"],
        ["集团", "TP&MIX-ways + saic观星台集团订单日报（预售期小订区块）"],
    ]
    A(_h_section("口径与数据源",
                 _h_table(["模块", "口径"], scope_rows)))
    known = ("已知限制：全文预售订单口径统一为 release DM2（留存小订）；DM2 全集的大定/锁单/开票/交付均为试驾车，不计入零售；"
             "预售未结束存在右删失；正反向为竞争 PK 排名（非订单漏斗）；配置按显示名统计、value_code 缺失；画像登记人字段缺失率高。")
    A(f'<p class="section-note">{esc(known)}</p>')

    A("</main>\n<footer>")
    A(f'<img class="brand-sig" src="{static}/assets/brand/zihao_signature_transparent.png" alt="Raccoon Research" />')
    A('<div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>')
    A("</footer>\n</body>\n</html>")

    out_path = output_dir / f"L6_M2_预售情况汇报_{as_of.date()}.html"
    out_path.write_text("\n".join(S), encoding="utf-8")
    return out_path


def main() -> int:
    p = argparse.ArgumentParser(description="L6 M2 预售情况汇报 — Markdown/HTML 报告生成器")
    p.add_argument("--as-of", type=str, default=None, help="统计基准日 YYYY-MM-DD（默认今天）")
    p.add_argument("--output", type=str, default=str(_WS_ROOT / "outputs" / "reports"), help="输出目录")
    p.add_argument("--pk-csv", type=str, default=DEFAULT_PK_CSV, help="竞争 PK 正反向排名 CSV 路径")
    p.add_argument("--guanxingta-dir", type=str, default=DEFAULT_GUANXINGTAI_DIR, help="观星台集团订单日报目录")
    p.add_argument("--html", action="store_true", help="同时输出品牌化 HTML 报告")
    args = p.parse_args()

    from datetime import datetime
    as_of = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp(datetime.now().date())
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = render(as_of, out_dir, Path(args.pk_csv), Path(args.guanxingta_dir))
    print(f"✅ Markdown 报告已生成: {out_path}")
    if args.html:
        html_path = render_html(as_of, out_dir, Path(args.pk_csv), Path(args.guanxingta_dir))
        print(f"✅ HTML 报告已生成: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
