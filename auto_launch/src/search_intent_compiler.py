"""Layer: Search Pipeline — 自然语言 → search_intent"""
"""
search_intent_compiler.py — 将用户自然语言需求转为结构化 search_intent。

用法:
  python search_intent_compiler.py --request "看看极氪最近 7 天都有什么动作" --date 2026-07-02
  python search_intent_compiler.py --request "看看问界 M7 最近 7 天权益和价格有什么变化" --date 2026-07-02
"""

import re, json, sys
from datetime import datetime, timedelta
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = MODULE_DIR.parent
PROJECT_ROOT = SERVICE_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

import yaml

# ── 品牌 → 稳定英文 slug 映射 ───────────────────────

_BRAND_SLUG_MAP = {
    "极氪": "zeekr",
    "领克": "lynk_co",
    "问界": "aito",
    "智界": "luxeed",
    "享界": "stelato",
    "尊界": "maextro",
    "尚界": "saic_shangjie",
    "鸿蒙智行": "hima",
    "智己": "im",
    "理想": "lixiang",
    "小米": "xiaomi",
    "小米汽车": "xiaomi",
    "蔚来": "nio",
    "乐道": "onvo",
    "萤火虫": "firefly",
    "小鹏": "xpeng",
    "阿维塔": "avatr",
    "深蓝": "deepal",
    "零跑": "leapmotor",
    "腾势": "denza",
    "方程豹": "fangchengbao",
    "比亚迪": "byd",
    "特斯拉": "tesla",
    "埃安": "aion",
    "岚图": "voyah",
    "大众": "volkswagen",
    "MONA": "mona",
}


def _make_slug(brand: str, model: str = None) -> str:
    """生成稳定英文 slug，优先查表，再 fallback 拼音"""
    base = _BRAND_SLUG_MAP.get(brand, brand.lower().replace(" ", "_")[:20])
    if model:
        model_slug = model.lower().replace(" ", "_").replace("/", "_")
        return f"{base}_{model_slug}"
    return base

# ── 配置加载 ──────────────────────────────────────────

def _load_watchlists():
    brand_path = SERVICE_ROOT / "configs" / "priority_brand_watchlist.yaml"
    model_path = SERVICE_ROOT / "configs" / "ls8_competitor_watchlist.yaml"
    brands = {}
    models = {}
    if brand_path.exists():
        with open(brand_path) as f:
            data = yaml.safe_load(f)
        for cat in data.get("brands", []):
            for sb in cat.get("sub_brands", []):
                name = sb["name"]
                kw = sb.get("keywords", cat.get("keywords", []))
                brands[name] = {"catalog": cat["catalog"], "keywords": kw, "models": sb.get("models", [])}
                for mod in sb.get("models", []):
                    models[f"{name}{mod}"] = {"brand": name, "model": mod}
                    models[f"{name} {mod}"] = {"brand": name, "model": mod}
    if model_path.exists():
        with open(model_path) as f:
            data = yaml.safe_load(f)
        for t in data.get("targets", []):
            key = t["display_name"].replace(" ", "")
            models[key] = {"brand": t["brand"], "model": t["model"], "target_id": t["target_id"]}
            models[t["display_name"]] = {"brand": t["brand"], "model": t["model"], "target_id": t["target_id"]}
            for a in t.get("model_aliases", []):
                models[a] = {"brand": t["brand"], "model": t["model"], "target_id": t["target_id"]}
            for a in t.get("brand_aliases", []):
                if a not in brands:
                    brands[a] = {"catalog": "", "keywords": [t["brand"]], "models": []}
    return brands, models


def _load_event_types():
    path = SERVICE_ROOT / "configs" / "event_types.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f)


def _load_source_tiers():
    path = SERVICE_ROOT / "configs" / "source_tiers.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f)


# ── mode 判断 ─────────────────────────────────────────

