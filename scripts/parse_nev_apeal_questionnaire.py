#!/usr/bin/env python
"""
parse_nev_apeal_questionnaire.py — 解析 NEV-APEAL 问卷 PDF 结构并与 SAV 变量映射

读取 2024 中国新能源汽车产品魅力指数研究 (NEV-APEAL)_问卷.pdf，
提取每个问题的 编号 / 题干 / 题型，然后与 .sav 数据的 370 个变量建立映射，
标注映射状态（完全匹配 / 部分匹配 / SAV 中缺失 / 非 SAV 题）。

用法:
    python scripts/parse_nev_apeal_questionnaire.py
    python scripts/parse_nev_apeal_questionnaire.py --output outputs/reports/nev_apeal_questionnaire_map.md
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import pyreadstat
except ImportError:
    pyreadstat = None

SERVICE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF = SERVICE_ROOT / "dataset" / "2024年中国新能源汽车产品魅力指数研究 (NEV-APEAL)_问卷.pdf"
DEFAULT_SAV = SERVICE_ROOT / "dataset" / "24 NEV-APEAL数据片段.sav"
DEFAULT_OUTPUT = SERVICE_ROOT / "outputs" / "reports" / "nev_apeal_questionnaire_map.md"

# 题型关键词（中英文混合，用于从题干尾部识别）
SINGLE_MARKERS = ["单选"]
MULTI_MARKERS = ["可多选", "多选"]
MATRIX_MARKERS = ["每列单选", "每行单选", "单选\n"]
FILL_MARKERS = ["填写", "开放题"]

# 页脚版权行，用于过滤
FOOTER_RE = re.compile(r"© 2024 J\.D\. Power")

# 问题编号正则：大写字母开头的编号，如 SCR_BODYTYPE, NEV_01, AEXT_R_01
QID_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s+")


def extract_pages(pdf_path: str) -> List[str]:
    if pdfplumber is None:
        raise SystemExit("缺少 pdfplumber，请先 pip install pdfplumber")
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            out.append(page.extract_text() or "")
    return out


def detect_type(line: str) -> str:
    """从题干行推断题型。"""
    if any(m in line for m in MULTI_MARKERS):
        return "可多选"
    if any(m in line for m in ("每列单选", "每行单选")):
        return "每列单选"
    if any(m in line for m in FILL_MARKERS):
        return "填写"
    if any(m in line for m in SINGLE_MARKERS):
        return "单选"
    return "单选"


def parse_questions(pages: List[str]) -> List[Dict[str, Any]]:
    """逐页提取问题：编号 + 题干（首行）。"""
    questions: List[Dict[str, Any]] = []
    for pidx, page in enumerate(pages):
        lines = page.split("\n")
        for line in lines:
            if FOOTER_RE.search(line):
                continue
            if line.strip() in ("问题编号", "问题", "题型", "开始"):
                continue
            m = QID_RE.match(line)
            if not m:
                continue
            qid = m.group(1)
            # 过滤干扰项
            if qid in ("J", "D", "Power", "2024", "NEV", "APEAL", "R1", "R2", "R3"):
                continue
            # 题干 = 编号之后的内容（去掉首尾空白）
            rest = line[m.end():].strip()
            # 过滤纯选项行（如 "1 是" "0 否"）
            if re.match(r"^\d+\s+\S", rest) and len(rest) < 40:
                continue
            qtype = detect_type(line)
            questions.append({
                "qid": qid,
                "question": rest,
                "type": qtype,
                "page": pidx + 1,
            })
    # 去重（同编号可能跨页重复出现）
    seen = set()
    uniq = []
    for q in questions:
        if q["qid"] in seen:
            continue
        seen.add(q["qid"])
        uniq.append(q)
    return uniq


def load_sav_vars(sav_path: str) -> Dict[str, Any]:
    if pyreadstat is None:
        raise SystemExit("缺少 pyreadstat，请先 pip install pyreadstat")
    df, meta = pyreadstat.read_sav(str(sav_path), user_missing=True)
    cols = list(df.columns)
    col2label = dict(zip(meta.column_names, meta.column_labels)) if meta.column_labels else {}
    indices = [c for c in cols if c.endswith("_Index") or c in ("APEAL_WT", "APEAL_Index")]
    return {"columns": cols, "col2label": col2label, "indices": indices}


def match_qid(qid: str, sav_cols: List[str]) -> str:
    """判断问卷编号与 SAV 列的匹配状态。

    returns: exact | partial | missing
    """
    if qid in sav_cols:
        return "exact"
    # 部分匹配：SAV 列以 qid 开头（如 AEXT_R_01 → SAV 中 AEXT_R_01 本身，或带后缀）
    partials = [c for c in sav_cols if c.startswith(qid) or qid.startswith(c)]
    if partials:
        return "partial"
    # 后缀规则：NEV_11A → SAV 中 NEV_11A; SCR_G_2 → SAV 中 SCR_G_2_R1..R97
    prefix = qid
    if re.match(r".*_R\d+$", qid):
        prefix = qid.rsplit("_R", 1)[0]
    if prefix in sav_cols or any(c.startswith(prefix + "_") for c in sav_cols):
        return "partial"
    return "missing"


def get_matched_cols(qid: str, sav_cols: List[str]) -> List[str]:
    """返回与 qid 匹配的 SAV 列名列表。"""
    if qid in sav_cols:
        return [qid]
    out = [c for c in sav_cols if c.startswith(qid) or qid.startswith(c)]
    prefix = re.sub(r"_R\d+$", "", qid)
    out += [c for c in sav_cols if c.startswith(prefix + "_")]
    # 去重保序
    seen, res = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            res.append(c)
    return res


def render_md(questions: List[Dict[str, Any]], sav: Dict[str, Any],
              qid2cols: Dict[str, List[str]]) -> str:
    cols = sav["columns"]
    col2label = sav["col2label"]
    total = len(questions)
    stats = {"exact": 0, "partial": 0, "missing": 0}
    for q in questions:
        stats[match_qid(q["qid"], cols)] += 1

    lines = ["# NEV-APEAL 2024 问卷结构与 SAV 变量映射", ""]
    lines.append(f"> 问卷：2024 年中国新能源汽车产品魅力指数研究 (NEV-APEAL)_问卷.pdf")
    lines.append(f"> SAV：dataset/24 NEV-APEAL数据片段.sav（{len(cols)} 个变量）")
    lines.append(f"> 问卷题数：{total} | 完全匹配 {stats['exact']} | 部分匹配 {stats['partial']} | SAV 中缺失 {stats['missing']}")
    lines.append("")

    # 直接输出表格形式（按页分组）
    rows = []
    for q in questions:
        qid = q["qid"]
        status = match_qid(qid, cols)
        matched = qid2cols.get(qid, [])
        status_txt = {"exact": "✅ 完全匹配", "partial": "⚠️ 部分匹配", "missing": "❌ SAV 缺失"}[status]
        if matched:
            sav_txt = ", ".join(f"`{c}`" for c in matched)
        else:
            sav_txt = "—"
        rows.append((q["page"], qid, q["question"], q["type"], status_txt, sav_txt))

    # 按页分组输出
    cur_page = 0
    for page, qid, q, t, st, sv in rows:
        if page != cur_page:
            lines.append(f"\n## 第 {page} 页")
            lines.append("")
            lines.append("| Q编号 | 题目 | 题型 | 映射 | SAV 变量 |")
            lines.append("|-------|------|------|------|----------|")
            cur_page = page
        q_esc = q.replace("|", "\\|")
        lines.append(f"| `{qid}` | {q_esc} | {t} | {st} | {sv} |")

    # 附录：SAV 中的派生指数/权重列
    lines.append("\n## 附录 · SAV 中的派生指数/权重列（问卷中无对应题）")
    lines.append("")
    for c in sav["indices"]:
        lbl = col2label.get(c, "")
        lines.append(f"- `{c}` — {lbl}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description="解析 NEV-APEAL 问卷 PDF 并映射 SAV 变量")
    p.add_argument("--pdf", default=str(DEFAULT_PDF), help="问卷 PDF 路径")
    p.add_argument("--sav", default=str(DEFAULT_SAV), help=".sav 数据路径")
    p.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Markdown 输出路径")
    args = p.parse_args()

    pages = extract_pages(args.pdf)
    questions = parse_questions(pages)
    sav = load_sav_vars(args.sav)
    qid2cols = {q["qid"]: get_matched_cols(q["qid"], sav["columns"]) for q in questions}

    md = render_md(questions, sav, qid2cols)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")

    # JSON 结构数据
    json_out = out.with_suffix(".json")
    payload = {
        "questions": questions,
        "qid2cols": qid2cols,
        "n_sav_vars": len(sav["columns"]),
    }
    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # 终端摘要
    from collections import Counter
    statuses = Counter(match_qid(q["qid"], sav["columns"]) for q in questions)
    print(f"问卷题数: {len(questions)}")
    print(f"映射状态: {dict(statuses)}")
    print(f"SAV 变量数: {len(sav['columns'])}")
    print(f"Markdown: {out}")
    print(f"JSON: {json_out}")


if __name__ == "__main__":
    main()
