"""Search Service — search queries through a configured provider.

Usage:
    python -m capabilities.search.search_service -q "query" [-q "q2" ...]
    python -m capabilities.search.search_service -q "..." --provider mock
    python -m capabilities.search.search_service -q "..." --refresh --limit 8

Provider env:
    DOUBAO_SEARCH_GLOBAL_API_KEY
    VOLC_SEARCH_BASE_URL
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Iterable, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from capabilities.search.schemas import SearchRequest, SearchResponse
from capabilities.search.providers import get_provider


def search(request: SearchRequest) -> SearchResponse:
    provider = get_provider(request.provider)
    return provider.search(request)


def search_multi(
    queries: Iterable[str],
    *,
    provider_name: str = "doubao_global",
    limit: int = 10,
    snippet_length: int = 500,
    use_cache: bool = True,
    refresh: bool = False,
    timeout: int = 30,
    retries: int = 3,
    cache_ttl: Optional[int] = None,
    cache_dir: Optional[str] = None,
) -> list[SearchResponse]:
    """Run several queries; one failing query does not interrupt the others."""
    out = []
    for q in queries:
        request = SearchRequest(
            query=q,
            provider=provider_name,
            limit=limit,
            snippet_length=snippet_length,
            use_cache=use_cache,
            refresh=refresh,
            timeout=timeout,
            retries=retries,
            cache_ttl=cache_ttl,
            cache_dir=cache_dir,
        )
        out.append(search(request))
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Search Service — web search primitive")
    p.add_argument("-q", "--query", action="append", required=True, help="查询，可重复多个")
    p.add_argument("--provider", default="doubao_global", choices=["doubao_global", "mock"])
    p.add_argument("--limit", type=int, default=10, help="每查询返回结果数")
    p.add_argument("--snippet-length", type=int, default=500, help="摘要长度")
    p.add_argument("--timeout", type=int, default=30, help="请求超时（秒）")
    p.add_argument("--retries", type=int, default=3, help="失败重试次数")
    p.add_argument("--cache-ttl", type=int, default=None, help="缓存有效期（秒），默认 24h")
    p.add_argument("--refresh", action="store_true", help="忽略缓存强制请求 API")
    return p


def main():
    args = _build_parser().parse_args()
    responses = search_multi(
        args.query,
        provider_name=args.provider,
        limit=args.limit,
        snippet_length=args.snippet_length,
        use_cache=True,
        refresh=args.refresh,
        timeout=args.timeout,
        retries=args.retries,
    )
    payload = {
        "searches": [r.to_dict() for r in responses],
        "total_ok": sum(1 for r in responses if r.status == "success"),
        "total_failed": sum(1 for r in responses if r.status == "error"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if payload["total_failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
