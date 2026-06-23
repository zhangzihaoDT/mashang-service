#!/usr/bin/env python3
"""
[EXPERIMENTAL] Auto Launch Battle Brief Writer — 基于 normalized_evidence.json 生成一页摘要。

⚠️ 不推荐作为主报告使用。原始 AI 返回 (raw.md) 才是主报告。
此脚本仅生成 machine-readable 结构化摘要，用于快速索引。
完整业务判断请以 report.raw.md 为准。

用法:
  python mashang_workspace/promptbuilders/auto_launch/examples/build_battle_brief.py \
    --normalized-file mashang_workspace/outputs/auto_launch/normalized/byd_datang_ev_launch_7d_vs_ls8.normalized_evidence.json \
    --output mashang_workspace/outputs/auto_launch/reports/byd_datang_ev_launch_7d_vs_ls8.executive_brief.md
"""

import json, sys, argparse
from pathlib import Path


THREAT_MAP = {
    "high": "高", "h": "高", "高": "高", "critical": "极高",
    "medium": "中", "m": "中", "中": "中",
    "low": "低", "l": "低", "低": "低",
}
CONFIDENCE_MAP = {"high": "高", "medium": "中", "low": "低"}
EVIDENCE_MAP = {True: "有", False: "无"}


def _norm(v):
    return str(v).strip().lower() if v else ""


def _threat_label(v):
    return THREAT_MAP.get(_norm(v), str(v))


def _confidence_label(v):
    return CONFIDENCE_MAP.get(_norm(v), str(v))


def load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        print(f"[ERROR] 文件不存在: {p}", file=sys.stderr)
        sys.exit(1)
    return json.loads(p.read_text(encoding="utf-8"))


def _has_evidence(val) -> bool:
    if val is None:
        return False
    s = str(val).strip().lower()
    return s not in ("", "unknown", "none", "null", "待补充")


