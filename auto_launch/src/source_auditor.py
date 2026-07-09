"""Layer: Intelligence Utilities — 信源覆盖审计"""

import yaml
from pathlib import Path
from collections import defaultdict, Counter


def _load_priority_brands() -> list[dict]:
    """Load brand catalog list from priority_brand_watchlist.yaml — the canonical brand list for expected coverage checks."""
    path = Path(__file__).resolve().parent.parent / "configs" / "priority_brand_watchlist.yaml"
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("brands", [])


def _load_ls8_targets() -> list[dict]:
    """Load LS8 competitor targets from ls8_competitor_watchlist.yaml."""
    path = Path(__file__).resolve().parent.parent / "configs" / "ls8_competitor_watchlist.yaml"
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("targets", [])


def _gather_brand_facts(brand_entry: dict, by_brand: dict) -> list[dict]:
    """Collect facts matching a watchlist brand entry (catalog name + all sub_brand names)."""
    names = [brand_entry["catalog"]]
    for sb in brand_entry.get("sub_brands", []):
        names.append(sb["name"])
    facts = []
    for name in names:
        facts.extend(by_brand.get(name, []))
    return facts


def _gather_target_facts(target: dict, by_brand: dict) -> list[dict]:
    """Collect facts matching an LS8 competitor target (brand + model aliases)."""
    bname = target.get("brand", "")
    mname = target.get("model", "")
    seen_ids = set()
    facts = []
    all_names = [bname] + [a for a in target.get("brand_aliases", []) if a != bname]
    for name in all_names:
        for f in by_brand.get(name, []):
            fid = f.get("fact_id") or id(f)
            if fid in seen_ids:
                continue
            seen_ids.add(fid)
            if not mname or any(a.lower() in (f.get("model") or "").lower() for a in [mname] + target.get("model_aliases", [])):
                facts.append(f)
    if not facts and bname:
        for f in by_brand.get(bname, []):
            fid = f.get("fact_id") or id(f)
            if fid not in seen_ids:
                facts.append(f)
                seen_ids.add(fid)
    return facts


def _tier_label(tier: str) -> str:
    labels = {"tier_1_official": "official", "tier_2_authoritative": "authoritative",
              "tier_3_industry_media": "auto_media", "tier_4_social_signal": "social",
              "tier_5_unverified": "weak"}
    return labels.get(tier, "unknown")


