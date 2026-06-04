import json
import datetime
import re
import copy
import pandas as pd

from agent.planner import PlanningAgent
from operators import run_registered_operator, resolve_intent_from_plan
from operators.time_windows import extract_listed_dates
from schema import MetricRegistry
from tools import ComparisonTool, CompositionTool, FastPathTool, MultiTableMetricTool, QueryTool, StatisticsTool

_metric_registry = MetricRegistry()


_INTENT_EVIDENCE_HINTS: dict[str, dict] = {
    "metric_ratio": {"fact_types": ["metric_value", "dimension_breakdown"], "result_type": "metric_ratio"},
    "metric_ratio_trend": {"fact_types": ["time_grouped_metric", "trend_summary"], "grain": "day", "result_type": "metric_ratio_trend"},
    "dimension_share": {"fact_types": ["dimension_breakdown", "share_summary"], "result_type": "dimension_share"},
    "dimension_share_trend": {"fact_types": ["time_grouped_metric", "share_summary", "trend_summary"], "grain": "day", "result_type": "dimension_share_trend"},
    "active_store": {"fact_types": ["time_grouped_metric", "metric_value"], "grain": "day", "has_series": True, "result_type": "operator"},
    "retained_intention": {"fact_types": ["metric_value"], "result_type": "operator"},
    "retained_intention_conversion": {"fact_types": ["metric_value"], "result_type": "operator"},
    "age_cohort": {"fact_types": ["share_summary", "dimension_breakdown"], "dimension": "age_cohort", "result_type": "operator"},
    "city_tier": {"fact_types": ["share_summary", "dimension_breakdown"], "dimension": "city_tier", "result_type": "operator"},
    "province_topk": {"fact_types": ["share_summary", "dimension_breakdown", "ranking_result"], "dimension": "province", "result_type": "operator"},
    "store_avg_lock": {"fact_types": ["metric_value", "time_grouped_metric"], "grain": "day", "has_series": True, "result_type": "operator"},
    "assign_conversion": {"fact_types": ["metric_value", "dimension_breakdown"], "result_type": "operator"},
    "weighted_lead_conversion": {"fact_types": ["metric_value"], "result_type": "operator"},
    "mature_lock_prediction": {"fact_types": ["metric_value"], "result_type": "operator"},
}


def _infer_block_type(plan: dict) -> str:
    intent = (plan.get("analysis_intent", {}) or {}).get("type")
    if intent:
        return intent
    statistics = plan.get("statistics")
    if isinstance(statistics, dict) and statistics.get("type"):
        return str(statistics.get("type"))
    comparison = plan.get("comparison")
    if isinstance(comparison, dict) and comparison.get("type") and comparison.get("type") != "none":
        return str(comparison.get("type"))
    fast_path = plan.get("fast_path")
    if isinstance(fast_path, dict) and fast_path.get("type"):
        return str(fast_path.get("type"))
    return "query"


def _infer_row_count(result: object) -> int | None:
    if isinstance(result, pd.DataFrame):
        return len(result)
    if not isinstance(result, dict):
        return None
    for key in ["daily_rows", "weekly_rows", "weekend_rows"]:
        rows = result.get(key)
        if isinstance(rows, list):
            return len(rows)
    data = result.get("data")
    if isinstance(data, list):
        return len(data)
    return None


def _extract_statistics_summary(result: object) -> dict | None:
    if not isinstance(result, dict):
        return None
    stype = result.get("type")
    if stype == "trend_summary":
        out: dict = {"type": "trend_summary"}
        for key in ["direction", "latest", "mean", "total_change", "slope", "window_days"]:
            if key in result:
                out[key] = result.get(key)
        return out
    if stype == "contribution_summary":
        out = {"type": "contribution_summary"}
        for key in ["dimension_field", "comparison_method", "baseline_period", "target_period", "first_total", "last_total", "total_delta", "top_k"]:
            if key in result:
                out[key] = result.get(key)
        return out
    return None


def _infer_status_and_error(result: object) -> tuple[str, object]:
    if isinstance(result, dict) and result.get("error"):
        return "error", result
    return "success", None


def _infer_evidence_hints(intent: str, result: dict | None, plan: dict | None) -> dict | None:
    hints = _INTENT_EVIDENCE_HINTS.get(intent)
    if hints is None:
        return None
    hints = dict(hints)
    metric = None
    if isinstance(result, dict):
        metric = result.get("metric_alias") or result.get("metric")
    if not metric and isinstance(plan, dict):
        m = plan.get("metric", {}) or {}
        metric = m.get("alias") or m.get("business_name")
    if metric:
        hints["metric"] = metric
    if isinstance(result, dict) and result.get("dimension_field"):
        hints["dimension"] = result["dimension_field"]
    return hints


def _comparison_df_to_dict(df: "pd.DataFrame", comparison_type: str, metric_alias: str) -> dict:
    cols = [c for c in df.columns if not c.endswith(("_current", "_compare", "_diff", "_diff_pct"))]
    dim_cols = [c for c in cols if c != metric_alias]
    has_dims = bool(dim_cols)
    if has_dims:
        return {
            "evidence_hints": {"fact_types": ["comparison_result", "dimension_breakdown"], "has_comparison": True, "comparison_type": comparison_type, "result_type": "comparison"},
            "rows": df.to_dict(orient="records"),
        }
    row = df.iloc[0].to_dict() if not df.empty else {}
    return {
        "evidence_hints": {"fact_types": ["comparison_result"], "has_comparison": True, "comparison_type": comparison_type, "result_type": "comparison"},
        **row,
    }


