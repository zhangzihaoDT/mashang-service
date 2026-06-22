#!/usr/bin/env python
"""
与重点品牌 watchlist 做增量 diff。

用法:
  python mashang_workspace/research_scripts/miit_new_car/diff_watchlist.py --batch 408
  python mashang_workspace/research_scripts/miit_new_car/diff_watchlist.py --batch 408 --previous-batch 407
  python mashang_workspace/research_scripts/miit_new_car/diff_watchlist.py --batch 408 --format json
"""

import sys, json, csv, argparse
from pathlib import Path
from typing import Optional

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT))

DEFAULT_WATCHLIST = WORKSPACE_ROOT / "configs" / "miit_new_car_watchlist.csv"
PARSED_BASE = WORKSPACE_ROOT / "outputs" / "miit_new_car" / "parsed"
DIFF_BASE = WORKSPACE_ROOT / "outputs" / "miit_new_car" / "diff"
STATE_FILE = WORKSPACE_ROOT / "outputs" / "miit_new_car" / "state" / "latest_processed_batch.json"

TARGET_FIELDS = [
    "batch_no", "batch_status", "publish_date",
    "publicity_start", "publicity_end",
    "enterprise_name", "brand", "product_model", "vehicle_name",
    "product_type", "energy_type", "fuel_type", "battery_type",
    "range_km", "motor_power", "dimensions",
    "source_url", "asset_url", "ingested_at",
]


def _load_watchlist(path: Path) -> list[dict]:
    if not path.exists():
        print(f"[WARN] watchlist 不存在: {path}，使用默认空列表")
        return []
    entries = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            brand = row.get("brand", "").strip()
            keywords = row.get("keywords", brand).strip()
            if brand:
                entries.append({"brand": brand, "keywords": keywords})
    return entries


def _load_previous_products(batch_no: int) -> list[dict]:
    json_path = PARSED_BASE / f"batch_{batch_no}_products.json"
    if not json_path.exists():
        return []
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _keyword_match(enterprise_name: str, brand: str, product_model: str, vehicle_name: str, keywords: str) -> bool:
    """检查 product record 是否匹配 watchlist 中的 keywords。"""
    text = f"{enterprise_name} {brand} {product_model} {vehicle_name}"
    for kw in keywords.split(";"):
        kw = kw.strip()
        if kw and kw in text:
            return True
    return False


