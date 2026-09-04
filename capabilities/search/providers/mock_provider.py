"""Mock search provider — offline sample results, for tests and smoke runs."""

from datetime import datetime, timezone

from capabilities.search.schemas import SearchResponse, SearchRequest


class MockSearchProvider:
    name = "mock"

    def search(self, request: SearchRequest) -> SearchResponse:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        results = [
            {
                "title": f"Mock 结果 1 for「{request.query}」",
                "url": "https://example.com/1",
                "snippet": "这是一条离线 mock 摘要，不依赖任何外部服务。",
                "source": "example.com",
                "publish_time": "",
                "rank": 1,
            }
        ]
        return SearchResponse(
            provider=self.name,
            query=request.query,
            status="success",
            cached=False,
            result_count=len(results),
            results=results,
            created_at=now,
        )
