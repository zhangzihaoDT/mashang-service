"""Layer: Search Pipeline — Volc Search API 客户端（兼容薄封装）

底层传输已收敛至 Base Capability `capabilities/search`（provider=doubao_global）。
本模块保留 `VolcSearchClient` / `VolcSearchError` / `search` / `search_batch` 对外接口与
返回 envelope（query/status/result_count/results/raw_response/retrieved_at/attempts/meta），
使 auto_launch 各消费模块与测试无感。auto_launch 自有缓存层（search_cache）保持在上层。

环境变量:
  VOLC_SEARCH_BASE_URL
  DOUBAO_SEARCH_GLOBAL_API_KEY

用法:
  python volc_search_client.py --query "极氪 最近7天 权益" --output results.json
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from capabilities.search.search_service import search as capability_search  # noqa: E402
from capabilities.search.schemas import SearchRequest  # noqa: E402


class VolcSearchError(Exception):
    pass


class VolcSearchClient:
    """Volc Search API 轻量客户端（兼容封装，传输在 capabilities/search）。

    auto_launch 上层自管缓存，因此默认 use_cache=False；超时/重试次数透传。
    """

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None,
                 timeout: int = 30, max_retries: int = 3, retry_delay: int = 2):
        self.base_url = base_url or os.environ.get("VOLC_SEARCH_BASE_URL", "")
        self.api_key = api_key or os.environ.get("DOUBAO_SEARCH_GLOBAL_API_KEY", "")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        if not self.base_url or not self.api_key:
            raise VolcSearchError(
                "Missing DOUBAO_SEARCH_GLOBAL_API_KEY or VOLC_SEARCH_BASE_URL. "
                "Please export them before running Volc Search."
            )

    def _error_envelope(self, query: str, error: str) -> dict:
        return {
            "query": query,
            "status": "error",
            "error": error,
            "result_count": 0,
            "results": [],
            "raw_response": None,
            "retrieved_at": datetime.now().isoformat(),
            "attempts": self.max_retries,
        }

    def search(self, query: str, result_limit: int = 10) -> dict:
        """执行单次搜索，返回兼容 envelope。失败不抛（status=error）。"""
        request = SearchRequest(
            query=query,
            provider="doubao_global",
            limit=result_limit,
            snippet_length=500,
            use_cache=False,
            timeout=self.timeout,
            retries=self.max_retries,
            api_key=self.api_key,
            base_url=self.base_url,
        )
        resp = capability_search(request)

        if resp.status == "error":
            return self._error_envelope(query, resp.error or "unknown error")

        results = []
        for doc in resp.results:
            item = dict(doc)
            item.setdefault("source_name", item.get("source", ""))
            results.append(item)

        return {
            "query": query,
            "status": "success",
            "result_count": len(results),
            "results": results,
            "raw_response": None,
            "retrieved_at": datetime.now().isoformat(),
            "attempts": 1,
        }

    def search_batch(self, queries: list[dict], result_limit: int = 10) -> list[dict]:
        """批量搜索，单条失败不中断"""
        results = []
        for q_item in queries:
            query = q_item["query"] if isinstance(q_item, dict) else q_item
            r = self.search(query, result_limit)
            r["meta"] = q_item if isinstance(q_item, dict) else {}
            results.append(r)
        return results


def main():
    parser = __import__("argparse").ArgumentParser(description="Volc Search 客户端")
    parser.add_argument("--query", required=True, help="搜索查询")
    parser.add_argument("--limit", type=int, default=10, help="每查询结果数")
    parser.add_argument("--output", help="输出路径")
    args = parser.parse_args()

    try:
        client = VolcSearchClient()
        result = client.search(args.query, args.limit)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"[search] 已写入: {args.output}")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))

    except VolcSearchError as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
