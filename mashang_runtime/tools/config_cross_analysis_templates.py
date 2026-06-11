import re
from datetime import date
from typing import Optional

_TEMPLATES: list[dict] = []
_DISTRIBUTION_TEMPLATES: list[dict] = []


def _t(
    name: str,
    keywords: list[str],
    attribute_pattern: str,
    dimension_field: str = "product_name",
    dimension_mapping_key: str = "seat_count_logic",
    positive_value: str = "是",
    description: str = "",
):
    _TEMPLATES.append(dict(
        name=name,
        keywords=keywords,
        attribute_pattern=attribute_pattern,
        dimension_field=dimension_field,
        dimension_mapping_key=dimension_mapping_key,
        positive_value=positive_value,
        description=description or f"{name} 渗透率/选装率",
    ))


def _d(
    name: str,
    keywords: list[str],
    attribute_pattern: str,
    top_k: int = 10,
    description: str = "",
):
    _DISTRIBUTION_TEMPLATES.append(dict(
        name=name,
        keywords=keywords,
        attribute_pattern=attribute_pattern,
        top_k=top_k,
        description=description or f"{name} 选装比例/分布",
    ))


_t("floor_heating",       ["地暖"],                    "地暖")
_t("wheel_hub",           ["轮毂", "轮辋"],             "轮毂|轮辋")
_t("exterior_color",      ["外饰", "颜色"],             "外饰")
_t("interior_color",      ["内饰"],                    "内饰")
_t("benefit_package",     ["礼包", "权益包"],           "礼包")
_t("lidar",               ["激光雷达", "Thor", "Orin"], "激光雷达", positive_value="是|标准|高阶|Thor|Orin")
_t("air_suspension",      ["空气悬架", "空悬", "CDC"],  "空气悬架|CDC")
_t("steering_wheel",      ["方向盘", "半幅方向盘"],      "方向盘")
_t("refrigerator",        ["冰箱"],                    "冰箱")
_t("sunroof",             ["天幕", "防晒天幕"],         "天幕")
_t("sound_system",        ["音响", "扬声器"],           "扬声器|音响")
_t("seat",                ["座椅", "零重力"],           "座椅")
_t("tow_hitch",           ["拖挂", "拖车钩"],           "拖挂")
_t("rear_entertainment",  ["后排屏", "后排娱乐", "观影屏"], "后排.*屏|观影屏")
_t("isc_light",           ["ISC", "尾灯"],             "ISC")
_t("adas",                ["驾驶辅助", "AD", "智驾"],   "AD|驾驶辅助")
_t("trailer_hitch",       ["拖挂系统"],                 "拖挂系统")
_t("steer_by_wire",       ["线控"],                    "线控")

_d("wheel_hub_dist",      ["不同轮毂", "轮毂.*比例", "轮毂.*占比", "轮毂.*分布", "轮毂.*选装"], "轮毂|轮辋", top_k=10)
_d("exterior_color_dist", ["外饰.*比例", "外饰.*占比", "外饰.*分布", "颜色.*比例", "颜色.*占比", "颜色.*分布"], "外饰", top_k=10)
_d("interior_color_dist", ["内饰.*比例", "内饰.*占比", "内饰.*分布"], "内饰", top_k=10)


def match(query: str) -> Optional[dict]:
    q = query.replace(" ", "")
    for t in _TEMPLATES:
        if any(k in q for k in t["keywords"]):
            return dict(t)
    return None


def match_distribution(query: str) -> Optional[dict]:
    q = query.replace(" ", "")
    for t in _DISTRIBUTION_TEMPLATES:
        if any(re.search(k, q) for k in t["keywords"]):
            return dict(t)
    return None


_SERIES_GROUP_TOKENS = {"CM0", "CM1", "CM2", "DM0", "DM1"}
_PRODUCT_TYPE_TOKENS = {"增程", "纯电"}


def _detect_business_filters(query: str, business_def: dict) -> list[dict]:
    q_upper = query.upper().replace(" ", "")
    filters = []

    for token in _SERIES_GROUP_TOKENS:
        if token in q_upper:
            logic = (business_def or {}).get("series_group_logic", {})
            if token in logic:
                filters.append({"field": "series_group_logic", "op": "==", "value": token})
            break

    for token in _PRODUCT_TYPE_TOKENS:
        if token in query:
            logic = (business_def or {}).get("product_type_logic", {})
            if token in logic:
                rule = logic[token]
                or_clauses, not_clauses = _parse_product_type_rule(rule)
                if not_clauses:
                    for v in not_clauses:
                        filters.append({"field": "product_name", "op": "not contains", "value": v})
                if len(or_clauses) == 1:
                    filters.append({"field": "product_name", "op": "contains", "value": or_clauses[0]})
                elif len(or_clauses) > 1:
                    filters.append({"field": "product_name", "op": "matches", "value": "|".join(or_clauses)})
            break

    return filters


