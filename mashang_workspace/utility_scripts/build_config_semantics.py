#!/usr/bin/env python3
"""构建 config_semantics 业务定义表。

从 config_attribute.parquet 发现 (series, Attribute, value_code) 组合，
结合人工业务语义层（分类/选装性/价格），生成 config_semantics 写入
shared/schema/config_semantics.json。

覆盖范围：LS8 + LS9（未来可扩展其他车系）。
粒度：规范层 (Attribute, value_code)，value 显示名作为 aliases 附属。

用法：
    python mashang_workspace/utility_scripts/build_config_semantics.py
    python mashang_workspace/utility_scripts/build_config_semantics.py --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_SEMANTICS_PATH = REPO_ROOT / "shared" / "schema" / "config_semantics.json"
CONFIG_PARQUET = REPO_ROOT / "dataset" / "config_attribute.parquet"
ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"

SERIES_SCOPE = ["LS8", "LS9"]

# 人工业务语义层：{series: {attribute: {...}}}
# semantic 取值：
#   - selection_tier: 选装包档位（已选 Stand/Pro/Plus），每档 included=true
#   - enum: 单选款式（内饰/外饰/轮毂/方向盘/激光雷达），每 code 一个款式
#   - boolean: 是/否选装，included 由 code 决定（Y=是 选装；N=否 未选）
#   - noise: 极小量 NaN-only 历史噪音行，不计入统计
MANUAL_SEMANTICS = {
    "LS8": {
        "已选": {
            "category": "选装包",
            "semantic": "selection_tier",
            "display_name": "已选配置",
            "codes": {
                "Stand": {"display": "超远距高精度激光雷达", "price": 0, "note": "标配激光雷达"},
                "Pro": {"display": "奢华智选包", "price": 9800, "note": ""},
                "Plus": {"display": "奢华智选包及一体式超广域探射灯", "price": 13600, "note": "含奢华智选包 + 探射灯"},
            },
        },
        "内饰": {
            "category": "内饰",
            "semantic": "enum",
            "display_name": "内饰",
            "codes": {
                "IN2-ASH": {"display": "大象灰黑"},
                "IN3-ASA": {"display": "大象灰棕"},
                "IN2-AMA": {"display": "大象灰米"},
            },
        },
        "外饰": {
            "category": "外饰",
            "semantic": "enum",
            "display_name": "外饰",
            "codes": {
                "EX1-PYX": {"display": "奥林匹斯黑"},
                "EX1-AEG": {"display": "帕米尔灰"},
                "EX1-WSE": {"display": "阿尔卑斯白"},
                "EX1-SSA": {"display": "乔戈里银"},
                "EX1-GYC": {"display": "布莱德绿"},
            },
        },
        "轮毂": {
            "category": "轮毂",
            "semantic": "enum",
            "display_name": "轮毂",
            "codes": {
                "SD-TI21-J": {"display": "21英寸星耀超多辐豪华轮辋"},
                "SD-TI21": {"display": "21英寸星夜黑超多辐豪华轮辋"},
                "SD-TI20-J": {"display": "20英寸星刃十辐运动轮辋"},
                "SD-TI22": {"display": "22英寸星冕镜面超奢轮辋"},
            },
        },
        "方向盘": {
            "category": "方向盘",
            "semantic": "enum",
            "display_name": "方向盘",
            "codes": {
                "Oval": {"display": "超广角视野全幅柔感瞬热方向盘"},
                "Full": {"display": "全幅柔感瞬热方向盘"},
            },
        },
        "21.5英寸二排观影屏": {
            "category": "后排娱乐",
            "semantic": "boolean",
            "display_name": "21.5英寸二排观影屏",
        },
        "21.5英寸4K二排观影屏": {
            "category": "后排娱乐",
            "semantic": "boolean",
            "display_name": "21.5英寸4K二排观影屏",
        },
        "21.5英寸二排娱乐屏": {
            "category": "后排娱乐",
            "semantic": "boolean",
            "display_name": "21.5英寸二排娱乐屏",
        },
        "后排娱乐屏（仅5座可选）": {
            "category": "后排娱乐",
            "semantic": "boolean",
            "display_name": "后排娱乐屏（仅5座可选）",
        },
        "IM 智控地暖系统": {
            "category": "座舱舒适",
            "semantic": "boolean",
            "display_name": "IM 智控地暖系统",
        },
        "地暖": {
            "category": "座舱舒适",
            "semantic": "boolean",
            "display_name": "地暖",
        },
        "舒适包": {
            "category": "座舱舒适",
            "semantic": "boolean",
            "display_name": "舒适包",
        },
        "舒适包  （音响/机械按摩等）": {
            "category": "座舱舒适",
            "semantic": "boolean",
            "display_name": "舒适包（音响/机械按摩等）",
        },
        "全线控转向系统": {
            "category": "底盘操控",
            "semantic": "boolean",
            "display_name": "全线控转向系统",
        },
        "线控转向": {
            "category": "底盘操控",
            "semantic": "boolean",
            "display_name": "线控转向",
        },
        "顶探照灯": {
            "category": "智能交互",
            "semantic": "boolean",
            "display_name": "顶探照灯",
        },
        "超远距高精度双激光雷达": {
            "category": "智能驾驶",
            "semantic": "enum",
            "display_name": "超远距高精度双激光雷达",
            "codes": {
                "Pro": {"display": "高阶"},
                "Stand": {"display": "标准"},
            },
        },
        "智慧舒享包": {"category": "", "semantic": "noise", "display_name": ""},
        "超远距高精度激光雷达": {"category": "", "semantic": "noise", "display_name": ""},
        "激光雷达": {"category": "", "semantic": "noise", "display_name": ""},
    },
    "LS9": {
        "内饰": {
            "category": "内饰",
            "semantic": "enum",
            "display_name": "内饰",
            "codes": {
                "IN2-ASH": {"display": "大地象灰 深"},
                "IN2-AMA": {"display": "大地象灰 浅"},
                "IN1-ASH": {"display": "深色内饰（麂皮）"},
                "IN1-AMA": {"display": "浅色内饰（麂皮）"},
                "IN2-ASF": {"display": "大地橘色"},
            },
        },
        "外饰": {
            "category": "外饰",
            "semantic": "enum",
            "display_name": "外饰",
            "codes": {
                "EX1-PYX": {"display": "奥林匹斯黑"},
                "EX1-JND": {"display": "波罗蒂蓝"},
                "EX1-SSA": {"display": "乔戈里银"},
                "EX1-AEG": {"display": "高加索灰"},
            },
        },
        "轮毂": {
            "category": "轮毂",
            "semantic": "enum",
            "display_name": "轮毂",
            "codes": {
                "SD-TI21": {"display": "21英寸星耀超多辐豪华轮辋"},
                "SD-TI22": {"display": "22英寸星冕镜面超奢轮辋"},
            },
        },
        "方向盘": {
            "category": "方向盘",
            "semantic": "enum",
            "display_name": "方向盘",
            "codes": {
                "Half": {"display": "半幅方向盘"},
                "Full": {"display": "全幅方向盘"},
                "Oval": {"display": "小全幅方向盘"},
            },
        },
        "激光雷达": {
            "category": "智能驾驶",
            "semantic": "enum",
            "display_name": "激光雷达",
            "codes": {
                "Pro": {"display": "高阶+Thor"},
            },
        },
        "智能冷暖双用冰箱": {
            "category": "座舱舒适",
            "semantic": "boolean",
            "display_name": "智能冷暖双用冰箱",
        },
        "车载冰箱": {
            "category": "座舱舒适",
            "semantic": "boolean",
            "display_name": "车载冰箱",
        },
        "拖挂系统": {
            "category": "拖挂",
            "semantic": "boolean",
            "display_name": "拖挂系统",
        },
        "拖挂尾勾": {
            "category": "拖挂",
            "semantic": "boolean",
            "display_name": "拖挂尾勾",
        },
        "线控转向": {
            "category": "底盘操控",
            "semantic": "boolean",
            "display_name": "线控转向",
        },
        "动力电池": {
            "category": "动力电池",
            "semantic": "enum",
            "display_name": "动力电池",
            "codes": {
                "52": {"display": "52度电池"},
            },
        },
    },
}


def build_aliases_from_data():
    """从数据抓取每个 (series, attribute, code) 的全部 value 显示名。"""
    orders = pd.read_parquet(ORDER_PARQUET, columns=["order_number", "series"])
    orders["order_number"] = orders["order_number"].astype(str)
    configs = pd.read_parquet(
        CONFIG_PARQUET, columns=["Order Number", "Attribute", "value", "value_code"]
    )
    configs["Order Number"] = configs["Order Number"].astype(str)
    merged = configs.merge(
        orders, left_on="Order Number", right_on="order_number", how="left"
    )
    merged = merged[merged["series"].isin(SERIES_SCOPE)].copy()
    merged["vc"] = merged["value_code"].astype(str)
    merged.loc[merged["vc"].isin(["<NA>", "nan", "None"]), "vc"] = ""

    aliases = {}
    for (series, attribute, code), group in merged.groupby(
        ["series", "Attribute", "vc"], dropna=False
    ):
        if code == "":
            continue
        aliases.setdefault(series, {}).setdefault(attribute, {}).setdefault(
            code, {"aliases": [], "order_count": 0}
        )
        entry = aliases[series][attribute][code]
        for value in group["value"].dropna().unique():
            entry["aliases"].append(str(value))
        entry["aliases"] = list(dict.fromkeys(entry["aliases"]))
        entry["order_count"] = int(group["Order Number"].nunique())
    return aliases


def build_semantics(dry_run=False):
    aliases = build_aliases_from_data()
    config_semantics = {
        "description": (
            "基于 (Attribute, value_code) 的配置业务语义定义。报告脚本消费此表，"
            "替代代码内硬编码判定。value_code 为 NaN 的历史行按 (Attribute, value) "
            "经 aliases 反推归并（已校验 0 歧义）。noise 属性为极小量 NaN-only 历史噪音行。"
        ),
        "coverage": {"series": SERIES_SCOPE, "scope_note": "当前覆盖 LS8 + LS9"},
        "series": {},
    }
    warnings = []
    for series in SERIES_SCOPE:
        series_semantics = {"attributes": {}}
        manual = MANUAL_SEMANTICS.get(series, {})
        observed = aliases.get(series, {})
        for attribute, spec in sorted(manual.items()):
            if spec.get("semantic") == "noise":
                series_semantics["attributes"][attribute] = {
                    "category": "noise",
                    "semantic": "noise",
                }
                continue
            attr_entry = {
                "category": spec["category"],
                "semantic": spec["semantic"],
                "display_name": spec.get("display_name", attribute),
                "codes": {},
            }
            observed_codes = observed.get(attribute, {})
            if spec["semantic"] == "boolean":
                for code in ["Y", "N"]:
                    code_spec = {
                        "display": "是" if code == "Y" else "否",
                        "included": code == "Y",
                        "aliases": [],
                        "order_count": 0,
                    }
                    if code in observed_codes:
                        code_spec["aliases"] = observed_codes[code]["aliases"]
                        code_spec["order_count"] = observed_codes[code]["order_count"]
                    attr_entry["codes"][code] = code_spec
            else:
                for code, code_manual in spec.get("codes", {}).items():
                    code_spec = {
                        "display": code_manual["display"],
                        "included": True,
                        "aliases": [],
                        "order_count": 0,
                    }
                    if code_manual.get("price") is not None:
                        code_spec["price"] = code_manual["price"]
                    if code_manual.get("note"):
                        code_spec["note"] = code_manual["note"]
                    if code in observed_codes:
                        code_spec["aliases"] = observed_codes[code]["aliases"]
                        code_spec["order_count"] = observed_codes[code]["order_count"]
                    attr_entry["codes"][code] = code_spec
            # 校验：手动定义的 code 是否都在数据中出现（enum/selection_tier）
            if spec["semantic"] in ("enum", "selection_tier"):
                for code in spec.get("codes", {}):
                    if code not in observed_codes:
                        warnings.append(f"{series}.{attribute}.{code} 未在数据中出现")
            series_semantics["attributes"][attribute] = attr_entry
        config_semantics["series"][series] = series_semantics

    # 校验：数据中出现但未定义的 (attribute, code)
    for series in SERIES_SCOPE:
        observed = aliases.get(series, {})
        manual = MANUAL_SEMANTICS.get(series, {})
        for attribute, codes in observed.items():
            if attribute not in manual:
                warnings.append(f"{series}.{attribute} 未在人工定义中（观测到 {len(codes)} 个 code）")
    return config_semantics, warnings


def main():
    parser = argparse.ArgumentParser(description="构建 config_semantics 业务定义表")
    parser.add_argument("--dry-run", action="store_true", help="只校验不写入")
    args = parser.parse_args()

    config_semantics, warnings = build_semantics(dry_run=args.dry_run)

    if not args.dry_run:
        CONFIG_SEMANTICS_PATH.write_text(
            json.dumps(config_semantics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[Written] {CONFIG_SEMANTICS_PATH}")
    else:
        print("[Dry-run] 不写入，仅输出校验结果")
        print(json.dumps(config_semantics, ensure_ascii=False, indent=2)[:2000])

    if warnings:
        print("[Warnings]")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("[Warnings] 无")


if __name__ == "__main__":
    main()
