"""Layer: Inbox Core — 基于 facts 生成去重聚类简报"""
"""
brief_renderer.py — facts → daily brief markdown。

关键特性:
  - 自动过滤 is_test / quality_status=test|invalid 数据
  - event-level dedup / clustering
  - 结构化简报：今日重点 → 品牌速览 → 事件类型 → 观察 → 信源质量
  - 空状态报告
"""

from datetime import datetime
from collections import defaultdict, OrderedDict

_MARK_TEST_BRANDS = {"A", "B", "C", "D"}

_EVENT_TYPE_PRIORITY = {
    "上市": 100, "预售": 95, "预订": 90, "盲订": 88,
    "价格": 85, "降价": 85, "涨价": 80,
    "权益": 80, "权益调整": 80, "补贴": 75, "限时": 70,
    "交付": 75, "开启交付": 75, "交付数据": 70,
    "改款": 65, "改款上市": 65, "新款": 60,
    "发布会": 60, "发布": 55, "新品发布": 55,
    "销量": 50, "销量里程碑": 50, "订单": 50,
    "合作": 45, "战略合作": 45, "联名": 40,
    "OTA": 40, "技术": 35, "技术发布": 35,
    "融资": 30, "召回": 25,
}

_SOURCE_TIER_PRIORITY = {
    "tier_1_official": 100,
    "tier_2_authoritative": 80,
    "tier_3_industry_media": 60,
    "tier_4_social_signal": 40,
    "tier_5_unverified": 20,
}

# 事件类型 English → Chinese 显示名映射
_EVENT_TYPE_DISPLAY = {
    "launch": "上市",
    "presale": "预售",
    "preorder": "预订",
    "blind_order": "盲订",
    "benefit_adjustment": "权益调整",
    "price_adjustment": "价格调整",
    "delivery_start": "交付",
    "delivery_metric": "交付数据",
    "sales_milestone": "销量里程碑",
    "order_milestone": "订单里程碑",
    "technology_release": "技术发布",
    "ota_update": "OTA 更新",
    "product_update": "产品更新",
    "launch_event": "发布会",
    "channel_campaign": "渠道活动",
    "store_activity": "门店活动",
    "dealer_activity": "经销商活动",
    "partnership": "合作",
    "brand_campaign": "品牌活动",
    "executive_voice": "高管发声",
    "public_opinion": "舆情",
    "test_drive": "试驾",
    "recall": "召回",
    "funding": "融资",
}

# 频道/平台后缀 → 清理
_CLEAN_TITLE_SUFFIXES = [
    "_易车", "_手机新浪网", "_新浪财经_新浪网", "_新浪汽车",
    "|手机新浪网", "|zeekr 9x",
    "_zaker新闻", "_太平洋汽车", "_懂车帝",
]


def _display_event_type(raw: str) -> str:
    """将原始 event_type 映射为中文显示名。"""
    if not raw:
        return "其他"
    # Direct match
    if raw in _EVENT_TYPE_DISPLAY:
        return _EVENT_TYPE_DISPLAY[raw]
    # Chinese already
    for cn in _EVENT_TYPE_PRIORITY:
        if cn in raw:
            return cn
    # Partial match
    for eng, cn in _EVENT_TYPE_DISPLAY.items():
        if eng in raw:
            return cn
    return raw


def _clean_title(title: str) -> str:
    """清理标题中的站点后缀/平台水印。"""
    if not title:
        return ""
    t = title.strip()
    for suf in _CLEAN_TITLE_SUFFIXES:
        if suf in t:
            t = t.split(suf)[0].strip()
    # Trim trailing site patterns: " - 新浪", "_易车" etc
    import re
    t = re.sub(r"[/_|]\s*(手机)?新浪.*$", "", t)
    t = re.sub(r"[/_|]\s*易车.*$", "", t)
    t = re.sub(r"[/_|]\s*(汽车之家|太平洋汽车|懂车帝|zaker).*$", "", t)
    return t[:80]


# ── Filtering ──

def _is_clean_fact(fact: dict) -> bool:
    """判断是否属于有效事实（非测试、非夹具）。"""
    if fact.get("is_test"):
        return False
    qs = fact.get("quality_status") or ""
    if qs in ("test", "invalid"):
        return False
    brand = (fact.get("brand") or "").strip()
    if brand in _MARK_TEST_BRANDS:
        return False
    title = (fact.get("title") or "").strip()
    if title == "Test":
        return False
    source = (fact.get("source_name") or "").strip()
    if source == "src":
        return False
    return True


