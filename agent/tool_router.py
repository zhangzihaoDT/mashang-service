import json
import datetime
import re
import copy
import pandas as pd

from agent.planner import PlanningAgent
from operators import run_registered_operator
from operators.time_windows import extract_listed_dates
from tools import ComparisonTool, CompositionTool, FastPathTool, MultiTableMetricTool, QueryTool, StatisticsTool


def _infer_block_type(plan: dict) -> str:
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
        out = {"type": "trend_summary"}
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


_EVIDENCE_HINTS: dict[str, dict] = {
    "trend_summary": {"fact_types": ["trend_summary", "time_grouped_metric"], "grain": "day", "has_series": True, "result_type": "statistics"},
    "contribution_summary": {"fact_types": ["contribution_summary", "dimension_breakdown", "share_summary"], "result_type": "statistics"},
    "category_share": {"fact_types": ["share_summary", "dimension_breakdown", "ranking_result"], "result_type": "statistics"},
    "province_topk_share": {"fact_types": ["share_summary", "dimension_breakdown", "ranking_result"], "dimension": "province", "result_type": "operator"},
    "city_tier_distribution": {"fact_types": ["share_summary", "dimension_breakdown"], "dimension": "city_tier", "result_type": "operator"},
    "age_cohort_distribution": {"fact_types": ["share_summary", "dimension_breakdown"], "dimension": "age_cohort", "result_type": "operator"},
    "retained_intention": {"fact_types": ["metric_value"], "result_type": "operator"},
    "retained_intention_conversion": {"fact_types": ["metric_value"], "result_type": "operator"},
    "active_store": {"fact_types": ["time_grouped_metric", "metric_value"], "grain": "day", "has_series": True, "result_type": "operator"},
    "daily_mean": {"fact_types": ["metric_value", "time_grouped_metric"], "grain": "day", "has_series": True, "result_type": "statistics"},
    "daily_mean_median": {"fact_types": ["metric_value", "time_grouped_metric"], "grain": "day", "has_series": True, "result_type": "statistics"},
    "weekly_decline_ratio": {"fact_types": ["metric_value", "time_grouped_metric"], "grain": "week", "has_series": True, "result_type": "statistics"},
    "daily_threshold_count": {"fact_types": ["metric_value", "time_grouped_metric"], "grain": "day", "has_series": True, "result_type": "statistics"},
    "daily_percentile_rank": {"fact_types": ["metric_value", "distribution_summary", "time_grouped_metric"], "grain": "day", "has_series": True, "result_type": "statistics"},
    "weekend_percentile_rank": {"fact_types": ["metric_value", "distribution_summary", "time_grouped_metric"], "grain": "weekend", "has_series": True, "result_type": "statistics"},
    "weekday_percentile_rank": {"fact_types": ["metric_value", "distribution_summary", "time_grouped_metric"], "grain": "day", "has_series": True, "result_type": "statistics"},
    "yoy": {"fact_types": ["comparison_result"], "has_comparison": True, "comparison_type": "yoy", "result_type": "comparison"},
    "wow": {"fact_types": ["comparison_result"], "has_comparison": True, "comparison_type": "wow", "result_type": "comparison"},
    "dod": {"fact_types": ["comparison_result"], "has_comparison": True, "comparison_type": "dod", "result_type": "comparison"},
    "numeric_ratio": {"fact_types": ["metric_value"], "result_type": "fast_path"},
    "data_update": {"fact_types": ["metric_value"], "result_type": "fast_path"},
    "data_sync": {"fact_types": ["metric_value"], "result_type": "fast_path"},
}


def _infer_evidence_hints(block_type: str, result: dict | None, plan: dict | None) -> dict | None:
    hints = _EVIDENCE_HINTS.get(block_type)
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
    operator_result = run_registered_operator(plan=plan, user_query=user_query, query_tool=query_tool)
    if operator_result is not None and tool_result is None:
        execution_meta = {
            "engine": "operator",
            "route": f"operators.{str(operator_result.get('type') or 'unknown')}",
        }
        print(f"[Route] 使用固定算子: {execution_meta['route']}")
        tool_result = operator_result
    if tool_result is None and composition_tool is not None:
        intent = plan.get("analysis_intent", {}) or {}
        if intent.get("type") == "share_breakdown":
            execution_meta = {"engine": "composition", "route": f"composition.{intent.get('denominator_scope', 'share')}"}
            print(f"\n[Thinking] 执行构成分析: {execution_meta['route']}")
            try:
                composition_result = composition_tool.execute(plan)
                if isinstance(composition_result, str):
                    tool_result = composition_result
                elif isinstance(composition_result, pd.DataFrame):
                    tool_result = composition_result
                else:
                    tool_result = str(composition_result)
            except Exception as e:
                tool_result = {"type": "composition_error", "error": "composition_execution_failed", "message": str(e)}
    if tool_result is None and multi_table_tool is not None:
        intent = plan.get("analysis_intent", {}) or {}
        if intent.get("type") == "attribute_penetration":
            execution_meta = {"engine": "multi_table", "route": "multi_table.attribute_penetration"}
            print(f"\n[Thinking] 执行多表属性渗透率分析: {execution_meta['route']}")
            try:
                mt_result = multi_table_tool.execute(plan)
                tool_result = mt_result if isinstance(mt_result, str) else mt_result
            except Exception as e:
                tool_result = {"type": "attribute_penetration_error", "error": "multi_table_execution_failed", "message": str(e)}
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
                    "comparison": {"type": comparison_type},
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
        dimension_field = statistics.get("dimension_field") if isinstance(statistics, dict) else None
        if not dimension_field and isinstance(dimensions, list) and len(dimensions) >= 2:
            dimension_field = dimensions[1]
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
    evidence_hints = _infer_evidence_hints(block_type, tool_result if isinstance(tool_result, dict) else None, plan)
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
        if len(dates) >= 2 and len(dates) <= 10 and has_time_dim and has_other_dim:
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
    return {
        "status": "ok",
        "result_blocks": [execution["block"]],
        "structured_blocks": [execution.get("structured")] if isinstance(execution.get("structured"), dict) else [],
        "execution_meta": execution.get("execution_meta") or {},
        "plan": plan,
    }
