import datetime
import json

from openai import OpenAI

from agent.llm_config import DEEPSEEK_CHAT_MODEL
from agent.state import AgentState

SUPPORTED_FACT_TYPES = {
    "metric_value",
    "time_grouped_metric",
    "trend_summary",
    "comparison_result",
    "dimension_breakdown",
    "share_summary",
    "ranking_result",
    "distribution_summary",
    "contribution_summary",
}


def _extract_json_content(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return raw


def _sanitize_facts(
    facts: object,
    structured_blocks_payload: list[dict],
) -> tuple[list[dict], dict]:
    missing_info: dict = {}
    if not isinstance(facts, list):
        return ([], {"invalid_facts_type": {"expected": "list", "got": str(type(facts).__name__)}})

    allowed_block_ids = set()
    for b in structured_blocks_payload:
        if not isinstance(b, dict):
            continue
        bid = b.get("block_id")
        if isinstance(bid, str) and bid:
            allowed_block_ids.add(bid)

    cleaned: list[dict] = []
    dropped: list[dict] = []
    for f in facts:
        if not isinstance(f, dict) or not f:
            continue
        src_obj = f.get("source") if isinstance(f.get("source"), dict) else {}
        src = src_obj.get("block_id") or f.get("source_block_id")
        ftype = f.get("fact_type")
        if not isinstance(src, str) or not src:
            dropped.append({"reason": "missing_source_block_id", "fact": f})
            continue
        if allowed_block_ids and src not in allowed_block_ids:
            dropped.append({"reason": "unknown_source_block_id", "fact": f})
            continue
        if not isinstance(ftype, str) or not ftype:
            dropped.append({"reason": "missing_fact_type", "fact": f})
            continue
        if ftype not in SUPPORTED_FACT_TYPES:
            dropped.append({"reason": "unsupported_fact_type", "fact": f})
            continue
        if not isinstance(f.get("source"), dict):
            f["source"] = {"block_id": src}
        if f.get("values") is not None and not isinstance(f.get("values"), dict):
            dropped.append({"reason": "invalid_values_type", "fact": f})
            continue
        if f.get("conclusion") is not None and not isinstance(f.get("conclusion"), dict):
            dropped.append({"reason": "invalid_conclusion_type", "fact": f})
            continue
        cleaned.append(f)

    if dropped:
        missing_info["dropped_facts"] = dropped[:20]
    return (cleaned, missing_info)


def _build_fact_source(block) -> dict:
    execution_meta = getattr(block, "execution_meta", None)
    return {
        "block_id": getattr(block, "block_id", None),
        "step": getattr(block, "step", None),
        "block_type": getattr(block, "block_type", None),
        "route": execution_meta.get("route") if isinstance(execution_meta, dict) else None,
    }


def _get_metric_name(result: dict) -> str:
    return result.get("metric_alias") or result.get("metric") or ""


def _get_dataset_name(plan: dict) -> str | None:
    return plan.get("dataset")


def _build_time_range(result: dict, plan: dict) -> dict | None:
    time = plan.get("time") if isinstance(plan.get("time"), dict) else {}
    start = time.get("start") or result.get("date_start")
    end = time.get("end") or result.get("date_end")
    window_days = result.get("window_days")
    label = None
    if isinstance(window_days, int) and window_days > 0:
        label = f"近{window_days}日"
    if not start and not end:
        return None
    return {"start": start, "end": end, "grain": "day", "label": label}


def _detect_dimension_field(rows: list[dict]) -> str | None:
    if not rows or not isinstance(rows[0], dict):
        return None
    return next((k for k in rows[0] if k not in ("count", "share")), None)


_DATA_EXCLUDE = {
    "type", "metric_alias", "metric", "window_days", "total_days", "window_weeks", "total_weeks",
    "top_k", "comparison_method", "date_start", "date_end",
    "city_field", "age_field", "identity_field",
    "mapping_unknown_count", "mapping_unknown_ratio",
    "first_date", "last_date", "time_field",
    "reference_date", "reference_value",
}

# ── Field Recognition Dictionaries (Chinese-aware) ──────────────────────

TIME_COL_KEYWORDS = [
    "date", "day", "week", "month", "year",
    "日期", "日", "天", "周", "月份", "月", "年份", "年",
]

METRIC_COL_KEYWORDS = [
    "count", "cnt", "num", "total", "sum", "volume", "amount", "value",
    "锁单", "订单", "线索", "试驾", "销量", "销售", "数量", "总数", "人数",
]

DIMENSION_COL_KEYWORDS = [
    "dimension", "category", "model", "series", "config", "brand",
    "city", "province", "region", "store", "channel", "gender",
    "age_group", "tier", "cohort", "segment", "group", "label",
    "车型", "车系", "配置", "品牌", "城市", "省份", "大区",
    "门店", "渠道", "性别", "年龄段",
]

SHARE_COL_KEYWORDS = [
    "占比", "share", "ratio", "percent", "percentage", "份额",
    "率", "rate", "比例", "渗透率", "转化率",
]

RANK_COL_KEYWORDS = [
    "rank", "ranking", "top", "排名", "排行", "名次",
]

COMPARISON_COL_KEYWORDS = [
    "baseline", "current", "previous", "target",
    "delta", "diff", "change", "growth",
    "同比", "环比", "差值", "变化", "增长", "较上",
]

DISTRIBUTION_COL_KEYWORDS = [
    "mean", "avg", "median", "std", "min", "max",
    "p25", "p50", "p75", "percentile", "quantile",
    "less_count", "le_count", "matched_days", "matched_ratio",
    "方差", "标准差", "分位", "均值", "平均", "中位数", "最大", "最小",
]


def _match_keywords(col: str, keywords: list[str]) -> bool:
    col_lower = col.lower()
    return any(kw.lower() in col_lower for kw in keywords)


def _extract_columns_from(result) -> tuple[list[str], list[dict] | None]:
    try:
        import pandas as pd
        if isinstance(result, pd.DataFrame):
            cols = [c for c in result.columns if c not in _DATA_EXCLUDE]
            return cols, result.to_dict(orient="records")
    except ImportError:
        pass
    if isinstance(result, dict):
        flat_cols = [k for k in result
                     if k not in _DATA_EXCLUDE and k != "evidence_hints"
                     and not isinstance(result[k], (list, dict))]
        rows_data = result.get("rows")
        if isinstance(rows_data, list) and rows_data:
            row_cols = [c for c in rows_data[0] if c not in _DATA_EXCLUDE]
            return list(dict.fromkeys(flat_cols + row_cols)), rows_data
        for series_key in ("daily_rows", "weekly_rows", "weekend_rows"):
            sr = result.get(series_key)
            if isinstance(sr, list) and sr:
                row_cols = [c for c in sr[0] if c not in _DATA_EXCLUDE]
                return list(dict.fromkeys(flat_cols + row_cols)), sr
        flat = result.get("result_summary") if isinstance(result.get("result_summary"), dict) else result
        cols = [k for k in flat if k not in _DATA_EXCLUDE and not isinstance(flat[k], list) and not isinstance(flat[k], dict) and k != "evidence_hints"]
        return cols, [flat] if cols else []
    return [], []


def _detect_time_columns(columns: list[str]) -> list[str]:
    return [c for c in columns if _match_keywords(c, TIME_COL_KEYWORDS) or c.endswith(("_date", "_time", "_start", "_end"))]


def _detect_metric_columns(columns: list[str]) -> list[str]:
    return [c for c in columns if _match_keywords(c, METRIC_COL_KEYWORDS)]


def _detect_dimension_columns(columns: list[str]) -> list[str]:
    return [c for c in columns if _match_keywords(c, DIMENSION_COL_KEYWORDS)]


def _detect_share_columns(columns: list[str]) -> list[str]:
    return [c for c in columns if _match_keywords(c, SHARE_COL_KEYWORDS) or c.endswith(("_share", "_pct", "_rate"))]


def _detect_rank_columns(columns: list[str]) -> list[str]:
    return [c for c in columns if _match_keywords(c, RANK_COL_KEYWORDS) or c.endswith(("_rank", "_ranking"))]


def _detect_comparison_columns(columns: list[str]) -> list[str]:
    out = [c for c in columns if _match_keywords(c, COMPARISON_COL_KEYWORDS)]
    out.extend(c for c in columns if c.endswith(("_current", "_compare", "_diff", "_diff_pct", "_pct_change")))
    return list(dict.fromkeys(out))


def _detect_distribution_columns(columns: list[str]) -> list[str]:
    return [c for c in columns if _match_keywords(c, DISTRIBUTION_COL_KEYWORDS) or c.endswith(("_std", "_variance", "_quantile"))]


def _make_fact(
    block_id: str,
    fact_type: str,
    content: str,
    metadata: dict,
    source: dict,
    evidence_type: str,
) -> dict:
    return {
        "fact_id": f"fact_{block_id}_{fact_type}",
        "fact_type": fact_type,
        "content": content,
        "metadata": metadata,
        "source": source,
        "evidence_type": evidence_type,
    }


def _build_column_based_facts(block, result, plan: dict, time_range: dict | None = None) -> list[dict]:
    declared_hints = None
    if isinstance(result, dict):
        declared_hints = result.get("evidence_hints")
    declared_types: set[str] = set()
    if isinstance(declared_hints, dict):
        ft = declared_hints.get("fact_types")
        if isinstance(ft, list):
            declared_types = set(ft)
    use_declared = bool(declared_types)

    cols, rows = _extract_columns_from(result)
    if not cols and not use_declared:
        return []

    time_cols = _detect_time_columns(cols)
    metric_cols = _detect_metric_columns(cols)
    dim_cols = _detect_dimension_columns(cols)
    share_cols = _detect_share_columns(cols)
    rank_cols = _detect_rank_columns(cols)
    comp_cols = _detect_comparison_columns(cols)
    dist_cols = _detect_distribution_columns(cols)

    hints_metric = declared_hints.get("metric") if isinstance(declared_hints, dict) else None
    metric = hints_metric or _get_metric_name(result if isinstance(result, dict) else {})
    dataset = _get_dataset_name(plan)
    source = _build_fact_source(block)
    block_id = source["block_id"]
    block_type = source["block_type"]

    has_time = bool(time_cols)
    has_dim = bool(dim_cols)
    has_share = bool(share_cols)
    has_rank = bool(rank_cols)
    has_comp = bool(comp_cols)
    has_dist = bool(dist_cols)
    has_metric = bool(metric_cols)

    row_keys: set[str] = set()
    if rows:
        row_keys = set(rows[0].keys())
    row_metric_cols = [c for c in metric_cols if c in row_keys]
    row_dim_cols = [c for c in dim_cols if c in row_keys]

    facts: list[dict] = []

    def _should(fact_type: str) -> bool:
        return not use_declared or fact_type in declared_types

    # ── comparison_result ────────────────────────────────────────────
    if has_comp and _should("comparison_result"):
        cv = {}
        for k in comp_cols:
            v = rows[0].get(k) if rows else None
            if v is None and isinstance(result, dict):
                v = result.get(k)
            if v is not None:
                cv[k] = v
        if cv:
            hints = declared_hints if isinstance(declared_hints, dict) else {}
            ct = hints.get("comparison_type") or (block_type if block_type in ("yoy", "wow", "dod") else None)
            cl = {"yoy": "同比", "wow": "环比", "dod": "日环比"}.get(ct) if ct else None
            current_val = next((cv[k] for k in cv if k.endswith("_current") or k == "current"), None)
            compare_val = next((cv[k] for k in cv if k.endswith("_compare") or k == "previous"), None)
            content = f"{metric}{cl or '对比'}：当前{current_val or '?'}，对比{compare_val or '?'}"
            facts.append(_make_fact(block_id, "comparison_result", content, {
                "metric": metric, "comparison_type": ct, "values": cv, "dimension": dim_cols[0] if dim_cols and len(dim_cols) == 1 else None,
            }, source, "descriptive_comparison"))

    # ── distribution_summary ─────────────────────────────────────────
    if has_dist and _should("distribution_summary"):
        dv = {}
        for k in dist_cols:
            v = rows[0].get(k) if rows else None
            if v is None and isinstance(result, dict):
                v = result.get(k)
            if v is not None:
                dv[k] = v
        if dv:
            top_keys = list(dv.keys())[:3]
            content = f"{metric}分布：{'，'.join(f'{k}={dv[k]}' for k in top_keys)}"
            facts.append(_make_fact(block_id, "distribution_summary", content, {
                "metric": metric, "values": dv,
            }, source, "descriptive_distribution"))

    if not rows:
        return facts

    n = len(rows)

    # ── share_summary ────────────────────────────────────────────────
    if has_dim and has_share and _should("share_summary"):
        dim_col = row_dim_cols[0] if row_dim_cols else dim_cols[0]
        share_col = share_cols[0]
        top_row = rows[0]
        top_label = str(top_row.get(dim_col, ""))
        top_share = top_row.get(share_col)
        content = f"按{dim_col}拆解{metric}占比，共{n}个分组"
        if top_label and top_share is not None:
            content += f"，最高={top_label}({top_share:.1%})"
        meta = {"dimension": dim_col, "metric": metric, "row_count": n}
        if isinstance(result, dict) and result.get("total") is not None:
            meta["total"] = result["total"]
        facts.append(_make_fact(block_id, "share_summary", content, meta, source, "descriptive_share"))

    # ── dimension_breakdown ──────────────────────────────────────────
    if has_dim and has_metric and _should("dimension_breakdown"):
        dim_col = row_dim_cols[0] if row_dim_cols else dim_cols[0]
        metric_col = row_metric_cols[0] if row_metric_cols else metric_cols[0]
        content = f"结果按{dim_col}拆解{metric}，共{n}个分组"
        facts.append(_make_fact(block_id, "dimension_breakdown", content, {
            "dimension_fields": [dim_col], "metric_fields": [metric_col], "row_count": n,
        }, source, "descriptive_breakdown"))

    # ── share_summary (deterministic fallback, computed from dimension values) ──
    if has_dim and has_metric and not has_share and _should("share_summary") and rows:
        dim_col = row_dim_cols[0] if row_dim_cols else dim_cols[0]
        metric_col = row_metric_cols[0] if row_metric_cols else metric_cols[0]
        numeric_values = [r.get(metric_col) for r in rows if isinstance(r.get(metric_col), (int, float))]
        if numeric_values:
            total = sum(numeric_values)
            top_row = rows[0]
            top_label = str(top_row.get(dim_col, ""))
            top_val = top_row.get(metric_col, 0)
            top_share = top_val / total if total > 0 else 0
            content = f"按{dim_col}拆解{metric}占比，共{n}个分组"
            if top_label and total > 0:
                content += f"，最高={top_label}({top_share:.1%})"
            meta = {"dimension": dim_col, "metric": metric, "row_count": n, "total": total}
            facts.append(_make_fact(block_id, "share_summary", content, meta, source, "descriptive_share"))

    # ── ranking_result ───────────────────────────────────────────────
    has_topk = bool(result.get("top_k")) if isinstance(result, dict) else False
    if has_dim and has_metric and (has_rank or has_topk or n >= 3) and _should("ranking_result"):
        dim_col = row_dim_cols[0] if row_dim_cols else dim_cols[0]
        metric_col = row_metric_cols[0] if row_metric_cols else metric_cols[0]
        top_k = result.get("top_k") if isinstance(result, dict) else None
        top_n = top_k or n
        first_label = str(rows[0].get(dim_col, ""))
        first_val = rows[0].get(metric_col)
        content = f"按{metric_col}排名，TOP{top_n}"
        if first_label and first_val is not None:
            content += f"：第1名={first_label}({first_val})"
        facts.append(_make_fact(block_id, "ranking_result", content, {
            "rank_field": dim_col, "top_k": top_n, "row_count": n,
        }, source, "descriptive_ranking"))

    # ── time_grouped_metric ──────────────────────────────────────────
    if has_time and has_metric and _should("time_grouped_metric"):
        time_col = time_cols[0]
        metric_col = row_metric_cols[0] if row_metric_cols else metric_cols[0]
        grain = "day"
        if time_col in ("week_start",):
            grain = "week"
        elif time_col in ("weekend_start",):
            grain = "weekend"
        hints_grain = declared_hints.get("grain") if isinstance(declared_hints, dict) else None
        if hints_grain:
            grain = hints_grain
        content = f"按{grain}统计{metric}，共{n}个周期"
        tr = dict(time_range) if time_range else None
        if tr:
            tr["grain"] = grain
        facts.append(_make_fact(block_id, "time_grouped_metric", content, {
            "metric": metric, "grain": grain, "period_count": n, "time_range": tr,
        }, source, "descriptive_time_series"))

    # ── metric_value ──────────────────────────────────────────────────
    if has_metric and (_should("metric_value") if use_declared else (not has_dim and not has_time)):
        metric_col = (row_metric_cols[0] if row_metric_cols else metric_cols[0]) if metric_cols else None
        primary = rows[0].get(metric_col) if rows and metric_col else None
        if primary is None and isinstance(result, dict):
            primary = result.get(metric_col)
        if primary is not None:
            extras = {}
            for mc in metric_cols[1:]:
                v = rows[0].get(mc) if rows else None
                if v is None and isinstance(result, dict):
                    v = result.get(mc)
                if v is not None:
                    extras[mc] = v
            content = f"当前{metric_col}值为{primary}"
            facts.append(_make_fact(block_id, "metric_value", content, {
                "metric": metric, metric_col: primary, **extras,
            }, source, "descriptive_metric"))

    return facts

    # share_summary
    if has_dim and has_share and _should("share_summary"):
        dim_col = dim_cols[0]
        share_col = share_cols[0]
        share_rows = []
        for r in rows:
            label = r.get(dim_col)
            if label is not None:
                share_rows.append({"label": label, "count": r.get("count"), "share": r.get(share_col)})
        others = result.get("others") if isinstance(result, dict) else None
        if isinstance(others, dict):
            share_rows.append({"label": "其他", "count": others.get("count"), "share": others.get("share")})
        if share_rows:
            total = result.get("total") if isinstance(result, dict) else None
            facts.append({
                "fact_id": f"fact_{block_id}_share_summary",
                "fact_type": "share_summary",
                "metric": metric,
                "dataset": dataset,
                "dimension": dim_col,
                "time_range": time_range,
                "values": {"total": total, "rows": share_rows},
                "conclusion": None,
                "source": source,
                "evidence_type": "descriptive_share",
            })

    # dimension_breakdown
    if has_dim and has_metric and _should("dimension_breakdown"):
        dim_col = dim_cols[0]
        metric_col = row_metric_cols[0] if row_metric_cols else metric_cols[0]
        breakdown_rows = []
        for r in rows:
            label = r.get(dim_col)
            val = r.get(metric_col)
            if label is not None and val is not None:
                breakdown_rows.append({dim_col: label, "count": val, "share": r.get(share_cols[0]) if share_cols else None})
        facts.append({
            "fact_id": f"fact_{block_id}_dimension_breakdown",
            "fact_type": "dimension_breakdown",
            "metric": metric,
            "dataset": dataset,
            "dimension": dim_col,
            "time_range": time_range,
            "values": {"dimension_field": dim_col, "rows": breakdown_rows},
            "conclusion": None,
            "source": source,
            "evidence_type": "descriptive_breakdown",
        })

    # ranking_result
    has_topk = bool(result.get("top_k")) if isinstance(result, dict) else False
    if has_dim and has_metric and (has_rank or has_topk or len(rows) >= 3) and _should("ranking_result"):
        dim_col = dim_cols[0]
        metric_col = row_metric_cols[0] if row_metric_cols else metric_cols[0]
        rankings = []
        for i, r in enumerate(rows):
            label = r.get(dim_col)
            val = r.get(metric_col)
            if label is not None and val is not None:
                rankings.append({"rank": i + 1, "label": label, "value": val})
        facts.append({
            "fact_id": f"fact_{block_id}_ranking_result",
            "fact_type": "ranking_result",
            "metric": metric,
            "dataset": dataset,
            "dimension": dim_col,
            "time_range": time_range,
            "values": {"rank_field": dim_col, "rankings": rankings, "top_k": len(rankings)},
            "conclusion": None,
            "source": source,
            "evidence_type": "descriptive_ranking",
        })

    # time_grouped_metric
    if has_time and has_metric and _should("time_grouped_metric"):
        time_col = time_cols[0]
        metric_col = row_metric_cols[0] if row_metric_cols else metric_cols[0]
        series = []
        for r in rows:
            t = r.get(time_col)
            v = r.get(metric_col)
            if t is not None and v is not None:
                series.append({"date": str(t)[:10], "value": v})
        grain = "day"
        if time_col in ("week_start",):
            grain = "week"
        elif time_col in ("weekend_start",):
            grain = "weekend"
        hints_grain = declared_hints.get("grain") if isinstance(declared_hints, dict) else None
        if hints_grain:
            grain = hints_grain
        tr = dict(time_range) if time_range else None
        if tr:
            tr["grain"] = grain
        facts.append({
            "fact_id": f"fact_{block_id}_time_grouped_metric",
            "fact_type": "time_grouped_metric",
            "metric": metric,
            "dataset": dataset,
            "dimension": None,
            "time_range": tr,
            "values": {"time_series": series, "grain": grain},
            "conclusion": None,
            "source": source,
            "evidence_type": "descriptive_time_series",
        })

    # metric_value (only when no dims or time series unless declared)
    if has_metric and (_should("metric_value") if use_declared else (not has_dim and not has_time)):
        metric_col = (row_metric_cols[0] if row_metric_cols else metric_cols[0]) if metric_cols else None
        primary = rows[0].get(metric_col) if rows and metric_col else None
        if primary is None and isinstance(result, dict):
            primary = result.get(metric_col)
        if primary is not None:
            values = {metric_col: primary}
            for mc in metric_cols[1:]:
                v = rows[0].get(mc) if rows else None
                if v is None and isinstance(result, dict):
                    v = result.get(mc)
                if v is not None:
                    values[mc] = v
            facts.append({
                "fact_id": f"fact_{block_id}_metric_value",
                "fact_type": "metric_value",
                "metric": metric,
                "dataset": dataset,
                "dimension": None,
                "time_range": time_range,
                "values": values,
                "conclusion": None,
                "source": source,
                "evidence_type": "descriptive_metric",
            })

    return facts


def _build_share_breakdown_facts(block, result: dict, plan: dict, time_range: dict | None = None) -> list[dict]:
    metric = _get_metric_name(result)
    dataset = _get_dataset_name(plan)
    if time_range is None:
        time_range = _build_time_range(result, plan)
    source = _build_fact_source(block)
    block_id = source["block_id"]

    rows = result.get("rows")
    if not isinstance(rows, list) or not rows:
        return []
    dim_field = _detect_dimension_field(rows)
    if not dim_field:
        return []
    total = result.get("total")
    top_k = result.get("top_k")
    n = len(rows)
    first_row = rows[0]

    facts: list[dict] = []

    # share_summary
    top_label = str(first_row.get(dim_field, ""))
    top_share = first_row.get("share")
    content = f"按{dim_field}拆解{metric}占比，共{n}个分组"
    if top_label and top_share is not None:
        content += f"，最高={top_label}({top_share:.1%})"
    meta = {"dimension": dim_field, "metric": metric, "row_count": n}
    if total is not None:
        meta["total"] = total
    facts.append(_make_fact(block_id, "share_summary", content, meta, source, "descriptive_share"))

    # dimension_breakdown
    content = f"结果按{dim_field}拆解{metric}，共{n}个分组"
    facts.append(_make_fact(block_id, "dimension_breakdown", content, {
        "dimension_fields": [dim_field], "metric_fields": [metric], "row_count": n,
    }, source, "descriptive_breakdown"))

    # ranking_result
    if top_k or n >= 3:
        first_val = first_row.get("count")
        top_n = top_k or n
        content = f"按{metric}排名，TOP{top_n}"
        if top_label and first_val is not None:
            content += f"：第1名={top_label}({first_val})"
        facts.append(_make_fact(block_id, "ranking_result", content, {
            "rank_field": dim_field, "top_k": top_n, "row_count": n,
        }, source, "descriptive_ranking"))

    return facts


def _build_stat_metric_value_facts(block, result: dict, plan: dict, time_range: dict | None) -> list[dict]:
    metric = _get_metric_name(result)
    dataset = _get_dataset_name(plan)
    source = _build_fact_source(block)
    block_id = source["block_id"]
    block_type = source["block_type"]

    value_key_map = {
        "daily_mean": "daily_mean",
        "daily_mean_median": "daily_mean",
        "weekly_decline_ratio": "decline_ratio",
        "daily_threshold_count": "matched_ratio",
        "daily_percentile_rank": "percentile_rank",
        "weekend_percentile_rank": "percentile_rank",
        "weekday_percentile_rank": "percentile_rank",
    }
    value_key = value_key_map.get(block_type)
    primary_value = result.get(value_key) if value_key else None
    if primary_value is None:
        return []

    meta: dict = {value_key: primary_value}
    if block_type == "daily_mean_median":
        meta["median"] = result.get("daily_median")
    if block_type == "daily_threshold_count":
        meta["threshold"] = result.get("threshold")
        meta["matched_days"] = result.get("matched_days")
        meta["total_days"] = result.get("total_days")
    if block_type in ("daily_percentile_rank", "weekday_percentile_rank"):
        meta["reference_value"] = result.get("reference_value")
    if block_type == "weekend_percentile_rank":
        meta["reference_value"] = result.get("reference_value")
    if block_type == "weekly_decline_ratio":
        meta["decline_weeks"] = result.get("decline_weeks")
        meta["total_weeks"] = result.get("total_weeks")

    value_labels = {"daily_mean": "日均", "daily_mean_median": "日均", "matched_ratio": "达标率", "decline_ratio": "下降比例", "percentile_rank": "百分位"}
    label = value_labels.get(value_key or "", "") or value_key or ""
    content = f"{metric}{label}值为{primary_value}"
    if block_type == "daily_mean_median" and meta.get("median") is not None:
        content += f"，中位数为{meta['median']}"

    return [_make_fact(block_id, "metric_value", content, meta, source, "descriptive_metric")]


def _build_time_series_facts(block, result: dict, plan: dict, time_range: dict | None) -> list[dict]:
    metric = _get_metric_name(result)
    dataset = _get_dataset_name(plan)
    source = _build_fact_source(block)
    block_id = source["block_id"]
    block_type = source["block_type"]

    grain = "day"
    row_count = 0

    daily_rows = result.get("daily_rows")
    if isinstance(daily_rows, list):
        row_count = len(daily_rows)
        grain = "day"
    if row_count == 0 and block_type == "weekly_decline_ratio":
        weekly_rows = result.get("weekly_rows")
        if isinstance(weekly_rows, list):
            row_count = len(weekly_rows)
            grain = "week"
    if row_count == 0 and block_type == "weekend_percentile_rank":
        weekend_rows = result.get("weekend_rows")
        if isinstance(weekend_rows, list):
            row_count = len(weekend_rows)
            grain = "weekend"

    if row_count == 0:
        return []

    tr = dict(time_range) if time_range else None
    if tr:
        tr["grain"] = grain

    content = f"按{grain}统计{metric}，共{row_count}个周期"
    return [_make_fact(block_id, "time_grouped_metric", content, {
        "metric": metric, "grain": grain, "period_count": row_count, "time_range": tr,
    }, source, "descriptive_time_series")]


def _build_numeric_ratio_facts(block, result: dict, plan: dict, time_range: dict | None = None) -> list[dict]:
    metric = _get_metric_name(result)
    dataset = _get_dataset_name(plan)
    source = _build_fact_source(block)
    block_id = source["block_id"]

    current = result.get("current")
    base = result.get("base")
    direction = result.get("direction", "")
    content = f"{metric}{direction}：当前{current}，基准{base}"
    pct = result.get("ratio_pct")
    if pct is not None:
        content += f"，变化{abs(pct):g}%"
    return [_make_fact(block_id, "metric_value", content, {
        "value": current, "base": base, "delta": result.get("delta"),
        "ratio": result.get("ratio"), "ratio_pct": pct, "direction": direction,
    }, source, "descriptive_metric")]


def _build_trend_summary_facts(block, result: dict, plan: dict, time_range: dict | None = None) -> list[dict]:
    metric = _get_metric_name(result)
    dataset = _get_dataset_name(plan)
    source = _build_fact_source(block)
    block_id = source["block_id"]
    if time_range is None:
        time_plan = plan.get("time") if isinstance(plan.get("time"), dict) else {}
        window_days = result.get("window_days")
        label = None
        if isinstance(window_days, int) and window_days > 0:
            label = f"近{window_days}日"
        time_range = {"start": time_plan.get("start"), "end": time_plan.get("end"), "grain": "day", "label": label}

    direction = result.get("direction", "")
    total_change = result.get("total_change")
    streak = result.get("streak_direction", "")
    streak_len = result.get("streak_length", 0)
    content = f"{metric}趋势{direction}"
    if total_change is not None:
        content += f"，近{result.get('window_days', '?')}日变化{total_change:+.1%}"
    if streak_len:
        content += f"，连续{streak_len}日{streak}"
    return [_make_fact(block_id, "trend_summary", content, {
        "metric": metric, "direction": direction, "total_change": total_change,
        "slope": result.get("slope"), "latest": result.get("latest"),
        "mean": result.get("mean"), "median": result.get("median"),
        "std": result.get("std"), "cv": result.get("cv"),
        "max_value": result.get("max_value"), "min_value": result.get("min_value"),
        "latest_position": result.get("latest_position"),
        "latest_percentile_rank": result.get("latest_percentile_rank"),
        "streak_direction": streak, "streak_length": streak_len,
        "recent_direction": result.get("recent_direction"),
        "time_range": time_range,
    }, source, "descriptive_trend")]


def _build_contribution_summary_facts(block, result: dict, plan: dict, time_range: dict | None = None) -> list[dict]:
    metric = _get_metric_name(result)
    dataset = _get_dataset_name(plan)
    source = _build_fact_source(block)
    block_id = source["block_id"]
    if time_range is None:
        time_plan = plan.get("time") if isinstance(plan.get("time"), dict) else {}
        window_days = result.get("window_days")
        label = None
        if isinstance(window_days, int) and window_days > 0:
            label = f"近{window_days}日"
        time_range = {"start": time_plan.get("start"), "end": time_plan.get("end"), "grain": "day", "label": label}

    dim_field = result.get("dimension_field")
    rows = result.get("rows")
    top10_share = None
    others_share = None
    if isinstance(result.get("total_delta"), (int, float)) and isinstance(rows, list):
        total_delta = float(result.get("total_delta") or 0.0)
        top_delta = float(sum(float((r.get("delta") or 0.0)) for r in rows[:10] if isinstance(r, dict)))
        top10_share = None if total_delta == 0.0 else float(top_delta / total_delta)
        others_obj = result.get("others") if isinstance(result.get("others"), dict) else {}
        others_share = others_obj.get("contribution_share")
    content = ""
    if isinstance(dim_field, str) and top10_share is not None:
        content = f"按{dim_field}拆解{metric}变化贡献，前10项合计贡献{top10_share:.1%}"
        if others_share is not None:
            content += f"，其余项贡献{others_share:.1%}"

    baseline_period = result.get("baseline_period") if isinstance(result.get("baseline_period"), dict) else {}
    target_period = result.get("target_period") if isinstance(result.get("target_period"), dict) else {}
    if not baseline_period and isinstance(result.get("first_date"), str):
        try:
            first_date = datetime.date.fromisoformat(str(result.get("first_date"))[:10])
            baseline_period = {"start": first_date.isoformat(), "end": (first_date + datetime.timedelta(days=1)).isoformat()}
        except Exception:
            baseline_period = {}
    if not target_period and isinstance(result.get("last_date"), str):
        try:
            last_date = datetime.date.fromisoformat(str(result.get("last_date"))[:10])
            target_period = {"start": last_date.isoformat(), "end": (last_date + datetime.timedelta(days=1)).isoformat()}
        except Exception:
            target_period = {}

    return [_make_fact(block_id, "contribution_summary", content or f"按{dim_field or '?'}拆解{metric}变化贡献", {
        "metric": metric, "dimension": dim_field, "time_range": time_range,
        "comparison_method": result.get("comparison_method") or "first_vs_last",
        "baseline_period": baseline_period or None, "target_period": target_period or None,
        "first_total": result.get("first_total"), "last_total": result.get("last_total"),
        "total_delta": result.get("total_delta"),
        "top10_contribution_share": top10_share, "others_contribution_share": others_share,
    }, source, "descriptive_contribution")]


# Fallback evidence_hints for block_types when not embedded in result dict
_FALLBACK_HINTS: dict[str, dict] = {
    "trend_summary": {"fact_types": ["trend_summary", "time_grouped_metric"]},
    "daily_percentile_rank": {"fact_types": ["metric_value", "distribution_summary", "time_grouped_metric"]},
    "weekend_percentile_rank": {"fact_types": ["metric_value", "distribution_summary", "time_grouped_metric"]},
    "weekday_percentile_rank": {"fact_types": ["metric_value", "distribution_summary", "time_grouped_metric"]},
    "daily_mean": {"fact_types": ["metric_value", "time_grouped_metric"]},
    "daily_mean_median": {"fact_types": ["metric_value", "time_grouped_metric"]},
    "weekly_decline_ratio": {"fact_types": ["metric_value", "time_grouped_metric"]},
    "daily_threshold_count": {"fact_types": ["metric_value", "time_grouped_metric"]},
    "category_share": {"fact_types": ["share_summary", "dimension_breakdown", "ranking_result"]},
    "province_topk_share": {"fact_types": ["share_summary", "dimension_breakdown", "ranking_result"]},
    "city_tier_distribution": {"fact_types": ["share_summary", "dimension_breakdown"]},
    "age_cohort_distribution": {"fact_types": ["share_summary", "dimension_breakdown"]},
    "contribution_summary": {"fact_types": ["contribution_summary"]},
    "yoy": {"fact_types": ["comparison_result"], "comparison_type": "yoy"},
    "wow": {"fact_types": ["comparison_result"], "comparison_type": "wow"},
    "dod": {"fact_types": ["comparison_result"], "comparison_type": "dod"},
    "numeric_ratio": {"fact_types": ["metric_value"]},
}

_BLOCK_HANDLERS = {
    "trend_summary": _build_trend_summary_facts,
    "contribution_summary": _build_contribution_summary_facts,
    "category_share": _build_share_breakdown_facts,
    "province_topk_share": _build_share_breakdown_facts,
    "city_tier_distribution": _build_share_breakdown_facts,
    "age_cohort_distribution": _build_share_breakdown_facts,
    "daily_mean": _build_stat_metric_value_facts,
    "daily_mean_median": _build_stat_metric_value_facts,
    "daily_threshold_count": _build_stat_metric_value_facts,
    "daily_percentile_rank": _build_stat_metric_value_facts,
    "weekend_percentile_rank": _build_stat_metric_value_facts,
    "weekday_percentile_rank": _build_stat_metric_value_facts,
    "weekly_decline_ratio": _build_stat_metric_value_facts,
    "numeric_ratio": _build_numeric_ratio_facts,
}

_BLOCK_TIME_SERIES_HANDLERS = {
    "daily_mean": _build_time_series_facts,
    "daily_mean_median": _build_time_series_facts,
    "daily_threshold_count": _build_time_series_facts,
    "daily_percentile_rank": _build_time_series_facts,
    "weekend_percentile_rank": _build_time_series_facts,
    "weekday_percentile_rank": _build_time_series_facts,
    "weekly_decline_ratio": _build_time_series_facts,
}


def _build_deterministic_facts(state: AgentState, limit_blocks: int = 3) -> list[dict]:
    out: list[dict] = []
    blocks = getattr(getattr(state, "results", None), "structured_blocks", None)
    if not isinstance(blocks, list) or not blocks:
        return []
    for b in blocks[-limit_blocks:]:
        result = getattr(b, "result", None)
        plan = getattr(b, "plan", None)
        if result is None or not isinstance(plan, dict):
            continue
        block_type = getattr(b, "block_type", None)
        if not block_type:
            continue

        handled = False

        if isinstance(result, dict):
            time_range = _build_time_range(result, plan)
            before = len(out)

            handler = _BLOCK_HANDLERS.get(block_type)
            if handler:
                handled = True
                nparams = handler.__code__.co_varnames[:handler.__code__.co_argcount]
                if "time_range" in nparams:
                    out.extend(handler(b, result, plan, time_range))
                else:
                    out.extend(handler(b, result, plan))

            ts_handler = _BLOCK_TIME_SERIES_HANDLERS.get(block_type)
            if ts_handler:
                handled = True
                out.extend(ts_handler(b, result, plan, time_range))

            # Fill gap: declared in evidence_hints but not produced by handlers
            this_block_facts = out[before:]
            this_block_types = set(f['fact_type'] for f in this_block_facts)
            hints = result.get("evidence_hints") if isinstance(result, dict) else None
            if not isinstance(hints, dict):
                hints = _FALLBACK_HINTS.get(block_type)
            if isinstance(hints, dict):
                declared = set(hints.get("fact_types", []))
                missing = declared - this_block_types
                if missing:
                    col_facts = _build_column_based_facts(b, result, plan, time_range)
                    for cf in col_facts:
                        if cf['fact_type'] in missing:
                            out.append(cf)
                            handled = True

        if not handled:
            out.extend(_build_column_based_facts(b, result, plan, None))

    return out


def _compact_structured_blocks(state: AgentState, limit_blocks: int = 3) -> list[dict]:
    blocks = []
    raw = getattr(getattr(state, "results", None), "structured_blocks", None)
    if not isinstance(raw, list) or not raw:
        return []
    for b in raw[-limit_blocks:]:
        block_id = getattr(b, "block_id", None)
        step = getattr(b, "step", None)
        block_type = getattr(b, "block_type", None)
        status = getattr(b, "status", None)
        question = getattr(b, "question", None)
        statistics = getattr(b, "statistics", None)
        execution_meta = getattr(b, "execution_meta", None)
        error = getattr(b, "error", None)
        result = getattr(b, "result", None)

        compact = {
            "block_id": block_id,
            "step": step,
            "block_type": block_type,
            "status": status,
            "question": question,
            "statistics": statistics if isinstance(statistics, dict) else None,
            "execution_meta": execution_meta if isinstance(execution_meta, dict) else {},
            "error": error,
        }
        if isinstance(result, dict):
            for key in ["type", "window_days", "latest", "mean", "median", "total_change", "direction", "slope"]:
                if key in result:
                    compact.setdefault("result_summary", {})[key] = result.get(key)
        blocks.append(compact)
    return blocks


def _has_uncovered_blocks(state: AgentState, deterministic_facts: list[dict]) -> bool:
    blocks = getattr(getattr(state, "results", None), "structured_blocks", None)
    if not isinstance(blocks, list) or not blocks:
        return False
    covered_block_ids = set()
    for f in deterministic_facts:
        src = f.get("source") if isinstance(f.get("source"), dict) else {}
        bid = src.get("block_id") or f.get("source_block_id")
        if isinstance(bid, str):
            covered_block_ids.add(bid)
    for b in blocks:
        bid = getattr(b, "block_id", None)
        if isinstance(bid, str) and bid not in covered_block_ids:
            bt = getattr(b, "block_type", None)
            if bt and bt not in ("query", "unknown"):
                return True
    return False


def extract_memory_update(client: OpenAI, state: AgentState, last_result: str) -> dict:
    deterministic_facts = _build_deterministic_facts(state)
    compact_structured = _compact_structured_blocks(state)

    if deterministic_facts and not _has_uncovered_blocks(state, deterministic_facts):
        return {"facts": deterministic_facts, "working_memory_update": {}, "missing_info": {}}

    facts_payload = json.dumps(state.memory.facts, ensure_ascii=False)
    working_payload = json.dumps(state.memory.working_memory, ensure_ascii=False)
    structured_payload = json.dumps(compact_structured, ensure_ascii=False)
    deterministic_facts_payload = json.dumps(deterministic_facts, ensure_ascii=False)
    messages = [
        {
            "role": "system",
            "content": (
                "你是记忆抽取器。"
                "请从当前执行结果中提取可复用结论 facts，并更新 working_memory。"
                "只输出 JSON，格式: "
                "{\"facts\": [...], \"working_memory_update\": {...}, \"missing_info\": {...}}。"
                "只抽取已经由 structured_blocks 支持的事实。"
                "不要推测。"
                "不要复述完整执行结果。"
                "facts 必须是数组，每个元素是一个 Fact（字典）。"
                "每条 fact 必须包含 source 对象，且 source.block_id 必须来自 structured_blocks.block_id。"
                "每条 fact 尽量包含 fact_type / metric / dataset / dimension / time_range / values / conclusion / evidence_type。"
                f"支持的 fact_type: {', '.join(sorted(SUPPORTED_FACT_TYPES))}。"

                "fact_type 判别规则："
                "当结果中包含时间字段（日/周/月）+ 指标序列时，输出 time_grouped_metric。"
                "当结果中包含某个业务维度的分组明细（如车型、渠道、城市、省份、门店、大区）时，输出 dimension_breakdown。"
                "当结果中包含占比、比例、份额、share、rate、百分比字段时，输出 share_summary。"
                "当结果中包含排名、TOPN、rank、排序结果时，输出 ranking_result。"
                "当结果中包含同比、环比、差值、变化率、baseline/target 时，输出 comparison_result。"
                "当结果包含趋势方向、上升/下降、峰值、谷值、波动、连续变化时，输出 trend_summary。"
                "当结果是单一指标值时，输出 metric_value。"
                "如果信息不足，写入 missing_info，而不是编造 fact。"
                "不要编造，不要重复已有事实。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"目标:\n{state.question}\n\n"
                f"已有 facts:\n{facts_payload}\n\n"
                f"已有 working_memory:\n{working_payload}\n\n"
                f"structured_blocks（最近几条，供抽取事实）:\n{structured_payload}\n\n"
                f"deterministic_facts（可直接复用/补全）:\n{deterministic_facts_payload}\n\n"
                f"当前结果:\n{str(last_result or '')}\n\n"
                "请输出 JSON。"
            ),
        },
    ]
    try:
        response = client.chat.completions.create(model=DEEPSEEK_CHAT_MODEL, messages=messages)
        content = str(response.choices[0].message.content or "")
        parsed = json.loads(_extract_json_content(content))
        if isinstance(parsed, dict):
            facts = parsed.get("facts")
            cleaned, sanitize_missing = _sanitize_facts(facts, compact_structured)
            all_facts = list(deterministic_facts)
            existing_ids = {f.get("fact_id") for f in all_facts if isinstance(f.get("fact_id"), str)}
            for f in cleaned:
                if f.get("fact_id") not in existing_ids:
                    all_facts.append(f)
                    existing_ids.add(f.get("fact_id"))
            parsed["facts"] = all_facts
            missing_info = parsed.get("missing_info")
            if not isinstance(missing_info, dict):
                missing_info = {}
            for k, v in sanitize_missing.items():
                if k not in missing_info:
                    missing_info[k] = v
            parsed["missing_info"] = missing_info
            if not isinstance(parsed.get("working_memory_update"), dict):
                parsed["working_memory_update"] = {}
            return parsed
    except Exception:
        pass
    return {"facts": deterministic_facts, "working_memory_update": {}, "missing_info": {}}


def apply_memory_update(state: AgentState, update: dict) -> None:
    if not isinstance(update, dict):
        return
    state.merge_facts(update.get("facts") or {})
    state.update_working_memory(update.get("working_memory_update") or {})
    missing = update.get("missing_info")
    if isinstance(missing, dict):
        if not isinstance(state.memory.missing_info, dict):
            state.memory.missing_info = {}
        for k, v in missing.items():
            if k not in state.memory.missing_info:
                state.memory.missing_info[k] = v
