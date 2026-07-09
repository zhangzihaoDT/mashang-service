"""Layer: Inbox Core — keep/discard 二分类"""
"""
inbox_filter.py — keep/discard 二分类过滤。

KEEP:
1. 明确品牌/车型 + 明确事件类型 + 明确信源
2. 明确品牌/车型 + 明确营销动作
3. 涉及上市、预售、权益、交付、发布会、价格、配置、交付数据、门店动作
4. 与 watchlist 车型或品牌直接相关

DISCARD:
1. 没有明确品牌/车型
2. 没有明确事件
3. 泛泛评论、预测、态度、观点
4. 与 watchlist 无关
5. 重复事实（上游调用者处理）
6. 无法形成结构化事实

第一版宁可少收，不要污染事实库。
"""

_KEEP_EVENT_KEYWORDS = [
    "上市", "预售", "权益", "交付", "发布会", "价格", "降价", "涨价",
    "配置", "改款", "OTA", "销量", "战报", "订单", "大定",
    "门店", "试驾", "亮相", "首发", "发布", "官宣", "下线",
    "召回", "合作", "代言", "联名", "融资", "补贴", "限时",
    "预订", "盲订", "开启交付", "首批交付", "月交付",
]

_DISCARD_KEYWORDS = [
    "我觉得", "我认为", "预计", "预测", "可能", "或许", "大概",
    "评论", "观点", "看法", "感受", "体验", "试驾体验",
    "推荐", "建议", "希望", "期待", "如果", "要是",
]


def classify(item: dict) -> dict:
    """
    对单个 raw item 进行二分类。
    返回: {"decision": "keep" | "discard", "reason": str, "item": dict}
    """
    brand = item.get("brand") or ""
    model = item.get("model") or ""
    event_type = item.get("event_type") or ""
    title = item.get("title") or ""
    claim = item.get("claim") or ""
    source_name = item.get("source_name") or ""
    category = item.get("category") or ""

    combined = f"{title} {claim} {category} {event_type}"

    # ── Discard checks (early exit) ──────────────────────────

    # 无品牌无车型
    has_brand_or_model = bool(brand) or bool(model)
    if not has_brand_or_model:
        return _discard(item, "no_brand_or_model: 无明确品牌/车型")

    # 泛泛评论/预测
    for kw in _DISCARD_KEYWORDS:
        if kw in combined:
            return _discard(item, f"opinion_or_prediction: 含主观/预测关键词 \"{kw}\"")

    # 没有事件类型也没有动作关键词
    has_event_type = bool(event_type)
    has_action_kw = any(kw in combined for kw in _KEEP_EVENT_KEYWORDS)

    if not has_event_type and not has_action_kw and not source_name:
        return _discard(item, "no_event_or_action: 无明确事件类型或营销动作关键词")

    # ── Keep checks ──────────────────────────────────────────

    # 明确品牌/车型 + 明确事件类型
    if has_brand_or_model and has_event_type:
        return _keep(item, "brand_model_and_event_type")

    # 明确品牌/车型 + 营销动作关键词
    if has_brand_or_model and has_action_kw:
        return _keep(item, "brand_model_with_action_keywords")

    # 明确品牌/车型 + 明确来源
    if has_brand_or_model and source_name:
        return _keep(item, "brand_model_with_source")

    # 明确品牌/车型 + 涉及 watchlist 核心事件
    watchlist_events = ["上市", "交付", "权益", "价格", "预售", "发布会"]
    if has_brand_or_model and any(kw in combined for kw in watchlist_events):
        return _keep(item, "brand_model_with_watchlist_event")

    # fallback: discard 以确保不污染
    return _discard(item, "no_structured_fact: 无法形成结构化事实")


def _keep(item: dict, reason: str) -> dict:
    return {"decision": "keep", "reason": reason, "item": item}


def _discard(item: dict, reason: str) -> dict:
    return {"decision": "discard", "reason": reason, "item": item}
