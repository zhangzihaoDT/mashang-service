import json
import re
import pandas as pd
from pathlib import Path

from .config_cross_analysis_templates import match as match_template
from operators.series_group_logic import apply_series_group_logic

REPO_ROOT = Path(__file__).resolve().parents[1]
BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
ORDER_DATA = REPO_ROOT / "dataset" / "order_data.parquet"
CONFIG_ATTR = REPO_ROOT / "dataset" / "config_attribute.parquet"


def _load_business_definition() -> dict:
    with open(BUSINESS_DEF, "r", encoding="utf-8") as f:
        return json.load(f)


def _like_to_pattern(like_expr: str) -> str:
    return like_expr.strip().strip("'\"").replace("%", "")


def _infer_dimension(value: str, mapping: dict) -> str:
    for label, rule in mapping.items():
        condition = rule.strip()
        if condition.startswith("product_name LIKE "):
            raw = condition[len("product_name LIKE "):].strip()
            pat = _like_to_pattern(raw)
            if pat and pat in value:
                return label
    return "未知"


def _apply_filters(df: pd.DataFrame, filters: list[dict]) -> pd.DataFrame:
    for f in filters:
        field, op, val = f.get("field"), f.get("op"), f.get("value")
        if not field or not op or val is None:
            continue
        if op == "==":
            df = df[df[field] == val]
        elif op == "!=":
            df = df[df[field] != val]
        elif op == ">=":
            df = df[df[field] >= val]
        elif op == "<":
            df = df[df[field] < val]
        elif op == "in":
            df = df[df[field].isin(val if isinstance(val, list) else [val])]
        elif op == "contains":
            df = df[df[field].astype(str).str.contains(str(val), na=False, regex=False)]
        elif op == "not contains":
            df = df[~df[field].astype(str).str.contains(str(val), na=False, regex=False)]
        elif op == "matches":
            df = df[df[field].astype(str).str.contains(str(val), na=False, regex=True)]
    return df


