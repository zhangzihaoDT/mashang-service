#!/usr/bin/env python3
"""
Auto Launch Battle Brief Validator — 对 battle_brief.md 做报告质量验收。
基于 normalized_evidence.json 的硬性质量门槛。

用法:
  python mashang_workspace/promptbuilders/auto_launch/examples/validate_battle_brief.py \
    --brief-file mashang_workspace/outputs/auto_launch/reports/byd_datang_ev_launch_7d_vs_ls8.battle_brief.md \
    --normalized-file mashang_workspace/outputs/auto_launch/normalized/byd_datang_ev_launch_7d_vs_ls8.normalized_evidence.json \
    --output mashang_workspace/outputs/auto_launch/reports/byd_datang_ev_launch_7d_vs_ls8.brief_validation.json
"""

import json, sys, argparse
from pathlib import Path


BARE_LABELS = [" high", " medium", " low", "h>", "m>", "l>"]
ACTION_CATEGORIES = ["定价", "权益", "传播", "话术", "监控", "销售", "产品", "数据补充", "舆情"]


def load_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        print(f"[ERROR] 文件不存在: {p}", file=sys.stderr)
        sys.exit(1)
    for enc in ["utf-8", "utf-8-sig", "utf-16", "gb18030"]:
        try:
            return p.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    print(f"[ERROR] 无法解码文件: {p}", file=sys.stderr)
    sys.exit(1)


def load_json(path: str) -> dict:
    return json.loads(load_text(path))


def _val(obj, *keys):
    for k in keys:
        if isinstance(obj, dict):
            obj = obj.get(k, {})
        else:
            return None
    return obj if obj not in (None, "", "unknown", "none", {}, []) else None


def _str(obj, *keys, default=""):
    v = _val(obj, *keys)
    return str(v) if v is not None else default


