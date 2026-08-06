#!/usr/bin/env python3
"""LS8 上市以来用户车锁配置拥有率报告。

配置拥有判定完全基于业务逻辑（config_semantics + config_attribute）：
1. 配置项集合严格来自当前 LS8 订单在 config_attribute 中出现的 Attribute/value_code。
2. 已选属性（LS8 独有）三个 value_code 的业务语义由 config_semantics 的
   selection_tier 定义（Stand=标配激光雷达 / Pro=奢华智选包 / Plus=选装包+探射灯），
   出现任一档位即代表拥有对应配置。
3. 激光雷达拥有判定：有已选记录按已选档位归并；无已选记录时按激光雷达选装属性判定。
4. 版本划分（产品版本 → product_name 匹配）为脚本内业务常量，不依赖官网配置表。

用法:
    python research_scripts/ls8_configuration_selection_report.py
    python research_scripts/ls8_configuration_selection_report.py --html
    python research_scripts/ls8_configuration_selection_report.py --format json
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
WS_ROOT = REPO_ROOT / "mashang_workspace"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(WS_ROOT))

from utils.config_semantics import (
    load_config_semantics,
    get_attribute_spec,
    is_noise_attribute,
    resolve_value_code,
    code_is_selected,
)
from utils.result_contract import build_success_contract, save_contract_json

ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
CONFIG_PARQUET = REPO_ROOT / "dataset" / "config_attribute.parquet"
BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
TEMPLATE_DIR = WS_ROOT / "templates"
REPORT_TEMPLATE = "ls8_configuration_selection.html"
OUTPUT_DIR = WS_ROOT / "outputs"
SERIES = "LS8"

# LS8 产品版本结构与 product_name 匹配规则（业务逻辑，非官网配置表）
LS8_VERSIONS = [
    "科技旗舰大五座 52 Max+",
    "科技旗舰大五座 66 Ultra",
    "奢享大六座 52 Max+",
    "奢享大六座 66 Ultra",
]
LS8_VERSION_MATCHERS = {
    "科技旗舰大五座 52 Max+": ["科技旗舰", "五座", "52"],
    "科技旗舰大五座 66 Ultra": ["科技旗舰", "五座", "66"],
    "奢享大六座 52 Max+": ["奢享", "六座", "52"],
    "奢享大六座 66 Ultra": ["奢享", "六座", "66"],
}
# 已选属性业务语义：Stand=标配激光雷达，Pro/Plus=含激光雷达的选装包档位。
# 已选出现（任一档位）即代表拥有激光雷达；无已选记录时，激光雷达选装属性出现即拥有。
SELECTED_ATTRIBUTE_LIDAR_TIERS = ("Stand", "Pro", "Plus")
LIDAR_OPTION_ATTRIBUTES = {"超远距高精度双激光雷达"}
CATEGORY_ORDER = {name: index for index, name in enumerate([
    "选装包", "智能驾驶", "座舱舒适", "内饰", "外饰", "轮毂", "方向盘", "后排娱乐",
    "底盘操控", "智能交互", "智能驾舱", "音响座椅", "拖挂", "动力电池",
    "外部配置", "内部配置", "安全配置", "基本参数", "整车性能", "动力系统", "智慧拓展", "其他",
])}


def parse_args():
    parser = argparse.ArgumentParser(description="LS8 上市以来用户车锁配置拥有率报告")
    parser.add_argument("--as-of", default=None, help="数据截止日期，默认使用数据中的最大锁单日期")
    parser.add_argument("--format", choices=["json", "terminal"], default="terminal")
    parser.add_argument("--html", action="store_true", help="同时生成品牌化 HTML 报告")
    parser.add_argument("--output", default=None, help="Result Contract JSON 输出路径")
    return parser.parse_args()


def load_business_definition():
    return json.loads(BUSINESS_DEF.read_text(encoding="utf-8"))


def launch_date(business_definition):
    return pd.Timestamp(business_definition["time_periods"]["LS8"]["end"])


def match_version(product_name, version_matchers):
    """按 version_matchers 把 product_name 归一到版本；无法匹配返回空串。"""
    name = str(product_name or "")
    for version, keywords in version_matchers.items():
        if all(kw in name for kw in keywords):
            return version
    return ""


def build_report_data(as_of_limit=None):
    business_definition = load_business_definition()
    start_date = launch_date(business_definition)
    versions = LS8_VERSIONS
    version_matchers = LS8_VERSION_MATCHERS

    config_semantics = load_config_semantics()

    orders = pd.read_parquet(ORDER_PARQUET)
    orders["lock_time"] = pd.to_datetime(orders["lock_time"], errors="coerce")
    user_orders = orders[
        (orders["series"] == SERIES)
        & (orders["order_type"] == "用户车")
        & (orders["lock_time"] >= start_date)
    ].copy()
    if as_of_limit:
        as_of_date = pd.Timestamp(as_of_limit).normalize()
        user_orders = user_orders[user_orders["lock_time"] < as_of_date + pd.Timedelta(days=1)]
    user_orders = user_orders.drop_duplicates("order_number")
    if user_orders.empty:
        raise RuntimeError("没有找到符合条件的 LS8 用户车锁单订单")

    as_of = user_orders["lock_time"].max().normalize()
    order_ids = set(user_orders["order_number"].dropna().astype(str))

    # 版本映射：订单 → LS8 产品版本（业务匹配规则）
    user_orders["config_version"] = user_orders["product_name"].apply(
        lambda n: match_version(n, version_matchers)
    )
    version_order_ids = defaultdict(set)
    for _, row in user_orders.iterrows():
        version_order_ids[row["config_version"]].add(str(row["order_number"]))
    matched_orders = {oid for oids in version_order_ids.values() for oid in oids}
    unmapped_orders = order_ids - matched_orders

    configs = pd.read_parquet(CONFIG_PARQUET)
    configs["Order Number"] = configs["Order Number"].astype(str)
    configs = configs[configs["Order Number"].isin(order_ids)].copy()

    order_meta = user_orders.set_index("order_number")[
        ["product_name", "lock_time", "config_version"]
    ].to_dict("index")

    # ---- 显式配置行归一（value_code → code），供选配率统计与明细 CSV ----
    resolved_rows = []
    unresolved = defaultdict(int)
    code_owners = defaultdict(set)  # (attribute, code) -> orders
    for _, row in configs.iterrows():
        order_id = str(row["Order Number"])
        attribute = str(row.get("Attribute") or "")
        value = str(row.get("value") or "").strip()
        raw_code = "" if pd.isna(row.get("value_code")) else str(row.get("value_code")).strip()
        spec = get_attribute_spec(config_semantics, SERIES, attribute)
        if is_noise_attribute(spec):
            continue
        code, display = resolve_value_code(spec, raw_code or None, value)
        if not code:
            unresolved[attribute] += 1
            continue
        resolved_rows.append({
            "order_number": order_id,
            "attribute": attribute,
            "code": code,
            "display": display or value,
            "included": code_is_selected(spec, code),
            "value": value,
            "value_code": raw_code,
        })
        code_owners[(attribute, code)].add(order_id)

    # ---- 已选 / 未选分组：已选 = 有"已选"属性记录；未选 = 无 ----
    selected_orders = set()
    for (attr, _code), sel in code_owners.items():
        if attr == "已选":
            selected_orders.update(sel)
    unselected_orders = order_ids - selected_orders

    # ---- 配置项差异/共性分类：判定粒度 = Attribute name，而非具体配置值 ----
    # 同一属性只要已选/未选两组都有记录即为共性（该属性下所有配置值进入矩阵）；
    # 仅一组出现的属性整体归为差异项。
    attr_sel_orders = defaultdict(set)
    attr_unsel_orders = defaultdict(set)
    attr_codes = defaultdict(list)  # attribute -> [{code, display, owners}]
    for (attribute, code), owners in code_owners.items():
        spec = get_attribute_spec(config_semantics, SERIES, attribute)
        if is_noise_attribute(spec):
            continue
        code_spec = (spec.get("codes") or {}).get(code, {})
        display = code_spec.get("display") or attribute
        owners = set(owners)
        attr_sel_orders[attribute].update(owners & selected_orders)
        attr_unsel_orders[attribute].update(owners & unselected_orders)
        attr_codes[attribute].append({"code": code, "display": display, "owners": owners})

    diff_rows = []
    common_matrix = []
    for attribute, codes in attr_codes.items():
        spec = get_attribute_spec(config_semantics, SERIES, attribute)
        category = spec.get("category") or "其他"
        has_sel = bool(attr_sel_orders[attribute])
        has_unsel = bool(attr_unsel_orders[attribute])
        if has_sel and has_unsel:
            # 共性属性：该属性下所有配置值行进入分版本矩阵
            for c in codes:
                owners = c["owners"]
                item_rates = []
                item_counts = []
                for v in versions:
                    v_orders = version_order_ids.get(v, set())
                    n = len(v_orders)
                    have = len(owners & v_orders)
                    item_counts.append(have)
                    item_rates.append(round(have / n * 100, 1) if n else 0.0)
                overall = len(owners) / len(order_ids) * 100 if order_ids else 0.0
                common_matrix.append({
                    "属性": attribute,
                    "配置值": c["display"],
                    "分类": category,
                    "cell_rates": item_rates,
                    "cell_counts": item_counts,
                    "覆盖订单": len(owners),
                    "总占比": round(overall, 1),
                })
        elif has_sel or has_unsel:
            # 差异属性：属性级汇总，配置值展示该属性在出现组的全部取值
            value_text = " / ".join(sorted(c["display"] for c in codes))
            order_count = len(attr_unsel_orders[attribute]) if has_unsel else len(attr_sel_orders[attribute])
            group_total = len(unselected_orders) if has_unsel else len(selected_orders)
            diff_rows.append({
                "归属": "仅未选" if has_unsel else "仅已选",
                "属性": attribute,
                "配置值": value_text,
                "订单数": order_count,
                "所在分类占比": round(order_count / group_total * 100, 1) if group_total else 0.0,
            })
    # 差异表排序：未选独有在前（更突出的异常特征），再按订单数降序
    diff_rows.sort(key=lambda r: (0 if r["归属"] == "仅未选" else 1, -r["订单数"], r["属性"]))
    common_matrix.sort(key=lambda row: (CATEGORY_ORDER.get(row["分类"], 99), row["属性"], -row["总占比"], row["配置值"]))

    # ---- 按 Attribute 汇总（订单级去重，显式配置表口径）----
    attribute_level_summary = []
    for attribute, group in configs.groupby("Attribute"):
        order_counts = group.groupby("Order Number").size()
        value_order_counts = group.groupby("value")["Order Number"].nunique().sort_values(ascending=False)
        top_value = str(value_order_counts.index[0]) if len(value_order_counts) else ""
        top_value_orders = int(value_order_counts.iloc[0]) if len(value_order_counts) else 0
        attribute_level_summary.append({
            "Attribute": str(attribute),
            "订单数": int(len(order_counts)),
            "覆盖率": round(len(order_counts) / len(order_ids) * 100, 1),
            "取值数": int(group["value"].nunique()),
            "主值": top_value,
            "主值订单数": top_value_orders,
            "来源": "显式配置表",
        })
    attribute_level_summary.sort(key=lambda row: (-row["订单数"], row["Attribute"]))

    # ---- 明细 CSV：显式配置行 ----
    version_of_order = {str(k): v for k, v in order_meta.items()}
    detail_rows = []
    for row in resolved_rows:
        oid = row["order_number"]
        meta = order_meta.get(oid, {})
        ver = meta.get("config_version", "")
        detail_rows.append({
            "order_number": oid,
            "product_name": meta.get("product_name", ""),
            "lock_time": str(meta.get("lock_time", "")),
            "config_version": ver,
            "attribute": row["attribute"],
            "value": row["value"],
            "value_code": row["value_code"],
            "code": row["code"],
            "included": row["included"],
        })
    complete_path = OUTPUT_DIR / "tables" / "ls8_lock_configuration_selection_since_launch.csv"
    complete_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(detail_rows).to_csv(complete_path, index=False)

    metrics = {
        "total_lock_orders": len(order_ids),
        "selected_orders": len(selected_orders),
        "unselected_orders": len(unselected_orders),
        "version_matched_orders": len(matched_orders),
        "version_unmatched_orders": len(unmapped_orders),
        "diff_attributes": len(diff_rows),
        "common_attributes": len({row["属性"] for row in common_matrix}),
        "common_config_values": len(common_matrix),
        "unresolved_config_rows": sum(unresolved.values()),
        "unresolved_by_attribute": dict(unresolved),
        "version_order_counts": {v: len(version_order_ids.get(v, set())) for v in versions},
    }

    tables = [
        {
            "title": "已选/未选差异配置摘录",
            "columns": ["归属", "属性", "配置值", "订单数", "所在分类占比"],
            "rows": diff_rows,
        },
        {
            "title": "共性配置分版本矩阵",
            "columns": ["属性", "配置值"] + versions + ["总计"],
            "rows": [
                {
                    "属性": "-",
                    "配置值": "锁单数",
                    **{v: 100.0 for v in versions},
                    "总计": 100.0,
                },
                *[
                    {
                        "属性": row["属性"],
                        "配置值": row["配置值"],
                        **{
                            v: rate
                            for v, count, rate in zip(versions, row["cell_counts"], row["cell_rates"])
                        },
                        "总计": row["总占比"],
                    }
                    for row in common_matrix
                ],
            ],
        },
    ]
    scope = {
        "data_source": f"{ORDER_PARQUET.name} ⋈ {CONFIG_PARQUET.name} ⋈ config_semantics.json",
        "time_window": {"start_date": str(start_date.date()), "end_date": str(as_of.date())},
        "filters": {"series": SERIES, "order_type": "用户车", "lock_time": "上市以来"},
        "metric_definition": (
            "报告以 已选/未选 为第一维度：已选 = 有『已选』属性记录的订单，未选 = 无。"
            "先把两组有差异的配置项（仅已选/仅未选出现）单独摘出；"
            "分版本矩阵仅使用两组共有的配置项一起分析。"
            "配置值展示采用 Attribute 名 + value display，value_code 仅用于归纳统一。"
            "分版本矩阵分母为该版本订单数，分子按订单级去重。"
        ),
    }
    result = {
        "summary": (
            f"LS8 上市以来用户车锁配置：共 {len(order_ids)} 单，"
            f"已选 {len(selected_orders)} 单、未选 {len(unselected_orders)} 单；"
            f"差异属性 {len(diff_rows)} 个（仅已选/仅未选），共性属性 {len({row['属性'] for row in common_matrix})} 个。"
        ),
        "metrics": metrics,
        "tables": tables,
    }
    artifacts = {"complete_configuration_csv": str(complete_path)}
    contract = build_success_contract(
        script="research_scripts/ls8_configuration_selection_report.py",
        command="python " + " ".join(sys.argv),
        scope=scope,
        result=result,
        artifacts=artifacts,
        followup_context={
            "metric": "ls8_configuration_map",
            "series": "LS8",
            "available_dimensions": ["config_item", "config_version", "Attribute", "value_code"],
            "top_entities": [{"field": "config_version", "value": v, "metrics": {"lock_count": len(version_order_ids.get(v, set()))}} for v in versions],
        },
    )
    view_data = {
        "total_orders": len(order_ids),
        "selected_orders": len(selected_orders),
        "unselected_orders": len(unselected_orders),
        "start_date": str(start_date.date()),
        "as_of": str(as_of.date()),
        "versions": versions,
        "version_counts": [len(version_order_ids.get(v, set())) for v in versions],
        "common_matrix": common_matrix,
        "diff_rows": diff_rows,
        "all_series_total": len(order_ids),
        "attribute_level_summary": attribute_level_summary,
        "scope": scope,
    }
    return contract, complete_path, view_data


def render_html(view_data, output_path):
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template(REPORT_TEMPLATE)
    html = template.render(
        static_prefix="../..",
        title="LS8 上市以来配置拥有率报告",
        brand_name="Raccoon Research",
        meta=f"mashang | {view_data['as_of']}",
        hero_title="智己 LS8 上市以来配置拥有率报告",
        hero_subtitle=(
            f"用户车锁单 · {view_data['start_date']} 起 · 截止 {view_data['as_of']} · "
            f"总锁单 {view_data['total_orders']:,} 单"
        ),
        data=view_data,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main():
    args = parse_args()
    contract, complete_path, view_data = build_report_data(args.as_of)
    json_path = Path(args.output) if args.output else OUTPUT_DIR / "tables" / "ls8_configuration_selection_since_launch.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    save_contract_json(contract, json_path)

    html_path = OUTPUT_DIR / "reports" / "ls8_configuration_selection_since_launch.html"
    if args.html:
        render_html(view_data, html_path)

    if args.format == "json":
        print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(contract["result"]["summary"])
        print(json.dumps(contract["result"]["metrics"], ensure_ascii=False, indent=2))
        print(f"JSON: {json_path}")
        print(f"明细 CSV: {complete_path}")
        if args.html:
            print(f"HTML: {html_path}")


if __name__ == "__main__":
    main()
