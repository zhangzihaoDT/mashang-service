#!/usr/bin/env python3
"""
doubao-search — 豆包 Global Search 的**底层搜索原语**入口（薄壳）。

底层实现已收敛至 Base Capability：`capabilities/search`（providers=doubao_global）。
本脚本仅负责把 skill 侧用法（multi-query / --refresh / --limit 等）映射到能力，
并保持历史 JSON 输出形状（{"searches": [...]}）不变。

只负责调用原语，不负责"怎么研究"：查询策略、是否搜索、如何 refine 由调用方（Agent）决定。

用法:
  python3 scripts/search.py -q "小米 电机 供应商"
  python3 scripts/search.py -q "query one" -q "query two" --limit 8
  python3 scripts/search.py -q "今天发布的新闻" --refresh
"""

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import find_dotenv, load_dotenv  # noqa: E402
from capabilities.search.search_service import search_multi  # noqa: E402

REQUIRED_ENV = ["DOUBAO_SEARCH_GLOBAL_API_KEY", "VOLC_SEARCH_BASE_URL"]


def load_environment():
    env_file = find_dotenv(usecwd=True)
    if env_file:
        load_dotenv(env_file)


def main():
    parser = argparse.ArgumentParser(description="Doubao Global Search 底层搜索原语")
    parser.add_argument("-q", "--query", action="append", required=True,
                        help="搜索查询，可重复传多个实现 query fan-out")
    parser.add_argument("--limit", type=int, default=10, help="每个查询返回结果数")
    parser.add_argument("--snippet-length", type=int, default=500, help="摘要长度（字符）")
    parser.add_argument("--timeout", type=int, default=30, help="请求超时（秒）")
    parser.add_argument("--retries", type=int, default=3, help="失败重试次数")
    parser.add_argument("--cache-ttl", type=int, default=None,
                        help="缓存有效期（秒），默认 24h")
    parser.add_argument("--refresh", action="store_true",
                        help="忽略缓存强制请求 API")
    args = parser.parse_args()

    load_environment()

    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            f"Missing environment variables: {', '.join(missing)} "
            f"(请在仓库根目录 .env 中配置)"
        )

    responses = search_multi(
        args.query,
        provider_name="doubao_global",
        limit=args.limit,
        snippet_length=args.snippet_length,
        use_cache=True,
        refresh=args.refresh,
        timeout=args.timeout,
        retries=args.retries,
        cache_ttl=args.cache_ttl,
    )

    # 保持历史输出形状（skill 侧读取的子集字段）
    output = []
    for r in responses:
        item = {
            "query": r.query,
            "cached": r.cached,
            "status": r.status,
            "results": r.results,
        }
        if r.status == "error":
            item["error"] = r.error
        output.append(item)

    print(json.dumps({"searches": output}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
