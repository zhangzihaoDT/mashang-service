"""
inbox_filter.py — Planner 日报按章节路由。

路由规则:
  brand_events       → confirmed_fact  (写入 facts 表)
  review_signals     → review_signal   (写入 signals 表)
  brand_status       → brand_status    (写入 brand_status 表)
  brand_volume       → brand_volume    (写入 brand_volume 表)
  other              → other
"""

_SECTION_ROUTE_MAP = {
    "brand_events":   "confirmed_fact",
    "review_signals": "review_signal",
    "brand_status":   "brand_status",
    "brand_volume":   "brand_volume",
    "other":          "other",
}


def route(item: dict) -> dict:
    """
    对 Planner item 按 section_type 路由。
    返回: {"decision": "route", "route_to": str, "reason": str, "item": dict}
    """
    section_type = item.get("section_type")
    route_to = _SECTION_ROUTE_MAP.get(section_type, "other")
    return {
        "decision": "route",
        "route_to": route_to,
        "reason": f"planner_section:{section_type}" if section_type else "no_section_type",
        "item": item,
    }
