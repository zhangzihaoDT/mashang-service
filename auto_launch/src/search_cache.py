"""
search_cache.py — query cache for Volc Search API。

缓存 key: provider + query + start_date + end_date + result_limit + mode + target_id
缓存路径: search_cache/{date}/{query_hash}.raw.json
默认 TTL: 24 小时
"""

import json, hashlib, os, time
from pathlib import Path
from datetime import datetime, timedelta


def _cache_key(provider: str, query: str, start_date: str, end_date: str,
               result_limit: int, mode: str, target_id: str) -> str:
    raw = f"{provider}|{query}|{start_date}|{end_date}|{result_limit}|{mode}|{target_id}"
    return hashlib.md5(raw.encode()).hexdigest()


def _cache_path(root_dir: str, query_hash: str, date: str = None) -> Path:
    d = date or datetime.now().strftime("%Y-%m-%d")
    p = Path(root_dir) / d / f"{query_hash}.raw.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_cache_key(provider: str, query: str, start_date: str, end_date: str,
                  result_limit: int, mode: str, target_id: str) -> str:
    return _cache_key(provider, query, start_date, end_date, result_limit, mode, target_id)


def is_cache_valid(cache_path: Path, ttl_hours: int = 24) -> bool:
    if not cache_path.exists():
        return False
    mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
    age = datetime.now() - mtime
    return age < timedelta(hours=ttl_hours)


def load_cache(cache_path: Path, ttl_hours: int = 24):
    if not is_cache_valid(cache_path, ttl_hours):
        return None
    with open(cache_path) as f:
        return json.load(f)


def save_cache(data: dict, cache_path: Path):
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def search_with_cache(client, query_text: str, result_limit: int,
                       cache_cfg: dict, date: str, mode: str, target_id: str,
                       provider: str = "doubao_search") -> dict:
    enabled = cache_cfg.get("enabled", True)
    refresh = cache_cfg.get("refresh", False)
    ttl = cache_cfg.get("ttl_hours", 24)
    root = cache_cfg.get("root_dir", "")

    if not enabled or refresh:
        result = client.search(query_text, result_limit)
        result["cache_status"] = "disabled" if not enabled else "refresh"
        result["api_called"] = True
        if not refresh and root:
            ck = get_cache_key(provider, query_text, date, date, result_limit, mode, target_id)
            save_cache(result, _cache_path(root, ck, date))
        return result

    ck = get_cache_key(provider, query_text, date, date, result_limit, mode, target_id)
    cp = _cache_path(root, ck, date)
    cached = load_cache(cp, ttl)

    if cached is not None:
        cached["cache_status"] = "hit"
        cached["api_called"] = False
        return cached

    result = client.search(query_text, result_limit)
    result["cache_status"] = "miss"
    result["api_called"] = True
    save_cache(result, cp)
    return result
