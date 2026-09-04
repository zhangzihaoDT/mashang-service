"""Search base capability — schemas, document model, and result contract.

A domain-agnostic web-search primitive (current provider: Doubao/Volc Global
Search). Query strategy — whether/when to search, how to refine, how to reason
over results — stays with the caller (Agent / business layer).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
DEFAULT_CACHE_DIR = os.path.join(_REPO_ROOT, "outputs", "search", "cache")
DEFAULT_TTL = 24 * 3600


# ── Document model ───────────────────────────────────────────────

@dataclass
class SearchDocument:
    title: str = ""
    url: str = ""
    snippet: str = ""
    source: str = ""
    publish_time: str = ""
    rank: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def snippet_text(snippet) -> str:
    """Snippet 归一：数组取 text 类型段拼接，字符串透传。"""
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


def cache_key(query: str, limit: int, snippet_length: int, provider: str) -> str:
    raw = json.dumps(
        {"provider": provider, "query": query, "limit": limit, "snippet_length": snippet_length},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Schemas ──────────────────────────────────────────────────────

@dataclass
class SearchRequest:
    query: str
    provider: str = "doubao_global"
    limit: int = 10
    snippet_length: int = 500
    use_cache: bool = True
    cache_ttl: int = DEFAULT_TTL
    cache_dir: Optional[str] = None
    refresh: bool = False
    timeout: int = 30
    retries: int = 3
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@dataclass
class SearchResponse:
    provider: str
    query: str
    status: str = "success"  # success | error
    cached: bool = False
    error: Optional[str] = None
    result_count: int = 0
    results: list[dict] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
