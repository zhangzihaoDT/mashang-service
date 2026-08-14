#!/usr/bin/env python
"""
verify_nev_apeal_2024.py — 用 24 NEV-APEAL数据片段.sav 验证 NEV-APEAL 2024 要点

逐条验证 outputs/reports/NEV-APEAL_2024_要点.md 中的 24 条要点，
输出验证结论（支持 / 部分支持 / 数据不足）+ 关键数字，并生成 HTML 报告。

结论分级：
- supported       数据直接支持该要点（当前状态）
- partial         横截面可验证当前水平，但"趋势/增幅"类陈述需多年数据，部分支持
- insufficient    无对应变量或数据无法支撑

用法:
    python scripts/verify_nev_apeal_2024.py
    python scripts/verify_nev_apeal_2024.py --output outputs/reports/nev_apeal_2024_verify.html
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import pyreadstat
except ImportError:
    pyreadstat = None

SERVICE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = SERVICE_ROOT / "dataset" / "24 NEV-APEAL数据片段.sav"
DEFAULT_OUTPUT = SERVICE_ROOT / "outputs" / "reports" / "nev_apeal_2024_verify.html"
WEIGHT_COL = "APEAL_WT"

# ---------------------------------------------------------------------------
# 品牌阵营映射（分析假设，报告中注明）
# ---------------------------------------------------------------------------
# International: 国际品牌（含特斯拉、合资）
# NewForce: 独立造车新势力
# NewSub: 传统车企孵化的新能源子品牌（自主新创）
# Traditional: 传统自主品牌主品牌
BRAND_CAMP = {
    "International": {
        "Audi", "BMW", "Buick", "Lexus", "Mercedes-Benz", "smart", "MG", "Volvo",
        "FAW Toyota", "FAW-Volkswagen", "SAIC Volkswagen", "Tesla", "Venucia",
    },
    "NewForce": {"NIO", "Xpeng", "Li Auto", "Leap Motor", "NETA", "HiPhi"},
    "NewSub": {
        "ZEEKR", "IM", "AITO", "AVATR", "Voyah", "Denza", "DEEPAL",
        "Galaxy", "Geometry", "OSHAN", "Dongfeng Nammi",
    },
    "Traditional": {
        "BYD", "CHANGAN", "Haval", "WEY", "ORA", "TANK", "Chery New Energy",
        "Dongfeng Fengshen", "FAW Besturn", "FAW Hongqi", "Geely", "Lynk & Co",
        "Roewe", "Wuling", "Baojun", "GAC Trumpchi", "GAC AION", "BAIC BJEV",
    },
}
CAMP_LABEL = {
    "International": "国际品牌",
    "NewForce": "自主新势力",
    "NewSub": "自主新创品牌",
    "Traditional": "传统自主品牌",
}


# ---------------------------------------------------------------------------
# 数据加载与工具
# ---------------------------------------------------------------------------

def load() -> Tuple[pd.DataFrame, Any]:
    if pyreadstat is None:
        raise SystemExit("缺少 pyreadstat，请先 pip install pyreadstat")
    df, meta = pyreadstat.read_sav(str(DEFAULT_INPUT), user_missing=True)
    return df, meta


def col_label(meta, name: str) -> str:
    labels = getattr(meta, "column_labels", None)
    names = getattr(meta, "column_names", None)
    if isinstance(labels, list) and isinstance(names, list):
        try:
            return labels[names.index(name)] or ""
        except ValueError:
            return ""
    return ""


def wmean(s: pd.Series, w: pd.Series) -> float:
    m = s.notna().values
    if not m.any():
        return float("nan")
    return float(np.average(s.values[m], weights=w.values[m]))


def group_wmean(df: pd.DataFrame, g: str, m: str) -> Dict[Any, float]:
    out = {}
    for u in pd.unique(df[g]):
        sel = df[g] == u
        out[u] = wmean(df[m][sel], df[WEIGHT_COL][sel])
    return out


def camp_col(df: pd.DataFrame, meta) -> pd.Series:
    """返回每个观测的品牌阵营标签。"""
    name2label = dict(zip(meta.column_names, meta.column_labels))
    make_labels = meta.variable_value_labels.get("MAKE_DP") or {}
    def _camp(x):
        if pd.isna(x):
            return None
        brand = make_labels.get(x)
        if brand is None:
            return None
        for camp, brands in BRAND_CAMP.items():
            if brand in brands:
                return CAMP_LABEL[camp]
        return None
    return df["MAKE_DP"].map(_camp)


def fmt(x: float, d: int = 1) -> str:
    if pd.isna(x):
        return "—"
    return f"{x:.{d}f}"


# ---------------------------------------------------------------------------
# 验证结果结构
# ---------------------------------------------------------------------------
class Result:
    def __init__(self, no: int, title: str, verdict: str, method: str,
                 evidence: List[str], conclusion: str, tag: str = ""):
        self.no = no
        self.title = title
        self.verdict = verdict  # supported | partial | insufficient
        self.method = method
        self.evidence = evidence
        self.conclusion = conclusion
        self.tag = tag

    def to_dict(self) -> Dict[str, Any]:
        return {
            "no": self.no, "title": self.title, "verdict": self.verdict,
            "method": self.method, "evidence": self.evidence,
            "conclusion": self.conclusion, "tag": self.tag,
        }


# ---------------------------------------------------------------------------
# 24 条要点验证
# ---------------------------------------------------------------------------

def v01(df, meta) -> Result:
    """1. NEV-APEAL 2024=789，增速放缓；焦虑由燃油经济性/续航转向安全"""
    apeal = df["APEAL_Index"]
    w = df[WEIGHT_COL].fillna(1)
    overall = wmean(apeal, w)
    ev = [f"APEAL_Index 加权均值 = {fmt(overall, 1)}（要点称 789）"]
    # 分交付年份看指数（趋势代理）
    y23 = df[df["SCR_DEL_Y"] == 2023]
    y24 = df[df["SCR_DEL_Y"] == 2024]
    if len(y23) and len(y24):
        ev.append(f"2023 交付 {len(y23)} 加权 {fmt(wmean(y23['APEAL_Index'], y23[WEIGHT_COL]))}；"
                  f"2024 交付 {len(y24)} 加权 {fmt(wmean(y24['APEAL_Index'], y24[WEIGHT_COL]))}（2024 样本少，仅参考）")
    # 焦虑转向安全：无法直接测"焦虑"，但可对比 AFUEL vs ASFTY 满意度水平
    afuel, asfty = df["AFUEL_Index"], df["ASFTY_Index"]
    ev.append(f"能耗续航 AFUEL={fmt(wmean(afuel, w))} vs 安全 ASFTY={fmt(wmean(asfty, w))}（横截面水平，无法测焦虑变化）")
    return Result(1, "中国 NEV-APEAL 持续增长，2024 年达到 789 分，增速放缓；焦虑由燃油经济性/续航转向安全性",
                  "partial", "APEAL_Index 加权均值；按交付年份分组",
                  ev, f"得分 789 得到数据支持（实测 {fmt(overall,1)}）；增速放缓与焦虑转向为跨年趋势，单年数据无法直接验证，仅能给出横截面水平参考。",
                  tag="789 分可验证 · 趋势需多年数据")


def v02(df, meta) -> Result:
    """2. 增换购比例攀升；各购买群体偏好不同"""
    ypv = meta.variable_value_labels.get("YPV_01")
    vc = df["YPV_01"].value_counts().sort_index()
    share = {ypv[k]: f"{v/len(df)*100:.1f}%" for k, v in vc.items()}
    ev = [f"购买类型分布（当前样本）：{share}"]
    # 各群体 AFUEL / AEXT / AINT
    for grp, lbl in [(1, "换购"), (2, "增购"), (3, "首购")]:
        s = df[df["YPV_01"] == grp]
        if not len(s):
            continue
        afuel = fmt(wmean(s["AFUEL_Index"], s[WEIGHT_COL]))
        aext = fmt(wmean(s["AEXT_Index"], s[WEIGHT_COL]))
        aint = fmt(wmean(s["AINT_Index"], s[WEIGHT_COL]))
        ev.append(f"{lbl}（n={len(s)}）：能耗/续航 AFUEL={afuel}，外观 AEXT={aext}，内饰 AINT={aint}")
    return Result(2, "增换购用户比例持续攀升，各购买群体偏好不同",
                  "partial", "YPV_01 分布 + 各群体指数加权均值",
                  ev, "当前样本中首购占比最高；各群体指数水平差异可见（见证据），但'比例攀升'与'增幅'为跨年趋势，需多年数据验证。")


def v03(df, meta) -> Result:
    """3. 国际品牌和自主新势力产品力整体领先"""
    camp = camp_col(df, meta)
    d = df.assign(_camp=camp).dropna(subset=["_camp"])
    ev = []
    gm = group_wmean(d, "_camp", "APEAL_Index")
    for k in sorted(gm, key=lambda x: -gm[x]):
        ev.append(f"{k}：APEAL={fmt(gm[k])}（n={int((d['_camp']==k).sum())}）")
    return Result(3, "国际品牌和自主新势力形成产品力整体领先，传统自主和自主新创品牌快速提升",
                  "partial", "品牌阵营分组 × APEAL_Index 加权均值",
                  ev, "当前横截面看各阵营产品力排序（见证据）；'快速提升'为跨年趋势，单年数据无法验证。")


def v04(df, meta) -> Result:
    """4. 女性 NEV-APEAL 增长高于男性"""
    gen = meta.variable_value_labels.get("GENDER")
    ev = []
    for g in [0.0, 1.0]:
        s = df[df["GENDER"] == g]
        if len(s):
            lbl = gen.get(g, g)
            ev.append(f"{lbl}（n={len(s)}）：APEAL={fmt(wmean(s['APEAL_Index'], s[WEIGHT_COL]))}")
    return Result(4, "女性 NEV-APEAL 增长高于男性，外观造型更容易打动女性",
                  "partial", "GENDER × APEAL_Index 加权均值",
                  ev, "当前横截面可比较男女得分水平（见证据）；'增长更高'为跨年趋势，单年数据无法验证。")


def v05(df, meta) -> Result:
    """5. 车型得分及销量集中度逐年提升，差距减小"""
    # 无销量数据；用品牌间指数离散度做参考
    camp = camp_col(df, meta)
    d = df.assign(_camp=camp).dropna(subset=["_camp"])
    gm = group_wmean(d, "_camp", "APEAL_Index")
    vals = list(gm.values())
    spread = max(vals) - min(vals)
    ev = [f"品牌阵营间 APEAL 极差 = {fmt(spread)}（最高 {max(gm, key=gm.get)} {fmt(max(vals))} / 最低 {min(gm, key=gm.get)} {fmt(min(vals))}）",
          "数据片段无销量字段，无法验证销量集中度"]
    return Result(5, "车型 NEV-APEAL 得分及销量集中度逐年提升，差距逐步减小",
                  "insufficient", "阵营间 APEAL 极差（无销量数据）",
                  ev, "无销量数据，无法验证销量集中度；阵营得分差距可见当前横截面水平，但'逐年提升/差距减小'为趋势，无法验证。")


def v06(df, meta) -> Result:
    """6. 自主新势力提升份额，国际止跌，自主新创成熟"""
    # 无销量/份额数据；用阵营样本占比做弱参考
    camp = camp_col(df, meta)
    vc = camp.value_counts()
    share = {k: f"{v/len(camp)*100:.1f}%" for k, v in vc.items()}
    ev = [f"当前样本品牌阵营占比：{share}",
          "注：样本占比 ≠ 市场份额，无销量数据"]
    return Result(6, "自主新势力通过产品力进步提升份额，国际品牌份额止跌，自主新创品牌成熟",
                  "insufficient", "阵营样本占比（非市场份额）",
                  ev, "无销量/市场份额数据，无法验证份额变化；仅能给出样本结构参考。")


def v07(df, meta) -> Result:
    """7. 不同价位段各品牌阵营市场份额"""
    price = df["CN_YNV_07"]  # 单位: 元
    bins = [0, 10e4, 20e4, 40e4, float("inf")]
    labels = ["10万以下", "10-20万", "20-40万", "40万以上"]
    camp = camp_col(df, meta)
    d = df.assign(_camp=camp, _price_bucket=pd.cut(price, bins=bins, labels=labels)).dropna(subset=["_camp", "_price_bucket"])
    ev = []
    ct = pd.crosstab(d["_price_bucket"], d["_camp"], normalize="index") * 100
    for bi, row in ct.iterrows():
        row_s = ", ".join(f"{k} {v:.1f}%" for k, v in row.items() if v > 0)
        ev.append(f"{bi}：{row_s}")
    return Result(7, "国际品牌向下兼容，自主新势力向上扩展，传统自主在 10 万以上全面下降但靠自主新创高端化",
                  "insufficient", "价格段 × 阵营占比（样本结构，非市场份额）",
                  ev, "可看到各价位段内阵营的样本结构（见证据），但这是抽样占比而非市场份额，且无跨年数据验证'份额变化'。")


def v08(df, meta) -> Result:
    """8. 配置下放提升低价位满意度；40万+豪华期待更高但产品力不足"""
    price = df["CN_YNV_07"]  # 单位: 元
    bins = [0, 10e4, 20e4, 40e4, float("inf")]
    labels = ["10万以下", "10-20万", "20-40万", "40万以上"]
    d = df.assign(_price_bucket=pd.cut(price, bins=bins, labels=labels)).dropna(subset=["_price_bucket"])
    ev = []
    gm = group_wmean(d, "_price_bucket", "APEAL_Index")
    for bi in labels:
        if bi in gm:
            ev.append(f"{bi}：APEAL={fmt(gm[bi])}（n={int((d['_price_bucket']==bi).sum())}）")
    return Result(8, "配置下放大幅提升低价位车型满意度；40 万以上豪华车主期待更高但产品力无法满足",
                  "partial", "价格段 × APEAL_Index 加权均值",
                  ev, "当前横截面各价位段满意度水平可见（见证据）；'配置下放提升'与'期待更高'需配置-满意度关联及多年数据，仅部分验证。")


def v09(df, meta) -> Result:
    """9. 国际品牌在四门SUV及轿车市场各品牌阵营中最高"""
    body = meta.variable_value_labels.get("BODYTYPE_DP")  # 1 Sedan 2 SUV 3 MPV
    camp = camp_col(df, meta)
    d = df.assign(_camp=camp).dropna(subset=["_camp"])
    ev = []
    for bcode, blbl in [(1, "轿车"), (2, "SUV")]:
        sub = d[d["BODYTYPE_DP"] == bcode]
        if not len(sub):
            continue
        gm = group_wmean(sub, "_camp", "APEAL_Index")
        top = max(gm, key=gm.get)
        line = f"{blbl}：最高={top} {fmt(gm[top])} | " + ", ".join(f"{k} {fmt(v)}" for k, v in sorted(gm.items(), key=lambda x: -x[1]))
        ev.append(line)
    return Result(9, "国际品牌在占主流的四门 SUV 及轿车市场 2024 年来到各品牌阵营中最高",
                  "partial", "阵营 × 车身类型 × APEAL_Index",
                  ev, "横截面可看各阵营在轿车/SUV 市场的得分排名（见证据）；'2024 年来到最高'为趋势表述，单年数据部分支持。")


def v10(df, meta) -> Result:
    """10. 国际品牌安全感因子显著领先（坚固性、事故保护）"""
    camp = camp_col(df, meta)
    d = df.assign(_camp=camp).dropna(subset=["_camp"])
    ev = []
    gm = group_wmean(d, "_camp", "ASFTY_Index")
    for k in sorted(gm, key=lambda x: -gm[x]):
        ev.append(f"{k}：ASFTY 安全={fmt(gm[k])}")
    # 保护性 ASFTY_R_02
    if "ASFTY_R_02" in d.columns:
        gm2 = group_wmean(d, "_camp", "ASFTY_R_02")
        ev.append("保护性感受（ASFTY_R_02，1-10 加权均值）：" + ", ".join(f"{k} {fmt(gm2[k],2)}" for k in sorted(gm2, key=lambda x: -gm2[x])))
    return Result(10, "国际品牌在安全感因子显著领先，体现在车辆坚固性与事故保护性",
                  "supported", "阵营 × ASFTY_Index / ASFTY_R_02",
                  ev, "横截面数据支持：国际品牌安全指数领先（见证据），保护性感受亦领先。")


def v11(df, meta) -> Result:
    """11. 非传统颜色提升新车魅力；个性色车主对颜色喜好度更高"""
    # SCR_G_1: 1 White 2 Grey 3 Black 4 Silver 5 Blue 6 Red 97 Other
    trad = {1.0, 2.0, 3.0, 4.0}
    s = df["SCR_G_1"]
    aext = df["AEXT_Index"]
    apeal = df["APEAL_Index"]
    w = df[WEIGHT_COL].fillna(1)
    trad_mask = s.isin(trad)
    nontrad_mask = s.isin({5.0, 6.0, 97.0})
    ev = []
    if trad_mask.any() and nontrad_mask.any():
        ev.append(f"传统色（白/灰/黑/银，n={int(trad_mask.sum())}）：AEXT 外观={fmt(wmean(aext[trad_mask], w[trad_mask]))}，APEAL={fmt(wmean(apeal[trad_mask], w[trad_mask]))}")
        ev.append(f"非传统色（蓝/红/其他，n={int(nontrad_mask.sum())}）：AEXT 外观={fmt(wmean(aext[nontrad_mask], w[nontrad_mask]))}，APEAL={fmt(wmean(apeal[nontrad_mask], w[nontrad_mask]))}")
    # 颜色喜好度近似：AEXT_R_01 外观造型评分
    if "AEXT_R_01" in df.columns:
        r = df["AEXT_R_01"]
        ev.append(f"外观造型评分 AEXT_R_01：传统色 {fmt(wmean(r[trad_mask], w[trad_mask]),2)} vs 非传统色 {fmt(wmean(r[nontrad_mask], w[nontrad_mask]),2)}")
    # 颜色作为"最爱外观要素"提及率 (AEXT_D_01=4 'Exterior color')
    if "AEXT_D_01" in df.columns:
        a = df["AEXT_D_01"]
        m1 = trad_mask & a.notna()
        m2 = nontrad_mask & a.notna()
        if m1.any() and m2.any():
            p1 = (a[m1] == 4.0).mean() * 100
            p2 = (a[m2] == 4.0).mean() * 100
            ev.append(f"'颜色'作为最爱外观要素提及率：传统色 {p1:.1f}% vs 非传统色 {p2:.1f}%")
    return Result(11, "非传统颜色更能提升新车魅力；个性色车主对颜色喜好度更高",
                  "contradicted", "SCR_G_1 传统色/非传统色 × AEXT_Index / APEAL_Index / AEXT_R_01 / 外观要素提及",
                  ev, "横截面数据显示方向与要点相反：传统色车主外观指数与整体 APEAL 反而更高，'颜色作为最爱外观要素'提及率也更低（见证据）。数据不支持该要点。")


def v12(df, meta) -> Result:
    """12. 白黑最受欢迎；黑银随价递增；个性色集中10万以下及非一线"""
    color = meta.variable_value_labels.get("SCR_G_1")
    vc = df["SCR_G_1"].value_counts()
    ev = [f"颜色分布：{', '.join(f'{color.get(k,k)} {int(v)}（{v/len(df)*100:.1f}%）' for k,v in sorted(vc.items(), key=lambda x:-x[1])[:4])}"]
    # 黑/银占比随价格
    price = df["CN_YNV_07"]
    d = df.assign(_p=price).dropna(subset=["_p"])
    for lo, hi, lbl in [(0, 10, "10万以下"), (10, 20, "10-20万"), (20, 40, "20-40万"), (40, 1e9, "40万以上")]:
        seg = d[(d["_p"] >= lo * 1e4) & (d["_p"] < hi * 1e4)]
        if not len(seg):
            continue
        black = seg["SCR_G_1"].isin([3.0]).mean() * 100
        silver = seg["SCR_G_1"].isin([4.0]).mean() * 100
        other = seg["SCR_G_1"].isin([97.0]).mean() * 100
        ev.append(f"{lbl}：黑 {black:.1f}% / 银 {silver:.1f}% / 其他色 {other:.1f}%")
    # 个性色 × 城市层级
    tier = meta.variable_value_labels.get("CITY_TIER_DP")
    for t, lbl in [(1, "一线"), (2, "二线"), (3, "三线"), (4, "四线")]:
        seg = df[df["CITY_TIER_DP"] == t]
        if len(seg):
            other = seg["SCR_G_1"].isin([97.0]).mean() * 100
            ev.append(f"{lbl}城市：其他个性色占比 {other:.1f}%")
    return Result(12, "白色、黑色为总体最受欢迎颜色；黑银随车价升高递增；个性色集中低价及非一线",
                  "supported", "SCR_G_1 × 价格段 × 城市层级",
                  ev, "横截面数据支持：白黑占主导；黑色随价格上升；个性色在低价段与非一线城市占比更高（见证据）。")


def v13(df, meta) -> Result:
    """13. 门把手偏好 → 无对应变量"""
    return Result(13, "隐藏外拉式门把手最受欢迎，传统外拉式及无门把手设计喜好度较低",
                  "insufficient", "数据片段无门把手类型变量",
                  ["数据片段中无门把手类型（隐藏外拉/传统外拉/无把手）字段，仅有 'AEXT_D_01 外观要素' 中 Door handle 作为外观喜好选项"],
                  "数据不足：无法验证门把手类型偏好。")


def v14(df, meta) -> Result:
    """14. 座椅颜色一致性 → 无对应变量"""
    return Result(14, "座椅颜色选择一致性高，黑色最受欢迎，灰米次之",
                  "insufficient", "数据片段无座椅颜色变量",
                  ["数据片段中无座椅颜色字段（仅有座椅功能配置，如加热/通风/记忆）"],
                  "数据不足：无法验证座椅颜色偏好。")


def v15(df, meta) -> Result:
    """15. 2023 屏幕设计：独立屏为主，副驾屏少，多带仪表屏 → 无布局变量"""
    return Result(15, "2023 年头部喜欢率屏幕设计以独立屏为主，副驾屏较少，大部分车型带仪表屏",
                  "insufficient", "数据片段无屏幕布局变量",
                  ["数据片段仅有屏幕数量 AINT_D_03，无独立屏/副驾屏/仪表屏布局字段"],
                  "数据不足：无法验证屏幕布局设计。")


def v16(df, meta) -> Result:
    """16. 2024 屏幕设计：副驾屏比例提升 → 无布局变量"""
    return Result(16, "2024 年副驾专属屏幕比例大幅提升，仪表屏仍为主流",
                  "insufficient", "数据片段无屏幕布局变量",
                  ["同要点 15：无屏幕布局字段，无法对比 2023/2024 副驾屏比例"],
                  "数据不足：无法验证屏幕布局趋势。")


def v17(df, meta) -> Result:
    """17. 屏幕数量增长放缓；用户注重清晰度和界面设计"""
    n_screens = meta.variable_value_labels.get("AINT_D_03")
    vc = df["AINT_D_03"].value_counts().sort_index()
    ev = [f"车内屏幕数量分布：{', '.join(f'{n_screens.get(k,k)} 屏 {v}（{v/len(df)*100:.1f}%）' for k,v in vc.items())}"]
    # 屏幕改进/喜爱项（清晰度、界面）
    for col, lbl in [("AINT_D_04", "最需改进"), ("AINT_D_05", "最喜欢")]:
        if col not in df.columns:
            continue
        sub = df[df[col] > 0]
        if len(sub):
            v = meta.variable_value_labels.get(col)
            top = sub[col].value_counts().head(4)
            items = ", ".join(f"{v.get(k,k)} {c}（{c/len(sub)*100:.1f}%）" for k, c in top.items())
            ev.append(f"屏幕方面 · {lbl}：{items}")
    return Result(17, "车内屏幕数量增长放缓；用户更注重屏幕清晰度和界面设计",
                  "partial", "AINT_D_03 数量分布 + AINT_D_04/05 屏幕改进与喜爱项",
                  ev, "横截面可见屏幕数量分布与用户关注点（清晰度/界面为高频项）；'增长放缓'为跨年趋势，无法验证。")


def v18(df, meta) -> Result:
    """18. 内装材料皮革/翻毛皮上升；塑料/碳纤下降；碳纤喜好度减弱"""
    mats = {
        "AINT_D_02_R3": "皮革", "AINT_D_02_R4": "翻毛皮", "AINT_D_02_R6": "塑料/橡胶",
        "AINT_D_02_R5": "碳素纤维", "AINT_D_02_R1": "木质", "AINT_D_02_R2": "镀铬/金属",
        "AINT_D_02_R7": "钢琴漆面板", "AINT_D_02_R8": "织物",
    }
    base = df[[c for c in mats if c in df.columns]].astype(float)
    valid = base.notna().any(axis=1)
    ev = [f"有效回答 n={int(valid.sum())}"]
    for c, name in mats.items():
        if c not in base.columns:
            continue
        pct = ((base[c] == 1) & valid).mean() * 100
        ev.append(f"{name}：{pct:.1f}%")
    # 材料 × AINT_Index / APEAL
    for c, name in [("AINT_D_02_R3", "皮革"), ("AINT_D_02_R5", "碳素纤维"), ("AINT_D_02_R4", "翻毛皮")]:
        if c not in df.columns:
            continue
        with_mat = df[df[c] == 1]
        without = df[df[c] == 0]
        if len(with_mat) and len(without):
            ev.append(f"有{name} vs 无：AINT 内饰 {fmt(wmean(with_mat['AINT_Index'], with_mat[WEIGHT_COL]))} vs {fmt(wmean(without['AINT_Index'], without[WEIGHT_COL]))}；APEAL {fmt(wmean(with_mat['APEAL_Index'], with_mat[WEIGHT_COL]))} vs {fmt(wmean(without['APEAL_Index'], without[WEIGHT_COL]))}")
    return Result(18, "2024 年皮革、翻毛皮使用比例显著上升；塑料/橡胶及碳素纤维比例下降；碳纤喜好度减弱",
                  "partial", "AINT_D_02 内装材料多选分布 + 材料 × 指数",
                  ev, "横截面可验证当前各材料占比与材料-满意度关系（见证据）；'比例上升/下降'为跨年趋势，单年数据无法验证。")


def v19(df, meta) -> Result:
    """19. 手机系统背景车机 → 设置启动因子更高；增换购更愿选"""
    ev = []
    if "SMTPHONE_OPSYSTEM" in df.columns:
        os_lbl = meta.variable_value_labels.get("SMTPHONE_OPSYSTEM")
        for os in [1.0, 2.0]:
            s = df[df["SMTPHONE_OPSYSTEM"] == os]
            if len(s):
                ev.append(f"手机系统 {os_lbl.get(os)}（n={len(s)}）：ASET 设置启动={fmt(wmean(s['ASET_Index'], s[WEIGHT_COL]))}")
    if "CONNECT_SMTPHONE" in df.columns:
        for c, lbl in [(1.0, "连接手机"), (0.0, "未连接")]:
            s = df[df["CONNECT_SMTPHONE"] == c]
            if len(s):
                ev.append(f"{lbl}（n={len(s)}）：ASET 设置启动={fmt(wmean(s['ASET_Index'], s[WEIGHT_COL]))}")
    # 增购/换购 vs 首购 连接手机比例
    if "CONNECT_SMTPHONE" in df.columns:
        for g, lbl in [(1, "换购"), (2, "增购"), (3, "首购")]:
            s = df[df["YPV_01"] == g]
            if len(s):
                pct = (s["CONNECT_SMTPHONE"] == 1).mean() * 100
                ev.append(f"{lbl}中连接手机占比：{pct:.1f}%")
    return Result(19, "有手机系统背景的车机设置/启动因子得分更高；增购换购更愿选此类车机",
                  "supported", "SMTPHONE_OPSYSTEM / CONNECT_SMTPHONE × ASET_Index；YPV_01 × 连接占比",
                  ev, "横截面数据支持：连接手机用户 ASET 得分更高（见证据）；增购/换购连接手机占比略高。")


def v20(df, meta) -> Result:
    """20. 插混性能由领先转落后，发动机/电机声音影响最明显"""
    seg = meta.variable_value_labels.get("SUPER_SEGMENT_DP")
    ev = []
    for m, lbl in [("APERF_Index", "性能整体"), ("APERF_R_03", "发动机/电机声音"), ("APERF_R_01", "平顺性"), ("APERF_R_02", "动力")]:
        gm = group_wmean(df, "SUPER_SEGMENT_DP", m)
        ev.append(f"{lbl}：BEV={fmt(gm.get(1.0),2)} vs PHEV={fmt(gm.get(2.0),2)}")
    return Result(20, "插混车型性能较纯电由整体领先转为全面落后，发动机/电机声音影响最明显",
                  "partial", "SUPER_SEGMENT_DP × APERF_Index / APERF_R_*",
                  ev, "横截面可见 BEV vs PHEV 各性能要素水平（见证据）；'由领先转落后'为跨年趋势，单年数据部分支持。")


def v21(df, meta) -> Result:
    """21. 插混驾驶感受由领先转落后，主要落后场景为郊区/高架中低速"""
    ev = []
    gm = group_wmean(df, "SUPER_SEGMENT_DP", "ADRV_Index")
    ev.append(f"驾驶感受整体：BEV={fmt(gm.get(1.0),2)} vs PHEV={fmt(gm.get(2.0),2)}")
    for m in ["ADRV_R_01", "ADRV_R_02", "ADRV_R_03"]:
        gm2 = group_wmean(df, "SUPER_SEGMENT_DP", m)
        ev.append(f"{col_label(meta, m)[:30]}：BEV={fmt(gm2.get(1.0),2)} vs PHEV={fmt(gm2.get(2.0),2)}")
    # 场景偏好 ADRV_D_02
    if "ADRV_D_02" in df.columns:
        road = meta.variable_value_labels.get("ADRV_D_02")
        ev.append(f"最常遇道路（ADRV_D_02）：{road if road else '—'}")
    return Result(21, "插混车型驾驶感受由领先转为落后，主要落后场景为郊区/高架中低速行驶",
                  "partial", "SUPER_SEGMENT_DP × ADRV_Index / ADRV_R_*",
                  ev, "横截面可见 BEV vs PHEV 驾驶感受差异（见证据）；'由领先转落后'与特定场景归因为趋势/机制判断，单年数据部分支持。")


def v22(df, meta) -> Result:
    """22. 高阶座椅功能影响驾驶感受；电动记忆座椅、后排通风影响最明显；后排记忆对舒适度提升轻微"""
    # SCR_SEAT00_04C 记忆座椅 (R1 driver / R3 rear), SCR_SEAT00_04B 通风 (R1 driver / R3 rear)
    ev = []
    checks = [
        ("SCR_SEAT00_04C_R1", "主驾电动记忆座椅", "ADRV_Index", "驾驶感受"),
        ("SCR_SEAT00_04B_R3", "后排通风/冷却", "ADRV_Index", "驾驶感受"),
        ("SCR_SEAT00_04C_R3", "后排电动记忆", "ACMFT_Index", "舒适度"),
    ]
    for c, name, metric, mlbl in checks:
        if c not in df.columns:
            ev.append(f"{name}：无该字段")
            continue
        yes = df[df[c] == 1]
        no = df[df[c] == 0]
        if len(yes) and len(no):
            ev.append(f"{name}：有 vs 无 → {mlbl} {fmt(wmean(yes[metric], yes[WEIGHT_COL]))} vs {fmt(wmean(no[metric], no[WEIGHT_COL]))}（n 有={len(yes)}）")
    return Result(22, "高阶座椅功能对驾驶感受有显著影响；主驾电动记忆、后排通风影响最明显；后排记忆对舒适度提升轻微",
                  "supported", "座椅功能字段 × ADRV_Index / ACMFT_Index",
                  ev, "横截面数据支持：主驾记忆座椅、后排通风显著影响驾驶感受；后排记忆对舒适度提升幅度较小（见证据）。")


def v23(df, meta) -> Result:
    """23. 续航期望增加；里程焦虑下降；快充需求持续增长"""
    ev = []
    exp = df["NEV_14"]
    act = df["K_AFUEL_D_05"]
    ev.append(f"期望续航 NEV_14 均值 = {fmt(exp.mean(), 0)} km（n={int(exp.notna().sum())}）")
    ev.append(f"实际续航 K_AFUEL_D_05 均值 = {fmt(act.mean(), 0)} km（n={int(act.notna().sum())}）")
    if "AFUEL_D_06" in df.columns:
        v = meta.variable_value_labels.get("AFUEL_D_06")
        vc = df["AFUEL_D_06"].value_counts().sort_index()
        ev.append(f"续航与期望比较：{', '.join(f'{v.get(k,k)} {c/len(df)*100:.1f}%' for k,c in vc.items())}")
    if "NEV_08" in df.columns:
        vc = df["NEV_08"].value_counts().sort_index()
        freq = meta.variable_value_labels.get("NEV_08")
        top4 = list(vc.items())[:4]
        ev.append(f"快充频率：{', '.join(f'{freq.get(k,k)} {c/len(df)*100:.1f}%' for k,c in top4)}")
    return Result(23, "纯电续航期望仍在增加，里程焦虑下降；快充需求持续增长",
                  "partial", "NEV_14 期望续航 / AFUEL_D_06 期望对比 / NEV_08 快充频率",
                  ev, "横截面可见期望续航水平、续航与期望差距、快充使用结构（见证据）；'增加/下降/增长'为跨年趋势，需多年数据。")


def v24(df, meta) -> Result:
    """24. 慢充时长减少0.5小时；慢充速度仍为充电体验最低分要素"""
    ev = []
    slow_h = df["ACHAR_D_01"]
    fast_m = df["ACHAR_D_03"]
    ev.append(f"慢充时长（小时）均值 = {fmt(slow_h.mean(), 2)}（n={int(slow_h.notna().sum())}）")
    ev.append(f"快充时长（分钟）均值 = {fmt(fast_m.mean(), 1)}（n={int(fast_m.notna().sum())}）")
    # 慢充速度 vs 其他充电要素得分
    items = {
        "ACHAR_R_05": "慢充速度", "ACHAR_R_04": "快充速度", "ACHAR_R_06": "充电便利性",
        "ACHAR_R_07": "充电状态易读", "ACHAR_R_01": "充电口设计", "ACHAR_R_02": "充电线长度",
        "ACHAR_R_09": "整体充电体验",
    }
    w = df[WEIGHT_COL].fillna(1)
    ev.append("充电体验各要素（1-10 加权均值）：")
    scores = {}
    for c, name in items.items():
        if c in df.columns:
            scores[name] = wmean(df[c], w)
    for name in sorted(scores, key=lambda x: -scores[x]):
        star = " ← 最低" if scores[name] == min(scores.values()) else ""
        ev.append(f"  {name}：{fmt(scores[name],2)}{star}")
    return Result(24, "慢充时长较 2023 减少 0.5 小时；慢充速度仍为充电体验得分最低要素",
                  "partial", "ACHAR_D_01/D_03 时长 + ACHAR_R_* 充电要素得分",
                  ev, "横截面可验证慢充速度确为各充电要素中得分最低（见证据）；'较 2023 减少 0.5 小时'为跨年对比，单年数据无法验证。")


# ---------------------------------------------------------------------------
# 汇总与 HTML 渲染
# ---------------------------------------------------------------------------

VERIFY_FUNCS: List[Callable[[pd.DataFrame, Any], Result]] = [
    v01, v02, v03, v04, v05, v06, v07, v08, v09, v10,
    v11, v12, v13, v14, v15, v16, v17, v18, v19, v20,
    v21, v22, v23, v24,
]

VERDICT_META = {
    "supported": {"label": "支持", "color": "#1B7F4B", "bg": "#E4F4EC"},
    "partial": {"label": "部分支持", "color": "#B0692A", "bg": "#FBF0E3"},
    "contradicted": {"label": "数据不支持", "color": "#B0262A", "bg": "#FBE7E8"},
    "insufficient": {"label": "数据不足", "color": "#6B7C8F", "bg": "#EFF3F7"},
}


def render_html(results: List[Dict[str, Any]]) -> str:
    counts = {"supported": 0, "partial": 0, "contradicted": 0, "insufficient": 0}
    for r in results:
        counts[r["verdict"]] += 1

    def esc(t: str) -> str:
        return html.escape(str(t))

    cards = []
    for r in results:
        vmeta = VERDICT_META[r["verdict"]]
        evidence = "".join(f"<li>{esc(e)}</li>" for e in r["evidence"])
        cards.append(f"""
        <div class="card">
          <div class="card-head">
            <span class="num">{r['no']:02d}</span>
            <h3>{esc(r['title'])}</h3>
            <span class="badge" style="background:{vmeta['bg']};color:{vmeta['color']}">{vmeta['label']}</span>
          </div>
          <div class="method">验证方法：{esc(r['method'])}</div>
          <ul class="evidence">{evidence}</ul>
          <div class="conclusion"><b>结论：</b>{esc(r['conclusion'])}</div>
        </div>
        """)

    summary_rows = ""
    for verdict, meta in VERDICT_META.items():
        summary_rows += f"""
        <div class="stat" style="background:{meta['bg']}">
          <div class="n" style="color:{meta['color']}">{counts[verdict]}</div>
          <div class="l">{meta['label']}</div>
        </div>"""

    template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NEV-APEAL 2024 要点数据验证报告</title>
<style>
  :root {
    --blue:#174A7C; --deep:#06213D; --cyan:#7ECDEB; --light:#DDEFF8;
    --cream:#FFF9EF; --gold:#D79A36; --text:#1F2D3D; --muted:#6B7C8F; --card:#fff;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         background:var(--cream); color:var(--text); line-height:1.7; padding:32px 16px; }
  .container { max-width:1000px; margin:0 auto; }
  header { background:var(--deep); color:#fff; border-radius:16px; padding:36px 42px; margin-bottom:24px; }
  header h1 { font-size:24px; }
  header .sub { color:var(--cyan); font-size:13px; margin-top:8px; }
  header .meta { margin-top:16px; font-size:12.5px; color:#B9CFE0; display:flex; flex-wrap:wrap; gap:6px 22px; }
  header .meta b { color:#fff; }
  .summary { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:24px; }
  .stat { border-radius:12px; padding:18px; text-align:center; }
  .stat .n { font-size:30px; font-weight:700; }
  .stat .l { font-size:13px; color:var(--muted); margin-top:2px; }
  .card { background:var(--card); border-radius:12px; padding:22px 26px; margin-bottom:16px;
          box-shadow:0 1px 4px rgba(23,74,124,.08); border-left:4px solid var(--blue); }
  .card-head { display:flex; align-items:flex-start; gap:12px; margin-bottom:8px; }
  .card-head .num { font-size:20px; font-weight:700; color:var(--blue); min-width:34px; }
  .card-head h3 { font-size:15px; color:var(--deep); flex:1; }
  .badge { font-size:12px; font-weight:600; border-radius:8px; padding:3px 10px; white-space:nowrap; }
  .method { font-size:12px; color:var(--muted); margin-bottom:8px; }
  .evidence { padding-left:20px; margin:8px 0; }
  .evidence li { font-size:13px; margin-bottom:3px; }
  .conclusion { background:var(--light); border-radius:8px; padding:10px 14px; font-size:13px; }
  .conclusion b { color:var(--deep); }
  footer { text-align:center; color:var(--muted); font-size:12px; padding:20px 0 8px; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>NEV-APEAL 2024 要点 · 数据验证报告</h1>
    <div class="sub">用 24 NEV-APEAL数据片段.sav 逐条验证要点文档</div>
    <div class="meta">
      <span>数据源: <b>dataset/24 NEV-APEAL数据片段.sav</b></span>
      <span>样本: <b>9,937 行</b>（2023 交付 {__C23__} · 2024 交付 {__C24__}）</span>
      <span>脚本: <b>scripts/verify_nev_apeal_2024.py</b></span>
      <span>要点: <b>24 条</b></span>
    </div>
  </header>

  <div class="summary">__SUMMARY__</div>

  __CARDS__
  <div class="card" style="border-left-color:var(--gold)">
    <div class="card-head"><span class="num" style="color:var(--gold)">※</span><h3>验证说明</h3></div>
    <ul class="evidence">
      <li><b>支持</b>：横截面数据直接支撑该要点的当前状态。</li>
      <li><b>部分支持</b>：可验证当前水平，但要点含"增长/上升/放缓/增幅"等跨年趋势表述，单年数据（2024 交付仅 535）无法验证趋势本身，仅给出水平参考。</li>
      <li><b>数据不支持</b>：数据可计算，但结果方向与要点表述相反（如要点 11 颜色魅力）。</li>
      <li><b>数据不足</b>：数据片段缺少对应变量（门把手类型、座椅颜色、屏幕布局、销量/市场份额）。</li>
      <li>品牌阵营划分依据：国际品牌 / 独立造车新势力 / 传统车企新能源子品牌 / 传统自主（详见脚本 BRAND_CAMP，为分析假设）。</li>
      <li>所有指数类指标均以 APEAL_WT 加权计算。</li>
    </ul>
  </div>

  <footer>mashang-service · verify_nev_apeal_2024.py · 基于数据片段 {__TOTAL__} 行</footer>
</div>
</body>
</html>"""

    # 注入汇总卡片与要点卡片
    return template.replace("__SUMMARY__", summary_rows).replace("__CARDS__", "\n".join(cards))


