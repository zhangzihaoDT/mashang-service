#!/usr/bin/env python3
"""
Auto Launch AI Response Validator — 验证 AI 返回结果是否符合 evidence schema 和输出结构要求。

用法:
  python mashang_workspace/promptbuilders/auto_launch/examples/validate_ai_response.py \
    --case-name sample_response \
    --raw-file mashang_workspace/promptbuilders/auto_launch/examples/fixtures/sample_response.synthetic.raw.md \
    --prompt-file mashang_workspace/outputs/auto_launch/prompts/examples/byd_datang_ev_launch_7d_vs_ls8.md \
    --output mashang_workspace/outputs/auto_launch/ai_response_examples/sample_response.validation.json
"""

import json, re, sys, argparse
from pathlib import Path
from collections.abc import Mapping


# Evidence field aliases — tolerant matching for real AI responses
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
        "energy_type", "power_type", "drivetrain_type", "fuel_type",
        "powertrain",
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
    """Get a value from nested dict using dot notation, returns None if not found."""
    parts = path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            return None
    return current


def _check_alias(obj: dict, expected_path: str, aliases: list[str]) -> tuple[bool, str]:
    """Check if any alias path exists in obj, return (found, matched_path)."""
    for alias in aliases:
        val = _deep_get(obj, alias)
        if val is not None and val != "" and val != []:
            return True, alias
    return False, ""


def load_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        print(f"[ERROR] 文件不存在: {p}", file=sys.stderr)
        sys.exit(1)

    encodings = ["utf-8", "utf-8-sig", "utf-16", "gb18030"]
    last_error = None
    used_encoding = None

    for enc in encodings:
        try:
            text = p.read_text(encoding=enc)
            used_encoding = enc
            break
        except (UnicodeDecodeError, LookupError) as e:
            last_error = e
            continue

    if used_encoding is None:
        print(f"[ERROR] 无法解码文件: {p}", file=sys.stderr)
        print(f"  尝试过的编码: {', '.join(encodings)}", file=sys.stderr)
        print(f"  最后错误: {last_error}", file=sys.stderr)
        print(f"  建议: 将文件保存为 UTF-8 编码后重试", file=sys.stderr)
        sys.exit(1)

    if used_encoding != "utf-8":
        print(f"[WARN] 文件编码为 {used_encoding}，非 UTF-8，建议保存为 UTF-8 格式。", file=sys.stderr)

    return text


def extract_json_blocks(text: str) -> list[dict]:
    blocks = []
    for m in re.finditer(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
            blocks.append(data)
        except json.JSONDecodeError:
            continue
    return blocks


def check_field(obj: dict, path: str, field_name: str) -> tuple[str, bool, str]:
    parts = path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list):
            try:
                idx = int(part)
                current = current[idx]
            except (ValueError, IndexError):
                return field_name, False, f"字段 '{path}' 不存在或不可访问"
        else:
            return field_name, False, f"字段 '{path}' 不存在"
    exists = current is not None and current != "" and current != []
    status = "✅" if exists else "❌"
    val_preview = str(current)[:80] if exists else ""
    return field_name, exists, f"{status} {field_name}: {val_preview}" if exists else f"{status} {field_name}: 缺失"


def parse_roles_from_prompt(prompt_text: str) -> dict:
    """Parse event_model, our_model, and expected_competitors from prompt text."""
    result = {
        "event_brand": "",
        "event_model": "",
        "our_brand": "",
        "our_model": "",
        "expected_competitors": [],
    }

    for line in prompt_text.split("\n"):
        ls = line.strip()
        # Parse business input table (| key | value |)
        if ls.startswith("|") and "|" in ls[1:]:
            parts = [p.strip() for p in ls.split("|") if p.strip()]
            if len(parts) >= 2:
                key, val = parts[0], parts[1]
                if key == "事件车型品牌":
                    result["event_brand"] = val
                elif key == "事件车型" and "品牌" not in key and "event_model" not in key:
                    result["event_model"] = val
                elif key == "本品品牌":
                    result["our_brand"] = val
                elif key == "本品车型":
                    result["our_model"] = val

    # Parse expected_competitors from competitor_detail table (pipe table in prompt)
    # Format: | # | 品牌 | 车型 | ... |
    in_competitor_table = False
    for line in prompt_text.split("\n"):
        ls = line.strip()
        if ls.startswith("| # | 品牌 |"):
            in_competitor_table = True
            continue
        if in_competitor_table:
            if not ls.startswith("|"):
                in_competitor_table = False
                continue
            # Skip table separators (---, :---:, ------)
            if "---" in ls or "::" in ls:
                continue
            parts = [p.strip() for p in ls.split("|") if p.strip()]
            if len(parts) >= 3:
                val = parts[2]
                # Skip header-like entries that match table headers
                if val.lower() in ("车型", "model", "display_name", "competitor"):
                    continue
                result["expected_competitors"].append(val)

    return result