def _parse_product_type_rule(rule: str) -> tuple[list[str], list[str]]:
    expr = rule.strip()
    or_terms = [t.strip() for t in expr.split(" OR ") if t.strip()]
    pos_clauses: list[str] = []
    neg_clauses: list[str] = []
    for term in or_terms:
        and_terms = [t.strip() for t in term.split(" AND ") if t.strip()]
        for cond in and_terms:
            negate = " NOT LIKE " in cond
            sep = " NOT LIKE " if negate else " LIKE "
            if sep in cond:
                tok = cond.split(sep, 1)[1].strip().strip("'\"").replace("%", "")
                if tok:
                    (neg_clauses if negate else pos_clauses).append(tok)
    return pos_clauses, neg_clauses


def describe_all() -> str:
    lines = [
        "可用配置渗透率分析模板（analysis_intent.type = attribute_penetration）：",
    ]
    for t in _TEMPLATES:
        kw = " / ".join(t["keywords"])
        lines.append(f"  - {t['name']}: 匹配关键词 [{kw}] → attribute_pattern='{t['attribute_pattern']}'")
    lines.append("")
    lines.append("可用配置分布分析模板（analysis_intent.type = attribute_distribution）：")
    for t in _DISTRIBUTION_TEMPLATES:
        kw = " / ".join(t["keywords"])
        lines.append(f"  - {t['name']}: 匹配关键词 [{kw}] → attribute_pattern='{t['attribute_pattern']}'")
    return "\n".join(lines)


TEMPLATE_CATALOG_MD = describe_all()


def _extract_date_until_today(query: str) -> Optional[str]:
    q = query.replace(" ", "")
    m = re.search(r"(\d{2,4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*至今", q)
    if m:
        y = int(m.group(1))
        if y < 100:
            y += 2000
        try:
            d = date(y, int(m.group(2)), int(m.group(3)))
            return d.isoformat()
        except Exception:
            pass
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s*至今", q)
    if m:
        try:
            return date.fromisoformat(m.group(1)).isoformat()
        except Exception:
            pass
    return None


def is_distribution_query(query: str) -> bool:
    return match_distribution(query) is not None


def build_plan(query: str, business_def: dict) -> Optional[dict]:
    is_dist = is_distribution_query(query)
    tmpl = match_distribution(query) if is_dist else match(query)
    if not tmpl:
        q = query.replace(" ", "")
        if "选装率" in q or "渗透率" in q:
            m = re.search(r"([\u4e00-\u9fff_a-zA-Z0-9]+?)(?:选装率|渗透率)", q)
            if m:
                attr_name = m.group(1)
                tmpl = {
                    "name": "custom",
                    "attribute_pattern": attr_name,
                    "dimension_field": "product_name",
                    "dimension_mapping_key": "seat_count_logic",
                    "positive_value": "是",
                }
        if not tmpl:
            return None

    series_tokens = re.findall(r"(LS\d+|L\d)", query.upper())
    series = series_tokens[0] if series_tokens else None
    group_tokens = [t for t in _SERIES_GROUP_TOKENS if t in query.upper().replace(" ", "")]

    time_periods = business_def.get("time_periods", {}) if isinstance(business_def, dict) else {}
    start = "2020-01-01"
    explicit_start = _extract_date_until_today(query)
    if explicit_start:
        start = explicit_start
    else:
        for key in [series, group_tokens[0] if group_tokens else None]:
            if key and key in time_periods:
                s = time_periods[key].get("end")
                if s:
                    start = s
                    break
    today = date.today().isoformat()

    dim_mapping = {}
    if not is_dist:
        mk = tmpl.get("dimension_mapping_key")
        if mk and isinstance(business_def, dict):
            dim_mapping = business_def.get(mk, {})

    filters = [{"field": "lock_time", "op": "!=", "value": None}]
    if series:
        filters.append({"field": "series", "op": "==", "value": series})
    if "用户车" in query:
        filters.append({"field": "order_type", "op": "==", "value": "用户车"})

    biz_filters = _detect_business_filters(query, business_def)
    filters.extend(biz_filters)

    if is_dist:
        analysis_intent = {
            "type": "attribute_distribution",
            "attribute_pattern": tmpl["attribute_pattern"],
            "top_k": tmpl.get("top_k", 10),
        }
    else:
        analysis_intent = {
            "type": "attribute_penetration",
            "attribute_pattern": tmpl["attribute_pattern"],
            "dimension_field": tmpl["dimension_field"],
        }
        if dim_mapping:
            analysis_intent["dimension_mapping"] = dim_mapping
        positive_value = tmpl.get("positive_value", "是")
        if positive_value != "是":
            analysis_intent["positive_value"] = positive_value

        variants = [v for v in re.split(r"\|", positive_value) if v and len(v) > 1]
        q_clean = query.replace(" ", "")
        matched_variant = next((v for v in variants if v in q_clean), None)
        if matched_variant:
            analysis_intent["value_contains"] = matched_variant

    return {
        "dataset": "order_data",
        "metric": {"field": "order_number", "agg": "count", "alias": "锁单数", "business_name": "锁单量"},
        "time": {"field": "lock_time", "start": start, "end": today},
        "filters": filters,
        "comparison": {"type": "none"},
        "analysis_intent": analysis_intent,
    }