class MultiTableMetricTool:
    def __init__(self, query_tool=None):
        self.query_tool = query_tool
        self._bd = _load_business_definition()

    def execute(self, plan: dict) -> dict | str:
        intent = plan.get("analysis_intent", {}) or {}
        intent_type = intent.get("type")
        if intent_type == "attribute_penetration":
            return self.attribute_penetration(plan)
        if intent_type == "attribute_distribution":
            return self.attribute_distribution(plan)
        return "MultiTableMetricTool: 不支持的 analysis_intent type"

    def _load_and_filter_orders(self, plan: dict) -> pd.DataFrame:
        filters_raw = (plan.get("filters") or [])
        time = (plan.get("time") or {})

        odf = pd.read_parquet(ORDER_DATA)

        has_group_filter = any(f.get("field") == "series_group_logic" for f in filters_raw)
        if has_group_filter and "series_group_logic" not in odf.columns and "product_name" in odf.columns:
            odf = apply_series_group_logic(odf, self._bd)

        odf = _apply_filters(odf, filters_raw)

        time_field = time.get("field")
        time_start = time.get("start")
        time_end = time.get("end")
        if time_field and time_start:
            odf = odf[odf[time_field].notna() & (odf[time_field] >= time_start)]
        if time_field and time_end:
            odf = odf[odf[time_field] < time_end]

        return odf

    def attribute_penetration(self, plan: dict) -> dict | str:
        intent = (plan.get("analysis_intent") or {})
        metric = (plan.get("metric") or {})
        user_query = plan.get("question") or ""

        dim_mapping = intent.get("dimension_mapping") or self._bd.get("seat_count_logic", {})
        dim_field = intent.get("dimension_field") or "product_name"
        attr_table = intent.get("attribute_table") or "config_attribute"
        attr_field = intent.get("attribute_field") or "Attribute"
        attr_pattern = intent.get("attribute_pattern") or ""
        value_field = intent.get("value_field") or "value"
        positive_value = intent.get("positive_value") or "是"
        value_contains = intent.get("value_contains") or ""
        join_left = intent.get("join_key_left") or "order_number"
        join_right = intent.get("join_key_right") or "Order Number"

        if not attr_pattern:
            tmpl = match_template(user_query)
            if tmpl:
                attr_pattern = tmpl["attribute_pattern"]
                positive_value = tmpl.get("positive_value", positive_value)
        if not attr_pattern:
            attr_pattern = "地暖"

        print(f"\n[MultiTableMetricTool] attribute_penetration: pattern='{attr_pattern}' positive='{positive_value}' value_contains='{value_contains}'")

        odf = self._load_and_filter_orders(plan)
        if odf.empty:
            return {"type": "attribute_penetration", "error": "主表过滤后无数据"}

        odf["_dimension"] = odf[dim_field].astype(str).apply(
            lambda x: _infer_dimension(x, dim_mapping)
        )
        total_all = len(odf)
        order_ids = odf[join_left].unique().tolist()

        cdf = pd.read_parquet(CONFIG_ATTR)
        matched = cdf[
            cdf[join_right].isin(order_ids)
            & cdf[attr_field].astype(str).str.contains(attr_pattern, na=False)
        ]
        if value_contains:
            positive_orders = matched[
                matched[value_field].astype(str).str.contains(value_contains, na=False, regex=False)
            ][join_right].unique()
        else:
            positive_re = re.compile(positive_value)
            positive_orders = matched[
                matched[value_field].astype(str).str.match(positive_re)
            ][join_right].unique()

        odf["_has_attr"] = odf[join_left].isin(positive_orders)

        dim_order = [k for k in dim_mapping.keys()] + ["未知"]
        rows = []
        for dim in dim_order:
            subset = odf[odf["_dimension"] == dim]
            total = len(subset)
            if total == 0:
                continue
            selected = int(subset["_has_attr"].sum())
            rate = round(selected / total * 100, 1)
            rows.append({
                "dimension": dim,
                "selected": selected,
                "total": total,
                "rate_pct": rate,
            })

        total_selected = int(odf["_has_attr"].sum())
        if value_contains:
            metric_alias = f'{attr_pattern}({value_contains})选装率'
        elif positive_value == "是":
            metric_alias = f'{attr_pattern}选装率'
        else:
            metric_alias = f'{attr_pattern}选装率'
        result = {
            "type": "attribute_penetration",
            "metric_alias": metric_alias,
            "attribute_pattern": attr_pattern,
        }
        if value_contains:
            result["value_filter"] = value_contains
        result.update({
            "total_selected": total_selected,
            "total_orders": total_all,
            "overall_rate_pct": round(total_selected / total_all * 100, 1) if total_all else 0.0,
            "rows": rows,
        })
        return result

    def attribute_distribution(self, plan: dict) -> dict | str:
        intent = (plan.get("analysis_intent") or {})
        metric = (plan.get("metric") or {})
        user_query = plan.get("question") or ""

        attr_field = intent.get("attribute_field") or "Attribute"
        attr_pattern = intent.get("attribute_pattern") or ""
        value_field = intent.get("value_field") or "value"
        top_k = int(intent.get("top_k") or 10)
        join_left = intent.get("join_key_left") or "order_number"
        join_right = intent.get("join_key_right") or "Order Number"

        if not attr_pattern:
            tmpl = match_template(user_query)
            if tmpl:
                attr_pattern = tmpl["attribute_pattern"]
        if not attr_pattern:
            return {"type": "attribute_distribution", "error": "缺少 attribute_pattern"}

        print(f"\n[MultiTableMetricTool] attribute_distribution: pattern='{attr_pattern}' top_k={top_k}")

        odf = self._load_and_filter_orders(plan)
        if odf.empty:
            return {"type": "attribute_distribution", "error": "主表过滤后无数据"}

        total_orders = len(odf)
        order_ids = odf[join_left].unique().tolist()

        cdf = pd.read_parquet(CONFIG_ATTR)
        matched = cdf[
            cdf[join_right].isin(order_ids)
            & cdf[attr_field].astype(str).str.contains(attr_pattern, na=False)
        ]
        if matched.empty:
            return {"type": "attribute_distribution", "error": "属性匹配后无数据"}

        dist = matched[value_field].value_counts()
        total_records = int(dist.sum())
        rows = []

        if top_k and len(dist) > top_k:
            top = dist.head(top_k)
            others = int(dist.iloc[top_k:].sum())
            for val, cnt in top.items():
                rows.append({
                    "value": str(val),
                    "count": int(cnt),
                    "share_pct": round(cnt / total_records * 100, 1),
                })
            rows.append({
                "value": "其他",
                "count": others,
                "share_pct": round(others / total_records * 100, 1),
            })
        else:
            for val, cnt in dist.items():
                rows.append({
                    "value": str(val),
                    "count": int(cnt),
                    "share_pct": round(cnt / total_records * 100, 1),
                })

        return {
            "type": "attribute_distribution",
            "metric_alias": metric.get("alias") or "选装比例",
            "attribute_pattern": attr_pattern,
            "total_orders": total_orders,
            "total_records": total_records,
            "rows": rows,
        }
