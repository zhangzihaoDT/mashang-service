#!/usr/bin/env python
"""
配置渗透率分析 — 选装率/属性分布

基于 config_attribute.parquet 的 value_code 做配置解析：
- value_code 是配置 code（Y=是 / N=否 / Stand=标准 / Pro=高阶 等），value 是显示名；
- 同一 (Attribute, value_code) 的多个显示名归并为一个配置（如 Stand = 标准 / 标准+Orin）；
- value_code 为 N 或 value 为"否"的行表示未含该配置，不计入渗透率分子；
- 覆盖独立属性行 + "已选"聚合属性（LS8 独有，value 含关键词时计入，
  如"已选"=超远距高精度激光雷达即 LS8 标配激光雷达的记录）。

注：旧的"选装包业务展开"（config_packages，如奢华智选包→包内配置）已废弃移除。
配置渗透率仅基于显式配置行统计；配置拥有率综合分析见 ls8_configuration_selection_report.py。

用法:
    python scripts/attribute_penetration_report.py                            # 默认分析激光雷达
    python scripts/attribute_penetration_report.py --model "LS8" --attribute "激光雷达"
    python scripts/attribute_penetration_report.py --format csv --output outputs/tables/
"""

import sys, argparse, json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

import pandas as pd
from datetime import datetime, timedelta
from utils.result_contract import build_success_contract, save_contract_json, contract_to_terminal

ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
CONFIG_PARQUET = REPO_ROOT / "dataset" / "config_attribute.parquet"

def parse_args():
    p = argparse.ArgumentParser(description="配置渗透率分析")
    p.add_argument("--date", type=str, help="单日查询")
    p.add_argument("--start-date", type=str, help="开始日期")
    p.add_argument("--end-date", type=str, help="结束日期")
    p.add_argument("--series", type=str, help="车系过滤")
    p.add_argument("--model", type=str, help="具体车型过滤")
    p.add_argument("--city", type=str, help="忽略")
    p.add_argument("--output", type=str, help="输出目录")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "csv", "json"])
    p.add_argument("--limit", type=int, default=10, help="TopN 属性值 (默认 10)")
    p.add_argument("--attribute", type=str, default="激光雷达", help="配置属性名称")
    return p.parse_args()


def resolve_time_range(args):
    if args.date:
        d = pd.Timestamp(args.date); return d, d + timedelta(days=1), args.date, "date"
    if args.start_date and args.end_date:
        s = pd.Timestamp(args.start_date)
        e = pd.Timestamp(args.end_date) + timedelta(days=1)
        return s, e, f"{args.start_date}~{args.end_date}", "range"
    yesterday = datetime.now() - timedelta(days=1)
    return (yesterday - timedelta(days=29)), yesterday + timedelta(days=1), "近30天", "range"


NEGATIVE_VALUE_CODES = {"N", "NO", "FALSE", "0"}
POSITIVE_VALUE_CODES = {"Y", "YES", "TRUE", "1"}
NEGATIVE_VALUE_NAMES = {"否", "无", "未选", "未装", "不选"}

SELECTED_ATTRIBUTE = "已选"


def is_penetrated(code, value):
    """判断一行配置记录是否表示"含该配置"。

    规则（value_code 优先）:
      - value_code 为显式负值（N/NO/FALSE/0）→ 未含；
      - value_code 为显式正值（Y/YES/TRUE/1）→ 含；
      - value_code 为档位值（Stand/Pro 等）→ 含（档位即已装）；
      - value_code 缺失时回退 value：value 为"否/无/未选"等 → 未含，否则含。
    """
    code = str(code or "").strip().upper()
    val = str(value or "").strip()
    if code in NEGATIVE_VALUE_CODES:
        return False
    if code in POSITIVE_VALUE_CODES:
        return True
    if code in {"STAND", "PRO", "PLUS", "MAX", "PREMIUM", "ULTRA"}:
        return True
    if val in NEGATIVE_VALUE_NAMES:
        return False
    return True


def build_value_code_map(config_df):
    """按 (Attribute, value_code) 归并显示名：同一属性下同 code 的多个 value 视为同一配置，取出现最多者。

    用于把 value 列归一化为规范配置名（如 标准/标准+Orin → 标准+Orin）。
    按 Attribute 区分，避免跨属性同 code 冲突（如 Stand 在不同属性下含义不同）。
    """
    if "value_code" not in config_df.columns:
        return {}
    coded = config_df[config_df["value_code"].notna()].copy()
    if not len(coded):
        return {}
    coded["value_code"] = coded["value_code"].astype(str).str.strip()
    coded["value"] = coded["value"].astype(str).str.strip()
    coded = coded[coded["value_code"].ne("") & coded["value"].ne("")]
    if not len(coded):
        return {}
    return coded.groupby(["Attribute", "value_code"])["value"].agg(lambda s: s.value_counts().idxmax()).to_dict()


def _keyword_variants(keyword):
    """返回 keyword 的匹配变体：含"寸"时补"英寸"写法（数据 value 用英寸）。"""
    variants = {keyword}
    if "寸" in keyword:
        variants.add(keyword.replace("寸", "英寸"))
    return sorted(variants)