def build_brief(normalized: dict) -> str:
    em = normalized.get("event_model", {})
    om = normalized.get("our_model", {})
    event = normalized.get("event", {})
    pricing = normalized.get("pricing", {})
    product = normalized.get("product", {})
    impact = normalized.get("impact_assessment", {})
    competitors = normalized.get("competitor_context", [])
    media = normalized.get("media_feedback", [])
    sources = normalized.get("evidence_sources", [])
    unknowns = normalized.get("unknown_or_unconfirmed", [])
    sg = normalized.get("schema_gap_summary", {})
    notes = normalized.get("normalization_notes", [])

    event_brand = em.get("brand", "")
    event_model = em.get("model", "")
    our_brand = om.get("brand", "") if om else ""
    our_model = om.get("model", "") if om else ""
    has_our = bool(our_brand and our_model) and our_brand != "（未指定）"

    # ── Derived assessments ──
    raw_threat = impact.get("threat_level", "unknown")
    threat_label = _threat_label(raw_threat)
    has_price_evidence = _has_evidence(pricing.get("starting_price"))
    has_product_evidence = _has_evidence(product.get("vehicle_level")) or bool(product.get("core_selling_points"))
    has_threat_evidence = _has_evidence(impact.get("price_pressure")) or _has_evidence(impact.get("space_pressure"))
    source_count = len(sources)
    unknown_count = len(unknowns)

    # Completeness
    if source_count >= 3 and unknown_count <= 3:
        evidence_completeness = "充分"
        confidence = "高"
    elif source_count >= 1 or unknown_count <= 5:
        evidence_completeness = "部分充分"
        confidence = "中"
    else:
        evidence_completeness = "不充分"
        confidence = "低"

    if source_count == 0:
        confidence = "低"
        evidence_completeness = "不充分（来源为 0）"
        # sources=0 时强制降级威胁等级——无来源支撑的威胁判断不可靠
        threat_label = "待评估（当前无可靠来源，需补充证据后重新判断）"

    if unknown_count > 5:
        if confidence != "低":
            confidence = "低"
        if "不充分" not in evidence_completeness:
            evidence_completeness += "（待补充信息较多）"

    # ── One sentence conclusion ──
    is_preliminary = source_count == 0 or unknown_count > 5
    prelim_tag = "【初步判断】" if is_preliminary else ""

    if has_our:
        if is_preliminary:
            one_liner = (
                f"{prelim_tag} {event_brand} {event_model} 以 {pricing.get('starting_price', '有竞争力')} 的定价"
                f"进入大型纯电 SUV 市场，但当前缺少可靠证据来源，威胁等级无法确认。"
                f"建议 {our_brand} 团队先补查 {event_brand} 的官方配置和定价信息，再评估对 {our_model} 的影响。"
            )
        elif threat_label in ("高", "极高"):
            one_liner = (
                f"{event_brand} {event_model} 以 {pricing.get('starting_price', '有竞争力')} 的定价"
                f"进入大型纯电 SUV 市场，对 {our_brand} {our_model} 构成明确价格锚点和用户心智压力。"
                f"当前判断置信度为 {confidence}，建议 {our_brand} 团队重点关注定价策略和差异化传播。"
            )
        elif threat_label == "中":
            one_liner = f"{event_brand} {event_model} 上市对 {our_brand} {our_model} 有一定影响，但暂不构成紧急威胁。"
        else:
            one_liner = f"{event_brand} {event_model} 上市对 {our_brand} {our_model} 影响有限。"
    else:
        one_liner = f"{event_brand} {event_model} 上市事件的市场信息已收集，本品未指定。"

    # ── Pricing pressure ──
    price_pressure = impact.get("price_pressure", "")
    space_pressure = impact.get("space_pressure", "")
    price_detail = f"起售价 {pricing.get('starting_price', '待确认')}"
    if has_our:
        price_detail += f"，直接覆盖 {our_model} 预期定价区间" if _has_evidence(pricing.get("starting_price")) else ""

    # ── Build report ──
    lines = []

    # Title
    if has_our:
        lines.append(f"# {event_brand} {event_model} 上市后对 {our_brand} {our_model} 的影响判断")
    else:
        lines.append(f"# {event_brand} {event_model} 上市事件简报")

    lines.append("")

    # ── 0. One-sentence conclusion ──
    lines.append("## 0. 一句话结论")
    lines.append("")
    lines.append(one_liner)
    lines.append("")

    # ── 1. Battle conclusion ──
    lines.append("## 1. 战情结论")
    lines.append("")
    lines.append(f"| 维度 | 判断 |")
    lines.append(f"|------|------|")
    lines.append(f"| 威胁等级 | **{threat_label}** |")
    lines.append(f"| 判断依据 | 价格压力({impact.get('price_pressure', '待评估')}) / 产品形态重叠({impact.get('product_overlap', impact.get('target_overlap', '待评估'))}) / 品牌声量 |")
    lines.append(f"| 证据完整度 | {evidence_completeness} |")
    lines.append(f"| 结论置信度 | {confidence} |")
    if source_count == 0:
        lines.append(f"| ⚠️ 证据链 | **来源为 0，当前结论应视为初步判断** |")
    if unknown_count > 5:
        lines.append(f"| ⚠️ 信息缺口 | **待补充信息 {unknown_count} 项，结论需谨慎** |")
    lines.append("")

    # ── 2. Confirmed facts ──
    lines.append("## 2. 已确认事实")
    lines.append("")
    facts = []
    if _has_evidence(event.get("date")):
        facts.append(f"- **事件日期**: {event['date']}（{event.get('confirmation_confidence', '')}）")
    if _has_evidence(pricing.get("starting_price")):
        facts.append(f"- **起售价**: {pricing['starting_price']}")
    sp = product.get("core_selling_points", [])
    if sp:
        lines.append(f"- **核心卖点**: {' / '.join(sp[:4])}")
    if _has_evidence(product.get("vehicle_level")):
        facts.append(f"- **车型级别**: {product['vehicle_level']}")
    if _has_evidence(product.get("energy_type")):
        facts.append(f"- **能源类型**: {product['energy_type']}")
    facts.append(f"- **竞品数量**: {len(competitors)} 个同战场车型")
    for f in facts:
        lines.append(f)
    if not facts:
        lines.append("（当前无已确认事实）")
    lines.append("")

    # ── 3. Specific pressure on our_model ──
    lines.append(f"## 3. 对 {our_model if has_our else '本品'} 的具体压力")
    lines.append("")

    # Price pressure
    lines.append("### 价格锚点压力")
    if has_price_evidence:
        lines.append(f"- **事实依据**: {price_detail}")
        lines.append(f"- **对 {our_model if has_our else '本品'} 的含义**: {event_brand} 的定价直接锚定该细分市场的价格区间，{our_model if has_our else '本品'}若定价高于此区间需给出明确差异化理由。")
    else:
        lines.append("- **事实依据**: 待补充证据（当前无价格数据）")
        lines.append(f"- **对 {our_model if has_our else '本品'} 的含义**: 待确认 {event_brand} 定价后才能评估。")
    lines.append("")

    # Space pressure
    lines.append("### 空间/座椅压力")
    vl = product.get("vehicle_level", "待补充证据")
    lines.append(f"- **事实依据**: {vl}")
    lines.append(f"- **对 {our_model if has_our else '本品'} 的含义**: 同级别产品在空间布局上形成直接竞争，{our_model if has_our else '本品'}需要在座椅布局或空间利用率上建立差异化。")
    lines.append("")

    # Range/charging pressure
    lines.append("### 续航/补能压力")
    range_val = impact.get("range_charging_pressure", "待补充证据")
    lines.append(f"- **事实依据**: {range_val}")
    lines.append(f"- **对 {our_model if has_our else '本品'} 的含义**: {'续航参数是同级别用户的核心决策因素之一，{event_brand} 若续航领先将形成明显优势。' if _has_evidence(range_val) else '当前无续航参数，需补查。'}")
    lines.append("")

    # Intelligence pressure
    lines.append("### 智驾/座舱压力")
    intel_val = impact.get("intelligence_pressure", "待补充证据")
    lines.append(f"- **事实依据**: {intel_val}")
    lines.append(f"- **对 {our_model if has_our else '本品'} 的含义**: 智能驾驶和座舱体验是当前新能源市场的核心竞争维度。")
    lines.append("")

    # Brand pressure
    lines.append("### 品牌与传播压力")
    brand_val = impact.get("brand_pressure", "待补充证据")
    lines.append(f"- **事实依据**: {brand_val}")
    lines.append(f"- **对 {our_model if has_our else '本品'} 的含义**: {event_brand} 的品牌声量和用户心智份额直接影响 {our_model if has_our else '本品'}的潜在客户转化。")
    lines.append("")

    # ── 4. Battlefield competitor context ──
    lines.append("## 4. 战场竞品背景")
    lines.append("")
    if competitors:
        lines.append(f"同战场（{sg.get('detected_top_level_keys', [''])[0] if sg.get('detected_top_level_keys') else '大型新能源 SUV'}）在监测车型：")
        lines.append("")
        for i, c in enumerate(competitors, 1):
            lines.append(f"{i}. {c}")
        lines.append("")
        lines.append("> 上述竞品为同战场背景信息，不构成本次事件的主体判断依据。")
    else:
        lines.append("（当前无同战场竞品数据）")
    lines.append("")

    # ── 5. Recommended actions ──
    lines.append("## 5. 建议动作")
    lines.append("")
    reco = impact.get("recommended_actions", [])

    actions = {
        "定价/权益": "需确认" + (f" {our_model}" if has_our else "") + "定价策略是否受" + event_brand + "价格锚点影响，评估是否需要调整权益方案。",
        "产品传播": "强化" + (f" {our_model}" if has_our else "本品") + "与" + event_brand + "的差异化卖点传播，避免正面参数对标。",
        "销售话术": "准备应对用户对比问询的标准话术，突出" + (f" {our_model}" if has_our else "本品") + "相对" + event_brand + "的独特优势。",
        "舆情监控": "持续监控" + event_brand + event_model + "上市后的媒体评价和用户反馈，重点关注价格和续航相关讨论。",
        "后续数据补充": "待补充续航参数、配置表、真实用户口碑等信息后重新评估威胁等级。" if unknown_count > 3 else "",
    }
    # Merge with AI-recommended actions
    if reco:
        for i, r in enumerate(reco[:5]):
            key = f"AI 建议 {i+1}"
            actions[key] = r if r else ""

    for area, action in actions.items():
        if action:
            lines.append(f"- **{area}**: {action}")
    lines.append("")

    # ── 6. Evidence risk & gaps ──
    lines.append("## 6. 证据风险与待补充信息")
    lines.append("")
    lines.append(f"| 维度 | 状态 |")
    lines.append(f"|------|------|")
    lines.append(f"| 来源数量 | {source_count} |")
    if source_count > 0:
        # Show first few source names
        source_names = [s.get("source_name", "unknown") for s in sources[:5] if isinstance(s, dict)]
        if source_names:
            unique_names = list(dict.fromkeys(n for n in source_names if n != "unknown"))
            if unique_names:
                lines.append(f"| 关键来源 | {', '.join(unique_names[:5])} |")
    else:
        lines.append(f"| ⚠️ 证据链 | **证据链不完整，当前结论应视为初步判断，不可用于最终业务决策** |")
    lines.append(f"| 待补充字段 | {unknown_count} |")
    missing = sg.get("missing_json_paths", [])
    if missing:
        for mp in missing[:5]:
            lines.append(f"  - 待补充: {mp}")
    if unknowns:
        lines.append(f"| 不确定项 | {len(unknowns)} |")
        for item in unknowns[:5]:
            lines.append(f"  - ⚠️ {str(item)[:80]}")
    lines.append("")

    # ── 7. Generation info (at the very end) ──
    lines.append("---")
    lines.append(f"*生成说明: 本报告由 build_battle_brief.py 基于 normalized_evidence.json 自动生成。")
    lines.append(f"不调用 LLM，不重新搜索。结论置信度受 evidence_sources 质量和数量影响。*")

    report = "\n".join(lines)
    # Replace bare "unknown" with business-friendly expression
    report = report.replace(" unknown", " 待补充证据")
    report = report.replace("（unknown）", "（待补充）")
    report = report.replace(": unknown", ": 待补充证据")
    # Clean bare English labels in judgment outputs
    report = report.replace("(high)", "")
    report = report.replace("(medium)", "")
    report = report.replace("(low)", "")
    report = report.replace("（high）", "")
    report = report.replace("（medium）", "")
    report = report.replace("（low）", "")
    return report


