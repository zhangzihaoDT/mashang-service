"""
name: pk_weekly_compare
use: python research_scripts/pk_weekly_compare.py --series LS6 --weeks 2026-09-21~2026-09-27 2026-09-07~2026-09-13
summary: 读取"正反向对比"CSV，按显式指定周（或最近 N 周）对比任意车型的 PK次数、PK正向排名、PK反向排名，输出 Markdown / HTML / JSON。
inputs:
  - schema/data_path.md（读取"正反向对比"路径）；--data-csv 可直接指定
  - schema/business_definition.json（6 座车型标记）
outputs:
  - stdout：Markdown 表格（terminal）
  - outputs/reports/pk_weekly_compare_<series>_<range>.html（默认，可用 --output/--html-out 覆盖）
  - --format json：标准 Result Contract

用法：
  # 显式指定周（推荐）：对比 LS6 的两周
  python research_scripts/pk_weekly_compare.py --series LS6 \
      --weeks 2026-09-21~2026-09-27 2026-09-07~2026-09-13

  # 兼容旧用法：最近 N 周
  python research_scripts/pk_weekly_compare.py --series LS8 LS9 -n 7
  python research_scripts/pk_weekly_compare.py --series LS6 --first-week 9 -n 2
"""

import argparse
from collections.abc import Callable
import glob
import html as html_lib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _ROOT.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict:
    return json.loads(_read_text(path))


def _read_data_paths(md_path: Path) -> dict[str, Path]:
    raw = _read_text(md_path).splitlines()
    out: dict[str, Path] = {}
    for line in raw:
        line = line.strip()
        if not line or line.startswith("---"):
            continue
        if "：" in line:
            name, path = line.split("：", 1)
        elif ":" in line:
            name, path = line.split(":", 1)
        else:
            continue
        name = name.strip()
        path = path.strip().replace("\\_", "_").replace("\\*", "*")
        expanded = glob.glob(path)
        if expanded:
            expanded = sorted(expanded, key=lambda p: (len(p), p))
            out[name] = Path(expanded[0])
        else:
            out[name] = Path(path)
    return out


def _read_csv_smart(path: Path) -> pd.DataFrame:
    last_err: Exception | None = None
    for enc in ("utf-8-sig", "utf-16", "gb18030", "gbk"):
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception as e:
            last_err = e
    raise RuntimeError(f"读取 CSV 失败: {path} (last_error={type(last_err).__name__}: {last_err})")


