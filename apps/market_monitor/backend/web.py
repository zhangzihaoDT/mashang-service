"""Read-only WSGI entry point for the independently deployed application."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import re
from datetime import date
from http import HTTPStatus
from pathlib import Path

from .snapshot import APP, SOURCES, encode, read_snapshot, snapshot_dir

LOG = logging.getLogger(__name__)
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
HEADERS = [
    ("Cache-Control", "no-store"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"),
]


def verify_access(header, accounts):
    scheme, _, credentials = header.partition(" ")
    if scheme.lower() != "basic":
        return False
    try:
        username, separator, token = base64.b64decode(credentials, validate=True).decode().partition(":")
    except (ValueError, binascii.Error):
        return False
    expected = accounts.get(username, "0" * 64)
    actual = hashlib.sha256(token.encode()).hexdigest()
    return hmac.compare_digest(actual, expected) and bool(separator) and username in accounts


def load_accounts():
    path = os.environ.get("MARKET_MONITOR_AUTH_FILE")
    if not path:
        raise ValueError("必须配置 MARKET_MONITOR_AUTH_FILE")
    accounts = json.loads(Path(path).read_bytes())
    if not isinstance(accounts, dict) or not accounts or any(
        not re.fullmatch(r"[A-Za-z0-9_.-]+", name)
        or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
        for name, digest in accounts.items()
    ):
        raise ValueError("权限文件必须为非空的用户名到 SHA-256 十六进制摘要映射")
    return accounts


def source_status(directory, source):
    metadata = SOURCES[source]
    try:
        snapshot = read_snapshot(directory, source)
    except (OSError, ValueError):
        LOG.exception("读取 %s 快照失败", source)
        snapshot = None
    if snapshot is None:
        return {**metadata, "state": "unavailable", "months": [], "latest_month": None}
    return {
        **metadata,
        "state": "available",
        "latest_month": snapshot["latest_month"],
        "months": sorted(snapshot["months"], reverse=True),
        "refreshed_at": snapshot["refreshed_at"],
        "upstream_updated_at": snapshot["upstream_updated_at"],
    }


def trend_window(months, month):
    end = date.fromisoformat(f"{month}-01")
    index = end.year * 12 + end.month - 1
    trend = []
    for position in range(max(12, index - 11), index + 1):
        year, offset = divmod(position, 12)
        key = f"{year:04d}-{offset + 1:02d}"
        metrics = months.get(key, {}).get("metrics", {})
        trend.append({"month": key, "total_sales": metrics.get("total_sales")})
    return trend


def create_app(directory=None, *, local=False):
    directory = snapshot_dir() if directory is None else directory
    accounts = None if local else load_accounts()
    assets = {
        uri: ((APP / "frontend" / filename).read_bytes(), mime)
        for uri, (filename, mime) in ASSETS.items()
    }

    def application(environ, start_response):
        method = environ["REQUEST_METHOD"]
        path = environ["PATH_INFO"]

        def respond(status, data, mime="application/json; charset=utf-8", extra=()):
            body = data if isinstance(data, bytes) else encode(data)
            headers = HEADERS + list(extra) + [
                ("Content-Type", mime), ("Content-Length", str(len(body))),
            ]
            start_response(f"{status} {HTTPStatus(status).phrase}", headers)
            return [] if method == "HEAD" else [body]

        if accounts is not None and not verify_access(environ.get("HTTP_AUTHORIZATION", ""), accounts):
            return respond(401, {"error": "authentication_required"}, extra=[
                ("WWW-Authenticate", 'Basic realm="China Automotive Market Monitor", charset="UTF-8"'),
            ])
        if method not in {"GET", "HEAD"}:
            return respond(405, {"error": "method_not_allowed"}, extra=[("Allow", "GET, HEAD")])
        if path in assets:
            return respond(200, *assets[path])
        if path == "/api/v1/status":
            return respond(200, {"sources": {key: source_status(directory, key) for key in SOURCES}})
        match = re.fullmatch(r"/api/v1/(insurance|miit)/([0-9]{4}-(?:0[1-9]|1[0-2]))", path)
        if match:
            source, month = match.groups()
            try:
                snapshot = read_snapshot(directory, source)
            except (OSError, ValueError):
                LOG.exception("读取 %s 快照失败", source)
                snapshot = None
            if snapshot is None:
                return respond(503, {"error": "source_unavailable", "source": source})
            months = snapshot["months"]
            if month not in months:
                return respond(404, {"error": "month_unavailable", "source": source, "month": month})
            response = {"month": month, "data": months[month]}
            if source == "insurance":
                response["trend"] = trend_window(months, month)
            return respond(200, response)
        return respond(404, {"error": "not_found"})

    return application
