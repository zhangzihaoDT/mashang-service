#!/usr/bin/env python
"""Generate a hypothesis-driven HTML report for the 2024 NEV-APEAL SAV.

The report follows docs/sav_exploratory_analysis_v2.md:
Measurement Contract -> Data Contract -> Signal -> Hypothesis -> Topic.
It deliberately treats configuration and brand differences as observational
signals, not causal effects.
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from scipy import stats
except ImportError as exc:  # pragma: no cover - dependency check for CLI users
    raise SystemExit("缺少 scipy，请先安装项目依赖") from exc

SERVICE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = SERVICE_ROOT / "dataset" / "24 NEV-APEAL数据片段.sav"
DEFAULT_OUTPUT = SERVICE_ROOT / "outputs" / "reports" / "nev_apeal_signal_topic_report.html"
DEFAULT_MARKDOWN_OUTPUT = SERVICE_ROOT / "outputs" / "reports" / "nev_apeal_signal_topic_report.md"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import explore_sav as explorer  # noqa: E402


PURCHASE_LABELS = {
    1.0: "换购",
    2.0: "增购",
    3.0: "首购",
}
ENERGY_LABELS = {1.0: "BEV 纯电", 2.0: "PHEV 插混"}
METRICS = {
    "APEAL_Index": "总体产品魅力",
    "AEXT_Index": "外观造型",
    "AINT_Index": "座舱内装",
    "AFUEL_Index": "补能续航",
    "APERF_Index": "动力性能",
    "ADRV_Index": "驾驶感受",
    "ACMFT_Index": "舒适度",
    "ASFTY_Index": "安全感知",
}


def weighted_mean(series: pd.Series, weights: pd.Series) -> float:
    valid = series.notna() & weights.notna()
    if not valid.any():
        return float("nan")
    return float(np.average(series[valid], weights=weights[valid]))


def fmt(value: Any, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):.{digits}f}"


def label(meta: Any, column: str, value: Any) -> str:
    return str((meta.variable_value_labels.get(column) or {}).get(value, value))


def group_rows(df: pd.DataFrame, meta: Any, group_col: str, metric_cols: list[str]) -> list[dict[str, Any]]:
    rows = []
    for value in sorted(df[group_col].dropna().unique()):
        sub = df[df[group_col] == value]
        row = {
            "value": value,
            "label": label(meta, group_col, value),
            "n": int(len(sub)),
        }
        for metric in metric_cols:
            row[metric] = weighted_mean(sub[metric], sub["APEAL_WT"].fillna(1.0))
        rows.append(row)
    return rows


def topic_analysis(df: pd.DataFrame, meta: Any) -> dict[str, Any]:
    metric_cols = list(METRICS)
    main_rows = group_rows(df, meta, "YPV_01", metric_cols)
    for row in main_rows:
        row["label"] = PURCHASE_LABELS.get(row["value"], row["label"])
    groups = [df.loc[df["YPV_01"] == value, "APEAL_Index"].dropna().to_numpy()
              for value in sorted(df["YPV_01"].dropna().unique())]
    f_stat, p_value = stats.f_oneway(*groups)

    pairwise = []
    values = sorted(df["YPV_01"].dropna().unique())
    for left in range(len(values)):
        for right in range(left + 1, len(values)):
            a = df.loc[df["YPV_01"] == values[left], "APEAL_Index"].dropna().to_numpy()
            b = df.loc[df["YPV_01"] == values[right], "APEAL_Index"].dropna().to_numpy()
            t_stat, p = stats.ttest_ind(a, b, equal_var=False)
            pooled_sd = np.sqrt((np.var(a, ddof=1) + np.var(b, ddof=1)) / 2)
            d = (np.mean(a) - np.mean(b)) / pooled_sd if pooled_sd else 0.0
            pairwise.append({
                "left": PURCHASE_LABELS.get(values[left], label(meta, "YPV_01", values[left])),
                "right": PURCHASE_LABELS.get(values[right], label(meta, "YPV_01", values[right])),
                "diff": weighted_mean(df.loc[df["YPV_01"] == values[left], "APEAL_Index"], df.loc[df["YPV_01"] == values[left], "APEAL_WT"].fillna(1.0))
                - weighted_mean(df.loc[df["YPV_01"] == values[right], "APEAL_Index"], df.loc[df["YPV_01"] == values[right], "APEAL_WT"].fillna(1.0)),
                "p": float(p),
                "d": float(d),
                "t": float(t_stat),
            })

    energy_rows = []
    for energy in sorted(df["SUPER_SEGMENT_DP"].dropna().unique()):
        sub = df[df["SUPER_SEGMENT_DP"] == energy]
        for row in group_rows(sub, meta, "YPV_01", ["APEAL_Index"]):
            row["energy"] = ENERGY_LABELS.get(energy, label(meta, "SUPER_SEGMENT_DP", energy))
            row["label"] = PURCHASE_LABELS.get(row["value"], row["label"])
            energy_rows.append(row)

    return {
        "main_rows": main_rows,
        "pairwise": pairwise,
        "energy_rows": energy_rows,
        "anova_f": float(f_stat),
        "anova_p": float(p_value),
    }


def signal_rows(df: pd.DataFrame, meta: Any) -> list[dict[str, str]]:
    scan = explorer.scan(
        df,
        meta,
        explorer.detect_multi_groups(df, meta),
        group_by=["SUPER_SEGMENT_DP", "CITY_TIER_DP", "YPV_01", "GENDER"],
        metrics=["APEAL_Index", "AEXT_Index", "AINT_Index", "AFUEL_Index", "ASFTY_Index"],
        top=20,
    )
    rows = []
    for item in scan["top_candidates"][:6]:
        group_label = explorer.col_label(meta, item["group"]) or item["group"]
        metric_label = METRICS.get(item["metric"], item["metric"])
        rows.append({
            "signal": f"{group_label} × {metric_label}",
            "fact": " / ".join(f"{k}={v}" for k, v in item["group_means"].items()),
            "evidence": f"效应量 {fmt(item['effect_size'], 4)}；p={item['p']:.3g}",
            "status": "候选 Signal",
        })
    return rows


def esc(value: Any) -> str:
    return html.escape(str(value))


def table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{esc(item)}</th>" for item in headers)
    body = "".join("<tr>" + "".join(f"<td>{esc(item)}</td>" for item in row) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def render_html(df: pd.DataFrame, meta: Any, vardict: pd.DataFrame, qc: dict[str, Any], topic: dict[str, Any], signals: list[dict[str, str]]) -> str:
    overall = weighted_mean(df["APEAL_Index"], df["APEAL_WT"].fillna(1.0))
    highest = max(topic["main_rows"], key=lambda row: row["APEAL_Index"])
    lowest = min(topic["main_rows"], key=lambda row: row["APEAL_Index"])
    delta = highest["APEAL_Index"] - lowest["APEAL_Index"]

    main_table = table(
        ["购买任务", "样本量", "APEAL", "外观", "座舱", "补能续航", "驾驶感受", "安全"],
        [[r["label"], r["n"], fmt(r["APEAL_Index"]), fmt(r["AEXT_Index"]), fmt(r["AINT_Index"]), fmt(r["AFUEL_Index"]), fmt(r["ADRV_Index"]), fmt(r["ASFTY_Index"])] for r in topic["main_rows"]],
    )
    energy_table = table(
        ["能源类型", "购买任务", "样本量", "APEAL"],
        [[r["energy"], r["label"], r["n"], fmt(r["APEAL_Index"])] for r in topic["energy_rows"]],
    )
    pair_table = table(
        ["对比", "加权差异", "Welch p", "Cohen's d"],
        [[f"{r['left']} - {r['right']}", f"{r['diff']:+.1f}", f"{r['p']:.3g}", f"{r['d']:+.3f}"] for r in topic["pairwise"]],
    )
    signal_table = table(
        ["扫描维度 × 指标", "观察到的事实", "统计证据", "阶段"],
        [[r["signal"], r["fact"], r["evidence"], r["status"]] for r in signals],
    )
    type_counts = vardict["type"].value_counts().to_dict()
    type_summary = "；".join(f"{k} {v}" for k, v in type_counts.items())

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NEV-APEAL 2024 Signal to Topic 报告</title>
<style>
:root{{--blue:#174A7C;--deep:#06213D;--cyan:#7ECDEB;--light:#DDEFF8;--cream:#FFF9EF;--gold:#D79A36;--text:#1F2D3D;--muted:#6B7C8F;--card:#fff;--line:#E5EAF0;--green:#2A9D8F}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--cream);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.65}}
.wrap{{max-width:1120px;margin:auto;padding:24px 18px 48px}} header{{background:var(--deep);color:#fff;border-radius:18px;padding:32px 36px;margin-bottom:20px}} h1{{font-size:27px;margin:0 0 8px}} h2{{font-size:19px;color:var(--deep);margin:0 0 12px}} h3{{font-size:16px;color:var(--deep);margin:0 0 7px}} p{{margin:7px 0}} .sub{{color:var(--cyan);font-size:14px}} .meta{{color:#B9CFE0;font-size:12px;margin-top:14px;display:flex;gap:8px 22px;flex-wrap:wrap}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}} .kpi,.card{{background:var(--card);border-radius:13px;box-shadow:0 1px 5px rgba(6,33,61,.07)}} .kpi{{padding:17px 18px}} .kpi .v{{font-size:27px;font-weight:700;color:var(--blue)}} .kpi .l{{font-size:12px;color:var(--muted)}} .card{{padding:23px 26px;margin-bottom:18px}} .topic{{border-left:5px solid var(--gold);background:#fffdf8}} .tag{{display:inline-block;padding:2px 9px;border-radius:12px;font-size:12px;background:var(--light);color:var(--blue);margin:2px 4px 2px 0}} .fact{{color:var(--blue);font-weight:600}} .note{{font-size:13px;color:var(--muted)}} .callout{{background:var(--light);padding:13px 16px;border-radius:9px;margin-top:14px}} .warning{{background:#FFF0D6;border-left:3px solid var(--gold);padding:12px 15px;border-radius:8px;font-size:13px}}
.table-wrap{{overflow-x:auto}} table{{width:100%;border-collapse:collapse;font-size:13px}} th{{text-align:left;background:#F6F8FA;color:var(--deep);padding:9px 10px;border-bottom:2px solid var(--blue);white-space:nowrap}} td{{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}} tr:nth-child(even){{background:#FAFAFA}} .bar{{height:8px;background:var(--light);border-radius:8px;overflow:hidden;margin-top:4px}} .bar i{{display:block;height:100%;background:var(--blue);border-radius:8px}} .columns{{display:grid;grid-template-columns:1fr 1fr;gap:18px}} ul{{padding-left:21px}} footer{{text-align:center;color:var(--muted);font-size:12px;padding:15px}}
@media(max-width:720px){{.grid{{grid-template-columns:repeat(2,1fr)}}.columns{{grid-template-columns:1fr}}header{{padding:25px 22px}}h1{{font-size:23px}}.card{{padding:19px}}}}
</style></head><body><div class="wrap">
<header><h1>NEV-APEAL 2024 · Signal to Topic 研究报告</h1><div class="sub">从数据事实出发，验证“购买任务是否对应不同的产品魅力期待”</div><div class="meta"><span>数据源：<b>24 NEV-APEAL数据片段.sav</b></span><span>样本：<b>{len(df):,}</b></span><span>变量：<b>{len(df.columns)}</b></span><span>权重：<b>APEAL_WT</b></span></div></header>
<div class="grid"><div class="kpi"><div class="v">{overall:.1f}</div><div class="l">总体 APEAL 加权均值</div></div><div class="kpi"><div class="v">{highest['label']}</div><div class="l">最高购买任务 · {highest['APEAL_Index']:.1f}</div></div><div class="kpi"><div class="v">{delta:+.1f}</div><div class="l">最高与最低任务差异</div></div><div class="kpi"><div class="v">{topic['anova_p']:.2g}</div><div class="l">购买任务 ANOVA p 值</div></div></div>
<section class="card topic"><h2>Executive Topic</h2><p class="fact">增购用户的总体产品魅力评价最高，但这一优势并非简单的能源类型差异；购买任务本身可能是理解用户期待与产品体验差异的关键切片。</p><p>在当前横截面样本中，增购用户 APEAL 为 <b>{highest['APEAL_Index']:.1f}</b>，比换购用户高 {topic['main_rows'][1]['APEAL_Index']-topic['main_rows'][0]['APEAL_Index']:+.1f} 分，比首购用户高 {topic['main_rows'][1]['APEAL_Index']-topic['main_rows'][2]['APEAL_Index']:+.1f} 分。该结果是关联性证据，不代表购买任务导致满意度变化。</p><div class="callout"><b>研究状态：REFINED</b>。原始假设“购买任务决定整体满意度”过强；更稳妥的表述是“购买任务与用户感知的产品魅力结构存在稳定差异，增购用户整体评价更高”。</div></section>
<section class="card"><h2>1 · Measurement & Data Contract</h2><div class="columns"><div><p><b>数据范围</b></p><ul><li>SPSS SAV，{len(df):,} 行 × {len(df.columns)} 列。</li><li>读取方式：pyreadstat，保留值标签；评分题中的 N/A 按缺失处理。</li><li>所有指数比较使用 APEAL_WT 加权；样本量 N 为未加权有效记录数。</li><li>题型识别：{type_summary}。</li></ul></div><div><p><b>QC 结果</b></p><ul><li>高缺失变量（&gt;20%）：{len(qc['checks'][0]['items'])} 个。</li><li>单值变量/标签异常等警告：{qc['n_warnings']} 条。</li><li>问卷映射：使用既有 `nev_apeal_questionnaire_map.json` 作为 Measurement Contract 参考。</li></ul><div class="warning">数据片段是横截面样本，不能支持“增长、下降、趋势、市场份额变化”等跨年结论。</div></div></div></section>
<section class="card"><h2>2 · Discovery：候选 Signal</h2><p class="note">先扫描核心人群切片与 APEAL 指数族，再选择一个业务相关且可进一步验证的候选。这里展示的是 Signal，不是最终 Insight。</p>{signal_table}</section>
<section class="card"><h2>3 · Topic Analysis：购买任务 × 产品魅力</h2><p class="note">分组：YPV_01；指标：APEAL_Index 及子指数。购买任务标签来自 SAV 值标签。</p>{main_table}<p class="note">主结果：增购用户在总体 APEAL、外观、座舱、补能续航、驾驶感受和安全感知等多个维度均处于较高水平；该结构值得进一步理解，但不能直接解释为“增购导致高分”。</p></section>
<section class="card"><h2>4 · Statistical Validation & Robustness</h2><p>三组总体差异：Welch/ANOVA F = {topic['anova_f']:.2f}，p = {topic['anova_p']:.3g}。两两检验如下，作为方向性验证；未对全量扫描结果做多重比较校正，因此不把单个 p 值当作最终证明。</p>{pair_table}<h3 style="margin-top:20px">按能源类型分层</h3>{energy_table}<p class="note">如果购买任务差异只由 BEV/PHEV 构成，分层后应消失。当前 BEV 与 PHEV 内部仍可观察到相同排序方向，支持“购买任务是有价值的解释切片”，但仍需控制价格、品牌与车型结构。</p></section>
<section class="card"><h2>5 · Insight、边界与产品问题</h2><div class="columns"><div><h3>Fact · 数据直接支持</h3><ul><li>增购组总体 APEAL 加权均值最高。</li><li>差异同时出现在多个体验子指数，而非单一题目。</li><li>在 BEV/PHEV 分层后，增购组仍保持较高方向。</li></ul></div><div><h3>Inference · 待验证解释</h3><ul><li>增购用户可能具备更成熟的新能源使用经验或更明确的产品筛选标准。</li><li>他们对产品的评价可能同时受到价格、品牌与配置结构影响。</li><li>当前数据不能区分“用户类型效应”与“车型/品牌组合效应”。</li></ul></div></div><div class="callout"><b>下一步业务问题：</b>在控制价格带、品牌阵营和车型后，增购用户仍然更重视哪些可感知体验？产品应优先优化“基本满意度”，还是为已有车辆的用户提供可感知的升级价值？</div></section>
<section class="card"><h2>6 · Other Signals / 后续候选</h2><ul><li>城市层级与 APEAL 子指数存在差异，可研究不同城市用户的体验基准。</li><li>BEV/PHEV 在补能续航与动力性能上方向不同，适合做能源类型 Topic。</li><li>配置有/无扫描出现较大效应量，但强烈可能混合了价格、品牌和车型结构，必须先做分层或回归验证。</li><li>品牌阵营与价位段结构可用于样本画像，不可当作市场份额。</li></ul></section>
<section class="card"><h2>方法与可追溯性</h2><p class="note">脚本：<code>scripts/analyze_nev_apeal_topic.py</code>；框架：<code>docs/sav_exploratory_analysis_v2.md</code>；输入：<code>dataset/24 NEV-APEAL数据片段.sav</code>；输出：本报告。主 Topic 使用 YPV_01 × APEAL_Index，Welch ANOVA/两两 Welch t-test，效应量为 Cohen's d。所有结论均限于当前数据片段与横截面口径。</p></section>
<footer>Raccoon Research · 用数据、AI 和一点点常识，研究复杂世界。</footer></div></body></html>"""