def main():
    p = argparse.ArgumentParser(description="Auto Launch Battle Brief Writer")
    p.add_argument("--normalized-file", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    normalized = load_json(args.normalized_file)
    report = build_brief(normalized)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"[OK] Battle brief: {out_path}")

    # Quick quality check
    issues = []
    if "unknown" in report:
        issues.append("报告中仍包含 'unknown' 字样")
    lines = report.split("\n")
    for i, line in enumerate(lines[:10]):
        if "normalize_ai_response" in line or "raw.md" in line or "validation_status" in line:
            issues.append(f"报告开头包含工程信息: {line.strip()[:40]}")
    if "一句话结论" not in report:
        issues.append("缺少'一句话结论'章节")
    if "证据风险与待补充信息" not in report:
        issues.append("缺少'证据风险与待补充信息'章节")
    action_count = report.count("**")
    if action_count < 8:
        issues.append(f"建议动作不足（检测到 {action_count//2} 个加粗标题，期望至少 4 条）")

    if issues:
        print("\n⚠️ 质量检查发现以下问题:")
        for iss in issues:
            print(f"  - {iss}")
    else:
        print("  ✅ 质量检查通过")

    print(f"\n  Lines: {len(lines)}")
    print(f"  Sections: {'/'.join(['一句话结论', '战情结论', '已确认事实', '具体压力', '战场竞品', '建议动作', '证据风险'])}")


if __name__ == "__main__":
    main()
