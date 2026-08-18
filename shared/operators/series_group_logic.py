import pandas as pd


def _eval_series_group_logic_expr(product_name: pd.Series, expr: str) -> pd.Series:
    s = product_name.astype("string").fillna("")
    expr = str(expr or "").strip()
    if not expr or expr.upper() == "ELSE":
        return pd.Series([False] * len(s), index=s.index)

    expr = expr.replace("(", " ").replace(")", " ")
    or_terms = [t.strip() for t in expr.split(" OR ") if t.strip()]

    out = pd.Series([False] * len(s), index=s.index)
    for term in or_terms:
        and_terms = [t.strip() for t in term.split(" AND ") if t.strip()]
        m = pd.Series([True] * len(s), index=s.index)
        for cond in and_terms:
            cond = cond.strip()
            if " NOT LIKE " in cond:
                tok = cond.split(" NOT LIKE ", 1)[1].strip().strip("'").strip('"')
                tok = tok.strip("%")
                m = m & (~s.str.contains(tok, na=False, regex=False))
            elif " LIKE " in cond:
                tok = cond.split(" LIKE ", 1)[1].strip().strip("'").strip('"')
                tok = tok.strip("%")
                m = m & (s.str.contains(tok, na=False, regex=False))
        out = out | m
    return out


def _rule_condition(rule) -> str:
    """提取规则表达式字符串，兼容旧字符串格式与新的 {priority, condition} 对象格式。"""
    if isinstance(rule, dict):
        return str(rule.get("condition", ""))
    return str(rule)


def _rule_priority(rule, default: int = 0) -> int:
    """提取规则优先级；旧字符串格式视为 priority=0。"""
    if isinstance(rule, dict):
        try:
            return int(rule.get("priority", default))
        except (TypeError, ValueError):
            return default
    return default


def apply_series_group_logic(df: pd.DataFrame, business_definition: dict) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if "series_group_logic" in df.columns:
        return df
    if "product_name" not in df.columns:
        df["series_group_logic"] = pd.NA
        return df

    logic = (business_definition or {}).get("series_group_logic") or {}
    if not isinstance(logic, dict) or not logic:
        df["series_group_logic"] = pd.NA
        return df

    rules = []
    for i, (key, rule) in enumerate(logic.items()):
        if str(key) == "其他":
            continue
        rules.append((_rule_priority(rule), i, str(key), _rule_condition(rule)))
    rules.sort(key=lambda r: (-r[0], r[1]))

    out = pd.Series(["其他"] * len(df), index=df.index, dtype="string")
    product_name = df["product_name"]
    for _, _, key, condition in rules:
        mask = _eval_series_group_logic_expr(product_name, condition)
        if mask.any():
            assign = mask & out.eq("其他")
            out = out.where(~assign, other=key)
    df["series_group_logic"] = out
    return df

