#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
series_group_logic 规则重叠审计

检查 business_definition.json 的 series_group_logic 规则在真实 product_name 上：
  1. 每条规则的独立匹配 product_name 集合
  2. 命中多条规则的 product_name（重叠）——重叠应只在族内发生，且由 priority/precedence 正确裁决
  3. 跨车系重叠（同一 product_name 命中不同车系的规则）——这是规则治理问题，应报警

用法：
  python mashang_workspace/utility_scripts/audit_series_group_overlap.py
  python mashang_workspace/utility_scripts/audit_series_group_overlap.py --json
  python mashang_workspace/utility_scripts/audit_series_group_overlap.py --strict   # 存在跨车系重叠时返回非 0

输出：规则匹配数、重叠清单、跨车系重叠清单。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WS = _REPO_ROOT / "mashang_workspace"
_BUSINESS_DEF = _REPO_ROOT / "shared" / "schema" / "business_definition.json"
_ORDER_DATA = _REPO_ROOT / "dataset" / "order_data.parquet"
_SGL_MODULE = _REPO_ROOT / "shared" / "operators" / "series_group_logic.py"


def _load_sgl():
    spec = importlib.util.spec_from_file_location("audit_sgl", _SGL_MODULE)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {_SGL_MODULE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def audit_overlap(business_def: dict, product_names: list[str]) -> dict:
    """对 product_name 全集评估每条 series_group_logic 规则，返回匹配数与重叠清单。"""
    sgl = _load_sgl()
    logic = (business_def or {}).get("series_group_logic") or {}
    s = pd.Series(list(product_names), dtype="string")

    matched: dict[str, set] = {}
    for key, rule in logic.items():
        if str(key) == "其他":
            continue
        condition = rule.get("condition") if isinstance(rule, dict) else str(rule)
        mask = sgl._eval_series_group_logic_expr(s, condition)
        matched[str(key)] = set(s[mask].astype(str))

    overlaps: dict[str, list[str]] = {}
    for p in product_names:
        hits = [g for g, names in matched.items() if p in names]
        if len(hits) > 1:
            overlaps[p] = hits

    mapping = (business_def or {}).get("model_series_mapping") or {}
    series_of = {g: series for series, groups in mapping.items() for g in groups}
    cross_family = {
        p: hits for p, hits in overlaps.items()
        if len({series_of.get(g, g) for g in hits}) > 1
    }

    return {
        "rule_matches": {g: len(names) for g, names in matched.items()},
        "overlap_count": len(overlaps),
        "overlaps": overlaps,
        "cross_family_overlap_count": len(cross_family),
        "cross_family_overlaps": cross_family,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="series_group_logic 规则重叠审计")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--strict", action="store_true", help="存在跨车系重叠时返回非 0 退出码")
    args = parser.parse_args()

    if not _BUSINESS_DEF.exists():
        print(f"❌ 缺少 {_BUSINESS_DEF}")
        return 1
    business_def = json.loads(_BUSINESS_DEF.read_text(encoding="utf-8"))

    if not _ORDER_DATA.exists():
        print(f"❌ 缺少 {_ORDER_DATA}")
        return 1
    product_names = pd.read_parquet(_ORDER_DATA, columns=["product_name"])["product_name"].dropna().tolist()
    product_names = sorted(set(product_names))

    result = audit_overlap(business_def, product_names)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print("=== series_group_logic 规则匹配（distinct product_name）===")
    for g, c in sorted(result["rule_matches"].items(), key=lambda x: -x[1]):
        print(f"  {g}: {c}")

    print(f"\n=== 重叠（命中>=2 条规则，共 {result['overlap_count']} 个 product_name）===")
    for p, hits in sorted(result["overlaps"].items()):
        print(f"  {p!r} -> {hits}")

    print(f"\n=== 跨车系重叠（规则治理问题，共 {result['cross_family_overlap_count']} 个）===")
    if result["cross_family_overlaps"]:
        for p, hits in sorted(result["cross_family_overlaps"].items()):
            print(f"  ❌ {p!r} -> {hits}")
    else:
        print("  无")

    if args.strict and result["cross_family_overlap_count"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