def _route_by_intent(
    plan: dict,
    user_query: str,
    query_tool: QueryTool,
    statistics_tool: StatisticsTool,
    composition_tool: CompositionTool | None = None,
    multi_table_tool: MultiTableMetricTool | None = None,
    memory_context: dict | None = None,
) -> tuple[object | None, dict]:
    intent = (plan.get("analysis_intent", {}) or {}).get("type", "")
    if not intent:
        operator_intent = resolve_intent_from_plan(plan)
        if operator_intent:
            plan.setdefault("analysis_intent", {})["type"] = operator_intent
            intent = operator_intent

    if not intent:
        from agent.runtime_decision import infer_intent_from_question
        runtime_intent = infer_intent_from_question(user_query or "")
        if runtime_intent and runtime_intent not in ("unknown", "metric", "trend", "compare", "ranking", "distribution", "diagnosis"):
            plan.setdefault("analysis_intent", {})["type"] = runtime_intent
            intent = runtime_intent
            print(f"[Route] runtime intent fallback: {intent}")
        q = user_query or ""
        rate_keywords = {"锁单率", "试驾率", "转化率"}
        if not intent and any(k in q for k in rate_keywords):
            from operators.registry import _load_registry as _load_op_reg
            op_reg = _load_op_reg().get("intent_map", {})
            for op_name, op_cfg in op_reg.items():
                hints = op_cfg.get("query_hints", [])
                matched_hints = sum(1 for h in hints if h in q)
                if matched_hints >= 1 and op_cfg.get("dataset") == "assign_data":
                    plan.setdefault("analysis_intent", {})["type"] = op_name
                    intent = op_name
                    print(f"[Route] operator fallback from rate query: {intent}")
                    break

    if not intent:
        return None, {"engine": "none", "route": "no_intent"}

    # ── metric_ratio / metric_ratio_trend: 指标比值 ──
    if intent in ("metric_ratio", "metric_ratio_trend"):
        relation = _metric_registry.match_metric_relation(user_query)
        if relation is None:
            return None, {"engine": "none", "route": "metric_ratio.no_relation"}
        rname, rcfg = relation
        num_name = rcfg.get("numerator", "")
        den_name = rcfg.get("denominator", "")
        num_metric = _metric_registry.get(num_name)
        den_metric = _metric_registry.get(den_name)
        if not num_metric or not den_metric:
            return None, {"engine": "none", "route": "metric_ratio.incomplete_definition"}
        time_field = num_metric.get("time_field") or den_metric.get("time_field") or "lock_time"
        dataset = num_metric.get("dataset") or den_metric.get("dataset") or "assign_data"
        time = plan.get("time", {}) or {}
        time_start = time.get("start")
        time_end = time.get("end")
        query_plan = {
            "dataset": dataset,
            "metrics": [
                {"field": num_metric.get("field"), "agg": num_metric.get("agg", "sum"), "alias": rname},
                {"field": den_metric.get("field"), "agg": den_metric.get("agg", "sum"), "alias": f"{den_name}_denominator"},
            ],
            "dimensions": [time_field],
            "filters": [
                *([{"field": time_field, "op": "!=", "value": None}] if time_field else []),
                *([{"field": time_field, "op": ">=", "value": time_start}] if time_start else []),
                *([{"field": time_field, "op": "<", "value": time_end}] if time_end else []),
            ],
            "post_process": [
                {"type": "ratio", "numerator": rname, "denominator": f"{den_name}_denominator", "alias": rname}
            ],
        }
        meta = {"engine": "metric_ratio", "route": f"metric_ratio.{rname}"}
        print(f"\n[Thinking] 执行指标比值: {rname} ({num_name} / {den_name})")
        try:
            raw_df = query_tool.execute_analysis_df(query_plan)
            if isinstance(raw_df, str):
                return raw_df, meta
            if intent == "metric_ratio_trend":
                trend_request = {
                    "type": "trend_summary",
                    "time_field": time_field,
                    "window_days": 10,
                    "metric_alias": rname,
                }
                result = statistics_tool.perform_statistics(trend_request, raw_df)
                return result, {"engine": "metric_ratio_trend", "route": f"metric_ratio_trend.{rname}"}
            return raw_df, meta
        except Exception as e:
            return {"type": "metric_ratio_error", "error": "metric_ratio_execution_failed", "message": str(e)}, meta

    # ── dimension_share / dimension_share_trend: 维度成员占比 ──
    if intent in ("dimension_share", "dimension_share_trend"):
        metric_field = (plan.get("metric") or {}).get("field", "order_number")
        metric_agg = (plan.get("metric") or {}).get("agg", "count")
        metric_alias = (plan.get("metric") or {}).get("alias") or metric_field
        time_field = (plan.get("time") or {}).get("field") or "lock_time"
        time_start = (plan.get("time") or {}).get("start")
        time_end = (plan.get("time") or {}).get("end")
        dataset = plan.get("dataset", "order_data")
        plan_filters = plan.get("filters") or []
        dim_filter = next((f for f in plan_filters if f.get("op") in ("==", "in") and f.get("field") in ("series", "series_group_logic", "product_name")), None)
        base_filters = [{"field": time_field, "op": "!=", "value": None}]
        if time_start:
            base_filters.append({"field": time_field, "op": ">=", "value": time_start})
        if time_end:
            base_filters.append({"field": time_field, "op": "<", "value": time_end})
        dim_filters = list(base_filters)
        if dim_filter:
            dim_filters.append(dim_filter)
        share_meta = {"engine": "dimension_share", "route": f"dimension_share.{metric_field}"}
        dim_label = dim_filter.get("value") if dim_filter else "?"
        print(f"\n[Thinking] 执行维度成员占比: {metric_field}, member={dim_label} / total over {time_field}")
        try:
            total_plan = {
                "dataset": dataset,
                "metrics": [{"field": metric_field, "agg": metric_agg, "alias": f"{metric_alias}_total"}],
                "dimensions": [time_field] if intent == "dimension_share_trend" else [],
                "filters": base_filters,
            }
            total_df = query_tool.execute_analysis_df(total_plan)
            if isinstance(total_df, str):
                return total_df, share_meta
            dim_plan = {
                "dataset": dataset,
                "metrics": [{"field": metric_field, "agg": metric_agg, "alias": metric_alias}],
                "dimensions": [time_field] if intent == "dimension_share_trend" else [],
                "filters": dim_filters,
            }
            dim_df = query_tool.execute_analysis_df(dim_plan)
            if isinstance(dim_df, str):
                return dim_df, share_meta
            share_col = "share"
            if intent == "dimension_share_trend" and time_field in total_df.columns and time_field in dim_df.columns:
                for df in (total_df, dim_df):
                    dt = pd.to_datetime(df[time_field].astype(str), errors="coerce")
                    df["_date"] = dt.dt.normalize() if dt.notna().any() else df[time_field]
                daily_total = total_df.groupby("_date", as_index=False).agg({f"{metric_alias}_total": "sum"}).sort_values("_date")
                daily_dim = dim_df.groupby("_date", as_index=False).agg({metric_alias: "sum"}).sort_values("_date")
                merged = daily_dim.merge(daily_total, on="_date", how="left")
                merged[metric_alias] = merged[metric_alias].fillna(0)
                merged[f"{metric_alias}_total"] = merged[f"{metric_alias}_total"].fillna(0)
                merged[share_col] = merged[metric_alias] / merged[f"{metric_alias}_total"].replace(0, float("nan"))
                trend_request = {
                    "type": "trend_summary",
                    "time_field": "_date",
                    "window_days": 10,
                    "metric_alias": share_col,
                }
                result = statistics_tool.perform_statistics(trend_request, merged)
                return result, {"engine": "dimension_share_trend", "route": f"dimension_share_trend.{metric_field}"}
            else:
                total_val = total_df.iloc[0].get(f"{metric_alias}_total", 1) if not total_df.empty else 1
                if not dim_df.empty:
                    dim_df[share_col] = dim_df[metric_alias] / total_val if total_val else 0
                return dim_df, share_meta
        except Exception as e:
            return {"type": "dimension_share_error", "error": "dimension_share_execution_failed", "message": str(e)}, share_meta

    # ── Operator intents (registered in operators/registry.json) ──
    if intent in _INTENT_EVIDENCE_HINTS:
        meta = {"engine": "operator", "route": f"operators.{intent}"}
        plan_time = (plan.get("time") or {})
        time_sig = f"{plan_time.get('start','')}_{plan_time.get('end','')}"
        filter_sig = "_".join(sorted(f"{f.get('field')}{f.get('op')}{f.get('value')}" for f in (plan.get("filters") or []) if isinstance(f, dict)))
        cache_key = f"{intent}|{plan.get('dataset','')}|{time_sig}|{filter_sig}"
        stm = (memory_context or {}).get("short_term_memory", {})
        cached = stm.get(cache_key) if isinstance(stm, dict) else None
        if cached and isinstance(cached, dict) and cached.get("type") == intent:
            operator_result = cached
        else:
            operator_result = run_registered_operator(plan=plan, user_query=user_query, query_tool=query_tool)
        if operator_result is None:
            return None, meta
        stats_type = (plan.get("statistics") or {}).get("type") if isinstance(plan.get("statistics"), dict) else None
        daily_rows = operator_result.get("daily_rows") if isinstance(operator_result, dict) else None
        if stats_type and daily_rows:
            meta = {"engine": "operator_with_statistics", "route": f"operators.{intent}.{stats_type}"}
            raw_df = pd.DataFrame(daily_rows)
            metric_alias = operator_result.get("metric_alias")
            if not metric_alias or metric_alias not in raw_df.columns:
                rate_cols = [c for c in raw_df.columns if c not in ("date",) and c != "date"]
                q = user_query or ""
                q_nospace = q.replace(" ", "")
                q_core = q_nospace
                for noise in ["近10日", "近7日", "近30日", "近10天", "近7天", "趋势", "走势", "波动"]:
                    q_core = q_core.replace(noise, "")
                def _col_core(c: str) -> str:
                    return c.replace(" ", "").replace("下发", "").replace("下发线索", "").replace("（", "").replace("(", "").replace("）", "").replace(")", "")
                exact_match = [c for c in rate_cols if q_core and (q_core in _col_core(c) or _col_core(c) in q_core)]
                if exact_match:
                    metric_alias = exact_match[0]
                else:
                    q_keywords = [k for k in ("转化率", "试驾率", "锁单率", "占比", "渗透率") if k in q]
                    if "转化率" in q:
                        q_keywords.extend(["试驾率", "锁单率"])
                    fallback = ["转化率", "试驾率", "锁单率", "占比"]
                    preferred = [c for c in rate_cols if any(k in c for k in (q_keywords or fallback))]
                    if len(preferred) >= 2:
                        import re as _re
                        clean_q = _re.sub(r"[；;].*$", "", q.strip())[:30]
                        def _shorten_label(c: str) -> str:
                            for prefix in ["下发线索数（", "下发线索数 (", "下发线索数（", "下发线索"]:
                                c = c.replace(prefix, "")
                            c = c.replace("）", ")").replace("（", "(").replace(")", "").replace("(", "").strip()
                            c = c.replace("门店", "门店 ").replace("直播", "直播 ").replace("平台", "平台 ").strip()
                            c = " ".join(c.split())
                            return c if c else "当日试驾率"
                        options_list = [
                            {"id": c, "label": _shorten_label(c), "definition": c}
                            for c in preferred[:8]
                        ]
                        clarification_result = {
                            "status": "clarification_required",
                            "clarification_type": "ambiguous_metric",
                            "question": f"你说的“{clean_q}”具体指哪个指标？",
                            "options": options_list,
                            "original_query": clean_q,
                            "_operator_result": operator_result,
                        }
                        return clarification_result, meta
                    metric_alias = (preferred or rate_cols)[0] if (preferred or rate_cols) else "value"
            if metric_alias in raw_df.columns and raw_df[metric_alias].dtype.kind == "O":
                cleaned = raw_df[metric_alias].astype(str).str.replace("%", "", regex=False).str.strip()
                raw_df[metric_alias] = pd.to_numeric(cleaned, errors="coerce")
            tool_result = statistics_tool.perform_statistics(
                {
                    "type": stats_type,
                    "time_field": "date",
                    "metric_alias": metric_alias,
                    "date_start": operator_result.get("date_start"),
                    "date_end": operator_result.get("date_end"),
                    "window_days": operator_result.get("window_days", 10),
                },
                raw_df,
            )
            return tool_result, meta
        return operator_result, meta

    # ── share_breakdown / attribute_penetration / attribute_distribution ──
    if intent == "share_breakdown" and composition_tool is not None:
        meta = {"engine": "composition", "route": f"composition.{intent}"}
        try:
            composition_result = composition_tool.execute(plan)
            if isinstance(composition_result, str):
                return composition_result, meta
            if isinstance(composition_result, pd.DataFrame):
                return composition_result, meta
            return str(composition_result), meta
        except Exception as e:
            return {"type": "composition_error", "error": "composition_execution_failed", "message": str(e)}, meta

    if intent in ("attribute_penetration", "attribute_distribution") and multi_table_tool is not None:
        meta = {"engine": "multi_table", "route": f"multi_table.{intent}"}
        try:
            mt_result = multi_table_tool.execute(plan)
            return mt_result if isinstance(mt_result, str) else mt_result, meta
        except Exception as e:
            return {"type": f"{intent}_error", "error": "multi_table_execution_failed", "message": str(e)}, meta

    # ── composition: 按维度拆解查询 ──
    if intent == "composition":
        meta = {"engine": "query", "route": "composition.query"}
        try:
            dims = list(plan.get("dimensions") or [])
            time_field = (plan.get("time") or {}).get("field")
            q = (user_query or "").replace(" ", "")
            has_time_group = any(k in q for k in [
                "按周", "每周", "周度", "逐周", "周别",
                "按月", "每月", "月度", "逐月", "月别",
                "按日", "每日", "日度", "逐日", "日别", "按天",
            ])
            if time_field and not has_time_group and time_field in dims:
                dims.remove(time_field)
            dataset = plan.get("dataset", "order_data")
            metric = plan.get("metric", {})
            plan_filters = list(plan.get("filters") or [])
            time_start = (plan.get("time") or {}).get("start")
            time_end = (plan.get("time") or {}).get("end")
            query_plan = {
                "dataset": dataset,
                "metrics": [{"field": metric.get("field"), "agg": metric.get("agg"), "alias": metric.get("alias") or "value"}],
                "dimensions": dims,
                "filters": [
                    *[f for f in plan_filters if f.get("field") != time_field],
                    *([{"field": time_field, "op": ">=", "value": time_start}] if time_field and time_start else []),
                    *([{"field": time_field, "op": "<", "value": time_end}] if time_field and time_end else []),
                ],
            }
            result = query_tool.execute_analysis_df(query_plan)
            return result, meta
        except Exception as e:
            return {"type": "composition_error", "error": "composition_execution_failed", "message": str(e)}, meta

    return None, {"engine": "none", "route": f"unhandled_intent.{intent}"}