_MODE_PATTERNS = [
    (r"(?:看看|查查|搜一下|搜索)\s*(.+品牌|.+旗下)\s*(?:最近|近期|这段|有什么|动作|事件|营销|消息)", "brand_watch"),
    (r"(?:看看|查查|搜一下|搜索)\s*(?:品牌|集团)\s*(.+)\s*(?:最近|近期|有什么|动作|营销|事件)", "brand_watch"),
    (r"(?:看看|查查)\s*(.+?[车型])\s*(?:最近|近期|有什么|动作|权益|价格|上市|交付)", "model_watch"),
]

_BRAND_ONLY_KEYWORDS = ["品牌", "营销", "传播", "campaign", "声量"]
_MODEL_ONLY_KEYWORDS = ["车型", "交付", "改款", "评测", "试驾", "配置"]


def infer_mode(request: str, has_model_match: bool) -> str:
    req_lower = request.lower().replace(" ", "")

    # explicit model mention
    for kw in _MODEL_ONLY_KEYWORDS:
        if kw in req_lower:
            return "model_watch"

    for kw in _BRAND_ONLY_KEYWORDS:
        if kw in req_lower:
            return "brand_watch"

    if has_model_match:
        return "model_watch"

    return "brand_watch"


# ── target 识别 ───────────────────────────────────────

def identify_targets(request: str, brands: dict, models: dict):
    targets = []
    seen = set()

    # try model match first (longer substring = more specific)
    matches = []
    for key, info in models.items():
        if key in request:
            matches.append((len(key), key, info))
    matches.sort(reverse=True)

    for length, key, info in matches:
        brand_name = info["brand"]
        if brand_name in seen:
            continue
        seen.add(brand_name)
        is_in_wl = "target_id" in info
        model = info.get("model")
        targets.append({
            "target_id": info.get("target_id") if is_in_wl else _make_slug(brand_name, model),
            "target_type": "model" if model else "brand",
            "brand": brand_name,
            "brand_cn": brand_name,
            "model": model,
            "matched_alias": key,
            "confidence": "high" if is_in_wl else "medium",
            "is_in_watchlist": is_in_wl,
            "target_source": "ls8_watchlist" if is_in_wl else "ad_hoc_user_request",
        })
        break  # only one target per request

    if not targets:
        # try brand match
        for name, info in brands.items():
            if name in request:
                is_in_wl = True
                slug = _make_slug(name)
                targets.append({
                    "target_id": slug,
                    "target_type": "brand",
                    "brand": name,
                    "brand_cn": name,
                    "model": None,
                    "matched_alias": name,
                    "confidence": "high",
                    "is_in_watchlist": is_in_wl,
                    "target_source": "brand_watchlist",
                })
                seen.add(name)
                break

    # ad_hoc if nothing matched
    if not targets:
        tokens = re.sub(r"[看看查查搜索最近近期天今天明天昨天都有什么动作事件消息营销]", "", request).strip()
        if tokens:
            raw_slug = tokens[:20].replace(" ", "_")
            targets.append({
                "target_id": f"adhoc_{raw_slug}",
                "target_type": "brand",
                "brand": tokens[:10],
                "brand_cn": tokens[:10],
                "model": None,
                "matched_alias": tokens[:10],
                "confidence": "low",
                "is_in_watchlist": False,
                "target_source": "ad_hoc_user_request",
            })

    return targets


# ── 时间窗口识别 ──────────────────────────────────────