def clean_facts(facts: list[dict]) -> list[dict]:
    return [f for f in facts if _is_clean_fact(f)]


# ── Event-level dedup / clustering ──

def _normalize_title_for_key(title: str) -> str:
    """截取前 40 字符作为聚类 key 的一部分。"""
    return (title or "")[:40].strip()


def _make_event_key(fact: dict) -> str:
    brand = (fact.get("brand") or "").strip()
    model = (fact.get("model") or "").strip()
    event_type = _display_event_type(fact.get("event_type", ""))
    title = _normalize_title_for_key(_clean_title(fact.get("title", "")))
    return f"{brand}|{model}|{event_type}|{title}"


def _cluster_facts(facts: list[dict]) -> list[dict]:
    """将 facts 按事件聚类，每类合并来源计数。"""
    clusters: dict[str, dict] = {}
    for f in facts:
        key = _make_event_key(f)
        if key not in clusters:
            clusters[key] = {
                "brand": f.get("brand", ""),
                "model": f.get("model", ""),
                "event_type": _display_event_type(f.get("event_type", "")),
                "title": _clean_title(f.get("title", "")),
                "source_count": 0,
                "sources": [],
                "best_source_tier": f.get("source_tier", ""),
                "last_seen": f.get("last_seen", ""),
                "seen_count": 0,
            }
        c = clusters[key]
        c["source_count"] += 1
        c["seen_count"] += f.get("seen_count", 1)
        src = f.get("source_name", "") or ""
        if src and src not in c["sources"]:
            c["sources"].append(src)
        tier = f.get("source_tier", "") or ""
        if tier and (_SOURCE_TIER_PRIORITY.get(tier, 0) > _SOURCE_TIER_PRIORITY.get(c["best_source_tier"], 0)):
            c["best_source_tier"] = tier
        ls = f.get("last_seen", "") or ""
        if ls > c["last_seen"]:
            c["last_seen"] = ls
            c["title"] = _clean_title(f.get("title", ""))
    return list(clusters.values())


def _brief_rank(cluster: dict) -> tuple:
    et = (cluster.get("event_type") or "")[:10]
    et_score = max((v for k, v in _EVENT_TYPE_PRIORITY.items() if k in et), default=30)
    st = cluster.get("best_source_tier") or ""
    st_score = max((v for k, v in _SOURCE_TIER_PRIORITY.items() if k in st), default=10)
    source_count = min(cluster.get("source_count", 1), 20)
    return (et_score + st_score + source_count, cluster.get("last_seen", ""))


# ── Generate brief ──

