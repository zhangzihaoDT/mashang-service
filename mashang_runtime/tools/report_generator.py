import datetime
import json
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parents[1] / "logs"


def _fmt(val) -> str:
    if val is None or (isinstance(val, float) and val != val):
        return ""
    if isinstance(val, float):
        return f"{val:,.2f}" if abs(val) < 1e12 else f"{val:.4g}"
    if isinstance(val, int):
        return f"{val:,}"
    return str(val)


def _style_table(headers: list[str], rows: list[list]) -> str:
    parts = [
        '<table style="border-collapse:collapse;font-size:13px;width:auto;margin:0 0 20px 0;">',
        "<thead>",
        '<tr style="background:#1f2a3a;color:#fff;">',
    ]
    for h in headers:
        parts.append(
            '<th style="text-align:left;padding:7px 10px;border:1px solid #1f2a3a;">'
            f"{h}</th>"
        )
    parts.append("</tr></thead><tbody>")
    for i, row in enumerate(rows):
        bg = "#ffffff" if i % 2 == 0 else "#f8f9fa"
        parts.append(f'<tr style="background:{bg};">')
        for j, val in enumerate(row):
            align = "right" if j > 0 else "left"
            parts.append(
                f'<td style="text-align:{align};padding:5px 10px;'
                f'border:1px solid #d0d5dd;">{_fmt(val)}</td>'
            )
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "\n".join(parts)


class ReportGenerator:
    def generate_from_facts(
        self,
        facts: list[dict],
        title: str = "",
        save: bool = True,
    ) -> str:
        now = datetime.datetime.now()
        if not title:
            title = f"分析报告 {now.strftime('%Y-%m-%d %H:%M')}"
        stamp = now.strftime("%Y%m%d_%H%M%S_%f")[:20]
        filename = f"report_{stamp}.html"
        out_path = REPORTS_DIR / filename

        sections: list[str] = [
            "<!DOCTYPE html><html><head>",
            '<meta charset="utf-8">',
            f"<title>{title}</title>",
            "</head><body",
            ' style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;',
            'margin:24px;background:#fff;">',
            f'<h2 style="margin:0 0 4px 0;">{title}</h2>',
            f'<p style="margin:0 0 16px 0;color:#888;font-size:13px;">'
            f"生成时间: {now.strftime('%Y-%m-%d %H:%M:%S')}</p>",
        ]

        if not facts:
            sections.append('<p style="color:#999;">暂无数据。</p>')

        ft_groups: dict[str, list[dict]] = {}
        for f in facts:
            if not isinstance(f, dict):
                continue
            ft = f.get("fact_type", "other")
            ft_groups.setdefault(ft, []).append(f)

        for ft, items in ft_groups.items():
            label = {
                "metric_value": "核心指标",
                "time_grouped_metric": "时序数据",
                "trend_summary": "趋势摘要",
                "share_summary": "占比分析",
                "dimension_breakdown": "维度拆解",
                "ranking_result": "排名",
                "comparison_result": "对比分析",
                "distribution_summary": "分布分析",
                "contribution_summary": "贡献分析",
            }.get(ft, ft)
            sections.append(
                f'<h3 style="margin:16px 0 8px 0;color:#1f2a3a;'
                f'border-bottom:2px solid #1f2a3a;padding-bottom:4px;">{label}</h3>'
            )

            for f in items:
                content = f.get("content", "")
                meta = f.get("metadata") or {}
                sections.append(
                    f'<p style="margin:4px 0;font-size:13px;color:#333;">{content}</p>'
                )

                if ft == "dimension_breakdown":
                    dim = meta.get("dimension_fields", [None])[0]
                    metric = meta.get("metric_fields", [None])[0]
                    src = f.get("source", {})
                    block_id = src.get("block_id") if isinstance(src, dict) else None
                    if block_id:
                        sections.append(
                            f'<p style="margin:2px 0 8px 0;font-size:11px;color:#999;">'
                            f"来源: {block_id}</p>"
                        )

            sections.append("")

        sections.append("</body></html>")
        html = "\n".join(sections)

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        if save:
            out_path.write_text(html, encoding="utf-8")

        return str(out_path) if save else html

    def generate_from_dataframe(
        self,
        df,
        title: str = "",
        caption: str = "",
        save: bool = True,
    ) -> str:
        import pandas as pd

        now = datetime.datetime.now()
        if not title:
            title = f"数据报告 {now.strftime('%Y-%m-%d %H:%M')}"
        stamp = now.strftime("%Y%m%d_%H%M%S_%f")[:20]
        filename = f"report_{stamp}.html"
        out_path = REPORTS_DIR / filename

        headers = list(df.columns)
        rows = []
        for _, row in df.iterrows():
            rows.append([row[h] for h in headers])

        html = (
            "<!DOCTYPE html><html><head>"
            f'<meta charset="utf-8"><title>{title}</title>'
            "</head><body"
            ' style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;'
            'margin:24px;background:#fff;">'
            f'<h2 style="margin:0 0 4px 0;">{title}</h2>'
            + (
                f'<p style="margin:0 0 16px 0;color:#888;font-size:13px;">{caption}</p>'
                if caption
                else ""
            )
            + _style_table(headers, rows)
            + f'<p style="margin:8px 0 0 0;color:#aaa;font-size:11px;">'
            f"共 {len(df)} 行 | 生成时间: {now.strftime('%Y-%m-%d %H:%M:%S')}</p>"
            + "</body></html>"
        )

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        if save:
            out_path.write_text(html, encoding="utf-8")
        return str(out_path) if save else html


REPORT_GENERATOR_SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_report",
        "description": "将当前分析数据生成 HTML 报告并保存到 logs 目录。当用户要求输出报告/输出完整报告/输出 html 时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "报告标题，默认为自动生成",
                },
            },
            "required": [],
        },
    },
}
