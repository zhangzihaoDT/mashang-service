import json
import datetime

import pandas as pd

from .query_tool import QueryTool
from .multitable_metric_tool import _infer_dimension


class CompositionTool:
    def __init__(self, query_tool: QueryTool):
        self.query_tool = query_tool

    def execute(self, plan: dict) -> pd.DataFrame | str:
        analysis_intent = plan.get("analysis_intent", {}) or {}
        intent_type = analysis_intent.get("type")
        if intent_type == "share_breakdown":
            method = analysis_intent.get("denominator_scope", "")
            if "within_each_week" in method:
                return self.weekly_share_by_dimension(plan)
            if "within_each_day" in method:
                return self.daily_share_by_dimension(plan)
            if "within_each_month" in method:
                return self.monthly_share_by_dimension(plan)
            return self.share_by_dimension(plan)
        return "CompositionTool: 不支持的 analysis_intent type"

    def share_by_dimension(self, plan: dict) -> pd.DataFrame | str:
        return self._partitioned_share(plan, time_grain=None)

    def weekly_share_by_dimension(self, plan: dict) -> pd.DataFrame | str:
        return self._partitioned_share(plan, time_grain="week")

    def daily_share_by_dimension(self, plan: dict) -> pd.DataFrame | str:
        return self._partitioned_share(plan, time_grain="day")

    def monthly_share_by_dimension(self, plan: dict) -> pd.DataFrame | str:
        return self._partitioned_share(plan, time_grain="month")

    def topn_share(self, plan: dict, top_n: int = 10) -> pd.DataFrame | str:
        df = self.share_by_dimension(plan)
        if isinstance(df, str):
            return df
        share_col = [c for c in df.columns if "占比" in c or "share" in c.lower()]
        if share_col:
            df = df.sort_values(share_col[0], ascending=False).head(top_n)
        return df

    def cumulative_share(self, plan: dict) -> pd.DataFrame | str:
        df = self.share_by_dimension(plan)
        if isinstance(df, str):
            return df
        share_col = [c for c in df.columns if "占比" in c or "share" in c.lower() or "pct" in c.lower()]
        if share_col:
            df = df.sort_values(share_col[0], ascending=False)
            df["累计占比"] = df[share_col[0]].cumsum()
        return df

    def _partitioned_share(self, plan: dict, time_grain: str | None) -> pd.DataFrame | str:
        dataset = plan.get("dataset")
        metric = plan.get("metric", {}) or {}
        time = plan.get("time", {}) or {}
        dimensions = plan.get("dimensions", []) or []
        filters = plan.get("filters", []) or []
        analysis_intent = plan.get("analysis_intent", {}) or {}

        time_field = time.get("field")
        time_start = time.get("start")
        time_end = time.get("end")
        breakdown_dim = analysis_intent.get("breakdown_dimension")
        metric_alias = metric.get("alias") or "value"
        denom_scope = analysis_intent.get("denominator_scope", "")

        if not dataset or not time_field:
            return "CompositionTool: 缺少 dataset 或 time.field"

        effective_dims = list(dict.fromkeys([d for d in [time_field, breakdown_dim] if d]))
        if denom_scope == "overall":
            effective_dims = [d for d in effective_dims if d != time_field]
        if not effective_dims:
            return "CompositionTool: 没有有效的维度列"

        query_plan = {
            "dataset": dataset,
            "metrics": [{"field": metric.get("field"), "agg": metric.get("agg") or "count", "alias": metric_alias}],
            "dimensions": effective_dims,
            "filters": list(filters),
        }
        original_derived = plan.get("derived_dimensions")
        if original_derived:
            query_plan["derived_dimensions"] = list(original_derived)
        if time_field and time_start and time_end:
            query_plan["filters"].append({"field": time_field, "op": ">=", "value": time_start})
            query_plan["filters"].append({"field": time_field, "op": "<", "value": time_end})

        df = self.query_tool.execute_analysis_df(query_plan)
        if isinstance(df, str):
            return df
        if df.empty:
            return "CompositionTool: 查询结果为空"

        if time_field in df.columns and time_grain:
            df[time_field] = pd.to_datetime(df[time_field], errors="coerce")
            if time_grain == "week":
                df[time_field] = df[time_field].dt.isocalendar().week.astype(str).apply(lambda x: f"第{x}周")
            elif time_grain == "month":
                df[time_field] = df[time_field].dt.month.astype(str).apply(lambda x: f"{x}月")
            dims_after = [c for c in effective_dims if c != time_field]
            agg_after = {metric_alias: "sum"}
            groupby_cols = [time_field]
            if breakdown_dim and breakdown_dim in df.columns:
                groupby_cols.append(breakdown_dim)
            df = df.groupby(groupby_cols, observed=True).agg(agg_after).reset_index()

        dim_mapping = analysis_intent.get("dimension_mapping")
        if dim_mapping and breakdown_dim and breakdown_dim in df.columns:
            df[breakdown_dim] = df[breakdown_dim].astype(str).apply(
                lambda x: _infer_dimension(x, dim_mapping)
            )
            agg_cols = {metric_alias: "sum"}
            groupby_cols = [c for c in [time_field, breakdown_dim] if c and c in df.columns]
            if denom_scope == "overall":
                groupby_cols = [c for c in groupby_cols if c != time_field]
            if groupby_cols:
                df = df.groupby(groupby_cols, observed=True).agg(agg_cols).reset_index()

        share_alias = "占比"
        denom_scope = analysis_intent.get("denominator_scope", "")
        if denom_scope == "overall":
            partition_cols = []
        else:
            partition_cols = [c for c in [time_field] if c and c in df.columns]
        if partition_cols and metric_alias in df.columns:
            df[share_alias] = df[metric_alias] / df.groupby(partition_cols, observed=True)[metric_alias].transform("sum")
        elif not partition_cols and metric_alias in df.columns:
            total = df[metric_alias].sum()
            df[share_alias] = df[metric_alias] / total if total else 0.0
        return df