def infer_time_window(request: str, monitor_date_str: str):
    monitor_date = datetime.strptime(monitor_date_str, "%Y-%m-%d")

    patterns = [
        (r"最近\s*(\d+)\s*天", lambda m: int(m.group(1))),
        (r"近\s*一周|本周", lambda m: 7),
        (r"最近\s*24\s*小时", lambda m: 1),
        (r"最近\s*48\s*小时", lambda m: 2),
        (r"过去\s*一个?月|最近\s*30\s*天", lambda m: 30),
        (r"今天|今日", lambda m: 0),
        (r"昨天|昨日", lambda m: 1),
    ]

    days = None
    for pat, fn in patterns:
        m = re.search(pat, request)
        if m:
            days = fn(m)
            break

    if days is None:
        # default: primary=1, fallback=7
        start = monitor_date - timedelta(days=1)
        return {
            "window_type": "default",
            "days": 1,
            "fallback_days": 7,
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": monitor_date.strftime("%Y-%m-%d"),
            "start_datetime": start.strftime("%Y-%m-%dT00:00:00+08:00"),
            "end_datetime": monitor_date.strftime("%Y-%m-%dT23:59:59+08:00"),
            "timezone": "Asia/Shanghai",
            "date_inclusive": True,
        }

    if days == 0:
        md = monitor_date
        return {
            "window_type": "today",
            "days": 0,
            "start_date": md.strftime("%Y-%m-%d"),
            "end_date": md.strftime("%Y-%m-%d"),
            "start_datetime": md.strftime("%Y-%m-%dT00:00:00+08:00"),
            "end_datetime": md.strftime("%Y-%m-%dT23:59:59+08:00"),
            "timezone": "Asia/Shanghai",
            "date_inclusive": True,
        }

    start = monitor_date - timedelta(days=days)
    return {
        "window_type": "relative_days",
        "days": days,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": monitor_date.strftime("%Y-%m-%d"),
        "start_datetime": start.strftime("%Y-%m-%dT00:00:00+08:00"),
        "end_datetime": monitor_date.strftime("%Y-%m-%dT23:59:59+08:00"),
        "timezone": "Asia/Shanghai",
        "date_inclusive": True,
    }


# ── event_scope 识别 ──────────────────────────────────

_EVENT_KEYWORD_MAP = [
    (r"价格|降价|涨价|售价|调价", ["official_price_change"]),
    (r"权益|优惠|金融|置换|补贴", ["benefit_adjustment"]),
    (r"上市|发布|开售", ["launch"]),
    (r"预售|盲订|预订", ["presale"]),
    (r"交付|提车|交车", ["delivery_start", "order_milestone"]),
    (r"订单|大定|锁单|战报|销量", ["order_milestone", "sales_milestone"]),
    (r"发布会|亮相|首发", ["launch_event", "debut"]),
    (r"改款|新款|2026款", ["facelift_launch"]),
    (r"配置|参数|版本", ["config_release"]),
    (r"营销|传播|campaign|广告|品牌片", ["brand_campaign"]),
    (r"活动|试驾|巡展|门店", ["channel_campaign", "user_event"]),
    (r"联名|代言|合作", ["partnership"]),
    (r"高管|直播|访谈", ["executive_voice"]),
    (r"爆料|路透|销售|风声|疑似|据说", ["rumor_or_leak"]),
    (r"技术|智驾|电池|平台", ["technology_release"]),
]

_ALL_EVENT_IDS = [
    "launch", "presale", "launch_event", "debut", "config_release",
    "price_release", "delivery_start", "benefit_adjustment", "official_price_change",
    "facelift_launch", "brand_campaign", "sales_milestone", "production_milestone",
    "technology_release", "channel_campaign", "user_event", "partnership",
    "executive_voice", "public_opinion", "rumor_or_leak",
]


def infer_event_scope(request: str, mode: str, event_types_config: dict):
    req_lower = request.replace(" ", "")

    # open-ended scan
    if any(kw in req_lower for kw in ["有什么动作", "有什么消息", "都有什么", "有什么事件", "全量"]):
        return {
            "scope_type": "all_relevant_actions",
            "event_type_ids": _ALL_EVENT_IDS,
        }

    matched_ids = []
    for pat, ids in _EVENT_KEYWORD_MAP:
        if re.search(pat, request):
            for eid in ids:
                if eid not in matched_ids:
                    matched_ids.append(eid)
                # also include mode-appropriate additional types
    if not matched_ids:
        return {
            "scope_type": "all_relevant_actions",
            "event_type_ids": _ALL_EVENT_IDS,
        }

    return {
        "scope_type": "specific_events",
        "event_type_ids": matched_ids,
    }