def match_attribute_rows(config_in_scope, keyword):
    """匹配目标配置的配置行。

    覆盖两类记录:
      1. 独立属性行：Attribute 名称含 keyword（如"超远距高精度双激光雷达"匹配"激光雷达"）
         或 value 含 keyword（如"22英寸星冕镜面超奢轮辋"匹配"22寸"，尺寸做寸/英寸归一化）；
      2. "已选"聚合属性（LS8 独有）：Attribute="已选" 且 value 含 keyword
         （如"已选"=超远距高精度激光雷达，编码 LS8 标配激光雷达）。
    """
    variants = _keyword_variants(keyword)
    pat = "|".join(variants)
    indep = config_in_scope[
        (config_in_scope["Attribute"] != SELECTED_ATTRIBUTE)
        & (
            config_in_scope["Attribute"].astype(str).str.contains(pat, na=False)
            | config_in_scope["value"].astype(str).str.contains(pat, na=False)
        )
    ]
    if SELECTED_ATTRIBUTE not in set(config_in_scope["Attribute"]):
        return indep
    sel = config_in_scope[config_in_scope["Attribute"] == SELECTED_ATTRIBUTE]
    sel_match = sel[sel["value"].astype(str).str.contains(pat, na=False)]
    return pd.concat([indep, sel_match], ignore_index=True)


def main():
    args = parse_args()
    t_start, t_end, t_label, tw_type = resolve_time_range(args)
    cmd = "python " + " ".join(sys.argv)

    order_df = pd.read_parquet(str(ORDER_PARQUET))
    order_df["lock_time"] = pd.to_datetime(order_df["lock_time"], errors="coerce")
    order_df = order_df[order_df["lock_time"].notna()].copy()
    mask = (order_df["lock_time"] >= t_start) & (order_df["lock_time"] < t_end)
    filtered = order_df[mask]

    if args.series: filtered = filtered[filtered["series"] == args.series]
    if args.model: filtered = filtered[filtered["product_name"].str.contains(args.model, na=False)]

    order_ids = set(filtered["order_number"].dropna().unique())
    total_orders = len(order_ids)

    config_df = pd.read_parquet(str(CONFIG_PARQUET))
    config_in_scope = config_df[config_df["Order Number"].isin(order_ids)]
    attr_filtered = match_attribute_rows(config_in_scope, args.attribute)

    value_code_map = build_value_code_map(config_df)

    # 逐行判定"是否含该配置"，并按 value_code 归并显示名
    rows = []
    for _, r in attr_filtered.iterrows():
        code = r.get("value_code")
        val = str(r.get("value") or "").strip()
        if pd.isna(code):
            label = val
        else:
            label = value_code_map.get((str(r["Attribute"]), str(code).strip()), val)
        rows.append({
            "order_number": str(r["Order Number"]),
            "value": val,
            "value_code": "" if pd.isna(code) else str(code).strip(),
            "label": label,
            "penetrated": is_penetrated(code, val),
        })
    recs = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["order_number", "value", "value_code", "label", "penetrated"])

    penetrated_orders = set(recs.loc[recs["penetrated"], "order_number"]) if len(recs) else set()
    penetration_rate = round(len(penetrated_orders) / total_orders * 100, 1) if total_orders else 0

    items = []
    dim_items = []
    if len(recs):
        value_counts = recs.loc[recs["penetrated"], "label"].value_counts().head(args.limit)
        for val, cnt in value_counts.items():
            pct = round(cnt / total_orders * 100, 1)
            items.append({"value": str(val), "metrics": {"count": int(cnt), "pct": pct}})
            dim_items.append({"value": str(val), "metrics": {"count": int(cnt), "share": round(cnt / total_orders, 4)}})

    time_window = {"type": tw_type}
    if tw_type == "date": time_window["date"] = t_label
    else: time_window.update({"start_date": str(t_start.date()), "end_date": str((t_end - timedelta(days=1)).date())})

    scope = {
        "data_source": f"{ORDER_PARQUET} ⋈ {CONFIG_PARQUET}",
        "time_window": time_window,
        "filters": {"series": args.series, "model": args.model, "attribute": args.attribute},
        "metric_definition": (
            f"{args.attribute} 渗透率 = 含该配置的订单数 / 总订单数；"
            f"含该配置 = 配置表按 value_code 解析（Y/档位=含，N/否=不含）；"
            f"显示名按 (Attribute, value_code) 归并（同一属性下同 code 多个显示名视为同一配置）；"
            f"覆盖独立属性行 + '已选'聚合属性（LS8 独有，value 含关键词时计入）"
        ),
    }
    result = {
        "summary": f"{args.attribute} 渗透率: {penetration_rate}% ({len(penetrated_orders)}/{total_orders})",
        "metrics": {
            "total_orders": total_orders,
            "penetrated_orders": len(penetrated_orders),
            "penetration_rate_pct": penetration_rate,
        },
        "dimensions": [{"name": "value", "items": dim_items}],
    }
    artifacts = {}
    out_dir = Path(args.output) if args.output else REPO_ROOT / "outputs" / "tables"
    if args.format == "csv" or (args.output and args.format == "terminal"):
        out_dir.mkdir(parents=True, exist_ok=True)
        if len(recs):
            recs.drop(columns=["label"]).to_csv(out_dir / f"{t_label}_attribute_{args.attribute}.csv", index=False)
        artifacts["csv"] = str(out_dir / f"{t_label}_attribute_{args.attribute}.csv")

    contract = build_success_contract(
        script="scripts/attribute_penetration_report.py", command=cmd, scope=scope,
        result=result, artifacts=artifacts,
        followup_context={"metric": "attribute_penetration", "attribute": args.attribute,
                          "available_dimensions": ["series", "product_name", "value_code"],
                          "top_entities": [{"field": "value", "value": str(v), "metrics": {"count": int(c)}}
                                           for v, c in (value_counts.items() if len(recs) else [])]},
    )

    if args.format == "json":
        if args.output:
            save_contract_json(contract, out_dir / f"{t_label}_attribute_{args.attribute}.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(contract_to_terminal(contract))

if __name__ == "__main__":
    main()
