#!/usr/bin/env python3
"""
Auto Launch Report Packager — 将 raw.md / validation / normalized 打包为标准化报告目录。

报告产物优先级:
  1. report.raw.md —— 主报告（原样复制 AI 返回）
  2. executive_brief.md —— 一页摘要（不替代 raw.md）
  3. report.index.json —— 机器索引
  4. report.quality.json —— 质量检查

用法:
  python mashang_workspace/promptbuilders/auto_launch/examples/package_ai_report.py \
    --case-name byd_datang_ev_launch_7d_vs_ls8 \
    --raw-file mashang_workspace/outputs/auto_launch/ai_response_examples/byd_datang_ev_launch_7d_vs_ls8.raw.md \
    --validation-file mashang_workspace/outputs/auto_launch/ai_response_examples/byd_datang_ev_launch_7d_vs_ls8.validation.json \
    --normalized-file mashang_workspace/outputs/auto_launch/normalized/byd_datang_ev_launch_7d_vs_ls8.normalized_evidence.json \
    --output-dir mashang_workspace/outputs/auto_launch/reports/byd_datang_ev_launch_7d_vs_ls8
"""

import json, shutil, sys, argparse
from pathlib import Path


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
    print(f"[ERROR] 无法解码: {p}", file=sys.stderr)
    sys.exit(1)


def load_json(path: str) -> dict:
    return json.loads(load_text(path))


def main():
    p = argparse.ArgumentParser(description="Auto Launch Report Packager")
    p.add_argument("--case-name", required=True)
    p.add_argument("--raw-file", required=True)
    p.add_argument("--validation-file", required=True)
    p.add_argument("--normalized-file", required=True)
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    raw_text = load_text(args.raw_file)
    validation = load_json(args.validation_file)
    normalized = load_json(args.normalized_file)

    # ── 1. report.raw.md — original AI response ──
    raw_dest = out / "report.raw.md"
    raw_dest.write_text(raw_text, encoding="utf-8")
    print(f"[OK] {raw_dest} ({len(raw_text)} chars)")

    # ── 2. executive_brief.md — one-page summary ──
    em = normalized.get("event_model", {})
    om = normalized.get("our_model", {})
    impact = normalized.get("impact_assessment", {})
    pricing = normalized.get("pricing", {})
    sources = normalized.get("evidence_sources", [])
    unknowns = normalized.get("unknown_or_unconfirmed", [])
    competitors = normalized.get("competitor_context", [])
    sg = validation.get("schema_gap_summary", {})

    threat = impact.get("threat_level", "未知")
    source_count = len(sources)
    unknown_count = len(unknowns)
    has_our = bool(om) and om.get("brand") and om.get("model") and om.get("brand") != "（未指定）"

    brief = []
    brief.append(f"# {em.get('brand', '')} {em.get('model', '')} {'vs ' + om.get('brand', '') + ' ' + om.get('model', '') if has_our else ''}：一页摘要")
    brief.append("")
    brief.append("> 以下为基于 AI 原始报告的摘要，**不替代原始报告**。")
    brief.append("> 完整信息请查看 `report.raw.md`。")
    brief.append("")

    # Conclusion
    brief.append("## 结论")
    brief.append("")
    if threat and threat != "unknown":
        brief.append(f"AI 返回的威胁判断为 **{threat}**。")
    else:
        brief.append("原始报告中未明确给出威胁等级判断。")
    brief.append("（直接从 raw.md 引用，非重新推断）")
    brief.append("")

    # Core impact
    brief.append("## 核心影响")
    brief.append("")
    brief.append(f"- **价格锚点**: {pricing.get('starting_price', '原始报告中有描述')}")
    brief.append(f"- **产品形态**: {impact.get('product_overlap', impact.get('target_overlap', '原始报告中有描述'))}")
    brief.append(f"- **补能/续航**: 结构化抽取未覆盖，原始报告中可能已有相关描述，请以 report.raw.md 为准")
    brief.append(f"- **声量/订单**: 同上")
    if has_our:
        brief.append(f"- **{om.get('model', '本品')} 应对**: 原始报告中有 {source_count} 个信源支撑，具体判断见 report.raw.md")
    brief.append("")

    # Evidence risk
    brief.append("## 证据风险")
    brief.append("")
    vstatus = validation.get("validation_status", "unknown")
    brief.append(f"| 维度 | 状态 |")
    brief.append(f"|------|------|")
    brief.append(f"| validation_status | {vstatus} |")
    brief.append(f"| 来源数量 | {source_count} |")
    brief.append(f"| 待补充字段数 | {unknown_count} |")
    missing = sg.get("missing_json_paths", [])
    if missing:
        for mp in missing[:5]:
            brief.append(f"  - ⚠️ 结构化字段缺失: {mp}")
    if unknowns:
        for item in unknowns[:5]:
            brief.append(f"  - ⚠️ {str(item)[:80]}")
    brief.append("")
    brief.append("**建议**: 以上缺失仅代表结构化抽取未覆盖，原始报告中可能已有相关描述，请以 raw.md 为准。如需要完整结构化数据，建议人工补查。")
    brief.append("")

    brief_dest = out / "executive_brief.md"
    brief_dest.write_text("\n".join(brief), encoding="utf-8")
    print(f"[OK] {brief_dest} ({len(brief)} lines)")

    # ── 3. report.index.json — machine index ──
    index = {
        "case_name": args.case_name,
        "event_model": {"brand": em.get("brand", ""), "model": em.get("model", "")},
        "our_model": om if has_our else None,
        "event_date": normalized.get("event", {}).get("date", ""),
        "price_range": pricing.get("starting_price", ""),
        "threat_level": threat,
        "competitors": competitors,
        "sources_count": source_count,
        "unknown_count": unknown_count,
        "validation_status": vstatus,
    }
    idx_dest = out / "report.index.json"
    idx_dest.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] {idx_dest}")

    # ── 4. report.quality.json — quality check ──
    quality = {
        "case_name": args.case_name,
        "validation_status": vstatus,
        "schema_gap_summary": sg,
        "evidence_risk_level": validation.get("evidence_risk_level", "unknown"),
        "warnings": validation.get("warnings", []),
        "hard_fails": validation.get("hard_fail_rules", []),
        "source": "validate_ai_response.py + validate_battle_brief.py",
    }
    qual_dest = out / "report.quality.json"
    qual_dest.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] {qual_dest}")

    print(f"\n  Report package: {out}")
    print(f"  ├── report.raw.md (主报告)")
    print(f"  ├── executive_brief.md (摘要)")
    print(f"  ├── report.index.json (索引)")
    print(f"  └── report.quality.json (质量)")


if __name__ == "__main__":
    main()
