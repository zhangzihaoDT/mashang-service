#!/usr/bin/env python3
"""
Golden Prompt Cases 生成器 — 调用 promptbuilder.py 生成标准 Prompt 样例并校验。

用法:
  python mashang_workspace/promptbuilders/auto_launch/examples/generate_golden_cases.py
"""

import json, subprocess, sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[2]
PROMPTBUILDER = WORKSPACE_ROOT / "promptbuilders" / "auto_launch" / "promptbuilder.py"
OUTPUT_DIR = WORKSPACE_ROOT / "outputs" / "auto_launch" / "prompts" / "examples"
AUL_CONFIGS = MODULE_DIR.parent / "configs"

CASES = [
    {
        "case_name": "ledao_l80_launch_48h_vs_ls8",
        "case_type": "impact_vs_our_model",
        "core_question": "乐道 L80 上市后是否影响智己 LS8",
        "desc": "乐道 L80 上市 -> 对智己 LS8 的影响",
        "args": {
            "--event-brand": "乐道",
            "--event-model": "L80",
            "--our-brand": "智己",
            "--our-model": "LS8",
            "--event-type": "上市",
            "--event-date": "2026-06-25",
            "--window": "48h",
            "--targets-file": str(AUL_CONFIGS / "ls8_competitor_watchlist.csv"),
            "--target-profile-file": str(AUL_CONFIGS / "target_profiles.yaml"),
            "--battle-fields-file": str(AUL_CONFIGS / "battle_fields.yaml"),
            "--competitor-limit": "5",
            "--include-priority": "high",
        },
    },
    {
        "case_name": "wenjie_m7_launch_72h_vs_ls8",
        "case_type": "impact_vs_our_model",
        "core_question": "问界 M7 上市后是否影响智己 LS8",
        "desc": "问界 M7 上市 -> 对智己 LS8 的影响",
        "args": {
            "--event-brand": "问界",
            "--event-model": "M7",
            "--our-brand": "智己",
            "--our-model": "LS8",
            "--event-type": "上市",
            "--event-date": "2026-07-10",
            "--window": "72h",
            "--targets-file": str(AUL_CONFIGS / "ls8_competitor_watchlist.csv"),
            "--target-profile-file": str(AUL_CONFIGS / "target_profiles.yaml"),
            "--battle-fields-file": str(AUL_CONFIGS / "battle_fields.yaml"),
            "--competitor-limit": "5",
            "--include-priority": "high",
        },
    },
    {
        "case_name": "xiaomi_yu7_launch_72h_vs_competitors",
        "case_type": "general_event_intelligence",
        "core_question": "小米 YU7 上市事件情报检索（本品未指定，仅做市场信号收集）",
        "desc": "小米 YU7 上市 -> 全部竞品影响（manual 竞品，non-impact 情报）",
        "args": {
            "--event-brand": "小米",
            "--event-model": "YU7",
            "--event-type": "上市",
            "--event-date": "2026-07-10",
            "--window": "72h",
            "--competitors": "特斯拉Model Y,小鹏G6,理想L6,问界M5,智界R7",
        },
    },
    {
        "case_name": "byd_datang_ev_launch_7d_vs_ls8",
        "case_type": "impact_vs_our_model",
        "core_question": "比亚迪大唐EV上市后是否影响智己LS8",
        "desc": "比亚迪大唐EV 上市 -> 对智己 LS8 的影响",
        "args": {
            "--event-brand": "比亚迪",
            "--event-model": "大唐EV",
            "--our-brand": "智己",
            "--our-model": "LS8",
            "--event-type": "上市",
            "--event-date": "2026-06-17",
            "--window": "7d",
            "--targets-file": str(AUL_CONFIGS / "ls8_competitor_watchlist.csv"),
            "--target-profile-file": str(AUL_CONFIGS / "target_profiles.yaml"),
            "--battle-fields-file": str(AUL_CONFIGS / "battle_fields.yaml"),
            "--competitor-limit": "5",
            "--include-priority": "high",
        },
    },
]


