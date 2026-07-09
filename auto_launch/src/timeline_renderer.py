"""Layer: Inbox Core — 品牌/车型事件时间线"""

from collections import defaultdict
from datetime import datetime


def generate_timeline(facts: list[dict], brand: str = None, model: str = None) -> str:
    """从 facts 生成品牌/车型事件时间线。按 event_date 排序，按月份分组。"""
    if not facts:
        return _empty_timeline(brand, model)

    # 按 event_date 过滤有日期的事实
    dated = [f for f in facts if f.get("event_date")]
    undated = [f for f in facts if not f.get("event_date")]

    # 按年月分组
    by_month = defaultdict(list)
    for f in sorted(dated, key=lambda x: x["event_date"], reverse=True):
        ed = f["event_date"]
        month_key = ed[:7]  # YYYY-MM
        by_month[month_key].append(f)

    title_brand = brand or "全部品牌"
    title_model = f" {model}" if model else ""
    lines = [f"# 事件时间线 — {title_brand}{title_model}", ""]
    lines.append(f"*共 {len(facts)} 条事实，{len(dated)} 条含事件日期*")
    lines.append("")

    if not dated:
        lines.append("（无含日期的事实）")
        lines.append("")
        if undated:
            lines.append("## 无日期事件")
            lines.append("")
            for f in undated:
                _append_fact_line(lines, f)
        return "\n".join(lines)

    for month in sorted(by_month.keys(), reverse=True):
        lines.append(f"## {month}")
        lines.append("")
        for f in by_month[month]:
            ed = f.get("event_date", "")[5:]
            brand_tag = f.get("brand") or "?"
            model_tag = f" {f['model']}" if f.get("model") else ""
            et = f.get("event_type") or "?"
            title_text = (f.get("title") or "")[:60]
            tier = f.get("source_tier") or ""
            source = f.get("source_name") or "?"
            seen = f.get("seen_count", 1)
            badge = _badge(f)
            lines.append(f"- **{ed}** [{brand_tag}{model_tag}] **{et}** — {title_text}  {badge}")
            lines.append(f"  {source} · 信源: {_tier_label(tier)} · 出现 {seen} 次")
            lines.append("")

    if undated:
        lines.append("## 无日期事件")
        lines.append("")
        for f in undated:
            _append_fact_line(lines, f)

    lines.append("---")
    lines.append("")
    lines.append(f"*生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")

    return "\n".join(lines)


def _append_fact_line(lines: list, f: dict):
    brand_tag = f.get("brand") or "?"
    model_tag = f" {f['model']}" if f.get("model") else ""
    et = f.get("event_type") or "?"
    title_text = (f.get("title") or "")[:60]
    badge = _badge(f)
    lines.append(f"- [{brand_tag}{model_tag}] **{et}** — {title_text}  {badge}")
    lines.append("")


def _empty_timeline(brand: str = None, model: str = None) -> str:
    t = f"{brand or '全部品牌'}{f' {model}' if model else ''}"
    return f"""# 事件时间线 — {t}

（无）— 当前事实库无匹配数据。
"""


def _badge(f: dict) -> str:
    et = (f.get("event_type") or "")[:10]
    high = ["上市", "预售", "价格", "降价", "权益", "交付"]
    if any(k in et for k in high):
        return "`HOT`"
    if "tier_1" in (f.get("source_tier") or ""):
        return "`official`"
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