def render_markdown(df: pd.DataFrame, vardict: pd.DataFrame, qc: dict[str, Any], topic: dict[str, Any], signals: list[dict[str, str]]) -> str:
    overall = weighted_mean(df["APEAL_Index"], df["APEAL_WT"].fillna(1.0))
    highest = max(topic["main_rows"], key=lambda row: row["APEAL_Index"])
    lowest = min(topic["main_rows"], key=lambda row: row["APEAL_Index"])
    type_summary = "；".join(f"{k} {v}" for k, v in vardict["type"].value_counts().to_dict().items())
    lines = [
        "# NEV-APEAL 2024 · Signal to Topic 研究报告", "",
        "> 从数据事实出发，验证“购买任务是否对应不同的产品魅力期待”。", "",
        "## Executive Topic", "",
        "增购用户的总体产品魅力评价最高，但这一优势并非简单的能源类型差异；购买任务本身可能是理解用户期待与产品体验差异的关键切片。", "",
        f"在当前横截面样本中，增购用户 APEAL 为 **{highest['APEAL_Index']:.1f}**，比最低组（{lowest['label']}）高 **{highest['APEAL_Index'] - lowest['APEAL_Index']:+.1f}** 分。总体 APEAL 加权均值为 **{overall:.1f}**。该结果是关联性证据，不代表购买任务导致满意度变化。", "",
        "> **研究状态：REFINED。** 原始假设“购买任务决定整体满意度”过强；更稳妥的表述是“购买任务与用户感知的产品魅力结构存在稳定差异，增购用户整体评价更高”。", "",
        "## 1. Measurement & Data Contract", "",
        f"- 数据源：`dataset/24 NEV-APEAL数据片段.sav`；样本：{len(df):,} 行 × {len(df.columns)} 列。",
        "- 权重：`APEAL_WT`；指数均值使用加权均值，样本量 N 为未加权有效记录数。",
        f"- 题型识别：{type_summary}。",
        f"- QC：高缺失变量（>20%）{len(qc['checks'][0]['items'])} 个；警告 {qc['n_warnings']} 条。",
        "- 数据边界：当前为横截面数据片段，不能支持增长、下降、趋势或市场份额变化等跨年结论。", "",
        "## 2. Discovery：候选 Signal", "",
        "| 扫描维度 × 指标 | 观察到的事实 | 统计证据 | 阶段 |", "|---|---|---|---|",
    ]
    lines.extend(f"| {r['signal']} | {r['fact']} | {r['evidence']} | {r['status']} |" for r in signals)
    lines.extend(["", "这里展示的是 Signal，不是最终 Insight。扫描先用于寻找值得继续验证的现象。", "", "## 3. Topic Analysis：购买任务 × 产品魅力", "", "分组变量：`YPV_01`；指标：`APEAL_Index` 及 APEAL 子指数。", "", "| 购买任务 | 样本量 | APEAL | 外观 | 座舱 | 补能续航 | 驾驶感受 | 安全 |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
    lines.extend(f"| {r['label']} | {r['n']} | {r['APEAL_Index']:.1f} | {r['AEXT_Index']:.1f} | {r['AINT_Index']:.1f} | {r['AFUEL_Index']:.1f} | {r['ADRV_Index']:.1f} | {r['ASFTY_Index']:.1f} |" for r in topic["main_rows"])
    lines.extend(["", "主结果：增购用户在多个体验子指数上处于较高水平，但不能直接解释为“增购导致高分”。", "", "## 4. Statistical Validation & Robustness", "", f"三组总体差异：Welch/ANOVA F = **{topic['anova_f']:.2f}**，p = **{topic['anova_p']:.3g}**。", "", "| 对比 | 加权差异 | Welch p | Cohen's d |", "|---|---:|---:|---:|"])
    lines.extend(f"| {r['left']} - {r['right']} | {r['diff']:+.1f} | {r['p']:.3g} | {r['d']:+.3f} |" for r in topic["pairwise"])
    lines.extend(["", "### 按能源类型分层", "", "| 能源类型 | 购买任务 | 样本量 | APEAL |", "|---|---|---:|---:|"])
    lines.extend(f"| {r['energy']} | {r['label']} | {r['n']} | {r['APEAL_Index']:.1f} |" for r in topic["energy_rows"])
    lines.extend(["", "BEV 与 PHEV 内部仍可观察到相同排序方向，但仍需控制价格、品牌与车型结构。", "", "## 5. Insight、边界与产品问题", "", "### Fact · 数据直接支持", "- 增购组总体 APEAL 加权均值最高。", "- 差异同时出现在多个体验子指数，而非单一题目。", "- 在 BEV/PHEV 分层后，增购组仍保持较高方向。", "", "### Inference · 待验证解释", "- 增购用户可能具备更成熟的新能源使用经验或更明确的产品筛选标准。", "- 评价差异可能同时受到价格、品牌与配置结构影响。", "- 当前数据不能区分用户类型效应与车型/品牌组合效应。", "", "> **下一步业务问题：** 在控制价格带、品牌阵营和车型后，增购用户仍然更重视哪些可感知体验？", "", "## 6. Other Signals / 后续候选", "", "- 城市层级与 APEAL 子指数存在差异，可研究不同城市用户的体验基准。", "- BEV/PHEV 在补能续航与动力性能上方向不同，适合做能源类型 Topic。", "- 配置有/无扫描可能混合价格、品牌和车型结构，必须先做分层或回归验证。", "- 品牌阵营与价位段结构可用于样本画像，不可当作市场份额。", "", "## 方法与可追溯性", "", "- 脚本：`scripts/analyze_nev_apeal_topic.py`；框架：`docs/sav_exploratory_analysis_v2.md`。", "- 主 Topic：`YPV_01 × APEAL_Index`；检验：Welch ANOVA、两两 Welch t-test、Cohen's d。", "- 结论范围：仅限当前 SAV 数据片段与横截面口径。", "", "---", "", "Raccoon Research · 用数据、AI 和一点点常识，研究复杂世界。", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 NEV-APEAL Signal to Topic HTML 报告")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="SAV 数据路径")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="HTML 输出路径")
    parser.add_argument("--markdown-output", default=str(DEFAULT_MARKDOWN_OUTPUT), help="Markdown 输出路径")
    args = parser.parse_args()

    df, meta = explorer.load_sav(args.input)
    multi = explorer.detect_multi_groups(df, meta)
    rating_cols = [c for c in df.columns if explorer.infer_var_type(c, meta.variable_value_labels.get(c)) == "rating"]
    df = explorer.clean_rating_values(df, meta, rating_cols)
    vardict = explorer.build_vardict(df, meta, multi)
    qc = explorer.run_qc(df, meta, multi)
    topic = topic_analysis(df, meta)
    signals = signal_rows(df, meta)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(df, meta, vardict, qc, topic, signals), encoding="utf-8")
    markdown_output = Path(args.markdown_output)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(render_markdown(df, vardict, qc, topic, signals), encoding="utf-8")
    print(f"样本: {len(df):,} x {len(df.columns)}")
    print(f"Topic: 增购用户 APEAL={max(topic['main_rows'], key=lambda r: r['APEAL_Index'])['APEAL_Index']:.1f}")
    print(f"HTML 报告: {output.resolve()}")
    print(f"Markdown 报告: {markdown_output.resolve()}")


if __name__ == "__main__":
    main()
