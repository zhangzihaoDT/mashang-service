#!/usr/bin/env python
"""
Runtime V2 — Response Renderer

将 Result Contract 渲染为简洁自然语言回答。
只使用 contract 中已有字段，不编造数据。

展示层配置（metric 中文标签、追问后缀）由调用方经参数注入（来自 config），
本模块不硬编码任何业务文案。
"""


def render(contract_data: dict, metric_labels=None, hint_suffix: str = "") -> str:
    """将 contract data 渲染为自然语言回答。

    metric_labels: {英文 metric key: 中文标签}，缺省为空表（按原 key 显示）。
    hint_suffix:   追问提示的业务后缀（由 config 注入，如能力的分组维度名），缺省无后缀。
    """
    labels = metric_labels or {}
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
                label = labels.get(k, k)
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
            base = f"你可以继续追问“{'、'.join(hints)}”"
            if hint_suffix:
                base = base[:-1] + f"的{hint_suffix}”"
            lines.append(base + "。")

    return "\n".join(lines).strip()
