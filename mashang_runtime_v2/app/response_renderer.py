#!/usr/bin/env python
"""
Runtime V2 — Response Renderer

将 Result Contract 渲染为简洁自然语言回答。
只使用 contract 中已有字段，不编造数据。
"""


def render(contract_data: dict) -> str:
    """将 contract data 渲染为自然语言回答。"""
    status = contract_data.get("status", "error")
    quality = contract_data.get("contract_quality", "ok")

    if status == "error" or quality == "error":
        error = contract_data.get("error", "unknown error")
        return f"查询出错：{error}"

    summary = contract_data.get("summary", "")
    metrics = contract_data.get("metrics", {})
    dimensions = contract_data.get("dimensions", [])
    fc = contract_data.get("followup_context", {})
    warnings = contract_data.get("warnings", [])

    if not summary and not metrics and not dimensions:
        return "结果已生成，但缺少可展示摘要字段。"

    lines = []

    if summary:
        lines.append(summary)
        lines.append("")

    if metrics:
        for k, v in metrics.items():
            if v is not None:
                # Use Chinese label for common metrics
                label = {"total_lock_count": "总锁单数", "total_leads": "总线索数",
                         "vehicle_count": "用户车锁单", "avg_atp": "ATP均价"}.get(k, k)
                lines.append(f"  {label}：{v}")
        lines.append("")

    if dimensions:
        for dim in dimensions:
            name = dim.get("name", "分类")
            items = dim.get("items", [])
            if items:
                lines.append(f"Top {name}：")
                for i, item in enumerate(items[:10], 1):
                    val = item.get("value", "")
                    m = item.get("metrics", {})
                    parts = [f"{mk}={mv}" for mk, mv in m.items() if mv is not None]
                    lines.append(f"  {i}. {val}：{'，'.join(parts)}")
                lines.append("")

    # Warnings hint
    if quality == "warning":
        lines.append("（注意：结果字段不完整）")

    # Next turn hints
    top = fc.get("top_entities", [])
    if top:
        hints = [t.get("value", "") for t in top[:3] if t.get("value")]
        if hints:
            lines.append(f"你可以继续追问“{'、'.join(hints)}的城市分布”。")

    return "\n".join(lines).strip()