def validate_brief(brief_text: str, normalized: dict) -> dict:
    checks = []
    hard_fails = []
    warnings = []

    def _check(name: str, passed: bool, detail: str = ""):
        checks.append({"check": name, "passed": passed, "detail": detail})

    # ── Extract data from normalized ──
    impact = normalized.get("impact_assessment", {})
    pricing = normalized.get("pricing", {})
    product = normalized.get("product", {})
    em = normalized.get("event_model", {})
    om = normalized.get("our_model", {})

    sources = normalized.get("evidence_sources", [])
    source_count = len(sources)
    unknowns = normalized.get("unknown_or_unconfirmed", [])
    unknown_count = len(unknowns)
    competitors = normalized.get("competitor_context", [])
    threat_raw = impact.get("threat_level", "")
    threat_str = str(threat_raw).strip().lower() if threat_raw else ""
    has_our = bool(om) and om.get("brand") and om.get("model") and om.get("brand") != "（未指定）"

    # ── 1. Section coverage (soft) ──
    section_checks = {
        "一句话结论": "一句话结论" in brief_text,
        "战情结论": "战情结论" in brief_text,
        "已确认事实": "已确认事实" in brief_text,
        "具体压力": "具体压力" in brief_text,
        "战场竞品": "战场竞品" in brief_text,
        "建议动作": "建议动作" in brief_text,
        "证据风险": "证据风险" in brief_text,
    }
    for name, ok in section_checks.items():
        _check(f"章节: {name}", ok)
    section_count = sum(section_checks.values())

    # ── 2. Hard Fail A: sources=0 + threat=高/高 → fail ──
    # Check threat from the report text (not normalized data), to account for builder downgrades
    sources_zero = source_count == 0
    report_threat_line = [l for l in brief_text.split("\n") if "威胁等级" in l]
    report_threat_raw = report_threat_line[0] if report_threat_line else ""
    # If report already downgraded threat (contains "待评估" or "无法确认"), skip this fail
    report_threat_downgraded = "待评估" in report_threat_raw or "无法确认" in report_threat_raw or "初步判断" in report_threat_raw
    threat_high = threat_str in ("high", "高", "h", "critical") and not report_threat_downgraded
    hard_a = sources_zero and threat_high
    if hard_a:
        hard_fails.append(f"A: sources_count=0 但 threat_level={threat_raw}（无证据来源时不能给强威胁结论）")

    # ── 3. Hard Fail B: sources=0 but no "证据链不完整" in report ──
    hard_b = sources_zero and "证据链不完整" not in brief_text
    if hard_b:
        hard_fails.append("B: sources_count=0 但报告未写'证据链不完整'")

    # ── 4. Hard Fail C: fact terms count = 0 ──
    fact_keywords = ["确认", "官方", "公布", "发布", "起售价", "续航", "电池", "上市日期", "来源"]
    fact_count = sum(1 for k in fact_keywords if k in brief_text)
    hard_c = fact_count == 0
    if hard_c:
        hard_fails.append("C: fact_terms_count=0（报告没有事实支撑）")

    # ── 5. Hard Fail D: engineering info in first 10 lines ──
    first_lines = "\n".join(brief_text.split("\n")[:10])
    eng_markers = ["normalize_ai_response", "raw.md", "validation_status", "validate_ai_response"]
    hard_d = any(m in first_lines for m in eng_markers)
    if hard_d:
        hard_fails.append("D: 报告开头包含工程信息")

    # ── 6. Hard Fail E: bare labels ──
    bare_label_count = 0
    for label in BARE_LABELS:
        bare_label_count += brief_text.count(label)
    if bare_label_count > 0:
        warnings.append(f"E: 报告中出现 {bare_label_count} 处裸标签（high/medium/low），应使用中文解释")

    # ── 7. Hard Fail F: unknown_count >= 5 but no confidence downgrade
    # Check if report mentions "初步判断" or "置信度.*低" or "谨慎"
    has_confidence_warning = any(m in brief_text for m in ["初步判断", "置信度为 低", "置信度.*低", "结论需谨慎", "信息缺口"])
    hard_f = unknown_count >= 5 and not has_confidence_warning
    if hard_f:
        hard_fails.append(f"F: unknown_items={unknown_count} >= 5 但报告没有提示初步判断或置信度降级")

    # ── 8. Evidence coverage (from normalized_evidence.json, not keyword match) ──
    has_price_info = bool(_val(pricing, "starting_price") or _val(pricing, "price_range"))
    has_threat_assessment = bool(_val(impact, "threat_level"))
    has_product_pressure = any(_val(product, d) for d in ["vehicle_level", "energy_type", "core_selling_points"])
    has_brand_context = bool(_val(impact, "brand_pressure"))
    has_evidence_sources = source_count > 0

    ev_from_data = {
        "price_info": has_price_info,
        "threat_assessment": has_threat_assessment,
        "product_pressure": has_product_pressure,
        "brand_context": has_brand_context,
        "evidence_sources": has_evidence_sources,
    }
    ev_count = sum(1 for v in ev_from_data.values() if v)
    _check(f"证据覆盖 ({ev_count}/5)", ev_count >= 3,
           f"price={has_price_info} threat={has_threat_assessment} product={has_product_pressure} brand={has_brand_context} sources={has_evidence_sources}")

    # ── 9. Judgment quality from data ──
    # Count how many judgments have actual evidence support
    judgment_fields = ["price_pressure", "space_pressure", "range_charging_pressure", "intelligence_pressure", "brand_pressure"]
    supported = sum(1 for f in judgment_fields if _val(impact, f) and _str(impact, f) not in ("unknown", "待补充证据", ""))
    unsupported = sum(1 for f in judgment_fields if not _val(impact, f) or _str(impact, f) in ("unknown", "待补充证据", ""))
    # If report says "待评估", it acknowledged the evidence gap — that's valid behavior
    conclusion_has_evidence = (has_threat_assessment or report_threat_downgraded) and (has_price_info or has_product_pressure)
    threat_has_evidence = (has_threat_assessment or report_threat_downgraded) and (has_price_info or has_product_pressure or has_evidence_sources)

    judgment_quality = {
        "fact_support_count": fact_count,
        "judgment_dimensions_total": len(judgment_fields),
        "supported_judgment_count": supported,
        "unsupported_judgment_count": unsupported,
        "conclusion_has_evidence_support": conclusion_has_evidence,
        "threat_level_has_evidence_support": threat_has_evidence,
    }
    _check("有证据支撑的判断维度比例", supported >= 1 or unsupported <= 3,
           f"{supported}/{len(judgment_fields)} 有证据支撑, {unsupported} 个待补充")

    # ── 10. Recommendation coverage ──
    reco_categories = [cat for cat in ACTION_CATEGORIES if cat in brief_text]
    reco_coverage = len(reco_categories)
    _check(f"建议动作覆盖 ({reco_coverage}/{len(ACTION_CATEGORIES)} 类)",
           reco_coverage >= 4, f"检测到: {', '.join(reco_categories)}")

    # ── 11. Our model mention ──
    if has_our:
        om_name = om.get("model", "")
        om_brand = om.get("brand", "")
        has_mention = (om_name in brief_text) or (om_brand in brief_text)
        _check(f"提及本品 {om_brand} {om_name}", has_mention)

    # ── Evidence risk level ──
    risk_score = 0
    if sources_zero:
        risk_score += 3
    if unknown_count >= 5:
        risk_score += 2
    if unsupported >= 3:
        risk_score += 1
    if risk_score >= 4:
        evidence_risk_level = "高"
    elif risk_score >= 2:
        evidence_risk_level = "中"
    else:
        evidence_risk_level = "低"

    # ── Final status ──
    any_hard_fail = len(hard_fails) > 0
    any_warning = len(warnings) > 0

    if any_hard_fail:
        validation_status = "failed"
    elif any_warning:
        validation_status = "passed_with_warnings"
    else:
        validation_status = "passed"

    final_quality_verdict = {
        "hard_fail_count": len(hard_fails),
        "warning_count": len(warnings),
        "section_coverage": f"{section_count}/{len(section_checks)}",
        "evidence_support_ratio": f"{supported}/{len(judgment_fields)}",
        "evidence_risk_level": evidence_risk_level,
        "recommendation_coverage": reco_coverage,
    }

    return {
        "validation_status": validation_status,
        "all_checks_passed": not any_hard_fail,
        "hard_fail_rules": hard_fails,
        "sources_count": source_count,
        "unknown_items_count": unknown_count,
        "fact_support_count": fact_count,
        "unsupported_judgment_count": unsupported,
        "recommendation_coverage": reco_coverage,
        "evidence_risk_level": evidence_risk_level,
        "final_quality_verdict": final_quality_verdict,
        "section_coverage": section_checks,
        "evidence_coverage_from_data": ev_from_data,
        "judgment_quality": judgment_quality,
        "warnings": warnings,
        "checks": checks,
    }


