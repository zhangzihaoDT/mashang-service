"""Layer: Search Pipeline — Volc Search API 客户端"""
"""
volc_search_client.py — Volc Search API 客户端。

环境变量:
  VOLC_SEARCH_BASE_URL
   DOUBAO_SEARCH_GLOBAL_API_KEY

用法:
  python volc_search_client.py --query "极氪 最近7天 权益" --output results.json
"""

import json, os, sys, time
from pathlib import Path
from datetime import datetime

MODULE_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = MODULE_DIR.parent
PROJECT_ROOT = SERVICE_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import requests
except ImportError:
    requests = None


class VolcSearchError(Exception):
    pass


class VolcSearchClient:
    """Volc Search API 轻量客户端"""

    def __init__(self, base_url: str = None, api_key: str = None,
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

    @property
    def _search_path(self) -> str:
        """豆包搜索 Global版 API 路径"""
        return "/search_api/global_search"

    def _transform_request(self, query: str, result_limit: int) -> dict:
        """将内部查询参数转为豆包搜索 API 请求格式"""
        return {
            "Query": query,
            "DocCount": result_limit,
            "MaxSnippetLength": 500,
            "MaxImageCountPerDoc": 0,
        }

    def _transform_response(self, raw: dict, query: str, attempt: int) -> dict:
        """将豆包搜索 API 响应转为内部统一格式"""
        result = raw.get("Result")
        if not result:
            docs = []
        else:
            docs = result.get("Documents", [])
        items = []
        for doc in docs:
            snippets = doc.get("Snippet", [])
            snippet_text = " ".join(
                s.get("Text", "") for s in snippets if s.get("Type") == "text"
            )
            host_info = doc.get("HostInfo", {})
            doc_info = doc.get("DocumentInfo", {})
            items.append({
                "title": doc.get("Title", ""),
                "url": doc.get("Url", ""),
                "snippet": snippet_text,
                "source": host_info.get("Hostname", ""),
                "source_name": host_info.get("Hostname", ""),
                "publish_time": doc_info.get("PublishTime", ""),
                "rank": doc.get("Rank", 0),
            })

        return {
            "query": query,
            "status": "success",
            "result_count": len(items),
            "results": items,
            "raw_response": raw,
            "retrieved_at": datetime.now().isoformat(),
            "attempts": attempt,
        }

    def search(self, query: str, result_limit: int = 10) -> dict:
        """执行单次搜索，返回原始响应"""
        if requests is None:
            raise VolcSearchError("requests 库未安装: pip install requests")

        url = f"{self.base_url}{self._search_path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = self._transform_request(query, result_limit)

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(
                    url, headers=headers, json=payload,
                    timeout=self.timeout
                )
                resp.raise_for_status()
                data = resp.json()
                return self._transform_response(data, query, attempt)

            except requests.exceptions.Timeout as e:
                last_error = f"Timeout: {e}"
            except requests.exceptions.RequestException as e:
                last_error = f"HTTP Error: {e}"
            except json.JSONDecodeError as e:
                last_error = f"JSON Parse Error: {e}"

            if attempt < self.max_retries:
                time.sleep(self.retry_delay)

        return {
            "query": query,
            "status": "error",
            "error": last_error,
            "result_count": 0,
            "results": [],
            "raw_response": None,
            "retrieved_at": datetime.now().isoformat(),
            "attempts": self.max_retries,
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
    parser = argparse.ArgumentParser(description="Volc Search 客户端")
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
    import argparse
    main()
