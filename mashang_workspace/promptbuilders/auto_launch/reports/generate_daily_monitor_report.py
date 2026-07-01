#!/usr/bin/env python3
"""
generate_daily_monitor_report.py — 从 Daily Monitor intake 输出生成日报 Report。

用法:
  python reports/generate_daily_monitor_report.py \\
      --input-dir path/to/daily_monitor \\
      --output-md path/to/daily_monitor_report.md \\
      --output-html path/to/daily_monitor_report.html

  如果省略 --output-md 和 --output-html，默认在 input-dir 下输出。

依赖: 无 (仅 Python 标准库)
"""

import json
import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path


# ── Reading ──────────────────────────────────────────────────────


def _load_json(path):
    """Load JSON, return None if missing or corrupt."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _load_txt(path):
    """Load text file, return '' if missing."""
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


# ── Conclusion builder ───────────────────────────────────────────


def _build_conclusions(normalized, candidates, needs_review, ds_count=0):
    """Build 3-5 short conclusions from data."""
    lines = []
    monitor_date = normalized.get("monitor_date", "unknown") if normalized else "unknown"
    ec = len(candidates) if candidates else 0
    nr = len(needs_review) if needs_review else 0

    lines.append(f"本轮（{monitor_date}）共发现 **{ec}** 条明确销售动作" +
                 (f"，**{ds_count}** 条弱信号" if ds_count > 0 else "") +
                 (f"，**{nr}** 条待复核。" if nr > 0 else "。"))

    if ec > 0:
        # Event type distribution
        from collections import Counter
        et_counts = Counter(c.get("event_type", "unknown") for c in candidates)
        top_types = et_counts.most_common(3)
        lines.append(f"销售动作主要集中在：{'、'.join(f'{et}（{c}）' for et, c in top_types)}。")

        # Impact pressure summary
        pressure_dims = {"price_pressure": "价格", "rights_pressure": "权益",
                         "configuration_pressure": "配置", "delivery_pressure": "交付"}
        high_dims = []
        for k, label in pressure_dims.items():
            highs = [c.get("event_model", "?") for c in candidates
                     if c.get("impact_vs_our_model", {}).get(k) == "high"]
            if highs:
                high_dims.append(f"{label}压力较高（{'、'.join(highs)}）")
        if high_dims:
            lines.append("对 LS8 的轻量压力方面：" + "；".join(high_dims) + "。")

        lines.append("建议人工复核 event_candidates，选择重要事件进入 impact_vs_our_model 深度分析。")
    else:
        lines.append("本轮可作为 no-event daily monitor pilot 留档。")

    return "\n".join(lines)


# ── Markdown render ──────────────────────────────────────────────


def render_md(input_dir, normalized, candidates, needs_review, no_event_models):
    """Render markdown report."""
    lines = []
    lines.append("# Auto Launch Daily Monitor Report\n")

    # 1. Summary table
    md = normalized or {}
    lines.append("## 1. Run Summary\n")
    lines.append("| 字段 | 值 |\n|---|---|\n")
    lines.append(f"| task_name | {md.get('task_name', 'unknown')} |\n")
    lines.append(f"| monitor_date | {md.get('monitor_date', 'unknown')} |\n")
    lines.append(f"| battle_field | {md.get('battle_field', 'unknown')} |\n")
    lines.append(f"| our_model | {md.get('our_model', 'unknown')} |\n")
    ec = len(candidates) if candidates else 0
    ds = len(md.get("discovery_signals", []))
    nr = len(needs_review) if needs_review else 0
    ne = len(no_event_models) if no_event_models else 0
    sa = len(md.get("search_audit", []))
    lines.append(f"| event_candidates_count | {ec} |\n")
    lines.append(f"| discovery_signals_count | {ds} |\n")
    lines.append(f"| needs_review_count | {nr} |\n")
    lines.append(f"| no_event_models_count | {ne} |\n")
    lines.append(f"| search_audit_count | {sa} |\n")
    # Window policy
    wp = md.get("window_policy", {})
    cew = wp.get("confirmed_event_window", {})
    dsw = wp.get("discovery_signal_window", {})
    cw = wp.get("context_window", {})
    if cew or dsw or cw:
        lines.append(f"| confirmed_event_window | {cew.get('primary_start','?')} ~ {cew.get('end','?')} |\n")
        lines.append(f"| discovery_signal_window | {dsw.get('default_start','?')} ~ {dsw.get('end','?')} |\n")
        lines.append(f"| context_window | {cw.get('start','?')} ~ {cw.get('end','?')} |\n")
    lines.append("\n")

    # 2. Event candidates
    lines.append("## 2. 今日明确销售动作\n\n")
    if candidates:
        lines.append("| 品牌 | 车型 | event_type | 事件名称 | 事件日期 | 可信度 | discovered | source_pub | window | review_flags | 价格压力 | 权益压力 | 配置压力 | 交付压力 |\n")
        lines.append("|------|------|-----------|----------|----------|--------|------------|------------|--------|--------------|----------|----------|----------|----------|\n")
        for c in candidates:
            imp = c.get("impact_vs_our_model", {})
            rfs = ",".join(c.get("review_flags", [])) if c.get("review_flags") else ""
            lines.append(f"| {c.get('event_brand','unknown')} | {c.get('event_model','unknown')} | {c.get('event_type','unknown')} | {c.get('event_name','unknown')} | {c.get('event_date','unknown')} | {c.get('confidence','unknown')} | {c.get('discovered_date','unknown')} | {c.get('source_publish_time','unknown')} | {c.get('window_match','unknown')} | {rfs or '[]'} | {imp.get('price_pressure','unknown')} | {imp.get('rights_pressure','unknown')} | {imp.get('configuration_pressure','unknown')} | {imp.get('delivery_pressure','unknown')} |\n")
    else:
        lines.append("None\n")
    lines.append("\n")

    # 3. Discovery Signals
    lines.append("## 3. 销售弱信号 Discovery Signals\n\n")
    if ds > 0:
        lines.append("| 品牌 | 车型 | signal_type | 线索名称 | possible_event_type | 可信度 | discovered | source_pub | window | review_flags | 未进入 candidate 原因 |\n")
        lines.append("|------|------|------------|----------|---------------------|--------|------------|------------|--------|--------------|---------------------|\n")
        for s in md.get("discovery_signals", []):
            rfs = ",".join(s.get("review_flags", [])) if s.get("review_flags") else ""
            lines.append(f"| {s.get('event_brand','')} | {s.get('event_model','')} | {s.get('signal_type','')} | {s.get('signal_name','')} | {s.get('possible_event_type','')} | {s.get('confidence','')} | {s.get('discovered_date','')} | {s.get('source_publish_time','')} | {s.get('window_match','')} | {rfs} | {s.get('why_not_candidate','')} |\n")
    else:
        lines.append("None\n")
    lines.append("\n")

    # 4. Event evidence (renumbered)
    lines.append("## 4. 事件证据 Source Evidence\n\n")
    if candidates:
        lines.append("| 车型 | source_tier | source_name | source_title | publish_time | source_url |\n")
        lines.append("|------|-------------|-------------|--------------|--------------|------------|\n")
        for c in candidates:
            for s in c.get("source_items", []):
                em = c.get("event_model", "?")
                lines.append(f"| {em} | {s.get('source_tier','')} | {s.get('source_name','')} | {s.get('source_title','')} | {s.get('publish_time','')} | {s.get('source_url','')} |\n")
    else:
        lines.append("None\n")
    lines.append("\n")

    # 5. Needs review (renumbered)
    lines.append("## 5. 待复核项目 Needs Review\n\n")
    if needs_review:
        lines.append("| 品牌 | 车型 | candidate_event_type | raw_event_name | reason | missing_evidence |\n")
        lines.append("|------|------|---------------------|----------------|--------|------------------|\n")
        for item in needs_review:
            lines.append(f"| {item.get('event_brand','')} | {item.get('event_model','')} | {item.get('candidate_event_type','')} | {item.get('raw_event_name','')} | {item.get('reason','')} | {item.get('missing_evidence','')} |\n")
    else:
        lines.append("None\n")
    lines.append("\n")

    # 6. No event models
    lines.append("## 6. 未发现动作车型 No Event Models\n\n")
    if no_event_models:
        for m in no_event_models:
            lines.append(f"- {m}\n")
    else:
        lines.append("None\n")
    lines.append("\n")

    # 7. Search Audit
    lines.append("## 7. 检索覆盖 Search Audit\n\n")
    if sa > 0:
        lines.append("| 车型 | 官方确认层 | 媒体交叉验证层 | 销售弱信号层 | confirmed_win | discovery_win | context_win | official | mainstream | industry | user_gen | unknown | coverage_note |\n")
        lines.append("|------|-----------|---------------|--------------|---------------|---------------|-------------|----------|------------|----------|----------|---------|---------------|\n")
        for a in md.get("search_audit", []):
            sl = a.get("searched_layers", {})
            sc = a.get("source_coverage", {})
            wc = a.get("window_coverage", {})
            lines.append(f"| {a.get('event_model','')} | {sl.get('official_confirmation','?')} | {sl.get('media_cross_check','?')} | {sl.get('sales_weak_signals','?')} | {wc.get('confirmed_event_window', 'unknown')} | {wc.get('discovery_signal_window', 'unknown')} | {wc.get('context_window', 'unknown')} | {sc.get('official',0)} | {sc.get('mainstream_media',0)} | {sc.get('industry_media',0)} | {sc.get('user_generated',0)} | {sc.get('unknown',0)} | {a.get('coverage_note','')} |\n")
    else:
        lines.append("None\n")
    lines.append("\n")

    # 8. Conclusions
    lines.append("## 8. 结论\n\n")
    lines.append(_build_conclusions(md, candidates, needs_review, ds))
    lines.append("\n\n")

    # 9. Next Step
    lines.append("## 9. Next Step\n\n")
    if ec > 0:
        lines.append("建议人工复核 event_candidates，选择重要事件进入 impact_vs_our_model。\n")
    elif ds > 0:
        lines.append("本轮无确认事件，但有发现销售动作线索，建议人工判断是否继续追踪。\n")
    else:
        lines.append("本轮可作为 no-event daily monitor pilot 留档。\n")
    lines.append("\n")

    # Metadata
    lines.append("## Report Metadata\n\n")
    lines.append("| 字段 | 值 |\n|---|---|\n")
    lines.append("| source_file | raw_ai_output.json |\n")
    lines.append("| render_mode | deterministic_raw_render |\n")
    lines.append(f"| raw_event_candidates_count | {ec} |\n")
    lines.append(f"| raw_discovery_signals_count | {ds} |\n")
    lines.append(f"| raw_needs_review_count | {nr} |\n")
    lines.append(f"| raw_no_event_models_count | {ne} |\n")
    lines.append(f"| raw_search_audit_count | {sa} |\n")

    return "".join(lines)


# ── HTML render ──────────────────────────────────────────────────


CSS = """
:root {
  --zh-blue: #174A7C;
  --zh-deep-blue: #06213D;
  --zh-cyan: #7ECDEB;
  --zh-raccoon-gold: #D79A36;
  --zh-cream: #FFF9EF;
  --zh-text: #1F2D3D;
  --zh-muted: #6B7280;
  --zh-border: #E5EAF0;
  --zh-bg: #FAFBFC;
  --zh-card: #FFFFFF;
  --zh-panel: #F6F8FA;
  --zh-row-alt: #FAFAFA;
}
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--zh-bg); color: var(--zh-text); max-width: 960px; margin: 0 auto; padding: 24px 16px; line-height: 1.6; }
h1 { color: var(--zh-blue); font-size: 24px; border-bottom: 2px solid var(--zh-cyan); padding-bottom: 8px; }
h2 { color: var(--zh-blue); font-size: 18px; margin-top: 28px; }
.summary-cards { display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0; }
.card { background: var(--zh-card); border: 1px solid var(--zh-border); border-radius: 8px; padding: 12px 18px; flex: 1; min-width: 120px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.card .num { font-size: 28px; font-weight: 700; color: var(--zh-blue); }
.card .label { font-size: 12px; color: var(--zh-muted); margin-top: 2px; }
.card.gold .num { color: var(--zh-raccoon-gold); }
table { width: 100%; border-collapse: collapse; background: var(--zh-card); border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.06); margin: 12px 0; }
th { background: var(--zh-panel); color: var(--zh-text); padding: 8px 10px; text-align: left; font-size: 13px; font-weight: 600; border-bottom: 2px solid var(--zh-border); }
td { padding: 7px 10px; font-size: 13px; border-bottom: 1px solid var(--zh-border); }
tr:nth-child(even) td { background: var(--zh-row-alt); }
.none { color: var(--zh-muted); font-style: italic; }
.conclusion { background: var(--zh-cream); border-left: 4px solid var(--zh-raccoon-gold); padding: 12px 16px; border-radius: 4px; margin: 12px 0; white-space: pre-wrap; }
"""


def _esc(text):
    """HTML-escape a string."""
    if not isinstance(text, str):
        text = str(text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_html(input_dir, normalized, candidates, needs_review, no_event_models):
    """Render HTML report."""
    md = normalized or {}
    ec = len(candidates) if candidates else 0
    nr = len(needs_review) if needs_review else 0
    ne = len(no_event_models) if no_event_models else 0

    parts = []
    parts.append(f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'><title>Daily Monitor Report</title><style>{CSS}</style></head><body>")
    parts.append(f"<h1>Auto Launch Daily Monitor Report</h1>")

    # Summary cards
    parts.append("<div class='summary-cards'>")
    parts.append(f"<div class='card'><div class='num'>{ec}</div><div class='label'>Event Candidates</div></div>")
    parts.append(f"<div class='card gold'><div class='num'>{len(md.get('discovery_signals', []))}</div><div class='label'>Discovery Signals</div></div>")
    parts.append(f"<div class='card'><div class='num'>{nr}</div><div class='label'>Needs Review</div></div>")
    parts.append(f"<div class='card'><div class='num'>{ne}</div><div class='label'>No Event Models</div></div>")
    parts.append("</div>")

    # Summary table
    parts.append("<h2>1. Run Summary</h2>")
    parts.append("<table>")
    for k, v in [("task_name", md.get("task_name")), ("monitor_date", md.get("monitor_date")),
                 ("battle_field", md.get("battle_field")), ("our_model", md.get("our_model"))]:
        parts.append(f"<tr><th>{_esc(k)}</th><td>{_esc(v or 'unknown')}</td></tr>")
    wp = md.get("window_policy", {})
    for k, win in [("confirmed_event_window", wp.get("confirmed_event_window", {})),
                    ("discovery_signal_window", wp.get("discovery_signal_window", {})),
                    ("context_window", wp.get("context_window", {}))]:
        start = win.get("primary_start") or win.get("default_start") or win.get("start", "")
        end = win.get("end", "")
        val = f"{_esc(start)} ~ {_esc(end)}" if start else ""
        if val:
            parts.append(f"<tr><th>{_esc(k)}</th><td>{val}</td></tr>")
    parts.append("</table>")

    # 2. Event candidates
    parts.append("<h2>2. 今日明确销售动作</h2>")
    if candidates:
        parts.append("<table><tr><th>品牌</th><th>车型</th><th>event_type</th><th>事件名称</th><th>日期</th><th>可信度</th><th>window</th><th>review</th><th>价格</th><th>权益</th><th>配置</th><th>交付</th></tr>")
        for c in candidates:
            imp = c.get("impact_vs_our_model", {})
            rfs = ",".join(c.get("review_flags", []))
            parts.append(f"<tr><td>{_esc(c.get('event_brand',''))}</td><td>{_esc(c.get('event_model',''))}</td><td>{_esc(c.get('event_type',''))}</td><td>{_esc(c.get('event_name',''))}</td><td>{_esc(c.get('event_date',''))}</td><td>{_esc(c.get('confidence',''))}</td><td>{_esc(c.get('window_match',''))}</td><td>{_esc(rfs)}</td><td>{_esc(imp.get('price_pressure',''))}</td><td>{_esc(imp.get('rights_pressure',''))}</td><td>{_esc(imp.get('configuration_pressure',''))}</td><td>{_esc(imp.get('delivery_pressure',''))}</td></tr>")
        parts.append("</table>")
    else:
        parts.append("<p class='none'>None</p>")

    # 3. Discovery Signals
    parts.append("<h2>3. 销售弱信号 Discovery Signals</h2>")
    ds_list = md.get("discovery_signals", [])
    if ds_list:
        parts.append("<table><tr><th>品牌</th><th>车型</th><th>signal_type</th><th>线索名称</th><th>possible_type</th><th>可信度</th><th>window</th><th>review</th><th>未进入原因</th></tr>")
        for s in ds_list:
            rfs = ",".join(s.get("review_flags", []))
            parts.append(f"<tr><td>{_esc(s.get('event_brand',''))}</td><td>{_esc(s.get('event_model',''))}</td><td>{_esc(s.get('signal_type',''))}</td><td>{_esc(s.get('signal_name',''))}</td><td>{_esc(s.get('possible_event_type',''))}</td><td>{_esc(s.get('confidence',''))}</td><td>{_esc(s.get('window_match',''))}</td><td>{_esc(rfs)}</td><td>{_esc(s.get('why_not_candidate',''))}</td></tr>")
        parts.append("</table>")
    else:
        parts.append("<p class='none'>None</p>")

    # 4. Evidence
    parts.append("<h2>4. 事件证据 Source Evidence</h2>")
    if candidates:
        parts.append("<table><tr><th>车型</th><th>source_tier</th><th>source_name</th><th>source_title</th><th>publish_time</th><th>source_url</th></tr>")
        for c in candidates:
            em = _esc(c.get("event_model", "?"))
            for s in c.get("source_items", []):
                url = _esc(s.get("source_url", ""))
                parts.append(f"<tr><td>{em}</td><td>{_esc(s.get('source_tier',''))}</td><td>{_esc(s.get('source_name',''))}</td><td>{_esc(s.get('source_title',''))}</td><td>{_esc(s.get('publish_time',''))}</td><td><a href='{url}'>{url[:50]}</a></td></tr>")
        parts.append("</table>")
    else:
        parts.append("<p class='none'>None</p>")

    # 5. Needs review
    parts.append("<h2>5. 待复核项目 Needs Review</h2>")
    if needs_review:
        parts.append("<table><tr><th>品牌</th><th>车型</th><th>类型</th><th>事件名称</th><th>原因</th><th>缺失证据</th></tr>")
        for item in needs_review:
            parts.append(f"<tr><td>{_esc(item.get('event_brand',''))}</td><td>{_esc(item.get('event_model',''))}</td><td>{_esc(item.get('candidate_event_type',''))}</td><td>{_esc(item.get('raw_event_name',''))}</td><td>{_esc(item.get('reason',''))}</td><td>{_esc(item.get('missing_evidence',''))}</td></tr>")
        parts.append("</table>")
    else:
        parts.append("<p class='none'>None</p>")

    # 6. No event models
    parts.append("<h2>6. 未发现动作车型 No Event Models</h2>")
    if no_event_models:
        parts.append("<ul>")
        for m in no_event_models:
            parts.append(f"<li>{_esc(m)}</li>")
        parts.append("</ul>")
    else:
        parts.append("<p class='none'>None</p>")

    # 7. Search Audit
    parts.append("<h2>7. 检索覆盖 Search Audit</h2>")
    sa_list = md.get("search_audit", [])
    if sa_list:
        parts.append("<table><tr><th>车型</th><th>官方确认</th><th>媒体验证</th><th>弱信号</th><th>conf_win</th><th>disc_win</th><th>ctx_win</th><th>official</th><th>mainstream</th><th>industry</th><th>user_gen</th><th>unknown</th><th>coverage_note</th></tr>")
        for a in sa_list:
            sl = a.get("searched_layers", {})
            sc = a.get("source_coverage", {})
            wc = a.get("window_coverage", {})
            parts.append(f"<tr><td>{_esc(a.get('event_model',''))}</td><td>{sl.get('official_confirmation','?')}</td><td>{sl.get('media_cross_check','?')}</td><td>{sl.get('sales_weak_signals','?')}</td><td>{wc.get('confirmed_event_window','?')}</td><td>{wc.get('discovery_signal_window','?')}</td><td>{wc.get('context_window','?')}</td><td>{sc.get('official',0)}</td><td>{sc.get('mainstream_media',0)}</td><td>{sc.get('industry_media',0)}</td><td>{sc.get('user_generated',0)}</td><td>{sc.get('unknown',0)}</td><td>{_esc(a.get('coverage_note',''))}</td></tr>")
        parts.append("</table>")
    else:
        parts.append("<p class='none'>None</p>")

    # 8. Conclusions
    parts.append("<h2>8. 结论</h2>")
    parts.append(f"<div class='conclusion'>{_build_conclusions(md, candidates, needs_review, len(ds_list))}</div>")

    # 9. Next Step
    parts.append("<h2>9. Next Step</h2>")
    if ec > 0:
        parts.append("<p>建议人工复核 event_candidates，选择重要事件进入 impact_vs_our_model。</p>")
    elif len(ds_list) > 0:
        parts.append("<p>本轮无确认事件，但有销售动作线索，建议人工判断是否继续追踪。</p>")
    else:
        parts.append("<p>本轮可作为 no-event daily monitor pilot 留档。</p>")

    parts.append("</body></html>")
    return "".join(parts)


# ── Main ─────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Generate Daily Monitor Report from intake outputs")
    parser.add_argument("--input-dir", "-i", required=True, help="Daily monitor intake output directory")
    parser.add_argument("--output-md", "-m", help="Output markdown path (default: input-dir/daily_monitor_report.md)")
    parser.add_argument("--output-html", "-l", help="Output HTML path (default: input-dir/daily_monitor_report.html)")
    args = parser.parse_args()

    input_dir = args.input_dir
    if not os.path.isdir(input_dir):
        print(f"[auto_launch report] ERROR: input dir not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    # Load primary data source: raw_ai_output.json (golden source)
    raw = _load_json(os.path.join(input_dir, "raw_ai_output.json"))
    # Fallback: normalized_daily_monitor.json
    data = raw or _load_json(os.path.join(input_dir, "normalized_daily_monitor.json"))

    if data is None:
        print(f"[auto_launch report] ERROR: neither raw_ai_output.json nor normalized_daily_monitor.json found in {input_dir}", file=sys.stderr)
        sys.exit(1)

    # All data MUST come from raw/normalized top-level arrays only.
    # Do NOT read from event_candidates.json / needs_review.json / etc. as they may be stale.
    candidates = data.get("event_candidates", [])
    needs_review = data.get("needs_review", [])
    no_event_models = data.get("no_event_models", [])

    # Consistency check
    ec, ds, nr, ne, sa = (len(data.get("event_candidates", [])),
                           len(data.get("discovery_signals", [])),
                           len(data.get("needs_review", [])),
                           len(data.get("no_event_models", [])),
                           len(data.get("search_audit", [])))
    expected = {"event_candidates": ec, "discovery_signals": ds,
                "needs_review": nr, "no_event_models": ne, "search_audit": sa}

    # Resolve output paths
    output_md = args.output_md or os.path.join(input_dir, "daily_monitor_report.md")
    output_html = args.output_html or os.path.join(input_dir, "daily_monitor_report.html")

    # Render
    md = render_md(input_dir, data, candidates, needs_review, no_event_models)
    html = render_html(input_dir, data, candidates, needs_review, no_event_models)

    # Write
    with open(output_md, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[auto_launch report] MD OK: {output_md}")

    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[auto_launch report] HTML OK: {output_html}")

    # Write report_manifest with consistency-verified counts
    manifest = {
        "report_type": "daily_monitor_report",
        "input_dir": os.path.abspath(input_dir),
        "source_file": "raw_ai_output.json" if raw else "normalized_daily_monitor.json",
        "outputs": {"markdown": os.path.abspath(output_md), "html": os.path.abspath(output_html)},
        "render_mode": "deterministic_raw_render",
        **expected,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = os.path.join(input_dir, "report_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"[auto_launch report] manifest OK: {manifest_path}")

    print(f"[auto_launch report] done")
    sys.exit(0)


if __name__ == "__main__":
    main()