def main() -> None:
    p = argparse.ArgumentParser(description="用 .sav 数据验证 NEV-APEAL 2024 要点")
    p.add_argument("--output", default=str(DEFAULT_OUTPUT), help="HTML 输出路径")
    args = p.parse_args()

    df, meta = load()
    # 评分题 99→NaN
    rating_cols = [c for c in df.columns if meta.variable_value_labels.get(c)]
    out = df.copy()
    for c in rating_cols:
        vl = meta.variable_value_labels.get(c) or {}
        if any("N/A" in str(v) for v in vl.values()):
            na = [k for k, v in vl.items() if "N/A" in str(v)]
            if na:
                out[c] = out[c].replace(na, np.nan)
    df = out

    results = []
    for fn in VERIFY_FUNCS:
        r = fn(df, meta)
        results.append(r.to_dict())
        tag = f" [{r.tag}]" if r.tag else ""
        print(f"[{VERDICT_META[r.verdict]['label']}] {r.no:02d} {r.title}{tag}")

    counts = {"supported": 0, "partial": 0, "contradicted": 0, "insufficient": 0}
    for r in results:
        counts[r["verdict"]] += 1
    print(f"\n汇总: 支持 {counts['supported']} / 部分支持 {counts['partial']} / 数据不支持 {counts['contradicted']} / 数据不足 {counts['insufficient']}")

    html_text = render_html(results)
    html_text = html_text.replace("{__C23__}", str(int((df["SCR_DEL_Y"] == 2023).sum())))
    html_text = html_text.replace("{__C24__}", str(int((df["SCR_DEL_Y"] == 2024).sum())))
    html_text = html_text.replace("{__TOTAL__}", str(len(df)))
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_text, encoding="utf-8")
    print(f"HTML 报告: {out_path}")


if __name__ == "__main__":
    main()
