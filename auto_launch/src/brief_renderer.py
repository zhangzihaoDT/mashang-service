"""Layer: Inbox Core — 基于 facts 生成 Markdown 每日简报"""

from datetime import datetime
from collections import defaultdict, OrderedDict

# 事件类型排序权重（数值越高越优先）
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

_EVENT_TYPE_GROUPS = OrderedDict([
    ("上市/预售", ["上市", "预售", "预订", "盲订", "发布", "新品发布", "发布会", "亮相", "首发"]),
    ("价格/权益", ["价格", "降价", "涨价", "权益", "权益调整", "补贴", "限时", "官方价格调整"]),
    ("交付/销量", ["交付", "开启交付", "交付数据", "销量", "销量里程碑", "订单", "战报"]),
    ("产品/技术", ["改款", "改款上市", "新款", "OTA", "技术", "技术发布", "配置"]),
    ("品牌/合作", ["合作", "战略合作", "联名", "代言", "融资", "品牌"]),
    ("其他", []),
])


def brief_rank(item: dict) -> tuple:
    """
    计算单条事实的排序分值。
    返回 tuple 用于 sorted(..., reverse=True)。
    维度：事件类型权重 + 信源权重 + seen_count + 最近出现时间 - 缺失惩罚。
    """
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


def generate_brief(facts: list[dict], title: str = None) -> str:
    """
    基于 facts 生成 Markdown 简报。
    返回 Markdown 字符串。
    """
    if not facts:
        return _empty_brief(title)

    ranked = sorted(facts, key=brief_rank, reverse=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    brief_title = title or f"Auto Launch 每日简报 — {date_str}"

    lines = [f"# {brief_title}", ""]

    # ── Section 1: 今日最值得关注 ──────────────────────────
    top = ranked[:5]
    lines.append("## 今日最值得关注")
    lines.append("")
    for i, item in enumerate(top, 1):
        brand = item.get("brand") or "?"
        model = item.get("model") or ""
        et = item.get("event_type") or "?"
        title_text = (item.get("title") or "")[:60]
        tier = item.get("source_tier") or ""
        tier_label = _tier_label(tier)
        source = item.get("source_name") or "?"
        seen = item.get("seen_count", 1)
        badge = _badge(item)
        model_tag = f" {model}" if model else ""
        lines.append(f"  {i}. **[{brand}{model_tag}]** {et} — {title_text}  {badge}")
        lines.append(f"     {tier_label} · {source} · 出现 {seen} 次")
        lines.append("")
    lines.append("")

    # ── Section 2: 按品牌聚合 ──────────────────────────────
    lines.append("## 按品牌")
    lines.append("")
    by_brand = defaultdict(list)
    for item in ranked:
        by_brand[item.get("brand") or "未知"].append(item)
    for brand, items in sorted(by_brand.items()):
        lines.append(f"### {brand}")
        lines.append("")
        for item in items:
            model = item.get("model") or ""
            et = item.get("event_type") or "?"
            title_text = (item.get("title") or "")[:50]
            badge = _badge(item)
            model_tag = f" {model}" if model else ""
            lines.append(f"- **{et}**{model_tag} — {title_text}  {badge}")
        lines.append("")

    # ── Section 3: 按事件类型聚合 ──────────────────────────
    lines.append("## 按事件类型")
    lines.append("")
    grouped = _group_by_event_type(ranked)
    for group_name, group_items in grouped:
        if not group_items:
            continue
        lines.append(f"### {group_name}")
        lines.append("")
        for item in group_items:
            brand = item.get("brand") or "?"
            model = item.get("model") or ""
            title_text = (item.get("title") or "")[:50]
            badge = _badge(item)
            model_tag = f" {model}" if model else ""
            lines.append(f"- **{brand}{model_tag}** — {title_text}  {badge}")
        lines.append("")

    # ── Section 4: 信源质量 ────────────────────────────────
    lines.append("## 信源质量")
    lines.append("")
    by_tier = defaultdict(int)
    for item in ranked:
        by_tier[item.get("source_tier") or "unknown"] += 1
    for tier, cnt in sorted(by_tier.items(), key=lambda x: _SOURCE_TIER_PRIORITY.get(x[0], 0), reverse=True):
        bar = "█" * min(cnt * 3, 30)
        lines.append(f"- {_tier_label(tier):<30} {bar} {cnt}")
    lines.append("")

    # ── Section 5: 今日观察 ────────────────────────────────
    lines.append("## 今日观察")
    lines.append("")
    total = len(facts)
    brands = len(by_brand)
    top_brand = max(by_brand.items(), key=lambda x: len(x[1])) if by_brand else ("-", [])
    has_official = any("tier_1" in (i.get("source_tier") or "") for i in ranked)
    lines.append(f"- 今日共收录 **{total}** 条事实，涉及 **{brands}** 个品牌")
    lines.append(f"- 最活跃品牌：**{top_brand[0]}**（{len(top_brand[1])} 条）")
    lines.append(f"- 官方源覆盖：{'✅ 有' if has_official else '❌ 无'}")
    if ranked[0].get("event_type"):
        lines.append(f"- 最高优先级事件类型：**{ranked[0]['event_type']}**")
    lines.append("")

    # ── Section 6: Facts Audit 摘要 ────────────────────────
    lines.append("---")
    lines.append("")
    lines.append(f"*简报生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append(f"*数据来源: auto_launch facts 库 {total} 条事实*")
    lines.append("")

    return "\n".join(lines)


def _empty_brief(title: str = None) -> str:
    date_str = datetime.now().strftime("%Y-%m-%d")
    t = title or f"Auto Launch 每日简报 — {date_str}"
    return f"""# {t}

## 今日最值得关注

（无）— 当前事实库无匹配数据。

## 今日观察

- 事实库为空，请通过 inbox 或 search --to-facts 导入事实。
"""


def _badge(item: dict) -> str:
    """为事实生成半角 badge 标签"""
    et = (item.get("event_type") or "")[:10]
    high_priority_ets = ["上市", "预售", "价格", "降价", "权益", "交付"]
    if any(k in et for k in high_priority_ets):
        return "`HOT`"
    if "tier_1" in (item.get("source_tier") or ""):
        return "`official`"
    if item.get("seen_count", 1) >= 3:
        return "`repeated`"
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


def _group_by_event_type(items: list) -> list[tuple[str, list]]:
    """按事件类型分组，返回 [(group_name, items), ...]"""
    ungrouped = []
    by_group = defaultdict(list)
    for item in items:
        et = item.get("event_type") or ""
        placed = False
        for group_name, keywords in _EVENT_TYPE_GROUPS.items():
            if any(k in et for k in keywords):
                by_group[group_name].append(item)
                placed = True
                break
        if not placed:
            ungrouped.append(item)

    result = []
    for gname, _ in _EVENT_TYPE_GROUPS.items():
        if by_group.get(gname):
            result.append((gname, by_group[gname]))
    if ungrouped:
        result.append(("其他", ungrouped))
    return result
