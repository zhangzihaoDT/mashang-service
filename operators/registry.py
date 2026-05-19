from operators.active_store import run_active_store_operator
from operators.age_cohort import run_age_cohort_operator
from operators.city_tier import run_city_tier_distribution_operator
from operators.province_topk import run_province_topk_share_operator
from operators.retained_intention import run_retained_intention_operator, run_retained_intention_conversion_operator
from operators.store_avg_lock import run_store_avg_lock_operator
from operators.assign_conversion import run_assign_conversion_operator
from operators.weighted_lead_conversion import run_weighted_lead_conversion_operator
from pathlib import Path
import json
from operators.series_group_logic import apply_series_group_logic

REPO_ROOT = Path(__file__).resolve().parents[1]
OPERATOR_CATALOG_FILE = REPO_ROOT / "operators" / "index_summary.json"


def get_operator_catalog_md() -> str:
    try:
        catalog = json.loads(OPERATOR_CATALOG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return ""
    lines = ["### 可用算子 (Operator Catalog)\n"]
    for i, entry in enumerate(catalog, 1):
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        lines.append(f"{i}. **{title}**: {summary}")
    return "\n".join(lines) + "\n"


def _is_active_store_plan(plan: dict, user_query: str) -> bool:
    metric = (plan or {}).get("metric", {}) or {}
    text = " ".join(
        [
            str(user_query or ""),
            str(metric.get("alias") or ""),
            str(metric.get("business_name") or ""),
            str(metric.get("field") or ""),
        ]
    )
    return "在营门店" in text


def _is_retained_intention_plan(plan: dict, user_query: str) -> bool:
    metric = (plan or {}).get("metric", {}) or {}
    text = " ".join(
        [
            str(user_query or ""),
            str(metric.get("alias") or ""),
            str(metric.get("business_name") or ""),
            str(metric.get("field") or ""),
        ]
    )
    return "留存小订" in text


def _is_retained_intention_conversion_plan(plan: dict, user_query: str) -> bool:
    metric = (plan or {}).get("metric", {}) or {}
    text = " ".join(
        [
            str(user_query or ""),
            str(metric.get("alias") or ""),
            str(metric.get("business_name") or ""),
            str(metric.get("field") or ""),
        ]
    )
    return ("留存小订" in text) and ("转化" in text)


def _is_age_cohort_plan(plan: dict, user_query: str) -> bool:
    metric = (plan or {}).get("metric", {}) or {}
    text = " ".join(
        [
            str(user_query or ""),
            str(plan.get("question") or ""),
            str(metric.get("alias") or ""),
            str(metric.get("business_name") or ""),
            str(metric.get("field") or ""),
        ]
    )
    if "年龄" not in text:
        return False
    if not any(k in text for k in ["占比", "比例", "分布", "00后", "95后", "90后", "85后", "80后", "75后", "70后", "65后", "60前"]):
        return False
    return any(k in text for k in ["锁单", "订单", "交付", "开票", "小订", "意向金"])

def _is_city_tier_plan(plan: dict, user_query: str) -> bool:
    metric = (plan or {}).get("metric", {}) or {}
    text = " ".join(
        [
            str(user_query or ""),
            str(plan.get("question") or ""),
            str(metric.get("alias") or ""),
            str(metric.get("business_name") or ""),
            str(metric.get("field") or ""),
        ]
    )
    if not any(k in text for k in ["城市", "city"]):
        return False
    if not any(k in text for k in ["占比", "比例", "分布"]):
        return False
    if not any(k in text for k in ["线级", "城市线级", "城市等级", "一线", "新一线", "二线", "三线", "三线及以下"]):
        return False
    return any(k in text for k in ["锁单", "订单", "交付", "开票", "小订", "意向金"])

def _is_assign_conversion_plan(plan: dict, user_query: str) -> bool:
    metric = (plan or {}).get("metric", {}) or {}
    text = " ".join(
        [
            str(user_query or ""),
            str(metric.get("alias") or ""),
            str(metric.get("business_name") or ""),
            str(metric.get("field") or ""),
        ]
    )
    return ("下发线索" in text) and ("转化率" in text or "锁单率" in text)


def _is_weighted_lead_conversion_plan(plan: dict, user_query: str) -> bool:
    metric = (plan or {}).get("metric", {}) or {}
    text = " ".join(
        [
            str(user_query or ""),
            str(metric.get("alias") or ""),
            str(metric.get("business_name") or ""),
            str(metric.get("field") or ""),
        ]
    )
    return "加权锁单率" in text


def _is_province_topk_share_plan(plan: dict, user_query: str) -> bool:
    metric = (plan or {}).get("metric", {}) or {}
    text = " ".join(
        [
            str(user_query or ""),
            str(plan.get("question") or ""),
            str(metric.get("alias") or ""),
            str(metric.get("business_name") or ""),
            str(metric.get("field") or ""),
        ]
    )
    if not any(k in text for k in ["省", "省份", "province"]):
        return False
    if not any(k in text for k in ["占比", "比例", "分布"]):
        return False
    if not any(k in text.upper() for k in ["TOP", "前"]):
        return False
    return any(k in text for k in ["锁单", "订单", "交付", "开票", "小订", "意向金", "销量"])


def _is_store_avg_lock_plan(plan: dict, user_query: str) -> bool:
    metric = (plan or {}).get("metric", {}) or {}
    text = " ".join(
        [
            str(user_query or ""),
            str(metric.get("alias") or ""),
            str(metric.get("business_name") or ""),
            str(metric.get("field") or ""),
        ]
    )
    return "店均锁单" in text


def run_registered_operator(plan: dict, user_query: str, query_tool) -> dict | None:
    if _is_store_avg_lock_plan(plan, user_query):
        query_tool._load_datasets()
        df = query_tool.datasets.get("order_data")
        if df is None:
            return {"type": "store_avg_lock", "error": "dataset_not_found", "message": "缺少 order_data 数据集"}
        time = (plan or {}).get("time", {}) or {}
        start = time.get("start")
        end = time.get("end")
        if not start or not end:
            return {"type": "store_avg_lock", "error": "missing_time_window", "message": "店均锁单数需要明确 start/end"}
        return run_store_avg_lock_operator(df=df, start=str(start), end=str(end))

    if _is_weighted_lead_conversion_plan(plan, user_query):
        query_tool._load_datasets()
        df = query_tool.datasets.get("assign_data")
        if df is None:
            return {"type": "weighted_lead_conversion", "error": "dataset_not_found", "message": "缺少 assign_data 数据集"}
        time = (plan or {}).get("time", {}) or {}
        start = time.get("start")
        end = time.get("end")
        if not start or not end:
            return {"type": "weighted_lead_conversion", "error": "missing_time_window", "message": "加权锁单率需要明确 start/end"}
        return run_weighted_lead_conversion_operator(df=df, start=str(start), end=str(end))

    if _is_assign_conversion_plan(plan, user_query):
        query_tool._load_datasets()
        df = query_tool.datasets.get("assign_data")
        if df is None:
            return {"type": "assign_conversion", "error": "dataset_not_found", "message": "缺少 assign_data 数据集"}
        time = (plan or {}).get("time", {}) or {}
        start = time.get("start")
        end = time.get("end")
        if not start or not end:
            return {"type": "assign_conversion", "error": "missing_time_window", "message": "下发线索转化率需要明确 start/end"}
        return run_assign_conversion_operator(df=df, start=str(start), end=str(end))

    if _is_province_topk_share_plan(plan, user_query):
        query_tool._load_datasets()
        df = query_tool.datasets.get("order_data")
        if df is None:
            return {"type": "province_topk_share", "error": "dataset_not_found", "message": "缺少 order_data 数据集"}
        time = (plan or {}).get("time", {}) or {}
        start = time.get("start")
        end = time.get("end")
        if not start or not end:
            return {"type": "province_topk_share", "error": "missing_time_window", "message": "省份 TOP 占比需要明确 start/end"}
        series = None
        filters = plan.get("filters", [])
        for f in filters:
            if f.get("field") in ("series", "series_group_logic") and f.get("op") == "==":
                series = f.get("value")
                break
        combined = " ".join([str(user_query or ""), str(plan.get("question") or "")]).replace(" ", "")
        if any(k in combined for k in ["门店城市", "store_city"]):
            city_field = "store_city"
        else:
            city_field = "license_city"
        return run_province_topk_share_operator(
            df=df,
            user_query=" ".join([str(user_query or ""), str(plan.get("question") or "")]).strip(),
            start=str(start),
            end=str(end),
            series=str(series) if series is not None else None,
            city_field=city_field,
            time_field="lock_time",
        )

    if _is_city_tier_plan(plan, user_query):
        query_tool._load_datasets()
        df = query_tool.datasets.get("order_data")
        if df is None:
            return {"type": "city_tier_distribution", "error": "dataset_not_found", "message": "缺少 order_data 数据集"}
        time = (plan or {}).get("time", {}) or {}
        start = time.get("start")
        end = time.get("end")
        if not start or not end:
            return {"type": "city_tier_distribution", "error": "missing_time_window", "message": "城市分布占比需要明确 start/end"}
        series = None
        filters = plan.get("filters", [])
        for f in filters:
            if f.get("field") in ("series", "series_group_logic") and f.get("op") == "==":
                series = f.get("value")
                break
        combined = " ".join([str(user_query or ""), str(plan.get("question") or "")]).replace(" ", "")
        if any(k in combined for k in ["门店城市", "store_city"]):
            city_field = "store_city"
        elif any(k in combined for k in ["上牌城市", "license_city"]):
            city_field = "license_city"
        else:
            city_field = "license_city"
        return run_city_tier_distribution_operator(
            df=df,
            start=str(start),
            end=str(end),
            series=str(series) if series is not None else None,
            city_field=city_field,
            time_field="lock_time",
        )

    if _is_age_cohort_plan(plan, user_query):
        query_tool._load_datasets()
        df = query_tool.datasets.get("order_data")
        if df is None:
            return {"type": "age_cohort_distribution", "error": "dataset_not_found", "message": "缺少 order_data 数据集"}
        time = (plan or {}).get("time", {}) or {}
        start = time.get("start")
        end = time.get("end")
        if not start or not end:
            return {"type": "age_cohort_distribution", "error": "missing_time_window", "message": "年龄占比分布需要明确 start/end"}
        series = None
        filters = plan.get("filters", [])
        for f in filters:
            if f.get("field") in ("series", "series_group_logic") and f.get("op") == "==":
                series = f.get("value")
                break
        combined_text = " ".join([str(user_query or ""), str(plan.get("question") or "")]).replace(" ", "")
        use_order = any(k in combined_text for k in ["订单用户", "订单年龄", "订单用户年龄", "购车人年龄", "order_age", "buyer_age"])
        if use_order:
            age_field = "buyer_age"
            identity_field = "buyer_identity_no"
        else:
            age_field = "owner_age"
            identity_field = "owner_identity_no"
        return run_age_cohort_operator(
            df=df,
            user_query=" ".join([str(user_query or ""), str(plan.get("question") or "")]).strip(),
            start=str(start),
            end=str(end),
            series=str(series) if series is not None else None,
            age_field=age_field,
            identity_field=identity_field if identity_field in df.columns else None,
            time_field="lock_time",
        )

    if _is_retained_intention_conversion_plan(plan, user_query):
        query_tool._load_datasets()
        df = query_tool.datasets.get("order_data")
        if df is None:
            return {"type": "retained_intention_conversion", "error": "dataset_not_found", "message": "缺少 order_data 数据集"}
        time = (plan or {}).get("time", {}) or {}
        start = time.get("start")
        end = time.get("end")
        if not start or not end:
            return {"type": "retained_intention_conversion", "error": "missing_time_window", "message": "留存小订转化算子需要明确 start/end"}
        series = None
        filters = plan.get("filters", [])
        for f in filters:
            if f.get("field") in ("series", "series_group_logic") and f.get("op") == "==":
                series = f.get("value")
                break
        bdef: dict = {}
        if "series_group_logic" not in df.columns:
            try:
                bdef_path = Path(__file__).resolve().parents[1] / "schema" / "business_definition.json"
                bdef = json.loads(bdef_path.read_text(encoding="utf-8")) if bdef_path.exists() else {}
                df = apply_series_group_logic(df.copy(), bdef)
            except Exception:
                bdef = {}
        else:
            try:
                bdef_path = Path(__file__).resolve().parents[1] / "schema" / "business_definition.json"
                bdef = json.loads(bdef_path.read_text(encoding="utf-8")) if bdef_path.exists() else {}
            except Exception:
                bdef = {}
        return run_retained_intention_conversion_operator(df=df, series=series, lock_start=start, lock_end=end, business_definition=bdef)

    if _is_retained_intention_plan(plan, user_query):
        query_tool._load_datasets()
        df = query_tool.datasets.get("order_data")
        if df is None:
            return {"type": "retained_intention", "error": "dataset_not_found", "message": "缺少 order_data 数据集"}
        time = (plan or {}).get("time", {}) or {}
        start = time.get("start")
        end = time.get("end")
        if not start or not end:
            return {"type": "retained_intention", "error": "missing_time_window", "message": "留存小订算子需要明确 start/end"}
        series = None
        filters = plan.get("filters", [])
        for f in filters:
            if f.get("field") in ("series", "series_group_logic") and f.get("op") == "==":
                series = f.get("value")
                break
        
        if "series_group_logic" not in df.columns:
            try:
                bdef_path = Path(__file__).resolve().parents[1] / "schema" / "business_definition.json"
                bdef = json.loads(bdef_path.read_text(encoding="utf-8")) if bdef_path.exists() else {}
                df = apply_series_group_logic(df.copy(), bdef)
            except Exception:
                pass
                
        return run_retained_intention_operator(df=df, series=series, start=start, end=end)

    if not _is_active_store_plan(plan, user_query):
        return None
    query_tool._load_datasets()
    df = query_tool.datasets.get("order_data")
    if df is None:
        return {"type": "active_store", "error": "dataset_not_found", "message": "缺少 order_data 数据集"}
    time = (plan or {}).get("time", {}) or {}
    start = time.get("start")
    end = time.get("end")
    if not start or not end:
        return {"type": "active_store", "error": "missing_time_window", "message": "在营门店算子需要明确 start/end"}
    return run_active_store_operator(df=df, start=start, end=end)