def audit(facts: list[dict], watchlist: str = "priority") -> dict:
    """
    Source quality coverage audit.

    Parameters
    ----------
    facts : list[dict]
        Facts from FactStore.query().
    watchlist : str
        Which watchlist to use for expected coverage checks.
        "priority" — use priority_brand_watchlist.yaml (24 key brands).
        "ls8"     — use ls8_competitor_watchlist.yaml (10 competitor targets).
    """
    if not facts:
        return {"total": 0, "warnings": ["no facts"], "watchlist": watchlist}

    total = len(facts)
    brands = set()
    models = set()
    by_brand = defaultdict(list)
    by_event_type = defaultdict(list)
    flags = []

    for f in facts:
        b = f.get("brand") or ""
        m = f.get("model") or ""
        et = f.get("event_type") or ""
        if b:
            brands.add(b)
        if m:
            models.add(m)
        if b:
            by_brand[b].append(f)
        if et:
            by_event_type[et].append(f)

    # Source tier distribution
    tier_counts = Counter(_tier_label(f.get("source_tier", "")) for f in facts)
    official_count = tier_counts.get("official", 0)
    auto_media_count = tier_counts.get("auto_media", 0)
    social_count = tier_counts.get("social", 0)
    weak_count = tier_counts.get("weak", 0)

    missing_url = sum(1 for f in facts if not f.get("source_url"))
    missing_event_date = sum(1 for f in facts if not f.get("event_date"))
    official_rate = round(official_count / total * 100, 1) if total else 0
    media_rate = round(auto_media_count / total * 100, 1) if total else 0

    # Per-brand breakdown
    brand_coverage = {}
    for b, items in sorted(by_brand.items()):
        t = len(items)
        o = sum(1 for f in items if _tier_label(f.get("source_tier", "")) == "official")
        m = sum(1 for f in items if _tier_label(f.get("source_tier", "")) == "auto_media")
        p = 0  # deprecated portal check
        s = sum(1 for f in items if _tier_label(f.get("source_tier", "")) == "social")
        mu = sum(1 for f in items if not f.get("source_url"))
        brand_coverage[b] = {
            "facts": t, "official": o, "auto_media": m,
            "social": s, "missing_url": mu,
            "official_rate": round(o / t * 100, 1) if t else 0,
        }

    # Per-event-type breakdown
    event_type_coverage = {}
    for et, items in sorted(by_event_type.items()):
        t = len(items)
        o = sum(1 for f in items if _tier_label(f.get("source_tier", "")) == "official")
        m = sum(1 for f in items if _tier_label(f.get("source_tier", "")) == "auto_media")
        w = sum(1 for f in items if _tier_label(f.get("source_tier", "")) in ("social", "weak"))
        event_type_coverage[et] = {
            "facts": t, "official_rate": round(o / t * 100, 1) if t else 0,
            "media_rate": round(m / t * 100, 1) if t else 0,
            "weak_source_count": w,
        }

    # Low quality facts (with flags)
    low_quality = []
    for f in facts:
        lq_flags = []
        if not f.get("source_url"):
            lq_flags.append("missing_source_url")
        if not f.get("event_date"):
            lq_flags.append("missing_event_date")
        tl = _tier_label(f.get("source_tier", ""))
        if tl in ("weak", "social"):
            lq_flags.append(f"weak_source_tier:{f.get('source_tier','')}")
        if tl in ("auto_media",) and f.get("source_tier") != "tier_1_official":
            pass  # media-only is not a quality issue per se
        if tl == "social" or (tl == "weak" and f.get("source_tier") != "tier_1_official"):
            pass
        if lq_flags:
            low_quality.append({
                "fact_id": f.get("fact_id"),
                "brand": f.get("brand"), "title": (f.get("title") or "")[:60],
                "source_tier": f.get("source_tier"), "flags": lq_flags,
            })

    # Expected source coverage check — brand list derived from watchlist config
    expected_flags = []
    if watchlist == "ls8":
        ls8_targets = _load_ls8_targets()
        for t in ls8_targets:
            bname = t.get("display_name", t["target_id"])
            bfacts = _gather_target_facts(t, by_brand)
            if not bfacts:
                continue
            has_official = any(_tier_label(f.get("source_tier", "")) == "official" for f in bfacts)
            has_auto_media = any(_tier_label(f.get("source_tier", "")) == "auto_media" for f in bfacts)
            if not has_official:
                expected_flags.append({"brand": bname, "flag": "expected_official_missing",
                                       "detail": f"未找到 {bname} 官方源事实"})
            if not has_auto_media:
                expected_flags.append({"brand": bname, "flag": "expected_auto_media_missing",
                                       "detail": f"未找到 {bname} 汽车媒体源事实"})
    else:
        priority_brands = _load_priority_brands()
        for entry in priority_brands:
            bname = entry["catalog"]
            bfacts = _gather_brand_facts(entry, by_brand)
            if not bfacts:
                continue
            has_official = any(_tier_label(f.get("source_tier", "")) == "official" for f in bfacts)
            has_auto_media = any(_tier_label(f.get("source_tier", "")) == "auto_media" for f in bfacts)
            if not has_official:
                expected_flags.append({"brand": bname, "flag": "expected_official_missing",
                                       "detail": f"未找到 {bname} 官方源事实"})
            if not has_auto_media:
                expected_flags.append({"brand": bname, "flag": "expected_auto_media_missing",
                                       "detail": f"未找到 {bname} 汽车媒体源事实"})

    # Suggestions
    suggestions = []
    if official_rate < 30:
        suggestions.append("官方源不足（<30%）：建议对低覆盖品牌执行 official_first 搜索")
    if media_rate < 20:
        suggestions.append("汽车媒体源不足（<20%）：建议执行 auto_media_deep 搜索")
    if social_count > total * 0.5:
        suggestions.append(f"社媒/弱信源占比过高（{social_count}/{total}）：建议增加官方/媒体源交叉验证")
    if missing_url > total * 0.3:
        suggestions.append(f"missing_url 偏高（{missing_url}/{total}）：建议检查 parser 或 normalize 是否遗漏 URL")
    if expected_flags:
        for ef in expected_flags[:3]:
            suggestions.append(f"期望信源缺失：{ef['brand']} — {ef['flag']}")

    return {
        "total": total,
        "watchlist": watchlist,
        "brands": len(brands),
        "models": len(models),
        "official_count": official_count,
        "official_rate": official_rate,
        "auto_media_count": auto_media_count,
        "media_rate": media_rate,
        "social_count": social_count,
        "weak_count": weak_count,
        "missing_url": missing_url,
        "missing_event_date": missing_event_date,
        "brand_coverage": brand_coverage,
        "event_type_coverage": event_type_coverage,
        "low_quality_count": len(low_quality),
        "low_quality": low_quality[:20],
        "expected_flags": expected_flags,
        "suggestions": suggestions,
    }