def generate_brief(facts: list[dict], title: str = None, brief_date: str = None,
                   signals: list[dict] = None,
                   brand_statuses: list[dict] = None,
                   brand_volumes: list[dict] = None) -> str:
    """
    从 facts（+ 可选 signals / brand_statuses / brand_volumes）生成简报。

    brief_date 支持 "YYYY-MM-DD"（单日）或 "YYYY-MM-DD~YYYY-MM-DD"（周期）格式。
    如果有效 facts 为空，生成空状态报告（含额外数据时仍输出各章节）。
    """
    clean = clean_facts(facts)
    filtered_count = len(facts) - len(clean)
    clusters = _cluster_facts(clean)
    ranked = sorted(clusters, key=_brief_rank, reverse=True)

    is_range = brief_date and "~" in brief_date
    if brief_date:
        date_str = brief_date
    else:
        dates = [f.get("event_date") for f in clean if f.get("event_date")]
        date_str = max(set(dates), key=dates.count) if dates else datetime.now().strftime("%Y-%m-%d")

    report_type_label = "周期简报" if is_range else "每日简报"
    brief_title = title or f"Auto Launch {report_type_label} — {date_str}"

    # Check if we have any data at all
    has_facts = bool(clusters)
    has_extra = bool(signals) or bool(brand_statuses) or bool(brand_volumes)
    has_any = has_facts or has_extra

    if not has_any:
        return _empty_brief(title, filtered_count)

    # Count brands
    brands_in = set(c["brand"] for c in clusters if c.get("brand"))
    has_official = any("tier_1" in (c.get("best_source_tier") or "") for c in clusters)

    section_label = "近期重点" if is_range else "今日重点"
    period_label = "本周期" if is_range else "今日"

    lines = [f"# {brief_title}", ""]

    # ── 近期/今日重点（facts 部分） ──
    if has_facts:
        lines.append(f"## {section_label}")
        lines.append("")
        top = ranked[:5]
        for i, c in enumerate(top, 1):
            brand = c.get("brand") or "?"
            model = c.get("model") or ""
            et = c.get("event_type") or "?"
            title_text = (c.get("title") or "")[:60]
            src_cnt = c.get("source_count", 1)
            sources = c.get("sources", [])
            tier = c.get("best_source_tier") or ""
            tier_label = _tier_label(tier)
            model_tag = f" {model}" if model else ""
            badge = _badge(c)
            evidence = f"（{src_cnt} 个来源）" if src_cnt > 1 else ""
            lines.append(f"  {i}. **[{brand}{model_tag}]** {et} — {title_text}  {badge}")
            lines.append(f"     {tier_label} · {', '.join(sources[:2])} {evidence}")
            lines.append("")
        lines.append("")

    # ── 待审查信号 ──
    if signals:
        lines.append("## 待审查信号")
        lines.append("")
        for i, s in enumerate(signals, 1):
            brand = s.get("brand") or ""
            signal_text = (s.get("claim") or s.get("title") or "")[:100]
            note = (s.get("note") or "")[:80]
            source = s.get("source_name") or ""
            model = s.get("model") or ""
            model_tag = f" [{model}]" if model else ""
            lines.append(f"  {i}. **{brand}{model_tag}**: {signal_text}")
            if note:
                lines.append(f"     原因: {note}")
            if source:
                lines.append(f"     来源: {source}")
            lines.append("")
        lines.append("")

    # ── 品牌动作速览（facts） ──
    if has_facts:
        lines.append("## 品牌动作速览")
        lines.append("")
        by_brand: dict[str, list] = defaultdict(list)
        for c in ranked:
            by_brand[c.get("brand") or "未知"].append(c)
        for brand, items in sorted(by_brand.items()):
            lines.append(f"### {brand}")
            lines.append("")
            for c in items:
                model = c.get("model") or ""
                et = c.get("event_type") or "?"
                title_text = (c.get("title") or "")[:50]
                src_cnt = c.get("source_count", 1)
                badge = _badge(c)
                model_tag = f" {model}" if model else ""
                evidence = f"（{src_cnt} 个来源）" if src_cnt > 1 else ""
                lines.append(f"- **{et}**{model_tag} — {title_text}  {badge} {evidence}")
            lines.append("")

    # ── 事件类型分布 ──
    if has_facts:
        lines.append("## 事件类型分布")
        lines.append("")
        by_event_type: dict[str, list] = defaultdict(list)
        for c in clusters:
            by_event_type[c.get("event_type") or "其他"].append(c)
        for et, items in sorted(by_event_type.items(), key=lambda x: len(x[1]), reverse=True):
            brand_list = ", ".join(sorted(set(c["brand"] for c in items if c.get("brand"))))
            count = sum(c["source_count"] for c in items)
            lines.append(f"- **{et}** — {len(items)} 事件 / {count} 来源 — {brand_list}")
        lines.append("")

    # ── Footer ──
    lines.append("---")
    lines.append("")
    total_sources = ["facts"]
    if signals:
        total_sources.append(f"{len(signals)} signals")
    if brand_statuses:
        total_sources.append(f"{len(brand_statuses)} statuses")
    if brand_volumes:
        total_sources.append(f"{len(brand_volumes)} volumes")
    lines.append(f"*简报生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append(f"*数据来源: auto_launch {' + '.join(total_sources)}*")
    lines.append("")

    return "\n".join(lines)


def _empty_brief(title: str = None, filtered_count: int = 0,
                 signals: list[dict] = None,
                 brand_statuses: list[dict] = None,
                 brand_volumes: list[dict] = None) -> str:
    date_str = datetime.now().strftime("%Y-%m-%d")
    t = title or f"Auto Launch 每日简报 — {date_str}"
    filter_note = f"\n已过滤 test/invalid 数据 {filtered_count} 条。" if filtered_count else ""

    has_extra = bool(signals) or bool(brand_statuses) or bool(brand_volumes)
    if has_extra:
        lines = [f"# {t}", ""]
        lines.append("## 今日重点")
        lines.append("")
        lines.append(f"（无）— 当前 facts 库无匹配有效事实。{filter_note}")
        lines.append("")
        if signals:
            lines.append("## 待审查信号")
            lines.append("")
            for i, s in enumerate(signals, 1):
                brand = s.get("brand") or ""
                signal_text = (s.get("claim") or s.get("title") or "")[:100]
                note = (s.get("note") or "")[:80]
                source = s.get("source_name") or ""
                model = s.get("model") or ""
                model_tag = f" [{model}]" if model else ""
                lines.append(f"  {i}. **{brand}{model_tag}**: {signal_text}")
                if note:
                    lines.append(f"     原因: {note}")
                if source:
                    lines.append(f"     来源: {source}")
                lines.append("")
            lines.append("")
        lines.append("---")
        lines.append("")
        total = ["facts (空)"]
        if signals:
            total.append(f"{len(signals)} signals")
        if brand_statuses:
            total.append(f"{len(brand_statuses)} statuses")
        if brand_volumes:
            total.append(f"{len(brand_volumes)} volumes")
        lines.append(f"*数据来源: auto_launch {' + '.join(total)}*")
        lines.append("")
        return "\n".join(lines)

    return f"""# {t}

## 今日重点

（无）— 当前 facts 库无匹配有效事实。{filter_note}

## 品牌动作速览

facts 库未发现可用于生成简报的有效事实。

## 事件类型分布

（无）
"""


def _badge(cluster: dict) -> str:
    et = (cluster.get("event_type") or "")[:10]
    high_priority_ets = ["上市", "预售", "价格", "降价", "权益", "交付"]
    if any(k in et for k in high_priority_ets):
        return "`HOT`"
    if "tier_1" in (cluster.get("best_source_tier") or ""):
        return "`official`"
    if cluster.get("source_count", 1) >= 3:
        return "`multi-source`"
    return ""


def _tier_label(tier: str) -> str:
    labels = {
        "tier_1_official": "官方",
        "tier_2_authoritative": "权威媒体",
        "tier_3_industry_media": "行业媒体",
        "tier_4_social_signal": "社交信号",
        "tier_5_unverified": "未验证",
    }
    return labels.get(tier, tier)


# ── Backward compat exports ──

def _group_by_event_type(items: list) -> list[tuple[str, list]]:
    """Legacy: group by event type category (used by tests)."""
    groups: dict[str, list] = defaultdict(list)
    for item in items:
        et = item.get("event_type") or ""
        placed = False
        for gname, keywords in _EVENT_TYPE_GROUPS.items():
            if any(k in et for k in keywords):
                groups[gname].append(item)
                placed = True
                break
        if not placed:
            groups["其他"].append(item)
    result = []
    for gname, _ in _EVENT_TYPE_GROUPS.items():
        if groups.get(gname):
            result.append((gname, groups[gname]))
    if groups.get("其他"):
        result.append(("其他", groups["其他"]))
    return result


_EVENT_TYPE_GROUPS = OrderedDict([
    ("上市/预售", ["上市", "预售", "预订", "盲订", "发布", "新品发布", "发布会", "亮相", "首发"]),
    ("价格/权益", ["价格", "降价", "涨价", "权益", "权益调整", "补贴", "限时", "官方价格调整", "benefit_adjustment"]),
    ("交付/销量", ["交付", "开启交付", "交付数据", "销量", "销量里程碑", "订单", "战报",
                   "delivery_start", "delivery_metric", "sales_milestone", "order_milestone",
                   "monthly_sales", "monthly_delivery", "sales_data"]),
    ("产品/技术", ["改款", "改款上市", "新款", "OTA", "技术", "技术发布", "配置",
                   "technology_release", "ota_update", "product_update"]),
    ("品牌/合作", ["合作", "战略合作", "联名", "代言", "融资", "品牌",
                   "channel_campaign", "store_activity", "dealer_activity", "partnership",
                   "brand_campaign", "executive_voice", "public_opinion"]),
    ("其他", []),
])

def brief_rank(item: dict) -> tuple:
    """Legacy: compute rank for a single fact (used by tests)."""
    et = (item.get("event_type") or "")[:10]
    et_score = max((v for k, v in _EVENT_TYPE_PRIORITY.items() if k in et), default=30)
    st = item.get("source_tier") or ""
    st_score = max((v for k, v in _SOURCE_TIER_PRIORITY.items() if k in st), default=10)
    seen = min(item.get("seen_count", 1), 20)
    last_seen = item.get("last_seen") or ""
    penalty = 0
    if not item.get("source_url"):
        penalty -= 10
    if not item.get("event_date"):
        penalty -= 5
    if not item.get("model"):
        penalty -= 3
    return (et_score + st_score + seen + penalty, last_seen)
