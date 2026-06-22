#!/usr/bin/env python
"""
MIIT 统一 HTTP 请求工具模块。

提供带重试、backoff、统一错误处理的 HTTP GET 请求。
"""

import time, sys
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

_retry_counter = 0


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.miit-eidc.org.cn/",
}

DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 1.5  # seconds


class NetworkError(RuntimeError):
    """网络请求失败，包含原始异常和 URL。"""

    def __init__(self, message: str, url: str = "", cause: Exception | None = None):
        self.url = url
        self.cause = cause
        super().__init__(message)


def http_get(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
    headers: dict | None = None,
) -> tuple[bytes, int]:
    """
    HTTP GET 请求。

    参数:
        url: 请求 URL
        timeout: 超时秒数
        retries: 重试次数
        backoff: 退避秒数（指数增长）
        headers: 额外请求头

    返回:
        (bytes, http_status_code)

    异常:
        NetworkError: 所有网络错误统一包装为此异常
    """
    req_headers = dict(DEFAULT_HEADERS)
    if headers:
        req_headers.update(headers)

    global _retry_counter
    last_error: Exception | None = None
    req = Request(url, headers=req_headers)

    for attempt in range(1, retries + 1):
        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return raw, resp.status
        except HTTPError as e:
            # HTTP errors (4xx, 5xx) — no retry for client errors
            if 400 <= e.code < 500 and e.code not in (429,):
                raise NetworkError(
                    f"HTTP {e.code} {url}",
                    url=url, cause=e,
                )
            last_error = e
            if attempt < retries:
                _retry_counter += 1
                wait = backoff ** attempt
                print(f"  [RETRY] [{attempt}/{retries}] HTTP {e.code} {url} — 等待 {wait:.1f}s", file=sys.stderr)
                time.sleep(wait)
        except TimeoutError as e:
            last_error = e
            if attempt < retries:
                _retry_counter += 1
                wait = backoff ** attempt
                print(f"  [RETRY] [{attempt}/{retries}] 超时 {url} — 等待 {wait:.1f}s", file=sys.stderr)
                time.sleep(wait)
        except URLError as e:
            last_error = e
            if attempt < retries:
                _retry_counter += 1
                wait = backoff ** attempt
                print(f"  [RETRY] [{attempt}/{retries}] URLError {url} — 等待 {wait:.1f}s", file=sys.stderr)
                time.sleep(wait)
        except OSError as e:
            last_error = e
            if attempt < retries:
                _retry_counter += 1
                wait = backoff ** attempt
                print(f"  [RETRY] [{attempt}/{retries}] OSError {url} — 等待 {wait:.1f}s", file=sys.stderr)
                time.sleep(wait)
        except Exception as e:
            raise NetworkError(
                f"未知错误 {url}: {type(e).__name__}: {e}",
                url=url, cause=e,
            )

    # All retries exhausted
    err_msg = f"请求失败（已重试 {retries} 次）{url}: {last_error}"
    raise NetworkError(err_msg, url=url, cause=last_error)


def http_get_text(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
    headers: dict | None = None,
) -> str:
    """HTTP GET 并返回 decoded UTF-8 文本。"""
    raw, status = http_get(url, timeout=timeout, retries=retries, backoff=backoff, headers=headers)
    return raw.decode("utf-8", errors="replace")


def get_and_reset_retry_count() -> int:
    """返回并重置全局网络 retry 计数器。"""
    global _retry_counter
    val = _retry_counter
    _retry_counter = 0
    return val
