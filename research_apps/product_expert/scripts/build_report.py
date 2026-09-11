#!/usr/bin/env python3
"""Build the two-method report for a product_expert run.

The report separates two research methods over the same free text:

  A. Preset Question Coding   问题事先已知；LLM 只做编码；计数确定性聚合
  B. Open Discovery           问题事先未知；Evidence → Issue → Pattern → Convergence

A never uses LLM text generation: it renders preset_stats.json, which is derived
deterministically from preset_coding.json. B renders Pattern semantics and echoes
verbatim evidence quotes only. The script never re-derives statistics and never
synthesizes a quote, so the report cannot drift from, or out-talk, the record.

Outputs (default: reports/<run_id>/):
  product_expert_report.md
  product_expert_report.html
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]

DETAIL_LIMIT = 3
OBSERVATION_LIMIT = 3
QUOTE_LIMIT = 3
MODELS = ["LS6", "L6"]
OTHER_MODELS = ["LS8", "LS9", "OTHER"]

EVIDENCE_TYPE_LABEL = {
    "direct_quote": "用户/店长原话",
    "paraphrase": "专家转述",
    "expert_observation": "专家观察",
    "benchmark": "竞品对标",
}
SOURCE_FIELD_LABEL = {
    "l6_weakness": "L6 体验弱点",
    "ls6_weakness": "LS6 体验弱点",
    "test_drive_feedback": "试驾反馈",
    "ls8_ls9_suggestion": "LS8/LS9 建议或销售",
    "store_sales": "门店销售",
    "store_impression": "门店印象",
    "other": "其他",
}
RECURRENCE_LABEL = {
    "systemic": "Systemic（跨店跨时间）",
    "repeated": "Repeated（多店复现）",
    "isolated": "Isolated（单店孤立）",
}
STORE_OPS_CODE = ["footfall", "peak_hours", "leads", "test_drive", "lock_order", "walk_in"]
STORE_OPS_LABEL = {
    "footfall": "客流", "peak_hours": "高峰", "leads": "留资",
    "test_drive": "试驾", "lock_order": "锁单/交付", "walk_in": "自然客流",
}


def load_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def fmt_list(values, sep="、"):
    values = [v for v in values if v]
    return sep.join(values) if values else "—"


def fmt_md(iso_date: str) -> str:
    return f"{iso_date[5:7]}/{iso_date[8:10]}"


def window_from(periods: list[dict]) -> str:
    if not periods:
        return "—"
    return f"{fmt_md(min(p['start_date'] for p in periods))}–{fmt_md(max(p['end_date'] for p in periods))}"


def scope_from(run, convergences) -> dict:
    experts, stores = [], []
    periods = {}
    for c in convergences:
        for e in c["attribution"]["product_experts"]:
            if e not in experts:
                experts.append(e)
        for s in c["attribution"]["city_stores"]:
            if s not in stores:
                stores.append(s)
        for p in c["attribution"]["support_periods"]:
            periods[(p["start_date"], p["end_date"])] = p
    plist = sorted(periods.values(), key=lambda p: p["start_date"])
    return {"run_id": run["run_id"], "record_count": run.get("record_count"),
            "product_experts": experts, "city_stores": stores,
            "support_periods": plist, "window": window_from(plist)}


def evidence_text(row: dict):
    quote = (row.get("quote") or "").strip()
    if quote:
        return quote, True
    return (row.get("statement") or "").strip(), False


def evidence_source(row: dict) -> str:
    ref = row["source_ref"]
    field = ref.get("source_field") or ""
    etype = row.get("evidence_type") or ""
    return (f"{ref.get('expert', '—')} · {ref.get('store', '—')} · {ref.get('support_date', '—')} · "
            f"{SOURCE_FIELD_LABEL.get(field, field or '—')} · {EVIDENCE_TYPE_LABEL.get(etype, etype or '—')}")


def pattern_evidence(c, evidence):
    return [evidence[eid] for eid in c["source_evidence_ids"] if eid in evidence]


def quote_md(rows: list[dict]) -> list[str]:
    out: list[str] = []
    for row in rows[:QUOTE_LIMIT]:
        text, verbatim = evidence_text(row)
        out.append(f"> 「{text}」" if verbatim else f"> {text}（归一化陈述，非原文）")
        out.append(f"> — {evidence_source(row)}")
        out.append("")
    if len(rows) > QUOTE_LIMIT:
        out.append(f"<details><summary>更多原文（{len(rows) - QUOTE_LIMIT}）</summary>")
        out.append("")
        for row in rows[QUOTE_LIMIT:]:
            text, verbatim = evidence_text(row)
            out.append(f"> 「{text}」" if verbatim else f"> {text}（归一化陈述，非原文）")
            out.append(f"> — {evidence_source(row)}")
            out.append("")
        out.append("</details>")
        out.append("")
    return out


def quote_html(add, rows: list[dict]) -> None:
    def emit(row: dict) -> None:
        text, verbatim = evidence_text(row)
        if verbatim:
            add(f"<blockquote>{_esc(text)}</blockquote>")
        else:
            add(f"<blockquote>{_esc(text)}<span class='norm'>（归一化陈述，非原文）</span></blockquote>")
        add(f"<div class='src'>{_esc(evidence_source(row))}</div>")

    for row in rows[:QUOTE_LIMIT]:
        emit(row)
    if len(rows) > QUOTE_LIMIT:
        add(f"<details class='more'><summary>更多原文（{len(rows) - QUOTE_LIMIT}）</summary>")
        for row in rows[QUOTE_LIMIT:]:
            emit(row)
        add("</details>")


def research_observations(findings, conv_by_pattern):
    out = []
    for f in findings:
        if f.get("status") != "ready":
            continue
        convs = [conv_by_pattern[pid] for pid in f["pattern_ids"]]
        if not convs or not all(c["recurrence"] == "systemic" for c in convs):
            continue
        mentions = len({e for c in convs for e in c["source_evidence_ids"]})
        out.append((mentions, f))
    out.sort(key=lambda t: (-t[0], t[1]["finding_id"]))
    return [f for _, f in out[:OBSERVATION_LIMIT]]


def trace_rows(patterns, conv_by_pattern):
    rows = []
    for p in patterns:
        c = conv_by_pattern[p["pattern_id"]]
        rows.append({"pattern_id": p["pattern_id"], "pattern_key": p["pattern_key"],
                     "evidence_strength": c["evidence_strength"], "recurrence": c["recurrence"],
                     "evidence_count": c["counts"]["evidence_count"],
                     "convergence_id": c["convergence_id"], "issue_ids": p["issue_ids"]})
    return rows


def ranked(counts: list[dict], model: str) -> list[dict]:
    rows = []
    for r in counts:
        records = r.get("records_by_model", {}).get(model, [])
        if records:
            rows.append({"label": r["label"], "code": r["code"],
                         "mentions": r["by_model"].get(model, 0), "record_count": len(records)})
    rows.sort(key=lambda x: (-x["record_count"], -x["mentions"], x["label"]))
    return rows


def model_label(model: str) -> str:
    return {"STORE": "全店", "OTHER": "其他车型"}.get(model, model)


def sum_models(counts: list[dict], models: list[str]) -> list[dict]:
    rows = []
    for r in counts:
        recs: set[int] = set()
        mentions = 0
        for m in models:
            mentions += r["by_model"].get(m, 0)
            recs.update(r.get("records_by_model", {}).get(m, []))
        if recs:
            rows.append({"label": r["label"], "mentions": mentions, "record_count": len(recs)})
    rows.sort(key=lambda x: (-x["record_count"], -x["mentions"], x["label"]))
    return rows


def other_models_summary(counts: list[dict]) -> list[dict]:
    return sum_models(counts, OTHER_MODELS)


def store_level_summary(counts: list[dict]) -> list[dict]:
    return sum_models(counts, ["STORE"])


def store_ops_columns(record: dict) -> dict:
    cols = {code: [] for code in STORE_OPS_CODE}
    for item in record["items"]:
        if item["code"] in cols:
            cols[item["code"]].append(item["quote"])
    return cols


def scope_line(scope, evidence_count, problem_count, coding_count) -> str:
    return (f"{scope['record_count']} 条记录 · {len(scope['product_experts'])} 位专家 · "
            f"{len(scope['city_stores'])} 家门店 · {evidence_count} 条一线观察 · "
            f"{problem_count} 个开放问题 · {coding_count} 条预设编码")


# ----------------------------------------------------------------------------
# Markdown
# ----------------------------------------------------------------------------


def build_markdown(run, patterns, convergences, findings, issues, evidence, pstats) -> str:
    pidx = {p["pattern_id"]: p for p in patterns}
    conv_by_pattern = {c["pattern_id"]: c for c in convergences}
    scope = scope_from(run, convergences)
    obs = research_observations(findings, conv_by_pattern)
    ordered = sorted(convergences, key=lambda c: (-c["counts"]["evidence_count"], c["pattern_id"]))
    top, rest = ordered[:DETAIL_LIMIT], ordered[DETAIL_LIMIT:]

    L = []
    add = L.append
    add(f"# 产品专家一线问题发现｜{scope['window']}")
    add("")

    add("# 01 本期概览")
    add("")
    add(scope_line(scope, len(evidence), len(patterns), pstats["coding_count"]))
    add("")
    if obs:
        for f in obs:
            add(f"- {f['statement']}")
        add("")

    # ---- 02 Preset Coding ----
    add("# 02 业务主题扫描")
    add("")
    add("> 预设问题编码：问题事先已知，LLM 只做编码，计数由脚本确定性聚合。")
    add("")

    add("## A1 门店支持概况")
    add("")
    add("| 项目 | 内容 |")
    add("| --- | --- |")
    add(f"| 记录数 | {scope['record_count']} |")
    add(f"| 产品专家 | {len(scope['product_experts'])}：{fmt_list(scope['product_experts'])} |")
    add(f"| 城市+门店 | {len(scope['city_stores'])}：{fmt_list(scope['city_stores'])} |")
    add(f"| 支持波次 | {len(scope['support_periods'])}：" +
        fmt_list([p["raw"] for p in scope["support_periods"]]) + " |")
    add("")

    add("---")
    add("")
    add("## A2 现场客流情况")
    add("")
    add("| 记录 | 专家 / 门店 | 客流 | 留资 | 试驾 | 锁单/交付 | 高峰 |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for rec in pstats["store_ops"]["records"]:
        cols = store_ops_columns(rec)
        add(f"| {rec['support_date']} | {rec['expert']} / {rec['store']} | "
            f"{fmt_list(cols['footfall'])} | {fmt_list(cols['leads'])} | {fmt_list(cols['test_drive'])} | "
            f"{fmt_list(cols['lock_order'])} | {fmt_list(cols['peak_hours'])} |")
    add("")
    add("> 只统计门店经营字段中明确写出的内容；空值为未记录，不代表 0。")
    add("")

    add("---")
    add("")
    add("## A3 展车状态")
    add("")
    add("| 门店 | 车型 | 展车 | 试驾车 | 原文 |")
    add("| --- | --- | --- | --- | --- |")
    for r in pstats["availability"]["rows"]:
        disp = r["display"]["label"] if r["display"] else "—"
        test = r["test_drive"]["label"] if r["test_drive"] else "—"
        quotes = "；".join(f"「{q}」" for q in r["quotes"])
        add(f"| {r['store']} | {model_label(r['model'])} | {disp} | {test} | {quotes} |")
    add("")

    denom = scope["record_count"]
    add(f"> A4–A7 为**记录覆盖率**：分子是命中该主题的去重 record_index 数，"
        f"分母是门店记录数（N={denom}）。同一记录可命中多个主题，故各行分数不可相加。")
    add("")
    for gkey, title in [("customer_concern", "A4 客户关注主题"),
                        ("positive_feedback", "A5 正向产品反馈"),
                        ("competitor_attention", "A6 竞品关注"),
                        ("purchase_barrier", "A7 下单阻碍")]:
        group = pstats[gkey]
        add("---")
        add("")
        add(f"## {title}")
        add("")
        any_rows = False
        for model in MODELS:
            rows = ranked(group["counts"], model)
            if not rows:
                continue
            any_rows = True
            add(f"**{model}**")
            add("")
            for r in rows:
                add(f"- {r['label']}　{'█' * max(1, round(r['record_count'] / denom * 10))} "
                    f"{r['record_count']}/{denom} 条记录（编码 {r['mentions']}）")
            add("")
        oth = other_models_summary(group["counts"])
        if oth:
            add("**其他车型**：" + "、".join(
                f"{r['label']} {r['record_count']}/{denom}（编码 {r['mentions']}）" for r in oth))
            add("")
        st = store_level_summary(group["counts"])
        if st:
            add("**全店（未区分车型）**：" + "、".join(
                f"{r['label']} {r['record_count']}/{denom}（编码 {r['mentions']}）" for r in st))
            add("")
        if not any_rows:
            add("本轮 L6/LS6 无明确记录（unavailable）。")
            add("")

    add("---")
    add("")
    add("## A8 不满意主题")
    add("")
    add("暂缓启用：与开放问题发现的弱项重叠度高，待数据积累后再编码。")
    add("")

    # ---- 03 Open Discovery ----
    add("# 03 一线问题发现")
    add("")
    add("> 开放问题发现：问题事先未知，由模型从原始自由文本中发现并归并。")
    add("")
    add(f"**{scope['record_count']} 条门店记录 → 识别出 {len(patterns)} 个开放问题**")
    add("")

    for i, c in enumerate(top, start=1):
        p = pidx[c["pattern_id"]]
        if i > 1:
            add("---")
            add("")
        add(f"## B{i} {p['title']}")
        add("")
        add(f"**{c['counts']['evidence_count']} 次提及 · {c['counts']['product_expert_count']} 位专家 · "
            f"{c['counts']['city_store_count']} 家门店**")
        add("")
        add(f"**LLM 提炼**：{p['hypothesis']}")
        add("")
        add("**一线上报**")
        add("")
        L.extend(quote_md(pattern_evidence(c, evidence)))

    if rest:
        add("<details><summary>其余开放问题（{}）</summary>".format(len(rest)))
        add("")
        for c in rest:
            p = pidx[c["pattern_id"]]
            add(f"### {p['title']}")
            add("")
            add(f"**{c['counts']['evidence_count']} 次提及 · {c['counts']['product_expert_count']} 位专家 · "
                f"{c['counts']['city_store_count']} 家门店**")
            add("")
            add(f"**LLM 提炼**：{p['hypothesis']}")
            add("")
            add("**一线上报**")
            add("")
            L.extend(quote_md(pattern_evidence(c, evidence)))
        add("</details>")
        add("")

    add("## 时间比较")
    add("")
    add("Baseline only：本期为首个基线窗口，暂无跨期趋势。")
    add("")

    add("## 方法与 Runtime 追溯")
    add("")
    add("- A 预设编码：问题事先已知，LLM 只编码，计数由 `derive_preset_stats.py` 聚合。")
    add("- B 开放发现：问题事先未知，Evidence → Issue → Pattern → Convergence。")
    add("- 数字只读 `preset_stats.json` / `convergence.json`；一线原文逐字取自 `evidence.jsonl`，报告不生成、不改写任何原话。")
    add("- 样本为定性、自报、非随机门店样本，用于发现问题与形成假设，不用于估计总体比例。")
    add("")
    add("| Pattern | pattern_key | 证据强度 | 复现 | 证据 | Convergence | Issues |")
    add("| --- | --- | --- | --- | ---: | --- | --- |")
    for t in trace_rows(patterns, conv_by_pattern):
        add(f"| {t['pattern_id']} | `{t['pattern_key']}` | {t['evidence_strength']} | {t['recurrence']} | "
            f"{t['evidence_count']} | {t['convergence_id']} | {fmt_list(t['issue_ids'])} |")
    add("")
    add("---")
    add("")
    add("_Product Expert · 用数据、AI 和一点点常识，研究复杂世界。_")
    add("")
    return "\n".join(L)


# ----------------------------------------------------------------------------
# HTML
# ----------------------------------------------------------------------------


def _esc(v):
    return html.escape(str(v))


def _chips(values):
    return "".join(f'<span class="chip">{_esc(v)}</span>' for v in values if v)


def build_html(run, patterns, convergences, findings, issues, evidence, pstats) -> str:
    pidx = {p["pattern_id"]: p for p in patterns}
    conv_by_pattern = {c["pattern_id"]: c for c in convergences}
    scope = scope_from(run, convergences)
    obs = research_observations(findings, conv_by_pattern)
    ordered = sorted(convergences, key=lambda c: (-c["counts"]["evidence_count"], c["pattern_id"]))
    top, rest = ordered[:DETAIL_LIMIT], ordered[DETAIL_LIMIT:]

    P = []
    add = P.append
    add("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>")
    add("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    add(f"<title>产品专家一线问题发现 · {_esc(scope['window'])}</title><style>")
    add("""
