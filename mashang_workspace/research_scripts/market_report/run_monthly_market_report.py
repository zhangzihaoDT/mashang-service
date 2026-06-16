#!/usr/bin/env python
"""
月度汽车市场报告 — 固定 24 个查询执行脚本

读取 Query Spec YAML，按指定月份执行 passenger_insurance 数据查询，
输出结构化数据底稿（JSON / XLSX / MD）。

Usage:
  # dry-run（默认）：解析查询规范，不执行数据查询
  python research_scripts/market_report/run_monthly_market_report.py --month 2026-05

  # execute：执行实际数据查询
  python research_scripts/market_report/run_monthly_market_report.py --month 2026-05 --execute

  # 指定 query-spec 和 output-dir
  python research_scripts/market_report/run_monthly_market_report.py \
    --month 2026-05 \
    --query-spec configs/monthly_market_report_queries.yaml \
    --output-dir outputs/monthly_market_report/2026-05 \
    --execute
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, date
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None

try:
    import pandas as pd
except ImportError:
    pd = None

# ---------------------------------------------------------------------------
# Path setup — use workspace utilities
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_WORKSPACE_ROOT = _THIS_DIR.parents[1]

if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from utils.paths import WORKSPACE_ROOT, PROJECT_ROOT, ensure_shared_on_path
ensure_shared_on_path()

# ---------------------------------------------------------------------------
# Imports after path setup
# ---------------------------------------------------------------------------
from utils.result_contract import build_success_contract, build_error_contract, save_contract_json
from shared.loaders.passenger_insurance_loader import load_passenger_insurance_table, list_passenger_insurance_tables


# ---------------------------------------------------------------------------
# Time parameter calculation
# ---------------------------------------------------------------------------
def compute_time_params(report_month: str) -> dict[str, str]:
    """计算所有时间参数。

    Args:
        report_month: YYYY-MM 格式的月份

    Returns:
        时间参数字典
    """
    dt = datetime.strptime(report_month, "%Y-%m")
    y = dt.year
    m = dt.month

    # 当月首日
    import calendar
    _, last_day = calendar.monthrange(y, m)

    month_start = f"{y:04d}-{m:02d}-01"
    month_end = f"{y:04d}-{m:02d}-{last_day:02d}"
    ytd_start = f"{y:04d}-01-01"
    ytd_end = month_end

    # 去年同月
    ly = y - 1
    _, ly_last_day = calendar.monthrange(ly, m)
    last_year_month_start = f"{ly:04d}-{m:02d}-01"
    last_year_month_end = f"{ly:04d}-{m:02d}-{ly_last_day:02d}"
    last_year_ytd_start = f"{ly:04d}-01-01"
    last_year_ytd_end = f"{ly:04d}-{m:02d}-{ly_last_day:02d}"

    # 滚动 12 个月（往前推 12 个月）
    if m == 12:
        rolling_start_y = y
        rolling_start_m = 1
    else:
        rolling_start_y = ly
        rolling_start_m = m + 1
    rolling_12m_start = f"{rolling_start_y:04d}-{rolling_start_m:02d}-01"
    rolling_12m_end = month_end

    return {
        "report_month": report_month,
        "month_start": month_start,
        "month_end": month_end,
        "ytd_start": ytd_start,
        "ytd_end": ytd_end,
        "last_year_month_start": last_year_month_start,
        "last_year_month_end": last_year_month_end,
        "last_year_ytd_start": last_year_ytd_start,
        "last_year_ytd_end": last_year_ytd_end,
        "rolling_12m_start": rolling_12m_start,
        "rolling_12m_end": rolling_12m_end,
    }


# ---------------------------------------------------------------------------
# Query spec loading
# ---------------------------------------------------------------------------
def load_query_spec(path: str | Path) -> dict:
    """加载 YAML 查询规范。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Query spec not found: {p}")
    if yaml is None:
        raise ImportError("PyYAML is required. Install with: pip install pyyaml")
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Adapter query IDs — 需跨表关联或多步处理的 query
# ---------------------------------------------------------------------------
ADAPTER_QUERIES: set[str] = {
    "price_band_brand_competition",
    "tier1_city_competition",
    "new_tier1_city_competition",
    "tier2_city_competition",
    "tier3_lower_city_competition",
}

