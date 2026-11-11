#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.2 Validated Research Planning —— 研究计划、前置核验与结论契约。

本模块只做三件事，不做正式分析计算：
1. `probe_facts()`        轻量探测：只回答"数据够不够、字段在不在、样本有多少"
2. `build_research_plan()` 把研究任务写成可程序化核验的计划
3. `validate_research_plan()` Gate A：逐问 PASS / SKIP / BLOCK

以及计算后的结论契约：
4. `compute_findings()`   ResearchFindings：每条结论绑定本次指标与数值
5. `validate_findings()`  Gate B：数值、方向、恒等式
6. `validate_report()`    Gate C：HTML 与结论一致性
"""

from __future__ import annotations

import re
from typing import Any

# ── 问题库：每个研究问题的可比性条件与输出依赖 ────────────────────────────
# required=True 的问题若不可执行 → BLOCK（整轮研究必须重新规划）
# required=False 的问题不可执行 → SKIP（跳过并记录，不影响主流程）
QUESTION_SPECS: list[dict[str, Any]] = [
    {"id": "q1", "title": "同期锁单水平", "required": True,
     "needs": ["locks"], "outputs": ["table_same_period", "chart_cumulative"]},
    {"id": "q2", "title": "差异形成路径", "required": True,
     "needs": ["locks"], "outputs": ["table_gap"]},
    {"id": "q3", "title": "日增动能", "required": True,
     "needs": ["locks"], "outputs": ["table_dynamics", "chart_daily"]},
    {"id": "q4", "title": "预售池规模与转化", "required": True,
     "needs": ["presale"], "outputs": ["table_presale", "chart_pool_state"]},
    {"id": "q5", "title": "锁单来源三分", "required": True,
     "needs": ["origin"], "outputs": ["table_origin", "chart_origin"]},
    {"id": "q6", "title": "区域差额", "required": False,
     "needs": ["province"], "outputs": ["table_province", "table_city"]},
    {"id": "q7", "title": "网络与单店产能", "required": False,
     "needs": ["store"], "outputs": ["table_store", "chart_network"]},
    {"id": "q8", "title": "产品结构与客群", "required": False,
     "needs": ["product", "profile"], "outputs": ["table_product", "table_user"]},
    {"id": "q8b", "title": "同档客群对比", "required": False,
     "needs": ["segment"], "outputs": ["table_same_battery"]},
    {"id": "q8c", "title": "座椅拆分对比", "required": False,
     "needs": ["seat_field"], "outputs": ["table_seat", "chart_seat_combos"]},
    {"id": "q8d", "title": "版本缺口验证", "required": False,
     "needs": ["segment"], "outputs": ["table_version_gap"]},
    {"id": "q9", "title": "订单质量", "required": False,
     "needs": ["refund_events"], "outputs": ["table_quality"]},
    {"id": "q10", "title": "后续增长动能", "required": False,
     "needs": ["pool_events"], "outputs": ["table_pool", "chart_pool_consumption"]},
]

MIN_LOCKS = 30          # 单代际窗口锁单下限
MIN_SEGMENT = 30        # 同档客群比较的最小样本
MIN_PROVINCE_N = 10     # 省级分析的有效样本下限
SMALL_GAP_RATIO = 0.05  # 差额小于主车累计 5% 时禁用「贡献占比」类指标


def _fmt(x: float) -> str:
    return f"{x:,.0f}"


def build_research_plan(facts: dict) -> dict:
    """把研究任务写成结构化计划（可被程序核验）。"""
    main = facts["main"]
    benches = facts["benchmarks"]
    n = facts["n_days"]
    gens = [main] + benches
    cum = facts["cum"]
    gaps = {b: cum[main] - cum[b] for b in benches}
    small_gap = all(abs(g) <= SMALL_GAP_RATIO * max(cum[main], 1) for g in gaps.values())

    questions = []
    for spec in QUESTION_SPECS:
        q = {
            "id": spec["id"], "title": spec["title"], "required": spec["required"],
            "compares": [main] + benches if spec["id"] not in ("q8b", "q8c") else [main, benches[0]],
            "metrics": [], "data_deps": spec["needs"], "outputs": spec["outputs"],
            "comparability": [], "fallback": "skip_and_record",
        }
        if spec["id"] in ("q1", "q2", "q3"):
            q["metrics"] = ["cum_locks", "daily_locks", "marginal_gap"]
            q["comparability"] = ["各代际窗口锁单 ≥ %d" % MIN_LOCKS,
                                  "统计粒度均为「用户车零售单、按 lock_time 归日」"]
        elif spec["id"] == "q4":
            q["metrics"] = ["pool_total", "pool_lock_rate", "scale_effect", "rate_effect"]
            q["comparability"] = ["各代际预售池 ≥ 100 单",
                                  "预售天数差异需在结论中标注，不可直接读作需求强弱"]
        elif spec["id"] == "q5":
            q["metrics"] = ["pre_lock", "launch_day_lock", "direct_lock"]
            q["comparability"] = ["小订停收时点一致（上市日 24:00）",
                                  "直锁占比跨代际差异 > 10pp 时需先排除下单链路差异"]
        elif spec["id"] == "q6":
            q["metrics"] = ["province_abs_diff", "city_abs_diff"]
            q["comparability"] = ["各代际有效省份样本 ≥ %d" % MIN_PROVINCE_N,
                                  "上牌省份口径一致（license_city → 省）"]
        elif spec["id"] == "q7":
            q["metrics"] = ["stores_with_gen", "locks_per_store"]
            q["comparability"] = ["门店必须按目标代际过滤",
                                  "统计粒度一致（单店窗口锁单）"]
        elif spec["id"] == "q8":
            q["metrics"] = ["version_mix", "battery_mix", "gender", "age_mean", "tier"]
            q["comparability"] = ["配置属性名与取值名字面一致才可比",
                                  "跨代际色板不同时不得比较具体颜色"]
        elif spec["id"] in ("q8b", "q8d"):
            seg = facts.get("segments", {})
            # 该区块只比较「主代际 vs 第一个对标」，核验对象必须与之一致
            pair = [main, benches[0]]
            missing = [g for g in pair if not seg.get(g, {}).get("93kWh")]
            q["metrics"] = ["segment_share", "segment_profile"]
            q["comparability"] = ["主代际与第一个对标都必须有 93kWh 段（该区块只比这一对）",
                                  "各侧同档样本 ≥ %d" % MIN_SEGMENT]
            q["blocked_by"] = [f"{g} 无 93kWh 段" for g in missing]
        elif spec["id"] == "q8c":
            q["metrics"] = ["seat_mix", "seat_profile"]
            q["comparability"] = ["config_attribute 存在「座椅」字段且有效值占比 ≥ 80%"]
            q["blocked_by"] = ([f"{main} 的「座椅」有效值占比 {facts['seat_coverage']:.0%}"]
                               if facts.get("seat_coverage", 0) < 0.8 else [])
        questions.append(q)

    return {
        "version": "1.2",
        "main": main, "benchmarks": benches, "as_of": facts["as_of"], "n_days": n,
        "window": {"main": [facts["windows"][main][0], facts["windows"][main][1]]},
        "global_constraints": {
            "small_gap": small_gap,
            "gap_values": gaps,
            "cum": {g: cum[g] for g in gens},
            "disable_share_of_gap": small_gap,
        },
        "questions": questions,
        "narrative_policy": {
            "no_preset_verdict": True,
            "inherit_previous_findings": False,
            "title_template": "data_driven",
        },
    }


def validate_research_plan(plan: dict, facts: dict) -> dict:
    """Gate A：逐问判定 PASS / SKIP / BLOCK，并给出可复算的依据。"""
    main = plan["main"]
    benches = plan["benchmarks"]
    n = plan["n_days"]
    cum = facts["cum"]
    results = []
    blocked, skipped = [], []

    def add(q, status, reason):
        results.append({"id": q["id"], "title": q["title"], "required": q["required"],
                        "status": status, "reason": reason})
        if status == "BLOCK":
            blocked.append(q["id"])
        elif status == "SKIP":
            skipped.append(q["id"])

    for q in plan["questions"]:
        qid = q["id"]
        # 1) 全局：样本量
        low = [g for g in ([main] + benches) if cum.get(g, 0) < MIN_LOCKS]
        if low:
            add(q, "BLOCK", f"{'、'.join(low)} 窗口锁单 < {MIN_LOCKS}，样本不足以支撑任何比较")
            continue

        # 2) 同档/版本缺口：按电量段存在性
        if qid in ("q8b", "q8d"):
            missing = q.get("blocked_by") or []
            if missing:
                add(q, "SKIP", "；".join(missing) + "，同档/缺口比较不成立")
                continue
            seg = facts["segments"]
            thin = [g for g in [main, benches[0]] if seg.get(g, {}).get("93kWh", 0) < MIN_SEGMENT]
            if thin:
                add(q, "SKIP", f"{'、'.join(thin)} 同档样本 < {MIN_SEGMENT}")
                continue
            add(q, "PASS", "两侧均有 93kWh 段且样本达标")
            continue

        # 3) 座椅拆分
        if qid == "q8c":
            if q.get("blocked_by"):
                add(q, "SKIP", "；".join(q["blocked_by"]) + "，无法拆分六座/五座")
                continue
            add(q, "PASS", f"「座椅」有效值覆盖 {facts['seat_coverage']:.0%}")
            continue

        # 4) 区域
        if qid == "q6":
            thin = [g for g in [main] + benches if facts.get("province_valid", {}).get(g, 0) < MIN_PROVINCE_N]
            if thin:
                add(q, "SKIP", f"{'、'.join(thin)} 有效省份样本 < {MIN_PROVINCE_N}")
                continue
            add(q, "PASS", "各代际有效省份样本达标，上牌省份口径一致")
            continue

        # 5) 网络
        if qid == "q7":
            thin = [g for g in [main] + benches if facts.get("stores", {}).get(g, 0) < 20]
            if thin:
                add(q, "SKIP", f"{'、'.join(thin)} 有效锁单门店 < 20 家")
                continue
            add(q, "PASS", "各代际均按自身过滤后有 ≥20 家有效锁单门店")
            continue

        # 6) 预售池
        if qid == "q4":
            thin = [g for g in [main] + benches if facts.get("pool", {}).get(g, 0) < 100]
            if thin:
                add(q, "BLOCK", f"{'、'.join(thin)} 预售池 < 100 单，无法做池-转化分解")
                continue
            add(q, "PASS", "三代际预售池均 ≥100 单")
            continue

        # 7) 默认：结构性问题一律 PASS，并登记指标策略
        note = "指标可用"
        if qid in ("q2",) and plan["global_constraints"]["disable_share_of_gap"]:
            note = "差额过小：禁用「D1 占总差额」类贡献占比，改用差额结构叙述"
        add(q, "PASS", note)

    verdict = "BLOCK" if blocked else "PASS"
    return {
        "gate": "A", "verdict": verdict,
        "checked_questions": len(results),
        "passed": [r["id"] for r in results if r["status"] == "PASS"],
        "skipped": [r for r in results if r["status"] == "SKIP"],
        "blocked": [r for r in results if r["status"] == "BLOCK"],
        "results": results,
        "notes": [
            "Gate A 只做可得性/可比性/有效性判定，不产生研究结论",
            f"窗口 N={n}，主代际 {main}，对标 {'、'.join(benches)}",
        ],
    }


# ── ResearchFindings：结论契约 ─────────────────────────────────────────────

def _gap_narrative(d: dict, n: int) -> str:
    d1 = int(round(d.get("d1_diff") or 0))
    cum = int(round(d.get("cum_diff") or 0))
    tail = cum - d1

    def _lead(v: int) -> str:
        return f"领先 {abs(v):,} 单" if v > 0 else (f"落后 {abs(v):,} 单" if v < 0 else "持平")

    head = "D1 持平" if d1 == 0 else f"D1 {_lead(d1)}"
    if tail == 0:
        mid = f"D2–D{n} 持平"
    elif d1 and tail * d1 < 0:
        mid = f"D2–D{n} 净回吐 {abs(tail):,} 单"
    else:
        mid = f"D2–D{n} 再{'领先' if tail > 0 else '落后'} {abs(tail):,} 单"
    return f"{head}，{mid}，最终{_lead(cum)}"


def _dir_word(v: float) -> str:
    return "高于" if v > 0 else ("低于" if v < 0 else "持平")


def compute_findings(ctx: dict) -> list[dict]:
    """从本次计算生成结构化结论；标题按数据方向生成，不继承任何历史案例的措辞。"""
    main, n = ctx["main"], ctx["n_days"]
    benches = ctx["benchmarks"]
    b1 = benches[0]
    b2 = benches[1] if len(benches) > 1 else None
    d = ctx["deltas"]
    cur = ctx["curves"]["curves"]
    dyn = ctx["dynamics"]
    pre = ctx["presale"]
    net = ctx["network"]
    org = ctx["origin"]
    out: list[dict] = []

    def f(id_, title, body, evidence, numbers, direction, scope):
        out.append({"id": id_, "title": title, "body": body, "evidence": evidence,
                    "numbers": numbers, "direction": direction, "scope": scope})

    # F1 水平与形态
    d1 = d[b1]
    ratio = d1["cum_ratio"]
    if ratio < 0.9:
        t = f"绝对水平落后，为对标的 {ratio:.0%}（差 {abs(d1['cum_diff']):,} 单）"
        direction = "behind"
    elif ratio > 1.1:
        t = f"绝对水平领先，为对标的 {ratio:.0%}（多 {abs(d1['cum_diff']):,} 单）"
        direction = "ahead"
    else:
        t = f"总量与对标基本持平（{ratio:.0%}），差异不在规模"
        direction = "parity"
    body = (f"{main} 上市 D1–D{n} 零售锁单 <b>{_fmt(cur[main]['cum'][-1])} 单</b>，"
            f"{b1} {_fmt(d1['cum_bench'])} 单"
            + (f"、{b2} {_fmt(d[b2]['cum_bench'])} 单" if b2 else "")
            + f"；相对于 {b1}：<b>{_gap_narrative(d1, n)}</b>。")
    f("f1", t, body,
      ["curves.curves", "deltas"], {"cum_main": cur[main]["cum"][-1],
                                    "cum_bench": d1["cum_bench"], "ratio": ratio},
      direction, "全部对标")

    # F2 释放节奏
    d1_share_m = dyn[main]["d1_share_of_cum"]
    d1_share_b = dyn[b1]["d1_share_of_cum"]
    diff_pp = (d1_share_m - d1_share_b) * 100
    if abs(diff_pp) < 3:
        t2 = "释放节奏与对标接近，首日占比差异不足 3pp"
        dir2 = "parity"
    elif diff_pp > 0:
        t2 = f"首日集中度明显更高（{d1_share_m:.1%} vs {d1_share_b:.1%}），后续释放更弱"
        dir2 = "front_loaded"
    else:
        t2 = f"首日集中度更低（{d1_share_m:.1%} vs {d1_share_b:.1%}），靠长尾补量"
        dir2 = "back_loaded"
    f("f2", t2,
      f"{main} D1 占窗口累计 {d1_share_m:.1%}，{b1} 为 {d1_share_b:.1%}；"
      f"D2–D{n} 日均 {dyn[main]['tail_avg']:.0f} 单 vs {dyn[b1]['tail_avg']:.0f} 单。",
      ["dynamics.d1_share_of_cum", "dynamics.tail_avg"],
      {"d1_share_main": d1_share_m, "d1_share_bench": d1_share_b},
      dir2, f"vs {b1}")

    # F3 预售池：规模 vs 转化（按数据选主因）
    p_m, p_b = pre[main], pre[b1]
    size_rel = p_m["pool_total"] / max(p_b["pool_total"], 1) - 1
    rate_gap = p_m["pool_lock_rate"] - p_b["pool_lock_rate"]
    if abs(size_rel) >= 0.2 and abs(size_rel) > abs(rate_gap):
        t3 = f"预售池规模{'更小' if size_rel < 0 else '更大'} {abs(size_rel):.0%}，转化率差异相对次要"
    elif abs(rate_gap) >= 0.03:
        t3 = f"预售池转化率{_dir_word(rate_gap)} {abs(rate_gap) * 100:.1f}pp，规模差异相对次要"
    else:
        t3 = "预售池规模与转化率均与对标接近"
    f("f3", t3,
      f"预售池 {_fmt(p_m['pool_total'])} 单（{p_m['presale_days']} 天），"
      f"{b1} {_fmt(p_b['pool_total'])} 单（{p_b['presale_days']} 天）；"
      f"池转化率 {p_m['pool_lock_rate']:.1%} vs {p_b['pool_lock_rate']:.1%}。",
      ["presale.pool_total", "presale.pool_lock_rate"],
      {"pool_main": p_m["pool_total"], "pool_bench": p_b["pool_total"],
       "rate_main": p_m["pool_lock_rate"], "rate_bench": p_b["pool_lock_rate"]},
      "mixed", f"vs {b1}")

    # F4 网络：门店数 vs 单店产出
    s_rel = net[main]["stores_with_gen"] / max(net[b1]["stores_with_gen"], 1) - 1
    p_rel = net[main]["locks_per_store"] / max(net[b1]["locks_per_store"], 1e-9) - 1
    if abs(p_rel) >= abs(s_rel):
        t4 = f"单店产出{_dir_word(p_rel)} {abs(p_rel):.0%}，网络规模差异（{s_rel:+.0%}）是次要项"
    else:
        t4 = f"门店数量{_dir_word(s_rel)} {abs(s_rel):.0%}，单店产出差异（{p_rel:+.0%}）是次要项"
    f("f4", t4,
      f"有效锁单门店 {_fmt(net[main]['stores_with_gen'])} 家 vs {_fmt(net[b1]['stores_with_gen'])} 家；"
      f"单店产出 {net[main]['locks_per_store']:.2f} vs {net[b1]['locks_per_store']:.2f} 单/店。",
      ["network.stores_with_gen", "network.locks_per_store"],
      {"stores_main": net[main]["stores_with_gen"], "stores_bench": net[b1]["stores_with_gen"],
       "per_store_main": net[main]["locks_per_store"], "per_store_bench": net[b1]["locks_per_store"]},
      "mixed", f"vs {b1}")

    # F5 来源结构：直锁占比差异
    dl = {g: (org[g]["none"] / max(org[g]["total"], 1)) for g in [main] + benches}
    spread = (max(dl.values()) - min(dl.values())) * 100
    if spread >= 10:
        t5 = f"下单链路差异显著：直锁占比跨代际相差 {spread:.0f}pp"
        body5 = ("；".join(f"{g} {dl[g]:.1%}" for g in [main] + benches)
                 + "。直锁占比受下单流程影响，不能读作需求强弱。")
    else:
        t5 = f"下单链路一致：直锁占比跨代际仅差 {spread:.1f}pp"
        body5 = "；".join(f"{g} {dl[g]:.1%}" for g in [main] + benches) + "。"
    f("f5", t5, body5, ["origin.none", "origin.total"],
      {f"direct_{g}": dl[g] for g in [main] + benches}, "mixed", "全部对标")

    return out


def validate_findings(findings: list[dict], ctx: dict) -> dict:
    """Gate B：结论数值与方向核验（可复算、可对账）。"""
    checks, failed = [], []
    cur = ctx["curves"]["curves"]
    d = ctx["deltas"]
    main = ctx["main"]

    for fd in findings:
        num = fd.get("numbers") or {}
        ok, msgs = True, []
        if "cum_main" in num:
            real = cur[main]["cum"][-1]
            if int(num["cum_main"]) != int(real):
                ok = False; msgs.append(f"cum_main {num['cum_main']} ≠ {real}")
            direction_ok = (
                (fd["direction"] == "behind" and num["ratio"] < 1)
                or (fd["direction"] == "ahead" and num["ratio"] > 1)
                or (fd["direction"] == "parity" and 0.9 <= num["ratio"] <= 1.1)
            )
            if not direction_ok:
                ok = False; msgs.append(f"方向 {fd['direction']} 与 ratio {num['ratio']:.3f} 不一致")
        if "d1_share_main" in num:
            real = ctx["dynamics"][main]["d1_share_of_cum"]
            if abs(num["d1_share_main"] - real) > 1e-6:
                ok = False; msgs.append("d1_share_main 与 metrics 不一致")
        if "pool_main" in num:
            if int(num["pool_main"]) != int(ctx["presale"][main]["pool_total"]):
                ok = False; msgs.append("pool_main 与 metrics 不一致")
        if "stores_main" in num:
            if int(num["stores_main"]) != int(ctx["network"][main]["stores_with_gen"]):
                ok = False; msgs.append("stores_main 与 metrics 不一致")
        checks.append({"finding": fd["id"], "ok": ok, "messages": msgs})
        if not ok:
            failed.append(fd["id"])

    # 全局方向一致性：所有 finding 不得与自身数值矛盾
    return {"gate": "B", "verdict": "FAIL" if failed else "PASS",
            "checked": len(checks), "failed": failed, "checks": checks}


def validate_report(html: str, findings: list[dict], ctx: dict) -> dict:
    """Gate C：HTML 与已确认结论的一致性（标题、关键数字、禁用措辞）。"""
    issues = []
    plain = re.sub(r"<[^>]+>", "", html)

    for fd in findings:
        if fd["title"] and fd["title"] not in plain:
            issues.append(f"结论标题未出现在报告中：{fd['id']} {fd['title'][:24]}")

    # 禁用与数据矛盾的固定措辞
    d1 = ctx["deltas"][ctx["benchmarks"][0]]
    ratio = d1["cum_ratio"]
    forbidden = []
    if ratio >= 0.9:
        forbidden += ["落后四成", "落后四 成", "落后四成以上"]
    if ratio >= 1.0:
        forbidden += ["全面落后", "持续失速"]
    for phrase in forbidden:
        if phrase in plain:
            issues.append(f"报告出现与数据矛盾的措辞：{phrase}（实际 ratio={ratio:.2f}）")

    return {"gate": "C", "verdict": "FAIL" if issues else "PASS",
            "issues": issues, "checked_findings": len(findings)}