# ── source_strategy ───────────────────────────────────

def infer_source_strategy(request: str):
    req_lower = request.replace(" ", "")

    if "只看官方" in req_lower or "官方源" in req_lower:
        return {
            "official_first": True,
            "include_authoritative_media": False,
            "include_industry_media": False,
            "include_social_signals": False,
            "social_signals_as_discovery_only": True,
            "allow_unverified_as_discovery_only": False,
        }

    if any(kw in req_lower for kw in ["风声", "爆料", "路透", "销售说", "经销商", "传闻"]):
        return {
            "official_first": True,
            "include_authoritative_media": True,
            "include_industry_media": True,
            "include_social_signals": True,
            "social_signals_as_discovery_only": True,
            "allow_unverified_as_discovery_only": True,
        }

    if any(kw in req_lower for kw in ["媒体怎么说", "媒体评价", "报道", "评测"]):
        return {
            "official_first": False,
            "include_authoritative_media": True,
            "include_industry_media": True,
            "include_social_signals": False,
            "social_signals_as_discovery_only": True,
            "allow_unverified_as_discovery_only": False,
        }

    if any(kw in req_lower for kw in ["传播", "声量", "热度", "讨论"]):
        return {
            "official_first": True,
            "include_authoritative_media": True,
            "include_industry_media": True,
            "include_social_signals": True,
            "social_signals_as_discovery_only": True,
            "allow_unverified_as_discovery_only": True,
        }

    # default
    return {
        "official_first": True,
        "include_authoritative_media": True,
        "include_industry_media": True,
        "include_social_signals": True,
        "social_signals_as_discovery_only": True,
        "allow_unverified_as_discovery_only": True,
    }


# ── 主函数 ────────────────────────────────────────────

def compile_intent(request: str, monitor_date: str = None, output_path: str = None):
    if monitor_date is None:
        monitor_date = datetime.now().strftime("%Y-%m-%d")

    brands, models = _load_watchlists()
    event_types_config = _load_event_types()

    targets = identify_targets(request, brands, models)
    has_model = any(t["target_type"] == "model" for t in targets)
    mode = infer_mode(request, has_model)

    time_window = infer_time_window(request, monitor_date)
    event_scope = infer_event_scope(request, mode, event_types_config)
    source_strategy = infer_source_strategy(request)

    ambiguities = []
    if mode == "unknown":
        ambiguities.append({"field": "mode", "reason": "无法判断监控模式，需用户补充品牌或车型信息"})
    if not targets:
        ambiguities.append({"field": "target", "reason": "未识别到目标品牌或车型"})

    notes = []
    if event_scope["scope_type"] == "all_relevant_actions":
        notes.append(f"用户问题为开放式动作扫描，自动覆盖{'品牌' if mode == 'brand_watch' else '车型'}级全量事件。")

    intent = {
        "user_request": request,
        "monitor_date": monitor_date,
        "intent_type": "open_ended_activity_scan" if event_scope["scope_type"] == "all_relevant_actions" else "specific_event_scan",
        "mode": mode,
        "targets": targets,
        "time_window": time_window,
        "event_scope": event_scope,
        "source_strategy": source_strategy,
        "query_budget": {
            "query_budget_per_target": 8,
            "result_limit_per_query": 10,
        },
        "ambiguities": ambiguities,
        "notes": notes,
    }

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(intent, f, ensure_ascii=False, indent=2)
        print(f"[intent] 已写入: {output_path}")

    return intent


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="搜索意图转译器")
    parser.add_argument("--request", required=True, help="用户自然语言请求")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="监控日期")
    parser.add_argument("--output", help="输出路径")
    args = parser.parse_args()

    intent = compile_intent(args.request, args.date, args.output)
    print(json.dumps(intent, ensure_ascii=False, indent=2))