:root{--paper:#ffffff;--paper-2:#f5f5f5;--ink:#2d3142;--muted:#4f5d75;--soft:#7a8399;
  --rule:rgba(45,49,66,.12);--rule-solid:#e3e3e3;--accent:#eb6c36;--accent-tint:rgba(235,108,54,.08);--link:#2e5aa8;
  --fill:rgba(45,49,66,.05);--fill-strong:rgba(45,49,66,.09)}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:"Noto Sans CJK SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif;line-height:1.7;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:960px;margin:0 auto;padding:56px 28px 72px}
.eyebrow{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin:0 0 12px}
h1{font-size:34px;line-height:1.2;font-weight:600;letter-spacing:-.01em;color:var(--ink);margin:0 0 12px}
.overview{font-size:14.5px;color:var(--muted);margin:0 0 16px;font-variant-numeric:tabular-nums}
h2.sect{font-size:20px;font-weight:600;color:var(--ink);margin:52px 0 16px;padding-bottom:10px;border-bottom:1px solid var(--rule-solid)}
h2.sect small{display:block;font-size:12.5px;font-weight:400;color:var(--soft);letter-spacing:0;margin-top:4px}
h3{font-size:15px;color:var(--ink);font-weight:600;margin:32px 0 12px}
h3 .n{color:var(--soft);margin-right:8px;font-variant-numeric:tabular-nums}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-top:10px}
.card{background:var(--paper-2);border:1px solid var(--rule);border-radius:8px;padding:18px 20px}
.card.span-2{grid-column:1 / -1}
.card h3{margin-top:0}
.card .note{margin-top:12px}
.obs-list{margin:0;padding-left:20px}
.obs-list li{margin:6px 0;font-size:14px}
.stat-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:4px}
.stat-row.two{grid-template-columns:repeat(2,1fr)}
.stat{background:var(--paper);border:1px solid var(--rule);border-radius:6px;padding:12px 14px}
.stat b{display:block;font-size:24px;font-weight:600;color:var(--ink);font-variant-numeric:tabular-nums;line-height:1.1}
.stat span{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
th,td{padding:11px 10px;border-bottom:1px solid var(--rule);text-align:left;vertical-align:top}
th{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600;
  border-bottom:1px solid var(--rule-solid);white-space:nowrap}
tr:last-child td{border-bottom:none}
.chip{display:inline-block;font-size:11.5px;color:var(--muted);background:var(--fill);
  border:1px solid var(--rule);border-radius:4px;padding:1px 6px;margin:2px 4px 2px 0;white-space:nowrap}
.note{font-size:12.5px;color:var(--soft);margin:10px 0 0}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:28px}
.rank{display:flex;flex-direction:column;gap:7px;margin:8px 0 0}
.rank .row{display:grid;grid-template-columns:1fr 1fr 42px;align-items:center;gap:10px}
.rank .label{font-size:13px;color:var(--ink);white-space:normal;overflow-wrap:anywhere}
.rank .track{height:10px;background:var(--fill-strong);border-radius:3px;overflow:hidden}
.rank .track>i{display:block;height:100%;background:var(--muted);border-radius:3px}
.rank .row:first-child .track>i{background:var(--accent)}
.rank .num{font-size:13.5px;font-weight:600;color:var(--ink);text-align:right;font-variant-numeric:tabular-nums}
.rank-title{font-size:11.5px;font-weight:600;color:var(--muted);letter-spacing:.08em;text-transform:uppercase;margin:0}
.other-models{font-size:12.5px;color:var(--soft);margin:10px 0 0;font-variant-numeric:tabular-nums}
.detail{background:var(--paper-2);border:1px solid var(--rule);border-radius:8px;padding:18px 20px;margin:14px 0}
.detail h4{font-size:17px;color:var(--ink);font-weight:600;margin:0 0 8px}
.meta{font-size:13px;color:var(--muted);font-weight:600;margin:0 0 12px;font-variant-numeric:tabular-nums}
.detail .block{margin:10px 0}
.detail .k{display:block;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--soft);margin-bottom:3px}
.detail .v{font-size:14px;margin:0}
.raw{margin-top:14px;border-top:1px solid var(--rule);padding-top:10px}
blockquote{margin:0 0 2px;padding:9px 13px;background:var(--paper);border-left:2px solid var(--rule-solid);border-radius:0 4px 4px 0;font-size:13.5px}
blockquote .norm{color:var(--soft);font-size:11.5px}
.src{font-size:11px;color:var(--soft);margin:0 0 12px 13px}
details.other{margin-top:16px}
details.other summary{cursor:pointer;font-size:14px;color:var(--link);font-weight:600}
details.more{margin-top:8px}
details.more summary{cursor:pointer;font-size:12.5px;color:var(--link);font-weight:600;margin-bottom:8px}
.temporal{font-size:13.5px;color:var(--muted);border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);padding:14px 0;margin:40px 0 0}
.appendix{font-size:12.5px;color:var(--soft);margin-top:28px}
.appendix summary{cursor:pointer;font-size:13px;color:var(--link);font-weight:600}
.appendix ul{margin:10px 0 0;padding-left:18px}
.appendix table{font-size:12px}.appendix th,.appendix td{padding:7px 8px}
footer{margin-top:40px;color:var(--soft);font-size:12px;letter-spacing:.04em}
@media(max-width:760px){.cols{grid-template-columns:1fr}.grid{grid-template-columns:1fr}.stat-row{grid-template-columns:1fr 1fr}h1{font-size:26px}}
""")
    add("</style></head><body><main class='wrap'>")
    add('<p class="eyebrow">FIELD INTELLIGENCE · ' + _esc(scope["run_id"]) + "</p>")
    add(f"<h1>产品专家一线问题发现｜{_esc(scope['window'])}</h1>")

    add("<h2 class='sect'>01 本期概览</h2>")
    add("<section class='card span-2'>")
    add(f"<p class='overview'>{_esc(scope_line(scope, len(evidence), len(patterns), pstats['coding_count']))}</p>")
    if obs:
        add("<ul class='obs-list'>")
        for f in obs:
            add(f"<li>{_esc(f['statement'])}</li>")
        add("</ul>")
    add("</section>")

    # 02
    add("<h2 class='sect'>02 业务主题扫描"
        "<small>预设问题编码：问题事先已知；LLM 只做编码；计数由脚本确定性聚合</small></h2>")
    add("<div class='grid'>")

    add("<section class='card span-2'>")
    add("<h3><span class='n'>A1</span>门店支持概况</h3>")
    add("<div class='stat-row'>")
    add(f"<div class='stat'><b>{scope['record_count']}</b><span>门店记录</span></div>")
    add(f"<div class='stat'><b>{len(scope['product_experts'])}</b><span>产品专家</span></div>")
    add(f"<div class='stat'><b>{len(scope['city_stores'])}</b><span>城市+门店</span></div>")
    add(f"<div class='stat'><b>{len(scope['support_periods'])}</b><span>支持波次</span></div>")
    add("</div>")
    add(f"<p class='note'>产品专家：{_esc(fmt_list(scope['product_experts']))}<br>"
        f"城市+门店：{_esc(fmt_list(scope['city_stores']))}<br>"
        f"支持波次：{_esc(fmt_list([p['raw'] for p in scope['support_periods']]))}</p>")
    add("</section>")

    add("<section class='card span-2'>")
    add("<h3><span class='n'>A2</span>现场客流情况</h3>")
    add("<table><thead><tr><th>记录</th><th>专家 / 门店</th><th>客流</th><th>留资</th><th>试驾</th><th>锁单/交付</th><th>高峰</th></tr></thead><tbody>")
    for rec in pstats["store_ops"]["records"]:
        c = store_ops_columns(rec)
        add(f"<tr><td>{_esc(rec['support_date'])}</td><td>{_esc(rec['expert'])} / {_esc(rec['store'])}</td>"
            f"<td>{_esc(fmt_list(c['footfall']))}</td><td>{_esc(fmt_list(c['leads']))}</td>"
            f"<td>{_esc(fmt_list(c['test_drive']))}</td><td>{_esc(fmt_list(c['lock_order']))}</td>"
            f"<td>{_esc(fmt_list(c['peak_hours']))}</td></tr>")
    add("</tbody></table>")
    add("<p class='note'>只统计明确写出的内容；空值为未记录，不代表 0。</p>")
    add("</section>")

    add("<section class='card span-2'>")
    add("<h3><span class='n'>A3</span>展车状态</h3>")
    add("<table><thead><tr><th>门店</th><th>车型</th><th>展车</th><th>试驾车</th><th>原文</th></tr></thead><tbody>")
    for r in pstats["availability"]["rows"]:
        disp = r["display"]["label"] if r["display"] else "—"
        test = r["test_drive"]["label"] if r["test_drive"] else "—"
        quotes = "；".join(f"「{q}」" for q in r["quotes"])
        add(f"<tr><td>{_esc(r['store'])}</td><td>{_esc(model_label(r['model']))}</td><td>{_esc(disp)}</td>"
            f"<td>{_esc(test)}</td><td>{_esc(quotes)}</td></tr>")
    add("</tbody></table>")
    add("</section>")

    denom = scope["record_count"]
    for idx, (gkey, title) in enumerate([("customer_concern", "客户关注主题"),
                                          ("positive_feedback", "正向产品反馈"),
                                          ("competitor_attention", "竞品关注"),
                                          ("purchase_barrier", "下单阻碍")], start=4):
        group = pstats[gkey]
        add("<section class='card span-2'>")
        add(f"<h3><span class='n'>A{idx}</span>{_esc(title)}</h3>")
        add("<div class='cols'>")
        has = False
        for model in MODELS:
            rows = ranked(group["counts"], model)
            add("<div>")
            add(f"<p class='rank-title'>{_esc(model)}</p>")
            if rows:
                has = True
                add("<div class='rank'>")
                for r in rows:
                    pct = max(3, round(r["record_count"] / denom * 100))
                    add(f"<div class='row' title='编码条目 {r['mentions']}'>"
                        f"<div class='label'>{_esc(r['label'])}</div>"
                        f"<div class='track'><i style='width:{pct}%'></i></div>"
                        f"<div class='num'>{r['record_count']}/{denom}</div></div>")
                add("</div>")
            else:
                add("<p class='note'>无明确记录</p>")
            add("</div>")
        add("</div>")
        oth = other_models_summary(group["counts"])
        if oth:
            add("<p class='other-models'>其他车型：" +
                _esc("、".join(f"{r['label']} {r['record_count']}/{denom}（编码 {r['mentions']}）" for r in oth)) + "</p>")
        st = store_level_summary(group["counts"])
        if st:
            add("<p class='other-models'>全店（未区分车型）：" +
                _esc("、".join(f"{r['label']} {r['record_count']}/{denom}（编码 {r['mentions']}）" for r in st)) + "</p>")
        if not has:
            add("<p class='note'>本轮 L6/LS6 无明确记录（unavailable）。</p>")
        add("</section>")

    add("<section class='card span-2'>")
    add("<h3><span class='n'>A8</span>不满意主题</h3>")
    add("<p class='note'>暂缓启用：与开放问题发现的弱项重叠度高，待数据积累后再编码。</p>")
    add("</section>")

    add("</div>")
    add(f"<p class='note'>A4–A7 为<strong>记录覆盖率</strong>：分子是命中该主题的去重 record_index 数，"
        f"分母是门店记录数（N={denom}）。同一记录可命中多个主题，故各行分数不可相加。</p>")

    # B
    add("<h2 class='sect'>03 一线问题发现"
        "<small>开放问题发现：问题事先未知；由模型从一线文字中发现并归并</small></h2>")
    add("<section class='card span-2'>")
    add("<div class='stat-row two'>")
    add(f"<div class='stat'><b>{scope['record_count']}</b><span>门店记录</span></div>")
    add(f"<div class='stat'><b>{len(patterns)}</b><span>识别出的开放问题</span></div>")
    add("</div>")
    add(f"<p class='note'>{scope['record_count']} 条门店记录中，模型发现并归并出 "
        f"{len(patterns)} 个开放问题；其余问题折叠在文末。</p>")
    add("</section>")

    def render_detail(label, c):
        p = pidx[c["pattern_id"]]
        add("<div class='detail'>")
        add(f"<h4>{_esc(label)}{_esc(p['title'])}</h4>")
        add(f"<p class='meta'>{c['counts']['evidence_count']} 次提及 · "
            f"{c['counts']['product_expert_count']} 位专家 · {c['counts']['city_store_count']} 家门店</p>")
        add(f"<div class='block'><span class='k'>LLM 提炼</span><p class='v'>{_esc(p['hypothesis'])}</p></div>")
        add("<div class='raw'><span class='k'>一线上报</span>")
        quote_html(add, pattern_evidence(c, evidence))
        add("</div></div>")

    for i, c in enumerate(top, start=1):
        render_detail(f"B{i} ", c)

    if rest:
        add(f"<details class='other'><summary>其余开放问题（{len(rest)}）</summary>")
        for c in rest:
            render_detail("", c)
        add("</details>")

    add("<p class='temporal'>Baseline only：本期为首个基线窗口，暂无跨期趋势。</p>")

    add("<details class='appendix'><summary>方法与 Runtime 追溯</summary><ul>")
    add("<li>A 预设编码：问题事先已知，LLM 只编码，计数由 <code>derive_preset_stats.py</code> 聚合。</li>")
    add("<li>B 开放发现：问题事先未知，Evidence → Issue → Pattern → Convergence。</li>")
    add("<li>数字只读 <code>preset_stats.json</code> / <code>convergence.json</code>；一线原文逐字取自 "
        "<code>evidence.jsonl</code>，报告不生成、不改写任何原话。</li>")
    add("<li>样本为定性、自报、非随机门店样本，不用于估计总体比例。</li>")
    add("</ul><table><thead><tr><th>Pattern</th><th>pattern_key</th><th>证据强度</th><th>复现</th>"
        "<th>证据</th><th>Convergence</th><th>Issues</th></tr></thead><tbody>")
    for t in trace_rows(patterns, conv_by_pattern):
        add(f"<tr><td>{_esc(t['pattern_id'])}</td><td><code>{_esc(t['pattern_key'])}</code></td>"
            f"<td>{_esc(t['evidence_strength'])}</td><td>{_esc(t['recurrence'])}</td>"
            f"<td>{t['evidence_count']}</td><td>{_esc(t['convergence_id'])}</td>"
            f"<td>{_esc(fmt_list(t['issue_ids']))}</td></tr>")
    add("</tbody></table></details>")

    add("<footer>产品专家一线问题发现 · " + _esc(scope["window"]) + " · " + _esc(scope["run_id"]) +
        " · Field Intelligence Report</footer>")
    add("</main></body></html>")
    return "\n".join(P)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    run_dir = args.run_dir
    run = load_json(run_dir / "run.json")
    patterns = load_json(run_dir / "patterns.json")
    convergences = load_json(run_dir / "convergence.json")
    findings = load_json(run_dir / "findings.json")
    issues = {r["issue_id"]: r for r in load_json(run_dir / "issues.json")}
    evidence = {r["evidence_id"]: r for r in load_jsonl(run_dir / "evidence.jsonl")}
    pstats = load_json(run_dir / "preset_stats.json")

    out_dir = args.output_dir or (APP_DIR / "reports" / run["run_id"])
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "product_expert_report.md"
    html_path = out_dir / "product_expert_report.html"
    md_path.write_text(build_markdown(run, patterns, convergences, findings, issues, evidence, pstats), encoding="utf-8")
    html_path.write_text(build_html(run, patterns, convergences, findings, issues, evidence, pstats), encoding="utf-8")
    print(f"wrote {md_path}")
    print(f"wrote {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
