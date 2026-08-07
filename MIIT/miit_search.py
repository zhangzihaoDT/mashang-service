#!/usr/bin/env python3
"""
MIIT 公告品牌搜索工具

从 brand_watchlist.yaml 读取品牌列表，
在指定批次的 MIIT 新产品公示中搜索各品牌的新车申报信息。

用法:
  python miit_search.py                           # 搜索第 409 批所有品牌
  python miit_search.py --batch 409               # 指定批次
  python miit_search.py --brand 智己              # 只搜索指定品牌
  python miit_search.py --format json             # JSON 输出
"""

import argparse
import json
import time
import sys
from pathlib import Path
from urllib.parse import urlencode, quote

import requests
import yaml

# ── MIIT API 配置 ──────────────────────────────────────────────────
MIIT_API = "https://www.miit.gov.cn/api-gateway/jpaas-publish-server/front/page/build/unit"
# 每个公告批次对应独立的 pageId 与 iframe 索引目录，需按批次切换
BATCH_CONFIG = {
    "409": {
        "pageId": "49d24aca2b7f42e599691da4cc329220",
        "index": "xcpgs409dwdwe233",
    },
    "410": {
        "pageId": "f7397ceb83214c88b85595615baf5d03",
        "index": "xcpgs410we24r34",
    },
}
DEFAULT_BATCH = "409"

BASE_PARAMS_TEMPLATE = {
    "webId": "b3eba6883f9240e2b51025f690afbae8",
    "parseType": "buildstatic",
    "pageType": "column",
    "tagId": "信息列表",
    "tplSetId": "9a9a7b87a4444169bdef99ff1f84e1aa",
    "unitUrl": "/api-gateway/jpaas-publish-server/front/page/build/unit",
}

# ── 路径 ────────────────────────────────────────────────────────────
HERE = Path(__file__).parent
WATCHLIST_PATH = HERE / "brand_watchlist.yaml"


def load_watchlist():
    """Load and flatten MIIT/brand_watchlist.yaml into brand list format.

    Original format is category-grouped:
       一线新能源:
         - 小米
         - 蔚来

    Returns same structure as old priority_brand_watchlist.yaml for compatibility.
    """
    with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    brands = []
    for category, names in data.items():
        for name in names:
            brands.append({"catalog": name, "keywords": [name]})
    return {"brands": brands, "watchlist_name": "MIIT 公告关注品牌清单"}


def get_batch_config(batch: str) -> dict:
    return BATCH_CONFIG.get(batch, BATCH_CONFIG[DEFAULT_BATCH])


def build_headers(batch: str) -> dict:
    cfg = get_batch_config(batch)
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/150.0.0.0 Safari/537.36",
        "Referer": f"https://www.miit.gov.cn/datainfo/dljdclscqyjcpgg/"
                   f"{cfg['index']}/index.html",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "*/*",
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    }


# Shared session for cookie persistence
SESSION = requests.Session()


def _prime_session(batch: str):
    cfg = get_batch_config(batch)
    SESSION.headers.update(build_headers(batch))
    try:
        SESSION.get(
            f"https://www.miit.gov.cn/datainfo/dljdclscqyjcpgg/"
            f"{cfg['index']}/index.html",
            timeout=15,
        )
    except Exception:
        pass  # non-fatal; the page visit is just for cookie priming


def search_batch(batch: str, cpsb: str = "", qymc: str = "") -> dict:
    """
    调用 MIIT API 搜索指定批次。
    cpsb: 产品商标  qymc: 企业名称
    """
    cfg = get_batch_config(batch)
    _prime_session(batch)
    search_obj = {
        "title": "",
        "PICI": batch,
        "QYMC": qymc or " ",
        "CPSB": cpsb,
        "CPMC": "",
        "CPXH": "",
    }
    param_json = {
        "pageNo": 1,
        "loadEnabled": True,
        "search": json.dumps(search_obj, ensure_ascii=False, separators=(",", ":")),
        "pageSize": "20",
    }
    base_params = {**BASE_PARAMS_TEMPLATE, "pageId": cfg["pageId"]}
    params = {**base_params, "paramJson": json.dumps(param_json, ensure_ascii=False, separators=(",", ":"))}

    resp = SESSION.get(MIIT_API, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # 解析 HTML 中的表格行
    rows = _parse_table_html(data.get("data", {}).get("html", ""))
    return {
        "batch": batch,
        "cpsb": cpsb,
        "qymc": qymc,
        "count": len(rows),
        "rows": rows,
    }


def _parse_table_html(html: str) -> list[dict]:
    """从 MIIT 返回的 HTML 中解析表格行"""
    import re

    rows = []
    # 找 tbody 内的所有 tr
    pattern = r'<tbody[^>]*>(.*?)</tbody>'
    m = re.search(pattern, html, re.DOTALL)
    if not m:
        # 可能没有 tbody, 直接找 tr
        m = re.search(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)
    if not m:
        return rows

    table_html = m.group(1)
    tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
    td_pattern = re.compile(r'<td[^>]*>.*?<a[^>]*>(.*?)</a>.*?</td>', re.DOTALL)

    for tr_match in tr_pattern.finditer(table_html):
        tr_content = tr_match.group(1)
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr_content, re.DOTALL)
        # 列顺序: 标题 / 批次 / 企业名称 / 产品商标 / 产品名称 / 产品型号
        if len(tds) >= 6:
            def extract(td):
                text = re.sub(r'<[^>]+>', ' ', td)
                return re.sub(r'\s+', ' ', text).strip()
            # Extract detail URL from first column's anchor
            url_m = re.search(r'href=\"([^\"]+)\"', tds[0])
            detail_url = url_m.group(1) if url_m else ""
            rows.append({
                "qymc": extract(tds[2]),
                "cpsb": extract(tds[3]),
                "cpmc": extract(tds[4]),
                "cpxh": extract(tds[5]),
                "detail_url": detail_url,
            })

    # 跳过表头行
    return [r for r in rows if r["cpsb"] and not r["cpsb"].startswith("产品")]


