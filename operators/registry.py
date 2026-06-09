from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from operators.active_store import run_active_store_operator
from operators.age_cohort import run_age_cohort_operator
from operators.city_tier import run_city_tier_distribution_operator
from operators.province_topk import run_province_topk_share_operator
from operators.retained_intention import run_retained_intention_operator, run_retained_intention_conversion_operator
from operators.store_avg_lock import run_store_avg_lock_operator
from operators.assign_conversion import run_assign_conversion_operator
from operators.weighted_lead_conversion import run_weighted_lead_conversion_operator
from operators.mature_lock_prediction import run_mature_lock_prediction_operator
from operators.atp_analysis import run_atp_operator
from operators.series_group_logic import apply_series_group_logic

REPO_ROOT = Path(__file__).resolve().parents[1]
_REGISTRY_FILE = REPO_ROOT / "operators" / "registry.json"
_CATALOG_FILE = REPO_ROOT / "operators" / "operator_catalog.json"


def _load_registry() -> dict:
    try:
        return json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"operators": {}, "intent_map": {}}


def _load_catalog() -> list[dict]:
    try:
        return json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def get_operator_catalog_md() -> str:
    catalog = _load_catalog()
    if not catalog:
        return ""
    lines = ["### 可用算子 (Operator Catalog)\n"]
    for i, entry in enumerate(catalog, 1):
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        lines.append(f"{i}. **{title}**: {summary}")
    return "\n".join(lines) + "\n"


def get_registered_intents() -> list[str]:
    registry = _load_registry()
    return list(registry.get("intent_map", {}).keys())


def resolve_intent_from_plan(plan: dict) -> str | None:
    analysis_intent = plan.get("analysis_intent", {}) or {}
    intent = analysis_intent.get("type")
    if intent and intent in _load_registry().get("intent_map", {}):
        return intent
    metric = plan.get("metric", {}) or {}
    plan_metric_text = " ".join(str(v) for v in [metric.get("alias"), metric.get("business_name"), metric.get("field")] if v)
    question = plan.get("question", "")
    user_text = f"{question} {plan_metric_text}"
    registry = _load_registry()
    scored: list[tuple[int, str]] = []
    for intent_name, intent_cfg in registry.get("intent_map", {}).items():
        hints = intent_cfg.get("query_hints", [])
        if all(h in user_text for h in hints):
            metric_names = intent_cfg.get("metric_names", [])
            name_match = any(m in user_text for m in metric_names)
            score = len(hints) * 100 + (200 if name_match else 0)
            scored.append((score, intent_name))
        elif any(h in user_text for h in hints):
            metric_names = intent_cfg.get("metric_names", [])
            if any(m in user_text for m in metric_names):
                score = len(hints) * 10
                scored.append((score, intent_name))
    if scored:
        scored.sort(key=lambda x: -x[0])
        return scored[0][1]
    return None


def _resolve_operator_params(intent: str, plan: dict, user_query: str, query_tool) -> dict | None:
    registry = _load_registry()
    intent_cfg = registry.get("intent_map", {}).get(intent)
    if not intent_cfg:
        return None
    op_name = intent_cfg.get("operator")
    op_reg = registry.get("operators", {}).get(op_name)
    if not op_reg:
        return None
    query_tool._load_datasets()
    dataset_name = op_reg.get("dataset", "order_data")
    df = query_tool.datasets.get(dataset_name)
    if df is None:
        return {"type": op_name, "error": "dataset_not_found", "message": f"缺少 {dataset_name} 数据集"}
    time = (plan or {}).get("time", {}) or {}
    start = time.get("start")
    end = time.get("end")
    if not start or not end:
        return {"type": op_name, "error": "missing_time_window", "message": f"{op_reg.get('name', op_name)} 需要明确 start/end"}
    series = None
    filters = plan.get("filters", [])
    for f in filters:
        if f.get("field") in ("series", "series_group_logic") and f.get("op") == "==":
            series = f.get("value")
            break
    combined_text = " ".join([str(user_query or ""), str(plan.get("question") or "")]).replace(" ", "")

    if intent == "active_store":
        return run_active_store_operator(df=df, start=start, end=end)

    if intent == "retained_intention":
        bdef = _load_business_definition(df, plan)
        return run_retained_intention_operator(df=df, series=series, start=start, end=end, plan=plan, business_definition=bdef)

    if intent == "retained_intention_conversion":
        bdef = _load_business_definition(df, plan)
        return run_retained_intention_conversion_operator(df=df, series=series, lock_start=start, lock_end=end, business_definition=bdef)

    if intent == "age_cohort":
        use_order = any(k in combined_text for k in ["订单用户", "订单年龄", "订单用户年龄", "购车人年龄", "order_age", "buyer_age"])
        age_field = "buyer_age" if use_order else "owner_age"
        identity_field = "buyer_identity_no" if use_order else "owner_identity_no"
        return run_age_cohort_operator(
            df=df, user_query=" ".join([str(user_query or ""), str(plan.get("question") or "")]).strip(),
            start=str(start), end=str(end), series=str(series) if series is not None else None,
            age_field=age_field, identity_field=identity_field if identity_field in df.columns else None,
            time_field="lock_time",
        )

    if intent == "city_tier":
        if any(k in combined_text for k in ["门店城市", "store_city"]):
            city_field = "store_city"
        elif any(k in combined_text for k in ["上牌城市", "license_city"]):
            city_field = "license_city"
        else:
            city_field = "license_city"
        return run_city_tier_distribution_operator(
            df=df, start=str(start), end=str(end),
            series=str(series) if series is not None else None,
            city_field=city_field, time_field="lock_time",
        )

    if intent == "province_topk":
        if any(k in combined_text for k in ["门店城市", "store_city"]):
            city_field = "store_city"
        else:
            city_field = "license_city"
        return run_province_topk_share_operator(
            df=df, user_query=" ".join([str(user_query or ""), str(plan.get("question") or "")]).strip(),
            start=str(start), end=str(end), series=str(series) if series is not None else None,
            city_field=city_field, time_field="lock_time",
        )

    if intent == "store_avg_lock":
        return run_store_avg_lock_operator(df=df, start=str(start), end=str(end))

    if intent == "assign_conversion":
        return run_assign_conversion_operator(df=df, start=str(start), end=str(end))

    if intent == "weighted_lead_conversion":
        return run_weighted_lead_conversion_operator(df=df, start=str(start), end=str(end))

    if intent == "mature_lock_prediction":
        return run_mature_lock_prediction_operator(df=df, start=str(start), end=str(end))

    if intent == "atp":
        return run_atp_operator(df=df, start=str(start), end=str(end))

    return None


def _load_business_definition(df, plan) -> dict:
    bdef_path = REPO_ROOT / "schema" / "business_definition.json"
    bdef = {}
    try:
        bdef = json.loads(bdef_path.read_text(encoding="utf-8")) if bdef_path.exists() else {}
    except Exception:
        bdef = {}
    if "series_group_logic" not in df.columns:
        try:
            df = apply_series_group_logic(df.copy(), bdef)
        except Exception:
            pass
    return bdef


def run_registered_operator(plan: dict, user_query: str, query_tool) -> dict | None:
    intent = resolve_intent_from_plan(plan)
    if intent is None:
        return None
    return _resolve_operator_params(intent, plan, user_query, query_tool)