def validate_response(raw_text: str, prompt_text: str, case_name: str) -> dict:
    """Run all validation checks and return results."""
    checks = []
    errors = []
    warnings = []
    all_pass = True

    def _check(pass_cond: bool, name: str, detail: str = ""):
        nonlocal all_pass
        if not pass_cond:
            all_pass = False
        checks.append({"check": name, "passed": pass_cond, "detail": detail})
        return pass_cond

    # ── 0. Parse roles from prompt ────────────────────────────────
    roles = parse_roles_from_prompt(prompt_text)
    event_brand = roles["event_brand"]
    event_model_name = roles["event_model"]
    our_brand = roles["our_brand"]
    our_model_name = roles["our_model"]
    expected_competitors = roles["expected_competitors"]

    detected_event_model = f"{event_brand} {event_model_name}".strip()
    has_our_model = bool(our_brand and our_model_name) and our_brand != "（未指定）" and our_model_name != "（未指定）"
    detected_our_model = f"{our_brand} {our_model_name}".strip() if has_our_model else ""
    is_impact = "对我方车型影响判断" in prompt_text

    # Build role model patterns for exclusion
    role_patterns = []
    if event_brand:
        role_patterns.append(event_brand)
    if event_model_name:
        role_patterns.append(event_model_name)
    if has_our_model:
        if our_brand:
            role_patterns.append(our_brand)
        if our_model_name:
            role_patterns.append(our_model_name)

    def _is_role_model(name: str) -> bool:
        name_lower = name.lower()
        for rp in role_patterns:
            if rp.lower() in name_lower:
                return True
        return False

    def _is_event_model(name: str) -> bool:
        name_lower = name.lower()
        if event_brand and event_brand.lower() in name_lower:
            return True
        if event_model_name and event_model_name.lower() in name_lower:
            return True
        return False

    def _is_our_model(name: str) -> bool:
        if not has_our_model:
            return False
        name_lower = name.lower()
        if our_brand and our_brand.lower() in name_lower:
            return True
        if our_model_name and our_model_name.lower() in name_lower:
            return True
        return False

    excluded_role_models = []
    if detected_event_model:
        excluded_role_models.append(f"event_model: {detected_event_model}")
    if detected_our_model:
        excluded_role_models.append(f"our_model: {detected_our_model}")

    # ── 1. JSON block extraction ──────────────────────────────────
    json_blocks = extract_json_blocks(raw_text)
    _check(len(json_blocks) > 0, "包含 JSON 区块", f"找到 {len(json_blocks)} 个 JSON 块")
    if not json_blocks:
        errors.append("未找到 JSON 区块")

    # ── 2. Markdown section check (required sections coverage) ────
    required_sections = ["事件概要", "价格与权益", "产品核心", "竞品对比", "舆论热度", "对我方影响"]
    markdown_sections_detected = []
    for sec in required_sections:
        # Match ## N. 标题 or ## 标题
        pattern = r"##\s+\d*\.?\s*" + re.escape(sec)
        if re.search(pattern, raw_text):
            markdown_sections_detected.append(sec)
    md_coverage = len(markdown_sections_detected)
    _check(md_coverage >= 3, f"包含 Markdown 简报区块（{md_coverage}/{len(required_sections)} 章节）",
           f"检测到: {', '.join(markdown_sections_detected)}")

    # ── 3a. Text presence check: evidence / source_url / publish_time / confidence ──
    text_presence_check = {
        "evidence_or_证据": "evidence" in raw_text.lower() or "证据" in raw_text,
        "source_url_or_https": "source_url" in raw_text or "sourceUrl" in raw_text or "https://" in raw_text,
        "publish_or_日期": "publish" in raw_text.lower() or "published" in raw_text.lower() or "日期" in raw_text,
        "confidence_or_可信": "confidence" in raw_text.lower() or "可信" in raw_text or "置信度" in raw_text,
        "unknown_or_无法确认": "unknown" in raw_text.lower() or "无法确认" in raw_text or "unconfirmed" in raw_text.lower() or "待验证" in raw_text,
    }
    for check_name, passed in text_presence_check.items():
        _check(passed, f"text presence: {check_name}")

    # ── 3b. JSON field check: structured evidence fields ──────────
    json_field_check = {
        "evidence_trail": False,
        "source_url_in_structure": False,
        "publish_time_in_structure": False,
        "confidence_in_structure": False,
        "unconfirmed_claims": False,
    }
    if json_blocks:
        main_block = json_blocks[0]
        json_field_check["evidence_trail"] = "evidence_trail" in main_block
        # Check for source_url in event_confirmation or evidence_trail
        json_field_check["source_url_in_structure"] = bool(
            main_block.get("event_confirmation", {}).get("official_announcement_url") or
            main_block.get("evidence_trail", {}).get("sources_used")
        )
        json_field_check["publish_time_in_structure"] = "publish_date" in str(main_block) or "published_at" in str(main_block) or "event_date" in str(main_block)
        json_field_check["confidence_in_structure"] = "confidence" in str(main_block) or "confirmation_confidence" in str(main_block)
        json_field_check["unconfirmed_claims"] = "unconfirmed_claims" in main_block.get("evidence_trail", {})
    for check_name, passed in json_field_check.items():
        _check(passed, f"json field: {check_name}")

    # ── 5. Event model mention ────────────────────────────────────
    _check(bool(event_brand and event_model_name), "提及 event_model", f"检测到: {detected_event_model}")

    # ── 6. Our model mention (if applicable) ──────────────────────
    if is_impact:
        _check(has_our_model, "impact case: 提及 our_model", f"our_model={detected_our_model}")
        if has_our_model:
            our_in_response = our_brand in raw_text or our_model_name in raw_text
            _check(our_in_response, "impact case: our_model 出现在 AI 响应中",
                   f"{'✅ 找到' if our_in_response else '❌ 未找到'} {our_brand} / {our_model_name}")
    else:
        _check(True, "general case: our_model 可选", "non-impact 模式")

    # ── 7. Competitor detection (with role exclusion) ─────────────
    raw_competitors = []
    for blk in json_blocks:
        ca = blk.get("competitive_analysis", {})
        comps = ca.get("competitors", [])
        for c in comps:
            name = c.get("competitor_name", "")
            model = c.get("competitor_model", "")
            combined = f"{name} {model}".strip()
            if combined:
                raw_competitors.append(combined)
    if not raw_competitors:
        for line in raw_text.split("\n"):
            m = re.search(r'"competitor_name"\s*:\s*"([^"]+)"', line)
            if m:
                raw_competitors.append(m.group(1))

    # Exclude event_model and our_model from competitors
    detected_competitors = [c for c in raw_competitors if not _is_role_model(c)]
    excluded_count = len(raw_competitors) - len(detected_competitors)

    _check(len(detected_competitors) >= 1, "提及至少 1 个 competitor_context 车型（非 role model）",
           f"检测到: {', '.join(detected_competitors[:5])}" if detected_competitors else "")

    # Impact case: our_model must NOT be in competitors
    if is_impact and has_our_model:
        our_in_competitors = any(_is_our_model(c) for c in raw_competitors)
        _check(not our_in_competitors, "impact case: our_model 未出现在 detected_competitors 中",
               f"{'✅ 正确排除' if not our_in_competitors else '❌ our_model 出现在竞品中'}")

    # Event model must NOT be in competitors
    event_in_competitors = any(_is_event_model(c) for c in raw_competitors)
    _check(not event_in_competitors, "event_model 未出现在 detected_competitors 中",
           f"{'✅ 正确排除' if not event_in_competitors else '❌ event_model 出现在竞品中'}")

    # Role detection status
    role_issues = []
    if is_impact and not has_our_model:
        role_issues.append("impact case 缺少 our_model")
    if not event_brand:
        role_issues.append("未检测到 event_brand")
    if not event_model_name:
        role_issues.append("未检测到 event_model")
    role_detection_status = "passed" if not role_issues else "failed"

    # ── 8. Impact assessment dimensions ───────────────────────────
    impact_dims = ["价格", "空间", "续航", "补能", "智驾", "品牌", "用户心智", "销售权益"]
    found_dims = [dim for dim in impact_dims if dim in raw_text]
    _check(len(found_dims) >= 3, "至少覆盖 3 个影响判断维度",
           f"覆盖 {len(found_dims)}/{len(impact_dims)}: {', '.join(found_dims)}")

    # ── 9. Evidence field coverage (strict + tolerant) ──────────
    ev_fields_to_check = [
        ("event_confirmation.event_name", "事件名称"),
        ("event_confirmation.event_date_confirmed", "确认日期"),
        ("pricing_and_权益.price.starting_price", "起售价"),
        ("pricing_and_权益.权益", "权益列表"),
        ("product_positioning.vehicle_level", "车型级别"),
        ("product_positioning.energy_type", "能源类型"),
        ("product_positioning.core_selling_points", "核心卖点"),
        ("competitive_analysis.competitors", "竞品对比"),
        ("media_and_user_feedback.media_coverage", "媒体覆盖"),
        ("impact_assessment.threat_level", "威胁等级"),
        ("evidence_trail.sources_used", "证据来源"),
    ]

    evidence_field_coverage = {}
    alias_matched_fields = []
    missing_json_paths = []
    possible_alias_matches = {}
    strict_schema_passed = True
    tolerant_schema_passed = True

    if json_blocks:
        main_block = json_blocks[0]

        # Detect top-level keys for gap analysis
        detected_top_level_keys = list(main_block.keys())
        detected_nested_key_candidates = {}
        for k, v in main_block.items():
            if isinstance(v, dict):
                detected_nested_key_candidates[k] = list(v.keys())
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                detected_nested_key_candidates[k] = [type(v).__name__, f"{len(v)} items"]

        for field_path, display_name in ev_fields_to_check:
            # Strict check
            name, strict_ok, detail = check_field(main_block, field_path, display_name)
            evidence_field_coverage[field_path] = strict_ok
            _check(strict_ok, f"evidence 字段: {display_name}", detail)
            if not strict_ok:
                strict_schema_passed = False
                missing_json_paths.append(field_path)

                # Tolerant alias check
                aliases = EVIDENCE_ALIASES.get(field_path, [])
                alias_ok, matched = _check_alias(main_block, field_path, aliases)
                if alias_ok:
                    tolerant_schema_passed = False
                    alias_matched_fields.append({"expected": field_path, "matched": matched, "display": display_name})
                    possible_alias_matches[field_path] = matched
                    # Add a separate tolerant check entry
                    _check(True, f"evidence 字段(tolerant): {display_name} → 别名 {matched}")

        if not missing_json_paths:
            tolerant_schema_passed = True
    else:
        strict_schema_passed = False
        tolerant_schema_passed = False
        detected_top_level_keys = []
        detected_nested_key_candidates = {}
        for _, display_name in ev_fields_to_check:
            _check(False, f"evidence 字段: {display_name}", "无 JSON 区块可检查")

    # Schema gap summary
    schema_gap_summary = {
        "expected_json_paths": [p for p, _ in ev_fields_to_check],
        "missing_json_paths": missing_json_paths,
        "detected_top_level_keys": detected_top_level_keys,
        "detected_nested_key_candidates": detected_nested_key_candidates,
        "possible_alias_matches": possible_alias_matches,
    }

    # ── Validation status logic ─────────────────────────────────
    has_structure_failure = not json_blocks or md_coverage < 1 or not bool(event_brand)
    # Role failure: impact case but our_model missing in response
    role_failure = False
    if is_impact and has_our_model:
        our_in_response = our_brand in raw_text or our_model_name in raw_text
        if not our_in_response:
            role_failure = True

    if has_structure_failure:
        validation_status = "failed"
    elif not strict_schema_passed and tolerant_schema_passed:
        validation_status = "passed_with_schema_warnings"
    elif not strict_schema_passed and not tolerant_schema_passed:
        validation_status = "failed_with_warnings" if not errors else "failed"
    elif all_pass:
        validation_status = "passed"
    else:
        validation_status = "failed_with_warnings" if not errors else "failed"

    return {
        "case_name": case_name,
        "validation_status": validation_status,
        "all_checks_passed": all_pass,
        "strict_schema_passed": strict_schema_passed,
        "tolerant_schema_passed": tolerant_schema_passed,
        "schema_gap_summary": schema_gap_summary,
        "alias_matched_fields": alias_matched_fields,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "detected_event_model": detected_event_model,
        "detected_our_model": detected_our_model,
        "detected_competitors": detected_competitors,
        "expected_competitors": expected_competitors,
        "excluded_role_models": excluded_role_models,
        "role_detection_status": role_detection_status,
        "markdown_sections_detected": markdown_sections_detected,
        "text_presence_check": text_presence_check,
        "json_field_check": json_field_check,
        "evidence_field_coverage": evidence_field_coverage,
    }