def diff_batch(
    batch_no: int,
    previous_batch: Optional[int] = None,
    watchlist_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    state_update: bool = True,
) -> dict:
    """对比指定批次与上一批/watchlist，输出 diff。"""
    watchlist_path = watchlist_path or DEFAULT_WATCHLIST
    watchlist = _load_watchlist(watchlist_path)

    # Load current batch
    current = _load_previous_products(batch_no)
    if not current:
        raise FileNotFoundError(
            f"当前批次解析结果不存在: {PARSED_BASE / f'batch_{batch_no}_products.json'}\n"
            f"请先运行 parse_products.py --batch {batch_no}"
        )

    # Determine previous batch
    if previous_batch is None:
        prev_no = (batch_no // 10) * 10 - 1 if batch_no % 10 == 0 else batch_no - 1
        # Try the actual previous batch
        for candidate in range(batch_no - 1, max(batch_no - 5, 0), -1):
            if (PARSED_BASE / f"batch_{candidate}_products.json").exists():
                prev_no = candidate
                break
        previous_batch = prev_no

    previous = _load_previous_products(previous_batch)

    # Build identifier map for previous batch
    prev_ids: set[str] = set()
    for p in previous:
        key = f"{p.get('enterprise_name', '')}|{p.get('product_model', '')}|{p.get('vehicle_name', '')}"
        if key.strip("|"):
            prev_ids.add(key)

    # Watchlist matches
    matched: list[dict] = []
    unmatched: list[dict] = []
    new_products: list[dict] = []
    for p in current:
        # Check if this is a new product (not in previous batch)
        key = f"{p.get('enterprise_name', '')}|{p.get('product_model', '')}|{p.get('vehicle_name', '')}"
        is_new = key.strip("|") and key not in prev_ids

        # Check watchlist match
        wl_match = _keyword_match(
            p.get("enterprise_name", ""),
            p.get("brand", ""),
            p.get("product_model", ""),
            p.get("vehicle_name", ""),
            ";".join(w["keywords"] for w in watchlist),
        )

        entry = {
            **p,
            "is_new": is_new,
            "watchlist_match": wl_match,
        }

        if wl_match:
            matched.append(entry)
        else:
            unmatched.append(entry)
        if is_new:
            new_products.append(entry)

    result = {
        "batch_no": batch_no,
        "previous_batch": previous_batch,
        "total_products": len(current),
        "watchlist_matched": len(matched),
        "new_products": len(new_products),
        "new_watchlist_matched": sum(1 for p in new_products if p["watchlist_match"]),
        "watchlist": watchlist,
        "matched_products": matched,
        "new_products_detail": new_products,
    }

    # Save diff output
    out_dir = output_dir or DIFF_BASE
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"batch_{batch_no}_watchlist_diff"

    # JSON
    json_path = out_dir / f"{prefix}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  JSON: {json_path}")

    # Markdown
    md_path = out_dir / f"{prefix}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 第 {batch_no} 批重点品牌 Watchlist Diff\n\n")
        f.write(f"- 对比基准: 第 {previous_batch} 批\n")
        f.write(f"- 总产品数: {result['total_products']}\n")
        f.write(f"- Watchlist 匹配: {result['watchlist_matched']} 个\n")
        f.write(f"- 新增产品: {result['new_products']} 个\n")
        f.write(f"- 新增匹配: {result['new_watchlist_matched']} 个\n\n")

        f.write("## Watchlist 匹配产品\n\n")
        f.write("| 企业名称 | 品牌 | 产品型号 | 车辆名称 | 新增 |\n")
        f.write("|---------|------|---------|--------|----|\n")
        for p in matched:
            label = "🆕" if p["is_new"] else ""
            f.write(f"| {p['enterprise_name']} | {p['brand']} | {p['product_model']} | {p['vehicle_name']} | {label} |\n")

        f.write("\n## 新增产品\n\n")
        f.write("| 企业名称 | 品牌 | 产品型号 | 车辆名称 | Watchlist |\n")
        f.write("|---------|------|---------|--------|----------|\n")
        for p in new_products:
            wl_label = "✅" if p["watchlist_match"] else ""
            f.write(f"| {p['enterprise_name']} | {p['brand']} | {p['product_model']} | {p['vehicle_name']} | {wl_label} |\n")
    print(f"  Markdown: {md_path}")

    # Update state
    if state_update:
        state_dir = STATE_FILE.parent
        state_dir.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "latest_batch_no": batch_no,
                "previous_batch_no": previous_batch,
                "last_run": result["new_products_detail"][0].get("ingested_at", "") if result["new_products_detail"] else "",
                "status": "success",
            }, f, ensure_ascii=False, indent=2)

    return result


def main():
    p = argparse.ArgumentParser(description="对指定批次做 watchlist diff")
    p.add_argument("--batch", type=int, required=True, help="批次号")
    p.add_argument("--previous-batch", type=int, help="上一批次号（默认自动推断）")
    p.add_argument("--watchlist", type=str, help="watchlist CSV 路径")
    p.add_argument("--output-dir", type=str, help="输出目录")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    args = p.parse_args()

    try:
        result = diff_batch(
            batch_no=args.batch,
            previous_batch=args.previous_batch,
            watchlist_path=Path(args.watchlist) if args.watchlist else None,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    if args.format == "json":
        summary = {k: v for k, v in result.items() if k not in ("matched_products", "new_products_detail", "watchlist")}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    wl_names = [w["brand"] for w in result["watchlist"]] if result.get("watchlist") else []
    print(f"\n[Summary] 第 {result['batch_no']} 批 Watchlist Diff")
    print(f"  对比基准: 第 {result['previous_batch']} 批")
    print(f"  总产品: {result['total_products']}")
    print(f"  Watchlist 命中: {result['watchlist_matched']} / {len(wl_names)} 品牌")
    print(f"  新增产品: {result['new_products']} (其中 watchlist 相关: {result['new_watchlist_matched']})")
    if result.get("watchlist"):
        print(f"  Watchlist: {', '.join(wl_names)}")


if __name__ == "__main__":
    main()