def _execute_single_plan(
    plan: dict,
    user_query: str,
    query_tool: QueryTool,
    comparison_tool: ComparisonTool,
    statistics_tool: StatisticsTool,
    composition_tool: CompositionTool | None = None,
    multi_table_tool: MultiTableMetricTool | None = None,
    memory_context: dict | None = None,
) -> dict:
    dataset = plan.get("dataset")
    metric = plan.get("metric", {}) or {}
    time = plan.get("time", {}) or {}
    dimensions = plan.get("dimensions", []) or []
    filters = plan.get("filters", []) or []
    comparison = plan.get("comparison", {}) or {}
    statistics = plan.get("statistics", {}) or {}
    fast_path = plan.get("fast_path", {}) or {}
    post_process = plan.get("post_process", []) or []

    time_field = time.get("field")
    time_start = time.get("start")
    time_end = time.get("end")

    filters_without_time = []
    for f in filters:
        if not isinstance(f, dict):
            continue
        if f.get("field") != time_field:
            filters_without_time.append(f)
            continue
        if f.get("op") in {">=", "<"} and str(f.get("value")) in {str(time_start), str(time_end)}:
            continue
        filters_without_time.append(f)

    comparison_type = comparison.get("type")
    stats_type = statistics.get("type") if isinstance(statistics, dict) else None

    execution_meta = {"engine": "dsl", "route": "query_tool"}
    tool_result = None
    comparison_df = None

    if isinstance(fast_path, dict) and fast_path.get("type"):
        execution_meta = {"engine": "fast_path", "route": f"fast_path.{str(fast_path.get('type'))}"}
        tool_result = FastPathTool().run(
            config=fast_path,
            user_query=user_query,
            memory_context=memory_context,
        )

    if tool_result is None:
        route_result, meta = _route_by_intent(
            plan, user_query, query_tool, statistics_tool,
            composition_tool=composition_tool, multi_table_tool=multi_table_tool,
            memory_context=memory_context,
        )
        if isinstance(route_result, dict) and route_result.get("status") == "clarification_required":
            return {
                "status": "clarification_required",
                "clarification": {
                    "need": True,
                    "question": route_result.get("question", ""),
                    "options": [o.get("label", o.get("id", "")) for o in (route_result.get("options") or [])],
                    "_options_detail": route_result.get("options", []),
                    "_operator_result": route_result.get("_operator_result"),
                },
                "original_query": route_result.get("original_query", user_query),
                "plan": plan,
            }
        if route_result is not None:
            tool_result = route_result
            execution_meta = meta

    if comparison_type in {"yoy", "wow", "dod"}:
        if comparison_type == "wow" and stats_type == "weekly_decline_ratio":
            execution_meta = {"engine": "comparison", "route": "comparison.weekly_wow_series"}
            print("\n[Thinking] 执行共享周序列算子（Comparison → Weekly WoW Series）...")
            comparison_result = comparison_tool.build_weekly_wow_series(
                {
                    "dataset": dataset,
                    "filters": filters_without_time,
                    "time": {"field": time_field, "start": time_start, "end": time_end},
                    "statistics": statistics,
                }
            )
            if isinstance(comparison_result, str):
                tool_result = comparison_result
            else:
                comparison_df = comparison_result
        else:
            execution_meta = {"engine": "comparison", "route": f"comparison.{comparison_type}"}
            print(f"\n[Thinking] 执行派生指标对比计算: {comparison_type}")
            comparison_result = comparison_tool.perform_comparison_df(
                {
                    "dataset": dataset,
                    "metrics": [
                        {
                            "field": metric.get("field"),
                            "agg": metric.get("agg"),
                            "alias": metric.get("alias") or metric.get("business_name") or "value",
                        }
                    ],
                    "dimensions": dimensions,
                    "filters": filters_without_time,
                    "time": {"field": time_field, "start": time_start, "end": time_end},
                    "comparison": comparison,
                }
            )
            if isinstance(comparison_result, str):
                tool_result = comparison_result
            else:
                comparison_df = comparison_result
                if not stats_type:
                    metric_alias = metric.get("alias") or metric.get("business_name") or "value"
                    tool_result = _comparison_df_to_dict(comparison_df, comparison_type, metric_alias)

    if stats_type == "weekly_decline_ratio" and tool_result is None:
        execution_meta = {"engine": "statistics", "route": "statistics.weekly_decline_ratio"}
        print("\n[Thinking] 执行统计型序列分析...")
        if comparison_df is not None:
            if comparison_type != "wow":
                tool_result = {
                    "type": "weekly_decline_ratio",
                    "error": "unsupported_pipeline_input",
                    "message": "weekly_decline_ratio 仅支持与 wow 周序列算子联动。",
                }
            else:
                stat_request = {
                    "type": "weekly_decline_ratio",
                    "series_input": True,
                    "window_weeks": statistics.get("window_weeks") or 10,
                    "weekdays": statistics.get("weekdays") or [4, 5],
                }
                try:
                    tool_result = statistics_tool.perform_statistics(stat_request, comparison_df)
                except Exception as e:
                    tool_result = {"type": "weekly_decline_ratio", "error": "statistics_execution_failed", "message": str(e)}
        else:
            numerator_metric = statistics.get("numerator_metric", {}) if isinstance(statistics, dict) else {}
            denominator_metric = statistics.get("denominator_metric", {}) if isinstance(statistics, dict) else {}
            window_weeks = statistics.get("window_weeks") or 10
            try:
                window_weeks = int(window_weeks)
            except Exception:
                window_weeks = 10
            query_time_start = time_start
            query_time_end = time_end
            try:
                if time_end:
                    end_day = datetime.date.fromisoformat(str(time_end)[:10])
                    start_day = end_day - datetime.timedelta(days=(max(int(window_weeks), 1) * 7 + 7))
                    query_time_start = start_day.isoformat()
                    query_time_end = end_day.isoformat()
            except Exception:
                pass
            query_plan = {
                "dataset": dataset,
                "metrics": [
                    {
                        "field": numerator_metric.get("field") or metric.get("field"),
                        "agg": numerator_metric.get("agg") or metric.get("agg") or "sum",
                        "alias": numerator_metric.get("alias") or "门店当日锁单数",
                    },
                    {
                        "field": denominator_metric.get("field") or "下发线索数 (门店)",
                        "agg": denominator_metric.get("agg") or "sum",
                        "alias": denominator_metric.get("alias") or "门店线索数",
                    },
                ],
                "dimensions": ([time_field] if time_field else []),
                "filters": [
                    *filters_without_time,
                    {"field": time_field, "op": ">=", "value": query_time_start},
                    {"field": time_field, "op": "<", "value": query_time_end},
                ]
                if time_field and query_time_start and query_time_end
                else filters_without_time,
            }
            raw_df = query_tool.execute_analysis_df(query_plan)
            if isinstance(raw_df, str):
                tool_result = raw_df
            else:
                numerator_alias = numerator_metric.get("alias") or "门店当日锁单数"
                denominator_alias = denominator_metric.get("alias") or "门店线索数"
                weekly_missing_cols = [c for c in [statistics.get("time_field") or time_field, numerator_alias, denominator_alias] if c not in raw_df.columns]
                if weekly_missing_cols:
                    print(f"  ⚠️  weekly_decline_ratio 输入列缺失，降级为基础查询输出: {weekly_missing_cols}")
                    tool_result = {
                        "type": "weekly_decline_ratio",
                        "error": "invalid_statistics_input_schema",
                        "missing_columns": weekly_missing_cols,
                    }
                else:
                    stat_request = {
                        "type": "weekly_decline_ratio",
                        "time_field": statistics.get("time_field") or time_field,
                        "window_weeks": statistics.get("window_weeks") or 10,
                        "weekdays": statistics.get("weekdays") or [4, 5],
                        "numerator_alias": numerator_alias,
                        "denominator_alias": denominator_alias,
                    }
                    try:
                        tool_result = statistics_tool.perform_statistics(stat_request, raw_df)
                    except Exception as e:
                        tool_result = {"type": "weekly_decline_ratio", "error": "statistics_execution_failed", "message": str(e)}
    elif stats_type == "daily_threshold_count" and tool_result is None:
        execution_meta = {"engine": "statistics", "route": "statistics.daily_threshold_count"}
        print("\n[Thinking] 执行统计型阈值计数分析...")
        value_metric = statistics.get("value_metric", {}) if isinstance(statistics, dict) else {}
        metric_alias = value_metric.get("alias") or metric.get("alias") or "value"
        if comparison_df is not None:
            comparison_metric_alias = f"{metric_alias}_diff"
            stat_time_field = (
                statistics.get("time_field")
                or (time_field if time_field in comparison_df.columns else None)
                or (dimensions[0] if isinstance(dimensions, list) and dimensions else None)
            )
            stat_metric_alias = statistics.get("metric_alias") or comparison_metric_alias
            pipeline_missing_cols = [c for c in [stat_time_field, stat_metric_alias] if c and c not in comparison_df.columns]
            if not stat_time_field:
                tool_result = {
                    "type": "daily_threshold_count",
                    "error": "invalid_statistics_input_schema",
                    "missing_columns": ["time_field"],
                }
            elif pipeline_missing_cols:
                print(f"  ⚠️  comparison→statistics 输入列缺失，返回结构化错误: {pipeline_missing_cols}")
                tool_result = {
                    "type": "daily_threshold_count",
                    "error": "invalid_statistics_input_schema",
                    "missing_columns": pipeline_missing_cols,
                }
            else:
                stat_request = {
                    "type": "daily_threshold_count",
                    "time_field": stat_time_field,
                    "window_days": statistics.get("window_days") or 30,
                    "date_start": time_start,
                    "date_end": time_end,
                    "op": statistics.get("op") or ">",
                    "threshold": statistics.get("threshold") if isinstance(statistics, dict) else 0,
                    "metric_alias": stat_metric_alias,
                }
                try:
                    tool_result = statistics_tool.perform_statistics(stat_request, comparison_df)
                except Exception as e:
                    tool_result = {"type": "daily_threshold_count", "error": "statistics_execution_failed", "message": str(e)}
        else:
            window_days = statistics.get("window_days") or 30
            try:
                window_days = int(window_days)
            except Exception:
                window_days = 30
            query_time_start = time_start
            query_time_end = time_end
            query_plan = {
                "dataset": dataset,
                "metrics": [
                    {
                        "field": value_metric.get("field") or metric.get("field"),
                        "agg": value_metric.get("agg") or metric.get("agg") or "count",
                        "alias": metric_alias,
                    }
                ],
                "dimensions": dimensions,
                "filters": [
                    *filters_without_time,
                    {"field": time_field, "op": ">=", "value": query_time_start},
                    {"field": time_field, "op": "<", "value": query_time_end},
                ]
                if time_field and query_time_start and query_time_end
                else filters_without_time,
            }
            raw_df = query_tool.execute_analysis_df(query_plan)
            if isinstance(raw_df, str):
                tool_result = raw_df
            else:
                daily_missing_cols = [c for c in [statistics.get("time_field") or time_field, metric_alias] if c not in raw_df.columns]
                if daily_missing_cols:
                    print(f"  ⚠️  daily_threshold_count 输入列缺失，返回结构化错误: {daily_missing_cols}")
                    tool_result = {
                        "type": "daily_threshold_count",
                        "error": "invalid_statistics_input_schema",
                        "missing_columns": daily_missing_cols,
                    }
                else:
                    stat_request = {
                        "type": "daily_threshold_count",
                        "time_field": statistics.get("time_field") or time_field,
                        "window_days": window_days,
                        "date_start": query_time_start,
                        "date_end": query_time_end,
                        "op": statistics.get("op") or ">",
                        "threshold": statistics.get("threshold") if isinstance(statistics, dict) else 0,
                        "metric_alias": metric_alias,
                    }
                    try:
                        tool_result = statistics_tool.perform_statistics(stat_request, raw_df)
                    except Exception as e:
                        tool_result = {"type": "daily_threshold_count", "error": "statistics_execution_failed", "message": str(e)}
    elif stats_type == "daily_mean" and tool_result is None:
        execution_meta = {"engine": "statistics", "route": "statistics.daily_mean"}
        print("\n[Thinking] 执行统计型日均分析...")
        value_metric = statistics.get("value_metric", {}) if isinstance(statistics, dict) else {}
        metric_alias = value_metric.get("alias") or metric.get("alias") or "value"
        if comparison_df is not None:
            tool_result = {
                "type": "daily_mean",
                "error": "unsupported_pipeline_input",
                "message": "daily_mean 暂不支持 comparison 联动，请使用单窗口查询。",
            }
        else:
            window_days = statistics.get("window_days") or 30
            try:
                window_days = int(window_days)
            except Exception:
                window_days = 30
            query_time_start = time_start
            query_time_end = time_end
            query_plan = {
                "dataset": dataset,
                "metrics": [
                    {
                        "field": value_metric.get("field") or metric.get("field"),
                        "agg": value_metric.get("agg") or metric.get("agg") or "count",
                        "alias": metric_alias,
                    }
                ],
                "dimensions": dimensions,
                "filters": [
                    *filters_without_time,
                    {"field": time_field, "op": ">=", "value": query_time_start},
                    {"field": time_field, "op": "<", "value": query_time_end},
                ]
                if time_field and query_time_start and query_time_end
                else filters_without_time,
            }
            raw_df = query_tool.execute_analysis_df(query_plan)
            if isinstance(raw_df, str):
                tool_result = raw_df
            else:
                daily_missing_cols = [c for c in [statistics.get("time_field") or time_field, metric_alias] if c not in raw_df.columns]
                if daily_missing_cols:
                    print(f"  ⚠️  daily_mean 输入列缺失，返回结构化错误: {daily_missing_cols}")
                    tool_result = {
                        "type": "daily_mean",
                        "error": "invalid_statistics_input_schema",
                        "missing_columns": daily_missing_cols,
                    }
                else:
                    stat_request = {
                        "type": "daily_mean",
                        "time_field": statistics.get("time_field") or time_field,
                        "window_days": window_days,
                        "date_start": query_time_start,
                        "date_end": query_time_end,
                        "metric_alias": metric_alias,
                    }
                    try:
                        tool_result = statistics_tool.perform_statistics(stat_request, raw_df)
                    except Exception as e:
                        tool_result = {"type": "daily_mean", "error": "statistics_execution_failed", "message": str(e)}
    elif stats_type == "daily_mean_median" and tool_result is None:
        execution_meta = {"engine": "statistics", "route": "statistics.daily_mean_median"}
        print("\n[Thinking] 执行统计型日均/中位数分析...")
        value_metric = statistics.get("value_metric", {}) if isinstance(statistics, dict) else {}
        metric_alias = value_metric.get("alias") or metric.get("alias") or "value"
        if comparison_df is not None:
            tool_result = {
                "type": "daily_mean_median",
                "error": "unsupported_pipeline_input",
                "message": "daily_mean_median 暂不支持 comparison 联动，请使用单窗口查询。",
            }
        else:
            window_days = statistics.get("window_days") or 30
            try:
                window_days = int(window_days)
            except Exception:
                window_days = 30
            query_time_start = time_start
            query_time_end = time_end
            query_plan = {
                "dataset": dataset,
                "metrics": [
                    {
                        "field": value_metric.get("field") or metric.get("field"),
                        "agg": value_metric.get("agg") or metric.get("agg") or "count",
                        "alias": metric_alias,
                    }
                ],
                "dimensions": dimensions,
                "filters": [
                    *filters_without_time,
                    {"field": time_field, "op": ">=", "value": query_time_start},
                    {"field": time_field, "op": "<", "value": query_time_end},
                ]
                if time_field and query_time_start and query_time_end
                else filters_without_time,
            }
            raw_df = query_tool.execute_analysis_df(query_plan)
            if isinstance(raw_df, str):
                tool_result = raw_df
            else:
                daily_missing_cols = [c for c in [statistics.get("time_field") or time_field, metric_alias] if c not in raw_df.columns]
                if daily_missing_cols:
                    print(f"  ⚠️  daily_mean_median 输入列缺失，返回结构化错误: {daily_missing_cols}")
                    tool_result = {
                        "type": "daily_mean_median",
                        "error": "invalid_statistics_input_schema",
                        "missing_columns": daily_missing_cols,
                    }
                else:
                    stat_request = {
                        "type": "daily_mean_median",
                        "time_field": statistics.get("time_field") or time_field,
                        "window_days": window_days,
                        "date_start": query_time_start,
                        "date_end": query_time_end,
                        "metric_alias": metric_alias,
                    }
                    try:
                        tool_result = statistics_tool.perform_statistics(stat_request, raw_df)
                    except Exception as e:
                        tool_result = {"type": "daily_mean_median", "error": "statistics_execution_failed", "message": str(e)}
    elif stats_type == "monthly_mean" and tool_result is None:
        execution_meta = {"engine": "statistics", "route": "statistics.monthly_mean"}
        print("\n[Thinking] 执行月均分析...")
        value_metric = statistics.get("value_metric", {}) if isinstance(statistics, dict) else {}
        metric_alias = value_metric.get("alias") or metric.get("alias") or "value"
        if comparison_df is not None:
            tool_result = {
                "type": "monthly_mean",
                "error": "unsupported_pipeline_input",
                "message": "monthly_mean 暂不支持 comparison 联动，请使用单窗口查询。",
            }
        else:
            query_time_start = time_start
            query_time_end = time_end
            query_plan = {
                "dataset": dataset,
                "metrics": [
                    {
                        "field": value_metric.get("field") or metric.get("field"),
                        "agg": value_metric.get("agg") or metric.get("agg") or "count",
                        "alias": metric_alias,
                    }
                ],
                "dimensions": dimensions,
                "filters": [
                    *filters_without_time,
                    {"field": time_field, "op": ">=", "value": query_time_start},
                    {"field": time_field, "op": "<", "value": query_time_end},
                ]
                if time_field and query_time_start and query_time_end
                else filters_without_time,
            }
            raw_df = query_tool.execute_analysis_df(query_plan)
            if isinstance(raw_df, str):
                tool_result = raw_df
            else:
                missing_cols = [c for c in [statistics.get("time_field") or time_field, metric_alias] if c not in raw_df.columns]
                if missing_cols:
                    print(f"  ⚠️  monthly_mean 输入列缺失，返回结构化错误: {missing_cols}")
                    tool_result = {
                        "type": "monthly_mean",
                        "error": "invalid_statistics_input_schema",
                        "missing_columns": missing_cols,
                    }
                else:
                    stat_request = {
                        "type": "monthly_mean",
                        "time_field": statistics.get("time_field") or time_field,
                        "metric_alias": metric_alias,
                    }
                    try:
                        tool_result = statistics_tool.perform_statistics(stat_request, raw_df)
                    except Exception as e:
                        tool_result = {"type": "monthly_mean", "error": "statistics_execution_failed", "message": str(e)}
    elif stats_type == "trend_summary" and tool_result is None:
        execution_meta = {"engine": "statistics", "route": "statistics.trend_summary"}
        print("\n[Thinking] 执行趋势分析汇总...")
        value_metric = statistics.get("value_metric", {}) if isinstance(statistics, dict) else {}
        metric_alias = value_metric.get("alias") or metric.get("alias") or "value"
        if comparison_df is not None:
            tool_result = {
                "type": "trend_summary",
                "error": "unsupported_pipeline_input",
                "message": "trend_summary 暂不支持 comparison 联动，请使用单窗口查询。",
            }
        else:
            window_days = statistics.get("window_days") or 10
            try:
                window_days = int(window_days)
            except Exception:
                window_days = 10
            query_time_start = time_start
            query_time_end = time_end
            query_plan = {
                "dataset": dataset,
                "metrics": [
                    {
                        "field": value_metric.get("field") or metric.get("field"),
                        "agg": value_metric.get("agg") or metric.get("agg") or "count",
                        "alias": metric_alias,
                    }
                ],
                "dimensions": dimensions,
                "filters": [
                    *filters_without_time,
                    {"field": time_field, "op": ">=", "value": query_time_start},
                    {"field": time_field, "op": "<", "value": query_time_end},
                ]
                if time_field and query_time_start and query_time_end
                else filters_without_time,
            }
            raw_df = query_tool.execute_analysis_df(query_plan)
            if isinstance(raw_df, str):
                tool_result = raw_df
            else:
                trend_missing_cols = [c for c in [statistics.get("time_field") or time_field, metric_alias] if c not in raw_df.columns]
                if trend_missing_cols:
                    print(f"  ⚠️  trend_summary 输入列缺失，返回结构化错误: {trend_missing_cols}")
                    tool_result = {
                        "type": "trend_summary",
                        "error": "invalid_statistics_input_schema",
                        "missing_columns": trend_missing_cols,
                    }
                else:
                    stat_request = {
                        "type": "trend_summary",
                        "time_field": statistics.get("time_field") or time_field,
                        "window_days": window_days,
                        "date_start": query_time_start,
                        "date_end": query_time_end,
                        "metric_alias": metric_alias,
                    }
                    try:
                        tool_result = statistics_tool.perform_statistics(stat_request, raw_df)
                    except Exception as e:
                        tool_result = {"type": "trend_summary", "error": "statistics_execution_failed", "message": str(e)}
    elif stats_type == "contribution_summary" and tool_result is None:
        execution_meta = {"engine": "statistics", "route": "statistics.contribution_summary"}
        print("\n[Thinking] 执行贡献拆解汇总...")
        value_metric = statistics.get("value_metric", {}) if isinstance(statistics, dict) else {}
        metric_alias = value_metric.get("alias") or metric.get("alias") or "value"
        dimension_field = None
        if isinstance(dimensions, list) and len(dimensions) >= 2:
            dimension_field = dimensions[1]
        if not dimension_field:
            dimension_field = statistics.get("dimension_field") if isinstance(statistics, dict) else None
        if comparison_df is not None:
            tool_result = {
                "type": "contribution_summary",
                "error": "unsupported_pipeline_input",
                "message": "contribution_summary 暂不支持 comparison 联动，请使用单窗口查询。",
            }
        else:
            window_days = statistics.get("window_days") or 10
            try:
                window_days = int(window_days)
            except Exception:
                window_days = 10
            query_time_start = time_start
            query_time_end = time_end
            query_plan = {
                "dataset": dataset,
                "metrics": [
                    {
                        "field": value_metric.get("field") or metric.get("field"),
                        "agg": value_metric.get("agg") or metric.get("agg") or "count",
                        "alias": metric_alias,
                    }
                ],
                "dimensions": dimensions,
                "filters": [
                    *filters_without_time,
                    {"field": time_field, "op": ">=", "value": query_time_start},
                    {"field": time_field, "op": "<", "value": query_time_end},
                ]
                if time_field and query_time_start and query_time_end
                else filters_without_time,
            }
            raw_df = query_tool.execute_analysis_df(query_plan)
            if isinstance(raw_df, str):
                tool_result = raw_df
            else:
                missing_cols = [c for c in [statistics.get("time_field") or time_field, dimension_field, metric_alias] if c and c not in raw_df.columns]
                if missing_cols:
                    tool_result = {
                        "type": "contribution_summary",
                        "error": "invalid_statistics_input_schema",
                        "missing_columns": missing_cols,
                    }
                else:
                    stat_request = {
                        "type": "contribution_summary",
                        "time_field": statistics.get("time_field") or time_field,
                        "dimension_field": dimension_field,
                        "window_days": window_days,
                        "date_start": query_time_start,
                        "date_end": query_time_end,
                        "metric_alias": metric_alias,
                        "top_k": statistics.get("top_k") if isinstance(statistics, dict) else None,
                    }
                    try:
                        tool_result = statistics_tool.perform_statistics(stat_request, raw_df)
                    except Exception as e:
                        tool_result = {"type": "contribution_summary", "error": "statistics_execution_failed", "message": str(e)}
    elif stats_type == "category_share" and tool_result is None:
        execution_meta = {"engine": "statistics", "route": "statistics.category_share"}
        print("\n[Thinking] 执行分类占比分析...")
        metric_alias = metric.get("alias") or metric.get("business_name") or "value"
        if isinstance(statistics, dict):
            metric_alias = (statistics.get("value_metric") or {}).get("alias") or metric_alias
        if comparison_df is not None:
            tool_result = {
                "type": "category_share",
                "error": "unsupported_pipeline_input",
                "message": "category_share 暂不支持 comparison 联动，请使用单窗口查询。",
            }
        else:
            category_field = None
            if isinstance(statistics, dict):
                category_field = statistics.get("category_field")
            if not category_field and isinstance(dimensions, list) and len(dimensions) == 1:
                category_field = dimensions[0]
            top_k = None
            if isinstance(statistics, dict):
                top_k = statistics.get("top_k")
            query_plan = {
                "dataset": dataset,
                "metrics": [
                    {
                        "field": metric.get("field"),
                        "agg": metric.get("agg") or "count",
                        "alias": metric_alias,
                    }
                ],
                "dimensions": dimensions,
                "filters": [
                    *filters_without_time,
                    {"field": time_field, "op": ">=", "value": time_start},
                    {"field": time_field, "op": "<", "value": time_end},
                ]
                if time_field and time_start and time_end
                else filters_without_time,
            }
            raw_df = query_tool.execute_analysis_df(query_plan)
            if isinstance(raw_df, str):
                tool_result = raw_df
            else:
                missing_cols = [c for c in [category_field, metric_alias] if c and c not in raw_df.columns]
                if missing_cols:
                    tool_result = {
                        "type": "category_share",
                        "error": "invalid_statistics_input_schema",
                        "missing_columns": missing_cols,
                    }
                else:
                    stat_request = {
                        "type": "category_share",
                        "category_field": category_field,
                        "value_field": metric_alias,
                        "top_k": top_k,
                    }
                    try:
                        tool_result = statistics_tool.perform_statistics(stat_request, raw_df)
                    except Exception as e:
                        tool_result = {"type": "category_share", "error": "statistics_execution_failed", "message": str(e)}
    elif stats_type == "daily_percentile_rank" and tool_result is None:
        execution_meta = {"engine": "statistics", "route": "statistics.daily_percentile_rank"}
        print("\n[Thinking] 执行统计型分位分析...")
        value_metric = statistics.get("value_metric", {}) if isinstance(statistics, dict) else {}
        metric_alias = value_metric.get("alias") or metric.get("alias") or "value"
        if comparison_df is not None:
            tool_result = {
                "type": "daily_percentile_rank",
                "error": "unsupported_pipeline_input",
                "message": "daily_percentile_rank 暂不支持 comparison 联动，请使用单窗口查询。",
            }
        else:
            window_days = statistics.get("window_days") or 30
            try:
                window_days = int(window_days)
            except Exception:
                window_days = 30
            query_time_start = time_start
            query_time_end = time_end
            query_plan = {
                "dataset": dataset,
                "metrics": [
                    {
                        "field": value_metric.get("field") or metric.get("field"),
                        "agg": value_metric.get("agg") or metric.get("agg") or "count",
                        "alias": metric_alias,
                    }
                ],
                "dimensions": dimensions,
                "filters": [
                    *filters_without_time,
                    {"field": time_field, "op": ">=", "value": query_time_start},
                    {"field": time_field, "op": "<", "value": query_time_end},
                ]
                if time_field and query_time_start and query_time_end
                else filters_without_time,
            }
            raw_df = query_tool.execute_analysis_df(query_plan)
            if isinstance(raw_df, str):
                tool_result = raw_df
            else:
                daily_missing_cols = [c for c in [statistics.get("time_field") or time_field, metric_alias] if c not in raw_df.columns]
                if daily_missing_cols:
                    print(f"  ⚠️  daily_percentile_rank 输入列缺失，返回结构化错误: {daily_missing_cols}")
                    tool_result = {
                        "type": "daily_percentile_rank",
                        "error": "invalid_statistics_input_schema",
                        "missing_columns": daily_missing_cols,
                    }
                else:
                    stat_request = {
                        "type": "daily_percentile_rank",
                        "time_field": statistics.get("time_field") or time_field,
                        "window_days": window_days,
                        "date_start": query_time_start,
                        "date_end": query_time_end,
                        "reference_date": statistics.get("reference_date"),
                        "reference_value": statistics.get("reference_value"),
                        "metric_alias": metric_alias,
                    }
                    try:
                        tool_result = statistics_tool.perform_statistics(stat_request, raw_df)
                    except Exception as e:
                        tool_result = {"type": "daily_percentile_rank", "error": "statistics_execution_failed", "message": str(e)}

    elif stats_type == "weekend_percentile_rank" and tool_result is None:
        execution_meta = {"engine": "statistics", "route": "statistics.weekend_percentile_rank"}
        print("\n[Thinking] 执行周末分位分析...")
        value_metric = statistics.get("value_metric", {}) if isinstance(statistics, dict) else {}
        metric_alias = value_metric.get("alias") or metric.get("alias") or "value"
        if comparison_df is not None:
            tool_result = {
                "type": "weekend_percentile_rank",
                "error": "unsupported_pipeline_input",
                "message": "weekend_percentile_rank 暂不支持 comparison 联动，请使用单窗口查询。",
            }
        else:
            window_weekends = statistics.get("window_weekends") or 10
            try:
                window_weekends = int(window_weekends)
            except Exception:
                window_weekends = 10
            query_time_start = time_start
            query_time_end = time_end
            query_plan = {
                "dataset": dataset,
                "metrics": [
                    {
                        "field": value_metric.get("field") or metric.get("field"),
                        "agg": value_metric.get("agg") or metric.get("agg") or "count",
                        "alias": metric_alias,
                    }
                ],
                "dimensions": dimensions,
                "filters": [
                    *filters_without_time,
                    {"field": time_field, "op": ">=", "value": query_time_start},
                    {"field": time_field, "op": "<", "value": query_time_end},
                ]
                if time_field and query_time_start and query_time_end
                else filters_without_time,
            }
            raw_df = query_tool.execute_analysis_df(query_plan)
            if isinstance(raw_df, str):
                tool_result = raw_df
            else:
                weekend_missing_cols = [c for c in [statistics.get("time_field") or time_field, metric_alias] if c not in raw_df.columns]
                if weekend_missing_cols:
                    print(f"  ⚠️  weekend_percentile_rank 输入列缺失，返回结构化错误: {weekend_missing_cols}")
                    tool_result = {
                        "type": "weekend_percentile_rank",
                        "error": "invalid_statistics_input_schema",
                        "missing_columns": weekend_missing_cols,
                    }
                else:
                    stat_request = {
                        "type": "weekend_percentile_rank",
                        "time_field": statistics.get("time_field") or time_field,
                        "window_weekends": window_weekends,
                        "reference_date": statistics.get("reference_date"),
                        "metric_alias": metric_alias,
                    }
                    try:
                        tool_result = statistics_tool.perform_statistics(stat_request, raw_df)
                    except Exception as e:
                        tool_result = {"type": "weekend_percentile_rank", "error": "statistics_execution_failed", "message": str(e)}

    elif stats_type == "weekday_percentile_rank" and tool_result is None:
        execution_meta = {"engine": "statistics", "route": "statistics.weekday_percentile_rank"}
        print("\n[Thinking] 执行指定周内日分位分析...")
        value_metric = statistics.get("value_metric", {}) if isinstance(statistics, dict) else {}
        metric_alias = value_metric.get("alias") or metric.get("alias") or "value"
        if comparison_df is not None:
            tool_result = {
                "type": "weekday_percentile_rank",
                "error": "unsupported_pipeline_input",
                "message": "weekday_percentile_rank 暂不支持 comparison 联动，请使用单窗口查询。",
            }
        else:
            window_weeks = statistics.get("window_weeks") or 10
            try:
                window_weeks = int(window_weeks)
            except Exception:
                window_weeks = 10
            weekdays = statistics.get("weekdays") if isinstance(statistics, dict) else None
            query_time_start = time_start
            query_time_end = time_end
            query_plan = {
                "dataset": dataset,
                "metrics": [
                    {
                        "field": value_metric.get("field") or metric.get("field"),
                        "agg": value_metric.get("agg") or metric.get("agg") or "count",
                        "alias": metric_alias,
                    }
                ],
                "dimensions": dimensions,
                "filters": [
                    *filters_without_time,
                    {"field": time_field, "op": ">=", "value": query_time_start},
                    {"field": time_field, "op": "<", "value": query_time_end},
                ]
                if time_field and query_time_start and query_time_end
                else filters_without_time,
            }
            raw_df = query_tool.execute_analysis_df(query_plan)
            if isinstance(raw_df, str):
                tool_result = raw_df
            else:
                missing_cols = [c for c in [statistics.get("time_field") or time_field, metric_alias] if c not in raw_df.columns]
                if missing_cols:
                    print(f"  ⚠️  weekday_percentile_rank 输入列缺失，返回结构化错误: {missing_cols}")
                    tool_result = {
                        "type": "weekday_percentile_rank",
                        "error": "invalid_statistics_input_schema",
                        "missing_columns": missing_cols,
                    }
                else:
                    stat_request = {
                        "type": "weekday_percentile_rank",
                        "time_field": statistics.get("time_field") or time_field,
                        "window_weeks": window_weeks,
                        "weekdays": weekdays,
                        "date_start": query_time_start,
                        "date_end": query_time_end,
                        "reference_date": statistics.get("reference_date"),
                        "metric_alias": metric_alias,
                    }
                    try:
                        tool_result = statistics_tool.perform_statistics(stat_request, raw_df)
                    except Exception as e:
                        tool_result = {"type": "weekday_percentile_rank", "error": "statistics_execution_failed", "message": str(e)}

    if tool_result is None:
        execution_meta = {"engine": "dsl", "route": "query_tool"}
        print("\n[Thinking] 执行单次查询...")
        query_plan = {
            "dataset": dataset,
            "metrics": [
                {
                    "field": metric.get("field"),
                    "agg": metric.get("agg"),
                    "alias": metric.get("alias") or metric.get("business_name") or "value",
                }
            ],
            "dimensions": dimensions,
            "filters": [
                *filters_without_time,
                {"field": time_field, "op": ">=", "value": time_start},
                {"field": time_field, "op": "<", "value": time_end},
            ]
            if time_field and time_start and time_end
            else filters_without_time,
        }
        if post_process:
            query_plan["post_process"] = list(post_process)
        tool_result = query_tool.execute_analysis(query_plan)
        tool_df = query_tool.execute_analysis_df(query_plan)
        if not isinstance(tool_df, str):
            tool_result = tool_df

    if isinstance(tool_result, str) and ("找不到数据集" in tool_result or "聚合计算失败" in tool_result):
        print("  ⚠️  执行异常，尝试回退到关键词匹配...")
        fallback_question = plan.get("question") or user_query
        fallback_result = query_tool.answer_question(fallback_question)
        tool_result = f"执行遇到问题: {tool_result}\n\n尝试关键词匹配结果:\n{fallback_result}"

    print(f"[Route] 规划路由完成: {execution_meta['engine']}::{execution_meta['route']}")
    sub_query = plan.get("question") or user_query
    tool_result_text = json.dumps(tool_result, ensure_ascii=False, indent=2) if isinstance(tool_result, dict) else str(tool_result)
    block = f"查询: {sub_query}\nDSL: {json.dumps(plan, ensure_ascii=False)}\n执行结果:\n{tool_result_text}"
    status, error = _infer_status_and_error(tool_result)
    row_count = _infer_row_count(tool_result)
    enriched_meta = dict(execution_meta or {})
    if row_count is not None:
        enriched_meta["row_count"] = int(row_count)
    block_type = _infer_block_type(plan)
    operator_intent = (plan.get("analysis_intent", {}) or {}).get("type") or resolve_intent_from_plan(plan)
    evidence_hints = _infer_evidence_hints(operator_intent, tool_result if isinstance(tool_result, dict) else None, plan)
    if evidence_hints:
        enriched_meta["evidence_hints"] = evidence_hints
        if isinstance(tool_result, dict):
            tool_result = dict(tool_result)
            tool_result["evidence_hints"] = evidence_hints
    structured = {
        "question": sub_query,
        "plan": plan,
        "dsl": plan,
        "result": tool_result,
        "statistics": _extract_statistics_summary(tool_result),
        "execution_meta": enriched_meta,
        "block_type": block_type,
        "status": status,
        "error": error,
        "block": block,
    }
    return {"block": block, "execution_meta": execution_meta, "structured": structured}