# tp_bucket_5w 边界定义（单位：元）
TP_BUCKET_5W_BOUNDS: list[tuple[float, float, str]] = [
    (0, 50000, "5万以下"),
    (50000, 100000, "5-10万"),
    (100000, 150000, "10-15万"),
    (150000, 200000, "15-20万"),
    (200000, 250000, "20-25万"),
    (250000, 300000, "25-30万"),
    (300000, 350000, "30-35万"),
    (350000, 400000, "35-40万"),
    (400000, 450000, "40-45万"),
    (450000, 500000, "45-50万"),
    (500000, 550000, "50-55万"),
    (550000, 600000, "55-60万"),
    (600000, float("inf"), "60万以上"),
]


def _bin_tp(weighted_tp: float) -> str:
    """将 weighted_tp 映射到 tp_bucket_5w 区间。"""
    if pd.isna(weighted_tp) or weighted_tp <= 0:
        return "其他"
    for lo, hi, label in TP_BUCKET_5W_BOUNDS:
        if lo < weighted_tp <= hi:
            return label
    return "其他"


# ---------------------------------------------------------------------------
# Table name to human label mapping
# ---------------------------------------------------------------------------
TABLE_LABELS: dict[str, str] = {
    "market_energy_monthly": "市场总量与能源结构",
    "brand_monthly": "品牌月度数据",
    "model_monthly": "车型月度数据",
    "geo_monthly": "地理月度数据",
    "price_segment_monthly": "价格段月度数据",
    "product_segment_monthly": "产品细分月度数据",
}


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------
def execute_query(query: dict, time_params: dict[str, str], available_tables: list[str]) -> dict:
    """执行单个查询。

    在 dry-run 模式下只返回查询计划；在 execute 模式下尝试从 passenger_insurance 加载数据。

    Args:
        query: 查询定义
        time_params: 时间参数
        available_tables: 可用表列表

    Returns:
        执行结果 dict
    """
    qid = query["id"]
    table = query.get("table", "")
    grain = query.get("grain", [])
    metrics = query.get("metrics", [])
    dimensions = query.get("dimensions", [])
    filters = query.get("filters", {})
    output_type = query.get("output_type", "table")
    business_logic = query.get("business_logic", "")

    result: dict[str, Any] = {
        "id": qid,
        "title": query.get("title", ""),
        "group": query.get("group", "other"),
        "status": "planned",
        "table": table,
        "grain": grain,
        "metrics": metrics,
        "filters": filters,
        "time_window": {
            "month": time_params["month_start"],
            "month_end": time_params["month_end"],
            "ytd_start": time_params["ytd_start"],
            "ytd_end": time_params["ytd_end"],
        },
        "output_type": output_type,
        "data": None,
        "error": None,
    }

    # Adapter queries: route to cross-table execution
    if qid in ADAPTER_QUERIES:
        return execute_adapter_query(query, time_params, available_tables)

    is_dry_run = _GLOBAL_DRY_RUN

    if is_dry_run:
        result["status"] = "dry_run"
        result["summary"] = f"[DRY RUN] 将查询 {TABLE_LABELS.get(table, table)} 表，指标={metrics}，维度={dimensions}，过滤={filters}"
        return result

    # Execute mode — try to load data
    if not pd:
        result["status"] = "error"
        result["error"] = "pandas is required for execute mode"
        return result

    if table not in available_tables:
        result["status"] = "skipped"
        result["error"] = f"表 '{table}' 不在可用 passenger_insurance 表中。可用表: {available_tables}"
        return result

    try:
        df = load_passenger_insurance_table(table)
        if df is None or df.empty:
            result["status"] = "skipped"
            result["error"] = f"表 '{table}' 返回空数据"
            return result

        # Ensure date_month is datetime
        if "date_month" in df.columns:
            df["date_month"] = pd.to_datetime(df["date_month"])

        # Apply time filter based on query grain
        month_start = pd.to_datetime(time_params["month_start"])
        month_end = pd.to_datetime(time_params["month_end"])

        if "date_month" in df.columns:
            df = df[(df["date_month"] >= month_start) & (df["date_month"] <= month_end)]

        # Apply static filters
        for field, values in filters.items():
            if field in df.columns:
                if isinstance(values, list):
                    df = df[df[field].isin(values)]
                else:
                    df = df[df[field] == values]

        # Build result data
        data: dict[str, Any] = {
            "row_count": len(df),
            "columns": list(df.columns),
        }

        if not df.empty and metrics:
            if grain:
                group_cols = [c for c in grain if c in df.columns]
                if group_cols:
                    agg_dict = {}
                    for m in metrics:
                        if m in df.columns:
                            agg_dict[m] = "sum" if m == "sales" else "mean"
                    if agg_dict:
                        grouped = df.groupby(group_cols, observed=True).agg(agg_dict).reset_index()
                        data["grouped"] = grouped.to_dict(orient="records")
                    else:
                        data["sample"] = df.head(20).to_dict(orient="records")
                else:
                    data["sample"] = df.head(20).to_dict(orient="records")
            else:
                # Aggregate all
                agg = {}
                for m in metrics:
                    if m in df.columns:
                        agg[f"total_{m}"] = float(df[m].sum()) if m == "sales" else float(df[m].mean())
                data["aggregated"] = agg
        else:
            data["sample"] = df.head(20).to_dict(orient="records")

        result["status"] = "success"
        result["data"] = data
        result["summary"] = f"表 {TABLE_LABELS.get(table, table)}: {len(df)} 行数据"

    except Exception as e:
        result["status"] = "error"
        result["error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()

    return result


# ---------------------------------------------------------------------------
# Adapter query execution — 跨表关联或多步处理的查询
# ---------------------------------------------------------------------------
def execute_adapter_query(query: dict, time_params: dict[str, str], available_tables: list[str]) -> dict:
    """执行 adapter 类型的跨表查询。

    Args:
        query: 查询定义
        time_params: 时间参数
        available_tables: 可用表列表

    Returns:
        执行结果 dict
    """
    qid = query["id"]
    metrics = query.get("metrics", ["sales"])
    output_type = query.get("output_type", "table")

    result: dict[str, Any] = {
        "id": qid,
        "title": query.get("title", ""),
        "group": query.get("group", "other"),
        "status": "planned",
        "table": "adapter",
        "grain": query.get("grain", []),
        "metrics": metrics,
        "filters": query.get("filters", {}),
        "time_window": {
            "month": time_params["month_start"],
            "month_end": time_params["month_end"],
            "ytd_start": time_params["ytd_start"],
            "ytd_end": time_params["ytd_end"],
        },
        "output_type": output_type,
        "data": None,
        "error": None,
    }

    if _GLOBAL_DRY_RUN:
        result["status"] = "dry_run"
        if qid == "price_band_brand_competition":
            result["summary"] = "[DRY RUN] 跨表 adapter: model_monthly + brand_monthly，按 weighted_tp 分价位段统计品牌排名"
        else:
            result["summary"] = "[DRY RUN] 跨表 adapter: geo_monthly，按 city_tier_group 统计城市新能源销量和渗透率"
        return result

    if not pd:
        result["status"] = "error"
        result["error"] = "pandas is required for execute mode"
        return result

    try:
        if qid == "price_band_brand_competition":
            _execute_price_band_brand(result, time_params, available_tables)
        elif qid in ("tier1_city_competition", "new_tier1_city_competition",
                     "tier2_city_competition", "tier3_lower_city_competition"):
            _execute_city_competition(result, time_params, available_tables)
        else:
            result["status"] = "error"
            result["error"] = f"未知 adapter query id: {qid}"
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()

    return result


def _execute_price_band_brand(result: dict, time_params: dict[str, str], available_tables: list[str]) -> None:
    """执行 price_band_brand_competition。

    从 model_monthly 读取车型数据，用 weighted_tp 分桶到 tp_bucket_5w，
    筛选新能源车型，按 (date_month, tp_bucket, brand) 汇总销量并排名。
    """
    if "model_monthly" not in available_tables:
        result["status"] = "skipped"
        result["error"] = "需要 model_monthly 表进行价位段品牌排名分析"
        return

    df = load_passenger_insurance_table("model_monthly")
    if df is None or df.empty:
        result["status"] = "skipped"
        result["error"] = "model_monthly 表返回空数据"
        return

    df["date_month"] = pd.to_datetime(df["date_month"])
    month_start = pd.to_datetime(time_params["month_start"])
    month_end = pd.to_datetime(time_params["month_end"])
    df = df[(df["date_month"] >= month_start) & (df["date_month"] <= month_end)]

    # 筛选新能源车型（纯电动、插电式混合动力、增程型电动）
    nev_fuel_types = ["纯电动", "插电式混合动力", "增程型电动"]
    df = df[df["fuel_type"].isin(nev_fuel_types)]

    if df.empty:
        result["status"] = "success"
        result["data"] = {"row_count": 0, "note": "当月无新能源车型数据"}
        result["summary"] = "model_monthly: 当月无新能源车型数据"
        return

    # 按 weighted_tp 分价位段
    df["tp_bucket"] = df["weighted_tp"].apply(_bin_tp)

    # 排除"其他"和"5万以下"（非典型价位段）
    price_bands = ["5-10万", "10-15万", "15-20万", "20-25万", "25-30万",
                   "30-35万", "35-40万", "40-45万", "45-50万", "50-55万",
                   "55-60万", "60万以上"]
    df = df[df["tp_bucket"].isin(price_bands)]

    if df.empty:
        result["status"] = "success"
        result["data"] = {"row_count": 0, "note": "分价位段后无有效数据"}
        result["summary"] = "model_monthly: 分价位段后无有效数据"
        return

    # 聚合：每个价位段 × 品牌的销量
    grouped = df.groupby(["tp_bucket", "brand"], observed=True).agg(
        sales=("sales", "sum")
    ).reset_index()

    # 计算每个价位段的总销量和品牌份额
    band_totals = grouped.groupby("tp_bucket")["sales"].transform("sum")
    grouped["share"] = (grouped["sales"] / band_totals * 100).round(2)

    # 在每个价位段内按销量排名
    grouped["rank"] = grouped.groupby("tp_bucket")["sales"].rank(method="dense", ascending=False).astype(int)
    grouped = grouped.sort_values(["tp_bucket", "rank"])

    # 汇总每个价位段的市场规模
    band_summary = df.groupby("tp_bucket", observed=True).agg(
        band_sales=("sales", "sum"),
        brand_count=("brand", "nunique"),
    ).reset_index().sort_values("band_sales", ascending=False)

    records = grouped.to_dict(orient="records")
    band_records = band_summary.to_dict(orient="records")

    result["status"] = "success"
    result["data"] = {
        "row_count": len(grouped),
        "brands_ranked": len(records),
        "grouped": records,
        "band_summary": band_records,
        "note": "价位段基于车型 weighted_tp 分桶，品牌排名仅限新能源车型",
    }
    total_nev_sales = int(df["sales"].sum())
    result["summary"] = f"新能源分价位段品牌排名: {len(records)} 条记录，{total_nev_sales:,} 总销量"


def _execute_city_competition(result: dict, time_params: dict[str, str], available_tables: list[str]) -> None:
    """执行城市市场结构查询。

    从 geo_monthly 获取城市线级 × 能源类型的销量结构。
    返回当前 6 张单表可支持的城市线级结构指标（销量、份额、渗透率）。
    """
    qid = result["id"]

    tier_map = {
        "tier1_city_competition": "一线",
        "new_tier1_city_competition": "新一线",
        "tier2_city_competition": "二线",
        "tier3_lower_city_competition": "三线及以下",
    }
    target_tier = tier_map.get(qid, "")

    if "geo_monthly" not in available_tables:
        result["status"] = "skipped"
        result["error"] = f"需要 geo_monthly 表进行 {target_tier} 新能源市场结构分析"
        return

    df = load_passenger_insurance_table("geo_monthly")
    if df is None or df.empty:
        result["status"] = "skipped"
        result["error"] = "geo_monthly 表返回空数据"
        return

    df["date_month"] = pd.to_datetime(df["date_month"])
    month_start = pd.to_datetime(time_params["month_start"])
    month_end = pd.to_datetime(time_params["month_end"])
    df = df[(df["date_month"] >= month_start) & (df["date_month"] <= month_end)]

    # 筛选目标城市线级
    if qid == "tier3_lower_city_competition":
        df = df[df["city_tier_group"] == "三线及以下"]
    else:
        df = df[df["city_tier_group"] == target_tier]

    if df.empty:
        result["status"] = "success"
        result["summary"] = f"{target_tier}: 当月无数据"
        result["data"] = {"row_count": 0, "note": f"{target_tier} 当月无数据"}
        return

    # 城市线级总览：总销量、新能源销量、渗透率
    total_sales = float(df["sales"].sum())
    nev_df = df[df["fuel_type_group"] == "新能源"]
    nev_sales = float(nev_df["sales"].sum()) if not nev_df.empty else 0
    nev_penetration = round(nev_sales / total_sales * 100, 2) if total_sales > 0 else 0

    # 各城市销量 × 能源类型结构
    city_grouped = df.groupby(["city", "fuel_type_group"], observed=True).agg(
        sales=("sales", "sum")
    ).reset_index()

    # 城市排名（按总销量）
    city_total = df.groupby("city", observed=True).agg(
        total_sales=("sales", "sum")
    ).reset_index().sort_values("total_sales", ascending=False)

    records = city_grouped.to_dict(orient="records")
    city_ranks = city_total.head(20).to_dict(orient="records")

    result["status"] = "success"
    result["data"] = {
        "row_count": len(city_grouped),
        "tier": target_tier,
        "total_sales": total_sales,
        "nev_sales": nev_sales,
        "nev_penetration_pct": nev_penetration,
        "city_count": int(city_total["city"].nunique()),
        "grouped": records,
        "city_ranking": city_ranks,
    }
    result["summary"] = f"{target_tier}: {int(total_sales):,} 总销量，{nev_penetration}% 新能源渗透率，{int(city_total['city'].nunique())} 个城市"


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------
def write_json_output(results: list[dict], output_path: Path, time_params: dict, spec_info: dict) -> Path:
    """写入 JSON 结果文件（Result Contract 格式）。"""
    total = len(results)
    succeeded = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] in ("skipped", "dry_run"))

    contract = build_success_contract(
        script="research_scripts/market_report/run_monthly_market_report.py",
        command=f"--month {time_params['report_month']} --execute",
        scope={
            "data_source": "passenger_insurance",
            "time_window": {
                "report_month": time_params["report_month"],
                "month_start": time_params["month_start"],
                "month_end": time_params["month_end"],
                "ytd_start": time_params["ytd_start"],
                "ytd_end": time_params["ytd_end"],
            },
            "filters": {},
            "metric_definition": "24 个固定月报查询问题，详见 query_spec",
        },
        result={
            "summary": f"月报 {time_params['report_month']}: {succeeded} success, {failed} failed, {skipped} skipped/planned",
            "total_queries": total,
            "succeeded": succeeded,
            "failed": failed,
            "skipped_or_planned": skipped,
        },
        artifacts={
            "json": str(output_path / "query_results.json"),
            "xlsx": str(output_path / "query_results.xlsx") if (output_path / "query_results.xlsx").exists() else None,
            "md": str(output_path / "report_draft.md") if (output_path / "report_draft.md").exists() else None,
        },
        followup_context={
            "metric": "market_report",
            "report_month": time_params["report_month"],
            "available_dimensions": ["model", "brand", "city", "energy_type", "price_band"],
        },
    )

    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "query_results.json"

    output = {
        "contract": contract,
        "time_params": time_params,
        "query_spec": {
            "report_name": spec_info.get("report_name", ""),
            "version": spec_info.get("version", ""),
        },
        "queries": results,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    return json_path


def write_xlsx_output(results: list[dict], output_path: Path) -> Path | None:
    """写入 Excel 输出文件，每个 query 一个 sheet。"""
    if pd is None:
        return None
    try:
        output_path.mkdir(parents=True, exist_ok=True)
        xlsx_path = output_path / "query_results.xlsx"

        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
            for r in results:
                qid = r["id"]
                sheet_name = qid[:31]

                meta = pd.DataFrame([
                    {"field": "id", "value": r.get("id", "")},
                    {"field": "title", "value": r.get("title", "")},
                    {"field": "status", "value": r.get("status", "")},
                    {"field": "table", "value": r.get("table", "")},
                    {"field": "summary", "value": r.get("summary", "")},
                ])
                meta.to_excel(writer, sheet_name=sheet_name, index=False)

                data = r.get("data")
                if data and isinstance(data, dict):
                    grouped = data.get("grouped")
                    if grouped and isinstance(grouped, list):
                        pd.DataFrame(grouped).to_excel(
                            writer, sheet_name=f"{sheet_name}_data"[:31], index=False
                        )

        return xlsx_path
    except Exception:
        return None


def write_md_draft(results: list[dict], output_path: Path, time_params: dict) -> Path:
    """写入 Markdown 报告草稿。"""
    output_path.mkdir(parents=True, exist_ok=True)
    md_path = output_path / "report_draft.md"

    lines: list[str] = []
    lines.append(f"# 月度汽车市场报告 — {time_params['report_month']}\n")
    lines.append(f"> 基于 passenger_insurance 乘用车上险数据\n")
    lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append("---\n")

    groups: dict[str, list[dict]] = {}
    for r in results:
        g = r.get("group", "other")
        if g not in groups:
            groups[g] = []
        groups[g].append(r)

    group_labels: dict[str, str] = {
        "overall_market": "## 一、整体市场概览",
        "premium_market": "## 二、中高端市场",
        "transaction_price": "## 三、成交价结构",
        "model_rankings": "## 四、车型排名",
        "brand_competition": "## 五、品牌竞争",
        "city_competition": "## 六、城市市场结构",
    }

    for g, queries in groups.items():
        label = group_labels.get(g, f"## {g}")
        lines.append(label)
        lines.append("")
        for r in queries:
            status_icon = {
                "success": "✅",
                "dry_run": "🔍",
                "planned": "📋",
                "error": "❌",
                "skipped": "⏭️",
            }.get(r.get("status", ""), "❓")

            lines.append(f"### {status_icon} {r['id']}: {r['title']}")
            lines.append("")
            lines.append(f"- **状态**: {r.get('status', 'N/A')}")
            lines.append(f"- **数据集**: {TABLE_LABELS.get(r.get('table', ''), r.get('table', 'N/A'))}")
            lines.append(f"- **指标**: {', '.join(r.get('metrics', []))}")
            lines.append(f"- **时间**: {r.get('time_window', {}).get('month', 'N/A')} ~ {r.get('time_window', {}).get('month_end', 'N/A')}")

            summary = r.get("summary")
            if summary:
                lines.append(f"- **摘要**: {summary}")

            error = r.get("error")
            if error:
                lines.append(f"- **错误**: {error}")

            data = r.get("data")
            if data and isinstance(data, dict):
                agg = data.get("aggregated")
                if agg:
                    for k, v in agg.items():
                        lines.append(f"- **{k}**: {v:,.0f}" if isinstance(v, (int, float)) else f"- **{k}**: {v}")

                grouped = data.get("grouped")
                if grouped and isinstance(grouped, list):
                    lines.append("")
                    lines.append("| " + " | ".join(grouped[0].keys()) + " |")
                    lines.append("| " + " | ".join(["---"] * len(grouped[0].keys())) + " |")
                    for row in grouped[:10]:
                        vals = []
                        for v in row.values():
                            if isinstance(v, float):
                                vals.append(f"{v:,.0f}")
                            else:
                                vals.append(str(v))
                        lines.append("| " + " | ".join(vals) + " |")
                    if len(grouped) > 10:
                        lines.append(f"| *... 共 {len(grouped)} 行* |")

            lines.append("")
        lines.append("---\n")

    lines.append("\n---\n")
    lines.append("*报告由 mashang_workspace/monthly-market-report Skill 自动生成*\n")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return md_path


def write_run_metadata(results: list[dict], time_params: dict, output_path: Path) -> Path:
    """写入运行元信息文件。"""
    output_path.mkdir(parents=True, exist_ok=True)
    meta_path = output_path / "run_metadata.json"

    total = len(results)
    succeeded = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "error")
    dry_run = sum(1 for r in results if r["status"] == "dry_run")
    skipped = sum(1 for r in results if r["status"] == "skipped")

    metadata = {
        "run_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "report_month": time_params["report_month"],
        "time_params": time_params,
        "total_queries": total,
        "success": succeeded,
        "failed": failed,
        "dry_run": dry_run,
        "skipped": skipped,
        "errors": [
            {"id": r["id"], "error": r.get("error")}
            for r in results if r["status"] in ("error", "skipped")
        ],
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return meta_path


# ---------------------------------------------------------------------------
# Global dry-run flag
# ---------------------------------------------------------------------------
_GLOBAL_DRY_RUN = True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    global _GLOBAL_DRY_RUN

    parser = argparse.ArgumentParser(
        description="月度汽车市场报告 — 固定 24 查询执行脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--month", required=True,
        help="报告月份，格式 YYYY-MM，例如 2026-05",
    )
    parser.add_argument(
        "--query-spec",
        default=str(WORKSPACE_ROOT / "configs" / "monthly_market_report_queries.yaml"),
        help="查询规范 YAML 文件路径",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="输出目录，默认为 outputs/monthly_market_report/YYYY-MM",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="执行模式：实际查询 passenger_insurance 数据。默认 dry-run 只解析查询规范",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="显式指定 dry-run 模式",
    )
    parser.add_argument(
        "--format", choices=["json", "terminal"], default="terminal",
        help="输出格式 (default: terminal)",
    )

    args = parser.parse_args()

    # Determine dry-run vs execute
    if args.execute:
        _GLOBAL_DRY_RUN = False
    elif args.dry_run:
        _GLOBAL_DRY_RUN = True
    else:
        _GLOBAL_DRY_RUN = True  # default to dry-run

    # 1. Compute time params
    time_params = compute_time_params(args.month)

    # 2. Load query spec
    try:
        spec = load_query_spec(args.query_spec)
    except Exception as e:
        err_contract = build_error_contract(
            script="research_scripts/market_report/run_monthly_market_report.py",
            command=f"--month {args.month}",
            error_message=f"加载查询规范失败: {e}",
        )
        print(json.dumps(err_contract, ensure_ascii=False, indent=2))
        sys.exit(1)

    queries = spec.get("queries", [])
    if not queries:
        err_contract = build_error_contract(
            script="research_scripts/market_report/run_monthly_market_report.py",
            command=f"--month {args.month}",
            error_message="查询规范中未找到 queries 定义",
        )
        print(json.dumps(err_contract, ensure_ascii=False, indent=2))
        sys.exit(1)

    # 3. Determine output dir
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = WORKSPACE_ROOT / "outputs" / "monthly_market_report" / args.month

    # 4. Get available tables (for execute mode)
    available_tables = []
    if not _GLOBAL_DRY_RUN:
        try:
            available_tables = list_passenger_insurance_tables()
        except Exception as e:
            print(f"[WARN] 无法获取可用表列表: {e}", file=sys.stderr)

    # 5. Execute queries
    results: list[dict] = []
    for q in queries:
        qid = q.get("id", "unknown")
        q["group"] = q.get("group", "other")
        result = execute_query(q, time_params, available_tables)
        results.append(result)

        if args.format == "terminal":
            icon = "🔍" if result["status"] == "dry_run" else "✅" if result["status"] == "success" else "❌" if result["status"] == "error" else "⏭️"
            print(f"  {icon} [{result['status'].upper()}] {qid}: {result.get('summary', '') or result.get('error', '')}")

    # 6. Write outputs
    try:
        json_path = write_json_output(results, output_dir, time_params, spec)
        print(f"\n  JSON: {json_path}")
    except Exception as e:
        print(f"[ERROR] 写入 JSON 失败: {e}", file=sys.stderr)

    try:
        xlsx_path = write_xlsx_output(results, output_dir)
        if xlsx_path:
            print(f"  XLSX: {xlsx_path}")
    except Exception as e:
        print(f"[WARN] 写入 XLSX 失败: {e}", file=sys.stderr)

    try:
        md_path = write_md_draft(results, output_dir, time_params)
        print(f"  MD:   {md_path}")
    except Exception as e:
        print(f"[WARN] 写入 MD 失败: {e}", file=sys.stderr)

    try:
        meta_path = write_run_metadata(results, time_params, output_dir)
        print(f"  META: {meta_path}")
    except Exception as e:
        print(f"[WARN] 写入 metadata 失败: {e}", file=sys.stderr)

    # 7. Print summary
    total = len(results)
    succeeded = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] in ("skipped", "dry_run"))

    print(f"\n{'='*60}")
    print(f"  月度市场报告 — {args.month}")
    print(f"  {'='*60}")
    print(f"  模式: {'EXECUTE' if not _GLOBAL_DRY_RUN else 'DRY RUN'}")
    print(f"  总计: {total} queries")
    print(f"  成功: {succeeded}")
    print(f"  失败: {failed}")
    print(f"  跳过/计划: {skipped}")
    print(f"  输出: {output_dir}")
    if args.format == "json":
        succeeded_contract = build_success_contract(
            script="research_scripts/market_report/run_monthly_market_report.py",
            command=f"--month {args.month}",
            scope={
                "data_source": "passenger_insurance",
                "time_window": {"report_month": args.month},
            },
            result={"summary": f"月报 {args.month}: {succeeded} success, {failed} failed, {skipped} skipped/planned"},
        )
        print(json.dumps(succeeded_contract, ensure_ascii=False, indent=2))
    else:
        # Print terminal summary
        succeeded_list = [r for r in results if r["status"] == "success"]
        failed_list = [r for r in results if r["status"] == "error"]
        skipped_list = [r for r in results if r["status"] in ("skipped", "dry_run")]

        if failed_list:
            print(f"\n  ❌ 失败查询:")
            for r in failed_list:
                print(f"    - {r['id']}: {r.get('error', '')}")

        if succeeded_list:
            print(f"\n  ✅ 成功查询:")
            for r in succeeded_list[:5]:
                print(f"    - {r['id']}: {r.get('summary', '')}")
            if len(succeeded_list) > 5:
                print(f"    ... 共 {len(succeeded_list)} 个")


if __name__ == "__main__":
    main()
