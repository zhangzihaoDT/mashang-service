#!/usr/bin/env python3
"""
Auto Launch AI Response Normalizer — 将 AI raw.md 转换为标准化证据 JSON 和可读战情简报。

用法:
  python mashang_workspace/promptbuilders/auto_launch/examples/normalize_ai_response.py \
    --case-name byd_datang_ev_launch_7d_vs_ls8 \
    --raw-file mashang_workspace/outputs/auto_launch/ai_response_examples/byd_datang_ev_launch_7d_vs_ls8.raw.md \
    --prompt-file mashang_workspace/outputs/auto_launch/prompts/examples/byd_datang_ev_launch_7d_vs_ls8.md \
    --validation-file mashang_workspace/outputs/auto_launch/ai_response_examples/byd_datang_ev_launch_7d_vs_ls8.validation.json \
    --normalized-output mashang_workspace/outputs/auto_launch/normalized/byd_datang_ev_launch_7d_vs_ls8.normalized_evidence.json \
    --report-output mashang_workspace/outputs/auto_launch/reports/byd_datang_ev_launch_7d_vs_ls8.battle_brief.md
"""

import json, re, sys, argparse
from pathlib import Path
from collections.abc import Mapping

# Reuse the same alias mappings from validate_ai_response.py
EVIDENCE_ALIASES = {
    "pricing_and_权益.price.starting_price": [
        "pricing.price.starting_price", "pricing.starting_price", "price.starting_price",
        "price_range", "starting_price", "pricing.price_range",
    ],
    "pricing_and_权益.权益": [
        "benefits", "sales_benefits", "launch_benefits", "purchase_benefits",
        "incentives", "promotions",
    ],
    "product_positioning.vehicle_level": [
        "vehicle_level", "segment", "vehicle_segment", "market_segment",
        "class", "vehicle_class",
    ],
    "product_positioning.energy_type": [
        "energy_type", "power_type", "drivetrain_type", "fuel_type", "powertrain",
    ],
    "competitive_analysis.competitors": [
        "competitor_context", "competitor_comparison", "competitor_analysis",
        "competitive_landscape", "competitors", "competition",
    ],
    "media_and_user_feedback.media_coverage": [
        "media_coverage", "media_feedback", "media_mentions", "press_coverage",
        "coverage", "media",
    ],
    "evidence_trail.sources_used": [
        "sources", "source_list", "references", "citations",
        "evidence_sources", "source_urls",
    ],
}


def _deep_get(obj, path: str):
    parts = path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            return None
    return current


def _alias_get(obj: dict, expected_path: str) -> tuple:
    """Try expected path first, then aliases. Returns (value, source_path)."""
    val = _deep_get(obj, expected_path)
    if val is not None and val != "" and val != []:
        return val, expected_path
    for alias in EVIDENCE_ALIASES.get(expected_path, []):
        val = _deep_get(obj, alias)
        if val is not None and val != "" and val != []:
            return val, alias
    return None, None


def extract_json_block(text: str) -> dict | None:
    for m in re.finditer(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL):
        raw = m.group(1).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            continue
    return None


def parse_prompt_roles(prompt_text: str) -> dict:
    result = {"event_brand": "", "event_model": "", "our_brand": "", "our_model": "", "expected_competitors": []}
    for line in prompt_text.split("\n"):
        ls = line.strip()
        if ls.startswith("|") and "|" in ls[1:]:
            parts = [p.strip() for p in ls.split("|") if p.strip()]
            if len(parts) >= 2:
                key, val = parts[0], parts[1]
                if key == "事件车型品牌":
                    result["event_brand"] = val
                elif key == "事件车型":
                    result["event_model"] = val
                elif key == "本品品牌":
                    result["our_brand"] = val
                elif key == "本品车型":
                    result["our_model"] = val
    # Parse expected competitors from table
    in_table = False
    for line in prompt_text.split("\n"):
        ls = line.strip()
        if ls.startswith("| # | 品牌 |"):
            in_table = True
            continue
        if in_table:
            if not ls.startswith("|"):
                break
            if "---" in ls or "::" in ls:
                continue
            parts = [p.strip() for p in ls.split("|") if p.strip()]
            if len(parts) >= 3 and parts[2].lower() not in ("车型", "model", "display_name"):
                result["expected_competitors"].append(parts[2])
    return result


def load_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        print(f"[ERROR] 文件不存在: {p}", file=sys.stderr)
        sys.exit(1)
    encodings = ["utf-8", "utf-8-sig", "utf-16", "gb18030"]
    for enc in encodings:
        try:
            return p.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    print(f"[ERROR] 无法解码文件: {p}", file=sys.stderr)
    sys.exit(1)