def get_search_keywords(brand_entry: dict) -> list[str]:
    """
    从品牌配置中提取搜索关键词。
    先试 catalog, 再试 keywords.
    """
    keywords = [brand_entry["catalog"]]
    if "keywords" in brand_entry:
        keywords.extend(brand_entry["keywords"])
    return list(dict.fromkeys(keywords))  # 去重保序


def search_brand_in_batch(brand_entry: dict, batch: str) -> dict:
    """搜索单个品牌在指定批次中的申报信息"""
    cat = brand_entry["catalog"]
    search_terms = get_search_keywords(brand_entry)

    results = {"catalog": cat, "searches": [], "all_rows": [], "total_count": 0}

    for term in search_terms:
        for field, label in [("cpsb", "产品商标"), ("qymc", "企业名称")]:
            kwargs = {"batch": batch, field: term}
            try:
                res = search_batch(**kwargs)
                if res["count"] > 0:
                    results["searches"].append({
                        "field": label,
                        "term": term,
                        "count": res["count"],
                    })
                    results["all_rows"].extend(res["rows"])
                    results["total_count"] += res["count"]
            except requests.HTTPError as e:
                if e.response.status_code == 403:
                    continue  # 跳过被限的搜索方式
                results.setdefault("errors", []).append(
                    f"{label}={term}: {e}"
                )
            except Exception as e:
                results.setdefault("errors", []).append(
                    f"{label}={term}: {e}"
                )
        time.sleep(1.0)

    # 去重 (同一型号只保留一条)
    seen = set()
    deduped = []
    for row in results["all_rows"]:
        key = row["cpxh"]
        if key not in seen:
            seen.add(key)
            deduped.append(row)
    results["all_rows"] = deduped
    results["total_count"] = len(deduped)

    return results


def format_text_report(brand_results: list[dict]) -> str:
    lines = []
    for br in brand_results:
        lines.append(f"\n{'='*60}")
        lines.append(f"品牌: {br['catalog']}")
        ways = ", ".join(f'{s["field"]}={s["term"]}({s["count"]}条)' for s in br["searches"])
        lines.append(f"共 {br['total_count']} 条记录 (搜索方式: {ways})")
        lines.append("-"*60)
        if br["total_count"] == 0:
            lines.append("  无数据")
        else:
            for row in br["all_rows"]:
                lines.append(f"  {row['qymc']} | {row['cpsb']} | {row['cpmc']} | {row['cpxh']}")
                if "extra" in row:
                    lines.append(f"    备注: {row['extra']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="MIIT 公告品牌搜索工具")
    parser.add_argument("--batch", default=DEFAULT_BATCH, help=f"公告批次号 (默认 {DEFAULT_BATCH})")
    parser.add_argument("--brand", help="只搜索指定品牌 catalog (如 智己)")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    args = parser.parse_args()

    watchlist = load_watchlist()
    brands = watchlist.get("brands", [])

    if args.brand:
        brands = [b for b in brands if b["catalog"] == args.brand]
        if not brands:
            print(f"未找到品牌: {args.brand}")
            sys.exit(1)

    results = []
    for brand in brands:
        print(f"搜索 {brand['catalog']} ...", file=sys.stderr)
        res = search_brand_in_batch(brand, args.batch)
        results.append(res)

    if args.format == "json":
        report = {
            "watchlist": watchlist.get("watchlist_name"),
            "batch": args.batch,
            "brands": results,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(results))


if __name__ == "__main__":
    main()