def _to_number_series(x: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(x):
        return x.astype(float)
    return pd.to_numeric(
        x.astype(str).str.replace(",", "", regex=False).str.strip(),
        errors="coerce",
    )


def _parse_week_start(s: str) -> pd.Timestamp:
    t = str(s).strip()
    t = t.replace("～", "~").replace("—", "~").replace("–", "~").replace("－", "-")
    t = t.replace(" ", "")
    if "~" not in t:
        raise ValueError(f"Week 字段无法解析（缺少 ~ / ～）：{s!r}")
    start_s, end_s = t.split("~", 1)
    start = pd.to_datetime(start_s, errors="raise")
    end_s = end_s.strip()
    if len(end_s) == 5 and end_s[2] == "-":
        end_s = f"{start.year}-{end_s}"
    _ = pd.to_datetime(end_s, errors="coerce")
    return pd.Timestamp(start).normalize()


def _week_monday(d: pd.Timestamp) -> pd.Timestamp:
    d = pd.Timestamp(d).normalize()
    return d - pd.Timedelta(days=int(d.weekday()))


def _parse_week_arg(s: str) -> pd.Timestamp:
    """解析 CLI 周参数：``2026-09-21~2026-09-27`` 或单日 ``2026-09-21`` → 周起始日。"""
    t = str(s).strip()
    if any(sep in t for sep in ("~", "～", "—", "–")):
        return _parse_week_start(t)
    ts = pd.to_datetime(t, errors="raise")
    return pd.Timestamp(ts).normalize()


def _week_range_label(ws: pd.Timestamp) -> str:
    """周起始日 → ``MM-DD~MM-DD`` 展示标签。"""
    return f"{ws.strftime('%m-%d')}~{(ws + pd.Timedelta(days=6)).strftime('%m-%d')}"


def _iso_week_label(dt: pd.Timestamp) -> str:
    iso_year, iso_week, _ = dt.isocalendar()
    return f"W{iso_week:02d}"

def _week_cols(week_labels: list[str]) -> list[str]:
    return ["对比车系"] + week_labels


def _to_raw_str(x: pd.Series) -> pd.Series:
    s = x.astype("string")
    s = s.where(s.notna(), None)
    s = s.map(lambda v: str(v).strip() if v is not None else None)
    return s.replace({"nan": None, "None": None})


def _normalize_model_name(s: str) -> str:
    t = str(s or "").strip()
    t = t.replace("　", " ").strip()
    t = t.replace(" ", "")
    if t.upper().startswith("ZEEKR"):
        t = "极氪" + t[len("ZEEKR"):]
    u = t.upper()
    if u.endswith("REEV"):
        t = t[:-4]
    elif u.endswith("EV"):
        t = t[:-2]
    return t


def _is_six_seat_model(model_name: str, six_seat_models_norm: set[str]) -> bool:
    x = _normalize_model_name(model_name)
    if not x:
        return False
    for m in six_seat_models_norm:
        if not m:
            continue
        if x == m or x.startswith(m):
            return True
    return False


@dataclass(frozen=True)
class SeriesWindow:
    series: str
    end_date: pd.Timestamp
    base_week_monday: pd.Timestamp
    num_weeks: int


def _resolve_series_windows(business_definition: dict, series_list: list[str]) -> list[SeriesWindow]:
    tp = business_definition.get("time_periods") or {}
    out: list[SeriesWindow] = []
    for s in series_list:
        if s not in tp:
            raise KeyError(f"business_definition.time_periods 中未找到 {s!r}")
        end_s = (tp[s] or {}).get("end")
        if not end_s:
            raise KeyError(f"business_definition.time_periods.{s}.end 为空")
        end_date = pd.to_datetime(end_s, errors="raise").normalize()
        base_week_monday = _week_monday(end_date)
        out.append(SeriesWindow(series=s, end_date=end_date, base_week_monday=base_week_monday, num_weeks=0))
    return out


def _format_markdown_table(title: str, df: pd.DataFrame) -> str:
    cols = df.columns.tolist()
    df = df.loc[:, cols].copy()

    def _cell(v) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        return str(v)

    lines = [f"\n## {title}", "", "| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(_cell(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def _build_week_ranges(w: SeriesWindow, first_week: int = 1) -> dict[int, tuple[pd.Timestamp, pd.Timestamp]]:
    out: dict[int, tuple[pd.Timestamp, pd.Timestamp]] = {}
    for i in range(first_week, first_week + w.num_weeks):
        start = w.base_week_monday + pd.Timedelta(days=7 * (i - 1))
        end = start + pd.Timedelta(days=6)
        out[i] = (start, end)
    return out


def _render_html_table(
    df: pd.DataFrame,
    week_sublabels: dict[str, str],
    *,
    cell_html: Callable[[pd.Series, str], str] | None = None,
) -> str:
    cols = df.columns.tolist()
    df = df.loc[:, cols].copy()

    parts: list[str] = ['<table class="report-table">', "<thead>", "<tr>"]
    for c in cols:
        if c in week_sublabels and week_sublabels[c]:
            parts.append(
                f"<th>{html_lib.escape(c)}<span class=\"sub\">{week_sublabels[c]}</span></th>"
            )
        else:
            parts.append(f"<th>{html_lib.escape(c)}</th>")
    parts.extend(["</tr>", "</thead>", "<tbody>"])

    for _, r in df.iterrows():
        parts.append("<tr>")
        for c in cols:
            if cell_html is not None:
                parts.append(f"<td>{cell_html(r, c)}</td>")
            else:
                v = r.get(c, "")
                s = "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)
                parts.append(f"<td>{html_lib.escape(s)}</td>")
        parts.append("</tr>")
    parts.extend(["</tbody>", "</table>"])
    return "\n".join(parts)


def _format_html_report(
    title: str,
    meta_lines: list[str],
    blocks: list[tuple[str, pd.DataFrame, dict[str, str]]],
) -> str:
    parts: list[str] = [
        "<!doctype html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8" />',
        '<meta name="viewport" content="width=device-width, initial-scale=1" />',
        f"<title>{title}</title>",
        '<link rel="stylesheet" href="../../templates/report_style.css">',
        "<style>",
        "body{margin:24px;background:var(--zh-bg);color:var(--zh-text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;}",
        "h1{margin:0 0 12px 0;font-size:20px;color:var(--zh-blue);border-left:4px solid var(--zh-blue);padding-left:12px;}",
        "h2{margin:18px 0 8px 0;font-size:16px;color:var(--zh-deep-blue);}",
        ".meta{margin:0 0 12px 0;padding:12px 14px;background:var(--zh-panel);border:1px solid var(--zh-border);border-radius:8px;}",
        ".meta ul{margin:0;padding-left:18px;}",
        "table{border-collapse:collapse;width:100%;margin:8px 0 18px 0;}",
        "th .sub{display:block;font-size:11px;color:var(--zh-muted);margin-top:2px;font-weight:400;line-height:1.25;text-transform:none;letter-spacing:0;}",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>{title}</h1>",
        '<div class="meta">',
        "<ul>",
    ]
    for line in meta_lines:
        s = str(line).strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("- "):
            s = s[2:]
        parts.append(f"<li>{s}</li>")
    parts.extend(["</ul>", "</div>"])

    for t, df, week_sublabels in blocks:
        parts.append(f"<h2>{t}</h2>")
        if "_cell_html" in df.attrs and callable(df.attrs["_cell_html"]):
            parts.append(
                _render_html_table(
                    df,
                    week_sublabels=week_sublabels,
                    cell_html=df.attrs["_cell_html"],
                )
            )
        else:
            parts.append(_render_html_table(df, week_sublabels=week_sublabels))

    parts.extend(["</body>", "</html>"])
    return "\n".join(parts)


def _build_metric_pivot(sub: pd.DataFrame, value_col: str, week_labels: list[str]) -> pd.DataFrame:
    s = sub.copy()
    s[value_col] = _to_raw_str(s[value_col])
    cols = _week_cols(week_labels)
    pivot = (
        s.pivot_table(
            index="车系",
            columns="wk_index",
            values=value_col,
            aggfunc="first",
            dropna=False,
        )
        .rename(columns={i: week_labels[i - 1] for i in range(1, len(week_labels) + 1)})
        .reset_index()
        .rename(columns={"车系": "对比车系"})
    )
    for lbl in week_labels:
        if lbl not in pivot.columns:
            pivot[lbl] = ""
    pivot = pivot[cols].copy()
    pivot = pivot.sort_values(by=["对比车系"], kind="mergesort").reset_index(drop=True)
    return pivot


def _build_pk_num_pivot(sub: pd.DataFrame, week_labels: list[str]) -> pd.DataFrame:
    s = sub.copy()
    s["PK次数_num"] = _to_number_series(s["PK次数"])
    cols = _week_cols(week_labels)
    pivot = (
        s.pivot_table(
            index="车系",
            columns="wk_index",
            values="PK次数_num",
            aggfunc="first",
            dropna=False,
        )
        .rename(columns={i: week_labels[i - 1] for i in range(1, len(week_labels) + 1)})
        .reset_index()
        .rename(columns={"车系": "对比车系"})
    )
    for lbl in week_labels:
        if lbl not in pivot.columns:
            pivot[lbl] = float("nan")
    pivot = pivot[cols].copy()
    pivot = pivot.sort_values(by=["对比车系"], kind="mergesort").reset_index(drop=True)
    return pivot


def _build_rank_pivot(sub: pd.DataFrame, value_col: str, week_labels: list[str]) -> pd.DataFrame:
    return _build_metric_pivot(sub, value_col=value_col, week_labels=week_labels)


def _attach_rank_bar_cells(rank_df: pd.DataFrame, pk_num_df: pd.DataFrame) -> pd.DataFrame:
    cols = rank_df.columns.tolist()
    pk_num_df = pk_num_df.loc[:, cols].copy()
    week_cols = [c for c in cols if c != "对比车系"]
    pk_max = float(pd.to_numeric(pk_num_df[week_cols].stack(), errors="coerce").max())
    if not (pk_max > 0):
        pk_max = 0.0

    def _cell_html(row: pd.Series, col: str) -> str:
        if col == "对比车系":
            v0 = row.get(col, "")
            s0 = "" if v0 is None or (isinstance(v0, float) and pd.isna(v0)) else str(v0)
            return html_lib.escape(s0)

        v = row.get(col, "")
        rank_s = "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)

        pk_row = pk_num_df[pk_num_df["对比车系"] == row.get("对比车系")]
        pk = None
        if len(pk_row) == 1:
            pk = pk_row.iloc[0].get(col)
        pk_num = float(pd.to_numeric(pd.Series([pk]), errors="coerce").iloc[0]) if pk is not None else float("nan")

        width = 0
        if pk_max > 0 and pd.notna(pk_num):
            width = int(round(100.0 * pk_num / pk_max))
            width = max(0, min(100, width))

        title = ""
        if pd.notna(pk_num):
            title = f' title="PK次数: {int(round(pk_num))}"'
        bar = f'<div class="bar" style="width:{width}%;"></div>' if width > 0 else '<div class="bar" style="width:0%;"></div>'
        return f'<div class="barcell"{title}>{bar}<div class="txt">{html_lib.escape(rank_s)}</div></div>'

    rank_df.attrs["_cell_html"] = _cell_html
    return rank_df


def _attach_rank_bar_cells_with_six_seat(
    rank_df: pd.DataFrame,
    pk_num_df: pd.DataFrame,
    *,
    six_seat_models_norm: set[str],
) -> pd.DataFrame:
    cols = rank_df.columns.tolist()
    pk_num_df = pk_num_df.loc[:, cols].copy()
    week_cols = [c for c in cols if c != "对比车系"]
    pk_max = float(pd.to_numeric(pk_num_df[week_cols].stack(), errors="coerce").max())
    if not (pk_max > 0):
        pk_max = 0.0

    def _cell_html(row: pd.Series, col: str) -> str:
        model_name = row.get("对比车系", "")
        is_six = _is_six_seat_model(str(model_name), six_seat_models_norm)

        if col == "对比车系":
            v0 = row.get(col, "")
            s0 = "" if v0 is None or (isinstance(v0, float) and pd.isna(v0)) else str(v0)
            badge = '<span class="badge-six-seat">6座</span>' if is_six else ""
            return f"{html_lib.escape(s0)}{badge}"

        v = row.get(col, "")
        rank_s = "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)

        pk_row = pk_num_df[pk_num_df["对比车系"] == model_name]
        pk = None
        if len(pk_row) == 1:
            pk = pk_row.iloc[0].get(col)
        pk_num = float(pd.to_numeric(pd.Series([pk]), errors="coerce").iloc[0]) if pk is not None else float("nan")

        width = 0
        if pk_max > 0 and pd.notna(pk_num):
            width = int(round(100.0 * pk_num / pk_max))
            width = max(0, min(100, width))

        title = ""
        if pd.notna(pk_num):
            title = f' title="PK次数: {int(round(pk_num))}"'

        bar_class = "bar six" if is_six else "bar"
        bar = f'<div class="{bar_class}" style="width:{width}%;"></div>' if width > 0 else f'<div class="{bar_class}" style="width:0%;"></div>'
        return f'<div class="barcell"{title}>{bar}<div class="txt">{html_lib.escape(rank_s)}</div></div>'

    rank_df.attrs["_cell_html"] = _cell_html
    return rank_df


def _sort_by_last_week_pk(rank_df: pd.DataFrame, pk_num_df: pd.DataFrame,
                          sort_col: str | None = None) -> pd.DataFrame:
    cols = rank_df.columns.tolist()
    pk_num_df = pk_num_df.loc[:, cols].copy()
    sort_col = sort_col or cols[-1]
    key = pd.to_numeric(pk_num_df[sort_col], errors="coerce")
    key = key.fillna(-1)
    pk_num_df["_sort_key"] = key
    merged = rank_df.merge(pk_num_df[["对比车系", "_sort_key"]], on="对比车系", how="left")
    merged["_sort_key"] = pd.to_numeric(merged["_sort_key"], errors="coerce").fillna(-1)
    merged = merged.sort_values(by=["_sort_key", "对比车系"], ascending=[False, True], kind="mergesort")
    merged = merged.drop(columns=["_sort_key"]).reset_index(drop=True)
    return merged


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    recs: list[dict] = []
    for _, r in df.iterrows():
        rec: dict = {}
        for c in df.columns:
            v = r[c]
            rec[str(c)] = None if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v)
        recs.append(rec)
    return recs


def _safe_tag(s: str) -> str:
    return str(s).replace("/", "-").replace(" ", "").replace("~", "_").replace(":", "")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="竞争 PK 周度对比（泛化：显式指定车型与对比周）")
    p.add_argument("--data-path-md", default=str(_PROJECT_ROOT / "shared" / "schema" / "data_path.md"))
    p.add_argument(
        "--business-definition",
        default=str(_PROJECT_ROOT / "shared" / "schema" / "business_definition.json"),
    )
    p.add_argument("--data-csv", default=None, help='可选：直接指定"正反向对比"CSV 路径（覆盖 data_path.md）')
    p.add_argument("--series", nargs="*", default=["LS8", "LS9"], help="对比车型（series），如 LS6")
    p.add_argument(
        "--weeks", nargs="+", default=None,
        help="显式周区间（推荐，按传入顺序展示）：如 2026-09-21~2026-09-27 2026-09-07~2026-09-13；也可只给起始日 2026-09-21",
    )
    p.add_argument("-n", "--num-weeks", type=int, default=4,
                   help="兼容模式：最近 N 周（未指定 --weeks 时生效）；0 = 全部")
    p.add_argument("--first-week", type=int, default=None,
                   help="兼容模式：起始周索引（从 1 开始），配合 -n；如 --first-week 9 -n 2")
    p.add_argument("--format", choices=["terminal", "json", "html"], default="html")
    p.add_argument("--output", default=None, help="输出目录或文件（html/json）")
    p.add_argument("--html-out", default=None, help="[兼容] HTML 输出路径；等价 --format html --output <path>")
    p.add_argument("--no-stdout", action="store_true", help="仅写文件，不输出 stdout Markdown")
    args = p.parse_args(argv)

    if args.html_out:
        args.format = "html"
        args.output = args.html_out

    business_definition = _load_json(Path(args.business_definition))
    six_seat_models = (
        (business_definition.get("business_knowledge") or {})
        .get("main_selling_models_seats_6", {})
        .get("models", [])
    )
    six_seat_models_norm = {_normalize_model_name(x) for x in (six_seat_models or [])}

    csv_path = Path(args.data_csv) if args.data_csv else None
    if csv_path is None:
        data_paths = _read_data_paths(Path(args.data_path_md))
        if "正反向对比" not in data_paths:
            raise KeyError(f"未在 {args.data_path_md} 中找到 '正反向对比' 的数据路径")
        csv_path = data_paths["正反向对比"]
    if not csv_path.exists():
        raise FileNotFoundError(f"找不到数据文件: {csv_path}")

    df = _read_csv_smart(csv_path)
    required_cols = {"Week", "series", "PK次数", "PK正向排名", "PK反向排名"}
    missing = required_cols - set(df.columns)
    if missing:
        raise KeyError(f"CSV 缺少必要列: {sorted(missing)}; 实际列={list(df.columns)}")

    df = df.copy()
    df["week_start"] = df["Week"].map(_parse_week_start)
    df["PK次数_num"] = _to_number_series(df["PK次数"]).fillna(0.0)

    all_week_starts = sorted(df["week_start"].unique())
    avail = set(all_week_starts)
    warnings: list[str] = []
    missing_weeks: list[pd.Timestamp] = []

    if args.weeks:
        mode = "explicit"
        raw = [_parse_week_arg(w) for w in args.weeks]
        seen: set[pd.Timestamp] = set()
        selected_week_starts = [ws for ws in raw if not (ws in seen or seen.add(ws))]
        missing_weeks = [ws for ws in selected_week_starts if ws not in avail]
        if missing_weeks:
            warnings.append("以下指定周在数据源中无记录：" + "; ".join(
                f"{ws.date()}~{(ws + pd.Timedelta(days=6)).date()}" for ws in missing_weeks))
        num_weeks = len(selected_week_starts)
    else:
        mode = "recent"
        num_weeks = args.num_weeks if 0 < args.num_weeks <= len(all_week_starts) else len(all_week_starts)
        if args.first_week is not None:
            start_idx = max(0, args.first_week - 1)
            selected_week_starts = all_week_starts[start_idx:start_idx + num_weeks]
        else:
            selected_week_starts = all_week_starts[-num_weeks:]

    if not selected_week_starts:
        raise SystemExit("❌ 未选定任何周，请检查 --weeks / -n 参数")

    ws_to_pos = {ws: i + 1 for i, ws in enumerate(selected_week_starts)}
    week_labels = [_week_range_label(ws) for ws in selected_week_starts]
    week_sublabels = {lbl: _iso_week_label(ws) for lbl, ws in zip(week_labels, selected_week_starts)}
    # 显式模式下按第一周（主周）PK次数降序；兼容模式沿用最后一周
    sort_col = week_labels[0] if mode == "explicit" else None

    pos_tables: list[tuple[str, pd.DataFrame, dict[str, str]]] = []
    neg_tables: list[tuple[str, pd.DataFrame, dict[str, str]]] = []
    pk_sum_tables: list[tuple[str, pd.DataFrame, dict[str, str]]] = []
    missing_series: list[str] = []

    for series in args.series:
        sub = df[df["series"].astype(str).str.upper() == series.upper()].copy()
        if sub.empty:
            missing_series.append(series)
            warnings.append(f"数据源中未找到车型 {series}")
            continue

        sub = sub[sub["week_start"].isin(selected_week_starts)].copy()
        if sub.empty:
            warnings.append(f"{series} 在所选周（{'、'.join(week_labels)}）无 PK 记录")
            continue
        sub["wk_index"] = sub["week_start"].map(ws_to_pos)

        pk_by_week = sub.groupby("wk_index", as_index=True)["PK次数_num"].sum().to_dict()
        pk_row: dict[str, str] = {"对比车系": series}
        for i, lbl in enumerate(week_labels, 1):
            pk_row[lbl] = str(int(round(float(pk_by_week.get(i, 0.0)))))
        pk_sum_tables.append((f"{series} - PK次数（sum）", pd.DataFrame([pk_row]), week_sublabels))

        pk_num = _build_pk_num_pivot(sub, week_labels=week_labels)

        pos_rank = _sort_by_last_week_pk(
            _build_rank_pivot(sub, "PK正向排名", week_labels=week_labels), pk_num, sort_col=sort_col)
        pos_tables.append((
            f"{series} - PK正向排名",
            _attach_rank_bar_cells_with_six_seat(pos_rank, pk_num, six_seat_models_norm=six_seat_models_norm),
            week_sublabels,
        ))

        neg_rank = _sort_by_last_week_pk(
            _build_rank_pivot(sub, "PK反向排名", week_labels=week_labels), pk_num, sort_col=sort_col)
        neg_tables.append((
            f"{series} - PK反向排名",
            _attach_rank_bar_cells_with_six_seat(neg_rank, pk_num, six_seat_models_norm=six_seat_models_norm),
            week_sublabels,
        ))

    series_names = "、".join(args.series)
    first_lbl, last_lbl = week_labels[0], week_labels[-1]
    if mode == "explicit":
        meta_title = f"{series_names} PK 对比（{first_lbl} / {last_lbl}）"
    else:
        meta_title = f"{series_names} 近{num_weeks}周 PK 对比（{first_lbl} ~ {last_lbl}）"
    meta_lines = [f"# {meta_title}", ""]
    meta_lines.append(f"- 车型: {series_names}｜周数: {len(selected_week_starts)}")
    meta_lines.append("- 周次: " + "; ".join(
        f"{lbl}={_iso_week_label(ws)}" for lbl, ws in zip(week_labels, selected_week_starts)))
    meta_lines += [f"- ⚠️ {w}" for w in warnings]

    blocks = [*pk_sum_tables, *pos_tables, *neg_tables]

    if args.format == "html":
        if args.output:
            op = Path(args.output)
            html_path = op if op.suffix.lower() == ".html" else (
                op / f"pk_weekly_compare_{_safe_tag(series_names)}_{_safe_tag(first_lbl)}.html")
        else:
            html_path = (_ROOT / "outputs" / "reports"
                         / f"pk_weekly_compare_{_safe_tag(series_names)}_{_safe_tag(first_lbl)}.html")
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(
            _format_html_report(title=meta_title, meta_lines=meta_lines, blocks=blocks), encoding="utf-8")
        if not args.no_stdout:
            print("\n".join(meta_lines))
            for title, tdf, _ in blocks:
                print(_format_markdown_table(title, tdf))
            print(f"\nHTML: {html_path}")
        return

    if args.format == "json":
        contract = {
            "status": "success",
            "script": "research_scripts/pk_weekly_compare.py",
            "scope": {
                "data_source": str(csv_path),
                "time_window": {
                    "mode": mode,
                    "weeks": week_labels,
                    "week_starts": [ws.date().isoformat() for ws in selected_week_starts],
                },
                "filters": {"series": args.series},
                "metric_definition": "竞争PK：PK次数 / PK正向排名 / PK反向排名（周度；排名越小越强）",
            },
            "result": {
                "summary": meta_title,
                "tables": [
                    {"name": title, "columns": [str(c) for c in tdf.columns], "rows": _df_to_records(tdf)}
                    for title, tdf, _ in blocks
                ],
                "missing_weeks": [ws.date().isoformat() for ws in missing_weeks],
                "missing_series": missing_series,
            },
            "artifacts": {},
            "followup_context": {"metric": "pk_weekly_compare", "series": args.series,
                                 "available_dimensions": ["series", "week"]},
            "warnings": warnings,
            "errors": [],
        }
        if args.output:
            op = Path(args.output)
            json_path = op if op.suffix.lower() == ".json" else (
                op / f"pk_weekly_compare_{_safe_tag(series_names)}.json")
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"已输出: {json_path}")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
        return

    print("\n".join(meta_lines))
    for title, tdf, _ in blocks:
        print(_format_markdown_table(title, tdf))


if __name__ == "__main__":
    main()