def load_json_file(path: str) -> dict:
    return json.loads(load_text(path))


def _is_role_model(name: str, role_patterns: list[str]) -> bool:
    nl = name.lower()
    for rp in role_patterns:
        if rp.lower() in nl:
            return True
    return False


def _extract_sources_from_json(obj, max_depth=5, _depth=0) -> list[dict]:
    """Recursively scan JSON for source/url fields and return structured list."""
    if _depth > max_depth or not isinstance(obj, (dict, list)):
        return []
    results = []
    seen_urls = set()
    if isinstance(obj, dict):
        has_url = False
        url_val = ""
        source_name = ""
        for k, v in obj.items():
            kl = k.lower()
            if kl == "url" and isinstance(v, str) and v.startswith("http"):
                has_url = True
                url_val = v
            if kl in ("source", "source_name", "media_name", "source_type") and isinstance(v, str):
                source_name = v
            results.extend(_extract_sources_from_json(v, max_depth, _depth + 1))
        if has_url and url_val not in seen_urls:
            seen_urls.add(url_val)
            results.append({
                "source_name": source_name or "unknown",
                "source_url": url_val,
                "source_type": "unknown",
                "publish_time": "",
                "confidence": "",
                "extraction_method": "json_recursive_scan",
            })
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_extract_sources_from_json(item, max_depth, _depth + 1))
    return results


def _extract_urls_from_markdown(text: str) -> list[str]:
    """Extract all http(s):// URLs from markdown text."""
    urls = re.findall(r'https?://[^\s\)\"\'<>\[\]]+', text)
    return list(dict.fromkeys(urls))  # dedup preserving order