def render_markdown(report: dict) -> str:
    if report["total"] == 0:
        return "# Source Coverage Audit\n\n（无数据）\n"

    lines = ["# Source Coverage Audit", ""]
    watchlist_label = f" ({report.get('watchlist', 'priority')})" if report.get("watchlist") else ""
    lines.append(f"**Watchlist:** {report.get('watchlist', 'priority')}  ")
    lines.append(f"**Total facts:** {report['total']}  ")
    lines.append(f"**Brands covered:** {report['brands']}  ")
    lines.append(f"**Models covered:** {report['models']}  ")
    lines.append(f"**Official rate:** {report['official_rate']}% ({report['official_count']}/{report['total']})  ")
    lines.append(f"**Auto media rate:** {report['media_rate']}% ({report['auto_media_count']}/{report['total']})  ")
    lines.append(f"**Social/weak:** {report['social_count'] + report['weak_count']}/{report['total']}  ")
    lines.append(f"**Missing source_url:** {report['missing_url']}  ")
    lines.append(f"**Missing event_date:** {report['missing_event_date']}  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Per-brand
    lines.append("## Per-Brand Coverage")
    lines.append("")
    hdr = f"{'brand':<12} {'facts':<7} {'official':<9} {'media':<6} {'social':<7} {'missing_url':<12} {'official_rate':<14}"
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for b, cov in sorted(report["brand_coverage"].items()):
        lines.append(f"{b:<12} {cov['facts']:<7} {cov['official']:<9} {cov['auto_media']:<6} {cov['social']:<7} {cov['missing_url']:<12} {cov['official_rate']}%")
    lines.append("")

    # Per event type
    lines.append("## Per-Event-Type Coverage")
    lines.append("")
    hdr2 = f"{'event_type':<20} {'facts':<7} {'official_rate':<14} {'media_rate':<12} {'weak_count':<12}"
    lines.append(hdr2)
    lines.append("-" * len(hdr2))
    for et, cov in sorted(report["event_type_coverage"].items()):
        lines.append(f"{et[:18]:<20} {cov['facts']:<7} {cov['official_rate']}%{'':<10} {cov['media_rate']}%{'':<8} {cov['weak_source_count']}")
    lines.append("")

    # Expected flags
    if report["expected_flags"]:
        lines.append("## Expected Source Gaps")
        lines.append("")
        for ef in report["expected_flags"]:
            lines.append(f"- **{ef['brand']}** — {ef['flag']}: {ef['detail']}")
        lines.append("")

    # Low quality
    if report["low_quality"]:
        lines.append("## Low Quality Facts")
        lines.append("")
        for lq in report["low_quality"][:10]:
            flags = ", ".join(lq["flags"])
            lines.append(f"- fact_id={lq['fact_id']} **{lq['brand']}** — {lq['title']}  (`{flags}`)")
        if report["low_quality_count"] > 10:
            lines.append(f"- ... 还有 {report['low_quality_count'] - 10} 条")
        lines.append("")

    # Suggestions
    if report["suggestions"]:
        lines.append("## Suggestions")
        lines.append("")
        for s in report["suggestions"]:
            lines.append(f"- {s}")
        lines.append("")

    return "\n".join(lines)