def main():
    p = argparse.ArgumentParser(description="Auto Launch AI Response Validator")
    p.add_argument("--case-name", required=True, help="case 名称")
    p.add_argument("--raw-file", required=True, help="AI 返回的原始 markdown 文件路径")
    p.add_argument("--prompt-file", required=True, help="对应的 prompt 文件路径（用于提取期待值）")
    p.add_argument("--output", default=None, help="validation.json 输出路径")
    p.add_argument("--strict", action="store_true", help="严格模式：仅 passed 视为成功，passed_with_schema_warnings 视为失败")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    args = p.parse_args()

    raw_text = load_text(args.raw_file)
    prompt_text = load_text(args.prompt_file)

    result = validate_response(raw_text, prompt_text, args.case_name)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] Validation result: {out_path}")

    # Terminal output
    vs = result["validation_status"]
    if vs == "passed":
        status_icon = "✅"
    elif vs == "passed_with_schema_warnings":
        status_icon = "⚠️"
    else:
        status_icon = "❌"

    print(f"\n{'='*60}")
    print(f"  Validation Result: {status_icon} {vs}")
    print(f"{'='*60}")
    print(f"  Case: {result['case_name']}")
    print(f"  event_model: {result['detected_event_model']}")
    print(f"  our_model: {result['detected_our_model']}")
    print(f"  competitors: {', '.join(result['detected_competitors'][:5])}")
    print(f"  excluded_role_models: {', '.join(result['excluded_role_models'])}")
    print(f"  role_detection_status: {result['role_detection_status']}")
    print(f"  expected_competitors (from prompt): {', '.join(result['expected_competitors'][:5])}")
    print(f"  markdown_sections: {', '.join(result.get('markdown_sections_detected', []))}")
    print(f"  strict_schema: {'✅' if result.get('strict_schema_passed') else '❌'}  "
          f"tolerant_schema: {'✅' if result.get('tolerant_schema_passed') else '❌'}")

    # Schema gap details (always shown for non-passed)
    sg = result.get("schema_gap_summary", {})
    if sg.get("missing_json_paths"):
        print(f"  schema_gap: missing {len(sg['missing_json_paths'])} fields → {', '.join(sg['missing_json_paths'][:5])}")
        if len(sg['missing_json_paths']) > 5:
            print(f"    ... and {len(sg['missing_json_paths'])-5} more")
    if result.get("alias_matched_fields"):
        for a in result["alias_matched_fields"]:
            print(f"  alias match: {a['display']} → expected={a['expected']}, actual={a['matched']}")
    if sg.get("detected_top_level_keys"):
        print(f"  top-level keys ({len(sg['detected_top_level_keys'])}): {', '.join(sg['detected_top_level_keys'][:8])}")
    if sg.get("detected_nested_key_candidates"):
        for k, v in list(sg['detected_nested_key_candidates'].items())[:5]:
            nested_str = ", ".join(v[:4])
            print(f"  nested '{k}': {nested_str}")

    print(f"  Checks: {sum(1 for c in result['checks'] if c['passed'])}/{len(result['checks'])} passed")
    for c in result["checks"]:
        icon = "✅" if c["passed"] else "❌"
        print(f"    {icon} {c['check']}: {c['detail'][:80]}")
    if result.get("errors"):
        for e in result["errors"]:
            print(f"    ❌ ERROR: {e}")
    if result.get("warnings"):
        for w in result["warnings"]:
            print(f"    ⚠️  WARNING: {w}")

    if args.format == "json" and not args.output:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    # Exit policy: validation_status based
    if vs == "passed":
        sys.exit(0)
    elif vs == "passed_with_schema_warnings":
        sys.exit(0 if not args.strict else 1)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
