"""Doubao / Volc Global Search provider.

Calls `{VOLC_SEARCH_BASE_URL}/search_api/global_search` (a dumb transport client):
  - Bearer auth via DOUBAO_SEARCH_GLOBAL_API_KEY
  - retry on 429 / 5xx; other 4xx fail fast
  - optional 24h local cache (content-addressed on query/limit/snippet_length)
Query strategy / refinement is NOT here — it belongs to the caller.

Env vars:
  DOUBAO_SEARCH_GLOBAL_API_KEY
  VOLC_SEARCH_BASE_URL
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from capabilities.search.schemas import (
    SearchResponse,
    SearchRequest,
    SearchDocument,
    cache_key,
    snippet_text,
    DEFAULT_CACHE_DIR,
    DEFAULT_TTL,
)

# Retryable HTTP statuses: 429 rate limit + 5xx server errors
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
BACKOFF_SECONDS = [2, 4, 8]


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


class DoubaoGlobalProvider:
    name = "doubao_global"

    def _endpoint(self, base_url: str) -> str:
        return f"{base_url.rstrip('/')}/search_api/global_search"

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _failed(self, request: SearchRequest, error: str) -> SearchResponse:
        return SearchResponse(
            provider=self.name,
            query=request.query,
            status="error",
            error=error,
            created_at=self._now(),
        )

    def _load_cache(self, request: SearchRequest, key: str) -> Optional[list]:
        cache_dir = Path(request.cache_dir or DEFAULT_CACHE_DIR)
        path = cache_dir / f"{key}.json"
        if not path.exists():
            return None
        age = time.time() - path.stat().st_mtime
        if age > (request.cache_ttl or DEFAULT_TTL):
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_cache(self, request: SearchRequest, key: str, data: list):
        cache_dir = Path(request.cache_dir or DEFAULT_CACHE_DIR)
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"{key}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def search(self, request: SearchRequest) -> SearchResponse:
        now = self._now()
        api_key = request.api_key or _env("DOUBAO_SEARCH_GLOBAL_API_KEY")
        base_url = request.base_url or _env("VOLC_SEARCH_BASE_URL")
        if not api_key or not base_url:
            return self._failed(
                request,
                "DOUBAO_SEARCH_GLOBAL_API_KEY and VOLC_SEARCH_BASE_URL must be set "
                "(and no api_key/base_url provided)",
            )

        key = cache_key(request.query, request.limit, request.snippet_length, self.name)

        if request.use_cache and not request.refresh:
            cached = self._load_cache(request, key)
            if cached is not None:
                return SearchResponse(
                    provider=self.name,
                    query=request.query,
                    status="success",
                    cached=True,
                    result_count=len(cached),
                    results=cached,
                    created_at=now,
                )

        url = self._endpoint(base_url)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "Query": request.query,
            "DocCount": request.limit,
            "MaxSnippetLength": request.snippet_length,
            "MaxImageCountPerDoc": 0,
        }

        last_error: Optional[str] = None
        for attempt in range(request.retries):
            try:
                resp = httpx.post(url, headers=headers, json=payload, timeout=request.timeout)
                if resp.status_code != 200:
                    if resp.status_code in RETRYABLE_STATUS:
                        last_error = f"HTTP {resp.status_code} (retryable)"
                    else:
                        # Non-retryable 4xx: fail fast
                        return self._failed(request, f"HTTP {resp.status_code}: {request.query[:80]!r}")
                else:
                    body = resp.json()
                    docs = body.get("Result", {}).get("Documents", [])
                    results = []
                    for index, doc in enumerate(docs):
                        d = SearchDocument(
                            title=doc.get("Title", ""),
                            url=doc.get("Url", ""),
                            snippet=snippet_text(doc.get("Snippet")),
                            source=(doc.get("HostInfo") or {}).get("Hostname", ""),
                            publish_time=(doc.get("DocumentInfo") or {}).get("PublishTime", ""),
                            rank=index + 1,
                        )
                        results.append(d.to_dict())
                    if request.use_cache:
                        self._write_cache(request, key, results)
                    return SearchResponse(
                        provider=self.name,
                        query=request.query,
                        status="success",
                        result_count=len(results),
                        results=results,
                        created_at=now,
                    )
            except httpx.TimeoutException as exc:
                last_error = f"Timeout: {exc}"
            except httpx.RequestError as exc:
                last_error = f"ConnectionError: {exc}"
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                last_error = f"Parse Error: {exc}"

            if attempt < request.retries - 1:
                wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                print(f"[search] retry {attempt + 1}: {last_error} (wait {wait}s)", file=sys.stderr)
                time.sleep(wait)

        return self._failed(
            request, f"search failed after {request.retries} attempts: {last_error}"
        )