def run_promptbuilder(case: dict) -> tuple[str, dict]:
    """Run promptbuilder.py and return (prompt_text, context_json)."""
    args = [sys.executable, str(PROMPTBUILDER), "--format", "json"]
    for k, v in case["args"].items():
        args.extend([k, v])
    r = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"promptbuilder 失败 (exit={r.returncode}): {r.stderr}")
    out = json.loads(r.stdout)
    return out["prompt"], out["context"]


def validate_prompt(case_name: str, prompt_text: str, context: dict, case_def: dict | None = None) -> dict:
    """Validate a generated prompt and return validation results."""
    errors = []
    warnings = []

    # No unresolved placeholders
    import re
    remaining = re.findall(r"\{\{.*?\}\}", prompt_text)
    if remaining:
        errors.append(f"未渲染占位符: {remaining}")

    # Must contain event brand and model
    eb = context.get("event_brand", "")
    em = context.get("event_model", "")
    ob = context.get("our_brand", "")
    om = context.get("our_model", "")
    if eb and eb not in prompt_text:
        warnings.append(f"Prompt 中未找到事件品牌 '{eb}'")
    if em and em not in prompt_text:
        warnings.append(f"Prompt 中未找到事件车型 '{em}'")
    if ob and ob not in prompt_text and ob != "（未指定）":
        warnings.append(f"Prompt 中未找到本品品牌 '{ob}'")
    if om and om not in prompt_text and om != "（未指定）":
        warnings.append(f"Prompt 中未找到本品车型 '{om}'")

    # Case type specific checks
    ct = (case_def or {}).get("case_type", "")
    if not ct:
        om_val = context.get("our_model", "")
        ct = "impact_vs_our_model" if om_val and om_val != "（未指定）" else "general_event_intelligence"

    if ct == "impact_vs_our_model":
        ob_val = context.get("our_brand", "")
        om_val = context.get("our_model", "")
        if not ob_val or ob_val == "（未指定）":
            errors.append("impact_vs_our_model 类型但 our_brand 为空")
        if not om_val or om_val == "（未指定）":
            errors.append("impact_vs_our_model 类型但 our_model 为空")
        # Must contain explicit impact statement referencing both
        if eb and em and ob_val and om_val and ob_val != "（未指定）":
            impact_phrase = f"{eb} {em}.*{ob_val} {om_val}"
            import re
            if not re.search(impact_phrase, prompt_text):
                warnings.append(f"impact_vs_our_model 类型但影响判断可能未同时引用 event_model({eb} {em}) 和 our_model({ob_val} {om_val})")

    # Must contain event type name
    et = context.get("event_type_name", "")
    if et and et not in prompt_text:
        warnings.append(f"Prompt 中未找到事件类型 '{et}'")

    # Must contain time window
    tw = context.get("time_window_desc", "")
    if tw and tw not in prompt_text:
        ws = context.get("time_window_start", "")
        we = context.get("time_window_end", "")
        if ws and we:
            win_str = f"{ws} 至 {we}"
            if win_str not in prompt_text:
                warnings.append(f"Prompt 中未找到时间窗口 '{tw}'")

    # Must contain at least 1 competitor
    comp = context.get("competitors", "")
    if not comp or comp in ("未指定", "未指定（需用户手动补充）"):
        errors.append("竞品列表为空")
    elif "未从 watchlist" in comp:
        warnings.append(f"竞品推导结果: {comp}")

    # Must contain evidence schema requirement
    if "evidence" not in prompt_text.lower() and "证据" not in prompt_text:
        warnings.append("Prompt 中可能缺少证据引用规则")

    # Must contain core modules (5 common + 1 conditional)
    module_keywords = ["事件确认", "价格与权益", "产品定位", "竞品对标", "媒体与用户反馈"]
    for mk in module_keywords:
        if mk not in prompt_text:
            warnings.append(f"Prompt 中未找到模块: {mk}")
    # Module 6 is conditional: 对我方车型影响 (impact) or 市场事件影响分析 (general)
    has_impact = "对我方车型影响判断" in prompt_text
    has_general = "市场事件影响分析" in prompt_text
    if ct == "impact_vs_our_model" and not has_impact:
        warnings.append("impact_vs_our_model 类型但未找到'对我方车型影响判断'模块")
    elif ct == "general_event_intelligence" and not has_general:
        warnings.append("general_event_intelligence 类型但未找到'市场事件影响分析'模块")
    elif not has_impact and not has_general:
        warnings.append("Prompt 中未找到模块6（对我方车型影响 / 市场事件影响分析）")

    validation_status = "passed" if not errors else "failed"
    return {
        "case_name": case_name,
        "validation_status": validation_status,
        "errors": errors,
        "warnings": warnings,
        "unresolved_placeholders_count": len(remaining),
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for case in CASES:
        cn = case["case_name"]
        print(f"\n{'='*60}")
        print(f"  Generating: {cn}")
        print(f"{'='*60}")

        try:
            prompt_text, context = run_promptbuilder(case)
        except Exception as e:
            print(f"  [ERROR] 生成失败: {e}")
            results.append({"case_name": cn, "validation_status": "error", "error": str(e)})
            continue

        # Write prompt
        md_path = OUTPUT_DIR / f"{cn}.md"
        md_path.write_text(prompt_text, encoding="utf-8")
        print(f"  [OK] Prompt: {md_path} ({len(prompt_text)} chars)")

        # Write metadata
        validation = validate_prompt(cn, prompt_text, context, case_def=case)
        metadata = {
            "case_name": cn,
            "case_type": case.get("case_type", "unknown"),
            "core_question": case.get("core_question", ""),
            "event_brand": context.get("event_brand", ""),
            "event_model": context.get("event_model", ""),
            "our_brand": context.get("our_brand", ""),
            "our_model": context.get("our_model", ""),
            "event_type": context.get("event_type_name", ""),
            "event_date": context.get("time_window_desc", ""),
            "time_window_start": context.get("time_window_start", ""),
            "time_window_end": context.get("time_window_end", ""),
            "window": case["args"].get("--window", ""),
            "competitor_source": context.get("competitor_source", ""),
            "competitor_match_field": context.get("competitor_match_field", ""),
            "competitors": context.get("competitors", ""),
            "target_group": context.get("target_group", ""),
            "target_group_source": context.get("target_group_source", ""),
            "same_battle_field_competitor_count": context.get("same_battle_field_competitor_count", ""),
            "supplemented_from_other_groups": context.get("supplemented_from_other_groups", ""),
            "**validation**": validation,
        }
        meta_path = OUTPUT_DIR / f"{cn}.metadata.json"
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [OK] Metadata: {meta_path}")

        # Summary
        v = validation
        status_icon = "✅" if v["validation_status"] == "passed" else "❌"
        print(f"  {status_icon} Validation: {v['validation_status']} "
              f"(unresolved={v['unresolved_placeholders_count']}, "
              f"errors={len(v['errors'])}, warnings={len(v['warnings'])})")

        results.append({
            "case_name": cn,
            "md_path": str(md_path),
            "meta_path": str(meta_path),
            "validation": v,
            "competitor_source": context.get("competitor_source", ""),
            "competitors": context.get("competitors", ""),
        })

    # Final summary
    print(f"\n\n{'='*60}")
    print(f"  Golden Prompt Cases — Summary")
    print(f"{'='*60}")
    all_passed = True
    for r in results:
        status = r["validation"]["validation_status"]
        icon = "✅" if status == "passed" else "❌"
        if status != "passed":
            all_passed = False
        print(f"  {icon} {r['case_name']}")
        print(f"      source={r['competitor_source']}, competitors={r['competitors'][:60]}")
        print(f"      {r['md_path']}")
    print(f"\n  All passed: {'✅ YES' if all_passed else '❌ NO'}")
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