def normalize(raw_file: str, prompt_file: str, validation_file: str, case_name: str) -> tuple[dict, str]:
    raw_text = load_text(raw_file)
    prompt_text = load_text(prompt_file)
    validation = load_json_file(validation_file)

    raw_json = extract_json_block(raw_text)
    sg = validation.get("schema_gap_summary", {})

    # Parse roles
    roles = parse_prompt_roles(prompt_text)
    event_brand = roles["event_brand"]
    event_model_name = roles["event_model"]
    our_brand = roles["our_brand"]
    our_model_name = roles["our_model"]
    expected_competitors = roles["expected_competitors"]
    has_our = bool(our_brand and our_model_name) and our_brand != "（未指定）"

    role_patterns = [event_brand, event_model_name]
    if has_our:
        role_patterns += [our_brand, our_model_name]
    role_patterns = [r for r in role_patterns if r]

    normalization_notes = []

    # ── Helper: get from raw with alias fallback ──
    def _get(path: str, default=None):
        if raw_json:
            val, src = _alias_get(raw_json, path)
            if val is not None:
                return val
        return default

    def _get_str(path: str, default="unknown"):
        val = _get(path)
        if val is None:
            return default
        if isinstance(val, list):
            return str(val[0]) if val else default
        return str(val)

    def _get_list(path: str, default=None):
        val = _get(path)
        if isinstance(val, list):
            return val
        if val is None:
            return default or []
        return [str(val)]

    # ── Build normalized evidence ──
    # Event info from raw JSON first, fallback to prompt
    ev_conf = (raw_json or {}).get("event_confirmation", {})
    event_name = ev_conf.get("event_name", "") or f"{event_brand} {event_model_name} 上市事件"
    event_date = ev_conf.get("event_date_confirmed", "") or validation.get("event_date", "")
    event_confidence = ev_conf.get("confirmation_confidence", "medium")

    pricing_section = (raw_json or {}).get("pricing_and_权益", {}) or {}
    pricing_price = pricing_section.get("price", {}) if isinstance(pricing_section.get("price"), dict) else {}
    starting_price = _get_str("pricing_and_权益.price.starting_price")
    if starting_price == "unknown":
        starting_price = _get_str("pricing_and_权益.price_range", "unknown")

    benefits_raw = pricing_section.get("权益", []) or _get_list("pricing_and_权益.权益")

    product_section = (raw_json or {}).get("product_positioning", {}) or {}
    selling_points = product_section.get("core_selling_points", []) or _get_list("product_positioning.core_selling_points")
    vehicle_level = _get_str("product_positioning.vehicle_level")
    energy_type = _get_str("product_positioning.energy_type")

    # Impact assessment
    impact = (raw_json or {}).get("impact_assessment", {}) or {}
    threat_level = impact.get("threat_level", "unknown")
    recommended = impact.get("recommended_action", "")
    if isinstance(recommended, str):
        recommended_list = [s.strip() for s in recommended.split("。") if s.strip()]
    elif isinstance(recommended, list):
        recommended_list = recommended
    else:
        recommended_list = []

    # Competitor context — exclude role models
    raw_competitors = []
    ca = (raw_json or {}).get("competitive_analysis", {}) or {}
    comps = ca.get("competitors", []) if isinstance(ca.get("competitors"), list) else _get_list("competitive_analysis.competitors")
    if comps and isinstance(comps[0], dict):
        for c in comps:
            name = f"{c.get('competitor_name', '')} {c.get('competitor_model', '')}".strip()
            if name:
                raw_competitors.append(name)
    elif comps:
        raw_competitors = [str(c) for c in comps]

    competitor_context = [c for c in raw_competitors if not _is_role_model(c, role_patterns)]
    if not competitor_context and expected_competitors:
        competitor_context = expected_competitors[:]
        normalization_notes.append(f"competitor_context_from=prompt_metadata (raw JSON 无 competitors)")

    # Media feedback
    media = []
    media_coverage = ca.get("media_coverage", []) if isinstance(ca.get("media_coverage"), list) else _get_list("media_and_user_feedback.media_coverage")
    if isinstance(media_coverage, list):
        for m in media_coverage[:5]:
            if isinstance(m, dict):
                media.append(m.get("article_title", m.get("key_quote", str(m)[:80])))
            else:
                media.append(str(m)[:80])

    # Evidence sources — recursive scan + markdown fallback
    json_sources = _extract_sources_from_json(raw_json) if raw_json else []
    markdown_urls = _extract_urls_from_markdown(raw_text)

    # Merge: prefer JSON sources (richer metadata), supplement with markdown URLs not already in JSON
    json_urls = {s["source_url"] for s in json_sources}
    for url in markdown_urls:
        if url not in json_urls:
            json_sources.append({
                "source_name": "unknown",
                "source_url": url,
                "source_type": "unknown",
                "publish_time": "",
                "confidence": "",
                "extraction_method": "markdown_url_regex",
            })
            json_urls.add(url)

    sources_used = [s["source_url"] for s in json_sources]

    if not sources_used:
        normalization_notes.append("raw_text 中未抽取到可结构化 source_url（JSON 无 evidence 字段，Markdown 无 https:// 链接）")

    et = (raw_json or {}).get("evidence_trail", {}) or {}
    unconfirmed = et.get("unconfirmed_claims", [])

    # Unknown/unconfirmed
    unknown_items = []
    if unconfirmed:
        unknown_items = list(unconfirmed) if isinstance(unconfirmed, list) else [str(unconfirmed)]
    for fp in sg.get("missing_json_paths", []):
        unknown_items.append(f"字段缺失: {fp}")

    schema_gap_summary = {
        "missing_json_paths": sg.get("missing_json_paths", []),
        "detected_top_level_keys": sg.get("detected_top_level_keys", []),
        "possible_alias_matches": sg.get("possible_alias_matches", {}),
    }

    # Track field sources
    field_sources = {}

    normalized = {
        "case_name": case_name,
        "schema_version": "auto_launch_normalized_evidence.v0.1",
        "event_model": {"brand": event_brand, "model": event_model_name},
        "our_model": {"brand": our_brand, "model": our_model_name} if has_our else None,
        "event": {
            "type": validation.get("event_type", ""),
            "date": event_date,
            "name": event_name,
            "confirmation_confidence": event_confidence,
        },
        "pricing": {
            "starting_price": starting_price,
            "price_range": _get_str("pricing_and_权益.price.price_range", "unknown"),
            "benefits": benefits_raw if isinstance(benefits_raw, list) else [str(benefits_raw)] if benefits_raw else [],
        },
        "product": {
            "vehicle_level": vehicle_level,
            "energy_type": energy_type,
            "core_selling_points": selling_points if isinstance(selling_points, list) else [],
        },
        "impact_assessment": {
            "threat_level": threat_level,
            "price_pressure": impact.get("price_overlap", "unknown"),
            "space_pressure": impact.get("product_overlap", "unknown") if "product_overlap" in impact else impact.get("target_overlap", "unknown"),
            "range_charging_pressure": "unknown",
            "intelligence_pressure": "unknown",
            "brand_pressure": "unknown",
            "overall_summary": "unknown",
            "recommended_actions": recommended_list,
        },
        "competitor_context": competitor_context,
        "media_feedback": media,
        "evidence_sources": json_sources,
        "unknown_or_unconfirmed": unknown_items,
        "schema_gap_summary": schema_gap_summary,
        "normalization_notes": normalization_notes,
    }

    # ── Build battle brief ──
    threat_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(str(threat_level).lower(), "⚪")

    brief_lines = [
        f"# {event_brand} {event_model_name} 上市后对{our_brand} {our_model_name}的影响简报" if has_our else f"# {event_brand} {event_model_name} 上市事件简报",
        "",
        "> 本报告由 normalize_ai_response.py 自动生成",
        f"> 原始 AI 返回: {raw_file}",
        f"> 验证结果: {validation.get('validation_status', 'unknown')}",
        "",
        "## 1. 结论摘要",
        f"- **威胁等级**: {threat_icon} {threat_level}",
        f"- **价格压力**: {impact.get('price_overlap', 'unknown')}",
        f"- **空间/产品重叠度**: {impact.get('product_overlap', impact.get('target_overlap', 'unknown'))}",
        f"- **核心压力来源**: 价格锚点{' + ' if starting_price != 'unknown' else ''}产品形态重叠" if starting_price != "unknown" or impact.get("product_overlap", "") else "待评估",
        "",
        "## 2. 事件事实",
        f"- **事件车型**: {event_brand} {event_model_name}",
        f"- **事件类型**: {validation.get('event_type', 'unknown')}",
        f"- **事件日期**: {event_date}",
        f"- **起售价**: {starting_price}",
        f"- **核心卖点**: {', '.join(selling_points[:3]) if selling_points else 'unknown'}",
        "",
        "## 3. 产品压力",
        f"- **空间/尺寸**: {vehicle_level}",
        f"- **续航/补能**: {energy_type}",
        f"- **智驾**: unknown（暂无数据）",
        f"- **品牌**: {event_brand}",
        "",
        "## 4. 对本品的影响",
    ]
    if has_our:
        brief_lines += [
            f"- **价格锚点**: {starting_price} 直接覆盖 {our_model_name} 预期定价区间" if starting_price != "unknown" else "- **价格锚点**: 未知",
            f"- **用户心智**: {event_brand} 品牌声量对 {our_model_name} 用户心智的影响",
            f"- **战场竞争**: {len(competitor_context)} 个同战场竞品",
            f"- **传播风险**: {event_brand} 上市传播可能抢占 {our_model_name} 关注度",
        ]
    else:
        brief_lines += [
            "- **本品未指定**: 当前无本品车型对照",
        ]

    brief_lines += [
        "",
        "## 5. 建议动作",
    ]
    if recommended_list:
        for action in recommended_list[:5]:
            brief_lines.append(f"- {action}")
    else:
        brief_lines += [
            "- 关注定价策略和权益调整",
            "- 加快差异化卖点传播",
        ]

    brief_lines += [
        "",
        "## 6. 证据与不确定项",
        f"- **来源数量**: {len(sources_used)}",
        f"- **不确定项**: {len(unknown_items)} 项",
    ]
    for item in unknown_items[:5]:
        brief_lines.append(f"  - ⚠️ {item}")
    if len(unknown_items) > 5:
        brief_lines.append(f"  - ... and {len(unknown_items)-5} more")

    brief_text = "\n".join(brief_lines)
    return normalized, brief_text