def run_dsl_step(
    action_query: str,
    planning_agent: PlanningAgent,
    query_tool: QueryTool,
    comparison_tool: ComparisonTool,
    statistics_tool: StatisticsTool,
    composition_tool: CompositionTool | None = None,
    multi_table_tool: MultiTableMetricTool | None = None,
    memory_context: dict | None = None,
) -> dict:
    print("\n[Thinking] PlanningAgent 正在构建执行规划并路由...")
    plan = planning_agent.create_plan(action_query, memory_context=memory_context)
    if not isinstance(plan, dict) or not plan:
        planning_error = ""
        try:
            planning_error = str(getattr(planning_agent, "last_planning_error", "") or "").strip()
        except Exception:
            planning_error = ""
        suffix = f" 规划器错误信息: {planning_error}" if planning_error else ""
        return {"status": "error", "message": f"未能生成有效的规划 DSL。{suffix}"}

    working_memory = None
    if isinstance(memory_context, dict) and isinstance(memory_context.get("working_memory"), dict):
        working_memory = memory_context.get("working_memory")

    try:
        plan_fingerprint_payload = {
            "dataset": plan.get("dataset"),
            "metric": plan.get("metric"),
            "time": plan.get("time"),
            "dimensions": plan.get("dimensions"),
            "filters": plan.get("filters"),
            "comparison": plan.get("comparison"),
            "statistics": (plan.get("statistics") or {}).get("type") if isinstance(plan.get("statistics"), dict) else None,
        }
        plan_fingerprint = json.dumps(plan_fingerprint_payload, ensure_ascii=False, sort_keys=True)
    except Exception:
        plan_fingerprint = None

    if isinstance(working_memory, dict) and plan_fingerprint:
        last_fp = working_memory.get("last_plan_fingerprint")
        last_q = working_memory.get("last_action_query")
        if last_fp == plan_fingerprint:
            repeated = int(working_memory.get("repeated_plan_count") or 0) + 1
            working_memory["repeated_plan_count"] = repeated
            if last_q and last_q != action_query:
                fallback = planning_agent._rule_based_plan(action_query)
                if isinstance(fallback, dict) and fallback:
                    plan = planning_agent._fill_defaults(planning_agent._normalize_plan(fallback), action_query)
                    try:
                        plan_fingerprint_payload = {
                            "dataset": plan.get("dataset"),
                            "metric": plan.get("metric"),
                            "time": plan.get("time"),
                            "dimensions": plan.get("dimensions"),
                            "filters": plan.get("filters"),
                            "comparison": plan.get("comparison"),
                            "statistics": (plan.get("statistics") or {}).get("type") if isinstance(plan.get("statistics"), dict) else None,
                        }
                        plan_fingerprint = json.dumps(plan_fingerprint_payload, ensure_ascii=False, sort_keys=True)
                    except Exception:
                        plan_fingerprint = None
        else:
            working_memory["repeated_plan_count"] = 0
        working_memory["last_plan_fingerprint"] = plan_fingerprint
        working_memory["last_action_query"] = action_query

    if isinstance(plan.get("comparison"), dict) and plan["comparison"].get("type") in ("yoy", "wow") and not plan["comparison"].get("target_year"):
        time_info = plan.get("time")
        if isinstance(time_info, dict):
            start_str = time_info.get("start")
            if isinstance(start_str, str):
                try:
                    current_year = int(start_str[:4])
                except (ValueError, IndexError):
                    current_year = None
                if current_year:
                    from operators.time_windows import extract_compare_year
                    target = extract_compare_year(action_query, current_year)
                    if target is not None:
                        plan["comparison"]["target_year"] = target

    goal_time_window = None
    goal_time_window_confidence = None
    if isinstance(memory_context, dict):
        goal_time_window = memory_context.get("goal_time_window")
        goal_time_window_confidence = memory_context.get("goal_time_window_confidence")

    if (
        goal_time_window
        and isinstance(goal_time_window, (tuple, list))
        and len(goal_time_window) == 2
        and goal_time_window_confidence in {"high", "medium"}
        and isinstance(plan.get("time"), dict)
    ):
        try:
            goal_start = datetime.date.fromisoformat(str(goal_time_window[0])[:10])
            goal_end = datetime.date.fromisoformat(str(goal_time_window[1])[:10])
            time = plan.get("time") or {}
            time_start = datetime.date.fromisoformat(str(time.get("start"))[:10])
            time_end = datetime.date.fromisoformat(str(time.get("end"))[:10])

            clamped_start = max(time_start, goal_start)
            clamped_end = min(time_end, goal_end)
            if clamped_end <= clamped_start:
                return {
                    "status": "error",
                    "message": f"规划的时间窗口超出目标范围，且裁剪后无有效区间: [{clamped_start.isoformat()}, {clamped_end.isoformat()})",
                }

            if clamped_start != time_start or clamped_end != time_end:
                time["start"] = clamped_start.isoformat()
                time["end"] = clamped_end.isoformat()
                plan["time"] = time

                time_field = time.get("field")
                filters = plan.get("filters")
                if isinstance(time_field, str) and isinstance(filters, list) and filters:
                    rewritten_filters: list[dict] = []
                    for f in filters:
                        if not isinstance(f, dict):
                            continue
                        if f.get("field") != time_field:
                            rewritten_filters.append(f)
                            continue
                        op = f.get("op")
                        value = f.get("value")
                        if op in {">=", "<"} and isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value.strip()):
                            continue
                        rewritten_filters.append(f)
                    plan["filters"] = rewritten_filters
        except Exception:
            pass

    if isinstance(plan.get("clarification"), dict):
        clarification = plan["clarification"]
        if clarification.get("need"):
            return {
                "status": "clarification",
                "clarification": clarification,
                "original_question": plan.get("question") or action_query,
                "plan": plan,
            }

    if (
        isinstance(plan.get("comparison"), dict)
        and plan["comparison"].get("type") == "none"
        and not (isinstance(plan.get("statistics"), dict) and plan["statistics"].get("type"))
        and not (isinstance(plan.get("fast_path"), dict) and plan["fast_path"].get("type"))
    ):
        dates = extract_listed_dates(action_query, datetime.date.today())
        time = plan.get("time")
        if isinstance(time, dict) and isinstance(time.get("field"), str) and time.get("field"):
            time_field = time.get("field")
        else:
            time_field = None
        dims = plan.get("dimensions")
        has_time_dim = isinstance(dims, list) and isinstance(time_field, str) and time_field in dims
        has_other_dim = isinstance(dims, list) and any(isinstance(d, str) and d and d != time_field for d in dims)
        dates_are_range = bool(re.search(r"[日月号年\d][~到至\-\u2014\u2013\uFF0D][\d年月]", (action_query or "").replace(" ", "")))
        if len(dates) >= 2 and len(dates) <= 10 and has_time_dim and has_other_dim and not dates_are_range:
            result_blocks: list[str] = []
            structured_blocks: list[dict] = []
            for day in dates:
                try:
                    day_date = datetime.date.fromisoformat(day)
                except Exception:
                    continue
                sub_plan = copy.deepcopy(plan)
                if isinstance(sub_plan.get("time"), dict):
                    sub_plan["time"]["start"] = day_date.isoformat()
                    sub_plan["time"]["end"] = (day_date + datetime.timedelta(days=1)).isoformat()
                if isinstance(sub_plan.get("dimensions"), list) and time_field:
                    sub_plan["dimensions"] = [d for d in sub_plan["dimensions"] if d != time_field]
                sub_plan["question"] = f"{action_query}（{day_date.isoformat()}）"
                execution = _execute_single_plan(
                    plan=sub_plan,
                    user_query=sub_plan["question"],
                    query_tool=query_tool,
                    comparison_tool=comparison_tool,
                    statistics_tool=statistics_tool,
                    composition_tool=composition_tool,
                    multi_table_tool=multi_table_tool,
                    memory_context=memory_context,
                )
                result_blocks.append(execution["block"])
                structured = execution.get("structured")
                if isinstance(structured, dict) and structured:
                    structured_blocks.append(structured)
            if result_blocks:
                return {
                    "status": "ok",
                    "result_blocks": result_blocks,
                    "structured_blocks": structured_blocks,
                    "execution_meta": {"engine": "dsl", "route": "query_tool.multi_date_split", "subqueries": len(result_blocks)},
                    "plan": plan,
                }

    execution = _execute_single_plan(
        plan=plan,
        user_query=action_query,
        query_tool=query_tool,
        comparison_tool=comparison_tool,
        statistics_tool=statistics_tool,
        composition_tool=composition_tool,
        multi_table_tool=multi_table_tool,
        memory_context=memory_context,
    )
    if isinstance(execution, dict) and execution.get("status") == "clarification_required":
        clar = execution.get("clarification", {})
        plan_time = (plan.get("time") or {})
        time_sig = f"{plan_time.get('start','')}_{plan_time.get('end','')}"
        filter_sig = "_".join(sorted(f"{f.get('field')}{f.get('op')}{f.get('value')}" for f in (plan.get("filters") or []) if isinstance(f, dict)))
        op_intent = resolve_intent_from_plan(plan) or (plan.get("analysis_intent") or {}).get("type", "")
        cache_key = f"{op_intent}|{plan.get('dataset','')}|{time_sig}|{filter_sig}" if op_intent else ""
        return {
            "status": "clarification",
            "clarification": clar,
            "original_question": execution.get("original_query", action_query),
            "plan": plan,
            "_operator_result": clar.get("_operator_result"),
            "_cache_key": cache_key,
        }
    return {
        "status": "ok",
        "result_blocks": [execution["block"]],
        "structured_blocks": [execution.get("structured")] if isinstance(execution.get("structured"), dict) else [],
        "execution_meta": execution.get("execution_meta") or {},
        "plan": plan,
    }
