from typing import Optional
from capabilities.search.schemas import SearchResponse, SearchRequest


class BaseSearchProvider:
    name: str = "base"

    def search(self, request: SearchRequest) -> SearchResponse:
        raise NotImplementedError


def get_provider(name: str) -> BaseSearchProvider:
    if name == "doubao_global":
        from capabilities.search.providers.doubao_global_provider import DoubaoGlobalProvider
        return DoubaoGlobalProvider()
    elif name == "mock":
        from capabilities.search.providers.mock_provider import MockSearchProvider
        return MockSearchProvider()
    else:
        raise ValueError(f"Unknown search provider: {name}")
