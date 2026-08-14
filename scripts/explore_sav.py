#!/usr/bin/env python
"""
explore_sav.py — .sav (SPSS) 数据集探索性分析脚本

按 docs/sav_exploratory_analysis.md 流水线实现:
    .sav -> pyreadstat -> 变量字典 -> 题型识别 -> Data QC
        -> Descriptive Statistics -> 配置归因 -> 偏好题识别 -> 品牌/价位映射
        -> 自动扫描差异 -> Topic 深挖 -> 统计验证

子命令:
    dict        变量字典 (变量名/标签/值标签/类型/缺失率)
    types       问卷题型识别 (numeric/rating/scale7/categorical/multi)
    qc          Data QC (缺失/异常/多选逻辑/标签完整性)
    describe    描述统计 (加权频数/提及率/均值/Top2 Box)
    config-scan 配置归因 (多选配置 有/无 × 指标, 效应量排序)
    preference  偏好题识别 (Most Improved / Love Most 提及率)
    camp        品牌阵营 × 价位段结构分析
    scan        自动扫描差异 (分组 x 指标, 排序输出候选 Topic)
    topic       针对 Topic 深挖 + 统计验证 (ANOVA/t-test + 效应量)

用法示例:
    python scripts/explore_sav.py dict
    python scripts/explore_sav.py config-scan --min-has 100
    python scripts/explore_sav.py preference
    python scripts/explore_sav.py camp
    python scripts/explore_sav.py scan --group-by SUPER_SEGMENT_DP
    python scripts/explore_sav.py topic --group-by SUPER_SEGMENT_DP --metric APEAL_Index
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import pyreadstat
except ImportError:
    pyreadstat = None

try:
    from scipy import stats
except ImportError:
    stats = None

SERVICE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = SERVICE_ROOT / "dataset" / "24 NEV-APEAL数据片段.sav"
DEFAULT_OUTPUT = SERVICE_ROOT / "outputs" / "sav_apeal"
WEIGHT_COL = "APEAL_WT"

# ---- 题型常量 ----
RATING_NA_LABELS = {"N/A", "n/a", "NA"}
MULTI_RE = re.compile(r"^(.*)_R\d+$")


# ---------------------------------------------------------------------------
# 数据加载与元数据
# ---------------------------------------------------------------------------

def load_sav(path: str) -> Tuple[pd.DataFrame, Any]:
    """读取 .sav，返回 (df, meta)。"""
    if pyreadstat is None:
        sys.exit("缺少 pyreadstat，请先 `pip install pyreadstat`")
    df, meta = pyreadstat.read_sav(path, user_missing=True)
    return df, meta


def col_label(meta, name: str) -> Optional[str]:
    """按变量名取列标签。meta.column_labels 是与 column_names 对齐的 list。"""
    labels = getattr(meta, "column_labels", None)
    names = getattr(meta, "column_names", None)
    if isinstance(labels, list) and isinstance(names, list):
        try:
            return labels[names.index(name)]
        except ValueError:
            return None
    if isinstance(labels, dict):
        return labels.get(name)
    return None


_NUMERIC_UNITS = {"cm", "km", "m", "kg", "g", "mm", "l", "ml", "lb", "in", "kmh", "kph"}


def _labels_are_numeric(vl: Dict[Any, str]) -> bool:
    """标签是否本质是数值（可带单位后缀），如 HEIGHT 的 '140CM' 类。

    'Tier 1' 这类语义标签不算数值（字母部分不是单位）。
    """
    if not vl:
        return False
    for v in vl.values():
        if v is None:
            continue
        s = str(v).strip()
        num = re.sub(r"[^0-9.]", "", s)
        if not num.replace(".", "", 1).isdigit():
            return False
        alpha = re.sub(r"[^a-zA-Z]", "", s).lower()
        if alpha and alpha not in _NUMERIC_UNITS:
            return False
    return True


def _labels_pure_digit(vl: Dict[Any, str]) -> bool:
    """标签文本是否全部为纯数字（如 YNV 语义差异的 '1'..'7'）。"""
    return all(str(v).strip().replace(".", "", 1).isdigit() for v in vl.values())


def infer_var_type(name: str, vl: Optional[Dict[Any, str]]) -> str:
    """判断单个变量题型。

    returns: numeric | rating | scale7 | categorical | multi (组内成员)
    """
    if not vl:
        return "numeric"
    keys = set(vl.keys())
    # 纯数字标签: 小规模(<=12)视为有序数字量表(scale7), 大规模视为连续
    if _labels_pure_digit(vl):
        return "scale7" if len(keys) <= 12 else "numeric"
    if _labels_are_numeric(vl):
        return "numeric"
    # 11 分量表: 含 'Unacceptable'/'Truly Exceptional'/'N/A'
    labels_text = " ".join(str(v) for v in vl.values())
    if len(keys) >= 10 and ("N/A" in labels_text or "Unacceptable" in labels_text):
        return "rating"
    if len(keys) == 7 and keys == {1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0}:
        return "scale7"
    return "categorical"


def detect_multi_groups(df: pd.DataFrame, meta) -> Dict[str, List[str]]:
    """识别多选组: 列名 *_R\\d+ 且取值为 {0,1} 的归为一组。"""
    groups: Dict[str, List[str]] = defaultdict(list)
    for c in df.columns:
        m = MULTI_RE.match(c)
        if not m:
            continue
        vl = meta.variable_value_labels.get(c)
        if vl and set(vl.keys()) <= {0.0, 1.0}:
            groups[m.group(1)].append(c)
    for k in list(groups):
        if len(groups[k]) < 2:
            del groups[k]
    return dict(groups)


def clean_rating_values(df: pd.DataFrame, meta, rating_cols: List[str]) -> pd.DataFrame:
    """将 11 分量表题中的 99=N/A 转为 NaN（仅对 rating 题）。"""
    out = df.copy()
    for c in rating_cols:
        vl = meta.variable_value_labels.get(c) or {}
        na_vals = [k for k, v in vl.items() if str(v).strip() in RATING_NA_LABELS]
        if na_vals:
            out[c] = out[c].replace(na_vals, np.nan)
    return out


# ---------------------------------------------------------------------------
# 变量字典
# ---------------------------------------------------------------------------

def build_vardict(df: pd.DataFrame, meta, multi_groups: Dict[str, List[str]]) -> pd.DataFrame:
    multi_members = {c for cols in multi_groups.values() for c in cols}
    rows = []
    for c in df.columns:
        vl = meta.variable_value_labels.get(c)
        vtype = infer_var_type(c, vl)
        if c in multi_members:
            vtype = "multi"
        rows.append(
            {
                "variable": c,
                "label": col_label(meta, c),
                "type": vtype,
                "n_labels": len(vl) if vl else 0,
                "n_unique": int(df[c].nunique(dropna=False)),
                "missing": int(df[c].isna().sum()),
                "missing_rate": round(float(df[c].isna().mean()), 4),
            }
        )
    vardict = pd.DataFrame(rows)
    return vardict


# ---------------------------------------------------------------------------
# Data QC
# ---------------------------------------------------------------------------

def run_qc(df: pd.DataFrame, meta, multi_groups: Dict[str, List[str]]) -> Dict[str, Any]:
    report: Dict[str, Any] = {"checks": [], "warnings": []}
    # 1) 缺失率高的变量
    high_miss = df.columns[df.isna().mean() > 0.2].tolist()
    report["checks"].append({"name": "high_missing", "detail": f"{len(high_miss)} 个变量缺失率>20%", "items": high_miss})
    # 2) 全缺失 / 单值变量
    for c in df.columns:
        nuniq = df[c].nunique(dropna=True)
        if nuniq <= 1:
            report["warnings"].append({"variable": c, "issue": f"仅 {nuniq} 个取值"})
    # 3) rating 题 99 转 NaN 后异常
    for c in df.columns:
        vl = meta.variable_value_labels.get(c)
        if not vl:
            continue
        lbls = set(str(v) for v in vl.values())
        # 检查取值是否都在标签内
        unlabelled = set(pd.unique(df[c].dropna()))
        known = set(vl.keys())
        unknown = unlabelled - known
        if unknown:
            report["warnings"].append({"variable": c, "issue": f"存在未映射取值 {sorted(unknown)[:8]}"})
        if len(lbls) >= 10 and ("Unacceptable" in " ".join(lbls) or "Truly Exceptional" in " ".join(lbls)):
            if df[c].dropna().between(1, 10).all() is False:
                report["warnings"].append({"variable": c, "issue": "评分题存在超出 1-10 的取值"})
    # 4) 多选逻辑: 矛盾选项 (列标签为纯否定语义, 如 'No'/'None of above'/'Do not have feature at all')
    #    与其他选项同时选中才算矛盾; 矩阵型多选(座位x调节方式)不算。
    NEGATIVE_LABELS = {
        "no", "none of above", "none of these", "do not have feature at all",
        "do not have", "don't know", "not applicable",
    }
    for grp, cols in multi_groups.items():
        sub = df[cols].astype(float)
        valid = sub.notna().any(axis=1)
        for c in cols:
            lbl = (col_label(meta, c) or "").strip().lower()
            if lbl not in NEGATIVE_LABELS:
                continue
            other = [x for x in cols if x != c]
            if not other:
                continue
            n_contra = int(((sub[other].sum(axis=1) > 0) & (sub[c] == 1) & valid).sum())
            if n_contra:
                report["warnings"].append(
                    {"variable": grp, "issue": f"选项 {c}({col_label(meta, c)}) 与其它选项同时选中 {n_contra} 行"}
                )
    report["n_rows"] = len(df)
    report["n_cols"] = len(df.columns)
    report["n_warnings"] = len(report["warnings"])
    return report


# ---------------------------------------------------------------------------
# 加权工具
# ---------------------------------------------------------------------------

def wmean(s: pd.Series, w: pd.Series) -> float:
    m = s.notna().values
    if not m.any():
        return float("nan")
    vals = s.values[m]
    wts = w.values[m]
    return float(np.average(vals, weights=wts))


def wshare(s: pd.Series, w: pd.Series) -> Dict[Any, float]:
    """分类变量各取值的加权占比。"""
    m = s.notna().values
    if not m.any():
        return {}
    vals = s.values[m]
    wts = w.values[m]
    total = wts.sum()
    out: Dict[Any, float] = {}
    for v in pd.unique(vals):
        sel = vals == v
        out[v] = float(wts[sel].sum() / total)
    return out


# ---------------------------------------------------------------------------
# 描述统计
# ---------------------------------------------------------------------------

def describe(df: pd.DataFrame, meta, multi_groups: Dict[str, List[str]],
             vtype_filter: Optional[str] = None, top: int = 30) -> Dict[str, Any]:
    w = df[WEIGHT_COL].fillna(1.0)
    vardict = build_vardict(df, meta, multi_groups)
    # 权重列不是分析变量，不进入描述统计
    vardict = vardict[vardict["variable"] != WEIGHT_COL]
    if vtype_filter:
        vardict = vardict[vardict["type"] == vtype_filter]
    stats_out: List[Dict[str, Any]] = []
    multi_mention: List[Dict[str, Any]] = []

    for _, r in vardict.iterrows():
        c = r["variable"]
        vt = r["type"]
        if vt == "multi":
            continue  # 多选在下方单独聚合
        col = df[c]
        rec = {"variable": c, "label": r["label"], "type": vt, "n": int(col.notna().sum())}
        if vt in ("numeric", "rating", "scale7"):
            valid = col.dropna()
            if len(valid):
                rec.update(
                    {
                        "weighted_mean": round(wmean(valid, w[valid.index]), 2),
                        "mean": round(float(valid.mean()), 2),
                        "median": round(float(valid.median()), 1),
                        "std": round(float(valid.std()), 2),
                        "min": round(float(valid.min()), 1),
                        "max": round(float(valid.max()), 1),
                    }
                )
            if vt == "rating":
                top2 = col.dropna() >= 9
                rec["top2_box_pct"] = round(float(top2.mean()) * 100, 1)
        else:
            share = wshare(col, w)
            rec["weighted_share"] = {str(k): round(v * 100, 2) for k, v in share.items()}
        stats_out.append(rec)

    # 多选提及率
    for grp, cols in multi_groups.items():
        sub = df[cols]
        valid_mask = sub.notna().any(axis=1)
        if not valid_mask.any():
            continue
        valid_w = w[valid_mask].sum()
        mentions = {}
        for c in cols:
            opt_text = col_label(meta, c) or c
            n = int(((sub[c] == 1) & valid_mask).sum())
            mw = float(w[(sub[c] == 1) & valid_mask].sum() / valid_w * 100)
            mentions[c] = {"option": str(opt_text), "n": n, "weighted_pct": round(mw, 2)}
        multi_mention.append({"group": grp, "base": int(valid_mask.sum()), "options": mentions})

    result = {"variables": stats_out, "multi_mention": multi_mention}
    if top:
        result["multi_mention"] = result["multi_mention"][:top]
    return result


# ---------------------------------------------------------------------------
# 自动扫描差异
# ---------------------------------------------------------------------------

# 品牌阵营映射（分析假设，报告中注明）
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

PRICE_BINS = [0, 10e4, 20e4, 40e4, float("inf")]
PRICE_LABELS = ["10万以下", "10-20万", "20-40万", "40万以上"]


def make_camp_col(df: pd.DataFrame, meta) -> pd.Series:
    """品牌 → 阵营标签（未识别品牌返回 None）。"""
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


def make_price_bucket(df: pd.DataFrame, price_col: str = "CN_YNV_07") -> pd.Series:
    """连续价格 → 价位段标签。"""
    if price_col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="object")
    return pd.cut(df[price_col], bins=PRICE_BINS, labels=PRICE_LABELS)


def camp_analysis(df: pd.DataFrame, meta, metric: str = "APEAL_Index") -> Dict[str, Any]:
    """品牌阵营 × 价位段结构分析: 阵营占比、价位段内阵营结构、阵营×价位段×指标。"""
    camp = make_camp_col(df, meta)
    price_b = make_price_bucket(df)
    d = df.assign(_camp=camp, _price=price_b).dropna(subset=["_camp"])
    ev = []
    # 阵营样本结构
    vc = d["_camp"].value_counts()
    ev.append("阵营样本占比：" + ", ".join(f"{k} {v/len(d)*100:.1f}%" for k, v in vc.items()))
    # 价位段 × 阵营交叉结构
    ct = pd.crosstab(d["_price"], d["_camp"], normalize="index") * 100
    for bi, row in ct.iterrows():
        row_s = ", ".join(f"{k} {v:.1f}%" for k, v in row.items() if v > 0)
        ev.append(f"{bi}：{row_s}")
    # 阵营 × 指标加权均值
    for k in sorted(CAMP_LABEL.values()):
        sub = d[d["_camp"] == k]
        if len(sub):
            ev.append(f"{k}（n={len(sub)}）：{metric}={round(wmean(sub[metric], sub[WEIGHT_COL]), 1)}")
    return {
        "method": "品牌阵营映射 + 价位段分箱 + 阵营×价位×指标加权",
        "evidence": ev,
        "conclusion": "样本结构为抽样占比而非市场份额；阵营/价位段得分可作横截面参考，'份额变化'类趋势需销量数据。",
    }


def config_scan(df: pd.DataFrame, meta, multi_groups: Dict[str, List[str]],
                metrics: Optional[List[str]] = None, top: int = 30,
                min_has: int = 50) -> Dict[str, Any]:
    """配置归因: 多选组(配置)逐选项 有/无 × 指标 加权均值差异 + t-test。

    配置是二分多选(如 '主驾电动记忆座椅' Yes/No)，按是否拥有该配置分组，
    比较拥有者 vs 未拥有者的指标差异，输出效应量排序。
    过滤: 拥有样本 < min_has 的选项跳过; 排除 Other/Don't know 等非业务选项。
    """
    if stats is None:
        sys.exit("缺少 scipy，请先 `pip install scipy`")
    metrics = metrics or _default_metrics(df)
    w = df[WEIGHT_COL].fillna(1.0)
    # 排除非业务选项: 列标签含否定/其他/不知道等语义 (子串匹配)
    EXCLUDE_OPT = {"other", "don't know", "do not have feature at all", "do not have",
                   "none of above", "none of these", "not applicable", "no adjustment",
                   "no feature", "don't have"}
    results = []
    for grp, cols in multi_groups.items():
        for c in cols:
            if df[c].dtype.kind not in "biuf":
                continue
            opt_lbl = col_label(meta, c) or c
            if any(tok in opt_lbl.lower() for tok in EXCLUDE_OPT):
                continue
            sub = df[[c, WEIGHT_COL]].dropna()
            if len(sub) < 30:
                continue
            vc = sub[c].value_counts()
            if vc.get(1, 0) < min_has or vc.get(0, 0) < min_has:
                continue
            yes_mask = sub[c] == 1
            no_mask = sub[c] == 0
            opt_lbl = col_label(meta, c) or c
            for m in metrics:
                if m not in df.columns:
                    continue
                ys = df.loc[sub.index, m][yes_mask]
                ns = df.loc[sub.index, m][no_mask]
                ys = ys[ys.notna()]
                ns = ns[ns.notna()]
                if len(ys) < min_has or len(ns) < min_has:
                    continue
                w_yes = w.loc[ys.index]
                w_no = w.loc[ns.index]
                wmy = wmean(ys, w_yes)
                wmn = wmean(ns, w_no)
                t, p = stats.ttest_ind(ys.values, ns.values, equal_var=False)
                pooled = np.sqrt((np.var(ys.values) + np.var(ns.values)) / 2)
                d = abs(np.mean(ys.values) - np.mean(ns.values)) / pooled if pooled else 0
                results.append({
                    "config": opt_lbl, "group": grp, "metric": m,
                    "n_has": int(len(ys)), "n_not": int(len(ns)),
                    "wmean_has": round(wmy, 2), "wmean_not": round(wmn, 2),
                    "diff": round(wmy - wmn, 2), "p": float(p), "cohens_d": round(float(d), 3),
                })
    res_df = pd.DataFrame(results)
    if res_df.empty:
        return {"rows": [], "top": []}
    res_df = res_df.sort_values(["cohens_d", "p"], ascending=[False, True])
    rows = res_df.to_dict("records")
    return {"rows": rows, "top": rows[:top]}


def preference_analysis(df: pd.DataFrame, meta) -> Dict[str, Any]:
    """偏好题识别: 识别 'Most Improved / Love Most'（最需改进 / 最喜欢）类题型，
    输出各题选项提及率排序，用于改进优先级洞察。"""
    results = []
    for c in df.columns:
        vl = meta.variable_value_labels.get(c)
        if not vl:
            continue
        lbl = col_label(meta, c) or ""
        # 偏好题核心特征: 列标签含 Most Improved / Love Most
        if not ("most improved" in lbl.lower() or "love most" in lbl.lower()):
            continue
        # 排除多选成员(_R)
        if c in {x for cols in detect_multi_groups(df, meta).values() for x in cols}:
            continue
        sub = df[c].dropna()
        if len(sub) < 100:
            continue
        vc = sub.value_counts()
        top = vc.head(5)
        items = [
            {"value": k, "label": str(vl.get(k, k)), "n": int(v),
             "pct": round(float(v / len(sub) * 100), 1)}
            for k, v in top.items()
        ]
        results.append({
            "variable": c, "label": lbl, "n_valid": int(len(sub)),
            "top_options": items,
        })
    results.sort(key=lambda x: -x["n_valid"])
    return {"rows": results}


def _default_groups(df: pd.DataFrame, meta, multi_groups: Dict[str, List[str]]) -> List[str]:
    """默认分组变量: 主分类变量(非多选成员)且类别数 2-12。

    多选组内二分选项(_R*)不作为默认分组; 如需要可 --group-by 显式指定。
    """
    multi_members = {c for cols in multi_groups.values() for c in cols}
    out = []
    for c in df.columns:
        if c in multi_members:
            continue
        vl = meta.variable_value_labels.get(c)
        if not vl:
            continue
        vtype = infer_var_type(c, vl)
        if vtype != "categorical":
            continue
        if 2 <= len(vl) <= 12 and _labels_are_numeric(vl) is False:
            out.append(c)
    return out


def _default_metrics(df: pd.DataFrame) -> List[str]:
    """默认指标: APEAL 指数族 + OSAT。"""
    pref = [c for c in df.columns if c.endswith("_Index") or c == "APEAL_Index"]
    return ["APEAL_Index"] + [c for c in pref if c != "APEAL_Index"]


def scan(df: pd.DataFrame, meta, multi_groups: Dict[str, List[str]],
         group_by: Optional[List[str]] = None, metrics: Optional[List[str]] = None,
         top: int = 30) -> Dict[str, Any]:
    if stats is None:
        sys.exit("缺少 scipy，请先 `pip install scipy`")
    groups = group_by or _default_groups(df, meta, multi_groups)
    metrics = metrics or _default_metrics(df)
    w = df[WEIGHT_COL].fillna(1.0)

    results = []
    for g in groups:
        for m in metrics:
            if m not in df.columns or g not in df.columns or m == g:
                continue
            sub = df[[g, m]].dropna()
            if len(sub) < 30:
                continue
            cats = sub[g]
            vc = cats.value_counts()
            # 排除占比失衡变量(如 99% vs 1% 的配置开关), 避免效应量虚高
            if vc.max() / len(sub) > 0.95:
                continue
            uniq = [u for u in pd.unique(cats) if cats.isin([u]).sum() >= 10]
            if len(uniq) < 2:
                continue
            s = sub[sub[g].isin(uniq)]
            if len(s) < 30:
                continue
            w_s = df.loc[s.index, WEIGHT_COL].fillna(1.0).values
            groups_list = [s[m][s[g] == u].values for u in uniq]
            # 组加权均值 (位置对齐)
            gmeans = {}
            for u in uniq:
                sel = s[g] == u
                gmeans[str(u)] = round(wmean(s[m][sel], pd.Series(w_s[sel.values])), 2)
            if len(uniq) == 2:
                stat, p = stats.ttest_ind(groups_list[0], groups_list[1], equal_var=False)
                eta = None
                a, b = groups_list[0], groups_list[1]
                if len(a) and len(b):
                    pooled = np.sqrt((np.var(a) + np.var(b)) / 2)
                    eta = abs(np.mean(a) - np.mean(b)) / pooled if pooled else 0
                effect = round(eta, 3) if eta else None
            else:
                f, p = stats.f_oneway(*groups_list)
                # eta² = SS_between / SS_total
                allv = np.concatenate(groups_list)
                grand = allv.mean()
                ss_between = sum(len(x) * (np.mean(x) - grand) ** 2 for x in groups_list)
                ss_total = ((allv - grand) ** 2).sum()
                effect = round(float(ss_between / ss_total), 4) if ss_total else 0.0
            results.append(
                {
                    "group": g,
                    "group_label": col_label(meta, g),
                    "metric": m,
                    "n_groups": len(uniq),
                    "p": float(p),
                    "effect_size": effect,
                    "group_means": gmeans,
                }
            )

    res_df = pd.DataFrame(results)
    if res_df.empty:
        return {"rows": [], "top_candidates": []}
    res_df["abs_effect"] = res_df["effect_size"].fillna(0).abs()
    res_df = res_df.sort_values(["abs_effect", "p"], ascending=[False, True])
    rows = res_df.to_dict("records")
    return {"rows": rows, "top_candidates": rows[:top]}


# ---------------------------------------------------------------------------
# Topic 深挖 + 统计验证
# ---------------------------------------------------------------------------

def topic(df: pd.DataFrame, meta, multi_groups: Dict[str, List[str]],
          group_by: str, metric: str, pairwise: bool = False) -> Dict[str, Any]:
    if stats is None:
        sys.exit("缺少 scipy，请先 `pip install scipy`")
    for v in (group_by, metric):
        if v not in df.columns:
            sys.exit(f"变量不存在: {v}")
    w = df[WEIGHT_COL].fillna(1.0)
    vl = meta.variable_value_labels.get(group_by)
    sub = df[[group_by, metric]].dropna()
    uniq = [u for u in pd.unique(sub[group_by]) if sub[group_by].isin([u]).sum() >= 5]
    s = sub[sub[group_by].isin(uniq)]
    groups_list = [s[metric][s[group_by] == u].values for u in uniq]
    w_s = df.loc[s.index, WEIGHT_COL].fillna(1.0).values
    detail = []
    for u in uniq:
        sel = s[group_by] == u
        col = s[metric][sel]
        label = (vl or {}).get(u, u)
        detail.append(
            {
                "value": u,
                "label": str(label),
                "n": int(col.notna().sum()),
                "weighted_mean": round(wmean(col, pd.Series(w_s[sel.values])), 2),
                "mean": round(float(col.mean()), 2),
                "std": round(float(col.std()), 2),
            }
        )

    test = {}
    if len(uniq) == 2:
        stat, p = stats.ttest_ind(groups_list[0], groups_list[1], equal_var=False)
        a, b = groups_list[0], groups_list[1]
        pooled = np.sqrt((np.var(a) + np.var(b)) / 2)
        d = abs(np.mean(a) - np.mean(b)) / pooled if pooled else 0
        test = {"method": "Welch t-test", "stat": round(stat, 3), "p": float(p),
                "cohens_d": round(float(d), 3)}
    else:
        f, p = stats.f_oneway(*groups_list)
        k, pkw = stats.kruskal(*groups_list)
        allv = np.concatenate(groups_list)
        grand = allv.mean()
        ss_between = sum(len(x) * (np.mean(x) - grand) ** 2 for x in groups_list)
        ss_total = ((allv - grand) ** 2).sum()
        eta2 = ss_between / ss_total if ss_total else 0
        test = {"method": "ANOVA", "F": round(f, 3), "p": float(p),
                "eta2": round(float(eta2), 4),
                "kruskal_H": round(k, 3), "kruskal_p": float(pkw)}

    pairwise_out = []
    if pairwise:
        try:
            from statsmodels.stats.multicomp import pairwise_tukeyhsd
        except ImportError:
            pairwise_out = []
        else:
            if len(uniq) > 2:
                tukey = pairwise_tukeyhsd(s[metric], s[group_by].astype(str))
                tbl = tukey.summary().data[1:]
                pairwise_out = [
                    {"group1": str(r[0]), "group2": str(r[1]), "diff": round(r[2], 3),
                     "p_adj": float(r[3]), "reject": bool(r[6])}
                    for r in tbl
                ]

    return {
        "group_by": group_by,
        "group_label": col_label(meta, group_by),
        "metric": metric,
        "n_rows": int(s.shape[0]),
        "detail": detail,
        "test": test,
        "pairwise": pairwise_out,
        "conclusion": _draft_conclusion(detail, test),
    }


def _draft_conclusion(detail: List[Dict[str, Any]], test: Dict[str, Any]) -> str:
    if not detail:
        return "样本不足，无法给出结论。"
    detail = sorted(detail, key=lambda x: x.get("weighted_mean") or 0, reverse=True)
    hi, lo = detail[0], detail[-1]
    p = test.get("p", 1)
    sig = "显著" if p < 0.05 else "不显著"
    effect = test.get("cohens_d") or test.get("eta2")
    return (
        f"{hi['label']} 加权均值 {hi['weighted_mean']}，"
        f"{lo['label']} 加权均值 {lo['weighted_mean']}，差异 {sig}"
        f"（p={p:.3g}，效应量={effect}）。"
    )


# ---------------------------------------------------------------------------
# 输出与 CLI
# ---------------------------------------------------------------------------

def emit(data: Any, fmt: str, outdir: Path, basename: str) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        p = outdir / f"{basename}.json"
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    else:
        p = outdir / f"{basename}.csv"
        df_out = pd.DataFrame(data)
        df_out.to_csv(p, index=False, encoding="utf-8-sig")
    return p


def build_result_contract(script: str, result: Dict[str, Any], artifacts: Dict[str, str],
                          scope: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "success",
        "script": script,
        "scope": scope,
        "result": result,
        "artifacts": artifacts,
        "followup_context": {},
        "warnings": [],
        "errors": [],
    }


def main() -> None:
    p = argparse.ArgumentParser(description=".sav (SPSS) 数据集探索性分析")
    p.add_argument("--input", default=str(DEFAULT_INPUT), help=".sav 文件路径")
    p.add_argument("--output", default=str(DEFAULT_OUTPUT), help="输出目录")
    p.add_argument("--format", default="json", choices=["json", "csv"], help="文件输出格式")
    sub = p.add_subparsers(dest="command", required=True)

    # dict
    sp = sub.add_parser("dict", help="输出变量字典")
    sp.add_argument("--vtype", choices=["numeric", "rating", "scale7", "categorical", "multi"], default=None)
    sp.set_defaults(func=cmd_dict)

    # types
    sp = sub.add_parser("types", help="问卷题型识别")
    sp.add_argument("--vtype", choices=["numeric", "rating", "scale7", "categorical", "multi"], default=None)
    sp.add_argument("--top", type=int, default=50)
    sp.set_defaults(func=cmd_types)

    # qc
    sp = sub.add_parser("qc", help="Data QC")
    sp.set_defaults(func=cmd_qc)

    # describe
    sp = sub.add_parser("describe", help="描述统计")
    sp.add_argument("--vtype", choices=["numeric", "rating", "scale7", "categorical"], default=None)
    sp.add_argument("--multi-top", type=int, default=10, help="多选提及率展示前 N 组")
    sp.set_defaults(func=cmd_describe)

    # scan
    sp = sub.add_parser("scan", help="自动扫描差异")
    sp.add_argument("--group-by", nargs="*", default=None, help="分组变量，默认自动")
    sp.add_argument("--metric", nargs="*", default=None, help="指标变量，默认 APEAL 指数族")
    sp.add_argument("--top", type=int, default=20)
    sp.set_defaults(func=cmd_scan)

    # topic
    sp = sub.add_parser("topic", help="Topic 深挖 + 统计验证")
    sp.add_argument("--group-by", required=True, help="分组变量")
    sp.add_argument("--metric", default="APEAL_Index", help="指标变量")
    sp.add_argument("--pairwise", action="store_true", help="输出 Tukey 两两对比")
    sp.set_defaults(func=cmd_topic)

    # camp
    sp = sub.add_parser("camp", help="品牌阵营 × 价位段结构分析")
    sp.add_argument("--metric", default="APEAL_Index", help="指标变量")
    sp.set_defaults(func=cmd_camp)

    # config-scan
    sp = sub.add_parser("config-scan", help="配置归因扫描 (多选配置 有/无 × 指标)")
    sp.add_argument("--metric", nargs="*", default=None, help="指标变量，默认 APEAL 指数族")
    sp.add_argument("--top", type=int, default=20)
    sp.add_argument("--min-has", type=int, default=50, help="拥有该配置的最小样本量（过滤小样本）")
    sp.set_defaults(func=cmd_config_scan)

    # preference
    sp = sub.add_parser("preference", help="偏好题识别 (最喜欢/最需改进) 提及率排序")
    sp.set_defaults(func=cmd_preference)

    args = p.parse_args()
    args.func(args)


def _load(args):
    df, meta = load_sav(args.input)
    multi = detect_multi_groups(df, meta)
    rating_cols = [
        c for c in df.columns
        if infer_var_type(c, meta.variable_value_labels.get(c)) == "rating"
    ]
    df = clean_rating_values(df, meta, rating_cols)
    return df, meta, multi


def cmd_dict(args):
    df, meta, multi = _load(args)
    vd = build_vardict(df, meta, multi)
    if args.vtype:
        vd = vd[vd["type"] == args.vtype]
    vd = vd.sort_values("missing_rate", ascending=False)
    outdir = Path(args.output)
    p = emit(vd.to_dict("records"), args.format, outdir, "variable_dictionary")
    print(vd.head(40).to_string(index=False))
    print(f"\n共 {len(vd)} 个变量，字典输出: {p}")


def cmd_types(args):
    df, meta, multi = _load(args)
    vd = build_vardict(df, meta, multi)
    summary = vd.groupby("type").size().to_dict()
    print("题型分布:", json.dumps(summary, ensure_ascii=False))
    sub = vd if not args.vtype else vd[vd["type"] == args.vtype]
    sub = sub.head(args.top)
    print(sub[["variable", "label", "type", "n_labels", "missing_rate"]].to_string(index=False))
    outdir = Path(args.output)
    emit(vd.to_dict("records"), args.format, outdir, "variable_types")


def cmd_qc(args):
    df, meta, multi = _load(args)
    rep = run_qc(df, meta, multi)
    print(f"样本 {rep['n_rows']} x {rep['n_cols']}，警告 {rep['n_warnings']} 条")
    for w in rep["warnings"][:30]:
        print("  [!]", w["variable"], "-", w["issue"])
    outdir = Path(args.output)
    p = emit(rep, "json", outdir, "data_qc_report")
    print("QC 报告: ", p)


def cmd_describe(args):
    df, meta, multi = _load(args)
    res = describe(df, meta, multi, vtype_filter=args.vtype, top=args.multi_top)
    print("== 数值/量表/分类变量 ==")
    for r in res["variables"][:60]:
        if r["type"] in ("numeric", "rating", "scale7"):
            extra = f", Top2={r.get('top2_box_pct')}" if r["type"] == "rating" else ""
            print(f"  {r['variable']:<22} n={r['n']:<6} wmean={r.get('weighted_mean')}{extra}")
        else:
            share = r.get("weighted_share", {})
            top_share = sorted(share.items(), key=lambda x: -x[1])[:3]
            share_str = ", ".join(f"{k}={v}%" for k, v in top_share)
            print(f"  {r['variable']:<22} n={r['n']:<6} share[{share_str}]")
    print("\n== 多选提及率 (Top 组) ==")
    for g in res["multi_mention"]:
        opts = ", ".join(f"{o['option']}={o['weighted_pct']}%" for o in list(g["options"].values())[:4])
        print(f"  {g['group']:<22} base={g['base']:<6} {opts}")
    outdir = Path(args.output)
    emit(res, "json", outdir, "descriptive_statistics")


def cmd_scan(args):
    df, meta, multi = _load(args)
    res = scan(df, meta, multi, group_by=args.group_by, metrics=args.metric, top=args.top)
    rows = res["rows"]
    print(f"扫描 {len(rows)} 组 (分组 x 指标) 组合，候选 Topic 前 {args.top}:")
    for r in res["top_candidates"]:
        print(f"  {r['group']} x {r['metric']}  p={r['p']:.3g}  effect={r['effect_size']}  "
              f"means={r['group_means']}")
    outdir = Path(args.output)
    p = emit(rows, args.format, outdir, "diff_scan_results")
    print("完整扫描结果: ", p)


def cmd_topic(args):
    df, meta, multi = _load(args)
    res = topic(df, meta, multi, group_by=args.group_by, metric=args.metric,
                pairwise=args.pairwise)
    print(f"== {res['group_by']} x {res['metric']} ==")
    print(f"{'label':<30}{'n':>8}{'wmean':>10}{'mean':>10}{'std':>8}")
    for d in res["detail"]:
        print(f"{d['label']:<30}{d['n']:>8}{d['weighted_mean']:>10}{d['mean']:>10}{d['std']:>8}")
    print("\n检验:", json.dumps(res["test"], ensure_ascii=False))
    if res["pairwise"]:
        print("两两对比 (Tukey):")
        for r in res["pairwise"]:
            print(f"  {r['group1']} vs {r['group2']}  diff={r['diff']}  p={r['p_adj']:.4f}")
    print("\n结论:", res["conclusion"])
    outdir = Path(args.output)
    p = emit(res, "json", outdir, f"topic_{args.group_by}_{args.metric}")
    print("Topic 深挖输出: ", p)


def cmd_camp(args):
    df, meta, multi = _load(args)
    res = camp_analysis(df, meta, metric=args.metric)
    print("== 品牌阵营 × 价位段结构分析 ==")
    for e in res["evidence"]:
        print("  ", e)
    print("\n说明:", res["conclusion"])
    outdir = Path(args.output)
    p = emit(res, "json", outdir, "camp_analysis")
    print("输出: ", p)


def cmd_config_scan(args):
    df, meta, multi = _load(args)
    res = config_scan(df, meta, multi, metrics=args.metric, top=args.top, min_has=args.min_has)
    rows = res["rows"]
    print(f"配置归因扫描 {len(rows)} 组 (配置 x 指标)，Top {args.top} 按效应量排序:")
    for r in res["top"]:
        print(f"  {r['config'][:40]:<42} × {r['metric']:<12} 有={r['wmean_has']} 无={r['wmean_not']} "
              f"Δ={r['diff']:+.1f}  p={r['p']:.2g}  d={r['cohens_d']}")
    outdir = Path(args.output)
    p = emit(rows, args.format, outdir, "config_attribution_scan")
    print("完整结果: ", p)


def cmd_preference(args):
    df, meta, multi = _load(args)
    res = preference_analysis(df, meta)
    rows = res["rows"]
    print(f"识别到 {len(rows)} 道偏好题（最喜欢/最需改进），按有效回答排序:")
    for r in rows[:20]:
        opts = ", ".join(f"{o['label'][:22]}={o['pct']}%" for o in r["top_options"][:3])
        print(f"  {r['variable']:<16} n={r['n_valid']:<6} {opts}")
    outdir = Path(args.output)
    p = emit(rows, args.format, outdir, "preference_analysis")
    print("完整结果: ", p)


if __name__ == "__main__":
    main()