def main():
    p = argparse.ArgumentParser(description="Auto Launch Battle Brief Validator")
    p.add_argument("--brief-file", required=True)
    p.add_argument("--normalized-file", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    brief_text = load_text(args.brief_file)
    normalized = load_json(args.normalized_file)

    result = validate_brief(brief_text, normalized)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Brief validation: {out_path}")

    icon = {"passed": "✅", "passed_with_warnings": "⚠️", "failed": "❌"}
    vs = result["validation_status"]
    print(f"\n{'='*60}")
    print(f"  Brief Validation: {icon.get(vs, '?')} {vs}")
    print(f"{'='*60}")
    for hf in result["hard_fail_rules"]:
        print(f"  ❌ HARD FAIL: {hf}")
    for w in result.get("warnings", []):
        print(f"  ⚠️  {w}")
    fq = result.get("final_quality_verdict", {})
    print(f"  sections: {fq.get('section_coverage', '?')}")
    print(f"  evidence_support: {fq.get('evidence_support_ratio', '?')}")
    print(f"  evidence_risk_level: {fq.get('evidence_risk_level', '?')}")
    print(f"  recommendation_coverage: {fq.get('recommendation_coverage', 0)}/{len(ACTION_CATEGORIES)}")
    print(f"  sources: {result.get('sources_count', '?')}, unknown_items: {result.get('unknown_items_count', '?')}")

    sys.exit(0 if vs in ("passed", "passed_with_warnings") else 1)


if __name__ == "__main__":
    main()
