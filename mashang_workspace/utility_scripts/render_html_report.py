#!/usr/bin/env python
"""
render_html_report.py — render Result Contract JSON as branded HTML report.

Reads a Result Contract (from file or stdin) and renders it using Jinja2
templates with the Raccoon Research visual identity.

Usage:
    python utility_scripts/render_html_report.py --input contract.json --output report.html
    python runtime_scripts/daily_lock_count.py --format json | python utility_scripts/render_html_report.py
    python utility_scripts/render_html_report.py --input contract.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

HERE = Path(__file__).resolve().parent.parent  # utility_scripts/ -> mashang_workspace/
TEMPLATE_DIR = HERE / "templates"
OUTPUT_DIR = HERE / "outputs" / "reports"

METRIC_LABELS = {
    "total_lock_count": "总锁单数",
    "total_leads": "总线索",
    "store_ratio_pct": "到店率",
    "drive_rate_pct": "试驾率",
    "lock7_rate_pct": "7日锁单率",
    "lock30_rate_pct": "30日锁单率",
    "total_orders": "总订单数",
    "penetrated_orders": "选配订单数",
    "penetration_rate_pct": "渗透率",
    "total_amount": "总金额",
    "vehicle_count": "车辆数",
    "avg_atp": "均价",
    "lock_count": "锁单数",
    "share": "占比",
    "h1_actual": "上半月实际",
    "mode_forecast": "最可能预测",
    "p50_forecast": "P50预测",
    "p10_forecast": "P10预测",
    "p90_forecast": "P90预测",
}

DIMENSION_LABELS = {
    "product_name": "车型",
    "series": "车系",
    "license_city": "城市",
    "parent_region_name": "区域",
    "store_city": "门店城市",
}


def format_value(key: str, value) -> str:
    if key.endswith("_rate_pct") or key == "penetration_rate_pct" or key == "share":
        return f"{value:.1%}" if isinstance(value, float) else str(value)
    if key == "avg_atp":
        return f"¥{value:,.0f}" if isinstance(value, (int, float)) else str(value)
    if key in ("total_amount",):
        return f"¥{value:,.0f}" if isinstance(value, (int, float)) else str(value)
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def build_kpis(metrics: dict) -> list[dict]:
    return [
        {
            "label": METRIC_LABELS.get(k, k),
            "value": format_value(k, v),
            "direction": "up",
        }
        for k, v in metrics.items()
        if v is not None
    ]


def build_tables_from_contract(result: dict) -> list[dict]:
    tables = list(result.get("tables") or [])

    if not tables:
        for dim in result.get("dimensions") or []:
            dim_name = dim.get("name", "")
            items = dim.get("items", [])
            if not items:
                continue
            metric_keys = list(items[0].get("metrics", {}).keys())
            columns = [DIMENSION_LABELS.get(dim_name, dim_name)] + [
                METRIC_LABELS.get(k, k) for k in metric_keys
            ]
            rows = []
            for item in items:
                row = {columns[0]: item.get("value", "")}
                for i, mk in enumerate(metric_keys):
                    row[columns[i + 1]] = format_value(mk, item.get("metrics", {}).get(mk))
                rows.append(row)
            tables.append(
                {
                    "title": DIMENSION_LABELS.get(dim_name, f"按{dim_name}分布"),
                    "columns": columns,
                    "rows": rows,
                }
            )

    return tables


def format_time_window(scope: dict) -> str:
    tw = scope.get("time_window", {})
    if tw.get("date"):
        return tw["date"]
    parts = []
    if tw.get("start_date"):
        parts.append(tw["start_date"])
    if tw.get("end_date"):
        parts.append("~")
        parts.append(tw["end_date"])
    if not parts:
        return ""
    return " ".join(parts)


def build_data_scope(scope: dict) -> dict:
    info = {}
    if scope.get("data_source"):
        info["data_source"] = scope["data_source"]
    tw = format_time_window(scope)
    if tw:
        info["time_window"] = tw
    if scope.get("metric_definition"):
        info["metric_definition"] = scope["metric_definition"]
    filters = scope.get("filters", {})
    active_filters = {k: v for k, v in filters.items() if v is not None and v != "None"}
    if active_filters:
        info["filters"] = json.dumps(active_filters, ensure_ascii=False)
    return info


def derive_title(contract: dict) -> str:
    script = contract.get("script", "")
    result = contract.get("result", {})
    if result.get("summary"):
        summary = result["summary"]
        return summary.split("\n")[0][:60]
    if script:
        name = Path(script).stem
        label_map = {
            "daily_lock_count": "锁单日报",
            "lock_by_model": "锁单车型分布",
            "lock_city_distribution": "锁单城市分布",
            "assign_conversion_analysis": "线索转化分析",
            "attribute_penetration_report": "配置渗透率报告",
            "atp_price_report": "ATP价格报告",
            "cohort_forecast": "锁单预测",
            "release_curve_analysis": "释放曲线分析",
        }
        for key, label in label_map.items():
            if key in name:
                return label
    return "数据分析报告"


def _compute_static_prefix(output_path: str | Path | None) -> str:
    """Compute relative path from output directory to project root (HERE)."""
    if output_path is None:
        return ".."
    out_dir = Path(output_path).resolve().parent
    try:
        return os.path.relpath(HERE, out_dir)
    except ValueError:
        return ".."


def render_report(
    contract: dict,
    output_path: str | None = None,
    title: str | None = None,
    template_name: str = "report_generic.html",
) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template(template_name)

    result = contract.get("result", {})
    scope = contract.get("scope", {})

    kpis = build_kpis(result.get("metrics", {}))
    tables = build_tables_from_contract(result)
    data_scope = build_data_scope(scope)
    static_prefix = _compute_static_prefix(output_path)

    script_name = Path(contract.get("script", "report")).stem
    now = contract.get("generated_at", "")

    html = template.render(
        contract=contract,
        static_prefix=static_prefix,
        title=title or derive_title(contract),
        brand_name=contract.get("brand_name", "mashang"),
        meta=contract.get("meta", f"{script_name} | {now[:10] if now else ''}"),
        hero_title=title or derive_title(contract),
        hero_subtitle=result.get("summary", ""),
        kpis=kpis,
        summary=result.get("summary", ""),
        tables=tables,
        data_scope=data_scope,
    )

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"  HTML: {out.resolve()}")
    return html


def main():
    parser = argparse.ArgumentParser(description="Render Result Contract as branded HTML report")
    parser.add_argument("--input", "-i", help="Input JSON file (reads stdin if omitted)")
    parser.add_argument("--output", "-o", help="Output HTML file path")
    parser.add_argument("--title", "-t", help="Report title (overrides auto-detect)")
    parser.add_argument("--template", default="report_generic.html", help="Template name (default: report_generic.html)")
    args = parser.parse_args()

    if args.input:
        with open(args.input, encoding="utf-8") as f:
            contract = json.load(f)
    else:
        contract = json.load(sys.stdin)

    if contract.get("status") == "error":
        print(f"  Cannot render error contract: {contract.get('errors', [{}])[0].get('message', '')}")
        sys.exit(1)

    output_path = args.output
    if not output_path:
        script_name = Path(contract.get("script", "report")).stem
        now = contract.get("generated_at", "")
        date_part = now[:10] if now else "unknown"
        output_path = str(OUTPUT_DIR / f"{script_name}_{date_part}.html")

    try:
        render_report(contract, output_path=output_path, title=args.title, template_name=args.template)
    except Exception as e:
        print(f"  Error rendering report: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
