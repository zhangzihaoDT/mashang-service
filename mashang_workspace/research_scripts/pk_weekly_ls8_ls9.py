"""
name: pk_weekly_compare_ls8_ls9
use: python research_scripts/pk_weekly_ls8_ls9.py -n 7
updated_at: "2026-05-27"
summary: 读取"正反向对比"CSV，对比 LS8/LS9 在（end day 所在周的周一）起算连续 N 周的 PK次数、PK正向排名、PK反向排名，并输出 N 个表格到 stdout。
inputs:
  - schema/data_path.md（读取"正反向对比"路径）
  - schema/business_definition.json（读取 time_periods.<series>.end）
outputs:
  - stdout：Markdown 表格
  - outputs/reports/pk_weekly_compare_ls8_ls9.html（默认）
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


def _week_cols(num_weeks: int) -> list[str]:
    return ["对比车系"] + [f"第{i}周" for i in range(1, num_weeks + 1)]


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
    lines = [f"\n## {title}", "", "| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def _build_week_ranges(w: SeriesWindow) -> dict[int, tuple[pd.Timestamp, pd.Timestamp]]:
    out: dict[int, tuple[pd.Timestamp, pd.Timestamp]] = {}
    for i in range(1, w.num_weeks + 1):
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

    parts: list[str] = ['<table class="t">', "<thead>", "<tr>"]
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
        "<style>",
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,'Noto Sans','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;margin:24px;color:#111;}",
        "h1{margin:0 0 12px 0;font-size:20px;}",
        "h2{margin:18px 0 8px 0;font-size:16px;}",
        ".meta{margin:0 0 12px 0;padding:12px 14px;background:#fafafa;border:1px solid #eee;border-radius:8px;}",
        ".meta ul{margin:0;padding-left:18px;}",
        "table{border-collapse:collapse;width:100%;margin:8px 0 18px 0;}",
        "th,td{border:1px solid #e5e5e5;padding:8px 10px;font-size:13px;}",
        "th{background:#f5f5f5;text-align:left;}",
        "td{text-align:left;}",
        "th .sub{display:block;font-size:11px;color:#666;margin-top:2px;font-weight:400;line-height:1.25;}",
        ".barcell{position:relative;display:block;width:100%;min-height:18px;line-height:18px;}",
        ".barcell .bar{position:absolute;left:0;top:0;bottom:0;background:#3b82f633;border-radius:3px;pointer-events:none;}",
        ".barcell .bar.six{background:#f9731633;}",
        ".barcell .txt{position:relative;z-index:1;font-variant-numeric:tabular-nums;pointer-events:none;}",
        ".badge{display:inline-block;margin-left:6px;padding:1px 6px;border-radius:10px;font-size:11px;line-height:16px;background:#f9731622;color:#9a3412;border:1px solid #f9731633;}",
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


def _build_metric_pivot(sub: pd.DataFrame, value_col: str, num_weeks: int) -> pd.DataFrame:
    s = sub.copy()
    s[value_col] = _to_raw_str(s[value_col])
    cols = _week_cols(num_weeks)
    pivot = (
        s.pivot_table(
            index="车系",
            columns="wk_index",
            values=value_col,
            aggfunc="first",
            dropna=False,
        )
        .rename(columns={i: f"第{i}周" for i in range(1, num_weeks + 1)})
        .reset_index()
        .rename(columns={"车系": "对比车系"})
    )
    for i in range(1, num_weeks + 1):
        c = f"第{i}周"
        if c not in pivot.columns:
            pivot[c] = ""
    pivot = pivot[cols].copy()
    pivot = pivot.sort_values(by=["对比车系"], kind="mergesort").reset_index(drop=True)
    return pivot


def _build_pk_num_pivot(sub: pd.DataFrame, num_weeks: int) -> pd.DataFrame:
    s = sub.copy()
    s["PK次数_num"] = _to_number_series(s["PK次数"])
    cols = _week_cols(num_weeks)
    pivot = (
        s.pivot_table(
            index="车系",
            columns="wk_index",
            values="PK次数_num",
            aggfunc="first",
            dropna=False,
        )
        .rename(columns={i: f"第{i}周" for i in range(1, num_weeks + 1)})
        .reset_index()
        .rename(columns={"车系": "对比车系"})
    )
    for i in range(1, num_weeks + 1):
        c = f"第{i}周"
        if c not in pivot.columns:
            pivot[c] = float("nan")
    pivot = pivot[cols].copy()
    pivot = pivot.sort_values(by=["对比车系"], kind="mergesort").reset_index(drop=True)
    return pivot


def _build_rank_pivot(sub: pd.DataFrame, value_col: str, num_weeks: int) -> pd.DataFrame:
    return _build_metric_pivot(sub, value_col=value_col, num_weeks=num_weeks)


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
            badge = '<span class="badge">6座</span>' if is_six else ""
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


def _sort_by_last_week_pk(rank_df: pd.DataFrame, pk_num_df: pd.DataFrame) -> pd.DataFrame:
    cols = rank_df.columns.tolist()
    pk_num_df = pk_num_df.loc[:, cols].copy()
    last_week_col = cols[-1]
    key = pd.to_numeric(pk_num_df[last_week_col], errors="coerce")
    key = key.fillna(-1)
    pk_num_df["_sort_key"] = key
    merged = rank_df.merge(pk_num_df[["对比车系", "_sort_key"]], on="对比车系", how="left")
    merged["_sort_key"] = pd.to_numeric(merged["_sort_key"], errors="coerce").fillna(-1)
    merged = merged.sort_values(by=["_sort_key", "对比车系"], ascending=[False, True], kind="mergesort")
    merged = merged.drop(columns=["_sort_key"]).reset_index(drop=True)
    return merged


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--data-path-md",
        default=str(_PROJECT_ROOT / "shared" / "schema" / "data_path.md"),
    )
    p.add_argument(
        "--business-definition",
        default=str(_PROJECT_ROOT / "shared" / "schema" / "business_definition.json"),
    )
    p.add_argument(
        "--data-csv",
        default=None,
        help='可选：直接指定"正反向对比"CSV 路径（覆盖 data_path.md）',
    )
    p.add_argument("--series", nargs="*", default=["LS8", "LS9"])
    p.add_argument(
        "-n", "--num-weeks",
        type=int,
        default=0,
        help="对比周数；设为 0 则自动以 LS8 数据最大周为准",
    )
    p.add_argument(
        "--html-out",
        default=str(_ROOT / "outputs" / "reports" / "pk_weekly_compare_ls8_ls9.html"),
        help="HTML 报告输出路径；传空字符串可禁用",
    )
    p.add_argument("--no-stdout", action="store_true", help="不输出 stdout Markdown（仅写 HTML）")
    args = p.parse_args(argv)

    business_definition = _load_json(Path(args.business_definition))
    windows = _resolve_series_windows(business_definition, list(args.series))
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

    max_weeks_by_series: dict[str, int] = {}
    for w in windows:
        sub = df[df["series"].astype(str).str.upper() == w.series.upper()]
        if not sub.empty:
            max_ws = sub["week_start"].max()
            max_weeks_by_series[w.series] = max(1, int((max_ws - w.base_week_monday).days // 7 + 1))
        else:
            max_weeks_by_series[w.series] = 1

    if args.num_weeks <= 0:
        num_weeks = max(max_weeks_by_series.get(s, 1) for s in args.series)
    else:
        num_weeks = args.num_weeks
    windows = [
        SeriesWindow(
            series=w.series, end_date=w.end_date, base_week_monday=w.base_week_monday, num_weeks=num_weeks,
        )
        for w in windows
    ]

    pos_tables: list[tuple[str, pd.DataFrame, dict[str, str]]] = []
    neg_tables: list[tuple[str, pd.DataFrame, dict[str, str]]] = []
    pk_sum_tables: list[tuple[str, pd.DataFrame, dict[str, str]]] = []
    ranges_by_series: dict[str, dict[int, tuple[pd.Timestamp, pd.Timestamp]]] = {}

    for w in windows:
        ranges_by_series[w.series] = _build_week_ranges(w)
        sub = df[df["series"].astype(str).str.upper() == w.series.upper()].copy()
        if sub.empty:
            continue

        sub["wk_index"] = ((sub["week_start"] - w.base_week_monday).dt.days // 7) + 1
        sub = sub[sub["wk_index"].between(1, w.num_weeks)].copy()

        week_sublabels = {
            f"第{i}周": f"{ranges_by_series[w.series][i][0].date()} ~ {ranges_by_series[w.series][i][1].date()}"
            for i in range(1, w.num_weeks + 1)
        }

        pk_by_week = sub.groupby("wk_index", as_index=True)["PK次数_num"].sum().to_dict()
        pk_row: dict[str, str] = {"对比车系": w.series}
        for i in range(1, w.num_weeks + 1):
            pk_row[f"第{i}周"] = str(int(round(float(pk_by_week.get(i, 0.0)))))
        pk_sum_tables.append(
            (
                f"{w.series} - PK次数（sum）",
                pd.DataFrame([pk_row]),
                week_sublabels,
            )
        )

        pk_num = _build_pk_num_pivot(sub, num_weeks=w.num_weeks)

        pos_rank = _build_rank_pivot(sub, "PK正向排名", num_weeks=w.num_weeks)
        pos_rank = _sort_by_last_week_pk(pos_rank, pk_num)
        pos_tables.append(
            (
                f"{w.series} - PK正向排名",
                _attach_rank_bar_cells_with_six_seat(pos_rank, pk_num, six_seat_models_norm=six_seat_models_norm),
                week_sublabels,
            )
        )

        neg_rank = _build_rank_pivot(sub, "PK反向排名", num_weeks=w.num_weeks)
        neg_rank = _sort_by_last_week_pk(neg_rank, pk_num)
        neg_tables.append(
            (
                f"{w.series} - PK反向排名",
                _attach_rank_bar_cells_with_six_seat(neg_rank, pk_num, six_seat_models_norm=six_seat_models_norm),
                week_sublabels,
            )
        )

    series_names = "、".join(w.series for w in windows)
    meta_title = f"{series_names} 上市后（end day 所在周起算）连续 {num_weeks} 周 PK 对比"
    meta_lines = [f"# {meta_title}", ""]
    meta_lines.append(f"- 统一对比周数: {num_weeks} 周")
    meta_lines.append(
        f"- 数据最大动态周: "
        + "; ".join(f"{s}={max_weeks_by_series.get(s, '?')}周" for s in (w.series for w in windows))
    )
    for w in windows:
        ranges = ranges_by_series[w.series]
        week_descrs = "; ".join(
            f"第{i}周={ranges[i][0].date()}~{ranges[i][1].date()}"
            for i in range(1, w.num_weeks + 1)
        )
        meta_lines.append(
            f"- {w.series}: end={w.end_date.date()} base_week_monday={w.base_week_monday.date()} ({week_descrs})"
        )

    html_out = str(args.html_out or "").strip()
    if html_out:
        html_path = Path(html_out)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        report_html = _format_html_report(
            title=meta_title,
            meta_lines=meta_lines,
            blocks=[
                *pk_sum_tables,
                *pos_tables,
                *neg_tables,
            ],
        )
        html_path.write_text(report_html, encoding="utf-8")

    if not args.no_stdout:
        print("\n".join(meta_lines))
        for title, tdf, _ in pk_sum_tables:
            print(_format_markdown_table(title, tdf))
        for title, tdf, _ in pos_tables:
            print(_format_markdown_table(title, tdf))
        for title, tdf, _ in neg_tables:
            print(_format_markdown_table(title, tdf))
        if html_out:
            print(f"\nHTML: {html_out}")


if __name__ == "__main__":
    main()