def main():
    p = argparse.ArgumentParser(description="Auto Launch AI Response Normalizer")
    p.add_argument("--case-name", required=True)
    p.add_argument("--raw-file", required=True)
    p.add_argument("--prompt-file", required=True)
    p.add_argument("--validation-file", required=True)
    p.add_argument("--normalized-output", required=True)
    p.add_argument("--report-output", required=True)
    args = p.parse_args()

    normalized, report = normalize(args.raw_file, args.prompt_file, args.validation_file, args.case_name)

    # Write normalized evidence
    neo = Path(args.normalized_output)
    neo.parent.mkdir(parents=True, exist_ok=True)
    neo.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Normalized evidence: {neo}")

    # Write battle brief
    bo = Path(args.report_output)
    bo.parent.mkdir(parents=True, exist_ok=True)
    bo.write_text(report, encoding="utf-8")
    print(f"[OK] Battle brief: {bo}")

    # Print summary
    print(f"\n  Summary:")
    print(f"    event: {normalized['event_model']['brand']} {normalized['event_model']['model']}")
    om = normalized.get("our_model")
    if om:
        print(f"    our:   {om['brand']} {om['model']}")
    print(f"    threat: {normalized['impact_assessment']['threat_level']}")
    print(f"    competitors ({len(normalized['competitor_context'])}): {', '.join(normalized['competitor_context'][:5])}")
    print(f"    unknown items: {len(normalized['unknown_or_unconfirmed'])}")
    print(f"    normalization_notes: {len(normalized['normalization_notes'])}")


if __name__ == "__main__":
    main()
