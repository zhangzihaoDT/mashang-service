#!/usr/bin/env python3
"""
doubao-search — 豆包 Global Search 的底层搜索原语（dumb client）。

只负责：
  - API key / base URL 读取（根目录 .env）
  - API 请求 / retry / timeout
  - 24h 本地缓存
  - 归一化 / multi-query / JSON 输出

不负责"怎么研究"：查询策略、是否搜索、如何 refine 由调用方（Agent）决定。

用法:
  python3 search.py -q "小米 电机 供应商"
  python3 search.py -q "query one" -q "query two" -q "query three" --limit 8
  python3 search.py -q "今天发布的新闻" --refresh
  python3 search.py -q "..." --limit 10 --snippet-length 800
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import requests
from dotenv import find_dotenv, load_dotenv

CACHE_DIR = Path.home() / ".cache" / "opencode" / "doubao-search"
DEFAULT_TTL = 24 * 3600

# 可重试的 HTTP 状态码（429 限流 + 5xx 服务端错误）
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class DoubaoSearchError(Exception):
    """豆包搜索确定性失败（不可重试的 4xx 或重试耗尽）。"""


def load_environment():
    env_file = find_dotenv(usecwd=True)
    if env_file:
        load_dotenv(env_file)


def cache_key(query, limit, snippet_length):
    payload = {
        "provider": "doubao-global-search",
        "query": query,
        "limit": limit,
        "snippet_length": snippet_length,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def read_cache(key, ttl):
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > ttl:
        return None
    return json.loads(path.read_text())


def write_cache(key, data):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def _snippet_text(snippet):
    """Snippet 是数组，取 text 类型拼接（与 volc_search_client 一致）。"""
    if isinstance(snippet, str):
        return snippet
    if isinstance(snippet, list):
        parts = [
            s.get("Text", "")
            for s in snippet
            if isinstance(s, dict) and s.get("Type") == "text"
        ]
        return " ".join(parts)
    return ""


def search(query, limit, snippet_length, timeout, retries):
    api_key = os.environ["DOUBAO_SEARCH_GLOBAL_API_KEY"]
    base_url = os.environ["VOLC_SEARCH_BASE_URL"].rstrip("/")

    url = f"{base_url}/search_api/global_search"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "Query": query,
        "DocCount": limit,
        "MaxSnippetLength": snippet_length,
        "MaxImageCountPerDoc": 0,
    }

    last_error = None

    for attempt in range(retries):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )

            if response.status_code != 200:
                if response.status_code in RETRYABLE_STATUS:
                    # 429 / 5xx：可重试，走下面的重试逻辑
                    last_error = (
                        f"HTTP {response.status_code} "
                        f"(retryable)"
                    )
                else:
                    # 4xx（非 429）：fail fast，不重试
                    raise DoubaoSearchError(
                        f"HTTP {response.status_code}: {query[:80]!r}"
                    )
            else:
                body = response.json()
                docs = body.get("Result", {}).get("Documents", [])

                return [
                    {
                        "title": doc.get("Title", ""),
                        "url": doc.get("Url", ""),
                        "snippet": _snippet_text(doc.get("Snippet")),
                        "source": (doc.get("HostInfo") or {}).get("Hostname", ""),
                        "publish_time": (doc.get("DocumentInfo") or {}).get("PublishTime", ""),
                        "rank": index + 1,
                    }
                    for index, doc in enumerate(docs)
                ]

        except requests.exceptions.Timeout as exc:
            last_error = f"Timeout: {exc}"
        except requests.exceptions.ConnectionError as exc:
            last_error = f"ConnectionError: {exc}"
        except requests.exceptions.RequestException as exc:
            last_error = f"HTTP Error: {exc}"
        except (ValueError, KeyError, TypeError) as exc:
            last_error = f"Parse Error: {exc}"

        if attempt < retries - 1:
            time.sleep(2 * (attempt + 1))

    raise DoubaoSearchError(
        f"Doubao search failed after {retries} attempts: {last_error}"
    )


def run_query(args, query):
    key = cache_key(query, args.limit, args.snippet_length)

    if not args.refresh:
        cached = read_cache(key, args.cache_ttl)
        if cached is not None:
            return {"query": query, "cached": True, "results": cached}

    results = search(
        query=query,
        limit=args.limit,
        snippet_length=args.snippet_length,
        timeout=args.timeout,
        retries=args.retries,
    )
    write_cache(key, results)

    return {"query": query, "cached": False, "results": results}


def run_all(args):
    """执行所有查询，单条失败不中断，保留 partial results。

    每条查询结果含 status: success | error。
    一条查询失败（如 401 / 重试耗尽）不影响其他查询。
    """
    output = []
    for query in args.query:
        try:
            item = run_query(args, query)
            item["status"] = "success"
        except DoubaoSearchError as exc:
            item = {
                "query": query,
                "status": "error",
                "error": str(exc),
                "results": [],
            }
        output.append(item)
    return output


def main():
    parser = argparse.ArgumentParser(description="Doubao Global Search 底层搜索原语")
    parser.add_argument("-q", "--query", action="append", required=True,
                        help="搜索查询，可重复传多个实现 query fan-out")
    parser.add_argument("--limit", type=int, default=10, help="每个查询返回结果数")
    parser.add_argument("--snippet-length", type=int, default=500,
                        help="摘要长度（字符）")
    parser.add_argument("--timeout", type=int, default=30, help="请求超时（秒）")
    parser.add_argument("--retries", type=int, default=3, help="失败重试次数")
    parser.add_argument("--cache-ttl", type=int, default=DEFAULT_TTL,
                        help="缓存有效期（秒），默认 24h")
    parser.add_argument("--refresh", action="store_true",
                        help="忽略缓存强制请求 API")
    args = parser.parse_args()

    load_environment()

    required = ["DOUBAO_SEARCH_GLOBAL_API_KEY", "VOLC_SEARCH_BASE_URL"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            f"Missing environment variables: {', '.join(missing)} "
            f"(请在仓库根目录 .env 中配置)"
        )

    output = run_all(args)

    print(json.dumps({"searches": output}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
